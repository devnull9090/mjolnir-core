-- lifts.lua's loop: it hands MJOLNIRLobby's DLL the running map's phantoms
-- (a converted level's and a Forge pack's) only when they change, and an
-- empty set once the map is gone. No timers and no players: the DLL pushes.
local Lifts = dofile("mods/MJOLNIRLevelLoader/Scripts/lifts.lua")
ExecuteInGameThreadWithDelay = function() error("no fast loop: the DLL pushes every tick") end
FindAllOf = function() error("no actor scans") end

local sent, logged = {}, {}
local accept = true
local script = {
    request = function(file, export, text)
        assert(file == "lifts.txt" and export == "mjolnir_sim_lifts")
        if not accept then return false end
        sent[#sent + 1] = text
        return true
    end,
}
local phantom = { key = "pack:1", asset = "test", planes = { { 1, 0, 0, -200 }, { -1, 0, 0, -200 }, { 0, 1, 0, -200 },
    { 0, -1, 0, -200 }, { 0, 0, -1, 45 }, { 0, 0, 1, -395 } }, bounds = { 0, 0, 220, 330 }, origin = { 0, 0, 45 },
    forward = { 0, 0, 1 }, direction = { 2000, 450 }, negates_gravity = true }
local tube = { asset = "levels\\lockout_lift_tube", pill = { { 0, 0, 0 }, { 0, 0, 1000 } }, radius = 150,
    bounds = { 0, 0, 500, 600 }, origin = { 0, 0, 0 }, forward = { 0, 0, 1 }, direction = { 3048, 1219.2 } }
local dynamic, collects, refreshes, active = {}, 0, 0, false
local packs = {
    refresh = function() refreshes = refreshes + 1 end,
    active = function() return active end,
    collect = function() collects = collects + 1; return dynamic end,
}
local world = { GetAddress = function() return 1 end }
local current = { level = nil, scenario = "TST" }
Lifts.init({ Current = current, PackLifts = packs, getWorld = function() return world end,
    Log = function(line) logged[#logged + 1] = line end, Script = script })

-- A map with no lifts and no lift blocks: nothing to hand over, no work.
Lifts.tick(); Lifts.tick()
assert(#sent == 0 and collects == 0 and refreshes == 1, "no lifts: no file, no pack scan, one inventory read")

-- A converted level: its phantoms once, then nothing while they stay put.
current.level = { lifts = { tube }, canvas = { origin = { 0, 0, 0 } } }
Lifts.tick()
assert(#sent == 1 and sent[1]:match("\nlift lockout_lift_tube 0 ") and sent[1]:match("pill "), "H2 phantom handed over")
for _ = 1, 5 do Lifts.tick() end
assert(#sent == 1 and refreshes == 2, "a fixed set is written once a map")
assert(logged[#logged]:match("1 phantom%(s%) on TST"))

-- Forge pack lift blocks are read again each tick, and only a change is sent.
active, dynamic = true, { phantom }
Lifts.tick()
assert(#sent == 2 and select(2, sent[2]:gsub("\nlift ", "")) == 2, "the pack's lift joins the level's")
Lifts.tick()
assert(#sent == 2 and collects == 2, "an unmoved piece sends nothing")
dynamic = { { key = "pack:1", asset = "test", planes = phantom.planes, bounds = { 100, 0, 220, 330 },
    origin = { 100, 0, 45 }, forward = { 0, 0, 1 }, direction = { 2000, 450 }, negates_gravity = true } }
Lifts.tick()
assert(#sent == 3, "a moved piece is sent")
dynamic = {}
Lifts.tick()
assert(#sent == 4 and select(2, sent[4]:gsub("\nlift ", "")) == 1, "a deleted piece stops at once")

-- Travel: the world goes, so the DLL is told there are none.
world = nil
Lifts.tick()
assert(#sent == 5 and sent[5] == Lifts.EMPTY, "no world: an empty set")
Lifts.tick()
assert(#sent == 5, "said once")

-- The next map with lifts in Slayer, no level metadata: only the pack's.
world = { GetAddress = function() return 2 end }
current.level, dynamic = nil, { phantom }
Lifts.tick()
assert(#sent == 6 and select(2, sent[6]:gsub("\nlift ", "")) == 1, "works without level metadata")

-- An older Lobby DLL without the export: said once, then left alone.
accept = false
dynamic = {}
local before = #logged
Lifts.tick(); Lifts.tick()
assert(#logged == before + 1 and logged[#logged]:match("MJOLNIRLobby 0%.25%.0"), "an old DLL is reported once")

print("test_lifts_runtime: ok")
