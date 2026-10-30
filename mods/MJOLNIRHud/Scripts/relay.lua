-- MJOLNIR HUD: the feed's incidents from the host to fireteam clients
-- (docs/multiplayer_hud.md, "On fireteam clients").
--
-- The host's incident handler gets every player's incidents; a fireteam
-- client's gets few of them (docs/match_stats.md). So after each drain the
-- host sends what the feed and the tallies need (kills, deaths, suicides,
-- medals, captures, joins and quits) to every remote player's controller, as
-- one ClientMessage of type "MJOLNIR" (the channel MJOLNIRLobby's messages
-- and the level loader's sound relay ride):
--
--   MJOLNIR|feed|kill,2,0,0,1,SniperRifle;death,2,0,0,0,SniperRifle
--                name,cause,effect,value,modifier,damage type
--
-- A client takes each incident once: one it has already had, from its own
-- handler or another relay (same name, cause and effect within WINDOW
-- seconds), is dropped. Nothing is assumed about which incidents a client
-- gets by itself.
--
-- Remote controllers are found without walking the object array each time
-- (FindAllOf costs ~20 ms on a converted map): one scan when the host's
-- match starts, then every controller made after it, as it is made.

local Relay = {}

Relay.PREFIX = "MJOLNIR|feed|"
Relay.WINDOW = 2.5
Relay.MAX = 16 -- incidents in one message

local CARRIED = {
    kill = true, suicide = true, death = true, first_blood = true, flag_scored = true,
    player_joined = true, player_rejoined = true, player_quit = true, player_booted_player = true,
    -- Who is alive on the scoreboard (#249): a client hears only its own spawns.
    player_spawn = true,
}

--- Whether the feed or the tallies need incident `name` on a client.
function Relay.carried(name)
    if type(name) ~= "string" then return false end
    return CARRIED[name] or name:match("^multikill_x%d+$") ~= nil or name:match("^%d+_in_a_row$") ~= nil
end

local function int(v)
    v = tonumber(v)
    if not v then return 0 end
    return math.floor(v)
end

--- One message for `incidents` (the carried ones, at most MAX); nil when
--- there is nothing to send.
function Relay.encode(incidents)
    local items = {}
    for _, inc in ipairs(incidents) do
        if Relay.carried(inc.name) and #items < Relay.MAX then
            local damage = type(inc.damage) == "string" and inc.damage:match("([%w_]+)$") or ""
            if damage == "Invalid" or damage == "None" then damage = "" end
            items[#items + 1] = string.format("%s,%d,%d,%d,%d,%s", inc.name, int(inc.cause), int(inc.effect),
                int(inc.value), int(inc.modifier), damage)
        end
    end
    if #items == 0 then return nil end
    return Relay.PREFIX .. table.concat(items, ";")
end

--- The incidents in a message (marked `relayed`, arrived at `t`), or nil
--- when it is not one of ours.
function Relay.decode(text, t)
    if type(text) ~= "string" or text:sub(1, #Relay.PREFIX) ~= Relay.PREFIX then return nil end
    local out = {}
    for item in text:sub(#Relay.PREFIX + 1):gmatch("[^;]+") do
        local name, cause, effect, value, modifier, damage =
            item:match("^([%w_]+),(-?%d+),(-?%d+),(-?%d+),(-?%d+),([%w_]*)$")
        if name and Relay.carried(name) then
            out[#out + 1] = { name = name, cause = tonumber(cause), effect = tonumber(effect), value = tonumber(value),
                modifier = tonumber(modifier), damage = damage ~= "" and damage or nil, at = t, relayed = true }
        end
    end
    return out
end

--- Whether `inc` was already taken: the same incident (name, cause, effect)
--- from another source (the machine's own handler, this relay, the level
--- loader's sound relay) within WINDOW seconds. Two from one source are two
--- incidents (a quick respawn can die twice to the same killer). Records it
--- when not. `recent` is the match's own table.
function Relay.seen(recent, inc)
    local key = inc.name .. "|" .. tostring(inc.cause) .. "|" .. tostring(inc.effect)
    local source = inc.source or (inc.relayed and "feed" or "own")
    local list = recent[key] or {}
    recent[key] = list
    for i = #list, 1, -1 do
        local r = list[i]
        if math.abs(inc.at - r.at) >= Relay.WINDOW then
            table.remove(list, i)
        elseif r.source ~= source then
            table.remove(list, i)
            return true
        end
    end
    list[#list + 1] = { at = inc.at, source = source }
    return false
end

--------------------------------------------------------------------------------
-- Remote controllers (the host)
--------------------------------------------------------------------------------

local remotes = {}   -- address -> controller
local rosterSent = {} -- address -> the bot roster it has had (Relay.syncBots)
local watching = false

local function track(pc)
    local ok, address = pcall(function() return pc:GetAddress() end)
    if ok and address then remotes[address] = pc end
end

--- On the host, when its match starts: the controllers there are now, and
--- from then on each one as it is made.
function Relay.arm()
    remotes = {}
    rosterSent = {}
    for _, pc in ipairs(FindAllOf("PlayerController") or {}) do track(pc) end
    if not watching then
        watching = pcall(NotifyOnNewObject, "/Script/Engine.PlayerController", track)
    end
end

--- The remote players' controllers now. Gone and local ones are dropped; one
--- whose player has not arrived yet is kept for later.
function Relay.controllers()
    local out = {}
    for address, pc in pairs(remotes) do
        local ok, state = pcall(function()
            if not pc:IsValid() then return "gone" end
            if pc:IsLocalController() then return "local" end
            if not (pc.Player:IsValid() and pc.PlayerState:IsValid()) then return "waiting" end
            return "remote"
        end)
        if not ok or state == "gone" or state == "local" then
            remotes[address] = nil
        elseif state == "remote" then
            out[#out + 1] = pc
        end
    end
    return out
end

--- The host's bots (Scripts/bots.lua) by seat, for the clients' feed and
--- board, which hear bot seats in the relayed incidents. A client asks for
--- it (BOTS_ASK) when its match starts; the host also sends it to everyone
--- when it changes:
---   MJOLNIR|bots|100=Desmond (bot);101=Kira (bot)
Relay.BOTS = "MJOLNIR|bots|"
--- What a client sends its host (ServerExecRPC) to be told the roster.
Relay.BOTS_ASK = "MJOLNIR|bots?"

function Relay.encodeBots(seats)
    local items = {}
    for _, s in ipairs(seats) do
        items[#items + 1] = string.format("%d=%s", s.index, (tostring(s.name):gsub("[;=|]", "")))
    end
    return Relay.BOTS .. table.concat(items, ";")
end

--- `{ [seat] = name }`, or nil when `text` is not a bot roster.
function Relay.decodeBots(text)
    if type(text) ~= "string" or text:sub(1, #Relay.BOTS) ~= Relay.BOTS then return nil end
    local out = {}
    for seat, name in text:sub(#Relay.BOTS + 1):gmatch("(%d+)=([^;]+)") do out[tonumber(seat)] = name end
    return out
end

--- Sends the bot roster `message` (version `version`) to each remote player
--- that has not had that version: once when the bots change, and once to
--- each player as they arrive. Returns how many got it.
function Relay.syncBots(message, version)
    local kind = FName("MJOLNIR")
    local sent = 0
    for _, pc in ipairs(Relay.controllers()) do
        local ok, address = pcall(function() return pc:GetAddress() end)
        if ok and address and rosterSent[address] ~= version then
            if pcall(function() pc:ClientMessage(message, kind, 0) end) then
                rosterSent[address] = version
                sent = sent + 1
            end
        end
    end
    return sent
end

--- Sends `incidents` to every remote player. Returns how many got it.
function Relay.send(incidents)
    local message = Relay.encode(incidents)
    if not message then return 0 end
    local kind = FName("MJOLNIR")
    local sent = 0
    for _, pc in ipairs(Relay.controllers()) do
        if pcall(function() pc:ClientMessage(message, kind, 0) end) then sent = sent + 1 end
    end
    return sent
end

return Relay
