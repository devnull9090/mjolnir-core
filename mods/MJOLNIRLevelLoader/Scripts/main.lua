-- MJOLNIR Level Loader
--
-- Runtime half of the level authoring pipeline (docs/level_format.md). Custom
-- levels are map variants over a shipped scenario: the solid half of a level
-- lives in a baked scenario-tag override, and this mod spawns the other half —
-- the `decor` section of the level file — when the canvas world arrives.
--
-- Decor is visuals-only BY DESIGN. The Blam simulation collides exclusively
-- with its own world (BSP + Blam objects) and walks straight through Unreal
-- geometry, runtime-spawned and cooked alike (verified 2026-08-19, see
-- docs/multiplayer_investigation_notes.md). Decor actors are therefore spawned
-- with collision OFF so the Unreal side (camera sweeps) agrees with what the
-- sim already believes. Anything solid must be a Blam object placement.
--
-- Level files live next to the mod: levels/<SCENARIO>.level.json — written
-- there by `mjolnir level bake --install-test` or by hand. The watcher spots
-- the canvas scenario's world, reads the file, and furnishes it. Positions in
-- the file are UE cm relative to canvas.origin.
--
-- Native half: native/mjolnir_map_registry.dll (source native/map_registry,
-- never committed — build.ps1 or the release builds it) lets a standalone
-- map run on a world of its own: the engine resolves a mission's world by
-- short name through the AssetRegistry, which only knows shipped packages,
-- and the DLL answers for worlds found in the installed containers. Without
-- the DLL everything else here still works on canvas worlds.
--
-- Commands:
--   mjolnir_level_status   what is loaded, spawned, or failing
--   mjolnir_level_reload   re-read the level file and respawn decor (dev loop)
--   mjolnir_level_clear    remove everything this mod spawned
--   mjolnir_level_rescan   re-read the containers' world lists (native half)

--------------------------------------------------------------------------------
-- Paths (same derivation as MJOLNIRBridge: relative paths depend on the
-- process working directory, debug.getinfo does not)
--------------------------------------------------------------------------------

local function modDirectory()
    local source = debug.getinfo(1, "S").source or ""
    local path = source:gsub("^@", ""):gsub("/", "\\")
    -- <ue4ss>\Mods\MJOLNIRLevelLoader\Scripts\main.lua -> <mod root>
    local root = path
    for _ = 1, 2 do
        root = root:match("^(.*)\\[^\\]*$") or root
    end
    return root
end

local MOD_DIR = modDirectory()
local Json = dofile(MOD_DIR .. "\\Scripts\\json.lua")

local function levelPathFor(scenario)
    return MOD_DIR .. "\\levels\\" .. scenario .. ".level.json"
end

local function readFile(path)
    local f = io.open(path, "rb")
    if not f then return nil end
    local data = f:read("*a")
    f:close()
    return data
end

--------------------------------------------------------------------------------
-- Shared helpers (patterns from MJOLNIRWorldBuilder / MJOLNIRCTF)
--------------------------------------------------------------------------------

local MOBILITY_MOVABLE = 2
local COLLISION_NONE = 0

local function Log(msg)
    print("[MJOLNIR LevelLoader] " .. tostring(msg) .. "\n")
end

local function firstValid(list)
    for _, o in ipairs(list or {}) do
        if o and o:IsValid() then return o end
    end
    return nil
end

--- StaticFindObject returns a NON-NULL garbage pointer for paths that do not
--- exist, and reading properties off one exits the process. A real object
--- produces a real name; a phantom produces nothing. Never skip this.
local function findObject(path)
    local ok, o = pcall(function() return StaticFindObject(path) end)
    if not ok or not o then return nil end
    local okName, name = pcall(function() return o:GetFullName() end)
    if okName and type(name) == "string" and #name > 0 then return o end
    return nil
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

--- "World /Game/Levels/Halo1/Solo/B40/B40.B40" -> "B40" (uppercased).
--- The frontend and anything unrecognised return nil.
local function scenarioOf(world)
    local ok, name = pcall(function() return world:GetFullName() end)
    if not ok or type(name) ~= "string" then return nil end
    local asset = name:match("%.([%w_]+)$")
    if not asset then return nil end
    return string.upper(asset)
