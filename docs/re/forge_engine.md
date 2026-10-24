# Forge is still in the simulation (CU4)

**Status:** 2026-10-24. Playable on the host: MJOLNIRLobby offers a FORGE
game type, MJOLNIRLevelLoader starts the map under the sandbox engine, and
MJOLNIRForge binds keys that send the engine's own editor requests (*What
ships*). Verified in game on Blood Gulch: turn into the Monitor and back,
grab, move, drop, push out and delete objects, all through the simulation's
request path. Not yet: placing new objects (converted maps have no sandbox
palette), saving a layout, fireteam clients. The history below covers the
first live run (*Live run, 2026-10-24*, which ended in a hang), the model
fix (*Retest with the fixed model*) and the request path (*The request path
on the host*).
**Binary:** `HaloSimulation_tag_release.dll`, CU4 (md5
`e42f3f342ca816ca3a24aa0deda5581e`, build lock in
[`../build_lock.md`](../build_lock.md)). Every address is an RVA into that
build unless written as a full `0x18…` VA.
**See also:** [megalo_engine.md](megalo_engine.md) (how the host is made to
start a non-campaign engine), [reach_game_engine.md](reach_game_engine.md)
(the vtable layout the sandbox engine shares with Megalo).

Halo Reach's Forge is not a separate program: it is game engine 1, *sandbox*,
which runs a map with a Megalo-style variant plus an editor layer. Players
toggle between their biped and a flying **monitor**; as a monitor they grab,
move, rotate, place and delete map-variant objects, and every change is a
networked request the host applies. All of that code is still in CU4's
simulation, and every tag it names ships. What is missing is the same thing
that was missing for multiplayer: the Unreal host never asks for engine 1, and
it never drew Reach's Forge menus.

## Summary

| Piece | State in CU4 | Status |
|---|---|---|
| Sandbox engine object and vtable (engine 1) | complete, 31 slots differ from Megalo | VERIFIED (vtable diff) |
| Default sandbox variant (`0xf890` bytes) | the variant builder `0x21c4f0` handles type 1 | VERIFIED (code) |
| Per-player editor input loop | intact in sandbox slot 30 (`0x302260`) | VERIFIED (code) |
| Editor request protocol (15 types) | encode `0x4078c0`, decode `0x407c50`, apply `0x305a90` | VERIFIED (code) |
| Become monitor / become biped | `0x300240` → `0x3054f0` | VERIFIED (code) |
| Editor biped tag | `multiplayer_globals` runtime → `objects\characters\monitor\monitor_editor` (bipd) ships | VERIFIED (tag read) |
| Editor gizmo, cursor effect | `objects\ui\editor_gizmo\editor_gizmo` (scen), `multiplayer\sandbox\cursor_impact` (effe) ship | VERIFIED (tag list) |
| Monitor interpolation | `globals\simulation_interpolation\forge_monitor_editor` ships | VERIFIED (tag list) |
| Forge menus (`forge_main`, `forge_object_properties_*`, `forge_tools_*`) | string ids only; Reach GUI screens the UE host never built | VERIFIED (strings, no code) |
| `monitor_editor` creatable | shipped: no. Its model pairs the 4-node `monitor_editor` skeleton with `monitor`'s 5-node animation, collision and physics; those three references stay unresolved at load and object_new returns -1. Fixed by pointing the model's `skeleton model` at `monitor` | VERIFIED (live, 2026-10-24) |
| Become the monitor and back | yes, with the fixed model: `0x300240(engine, p, 1)` swaps in a flying `monitor_editor`, `(…, 0)` restores the Spartan | VERIFIED (live, 2026-10-24) |
| Sandbox engine running a map | yes: BGL under engine 1, editor cursor and grab work with a stand-in editor biped | VERIFIED (live, 2026-10-24) |
| UE rendering of `monitor_editor`, `editor_gizmo` | unknown | UNTESTED |

So "Forge mode" here is the monitor plus the grab/move/place/delete engine,
with no menus. A menu is ours to build, as the multiplayer lobby was.

## The sandbox engine

