#include "MjolnirUIBuilderLibrary.h"

#include "AssetRegistry/AssetRegistryModule.h"
#include "Blueprint/UserWidget.h"
#include "Blueprint/WidgetBlueprintGeneratedClass.h"
#include "Blueprint/WidgetTree.h"
#include "Components/PanelWidget.h"
#include "Components/TextBlock.h"
#include "EdGraph/EdGraph.h"
#include "EdGraphSchema_K2.h"
#include "K2Node_CallFunction.h"
#include "K2Node_ComponentBoundEvent.h"
#include "K2Node_FunctionEntry.h"
#include "K2Node_VariableGet.h"
#include "Kismet/KismetTextLibrary.h"
#include "Kismet2/BlueprintEditorUtils.h"
#include "Kismet2/KismetEditorUtilities.h"
#include "MaterialEditingLibrary.h"
#include "Materials/Material.h"
#include "Modules/ModuleManager.h"
#include "WidgetBlueprint.h"
#include "Landscape.h"
#include "LandscapeInfo.h"
#include "LandscapeImportHelper.h"
#include "Misc/FileHelper.h"
#include "UObject/EnumProperty.h"
#include "UObject/FieldPathProperty.h"
#include "UObject/PropertyOptional.h"
#include "UObject/TextProperty.h"
#include "UObject/UObjectIterator.h"

IMPLEMENT_MODULE(FDefaultModuleImpl, MjolnirUIBuilder)

DEFINE_LOG_CATEGORY_STATIC(LogMjolnirUI, Log, All);

namespace
{
	bool Connect(UEdGraphPin* A, UEdGraphPin* B, const TCHAR* What)
	{
		if (!A || !B || !GetDefault<UEdGraphSchema_K2>()->TryCreateConnection(A, B))
		{
			UE_LOG(LogMjolnirUI, Error, TEXT("MJOLNIR UI: could not connect %s"), What);
			return false;
		}
		return true;
	}

	template <typename NodeT>
	NodeT* Place(UEdGraph& Graph, int32 X, int32 Y, TFunctionRef<void(NodeT*)> Setup)
	{
		FGraphNodeCreator<NodeT> Creator(Graph);
		NodeT* Node = Creator.CreateNode();
		Setup(Node);
		Node->NodePosX = X;
		Node->NodePosY = Y;
		Creator.Finalize();
		return Node;
	}

	UK2Node_CallFunction* PlaceCall(UEdGraph& Graph, int32 X, int32 Y, UClass* Class, FName Function)
	{
		UFunction* Fn = Class->FindFunctionByName(Function);
		if (!Fn)
		{
			UE_LOG(LogMjolnirUI, Error, TEXT("MJOLNIR UI: no function %s on %s"), *Function.ToString(), *Class->GetName());
			return nullptr;
		}
		return Place<UK2Node_CallFunction>(Graph, X, Y, [Fn](UK2Node_CallFunction* N) { N->SetFromFunction(Fn); });
	}

	void Compile(UWidgetBlueprint* Blueprint)
	{
		FKismetEditorUtilities::CompileBlueprint(Blueprint, EBlueprintCompileOptions::SkipGarbageCollection);
	}
}

UWidgetBlueprint* UMjolnirUIBuilderLibrary::CreateWidgetBlueprint(const FString& PackagePath, const FString& Name, TSubclassOf<UUserWidget> ParentClass)
{
	UPackage* Package = CreatePackage(*(PackagePath / Name));
	UClass* Parent = ParentClass ? ParentClass.Get() : UUserWidget::StaticClass();
	UBlueprint* Blueprint = FKismetEditorUtilities::CreateBlueprint(
		Parent, Package, FName(*Name), BPTYPE_Normal,
		UWidgetBlueprint::StaticClass(), UWidgetBlueprintGeneratedClass::StaticClass(), NAME_None);
	UWidgetBlueprint* Widget = Cast<UWidgetBlueprint>(Blueprint);
	if (!Widget)
	{
		UE_LOG(LogMjolnirUI, Error, TEXT("MJOLNIR UI: could not create %s/%s"), *PackagePath, *Name);
		return nullptr;
	}
	FAssetRegistryModule::AssetCreated(Widget);
	Package->MarkPackageDirty();
	return Widget;
}

