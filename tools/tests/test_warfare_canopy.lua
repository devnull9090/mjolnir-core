-- lua tools/tests/test_warfare_canopy.lua
local Canopy = dofile("mods/MJOLNIRHud/Scripts/warfare_canopy.lua")
local spawned, attached, collide, scale, offset = 0, 0, nil, nil, nil
local mesh = { IsValid = function() return true end }
FName = function(s) return s end
StaticFindObject = function(path)
    if path:find("KismetSystemLibrary", 1, true) then
        return { MakeSoftObjectPath = function(_, p) return p end,
            Conv_SoftObjPathToSoftObjRef = function(_, p) return p end,
            LoadAsset_Blocking = function() return mesh end }
    end
    return "StaticMeshActor"
end
local actor = { IsValid = function() return true end,
    SetActorHiddenInGame = function(self, hidden) self.hidden = hidden end,
    K2_AttachToComponent = function() attached = attached + 1; return true end,
    StaticMeshComponent = {
        SetCollisionEnabled = function(_, value) collide = value end,
        SetStaticMesh = function() end, SetCastShadow = function() end,
        CreateDynamicMaterialInstance = function() return { IsValid = function() return true end,
            SetVectorParameterValue = function() end } end,
        K2_SetRelativeLocationAndRotation = function(_, at) offset = at end,
        SetRelativeScale3D = function(_, value) scale = value end,
    } }
local world = { SpawnActor = function() spawned = spawned + 1; return actor end }
local pc = { GetWorld = function() return world end }
local body = { GetAddress = function() return 42 end, RootComponent = {} }
local cachedAlive = true
local view = Canopy.new(function() return cachedAlive and {} or nil, cachedAlive and body or nil end)
local s = { phase = 2, players = { [0] = { stage = 4, localUser = 0, unit = 123 } } }
view.tick({ players = {} }, s, pc, 0)
assert(spawned == 1 and attached == 1 and actor.hidden == false)
assert(collide == 0 and scale.X == 4.1166 and offset.Z == 274.4)
view.tick({ players = {} }, s, pc, .5)
assert(spawned == 1 and attached == 1, "engine attachment follows body without per-frame Lua motion")
s.players[0].unit = 456
view.tick({ players = {} }, s, pc, 1)
assert(attached == 2, "a new unit rebinds the canopy")
cachedAlive = false
view.tick({ players = {} }, s, pc, 1.5)
assert(actor.hidden, "a missing, dead or recycled cached body hides its canopy")
cachedAlive = true
s.players[0].stage = 5
view.tick({ players = {} }, s, pc, 2)
assert(actor.hidden, "landing hides canopy")
s.players[0].stage = 4
view.tick({ players = {} }, s, pc, 2.5)
view.hide()
assert(actor.hidden, "HUD hidden/world exit removes presentation")
print("Warfare canopy: collision disabled, native-stage-only display, cached attachment/rebind and cleanup passed")
