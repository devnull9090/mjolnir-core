# Loading a brand-new scenario (2026-09-03)

How Halo: Campaign Evolved decides whether a scenario name can launch, what a
new scenario package needs, and how far a new one (`PG1`) gets today. Every
claim below was checked in the running game (CU4, host exe PE timestamp
`0x8a03f777`) or read out of the shipping binary; the probe tooling is in
`native/scenario_probe/` and the raw run log is `probe_log_2026-09-02.md`.

## The 2026-08-20 "closed door" was a misdiagnosis

The standalone container that `mjolnir level bake --standalone <CODE>` builds
**is** mounted into the UE package store. A vtable-slot hook on
`FFilePackageStoreBackend` (vtable RVA `0xB446618`; slot 2 `BeginRead`,
slot 4 `GetPackageStoreEntry`) listed it among the mounted containers with
one package registered (`FMountedContainer::NumMountedPackages == 1`). Every
piece of that container format — `FPackageId`, `ContainerHeader`, BLAKE3
metas, directory index — was already right.

What proved nothing was the probe: UE4SS's Lua `LoadAsset` never reaches the
package store for a package it does not know (a made-up name and the new
package both produced zero `GetPackageStoreEntry` calls), so "LoadAsset
returns invalid" measured UE4SS's own gatekeeping, not the loader.

## What gates a scenario name

Read from the exe (RVAs image-relative) and confirmed live:

1. `UBlamCampaignFlowGameSubsystem::SetAndBeginCampaign` — exec thunk
   `0x7B433C0`, implementation `0x7B446E0` — does a **linear scan of the
   active campaign asset's `ScenarioList`** (`TArray<FDataTableRowHandle>` at
   `UBlamCampaignDataAsset + 0x40`, 16-byte elements `{UDataTable*, FName}`)
   comparing the 64-bit `FName`. No match → `CurrentScenarioIndex` stays −1 →
   `false` in under a millisecond with no Blam error. Nothing here touches
   tags, the IoDispatcher or the package store.
2. `StartScenario` (`0x7B44CB0`) fetches the row from
   `/Game/Blueprints/Campaign/DT_Scenarios` (a `UDataTable`, 13 rows, row
   struct `BlamScenarioDataTableRow`), fails if the row is missing, if
   `UnrealLevel` is unset or if `ScenarioName` is shorter than two characters,
   then derives the scenario tag's package path from the row and opens it via
   `0x7B9F240`: `FPackageId::FromName` → `FIoDispatcher::GetSizeForChunk`
   (chunk **existence**, not the package store). Tag reads go through the
   `TagIoHandler` (`0x7B9EBB0`), which consults
   `BlamCookedTagReferencesEngineSubsystem` when the cvar
   `Blam.TagIoHandler.IoStore.UseCookedTagReferences.Enabled` (backing byte
   `.data 0xD0A94DC`, default 1) is set.

### `BlamScenarioDataTableRow` (176 bytes per row)

| offset | field | notes |
|---|---|---|
| +0 | vtable (`FTableRowBase`) | |
| +8 | `UnrealLevel` `TSoftObjectPtr<UWorld>` | weak ptr @8, `FTopLevelAssetPath` @16 (package FName, asset FName), sub-path FString @32 |
| +48 | `ScenarioName` `FString` | `"B40"` — the codename the tag path is derived from |
| +64 | `MapGuid` | |
| +80 / +96 | `MissionTitle` / `MissionDescription` `FText` | |
| +112 | `MissionPreviewImage` soft ptr | |
| +152 | `InsertionPointsDataAsset` `UObject*` | drives RALLY POINT SELECT |
| +160 | `ProgressionUnlockTag` `FName` | |

