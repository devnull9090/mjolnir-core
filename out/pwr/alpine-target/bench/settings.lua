local pc = mj.pc()
local w = pc:GetWorld()
assert(w:GetFName():ToString() == "PWR")
local k = StaticFindObject("/Script/Engine.Default__KismetSystemLibrary")
local cfg = StaticFindObject("/Script/Engine.Default__GameUserSettings"):GetGameUserSettings()
local size = StaticFindObject("/Script/UMG.Default__WidgetLayoutLibrary"):GetViewportSize(pc)
local function value(label, callback)
    local ok, v = pcall(callback)
    print("READ " .. label .. " " .. ((ok and v~=nil) and tostring(v) or "unavailable"))
end
value("viewport_w", function() return size.X end)
value("viewport_h", function() return size.Y end)
value("world", function() return w:GetFullName() end)
value("hud", function() return pc.MyHUD.bShowHUD end)
value("display_mode", function() return cfg:GetFullscreenMode() end)
value("saved_vsync", function() return cfg:IsVSyncEnabled() end)
value("saved_fps_limit", function() return cfg:GetFrameRateLimit() end)
value("dynamic_resolution_setting", function() return cfg:IsDynamicResolutionEnabled() end)
value("saved_frame_generation", function() return cfg.bFrameGeneration end)
for _, group in ipairs({"ViewDistance", "AntiAliasing", "Shadow", "GlobalIllumination", "Reflection", "PostProcess", "Texture", "Effects", "Foliage", "Shading"}) do
    local name = "sg." .. group .. "Quality"
    value(name, function() return k:GetConsoleVariableIntValue(name) end)
end
-- Shipping Kismet returns zero for unknown CVars. Optional vendor zeros are recorded
-- as raw CVar responses, never interpreted as confirmed vendor state or render size.
for _, name in ipairs({"r.ScreenPercentage", "sg.ResolutionQuality", "t.MaxFPS", "r.VSync",
    "t.IdleWhenNotForeground", "r.DynamicRes.OperationMode", "r.DynamicRes.MinScreenPercentage",
    "r.DynamicRes.MaxScreenPercentage", "r.AntiAliasingMethod", "r.TemporalAA.Upsampling",
    "r.NGX.DLSS.Enable", "r.Streamline.DLSSG.Enable", "r.FidelityFX.FSR3.Enabled",
    "r.FidelityFX.FI.Enabled", "r.ViewDistanceScale", "r.Nanite", "r.Shadow.Virtual.Enable",
    "foliage.DensityScale", "grass.DensityScale", "r.Streaming.PoolSize"}) do
    value(name, function() return k:GetConsoleVariableFloatValue(name) end)
end

