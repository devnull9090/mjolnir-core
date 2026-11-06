-- The game's own play path: HaloAudioSound through its Blueprint library.
local pc = FindFirstOf("PlayerController")
local pawn = pc.Pawn
local lib = StaticFindObject("/Script/HaloAudioUnreal.Default__HaloAudioBlueprintFunctionLibrary")
local l = pawn:K2_GetActorLocation()
local ok, r = pcall(function()
    return lib:PlaySoundAtPosition(MJ.hsOnce, pawn, { X = l.X, Y = l.Y, Z = l.Z },
        { Pitch = 0, Yaw = 0, Roll = 0 }, 0.0, pawn, {})
end)
print("PlaySoundAtPosition", ok, r)