Table at `0xbd5210`, slot 1 → object `0xbd52d0`, vtable `0x85d740` (114
slots). Its slot 0 (`0x6970`) returns 1. The slots that differ from the
Megalo engine's vtable (`0x85dae8`):

| Slot | Sandbox | Megalo | Role in sandbox |
|---|---|---|---|
| 0 | `0x6970` | `0x47d60` | engine index 1 |
| 4 | `0x3044e0` | `0x400660` | build a player's sim HUD state (calls `0x2fe810`, "is editing") |
| 7 | `0x67550` | `0x3ef910` | "enough teams": always true, so a solo session is enough |
| 8 | `0x300ce0` | `0x3fd550` | new map: runs Megalo's new-map first, then clears the editor state (below), reads the sandbox variant copy into `0x2c33ab0` |
| 9 | `0x300cb0` | `0x3fd710` | dispose |
| 10 | `0x300f60` | `0x3fd740` | new round: runs Megalo's, resets the map variant (`0x32e300`), clears editor state |
| 15, 16 | `0x6130`, `0x301230` | `0x3f0260`, `0x6130` | player leaving: drop out of editor (`0x300240(…, 0)`), release a held object (`0x3070e0`) |
| 19 | `0x303010` | ret | release a held object |
| 21 | `0x301130` | ret | player spawned: if the player's editor flag is set, spawn as the monitor (`0x3054f0`) |
| 23 | `0x301110` | ret | map-variant refresh (`0x32cb70`) |
| 29 | `0x303060` | `0x3fdad0` | per tick: runs Megalo's tick, then map-variant upkeep; on a client (`+0x11 == 4`) moves each held object toward its owner's cursor |
| 30 | `0x302260` | `0x3f09b0` | **per player per tick: the editor's input loop** (below) |
| 32 | `0x303f10` | `0x3ff1b0` | apply traits (editor traits for monitors) |
| 39 | `0x304470` | `0x401c00` | pickup permission |
| 42, 43 | `0x2fe470`, `0x2fe5f0` | `0x4011d0`, `0x401300` | label filters |
| 50 | `0x300a90` | `0x401470` | object deleted |
| 56 | `0x303760` | `0x3f1650` | |
| 62, 64 | `0x3046e0`, `0x304930` | | incidents, object death |
| 66 | `0x304670` | ret | under mode 3 and variant type 1, clear a value for editing players |
| 72 | `0x2feeb0` | ret | on event 2, every editing player releases what it holds |
| 73, 74 | `0x300b80`, `0x300c70` | | round-end and round-timer hooks |
| 77 | `0x6960` | `0x6970` | |
| 79 | `0x304190` | `0x403260` | host migration: re-applies editor mode per player |
| 86-88 | `0x303770`, `0x303920`, `0x303bd0` | | sandbox globals entity build / diff / apply |
| 103 | `0x1e700` | `0x67550` | "need two teams or players": false |
| 113 | `0x3036f0` | `0x3fe520` | runs the Megalo triggers only when `G+0x2c69` is set |

