# The Blam console

**Build:** `2026.08.11.1121610.2-Rel-i343-Meteorite-2607-CU4` (Steam)
**Mod:** `mods/MJOLNIRBlamConsole` (Lua) + `native/blam_console` (C)
**Definitions:** `defs/hce/console.json`, from `mjolnir console`
**Date:** 2026-09-02

## Summary

Halo Campaign Evolved's simulation DLL still carries the classic Blam
console: the HS compiler, the engine function table, `help`, `script_doc`,
the `cheat_*` and `debug_*` names. Nothing on the Unreal side feeds it text.
Every Blam command typed at the Unreal console — `game_speed 1`,
`cheat_all_weapons`, `help` — comes back `Command not recognized`, and so
does the same text sent through Kismet's `ExecuteConsoleCommand`. There are
no Exec-flagged UFunctions on the Blam or Meteorite player controllers, no
cheat manager is spawned, and the shipping exe has no `help` or
`DumpConsoleCommands` at all.

This mod is the missing wire. Type a Blam function at the Unreal console and
it runs through the engine's own compile-and-evaluate on the simulation
thread; the result value, or the compiler's error message, comes back to the
UE4SS console. `help` lists everything the engine knows, with signatures.

Two facts about the release build shape what you get:

- **1,270 of the 1,695 functions are live.** The scripting API proper —
  `object_create`, `player_teleport`, `ai_place`, `unit_get_health`,
  `game_save`, `fade_out`, the whole `ai_*` family — works.
- **425 functions are compiled out**, and every `cheat_*` is among them. They
  share one stub evaluator that returns void without looking at its
  arguments. Likewise 217 of the 260 engine globals (`game_speed`,
  `cheat_deathless_player`, `console_pauses_game`) have no storage: they read
  as zero and ignore writes. `help` marks both, and the mod says so when you
  run one.

## Using it

```
help                      counts, and how to narrow
help player_              every name containing "player_", with signatures
ai_enabled                a bare function, no arguments
player_teleport player0 flag_name
blam (unit_get_health (player0))      parenthesised script needs the prefix
blam !(+ 1 2)             run even with no game in progress
blam_status               is the native half installed, and where
```

Answers arrive a simulation tick later and print to the **UE4SS console and
`UE4SS.log`**, not to the Unreal console: by the time the simulation thread
has evaluated the line, the output device Unreal gave the command is gone.
Open the UE4SS GUI console (`Ctrl+O` by default) beside the game, or tail
the log.

A line without parentheses is rewritten the way the engine's own console
does it: `name` becomes `(name)`, `name args` becomes `(name args)`, and
`global value` becomes `(set global value)`. Text is lowercased, so string
arguments are too.

Names that shadow an Unreal command (`open`, `exit`, `quit`, `stat`,
`pause`) are not registered; use `blam <name>` for those.

## Building and installing

The native half is built from source and never committed:

```powershell
.\native\blam_console\build.ps1          # needs VS 2022 with the x64 C++ toolset
.\scripts\install-bridge.ps1 -Mods MJOLNIRBlamConsole
```

The DLL is loaded by the Lua mod through `package.loadlib`, so it needs
nothing from the UE4SS SDK. Definitions come from the simulation DLL itself:

```
mjolnir console --dll "<install>\Meteorite\Binaries\Win64\HaloSimulation_tag_release.dll" \
    --build "<build string>" --lua mods/MJOLNIRBlamConsole/Scripts/defs.lua
```

That reads the function table and the globals array out of the PE image by
walking outward from the `sleep_until` and `game_speed` definitions, checks
every opcode the scripting corpus knows against the same slot, and refuses to
write if any disagree.

## How it works

The shell object the Unreal side creates through the DLL's one export,
`CreateBlamEngineShell`, owns a queue object at `+0x140`. Slot 0 of that
object's vtable is the routine the simulation thread calls once per tick to
drain events Unreal has pushed (lock-free `SLIST`s, event type 3 subtype 2
being "compile and evaluate this text", which nothing on the Unreal side ever
sends). The mod swaps that one vtable pointer for its own routine, which calls
the original and then runs whatever command is waiting. No code is patched;
the swap is a single aligned pointer write behind `VirtualProtect`.

