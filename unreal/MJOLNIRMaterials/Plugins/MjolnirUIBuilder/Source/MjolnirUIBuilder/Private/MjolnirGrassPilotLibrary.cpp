#include "MjolnirGrassPilotLibrary.h"

#include "AssetCompilingManager.h"
#include "AssetRegistry/AssetRegistryModule.h"
#include "Dom/JsonObject.h"
#include "Engine/StaticMesh.h"
#include "Engine/Texture2D.h"
#include "Engine/World.h"
#include "LandscapeComponent.h"
#include "LandscapeGrassType.h"
#include "LandscapeProxy.h"
#include "MaterialEditingLibrary.h"
#include "Materials/Material.h"
#include "Materials/MaterialInstance.h"
#include "Materials/MaterialInstanceDynamic.h"
#include "Materials/MaterialExpressionLandscapeGrassOutput.h"
#include "Materials/MaterialExpressionLandscapeLayerCoords.h"
#include "Materials/MaterialExpressionTextureSample.h"
#include "Misc/App.h"
#include "Misc/Base64.h"
#include "Misc/PackageName.h"
#include "Serialization/JsonSerializer.h"
#include "Serialization/JsonWriter.h"

namespace
{
    bool IsPilotAsset(const UObject* Object)
    {
        return Object && Object->GetOutermost()->GetName().StartsWith(TEXT("/Game/MJOLNIR/GrassPilot/"));
    }

    template<class T> T* Node(UMaterial* Material, int32 X)
    {
        return CastChecked<T>(UMaterialEditingLibrary::CreateMaterialExpression(Material, T::StaticClass(), X, -2400));
    }

    FString Json(const TSharedRef<FJsonObject>& Object)
    {
        FString Result;
        FJsonSerializer::Serialize(Object, TJsonWriterFactory<>::Create(&Result));
        return Result;
    }
}

ULandscapeGrassType* UMjolnirGrassPilotLibrary::CreateGrassType(const FString& PackagePath,
    const TArray<UStaticMesh*>& Meshes, const TArray<float>& Densities,
    const TArray<FVector2D>& ScaleRanges, int32 StartCullCm, int32 EndCullCm)
{
    if (!PackagePath.StartsWith(TEXT("/Game/MJOLNIR/GrassPilot/")) || !FPackageName::IsValidLongPackageName(PackagePath)
        || Meshes.Num() != 3 || Densities.Num() != Meshes.Num() || ScaleRanges.Num() != Meshes.Num()
        || StartCullCm < 0 || EndCullCm <= StartCullCm || EndCullCm > 8000)
        return nullptr;
    for (int32 I = 0; I < Meshes.Num(); ++I)
    {
        if (!Meshes[I] || !FMath::IsFinite(Densities[I]) || Densities[I] <= 0 || Densities[I] > 200
            || !FMath::IsFinite(ScaleRanges[I].X) || !FMath::IsFinite(ScaleRanges[I].Y)
            || ScaleRanges[I].X <= 0 || ScaleRanges[I].Y < ScaleRanges[I].X || ScaleRanges[I].Y > 1)
            return nullptr;
    }
    UPackage* Package = CreatePackage(*PackagePath);
    const FName Name(*FPackageName::GetLongPackageAssetName(PackagePath));
    if (FindObject<UObject>(Package, *Name.ToString())) return nullptr;
    ULandscapeGrassType* Type = NewObject<ULandscapeGrassType>(Package, Name, RF_Public | RF_Standalone);
    Type->bEnableDensityScaling = true;
    for (int32 I = 0; I < Meshes.Num(); ++I)
    {
        FGrassVariety Variety;
        Variety.GrassMesh = Meshes[I];
        Variety.OverrideMaterials.Empty();
        Variety.GrassDensity.Default = Densities[I];
        Variety.GrassDensityQuality.Default = Densities[I];
        Variety.StartCullDistance.Default = StartCullCm;
        Variety.StartCullDistanceQuality.Default = StartCullCm;
        Variety.EndCullDistance.Default = EndCullCm;
        Variety.EndCullDistanceQuality.Default = EndCullCm;
        Variety.MinLOD = -1;
        Variety.bUseGrid = true;
        Variety.PlacementJitter = 1.0f;
        Variety.Scaling = EGrassScaling::Uniform;
        Variety.ScaleX = Variety.ScaleY = Variety.ScaleZ = FFloatInterval(ScaleRanges[I].X, ScaleRanges[I].Y);
        Variety.RandomRotation = true;
        Variety.AlignToSurface = true;
        Variety.bWeightAttenuatesMaxScale = false;
        Variety.bUseLandscapeLightmap = false;
        Variety.bCastDynamicShadow = false;
        Variety.bCastContactShadow = false;
        Variety.bAffectDistanceFieldLighting = false;
        Variety.bKeepInstanceBufferCPUCopy = false;
        Variety.InstanceWorldPositionOffsetDisableDistance = 0;
        Type->GrassVarieties.Add(Variety);
    }
    Type->PostEditChange();
    FAssetRegistryModule::AssetCreated(Type);
    Type->MarkPackageDirty();
    return Type;
}

