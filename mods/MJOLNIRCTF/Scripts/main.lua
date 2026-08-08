-- MJOLNIR CTF
--
-- Installs a game mode into Halo Campaign Evolved's own Experience framework,
-- and lays out a Capture the Flag arena inside a custom world.
--
-- Why this works without cooking anything
-- ---------------------------------------
-- The game ships /Script/BlamExperience, a Lyra-style experience framework, and
-- runs it: in a loaded mission the GameState carries a
-- BlamExperienceManagerComponent whose CurrentExperience resolves to
-- BP_BlamExperienceDefault_C. That shipped experience is *empty* -- zero
-- GameFeaturesToEnable, zero Actions, zero ActionSets -- so nothing competes
-- with us for it.
--
-- Two routes into that component were tried and rejected before this one:
--
--   * -BlamExperience=<id> on the command line is ignored. Verified with a
--     deliberately bogus id: CurrentExperience still came back as the default,
--     with the argument confirmed present via KismetSystemLibrary::GetCommandLine.
--     The campaign flow sets the experience explicitly, which beats it.
--   * Cooking our own UBlamExperienceDefinition asset would hit the same
--     serialization wall that stops cooked actors loading (343's engine build
--     has its own class layouts; stock UE 5.5 cooks properties unversioned).
--
-- The route that does work: construct the definition in-process, from the
-- game's own class, and assign it. StaticConstructObject on
-- /Script/BlamExperience.BlamExperienceDefinition succeeds, CurrentExperience
-- is writable, the assignment sticks, and OnRep_CurrentExperience is callable.
-- Verified in mission A30 on CU3, 2026-08-04.
--
-- The arena is built the same way and for the same reason the World Builder
-- builds floors at runtime: cooked actor components do not deserialize, so the
-- cooked world ships empty and the map is assembled in-process.
--
-- Commands:
--   mjolnir_ctf_experience       install the CTF experience on the live GameState
--   mjolnir_ctf_arena [size_m]   lay out a two-base CTF arena around the player
--   mjolnir_ctf_status           report experience, arena and team state
--   mjolnir_ctf_reset            forget what we spawned (does not despawn)
--
-- Everything is idempotent: each command reuses what it already made.

local EXPERIENCE_CLASS = "/Script/BlamExperience.BlamExperienceDefinition"
local BASIC_CUBE = "/Engine/BasicShapes/Cube.Cube"

-- EComponentMobility: Static = 0, Stationary = 1, Movable = 2.
-- SetStaticMesh silently no-ops on a registered static component, so this has
-- to be set before the mesh, not after.
local MOBILITY_MOVABLE = 2

-- Arena dimensions in metres. The default is deliberately small: an arena has
-- to be crossable on foot for a flag run to mean anything, and the pawn walks
-- on Blam BSP collision inherited from whatever scenario the world overrides.
local DEFAULT_ARENA_M = 120.0

-- Base separation as a fraction of arena size, measured centre to centre.
local BASE_SEPARATION = 0.68

-- How far below the pawn the arena floor is laid, in cm. Matches the World
-- Builder so the two agree about where the ground is.
local FLOOR_DROP = 120.0

local FLAG_STAND_SCALE = 1.5
local BASE_PAD_M = 18.0

local Spawned = {}
local Experience = nil
local LastWorldName = nil

-- Names have to be unique within the outer, so installing twice in one session
-- cannot reuse one. A counter does that without reaching for a clock.
local InstallCount = 0

local function Log(msg)
    print("[MJOLNIR CTF] " .. tostring(msg) .. "\n")
end

--- First real parameter of a console command.
---
--- UE4SS hands the handler only the parameters, but some builds prepend the
--- command word itself; tolerate both so the commands survive either shape.
local function commandArg(args, index)
    local offset = (type(args[1]) == "string" and args[1]:lower():find("^mjolnir_")) and 1 or 0
    return args[index + offset]
end

--- StaticFindObject returns a NON-NULL garbage pointer for paths that do not
--- exist, and reading properties off one exits the process. A real object
--- produces a real name; a phantom produces nothing. Never skip this.
local function findObject(path)
    local ok, o = pcall(function() return StaticFindObject(path) end)
    if not ok or not o then return nil end
    local okName, name = pcall(function() return o:GetFullName() end)
    if okName and type(name) == "string" and #name > 0 then return o, name end
    return nil
end

local function nameOf(o)
    if not o then return "none" end
    local ok, n = pcall(function() return o:GetFullName() end)
    return (ok and n) or "?"
end

--- Are two handles the same UObject?
---
--- Reflection hands back a fresh wrapper each time a property is read, so `==`
--- on two handles to the same object is false. Comparing full names is what
--- actually answers the question -- a name is unique within a world, which is
--- the only scope these comparisons span.
local function sameObject(a, b)
    if not a or not b then return false end
    local na, nb = nameOf(a), nameOf(b)
    return na ~= "?" and na ~= "none" and na == nb
end

local function firstValid(list)
    for _, o in ipairs(list or {}) do
        if o and o:IsValid() then return o end
    end
    return nil
end

