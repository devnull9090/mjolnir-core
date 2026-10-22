# HaloSimulation_tag_release.dll Analysis

**Status:** Active research
**Last verified:** 2026-07-26
**Game build:** `2026.06.26.1097863.1-Rel-i343-Meteorite-2606-CU2`

> **Build label:** this note is stamped CU2; the installed build is CU4, whose simulation DLL is
> a different binary (SHA-256 `C8C14440...3BF7`, `config/hce-build.lock.json`). The RVAs below
> are CU2's; apart from the embedded interface's table (see the update there), they have not been
> re-measured on CU4. See [`build_lock.md`](build_lock.md).

## Artifact

| Property | Value |
|---|---|
| File | `HaloSimulation_tag_release.dll` |
| Size | `14,670,608` bytes |
| SHA-256 | `8EE1A37F6F0BC89241F47946546EDCA798962F81E2D06B386196BC75DE991705` |
| Image base | `0x180000000` |
| Export | `CreateBlamEngineShell` at RVA `0x6980` |

The matching host executable has SHA-256
`0670FAA751E2553940B90DF6BE43D3B0FF59EA87F22155CF3C3FE9D439367F1D`
and MD5 `F6FB844FD0D0A2C48FA8E76DB02DEB9E`.

## Evidence Labels

- **Verified:** reproduced by direct decompilation or an executable inventory.
- **Observed:** present in an artifact, but runtime reachability is not proven.
- **Hypothesis:** a testable interpretation that still needs a discriminating check.

## Shell Factory

**Verified inferred ABI:**

```cpp
bool CreateBlamEngineShell(void* context, void** outShell);
```

The decompiled export:

1. Allocates `0x5A0` bytes with `0x20`-byte alignment.
2. Stores the caller context at object offset `0x10`.
3. Installs interface tables at object offsets `0x0` and `0x140`.
4. Initializes three Windows lock-free singly linked lists.
5. Seeds a reusable 32-entry event pool.
6. Replaces the process-global shell and frees the previous `0x5A0` allocation.
7. Writes the new object to `outShell` and returns `1`.

This is not a zero-argument singleton getter. Any hook or replacement must preserve the two-argument
factory contract and ownership behavior.

## Primary Interface

**Verified:** the table at RVA `0x7B1560` contains nine entries.

| Slot | RVA | Observed behavior |
|---:|---:|---|
| 0 | `0x7230` | Clears shell state and releases the global shell allocation. |
| 1 | `0x7280` | Performs one-time initialization and normalizes a supplied path. |
| 2 | `0x7360` | Large startup path; initializes tag systems and can create a worker thread. |
| 3 | `0x89F0` | Clears queues, frees worker state, waits for the worker, and closes its handle. |
| 4 | `0x6940` | Returns the embedded interface at `this + 0x140`. |
| 5 | `0x8B00` | Builds an auxiliary result/container; exact role is unknown. |
| 6 | `0x9A00` | Allocates and returns an auxiliary callback object. |
| 7 | `0x9A70` | Releases four callback/object references. |
| 8 | `0x6130` | Control Flow Guard placeholder in the recovered table. |

These names describe behavior. They are not recovered source symbols.

## Embedded Output Interface

**Verified:** primary slot 4 returns `this + 0x140`. The table there is at RVA `0x7B1610` and
also contains nine entries.

- Slot 0 drains lock-free queues and dispatches shell events.
- Slots 1, 2, 4, and 5 enqueue typed payloads through the 32-entry pool.
- Slots 6 through 8 are small payload-release thunks.
- Slot 3 is a Control Flow Guard placeholder in the recovered table.

This shape is consistent with the shell output callback layer named by
`FBlamEngineLauncher::RegisterShellOutputHandlerCallbacks`, but that source-level name is still an
**Observed** correlation rather than a recovered RTTI symbol.