bool UMjolnirGrassPilotLibrary::AttachGrassOutput(UMaterial* Material, UTexture2D* Density,
    ULandscapeGrassType* GrassType, FVector2D OriginCm, FVector2D QuadCm, int32 GridSize)
{
    FAssetCompilingManager::Get().FinishAllCompilation();
    if (!IsPilotAsset(Material) || !IsPilotAsset(Density) || !IsPilotAsset(GrassType)
        || GridSize < 2 || Density->GetSizeX() != GridSize || Density->GetSizeY() != GridSize
        || !FMath::IsFinite(OriginCm.X) || !FMath::IsFinite(OriginCm.Y)
        || !FMath::IsFinite(QuadCm.X) || !FMath::IsFinite(QuadCm.Y) || QuadCm.X <= 0 || QuadCm.Y <= 0)
        return false;
    for (UMaterialExpression* Expression : Material->GetExpressions())
        if (Cast<UMaterialExpressionLandscapeGrassOutput>(Expression)) return false;

    // PNG rows are Unreal +Y. Native layer coordinates are local vertex XY +
    // SectionBase, including in the grass point-render pass. Reconstructed
    // pixel world position drifts there and bleeds across categorical edges.
    // Sample the corresponding global-grid texel centre directly instead.
    auto* UV = Node<UMaterialExpressionLandscapeLayerCoords>(Material, -1000);
    UV->MappingType = TCMT_XY;
    UV->MappingScale = GridSize;
    UV->MappingPanU = UV->MappingPanV = 0.5f / GridSize;
    auto* Sample = Node<UMaterialExpressionTextureSample>(Material, -800);
    Sample->Texture = Density;
    Sample->SamplerType = SAMPLERTYPE_LinearColor;
    Sample->Coordinates.Connect(0, UV);
    auto* Output = Node<UMaterialExpressionLandscapeGrassOutput>(Material, -400);
    Output->GrassTypes.Empty();
    FGrassInput Input(FName(TEXT("PWRPilotGrass")));
    Input.GrassType = GrassType;
    Input.Input.Connect(1, Sample); // TextureSample's R output.
    Output->GrassTypes.Add(Input);
    UMaterialEditingLibrary::RecompileMaterial(Material);
    Material->MarkPackageDirty();
    return true;
}

