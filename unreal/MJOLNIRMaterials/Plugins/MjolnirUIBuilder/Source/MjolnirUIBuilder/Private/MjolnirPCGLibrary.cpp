#include "MjolnirPCGLibrary.h"

#include "AssetRegistry/AssetRegistryModule.h"
#include "Async/TaskGraphInterfaces.h"
#include "Components/BoxComponent.h"
#include "Data/PCGPointData.h"
#include "Dom/JsonObject.h"
#include "Elements/IO/PCGLoadAssetElement.h"
#include "Elements/PCGAttributeFilter.h"
#include "Elements/PCGAttributeNoise.h"
#include "Elements/PCGDensityFilter.h"
#include "Elements/PCGTransformPoints.h"
#include "Engine/World.h"
#include "GameFramework/Actor.h"
#include "HAL/PlatformProcess.h"
#include "Metadata/PCGMetadata.h"
#include "Metadata/PCGMetadataAttributeTpl.h"
#include "Misc/FileHelper.h"
#include "Misc/PackageName.h"
#include "PCGComponent.h"
#include "PCGContext.h"
#include "PCGDataAsset.h"
#include "PCGGraph.h"
#include "PCGNode.h"
#include "PCGPin.h"
#include "PCGSubsystem.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"
#include "Serialization/JsonWriter.h"
#include "UObject/Package.h"
#include "UObject/SavePackage.h"

DEFINE_LOG_CATEGORY_STATIC(LogMjolnirPCG, Log, All);

namespace
{
bool Fail(const FString& Why)
{
	UE_LOG(LogMjolnirPCG, Error, TEXT("MJOLNIR PCG: %s"), *Why);
	return false;
}

bool SaveAsset(UObject* Asset)
{
	Asset->MarkPackageDirty();
	FAssetRegistryModule::AssetCreated(Asset);
	FSavePackageArgs Args;
	Args.TopLevelFlags = RF_Public | RF_Standalone;
	Args.SaveFlags = SAVE_None;
	const FString Filename = FPackageName::LongPackageNameToFilename(Asset->GetOutermost()->GetName(), FPackageName::GetAssetPackageExtension());
	return UPackage::SavePackage(Asset->GetOutermost(), Asset, *Filename, Args);
}

bool VectorField(const TSharedPtr<FJsonObject>& Obj, const TCHAR* Key, FVector& Result)
{
	const TArray<TSharedPtr<FJsonValue>>* Values;
	if (!Obj->TryGetArrayField(Key, Values) || Values->Num() != 3) return false;
	Result = FVector((*Values)[0]->AsNumber(), (*Values)[1]->AsNumber(), (*Values)[2]->AsNumber());
	return !Result.ContainsNaN();
}

TArray<TSharedPtr<FJsonValue>> Numbers(std::initializer_list<double> Values)
{
	TArray<TSharedPtr<FJsonValue>> Result;
	for (double V : Values) Result.Add(MakeShared<FJsonValueNumber>(V));
	return Result;
}
}

