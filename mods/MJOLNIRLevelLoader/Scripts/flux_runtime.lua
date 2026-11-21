-- Explicit terrain-backed Flux domains. Baked playback creates surfaces only:
-- the installed domain's StopSimulation function controls its editor helper,
-- not runtime ticking. No simulation domain/modifiers are allocated for playback.
local Flux = {}
local hashes = {"terrain_manifest_sha256", "terrain_samples_sha256", "water_geometry_sha256",
    "capture_bed_sha256", "settings_sha256"}
local DOMAIN = "/Game/FluidFlux/Simulation/Blueprints/BP_FluxSimulationDomain.BP_FluxSimulationDomain_C"
local SURFACE = "/Game/FluidFlux/Surface/Templates/River/BP_FluxSurface_River.BP_FluxSurface_River_C"
local COASTLINE = "/Game/FluidFlux/Surface/Templates/Coastline/BP_FluxSurface_Coastline.BP_FluxSurface_Coastline_C"
local WAVE = "/Game/FluidFlux/Waves/Blueprints/BP_FluxOceanWave.BP_FluxOceanWave_C"
local STATE = "/Game/FluidFlux/Simulation/Blueprints/PDA_FluxSimulationState.PDA_FluxSimulationState_C"
local SOURCE = "/Game/FluidFlux/Simulation/Modifiers/BP_FluxModifierSourceActor.BP_FluxModifierSourceActor_C"
local simulationKeys={FoamFadeSpeed=true,FoamShallowGenerate=true,FoamShallowDepth=true,FoamWaveGenerate=true}
local waveLimits={height_cm={0.01,50},length_cm={100,10000},choppiness={0,1},offset_cm={-50,50},water_height_cm={-999000,999000}}

local function finite(n) return type(n)=="number" and n==n and math.abs(n)<math.huge end
local function vector(v,n)
    if type(v)~="table" or #v~=n then return false end
    for i=1,n do if not finite(v[i]) then return false end end
    return true
end
local function path(p)
    return type(p)=="string" and p:match("^flux_state/[%w_/-]+%.exr$") and not p:find("..",1,true)
end
local function equal(a,b,n,tolerance)
    if not vector(a,n) or not vector(b,n) then return false end
    for i=1,n do if math.abs(a[i]-b[i])>tolerance then return false end end
    return true
end
function Flux.validProvenance(p)
    if type(p)~="table" or p.schema~="mjolnir-flux-provenance-v1" then return false end
    for _,key in ipairs(hashes) do
        if type(p[key])~="string" or #p[key]~=64 or p[key]:find("[^0-9a-f]") then return false end
    end
    return true
end
function Flux.fits(spec, state)
    if type(state)~="table" or type(spec.domain)~="table" then return false,"state missing" end
    local d=spec.domain
    if not equal(state.centre,d.centre,3,0.999999) or not equal(state.res,d.res,2,0)
        or state.cell~=d.cell or state.height_cm~=d.height then return false,"domain changed" end
    if not path(state.height) or not path(state.velocity) or not path(state.ground) or not finite(state.capture) then return false,"state files/capture invalid" end
    if not Flux.validProvenance(spec.provenance) or not Flux.validProvenance(state.provenance) then return false,"terrain provenance missing" end
    for _,key in ipairs(hashes) do
        if state.provenance[key]~=spec.provenance[key] then return false,key.." changed" end
    end
    if not equal(state.origin,spec.origin or {0,0,0},3,0) then return false,"canvas origin changed" end
    return true
end
local function validateWave(s)
    local wave=s.ocean_wave
    if wave==nil then return end
    if s.playback~="baked" or s.surface~=COASTLINE or type(wave)~="table" then
        error("Flux ocean_wave requires baked playback and the explicit native Coastline surface")
    end
    for key in pairs(wave) do if not waveLimits[key] then error("Unknown Flux ocean_wave option: "..tostring(key)) end end
    for key,limits in pairs(waveLimits) do
        local value=wave[key]
        if not finite(value) or value<limits[1] or value>limits[2] then error("Invalid Flux ocean_wave option: "..key) end
    end
    local d=s.domain; local origin=s.origin or {0,0,0}
    if not vector(origin,3) then error("Invalid Flux ocean_wave origin") end
    local z=wave.water_height_cm+wave.offset_cm
    if z<d.centre[3]-d.height or z>d.centre[3] then error("Flux ocean_wave height is outside its captured domain") end
    local x,y=d.centre[1]+origin[1],d.centre[2]+origin[2]
    z=z+origin[3]
    -- Native Flux clamps state coordinates at a999999cm vector radius.
    if not finite(x*x+y*y+z*z) or x*x+y*y+z*z>=999000^2 then error("Flux ocean_wave world position exceeds native bounds") end
