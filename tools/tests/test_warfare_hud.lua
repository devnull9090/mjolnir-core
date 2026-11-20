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
local Flight=dofile("mods/MJOLNIRHud/Scripts/warfare_instruments.lua")
local airborneSample=sample(100,1,0,0,"123",4).."flight 0 -3 4 -12 1 -0.53\nclearance 0 82.37\n"
local airborne=assert(Warfare.parse(airborneSample))
local speed,sink,track,height,label=Flight.readout(airborne.flight[0],airborne.clearance[0])
eq(speed,"47","3-D speed from native m/s to km/h"); eq(sink,"12");eq(label,"SINK")
eq(track,"323° NW");eq(height,"82");eq(airborne.flight[0].brake,true);eq(airborne.flight[0].steer,-.53)
eq(select(3,Flight.readout({vx=1,vy=0,vz=0})),"090° E","native X east matches the tactical grid")
eq(select(3,Flight.readout({vx=0,vy=-5,vz=2})),"180° S")
eq(select(3,Flight.readout({vx=0,vy=0,vz=-35})),"—","vertical fall has no horizontal bearing")
eq(select(5,Flight.readout({vx=0,vy=1,vz=3})),"CLIMB")
eq(Flight.readout(nil,nil),"—","missing instrument data is not zero")
for _,row in ipairs({"flight 0 -3 4 -12 1 0\n","flight 1 1e999 2 3 0 0\n",
    "flight 1 2 3 4 3 0\n","flight 1 2 3 4 1 -2\n","clearance 0 50\n","clearance 1 -20\n"}) do
    eq(Warfare.parse(airborneSample..row),nil,"bad or duplicate flight observation")
end
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

-- Build and tick the actual runtime-composed panel with a small UMG double.
do
    local created, frames={},{}
    local function new(name)
        local w={IsValid=function() return true end}
        function w:SetText(t) self.value=t end
        function w:SetVisibility(v) self.visibility=v end
        function w:AddChildToCanvas() return new() end
        setmetatable(w,{__index=function() return function() end end})
        if name then created[name]=w end
        return w
    end
    local oldFind,oldConstruct,oldName,oldText=StaticFindObject,StaticConstructObject,FName,FText
    StaticFindObject=function(path)
        if path:find("Default__WidgetBlueprintLibrary",1,true) then
            return {Create=function()
                local w=new();w.WidgetTree={};frames[#frames+1]=w;return w
            end}
        end
        return path
    end
    FName=function(name) return name end;FText=FName
    StaticConstructObject=function(_,_,name) return new(name) end
    local pc={GetAddress=function() return 25 end,
        PlayerCameraManager={IsValid=function() return true end,GetCameraLocation=function() return {X=10,Y=20,Z=30} end}}
    local projection=true
    function pc:GetViewportSize(size) size.SizeX,size.SizeY=1280,720 end
    function pc:ProjectWorldLocationToScreen(world,pixel)
        eq(world.X,-290);eq(world.Y,-380,"Blam north is UE -Y");eq(world.Z,-1170)
        pixel.X,pixel.Y=780,430
        return projection
    end
    local panel=Flight.new()
    assert(panel.update(pc,4,airborne.flight[0],82,"SPACE","SHIFT"))
    eq(created.Speed.value,"47");eq(created.Mode.value,"BRAKING");eq(created.Track.value,"TRK  323° NW")
    eq(frames[1].visibility,3)
    panel.frame(pc,1)
    eq(frames[2].visibility,3,"flight path drawn at visible measured trajectory")
    projection=false;panel.frame(pc,1.1);eq(frames[2].visibility,1)
    panel.update(pc,3,nil,nil,"U","L3")
    eq(created.Mode.value,"FREEFALL");eq(created.Speed.value,"—");eq(created.Control.value,"U  DEPLOY")
    panel.hide();eq(frames[1].visibility,1);eq(#frames,2,"widgets reused throughout drop")
    StaticFindObject,StaticConstructObject,FName,FText=oldFind,oldConstruct,oldName,oldText
end

-- Exercise the actual HUD poll from the installation under test. The merged
-- release once called Markers.tick with only five arguments. Module-level
-- parser and lifecycle checks still passed, but each tick cleared the rig.
do
    local f = assert(io.open("mods/MJOLNIRHud/Scripts/main.lua", "rb"))
    local main = f:read("*a"):gsub("\r\n", "\n")
    f:close()
    local tickSource = assert(main:match("(local function tick%(%)\n.-\nend)\n"))
    local stamp, activeCode = 10, "PWR"
    local world = {}
    local pc = { GetWorld = function() return world end }
    local stop = {}
    local function noop() end
    local dispatch = dofile("mods/MJOLNIRHud/Scripts/markers.lua").new({Hill={}})
    local fixture = {
        code="PWR", variant="warfare", mode={family="warfare"}, teams={[0]=0,[1]=0},
        players={}, warfare=hud,
    }
    local env = setmetatable({
        playerController=function() return pc end, scenarioOf=function() return activeCode end,
        Hitches={poll=noop}, lastWorld=activeCode, Match=fixture,
        hookIncidents=noop, ensureWidgets=noop, ensureFrameHook=noop,
        refreshLocalPlayer=noop, isHostWorld=function() return false end,
        findBipeds=noop, Markers=dispatch, now=function() return stamp end,
        HudHidden=true, LOCAL_PLAYER=0, boardDirty=false, Bots={tick=noop},
        -- The first roster refresh immediately after objective dispatch marks
        -- the end of this test's portion of the full game-thread poll.
        syncBotNames=function() error(stop) end,
    }, {__index=_G})
    local poll = assert(load(tickSource .. "\nreturn tick", "@staged HUD poll", "t", env))()
    local function pollAt(t, tck, map)
        stamp, activeCode = t, map
        env.lastWorld = map
        fixture.nextBotRoster = 0
        raw = sample(tck, 2, 30, 12, "833444", 4)
        local ok, err = pcall(poll)
        assert(not ok and err == stop, tostring(err))
    end
    pollAt(13, 300, "PWR")
    pollAt(13.5, 330, "PWR")
    eq(fixture.warfare.snapshot and fixture.warfare.snapshot.instance, "833444", "poll forwards actual PWR world")
    eq(fixture.warfare.snapshot.players[0].stage, 4, "presentation receives the gliding rider")
    eq(env.boardDirty, true, "changed native score invalidates the normal scoreboard")
    pollAt(14, 360, "BGL")
    eq(fixture.warfare.snapshot, nil, "poll supplies actual world on travel")
end

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
