-- Run from the repository root with Lua 5.4, or Python + lupa:
-- python -c "from lupa import LuaRuntime; LuaRuntime(encoding=None).execute(open('tools/tests/test_lifts.lua','rb').read())"
--
-- MJOLNIRLevelLoader's lifts.lua (#235): a Halo 2 phantom in the
-- simulation's units, and the file MJOLNIRLobby's DLL reads. The push itself
-- is the DLL's (native/lobby/test_lifts.c). Loading the module must not need
-- UE4SS.
local Lifts = dofile("mods/MJOLNIRLevelLoader/Scripts/lifts.lua")

local function near(actual, expected, label, tolerance)
    assert(math.abs(actual - expected) <= (tolerance or 1e-4),
        (label or "value") .. ": expected " .. tostring(expected) .. ", got " .. tostring(actual))
end

local WU = 304.8

-- Lockout's lower lift, as tools/level/gen_ce_level.py writes it (planes,
-- marker, pushes in cm): a tube 3.7 m across, 13.7 m tall, tilted 7 degrees.
local tube = {
    asset = "scenarios\\objects\\multi\\lockout\\lockout_lift_tube\\lockout_lift_tube",
    planes = { { 0.0, -0.1217, -0.9926, -4155.7 }, { -1.0, 0.0, 0.0, -640.6 }, { 0.0, 0.9926, -0.1217, 3153.0 },
               { 0.0, -0.9926, 0.1217, -3521.9 }, { 1.0, 0.0, 0.0, 271.8 }, { 0.0, 0.1217, 0.9926, 2784.0 } },
    bounds = { -456.2, -3732.0, -3036.0, 750.0 },
    origin = { -456.2, -3815.3, -3718.9 }, forward = { 0.0, 0.1217, 0.9926 },
    center = { 0, 0 }, axis = { 3048.0, 3048.0 }, direction = { 3048.0, 1219.2 }, negates_gravity = true,
}
-- Midship's power lift: a pill.
local pill = {
    asset = "scenarios\\objects\\multi\\midship\\cov_power_lift\\cov_power_lift",
    pill = { { -3573.1, -519.9, -208.1 }, { -3569.0, -508.1, 1011.1 } }, radius = 152.4,
    bounds = { -3571.1, -514.0, 401.5, 762.0 }, origin = { -3590.3, -495.6, -83.7 },
    forward = { 0.0027, 0.0091, 1.0 }, center = { 0.0, 0.0 }, axis = { 0.0, 0.0 },
    direction = { 5486.4, 1158.2 }, negates_gravity = false,
}

-- Unreal cm to the simulation: wu = cm / 304.8, and the sim's y is -Y.
local s = assert(Lifts.toSim(tube, { 0, 0, 0 }))
near(s.origin[1], -456.2 / WU, "origin x") near(s.origin[2], 3815.3 / WU, "origin y flips")
near(s.origin[3], -3718.9 / WU, "origin z")
near(s.forward[2], -0.1217 / math.sqrt(0.1217 ^ 2 + 0.9926 ^ 2), "forward y flips")
near(s.bounds[4], 750.0 / WU, "bounding radius")
near(s.direction[1], 10, "3048 cm/s^2 is 10 wu/s^2") near(s.direction[2], 4, "1219.2 cm/s is 4 wu/s")
near(s.axis[1], 10, "axis acceleration") near(s.center[1], 0, "no centre pull")
assert(s.negates and s.name == "lockout_lift_tube" and #s.planes == 6)

-- Each plane keeps its side: n.p + d, in cm, is the sim plane's value at the
-- same point times 304.8. Checked on points in, under and beside the tube.
local o, f = tube.origin, tube.forward
local points = { { o[1], o[2] + 100 * f[2], o[3] + 100 * f[3] }, { o[1], o[2], o[3] - 50 }, { o[1] + 300, o[2], o[3] + 100 } }
for _, origin in ipairs({ { 0, 0, 0 }, { 1000, -2000, 50 } }) do
    local moved = assert(Lifts.toSim(tube, origin))
    for _, p in ipairs(points) do
        -- The phantom is relative to the canvas origin; the sim is not.
        local q = { (p[1] + origin[1]) / WU, -(p[2] + origin[2]) / WU, (p[3] + origin[3]) / WU }
        for i, n in ipairs(tube.planes) do
            local m = moved.planes[i]
            near(m[1] * q[1] + m[2] * q[2] + m[3] * q[3] + m[4], (n[1] * p[1] + n[2] * p[2] + n[3] * p[3] + n[4]) / WU,
                "plane " .. i, 1e-6)
        end
    end
end

local sp = assert(Lifts.toSim(pill))
near(sp.pill[1][2], 519.9 / WU, "pill end y flips") near(sp.pill[3], 152.4 / WU, "pill radius")
assert(not sp.negates and not sp.planes)

-- What the DLL can't use is left out, with the reason.
assert(not Lifts.toSim({ origin = { 0, 0, 0 }, forward = { 0, 0, 2 }, bounds = { 0, 0, 0, 1 }, pill = pill.pill, radius = 1 }))
assert(not Lifts.toSim({ origin = { 0, 0, 0 }, forward = { 0, 0, 1 }, bounds = { 0, 0, 0, 1 } }), "no shape")
assert(not Lifts.toSim({ origin = { 0, 0, 0 }, forward = { 0, 0, 1 }, bounds = { 0, 0, 0 / 0, 1 }, pill = pill.pill, radius = 1 }))
local many = { origin = { 0, 0, 0 }, forward = { 0, 0, 1 }, bounds = { 0, 0, 0, 1 }, planes = {} }
for i = 1, Lifts.MAX_PLANES + 1 do many.planes[i] = { 0, 0, 1, -i } end
assert(not Lifts.toSim(many), "more planes than one phantom holds")
local skipped = {}
local _, kept = Lifts.serialize({ tube, many, pill }, nil, function(why) skipped[#skipped + 1] = why end)
assert(kept == 2 and #skipped == 1 and skipped[1] == "too many planes")
local full = {}
for i = 1, Lifts.MAX + 2 do full[i] = pill end
_, kept = Lifts.serialize(full)
assert(kept == Lifts.MAX, "no more phantoms than the DLL holds")

-- Names are plain for the DLL's log.
assert(Lifts.name("a\\b c:d/e f") == "e_f" and Lifts.name(nil) == "lift" and #Lifts.name(string.rep("x", 90)) == 47)

-- The file: the DLL's test reads the same fixture (native/lobby/test_lifts.c).
local text, count = Lifts.serialize({ tube, pill })
assert(count == 2)
assert(text:match("^mjolnir%-lifts 1\nlift lockout_lift_tube 1 %-1%.496719 12%.517388 %-12%.201115 "))
assert(select(2, text:gsub("\nplane ", "")) == 6 and text:match("\nend\n$"))
local fixture = assert(io.open("tools/tests/fixtures/lifts_lockout_midship.txt", "rb"))
local expected = fixture:read("a")
fixture:close()
assert(text == expected:gsub("\r\n", "\n"), "the fixture is what serialize writes:\n" .. text)
assert(Lifts.serialize({}) == Lifts.EMPTY)

print("test_lifts: ok")