`UDataTable::RowMap` is a `TMap<FName, uint8*>` at `+0x30` (UE 5.5 `TSet`
layout: elements `{ptr,num,max}` @0x30, inline allocation bits @0x40, `NumBits`
@0x58, hash buckets pointer @0x70, `HashSize` @0x78; 24-byte elements
`{FName, uint8*, HashNext, HashIndex}`). Bucket = `GetTypeHash(FName) &
(HashSize-1)` with the 5.5 `FNameEntryHandle` hash
`(block<<19)+block+(offset<<16)+offset+(offset>>4)` (block = id>>16, offset =
id&0xffff), verified against all 13 shipped rows.

### `BlamCookedTagReferencesEngineSubsystem`

`+0x30` `TArray<FString>` of 10,201 cooked tag package paths — element index is
the runtime **tag index**; searched by `TArray<FString>::Find` (linear,
case-insensitive). `+0x40` `TMap<int32 tag index, TArray<int32>>` with 13
entries (one per shipped scenario), each the list of tag indices that scenario
references — the preload set. `0x1fff` at `+0x50` is the sparse array's
inline allocation bits (13 live elements), not a hash mask.

## What a new scenario needs

1. **Its package in its own folder**:
   `/Game/Tags/Levels/Halo1/Solo/<CODE>/_Generated_/<CODE>-scenario`. The
   flow derives that path from the row, so a package left in the donor's
   folder is never found. `mjolnir level bake --standalone` now renames the
   folder segment as well as the leaf (still same-length surgery; codenames
   are three characters like every shipped one).
2. **A `DT_Scenarios` row** — clone B40's 176 bytes, replace `ScenarioName`.
3. **A `ScenarioList` handle** `{DT_Scenarios, FName(<CODE>)}` on the campaign
   asset (`DA_FirstPlayableCampaign`).
4. Optionally its path appended to the cooked-references path table and a
   per-scenario reference entry (borrowing B40's list); the spare capacity in
   both arrays is enough without reallocation.

With 1–3 in place, **`SetAndBeginCampaign(DA_FirstPlayableCampaign, "PG1")`
returns true**, the row's world loads, and the only
`BlamScenarioTagDataAsset` in memory is
`/Game/Tags/Levels/Halo1/Solo/PG1/_Generated_/PG1-scenario` — served from the
mod container. The real CAMPAIGN → NEW GAME → MISSION SELECT screen shows PG1
as an eleventh mission (with the cloned row's title) and launches it through
the game's own flow.

## What still blocks

The simulation does not start for PG1: the pawn stays at the origin and the
frame is black, while shipped missions started through the same menu run. The
stall has a precise signature (measured 2026-09-03 on CU4, host pid 13828):

| signal | shipped mission (B40) | new scenario (PG1) |
|---|---|---|
| `SetAndBeginCampaign` returns | true | true |
| scenario tag asset in memory | `B40-scenario` | `PG1-scenario` (mod container) |
| `ServerMarkFinishedBlamMapLoad` | fires ~4 s after launch | never fires |
| `bWaitingForBlamGameplayStart` | clears | stays true |

So the blocker sits in the Blam simulation's own map load, upstream of every
UE-side gate. Three candidates were ruled out by experiment:

- **The world's scenario actor is not the binding.** `BlamScenario` is an
  `Actor` subclass (`ScenarioName`, `CampaignId`, `MapId`, `MAPNAME`,
  `StructureBsps`, `ZoneSets`...) and the cooked B40 world package does contain
  an export named `BlamScenario_UAID_F02F74DC4569B31902`. But in the loaded,
  stalled world `FindAllOf("BlamScenario")` returns **zero** actors and no
  actor's name contains "BlamScenario" (28 actors; the only Blam-named one is
  `BP_BlamCameraManager_C`). The actor is spawned *after* the sim's map load
  succeeds, so it cannot be what refuses PG1. The B40 world also does not
  import `B40-scenario`.
- **The UE map-load handshake is downstream.** Calling
  `ServerMarkFinishedBlamMapLoad`, `ServerMarkHasFinishedHaloActorPooling` and
  `ServerMarkHasFinishedProcessingPsoCache` by hand flips all three flags,
  brings `BlamNetworkGameStateComponent::bSessionRunning` to true and spawns a
  `BP_MeteoritePawn_C` — but `bWaitingForBlamGameplayStart` stays true and the
  pawn stays at the origin. Forcing the handshake does not start the sim.
- **The cooked-reference table is not the gate.** With
  `Blam.TagIoHandler.IoStore.UseCookedTagReferences.Enabled 0` (set through
  `KismetSystemLibrary::ExecuteConsoleCommand`; the backing byte at
  `.data 0xD0A94DC` reads 0 afterwards) a shipped mission still loads and
  plays normally, and PG1 still stalls identically. Adding PG1 to the path
  table and cloning B40's per-scenario reference list (earlier run) also
  changed nothing.

Remaining hypotheses, cheapest first:

- The sim keys campaign maps by **name** through its own registry. The Blam
  console carries `levels_add_campaign_map` and
  `levels_add_campaign_map_with_id`, but both are stubs in this release build,
  so the registry (if it exists) cannot be extended from the console.
- Something in the scenario's own root fields (`map id`, `campaign id`,
  `map name` string id) is matched against a sim-side table. The scnr field
  documentation in the sim binary describes `map name` as "Used to associate
  external resources with" the scenario.