bool UMjolnirPCGLibrary::GeneratePoints(UWorld* World, const FString& InputJson, const FString& GraphPackage,
	const FString& OutputJson, int32 Seed, float ScaleMin, float ScaleMax)
{
	if (!World || !GraphPackage.StartsWith(TEXT("/Game/MJOLNIR/PCGAuthoring/")) ||
		!FMath::IsFinite(ScaleMin) || !FMath::IsFinite(ScaleMax) || ScaleMin <= 0 || ScaleMax < ScaleMin)
		return Fail(TEXT("invalid world, authoring package, or scale interval"));
	FString InputText;
	TSharedPtr<FJsonObject> Input;
	if (!FFileHelper::LoadFileToString(InputText, *InputJson) ||
		!FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(InputText), Input))
		return Fail(TEXT("cannot read candidate JSON"));
	const TArray<TSharedPtr<FJsonValue>>* Candidates;
	if (!Input->TryGetArrayField(TEXT("points"), Candidates) || Candidates->Num() > 2000000)
		return Fail(TEXT("missing points or candidate budget exceeded"));
	bool bAlign = false;
	Input->TryGetBoolField(TEXT("align_to_normal"), bAlign);

	const FString DataPackageName = GraphPackage + TEXT("_Candidates");
	UPackage* DataPackage = CreatePackage(*DataPackageName);
	DataPackage->FullyLoad();
	UPCGDataAsset* DataAsset = NewObject<UPCGDataAsset>(DataPackage, *FPackageName::GetShortName(DataPackageName), RF_Public | RF_Standalone);
	UPCGPointData* PointData = NewObject<UPCGPointData>(DataAsset, TEXT("ProjectedCandidates"), RF_Public);
	auto* IdAttribute = PointData->Metadata->CreateAttribute<int64>(TEXT("CandidateId"), -1, false, false);
	auto* MaskAttribute = PointData->Metadata->CreateAttribute<double>(TEXT("BiomeMask"), 0.0, false, false);
	auto& Points = PointData->GetMutablePoints();
	Points.Reserve(Candidates->Num());
	TSet<int64> Seen;
	for (const auto& Value : *Candidates)
	{
		const auto Obj = Value->AsObject();
		FVector Position, Normal(0, 0, 1);
		double Id, Density;
		if (!Obj || !VectorField(Obj, TEXT("position"), Position) ||
			!Obj->TryGetNumberField(TEXT("id"), Id) || Id < 0 || Id > MAX_int32 || Id != FMath::FloorToDouble(Id) ||
			!Obj->TryGetNumberField(TEXT("density"), Density) || !FMath::IsFinite(Density) || Density < 0 || Density > 1 || Seen.Contains(int64(Id)))
			return Fail(TEXT("invalid/duplicate candidate id, position or density"));
		Seen.Add(int64(Id));
		if (Obj->HasField(TEXT("normal")) && !VectorField(Obj, TEXT("normal"), Normal)) return Fail(TEXT("invalid normal"));
		double Mask = 1.0;
		Obj->TryGetNumberField(TEXT("biome_mask"), Mask);
		if (!FMath::IsFinite(Mask) || Mask < 0 || Mask > 1) return Fail(TEXT("invalid biome mask"));
		bool Allowed = true;
		Obj->TryGetBoolField(TEXT("allowed"), Allowed);
		if (!Allowed) Mask = 0.0;
		const FVector Location(100 * Position.X, -100 * Position.Y, 100 * Position.Z);
		const FVector Up = FVector(Normal.X, -Normal.Y, Normal.Z).GetSafeNormal(UE_SMALL_NUMBER, FVector::UpVector);
		const FQuat Rotation = bAlign ? FQuat::FindBetweenNormals(FVector::UpVector, Up) : FQuat::Identity;
		FPCGPoint& Point = Points.Add_GetRef(FPCGPoint(FTransform(Rotation, Location), float(Density), int32(Id)));
		Point.MetadataEntry = PointData->Metadata->AddEntry();
		IdAttribute->SetValue(Point.MetadataEntry, int64(Id));
		MaskAttribute->SetValue(Point.MetadataEntry, Mask);
	}
	FPCGTaggedData& Tagged = DataAsset->Data.TaggedData.AddDefaulted_GetRef();
	Tagged.Data = PointData;
	Tagged.Pin = PCGPinConstants::DefaultOutputLabel;
	DataAsset->Name = TEXT("PWR projected candidates: source terrain is authoritative");
	if (!SaveAsset(DataAsset)) return Fail(TEXT("could not save source PCG data asset"));

	UPackage* Package = CreatePackage(*GraphPackage);
	Package->FullyLoad();
	UPCGGraph* Graph = NewObject<UPCGGraph>(Package, *FPackageName::GetShortName(GraphPackage), RF_Public | RF_Standalone);
	UPCGLoadDataAssetSettings* LoadSettings;
	UPCGNode* Load = Graph->AddNodeOfType(LoadSettings);
	LoadSettings->Asset = DataAsset;
	LoadSettings->bSynchronousLoad = true;
	LoadSettings->UpdateFromData();
	Load->UpdateAfterSettingsChangeDuringCreation();
	Load->SetNodePosition(-900, 0);

	UPCGAttributeFilteringSettings* MaskSettings;
	UPCGNode* Mask = Graph->AddNodeOfType(MaskSettings);
	MaskSettings->TargetAttribute.SetAttributeName(TEXT("BiomeMask"));
	MaskSettings->Operator = EPCGAttributeFilterOperator::GreaterOrEqual;
	MaskSettings->bUseConstantThreshold = true;
	MaskSettings->AttributeTypes.Type = EPCGMetadataTypes::Double;
	MaskSettings->AttributeTypes.DoubleValue = 0.5;
	Mask->NodeTitle = TEXT("Biome and exclusion mask");
	Mask->SetNodePosition(-650, 0);
	Graph->AddEdge(Load, PCGPinConstants::DefaultOutputLabel, Mask, PCGPinConstants::DefaultInputLabel);

	UPCGDensityFilterSettings* DensitySettings;
	UPCGNode* Density = Graph->AddNodeOfType(DensitySettings);
	DensitySettings->LowerBound = 0.000001f;
	DensitySettings->UpperBound = 1.f;
	Density->SetNodePosition(-400, 0);
	Graph->AddEdge(Mask, PCGPinConstants::DefaultInFilterLabel, Density, PCGPinConstants::DefaultInputLabel);

	UPCGAttributeNoiseSettings* NoiseSettings;
	UPCGNode* Noise = Graph->AddNodeOfType(NoiseSettings);
	NoiseSettings->InputSource.SetPointProperty(EPCGPointProperties::Density);
	NoiseSettings->OutputTarget.SetAttributeName(TEXT("DensityDraw"));
	NoiseSettings->Mode = EPCGAttributeNoiseMode::Set;
	NoiseSettings->Seed = 104729;
	Noise->NodeTitle = TEXT("Seeded density draw");
	Noise->SetNodePosition(-150, 0);
	Graph->AddEdge(Density, PCGPinConstants::DefaultOutputLabel, Noise, PCGPinConstants::DefaultInputLabel);

	UPCGAttributeFilteringSettings* KeepSettings;
	UPCGNode* Keep = Graph->AddNodeOfType(KeepSettings);
	KeepSettings->TargetAttribute.SetAttributeName(TEXT("DensityDraw"));
	KeepSettings->Operator = EPCGAttributeFilterOperator::LesserOrEqual;
	KeepSettings->ThresholdAttribute.SetPointProperty(EPCGPointProperties::Density);
	KeepSettings->bUseConstantThreshold = false;
	KeepSettings->bUseSpatialQuery = false;
	Keep->NodeTitle = TEXT("Draw below biome density");
	Keep->SetNodePosition(100, 0);
	Graph->AddEdge(Noise, PCGPinConstants::DefaultOutputLabel, Keep, PCGPinConstants::DefaultInputLabel);

	UPCGAttributeNoiseSettings* ChoiceSettings;
	UPCGNode* Choice = Graph->AddNodeOfType(ChoiceSettings);
	ChoiceSettings->InputSource.SetPointProperty(EPCGPointProperties::Density);
	ChoiceSettings->OutputTarget.SetAttributeName(TEXT("AssetDraw"));
	ChoiceSettings->Mode = EPCGAttributeNoiseMode::Set;
	ChoiceSettings->Seed = 130363;
	Choice->NodeTitle = TEXT("Seeded mesh variant");
	Choice->SetNodePosition(350, 0);
	Graph->AddEdge(Keep, PCGPinConstants::DefaultInFilterLabel, Choice, PCGPinConstants::DefaultInputLabel);

	UPCGTransformPointsSettings* TransformSettings;
	UPCGNode* Transform = Graph->AddNodeOfType(TransformSettings);
	TransformSettings->Seed = 155921;
	TransformSettings->RotationMin = FRotator(0, 0, 0);
	TransformSettings->RotationMax = FRotator(0, 360, 0);
	TransformSettings->ScaleMin = FVector(ScaleMin);
	TransformSettings->ScaleMax = FVector(ScaleMax);
	TransformSettings->bUniformScale = true;
	Transform->NodeTitle = TEXT("Yaw and scale; preserve collision projection");
	Transform->SetNodePosition(600, 0);
	Graph->AddEdge(Choice, PCGPinConstants::DefaultOutputLabel, Transform, PCGPinConstants::DefaultInputLabel);
	Graph->GetOutputNode()->SetNodePosition(900, 0);
	Graph->AddEdge(Transform, PCGPinConstants::DefaultOutputLabel, Graph->GetOutputNode(), PCGPinConstants::DefaultOutputLabel);
	if (!SaveAsset(Graph)) return Fail(TEXT("could not save PCG graph"));

	AActor* Owner = World->SpawnActor<AActor>();
	if (!Owner) return Fail(TEXT("could not spawn authoring owner"));
	Owner->SetActorLabel(TEXT("PWR PCG export (editor only)"));
	// PCG still validates its owner's bounds even when every graph point comes
	// from a data asset. A plain actor has none, so give this editor-only owner
	// an explicit non-colliding source domain before registering the component.
	const FBox Domain = PointData->GetBounds().ExpandBy(100.0);
	UBoxComponent* Bounds = NewObject<UBoxComponent>(Owner);
	Owner->SetRootComponent(Bounds);
	Bounds->SetBoxExtent(Domain.GetExtent());
	Bounds->SetCollisionEnabled(ECollisionEnabled::NoCollision);
	Owner->AddInstanceComponent(Bounds);
	Bounds->RegisterComponent();
	Owner->SetActorLocation(Domain.GetCenter());
	UPCGComponent* Component = NewObject<UPCGComponent>(Owner);
	Component->GenerationTrigger = EPCGComponentGenerationTrigger::GenerateOnDemand;
	Component->Seed = Seed;
	Owner->AddInstanceComponent(Component);
	Component->RegisterComponent();
	Component->SetGraph(Graph);
	UPCGSubsystem* Subsystem = World->GetSubsystem<UPCGSubsystem>();
	if (!Subsystem) { Owner->Destroy(); return Fail(TEXT("PCG subsystem unavailable")); }
	const FPCGTaskId Task = Component->GenerateLocalGetTaskId(true);
	if (Task == InvalidPCGTaskId) { Owner->Destroy(); return Fail(TEXT("PCG rejected graph scheduling")); }
	const double Deadline = FPlatformTime::Seconds() + 300.0;
	while (Component->IsGenerating() && FPlatformTime::Seconds() < Deadline)
	{
		Subsystem->Tick(1.0f / 60.0f);
		FTaskGraphInterface::Get().ProcessThreadUntilIdle(ENamedThreads::GameThread);
		FPlatformProcess::Sleep(0.001f);
	}
	if (Component->IsGenerating())
	{
		Subsystem->CancelGeneration(Component);
		Owner->Destroy();
		return Fail(TEXT("PCG graph timed out"));
	}
	const FPCGDataCollection& Generated = Component->GetGeneratedGraphOutput();
	TArray<TSharedPtr<FJsonValue>> Rows;
	TSet<int64> OutputIds;
	for (const FPCGTaggedData& Output : Generated.TaggedData)
	{
		const UPCGPointData* Result = Cast<UPCGPointData>(Output.Data);
		if (!Result) continue;
		const auto* Ids = Result->Metadata->GetConstTypedAttribute<int64>(TEXT("CandidateId"));
		const auto* Choices = Result->Metadata->GetConstTypedAttribute<double>(TEXT("AssetDraw"));
		const auto* FloatChoices = Result->Metadata->GetConstTypedAttribute<float>(TEXT("AssetDraw"));
		if (!Ids || (!Choices && !FloatChoices)) { Owner->Destroy(); return Fail(TEXT("generated metadata missing")); }
		for (const FPCGPoint& Point : Result->GetPoints())
		{
			const int64 Id = Ids->GetValueFromItemKey(Point.MetadataEntry);
			if (!Seen.Contains(Id) || OutputIds.Contains(Id)) { Owner->Destroy(); return Fail(TEXT("unknown or duplicate PCG output id")); }
			OutputIds.Add(Id);
			const FVector P = Point.Transform.GetLocation(), S = Point.Transform.GetScale3D();
			const FQuat Q = Point.Transform.GetRotation();
			auto Row = MakeShared<FJsonObject>();
			Row->SetNumberField(TEXT("id"), double(Id));
			Row->SetArrayField(TEXT("position_cm"), Numbers({P.X, P.Y, P.Z}));
			Row->SetArrayField(TEXT("rotation_xyzw"), Numbers({Q.X, Q.Y, Q.Z, Q.W}));
			Row->SetArrayField(TEXT("scale_xyz"), Numbers({S.X, S.Y, S.Z}));
			Row->SetNumberField(TEXT("asset_draw"), Choices ? Choices->GetValueFromItemKey(Point.MetadataEntry) : FloatChoices->GetValueFromItemKey(Point.MetadataEntry));
			Rows.Add(MakeShared<FJsonValueObject>(Row));
		}
	}
	auto Export = MakeShared<FJsonObject>();
	Export->SetNumberField(TEXT("schema"), 1);
	Export->SetStringField(TEXT("generator"), TEXT("UE5.5 UPCGGraph / PCGComponent GenerateLocal"));
	Export->SetStringField(TEXT("graph"), Graph->GetPathName());
	Export->SetNumberField(TEXT("seed"), Seed);
	Export->SetNumberField(TEXT("input_count"), Candidates->Num());
	Export->SetArrayField(TEXT("points"), Rows);
	FString Json;
	FJsonSerializer::Serialize(Export, TJsonWriterFactory<TCHAR, TCondensedJsonPrintPolicy<TCHAR>>::Create(&Json));
	const bool Saved = FFileHelper::SaveStringToFile(Json, *OutputJson, FFileHelper::EEncodingOptions::ForceUTF8WithoutBOM);
	UE_LOG(LogMjolnirPCG, Display, TEXT("MJOLNIR PCG: executed %s seed=%d candidates=%d selected=%d export=%s"),
		*Graph->GetPathName(), Seed, Candidates->Num(), Rows.Num(), *OutputJson);
	Owner->Destroy();
	return Saved;
}
