-- Pack lights are bounded data. Only the namespaced actor of a validated
-- pack/block gets a movable point-light component; no pack supplies code.
local Lights = {}
local LIMIT = 64

local function finite(n, low, high)
    return type(n) == "number" and n == n and n >= low and n <= high
end
local function vector(v, low, high)
    return type(v) == "table" and #v == 3
        and finite(v[1], low, high) and finite(v[2], low, high) and finite(v[3], low, high)
end
local function id(s, pack)
    return type(s) == "string" and #s >= (pack and 2 or 1) and #s <= 64
        and s:match(pack and "^[a-z0-9][a-z0-9%-]*$" or "^[a-z0-9][a-z0-9_%-]*$") ~= nil
end
function Lights.validSpec(s)
    if type(s) ~= "table" then return false end
    for key in pairs(s) do
        if key ~= "offset_m" and key ~= "color_rgb" and key ~= "intensity_cd" and key ~= "radius_m" then return false end
    end
    return vector(s.offset_m, -100, 100) and vector(s.color_rgb, 0, 1)
        and finite(s.intensity_cd, 0, 10000) and s.intensity_cd > 0
        and finite(s.radius_m, 0, 100) and s.radius_m > 0
end

-- Source geometry is right-handed Z-up metres. The actor root is already
-- in the Unreal world, and its mesh normalization must not scale the lamp.
function Lights.offset(spec)
    return { X = spec.offset_m[1] * 100, Y = -spec.offset_m[2] * 100, Z = spec.offset_m[3] * 100 }
end

local function valid(object)
    return object and object:IsValid()
end
local function unwrap(object)
    if type(object) == "userdata" and object.get then return object:get() end
    return object
