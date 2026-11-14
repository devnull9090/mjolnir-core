-- MJOLNIR FlyCam (Detached Camera for Halo Campaign Evolved)
--
-- The player pawn in this game is a puppet of the original Blam simulation,
-- which reads its own copy of the keyboard and mouse. Nothing at the Unreal
-- layer stops it, so the native half (native/flycam, mjolnir_flycam.dll)
-- blanks the simulation's input while FlyCam is on: the player stands still
-- and WASD and the mouse fly the camera instead, read from Unreal's own
-- PlayerInput, which is a separate copy. Without the DLL, FlyCam still works
-- but WASD moves the player too; the numpad then flies the camera alone.
--
-- Hotkeys (README.md has the full list):
--   F8 : FlyCam on/off          F7 : HUD on/off       F9 / Numpad 0 : mouse look
--   F6 : pin the shot list      Tab (hold) : show the shot list
-- While FlyCam is on:
--   W/A/S/D (or numpad 8/4/2/6) fly where you look and strafe
--   Space / E (numpad 9) up, C / Q (numpad 3) down
--   Shift boost, Left Alt slow, mouse wheel or Numpad +/- (] / [) speed
--   Z / X zoom in / out (field of view), R resets FOV to 90 and roll to 0
--   1-9, 0 : jump to shot 1-10    Ctrl + 1-9, 0 : save the view as shot 1-10
--   Numpad 5 : snap to the player
--   mjolnir_camera : shots, poses and paths from the console (README.md)
--
-- The first-person rig (arms + gun) is hidden so it stops floating in front
-- of the lens; the game's own shadow-proxy body doubles as the external
-- player model (`mjolnir_camera body hide` hides it for clean shots).

local bEnabled = false
local bMouseLookEnabled = true
local bHUDVisible = true

local scriptPath = (debug.getinfo(1, "S").source or ""):gsub("^@", "")
local scriptDirectory = scriptPath:match("^(.*)[\\/][^\\/]+$") or "."
local modDirectory = scriptDirectory:match("^(.*)[\\/]Scripts$") or scriptDirectory
local Path = dofile(scriptDirectory .. "\\camera_path.lua")
local Json = dofile(scriptDirectory .. "\\json.lua")
local Shots = dofile(scriptDirectory .. "\\shots.lua").init(Json)
local Flight = dofile(scriptDirectory .. "\\flight.lua")
local localAppData = os.getenv("LOCALAPPDATA")
local SavedDirectory = localAppData and (localAppData .. "\\Meteorite\\Saved\\") or nil
local PoseFile = SavedDirectory and (SavedDirectory .. "MJOLNIR_FlyCam_poses.txt") or nil
local Poses = {}
local Playback = nil

local SpawnedCameraActor = nil
local OwnerController = nil
local OwnerAddress = nil
local Engine = nil

local Speed = Flight.DEFAULT_SPEED -- cm/s before boost/slow
local MouseSensitivity = 2.0
local ZoomRate = 0.9               -- FOV changes by e^(rate) per second held
local FlightState = Flight.new()

local CamLoc = { X = 0.0, Y = 0.0, Z = 0.0 }
local CamRot = { Pitch = 0.0, Yaw = 0.0, Roll = 0.0 }
local CamFOV = 90.0

-- Visibility bookkeeping: exact prior state, restored on disable.
local SavedVisibility = {}   -- { {comp=<obj>, visible=<bool>} }
local SavedBody = {}         -- the third-person body, hidden by `body hide`
local SavedHudWidgets = {}   -- { {widget=<obj>, visibility=<int>} }
local bBodyHidden = false
local CommandOutput = nil

local function Log(msg)
    print("[MJOLNIR FlyCam] " .. tostring(msg) .. "\n")
    if CommandOutput then pcall(function() CommandOutput:Log("MJOLNIR FlyCam: " .. tostring(msg)) end) end
end

local function IsValid(obj)
    local ok, valid = pcall(function() return obj and obj:IsValid() end)
    return ok and valid == true
end

--------------------------------------------------------------------------------
-- Input lock (native half)
--------------------------------------------------------------------------------

local Lock = {
    dll = modDirectory .. "\\native\\mjolnir_flycam.dll",
    statusFile = modDirectory .. "\\native\\flycam_status.txt",
    lockFn = nil, unlockFn = nil, beatFn = nil,
    state = "not loaded",
    locked = false,
}