`G` is the game-engine globals, `[TLS+0x38]`. Many sandbox paths also gate on
the game-options mode byte (`[TLS+0x60]+0x10`) being 3 and on
`0x2b5520()` (the live variant's type, `[TLS+0x60]+0x15f0`) being 1.

### Per-player editor state

`0x2fe740(player)` returns `G + 0x17a4 + player*300` (16 players). Slots 8
and 10 reset it:

| Offset | Meaning | Reset value |
|---|---|---|
| `+0x0` | editor flag: 1 = this player wants to be the monitor | 0 |
| `+0x4` | held (grabbed) object | -1 |
| `+0x8` | object under the cursor | -1 |
| `+0xc` | grab distance (`max(this, 5.0)` in the cursor ray) | 5.0 |
| `+0x10..+0x18` | cursor point | 0 |
| `+0xc8..` (`+0x186c`, `+0x1870`) | held-object rotation state | 0, 1.0 |
| `+0xf4` | rotate-mode latch | 0 |

`G+0x2a64..0x2ae4` (128 bytes) are set to all ones and `G+0x2c64` (a count
capped at 31 by the placement path), `G+0x2c68`, `G+0x2c69` cleared at each
new map.

**"Is editing"** `0x2fe810(player)`: the editor flag is 1 **and** the
player's unit (`players[p]+0x28`) is an object of the tag `0x30d090()`
returns. `0x30d090` reads `matg+0x110` (the `multiplayer_globals` reference),
then its runtime block (`+0x10`), then the editor biped reference (`+0xc`).
In CU4 that is `objects\characters\monitor\monitor_editor`.

## The input loop (sandbox slot 30, `0x302260`)

Each tick, for each local player with a unit, after the base per-player
tick and the cursor update (`0x301510`, which ray-casts from the unit's aim
up to the grab distance with `0x2c5960` and records the hit object and
point), slot 30 reads five buttons from the player's control state:

| Request | Gamepad (device type 1): fixed button entry | Other device: abstract action slot (`+0x1a0` table), label written |
|---|---|---|
| toggle editor | entry `0x4d` | slot 0, label `0x28` |
| grab / release | entry `0x52` | slot 5, label `0x2d` |
| (third) | entry `0x53` | slot 6, label `0x2e` |
| rotate / alternate | entry `0x5a` | slot 13, label `0x35` |

The control state is `0x14310e8 + local_user*0x7e0`, an array of 16-byte
button entries (`+0` held ticks, `+2` down, `+3` consumed latch, `+8` owner
label, `+0xc` owner; `0x7f` = unowned). The device type per local user is
`0x182cca4[device]` (via `0x14318c4`). Which Unreal key, if any, feeds
entry `0x4d` / slot 0 is not known; in Reach it is D-pad up.

The toggle fires when the button is down and unconsumed, none of the four
entries at `+0x23..+0x53` is latched, and **either** `0x4b6fb0()` is true
**or** the sandbox variant's byte `+0xf861` is not 1. `0x4b6fb0` jumps
through a table the host fills at `[0xca3480]+0x5b460` and returns 0 when
nothing is registered; `+0xf861` sits where `sandbox_editing_mode`
("All players" / "Only Leader") belongs. The default variant's value there is
not read yet.

It builds a request and hands it to `0x4074c0`.

## The request protocol

A request is 0x40 bytes: payload at `+0`, player index at `+0x38`, type
(u16) at `+0x3c`. `0x4074c0` sends it: a client (`[TLS+0x60]+0x11 == 4`)
posts net message `0x3e`; otherwise it bit-packs the request
(`0x4078c0`) into the simulation's own event queue (`0x500910`, kind
`0xb`). The queue's consumer `0x4cd900` decodes (`0x407c50`), checks the
player, and calls the applier `0x305a90`, which jumps through the table at
`0x30621c` on the type:

| Type | Payload (decoder) | Applier case | What it does |
|---|---|---|---|
| 0 | 4+8+5 bits, 16-byte vector | `0x305b38` → `0x306260` | sets player state `+0x1c..+0x24`, then a placement/spawn call |
| 1 | object | `0x305bb2` → `0x306730` | |
| **2** | 1 bit: wanted state | `0x305bc1` → `0x300240(&sandbox_engine, player, bit)` | **toggle editor**: become the monitor or the biped |
| 3 | object | `0x305be0` → `0x306d30` | grab an object |
| 4 | 1 bit | `0x305c6d` → `0x3070e0` | release the held object |
| 5 | a struct (`0x330230`) | `0x305c7e` → `0x3071e0` | object properties |
| 6 | tag (group `obje`) + 8 + 8 bits | `0x305cc8` | map-variant edit through `0x32cd50` / `0x32cef0`, then reset (`0x32e300`) |
| 7 | none | `0x305d95` → `0x2afa70` | end the round (reset map / end session) |
| 8 | three optional fields | `0x305dac` | delete through `0x5a58a0`, map-variant `0x32e580` |
| 9 | 32 bits | `0x305e55` | map-variant edit via `0x305a30` |
| 10 | 16-byte vector | `0x3060ca` | create from the palette (`0x306550`), drop the held object first |
| 11 | position + quantised forward/up | `0x305f6a` | set an object's transform (checks `0x307390`: editing, may edit) |
| 12 | 3 bits | `0x306024` | |
| 13 | 1 bit | `0x30604b` | |
| 14 | 1 bit | `0x30609c` | sets per-player `+0x38` |

