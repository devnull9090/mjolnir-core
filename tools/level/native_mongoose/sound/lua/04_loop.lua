-- The looping sound through the game's path; 05 stops it by the id this keeps.
local pc = FindFirstOf("PlayerController")
local pawn = pc.Pawn
local lib = StaticFindObject("/Script/HaloAudioUnreal.Default__HaloAudioBlueprintFunctionLibrary")
local l = pawn:K2_GetActorLocation()
local ok, r = pcall(function()
    return lib:PlaySoundAtPosition(MJ.hsLoop, pawn, { X = l.X, Y = l.Y, Z = l.Z },
        { Pitch = 0, Yaw = 0, Roll = 0 }, 0.0, pawn, {})
end)
MJ_LOOP = r
print("loop", ok, r)
