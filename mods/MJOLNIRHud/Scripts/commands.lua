-- MJOLNIR HUD: slash commands in match chat (docs/multiplayer_hud.md,
-- "Slash commands").
--
-- A chat line that starts with "/" is a command, never chat: it is not
-- relayed and not recorded. Typing "/" lists the commands this player may
-- use; Tab completes the highlighted one, or a player's name after it.
--
-- The host runs every command. A fireteam client sends
-- "MJOLNIR|cmd|<line>" over ServerExecRPC; the host takes the sender from
-- the controller the RPC came in on, never from the line, and answers that
-- player alone with a system line. Host commands run only from the host's
-- own chat box: a client's /kick is refused, whatever it says.
--
-- What the commands use:
--   kick, ban, unban   MJOLNIRLobby's own (`mjolnir_auto kick|ban|unban`)
--   suicide, slay      (unit_kill (player_get <index>)) through the Blam
--                      console's mailbox (MJOLNIRBlamConsole), one line a poll
--   bench              Scripts/bench.lua's foliage bench, sent to the hub
--                      (POST /benches); runs where it is typed
--   tp, bring          objects_attach then objects_detach, a poll apart:
--                      the attached object takes its parent's place
--                      (experimental: not tried with two players yet)

local Commands = {}

Commands.PREFIX = "MJOLNIR|cmd|"
Commands.ROWS = 6 -- build_mjolnir_ui.py CHAT_SUGGEST_ROWS

--- Every command: who may use it ("all" or "host"), its arguments, what it
--- does, and whether it runs where it is typed (`here`) instead of on the
--- host.
local LIST = {
    { name = "help", who = "all", help = "List the commands", here = true },
    { name = "players", who = "all", help = "List the players in the match", here = true },
    { name = "bench", who = "all", help = "Time this map with and without its foliage, and send it to the hub", here = true },
    { name = "suicide", who = "all", help = "Kill your player, to respawn when stuck", aliases = { "respawn" } },
    { name = "kick", who = "host", args = "<player>", help = "Send a player back to their menu", player = true },
    { name = "ban", who = "host", args = "<player>", help = "Kick a player and keep them out of your games", player = true },
    { name = "unban", who = "host", args = "<name>", help = "Let a banned name join again" },
    { name = "slay", who = "host", args = "<player>", help = "Kill a player", player = true },
    { name = "tp", who = "host", args = "<player>", help = "Teleport to a player (experimental)", player = true },
    { name = "bring", who = "host", args = "<player>", help = "Teleport a player to you (experimental)", player = true },
}
local BY_NAME = {}
for _, c in ipairs(LIST) do
    BY_NAME[c.name] = c
    for _, a in ipairs(c.aliases or {}) do BY_NAME[a] = c end
end

--- "/kick  bob smith" -> "kick", "bob smith"; nil for a line that is not a
--- command.
function Commands.parse(text)
    if type(text) ~= "string" then return nil end
    local name, rest = text:match("^%s*/(%S*)%s*(.-)%s*$")
    if not name then return nil end
    return string.lower(name), rest
end

function Commands.find(name)
    return BY_NAME[name]
end

local function allowed(c, isHost)
    return c.who == "all" or (c.who == "host" and isHost)
end

