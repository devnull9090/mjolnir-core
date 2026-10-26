-- Run with Lua 5.4 from the repo root, or Python + lupa.
local Presence = dofile("mods/MJOLNIRLobby/Scripts/presence.lua")
local Session = dofile("mods/MJOLNIRLobby/Scripts/publicsession.lua")
local Snapshot = dofile("mods/MJOLNIRHud/Scripts/presence_snapshot.lua")
local Json = dofile("mods/MJOLNIRLobby/Scripts/json.lua")
local function eq(a, b, why) assert(a == b, (why or "value") .. ": " .. tostring(a) .. " != " .. tostring(b)) end

local match = { code = "BGL", title = "Blood Gulch", variant = "team_slayer", presenceStarted = 900,
    players = { [0] = { rawKills = 99, deaths = 2 }, [7] = { kills = -1, rawKills = 3, deaths = 4 } } }
local raw = Snapshot.encode(match, 7, "game-123", 1000)
local hud = assert(Presence.snapshot(raw, "game-123", 1001))
eq(hud.kills, 3, "local seat and raw kills, not penalized score or host seat")
eq(hud.deaths, 4)
eq(Presence.snapshot(raw, "old-process", 1001), nil)
eq(Presence.snapshot(raw, "game-123", 1005), nil)
eq(Presence.snapshot(raw, "game-123", 990), nil)
eq(Presence.snapshot(raw:gsub("kills=3", "kills=nan"), "game-123", 1001), nil)
eq(Presence.snapshot(raw:gsub("kills=3", "kills=1.5"), "game-123", 1001), nil)
eq(Presence.snapshot(Snapshot.encode(nil, 7, "game-123", 1000), "game-123", 1001), nil)
assert(Presence.snapshot(raw:gsub("title=Blood Gulch\n", ""), "game-123", 1001).title == "BGL")

local public = { id = "public-123", players = 6, maxPlayers = 16, joinable = true }
local activity = Presence.activity({ world_code = "BGL" }, hud, public)
eq(activity.name, "MJOLNIR Core")
eq(activity.details, "Blood Gulch | Team Slayer")
eq(activity.state, "3 kills | 4 deaths (observed)")
eq(activity.secrets.join, "mjolnir:v1:public-123")
eq(activity.timestamps.start, 900)
eq(activity.party.size[2], 16)
eq(Json.decode(Presence.encode(activity)).secrets.join, activity.secrets.join)
eq(Presence.activity({ world_code = "OTHER" }, hud, public).secrets, nil, "no stale HUD during travel")
hud.over = true
eq(Presence.activity({ world_code = "BGL" }, hud, public).secrets, nil)
eq(Presence.activity({ world_code = "BGL" }, hud, public).timestamps, nil)
eq(Presence.activity({ frontend = true }, hud, nil).details, "Main menu")
public.joinable = false
eq(Presence.activity({ frontend = true }, nil, public).secrets, nil)
eq(Presence.activity({ frontend = true, lobby = true, map_title = 'A "map"', mode = "ctf" }, nil, nil).details,
    'A "map" | Capture the Flag')
eq(Json.decode(Presence.encode({ value = 'quote"\\\n' })).value, 'quote"\\\n')

