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
class UStaticMesh;
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

	/**
	 * Connect From's output OutputName ("" for the first) to Material's Pixel
	 * Depth Offset, which Python's MaterialProperty enum leaves out too: the
	 * B30 ground masters' parallax sand, drawn at the depth it shows.
	 */
	UFUNCTION(BlueprintCallable, Category = "MJOLNIR|Materials")
	static bool ConnectPixelDepthOffset(UMaterial* Material, UMaterialExpression* From, const FString& OutputName);

	/**
	 * Connect From's output OutputName ("" for the first) to Material's
	 * Displacement (Nanite tessellation's height, 0..1 about the material's
	 * DisplacementScaling centre), which Python's MaterialProperty lacks too.
	 */
	UFUNCTION(BlueprintCallable, Category = "MJOLNIR|Materials")
	static bool ConnectDisplacement(UMaterial* Material, UMaterialExpression* From, const FString& OutputName);

	/**
	 * Spawn a Landscape in World from a heightmap, as the editor's New
	 * Landscape tool does: ComponentsX x ComponentsY components of
	 * SectionsPerComponent^2 sections of QuadsPerSection quads, Heights the
	 * (ComponentsX * quads + 1) x (ComponentsY * quads + 1) samples, row by row
	 * (0..65535, 32768 the actor's z), Location its corner and Scale its
	 * spacing (cm a quad; z 100 spans -256..256 m). No edit layers, no paint
	 * layers. Holes, when given (one byte a sample, 255 a hole), become the
	 * visibility layer: the material cuts them with a Landscape Visibility
	 * Mask (build_ce_materials.py M_CE_Landscape).
	 */
	UFUNCTION(BlueprintCallable, Category = "MJOLNIR|Landscape")
	static class ALandscape* CreateLandscape(UWorld* World, FVector Location, FVector Scale, int32 ComponentsX,
		int32 ComponentsY, int32 SectionsPerComponent, int32 QuadsPerSection, const TArray<int32>& Heights,
		UMaterialInterface* Material, const TArray<uint8>& Holes);

	/**
	 * Build Mesh's one LOD from arrays, as an importer would: Positions in cm
	 * and Normals one a position (every triangle at a position shares its
	 * normal, so a welded surface displaces without cracks), Indices three a
	 * triangle into them, UV0 and UV1 one a corner (Indices' order),
	 * Sections the material slot of each triangle and SlotNames the slots.
	 * Colors, when given, one a position: the vertex colour (a material's
	 * per-vertex weight). ShadeNormals, when given, one a corner: a second
	 * normal for the material, in UV2 (x, y) and UV3 (z) (the vertex normal
	 * stays the welded one, which Nanite displaces along).
	 * Normals are kept, tangents built, no lightmap UVs generated (UV1 is
	 * the caller's). The caller sets Nanite and saves.
	 */
	UFUNCTION(BlueprintCallable, Category = "MJOLNIR|Mesh")
	static bool BuildStaticMesh(UStaticMesh* Mesh, const TArray<FVector>& Positions, const TArray<FVector>& Normals,
		const TArray<int32>& Indices, const TArray<FVector2D>& UV0, const TArray<FVector2D>& UV1,
		const TArray<int32>& Sections, const TArray<FName>& SlotNames, const TArray<FLinearColor>& Colors,
		const TArray<FVector>& ShadeNormals);

	/**
	 * Write every loaded class and struct's unversioned property schema, and
	 * every enum, to Path as a .usmap (version 3, uncompressed): the stock
	 * engine's layout, as the cook writes it (editor-only properties left
	 * out). Against the game's own .usmap it lets a stock-cooked package's
	 * properties be re-encoded in 343's layout (ue-asset's retarget).
	 */
	UFUNCTION(BlueprintCallable, Category = "MJOLNIR|Cook")
	static bool WriteUsmap(const FString& Path);

	/**
	 * Give Collection the game's own GUIDs: its StateId and each parameter's
	 * Id, in order, each as the 32 hex digits of the GUID's bytes as cooked
	 * (four little-endian words, as `mjolnir ue get` prints them). A cooked
	 * material finds a collection's values at runtime by the collection's
	 * StateId, so a stand-in for a game collection (the deformation
	 * globals, Scripts/build_ce_materials.py) must carry the game's. Call
	 * it after the last edit to the collection: an edit makes a new StateId.
	 */
	UFUNCTION(BlueprintCallable, Category = "MJOLNIR|Materials")
	static bool SetCollectionIds(class UMaterialParameterCollection* Collection, const FString& StateId,
		const TArray<FString>& ScalarIds, const TArray<FString>& VectorIds);
};
