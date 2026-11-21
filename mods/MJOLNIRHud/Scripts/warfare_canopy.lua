-- Native match stages drive these local cosmetic actors. Unreal attachments
-- follow the rider between samples. All positions are centimetres from feet.
local Canopy = {}
local ROOT = "/Game/MJOLNIR/Insertion/PWR/"
local function asset(name) return ROOT .. name .. "." .. name end
local CANOPY, PACK = asset("SM_PWR_ParachuteV2"), asset("SM_PWR_ParachutePackV2")
local LEGACY = "/Game/MJOLNIR/Maps/PWR/SM_PWR_Parachute.SM_PWR_Parachute"
local MATERIAL = "/Engine/BasicShapes/BasicShapeMaterial.BasicShapeMaterial"
local ZERO, ROT = { X = 0, Y = 0, Z = 0 }, { Pitch = 0, Yaw = 0, Roll = 0 }
local PACK_OFFSET, OLD_OFFSET = { X = -29, Y = 0, Z = 122 }, { X = 0, Y = 0, Z = 274.4 }
local PACK_SECONDS, MAX_DROPS = 12, 8

local function valid(obj)
    local ok, yes = pcall(function() return obj and obj:IsValid() end)
    return ok and yes
end

local function load(path)
    local library = StaticFindObject("/Script/Engine.Default__KismetSystemLibrary")
    return library:LoadAsset_Blocking(library:Conv_SoftObjPathToSoftObjRef(library:MakeSoftObjectPath(path)))
end

local function destroy(actor)
    if valid(actor) then pcall(function() actor:K2_DestroyActor() end) end
end

