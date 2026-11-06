local lib = StaticFindObject("/Script/HaloAudioUnreal.Default__HaloAudioBlueprintFunctionLibrary")
print("stop", pcall(function() lib:StopTrackedSound(MJ_LOOP) end))
