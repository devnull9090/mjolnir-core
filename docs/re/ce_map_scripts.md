# Custom Edition map scripts on CU4

**Build:** CU4 (`HaloSimulation_tag_release.dll`)
**Date:** 2026-11-01 (load fix and device test 2026-11-02)
**Tools:** `tools/ce_scripts/` (`ce_hs.py` decompiles one CE `.map`'s scripts;
`survey.py` runs it over the halomaps mirror; `bucket.py` sorts every function
the corpus calls against `defs/hce/console.json` and the compiler corpus)
**Example:** [`yoyorast_island_v2.decompiled.hsc`](yoyorast_island_v2.decompiled.hsc)

## Status (2026-11-04)

Yoyorast Island V2's buttons, gates and panic shields work on a host, in a
private Megalo Slayer game on PC 1. See [Yoyorast in game](#yoyorast-in-game).
Sanctuary Final's buttons, floor and automatic doors work the same way from a
translated script: see [the translator](#other-maps-the-translator) and
[Sanctuary Final in game](#sanctuary-final-in-game). No fireteam client has seen
either, and nothing has been published.

Corrections to what follows, from reading the sim and from the game:

- **The engine compiles `source files` at load.** A scenario's `scripts` block
  is emptied at load (`0x2b7800` → `0x2d7160`) and rebuilt from the source by
  `0x1f5900`, so the tree `blam_hsc` writes has no effect at run time. The
  product is HSC text the engine accepts.
- **One bad literal costs that script and its dependents**, not every script
  (`0x1f64cf` marks one bit). Only a first-pass error, such as a bad script
  header, loses the rest of its source file.
- **An unregistered `string_id` literal can be made legal.** Script names
  register in the compiler's first pass (`0x1f60fa`), before literals are read:
  `(script static void bluedanube (sleep 0))` lets `"bluedanube"` through.
  Proven on DVT. Names in `object names`, `cutscene flags` and `trigger volumes`
  register themselves: unregistered ones resolve.
- **A name no placement claims kills every script that uses it** (`0x34fb00`:
  "no object exists with this name").
- **YOY has 51 scripts**, not 59, and nothing wakes the two dormant ones, so
  its three absent functions never run.
- **`sleep` counts 30 Hz units at any tick rate**, so `(sleep 1800)` stays
  60 seconds at 60 ticks a second.
- **`h2_machines.py` is on main.**
- `game_multiplayer` and `game_player_count` are void setup commands that take
  an argument, not queries, so neither can gate anything. None is needed.

## Summary

Community CE maps lose all of their scripting when we convert them, and the
cause is our pipeline, not the engine. The bake writes `clear.scripts: true` and
also empties `machines`, `controls`, `device groups`, `object names`,
`trigger volumes` and `cutscene flags` (see `yoyorast_island_v2.level.json`), so
everything a map script refers to is gone before the script could run.

Restoring stubbed HS functions is almost irrelevant here. Across the 759 halomaps
downloads that have scripts, only 8 stubbed functions are called, by 18 maps in
total, and every one of them is a debug or cheat command. Most of what the maps
call is live in CU4:

| Bucket | Functions | Map-uses | What it takes |
|---|---:|---:|---|
| live, and the compiler accepts it | 119 | 7,328 | nothing |
| live, but missing from the compiler's corpus | 36 | 611 | feed `console.json` signatures to `blam_hsc` |
| stubbed in CU4 | 8 | 18 | nothing worth doing (debug and cheat commands) |
| absent from CU4's table (the CE API that Reach dropped) | 99 | 796 | source rewrite at conversion, or a new evaluator |

*Map-uses* means the number of maps that call the function at least once.
**403 of the 759 scripted maps call nothing outside the live set**: once the
conversion carries scripts, their scripts compile as they are.

## Why no baked script ever ran (fixed 2026-11-02)

The device test map (`examples/levels/device_test/`, codename `DVT`) showed that
scripts do run in a Megalo match: startup, dormant and continuous threads, and
the classic `sleep_until (begin … false)` loop. There is no mode gate. But until
2026-11-02 **no script baked by `mjolnir level bake` loaded at all**, including
the bake's own startup stub. That has been true of every level and converted
map ever baked: the source has been dropped since the first stub
(3d1cad1c, 2026-09-03). Two independent causes:

1. **No source files.** `stub_scripts` emptied `source files`. A scenario
   whose `scripts` block is non-empty but whose `source files` block is empty
   loads with `scripts` at 0 (its globals survive). Shipped scenarios always
   carry their source. The bake now keeps it.
2. **An unregistered `string_id` literal.** The stub opened with
   `(submit_incident_with_custom_string_id "game_activity_begin" "mjolnir")`,
   copied from B40, which passes `"b40"`. `mjolnir` is not a registered string
   id, so the load-time check failed that script. The line is gone, and the bake
   now refuses any `string_id` literal missing from `defs/hce/string-ids.json`.
   Script *names* are `string_id`s too, but unregistered names load fine
   (`mj_mark` and the others ran).

How the load works (CU4 sim RVAs):

- `0x1f5900`, the scenario script post-process, type-checks every global
  initialiser and every script root with `0x34c5b0`. A failure is reported
  through `0x1f8110`, but only when source files exist. It is reported as
  `[source line n] script: message` to the console's output capture
  (`0x2c2ef18` buffer, `0x2c2ef14` size), which is unset at load.
- Failed scripts, and whatever depends on them, are removed by `0x34a890`.
- `0x1fc740` (runtime init for a new map) initialises globals and calls
  `0x1fca30`, which spawns a thread (`0x1fd560`) for every startup, dormant
  and continuous script. `hs_update` (`0x1fcb00`, called from the game tick
  `0x206d70`) runs them while `[TLS+0x1f0]+0` is set.
- Thread pools: `[TLS+0x360]` and `[TLS+0x350]`, elements of `0x52c` bytes at
  `+0x50` (`+0x2` script index, `+0xc` wake tick, `+0x20` kind). Scenario
  `+0x3c8` = scripts count, `+0x3d4` = globals count, `+0x3ec` = source files.

`tools/ce_scripts/hs_probe_lobby.patch` is the lobby-DLL probe that found this.
It logs the runtime state and the pools, and installs a capture buffer before a
map loads so the post-process failures are logged. It uses hard-coded CU4 RVAs:
apply it for debugging, never ship it.

**Consequence for already-published maps:** their stub has never run, on the
host or on a joiner. The fade-in
and input handoff they rely on come from elsewhere (the lobby DLL's
`mjolnir_sim_fade_in`, the loader). A rebake makes the stub run for the first
time. Whether HS also runs on fireteam clients is still open, and the stub's
`player0` calls would run there too. Test a rebaked converted map in game, with a
joiner, before releasing it.

## Device test results (DVT, 2026-11-02, host only)

B40's elevator room (BSP 4, insertion point 2), with B40's machines, controls,
device groups and object names kept. `blam.set` cuts `elevator_a_control_2`
out of its device group, and `device_test.hsc` drives the door beside it
(`blamdevicemachine28`) the Yoyorast way: wait for the control's position to
reach 1, open the door, wait 10 s, close it, reset the control.

| Check | Result |
|---|---|
| startup script sets a flag | runs |
| continuous scripts count once a second (short and real globals) | run |
| startup `sleep_until` loop counts | runs |
| switch set to 1 → script counts the press, door opens | yes |
| 10 s later: door closed, switch back at 0 | yes |
| the now-running startup stub: weapon up, HUD on, player moves at match start (host) | yes |
| a player pressing the switch (use button) | **not tested** (needs a person) |
| a fireteam client presses it, and the door moves on both machines | **not tested** (needs PC 2) |

Results were read through `mjolnir_sim_script` lines that fade the screen green
or red. `blam (...)` console lines from Lua hang the game thread, and a Lua
busy-wait in `game_lua` killed the bridge's tick hook.

## Yoyorast Island V2: what its doors and shields actually do

All 59 scripts are in the decompile. There are ten devices, five gates
(`gateflag1/2`, `gatemain`, `gateramp`, `gatepath`) and five "panic" shields
(`panicroom`, `panicbal`, `panichall1/2`, `panichill`). Each one has a
`_control` (the button), a `_machine` (the door or shield), and three scripts:

```
X_check  (continuous): control position = 1 ? teleport X_crusher onto X_open_flag
                                            : teleport X_crusher onto X_closed_flag
X_auto   (continuous): wait for control = 1, wait 1800 ticks (60 s), set control back to 0
X_sync   (continuous): if X_open_biped is dead   -> machine to 1, recreate both bipeds
                       if X_closed_biped is dead -> machine to 0, recreate both bipeds
```

That is the "hacky sync" from the original release, and the reason for it.
CE 1.0's netcode did not replicate device positions, so a button press on the
host never reached the clients' doors. It did replicate vehicles and biped
deaths. So the host drives a vehicle (`X_crusher`) onto one of two bipeds, every
machine sees that biped die, and every machine's own copy of `X_sync` moves
its own door. The bipeds act as a one-bit radio. The panic shields also create
and destroy their machine, so a closed shield has no collision once it opens.

The rest of the hack layer exists only to find out which machine is the host:
`is_server check`, `is_server defined`, `host_check_secondary`, `host_check_3`,
`host_check_4` and `is_server_active` combine four probes (a biped's health,
an effect that kills a biped, the player count, a vehicle in a trigger volume)
into `is_server`. The vehicle spawns and the random teleporter wait for it.
The teleporter's destination pips use the same biped trick
(`sync telepips` → `object_set_permutation`).

On a Reach-lineage simulation, the host owns objects and replicates them, so
most of that layer has no work left to do:

- **Each door becomes one rule**: when the control reaches 1, move the machine
  to 1, wait 60 s, then put both back. That is a control and a machine in one
  device group, or four lines of HS. The crushers, the open and closed bipeds,
  and the flags they sit on are dropped.
- **Host detection is dropped**: `is_server` becomes `true`. This assumes that
  scripts run only on the host. See *Unverified*.
- **Unchanged:** the teleporter (`begin_random` over flags plus `object_teleport`
  of the player's unit), `deadwer` / `niggalyncha` (kill volumes), the vehicle
  respawn teleports, and the panic shields' `object_create` / `object_destroy`.

**Function coverage for YOY.** Every function the map calls is live except three:

| Function | Status | Fix |
|---|---|---|
| `object_destroy_containing`, `object_create_anew_containing` | absent | expand at conversion, one call per matching object name (`optimize_out_1`..`35`) |
| `rasterizer_decals_flush` | absent | drop it |
| `object_set_permutation`, `unit_set_enterable_by_player`, `cinematic_*`, `camera_set`, `render_lights` | live, not in the compiler corpus | corpus gap, see below |

`object_set_permutation` takes `string_id`s on CU4. The converted scenery has to
keep its permutation names (`telepip_*`: `atvbase`, `beachbase`, ...) for the
pips to change.

## What the conversion needs (in order of payoff)

1. **Carry the map's devices and names into the bake.** Append lanes for
   machines, controls, device groups, object names, trigger volumes and
   cutscene flags (the flags are what `object_teleport` targets), with the same
   `Op::KeepLast` semantics the placement lanes already use. Keep the placement
   flags: YOY's panic machines have "not automatically" set because a script
   creates them (`level.rs:1607`). Controls need a CU4 `device_control` donor.
   CU4 ships 20, and two of them are invisible switches that suit a CE button
   drawn by the loader: `invisible_switch/switch_sc` and
   `B40/.../b40-forerunner_switch-door_invis`. Machines can follow the
   `h2_machines.py` recipe (clone B40's elevator family and swap in the model
   and collision). That recipe is on the Halo 2 branch, not on main.
2. **Compile the map's own script instead of the stub.** `stub_scripts`
   (`crates/blam-cli/src/level.rs:1757`) already compiles HSC and rewrites the
   scenario's script section. It needs a variant that compiles the translated CE
   source with `Compiler::with_names` (so object, trigger-volume and flag
   literals resolve to indices) next to the `mjolnir_level_startup` handoff
   script. Drop scripts that only drive cutscene blocks we clear, such as YOY's
   `cutscenes`.
3. **Give the compiler every live function.** `blam_hsc` builds its signatures
   from the campaign's own calls (458 functions), so it rejects functions that
   are live but never called by a campaign scenario. `console.json` has the
   engine's declared parameter and return types for all 1,270 live functions.
   Merging them in covers 36 functions and 611 map-uses at once:
   `cinematic_set_title` 146, `object_set_permutation` 94, `camera_set` 49,
   `sound_looping_start` 41, `cinematic_stop` 40, `cinematic_show_letterbox` 37,
   `object_set_facing` 33, `sound_looping_stop` 29, `unit_get_shield` 26,
   `breakable_surfaces_reset` 21, `unit_set_enterable_by_player` 19, and more.
   This also helps anyone writing HSC for a mod, not only for converted maps.
4. **CE-to-CU4 rewrite table** for functions that were renamed or dropped but
   have a CU4 equivalent:

   | CE (maps) | CU4 |
   |---|---|
   | `object_create_anew_containing` 23, `object_destroy_containing` 12, `object_create_containing` 9 | expand over object names at conversion |
   | `vehicle_test_seat_list` 26 | `vehicle_test_seat_unit_list`; its seat argument is a `unit_seat_mapping`, not CE's seat-label string (CE's `""` means any seat), so the rewrite has to map seat labels |
   | `show_hud` 32, `hud_show_motion_sensor` 8, `hud_show_health` 6, `hud_show_shield` 2, `hud_show_crosshair` 1 | `chud_show`, `chud_show_motion_sensor`, `chud_show_shield`, `chud_show_crosshair` |
   | `object_pvs_set_camera` 14, `object_pvs_set_object` 3, `object_pvs_activate` 2 | `pvs_set_camera`, `pvs_set_object` |
   | `switch_bsp` 58, `structure_bsp_index` 25 | converted maps have one BSP: drop the switch, use the constant `0` |
   | `game_save_totally_unsafe` 33, `rasterizer_decals_flush`, `objects_predict`, `*_predict` | drop |
   | `show_hud_help_text` / `hud_set_help_text` 6 | `hud_show_training_text` / `hud_set_training_text` (untested) |

5. **New evaluators for CE features that CU4 has no function for.** These use
   the restored-cheats recipe ([`restored_cheats.md`](restored_cheats.md)):
   take over a stub's definition, point its name and `evaluate` at our own
   code, and add the signature to the corpus. Ranked by maps:

   | Function | Maps | What maps do with it | Implementation idea |
   |---|---:|---|---|
   | `sv_say` | 154 | server announcements ("The gate was opened!", credits) | route to MJOLNIR's match chat / HUD message line |
   | `unit_get_current_flashlight_state` / `unit_set_desired_flashlight_state` | 51 / 33 | **the flashlight as a use button**: Coldsnap (already on the hub) picks up and hooks vehicles with it | read the unit's flashlight bit; CU4 has `unit_set_integrated_flashlight` and `game_can_use_flashlights` to start from |
   | `object_set_collideable` | 12 | walk-through doors and shields | object flag write |
   | `activate_team_nav_point_*` / `deactivate_*` | 8 + 4 | objective markers | `chud_track_object`, or a HUD waypoint |
   | `ai_*` (CE encounter API: `ai_attach`, `ai_magically_see_players`, `ai_set_respawn`, ...) | 15, 12, 13, ... | AI maps | a separate project; CE encounters do not map onto CU4 squads one to one |

The 8 stubbed functions maps call (`ai_reconnect`, `cls`, `cheat_teleport_to_camera`,
`debug_camera_load/save`, `core_save`, `cheat_all_weapons` (already restored),
`map_name`) are not worth more work. The two stubs that might matter are
`game_multiplayer` and `game_player_count`. CU4 has no other "am I the host"
check, so if HS turns out to run on clients as well (see *Unverified*), these
are the ones to bring back for host gating.

## Corpus numbers

From `survey.py` over `D:\halomaps` (2026-11-01): 4,248 downloads with a
playable `.map` (one parse error); 759 with scripts; 983 with machines; 299
with controls; 149 with device groups. 76 maps script devices, and 54 of those
also have controls (the Yoyorast pattern). The top-rated maps with controls
and device scripts include Base Havoc Beta (5101: 30 machines, 18 controls),
Hugeass (1196), The Rise of Asis (4572), Yoyorast Island V2 (4957), Sanctuary
Final (5241), Precipice (5708: 82 machines, 16 controls), Hotzone (1810), and
H2 Zanzibar Updated (1153).

The "absent" bucket was cleaned of names that are scripts defined by the map
itself. The decompiler reads a call's name from the string table, and the
string table also holds a map's own script names (`red_fb_kill`, `wave1`, ...).
A few hundred maps are protected. Script names with spaces (`is_server check`)
are the protector's renames and do not affect the tree.

## Yoyorast in game

Tested on PC 1 as host, 2026-11-04, with real presses through `game_input`
(`game_input` mouse and keys do reach a player in a match).

| Check | Result |
|---|---|
| prompt on a button, "E ACTIVATE DEVICE" | yes |
| real press on `gateramp_control` | control 1, machine travels 1.856 wu down |
| `gatemain` rises, drawn with the CE mesh | yes |
| `gatemain` raised stops a player; lowered lets one walk through | yes |
| `panichall2` shield appears, blocks, and disappears | yes |
| a control resets 60 s after a press, and its device follows | yes |
| the random teleporter sends a player to a destination | yes |
| `deathbox` kills a player | yes |
| `gatepath` moves | yes; a player blocked by it was **not** walked |
| `gateflag1`/`gateflag2` hatches | **not** walked |
| fireteam client (press, position, shield, teleporter) | **not tested** |
| bots at a raised gate | **not tested**; their pathfinding does not know gates |

How it is built, with no reconvert:

- `tools/ce_scripts/ce_scenario.py` reads the scenario blocks scripts name.
- `tools/level/ce_machines.py` builds a machine tag family per CE tag from
  B40's elevator. The elevator's own position animation is a root slide, so a
  gate only needs new frames (`slide_resource`). CE's collision BSP crosses
  unchanged: the node's rest offset goes in the donor's second node instead.
- `tools/level/add_devices.py` takes the moving parts out of the map's meshes
  by matching triangles to the staged model (slots and lighting stay), builds a
  mesh per machine, and writes the level lanes.
- `tools/level/data/yoy.hsc` is YOY's script by hand: one rule and the original
  60 s reset per device, the random teleporter and `deathbox`.
- `MJOLNIRLevelLoader/Scripts/devices.lua` rides each mesh on its machine.

What the game taught:

- A gate retracted flush with the floor stops a biped dead where CE walks over
  it: moving collision has no step-up. The low end of a vertical slide sinks
  0.15 wu further (`SINK`).
- A panic shield stays a machine, parked 300 wu down at position 0, rather than
  being created and destroyed. A destroyed actor returns to a shared pool, which
  an attached mesh cannot follow. The game stops updating an actor it hides, so
  `Devices.shows` shows a shield's mesh only while its actor is shown and home.
- A device the player cannot see shows its old position in Unreal until it is
  seen. The sim moves it regardless.
- A CE control's yaw points into its wall, so the game's panel, which faces its
  actor's forward, turns 180°.
- Buttons are B40's Forerunner panel with an `activate_device` prompt, which
  draws itself. CE's holo panel has no material in the map's cook, and its four
  custom prompts ("toggle the main gate") have no route.

Not carried yet: the teleporter's direction pips (scenery permutations),
vehicle respawns and the volumes that test a named vehicle (a vehicle comes
through the map variant, which holds no name), race detection, device sounds,
`panicbal`'s 1.1 scale. YOY's original names for two kill volumes are not
carried either.

The clean build also hosts CTF: the devices bind and its scripts run. A
device's rule does not depend on the game type, since HS has no mode gate.
YOY's King, Oddball and Race markers are another matter, and need the work in
[`../game_modes.md`](../game_modes.md).

## Other maps: the translator

`tools/ce_scripts/ce_translate.py` turns a map's own script into HSC, so
`yoy.hsc` is no longer the pattern to copy by hand. It reads the syntax data as
a tree that keeps each literal's type, and writes the script and a report: what
to carry, and everything left out, with why.

| Pass | What it does |
|---|---|
| Normalise | names without spaces, spelled as their blocks spell them (CE kept what the script typed); initialisers folded |
| Host | a flag set by a health probe, or named for the server or host, becomes `true`, and client branches go |
| Sync | a check and sync script pair around a control becomes one rule, with its direction read from the sync script. Any other signal biped becomes a boolean, and a wait straight after its own signal goes |
| Create and destroy | scenery and unanimated machines are parked by position; `*_containing` expands over names |
| Functions | the rename and drop table, seat labels, `ce_tag_paths.json` for tag literals |
| Names | a statement naming something the bake does not carry goes, not the script; a script left with nothing to do goes too |
| Registrars | a static script for each unregistered `string_id` literal |

Over the 759 scripted maps of the mirror (`check_corpus.py`), every map's output
compiles. (One failed on an empty script name, 7063; fixed, and that map rechecked.)
Over the 65 that move a device, 0 are refused. **Compiling is not running:** only
YOY's rules and Sanctuary have been in a game. 69 maps have signals, and only YOY
has the check and sync shape; the rest keep their logic on booleans (Hypothermia's
elevators read correctly, by eye). Yoyorast's translation matches `yoy.hsc`: the
same 10 rules, resets, `gatepath`'s inversion and start, the teleporter and
`deathbox` (`test_ce_translate.py`, with `CE_YOY_MAP` set).

The brief's count of 191 maps needing a tag table was high. 203 distinct tag
literals survive to that pass, in 111 maps, and only 11 are stock paths; the rest
are the maps' own tags, which the game does not have. So the table holds six
entries, four chosen by hand, and none has been heard or seen in game. What a
map loses that way is an effect or a sound, and the report names each one.

Building a map:

```
ce_translate.py <map> <code>.hsc --report report.json --tags <staging>/tags.json
ce_promote.py <map> <staging> --names <report's promote>     # before converting
convert_ce_map.sh <staging> <CODE> <out>
ce_machines.py <map> <staging> <CODE> <machines> --report report.json --auto
add_devices.py <map> <staging> <out> <level> <level> <CODE> <dir> --script <code>.hsc --machines <machines>
mjolnir level bake <dir>/<code>.base.level.json --standalone <CODE> ...
```

`ce_promote.py` has to run first: scenery goes into the BSP's collision at
conversion, where nothing can move it.

## Sanctuary Final in game

Tested on PC 1 as host, 2026-11-04, private Slayer, real presses through
`game_input`. Lightmaps were the map's shipped pages and foliage was off: the
solver had not finished Sanctuary after 35 minutes. Reaching the devices took a
test-only copy with teleports; the clean build was then loaded and its devices
checked, not pressed.

| Check | Result |
|---|---|
| map converts, loads, 69 machines and 2 controls bind | yes |
| translated script runs (the startup script raises the platforms) | yes |
| `pod_switch`: prompt, real press | yes |
| platforms leave after the original's `delay_time` of 20 s | yes: still up 2 s after the press, gone at 23 s |
| deck opens, meshes and collision gone, vehicles on it fall | yes |
| platforms return after `pod_time`, 60 s more | yes: gone at 35 s, back at 93 s, the times read |
| `reset_switch` press reaches its script | yes |
| automatic door: closed at rest, opens at about 5 m, both halves drawn moving | yes |
| walk through the open door; it closes behind | yes |
| a closed door stops a player | **not tested**: it opens first |
| a second `pod_switch` press after the cycle | **not tested** |
| fireteam client | **not tested** |

What is different from CE: the 12 HEV pods are not carried, since a vehicle comes
through the map variant, which holds no name. Stand-ins from the vehicle palette
sit on the deck and fall, but no script loads players into them, and `reset_switch`
has nothing left to reset. Sanctuary's pods were the map's way down from the
station, so the drop is a hole in the floor for now.

Precipice stages and translates but was not converted. Its 16 controls are unnamed
and belong to no device group, so they drive nothing; its boss is custom effects,
sounds and AI.

What these maps taught:

- **Neither map's doors are scripted.** They are door-type machines no script
  names, which open by themselves. `ce_machines.py --auto` carries them.
- **A CE door is several parts moving apart**, each with a BSP, and a clone of
  B40's elevator has one moving root. Each part is a door of its own, placed at
  its node. Sanctuary's doors are 66 machines this way, and every tag family is
  five containers. Two door tags stay still: `882` has rotated nodes and `827`'s
  collision names nodes its render model lacks.
- **Both maps overflow the 16-bit collision tables** (37,784 and 40,304 surfaces
  against 32,767). `split::shed` cuts subtrees out of the tree, leaves open space
  there, and gives their surfaces to two-sided standalone pieces. Players walked
  the deck and a corridor; bullets and bots were not tried in a cut region, and
  bots may find no sectors there. Sanctuary's BSP and scenery came to six
  instances.
- **halo2ue died on both maps**: a lightmap vertex pointer held a heap address
  above the BSP's magic. The fix is branch `fix/bsp-lightmap-pointer-bounds` in
  HalcyonRing, not pushed, so `convert_ce_map.sh`'s default exporter still fails;
  YOY stages byte-identically with it.
- A teleport into solid reads as the Guardians taking the player. Check a flag
  against the staged BSP first.

Turning devices are built (`ce_machines.py`, by `h2_machines.turn_resource`, the
node's frames read as one axis) and tested on frames only. Neither map scripts one
with collision, so no CE turning device has been in a game.

## Clients, from reading the sim

Both questions are answered statically; only the two-PC run is left.

1. **HS on a client.** `0x1fca30` spawns only dormant threads on a client
   (simulation type 4), so startup and continuous scripts run on the host alone.
   `is_server` is the constant `true`. The byte has not been read live on a
   joiner.
2. **A client's press.** `0x193b90` sends simulation event `0x22`; the host's
   `0x591dc0` checks the unit and a distance under 2 wu, then runs the press.
   Device position and power reach clients by entity update (`0x58f950`).

One open risk: `teleport_player` moves a player from the host, and on Halo 2's
lifts a push the host sends a joiner's unit did nothing.

The test: host on PC 1, PC 2 joins YOY. Press a gate button on each, watch both
screens, walk into a raised gate on the client, press a panic shield, and go
through the teleporter on the client.