Slot 30 itself uses types 1, 2, 3 and 10 (the call sites at `0x302926`,
`0x302a81`, `0x302b4b`, `0x302d67`, `0x302ee5`).

### Toggling (`0x300240`)

`0x300240(engine, player, want)` returns at once if `0x2fe810` already
equals `want`. For `want = 1` it calls `0x3054f0`: build placement data for
the editor biped (`0x5ee570` with `0x30d090()`), at the unit's position and
facing, create it (`0x5a0fc0`), move the player's control to it, and hide
and detach the old biped. For `want = 0` it does the reverse: find the
player's parked biped (`0x3059a0`, an object whose `+0x1c0` is the player),
restore it at the monitor's position and orientation, and delete the
monitor. Sandbox slot 21 re-enters the monitor at respawn when the flag is
still set.

### Placing (`0x306550`)

`0x306550` refuses once `G+0x2c64` exceeds 31, finds the held object's
map-variant entry (`0x32b600()`, the map variant: 651 entries of `0x4c` at
`+0x14fc`), walks the **scenario's sandbox palette** (scenario tag
`0x10c3558`, block count `+0x214`, elements of `0x14` at `+0x218`, each with
a list of seven-dword entries) to its palette and entry, and creates the
entry's variant through `0x3049e0`. With no palette on the scenario there is
nothing to place (`forge_cannot_place_object`).

## What ships

Tags (from `mjolnir list`):

- `multiplayer\multiplayer_globals` runtime block: **editor biped**
  `objects\characters\monitor\monitor_editor` (bipd), **editor helper**
  `objects\ui\editor_gizmo\editor_gizmo` (scen), multiplayer constants
  **sandbox effect** `multiplayer\sandbox\cursor_impact` (effe),
  **sandbox intro message** `ui\chud\multiplayer_intro\summary_editor` (chdt).
- `objects\characters\monitor\monitor_editor` biped, model, skeleton_model.
- `objects\ui\editor_gizmo\editor_gizmo` scenery, model, collision, physics.
- `globals\simulation_interpolation\forge_monitor_editor`.
- `multiplayer\game_variant_settings\Sandbox\editor_traits*` (11 settings
  definitions: shields, sensors, appearance for the monitor).

Strings in the DLL: the Reach Forge GUI vocabulary (`forge_main`,
`forge_main_menu_palettes`, `forge_object_properties_*` with teleporter,
shape, spawn-time and symmetry fields, `forge_tools_*`,
`forge_object_edit_coords_*`, `in_game_leave_forge`, `confirm_forge_delete_*`,
`pregame_lobby_mapeditor`), the editor globals
`g_editor_maximum_edited_object_speed`, `g_editor_edited_object_spring_constant`,
`g_editor_maximum_rotation_speed`, the map-variant console commands
(`read_map_variant_and_make_current`, `write_current_map_variant`,
`net_load_and_use_map_variant`, `net_build_map_variant`,
`net_verify_map_variant`) and a `sandbox.map` file name.

The debug global `superforge` (Reach's developer Forge, which shows palettes
flagged "hidden#this palette is only visible in superforge") is in the
globals table at `0x9a2020` with type 5 and a null storage pointer: compiled
out, like the rest of the debug globals in this build. The map-variant
console commands have no references (stubs, as in
[`../blam_console.md`](../blam_console.md)).

In Unreal's containers nothing is named for Forge, the monitor or the gizmo
(a grep of every `.utoc`). Whether Unreal draws `monitor_editor` (a sim
object Unreal has no actor class for) is the first thing the live test
answers; an invisible monitor is still a working editor.

## Starting it

The switch is the Megalo one with a different constant: the load-map
handler's `mov r8d, 3` at `0xf6db` becomes `mov r8d, 1`, and
`0x21c4f0(&variant, 1)` builds a default sandbox variant (`0xf890` bytes,
header `0x304`/1). `mjolnir live engine --launch-engine 1` already writes it.