UWidget* UMjolnirUIBuilderLibrary::AddWidget(UWidgetBlueprint* Blueprint, TSubclassOf<UWidget> WidgetClass, FName Name, FName Parent)
{
	if (!Blueprint || !WidgetClass)
	{
		return nullptr;
	}
	UWidgetTree* Tree = Blueprint->WidgetTree;
	UWidget* Widget = Tree->ConstructWidget<UWidget>(WidgetClass, Name);
	Widget->bIsVariable = true;
	if (Parent.IsNone())
	{
		Tree->RootWidget = Widget;
	}
	else
	{
		UPanelWidget* Panel = Cast<UPanelWidget>(Tree->FindWidget(Parent));
		if (!Panel)
		{
			UE_LOG(LogMjolnirUI, Error, TEXT("MJOLNIR UI: %s is not a panel"), *Parent.ToString());
			return nullptr;
		}
		Panel->AddChild(Widget);
	}
	FBlueprintEditorUtils::MarkBlueprintAsStructurallyModified(Blueprint);
	return Widget;
}

bool UMjolnirUIBuilderLibrary::AddStringFunction(UWidgetBlueprint* Blueprint, FName FunctionName, FName StringParam, FName TextBlock)
{
	if (!Blueprint)
	{
		return false;
	}
	UEdGraph* Graph = FBlueprintEditorUtils::CreateNewGraph(Blueprint, FunctionName, UEdGraph::StaticClass(), UEdGraphSchema_K2::StaticClass());
	FBlueprintEditorUtils::AddFunctionGraph<UClass>(Blueprint, Graph, /*bIsUserCreated=*/true, nullptr);
	UK2Node_FunctionEntry* Entry = nullptr;
	for (UEdGraphNode* Node : Graph->Nodes)
	{
		if ((Entry = Cast<UK2Node_FunctionEntry>(Node)) != nullptr)
		{
			break;
		}
	}
	if (!Entry)
	{
		UE_LOG(LogMjolnirUI, Error, TEXT("MJOLNIR UI: %s has no entry node"), *FunctionName.ToString());
		return false;
	}
	FEdGraphPinType StringType;
	StringType.PinCategory = UEdGraphSchema_K2::PC_String;
	Entry->CreateUserDefinedPin(StringParam, StringType, EGPD_Output, /*bUseUniqueName=*/false);
	FBlueprintEditorUtils::MarkBlueprintAsStructurallyModified(Blueprint);
	if (TextBlock.IsNone())
	{
		return true;
	}

	// The text block's variable must exist on the skeleton class first.
	Compile(Blueprint);
	UK2Node_VariableGet* Get = Place<UK2Node_VariableGet>(*Graph, 200, 200,
		[TextBlock](UK2Node_VariableGet* N) { N->VariableReference.SetSelfMember(TextBlock); });
	UK2Node_CallFunction* ToText = PlaceCall(*Graph, 200, 100, UKismetTextLibrary::StaticClass(),
		GET_FUNCTION_NAME_CHECKED(UKismetTextLibrary, Conv_StringToText));
	UK2Node_CallFunction* SetText = PlaceCall(*Graph, 500, 0, UTextBlock::StaticClass(),
		GET_FUNCTION_NAME_CHECKED(UTextBlock, SetText));
	if (!ToText || !SetText)
	{
		return false;
	}
	bool Ok = Connect(Entry->FindPin(UEdGraphSchema_K2::PN_Then), SetText->GetExecPin(), TEXT("entry -> SetText"));
	Ok &= Connect(Entry->FindPin(StringParam), ToText->FindPin(TEXT("InString")), TEXT("param -> Conv_StringToText"));
	Ok &= Connect(ToText->GetReturnValuePin(), SetText->FindPin(TEXT("InText")), TEXT("Conv_StringToText -> InText"));
	Ok &= Connect(Get->FindPin(TextBlock), SetText->FindPin(UEdGraphSchema_K2::PN_Self), TEXT("text block -> self"));
	FBlueprintEditorUtils::MarkBlueprintAsModified(Blueprint);
	return Ok;
}

