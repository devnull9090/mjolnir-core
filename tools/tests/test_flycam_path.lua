-- Run from the repository root: python -c "from lupa import LuaRuntime; LuaRuntime().execute(open('tools/tests/test_flycam_path.lua').read())"
local Path = dofile("mods/MJOLNIRFlyCam/Scripts/camera_path.lua")
local function near(a, b) assert(math.abs(a - b) < 1e-8, tostring(a) .. " ~= " .. tostring(b)) end
local a = { X = 0, Y = 10, Z = 0, Pitch = 0, Yaw = 170, Roll = -170, FOV = 70 }
local b = { X = 100, Y = 30, Z = 20, Pitch = 20, Yaw = -170, Roll = 170, FOV = 90 }
local c = { X = 300, Y = 30, Z = 40, Pitch = 20, Yaw = -150, Roll = 170, FOV = 110 }
local poses = { a = a, b = b, c = c }

local line = assert(Path.record("a", a))
local replacement = assert(Path.record("a", b))
local loaded = assert(Path.parse(line .. replacement .. assert(Path.record("b", b))))
near(loaded.a.X, 100) -- last record wins without deleting earlier data
assert(not Path.parse(line:sub(1, -2))) -- an incomplete append is not silently accepted
assert(not Path.parse("pose1,bad,1,2\n"))
assert(not Path.record("../bad", a))
assert(not Path.record("bad", { X = 0 / 0 }))
assert(not Path.validName("two words"))
assert(not Path.create(poses, { "a", "missing" }, 2, "linear"))
assert(not Path.create(poses, { "a", "b" }, 0, "linear"))
assert(not Path.create(poses, { "a", "b" }, 2, "unknown"))
local tooMany = {}; for i = 1, 33 do tooMany[i] = "a" end
assert(not Path.create(poses, tooMany, 2, "linear"))
local invalidFov = { X = 0, Y = 0, Z = 0, Pitch = 0, Yaw = 0, Roll = 0, FOV = 200 }
assert(not Path.pose(invalidFov))

local linear = assert(Path.create(poses, { "a", "b", "c" }, 2, "linear"))
local start, done = Path.sample(linear, 0)
near(start.X, 0); assert(not done)
local mid = Path.sample(linear, 1)
near(mid.X, 50); near(mid.Yaw, 180); near(mid.Roll, -180); near(mid.FOV, 80)
local boundary = Path.sample(linear, 2)
near(boundary.X, 100); near(boundary.Yaw, -170)
local second = Path.sample(linear, 3)
near(second.X, 200); near(second.FOV, 100)
local finish, finished = Path.sample(linear, 4)
near(finish.X, 300); near(finish.Yaw, -150); assert(finished)
poses.b.X = 999 -- the in-flight path is a snapshot
near((Path.sample(linear, 2)).X, 100)
poses.b.X = 100

local smooth = assert(Path.create(poses, { "a", "b" }, 2, "smooth"))
near((Path.sample(smooth, 0.5)).X, 15.625) -- smoothstep(.25)
near((Path.sample(smooth, 1)).X, 50)
local many = assert(Path.create(poses, { "a", "b" }, 2, "linear"))
local few = assert(Path.create(poses, { "a", "b" }, 2, "linear"))
local manyPose, fewPose
for _ = 1, 60 do manyPose = Path.advance(many, 1 / 60) end
for _ = 1, 5 do fewPose = Path.advance(few, 0.2) end
near(manyPose.X, fewPose.X); near(manyPose.Yaw, fewPose.Yaw)
local bad, _, badError = Path.advance(few, -1)
assert(not bad and badError)

-- Integration exercises the actual console and tick callbacks with mocked UE
-- objects. File I/O is an in-memory Saved directory, never the installed game.
local originalGetenv, originalOpen = os.getenv, io.open
local savedText
os.getenv = function(name) if name == "LOCALAPPDATA" then return "FAKE_LOCAL" end return originalGetenv(name) end
io.open = function(name, mode)
    if not name:find("FAKE_LOCAL", 1, true) then return originalOpen(name, mode) end
    if mode == "rb" and not savedText then return nil, "not found" end
    local stream = {}
    function stream:read() return savedText end
    function stream:write(text) savedText = (savedText or "") .. text; return self end
    function stream:close() return true end
    return stream
end
local function valid(o) o.IsValid = function() return true end; return o end
local component = valid({ FieldOfView = 90, bConstrainAspectRatio = true })
local camera = valid({ CameraComponent = component })
function camera:K2_SetActorLocationAndRotation(loc, rot)
    self.loc = { X = loc.X, Y = loc.Y, Z = loc.Z }
    self.rot = { Pitch = rot.Pitch, Yaw = rot.Yaw, Roll = rot.Roll }
