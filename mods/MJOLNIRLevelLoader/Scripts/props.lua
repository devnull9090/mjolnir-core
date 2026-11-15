--- Physics props: a crate the simulation moves, drawn as a level's prop.
---
--- A level's `dress` list (tools/level/upgrade_ce_map.py `physics_props`)
--- names a crate's actor class and the prop's mesh, its materials and its
--- transform (as build_terrain_meshes.py wrote them). Every actor of that
--- class gets the prop's mesh as a component of its own, and the crate's own
--- meshes are hidden, so the crate's physics carries the prop: shot, bumped
--- or knocked about, the prop moves with it. Zanzibar's fusion coils ride
--- crate_space_a (2026-11-15).
---
--- The game pools these actors: they exist from the load (hidden, at the
--- origin) and are shown as the simulation places a crate, so the pool is
--- dressed at load (one sweep a world) and new actors as they are made; the
--- crate's meshes are hidden again every few seconds in case the game shows
--- them as it hands an actor out (the health packs' pickup mesh came back
--- that way).
local Props = {}

--- deps: Log, resolveMesh, findObject, applyMaterials, hideAllBut, getWorld,
--- Current, MOBILITY_MOVABLE, COLLISION_NONE.
function Props.new(d)
    local self = { watched = {}, dressed = {}, sweptWorld = nil, logged = {} }

    local function specs()
        local l = d.Current.level and d.Current.level.dress
        return type(l) == "table" and l or {}
    end

    local function shortClass(path)
        return tostring(path):match("%.([^%.]+)$") or tostring(path)
    end

    function self.dress(world, actor, spec)
        if not actor:IsValid() then return end
        local key = actor:GetFullName()
        local mine = self.dressed[key]
        if mine and mine.comp:IsValid() then
            d.hideAllBut(actor, mine.comp)
            return
        end
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
        local p, s = spec.pos or { 0, 0, 0 }, spec.scale or 1.0
        -- terrain.json's scale is [x, y, z]; a single number scales evenly.
        local sx, sy, sz = s, s, s
        if type(s) == "table" then sx, sy, sz = s[1] or 1, s[2] or s[1] or 1, s[3] or s[1] or 1 end
        comp:K2_SetRelativeLocationAndRotation({ X = p[1], Y = p[2], Z = p[3] },
            { Pitch = 0, Yaw = 0, Roll = 0 }, false, d.Current.emptyHit(), false)
        comp:SetRelativeScale3D({ X = sx, Y = sy, Z = sz })
        self.dressed[key] = { comp = comp, actor = actor }
        d.hideAllBut(actor, comp)
        local applied, failed = d.applyMaterials(comp, spec.materials, world, "prop")
        if not self.logged[spec.mesh] then
            self.logged[spec.mesh] = true
            d.Log(string.format("physics props: %s on %s (%d material(s), %d failed)",
                tostring(spec.mesh):match("[^/]+$") or spec.mesh, shortClass(spec.actor_class), applied, failed))
        end
    end

    --- Arm a watch a class (once) and dress the class's pool (once a world).
    function self.tick()
        local world = d.getWorld()
        if not world then return end
        for _, spec in ipairs(specs()) do
            if spec.actor_class and not self.watched[spec.actor_class] then
                local ok = pcall(NotifyOnNewObject, spec.actor_class, function(actor)
                    for _, ms in ipairs({ 50, 500, 2000 }) do
                        ExecuteInGameThreadWithDelay(ms, function()
                            local w = d.getWorld()
                            if not (w and actor:IsValid()) then return end
                            local okd, err = pcall(self.dress, w, actor, spec)
                            if not okd then d.Log("physics props: " .. tostring(err)) end
                        end)
                    end
                end)
                self.watched[spec.actor_class] = ok or "failed"
            end
        end
        local name = d.Current.worldName
        if self.sweptWorld ~= name then
            self.sweptWorld = name
            self.dressed = {}
            local n = 0
            for _, spec in ipairs(specs()) do
                for _, actor in ipairs(FindAllOf(shortClass(spec.actor_class)) or {}) do
                    local ok, err = pcall(self.dress, world, actor, spec)
                    if ok then n = n + 1 elseif n == 0 then d.Log("physics props: " .. tostring(err)) end
                end
            end
            if n > 0 then d.Log(string.format("physics props: %d actor(s) dressed", n)) end
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
