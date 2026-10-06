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
    -- CTF flag actors already dressed, by full name (dressFlags).
    flags = {},
    -- Bipeds already given their team colour, by full name.
    tinted = {},
    -- Set once fade_in has been asked for; it waits for the player, while the
    -- terrain and sky go in as soon as the world is known.
    faded = false,
    -- Set once the game type has been announced (see playEvent).
    announced = false,
    fileMissing = false,
    -- Decor whose material follows a CE periodic function (a beacon's flare
    -- pulsing with its light): { mid, param, base, fn, period }.
    pulses = {},
    -- CE material instances told the sun's illuminance (runtimeMaterial),
    -- for `mjolnir_light_scale`.
    sunMids = {},
}

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
    Current.flags = {}
    Current.packDressed = false
    Current.tinted = {}
    Current.fileMissing = false
    Current.pulses = {}
    Current.sunMids = {}
end

local function clearActors()
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
    Current.sunMids = {}
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

--- Resolve a mesh object path, loading the asset if it is not in memory.
--- Never called on world packages: decor mesh paths are object paths into
--- /Engine or /Game mesh packages (LoadAsset on a world package crashes).
local function resolveMesh(path)
    local mesh = findObject(path)
    if mesh then return mesh end
    local ok, loaded = pcall(function() return LoadAsset(path) end)
    if ok and loaded and loaded:IsValid() then return loaded end
    -- UE4SS's LoadAsset only knows what the game's AssetRegistry lists, which
    -- leaves out every package of ours (the converted levels' cooked
    -- materials and textures, pakchunk988). A soft-path blocking load goes
    -- straight to the package store instead.
    ok, loaded = pcall(function()
        local ksl = findObject("/Script/Engine.Default__KismetSystemLibrary")
        return ksl:LoadAsset_Blocking(ksl:Conv_SoftObjPathToSoftObjRef(ksl:MakeSoftObjectPath(path)))
    end)
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
    return MOD_DIR .. "\\" .. value:gsub("/", "\\")
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

--- Dynamic lights on the terrain (`mjolnir_terrain_lights`, an experiment).
--- The game's own lights (headlights, muzzle flashes, explosions) multiply
--- the terrain's base colour, which holds only the sun's share of the baked
--- light: nothing where CE had shade. `on` gives the CE environment masters
--- (the trial build, with DYNAMIC_ALBEDO_CODE) the surface's albedo there
--- (DynamicAlbedo, a multiplier), puts the terrain on lighting channel 0
--- with the game's lights, and spawns the terrain's shadow copy, so the
--- Unreal sun stays out of CE's shade and the materials need give nothing
--- back there (SunVisBake). `noproxy` leaves the copy out: the sun then
--- reaches everywhere and the albedo in CE's shade is capped by what the
--- emissive can give back. Lasts until the game closes.
--- `margin` sets how far (bake texels) CE's sun and shade are pulled in
--- from their edges, where the copy's shadow and the bake disagree.
--- `unreal` draws the terrain in Unreal's direct light (UnrealLit,
--- build_ce_materials.py SUNLIT_CODE), with the sun mask keeping CE's shade.
local TerrainLights = { on = false, albedo = 1.0, proxy = true, margin = nil, fill = false, unreal = false }

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
local function runtimeMaterial(world, spec, name)
    local kml = findObject("/Script/Engine.Default__KismetMaterialLibrary")
    local parent = nil
    -- The lightmap experiment draws the CE environment masters with the
    -- trial build, when it is installed.
    local master = (TerrainShadows.lightmap or TerrainLights.on) and type(spec.parent) == "string"
        and spec.parent:match("^/Game/MJOLNIR/CE/(M_CE_Environment[%w]*%.M_CE_Environment[%w]*)$")
    if master then parent = resolveMesh(TRIAL_MASTERS .. master) end
    parent = parent or (type(spec.parent) == "string" and resolveMesh(spec.parent))
    if not kml or not parent then return nil, "parent material not found: " .. tostring(spec.parent) end
    local mid = kml:CreateDynamicMaterialInstance(world, parent, FName(name), 0)
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

