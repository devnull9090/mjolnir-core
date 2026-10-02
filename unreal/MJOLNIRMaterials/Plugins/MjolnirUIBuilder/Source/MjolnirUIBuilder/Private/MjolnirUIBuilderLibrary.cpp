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
#include "Modules/ModuleManager.h"
#include "WidgetBlueprint.h"

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
