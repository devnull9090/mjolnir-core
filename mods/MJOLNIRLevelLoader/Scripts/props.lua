--- Physics props: a crate the simulation moves, drawn as a level's prop.
---
--- A level's `dress` list (tools/level/upgrade_ce_map.py `physics_props`,
--- written from a Halo 2 map's own tag data by h2_physics_props.py) names a
--- crate actor class, the prop's mesh, its materials, its transform and the
--- spots its crates start at (`spawns`, Unreal cm). Prop types share one
--- crate actor class: a crate is dressed as the prop whose spawn is nearest
--- where it first appears, so a map can have any number of prop types (the
--- game has only some two dozen crate Blueprints). The prop's mesh is added to
--- the crate as a component and the crate's own meshes are hidden, so the
--- crate's physics carries the prop.
---
--- The game pools these actors: they exist from the load (hidden, at the
--- origin) and are shown as the simulation places a crate, so a crate not yet
--- in place is retried (`pending`) until it is; the crate's meshes are hidden
--- again every few seconds in case the game shows them as it hands an actor
--- out (the health packs' pickup mesh came back that way).
---
--- While it lives a prop's materials get its health (`Health`, the crate's
--- body vitality: Halo 2's fusion coil core glows orange whole and pink-red
--- shot). When it dies it stays where it fell, burnt (`Charred`), and its
--- `death_fx` plays: Niagara systems, a scorch decal and Halo 2's own death
--- sounds (Zanzibar, 2026-11-15).
--- Whether `actor` belongs to the world named `worldName` (a world's
--- GetFullName, "World /Game/.../CNT/CNT.CNT"). Right after a map change
--- FindAllOf still returns the last map's actors, being destroyed but not
--- yet freed; reading one (its location, its components) crashed the game
--- in UE4SS going from Zanzibar to Containment (2026-11-18).
local function inWorld(actor, worldName)
    local path = type(worldName) == "string" and worldName:match("^%S+%s+(.+)$")
    if not path then return false end
    local ok, name = pcall(function() return actor:GetFullName() end)
    return ok and type(name) == "string" and name:find(path .. ":", 1, true) ~= nil
end

local Props = {}