local function applyMaterials(comp, list, world, id)
    if type(list) ~= "table" then return 0, 0 end
    local applied, failed = 0, 0
    -- A machine's moving part is drawn moved by its material (the CE device
    -- masters' World Position Offset), out past the mesh's own bounds: the
    -- spec's bounds_scale keeps the mesh drawn wherever the part goes.
    local bounds = 1.0
    for i, entry in ipairs(list) do
        local mat, err
        if type(entry) == "string" and #entry > 0 then
            mat = resolveMesh(entry)
            err = "not found: " .. entry
        elseif type(entry) == "table" then
            local ok, m, e = pcall(runtimeMaterial, world, entry, string.format("%s_%d", id, i - 1))
            mat, err = ok and m or nil, ok and e or m
            if mat and type(entry.bounds_scale) == "number" then bounds = math.max(bounds, entry.bounds_scale) end
        end
        if mat then
            if pcall(function() comp:SetMaterial(i - 1, mat) end) then
                applied = applied + 1
            else
                failed = failed + 1
            end
        elseif entry ~= "" then
            failed = failed + 1
            Log(string.format("decor '%s' slot %d: %s", tostring(id), i - 1, tostring(err)))
        end
    end
    if bounds > 1.0 then
        local ok = pcall(function() comp:SetBoundsScale(bounds) end)
        if not ok then ok = pcall(function() comp.BoundsScale = bounds; comp:MarkRenderStateDirty() end) end
        Log(string.format("decor '%s': bounds scale %.2f for its moving machine parts%s", tostring(id), bounds,
            ok and "" or " (could not set)"))
    end
    return applied, failed
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
            elseif Current.actors[key] then
                if Current.actors[key]:IsValid() then pcall(function() Current.actors[key]:K2_DestroyActor() end) end
                Current.actors[key] = nil
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
        c:SetLightColor({ R = SKY_FILL.color[1], G = SKY_FILL.color[2], B = SKY_FILL.color[3], A = 1 }, false)
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
    if not (terrain and terrain:IsValid() and stem) then return false, "no terrain with a lightmap" end
    local raw = readFile(textureFile("bake\\" .. stem .. "_sunmask.json"))
    if not raw then return false, "no bake\\" .. stem .. "_sunmask.json" end
    local okJson, spec = pcall(Json.decode, raw)
    if not okJson or type(spec) ~= "table" or type(spec.min) ~= "table" then return false, "unreadable sun mask json" end
    local levels = lightmapSun()
    if not levels then return false, "the level names no lightmap_sun levels" end
    local tex, err = importTexture(world, "bake\\" .. stem .. "_sunmask.png", true)
    if not tex then return false, tostring(err) end
    local master = resolveMesh(TRIAL_MASTERS .. "M_CE_SunLight.M_CE_SunLight")
    if not master then return false, "trial M_CE_SunLight not installed" end
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
        local nApplied, nFailed = applyMaterials(actor.StaticMeshComponent, item.materials, world, tostring(item.id))
        Log(string.format("decor '%s': %d material(s) applied, %d failed",
            tostring(item.id), nApplied, nFailed))
        local pulse = item.pulse
        if type(pulse) == "table" and type(pulse.param) == "string" then
            local first = item.materials[1]
            local base = type(first) == "table" and first.scalars and first.scalars[pulse.param]
            local okM, mid = pcall(function() return actor.StaticMeshComponent:GetMaterial(0) end)
            if okM and mid and mid:IsValid() and base then
                Current.pulses[#Current.pulses + 1] = {
                    mid = mid, param = FName(pulse.param), base = base,
                    fn = pulse["function"] or 2, period = pulse.period or 1.0,
                }
            end
        end
    end
    -- After the materials: the strength is set on them.
    if (TerrainShadows.cast or TerrainShadows.strength) and isTerrain(item) then
        pcall(applyTerrainShadows, actor)
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
            pcall(function() c:SetAtmosphereSunLight(false) end)
            if type(sun.color) == "table" then
                c:SetLightColor({ R = sun.color[1], G = sun.color[2], B = sun.color[3], A = 1.0 }, false)
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
        c:SetIntensity((skylight.intensity or 3.0) * k)
        if type(skylight.color) == "table" then
            c:SetLightColor({ R = skylight.color[1], G = skylight.color[2], B = skylight.color[3], A = 1.0 })
        end
        c:RecaptureSky()
    end)
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

--- A level baked with `clear.scripts` has no mission script left to fade the
--- screen back in after the loading screen, so the map boots pitch black with
--- a live simulation behind it. Ask the Blam console to fade in once the
--- player exists, unless the level opts out with `environment.fade_in = false`.
--- The level's ambient sound (environment.sounds, from the CE map's BSP
--- background sound and sound scenery: tools/level/ce_sounds.py), played
--- through Unreal's own audio engine, which the game runs beside its own.
--- Background loops are 2D and map-wide; emitters are 3D loops that fall off
--- linearly from `inner` to `inner + falloff` centimetres, as CE's distance
--- bounds do.
local function spawnSounds(world)
    local env = Current.level and Current.level.environment
    local sounds = type(env) == "table" and env.sounds
    if type(sounds) ~= "table" then return end
    local gs = findObject("/Script/Engine.Default__GameplayStatics")
    local attClass = findObject("/Script/Engine.SoundAttenuation")
    if not gs then return end
    local playing, failed = 0, 0

    local function keep(key, comp, fade)
        if not (comp and comp:IsValid()) then
            failed = failed + 1
            return
        end
        Current.actors[key] = comp
        if fade and fade > 0 then pcall(function() comp:FadeIn(fade, 1.0, 0.0, 0) end) end
        playing = playing + 1
    end

    for i, s in ipairs(type(sounds.background) == "table" and sounds.background or {}) do
        local wave = type(s.wave) == "string" and resolveMesh(s.wave)
        if wave then
            local ok, comp = pcall(function()
                return gs:SpawnSound2D(world, wave, s.gain or 1.0, 1.0, 0.0, nil, false, false)
            end)
            keep("__bg" .. i, ok and comp, s.fade_in)
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
            local ok, comp = pcall(function()
                return gs:SpawnSoundAtLocation(world, wave,
                    { X = origin[1] + s.pos[1], Y = origin[2] + s.pos[2], Z = origin[3] + s.pos[3] },
                    { Pitch = 0, Yaw = 0, Roll = 0 }, s.gain or 1.0, 1.0, 0.0, att, nil, false)
            end)
            keep("__snd" .. i, ok and comp, s.fade_in)
        else
            failed = failed + 1
            Log("sound not found: " .. tostring(s.wave))
        end
    end
    Log(string.format("ambient sound: %d playing, %d failed", playing, failed))
