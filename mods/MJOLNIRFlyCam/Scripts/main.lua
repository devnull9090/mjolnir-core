-- MJOLNIR FlyCam (Possession & Smooth Camera Control)
-- For Halo Campaign Evolved
-- Hotkeys:
--   F8 : Toggle FlyCam ON/OFF
--   F7 : Toggle HUD Overlay ON/OFF
--   F9 : Toggle Mouse Look ON/OFF
-- Controls:
--   W / S or I / K or Up / Down Arrows : Move Camera Forward / Backward
--   A / D or J / L or Left / Right Arrows : Strafe Camera Left / Right
--   Space / U or Numpad 9 : Move Camera Up
--   Left Ctrl / O or Numpad 7 : Move Camera Down
--   Left Shift : Boost Speed (3x)
--   Mouse : Look around continuously

local bEnabled = false
local bMouseLookEnabled = true
local bHUDVisible = true

local SpawnedCameraActor = nil
local OriginalPawn = nil
local OriginalViewTarget = nil

local BaseSpeed = 1800.0 -- units per second
local BoostMultiplier = 3.0
local MouseSensitivity = 1.8

local CamLoc = { X = 0.0, Y = 0.0, Z = 0.0 }
local CamRot = { Pitch = 0.0, Yaw = 0.0, Roll = 0.0 }

local function Log(msg)
    print("[MJOLNIR FlyCam] " .. tostring(msg) .. "\n")
end

local function GetPlayerController()
    local ok, pc = pcall(function() return FindFirstOf("PlayerController") end)
    if ok and pc and pc:IsValid() then
        return pc
    end
    local okAll, pcs = pcall(function() return FindAllOf("PlayerController") end)
    if okAll and pcs then
        for _, p in ipairs(pcs) do
            if p and p:IsValid() then return p end
        end
    end
    return nil
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

local function SetHUDVisible(visible)
    bHUDVisible = visible
    local PC = GetPlayerController()
    if not PC or not PC:IsValid() then return end

    pcall(function()
        if PC.MyHUD and PC.MyHUD:IsValid() then
            PC.MyHUD.bShowHUD = visible
            Log("HUD visibility set to: " .. tostring(visible))
        end
    end)
end

local function ToggleHUD()
    SetHUDVisible(not bHUDVisible)
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
    end)
end

-- Helper to check if a key is held down
local function IsKeyDown(PC, keyObj, keyName)
    if not PC or not PC:IsValid() then return false end

    -- Query PlayerInput directly if available
    if PC.PlayerInput and PC.PlayerInput:IsValid() then
        local okInput, pressed = pcall(function() return PC.PlayerInput:IsPressed(keyObj) end)
        if okInput and pressed then return true end
    end

    -- Query IsInputKeyDown with key object
    if keyObj then
        local ok, down = pcall(function() return PC:IsInputKeyDown(keyObj) end)
        if ok and down then return true end
    end

    -- Query IsInputKeyDown with FName
    if keyName then
        local ok, down = pcall(function() return PC:IsInputKeyDown(FName(keyName)) end)
        if ok and down then return true end
    end

    return false
end