- The loading pipeline itself: a tick state machine at RVA `0x7B48160`
  (registered by `0x7B47FE0`, which sets a state byte at `+0xD9` and a repeating
  timer) dispatches five states, one of which consults the cooked-reference
  lookup (`0x6720650`, the same helper `BuildTagIoRequest` uses) and one of
  which is a float-timeout wait at `+0x1F0`/`+0x1F4`. Instrumenting that state
  byte during a PG1 load is the next concrete step.

## The name is fine; the package is not (2026-09-03, second session)

A clean discriminator settles what the simulation actually rejects. Inject a
data-table row keyed `PG2` — a name the game has never seen — but leave its
`ScenarioName` field reading `B40`, so the flow derives the *shipped* tag path
from it. Launched from MISSION SELECT as an eleventh mission, that row starts
normally: `ServerMarkFinishedBlamMapLoad` fires 1.8 s later and the mission
plays.

So new names, new `DT_Scenarios` rows and new `ScenarioList` entries are all
accepted. What the simulation refuses is a **new scenario tag package**, even
one whose `.uasset` and `.ubulk` are byte-identical to a shipped scenario's
(verified: both chunks ship in the mod container at the same sizes, and a
byte search for the donor codename finds the same 46 and 413 hits at the same
offsets as the shipped tag). Until the tag registry the simulation builds at
startup can be extended, a custom map has to ride on a shipped scenario tag,
with a new menu row pointing at that shipped codename.

Also worth keeping: a bare `SetAndBeginCampaign` from script does not
cold-start the simulation *even for a shipped mission* — it returns true, the
world loads, and no map-load mark ever arrives. Only the menu flow brings the
session up, so it is not a shortcut for automation and not evidence about a
new scenario.

## Making a blank map out of a shipped mission

`mjolnir level bake` now strips a mission to bare geometry. `blam.clear` takes
the placement flags it always had plus a `blocks` list naming any other root
block to empty, and `clear.scripts` no longer just empties the script block:

```json
"clear": { "squads": true, "vehicles": true, "scripts": true,
           "blocks": ["scenery", "machines", "trigger volumes",
                      "scenario kill triggers"] }
```

**A map with no script at all boots black and frozen.** Blam hands a level to
the player from the mission's own script: the screen starts faded out, the
camera is under script control and player input is off. B40 in particular
opens with the player belted into a Pelican for the intro cinematic, so a
script-less bake leaves a live simulation the player cannot see or move in —
the simulation is fine (a console `player_teleport` moves the unit), only the
handover never happens. `clear.scripts` therefore compiles a replacement
section holding one script:

```
(script startup mjolnir_level_startup
  (begin
    (fade_in 0 0 0 15)
    (camera_control false)
    (player_enable_input true)))
```

