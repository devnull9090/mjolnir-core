# Forge is still in the simulation (CU4)

**Status:** 2026-11-01 (layouts); 2026-10-24 (the editor). Playable on the host: MJOLNIRLobby offers a FORGE
game type, MJOLNIRLevelLoader starts the map under the sandbox engine, and
MJOLNIRForge binds keys that send the engine's own editor requests (*What
ships*). Verified in game on Blood Gulch: turn into the Monitor and back,
grab, move, drop, push out and delete objects, all through the simulation's
request path. Layouts save, load and start games since 2026-11-01 (*Layouts*). Properties and markers since the same day (*Object properties, markers
and the grab crash*). Not yet: fireteam clients, tilting. The history below covers the
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
  fix, and `pakchunk980-MJOLNIRFORGEUI-Windows`, the Forge HUD
  (`WBP_MJOLNIRForge`, [../custom_ui.md](../custom_ui.md))
  (`tools/level/build_ce_runtime.sh`).
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
  delete (1), duplicate (10, after `0x306550`) and place (0, the palette
  entry it keeps selected; see "Palettes" below, which also covers
  `forge_palette.txt`). It adjusts the grab
  distance (`+0xc`, 1 to 60 m) directly. Commands older than 0.75 s are
  dropped, so a key pressed in the pause menu does not act on resume. Its
  state (editing, held and targeted objects with tag names, distance, the
  last result) goes to `forge_state.txt`, which the mod's panel shows. Keys
  default to B, V, N, Delete, Page Down and Page Up: free in the Blam
  keyboard preset (`BlamInputMapper:GetKeyForAction`; G and C throw
  grenades, Z and X zoom). A key typed into match chat is ignored. The DLL
  also reports each object's tag group (the tag table entry's `+0x04`, a
  little-endian four-CC: `weap` reads "paew") and counts its results, so the
  HUD (`Scripts/hud.lua`) can show a category and one note per action.
- **MJOLNIRHud 0.11.5:** no score strip in a FORGE game.

Verified in game 2026-10-24 (BGL, solo): the lobby started FORGE in one load
(engine 1), the panel showed, B became the monitor and back, V dropped and
then grabbed a rifle through request types 4 and 3, Page Up pushed it from
2 to 6 m, N reported the missing palette, Delete removed the rifle. Moving
the monitor works with the game's own controls.

The HUD, verified in game the same day (BGL, solo, test containers installed
by hand): the badge in both modes, the reticle's three tints, the target card
aiming at a shotgun and holding an assault rifle (category, name, the game's
silhouette, key hints, the distance bar), the control bar dimming, and the
notes for the Monitor, a drop and a delete. Screenshots in
[../forge.md](../forge.md).

Known limits: host only (a fireteam client reads slot 0 as Slayer); the
cursor needs line of sight (it hits walls and the ground first); the monitor
flies through some walls.

## Palettes

The scenario's `map variant palettes` block (scenario `+0x214` count,
`+0x218` block handle; at most 16) is what the engine places from. A block
handle `h` is at `bases[h >> 28] + h * 4`, with the bases at `0x2c2ccc0`
(the same arithmetic in `0x32f220`, `0x32cef0`, `0x32ce10`).

| Element | Size | Fields |
|---|---|---|
| palette | 5 dwords | name (string id), flags, entries (count `+0x8`, handle `+0xc`), minimum thorage version |
| entry | 7 dwords | name, variants (count `+0x4`, handle `+0x8`), `+0xc` ?, **maximum allowed `+0x10`**, **price per instance `+0x14`**, minimum thorage version |
| variant | 6 dwords | object reference (tag index at `+0x10`), variant name (`+0x14`) |

A palette entry's **flat index** counts every earlier palette's entries
first (`0x32ce10(_, palette, entry)`); `0x32cef0(mv, flat)` turns it back
into the entry. The map variant keeps a quota per flat index at
`mv + 0xd640 + i * 3` (minimum, maximum, placed) and a budget at `mv + 0x2e0`
with the spent amount at `+0x2e4`.

**`0x3049e0(tag, out)`**, "may one more be created": the tag must have
multiplayer object data (`tag_get(tag) + 0x124 > 0`) and a palette entry
(`0x32cd50`). With `out` it also finds a spot (`0x2cf130`). Then
`maximum allowed > 0 && placed >= maximum` refuses, and so does
`price + spent > budget`. Maximum allowed 0 is no quota.

