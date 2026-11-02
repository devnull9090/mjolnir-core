-- Bounded, data-only surface profiles. Animation lives in the GPU material;
-- this module assigns an instance once per active actor, never per frame.
local Materials = {}
local MAX_CLASSES, MAX_ACTORS = 64, 256
local profiles = { glass_cyan = true, teleporter_green = true }

local function slug(value, pack)
    return type(value) == "string" and #value >= (pack and 2 or 1) and #value <= 64
        and value:match(pack and "^[a-z0-9][a-z0-9%-]*$" or "^[a-z0-9][a-z0-9_%-]*$") ~= nil
end
function Materials.validSurfaces(value)
    if type(value) ~= "table" or #value < 1 or #value > 16 then return false end
    local seen = {}
    for _, item in ipairs(value) do
        if type(item) ~= "table" then return false end
        for key in pairs(item) do if key ~= "slot" and key ~= "profile" then return false end end
        if type(item.slot) ~= "number" or item.slot % 1 ~= 0 or item.slot < 0 or item.slot > 15
            or seen[item.slot] or not profiles[item.profile] then return false end
        seen[item.slot] = true
    end
    return true
end
local function valid(value) return value and value:IsValid() end
local function unwrap(value)
    if type(value) == "userdata" and value.get then return value:get() end
    return value
