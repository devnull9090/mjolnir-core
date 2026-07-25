-- MJOLNIR FlyCam (Free Debug Camera Mod)
-- For Halo Campaign Evolved
-- Hotkeys:
--   F8 : Toggle FlyCam ON/OFF
--   I / K (or Numpad 8 / 2) : Move Forward / Backward
--   J / L (or Numpad 4 / 6) : Strafe Left / Right
--   U / O (or Numpad 9 / 7) : Move Up / Down
--   Arrow Keys : Rotate Pitch / Yaw
--   [ / ] : Decrease / Increase Camera Speed

local UEHelpers = require("UEHelpers")

local bEnabled = false
local SpawnedCameraActor = nil
local OriginalViewTarget = nil
local CurrentSpeed = 50.0

local CamLoc = { X = 0.0, Y = 0.0, Z = 0.0 }
local CamRot = { Pitch = 0.0, Yaw = 0.0, Roll = 0.0 }

local function Log(msg)
    print("[MJOLNIR FlyCam] " .. tostring(msg) .. "\n")
end

local function GetPlayerController()
    local pcs = UEHelpers.GetAllPlayerControllers()
    if pcs and #pcs > 0 then
        for _, pc in ipairs(pcs) do
            if pc and pc:IsValid() then
                return pc
            end
        end
    end
    return nil
end

local function VectorAdd(v1, v2)
    return { X = v1.X + v2.X, Y = v1.Y + v2.Y, Z = v1.Z + v2.Z }
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

local function UpdateCameraTransform()
    if not bEnabled or not SpawnedCameraActor or not SpawnedCameraActor:IsValid() then return end

    local ok, err = pcall(function()
        SpawnedCameraActor:K2_SetActorLocationAndRotation(
            { X = CamLoc.X, Y = CamLoc.Y, Z = CamLoc.Z },
            { Pitch = CamRot.Pitch, Yaw = CamRot.Yaw, Roll = CamRot.Roll },
            false,
            {},
            false
        )
    end)
    if not ok then
        -- Fallback to property assignment if method signature varies
        pcall(function()
            SpawnedCameraActor.K2_SetActorLocation({ X = CamLoc.X, Y = CamLoc.Y, Z = CamLoc.Z }, false, {}, false)
            SpawnedCameraActor.K2_SetActorRotation({ Pitch = CamRot.Pitch, Yaw = CamRot.Yaw, Roll = CamRot.Roll }, false)
        end)
    end
end

local function EnableFlyCam()
    local PC = GetPlayerController()
    if not PC or not PC:IsValid() then
        Log("Cannot enable: No valid PlayerController found.")
        return
    end

    -- Get camera manager or current view target location
    local CamMgr = PC.PlayerCameraManager
    if CamMgr and CamMgr:IsValid() then
        local okLoc, loc = pcall(function() return CamMgr:GetCameraLocation() end)
        local okRot, rot = pcall(function() return CamMgr:GetCameraRotation() end)

        if okLoc and loc then
            CamLoc = { X = loc.X, Y = loc.Y, Z = loc.Z }
        else
            CamLoc = { X = 0.0, Y = 0.0, Z = 100.0 }
        end

        if okRot and rot then
            CamRot = { Pitch = rot.Pitch, Yaw = rot.Yaw, Roll = rot.Roll }
        else
            CamRot = { Pitch = 0.0, Yaw = 0.0, Roll = 0.0 }
        end
    end

    -- Save original view target
    OriginalViewTarget = PC.TargetViewTarget and PC.TargetViewTarget.Target or nil

    -- Find CameraActor class and construct actor
    local CameraClass = StaticFindObject("/Script/Engine.CameraActor")
    if not CameraClass or not CameraClass:IsValid() then
        Log("ERROR: Could not find /Script/Engine.CameraActor class.")
        return
    end

    local World = PC:GetWorld()
    if not World or not World:IsValid() then
        Log("ERROR: Could not get World from PlayerController.")
        return
    end

    -- Spawn CameraActor
    local okSpawn, actor = pcall(function()
        return World:SpawnActor(CameraClass, { X = CamLoc.X, Y = CamLoc.Y, Z = CamLoc.Z }, { Pitch = CamRot.Pitch, Yaw = CamRot.Yaw, Roll = CamRot.Roll })
    end)

    if not okSpawn or not actor or not actor:IsValid() then
        -- Fallback to StaticConstructObject if SpawnActor is restricted
        local okConst, constActor = pcall(function()
            return StaticConstructObject(CameraClass, World)
        end)
        if okConst and constActor and constActor:IsValid() then
            actor = constActor
        end
    end

    if not actor or not actor:IsValid() then
        Log("ERROR: Failed to spawn or construct CameraActor.")
        return
    end

    SpawnedCameraActor = actor
    UpdateCameraTransform()

    -- Switch view target to our CameraActor
    pcall(function()
        PC:SetViewTargetWithBlend(SpawnedCameraActor, 0.1, 0, 0, false)
    end)

    bEnabled = true
    Log("FlyCam ENABLED! Speed: " .. tostring(CurrentSpeed))
