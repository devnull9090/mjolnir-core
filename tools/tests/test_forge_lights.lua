-- Exercises the actual UE adapter with fake reflected objects, including
-- attachment coordinates, candela units, pooling and world/inventory cleanup.
local Lights = dofile("mods/MJOLNIRForge/Scripts/lights.lua")
local checks = 0
local function eq(a, b)
    checks = checks + 1
    assert(a == b, "expected " .. tostring(b) .. ", got " .. tostring(a))
end
local serial = 0
local function object(name)
    serial = serial + 1
    return { name = name, address = serial, dead = false,
        IsValid = function(self) return not self.dead end,
        GetFullName = function(self) return self.name end,
        GetAddress = function(self) return self.address end }
end
local world = object("World")
package.preload.UEHelpers = function() return { GetWorld = function() return world end } end
FName = function(s) return s end
local classes, actors, created, destroyed = {}, {}, {}, 0
StaticFindObject = function(path) return classes[path] end
local function installClass(path) classes[path] = object(path); return classes[path] end
installClass("/Script/BlamSynchronization.BlamObjectSynchronizationComponent")
installClass("/Script/Engine.PointLightComponent")
local gs = installClass("/Script/Engine.Default__GameplayStatics")
local lastOutput
function gs:GetAllActorsOfClass(_, cls, out)
    if lastOutput then eq(out, lastOutput) end
    eq(next(out), nil)
    lastOutput = out
    for _, actor in ipairs(actors[cls.name] or {}) do out[#out + 1] = actor end
end
local function actor(name)
    local a = object(name)
    a.RootComponent = object("root")
    a.sync = { BlamObjectIndex = 123 }
    function a:K2_GetComponentsByClass() return { self.sync } end
    function a:AddComponentByClass(cls, manual, transform, deferred)
        eq(cls, classes["/Script/Engine.PointLightComponent"])
        eq(manual, true); eq(deferred, false); eq(transform.Scale3D.Z, 1)
        local c = object("light")
        function c:K2_AttachToComponent(parent, socket, location, rotation, scale, weld)
            self.parent = parent; eq(socket, "None"); eq(location, 0); eq(rotation, 0); eq(scale, 1); eq(weld, false)
            if a.failAttach then return false end
        end
        function c:K2_SetRelativeLocation(pos) self.position = pos end
        function c:SetIntensity(n) self.intensity = n end
        function c:SetAttenuationRadius(n) self.radius = n end
        function c:SetLightColor(color, srgb) self.color = color; eq(srgb, true) end
        function c:SetSourceRadius(n) self.source = n end
        function c:SetCastShadows(on) self.shadows = on end
        function c:SetHiddenInGame(on) self.hidden = on end
        function c:SetVisibility(on) self.visible = on end
        function c:K2_DestroyComponent() self.dead = true; destroyed = destroyed + 1 end
        created[#created + 1] = c
        return c
    end
    return a
end
local spec = { offset_m = { 1, -0.35, 3.1 }, color_rgb = { 1, 0.05, 0.03 }, intensity_cd = 70, radius_m = 8 }
local block = { id = "light_pylon_red", tag = "objects\\mjolnir\\forge\\foundry\\light_pylon_red", light = spec }
local pack = { slug = "foundry", forge_pack = { schema_version = 1, id = "foundry", blocks = { block } } }
local inventory = { schema_version = 1, packs = { pack } }
local path = "/Game/MJOLNIR/Forge/foundry/BP_light_pylon_red.BP_light_pylon_red_C"
local manager = Lights.new()
manager:setInventory(inventory)
eq(manager:tick(), 0) -- class has not loaded yet: retry next sweep
installClass(path)
local first = actor("lamp1")
actors[path] = { first }
eq(manager:tick(), 1)
local light = created[1]
eq(light.parent, first.RootComponent)
eq(light.position.X, 100); eq(light.position.Y, 35); eq(light.position.Z, 310)
eq(light.Mobility, 2); eq(light.IntensityUnits, 1); eq(light.bUseInverseSquaredFalloff, true)
eq(light.intensity, 70); eq(light.radius, 800); eq(light.color.G, 0.05)
eq(light.shadows, false); eq(light.visible, true); eq(light.hidden, false)
eq(manager:tick(), 1); eq(#created, 1) -- moving the parent needs no new lamp
first.sync.BlamObjectIndex = -1
eq(manager:tick(), 0); eq(destroyed, 1) -- pooled, still-valid actor has no light
first.sync.BlamObjectIndex = 4294967295
eq(manager:tick(), 0)
first.sync.BlamObjectIndex = 456
eq(manager:tick(), 1)
first.bHidden = true
eq(manager:tick(), 0)
first.bHidden = false
eq(manager:tick(), 1)
-- No method on a stale class/light wrapper is safe after world-package GC.
-- Poison them instead of merely returning false from IsValid: an actual
-- native dereference would crash before Lua could catch it.
local staleClass = classes[path]
staleClass.IsValid = function() error("stale Blueprint class was dereferenced") end
installClass(path)
local departingLight = created[#created]
local staleTouches = 0
local function staleAccess()
    staleTouches = staleTouches + 1
    error("departing-world wrapper was dereferenced")
end
departingLight.IsValid = staleAccess
departingLight.K2_DestroyComponent = staleAccess
world = object("World") -- same name, new object: forget old wrappers
local before = destroyed
eq(manager:tick(), 1); eq(destroyed, before)
eq(staleTouches, 0) -- also detect accesses whose Lua errors were swallowed
actors[path] = {}
for n = 1, 70 do actors[path][n] = actor(string.format("lamp%03d", n)) end
eq(manager:tick(), 64)
eq(manager:tick(), 64)
actors[path][1].dead = true
eq(manager:tick(), 64) -- a waiting lamp takes a released slot
manager:setInventory(nil)
eq(manager:tick(), 0)
manager:setInventory({ schema_version = 1, packs = { pack, pack } })
eq(manager:tick(), 0) -- conflicting identity cannot win by list order
manager:setInventory(inventory)
eq(manager:tick(), 64)
for _, entry in pairs(manager.live) do
    entry.light.IsValid = staleAccess
    entry.light.K2_DestroyComponent = staleAccess
    eq(entry.actor, nil)
end
world = nil
eq(manager:tick(), 0)
eq(staleTouches, 0)
world = object("World")
local broken = actor("cannot_attach"); broken.failAttach = true
actors[path] = { broken }
before = destroyed
eq(manager:tick(), 0)
eq(destroyed, before + 1) -- failed attachment cannot leak a lamp at the world origin
eq(created[#created].dead, true)
eq(Lights.validSpec(spec), true)
for key, bad in pairs({ offset_m = { 0, 101, 0 }, color_rgb = { 0, -0.1, 0 }, intensity_cd = 10001, radius_m = 101 }) do
    local s = {}; for k, value in pairs(spec) do s[k] = value end; s[key] = bad
    eq(Lights.validSpec(s), false)
end
eq(Lights.validSpec({}), false)
local s = {}; for key, value in pairs(spec) do s[key] = value end
s.offset_m = { 0 / 0, 0, 0 }; eq(Lights.validSpec(s), false)
s.offset_m = { 0, 0, 0 }; s.script = "never"; eq(Lights.validSpec(s), false)
print("Forge lights: " .. checks .. " checks passed")
