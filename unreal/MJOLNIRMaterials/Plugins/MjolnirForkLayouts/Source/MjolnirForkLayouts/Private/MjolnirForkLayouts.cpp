// Recreates Halo: Campaign Evolved's uniform buffer layouts in the stock editor.
//
// The game runs a 343 fork of UE 5.5.4 whose global uniform buffers (View,
// Primitive, Scene, SceneTextures, ForwardLightData, DeferredLight,
// LumenCardPass and everything nesting them) carry members stock 5.5.4 does
// not. A shader records the uniform buffers it reads by layout hash, and the
// game binds a buffer only when it knows that hash, so a material compiled
// against stock layouts finds View unbound and crashes the renderer.
//
// At PostEngineInit (after the engine built its layouts, before anything here
// cooks) this module rewrites each differing FShaderParametersMetadata to the
// fork's definition - read from the game's own memory by tools/ue/ub_dump.py
// into Config/ForkUniformBuffers.json - re-runs the engine's own layout and
// declaration initialisers on it, creates the nested structs only the fork
// has, and checks every global struct's layout hash against the game's. The
// generated HLSL declarations and hashes then match the fork, so shaders
// compiled afterwards bind in the game. It does not touch C++ struct types:
// the editor must not render with the patched layouts, which is why this is
// meant for the cook commandlet.

#include "Modules/ModuleManager.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"
#include "Dom/JsonObject.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"
#include "ShaderParameterMetadata.h"
#include "RHI.h"
#include "ShaderCompilerCore.h"

DEFINE_LOG_CATEGORY_STATIC(LogMjolnirForkLayouts, Log, All);

// Private member access through explicit template instantiation (access
// checking does not apply to the arguments of an explicit instantiation).
namespace MjolnirPrivate
{
	template <typename Tag, typename Tag::Type Member>
	struct TAccess
	{
		friend typename Tag::Type Get(Tag) { return Member; }
	};

	using FMember = FShaderParametersMetadata::FMember;

	struct FMembersTag { using Type = TArray<FMember> FShaderParametersMetadata::*; friend Type Get(FMembersTag); };
	struct FSizeTag { using Type = const uint32 FShaderParametersMetadata::*; friend Type Get(FSizeTag); };
	struct FLayoutTag { using Type = FUniformBufferLayoutRHIRef FShaderParametersMetadata::*; friend Type Get(FLayoutTag); };
	struct FDeclTag { using Type = FThreadSafeSharedStringPtr FShaderParametersMetadata::*; friend Type Get(FDeclTag); };
	struct FDeclAnsiTag { using Type = FThreadSafeSharedAnsiStringPtr FShaderParametersMetadata::*; friend Type Get(FDeclAnsiTag); };
	struct FTableCacheTag { using Type = TArray<FUniformResourceEntry> FShaderParametersMetadata::*; friend Type Get(FTableCacheTag); };
	struct FNameBufferTag { using Type = FThreadSafeNameBufferPtr FShaderParametersMetadata::*; friend Type Get(FNameBufferTag); };
	struct FInitLayoutTag { using Type = void (FShaderParametersMetadata::*)(FRHIUniformBufferLayoutInitializer*); friend Type Get(FInitLayoutTag); };
	struct FInitDeclTag { using Type = void (FShaderParametersMetadata::*)(); friend Type Get(FInitDeclTag); };

	template struct TAccess<FMembersTag, &FShaderParametersMetadata::Members>;
	template struct TAccess<FSizeTag, &FShaderParametersMetadata::Size>;
	template struct TAccess<FLayoutTag, &FShaderParametersMetadata::Layout>;
	template struct TAccess<FDeclTag, &FShaderParametersMetadata::UniformBufferDeclaration>;
	template struct TAccess<FDeclAnsiTag, &FShaderParametersMetadata::UniformBufferDeclarationAnsi>;
	template struct TAccess<FTableCacheTag, &FShaderParametersMetadata::ResourceTableCache>;
	template struct TAccess<FNameBufferTag, &FShaderParametersMetadata::MemberNameBuffer>;
	template struct TAccess<FInitLayoutTag, &FShaderParametersMetadata::InitializeLayout>;
	template struct TAccess<FInitDeclTag, &FShaderParametersMetadata::InitializeUniformBufferDeclaration>;
}

namespace
{
	using namespace MjolnirPrivate;

