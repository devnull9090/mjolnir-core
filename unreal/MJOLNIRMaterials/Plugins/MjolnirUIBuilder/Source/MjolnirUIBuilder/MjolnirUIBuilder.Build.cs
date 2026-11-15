using UnrealBuildTool;

public class MjolnirUIBuilder : ModuleRules
{
	public MjolnirUIBuilder(ReadOnlyTargetRules Target) : base(Target)
	{
		PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;
		PublicDependencyModuleNames.AddRange(new string[] { "Core", "CoreUObject", "Engine", "UMG" });
		PrivateDependencyModuleNames.AddRange(new string[] { "UMGEditor", "UnrealEd", "BlueprintGraph", "Kismet", "KismetCompiler", "AssetTools", "AssetRegistry", "SlateCore", "Slate", "MaterialEditor", "Landscape", "LandscapeEditor", "MeshDescription", "StaticMeshDescription", "PCG", "Json" });
	}
}