end
local function engineAdapter()
    local native, output, reported = {}, {}, {}
    local engine
    local function find(path)
        assert(path:match("^/Script/"), "only native objects may be cached")
        if valid(native[path]) then return native[path] end
        local object = StaticFindObject(path)
        if valid(object) then native[path] = object; return object end
    end
    local function ksl() return find("/Script/Engine.Default__KismetSystemLibrary") end
    local function load(path)
        local system = ksl()
        if not system then return nil end
        -- Native soft-path loading returns an already loaded asset quickly.
        -- Called only for a newly seen actor, and failures are cached per world.
        local object = system:LoadAsset_Blocking(system:Conv_SoftObjPathToSoftObjRef(system:MakeSoftObjectPath(path)))
        return valid(object) and object or nil
    end
    return {
        valid = valid,
        key = function(object) return object:GetFullName() .. ":" .. tostring(object:GetAddress()) end,
        report = function(key, message)
            if not reported[key] then reported[key] = true; print("[MJOLNIR Forge] surfaces: " .. message .. "\n") end
        end,
        world = function()
            if not valid(engine) then engine = FindFirstOf("GameEngine") end
            if not valid(engine) then return nil end
            local ok, world = pcall(function()
                local pc = engine.GameViewport.GameInstance.LocalPlayers[1].PlayerController
                return valid(pc) and pc:GetWorld() or nil
            end)
            return ok and world or nil
        end,
        actors = function(world, path)
            local system, gs = ksl(), find("/Script/Engine.Default__GameplayStatics")
            if not system or not gs then return {} end
            -- No global UObject scan and no class load in the frontend/travel.
            local class = system:Conv_SoftClassReferenceToClass(
                system:Conv_SoftClassPathToSoftClassRef(system:MakeSoftClassPath(path)))
            if not valid(class) then return {} end
            gs:GetAllActorsOfClass(world, class, output)
            local actors = {}
            for i, actor in ipairs(output) do
                actors[#actors+1] = unwrap(actor)
                output[i] = nil
            end
            return actors
        end,
        binding = function(actor)
            if not valid(actor) or actor.bHidden then return nil end
            local class = find("/Script/BlamSynchronization.BlamObjectSynchronizationComponent")
                or find("/Script/BlamEngine.BlamObjectSynchronizationComponent")
            if not class then return nil end
            for _, item in ipairs(actor:K2_GetComponentsByClass(class) or {}) do
                local index = unwrap(item).BlamObjectIndex
                if type(index) == "number" and index ~= -1 and index ~= 4294967295 then return index end
            end
        end,
        apply = function(actor, pack, surface, profile)
            local class = find("/Script/Engine.StaticMeshComponent")
            if not class then return false, "static mesh component class unavailable" end
            local component
            for _, item in ipairs(actor:K2_GetComponentsByClass(class) or {}) do
                local candidate = unwrap(item)
                if valid(candidate.StaticMesh) and candidate:GetNumMaterials() > surface.slot then
                    component = candidate
                    break
                end
            end
            if not component then return false, "requested material slot unavailable" end
            local root = "/Game/MJOLNIR/Forge/" .. pack
            local parent = load(root .. "/Materials/" .. profile.master .. "." .. profile.master)
            if not parent then return false, "pack material missing: " .. profile.master end
            local textures = {}
            for parameter, name in pairs(profile.textures) do
                local texture = load(root .. "/Textures/" .. name .. "." .. name)
                if not texture then return false, "pack texture missing: " .. name end
                textures[parameter] = texture
            end
            local mid = component:CreateDynamicMaterialInstance(surface.slot, parent, FName("MJOLNIRForgeSurface" .. surface.slot))
            if not valid(mid) then return false, "material instance creation failed" end
            for name, value in pairs(textures) do mid:SetTextureParameterValue(FName(name), value) end
            for name, value in pairs(profile.scalars) do mid:SetScalarParameterValue(FName(name), value) end
            for name, value in pairs(profile.vectors) do
                mid:SetVectorParameterValue(FName(name), {R=value[1], G=value[2], B=value[3], A=value[4]})
            end
            return true
        end,
    }
end

local function validProfiles(data)
    if type(data) ~= "table" or data.schema_version ~= 1 or type(data.profiles) ~= "table" then return false end
    for name in pairs(profiles) do
        local profile = data.profiles[name]
        if type(profile) ~= "table" or type(profile.master) ~= "string" or not profile.master:match("^M_Forge%w+$")
            or type(profile.textures) ~= "table" or type(profile.scalars) ~= "table" or type(profile.vectors) ~= "table" then return false end
        local count = 0
        for _, parameters in ipairs({profile.textures, profile.scalars, profile.vectors}) do
            for key, value in pairs(parameters) do
                count = count + 1
                if count > 128 or type(key) ~= "string" or #key > 64 or not key:match("^%w+$") then return false end
                if parameters == profile.textures then
                    if type(value) ~= "string" or #value > 64 or not value:match("^T_%w+$") then return false end
                elseif parameters == profile.scalars then
                    if type(value) ~= "number" or value ~= value or math.abs(value) > 100000 then return false end
                else
                    if type(value) ~= "table" or #value ~= 4 then return false end
                    for _, v in ipairs(value) do
                        if type(v) ~= "number" or v ~= v or math.abs(v) > 100000 then return false end
                    end
                end
            end
        end
    end
    return true
end

function Materials.new(data, adapter)
    local api = adapter or engineAdapter()
    local self = { definitions = {}, live = {}, failed = {}, world = nil }
    local enabled = validProfiles(data)
    function self:setInventory(inventory)
        local definitions, count, visited = {}, 0, 0
        if enabled and type(inventory) == "table" and inventory.schema_version == 1 and type(inventory.packs) == "table" then
            for _, pack in ipairs(inventory.packs) do
                local catalog = type(pack) == "table" and pack.forge_pack
                if type(catalog) == "table" and catalog.schema_version == 1 and slug(catalog.id, true)
                    and catalog.id == pack.slug and type(catalog.blocks) == "table" and #catalog.blocks <= 256 then
                    for _, block in ipairs(catalog.blocks) do
                        visited = visited + 1
                        if visited > 4096 then break end
                        if count < MAX_CLASSES and type(block) == "table" and slug(block.id, false) and Materials.validSurfaces(block.surfaces)
                            and block.tag == "objects\\mjolnir\\forge\\" .. pack.slug .. "\\" .. block.id then
                            local path = "/Game/MJOLNIR/Forge/" .. pack.slug .. "/BP_" .. block.id .. ".BP_" .. block.id .. "_C"
                            if not definitions[path] then count = count + 1 end
                            definitions[path] = { pack = pack.slug, surfaces = block.surfaces }
                        end
                    end
                end
                if visited > 4096 then break end
            end
        end
        self.definitions, self.live, self.failed = definitions, {}, {}
    end
    function self:tick()
        if not enabled then return 0 end
        local world = api.world()
        local key = api.valid(world) and api.key(world) or nil
        if key ~= self.world then self.live, self.failed, self.world = {}, {}, key end
        if not key then return 0 end
        local paths = {}
        for path in pairs(self.definitions) do paths[#paths+1] = path end
        table.sort(paths)
        local nextLive, count = {}, 0
        for _, path in ipairs(paths) do
            if count >= MAX_ACTORS then break end
            if not self.failed[path] then
                local definition = self.definitions[path]
                for _, actor in ipairs(api.actors(world, path)) do
                    if count >= MAX_ACTORS or self.failed[path] then break end
                    local binding = api.binding(actor)
                    if binding ~= nil then
                        count = count + 1
                        local actorKey = api.key(actor) .. ":" .. tostring(binding)
                        local done = self.live[actorKey]
                        if not done then
                            done = true
                            for _, surface in ipairs(definition.surfaces) do
                                local ok, applied, reason = pcall(api.apply, actor, definition.pack, surface, data.profiles[surface.profile])
                                if not ok or not applied then
                                    done = false
                                    self.failed[path] = true
                                    if api.report then api.report(path, tostring(ok and reason or applied)) end
                                    break
                                end
                            end
                        end
                        if done then nextLive[actorKey] = true end
                    end
                end
            end
        end
        -- Only string keys/booleans persist. No actor, component, MID, texture
        -- or Blueprint wrapper survives a poll or can be used after world GC.
        self.live = nextLive
        return count
    end
    return self
end
return Materials
