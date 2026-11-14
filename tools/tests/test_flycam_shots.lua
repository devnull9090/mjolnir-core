-- Run from the repository root: lua tools/tests/test_flycam_shots.lua
local Json = dofile("mods/MJOLNIRFlyCam/Scripts/json.lua")
local Shots = dofile("mods/MJOLNIRFlyCam/Scripts/shots.lua").init(Json)
local Flight = dofile("mods/MJOLNIRFlyCam/Scripts/flight.lua")
local function near(a, b, eps) assert(math.abs(a - b) < (eps or 1e-6), tostring(a) .. " ~= " .. tostring(b)) end

local pose = { x = 1200.5, y = -340, z = 2210.25, pitch = -18.2, yaw = 45, roll = 0, fov = 78 }

-- Empty and blank files are an empty list; a broken file is refused.
assert(#Shots.decode(nil, "ZAN").shots == 0)
assert(#Shots.decode("  \n", "ZAN").shots == 0)
assert(not Shots.decode("{", "ZAN"))
assert(not Shots.decode('{"shots": [{"n": 1}]}', "ZAN"))
assert(not Shots.decode('{"shots": [{"n": 1, "x":0,"y":0,"z":0,"pitch":0,"yaw":0,"roll":0,"fov":70},'
    .. '{"n": 1, "x":0,"y":0,"z":0,"pitch":0,"yaw":0,"roll":0,"fov":70}]}', "ZAN"))

-- Numbers: lowest free, stable across deletes; names find and replace.
local data = Shots.empty("ZAN")
assert(Shots.put(data, pose).n == 1)
assert(Shots.put(data, pose, nil, "overview").n == 2)
assert(Shots.put(data, pose, 10).n == 10)
assert(Shots.remove(data, "1").n == 1)
assert(Shots.put(data, pose).n == 1)
assert(Shots.find(data, "overview").n == 2)
local moved = { x = 1, y = 2, z = 3, pitch = 4, yaw = 5, roll = 0, fov = 60 }
assert(Shots.put(data, moved, nil, "overview").n == 2)          -- same name replaces
assert(Shots.find(data, "2").x == 1)
assert(Shots.put(data, pose, 2).name == "overview")              -- renumbered save keeps its name
assert(not Shots.put(data, pose, 3, "overview"))                 -- names are unique
assert(not Shots.put(data, pose, 100))
assert(not Shots.put(data, pose, 4, "two words"))
assert(not Shots.put(data, { x = 0, y = 0, z = 0, pitch = 0, yaw = 0, roll = 0, fov = 200 }, 4))
assert(not Shots.find(data, "missing"))

-- Round trip, sorted by number, exact to 4 decimals.
local text = Shots.encode(data)
local back = assert(Shots.decode(text, "ZAN"))
assert(#back.shots == #data.shots)
for i, s in ipairs(back.shots) do
    local o = data.shots[i]
    assert(s.n == o.n and s.name == o.name)
    for _, k in ipairs({ "x", "y", "z", "pitch", "yaw", "roll", "fov" }) do near(s[k], o[k], 1e-4) end
end
assert(back.shots[1].n == 1 and back.shots[#back.shots].n == 10)
assert(text:find('"map": "ZAN"', 1, true))
assert(Shots.encode(back) == text)                                -- stable: re-saving changes nothing
assert(Shots.decode(Shots.encode(Shots.empty("ZAN")), "ZAN"))

-- Every number 1..99 used: no free slot.
local full = Shots.empty("X")
for n = 1, Shots.MAX do assert(Shots.put(full, pose, n)) end
assert(not Shots.put(full, pose))

assert(Shots.validMap("ZAN") and Shots.validMap("h2_zanzibar") and not Shots.validMap("../x"))

-- Flight: eases toward the target speed, stops, flies along the view.
local state = Flight.new()
local rot = { Pitch = 0, Yaw = 90, Roll = 0 }
local total = 0
for _ = 1, 600 do total = total + Flight.step(state, rot, { fwd = 1 }, 750, 1 / 60).Y end
near(total, 750 * 10, 120)                                         -- ~10 s at 750 cm/s, minus the ease-in
near(state.vel.X, 0, 1e-6)
for _ = 1, 120 do Flight.step(state, rot, {}, 750, 1 / 60) end
assert(state.vel.X == 0 and state.vel.Y == 0)                      -- comes to rest
local up = Flight.offset({ Pitch = 90, Yaw = 0, Roll = 0 }, 100, 0, 0)
near(up.Z, 100)
local diag = Flight.step(Flight.new(), { Pitch = 0, Yaw = 0, Roll = 0 }, { fwd = 1, right = 1 }, 100, 100)
near(math.sqrt(diag.X ^ 2 + diag.Y ^ 2), 100 * 100, 1e-3)         -- diagonals are not faster
local r = Flight.normalizeRot({ Pitch = 120, Yaw = 190, Roll = 0 })
assert(r.Pitch == 89); near(r.Yaw, -170)
assert(Flight.clampFov(1) == 5 and Flight.clampFov(500) == 170)

print("test_flycam_shots: ok")