	/** Strings handed to metadata must outlive it; these never die. */
	const TCHAR* Persist(const FString& S)
	{
		static TArray<TUniquePtr<FString>> Storage;
		Storage.Add(MakeUnique<FString>(S));
		return **Storage.Last();
	}

	const ANSICHAR* PersistAnsi(const FString& S)
	{
		static TArray<TUniquePtr<TArray<ANSICHAR>>> Storage;
		auto Bytes = MakeUnique<TArray<ANSICHAR>>();
		const FTCHARToUTF8 Utf8(*S);
		Bytes->Append(Utf8.Get(), Utf8.Length());
		Bytes->Add(0);
		Storage.Add(MoveTemp(Bytes));
		return Storage.Last()->GetData();
	}

	FString StringField(const TSharedPtr<FJsonObject>& Obj, const TCHAR* Name)
	{
		FString Out;
		Obj->TryGetStringField(Name, Out);
		return Out;
	}

	uint32 UintField(const TSharedPtr<FJsonObject>& Obj, const TCHAR* Name)
	{
		double Out = 0;
		Obj->TryGetNumberField(Name, Out);
		return (uint32)Out;
	}

	bool SameMember(const FMember& A, const FMember& B)
	{
		return FCString::Strcmp(A.GetName(), B.GetName()) == 0
			&& FCString::Strcmp(A.GetShaderType(), B.GetShaderType()) == 0
			&& A.GetOffset() == B.GetOffset()
			&& A.GetBaseType() == B.GetBaseType()
			&& A.GetPrecision() == B.GetPrecision()
			&& A.GetNumRows() == B.GetNumRows()
			&& A.GetNumColumns() == B.GetNumColumns()
			&& A.GetNumElements() == B.GetNumElements()
			&& A.GetStructMetadata() == B.GetStructMetadata();
	}

	bool SameMembers(const TArray<FMember>& A, const TArray<FMember>& B)
	{
		if (A.Num() != B.Num())
		{
			return false;
		}
		for (int32 i = 0; i < A.Num(); ++i)
		{
			if (!SameMember(A[i], B[i]))
			{
				return false;
			}
		}
		return true;
	}

	/** A member as stock HLSL addresses it, by value (it must outlive the
	 *  arrays patching replaces). */
	struct FLeaf
	{
		EUniformBufferBaseType Base;
		uint32 Rows;
		uint32 Columns;
		uint32 Elements;
	};

	/** Every member path: nested structs add "Name.", included structs add
	 *  nothing. Structs themselves are not leaves. */
	void Leaves(const TArray<FMember>& Members, const FString& Prefix, TMap<FString, FLeaf>& Out)
	{
		for (const FMember& M : Members)
		{
			const EUniformBufferBaseType Base = M.GetBaseType();
			if (Base == UBMT_NESTED_STRUCT && M.GetStructMetadata())
			{
				Leaves(M.GetStructMetadata()->GetMembers(), Prefix + M.GetName() + TEXT("."), Out);
			}
			else if (Base == UBMT_INCLUDED_STRUCT && M.GetStructMetadata())
			{
				Leaves(M.GetStructMetadata()->GetMembers(), Prefix, Out);
			}
			else
			{
				Out.Add(Prefix + M.GetName(), FLeaf{ Base, M.GetNumRows(), M.GetNumColumns(), M.GetNumElements() });
			}
		}
	}

	class FForkLayouts
	{
	public:
		/** Stock member paths of every global struct, taken before anything is
		 *  patched (patching one struct changes the paths of all that nest it). */
		TMap<const FShaderParametersMetadata*, TMap<FString, FLeaf>> StockLeaves;

		int32 Patched = 0;
		int32 Created = 0;

