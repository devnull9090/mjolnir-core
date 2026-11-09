-- MJOLNIR Lobby after a match and at a start, through main.lua's own code
-- with no game: three problems from the 2026-11-07 two-PC run.
--   1. The host's Quit (LeaveGame) opened the post-game vote, and with nobody
--      voting it started another match. A quit now opens the lobby; a real
--      end still votes and starts the winner.
--   2. A map in a maps.json whose world is in no container was voted for and
--      stranded the fireteam. It is no longer listed or voted on, its start
--      fails with a reason, and a vote whose game cannot start takes
--      everyone back to the lobby.
--   3. A joiner without the host's map left with only CONNECTION LOST. It is
--      now told which map, that it lacks it, and offered the download.
local checks = 0
local function eq(actual, expected, label)
    checks = checks + 1
    assert(actual == expected, (label or "value") .. ": expected " .. tostring(expected) .. ", got " .. tostring(actual))
end
local function has(text, part, label)
    checks = checks + 1
    assert(type(text) == "string" and text:find(part, 1, true), (label or "text") .. ": no '" .. part .. "' in " .. tostring(text))
end

-------------------------------------------------------------------------------
-- A game that is not there
-------------------------------------------------------------------------------

local worldName = "Frontend"
local worldAddress = 1         -- the world's identity; a fireteam leave loads a fresh frontend
local host = true
local worlds = nil            -- MapLive.worlds' answers by code; nil: cannot say
local staleWorld = nil        -- a code whose world is only found missing when asked afresh
local otherRelease = {}       -- code -> true: this PC has another release than the host's
local results = nil           -- MJOLNIRHud's last_match.txt
local logs, sent, hooks, handlers, queued, pushed, calls = {}, {}, {}, {}, {}, {}, {}
local left = 0                -- fireteam leaves

local MAPS = '[{"code":"BGL","title":"Blood Gulch","modes":["slayer","koth"]},'
    .. '{"code":"PRS","title":"Prisoner","modes":["slayer","koth"]},'
    .. '{"code":"DCN","title":"Danger Canyon","modes":["slayer"]}]'
-- A leftover of `mjolnir level bake --install-test`: listed, never mounted.
local DEV_MAPS = '[{"code":"ZZT","title":"Ivory Tower","modes":["slayer"]}]'