That is enough: the map fades in, the player owns the camera and walks.
`examples/levels/blank_b40.level.json` is the worked example — B40 with every
placement, every AI, every trigger and the whole mission script gone, plus a
sky and four landmark shapes spawned by the runtime loader.

## Runtime insertion (probe recipe)

`native/scenario_probe/tagrefs_probe.c` exports, loaded from the UE4SS Lua
sandbox with `package.loadlib(path, "<export>")()` and driven through small
request files next to the DLL:

| export | request file | effect |
|---|---|---|
| `dump_bytes` | `dump_req.txt` = `<hex addr> <len>` | hexdump to `tagrefs.log` |
| `dt_addrow` | `dt_req.txt` = `<table> <template row> <fname idx> <row size> <name>` | clone a row, replace `ScenarioName`, insert into `RowMap` |
| `scenlist_append` | `scenlist_req.txt` = `<TArray addr> <fname idx> <number>` | grow `ScenarioList` by one handle |
| `tagrefs_append` | `tagrefs_addr.txt`, `tagrefs_append.txt` | append a path to the cooked path table |
| `refs_addentry` | `refs_req.txt` = `<subsystem> <key> <template key>` | add a per-scenario reference entry |

`store_probe.c` hooks the package-store backend (`probe_open`,
`probe_logall`, `probe_close`) and writes `store_probe.log`.

Hazards learned the hard way: an `FString` is `{ptr, Num @+8, Max @+12}` (a
count written at +4 corrupted the pointer's high dword and crashed
`StartScenario`); assigning an `FText` from UE4SS Lua to a menu item crashes
in the `HaloUIViewItemData` destructor at the next garbage collection (set
only `StartingScenarioName`/`CampaignData` on a *shipped* `BP_DebugMapItemData_C`);
buffers the probe allocates with `HeapAlloc` are freed by `FMemory::Free` at
shutdown (exit crash) — a shipping mod must allocate through the engine or
only grow into existing capacity.

Two exe details worth keeping: `mjolnir_mission <CODE>` cannot cold-start the
sim on CU4 (the UI performs a session bring-up the bare call does not), and
UE4SS `LoadAsset` is not a loader probe.

## 2026-09-11: the door is open — the row has to be cooked

The "new package is refused" conclusion above was one step short. The
simulation does not resolve campaign maps from `DT_Scenarios` on demand; it
builds its own `levels` registry once, at boot, from the tables the
`BlamBuiltInMapInfoDataAsset` names — `/Game/Blueprints/Campaign/BuiltInMapInfoData`,
`CampaignMapInfoTables = [DT_Scenarios, DT_Test_Scenarios]` (`mjolnir ue get
--package BuiltInMapInfoData`). The sim side is Reach's levels system
(`HaloSimulation_tag_release.dll` CU4 `FUN_180322aa0` allocates the
"campaigns", "campaign levels" (64 × 0x274 bytes), "campaign insertions",
"multiplayer levels"… arrays; the console's `levels_add_campaign_map*` are
stubs pointing at the same no-op handlers). So a row injected at runtime
satisfied `StartScenario`, which reads the table then, but the registry the
simulation had already built did not know the codename — and a *shipped*
codename in a new row worked because the registry knew that one.

`blam-pack --example scenario_register <CODE>` cooks the row: it clones the
donor's `DT_Scenarios` row under the new name with `ScenarioName = CODE`
(`ue_asset::datatable` — the table's native tail is the u32 object trailer, a
u32 count, then `FName` + unversioned row struct per row, rebuilt byte for
byte before anything changes), appends a `ScenarioList` handle to
`DA_FirstPlayableCampaign`, and packs both into `pakchunk996-MJOLNIRREG-<CODE>_P`.

Verified live (CU4): with that container beside the standalone `PG1`
package from `mjolnir level bake --standalone PG1`, MISSION SELECT lists an
eleventh mission, and launching it **starts the simulation** —
`PG1-scenario` is the only scenario asset in memory, the pawn is placed,
`ServerMarkFinishedBlamMapLoad` fires, and B40's intro cinematic and mission
play on the new tag package. A brand-new scenario tag package loads.

