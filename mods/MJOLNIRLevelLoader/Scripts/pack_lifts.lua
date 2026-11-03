-- Bounded Forge lift data -> the same phantoms used by converted Halo 2 maps.
-- Only active namespaced actors count. Resolve classes without loading assets;
-- retain no Blueprint classes, actors or components between game-thread calls.
local PackLifts = { MAX_CLASSES = 16, MAX_ACTORS = 64 }
local SPARTAN = "/Game/_Prototypes/SynchronizationTestContent/TestActor/BP_SpartansBipedActor.BP_SpartansBipedActor_C"
local function finite(n, lo, hi) return type(n) == "number" and n == n and n >= lo and n <= hi end
-- Reflected integer properties can expose the same salted datum as signed
-- int32 or uint32. Canonicalize before using it as an identity or player index.
function PackLifts.datum32(n)
    if not finite(n, -2147483648, 4294967295) or n ~= math.floor(n) then return nil end
    n = n % 4294967296
    return n ~= 4294967295 and n or nil
end
local function vec(v, lo, hi)
    return type(v) == "table" and #v == 3 and finite(v[1], lo, hi) and finite(v[2], lo, hi) and finite(v[3], lo, hi)
end
local function dot(a, b) return a[1]*b[1] + a[2]*b[2] + a[3]*b[3] end
function PackLifts.validSpec(s)
    if type(s) ~= "table" then return false end
    local keys = { offset_m=true, size_m=true, direction=true, acceleration_m_s2=true, max_speed_m_s=true, negates_gravity=true }
    for k in pairs(s) do if not keys[k] then return false end end
    return vec(s.offset_m, -100, 100) and vec(s.size_m, 0.1, 100)
        and vec(s.direction, -1, 1) and math.abs(dot(s.direction, s.direction)-1) <= 0.001
        and finite(s.acceleration_m_s2, 0.1, 100) and finite(s.max_speed_m_s, 0.1, 30)
        and type(s.negates_gravity) == "boolean"
end

