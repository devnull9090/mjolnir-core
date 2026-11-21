#pragma once

#include "CoreMinimal.h"
#include "Kismet/BlueprintFunctionLibrary.h"
#include "MjolnirPCGLibrary.generated.h"

/** Editor-only bridge. Its saved graph uses stock PCG nodes; its export has no UObject references. */
UCLASS()
class MJOLNIRUIBUILDER_API UMjolnirPCGLibrary : public UBlueprintFunctionLibrary
{
	GENERATED_BODY()
public:
	/** Import projected candidates, save/run a real UPCGGraph, export generated transforms.
	 * GraphPackage must live under /Game/MJOLNIR/PCGAuthoring (never cooked).
	 * No XY displacement: visual and Blam collision keep the same projected position.
	 */
	UFUNCTION(BlueprintCallable, Category = "MJOLNIR|PCG")
	static bool GeneratePoints(UWorld* World, const FString& InputJson, const FString& GraphPackage,
		const FString& OutputJson, int32 Seed, float ScaleMin = 0.85f, float ScaleMax = 1.15f);
};
