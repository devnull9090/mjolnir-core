-- Plain checks for MJOLNIRLevelLoader's devices.lua; run with stock Lua.
package.path = "mods/MJOLNIRLevelLoader/Scripts/?.lua;" .. package.path
local Devices = require("devices")

local at = Devices.shifted({ X = 10, Y = 20, Z = 30 }, { X = 1, Y = 2, Z = -500 }, { X = 1, Y = 2, Z = 3 })
assert(at.X == 10 and at.Y == 20 and at.Z == -473, "a mesh moves by its part's offset from its actor")

assert(Devices.near({ X = 0, Y = 0, Z = 0 }, { X = 10, Y = 5, Z = 5 }), "a device stands where it was placed")
assert(not Devices.near({ X = 0, Y = 0, Z = 0 }, { X = 40, Y = 0, Z = 0 }), "another device is not this one")

assert(Devices.shows(false, 1.0), "a shield at home shows")
assert(not Devices.shows(false, 0.0), "a parked shield does not")
assert(not Devices.shows(true, 0.583), "the game stopped updating a hidden shield mid-move: it is parking")
assert(Devices.distance({ X = 0, Y = 0, Z = 0 }, { X = 1, Y = -2, Z = 3 }) == 6)
-- Scans for an unbound device back off: one that never binds was a 25 ms
-- FindAllOf every 2 s for a whole match.
assert(Devices.nextWait(Devices.SCAN_S, false) == 2 * Devices.SCAN_S, "a scan that binds nothing waits twice as long")
assert(Devices.nextWait(Devices.SCAN_MAX_S, false) == Devices.SCAN_MAX_S, "the wait stops growing")
assert(Devices.nextWait(32, true) == Devices.SCAN_S, "a scan that binds one looks again soon")
local wait, total = Devices.SCAN_S, 0
for _ = 1, Devices.SCAN_TRIES do total, wait = total + wait, Devices.nextWait(wait, false) end
assert(total > 120 and total < 600, "a device that never binds is looked for for minutes, not a whole match")

-- The tick, with a level whose one device never binds: scans stop.
local scans, logged = 0, {}
_G.FindAllOf = function() scans = scans + 1; return {} end
_G.StaticFindObject = function() return { IsValid = function() return true end } end
local clock = 1000
local realTime = os.time
os.time = function() return clock end
Devices.init({ Log = function(line) logged[#logged + 1] = line end,
    Current = { actors = {}, level = { devices = { { name = "gate", class = "BP_Gate_C", pos = { 0, 0, 0 }, decor = {} } } } } })
for _ = 1, 4000 do
    Devices.tick()
    clock = clock + 0.25
end
os.time = realTime
assert(scans == Devices.SCAN_TRIES, "scans stop after SCAN_TRIES that bind nothing, got " .. scans)
assert(#logged == 1 and logged[1]:find("gate", 1, true), "the device that never bound is named once")

print("ok")