Caution: the shipped runtime's `mjolnir_megalo_on`
(`native/map_registry/mjolnir_map_registry.c`) refuses **all** of its
patches when `0xf6db` holds neither `03` nor `02`, so after the CLI writes
`01` a converted-map launch leaves the variant-file and quit patches
(`0x3f8a8d`, `0xef18`) off. Either launch once normally first (the patches
stay applied on the way back to the menu) and then write `01`, or pass the
CLI's own `--map-variant-gate skip --map-variant-reset skip` and accept that
quitting from the match hangs.

## Live run, 2026-10-24

Solo, PC 1, CU4, Blood Gulch (BGL) hosted with `mjolnir_auto host BGL slayer
private`. All changes were in memory only.

**Getting engine 1.** The sim DLL is loaded only once a game starts, so the
CLI cannot patch it at the first main menu. What worked: host BGL once
normally (the runtime applies its Megalo patches), leave with
`BlamCampaignFlowGameSubsystem:LeaveGame()` (the patches stay applied), run
`mjolnir live engine --launch-engine 1`, then host BGL again. The runtime's
`mjolnir_megalo_on` then refuses (`0xf6db` holds `01`) but the other patches
are already in place. Result, VERIFIED with `mjolnir live engine` and a
memory read:

- engine index 1, sandbox (Forge); game options mode 3; live variant type 1;
- the default sandbox variant's `+0xf861` (editing mode) is 0, so the
  toggle's permission gate passes;
- a normal Spartan spawns, the Megalo HUD is up, `megalo_objects` is empty;
- every Forge tag is loaded in the map: `monitor_editor` (bipd, hlmt, skel),
  `monitor` coll/jmad/frms/phmo, `monitor_beam` (weap), `editor_gizmo`,
  `forge_monitor_editor` (siin), `summary_editor` (chdt).

**The toggle button.** Local user 0 is on device type 1 (the fixed-button
layout), so the toggle is control entry `0x4d` at `0x14310e8` (user 0).
Unreal never writes that entry: it reads all zeros. Writing its down byte
(`+2`) is seen by the input system. Slot 30 consumed it (set the latch at
`+3`) only after the gate jump at `0x30236f` (`jne` on
`0x1802af760() != 1 || 0x4891e0(...) || options[0x1da]`) was NOPed, so one
of those three refuses under the Unreal host. Not narrowed down further. The
request it then queued never reached the applier, and no monitor appeared.

**Calling the sim directly.** A one-shot stub on sandbox vtable slot 113
(the engine calls it every tick through the Megalo tick, so it runs on the
simulation thread with the right TLS) calls any sim function and stores
`rax`. The stub scripts live in the session scratchpad and were not
committed. Findings:

- `0x300240(engine, 0, 1)` and `0x3054f0(0)` run without a crash but return
  failure: **object_new (`0x5a0fc0`) returns -1 for `monitor_editor`**.
  object_new with the same placement code creates an assault rifle and a
  Spartan biped at the same spot, so the failure is specific to that tag.
- Observed, cause not settled: in the loaded `monitor_editor` model (hlmt),
  the collision, animation and physics references (all naming
  `objects\characters\monitor\monitor`) held handle -1 while its skeleton
  reference was resolved, though all four targets are loaded. The Spartan's
  model has all four resolved, but Spartans had already been created, and
  references resolve by name on demand
  ([`../iostore_packaging.md`](../iostore_packaging.md)), so -1 may only mean
  "not used yet". Writing the handles in did not make object_new succeed.
  The Unreal side is intact: the model package imports all four targets and
  every imported export hash matches its target's export.
  The one structural difference from creatable models: the editor model's
  skeleton (`monitor_editor`, 4 nodes) differs from the `monitor` animation,
  collision and physics (built for the 5-node `monitor` skeleton), and
  object_new compares node counts. INFERRED; see *Next steps*.
- Workaround that proved the editor: point `multiplayer_globals` runtime
  **editor biped** (`mulg` root `+0x10c` in memory) at
  `objects\characters\spartans\spartans`. With the editor flag
  (`G+0x17a4`) set, the player's Spartan then counts as the editor
  (`0x2fe810` is true) and **the sim updates the editor cursor each tick**
  (a 5 m ray from the aim, written to `+0x10..+0x18`). VERIFIED.
