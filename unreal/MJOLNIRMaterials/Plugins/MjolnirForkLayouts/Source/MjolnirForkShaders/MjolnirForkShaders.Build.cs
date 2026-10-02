using UnrealBuildTool;

public class MjolnirForkShaders : ModuleRules
{
	public MjolnirForkShaders(ReadOnlyTargetRules Target) : base(Target)
	{
		PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;
		PrivateDependencyModuleNames.AddRange(new string[] { "Core", "RenderCore" });
	}
}