		/** The metadata matching Def: Stock itself when it already matches,
		 *  Stock patched in place when it does not, a new struct when the
		 *  stock editor has none. */
		FShaderParametersMetadata* Resolve(const TSharedPtr<FJsonObject>& Def, FShaderParametersMetadata* Stock, const FString& Path)
		{
			if (FShaderParametersMetadata** Done = Resolved.Find(Def.Get()))
			{
				return *Done;
			}

			TArray<FMember> Members;
			const TArray<TSharedPtr<FJsonValue>>* JsonMembers = nullptr;
			Def->TryGetArrayField(TEXT("members"), JsonMembers);
			const TArray<FMember>* StockMembers = Stock ? &(Stock->*Get(FMembersTag())) : nullptr;
			if (JsonMembers)
			{
				for (const TSharedPtr<FJsonValue>& Value : *JsonMembers)
				{
					const TSharedPtr<FJsonObject> M = Value->AsObject();
					const FString Name = StringField(M, TEXT("name"));
					const FString ShaderType = StringField(M, TEXT("shader_type"));
					const FMember* StockMember = nullptr;
					if (StockMembers)
					{
						StockMember = StockMembers->FindByPredicate([&](const FMember& X) { return Name.Equals(X.GetName(), ESearchCase::CaseSensitive); });
					}

					const FShaderParametersMetadata* Nested = nullptr;
					const TSharedPtr<FJsonObject>* NestedDef = nullptr;
					if (M->TryGetObjectField(TEXT("struct"), NestedDef) && NestedDef && NestedDef->IsValid())
					{
						FShaderParametersMetadata* NestedStock = StockMember ? const_cast<FShaderParametersMetadata*>(StockMember->GetStructMetadata()) : nullptr;
						Nested = Resolve(*NestedDef, NestedStock, Path + TEXT(".") + Name);
					}

					const TCHAR* NameP = StockMember ? StockMember->GetName() : Persist(Name);
					const TCHAR* TypeP = (StockMember && ShaderType.Equals(StockMember->GetShaderType(), ESearchCase::CaseSensitive)) ? StockMember->GetShaderType() : Persist(ShaderType);
					Members.Emplace(
						NameP, TypeP, 0, UintField(M, TEXT("offset")),
						(EUniformBufferBaseType)UintField(M, TEXT("base")),
						(EShaderPrecisionModifier::Type)UintField(M, TEXT("precision")),
						UintField(M, TEXT("rows")), UintField(M, TEXT("cols")), UintField(M, TEXT("elements")),
						Nested);
				}
			}

			const uint32 Size = UintField(Def, TEXT("size"));
			FString WantHash;
			const bool bHasHash = Def->TryGetStringField(TEXT("hash"), WantHash) && !WantHash.IsEmpty();

			FShaderParametersMetadata* Result = Stock;
			const bool bGlobal = Stock && Stock->GetUseCase() != FShaderParametersMetadata::EUseCase::ShaderParameterStruct;
			bool bMatches = false;
			if (Stock)
			{
				const bool bMembersMatch = SameMembers(*StockMembers, Members) && Stock->GetSize() == Size;
				const bool bHashMatches = !bHasHash || FString::Printf(TEXT("%08x"), Stock->GetLayoutHash()) == WantHash;
				bMatches = bMembersMatch && bHashMatches;
			}
			if (bGlobal && !bMatches)
			{
				// A global uniform buffer is found by name and static slot, so it
				// is changed in place. Stock shader source that reads a member the
				// fork removed still has to compile; Compat() maps those.
				Patch(Stock, MoveTemp(Members), Size);
				if (const TMap<FString, FLeaf>* Before = StockLeaves.Find(Stock))
				{
					Compat(Stock, *Before);
				}
				++Patched;
				UE_LOG(LogMjolnirForkLayouts, Display, TEXT("patched %s (%s)"), Stock->GetStructTypeName(), *Path);
			}
			else if (!Stock || !bMatches)
			{
				// A nested parameter struct is cloned, never changed in place:
				// global shaders' own parameter structs nest the stock one and
				// must keep binding the stock HLSL.
				const FString Variable = StringField(Def, TEXT("variable"));
				Result = new FShaderParametersMetadata(
					FShaderParametersMetadata::EUseCase::ShaderParameterStruct,
					(EUniformBufferBindingFlags)UintField(Def, TEXT("binding_flags")),
					Persist(StringField(Def, TEXT("layout_name"))),
					Persist(StringField(Def, TEXT("type"))),
					Variable.IsEmpty() ? nullptr : Persist(Variable),
					nullptr,
					PersistAnsi(TEXT("MjolnirForkLayouts")),
					0,
					Size,
					Members,
					false,
					nullptr,
					(FShaderParametersMetadata::EUsageFlags)UintField(Def, TEXT("usage_flags")));
				++Created;
				UE_LOG(LogMjolnirForkLayouts, Display, TEXT("created %s (%s)"), Result->GetStructTypeName(), *Path);
			}
			Resolved.Add(Def.Get(), Result);
			return Result;
		}