What that opens: the scenario, its BSPs and its other tags can all live under
the new codename's folder (ordinary new tags were already proven to load by
name), so a map no longer has to override a shipped mission. What is still
shared is the UE side: the row's `UnrealLevel` points at B40's world, and a
brand-new world package has not been tried natively yet — `LoadAsset` was
never a valid probe for it either.

### The map's own BSP tags (later the same day)

`mjolnir level bake <file> --standalone BGL --bsp 8=<collision payload>` gives
the map its own structure BSP: the canvas scenario's `structure bsps[8]` pair
— `bsp_01_1_start` (sbsp) and its `scenario_structure_lighting_info` — is
cloned under `/Solo/BGL/_Generated_/`, the BSP with the given body, the
lighting info as shipped, and the baked scenario's two references are
repointed (`sbsp:levels\halo1\sologlsp_01_1_start`). The clones are the
shipped wrappers with the codename swapped into the package path — the same
same-length surgery as the scenario package — packed into the map container
beside it. Verified live: with no override of B40's BSP installed, BGL starts
and the pawn stands on the Blood Gulch collision at its start.

One negative result worth keeping: a BSP wrapper rebuilt from scratch by
`blam_pack::newtag::build` (the route that works for collision models and
projectiles) registers and the scenario loads, but the simulation never
starts the map — pawn at the origin, loader waiting. Whatever the structure
BSP's cooked wrapper carries beyond what `tagwrap` models, the map load needs
it, so BSPs are cloned, not rebuilt.

What is still B40's: the world (`UnrealLevel`) and the other 17 BSPs the
scenario references, all read-only shipped tags.

### The map's own Unreal world: not yet (later still; resolved in the next section)

