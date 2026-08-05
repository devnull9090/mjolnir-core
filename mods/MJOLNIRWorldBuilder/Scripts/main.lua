-- MJOLNIR World Builder
--
-- Furnishes a custom world after it has loaded. A world cooked in stock UE 5.5
-- loads in this game, but some of its cooked *components* do not: 343's engine
-- build deserializes UCapsuleComponent and UDirectionalLightComponent
-- differently, and a package carrying either dies during load with
--
--   DirectionalLightComponent ... Serial size mismatch: Expected 67, Actual 21
--
-- (see docs/multiplayer_investigation_notes.md). Actors spawned in-process are
-- built from the game's own class layouts, so they sidestep that entirely.
-- Hence the division of labour: the cook ships what it can, this mod adds what
-- it cannot.
--
-- Overriding a campaign scenario's world also removes that world's sun, sky and
-- fog, so a custom world starts unlit and renders black no matter what geometry
-- is present. Lighting is therefore the mod's first job, not a nicety.
--
-- Commands:
--   mjolnir_world_probe          report what is actually in the loaded world
--   mjolnir_world_build [size_m] light the world and lay a floor under the pawn
--   mjolnir_world_light          lighting only
--   mjolnir_world_floor [size_m] floor only
--
-- Everything is idempotent: each command reuses what it already spawned.

local BASIC_CUBE = "/Engine/BasicShapes/Cube.Cube"

-- EComponentMobility: Static = 0, Stationary = 1, Movable = 2.
local MOBILITY_MOVABLE = 2

local DEFAULT_FLOOR_M = 100.0

-- How far below the pawn the floor's top surface is laid. A short drop is
-- deliberate: it lands the player *on* the slab and makes contact obvious,
-- where spawning flush risks starting interpenetrated and being pushed out.
local FLOOR_DROP = 120.0

local Spawned = {
    floor = nil,
    sun = nil,
    sky = nil,
    atmosphere = nil,
}

local function Log(msg)
    print("[MJOLNIR WorldBuilder] " .. tostring(msg) .. "\n")
end

--- First real parameter of a console command.
---
--- UE4SS hands the handler only the parameters, but some builds prepend the
--- command word itself; tolerate both so the commands survive either shape.
local function commandArg(args, index)
    local offset = (type(args[1]) == "string" and args[1]:lower():find("^mjolnir_")) and 1 or 0
    return args[index + offset]
end

local function firstValid(list)
    for _, o in ipairs(list or {}) do
        if o and o:IsValid() then return o end
    end
    return nil
end

local function countOf(className)
    local n = 0
    local ok, list = pcall(function() return FindAllOf(className) end)
    if ok then
        for _, o in ipairs(list or {}) do
            if o and o:IsValid() then n = n + 1 end
        end
    end
    return n
end

local function getPlayerController()
    return firstValid(FindAllOf("PlayerController"))
end

local function getPawn()
    local pc = getPlayerController()
    if not pc then return nil end
    local ok, pawn = pcall(function() return pc.Pawn end)
    if ok and pawn and pawn:IsValid() then return pawn end
    return nil
end

local function getWorld()
    local pc = getPlayerController()
    if not pc then return nil end
    local ok, world = pcall(function() return pc:GetWorld() end)
    if ok and world and world:IsValid() then return world end
    return nil
end

--- Spawn an engine actor by class path, reusing a previous one if it survives.
local function spawnActor(key, classPath, location, rotation)
    if Spawned[key] and Spawned[key]:IsValid() then
        return Spawned[key], false
    end
    local world = getWorld()
    if not world then
        Log("no live world; load a mission first")
        return nil, false
    end
    local class = StaticFindObject(classPath)
    if not class or not class:IsValid() then
        Log("class not found: " .. classPath)
        return nil, false
    end
    local ok, actor = pcall(function()
        return world:SpawnActor(class,
            { X = location.X, Y = location.Y, Z = location.Z },
            rotation or { Pitch = 0.0, Yaw = 0.0, Roll = 0.0 })
    end)
    if not ok or not actor or not actor:IsValid() then
        Log("failed to spawn " .. classPath .. ": " .. tostring(actor))
        return nil, false
    end
    Spawned[key] = actor
    return actor, true
end

