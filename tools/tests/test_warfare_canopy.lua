-- lua tools/tests/test_warfare_canopy.lua
local Canopy = dofile("mods/MJOLNIRHud/Scripts/warfare_canopy.lua")
local available, spawned, lookups = {}, {}, {}
local function valid(self) return not self.destroyed end
FName = function(s) return s end
StaticFindObject = function(path)
    if path:find("KismetSystemLibrary",1,true) then
        return { MakeSoftObjectPath=function(_,p) return p end, Conv_SoftObjPathToSoftObjRef=function(_,p) return p end,
            LoadAsset_Blocking=function(_,p)
                local key = p:match("%.([^%.]+)$")
                lookups[key]=(lookups[key] or 0)+1
                if available[key] then return { IsValid=valid, name=key } end
            end }
    end
    return path
end
local function nothing() end
local world = { SpawnActor=function()
    local comp = { SetCollisionEnabled=function(self,value) self.collision=value end,
        SetStaticMesh=function(self,value) self.mesh=value end, SetCastShadow=nothing,
        K2_SetRelativeLocationAndRotation=function(self,at,rot) self.offset=at; self.roll=rot.Roll end,
        SetRelativeScale3D=function(self,s) self.scale=s end,
        CreateDynamicMaterialInstance=function(self) self.override=true; return { IsValid=valid, SetVectorParameterValue=nothing } end }
    local actor={ StaticMeshComponent=comp, IsValid=valid,
        SetActorHiddenInGame=function(self,hidden) self.hidden=hidden end,
        K2_AttachToComponent=function(self,to) self.parent=to; return true end,
        K2_DetachFromActor=function(self) self.parent=nil; self.detached=true end,
        K2_SetActorLocationAndRotation=function(self,at) self.landedAt=at end,
        SetLifeSpan=function(self,n) self.life=n end, K2_DestroyActor=function(self) self.destroyed=true end }
    spawned[#spawned+1]=actor
    return actor
end }
local function body(address)
    return {GetWorld=function() return world end, GetAddress=function() return address end, RootComponent={},
        K2_GetActorLocation=function() return {X=12,Y=5,Z=340} end, K2_GetActorRotation=function() return {Yaw=35} end}
end
local biped, vehicle=body(42), body(43)
local live=true
local bindCount, restoreCount, holsters, draws=0,0,0,0
local grips={ start=function() bindCount=bindCount+1; return {} end,
    frame=nothing,
    holster=function() holsters=holsters+1; return {} end, unholster=function() draws=draws+1 end,
    stop=function(g) if g then restoreCount=restoreCount+1 end end }
local view = Canopy.new(function() if live then return {},vehicle,biped end end,grips)
local player = {stage=2,localUser=0,unit=123}
local snapshot={phase=1,instance="1",players={[0]=player}}
local function tick(stage,t) player.stage=stage; view.tick({players={}},snapshot,{},t) end
available={SM_PWR_ParachuteV2=true,SM_PWR_ParachutePackV2=true,SM_PWR_Parachute=true}
tick(2,0)
local pack=spawned[1]
assert(#spawned==1 and pack.parent==biped.RootComponent and pack.StaticMeshComponent.offset.Z==122)
assert(pack.StaticMeshComponent.mesh.name=="SM_PWR_ParachutePackV2")
tick(7,.2); tick(3,.4); tick(4,.6)
local canopy=spawned[2]
assert(#spawned==2 and canopy.StaticMeshComponent.mesh.name=="SM_PWR_ParachuteV2" and bindCount==1)
for _,a in ipairs(spawned) do assert(a.StaticMeshComponent.collision==0 and not a.StaticMeshComponent.override) end
assert(canopy.StaticMeshComponent.scale.X==1 and canopy.StaticMeshComponent.offset.Z==0)
view.frame(.8)
assert(canopy.StaticMeshComponent.offset.Z < -1, "line stretch should settle once after opening")
snapshot.flight={[0]={steer=1,brake=true}}
tick(4,1); view.frame(1.8)
assert(canopy.StaticMeshComponent.roll > 4.9 and canopy.StaticMeshComponent.offset.Z < -3)
snapshot.flight=nil
tick(4,1.9); view.frame(2.8)
assert(math.abs(canopy.StaticMeshComponent.roll)<.02 and math.abs(canopy.StaticMeshComponent.offset.Z)<.03)
tick(5,3); tick(5,3.1)
assert(#spawned==2 and #view.drops==1 and canopy.destroyed and restoreCount==1)
assert(holsters==1 and draws==1)
assert(pack.detached and pack.landedAt.Z==340 and pack.life==12 and not pack.destroyed)
tick(0,15.1)
assert(pack.destroyed and #view.drops==0)
-- Changing salted units while the same pooled biped exists must never credit a drop.
tick(3,13.5); local previous=spawned[#spawned]
player.unit=456; tick(5,14)
assert(previous.destroyed and not previous.detached and #view.drops==0)
tick(4,14.5); live=false; tick(5,15); live=true
assert(#view.drops==0 and next(view.actors)==nil)
for i=1,9 do
    snapshot.players={[i]=player}
    tick(4,15+i*.1); tick(5,15+i*.1+.05)
end
assert(#view.drops==8)
local oldest=view.drops[1].actor
view.hide(); assert(oldest.destroyed and #view.drops==0)
-- Legacy packages retain the measured transform and two material overrides.
available={SM_PWR_Parachute=true,BasicShapeMaterial=true}
snapshot.players={[0]=player}
tick(3,18); tick(4,19)
local old=spawned[#spawned]
assert(old.StaticMeshComponent.scale.X==4.1166 and old.StaticMeshComponent.offset.Z==274.4)
assert(old.StaticMeshComponent.override and old.StaticMeshComponent.mesh.name=="SM_PWR_Parachute")
local misses=lookups.SM_PWR_ParachuteV2
tick(4,20); tick(5,21); tick(4,22)
assert(lookups.SM_PWR_ParachuteV2==misses and #view.drops==0)
snapshot.phase=3; tick(4,23); assert(next(view.actors)==nil)
print("Warfare rigs: real biped, seated pack, canopy, grips, one grounded pack, cap, expiry, respawn, legacy fallback and teardown passed")
