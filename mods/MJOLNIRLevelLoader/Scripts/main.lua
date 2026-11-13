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
--   mjolnir_terrain_shadows [on|off] [strength]
--                          let a converted level's terrain cast shadows (an
--                          experiment, see TerrainShadows)
--   mjolnir_light_scale [k|default]
--                          how much brighter a converted level's sun and sky
--                          are than CE's, exposure compensated (lightScale)
--   mjolnir_terrain_debug [layer|off]
--                          show one layer of a converted level's terrain light
--   mjolnir_terrain_lights [on|off] [albedo] [noproxy] [fill]
--                          let the game's lights light a converted level's
--                          terrain (an experiment, see TerrainLights)
--   mjolnir_water [ocean|ce|default] | [waves <x>|waves default]
--                          draw a converted level's CE water as rolling,
--                          reflecting water (M_CE_Ocean, see applyWater)
--   mjolnir_foliage [on|off]
--   mjolnir_effects [on|off]
--                          the game's grass on a converted level's grassy
--                          ground, from its level file (see Foliage.spawn)
--   mjolnir_terrain_detail [game|ce] | param <Name> <value>
--                          draw CE's sand and grass detail with the game's own
--                          surfaces (an experiment, see GameDetail)

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
local VariantSettings = dofile(MOD_DIR .. "\\Scripts\\variant_settings.lua")
local VehicleSets = dofile(MOD_DIR .. "\\Scripts\\vehicle_sets.lua")
-- CTF flags and team armour in their team's colours (Teams.init in
-- initialize, once main.lua's helpers exist).
local Teams = dofile(MOD_DIR .. "\\Scripts\\teams.lua")
-- A load's steps spread over frames (spawnDecor).
local Dress = dofile(MOD_DIR .. "\\Scripts\\dress.lua")

--- Installed maps live beside the mods, not in this mod's own folder (the
--- launcher digests that to spot tampering): <ue4ss>\MJOLNIRMaps\<CODE>\,
--- written by the launcher from map packs (docs/map_distribution.md).
local MAPS_DIR = (MOD_DIR:match("^(.*)\\Mods\\[^\\]*$") or MOD_DIR) .. "\\MJOLNIRMaps"

local function levelPathFor(scenario)
    local installed = MAPS_DIR .. "\\" .. scenario .. "\\level.json"
    local f = io.open(installed, "rb")
    if f then
        f:close()
        return installed
    end
    -- A map converted on this machine with --install, or a test level.
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
-- EShadowCacheInvalidationBehavior::Rigid
local SHADOW_CACHE_RIGID = 2

local function Log(msg)
    print("[MJOLNIR LevelLoader] " .. tostring(msg) .. "\n")
end

--- Actors of one class, as NotifyOnNewObject reports them, by address.
--- FindAllOf walks every object in the game (~20 ms on a converted map), too
--- slow for anything periodic: it runs once, as a watch is armed, for the
--- actors made before it. An actor leaves its set when it is gone.
local function track(set, actor)
    local ok, address = pcall(function() return actor:GetAddress() end)
    if ok and address then set[address] = actor end
end

local function liveIn(set)
    local list = {}
    for address, actor in pairs(set) do
        if actor:IsValid() then list[#list + 1] = actor else set[address] = nil end
    end
    return list
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

--- The first local player's controller, read through the engine: a few
--- property reads. FindAllOf walks every object in the game, ~20 ms on a
--- converted map (200,000 objects, 2026-10-02); the pulse and event loops
--- asking for it held the game thread at 23 ms a frame with the GPU at 2.
--- It is the right controller, too: FindAllOf lists the frontend's leftover
--- one first.
local Engine = nil
local function getPlayerController()
    if not (Engine and Engine:IsValid()) then
        Engine = FindFirstOf("GameEngine")
        if not (Engine and Engine:IsValid()) then return nil end
    end
    local ok, pc = pcall(function()
        return Engine.GameViewport.GameInstance.LocalPlayers[1].PlayerController
    end)
    if ok and pc and pc:IsValid() then return pc end
    return nil
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
    textures = {},     -- runtime textures, by file (see importTexture)
    spawned = 0,
    failed = 0,
    -- Set once the world has been furnished. Decor counts cannot say so: a
    -- level with no decor spawns nothing, and furnishing again every tick
    -- re-spawned the environment and re-sent fade_in every 1.5 s.
    furnished = false,
    -- Set once fade_in has been asked for; it waits for the player, while the
    -- terrain and sky go in as soon as the world is known.
    faded = false,
    -- Set once the game type has been announced (see playEvent).
    announced = false,
    fileMissing = false,
    -- Decor whose material follows a CE periodic function (a beacon's flare
    -- pulsing with its light): { mid, param, base, fn, period }.
    pulses = {},
    -- Sounds on a machine's moving part (spawnSounds): { comp, pos, pivot,
    -- t0, t1, s0, s1, period, position }, moved by moveSounds.
    movingSounds = {},
    -- Decor that turns about a pivot (a Halo 2 gear: Ascension's antennas;
    -- level.decor[].motion): { actor, rest, pivot, period, keys }, turned
    -- by the "turning machines" loop.
    turning = {},
    -- The simulation's machine actors a turning mesh rides, by full name:
    -- one mesh each.
    claimed = {},
    -- Level sounds that follow the game's volume sliders (spawnSounds):
    -- { comp, gain, category, volume }, kept in step by syncVolumes.
    volumed = {},
    -- CE material instances told the sun's illuminance (runtimeMaterial),
    -- for `mjolnir_light_scale`.
    sunMids = {},
    -- Material instances with a level file's `scalars` (scalarMid), by
    -- source material, shared by every decor piece and foliage group that
    -- asks for the same values.
    scalarMids = {},
    -- Baked decor pieces (MJDecor_<id>) given scalar instances in this
    -- world, by id: a reload puts back the mesh's own materials on these
    -- alone. A piece fresh from the world has its mesh's own already.
    bakedMids = {},
    -- The dressing under way (spawnDecor): its number, raised by every new
    -- dressing and by anything that makes the one under way stale (another
    -- world, a reload, a clear), and whether one is running.
    dressGen = 0,
    dressing = false,
    -- The world the level was furnished in (spawnDecor), for the loops that
    -- need a world context: getWorld() reads a dozen properties and leaves
    -- ~1.5 KB of handles behind a call.
    world = nil,
    -- The one table every call with a hit-result out parameter is handed
    -- (K2_SetActorTransform's SweepHitResult and the like). UE4SS keeps a
    -- registry reference to an out parameter's table and never lets it go:
    -- a fresh {} a call left 7,733 FHitResult tables (13 objects each) live
    -- on Death Island, all marked again by every garbage collection, and a
    -- 10 Hz loop added one a run. One shared table: nothing piles up.
    -- Hand it over through Current.emptyHit(), never as it is: see there.
    hit = {},
}

--- Current.hit emptied, for a call's hit-result out parameter. UE4SS writes
--- the call's FHitResult back into the table, and the next call pushes
--- every field in it into the parameter first. Three of them are weak
--- object pointers (Component, PhysMaterial, HitObjectHandle's
--- ReferenceObject), which UE4SS cannot set: each logged
--- "[push_weakobjectproperty] Operation::Set is not supported", three lines
--- a move, ~822,000 in a 10-minute CTF match on Chill Out from the flag
--- cloth alone (2026-11-07). Emptied, a move also cost a quarter of the
--- time (300 in 6 ms, not 22 with their 900 log lines), and no more
--- garbage: UE4SS writes fresh tables for the result's vectors every call
--- either way.
--- A function on Current rather than a local: main.lua is at Lua's 200.
function Current.emptyHit()
    local hit = Current.hit
    for k in pairs(hit) do hit[k] = nil end
    return hit
end

--- The world's Landscape, looked up once a world. Four steps of a load
--- each asked FindFirstOf("Landscape"), a walk of every object in the game
--- (~20 ms on a converted map); GameplayStatics' GetActorOfClass looks only
--- at the world's actors of that class. FindFirstOf stays as the fallback
--- should that call fail. Nil when the world has none.
function Current.landscapeActor(world)
    local land = Current.landscape
    if land and land:IsValid() then return land end
    land = nil
    local ok = pcall(function()
        local gs = findObject("/Script/Engine.Default__GameplayStatics")
        local cls = findObject("/Script/Landscape.Landscape")
        if not (gs and cls and world) then error("no class") end
        land = gs:GetActorOfClass(world, cls)
    end)
    if not ok then land = FindFirstOf("Landscape") end
    if land and land:IsValid() then
        Current.landscape = land
        return land
    end
    return nil
end

--- A load's steps, timed (os.clock: wall time on Windows). A converted
--- map's dressing held the game thread 1.5 s on Timberland, and which step
--- took it was a guess (docs/lua_native_audit.md). Current.lapStart() as a
--- world's load begins, Current.lap(name) after each step (the time since
--- the last lap), Current.lapDone() logs them once. Laps outside a load
--- (a console command's) are not kept.
function Current.lapStart()
    local now = os.clock()
    Current.laps = { at = now, started = now }
end

function Current.lap(name)
    local laps = Current.laps
    if not laps then return end
    local now = os.clock()
    laps[#laps + 1] = { name = name, ms = (now - laps.at) * 1000 }
    laps.at = now
end

function Current.lapDone(frames)
    local laps = Current.laps
    if not laps then return end
    Current.laps = nil
    -- A step done a slice a frame laps once a slice: summed by name, in
    -- the order the steps first ran.
    local order, sums, longest = {}, {}, { name = "none", ms = 0 }
    for _, l in ipairs(laps) do
        if not sums[l.name] then order[#order + 1] = l.name end
        sums[l.name] = (sums[l.name] or 0) + l.ms
        if l.ms > longest.ms then longest = l end
    end
    local parts = {}
    for _, name in ipairs(order) do
        if sums[name] >= 1 then parts[#parts + 1] = string.format("%s %.0f", name, sums[name]) end
    end
    Log(string.format("load timing on %s: %.0f ms from the world to dressed%s, longest single run %s %.0f ms; ms: %s",
        tostring(Current.scenario), (os.clock() - laps.started) * 1000, frames or "", longest.name, longest.ms,
        table.concat(parts, ", ")))
end

local function resetState()
    Current.worldName = nil
    Current.scenario = nil
    Current.level = nil
    Current.actors = {}
    Current.textures = {}
    Current.spawned = 0
    Current.failed = 0
    Current.furnished = false
    Current.faded = false
    Current.announced = false
    Current.packDressed = false
    Current.fileMissing = false
    Current.pulses = {}
    Current.movingSounds = {}
    Current.turning = {}
    Current.claimed = {}
    Current.volumed = {}
    Current.soundSet = nil
    Current.sunMids = {}
    Current.scalarMids = {}
    Current.bakedMids = {}
    Current.foliageDressed = nil
    Current.rocksHidden = nil
    Current.broken = nil
    Current.breakPreloaded = nil
    Current.dressGen = Current.dressGen + 1
    Current.dressing = false
    Current.dressQueue = nil
    Current.meshScan = nil
    Current.landscape = nil
    Current.water = nil
    Current.weatherHidden = nil
    Current.weatherAt = nil
    Current.world = nil
    Current.skyRecapture = nil
    Current.fluxPending = nil
    -- The console variables a level changed (the sun's shadows,
    -- spawnEnvironment) back as the game had them.
    if Current.cvars then
        pcall(function()
            local ks = findObject("/Script/Engine.Default__KismetSystemLibrary")
            for name, value in pairs(Current.cvars) do
                ks:ExecuteConsoleCommand(getWorld(), string.format("%s %g", name, value), getPlayerController())
            end
        end)
        Current.cvars = nil
    end
    -- The flags and Spartans of the last world (teams.lua).
    Teams.reset()
end

local function clearActors()
    -- Reloads keep the world but replace its actors. Invalidate any pending
    -- capture before destroying them, and allow the replacement sky to capture.
    Current.skyRecapture = nil
    -- A dressing under way stops at its next step; a cleared world counts
    -- as dressed, so the watcher does not dress it again.
    Current.dressGen = Current.dressGen + 1
    if Current.dressing then Current.furnished = true end
    Current.dressing = false
    Current.dressQueue = nil
    Current.meshScan = nil
    for _, actor in pairs(Current.actors) do
        if actor and actor:IsValid() then
            -- Sounds are components, not actors.
            if not pcall(function() actor:K2_DestroyActor() end) then
                pcall(function() actor:Stop() end)
                pcall(function() actor:K2_DestroyComponent(actor) end)
            end
        end
    end
    Current.actors = {}
    Current.broken = nil
    Current.sunMids = {}
    Current.scalarMids = {}
    Current.movingSounds = {}
    Current.turning = {}
    Current.claimed = {}
    Current.volumed = {}
    Current.soundSet = nil
    Current.spawned = 0
    Current.failed = 0
end

--------------------------------------------------------------------------------
-- Loading and validation
--------------------------------------------------------------------------------

--- B30's ground (level.landscape.pbr) is Megascans surfaces made for
--- daylight; under a CE dusk (Death Island's weak sun and purple sky) the
--- sand went mauve and its shade navy. `pbr.light` { sun = { scale, tint },
--- sky = { scale, tint } } scales and tints the level's sun and sky light
--- here, as the file is read, so the CE masters (told the sun's colour and
--- strength, runtimeMaterial's Sun* parameters) agree with the lights spawned.
local function landscapeLight(level)
    local land = type(level.landscape) == "table" and level.landscape
    local light = land and type(land.pbr) == "table" and land.pbr.light
    local env = level.environment
    if type(light) ~= "table" or type(env) ~= "table" then return end
    if type(land.pbr.haze) == "table" then env.haze = land.pbr.haze end
    for key, envKey in pairs({ sun = "sun", sky = "skylight" }) do
        local change, target = light[key], env[envKey]
        if type(change) == "table" and type(target) == "table" then
            if type(change.scale) == "number" and type(target.intensity) == "number" then
                target.intensity = target.intensity * change.scale
            end
            if type(change.tint) == "table" then
                local c = type(target.color) == "table" and target.color or { 1, 1, 1 }
                target.color = { (c[1] or 1) * (change.tint[1] or 1), (c[2] or 1) * (change.tint[2] or 1),
                    (c[3] or 1) * (change.tint[3] or 1) }
            end
        end
    end
end

--- The level file a travel decoded, kept for the load that follows
--- (level_files.lua): one decode a map, not two.
local LevelFiles = dofile(MOD_DIR .. "\\Scripts\\level_files.lua").new(Json.decode)

--- Decode and sanity-check a level file. Full validation is the CLI's job
--- (`mjolnir level validate`); the loader checks only what it consumes.
local function loadLevelFile(scenario, fileKey)
    local path = levelPathFor(fileKey or scenario)
    local raw = readFile(path)
    if not raw then return nil, "no file: " .. path end

    local ok, level = LevelFiles.decode(path, raw, true)
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
    -- Files the level names (its foliage) sit beside it.
    level._dir = path:match("^(.*)\\[^\\]+$")
    landscapeLight(level)
    return level
end

--- The level file for the running world: the scenario tag's own file when
--- one is loaded, else the world's.
local function loadCurrentLevelFile(scenario)
    local tag = scenarioTagOf()
    Current.lap("scenario tag")
    if tag then
        local level = loadLevelFile(scenario, tag)
        -- The tag outlives its map: on a fireteam client the map just left
        -- is still loaded at the menu, and its level was furnished behind
        -- the menu and its game type announced again (playtest,
        -- 2026-10-03). The tag's file counts only on its own world or on
        -- the world its canvas names.
        if level and tag ~= scenario and string.upper(level.canvas.scenario) ~= scenario then
            level = nil
        end
        if level then
            if tag ~= scenario then
                Log(string.format("scenario tag %s has its own level file", tag))
            end
            return level
        end
    end
    -- A player who joins a match under way has no scenario tag object (its
    -- game was started from the session, not by a travel), so the tag cannot
    -- name the file. An installed map's folder is named for the codename of
    -- the world it runs on, which says the same thing.
    if not tag then
        local f = io.open(MAPS_DIR .. "\\" .. scenario .. "\\level.json", "rb")
        if f then
            f:close()
            return loadLevelFile(scenario, scenario)
        end
    end
    return loadLevelFile(scenario)
end

--------------------------------------------------------------------------------
-- Decor spawning
--------------------------------------------------------------------------------

--- Whether a watch that has not armed may try again now. NotifyOnNewObject
--- on a class not loaded yet raises after looking the class up, a walk of
--- every object; retried from 1.5 s loops up to four times a pass, it was
--- part of the CTF freeze (playtest, 2026-10-03). Once every 10 s per watch.
local ArmAt = {}
local function mayArm(name)
    if os.clock() < (ArmAt[name] or 0) then return false end
    ArmAt[name] = os.clock() + 10
    return true
end

--- Assets resolved this world, by path, and paths that would not load.
--- A lookup of a path that is not in memory walks every object in the game
--- (18.7 ms on a converted map), and the loads after it block: re-dressing
--- the Spartans every 3 s missed all seven Mk V meshes each time and froze a
--- CTF host for ~250 ms every 3.24 s (playtest, 2026-10-03). A path that
--- does not load is not tried again until the next world.
local Resolved, Unresolved = {}, {}

--- Resolve a mesh object path, loading the asset if it is not in memory.
--- Never called on world packages: decor mesh paths are object paths into
--- /Engine or /Game mesh packages (LoadAsset on a world package crashes).
local function resolveMesh(path)
    -- A Lua handle does not keep its object: after a garbage collection the
    -- address may hold something else, so the name has to match too.
    local known = Resolved[path]
    if known then
        local ok, name = pcall(function() return known:IsValid() and known:GetFullName() end)
        if ok and type(name) == "string" and name:sub(-#path) == path then return known end
        Resolved[path] = nil
    end
    if Unresolved[path] then return nil end
    -- A soft-path blocking load first: it hands back an object already in
    -- memory in ~0.03 ms and loads one in ~1 ms, where StaticFindObject
    -- took ~21 ms a path, loaded or not. Death Island's terrain resolves 124
    -- textures: 3.5 s of its load frame were these lookups (2026-10-18).
    local ok, loaded = pcall(function()
        local ksl = Resolved["\0ksl"]
        if not (ksl and ksl:IsValid()) then
            ksl = findObject("/Script/Engine.Default__KismetSystemLibrary")
            Resolved["\0ksl"] = ksl
        end
        return ksl:LoadAsset_Blocking(ksl:Conv_SoftObjPathToSoftObjRef(ksl:MakeSoftObjectPath(path)))
    end)
    if ok and loaded and loaded:IsValid() then
        Resolved[path] = loaded
        return loaded
    end
    -- The soft path does not take a name with a number (SM_..._Big_6):
    -- UE4SS's LoadAsset does, for what the game's AssetRegistry lists (none
    -- of our own packages, which the soft path loads).
    ok, loaded = pcall(function() return LoadAsset(path) end)
    if ok and loaded and loaded:IsValid() then
        Resolved[path] = loaded
        return loaded
    end
    local mesh = findObject(path)
    if mesh then
        Resolved[path] = mesh
        return mesh
    end
    Unresolved[path] = true
    Log("asset not found, not tried again on this map: " .. path)
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
--- Runtime textures. A texture value that is not an object path ("/Game/...")
--- is an image file under the mod folder (or an absolute path), read with
--- ImportFileAsTexture2D. That gives a transient texture with one mip, which
--- shimmers wherever it tiles into the distance, so by default it is drawn
--- once into a render target that generates its own mips, and the render
--- target is what the material samples. Nothing here is cooked: it is how
--- converted maps carry their classic textures (docs/ce_map_conversion.md).
--- Cached per world by path, so slots that share a texture share one copy.
local ETRT_RGBA8, ETRT_RGBA8_SRGB = 2, 3
local BLEND_OPAQUE = 0

local function isObjectPath(value)
    return value:sub(1, 1) == "/"
end

local function textureFile(value)
    if value:match("^%a:[/\\]") then return value end
    local rel = value:gsub("/", "\\")
    -- A map's own files (its decals' textures) sit beside its level file.
    local dir = Current.level and Current.level._dir
    if dir then
        local f = io.open(dir .. "\\" .. rel, "rb")
        if f then
            f:close()
            return dir .. "\\" .. rel
        end
    end
    return MOD_DIR .. "\\" .. rel
end

--- A dynamic M_CE_LinearCopy over `tex` (importTexture's linear path), or
--- nil without the trial masters.
local function linearCopy(world, tex)
    local master = resolveMesh("/Game/MJOLNIR/CETrial/M_CE_LinearCopy.M_CE_LinearCopy")
        or resolveMesh("/Game/MJOLNIR/CE/M_CE_LinearCopy.M_CE_LinearCopy")
    local kml = findObject("/Script/Engine.Default__KismetMaterialLibrary")
    if not (master and kml) then return nil end
    local mid = kml:CreateDynamicMaterialInstance(world, master, FName("ce_linear_copy"), 0)
    if not (mid and mid:IsValid()) then return nil end
    mid:SetTextureParameterValue(FName("Src"), tex)
    return mid
end

--- A file's size, as a cheap signature that it changed on disk.
local function fileSize(path)
    local f = io.open(path, "rb")
    if not f then return nil end
    local n = f:seek("end")
    f:close()
    return n
end

local function importTexture(world, value, linear)
    -- Keyed by the file's size too: a bake rewritten on disk is read again,
    -- an unchanged one never is. Every page read again on every respawn
    -- (dropping the cache) was followed twice by a GPU crash (2026-10-06).
    local key = value .. (linear and "|linear" or "") .. "|" .. tostring(fileSize(textureFile(value)))
    local cached = Current.textures[key]
    if cached and cached:IsValid() then return cached end
    local krl = findObject("/Script/Engine.Default__KismetRenderingLibrary")
    if not krl then return nil, "KismetRenderingLibrary missing" end
    local okImport, tex = pcall(function()
        return krl:ImportFileAsTexture2D(world, textureFile(value))
    end)
    if not okImport or not tex or not tex:IsValid() then
        return nil, "could not read " .. textureFile(value)
    end
    local result = tex
    local okMips = pcall(function()
        local w, h = tex:Blueprint_GetSizeX(), tex:Blueprint_GetSizeY()
        local rt = krl:CreateRenderTarget2D(world, w, h, linear and ETRT_RGBA8 or ETRT_RGBA8_SRGB,
            { R = 0, G = 0, B = 0, A = 1 }, true, false)
        if not rt or not rt:IsValid() then error("no render target") end
        -- UE4SS hands the out parameters back in the first table: the canvas
        -- as `Canvas` (with the size beside it).
        local out, context = {}, {}
        -- The import is always sRGB, so a linear texture (a bake page, a sun
        -- mask) goes through M_CE_LinearCopy, which re-encodes what the
        -- sampler decoded: drawn as it is, 128 in the file arrived as 55.
        local copy = linear and linearCopy(world, tex)
        krl:BeginDrawCanvasToRenderTarget(world, rt, out, context, {})
        if copy then
            out.Canvas:K2_DrawMaterial(copy, { X = 0, Y = 0 }, { X = w, Y = h }, { X = 0, Y = 0 }, { X = 1, Y = 1 },
                0.0, { X = 0.5, Y = 0.5 })
        else
            if linear then Log("texture " .. value .. ": no M_CE_LinearCopy, so it reads sRGB-decoded (too dark)") end
            out.Canvas:K2_DrawTexture(tex, { X = 0, Y = 0 }, { X = w, Y = h }, { X = 0, Y = 0 }, { X = 1, Y = 1 },
                { R = 1, G = 1, B = 1, A = 1 }, BLEND_OPAQUE, 0.0, { X = 0.5, Y = 0.5 })
        end
        krl:EndDrawCanvasToRenderTarget(world, { RenderTarget = rt })
        result = rt
    end)
    if not okMips then Log("texture " .. value .. ": no mip chain, using the single-mip import") end
    Current.textures[key] = result
    return result
end

--- Terrain shadow experiment. A converted level's terrain casts no shadows
--- (its own are in the CE lightmaps, build_terrain_meshes.py), so nothing in
--- it blocks the Unreal sun: a player on a platform shadows the ground under
--- it, and a player under one stands in full sun. `mjolnir_terrain_shadows
--- on` lets the terrain cast, to see what that costs: the materials still
--- drop their sun share (ShadowStrength) wherever the sun is blocked, so the
--- lightmaps' own shadows darken a second time. An optional strength sets
--- that share on every terrain material, to weigh the one against the other.
--- `lightmap` instead gives the materials the level's lightmap levels in
--- CE's shadow and sun (LightmapSun, build_ce_materials.py SUN_WEIGHT_CODE),
--- so a baked shadow gives up nothing: with the terrain still casting
--- nothing, an object's shadow no longer shows through a roof onto ground
--- CE had in shade, and the level otherwise looks as it did (Blood Gulch,
--- 2026-10-04: the Banshee on the base roof). Until the runtime pack's
--- masters carry that, it needs the trial masters
--- (MJ_CE_ROOT=/Game/MJOLNIR/CETrial, chunk 983). Off by default; it lasts
--- until the game closes, maps loaded later included.
local TerrainShadows = { cast = false, strength = nil, lightmap = nil, proxy = false, ao = nil }
local TRIAL_MASTERS = "/Game/MJOLNIR/CETrial/"

--- Game detail experiment (`mjolnir_terrain_detail`, 2026-10-11): a CE
--- surface whose detail map is one of GameDetail.surfaces' is drawn with the
--- game's own surface instead (Campaign Evolved's B30 beach: Megascans sand
--- and grass), through the trial masters' GameDetail path
--- (build_ce_materials.py GAME_DETAIL_CODE): the game's albedo as the
--- detail map's grain, the base map keeping the level's colours, and its
--- normal map in the bump shading. Off by default; it lasts until the game
--- closes. `params` are scalars set on every such slot (GameTile,
--- GameDetailStrength, GameNormalStrength, GameAlbedoGain); at the master's
--- 1 the game's grain was faint under Death Island's base map, 2 shows it.
--- Each surface says how much of CE's colour it keeps (`keep`: the sand
--- 0.2, its base map smeared it; the grass 0.85, B30's is a desaturated
--- albedo for tinting) and may name a second albedo (`b`) blended in over
--- patches tens of metres across and, as a primary detail, a rippled one
--- (`w`, `wn`: albedo and normal) for the band just above the sea. Slots also get GameWet (the sea's height,
--- from the level's water mesh): wet sand just above the waterline.
local GameDetail = { on = false, params = { GameDetailStrength = 2.0 } }
do
    -- (A block: the file is at Lua's 200 locals.)
    local MEGASCANS = "/Game/Megascans/Surfaces/"
    GameDetail.surfaces = {
        T_levels_b30_bitmaps_detail_sand = {
            d = MEGASCANS .. "Thai_Beach_Sand_tefgafrk/T_Thai_Beach_Sand_tefgafrk_2K_NSVT_D.T_Thai_Beach_Sand_tefgafrk_2K_NSVT_D",
            n = MEGASCANS .. "Thai_Beach_Sand_tefgafrk/T_Thai_Beach_Sand_tefgafrk_2K_NSVT_N.T_Thai_Beach_Sand_tefgafrk_2K_NSVT_N",
            b = MEGASCANS .. "Beach_Sand_xdheagk/T_Beach_Sand_xdheagk_2K_NSVT_D.T_Beach_Sand_xdheagk_2K_NSVT_D",
            w = MEGASCANS .. "Thai_Rippled_Beach_Sand_vb1ldadn/T_Thai_Rippled_Beach_Sand_vb1ldadn_2K_NSVT_D.T_Thai_Rippled_Beach_Sand_vb1ldadn_2K_NSVT_D",
            wn = MEGASCANS .. "Thai_Rippled_Beach_Sand_vb1ldadn/T_Thai_Rippled_Beach_Sand_vb1ldadn_2K_NSVT_N.T_Thai_Rippled_Beach_Sand_vb1ldadn_2K_NSVT_N",
            keep = 0.2,
        },
        T_levels_a30_bitmaps_detail_grass = {
            d = MEGASCANS .. "Ground_Grass_tb3nce2k/T_Ground_Grass_tb3nce_Desat_4K_NSVT_D.T_Ground_Grass_tb3nce_Desat_4K_NSVT_D",
            n = MEGASCANS .. "Ground_Grass_tb3nce2k/T_Ground_Grass_NSVT_4K_N.T_Ground_Grass_NSVT_4K_N",
            keep = 0.85,
        },
    }
end

--- The game surfaces for a CE environment spec's detail maps, as
--- { Primary = surface, Secondary = surface } (either may be absent), or nil.
function GameDetail.surfacesFor(spec)
    if not GameDetail.on or type(spec.textures) ~= "table" then return nil end
    local found = nil
    for _, slot in ipairs({ "Primary", "Secondary" }) do
        local leaf = type(spec.textures[slot]) == "string" and spec.textures[slot]:match("%.([%w_]+)$")
        if leaf and GameDetail.surfaces[leaf] then
            found = found or {}
            found[slot] = GameDetail.surfaces[leaf]
        end
    end
    return found
end

--- Dynamic lights on the terrain (`mjolnir_terrain_lights`), on by default
--- for converted levels since 2026-10-06. Unreal draws the terrain's direct
--- light (UnrealLit: the runtime pack's CE environment masters,
--- build_ce_materials.py SUNLIT_CODE) over CE's sunlit colour and bump map,
--- CE's lightmap stays its ambient, the terrain joins lighting channel 0 with
--- the game's lights, its shadow copy keeps the sun out of what the geometry
--- shades, and the level's sun takes the map's sun mask (environment.sun_mask,
--- M_CE_SunLight) so CE's broad soft shadows stay. `hybrid` is the earlier
--- mode (the sun share topped up for the other lights), `trial` the trial
--- masters (chunk 983) over a bake in bake\ beside this mod, `off` CE's
--- unlit terrain. Lasts until the game closes.
--- `margin` sets how far (bake texels) CE's sun and shade are pulled in
--- from their edges, where the copy's shadow and the bake disagree.
local TerrainLights = { on = true, albedo = 1.0, proxy = true, margin = nil, fill = false, unreal = true, trial = false }

local function proxyWanted()
    return TerrainShadows.proxy or (TerrainLights.on and TerrainLights.proxy)
end

--- The level's lightmap levels { shadow, sunlit }: the experiment's, else
--- the level's own (environment.sun.lightmap_sun), else nil.
local function lightmapSun()
    if TerrainShadows.lightmap then return TerrainShadows.lightmap end
    local env = Current.level and Current.level.environment
    local sun = type(env) == "table" and env.sun
    local v = type(sun) == "table" and sun.lightmap_sun
    if type(v) == "table" and type(v[1]) == "number" and type(v[2]) == "number" then return v end
    return nil
end

--- The scene's light scale. A converted level is drawn at a fixed exposure
--- of about 1 (environment.post) under a sun of a few lux, so CE's colours
--- land on the screen as they are. The game's own lights are physical and
--- tuned for its auto exposure (EV100 -2.5 to 16, a daylight mission near
--- 13): a Warthog headlight is 18 EV, some 32,000 cd, 160 times the level's
--- sun at 5 m, and turned whatever it reached white (Blood Gulch,
--- 2026-10-05). So the sun and sky light are multiplied by this and the
--- exposure divided by it: the CE materials divide by the camera's exposure
--- (and are told the sun's real illuminance, runtimeMaterial), so the level
--- looks the same, while the game's lights, effects and emissive surfaces
--- come down to their designed strength against it. 1 is the old scene;
--- 2^13 would be daylight, where a headlight barely shows. Needs the fixed
--- exposure: without environment.post the scale is 1.
local DEFAULT_LIGHT_SCALE = 256
local LightScale = { value = nil } -- `mjolnir_light_scale`, until the game closes

local function lightScale()
    local env = Current.level and Current.level.environment
    if type(env) ~= "table" or type(env.post) ~= "table" or not env.post.manual_exposure then return 1.0 end
    local k = LightScale.value or env.light_scale or DEFAULT_LIGHT_SCALE
    return (type(k) == "number" and k > 0) and k or 1.0
end

--- What the CE masters are told the sun is (runtimeMaterial, SunIlluminance).
local function sunIlluminance(sun)
    return (sun.intensity or 8.0) * (sun.response or 0.7) * lightScale()
end

--- The switch that turns a CE master's texture parameter off.
local HAS_PARAM = {
    Primary = "HasPrimary", Secondary = "HasSecondary", Micro = "HasMicro", Bump = "HasBump",
    Lightmap = "HasLightmap", SelfIllumMap = "HasSelfIllum", Multipurpose = "HasMulti",
    ReflectionCube = "HasReflection", Bake = "HasBake",
}

--- A runtime material: `{ "parent": "/Game/.../MI_X.MI_X", "textures":
--- { "Diffuse": "textures/bgl/ground.png", "Normal": "/Engine/..." },
--- "scalars": { "RoughnessMult": 1.0 }, "linear": ["Normal"] }`. Texture
--- parameters named in `linear` are imported without sRGB (normal maps).
--- With `target` (Land.apply's landscape), the parameters go to it instead
--- of a new instance.
local function runtimeMaterial(world, spec, name, target)
    local kml = findObject("/Script/Engine.Default__KismetMaterialLibrary")
    local parent = nil
    -- The lightmap experiment draws the CE environment masters with the
    -- trial build, when it is installed.
    local game = GameDetail.surfacesFor(spec)
    -- A ground slot a Landscape draws (level.landscape.cut, by its base
    -- map): the trial's masked master, which keeps only the landscape's holes.
    local land = Current.level and Current.level.landscape
    local cut = not target and type(land) == "table" and type(land.cut) == "table"
        and type(spec.textures) == "table" and spec.textures.Base ~= nil and land.cut or nil
    if cut then
        local hit = spec.textures.Base == cut.base
        for _, b in ipairs(type(cut.bases) == "table" and cut.bases or {}) do hit = hit or spec.textures.Base == b end
        -- `cut.slots`: the ground's slots exactly (the name ends in the
        -- slot): Ice Fields' ice caves share its ground's base map, and cut
        -- by the landscape's mask they opened holes in the tunnels.
        if hit and type(cut.slots) == "table" then
            local slot = tonumber(tostring(name):match("_(%d+)$"))
            local listed = false
            for _, s in ipairs(cut.slots) do listed = listed or s == slot end
            -- A look that keeps its slot whole (LandCutEdge below 0: Ice
            -- Fields' ice caves) keeps it whole here too: this material is
            -- also the terrain's shadow proxy's, and cut it let the sun
            -- through the tunnels' roof in the landscape's steps.
            for _, look in ipairs(type(cut.looks) == "table" and cut.looks or {}) do
                local whole = type(look.scalars) == "table" and (look.scalars.LandCutEdge or 0) < 0
                for _, s in ipairs(whole and type(look.slots) == "table" and look.slots or {}) do
                    if s == slot then listed = false end
                end
            end
            hit = listed
        end
        if not hit then cut = nil end
    end
    local master = (TerrainShadows.lightmap or TerrainLights.trial or game or cut) and type(spec.parent) == "string"
        and spec.parent:match("^/Game/MJOLNIR/CE/(M_CE_Environment[%w]*%.M_CE_Environment[%w]*)$")
    if cut and master then
        local sides = master:match("^M_CE_Environment(%w*)%.")
        if sides and not sides:find("Masked", 1, true) then
            master = "M_CE_EnvironmentMasked" .. sides .. ".M_CE_EnvironmentMasked" .. sides
        end
    end
    if master then parent = resolveMesh(TRIAL_MASTERS .. master) end
    parent = parent or (type(spec.parent) == "string" and resolveMesh(spec.parent))
    -- A master newer than the installed runtime pack (M_CE_Plasma,
    -- 2026-10-13): the trial build's copy, when that is installed.
    if not parent and type(spec.parent) == "string" then
        local leaf = spec.parent:match("^/Game/MJOLNIR/CE/([%w_]+%.[%w_]+)$")
        if leaf then parent = resolveMesh(TRIAL_MASTERS .. leaf) end
    end
    -- Halo 2's camera-facing sprites (M_H2_Billboard, chunk 981) on a
    -- runtime pack from before it: still cards, drawn unturned.
    if not parent and spec.parent == "/Game/MJOLNIR/H2/M_H2_Billboard.M_H2_Billboard" then
        parent = resolveMesh("/Game/MJOLNIR/CE/M_CE_EnvironmentMaskedTwoSided.M_CE_EnvironmentMaskedTwoSided")
    end
    local mid = target
    if not mid then
        if not kml or not parent then return nil, "parent material not found: " .. tostring(spec.parent) end
        mid = kml:CreateDynamicMaterialInstance(world, parent, FName(name), 0)
    end
    if not mid or not mid:IsValid() then return nil, "no dynamic instance" end
    local linear = {}
    for _, p in ipairs(spec.linear or {}) do linear[p] = true end
    -- A texture the map pack never cooked costs the material that texture,
    -- not the whole material: dropped, its Has* switch off, the rest drawn
    -- (Infinity's pack shipped without two multipurpose maps, and its
    -- boulders and leaves fell back to the donor's flat material).
    local missing = {}
    for param, value in pairs(spec.textures or {}) do
        local tex, err
        if isObjectPath(value) then
            tex = resolveMesh(value)
            err = "texture not found: " .. value
        else
            tex, err = importTexture(world, value, linear[param])
        end
        if tex then
            mid:SetTextureParameterValue(FName(param), tex)
        else
            missing[#missing + 1] = param
            Log(string.format("material '%s': %s (drawn without it)", name, tostring(err)))
        end
    end
    for param, value in pairs(spec.scalars or {}) do
        mid:SetScalarParameterValue(FName(param), value)
    end
    if cut and master then
        local mask = type(cut.mask) == "string" and resolveMesh(cut.mask)
        local r = type(cut.rect) == "table" and cut.rect
        if mask and r then
            mid:SetTextureParameterValue(FName("LandMask"), mask)
            mid:SetVectorParameterValue(FName("LandRect"), { R = r[1], G = r[2], B = r[3], A = r[4] })
            mid:SetScalarParameterValue(FName("LandMaskSize"), cut.size or 505)
            mid:SetScalarParameterValue(FName("AlphaTest"), 0.0)
            mid:SetScalarParameterValue(FName("LandCut"), 1.0)
            if type(cut.edge) == "number" then mid:SetScalarParameterValue(FName("LandCutEdge"), cut.edge) end
        else
            Log(string.format("material '%s': landscape cut mask not found: %s", name, tostring(cut.mask)))
        end
    end
    if game and master then
        local n = 0
        for slot, surface in pairs(game) do
            local d, nrm = resolveMesh(surface.d), resolveMesh(surface.n)
            if d and nrm then
                mid:SetTextureParameterValue(FName("Game" .. slot), d)
                mid:SetTextureParameterValue(FName("Game" .. slot .. "N"), nrm)
                mid:SetScalarParameterValue(FName("HasGame" .. slot), 1.0)
                mid:SetScalarParameterValue(FName("Game" .. slot .. "Keep"), surface.keep or 1.0)
                local b = surface.b and resolveMesh(surface.b)
                if b then
                    mid:SetTextureParameterValue(FName("Game" .. slot .. "B"), b)
                    mid:SetScalarParameterValue(FName("HasGame" .. slot .. "B"), 1.0)
                end
                local w, wn = surface.w and resolveMesh(surface.w), surface.wn and resolveMesh(surface.wn)
                if slot == "Primary" and w and wn then
                    mid:SetTextureParameterValue(FName("GamePrimaryW"), w)
                    mid:SetTextureParameterValue(FName("GamePrimaryWN"), wn)
                    mid:SetScalarParameterValue(FName("HasGamePrimaryW"), 1.0)
                end
                n = n + 1
            else
                Log(string.format("material '%s': game surface for %s not found", name, slot))
            end
        end
        mid:SetScalarParameterValue(FName("GameDetail"), n > 0 and 1.0 or 0.0)
        -- CE's micro detail goes: the game's surface is the fine grain now,
        -- and Death Island's (detail_ground) left dark blotches a metre or
        -- two across all over the new sand.
        if n > 0 then mid:SetScalarParameterValue(FName("HasMicro"), 0.0) end
        for param, v in pairs(GameDetail.params) do mid:SetScalarParameterValue(FName(param), v) end
        for _, item in ipairs(Current.level and Current.level.decor or {}) do
            if type(item) == "table" and type(item.mesh) == "string" and item.mesh:find("_Water%.")
                and type(item.pos) == "table" then
                local z = item.pos[3] + ((Current.level.canvas or {}).origin or { 0, 0, 0 })[3]
                mid:SetVectorParameterValue(FName("GameWet"), { R = z, G = 60, B = 0.35, A = 0 })
                break
            end
        end
    end
    if TerrainLights.on then
        mid:SetScalarParameterValue(FName("DynamicAlbedo"), TerrainLights.albedo)
        mid:SetScalarParameterValue(FName("SunVisBake"), TerrainLights.proxy and 1.0 or 0.0)
        if TerrainLights.margin then mid:SetScalarParameterValue(FName("BakeMargin"), TerrainLights.margin) end
        mid:SetScalarParameterValue(FName("UnrealLit"), TerrainLights.unreal and 1.0 or 0.0)
        for param, v in pairs(TerrainLights.params or {}) do mid:SetScalarParameterValue(FName(param), v) end
    end
    for _, param in ipairs(missing) do
        local has = HAS_PARAM[param]
        if has then mid:SetScalarParameterValue(FName(has), 0.0) end
        -- A model with no multipurpose map reflects everywhere (CE's rule
        -- for a shader without one); one whose map went missing would turn
        -- to chrome, so it loses the reflection instead.
        if param == "Multipurpose" then mid:SetScalarParameterValue(FName("HasReflection"), 0.0) end
    end
    -- The lightmap experiment's baked corners and sun (ue-texture's
    -- lightmap_bake): one texture per lightmap page, named for the page's
    -- texture, in bake\ beside this mod.
    local lightmap = TerrainShadows.lightmap and type(spec.textures) == "table" and spec.textures.Lightmap
    local leaf = type(lightmap) == "string" and lightmap:match("%.([%w_]+)$")
    if leaf then
        local file = "bake\\" .. leaf .. ".png"
        local f = io.open(textureFile(file), "rb")
        if f then
            f:close()
            local tex = importTexture(world, file, true)
            if tex then
                mid:SetTextureParameterValue(FName("Bake"), tex)
                mid:SetScalarParameterValue(FName("HasBake"), 1.0)
                mid:SetScalarParameterValue(FName("BakeAO"), TerrainShadows.ao or 1.0)
            end
        end
    end
    for param, v in pairs(spec.vectors or {}) do
        if type(v) == "table" then
            mid:SetVectorParameterValue(FName(param), { R = v[1] or 0, G = v[2] or 0, B = v[3] or 0, A = v[4] or 1 })
        end
    end
    -- Object shadows: the CE masters draw a share of their baked colour as
    -- this level's sun (MJOLNIRMaterials build_ce_materials.py,
    -- SUN_WEIGHT_CODE), so they need the sun the environment spawns.
    -- Masters without these parameters ignore them.
    local env = Current.level and Current.level.environment
    local sun = type(env) == "table" and env.sun
    if type(sun) == "table" then
        local p, y = math.rad(sun.pitch or -50.0), math.rad(sun.yaw or 30.0)
        -- The light travels along its forward vector; the material wants
        -- the direction towards it.
        mid:SetVectorParameterValue(FName("SunDir"),
            { R = -math.cos(p) * math.cos(y), G = -math.cos(p) * math.sin(y), B = -math.sin(p), A = 0 })
        local c = type(sun.color) == "table" and sun.color or { 1, 1, 1 }
        mid:SetVectorParameterValue(FName("SunColor"), { R = c[1], G = c[2], B = c[3], A = 1 })
        -- CE's own sun (the sky light's colour x power, environment.sun.ce_light,
        -- gen_ce_level.py): with the solver's ambient page the masters rebuild
        -- each texel's sunlit lightmap from it, per channel, at the texel's N.L.
        local ce = type(sun.ce_light) == "table" and sun.ce_light
        if ce then
            mid:SetVectorParameterValue(FName("SunCE"), { R = ce[1] or 0, G = ce[2] or 0, B = ce[3] or 0, A = 1 })
        end
        -- The lit share comes out at about 0.7 of Lambert's prediction in
        -- this renderer (measured on Blood Gulch: sunlit ground matched with
        -- and without the share only at 0.7), so the material is told the
        -- sun is that much dimmer than the light really is. The material
        -- divides the camera's exposure out of its colour before it works
        -- the share out, so the scene's light scale goes in as well.
        mid:SetScalarParameterValue(FName("SunIlluminance"), sunIlluminance(sun))
        Current.sunMids[#Current.sunMids + 1] = mid
        mid:SetScalarParameterValue(FName("ShadowStrength"), sun.shadow_strength or 0.9)
        local levels = lightmapSun()
        if levels then
            mid:SetVectorParameterValue(FName("LightmapSun"), { R = levels[1], G = levels[2], B = 0, A = 0 })
        end
    end
    return mid
end

--- One slot of applyMaterials: entry `i` of a material list made and set,
--- counted in `st` ({ applied, failed, bounds }). A load sets a spawned
--- piece's slots one at a time, a slice a frame (spawnDecorItem): CE
--- terrain is up to 106 runtime materials on one mesh.
local function applyMaterial(comp, entry, i, world, id, st)
    local mat, err
    if type(entry) == "string" and #entry > 0 then
        mat = resolveMesh(entry)
        err = "not found: " .. entry
    elseif type(entry) == "table" then
        local ok, m, e = pcall(runtimeMaterial, world, entry, string.format("%s_%d", id, i - 1))
        mat, err = ok and m or nil, ok and e or m
        -- A machine's moving part is drawn moved by its material (the CE
        -- device masters' World Position Offset), out past the mesh's own
        -- bounds: the spec's bounds_scale keeps the mesh drawn wherever the
        -- part goes.
        if mat and type(entry.bounds_scale) == "number" then st.bounds = math.max(st.bounds, entry.bounds_scale) end
    end
    if mat then
        if pcall(function() comp:SetMaterial(i - 1, mat) end) then
            st.applied = st.applied + 1
        else
            st.failed = st.failed + 1
        end
    elseif entry ~= "" then
        st.failed = st.failed + 1
        Log(string.format("decor '%s' slot %d: %s", tostring(id), i - 1, tostring(err)))
    end
end

--- After applyMaterial's slots: the bounds the moving parts need. Returns
--- the slots applied and failed.
local function materialsDone(comp, id, st)
    if st.bounds > 1.0 then
        local bounds = st.bounds
        local ok = pcall(function() comp:SetBoundsScale(bounds) end)
        if not ok then ok = pcall(function() comp.BoundsScale = bounds; comp:MarkRenderStateDirty() end) end
        Log(string.format("decor '%s': bounds scale %.2f for its moving machine parts%s", tostring(id), bounds,
            ok and "" or " (could not set)"))
    end
    return st.applied, st.failed
end

local function applyMaterials(comp, list, world, id)
    if type(list) ~= "table" then return 0, 0 end
    local st = { applied = 0, failed = 0, bounds = 1.0 }
    for i, entry in ipairs(list) do applyMaterial(comp, entry, i, world, id, st) end
    return materialsDone(comp, id, st)
end

--- The pieces build_terrain_meshes.py writes ("<map>_terrain",
--- "<map>_terrain_1", ...) less the sky, whose dome would shade the whole map.
local function isTerrain(item)
    return type(item) == "table" and item.cast_shadow == false and item.sort_priority == nil
        and type(item.id) == "string" and item.id:find("_terrain", 1, true) ~= nil
end

--- The sun share to give the terrain materials: the experiment's, else the
--- level's own (runtimeMaterial), else nil to leave them alone.
local function terrainShadowStrength()
    if TerrainShadows.strength then return TerrainShadows.strength end
    local env = Current.level and Current.level.environment
    local sun = type(env) == "table" and env.sun
    if type(sun) == "table" then return sun.shadow_strength or 0.9 end
    return nil
end

local function applyTerrainShadows(actor)
    local comp = actor.StaticMeshComponent
    -- CE BSP surfaces are one-sided: drawn two-sided into the shadow map, a
    -- piece seen edge-on or from behind by the sun still blocks it.
    comp.bCastShadowAsTwoSided = TerrainShadows.cast
    comp:SetCastShadow(TerrainShadows.cast)
    pcall(function() comp:MarkRenderStateDirty() end)
    local strength = terrainShadowStrength()
    if strength == nil then return end
    local name = FName("ShadowStrength")
    -- A transplanted mesh keeps the donor's one slot, so GetNumMaterials says
    -- 1; the terrain's materials are the component's overrides (55 on Blood
    -- Gulch, applyMaterials).
    local count = comp:GetNumMaterials()
    pcall(function() count = math.max(count, comp.OverrideMaterials:GetArrayNum()) end)
    for i = 0, count - 1 do
        local mid = comp:GetMaterial(i)
        if mid and mid:IsValid() then
            pcall(function() mid:SetScalarParameterValue(name, strength) end)
        end
    end
end

--- The terrain's hidden shadow copy (`mjolnir_terrain_shadows proxy`): the
--- solid terrain again, never drawn, casting only, so what stands under a
--- roof (players, vehicles, weapons) is shaded, which the visible terrain,
--- casting nothing, cannot do. Its shadow falls on the terrain too, but with
--- the `lightmap` materials it shows only where CE had sun. Not the
--- translucent pieces (glass, teleporter fields) or the sky.
local function isSolidTerrain(item)
    return isTerrain(item) and type(item.mesh) == "string" and item.mesh:find("_Terrain%.") ~= nil
end

local function spawnShadowProxy(world, item)
    local key = item.id .. "__shadow"
    if Current.actors[key] and Current.actors[key]:IsValid() then return true end
    local source = Current.actors[item.id]
    if not (source and source:IsValid()) then return false, "terrain not spawned" end
    local cls = findObject("/Script/Engine.StaticMeshActor")
    local l, r = source:K2_GetActorLocation(), source:K2_GetActorRotation()
    local actor = world:SpawnActor(cls, { X = l.X, Y = l.Y, Z = l.Z },
        { Pitch = r.Pitch, Yaw = r.Yaw, Roll = r.Roll })
    if not (actor and actor:IsValid()) then return false, "spawn failed" end
    Current.actors[key] = actor
    local src, comp = source.StaticMeshComponent, actor.StaticMeshComponent
    comp.Mobility = MOBILITY_MOVABLE
    comp:SetStaticMesh(src.StaticMesh)
    local s = source:GetActorScale3D()
    actor:SetActorScale3D({ X = s.X, Y = s.Y, Z = s.Z })
    comp:SetCollisionEnabled(COLLISION_NONE)
    -- The terrain's own materials, so masked surfaces (foliage, grates) cut
    -- their shadows as they are drawn.
    local count = src:GetNumMaterials()
    pcall(function() count = math.max(count, src.OverrideMaterials:GetArrayNum()) end)
    for i = 0, count - 1 do comp:SetMaterial(i, src:GetMaterial(i)) end
    -- Under a landscape: its ground slots cast nothing (the landscape casts
    -- the ground's shadows). CE's ground lies a few cm under and over the
    -- landscape, and around every hole the two overlap: cast from there it
    -- shadowed the landscape in blotches that changed with the camera (the
    -- shadow map's resolution), Ice Fields, 2026-10-13; a strict cut (no
    -- grow, half a hole) still left them. Whole slots (LandCut off: Ice
    -- Fields' caves) keep casting.
    local land = Current.level and Current.level.landscape
    local cut = type(land) == "table" and type(land.cut) == "table" and land.cut
    local hidden = cut and resolveMesh(TRIAL_MASTERS .. "M_CE_Hidden.M_CE_Hidden")
    for _, slot in ipairs(hidden and type(cut.slots) == "table" and cut.slots or {}) do
        pcall(function()
            local m = comp:GetMaterial(slot)
            if m and m:IsValid() and m:K2_GetScalarParameterValue(FName("LandCut")) > 0.5 then
                comp:SetMaterial(slot, hidden)
            end
        end)
    end
    -- CE's light fixtures cast nothing: each placed light sits a step in
    -- front of its fixture (upgrade_ce_map.py LIGHT_STEP), and the fixture
    -- still shadowed its own lamp across the wall behind it. That shadow
    -- came and went with the camera's distance (Death Island's sconces, gone
    -- past ~22 m, 2026-10-15); CE's lightmaps have no such shadow.
    local fixtureHidden = resolveMesh(TRIAL_MASTERS .. "M_CE_Hidden.M_CE_Hidden")
    for i, m in ipairs(fixtureHidden and type(item.materials) == "table" and item.materials or {}) do
        local base = type(m) == "table" and type(m.textures) == "table" and m.textures.Base
        if type(base) == "string" and base:find("_light_fixtures_", 1, true) then
            pcall(function() comp:SetMaterial(i - 1, fixtureHidden) end)
        end
    end
    comp.bCastHiddenShadow = true
    -- CE BSP surfaces are one-sided, and the lightmap bake's sun rays stop
    -- at either side: one-sided, the copy let the sun through the back of
    -- Blood Gulch's cliffs where CE had shade, which the dynamic albedo
    -- (TerrainLights) then drew lit (2026-10-05).
    comp.bCastShadowAsTwoSided = true
    -- Shadows only. Hidden from the camera, the copy still stood in the
    -- reflections and indirect light (distance fields, the Lumen scene, ray
    -- tracing), exactly on the terrain, and the two took turns frame by
    -- frame: gun glass and windshields flashed the sunlit ground (2026-10-05).
    comp.bVisibleInRayTracing = false
    comp.bVisibleInReflectionCaptures = false
    comp.bVisibleInRealTimeSkyCaptures = false
    comp.bAffectDynamicIndirectLighting = false
    comp.bAffectDistanceFieldLighting = false
    comp:SetCastShadow(true)
    comp:SetHiddenInGame(true, false)
    -- `shadow_shell` (tools/level/shadow_shell.py): the walls again, a little
    -- behind themselves, beside the copy. Its one-sided planes let the sun
    -- down every inside corner, where the neighbouring wall stands inside the
    -- shadow map's bias and nothing stands behind it (Sidewinder, 2026-10-14).
    local shell = Current.level and type(Current.level.shadow_shell) == "table"
        and resolveMesh(Current.level.shadow_shell.mesh)
    if shell and not (Current.actors["__shadow_shell"] and Current.actors["__shadow_shell"]:IsValid()) then
        local sa = world:SpawnActor(cls, { X = 0, Y = 0, Z = 0 }, { Pitch = 0, Yaw = 0, Roll = 0 })
        if sa and sa:IsValid() then
            Current.actors["__shadow_shell"] = sa
            local sc = sa.StaticMeshComponent
            sc.Mobility = MOBILITY_MOVABLE
            sc:SetStaticMesh(shell)
            sc:SetCollisionEnabled(COLLISION_NONE)
            sc.bCastHiddenShadow = true
            sc.bCastShadowAsTwoSided = true
            sc.bVisibleInRayTracing = false
            sc.bVisibleInReflectionCaptures = false
            sc.bVisibleInRealTimeSkyCaptures = false
            sc.bAffectDynamicIndirectLighting = false
            sc.bAffectDistanceFieldLighting = false
            sc:SetCastShadow(true)
            sc:SetHiddenInGame(true, false)
            Log("terrain shadow shell: " .. tostring(Current.level.shadow_shell.mesh))
        end
    elseif Current.level and type(Current.level.shadow_shell) == "table" and not shell then
        Log("terrain shadow shell not found: " .. tostring(Current.level.shadow_shell.mesh))
    end
    return true
end

local function applyShadowProxies(world)
    local n = 0
    for _, item in ipairs(Current.level and Current.level.decor or {}) do
        if isSolidTerrain(item) then
            local key = item.id .. "__shadow"
            if proxyWanted() then
                local ok, done, err = pcall(spawnShadowProxy, world, item)
                if ok and done then
                    n = n + 1
                else
                    Log("shadow proxy for '" .. item.id .. "': " .. tostring(ok and err or done))
                end
            else
                for _, k in ipairs({ key, "__shadow_shell" }) do
                    if Current.actors[k] then
                        if Current.actors[k]:IsValid() then pcall(function() Current.actors[k]:K2_DestroyActor() end) end
                        Current.actors[k] = nil
                    end
                end
            end
        end
    end
    return n
end

--- Sky fill (`mjolnir_terrain_lights fill`, an experiment): the sky light
--- cannot take a light function, so in CE's shade objects kept ~40% of their
--- sunlit brightness where CE drew them at a few percent. Most of the sky
--- light moves into three shadowless directional lights 20 degrees above
--- the horizon, 120 apart, sky-blue, on the sun mask: measured against the
--- sky light on a grey cube in Blood Gulch's open ground (2026-10-06), 864
--- each for a sky light of 768 matched it within ~10%. Objects only
--- (channel 0); the terrain draws its own light.
local SKY_FILL = { keep = 0.15, per_sky = 1.125, color = { 0.5, 0.62, 1.0 }, pitch = -20.0, yaws = { 0, 120, 240 } }

local function spawnSkyFill(world, lightFunction)
    local skyActor = Current.actors["__sky"]
    if not (skyActor and skyActor:IsValid()) then return 0 end
    local skylight = (Current.level.environment or {}).skylight or {}
    local sky = (skylight.intensity or 3.0) * lightScale()
    local cls = findObject("/Script/Engine.DirectionalLight")
    local n = 0
    for i, yaw in ipairs(SKY_FILL.yaws) do
        local key = "__skyfill" .. i
        local actor = Current.actors[key]
        if not (actor and actor:IsValid()) then
            actor = world:SpawnActor(cls, { X = 0, Y = 0, Z = 50000 }, { Pitch = SKY_FILL.pitch, Yaw = yaw, Roll = 0 })
            Current.actors[key] = actor
        end
        local c = actor.LightComponent
        c.Mobility = MOBILITY_MOVABLE
        c:SetCastShadows(false)
        pcall(function() c:SetAtmosphereSunLight(false) end)
        c:SetLightingChannels(true, false, false)
        c:SetIntensity(sky * SKY_FILL.per_sky)
        c:SetLightColor({ R = SKY_FILL.color[1], G = SKY_FILL.color[2], B = SKY_FILL.color[3], A = 1 }, true)
        c:SetLightFunctionMaterial(lightFunction)
        pcall(function() c:SetLightFunctionFadeDistance(1.0e7) end)
        actor:K2_SetActorRotation({ Pitch = SKY_FILL.pitch, Yaw = yaw, Roll = 0 }, false)
        n = n + 1
    end
    skyActor.LightComponent:SetIntensity(sky * SKY_FILL.keep)
    return n
end

--- The level's sun mask (TerrainLights): lightmap_bake's <stem>_sunmask,
--- CE's lightmap seen from above, in bake\ beside this mod. It goes on the
--- level's sun as a light function (the trial M_CE_SunLight), so the sun
--- stays out of what CE drew in shade and objects standing there darken; the
--- terrain's materials get the same mask, to know how much sun reaches them.
--- Its JSON places it relative to the terrain actor (the mesh's box centre).
local function applySunMask(world)
    local terrain, stem
    for _, item in ipairs(Current.level and Current.level.decor or {}) do
        if isSolidTerrain(item) then
            terrain = Current.actors[item.id]
            for _, m in ipairs(item.materials or {}) do
                local lm = type(m) == "table" and type(m.textures) == "table" and m.textures.Lightmap
                local leaf = type(lm) == "string" and lm:match("%.([%w_]+)$")
                if leaf then
                    stem = leaf:gsub("_n%d+$", "")
                    break
                end
            end
            break
        end
    end
    if not (terrain and terrain:IsValid()) then return false, "no terrain" end
    local levels = lightmapSun()
    if not levels or levels[2] <= levels[1] then return false, "the level names no lightmap_sun levels (no sun)" end
    -- The map's cooked mask (environment.sun_mask, gen_ce_level.py), unless a
    -- trial is running on a bake in bake\ beside this mod.
    local env = Current.level.environment or {}
    local spec, tex = env.sun_mask, nil
    -- A level whose lightmaps the solver drew says so (sun_mask false,
    -- gen_ce_level.py --no-sun-mask): the terrain copy's shadows are the
    -- sun's shadows, and a trial's mask beside this mod must not stand in.
    if spec == false then return false, "the level names no sun mask (the solver's lightmaps)" end
    if TerrainLights.trial or type(spec) ~= "table" then
        if not stem then return false, "no terrain with a lightmap" end
        local raw = readFile(textureFile("bake\\" .. stem .. "_sunmask.json"))
        if raw then
            local okJson, s2 = pcall(Json.decode, raw)
            if okJson and type(s2) == "table" then
                local t2 = importTexture(world, "bake\\" .. stem .. "_sunmask.png", true)
                if t2 then spec, tex = s2, t2 end
            end
        end
    end
    if type(spec) ~= "table" or type(spec.min) ~= "table" then return false, "the level has no sun mask" end
    if not tex then
        tex = resolveMesh(spec.texture)
        if not tex then return false, "sun mask texture not found: " .. tostring(spec.texture) end
    end
    local master = (TerrainLights.trial and resolveMesh(TRIAL_MASTERS .. "M_CE_SunLight.M_CE_SunLight"))
        or resolveMesh("/Game/MJOLNIR/CE/M_CE_SunLight.M_CE_SunLight")
    if not master then return false, "M_CE_SunLight not installed (runtime pack too old)" end
    local l = terrain:K2_GetActorLocation()
    local xform = { R = l.X + spec.min[1], G = l.Y + spec.min[2],
                    B = 1.0 / (spec.width * spec.cell_cm), A = 1.0 / (spec.height * spec.cell_cm) }
    local function place(mid)
        mid:SetTextureParameterValue(FName("SunMask"), tex)
        mid:SetVectorParameterValue(FName("SunMaskXform"), xform)
        mid:SetScalarParameterValue(FName("HasSunMask"), 1.0)
        mid:SetVectorParameterValue(FName("LightmapSun"), { R = levels[1], G = levels[2], B = 0, A = 0 })
    end
    local kml = findObject("/Script/Engine.Default__KismetMaterialLibrary")
    local light = kml:CreateDynamicMaterialInstance(world, master, FName("ce_sun_light"), 0)
    place(light)
    local sun = Current.actors["__sun"]
    if not (sun and sun:IsValid()) then return false, "no sun" end
    local c = sun.LightComponent
    c:SetLightFunctionMaterial(light)
    -- The fade is for a light function seen from far off; this one is
    -- the level's own light.
    pcall(function() c:SetLightFunctionFadeDistance(1.0e7) end)
    local n = 0
    for _, mid in ipairs(Current.sunMids) do
        if mid:IsValid() and pcall(place, mid) then n = n + 1 end
    end
    local fills = TerrainLights.fill and spawnSkyFill(world, light) or 0
    return string.format("%dx%d at %g cm on the sun and %d material(s)%s", spec.width, spec.height, spec.cell_cm, n,
        fills > 0 and string.format(", %d sky fill light(s)", fills) or "")
end

--- A copy of `src` with a level file's `scalars` ({ name = value }), one a
--- source material and set of values for the whole level. B30's trees
--- (MM_Foliage_MET) sway by their material's own angles, each instance on its
--- own phase: a swapped tree, built from 20 to 60 pieces and its leaf
--- clusters, swung every piece its own way by metres (2026-10-12).
local function scalarMid(world, src, scalars)
    if not (src and src:IsValid()) or type(scalars) ~= "table" then return nil end
    local names = {}
    for name, v in pairs(scalars) do
        if type(v) == "number" then names[#names + 1] = name end
    end
    table.sort(names)
    local key = src:GetFullName()
    for _, name in ipairs(names) do key = key .. "|" .. name .. "=" .. tostring(scalars[name]) end
    local mid = Current.scalarMids[key]
    if mid and mid:IsValid() then return mid end
    local kml = findObject("/Script/Engine.Default__KismetMaterialLibrary")
    if not kml then return nil end
    local n = 0
    for _ in pairs(Current.scalarMids) do n = n + 1 end
    mid = kml:CreateDynamicMaterialInstance(world, src, FName(string.format("scalars_%d", n)), 0)
    if not (mid and mid:IsValid()) then return nil end
    for _, name in ipairs(names) do
        -- "Name#k": layer k's parameter of a layered material (B40's glacial
        -- rock tiles its base layer by "Tile U#0"), which a plain set by
        -- name does not reach.
        local param, layer = name:match("^(.-)#(%d+)$")
        if param then
            pcall(function()
                mid:SetScalarParameterValueByInfo({ Name = FName(param), Association = 0, Index = tonumber(layer) },
                    scalars[name])
            end)
        else
            mid:SetScalarParameterValue(FName(name), scalars[name])
        end
    end
    Current.scalarMids[key] = mid
    return mid
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
        -- The rotation asked for, set exactly (once Movable: a Static actor
        -- refuses it): through UE4SS, SpawnActor's comes out wrong (pitch
        -- alone negated, mixed angles composed otherwise), and a tilted
        -- tree's pieces, each turned about its own pivot, stood apart: a
        -- trunk with a gap, a branch hanging in the air (2026-10-18).
        actor:K2_SetActorRotation({ Pitch = rot[1] or 0.0, Yaw = rot[2] or 0.0, Roll = rot[3] or 0.0 }, false)
        comp:SetStaticMesh(mesh)
        local s = item.scale
        if type(s) == "table" and #s >= 3 then
            actor:SetActorScale3D({ X = s[1], Y = s[2], Z = s[3] })
        end
        -- Decor is not solid to the sim; keep the Unreal side consistent.
        comp:SetCollisionEnabled(COLLISION_NONE)
        -- A converted map's sky draws before the rest of its translucency.
        if type(item.sort_priority) == "number" then
            comp:SetTranslucentSortPriority(item.sort_priority)
        end
        -- A converted level's own shadows are baked into its lightmaps;
        -- only objects (vehicles, players, weapons) cast real ones.
        if item.cast_shadow == false then
            comp:SetCastShadow(false)
            -- The CE terrain is lit only to receive object shadows from the
            -- sun: its base colour is the sun's share of the baked light, so
            -- another light would brighten only where CE had sun. It stays
            -- on lighting channel 1, which only the level's sun shares, out
            -- of the game's lights' way, unless the materials hold the
            -- surface's albedo for them (TerrainLights).
            comp:SetLightingChannels(TerrainLights.on, true, false)
        end
        -- `capture_only`: there for Fluid Flux's one ground capture (a
        -- river's bed, upgrade_ce_map.flux_bed), hidden after it
        -- (Effects.flux). Neither Flux's phantom material nor a component
        -- visible in scene captures alone reached its capture.
        if item.capture_only then comp:SetCastShadow(false) end
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

    -- The piece's look, as jobs in order: its tint, its material slots one
    -- a job, then what needs them. During a load they go to the load's queue
    -- (Current.dressQueue), a slice a frame: Timberland's 26 spawned pieces
    -- took 569 ms in one frame, its CE terrain 106 materials of them.
    -- Otherwise they run now.
    local id = tostring(item.id)
    local jobs = {}
    if item.tint then
        jobs[#jobs + 1] = function(comp)
            if not applyTint(comp, item.tint) then
                Log("tint failed for '" .. id .. "' (mesh has no Color param?)")
            end
        end
    end
    if item.materials then
        local st = { applied = 0, failed = 0, bounds = 1.0 }
        for i, entry in ipairs(type(item.materials) == "table" and item.materials or {}) do
            jobs[#jobs + 1] = function(comp) applyMaterial(comp, entry, i, world, id, st) end
        end
        jobs[#jobs + 1] = function(comp)
            local nApplied, nFailed = materialsDone(comp, id, st)
            Log(string.format("decor '%s': %d material(s) applied, %d failed", id, nApplied, nFailed))
            local pulse = item.pulse
            if type(pulse) == "table" and type(pulse.param) == "string" then
                local first = item.materials[1]
                local base = type(first) == "table" and first.scalars and first.scalars[pulse.param]
                local okM, mid = pcall(function() return comp:GetMaterial(0) end)
                if okM and mid and mid:IsValid() and base then
                    -- The setter kept: UE4SS hands back a new function handle at
                    -- every method lookup (~250 bytes), and one bound to its
                    -- object, so it is this instance's own.
                    Current.pulses[#Current.pulses + 1] = {
                        mid = mid, set = mid.SetScalarParameterValue, param = FName(pulse.param), base = base,
                        fn = pulse["function"] or 2, period = pulse.period or 1.0,
                    }
                end
            end
        end
    end
    jobs[#jobs + 1] = function(comp)
        -- `scalars`: values on the mesh's own materials (scalarMid), e.g. a
        -- swapped tree's sway.
        if type(item.scalars) == "table" then
            pcall(function()
                for i = 0, comp:GetNumMaterials() - 1 do
                    local mid = scalarMid(world, comp:GetMaterial(i), item.scalars)
                    if mid then comp:SetMaterial(i, mid) end
                end
            end)
        end
        -- `static`: no vertex offset (wind) at all. A swaying mesh is rebuilt
        -- for ray tracing every frame and re-renders its shadow pages; Ice
        -- Fields' 506 fir pieces hung the GPU in Lumen's reflections and their
        -- shadows jumped as the player walked (2026-10-13).
        -- A swapped tree's piece (its sway calmed, scenery_swap.py TREE_CALM)
        -- too: each piece bends about its own pivot, and a 10 m trunk piece's
        -- tip moved far enough to part from the next, the trunk breaking apart
        -- and joining again in the wind (Infinity, 2026-10-18). Its leaf
        -- clusters (foliage) still flutter.
        if item.static or (type(item.scalars) == "table" and item.scalars["Wind Sway Max Angle"] == 0) then
            pcall(function() comp:SetEvaluateWorldPositionOffset(false) end)
        end
        -- After the materials: the strength is set on them.
        if (TerrainShadows.cast or TerrainShadows.strength) and isTerrain(item) then
            pcall(applyTerrainShadows, actor)
        end
    end
    local function run(job)
        if actor:IsValid() then job(actor.StaticMeshComponent) end
    end
    if Current.dressQueue then
        Current.dressQueue.add(jobs, run)
    else
        for _, job in ipairs(jobs) do run(job) end
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
    local k = lightScale()
    place("__sun", "/Script/Engine.DirectionalLight",
        { Pitch = sun.pitch or -50.0, Yaw = sun.yaw or 30.0, Roll = 0 },
        function(actor)
            local c = actor.LightComponent
            c.Mobility = MOBILITY_MOVABLE
            c:SetIntensity((sun.intensity or 8.0) * k)
            pcall(function() c:SetCastShadows(true) end)
            -- The sun's angular size sets how soft its shadows are. Only a
            -- level that asks for it: at 3 degrees the virtual shadow maps
            -- leaked light in thin lines across shaded ground and a halo
            -- around the first-person gun (Blood Gulch, 2026-10-06), so the
            -- engine's 0.54 stays the default.
            if type(sun.source_angle) == "number" then
                pcall(function() c:SetLightSourceAngle(sun.source_angle) end)
            end
            -- CE's walls are one-sided planes, and the terrain copy's shadow
            -- cannot hold the sun off the last shadow texel or two of a
            -- concave crease: a lit sliver ran along every inside corner of
            -- Sidewinder's rooms, crawling as the shadow map's texel dither
            -- re-rolled each frame (2026-10-14). Finer sun shadows narrow it
            -- (`sun.shadow_lod`, the engine's -1.5 by default) and no dither
            -- stills it; resetState puts both back.
            -- With weather, reflections trace the scene only, not the screen:
            -- the falling flakes in front of the camera are in the screen, and
            -- the ice reflected them as big dark blots sliding across it, far
            -- off too (Sidewinder, 2026-10-14).
            pcall(function()
                local ks = findObject("/Script/Engine.Default__KismetSystemLibrary")
                Current.cvars = Current.cvars or {}
                local set = {
                    ["r.Shadow.Virtual.SMRT.TexelDitherScaleDirectional"] = 0,
                    ["r.Shadow.Virtual.ResolutionLodBiasDirectional"] = tonumber(sun.shadow_lod) or -3,
                }
                if type(env.weather) == "table" and type(env.weather.system) == "string" then
                    set["r.Lumen.Reflections.ScreenTraces"] = 0
                end
                -- `sun.shadow_normal_bias`: the sun skimming a smooth wall
                -- drew its shadow's edge as a row of teeth, a shadow texel
                -- each stretched down the face (Zanzibar's sea-wall slabs
                -- once they took a PBR surface lit by the sun, 2026-11-12).
                -- The engine's 0.5 left them; 3 cleared them.
                if tonumber(sun.shadow_normal_bias) then
                    set["r.Shadow.Virtual.NormalBias"] = tonumber(sun.shadow_normal_bias)
                end
                -- A Flux sea mirrors the CE sky mesh's horizon strip, which
                -- Lumen finds far brighter than the sky drawn there: a hard
                -- white line all along Death Island's horizon. Clamped, it
                -- is a faint edge (2026-10-14).
                local coast = type(Current.level.flux) == "table" and Current.level.flux.coast
                if type(coast) == "table" then
                    set["r.Lumen.Reflections.MaxRayIntensity"] = tonumber(coast.max_ray) or 2
                end
                for name, value in pairs(set) do
                    if Current.cvars[name] == nil then Current.cvars[name] = ks:GetConsoleVariableFloatValue(name) end
                    ks:ExecuteConsoleCommand(world, string.format("%s %g", name, value), getPlayerController())
                end
            end)
            -- Channel 0 for objects, channel 1 for the terrain (spawnDecorItem).
            pcall(function() c:SetLightingChannels(true, true, false) end)
            -- The CE materials draw a share of their baked light as this sun
            -- and divide it out again (runtimeMaterial's Sun* parameters), so
            -- the light must be exactly what they are told: the level's
            -- rotation (the spawn rotation does not stick: the light came up
            -- at -69/19 whatever the level said), its colour as given
            -- (linear, not converted from sRGB), and no atmosphere between
            -- (which tints and dims it by elevation). Any of the three off
            -- and the hills shade wrongly.
            pcall(function()
                actor:K2_SetActorRotation({ Pitch = sun.pitch or -50.0, Yaw = sun.yaw or 30.0, Roll = 0 }, false)
            end)
            pcall(function() c:SetAtmosphereSunLight(sun.atmosphere_sun == true) end)
            if type(sun.color) == "table" then
                -- bSRGB true: the component keeps an 8-bit colour the renderer
                -- decodes as sRGB, so the linear colour the level names must be
                -- encoded going in. With false, (0.44, 0.54, 1.0) lit the world
                -- at (0.17, 0.25, 1.0): Gephyrophobia's deck drew at half the
                -- red and green the masters were told to expect (2026-10-08).
                c:SetLightColor({ R = sun.color[1], G = sun.color[2], B = sun.color[3], A = 1.0 }, true)
            end
        end)
    if env.atmosphere ~= false then
        place("__atmosphere", "/Script/Engine.SkyAtmosphere", nil, nil)
    end
    local skylight = env.skylight or {}
    place("__sky", "/Script/Engine.SkyLight", nil, function(actor)
        local c = actor.LightComponent
        c.Mobility = MOBILITY_MOVABLE
        c.bRealTimeCapture = true
        -- A physical atmosphere already captures the scaled sun radiance.
        -- Multiplying its capture by k again washes native foliage white.
        c:SetIntensity((skylight.intensity or 3.0) * (skylight.physical and 1 or k))
        if type(skylight.color) == "table" then
            c:SetLightColor({ R = skylight.color[1], G = skylight.color[2], B = skylight.color[3], A = 1.0 })
        end
        -- `skylight.lower`: the colour of the lower hemisphere (the ground's
        -- bounce), not black; with `skylight.lower_from_below` the capture's
        -- own lower half is ignored for it. A CE sky dome's deep blue lit
        -- every shade from below navy (Blood Gulch's pebbles drew blue).
        if type(skylight.lower) == "table" then
            pcall(function()
                c.LowerHemisphereColor = { R = skylight.lower[1], G = skylight.lower[2], B = skylight.lower[3], A = 1.0 }
                c.bLowerHemisphereIsBlack = false
            end)
        end
        c:RecaptureSky()
    end)
    -- `environment.clouds`: Unreal's volumetric clouds over the level, for a
    -- sky whose CE dome is a painted backdrop (its clouds stay, the
    -- volumetric ones drift over the map itself). Needs the atmosphere.
    local clouds = env.clouds
    if type(clouds) == "table" and env.atmosphere ~= false then
        place("__clouds", "/Script/Engine.VolumetricCloud", nil, function(actor)
            local c = actor.VolumetricCloudComponent
            pcall(function() c:SetLayerBottomAltitude(clouds.bottom or 3.0) end)
            pcall(function() c:SetLayerHeight(clouds.height or 4.0) end)
            local m = type(clouds.material) == "string" and resolveMesh(clouds.material)
            if m then pcall(function() c:SetMaterial(m) end) end
        end)
    end
    -- `environment.sky_fog`: a CE sky with no model is its outdoor fog's
    -- colour (Coldsnap's night). The masters fog the level towards it and
    -- reach it at the opaque distance; a height fog that starts there turns
    -- everything farther, the empty sky included, that colour. Its colour is
    -- linear and exposed like a light, so it is raised by the light scale the
    -- post-process takes back out. The fog sits far above the map: below its
    -- height it only thickens, so every ray past the start is opaque.
    local skyFog = env.sky_fog
    if type(skyFog) == "table" and type(skyFog.color) == "table" then
        place("__sky_fog", "/Script/Engine.ExponentialHeightFog", nil, function(actor)
            pcall(function()
                actor:K2_SetActorLocation({ X = high.X, Y = high.Y, Z = high.Z + (skyFog.height or 400000.0) },
                    false, Current.emptyHit(), false)
            end)
            local c = actor.Component
            c.Mobility = MOBILITY_MOVABLE
            c:SetFogDensity(skyFog.density or 0.5)
            c:SetFogHeightFalloff(0.001)
            c:SetStartDistance(skyFog.start or 0.0)
            c:SetFogMaxOpacity(1.0)
            c:SetFogInscatteringColor({ R = skyFog.color[1] * k, G = skyFog.color[2] * k, B = skyFog.color[3] * k, A = 1.0 })
            pcall(function() c:SetDirectionalInscatteringColor({ R = 0, G = 0, B = 0, A = 1.0 }) end)
        end)
    end
    -- `environment.haze` (a B30 landscape's, landscapeLight): Unreal's height
    -- fog as distance haze, for the surfaces that do not fog themselves as
    -- CE's masters do (the landscape, the cliffs' rock). Cut off short of the
    -- sky mesh, which it otherwise turned to storm cloud. Its colour exposed
    -- as the lights are (the light scale).
    -- The sky light's capture takes the height fog in, and the sea reflects
    -- the capture's horizon: under Death Island's CE fog (0.5, pale blue) it
    -- drew near white. Nothing renders until the load lets go of the game
    -- thread, so the capture asked for above would see the haze; it comes
    -- up clear (opacity 0), the sky is captured again, and then it fades in.
    local haze = env.haze
    if type(haze) == "table" and type(haze.color) == "table" then
        place("__haze", "/Script/Engine.ExponentialHeightFog", nil, function(actor)
            pcall(function() actor:K2_SetActorLocation({ X = 0, Y = 0, Z = haze.height or 0 }, false, Current.emptyHit(), false) end)
            local c = actor.Component
            c.Mobility = MOBILITY_MOVABLE
            c.FogCutoffDistance = haze.cutoff or 80000
            c:SetFogDensity(haze.density or 0.02)
            c:SetFogHeightFalloff(haze.falloff or 0.08)
            c:SetStartDistance(haze.start or 2500)
            c:SetFogMaxOpacity(0.0)
            c:SetFogInscatteringColor({ R = haze.color[1] * k, G = haze.color[2] * k, B = haze.color[3] * k, A = 1.0 })
            -- `haze.sun` {r, g, b, exponent, start cm}: the haze glows
            -- towards the sun (directional inscattering).
            if type(haze.sun) == "table" then
                local sc = haze.sun
                pcall(function()
                    c:SetDirectionalInscatteringColor({ R = (sc[1] or 1) * k, G = (sc[2] or 1) * k, B = (sc[3] or 1) * k, A = 1.0 })
                    c:SetDirectionalInscatteringExponent(sc[4] or 8.0)
                    c:SetDirectionalInscatteringStartDistance(sc[5] or 3000.0)
                end)
            end
            -- Both as soon as they can be: the capture on the first tick after
            -- the load lets go (the delay has run out by then), the haze a few
            -- frames after it. At 1 s and 2 s it came up ~2 s after the
            -- player spawned (2026-10-18), once the load itself was short.
            ExecuteInGameThreadWithDelay(50, function()
                local sky = Current.actors.__sky
                if sky and sky:IsValid() then pcall(function() sky.LightComponent:RecaptureSky() end) end
                ExecuteInGameThreadWithDelay(250, function()
                    if actor:IsValid() then pcall(function() actor.Component:SetFogMaxOpacity(haze.max_opacity or 0.7) end) end
                end)
            end)
        end)
    end
    -- `environment.post`: an unbound post-process volume. Converted CE levels
    -- draw CE's own colours (their materials undo the game's display colour
    -- correction), so they ask for everything between material and screen to
    -- be neutral: a fixed exposure (manual, no physical camera, its bias
    -- only the light scale's, which the materials divide back out), no
    -- local exposure (contrast scales 1), and the tonemapper without its
    -- filmic curve, gamut expansion or blue correction. Measured with a grey
    -- probe, docs/re/fork_renderer.md.
    local post = env.post
    if type(post) == "table" then
        place("__post", "/Script/Engine.PostProcessVolume", nil, function(actor)
            actor.bUnbound = true
            actor.Priority = 1000.0
            actor.BlendWeight = 1.0
            local s = actor.Settings
            local function set(key, field, value)
                if value ~= nil then
                    s["bOverride_" .. field] = true
                    s[field] = value
                end
            end
            set("tone_curve", "ToneCurveAmount", post.tone_curve)
            set("expand_gamut", "ExpandGamut", post.expand_gamut)
            set("blue_correction", "BlueCorrection", post.blue_correction)
            set("bloom", "BloomIntensity", post.bloom)
            set("vignette", "VignetteIntensity", post.vignette)
            -- Rougher surfaces reflect from the radiance cache, not traced
            -- rays (docs/level_format.md); a level of glossy metal saves ms.
            set("max_traced_roughness", "LumenMaxRoughnessToTraceReflections", post.max_traced_roughness)
            if post.manual_exposure then
                set("manual_exposure", "AutoExposureMethod", 2) -- AEM_Manual
                set("manual_exposure", "AutoExposureApplyPhysicalCameraExposure", false)
            end
            -- Down by the light scale (lightScale), in stops.
            set("exposure_bias", "AutoExposureBias", (post.exposure_bias or 0.0) - math.log(k, 2))
            set("local_exposure", "LocalExposureHighlightContrastScale", post.local_exposure)
            set("local_exposure", "LocalExposureShadowContrastScale", post.local_exposure)
        end)
    end
    Log("environment spawned (sun/atmosphere/skylight" .. (type(post) == "table" and "/post" or "") .. ")")

end

--- The game's volume sliders (Settings > Audio) set its Wwise buses, and the
--- level's sounds play through Unreal's own audio engine beside Wwise, so
--- they never followed them: water, teleporters and the announcer kept
--- playing at full volume with the game turned down (2026-10-10). Each sound
--- is scaled by Master times its category's slider instead, read from the
--- game's settings object (MeteoriteGameUserSettings, the engine's
--- GameUserSettings).
local VOLUME_SLIDERS = {
    ambient = "VolumeSFXAmbient",
    music = "VolumeMusicGameplay",
    announcer = "VolumeVODialog",
    gameplay = "VolumeSFXGameplay",
}

local UserSettings = nil

--- Master times the category's slider, 0..1; 1 when the settings cannot be
--- read, as before.
local function gameVolume(category)
    local ok, v = pcall(function()
        if not (UserSettings and UserSettings:IsValid()) then
            UserSettings = findObject("/Script/Engine.Default__GameUserSettings"):GetGameUserSettings()
        end
        return UserSettings.VolumeMaster * UserSettings[VOLUME_SLIDERS[category] or VOLUME_SLIDERS.ambient]
    end)
    if ok and type(v) == "number" and v == v then return math.max(0.0, math.min(1.0, v)) end
    return 1.0
end

--- Keep the level's sounds at the sliders as they move. One settings read per
--- category a pass, and a sound is only told when its volume changed.
local function syncVolumes()
    if #Current.volumed == 0 then return end
    local volumes, changed = {}, {}
    -- Halo 2's background loops belong to BSP clusters (`zones`: bounds and
    -- the set of loops each plays): the set of the zone the camera is in,
    -- or nearest to, is heard and the others fade out.
    local env = Current.level and Current.level.environment
    local zones = type(env) == "table" and type(env.sounds) == "table" and env.sounds.zones
    local active
    if type(zones) == "table" and #zones > 0 then
        local ok, cam = pcall(function()
            return getPlayerController().PlayerCameraManager:GetCameraLocation()
        end)
        if ok and cam then
            local o = (Current.level.canvas or {}).origin or { 0, 0, 0 }
            local p = { cam.X - o[1], cam.Y - o[2], cam.Z - o[3] }
            local best, bestSize = math.huge, math.huge
            for _, z in ipairs(zones) do
                local d, size = 0, 1
                for k = 1, 3 do
                    local gap = math.max(z.min[k] - p[k], 0, p[k] - z.max[k])
                    d = d + gap * gap
                    size = size * math.max(z.max[k] - z.min[k], 1)
                end
                if d < best or (d == best and size < bestSize) then
                    best, bestSize, active = d, size, z.set
                end
            end
        end
    end
    if active and active ~= Current.soundSet then
        Current.soundSet = active
        Log("background sound: set " .. tostring(active))
    end
    for _, v in ipairs(Current.volumed) do
        if v.set and active and v.comp:IsValid() then
            local heard = v.set == active
            if heard ~= v.heard then
                pcall(function() v.comp:AdjustVolume(1.0, heard and 1.0 or 0.0, 0) end)
                v.heard = heard
            end
        end
        volumes[v.category] = volumes[v.category] or gameVolume(v.category)
        local volume = volumes[v.category]
        if volume ~= v.volume and v.comp:IsValid() then
            v.comp:SetVolumeMultiplier(v.gain * volume)
            v.volume = volume
            changed[v.category] = (changed[v.category] or 0) + 1
        end
    end
    for category, n in pairs(changed) do
        Log(string.format("sound volume: %s %.2f (%d sound(s))", category, volumes[category], n))
    end
end

--- A level baked with `clear.scripts` has no mission script left to fade the
--- screen back in after the loading screen, so the map boots pitch black with
--- a live simulation behind it. Ask the Blam console to fade in once the
--- player exists, unless the level opts out with `environment.fade_in = false`.
--- The level's ambient sound (environment.sounds, from the CE map's BSP
--- background sound and sound scenery: tools/level/ce_sounds.py), played
--- through Unreal's own audio engine, which the game runs beside its own.
--- Background loops are 2D and map-wide (a Halo 2 map's follow the BSP
--- cluster the camera is in, `zones`); emitters are 3D loops that fall off
--- linearly from `inner` to `inner + falloff` centimetres, as CE's distance
--- bounds do, at most `max` of one sound at a time.
local function spawnSounds(world)
    local env = Current.level and Current.level.environment
    local sounds = type(env) == "table" and env.sounds
    if type(sounds) ~= "table" then return end
    local gs = findObject("/Script/Engine.Default__GameplayStatics")
    local attClass = findObject("/Script/Engine.SoundAttenuation")
    local limitClass = findObject("/Script/Engine.SoundConcurrency")
    if not gs then return end
    local playing, failed = 0, 0
    -- `max` (Halo 2's sound class: how many of one sound play at once): one
    -- concurrency group a sound, which keeps the nearest playing and lets
    -- the engine bring a stopped loop back as the listener nears it.
    local limits, limitCount = {}, 0
    local function limit(s)
        if not (limitClass and type(s.max) == "number" and s.max > 0) then return nil end
        local key = s.wave .. "#" .. s.max
        if limits[key] == nil then
            limits[key] = false
            pcall(function()
                limitCount = limitCount + 1
                local c = StaticConstructObject(limitClass, world, FName("MJOLNIR_Limit_" .. limitCount))
                c.Concurrency.MaxCount = math.floor(s.max)
                c.Concurrency.ResolutionRule = 3     -- stop the farthest, then the oldest
                limits[key] = c
            end)
        end
        return limits[key] or nil
    end

    -- Spawned at the sliders' volume (gameVolume), kept there by syncVolumes.
    local function keep(key, comp, fade, gain, category, volume, set)
        if not (comp and comp:IsValid()) then
            failed = failed + 1
            return
        end
        Current.actors[key] = comp
        Current.volumed[#Current.volumed + 1] = { comp = comp, gain = gain, category = category, volume = volume,
                                                  set = set, heard = set and false or nil }
        -- A zoned background starts silent; syncVolumes fades in the set
        -- of the zone the camera is in.
        if set then pcall(function() comp:AdjustVolume(0.0, 0.0, 0) end) end
        if fade and fade > 0 then pcall(function() comp:FadeIn(fade, 1.0, 0.0, 0) end) end
        playing = playing + 1
    end

    for i, s in ipairs(type(sounds.background) == "table" and sounds.background or {}) do
        local wave = type(s.wave) == "string" and resolveMesh(s.wave)
        if wave then
            -- A CE music loop (class music) follows the music slider.
            local gain, category = s.gain or 1.0, s.category or "ambient"
            local volume = gameVolume(category)
            local set = type(sounds.zones) == "table" and s.set or nil
            -- A loop faded to nothing has to keep playing to be faded back
            -- (PlayWhenSilent, as the moving emitters below).
            if set then pcall(function() wave.VirtualizationMode = 1 end) end
            -- `pitch`: Halo 2's pitched loops (the humming lights, 5
            -- semitones down).
            local ok, comp = pcall(function()
                return gs:SpawnSound2D(world, wave, gain * volume, s.pitch or 1.0, 0.0, nil, false, false)
            end)
            keep("__bg" .. i, ok and comp, not set and s.fade_in or nil, gain, category, volume, set)
        else
            failed = failed + 1
            Log("sound not found: " .. tostring(s.wave))
        end
    end

    for i, s in ipairs(type(sounds.emitters) == "table" and sounds.emitters or {}) do
        local wave = type(s.wave) == "string" and resolveMesh(s.wave)
        if wave and type(s.pos) == "table" then
            local att
            if attClass then
                pcall(function()
                    att = StaticConstructObject(attClass, world, FName("MJOLNIR_Att_" .. i))
                    local a = att.Attenuation
                    a.bAttenuate = true
                    a.bSpatialize = true
                    a.DistanceAlgorithm = 0          -- linear, as CE
                    a.AttenuationShape = 0           -- sphere
                    a.AttenuationShapeExtents = { X = s.inner or 150.0, Y = 0, Z = 0 }
                    a.FalloffDistance = s.falloff or 600.0
                end)
            end
            local origin = Current.level.canvas.origin
            if type(s.motion) == "table" then
                -- Out of range most of its cycle, the loop was virtualized
                -- with Restart (2) and did not come back within the second
                -- the beam is near (Infinity, 2026-10-08); PlayWhenSilent
                -- keeps it running.
                pcall(function() wave.VirtualizationMode = 1 end)
            end
            local gain, category = s.gain or 1.0, s.category or "ambient"
            local volume = gameVolume(category)
            local ok, comp = pcall(function()
                return gs:SpawnSoundAtLocation(world, wave,
                    { X = origin[1] + s.pos[1], Y = origin[2] + s.pos[2], Z = origin[3] + s.pos[3] },
                    { Pitch = 0, Yaw = 0, Roll = 0 }, gain * volume, s.pitch or 1.0, 0.0, att, limit(s), false)
            end)
            keep("__snd" .. i, ok and comp, s.fade_in, gain, category, volume)
            -- On a machine's moving part (Infinity's beams): moved with it
            -- by moveSounds, as the part's material moves it.
            local m = s.motion
            if ok and comp and comp:IsValid() and type(m) == "table" and type(m.t1) == "table" then
                local o = Current.level.canvas.origin
                local abs = function(v) return { o[1] + v[1], o[2] + v[2], o[3] + v[3] } end
                Current.movingSounds[#Current.movingSounds + 1] = {
                    comp = comp, pos = abs(s.pos), pivot = abs(m.pivot or s.pos), t0 = m.t0 or { 0, 0, 0 },
                    t1 = m.t1, s0 = m.s0 or 1, s1 = m.s1 or 1, period = m.period or 0, position = m.position or 0,
                }
            end
        else
            failed = failed + 1
            Log("sound not found: " .. tostring(s.wave))
        end
    end
    Log(string.format("ambient sound: %d playing, %d failed%s", playing, failed,
        #Current.movingSounds > 0 and (", " .. #Current.movingSounds .. " on moving parts") or ""))
end

--- Capture the Flag flags and team armour are teams.lua's (Teams.flagTick,
--- Teams.armorTick, Teams.onIncident): CE's flag mesh on each flag actor in
--- the colours of its tag's team, and Mk V Classic tinted on the game's
--- own events.

--- Health packs (the level's `health_pack`). Nothing in the game heals on
--- contact, so the Megalo variants make and take the packs
--- (blam_megalo::powerups); the pack is equipment cloned from the battle rifle
--- ammo pickup (tools/level/build_ctf_flag.sh), whose actor gets CE's health
--- pack mesh in place of its own. No CE map places battle rifle ammo, so every
--- such actor is a pack.
local HEALTH_PACK_ACTOR_CLASS_PATH =
    "/Game/_Prototypes/SynchronizationTestContent/Assets/Equipments/BP_Battle_Rifle_ammo_EquipmentActor.BP_Battle_Rifle_ammo_EquipmentActor_C"
--- The mesh put on each pack actor, by actor full name.
local PackMeshes = {}

local function healthPackLevel()
    local hp = Current.level and Current.level.health_pack
    if type(hp) == "table" and hp.mesh then return hp end
end

--- Hide every primitive of `actor` but `mine` (a pack's mesh here; a flag's
--- mesh and cloth, as a list, in teams.lua).
local function hideAllBut(actor, mine)
    local keep = {}
    for _, m in ipairs(type(mine) == "table" and mine or { mine }) do
        if m and m:IsValid() then keep[m:GetFullName()] = true end
    end
    for _, c in ipairs(actor:K2_GetComponentsByClass(findObject("/Script/Engine.PrimitiveComponent")) or {}) do
        pcall(function()
            if type(c) == "userdata" and c.get then c = c:get() end
            if keep[c:GetFullName()] then return end
            c:SetHiddenInGame(true, false)
            c:SetVisibility(false, false)
        end)
    end
end

--- The crate's box (its own mesh's bounds, in its frame), read once.
local PackCrate = nil

local function packCrate(actor)
    if PackCrate then return PackCrate end
    for _, c in ipairs(actor:K2_GetComponentsByClass(findObject("/Script/Engine.StaticMeshComponent")) or {}) do
        pcall(function()
            if type(c) == "userdata" and c.get then c = c:get() end
            local sm = c.StaticMesh
            if sm and sm:IsValid() and sm:GetFName():ToString() == "SM_ammo_pickup_BR" then
                local b = sm:GetBounds()
                PackCrate = { o = { b.Origin.X, b.Origin.Y, b.Origin.Z }, e = { b.BoxExtent.X, b.BoxExtent.Y, b.BoxExtent.Z } }
            end
        end)
    end
    -- As measured on CU4 (2026-10-08), should the mesh not be found.
    PackCrate = PackCrate or { o = { 3.45, 0, 0 }, e = { 22.74, 11.40, 4.62 } }
    return PackCrate
end

--- Stand the pack's mesh upright on the ground under its crate, with the
--- crate's heading. The crate is a physics object made 0.1 wu above its spot
--- (blam_megalo::powerups) that can come to rest tipped on its side (Ice
--- Fields, 2026-10-08: rolled 17 and 40 degrees), while CE's packs stand
--- upright. CE's model has its origin at its base and the crate has its at
--- its centre (4.6 cm up when it lies flat), so the base goes to the crate's
--- lowest corner, which is on the ground.
local function seatPackMesh(actor, comp, hp)
    local f, r, u = actor:GetActorForwardVector(), actor:GetActorRightVector(), actor:GetActorUpVector()
    local box = packCrate(actor)
    local axes = { f.Z, r.Z, u.Z }
    local lowest = 0
    for i = 1, 3 do lowest = lowest + box.o[i] * axes[i] - box.e[i] * math.abs(axes[i]) end
    -- The mesh's offset above the base (hp.pos, the rewrite's transform),
    -- straight up from the crate's lowest corner, in the crate's frame.
    local p = hp.pos or { 0, 0, 0 }
    local up = (p[3] or 0) + lowest
    comp:K2_SetRelativeLocation({ X = (p[1] or 0) + up * f.Z, Y = (p[2] or 0) + up * r.Z, Z = up * u.Z }, false, Current.emptyHit(), false)
    comp:SetAbsolute(false, true, false)
    comp:K2_SetWorldRotation({ Pitch = 0, Yaw = actor:K2_GetActorRotation().Yaw, Roll = 0 }, false, Current.emptyHit(), false)
end

local function dressHealthPack(world, actor, hp)
    if not actor:IsValid() then return end
    local key = actor:GetFullName()
    local mine = PackMeshes[key]
    if mine and mine:IsValid() then
        hideAllBut(actor, mine)
        -- Again once the crate has landed.
        pcall(seatPackMesh, actor, mine, hp)
        return
    end
    local mesh = resolveMesh(hp.mesh)
    if not mesh then error("mesh not found: " .. tostring(hp.mesh)) end
    local comp = actor:AddComponentByClass(findObject("/Script/Engine.StaticMeshComponent"), false, {
        Rotation = { X = 0, Y = 0, Z = 0, W = 1 },
        Translation = { X = 0, Y = 0, Z = 0 },
        Scale3D = { X = 1, Y = 1, Z = 1 },
    }, false)
    if not (comp and comp:IsValid()) then error("no mesh component") end
    comp.Mobility = MOBILITY_MOVABLE
    comp:SetStaticMesh(mesh)
    comp:SetCollisionEnabled(COLLISION_NONE)
    local p, s = hp.pos or { 0, 0, 0 }, hp.scale or 1.0
    comp:K2_SetRelativeLocationAndRotation({ X = p[1], Y = p[2], Z = p[3] },
        { Pitch = 0, Yaw = 0, Roll = 0 }, false, Current.emptyHit(), false)
    comp:SetRelativeScale3D({ X = s, Y = s, Z = s })
    pcall(seatPackMesh, actor, comp, hp)
    PackMeshes[key] = comp
    hideAllBut(actor, comp)
    local applied, failed = applyMaterials(comp, hp.materials, world, "health_pack")
    if not Current.packDressed then
        Current.packDressed = true
        Log(string.format("health packs: first pack dressed (%d material(s), %d failed)", applied, failed))
    end
end

local packsWatched = false

--- Every pack the variant makes (one per spot, again after each pickup) is
--- dressed as it appears; the game may show the pickup's own mesh again a
--- moment later, so it is hidden again then, and the mesh is seated again
--- once the crate has fallen and settled.
local function watchHealthPacks()
    if packsWatched or not mayArm("packs") then return end
    packsWatched = pcall(NotifyOnNewObject, HEALTH_PACK_ACTOR_CLASS_PATH, function(actor)
        for _, ms in ipairs({ 50, 500, 2000, 5000 }) do
            ExecuteInGameThreadWithDelay(ms, function()
                local hp, world = healthPackLevel(), getWorld()
                if not (hp and world and actor:IsValid()) then return end
                local ok, err = pcall(dressHealthPack, world, actor, hp)
                if not ok then Log("health pack: " .. tostring(err)) end
            end)
        end
    end)
    if packsWatched then Log("health packs: watching for pack actors") end
end

--- Event sounds. The game engine raises Reach's events (incidents) on a
--- converted multiplayer map, teleports, respawn ticks, multikills, mode
--- starts, but the sounds its event list names were cut from the build (336
--- of 339 sound tags missing). events.json maps an event to CE's sound for it
--- (tools/level/ce_sounds.py --events), cooked under /Game/MJOLNIR/Sounds/Events;
--- the incident handler on the game state is hooked to play it.
local EventSounds = nil
--- Waves resolved at level load, by event name. Loading or playing a sound
--- inside the incident hook froze the game on the first teleport, so the hook
--- only queues and drainEvents plays from the loader's own game-thread call.
local EventWaves = {}
local EventQueue = {}
--- The game type the multiplayer menu started (pending_variant.txt), or the
--- level's own; picks the announcement at the first spawn.
local RunningVariant = nil
--- Events heard only by the player who caused them.
-- lap_complete is a health pack taken (blam_megalo::powerups): CE played its
-- pickup sound to the player who took it.
local PERSONAL = { teleporter_used = true, respawn_tick = true, respawn_final_tick = true, lap_complete = true }
--- The local player's absolute index in the engine's player table: 0 on the
--- host, the joiner's own slot on a fireteam client (1 for the first). Read
--- from the first local player's BlamPlayerStateComponent before events are
--- played; with 0 assumed, a client heard the host's respawn countdown
--- (silently, as it was not theirs) and never its own (two PCs, 2026-10-01).
local LOCAL_PLAYER = 0

local function refreshLocalPlayer()
    local ok, index = pcall(function()
        return getPlayerController().PlayerState.BlamPlayerStateComponent.BlamAbsolutePlayerIndex
    end)
    if ok and type(index) == "number" and index >= 0 then LOCAL_PLAYER = index end
end
--- The engine raises no game-start event on a converted map (only
--- player_spawn), so CE's announcement plays at the local player's first
--- spawn, by game type.
local START_EVENTS = {
    -- No line yet: events.json has no row, so it starts in silence rather
    -- than announce the wrong game.
    { "juggernaut", "juggernaut_game_start" },
    { "stalker", "juggernaut_game_start" },
    { "reverse_tag", "juggernaut_game_start" },
    { "slayer", "slayer_start" },
    { "koth", "koth_game_start" },
    { "king", "koth_game_start" },
    { "oddball", "ball_game_start" },
    { "ball", "ball_game_start" },
    { "ctf", "ctf_game_start" },
    { "assault", "ctf_game_start" },
    { "race", "race_game_start" },
    { "rally", "race_game_start" },
}
local START_EVENT_SET = {}
for _, e in ipairs(START_EVENTS) do START_EVENT_SET[e[2]] = true end

local function startEvent()
    local mode = string.lower(tostring(RunningVariant or (Current.level and Current.level.variant) or "slayer"))
    for _, e in ipairs(START_EVENTS) do
        if mode:find(e[1], 1, true) then return e[2] end
    end
    return "slayer_start"
end

local function personalEvent(name)
    return PERSONAL[name] or name:find("^multikill_x") or name:find("_in_a_row$")
end

local function preloadEventSounds()
    EventWaves = {}
    EventQueue = {}
    if not (EventSounds and Current.level and Current.level.multiplayer == true) then return end
    local n, failed = 0, 0
    for name, paths in pairs(EventSounds) do
        if type(paths) == "table" then
            -- Paths, not the waves: nothing holds a wave loaded from Lua, so
            -- the garbage collector frees it and later sounds went silent;
            -- each is found (or loaded again) as it plays.
            local waves = {}
            for _, path in ipairs(paths) do
                if resolveMesh(path) then waves[#waves + 1] = path else failed = failed + 1 end
            end
            if #waves > 0 then
                EventWaves[name] = waves
                n = n + #waves
            end
        end
    end
    Log(string.format("event sounds: %d wave(s) loaded, %d failed", n, failed))
end

--- Each incident's first occurrence per level is logged (with or without a
--- sound), so what a game type raises, and for whom, shows up.
local SilentIncidents = {}

--- Whether an incident concerns the local player: its cause or its effect,
--- or neither set (a team game raises the respawn countdown with no cause
--- player, and the ticks went silent under CTF).
local function isLocal(cause, effect)
    if cause == LOCAL_PLAYER or effect == LOCAL_PLAYER then return true end
    return (cause == nil or cause < 0) and (effect == nil or effect < 0)
end

local function playEvent(name, cause, value, effect)
    -- A flag's incident moves flags on and off their stands, and a new
    -- round resets them (teams.lua). No flag takes its colour from one.
    Teams.onIncident(name, value)
    if not SilentIncidents[name] then
        SilentIncidents[name] = true
        local heard = EventWaves[name] or (value and EventWaves[name .. ":" .. tostring(value)])
        Log(string.format("incident %s (cause %s, effect %s, value %s)%s", name, tostring(cause),
            tostring(effect), tostring(value), heard and "" or ": no sound"))
    end
    if personalEvent(name) and not isLocal(cause, effect) then return end
    if START_EVENT_SET[name] then
        if Current.announced then return end
        Current.announced = true
    end
    if name == "player_spawn" then
        if cause ~= LOCAL_PLAYER or Current.announced then return end
        Current.announced = true
        name = startEvent()
    end
    -- A team-specific line first: a script's incident carries its team as
    -- the value (CTF: the flag's, 0 red or 1 blue), keyed "name:value".
    local waves = (value and EventWaves[name .. ":" .. tostring(value)]) or EventWaves[name]
    if not waves then return end
    local wave = resolveMesh(waves[math.random(#waves)])
    local gs = findObject("/Script/Engine.Default__GameplayStatics")
    local world = getWorld()
    -- The announcer follows the dialogue slider (syncVolumes' sliders).
    local volume = gameVolume("announcer")
    if wave and gs and world and volume > 0 then
        pcall(function() gs:PlaySound2D(world, wave, volume, 1.0, 0.0, nil, nil, true) end)
    end
end

--- Play what the hook queued; runs on the game thread, outside any hook.
--- Incidents reach the host's incident handler for every player, a fireteam
--- client's for almost none (two PCs, 2026-10-03: the host heard a joiner's
--- teleporter_used, the joiner only its own player_spawn). The host relays
--- them over the controller RPC MJOLNIRLobby's messages use (ClientMessage
--- with type "MJOLNIR"; docs/multiplayer_postgame.md), and each client
--- filters them as its own (personalEvent / isLocal). Incidents a client
--- does get itself are not taken from the relay.
local RELAY_TYPE = "MJOLNIR"
local NativeIncidents = {}
local relayHooked = false

local function isHostWorld()
    local ok, yes = pcall(function() return getWorld().AuthorityGameMode:IsValid() end)
    return ok and yes == true
end

--- Whether a client has a use for an incident: one with a sound, or a flag's
--- (a grab takes the flag off its stand at once, and any flag incident puts
--- the skull's effect out again; teams.lua). Relaying every incident sent
--- six reliable messages for one sniper headshot, most of them silent, and
--- each one queued behind the last (playtest, 2026-10-03).
local function relayed(e)
    local name = e[1]
    if name == "player_spawn" or e.relayed then return false end
    return name:find("^flag_") ~= nil or EventWaves[name] ~= nil
        or (e[3] ~= nil and EventWaves[name .. ":" .. tostring(e[3])] ~= nil)
end

--- The world's controllers, from one FindAllOf every few seconds: a walk
--- per relay held the host's game thread ~20 ms each time an event came in.
local Controllers = { list = {}, at = -100, world = nil }
local function controllers()
    local world = Current.worldName
    if world ~= Controllers.world or os.clock() - Controllers.at > 5 then
        Controllers.list = FindAllOf("PlayerController") or {}
        Controllers.at, Controllers.world = os.clock(), world
    end
    return Controllers.list
end

local function relayEvents(queued)
    if not isHostWorld() then return end
    local messages = {}
    for _, e in ipairs(queued) do
        if relayed(e) then
            messages[#messages + 1] = string.format("MJOLNIR|event|%s|%s|%s|%s", tostring(e[1]),
                tostring(e[2] or -1), tostring(e[3] or 0), tostring(e[4] or -1))
        end
    end
    if #messages == 0 then return end
    local kind = FName(RELAY_TYPE)
    for _, pc in ipairs(controllers()) do
        pcall(function()
            if not pc:IsValid() or pc:IsLocalController() then return end
            if not (pc.Player:IsValid() and pc.PlayerState:IsValid()) then return end
            for _, msg in ipairs(messages) do pc:ClientMessage(msg, kind, 0) end
        end)
    end
end

--- Drain on the next tick rather than the next 100 ms poll: each side's
--- wait for its poll added up to ~117 ms to a relayed sound. Never from
--- inside the hook itself (playing a sound there froze the game).
local drainEvents
local drainPending = false
local function scheduleDrain()
    if drainPending then return end
    drainPending = true
    ExecuteInGameThread(function()
        drainPending = false
        pcall(drainEvents)
    end)
end

local function hookRelay()
    if relayHooked then return end
    relayHooked = pcall(function()
        RegisterHook("/Script/Engine.PlayerController:ClientMessage", function(_, s, kind)
            local okK, name = pcall(function() return kind:get():ToString() end)
            if not okK or name ~= RELAY_TYPE then return end
            local okS, text = pcall(function() return s:get():ToString() end)
            if not okS then return end
            local event, cause, value, effect = text:match("^MJOLNIR|event|([^|]*)|([^|]*)|([^|]*)|([^|]*)$")
            if not event or NativeIncidents[event] or #EventQueue >= 32 or isHostWorld() then return end
            EventQueue[#EventQueue + 1] = { event, tonumber(cause), tonumber(value), tonumber(effect), relayed = true }
            scheduleDrain()
        end)
    end)
    Log(relayHooked and "event sounds: relay from the host armed" or "event sounds: could not hook ClientMessage")
end

drainEvents = function()
    if #EventQueue == 0 then return end
    refreshLocalPlayer()
    local queued = EventQueue
    EventQueue = {}
    pcall(relayEvents, queued)
    for _, e in ipairs(queued) do
        local ok, err = pcall(playEvent, e[1], e[2], e[3], e[4])
        if not ok then Log("event " .. tostring(e[1]) .. ": " .. tostring(err)) end
    end
end

local function loadEventSounds()
    local raw = readFile(MOD_DIR .. "\\events.json")
    if not raw then return end
    local ok, t = pcall(Json.decode, raw)
    if not ok or type(t) ~= "table" then
        Log("events.json: " .. tostring(t))
        return
    end
    EventSounds = t
    local n = 0
    for _ in pairs(t) do n = n + 1 end
    Log(string.format("event sounds: %d event(s)", n))
end

local INCIDENT_EVENT = "/Game/Blueprints/BPC_MeteoriteIncidentHandlerComponent.BPC_MeteoriteIncidentHandlerComponent_C:OnIncident_Event"
local incidentHooked = false

--- Hook the incident handler once its Blueprint is loaded (it is not at the
--- main menu, where the mod starts); retried as levels load. The hook does
--- no more than read the event and queue it.
local function hookIncidents()
    if incidentHooked or not EventSounds then return end
    -- RegisterHook raises while the Blueprint is not loaded.
    incidentHooked = pcall(function()
        RegisterHook(INCIDENT_EVENT, function(_, incident)
            local okI, name, cause, value, effect = pcall(function()
                local i = incident:get()
                return i.Name:ToString(), i.CausePlayerAbsoluteIndex, i.CustomValue, i.EffectPlayerAbsoluteIndex
            end)
            -- Positive values are timed-objective score snapshots for the
            -- HUD, not another pickup/control announcement every second.
            if okI and (name == "ball_taken" or name == "hill_controlled")
                and type(value) == "number" and value > 0 then return end
            -- Flag incidents and the end of a round count without sounds
            -- too: they place the flags and reset them (teams.lua).
            if not (okI and name) or not (next(EventWaves) or name:find("^flag_") or name == "round_over") then return end
            if #EventQueue < 32 then
                NativeIncidents[name] = true
                EventQueue[#EventQueue + 1] = { name, cause, value, effect }
                scheduleDrain()
            end
        end)
    end)
    if incidentHooked then Log("event sounds: incident hook armed") end
end

--------------------------------------------------------------------------------
-- Breakable glass (converted Halo 2 maps)
--------------------------------------------------------------------------------

--- The sim breaks a sheet of glass (blam_sbsp::convert::rebuild_breakable)
--- and lets players through, but the glass is our mesh: a decor item lists
--- each sheet's mesh slots and its box in centimetres (`breakables`, from
--- tools/level/split_breakable_glass.py). The game's break effect names the
--- point it broke at; the sheet there loses its slots (M_CE_Hidden) and
--- throws glass chips. Sheets stay broken until the world is rebuilt.
local BREAK_EVENT = "/Game/Blueprints/FX/Breakable/Data/BP_BaseBreakableSurfaceEffect.BP_BaseBreakableSurfaceEffect_C:Spawn"
local BREAK_FX = "/Game/FX/Library/Sandbox/Weapons/Impacts/Glass/NS_Impact_Glass_Lrg.NS_Impact_Glass_Lrg"
local BREAK_PAD = 30.0 -- cm around a sheet's box: a melee or a body touches off its plane
local breakHooked = false

local function levelHasBreakables()
    for _, item in ipairs(Current.level and Current.level.decor or {}) do
        if type(item) == "table" and type(item.breakables) == "table" and #item.breakables > 0 then return true end
    end
    return false
end

--- The sheet whose padded box holds `p` (nearest centre wins), and its actor.
local function sheetAt(p)
    local best, bestActor, bestKey, bestD
    for index, item in ipairs(Current.level and Current.level.decor or {}) do
        if type(item) == "table" and type(item.breakables) == "table" then
            local actor = Current.actors[item.id or ("#" .. index)]
            for _, s in ipairs(item.breakables) do
                local lo, hi = s.min, s.max
                if type(lo) == "table" and type(hi) == "table"
                    and p.X >= lo[1] - BREAK_PAD and p.X <= hi[1] + BREAK_PAD
                    and p.Y >= lo[2] - BREAK_PAD and p.Y <= hi[2] + BREAK_PAD
                    and p.Z >= lo[3] - BREAK_PAD and p.Z <= hi[3] + BREAK_PAD then
                    local cx, cy, cz = (lo[1] + hi[1]) / 2 - p.X, (lo[2] + hi[2]) / 2 - p.Y, (lo[3] + hi[3]) / 2 - p.Z
                    local d = cx * cx + cy * cy + cz * cz
                    if not bestD or d < bestD then
                        best, bestActor, bestKey, bestD = s, actor, tostring(item.id or index) .. "/" .. tostring(s.sheet), d
                    end
                end
            end
        end
    end
    return best, bestActor, bestKey
end

local function shatter(world, sheet)
    local okF, nfl = pcall(findObject, "/Script/Niagara.Default__NiagaraFunctionLibrary")
    local fx = resolveMesh(BREAK_FX)
    if not (okF and nfl and fx) then return end
    local lo, hi = sheet.min, sheet.max
    -- Chips over the sheet: a 3 x 3 grid across its two long axes.
    local span = { hi[1] - lo[1], hi[2] - lo[2], hi[3] - lo[3] }
    for a = 0, 2 do
        for b = 0, 2 do
            local u, v = (a + 0.5) / 3, (b + 0.5) / 3
            local p
            if span[1] <= span[2] and span[1] <= span[3] then
                p = { X = (lo[1] + hi[1]) / 2, Y = lo[2] + span[2] * u, Z = lo[3] + span[3] * v }
            elseif span[2] <= span[3] then
                p = { X = lo[1] + span[1] * u, Y = (lo[2] + hi[2]) / 2, Z = lo[3] + span[3] * v }
            else
                p = { X = lo[1] + span[1] * u, Y = lo[2] + span[2] * v, Z = (lo[3] + hi[3]) / 2 }
            end
            -- Spawned inactive so its crack decal (Crack_Masked_Dithered) is
            -- off before the first frame: nine cracks on a grid stayed
            -- hanging where the glass had been, nowhere near the shots.
            pcall(function()
                local c = nfl:SpawnSystemAtLocation(world, fx, p, { Pitch = 0, Yaw = 0, Roll = 0 }, { X = 1, Y = 1, Z = 1 }, true, false, 0, true)
                c:SetEmitterEnable(FName("Crack_Masked_Dithered"), false)
                c:Activate(false)
            end)
        end
    end
end

--- A break, on the game thread's next pass: never in the break effect's own
--- call. The sim waits on that call, and a blocking load inside it (the
--- chips or the hide material, after a map reload emptied the asset cache)
--- deadlocked the game for good (2026-11-10).
local function breakAt(p)
    local sheet, actor, key = sheetAt(p)
    if not sheet or not actor or not actor:IsValid() then return end
    Current.broken = Current.broken or {}
    if Current.broken[key] then return end
    Current.broken[key] = true
    local hidden = resolveMesh(TRIAL_MASTERS .. "M_CE_Hidden.M_CE_Hidden")
    if hidden then
        for _, slot in ipairs(sheet.slots or {}) do
            pcall(function() actor.StaticMeshComponent:SetMaterial(slot, hidden) end)
        end
    end
    shatter(Current.world or getWorld(), sheet)
    Log(string.format("glass: sheet %s broke at (%.0f, %.0f, %.0f)", key, p.X, p.Y, p.Z))
end

local BreakQueue = {}
local breakDrainPending = false

local function drainBreaks()
    breakDrainPending = false
    local queued = BreakQueue
    BreakQueue = {}
    for _, p in ipairs(queued) do
        local ok, err = pcall(breakAt, p)
        if not ok then Log("glass: " .. tostring(err)) end
    end
end

--- The hook itself only reads the point and queues it.
local function onBreak(ev)
    local okP, p = pcall(function()
        local t = ev:get().Transform.Translation
        return { X = t.X, Y = t.Y, Z = t.Z }
    end)
    -- The effect's first call names no point (all zero).
    if not okP or not p or (p.X == 0 and p.Y == 0 and p.Z == 0) then return end
    if #BreakQueue >= 32 then return end
    BreakQueue[#BreakQueue + 1] = p
    if not breakDrainPending then
        breakDrainPending = true
        ExecuteInGameThread(drainBreaks)
    end
end

--- Each level with glass loads the chips and the hide material as it comes
--- up (the asset cache empties with every world), and hooks the break
--- effect once (its Blueprint is loaded by then); retried each tick until
--- the hook holds.
local function hookBreakables()
    local level = Current.level
    if not level then return end
    if level.hasBreakables == nil then level.hasBreakables = levelHasBreakables() end
    if not level.hasBreakables then return end
    if not Current.breakPreloaded then
        Current.breakPreloaded = true
        resolveMesh(BREAK_FX)
        resolveMesh(TRIAL_MASTERS .. "M_CE_Hidden.M_CE_Hidden")
    end
    if breakHooked then return end
    breakHooked = pcall(function()
        RegisterHook(BREAK_EVENT, function(_, ev)
            local ok, err = pcall(onBreak, ev)
            if not ok then Log("glass: " .. tostring(err)) end
        end)
    end)
    if breakHooked then Log("glass: break hook armed") end
end

local function fadeIn()
    local env = Current.level and Current.level.environment
    if type(env) ~= "table" or env.fade_in == false then return end
    -- A bake that replaces the mission's scripts (blam.clear.scripts) gives
    -- the scenario its own startup script, which fades in as the map starts.
    -- Fading in again when the pawn turns up, 20-30 s later on a converted
    -- multiplayer map, flashes the screen black.
    local blam = Current.level.blam
    if type(blam) == "table" and type(blam.clear) == "table" and blam.clear.scripts == true then
        Log("fade_in left to the scenario's startup script")
        return
    end
    local ok = pcall(function()
        local kismet = StaticFindObject("/Script/Engine.Default__KismetSystemLibrary")
        local pc = getPlayerController()
        if kismet and pc then
            kismet:ExecuteConsoleCommand(pc, "blam !(fade_in 0 0 0 15)", pc)
        end
    end)
    Log(ok and "fade_in requested" or "fade_in request failed")
end

--- `environment.weather`: CE's weather particle system (Coldsnap's snow),
--- drawn with one of the game's own Niagara systems (`system`), `copies` of
--- it, each told the `params` (user parameters by name, floats). The PNW
--- falling snow fills a box around its component, not around the view, so
--- the copies are kept at the camera unless `follow` is false. They are
--- placed in the world, not attached: the camera manager is a hidden actor,
--- and nothing attached to it draws. Called ten times a second, so each move
--- is small and goes as a teleport: moved once a second, the first move
--- after the spawn smeared every flake across the screen. A copy is spawned
--- where one is missing (the first spawns after the system loads can come
--- back empty).
---
--- `weather.roofs` (gen_ce_level.weather_roofs): the ceilings over the
--- level by cell. While one is above the camera within the reach the copies
--- are hidden: the box about the camera snowed through Coldsnap's roofs,
--- where CE's weather polys over the openings stopped its flakes.
local function updateWeather()
    -- Nested: the main chunk is at Lua's 200 locals.
    local function underRoof(roofs, at)
        if type(roofs) ~= "table" or type(roofs.cells) ~= "table" then return false end
        local cell = roofs.cell or 609.6
        local zs = roofs.cells[string.format("%d,%d", math.floor(at.X / cell), math.floor(at.Y / cell))]
        if type(zs) ~= "table" then return false end
        local reach = roofs.reach or 2500.0
        for _, z in ipairs(zs) do
            local above = z - at.Z
            if above > 0 and above <= reach then return true end
        end
        return false
    end
    local env = Current.furnished and Current.level and Current.level.environment
    local w = type(env) == "table" and env.weather
    if type(w) ~= "table" or type(w.system) ~= "string" then return end
    local pc = getPlayerController()
    local cm = pc and pc.PlayerCameraManager
    if not (cm and cm:IsValid()) then return end
    local at = cm:GetCameraLocation()
    local here = { X = at.X, Y = at.Y, Z = at.Z }
    local hidden = underRoof(w.roofs, here)
    local changed = hidden ~= (Current.weatherHidden or false)
    Current.weatherHidden = hidden
    if changed then Log(hidden and "weather: under a roof, hidden" or "weather: in the open, shown") end
    -- Moved when the camera has gone half a metre: each move is a call that
    -- leaves a reference behind (Current.hit), ten a second a copy.
    local last = Current.weatherAt
    local follow = w.follow ~= false and not (last and math.abs(here.X - last.X) < 50
        and math.abs(here.Y - last.Y) < 50 and math.abs(here.Z - last.Z) < 50)
    if follow then Current.weatherAt = here end
    local missing = {}
    for i = 1, math.max(1, math.min(w.copies or 1, 16)) do
        local comp = Current.actors["__weather" .. i]
        if comp and comp:IsValid() then
            if follow then comp:K2_SetWorldLocation(here, false, Current.emptyHit(), true) end
            if changed then pcall(function() comp:SetVisibility(not hidden, false) end) end
        else
            missing[#missing + 1] = i
        end
    end
    if #missing == 0 then return end
    local system = resolveMesh(w.system)
    local nfl = findObject("/Script/Niagara.Default__NiagaraFunctionLibrary")
    local world = getWorld()
    if not (system and nfl and world) then return end
    for _, i in ipairs(missing) do
        local ok, comp = pcall(function()
            return nfl:SpawnSystemAtLocation(world, system, here, { Pitch = 0, Yaw = 0, Roll = 0 },
                { X = 1, Y = 1, Z = 1 }, false, false, 0, false)
        end)
        if not (ok and comp and comp:IsValid()) then return end
        for name, value in pairs(type(w.params) == "table" and w.params or {}) do
            if type(value) == "number" then
                pcall(function() comp:SetVariableFloat(FName(name), value) end)
            end
        end
        comp:Activate(true)
        if hidden then pcall(function() comp:SetVisibility(false, false) end) end
        Current.actors["__weather" .. i] = comp
    end
    Log(string.format("weather: %d of %d cop%s of %s", #missing, w.copies or 1,
        (w.copies or 1) == 1 and "y" or "ies", w.system:match("[^./]+$") or w.system))
end

--------------------------------------------------------------------------------
-- Water: CE water as rolling, reflecting water (M_CE_Ocean)
--------------------------------------------------------------------------------

--- `environment.water` / `mjolnir_water`: a converted map's CE water
--- (M_CE_Water) drawn with M_CE_Ocean (chunk 982,
--- unreal/MJOLNIRMaterials/Scripts/build_ce_water.py): translucent water
--- that clears over the shallows by its depth, with a Gerstner swell moving
--- the surface and CE's own ripple maps on top (docs/ce_map_conversion.md,
--- "Water"). It reflects CE's own cube map, as CE's water did (oceanSpec
--- passes the slot's ReflectionCube, brightness and tints on). It is not
--- Single Layer Water because the game forces that model's refraction off:
--- it never showed the sand under it, and drew a line along every beach.
---
--- Only water on a mesh of its own (SM_<map>_Water, build_terrain_meshes.py).
--- Unreal takes a rewritten mesh's passes from slot 0: on the translucent
--- mesh, Single Layer Water drew unlit, and giving it slot 0 took the glass,
--- teleporter fields and shore foam out of the translucency pass. Maps
--- converted before the split keep CE's water.
---
--- What else changes while it is on (Death Island, 2026-10-11):
--- - The sky light stays as spawnEnvironment left it. (Its cube map never
---   reached translucent water; given a lower half that was not black, it
---   came back as neon cyan glints on the Single Layer Water before.)
--- - CE's shore foam (transparent sections whose maps are named for waves)
---   is faded out: it is flat, and the moving surface cut it into a dashed
---   line and smeared it.
--- - CE's planar fog is off (oceanFog): the water hides the sea floor by its
---   own depth now, and CE's (Death Island: opaque 30 cm away and 46 cm
---   down) turned the sand to fog within half a metre of the waterline.
---
--- (The game's own Fluid Flux ocean, tried first on 2026-10-10, draws its
--- waves only beyond a few hundred metres of the camera: near the player it
--- leaves the surface to Fluid Flux's runtime mesh generator.)
---
--- Fields: `style` ("ocean" or "ce", the default), `waves` (the swell's
--- WaveAmplitude, 0.35 by default: Death Island's swell at 1 broke over the
--- beach), `params` (more of M_CE_Ocean's parameters by name: numbers for
--- scalars, 4-number lists for vectors).
local OCEAN = "/Game/MJOLNIR/Water/M_CE_Ocean.M_CE_Ocean"
local CE_WATER = "/Game/MJOLNIR/CE/M_CE_Water.M_CE_Water"
-- The chop on M_CE_Ocean close up: the game's own detail wave map (the
-- Fluid Flux ocean's), a game asset loaded by path. CE's ripple maps are
-- too coarse for it, and stronger they reflected the beach as blots.
local DETAIL_WAVE = "/Game/FluidFlux/Surface/Materials/Textures/T_DetailWaveTexture_01.T_DetailWaveTexture_01"
local WAVES = 0.35

-- `mjolnir_water`: the style and swell for every level loaded later, until
-- the game closes; nil hands them back to each level file.
local WaterOverride = { style = nil, waves = nil }

local function waterEnv()
    local env = Current.level and Current.level.environment
    return type(env) == "table" and type(env.water) == "table" and env.water or {}
end

local function waterStyle()
    return WaterOverride.style or waterEnv().style or "ce"
end

local function waveAmplitude()
    return WaterOverride.waves or waterEnv().waves or WAVES
end

--- Every decor slot the level draws with M_CE_Water, from the level file
--- (each slot's spec, so CE's material can be rebuilt from it), and whether
--- its mesh is the water's own; and CE's shore foam, the transparent slots
--- whose maps are named for waves. The tint pass beside some water
--- (M_CE_WaterBackground) and sky water stay as they are.
local function ceWaterSlots()
    local slots, foam = {}, {}
    for _, item in ipairs(type(Current.level.decor) == "table" and Current.level.decor or {}) do
        local actor = type(item) == "table" and Current.actors[item.id]
        if actor and actor:IsValid() and type(item.materials) == "table" then
            local comp = actor.StaticMeshComponent
            local own = type(item.mesh) == "string" and item.mesh:find("_Water%.") ~= nil
            for i, entry in ipairs(item.materials) do
                local s = { comp = comp, slot = i - 1, spec = entry, id = item.id, own = own }
                if type(entry) == "table" and entry.parent == CE_WATER then
                    slots[#slots + 1] = s
                elseif type(entry) == "table" and type(entry.parent) == "string"
                    and entry.parent:find("/M_CE_Transparent", 1, true) then
                    for _, tex in pairs(type(entry.textures) == "table" and entry.textures or {}) do
                        if type(tex) == "string" and tex:lower():find("wave") then
                            foam[#foam + 1] = s
                            break
                        end
                    end
                end
            end
        end
    end
    return slots, foam
end

--- An M_CE_Ocean spec from a CE water slot's: its ripple maps and their
--- motion, its reflection (cube, brightness, tints), the swell, and the
--- level's own parameters.
local function oceanSpec(spec)
    local o = { parent = OCEAN, textures = { DetailWave = DETAIL_WAVE }, scalars = { WaveAmplitude = waveAmplitude() },
        vectors = {} }
    for k, v in pairs(type(spec.textures) == "table" and spec.textures or {}) do
        if k:find("^RippleMap") or k == "ReflectionCube" then o.textures[k] = v end
    end
    for k, v in pairs(type(spec.vectors) == "table" and spec.vectors or {}) do
        if k:find("^Ripple") or k == "PerpTint" or k == "ParaTint" then o.vectors[k] = v end
    end
    for k, v in pairs(type(spec.scalars) == "table" and spec.scalars or {}) do
        if k == "PerpBrightness" or k == "ParaBrightness" then o.scalars[k] = v end
    end
    local p = waterEnv().params
    for k, v in pairs(type(p) == "table" and p or {}) do
        if type(v) == "number" then o.scalars[k] = v elseif type(v) == "table" then o.vectors[k] = v end
    end
    return o
end

--- A CE transparent slot faded out entirely: the masters fade by their
--- atmospheric fog (TRANSPARENT_CODE), full from distance 0, for every blend.
local function fadeOut(s)
    local mat = s.comp:GetMaterial(s.slot)
    mat:SetScalarParameterValue(FName("FogDensity"), 1.0)
    mat:SetScalarParameterValue(FName("FogStart"), -1.0)
    mat:SetScalarParameterValue(FName("FogOpaque"), 0.0)
end

--- The terrain's CE planar fog off while the ocean is `on`, or as the level
--- file has it. Every decor slot with PlanarFogParams but the water's own.
local function oceanFog(on)
    local n = 0
    for _, item in ipairs(type(Current.level.decor) == "table" and Current.level.decor or {}) do
        local actor = type(item) == "table" and Current.actors[item.id]
        if actor and actor:IsValid() and type(item.materials) == "table" then
            local comp = actor.StaticMeshComponent
            for i, entry in ipairs(item.materials) do
                local p = type(entry) == "table" and type(entry.vectors) == "table" and entry.vectors.PlanarFogParams
                if type(p) == "table" and (p[4] or 0) > 0.5 then
                    local ok = pcall(function()
                        comp:GetMaterial(i - 1):SetVectorParameterValue(FName("PlanarFogParams"), {
                            R = p[1], G = p[2], B = p[3], A = on and 0 or 1 })
                    end)
                    if ok then n = n + 1 end
                end
            end
        end
    end
    return n
end

local function rebuild(world, s)
    local ok, mat = pcall(runtimeMaterial, world, s.spec, string.format("%s_%d", s.id, s.slot))
    return ok and mat and pcall(function() s.comp:SetMaterial(s.slot, mat) end)
end

--- Draw the level's CE water in the style asked for (waterStyle), once the
--- decor is up (a step of the dressing); again whenever `mjolnir_water`
--- changes it.
local function applyWater(world)
    if not (Current.level and (Current.furnished or Current.dressing)) then return end
    local slots, foam = ceWaterSlots()
    if #slots == 0 then return end
    local style = waterStyle()
    local was = Current.water and Current.water.style or "ce"
    if style ~= "ocean" then
        if was ~= "ocean" then return end
        for _, s in ipairs(slots) do rebuild(world, s) end
        for _, s in ipairs(foam) do rebuild(world, s) end
        pcall(oceanFog, false)
        Current.water = { style = "ce" }
        Log(string.format("water: %d slot(s) back to CE's", #slots))
        return
    end

    local own = {}
    for _, s in ipairs(slots) do
        if s.own then own[#own + 1] = s end
    end
    if #own == 0 then
        Log("water: this map's water shares its translucent mesh (converted before SM_<map>_Water); CE's kept")
        return
    end
    if not resolveMesh(OCEAN) then
        Log("water: M_CE_Ocean is not installed (pakchunk982); CE's kept")
        return
    end
    local done = 0
    for _, s in ipairs(own) do
        local ok, mat = pcall(runtimeMaterial, world, oceanSpec(s.spec), string.format("%s_%d_ocean", s.id, s.slot))
        if ok and mat and pcall(function() s.comp:SetMaterial(s.slot, mat) end) then done = done + 1 end
    end
    local faded = 0
    for _, s in ipairs(foam) do
        if pcall(fadeOut, s) then faded = faded + 1 end
    end
    pcall(oceanFog, true)
    Current.water = { style = "ocean", slots = done }
    Log(string.format("water: %d of %d slot(s) as M_CE_Ocean, waves x%.2f, %d foam slot(s) faded", done, #slots,
        waveAmplitude(), faded))
end

--- `mjolnir_water [ocean|ce|default] | [waves <x>|waves default]`: draw CE
--- water as M_CE_Ocean or as CE's, on this level and every one loaded later
--- until the game closes (`default` hands it back to the level file).
--- No argument reports it.
local function waterCommand(args)
    local arg, value = args and args[1], args and args[2]
    if arg == "ocean" or arg == "ce" then
        WaterOverride.style = arg
    elseif arg == "default" then
        WaterOverride.style = nil
    elseif arg == "waves" and (tonumber(value) or value == "default") then
        WaterOverride.waves = tonumber(value)
        -- A new swell reaches the water through a fresh application.
        if Current.water and Current.water.style == "ocean" then Current.water.style = "reapply" end
    elseif arg ~= nil then
        Log("usage: mjolnir_water [ocean | ce | default] | [waves <x> | waves default]")
        return
    end
    local world = getWorld()
    if arg ~= nil and world then applyWater(world) end
    Log(string.format("water: %s%s, waves x%.2f", waterStyle(), WaterOverride.style and " (set by command)" or "",
        waveAmplitude()))
end

--------------------------------------------------------------------------------
-- Foliage: the game's own grass where a converted map draws grass
--------------------------------------------------------------------------------

--- `foliage` in the level file (tools/level/scatter_grass.py): `file`, the
--- clumps beside the level file (FOLIAGE_MAGIC, then per group a count and
--- that many x, y, z float32 cm, yaw in 256ths of a turn and scale in
--- hundredths), `groups` [{ mesh, tint, tint_param, params, scalars, material, cull, shadow, bands }] in the
--- file's order (tools/level/scatter_foliage.py: grass, tufts, rocky
--- ground, stones), and optional `cull` [start, end] cm for groups without
--- their own and `wind` { dir = [x, y], strength = 0..1 }.
--- Each group is one hierarchical instanced mesh (Death Island: 380,000
--- clumps in five). The grass is the game's Megascans grass (B30's beach),
--- tinted through its Color Overlay. `mjolnir_foliage off` leaves it out
--- until the game closes.
--- MJF2 files (scatter_foliage.py since 2026-10-11) add to each clump the
--- ground's normal x and y in 127ths, a signed byte each: rocks lie along
--- the slope (0, 0 stands upright, as every MJFG clump does).
--- MJF3 adds three colour bytes a record (100ths; 255s for none), the CE
--- light where a cliff group's rock sits. Cliff groups (`cliff`,
--- scatter_foliage's cladding) are mesh actors, one a rock, not instances:
--- this game's renderer drew our materials black on instanced meshes. They
--- are drawn in the cliffs' rock once the landscape is applied (Land.cliffs,
--- from Foliage.cliffGroups: the actors, the wall's base map, the group's
--- light).
local Foliage = { MAGIC = "MJFG", MAGIC2 = "MJF2", MAGIC3 = "MJF3", CULL = { 5000, 9000 }, on = true, cliffGroups = {} }

--- A clump's rotation: turned `yaw` (radians) about the vertical, then tilted
--- so its up is the ground normal (nx, ny, up).
function Foliage.rotation(yaw, nx, ny)
    local hz, hw = math.sin(yaw / 2), math.cos(yaw / 2)
    local s2 = nx * nx + ny * ny
    if s2 < 1e-6 then return { X = 0, Y = 0, Z = hz, W = hw } end
    local nz = math.sqrt(math.max(1 - s2, 0))
    -- From up to the normal: about (-ny, nx, 0) by acos(nz).
    local half = math.acos(math.min(nz, 1)) / 2
    local k = math.sin(half) / math.sqrt(s2)
    local ax, ay, aw = -ny * k, nx * k, math.cos(half)
    -- tilt * yaw (the yaw is applied first)
    return { X = ax * hw + ay * hz, Y = ay * hw - ax * hz, Z = aw * hz, W = aw * hw }
end

--- The game's foliage wind (HaloFoliageAndWindInteractions) blows only where
--- its wind flowmap is filled, which BP_Wind_Flowmap_Generator does in the
--- game's levels and nothing does on a converted map's world. Spawning the
--- game's wind simulation manager crashed the game (2026-10-11). This does
--- what the generator's UpdateMPC and UpdateFlowmap do, for one steady wind:
--- the flowmap's extents and origin over the level and its top speed in the
--- parameter collection, the flowmap cleared to the wind (0.5 is calm, red
--- and green the direction), the gust mask to white.
function Foliage.wind(world, wind, centre)
    local kml = findObject("/Script/Engine.Default__KismetMaterialLibrary")
    local krl = findObject("/Script/Engine.Default__KismetRenderingLibrary")
    local mpc = resolveMesh("/HaloFoliageAndWindInteractions/Materials/MPC_GlobalFlowmapWind.MPC_GlobalFlowmapWind")
    local flow = resolveMesh("/HaloFoliageAndWindInteractions/Storage/RT_GlobalFlowmapWind.RT_GlobalFlowmapWind")
    local gust = resolveMesh("/HaloFoliageAndWindInteractions/Storage/RT_GlobalFlowmapGustMask.RT_GlobalFlowmapGustMask")
    if not (kml and krl and mpc and flow and gust) then return false end
    local half = 200000
    kml:SetVectorParameterValue(world, mpc, FName("Flowmap_Dimensions"), { R = 2 * half, G = 2 * half, B = 0, A = 0 })
    kml:SetVectorParameterValue(world, mpc, FName("Flowmap_Origin"),
        { R = centre[1] - half, G = centre[2] - half, B = 0, A = 0 })
    kml:SetScalarParameterValue(world, mpc, FName("Flowmap_MaxWindSpeed(m/s)"), 15)
    local dir = type(wind.dir) == "table" and wind.dir or { 0.9, 0.4 }
    local len = math.max(math.sqrt(dir[1] * dir[1] + dir[2] * dir[2]), 1e-3)
    local k = (wind.strength or 0.4) * 0.5
    krl:ClearRenderTarget2D(world, flow, { R = 0.5 + k * dir[1] / len, G = 0.5 + k * dir[2] / len, B = 0.5, A = 1 })
    krl:ClearRenderTarget2D(world, gust, { R = 1, G = 1, B = 1, A = 1 })
    return true
end

--- A cliff group's rocks (MJF3 records from `pos`) as mesh actors, no
--- collision; returns the position after them.
function Foliage.spawnCladding(world, g, group, mesh, raw, pos, size)
    local cls = findObject("/Script/Engine.StaticMeshActor")
    local actors = {}
    for k = 1, size do
        local x, y, z, yaw, scale, nx, ny, lr, lg, lb
        x, y, z, yaw, scale, nx, ny, lr, lg, lb, pos = string.unpack("<fffBBbbBBB", raw, pos)  -- luacheck: ignore 143 (Lua 5.4's string.unpack)
        if mesh and cls then
            local actor = world:SpawnActor(cls, { X = x, Y = y, Z = z }, { Pitch = 0, Yaw = 0, Roll = 0 })
            if actor and actor:IsValid() then
                local s = scale / 100
                actor:SetMobility(MOBILITY_MOVABLE)
                local c = actor.StaticMeshComponent
                c:SetStaticMesh(mesh)
                c:SetCollisionEnabled(COLLISION_NONE)
                -- Out of Lumen's bounce: 3,000 rocks lit by the cliffs' fill
                -- (emissive) bounced the whole scene orange.
                pcall(function() c:SetAffectDynamicIndirectLighting(false) end)
                -- The CE light where it sits (group.lm: the record's colour
                -- bytes, gamma), which M_CE_CliffPBR shades it by
                -- (CladLight.a 2) as the wall under it is shaded.
                if group.lm then
                    pcall(function()
                        c:SetCustomPrimitiveDataFloat(0, lr / 255)
                        c:SetCustomPrimitiveDataFloat(1, lg / 255)
                        c:SetCustomPrimitiveDataFloat(2, lb / 255)
                    end)
                end
                actor:K2_SetActorTransform({ Rotation = Foliage.rotation(yaw * math.pi / 128, nx / 127, ny / 127),
                    Translation = { X = x, Y = y, Z = z }, Scale3D = { X = s, Y = s, Z = s } }, false, Current.emptyHit(), true)
                actors[#actors + 1] = actor
                Current.actors[string.format("__clad_%d_%d", g, k)] = actor
            end
        end
    end
    Foliage.cliffGroups[#Foliage.cliffGroups + 1] = { actors = actors, base = group.base, light = group.light,
        lm = group.lm }
    return pos
end

--- The level's ambient life and weather (level.effects, from
--- tools/level/scenery_swap.py's effects): the game's own Niagara systems,
--- `placed` [{ system, pos, rot, scale }] where they are (gulls over a
--- beach, butterflies over the grass, leaves falling from a tree, surf on
--- the shore) and `camera` [system] riding with the player's camera (dust
--- in the air). `mjolnir_effects off` leaves them out until the game closes.
local Effects = { on = true }

function Effects.spawn(world)
    local fx = Current.level and Current.level.effects
    if not Effects.on or type(fx) ~= "table" then return end
    local nfl = findObject("/Script/Niagara.Default__NiagaraFunctionLibrary")
    if not nfl then return end
    local origin = (Current.level.canvas or {}).origin or { 0, 0, 0 }
    local placed, failed = 0, 0
    for _, e in ipairs(type(fx.placed) == "table" and fx.placed or {}) do
        local system = type(e) == "table" and type(e.system) == "string" and resolveMesh(e.system)
        local p = type(e) == "table" and e.pos
        if system and type(p) == "table" then
            local r = type(e.rot) == "table" and e.rot or {}
            local s = tonumber(e.scale) or 1.0
            local ok = pcall(function()
                nfl:SpawnSystemAtLocation(world, system,
                    { X = origin[1] + p[1], Y = origin[2] + p[2], Z = origin[3] + p[3] },
                    { Pitch = r[1] or 0, Yaw = r[2] or 0, Roll = r[3] or 0 }, { X = s, Y = s, Z = s },
                    false, true, 0, false)
            end)
            if ok then placed = placed + 1 else failed = failed + 1 end
        else
            failed = failed + 1
        end
    end
    local attached = 0
    local pc = getPlayerController()
    local root = pc and pc.PlayerCameraManager and pc.PlayerCameraManager.TransformComponent
    for _, path in ipairs(type(fx.camera) == "table" and fx.camera or {}) do
        local system = type(path) == "string" and resolveMesh(path)
        if system and root then
            if pcall(function()
                nfl:SpawnSystemAttached(system, root, FName("None"), { X = 0, Y = 0, Z = 0 },
                    { Pitch = 0, Yaw = 0, Roll = 0 }, 0, false, true, 0, false)
            end) then attached = attached + 1 end
        end
    end
    Log(string.format("effects: %d placed, %d on the camera, %d failed", placed, attached, failed))
end

--- The level's waterfalls (level.waterfalls): the game's large waterfall
--- (BP_PNW_Liquid_Waterfall_DeformedMesh: a sheet of water bent along a
--- ballistic path, built by its construction script) where CE drew a flat
--- scrolling card, each { pos, yaw, params, vectors, scalars, effects }:
--- `pos` the lip (cm from the canvas origin), `yaw` the way the water
--- leaves it, `params` the Blueprint's own (duration, Speed, BaseWidth,
--- EndWidth, BaseThickness, EndThickness, NoiseStrength, Instances...),
--- `vectors`/`scalars` its water material's (SkyColor: the PNW sky's blue
--- drew a saturated blue sheet under a CE dusk), `effects` the splash and
--- spray at its foot [{ system, pos, rot, scale }], `sheet` false to leave
--- the Blueprint out (the falls drawn by Effects.flux). The CE card is hidden by
--- the level file itself (upgrade_ce_map.py). Timberland, 2026-10-14.
Effects.WATERFALL = "/Game/FX/Library/Environment/PNW/Liquids/LargeWaterfall/BP_PNW_Liquid_Waterfall_DeformedMesh.BP_PNW_Liquid_Waterfall_DeformedMesh_C"
Effects.WATERFALL_MESH = "/Game/FX/Library/Environment/PNW/Liquids/LargeWaterfall/Meshes/SM_Liquid_TileableWaterfallLower.SM_Liquid_TileableWaterfallLower"

function Effects.waterfalls(world)
    local list = Current.level and Current.level.waterfalls
    if type(list) ~= "table" or #list == 0 then return end
    local ksl = findObject("/Script/Engine.Default__KismetSystemLibrary")
    local cls = ksl:LoadClassAsset_Blocking(ksl:Conv_SoftClassPathToSoftClassRef(ksl:MakeSoftClassPath(Effects.WATERFALL)))
    if not (cls and cls:IsValid()) then error("waterfall class not found") end
    local mesh = resolveMesh(Effects.WATERFALL_MESH)
    local nfl = findObject("/Script/Niagara.Default__NiagaraFunctionLibrary")
    local origin = (Current.level.canvas or {}).origin or { 0, 0, 0 }
    local n, fx = 0, 0
    for i, w in ipairs(list) do
        local p = type(w) == "table" and w.pos
        local key = "__waterfall_" .. i
        -- `sheet: false`: the effects at its foot only, the water itself
        -- being Fluid Flux's (Effects.flux).
        local done = Current.actors[key] or Current.actors[key .. "_fx1"]
        if type(p) == "table" and not (done and done:IsValid()) then
            local actor = w.sheet ~= false and world:SpawnActor(cls,
                { X = origin[1] + p[1], Y = origin[2] + p[2], Z = origin[3] + p[3] },
                { Pitch = 0, Yaw = tonumber(w.yaw) or 0, Roll = 0 })
            if actor and actor:IsValid() then
                Current.actors[key] = actor
                actor.Mesh = mesh
                for k, v in pairs(type(w.params) == "table" and w.params or {}) do
                    pcall(function() actor[k] = v end)
                end
                actor:UserConstructionScript()
                pcall(function() actor["Text Render"]:SetVisibility(false, false) end)
                pcall(function()
                    local m = actor.InstancedStaticMesh:GetMaterial(0)
                    for k, v in pairs(type(w.scalars) == "table" and w.scalars or {}) do
                        m:SetScalarParameterValue(FName(k), v)
                    end
                    for k, v in pairs(type(w.vectors) == "table" and w.vectors or {}) do
                        m:SetVectorParameterValue(FName(k), { R = v[1], G = v[2], B = v[3], A = v[4] or 1 })
                    end
                end)
                n = n + 1
            end
            for j, e in ipairs(type(w.effects) == "table" and w.effects or {}) do
                local system = type(e.system) == "string" and resolveMesh(e.system)
                local q = type(e.pos) == "table" and e.pos
                if system and q and nfl then
                    local r = type(e.rot) == "table" and e.rot or {}
                    local s = tonumber(e.scale) or 1.0
                    local ok, comp = pcall(function()
                        return nfl:SpawnSystemAtLocation(world, system,
                            { X = origin[1] + q[1], Y = origin[2] + q[2], Z = origin[3] + q[3] },
                            { Pitch = r[1] or 0, Yaw = r[2] or 0, Roll = r[3] or 0 }, { X = s, Y = s, Z = s },
                            false, true, 0, false)
                    end)
                    if ok and comp then
                        Current.actors[key .. "_fx" .. j] = comp
                        fx = fx + 1
                    end
                end
            end
        end
    end
    Log(string.format("waterfalls: %d of %d, %d effect(s)", n, #list, fx))
end

--- Fluid Flux over the level's rivers (level.flux, upgrade_ce_map.py
--- flux_spec): A30's shallow-water simulation, live. `domain` { centre, res,
--- cell, height } is the simulated rectangle (cells of `cell` cm; the area
--- spans centre Z - 0.75 height .. + 0.25 height), `surface` the Flux surface
--- Blueprint that draws it, `sources` [{ pos, scale, volume, mode, velocity }]
--- its modifiers (BE_FluxMode: 0 Add, 1 Set, 2 Adjust; a source's Z is the
--- level Set and Adjust work to, scale x 10 m its size; Duration -1 or it
--- lasts one step). The ground is captured once, from above: every actor the
--- loader spawned but `ground` is tagged out of it (a tree drew as a glass
--- spike of water), and `hide` (CE's own river mesh) is hidden. It starts
--- a few seconds in, the landscape streamed in first. Timberland, 2026-10-14.
Effects.FLUX_DOMAIN = "/Game/FluidFlux/Simulation/Blueprints/BP_FluxSimulationDomain.BP_FluxSimulationDomain_C"
Effects.FLUX_SOURCE = "/Game/FluidFlux/Simulation/Modifiers/BP_FluxModifierSourceActor.BP_FluxModifierSourceActor_C"
Effects.FLUX_SURFACE = "/Game/FluidFlux/Surface/Templates/River/BP_FluxSurface_River.BP_FluxSurface_River_C"

--- Optional river colour, on the new Flux surface's own material instances.
--- CE's rivers.spec belongs to the hidden CE water and cannot colour Flux.
function Effects.fluxColor(surf, spec)
    if type(spec.color_preset) == "string" then
        local preset = resolveMesh(spec.color_preset)
        if not preset then error("Flux colour preset not found: " .. spec.color_preset) end
        surf.BaseColorPreset = preset
        surf:ApplyColor()
    end
    if type(spec.surface_vectors) == "table" then
        local materials = surf.MaterialInstances
        for i = 1, #materials do
            for key, v in pairs(spec.surface_vectors) do
                materials[i]:SetVectorParameterValue(FName(key), { R = v[1], G = v[2], B = v[3], A = v[4] or 1 })
            end
        end
    end
end

--- The sea as B30's beach has it (level.flux.coast): Fluid Flux's ocean wave
--- (BP_FluxOceanWave) and a coastline domain, which captures the ground
--- under `centre` (`res` cells of `cell` cm, `height` cm deep), builds the
--- shore's distance field from it and draws the sea with
--- BP_FluxSurface_Coastline: waves to the camera, breaking on the beach.
--- `water` is the sea level (cm). Returns a line for the log. Death Island,
--- 2026-10-14.
Effects.FLUX_COAST = "/Game/FluidFlux/Coastline/Blueprints/BP_FluxCoastlineDomain.BP_FluxCoastlineDomain_C"
Effects.FLUX_WAVE = "/Game/FluidFlux/Waves/Blueprints/BP_FluxOceanWave.BP_FluxOceanWave_C"

function Effects.fluxCoast(w, k, origin, cls, gs, tag)
    local c = { X = origin[1] + k.centre[1], Y = origin[2] + k.centre[2], Z = origin[3] + k.water }
    Current.actors["__flux_wave"] = w:SpawnActor(cls(Effects.FLUX_WAVE), c, { Pitch = 0, Yaw = 0, Roll = 0 })
    -- The domain a little over the water (`lift` cm, B30's ~6 m: its actor at
    -- 605.7, its sea at 20), the sea's height given apart. Level with the
    -- water, it found no shore: the surf drew no white water and no run-up
    -- up the beach (Death Island, 2026-10-14).
    local dz = { X = c.X, Y = c.Y, Z = c.Z + (tonumber(k.lift) or 600.0) }
    local xf = { Rotation = { X = 0, Y = 0, Z = 0, W = 1 }, Translation = dz, Scale3D = { X = 1, Y = 1, Z = 1 } }
    local dom = gs:BeginDeferredActorSpawnFromClass(w, cls(Effects.FLUX_COAST), xf, 1, nil, 0)
    dom.AreaResolution = { X = k.res[1], Y = k.res[2] }
    dom.AreaWorldPixelSize = math.floor(k.cell)
    dom.AreaWorldHeight = k.height or 10000.0
    dom.WaterSurfaceHeight = origin[3] + k.water
    dom.HeightmapUpdateFrequency = 1000000.0
    local cv = dom.CaptureVisibility
    cv.ActorsWithTags_47_FB1C9D8B486CC31A912C34BC8E3BB996 = tag
    cv.UseInstancedMeshes_64_5640381C4A7506AD66F872A101E54AB7 = false
    cv.UseFoliageMeshes_63_108019E4475E89156CB35DA9D2A91E33 = false
    dom.CaptureVisibility = cv
    -- The Landscape out of the coast's capture: it runs under the sea a
    -- metre down, so the whole domain read as shallows, a milky square with
    -- a hard edge against the open sea. CE's own beach (made whole for the
    -- capture) gives the shore. The river keeps it: its banks. A coast with a
    -- `seabed` (build_landscape.py --sea: the floor shelving away from the
    -- shore) keeps it too: the shelf is what the surf breaks on.
    pcall(function()
        if k.seabed then return end
        local land = Current.landscapeActor(w)
        if land and land:IsValid() then
            local t = land.Tags
            t[#t + 1] = tag
        end
    end)
    gs:FinishSpawningActor(dom, xf, 0)
    Current.actors["__flux_coast"] = dom
    -- The surface the domain made takes its waves from OceanWaveActor (B30
    -- sets it in the level); unset, the sea was a pale flat sheet with no
    -- swell and no surf. InitializeStates hands the wave to its materials.
    local wave = Current.actors["__flux_wave"]
    ExecuteInGameThreadWithDelay(1500, function()
        pcall(function()
            local surf = dom:IsValid() and dom.SurfaceActorRenderer
            if surf and surf:IsValid() and wave:IsValid() then
                -- `swell`: the wave height (cm); B30's is 140, the actor's
                -- 230. Death Island's sea floor lies a metre down far out,
                -- so a 140 cm swell's troughs bared sandbars all over the
                -- shallows: water "in random places" (2026-10-14).
                wave.OceanWaveHeight = tonumber(k.swell) or 140.0
                -- B30's shore waves (its MIDs' WaveProfile*/ShoreWave*,
                -- which InitializeStates derives from these): with the
                -- actor's defaults the beach got no run-up, only a flat
                -- plane cutting the sand.
                wave.WaveProfileSize = 550
                wave.WaveAnimationDistance = 8
                wave.WaveMovementSpeed = 0.3
                wave.WaveAnimationSpeed = 2
                wave.WaveProfileAreaBlend = 1.5
                surf.OceanWaveActor = wave
                surf:InitializeStates()
                -- Two B30 values the actor does not set.
                for _, m in ipairs({ surf.SurfaceOverInstance, surf.SurfaceDistantInstance }) do
                    m:SetScalarParameterValue(FName("WaveGroundPrediction"), 1100)
                    m:SetScalarParameterValue(FName("CoastlineScattringHeight"), 0.004)
                end
            end
        end)
    end)
    return string.format("coast %dx%d at %d cm, sea at %g", k.res[1], k.res[2], math.floor(k.cell), k.water)
end

--- A coast takes its ground once, as it spawns. A capture that drew nothing
--- leaves the ground map at its clear value, far over the sea, so the domain
--- reads as land all the way across: its coast map's red channel is saturated
--- and the sea draws only outside the domain, the seabed bare inside it. Seen
--- once on PC 2 (Yoyorast, 2026-11-06) and not on demand since; taking the
--- capture again brought the sea straight back. A healthy coast has open sea
--- at some of these (Yoyorast and Death Island read 0 at three of the five),
--- and each read waits on the GPU, so only these few.
Effects.COAST_SAMPLES = { { 0.25, 0.25 }, { 0.75, 0.25 }, { 0.5, 0.5 }, { 0.25, 0.75 }, { 0.75, 0.75 } }
Effects.COAST_LAND = 254.0
--- Seconds between tries. A capture costs a frame of about 0.7 s, so a coast
--- gets this many and no more, however it reads.
Effects.COAST_RETRIES = { 2000, 5000, 10000 }

--- Whether the coast map reads as land everywhere; nil when it cannot be read.
function Effects.coastDry(dom)
    local w = getWorld()
    local lib = findObject("/Script/Engine.Default__KismetRenderingLibrary")
    local rt = dom.CoastlineMap
    if not (w and lib and rt and rt:IsValid()) then return nil end
    for _, uv in ipairs(Effects.COAST_SAMPLES) do
        local c = lib:ReadRenderTargetRawUV(w, rt, uv[1], uv[2], false)
        if c.R < Effects.COAST_LAND then return false end
    end
    return true
end

--- Take the coast's ground capture again, then look at it again, until it
--- reads right or the tries run out; `done` (the ground put back) runs then.
--- `try` counts from 1. A level left behind is left alone.
function Effects.coastCheck(level, try, done)
    local dom = Current.level == level and Current.actors["__flux_coast"]
    local alive = dom and dom:IsValid()
    local ok, dry = false, nil
    if alive then ok, dry = pcall(Effects.coastDry, dom) end
    if not ok or not dry then
        if try > 1 then Log(string.format("flux: coast reads right after %d capture(s) again", try - 1)) end
        if alive and not ok then Log("flux: coast check: " .. tostring(dry)) end
        done()
        return
    end
    local wait = Effects.COAST_RETRIES[try]
    if not wait then
        Log(string.format("flux: coast still reads as land after %d capture(s) again; "
            .. "`mjolnir_flux_recapture` takes it again by hand", try - 1))
        done()
        return
    end
    Log(string.format("flux: coast reads as land all over, its ground capture drew nothing; taking it again (%d)", try))
    local rebuilt, why = pcall(function() dom:RebuildAll() end)
    if not rebuilt then
        Log("flux: capture: " .. tostring(why))
        done()
        return
    end
    ExecuteInGameThreadWithDelay(wait, function() Effects.coastCheck(level, try + 1, done) end)
end

--- `mjolnir_flux_recapture`: a coast's ground capture again, by hand. Ground
--- that stands only for the capture has to stand for this one too: without
--- Death Island's the island left the coast map.
function Effects.fluxRecapture()
    local dom = Current.actors and Current.actors["__flux_coast"]
    if not (dom and dom:IsValid()) then return "no Flux coast on this level" end
    local shown = {}
    for _, item in ipairs(Current.level.decor or {}) do
        local a = type(item) == "table" and item.capture_only and Current.actors[item.id]
        if a and a:IsValid() then
            a:SetActorHiddenInGame(false)
            shown[#shown + 1] = a
        end
    end
    dom:RebuildAll()
    ExecuteInGameThreadWithDelay(3000, function()
        for _, a in ipairs(shown) do
            pcall(function() if a:IsValid() then a:SetActorHiddenInGame(true) end end)
        end
    end)
    return "ground captured again"
end

--- Fluid Flux's sea kept out of the tunnels and rooms (level.flux.dry,
--- upgrade_ce_map.flux_dry_zones). Its surface is one plane at sea level
--- everywhere, so it stood in a tunnel ramping under it, churning, and its
--- underwater fog volumes filled the rooms wholly under it (Yoyorast,
--- 2026-10-16). `cut` [{ rect = { x0, y0, x1, y1 } }]: Flux has one cut
--- rectangle (its surface materials' SurfaceCutMask: centre x, y, size x,
--- y in cm), moved to the zone nearest the camera within DRY_NEAR cm; from
--- outside, the land over a tunnel hides it. `fog` [{ x, y, floor, roof }]
--- by `cell` cm: inside one (or beside it), between its floor and roof,
--- the underwater volumes are hidden.
Effects.DRY_NEAR = 4000.0

function Effects.dryTick()
    local spec = Current.level and Current.level.flux
    local dry = type(spec) == "table" and type(spec.dry) == "table" and spec.dry
    local dom = dry and Current.actors["__flux_coast"]
    local surf = dom and dom:IsValid() and dom.SurfaceActorRenderer
    if not (surf and surf:IsValid()) then return end
    local st = Effects.dry
    -- By address, and the camera through getPlayerController: a name
    -- string and a GameplayStatics StaticFindObject every 100 ms read
    -- 12-13 ms a second (hitch log, 2026-10-17).
    if not st or st.surf ~= surf:GetAddress() then
        local cell = tonumber(dry.cell) or 100.0
        st = { surf = surf:GetAddress(), cell = cell, cells = {}, n = 0 }
        for _, c in ipairs(type(dry.fog) == "table" and dry.fog or {}) do
            st.cells[string.format("%d,%d", math.floor((c[1] + cell * 0.5) / cell),
                math.floor((c[2] + cell * 0.5) / cell))] = c
        end
        Effects.dry = st
    end
    local ok, cam = pcall(function()
        return getPlayerController().PlayerCameraManager:GetCameraLocation()
    end)
    if not ok or not cam then return end
    local o = (Current.level.canvas or {}).origin or { 0, 0, 0 }
    local x, y, z = cam.X - o[1], cam.Y - o[2], cam.Z - o[3]
    local best, near = nil, Effects.DRY_NEAR
    for i, zone in ipairs(type(dry.cut) == "table" and dry.cut or {}) do
        local r = zone.rect
        local dx, dy = math.max(r[1] - x, 0, x - r[3]), math.max(r[2] - y, 0, y - r[4])
        local d = math.sqrt(dx * dx + dy * dy)
        if d < near then best, near = i, d end
    end
    -- Again now and then: the surface's own ApplyMask can put its back.
    st.n = st.n + 1
    if best ~= st.cut or st.n % 30 == 0 then
        st.cut = best
        local r = best and dry.cut[best].rect
        local v = r and { R = o[1] + (r[1] + r[3]) / 2, G = o[2] + (r[2] + r[4]) / 2, B = r[3] - r[1], A = r[4] - r[2] }
            or { R = 0, G = 0, B = 0, A = 0 }
        pcall(function()
            local mis = surf.MaterialInstances
            for i = 1, #mis do mis[i]:SetVectorParameterValue(FName("SurfaceCutMask"), v) end
        end)
    end
    local inside = false
    local cx, cy = math.floor(x / st.cell), math.floor(y / st.cell)
    for dx = -1, 1 do
        for dy = -1, 1 do
            local c = st.cells[string.format("%d,%d", cx + dx, cy + dy)]
            if c and z > c[3] - 100 and z < c[4] + 50 then inside = true end
        end
    end
    if inside ~= st.inside then
        st.inside = inside
        pcall(function()
            surf.VolumeScattering:SetVisibility(not inside, false)
            surf.VolumeAbsorbtion:SetVisibility(not inside, false)
        end)
    end
end

--- A river's settled water, baked (level.flux.state: `mjolnir_flux_bake`'s
--- height/velocity EXRs beside the level file, and the domain they fit), as
--- the domain's InitialState: its ResetRenderTargets at BeginPlay draws it in
--- (LoadInitialState) instead of starting dry, as the game's own
--- PDA_M06_343_FluxState does. Set before the deferred spawn finishes. A
--- state baked for another domain (centre, resolution or cell) is left out.
--- Returns whether the state went in.
function Effects.fluxState(w, dom, spec, centre)
    local bs, d = spec.state, spec.domain
    if type(bs) ~= "table" or type(bs.height) ~= "string" or type(bs.velocity) ~= "string" then return false end
    local fits = type(bs.centre) == "table" and type(bs.res) == "table"
        and math.abs(bs.centre[1] - d.centre[1]) < 1 and math.abs(bs.centre[2] - d.centre[2]) < 1
        and math.abs(bs.centre[3] - d.centre[3]) < 1 and bs.res[1] == d.res[1] and bs.res[2] == d.res[2]
        and bs.cell == d.cell and bs.height_cm == d.height
    if not fits then Log("flux: the baked state is for another domain; filling instead") return false end
    local K = findObject("/Script/Engine.Default__KismetRenderingLibrary")
    local cls = findObject("/Game/FluidFlux/Simulation/Blueprints/PDA_FluxSimulationState.PDA_FluxSimulationState_C")
    local dir = (Current.level._dir or MOD_DIR) .. "\\"
    local hw = K:ImportFileAsTexture2D(w, dir .. bs.height)
    local vd = K:ImportFileAsTexture2D(w, dir .. bs.velocity)
    if not (cls and hw and hw:IsValid() and vd and vd:IsValid()) then
        Log("flux: baked state files missing; filling instead") return false
    end
    hw.SRGB = false
    vd.SRGB = false
    -- Outer the domain: its InitialState property keeps the state (and the
    -- state its textures) alive.
    local st = StaticConstructObject(cls, dom)
    st.HeightWetMap = hw
    st.VelocityDepthFoamMap = vd
    -- The raw simulation targets, as the domain's own CurrentState holds
    -- them: no encoding.
    st.EncodeHeightMax = 1.0
    st.EncodeVelocityMax = 1.0
    st.Compression = false
    st.AreaLocation = centre
    st.AreaSize = { X = d.res[1] * d.cell, Y = d.res[2] * d.cell, Z = d.height }
    st.Resolution = { X = d.res[1], Y = d.res[2] }
    st.CaptureOffset = tonumber(bs.capture) or 0
    dom.InitialState = st
    return true
end

--- `mjolnir_flux_bake`: the river as it is now (let it settle first) into
--- flux_state\ beside the level file: its height/wet and velocity/depth/foam
--- targets as EXR (the RG16f height copied into RGBA16f first, which the
--- engine writes as EXR rather than a clamped PNG), and state.json with the
--- domain it fits. tools/level/upgrade_ce_map.py ships them.
function Effects.fluxBake()
    local dom = Current.actors["__flux_domain"]
    local spec = Current.level and Current.level.flux
    if not (dom and dom:IsValid() and type(spec) == "table" and type(spec.domain) == "table") then
        return "no Flux river on this level"
    end
    local st, w = dom.CurrentState, getWorld()
    local K = findObject("/Script/Engine.Default__KismetRenderingLibrary")
    local d = spec.domain
    local dir = (Current.level._dir or MOD_DIR) .. "\\flux_state"
    local rt = K:CreateRenderTarget2D(w, d.res[1], d.res[2], 6, { R = 0, G = 0, B = 0, A = 0 }, false, false)
    local outs, size, ctx = {}, {}, {}
    K:BeginDrawCanvasToRenderTarget(w, rt, outs, size, ctx)
    outs.Canvas:K2_DrawTexture(st.HeightWetMap, { X = 0, Y = 0 }, { X = d.res[1], Y = d.res[2] }, { X = 0, Y = 0 },
        { X = 1, Y = 1 }, { R = 1, G = 1, B = 1, A = 1 }, 0, 0, { X = 0, Y = 0 })
    K:EndDrawCanvasToRenderTarget(w, ctx)
    K:ExportRenderTarget(w, rt, dir, "height.exr")
    K:ExportRenderTarget(w, st.VelocityDepthFoamMap, dir, "velocity.exr")
    local f = io.open(dir .. "\\state.json", "w")
    if not f then return "could not write " .. dir end
    f:write(string.format('{"height": "flux_state/height.exr", "velocity": "flux_state/velocity.exr", '
        .. '"centre": [%s, %s, %s], "res": [%d, %d], "cell": %s, "height_cm": %s, "capture": %s}\n',
        d.centre[1], d.centre[2], d.centre[3], d.res[1], d.res[2], d.cell, d.height, st.CaptureOffset))
    f:close()
    return "baked into " .. dir
end

--- Hide CE's water (level.flux.hide), once the Flux water has taken over.
function Effects.hideCE(spec)
    for _, key in ipairs(type(spec.hide) == "table" and spec.hide or {}) do
        local a = Current.actors[key]
        if a and a:IsValid() then pcall(function() a:SetActorHiddenInGame(true) end) end
    end
end

function Effects.flux(world)
    local spec = Current.level and Current.level.flux
    if type(spec) ~= "table" or (type(spec.domain) ~= "table" and type(spec.coast) ~= "table") then return end
    for _, key in ipairs({ "__flux_domain", "__flux_coast" }) do
        if Current.actors[key] and Current.actors[key]:IsValid() then return end
    end
    if Current.fluxPending then return end
    Current.fluxPending = true
    local name, level = Current.worldName, Current.level
    -- A coast goes in a third of a second after the decor, so its sea is up
    -- by the time the screen fades in: 4 s after, CE's water showed for ~3 s
    -- and then the sea changed in front of the player (Death Island,
    -- 2026-10-18). Its capture came out the same. A river keeps 4 s: that
    -- wait is what its capture of the ground was proved with (Timberland).
    local delay = tonumber(spec.delay_ms) or (type(spec.domain) == "table" and 4000 or 300)
    ExecuteInGameThreadWithDelay(delay, function()
        local w = getWorld()
        if not w or Current.worldName ~= name or Current.level ~= level then return end
        Current.fluxPending = false
        Current.fluxHideLater = false
        local ok, err = pcall(function()
            local ksl = findObject("/Script/Engine.Default__KismetSystemLibrary")
            local gs = findObject("/Script/Engine.Default__GameplayStatics")
            local function cls(path)
                local c = ksl:LoadClassAsset_Blocking(ksl:Conv_SoftClassPathToSoftClassRef(ksl:MakeSoftClassPath(path)))
                if not (c and c:IsValid()) then error("class not found: " .. path) end
                return c
            end
            local origin = (Current.level.canvas or {}).origin or { 0, 0, 0 }
            local tag, keep = FName("FluxHide"), {}
            for _, key in ipairs(type(spec.ground) == "table" and spec.ground or {}) do keep[key] = true end
            local tagged = 0
            for key, a in pairs(Current.actors) do
                if not keep[key] then
                    pcall(function()
                        local t = a.Tags
                        t[#t + 1] = tag
                        tagged = tagged + 1
                    end)
                end
            end
            -- The capture does not see the Landscape, and CE's ground under it
            -- is cut away: the river's flat 200 m was a hole the water fell
            -- through. CE's ground whole for the one capture (its cut rect,
            -- LandRect, moved off the map: both cut masters draw everything
            -- outside it), cut again after it (Timberland, 2026-10-14).
            -- Every ground slot with a cut rect (Death Island's cut slots are
            -- picked by base map, so the level file names none).
            local uncut = {}
            -- Not for a seabed coast alone: its landscape is the floor, and
            -- CE's flat one, made whole, would lie over it.
            local seabed = type(spec.coast) == "table" and spec.coast.seabed
            for key in pairs((type(spec.domain) == "table" or not seabed) and keep or {}) do
                local a = Current.actors[key]
                pcall(function()
                    local comp = a.StaticMeshComponent
                    local n = comp:GetNumMaterials()
                    pcall(function() n = math.max(n, comp.OverrideMaterials:GetArrayNum()) end)
                    for slot = 0, n - 1 do
                        pcall(function()
                            local m = comp:GetMaterial(slot)
                            local r = m:K2_GetVectorParameterValue(FName("LandRect"))
                            if r.B > 1.0 and r.B < 1.0e7 then
                                m:SetVectorParameterValue(FName("LandRect"), { R = 1.0e8, G = 1.0e8, B = 1.0, A = 1.0 })
                                uncut[#uncut + 1] = { m, { R = r.R, G = r.G, B = r.B, A = r.A } }
                            end
                        end)
                    end
                end)
            end
            -- The coast's `floor` (CE's sea floor slots) out of the capture as
            -- well: a metre under the water everywhere, it made the whole
            -- domain surf (upgrade_ce_map.flux_coast).
            local floored = {}
            local hidden = resolveMesh(TRIAL_MASTERS .. "M_CE_Hidden.M_CE_Hidden")
            local floor = not seabed and type(spec.coast) == "table" and type(spec.coast.floor) == "table"
                and spec.coast.floor or {}
            for key, slots in pairs(hidden and floor or {}) do
                local a = Current.actors[key]
                for _, slot in ipairs(a and a:IsValid() and slots or {}) do
                    pcall(function()
                        local comp = a.StaticMeshComponent
                        floored[#floored + 1] = { comp, slot, comp:GetMaterial(slot) }
                        comp:SetMaterial(slot, hidden)
                    end)
                end
            end
            local made = {}
            if type(spec.domain) == "table" then
                local d = spec.domain
                local c = { X = origin[1] + d.centre[1], Y = origin[2] + d.centre[2], Z = origin[3] + d.centre[3] }
                local surf = w:SpawnActor(cls(spec.surface or Effects.FLUX_SURFACE), c, { Pitch = 0, Yaw = 0, Roll = 0 })
                Current.actors["__flux_surface"] = surf
                local xf = { Rotation = { X = 0, Y = 0, Z = 0, W = 1 }, Translation = c, Scale3D = { X = 1, Y = 1, Z = 1 } }
                local dom = gs:BeginDeferredActorSpawnFromClass(w, cls(Effects.FLUX_DOMAIN), xf, 1, nil, 0)
                dom.AreaResolution = { X = d.res[1], Y = d.res[2] }
                dom.AreaWorldPixelSize = d.cell
                dom.AreaWorldHeight = d.height
                dom.SurfaceActorReference = surf
                -- One capture: the default re-captures every 0.4 s.
                dom.HeightmapUpdateFrequency = 1000000.0
                local sv = dom.SceneVisibility
                sv.ActorsWithTags_47_FB1C9D8B486CC31A912C34BC8E3BB996 = tag
                sv.UseInstancedMeshes_64_5640381C4A7506AD66F872A101E54AB7 = false
                sv.UseFoliageMeshes_63_108019E4475E89156CB35DA9D2A91E33 = false
                dom.SceneVisibility = sv
                -- Its baked water, if any: then it starts full and needs
                -- no priming.
                local baked = Effects.fluxState(w, dom, spec, c)
                gs:FinishSpawningActor(dom, xf, 0)
                Current.actors["__flux_domain"] = dom
                local src, comps, primed = cls(Effects.FLUX_SOURCE), {}, {}
                for i, s in ipairs(type(spec.sources) == "table" and spec.sources or {}) do
                  if not (baked and s.prime) then
                    local p, sc = s.pos, tonumber(s.scale) or 1.0
                    local t = { Rotation = { X = 0, Y = 0, Z = 0, W = 1 },
                        Translation = { X = origin[1] + p[1], Y = origin[2] + p[2], Z = origin[3] + p[3] },
                        Scale3D = { X = sc, Y = sc, Z = sc } }
                    local a = gs:BeginDeferredActorSpawnFromClass(w, src, t, 1, nil, 0)
                    gs:FinishSpawningActor(a, t, 0)
                    local m = a.FluxModifierSource
                    m.Duration = -1.0
                    m.Volume = tonumber(s.volume) or 1.0
                    m.Mode = tonumber(s.mode) or 2
                    if type(s.velocity) == "table" then m.Velocity = { X = s.velocity[1], Y = s.velocity[2] } end
                    Current.actors["__flux_source_" .. i] = a
                    comps[#comps + 1] = m
                    if s.prime then primed[#primed + 1] = "__flux_source_" .. i end
                  end
                end
                -- A primed river fills over prime_ms: its bed showed dry for
                -- that minute with CE's water already hidden (Battle Creek,
                -- 2026-10-19). CE's stays until the river is full.
                Current.fluxHideLater = #primed > 0
                -- `prime` sources fill the river at the start, then go: held,
                -- a Set source takes away the water that runs in, and the river
                -- stood still (Timberland, 2026-10-14).
                ExecuteInGameThreadWithDelay(tonumber(spec.prime_ms) or 60000, function()
                    if Current.worldName ~= name or Current.level ~= level then return end
                    local gone = 0
                    for _, key in ipairs(primed) do
                        local a = Current.actors[key]
                        if a and a:IsValid() then pcall(function() a:K2_DestroyActor() end) gone = gone + 1 end
                        Current.actors[key] = nil
                    end
                    pcall(function()
                        if dom:IsValid() then
                            dom:FindWorldModifiers(true)
                            for k, a in pairs(Current.actors) do
                                if k:find("^__flux_source_") and a:IsValid() then a.FluxModifierSource:UpdateMaterial() end
                            end
                        end
                    end)
                    Log(string.format("flux: river filled, %d priming source(s) removed", gone))
                    Effects.hideCE(spec)
                end)
                dom:FindWorldModifiers(true)
                -- Volume, mode and velocity reach the simulation through the
                -- source's material, which only UpdateMaterial writes.
                for _, m in ipairs(comps) do m:UpdateMaterial() end
                pcall(function() dom:CaptureGroundHeightmap(true) end)
                if type(spec.color_preset) == "string" or type(spec.surface_vectors) == "table" then
                    -- InitializeStates applies the preset again when the domain
                    -- binds its state. Apply our vectors after that startup; the
                    -- surface's later 2 s callback only initializes overlaps.
                    ExecuteInGameThreadWithDelay(math.max(1500, ((tonumber(dom.RuntimeCaptureDelay) or 0) + 0.5) * 1000), function()
                        if Current.worldName ~= name or Current.level ~= level then return end
                        local applied, why = pcall(function()
                            if surf:IsValid() then Effects.fluxColor(surf, spec) end
                        end)
                        if not applied then Log("flux: colour: " .. tostring(why)) end
                    end)
                end
                made[#made + 1] = string.format("river %dx%d at %g cm, %d source(s)", d.res[1], d.res[2], d.cell, #comps)
            end
            if type(spec.coast) == "table" then
                made[#made + 1] = Effects.fluxCoast(w, spec.coast, origin, cls, gs, tag)
            end
            -- The coastline captures half a second after it spawns.
            local only = {}
            for _, item in ipairs(Current.level.decor or {}) do
                local a = type(item) == "table" and item.capture_only and Current.actors[item.id]
                if a then only[#only + 1] = a end
            end
            ExecuteInGameThreadWithDelay(3000, function()
                -- Checked before the ground goes back: a capture taken again
                -- has to see what this one was meant to.
                Effects.coastCheck(level, 1, function()
                    for _, a in ipairs(only) do
                        pcall(function() if a:IsValid() then a:SetActorHiddenInGame(true) end end)
                    end
                    for _, u in ipairs(uncut) do
                        pcall(function() u[1]:SetVectorParameterValue(FName("LandRect"), u[2]) end)
                    end
                    for _, f in ipairs(floored) do
                        pcall(function() f[1]:SetMaterial(f[2], f[3]) end)
                    end
                end)
            end)
            Log(string.format("flux: %s; %d actor(s) out of the ground capture, %d ground slot(s) whole for it, "
                .. "%d sea floor slot(s) out of it", table.concat(made, ", "), tagged, #uncut, #floored))
        end)
        -- CE's water (`hide`) goes once Flux's is up, not before: until then
        -- the level has its old water rather than none. It is out of the
        -- ground capture already (FluxHide, with every actor not `ground`).
        if ok and not Current.fluxHideLater then Effects.hideCE(spec) end
        if not ok then Log("flux: " .. tostring(err)) end
    end)
end

--- CE's placed lights (level.lights, tools/level/upgrade_ce_map.py
--- ce_lights: a base's wall sconces and floor lamps), as shadowed point
--- lights: `pos` (cm, from the canvas origin), `colour`, `intensity` (cd
--- before the light scale, lightScale; unitless with `falloff`), `falloff`
--- (optional: Unreal's non-physical falloff exponent), `radius` (cm),
--- `source_radius` (optional: emitter radius in cm, default 8),
--- `specular_scale` (optional: specular contribution, clamped to 0..1),
--- `shadow_distance` (optional: cm from the camera they shadow to, default
--- 8000). The terrain shades
--- them through TerrainLights; `mjolnir_terrain_lights off` leaves CE's
--- surfaces out of their reach.
local Placed = {}

function Placed.lights(world)
    local lights = Current.level and Current.level.lights
    if type(lights) ~= "table" or #lights == 0 then return end
    local cls = findObject("/Script/Engine.PointLight")
    if not cls then return end
    local origin = (Current.level.canvas or {}).origin or { 0, 0, 0 }
    local k = lightScale()
    local n = 0
    for i, l in ipairs(lights) do
        local key = "__light_" .. i
        local p = type(l) == "table" and l.pos
        if type(p) == "table" and not (Current.actors[key] and Current.actors[key]:IsValid()) then
            local ok, actor = pcall(function()
                return world:SpawnActor(cls, { X = origin[1] + p[1], Y = origin[2] + p[2], Z = origin[3] + p[3] },
                    { Pitch = 0, Yaw = 0, Roll = 0 })
            end)
            if ok and actor and actor:IsValid() then
                pcall(function()
                    local c = actor.LightComponent
                    local colour = type(l.colour) == "table" and l.colour or { 1, 1, 1 }
                    c.Mobility = MOBILITY_MOVABLE
                    if tonumber(l.falloff) then
                        -- Unreal's non-physical falloff (unitless): no
                        -- burned-white surfaces beside the lamp.
                        c.bUseInverseSquaredFalloff = false
                        c.LightFalloffExponent = tonumber(l.falloff)
                        c.IntensityUnits = 0
                    else
                        c.IntensityUnits = 1 -- candelas
                    end
                    c:SetIntensity((tonumber(l.intensity) or 25) * k)
                    c:SetAttenuationRadius(tonumber(l.radius) or 2000)
                    c:SetLightColor({ R = colour[1], G = colour[2], B = colour[3], A = 1 }, true)
                    -- The game's lights stop shadowing 25 m from the camera
                    -- (MaxShadowDistance, r.Lighting.DefaultMaxShadowDistance
                    -- 2500, fading over the last 5 m): a room seen through a
                    -- doorway from further off lost its shadows, and they
                    -- faded in as you walked up, and a floor lamp's half-faded
                    -- shadow let its light onto the floor outside its
                    -- building (Death Island, 2026-10-15).
                    -- Set before SetCastShadows, whose render state rebuild
                    -- at the end of the frame takes it in.
                    c.MaxShadowDistance = tonumber(l.shadow_distance) or 8000
                    c.ShadowFadeRange = 1000
                    c:SetCastShadows(true)
                    c:SetSourceRadius(math.max(0, tonumber(l.source_radius) or 8))
                    local specular = tonumber(l.specular_scale)
                    if specular then c:SetSpecularScale(math.max(0, math.min(1, specular))) end
                end)
                Current.actors[key] = actor
                n = n + 1
            end
        end
    end
    Log(string.format("lights: %d of CE's placed lights", n))
end

--- The game's own decals (level.decals, tools/level/upgrade_ce_map.py
--- grime_decals: Megascans soil splashed up a base's walls where they meet
--- the ground, leaks run down from their tops): `material` (a shipped
--- decal material instance), `pos` (cm, from the canvas origin), `rot`
--- [pitch, yaw, roll] (the decal projects along its x), `size` (half
--- extents, cm), `scalars` (optional, the material's parameters). Only the game's decal materials: ours fail its pipeline
--- state creation, a fatal error (PipelineStateCache.cpp:551).
function Placed.decals(world)
    local decals = Current.level and Current.level.decals
    if type(decals) ~= "table" or #decals == 0 then return end
    local cls = findObject("/Script/Engine.DecalActor")
    if not cls then return end
    local origin = (Current.level.canvas or {}).origin or { 0, 0, 0 }
    local n, failed = 0, 0
    for i, d in ipairs(decals) do
        local key = "__decal_" .. i
        local p = type(d) == "table" and d.pos
        local material = type(d) == "table" and type(d.material) == "string" and resolveMesh(d.material)
        if type(p) == "table" and material and not (Current.actors[key] and Current.actors[key]:IsValid()) then
            local r = type(d.rot) == "table" and d.rot or {}
            local ok, actor = pcall(function()
                return world:SpawnActor(cls, { X = origin[1] + p[1], Y = origin[2] + p[2], Z = origin[3] + p[3] },
                    { Pitch = r[1] or 0, Yaw = r[2] or 0, Roll = r[3] or 0 })
            end)
            if ok and actor and actor:IsValid() then
                local size = type(d.size) == "table" and d.size or { 30, 100, 100 }
                pcall(function()
                    -- `scalars`: the material's own parameters (scalarMid), e.g.
                    -- a Megascans decal's "Opacity Intensity".
                    actor.Decal:SetDecalMaterial(type(d.scalars) == "table" and scalarMid(world, material, d.scalars)
                        or material)
                    actor.Decal.DecalSize = { X = size[1], Y = size[2], Z = size[3] }
                    -- Gone by the time it covers a few pixels.
                    actor.Decal:SetFadeScreenSize(0.004)
                end)
                Current.actors[key] = actor
                n = n + 1
            else
                failed = failed + 1
            end
        elseif not material then
            failed = failed + 1
        end
    end
    Log(string.format("decals: %d placed, %d failed", n, failed))
end

--- The game's foliage quality (Settings > Video, sg.FoliageQuality 0..3):
--- below Epic the grass groups keep one clump in `keep` and every group
--- culls at `cull` of its distance, so a lower setting pays less for B30's
--- grass (Blood Gulch's valley: ~2 ms of a 14 ms frame at Epic, 4K).
--- `still`: no wind at Low and Medium. Swaying grass was half of Death
--- Island's grass cost on the GPU (1.2 of 2.5 ms, RTX 5090, 2026-10-17);
--- WorldPositionOffsetDisableDistance does nothing in this build, so the
--- sway is all or none.
Foliage.QUALITY = { [0] = { keep = 4, cull = 0.45, still = true }, [1] = { keep = 3, cull = 0.6, still = true },
    [2] = { keep = 2, cull = 0.8 }, [3] = { keep = 1, cull = 1.0 } }
Foliage.GRASSY = { grass = true, ["short grass"] = true, ["lip grass"] = true, weeds = true, tufts = true }

function Foliage.quality()
    local ok, q = pcall(function()
        return findObject("/Script/Engine.Default__KismetSystemLibrary"):GetConsoleVariableIntValue("sg.FoliageQuality")
    end)
    q = ok and tonumber(q) or 3
    return Foliage.QUALITY[math.max(0, math.min(3, q))] or Foliage.QUALITY[3]
end

--- A group's material on one of its meshes (a spawned band or a baked
--- one): `material`, `tint`/`tint_param`/`params`/`scalars` as tinted
--- instances, one a slot shared by the group's meshes (`mids`, returned).
function Foliage.dress(world, kml, g, group, comp, mids)
    local material = type(group.material) == "string" and resolveMesh(group.material)
    if material then comp:SetMaterial(0, material) end
    if type(group.tint) == "table" and kml then
        -- One tinted instance a slot, shared by the bands.
        if not mids then
            mids = {}
            for i = 0, comp:GetNumMaterials() - 1 do
                local mid = kml:CreateDynamicMaterialInstance(world, comp:GetMaterial(i), FName(string.format("foliage_%d_%d", g, i)), 0)
                -- `tint_param`: B30's own foliage master (MM_Foliage_MET)
                -- tints through "Color Tint", the Megascans one through
                -- "Color Overlay".
                local param = type(group.tint_param) == "string" and group.tint_param or "Color Overlay"
                mid:SetVectorParameterValue(FName(param),
                    { R = group.tint[1], G = group.tint[2], B = group.tint[3], A = 1 })
                -- `params`: more vector parameters by name, e.g. a
                -- B30 grass's "Subsurface Color Tint" with its tint.
                if type(group.params) == "table" then
                    for name, v in pairs(group.params) do
                        if type(v) == "table" then
                            mid:SetVectorParameterValue(FName(name), { R = v[1], G = v[2], B = v[3], A = v[4] or 1 })
                        end
                    end
                end
                for name, v in pairs(type(group.scalars) == "table" and group.scalars or {}) do
                    if type(v) == "number" then mid:SetScalarParameterValue(FName(name), v) end
                end
                mids[i] = mid
            end
        end
        for i, mid in pairs(mids) do comp:SetMaterial(i, mid) end
    elseif type(group.scalars) == "table" then
        -- `scalars`: values on the mesh's own materials (scalarMid),
        -- e.g. a swapped tree's leaf clusters.
        for i = 0, comp:GetNumMaterials() - 1 do
            local mid = scalarMid(world, comp:GetMaterial(i), group.scalars)
            if mid then comp:SetMaterial(i, mid) end
        end
    end
    return mids
end

--- A level whose foliage is `baked` (tools/level/foliage_bake.py,
--- upgrade_ce_map.py `bake_foliage`) carries its groups in the world as
--- hierarchical instanced meshes named MJFol_<group>_<band>_<tier>: this
--- gives them what Foliage.spawn gives its own, the group's materials and
--- tints, its cull distances scaled and its wind stilled by the quality,
--- and hides the grassy groups' tiers above the quality (tier 0 at Low, 0-1
--- Medium, 0-2 High: the loader's keep 4, 3, 2). `quality` nil hides them
--- all (`mjolnir_foliage off`). Cull and wind are worked out afresh from
--- the level file each time (the components keep the last load's), as
--- Foliage.spawn and BakeFoliage work them out. One FindAllOf, no handles
--- kept. Returns the baked meshes found, then the meshes and clumps drawn.
--- The meshes are found and counted here; during a load they are dressed
--- a slice a frame (Current.dressQueue, the step after the foliage's):
--- hundreds of them, a few calls each.
Foliage.TIERS = { [4] = 0, [3] = 1, [2] = 2, [1] = 3 }
function Foliage.dressBaked(world, foliage, quality)
    local kml = findObject("/Script/Engine.Default__KismetMaterialLibrary")
    local top = quality and (Foliage.TIERS[quality.keep] or 3) or -1
    local mids, found, comps, drawn, work = {}, 0, 0, 0, {}
    for _, comp in ipairs(FindAllOf("HierarchicalInstancedStaticMeshComponent") or {}) do
        local g, b, tier = comp:GetFName():ToString():match("^MJFol_(%d+)_(%d+)_(%d+)$")
        g, b, tier = tonumber(g), tonumber(b), tonumber(tier)
        local group = g and foliage.groups[g]
        if type(group) == "table" then
            found = found + 1
            local shown = tier <= top
            if shown then comps, drawn = comps + 1, drawn + comp:GetInstanceCount() end
            work[#work + 1] = { comp = comp, g = g, b = b, group = group, shown = shown }
        end
    end
    -- Back to the mesh's own materials first: a reload dressed the last
    -- load's tinted instances again, and the grass drew dark grey
    -- (2026-10-18). Only after a dressing in this world: BakeFoliage sets
    -- no materials, so a mesh fresh from the world has its own.
    local reset = Current.foliageDressed
    local function dressMesh(w)
        local comp, group = w.comp, w.group
        -- Found frames ago during a load (the queue).
        if not comp:IsValid() then return end
        comp:SetVisibility(w.shown, false)
        if not w.shown then return end
        if reset then
            pcall(function()
                local mesh = comp.StaticMesh
                for i = 0, comp:GetNumMaterials() - 1 do comp:SetMaterial(i, mesh:GetMaterial(i)) end
            end)
        end
        mids[w.g] = Foliage.dress(world, kml, w.g, group, comp, mids[w.g])
        local gc = type(group.cull) == "table" and group.cull
            or type(foliage.cull) == "table" and foliage.cull or Foliage.CULL
        gc = { gc[1] * quality.cull, gc[2] * quality.cull }
        local bands = math.max(1, math.floor(tonumber(group.bands) or 1))
        local far = bands > 1 and gc[1] + (gc[2] - gc[1]) * w.b / bands or gc[2]
        comp:SetCullDistances(math.floor(math.min(gc[1], far)), math.floor(far))
        local sway = not (group.static or quality.still)
        pcall(function() comp:SetEvaluateWorldPositionOffset(sway) end)
    end
    if Current.dressQueue then
        Current.dressQueue.add(work, dressMesh)
    else
        for _, w in ipairs(work) do dressMesh(w) end
    end
    if comps > 0 then Current.foliageDressed = true end
    return found, comps, drawn
end

--- The world's mesh actors the loader dresses, by name, from one walk:
--- the swapped scenery (MJDecor_<id>, by id) and the cladding rocks
--- (MJClad_<group>_<rock>, by group). spawnDecor and Foliage.bakedRocks
--- each made a FindAllOf("StaticMeshActor") of their own, ~20 ms and a
--- name read for each of thousands of actors. Kept on Current.meshScan for
--- the load that made it, then dropped: no handle outlives the load.
function Foliage.scanMeshActors()
    local scan = Foliage.newScan()
    for _, a in ipairs(FindAllOf("StaticMeshActor") or {}) do Foliage.classify(scan, a) end
    return scan
end

function Foliage.newScan() return { decor = {}, rocks = {}, nRocks = 0 } end

--- One mesh actor into a scan, by its name. A load reads the names a
--- slice a frame: thousands of actors (Timberland's 4,242 pieces and 2,070
--- rocks), a name read each.
function Foliage.classify(scan, a)
    if not a:IsValid() then return end
    local name = a:GetFName():ToString()
    local id = name:match("^MJDecor_(.+)$")
    if id then
        scan.decor[id] = a
        return
    end
    local g = tonumber(name:match("^MJClad_(%d+)_%d+$"))
    if g then
        local list = scan.rocks[g] or {}
        list[#list + 1] = a
        scan.rocks[g], scan.nRocks = list, scan.nRocks + 1
    end
end

--- The cladding rocks a baked world carries (MJClad_<group>_<rock>, mesh
--- actors: BakeFoliage's flag 8), by group: the load's scan when it made
--- one, else a scan of its own. `shown` false hides them (`mjolnir_foliage
--- off`), true shows them again; rocks fresh from the world are shown
--- already, so only after a hiding in this world. The lists go to
--- Foliage.cliffGroups for Land.cliffs, which drops them once the rocks
--- have their material: the loader keeps no handle a rock.
function Foliage.bakedRocks(shown)
    local scan = Current.meshScan or Foliage.scanMeshActors()
    local set = shown == false or (shown == true and Current.rocksHidden)
    if set then
        for _, list in pairs(scan.rocks) do
            for _, actor in ipairs(list) do actor:SetActorHiddenInGame(not shown) end
        end
        Current.rocksHidden = shown == false
    end
    return scan.rocks, scan.nRocks
end

function Foliage.spawn(world)
    local foliage = Current.level and Current.level.foliage
    if type(foliage) ~= "table" or type(foliage.file) ~= "string" or type(foliage.groups) ~= "table" then
        return
    end
    -- Only a landscape world (upgrade_ce_map.py) can carry baked foliage.
    local landWorld = type(Current.level.landscape) == "table"
    if not Foliage.on then
        if landWorld then
            Foliage.dressBaked(world, foliage, nil)
            Foliage.bakedRocks(false)
        end
        return
    end
    Current.lap("before foliage")
    -- The header first (magic, version, group count). The clumps follow,
    -- read only when a group needs them (one the world does not carry):
    -- a baked world needs none, and Timberland's file is 15 MB.
    local file = io.open((Current.level._dir or MOD_DIR) .. "\\" .. foliage.file, "rb")
    local raw = file and file:read(12)
    local magic = raw and #raw == 12 and raw:sub(1, 4)
    if magic ~= Foliage.MAGIC and magic ~= Foliage.MAGIC2 and magic ~= Foliage.MAGIC3 then
        if file then file:close() end
        Log("foliage: " .. foliage.file .. " missing or not a foliage file")
        return
    end
    local cls = findObject("/Script/Engine.StaticMeshActor")
    local hism = findObject("/Script/Engine.HierarchicalInstancedStaticMeshComponent")
    local kml = findObject("/Script/Engine.Default__KismetMaterialLibrary")
    local cull = type(foliage.cull) == "table" and foliage.cull or Foliage.CULL
    local started = os.clock()
    local _, count, pos = string.unpack("<II", raw, 5)  -- luacheck: ignore 143 (Lua 5.4's string.unpack)
    local tilted = magic == Foliage.MAGIC2 or magic == Foliage.MAGIC3
    local coloured = magic == Foliage.MAGIC3
    Foliage.cliffGroups = {}
    local quality = Foliage.quality()
    local total, sx, sy, n = 0, 0, 0, 0
    -- Baked: what the world carries decides, not the level file's `baked`.
    -- The launcher puts the hub's level.json back on every launch and leaves
    -- installed containers alone, so a baked world under an older level file
    -- spawned every clump and rock a second time: trees with a swaying copy
    -- of their leaves, rocks flickering in each other (2026-10-18). A level
    -- file that says baked over a world without them spawns them as before.
    local baked, centre = nil, nil
    if landWorld then
        local found, comps, drawn = Foliage.dressBaked(world, foliage, quality)
        if found > 0 then
            baked = string.format(", %d baked clump(s) drawn in %d mesh(es)", drawn, comps)
            -- The wind's flowmap centres on the clumps: assemble's mean of
            -- them (it spans 4 km, so the origin serves a level without one).
            centre = drawn > 0 and (type(foliage.centre) == "table" and foliage.centre or { 0, 0 }) or nil
        elseif foliage.baked == true then
            Log("foliage: the level file says baked, but the world carries none; spawning it")
        end
    end
    Current.lap("foliage baked meshes")
    -- Baked cladding rocks likewise: spawned only for a group the world
    -- does not carry.
    local rocks, rocked = {}, 0
    if landWorld and coloured then rocks, rocked = Foliage.bakedRocks(true) end
    Current.lap("foliage baked rocks")
    -- The clumps: needed for a group spawned here, that is any group of an
    -- unbaked world, and a baked world's cladding the world lacks.
    local need = not baked
    for g = 1, count do
        local group = foliage.groups[g] or {}
        if group.cliff == true and coloured and not rocks[g] then need = true end
    end
    if need then raw = raw .. (file:read("a") or "") end
    file:close()
    Current.lap("foliage file")
    for g = 1, count do
        -- Without the clumps, only the two branches that skip a group's
        -- clumps are taken: its size is not needed.
        local size = 0
        if need then
            size, pos = string.unpack("<I", raw, pos)  -- luacheck: ignore 143 (Lua 5.4's string.unpack)
        end
        local group = foliage.groups[g] or {}
        if baked and not (group.cliff == true and coloured) then
            pos = pos + size * (coloured and 19 or tilted and 16 or 14)
            goto continue
        end
        if group.cliff == true and coloured and rocks[g] then
            pos = pos + size * 19
            Foliage.cliffGroups[#Foliage.cliffGroups + 1] = { actors = rocks[g], base = group.base,
                light = group.light, lm = group.lm, baked = true }
            goto continue
        end
        local mesh = type(group.mesh) == "string" and resolveMesh(group.mesh)
        if group.cliff == true and coloured then
            pos = Foliage.spawnCladding(world, g, group, mesh, raw, pos, size)
            total = total + size
            goto continue
        end
        local actor = mesh and cls and hism and world:SpawnActor(cls, { X = 0, Y = 0, Z = 0 }, { Pitch = 0, Yaw = 0, Roll = 0 })
        -- `bands` > 1: the group's clumps dealt in turn to that many meshes,
        -- culled at distances spread over its cull range. The game's foliage
        -- materials do not fade, so one cull distance is one hard ring where
        -- all the grass goes; bands thin it out over the range instead.
        local bands = math.max(1, math.floor(tonumber(group.bands) or 1))
        local gc = type(group.cull) == "table" and group.cull or cull
        gc = { gc[1] * quality.cull, gc[2] * quality.cull }
        local keep = Foliage.GRASSY[group.rule] and quality.keep or 1
        local comps, mids = {}, nil
        for b = 1, (actor and actor:IsValid()) and bands or 0 do
            local comp = actor:AddComponentByClass(hism, false, {
                Rotation = { X = 0, Y = 0, Z = 0, W = 1 }, Translation = { X = 0, Y = 0, Z = 0 },
                Scale3D = { X = 1, Y = 1, Z = 1 } }, false)
            if not (comp and comp:IsValid()) then break end
            comp.Mobility = MOBILITY_MOVABLE
            comp:SetStaticMesh(mesh)
            comp:SetCollisionEnabled(COLLISION_NONE)
            -- `static` (a group's): no wind, as decor's `static`; nor at a
            -- foliage quality that is `still`.
            if group.static or quality.still then pcall(function() comp:SetEvaluateWorldPositionOffset(false) end) end
            local far = bands > 1 and gc[1] + (gc[2] - gc[1]) * b / bands or gc[2]
            -- Whole centimetres: UE4SS passes a fractional number to an int32
            -- parameter as 0, and a 0 end distance never culls. A third of a
            -- band's range (7333.3) left 51,000 of Death Island's clumps
            -- drawn across the whole map (2026-10-17).
            comp:SetCullDistances(math.floor(math.min(gc[1], far)), math.floor(far))
            -- Rigid: the wind's vertex offset does not invalidate the virtual
            -- shadow map's cached pages. Swaying grass re-rendered its
            -- shadows every frame, ~1.5 ms of GPU on Yoyorast at 4K
            -- (2026-10-12); the shadows stay, they just do not sway.
            pcall(function() comp.ShadowCacheInvalidationBehavior = SHADOW_CACHE_RIGID end)
            comp:SetCastShadow(group.shadow ~= false)
            mids = Foliage.dress(world, kml, g, group, comp, mids)
            comps[#comps + 1] = comp
        end
        if #comps > 0 then
            Current.actors["__foliage_" .. g] = actor
            for k = 1, size do
                local x, y, z, yaw, scale
                local nx, ny = 0, 0
                if coloured then
                    x, y, z, yaw, scale, nx, ny, pos = string.unpack("<fffBBbbxxx", raw, pos)  -- luacheck: ignore 143 (Lua 5.4's string.unpack)
                elseif tilted then
                    x, y, z, yaw, scale, nx, ny, pos = string.unpack("<fffBBbb", raw, pos)  -- luacheck: ignore 143 (Lua 5.4's string.unpack)
                else
                    x, y, z, yaw, scale, pos = string.unpack("<fffBB", raw, pos)  -- luacheck: ignore 143 (Lua 5.4's string.unpack)
                end
                if k % keep == 0 then
                    local s = scale / 100
                    comps[(k // keep - 1) % #comps + 1]:AddInstance({ Rotation = Foliage.rotation(yaw * math.pi / 128, nx / 127, ny / 127),
                        Translation = { X = x, Y = y, Z = z }, Scale3D = { X = s, Y = s, Z = s } }, true)
                    sx, sy, n = sx + x, sy + y, n + 1
                end
            end
            total = total + size
        else
            pos = pos + size * (coloured and 19 or tilted and 16 or 14)
            Log("foliage: group " .. g .. " not spawned (" .. tostring(group.mesh) .. ")")
        end
        ::continue::
    end
    centre = centre or n > 0 and { sx / n, sy / n }
    local wind = centre and pcall(Foliage.wind, world, type(foliage.wind) == "table" and foliage.wind or {}, centre)
    Log(string.format("foliage: %d clump(s) in %d group(s), %d placed (quality: 1 in %d grass, cull x%.2f%s)%s%s, %.1f s%s",
        total, count, n, quality.keep, quality.cull, quality.still and ", still" or "", baked or "",
        rocked > 0 and string.format(", %d baked rock(s)", rocked) or "", os.clock() - started, wind and ", wind on" or ""))
end

--- A Landscape in the map's world (MJOLNIRMaterials build_ce_landscape.py)
--- draws the ground shader whose material level.landscape.material is: the
--- terrain mesh slot's own parameters, less the textures the landscape bakes
--- over world XY (tools/level/build_landscape.py leaves those out). They go
--- to the landscape's per-component instances.
local Land = {}

--- B30's ground (M_CE_LandscapePBR, level.landscape.pbr): the game's
--- Megascans sand, rippled sand and ground grass, the CE base bake that
--- says where grass grows (and its rectangle), and the sea's height for the
--- rippled and wet bands.
Land.MEGASCANS = "/Game/Megascans/Surfaces/"
Land.SURFACES = {
    SandD = "Thai_Beach_Sand_tefgafrk/T_Thai_Beach_Sand_tefgafrk_2K_NSVT_D",
    SandN = "Thai_Beach_Sand_tefgafrk/T_Thai_Beach_Sand_tefgafrk_2K_NSVT_N",
    SandO = "Thai_Beach_Sand_tefgafrk/T_ThaiBeachSand_tefgafrk_2K_NSVT_ORDp",
    RipD = "Thai_Rippled_Beach_Sand_vb1ldadn/T_Thai_Rippled_Beach_Sand_vb1ldadn_2K_NSVT_D",
    RipN = "Thai_Rippled_Beach_Sand_vb1ldadn/T_Thai_Rippled_Beach_Sand_vb1ldadn_2K_NSVT_N",
    RipO = "Thai_Rippled_Beach_Sand_vb1ldadn/T_ThaiRippledBeachSand_vb1ldadn_2K_NSVT_ORDp",
    GrassD = "Ground_Grass_tb3nce2k/T_Ground_Grass_tb3nce_Desat_4K_NSVT_D",
    GrassN = "Ground_Grass_tb3nce2k/T_Ground_Grass_NSVT_4K_N",
    GrassO = "Ground_Grass_tb3nce2k/T_Ground_Grass_NSVT_4K_OHRG",
    SandBD = "Beach_Sand_xdheagk/T_Beach_Sand_xdheagk_2K_NSVT_D",
    SandBN = "Beach_Sand_xdheagk/T_Beach_Sand_xdheagk_2K_NSVT_N",
    -- Earth inland (pbr.inland): packed earth, sandy gravel, gravel.
    DirtD = "Trampled_Forest_Path_ub4jdihkw/T_Trampled_Forest_Path_ub4jdihkw_NSVT_D",
    DirtN = "Trampled_Forest_Path_ub4jdihkw/T_Trampled_Forest_Path_ub4jdihkw_NSVT_N",
    DirtO = "Trampled_Forest_Path_ub4jdihkw/T_Trampled_Forest_Path_ub4jdihkw_NSVT_ORHG",
    MidD = "Sandy_Gravel_Ground_vmndcca/T_T_Sandy_Gravel_Ground_vmndcca_B_2K_NSVT_D_copy",
    MidN = "Sandy_Gravel_Ground_vmndcca/T_Sandy_Gravel_Ground_vmndcca_2K_NSVT_N",
    MidO = "Sandy_Gravel_Ground_vmndcca/T_T_Sandy_Gravel_Ground_vmndcca_B_2K_NSVT_ORHG",
    GravD = "Ground_Gravel_uconcitg/T_Ground_Gravel_uconcitg_sbs_NSVT_D",
    GravN = "Ground_Gravel_uconcitg/T_Ground_Gravel_uconcitg_sbs_NSVT_N",
    GravO = "Ground_Gravel_uconcitg/T_Ground_Gravel_uconcitg_sbs_NSVT_ORHG",
}

--- The sea's height (cm), from the level's water mesh, or nil. Nil too for
--- a level whose landscape says `sea = false`: its water is a pond, not a
--- sea (Coagulation's pool sits 7 m above the valley floor, which drew as a
--- beach under it).
function Land.seaHeight()
    if type(Current.level.landscape) == "table" and Current.level.landscape.sea == false then return nil end
    for _, item in ipairs(Current.level.decor or {}) do
        if type(item) == "table" and type(item.mesh) == "string" and item.mesh:find("_Water%.")
            and type(item.pos) == "table" then
            return item.pos[3] + ((Current.level.canvas or {}).origin or { 0, 0, 0 })[3]
        end
    end
    return nil
end

--- `set` takes the parameters: { tex = fn(name, texture), vec = fn(name,
--- {R,G,B,A}) }, for the landscape (Land.landSetter) or a mesh's instance.
function Land.pbr(set, pbr)
    local missing = 0
    -- `pbr.surfaces`: the level's own surfaces over Land.SURFACES, by
    -- parameter (Blood Gulch's paths are packed earth, not beach sand).
    local surfaces = {}
    for param, path in pairs(Land.SURFACES) do surfaces[param] = path end
    for param, path in pairs(type(pbr.surfaces) == "table" and pbr.surfaces or {}) do surfaces[param] = path end
    for param, path in pairs(surfaces) do
        local leaf = path:match("([^/]+)$")
        local tex = resolveMesh(Land.MEGASCANS .. path .. "." .. leaf)
        if tex then
            set.tex(param, tex)
        else
            missing = missing + 1
        end
    end
    local base = type(pbr.base) == "string" and resolveMesh(pbr.base)
    if base then set.tex("Base", base) end
    local r = type(pbr.rect) == "table" and pbr.rect
    if r then set.vec("LandRect", { R = r[1], G = r[2], B = r[3], A = r[4] }) end
    local function vec(param, v)
        if type(v) == "table" then
            set.vec(param, { R = v[1] or 0, G = v[2] or 0, B = v[3] or 0, A = v[4] or 0 })
        end
    end
    vec("GrassTint", pbr.grass_tint)
    vec("SandTint", pbr.sand_tint)
    vec("LandLook", pbr.look)
    -- Ice where CE's base map is painted dark (Ice Fields' frozen pond).
    vec("LandIce", pbr.ice)
    vec("LandIceColor", pbr.ice_color)
    -- Depth: sand and footprint depth (cm), fade distance (cm), ray steps.
    vec("LandParallax", pbr.parallax)
    -- Far sand: strength, where it takes over (cm from, to), scale.
    vec("LandMacro", pbr.macro)
    -- Banks as grass: normal z where it starts, all grass, strength.
    vec("GroundSlope", pbr.slope)
    -- Where the ground meets a wall (pbr.edge: the landscape's edge map):
    -- grass worn at a lip, earth tint there, shade at a foot.
    local edge = type(pbr.edge) == "table" and type(pbr.edge.texture) == "string" and resolveMesh(pbr.edge.texture)
    if edge then
        set.tex("LandEdge", edge)
        local l = type(pbr.edge_look) == "table" and pbr.edge_look or { 0.8, 0.5, 0.45 }
        set.vec("LandEdgeLook", { R = l[1] or 0, G = l[2] or 0, B = l[3] or 0, A = 1 })
    end
    -- CE's baked light, as occlusion: the lightmap bake and its levels.
    local lm = type(pbr.lightmap) == "string" and resolveMesh(pbr.lightmap)
    local levels = lightmapSun()
    if lm and levels then
        set.tex("LM", lm)
        set.vec("LandLMLevels", { R = levels[1], G = levels[2], B = 0, A = 0 })
    end
    vec("LandTiles", pbr.tiles)
    vec("LandMix", pbr.mix)
    -- Earth inland: from, to (cm over the sea), ragged (cm), strength; with
    -- no sea the strength is the earth's share everywhere. `dirt`: sandy
    -- gravel's share in the change, gravel's share, patch cell (cm), sandy
    -- patches inland; `dirt_tint` the earth's colour.
    vec("LandInland", pbr.inland)
    vec("LandDirt", pbr.dirt)
    vec("DirtTint", pbr.dirt_tint)
    vec("LandWet", pbr.wet)
    -- The sea, from the level's water (as GameWet): the rippled band and the
    -- wet edge sit over it.
    local sea = Land.seaHeight()
    local band = type(pbr.sea) == "table" and pbr.sea or {}
    set.vec("LandSea", { R = sea or 0, G = band[1] or 150, B = band[2] or 40, A = sea and 1 or 0 })
    return missing
end

function Land.landSetter(land)
    return {
        tex = function(n, t) land:SetLandscapeMaterialTextureParameterValue(FName(n), t) end,
        vec = function(n, v) land:SetLandscapeMaterialVectorParameterValue(FName(n), v) end,
    }
end

--- The cliffs under a B30 landscape (level.landscape.cliff) in the game's
--- own rock: M_CE_CliffPBR, triplanar and lit by Unreal (CE's cliff map is
--- a 1024 x 256 strip stretched over 20 m walls). A slot is a cliff by its
--- primary detail map (`details`, the bitmap names); each keeps its own base
--- map (the banding's colours) and lightmap page (shade). `rock_a` (the
--- grain) and `rock_b` (metres across) name Megascans surfaces as
--- { d, n, o } under Land.MEGASCANS; `tiles`, `mix`, `look`, `tint`, `rough`
--- are the master's CliffTiles, CliffMix, CliffLook, RockTint, CliffRough;
--- `fill` [r, g, b, strength] the bounce light off the sand (strength in the
--- level's light units); `soil` the earth under the turf (as a rock), `drape`
--- and `foot` CliffDrape and CliffFoot, `sand` CliffSand, which blend a wall
--- into the ground at its lip and foot by the landscape's edge map
--- (level.landscape.pbr.edge). Returns the slots changed.
Land.ROCK_A = {
    d = "Rock_Jagged_udemcebew/T_Rock_Jagged_udemcebew_NSVT_D",
    n = "Rock_Jagged_udemcebew/T_Rock_Jagged_udemcebew_NSVT_N",
    o = "Rock_Jagged_udemcebew/T_Rock_Jagged_udemcebew_NSVT_ORHG",
}
Land.SOIL = {
    d = "Soil_Damp_sbykj0p0/T_Damp_Soil_Cliff_sbykj0p0_2K_D",
    n = "Soil_Damp_sbykj0p0/T_Damp_Soil_Cliff_sbykj0p0_2K_N",
    o = "Soil_Damp_sbykj0p0/T_Damp_Soil_Cliff_sbykj0p0_2K_ORHG",
}
Land.ROCK_B = {
    d = "Rock_Jagged_udemcebew/T_Rock_Jagged_udemcebew_NSVT_D",
    n = "Rock_Jagged_udemcebew/T_Rock_Jagged_udemcebew_NSVT_N",
    o = "Rock_Jagged_udemcebew/T_Rock_Jagged_udemcebew_NSVT_ORHG",
}

--- Structure walls in a PBR surface (level.landscape.structures, from
--- upgrade_ce_map.py `structure_surfaces`): a converted map's concrete and
--- metal are one small colour map stretched over tens of metres, flat
--- paint beside the remastered rock. Each set names its slots by base map
--- (`bases`: substrings of the base texture's name) and two surfaces
--- (`rock_a` the grain, `rock_b` the large shapes: { d, n, o } texture
--- paths), and they draw with the cliffs' master: the surface projected in
--- world space, the map's own base map as its colour (so its stains, seams
--- and painted lines stay where they were) and its lightmap as its light.
--- No turf at a lip and no sand at a foot unless a set asks (`drape`,
--- `foot`: the cliffs' parameters): a wall is not a cliff, but stains run
--- down it from its top and it stands in shade where it meets the ground.
--- By the sea it is wet as the rock is (`wet` cm over the water).
function Land.structures(world, spec)
    local sets = type(spec.structures) == "table" and spec.structures or {}
    if #sets == 0 then return 0 end
    local kml = findObject("/Script/Engine.Default__KismetMaterialLibrary")
    local parent = resolveMesh(TRIAL_MASTERS .. "M_CE_CliffPBR.M_CE_CliffPBR")
    if not (kml and parent) then return 0 end
    local function vec(mid, name, v)
        if type(v) == "table" then
            mid:SetVectorParameterValue(FName(name), { R = v[1] or 0, G = v[2] or 0, B = v[3] or 0, A = v[4] or 1 })
        end
    end
    local levels = lightmapSun()
    local cliff = type(spec.cliff) == "table" and spec.cliff or {}
    local sea = Land.seaHeight()
    -- The landscape's edge map: where each wall's top and foot are.
    local edge = type(spec.pbr) == "table" and type(spec.pbr.edge) == "table" and spec.pbr.edge
    local edgeTex = edge and type(edge.texture) == "string" and resolveMesh(edge.texture) or nil
    Land.structureMids = {}
    local changed = 0
    for si, set in ipairs(sets) do
        local textures = {}
        for prefix, rock in pairs({ RockA = set.rock_a, RockB = set.rock_b or set.rock_a }) do
            if type(rock) == "table" then
                textures[prefix .. "D"] = Land.megascans(rock.d)
                textures[prefix .. "N"] = Land.megascans(rock.n)
                textures[prefix .. "O"] = Land.megascans(rock.o)
            end
        end
        local tokens = {}
        for _, b in ipairs(type(set.bases) == "table" and set.bases or {}) do tokens[#tokens + 1] = tostring(b):lower() end
        if textures.RockAD and textures.RockAN and #tokens > 0 then
            for index, item in ipairs(Current.level.decor or {}) do
                local actor = Current.actors[(type(item) == "table" and item.id) or ("#" .. index)]
                if type(item) == "table" and type(item.materials) == "table" and actor and actor:IsValid() then
                    local comp = actor.StaticMeshComponent
                    for i, entry in ipairs(item.materials) do
                        local t = type(entry) == "table" and type(entry.textures) == "table" and entry.textures
                        local leaf = t and type(t.Base) == "string" and t.Base:match("%.([%w_]+)$")
                        local hit = false
                        if leaf then
                            local lower = leaf:lower()
                            for _, token in ipairs(tokens) do hit = hit or lower:find(token, 1, true) ~= nil end
                        end
                        if hit then
                            local mid = kml:CreateDynamicMaterialInstance(world, parent,
                                FName(string.format("mjolnir_structure_%d_%d", si, i)), 0)
                            if mid and mid:IsValid() then
                                for name, tex in pairs(textures) do mid:SetTextureParameterValue(FName(name), tex) end
                                local base = resolveMesh(t.Base)
                                if base then mid:SetTextureParameterValue(FName("Base"), base) end
                                local lm = type(t.Lightmap) == "string" and not t.Lightmap:find("object_lighting", 1, true)
                                    and resolveMesh(t.Lightmap)
                                if lm and levels then
                                    mid:SetTextureParameterValue(FName("LM"), lm)
                                    vec(mid, "LandLMLevels", { levels[1], levels[2], 0, 0 })
                                end
                                -- `bake_ao`: the conversion's baked corners
                                -- (the slot's Bake texture), as a power.
                                local bake = set.bake_ao and type(t.Bake) == "string" and resolveMesh(t.Bake)
                                if bake then
                                    mid:SetTextureParameterValue(FName("Bake"), bake)
                                    vec(mid, "CliffBakeAO", { set.bake_ao, 0, 0, 0 })
                                end
                                vec(mid, "CliffTiles", set.tiles)
                                vec(mid, "CliffMix", set.mix)
                                vec(mid, "CliffLook", set.look)
                                vec(mid, "RockTint", set.tint)
                                vec(mid, "CliffRough", set.rough)
                                vec(mid, "CliffFar", set.far)
                                vec(mid, "CliffVary", set.vary)
                                vec(mid, "CliffCETint", set.ce_tint or cliff.ce_tint)
                                vec(mid, "CliffDrape", set.drape or { 30, 70, 700, 0 })
                                vec(mid, "CliffFoot", set.foot or { 35, 150, 0.45, 0 })
                                -- `drape`: earth under a wall's top, a fringe of
                                -- moss on it and stains below, in the cliffs'
                                -- soil and the ground's grass; no turf on the
                                -- surfaces that look up (CliffLedge 0: floors).
                                if set.drape then
                                    local own = type(spec.pbr) == "table" and type(spec.pbr.surfaces) == "table"
                                        and spec.pbr.surfaces or {}
                                    local soil = type(cliff.soil) == "table" and cliff.soil or Land.SOIL
                                    local dress = {
                                        GrassD = Land.megascans(own.GrassD or Land.SURFACES.GrassD),
                                        GrassN = Land.megascans(own.GrassN or Land.SURFACES.GrassN),
                                        SoilD = Land.megascans(soil.d), SoilN = Land.megascans(soil.n),
                                        SoilO = Land.megascans(soil.o),
                                    }
                                    for name, tex in pairs(dress) do mid:SetTextureParameterValue(FName(name), tex) end
                                    vec(mid, "GrassTint", set.moss or (spec.pbr and spec.pbr.grass_tint))
                                    vec(mid, "CliffLedge", { set.ledge or 0, 0, 0, 0 })
                                end
                                if edgeTex and (set.drape or set.foot) then
                                    mid:SetTextureParameterValue(FName("Edge"), edgeTex)
                                    vec(mid, "EdgeRect", edge.rect)
                                    vec(mid, "EdgeRange", { edge.range[1], edge.range[2], 0, 0 })
                                end
                                if sea and set.wet then vec(mid, "LandSea", { sea, 0, set.wet, 1 }) end
                                local f = set.fill or cliff.fill
                                if type(f) == "table" then
                                    vec(mid, "CliffFill", { f[1], f[2], f[3], (f[4] or 0) * lightScale() })
                                end
                                -- A set's `fill_occlusion` {share, power}: the
                                -- fill follows the map's baked shade.
                                local fd = set.fill_dir or cliff.fill_dir or { 0.75, -0.35, 0, 0 }
                                local fo = type(set.fill_occlusion) == "table" and set.fill_occlusion or { 0, 0 }
                                vec(mid, "CliffFillDir", { fd[1], fd[2], fo[1] or 0, fo[2] or 0 })
                                if pcall(function() comp:SetMaterial(i - 1, mid) end) then
                                    changed = changed + 1
                                    Land.structureMids[#Land.structureMids + 1] = mid
                                end
                            end
                        end
                    end
                end
            end
        end
    end
    return changed
end

function Land.megascans(path)
    if type(path) ~= "string" then return nil end
    if path:sub(1, 1) == "/" then return resolveMesh(path) end
    local leaf = path:match("([^/]+)$")
    return resolveMesh(Land.MEGASCANS .. path .. "." .. leaf)
end

--- Spawn the tessellated cliffs (Land.cliffs, cliff.tess): the mesh at the
--- origin, its sections in `mids`, then the terrain's own cliff slots
--- hidden. Out of Lumen's bounce and casting no shadow, as the terrain
--- mesh (its shadow proxy still casts the cliffs' shadows): the copy's
--- Lumen cards bounced its fill over the whole scene (2026-10-13).
function Land.tessCliffs(world, tess, mids, terrain, hidden)
    local mesh = resolveMesh(tess.mesh)
    if not mesh then error("tessellated cliff mesh not found: " .. tostring(tess.mesh)) end
    local key = "__cliff_tess"
    local actor = Current.actors[key]
    if not (actor and actor:IsValid()) then
        actor = world:SpawnActor(findObject("/Script/Engine.StaticMeshActor"), { X = 0, Y = 0, Z = 0 },
            { Pitch = 0, Yaw = 0, Roll = 0 })
        if not (actor and actor:IsValid()) then error("spawn failed") end
        Current.actors[key] = actor
    end
    local c = actor.StaticMeshComponent
    c.Mobility = MOBILITY_MOVABLE
    c:SetStaticMesh(mesh)
    c:SetCollisionEnabled(COLLISION_NONE)
    c:SetCastShadow(false)
    c:SetAffectDynamicIndirectLighting(false)
    for k, m in ipairs(mids) do c:SetMaterial(k - 1, m) end
    for _, slot in ipairs(tess.slots) do terrain:SetMaterial(slot, hidden) end
end

--- Slot meshes (level.slot_meshes, tools/level/cliff_mesh.py --parent):
--- translucent surfaces a conversion left on the opaque terrain mesh, which
--- can draw no translucency (a mesh enters that pass by its own slots), as a
--- mesh of their own at the origin. Each section takes the material the
--- loader made for its slot on decor `item`, and the slot is hidden.
--- Yoyorast's plasma beams drew white, then nothing (2026-10-13).
function Land.slotMeshes(world, level)
    local n = 0
    for gi, e in ipairs(type(level.slot_meshes) == "table" and level.slot_meshes or {}) do
        local terrain = Current.actors[e.item]
        local mesh = type(e.mesh) == "string" and resolveMesh(e.mesh)
        local hidden = resolveMesh(TRIAL_MASTERS .. "M_CE_Hidden.M_CE_Hidden")
        if terrain and terrain:IsValid() and mesh and hidden then
            local key = "__slot_mesh_" .. gi
            local actor = Current.actors[key]
            if not (actor and actor:IsValid()) then
                actor = world:SpawnActor(findObject("/Script/Engine.StaticMeshActor"), { X = 0, Y = 0, Z = 0 },
                    { Pitch = 0, Yaw = 0, Roll = 0 })
                Current.actors[key] = actor
            end
            if actor and actor:IsValid() then
                local c, tc = actor.StaticMeshComponent, terrain.StaticMeshComponent
                c.Mobility = MOBILITY_MOVABLE
                c:SetStaticMesh(mesh)
                c:SetCollisionEnabled(COLLISION_NONE)
                c:SetCastShadow(false)
                for k, slot in ipairs(e.slots or {}) do
                    c:SetMaterial(k - 1, tc:GetMaterial(slot))
                    tc:SetMaterial(slot, hidden)
                end
                n = n + 1
            end
        else
            Log("slot mesh " .. tostring(e.mesh) .. ": " .. (mesh and "decor '" .. tostring(e.item) .. "' not spawned"
                or "mesh not found"))
        end
    end
    return n
end

function Land.cliffs(world, spec)
    local cliff = spec.cliff
    if type(cliff) ~= "table" then return 0 end
    local details = {}
    for _, d in ipairs(type(cliff.details) == "table" and cliff.details or {}) do details[d] = true end
    -- `cliff.slots`: the terrain's cliff slots exactly (0-based), over the
    -- detail maps (Sidewinder's cliffs share its ground's snow detail).
    -- `details` then answers by slot: isCliff(leaf, slot).
    local slotSet = nil
    if type(cliff.slots) == "table" then
        slotSet = {}
        for _, s in ipairs(cliff.slots) do slotSet[s] = true end
    end
    local function isCliff(leaf, slot, item)
        if slotSet then
            return slotSet[slot] == true and type(item.mesh) == "string" and item.mesh:find("_Terrain%.") ~= nil
        end
        return leaf ~= nil and details[leaf] == true
    end
    -- `cliff.material`: a shipped material the cliff slots take as they are
    -- (Ice Fields: B40's MIP_Rock_Glacial_Inst, rock and snow projected in
    -- world space, so CE's UVs do not matter); the cladding rocks then keep
    -- their meshes' own (B40's glacial rocks, snow-topped already).
    -- `cliff.scalars` over the shipped material's own (scalarMid): its rock
    -- tiles by CE's UVs ("Tile U#0", "Tile V#0"), and Sidewinder's cliff strip
    -- spans 92 m across to 26 m up, which squashed the rock flat
    -- (2026-10-13).
    local shipped = type(cliff.material) == "string" and resolveMesh(cliff.material)
    if shipped and type(cliff.scalars) == "table" then
        shipped = scalarMid(world, shipped, cliff.scalars) or shipped
    end
    if shipped then
        local n = 0
        for index, item in ipairs(Current.level.decor or {}) do
            local actor = Current.actors[(type(item) == "table" and item.id) or ("#" .. index)]
            if type(item) == "table" and type(item.materials) == "table" and actor and actor:IsValid() then
                for i, entry in ipairs(item.materials) do
                    local t = type(entry) == "table" and type(entry.textures) == "table" and entry.textures
                    local leaf = t and type(t.Primary) == "string" and t.Primary:match("%.([%w_]+)$")
                    if t and isCliff(leaf, i - 1, item) and pcall(function() actor.StaticMeshComponent:SetMaterial(i - 1, shipped) end) then
                        n = n + 1
                    end
                end
            end
        end
        -- With cliff.tess: the cliffs' subdivided copy (smoothed normals) in
        -- the shipped material, for CE's faceted slots: Ice Fields' rock
        -- lumps drew as hard-edged domes.
        local tess = type(cliff.tess) == "table" and cliff.tess
        local hidden = tess and resolveMesh(TRIAL_MASTERS .. "M_CE_Hidden.M_CE_Hidden")
        local item = tess and hidden and Current.actors[tess.item]
        if item and item:IsValid() then
            local mids = {}
            for k = 1, #(tess.slots or {}) do mids[k] = shipped end
            local ok, err = pcall(Land.tessCliffs, world, tess, mids, item.StaticMeshComponent, hidden)
            Log("landscape: " .. (ok and string.format("cliffs subdivided (%d section(s)) in the shipped rock", #mids)
                or tostring(err)))
        end
        return n
    end
    local kml = findObject("/Script/Engine.Default__KismetMaterialLibrary")
    local parent = resolveMesh(TRIAL_MASTERS .. "M_CE_CliffPBR.M_CE_CliffPBR")
    if not (kml and parent) then return 0 end
    -- Tessellated cliffs (cliff.tess): the terrain's cliff slots drawn by a
    -- Nanite copy of themselves (tools/level/cliff_mesh.py, `mesh`, Unreal
    -- cm at the origin, a section a slot of `slots` on decor `item`) in
    -- M_CE_CliffTess, displaced by the rock's height (`disp`, 0..1 of 50 cm),
    -- the slots themselves hidden; `cladding` puts the cladding rocks on the
    -- tessellated master too, at `clad_disp`.
    local tess = type(cliff.tess) == "table" and cliff.tess or nil
    local tessParent = tess and resolveMesh(TRIAL_MASTERS .. "M_CE_CliffTess.M_CE_CliffTess")
    local hidden = tess and resolveMesh(TRIAL_MASTERS .. "M_CE_Hidden.M_CE_Hidden")
    if not (tessParent and hidden) then tess = nil end
    local tessSection = {}
    for k, slot in ipairs(tess and tess.slots or {}) do tessSection[slot] = k end
    local tessMids, tessComp = {}, nil
    local textures = {}
    for prefix, rock in pairs({ RockA = cliff.rock_a or Land.ROCK_A, RockB = cliff.rock_b or Land.ROCK_B }) do
        textures[prefix .. "D"] = Land.megascans(rock.d)
        textures[prefix .. "N"] = Land.megascans(rock.n)
        textures[prefix .. "O"] = Land.megascans(rock.o)
    end
    -- The level's own ground (pbr.surfaces) over B30's: Ice Fields' cliffs
    -- take its snow on their ledges and at their feet, not B30's turf.
    local own = type(spec.pbr) == "table" and type(spec.pbr.surfaces) == "table" and spec.pbr.surfaces or {}
    textures.GrassD = Land.megascans(own.GrassD or Land.SURFACES.GrassD)
    textures.GrassN = Land.megascans(own.GrassN or Land.SURFACES.GrassN)
    textures.SandD = Land.megascans(own.SandD or Land.SURFACES.SandD)
    -- The earth under the turf at a lip.
    local soil = type(cliff.soil) == "table" and cliff.soil or Land.SOIL
    textures.SoilD = Land.megascans(soil.d)
    textures.SoilN = Land.megascans(soil.n)
    textures.SoilO = Land.megascans(soil.o)
    -- The landscape's edge map: where each wall's top and foot are.
    local edge = type(spec.pbr) == "table" and type(spec.pbr.edge) == "table" and spec.pbr.edge
    textures.Edge = edge and type(edge.texture) == "string" and resolveMesh(edge.texture) or nil
    local function vec(mid, name, v)
        if type(v) == "table" then
            mid:SetVectorParameterValue(FName(name), { R = v[1] or 0, G = v[2] or 0, B = v[3] or 0, A = v[4] or 1 })
        end
    end
    local levels = lightmapSun()
    local sea = Land.seaHeight()
    Land.cliffMids = {}
    local changed = 0
    for index, item in ipairs(Current.level.decor or {}) do
        local id = (type(item) == "table" and item.id) or ("#" .. index)
        local actor = Current.actors[id]
        if type(item) == "table" and type(item.materials) == "table" and actor and actor:IsValid() then
            local comp = actor.StaticMeshComponent
            for i, entry in ipairs(item.materials) do
                local t = type(entry) == "table" and type(entry.textures) == "table" and entry.textures
                local leaf = t and type(t.Primary) == "string" and t.Primary:match("%.([%w_]+)$")
                if t and isCliff(leaf, i - 1, item) then
                    local mid = kml:CreateDynamicMaterialInstance(world, parent, FName(string.format("mjolnir_cliff_%d", i)), 0)
                    if mid and mid:IsValid() then
                        for name, tex in pairs(textures) do mid:SetTextureParameterValue(FName(name), tex) end
                        local base = type(t.Base) == "string" and resolveMesh(t.Base)
                        if base then mid:SetTextureParameterValue(FName("Base"), base) end
                        -- (Scenery's "lightmap" is CE's object lighting, no page.)
                        local lm = type(t.Lightmap) == "string" and not t.Lightmap:find("object_lighting", 1, true)
                            and resolveMesh(t.Lightmap)
                        if lm and levels then
                            mid:SetTextureParameterValue(FName("LM"), lm)
                            vec(mid, "LandLMLevels", { levels[1], levels[2], 0, 0 })
                        end
                        vec(mid, "GrassTint", spec.pbr and spec.pbr.grass_tint)
                        vec(mid, "CliffTiles", cliff.tiles)
                        vec(mid, "CliffMix", cliff.mix)
                        vec(mid, "CliffLook", cliff.look)
                        vec(mid, "RockTint", cliff.tint)
                        vec(mid, "CliffRough", cliff.rough)
                        vec(mid, "CliffFar", cliff.far)
                        vec(mid, "CliffCETint", cliff.ce_tint)
                        if textures.Edge then
                            vec(mid, "EdgeRect", edge.rect)
                            vec(mid, "EdgeRange", { edge.range[1], edge.range[2], 0, 0 })
                        end
                        vec(mid, "CliffDrape", cliff.drape)
                        vec(mid, "CliffFoot", cliff.foot)
                        -- Scenery (CE's object lighting, no lightmap page): a
                        -- boulder, bare rock, no turf on its top or sand at its foot.
                        if type(t.Lightmap) == "string" and t.Lightmap:find("object_lighting", 1, true) then
                            local d = type(cliff.drape) == "table" and cliff.drape or { 30, 70, 700 }
                            local fo = type(cliff.foot) == "table" and cliff.foot or { 35, 150, 0.45 }
                            vec(mid, "CliffDrape", { d[1], d[2], d[3], 0 })
                            vec(mid, "CliffFoot", { fo[1], fo[2], fo[3], 0 })
                            -- Its CE map is light granite, not the cliffs' dark
                            -- strip: unboosted, and more of its own colour
                            -- (at the cliffs' 2.6 the boulders went white).
                            local mx = type(cliff.mix) == "table" and cliff.mix or { 0.6, 1, 1, 1 }
                            local lk = type(cliff.look) == "table" and cliff.look or { 1.2, 0.55, 0.3, 1.5 }
                            vec(mid, "CliffMix", { mx[1], mx[2], 0.75, mx[4] })
                            vec(mid, "CliffLook", { lk[1], 0.7, lk[3], 1.2 })
                        end
                        -- The foot's sand tint: the ground's own (as the beach).
                        vec(mid, "CliffSand", cliff.sand or (type(spec.pbr) == "table" and spec.pbr.sand_tint))
                        -- The fill is light: exposed as the level's lights are.
                        local f = cliff.fill
                        if type(f) == "table" then vec(mid, "CliffFill", { f[1], f[2], f[3], (f[4] or 0) * lightScale() }) end
                        -- Indoors: CE's lightmap is the rock's light (`indoor`, its gain).
                        if spec.indoor then
                            vec(mid, "CliffIndoor", { (tonumber(cliff.indoor) or 1.0) * lightScale(), 0, 0, 0 })
                        end
                        vec(mid, "CliffFillDir", cliff.fill_dir)
                        if sea then vec(mid, "LandSea", { sea, 0, cliff.wet or 60, 1 }) end
                        -- The tessellated copy's section: the same rock.
                        local k = tess and item.id == tess.item and tessSection[i - 1]
                        if k then
                            local tm = kml:CreateDynamicMaterialInstance(world, tessParent,
                                FName(string.format("mjolnir_clifftess_%d", i - 1)), 0)
                            if tm and tm:IsValid() and pcall(function() tm:CopyParameterOverrides(mid) end) then
                                vec(tm, "CliffDisp", { tess.disp or 0.6, tess.mip or 400, 0, 0 })
                                tessMids[k] = tm
                                tessComp = comp
                            end
                        end
                        if pcall(function() comp:SetMaterial(i - 1, mid) end) then
                            changed = changed + 1
                            Land.cliffMids[#Land.cliffMids + 1] = mid
                        end
                    end
                end
            end
        end
    end
    if tess and tessComp and #tessMids == #(tess.slots or {}) then
        local ok, err = pcall(Land.tessCliffs, world, tess, tessMids, tessComp, hidden)
        Log("landscape: " .. (ok and string.format("cliffs tessellated (%d section(s))", #tessMids) or tostring(err)))
        for _, tm in ipairs(tessMids) do Land.cliffMids[#Land.cliffMids + 1] = tm end
    elseif tess then
        Log(string.format("landscape: cliffs not tessellated (%d of %d section material(s))", #tessMids,
            #(tess.slots or {})))
    end
    -- The cladding rocks (Foliage.cliffGroups): the same rock, their CE base
    -- map the wall's, their CE light their own (group.lm: the lightmap under
    -- each, custom primitive data) or their group's.
    -- (M_CE_CladTess: the cliffs' tessellated master shades by normals
    -- the cliff mesh carries in UV2/UV3, which a rock's mesh has not.)
    local cladTess = tess and tess.cladding and resolveMesh(TRIAL_MASTERS .. "M_CE_CladTess.M_CE_CladTess")
    local cladParent = cladTess or parent
    for gi, group in ipairs(Foliage.cliffGroups or {}) do
        local mid = kml:CreateDynamicMaterialInstance(world, cladParent, FName(string.format("mjolnir_clad_%d", gi)), 0)
        if mid and mid:IsValid() then
            for name, tex in pairs(textures) do mid:SetTextureParameterValue(FName(name), tex) end
            local base = type(group.base) == "string" and resolveMesh(group.base)
            if base then mid:SetTextureParameterValue(FName("Base"), base) end
            vec(mid, "GrassTint", spec.pbr and spec.pbr.grass_tint)
            vec(mid, "CliffTiles", cliff.tiles)
            vec(mid, "CliffMix", cliff.mix)
            vec(mid, "CliffLook", cliff.look)
            vec(mid, "RockTint", cliff.tint)
            vec(mid, "CliffRough", cliff.rough)
            vec(mid, "CliffFar", cliff.far)
            vec(mid, "CliffCETint", cliff.ce_tint)
            local f = cliff.fill
            if type(f) == "table" then vec(mid, "CliffFill", { f[1], f[2], f[3], (f[4] or 0) * lightScale() }) end
            vec(mid, "CliffFillDir", cliff.fill_dir)
            -- The rocks' own displacement (`clad_disp`): Megascans meshes are
            -- detailed already, and the walls' 0.6 folded them, backfaces
            -- showing as pale lavender patches (2026-10-13).
            if cladParent ~= parent then
                vec(mid, "CliffDisp", { tess.clad_disp or tess.disp or 0.6, tess.mip or 400, 0, 0 })
            end
            if textures.Edge then
                vec(mid, "EdgeRect", edge.rect)
                vec(mid, "EdgeRange", { edge.range[1], edge.range[2], 0, 0 })
            end
            -- Rocks have no lip of their own and no foot: no turf, no sand.
            local d = type(cliff.drape) == "table" and cliff.drape or { 35, 35, 700 }
            vec(mid, "CliffDrape", { d[1], d[2], d[3], 0 })
            vec(mid, "CliffFoot", { 35, 150, 0.45, 0 })
            if sea then vec(mid, "LandSea", { sea, 0, cliff.wet or 60, 1 }) end
            local gl = type(group.light) == "table" and group.light or { -1, -1, -1 }
            if group.lm and levels then
                vec(mid, "CladLight", { gl[1], gl[2], gl[3], 2 })
                vec(mid, "LandLMLevels", { levels[1], levels[2], 0, 0 })
            else
                vec(mid, "CladLight", group.light)
            end
            -- Thousands of rocks (7,086 on Blood Gulch): during a load, a
            -- slice a frame (Current.dressQueue, the step after this one).
            local function dressRock(actor)
                if actor:IsValid() then
                    pcall(function() actor.StaticMeshComponent:SetMaterial(0, mid) end)
                end
            end
            if Current.dressQueue then
                Current.dressQueue.add(group.actors, dressRock)
            else
                for _, actor in ipairs(group.actors) do dressRock(actor) end
            end
            -- Baked rocks are the world's: no handle kept once dressed.
            if group.baked then group.actors = {} end
            changed = changed + 1
            Land.cliffMids[#Land.cliffMids + 1] = mid
        end
    end
    return changed
end

--- The terrain mesh's ground slots under a B30 landscape (level.landscape.cut)
--- drawn with M_CE_GroundPBR: the same ground, only in the landscape's holes,
--- so a hole's edge shows no seam. Returns the slots changed.
function Land.ground(world, spec)
    local cut = spec.cut
    if type(cut) ~= "table" then return 0 end
    local bases = {}
    for _, b in ipairs(type(cut.bases) == "table" and cut.bases or { cut.base }) do bases[b] = true end
    -- `cut.slots`: the ground's terrain slots exactly (0-based), over the
    -- base maps, which slots of other shaders can share (Ice Fields' caves).
    local exact = nil
    if type(cut.slots) == "table" then
        exact = {}
        for _, s in ipairs(cut.slots) do exact[s] = true end
    end
    local kml = findObject("/Script/Engine.Default__KismetMaterialLibrary")
    local parent = resolveMesh(TRIAL_MASTERS .. "M_CE_GroundPBR.M_CE_GroundPBR")
    local mask = type(cut.mask) == "string" and resolveMesh(cut.mask)
    if not (kml and parent and mask) then return 0 end
    -- One instance a slot: each reads its own base map and lightmap page by
    -- the mesh's UVs (the bakes hold only the lowest layer of the ground).
    Land.groundMids = {}
    local changed = 0
    for index, item in ipairs(Current.level.decor or {}) do
        local id = (type(item) == "table" and item.id) or ("#" .. index)
        local actor = Current.actors[id]
        if type(item) == "table" and type(item.materials) == "table" and actor and actor:IsValid() then
            local comp = actor.StaticMeshComponent
            for i, entry in ipairs(item.materials) do
                if type(entry) == "table" and type(entry.textures) == "table" and bases[entry.textures.Base]
                    and (not exact or exact[i - 1]) then
                    local mid = kml:CreateDynamicMaterialInstance(world, parent, FName(string.format("mjolnir_ground_%d", i)), 0)
                    if mid and mid:IsValid() then
                        Land.pbr({
                            tex = function(n, t) mid:SetTextureParameterValue(FName(n), t) end,
                            vec = function(n, v) mid:SetVectorParameterValue(FName(n), v) end,
                        }, spec.pbr)
                        mid:SetTextureParameterValue(FName("LandMask"), mask)
                        mid:SetScalarParameterValue(FName("LandMaskSize"), cut.size or 505)
                        if type(cut.edge) == "number" then mid:SetScalarParameterValue(FName("LandCutEdge"), cut.edge) end
                        local own = resolveMesh(entry.textures.Base)
                        if own then mid:SetTextureParameterValue(FName("Base"), own) end
                        local lm = type(entry.textures.Lightmap) == "string" and resolveMesh(entry.textures.Lightmap)
                        if lm then mid:SetTextureParameterValue(FName("LM"), lm) end
                        mid:SetScalarParameterValue(FName("MeshUV"), 1.0)
                        -- Steep ground in the cliffs' rock (level.landscape.cliff).
                        local cl = type(spec.cliff) == "table" and spec.cliff
                        if cl then
                            local rock = type(cl.rock_a) == "table" and cl.rock_a or Land.ROCK_A
                            local rd, rn = Land.megascans(rock.d), Land.megascans(rock.n)
                            if rd and rn then
                                mid:SetTextureParameterValue(FName("RockD"), rd)
                                mid:SetTextureParameterValue(FName("RockN"), rn)
                                local t = type(cl.tint) == "table" and cl.tint or { 1, 1, 1 }
                                mid:SetVectorParameterValue(FName("RockTint"), { R = t[1], G = t[2], B = t[3], A = 1 })
                                local st = type(cl.steep) == "table" and cl.steep or { 0.35, 0.6, 250, 1 }
                                mid:SetVectorParameterValue(FName("GroundSteep"), { R = st[1], G = st[2], B = st[3], A = st[4] })
                                local f = type(cl.fill) == "table" and cl.fill or { 1, 0.8, 0.62, 0 }
                                mid:SetVectorParameterValue(FName("CliffFill"),
                                    { R = f[1], G = f[2], B = f[3], A = (f[4] or 0) * lightScale() })
                            end
                        end
                        local blended = type(entry.scalars) == "table" and (entry.scalars.Type or 0) > 0.5
                        mid:SetScalarParameterValue(FName("PlainSand"), blended and 0.0 or 1.0)
                        -- `cut.looks`: a slot's own parameters over the ground's
                        -- ({ slots, vectors = { name = {r, g, b, a} } }): Ice
                        -- Fields' ice patches, the ground forced wet (a sea far
                        -- above): glassy, darker, blue, flat.
                        for _, look in ipairs(type(cut.looks) == "table" and cut.looks or {}) do
                            local on = false
                            for _, s in ipairs(type(look.slots) == "table" and look.slots or {}) do on = on or s == i - 1 end
                            if on then
                                for pname, v in pairs(type(look.vectors) == "table" and look.vectors or {}) do
                                    mid:SetVectorParameterValue(FName(pname), { R = v[1] or 0, G = v[2] or 0, B = v[3] or 0, A = v[4] or 0 })
                                end
                                for pname, v in pairs(type(look.scalars) == "table" and look.scalars or {}) do
                                    mid:SetScalarParameterValue(FName(pname), v)
                                end
                            end
                        end
                        if pcall(function() comp:SetMaterial(i - 1, mid) end) then
                            changed = changed + 1
                            Land.groundMids[#Land.groundMids + 1] = mid
                        end
                    end
                end
            end
        end
    end
    return changed
end

function Land.apply(world)
    local spec = Current.level and Current.level.landscape
    if type(spec) ~= "table" then return end
    -- An indoor map (upgrade_ce_map.py `indoor`: Rat Race's tunnels): no
    -- Landscape, only its cliffs in the game's rock.
    if spec.indoor then
        local cok, cliffs = pcall(Land.cliffs, world, spec)
        Log("landscape: indoor, " .. (cok and string.format("%d cliff slot(s) in the game's rock", cliffs)
            or tostring(cliffs)))
        return
    end
    Current.lap("before landscape")
    local land = Current.landscapeActor(world)
    Current.lap("landscape scan")
    if not (land and land:IsValid()) then
        Log("landscape: the level names one but the world has none")
        return
    end
    if type(spec.pbr) == "table" then
        -- Four jobs, in order: during a load each goes to the load's queue
        -- (Current.dressQueue), and none shares a frame with another once
        -- the frame's budget is spent; together they were a 90 ms frame on
        -- Timberland. Otherwise they run now.
        local jobs = {
            function()
                local ok, missing = pcall(Land.pbr, Land.landSetter(land), spec.pbr)
                Log("landscape: " .. (ok and string.format("B30 ground applied (%d surface map(s) missing)", missing)
                    or tostring(missing)))
                Current.lap("landscape pbr")
            end,
            function()
                local gok, slots = pcall(Land.ground, world, spec)
                Log("landscape: " .. (gok and string.format("%d mesh ground slot(s) in the same look", slots)
                    or tostring(slots)))
                Current.lap("landscape ground")
            end,
            function()
                -- The cliffs' fill (the sand's bounce) on the landscape too,
                -- its share on flat ground GroundSlope.w (pbr.slope[4]).
                local f = type(spec.cliff) == "table" and spec.cliff.fill
                if type(f) == "table" then
                    pcall(function()
                        land:SetLandscapeMaterialVectorParameterValue(FName("CliffFill"),
                            { R = f[1], G = f[2], B = f[3], A = (f[4] or 0) * lightScale() })
                    end)
                end
                local cok, cliffs = pcall(Land.cliffs, world, spec)
                Log("landscape: " .. (cok and string.format("%d cliff slot(s) in the game's rock", cliffs)
                    or tostring(cliffs)))
                Current.lap("landscape cliffs")
            end,
            function()
                local sok, n = pcall(Land.structures, world, spec)
                if not sok or n > 0 then
                    Log("landscape: " .. (sok and string.format("%d structure slot(s) in a PBR surface", n) or tostring(n)))
                end
                Current.lap("landscape structures")
            end,
            function()
                pcall(function()
                    local comps = land.LandscapeComponents
                    for i = 1, #comps do
                        comps[i]:SetCastShadow(false)
                        -- Out of Lumen's bounce, as the cladding: lit by the
                        -- fill (emissive), the ground flooded the whole scene
                        -- orange.
                        comps[i]:SetAffectDynamicIndirectLighting(false)
                    end
                end)
                Current.lap("landscape components")
            end,
        }
        local function run(job) if land:IsValid() then job() end end
        if Current.dressQueue then
            Current.dressQueue.add(jobs, run)
        else
            for _, job in ipairs(jobs) do run(job) end
        end
        return
    end
    if type(spec.material) ~= "table" then return end
    local target = {
        IsValid = function() return land:IsValid() end,
        SetScalarParameterValue = function(_, n, v) land:SetLandscapeMaterialScalarParameterValue(n, v) end,
        SetVectorParameterValue = function(_, n, v) land:SetLandscapeMaterialVectorParameterValue(n, v) end,
        SetTextureParameterValue = function(_, n, v) land:SetLandscapeMaterialTextureParameterValue(n, v) end,
    }
    local ok, mid, err = pcall(runtimeMaterial, world, spec.material, "landscape", target)
    Log("landscape: " .. ((ok and mid) and "ground material applied" or tostring(ok and err or mid)))
    -- As the terrain mesh: its shadows come from the shadow proxies (and the
    -- CE lightmaps), not the ground itself.
    pcall(function()
        local comps = land.LandscapeComponents
        for i = 1, #comps do comps[i]:SetCastShadow(false) end
    end)
end

--- Footprints on a landscape, as Silent Cartographer's beach keeps them:
--- every player's steps, drawn with the game's Spartan print into a render
--- target over a square around the local player, which the landscape master
--- reads (build_ce_materials.py FOOT_CODE: FootRT, FootRect) to darken the
--- ground and bend its normal. When the local player nears the square's
--- edge it moves, its prints carried over (two targets, drawn one into the
--- other); they fade slowly. Engine canvas drawing only: a decal material of
--- ours took the game down (a pipeline state it could not build).
local Footprints = {
    MAP = "/HaloLandscapeDeformations/Resources/T_Spartan_Decal_Footprint_11.T_Spartan_Decal_Footprint_11",
    BLACK = "/Engine/EngineResources/Black.Black",
    RES = 4096, SIZE = 4096, -- texels and cm a side: 1 cm a texel (at 2 the tread was lost)
    DARK = 0.85, RELIEF = 3.0, -- how much a print darkens the ground, and bends it (CE ground)
    -- On the B30 ground: no darkening, only light and occlusion (its slopes
    -- read over 3 texels, so 2.5 bends as far as 8 did over one).
    SHADE_RELIEF = 2.5, SHADE_AO = 0.6,
    PRINT = 38, -- cm a side of the print's square map
    STRIDE = 70, SIDE = 12, -- cm between prints, and either side of the line
    FADE = 0.03, -- of the prints' depth lost every FADE_MS
    FADE_MS = 2000,
    on = true, walkers = {}, world = nil, rt = nil, cx = 0, cy = 0, fadedAt = 0,
}

--- A new, black render target. Only the landscape's material instances
--- keep one alive: a target held by Lua alone is garbage collected (a spare
--- held for re-centring went within a minute, and drawing on it took the
--- game down, 2026-10-11), so there is only ever the one in use.
function Footprints.newTarget(world)
    local krl = findObject("/Script/Engine.Default__KismetRenderingLibrary")
    local rt = krl and krl:CreateRenderTarget2D(world, Footprints.RES, Footprints.RES, 0,
        { R = 0, G = 0, B = 0, A = 1 }, false, false)
    if rt and rt:IsValid() then return rt end
    return nil
end

--- The render target, made for this world and handed to the landscape.
function Footprints.targets(world)
    -- By name: two Lua handles on one world are not equal, and comparing
    -- them made new targets every tick.
    local name = world:GetFullName()
    if Footprints.world == name and Footprints.rt and Footprints.rt:IsValid() then return Footprints.rt end
    Footprints.world, Footprints.rt, Footprints.walkers = name, nil, {}
    local land = Current.landscapeActor(world)
    if not (land and land:IsValid()) then return nil end
    local rt = Footprints.newTarget(world)
    if not rt then return nil end
    Footprints.rt, Footprints.land = rt, land
    local pawn = getPawn()
    local p = pawn and pawn:K2_GetActorLocation() or { X = 0, Y = 0 }
    Footprints.cx, Footprints.cy = p.X, p.Y
    land:SetLandscapeMaterialScalarParameterValue(FName("FootTexel"), 1.0 / Footprints.RES)
    land:SetLandscapeMaterialScalarParameterValue(FName("FootDark"), Footprints.DARK)
    land:SetLandscapeMaterialScalarParameterValue(FName("FootRelief"), Footprints.RELIEF)
    land:SetLandscapeMaterialScalarParameterValue(FName("FootStrength"), Footprints.on and 1.0 or 0.0)
    Footprints.params()
    Footprints.hand()
    return rt
end

--- The B30 ground's footprint parameters (M_CE_LandscapePBR FootParams:
--- strength, relief, texel, occlusion).
function Footprints.params()
    local v = { R = Footprints.on and 1.0 or 0.0, G = Footprints.SHADE_RELIEF, B = 1.0 / Footprints.RES, A = Footprints.SHADE_AO }
    Footprints.land:SetLandscapeMaterialVectorParameterValue(FName("FootParams"), v)
    for _, g in ipairs(Land.groundMids or {}) do
        if g:IsValid() then g:SetVectorParameterValue(FName("FootParams"), v) end
    end
end

--- The current target and its square, to the landscape (which also keeps
--- the target from being collected).
function Footprints.hand()
    local land = Footprints.land
    local rect = { R = Footprints.cx, G = Footprints.cy, B = Footprints.SIZE, A = Footprints.SIZE }
    land:SetLandscapeMaterialTextureParameterValue(FName("FootRT"), Footprints.rt)
    land:SetLandscapeMaterialVectorParameterValue(FName("FootRect"), rect)
    -- The mesh's ground in the landscape's holes (Land.ground) takes them too.
    for _, g in ipairs(Land.groundMids or {}) do
        if g:IsValid() then
            g:SetTextureParameterValue(FName("FootRT"), Footprints.rt)
            g:SetVectorParameterValue(FName("FootRect"), rect)
        end
    end
end

--- Draw on `rt` (the current target by default): `fn(canvas)` between
--- begin and end. A target that is gone, or a begin that hands back no
--- canvas, draws nothing: an end with no begin behind it crashed the game.
function Footprints.draw(world, fn, rt)
    rt = rt or Footprints.rt
    if not (rt and rt:IsValid()) then return false end
    local krl = findObject("/Script/Engine.Default__KismetRenderingLibrary")
    -- UE4SS hands the out parameters back shifted: the canvas (and size) in
    -- the first table, the drawing context in the second. The same three
    -- tables every draw (UE4SS keeps each out parameter's table: Current.hit),
    -- emptied first so a begin that fails does not hand back the last
    -- canvas and context.
    Footprints.out = Footprints.out or { {}, {}, {} }
    for _, t in ipairs(Footprints.out) do
        for k in pairs(t) do t[k] = nil end
    end
    local c1, c2, c3 = Footprints.out[1], Footprints.out[2], Footprints.out[3]
    krl:BeginDrawCanvasToRenderTarget(world, rt, c1, c2, c3)
    local canvas = c1.Canvas
    if not (canvas and canvas:IsValid()) then
        Log("footprints: no canvas to draw on; off (mjolnir_footprints on to try again)")
        Footprints.on = false
        return false
    end
    local ok, err = pcall(fn, canvas)
    krl:EndDrawCanvasToRenderTarget(world, c2)
    if not ok then Log("footprints: " .. tostring(err)) end
    return ok
end

--- Move the square to centre on (x, y), carrying the prints over into a
--- new target.
function Footprints.recentre(world, x, y)
    local old = Footprints.rt
    local rt = Footprints.newTarget(world)
    if not (rt and old and old:IsValid()) then return end
    local scale = Footprints.RES / Footprints.SIZE
    local dx, dy = (Footprints.cx - x) * scale, (Footprints.cy - y) * scale
    Footprints.draw(world, function(canvas)
        canvas:K2_DrawTexture(old, { X = dx, Y = dy }, { X = Footprints.RES, Y = Footprints.RES }, { X = 0, Y = 0 },
            { X = 1, Y = 1 }, { R = 1, G = 1, B = 1, A = 1 }, 0, 0, { X = 0.5, Y = 0.5 })
    end, rt)
    Footprints.rt, Footprints.cx, Footprints.cy = rt, x, y
    Footprints.hand()
end

--- One print at (x, y), facing `yaw` (degrees from +x towards +y), `side`
--- -1 or 1 of the walking line.
function Footprints.stamp(world, x, y, yaw, side)
    local map = resolveMesh(Footprints.MAP)
    if not map then return end
    local a = math.rad(yaw)
    local px, py = x - math.sin(a) * Footprints.SIDE * side, y + math.cos(a) * Footprints.SIDE * side
    local scale = Footprints.RES / Footprints.SIZE
    local u = (px - Footprints.cx) * scale + Footprints.RES / 2
    local v = (py - Footprints.cy) * scale + Footprints.RES / 2
    local size = Footprints.PRINT * scale
    if u < 0 or v < 0 or u > Footprints.RES or v > Footprints.RES then return end
    Footprints.draw(world, function(canvas)
        -- The map's toe points up the canvas (-v); the canvas turns it
        -- clockwise, so the walking direction's yaw is 90 degrees on.
        canvas:K2_DrawTexture(map, { X = u - size / 2, Y = v - size / 2 }, { X = size, Y = size }, { X = 0, Y = 0 },
            { X = 1, Y = 1 }, { R = 1, G = 1, B = 1, A = 1 }, 2, yaw + 90, { X = 0.5, Y = 0.5 })
    end)
end

--- The campaign's own ground deformation (343's HaloLandscapeDeformations
--- plugin), on a landscape level unless `landscape.deform` is false: its
--- manager keeps a 9216-texel map over 153.6 m round the camera
--- (MPC_DeformationGlobals DeformationCenterWP, snapped to 51.2 m), into
--- which the brushes the game's Blueprints already carry draw: every
--- warthog wheel and scorpion tread (T_WheelTextureElevation24, tread and
--- all), Spartan and Elite feet, the ghost's melting. Campaign levels place
--- the manager; ours spawns it, and registers the brushes itself (they do
--- not find a manager that comes after them): those in the world, then each
--- as it is made. Our landscape master reads the map as its footprints
--- (FootRT/FootRect: the same uv), so the sand takes tracks with no re-cook.
--- The map stands at 0.2 where nothing was drawn, so prints shade by their
--- slope only (no occlusion). Death Island, 2026-10-14.
Footprints.DEFORM_MANAGER = "/Game/Landscape/Deformation/BP_LandscapeDeformationManager_Configured.BP_LandscapeDeformationManager_Configured_C"
Footprints.DEFORM_BRUSH = "/Script/HaloLandscapeDeformations.LandscapeDeformationBrushComponent"
Footprints.DEFORM_MPC = "/HaloLandscapeDeformations/Toolkit/MPC_DeformationGlobals.MPC_DeformationGlobals"
Footprints.DEFORM_SPAN = 15360
Footprints.brushProps = {}
--- The Blam object classes whose actors carry brushes and are not pawns.
Footprints.BRUSH_ACTORS = { BP_WarthogVehicleActor_C = true, BP_ScorpionVehicleActor_C = true,
    BP_GhostVehicleActor_C = true, BP_SpartansBipedActor_C = true, BP_EliteBipedActor_C = true }

--- Register one brush with the manager, once.
function Footprints.addBrush(b)
    local d = Footprints.deform
    if not (d and d.manager:IsValid() and b and b:IsValid()) then return false end
    local key = b:GetFullName()
    if d.seen[key] or key:find("Default__", 1, true) then return false end
    local owner = b:GetOwner()
    if not (owner and owner:IsValid()) then return false end
    d.seen[key] = true
    return pcall(function() d.manager:AddLandscapeDeformationBrush(b) end)
end

--- The brush components an actor's class declares (its Blueprint variables).
function Footprints.actorBrushes(actor)
    local cls = actor:GetClass()
    local name = cls:GetFName():ToString()
    local props = Footprints.brushProps[name]
    if not props then
        props = {}
        local brushClass = findObject(Footprints.DEFORM_BRUSH)
        local k = cls
        while k and k:IsValid() and not k:GetFullName():find("^Class /Script/") do
            k:ForEachProperty(function(p)
                if p:GetClass():GetFName():ToString() == "ObjectProperty" then
                    local n = p:GetFName():ToString()
                    local ok, pc = pcall(function() return p:GetPropertyClass() end)
                    if ok and pc and brushClass then
                        if pc:GetFullName() == brushClass:GetFullName() then props[#props + 1] = n end
                    elseif n:find("LandscapeDeform") or n:find("^LDB_") or n:find("MeltingBrush") then
                        props[#props + 1] = n
                    end
                end
            end)
            k = k:GetSuperStruct()
        end
        Footprints.brushProps[name] = props
    end
    local n = 0
    for _, p in ipairs(props) do
        local ok, b = pcall(function() return actor[p] end)
        if ok and b and Footprints.addBrush(b) then n = n + 1 end
    end
    return n
end

function Footprints.deformStart(world)
    local land = Current.level and Current.level.landscape
    if not (type(land) == "table" and type(land.pbr) == "table" and land.deform ~= false) then return end
    if Current.actors["__deform_manager"] and Current.actors["__deform_manager"]:IsValid() then return end
    Current.lap("before deformation")
    local ldl = Current.landscapeActor(world)
    Current.lap("deformation landscape scan")
    if not (ldl and ldl:IsValid()) then return end
    local ksl = findObject("/Script/Engine.Default__KismetSystemLibrary")
    local cls = ksl:LoadClassAsset_Blocking(ksl:Conv_SoftClassPathToSoftClassRef(ksl:MakeSoftClassPath(Footprints.DEFORM_MANAGER)))
    if not (cls and cls:IsValid()) then error("deformation manager class not found") end
    local m = world:SpawnActor(cls, { X = 0, Y = 0, Z = 0 }, { Pitch = 0, Yaw = 0, Roll = 0 })
    if not (m and m:IsValid()) then error("deformation manager did not spawn") end
    Current.actors["__deform_manager"] = m
    Footprints.deform = { manager = m, seen = {}, world = world:GetFullName(), cx = nil, cy = nil, land = ldl,
        footprints = Footprints.deform and Footprints.deform.footprints or Footprints.on }
    -- Brushes made from now on (a vehicle or player spawning), once each is
    -- on its actor; the components that exist already, from their actors.
    if not Footprints.watching and mayArm("deform") then
        Footprints.watching = pcall(NotifyOnNewObject, Footprints.DEFORM_BRUSH, function(b)
            ExecuteInGameThreadWithDelay(1000, function() pcall(Footprints.addBrush, b) end)
        end)
    end
    local gs = findObject("/Script/Engine.Default__GameplayStatics")
    local out = {}
    gs:GetAllActorsOfClass(world, findObject("/Script/Engine.Pawn"), out)
    local n = 0
    for i = 1, #out do
        pcall(function() n = n + Footprints.actorBrushes(out[i]:get()) end)
    end
    Current.lap("deformation manager and pawns")
    -- Vehicles and bipeds are not pawns: the actors of their classes. All
    -- are Blam objects, so one GetAllActorsOfClass on their native class
    -- lists them, and each class's name is read once. It was a FindFirstOf
    -- a class (a walk of every object, ~20 ms each) for a class to ask for.
    -- The actors are taken off the call's array now; their classes are read
    -- (1,364 actors on Timberland) and their brushes registered after, a
    -- slice a frame during a load (Current.dressQueue).
    local blam, actors, names, wanted = {}, {}, {}, Footprints.BRUSH_ACTORS
    gs:GetAllActorsOfClass(world, findObject("/Script/BlamSynchronization.BlamObjectActor"), blam)
    for i = 1, #blam do
        pcall(function() actors[#actors + 1] = blam[i]:get() end)
    end
    local function register(actor)
        if not actor:IsValid() then return end
        local class = actor:GetClass()
        local key = class:GetAddress()
        local name = names[key]
        if not name then
            name = class:GetFName():ToString()
            names[key] = name
        end
        if wanted[name] then n = n + Footprints.actorBrushes(actor) end
    end
    local function registered()
        Log(string.format("deformation: the game's manager, %d brush(es) registered%s", n,
            (Footprints.deform and Footprints.deform.fromMpc) and ", centre read by the sand"
            or Footprints.hooked and ", recentres followed" or ""))
    end
    Current.lap("deformation vehicles and bipeds")
    -- Our own footprints give way to the game's.
    Footprints.on = false
    local v = { R = 1.0, G = 4.0, B = 1.0 / 9216.0, A = 0.0 }
    ldl:SetLandscapeMaterialScalarParameterValue(FName("FootStrength"), 0.0)
    ldl:SetLandscapeMaterialVectorParameterValue(FName("FootParams"), v)
    ldl:SetLandscapeMaterialTextureParameterValue(FName("FootRT"), m.RTDeformationMask_Canvas)
    for _, g in ipairs(Land.groundMids or {}) do
        if g:IsValid() then
            g:SetVectorParameterValue(FName("FootParams"), v)
            g:SetTextureParameterValue(FName("FootRT"), m.RTDeformationMask_Canvas)
        end
    end
    -- `foot_mpc` (upgrade_ce_map.py): the sand reads the map's centre from
    -- the game's globals itself (FootFromMPC), as the campaign's ground does,
    -- and nothing here follows the manager.
    if land.pbr.foot_mpc == true then
        Footprints.deform.fromMpc = true
        local rect = { R = 0, G = 0, B = Footprints.DEFORM_SPAN, A = Footprints.DEFORM_SPAN }
        ldl:SetLandscapeMaterialScalarParameterValue(FName("FootFromMPC"), 1.0)
        ldl:SetLandscapeMaterialVectorParameterValue(FName("FootRect"), rect)
        for _, g in ipairs(Land.groundMids or {}) do
            if g:IsValid() then
                g:SetScalarParameterValue(FName("FootFromMPC"), 1.0)
                g:SetVectorParameterValue(FName("FootRect"), rect)
            end
        end
    else
        Footprints.deformHook()
    end
    if Current.dressQueue then
        Current.dressQueue.add(actors, register)
        Current.dressQueue.add({ registered }, function(job) job() end)
    else
        for _, actor in ipairs(actors) do pcall(register, actor) end
        registered()
    end
end

--- The map's centre to the sand: FootRect on the landscape and the mesh's
--- ground in its holes.
function Footprints.deformRect(x, y)
    local d = Footprints.deform
    if not (d and not d.fromMpc and d.land:IsValid()) then return end
    d.cx, d.cy = x, y
    local rect = { R = x, G = y, B = Footprints.DEFORM_SPAN, A = Footprints.DEFORM_SPAN }
    d.land:SetLandscapeMaterialVectorParameterValue(FName("FootRect"), rect)
    for _, g in ipairs(Land.groundMids or {}) do
        if g:IsValid() then g:SetVectorParameterValue(FName("FootRect"), rect) end
    end
end

--- The manager recentres its map (every 51.2 m the camera goes) and shifts
--- the map's contents in the same tick: the sand must follow in that tick.
--- Followed from the 100 ms loop alone, the tracks were drawn off the map
--- for a few frames at every step, a flash while moving (Death Island,
--- 2026-10-15). Its SetMPCGridParameters sets the centre from its actor.
function Footprints.deformHook()
    if Footprints.hooked then return end
    Footprints.hooked = pcall(RegisterHook,
        "/HaloLandscapeDeformations/Toolkit/BP_LandscapeDeformationManager.BP_LandscapeDeformationManager_C:SetMPCGridParameters",
        function(ctx)
            pcall(function()
                local l = ctx:get():K2_GetActorLocation()
                Footprints.deformRect(l.X, l.Y)
            end)
        end)
end

--- The map's centre to the sand, when the manager moves it (the hook's
--- backstop). True while the game's deformation is on (our own footprints
--- stand down).
function Footprints.deformTick()
    local d = Footprints.deform
    if not d then return false end
    local world = getWorld()
    if not (world and world:GetFullName() == d.world and d.manager:IsValid()) then
        Footprints.deform, Footprints.on = nil, d.footprints
        return false
    end
    if d.fromMpc then return true end
    -- Kept for the map: a StaticFindObject of the collection takes ~13 ms,
    -- the library ~1 ms, and asking every run held each 100 ms tick ~15 ms,
    -- a beat ten times a second (MJOLNIRHud's hitch log, 2026-10-17).
    if not (d.mpc and d.mpc:IsValid()) then d.mpc = findObject(Footprints.DEFORM_MPC) end
    if not (d.kml and d.kml:IsValid()) then d.kml = findObject("/Script/Engine.Default__KismetMaterialLibrary") end
    if not (d.mpc and d.kml) then return true end
    local c = d.kml:GetVectorParameterValue(world, d.mpc, FName("DeformationCenterWP"))
    if c.R ~= d.cx or c.G ~= d.cy then Footprints.deformRect(c.R, c.G) end
    return true
end

--- Every player's pawn, stepping: a print each STRIDE it covers on the
--- ground (a jump, a respawn or a teleporter is not a step).
function Footprints.tick()
    if Footprints.deformTick() then return end
    local land = Current.level and Current.level.landscape
    -- Not indoors: no Landscape to find, and looking for one every tick costs.
    if not (Footprints.on and Current.furnished and type(land) == "table" and not land.indoor) then return end
    local world = getWorld()
    if not (world and Footprints.targets(world)) then return end
    local me = not Footprints.hold and getPawn()
    if me then
        local p = me:K2_GetActorLocation()
        if math.abs(p.X - Footprints.cx) > Footprints.SIZE / 4 or math.abs(p.Y - Footprints.cy) > Footprints.SIZE / 4 then
            Footprints.recentre(world, p.X, p.Y)
        end
    end
    local now = os.clock()
    if now - Footprints.fadedAt > Footprints.FADE_MS / 1000 then
        Footprints.fadedAt = now
        local black = resolveMesh(Footprints.BLACK)
        if black then
            Footprints.draw(world, function(canvas)
                canvas:K2_DrawTexture(black, { X = 0, Y = 0 }, { X = Footprints.RES, Y = Footprints.RES },
                    { X = 0, Y = 0 }, { X = 1, Y = 1 }, { R = 1, G = 1, B = 1, A = Footprints.FADE }, 2, 0,
                    { X = 0.5, Y = 0.5 })
            end)
        end
    end
    local gs = findObject("/Script/Engine.Default__GameplayStatics")
    local state = gs and gs:GetGameState(world)
    if not (state and state:IsValid()) then return end
    local players = state.PlayerArray
    for i = 1, #players do
        local ps = players[i]
        local pawn = ps and ps:IsValid() and ps:GetPawn()
        if pawn and pawn:IsValid() then
            local key = ps:GetFullName()
            local p = pawn:K2_GetActorLocation()
            local w = Footprints.walkers[key]
            if not w then
                Footprints.walkers[key] = { x = p.X, y = p.Y, z = p.Z, side = 1 }
            else
                local dx, dy, dz = p.X - w.x, p.Y - w.y, p.Z - w.z
                local d = math.sqrt(dx * dx + dy * dy)
                if d > 400 or math.abs(dz) > 60 then
                    w.x, w.y, w.z = p.X, p.Y, p.Z
                elseif d >= Footprints.STRIDE then
                    w.x, w.y, w.z, w.side = p.X, p.Y, p.Z, -w.side
                    Footprints.stamp(world, p.X, p.Y, math.deg(math.atan(dy, dx)), w.side)
                end
            end
        end
    end
end

function Footprints.command(args)
    local a = (args and args[1] or ""):lower()
    if a == "on" or a == "off" then
        Footprints.on, Footprints.hold = (a == "on"), false
        if Footprints.land and Footprints.land:IsValid() then
            Footprints.land:SetLandscapeMaterialScalarParameterValue(FName("FootStrength"), Footprints.on and 1.0 or 0.0)
            Footprints.params()
        end
    elseif a == "test" then
        -- A trail ahead of the camera, to look at without walking; the
        -- square stays put (not on the player) until on or off.
        Footprints.hold = true
        local world = getWorld()
        local pc = getPlayerController()
        if world and pc and Footprints.targets(world) then
            local cm = pc.PlayerCameraManager
            local o, r = cm:GetCameraLocation(), cm:GetCameraRotation()
            local yaw = r.Yaw
            local rad = math.rad(yaw)
            local x, y = o.X + math.cos(rad) * 300, o.Y + math.sin(rad) * 300
            Footprints.recentre(world, x, y)
            local side = 1
            for _ = 1, 14 do
                side = -side
                Footprints.stamp(world, x, y, yaw, side)
                x, y = x + math.cos(rad) * Footprints.STRIDE, y + math.sin(rad) * Footprints.STRIDE
            end
        end
    end
    Log(string.format("footprints: %s, square at %.0f, %.0f", Footprints.on and "on" or "off", Footprints.cx,
        Footprints.cy))
end

--- Opt-in one-shot capture after the runtime sky mesh and decor are present.
--- The initial environment capture runs before decor. A CE sky mesh can
--- therefore leave native surfaces shaded against an empty capture on load.
--- This opt-in captures the currently rendered sky, including any restored
--- height haze; it intentionally does not repeat the earlier clear-haze capture.
--- Capture once after furnishing; no polling or recurring per-frame work.
function Current.recaptureSkyAfterDecor(world)
    local level = Current.level
    local env = type(level) == "table" and level.environment
    local settings = type(env) == "table" and env.skylight
    if type(settings) ~= "table" or settings.recapture_after_load ~= true or Current.skyRecapture then return false end
    local sky = Current.actors.__sky
    local function identity(object)
        if not (object and object:IsValid()) then return nil end
        return tostring(object:GetAddress()) .. "|" .. object:GetFullName()
    end
    local ok, worldId, skyId, component, componentId = pcall(function()
        local c = sky and sky:IsValid() and sky.LightComponent
        return identity(world), identity(sky), c, identity(c)
    end)
    if not ok or not worldId or not skyId or not componentId then return false end
    local request = { world = worldId, sky = skyId, component = componentId }
    Current.skyRecapture = request
    ExecuteInGameThreadWithDelay(500, function()
        -- Level reload/travel may replace actors while a delayed callback is
        -- pending. Check current state before touching any saved UE handles.
        if Current.skyRecapture ~= request or Current.level ~= level
            or Current.world ~= world or Current.actors.__sky ~= sky then return end
        local captured, err = pcall(function()
            if identity(getWorld()) ~= request.world or identity(world) ~= request.world
                or identity(sky) ~= request.sky or identity(component) ~= request.component then return end
            if identity(sky.LightComponent) ~= request.component then return end
            component:RecaptureSky()
            request.complete = true
            Log("skylight recaptured after decor")
        end)
        if not captured then Log("post-decor skylight capture: " .. tostring(err)) end
    end)
    return true
end

--- A run of ours on the game thread, for MJOLNIRHud's hitch log (its
--- Scripts/hitches.lua): a run reading a millisecond or more goes through
--- a UE4SS shared variable, so a long frame there names the loops that ran
--- in it. The timed loops (`every`) and the load's frames report here.
function Current.reportWork(name, started, took)
    if took < 0.001 then return end
    pcall(function()
        local mod = rawget(_G, "ModRef")
        local work = mod:GetSharedVariable("MJOLNIR.work")
        work = type(work) == "string" and work or ""
        -- Nothing reads it without the HUD: it stops growing.
        if #work < 4000 then
            mod:SetSharedVariable("MJOLNIR.work",
                string.format("%s%.3f|LevelLoader|%s|%.0f;", work, started, name, took * 1000))
        end
    end)
end

--- The fade, once the level is dressed and the player is in the world:
--- from the watcher, and from the dressing's last step. The opening spawn
--- raises no player_spawn (only respawns do), so the game type is
--- announced once the player is in the world.
function Current.tryFade()
    if not (Current.level and Current.furnished) or Current.faded then return end
    if not getPawn() then return end -- still loading
    Current.faded = true
    fadeIn()
    if next(EventWaves) and #EventQueue < 32 then
        refreshLocalPlayer()
        EventQueue[#EventQueue + 1] = { "player_spawn", LOCAL_PLAYER }
    end
end

--- Dress the world from its level file: the sky and lights, the decor, the
--- water, foliage, effects, landscape and footprints, in that order.
--- Each is a step for Dress.run, which spreads them over frames (dress.lua):
--- made in one go they held Timberland's game thread 1.5 s in one frame
--- (docs/lua_native_audit.md). The world counts as furnished, and fades in,
--- once the last step has run; Current.dressing says one is under way.
local function spawnDecor(world)
    local level = Current.level
    Current.world = world
    Current.dressGen = Current.dressGen + 1
    Current.dressing = true
    Current.dressQueue = Dress.queue(function(err) Log("dressing: " .. tostring(err)) end)
    local gen = Current.dressGen
    local steps = {}
    -- Each step's time lapped under its name (Current.lap), from when it
    -- starts, not from the frame before.
    local function step(name, fn, alone)
        steps[#steps + 1] = { name = name, alone = alone, fn = function(deadline)
            if Current.laps then Current.laps.at = os.clock() end
            local more = fn(deadline)
            Current.lap(name)
            return more
        end }
    end
    step("environment", function() spawnEnvironment(world) end)
    step("sounds", function() spawnSounds(world) end)
    step("event sounds", function() preloadEventSounds() end)
    local decor = level and level.decor
    if type(decor) ~= "table" or #decor == 0 then
        Log("level '" .. tostring(level and level.name) .. "': no decor to spawn")
        step("sky recapture", function() Current.recaptureSkyAfterDecor(world) end)
    else
        local origin = level.canvas.origin
        -- Swapped scenery baked into a landscape world (BakeDecor,
        -- MJDecor_<id>): the world's own. It gets its `scalars` and `static`
        -- here, and no handle is kept. One walk of the mesh actors, shared
        -- with the baked rocks (Foliage.scanMeshActors); what the world
        -- lacks is spawned.
        local baked, nBaked, bakedMs, spawnedMs = {}, 0, 0, 0
        if type(level.landscape) == "table" then
            -- The walk in a frame of its own, the names read after it.
            local all, names = {}, nil
            step("mesh actor scan", function()
                all = FindAllOf("StaticMeshActor") or {}
                Current.meshScan = Foliage.newScan()
                baked = Current.meshScan.decor
            end, true)
            step("mesh actor names", function(deadline)
                local scan = Current.meshScan
                names = names or Dress.slices(all, function(a) Foliage.classify(scan, a) end)
                local more = names(deadline)
                if not more then all = {} end
                return more
            end)
        end
        step("decor", Dress.slices(decor, function(item, index)
            local id = (type(item) == "table" and item.id) or ("#" .. index)
            local own = baked[id]
            local itemAt = os.clock()
            if own then
                nBaked = nBaked + 1
                -- Found frames ago (the mesh actor scan).
                if not own:IsValid() then return end
                -- Still, as spawnDecorItem keeps them (a swapped tree's
                -- piece), first and on its own: a material error below
                -- skipped it, and Infinity's small trees swayed apart
                -- (2026-10-19). Worlds baked since carry it themselves
                -- (foliage_bake.py `still`). Either way: a world baked still
                -- follows a level file that lets the piece move, and the
                -- other way round.
                local scalars = type(item.scalars) == "table" and item.scalars
                local still = item.static or (scalars and scalars["Wind Sway Max Angle"] == 0)
                pcall(function() own.StaticMeshComponent:SetEvaluateWorldPositionOffset(not still) end)
                -- `scalars`: instances of the mesh's own materials. A piece
                -- without them keeps the mesh's own, which a piece fresh
                -- from the world has (BakeDecor sets none, and a piece with
                -- a material of its own is not in the runtime decor): set
                -- again only where an earlier dressing of this world (a
                -- reload) gave it instances. Setting every slot of every
                -- piece to what it had was thousands of calls on
                -- Timberland, each changing nothing.
                if scalars or Current.bakedMids[id] then
                    pcall(function()
                        local comp = own.StaticMeshComponent
                        local mesh = comp.StaticMesh
                        for i = 0, comp:GetNumMaterials() - 1 do
                            local src = mesh:GetMaterial(i)
                            local mid = scalars and scalarMid(world, src, scalars) or src
                            if mid then comp:SetMaterial(i, mid) end
                        end
                    end)
                    Current.bakedMids[id] = scalars and true or nil
                end
                bakedMs = bakedMs + (os.clock() - itemAt)
                return
            end
            if not (Current.actors[id] and Current.actors[id]:IsValid()) then
                local actor, err = spawnDecorItem(world, origin, item)
                if actor then
                    Current.actors[id] = actor
                    Current.spawned = Current.spawned + 1
                    -- A turning machine: turned from its rest by the "turning
                    -- machines" loop (motion: pivot_cm from the actor, period
                    -- in seconds, keys { seconds, yaw degrees }), which also
                    -- plays the sounds its turn raises (events: { t seconds,
                    -- wave, gain, inner, falloff cm }) at its pivot.
                    local mo = item.motion
                    if type(mo) == "table" and type(mo.keys) == "table" and #mo.keys >= 2
                        and type(mo.pivot_cm) == "table" and (tonumber(mo.period) or 0) > 0 then
                        local l = actor:K2_GetActorLocation()
                        local m = {
                            actor = actor, rest = { l.X, l.Y, l.Z }, period = mo.period, keys = mo.keys,
                            pivot = { l.X + mo.pivot_cm[1], l.Y + mo.pivot_cm[2], l.Z + mo.pivot_cm[3] },
                            loc = { X = 0, Y = 0, Z = 0 }, rot = { Pitch = 0, Yaw = 0, Roll = 0 }, events = {},
                        }
                        -- Paths, not waves or attenuation objects: nothing in the
                        -- engine holds what Lua alone made or loaded, and the
                        -- garbage collector freed them under the next play (a
                        -- null access 41 s into Ascension). Each is made as it
                        -- plays, and the sound holds it.
                        for _, e in ipairs(type(mo.events) == "table" and mo.events or {}) do
                            if type(e.wave) == "string" and type(e.t) == "number" and resolveMesh(e.wave) then
                                m.events[#m.events + 1] = { t = e.t, wave = e.wave, gain = e.gain or 1.0,
                                    inner = e.inner or 150.0, falloff = e.falloff or 600.0 }
                            end
                        end
                        m.at = { X = m.pivot[1], Y = m.pivot[2], Z = m.pivot[3] }
                        -- A turn about another axis than +Z (Zanzibar's wheels):
                        -- its unit vector, the keys' degrees about it.
                        if type(mo.axis) == "table" and #mo.axis == 3 then
                            m.axis = { X = mo.axis[1], Y = mo.axis[2], Z = mo.axis[3] }
                        end
                        -- A machine of the simulation's own turns its collision
                        -- (follow: the Blueprint class the game draws it with,
                        -- its position from the canvas origin): the mesh rides
                        -- on that actor's turning part instead of the clock.
                        local f = mo.follow
                        if type(f) == "table" and type(f.class) == "string" and type(f.pos) == "table" then
                            m.follow = { class = f.class, pos = { origin[1] + f.pos[1], origin[2] + f.pos[2], origin[3] + f.pos[3] } }
                            m.entry = mo.entry
                        end
                        Current.turning[#Current.turning + 1] = m
                    end
                else
                    Current.failed = Current.failed + 1
                    Log(string.format("decor '%s': %s", tostring(id), tostring(err)))
                end
            end
            spawnedMs = spawnedMs + (os.clock() - itemAt)
        end, function(item, index, err)
            Log(string.format("decor '%s': %s", tostring(type(item) == "table" and item.id or ("#" .. index)),
                tostring(err)))
        end))
        -- What the spawned pieces handed on: their materials, a slot a job.
        step("decor materials", Current.dressQueue.step)
        step("decor done", function()
            -- The world's pieces are dressed: their handles go.
            baked = {}
            if Current.meshScan then Current.meshScan.decor = {} end
            Log(string.format("level '%s': %d decor spawned, %d failed%s",
                tostring(level.name), Current.spawned, Current.failed,
                nBaked > 0 and string.format(", %d baked in the world", nBaked) or ""))
            Log(string.format("load timing: decor %.0f ms on %d baked piece(s), %.0f ms on %d spawned",
                bakedMs * 1000, nBaked, spawnedMs * 1000, #decor - nBaked))
        end)
        if type(level.slot_meshes) == "table" then
            step("slot meshes", function()
                local sok, sn = pcall(Land.slotMeshes, world, level)
                Log("slot meshes: " .. tostring(sok and sn or sn))
            end)
        end
        step("terrain shadow proxy", function()
            if proxyWanted() then
                Log(string.format("terrain shadow proxy: %d spawned", applyShadowProxies(world)))
            end
        end)
        step("sun mask", function()
            if TerrainLights.on then
                local ok, done, err = pcall(applySunMask, world)
                Log("sun mask: " .. tostring(ok and (done or err) or done))
            end
        end)
        -- An error in one of these is logged under its name ("water: ...")
        -- and the next step runs, as each ran under its own pcall.
        step("water", function() applyWater(world) end)
        step("foliage", function()
            Foliage.spawn(world)
            -- The rocks went to Foliage.cliffGroups (Land.cliffs).
            Current.meshScan = nil
        end, true)
        -- What the foliage handed on: its baked meshes' dressing.
        step("foliage meshes", Current.dressQueue.step)
        step("effects", function() Effects.spawn(world) end)
        step("waterfalls", function() Effects.waterfalls(world) end)
        step("flux", function() Effects.flux(world) end, true)
        step("lights", function() Placed.lights(world) end)
        step("decals", function() Placed.decals(world) end)
        step("landscape", function() Land.apply(world) end, true)
        -- What the landscape handed on: its ground, cliffs and components,
        -- then the cladding rocks' material.
        step("landscape jobs", Current.dressQueue.step)
        step("deformation", function() Footprints.deformStart(world) end, true)
        -- What it handed on: the vehicles and bipeds whose brushes it registers.
        step("deformation jobs", Current.dressQueue.step)
        step("sky recapture", function() Current.recaptureSkyAfterDecor(world) end)
    end
    -- The load's garbage (the level file's text, thousands of handles),
    -- collected now, behind the loading screen, not in a match minutes on:
    -- two full collections, as a finalized UE4SS handle survives one
    -- (docs/performance.md), a frame each, then back to generational.
    step("collect", function() collectgarbage("collect") end, true)
    step("collect again", function()
        collectgarbage("collect")
        pcall(collectgarbage, "generational", 5, 100)
    end, true)
    Dress.run(steps, {
        defer = function(fn) ExecuteInGameThreadWithDelay(1, fn) end,
        alive = function() return Current.dressGen == gen and Current.level == level and world:IsValid() end,
        onError = function(name, err) Log(name .. ": " .. tostring(err)) end,
        onFrame = function(started, took, names)
            Current.reportWork("load", started, took)
            -- A frame the load could not cut finer, named.
            if took >= 0.03 then
                Log(string.format("load timing: a frame of %.0f ms (%s)", took * 1000, table.concat(names, " + ")))
            end
        end,
        onDone = function(stats)
            Current.dressing = false
            Current.furnished = true
            Current.meshScan = nil
            Current.dressQueue = nil
            Current.lapDone(string.format(" over %d frame(s), %.0f ms of it ours, the longest frame's share %.0f ms (%s), "
                .. "the shortest gap between frames %.1f ms", stats.frames, stats.busy * 1000, stats.longest * 1000,
                stats.longestSteps, (stats.minGap or 0) * 1000))
            Current.tryFade()
        end,
    })
end

--------------------------------------------------------------------------------
-- Watcher: spot the canvas world, furnish it, fade in once the player exists
--------------------------------------------------------------------------------

local function tick()
    local world = getWorld()
    if not world then return end

    local worldName = world:GetFullName()
    if worldName ~= Current.worldName then
        -- A new world: drop stale handles, look for a level file.
        resetState()
        EventWaves = {}
        SilentIncidents = {}
        -- Nothing queued on the old map plays in the new world, and which
        -- incidents arrive natively is learnt again: a player who hosted
        -- earlier had every name marked native and, as a client, dropped
        -- every relayed sound.
        EventQueue = {}
        NativeIncidents = {}
        Resolved, Unresolved = {}, {}
        BreakQueue = {}
        Current.worldName = worldName
        -- The seamless-travel transition world still answers with the
        -- scenario it is leaving; dressing it spawned the old map's terrain
        -- into the fade back to the menu at game end. Its name is
        -- /Game/Levels/Test/SeamlessTravelTEst: compare case-blind (a
        -- case-sensitive test missed it, and every return to the menu spent
        -- seconds dressing it).
        if string.upper(worldName):find("SEAMLESSTRAVEL", 1, true) then return end
        Current.lapStart()
        Current.scenario = scenarioOf(world)
        if not Current.scenario then return end
        -- The menu has no level. The match is over, so the file that tells
        -- other mods a match runs goes: only the next switch removed it, so
        -- a host back at the menu still had one, and a FIND GAMES join to
        -- the same map was taken as already switched.
        if Current.scenario == "FRONTEND" then
            os.remove(MOD_DIR .. "\\running.txt")
            return
        end

        local level, err = loadCurrentLevelFile(Current.scenario)
        Current.lap("level file")
        if not level then
            Current.laps = nil
            Current.fileMissing = true
            if err and not err:find("^no file") then
                Log("level file for " .. Current.scenario .. ": " .. err)
            end
            return
        end
        Current.level = level
        Log(string.format("world %s has level '%s'", Current.scenario, tostring(level.name)))
        hookIncidents()
        Current.lap("incident hooks")
    end

    -- Terrain and sky need only the world, so they are in place behind the
    -- loading screen; waiting for the player left converted maps black for
    -- 20-30 s after it. The dressing runs over the next frames (spawnDecor)
    -- and fades in when it is done; this pass fades in a dressed world
    -- whose player came later.
    if Current.level and not Current.furnished and not Current.dressing then
        spawnDecor(world)
    end
    hookBreakables()
    Current.tryFade()
end

-- The Lua collector in generational mode. Incremental, it let ~40 MB of
-- garbage pile up between cycles, and finishing one (sweeping it, and
-- running the finalizers of the thousands of object handles UE4SS hands
-- out) landed in a single step: whichever loop allocated next held the game
-- thread 30-200 ms, the pulses most often, being the most frequent (MJOLNIRHud
-- hitch log, 2026-10-18). A smaller step size made it worse: the heap ran to
-- 230 MB and the step that finished the cycle took 205 ms. Generational, a
-- young collection takes only what was made since the last. At the default
-- 20% of the heap that was ~3.5 MB, an 11 ms run every ~97 s; at 5% it is a
-- quarter of that, four times as often. UE4SS ships Lua 5.4.7, whose
-- generational mode is sound.
pcall(collectgarbage, "generational", 5, 100)

--- Run `fn` on the game thread every `ms`, from the game thread: each run
--- schedules the next. An async loop that hands work to the game thread
--- (LoopAsync + ExecuteInGameThread) can deadlock UE4SS, the async thread
--- holding the mod's Lua lock while it queues, the game thread holding the
--- queue while it waits for the lock; at 0.1 s and 0.3 s it froze the game
--- within minutes (2026-10-01).
---
--- A run that holds the game thread past 50 ms is logged with its name (at
--- most once every 30 s per loop): a CTF host froze ~250 ms every 3.24 s in
--- Lua, and nothing said which loop (playtest, 2026-10-03).
---
--- Each run that reads a millisecond or more is also handed to MJOLNIRHud's
--- hitch log (its Scripts/hitches.lua), through a UE4SS shared variable, so
--- a long frame there names the loops that ran in it.
---
--- With `paced`, `fn` returns how long to wait before its next run, in ms
--- (`ms` when it returns nothing or fails): the flag cloth runs at 30 Hz
--- only while a flag moves on screen.
local function every(ms, name, fn, paced)
    local reportedAt = -100
    local function run()
        local started = os.clock()
        local ok, err = pcall(fn)
        if not ok then Log(name .. " error: " .. tostring(err)) end
        local wait = paced and ok and type(err) == "number" and err > 0 and err or ms
        local took = os.clock() - started
        Current.reportWork(name, started, took)
        if took > 0.05 and started - reportedAt > 30 then
            reportedAt = started
            Log(string.format("slow: the %s loop held the game thread %.0f ms", name, took * 1000))
        end
        ExecuteInGameThreadWithDelay(wait, run)
    end
    ExecuteInGameThreadWithDelay(ms, run)
end

--- CE's periodic functions, 0..1, as the shaders evaluate them
--- (build_ce_materials.py WAVE): one, zero, cosine, diagonal wave, slide,
--- and a smooth stand-in for the noise family.
local function ceWave(fn, x)
    if fn < 0.5 then return 1.0 elseif fn < 1.5 then return 0.0
    elseif fn < 3.5 then return 0.5 - 0.5 * math.cos(2 * math.pi * x)
    elseif fn < 5.5 then return 1.0 - math.abs(2.0 * (x % 1.0) - 1.0)
    elseif fn < 7.5 then return x % 1.0
    end
    return 0.5 + 0.5 * math.sin(2 * math.pi * x) * math.sin(5.1 * x)
end

local KismetSystem = nil

--- Every pulsing decor material, at the game's time. 25 times a second
--- with Death Island's 25 flares, so nothing here may leave garbage: a
--- getWorld() and a method lookup a flare made ~8 KB a run, 200 KB a
--- second, and the collections that bought cost 30-150 ms runs (MJOLNIRHud
--- hitch log, 2026-10-18).
local function updatePulses()
    if #Current.pulses == 0 then return end
    local world = Current.world
    if not (world and world:IsValid()) then return end
    KismetSystem = KismetSystem or StaticFindObject("/Script/Engine.Default__KismetSystemLibrary")
    local t = KismetSystem:GetGameTimeInSeconds(world)
    for _, p in ipairs(Current.pulses) do
        if p.mid:IsValid() then
            p.set(p.mid, p.param, p.base * ceWave(p.fn, t / p.period))
        end
    end
end

local function watch()
    every(1500, "tick", tick)
    -- A 1 s cosine needs ~25 updates a second to read as smooth.
    every(40, "pulses", updatePulses)
    -- Event sounds wait at most a tenth of a second (respawn ticks are a
    -- second apart).
    every(100, "event sounds", drainEvents)
    every(100, "weather", updateWeather)
    every(100, "footprints", Footprints.tick)
    every(100, "dry zones", Effects.dryTick)
    -- A slider moved in the pause menu is heard within half a second.
    every(500, "sound volume", syncVolumes)
    -- CTF flags: new flag actors are dressed as they are made, and a slow
    -- sweep (every other pass) takes in any the watch missed and reads each
    -- flag's team again. Team armour is tinted on the game's own events; a
    -- pass checks the Spartans for a tint undone. Both in teams.lua, which
    -- checks for a CTF level or a team game itself.
    every(1500, "CTF flags", Teams.flagTick)
    -- The flags' cloth waves, and trails behind a carrier: 30 times a second
    -- while a flag moves on screen, 15 at rest, once a second without flags
    -- (teams.lua CLOTH_MS).
    every(33, "flag cloth", Teams.clothTick, true)
    every(1500, "team armour", Teams.armorTick)
    -- A player below the map's kill floor dies (kill_floor.lua; host only).
    every(500, "kill floor", function() if Teams.KillFloor then Teams.KillFloor.tick() end end)
    -- Halo 2's lifts push this game's own players (lifts.lua).
    every(500, "lifts", function() if Teams.Lifts then Teams.Lifts.tick() end end)
    -- A CE map's gates and shields ride their machines (devices.lua), once
    -- the world is dressed: a device binds only once its decor is spawned,
    -- and the dressing spawns it over several frames (spawnDecor).
    every(250, "devices", function() if Teams.Devices and Current.furnished then Teams.Devices.tick() end end)
    -- A converted vehicle's own sounds (vehicle_sounds.lua).
    every(100, "vehicle sounds", function() if Teams.VehicleSounds then Teams.VehicleSounds.tick() end end)
    -- Health packs: new pack actors are reported as they are made
    -- (watchHealthPacks); the first ones can come before the watch does, so
    -- the pass that arms it sweeps for them too, once: a FindAllOf is a
    -- 20 ms frame on a converted map.
    -- Sounds on moving machine parts follow them: p = frac(t / period +
    -- position) on the world's clock (the materials' Time), a held position
    -- when the period is 0, as the CE device masters' World Position Offset
    -- (build_ce_materials.py DEVICE_WPO_CODE).
    every(100, "moving sounds", function()
        if #Current.movingSounds == 0 then return end
        local world = Current.world
        if not (world and world:IsValid()) then return end
        -- The world's time (as GameplayStatics' GetTimeSeconds), through
        -- the library pulses keep: a StaticFindObject a run cost ~1 ms.
        KismetSystem = KismetSystem or StaticFindObject("/Script/Engine.Default__KismetSystemLibrary")
        local now = KismetSystem:GetGameTimeInSeconds(world)
        for _, m in ipairs(Current.movingSounds) do
            if m.comp:IsValid() then
                local p = m.period > 0 and ((now / m.period + m.position) % 1.0) or m.position
                local sc = m.s0 + (m.s1 - m.s0) * p
                local at = m.at or {}
                m.at = at
                local moved = false
                for k = 1, 3 do
                    local v = m.pos[k] + (m.pos[k] - m.pivot[k]) * (sc - 1) + m.t0[k] + (m.t1[k] - m.t0[k]) * p
                    if at[k] == nil or math.abs(v - at[k]) > 1 then at[k], moved = v, true end
                end
                -- A held part (period 0) is placed once.
                if moved then
                    m.comp:K2_SetWorldLocation({ X = at[1], Y = at[2], Z = at[3] }, false, Current.emptyHit(), false)
                end
            end
        end
    end)
    -- Turning machines (Halo 2 gears: Ascension's antennas), on the world's
    -- clock from the level's load, as the game runs a gear's position from
    -- it: the yaw between the keys at t mod period, the actor swung about
    -- its pivot to it. Its tables are its own, refilled: nothing per run.
    every(33, "turning machines", function()
        -- Once the world is dressed: its machines are spawned over frames.
        if #Current.turning == 0 or not Current.furnished then return end
        local world = Current.world
        if not (world and world:IsValid()) then return end
        KismetSystem = KismetSystem or StaticFindObject("/Script/Engine.Default__KismetSystemLibrary")
        local now = KismetSystem:GetGameTimeInSeconds(world)
        local gs, scans = nil, nil
        for _, m in ipairs(Current.turning) do
            -- A machine of the simulation's own turns the part's collision
            -- (follow): its Unreal actor is found (a FindAllOf every 2 s
            -- until it is; the mesh turns by the clock meanwhile), the mesh
            -- posed at the machine's present angle and attached to the part
            -- that turns, whose own mesh is hidden. The angle about the
            -- axis comes from a vector of the actor's frame and the same of
            -- the part's; the turn's phase, for the sounds, is fitted to
            -- what the part does, as the simulation runs its gears from its
            -- own clock.
            local function partAngle()
                local k = m.axis or { X = 0, Y = 0, Z = 1 }
                local a, b = m.base:GetActorForwardVector(), m.part:GetForwardVector()
                if math.abs(a.X * k.X + a.Y * k.Y + a.Z * k.Z) > 0.9 then
                    a, b = m.base:GetActorUpVector(), m.part:GetUpVector()
                end
                local ak, bk = a.X * k.X + a.Y * k.Y + a.Z * k.Z, b.X * k.X + b.Y * k.Y + b.Z * k.Z
                local cross = k.X * (a.Y * b.Z - a.Z * b.Y) + k.Y * (a.Z * b.X - a.X * b.Z) + k.Z * (a.X * b.Y - a.Y * b.X)
                return math.deg(math.atan(cross, a.X * b.X + a.Y * b.Y + a.Z * b.Z - ak * bk))
            end
            if m.actor:IsValid() and m.follow and not m.attached then
                if not m.seek or now - m.seek > 2 then
                    m.seek = now
                    -- One actor a part: parts placed together (Zanzibar's
                    -- wheel and its blades) each claim their own, and a
                    -- part's meshes (its opaque and translucent ones, by
                    -- their staging entry) share it.
                    -- One scan a class a run, shared: each is ~20 ms.
                    Current.claimed = Current.claimed or {}
                    scans = scans or {}
                    scans[m.follow.class] = scans[m.follow.class] or FindAllOf(m.follow.class) or {}
                    pcall(function()
                        for _, a in ipairs(scans[m.follow.class]) do
                            local l = a:K2_GetActorLocation()
                            local d = math.abs(l.X - m.follow.pos[1]) + math.abs(l.Y - m.follow.pos[2]) + math.abs(l.Z - m.follow.pos[3])
                            local key = a:GetFullName()
                            local owner = Current.claimed[key]
                            if d < 30 and (not owner or (m.entry ~= nil and owner == m.entry)) then
                                Current.claimed[key] = m.entry or true
                                m.base = a
                                m.part = a:K2_GetComponentsByClass(StaticFindObject("/Script/Engine.StaticMeshComponent"))[1]:get()
                                m.pose = partAngle()
                                break
                            end
                        end
                    end)
                end
            elseif m.actor:IsValid() and m.attached and not m.offset and m.part:IsValid() then
                local h = m.hist
                local rel = partAngle()
                h[#h + 1] = { now, rel }
                local lo, hi = rel, rel
                for _, sm in ipairs(h) do lo, hi = math.min(lo, sm[2]), math.max(hi, sm[2]) end
                if now - h[1][1] > 8 and hi - lo > 5 then
                    local function at(t)
                        local keys = m.keys
                        for k = 2, #keys do
                            if t <= keys[k][1] then
                                local a, b = keys[k - 1], keys[k]
                                return b[1] > a[1] and (a[2] + (b[2] - a[2]) * (t - a[1]) / (b[1] - a[1])) or b[2]
                            end
                        end
                        return keys[#keys][2]
                    end
                    local best, bestCost = 0, math.huge
                    for o = 0, m.period, 0.1 do
                        local cost = 0
                        for i = 1, #h, 3 do
                            local e = (at((h[i][1] - o) % m.period) - h[i][2] + 540) % 360 - 180
                            cost = cost + e * e
                        end
                        if cost < bestCost then best, bestCost = o, cost end
                    end
                    m.offset, m.hist = best, nil
                    Log(string.format("turning machine phase: %.1f s from the world clock", best))
                elseif #h > 600 then
                    table.remove(h, 1)
                end
            end
            if m.actor:IsValid() then
                local t = (now - (m.offset or 0)) % m.period
                -- Its sounds whose time the turn passed since the last
                -- run (across the wrap too); none on the first.
                local last = m.last
                m.last = t
                for _, e in ipairs(last and (not m.follow or m.offset) and m.events or {}) do
                    if (last < t and e.t > last and e.t <= t) or (t < last and (e.t > last or e.t <= t)) then
                        gs = gs or findObject("/Script/Engine.Default__GameplayStatics")
                        pcall(function()
                            local wave = resolveMesh(e.wave)
                            if not wave then return end
                            -- The class is native and never collected; a
                            -- StaticFindObject a play would be ~20 ms.
                            Current.attClass = Current.attClass or findObject("/Script/Engine.SoundAttenuation")
                            Current.machineSounds = (Current.machineSounds or 0) + 1
                            local att = StaticConstructObject(Current.attClass, world,
                                FName("MJOLNIR_MachAtt_" .. Current.machineSounds))
                            local a = att.Attenuation
                            a.bAttenuate = true
                            a.bSpatialize = true
                            a.DistanceAlgorithm = 0
                            a.AttenuationShape = 0
                            a.AttenuationShapeExtents = { X = e.inner, Y = 0, Z = 0 }
                            a.FalloffDistance = e.falloff
                            gs:SpawnSoundAtLocation(world, wave, m.at, m.rot, e.gain * gameVolume("ambient"),
                                1.0, 0.0, att, nil, true)
                        end)
                    end
                end
                local keys, yaw = m.keys, m.keys[#m.keys][2]
                for k = 2, #keys do
                    if t <= keys[k][1] then
                        local a, b = keys[k - 1], keys[k]
                        local span = b[1] - a[1]
                        yaw = span > 0 and (a[2] + (b[2] - a[2]) * (t - a[1]) / span) or b[2]
                        break
                    end
                end
                -- A ridden mesh moves with the machine, not here; one just
                -- found is posed at the machine's angle first.
                if m.attached then
                    yaw = m.yaw
                elseif m.pose then
                    yaw, m.yaw = m.pose, nil
                end
                if yaw ~= m.yaw and m.axis then
                    -- About its axis k: the rest offset turned by Rodrigues'
                    -- formula, the actor's rotation from the axis and angle.
                    m.yaw = yaw
                    local r = math.rad(yaw)
                    local c, sn = math.cos(r), math.sin(r)
                    local k = m.axis
                    local vx, vy, vz = m.rest[1] - m.pivot[1], m.rest[2] - m.pivot[2], m.rest[3] - m.pivot[3]
                    local kv = (k.X * vx + k.Y * vy + k.Z * vz) * (1 - c)
                    m.loc.X = m.pivot[1] + vx * c + (k.Y * vz - k.Z * vy) * sn + k.X * kv
                    m.loc.Y = m.pivot[2] + vy * c + (k.Z * vx - k.X * vz) * sn + k.Y * kv
                    m.loc.Z = m.pivot[3] + vz * c + (k.X * vy - k.Y * vx) * sn + k.Z * kv
                    Current.mathLib = Current.mathLib or StaticFindObject("/Script/Engine.Default__KismetMathLibrary")
                    local ro = Current.mathLib:RotatorFromAxisAndAngle(k, yaw)
                    m.rot.Pitch, m.rot.Yaw, m.rot.Roll = ro.Pitch, ro.Yaw, ro.Roll
                    m.actor:K2_SetActorLocationAndRotation(m.loc, m.rot, false, Current.emptyHit(), false)
                elseif yaw ~= m.yaw then
                    m.yaw = yaw
                    local r = math.rad(yaw)
                    local c, sn = math.cos(r), math.sin(r)
                    local dx, dy = m.rest[1] - m.pivot[1], m.rest[2] - m.pivot[2]
                    m.loc.X = m.pivot[1] + dx * c - dy * sn
                    m.loc.Y = m.pivot[2] + dx * sn + dy * c
                    m.loc.Z = m.rest[3]
                    m.rot.Yaw = yaw
                    m.actor:K2_SetActorLocationAndRotation(m.loc, m.rot, false, Current.emptyHit(), false)
                end
                if m.pose and m.part and m.part:IsValid() then
                    pcall(function()
                        m.actor:K2_AttachToComponent(m.part, FName("None"), 1, 1, 1, true)
                        m.part:SetVisibility(false, false)
                    end)
                    m.attached, m.pose, m.hist = true, nil, {}
                    -- No sounds, nothing to fit the phase for (a wheel that
                    -- turns evenly has no landmark to fit it to anyway).
                    if #m.events == 0 then m.offset, m.hist = 0, nil end
                    Log(string.format("turning machine rides the simulation's %s", m.follow.class))
                end
            end
        end
    end)
    local packSweeps = 0
    every(1500, "health packs", function()
        local hp = Current.furnished and healthPackLevel()
        if not hp then return end
        watchHealthPacks()
        if packSweeps >= 1 then return end
        packSweeps = packSweeps + 1
        local world = getWorld()
        for _, actor in ipairs(world and FindAllOf("BP_Battle_Rifle_ammo_EquipmentActor_C") or {}) do
            pcall(dressHealthPack, world, actor, hp)
        end
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
        if Current.water then
            Log("water: " .. Current.water.style .. (Current.water.slots and string.format(" (%d slot(s))", Current.water.slots) or ""))
        end
        pcall(Teams.status)
    else
        Log("no level loaded")
    end
    -- The live heap: two full collections, as a finalized UE4SS handle
    -- survives one (docs/performance.md). Then back to generational.
    local held = 0
    for _ in pairs(Current.actors or {}) do held = held + 1 end
    local before = collectgarbage("count")
    collectgarbage("collect")
    collectgarbage("collect")
    Log(string.format("lua heap: %.1f MB live (%.1f MB before collecting), %d actor handle(s) held",
        collectgarbage("count") / 1024, before / 1024, held))
    pcall(collectgarbage, "generational", 5, 100)
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
    if world then
        Current.lapStart()
        spawnDecor(world)
    end
end

--- `mjolnir_terrain_shadows [on|off] [strength]`: see TerrainShadows. No
--- argument reports the setting; a strength alone keeps the cast setting;
--- `off` alone puts the level's own strength back.
--- `mjolnir_terrain_shadows lightmap [shadow sunlit]` respawns the level
--- with the lightmap levels (the level's own when not given), the terrain
--- still casting nothing unless `on` says so; `off` undoes that too.
--- `mjolnir_terrain_shadows proxy [off]` adds (removes) the terrain's hidden
--- shadow copy (spawnShadowProxy); `off` removes it too.
--- `mjolnir_terrain_shadows ao <strength>` sets the baked corners' strength
--- (runtimeMaterial's Bake) on the terrain as it stands.
local function terrainShadows(args)
    args = args or {}
    local mode, value = args[1], tonumber(args[2])
    local hadLightmap = TerrainShadows.lightmap ~= nil
    if mode == "ao" then
        -- The baked corners' strength (BakeAO, a power: 0 none, 1 as baked).
        local param = "BakeAO"
        local amount = math.max(0.0, value or 1.0)
        TerrainShadows.ao = amount
        local n = 0
        for _, item in ipairs(Current.level and Current.level.decor or {}) do
            local actor = isTerrain(item) and Current.actors[item.id]
            if actor and actor:IsValid() then
                pcall(function()
                    local comp = actor.StaticMeshComponent
                    local count = math.max(comp:GetNumMaterials(), comp.OverrideMaterials:GetArrayNum())
                    for i = 0, count - 1 do
                        local mid = comp:GetMaterial(i)
                        -- One at a time: a slot holding a shipped (constant)
                        -- material cannot take the parameter, and on Blood
                        -- Gulch slot 0 does, which stopped the whole terrain.
                        if mid and mid:IsValid() and pcall(function()
                            mid:SetScalarParameterValue(FName(param), amount)
                        end) then
                            n = n + 1
                        end
                    end
                end)
            end
        end
        Log(string.format("baked corners: strength %.2f on %d material(s)", amount, n))
        return
    end
    if mode == "proxy" or mode == "off" then
        TerrainShadows.proxy = mode == "proxy" and args[2] ~= "off"
        local world = getWorld()
        local n = world and applyShadowProxies(world) or 0
        Log(string.format("terrain shadow proxy %s (%d)", TerrainShadows.proxy and "ON" or "off", n))
        if mode == "proxy" then return end
    end
    if mode == "lightmap" then
        local shadow, sunlit = tonumber(args[2]), tonumber(args[3])
        TerrainShadows.lightmap = nil
        local levels = (shadow and sunlit) and { shadow, sunlit } or lightmapSun()
        if not levels or levels[2] <= levels[1] then
            Log("usage: mjolnir_terrain_shadows lightmap <shadow> <sunlit> (this level names none)")
            return
        end
        TerrainShadows.lightmap = levels
        if not resolveMesh(TRIAL_MASTERS .. "M_CE_Environment.M_CE_Environment") then
            Log("lightmap: trial masters (" .. TRIAL_MASTERS .. ", chunk 983) not installed; the shipped masters ignore LightmapSun")
        end
        Log(string.format("lightmap: shadow %.3f, sunlit %.3f; respawning the level", levels[1], levels[2]))
        reload()
        return
    end
    if mode == "on" or mode == "off" then
        TerrainShadows.cast = mode == "on"
        if mode == "off" and not value then TerrainShadows.strength = nil end
        if mode == "off" and hadLightmap then
            TerrainShadows.lightmap = nil
            Log("lightmap: off; respawning the level")
            reload()
            return
        end
    elseif tonumber(mode) then
        value = tonumber(mode)
    elseif mode ~= nil then
        Log("usage: mjolnir_terrain_shadows [on|off] [strength 0..1]")
        return
    end
    if value then TerrainShadows.strength = math.max(0.0, math.min(1.0, value)) end
    local n = 0
    for _, item in ipairs(Current.level and Current.level.decor or {}) do
        local actor = isTerrain(item) and Current.actors[item.id]
        if actor and actor:IsValid() then
            local ok, err = pcall(applyTerrainShadows, actor)
            if ok then n = n + 1 else Log("terrain shadows on '" .. item.id .. "': " .. tostring(err)) end
        end
    end
    Log(string.format("terrain shadows %s, strength %s, %d terrain mesh(es) updated",
        TerrainShadows.cast and "ON" or "off", tostring(terrainShadowStrength()), n))
end

--- `mjolnir_light_scale [k|default]`: see lightScale. Sets the scale on the
--- level as it stands and on every level loaded later, until the game closes
--- (`default` hands it back to the level file). No argument reports it.
local function setLightScale(args)
    local arg = args and args[1]
    if arg == "default" then
        LightScale.value = nil
    elseif tonumber(arg) and tonumber(arg) > 0 then
        LightScale.value = tonumber(arg)
    elseif arg ~= nil then
        Log("usage: mjolnir_light_scale [k > 0 | default]")
        return
    end
    local k = lightScale()
    local env = Current.level and Current.level.environment
    if arg == nil or type(env) ~= "table" then
        Log(string.format("light scale %g%s", k, LightScale.value and " (set by command)" or ""))
        return
    end
    local function actor(key)
        local a = Current.actors[key]
        return a and a:IsValid() and a or nil
    end
    local sun, sky, post = actor("__sun"), actor("__sky"), actor("__post")
    local sunEnv, skyEnv = env.sun or {}, env.skylight or {}
    if sun then pcall(function() sun.LightComponent:SetIntensity((sunEnv.intensity or 8.0) * k) end) end
    if sky then pcall(function() sky.LightComponent:SetIntensity((skyEnv.intensity or 3.0) * (skyEnv.physical and 1 or k)) end) end
    for i, l in ipairs(type(Current.level.lights) == "table" and Current.level.lights or {}) do
        local a = actor("__light_" .. i)
        if a then pcall(function() a.LightComponent:SetIntensity((tonumber(l.intensity) or 25) * k) end) end
    end
    if post then
        pcall(function()
            local s = post.Settings
            s.bOverride_AutoExposureBias = true
            s.AutoExposureBias = ((env.post or {}).exposure_bias or 0.0) - math.log(k, 2)
        end)
    end
    local n = 0
    for _, mid in ipairs(Current.sunMids) do
        if mid:IsValid() and pcall(function() mid:SetScalarParameterValue(FName("SunIlluminance"), sunIlluminance(sunEnv)) end) then
            n = n + 1
        end
    end
    Log(string.format("light scale %g (exposure bias %.2f), %d CE material(s) updated", k, -math.log(k, 2), n))
end

--- `mjolnir_terrain_debug [layer]`: the terrain's debug view (the CE
--- environment masters' DebugView, build_ce_materials.py DEBUG_CODE), one
--- layer of its light at a time, by number or name; `off` or no argument
--- goes back. Needs the trial masters (the level as `mjolnir_terrain_lights
--- on` or `mjolnir_terrain_shadows lightmap` draws it).
local DEBUG_LAYERS = {
    off = 0, lightmap = 1, corners = 2, sky = 3, sunvis = 4, mask = 5, sunshare = 6,
    topup = 7, base = 8, charts = 9, unreal = 10, ce = 11,
}

local function terrainDebug(args)
    local arg = args and args[1] or "off"
    local layer = tonumber(arg) or DEBUG_LAYERS[string.lower(arg)]
    if not layer then
        local names = {}
        for name, n in pairs(DEBUG_LAYERS) do names[#names + 1] = string.format("%d %s", n, name) end
        table.sort(names, function(a, b) return tonumber(a:match("^%d+")) < tonumber(b:match("^%d+")) end)
        Log("usage: mjolnir_terrain_debug <layer>: " .. table.concat(names, ", "))
        return
    end
    local n = 0
    for _, mid in ipairs(Current.sunMids) do
        if mid:IsValid() and pcall(function() mid:SetScalarParameterValue(FName("DebugView"), layer) end) then
            n = n + 1
        end
    end
    Log(string.format("terrain debug view %d on %d material(s)", layer, n))
end

--- `mjolnir_foliage [on|off]`: see Foliage.spawn; respawns the level.
function Foliage.command(args)
    local mode = args and args[1]
    if mode == "on" or mode == "off" then
        Foliage.on = mode == "on"
        reload()
    end
    Log("foliage: " .. (Foliage.on and "on" or "off"))
end

--- `mjolnir_effects [on|off]`: see Effects.spawn; respawns the level.
function Effects.command(args)
    local mode = args and args[1]
    if mode == "on" or mode == "off" then
        Effects.on = mode == "on"
        reload()
    end
    Log("effects: " .. (Effects.on and "on" or "off"))
end

--- `mjolnir_terrain_detail [game|ce] | param <Name> <value>`: see GameDetail.
--- `game`/`ce` respawn the level (the masters change), as does a param. No
--- argument reports it.
local function terrainDetail(args)
    args = args or {}
    local mode = args[1]
    if mode == "game" or mode == "ce" then
        GameDetail.on = mode == "game"
        if GameDetail.on and not resolveMesh(TRIAL_MASTERS .. "M_CE_Environment.M_CE_Environment") then
            Log("terrain detail: trial masters (" .. TRIAL_MASTERS .. ", chunk 983) not installed")
        end
    elseif mode == "param" and args[2] and tonumber(args[3]) then
        GameDetail.params[args[2]] = tonumber(args[3])
    elseif mode ~= nil then
        Log("usage: mjolnir_terrain_detail [game|ce] | param <Name> <value>")
        return
    end
    local params = {}
    for k, v in pairs(GameDetail.params) do params[#params + 1] = string.format("%s %g", k, v) end
    Log(string.format("terrain detail: %s%s", GameDetail.on and "game" or "ce",
        #params > 0 and (" (" .. table.concat(params, ", ") .. ")") or ""))
    if mode ~= nil then reload() end
end

--- `mjolnir_terrain_lights [on|off] [albedo] [noproxy]`: see TerrainLights.
--- `on`/`off` respawn the level (the masters change); an albedo alone sets
--- DynamicAlbedo on the materials as they stand, `margin <texels>` their
--- BakeMargin. No argument reports it.
local function terrainLights(args)
    args = args or {}
    local mode = args[1]
    local value = tonumber(args[2]) or tonumber(mode)
    if mode == "param" and args[2] and tonumber(args[3]) then
        -- Any scalar of the CE environment masters, on the level as it
        -- stands and on every level loaded later (AlbedoGain, AmbientGain...).
        TerrainLights.params = TerrainLights.params or {}
        TerrainLights.params[args[2]] = tonumber(args[3])
        local n = 0
        for _, mid in ipairs(Current.sunMids) do
            if mid:IsValid() and pcall(function() mid:SetScalarParameterValue(FName(args[2]), tonumber(args[3])) end) then
                n = n + 1
            end
        end
        Log(string.format("terrain lights: %s %g on %d material(s)", args[2], tonumber(args[3]), n))
        return
    end
    if mode == "margin" and tonumber(args[2]) then
        TerrainLights.margin = math.max(0.0, tonumber(args[2]))
        local n = 0
        for _, mid in ipairs(Current.sunMids) do
            if mid:IsValid() and pcall(function() mid:SetScalarParameterValue(FName("BakeMargin"), TerrainLights.margin) end) then
                n = n + 1
            end
        end
        Log(string.format("terrain lights: margin %.2f texel(s) on %d material(s)", TerrainLights.margin, n))
        return
    end
    if mode == "on" or mode == "off" then
        TerrainLights.on = mode == "on"
        local function has(word) return args[2] == word or args[3] == word or args[4] == word end
        TerrainLights.proxy = not has("noproxy")
        TerrainLights.fill = has("fill")
        TerrainLights.unreal = not has("hybrid")
        TerrainLights.trial = has("trial")
        -- A trial runs on the bake in bake\ beside this mod, loaded in the
        -- same respawn. An indoor level names no lightmap levels: {0, 0}
        -- still loads the bake, and the masters read it as "no sun levels".
        if TerrainLights.on and TerrainLights.trial and not TerrainShadows.lightmap then
            TerrainShadows.lightmap = lightmapSun() or { 0, 0 }
        end
        if TerrainLights.on and not value then TerrainLights.albedo = 1.0 end
        if value then TerrainLights.albedo = math.max(0.0, value) end
        if TerrainLights.trial and not resolveMesh(TRIAL_MASTERS .. "M_CE_Environment.M_CE_Environment") then
            Log("terrain lights: trial masters (" .. TRIAL_MASTERS .. ", chunk 983) not installed")
        end
        Log(string.format("terrain lights %s%s (albedo %.2f, shadow proxy %s, sky fill %s); respawning the level",
            TerrainLights.on and "ON" or "off", TerrainLights.unreal and ", Unreal-lit" or "", TerrainLights.albedo,
            TerrainLights.proxy and "on" or "off", TerrainLights.fill and "on" or "off"))
        reload()
        return
    elseif value then
        TerrainLights.albedo = math.max(0.0, value)
        local n = 0
        for _, mid in ipairs(Current.sunMids) do
            if mid:IsValid() and pcall(function() mid:SetScalarParameterValue(FName("DynamicAlbedo"), TerrainLights.albedo) end) then
                n = n + 1
            end
        end
        Log(string.format("terrain lights: albedo %.2f on %d material(s)", TerrainLights.albedo, n))
        return
    elseif mode ~= nil then
        Log("usage: mjolnir_terrain_lights [on|off] [albedo] [noproxy] [fill] [hybrid] [trial] | margin <texels> | param <Name> <value>")
        return
    end
    Log(string.format("terrain lights %s (albedo %.2f, shadow proxy %s)",
        TerrainLights.on and "ON" or "off", TerrainLights.albedo, TerrainLights.proxy and "on" or "off"))
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

--- The multiplayer switch. A converted CE multiplayer map runs under the
--- simulation's Megalo engine, which the campaign flow never asks for: the
--- native half patches the map-load handler (and the map-variant checks the
--- campaign flow cannot satisfy) just before such a map starts, and puts the
--- shipped bytes back before any other mission (docs/re/megalo_engine.md).
--- A level file opts in with `"multiplayer": true`; the level's codename is
--- the ScenarioName the campaign flow is asked to begin.
local function multiplayerLevel(code)
    local path = code and levelPathFor(code)
    local raw = path and readFile(path)
    if not raw then return nil end
    -- Kept for the load that follows (LevelFiles), which reads it again.
    local ok, level = LevelFiles.decode(path, raw, false)
    if ok and type(level) == "table" and level.multiplayer == true then return level end
    return nil
end

--- Game type by insertion point index. A converted map keeps one copy of its
--- insertion point per slot (`level bake`, single_bsp), MJOLNIRLobby starts a
--- game type at its slot's insertion point, and the host's travel carries
--- the index to every fireteam client (`?InsertionPointIndex=1` is CTF), the
--- one choice of the host's that the travel itself carries. A slot names an
--- engine only: match_variant.txt names the exact variant, and this is the
--- fallback (VariantSettings.exactVariant). Keep in step with MJOLNIRLobby's
--- modes.lua.
local GAME_TYPE_SLOTS = { [0] = "slayer", [1] = "ctf", [2] = "team_slayer", [3] = "koth", [4] = "oddball", [5] = "forge",
    [6] = "race" }

local function loadMegaloSwitch()
    if not package or not package.loadlib then return end
    local dll = MOD_DIR .. "\\native\\mjolnir_map_registry.dll"
    local on = package.loadlib(dll, "mjolnir_megalo_on")
    local off = package.loadlib(dll, "mjolnir_megalo_off")
    -- A level that names a variant ("variant": "slayer") gets
    -- variants\slayer.mglo, staged next to the DLL as native\variant.mglo;
    -- the native half installs it where the simulation's loader reads it at
    -- the next round reset (docs/ce_map_conversion.md).
    local variant = package.loadlib(dll, "mjolnir_megalo_variant")
    -- A FORGE game (MJOLNIRLobby) runs the sandbox engine instead, whose
    -- default variant the load builds itself (docs/re/forge_engine.md).
    local forgeOn = package.loadlib(dll, "mjolnir_forge_on")
    if not (on and off) then
        Log("multiplayer switch: not in this build of the native DLL")
        return
    end
    -- Team armour: in a team game the native half makes the simulation
    -- choose Mk V Classic for every Spartan (the one armour whose material
    -- takes a team colour; teams.lua tints it), on every machine, as each
    -- simulation works out every player's armour itself. Off, each player
    -- wears their own choice. An older DLL has no switch, and teams.lua
    -- swaps the armour to Mk V itself.
    local armorOn = package.loadlib(dll, "mjolnir_team_armor_on")
    local armorOff = package.loadlib(dll, "mjolnir_team_armor_off")
    Teams.native = (armorOn and armorOff) and "off" or "missing"
    if Teams.native == "missing" then
        Log("team armour: no switch in this build of the native DLL; in team games the Lua swaps each Spartan to Mk V Classic")
    end
    local function teamArmor(wanted)
        if not (armorOn and armorOff) then return end
        local ok, err = pcall(wanted and armorOn or armorOff)
        if ok then
            Teams.native = wanted and "on" or "off"
        else
            Log("team armour: " .. tostring(err))
        end
    end
    --- Switch for the map about to load: the host's campaign flow names it
    --- (SetAndBeginCampaign), a client in the host's fireteam learns it from
    --- the travel the host sends (ClientTravel, `...?ScenarioName=BGL...`).
    --- A client never sees SetAndBeginCampaign: without this its simulation
    --- stayed in the campaign engine and its screen black (two PCs,
    --- 2026-10-01).
    local switched = { code = nil, at = -1000 }
    local function switchFor(code, pending, how)
        local readAt = os.clock()
        local level = multiplayerLevel(code)
        if code then
            Log(string.format("load timing: the %s switch read %s's level file in %.0f ms", how, tostring(code),
                (os.clock() - readAt) * 1000))
        end
        -- The match for other mods (MJOLNIRHud): "CODE<TAB>game
        -- type<TAB>title", or no file while no multiplayer map runs.
        os.remove(MOD_DIR .. "\\running.txt")
        if not level and not code then
            -- A travel that names no scenario: the way back to the frontend.
            -- Leave the patches alone. Restoring them under a running Megalo
            -- game froze every fireteam client on its way back to the menu
            -- (two PCs, 2026-10-02); the next map start names its scenario
            -- and switches either way. Team armour is only a flag the
            -- native hook reads, safe to clear: the menu shows each player's
            -- own armour.
            switched.code = nil
            teamArmor(false)
            return
        end
        if not level then
            off()
            teamArmor(false)
            switched.code = nil
            return
        end
        -- The game type: the host's choice from the multiplayer menu, which a
        -- client has from match_variant.txt or the travel's slot; else the
        -- map's default.
        local chosen = pending or level.variant
        switched.code, switched.at = code, os.clock()
        if chosen == "forge" then
            if not forgeOn then
                Log("multiplayer switch: FORGE needs a newer mjolnir_map_registry.dll; " .. tostring(code)
                    .. " starts as Slayer")
                chosen = "slayer"
            else
                forgeOn()
                RunningVariant = chosen
                teamArmor(false)
                -- The sandbox's own variant has no filters to show the map's
                -- vehicles: MJOLNIRForge's DLL shows these (vehicle_sets.lua).
                local shown = io.open(MOD_DIR .. "\\forge_vehicles.txt", "wb")
                if shown then
                    local okL, layout = pcall(Json.decode, readFile(MOD_DIR .. "\\variants\\slayer.layout.json") or "")
                    local list = type(level.vehicle_sets) == "table" and level.vehicle_sets or {}
                    shown:write(VehicleSets.forgeLines(list, okL and layout or nil, level.spawn_sets, level.game))
                    shown:close()
                end
                local running = io.open(MOD_DIR .. "\\running.txt", "w")
                if running then
                    running:write(tostring(code), "\tforge\t", tostring(level.title or level.name or code), "\n")
                    running:close()
                end
                Log("multiplayer switch: " .. tostring(code) .. " starts under the sandbox engine, FORGE (" .. how .. ")")
                return
            end
        end
        on()
        Log("multiplayer switch: " .. tostring(code) .. " starts under the Megalo engine (" .. how .. ")")
        RunningVariant = chosen
        teamArmor(Teams.TEAM_GAMES[string.lower(tostring(chosen))] == true)
        local running = io.open(MOD_DIR .. "\\running.txt", "w")
        if running then
            running:write(tostring(code), "\t", tostring(chosen or ""), "\t",
                tostring(level.title or level.name or code), "\n")
            running:close()
        end
        if chosen and variant then
            local name = tostring(chosen)
            local bytes = readFile(MOD_DIR .. "\\variants\\" .. name .. ".mglo")
            -- The host's game settings (MJOLNIRLobby writes them here on the
            -- host and on every fireteam client), patched into the copy the
            -- simulation loads, so every machine runs the same rules.
            local settingsText = readFile(MOD_DIR .. "\\variant_settings.txt")
            local parsed = VariantSettings.parse(settingsText)
            if bytes and settingsText and settingsText:match("%S") then
                local settings = VariantSettings.forMode(parsed, name)
                local patched, why = VariantSettings.apply(bytes, settings)
                if patched then
                    bytes = patched
                    Log("multiplayer switch: game settings " .. VariantSettings.format(settings))
                else
                    Log("multiplayer switch: game settings not applied (" .. tostring(why) .. "); the variant's own rules run")
                end
            end
            -- CE's vehicle sets, and CE's and Halo 2's spawn sets: the map
            -- places its vehicles, and the spawn points only some game types
            -- use, hidden, and the variant requires the labels of the ones
            -- this game type and the host's vehicle settings pick
            -- (vehicle_sets.lua). Spawn sets go first, so a cut drops
            -- vehicles. Every machine computes the same filters from the
            -- same settings line and level.
            if bytes and (type(level.vehicle_sets) == "table" or type(level.spawn_sets) == "table") then
                local layout
                local rawLayout = readFile(MOD_DIR .. "\\variants\\" .. name .. ".layout.json")
                if rawLayout then
                    local okL, l = pcall(Json.decode, rawLayout)
                    if okL then layout = l end
                end
                local choices = VehicleSets.fromSettings(parsed)
                local spawns = VehicleSets.spawnFilters(level.spawn_sets, name, level.game)
                local okV, out, added, dropped = pcall(function()
                    local wanted = {}
                    for _, f in ipairs(spawns) do wanted[#wanted + 1] = f end
                    if type(level.vehicle_sets) == "table" then
                        for _, f in ipairs(VehicleSets.filters(level.vehicle_sets, name, choices)) do
                            wanted[#wanted + 1] = f
                        end
                    end
                    return VehicleSets.apply(bytes, layout, wanted)
                end)
                if okV and out then
                    bytes = out
                    Log(string.format("multiplayer switch: spawn sets %d, vehicles %s: %d label filter(s)%s",
                        #spawns, VehicleSets.describe(choices), added,
                        dropped > 0 and (", " .. dropped .. " left out (the variant holds 16 filters)") or ""))
                else
                    Log("multiplayer switch: spawn and vehicle sets not applied (" .. tostring(okV and added or out)
                        .. "); the map's hidden spawn points and vehicles stay hidden")
                end
            end
            local staged = bytes and io.open(MOD_DIR .. "\\native\\variant.mglo", "wb")
            if staged then
                staged:write(bytes)
                staged:close()
                variant()
                Log("multiplayer switch: variant " .. name .. " (see native\\map_registry.log)")
                -- CTF makes each team's flag of its own type, and the blue
                -- one ships in the CE runtime pack: without it the
                -- simulation wipes the whole script (docs/game_modes.md
                -- 2.2), a match with no flags and nothing to say why.
                if (name == "ctf" or name == "assault") and not Teams.blueFlagInstalled() then
                    Log("CTF needs the CE runtime with the blue flag (" .. Teams.BLUE_FLAG_CONTAINER .. "), and this PC "
                        .. "does not have it: a CTF variant that names the blue flag runs with no flags and no captures "
                        .. "here. Update the MJOLNIR CE runtime pack in the launcher.")
                end
            else
                Log("multiplayer switch: no variants\\" .. name .. ".mglo; the default variant runs")
            end
        end
    end

    local hooked = pcall(function()
        RegisterHook("/Script/BlamEngine.BlamCampaignFlowGameSubsystem:SetAndBeginCampaign",
            function(_, _, scenario)
                local code
                pcall(function() code = string.upper(scenario:get():ToString()) end)
                -- A game type chosen in the multiplayer menu (MJOLNIRLobby)
                -- arrives as pending_variant.txt; it is used once.
                local pending = readFile(MOD_DIR .. "\\pending_variant.txt")
                if pending then os.remove(MOD_DIR .. "\\pending_variant.txt") end
                pending = pending and pending:match("^%s*([%w_]+)%s*$")
                switchFor(code, pending, "host")
            end)
    end)
    --- Switch for a travel URL (`...?ScenarioName=BGL?InsertionPointIndex=0`).
    local function switchForUrl(target, how)
        local code = target:match("[?&]ScenarioName=([%w_]+)")
        code = code and string.upper(code)
        -- The host's own SetAndBeginCampaign has already switched for
        -- this map; anything else (a client, or a travel back to the
        -- frontend, which names no scenario) decides here.
        if code and switched.code == code and os.clock() - switched.at < 60 then return end
        -- The engine travels as the insertion point index: the lobby starts
        -- a game type at its slot's insertion point (GAME_TYPE_SLOTS). The
        -- exact variant is in match_variant.txt, from the host's messages or
        -- the listing, when it is for this map and agrees with the slot.
        local slot = tonumber(target:match("[?&]InsertionPointIndex=(%d+)") or "")
        local exact, note = VariantSettings.exactVariant(readFile(MOD_DIR .. "\\match_variant.txt"), code, slot,
            function(id) return readFile(MOD_DIR .. "\\variants\\" .. id .. ".mglo") ~= nil end)
        if note then Log("multiplayer switch: " .. note) end
        switchFor(code, exact or (slot and GAME_TYPE_SLOTS[slot]), how)
    end
    local clientHooked = pcall(function()
        RegisterHook("/Script/Engine.PlayerController:ClientTravelInternal", function(_, url)
            local okU, target = pcall(function() return url:get():ToString() end)
            if not okU or type(target) ~= "string" then return end
            switchForUrl(target, "client travel")
        end)
    end)
    -- A player who joins a match under way gets no travel from the host:
    -- MJOLNIRLobby's native half replays the client side of one, which does
    -- not pass through ClientTravelInternal. MJOLNIRLobby leaves the URL in
    -- join_switch.txt (a console command needs a player controller that a
    -- held world does not have yet), or it is typed here.
    RegisterConsoleCommandHandler("mjolnir_level_join", function(full)
        local target = tostring(full or ""):match("^%S+%s+(%S+)")
        if target then switchForUrl(target, "join in progress") end
        return true
    end)
    every(500, "join switch", function()
        local path = MOD_DIR .. "\\join_switch.txt"
        local target = readFile(path)
        if not target then return end
        os.remove(path)
        target = target:match("^%s*(%S+)")
        if target then switchForUrl(target, "join in progress") end
    end)
    Log(hooked and "multiplayer switch: armed (levels with \"multiplayer\": true)"
        or "multiplayer switch: could not hook SetAndBeginCampaign")
    if not clientHooked then Log("multiplayer switch: could not hook ClientTravelInternal (fireteam clients)") end
end

local function initialize()
    -- Kill floors (#234) and Halo 2's lifts (#235), kept on Teams: main.lua
    -- is at Lua's 200 locals. Both run Blam script through sim_script.lua.
    Teams.Script = dofile(MOD_DIR .. "\\Scripts\\sim_script.lua")
    Teams.Script.init(MOD_DIR)
    Teams.KillFloor = dofile(MOD_DIR .. "\\Scripts\\kill_floor.lua")
    Teams.KillFloor.init({ Log = Log, getWorld = getWorld, isHost = isHostWorld, Current = Current, Script = Teams.Script })
    Teams.Lifts = dofile(MOD_DIR .. "\\Scripts\\lifts.lua")
    Teams.PackLifts = dofile(MOD_DIR .. "\\Scripts\\pack_lifts.lua").new({
        inventoryPath = MOD_DIR .. "\\..\\..\\MJOLNIRForgePacks\\installed.json", decode = Json.decode,
    })
    Teams.Lifts.init({ Log = Log, getWorld = getWorld, Current = Current, Script = Teams.Script, PackLifts = Teams.PackLifts })
    Teams.Devices = dofile(MOD_DIR .. "\\Scripts\\devices.lua")
    Teams.Devices.init({ Log = Log, Current = Current })
    Teams.VehicleSounds = dofile(MOD_DIR .. "\\Scripts\\vehicle_sounds.lua")
    Teams.VehicleSounds.init({
        Log = Log, Current = Current, findObject = findObject, resolveMesh = resolveMesh, gameVolume = gameVolume,
        getWorld = getWorld, readFile = readFile, decode = Json.decode,
    })
    Teams.init({
        Log = Log, findObject = findObject, resolveMesh = resolveMesh, applyMaterials = applyMaterials,
        hideAllBut = hideAllBut, getPawn = getPawn, getWorld = getWorld, track = track, liveIn = liveIn,
        mayArm = mayArm, Current = Current, modDir = MOD_DIR, decode = Json.decode,
        -- The running game type changes with each map (switchFor).
        variant = function() return RunningVariant end,
    })
    loadMapRegistry()
    loadMegaloSwitch()
    loadEventSounds()
    hookIncidents()
    hookRelay()
    RegisterConsoleCommandHandler("mjolnir_level_status", function()
        status()
        return true
    end)
    RegisterConsoleCommandHandler("mjolnir_level_reload", function()
        reload()
        return true
    end)
    RegisterConsoleCommandHandler("mjolnir_flux_bake", function()
        local _, msg = pcall(Effects.fluxBake)
        Log("flux bake: " .. tostring(msg))
        return true
    end)
    RegisterConsoleCommandHandler("mjolnir_flux_recapture", function()
        ExecuteInGameThread(function()
            local _, msg = pcall(Effects.fluxRecapture)
            Log("flux: " .. tostring(msg))
        end)
        return true
    end)
    RegisterConsoleCommandHandler("mjolnir_level_clear", function()
        clearActors()
        Log("cleared")
        return true
    end)
    RegisterConsoleCommandHandler("mjolnir_terrain_shadows", function(_, args)
        terrainShadows(args)
        return true
    end)
    RegisterConsoleCommandHandler("mjolnir_light_scale", function(_, args)
        setLightScale(args)
        return true
    end)
    RegisterConsoleCommandHandler("mjolnir_terrain_debug", function(_, args)
        terrainDebug(args)
        return true
    end)
    RegisterConsoleCommandHandler("mjolnir_terrain_lights", function(_, args)
        terrainLights(args)
        return true
    end)
    RegisterConsoleCommandHandler("mjolnir_water", function(_, args)
        waterCommand(args)
        return true
    end)
    RegisterConsoleCommandHandler("mjolnir_terrain_detail", function(_, args)
        terrainDetail(args)
        return true
    end)
    RegisterConsoleCommandHandler("mjolnir_foliage", function(_, args)
        Foliage.command(args)
        return true
    end)
    RegisterConsoleCommandHandler("mjolnir_footprints", function(_, args)
        Footprints.command(args)
        return true
    end)
    RegisterConsoleCommandHandler("mjolnir_effects", function(_, args)
        Effects.command(args)
        return true
    end)
    Log("commands registered: mjolnir_level_status / _reload / _clear, mjolnir_terrain_shadows, mjolnir_light_scale, mjolnir_terrain_lights, mjolnir_water, mjolnir_terrain_detail, mjolnir_foliage, mjolnir_footprints, mjolnir_effects")
    watch()
end

ExecuteInGameThreadWithDelay(5000, initialize)
print("[MJOLNIR LevelLoader] Module loaded.\n")
