-- Pure geometry plus injected actor discovery: no installed game required.
local Pack = dofile("mods/MJOLNIRLevelLoader/Scripts/pack_lifts.lua")
local Lifts = dofile("mods/MJOLNIRLevelLoader/Scripts/lifts.lua")
local function copy(x) if type(x)~="table" then return x end local y={} for k,v in pairs(x) do y[k]=copy(v) end return y end
assert(Pack.datum32(-482344751)==3812622545 and Pack.datum32(3812622545)==3812622545,"E34000D1 signed/unsigned identity")
assert(Pack.datum32(-2147483648)==2147483648 and Pack.datum32(0)==0 and Pack.datum32(4294967294)==4294967294)
for _, datum in ipairs({-1,4294967295,-2147483649,4294967296,1.5,-1.5,0/0,math.huge,-math.huge,"123",false}) do
    assert(Pack.datum32(datum)==nil,"invalid datum: "..tostring(datum))
end
assert(Pack.datum32(nil)==nil)
local spec={offset_m={0,0,.45},size_m={4,4,3.5},direction={0,0,1},acceleration_m_s2=20,max_speed_m_s=4.5,negates_gravity=true}
assert(Pack.validSpec(spec))
for _, change in ipairs({{"offset_m",{101,0,0}},{"size_m",{4,0,8}},{"size_m",{4,4,101}},
    {"direction",{0,0,0}},{"direction",{0,0,2}},{"max_speed_m_s",31},{"acceleration_m_s2",0},
    {"negates_gravity",1},{"script","anything"},{"offset_m",{0/0,0,0}}}) do
    local bad=copy(spec);bad[change[1]]=change[2];assert(not Pack.validSpec(bad),change[1])
end
local pose={position={1000,2000,3000},forward={1,0,0},right={0,1,0},up={0,0,1}}
local lift=assert(Pack.transform(spec,pose,"test",{1000,2000,3000}))
assert(Lifts.inside(lift,{0,0,50}),"standing on .5m deck activates")
assert(not Lifts.inside(lift,{0,0,44}),"beneath the deck is outside")
assert(Lifts.inside(lift,{199,199,394}) and not Lifts.inside(lift,{201,0,50}),"full4m box")
assert(not Lifts.inside(lift,{0,0,396}),"no force beyond column top")
assert(lift.direction[1]==2000 and lift.direction[2]==450)
local velocity=Lifts.push(lift,{0,0,50},{123,-45,0},.05)
assert(velocity[1]==123 and velocity[2]==-45,"preserve horizontal steering")
-- Full actor rotation: source+Z points along world+X after pitching the piece.
local tilted={position={0,0,0},forward={0,0,-1},right={0,1,0},up={1,0,0}}
lift=assert(Pack.transform(spec,tilted,"tilted"))
assert(Lifts.inside(lift,{100,0,0}) and not Lifts.inside(lift,{0,0,100}))
assert(lift.forward[1]==1 and lift.forward[3]==0)
assert(not Pack.transform(spec,{position={0,0,0}},"bad"))
local offset=copy(spec);offset.offset_m={1,2,.45}
local yaw={position={0,0,0},forward={0,1,0},right={-1,0,0},up={0,0,1}}
lift=assert(Pack.transform(offset,yaw,"yaw"))
assert(lift.origin[1]==200 and lift.origin[2]==100 and lift.origin[3]==45,"sourceY flip then actor yaw")

local block={id="lift",tag="objects\\mjolnir\\forge\\test-pack\\lift",lift=spec}
local inventory={schema_version=1,packs={{slug="test-pack",forge_pack={schema_version=1,id="test-pack",blocks={block}}}}}
local actor={datum=10,pose=pose}
local calls=0
local api={actors=function(world,path) calls=calls+1;return world.actors end,
    active=function(a)return a.datum end,key=function(a,d)return "actor:"..d end,
    pose=function(a)return a.pose end,players=function(world)return world.players end}
