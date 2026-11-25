-- Run from the repository root with Lua 5.4, or Python + lupa.
-- MJOLNIRLobby games.lua with a lobby DLL that has the in-memory exports
-- (native/lobby/mjolnir_lobby.c): hub calls go out as an argument and come
-- back from the mailbox, the lobby connection and the audio bind are
-- returned, and the held world is asked of the DLL. No request or reply file
-- is opened for any of them.
local checks = 0
local function eq(actual, expected, label)
    checks = checks + 1
    assert(actual == expected, (label or "value") .. ": expected " .. tostring(expected) .. ", got " .. tostring(actual))
end

local opened, scheduled, sent, mailbox, requests, claims = {}, {}, {}, {}, {}, {}
local time = 0
local held, declines = false, false
local exports = {
    mjolnir_hub_send = function(request)
        if declines then return nil end
        sent[#sent + 1] = request
        return true
    end,
    mjolnir_reply_take = function(name)
        local text = mailbox[name]
        mailbox[name] = nil
        return true, text
    end,
    mjolnir_lobby_connection_get = function() return "ok conn-1\nlock 0\nmax 8\n" end,
    mjolnir_jip_held = function() return held end,
    mjolnir_request_put = function(name, text, reply, keep)
        requests[name] = { text = text, reply = reply, keep = keep }
        return true
    end,
    mjolnir_reply_claim = function(name) claims[name] = true; return true end,
}
local env
env = setmetatable({
    io = { open = function(path, mode)
        opened[#opened + 1] = tostring(path) .. " " .. tostring(mode)
        return nil
    end },
    os = setmetatable({ time = function() return 1000 + math.floor(time) end,
        clock = function() return time end }, { __index = os }),
    ExecuteInGameThreadWithDelay = function(ms, fn) scheduled[#scheduled + 1] = { at = time + ms / 1000, fn = fn } end,
    package = { loadlib = function(_, name) return exports[name] or function() end end },
    -- The mod's own Windows paths, on any OS (CI runs Linux).
    dofile = function(path) return assert(loadfile((path:gsub("\\", "/")), "t", env))() end,
}, { __index = _G })
env._G = env
local Games = assert(loadfile("mods/MJOLNIRLobby/Scripts/games.lua", "t", env))()
local Json = assert(loadfile("mods/MJOLNIRLobby/Scripts/json.lua", "t", env))()
Games.init({
    modDir = "mods\\MJOLNIRLobby", json = Json, log = function() end, version = "test",
    world = function() return "world-1" end,
    info = function() return { map_code = "BGL", game_type = "slayer", players = 1, in_game = false } end,
    net = { isHost = function() return true end, on = function() end, toClients = function() end },
})
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
local function filesTouched(pattern)
    local n = 0
    for _, o in ipairs(opened) do if o:find(pattern) then n = n + 1 end end
    return n
end

-- A hub call: the request text as the file had it, the reply from the mailbox.
local status, data
Games.call("POST", "/lobbies/x/heartbeat", { players = 2 }, function(s, d) status, data = s, d end)
eq(#sent, 1, "one request handed over")
local id, method, path, body = sent[1]:match("^(%S+) (%S+) (%S+)\n(.*)$")
eq(method, "POST", "method")
eq(path, "/lobbies/x/heartbeat", "path")
eq(body, '{"players":2}', "body")
advance(0.3)
eq(status, nil, "no answer before the reply")
mailbox["hub_reply_" .. id .. ".txt"] = '200\n{"ok":true}'
advance(0.2)
eq(status, 200, "status from the mailbox")
eq(data and data.ok, true, "body from the mailbox")
eq(filesTouched("hub_"), 0, "no hub request or reply file")

-- The lobby connection, returned.
eq(Games.connectionText(), "ok conn-1\nlock 0\nmax 8\n", "connection text returned")
eq(filesTouched("lobby_connection"), 0, "no lobby_connection.txt")

-- The held world, asked of the DLL.
eq(Games.worldHeld(), false, "not held")
held = true
eq(Games.worldHeld(), true, "held")
eq(filesTouched("jip_held"), 0, "no jip_held.txt")

-- A DLL that cannot take the request (too long, or no Lua channel) answers
-- nil: the call goes through hub_request.txt instead.
declines = true
Games.call("GET", "/lobbies", nil, function() end)
eq(filesTouched("hub_request.txt"), 1, "file route when the DLL declines")

-- Request files the DLL reads: handed over in memory, the reply claimed and
-- taken from the mailbox; a setting kept for every read.
eq(Games.put("lobby_max.txt", "8", "lobby_max_reply.txt"), "memory", "request in memory")
eq(requests["lobby_max.txt"].text, "8", "request text")
eq(requests["lobby_max.txt"].reply, "lobby_max_reply.txt", "reply claimed")
eq(requests["lobby_max.txt"].keep, false, "one-shot by default")
mailbox["lobby_max_reply.txt"] = "ok 8\n"
eq(Games.reply("lobby_max_reply.txt", "memory"), "ok 8\n", "reply from the mailbox")
eq(Games.put("team_game.txt", "1", nil, true), "memory", "setting in memory")
eq(requests["team_game.txt"].keep, true, "setting kept")
eq(Games.claim("map_install_status.txt"), "memory", "a reply claimed without a request")
eq(claims["map_install_status.txt"], true, "claim reached the DLL")
eq(filesTouched("lobby_max") + filesTouched("team_game"), 0, "no request or reply file")

print("games memory channels: " .. checks .. " checks passed")
