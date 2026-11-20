-- Offline behavior coverage: lua tools/tests/test_flux_runtime.lua
local Flux=dofile("mods/MJOLNIRLevelLoader/Scripts/flux_runtime.lua")
local Json=dofile("mods/MJOLNIRLevelLoader/Scripts/json.lua")
local function clone(v) if type(v)~="table" then return v end; local o={};for k,x in pairs(v) do o[k]=clone(x) end;return o end
local provenance={schema="mjolnir-flux-provenance-v1"}
for _,k in ipairs({"terrain_manifest_sha256","terrain_samples_sha256","water_geometry_sha256","capture_bed_sha256","settings_sha256"}) do provenance[k]=string.rep("a",64) end
local spec={id="river",playback="baked",domain={centre={100,-200,8000},res={128,256},cell=100,height=16000},
    origin={0,0,0},provenance=provenance}
spec.state={height="flux_state/river/height.exr",velocity="flux_state/river/velocity.exr",ground="flux_state/river/ground.exr",capture=4000,
    centre=clone(spec.domain.centre),res={128,256},cell=100,height_cm=16000,origin={0,0,0},provenance=clone(provenance)}
assert(Flux.fits(spec,spec.state))
for _,key in ipairs({"terrain_manifest_sha256","terrain_samples_sha256","water_geometry_sha256","capture_bed_sha256","settings_sha256"}) do
    local bad=clone(spec.state);bad.provenance[key]=string.rep("b",64);assert(not Flux.fits(spec,bad),key)
end
for _,badpath in ipairs({"../height.exr","flux_state/../height.exr","C:/height.exr","flux_state/river/height.png"}) do
    local bad=clone(spec.state);bad.height=badpath;assert(not Flux.fits(spec,bad))
end
local bad=clone(spec.state);bad.origin={0,0,1};assert(not Flux.fits(spec,bad))
bad=clone(spec.state);bad.centre={100,-200};assert(not Flux.fits(spec,bad))
bad=clone(spec.state);bad.capture=0/0;assert(not Flux.fits(spec,bad))
assert(Json.decode(Flux.encode(spec.state)).provenance.settings_sha256==provenance.settings_sha256)
assert(Json.decode(Flux.encode({message='a\n"\\b'})).message=='a\n"\\b')

