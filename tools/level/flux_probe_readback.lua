-- Explicit read-only bridge probe of the active Flux surface/domain/bed.
local function xyz(p) return string.format("%.6f %.6f %.6f",p.X,p.Y,p.Z) end
local function active(a) return a and a:IsValid() and not a:IsActorBeingDestroyed() end
print("WORLD "..mj.world():GetFullName())
local domains,surfaces,beds,sources=0,0,0,0
for _,class in ipairs({"BP_FluxSimulationDomain_C","BP_FluxSurface_River_C"}) do
    for _,actor in ipairs(FindAllOf(class) or {}) do
        if active(actor) and actor:GetFullName():find("PersistentLevel",1,true) then
            print("FLUX_ACTOR "..actor:GetFullName())
            print("LOCATION "..xyz(actor:K2_GetActorLocation()))
            if class=="BP_FluxSimulationDomain_C" then
                domains=domains+1
                print(string.format("DOMAIN %d %d %.3f %.3f",actor.AreaResolution.X,actor.AreaResolution.Y,actor.AreaWorldPixelSize,actor.AreaWorldHeight))
                print("UPDATE_SIMULATION "..tostring(actor.UpdateSimulation))
            else
                surfaces=surfaces+1
                local state=actor.SimulationState
                if state and state:IsValid() then
                    print("STATE_AREA "..xyz(state.AreaLocation).." size "..xyz(state.AreaSize))
                    print("STATE_CAPTURE "..tostring(state.CaptureOffset))
                    print("STATE_HEIGHT "..state.HeightWetMap:GetFullName())
                    print("STATE_VELOCITY "..state.VelocityDepthFoamMap:GetFullName())
                    print("STATE_GROUND "..state.GroundMap:GetFullName())
                end
            end
        end
    end
end
for _,actor in ipairs(FindAllOf("StaticMeshActor") or {}) do
    if active(actor) then
        local component=actor.StaticMeshComponent
        local mesh=component and component.StaticMesh
        if mesh and mesh:IsValid() and mesh:GetFullName():find("SM_PWR_FluxProofBed",1,true) then
            beds=beds+1
            print("BED_LOCATION "..xyz(actor:K2_GetActorLocation()))
            print("BED_SCALE "..xyz(actor:GetActorScale3D()))
            print("BED_COLLISION "..tostring(component:GetCollisionEnabled()))
        end
    end
end
for _,actor in ipairs(FindAllOf("BP_FluxModifierSourceActor_C") or {}) do
    if active(actor) and actor:GetFullName():find("PersistentLevel",1,true) then sources=sources+1 end
end
print(string.format("FLUX_COUNTS domains=%d surfaces=%d beds=%d sources=%d",domains,surfaces,beds,sources))
assert(surfaces>0,"No active Flux surface; this is not a playback acceptance")