end

--- The codename of the scenario tag actually running, e.g. "PG1" from
--- `.../PG1/_Generated_/PG1-scenario`. A standalone map (`mjolnir level bake
--- --standalone`) runs its own scenario tag on a shipped world, so its level
--- file is keyed by this rather than by the world; nil when no scenario asset
--- is loaded yet or its name does not follow the pattern.
local function scenarioTagOf()
    local ok, assets = pcall(function() return FindAllOf("BlamScenarioTagDataAsset") end)
    if not ok or type(assets) ~= "table" then return nil end
    for _, a in ipairs(assets) do
        local okn, name = pcall(function() return a:GetFullName() end)
        if okn and type(name) == "string" then
            local code = name:match("([%w_]+)%-scenario%.[%w_]+%-scenario$")
            if code then return string.upper(code) end
        end
    end
    return nil
end

--------------------------------------------------------------------------------
-- Level state
--------------------------------------------------------------------------------

local Current = {
    worldName = nil,   -- full name of the world the state belongs to
    scenario = nil,    -- "B40"
    level = nil,       -- decoded level table
    actors = {},       -- spawned decor actors, by decor id
    spawned = 0,
    failed = 0,
    fileMissing = false,
}

local function resetState()
    Current.worldName = nil
    Current.scenario = nil
    Current.level = nil
    Current.actors = {}
    Current.spawned = 0
    Current.failed = 0
    Current.fileMissing = false
end

local function clearActors()
    for _, actor in pairs(Current.actors) do
        if actor and actor:IsValid() then
            pcall(function() actor:K2_DestroyActor() end)
        end
    end
    Current.actors = {}
    Current.spawned = 0
    Current.failed = 0
end

--------------------------------------------------------------------------------
-- Loading and validation
--------------------------------------------------------------------------------

--- Decode and sanity-check a level file. Full validation is the CLI's job
--- (`mjolnir level validate`); the loader checks only what it consumes.
local function loadLevelFile(scenario, fileKey)
    local path = levelPathFor(fileKey or scenario)
    local raw = readFile(path)
    if not raw then return nil, "no file: " .. path end

    local ok, level = pcall(Json.decode, raw)
    if not ok then return nil, "parse failed: " .. tostring(level) end

    if type(level) ~= "table" or level.schema_version ~= 1 then
        return nil, "unsupported schema_version"
    end
    local canvas = level.canvas
    if type(canvas) ~= "table" or type(canvas.origin) ~= "table"
        or type(canvas.scenario) ~= "string" then
        return nil, "missing canvas"
    end
    -- A file found by world name must target that world. A file found by
    -- scenario tag codename belongs to that scenario wherever it runs: on
    -- its canvas world, or on a world of its own that carries the codename.
    if not fileKey and string.upper(canvas.scenario) ~= scenario then
        return nil, string.format("file targets %s but the loaded world is %s",
            canvas.scenario, scenario)
    end
    return level
end

--- The level file for the running world: the scenario tag's own file when
--- one is loaded, else the world's.
local function loadCurrentLevelFile(scenario)
    local tag = scenarioTagOf()
    if tag then
        local level = loadLevelFile(scenario, tag)
        if level then
            if tag ~= scenario then
                Log(string.format("scenario tag %s has its own level file", tag))
            end
            return level
        end
    end
    return loadLevelFile(scenario)
end

--------------------------------------------------------------------------------
-- Decor spawning
--------------------------------------------------------------------------------

--- Resolve a mesh object path, loading the asset if it is not in memory.
--- Never called on world packages: decor mesh paths are object paths into
--- /Engine or /Game mesh packages (LoadAsset on a world package crashes).
local function resolveMesh(path)
    local mesh = findObject(path)
    if mesh then return mesh end
    local ok, loaded = pcall(function() return LoadAsset(path) end)
    if ok and loaded and loaded:IsValid() then return loaded end
    return nil
