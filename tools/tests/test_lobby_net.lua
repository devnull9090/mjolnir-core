-- Run from the repository root with Lua 5.4:
--   lua tools/tests/test_lobby_net.lua
--
-- Drives MJOLNIRLobby's net.lua (messages from the host to its fireteam)
-- against stand-in controllers and a game state: Net.clients walks the
-- controllers (FindAllOf, ~25 ms on a converted map) only when the world's
-- players change, never while the host is alone, and every connected client
-- still gets every message (docs/lua_native_audit.md).
local function eq(actual, expected, label)
    assert(actual == expected, (label or "value") .. ": expected " .. tostring(expected) .. ", got " .. tostring(actual))
end

local walks = 0
local readable = true
local playerStates = {}   -- the game state's PlayerArray
local controllers = {}    -- what FindAllOf("PlayerController") finds

local function state(address)
    return { IsValid = function() return true end, GetAddress = function() return address end }
end

local playerArray = {
    ForEach = function(_, fn)
        for i, ps in ipairs(playerStates) do fn(i, { get = function() return ps end }) end
    end,
}
local world = {
    AuthorityGameMode = { IsValid = function() return true end },
}
setmetatable(world, { __index = function(_, key)
    if key == "GameState" then
        if not readable then error("no game state") end
        return { PlayerArray = playerArray }
    end
end })

local hostState = state(100)
local hostPc = {
    IsValid = function() return true end,
    IsLocalController = function() return true end,
    GetWorld = function() return world end,
    PlayerState = hostState,
}
local engine = {
    IsValid = function() return true end,
    GameViewport = { GameInstance = { LocalPlayers = { { PlayerController = hostPc } } } },
}

--- A client's controller: `connected` false is a joiner whose connection is
--- not up yet; `gone` is one that left.
local function client(address)
    local c = { state = state(address), received = {}, connected = true, gone = false }
    c.pc = {
        IsValid = function() return not c.gone end,
        IsLocalController = function() return false end,
        ClientMessage = function(_, msg) c.received[#c.received + 1] = msg end,
    }
    setmetatable(c.pc, { __index = function(_, key)
        if key == "Player" then
            return { IsValid = function() return c.connected and not c.gone end }
        elseif key == "PlayerState" then
            return c.state
        end
    end })
    return c
end

local env = setmetatable({
    FindFirstOf = function(class) return class == "GameEngine" and engine or nil end,
    FindAllOf = function(class)
        if class ~= "PlayerController" then return {} end
        walks = walks + 1
        local out = {}
        for i, pc in ipairs(controllers) do out[i] = pc end
        return out
    end,
    FName = function(s) return s end,
    print = function() end,
    RegisterHook = function() end,
    ExecuteInGameThread = function(fn) fn() end,
}, { __index = _G })
local Net = assert(loadfile("mods/MJOLNIRLobby/Scripts/net.lua", "t", env))()

-- The host alone, as on every solo or private test host: nothing to walk for.
playerStates = { hostState }
controllers = { hostPc }
for _ = 1, 5 do eq(Net.toClients("publicsession", "", "0", 1, 16), 0, "alone: no client") end
eq(walks, 0, "alone: the controllers are never walked")
eq(#Net.clients(), 0, "alone: no remote players")
eq(walks, 0, "alone: still no walk")

-- A client joins: one walk, then every message reaches it with no more.
local a = client(200)
playerStates = { hostState, a.state }
controllers = { hostPc, a.pc }
for _ = 1, 5 do eq(Net.toClients("publicsession", "id", "1", 2, 16), 1, "one client: sent") end
eq(walks, 1, "a joiner: one walk")
eq(#a.received, 5, "the joiner got every message")
eq(Net.toClients("vote", "v"), 1, "a repeated message too")
eq(walks, 1, "and with no further walk")

-- A second joins whose connection is not up yet: found by one walk, sent to
-- once it is up, with no walk in between.
local b = client(300)
b.connected = false
playerStates = { hostState, a.state, b.state }
controllers = { hostPc, a.pc, b.pc }
eq(Net.toClients("ids", "x"), 1, "a joiner still connecting gets nothing yet")
eq(walks, 2, "the new player state: one walk")
b.connected = true
eq(Net.toClients("ids", "x"), 2, "its connection up: both get the next")
eq(walks, 2, "no walk for that")

-- One leaves as another arrives (the count stays at three): the new player
-- state still makes a walk, and the one gone gets nothing.
local c = client(400)
a.gone = true
playerStates = { hostState, b.state, c.state }
controllers = { hostPc, b.pc, c.pc }
local before = #a.received
eq(Net.toClients("lobby", "BGL"), 2, "the stayer and the newcomer")
eq(walks, 3, "a changed player is a walk, even at the same count")
eq(#a.received, before, "nothing to the one who left")
eq(#c.received, 1, "the newcomer got it")

-- A new world (new player states, as after travel): a walk.
local b2, c2 = state(500), state(600)
b.state, c.state = b2, c2
playerStates = { state(150), b2, c2 }
eq(Net.toClients("starting", "BGL"), 2, "after travel")
eq(walks, 4, "a new world's players: one walk")

-- Kick lists and the host watch read the same cache.
local list = Net.clients()
eq(#list, 2, "Net.clients: the connected clients")
eq(walks, 4, "Net.clients: no walk")

-- The game state cannot be read: the old rules. A repeated message reuses a
-- walk under CONTROLLERS_SECONDS old; any other walks.
readable = false
eq(Net.toClients("publicsession", "id"), 2, "no game state: still sent")
eq(walks, 5, "no game state: a one-off walks")
eq(Net.toClients("vote", "v"), 2, "no game state: a repeat still sent")
eq(walks, 5, "no game state: a repeat reuses the fresh walk")
readable = true

print("test_lobby_net: ok")