**Placing, request type 0** (`0x305b40` → `0x306260`): payload palette,
entry and variant as three u32s (4, 8 and 5 bits on the wire, `0x4078c0`),
then the point as three floats at `+0xc`. `0x306260(player, palette, entry,
variant, point*, ...)` returns at once while the player holds an object
(editor state `+4`), checks `0x3049e0` on the entry's variant, creates the
object (`0x32eff0`, `0x32f450`) and grabs it (`0x306d30`). A refusal shows
message `0x680032`, a failed create `0x680031`.

**Before 2026-10-24** MJOLNIR's level bake wrote one palette with an entry
per placed tag and `maximum allowed` = how many the map places, so the quota
was always full and duplicate never worked. The bake now writes a palette per
category (weapons, vehicles, equipment, scenery) listing every kind
`defs/level/palette-map.json` knows, placed or not, with no quota
(`crates/blam-cli/src/level.rs`, `map_variant_palettes`). The campaign-only
pelican, space banshee and seraph are left out (no multiplayer data), and so
is the battle rifle, which no stock canvas carries; a map whose level places
one of them lists it.
For maps baked the old way the Forge DLL lifts those quotas in memory: one
palette whose every entry has a quota above 0 gets 0 in each.

The DLL re-reads the palettes every 60 ticks on the simulation thread and,
when the list changes, `pump` writes `forge_palette.txt`: one line per entry,
`palette`, `entry`, tag group, tag name and whether `0x3049e0` allowed one
more (tab-separated). The state's `selected` indexes that list. The arrow
keys move the selection within a category (a run of one palette and one tag
group, so an old single palette still browses by group) or between
categories; Insert sends type 0 for it at the cursor, releasing a held
object first.

Verified in game 2026-10-24 (BGL, solo):

- The published BGL (old bake): the DLL read 20 entries and lifted their
  quotas; Insert placed an Active Camo and a Warthog from the palette at the
  cursor, held; N duplicated the Warthog.
- BGL rebaked: four palettes with 13 weapons, 6 vehicles, 8 equipment and 5
  scenery entries, all placeable. A Wraith, which BGL never places, came
  from the palette and drew.

## Layouts: save, load, start with one (2026-11-01)

MJOLNIRForge 0.3.0 saves the live map variant to a file and brings it back,
with the simulation's own encoder and decoder. Nothing in CU4 did this: the
five map-variant console commands (`net_build_map_variant` 1517,
`net_verify_map_variant` 1518, `net_load_and_use_map_variant` 1519,
`write_current_map_variant` 1520, `read_map_variant_and_make_current` 1521)
are stubs in CU4, and in MCC's `haloreach.dll` too (its shared stub
`0x86cbc`); Halo 3 does not have them. So there was no body to copy.

| Piece | RVA | Notes |
|---|---|---|
| live map variant | `0x32b600()` | `([TLS+0x250] + 0x30b) & ~3`, only in options mode 3; `0xd9c0` bytes |
| encode / decode | `0x32cfb0(mv, bits)` / `0x32d810(mv, bits)` → bool | |
| bitstream setup | `0x5323a0` | the session normaliser: encodes into a `0x7000`-byte stack buffer and decodes back; the template for both directions |
| reset | `0x32baf0(mv, map id)` | version 32 (`+0x2b0`), map GUID (`+0x2b8`, 16 bytes) zero, bounds empty (±FLT_MAX) |
| build from the scenario | `0x32cc00(mv)` | `0x32baf0(mv, scnr+0x10)`, then the placements (`0x32e0c0`) |
| make a given variant current | `0x32bdb0(dst, src, 0)` | what new-map does with a session-supplied variant; takes the map id from the GUID (`0x32bd40` → `0x32b1a0`), so -1 for a zero GUID |
| delete every variant object | `0x32f710()` | objects of mask `0x5ce` whose `+0x1c` (variant index) is set |
| create every entry's object | `0x32f6a0(mv)` | entries with flag bit 0 and no object yet (`+0x2c` = -1); round reset and host migration |
| resend an entry | `0x4d1b70(entry, 4)` | host migration does it for all 651 after recreating |