end
local world = valid({ GetAddress = function() return 333 end })
function camera:GetWorld() return world end
function world:SpawnActor() return camera end
local pawn = valid({})
function pawn:GetAttachedActors() end
function pawn:K2_GetComponentsByClass() return {} end
local cameraManager = valid({})
function cameraManager:GetCameraLocation() return { X = 1, Y = 2, Z = 3 } end
function cameraManager:GetCameraRotation() return { Pitch = 0, Yaw = 30, Roll = 0 } end
function cameraManager:GetFOVAngle() return 75 end
local pc = valid({ Pawn = pawn, PlayerCameraManager = cameraManager, MyHUD = valid({ bShowHUD = true }) })
function pc:GetAddress() return 101 end
function pc:IsLocalController() return true end
function pc:GetWorld() return world end
function pc:SetViewTargetWithBlend(target) self.target = target end
function pc:IsInputKeyDown() return true end -- manual input must not corrupt playback
function pc:GetInputMouseDelta(dx, dy) dx.DeltaX = 50; dy.DeltaY = 50 end
local remote = valid({ GetAddress = function() return 202 end, IsLocalController = function() return false end })
local engine = valid({ GameViewport = { GameInstance = { LocalPlayers = { { PlayerController = pc } } } } })
FindFirstOf = function(name) if name == "GameEngine" then return engine end return remote end
FindAllOf = function(name) if name == "PlayerController" then return { remote, pc } end return {} end
StaticFindObject = function() return valid({}) end
FName = function(s) return s end
local tick, command
RegisterHook = function(_, cb) tick = cb; return 1 end
RegisterConsoleCommandHandler = function(name, cb) assert(name == "mjolnir_camera"); command = cb end
RegisterKeyBind = function() end
Key = { F8 = 1, F7 = 2, F9 = 3, NUM_ZERO = 4, ADD = 5, SUBTRACT = 6, OEM_SIX = 7, OEM_FOUR = 8 }
ExecuteInGameThreadWithDelay = function(_, cb) cb() end
dofile("mods/MJOLNIRFlyCam/Scripts/main.lua")
assert(command)
local function context(obj) return { get = function() return obj end } end
local function delta(seconds) return { get = function() return seconds end } end
command(nil, { "set", "a", "0", "0", "0", "0", "170", "0", "70" })
command(nil, { "set", "b", "100", "30", "20", "20", "-170", "0", "90" })
assert(savedText and savedText:find("pose1,a", 1, true))
command(nil, { "play", "2", "linear", "a", "b" })
assert(pc.target == camera and not pc.MyHUD.bShowHUD)
assert(component.bConstrainAspectRatio == false)
near(camera.loc.X, 0); near(component.FieldOfView, 70)
tick(context(remote), delta(1)) -- remote callbacks on the host must do nothing
near(camera.loc.X, 0)
tick(nil, delta(1)); near(camera.loc.X, 0) -- unknown contexts fail closed
tick(context(pc), delta(1))
near(camera.loc.X, 50); near(camera.rot.Yaw, 180); near(component.FieldOfView, 80)
tick(context(remote), delta(1)); near(camera.loc.X, 50)
-- A different Lua wrapper around the same UObject address is still local.
local sameOwner = { GetAddress = function() return 101 end }
tick(context(sameOwner), delta(1))
near(camera.loc.X, 100); near(camera.rot.Yaw, -170); near(component.FieldOfView, 90)
command(nil, { "goto", "a" }); near(camera.loc.X, 0)
command(nil, { "play", "2", "smooth", "a", "b" })
tick(context(pc), delta(0.5)); near(camera.loc.X, 15.625)
command(nil, { "stop" }); assert(pc.target == camera)
command(nil, { "reload" }); command(nil, { "goto", "b" }); near(camera.loc.X, 100)
local completeRecords = savedText
savedText = completeRecords .. "incomplete"
command(nil, { "set", "c", "10", "0", "0", "0", "0", "0" })
assert(savedText == completeRecords .. "incomplete") -- no unsafe overwrite/append
command(nil, { "reload" }) -- failed reload does not erase in-memory poses
command(nil, { "goto", "a" }); near(camera.loc.X, 0)
savedText = completeRecords
command(nil, { "play", "2", "linear", "a", "b" })
tick(context(pc), delta(1.2)) -- a large but valid tick is not discarded
near(camera.loc.X, 60)
command(nil, { "play", "2", "linear", "a", "b" })
tick(context(pc), delta(0.002)); tick(context(pc), delta(0.002))
near(camera.loc.X, 0.2) -- no clock heuristic may drop high-FPS frames
local newer = valid({ Pawn = pawn, PlayerCameraManager = cameraManager,
                      MyHUD = valid({ bShowHUD = false }) })
function newer:GetAddress() return 303 end
function newer:GetWorld() return world end
function newer:SetViewTargetWithBlend(target) self.target = target end
function newer:IsInputKeyDown() return false end
function newer:GetInputMouseDelta() end
-- Older builds may not expose IsLocalController; the engine's LocalPlayers
-- chain still identifies the local controller authoritatively.
engine.GameViewport.GameInstance.LocalPlayers[1].PlayerController = newer
tick(context(newer), delta(1))
near(camera.loc.X, 0.2)
assert(newer.MyHUD.bShowHUD == false and newer.target == nil) -- no new owner mutation during loss
command(nil, { "goto", "b" })
assert(newer.target == camera and newer.MyHUD.bShowHUD == false)
near(camera.loc.X, 100)
command(nil, { "off" }); assert(newer.target == pawn and newer.MyHUD.bShowHUD)
-- Fallback ignores a remote even when UEHelpers returns it first.
engine.GameViewport.GameInstance.LocalPlayers[1].PlayerController = nil
package.preload.UEHelpers = function() return { GetPlayerController = function() return remote end } end
command(nil, { "goto", "a" }); assert(pc.target == camera and not pc.MyHUD.bShowHUD)
command(nil, { "off" }); assert(pc.target == pawn and pc.MyHUD.bShowHUD)
-- With no authoritative engine chain or positive local check, do not guess.
pc.IsLocalController = nil
command(nil, { "goto", "a" }); assert(pc.target == pawn and pc.MyHUD.bShowHUD)
function pc:IsLocalController() return true end
command(nil, { "play", "2", "linear", "a", "b" }); assert(pc.target == camera)
pc.IsValid = function() return false end
tick(context(remote), delta(1)) -- owner destruction cancels even on another controller's tick
near(camera.loc.X, 0)
pc.IsValid = function() return true end
os.getenv, io.open = originalGetenv, originalOpen
print("flycam path: pure interpolation, persistence and mocked console/tick integration passed")