end

--- The skull's ghostly fire (BP_SkullEffect) and its whispering, which is
--- the actor's own audio component (HaloAudioTracking): removing the effect
--- alone left the whisper playing. The game makes the effect again as the
--- flag is picked up and dropped, so it is removed again then, from the
--- first-person actor too.
local SKULL_PARTS = { "BP_SkullEffect", "HaloAudioTracking" }

--- The flag mesh the loader put on each flag actor, by actor full name;
--- every other mesh on the actor is the skull's.
local FlagMeshes = {}

--- Hide the skull's own meshes. The game shows them again (the skull came
--- back at the foot of the flag after it was dressed), so this runs whenever
--- the skull's parts are removed.
local function hideSkull(actor)
    local mine = FlagMeshes[actor:GetFullName()]
    for _, c in ipairs(actor:K2_GetComponentsByClass(findObject("/Script/Engine.PrimitiveComponent")) or {}) do
        pcall(function()
            if type(c) == "userdata" and c.get then c = c:get() end
            if mine and mine:IsValid() and c:GetFullName() == mine:GetFullName() then return end
            c:SetHiddenInGame(true, false)
            c:SetVisibility(false, false)
        end)
    end
end

local function quenchSkull(actor)
    hideSkull(actor)
    for _, c in ipairs(actor:K2_GetComponentsByClass(findObject("/Script/Engine.ActorComponent")) or {}) do
        pcall(function()
            if type(c) == "userdata" and c.get then c = c:get() end
            local name = c:GetFullName()
            for _, part in ipairs(SKULL_PARTS) do
                if name:find(part, 1, true) then
                    c:Deactivate()
                    c:K2_DestroyComponent(c)
                end
            end
        end)
    end
end

--- Capture the Flag flags (the level's `ctf`). The flag object borrows the
--- oddball's actor, since nothing ships for it (tools/level/build_ctf_flag.sh),
--- so each flag that turns up is a skull: it gets CE's flag mesh in its
--- team's colours instead, the team from the stand it is made on. A new flag
--- is a new actor (a captured or reset flag is deleted and made again).
local FLAG_ACTOR_CLASS = "BP_SkullActor_C"
local FP_FLAG_ACTOR_CLASS = "BP_FP_SkullActor_C"
local TEAM_NAMES = { [0] = "red", [1] = "blue" }
-- Within this of a stand, a new flag actor is that stand's flag.
local FLAG_AT_STAND_CM = 400

--- Put CE's flag mesh on a skull actor, at `pos` (cm), `rot` (pitch, yaw,
--- roll) and `scale` relative to it, in team `name`'s colours.
local function attachFlagMesh(world, actor, ctf, name, pos, rot, scale)
    local flag = ctf.flag
    local mesh = resolveMesh(flag.mesh)
    if not mesh then error("mesh not found: " .. tostring(flag.mesh)) end
    -- The skull's own meshes go (quenchSkull hides them, now and whenever
    -- the game shows them again); the actor, which follows the flag, stays.
    local comp = actor:AddComponentByClass(findObject("/Script/Engine.StaticMeshComponent"), false, {
        Rotation = { X = 0, Y = 0, Z = 0, W = 1 },
        Translation = { X = 0, Y = 0, Z = 0 },
        Scale3D = { X = 1, Y = 1, Z = 1 },
    }, false)
    if not (comp and comp:IsValid()) then error("no mesh component") end
    comp.Mobility = MOBILITY_MOVABLE
    comp:SetStaticMesh(mesh)
    comp:SetCollisionEnabled(COLLISION_NONE)
    comp:K2_SetRelativeLocationAndRotation({ X = pos[1], Y = pos[2], Z = pos[3] },
        { Pitch = rot[1], Yaw = rot[2], Roll = rot[3] }, false, {}, false)
    comp:SetRelativeScale3D({ X = scale, Y = scale, Z = scale })
    FlagMeshes[actor:GetFullName()] = comp
    hideSkull(actor)
    local materials = type(flag.materials) == "table" and flag.materials[name]
    local applied, failed = applyMaterials(comp, materials, world, "flag_" .. name)
    Log(string.format("CTF: %s flag dressed%s (%d material(s), %d failed)", name,
        actor:GetClass():GetFName():ToString() == FLAG_ACTOR_CLASS and "" or " in first person", applied, failed))
    return comp
end

--- Flags at home, pinned to their stands, by team name.
local HomeFlags = {}

--- A flag at home is drawn exactly on its stand, facing the stand's way: the
--- flag object (a weapon) settles a little off the stand and turned, which
--- showed on Gephyrophobia. Picked up, it follows the flag again
--- (unpinFlag).
local function pinFlag(comp, flag, stand, name)
    local p, yaw = flag.pos or { 0, 0, 0 }, math.rad(stand.yaw or 0)
    comp:SetAbsolute(true, true, false)
    comp:K2_SetWorldLocationAndRotation({
        X = stand.pos[1] + p[1] * math.cos(yaw) - p[2] * math.sin(yaw),
        Y = stand.pos[2] + p[1] * math.sin(yaw) + p[2] * math.cos(yaw),
        Z = stand.pos[3] + p[3],
    }, { Pitch = 0, Yaw = stand.yaw or 0, Roll = 0 }, false, {}, false)
    HomeFlags[name] = { comp = comp, flag = flag }
