#pragma once

#include "CoreMinimal.h"
#include "Kismet/BlueprintFunctionLibrary.h"
#include "MjolnirGrassPilotLibrary.generated.h"

class ALandscapeProxy;
class ULandscapeGrassType;
class UMaterial;
class UStaticMesh;
class UTexture2D;

/** Editor-only preparation. Cooked outputs reference stock Landscape classes only. */
UCLASS()
class MJOLNIRUIBUILDER_API UMjolnirGrassPilotLibrary : public UBlueprintFunctionLibrary
{
    GENERATED_BODY()
public:
    /** New native asset; densities are per 100 square metres in UE 5.5's implementation. */
    UFUNCTION(BlueprintCallable, Category="MJOLNIR|GrassPilot")
    static ULandscapeGrassType* CreateGrassType(const FString& PackagePath,
        const TArray<UStaticMesh*>& Meshes, const TArray<float>& Densities,
        const TArray<FVector2D>& ScaleRanges, int32 StartCullCm, int32 EndCullCm);

    /** Add one fixed, world-coordinate grass output to an isolated material clone. */
    UFUNCTION(BlueprintCallable, Category="MJOLNIR|GrassPilot")
    static bool AttachGrassOutput(UMaterial* Material, UTexture2D* Density,
        ULandscapeGrassType* GrassType, FVector2D OriginCm, FVector2D QuadCm, int32 GridSize);

    /** Build synchronously if requested, then read native serialized buffers without rebuilding.
     * Returns JSON including every component's weight bytes for independent CPU validation. */
    UFUNCTION(BlueprintCallable, Category="MJOLNIR|GrassPilot")
    static FString ReadGrassData(ALandscapeProxy* Landscape, ULandscapeGrassType* GrassType, bool bBuild);
};
