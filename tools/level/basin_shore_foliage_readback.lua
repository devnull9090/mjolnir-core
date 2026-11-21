-- Read the three .39 native-grass owners from the live PWR level.
-- C++ distance properties are centimetres and UE4SS exposes their reflected CamelCase names.
local specs = {
    {name="fine_a", owner="PWR_FineMeadow", source="PWRBlade_MJFol_1_1_0", base=22719, priorStart=2100, priorEnd=4400, total=1456, lower=18800, upper=31800},
    {name="fine_b", owner="PWR_FineMeadow", source="PWRBlade_MJFol_2_1_0", base=22606, priorStart=2100, priorEnd=4400, total=1227, lower=19600, upper=32700},
    {name="sedge", owner="MJOLNIR_Foliage", source="MJFol_2_1_0", base=123089, priorStart=4000, priorEnd=6000, total=963, lower=20400, upper=33500}
}
local found, countNew = {}, 0
local reserve = "PWR_BasinShoreGrass"
for _,component in ipairs(FindAllOf("HierarchicalInstancedStaticMeshComponent") or {}) do
    if component and component:IsValid() and component:GetFullName():find("/PWR/PWR.PWR:PersistentLevel.",1,true) then
        local actor=component:GetOwner()
        if actor and actor:IsValid() then
            local owner=actor:GetFName():ToString()
            local name=component:GetFName():ToString()
            if owner==reserve or owner=="PWR_FineMeadow" or owner=="MJOLNIR_Foliage" or owner=="PWR_FieldUnderstory" then
                local key=owner.."."..name
                assert(not found[key],"Duplicate native owner "..key)
                found[key]=component
                if owner==reserve then
                    assert(name:match("^PWRShore_%d+_%d+$"),"Unprotected component "..key)
                    countNew=countNew+1
                end
            end
        end
    end
end
local function check(key,count,near,far)
    local c=assert(found[key],"Missing native shore component "..key)
    local n=c:GetInstanceCount()
    local a,b=tonumber(c.InstanceStartCullDistance),tonumber(c.InstanceEndCullDistance)
    assert(a and b,"Missing native InstanceStartCullDistance/InstanceEndCullDistance on "..key)
    print(string.format("PWR_SHORE_FOLIAGE_COMPONENT %s count=%d start_cm=%d end_cm=%d visible=%s",key,n,a,b,tostring(c:IsVisible())))
    assert(n==count and a==near and b==far,"Unexpected shoreline count or distances on "..key)
    return n
end
assert(countNew==24,"Expected 24 native shoreline groups; found "..countNew)
local total=0
for g,spec in ipairs(specs) do
    check(spec.owner.."."..spec.source,spec.base,spec.priorStart,spec.priorEnd)
    for b=1,8 do
        local far=math.floor(spec.lower+(spec.upper-spec.lower)*b/8)
        local count=math.floor((spec.total+8-b)/8)
        local key=reserve..".PWRShore_"..g.."_"..b
        assert(found[key] and found[key]:IsVisible(),"Hidden local shore component "..key)
        total=total+check(key,count,far-6400,far)
    end
end
check("PWR_FieldUnderstory.MJFol_13_1_0",1070,25000,65000)
check("PWR_FieldUnderstory.MJFol_17_1_0",1032,44000,97000)
assert(total==3646,"Shore cohort population changed")
print("PWR_SHORE_FOLIAGE PASS")
