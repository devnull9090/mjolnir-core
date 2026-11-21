-- Private diagnosis of the upper river's downstream (+Unreal Y) surface.
-- Run once in the loaded map. Every test is relative to captured live values.
assert(PWREdgeStudy == nil, "A previous edge study must be restored first")
local surface
for _, actor in ipairs(FindAllOf("BP_FluxSurface_River_C") or {}) do
    if actor:IsValid() and actor:GetFullName():find("PersistentLevel", 1, true) then
        assert(not surface, "Ambiguous upper river")
        surface = actor
    end
end
assert(surface, "No persistent river actor")
local mesh = surface.SurfaceOverMesh
assert(mesh and mesh:IsValid(), "Missing SurfaceOverMesh")
local param = FName("FluxStateBorders")
local materials = {}
for i = 1, #surface.MaterialInstances do
    local mid = surface.MaterialInstances[i]
    local old = mid:K2_GetVectorParameterValue(param)
    materials[i] = {mid=mid, old={R=old.R,G=old.G,B=old.B,A=old.A}}
end
assert(#materials > 0)
local initiallyVisible = mesh:IsVisible()
local study = {}
PWREdgeStudy = study
local function setBorder(row, alpha)
    local old = row.old
    row.mid:SetVectorParameterValue(param, {R=old.R, G=old.G, B=old.B, A=alpha})
    local actual = row.mid:K2_GetVectorParameterValue(param)
    assert(actual.R == old.R and actual.G == old.G and actual.B == old.B)
    assert(math.abs(actual.A - alpha) < math.max(.00000001, math.abs(alpha)*.000001))
end
function study.apply(mode)
    -- The compiled material expression decides whether distance is normalized
    -- to the tile or measured in cm. Keep both hypotheses separate.
    assert(mode == "control" or mode == "uv" or mode == "cm" or mode == "hide")
    for _, row in ipairs(materials) do
        local alpha = row.old.A
        if mode == "uv" then alpha = 250 end -- 1000 m / 4 m
        if mode == "cm" then alpha = 1 / 400 end
        setBorder(row, alpha)
    end
    local visible = initiallyVisible and mode ~= "hide"
    mesh:SetVisibility(visible, false)
    assert(mesh:IsVisible() == visible)
    print("PWR_EDGE_STUDY " .. mode .. " PASS")
end
function study.restore()
    study.apply("control")
    PWREdgeStudy = nil
    print("PWR_EDGE_RESTORED PASS")
end
print("PWR_EDGE_READY PASS")
