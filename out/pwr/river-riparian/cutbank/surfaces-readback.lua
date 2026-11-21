-- Read only the two native surfaces attached to the cooked Pelican Warfare world.
local folder = "/Game/MJOLNIR/GrassPilot/Playable/"
local expected = {
    SM_PWR_CutbankRoots = { material="M_PWR_CutbankRoots", pos={-30000,-82000,14100} },
    SM_PWR_SpringCascade = { material="M_PWR_SpringCascade", pos={-39600,-97300,14600} },
}
local count = {}
local function valid(o) return o and o:IsValid() end
local function path(class,leaf) return class.." "..folder..leaf.."."..leaf end
for _,actor in ipairs(FindAllOf("StaticMeshActor") or {}) do
    if valid(actor) and actor:GetFullName():find("/PWR/PWR.PWR:PersistentLevel.",1,true) then
        local comp = actor.StaticMeshComponent
        local mesh = valid(comp) and comp.StaticMesh
        if valid(mesh) then
            local name = mesh:GetFName():ToString()
            local cfg = expected[name]
            if cfg and mesh:GetFullName()==path("StaticMesh",name) then
                count[name]=(count[name] or 0)+1
                local q = actor:K2_GetActorLocation()
                assert(math.abs(q.X-cfg.pos[1])<=1 and math.abs(q.Y-cfg.pos[2])<=1 and math.abs(q.Z-cfg.pos[3])<=1,
                       "Misregistered riparian surface "..name)
                local ok, visible = pcall(function() return comp:IsVisible() end)
                if ok then assert(visible,"Hidden riparian surface "..name) end
                local okcol, collision = pcall(function() return comp:GetCollisionEnabled() end)
                if okcol then
                    assert(tonumber(collision)==0 or tostring(collision):find("NoCollision",1,true),
                           "Unexpected collision for "..name..": "..tostring(collision))
                end
                local okmat, material = pcall(function() return comp:GetMaterial(0) end)
                if okmat then
                    assert(valid(material),"Missing material for "..name)
                    local materialPath = material:GetFullName()
                    if materialPath~=path("Material",cfg.material) then
                        local hasParent,parent = pcall(function() return material.Parent end)
                        assert(hasParent and valid(parent) and parent:GetFullName()==path("Material",cfg.material),
                               "Unexpected material for "..name..": "..materialPath)
                    end
                end
                print(string.format("PWR_RIPARIAN_SURFACE %s at %.1f %.1f %.1f; visible=%s collision=%s material=%s",
                                    mesh:GetFullName(),q.X,q.Y,q.Z,
                                    ok and tostring(visible) or "unreflected",
                                    okcol and tostring(collision) or "unreflected",
                                    okmat and material:GetFullName() or "unreflected"))
            end
        end
    end
end
for name in pairs(expected) do assert(count[name]==1,"Expected one "..name..", saw "..tostring(count[name] or 0)) end
print("PWR_RIPARIAN_SURFACES PASS 2")