end
function Flux.domains(spec)
    local list=type(spec.domains)=="table" and spec.domains or {spec}
    if #list<1 or #list>8 then error("Flux requires 1..8 named domains") end
    local seen={}
    for _,s in ipairs(list) do
        local id=s.id or "main"
        if type(id)~="string" or not id:match("^[a-z][a-z0-9_]*$") or seen[id] then error("Invalid/duplicate Flux domain id") end
        seen[id]=true
        if s.playback~="baked" and s.playback~="simulate" then error("Flux playback must be baked or simulate") end
        local d=s.domain
        if type(d)~="table" or not vector(d.centre,3) or not vector(d.res,2)
            or not finite(d.cell) or d.cell<=0 or not finite(d.height) or d.height<=0 or d.height>32000 then error("Invalid Flux domain") end
        for _,n in ipairs(d.res) do
            if n<1 or n>1024 or n%1~=0 or math.log(n,2)%1>1e-9 then error("Flux resolution must be power-of-two <=1024") end
        end
        if not Flux.validProvenance(s.provenance) then error("Flux requires terrain/bed/water/settings hashes") end
        local painter=s.surface_painter
        if painter and (type(painter)~="table" or type(painter.from_domain)~="string" or painter.from_domain==id
            or not finite(painter.start_ue_y_cm) or not finite(painter.end_ue_y_cm)
            or painter.start_ue_y_cm>=painter.end_ue_y_cm) then error("Invalid spatial Flux painter") end
        for key,value in pairs(s.simulation or {}) do
            if not simulationKeys[key] or not finite(value) or value<0 then error("Invalid Flux simulation option: "..tostring(key)) end
        end
        validateWave(s)
        if s.playback=="baked" then local ok,why=Flux.fits(s,s.state); if not ok then error("Flux "..id..": "..why) end end
    end
    for _,s in ipairs(list) do
        if s.surface_painter and not seen[s.surface_painter.from_domain] then error("Flux painter references an unknown domain") end
    end
    return list
end