**Update 2026-10-21:** on CU4 this table is at RVA `0x7B0610`, and slot 0 is the per-tick drain
at `0xE670` that the simulation thread calls; MJOLNIRBlamConsole swaps that one pointer to run
console commands (`native/blam_console/mjolnir_blam_console.c`, PR #91, mods-v0.5.0). The
lobby's native half finds the table from `CreateBlamEngineShell` and hooks slots 1, 2 and 4
(`native/lobby/mjolnir_lobby.c`, PR #130, mods-v0.12.0). Their callers are exe frames: the exe
queues type-0, object and type-3 commands through them for the network tick in slot 0, and
command 0/0 resets the session flow to state 1.

## UE5 Loader Path

**Verified in the matching host executable:**

1. Function RVA `0x7B26770` constructs the wide basename `HaloSimulation`.
2. It passes that basename to an internal engine module loader and stores the module handle at
   launcher offset `0x1A0`.
3. Function RVA `0x7B229C0` resolves the wide export name `CreateBlamEngineShell`.
4. It calls the export with a constructed callback/context object and launcher offset `0x1C8` as
   the shell out-pointer.
5. It immediately invokes primary interface slot 1 on the returned shell.

The executable contains no contiguous `tag_release` string. The suffix used by the physical DLL is
selected below this recovered launcher layer.

## Why the Suffix Is `tag_release`

**Verified in the matching host executable:** the reflected enumeration
`EBlamEngineBuildConfiguration` declares the members `TagPlay`, `TagProfile`, `TagRelease`, and
`TagTest`. The shipped module is the `TagRelease` configuration of the Blam engine.

In classic Blam terminology a *tag build* consumes individual tag files rather than a compiled cache
map. The shipped data layout matches: `12,328` real Blam tag files are packaged as Unreal assets and
there is no `.map` cache anywhere in the install. See
[`tag_data_pipeline.md`](tag_data_pipeline.md) for the file-level evidence.

## Multiplayer-Relevant Observations

The DLL contains strings and data definitions for CTF, Slayer, Oddball, King of the Hill,
Infection, Juggernaut, Assault, Territories, team options, respawn, loadouts, Megalo, Forge, and
Sandbox. This verifies that those definitions are present; it does not prove the shipping UE5 layer
can select or run each mode.

**Update 2026-10-21:** the project now runs the DLL's Megalo engine. The shipping UE5 flow still
never asks for it, but once the load-map handler is patched to request it (MJOLNIRLevelLoader's
multiplayer switch, which also lifts the map-variant checks the campaign flow cannot satisfy;
`mjolnir live engine --launch-engine 2` makes the handler patch alone, by hand), converted CE
maps run under it with a `.mglo` variant from `mjolnir megalo write`, which writes Slayer and CTF
(PR #106, mods-v0.7.0).

## Reproduction

Use Ghidra 12.1.2 or newer. The current headless launcher does not execute repository Python scripts
unless Ghidra is started through PyGhidra, so the maintained probes are Java scripts.

```powershell
& "C:\tools\ghidra_12.1.2_PUBLIC\support\analyzeHeadless.bat" `
  <project-dir> HaloSimulation `
  -import <path-to-HaloSimulation_tag_release.dll> `
  -scriptPath "C:\haloce\tools\ghidra" `
  -postScript AnalyzeBlamShell.java <output-dir>
```

For the host-side loader path, run `AnalyzeBlamLoader.java` against an analyzed
`HaloCampaignEvolved.exe` project and verify the stored executable hash first.

## Next Checks

1. Find all host call sites for primary shell slots 2 and 3.
2. Recover the startup structure passed to slot 2 and identify the game-variant selector.
3. Correlate that structure with live `/Script/BlamEngine` objects discovered through UE4SS.
4. Trace CTF and team-option string references to their owning functions and data tables.
5. Capture shell output event types while entering, hosting, and joining campaign co-op.
   **Partly done 2026-10-03:** the lobby's hooks on slots 1, 2 and 4 of the embedded interface log
   every command the exe queues on it, with the exe frames that queued it, while a client joins a
   multiplayer match (`native/lobby/mjolnir_lobby.c`).
6. Trace how slot 2's tag initialization resolves an Unreal package path back to a Blam tag, using
   the packaged tag inventory in [`tag_data_pipeline.md`](tag_data_pipeline.md) as the ground truth.
   **Partly answered 2026-09-05:** measured from outside on CU4, the simulation's tag table is
   enumerated from the mounted containers and a brand-new tag package loads by name
   ([`tag_table_and_string_ids.md`](tag_table_and_string_ids.md)). The trace through the DLL is
   still open.