end

local function DisableFlyCam()
    bEnabled = false
    local PC = GetPlayerController()
    if PC and PC:IsValid() and OriginalViewTarget and OriginalViewTarget:IsValid() then
        pcall(function()
            PC:SetViewTargetWithBlend(OriginalViewTarget, 0.1, 0, 0, false)
        end)
    end

    if SpawnedCameraActor and SpawnedCameraActor:IsValid() then
        pcall(function() SpawnedCameraActor:K2_DestroyActor() end)
    end
    SpawnedCameraActor = nil
    Log("FlyCam DISABLED.")
end

local function ToggleFlyCam()
    if bEnabled then
        DisableFlyCam()
    else
        EnableFlyCam()
    end
end

-- Keybindings
local function RegisterControls()
    -- F8 : Toggle FlyCam
    RegisterKeyBind(Key.F8, function()
        ExecuteInGameThread(ToggleFlyCam)
    end)

    -- Movement Keybinds
    RegisterKeyBind(Key.I, function()
        if not bEnabled then return end
        local fwd = GetForwardVector(CamRot)
        CamLoc.X = CamLoc.X + fwd.X * CurrentSpeed
        CamLoc.Y = CamLoc.Y + fwd.Y * CurrentSpeed
        CamLoc.Z = CamLoc.Z + fwd.Z * CurrentSpeed
        ExecuteInGameThread(UpdateCameraTransform)
    end)

    RegisterKeyBind(Key.K, function()
        if not bEnabled then return end
        local fwd = GetForwardVector(CamRot)
        CamLoc.X = CamLoc.X - fwd.X * CurrentSpeed
        CamLoc.Y = CamLoc.Y - fwd.Y * CurrentSpeed
        CamLoc.Z = CamLoc.Z - fwd.Z * CurrentSpeed
        ExecuteInGameThread(UpdateCameraTransform)
    end)

    RegisterKeyBind(Key.J, function()
        if not bEnabled then return end
        local right = GetRightVector(CamRot)
        CamLoc.X = CamLoc.X - right.X * CurrentSpeed
        CamLoc.Y = CamLoc.Y - right.Y * CurrentSpeed
        ExecuteInGameThread(UpdateCameraTransform)
    end)

    RegisterKeyBind(Key.L, function()
        if not bEnabled then return end
        local right = GetRightVector(CamRot)
        CamLoc.X = CamLoc.X + right.X * CurrentSpeed
        CamLoc.Y = CamLoc.Y + right.Y * CurrentSpeed
        ExecuteInGameThread(UpdateCameraTransform)
    end)

    RegisterKeyBind(Key.U, function()
        if not bEnabled then return end
        CamLoc.Z = CamLoc.Z + CurrentSpeed
        ExecuteInGameThread(UpdateCameraTransform)
    end)

    RegisterKeyBind(Key.O, function()
        if not bEnabled then return end
        CamLoc.Z = CamLoc.Z - CurrentSpeed
        ExecuteInGameThread(UpdateCameraTransform)
    end)

    -- Rotation Keybinds
    RegisterKeyBind(Key.LEFT_ARROW, function()
        if not bEnabled then return end
        CamRot.Yaw = CamRot.Yaw - 5.0
        ExecuteInGameThread(UpdateCameraTransform)
    end)

    RegisterKeyBind(Key.RIGHT_ARROW, function()
        if not bEnabled then return end
        CamRot.Yaw = CamRot.Yaw + 5.0
        ExecuteInGameThread(UpdateCameraTransform)
    end)

    RegisterKeyBind(Key.UP_ARROW, function()
        if not bEnabled then return end
        CamRot.Pitch = math.min(89.0, CamRot.Pitch + 5.0)
        ExecuteInGameThread(UpdateCameraTransform)
    end)

    RegisterKeyBind(Key.DOWN_ARROW, function()
        if not bEnabled then return end
        CamRot.Pitch = math.max(-89.0, CamRot.Pitch - 5.0)
        ExecuteInGameThread(UpdateCameraTransform)
    end)

    -- Speed Adjustment
    RegisterKeyBind(Key.LEFT_BRACKET, function()
        if not bEnabled then return end
        CurrentSpeed = math.max(5.0, CurrentSpeed - 15.0)
        Log("Speed decreased: " .. tostring(CurrentSpeed))
    end)

    RegisterKeyBind(Key.RIGHT_BRACKET, function()
        if not bEnabled then return end
        CurrentSpeed = CurrentSpeed + 15.0
        Log("Speed increased: " .. tostring(CurrentSpeed))
    end)

    Log("Keybinds registered successfully. Press F8 in-game to toggle FlyCam.")
end

ExecuteInGameThreadWithDelay(2000, RegisterControls)
Log("MJOLNIR FlyCam loaded.")
