-- MJOLNIR FlyCam (Detached Camera for Halo Campaign Evolved)
--
-- The player pawn in this game is a puppet of the original Blam engine
-- simulation, which reads raw input directly. Nothing at the UE layer
-- (DisableInput, SetIgnoreMoveInput, SetInputEnabled, world pause) stops
-- WASD/mouse from driving the player. Camera movement therefore lives on
-- the numpad, which the Blam sim does not read.
--
-- Hotkeys:
--   F8 : Toggle FlyCam ON/OFF
--   F7 : Toggle HUD Overlay ON/OFF
--   F9 or Numpad 0 : Toggle Mouse Look ON/OFF
--   mjolnir_camera  : Named poses and timed paths (see this mod's README)
-- Camera controls (numpad, active only while FlyCam is on):
--   Numpad 8 / 2 : Forward / Backward
--   Numpad 4 / 6 : Strafe Left / Right
--   Numpad 9 / 3 : Up / Down
--   Numpad 5     : Snap camera back to the player
--   Numpad + / - (or ] / [) : Raise / Lower base speed
--   Left Shift   : Boost (3x)
--   Mouse        : Look around (when Mouse Look is on)
--
-- While FlyCam is on, WASD/mouse still control the player (see note above).
-- The first-person rig (arms + gun) is hidden so it stops floating in front
-- of the lens; the game's own shadow-proxy body doubles as the external
-- player model.

local bEnabled = false
local bMouseLookEnabled = true
local bHUDVisible = true

local scriptPath = (debug.getinfo(1, "S").source or ""):gsub("^@", "")
local scriptDirectory = scriptPath:match("^(.*)[\\/][^\\/]+$") or "."
local Path = dofile(scriptDirectory .. "\\camera_path.lua")
local localAppData = os.getenv("LOCALAPPDATA")
local PoseFile = localAppData and (localAppData .. "\\Meteorite\\Saved\\MJOLNIR_FlyCam_poses.txt") or nil
local Poses = {}
local Playback = nil

local SpawnedCameraActor = nil
local OwnerController = nil
local OwnerAddress = nil
local Engine = nil

local BaseSpeed = 1800.0 -- units per second
local BoostMultiplier = 3.0
local MouseSensitivity = 2.0

local CamLoc = { X = 0.0, Y = 0.0, Z = 0.0 }
local CamRot = { Pitch = 0.0, Yaw = 0.0, Roll = 0.0 }
local CamFOV = 90.0

-- Visibility bookkeeping: exact prior state, restored on disable.
local SavedVisibility = {}   -- { {comp=<obj>, visible=<bool>} }
local SavedHudWidgets = {}   -- { {widget=<obj>, visibility=<int>} }
local CommandOutput = nil

local function Log(msg)
    print("[MJOLNIR FlyCam] " .. tostring(msg) .. "\n")
    if CommandOutput then pcall(function() CommandOutput:Log("MJOLNIR FlyCam: " .. tostring(msg)) end) end
end

local function IsValid(obj)
    local ok, valid = pcall(function() return obj and obj:IsValid() end)
    return ok and valid == true
end

-- nil means this build cannot answer the question; it is not proof of local.
local function IsLocal(obj)
    local ok, localController = pcall(function() return obj:IsLocalController() end)
    if ok and type(localController) == "boolean" then return localController end
    return nil
end

local function Address(obj)
    local ok, address = pcall(function() return obj:GetAddress() end)
    if ok and type(address) == "number" and address ~= 0 then return address end
    return nil
end

-- The engine's LocalPlayers[1] is authoritative, including older builds
-- without IsLocalController. Cache the engine itself, not the player: travel
-- replaces the local controller while the engine stays alive.
local function EngineLocalController()
    if not IsValid(Engine) then
        local ok, engine = pcall(function() return FindFirstOf("GameEngine") end)
        Engine = ok and engine or nil
    end
    if not IsValid(Engine) then return nil end
    local ok, pc = pcall(function()
        return Engine.GameViewport.GameInstance.LocalPlayers[1].PlayerController
    end)
    if ok and IsValid(pc) and IsLocal(pc) ~= false then return pc end
    return nil
end

local function GetPlayerController()
    local pc = EngineLocalController()
    if pc then return pc end
    -- Some older builds do not expose the engine chain. UEHelpers itself can
    -- return a remote player controller, so fallback candidates must prove
    -- they are local; never use the first merely valid player on a host.
    local okHelper, candidate = pcall(function() return require("UEHelpers").GetPlayerController() end)
    if okHelper and IsValid(candidate) and IsLocal(candidate) == true then return candidate end
    local okAll, pcs = pcall(function() return FindAllOf("PlayerController") end)
    if okAll and pcs then
        for _, p in ipairs(pcs) do
            if IsValid(p) and IsLocal(p) == true then return p end
        end
    end
    return nil
end

local function OwnerStillLocal()
    if not IsValid(OwnerController) or not IsValid(SpawnedCameraActor) then return false end
    local localState = IsLocal(OwnerController)
    if localState == false then return false end
    local current = EngineLocalController()
    local currentAddress = current and Address(current)
    if currentAddress then return currentAddress == OwnerAddress end
    -- If the engine chain is unavailable, accept only explicit local proof.
    return localState == true
end

-- FKey structs for IsInputKeyDown. Must be a table with KeyName; passing a
-- bare FName makes UE4SS marshal garbage as FKey's KeyDetails shared-ptr,
-- which is an instant access violation that pcall cannot catch.
local FKeyCache = {}
local function FKeyOf(name)
    local k = FKeyCache[name]
    if not k then
        k = { KeyName = FName(name) }
        FKeyCache[name] = k
    end
    return k
end

local function IsDown(PC, keyName)
    local ok, down = pcall(function() return PC:IsInputKeyDown(FKeyOf(keyName)) end)
    return ok and down == true
end

local function Rad(deg)
    return deg * (math.pi / 180.0)
end

local function GetForwardVector(rot)
    local p = Rad(rot.Pitch)
    local y = Rad(rot.Yaw)
    return {
        X = math.cos(p) * math.cos(y),
        Y = math.cos(p) * math.sin(y),
        Z = math.sin(p)
    }
end

local function GetRightVector(rot)
    local y = Rad(rot.Yaw + 90.0)
    return {
        X = math.cos(y),
        Y = math.sin(y),
        Z = 0.0
    }
end

-- K2_GetComponentsByClass returns a plain table whose entries may need :get()
local function unwrap(e)
    if type(e) == "userdata" and e.get then return e:get() end
    return e
end

local function ForEachPrimitiveComponent(actor, fn)
    local prim = StaticFindObject("/Script/Engine.PrimitiveComponent")
    if not prim or not prim:IsValid() then return end
    local ok, comps = pcall(function() return actor:K2_GetComponentsByClass(prim) end)
    if not ok or type(comps) ~= "table" then return end
    for i = 1, #comps do
        local c = unwrap(comps[i])
        if c then pcall(fn, c) end
    end
end

local function ForEachPawnAndWeaponActor(pawn, fn)
    pcall(fn, pawn)
    local attached = {}
    pcall(function() pawn:GetAttachedActors(attached, true, false) end)
    for i = 1, #attached do
        local a = unwrap(attached[i])
        if a then pcall(fn, a) end
    end
end

-- Hide the first-person rig: FP arms, visor overlays, and FP gun meshes
-- (FP_-prefixed component/class names on the pawn and attached weapon
-- actors) — but NOT the Shadow proxies. This game is first-person only and
-- has no separate third-person model: the bOwnerNoSee "shadow" meshes
-- (BPC_FP_ShadowSkeletalMesh full body, BPC_FP_ShadowStaticMesh gun) are
-- the only complete external body, and the engine already shows them
-- automatically when the view target is not the pawn. Vanilla's "two guns"
-- came from the always-rendered FP arms overlapping that shadow body.
-- (BPC_PAWN_SkeletalMesh is just the owner-view lower body — the legs you
-- see looking down in first person — so leave its bOnlyOwnerSee alone.)
local function HideFirstPersonRig(pawn)
    ForEachPawnAndWeaponActor(pawn, function(actor)
        ForEachPrimitiveComponent(actor, function(c)
            if not c:IsValid() then return end
            local cn = c:GetClass():GetFName():ToString()
            local n = c:GetFName():ToString()
            if (cn:find("FP_") or n:find("FP_"))
                and not (cn:find("Shadow") or n:find("Shadow"))
                and c:IsVisible() then
                SavedVisibility[#SavedVisibility + 1] = { comp = c, visible = true }
                c:SetVisibility(false, false)
            end
        end)
    end)
end

-- Weapon swaps while flying spawn fresh FP meshes; re-hide periodically.
local function RescanFirstPersonRig(pawn)
    HideFirstPersonRig(pawn)
end

local function RestoreVisibility()
    for _, entry in ipairs(SavedVisibility) do
        pcall(function()
            if entry.comp:IsValid() then
                entry.comp:SetVisibility(entry.visible, false)
            end
        end)
    end
    SavedVisibility = {}
end

local ESlateVisibility_Collapsed = 1

local function SetHUDVisible(visible)
    bHUDVisible = visible
    local PC = IsValid(OwnerController) and OwnerController or GetPlayerController()
    if PC and PC:IsValid() then
        pcall(function()
            if PC.MyHUD and PC.MyHUD:IsValid() then
                PC.MyHUD.bShowHUD = visible
            end
        end)
    end

    -- The HUD in this game is UMG (WBP_HUD_*), not AHUD.
    if visible then
        for _, entry in ipairs(SavedHudWidgets) do
            pcall(function()
                if entry.widget:IsValid() then
                    entry.widget:SetVisibility(entry.visibility)
                end
            end)
        end
        SavedHudWidgets = {}
    else
        local ok, widgets = pcall(function() return FindAllOf("UserWidget") end)
        if ok and widgets then
            for _, w in ipairs(widgets) do
                pcall(function()
                    if w:IsValid() then
                        local cn = w:GetClass():GetFName():ToString()
                        if cn:find("WBP_HUD") then
                            local vis = w:GetVisibility()
                            if vis ~= ESlateVisibility_Collapsed then
                                SavedHudWidgets[#SavedHudWidgets + 1] = { widget = w, visibility = vis }
                                w:SetVisibility(ESlateVisibility_Collapsed)
                            end
                        end
                    end
                end)
            end
        end
    end
end

local LoseCamera

local function ToggleHUD()
    if bEnabled and not OwnerStillLocal() then LoseCamera("local controller changed") end
    SetHUDVisible(not bHUDVisible)
end

-- A controller/level may disappear while detached. Restore only the old
-- objects we hid; never select a remote controller or modify a replacement
-- local player's HUD during travel.
LoseCamera = function(reason)
    local owner, address = OwnerController, OwnerAddress
    local localPc = EngineLocalController()
    local stillOwner = IsValid(owner) and IsLocal(owner) ~= false and
        ((localPc and Address(localPc) == address) or (not localPc and IsLocal(owner) == true))
    bEnabled = false
    Playback = nil
    if stillOwner then
        pcall(function()
            if owner.Pawn and owner.Pawn:IsValid() then owner:SetViewTargetWithBlend(owner.Pawn, 0.2, 0, 0, false) end
            if owner.MyHUD and owner.MyHUD:IsValid() then owner.MyHUD.bShowHUD = true end
        end)
    end
    RestoreVisibility()
    for _, entry in ipairs(SavedHudWidgets) do
        pcall(function() if entry.widget:IsValid() then entry.widget:SetVisibility(entry.visibility) end end)
    end
    SavedHudWidgets = {}
    SpawnedCameraActor, OwnerController, OwnerAddress = nil, nil, nil
    bHUDVisible = true
    Log("FlyCam disabled: " .. reason)
end

local function UpdateCameraTransform()
    if not bEnabled or not SpawnedCameraActor or not SpawnedCameraActor:IsValid() then return end
    pcall(function()
        SpawnedCameraActor:K2_SetActorLocationAndRotation(
            { X = CamLoc.X, Y = CamLoc.Y, Z = CamLoc.Z },
            { Pitch = CamRot.Pitch, Yaw = CamRot.Yaw, Roll = CamRot.Roll },
            false,
            {},
            false
        )
        local component = SpawnedCameraActor.CameraComponent
        if component and component:IsValid() then component.FieldOfView = CamFOV end
    end)
end

local function CurrentPose()
    return { X = CamLoc.X, Y = CamLoc.Y, Z = CamLoc.Z,
             Pitch = CamRot.Pitch, Yaw = CamRot.Yaw, Roll = CamRot.Roll, FOV = CamFOV }
end

local function ApplyPose(pose)
    CamLoc = { X = pose.X, Y = pose.Y, Z = pose.Z }
    CamRot = { Pitch = pose.Pitch, Yaw = pose.Yaw, Roll = pose.Roll }
    CamFOV = pose.FOV
    UpdateCameraTransform()
end

local function SnapToPlayer(PC)
    pcall(function()
        local pawn = PC.Pawn
        if pawn and pawn:IsValid() then
            local loc = pawn:K2_GetActorLocation()
            CamLoc = { X = loc.X, Y = loc.Y, Z = loc.Z + 150.0 }
        end
    end)
end

-- Per-tick camera update, driven by a RegisterHook on the game's own
-- PlayerController ReceiveTick (game thread, once per frame).
-- Two approaches that do NOT work here:
--   * RegisterHook on PlayerCameraManager:UpdateCamera — not a UFunction,
--     registration fails silently and the camera never moves.
--   * LoopAsync(16ms) + ExecuteInGameThread per tick — the cross-thread
--     task churn crashes UE4SS within seconds (access violation in the
--     Lua marshaling layer).
local RescanInterval = 2.0
local RescanTimer = 0.0

local function OnCameraTick(dt, PC)
    if not bEnabled then return end

    -- Level transition or camera destroyed under us: shut down cleanly.
    if not SpawnedCameraActor or not SpawnedCameraActor:IsValid() then
        LoseCamera("camera lost (level change?)")
        return
    end

    -- Playback follows the actual game tick delta, including a hitch, so a
    -- six-second segment does not silently gain time. A paused/invalid tick
    -- does not advance the shot. Manual movement retains its existing
    -- large-delta cap to avoid a jump after a pause.
    local pathDt = (type(dt) == "number" and dt == dt and dt > 0 and dt < 60) and dt or 0
    if type(dt) ~= "number" or dt ~= dt or dt <= 0.0 or dt > 0.5 then dt = 0.016 end

    if Playback then
        local pose, finished, err = Path.advance(Playback, pathDt)
        if not pose then
            Playback = nil
            Log("Camera path stopped: " .. tostring(err))
        else
            ApplyPose(pose)
            if finished then
                Playback = nil
                Log("Camera path finished; FlyCam remains at the final pose.")
            end
        end
    else

    -- Mouse look
    if bMouseLookEnabled then
        pcall(function()
            local d, d2 = {}, {}
            PC:GetInputMouseDelta(d, d2)
            local dx = d.DeltaX or 0.0
            local dy = d.DeltaY or 0.0
            if math.abs(dx) > 0.001 or math.abs(dy) > 0.001 then
                CamRot.Yaw = CamRot.Yaw + (dx * MouseSensitivity)
                CamRot.Pitch = math.max(-89.0, math.min(89.0, CamRot.Pitch + (dy * MouseSensitivity)))
            end
        end)
    end

    -- Numpad movement
    local bBoost = IsDown(PC, "LeftShift") or IsDown(PC, "RightShift")
    local speed = BaseSpeed * (bBoost and BoostMultiplier or 1.0) * dt

    local bForward  = IsDown(PC, "NumPadEight")
    local bBackward = IsDown(PC, "NumPadTwo")
    local bLeft     = IsDown(PC, "NumPadFour")
    local bRight    = IsDown(PC, "NumPadSix")
    local bUp       = IsDown(PC, "NumPadNine")
    local bDown     = IsDown(PC, "NumPadThree")

    local moveX, moveY, moveZ = 0.0, 0.0, 0.0

    if bForward or bBackward then
        local fwd = GetForwardVector(CamRot)
        local sign = bForward and 1.0 or 0.0
        sign = sign - (bBackward and 1.0 or 0.0)
        moveX = moveX + fwd.X * speed * sign
        moveY = moveY + fwd.Y * speed * sign
        moveZ = moveZ + fwd.Z * speed * sign
    end
    if bLeft or bRight then
        local rgt = GetRightVector(CamRot)
        local sign = (bRight and 1.0 or 0.0) - (bLeft and 1.0 or 0.0)
        moveX = moveX + rgt.X * speed * sign
        moveY = moveY + rgt.Y * speed * sign
    end
    if bUp then moveZ = moveZ + speed end
    if bDown then moveZ = moveZ - speed end

    if IsDown(PC, "NumPadFive") then
        SnapToPlayer(PC)
    else
        CamLoc.X = CamLoc.X + moveX
        CamLoc.Y = CamLoc.Y + moveY
        CamLoc.Z = CamLoc.Z + moveZ
    end

        UpdateCameraTransform()
    end

    -- Re-hide FP meshes that respawned (weapon swap etc.) every couple seconds.
    RescanTimer = RescanTimer + dt
    if RescanTimer >= RescanInterval then
        RescanTimer = 0.0
        pcall(function()
            local pawn = PC.Pawn
            if pawn and pawn:IsValid() then RescanFirstPersonRig(pawn) end
        end)
    end
end

local TickHookPath = "/Game/Blueprints/BP_MeteoritePlayerController.BP_MeteoritePlayerController_C:ReceiveTick"
local HookedTickFn = nil -- the UFunction object we hooked; dies on level unload
local TickErrorCount = 0

-- The hook is registered once per level and NEVER unregistered: tearing the
-- trampoline out of a hot per-frame function while the game thread may be
-- inside it raises STATUS_BAD_FUNCTION_TABLE (observed). When flycam is off
-- the callback is a single boolean check. A level change GCs the hooked
-- function object; we detect that and register a fresh hook on the new one.
local function EnsureTickHook()
    local fn = nil
    pcall(function() fn = StaticFindObject(TickHookPath) end)
    if not fn or not fn:IsValid() then
        Log("ERROR: " .. TickHookPath .. " not found (not in a mission?).")
        return false
    end

    if HookedTickFn and HookedTickFn:IsValid() then
        return true -- hook from this level generation is still live
    end

    local ok, pre = pcall(function()
        return RegisterHook(TickHookPath, function(self, DeltaSeconds)
            if not bEnabled then return end
            if not IsValid(OwnerController) or not IsValid(SpawnedCameraActor) then
                LoseCamera("owner or camera lost (level change?)")
                return
            end
            -- ReceiveTick is called once for EACH player controller on a
            -- host. Only the controller that owns this FlyCam may advance it.
            -- UE4SS passes a context wrapper; its UObject address is stable
            -- across different wrappers for the same controller.
            local okContext, contextAddress = pcall(function() return self:get():GetAddress() end)
            if not okContext or not contextAddress then return end
            local current = EngineLocalController()
            local currentAddress = current and Address(current)
            if currentAddress and currentAddress ~= OwnerAddress then
                LoseCamera("local controller changed (level change?)")
                return
            end
            if contextAddress ~= OwnerAddress then return end
            if not OwnerStillLocal() then
                LoseCamera("local controller could not be verified")
                return
            end
            local dt = nil
            pcall(function() dt = DeltaSeconds:get() end)
            local okTick, err = pcall(OnCameraTick, dt, OwnerController)
            if not okTick then
                TickErrorCount = TickErrorCount + 1
                if TickErrorCount >= 10 then
                    LoseCamera("repeated tick errors: " .. tostring(err))
                end
            end
        end)
    end)
    if not ok or not pre then
        Log("ERROR: could not hook " .. TickHookPath)
        return false
    end
    HookedTickFn = fn
    TickErrorCount = 0
    return true
end

local function EnableFlyCam()
    local PC = GetPlayerController()
    if not PC or not PC:IsValid() then
        Log("Cannot enable: No valid PlayerController found.")
        return
    end
    local pawn = PC.Pawn
    if not pawn or not pawn:IsValid() then
        Log("Cannot enable: no pawn (main menu?).")
        return
    end
    local pcAddress = Address(PC)
    if not pcAddress then
        Log("Cannot enable: local controller identity is unavailable.")
        return
    end

    local CamMgr = PC.PlayerCameraManager
    if CamMgr and CamMgr:IsValid() then
        local okLoc, loc = pcall(function() return CamMgr:GetCameraLocation() end)
        local okRot, rot = pcall(function() return CamMgr:GetCameraRotation() end)
        local okFov, fov = pcall(function() return CamMgr:GetFOVAngle() end)
        if okLoc and loc then CamLoc = { X = loc.X, Y = loc.Y, Z = loc.Z } end
        if okRot and rot then CamRot = { Pitch = rot.Pitch, Yaw = rot.Yaw, Roll = 0.0 } end
        if okFov and type(fov) == "number" and fov >= 5 and fov <= 170 then CamFOV = fov end
    end

    -- Reuse one camera actor per level. Destroying and respawning it on
    -- every toggle multiplies actor-lifecycle risk (the engine may still be
    -- blending from the old camera when it dies); the actor is GC'd with
    -- the level anyway.
    local okWorld, World = pcall(function() return PC:GetWorld() end)
    if not okWorld or not IsValid(World) then return end
    if IsValid(SpawnedCameraActor) then
        local worldAddress = Address(World)
        local okOldWorld, oldWorld = pcall(function() return SpawnedCameraActor:GetWorld() end)
        if not worldAddress or not okOldWorld or Address(oldWorld) ~= worldAddress then
            SpawnedCameraActor = nil
        end
    end
    if not SpawnedCameraActor or not SpawnedCameraActor:IsValid() then
        local CameraClass = StaticFindObject("/Script/Engine.CameraActor")
        if not CameraClass or not CameraClass:IsValid() then
            Log("ERROR: Could not find /Script/Engine.CameraActor class.")
            return
        end

        local okSpawn, actor = pcall(function()
            return World:SpawnActor(CameraClass,
                { X = CamLoc.X, Y = CamLoc.Y, Z = CamLoc.Z },
                { Pitch = CamRot.Pitch, Yaw = CamRot.Yaw, Roll = 0.0 })
        end)
        if not okSpawn or not actor or not actor:IsValid() then
            Log("ERROR: Failed to spawn CameraActor.")
            return
        end
        SpawnedCameraActor = actor
    end

    if not EnsureTickHook() then
        return
    end
    OwnerController, OwnerAddress = PC, pcAddress

    -- CameraActor otherwise constrains some displays to 16:9. Preserve the
    -- player's current FOV and set the transform after spawning (spawn-time
    -- rotation is not reliable in this engine build).
    pcall(function()
        local component = SpawnedCameraActor.CameraComponent
        component.bConstrainAspectRatio = false
        component.FieldOfView = CamFOV
        SpawnedCameraActor:K2_SetActorLocationAndRotation(CamLoc, CamRot, false, {}, true)
    end)

    pcall(function() PC:SetViewTargetWithBlend(SpawnedCameraActor, 0.2, 0, 0, false) end)

    SavedVisibility = {}
    RescanTimer = 0.0
    HideFirstPersonRig(pawn)

    SetHUDVisible(false)

    bEnabled = true
    Log("FlyCam ENABLED. Numpad 8/2/4/6 move, 9/3 up/down, 5 snap to player, Shift boost.")
    Log("F8 exit | F7 HUD | F9/Num0 mouse look | Num+/- speed. WASD still moves the player.")
end

local function DisableFlyCam()
    if bEnabled and not OwnerStillLocal() then
        LoseCamera("local controller changed")
        return
    end
    bEnabled = false
    Playback = nil
    local PC = OwnerController
    if PC and PC:IsValid() then
        pcall(function()
            local pawn = PC.Pawn
            if pawn and pawn:IsValid() then
                PC:SetViewTargetWithBlend(pawn, 0.2, 0, 0, false)
            end
        end)
    end

    RestoreVisibility()

    -- The camera actor is intentionally kept alive for reuse; see EnableFlyCam.

    SetHUDVisible(true)
    OwnerController, OwnerAddress = nil, nil
    Log("FlyCam DISABLED (view restored to player).")
end

local function ToggleFlyCam()
    if bEnabled then
        DisableFlyCam()
    else
        EnableFlyCam()
    end
end

local function ToggleMouseLook()
    bMouseLookEnabled = not bMouseLookEnabled
    Log("Mouse Look: " .. (bMouseLookEnabled and "ENABLED" or "DISABLED"))
end

local function AdjustSpeed(delta)
    if not bEnabled then return end
    BaseSpeed = math.max(200.0, BaseSpeed + delta)
    Log("Base FlyCam Speed: " .. tostring(BaseSpeed))
end

-- Poses are append-only records in the game's writable Saved directory; the
-- file is never evaluated as Lua. Refuse to append to a damaged file rather
-- than overwrite or silently discard a community member's earlier shots.
local function LoadPoses(quietMissing)
    if not PoseFile then return false, "LOCALAPPDATA is unavailable" end
    local f = io.open(PoseFile, "rb")
    if not f then
        if quietMissing then return true end
        return false, "pose file not found: " .. PoseFile
    end
    local text = f:read("*a")
    f:close()
    local loaded, err = Path.parse(text)
    if not loaded then return false, err end
    Poses = loaded
    return true
end

local function StorePose(name, pose)
    local line, err = Path.record(name, pose)
    if not line then return false, err end
    if not PoseFile then return false, "LOCALAPPDATA is unavailable" end
    local existing = ""
    local old = io.open(PoseFile, "rb")
    if old then existing = old:read("*a"); old:close() end
    local parsed, parseError = Path.parse(existing .. line)
    if not parsed then return false, "pose file was not changed: " .. tostring(parseError) end
    local f, openError = io.open(PoseFile, "ab")
    if not f then return false, "cannot write pose file: " .. tostring(openError) end
    local wrote, writeError = f:write(line)
    local closed, closeError = f:close()
    if not wrote or not closed then return false, "could not finish pose record: " .. tostring(writeError or closeError) end
    Poses[name] = assert(Path.pose(pose))
    return true
end

local function EnsureFlyCam()
    if bEnabled and not OwnerStillLocal() then LoseCamera("local controller changed") end
    if not bEnabled then EnableFlyCam() end
    return bEnabled and SpawnedCameraActor and SpawnedCameraActor:IsValid()
end

local function CameraHelp()
    Log("mjolnir_camera on|off|capture NAME|set NAME X Y Z PITCH YAW ROLL [FOV]")
    Log("mjolnir_camera goto NAME|play SECONDS_PER_SEGMENT linear|smooth A B [C ...]|stop|list|reload")
    Log("Pose coordinates are Unreal units/degrees; files are local to this computer.")
end

local function CameraCommand(args)
    args = type(args) == "table" and args or {}
    local offset = type(args[1]) == "string" and args[1]:lower() == "mjolnir_camera" and 1 or 0
    local words = {}
    for i = 1 + offset, #args do words[#words + 1] = tostring(args[i]) end
    local command = (words[1] or "help"):lower()
    if command == "help" then
        CameraHelp()
    elseif command == "on" then
        if not bEnabled then EnableFlyCam() else Log("FlyCam is already enabled.") end
    elseif command == "off" then
        if bEnabled then DisableFlyCam() else Playback = nil; Log("FlyCam is already disabled.") end
    elseif command == "capture" then
        local name = words[2]
        if #words ~= 2 or not Path.validName(name) then Log("Usage: mjolnir_camera capture NAME"); return end
        if not EnsureFlyCam() then Log("Could not enable FlyCam."); return end
        local ok, err = StorePose(name, CurrentPose())
        if not ok then Log("Pose not saved: " .. tostring(err)); return end
        Log("Captured pose " .. name .. " in " .. PoseFile)
    elseif command == "set" then
        if (#words ~= 8 and #words ~= 9) or not Path.validName(words[2]) then
            Log("Usage: mjolnir_camera set NAME X Y Z PITCH YAW ROLL [FOV]"); return
        end
        local pose = { X = words[3], Y = words[4], Z = words[5], Pitch = words[6],
                       Yaw = words[7], Roll = words[8], FOV = words[9] or CamFOV }
        local ok, err = StorePose(words[2], pose)
        if not ok then Log("Pose not saved: " .. tostring(err)); return end
        Log("Saved pose " .. words[2] .. " in " .. PoseFile)
    elseif command == "goto" then
        if #words ~= 2 or not Poses[words[2]] then Log("Unknown pose. Use mjolnir_camera list."); return end
        if not EnsureFlyCam() then Log("Could not enable FlyCam."); return end
        Playback = nil
        ApplyPose(Poses[words[2]])
        Log("At pose " .. words[2] .. ".")
    elseif command == "play" then
        local names = {}
        for i = 4, #words do names[#names + 1] = words[i] end
        local path, err = Path.create(Poses, names, words[2], (words[3] or ""):lower())
        if not path then Log("Camera path not started: " .. tostring(err)); return end
        if not EnsureFlyCam() then Log("Could not enable FlyCam."); return end
        Playback = path
        ApplyPose(path.frames[1])
        Log(string.format("Camera path: %d segments, %.3f seconds each, %s.",
                          #path.frames - 1, path.seconds, path.easing))
    elseif command == "stop" then
        Playback = nil
        Log("Camera path stopped; FlyCam remains at its current pose.")
    elseif command == "reload" then
        local ok, err = LoadPoses(false)
        if not ok then Log("Poses not reloaded: " .. tostring(err)); return end
        Log("Reloaded poses from " .. PoseFile)
    elseif command == "list" then
        local names = {}
        for name in pairs(Poses) do names[#names + 1] = name end
        table.sort(names)
        if #names == 0 then Log("No saved camera poses.") end
        for _, name in ipairs(names) do
            local p = Poses[name]
            Log(string.format("%s: %.3f %.3f %.3f | %.3f %.3f %.3f | FOV %.3f",
                name, p.X, p.Y, p.Z, p.Pitch, p.Yaw, p.Roll, p.FOV))
        end
        if PoseFile then Log("Pose file: " .. PoseFile) end
    else
        CameraHelp()
    end
end

-- Synchronous RegisterKeyBind: callbacks run on the game thread. The async
-- variant + ExecuteInGameThread deadlocks once the per-frame tick hook is
-- registered — the keybind thread holds the mod's Lua lock while waiting for
-- a game thread that is itself waiting for that lock to run the tick hook.
local function BindKey(key, fn)
    pcall(function()
        RegisterKeyBind(key, {}, fn)
    end)
end

local function RegisterControls()
    BindKey(Key.F8, ToggleFlyCam)
    BindKey(Key.F7, ToggleHUD)
    BindKey(Key.F9, ToggleMouseLook)
    BindKey(Key.NUM_ZERO, ToggleMouseLook)

    -- Speed: numpad +/- plus the old [ ] bindings
    BindKey(Key.ADD, function() AdjustSpeed(400.0) end)
    BindKey(Key.SUBTRACT, function() AdjustSpeed(-400.0) end)
    BindKey(Key.OEM_SIX, function() AdjustSpeed(400.0) end)
    BindKey(Key.OEM_FOUR, function() AdjustSpeed(-400.0) end)

    local ok, err = LoadPoses(true)
    if not ok then Log("Saved poses were not loaded: " .. tostring(err)) end
    if RegisterConsoleCommandHandler then
        local registered, registerError = pcall(RegisterConsoleCommandHandler, "mjolnir_camera", function(_, args, output)
            CommandOutput = output
            local success, commandError = pcall(CameraCommand, args)
            if not success then Log("Camera command failed: " .. tostring(commandError)) end
            CommandOutput = nil
            return true
        end)
        if not registered then Log("Could not register mjolnir_camera: " .. tostring(registerError)) end
    end

    Log("FlyCam Ready. Press F8 to toggle. Camera flies on the numpad (8/2/4/6, 9/3 up/down).")
end

ExecuteInGameThreadWithDelay(2000, RegisterControls)
Log("MJOLNIR FlyCam Loaded.")
