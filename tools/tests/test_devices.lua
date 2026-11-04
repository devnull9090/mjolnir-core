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
print("ok")