local function anything(name)
    return setmetatable({}, { __index = function(_, k)
        if k == "IsValid" then return function() return true end end
        if k == "GetCampaignSetup" then
            return function(_, _, _, out) calls[#calls + 1] = k; out.CampaignSetup = anything("setup") end
        end
        return function() calls[#calls + 1] = k; return anything(k) end
    end })
end
local function permissive()
    return setmetatable({}, { __index = function(t, k)
        local f = function() end
        rawset(t, k, f)
        return f
    end })
end

local netDriver = nil           -- the world's net driver; nil: none to reach
local mainMenu = { IsValid = function() return true end, IsVisible = function() return true end,
    IsActivated = function() return true end }
local pc = {
    IsValid = function() return true end,
    GetWorld = function()
        return {
            GetFName = function() return { ToString = function() return worldName end } end,
            AuthorityGameMode = { IsValid = function() return host end },
            GetAddress = function() return worldAddress end,
            NetDriver = netDriver,
        }
    end,
    PlayerState = { GetPlayerName = function() return { ToString = function() return "devnull" end } end },
}
local UI = permissive()
UI.log = function(m) logs[#logs + 1] = m end
UI.valid = function(o) return type(o) == "table" and o.IsValid ~= nil and o:IsValid() end
UI.playerController = function() return pc end
UI.liveWidget = function(name, alive)
    if name == "WBP_MainMenu_C" and alive(mainMenu) then return mainMenu end
    return nil
end
UI.push = function(spec)
    pushed[#pushed + 1] = spec
    return { screen = anything("screen"), spec = spec, buttons = {} }
end

local MapLive = permissive()
MapLive.worlds = function(codes, fresh)
    if not worlds then return nil end
    local out = {}
    for _, code in ipairs(codes) do
        out[code] = worlds[code]
        if fresh and code == staleWorld then out[code] = false end
    end
    return out
end
MapLive.register = function() return true end
MapLive.differs = function(code, release) return release ~= nil and otherRelease[code] == true end
MapLive.place = function() return 3 end

local Net = permissive()
Net.on = function(verb, fn) handlers[verb] = fn end
Net.isHost = function() return host end
Net.toClients = function(verb, ...) sent[#sent + 1] = { verb, ... } end
Net.toClient = function(_, verb, ...) sent[#sent + 1] = { verb, ... }; return true end
Net.clients = function() return {} end   -- no client connected

local Modes = dofile("mods/MJOLNIRLobby/Scripts/modes.lua")
Modes.writeChoice = function() end
local Games = permissive()
Games.isPublic = function() return false end
Games.status = function() return "" end
local modules = {
    ui = UI, net = Net, maplive = MapLive, modes = Modes, games = Games,
    json = dofile("mods/MJOLNIRLobby/Scripts/json.lua"),
    settings = setmetatable({ variantLine = function() return "" end }, getmetatable(permissive())),
    class_lifetime = { new = function() return function(_, cls) return cls end end },
    gametype = { new = function() return permissive() end },
}

local function contents(path)
    if path:find("MJOLNIRMaps\\maps.json", 1, true) then return MAPS end
    if path:find("MJOLNIRLevelLoader\\maps.json", 1, true) then return DEV_MAPS end
    if path:find("\\variants\\", 1, true) then return "" end
    if path:find("MJOLNIRHud\\last_match.txt", 1, true) then return results end
    return nil
end
local viewModel = {
    CanLeaveFireteam = function() return true end,
    -- The game's own leave loads the frontend again, a new world.
    LeaveFireteam = function() left = left + 1 worldAddress = worldAddress + 1 end,
}
local env = setmetatable({
    print = function() end,
    dofile = function(path)
        local name = assert(path:match("([^\\]+)%.lua$"))
        modules[name] = modules[name] or permissive()
        return modules[name]
    end,
    io = { open = function(path, mode)
        if mode:find("r", 1, true) then
            local text = contents(path)
            if not text then return nil end
            return { read = function() return text end, close = function() end }
        end
        return { write = function() end, close = function() end }
    end },
    package = { loadlib = function() return nil end },
    RegisterHook = function(name, fn) hooks[name] = fn end,
    RegisterConsoleCommandHandler = function() end,
    NotifyOnNewObject = function() end,
    ExecuteInGameThread = function(fn) fn() end,
    ExecuteInGameThreadWithDelay = function(_, fn) queued[#queued + 1] = fn end,
    StaticFindObject = function(path) return anything(path) end,
    FindFirstOf = function() return nil end,
    FindAllOf = function(class) return class == "MeteoritePlayerViewModel" and { viewModel } or {} end,
    FName = function(s) return s end,
    FText = function(s) return s end,
}, { __index = _G })
assert(loadfile("mods/MJOLNIRLobby/Scripts/main.lua", "t", env))()
local initialize = assert(queued[1], "the deferred initializer")
queued = {}
initialize()
queued = {}   -- the polls it starts; the test calls their bodies itself

local function upvalue(fn, name)
    for i = 1, 200 do
        local key, value = debug.getupvalue(fn, i)
        if not key then break end
        if key == name then return value, i end
    end
    error("missing upvalue " .. name)
end
local function setUpvalue(fn, name, value)
    local _, i = upvalue(fn, name)
    debug.setupvalue(fn, i, value)
end
local function runQueued()
    for _ = 1, 20 do
        local q = queued
        queued = {}
        if #q == 0 then return end
        for _, fn in ipairs(q) do fn() end
    end
end
local function logged(part)
    for _, m in ipairs(logs) do if m:find(part, 1, true) then return true end end
    return false
end
local function countdowns()
    local n = 0
    for _, c in ipairs(calls) do if c == "StartCountdown" then n = n + 1 end end
    return n
end

local hostPostGame = upvalue(upvalue(initialize, "watchMainMenu"), "hostPostGame")
local postTick = upvalue(upvalue(initialize, "watchPostGame"), "postTick")
local Live = upvalue(hostPostGame, "Live")
local voteOptions = upvalue(hostPostGame, "voteOptions")
local installedMaps = upvalue(voteOptions, "installedMaps")
local startGame = upvalue(upvalue(initialize, "AUTO").host, "startGame")
local function post() return (upvalue(postTick, "Post")) end

-- The screens are the game's: an opened lobby or post-game screen is a
-- stand-in that records what the lobby says on it.
local lobbyStatus, lobbies, postScreens = nil, 0, 0
local fakeLobby = { IsValid = function() return true end, IsActivated = function() return true end,
    Status = { SetText = function(_, t) lobbyStatus = t end } }
setUpvalue(hostPostGame, "openLobby", function()
    lobbies = lobbies + 1
    setUpvalue(postTick, "Lobby", fakeLobby)
end)
setUpvalue(hostPostGame, "openPostGame", function()
    postScreens = postScreens + 1
    local p = post()
    p.screen = { IsValid = function() return true end, IsActivated = function() return true end }
    return p.screen
end)
setUpvalue(postTick, "drawPostGame", function() end)

-- The pause menu's SAVE AND EXIT ends in EndCampaign (traced in game); a
-- LeaveGame from script is the same leave.
local QUIT_HOOK = "/Script/BlamEngine.BlamCampaignFlowGameSubsystem:EndCampaign"
local LEAVE_HOOK = "/Script/BlamEngine.BlamCampaignFlowGameSubsystem:LeaveGame"
eq(type(hooks[QUIT_HOOK]), "function", "SAVE AND EXIT (EndCampaign) is hooked")
eq(type(hooks[LEAVE_HOOK]), "function", "LeaveGame is hooked")
local resultsAt = os.time() - 1
local function standings(code, variant, endedAt)
    results = table.concat({ "match", code, variant, "Blood Gulch", "Slayer", "devnull", tostring(endedAt), "-" }, "\t")
        .. "\nplayer\tdevnull\t3\t3\t0\t-\t1\n"
end
local function reset()
    setUpvalue(postTick, "Post", nil)
    setUpvalue(postTick, "Lobby", nil)
    calls, sent, pushed, queued = {}, {}, {}, {}
    lobbies, postScreens, lobbyStatus = 0, 0, nil
end

-------------------------------------------------------------------------------
-- 1. A real end votes and starts; the host's Quit opens the lobby
-------------------------------------------------------------------------------

reset()
UI.startupReady()   -- the main menu has been up: hosting is allowed
standings("BGL", "slayer", resultsAt)
hostPostGame()
eq(postScreens, 1, "a round end opens the post-game screen")
eq(lobbies, 0, "and not the lobby")
local v = post() and post().vote
eq(v ~= nil and #v.options > 0, true, "with a vote")
eq(v.options[1].code, "BGL", "the game just played first")
-- Nobody votes: the time runs out and the host starts the rotation's pick.
v.endsAt = os.clock() - 1
postTick()
eq(v.chosen, 2, "no ballots: the second option")
runQueued()
eq(countdowns(), 1, "the chosen game starts")
eq(sent[#sent][1], "starting", "and the fireteam is told")

-- The host quits a match from the pause menu: LeaveGame, then the standings.
reset()
worldName = "BGL"
hooks[QUIT_HOOK]()
eq(Live.quitAt ~= nil, true, "a host's Quit is remembered")
worldName = "Frontend"
resultsAt = resultsAt + 1
standings("BGL", "slayer", resultsAt)
hostPostGame()
eq(lobbies, 1, "after the host's Quit: the lobby")
eq(postScreens, 0, "no post-game screen")
eq(post(), nil, "no vote")
for _ = 1, 100 do postTick() end
runQueued()
eq(countdowns(), 0, "and nothing starts")
eq(Live.quitAt, nil, "the quit is used up")
eq(logged("the host quit the match"), true, "logged")

-- LeaveGame, the same leave from script, counts too.
reset()
worldName = "BGL"
hooks[LEAVE_HOOK]()
worldName = "Frontend"
resultsAt = resultsAt + 1
standings("BGL", "slayer", resultsAt)
hostPostGame()
eq(lobbies, 1, "after LeaveGame: the lobby")
eq(postScreens, 0, "no vote after LeaveGame")

-- A leave, then a new game at once: that game's own end still votes.
reset()
worldName = "BGL"
hooks[QUIT_HOOK]()
worldName = "Frontend"
upvalue(initialize, "AUTO").host({ "PRS", "slayer", "private" })
eq(Live.quitAt, nil, "starting a game forgets an earlier leave")
resultsAt = resultsAt + 1
standings("PRS", "slayer", resultsAt)
hostPostGame()
eq(postScreens, 1, "the new game's end votes")

-- A client's leave is not the host's quit.
reset()
host, worldName = false, "BGL"
hooks[QUIT_HOOK]()
eq(Live.quitAt, nil, "a client's Quit is not the host's")
host = true
hooks[QUIT_HOOK]()   -- in a match: remembered...
worldName = "Frontend"
Live.quitAt = os.time() - 120   -- ...but long before these standings
resultsAt = resultsAt + 1
standings("BGL", "slayer", resultsAt)
hostPostGame()
eq(postScreens, 1, "standings long after a quit vote as usual")
eq(Live.quitAt, nil, "and use the stale quit up")
reset()
hooks[QUIT_HOOK]()   -- in the frontend: nothing to quit
eq(Live.quitAt, nil, "LeaveGame in the frontend is no quit")
-- A Quit while the final standings are up (they come first) is a quit.
Live.quitAt = os.time()
resultsAt = os.time() - 6
standings("BGL", "slayer", resultsAt)
hostPostGame()
eq(lobbies, 1, "a Quit during the final standings: the lobby")
eq(postScreens, 0, "no vote")
-- However long the finished match was held (in game: a round over on a
-- one-minute limit, held with hold_match.txt, then SAVE AND EXIT 12 s later).
reset()
Live.quitAt = os.time()
resultsAt = os.time() - 60
standings("BGL", "slayer", resultsAt)
hostPostGame()
eq(lobbies, 1, "standings from well before the quit: still the lobby")
eq(postScreens, 0, "still no vote")

-------------------------------------------------------------------------------
-- 2. A map whose world is in no container
-------------------------------------------------------------------------------

local function codes(maps)
    local out = {}
    for _, m in ipairs(maps) do out[#out + 1] = m.code end
    return table.concat(out, ",")
end
worlds = nil
eq(codes(installedMaps()), "BGL,PRS,DCN,ZZT", "when the native half cannot say, every listed map")
worlds = { BGL = true, PRS = true, DCN = true, ZZT = false }
eq(codes(installedMaps()), "BGL,PRS,DCN", "a map with no world is not installed")
worlds.DCN = nil
eq(codes(installedMaps()), "BGL,PRS,DCN", "an unknown answer keeps the map")
worlds.DCN = true
for _ = 1, 50 do
    for _, o in ipairs(voteOptions({ code = "BGL", variant = "slayer" })) do
        eq(o.code ~= "ZZT", true, "the vote never offers a map with no world")
    end
end
-- Even a vote after a match on it: the "again" option is not offered either.
for _, o in ipairs(voteOptions({ code = "ZZT", variant = "slayer" })) do
    eq(o.code ~= "ZZT", true, "nor again")
end
-- A start whose world is missing fails with a reason, before any countdown.
reset()
local ok, why = startGame({ code = "ZZT", title = "Ivory Tower" }, { id = "slayer", slot = 0 })
eq(ok, false, "a start with no world fails")
has(why, "IVORY TOWER is not installed on this PC", "and says why")
eq(countdowns(), 0, "no countdown")
eq(#sent, 0, "the fireteam is not told to start")

-- A vote whose game is no longer there: everyone goes back to the lobby.
reset()
resultsAt = os.time() + 5
standings("BGL", "slayer", resultsAt)
hostPostGame()
v = post().vote
v.options = { { code = "BGL", mode = "slayer", again = true }, { code = "ZZT", mode = "slayer" } }
v.endsAt = os.clock() - 1
postTick()   -- decides: ZZT is not installed
postTick()   -- and the post-game ends
eq(lobbies, 1, "a chosen game that is not installed: the lobby")
has(lobbyStatus, "Could not start: ZZT is not installed on this PC", "with why on the lobby")
eq(sent[#sent][1], "cancel", "and the fireteam's vote is closed")
eq(countdowns(), 0, "nothing starts")
-- The world goes missing after the vote was made: the start fails, and the
-- fireteam is not left on STARTING THE NEXT GAME either.
reset()
resultsAt = resultsAt + 1
standings("BGL", "slayer", resultsAt)
hostPostGame()
v = post().vote
v.options = { { code = "BGL", mode = "slayer", again = true }, { code = "DCN", mode = "slayer" } }
staleWorld = "DCN"
v.endsAt = os.clock() - 1
postTick()
runQueued()
postTick()
staleWorld = nil
eq(countdowns(), 0, "a start whose world is gone does not count down")
eq(lobbies, 1, "the lobby")
has(lobbyStatus, "Could not start: DANGER CANYON is not installed on this PC", "with the start's reason")
eq(sent[#sent][1], "cancel", "the fireteam's vote is closed")

-------------------------------------------------------------------------------
-- 3. A joiner told why it left
-------------------------------------------------------------------------------

local prompts = {}
Live.prompt = function(code, opts) prompts[#prompts + 1] = { code = code, opts = opts } end
Live.NOTICE_DELAY = 0
reset()
host, worldName, left = false, "Frontend", 0
handlers.starting({ "PTP", "", "slayer" })
eq(left, 1, "a joiner without the host's map leaves")
has(Live.notice and Live.notice.text, "doesn't have that map", "and keeps why")
has(Live.notice.text, "PTP", "naming the map")
Live.showNotice()   -- the frontend seen
Live.showNotice()   -- and the delay over
eq(#prompts, 1, "the map is offered")
eq(prompts[1].code, "PTP", "the host's map")
eq(prompts[1].opts.action, "DOWNLOAD", "to download")
has(prompts[1].opts.reason, "doesn't have that map", "with the reason on the screen")
eq(Live.notice, nil, "shown once")
Live.showNotice()
eq(#prompts, 1, "not again")

-- Another release of the map: the update, and why.
otherRelease.BGL = true
handlers.starting({ "BGL", "release-2", "koth" })
eq(left, 2, "another release: leaves too")
has(Live.notice.text, "another version", "and says so")
Live.showNotice()
Live.showNotice()
eq(prompts[2].opts.action, "UPDATE", "the update is offered")
eq(prompts[2].opts.release, "release-2", "the host's release")
otherRelease.BGL = nil

-- With the host's map and release: nothing happens.
handlers.starting({ "BGL", "", "slayer" })
eq(left, 2, "a joiner with the map stays")
eq(Live.notice, nil, "and has nothing to say")

-- A kick naming a map (the host started without them): the same offer.
handlers.kick({ "You don't have PROVING GROUND, so the host started the game without you.", "PTP" })
eq(left, 3, "the kick leaves the fireteam")
Live.showNotice()
Live.showNotice()
eq(prompts[3].code, "PTP", "the map named is offered")
has(prompts[3].opts.reason, "started the game without you", "with the host's reason")
-- Any other kick: its reason on a notice.
handlers.kick({ "You were kicked by the host.", "" })
Live.showNotice()
Live.showNotice()
eq(#prompts, 3, "no map to offer")
eq(pushed[#pushed] and pushed[#pushed].description, "You were kicked by the host.", "the reason on screen")
-- A kick in a match waits for the frontend.
worldName = "BGL"
handlers.kick({ "You were banned by the host.", "" })
local before = #pushed
Live.showNotice()
eq(#pushed, before, "not in the match")
worldName, worldAddress = "Frontend", worldAddress + 1   -- back on the menu: another world
Live.showNotice()
Live.showNotice()
eq(pushed[#pushed].description, "You were banned by the host.", "on the menu")

-- A kick that arrives on the frontend (the post-game vote is there):
-- the leave loads the frontend again, and a screen pushed into the world
-- before that went with it (one PC, two copies, 2026-11-07). Nothing shows
-- while the old world is up, then the delay counts in the new one.
do
    local fakeLeave = viewModel.LeaveFireteam
    viewModel.LeaveFireteam = function() left = left + 1 end   -- the reload is late
    local shown = #pushed
    handlers.kick({ "You were kicked by the host.", "" })
    Live.showNotice()
    Live.showNotice()
    eq(#pushed, shown, "nothing in the world being left")
    worldAddress = worldAddress + 1                               -- the fresh frontend
    Live.showNotice()
    Live.showNotice()
    eq(#pushed, shown + 1, "the reason in the new world")
    viewModel.LeaveFireteam = fakeLeave
end

-- `mjolnir_auto missing` puts the same notice up on one PC (a host alone
-- hears no `starting`): the same words and the same offer.
host = true
local before_ = #prompts
upvalue(initialize, "AUTO").missing({ "PTP", "slayer" })
has(Live.notice and Live.notice.text, "The host started PTP  /  SLAYER, and this PC doesn't have that map",
    "the verb's notice is the joiner's")
Live.showNotice()
Live.showNotice()
eq(#prompts, before_ + 1, "and offers the map")
eq(prompts[#prompts].code, "PTP", "the map named")

-- The host's own kick of a guest without the map names it.
host = true
local kick = upvalue(Live.removeLacking, "kick")
sent = {}
kick({ name = "Arctic", pc = {} }, "why", "PTP")
eq(sent[1][1], "kick", "a kick message")
eq(sent[1][3], "PTP", "with the map")

-- Between test copies on one PC a joiner whose host left the match by hand
-- follows it into a frontend nobody serves (2026-11-07): it leaves after
-- Live.STRANDED_AFTER with why, and never in a lobby or match that has a
-- host, on its own menu, or before it has been anyone's client. Between two
-- PCs the joiner follows the host into its lobby, so a player's game never
-- watches for it.
do
    eq(Live.STRANDED_WATCH, false, "a player's game (no MJOLNIR_INSTANCE) does not watch")
    do
        local cut = { ConnectionTimeout = 120, InitialConnectTimeout = 20 }
        netDriver = cut
        local frozenStranded = Live.stranded
        Live.stranded = function() return true end
        host, worldName = false, "Frontend"
        Live.watchStranded()
        Live.stranded = frozenStranded
        eq(cut.ConnectionTimeout, 120, "nothing cut on a player's PC")
        eq(Live.notice, nil, "and nothing said")
        netDriver, host = nil, true
    end
    Live.STRANDED_WATCH = true   -- a test copy
    local after = Live.STRANDED_AFTER
    local s = {}
    local function at(t, view) return Live.stranded(s, t, view) end
    eq(at(0, { frontend = true }), false, "starting up: no game state, never a client")
    eq(at(30, { frontend = true }), false, "still nothing to leave")
    eq(at(31, { host = true, frontend = true, players = 1 }), false, "its own menu")
    eq(at(40, { frontend = true }), false, "joining: the host's frontend loading")
    eq(at(70, { frontend = true }), false, "however long, before it was a client")
    eq(at(71, { frontend = true, players = 2 }), false, "in the host's lobby")
    eq(at(80, { frontend = false, players = 2 }), false, "in the match")
    eq(at(90, { frontend = false }), false, "the travel back: not the frontend yet")
    eq(at(91, { frontend = true }), false, "the frontend, before the host's game state")
    eq(at(91 + after - 1, { frontend = true }), false, "a slow host is not gone")
    eq(at(91 + after, { frontend = true, players = 2 }), false, "the lobby after a match")
    eq(at(200, { frontend = true, players = 0 }), false, "an empty game state starts the count")
    eq(at(200 + after, { frontend = true, players = 0 }), true, "and the host has left")
    eq(at(200 + after + 1, { frontend = true }), false, "once")
    eq(at(400, { frontend = true }), false, "not again until it is a client again")
    -- The way out: the game's own CONNECTION LOST, its connection's
    -- timeout cut to a second; the engine's disconnect when that cannot be
    -- done or does nothing. Never the fireteam's leave, whose
    -- CanLeaveFireteam reads through the missing game state.
    local commands = {}
    local findObject = env.StaticFindObject
    env.StaticFindObject = function()
        return { ExecuteConsoleCommand = function(_, _, command) commands[#commands + 1] = command end }
    end
    local before = left
    host, worldName = false, "Frontend"
    Live.watchStranded()   -- no game state in the fakes: never a client yet
    eq(#commands, 0, "nothing to leave on a first look")
    local frozen = Live.stranded
    local function strand()
        Live.stranded = function() return true end
        Live.watchStranded()
        Live.stranded = frozen
    end
    netDriver = { ConnectionTimeout = 120, InitialConnectTimeout = 20 }
    strand()
    eq(netDriver.ConnectionTimeout, Live.FORCED_TIMEOUT, "the connection's timeout cut")
    eq(#commands, 0, "and no disconnect")
    eq(left, before, "not the fireteam's leave")
    has(Live.notice and Live.notice.text, "The host left the match", "with why")
    -- The timeout ends the connection: a fresh frontend, nothing more to do.
    worldAddress = worldAddress + 1
    Live.STRANDED_AFTER = 0
    Live.watchStranded()
    eq(#commands, 0, "a new world: the timeout worked")
    -- It does nothing: the disconnect, once.
    strand()
    Live.watchStranded()
    eq(commands[1], "disconnect", "still that world: the engine's disconnect")
    Live.watchStranded()
    eq(#commands, 1, "only once")
    -- No net driver to reach: the disconnect at once.
    netDriver = nil
    strand()
    eq(commands[2], "disconnect", "no net driver: the disconnect")
    Live.STRANDED_AFTER = after
    Live.STRANDED_WATCH = false
    Live.notice = nil
    env.StaticFindObject = findObject
    host = true
end

-- A client's standings are the host's vote's: a client back on its own menu
-- soon after (its host left mid-match, a kick) opens no vote of its own on
-- them (one did on the match before, over the reason; 2026-11-07).
do
    reset()
    host, worldName = false, "Frontend"
    standings("CHL", "slayer", os.time() - 5)
    hostPostGame()
    eq(postScreens, 0, "a client opens no post-game screen")
    host = true   -- back on its own menu
    hostPostGame()
    eq(postScreens, 0, "nor once its own host, on standings it had as a client")
    eq(lobbies, 0, "and no lobby over the main menu")
    standings("BGL", "slayer", os.time())
    hostPostGame()
    eq(postScreens, 1, "its own match after votes as before")
    reset()
end
print("Lobby after a match: " .. checks .. " checks passed")
