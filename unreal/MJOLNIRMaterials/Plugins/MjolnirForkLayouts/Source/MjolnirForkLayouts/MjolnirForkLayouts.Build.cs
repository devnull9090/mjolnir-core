using UnrealBuildTool;

public class MjolnirForkLayouts : ModuleRules
{
	public MjolnirForkLayouts(ReadOnlyTargetRules Target) : base(Target)
	{
		PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;
		PrivateDependencyModuleNames.AddRange(new string[] { "Core", "CoreUObject", "Engine", "RenderCore", "RHI", "Json", "Projects" });
	}
}
