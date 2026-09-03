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
blam_overlay on|off       the on-screen panel (default on; remembered)
```

Answers arrive a simulation tick later and go to two places: an **on-screen
panel** in the top-left corner, which shows the last few answers for fifteen
seconds, and the **UE4SS console and `UE4SS.log`** (`Ctrl+O` opens the GUI
console), which get everything, including the long `help` listings the panel
truncates. The Unreal console itself shows what the handler knows while its
output device is still alive: the acknowledgement that a line was sent, the
stub and no-storage warnings, and the whole of `help` and `blam_status`,
which are answered synchronously. The answer to a Blam line cannot go there;
see *Why the answer is not in the Unreal console* below.

Every reference the hub publishes, with signatures and which names are
compiled out, is at [mjolnircore.com/docs/console](https://mjolnircore.com/docs/console).

A line without parentheses is rewritten the way the engine's own console
does it: `name` becomes `(name)`, `name args` becomes `(name args)`, and
`global value` becomes `(set global value)`. Text is lowercased, so string
arguments are too.

Names that shadow an Unreal command (`open`, `exit`, `quit`, `stat`,
`pause`) are not registered; use `blam <name>` for those.

## Why the answer is not in the Unreal console

Two facts, both measured on 2026-09-02, rule out the obvious routes.

- **The output device is gone.** Unreal hands the command handler an
  `FOutputDevice`, and writing to it works (`Ar:Log`), but it is a stack
  object that lives for the handler call. The answer arrives a simulation
  tick later.
- **Waiting for it deadlocks.** The simulation's per-tick drain, which is
  where the line is evaluated, only runs while the game thread is free. A
  handler that spun for 400 ms polling the mailbox got nothing; the answer
  appeared the instant the handler returned. So the handler cannot block.
- **The console's scrollback is not reflected.** `Engine.Console` exposes
  four properties to reflection (`ConsoleTargetPlayer`, two default
  textures, `HistoryBuffer`); `Scrollback`, `SBHead` and `SBPos` are plain
  members. Writing them would mean the native half calling the exe's
  `UConsole::OutputText`, one more exe-side signature to break on every
  update, for a line in a console most players open with Tab by accident.
- **`PrintString` is a no-op** in this Shipping build, and the Blueprint HUD
  never fires `ReceiveDrawHUD`, so neither of the cheap on-screen routes
  works either.

What does work is a plain `UMG.UserWidget` holding a `UMG.TextBlock`,
constructed from Lua with `WidgetBlueprintLibrary.Create` and added to the
viewport. It uses engine classes only, so it carries no build-specific
addresses. The panel is hidden (`Collapsed`) between answers rather than
removed: `RemoveFromParent` on a widget of this shape hung the game once in
testing, and the game had to be killed.

## Building and installing

The native half is built from source and never committed:

```powershell
.\native\blam_console\build.ps1          # needs VS 2022 with the x64 C++ toolset
.\scripts\install-bridge.ps1 -Mods MJOLNIRBlamConsole
```

The DLL is loaded by the Lua mod through `package.loadlib`, so it needs
nothing from the UE4SS SDK. CI builds it the same way: every pull request
compiles it on `windows-latest` (the `build-native` job in `ci.yml`, whose
artifact is what a reviewer installs), and the `mods-v*` release workflow
builds it again from the tag and drops it into the mod's zip before the
manifest is hashed and signed. The link uses `/Brepro`, so rebuilding the
same source with the same toolset gives the same bytes as the hash the job
prints.

Definitions come from the simulation DLL itself:

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

What replaces the dead cheats, tried the same day in A30:

| Sent | Answer |
|---|---|
| `skull_enabled bandana` | `error: skull must be "skull_iron", "skull_black_eye", ...` — the compiler lists the whole enum, 54 names before it truncates |
| `skull_enable skull_bandanna true` | `ok`, and the reserve ammo counter read ∞ at once |
| `skull_enabled skull_bandanna` | `= true (boolean)` |
| `game_rate 0.5 0 30` | `ok`, and the game ran in slow motion; `game_rate 1 0 0` restored it |
| `game_tick_get` twice, 7 s apart | ~59 ticks/s, before and during slow motion: the counter runs on real time |

So the skulls are the shipped route to the cheats, and `game_rate` stands in
for the `game_speed` global that has no storage.

The stub and no-storage flags were checked against the running process the
same day, not just the file on disk: `ReadProcessMemory` on the live globals
array found the same 217 null storage pointers, and walking the live function
table found the same 425 evaluators pointing at the stub. Nothing rebinds
either at runtime.

The on-screen panel and the Unreal-console echo, same day, in A30 at 1280×720
and 2560×1440: `ai_enabled`, `blam (unit_get_health (player0))`, `help
player_tele` and `blam_overlay` typed at the console. The panel showed each
answer below the objective text and collapsed fifteen seconds after the last;
`help` and the acknowledgements appeared in the Unreal console's own
scrollback.