- **Grab:** `0x306d30(player 0, object)` on a map-variant object (a
  `health_pack_spot`) set the player's held object (`+0x4`). VERIFIED. The
  held object did not move in the seconds checked (the view had not turned
  either). Shortly after that the game **hung** and had to be killed. There
  was no crash report. Likely causes: the scenery held while on the host,
  the NOPed gate, or the editor biped pointed at the Spartan.

`/suicide` with the editor flag set respawned the player as a Spartan, so
slot 21's respawn-as-monitor path either did not run or failed the same
object_new.

## Retest with the fixed model, 2026-10-24

Same machine and map, about an hour later. The other session's test mods
(MJOLNIRLobby 0.15.0, a planted UE4SS mod, `~mods/zz_TestMod_P.pak`) were
installed during this run.

**The fix.** One field in `objects\characters\monitor\monitor_editor` (model):
`skeleton model` from `monitor_editor` (4 nodes) to `monitor` (5 nodes), so
all four references agree with the campaign `monitor` model:

```
mjolnir pack --group model --tag "monitor/monitor_editor" \
  --set 'skeleton model=skel:objects\characters\monitor\monitor' \
  --out-dir <dir> --name pakchunk999-MJOLNIRDEV-forge-monitor_P
```

plus a 339-byte stub `.pak` (copied from an installed one; stubs differ only
in an unused seed). The package still imports `monitor_editor-skeleton_model`,
not `monitor-skeleton_model`. That did not matter, since references resolve
by name. The pack was installed for the run and removed afterwards; it holds
game content and was not committed.

**Results.** All VERIFIED with `mjolnir live` and memory reads:

- The tag table shows `skel objects\characters\monitor\monitor` in the slot
  where `monitor_editor`'s skeleton was, so the override loads.
- **All four model references resolve at load**, before anything is
  created. The never-spawned `editor_gizmo` model's references are resolved
  too (its animation reference is empty in the tag). So the -1 handles of the
  first run were a real load-time failure caused by the mixed skeletons, not
  lazy resolution.
- object_new creates `monitor_editor` (with its `monitor_beam` attached)
  under the Megalo engine, from the stub on the running engine's slot 113.
- Under the sandbox engine (the same two-load launch), the stub's call
  `0x300240(sandbox engine 0xbd52d0, player 0, 1)` turned player 0 into
  `monitor_editor` at the Spartan's position, 0.7 m up. The Spartan stayed
  in the world without a controller, the editor flag was set, and the editor
  cursor updated. Unreal drew the monitor's view: no arms or weapon, with the
  camera at the monitor's height. The monitor itself was not seen from
  outside.
- **It flies.** Forward for 1.5 s, then jump for 1.5 s, moved it from
  (98.66, -149.66, 0.70) to (100.13, -151.52, 2.40).
- `0x300240(…, 0)` put player 0 back in the original Spartan at the
  monitor's x/y (dropped to the ground) and deleted the monitor.
- Leaving the match and quitting were clean. There was no hang and no crash
  report, and the control-gate NOP of the first run was not used.

## The request path on the host, 2026-10-24

Third live run, same map, with the fixed model installed and no NOP:

- **The toggle gate passes.** On the simulation thread `0x4891e0` (is a UI
  holding this user's input) returned 0, `0x2af760` (round state) returned
  1, and the options byte at `+0x1da` read 0. So the first run's refusal was
  transient, not a gate that always shuts under the Unreal host. VERIFIED.
- **One tick on control entry `0x4d` toggles through the request path.**
  The press queued a type-2 request, the applier ran it, and player 0 became
  `monitor_editor`. The entry must be down for exactly one tick: held for six
  ticks (0.1 s) it toggled off and on again, because the latch does not hold
  across ticks. VERIFIED.
- **A held object follows the cursor on the host.** With a shotgun held,
  moving the monitor moved the cursor, and the shotgun tracked it about
  0.25 m behind and settled on it. So slot 29's client-only loop is the
  clients' interpolation, not the only mover. VERIFIED.
- **Release through the grab button (`0x52`)** dropped the shotgun where it
  was held, about 3 m from its spawn. No hang, so the first run's hang
  belongs to that run's NOP or editor-biped stand-in. VERIFIED.

Slot 30's controls map onto request types (target = the held object, else
the one under the cursor):