end

--- Tinting: the engine's basic shapes arrive with WorldGridMaterial on slot 0,
--- which exposes no color parameter — so the tint path swaps in a dynamic
--- instance of BasicShapeMaterial (which has a `Color` vector parameter) as
--- the MID source. Verified live on this build; the three-argument
--- CreateDynamicMaterialInstance form is the one UE4SS accepts.
local BASIC_SHAPE_MATERIAL = "/Engine/BasicShapes/BasicShapeMaterial.BasicShapeMaterial"

local function applyTint(comp, tint)
    if type(tint) ~= "table" or #tint < 4 then return false end
    local color = { R = tint[1], G = tint[2], B = tint[3], A = tint[4] }
    local ok = pcall(function()
        local basic = resolveMesh(BASIC_SHAPE_MATERIAL)
        if not basic then error("BasicShapeMaterial unavailable") end
        local mid = comp:CreateDynamicMaterialInstance(0, basic, FName("None"))
        if not mid or not mid:IsValid() then error("no MID") end
        mid:SetVectorParameterValue(FName("Color"), color)
    end)
    return ok
end

--- Per-section materials: `materials` is a list of material object paths, one
--- per material slot in order, and an empty entry leaves that slot alone. They
--- go on the *component*, not the mesh: a mesh whose geometry was written into
--- a donor package keeps the donor's single material slot however many slots
--- the package declares, while `SetMaterial` grows the component's override
--- list to as many sections as the render data names. That is what makes a
--- transplanted mesh come out textured rather than default grey.
local function applyMaterials(comp, list)
    if type(list) ~= "table" then return 0, 0 end
    local applied, failed = 0, 0
    for i, path in ipairs(list) do
        if type(path) == "string" and #path > 0 then
            local mat = resolveMesh(path)
            local ok = false
            if mat then
                ok = pcall(function() comp:SetMaterial(i - 1, mat) end)
            end
            if ok then applied = applied + 1 else failed = failed + 1 end
        end
    end
    return applied, failed
end

local function spawnDecorItem(world, origin, item)
    if type(item) ~= "table" or type(item.mesh) ~= "string"
        or type(item.pos) ~= "table" then
        return nil, "malformed decor entry"
    end

    local mesh = resolveMesh(item.mesh)
    if not mesh then return nil, "mesh not found: " .. item.mesh end

    local cls = findObject("/Script/Engine.StaticMeshActor")
    if not cls then return nil, "StaticMeshActor class missing" end

    local rot = item.rot or {}
    local ok, actor = pcall(function()
        return world:SpawnActor(cls, {
            X = origin[1] + item.pos[1],
            Y = origin[2] + item.pos[2],
            Z = origin[3] + item.pos[3],
        }, {
            Pitch = rot[1] or 0.0,
            Yaw = rot[2] or 0.0,
            Roll = rot[3] or 0.0,
        })
    end)
    if not ok or not actor or not actor:IsValid() then
        return nil, "spawn failed"
    end

    local okSetup, err = pcall(function()
        local comp = actor.StaticMeshComponent
        -- Order matters: SetStaticMesh silently refuses on a registered
        -- component whose mobility is Static, and StaticMeshActor ships Static.
        comp.Mobility = MOBILITY_MOVABLE
        comp:SetStaticMesh(mesh)
        local s = item.scale
        if type(s) == "table" and #s >= 3 then
            actor:SetActorScale3D({ X = s[1], Y = s[2], Z = s[3] })
        end
        -- Decor is not solid to the sim; keep the Unreal side consistent.
        comp:SetCollisionEnabled(COLLISION_NONE)
    end)
    if not okSetup then
        pcall(function() actor:K2_DestroyActor() end)
        return nil, "setup failed: " .. tostring(err)
    end

    -- Read the mesh back rather than trusting the setter.
    local applied = false
    pcall(function()
        local got = actor.StaticMeshComponent.StaticMesh
        applied = got and got:IsValid() and true or false
    end)
    if not applied then
        pcall(function() actor:K2_DestroyActor() end)
        return nil, "mesh did not apply: " .. item.mesh
    end

    if item.tint and not applyTint(actor.StaticMeshComponent, item.tint) then
        Log("tint failed for '" .. tostring(item.id) .. "' (mesh has no Color param?)")
    end
    if item.materials then
        local applied, failed = applyMaterials(actor.StaticMeshComponent, item.materials)
        Log(string.format("decor '%s': %d material(s) applied, %d failed",
            tostring(item.id), applied, failed))
    end
    return actor