local function buildLighting()
    local pawn = getPawn()
    local base = pawn and pawn:K2_GetActorLocation() or { X = 0, Y = 0, Z = 0 }
    local high = { X = base.X, Y = base.Y, Z = base.Z + 5000.0 }

    -- A steep sun angle keeps the floor lit whichever way the player faces.
    local sun, sunIsNew = spawnActor("sun", "/Script/Engine.DirectionalLight", high,
        { Pitch = -50.0, Yaw = 30.0, Roll = 0.0 })
    if sun and sunIsNew then
        pcall(function()
            local c = sun.LightComponent
            c.Mobility = MOBILITY_MOVABLE
            c:SetIntensity(8.0)
        end)
    end

    -- SkyAtmosphere gives the SkyLight something to capture; without it a
    -- real-time capture in an empty world captures blackness and contributes
    -- no ambient, leaving everything the sun does not hit fully black.
    local atmosphere = spawnActor("atmosphere", "/Script/Engine.SkyAtmosphere", high)

    local sky, skyIsNew = spawnActor("sky", "/Script/Engine.SkyLight", high)
    if sky and skyIsNew then
        pcall(function()
            local c = sky.LightComponent
            c.Mobility = MOBILITY_MOVABLE
            c.bRealTimeCapture = true
            c:SetIntensity(3.0)
            c:RecaptureSky()
        end)
    end

    Log(string.format("lighting: sun=%s atmosphere=%s skylight=%s",
        tostring(sun ~= nil), tostring(atmosphere ~= nil), tostring(sky ~= nil)))
    return sun ~= nil
end

local function buildFloor(sizeMetres)
    local pawn = getPawn()
    if not pawn then
        Log("no pawn; the floor is laid under the player")
        return false
    end
    local at = pawn:K2_GetActorLocation()

    local mesh = StaticFindObject(BASIC_CUBE)
    if not mesh or not mesh:IsValid() then
        local ok, loaded = pcall(function() return LoadAsset(BASIC_CUBE) end)
        mesh = (ok and loaded and loaded:IsValid()) and loaded or nil
    end
    if not mesh then
        Log("could not resolve " .. BASIC_CUBE)
        return false
    end

    -- The base cube is 100 cm and pivots at its centre, so a scale of N gives an
    -- N-metre edge and the top surface sits half the thickness above the actor.
    local scale = sizeMetres or DEFAULT_FLOOR_M
    local surfaceZ = at.Z - FLOOR_DROP
    local actor, isNew = spawnActor("floor", "/Script/Engine.StaticMeshActor",
        { X = at.X, Y = at.Y, Z = surfaceZ - 50.0 })
    if not actor then return false end

    -- An empty custom world has no ground, so the pawn is in free fall from the
    -- instant the level loads and is somewhere new by the time this runs. Move
    -- the slab under wherever the player is now rather than where they started,
    -- which also makes re-running the command work as a "catch me".
    if not isNew then
        pcall(function()
            actor:K2_SetActorLocation({ X = at.X, Y = at.Y, Z = surfaceZ - 50.0 },
                false, {}, true)
        end)
    end

    local ok, err = pcall(function()
        local comp = actor.StaticMeshComponent
        -- Order matters. SetStaticMesh refuses to do anything on a registered
        -- component whose mobility is Static -- it logs "not movable" and
        -- returns -- and StaticMeshActor's component ships Static. Flipping
        -- mobility first is what makes the assignment take.
        comp.Mobility = MOBILITY_MOVABLE
        comp:SetStaticMesh(mesh)
        actor:SetActorScale3D({ X = scale, Y = scale, Z = 1.0 })
        comp:SetCollisionEnabled(2) -- ECollisionEnabled::QueryAndPhysics
    end)
    if not ok then
        Log("floor setup failed: " .. tostring(err))
        return false
    end

    -- Read the mesh back rather than trusting the setter: a silently-refused
    -- SetStaticMesh leaves a live actor with no geometry, which looks exactly
    -- like a rendering problem from the outside.
    local applied = false
    pcall(function()
        local got = actor.StaticMeshComponent:GetStaticMesh()
        applied = got and got:IsValid() and true or false
    end)

    Log(string.format("floor %s: %.0f m pad, surface z=%.0f, mesh applied=%s",
        isNew and "spawned" or "reused", scale, surfaceZ, tostring(applied)))
    return applied
end

