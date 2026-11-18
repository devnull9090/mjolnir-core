-- Run from the repository root with Lua 5.4: the sound mixer's levels
-- (mods/MJOLNIRLevelLoader/Scripts/mixer.lua), its rows and its factors.
local checks = 0
local function eq(actual, expected, label)
    checks = checks + 1
    assert(actual == expected, (label or "value") .. ": expected " .. tostring(expected) .. ", got " .. tostring(actual))
end

local Mixer = dofile("mods/MJOLNIRLevelLoader/Scripts/mixer.lua")

-- Every whole decibel survives the slider and back; the left end mutes.
for db = Mixer.DB_MIN, Mixer.DB_MAX do
    eq(Mixer.fromSlider(Mixer.toSlider(db)), db, "round trip " .. db)
end
eq(Mixer.fromSlider(0.0), Mixer.MUTE, "left end mutes")
eq(Mixer.toSlider(Mixer.MUTE), 0.0, "muted sits at the left end")
eq(Mixer.words(0), "0 dB")
eq(Mixer.words(3), "+3 dB")
eq(Mixer.words(-6), "-6 dB")
eq(Mixer.words(Mixer.MUTE), "MUTED")

-- Names from tag paths: the last folder that is not "details" or "loop".
eq(Mixer.nameOf("sound\\ambience\\sound_scenery\\waves2\\details\\waves2"), "WAVES2")
eq(Mixer.nameOf("sound\\ambience\\zanzibar\\zanzibar_ocean_loop\\zanzibar_ocean_loop"), "ZANZIBAR OCEAN LOOP")
eq(Mixer.nameOf("sound\\ambience\\sound_scenery\\zanzibar_distant_battle\\details\\battle_details", true),
    "ZANZIBAR DISTANT BATTLE / BATTLE DETAILS")
eq(Mixer.nameOf("/Game/MJOLNIR/Maps/ZAN/Sounds/sound_gate.sound_gate"), "GATE")

-- A level's rows and factors, with no game: one row a tag, ALL SOUNDS first.
local Current = { worldName = "/Game/Levels/Halo1/Solo/TST/TST", level = {
    canvas = { origin = { 0, 0, 0 } },
    environment = { sounds = {
        background = { { wave = "/w/a.a", source = "s\\bed\\bed", set = 0 } },
        emitters = { { wave = "/w/b.b", source = "s\\hum\\hum", pos = { 0, 0, 0 }, inner = 100, falloff = 100 },
                     { wave = "/w/b.b", source = "s\\hum\\hum", pos = { 5000, 0, 0 }, inner = 100, falloff = 100 } },
        details = { { waves = { "/w/c.c" }, source = "s\\gull\\details\\gull", period = { 4, 9 } } },
    } },
} }
local logs = {}
local m = Mixer.new({ Log = function(s) logs[#logs + 1] = s end, Current = Current,
    Json = { decode = function() return {} end }, getWorld = function() end, getPlayerController = function() end,
    getCamera = function() return nil end, applyMix = function() end, retainUIClass = function() end })
eq(m.factor("s\\hum\\hum"), 1.0, "a sound at 0 dB plays as built")
m.levels["s\\hum\\hum"], m.factors = -20, {}
eq(math.abs(m.factor("s\\hum\\hum") - 0.1) < 1e-9, true, "-20 dB is a tenth")
m.levels[Mixer.MASTER], m.factors = 20, {}
eq(math.abs(m.factor("s\\hum\\hum") - 1.0) < 1e-9, true, "ALL SOUNDS multiplies in")
m.levels["s\\bed\\bed"], m.factors = Mixer.MUTE, {}
eq(m.factor("s\\bed\\bed"), 0.0, "muted is silent")

print("sound mixer: " .. checks .. " checks passed")
