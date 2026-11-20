-- Native Enhanced Input consumes the equipped rider's mapped combat keys.
-- The transient context belongs to one local player and never edits their
-- profile. Arming it in the Pelican covers the frame of exit as well.
local Input = {}
local actions = { "FirePrimary", "FireSecondary", "FireTertiary", "MeleeAttack",
    "ThrowGrenade", "SwitchWeapon", "DropWeapon" }
local movement = {"MoveForward","MoveBackward","MoveLeft","MoveRight","Jump"}
local defaults = {MoveForward="W",MoveBackward="S",MoveLeft="A",MoveRight="D",Jump="SpaceBar"}
local keyCache = {}
local function key(name)
    if not keyCache[name] then keyCache[name]={KeyName=FName(name)} end
    return keyCache[name]
end
local options = { bIgnoreAllPressedKeysUntilRelease=false, bForceImmediately=true, bNotifyUserSettings=false }
local function valid(object) return object and object:IsValid() end

local function combatContext(subsystem, assets)
    local keys = {}
    for _,suffix in ipairs(actions) do
        local action = assets[suffix]
        if valid(action) then
            for _, value in ipairs(subsystem:QueryKeysMappedToAction(action) or {}) do
                local key = type(value)=="userdata" and value.get and value:get() or value
                local name = key.KeyName:ToString()
                if name ~= "None" then keys[name] = true end
            end
        end
    end
    if next(keys)==nil then return end
    local mapping = StaticConstructObject(StaticFindObject("/Script/EnhancedInput.InputMappingContext"),subsystem)
    if not valid(mapping) then return end
    local sink = StaticConstructObject(StaticFindObject("/Script/EnhancedInput.InputAction"),mapping)
    if not valid(sink) then return end
    sink.bConsumeInput = true
    for name in pairs(keys) do mapping:MapKey(sink,{ KeyName=FName(name) }) end
    subsystem:AddMappingContext(mapping,10000,options)
    return mapping
end

