-- MJOLNIRLevelLoader's vehicle_sounds.lua against a stand-in for the game: a
-- seat taken and left, the horn held, the vehicle gone. Run with stock Lua.
package.path = "mods/MJOLNIRLevelLoader/Scripts/?.lua;" .. package.path

local spawned, watched = {}, nil
local function comp(wave, autoDestroy)
    local c = { wave = wave, autoDestroy = autoDestroy, valid = true, playing = true, volume = nil, pitch = nil, moved = 0 }
    function c.IsValid(self) return self.valid end
    function c.K2_SetWorldLocation(self) self.moved = self.moved + 1 end
    function c.SetVolumeMultiplier(self, v) self.volume = v end
    function c.SetPitchMultiplier(self, v) self.pitch = v end
    function c.FadeIn(self) self.playing = true end
    function c.FadeOut(self) self.playing = false end
    function c.Stop(self) self.playing = false end
    spawned[#spawned + 1] = c
    return c
end

function NotifyOnNewObject(path, callback) watched = callback end -- luacheck: ignore
local delayed = 0
function ExecuteInGameThreadWithDelay(_, f) delayed = delayed + 1; f() end -- luacheck: ignore
function FName(s) return s end -- luacheck: ignore
function StaticConstructObject() return { Attenuation = {} } end -- luacheck: ignore
local placed = {}
function FindAllOf() return placed end -- luacheck: ignore

local now = 0
local statics = {
    SpawnSoundAtLocation = function(_, _, wave, _, _, _, _, _, _, _, autoDestroy) return comp(wave.path, autoDestroy) end,
    GetGameTimeInSeconds = function() return now end,
}
local crouch = 0
local actor = {
    EngineOn = false, valid = true, X = 0,
    BlamUnit = { GetCrouch = function() return crouch end },
    BlamVehicleHumanJeep = { GetEngineAngularVelocityFraction = function() return 0.0 end },
}
function actor.IsValid(self) return self.valid end
function actor.GetAddress() return 4096 end
placed[1] = actor
function actor.GetFullName() return "BP_VHTMongoose_C /Game/Maps/VHT.VHT:PersistentLevel.BP_VHTMongoose_C_0" end
function actor.GetClass()
    return { GetFName = function() return { ToString = function() return "BP_VHTMongoose_C" end } end }
end
function actor.K2_GetActorLocation(self) return { X = self.X, Y = 0, Z = 0 } end

local unit = {
    IsValid = function() return true end,
    GetOwner = function() return actor end,
}
local world = { IsValid = function() return true end }
local range = function(n, l, h, p) return { name = n, wave = "/w/" .. n, natural = p, low = l, high = h } end
local entry = {
    top_speed = 2000,
    sounds = {
        { drive = "engine", gain = 0.6, fade_in = 1, fade_out = 1, start = { "/w/in" }, start_s = 2, ["end"] = { "/w/out" },
          end_s = 2, pitch = { 1, 2 }, ranges = { range("idle", 1, 1.1, 1.1), range("high", 1.1, 2.3, 2.3) } },
        { drive = "crouch", gain = 0.5, fade_in = 0, fade_out = 0, start = { "/w/horn_in" }, start_s = 0.25, ["end"] = {},
          end_s = 0, pitch = { 1, 1 }, ranges = { range("default", 0, 1, 1) } },
    },
}
local logs = {}
local file = "table"
local current = { level = { _dir = "x" }, hit = {} }
local V = require("vehicle_sounds")
V.init({
    Log = function(m) logs[#logs + 1] = m end,
    Current = current,
    findObject = function() return statics end,
    resolveMesh = function(path) return { path = path } end,
    gameVolume = function() return 0.5 end,
    getWorld = function() return world end,
    readFile = function() return file end,
    decode = function() return { BP_VHTMongoose_C = entry } end,
})
local function find(wave)
    for _, c in ipairs(spawned) do if c.wave == wave then return c end end
end
local function step(seconds)
    now = now + (seconds or 0.1)
    V.tick()
end

assert(watched, "the watch arms at init")
watched(unit)
assert(delayed == 0, "no table yet, so a new unit costs nothing")
step()
watched(unit)
assert(delayed == 1, "with a table a new unit is looked at")
step()
assert(#spawned == 0, "an empty vehicle is silent")
assert(#logs == 2, "the sweep and the watch bind one vehicle once: " .. table.concat(logs, "; "))

actor.EngineOn = true
step()
assert(find("/w/in") and find("/w/in").autoDestroy == true, "taking the seat plays the start")
assert(find("/w/idle") and find("/w/high"), "the loops come up under it with a fade")
assert(not find("/w/horn_in"), "no horn yet")
step()
assert(math.abs(find("/w/idle").volume - 0.6 * 0.5) < 1e-6, "idle plays at the track's gain and the slider")
assert(find("/w/high").volume == 0, "the high range waits")

actor.X = 200 -- 2000 cm/s: full revs, once they have climbed
for _ = 1, 12 do
    step()
    actor.X = actor.X + 200
end
assert(find("/w/idle").volume == 0, "at speed the idle range is out")
assert(math.abs(find("/w/high").pitch - 2 / 2.3) < 1e-6, "and the high range is at top pitch")
assert(find("/w/high").moved > 5, "the sound follows")

crouch = 1
step()
assert(find("/w/horn_in"), "crouch plays the horn's start")
assert(not find("/w/default"), "its loop waits for the start to end: no fade")
step(0.3)
assert(find("/w/default"), "then it loops")
crouch = 0
step()
assert(not find("/w/default").playing, "and stops with the key")

actor.EngineOn = false
step()
assert(find("/w/out"), "leaving plays the end")
assert(not find("/w/idle").playing and not find("/w/high").playing, "and the loops fade")

local before = #spawned
actor.EngineOn = true
step()
assert(find("/w/idle").playing, "boarding again reuses the loops")
assert(#spawned == before + 1, "only the start is new")

local function playing(wave)
    local n = 0
    for _, c in ipairs(spawned) do if c.wave == wave and c.playing then n = n + 1 end end
    return n
end

local old = find("/w/idle")
current.level = { _dir = "x" } -- a reload: same world, same vehicle
step()
assert(not old.playing, "a reload stops the loops it drops")
assert(playing("/w/idle") == 1, "and the vehicle binds once more, one engine")

actor.valid = false
step()
assert(playing("/w/idle") == 0, "a vehicle gone takes its loops with it")

-- A level with no table, then none at all: nothing runs and nothing is read.
local made, logged = #spawned, #logs
actor.valid = true
for _, level in ipairs({ { _dir = "y" }, {}, false }) do
    file = nil
    current.level = level or nil
    step()
    delayed = 0
    watched(unit)
    step()
    assert(delayed == 0 and #spawned == made and #logs == logged, "a stock map is left alone")
end
print("ok")