local function fixture()
    local world={}; local pending={}; local spawned={}; local references={};local textureOK=true;local failFinish=false
    local function object(kind)
        local material={scalars={}}
        function material:SetScalarParameterValue(name,value) self.scalars[name]=value end
        local o={kind=kind,valid=true,Tags={},MaterialInstances={material}}
        function o:IsValid() return self.valid end
        function o:K2_DestroyActor() self.valid=false end
        function o:SetActorHiddenInGame(hidden) self.hidden=hidden end
        function o:SetSimulationState(state) self.SimulationState=state;self.initializations=(self.initializations or 0)+1 end
        return o
    end
    local current={level={canvas={origin={0,0,0}},decor={},_dir="fixture"},actors={},dressGen=0}
    local K={ImportFileAsTexture2D=function() local o=object("texture");o.valid=textureOK;return o end}
    local gs={BeginDeferredActorSpawnFromClass=function(_,_,kind,transform)
        local o=object(kind);o.transform=transform;spawned[#spawned+1]=o
        if kind:find("SimulationDomain") then
            o.SceneVisibility={};local cap={components={}}
            function cap:ClearShowOnlyComponents() self.components={} end
            function cap:ShowOnlyActorComponents(actor,children) self.components[#self.components+1]=actor end
            o.FluxHeightMapComponent={CaptureComponent=cap}
            function o:FindWorldModifiers() end
            function o:CaptureGroundHeightmap() self.captured=true end
        end
        return o end,
        FinishSpawningActor=function(_,o)
            if failFinish and o.kind:find("FluxSurface") then error("surface finish failure") end
            o.finished=true;o.finishedWave=o.OceanWaveActor;o.finishedState=o.SimulationState
            o.finishedMode=o.SurfaceMeshMode;o.finishedRT=o.UseRenderTarget
            o.finishedHeight=o.OceanWaveHeight;o.finishedLength=o.OceanWaveLength
            o.finishedChoppiness=o.OceanWaveChoppiness;o.finishedOffset=o.OceanWaveOffset
            return o end}
    local api={Current=current,modDir="fixture",getWorld=function() return world end,
        findObject=function(p) if p:find("Rendering") then return K else return gs end end,
        class=function(p) return p end,name=function(n)return n end,
        construct=function(kind,outer) local o=object(kind);o.outer=outer;references[#references+1]=o;return o end,
        delay=function(ms,callback)pending[#pending+1]={ms,callback} end,
        color=function()end,hide=function()end,log=function()end}
    return {api=api,world=world,current=current,pending=pending,spawned=spawned,refs=references,
        badTexture=function()textureOK=false end,badFinish=function()failFinish=true end}
end

-- Two independently retained states, no domain or modifier allocation at all.
local f=fixture();local second=clone(spec);second.id="lake"
Flux.start(f.api,f.world,{domains={spec,second}})
assert(#f.spawned==0 and #f.pending==1)
f.pending[1][2]()
assert(f.current.fluxRuntime.status=="ready" and #f.spawned==2 and #f.refs==2)
for _,o in ipairs(f.spawned) do
    assert(o.kind:find("FluxSurface_River") and not o.kind:find("SimulationDomain"))
    assert(o.initializations==1 and o.SimulationState.outer==o)
    assert(o.SimulationState.HeightWetMap.SRGB==false and o.SimulationState.VelocityDepthFoamMap.SRGB==false)
    assert(o.SimulationState.GroundMap.SRGB==false)
end
local report=Flux.status(f.current)
assert(#report.domains==2 and not report.domains[1].simulation_domain and report.domains[1].sources==0)
Flux.start(f.api,f.world,{domains={spec}});assert(#f.spawned==2)

-- Stale bake rejects the complete batch before a valid sibling can be spawned.
f=fixture();second=clone(spec);second.id="lake";second.state.provenance.capture_bed_sha256=string.rep("c",64)
assert(not pcall(Flux.start,f.api,f.world,{domains={spec,second}}));assert(#f.spawned==0)
-- Reload/travel invalidates callbacks even when UE still exposes the old world.
f=fixture();Flux.start(f.api,f.world,spec);f.current.fluxRuntime=nil;f.pending[1][2]();assert(#f.spawned==0)
-- Missing texture destroys the partially spawned surface, not a half-ready lake.
f=fixture();f.badTexture();Flux.start(f.api,f.world,spec);f.pending[1][2]()
assert(f.current.fluxRuntime.status=="failed" and not f.spawned[1].valid)
assert(next(f.current.actors)==nil)

-- Optional native lake swell retains the same bake and allocates no solver.
local lake=clone(spec);lake.id="lake"
lake.surface="/Game/FluidFlux/Surface/Templates/Coastline/BP_FluxSurface_Coastline.BP_FluxSurface_Coastline_C"
lake.ocean_wave={height_cm=18,length_cm=1800,choppiness=0,offset_cm=0,water_height_cm=5500}
lake.origin={1000,2000,300};lake.state.origin=clone(lake.origin)
local saved=Flux.encode(lake.state)
f=fixture();f.current.level.canvas.origin=clone(lake.origin)
Flux.start(f.api,f.world,lake);f.pending[1][2]()
assert(f.current.fluxRuntime.status=="ready" and #f.spawned==2 and #f.refs==1)
local wave,surface=f.spawned[1],f.spawned[2]
assert(wave.kind:find("BP_FluxOceanWave") and surface.kind:find("FluxSurface_Coastline"))
assert(wave.finishedRT==false and wave.finishedHeight==18 and wave.finishedLength==1800)
assert(wave.finishedChoppiness==0 and wave.finishedOffset==0)
assert(wave.transform.Translation.X==1100 and wave.transform.Translation.Y==1800 and wave.transform.Translation.Z==5800)
assert(surface.finishedWave==wave and surface.finishedState==surface.SimulationState and surface.finishedMode==5)
assert(surface.MaterialInstances[1].scalars.WaveDetailWPOScale==0)
assert(f.current.actors.__flux_v2_lake_wave==wave)
assert(Flux.status(f.current).domains[1].ocean_wave and not Flux.status(f.current).domains[1].simulation_domain)
assert(Flux.encode(lake.state)==saved,"Presentation must not rewrite bake metadata")
-- Exercise the actual loader reload teardown, including wave registration and
-- stale material callbacks, without loading the module's global side effects.
local file=assert(io.open("mods/MJOLNIRLevelLoader/Scripts/main.lua"));local loader=file:read("*a");file:close()
local body=assert(loader:match("local function clearActors%(%)\r?\n(.-)\r?\nend"))
local clearActors=assert(load("return function(Current)\n"..body.."\nend"))()
clearActors(f.current)
assert(not wave.valid and not surface.valid and next(f.current.actors)==nil and f.current.fluxRuntime==nil)
for i=2,#f.pending do f.pending[i][2]() end
assert(#f.spawned==2)
-- Errors after wave allocation destroy both registered actors; stale colour
-- callbacks cannot revive or mutate a failed/reloaded surface.
for _,failure in ipairs({"badTexture","badFinish"}) do
    f=fixture();f.current.level.canvas.origin=clone(lake.origin);f[failure]()
    Flux.start(f.api,f.world,lake);f.pending[1][2]()
    assert(f.current.fluxRuntime.status=="failed" and #f.spawned==2 and next(f.current.actors)==nil)
    for _,actor in ipairs(f.spawned) do assert(not actor.valid) end
end
-- All wave options are checked before the first domain, actor or callback.
for _,mutate in ipairs({
    function(s)s.playback="simulate" end,
    function(s)s.surface=nil end,
    function(s)s.ocean_wave.height_cm=0 end,
    function(s)s.ocean_wave.height_cm=51 end,
    function(s)s.ocean_wave.length_cm=0/0 end,
    function(s)s.ocean_wave.length_cm=math.huge end,
    function(s)s.ocean_wave.choppiness=-1 end,
    function(s)s.ocean_wave.offset_cm=51 end,
    function(s)s.ocean_wave.water_height_cm=9000 end,
    function(s)s.ocean_wave.length_cm=nil end,
    function(s)s.ocean_wave.UseRenderTarget=true end,
    function(s)s.domain.centre[1]=1000000 end,
}) do
    f=fixture();local invalid=clone(lake);mutate(invalid)
    assert(not pcall(Flux.start,f.api,f.world,{domains={spec,invalid}}))
    assert(#f.spawned==0 and #f.pending==0 and f.current.fluxRuntime==nil)
end
-- Authoring captures only explicit bed components, never streamed terrain or
-- architecture that was absent from the loader's actor dictionary.
f=fixture();local authoring=clone(spec);authoring.playback="simulate";authoring.state=nil;authoring.ground={"bed"}
local bed={Tags={},IsValid=function()return true end,SetActorHiddenInGame=function()end}
f.current.actors.bed=bed
Flux.start(f.api,f.world,authoring);f.pending[1][2]()
assert(f.current.fluxRuntime.status=="ready")
local domain=f.current.fluxRuntime.domains[1].domain
assert(domain.SceneVisibility.VisibilityMode_42_9273EC4643AD4C97A94CBCB277A4531E==1)
assert(domain.SceneVisibility.ActorsWithTags_47_FB1C9D8B486CC31A912C34BC8E3BB996=="None")
assert(domain.captured and #domain.FluxHeightMapComponent.CaptureComponent.components==1)
assert(domain.FluxHeightMapComponent.CaptureComponent.components[1]==bed)
-- Legacy compatibility is an explicit dispatcher choice, not accidental import.
assert(not pcall(Flux.domains,{domain=spec.domain}))
assert(loadfile("mods/MJOLNIRLevelLoader/Scripts/main.lua"))
-- The optical transition is opt-in and must resolve to another domain before
-- any scene objects are spawned. The game rehearsal also samples the GPU mask.
local upstream=clone(spec)
local downstream=clone(spec); downstream.id="coast"
upstream.surface_painter={from_domain="coast",start_ue_y_cm=-1000,end_ue_y_cm=0}
assert(#Flux.domains({domains={upstream,downstream}})==2)
do
    local fixture=fixture()
    local renderer=fixture.api.findObject("Rendering")
    local black={IsValid=function()return true end}
    local target={IsValid=black.IsValid,rows={}}
    local created,finished=0,0
    function renderer:CreateRenderTarget2D(world,width,height,format)
        assert(world==fixture.world and width==4 and height==1024 and format==6)
        created=created+1;return target
    end
    function renderer:BeginDrawCanvasToRenderTarget(_,rt,canvas,_,context)
        assert(rt==target);context.RenderTarget=rt
        canvas.Canvas={IsValid=black.IsValid,K2_DrawTexture=function(_,_,at,_,_,_,c)
            assert(not target.rows[at.Y]);target.rows[at.Y]=c.R
        end}
    end
    function renderer:EndDrawCanvasToRenderTarget(_,context)
        assert(context.RenderTarget==target);finished=finished+1
    end
    local lookup=fixture.api.findObject
    fixture.api.findObject=function(path) if path:find("White") then return black end;return lookup(path) end
    Flux.start(fixture.api,fixture.world,{domains={upstream,downstream}})
    fixture.pending[1][2]()
    local function prepare(material,seed)
        material.IsValid=black.IsValid
        material.tex=black;material.vectors={}
        for _,k in ipairs({"SurfaceScattering","SurfaceAbsorption","ColorBehind"}) do
            material.vectors[k.."0"]={R=seed,G=.1,B=.2,A=1}
        end
        function material:K2_GetTextureParameterValue()return self.tex end
        function material:SetTextureParameterValue(_,value)self.tex=value end
        function material:K2_GetVectorParameterValue(k)return self.vectors[k] or {R=0,G=0,B=0,A=0} end
        function material:SetVectorParameterValue(k,value)self.vectors[k]=value end
        return material
    end
    local up=prepare(fixture.spawned[1].MaterialInstances[1],.4)
    local down=prepare(fixture.spawned[2].MaterialInstances[1],.9)
    for i=2,#fixture.pending do fixture.pending[i][2]() end
    assert(created==1 and finished==1 and up.tex==target and down.tex==black)
    assert(up.vectors.SurfaceScattering0.R==.4 and up.vectors.SurfaceScattering1.R==.9)
    assert(up.vectors.WorldToPainterUV.G==-13000 and up.vectors.WorldToPainterUV.A==25600)
    assert(target.rows[470]==nil and target.rows[500]>.45 and target.rows[500]<.60 and target.rows[530]==1)
end
for _,change in ipairs({
    function(p)p.from_domain="missing" end,
    function(p)p.from_domain="river" end,
    function(p)p.start_ue_y_cm=1 end,
    function(p)p.start_ue_y_cm=0/0 end,
    function(p)p.end_ue_y_cm=nil end,
}) do
    local invalid=clone(upstream);change(invalid.surface_painter)
    f=fixture()
    assert(not pcall(Flux.start,f.api,f.world,{domains={invalid,downstream}}))
    assert(#f.spawned==0 and #f.pending==0)
end
print("Flux runtime: validation, two baked domains, lifetime, teardown and failure tests passed")
