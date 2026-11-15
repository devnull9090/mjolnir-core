-- Read-only PWR acceptance probe. Execute through the existing game bridge
-- after a fresh launch; this file creates no actors, textures or callbacks.
local function active(a) return a and a:IsValid() and not a:IsActorBeingDestroyed() end
local function xyz(p) return string.format("%.6f %.6f %.6f",p.X,p.Y,p.Z) end
local function actors(class)
    local out={}
    for _,a in ipairs(FindAllOf(class) or {}) do
        if active(a) and a:GetFullName():find("PersistentLevel",1,true) then out[#out+1]=a end
    end
    return out
end
local domains=actors("BP_FluxSimulationDomain_C")
local sources=actors("BP_FluxModifierSourceActor_C")
local rivers=actors("BP_FluxSurface_River_C")
local coasts=actors("BP_FluxSurface_Coastline_C")
local waves=actors("BP_FluxOceanWave_C")
local beds=0
for _,a in ipairs(actors("StaticMeshActor")) do
    local c=a.StaticMeshComponent;local mesh=c and c.StaticMesh
    if mesh and mesh:IsValid() then
        local name=mesh:GetFullName():lower()
        if name:find("flux",1,true) and name:find("bed",1,true) then beds=beds+1;print("FLUX_BED "..a:GetFullName()) end
    end
end
print("WORLD "..mj.world():GetFullName())
print(string.format("FLUX_WAVE_COUNTS domains=%d sources=%d beds=%d river=%d coastline=%d waves=%d",
    #domains,#sources,beds,#rivers,#coasts,#waves))
assert(#domains==0 and #sources==0 and beds==0,"Solver, source or capture bed is still present")
assert(#rivers==1 and #coasts==1 and #waves==1,"Expected one River, one Coastline and one wave")
for _,surface in ipairs({rivers[1],coasts[1]}) do
    print("FLUX_SURFACE "..surface:GetFullName())
    print("SURFACE_LOCATION "..xyz(surface:K2_GetActorLocation()))
    print("SURFACE_MESH_MODE "..tostring(surface.SurfaceMeshMode))
    local state=surface.SimulationState
    assert(state and state:IsValid(),"Missing baked state")
    print("STATE_AREA "..xyz(state.AreaLocation).." size "..xyz(state.AreaSize))
    print("STATE_CAPTURE "..tostring(state.CaptureOffset))
    for _,key in ipairs({"HeightWetMap","VelocityDepthFoamMap","GroundMap"}) do
        local texture=state[key]
        assert(texture and texture:IsValid(),"Missing state texture: "..key)
        local name=texture:GetFullName()
        print("STATE_TEXTURE "..key.." "..name.." srgb="..tostring(texture.SRGB))
        assert(name:match("^Texture2D%s") and texture.SRGB==false,"State must use linear Texture2D, not a solver render target")
    end
end
local coast,wave=coasts[1],waves[1]
assert(coast.SurfaceMeshMode==5,"Coastline must retain finite mesh mode5")
assert(coast.OceanWaveActor and coast.OceanWaveActor:IsValid()
    and coast.OceanWaveActor:GetFullName()==wave:GetFullName(),"Wrong wave binding")
print("WAVE_LOCATION "..xyz(wave:K2_GetActorLocation()))
for _,key in ipairs({"UseRenderTarget","OceanWaveHeight","OceanWaveLength","OceanWaveChoppiness","OceanWaveOffset"}) do
    print("WAVE_PARAMETER "..key.." "..tostring(wave[key]))
end
local tick=wave:IsActorTickEnabled()
local renderTarget=wave.WaveTexture and wave.WaveTexture:IsValid() or false
print("WAVE_TICK "..tostring(tick));print("WAVE_RENDER_TARGET "..tostring(renderTarget))
assert(wave.UseRenderTarget==false and tick==false and not renderTarget,"Wave must use native texture animation without a ticking render target")
assert(wave.OceanWaveHeight==18 and wave.OceanWaveLength==1800 and wave.OceanWaveChoppiness==0 and wave.OceanWaveOffset==0,"Unexpected final wave settings")
local animation=wave.OceanWaveAnimation
assert(animation and animation:IsValid() and animation:GetFullName():match("^VolumeTexture%s"),"Missing installed wave volume texture")
print("WAVE_ANIMATION "..animation:GetFullName())
print("FLUX_WAVE_ACCEPTANCE PASS; visual shoreline/seam review and shader displacement measurement remain separate")
