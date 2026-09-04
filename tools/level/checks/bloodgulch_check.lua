-- One-launch self-check for the Bloodgulch test builds. Paste into the game
-- bridge's Lua after the map is up (NEW GAME, never RESUME). Prints PASS/FAIL
-- lines only; no screenshots needed.
--
-- 1. Is the pawn standing on the transplanted terrain? The blank map's tower
--    floors are cleared in the test containers, so the only floor under the
--    spawn is Bloodgulch's canyon at ~44.1 wu (CE z 0.12 + 44.0).
-- 2. Does a stock-cooked mesh asset load by path? Tries the runtime loader's
--    route (LoadAsset) and the Blueprint library's blocking load.

local TERRAIN_MESH = "/Game/Levels/Halo1/Solo/B40/Halo/Bloodgulch/bsp_0.bsp_0"
local EXPECT_Z, TOL = 44.1, 1.2

local pawn = FindFirstOf("BP_MeteoritePawn_C")
if not pawn or not pawn:IsValid() then
  print("[BG CHECK] no pawn yet")
  return
end
local function z() return pawn:K2_GetActorLocation().Z / 304.8 end
local z0 = z()
local t = os.clock(); while os.clock() - t < 3.0 do end
local z1 = z()
local verdict
if math.abs(z1 - EXPECT_Z) < TOL and math.abs(z1 - z0) < 0.05 then
  verdict = "PASS: standing on Halo terrain"
elseif z1 < 30 or (z1 - z0) < -2 then
  verdict = "FAIL: falling / fell through"
else
  verdict = string.format("inconclusive (expected ~%.1f)", EXPECT_Z)
end
print(string.format("[BG CHECK] landing: z %.2f -> %.2f  %s", z0, z1, verdict))

-- Mesh asset loading.
local found = StaticFindObject(TERRAIN_MESH)
print("[BG CHECK] mesh already in memory:", tostring(found and found:IsValid()))
local ok1, a1 = pcall(function() return LoadAsset(TERRAIN_MESH) end)
print("[BG CHECK] LoadAsset:", ok1 and tostring(a1 and a1:IsValid()) or ("error " .. tostring(a1)))
local ok2, a2 = pcall(function()
  local ke = StaticFindObject("/Script/Engine.Default__KismetSystemLibrary")
  return ke:LoadAsset_Blocking({ AssetPathName = FName(TERRAIN_MESH), SubPathString = "" })
end)
print("[BG CHECK] LoadAsset_Blocking:", ok2 and tostring(a2 and a2:IsValid()) or ("error " .. tostring(a2)))
local after = StaticFindObject(TERRAIN_MESH)
print("[BG CHECK] mesh in memory afterwards:", tostring(after and after:IsValid()))
