-- Run with game_lua in a loaded map. Loading an AkAudioEvent starts its bank
-- load; the post in 02 comes a few seconds later.
local k = StaticFindObject("/Script/Engine.Default__KismetSystemLibrary")
local function load(path)
    local ok, a = pcall(function()
        return k:LoadAsset_Blocking(k:Conv_SoftObjPathToSoftObjRef(k:MakeSoftObjectPath(path)))
    end)
    if ok and a and a:IsValid() then return a end
    print("NOT LOADED " .. path)
end
local R = "/Game/MJOLNIR/Audio/CEHorn/"
MJ = {
    once = load(R .. "Play_MJ_CE_Horn_Once.Play_MJ_CE_Horn_Once"),
    loop = load(R .. "Play_MJ_CE_Horn_Loop.Play_MJ_CE_Horn_Loop"),
    stop = load(R .. "Stop_MJ_CE_Horn_Loop.Stop_MJ_CE_Horn_Loop"),
    hsOnce = load(R .. "HS_MJ_CE_Horn_Once.HS_MJ_CE_Horn_Once"),
    hsLoop = load(R .. "HS_MJ_CE_Horn_Loop.HS_MJ_CE_Horn_Loop"),
    -- The control: a shipped event through the same call.
    stock = load("/Game/WwiseAudio/Events/Meteorite/Vehicle/Warthog/VEH_Warthog_Horn/Play_VEH_Warthog_Horn_Loop.Play_VEH_Warthog_Horn_Loop"),
}
for key, a in pairs(MJ) do
    print(key, a and a:GetFullName() or "nil")
end