local function probe()
    local world = getWorld()
    local pawn = getPawn()
    Log("world: " .. (world and world:GetFullName() or "none"))

    if world then
        pcall(function()
            local ws = world.PersistentLevel.WorldSettings
            Log("WorldSettings class: " .. ws:GetClass():GetFName():ToString()
                .. "  (stock 'WorldSettings' means the loaded world is ours,"
                .. " 'BlamWorldSettings' means the shipped one)")
        end)
    end

    for _, cls in ipairs({ "StaticMeshActor", "DirectionalLight", "SkyLight",
                           "SkyAtmosphere", "ExponentialHeightFog" }) do
        Log(string.format("  %-22s %d", cls, countOf(cls)))
    end

    if pawn then
        local loc = pawn:K2_GetActorLocation()
        Log(string.format("pawn at (%.0f, %.0f, %.0f)", loc.X, loc.Y, loc.Z))
    else
        Log("no pawn")
    end
end

local function build(sizeMetres)
    buildLighting()
    local floored = buildFloor(sizeMetres)
    if floored then
        Log("built. A still-black screen at the start of A15 is the brightness"
            .. " calibration prompt, not a failure -- press E to proceed.")
    end
end

local function toSize(raw)
    local n = tonumber(raw)
    if n and n > 0 then return n end
    return nil
end

-- Auto-build ------------------------------------------------------------------
--
-- A custom world arrives unfurnished and unlit, so waiting for a human to type
-- a command means staring at a black void first. This watcher spots our world
-- and furnishes it on arrival.
--
-- It also covers the case where nothing is holding the player up. Overriding a
-- campaign scenario happens to inherit that mission's Blam BSP collision, so on
-- A15 the pawn settles at z=2 rather than falling; a world with no such backing
-- would drop the pawn to KillZ in about fifteen seconds, which is not enough
-- time to type.
--
-- The tell is the WorldSettings class: every shipped world uses
-- BlamWorldSettings, and a world cooked in stock UE 5.5 gets plain
-- WorldSettings. That is the same signal used to prove the loaded world was
-- ours in the first place, and it cannot fire on a shipped map.

local AutoBuild = true
local LastWorldName = nil

local function isCustomWorld(world)
    local ok, name = pcall(function()
        return world.PersistentLevel.WorldSettings:GetClass():GetFName():ToString()
    end)
    return ok and name == "WorldSettings"
end

local function tick()
    if not AutoBuild then return end
    local world = getWorld()
    if not world then return end

    local name = world:GetFullName()
    if name == LastWorldName then return end

    if isCustomWorld(world) then
        if not getPawn() then return end -- still loading; try again next tick
        LastWorldName = name
        Log("custom world detected (stock WorldSettings) — furnishing it")
        build(nil)
    else
        -- A shipped world replaced ours; drop the stale actor handles.
        LastWorldName = name
        Spawned = { floor = nil, sun = nil, sky = nil, atmosphere = nil }
    end
end

-- LoopAsync runs off the game thread, so the body is marshalled back on before
-- it touches any UObject. Returning false keeps the loop alive.
local function watch()
    LoopAsync(1000, function()
        ExecuteInGameThread(function()
            local ok, err = pcall(tick)
            if not ok then Log("auto-build tick error: " .. tostring(err)) end
        end)
        return false
    end)
end

local function initialize()
    RegisterConsoleCommandHandler("mjolnir_world_probe", function()
        probe()
        return true
    end)
    RegisterConsoleCommandHandler("mjolnir_world_build", function(_, args)
        build(toSize(commandArg(args, 1)))
        return true
    end)
    RegisterConsoleCommandHandler("mjolnir_world_light", function()
        buildLighting()
        return true
    end)
    RegisterConsoleCommandHandler("mjolnir_world_floor", function(_, args)
        buildFloor(toSize(commandArg(args, 1)))
        return true
    end)
    RegisterConsoleCommandHandler("mjolnir_world_auto", function()
        AutoBuild = not AutoBuild
        Log("auto-build " .. (AutoBuild and "ON" or "OFF"))
        return true
    end)
    Log("commands registered: mjolnir_world_probe / _build / _light / _floor / _auto")
    watch()
end

ExecuteInGameThreadWithDelay(5000, initialize)
print("[MJOLNIR WorldBuilder] Module loaded.\n")