end

--- Spawn the level's sky and lighting (an empty canvas world has none, and a
--- black void reads as a failure). Patterns from MJOLNIRWorldBuilder.
local function spawnEnvironment(world)
    local env = Current.level and Current.level.environment
    if type(env) ~= "table" then return end
    local origin = Current.level.canvas.origin
    local high = { X = origin[1], Y = origin[2], Z = origin[3] + 5000.0 }

    local function place(key, classPath, rotation, setup)
        if Current.actors[key] and Current.actors[key]:IsValid() then return end
        local class = findObject(classPath)
        if not class then return end
        local ok, actor = pcall(function()
            return world:SpawnActor(class, high, rotation or { Pitch = 0, Yaw = 0, Roll = 0 })
        end)
        if ok and actor and actor:IsValid() then
            Current.actors[key] = actor
            if setup then pcall(setup, actor) end
        end
    end

    local sun = env.sun or {}
    place("__sun", "/Script/Engine.DirectionalLight",
        { Pitch = sun.pitch or -50.0, Yaw = sun.yaw or 30.0, Roll = 0 },
        function(actor)
            local c = actor.LightComponent
            c.Mobility = MOBILITY_MOVABLE
            c:SetIntensity(sun.intensity or 8.0)
        end)
    if env.atmosphere ~= false then
        place("__atmosphere", "/Script/Engine.SkyAtmosphere", nil, nil)
    end
    local skylight = env.skylight or {}
    place("__sky", "/Script/Engine.SkyLight", nil, function(actor)
        local c = actor.LightComponent
        c.Mobility = MOBILITY_MOVABLE
        c.bRealTimeCapture = true
        c:SetIntensity(skylight.intensity or 3.0)
        c:RecaptureSky()
    end)
    Log("environment spawned (sun/atmosphere/skylight)")

    -- A level baked with `clear.scripts` has no mission script left to fade the
    -- screen back in after the loading screen, so the map boots pitch black
    -- with a live simulation behind it. Ask the Blam console to fade in once,
    -- unless the level opts out with `environment.fade_in = false`.
    if env.fade_in ~= false then
        local ok = pcall(function()
            local kismet = StaticFindObject("/Script/Engine.Default__KismetSystemLibrary")
            local pc = FindFirstOf("PlayerController")
            if kismet and pc then
                kismet:ExecuteConsoleCommand(pc, "blam !(fade_in 0 0 0 15)", pc)
            end
        end)
        Log(ok and "fade_in requested" or "fade_in request failed")
    end
end

local function spawnDecor(world)
    local level = Current.level
    spawnEnvironment(world)
    local decor = level and level.decor
    if type(decor) ~= "table" or #decor == 0 then
        Log("level '" .. tostring(level and level.name) .. "': no decor to spawn")
        return
    end
    local origin = level.canvas.origin
    for index, item in ipairs(decor) do
        local id = (type(item) == "table" and item.id) or ("#" .. index)
        if not (Current.actors[id] and Current.actors[id]:IsValid()) then
            local actor, err = spawnDecorItem(world, origin, item)
            if actor then
                Current.actors[id] = actor
                Current.spawned = Current.spawned + 1
            else
                Current.failed = Current.failed + 1
                Log(string.format("decor '%s': %s", tostring(id), tostring(err)))
            end
        end
    end
    Log(string.format("level '%s': %d decor spawned, %d failed",
        tostring(level.name), Current.spawned, Current.failed))
end

--------------------------------------------------------------------------------
-- Watcher: spot the canvas world, furnish it once the player exists
--------------------------------------------------------------------------------