	private:
		TMap<const FJsonObject*, FShaderParametersMetadata*> Resolved;

		/** Keep stock shader source compiling against the fork's layout. The
		 *  shader compiler rewrites `UB.Path.Member` in place into the global
		 *  a `UB_DECL_*` line names (CleanupUniformBufferCode), so each stock
		 *  member the fork removed gets a line of its own: a resource maps onto
		 *  the fork's renamed equivalent when one sits beside it (the global
		 *  name must be no longer than the member path), a scalar onto a static
		 *  of the same name length. Neither touches the constant buffer, so
		 *  the layout and its hash stay the fork's. */
		static void Compat(FShaderParametersMetadata* Meta, const TMap<FString, FLeaf>& Before)
		{
			TMap<FString, FLeaf> ForkLeaves;
			Leaves(Meta->GetMembers(), TEXT(""), ForkLeaves);
			const FString Var = Meta->GetShaderVariableName();
			// Members the fork renamed (later-UE MegaLights work), stock -> fork.
			// A rename is a preprocessor define: macros expand before the
			// compiler's member rewrite, so `X.Path.Stock` reaches the fork's
			// member at any depth (the rewrite itself only accepts a
			// replacement of exactly the original's length).
			static const TMap<FString, FString> Renames = {
				{ TEXT("ForwardLocalLightBuffer"), TEXT("ForwardLightBuffer") },
			};

			FString Statics;
			FString Lines;
			TSet<FString> Defined;
			for (const auto& Pair : Before)
			{
				if (ForkLeaves.Contains(Pair.Key))
				{
					continue;
				}
				const FLeaf& M = Pair.Value;
				FString Parent, Leaf = Pair.Key;
				Pair.Key.Split(TEXT("."), &Parent, &Leaf, ESearchCase::CaseSensitive, ESearchDir::FromEnd);
				if (const FString* Rename = Renames.Find(Leaf))
				{
					const FString RenamedPath = Parent.IsEmpty() ? *Rename : Parent + TEXT(".") + *Rename;
					if (ForkLeaves.Contains(RenamedPath))
					{
						if (!Defined.Contains(Leaf))
						{
							Statics += FString::Printf(TEXT("#define %s %s\n"), *Leaf, **Rename);
							Defined.Add(Leaf);
						}
						UE_LOG(LogMjolnirForkLayouts, Display, TEXT("  %s.%s -> %s (renamed in the fork)"), *Var, *Pair.Key, *RenamedPath);
						continue;
					}
				}
				const FString Global = Pair.Key.Replace(TEXT("."), TEXT("_"));
				const TCHAR* Scalar = nullptr;
				switch (M.Base)
				{
				case UBMT_BOOL: Scalar = TEXT("bool"); break;
				case UBMT_INT32: Scalar = TEXT("int"); break;
				case UBMT_UINT32: Scalar = TEXT("uint"); break;
				case UBMT_FLOAT32: Scalar = TEXT("float"); break;
				default: break;
				}
				if (Scalar && M.Rows <= 1 && M.Columns <= 1 && M.Elements == 0)
				{
					Statics += FString::Printf(TEXT("static %s %s_%s;\n"), Scalar, *Var, *Global);
					Lines += FString::Printf(TEXT("UB_DECL_PARAMETER(%s,%s,%s);\n"), *Var, *Pair.Key, *Global);
					UE_LOG(LogMjolnirForkLayouts, Display, TEXT("  %s.%s -> static (removed in the fork)"), *Var, *Pair.Key);
				}
				else
				{
					UE_LOG(LogMjolnirForkLayouts, Warning, TEXT("  %s.%s was removed in the fork and has no stand-in; stock source reading it will not compile"), *Var, *Pair.Key);
				}
			}
			if (Lines.IsEmpty() && Statics.IsEmpty())
			{
				return;
			}

			FThreadSafeSharedStringPtr& Decl = Meta->*Get(FDeclTag());
			FString Text = *Decl;
			const FString Header = FString::Printf(TEXT("UniformBuffer %s\n"), *Var);
			const int32 HeaderAt = Text.Find(Header, ESearchCase::CaseSensitive);
			const int32 EndAt = Text.Find(TEXT("};"), ESearchCase::CaseSensitive, ESearchDir::FromEnd);
			if (HeaderAt == INDEX_NONE || EndAt == INDEX_NONE || EndAt < HeaderAt)
			{
				UE_LOG(LogMjolnirForkLayouts, Error, TEXT("%s: unexpected declaration shape, no stand-ins added"), *Var);
				return;
			}
			Text.InsertAt(EndAt, Lines);
			Text.InsertAt(HeaderAt, Statics);
			Decl = MakeShareable(new FString(Text));
			TArray<ANSICHAR>* Ansi = new TArray<ANSICHAR>;
			ShaderConvertAndStripComments(Text, *Ansi);
			(Meta->*Get(FDeclAnsiTag())) = MakeShareable(Ansi);
		}

