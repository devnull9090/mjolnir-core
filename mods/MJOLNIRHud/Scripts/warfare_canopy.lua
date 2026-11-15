-- Original PWR canopy: a cosmetic actor attached once to the cached biped.
-- Unreal follows the attachment; Lua never moves it or scans for players.
-- Transform from levels/warfare/pwr/canopy/build.py's canopy.runtime.json.
local Canopy = {}
local MESH = "/Game/MJOLNIR/Maps/PWR/SM_PWR_Parachute.SM_PWR_Parachute"
local MATERIAL = "/Engine/BasicShapes/BasicShapeMaterial.BasicShapeMaterial"
local OFFSET, SCALE = { X = 0, Y = 0, Z = 274.4 }, 4.1166

local function valid(actor)
    local ok, yes = pcall(function() return actor and actor:IsValid() end)
    return ok and yes
end

local function load(path)
    local library = StaticFindObject("/Script/Engine.Default__KismetSystemLibrary")
    return library:LoadAsset_Blocking(library:Conv_SoftObjPathToSoftObjRef(library:MakeSoftObjectPath(path)))
end

function Canopy.new(bipedAt)
    local self = { actors = {} }
    local mesh, material, retryAt, hit = nil, nil, 0, {}
    local function hide(item)
        if item and valid(item.actor) then pcall(function() item.actor:SetActorHiddenInGame(true) end) end
    end

    function self.hide()
        for _, item in pairs(self.actors) do hide(item) end
    end

    function self.tick(match, snapshot, pc, now)
        if not snapshot or snapshot.phase == 3 then self.hide(); return end
        for index = 0, 15 do
            local p, item = snapshot.players[index], self.actors[index]
            local body
            if p and p.stage == 4 and p.localUser >= 0 then
                local _, actor = bipedAt(match.players[index], index)
                body = actor
            end
            if not body then
                hide(item)
            else
                local ok = pcall(function()
                    if not valid(mesh) then
                        if now < retryAt then return end
                        retryAt = now + 3
                        mesh, material = load(MESH), load(MATERIAL)
                        if not valid(mesh) then return end
                    end
                    if not item or not valid(item.actor) then
                        local actor = pc:GetWorld():SpawnActor(StaticFindObject("/Script/Engine.StaticMeshActor"),
                            { X = 0, Y = 0, Z = 0 }, { Pitch = 0, Yaw = 0, Roll = 0 })
                        item = { actor = actor }
                        self.actors[index] = item
                        actor:SetActorHiddenInGame(true)
                        local comp = actor.StaticMeshComponent
                        comp.Mobility = 2
                        comp:SetCollisionEnabled(0) -- donor body setup must never reach gameplay
                        comp:SetStaticMesh(mesh)
                        comp:SetCollisionEnabled(0)
                        comp:SetCastShadow(false)
                        if valid(material) then
                            for slot, colour in pairs({ [0] = { .16, .22, .11 }, [1] = { .06, .07, .055 } }) do
                                local mid = comp:CreateDynamicMaterialInstance(slot, material, FName("None"))
                                if valid(mid) then mid:SetVectorParameterValue(FName("Color"),
                                    { R = colour[1], G = colour[2], B = colour[3], A = 1 }) end
                            end
                        end
                    end
                    local address = body:GetAddress()
                    if item.unit ~= p.unit or item.body ~= address then
                        if item.actor:K2_AttachToComponent(body.RootComponent, FName("None"), 0, 0, 0, false) == false then
                            error("canopy attachment failed")
                        end
                        for key in pairs(hit) do hit[key] = nil end
                        local comp = item.actor.StaticMeshComponent
                        comp:K2_SetRelativeLocationAndRotation(OFFSET, { Pitch = 0, Yaw = 0, Roll = 0 }, false, hit, false)
                        comp:SetRelativeScale3D({ X = SCALE, Y = SCALE, Z = SCALE })
                        item.unit, item.body = p.unit, address
                    end
                    item.actor:SetActorHiddenInGame(false)
                end)
                if not ok then hide(item) end
            end
        end
    end
    return self
end
return Canopy