**The bitstream** (`0x5323a0`'s stack struct, 0x48 bytes): `+0` begin, `+8`
end, `+0x10` size, `+0x14` 1, `+0x18` mode (1 write, 3 read), `+0x20` bits
(write: already in the buffer; read: in the accumulator), `+0x28` 64-bit
accumulator filled from the top, `+0x30` bits in it (write), `+0x38` cursor.
After encoding, the accumulator is flushed big-endian; the size is
`(+0x20 + +0x30 + 7) / 8` bytes. A reader starts with the first eight bytes
in the accumulator and `+0x20` = 64.

**New-map** (`0x2aca30`, mode 3): when the game options' map variant
(`([TLS+0x60] + 0x111fb) & ~3`) has `+0x2e9`, `+0x2e0` or `+0x2ea` set, it is
copied in with `0x32bdb0`; otherwise the live variant is built from the
scenario at `0x2ace53` (`call 0x32cc00`). The round reset then creates the
objects (`0x2ad80d`, `call 0x32f6a0`).

**Version 32 and the map GUID.** The decoder reads the GUID only from
version 32 on and fails when it is all zero (`0x32db50`); below 32 it derives
it from the map id (`0x32add0`, else zero) and keeps the version. CE builds
every variant at version 32 with a zero GUID, so the engine's own encoder
writes a file its decoder refuses (VERIFIED: the first save of BGL decoded
in our codec, 125 objects, and the sim refused it). A copy at version 31
round-trips: the GUID is not written and comes back zero. VERIFIED.

**Map ids.** `scnr+0x10` is the map id `0x32cc00` writes. `0x32bdb0` resets
the target with the id it derives from the GUID, -1 here, so after each copy
the DLL writes the scenario's id back, and it saves that id. A file is
refused only when both ids are real (> 0) and differ: converted maps carry 0
or -1, and the file's name ties it to its map anyway.

**How the DLL does it** (`native/forge/mjolnir_forge.c`, "Layouts"):

- **Save** (F5, sandbox slot-113 tick): copy the live variant, set version 31
  when the GUID is zero, encode, decode the result into scratch as a check,
  then write `layouts\<CODE>.mvar` (`_blf` 1.2, `mvar` 31.1 with a zero hash,
  `_eof` 1.1). `<CODE>` comes from MJOLNIRLevelLoader's `running.txt`. The
  previous file moves to `layouts\history\<CODE>-<time>.mvar`.
- **Load** (F6): decode the file into scratch, then the host-migration
  sequence: `0x32f710`, `0x32bdb0`, `0x32f6a0`, `0x4d1b70` per entry,
  `0x32e300`. A held object is released through request 4 first and the
  load waits a tick.
  With no `<CODE>.mvar`, the newest `<CODE>-*.mvar` in history moves back
  first, which undoes a revert.
- **Revert** (F2, a second press 0.3 to 4 s after the first, with no other
  command between them): the same with `0x32cc00` for the copy; the file moves
  to history.
- **At game start, any engine:** the `call` at `0x2ace53` is pointed (rel32)
  at a 12-byte `mov rax, imm64; jmp rax` stub in a page allocated within 2 GB
  of the DLL, which calls `layout_new_map`: build from the scenario, then
  `0x32bdb0` the map's saved layout over it. The round reset creates its
  objects, so Megalo's per-round setup (slot 10) sees them. The patch is
  checked (opcode `E8`, target `0x32cc00`) and made once.

Verified 2026-11-01 (BGL, solo, Steam CU4):

- Forge: placed an energy sword, saved (126 objects, 2,707 bytes); placed
  two more; F6 removed the two (126 again); F2 removed the saved one too
  ("the map's own layout"). Added a Wraith, saved (127).
  `mvar_summary` reads every save: version 31, bounds x 0.91..136.90,
  y -195.22..-40.06, z -6.28..55.00, no object outside them.
- Slayer on BGL, a fresh game: `layout=BGL: saved layout, 127 objects`;
  `mjolnir live objects` shows the Wraith at (45.57, -95.49, 1.65), where the
  file has it (45.60, -95.49, 1.62), and the sword beside it. BGL ships no
  Wraith, so it came from the layout.

## Object properties, markers and the grab crash (2026-11-01)

### Properties (request 5)

A map-variant entry carries the object's Forge properties at `+0x30`, 0x1c
bytes, the layout the property codec reads (`0x330230`) and writes
(`0x32ff40`):

| Offset | Field | Bits on the wire |
|---|---|---|
| `+0x00..+0x0f` | shape dimensions (floats) | 11 each, by shape |
| `+0x10` | shape type | 2 |
| `+0x11` | spawn order (s8) | 8 |
| `+0x12` | respawn time, s | 8 |
| `+0x13` | multiplayer object type | 5 |
| `+0x14` | label (i16, -1 none) | 1 + 8 |
| `+0x16` | flags | 8 |
| `+0x17` | team: 0 red, 1 blue, ... 8 neutral | 4 |
| `+0x18`, `+0x19` | type extras: spare clips; teleporter channel, passability | 8; 5, 5 |
| `+0x1a` | colour (-1 none) | 1 + 3 |

A weapon placed from BGL's palette reads
`…00 00 1e 01 ffff 0c 08 02 00 ff 00`: order 0, respawn 30, type 1, no
label, flags `0c`, neutral, 2 spare clips.

The labels' names live in the variant: label `i` is the NUL-terminated
string at `mv + 0x2f4 + u16[mv + 0x12f8 + 2i]`, count at `mv + 0x14f8`. On
BGL: `ce_warthog_2`, ..., `ctf_spawn_red`, `ctf_spawn_none`,
`ctf_spawn_blue`, `ctf_flag_return` (17), `ce_health_pack`.
`mvar_summary` now prints them.

**Request 5 through the event queue loses the block.** Sent with respawn 45,
the entry came back with 45 in its flags byte and the fields before it zero.
The object travels outside the bitstream (`0x407860` lifts payload `+0` for
types 1, 3, 4, 5, 10 and 11; the consumer `0x4cd900` puts it back), and both
codecs read as mirrors, so where the bits slip was not found. On the host
the DLL calls the applier itself, `0x3071e0(player handle, object, block)`,
which is what the consumer calls after decoding: the permission check
(`0x307390`), the write into the entry and the resend (`0x32fcd0`,
`0x32e870`). The first argument is the player's **handle**
(`salt << 16 | index`): the check compares it with the object's holder, so
an index alone refuses held objects. VERIFIED: respawn 45, order 1, team
blue and a label all landed, and survive a save.

### Physics modes (CU4 native code, 2026-11-02)

The per-object physics choice is stored in the **same saved properties byte**
at `properties + 0x16` (`entry + 0x46`). It is separate from the tag's
*phased physics in forge* flag described below. The mode resolver
`0x2fe9f0(object)` reads the saved byte, then asks `0x2fe8e0(object)` which
player currently holds the object:

| Saved flags, masked with `0xc0` | Mode | Native state while held | Native state after release |
|---|---|---|---|
| `0x00` | Normal | 1 | 0 |
| `0x40` | Fixed | 1 | 3 |
| `0x80` or `0xc0` | Phased | 2 | 3 |

Bit 7 takes precedence over bit 6. Preserve the lower six bits when changing
the mode. The Normal row also has a native temporary-held-state exception:
`0x2fec80(object)` can return state 1 for an unheld object whose runtime
multiplayer flag `+0x12 & 0x2000` is set. This is not a saved physics mode.

The tag flag does seed the initial choice: `0x32eff0` copies tag multiplayer
flags bit 1 into **both** saved bits 6 and 7 when creating an entry. Because
the mod sets that tag flag on structural palette objects, a newly inserted
piece commonly starts with flags `0xcc` (the other default bits are `0x0c`).
That is already Phased; the tag flag is not merely a clearance bypass.

`0x2feb20(object, state)` applies the resolved state to the live object's
flags at `+0xdc`. Considering just mask `0x600040`, state 0 writes zero,
state 1 writes `0x200000`, state 2 writes `0x600000`, and state 3 writes
`0x40`. State 3 also sets `+0xdc & 0x400`. The function rebuilds an existing
physics component through `0x2df480(object, 0)` or creates one through
`0x2df810(object)` when needed. This is a native physical state change;
Fixed does not require a mod to restore the object's position every tick.
The Havok body builder `0x249ed0` confirms the effect: live `+0xdc` bit 6
forces body motion type 5 (fixed), overriding the tag's normal motion choice.

The guard is important: the object's model reference must resolve
(`object` tag root `+0x60` is its handle), and that model must reference a
physics model (`hlmt + 0x2c`, the handle in the reference starting at `+0x20`).
If either handle is `-1`, the applier makes no physical change. The property
refresh enumerates native type mask `0x5ce`: vehicle, weapon, equipment,
scenery, machine, control and crate. Marker scenery without a physics model
can retain the saved bits but does not acquire a rigid body from this setting.
The mod's existing carry-and-recreate path remains necessary for such markers.

**Apply, release and persistence.** The host's existing property applier
`0x3071e0(player handle, object, properties)` copies the complete property
block into the entry and calls `0x32fcd0`, which refreshes matching live
objects through `0x32f940`. That refresh starts with
`0x2fe9f0` → `0x2feb20`. It then reapplies the entry's transform through
`0x32e870` and marks the entry changed with `0x4d1b70(entry, 1)`. Use this
path rather than writing only the live `+0xdc` flags. The request-5 event
queue corruption described above remains a reason to keep the mod's current
host-only property-edit boundary.

The native entry replication receiver `0x579350` copies all `0x1c` property
bytes from the update and calls `0x32fcd0`. `0x4d1b70` marks the corresponding
entry property bit in its 21-entry replication group. This verifies the
replication path in code; it is not a substitute for a two-PC live test.

Grabbing (`0x306890`) assigns the holder and applies the resolved held state;
it does not clear either saved physics bit. Releasing
(`0x3070e0` → `0x306d80`) clears the holder, records the current transform
through `0x305250`, and resolves/applies the released state. A set `0x80`
forces the fixed-release branch, which also ORs `0x40` into the saved byte;
thus `0x80` becoming `0xc0` on release is expected. A pre-existing `0x40`
survives an ordinary release even when the request's extra boolean is zero.
That boolean can request a fixed release independently; it is not the saved
three-way mode itself.

The property writer `0x32ff40` and reader `0x330230` serialize all eight flag
bits. Object recreation (`0x32f450`) calls `0x32f940`, restoring the resolved
mode from the loaded entry. The mod's marker carry/duplicate code copies the
entire `0x1c` property block, so those operations preserve the bits too.

The pack collision builder currently authors `rigid bodies[0].motion type`
as `fixed`; that asset setting alone is not evidence that the native grab,
release and render paths retained a stationary object. For a reported falling
object, inspect its actual `+0x1c` entry, saved `+0x46`, holder and live
`+0xdc` together. In particular, a saved byte of `0xcc` is already Phased.
After release its resolved state must be 3 and `+0xdc & 0x600040` must be
`0x40`; changing only its UI label to Fixed cannot explain or repair a
disagreement. These mode findings are verified from the CU4 native code.
The new F3 control and local freeze/save/reload checks are recorded in
[forge_pack_validation.md](../forge_pack_validation.md#forge-placement-controls-and-hud-recovery).
Multiplayer verification remains separate.

### The grab crash

Placing a flag stand from the palette crashed the simulation thread. UE4SS
then sat in its crash dialog, so the game looked hung. That is likely also
the hang of the first live run (*Live run, 2026-10-24*), which held a health
pack. A stack walk of the stuck thread (dbghelp `StackWalk64`, no symbols)
showed it in the grab: the consumer (`0x4cda8e`), the applier (`0x305bad`),
placing (`0x3063c0`), then the grab (`0x306d71` → `0x306890`), faulting at
`0x306b6b`. The grab drags an object through the chain from object `+0xcc`:
the data array `*0x10ccc90` (0xc0-byte elements), `+0x30`, then `+0x40`,
which it reads from `+0x170`. For CE's marker scenery (flag stands, spawn
points, health packs, teleporters) the last pointer is NULL. Placing grabs
what it creates (`0x306260` → `0x306d30`), so placing any of them crashed,
and so would V on one.

Before that, placing them did nothing at all. `0x3049e0(tag, point)` also
looks for room at the point (`0x2cf130`, sized by the tag's bounding radius)
unless the tag's multiplayer object flags (`+0x1a`) have bit 1, *phased
physics in forge*. Reach set that on its Forge scenery. CE's tags lack it,
and scenery resting on the ground never has room.

What the DLL does:

- It sets *phased physics in forge* in memory on every palette tag that is
  not a weapon, vehicle or equipment (5 on BGL). It finds the tag's root from
  the tag table entry `+0x1c` and the multiplayer block at root `+0x124`.
- It never lets the editor grab an object whose drag chain ends at NULL.
  Such objects are placed the way `0x306260` places, without the grab:
  `0x32eff0(mv, palette, entry, variant, point, forward, up)` → entry,
  `0x32f450(mv, entry, 1)` → object, `0x32e3b0(mv, flat)`,
  `0x4d1b70(entry, 4)`.
- V on such an object "carries" it: it keeps the palette entry (the flat
  index at entry `+0x2`, back to palette and entry by walking the palettes),
  the variant (`+0x2e`), the facing (forward at `+0x14`) and the properties,
  then deletes the object (request 1). V again makes it at the cursor with
  those properties. `,` and `.` turn it 22.5°.
- The cursor ray never lands on a marker, since they have no collision. So
  when it lands on no object, the DLL aims at the map-variant object without
  a drag chain nearest the line from the player's unit through the cursor
  point: within 1 m, plus 2% of the distance. Origins come from
  `0x5a6780`; the objects come from the object array, whose `+0x44` is the
  slots in use. Each object knows its variant entry at `+0x1c`.

Verified 2026-11-01 (BGL, solo):

- A flag stand placed with no crash, aimed at, set red and labelled
  `ctf_flag_return` (K, L ×17), then carried, turned 90° and put down: the
  new object had the same team and label and a facing of -90°.
- The layout was saved (129 objects; the stand is team 0, label 17,
  yaw -90°), and BGL was hosted as CTF. `mjolnir live objects` showed the red
  flag at (34.59, -78.27), on the Forge stand at (34.87, -78.27), as well as
  the map's own two.

### Turning a held object

Request 11 (exact transform) acts only on the held object, so it cannot move
a marker. Its applier (`0x305f6a`) writes the editor's hold transform from
the payload (`+4` onward):

| Editor state | Field |
|---|---|
| `+0x3c` | scale |
| `+0x40`, `+0x4c`, `+0x58` | forward, left, up |
| `+0x64` | position (recomputed from the cursor each tick) |
| `+0x70..+0x93` | the same three axes again: the snap's reference |

The snap is `+0xc8`, which request 12 sets. It is an index into
`0x85dad0` = {0, 90, 45, 30, 15, 5} degrees (0 = free); the per-tick hold
code (around `0x2ffe04`) snaps the hold axes to it about `+0x70`. Request 14
flips `+0x38`, which picks the order the snap composes in. Slot 30 sends it
when control entry `0x5a` is pressed (latch `+0xf4`). Request 13 sets
`G+0x2c69`, which gates Megalo's triggers in a sandbox game (slot 113).

The DLL turns a held object by rotating the three axes about Z on the
simulation thread, copying them to `+0x70`, and setting the snap to 0.
VERIFIED: a held energy sword went from 0° to -90° after four 22.5° turns
(`mjolnir live objects`).

### Native snapping and a placement grid (CU4, 2026-11-02)

These findings come from read-only disassembly/decompilation of the CU4
`HaloSimulation_tag_release.dll`, MD5
`e42f3f342ca816ca3a24aa0deda5581e`. RVAs below are relative to that DLL.
Local research output is under the ignored `.dream-loop/forge-controls/`
and `.dream-loop/forge-physics/` directories. This section records the
native contract behind the implemented F4 placement grid. Bounded local
validation is recorded separately in
[forge_pack_validation.md](../forge_pack_validation.md#forge-placement-controls-and-hud-recovery).

**Rotation has a native snap setting.** Per-player editor state is returned
by `0x2fe740(player)`, at `G + 0x17a4 + player * 300` where
`G = [TLS + 0x38]`. Its `+0xc8` integer selects the six-entry degree table
at `0x85dad0`: `{0, 90, 45, 30, 15, 5}`. Zero means free rotation.
`0x307400(axes, step_radians)` extracts Euler angles, rounds all three to
the selected increment, and rebuilds an orthonormal basis. This is not
limited to the yaw-only controls in the mod.

The ordinary `0x40`-byte Forge request has its payload at `+0`, player
index at `+0x38` and 16-bit type at `+0x3c`; send through `0x4074c0` on
the simulation thread. Relevant requests are:

| Request | Payload and application | Meaning |
|---|---|---|
| 12 | One byte, index 0 through 5. Applier `0x306024` clears state `+0x70..+0x93` and writes the index to `+0xc8`. | Rotation snap increment. The wire codec uses three bits, but the applier does not reject indices 6 or 7; callers must do so. |
| 14 | One byte, 0 or 1. Applier `0x30609c` changes state `+0x38` while editing. | Rotation composition mode: the two modes change matrix multiplication order around the reference basis. It is not a positional grid. |
| 13 | One-byte boolean. Sets `G + 0x2c69` while editing and marks its native state dirty. | Enables Megalo trigger execution in Forge; unrelated to snapping. |
| 11 | Object datum at `+0`; scale at `+4`; forward, left and up at `+8`, `+0x14`, `+0x20`; translation at `+0x2c`. | Sets the held target transform, after validating the holder and clamping translation to map-variant bounds. It does not immediately teleport the object. |

Request 11's applier is `0x305f6a`. Its codec's quantized position and
orientation are network representations, not an authoring grid. Slot 30
sends request 14 for native control entry `0x5a`, using state `+0xf4` as
the input latch. The inspected native input, request and carry paths contain
no corresponding positional-grid selector or position-rounding operation.
This is a scoped negative finding, not proof that no other game mode has one.

The hold update at `0x2ff820` integrates monitor movement, clamps the target
with `0x1a4940(mv + 0x2c8, point, out)`, applies distance/contact constraints,
snaps the orientation, and sends the resulting matrix to the Havok component
through `0x241ea0`. `0x2feff0` handles analog rotation and respects the
composition mode. The translation at editor state `+0x64` originates from
the held Havok body's matrix (`0x306890` reads body `+0x1a0..+0x1a8`).
It is **not necessarily the authored model origin**. Quantizing that target
would introduce an offset for pieces whose body center differs from their
bottom-center placement origin.

The earlier comma/period implementation described above rotates by 22.5
degrees, copies the axes to the reference basis, and forces snap index zero.
Exposing request 12 while retaining that reset would disable the chosen
setting as soon as those keys were used. Rotation commands must preserve
the selected mode; marker carry/recreate and new-placement yaw also need
an explicit policy because they do not pass through the native held-body
snapper. Pack `snap_m` metadata alone does not enable any engine behavior.

**A dependable position grid applies at placement/drop.** Native release
`0x3070e0(player, object, flag)` calls `0x306d80`, clears the held datum,
records the object's actual pose and restores its resolved physics mode.
It does not move the body to editor state `+0x64` before releasing it.
Sending request 11 and release in the same tick therefore cannot guarantee
an exact grid result.

For new placement and marker recreation, quantize the authored origin before
the existing creation path. For an existing rigid body, wait until a queued
native release has completed, then move its actual origin on a later
simulation tick. A bounded pending operation should retain scene identity,
the full salted object datum and map-variant entry identity; cancel on scene
change, deletion, re-grab, identity mismatch or timeout. Confirm host/Forge
state and that no player still holds the object. Do not force a different
saved physics mode as a side effect of snapping.

One world unit is 3.048 metres. For a positive finite grid size in metres,
round each world-aligned origin coordinate with
`roundf(origin_wu * 3.048f / grid_m) * grid_m / 3.048f`.
Use a consistent rule for negative coordinates and bypass rounding when the
grid is off. Reject non-finite inputs and candidates outside the current
map-variant bounds. The native setter's much larger coordinate limit is
not a replacement for map bounds.

The relevant native transform functions are:

| RVA | Verified callable contract and behavior |
|---|---|
| `0x5a6780` | `float *get_origin(uint32_t object, float out[3])`. Produces world-space origin, resolving parenting when present. |
| `0x5a6ae0` | `void get_axes(uint32_t object, float forward[3], float up[3])`. Either output may be NULL. The implementation indexes by the datum's low 16 bits and does not validate its salt. |
| `0x5ec880` | `void notify_transform(uint32_t object, float *position, float *forward, float *up)`. Calls type-specific callbacks with mutable pose buffers; native callers invoke it before setting the transform. |
| `0x59f600` | Byte/boolean result: `set_transform(object, position, forward, up, location_hint, update_spatial, sync_physics, flag8, flag9)`. Native map-variant and teleporter callers use `NULL, 1, 1, 0, 0` for the last five arguments. |
| `0x59f470` | `void mark_modified(uint32_t object)`. Sets the object-slot modified flag and propagates to parents. |
| `0x305250` | `void capture_pose(char reset_motion, uint32_t object)`. Copies actual origin/axes into the object's variant entry, marks transform dirty, and re-applies the pose through the setter. See the failure caveat below. |
| `0x32e870` | Applies a map-variant entry's transform to its object. Its data flow is variant to object, not capture. |
| `0x32ed40` | `void client_variant_sync(void *mv, uint32_t object)`. Runs only for game-options `+0x11 == 4`, applying a fixed/phased entry to a client object. It is not a host capture helper and has no boolean result. |

The object's parent datum is at object data `+0x14`. A world-origin grid
operation should require it to equal `0xffffffff`; otherwise the getter's
world-space result and setter's parent-relative storage need an explicit
conversion. For an unparented object, origin is `+0x44..+0x4c`, forward is
`+0x50..+0x58`, and up is `+0x5c..+0x64`. Read them through the getters and
validate the full datum before invoking any of these index-based functions.

`0x59f600` updates the native pose, object/network dirty flags, physics
through `0x2e13f0`, and spatial registration through `0x5b0070`. Its normal
unparented coordinate range is +/-32768 world units. An invalid position
returns false, but other work, including orientation changes, can still
occur; validate the complete pose first, including the buffers after the
mutable type callback. This setter performs **no collision-penetration
test**. A Normal object may subsequently settle away from the grid under
physics, whereas Fixed/Phased retain their existing native behavior.

The native convenience wrappers `0x59f8c0` and `0x59f9d0` call the type
callback, setter and modified notification, but can delete the object when
the setter fails. A grid implementation can instead call the explicit
sequence and inspect the setter's result. `0x305250(0, object)`, used by
native release, is the correct host pose-capture helper: it writes actual
origin to entry `+0x8`, forward/up to `+0x14`/`+0x20`, and calls
`0x4d1b70(entry, 2)` for a **transform** update. Its nonzero first argument
also overwrites velocities using a gravity step, so use zero when preserving
motion semantics. However, capture then re-applies the pose with setter
flags `NULL, 1, 1, 1, 0` and also has the native delete-on-failure branch.
It is not a pure copy. If the integration must exclude that branch entirely,
copy validated post-setter getter results into those three entry fields and
call `0x4d1b70(entry, 2)` explicitly. Mask 4 is creation, not transform.

`0x2cf130` is a free-placement search based on the tag's bounding sphere;
it is not an exact mesh penetration check and can reject valid flush modular
placements. `0x2cedb0` also searches alternative free positions rather than
validating only the requested coordinate. Neither establishes exact grid
collision safety. A release grid should use the engine transform path,
preserve collision/physics mode, and be described as placement snapping,
not continuous collision-constrained movement while held.

The implementation uses the explicit callback/setter/modified sequence,
then reads back the accepted pose and copies its three transform fields into
the variant entry with dirty bit 2. It does not call the secondary setter in
`0x305250`. Pending drops retain the full object datum, map-variant pointer,
layout generation, entry index and chosen grid, and expire after 30 ticks.
The marker fallback uses `0x603860(unit, out)` for the native view origin,
rather than the unit's model origin, and only considers the visible cursor
segment within a 0.35 m radius.

Local checks cover positive/negative grid coordinates, Normal/Fixed/Phased,
marker recreation, rigid-body release, 45/90-degree turns and saved transforms.
The native held-body spring can retain a small angular error, and collision
in Fixed mode can obstruct a requested orientation; Phased is appropriate for
precise structural assembly. Position snapping preserves the accepted axes.
All increments and invalid numeric inputs have portable regression coverage.
Forced deletion/map travel during a pending drop and multiplayer synchronization
remain unverified live; the cancellation guards have code review coverage.

## Next steps

1. Several layouts per map, picked in the lobby; a hub content type.
2. Fireteam Forge: done in code (2026-11-01); the lobby still refuses fireteam
   members (mods 0.42.0) until a two-PC test passes. The first lost PC 2 to a
   GPU crash during the client load ([forge.md](../forge.md)). FORGE has
   insertion slot 5 (MJOLNIRLobby `MODES`, loader `GAME_TYPE_SLOTS`,
   `games.lua` `GAME_TYPE_SLOT`), so clients start the sandbox engine. On a
   client (game options `+0x11` = 4) the DLL sends only the engine's own
   requests; client requests post net message `0x3e` to the host
   (`0x4074c0`). It keeps everything it does by hand to the host. Above all
   it never asks the host to grab, place or copy a marker, which would run the
   faulting grab on the host. It never applies a local layout at new map, so
   a client's objects stay the host's.
3. UI: a properties screen; tilting (only yaw so far). Physics, position grid
   and native angle snapping now have keyboard controls and HUD labels.
4. Republish the converted maps with the new palettes (the lift covers the
   old ones meanwhile, for the kinds they already place).
5. Building blocks: [../forge_blocks.md](../forge_blocks.md). Palette
   entries can be pointed at other loaded tags at run time (`slots.txt`);
   block packs need slot tags in the CE runtime.