--- The commands `isHost` may use, in order.
function Commands.visible(isHost)
    local out = {}
    for _, c in ipairs(LIST) do
        if allowed(c, isHost) then out[#out + 1] = c end
    end
    return out
end

--- What to suggest for `text` as typed: commands while the name is being
--- typed, players once a command that takes one has its space. Each is
--- { label, help, complete } where `complete` replaces the box's text.
--- `names` are the players' names as shown.
function Commands.suggest(text, isHost, names)
    local name, rest = Commands.parse(text)
    if not name then return {} end
    local out = {}
    local spaced = text:match("^%s*/%S+%s") ~= nil
    if not spaced then
        for _, c in ipairs(Commands.visible(isHost)) do
            if c.name:sub(1, #name) == name then
                out[#out + 1] = { label = "/" .. c.name .. (c.args and (" " .. c.args) or ""), help = c.help,
                    complete = "/" .. c.name .. (c.args and " " or "") }
            end
        end
        return out
    end
    local c = BY_NAME[name]
    if not (c and c.player and allowed(c, isHost)) then return {} end
    local want = string.lower(rest)
    for _, n in ipairs(names or {}) do
        if want == "" or string.lower(n):find(want, 1, true) then
            out[#out + 1] = { label = n, help = c.help, complete = "/" .. c.name .. " " .. n }
        end
    end
    return out
end

--- The player `query` names, from `players` ({ index, name, display }):
--- an exact name, else the only one it starts, else the only one it is in.
--- Returns the player, or nil and why.
function Commands.resolve(players, query)
    query = string.lower(query or "")
    if query == "" then return nil, "name a player" end
    local function names(p)
        return string.lower(p.display or p.name or ""), string.lower(p.name or "")
    end
    for _, p in ipairs(players) do
        local d, n = names(p)
        if d == query or n == query then return p end
    end
    for _, how in ipairs({ "start", "within" }) do
        local hits = {}
        for _, p in ipairs(players) do
            local d, n = names(p)
            local hit
            if how == "start" then
                hit = d:sub(1, #query) == query or n:sub(1, #query) == query
            else
                hit = d:find(query, 1, true) or n:find(query, 1, true)
            end
            if hit then hits[#hits + 1] = p end
        end
        if #hits == 1 then return hits[1] end
        if #hits > 1 then
            local shown = {}
            for _, p in ipairs(hits) do shown[#shown + 1] = p.display or p.name end
            return nil, "'" .. query .. "' could be " .. table.concat(shown, ", ")
        end
    end
    return nil, "no player called '" .. query .. "'"
end

--------------------------------------------------------------------------------
-- Running them
--------------------------------------------------------------------------------

--- The lines /help shows `isHost`.
function Commands.helpLines(isHost)
    local out = { "Commands (Tab completes):" }
    for _, c in ipairs(Commands.visible(isHost)) do
        out[#out + 1] = "/" .. c.name .. (c.args and (" " .. c.args) or "") .. "  " .. c.help
    end
    return out
end

local function unitOf(index)
    return string.format("(player_get %d)", index)
end

--- Runs `text` on the host. `who` = { name, index, here } for the sender:
--- `here` when it was typed on the host itself, `index` its seat (nil when
--- not seated yet). `cx` = { players (), kick (name, ban), unban (name),
--- blam (line), isHost }. Returns the lines to answer the sender with.
function Commands.run(cx, who, text)
    local name, rest = Commands.parse(text)
    local c = name and BY_NAME[name]
    if not c then
        return { "Unknown command /" .. tostring(name) .. ". Type /help for the list." }
    end
    if c.who == "host" and not who.here then
        return { "/" .. c.name .. " is for the host." }
    end
    if c.here then
        -- Typed on a client, these never reach the host; on the host itself
        -- they run here like any other.
        if c.name == "help" then return Commands.helpLines(cx.isHost) end
        if c.name == "bench" then return cx.bench() end
        local out = {}
        for _, p in ipairs(cx.players()) do out[#out + 1] = (p.display or p.name) end
        table.sort(out)
        return { #out .. " in the match: " .. table.concat(out, ", ") }
    end
    if c.name == "suicide" then
        if type(who.index) ~= "number" then return { "You are not seated yet. Try again in a few seconds." } end
        cx.blam("(unit_kill " .. unitOf(who.index) .. ")")
        return {}
    end
    if c.name == "unban" then
        if rest == "" then return { "/unban <name>" } end
        cx.unban(rest)
        return { "Unbanned " .. rest .. "." }
    end
    local target, why = Commands.resolve(cx.players(), rest)
    if not target then return { "/" .. c.name .. ": " .. why .. "." } end
    local shown = target.display or target.name
    if c.name == "kick" or c.name == "ban" then
        if target.index == who.index then return { "You can't " .. c.name .. " yourself." } end
        cx.kick(target.name, c.name == "ban")
        return { (c.name == "ban" and "Banned " or "Kicked ") .. shown .. "." }
    end
    if c.name == "slay" then
        cx.blam("(unit_kill " .. unitOf(target.index) .. ")")
        return { "Killed " .. shown .. "." }
    end
    if type(who.index) ~= "number" then return { "You are not seated yet." } end
    if target.index == who.index then return { "That's you." } end
    -- objects_attach parent marker child marker: the child goes to the
    -- parent; detached a poll later, it stays where the parent stands.
    local parent, child = unitOf(target.index), unitOf(who.index)
    if c.name == "bring" then parent, child = unitOf(who.index), unitOf(target.index) end
    cx.blam("(objects_attach " .. parent .. ' "" ' .. child .. ' "")')
    cx.blam("(objects_detach " .. parent .. " " .. child .. ")")
    return { (c.name == "tp" and "Teleported to " or "Brought ") .. shown .. (c.name == "bring" and " to you." or ".") }
end

--------------------------------------------------------------------------------
-- The Blam console's mailbox (host)
--------------------------------------------------------------------------------
-- MJOLNIRBlamConsole's native half takes one line at a time from
-- native\request.txt ("<id> <flags>\n<line>") when its pump runs, and puts
-- the answer, under the same id, in response.txt. The console's own lines
-- use small ids and it reads only the answer it waits for, so ours start
-- high. One a poll: the mailbox has one slot.

local BLAM_ID0 = 7000000
local blam = { queue = {}, id = BLAM_ID0, pump = nil, dir = nil, missing = false }

function Commands.initBlam(modsDir)
    blam.dir = modsDir .. "\\MJOLNIRBlamConsole\\native\\"
end

--- Loads the console's native half and installs it, at a host's match
--- start: its hook goes in on the first pump, better before a fight than
--- in one. False when the console mod is not installed.
function Commands.prepareBlam()
    if blam.pump then return true end
    if blam.missing or not blam.dir then return false end
    local fn = package and package.loadlib and package.loadlib(blam.dir .. "mjolnir_blam_console.dll", "mjolnir_blam_pump")
    if not fn then
        blam.missing = true
        return false
    end
    blam.pump = fn
    pcall(fn)
    return true
end

function Commands.queueBlam(line)
    if #blam.queue < 16 then blam.queue[#blam.queue + 1] = line end
end

--- Sends the next queued line, if any. Each poll on the host.
function Commands.pumpBlam()
    if #blam.queue == 0 or not Commands.prepareBlam() then return end
    local line = table.remove(blam.queue, 1)
    blam.id = blam.id + 1
    local f = io.open(blam.dir .. "request.txt", "wb")
    if not f then return end
    f:write(string.format("%d 0\n%s\n", blam.id, line))
    f:close()
    pcall(blam.pump)
end

function Commands.blamReady()
    return Commands.prepareBlam()
end

return Commands
