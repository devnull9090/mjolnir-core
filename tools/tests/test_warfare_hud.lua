-- lua tools/tests/test_warfare_hud.lua
local Warfare = dofile("mods/MJOLNIRHud/Scripts/warfare.lua")
local Board = dofile("mods/MJOLNIRHud/Scripts/scoreboard.lua")
Board.registerModes(dofile("mods/MJOLNIRLevelLoader/Scripts/mode_descriptors.lua"))
local function eq(a, b, what) assert(a == b, (what or "value") .. ": " .. tostring(a) .. " ~= " .. tostring(b)) end
local function sample(tick, phase, red, blue, instance, stage)
    return string.format("warfare-state 2\nready 1\nstatus 2\nhost 1\ninstance %s\ntick %d\nsampled_ms %d\nlayout 3\ninsertion_seconds 60\nphase %d\nelapsed_ticks 60\nrate 60\nconnected 2\nscore %d %d\nowner 1 0 2\nglobals %d 60 20569 %d 2 100 0 %d %d 1 0 2\nplayer 0 0 %d 0 -10.500 20.250 100.000 305397761\n",
        instance or "18446744073709551614", tick, 10000 + tick * 16, phase or 2, red or 17, blue or 9,
        phase or 2, (phase or 2) < 2 and 60 or 10, red or 17, blue or 9, stage or 0)
end

local parsed = assert(Warfare.parse(sample(100)))
eq(parsed.instance, "18446744073709551614", "uint64 identity kept exact")
eq(parsed.score[1], 17); eq(parsed.players[0].x, -10.5)
eq(assert(Warfare.parse(sample(100) .. "ordinal 0 0\n")).ordinals[0], 0, "optional HS ordinal metadata")
eq(Warfare.parse(sample(100):sub(1, -2)), nil, "partial last line")
eq(Warfare.parse(sample(100):gsub("owner 1 0 2", "owner 2 0 2")), nil, "torn score/owner mirrors")
eq(Warfare.parse(sample(100):gsub("20569", "20568")), nil, "old variant")
eq(Warfare.parse(sample(100):gsub("layout 3", "layout 2")), nil, "old map layout")
eq(Warfare.parse(sample(100):gsub("warfare%-state 2", "warfare-state 1")), nil, "old snapshot format")
eq(Warfare.parse(sample(100):gsub("phase 2", "phase 4")), nil, "invalid phase")
eq(Warfare.parse(sample(100) .. "ready 1\n"), nil, "duplicate field")
eq(Warfare.parse(sample(100):gsub("player 0 0 0", "player 16 0 0")), nil, "bounded player index")
eq(Warfare.parse(sample(100):gsub("100.000", "nan", 1)), nil, "invalid position")