local function pawnOf(pc)
    if not pc then return nil end
    local ok, pawn = pcall(function() return pc.Pawn end)
    if ok and pawn and pawn:IsValid() then return pawn end
    return nil
end

--- The possessed controller, not merely the first one.
---
--- A loaded mission keeps a pawnless BP_FrontendPlayerController_C alongside
--- the real BP_MeteoritePlayerController_C, and the frontend one sorts first.
--- Taking the first valid controller finds it, finds no pawn, and reports an
--- empty world -- so prefer whichever controller actually possesses something.
local function getPlayerController()
    local list = FindAllOf("PlayerController") or {}
    for _, pc in ipairs(list) do
        if pc and pc:IsValid() and pawnOf(pc) then return pc end
    end
    return firstValid(list)
end

local function getPawn()
    return pawnOf(getPlayerController())
end

local function getWorld()
    local pc = getPlayerController()
    if not pc then return nil end
    local ok, world = pcall(function() return pc:GetWorld() end)
    if ok and world and world:IsValid() then return world end
    return nil
end

local function getExperienceComponent()
    return firstValid(FindAllOf("BlamExperienceManagerComponent"))
end

-- ---------------------------------------------------------------------------
-- The experience
-- ---------------------------------------------------------------------------

--- Construct a BlamExperienceDefinition and install it as CurrentExperience.
---
--- The definition is outered to the GameState that owns the manager component,
--- which is what the shipped flow does with its own and keeps our object alive
--- exactly as long as the match it belongs to.
local function installExperience(label)
    local comp = getExperienceComponent()
    if not comp then
        Log("no BlamExperienceManagerComponent -- it lives on the GameState of a")
        Log("gameplay world, so load a mission first (the frontend has none)")
        return false
    end

    local before = nil
    pcall(function() before = comp.CurrentExperience end)

    if Experience and Experience:IsValid() then
        local current = nil
        pcall(function() current = comp.CurrentExperience end)
        if sameObject(current, Experience) then
            Log("already installed: " .. nameOf(Experience))
            return true
        end
    end

    local class = findObject(EXPERIENCE_CLASS)
    if not class then
        Log("class not found: " .. EXPERIENCE_CLASS)
        return false
    end

    local outer
    local okOuter, o = pcall(function() return comp:GetOuter() end)
    if okOuter and o and o:IsValid() then outer = o end
    if not outer then
        Log("could not resolve the component's outer")
        return false
    end

    InstallCount = InstallCount + 1
    local name = label or ("MJOLNIR_CTF_Experience_" .. tostring(InstallCount))
    local okNew, made = pcall(function()
        return StaticConstructObject(class, outer, FName(name))
    end)
    if not okNew or not made or not made:IsValid() then
        Log("could not construct an experience: " .. tostring(made))
        return false
    end

    local okSet, err = pcall(function() comp.CurrentExperience = made end)
    if not okSet then
        Log("could not assign CurrentExperience: " .. tostring(err))
        return false
    end

    -- On a listen host the property is set locally, so the OnRep the clients
    -- get never fires here. Calling it directly keeps host and client on the
    -- same code path.
    pcall(function() comp:OnRep_CurrentExperience() end)

    Experience = made
    Log("experience installed")
    Log("  was: " .. nameOf(before))
    Log("  now: " .. nameOf(made))
    return true
end

-- ---------------------------------------------------------------------------
-- The arena
-- ---------------------------------------------------------------------------

local function resolveMesh(path)
    local mesh = findObject(path)
    if mesh then return mesh end
    local ok, loaded = pcall(function() return LoadAsset(path) end)
    if ok and loaded and loaded:IsValid() then return loaded end
    return nil
end

--- Spawn a StaticMeshActor and give it geometry.
---
--- Mobility must be set before the mesh: SetStaticMesh logs "not movable" and
--- returns on a registered static component, leaving a live actor with nothing
--- to draw, which looks exactly like a rendering bug from outside.
local function spawnSlab(key, location, scale, label)
    if Spawned[key] and Spawned[key]:IsValid() then
        return Spawned[key], false
    end

    local world = getWorld()
    if not world then
        Log("no live world; load a mission first")
        return nil, false
    end

    local class = findObject("/Script/Engine.StaticMeshActor")
    if not class then
        Log("StaticMeshActor class not found")
        return nil, false
    end

    local okSpawn, actor = pcall(function()
        return world:SpawnActor(class, location, { Pitch = 0.0, Yaw = 0.0, Roll = 0.0 })
    end)
    if not okSpawn or not actor or not actor:IsValid() then
        Log("failed to spawn " .. label .. ": " .. tostring(actor))
        return nil, false
    end

    local mesh = resolveMesh(BASIC_CUBE)
    if not mesh then
        Log("could not resolve " .. BASIC_CUBE)
        return actor, true
    end

    local okMesh, err = pcall(function()
        local comp = actor.StaticMeshComponent
        comp.Mobility = MOBILITY_MOVABLE
        comp:SetStaticMesh(mesh)
    end)
    if not okMesh then
        Log("could not set mesh on " .. label .. ": " .. tostring(err))
    end

    pcall(function() actor:SetActorScale3D(scale) end)

    Spawned[key] = actor
    return actor, true