`mjolnir level bake --standalone BGL --world <bare.umap>` ships the MapKit's
bare level renamed to `/Game/Levels/Halo1/Solo/BGL/BGL`
(`ZenPackage::rename_package`: package name, the world export's name and
public hash) in the map container, and points the row's `UnrealLevel` at it.
Launching BGL then bounces straight back to the frontend. The store probe
(`native/scenario_probe/store_probe.c`, watching the new world's id) shows
**no `GetPackageStoreEntry` lookup for it at all**, and `LoadAsset` from the
frontend returns nothing for any of our added packages — the BSP clone
included, which the simulation loads fine by its own tag path. So the UE
loader refuses a package it has never heard of before the package store is
consulted; the tag path (chunk existence + direct IoDispatcher reads) never
hits that gate, which is why every Blam tag we add loads and no Unreal asset
does.

Ruled out on the way: the directory index layout (a UE-staged
`../../../` + `Meteorite/Content/...` mount changes nothing), and
file-name existence — `BlueprintPathsLibrary::FileExists` is false for
shipped IoStore assets too, and the shipped `.pak` siblings are 339-byte
stubs with empty indexes. Pointing the row at the shipped
`/Game/levels/Test/SeamlessTravelTEst` (the only cooked test world) bounces
as well, so a world also has to be one the flow expects. Where the gate is —
`FPackageName::DoesPackageExist` (`"is either short package name or does
not exist"` is in the exe), a 343 package-store backend, or the asset
registry — is the open reverse-engineering question; the CU4 exe is being
analyzed for it (`docs/re/ghidra_mcp.md`).

Until then `--world-object` can point a standalone map at any shipped world
by object path, and without either flag the map runs on the canvas
mission's world, which is what BGL ships with today.

### The world gate, found and passed (the same night)

The gate is not in the loader at all. It is the engine turning a **short map
name** into a package path, and it asks the AssetRegistry.

Found by redirecting call sites in the CU4 exe (`native/scenario_probe/
gate_probe.c`, `ar_probe.c`; `call rel32` patched to logging wrappers, no
prologue relocation) and reading the decompiles (`docs/re/ghidra_mcp.md`):

1. `BlamCampaignFlowGameSubsystem::StartScenario` (`FUN_147b44cb0`) first
   asks the BlamEngine module's tag object (module `+0x120`, virtual slot 3)
   whether `"/Game/Tags/" + <scenario name> + ".scenario"` exists —
   `Levels/Halo1/Solo/BGL/BGL` passes, our scenario tag is fine — and then
   requests a travel to the URL
   `BGL?SeamlessTravel?ScenarioName=BGL?InsertionPointIndex=0`. **The map is
   the row's world by its short name.**
2. `UEngine::Browse` → `MakeSureMapNameIsValid` (`FUN_1467789d0`): a name
   with a `/` goes to `FindObject`, then `FPackageName::DoesPackageExist`
   (IoStore chunk existence — this is the type-1 `DoesChunkExist` the chunk
   probe saw for B40). A name **without** a `/` goes to the AssetRegistry
   module's registry, `IAssetRegistry::GetFirstPackageByName(FStringView)`
   (virtual slot 30, `FUN_144614b60`, which consults the registry state's
   package-name index). No hit, no travel — and nothing downstream is ever
   asked, which is why no probe on the store or the dispatcher saw the new
   world.
3. The registry is `Meteorite/AssetRegistry.bin`, loaded once at boot
   (`FUN_144608f90`). `B40` is in it; `BGL` is not; `HasAssets` said as much
   from Lua all along.

Confirmed by answering the lookup: with slot 30 wrapped and the miss for
`BGL` answered with the FName `/Game/Levels/Halo1/Solo/BGL/BGL`, the travel
went through, `DoesChunkExist` and the package-store lookup fired for the
new world's id, and the game ran Blood Gulch on
`/Game/Levels/Halo1/Solo/BGL/BGL` — its own scenario, its own BSP, its own
world; B40 untouched.

**Shipped fix: `mods/MJOLNIRLevelLoader/native/mjolnir_map_registry.dll`**
(source `native/map_registry/`, built by its `build.ps1`, never committed —
CI and the mods release build it). The loader's Lua loads it at start; it
finds the registry through `FModuleManager` (no address hand-off), wraps
slot 30, and on a miss answers from the `.umap` files listed by the mounted
`.utoc` directory indexes in `Meteorite/Content/Paks` (World Partition
`_Generated_` cells skipped), building the FName the way the engine does
(`FUN_143709650` hash + `FUN_1436fcc60` intern). Shipped maps never reach the
fallback. That is why `blam_pack::build_addition` names files UE-style
(`../../../` mount, `Meteorite/Content/<path>.umap`): the index is the
manifest. `mjolnir_level_rescan` re-reads the containers after installing a
map while the game runs. Log: `native/map_registry.log`. CU4-only by RVA;
another build is refused with a log line and standalone worlds simply fall
back to bouncing.

**The data-only alternative, not yet built.** The same boot loader
(`FUN_144608f90`) then iterates the plugin manager's enabled content plugins
and appends each plugin's `<PluginDir>/AssetRegistry.bin` to the registry —
the DLC-plugin path. A `Meteorite/Plugins/<Name>/<Name>.uplugin` with
`EnabledByDefault` + `CanContainContent` (the exe parses both) and a
*minimal* `AssetRegistry.bin` listing just our worlds would make the engine
know them with no code injected at all. Needs: a writer for the UE 5.5
`FAssetRegistryState` serialization (name batch + tag store + asset list),
and a check that a loose `.uplugin` is discovered in this shipping build
(`.uplugin`/`.upluginmanifest` discovery is compiled in; the shipped
`Meteorite/` has no `Plugins` directory). Worth doing when a map should
install as data alone.

### What the map's own world may still need — and how not to test it

With the resolver in place BGL loads on the MapKit's bare world renamed to
`/Game/Levels/Halo1/Solo/BGL/BGL`: Blood Gulch terrain textured and lit,
HUD up, weapon raised, simulation clock running. A shipped mission's
persistent level carries more than that — `BlamWorldSettings`
(`DefaultScenario`, `DefaultGameMode`, `bForceNoPrecomputedLighting`), a
`BlamScenario` actor (`ScenarioName`, insertion points, mission dialogue,
objectives data asset, cutscene titles, data layers) and ten
`BlamGameModePlayerStart`s — and the bare world has a plain `WorldSettings`
and nothing else. Whether any of it matters to play is **not yet known**,
because of two traps that ate most of a night:

- **Synthetic input never reaches the simulation.** The game reads gameplay
  input through Microsoft GameInput (`GameInput.dll` is loaded), which does
  not see `SendInput` keys or mouse motion; Slate menus do, which is why the
  `game_input` tool drives menus fine. `IsInputKeyDown(W)` is true while the
  unit ignores it — on the shipped B40 too. Movement has to be tried by a
  person at the keyboard.
- **`BP_MeteoritePawn_C` is not the unit.** Its location is the same
  constant (19230.9, 1971.8, 13930.8) on B40, on BGL's bare world and on the
  donor world below; the camera sits 189 cm above it. It says nothing about
  where the Blam player is. `FindFirstOf("World")` may also hand back a
  streaming cell's world (time 0); take the controller's world.

For the comparison, `--world` accepts a shipped world too:
`ZenPackage::rename_world` rewrites every name containing the old package
path (2181 in B40's), so a World Partition donor's cells point at packages
that do not exist and never stream, and the `.ubulk` beside the `.umap` is
carried (B40's is 1.1 GB — its textures and HLODs). B40's persistent level
renamed as BGL loads and runs the BGL scenario, with `BlamWorldSettings`, the
`BlamScenario` actor and all ten player starts present — but also B40's
lights, fog volumes and post-process, so Blood Gulch is pitch dark. If a
tester finds the bare world's player locked and the donor's not, the answer
is a synthesized minimal world: the bare package plus those three actor
kinds copied from a shipped level (`native tail` bytes included), which is
zen export surgery `newtag::build` does not do yet. If both play, the bare
world is the product and the donor route can go.

## Several maps: each row needs its own `MapGuid` (2026-09-30)

With two maps registered side by side (one shared `pakchunk996-MJOLNIRREG_P`,
rows `BGL` and `GPH`, both cloned from `B40`), MISSION SELECT's Blood Gulch
started **B40's scenario** under Blood Gulch's world: the objects in play were
B40's Banshees, Ghosts and Shades instead of Blood Gulch's Warthogs, and the
Spartan stood at B40's start (25.6, -18.8, -15.6), outside Blood Gulch's
world bounds and below its terrain. With one cloned row the same duplicate
GUID had gone unnoticed.

Both clones carried the donor row's `MapGuid` (`+64`, B40's is
`56e460734f534340a0ee2f8645c232cd`). `blam_pack::scenario::register` now gives
each row a stable GUID of its own (`map_guid`: two FNV-1a 64 hashes of the
codename), and Blood Gulch starts its own scenario again: Warthogs, the
Spartan on the red base at (42.1, -75.1, 1.7).
`scenario_register <paks> - <out> --registry <MJOLNIRLevelLoader/registry>`
rebuilds the shared container from the installed maps' records without a
re-bake.

Two launch routes that do not work, for the record:

- A bare `SetAndBeginCampaign` from script (above) leaves the simulation with
  no game, for shipped missions too: `(list_count (players))` is 0, the
  Unreal pawn appears at the origin after about 50 s, and further
  `SetAndBeginCampaign` calls are ignored.
- The debug menu's TEST MAPS page (`WBP_TestMapDebugMenu_C:LaunchCampaignMap`)
  starts the map and then crashes about 35 s later in a destructor releasing a
  dangling member (`HaloCampaignEvolved.exe+0x714deba`, read of `-1`), every
  time.

CAMPAIGN > NEW GAME > MISSION SELECT > RALLY POINT > SKULLS > START is the
route that starts the simulation.