function Canopy.new(bipedAt, grips)
    local self = { actors = {}, drops = {} }
    local assets, hit, instance = {}, {}, nil
    local function outputHit()
        for key in pairs(hit) do hit[key] = nil end
        return hit
    end

    local function get(path)
        if assets[path] == nil then
            local ok, obj = pcall(load, path)
            assets[path] = ok and valid(obj) and obj or false
        end
        return assets[path]
    end

    local function attach(body, mesh, offset, scale, old)
        if not valid(mesh) then return nil end
        local actor = body:GetWorld():SpawnActor(StaticFindObject("/Script/Engine.StaticMeshActor"), ZERO, ROT)
        if not valid(actor) then return nil end
        local ok, failure = pcall(function()
            actor:SetActorHiddenInGame(true)
            local comp = actor.StaticMeshComponent
            comp.Mobility = 2
            comp:SetCollisionEnabled(0)
            assert(comp:SetStaticMesh(mesh) ~= false)
            comp:SetCollisionEnabled(0)
            comp:SetCastShadow(false)
            if old and valid(get(MATERIAL)) then
                for slot, colour in ipairs({ { .16, .22, .11 }, { .06, .07, .055 } }) do
                    local mid = comp:CreateDynamicMaterialInstance(slot - 1, get(MATERIAL), FName("None"))
                    if valid(mid) then mid:SetVectorParameterValue(FName("Color"),
                        { R = colour[1], G = colour[2], B = colour[3], A = 1 }) end
                end
            end
            assert(actor:K2_AttachToComponent(body.RootComponent, FName("None"), 0, 0, 0, false) ~= false)
            comp:K2_SetRelativeLocationAndRotation(offset, ROT, false, outputHit(), false)
            comp:SetRelativeScale3D({ X = scale, Y = scale, Z = scale })
            actor:SetActorHiddenInGame(false)
        end)
        if ok then return actor end
        print("[MJOLNIR PWR] Parachute attachment failed: " .. tostring(failure))
        destroy(actor)
    end

    local function clear(index)
        local item = self.actors[index]
        if item then
            if grips and item.weapons then grips.unholster(item.weapons) end
            if grips then grips.stop(item.grip) end
            destroy(item.canopy)
            destroy(item.pack)
            self.actors[index] = nil
        end
    end

    function self.hide()
        for index in pairs(self.actors) do clear(index) end
        for _, drop in ipairs(self.drops) do destroy(drop.actor) end
        self.drops, assets, instance = {}, {}, nil
    end

    local function dropPack(index, item, body, now)
        if not valid(item.pack) then return end
        local actor = item.pack
        local ok = pcall(function()
            local at, yaw = body:K2_GetActorLocation(), body:K2_GetActorRotation().Yaw
            -- Use the confirmed landing spot itself. Stepping sideways on a
            -- cliff or ramp can otherwise hang the cosmetic pack in mid-air.
            actor:K2_DetachFromActor(1, 1, 1)
            assert(actor:K2_SetActorLocationAndRotation({ X = at.X, Y = at.Y, Z = at.Z },
                { Pitch = 0, Yaw = yaw, Roll = 0 }, false, outputHit(), true) ~= false)
            actor:SetLifeSpan(PACK_SECONDS)
        end)
        if not ok then return end
        item.pack = nil
        print("[MJOLNIR PWR] Released landing pack for player " .. index)
        if #self.drops >= MAX_DROPS then destroy(table.remove(self.drops, 1).actor) end
        self.drops[#self.drops + 1] = { actor = actor, index = index, expires = now + PACK_SECONDS }
    end

    function self.tick(match, snapshot, pc, now)
        if not snapshot or snapshot.phase == 3 then self.hide(); return end
        if instance ~= snapshot.instance then self.hide(); instance = snapshot.instance end
        for i = #self.drops, 1, -1 do
            local drop = self.drops[i]
            if now >= drop.expires or not valid(drop.actor) then
                destroy(drop.actor)
                table.remove(self.drops, i)
            end
        end
        for index = 0, 15 do
            local p, item = snapshot.players[index], self.actors[index]
            local stage = p and p.localUser >= 0 and p.stage
            local wearing = stage == 2 or stage == 7 or stage == 3 or stage == 4
            local body
            if wearing or (item and stage == 5) then
                local _, actor, biped = bipedAt(match.players[index], index)
                body = biped or actor
            end
            local address = body and body:GetAddress()
            if item and (not address or item.unit ~= p.unit or item.body ~= address) then
                clear(index)
                item = nil
            end
            if wearing and body then
                if not item then
                    for i = #self.drops, 1, -1 do
                        if self.drops[i].index == index then destroy(table.remove(self.drops, i).actor) end
                    end
                    item = { body = address, unit = p.unit }
                    self.actors[index] = item
                    item.pack = attach(body, get(PACK), PACK_OFFSET, 1)
                    print("[MJOLNIR PWR] Player " .. index .. " pack attached=" .. tostring(valid(item.pack)))
                end
                if grips and (stage == 3 or stage == 4) and not item.weapons then
                    item.weapons = grips.holster(body, p.localUser)
                end
                if stage == 4 and item.stage ~= stage then
                    local mesh = get(CANOPY)
                    local old = not valid(mesh)
                    item.canopy = attach(body, old and get(LEGACY) or mesh, old and OLD_OFFSET or ZERO,
                        old and 4.1166 or 1, old)
                    print("[MJOLNIR PWR] Player " .. index .. " canopy attached=" .. tostring(valid(item.canopy)) .. " legacy=" .. tostring(old))
                    if not old and valid(item.canopy) and grips then
                        item.grip = grips.start(body, pc, p.localUser, item.canopy, now)
                        item.motion = { started=now, last=now, steer=0, brake=0, offset={X=0,Y=0,Z=0},
                            rotation={Pitch=0,Yaw=0,Roll=0} }
                    end
                elseif stage ~= 4 and item.canopy then
                    if grips then grips.stop(item.grip); item.grip = nil end
                    destroy(item.canopy)
                    item.canopy, item.motion = nil, nil
                end
                item.flight = snapshot.flight and snapshot.flight[index]
                item.stage = stage
            elseif item then
                if stage == 5 and (item.stage == 3 or item.stage == 4) then dropPack(index, item, body, now) end
                clear(index)
            end
        end
    end

    local function moveRig(item, now)
        local m = item.motion
        if not m or now - m.last < 1/30 then return end
        local elapsed, dt = now - m.started, now - m.last
        m.last = now
        local flight = item.flight
        local blend = 1 - math.exp(-10 * dt)
        local steer = flight and flight.steer or 0
        m.steer = m.steer + (steer - m.steer) * blend
        m.brake = m.brake + ((flight and flight.brake and 1 or 0) - m.brake) * blend
        -- A single impulse as the lines go taut, then quiet air in steady flight.
        local t = math.min(elapsed / .7, 1)
        local opening = (1 - t) * math.sin(t * math.pi)^2
        local roll = 5 * m.steer
        local drop = 4.0 * m.brake + 4.5 * opening
        local draw = -2.2 * m.brake - 1.5 * opening
        -- Pivot near the steering bars. Rolling around the feet makes the
        -- whole assembly slide sideways across the visor when turning.
        local gripHeight = 173
        local radians = math.rad(roll)
        local height = -drop + gripHeight * (1 - math.cos(radians))
        local at, rot = m.offset, m.rotation
        if math.abs(roll - rot.Roll) < .015 and math.abs(height - at.Z) < .025
            and math.abs(draw - at.X) < .025 then return end
        at.X, at.Y, at.Z = draw, -gripHeight*math.sin(radians), height
        rot.Roll = roll
        local ok = pcall(function()
            item.canopy.StaticMeshComponent:K2_SetRelativeLocationAndRotation(at, rot, false, outputHit(), false)
        end)
        if not ok then item.motion = nil end
    end

    function self.frame(now)
        if grips then
            for _, item in pairs(self.actors) do
                moveRig(item, now)
                if item.grip then grips.frame(item.grip, now) end
            end
        end
    end
    return self
end
return Canopy