end

local function unpinFlag(name)
    local home = HomeFlags[name]
    HomeFlags[name] = nil
    if not (home and home.comp:IsValid()) then return end
    local p = home.flag.pos or { 0, 0, 0 }
    home.comp:SetAbsolute(false, false, false)
    home.comp:K2_SetRelativeLocationAndRotation({ X = p[1], Y = p[2], Z = p[3] },
        { Pitch = 0, Yaw = 0, Roll = 0 }, false, {}, false)
end

local function dressFlag(world, actor, ctf)
    local at = actor:K2_GetActorLocation()
    local team, best, home = nil, math.huge, nil
    for _, s in ipairs(type(ctf.stands) == "table" and ctf.stands or {}) do
        local dx, dy, dz = at.X - s.pos[1], at.Y - s.pos[2], at.Z - s.pos[3]
        local d = dx * dx + dy * dy + dz * dz
        if d < best then team, best, home = s.team, d, s end
    end
    -- A flag picked up or dropped is a new actor away from both stands; its
    -- team is the one the flag incident just named (CustomValue).
    if best > FLAG_AT_STAND_CM * FLAG_AT_STAND_CM and Current.lastFlagTeam then
        team = Current.lastFlagTeam
    end
    local name = type(team) == "string" and team or TEAM_NAMES[team] or "red"
    local flag = ctf.flag
    local comp = attachFlagMesh(world, actor, ctf, name, flag.pos or { 0, 0, 0 }, { 0, 0, 0 }, flag.scale or 1.0)
    if best <= FLAG_AT_STAND_CM * FLAG_AT_STAND_CM then pinFlag(comp, flag, home, name) end
end

--- The flag in first person: the carrier's own copy of the skull actor
--- (BP_FP_SkullActor_C), whose origin is the camera. Its skull is drawn by
--- the first-person renderer, which a mesh of ours does not take part in, so
--- the flag is held as an ordinary mesh at a fixed place before the camera:
--- low on the right, its pole leaning up and to the left, as in CE. Relative
--- to the actor, X is forward, Y up and Z left. Found by hand, holding the
--- flag (2026-10-01).
local FP_FLAG = { pos = { 65, -42, -28 }, rot = { -10, -20, 60 }, scale = 0.7 }

local function dressFirstPersonFlag(world, actor, ctf)
    local name = TEAM_NAMES[Current.lastFlagTeam] or "red"
    attachFlagMesh(world, actor, ctf, name, FP_FLAG.pos, FP_FLAG.rot, FP_FLAG.scale)
end


--- Quench a skull actor, and dress it if it is a world flag (not the
--- first-person one, a subclass) not yet dressed.
local function handleSkull(world, actor, ctf)
    if not actor:IsValid() then return end
    pcall(quenchSkull, actor)
    local class = actor:GetClass():GetFName():ToString()
    local key = actor:GetFullName()
    if Current.flags[key] then return end
    Current.flags[key] = actor
    if class == FP_FLAG_ACTOR_CLASS then
        -- The pickup's incident (which names the flag's team) is drained a
        -- moment after the actor appears.
        ExecuteInGameThreadWithDelay(300, function()
            if not actor:IsValid() then return end
            local ok, err = pcall(dressFirstPersonFlag, world, actor, ctf)
            if not ok then Log("CTF first-person flag: " .. tostring(err)) end
        end)
        return
    end
    if class ~= FLAG_ACTOR_CLASS then return end
    local ok, err = pcall(dressFlag, world, actor, ctf)
    if not ok then Log("CTF flag: " .. tostring(err)) end
end

local function ctfLevel()
    local ctf = Current.level and Current.level.ctf
    if type(ctf) == "table" and type(ctf.flag) == "table" then return ctf end
end

--- Every skull actor the watch has seen (and the ones there before it).
local Skulls = {}