| Request | Sent when | Applier | Status |
|---|---|---|---|
| 2 toggle | toggle button | `0x300240` | VERIFIED |
| 3 grab | grab button, nothing held, cursor on an object | `0x306d30` | VERIFIED |
| 4 release | grab button while holding | `0x3070e0` | VERIFIED |
| 1 delete | action `0x2c` (a hold on the gamepad) | `0x306730`: clears every player's hold on it, removes it from the map variant (`0x32e580`), deletes it (`0x5a2c30`) | VERIFIED |
| 10 duplicate | default action, target valid and `0x306550` finds its palette entry; payload target + cursor point | `0x3060ca` | VERIFIED refusal without a palette |
| 11 transform reset | action `0x2f` with the held object targeted | `0x305f6a` | not tried |
| 14 mode flip | entry `0x5a` | per-player `+0x38` | not tried |

## What ships

- **CE runtime pack:** `pakchunk990-MJOLNIRFORGEMON_P`, the monitor model
  fix (`tools/level/build_ce_runtime.sh`).
- **`mjolnir_map_registry.dll`:** `mjolnir_forge_on`, the Megalo switch with
  engine 1 in the load-map handler's `mov r8d` (all seven sites as for
  Megalo). Site 0 accepts engines 1, 2 and 3, so switching between Megalo and
  Forge needs no reset first.
- **MJOLNIRLevelLoader:** a pending game type `forge` calls
  `mjolnir_forge_on`, stages no variant, writes `running.txt` with game type
  `forge`, and falls back to Slayer with an older DLL.
- **MJOLNIRLobby:** a FORGE mode on insertion slot 0, offered on every map
  once `MJOLNIRForge\native\mjolnir_forge.dll` and the runtime's monitor fix
  are installed. `mjolnir_auto host <CODE> forge private` starts one.
- **MJOLNIRForge + `native/forge`:** the DLL swaps sandbox vtable slot 113
  (runs every tick, in Forge games only) and, on that tick, builds the
  requests above from Lua's commands: toggle (2), grab or release (3/4),
  delete (1) and duplicate (10, after `0x306550`). It adjusts the grab
  distance (`+0xc`, 1 to 60 m) directly. Commands older than 0.75 s are
  dropped, so a key pressed in the pause menu does not act on resume. Its
  state (editing, held and targeted objects with tag names, distance, the
  last result) goes to `forge_state.txt`, which the mod's panel shows. Keys
  default to B, V, N, Delete, Page Down and Page Up: free in the Blam
  keyboard preset (`BlamInputMapper:GetKeyForAction`; G and C throw
  grenades, Z and X zoom). A key typed into match chat is ignored.

Verified in game 2026-10-24 (BGL, solo): the lobby started FORGE in one load
(engine 1), the panel showed, B became the monitor and back, V dropped and
then grabbed a rifle through request types 4 and 3, Page Up pushed it from
2 to 6 m, N reported the missing palette, Delete removed the rifle. Moving
the monitor works with the game's own controls.

Known limits: host only (a fireteam client reads slot 0 as Slayer);
duplicate needs a sandbox palette, which converted maps lack; the cursor
needs line of sight (it hits walls and the ground first); the monitor flies
through some walls.

## Next steps

1. Place: give converted scenarios a sandbox palette (`blam.map_variant`
   work in [megalo_engine.md](megalo_engine.md)); then duplicate works and a
   palette menu can send type 10 for new objects.
2. Save and load layouts: the map-variant format, codec and the
   simulation's own encoder and decoder are in
   [map_variant_format.md](map_variant_format.md).
3. Fireteam Forge: a game-type slot of its own (or another way for the
   game type to travel), so clients start the sandbox engine too.
4. UI: cooked palette and properties screens (requests 10 and 5), rotation
   (type 11 and the rotate state at `+0xc8`).
