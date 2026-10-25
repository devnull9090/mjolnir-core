-- Run from the repository root with Lua 5.4, or Python + lupa:
-- python -c "from lupa import LuaRuntime; LuaRuntime().execute(open('tools/tests/test_outdated.lua').read())"
--
-- Drives MJOLNIRLobby's outdated.lua (the out-of-date prompt at the main
-- menu) against a stand-in native half and screen kit: when it asks the
-- launcher, what it shows for an answer, and that it shows once a visit.
local function eq(actual, expected, label)
    assert(actual == expected, (label or "value") .. ": expected " .. tostring(expected) .. ", got " .. tostring(actual))
end

local dir = os.getenv("TEMP") or os.getenv("TMPDIR") or "/tmp"
local native = dir .. "/mjolnir-outdated-test/"
os.execute((package.config:sub(1, 1) == "\\" and "mkdir \"" .. native:gsub("/", "\\") .. "\" 2>nul" or "mkdir -p " .. native))

local function write(name, text)
    local f = assert(io.open(native .. name, "wb"))
    f:write(text)
    f:close()
end
local function read(name)
    local f = io.open(native .. name, "rb")
    if not f then return nil end
    local t = f:read("*a")
    f:close()
    return t
end
os.remove(native .. "update_check.json")

-- The native half: records each request, answers ok.
local requests = {}
package.loadlib = function(_, name)
    assert(name == "mjolnir_launcher", "unexpected export " .. tostring(name))
    return function()
        requests[#requests + 1] = (read("launcher_request.txt") or ""):match("%S+")
        write("launcher_reply.txt", "ok\n")
    end
end

local pushed = {}
local UI = {
    valid = function(o) return o ~= nil and o ~= false end,
    push = function(spec)
        local rec = { spec = spec, screen = { live = true } }
        pushed[#pushed + 1] = rec
        return rec
    end,
    describe = function(rec, text) rec.spec.description = text end,
    pop = function(rec) rec.screen = nil end,
    playerController = function() return nil end,
}
local delayed = {}
ExecuteInGameThreadWithDelay = function(_, fn) delayed[#delayed + 1] = fn end
StaticFindObject = function() return nil end

local Json = dofile("mods/MJOLNIRLobby/Scripts/json.lua")
local Outdated = dofile("mods/MJOLNIRLobby/Scripts/outdated.lua")
local logs = {}
Outdated.init({ json = Json, ui = UI, log = function(m) logs[#logs + 1] = m end, nativeDir = native })

-- Pure parts first.
eq(Outdated.findings({ items = {}, unsupported = {} }), nil, "nothing found")
eq(Outdated.findings(nil), nil, "no result")
eq(Outdated.arrived(100, nil), true, "first tick is an arrival")
eq(Outdated.arrived(101.5, 100), false, "the next poll is not")
eq(Outdated.arrived(200, 100), true, "back after a match is")
eq(Outdated.itemLine({ kind = "code", name = "MJOLNIRLobby", installed = "0.14.0", latest = "0.15.0" }),
    "MJOLNIRLobby (mod)   0.14.0 > 0.15.0", "code mod line")
eq(Outdated.itemLine({ kind = "content", name = "Blood Gulch", installed = Json.null, latest = "1.1.0" }),
    "Blood Gulch (hub)   ? > 1.1.0", "no installed version")
eq(Outdated.itemLine({ kind = "content", name = "Wizard", latest = "1.0.0", repair = true }),
    "Wizard   (FILES MISSING)", "repair line")

local many = { items = {}, unsupported = { { kind = "pak", name = "z_Mod_P" } } }
for i = 1, 8 do many.items[i] = { kind = "content", name = "Map " .. i, installed = "1.0.0", latest = "1.1.0" } end
local title, text = Outdated.describe(Outdated.findings(many))
eq(title, "UPDATE AVAILABLE", "title with updates")
assert(text:find("and 2 more", 1, true), "lists six and counts the rest")
assert(text:find("1 mod MJOLNIR did not install is", 1, true), "mentions the unsupported mod")
title = Outdated.describe(Outdated.findings({ items = {}, unsupported = many.unsupported }))
eq(title, "UNSUPPORTED MODS", "title with only unsupported mods")

-- At the main menu: the first tick asks, the answer shows once.
local menu = { IsActivated = function() return true end }
Outdated.tick(menu)
eq(#requests, 1, "the first visit asks the launcher")
eq(requests[1], "check", "for a check")
eq(#pushed, 0, "nothing to show before the answer")

write("update_check.json", '{"checked_at":1,"items":[{"kind":"code","id":"MJOLNIRLobby","name":"MJOLNIRLobby",'
    .. '"installed":"0.14.0","latest":"0.15.0","release_id":null,"repair":false}],"unreachable":[],"unsupported":[]}')
Outdated.tick(menu)
eq(#pushed, 1, "the answer shows")
eq(pushed[1].spec.title, "UPDATE AVAILABLE", "titled")
eq(pushed[1].spec.buttons[1].label, "UPDATE AND RESTART", "first button")

-- Not again on this visit, even once dismissed.
pushed[1].spec.buttons[2].onClick()
Outdated.tick(menu)
Outdated.tick(menu)
eq(#pushed, 1, "once a visit")
eq(#requests, 1, "no new check on the same visit")

-- Covered by another screen: waits until the menu is on top again.
local covered = { IsActivated = function() return false end }
-- A new visit (back from a match), with a fresh answer still in hand.
local realTime = os.time
os.time = function() return realTime() + 60 end
Outdated.tick(covered)
eq(#requests, 1, "a recent answer is reused")
eq(#pushed, 1, "not over another screen")
Outdated.tick(menu)
eq(#pushed, 2, "shown again on the next visit")

-- UPDATE AND RESTART asks the launcher to update and quits after a moment.
pushed[2].spec.buttons[1].onClick()
eq(requests[#requests], "update", "asks for the update")
eq(#delayed, 1, "the quit is scheduled")
assert(pushed[2].spec.description:find("Opening the MJOLNIR launcher", 1, true), "says what happens")

-- Much later: asks again.
os.time = function() return realTime() + 1000 end
os.remove(native .. "update_check.json")
Outdated.tick(menu)
eq(requests[#requests], "check", "a stale answer is asked for again")
os.time = realTime

print("test_outdated: ok")