-- pose axes are the actor's Unreal forward/right/up, position in cm.
-- Source coordinates are right-handed Z-up metres: source +Y is UE -Y.
function PackLifts.transform(spec, pose, key, canvas)
    if not PackLifts.validSpec(spec) or type(pose) ~= "table" or not vec(pose.position, -1e8, 1e8) then return nil end
    local basis = {pose.forward, pose.right, pose.up}
    for i=1,3 do
        local axis = basis[i]
        if not vec(axis, -1, 1) or math.abs(dot(axis, axis)-1) > 0.001 then return nil end
    end
    if math.abs(dot(pose.forward, pose.right)) > .001 or math.abs(dot(pose.forward, pose.up)) > .001
        or math.abs(dot(pose.right, pose.up)) > .001 then return nil end
    local axes = { pose.forward, {-pose.right[1], -pose.right[2], -pose.right[3]}, pose.up }
    local function direction(v)
        return { axes[1][1]*v[1]+axes[2][1]*v[2]+axes[3][1]*v[3],
                 axes[1][2]*v[1]+axes[2][2]*v[2]+axes[3][2]*v[3],
                 axes[1][3]*v[1]+axes[2][3]*v[2]+axes[3][3]*v[3] }
    end
    canvas = canvas or {0,0,0}
    local offset = direction(spec.offset_m)
    local origin, center, half = {}, {}, {}
    for k=1,3 do
        origin[k] = pose.position[k] - (canvas[k] or 0) + offset[k]*100
        center[k] = origin[k] + pose.up[k]*spec.size_m[3]*50
        half[k] = spec.size_m[k]*50
    end
    local planes = {}
    for k=1,3 do
        for _, sign in ipairs({-1,1}) do
            local n = {axes[k][1]*sign, axes[k][2]*sign, axes[k][3]*sign}
            planes[#planes+1] = {n[1],n[2],n[3],-dot(n,center)-half[k]}
        end
    end
    local forward = direction(spec.direction)
    local length = math.sqrt(dot(forward,forward))
    for k=1,3 do forward[k] = forward[k]/length end
    return { key=key, asset=key, planes=planes, origin=origin, forward=forward,
        bounds={center[1],center[2],center[3],math.sqrt(dot(half,half))},
        direction={spec.acceleration_m_s2*100,spec.max_speed_m_s*100}, negates_gravity=spec.negates_gravity }
end

local function valid(o) return o and o:IsValid() end
local function unwrap(o) return type(o)=="userdata" and o.get and o:get() or o end
local function xyz(v) return {v.X,v.Y,v.Z} end
local function engineAdapter()
    local native, output = {}, {}
    local function object(path)
        assert(path:match("^/Script/"), "cache only native immortal classes/CDOs")
        if valid(native[path]) then return native[path] end
        local found = StaticFindObject(path)
        if valid(found) then native[path]=found; return found end
    end
    local function actors(world, path)
        local ksl, gs = object("/Script/Engine.Default__KismetSystemLibrary"), object("/Script/Engine.Default__GameplayStatics")
        if not (ksl and gs) then return {} end
        local cls = ksl:Conv_SoftClassReferenceToClass(ksl:Conv_SoftClassPathToSoftClassRef(ksl:MakeSoftClassPath(path)))
        if not valid(cls) then return {} end
        local ok = pcall(gs.GetAllActorsOfClass, gs, world, cls, output)
        local out = {}
        for i, actor in ipairs(output) do
            if ok then out[#out+1]=unwrap(actor) end
            output[i]=nil
        end
        return out
    end
    return {
        actors=actors,
        active=function(actor)
            if not valid(actor) or actor.bHidden then return nil end
            local cls = object("/Script/BlamSynchronization.BlamObjectSynchronizationComponent")
                or object("/Script/BlamEngine.BlamObjectSynchronizationComponent")
            if not cls then return nil end
            for _, item in ipairs(actor:K2_GetComponentsByClass(cls) or {}) do
                local datum = PackLifts.datum32(unwrap(item).BlamObjectIndex)
                if datum ~= nil then return datum end
            end
        end,
        key=function(actor, datum) return actor:GetFullName()..":"..tostring(datum) end,
        pose=function(actor) return {position=xyz(actor:K2_GetActorLocation()), forward=xyz(actor:GetActorForwardVector()),
            right=xyz(actor:GetActorRightVector()), up=xyz(actor:GetActorUpVector())} end,
        players=function(world)
            local cls = object("/Script/BlamSynchronization.BlamUnitComponent")
            if not cls then return {} end
            local out = {}
            for _, actor in ipairs(actors(world,SPARTAN)) do
                if valid(actor) and not actor.bHidden then
                    pcall(function()
                        local unit = actor:GetComponentByClass(cls)
                        if not valid(unit) or not unit:IsControlledByAnyPlayer() then return end
                        local pawn = unit:TryAndGetControllingPlayerPawn()
                        if not (valid(pawn) and pawn:IsLocallyControlled()) then return end
                        local datum = PackLifts.datum32(unit:GetControllingPlayerDatumIndex())
                        if datum ~= nil then
                            out[#out+1]={actor=actor,index=math.floor(datum%65536),key=actor:GetFullName()..":"..tostring(datum)}
                        end
                    end)
                end
            end
            return out
        end,
    }
end

local function identifier(s, pack)
    return type(s)=="string" and #s>=(pack and 2 or 1) and #s<=64
        and s:match(pack and "^[a-z0-9][a-z0-9%-]*$" or "^[a-z0-9][a-z0-9_%-]*$")~=nil
end
function PackLifts.new(deps, adapter)
    local api = adapter or engineAdapter()
    local lifts = { definitions={}, paths={}, raw=false }
    function lifts:setInventory(inventory)
        local defs, seen = {}, {}
        if type(inventory)=="table" and inventory.schema_version==1 and type(inventory.packs)=="table" and #inventory.packs<=64 then
            for _, pack in ipairs(inventory.packs) do
                local data = type(pack)=="table" and pack.forge_pack
                if type(data)=="table" and data.schema_version==1 and identifier(data.id,true) and pack.slug==data.id
                    and type(data.blocks)=="table" and #data.blocks<=256 then
                    for _, block in ipairs(data.blocks) do
                        if type(block)=="table" and identifier(block.id,false)
                            and block.tag=="objects\\mjolnir\\forge\\"..data.id.."\\"..block.id then
                            local path="/Game/MJOLNIR/Forge/"..data.id.."/BP_"..block.id..".BP_"..block.id.."_C"
                            if seen[path] then defs[path]=nil else
                                seen[path]=true
                                if PackLifts.validSpec(block.lift) then defs[path]=block.lift end
                            end
                        end
                    end
                end
            end
        end
        local paths={}
        for path in pairs(defs) do paths[#paths+1]=path end
        table.sort(paths)
        self.paths, self.definitions={}, {}
        for i=1,math.min(#paths,PackLifts.MAX_CLASSES) do
            self.paths[i]=paths[i]; self.definitions[paths[i]]=defs[paths[i]]
        end
    end
    function lifts:refresh()
        if not deps or not deps.inventoryPath then return end
        local file=io.open(deps.inventoryPath,"rb")
        local raw=file and file:read(4*1024*1024+1) or nil
        if file then file:close() end
        if raw==self.raw then return end
        self.raw=raw
        local ok, inventory=false,nil
        if raw and #raw<=4*1024*1024 then ok,inventory=pcall(deps.decode,raw) end
        self:setInventory(ok and inventory or nil)
    end
    function lifts:collect(world,canvas)
        local out={}
        for _, path in ipairs(self.paths) do
            local okActors, actors=pcall(api.actors,world,path)
            for _, actor in ipairs(okActors and actors or {}) do
                if #out>=PackLifts.MAX_ACTORS then return out end
                local ok, lift=pcall(function()
                    local datum=api.active(actor)
                    if datum==nil then return nil end
                    return PackLifts.transform(self.definitions[path],api.pose(actor),api.key(actor,datum),canvas)
                end)
                if ok and lift then out[#out+1]=lift end
            end
        end
        table.sort(out,function(a,b) return a.key<b.key end)
        return out
    end
    function lifts:players(world) return api.players(world) end
    return lifts
end
return PackLifts
