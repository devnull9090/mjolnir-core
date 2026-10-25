-- Run from the repository root with Lua 5.4, or Python + lupa:
-- python -c "from lupa import LuaRuntime; LuaRuntime(encoding=None).execute(open('tools/tests/test_lifts.lua','rb').read())"
--
-- MJOLNIRLevelLoader's lifts.lua (#235): what is inside a Halo 2 phantom, how
-- it pushes, and the push in a unit's facing frame. Loading the module must
-- not need UE4SS.
local Lifts = dofile("mods/MJOLNIRLevelLoader/Scripts/lifts.lua")

local function near(actual, expected, label, tolerance)
    assert(math.abs(actual - expected) <= (tolerance or 1e-3),
        (label or "value") .. ": expected " .. tostring(expected) .. ", got " .. tostring(actual))
end

-- Lockout's lower lift, as tools/level/gen_ce_level.py writes it (planes,
-- marker, pushes in cm): a tube 3.7 m across, 13.7 m tall, tilted 7 degrees.
local tube = {
    planes = { { 0.0, -0.1217, -0.9926, -4155.7 }, { -1.0, 0.0, 0.0, -640.6 }, { 0.0, 0.9926, -0.1217, 3153.0 },
               { 0.0, -0.9926, 0.1217, -3521.9 }, { 1.0, 0.0, 0.0, 271.8 }, { 0.0, 0.1217, 0.9926, 2784.0 } },
    bounds = { -456.2, -3732.0, -3036.0, 750.0 },
    origin = { -456.2, -3815.3, -3718.9 }, forward = { 0.0, 0.1217, 0.9926 },
    center = { 0, 0 }, axis = { 3048.0, 3048.0 }, direction = { 3048.0, 1219.2 }, negates_gravity = true,
}
local o = tube.origin
assert(Lifts.inside(tube, { o[1], o[2], o[3] + 100 }), "a metre up the tube is inside")
assert(not Lifts.inside(tube, { o[1], o[2], o[3] - 50 }), "under the tube is not")
assert(not Lifts.inside(tube, { o[1] + 300, o[2], o[3] + 100 }), "beside the tube is not")
assert(Lifts.near(tube, { o[1], o[2], o[3] }, 0), "its foot is near")
assert(not Lifts.near(tube, { o[1] + 2000, o[2], o[3] }, 300), "20 m away is not")

-- Standing still on the axis (a metre along the tilted tube): the push goes
-- up the tube, and gravity is held off.
local f0 = tube.forward
local up1 = { o[1] + 100 * f0[1], o[2] + 100 * f0[2], o[3] + 100 * f0[3] }
local v = Lifts.push(tube, up1, { 0, 0, 0 }, 0.05)
near(v[3], 3048.0 * 0.05 * 0.9926, "up", 0.5)
near(v[1], 0, "no sideways push on the axis")
near(Lifts.sent(v, true, 0.05)[3], v[3] + Lifts.GRAVITY * 0.05, "sent with gravity held off", 0.01)
near(Lifts.sent(v, false, 0.05)[3], v[3], "sent as it is", 0.01)
-- Standing on the floor the biped reads still after a push; the speed the
-- last step gave carries on, so the lift gains 152 cm/s a step and leaves
-- the ground.
local first = Lifts.push(tube, up1, { 0, 0, 0 }, 0.05)
local second = Lifts.push(tube, up1, { 0, 0, 0 }, 0.05, first)
near(second[3], first[3] + 3048.0 * 0.05 * 0.9926, "carried", 0.5)
-- And it stops at the top speed: twenty steps from still reach 1219 cm/s
-- along the tube and no more.
local w = { 0, 0, 0 }
for _ = 1, 20 do w = Lifts.push(tube, up1, { 0, 0, 0 }, 0.05, w) end
near(w[2] * tube.forward[2] + w[3] * tube.forward[3], 1219.2, "top speed", 1)
-- At the top speed along the tube nothing more is added.
local top = { 0, 1219.2 * 0.1217, 1219.2 * 0.9926 }
v = Lifts.push(tube, up1, top, 0.05)
near(v[3], top[3], "held at top speed", 0.5)
-- Off the axis, the pull is towards it and slows into it: a metre off
-- after 50 ms it may not pass 1000 cm/s.
v = Lifts.push(tube, { up1[1] + 100, up1[2], up1[3] }, { 0, 0, 0 }, 0.05)
assert(v[1] < 0 and v[1] >= -1000, "pulled back towards the axis: " .. v[1])

-- A pill (Midship's power lift, say): inside within its radius of the
-- segment, ends rounded.
local pill = { pill = { { 0, 0, 0 }, { 0, 0, 1000 } }, radius = 150 }
assert(Lifts.inside(pill, { 100, 0, 500 }), "inside the pill")
assert(Lifts.inside(pill, { 0, 0, 1100 }), "inside the top cap")
assert(not Lifts.inside(pill, { 200, 0, 500 }), "outside the pill")
assert(not Lifts.inside(pill, { 0, 0, -200 }), "under the bottom cap")

-- object_set_velocity's frame: forward along the unit's yaw, left to its
-- left (Unreal's -Y at yaw 0), up; world units per second.
local f, l, u = Lifts.toUnit({ 304.8, 0, 0 }, 0)
near(f, 1, "forward at yaw 0") near(l, 0, "no left") near(u, 0, "no up")
f, l = Lifts.toUnit({ 0, -304.8, 0 }, 0)
near(f, 0, "-Y is not forward") near(l, 1, "-Y is left at yaw 0")
-- PC 2's push "4 0 0" at yaw 110.8 moved it along (-0.35, 0.94).
f, l = Lifts.toUnit({ -0.355 * 1219.2, 0.935 * 1219.2, 0 }, 110.8)
near(f, 4, "forward at yaw 110.8", 0.02) near(l, 0, "and no left", 0.02)
_, _, u = Lifts.toUnit({ 0, 0, 609.6 }, 45)
near(u, 2, "up")

print("test_lifts: ok")