--- A pass over every known skull actor, for any the watch's own handling
--- missed (MJOLNIRLevelLoader's slow tick). It was a FindAllOf: at 0.3 s,
--- twice a pass, the game stuttered, and at 3 s it still cost a 20 ms frame
--- on a converted map.
local function dressFlags(world)
    local ctf = ctfLevel()
    if not ctf then return end
    for _, actor in ipairs(liveIn(Skulls)) do
        handleSkull(world, actor, ctf)
    end
end

local SKULL_ACTOR_CLASS_PATH = "/Game/Weapons/Melee/Skull/Blueprints/BP_SkullActor.BP_SkullActor_C"
local skullsWatched = false

--- Every skull actor the game makes from now on (a flag picked up, dropped
--- or made anew, and the first-person one) is handled as it appears, once
--- its components exist.
local function watchSkulls()
    if skullsWatched then return end
    skullsWatched = pcall(NotifyOnNewObject, SKULL_ACTOR_CLASS_PATH, function(actor)
        track(Skulls, actor)
        ExecuteInGameThreadWithDelay(50, function()
            local ctf, world = ctfLevel(), getWorld()
            if ctf and world then handleSkull(world, actor, ctf) end
        end)
        -- The effect and its sound start a little after the actor.
        for _, ms in ipairs({ 500, 2000 }) do
            ExecuteInGameThreadWithDelay(ms, function()
                if ctfLevel() and actor:IsValid() then pcall(quenchSkull, actor) end
            end)
        end
    end)
    if skullsWatched then
        for _, actor in ipairs(FindAllOf(FLAG_ACTOR_CLASS) or {}) do track(Skulls, actor) end
        Log("CTF: watching for flag actors")
    end
end

--- The skull's effect comes back as a flag changes hands; a flag incident is
--- the cue to put it out again on the flags the loader knows.
local function quenchFlags()
    ExecuteInGameThreadWithDelay(200, function()
        local ctf, world = ctfLevel(), getWorld()
        local name = TEAM_NAMES[Current.lastFlagTeam]
        for key, actor in pairs(Current.flags) do
            if type(actor) == "userdata" and actor:IsValid() then
                pcall(quenchSkull, actor)
                -- The first-person actor may carry over to the next flag
                -- grabbed, of the other team: recolour it to this one.
                local comp = FlagMeshes[key]
                if ctf and world and name and comp and comp:IsValid()
                    and actor:GetClass():GetFName():ToString() == FP_FLAG_ACTOR_CLASS then
                    pcall(applyMaterials, comp, ctf.flag.materials[name], world, "flag_fp_" .. name)
                end
            end
        end
    end)
end

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

--- Hide every primitive of `actor` but `mine`.
local function hideAllBut(actor, mine)
    for _, c in ipairs(actor:K2_GetComponentsByClass(findObject("/Script/Engine.PrimitiveComponent")) or {}) do
        pcall(function()
            if type(c) == "userdata" and c.get then c = c:get() end
            if mine and mine:IsValid() and c:GetFullName() == mine:GetFullName() then return end
            c:SetHiddenInGame(true, false)
            c:SetVisibility(false, false)
        end)
    end
end

local function dressHealthPack(world, actor, hp)
    if not actor:IsValid() then return end
    local key = actor:GetFullName()
    local mine = PackMeshes[key]
    if mine and mine:IsValid() then
        hideAllBut(actor, mine)
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
        { Pitch = 0, Yaw = 0, Roll = 0 }, false, {}, false)
    comp:SetRelativeScale3D({ X = s, Y = s, Z = s })
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
--- moment later, so it is hidden again then.
local function watchHealthPacks()
    if packsWatched then return end
    packsWatched = pcall(NotifyOnNewObject, HEALTH_PACK_ACTOR_CLASS_PATH, function(actor)
        for _, ms in ipairs({ 50, 500 }) do
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
    { "slayer", "slayer_start" },
    { "koth", "koth_game_start" },
    { "king", "koth_game_start" },
    { "oddball", "ball_game_start" },
    { "ball", "ball_game_start" },
    { "ctf", "ctf_game_start" },
    { "race", "race_game_start" },
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

--- Re-tint team armour after a spawn (set below, beside tintBiped).
local retintSoon = function() end

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
    -- The CTF variant's flag incidents carry the flag's team (dressFlag).
    if name:find("^flag_") then
        if value == 0 or value == 1 then Current.lastFlagTeam = value end
        if name == "flag_grabbed" and TEAM_NAMES[value] then unpinFlag(TEAM_NAMES[value]) end
        quenchFlags()
    end
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
    if name == "player_spawn" or name == "respawn_final_tick" then
        retintSoon()
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
    if wave and gs and world then
        pcall(function() gs:PlaySound2D(world, wave, 1.0, 1.0, 0.0, nil, nil, true) end)
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

local function relayEvents(queued)
    if not isHostWorld() then return end
    local messages = {}
    for _, e in ipairs(queued) do
        if e[1] ~= "player_spawn" and not e.relayed then
            messages[#messages + 1] = string.format("MJOLNIR|event|%s|%s|%s|%s", tostring(e[1]),
                tostring(e[2] or -1), tostring(e[3] or 0), tostring(e[4] or -1))
        end
    end
    if #messages == 0 then return end
    local kind = FName(RELAY_TYPE)
    for _, pc in ipairs(FindAllOf("PlayerController") or {}) do
        pcall(function()
            if not pc:IsValid() or pc:IsLocalController() then return end
            if not (pc.Player:IsValid() and pc.PlayerState:IsValid()) then return end
            for _, msg in ipairs(messages) do pc:ClientMessage(msg, kind, 0) end
        end)
    end
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
        end)
    end)
    Log(relayHooked and "event sounds: relay from the host armed" or "event sounds: could not hook ClientMessage")
end

local function drainEvents()
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
            if not next(EventWaves) then return end
            local okI, name, cause, value, effect = pcall(function()
                local i = incident:get()
                return i.Name:ToString(), i.CausePlayerAbsoluteIndex, i.CustomValue, i.EffectPlayerAbsoluteIndex
            end)
            if okI and name and #EventQueue < 32 then
                NativeIncidents[name] = true
                EventQueue[#EventQueue + 1] = { name, cause, value, effect }
            end
        end)
    end)
    if incidentHooked then Log("event sounds: incident hook armed") end
end

