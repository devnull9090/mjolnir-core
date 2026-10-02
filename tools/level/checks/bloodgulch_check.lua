-- One-launch self-check for the Bloodgulch test builds. Paste into the game
-- bridge's Lua after the map is up (NEW GAME, never RESUME). Prints PASS/FAIL
-- lines only; no screenshots needed.
--
-- 1. Waits until the experience manager reports Blam gameplay started, so a
--    pawn frozen in the loading handshake is not mistaken for one standing.
-- 2. Samples the pawn's height for six seconds. Standing on the transplanted
--    terrain means a steady height near EXPECT_Z; falling means FAIL.
-- 3. Asks the asset registry to scan the mesh folder (a mod container is not
--    in the shipped registry), then tries LoadAsset. No blocking soft-path
--    load: that call crashed the game once with a mis-shaped struct. The
--    scan + LoadAsset pair was followed by a game-thread hang once
--    (2026-09-03 22:46, after a level reload), so run this part last.

local TERRAIN_MESH = "/Game/Levels/Halo1/Solo/B40/Halo/Bloodgulch/bsp_0.bsp_0"
local MESH_DIR = "/Game/Levels/Halo1/Solo/B40/Halo/Bloodgulch"
-- Blank map spawn (33.5, 33.5): Blood Gulch canyon floor after the +44 offset.
local EXPECT_Z, TOL = 44.1, 1.5

local function wait(seconds)
  local t = os.clock(); while os.clock() - t < seconds do end
end

local em = FindFirstOf("BlamExperienceManagerComponent")
local started = false
for _ = 1, 20 do
  local ok, waiting = pcall(function() return em.bWaitingForBlamGameplayStart end)
  if ok and waiting == false then started = true break end
  wait(0.5)
end
print("[BG CHECK] blam gameplay started:", tostring(started))

local pawn = FindFirstOf("BP_MeteoritePawn_C")
if not pawn or not pawn:IsValid() then
  print("[BG CHECK] no pawn")
  return
end
local function z() return pawn:K2_GetActorLocation().Z / 304.8 end
local samples = { z() }
for _ = 1, 6 do wait(1.0); samples[#samples + 1] = z() end
local z0, z1 = samples[1], samples[#samples]
local l = pawn:K2_GetActorLocation()
local verdict
if math.abs(z1 - EXPECT_Z) < TOL and math.abs(z1 - z0) < 0.05 then
  verdict = "PASS: steady on Halo terrain"
elseif z1 < 30 or (z1 - z0) < -2 then
  verdict = "FAIL: fell"
else
  verdict = string.format("inconclusive (expected ~%.1f)", EXPECT_Z)
end
local trace = {}
for _, s in ipairs(samples) do trace[#trace + 1] = string.format("%.2f", s) end
print(string.format("[BG CHECK] pawn xy (%.2f, %.2f) z trace %s  %s",
  l.X / 304.8, -l.Y / 304.8, table.concat(trace, " "), verdict))

-- Mesh asset loading.
local before = StaticFindObject(TERRAIN_MESH)
print("[BG CHECK] mesh in memory before:", tostring(before ~= nil and before:IsValid()))
local okScan, scanErr = pcall(function()
  local helpers = StaticFindObject("/Script/AssetRegistry.Default__AssetRegistryHelpers")
  local reg = helpers:GetAssetRegistry()
  reg:ScanPathsSynchronous({ MESH_DIR }, true, false)
end)
print("[BG CHECK] registry scan:", okScan and "ok" or ("error " .. tostring(scanErr)))
local okLoad, asset = pcall(function() return LoadAsset(TERRAIN_MESH) end)
print("[BG CHECK] LoadAsset after scan:", okLoad and tostring(asset and asset:IsValid()) or ("error " .. tostring(asset)))
local after = StaticFindObject(TERRAIN_MESH)
print("[BG CHECK] mesh in memory after:", tostring(after ~= nil and after:IsValid()))