-- Small deterministic JSON writer for bake metadata/status (the loader's JSON
-- module is intentionally decode-only). No UObject or arbitrary tables enter it.
function Flux.encode(value)
    local kind=type(value)
    if kind=="string" then return '"'..value:gsub('[%z\1-\31\\"]',function(c)
        return string.format("\\u%04x",c:byte()) end)..'"' end
    if kind=="number" then assert(finite(value)); return string.format("%.17g",value) end
    if kind=="boolean" then return tostring(value) end
    assert(kind=="table","Unsupported Flux JSON value")
    local out={}
    if #value>0 then for _,v in ipairs(value) do out[#out+1]=Flux.encode(v) end; return "["..table.concat(out,",").."]" end
    local keys={}; for k in pairs(value) do keys[#keys+1]=k end; table.sort(keys)
    for _,k in ipairs(keys) do out[#out+1]=Flux.encode(k)..":"..Flux.encode(value[k]) end
    return "{"..table.concat(out,",").."}"
end

local function alive(a) return a and a:IsValid() end
local function hideFromCapture(api,a)
    -- Current.actors also retains audio/decal components; only Actors have Tags.
    return pcall(function() local tags=a.Tags; tags[#tags+1]=api.name("FluxHide") end)
end
local function xf(c,scale)
    return {Rotation={X=0,Y=0,Z=0,W=1},Translation=c,Scale3D={X=scale or 1,Y=scale or 1,Z=scale or 1}}
end
local function centre(d,origin) return {X=d.centre[1]+origin[1],Y=d.centre[2]+origin[2],Z=d.centre[3]+origin[3]} end
local function waveMaterial(api,surf)
    -- Coastline ships with a separate24cm detail displacement. Keep the
    -- explicitly requested swell amplitude isolated; normal ripples remain.
    local materials=surf.MaterialInstances
    for i=1,#materials do materials[i]:SetScalarParameterValue(api.name("WaveDetailWPOScale"),0) end
end

function Flux.importState(api,world,outer,spec,c)
    local ok,why=Flux.fits(spec,spec.state); if not ok then error(why) end
    local bs,d=spec.state,spec.domain
    local K=api.findObject("/Script/Engine.Default__KismetRenderingLibrary")
    local root=api.Current.level._dir or api.modDir
    local h=K:ImportFileAsTexture2D(world,root.."/"..bs.height)
    local v=K:ImportFileAsTexture2D(world,root.."/"..bs.velocity)
    local g=K:ImportFileAsTexture2D(world,root.."/"..bs.ground)
    if not alive(h) or not alive(v) or not alive(g) then error("Flux state textures missing") end
    h.SRGB=false; v.SRGB=false; g.SRGB=false
    local state=api.construct(api.class(STATE),outer)
    state.HeightWetMap=h; state.VelocityDepthFoamMap=v; state.GroundMap=g
    state.EncodeHeightMax=1; state.EncodeVelocityMax=1; state.Compression=false
    state.AreaLocation=c; state.AreaSize={X=d.res[1]*d.cell,Y=d.res[2]*d.cell,Z=d.height}
    state.Resolution={X=d.res[1],Y=d.res[2]}; state.CaptureOffset=bs.capture
    return state
end

-- Stock BP_FluxWorldPainterComponent uses this rectangle and texture to mix
-- color slots 0 and 1 on the native material. Paint once after both surfaces
-- have their final color values. The MID owns the texture through level travel.
local function spatialPainter(api,world,entry,domains)
    local p=entry.spec.surface_painter
    local source
    for _,d in ipairs(domains) do if d.id==p.from_domain then source=d.surface;break end end
    assert(alive(source) and alive(entry.surface),"Missing painter surface")
    local instances=entry.surface.MaterialInstances
    local sample=source.MaterialInstances[1]
    assert(alive(sample) and #instances>0,"Incomplete painter materials")
    local state=entry.surface.SimulationState
    local middle,area=state.AreaLocation,state.AreaSize
    local x0,y0=middle.X-area.X*.5,middle.Y-area.Y*.5
    assert(y0<=p.start_ue_y_cm and p.end_ue_y_cm<=y0+area.Y,"Painter ramp lies outside the river tile")
    local render=api.findObject("/Script/Engine.Default__KismetRenderingLibrary")
    local rows=1024
    local rt=render:CreateRenderTarget2D(world,4,rows,6,{R=0,G=0,B=0,A=0},false,false)
    assert(alive(rt),"Could not create Flux painter canvas")
    local function color(c) return {R=c.R,G=c.G,B=c.B,A=c.A} end
    local keys={"SurfaceScattering","SurfaceAbsorption","ColorBehind"}
    local originals={}
    local ok,reason=pcall(function()
        local canvas,size,context={},{},{}
        render:BeginDrawCanvasToRenderTarget(world,rt,canvas,size,context)
        local finish=context.RenderTarget and context or size.RenderTarget and size or {RenderTarget=rt}
        local drew,err=pcall(function()
            assert(canvas.Canvas and canvas.Canvas:IsValid(),"Missing Flux painter canvas")
            local white=api.findObject("/Engine/EngineResources/WhiteSquareTexture.WhiteSquareTexture")
            if not alive(white) then white=api.findObject("/Engine/EngineResources/WhiteTexture.WhiteTexture") end
            if not alive(white) then white=nil end
            local first=math.max(0,math.floor((p.start_ue_y_cm-y0)/area.Y*rows))
            for row=first,rows-1 do
                local y=y0+(row+.5)*area.Y/rows
                local t=math.max(0,math.min(1,(y-p.start_ue_y_cm)/(p.end_ue_y_cm-p.start_ue_y_cm)))
                t=t*t*(3-2*t)
                -- UCanvas uses GWhiteTexture for a null render texture.
                canvas.Canvas:K2_DrawTexture(white,{X=0,Y=row},{X=4,Y=1},{X=0,Y=0},{X=1,Y=1},
                                            {R=t,G=t,B=t,A=t},0,0,{X=0,Y=0})
            end
        end)
        render:EndDrawCanvasToRenderTarget(world,finish)
        assert(drew,tostring(err))
        for i=1,#instances do
            local material=instances[i]
            local old={m=material,tex=material:K2_GetTextureParameterValue(api.name("PainterTexture")),vectors={}}
            table.insert(originals,old)
            local function set(k,v)
                local n=api.name(k)
                old.vectors[k]=color(material:K2_GetVectorParameterValue(n))
                material:SetVectorParameterValue(n,v)
            end
            material:SetTextureParameterValue(api.name("PainterTexture"),rt)
            set("WorldToPainterUV",{R=x0,G=y0,B=area.X,A=area.Y})
            for _,k in ipairs(keys) do set(k.."1",color(sample:K2_GetVectorParameterValue(api.name(k.."0")))) end
        end
    end)
    if not ok then
        for _,old in ipairs(originals) do
            old.m:SetTextureParameterValue(api.name("PainterTexture"),old.tex)
            for k,v in pairs(old.vectors) do old.m:SetVectorParameterValue(api.name(k),v) end
        end
        render:ReleaseRenderTarget2D(rt)
        error(reason)
    end
    entry.painter_target=rt
end

function Flux.start(api,world,spec)
    local current=api.Current
    if current.fluxRuntime then return end
    local domains=Flux.domains(spec) -- Fail before spawning anything.
    local level=current.level
    local origin=(level.canvas or {}).origin or {0,0,0}
    for _,s in ipairs(domains) do
        if not equal(s.origin or {0,0,0},origin,3,0) then error("Flux spec canvas origin changed") end
    end
    local run={status="pending",domains={},level=level}
    current.fluxRuntime=run
    -- UE4SS can wrap the same UWorld in different userdata on each lookup.
    -- These loader-owned identities are invalidated by both travel and reload.
    local function fresh() return current.fluxRuntime==run and current.level==level end
    api.delay(tonumber(spec.delay_ms) or 4000,function()
        if not fresh() then return end
        local keys={}
        local function register(key,a)
            if not alive(a) then error("Flux could not spawn "..key) end
            current.actors[key]=a; keys[#keys+1]=key
            hideFromCapture(api,a)
            return a
        end
        local ok,err=pcall(function()
            local gs=api.findObject("/Script/Engine.Default__GameplayStatics")
            local keep,simulating={},false
            for _,s in ipairs(domains) do if s.playback=="simulate" then
                simulating=true
                if type(s.ground)~="table" or #s.ground==0 then error("Flux simulation requires explicit capture ground") end
                for _,id in ipairs(s.ground) do
                    if not alive(current.actors[id]) then error("Flux capture bed missing: "..id) end
                    keep[id]=true
                end
            end end
            if simulating then
                for id,a in pairs(current.actors) do
                    if keep[id] then a:SetActorHiddenInGame(false)
                    elseif alive(a) then hideFromCapture(api,a) end
                end
            end
            for _,s in ipairs(domains) do
                local id=s.id or "main"
                local key="__flux_v2_"..id
                local c=centre(s.domain,origin)
                local wave
                if s.ocean_wave then
                    local q=s.ocean_wave
                    local wc={X=c.X,Y=c.Y,Z=q.water_height_cm+origin[3]}
                    wave=register(key.."_wave",gs:BeginDeferredActorSpawnFromClass(world,api.class(WAVE),xf(wc),1,nil,0))
                    wave.UseRenderTarget=false
                    wave.OceanWaveHeight=q.height_cm; wave.OceanWaveLength=q.length_cm
                    wave.OceanWaveChoppiness=q.choppiness; wave.OceanWaveOffset=q.offset_cm
                    gs:FinishSpawningActor(wave,xf(wc),0)
                end
                local surf=register(key.."_surface",gs:BeginDeferredActorSpawnFromClass(world,api.class(s.surface or SURFACE),xf(c),1,nil,0))
                local entry={id=id,playback=s.playback,status="starting",spec=s,surface=surf,wave=wave,sources=0}
                run.domains[#run.domains+1]=entry
                if s.playback=="baked" then
                    local state=Flux.importState(api,world,surf,s,c)
                    surf.SimulationState=state -- retained before BeginPlay
                    if wave then surf.SurfaceMeshMode=5; surf.OceanWaveActor=wave end
                    gs:FinishSpawningActor(surf,xf(c),0)
                    -- Cooked SetSimulationState(State) assigns the reference and
                    -- calls InitializeStates; no guessed Blueprint entrypoint.
                    surf:SetSimulationState(state)
                    if wave then waveMaterial(api,surf) end
                    entry.status="baked"; entry.state=state
                else
                    gs:FinishSpawningActor(surf,xf(c),0)
                    local dom=register(key.."_domain",gs:BeginDeferredActorSpawnFromClass(world,api.class(DOMAIN),xf(c),1,nil,0))
                    local d=s.domain
                    dom.AreaResolution={X=d.res[1],Y=d.res[2]}; dom.AreaWorldPixelSize=d.cell
                    dom.AreaWorldHeight=d.height; dom.SurfaceActorReference=surf
                    for field,value in pairs(s.simulation or {}) do dom[field]=value end
                    dom.HeightmapUpdateFrequency=1000000
                    local visibility=dom.SceneVisibility
                    -- Strict component allowlist: a tag exclusion list cannot
                    -- exclude streamed Landscape or native overhead geometry.
                    visibility.VisibilityMode_42_9273EC4643AD4C97A94CBCB277A4531E=1
                    visibility.ActorsWithTags_47_FB1C9D8B486CC31A912C34BC8E3BB996=api.name("None")
                    visibility.UseInstancedMeshes_64_5640381C4A7506AD66F872A101E54AB7=false
                    visibility.UseFoliageMeshes_63_108019E4475E89156CB35DA9D2A91E33=false
                    dom.SceneVisibility=visibility
                    local baked=Flux.fits(s,s.state)
                    if baked then dom.InitialState=Flux.importState(api,world,dom,s,c) end
                    gs:FinishSpawningActor(dom,xf(c),0)
                    local capture=dom.FluxHeightMapComponent.CaptureComponent
                    capture:ClearShowOnlyComponents()
                    for _,ground in ipairs(s.ground) do capture:ShowOnlyActorComponents(current.actors[ground],true) end
                    entry.domain=dom; entry.status="simulating"
                    local primers,modifiers={},{}
                    for i,q in ipairs(s.sources or {}) do if not (baked and q.prime) then
                        assert(vector(q.pos,3),"Flux source needs position")
                        local p={X=q.pos[1]+origin[1],Y=q.pos[2]+origin[2],Z=q.pos[3]+origin[3]}
                        local actor=register(key.."_source_"..i,gs:BeginDeferredActorSpawnFromClass(world,api.class(SOURCE),xf(p,q.scale),1,nil,0))
                        gs:FinishSpawningActor(actor,xf(p,q.scale),0)
                        local modifier=actor.FluxModifierSource
                        modifier.Duration=tonumber(q.duration) or -1; modifier.Volume=tonumber(q.volume) or 1
                        modifier.Mode=tonumber(q.mode) or 2
                        if q.velocity then modifier.Velocity={X=q.velocity[1],Y=q.velocity[2]} end
                        modifiers[#modifiers+1]=modifier; entry.sources=entry.sources+1
                        if q.prime then primers[#primers+1]=actor end
                    end end
                    dom:FindWorldModifiers(true)
                    for _,m in ipairs(modifiers) do m:UpdateMaterial() end
                    dom:CaptureGroundHeightmap(true)
                    api.delay(tonumber(s.prime_ms) or 60000,function()
                        if not fresh() or not alive(dom) then return end
                        for _,actor in ipairs(primers) do if alive(actor) then actor:K2_DestroyActor(); entry.sources=entry.sources-1 end end
                        dom:FindWorldModifiers(true)
                        entry.status="settled_pending_review"
                        api.log("flux "..id..": primers removed; inspect flow before baking")
                    end)
                end
                api.delay(2000,function()
                    if fresh() and alive(surf) then
                        local painted,why=pcall(function()
                            api.color(surf,s)
                            if type(s.surface_scalars)=="table" then
                                local materials=surf.MaterialInstances
                                for i=1,#materials do for scalar,value in pairs(s.surface_scalars) do
                                    materials[i]:SetScalarParameterValue(api.name(scalar),value)
                                end end
                            end
                            if wave then waveMaterial(api,surf) end
                        end)
                        if not painted then entry.color_error=tostring(why);api.log("flux "..id.." color: "..tostring(why)) end
                    end
                end)
                api.hide(s)
            end
            api.hide(spec)
            api.delay(3000,function()
                if not fresh() then return end
                for _,entry in ipairs(run.domains) do
                    if entry.spec.surface_painter then
                        local painted,why=pcall(spatialPainter,api,world,entry,run.domains)
                        if not painted then entry.color_error=tostring(why);api.log("flux "..entry.id.." painter: "..tostring(why)) end
                    end
                end
                for _,item in ipairs(level.decor or {}) do
                    local a=item.capture_only and current.actors[item.id]
                    if alive(a) then a:SetActorHiddenInGame(true) end
                end
            end)
            run.status="ready"
            api.log("flux: "..#run.domains.." terrain-backed domain(s) ready")
        end)
        if not ok then
            for i=#keys,1,-1 do local key=keys[i]; local a=current.actors[key]; if alive(a) then pcall(function() a:K2_DestroyActor() end) end; current.actors[key]=nil end
            run.status="failed"; run.error=tostring(err)
            api.log("flux: failed: "..tostring(err))
        end
    end)
end

function Flux.status(current)
    local run=current.fluxRuntime
    if not run then return {status="legacy_or_absent"} end
    local out={status=run.status,domains={}}
    if run.error then out.error=run.error end
    for _,e in ipairs(run.domains) do out.domains[#out.domains+1]={id=e.id,playback=e.playback,status=e.status,
        sources=e.sources,surface_valid=not not alive(e.surface),simulation_domain=not not alive(e.domain),
        ocean_wave=not not alive(e.wave)} end
    return out
end

function Flux.bake(api,id)
    local run=api.Current.fluxRuntime
    if not run or run.status~="ready" then return "no ready terrain-backed Flux domains" end
    local K=api.findObject("/Script/Engine.Default__KismetRenderingLibrary")
    local world=api.getWorld(); local count=0
    for _,e in ipairs(run.domains) do if not id or id=="all" or id==e.id then
        if not alive(e.domain) then error("Flux "..e.id.." is baked playback, not a simulation") end
        local state,d=e.domain.CurrentState,e.spec.domain
        local relative="flux_state/"..e.id
        local dir=(api.Current.level._dir or api.modDir).."/"..relative
        local rt=K:CreateRenderTarget2D(world,d.res[1],d.res[2],6,{R=0,G=0,B=0,A=0},false,false)
        local outs,size,context={},{},{}
        K:BeginDrawCanvasToRenderTarget(world,rt,outs,size,context)
        outs.Canvas:K2_DrawTexture(state.HeightWetMap,{X=0,Y=0},{X=d.res[1],Y=d.res[2]},{X=0,Y=0},{X=1,Y=1},{R=1,G=1,B=1,A=1},0,0,{X=0,Y=0})
        K:EndDrawCanvasToRenderTarget(world,context)
        K:ExportRenderTarget(world,rt,dir,"height.exr")
        K:ExportRenderTarget(world,state.VelocityDepthFoamMap,dir,"velocity.exr")
        -- The state binds Ground to water/underwater materials as well. Export
        -- it through RGBA16F: this UE version exports other RT formats as PNG.
        K:BeginDrawCanvasToRenderTarget(world,rt,outs,size,context)
        outs.Canvas:K2_DrawTexture(state.GroundMap,{X=0,Y=0},{X=d.res[1],Y=d.res[2]},{X=0,Y=0},{X=1,Y=1},{R=1,G=1,B=1,A=1},0,0,{X=0,Y=0})
        K:EndDrawCanvasToRenderTarget(world,context)
        K:ExportRenderTarget(world,rt,dir,"ground.exr")
        local metadata={schema="mjolnir-flux-state-v2",height=relative.."/height.exr",velocity=relative.."/velocity.exr",
            ground=relative.."/ground.exr",centre=d.centre,res=d.res,cell=d.cell,height_cm=d.height,capture=state.CaptureOffset,
            origin=e.spec.origin or {0,0,0},provenance=e.spec.provenance}
        local file=assert(io.open(dir.."/state.json","w"),"Cannot write Flux state metadata")
        file:write(Flux.encode(metadata).."\n"); file:close(); count=count+1
    end end
    if count==0 then error("Unknown Flux domain: "..tostring(id)) end
    return "baked "..count.." domain(s); validate EXRs and change playback to baked before shipping"
end
return Flux
