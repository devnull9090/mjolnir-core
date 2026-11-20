-- Evaluate through mjolnir-game game_lua after PWR's dressing jobs finish.
-- Read attached mesh materials; preloading a missing asset would invalidate this check.
local root = "/Game/MJOLNIR/World/PWR/Surfaces/"
local expected = {
    M_CE_AlpineApron = {
        ApronField="T_PWR_ApronField", ApronGeology="T_LandBase", ApronEcology="T_LandEcology",
        GrassD="T_Ground_Grass_tb3nce_Desat_4K_NSVT_D", SoilD="T_Trampled_Forest_Path_ub4jdihkw_NSVT_D",
        RockD="T_Rock_Jagged_udemcebew_NSVT_D", SnowD="T_Windswept_Snow_NSVT_D"
    },
    M_CE_PWRPaving = {PanelNormal="T_PWR_PavingNormal", PanelData="T_PWR_PavingData", PanelGraphic="T_PWR_PavingGraphic"},
    M_CE_PWRRock = {RockD="T_Rock_Jagged_udemcebew_NSVT_D", RockN="T_Rock_Jagged_udemcebew_NSVT_N"}
}
local counts, faults = {}, 0
local function valid(object) return object and object:IsValid() end
local function name(object) return valid(object) and object:GetFullName() or "none" end
local function fault(reason) faults=faults+1; print("FAILED "..reason) end
for _, actor in ipairs(FindAllOf("StaticMeshActor") or {}) do
    if valid(actor) and name(actor:GetWorld())=="World /Game/Levels/Halo1/Solo/PWR/PWR.PWR" then
        local c=actor.StaticMeshComponent
        local mesh=valid(c) and c.StaticMesh
        local asset=valid(mesh) and mesh:GetFName():ToString() or ""
        local parent, required
        if asset=="SM_PWR_DistantApron" then parent,required="M_CE_AlpineApron",true
        elseif asset:find("SM_PWR_BasePaving_",1,true)==1 then parent,required="M_CE_PWRPaving",true
        elseif asset:match("^SM_Rock_") or asset=="SM_PNWGL_Rock_Macro_B" then parent="M_CE_PWRRock" end
        if parent then
            for slot=0,c:GetNumMaterials()-1 do
                local mat=c:GetMaterial(slot)
                local ok,master=pcall(function() return mat.Parent end)
                if ok and name(master)=="Material "..root..parent.."."..parent then
                    counts[parent]=(counts[parent] or 0)+1
                    if counts[parent]==1 then
                        print(asset.." slot "..slot.." => "..name(master))
                        for parameter, wanted in pairs(expected[parent]) do
                            local got=mat:K2_GetTextureParameterValue(FName(parameter))
                            print(parameter.."="..name(got))
                            if not valid(got) or got:GetFName():ToString()~=wanted then fault(parent.."."..parameter) end
                        end
                    end
                elseif required then fault(asset.." slot "..slot.." got "..name(mat)) end
            end
        end
    end
end
for parent in pairs(expected) do print(parent.." attached slots="..tostring(counts[parent] or 0)) end
assert(counts.M_CE_AlpineApron==1 and counts.M_CE_PWRPaving==6 and counts.M_CE_PWRRock and faults==0,
       "PWR material verification incomplete")