-- Byte limits must retain whole multibyte codepoints without a utf8 global
-- (UE4SS's LuaJIT runtime does not supply that Lua 5.3 library).
local function title(value)
    return Presence.activity({ frontend = true, lobby = true, map_title = value, mode = "slayer" }, nil, nil).details
end
local eAcute, han, emoji = string.char(0xC3, 0xA9), string.char(0xE6, 0xBC, 0xA2), string.char(0xF0, 0x9F, 0x8E, 0xAE)
eq(title(string.rep("a", 118) .. eAcute), string.rep("a", 118) .. eAcute)
eq(title(string.rep("a", 119) .. eAcute), string.rep("a", 119))
eq(title(string.rep("a", 117) .. han), string.rep("a", 117) .. han)
eq(title(string.rep("a", 118) .. han), string.rep("a", 118))
eq(title(string.rep("a", 116) .. emoji), string.rep("a", 116) .. emoji)
eq(title(string.rep("a", 117) .. emoji), string.rep("a", 117))
eq(title("Map" .. string.char(0xE6, 0xBC)), "Map | Slayer", "drop a truncated snapshot codepoint")

local host = { public = true, id = "host-123", confirmed = 1000, maxPlayers = 16 }
eq(Session.host(host, { players = 3, in_game = true }, 1001, true, true).joinable, true)
eq(Session.host(host, { players = 16 }, 1001, true, true).joinable, false)
eq(Session.host(host, { players = 3, in_game = true }, 1001, true, false).joinable, false)
eq(Session.host(host, { players = 3 }, 1046, true, true), nil, "stale heartbeat")
eq(Session.host(host, { players = 3 }, 1001, false, true), nil, "offline")
host.public = false
eq(Session.host(host, {}, 1001, true, true), nil)

local guest, answer = Session.new(), nil
guest:worldChanged("world-a")
guest:joining("host-123", 1000)
guest:receive({ "old-host", "1", "2", "16" }, 1001)
eq(guest.id, nil, "old host cannot confirm a new join")
guest:receive({ "host-123", "1", "3", "16" }, 1002)
eq(guest:guest(1002), nil, "host message is not a public listing check")
guest:check(1002, function(done) answer = done end)
local row = { id = "host-123", state = "in_game", players = 3, max_players = 16 }
answer({ row }, 1003)
eq(guest:guest(1003).id, "host-123")
eq(guest:guest(1015), nil, "host messages time out after leaving")
guest:receive({ "host-123", "0", "3", "16" }, 1004)
eq(guest:guest(1004).joinable, false, "host disables JIP")
guest:leave()
guest:receive({ "host-123", "1", "3", "16" }, 1005)
eq(guest.id, nil, "do not re-advertise while leave is pending")
guest:worldChanged("world-b")
guest:receive({ "host-123", "1", "3", "16" }, 1006)
guest:check(1006, function(done) answer = done end)
guest:worldChanged("world-c")
answer({ row }, 1007)
eq(guest:guest(1007), nil, "old hub callback cannot revive a departed world")
guest:receive({ "bad/id", "1", "3", "16" }, 1008)
eq(guest.id, nil)
print("Discord presence: activity, observed local stats, freshness, privacy, capacity and guest generations passed")

-- Drive the real games.lua with an asynchronous native mailbox. A delayed
-- registration/heartbeat must not resurrect a private or previous-world game.
local files, scheduled, requests, handlers, sent = {}, {}, {}, {}, {}
local time, world, isHost = 0, "world-1", true
local dir = "mods\\MJOLNIRLobby\\native\\"
local function open(path, mode)
    if mode:match("^r") then
        if files[path] == nil then return nil end
        return { read = function() return files[path] end, close = function() return true end }
    end
    files[path] = ""
    return { write = function(self, ...)
        for _, v in ipairs({ ... }) do files[path] = files[path] .. tostring(v) end
        return self
    end, close = function() return true end }
end
local env
env = setmetatable({
    io = { open = open },
    os = { time = function() return 1000 + math.floor(time) end, remove = function(path) files[path] = nil end },
    dofile = function(path) return assert(loadfile(path:gsub("\\", "/"), "t", env))() end,
    ExecuteInGameThreadWithDelay = function(ms, fn) scheduled[#scheduled + 1] = { at = time + ms / 1000, fn = fn } end,
    package = { loadlib = function(_, name) return function()
        if name == "mjolnir_lobby_connection" then files[dir .. "lobby_connection.txt"] = "ok connection-never-in-presence\n" end
        if name == "mjolnir_hub_call" then
            local id, method, path, body = files[dir .. "hub_request.txt"]:match("^(%S+) (%S+) (%S+)\n(.*)$")
            requests[#requests + 1] = { id = id, method = method, path = path, body = body }
        end
    end end },
}, { __index = _G })
local games = assert(loadfile("mods/MJOLNIRLobby/Scripts/games.lua", "t", env))()
local function advance(seconds)
    local target = time + seconds
    while true do
        table.sort(scheduled, function(a, b) return a.at < b.at end)
        if not scheduled[1] or scheduled[1].at > target then break end
        local event = table.remove(scheduled, 1)
        time = event.at
        event.fn()
    end
    time = target
end
local function latest(method, path)
    for i = #requests, 1, -1 do
        if requests[i].method == method and requests[i].path == path then return requests[i] end
    end
    error("no request " .. method .. " " .. path)
end
local function respond(request, status, data)
    files[dir .. "hub_reply_" .. request.id .. ".txt"] = status .. "\n" .. Presence.encode(data)
    advance(0.2)
end
games.init({ modDir = "mods\\MJOLNIRLobby", json = Json, log = function() end, version = "test",
    world = function() return world end,
    info = function() return { map_code = "BGL", game_type = "slayer", players = 2, in_game = false } end,
    net = { isHost = function() return isHost end,
        on = function(verb, fn) handlers[verb] = fn end,
        toClients = function(...) sent[#sent + 1] = { ... } end },
})
games.setPublic(true)
advance(1)
local abandoned = latest("POST", "/lobbies")
games.setPublic(false)
respond(abandoned, 201, { id = "orphan-1", token = "private-host-token" })
eq(latest("DELETE", "/lobbies/orphan-1").method, "DELETE")
eq(games.presence(), nil)
games.setPublic(true)
advance(1)
respond(latest("POST", "/lobbies"), 201, { id = "host-123", token = "private-host-token" })
advance(1)
eq(games.presence().id, "host-123")
games.changed()
advance(1)
local oldHeartbeat = latest("POST", "/lobbies/host-123/heartbeat")
world = "world-2"
advance(1)
local currentHeartbeat = latest("POST", "/lobbies/host-123/heartbeat")
assert(currentHeartbeat.id ~= oldHeartbeat.id)
respond(oldHeartbeat, 200, {})
eq(games.presence(), nil, "old heartbeat cannot reconfirm after travel")
respond(currentHeartbeat, 200, {})
advance(1)
eq(games.presence().id, "host-123")
assert(not Presence.encode(games.presence()):find("private%-host%-token"))
assert(not Presence.encode(games.presence()):find("connection%-never"))
-- The separate Discord publisher keeps polling even if Games.loop stops.
-- Advance the clock without producer callbacks: no old join target may leak.
time = time + 5
for _, event in ipairs(scheduled) do event.at = math.max(event.at, time) end
eq(games.presence(), nil, "a stopped producer cannot keep a cached Join secret alive")
advance(1)
eq(games.presence().id, "host-123", "a fresh successful producer tick restores presence")
isHost, world = false, "guest-world"
advance(1)
handlers.publicsession({ "host-123", "1", "2", "16" }, nil)
advance(1)
local validation = latest("GET", "/lobbies")
respond(validation, 200, { lobbies = { row } })
advance(1)
eq(games.presence().id, "host-123", "joined player advertises the host's session")
handlers.publicsession({ "", "0", "0", "0" }, nil)
advance(1)
eq(games.presence(), nil, "host privacy change clears the guest")
print("Discord presence: real lobby host/guest propagation and asynchronous registration/heartbeat races passed")

-- A failed activity write must not keep the previous native snapshot alive.
local callbacks, nativeCalls = {}, 0
local publisherEnv = setmetatable({
    io = { open = function(path, mode)
        if path:find("discord_activity.json", 1, true) then return nil end
        if mode == "rb" then return nil end
        return { write = function(self) return self end, close = function() return true end }
    end },
    ExecuteInGameThreadWithDelay = function(_, fn) callbacks[#callbacks + 1] = fn end,
    package = { loadlib = function() return function() nativeCalls = nativeCalls + 1 end end },
}, { __index = _G })
local publisher = assert(loadfile("mods/MJOLNIRLobby/Scripts/presence.lua", "t", publisherEnv))()
publisher.init({ modDir = "fake", json = Json, log = function() end })
callbacks[1]()
eq(nativeCalls, 0, "failed write lets native heartbeat expire")
print("Discord presence: failed publisher writes do not refresh stale activity")