bool UMjolnirUIBuilderLibrary::BindEventToFunction(UWidgetBlueprint* Blueprint, FName Widget, FName Delegate, FName Function, const FString& Argument)
{
	if (!Blueprint)
	{
		return false;
	}
	// The widget's variable and the function must exist on the skeleton class.
	Compile(Blueprint);
	FObjectProperty* WidgetProperty = FindFProperty<FObjectProperty>(Blueprint->SkeletonGeneratedClass, Widget);
	FMulticastDelegateProperty* DelegateProperty = WidgetProperty
		? FindFProperty<FMulticastDelegateProperty>(WidgetProperty->PropertyClass, Delegate)
		: nullptr;
	UEdGraph* EventGraph = FBlueprintEditorUtils::FindEventGraph(Blueprint);
	if (!DelegateProperty || !EventGraph)
	{
		UE_LOG(LogMjolnirUI, Error, TEXT("MJOLNIR UI: no %s.%s to bind (or no event graph)"), *Widget.ToString(), *Delegate.ToString());
		return false;
	}
	const int32 Y = EventGraph->Nodes.Num() * 150;
	UK2Node_ComponentBoundEvent* Event = Place<UK2Node_ComponentBoundEvent>(*EventGraph, 0, Y,
		[WidgetProperty, DelegateProperty](UK2Node_ComponentBoundEvent* N) { N->InitializeComponentBoundEventParams(WidgetProperty, DelegateProperty); });
	UK2Node_CallFunction* Call = Place<UK2Node_CallFunction>(*EventGraph, 400, Y,
		[Function](UK2Node_CallFunction* N) { N->FunctionReference.SetSelfMember(Function); });
	UEdGraphPin* ArgumentPin = nullptr;
	for (UEdGraphPin* Pin : Call->Pins)
	{
		if (Pin->Direction == EGPD_Input && Pin->PinType.PinCategory == UEdGraphSchema_K2::PC_String)
		{
			ArgumentPin = Pin;
			break;
		}
	}
	if (!ArgumentPin)
	{
		UE_LOG(LogMjolnirUI, Error, TEXT("MJOLNIR UI: %s takes no String"), *Function.ToString());
		return false;
	}
	GetDefault<UEdGraphSchema_K2>()->TrySetDefaultValue(*ArgumentPin, Argument);
	const bool Ok = Connect(Event->FindPin(UEdGraphSchema_K2::PN_Then), Call->GetExecPin(), TEXT("event -> call"));
	FBlueprintEditorUtils::MarkBlueprintAsModified(Blueprint);
	return Ok;
}

bool UMjolnirUIBuilderLibrary::CompileWidget(UWidgetBlueprint* Blueprint)
{
	if (!Blueprint)
	{
		return false;
	}
	Compile(Blueprint);
	if (Blueprint->Status == BS_Error)
	{
		UE_LOG(LogMjolnirUI, Error, TEXT("MJOLNIR UI: %s failed to compile"), *Blueprint->GetName());
		return false;
	}
	Blueprint->MarkPackageDirty();
	return true;
}

bool UMjolnirUIBuilderLibrary::ConnectWorldPositionOffset(UMaterial* Material, UMaterialExpression* From, const FString& OutputName)
{
	if (!Material || !From || !UMaterialEditingLibrary::ConnectMaterialProperty(From, OutputName, MP_WorldPositionOffset))
	{
		UE_LOG(LogMjolnirUI, Error, TEXT("MJOLNIR: could not connect World Position Offset on %s"), Material ? *Material->GetName() : TEXT("(none)"));
		return false;
	}
	Material->MarkPackageDirty();
	return true;
}

bool UMjolnirUIBuilderLibrary::ConnectDisplacement(UMaterial* Material, UMaterialExpression* From, const FString& OutputName)
{
	if (!Material || !From || !UMaterialEditingLibrary::ConnectMaterialProperty(From, OutputName, MP_Displacement))
	{
		UE_LOG(LogMjolnirUI, Error, TEXT("MJOLNIR: could not connect Displacement on %s"), Material ? *Material->GetName() : TEXT("(none)"));
		return false;
	}
	Material->MarkPackageDirty();
	return true;
}

