-- Game-thread dispatch regression: real Forge main.lua, simulated UE4SS
-- queues. No game files, UI objects or native binaries are accessed.
local checks = 0
local function eq(actual, expected)
    checks = checks + 1
    assert(actual == expected, "expected " .. tostring(expected) .. ", got " .. tostring(actual))
end
local now, state = 1, "forge=1\nplayer=0\nediting=1\ncursor=ffffffff\nheld=ffffffff\ntick=0\n"
local queued, async, renders, logs, work = {}, nil, {}, {}, ""
local nativePumps, lightScans, badRender, badLight = 0, 0, false, false
local function queue(delay, callback) queued[#queued + 1] = { delay = delay, callback = callback } end
local function step()
    eq(#queued, 1)
    local item = table.remove(queued, 1)
    now = now + item.delay / 1000
    item.callback()
    return item.callback
end
local Hud = {
    init = function() end, setPackInventory = function() end,
    layoutWarning = function() return nil end,
    parsePalette = function() return {} end,
    render = function(s)
        now = now + 0.002
        if badRender then error("transient widget failure") end
        renders[#renders + 1] = s
        return true
    end,
}
local Lights = { setInventory = function() end, tick = function()
    lightScans = lightScans + 1
    now = now + 0.003
    if badLight then error("transient lamp failure") end
end }
local env
env = setmetatable({
    Key = setmetatable({}, { __index = function(_, name) return name end }),
    os = { clock = function() return now end },
    print = function(message) logs[#logs + 1] = message end,
    io = { open = function(path)
        local text
        if path:match("forge_state%.txt$") then text = state end
        if path:match("running%.txt$") then text = "FRB\tforge\tCrossline" end
        if text then return { read = function() return text end, close = function() end } end
    end },
    RegisterKeyBind = function() end,
    ExecuteInGameThread = function() error("recurring work allocated an anonymous game-thread callback") end,
    ExecuteInGameThreadWithDelay = queue,
    LoopAsync = function(_, callback) async = callback end,
    ModRef = {
        GetSharedVariable = function() return work end,
        SetSharedVariable = function(_, _, value) work = value end,
    },
    package = { loadlib = function(_, name)
        return function() if name == "mjolnir_forge_pump" then nativePumps = nativePumps + 1 end end
    end },
    dofile = function(path)
        if path:match("hud%.lua$") then return Hud end
        if path:match("class_lifetime%.lua$") then return { new = function() return function() end end } end
        if path:match("lights%.lua$") then return { new = function() return Lights end } end
        if path:match("materials%.lua$") then return { new = function() return { setInventory = function() end, tick = function() end } end } end
        error("optional JSON module absent in fixture")
    end,
}, { __index = _G })
-- reportWork uses rawget(_G), as it does in the real mod's Lua environment.
env._G = env
assert(loadfile("mods/MJOLNIRForge/Scripts/main.lua", "t", env))()
eq(queued[1].delay, 5000)
step() -- startup arms exactly one persistent callback and one asynchronous poll
eq(type(async), "function")
eq(queued[1].delay, 100)
local persistent = queued[1].callback

-- Simulate a blocked game thread while native input/state keeps advancing.
-- Updates coalesce to the newest snapshot and at most one pending lamp scan.
for i = 1, 1000 do
    state = "forge=1\nplayer=0\nediting=1\ncursor=" .. i .. "\ncursor_tag=object_" .. i .. "\ntick=" .. i .. "\n"
    eq(async(), false)
    eq(#queued, 1)
end
eq(nativePumps, 1000)
eq(#renders, 0)
eq(lightScans, 0)
eq(step(), persistent)
eq(#renders, 1)
eq(renders[1].cursor_tag, "object_1000")
eq(lightScans, 1)
eq(queued[1].callback, persistent)
eq(work:find("Forge|HUD|2;", 1, true) ~= nil, true)
eq(work:find("Forge|pack lights|3;", 1, true) ~= nil, true)

-- An unchanged snapshot does not redraw each game-thread tick. Later
-- snapshots use the same callback identity even after Lua garbage collection.
for _ = 1, 40 do
    step()
    collectgarbage("collect")
    eq(queued[1].callback, persistent)
end
eq(#renders, 1)
eq(lightScans, 1)
for i = 1001, 1200 do
    state = "forge=1\nplayer=0\nediting=1\ncursor=ffffffff\ntick=" .. i .. "\n"
    async()
    eq(step(), persistent)
end
eq(#renders, 201)
eq(renders[#renders].cursor_tag, nil)
eq(lightScans, 41)

-- One bad widget cannot remove the repeating game-thread callback or lose
-- its latest update. It retries without a new file and logs only once.
badRender = true
state = state .. "grid_m=1\n"
async()
local before = #renders
local beforeLogs = #logs
step(); step()
eq(#renders, before)
eq(#logs, beforeLogs + 1)
eq(queued[1].callback, persistent)
badRender = false
step()
eq(#renders, before + 1)
eq(renders[#renders].grid_m, "1")

-- The next native snapshot supersedes a failed render; lamp errors are
-- isolated as well and retry on their normal bounded cadence.
badRender, badLight = true, true
state = state .. "rotation_snap=45\n"
for _ = 1, 5 do async() end
step()
badRender = false
state = "forge=1\nplayer=0\nediting=1\ncursor=ffffffff\ngrid_m=2\nrotation_snap=15\n"
async(); step()
eq(renders[#renders].grid_m, "2")
eq(renders[#renders].rotation_snap, "15")
badLight = false
local oldScans = lightScans
for _ = 1, 5 do async() end
step()
eq(lightScans, oldScans + 1)
eq(queued[1].callback, persistent)
eq(#queued, 1)
print("Forge game-thread dispatch: " .. checks .. " checks passed")
