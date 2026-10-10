-- MJOLNIR Lobby: hub identities in game (docs/player_identity.md).
--
-- In game a player is their Steam or Xbox name; everyone who plays online
-- signed the launcher in with Discord, so the screens show that hub account
-- instead: its name and avatar. A host cannot take a joiner's word for who
-- it is, so each player proves it with a ticket from the hub:
--
--   client  POST /identity/tickets {platform_name, audience = the host's account}
--   client -> host   iam|<ticket>
--   host    POST /identity/tickets/resolve {tickets}   -> the accounts
--   host -> clients  ids|<host account>|<roster>
--
-- Only the host the ticket names can trade it, and the host takes an answer
-- only for the in-game name of the controller that sent the ticket. The
-- roster is keyed by in-game name, as everything else between the host and
-- its fireteam is (ballots, bans, seats): each entry is the account's id,
-- name and public report count. Every machine writes what it knows to
-- identities.txt beside this mod, which MJOLNIRHud reads for the
-- scoreboard and kill feed, and caches each account's avatar as
-- MJOLNIRMaps\_covers\av_<id>.png through the hub (the game's hub call
-- reaches nothing else).
--
-- A player the hub has banned from matchmaking still gets a ticket; a public
-- game's host that resolves one sends them back to their menu.

local Identity = {}

local TICKET_RETRY = 20     -- seconds between a client's tries to be on the roster
local WHOIS_SECONDS = 15    -- a client with no roster from its host asks this often
local SHARE_SECONDS = 30    -- the host re-sends the roster this often
local ME_RETRY = 60         -- after the hub did not say who we are

local Games, Net, log, dir, coversDir, localName, presentNames, isPublic, onBanned, worldContext
local me = nil              -- { id, name, reports } for this machine's account
local meBan = nil           -- the ban this account is under, as the hub said
local nextMe = 0
local asking = false
local hostId = nil          -- the host's account (a client learns it from ids)
local roster = {}           -- [in-game name] = { id, name, reports }
local lastIds = nil         -- when a client last heard ids
local nextTicket = 0
local nextWhois = 0
local lastWhois = -10       -- host: the last whois it answered
local pending = {}          -- host: tickets to resolve, { ticket, sender }
local resolving = false
local dirty = false
local nextShare = 0
local fetched = {}          -- avatars fetched this session, by account id
local textures = {}         -- account id -> texture object name
local wasHost = nil

local function now() return os.clock() end

local function writeFile(path, text)
    local f = io.open(path, "wb")
    if not f then return false end
    f:write(text)
    f:close()
    return true
end

local function exists(path)
    local f = io.open(path, "rb")
    if not f then return false end
    f:close()
    return true
end

local function valid(o)
    local ok, v = pcall(function() return o and o:IsValid() end)
    return ok and v
end

-- Fields of the roster ride inside one message field: percent-escape the
-- characters that separate them (and the message's own).
local function esc(s)
    return (tostring(s or ""):gsub("[%%;,|\t\r\n]", function(c) return string.format("%%%02X", c:byte()) end))
end

local function unesc(s)
    return (tostring(s or ""):gsub("%%(%x%x)", function(h) return string.char(tonumber(h, 16)) end))
end

local function encodeRoster()
    local parts = {}
    for platform, p in pairs(roster) do
        parts[#parts + 1] = table.concat({ esc(platform), esc(p.id), esc(p.name), tostring(p.reports or 0) }, ",")
    end
    table.sort(parts)
    return table.concat(parts, ";")
end

local function decodeRoster(text)
    local out = {}
    for entry in (text or ""):gmatch("[^;]+") do
        local platform, id, name, reports = entry:match("^([^,]*),([^,]*),([^,]*),(%d*)$")
        if platform and id and id:match("^[%x%-]+$") then
            out[unesc(platform)] = { id = id, name = unesc(name), reports = tonumber(reports) or 0 }
        end
    end
    return out
end

--- The avatar file of account `id`, fetched from the hub once a session (a
--- new avatar arrives with the next sign-in); the cached file meanwhile.
local function avatarFile(id) return coversDir .. "av_" .. id .. ".png" end

local function fetchAvatar(id)
    if fetched[id] or not id:match("^%x[%x%-]+$") then return end
    fetched[id] = true
    Games.call("FILE", "/users/" .. id .. "/avatar av_" .. id .. ".png", nil, function(status, data)
        if status == 200 and type(data) == "table" and data.saved == true then
            textures[id] = nil
        else
            log("identity: avatar " .. id .. ": the hub answered " .. tostring(status))
        end
    end)
end

--- What this machine knows, for MJOLNIRHud: one line per player,
--- "<in-game name>\t<account id>\t<hub name>\t<reports>".
local function save()
    local lines = {}
    for platform, p in pairs(roster) do
        lines[#lines + 1] = table.concat({ (platform:gsub("[\t\r\n]", " ")), p.id,
            (tostring(p.name):gsub("[\t\r\n]", " ")), tostring(p.reports or 0) }, "\t")
    end
    table.sort(lines)
    writeFile(dir .. "\\identities.txt", table.concat(lines, "\n") .. (#lines > 0 and "\n" or ""))
    for _, p in pairs(roster) do fetchAvatar(p.id) end
end

local function setRoster(next_)
    local before = encodeRoster()
    roster = next_
    if encodeRoster() ~= before then
        save()
        return true
    end
    return false
end

--- Who this machine's launcher signed in as (POST /identity/tickets with no
--- audience answers that without making a ticket).
local function askMe()
    if me or asking or now() < nextMe then return end
    local name = localName()
    if not name then return end
    asking = true
    Games.call("POST", "/identity/tickets", { platform_name = name:sub(1, 64) }, function(status, data)
        asking = false
        if status == 201 and type(data) == "table" and type(data.player) == "table" then
            me = { id = data.player.id, name = data.player.name, reports = 0 }
            meBan = data.matchmaking_ban
            log("identity: signed in as " .. tostring(me.name) .. (meBan and " (banned from matchmaking)" or ""))
            dirty = true
        else
            nextMe = now() + ME_RETRY
            if status ~= 0 then log("identity: the hub answered " .. tostring(status) .. " (who am I)") end
        end
    end)
end

--------------------------------------------------------------------------------
-- The host
--------------------------------------------------------------------------------

local function share()
    nextShare = now() + SHARE_SECONDS
    dirty = false
    Net.toClients("ids", me and me.id or "", encodeRoster())
end

local function resolve()
    if resolving or #pending == 0 then return end
    local batch = {}
    for i = 1, math.min(#pending, 16) do batch[i] = table.remove(pending, 1) end
    local tickets = {}
    for i, t in ipairs(batch) do tickets[i] = '"' .. t.ticket .. '"' end
    resolving = true
    Games.call("POST", "/identity/tickets/resolve", '{"tickets":[' .. table.concat(tickets, ",") .. "]}",
        function(status, data)
            resolving = false
            if status ~= 200 or type(data) ~= "table" or type(data.players) ~= "table" then
                log("identity: resolving tickets: the hub answered " .. tostring(status))
                return
            end
            local next_ = {}
            for k, v in pairs(roster) do next_[k] = v end
            for _, r in ipairs(data.players) do
                for _, t in ipairs(batch) do
                    -- The ticket must be the sender's own: issued for the
                    -- in-game name of the controller that sent it.
                    if t.ticket == r.ticket and r.platform_name == t.sender and type(r.player) == "table" then
                        next_[t.sender] = { id = r.player.id, name = r.player.name, reports = tonumber(r.reports) or 0 }
                        log(string.format("identity: %s is %s", t.sender, tostring(r.player.name)))
                        if type(r.matchmaking_ban) == "table" and isPublic() then
                            onBanned(t.sender, "Banned from matchmaking: " .. tostring(r.matchmaking_ban.reason))
                        end
                    end
                end
            end
            if setRoster(next_) then dirty = true end
        end)
end

local function hostTick()
    askMe()
    local mine = localName()
    local next_ = {}
    local present = presentNames()
    for _, name in ipairs(present) do
        if roster[name] then next_[name] = roster[name] end
    end
    if me and mine then next_[mine] = me end
    if setRoster(next_) then dirty = true end
    resolve()
    if me and (dirty or (#present > 1 and now() >= nextShare)) then share() end
end

--------------------------------------------------------------------------------
-- A fireteam client
--------------------------------------------------------------------------------

local function clientTick()
    askMe()
    local mine = localName()
    if not mine then return end
    if (not lastIds or now() - lastIds > SHARE_SECONDS * 2) and now() >= nextWhois and #presentNames() > 1 then
        nextWhois = now() + WHOIS_SECONDS
        Net.toHost("whois")
    end
    if roster[mine] or not hostId or hostId == "" or now() < nextTicket then return end
    nextTicket = now() + TICKET_RETRY
    Games.call("POST", "/identity/tickets", { platform_name = mine:sub(1, 64), audience = hostId },
        function(status, data)
            if status == 201 and type(data) == "table" and type(data.ticket) == "string" then
                Net.toHost("iam", data.ticket)
            elseif status ~= 0 then
                log("identity: ticket for the host: the hub answered " .. tostring(status))
            end
        end)
end

--------------------------------------------------------------------------------
-- Public
--------------------------------------------------------------------------------

--- Each second from MJOLNIRLobby's poll.
function Identity.tick(host)
    if host ~= wasHost then
        -- A new role, a new session: forget the last one's roster.
        wasHost = host
        hostId, lastIds = nil, nil
        pending = {}
        setRoster({})
        dirty = true
    end
    local ok, err = pcall(host and hostTick or clientTick)
    if not ok then log("identity: " .. tostring(err)) end
end

--- The hub account behind in-game name `name`: { id, name, reports } or nil.
function Identity.lookup(name)
    return name and roster[name] or nil
end

--- This machine's account, and the matchmaking ban it is under.
function Identity.me() return me, meBan end

--- Account `id`'s avatar as a texture, once its file is cached. Kept by
--- name, never by reference, as map covers are (maplive.lua).
function Identity.avatar(id)
    if not id then return nil end
    local path = avatarFile(id)
    if not exists(path) then
        fetchAvatar(id)
        return nil
    end
    if textures[id] then
        local ok, tex = pcall(StaticFindObject, textures[id])
        if ok and valid(tex) then return tex end
    end
    local krl = StaticFindObject("/Script/Engine.Default__KismetRenderingLibrary")
    local world = worldContext()
    if not (valid(krl) and world) then return nil end
    local ok, tex = pcall(function() return krl:ImportFileAsTexture2D(world, path) end)
    if not (ok and valid(tex)) then return nil end
    local okName, full = pcall(function() return tex:GetFullName() end)
    textures[id] = okName and full and full:match("^%S+%s+(.+)$") or nil
    return tex
end

--- deps: { Games, Net, log, modDir, coversDir, localName(), presentNames(),
--- isPublic(), onBanned(name, why), worldContext() }.
function Identity.init(deps)
    Games, Net, log = deps.Games, deps.Net, deps.log
    dir, coversDir = deps.modDir, deps.coversDir
    localName, presentNames = deps.localName, deps.presentNames
    isPublic, onBanned, worldContext = deps.isPublic, deps.onBanned, deps.worldContext
    writeFile(dir .. "\\identities.txt", "")

    -- A client proves itself to the host.
    Net.on("iam", function(f, sender)
        local ticket = f[1]
        if not (sender and sender ~= "?" and type(ticket) == "string" and ticket:match("^%x+$") and #ticket == 48) then
            return
        end
        for _, t in ipairs(pending) do
            if t.sender == sender then t.ticket = ticket return end
        end
        if #pending < 32 then pending[#pending + 1] = { ticket = ticket, sender = sender } end
    end)
    -- A client with no roster yet asks for it.
    Net.on("whois", function()
        if now() - lastWhois >= 3 then
            lastWhois = now()
            dirty = true
        end
    end)
    -- The host's roster.
    Net.on("ids", function(f)
        hostId = f[1] ~= "" and f[1] or nil
        lastIds = now()
        setRoster(decodeRoster(f[2]))
    end)
end

return Identity