bool UMjolnirUIBuilderLibrary::ConnectPixelDepthOffset(UMaterial* Material, UMaterialExpression* From, const FString& OutputName)
{
	if (!Material || !From || !UMaterialEditingLibrary::ConnectMaterialProperty(From, OutputName, MP_PixelDepthOffset))
	{
		UE_LOG(LogMjolnirUI, Error, TEXT("MJOLNIR: could not connect Pixel Depth Offset on %s"), Material ? *Material->GetName() : TEXT("(none)"));
		return false;
	}
	Material->MarkPackageDirty();
	return true;
}

ALandscape* UMjolnirUIBuilderLibrary::CreateLandscape(UWorld* World, FVector Location, FVector Scale, int32 ComponentsX,
	int32 ComponentsY, int32 SectionsPerComponent, int32 QuadsPerSection, const TArray<int32>& Heights,
	UMaterialInterface* Material, const TArray<uint8>& Holes)
{
	if (!World || ComponentsX < 1 || ComponentsY < 1 || SectionsPerComponent < 1 || QuadsPerSection < 1)
	{
		UE_LOG(LogMjolnirUI, Error, TEXT("CreateLandscape: bad arguments"));
		return nullptr;
	}
	const int32 QuadsPerComponent = SectionsPerComponent * QuadsPerSection;
	const int32 SizeX = ComponentsX * QuadsPerComponent + 1;
	const int32 SizeY = ComponentsY * QuadsPerComponent + 1;
	if (Heights.Num() != SizeX * SizeY)
	{
		UE_LOG(LogMjolnirUI, Error, TEXT("CreateLandscape: %d heights for %d x %d samples"), Heights.Num(), SizeX, SizeY);
		return nullptr;
	}
	TArray<uint16> Data;
	Data.SetNumUninitialized(Heights.Num());
	for (int32 i = 0; i < Heights.Num(); ++i)
	{
		Data[i] = static_cast<uint16>(FMath::Clamp(Heights[i], 0, 65535));
	}
	TMap<FGuid, TArray<uint16>> HeightDataPerLayers;
	HeightDataPerLayers.Add(FGuid(), MoveTemp(Data));
	TMap<FGuid, TArray<FLandscapeImportLayerInfo>> MaterialLayerDataPerLayers;
	TArray<FLandscapeImportLayerInfo>& Layers = MaterialLayerDataPerLayers.Add(FGuid(), TArray<FLandscapeImportLayerInfo>());
	if (Holes.Num() > 0)
	{
		if (Holes.Num() != SizeX * SizeY || !ALandscapeProxy::VisibilityLayer)
		{
			UE_LOG(LogMjolnirUI, Error, TEXT("CreateLandscape: %d hole samples for %d x %d"), Holes.Num(), SizeX, SizeY);
			return nullptr;
		}
		FLandscapeImportLayerInfo Visibility(ALandscapeProxy::VisibilityLayer->LayerName);
		Visibility.LayerInfo = ALandscapeProxy::VisibilityLayer;
		Visibility.LayerData = Holes;
		Layers.Add(MoveTemp(Visibility));
	}

	ALandscape* Landscape = World->SpawnActor<ALandscape>(Location, FRotator::ZeroRotator);
	if (!Landscape)
	{
		UE_LOG(LogMjolnirUI, Error, TEXT("CreateLandscape: spawn failed"));
		return nullptr;
	}
	Landscape->bCanHaveLayersContent = false;
	Landscape->LandscapeMaterial = Material;
	Landscape->LandscapeHoleMaterial = Material;
	// Per-component MIDs, so the loader can set the material's parameters at
	// runtime (SetLandscapeMaterial*ParameterValue does nothing without them).
	Landscape->bUseDynamicMaterialInstance = true;
	Landscape->SetActorRelativeScale3D(Scale);
	Landscape->Import(FGuid::NewGuid(), 0, 0, SizeX - 1, SizeY - 1, SectionsPerComponent, QuadsPerSection,
		HeightDataPerLayers, TEXT(""), MaterialLayerDataPerLayers, ELandscapeImportAlphamapType::Additive,
		TArrayView<const FLandscapeLayer>());
	if (ULandscapeInfo* Info = Landscape->GetLandscapeInfo())
	{
		Info->UpdateLayerInfoMap(Landscape);
	}
	Landscape->MarkPackageDirty();
	UE_LOG(LogMjolnirUI, Display, TEXT("CreateLandscape: %d x %d samples, %d component(s), %s"), SizeX, SizeY,
		Landscape->LandscapeComponents.Num(), Holes.Num() ? TEXT("with holes") : TEXT("no holes"));
	return Landscape;
}