local pack=Pack.new(nil,api);pack:setInventory(inventory)
local world={actors={actor},players={}}
assert(#pack:collect(world)==1 and calls==1)
actor.pose=tilted
assert(pack:collect(world)[1].forward[1]==1,"moved/rotated actor updates next poll")
actor.datum=nil
assert(#pack:collect(world)==0,"pooled unbound actor is inactive")
actor.datum=11
assert(pack:collect(world)[1].key=="actor:11","pooled actor rebind has new identity")
assert(#pack:collect({actors={},players={}})==0,"no wrappers carried into next world")
local bad=copy(inventory);bad.packs[1].forge_pack.blocks[2]=copy(block)
pack:setInventory(bad);assert(#pack:collect(world)==0,"ambiguous duplicate tag disabled")
bad=copy(inventory);bad.packs[1].forge_pack.blocks[1].tag="objects\\other"
pack:setInventory(bad);assert(#pack:collect(world)==0,"cross-namespace alias disabled")
pack:setInventory(inventory)
world.actors={};for i=1,100 do world.actors[i]={datum=i,pose=pose} end
assert(#pack:collect(world)==64,"actor work bounded")

-- Exercise the real engine adapter. Global Blueprint scans and asset loads
-- are forbidden, even for absent classes; lookups resolve anew each call.
local engineActors,queries={},0
local function valid(o) o.IsValid=function()return true end;return o end
local component=valid({BlamObjectIndex=17})
local liveActor=valid({bHidden=false,GetFullName=function()return "actor" end,
    K2_GetComponentsByClass=function()return {component} end,
    K2_GetActorLocation=function()return {X=0,Y=0,Z=0} end,
    GetActorForwardVector=function()return {X=1,Y=0,Z=0} end,
    GetActorRightVector=function()return {X=0,Y=1,Z=0} end,
    GetActorUpVector=function()return {X=0,Y=0,Z=1} end})
local native={}
native["/Script/Engine.Default__KismetSystemLibrary"]=valid({
    MakeSoftClassPath=function(_,s)return s end,Conv_SoftClassPathToSoftClassRef=function(_,s)return s end,
    Conv_SoftClassReferenceToClass=function(_,s)queries=queries+1;return valid({path=s}) end,
    LoadClassAsset_Blocking=function()error("must not load assets") end})
native["/Script/Engine.Default__GameplayStatics"]=valid({GetAllActorsOfClass=function(_,w,cls,out)
    for i,a in ipairs(engineActors) do out[i]=a end end})
native["/Script/BlamSynchronization.BlamObjectSynchronizationComponent"]=valid({})
StaticFindObject=function(path) assert(path:match("^/Script/"),"global Blueprint scan");return native[path] end
FindAllOf=function()error("global actor scan") end
local real=Pack.new();real:setInventory(inventory);engineActors={liveActor}
assert(#real:collect({})==1 and #real:collect({})==1 and queries==2,"fresh nonloading class resolution")
component.BlamObjectIndex=-482344751
local signed=real:collect({});assert(#signed==1 and signed[1].key=="actor:3812622545","signed actor datum remains active")
component.BlamObjectIndex=3812622545
assert(real:collect({})[1].key==signed[1].key,"signed/unsigned representations share cache identity")
for _, badDatum in ipairs({-1,4294967295,-2147483649,4294967296,17.25}) do
    component.BlamObjectIndex=badDatum;assert(#real:collect({})==0,"invalid actor datum is inactive")
end
component.BlamObjectIndex=17
engineActors={};assert(#real:collect({})==0,"reused output table cleared")
native["/Script/BlamSynchronization.BlamUnitComponent"]=valid({})
local function player(localControl,index,datum)
    local pawn=valid({IsLocallyControlled=function()return localControl end})
    local unit=valid({IsControlledByAnyPlayer=function()return true end,
        TryAndGetControllingPlayerPawn=function()return pawn end,GetControllingPlayerDatumIndex=function()return datum or 65536+index end})
    return valid({bHidden=false,GetFullName=function()return "player"..index end,GetComponentByClass=function()return unit end})
end
engineActors={player(true,3),player(false,4)}
local mine=real:players({})
assert(#mine==1 and mine[1].index==3,"push only this peer's locally controlled player")
engineActors={player(true,3,-482344957),player(false,4,-482344956),player(true,5,-1),player(true,6,4294967295)}
mine=real:players({})
assert(#mine==1 and mine[1].index==3 and mine[1].key=="player3:3812622339","signed local player keeps its slot and full identity")
engineActors={player(true,3,3812622339)}
assert(real:players({})[1].key==mine[1].key,"player identity stable across signed/unsigned representation")
print("test_pack_lifts: ok")
