-- lua tools/tests/test_warfare_input.lua
local Input=dofile("mods/MJOLNIRHud/Scripts/warfare_input.lua")
local owners,added,removed,loaded={},0,0,0
local function valid() return true end
FName=function(s) return { ToString=function() return s end } end
local contexts = {}
for user=0,1 do
    local controller={IsValid=valid,IsLocalController=valid}
    local subsystem={IsValid=valid}
    subsystem.QueryKeysMappedToAction=function(_,a)
        local remap = a.path:find("FirePrimary",1,true) and (user==0 and "J" or "Gamepad_RightTrigger") or "Mouse4"
        return {{KeyName=FName(remap)}}
    end
    subsystem.AddMappingContext=function(_,m,priority,o)
        assert(priority>0 and o.bForceImmediately and not o.bNotifyUserSettings)
        contexts[user]=m;added=added+1
    end
    subsystem.RemoveMappingContext=function(_,m)
        assert(m==contexts[user]);contexts[user]=nil;removed=removed+1
    end
    owners[user]=controller;controller.subsystem=subsystem
end
StaticFindObject=function(path)
    if path:find("Default__GameplayStatics",1,true) then return {GetPlayerController=function(_,pc,u) return owners[u] end} end
    if path:find("Default__SubsystemBlueprintLibrary",1,true) then
        return {GetLocalPlayerSubSystemFromPlayerController=function(_,pc,_) return pc.subsystem end}
    end
    if path:find("Default__KismetSystemLibrary",1,true) then return {MakeSoftObjectPath=function(_,p)return p end,
        Conv_SoftObjPathToSoftObjRef=function(_,p)return p end,LoadAsset_Blocking=function(_,p)
            loaded=loaded+1;return {IsValid=valid,path=p}
        end} end
    return path
end
StaticConstructObject=function(cls,outer)
    if cls:find("InputMappingContext",1,true) then
        return {IsValid=valid,keys={}, MapKey=function(m,a,key)
            assert(a.bConsumeInput);m.keys[key.KeyName:ToString()]=true
        end}
    end
    return {IsValid=valid}
end
local input=Input.new()
local a={stage=2,localUser=0,unit=101}
local b={stage=2,localUser=1,unit=102}
local remote={stage=4,localUser=-1,unit=103}
local snapshot={phase=1,instance="one",players={[3]=a,[7]=b,[8]=remote}}
input.tick(snapshot,{})
assert(added==2 and removed==0)
assert(contexts[0].keys.J and not contexts[0].keys.Gamepad_RightTrigger)
assert(contexts[1].keys.Gamepad_RightTrigger and not contexts[1].keys.J)
assert(not contexts[0].keys.SpaceBar and not contexts[0].keys.W)
local initialLoad=loaded
a.stage=3; b.stage=4; input.tick(snapshot,{}); assert(added==2 and loaded==initialLoad)
a.stage=5; input.tick(snapshot,{}); assert(not contexts[0] and contexts[1] and removed==1)
b.unit=104; b.stage=0; input.tick(snapshot,{}); assert(removed==2)
a.stage=3; input.tick(snapshot,{}); assert(added==3)
input.tick(nil,{}); assert(removed==3)
input.clear(); assert(removed==3)
print("Warfare input: remapped combat bindings, independent local players, no remote/movement capture, one lock and one release per rider passed")

-- Drive the same input sampler the HUD calls with real directional action
-- names. Local controller zero is rebound to IJKL and gamepad one is analog.
do
    local original=StaticFindObject
    local menus,paused=false,false
    local sent={}
    StaticFindObject=function(path)
        if path:find("Default__GameplayStatics",1,true) then
            return {GetPlayerController=function(_,_,u) return owners[u] end,IsGamePaused=function() return paused end}
        end
        if path:find("Default__KismetInputLibrary",1,true) then
            return {Key_GetDisplayName=function(_,k) return k.KeyName end}
        end
        if path:find("Default__SubsystemBlueprintLibrary",1,true) then
            return {GetLocalPlayerSubSystemFromPlayerController=function(_,c,cls)
                if cls:find("CommonInputSubsystem",1,true) then
                    return {IsValid=valid,GetCurrentInputType=function() return c==owners[1] and 1 or 0 end}
                end
                return c.subsystem
            end}
        end
        return original(path)
    end
    local move={MoveForward="I",MoveBackward="K",MoveLeft="J",MoveRight="L"}
    for user=0,1 do
        local c=owners[user]
        c.held,c.analog={},{}
        c.subsystem.QueryKeysMappedToAction=function(_,asset)
            local suffix=asset.path:match("/IA_Blam(%w+)%.")
            if suffix=="Jump" then return {{KeyName=FName("U")},{KeyName=FName("Gamepad_FaceButton_Bottom")}} end
            return {{KeyName=FName(move[suffix] or "Mouse4")}}
        end
        function c:IsInputKeyDown(k) return self.held[k.KeyName:ToString()]==true end
        function c:GetInputAnalogKeyState(k) return self.analog[k.KeyName:ToString()] or 0 end
        function c:GetControlRotation() return {Yaw=-32} end
    end
    local input=Input.new(function(user,unit,f,r,brake,yaw,edge)
        sent[user]={unit=unit,f=f,r=r,brake=brake,yaw=yaw,edge=edge}
    end,function() return menus end)
    a.stage,b.stage=2,4
    input.tick(snapshot,{})
    input.frame(1)
    assert(input.labels(0)=="U" and select(2,input.labels(1))=="L3")
    local c=owners[0]
    c.held.I,c.held.J,c.held.U,c.held.LeftShift=true,true,true,true
    owners[1].held.Gamepad_LeftThumbstick=true
    owners[1].analog.Gamepad_LeftX=.59
    input.frame(1.05)
    assert(sent[0].f==1 and sent[0].r==-1 and sent[0].edge and sent[0].yaw==-32 and not sent[0].brake)
    assert(math.abs(sent[1].r-.5)<1e-6 and sent[1].brake)
    a.stage=4
    input.tick(snapshot,{})
    input.frame(1.10)
    assert(not sent[0].edge and sent[0].brake and input.controls(0,a.unit)==-1)
    menus=true;input.frame(1.16)
    assert(sent[0].f==0 and sent[0].r==0 and not sent[0].brake and not sent[1].brake)
    menus=false;input.frame(1.22)
    assert(not sent[0].edge,"a held key cannot deploy again when UI closes")
    c.held.U=false;c.held.I=false;c.held.J=false;c.held.LeftShift=false;c.held.W=true
    input.frame(1.28)
    assert(sent[0].f==0 and not sent[0].brake,"rebinding forward does not leave W active")
    c.held.RightShift=true; input.frame(1.34); assert(sent[0].brake)
    paused=true; input.frame(1.4); assert(not sent[0].brake)
    paused=false;c.held.U=true;input.frame(1.46);assert(not sent[0].edge)
    c.held.U=false;input.frame(1.52);c.held.U=true;input.frame(1.58);assert(sent[0].edge)
    a.stage,b.stage=5,5;input.tick(snapshot,{})
    assert(not sent[0].brake and not sent[1].brake and input.controls(0,a.unit)==0)
    StaticFindObject=original
end
print("Warfare flight controls: remapped input, two local seats, analog deadzone, held brake, jump edges, pause/UI release and landing passed")