namespace MjolnirUsmap
{
	struct FWriter
	{
		TArray<uint8> Out;
		TMap<FString, uint32> NameIndex;
		TArray<FString> Names;

		uint32 Name(const FString& S)
		{
			if (const uint32* Found = NameIndex.Find(S))
			{
				return *Found;
			}
			const uint32 Index = Names.Add(S);
			NameIndex.Add(S, Index);
			return Index;
		}
		void U8(uint8 V) { Out.Add(V); }
		void U16(uint16 V) { Out.Append(reinterpret_cast<uint8*>(&V), 2); }
		void U32(uint32 V) { Out.Append(reinterpret_cast<uint8*>(&V), 4); }

		// The usmap type tags (ue-asset's usmap.rs read_type).
		void Type(const FProperty* P)
		{
			if (const FEnumProperty* E = CastField<FEnumProperty>(P))
			{
				U8(26);
				Type(E->GetUnderlyingProperty());
				U32(Name(E->GetEnum() ? E->GetEnum()->GetName() : FString()));
			}
			else if (const FByteProperty* B = CastField<FByteProperty>(P))
			{
				if (B->Enum)
				{
					U8(26);
					U8(0);
					U32(Name(B->Enum->GetName()));
				}
				else
				{
					U8(0);
				}
			}
			else if (CastField<FBoolProperty>(P)) { U8(1); }
			else if (CastField<FIntProperty>(P)) { U8(2); }
			else if (CastField<FFloatProperty>(P)) { U8(3); }
			else if (CastField<FDoubleProperty>(P)) { U8(7); }
			else if (CastField<FSoftObjectProperty>(P)) { U8(17); }
			else if (CastField<FWeakObjectProperty>(P)) { U8(14); }
			else if (CastField<FLazyObjectProperty>(P)) { U8(15); }
			else if (CastField<FObjectPropertyBase>(P)) { U8(4); }
			else if (CastField<FInterfaceProperty>(P)) { U8(12); }
			else if (CastField<FNameProperty>(P)) { U8(5); }
			else if (CastField<FMulticastDelegateProperty>(P)) { U8(13); }
			else if (CastField<FDelegateProperty>(P)) { U8(6); }
			else if (const FArrayProperty* A = CastField<FArrayProperty>(P))
			{
				U8(8);
				Type(A->Inner);
			}
			else if (const FStructProperty* S = CastField<FStructProperty>(P))
			{
				U8(9);
				U32(Name(S->Struct ? S->Struct->GetName() : FString()));
			}
			else if (CastField<FStrProperty>(P)) { U8(10); }
			else if (CastField<FTextProperty>(P)) { U8(11); }
			else if (CastField<FUInt64Property>(P)) { U8(18); }
			else if (CastField<FUInt32Property>(P)) { U8(19); }
			else if (CastField<FUInt16Property>(P)) { U8(20); }
			else if (CastField<FInt64Property>(P)) { U8(21); }
			else if (CastField<FInt16Property>(P)) { U8(22); }
			else if (CastField<FInt8Property>(P)) { U8(23); }
			else if (const FMapProperty* M = CastField<FMapProperty>(P))
			{
				U8(24);
				Type(M->KeyProp);
				Type(M->ValueProp);
			}
			else if (const FSetProperty* T = CastField<FSetProperty>(P))
			{
				U8(25);
				Type(T->ElementProp);
			}
			else if (CastField<FFieldPathProperty>(P)) { U8(27); }
			else if (const FOptionalProperty* O = CastField<FOptionalProperty>(P))
			{
				U8(28);
				Type(O->GetValueProperty());
			}
			else
			{
				U8(0xFF);
			}
		}
	};
}