local raw, reads, fields = sample(100), 0, {}
local Hill = dofile("mods/MJOLNIRHud/Scripts/hill.lua")
local fakeHill = { parse = Hill.parse, markerSpot = Hill.markerSpot }
fakeHill.field = function(name)
    local field = { name = name, draws = 0 }
    field.hide = function() field.hidden = true end
    field.worldOf = function() return {} end
    field.ensureLine = function() end
    field.say = function(text) field.line = text end
    field.draw = function(_, _, _, spot) field.draws = field.draws + 1; field.spot = spot; field.hidden = false end
    field.paint = function(colour) field.colour = colour end
    field.mark = function(_, _, _, _, text) field.label = text end
    field.frame = function() end
    fields[#fields + 1] = field
    return field
end
local hud = Warfare.new({ Hill = fakeHill,
    readSnapshot = function() reads = reads + 1; return raw end,
    readLevel = function() return '{"koth_hills":[[-9000,-3000,40,1000],[0,0,40,1000],[9000,3000,40,1000]]}' end,
})
eq(hud.start("PWR"), 3)
local match = { code = "PWR", variant = "warfare", mode = Board.modes.warfare,
    teams = { [0] = 0, [1] = 0 }, players = {
        [0] = { index = 0, team = "Red", kills = 99, deaths = 0, objectiveScore = 999 },
        [1] = { index = 1, team = "Blue", kills = 50, deaths = 0, objectiveScore = 888 },
    } }
local function tick(t, code, hidden) return hud.tick(match, t, {}, hidden, 0, code or "PWR") end
eq(tick(0), false, "disk sample alone never trusted")
eq(match.teams[0], 0)
tick(.25); eq(reads, 1, "500ms file cadence")
tick(.5); eq(hud.snapshot, nil, "identical old file cannot qualify")
raw = sample(130); eq(tick(1), true, "advancing native sample accepted")
eq(match.teams[0], 17); eq(match.teams[1], 9)
eq(Board.totals(match).Red, 17, "kills and player objective incidents cannot inflate control")
eq(Board.score(match.players[0], match.mode), 0, "control is a team score")
eq(Board.summary(match, 0).left, 17)
eq(Board.winner(match), "RED TEAM WINS")
eq(fields[1].colour, "Red"); eq(fields[2].colour, "empty"); eq(fields[3].colour, "Blue")
eq(fields[1].spot.x, -9000, "authored coordinates used unchanged")
eq(fields[3].label, "C  /  BLUE")
assert(fields[4].line:find("CAPTURE ON FOOT", 1, true))
tick(3.5); eq(hud.snapshot, nil, "stopped live tick expires")
eq(fields[1].hidden, true, "expired objective fields hidden")
eq(match.teams[0], 17, "stale data never rewinds accepted scores")
raw = sample(160, 2, 30, 12, "123"); tick(4)
eq(hud.snapshot, nil, "new instance must qualify again")
raw = sample(190, 2, 30, 12, "123"); tick(4.5)
eq(hud.snapshot.instance, "123"); eq(match.teams[0], 30)
raw = sample(220, 3, 500, 400, "123"); tick(5)
eq(Board.totals(match).Blue, 400)
tick(10); eq(hud.snapshot.phase, 3, "verified final score survives stopped postgame ticks")
eq(hud.accept(assert(Warfare.parse(sample(250, 0, 0, 0, "123"))), 10.25), false,
    "engine's pre-travel round reset cannot replace this instance's terminal result")
eq(hud.snapshot.score[1], 500)
eq(Board.winner(match), "RED TEAM WINS")
local result = Board.results(match, 0, 0)
assert(result:find("team\tRed\t500", 1, true))
tick(10.5, "BGL"); eq(hud.snapshot, nil, "world mismatch discards snapshot")
eq(fields[1].hidden, true)
raw = sample(250, 2, 300, 400, "456"); tick(11)
raw = sample(280, 2, 300, 400, "456"); tick(11.5)
eq(match.teams[0], 300)
raw = raw:gsub("ready 1", "ready 0"):gsub("status 2", "status 0")
tick(12); eq(hud.snapshot, nil, "native close immediately invalidates presentation")

for stage, hint in pairs({ [1] = "BOARDING", [2] = "SPACE TO JUMP", [3] = "SPACE TO DEPLOY",
    [4] = "PARACHUTE DEPLOYED", [6] = "DEPLOYMENT UNAVAILABLE", [7] = "EXITING" }) do
    assert(Warfare.describe(assert(Warfare.parse(sample(300, 1, 0, 0, "456", stage))), 0):find(hint, 1, true))
end
print("Warfare HUD: strict parser, freshness/instance/map guards, authoritative totals, capture fields and insertion hints passed")

local descriptors = dofile("mods/MJOLNIRLevelLoader/Scripts/mode_descriptors.lua")
local Settings = dofile("mods/MJOLNIRLobby/Scripts/settings.lua")
local Variants = dofile("mods/MJOLNIRLevelLoader/Scripts/variant_settings.lua")
Settings.registerModes(descriptors)
Settings.load("respawn=15\nsuicide_penalty=15\ntime_limit=5\nscore.warfare=25\n")
eq(Settings.value(Settings.option("respawn", "warfare")), 5, "persisted Slayer respawn cannot change Warfare")
eq(Settings.text(Settings.option("score", "warfare")), "500")
eq(Settings.text(Settings.option("time_limit", "warfare")), "20 MINUTES OF COMBAT")
eq(Settings.value(Settings.option("respawn", "slayer")), 15, "other modes keep their host settings")
local applied = Variants.forMode({ score = 25, ["score.warfare"] = 10, time_limit = 5,
    respawn_seconds = 15, suicide_seconds = 15, betrayal_seconds = 15, lives = 1, team_lives = 1, respawn_growth = 3 },
    "warfare", descriptors.warfare)
eq(applied.score, nil, "generated variant and native script retain the same score threshold")
eq(applied.time_limit, 0); eq(applied.respawn_seconds, 5); eq(applied.suicide_seconds, 0)
eq(applied.betrayal_seconds, 0); eq(applied.lives, 0); eq(applied.team_lives, 0); eq(applied.respawn_growth, 0)
eq(applied.team_scoring, nil, "no team scoring transformation")
print("Warfare settings: descriptor options and structural rules survive incompatible persisted settings")