-- Camera Update Frame Loop
local function OnCameraUpdate(DeltaTime)
    if not bEnabled then return end

    local PC = GetPlayerController()
    if not PC or not PC:IsValid() then return end

    local dt = (type(DeltaTime) == "number" and DeltaTime > 0.0005 and DeltaTime < 0.2) and DeltaTime or 0.016

    -- 1. Mouse Look Capture
    if bMouseLookEnabled then
        local deltaX, deltaY = 0.0, 0.0
        local okMouse, x, y = pcall(function() return PC:GetInputMouseDelta() end)
        if okMouse then
            if type(x) == "number" and type(y) == "number" then
                deltaX, deltaY = x, y
            elseif type(x) == "userdata" or type(x) == "table" then
                deltaX = x.X or x.x or 0.0
                deltaY = x.Y or x.y or 0.0
            end
        end

        if math.abs(deltaX) > 0.001 or math.abs(deltaY) > 0.001 then
            CamRot.Yaw = CamRot.Yaw + (deltaX * MouseSensitivity)
            CamRot.Pitch = math.max(-89.0, math.min(89.0, CamRot.Pitch - (deltaY * MouseSensitivity)))
        end
    end

    -- 2. Query Movement Keys
    local bBoost = IsKeyDown(PC, Key.LEFT_SHIFT, "LeftShift") or IsKeyDown(PC, Key.RIGHT_SHIFT, "RightShift")
    local speed = BaseSpeed * (bBoost and BoostMultiplier or 1.0) * dt

    local bForward  = IsKeyDown(PC, Key.W, "W") or IsKeyDown(PC, Key.I, "I") or IsKeyDown(PC, Key.NUM_EIGHT, "NumPadEight") or IsKeyDown(PC, Key.UP_ARROW, "Up")
    local bBackward = IsKeyDown(PC, Key.S, "S") or IsKeyDown(PC, Key.K, "K") or IsKeyDown(PC, Key.NUM_TWO, "NumPadTwo") or IsKeyDown(PC, Key.DOWN_ARROW, "Down")
    local bLeft     = IsKeyDown(PC, Key.A, "A") or IsKeyDown(PC, Key.J, "J") or IsKeyDown(PC, Key.NUM_FOUR, "NumPadFour") or IsKeyDown(PC, Key.LEFT_ARROW, "Left")
    local bRight    = IsKeyDown(PC, Key.D, "D") or IsKeyDown(PC, Key.L, "L") or IsKeyDown(PC, Key.NUM_SIX, "NumPadSix") or IsKeyDown(PC, Key.RIGHT_ARROW, "Right")
    local bUp       = IsKeyDown(PC, Key.SPACE, "SpaceBar") or IsKeyDown(PC, Key.U, "U") or IsKeyDown(PC, Key.NUM_NINE, "NumPadNine")
    local bDown     = IsKeyDown(PC, Key.LEFT_CONTROL, "LeftControl") or IsKeyDown(PC, Key.O, "O") or IsKeyDown(PC, Key.NUM_SEVEN, "NumPadSeven")

    local moveX, moveY, moveZ = 0.0, 0.0, 0.0

    if bForward then
        local fwd = GetForwardVector(CamRot)
        moveX = moveX + fwd.X * speed
        moveY = moveY + fwd.Y * speed
        moveZ = moveZ + fwd.Z * speed
    end
    if bBackward then
        local fwd = GetForwardVector(CamRot)
        moveX = moveX - fwd.X * speed
        moveY = moveY - fwd.Y * speed
        moveZ = moveZ - fwd.Z * speed
    end
    if bRight then
        local rgt = GetRightVector(CamRot)
        moveX = moveX + rgt.X * speed
        moveY = moveY + rgt.Y * speed
    end
    if bLeft then
        local rgt = GetRightVector(CamRot)
        moveX = moveX - rgt.X * speed
        moveY = moveY - rgt.Y * speed
    end
    if bUp then
        moveZ = moveZ + speed
    end
    if bDown then
        moveZ = moveZ - speed
    end

    CamLoc.X = CamLoc.X + moveX
    CamLoc.Y = CamLoc.Y + moveY
    CamLoc.Z = CamLoc.Z + moveZ

    UpdateCameraTransform()
end

local HookRegistered = false
local function RegisterCameraHook()
    if HookRegistered then return end

    pcall(function()
        RegisterHook("/Script/Engine.PlayerCameraManager:UpdateCamera", function(self, DeltaTime)
            local dt = type(DeltaTime) == "number" and DeltaTime or 0.016
            OnCameraUpdate(dt)
        end)
    end)

    HookRegistered = true
end

