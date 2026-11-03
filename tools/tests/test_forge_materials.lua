-- Exercise the real UE adapter: no game/UE runtime is required. These mocks
-- reject global Blueprint scans, stale wrappers and repeated material loads.
local Materials = dofile("mods/MJOLNIRForge/Scripts/materials.lua")
local Json = dofile("mods/MJOLNIRLevelLoader/Scripts/json.lua")
local file = assert(io.open("mods/MJOLNIRForge/Scripts/material_profiles.json"))
local profiles = Json.decode(file:read("*a")); file:close()
local checks, serial = 0, 0
local function eq(a, b)
    checks = checks + 1
    assert(a == b, "expected " .. tostring(b) .. ", got " .. tostring(a))
end
local function object(name)
    serial = serial + 1
    return {name=name, address=serial, IsValid=function(self) assert(not self.dead); return true end,
        GetFullName=function(self) assert(not self.dead); return self.name end,
        GetAddress=function(self) assert(not self.dead); return self.address end}
end
local world = object("WorldA")
local classes, actors, assets, lookups = {}, {}, {}, {}
local loads, created, reports, engineLookups = 0, {}, 0, 0
FName = function(name) return name end
FindAllOf = function() error("surface polling must not globally scan UObjects") end
StaticFindObject = function(path)
    assert(path:match("^/Script/"), "only native CDOs/classes may be cached")
    lookups[path] = (lookups[path] or 0) + 1
    return classes[path]