local function ReadStatus()
    local f = io.open(Lock.statusFile, "rb")
    if not f then return "no status" end
    local s = f:read("*l") or "no status"
    f:close()
    return s
end

function Lock.load()
    if not (package and package.loadlib) then Lock.state = "this Lua has no package.loadlib"; return end
    local f = io.open(Lock.dll, "rb")
    if not f then Lock.state = "mjolnir_flycam.dll is not installed"; return end
    f:close()
    local l, err = package.loadlib(Lock.dll, "mjolnir_flycam_lock")
    local u, err2 = package.loadlib(Lock.dll, "mjolnir_flycam_unlock")
    if not l or not u then Lock.state = "could not load the DLL: " .. tostring(err or err2); return end
    Lock.lockFn, Lock.unlockFn = l, u
    -- Older DLLs have no beat; with one, the lock lapses if FlyCam's tick stops.
    Lock.beatFn = package.loadlib(Lock.dll, "mjolnir_flycam_beat") or nil
    -- The DLL outlives a Lua reload; a reload must never leave the player frozen.
    pcall(u)
    Lock.state = "ready"
end

function Lock.set(on)
    local fn = on and Lock.lockFn or Lock.unlockFn
    if not fn then Lock.locked = false; return false end
    local ok, err = pcall(fn)
    Lock.state = ok and ReadStatus() or ("call failed: " .. tostring(err))
    Lock.locked = on and Lock.state:match("^ok locked") ~= nil
    return Lock.locked
end

--------------------------------------------------------------------------------
-- Player controller and ownership
--------------------------------------------------------------------------------

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

local function AnyDown(PC, names)
    for _, name in ipairs(names) do
        if IsDown(PC, name) then return true end
    end
    return false
end

local function JustPressed(PC, keyName)
    local ok, pressed = pcall(function() return PC:WasInputKeyJustPressed(FKeyOf(keyName)) end)
    return ok and pressed == true
end

