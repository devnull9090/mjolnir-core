-- Exercise existing H2 and new Forge providers through the single script writer.
local Lifts=dofile("mods/MJOLNIRLevelLoader/Scripts/lifts.lua")
local pending, sent={},{}
ExecuteInGameThreadWithDelay=function(ms,fn)assert(ms==50);pending[#pending+1]=fn end
local world={GetAddress=function()return 1 end}
local p={0,0,50}
local actor={K2_GetActorLocation=function()return {X=p[1],Y=p[2],Z=p[3]} end,
    GetVelocity=function()return {X=0,Y=0,Z=0} end,K2_GetActorRotation=function()return {Yaw=0} end}
local phantom={key="pack:1",asset="test",planes={{1,0,0,-200},{-1,0,0,-200},{0,1,0,-200},
    {0,-1,0,-200},{0,0,-1,45},{0,0,1,-395}},bounds={0,0,220,330},origin={0,0,45},forward={0,0,1},
    direction={2000,450},negates_gravity=true}
local dynamic={phantom}
local players={{actor=actor,index=3,key="player1"}}
local provider={refresh=function()end,collect=function()return dynamic end,players=function()return players end}
local current={level=nil}
Lifts.init({Current=current,PackLifts=provider,getWorld=function()return world end,Log=function()end,
    Script={send=function(lines)sent[#sent+1]=lines end}})
Lifts.tick();Lifts.tick();assert(#pending==1,"one fast loop even when tick repeats")
local function run()local f=table.remove(pending,1);assert(f);f() end
run();assert(#sent==1 and sent[1][1]:match("player_get 3"),"works without level metadata in Slayer")
local first=tonumber(sent[1][1]:match(" ([%d%.]+)%)$"))
run();assert(tonumber(sent[2][1]:match(" ([%d%.]+)%)$"))>first,"carry overcomes grounded biped velocity")
dynamic={};run();assert(#sent==2 and #pending==0,"deleted lift stops immediately")
-- A stock Halo2 level continues through the same script transport/provider.
current.level={lifts={phantom},canvas={origin={0,0,0}}};Lifts.tick();run()
assert(#sent==3,"H2 map phantom still works")
-- Travel before a scheduled callback: no stale actor access or second loop.
world=nil;actor.K2_GetActorLocation=function()error("stale world actor touched")end
run();assert(#pending==0 and #sent==3)
world={GetAddress=function()return 2 end};current.level=nil;players={};dynamic={phantom}
Lifts.tick();assert(#pending==0,"no local players means no push timer")
print("test_lifts_runtime: ok")