--- deps: Log, resolveMesh, findObject, applyMaterials, hideAllBut, getWorld,
--- Current, MOBILITY_MOVABLE, COLLISION_NONE, gameVolume.
function Props.new(d)
    local self = { watched = {}, dressed = {}, pending = {}, since = {}, sweptWorld = nil, logged = {} }
    local MATCH_CM, STRAY_S = 150.0, 3.0

    local function specs()
        local l = d.Current.level and d.Current.level.dress
        return type(l) == "table" and l or {}
    end

    local function shortClass(path)
        return tostring(path):match("%.([^%.]+)$") or tostring(path)
    end

    --- The prop a crate of `class` at `l` is: the class's only look, or the
    --- look with a spawn nearest it (within MATCH_CM).
    --- A crate still unmatched after STRAY_S (it fell or was knocked from
    --- where it started before anyone came near: Zanzibar's stacked coils)
    --- takes the nearest spawn at any distance.
    local function lookFor(class, l, any)
        local only, best, bestD = nil, nil, any and math.huge or MATCH_CM * MATCH_CM
        local n = 0
        for _, spec in ipairs(specs()) do
            if shortClass(spec.actor_class) == class then
                n = n + 1
                only = spec
                for _, s in ipairs(type(spec.spawns) == "table" and spec.spawns or {}) do
                    local dx, dy, dz = l.X - s[1], l.Y - s[2], l.Z - s[3]
                    local dd = dx * dx + dy * dy + dz * dz
                    if dd < bestD then best, bestD = spec, dd end
                end
            end
        end
        if n == 1 and not (type(only.spawns) == "table" and #only.spawns > 0) then return only end
        return best
    end

    local function undress(mine)
        if mine and mine.comp and mine.comp:IsValid() then
            pcall(function() mine.comp:K2_DestroyComponent(mine.comp) end)
        end
    end

    function self.dress(world, actor, spec)
        if not actor:IsValid() then return end
        local key = actor:GetFullName()
        local mine = self.dressed[key]
        if mine and mine.comp:IsValid() and mine.spec == spec then
            d.hideAllBut(actor, mine.comp)
            return
        end
        -- A pooled actor handed out as another prop: its old look goes.
        undress(mine)
        local mesh = d.resolveMesh(spec.mesh)
        if not mesh then error("mesh not found: " .. tostring(spec.mesh)) end
        local comp = actor:AddComponentByClass(d.findObject("/Script/Engine.StaticMeshComponent"), false, {
            Rotation = { X = 0, Y = 0, Z = 0, W = 1 },
            Translation = { X = 0, Y = 0, Z = 0 },
            Scale3D = { X = 1, Y = 1, Z = 1 },
        }, false)
        if not (comp and comp:IsValid()) then error("no mesh component") end
        comp.Mobility = d.MOBILITY_MOVABLE
        comp:SetStaticMesh(mesh)
        comp:SetCollisionEnabled(d.COLLISION_NONE)
        -- A dead prop's scorch (death_fx decal) belongs on the floor and the
        -- walls round it, not on the prop it is spawned over.
        pcall(function() comp.bReceivesDecals = false end)
        local p, s = spec.pos or { 0, 0, 0 }, spec.scale or 1.0
        -- terrain.json's scale is [x, y, z]; a single number scales evenly.
        local sx, sy, sz = s, s, s
        if type(s) == "table" then sx, sy, sz = s[1] or 1, s[2] or s[1] or 1, s[3] or s[1] or 1 end
        comp:K2_SetRelativeLocationAndRotation({ X = p[1], Y = p[2], Z = p[3] },
            { Pitch = 0, Yaw = 0, Roll = 0 }, false, d.Current.emptyHit(), false)
        comp:SetRelativeScale3D({ X = sx, Y = sy, Z = sz })
        self.dressed[key] = { comp = comp, actor = actor, spec = spec }
        self.pending[key] = nil
        d.hideAllBut(actor, comp)
        local applied, failed = d.applyMaterials(comp, spec.materials, world, "prop")
        if not self.logged[spec.mesh] then
            self.logged[spec.mesh] = true
            d.Log(string.format("physics props: %s on %s (%d material(s), %d failed)",
                tostring(spec.mesh):match("[^/]+$") or spec.mesh, shortClass(spec.actor_class), applied, failed))
        end
    end

    --- Dress a crate once it stands where a prop starts; until then it waits.
    local function tryDress(world, actor)
        if not actor:IsValid() or not inWorld(actor, d.Current.worldName) then return false end
        local key = actor:GetFullName()
        local hidden = false
        pcall(function() hidden = actor.bHidden end)
        local mine = self.dressed[key]
        if hidden then
            if not mine then self.pending[key] = actor end
            return false
        end
        if mine and mine.comp:IsValid() then return true end
        self.since[key] = self.since[key] or os.clock()
        local stray = os.clock() - self.since[key] > STRAY_S
        local spec = lookFor(actor:GetClass():GetFName():ToString(), actor:K2_GetActorLocation(), stray)
        if not spec then
            self.pending[key] = actor
            return false
        end
        self.since[key] = nil
        local ok, err = pcall(self.dress, world, actor, spec)
        if not ok then d.Log("physics props: " .. tostring(err)) end
        return ok
    end

    -- Every slot of the look: the mesh keeps the donor's one slot, so
    -- GetNumMaterials says 1; the look is the component's overrides.
    local function slots(comp)
        local n = 0
        pcall(function() n = comp:GetNumMaterials() end)
        pcall(function() n = math.max(n, comp.OverrideMaterials:GetArrayNum()) end)
        return n
    end

    local function parentName(m)
        local parent = ""
        pcall(function() parent = m.Parent:GetFName():ToString() end)
        return parent
    end

    --- Slots on another master (a fusion coil's additive glow shell,
    --- M_CE_TransparentAddTwoSided) have no `Charred`: dead, they draw the
    --- hidden master; alive again, their own material back.
    local CHARRED, HEALTH = FName("Charred"), FName("Health")
    local HIDDEN = "/Game/MJOLNIR/CETrial/M_CE_Hidden.M_CE_Hidden"
    local function setCharred(mine, dead)
        local comp = mine.comp
        mine.kept = mine.kept or {}
        for i = 0, slots(comp) - 1 do
            local m = mine.kept[i] or comp:GetMaterial(i)
            if m and m:IsValid() then
                if parentName(m) == "M_CE_PropLit" then
                    pcall(function() m:SetScalarParameterValue(CHARRED, dead and 1.0 or 0.0) end)
                elseif dead then
                    local hidden = d.resolveMesh(HIDDEN)
                    if hidden then
                        mine.kept[i] = m
                        pcall(function() comp:SetMaterial(i, hidden) end)
                    end
                elseif mine.kept[i] then
                    pcall(function() comp:SetMaterial(i, mine.kept[i]) end)
                    mine.kept[i] = nil
                end
            end
        end
    end

    local function setHealth(mine, h)
        for i = 0, slots(mine.comp) - 1 do
            local m = mine.comp:GetMaterial(i)
            if m and m:IsValid() and parentName(m) == "M_CE_PropLit" then
                pcall(function() m:SetScalarParameterValue(HEALTH, h) end)
            end
        end
    end

    --- The look's `death_fx`: `systems` [{system, scale, up}] Niagara
    --- systems; `decal` {material, color = [r, g, b, a] for its emissive
    --- colours, size = [depth, width, height] cm, life s} projected down onto
    --- what the prop stood on; `waves` {paths, gain}: Halo 2's own death sound
    --- (one variant at random), at the gameplay slider. This game's own
    --- sounds are Wwise events its audio system plays for its objects, which
    --- posting from here does not reach (silent, 2026-11-15), so the sound is
    --- Halo 2's, staged and imported as a sound wave.
    local NIAGARA = "/Script/Niagara.Default__NiagaraFunctionLibrary"
    local STATICS = "/Script/Engine.Default__GameplayStatics"
    local serial = 0
    local function attenuation(world)
        local class = d.findObject("/Script/Engine.SoundAttenuation")
        if not class then return nil end
        serial = serial + 1
        local att
        pcall(function()
            att = StaticConstructObject(class, world, FName("MJOLNIR_PropAtt_" .. serial))
            local a = att.Attenuation
            a.bAttenuate = true
            a.bSpatialize = true
            a.DistanceAlgorithm = 0
            a.AttenuationShape = 0
            a.AttenuationShapeExtents = { X = 600.0, Y = 0, Z = 0 }
            a.FalloffDistance = 6000.0
        end)
        return att
    end

    local function deathFx(mine)
        local fx = mine.spec and mine.spec.death_fx
        if type(fx) ~= "table" then return end
        local world = d.getWorld()
        if not world then return end
        local l = mine.actor:K2_GetActorLocation()
        local lib = d.findObject(NIAGARA)
        for _, e in ipairs(type(fx.systems) == "table" and fx.systems or {}) do
            local system = type(e.system) == "string" and d.resolveMesh(e.system)
            if system and lib then
                local s = tonumber(e.scale) or 1.0
                local ok, err = pcall(function()
                    lib:SpawnSystemAtLocation(world, system, { X = l.X, Y = l.Y, Z = l.Z + (tonumber(e.up) or 0) },
                        { Pitch = 0, Yaw = 0, Roll = 0 }, { X = s, Y = s, Z = s }, true, true, 0, true)
                end)
                if not ok then d.Log("physics props: death effect: " .. tostring(err)) end
            end
        end
        local statics = d.findObject(STATICS)
        local waves = type(fx.waves) == "table" and fx.waves.paths
        if statics and type(waves) == "table" and #waves > 0 then
            local wave = d.resolveMesh(waves[math.random(#waves)])
            local volume = (tonumber(fx.waves.gain) or 1.0) * (d.gameVolume and d.gameVolume("gameplay") or 1.0)
            if wave and volume > 0 then
                local ok, err = pcall(function()
                    statics:SpawnSoundAtLocation(world, wave, { X = l.X, Y = l.Y, Z = l.Z + 40 },
                        { Pitch = 0, Yaw = 0, Roll = 0 }, math.min(1.0, volume * 3.0), 1.0, 0.0,
                        attenuation(world), nil, true)
                end)
                if not ok then d.Log("physics props: death sound: " .. tostring(err)) end
            end
        end
        local decal = fx.decal
        local mat = type(decal) == "table" and type(decal.material) == "string" and d.resolveMesh(decal.material)
        if mat and statics then
            local size, c = decal.size or { 60, 130, 130 }, decal.color
            local ok, err = pcall(function()
                local dc = statics:SpawnDecalAtLocation(world, mat, { X = size[1], Y = size[2], Z = size[3] },
                    { X = l.X, Y = l.Y, Z = l.Z }, { Pitch = -90, Yaw = math.random(0, 359), Roll = 0 },
                    tonumber(decal.life) or 45.0)
                if type(c) == "table" and dc and dc:IsValid() then
                    -- Both: the grenade's decal keeps its blue in
                    -- EmissiveColor (its master's default) and EmissiveColor2.
                    local mid = dc:CreateDynamicMaterialInstance()
                    local colour = { R = c[1], G = c[2], B = c[3], A = c[4] or 1 }
                    mid:SetVectorParameterValue(FName("EmissiveColor"), colour)
                    mid:SetVectorParameterValue(FName("EmissiveColor2"), colour)
                end
            end)
            if not ok then d.Log("physics props: death decal: " .. tostring(err)) end
        end
    end

    --- Four times a second: crates waiting to be dressed, each dressed prop's
    --- health (its look's `Health`), and deaths (burnt, its death_fx).
    --- A prop's damage component and its two functions, read once: 4 times
    --- a second over every prop, a property read, a closure and two method
    --- lookups a prop were garbage enough that the collector's runs landed
    --- as 10-15 ms frames all over the hitch log (ZAN, 2026-11-15).
    local function damageOf(mine)
        if mine.dmg == nil then
            mine.dmg = false
            pcall(function()
                local dmg = mine.actor.BlamObjectDamage
                if dmg and dmg:IsValid() then
                    mine.dmg, mine.isDead, mine.vitality = dmg, dmg.IsDead, dmg.GetBodyVitality
                end
            end)
        end
        return mine.dmg
    end

    function self.deaths()
        if next(self.pending) then
            local world = d.getWorld()
            if world then
                for key, actor in pairs(self.pending) do
                    if actor:IsValid() then tryDress(world, actor) else self.pending[key] = nil end
                end
            end
        end
        for key, mine in pairs(self.dressed) do
            if mine.actor:IsValid() and mine.comp:IsValid() then
                local dead, health = false, 1.0
                local dmg = damageOf(mine)
                if dmg and dmg:IsValid() then
                    local ok, v = pcall(mine.isDead, dmg)
                    if ok then dead = v end
                    ok, v = pcall(mine.vitality, dmg)
                    if ok then health = v end
                end
                if type(health) ~= "number" or health ~= health then health = 1.0 end
                if dead ~= (mine.dead or false) then
                    -- Only a death seen happen blows up: a crate first seen
                    -- dead (a pooled actor, a rejoin) just stays burnt.
                    if dead and mine.dead == false then deathFx(mine) end
                    mine.dead = dead
                    setCharred(mine, dead)
                elseif mine.dead == nil then
                    mine.dead = dead
                end
                health = math.max(0.0, math.min(1.0, health))
                if not dead and math.abs(health - (mine.health or 1.0)) > 0.02 then
                    mine.health = health
                    setHealth(mine, health)
                end
            else
                self.dressed[key] = nil
            end
        end
    end

    --- Arm a watch a class (once) and look at the class's pool (once a world).
    function self.tick()
        local world = d.getWorld()
        if not world then return end
        for _, spec in ipairs(specs()) do
            local class = spec.actor_class
            if class and not self.watched[class] then
                local ok = pcall(NotifyOnNewObject, class, function(actor)
                    for _, ms in ipairs({ 50, 500, 2000 }) do
                        ExecuteInGameThreadWithDelay(ms, function()
                            local w = d.getWorld()
                            if w and actor:IsValid() then pcall(tryDress, w, actor) end
                        end)
                    end
                end)
                self.watched[class] = ok or "failed"
            end
        end
        local name = d.Current.worldName
        if self.sweptWorld ~= name then
            self.sweptWorld = name
            self.dressed, self.pending, self.since = {}, {}, {}
            local classes, n = {}, 0
            for _, spec in ipairs(specs()) do classes[shortClass(spec.actor_class)] = true end
            for class in pairs(classes) do
                for _, actor in ipairs(FindAllOf(class) or {}) do
                    if tryDress(world, actor) then n = n + 1 end
                end
            end
            d.Log(string.format("physics props: %d actor(s) dressed, the rest wait to be placed", n))
        else
            -- Hidden again: the game may show a pooled crate's own meshes
            -- as it hands the actor out.
            for key, mine in pairs(self.dressed) do
                if mine.actor:IsValid() and mine.comp:IsValid() then
                    pcall(d.hideAllBut, mine.actor, mine.comp)
                else
                    self.dressed[key] = nil
                end
            end
        end
    end

    return self
end

return Props
