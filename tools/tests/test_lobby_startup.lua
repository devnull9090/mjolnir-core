-- Exercise the real host entry points without a game, network or filesystem.
-- Existing controller/helpers at the title screen must not be enough to host.
local checks = 0
local function eq(actual, expected, label)
    checks = checks + 1
    assert(actual == expected, (label or "value") .. ": expected " .. tostring(expected) .. ", got " .. tostring(actual))
end
local widgets, queued, writes, calls = {}, {}, {}, {}
local worldName = "Frontend"
local function widget(visible, active)
    return { IsValid = function() return true end, IsVisible = function() return visible end,
        IsActivated = function() return active end }
end
local pc = { IsValid = function() return true end,
    GetWorld = function() return { GetFName = function() return { ToString = function() return worldName end } end } end,
    PlayerState = { GetPlayerName = function() return { ToString = function() return "Signed-in hub name" end } end } }
local UI = {
    log = function() end,
    valid = function(o) return type(o) == "table" and o.IsValid and o:IsValid() end,
    playerController = function() return pc end,
    liveWidget = function(name, predicate)
        local w = widgets[name]
        return w and predicate(w) and w or nil
    end,
}
local setup = widget(true, true)
local helpers = setmetatable({ IsValid = function() return true end,
    GetCampaignSetup = function(_, _, _, out) calls[#calls+1] = "setup"; out.CampaignSetup = setup end,
}, { __index = function(_, key) return function() calls[#calls+1] = key end end })
-- The real game types, with the one write that reaches the disk kept here.
local Modes = dofile("mods/MJOLNIRLobby/Scripts/modes.lua")
Modes.writeChoice = function(_, code, id) writes.match_variant = code .. " " .. id end
local modules = {
    ui = UI,
    modes = Modes,
    presence = { init = function() end },
    class_lifetime = { new = function() return function() end end },
    gametype = { new = function() return {} end },
    postgame = { new = function() return {} end },
    games = {
        setPublic = function(on) calls[#calls+1] = "public:" .. tostring(on) end,
        isPublic = function() return false end, status = function() return "" end,
        changed = function() calls[#calls+1] = "changed" end,
        hosting = function(on) calls[#calls+1] = "hosting:" .. tostring(on) end,
    },
    -- No world index here (MapLive.worlds returns nil: "cannot say").
    maplive = { register = function() calls[#calls+1] = "register"; return true end, release = function() return {} end,
        worlds = function() return nil end },
    settings = { variantLine = function() return "" end },
    net = { on = function() end, toClients = function() calls[#calls+1] = "starting message" end },
    json = { encode = function() return "{}" end },
}
local env = setmetatable({
    print = function() end,
    dofile = function(path)
        local name = assert(path:match("([^\\]+)%.lua$"))
        modules[name] = modules[name] or {}
        return modules[name]
    end,
    io = { open = function(path, mode)
        if mode:find("r", 1, true) then return nil end
        writes[path] = ""
        return { write = function(_, ...) for _, v in ipairs({...}) do writes[path] = writes[path] .. tostring(v) end end,
            close = function() end }
    end },
    StaticFindObject = function(path)
        calls[#calls+1] = "lookup"
        return path:find("CampaignMenuHelpers", 1, true) and helpers or setup
    end,
    FindFirstOf = function() return nil end,
    FName = function(s) return s end,
    ExecuteInGameThreadWithDelay = function(_, callback) queued[#queued+1] = callback end,
}, { __index = _G })
assert(loadfile("mods/MJOLNIRLobby/Scripts/main.lua", "t", env))()
eq(#queued, 1, "one deferred initializer")
local function upvalue(fn, name, replace)
    for i=1,100 do
        local key, value = debug.getupvalue(fn, i)
        if not key then break end
        if key == name then
            if replace ~= nil then debug.setupvalue(fn, i, replace) end
            return value
        end
    end
    error("missing upvalue " .. name)
end
local auto = upvalue(queued[1], "AUTO")
local startGame = upvalue(auto.host, "startGame")
local map, mode = { code = "FRB", title = "Crossline" }, { id = "forge", slot = 5, forge = true }
upvalue(auto.host, "mapByCode", function() return map end)
upvalue(auto.host, "modeById", function() return mode end)
-- Roster construction is independent of startup; the fixture has one player.
local autoState = upvalue(auto.host, "autoState")
upvalue(autoState, "rosterPlayers", function() return {pc} end)
local function state()
    for path, value in pairs(writes) do if path:match("auto_state%.txt$") then return value end end
    return ""
end
local function resetEffects() calls, writes = {}, {} end
local function refused(label)
    resetEffects()
    auto.host({"FRB", "forge", "private"})
    eq(#calls, 0, label .. " has no engine/publication calls")
    eq(state():find("result=error finish the title-screen sign-in", 1, true) ~= nil, true, label .. " actionable error")
    eq(state():find("signed_in=0", 1, true) ~= nil, true, label .. " not ready")
    for path in pairs(writes) do eq(path:match("auto_state%.txt$") ~= nil, true, label .. " only writes response") end
    resetEffects()
    local ok, why = startGame(map, mode)
    eq(ok, false, label .. " also blocks direct/menu start")
    eq(why:find("main menu", 1, true) ~= nil, true)
    eq(#calls, 0)
    eq(next(writes), nil)
end

widgets.WBP_TitleMenu_C = widget(true, true)
refused("fresh title")
-- Identity/player-controller existence must not bypass the stock login spinner.
widgets.WBP_TitleMenu_C = widget(false, false)
refused("login pending")
-- A black world reached by an older premature host must not fabricate sign-in.
worldName = "RWC"
refused("degraded world")
worldName = "Frontend"
widgets.WBP_MainMenu_C = widget(true, true)
eq(UI.startupReady(), true, "stock main menu establishes readiness")
resetEffects()
auto.host({"FRB", "forge", "private"})
eq(state():find("result=hosting FRB forge private", 1, true) ~= nil, true, "ready host succeeds")
eq(state():find("signed_in=1", 1, true) ~= nil, true)
local countdowns = 0
for _, call in ipairs(calls) do if call == "StartCountdown" then countdowns = countdowns + 1 end end
eq(countdowns, 1, "one native countdown")
-- FORGE is never public: a host alone leaves its lobby as shipped.
local hosting
for _, call in ipairs(calls) do hosting = call:match("^hosting:(%a+)") or hosting end
eq(hosting, "false", "FORGE start keeps the shipped solo branch")
-- Our lobby overlays and post-game voting may hide/destroy the stock menu.
widgets.WBP_MainMenu_C = nil
eq(UI.startupReady(), true, "lobby overlay retains readiness")
worldName = "FRB"
resetEffects()
eq(startGame(map, mode), true, "post-game start remains supported")
-- Logout/title reactivation wins even if an old main-menu widget remains.
worldName = "Frontend"
widgets.WBP_MainMenu_C = widget(true, true)
widgets.WBP_TitleMenu_C = widget(true, true)
refused("returned title")
widgets.WBP_MainMenu_C = nil
widgets.WBP_TitleMenu_C = widget(false, false)
refused("second login pending")
print("Lobby startup readiness: " .. checks .. " checks passed")