local function tick()
    local world = getWorld()
    if not world then return end

    local worldName = world:GetFullName()
    if worldName ~= Current.worldName then
        -- A new world: drop stale handles, look for a level file.
        resetState()
        Current.worldName = worldName
        Current.scenario = scenarioOf(world)
        if not Current.scenario then return end

        local level, err = loadCurrentLevelFile(Current.scenario)
        if not level then
            Current.fileMissing = true
            if err and not err:find("^no file") then
                Log("level file for " .. Current.scenario .. ": " .. err)
            end
            return
        end
        Current.level = level
        Log(string.format("world %s has level '%s' — waiting for the player",
            Current.scenario, tostring(level.name)))
    end

    if Current.level and Current.spawned == 0 and Current.failed == 0 then
        if not getPawn() then return end -- still loading
        spawnDecor(world)
    end
end

local function watch()
    LoopAsync(1500, function()
        ExecuteInGameThread(function()
            local ok, err = pcall(tick)
            if not ok then Log("tick error: " .. tostring(err)) end
        end)
        return false
    end)
end

--------------------------------------------------------------------------------
-- Commands
--------------------------------------------------------------------------------

local function status()
    Log("mod dir: " .. MOD_DIR)
    Log("world: " .. tostring(Current.worldName))
    Log("scenario: " .. tostring(Current.scenario)
        .. (Current.fileMissing and " (no level file)" or ""))
    if Current.level then
        Log(string.format("level '%s': %d decor spawned, %d failed",
            tostring(Current.level.name), Current.spawned, Current.failed))
    else
        Log("no level loaded")
    end
end

local function reload()
    if not Current.scenario then
        Log("no scenario world is loaded")
        return
    end
    clearActors()
    local level, err = loadCurrentLevelFile(Current.scenario)
    if not level then
        Current.level = nil
        Current.fileMissing = true
        Log("reload: " .. tostring(err))
        return
    end
    Current.level = level
    Current.fileMissing = false
    local world = getWorld()
    if world then spawnDecor(world) end
end

--- The native half. The engine turns a mission's SHORT world name into a
--- package path through the AssetRegistry, which is loaded once at boot from
--- the shipped AssetRegistry.bin and so never knows a world that arrives in
--- a mod container: the travel is refused before any container is asked.
--- native/mjolnir_map_registry.dll wraps that lookup and answers, on a miss,
--- from the .umap files listed by the mounted .utoc directory indexes
--- (docs/new_scenario_loading.md, "The world gate"). Shipped maps never
--- reach the fallback. CU4-only by RVA; the DLL refuses any other build.
local function loadMapRegistry()
    if not package or not package.loadlib then
        Log("map registry: this Lua has no package.loadlib; standalone worlds will not resolve")
        return
    end
    local dll = MOD_DIR .. "\\native\\mjolnir_map_registry.dll"
    local open, err = package.loadlib(dll, "mjolnir_map_registry_open")
    if not open then
        Log("map registry: " .. tostring(err))
        return
    end
    local rescan = package.loadlib(dll, "mjolnir_map_registry_rescan")
    open()
    if rescan then
        RegisterConsoleCommandHandler("mjolnir_level_rescan", function()
            rescan()
            Log("map registry: containers re-read (see native\\map_registry.log)")
            return true
        end)
    end
    Log("map registry: short-name resolver loaded (native\\map_registry.log)")
end

local function initialize()
    loadMapRegistry()
    RegisterConsoleCommandHandler("mjolnir_level_status", function()
        status()
        return true
    end)
    RegisterConsoleCommandHandler("mjolnir_level_reload", function()
        reload()
        return true
    end)
    RegisterConsoleCommandHandler("mjolnir_level_clear", function()
        clearActors()
        Log("cleared")
        return true
    end)
    Log("commands registered: mjolnir_level_status / _reload / _clear")
    watch()
end

ExecuteInGameThreadWithDelay(5000, initialize)
print("[MJOLNIR LevelLoader] Module loaded.\n")