--- Team colours. The Spartan's armour material has one colour (`Armor
--- Color`, Master Chief's olive), whatever team the simulation puts the
--- player on, though the biped's team component knows it
--- (`EBlamMultiplayerTeam::Red`). In a team game each Spartan gets its own
--- instance of the armour material in its team's colour, as a new biped
--- appears (every spawn is a new actor), and again a moment later for armour
--- pieces attached after it.
local TEAM_GAMES = { ctf = true, team_slayer = true }
local TEAM_ARMOR = {
    Red = { R = 1.0, G = 0.0, B = 0.0, A = 1 },
    Blue = { R = 0.03, G = 0.15, B = 1.0, A = 1 },
}
-- The colour the armour shows is `Armor Color` at global association with
-- parameter index 0, which only the by-info setter reaches: the plain setter
-- writes index -1, which this (layered) material never reads, and changed
-- nothing on screen. Found by giving each association and index its own
-- colour (2026-10-01).
local ARMOR_COLOR = { Name = FName("Armor Color"), Association = 0, Index = 0 }
local SPARTAN_CLASS_PATH = "/Game/_Prototypes/SynchronizationTestContent/TestActor/BP_SpartansBipedActor.BP_SpartansBipedActor_C"
local bipedsWatched = false

local function teamGame()
    return Current.level and Current.level.multiplayer == true
        and TEAM_GAMES[string.lower(tostring(RunningVariant))] == true
end

--- True once the armour has its team colour; false while the biped has no
--- team yet (a new biped is on none until the simulation spawns its player).
local function setArmorColor(mid, color)
    mid:SetVectorParameterValueByInfo(ARMOR_COLOR, color)
end

local function bipedTeam(actor)
    return actor.BlamGameTeam:GetGameTeamString():ToString():match("EBlamMultiplayerTeam::(%a+)")
end

--- In a team game every Spartan wears the classic Mk V armour. It is the one
--- armour whose material takes a colour (`Armor Color`): the others a player
--- can pick (Chief's default, MkIV, Blamite, Lone Wolf, the coatings) bake
--- their colours into textures, so a player in one stayed olive on Blue
--- (2026-10-02, CTF over two PCs). Each mesh component's class names its
--- role, the same whatever armour was picked, and the role names the Mk V
--- mesh; `armor` roles also get the team-coloured material. The shields keep
--- their own material (an empty or camo shell, the same for every armour).
local MKV = "/Game/Characters/Spartans/MkV_Classic/"
local MKV_FP = "/Game/Characters/SpartansFP/MkV_Classic/"
local MKV_ARMOR = MKV .. "Materials/MI_Spartans_MkV_Classic.MI_Spartans_MkV_Classic"
local BIPED_ROLES = {
    BPC_SkeletalMesh_C = { mesh = MKV .. "Mesh/SK_Spartans_MkV_Classic.SK_Spartans_MkV_Classic", armor = true },
    BPC_TranslucentSkeletalMesh_C = { mesh = MKV .. "Mesh/SK_Spartans_MkV_Classic_Shield.SK_Spartans_MkV_Classic_Shield" },
}
-- The local player's own view: first-person arms and their shield, the legs
-- seen looking down and their shield, and the body that casts its shadow.
local PAWN_ROLES = {
    BPC_FP_SkeletalMesh_C = { mesh = MKV_FP .. "Mesh/SK_SpartansFP_MkV_Classic.SK_SpartansFP_MkV_Classic", armor = true },
    BPC_FP_TranslucentSkeletalMesh_C = { mesh = MKV_FP .. "Mesh/SK_SpartansFP_MkV_Classic_Shield.SK_SpartansFP_MkV_Classic_Shield" },
    BPC_PAWN_SkeletalMesh_C = { mesh = MKV .. "Mesh/SK_Spartans_MkV_Classic_Legs.SK_Spartans_MkV_Classic_Legs", armor = true },
    BPC_FP_ShadowSkeletalMesh_C = {
        mesh = MKV .. "Mesh/SK_Spartans_MkV_Classic_NonNanite_Shadow.SK_Spartans_MkV_Classic_NonNanite_Shadow",
        armor = true,
    },
    BPC_TranslucentSkeletalMesh_C = { mesh = MKV .. "Mesh/SK_Spartans_MkV_Classic_ShieldLegs.SK_Spartans_MkV_Classic_ShieldLegs" },
}

--- Put every Spartan mesh on `actor` in the Mk V armour and give its armour
--- the team colour. Meshes already in Mk V are left in place.
local function dressMeshes(actor, roles, color)
    local tinted = false
    local skel = findObject("/Script/Engine.SkeletalMeshComponent")
    for _, c in ipairs(actor:K2_GetComponentsByClass(skel) or {}) do
        if type(c) == "userdata" and c.get then c = c:get() end
        local role = roles[c:GetClass():GetFName():ToString()]
        local mesh = role and resolveMesh(role.mesh)
        if mesh then
            local current = c.SkeletalMesh
            if not (current and current:IsValid() and current:GetFullName() == mesh:GetFullName()) then
                c:SetSkeletalMeshAsset(mesh)
            end
            if role.armor then
                local mat = c:GetMaterial(0)
                local name = mat and mat:IsValid() and mat:GetFName():ToString() or ""
                if name:find("^MJ_TeamArmor") then
                    setArmorColor(mat, color)
                    tinted = true
                else
                    local armor = resolveMesh(MKV_ARMOR)
                    if armor then
                        setArmorColor(c:CreateDynamicMaterialInstance(0, armor, FName("MJ_TeamArmor")), color)
                        tinted = true
                    end
                end
            end
        end
    end
    return tinted
end

local function tintBiped(actor)
    if not (actor and actor:IsValid() and teamGame()) then return false end
    local team = bipedTeam(actor)
    local color = team and TEAM_ARMOR[team]
    if not color then return false end
    return dressMeshes(actor, BIPED_ROLES, color)
end

--- Every Spartan biped the watch has seen (and the ones there before it).
local Bipeds = {}

local function watchBipeds()
    if bipedsWatched then return end
    bipedsWatched = pcall(NotifyOnNewObject, SPARTAN_CLASS_PATH, function(actor)
        track(Bipeds, actor)
        for _, ms in ipairs({ 300, 2000 }) do
            ExecuteInGameThreadWithDelay(ms, function()
                local ok, err = pcall(tintBiped, actor)
                if not ok then Log("team colour: " .. tostring(err)) end
            end)
        end
    end)
    if bipedsWatched then
        for _, actor in ipairs(FindAllOf("BP_SpartansBipedActor_C") or {}) do track(Bipeds, actor) end
    end
end

--- The Spartans in the world. A respawn reuses the actor, so the set holds
--- each for the match; arming the watch is the one FindAllOf.
local function knownBipeds()
    watchBipeds()
    return liveIn(Bipeds)
end

--- The local player's first-person arms, legs and shadow are meshes of the
--- pawn, which has no team; it takes the team of the Spartan nearest the
--- camera, its own body.
local function tintLocalPawn()
    if not teamGame() then return end
    local pawn = getPawn()
    local pc = getPlayerController()
    if not (pawn and pc) then return end
    local cam = pc.PlayerCameraManager:GetCameraLocation()
    local team, best = nil, math.huge
    for _, actor in ipairs(knownBipeds()) do
        local l = actor:K2_GetActorLocation()
        local d = (l.X - cam.X) ^ 2 + (l.Y - cam.Y) ^ 2 + (l.Z - cam.Z) ^ 2
        if d < best then team, best = bipedTeam(actor), d end
    end
    local color = team and TEAM_ARMOR[team]
    if color then dressMeshes(pawn, PAWN_ROLES, color) end
end

retintSoon = function()
    for _, ms in ipairs({ 300, 1500, 4000 }) do
        ExecuteInGameThreadWithDelay(ms, function()
            if not teamGame() then return end
            for _, actor in ipairs(knownBipeds()) do
                pcall(tintBiped, actor)
            end
            pcall(tintLocalPawn)
        end)
    end
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

local function spawnDecor(world)
    local level = Current.level
    spawnEnvironment(world)
    spawnSounds(world)
    preloadEventSounds()
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
    if proxyWanted() then
        Log(string.format("terrain shadow proxy: %d spawned", applyShadowProxies(world)))
    end
    if TerrainLights.on then
        local ok, done, err = pcall(applySunMask, world)
        Log("sun mask: " .. tostring(ok and (done or err) or done))
    end
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
        Current.worldName = worldName
        -- The seamless-travel transition world still answers with the
        -- scenario it is leaving; dressing it spawned the old map's terrain
        -- into the fade back to the menu at game end. Its name is
        -- /Game/Levels/Test/SeamlessTravelTEst: compare case-blind (a
        -- case-sensitive test missed it, and every return to the menu spent
        -- seconds dressing it).
        if string.upper(worldName):find("SEAMLESSTRAVEL", 1, true) then return end
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
        Log(string.format("world %s has level '%s'", Current.scenario, tostring(level.name)))
        hookIncidents()
    end

    -- Terrain and sky need only the world, so they are in place behind the
    -- loading screen; waiting for the player left converted maps black for
    -- 20-30 s after it.
    if Current.level and not Current.furnished then
        Current.furnished = true
        spawnDecor(world)
    end
    if Current.level and not Current.faded then
        if not getPawn() then return end -- still loading
        Current.faded = true
        fadeIn()
        -- The opening spawn raises no player_spawn (only respawns do), so
        -- the game type is announced once the player is in the world.
        if next(EventWaves) and #EventQueue < 32 then
            refreshLocalPlayer()
            EventQueue[#EventQueue + 1] = { "player_spawn", LOCAL_PLAYER }
        end
    end
end

--- Run `fn` on the game thread every `ms`, from the game thread: each run
--- schedules the next. An async loop that hands work to the game thread
--- (LoopAsync + ExecuteInGameThread) can deadlock UE4SS, the async thread
--- holding the mod's Lua lock while it queues, the game thread holding the
--- queue while it waits for the lock; at 0.1 s and 0.3 s it froze the game
--- within minutes (2026-10-01).
local function every(ms, name, fn)
    local function run()
        local ok, err = pcall(fn)
        if not ok then Log(name .. " error: " .. tostring(err)) end
        ExecuteInGameThreadWithDelay(ms, run)
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

--- Every pulsing decor material, at the game's time.
local function updatePulses()
    if #Current.pulses == 0 then return end
    local world = getWorld()
    if not world then return end
    KismetSystem = KismetSystem or StaticFindObject("/Script/Engine.Default__KismetSystemLibrary")
    local t = KismetSystem:GetGameTimeInSeconds(world)
    for _, p in ipairs(Current.pulses) do
        if p.mid:IsValid() then
            p.mid:SetScalarParameterValue(p.param, p.base * ceWave(p.fn, t / p.period))
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
    -- A flag picked up or dropped is a new actor, drawn as a skull until it
    -- is dressed, so CTF levels look for new ones often.
    -- CTF flags: new skull actors are reported as they are made
    -- (watchSkulls); a slow sweep catches any that were not.
    local sweeps = 0
    every(1500, "CTF flags", function()
        if not (Current.furnished and ctfLevel()) then return end
        watchSkulls()
        watchBipeds()
        sweeps = sweeps + 1
        if sweeps % 2 == 1 then
            local world = getWorld()
            if world then dressFlags(world) end
            -- A respawn reuses the actor and puts the stock armour back, so
            -- every pass re-tints (cheap: a few Spartans, a parameter each).
            for _, actor in ipairs(teamGame() and knownBipeds() or {}) do
                pcall(tintBiped, actor)
            end
            pcall(tintLocalPawn)
        end
    end)
    -- Health packs: new pack actors are reported as they are made
    -- (watchHealthPacks); the first ones can come before the watch does, so
    -- the pass that arms it sweeps for them too, once: a FindAllOf is a
    -- 20 ms frame on a converted map.
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
    if sky then pcall(function() sky.LightComponent:SetIntensity((skyEnv.intensity or 3.0) * k) end) end
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
        TerrainLights.unreal = has("unreal")
        -- Unreal-lit takes the runtime bake with it, so one respawn does both.
        if TerrainLights.on and TerrainLights.unreal and not TerrainShadows.lightmap then
            TerrainShadows.lightmap = lightmapSun()
        end
        if TerrainLights.on and not value then TerrainLights.albedo = 1.0 end
        if value then TerrainLights.albedo = math.max(0.0, value) end
        if TerrainLights.on and not resolveMesh(TRIAL_MASTERS .. "M_CE_Environment.M_CE_Environment") then
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
        Log("usage: mjolnir_terrain_lights [on|off] [albedo] [noproxy] [fill] [unreal] | margin <texels> | param <Name> <value>")
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
    local raw = code and readFile(levelPathFor(code))
    if not raw then return nil end
    local ok, level = pcall(Json.decode, raw)
    if ok and type(level) == "table" and level.multiplayer == true then return level end
    return nil
end

--- Game type by insertion point index. A converted map keeps one copy of its
--- insertion point per slot (`level bake`, single_bsp), MJOLNIRLobby starts a
--- game type at its slot's insertion point, and the host's travel carries
--- the index to every fireteam client (`?InsertionPointIndex=1` is CTF), the
--- one choice of the host's that reaches them. Keep in step with
--- MJOLNIRLobby's GAME_TYPE_SLOTS.
local GAME_TYPE_SLOTS = { [0] = "slayer", [1] = "ctf", [2] = "team_slayer", [3] = "koth", [4] = "oddball" }

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
    if not (on and off) then
        Log("multiplayer switch: not in this build of the native DLL")
        return
    end
    --- Switch for the map about to load: the host's campaign flow names it
    --- (SetAndBeginCampaign), a client in the host's fireteam learns it from
    --- the travel the host sends (ClientTravel, `...?ScenarioName=BGL...`).
    --- A client never sees SetAndBeginCampaign: without this its simulation
    --- stayed in the campaign engine and its screen black (two PCs,
    --- 2026-10-01).
    local switched = { code = nil, at = -1000 }
    local function switchFor(code, pending, how)
        local level = multiplayerLevel(code)
        -- The match for other mods (MJOLNIRHud): "CODE<TAB>game
        -- type<TAB>title", or no file while no multiplayer map runs.
        os.remove(MOD_DIR .. "\\running.txt")
        if not level and not code then
            -- A travel that names no scenario: the way back to the frontend.
            -- Leave the patches alone. Restoring them under a running Megalo
            -- game froze every fireteam client on its way back to the menu
            -- (two PCs, 2026-10-02); the next map start names its scenario
            -- and switches either way.
            switched.code = nil
            return
        end
        if not level then
            off()
            switched.code = nil
            return
        end
        on()
        switched.code, switched.at = code, os.clock()
        Log("multiplayer switch: " .. tostring(code) .. " starts under the Megalo engine (" .. how .. ")")
        -- The game type: the host's choice from the multiplayer menu; a
        -- client has only the map's default (the host's choice does not
        -- travel yet).
        local chosen = pending or level.variant
        RunningVariant = chosen
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
            if bytes and settingsText and settingsText:match("%S") then
                local settings = VariantSettings.forMode(VariantSettings.parse(settingsText), name)
                local patched, why = VariantSettings.apply(bytes, settings)
                if patched then
                    bytes = patched
                    Log("multiplayer switch: game settings " .. VariantSettings.format(settings))
                else
                    Log("multiplayer switch: game settings not applied (" .. tostring(why) .. "); the variant's own rules run")
                end
            end
            local staged = bytes and io.open(MOD_DIR .. "\\native\\variant.mglo", "wb")
            if staged then
                staged:write(bytes)
                staged:close()
                variant()
                Log("multiplayer switch: variant " .. name .. " (see native\\map_registry.log)")
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
        -- The game type travels as the insertion point index: the lobby
        -- starts game type N at insertion point N (GAME_TYPE_SLOTS).
        local slot = tonumber(target:match("[?&]InsertionPointIndex=(%d+)") or "")
        switchFor(code, slot and GAME_TYPE_SLOTS[slot], how)
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
    Log("commands registered: mjolnir_level_status / _reload / _clear, mjolnir_terrain_shadows, mjolnir_light_scale, mjolnir_terrain_lights")
    watch()
end

ExecuteInGameThreadWithDelay(5000, initialize)
print("[MJOLNIR LevelLoader] Module loaded.\n")