bool UMjolnirUIBuilderLibrary::WriteUsmap(const FString& Path)
{
	using namespace MjolnirUsmap;
	FWriter Body;

	TArray<UEnum*> Enums;
	TSet<FString> SeenEnums;
	for (TObjectIterator<UEnum> It; It; ++It)
	{
		if (!SeenEnums.Contains(It->GetName()))
		{
			SeenEnums.Add(It->GetName());
			Enums.Add(*It);
		}
	}
	Body.U32(Enums.Num());
	for (UEnum* E : Enums)
	{
		Body.U32(Body.Name(E->GetName()));
		const int32 Count = FMath::Min(E->NumEnums(), 65535);
		Body.U16(static_cast<uint16>(Count));
		for (int32 I = 0; I < Count; ++I)
		{
			Body.U32(Body.Name(E->GetNameStringByIndex(I)));
		}
	}

	// A struct's own properties in PropertyLink order, as
	// FUnversionedStructSchema numbers them in a cook (editor-only left out).
	TArray<UStruct*> Structs;
	TSet<FString> SeenStructs;
	for (TObjectIterator<UStruct> It; It; ++It)
	{
		UStruct* S = *It;
		if (S->IsA<UFunction>() || S->GetName().StartsWith(TEXT("REINST_")) || S->GetName().StartsWith(TEXT("SKEL_"))
			|| SeenStructs.Contains(S->GetName()))
		{
			continue;
		}
		SeenStructs.Add(S->GetName());
		Structs.Add(S);
	}
	Body.U32(Structs.Num());
	for (UStruct* S : Structs)
	{
		TArray<FProperty*> Own;
		for (FProperty* P = S->PropertyLink; P; P = P->PropertyLinkNext)
		{
			if (P->GetOwnerStruct() != S)
			{
				break;
			}
			if (!P->IsEditorOnlyProperty())
			{
				Own.Add(P);
			}
		}
		Body.U32(Body.Name(S->GetName()));
		UStruct* Super = S->GetSuperStruct();
		Body.U32(Super ? Body.Name(Super->GetName()) : 0xFFFFFFFFu);
		uint16 Slots = 0;
		for (FProperty* P : Own)
		{
			Slots += static_cast<uint16>(P->ArrayDim);
		}
		Body.U16(Slots);
		Body.U16(static_cast<uint16>(Own.Num()));
		uint16 Slot = 0;
		for (FProperty* P : Own)
		{
			Body.U16(Slot);
			Body.U8(static_cast<uint8>(P->ArrayDim));
			Body.U32(Body.Name(P->GetName()));
			Body.Type(P);
			Slot += static_cast<uint16>(P->ArrayDim);
		}
	}

	FWriter Names;
	Names.U32(Body.Names.Num());
	for (const FString& N : Body.Names)
	{
		FTCHARToUTF8 Utf8(*N);
		Names.U16(static_cast<uint16>(Utf8.Length()));
		Names.Out.Append(reinterpret_cast<const uint8*>(Utf8.Get()), Utf8.Length());
	}
	TArray<uint8> Payload = MoveTemp(Names.Out);
	Payload.Append(Body.Out);

	FWriter File;
	File.U16(0x30C4);
	File.U8(3);
	File.U32(0);
	File.U8(0);
	File.U32(Payload.Num());
	File.U32(Payload.Num());
	File.Out.Append(Payload);
	UE_LOG(LogMjolnirUI, Display, TEXT("WriteUsmap: %d enum(s), %d struct(s), %d name(s) -> %s"), Enums.Num(),
		Structs.Num(), Body.Names.Num(), *Path);
	return FFileHelper::SaveArrayToFile(File.Out, *Path);
}
