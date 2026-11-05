-- Plain checks for MJOLNIRLevelLoader's vehicle_sounds.lua; run with stock Lua.
package.path = "mods/MJOLNIRLevelLoader/Scripts/?.lua;" .. package.path
local V = require("vehicle_sounds")

local function near(a, b) return math.abs(a - b) < 1e-6 end

-- The Mongoose's engine loop, warthog_engine5.
local idle = { low = 1.0, high = 1.1, natural = 1.1 }
local low = { low = 1.1, high = 1.5, natural = 1.38 }
local high = { low = 1.75, high = 2.3, natural = 2.3 }

assert(V.weight(1.0, idle, true, false) == 1, "parked, the idle range plays")
assert(V.weight(1.0, low, false, false) == 0, "parked, the next range is silent")
assert(V.weight(1.3, low, false, false) == 1, "inside its bounds a range plays whole")
assert(near(V.weight(1.1, idle, true, false), 0.5) and near(V.weight(1.1, low, false, false), 0.5),
    "at a bound two ranges share")
assert(V.weight(2.0, high, false, true) == 1, "the top range plays")
assert(V.weight(3.0, high, false, true) == 1, "past the last bound the last range keeps playing")
assert(V.weight(0.5, idle, true, false) == 1, "under the first bound the first keeps playing")
assert(V.weight(1.0, { low = 0, high = 1, natural = 1 }, true, true) == 1, "a sound with one range always plays it")

assert(near(V.rate(1.1, idle), 1.0), "at its natural pitch a range plays as recorded")
assert(near(V.rate(1.0, idle), 1.0 / 1.1), "below it, slower")
assert(V.rate(1.5, {}) == 1.0, "no natural pitch, no bend")

assert(V.revs(0.25, 0, 2560) == 0.25, "the engine's value when the vehicle stands")
assert(V.revs(nil, 1280, 2560) == 0.5, "no reading: the speed carries it")
assert(V.revs(0.1, 5000, 2560) == 1, "never past full")
assert(V.revs(nil, 100, nil) == 0, "no top speed, nothing to go on")

assert(near(V.bend(0, 1, 0.1), V.RISE * 0.1), "revs climb at their rate")
assert(near(V.bend(1, 0, 0.1), 1 - V.FALL * 0.1), "and fall at theirs")
assert(V.bend(0.5, 0.51, 1) == 0.51, "without passing what they want")
print("ok")