FString UMjolnirGrassPilotLibrary::ReadGrassData(ALandscapeProxy* Landscape, ULandscapeGrassType* GrassType, bool bBuild)
{
    TSharedRef<FJsonObject> Root = MakeShared<FJsonObject>();
    Root->SetStringField(TEXT("schema"), TEXT("mjolnir-native-grass-readback-v1"));
    const FString Map = Landscape && Landscape->GetWorld() ? Landscape->GetWorld()->GetOutermost()->GetName() : FString();
    if (!IsPilotAsset(GrassType) ||
        (Map != TEXT("/Game/Levels/Halo1/Solo/LPG/LPG") && Map != TEXT("/Game/Levels/Halo1/Solo/LPE/LPE")))
    {
        Root->SetStringField(TEXT("error"), TEXT("Expected an authored PWR grass world and grass asset"));
        return Json(Root);
    }
    Root->SetStringField(TEXT("world"), Landscape->GetWorld()->GetOutermost()->GetName());
    Root->SetStringField(TEXT("grass_type"), GrassType->GetPathName());
    Root->SetBoolField(TEXT("built"), bBuild);
    if (bBuild)
    {
        if (!FApp::CanEverRender() || Landscape->GetWorld()->IsGameWorld())
        {
            Root->SetStringField(TEXT("error"), TEXT("GPU-capable editor world required; use -AllowCommandletRendering"));
            return Json(Root);
        }
        FAssetCompilingManager::Get().FinishAllCompilation();
        for (ULandscapeComponent* Component : Landscape->LandscapeComponents)
        {
            Component->UpdateMaterialInstances();
            // LPW uses dynamic landscape materials. Updating MICs alone leaves
            // existing MIDs pointing at the old MICs; the native grass baker
            // then sees a null material resource. Native re-registration
            // clears/recreates the MIDs from the new component MICs.
            Component->ReregisterComponent();
        }
        Landscape->GetWorld()->SendAllEndOfFrameUpdates();
        FAssetCompilingManager::Get().FinishAllCompilation();
        Landscape->BuildGrassMaps(); // Native blocking GPU bake, with shader/streaming/readback progress.
    }
    TArray<TSharedPtr<FJsonValue>> Components;
    for (ULandscapeComponent* Component : Landscape->LandscapeComponents)
    {
        TSharedRef<FJsonObject> Row = MakeShared<FJsonObject>();
        FIntPoint Base = Component->GetSectionBase();
        Row->SetNumberField(TEXT("x"), Base.X);
        Row->SetNumberField(TEXT("y"), Base.Y);
        Row->SetNumberField(TEXT("quads"), Component->ComponentSizeQuads);
        Row->SetStringField(TEXT("material"), GetPathNameSafe(Component->GetLandscapeMaterial()));
        Row->SetBoolField(TEXT("dynamic_materials"), Landscape->bUseDynamicMaterialInstance);
        Row->SetNumberField(TEXT("dynamic_material_count"), Component->MaterialInstancesDynamic.Num());
        Row->SetNumberField(TEXT("static_material_count"), Component->MaterialInstances.Num());
        if (Component->MaterialInstancesDynamic.Num() > 0)
        {
            UMaterialInstance* Instance = Component->MaterialInstancesDynamic[0];
            Row->SetStringField(TEXT("dynamic_material"), GetPathNameSafe(Instance));
            Row->SetStringField(TEXT("dynamic_material_parent"), Instance ? GetPathNameSafe(Instance->Parent) : TEXT("None"));
        }
        TArray<TSharedPtr<FJsonValue>> Types;
        for (ULandscapeGrassType* Type : Component->GetGrassTypes())
            Types.Add(MakeShared<FJsonValueString>(GetPathNameSafe(Type)));
        Row->SetArrayField(TEXT("grass_types"), Types);
        const FLandscapeComponentGrassData& Data = Component->GrassData.Get();
        Row->SetNumberField(TEXT("num_elements"), Data.NumElements);
        Row->SetNumberField(TEXT("weight_channels"), Data.WeightOffsets.Num());
        const int64 HeightBytes = int64(Data.NumElements) * sizeof(uint16);
        if (Data.NumElements > 0 && HeightBytes <= Data.HeightWeightData.Num())
            Row->SetStringField(TEXT("heights_b64"), FBase64::Encode(Data.HeightWeightData.GetData(), static_cast<uint32>(HeightBytes)));
        const int32* Offset = Data.WeightOffsets.Find(GrassType);
        if (Offset && Data.NumElements > 0 && *Offset >= Data.NumElements * int32(sizeof(uint16))
            && int64(*Offset) + Data.NumElements <= Data.HeightWeightData.Num())
        {
            Row->SetStringField(TEXT("weights_b64"), FBase64::Encode(Data.HeightWeightData.GetData() + *Offset, Data.NumElements));
        }
        // InitializeFrom(..., bStripEmptyWeights=true) keeps the height grid when
        // every channel is zero. This is valid saved data, not an unbuilt map.
        else if (Offset || (Data.NumElements > 0 &&
            (Data.WeightOffsets.Num() != 0 || Data.HeightWeightData.Num() != HeightBytes)))
            Row->SetStringField(TEXT("error"), TEXT("Missing or invalid grass weight buffer"));
        Components.Add(MakeShared<FJsonValueObject>(Row));
    }
    Root->SetArrayField(TEXT("components"), Components);
    return Json(Root);
}