-- Edge detection from Unreal's own key state, so keys typed into the console
-- or a text box (which Unreal's PlayerInput never sees) do nothing here.
local KeyWasDown = {}
local function Pressed(PC, keyName)
    local down = IsDown(PC, keyName)
    local was = KeyWasDown[keyName]
    KeyWasDown[keyName] = down
    return down and not was
end

--------------------------------------------------------------------------------
-- Visibility: first-person rig, body, HUD
--------------------------------------------------------------------------------

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
-- actors) — but NOT the Shadow proxies unless the body is hidden too. This
-- game is first-person only and has no separate third-person model: the
-- bOwnerNoSee "shadow" meshes (BPC_FP_ShadowSkeletalMesh full body,
-- BPC_FP_ShadowStaticMesh gun) are the only complete external body, and the
-- engine already shows them when the view target is not the pawn.
-- (BPC_PAWN_SkeletalMesh is just the owner-view lower body — the legs you
-- see looking down in first person — so leave its bOnlyOwnerSee alone.)
local function HideFirstPersonRig(pawn)
    ForEachPawnAndWeaponActor(pawn, function(actor)
        ForEachPrimitiveComponent(actor, function(c)
            if not c:IsValid() then return end
            local cn = c:GetClass():GetFName():ToString()
            local n = c:GetFName():ToString()
            local shadow = cn:find("Shadow") or n:find("Shadow")
            if (cn:find("FP_") or n:find("FP_")) and c:IsVisible() then
                if not shadow then
                    SavedVisibility[#SavedVisibility + 1] = { comp = c, visible = true }
                    c:SetVisibility(false, false)
                elseif bBodyHidden then
                    SavedBody[#SavedBody + 1] = { comp = c, visible = true }
                    c:SetVisibility(false, false)
                end
            end
        end)
    end)
end

local function RestoreList(list)
    for _, entry in ipairs(list) do
        pcall(function()
            if entry.comp:IsValid() then entry.comp:SetVisibility(entry.visible, false) end
        end)
    end
end

local function RestoreVisibility()
    RestoreList(SavedVisibility)
    RestoreList(SavedBody)
    SavedVisibility, SavedBody = {}, {}
end

local ESlateVisibility_Collapsed = 1
local ESlateVisibility_HitTestInvisible = 3

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

--------------------------------------------------------------------------------
-- Map code and shots file
--------------------------------------------------------------------------------

local MapOverride = nil
local MapCache = { world = nil, code = nil } -- FindAllOf is a full object scan: once per world

--- The running map's code: the scenario tag's codename ("ZAN" from
--- .../ZAN-scenario), else the world's name. Shots files are keyed by it, so
--- the same shots load on every build of a map.
local function ScanMapCode()
    local ok, assets = pcall(function() return FindAllOf("BlamScenarioTagDataAsset") end)
    if ok and type(assets) == "table" then
        for _, a in ipairs(assets) do
            local okn, name = pcall(function() return a:GetFullName() end)
            if okn and type(name) == "string" then
                local code = name:match("([%w_]+)%-scenario%.[%w_]+%-scenario$")
                if code then return string.upper(code), true end
            end
        end
    end
    local pc = GetPlayerController()
    local okWorld, world = pcall(function() return pc:GetWorld():GetFName():ToString() end)
    if okWorld and type(world) == "string" and Shots.validMap(world) then return world end
    return nil
end

local function MapCode()
    if MapOverride then return MapOverride end
    local pc = IsValid(OwnerController) and OwnerController or GetPlayerController()
    local okWorld, world = pcall(function() return pc:GetWorld() end)
    local address = okWorld and Address(world) or nil
    if address and MapCache.world == address and MapCache.code then return MapCache.code end
    local code, fromScenario = ScanMapCode()
    -- A world name may be the stand-in before the scenario tag loads: scan again.
    MapCache.world, MapCache.code = address, fromScenario and code or nil
    return code
end

local function ShotsFile(code)
    if not SavedDirectory or not code then return nil end
    return SavedDirectory .. "MJOLNIR_FlyCam_shots_" .. code .. ".json"
end

--- The map's shots, read fresh every time so edits by hand or by a tool
--- count. Returns data, code, path or nil, why.
local function LoadShots()
    local code = MapCode()
    if not code then return nil, "no map is loaded (or its code is unknown; use mjolnir_camera map CODE)" end
    local path = ShotsFile(code)
    if not path then return nil, "LOCALAPPDATA is unavailable" end
    local text = ""
    local f = io.open(path, "rb")
    if f then text = f:read("*a") or ""; f:close() end
    local data, err = Shots.decode(text, code)
    if not data then return nil, path .. " is invalid (" .. tostring(err) .. "); fix or move it" end
    data.map = code
    return data, code, path
end

--- Whole file or nothing: write beside, then swap in.
local function SaveShots(data, path)
    local temporary = path .. ".tmp"
    local f, err = io.open(temporary, "wb")
    if not f then return false, "cannot write " .. temporary .. ": " .. tostring(err) end
    local wrote, writeError = f:write(Shots.encode(data))
    local closed, closeError = f:close()
    if not wrote or not closed then
        os.remove(temporary)
        return false, "could not finish " .. temporary .. ": " .. tostring(writeError or closeError)
    end
    os.remove(path)
    local moved, moveError = os.rename(temporary, path)
    if not moved then return false, "could not replace " .. path .. ": " .. tostring(moveError) end
    return true
end

--------------------------------------------------------------------------------
-- Overlay: shot list and camera coordinates, never in a shot by default
--------------------------------------------------------------------------------

local Overlay = { widget = nil, text = nil, pinned = false, shown = false, timer = 0, lines = nil, listTimer = 0 }
local OVERLAY_X, OVERLAY_Y, OVERLAY_SCALE = 40, 120, 1.0

local function OverlayWidget()
    local w, t = Overlay.widget, Overlay.text
    if IsValid(w) and IsValid(t) then
        local okIn, inViewport = pcall(function() return w:IsInViewport() end)
        if okIn and not inViewport then
            pcall(function()
                w:AddToViewport(1001)
                w:SetPositionInViewport({ X = OVERLAY_X, Y = OVERLAY_Y }, false)
            end)
        end
        return w, t
    end
    w, t = nil, nil
    local pc = IsValid(OwnerController) and OwnerController or GetPlayerController()
    if not pc then return nil end
    local built = pcall(function()
        local library = StaticFindObject("/Script/UMG.Default__WidgetBlueprintLibrary")
        local widgetClass = StaticFindObject("/Script/UMG.UserWidget")
        local textClass = StaticFindObject("/Script/UMG.TextBlock")
        w = library:Create(pc, widgetClass, pc)
        local tree = w.WidgetTree
        t = StaticConstructObject(textClass, tree, FName("MJOLNIRFlyCamText"))
        tree.RootWidget = t
        t:SetColorAndOpacity({ SpecifiedColor = { R = 0.55, G = 0.95, B = 1.0, A = 1 }, ColorUseRule = 0 })
        t:SetShadowOffset({ X = 1.5, Y = 1.5 })
        t:SetShadowColorAndOpacity({ R = 0, G = 0, B = 0, A = 0.95 })
        t:SetRenderTransformPivot({ X = 0, Y = 0 })
        t:SetRenderScale({ X = OVERLAY_SCALE, Y = OVERLAY_SCALE })
        w:SetVisibility(ESlateVisibility_Collapsed)
        w:AddToViewport(1001)
        w:SetPositionInViewport({ X = OVERLAY_X, Y = OVERLAY_Y }, false)
    end)
    if not built or not IsValid(w) then return nil end
    Overlay.widget, Overlay.text = w, t
    return w, t
end

-- Hidden, never removed: RemoveFromParent has hung this game.
local function OverlayHide()
    if Overlay.shown and IsValid(Overlay.widget) then
        pcall(function() Overlay.widget:SetVisibility(ESlateVisibility_Collapsed) end)
    end
    Overlay.shown = false
end

local function OverlayText()
    local lines = {}
    lines[#lines + 1] = string.format("FLYCAM  %s   speed %d cm/s   fov %.1f   %s",
        tostring(MapCode() or "?"), math.floor(Speed + 0.5), CamFOV,
        Lock.locked and "player locked" or "PLAYER NOT LOCKED (" .. Lock.state .. ")")
    lines[#lines + 1] = string.format("cam  %.1f  %.1f  %.1f    pitch %.1f  yaw %.1f  roll %.1f",
        CamLoc.X, CamLoc.Y, CamLoc.Z, CamRot.Pitch, CamRot.Yaw, CamRot.Roll)
    lines[#lines + 1] = "1-0 go to shot 1-10   Ctrl+1-0 save   Z/X zoom   R reset fov   F6 pin list"
    if not Overlay.lines or Overlay.listTimer <= 0 then
        Overlay.listTimer = 1.0
        local data, err = LoadShots()
        Overlay.lines = {}
        if not data then
            Overlay.lines[1] = "shots: " .. tostring(err)
        elseif #data.shots == 0 then
            Overlay.lines[1] = "no shots saved for this map"
        else
            for _, s in ipairs(data.shots) do Overlay.lines[#Overlay.lines + 1] = Shots.describe(s) end
        end
    end
    lines[#lines + 1] = ""
    for _, l in ipairs(Overlay.lines) do lines[#lines + 1] = l end
    return table.concat(lines, "\n")
end

local function OverlayTick(dt, PC)
    local want = bEnabled and (Overlay.pinned or IsDown(PC, "Tab"))
    if not want then OverlayHide(); Overlay.lines = nil; return end
    Overlay.listTimer = Overlay.listTimer - dt
    Overlay.timer = Overlay.timer - dt
    if Overlay.shown and Overlay.timer > 0 then return end
    Overlay.timer = 0.1
    local w, t = OverlayWidget()
    if not w then return end
    pcall(function()
        t:SetText(FText(OverlayText()))
        if not Overlay.shown then w:SetVisibility(ESlateVisibility_HitTestInvisible) end
    end)
    Overlay.shown = true
end

--------------------------------------------------------------------------------
-- Camera state
--------------------------------------------------------------------------------

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
    Lock.set(false)
    OverlayHide()
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
    Overlay.widget, Overlay.text = nil, nil
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

-- A jump, not a move: motion blur and temporal AA must not smear the old view
-- into the first frames at the new one.
local function CameraCut()
    local pc = OwnerController
    if not IsValid(pc) then return end
    pcall(function() pc.PlayerCameraManager:SetGameCameraCutThisFrame() end)
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

local function ShotPose(s)
    return { X = s.x, Y = s.y, Z = s.z, Pitch = s.pitch, Yaw = s.yaw, Roll = s.roll, FOV = s.fov }
end

local function PoseShot(p)
    return { x = p.X, y = p.Y, z = p.Z, pitch = p.Pitch, yaw = p.Yaw, roll = p.Roll, fov = p.FOV }
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

local function SaveShot(n, name)
    local data, code, path = LoadShots()
    if not data then return false, code end
    local shot, err = Shots.put(data, PoseShot(CurrentPose()), n, name)
    if not shot then return false, err end
    local ok, saveError = SaveShots(data, path)
    if not ok then return false, saveError end
    Overlay.lines = nil
    return true, shot, path
end

local GotoShot -- defined after EnsureFlyCam

--------------------------------------------------------------------------------
-- Per-tick update
--------------------------------------------------------------------------------

-- Driven by a RegisterHook on the game's own PlayerController ReceiveTick
-- (game thread, once per frame). Two approaches that do NOT work here:
--   * RegisterHook on PlayerCameraManager:UpdateCamera — not a UFunction,
--     registration fails silently and the camera never moves.
--   * LoopAsync(16ms) + ExecuteInGameThread per tick — the cross-thread
--     task churn crashes UE4SS within seconds (access violation in the
--     Lua marshaling layer).
local RescanInterval = 2.0
local RescanTimer = 0.0

local DIGITS = { "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine", "Zero" }
local KEYS_FORWARD = { "W", "NumPadEight" }
local KEYS_BACK = { "S", "NumPadTwo" }
local KEYS_LEFT = { "A", "NumPadFour" }
local KEYS_RIGHT = { "D", "NumPadSix" }
local KEYS_UP = { "SpaceBar", "E", "NumPadNine" }
-- Not Left Ctrl: it is the save modifier, and sinking while saving would save
-- a different view from the one framed.
local KEYS_DOWN = { "C", "Q", "NumPadThree" }

local function AdjustSpeed(factor)
    Speed = Flight.clampSpeed(Speed * factor)
end

local function ManualTick(dt, PC)
    -- Mouse look, slower when zoomed in so aim stays precise.
    if bMouseLookEnabled then
        pcall(function()
            local d, d2 = {}, {}
            PC:GetInputMouseDelta(d, d2)
            local dx = d.DeltaX or 0.0
            local dy = d.DeltaY or 0.0
            if math.abs(dx) > 0.001 or math.abs(dy) > 0.001 then
                local s = MouseSensitivity * (CamFOV / 90.0)
                CamRot.Yaw = CamRot.Yaw + dx * s
                CamRot.Pitch = CamRot.Pitch + dy * s
                Flight.normalizeRot(CamRot)
            end
        end)
    end

    local ctrl = IsDown(PC, "LeftControl") or IsDown(PC, "RightControl")

    -- Shots: 1-0 jump, Ctrl+1-0 save.
    for i, key in ipairs(DIGITS) do
        if Pressed(PC, key) then
            if ctrl then
                local ok, shot, path = SaveShot(i, nil)
                if ok then Log("Saved shot " .. shot.n .. " in " .. path) else Log("Shot not saved: " .. tostring(shot)) end
            else
                GotoShot(tostring(i), false)
            end
            return
        end
    end

    -- Speed: wheel or +/-.
    if JustPressed(PC, "MouseScrollUp") then AdjustSpeed(1.25) end
    if JustPressed(PC, "MouseScrollDown") then AdjustSpeed(1 / 1.25) end

    -- Field of view.
    if IsDown(PC, "Z") then CamFOV = Flight.clampFov(CamFOV * math.exp(-ZoomRate * dt)) end
    if IsDown(PC, "X") then CamFOV = Flight.clampFov(CamFOV * math.exp(ZoomRate * dt)) end
    if Pressed(PC, "R") then CamFOV, CamRot.Roll = 90.0, 0.0 end

    if Pressed(PC, "NumPadFive") then
        SnapToPlayer(PC)
        Flight.stop(FlightState)
    else
        local axes = {
            fwd = (AnyDown(PC, KEYS_FORWARD) and 1 or 0) - (AnyDown(PC, KEYS_BACK) and 1 or 0),
            right = (AnyDown(PC, KEYS_RIGHT) and 1 or 0) - (AnyDown(PC, KEYS_LEFT) and 1 or 0),
            up =(AnyDown(PC, KEYS_UP) and 1 or 0) - (AnyDown(PC, KEYS_DOWN) and 1 or 0),
        }
        local speed = Speed
        if IsDown(PC, "LeftShift") or IsDown(PC, "RightShift") then speed = speed * Flight.BOOST end
        if IsDown(PC, "LeftAlt") then speed = speed * Flight.SLOW end
        local move = Flight.step(FlightState, CamRot, axes, speed, dt)
        CamLoc.X = CamLoc.X + move.X
        CamLoc.Y = CamLoc.Y + move.Y
        CamLoc.Z = CamLoc.Z + move.Z
    end

    UpdateCameraTransform()
end

local function OnCameraTick(dt, PC)
    if not bEnabled then return end
    if Lock.locked and Lock.beatFn then pcall(Lock.beatFn) end

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
        ManualTick(dt, PC)
    end

    OverlayTick(dt, PC)

    -- Re-hide FP meshes that respawned (weapon swap etc.) every couple seconds.
    RescanTimer = RescanTimer + dt
    if RescanTimer >= RescanInterval then
        RescanTimer = 0.0
        pcall(function()
            local pawn = PC.Pawn
            if pawn and pawn:IsValid() then HideFirstPersonRig(pawn) end
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

local function EnableFlyCam(blend)
    blend = blend or 0.2
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

    pcall(function() PC:SetViewTargetWithBlend(SpawnedCameraActor, blend, 0, 0, false) end)

    SavedVisibility, SavedBody = {}, {}
    RescanTimer = 0.0
    KeyWasDown = {}
    Flight.stop(FlightState)
    HideFirstPersonRig(pawn)

    SetHUDVisible(false)

    bEnabled = true
    if Lock.set(true) then
        Log("FlyCam ENABLED, player locked. WASD fly, Space/E up, C/Q down, Shift boost, Alt slow.")
    else
        Log("FlyCam ENABLED, player NOT locked (" .. Lock.state .. "): WASD moves the player too; fly on the numpad.")
    end
    Log("Z/X zoom, R reset FOV, wheel speed, 1-0 go to shot, Ctrl+1-0 save shot, Tab/F6 shot list, F8 exit.")
end

local function DisableFlyCam()
    if bEnabled and not OwnerStillLocal() then
        LoseCamera("local controller changed")
        return
    end
    bEnabled = false
    Playback = nil
    Lock.set(false)
    OverlayHide()
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

local function ToggleOverlayPin()
    Overlay.pinned = not Overlay.pinned
    if not Overlay.pinned then OverlayHide() end
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

local function EnsureFlyCam(blend)
    if bEnabled and not OwnerStillLocal() then LoseCamera("local controller changed") end
    if not bEnabled then EnableFlyCam(blend) end
    return bEnabled and SpawnedCameraActor and SpawnedCameraActor:IsValid()
end

--- Jump to a shot. fromConsole: a scripted capture, so the list goes away.
GotoShot = function(ref, fromConsole)
    local data, err = LoadShots()
    if not data then Log("Shots not read: " .. tostring(err)); return false end
    local shot = Shots.find(data, ref)
    if not shot then Log("No shot " .. tostring(ref) .. " on " .. data.map .. ". Use mjolnir_camera shots."); return false end
    if not EnsureFlyCam(0) then Log("Could not enable FlyCam."); return false end
    Playback = nil
    Flight.stop(FlightState)
    if fromConsole then Overlay.pinned = false; OverlayHide() end
    ApplyPose(ShotPose(shot))
    CameraCut()
    Log(string.format("At shot %d%s on %s.", shot.n, shot.name and (" (" .. shot.name .. ")") or "", data.map))
    return true
end

--- Pose lookup for `play`: saved shots by number or name, then named poses.
local function PlayLookup(words)
    local lookup, names = {}, {}
    local data = LoadShots()
    for i, word in ipairs(words) do
        local shot = data and Shots.find(data, word)
        if shot then
            local key = "shot" .. shot.n
            lookup[key] = ShotPose(shot)
            names[i] = key
        else
            lookup[word] = Poses[word]
            names[i] = word
        end
    end
    return lookup, names
end

local function CameraHelp()
    Log("mjolnir_camera on|off|where|help")
    Log("  shots | save [N] [NAME] | go N|NAME | delete N|NAME | map [CODE|auto]")
    Log("  fov DEG | speed CM_PER_S | move FWD RIGHT UP | look DYAW DPITCH | pos X Y Z | rot PITCH YAW ROLL")
    Log("  body hide|show | overlay on|off | lock")
    Log("  capture NAME | set NAME X Y Z PITCH YAW ROLL [FOV] | goto NAME | list | reload")
    Log("  play SECONDS_PER_SEGMENT linear|smooth A B [C ...] (shot numbers/names or poses) | stop")
    Log("Shots: one JSON file per map in " .. tostring(SavedDirectory) .. "MJOLNIR_FlyCam_shots_<MAP>.json")
end

local function NeedNumbers(words, first, count)
    local values = {}
    for i = first, first + count - 1 do
        local v = tonumber(words[i])
        if not v or v ~= v or v == math.huge or v == -math.huge then return nil end
        values[#values + 1] = v
    end
    return values
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
    elseif command == "where" then
        Log(string.format("%s cam %.4f %.4f %.4f | %.4f %.4f %.4f | FOV %.4f | speed %.0f | %s | %s",
            tostring(MapCode()), CamLoc.X, CamLoc.Y, CamLoc.Z, CamRot.Pitch, CamRot.Yaw, CamRot.Roll, CamFOV,
            Speed, bEnabled and "enabled" or "disabled", Lock.locked and "player locked" or ("not locked: " .. Lock.state)))
    elseif command == "shots" then
        local data, err, path = LoadShots()
        if not data then Log("Shots not read: " .. tostring(err)); return end
        if #data.shots == 0 then Log("No shots saved for " .. data.map .. ".") end
        for _, s in ipairs(data.shots) do Log(Shots.describe(s)) end
        Log("Shots file: " .. tostring(path))
    elseif command == "save" then
        local n, name
        if words[2] and tonumber(words[2]) then n, name = tonumber(words[2]), words[3] else name = words[2] end
        if #words > 3 or (n == nil and #words > 2) then Log("Usage: mjolnir_camera save [N] [NAME]"); return end
        if not EnsureFlyCam() then Log("Could not enable FlyCam."); return end
        local ok, shot, path = SaveShot(n, name)
        if not ok then Log("Shot not saved: " .. tostring(shot)); return end
        Log("Saved shot " .. Shots.describe(shot) .. " in " .. path)
    elseif command == "go" then
        if #words ~= 2 then Log("Usage: mjolnir_camera go N|NAME"); return end
        GotoShot(words[2], true)
    elseif command == "delete" then
        if #words ~= 2 then Log("Usage: mjolnir_camera delete N|NAME"); return end
        local data, err, path = LoadShots()
        if not data then Log("Shots not read: " .. tostring(err)); return end
        local shot = Shots.remove(data, words[2])
        if not shot then Log("No shot " .. words[2] .. " on " .. data.map .. "."); return end
        local ok, saveError = SaveShots(data, path)
        if not ok then Log("Shot not deleted: " .. tostring(saveError)); return end
        Overlay.lines = nil
        Log("Deleted shot " .. Shots.describe(shot))
    elseif command == "map" then
        if words[2] then
            if words[2]:lower() == "auto" then MapOverride = nil
            elseif Shots.validMap(words[2]) then MapOverride = words[2]:upper()
            else Log("Map codes use letters, digits, _ or -."); return end
        end
        Log("Map: " .. tostring(MapCode()) .. (MapOverride and " (set by hand; map auto undoes it)" or ""))
        Overlay.lines = nil
    elseif command == "fov" then
        local v = NeedNumbers(words, 2, 1)
        if not v or #words ~= 2 then Log("Usage: mjolnir_camera fov DEGREES (5-170)"); return end
        if not EnsureFlyCam() then return end
        CamFOV = Flight.clampFov(v[1]); UpdateCameraTransform()
        Log(string.format("FOV %.4f", CamFOV))
    elseif command == "speed" then
        local v = NeedNumbers(words, 2, 1)
        if not v or #words ~= 2 then Log("Usage: mjolnir_camera speed CM_PER_SECOND"); return end
        Speed = Flight.clampSpeed(v[1])
        Log(string.format("Speed %.0f cm/s", Speed))
    elseif command == "move" then
        local v = NeedNumbers(words, 2, 3)
        if not v or #words ~= 4 then Log("Usage: mjolnir_camera move FORWARD RIGHT UP (cm, camera-relative)"); return end
        if not EnsureFlyCam() then return end
        local d = Flight.offset(CamRot, v[1], v[2], v[3])
        CamLoc.X, CamLoc.Y, CamLoc.Z = CamLoc.X + d.X, CamLoc.Y + d.Y, CamLoc.Z + d.Z
        UpdateCameraTransform(); CameraCut()
        Log(string.format("cam %.4f %.4f %.4f", CamLoc.X, CamLoc.Y, CamLoc.Z))
    elseif command == "look" then
        local v = NeedNumbers(words, 2, 2)
        if not v or #words ~= 3 then Log("Usage: mjolnir_camera look DYAW DPITCH (degrees)"); return end
        if not EnsureFlyCam() then return end
        CamRot.Yaw, CamRot.Pitch = CamRot.Yaw + v[1], CamRot.Pitch + v[2]
        Flight.normalizeRot(CamRot); UpdateCameraTransform(); CameraCut()
        Log(string.format("pitch %.4f yaw %.4f", CamRot.Pitch, CamRot.Yaw))
    elseif command == "pos" then
        local v = NeedNumbers(words, 2, 3)
        if not v or #words ~= 4 then Log("Usage: mjolnir_camera pos X Y Z (Unreal cm)"); return end
        if not EnsureFlyCam(0) then return end
        CamLoc = { X = v[1], Y = v[2], Z = v[3] }; UpdateCameraTransform(); CameraCut()
    elseif command == "rot" then
        local v = NeedNumbers(words, 2, 3)
        if not v or #words ~= 4 then Log("Usage: mjolnir_camera rot PITCH YAW ROLL"); return end
        if not EnsureFlyCam(0) then return end
        CamRot = { Pitch = v[1], Yaw = v[2], Roll = v[3] }; Flight.normalizeRot(CamRot)
        UpdateCameraTransform(); CameraCut()
    elseif command == "body" then
        local mode = (words[2] or ""):lower()
        if mode ~= "hide" and mode ~= "show" then Log("Usage: mjolnir_camera body hide|show"); return end
        bBodyHidden = mode == "hide"
        if not bBodyHidden then RestoreList(SavedBody); SavedBody = {} end
        if bEnabled and IsValid(OwnerController) then
            pcall(function() HideFirstPersonRig(OwnerController.Pawn) end)
        end
        Log("Player body " .. (bBodyHidden and "hidden" or "shown") .. " while FlyCam is on.")
    elseif command == "overlay" then
        local mode = (words[2] or ""):lower()
        if mode ~= "on" and mode ~= "off" then Log("Usage: mjolnir_camera overlay on|off"); return end
        Overlay.pinned = mode == "on"
        if not Overlay.pinned then OverlayHide() end
    elseif command == "lock" then
        Log("Input lock: " .. (Lock.locked and "on" or "off") .. " (" .. Lock.state .. ")")
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
        if not EnsureFlyCam(0) then Log("Could not enable FlyCam."); return end
        Playback = nil
        ApplyPose(Poses[words[2]])
        CameraCut()
        Log("At pose " .. words[2] .. ".")
    elseif command == "play" then
        local refs = {}
        for i = 4, #words do refs[#refs + 1] = words[i] end
        local lookup, names = PlayLookup(refs)
        local path, err = Path.create(lookup, names, words[2], (words[3] or ""):lower())
        if not path then Log("Camera path not started: " .. tostring(err)); return end
        if not EnsureFlyCam(0) then Log("Could not enable FlyCam."); return end
        Playback = path
        ApplyPose(path.frames[1])
        CameraCut()
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
    BindKey(Key.F6, ToggleOverlayPin)
    BindKey(Key.F9, ToggleMouseLook)
    BindKey(Key.NUM_ZERO, ToggleMouseLook)

    -- Speed: numpad +/- plus the old [ ] bindings (the wheel is read per tick)
    BindKey(Key.ADD, function() if bEnabled then AdjustSpeed(1.25) end end)
    BindKey(Key.SUBTRACT, function() if bEnabled then AdjustSpeed(1 / 1.25) end end)
    BindKey(Key.OEM_SIX, function() if bEnabled then AdjustSpeed(1.25) end end)
    BindKey(Key.OEM_FOUR, function() if bEnabled then AdjustSpeed(1 / 1.25) end end)

    Lock.load()
    if Lock.state ~= "ready" then Log("Input lock unavailable: " .. Lock.state) end

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

    Log("FlyCam Ready. Press F8 to toggle; WASD + mouse fly it, Tab shows saved shots.")
end

ExecuteInGameThreadWithDelay(2000, RegisterControls)
Log("MJOLNIR FlyCam Loaded.")