local function refreshBindings(c, assets)
    local bindings={}
    for _,action in ipairs(movement) do
        local keys={}
        local mappedAction=valid(c.subsystem) and valid(assets[action])
        if mappedAction then
            for _,v in ipairs(c.subsystem:QueryKeysMappedToAction(assets[action]) or {}) do
                local mapped = type(v)=="userdata" and v.get and v:get() or v
                local name = mapped.KeyName:ToString()
                if name~="None" then keys[#keys+1]=name end
            end
        end
        if not mappedAction then
            keys[1]=defaults[action]
            if action=="Jump" then keys[2]="Gamepad_FaceButton_Bottom" end
        end
        bindings[action]=keys
    end
    c.bindings=bindings
end

local function down(c,name)
    return c.controller:IsInputKeyDown(key(name))
end

local function pressed(c,action)
    for _,name in ipairs(c.bindings[action]) do
        local stickDirection = name=="Gamepad_LeftX" or name=="Gamepad_LeftY" or name:match("^Gamepad_LeftStick_")
        if (action=="Jump" or not stickDirection) and down(c,name) then return true end
    end
    return false
end

local function axis(c,positive,negative,stick)
    local digital=(pressed(c,positive) and 1 or 0)-(pressed(c,negative) and 1 or 0)
    if digital~=0 then return digital end
    local analog=c.controller:GetInputAnalogKeyState(key(stick))
    local magnitude=math.min(1,math.max(0,(math.abs(analog)-.18)/.82))
    return analog<0 and -magnitude or magnitude
end

local function jumpLabel(c)
    local pad = (valid(c.commonInput) and c.commonInput:GetCurrentInputType()==1) or false
    for _,name in ipairs(c.bindings.Jump) do
        if (name:sub(1,8)=="Gamepad_")==pad then
            if name=="SpaceBar" then return "SPACE",pad end
            local ok,label=pcall(function()
                local lib=StaticFindObject("/Script/Engine.Default__KismetInputLibrary")
                return lib:Key_GetDisplayName(key(name),false):ToString():upper()
            end)
            return ok and label or name:upper(),pad
        end
    end
    return "JUMP",pad
end

function Input.new(submit, blocked)
    local self, active, assets = {}, {}, nil
    local nextSample, hudHidden = 0, false
    local function release(user,c)
        if submit and c.sent then pcall(submit,user,c.unit,0,0,false,nil,false) end
        c.sent,c.right,c.brake,c.jumpDown=false,0,false,nil
    end
    local function remove(user)
        local context=active[user]
        if context then
            release(user,context)
            pcall(function()
                if valid(context.subsystem) and valid(context.mapping) then
                    context.subsystem:RemoveMappingContext(context.mapping,options)
                end
            end)
            active[user]=nil
        end
    end
    function self.clear()
        for user in pairs(active) do remove(user) end
        assets=nil
    end
    function self.tick(snapshot,pc,hidden)
        hudHidden=hidden
        if not snapshot or snapshot.phase==3 then self.clear(); return end
        local required={}
        for _,player in pairs(snapshot.players) do
            if player.localUser>=0 and (player.stage==2 or player.stage==7 or player.stage==3 or player.stage==4) then
                required[player.localUser]=player
            end
        end
        for user,context in pairs(active) do
            if not required[user] or required[user].unit~=context.unit or snapshot.instance~=context.instance
                or not valid(context.controller) then remove(user) end
        end
        for user,player in pairs(required) do
            if not active[user] then pcall(function()
                local gameplay=StaticFindObject("/Script/Engine.Default__GameplayStatics")
                local controller=gameplay:GetPlayerController(pc,user)
                if not valid(controller) or not controller:IsLocalController() then return end
                if not assets then
                    assets={}
                    local lib=StaticFindObject("/Script/Engine.Default__KismetSystemLibrary")
                    local load={}
                    for _,suffix in ipairs(actions) do load[#load+1]=suffix end
                    if submit then for _,suffix in ipairs(movement) do load[#load+1]=suffix end end
                    for _,suffix in ipairs(load) do
                        local name="IA_Blam"..suffix
                        local path="/Game/Input/Actions/BlamActions/"..name.."."..name
                        local ok,action=pcall(function()
                            return lib:LoadAsset_Blocking(lib:Conv_SoftObjPathToSoftObjRef(lib:MakeSoftObjectPath(path)))
                        end)
                        if ok then assets[suffix]=action end
                    end
                end
                local context={controller=controller,unit=player.unit,instance=snapshot.instance,gameplay=gameplay,nextBind=0}
                local lib=StaticFindObject("/Script/Engine.Default__SubsystemBlueprintLibrary")
                context.subsystem=lib:GetLocalPlayerSubSystemFromPlayerController(controller,
                    StaticFindObject("/Script/EnhancedInput.EnhancedInputLocalPlayerSubsystem"))
                if valid(context.subsystem) then
                    -- Failure to construct the optional combat-key sink must
                    -- not take mapped flight controls away from an unarmed rider.
                    local ok,mapping=pcall(combatContext,context.subsystem,assets)
                    if ok then context.mapping=mapping end
                end
                if submit then
                    pcall(function()
                        context.commonInput=lib:GetLocalPlayerSubSystemFromPlayerController(controller,
                            StaticFindObject("/Script/CommonInput.CommonInputSubsystem"))
                    end)
                end
                active[user]=context
            end) end
            if active[user] then active[user].stage=player.stage end
        end
    end
    function self.frame(now)
        if not submit or now<nextSample or not next(active) then return end
        nextSample=now+1/25
        local gated=hudHidden or (blocked and blocked())
        for user,c in pairs(active) do
            local ok=pcall(function()
                if gated or not valid(c.controller) or c.gameplay:IsGamePaused(c.controller) then
                    release(user,c); return
                end
                if now>=c.nextBind then
                    refreshBindings(c,assets)
                    local labelled,jump,pad=pcall(jumpLabel,c)
                    c.jumpLabel,c.pad=labelled and jump or "JUMP",labelled and pad
                    c.nextBind=now+1
                end
                local jump=pressed(c,"Jump")
                local edge=jump and c.jumpDown==false
                c.jumpDown=jump
                local forward=axis(c,"MoveForward","MoveBackward","Gamepad_LeftY")
                local right=axis(c,"MoveRight","MoveLeft","Gamepad_LeftX")
                local brake=c.stage==4 and (down(c,"LeftShift") or down(c,"RightShift") or down(c,"Gamepad_LeftThumbstick"))
                submit(user,c.unit,forward,right,brake,c.controller:GetControlRotation().Yaw,edge)
                c.right,c.brake,c.sent=right,brake,true
            end)
            if not ok then release(user,c) end
        end
    end
    function self.controls(user,unit)
        local c=active[user]
        if c and c.unit==unit then return c.right or 0,c.brake or false end
        return 0,false
    end
    function self.labels(user)
        local c=active[user]
        return c and c.jumpLabel or "SPACE", c and c.pad and "L3" or "SHIFT"
    end
    return self
end
return Input
