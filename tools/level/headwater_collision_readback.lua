-- Check the three different parts of the lake against the decoded cooked
-- heightfield. A decorated shoreline can have more than one blocking actor.
local world = mj.world()
local system = StaticFindObject("/Script/Engine.Default__KismetSystemLibrary")
local clear = {R=0, G=0, B=0, A=0}
local probes = {
    {name="lakebed", x=-352, y=893,     height=136.86675},
    {name="sill",    x=-299.8163, y=816.271, height=141.31366},
    {name="bank",    x=-430, y=896,     height=151.0405},
}
local function componentObject(ref)
    if not ref then return end
    for _, resolve in ipairs({
        function() return ref:Get() end,
        function() return ref:get() end,
        function() return ref end,
    }) do
        local ok, component = pcall(function()
            local value = resolve()
            if value and value:IsValid() then return value end
        end)
        if ok and component then return component end
    end
end

local function landscapeHit(p)
    local x, y = p.x * 100, -p.y * 100
    local start = {X=x, Y=y, Z=(p.height+25)*100}
    local finish = {X=x, Y=y, Z=(p.height-22)*100}
    local ignored = {}
    for _=1,12 do
        local hit = {}
        system:LineTraceSingle(world, start, finish, 0, true, ignored, 0, hit, true, clear, clear, 0)
        if not hit.bBlockingHit then break end
        local component = componentObject(hit.Component)
        if not component then break end
        local name = component:GetFullName()
        if name:find("LandscapeHeightfieldCollisionComponent", 1, true)
                or name:find("LandscapeMeshCollisionComponent", 1, true) then
            return hit.Location.Z * .01, name
        end
        local actor = component:GetOwner()
        if not actor or not actor:IsValid() then break end
        print("HEADWATER_TRACE_SKIPPED " .. p.name .. " " .. name)
        ignored[#ignored+1] = actor
    end
    -- Some bridge versions wrap the weak FHitResult.Component opaquely.
    -- Ask the current world's terrain physics components directly in that case.
    for _, component in ipairs(FindAllOf("LandscapeHeightfieldCollisionComponent") or {}) do
        if component:IsValid() then
            local name = component:GetFullName()
            if name:find("PersistentLevel", 1, true) then
                local origin, extent, radius = {}, {}, {}
                system:GetComponentBounds(component, origin, extent, radius)
                if math.abs(x - origin.X) <= extent.X+1 and math.abs(y - origin.Y) <= extent.Y+1 then
                    local location, normal, bone, hit = {}, {}, {}, {}
                    local blocked = component:K2_LineTraceComponent(start, finish, true, false, false,
                                                                     location, normal, bone, hit)
                    if blocked then return location.Z * .01, name end
                end
            end
        end
    end
end
for _, p in ipairs(probes) do
    local height, component = landscapeHit(p)
    assert(height, "No verified Landscape collision for " .. p.name)
    local difference = math.abs(height - p.height)
    print(string.format("HEADWATER_LANDSCAPE_TRACE %s x=%.4f y=%.4f actual_m=%.5f expected_m=%.5f error_m=%.5f component=%s",
                        p.name, p.x, p.y, height, p.height, difference, component))
    assert(difference <= .15, "Landscape mismatch at " .. p.name)
end
print("HEADWATER_LANDSCAPE_ACCEPTANCE PASS")
