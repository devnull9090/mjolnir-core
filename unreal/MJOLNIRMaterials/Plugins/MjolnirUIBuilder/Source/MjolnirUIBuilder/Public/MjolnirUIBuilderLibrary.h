// Widget Blueprints built from Python (Scripts/build_mjolnir_ui.py).
//
// Python can create a Widget Blueprint asset but not edit its widget tree or
// place graph nodes. These functions do both, for the small set of patterns
// MJOLNIR's widgets use. Everything they place is stock engine: the cooked
// widget references UMG and Kismet libraries only, never this module.
#pragma once

#include "CoreMinimal.h"
#include "Kismet/BlueprintFunctionLibrary.h"
#include "MjolnirUIBuilderLibrary.generated.h"

class UMaterial;
class UMaterialExpression;
class UWidget;
class UUserWidget;
class UWidgetBlueprint;

UCLASS()
class MJOLNIRUIBUILDER_API UMjolnirUIBuilderLibrary : public UBlueprintFunctionLibrary
{
	GENERATED_BODY()

public:
	/**
	 * A new Widget Blueprint at PackagePath/Name. ParentClass is UserWidget
	 * when unset; a screen for the game's menu stack uses
	 * CommonActivatableWidget.
	 */
	UFUNCTION(BlueprintCallable, Category = "MJOLNIR|UI")
	static UWidgetBlueprint* CreateWidgetBlueprint(const FString& PackagePath, const FString& Name, TSubclassOf<UUserWidget> ParentClass);

	/**
	 * Add a widget of WidgetClass named Name under the panel named Parent, or as
	 * the root when Parent is None. The widget is a variable, so Lua and graphs
	 * reach it by name. Returns it, for Python to set its properties and slot.
	 */
	UFUNCTION(BlueprintCallable, Category = "MJOLNIR|UI")
	static UWidget* AddWidget(UWidgetBlueprint* Blueprint, TSubclassOf<UWidget> WidgetClass, FName Name, FName Parent);

	/**
	 * A function taking one String, FName(StringParam): with no TextBlock it is
	 * empty (an event for Lua to hook); with one, it sets that block's text.
	 */
	UFUNCTION(BlueprintCallable, Category = "MJOLNIR|UI")
	static bool AddStringFunction(UWidgetBlueprint* Blueprint, FName FunctionName, FName StringParam, FName TextBlock);

	/** When the widget named Widget raises Delegate (e.g. a Button's OnClicked), call Function(Argument). */
	UFUNCTION(BlueprintCallable, Category = "MJOLNIR|UI")
	static bool BindEventToFunction(UWidgetBlueprint* Blueprint, FName Widget, FName Delegate, FName Function, const FString& Argument);

	/** Compile; false when it fails. The caller saves the asset. */
	UFUNCTION(BlueprintCallable, Category = "MJOLNIR|UI")
	static bool CompileWidget(UWidgetBlueprint* Blueprint);

	/**
	 * Connect From's output OutputName ("" for the first) to Material's World
	 * Position Offset. Python's MaterialProperty enum leaves that input out, so
	 * the CE device masters (Scripts/build_ce_materials.py) wire it here.
	 */
	UFUNCTION(BlueprintCallable, Category = "MJOLNIR|Materials")
	static bool ConnectWorldPositionOffset(UMaterial* Material, UMaterialExpression* From, const FString& OutputName);
};