Running on that thread is not optional. `hs_compile_and_evaluate` reaches game
state through thread-local storage, so a call from any other thread sees
nothing.

The inner evaluate routine survives in the release build with what a console
needs, even though `console_printf` itself is gone:

| Piece | Where (RVA, CU4) | Used for |
|---|---:|---|
| `hs_compile_and_evaluate` (inner) | `0x1f8b30` | `(unused, source_name, text, interactive, unused, int* value, int* type)` |
| its `determinize` wrapper | `0x1f8710` | what the shell-event path calls; skipped |
| console output buffer, size | `0x2c2ef18`, `0x2c2ef14` | compile errors are appended here when non-null |
| compile error message, offset | `0x18327f0`, `0x18327f8` | set by the compiler |
| per-type formatters | `0x81f760` | `(short type, int value, char*, int)` |
| value-type names | `0x9aa1c0` | |
| `game_in_progress()` | `0x209a20` | what the shell's own subtype-1 path checks |
| shell object pointer | `0x2c40028` | |
| queue vtable | `0x7b0610` | slot 0 is the drain, `0xe670` |
| function table | `0x81ba20` | 1,695 slots, index = opcode |
| stub evaluator | `0x1b2430` | shared by the 425 compiled-out functions |
| globals array | `0x9a8560` | 260 × 24 bytes: name, type, storage |

The Lua side and the DLL talk through two files next to the DLL
(`request.txt`, `response.txt`) plus `status.txt`, because UE4SS links Lua
statically and exports none of its C API: a `loadlib`ed function can be
called but cannot read arguments. `mjolnir_blam_pump`, called from Lua, moves
text between the files and an in-memory mailbox; the simulation thread never
touches a file.

## After a game update

`mjolnir_blam_open` checks the simulation DLL's PE timestamp before
installing and writes the mismatch to `status.txt` instead of crashing. To
re-derive the RVAs:

1. `mjolnir console` finds the function table, globals and stub evaluator by
   itself; regenerate `defs.lua` and `console.json`.
2. The `init.txt` loader is the anchor for the rest: it is the one function
   referencing the strings `init.txt` and `console_command`, and the call it
   makes per line with `"console_command"` in `rdx` is the wrapper. The
   wrapper's only direct call is the inner evaluate.
3. In the inner evaluate: the `"%s: %.*s\n"` format is guarded by the output
   buffer global; the compiler's error strings are assigned to the error
   message global; the formatter table is indexed by the datum's type.
4. `CreateBlamEngineShell` allocates the shell and stores the queue vtable
   at `[0x28]` (byte `+0x140`); the global it stores the shell in is the
   shell pointer. `game_in_progress` is the check the drain makes for
   subtype-1 text events.
5. Update the `#define`s and `EXPECTED_TIMESTAMP` in
   `native/blam_console/mjolnir_blam_console.c`, rebuild, reinstall.

## Verified

2026-09-02, in A30. `ai_enabled` was typed at the in-game console; `fade_out`,
`fade_in` and the `blam (...)` line went through the bridge's `game_console`,
which lands in the same handlers; the rest through the native mailbox
directly.

| Sent | Answer |
|---|---|
| `ai_enabled` (typed) | `= true (boolean)` |
| `fade_out 0 0 0 30` | `ok`, and the screen went black; `fade_in 0 0 0 30` brought it back |
| `blam (unit_get_health (player0))` | `= 1.000000 (real)` |
| `help object_create` | nine signatures, `(object_create <object_name>)` among them |
| `(+ 1 2)` (at the frontend, forced) | `= 3.000000 (real)` |
| `(unit_get_health (player0))` | `= 1.000000 (real)` |
| `(unit_get_shield (player0))` | `= 1.000000 (real)` |
| `bogus_name_xyz` | `error: this is not a valid function or script name. (at character 1)` |
| `(+ 1` | `error: this left parenthesis is unmatched. (at character 0)` |
| `cheat_all_weapons` | `ok` — and nothing happened; it is a stub |
| `game_speed 0.5`, then `game_speed` | `= 0.000000 (real)` both times; no storage |
| `cheat_deathless_player 1` | `= false (boolean)`; no storage |