end

--- Lay out a symmetric two-base arena centred on the player.
---
--- Bases sit on the X axis so the run between them is a straight line, which
--- makes it obvious at a glance whether the geometry came out symmetric.
local function buildArena(sizeMetres)
    local pawn = getPawn()
    if not pawn then
        Log("no pawn; the arena is laid out around the player")
        return false
    end

    local size = sizeMetres or DEFAULT_ARENA_M
    local at = pawn:K2_GetActorLocation()
    local surfaceZ = at.Z - FLOOR_DROP
    local half = (size * 100.0 * BASE_SEPARATION) / 2.0

    -- Floor. The base cube is 100 cm and pivots at its centre, so a scale of N
    -- gives an N-metre edge and the walking surface sits half the thickness up.
    spawnSlab("floor",
        { X = at.X, Y = at.Y, Z = surfaceZ - 50.0 },
        { X = size, Y = size, Z = 1.0 },
        "floor")

    local layout = {
        { key = "base_red", team = "Red", x = at.X - half },
        { key = "base_blue", team = "Blue", x = at.X + half },
    }

    for _, base in ipairs(layout) do
        -- A raised pad marks each base and gives the flag stand somewhere to
        -- sit that reads as "theirs" from across the arena.
        spawnSlab(base.key,
            { X = base.x, Y = at.Y, Z = surfaceZ + 25.0 },
            { X = BASE_PAD_M, Y = BASE_PAD_M, Z = 0.5 },
            base.team .. " base pad")

        spawnSlab(base.key .. "_flag",
            { X = base.x, Y = at.Y, Z = surfaceZ + 50.0 + (FLAG_STAND_SCALE * 50.0) },
            { X = 0.6, Y = 0.6, Z = FLAG_STAND_SCALE },
            base.team .. " flag stand")
    end

    Log(string.format("arena: %.0f m floor, bases %.0f m apart on X", size, (half * 2) / 100.0))
    Log("  red base  at x=" .. string.format("%.0f", at.X - half))
    Log("  blue base at x=" .. string.format("%.0f", at.X + half))
    Log("flag stands are markers, not carryables -- the flag object does not")
    Log("ship in this build (oddball and the assault bomb do)")
    return true
end

-- ---------------------------------------------------------------------------
-- Status
-- ---------------------------------------------------------------------------

local function status()
    local world = getWorld()
    Log("world: " .. (world and nameOf(world) or "none"))

    local comp = getExperienceComponent()
    if not comp then
        Log("experience component: none (frontend, or no gameplay world)")
    else
        Log("experience component: " .. nameOf(comp))
        local ok, cur = pcall(function() return comp.CurrentExperience end)
        Log("  CurrentExperience: " .. (ok and nameOf(cur) or "?"))
        Log("  ours: " .. tostring(ok and sameObject(cur, Experience)))
        for _, gate in ipairs({
            "bWaitingForAllInitialPlayersToLoadLevel",
            "bWaitingForAllInitialPlayersToBeReadyForGameplay",
            "bWaitingForBlamGameplayStart",
        }) do
            local okGate, v = pcall(function() return comp[gate] end)
            Log("  " .. gate .. " = " .. tostring(okGate and v))
        end
    end

    local built = {}
    for key, actor in pairs(Spawned) do
        if actor and actor:IsValid() then built[#built + 1] = key end
    end
    table.sort(built)
    Log("arena pieces: " .. (#built > 0 and table.concat(built, ", ") or "none"))
end

-- ---------------------------------------------------------------------------
-- Lifecycle
-- ---------------------------------------------------------------------------

--- Drop our handles when the world changes.
---
--- The actors and the experience belong to the old world and are already gone;
--- holding stale handles would make the idempotency checks above resurrect
--- nothing and report success.
local function forgetOnWorldChange()
    local world = getWorld()
    local name = world and nameOf(world) or nil
    if name ~= LastWorldName then
        LastWorldName = name
        Spawned = {}
        Experience = nil
    end
end

local function watch()
    LoopAsync(1000, function()
        ExecuteInGameThread(function()
            pcall(forgetOnWorldChange)
        end)
        return false
    end)
end

local function toSize(arg)
    local n = tonumber(arg)
    if n and n > 0 then return n end
    return nil
end

local function initialize()
    RegisterConsoleCommandHandler("mjolnir_ctf_experience", function()
        installExperience()
        return true
    end)
    RegisterConsoleCommandHandler("mjolnir_ctf_arena", function(_, args)
        buildArena(toSize(commandArg(args, 1)))
        return true
    end)
    RegisterConsoleCommandHandler("mjolnir_ctf_status", function()
        status()
        return true
    end)
    RegisterConsoleCommandHandler("mjolnir_ctf_reset", function()
        Spawned = {}
        Experience = nil
        Log("forgot spawned handles (nothing despawned)")
        return true
    end)
    Log("commands registered: mjolnir_ctf_experience / _arena / _status / _reset")
    watch()
end

ExecuteInGameThreadWithDelay(5000, initialize)
print("[MJOLNIR CTF] Module loaded.\n")