end
local function engineAdapter()
    local reported, hit, actorOutput, nativeObjects = {}, {}, {}, {}
    local engine
    local function report(key, message)
        if reported[key] then return end
        reported[key] = true
        print("[MJOLNIR Forge] pack lights: " .. message .. "\n")
    end
    local function nativeObject(path)
        -- These /Script classes and CDOs live for the process. Never put a
        -- Blueprint or a world-owned object in this cache: even IsValid on
        -- its wrapper can dereference freed memory after package GC.
        assert(path:match("^/Script/"), "only native objects may be cached")
        local kept = nativeObjects[path]
        if valid(kept) then return kept end
        local found = StaticFindObject(path)
        if valid(found) then nativeObjects[path] = found; return found end
        return nil
    end
    local function blueprintClass(path)
        local ksl = nativeObject("/Script/Engine.Default__KismetSystemLibrary")
        if not ksl then return nil end
        -- UE4SS's string StaticFindObject scans the entire UObject array:
        -- four light classes cost 60-80 ms every half second on RWC. The
        -- engine's nonloading soft-class conversion takes <1 ms for an
        -- already loaded class. Never load pack assets early in the frontend
        -- or during travel. Resolve afresh; no Blueprint wrapper is retained
        -- across polls, pooling, same-world GC or map travel.
        local found = ksl:Conv_SoftClassReferenceToClass(
            ksl:Conv_SoftClassPathToSoftClassRef(ksl:MakeSoftClassPath(path)))
        return valid(found) and found or nil
    end
    local function world()
        if not valid(engine) then
            engine = FindFirstOf("GameEngine")
            if not valid(engine) then return nil end
        end
        -- The shared UEHelpers.GetWorld calls FindAllOf(PlayerController)
        -- on every invocation. Follow the current local player instead,
        -- retaining only the process-lifetime engine, never the controller.
        local ok, current = pcall(function()
            local pc = engine.GameViewport.GameInstance.LocalPlayers[1].PlayerController
            return valid(pc) and pc:GetWorld() or nil
        end)
        return ok and current or nil
    end
    return {
        world = world,
        key = function(object) return object:GetFullName() .. ":" .. tostring(object:GetAddress()) end,
        valid = valid,
        report = report,
        actors = function(world, path)
            local cls = blueprintClass(path)
            local gs = nativeObject("/Script/Engine.Default__GameplayStatics")
            if not (cls and gs) then return {} end
            -- Like FHitResult below, UE4SS retains out-parameter tables.
            -- One reusable table serves every class and inventory revision;
            -- it is empty between calls and holds no world-owned actors.
            local out, actors = actorOutput, {}
            gs:GetAllActorsOfClass(world, cls, out)
            for i, actor in ipairs(out) do
                actors[#actors + 1] = unwrap(actor)
                out[i] = nil
            end
            return actors
        end,
        active = function(actor)
            if not valid(actor) or actor.bHidden then return false end
            -- Deleted Blam actors can remain pooled Unreal objects. Only
            -- an actor currently bound to a simulation object is a lamp.
            local cls = nativeObject("/Script/BlamSynchronization.BlamObjectSynchronizationComponent")
                or nativeObject("/Script/BlamEngine.BlamObjectSynchronizationComponent")
            if not cls then return false end
            for _, item in ipairs(actor:K2_GetComponentsByClass(cls) or {}) do
                local c = unwrap(item)
                local index = c.BlamObjectIndex
                if type(index) == "number" and index ~= -1 and index ~= 4294967295 then return true end
            end
            return false
        end,
        create = function(actor, spec)
            local cls = nativeObject("/Script/Engine.PointLightComponent")
            if not cls or not valid(actor.RootComponent) then return nil end
            local c = actor:AddComponentByClass(cls, true, {
                Rotation = { X = 0, Y = 0, Z = 0, W = 1 },
                Translation = { X = 0, Y = 0, Z = 0 }, Scale3D = { X = 1, Y = 1, Z = 1 },
            }, false)
            if not valid(c) then return nil end
            local ok, err = pcall(function()
                c.Mobility = 2 -- movable
                if c:K2_AttachToComponent(actor.RootComponent, FName("None"), 0, 0, 1, false) == false then
                    error("point-light component could not attach to the piece root")
                end
                -- Reuse the out-parameter table: UE4SS retains FHitResult
                -- wrappers for fresh tables (LevelLoader uses the same rule).
                c:K2_SetRelativeLocation(Lights.offset(spec), false, hit, false)
                c.bUseInverseSquaredFalloff = true
                c.IntensityUnits = 1 -- candelas, not lumens or legacy unitless brightness
                c:SetIntensity(spec.intensity_cd)
                c:SetAttenuationRadius(spec.radius_m * 100)
                c:SetLightColor({ R = spec.color_rgb[1], G = spec.color_rgb[2], B = spec.color_rgb[3], A = 1 }, true)
                c:SetSourceRadius(8)
                c:SetCastShadows(false)
                c:SetHiddenInGame(false, false)
                c:SetVisibility(true, false)
            end)
            if not ok then
                report("attach", "attachment failed: " .. tostring(err))
                pcall(function() c:K2_DestroyComponent(c) end)
                return nil
            end
            return c
        end,
        destroy = function(component)
            if valid(component) then component:K2_DestroyComponent(component) end
        end,
    }
end

-- Adapter injection keeps lifecycle/cap tests independent of the game.
function Lights.new(adapter)
    local api = adapter or engineAdapter()
    local self = { definitions = {}, live = {}, world = nil }
    function self:setInventory(inventory)
        local definitions, duplicates = {}, {}
        if type(inventory) == "table" and inventory.schema_version == 1 and type(inventory.packs) == "table" then
            for _, pack in ipairs(inventory.packs) do
                local data = type(pack) == "table" and pack.forge_pack
                if type(data) == "table" and data.schema_version == 1 and id(data.id, true)
                    and data.id == pack.slug and type(data.blocks) == "table" and #data.blocks <= 256 then
                    for _, block in ipairs(data.blocks) do
                        if type(block) == "table" and id(block.id, false)
                            and block.tag == "objects\\mjolnir\\forge\\" .. data.id .. "\\" .. block.id then
                            local path = "/Game/MJOLNIR/Forge/" .. data.id .. "/BP_" .. block.id .. ".BP_" .. block.id .. "_C"
                            if duplicates[path] then definitions[path] = nil
                            else
                                duplicates[path] = true
                                if Lights.validSpec(block.light) then definitions[path] = block.light end
                            end
                        end
                    end
                end
            end
        end
        self.definitions = definitions
    end
    function self:tick()
        local world = api.world()
        local worldKey = api.valid(world) and api.key(world) or nil
        if self.world ~= worldKey then
            -- The departing world owns these components and destroys them.
            -- Never call IsValid/Destroy on wrappers from its object graph:
            -- pcall cannot catch a native UE4SS access violation after GC.
            self.live = {}
            self.world = worldKey
        end
        local wanted = {}
        if worldKey then
            local paths = {}
            for path in pairs(self.definitions) do paths[#paths + 1] = path end
            table.sort(paths)
            for _, path in ipairs(paths) do
                for _, actor in ipairs(api.actors(world, path)) do
                    local ok, active = pcall(api.active, actor)
                    if not ok and api.report then api.report("active", "actor check failed: " .. tostring(active)) end
                    if ok and active then
                        wanted[api.key(actor)] = { actor = actor, spec = self.definitions[path] }
                    end
                end
            end
        end
        local count = 0
        for key, entry in pairs(self.live) do
            if not wanted[key] or entry.spec ~= wanted[key].spec or not api.valid(entry.light) then
                pcall(api.destroy, entry.light)
                self.live[key] = nil
            else count = count + 1 end
        end
        local keys = {}
        for key in pairs(wanted) do keys[#keys + 1] = key end
        table.sort(keys)
        for _, key in ipairs(keys) do
            if count >= LIMIT then break end
            if not self.live[key] then
                local entry = wanted[key]
                local ok, light = pcall(api.create, entry.actor, entry.spec)
                if not ok and api.report then api.report("create", "creation failed: " .. tostring(light)) end
                if ok and api.valid(light) then
                    self.live[key] = { light = light, spec = entry.spec }
                    count = count + 1
                end
            end
        end
        return count
    end
    return self
end
return Lights
