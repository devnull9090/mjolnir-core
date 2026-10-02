// Recreates Halo: Campaign Evolved's GPU-scene primitive layout in the shaders
// the stock editor compiles.
//
// Vertex factories read each primitive's transform, bounds and custom data out
// of GPUScene's primitive buffer, at PrimitiveId * PRIMITIVE_SCENE_DATA_STRIDE
// float4s plus a fixed element index (Shared/SceneDefinitions.h,
// Private/SceneData.ush). 343's fork stores one more float4 per primitive (44,
// not 43), just ahead of the custom primitive data: the game's own shaders
// multiply primitive ids by 44, read every stock element up to 32 where stock
// does, and read custom data from element 35, never 34
// (docs/re/fork_renderer.md). A shader built with the stock stride reads some
// other primitive's transform: our probes rendered, correctly shaded, at
// another object's place and size.
//
// Shader source is found through virtual directory mappings, the most
// specific first, so mapping /Engine/Shared and /Engine/Private to patched
// copies overrides those two files for this project alone and leaves the
// engine install, and every other project using it, untouched. The copies are
// regenerated from the installed engine at every start, and each edit must
// match its stock text exactly once, so an engine update cannot be patched
// silently. Like MjolnirForkLayouts this is for the cook: the editor's own
// GPUScene still writes 43-float4 primitives, so do not render with it
// (-MjolnirStockShaders turns it off).

#include "Modules/ModuleManager.h"
#include "HAL/FileManager.h"
#include "Misc/CommandLine.h"
#include "Misc/FileHelper.h"
#include "Misc/Parse.h"
#include "Misc/Paths.h"
#include "ShaderCore.h"

DEFINE_LOG_CATEGORY_STATIC(LogMjolnirForkShaders, Log, All);

namespace
{
	struct FEdit
	{
		const TCHAR* File;    // relative to Engine/Shaders
		const TCHAR* Stock;   // must occur exactly once
		const TCHAR* Fork;
	};

	const FEdit GEdits[] = {
		{ TEXT("Shared/SceneDefinitions.h"),
		  TEXT("#define PRIMITIVE_SCENE_DATA_STRIDE 43"),
		  TEXT("#define PRIMITIVE_SCENE_DATA_STRIDE 44 // MJOLNIR: the fork's primitive layout") },
		{ TEXT("Private/SceneData.ush"),
		  TEXT("LoadPrimitivePrimitiveSceneDataElement(PrimitiveIndex,  34 + DataIndex)"),
		  TEXT("LoadPrimitivePrimitiveSceneDataElement(PrimitiveIndex,  35 + DataIndex) /* MJOLNIR: fork */") },
	};

	const TCHAR* GDirectories[] = { TEXT("Shared"), TEXT("Private") };

	/** Copies Engine/Shaders/<Dir> under Root, rewriting only files whose bytes differ. */
	bool Mirror(const FString& From, const FString& To)
	{
		TArray<FString> Files;
		IFileManager::Get().FindFilesRecursive(Files, *From, TEXT("*"), true, false);
		for (const FString& Source : Files)
		{
			FString Relative = Source;
			FPaths::MakePathRelativeTo(Relative, *(From / TEXT("")));
			const FString Dest = To / Relative;
			TArray<uint8> A, B;
			if (!FFileHelper::LoadFileToArray(A, *Source))
			{
				return false;
			}
			if (IFileManager::Get().FileSize(*Dest) == A.Num() && FFileHelper::LoadFileToArray(B, *Dest) && A == B)
			{
				continue;
			}
			if (!FFileHelper::SaveArrayToFile(A, *Dest))
			{
				return false;
			}
		}
		return Files.Num() > 0;
	}
}

class FMjolnirForkShadersModule : public IModuleInterface
{
public:
	virtual void StartupModule() override
	{
		if (FParse::Param(FCommandLine::Get(), TEXT("MjolnirStockShaders")))
		{
			UE_LOG(LogMjolnirForkShaders, Display, TEXT("fork shaders: off (-MjolnirStockShaders)"));
			return;
		}
		const FString Engine = FPaths::ConvertRelativePathToFull(FPaths::EngineDir() / TEXT("Shaders"));
		const FString Root = FPaths::ConvertRelativePathToFull(FPaths::ProjectIntermediateDir() / TEXT("MjolnirForkShaders"));

		for (const TCHAR* Dir : GDirectories)
		{
			if (!Mirror(Engine / Dir, Root / Dir))
			{
				UE_LOG(LogMjolnirForkShaders, Error, TEXT("fork shaders: could not mirror %s; shaders stay stock"), Dir);
				return;
			}
		}
		for (const FEdit& Edit : GEdits)
		{
			const FString Path = Root / Edit.File;
			FString Text;
			FFileHelper::LoadFileToString(Text, *(Engine / Edit.File));
			const int32 First = Text.Find(Edit.Stock, ESearchCase::CaseSensitive);
			const int32 Last = Text.Find(Edit.Stock, ESearchCase::CaseSensitive, ESearchDir::FromEnd);
			if (First == INDEX_NONE || First != Last)
			{
				UE_LOG(LogMjolnirForkShaders, Error, TEXT("fork shaders: %s does not hold \"%s\" exactly once (engine changed?); shaders stay stock"), Edit.File, Edit.Stock);
				return;
			}
			Text.ReplaceInline(Edit.Stock, Edit.Fork, ESearchCase::CaseSensitive);
			FString Existing;
			if (IFileManager::Get().FileSize(*Path) < 0 || !FFileHelper::LoadFileToString(Existing, *Path) || Existing != Text)
			{
				FFileHelper::SaveStringToFile(Text, *Path);
			}
		}
		for (const TCHAR* Dir : GDirectories)
		{
			AddShaderSourceDirectoryMapping(FString(TEXT("/Engine/")) + Dir, Root / Dir);
		}
		UE_LOG(LogMjolnirForkShaders, Display, TEXT("fork shaders: /Engine/Shared and /Engine/Private mapped to %s (%d edit(s))"), *Root, UE_ARRAY_COUNT(GEdits));
	}
};

IMPLEMENT_MODULE(FMjolnirForkShadersModule, MjolnirForkShaders)