local function EnableFlyCam()
    local PC = GetPlayerController()
    if not PC or not PC:IsValid() then
        Log("Cannot enable: No valid PlayerController found.")
        return
    end

    local CamMgr = PC.PlayerCameraManager
    if CamMgr and CamMgr:IsValid() then
        local okLoc, loc = pcall(function() return CamMgr:GetCameraLocation() end)
        local okRot, rot = pcall(function() return CamMgr:GetCameraRotation() end)

        if okLoc and loc then CamLoc = { X = loc.X, Y = loc.Y, Z = loc.Z } end
        if okRot and rot then CamRot = { Pitch = rot.Pitch, Yaw = rot.Yaw, Roll = rot.Roll } end
    end

    OriginalViewTarget = PC.TargetViewTarget and PC.TargetViewTarget.Target or nil
    OriginalPawn = PC.Pawn

    -- Disable input on Chief's Pawn so Master Chief stays stationary
    if OriginalPawn and OriginalPawn:IsValid() then
        pcall(function() OriginalPawn:DisableInput(PC) end)
    end

    local CameraClass = StaticFindObject("/Script/Engine.CameraActor")
    if not CameraClass or not CameraClass:IsValid() then
        Log("ERROR: Could not find /Script/Engine.CameraActor class.")
        return
    end

    local World = PC:GetWorld()
    if not World or not World:IsValid() then return end

    local okSpawn, actor = pcall(function()
        return World:SpawnActor(CameraClass, { X = CamLoc.X, Y = CamLoc.Y, Z = CamLoc.Z }, { Pitch = CamRot.Pitch, Yaw = CamRot.Yaw, Roll = CamRot.Roll })
    end)

    if not okSpawn or not actor or not actor:IsValid() then
        pcall(function()
            actor = StaticConstructObject(CameraClass, World)
        end)
    end

    if not actor or not actor:IsValid() then
        Log("ERROR: Failed to spawn CameraActor.")
        return
    end

    SpawnedCameraActor = actor
    UpdateCameraTransform()

    pcall(function()
        PC:SetViewTargetWithBlend(SpawnedCameraActor, 0.1, 0, 0, false)
        -- Keep move input enabled on PC so IsInputKeyDown receives WASD
        PC.bIgnoreMoveInput = false
        PC.bIgnoreLookInput = false
    end)

    -- Hide HUD automatically when FlyCam starts
    SetHUDVisible(false)

    bEnabled = true
    Log("FlyCam ENABLED (Player Stationary). F8: FlyCam Toggle | F7: HUD Toggle | F9: Mouse Look")
end

local function DisableFlyCam()
    bEnabled = false
    local PC = GetPlayerController()
    if PC and PC:IsValid() then
        pcall(function()
            if OriginalPawn and OriginalPawn:IsValid() then
                OriginalPawn:EnableInput(PC)
            end
            if OriginalViewTarget and OriginalViewTarget:IsValid() then
                PC:SetViewTargetWithBlend(OriginalViewTarget, 0.1, 0, 0, false)
            end
        end)
    end

    if SpawnedCameraActor and SpawnedCameraActor:IsValid() then
        pcall(function() SpawnedCameraActor:K2_DestroyActor() end)
    end
    SpawnedCameraActor = nil

    -- Restore HUD
    SetHUDVisible(true)

    Log("FlyCam DISABLED (Player Restored).")
end

local function ToggleFlyCam()
    if bEnabled then
        DisableFlyCam()
    else
        EnableFlyCam()
    end
end

local function BindKey(key, fn)
    pcall(function()
        RegisterKeyBindAsync(key, {}, fn)
    end)
end

local function RegisterControls()
    RegisterCameraHook()

    -- Toggle FlyCam (F8)
    BindKey(Key.F8, function() ExecuteInGameThread(ToggleFlyCam) end)

    -- Toggle HUD (F7)
    BindKey(Key.F7, function() ExecuteInGameThread(ToggleHUD) end)

    -- Toggle Mouse Look (F9)
    BindKey(Key.F9, function()
        bMouseLookEnabled = not bMouseLookEnabled
        Log("Mouse Look: " .. (bMouseLookEnabled and "ENABLED" or "DISABLED"))
    end)

    -- Speed Adjustment Keys ([ and ])
    BindKey(Key.OEM_FOUR, function()
        if not bEnabled then return end
        BaseSpeed = math.max(200.0, BaseSpeed - 400.0)
        Log("Base FlyCam Speed: " .. tostring(BaseSpeed))
    end)

    BindKey(Key.OEM_SIX, function()
        if not bEnabled then return end
        BaseSpeed = BaseSpeed + 400.0
        Log("Base FlyCam Speed: " .. tostring(BaseSpeed))
    end)

    Log("FlyCam Ready. Press F8 to Toggle FlyCam, F7 for HUD.")
end

ExecuteInGameThreadWithDelay(2000, RegisterControls)
Log("MJOLNIR FlyCam Loaded.")