		static void Patch(FShaderParametersMetadata* Meta, TArray<FMember>&& Members, uint32 Size)
		{
			Meta->*Get(FMembersTag()) = MoveTemp(Members);
			const_cast<uint32&>(Meta->*Get(FSizeTag())) = Size;
			(Meta->*Get(FLayoutTag())).SafeRelease();
			(Meta->*Get(FInitLayoutTag()))(nullptr);
			if (Meta->GetUseCase() != FShaderParametersMetadata::EUseCase::ShaderParameterStruct)
			{
				(Meta->*Get(FDeclTag())).Reset();
				(Meta->*Get(FDeclAnsiTag())).Reset();
				(Meta->*Get(FTableCacheTag())).Empty();
				(Meta->*Get(FNameBufferTag())).Reset();
				(Meta->*Get(FInitDeclTag()))();
			}
		}
	};

	void ApplyForkLayouts()
	{
		const FString Path = FPaths::Combine(FPaths::ProjectConfigDir(), TEXT("ForkUniformBuffers.json"));
		FString Text;
		if (!FFileHelper::LoadFileToString(Text, *Path))
		{
			UE_LOG(LogMjolnirForkLayouts, Warning, TEXT("no %s; stock uniform buffer layouts kept"), *Path);
			return;
		}
		TSharedPtr<FJsonObject> Root;
		if (!FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Text), Root) || !Root.IsValid())
		{
			UE_LOG(LogMjolnirForkLayouts, Error, TEXT("%s does not parse"), *Path);
			return;
		}

		TMap<FString, FShaderParametersMetadata*> StockGlobals;
		for (TLinkedList<FShaderParametersMetadata*>::TIterator It(FShaderParametersMetadata::GetStructList()); It; It.Next())
		{
			StockGlobals.Add((*It)->GetStructTypeName(), *It);
		}

		FForkLayouts Fork;
		for (const auto& Pair : StockGlobals)
		{
			Leaves(Pair.Value->GetMembers(), TEXT(""), Fork.StockLeaves.Add(Pair.Value));
		}
		for (const auto& Pair : Root->Values)
		{
			FShaderParametersMetadata** Stock = StockGlobals.Find(Pair.Key);
			if (!Stock)
			{
				// A global the stock editor does not have (the fork's own passes);
				// nothing here can compile against it, so it is left out.
				continue;
			}
			Fork.Resolve(Pair.Value->AsObject(), *Stock, Pair.Key);
		}

		int32 Matching = 0;
		int32 Mismatching = 0;
		for (const auto& Pair : Root->Values)
		{
			FShaderParametersMetadata** Stock = StockGlobals.Find(Pair.Key);
			if (!Stock)
			{
				continue;
			}
			const FString Want = StringField(Pair.Value->AsObject(), TEXT("hash"));
			const FString Have = FString::Printf(TEXT("%08x"), (*Stock)->GetLayoutHash());
			if (Want == Have)
			{
				++Matching;
			}
			else
			{
				++Mismatching;
				UE_LOG(LogMjolnirForkLayouts, Error, TEXT("%s: layout hash %s, the game's is %s"), *Pair.Key, *Have, *Want);
			}
		}
		UE_LOG(LogMjolnirForkLayouts, Display, TEXT("fork layouts: %d patched, %d created; %d global struct(s) match the game, %d do not"),
			Fork.Patched, Fork.Created, Matching, Mismatching);
	}
}

class FMjolnirForkLayoutsModule : public IModuleInterface
{
public:
	virtual void StartupModule() override
	{
		ApplyForkLayouts();
	}
};

IMPLEMENT_MODULE(FMjolnirForkLayoutsModule, MjolnirForkLayouts)
