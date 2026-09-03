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
frame is black, while shipped missions started through the same menu run.
Adding the cooked-references entries (4) did not change this. Working
hypotheses, cheapest first:

- The world binds to *its* scenario: the B40 world package may reference
  `B40-scenario` (a `BlamScenarioActor` lives in the world); a PG1 scenario
  on B40's world would then never complete the map-load handshake. Check the
  world's zen imports; if so, the fix is a world override whose actor points
  at the new scenario (the MapKit cook), or a runtime repoint before the sim
  binds.
- Something in the scenario's own root fields (`map id`, `campaign id`,
  `map name` string id) is matched against the campaign/progression tables.
- The `TagIoHandler` preopen list for a scenario not in the cooked tables.

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
