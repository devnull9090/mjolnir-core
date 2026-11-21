-- Blend from the equipped Spartan's current pose into the two steering
-- toggles. The engine solves two-bone IK once on deployment. During the
-- short reach it interpolates joint rotations; attachment then holds the pose.
local Grips = {}
local COMPONENT = 1
local IDENTITY = { Translation = { X=0,Y=0,Z=0 }, Rotation = { X=0,Y=0,Z=0,W=1 },
    Scale3D = { X=1,Y=1,Z=1 } }
local function valid(obj) return obj and obj:IsValid() end
local function unwrap(obj) return type(obj) == "userdata" and obj.get and obj:get() or obj end
local function add(a,b,s)
    return { X=a.X+b.X*s, Y=a.Y+b.Y*s, Z=a.Z+b.Z*s }
end
local function sub(a,b) return add(a,b,-1) end
local function length(v) return math.sqrt(v.X*v.X+v.Y*v.Y+v.Z*v.Z) end
local function quat(value) return { X=value.X, Y=value.Y, Z=value.Z, W=value.W } end

-- Hide the held weapon's own meshes in both views. Separate actors carry
-- the equipped weapon, even when its first-person mesh follows the pawn.
-- Changing local visibility keeps inventory, ammo, and the spawn loadout.
function Grips.holster(body, user)
    local hidden, seen = {}, {}
    local function held(owner)
        if not valid(owner) then return end
        local actors = {}
        owner:GetAttachedActors(actors,true,false)
        local class = StaticFindObject("/Script/Engine.MeshComponent")
        for _, wrapped in ipairs(actors) do
            local actor = unwrap(wrapped)
            if valid(actor) and actor:GetClass():GetFName():ToString():find("Weapon",1,true) then
                for _, item in ipairs(actor:K2_GetComponentsByClass(class) or {}) do
                    local mesh = unwrap(item)
                    if valid(mesh) and mesh:IsVisible() and not mesh.bHiddenInGame and not seen[mesh:GetAddress()] then
                        seen[mesh:GetAddress()] = true
                        hidden[#hidden+1] = { mesh=mesh, weapon=actor }
                        mesh:SetVisibility(false,false)
                    end
                end
            end
        end
    end
    pcall(held,body)
    pcall(function()
        local gameplay=StaticFindObject("/Script/Engine.Default__GameplayStatics")
        local controller=gameplay:GetPlayerController(body,user)
        if valid(controller) and controller:IsLocalController() then held(controller.Pawn) end
    end)
    return hidden
end

function Grips.unholster(hidden)
    for _,entry in ipairs(hidden or {}) do pcall(function()
        if valid(entry.mesh) and valid(entry.weapon) and entry.mesh:GetOwner():GetAddress()==entry.weapon:GetAddress() then
            entry.mesh:SetVisibility(true,false)
        end
    end) end
end

local function restore(rig)
    if rig.hidden then pcall(function()
        if valid(rig.source) and rig.source:GetSkinnedAsset():GetAddress() == rig.mesh then
            rig.source:SetVisibility(true, false)
        end
    end) end
    if rig.pose then pcall(function() rig.pose:K2_DestroyComponent(rig.pose) end) end
    rig.pose, rig.hidden = nil, false
end

local function solve(rig, side, toggle, chute, mathLib, ik)
    local pose = rig.pose
    local function bone(name)
        local result = FName(name .. "_" .. side)
        assert(pose:GetBoneIndex(result) >= 0)
        return result
    end
    local function point(name) return pose:GetBoneLocationByName(name, COMPONENT) end
    local function rotate(name, q)
        rig.keys[#rig.keys+1] = { name=name, from=rig.start[name:ToString()], to=quat(q) }
        pose:SetBoneRotationByName(name, mathLib:Quat_Rotator(q), COMPONENT)
    end
    local function aim(name, child, vector)
        local source = sub(point(child),point(name))
        assert(length(source) > .1 and length(vector) > .1)
        local delta = mathLib:Quat_FindBetweenVectors(source, vector)
        rotate(name, mathLib:Multiply_QuatQuat(delta, pose:GetBoneTransformByName(name,COMPONENT).Rotation))
    end
    local function basis(x,y) return mathLib:Conv_RotatorToQuaternion(mathLib:MakeRotFromXY(x,y)) end
    local sh, el, wr = bone("Shoulder"), bone("Elbow"), bone("Wrist")
    local index, pinky = bone("IndexFinger1"), bone("PinkyFinger1")
    local fore, mid, hand = point(sh), point(el), point(wr)
    local palm = point(bone("MiddleFinger1"))
    local handSize = length(sub(palm,hand))
    local upper, lower = length(sub(mid,fore)), length(sub(hand,mid))
    assert(upper > 10 and upper < 80 and lower > 10 and lower < 80 and handSize > 2 and handSize < 20)
    local xf = pose:K2_GetComponentToWorld()
    local center = mathLib:InverseTransformLocation(xf, chute:GetSocketLocation(toggle))
    local function axis(v) return mathLib:InverseTransformDirection(xf,v) end
    local fwd = axis(chute:GetForwardVector())
    local right = axis(chute:GetRightVector())
    local up = axis(chute:GetUpVector())
    local mirror = side == "L" and 1 or -1
    -- Each toggle's bar runs across the palm. Put the base knuckles over
    -- it and bend the lower fingers around its 3.4 cm grip.
    local palmDir = add({X=fwd.X*.55,Y=fwd.Y*.55,Z=fwd.Z*.55}, up,.835)
    local knuckles = add(add(center,up,2.8), fwd,-2.0)
    local target = add(knuckles,palmDir,-handSize)
    local distance = length(sub(target,fore))
    assert(distance < upper+lower-.1 and distance > math.abs(upper-lower)+.1)
    local pole = add(add(fore,right,-mirror*42),up,-32)
    local desiredElbow, desiredWrist = {}, {}
    ik:K2_TwoBoneIK(fore,mid,hand,pole,target,desiredElbow,desiredWrist,false,1,1)
    aim(sh,el,sub(desiredElbow,fore))
    aim(el,wr,sub(target,point(el)))
    local currentBasis = basis(sub(point(bone("MiddleFinger1")),point(wr)), sub(point(index),point(pinky)))
    local desiredBasis = basis(palmDir, { X=right.X*mirror, Y=right.Y*mirror, Z=right.Z*mirror })
    local delta = mathLib:Multiply_QuatQuat(desiredBasis,mathLib:Quat_Inversed(currentBasis))
    rotate(wr,mathLib:Multiply_QuatQuat(delta,pose:GetBoneTransformByName(wr,COMPONENT).Rotation))
    for _, digit in ipairs({ "Index", "Middle", "Ring", "Pinky" }) do
        local prefix = digit .. "Finger"
        local first, second, third, tip = bone(prefix.."1"), bone(prefix.."2"), bone(prefix.."3"), bone(prefix.."4")
        aim(first,second,add(fwd,up,.22))
        local down = {X=-up.X,Y=-up.Y,Z=-up.Z}
        aim(second,third,add(down,fwd,.18))
        aim(third,tip,add(down,fwd,-1.4))
    end
    assert(length(sub(point(bone("MiddleFinger1")),knuckles)) < 3)
end

local function bind(owner, role, chute, mathLib, ik, rigs)
    if not valid(owner) then return end
    local skeletal = StaticFindObject("/Script/Engine.SkeletalMeshComponent")
    for _, entry in ipairs(owner:K2_GetComponentsByClass(skeletal) or {}) do
        local source = unwrap(entry)
        if source:GetClass():GetFName():ToString() == role and source:IsVisible() and not source.bHiddenInGame then
            local mesh = source:GetSkinnedAsset()
            if not valid(mesh) then return end
            local rig = { source=source, mesh=mesh:GetAddress(), keys={}, start={} }
            local ok, failure = pcall(function()
                local pose = owner:AddComponentByClass(StaticFindObject("/Script/Engine.PoseableMeshComponent"),
                    true, IDENTITY, false)
                rig.pose = pose
                assert(valid(pose))
                pose:SetVisibility(false,false)
                pose:SetCollisionEnabled(0)
                pose:SetSkinnedAssetAndUpdate(mesh,true)
                pose:SetCollisionEnabled(0)
                pose:SetCastShadow(false)
                pose:SetOnlyOwnerSee(source.bOnlyOwnerSee)
                pose:SetOwnerNoSee(source.bOwnerNoSee)
                for i=0,source:GetNumMaterials()-1 do pose:SetMaterial(i,source:GetMaterial(i)) end
                assert(pose:K2_AttachToComponent(source,FName("None"),2,2,2,false) ~= false)
                -- Keep the visual rooted to the handle assembly as the
                -- player's camera turns independently of the body.
                assert(pose:K2_AttachToComponent(chute,FName("None"),1,1,1,false) ~= false)
                pose:CopyPoseFromSkeletalComponent(source)
                for _, side in ipairs({"L","R"}) do
                    local names = {"Shoulder","Elbow","Wrist"}
                    for _, digit in ipairs({"Index","Middle","Ring","Pinky"}) do
                        for n=1,3 do names[#names+1]=digit.."Finger"..n end
                    end
                    for _, name in ipairs(names) do
                        local key = name.."_"..side
                        local id = FName(key)
                        assert(pose:GetBoneIndex(id)>=0)
                        rig.start[id:ToString()]=quat(pose:GetBoneTransformByName(id,COMPONENT).Rotation)
                    end
                    solve(rig,side,FName(side=="L" and "grip_l" or "grip_r"),chute,mathLib,ik)
                end
                for _, key in ipairs(rig.keys) do
                    pose:SetBoneRotationByName(key.name,mathLib:Quat_Rotator(key.from),COMPONENT)
                end
                pose:SetVisibility(true,false)
                rig.hidden=true
                source:SetVisibility(false,false)
            end)
            if ok then
                rigs[#rigs+1]=rig
                print("[MJOLNIR PWR] Bound parachute grips on " .. role)
                return true
            else
                print("[MJOLNIR PWR] Grip binding failed on " .. role .. ": " .. tostring(failure))
                restore(rig)
            end
            return
        end
    end
end

local function reportGripProjection(controller, chute)
    local layout = StaticFindObject("/Script/UMG.Default__WidgetLayoutLibrary")
    local size = layout:GetViewportSize(controller)
    local function project(name)
        local world = chute:GetSocketLocation(FName(name))
        local pixel = {}
        if not controller:ProjectWorldLocationToScreen(world, pixel, false) then
            return "unprojectable"
        end
        local inside = pixel.X >= 0 and pixel.X < size.X and pixel.Y >= 0 and pixel.Y < size.Y
        return string.format("(%.1f,%.1f) %s", pixel.X, pixel.Y, inside and "inside" or "outside")
    end
    print(string.format("[MJOLNIR PWR] FP grip projection viewport=%.0fx%.0f grip_l=%s grip_r=%s",
        size.X, size.Y, project("grip_l"), project("grip_r")))
end

function Grips.start(body, pc, user, actor, now)
    local rigs = {}
    local mathLib = StaticFindObject("/Script/Engine.Default__KismetMathLibrary")
    local ok, failure = pcall(function()
        local ik = StaticFindObject("/Script/AnimGraphRuntime.Default__KismetAnimationLibrary")
        local chute = actor.StaticMeshComponent
        if not valid(mathLib) or not valid(ik) or not chute:DoesSocketExist(FName("grip_l"))
            or not chute:DoesSocketExist(FName("grip_r")) then return end
        bind(body,"BPC_SkeletalMesh_C",chute,mathLib,ik,rigs)
        local gameplay = StaticFindObject("/Script/Engine.Default__GameplayStatics")
        local controller = gameplay:GetPlayerController(body,user)
        if valid(controller) and controller:IsLocalController()
            and bind(controller.Pawn,"BPC_FP_SkeletalMesh_C",chute,mathLib,ik,rigs) then
            local measured, reason = pcall(reportGripProjection, controller, chute)
            if not measured then print("[MJOLNIR PWR] FP grip projection unavailable: " .. tostring(reason)) end
        end
    end)
    if ok and #rigs > 0 then return { rigs=rigs, lib=mathLib, start=now, next=now } end
    print("[MJOLNIR PWR] No parachute grip rig bound: " .. tostring(failure or "mesh or grip sockets unavailable"))
    for _, rig in ipairs(rigs) do restore(rig) end
end

function Grips.frame(state,now)
    if state.done or now<state.next then return end
    state.next=now+1/24
    local t=math.min(1,math.max(0,(now-state.start)/.34))
    local alpha=t*t*(3-2*t)
    for _, rig in ipairs(state.rigs) do
        if rig.pose then
            local ok=pcall(function()
                for _, key in ipairs(rig.keys) do
                    local q=state.lib:Quat_Slerp(key.from,key.to,alpha)
                    rig.pose:SetBoneRotationByName(key.name,state.lib:Quat_Rotator(q),COMPONENT)
                end
            end)
            if not ok then restore(rig) end
        end
    end
    state.done=t>=1
end

function Grips.stop(state)
    if state then for _, rig in ipairs(state.rigs) do restore(rig) end end
end
return Grips
