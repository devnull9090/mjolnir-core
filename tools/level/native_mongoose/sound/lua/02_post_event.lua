-- Raw AkAudioEvent post at the player. 0 = Wwise refused (event not in a loaded bank).
local pc = FindFirstOf("PlayerController")
local pawn = pc.Pawn
local ak = StaticFindObject("/Script/AkAudio.Default__AkGameplayStatics")
local l = pawn:K2_GetActorLocation()
local at = { X = l.X, Y = l.Y, Z = l.Z }
local rot = { Pitch = 0, Yaw = 0, Roll = 0 }
print("stock  id", ak:PostEventAtLocation(MJ.stock, at, rot, pawn))
-- Wait for the stock horn to finish before judging the next line by ear,
-- or run them apart: comment one out.
print("ours   id", ak:PostEventAtLocation(MJ.once, at, rot, pawn))