end
local engine = object("GameEngine")
local pc = object("PlayerController")
function pc:GetWorld() return world end
engine.GameViewport = {GameInstance={LocalPlayers={{PlayerController=pc}}}}
FindFirstOf = function(name) eq(name, "GameEngine"); engineLookups=engineLookups+1; return engine end
local function class(path) classes[path]=object(path); return classes[path] end
local syncClass = class("/Script/BlamSynchronization.BlamObjectSynchronizationComponent")
local meshClass = class("/Script/Engine.StaticMeshComponent")
local ksl = class("/Script/Engine.Default__KismetSystemLibrary")
function ksl:MakeSoftClassPath(path) return path end
function ksl:Conv_SoftClassPathToSoftClassRef(path) return path end
function ksl:Conv_SoftClassReferenceToClass(path) return classes[path] end
function ksl:LoadClassAsset_Blocking() error("must not load Blueprint classes while polling") end
function ksl:MakeSoftObjectPath(path) return path end
function ksl:Conv_SoftObjPathToSoftObjRef(path) return path end
function ksl:LoadAsset_Blocking(path) loads=loads+1; return assets[path] end
local gs = class("/Script/Engine.Default__GameplayStatics")
local outputRef
function gs:GetAllActorsOfClass(w, cls, output)
    eq(w, world); eq(cls, classes[cls.name]); eq(next(output), nil)
    if outputRef then eq(output, outputRef) end
    outputRef=output
    for _, a in ipairs(actors[cls.name] or {}) do output[#output+1]=a end
end
local function actor(name, binding)
    local a=object(name)
    a.sync={BlamObjectIndex=binding}; a.mesh=object(name.."Mesh"); a.mesh.StaticMesh=object("StaticMesh")
    function a.mesh:GetNumMaterials() return 9 end
    function a.mesh:CreateDynamicMaterialInstance(slot, parent, instanceName)
        eq(instanceName, "MJOLNIRForgeSurface"..slot)
        local mid=object("MID"); mid.slot=slot; mid.parent=parent; mid.params={}
        function mid:SetTextureParameterValue(key, value) self.params[key]=value end
        function mid:SetScalarParameterValue(key, value) self.params[key]=value end
        function mid:SetVectorParameterValue(key, value) self.params[key]=value end
        created[#created+1]=mid; a.mid=mid
        return mid
    end
    function a:K2_GetComponentsByClass(cls)
        assert(not self.dead)
        if cls==syncClass then return {self.sync} end
        eq(cls, meshClass); return {self.mesh}
    end
    return a
end
local root="/Game/MJOLNIR/Forge/test-pack"
local glassPath=root.."/BP_glass.BP_glass_C"
local portalPath=root.."/BP_portal.BP_portal_C"
class(glassPath); class(portalPath)
for _, name in ipairs({"M_ForgeGlassCyan", "M_ForgePortalGreen"}) do
    assets[root.."/Materials/"..name.."."..name]=object(name)
end
for _, name in ipairs({"T_PortalDust", "T_PortalMask"}) do
    assets[root.."/Textures/"..name.."."..name]=object(name)
end
local function block(id, slot, profile)
    return {id=id, tag="objects\\mjolnir\\forge\\test-pack\\"..id, surfaces={{slot=slot,profile=profile}}}
end
-- This is the launcher's installed.json shape: the release envelope wraps
-- its unchanged forge_pack catalog. A flattened fixture masks integration bugs.
local inventory={schema_version=1,packs={{slug="test-pack",version="0.2.0",sha256=string.rep("a",64),
    forge_pack={schema_version=1,id="test-pack",blocks={
    block("glass",7,"glass_cyan"),block("portal",8,"teleporter_green")}}}}}
local surfaces=Materials.new(profiles)
surfaces:setInventory(inventory)
local glass, portal=actor("glass", 0x12340001), actor("portal", 0x56780002)
actors[glassPath]={glass}; actors[portalPath]={portal}
eq(surfaces:tick(),2); eq(#created,2); eq(loads,6)
eq(glass.mid.slot,7); eq(glass.mid.params.Opacity,.24)
eq(glass.mid.params.GlassColor.G,.55)
eq(portal.mid.slot,8); eq(portal.mid.params.StageCount,4)
eq(portal.mid.params.Stage0UAnim.R,6); eq(portal.mid.params.Stage0UAnim.G,4)
eq(portal.mid.params.Stage1VAnim.B,0); eq(portal.mid.params.Stage1VAnim.A,-1)
eq(portal.mid.params.Map0,portal.mid.params.Map1)
eq(portal.mid.params.Map2,portal.mid.params.Map3)
for _=1,10 do eq(surfaces:tick(),2) end
eq(#created,2); eq(loads,6); eq(engineLookups,1)
for _, count in pairs(lookups) do eq(count,1) end
-- Hidden pool entries lose their assignment key; reactivation and salt reuse
-- both require a fresh MID. Stationary visible actors never do.
glass.bHidden=true; eq(surfaces:tick(),1); eq(#created,2)
glass.bHidden=false; eq(surfaces:tick(),2); eq(#created,3)
glass.sync.BlamObjectIndex=0x98760001; surfaces:tick(); eq(#created,4)
portal.sync.BlamObjectIndex=-1; eq(surfaces:tick(),1)
portal.sync.BlamObjectIndex=4294967295; eq(surfaces:tick(),1)
-- Travel invalidates every Blueprint/world wrapper. A second world resolves
-- classes anew; retaining any old actor/class/material object would assert.
world.dead=true; glass.dead=true; portal.dead=true
classes[glassPath].dead=true; classes[portalPath].dead=true
for _, asset in pairs(assets) do asset.dead=true end
world=object("WorldB"); class(glassPath); class(portalPath)
for path, value in pairs(assets) do assets[path]=object(value.name) end
glass=actor("glass",0x12340001); portal=actor("portal",0x56780002)
actors[glassPath]={glass}; actors[portalPath]={portal}
eq(surfaces:tick(),2); eq(#created,6)
-- A missing shader fails once for the entire class, including later pooled
-- actors in the same poll; it retries only on world/inventory change.
local oldPrint=print; print=function() reports=reports+1 end
assets[root.."/Materials/M_ForgeGlassCyan.M_ForgeGlassCyan"]=nil
actors[glassPath]={actor("newglass1",1),actor("newglass2",2)}
local before=loads
surfaces:tick(); eq(loads,before+1); eq(reports,1)
for _=1,5 do surfaces:tick() end
eq(loads,before+1); eq(reports,1)
assets[root.."/Materials/M_ForgeGlassCyan.M_ForgeGlassCyan"]=object("replacement")
surfaces:setInventory(inventory); eq(surfaces:tick(),3)
print=oldPrint
-- Malformed inventory and caller-supplied paths are ignored, never executed.
surfaces:setInventory({schema_version=1,packs={false,{slug="../evil",forge_pack={schema_version=1,id="../evil",blocks={}}},
    {slug="test-pack",blocks={block("glass",7,"glass_cyan")}},
    {slug="test-pack",forge_pack={schema_version=1,id="other-pack",blocks={block("glass",7,"glass_cyan")}}},
    {slug="test-pack",forge_pack={schema_version=1,id="test-pack",blocks={false,{},block("../escape",7,"glass_cyan")}}}}})
eq(next(surfaces.definitions),nil)
for _, invalid in ipairs({{},{{slot=7,profile="unknown"}},{{slot=-1,profile="glass_cyan"}},
    {{slot=16,profile="glass_cyan"}},{{slot=7.5,profile="glass_cyan"}},
    {{slot=7,profile="glass_cyan",path="/Game/Arbitrary"}},
    {{slot=7,profile="glass_cyan"},{slot=7,profile="teleporter_green"}}}) do
    eq(Materials.validSurfaces(invalid),false)
end
local disabled=Materials.new(nil,{world=function() error("invalid profiles must disable engine calls") end})
disabled:setInventory(inventory); eq(disabled:tick(),0)
-- The actor bound limits actual MID work, not only retained bookkeeping.
surfaces:setInventory(inventory); actors[portalPath]={}; actors[glassPath]={}
for i=1,300 do actors[glassPath][i]=actor("bulk"..i,i) end
before=#created; eq(surfaces:tick(),256); eq(#created-before,256)
before=#created; eq(surfaces:tick(),256); eq(#created,before)
print("Forge materials: "..checks.." checks passed")
