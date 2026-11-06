-- Paste with game_lua while driving. One call: handles go stale.
local a = FindFirstOf("BP_NMGMongoose_C")
if not a or not a:IsValid() then print("no Mongoose") return end
local j = a.BlamVehicleHumanJeep
local f = j:GetEngineAngularVelocityFraction()
local r = j:GetEngineRPM()
local v = a:GetVelocity()
local s = math.sqrt(v.X * v.X + v.Y * v.Y + v.Z * v.Z)
local p = 1 + math.max(0, math.min(1, f))
print(string.format("fraction %.3f rpm %.3f speed %.0f cm/s -> CE pitch %.3f, engine on %s", f, r, s, p, tostring(a.EngineOn)))
