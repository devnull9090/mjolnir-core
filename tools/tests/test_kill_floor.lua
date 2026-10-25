-- Run from the repository root with Lua 5.4, or Python + lupa:
-- python -c "from lupa import LuaRuntime; LuaRuntime(encoding=None).execute(open('tools/tests/test_kill_floor.lua','rb').read())"
--
-- MJOLNIRLevelLoader's kill_floor.lua (#234): which floor a map has, and
-- what counts as below it. Loading the module must not need UE4SS.
local KillFloor = dofile("mods/MJOLNIRLevelLoader/Scripts/kill_floor.lua")

local function eq(actual, expected, label)
    assert(actual == expected, (label or "value") .. ": expected " .. tostring(expected) .. ", got " .. tostring(actual))
end

-- Gephyrophobia's floor lies between its lowest playable spot (the hill under
-- the bridge, -6192) and the canyon floor (-7657).
local gph = KillFloor.floorFor("GPH", nil)
assert(gph and gph < -6192 and gph > -7657, "GPH's floor sits between the hill and the canyon floor")
eq(KillFloor.floorFor("gph", {}), gph, "map codes in any case")

-- A level's own "kill_floor" wins over the table; a map with neither has none.
eq(KillFloor.floorFor("GPH", { kill_floor = -9000 }), -9000, "the level's own floor")
eq(KillFloor.floorFor("BGL", nil), nil, "Blood Gulch has no floor")
eq(KillFloor.floorFor(nil, { kill_floor = -100 }), -100, "a level floor needs no code")
eq(KillFloor.floorFor("BGL", { kill_floor = "x" }), nil, "a non-number is ignored")

-- Below means strictly below; no floor or no height is never below.
eq(KillFloor.below(-7001, -7000), true, "under the floor")
eq(KillFloor.below(-7000, -7000), false, "on the floor")
eq(KillFloor.below(-6192, -7000), false, "the hill under the bridge")
eq(KillFloor.below(-8000, nil), false, "no floor")
eq(KillFloor.below(nil, -7000), false, "no height")

print("test_kill_floor: ok")
