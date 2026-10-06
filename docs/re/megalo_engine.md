# The Megalo engine is still in the simulation (CU4)

**Status:** 2026-09-30. **The simulation ran the Megalo engine live** (engine
index 2, `megalo_objects` valid, map objects placed) on a converted CE map, with
three one-byte launch patches plus one to the map-load handler. See *Running
it* below. Later the same day it ran our own Megalo script, loaded from a file
once a sixth patch unblocked the variant loader (*The variant file loader,
fixed*).
**Binary:** `HaloSimulation_tag_release.dll`, CU4 (build lock in
[`../build_lock.md`](../build_lock.md)). Every address is an RVA into that
build.

This overturns the August conclusion in
[`../multiplayer_ctf_plan.md`](../multiplayer_ctf_plan.md) that "the DLL has no
megalo interpreter". Its Phase 1 step 2 asked whether there is code behind the
multiplayer definitions. There is: Halo Reach's whole game-engine layer
survives, including the Megalo scripting engine that runs every Reach mode
(Slayer, CTF, Oddball, KOTH, Assault, Infection, Juggernaut, Territories) as
data. What was cut is the path that asks for it. The Unreal host only ever
builds a Campaign variant.

## The four game engines

`current_game_engine()` at `0x180e70` reads the engine index from the
game-engine globals (TLS `+0x38`, offset `+0x846c`) and returns
`game_engines[index]` from the table at `0xbd5210`. Slot 0 is empty. Each
engine object's first vtable slot returns its own index.

| index | engine | object | vtable (slots) | variant size | confidence |
|---|---|---|---|---|---|
| 1 | sandbox (Forge) | `0xbd52d0` | `0x85d740` (114) | `0xf890` | inferred from Reach's order and the size |
| 2 | **Megalo** | `0xc7a7b8` | `0x85dae8` (114) | `0xf860` | observed: its slots call the Megalo trigger entry and walk `megalo_objects` |
| 3 | campaign | `0x9cbdc0` | `0x855b48` (112) | `0x838` | verified: the host's campaign path hard-codes 3 |
| 4 | survival (Firefight) | `0x9b1f78` | `0x845388` (112) | `0x9d0` | inferred |

Engines 1/2 and 3/4 share a base layer, as in Reach. The two multiplayer
engines reach about 1,130 functions (~288 KB) that campaign and Firefight never
touch.

Game-engine subsystem entry `0x83a5d0`; init `0x2ac210` allocates the engine
globals (`0x8480`), the local globals (`0xdce8`), the render globals (`0xe38`)
and the `megalo_objects` datum array (512 × `0x94`, TLS `+0x3a0`) on every
run, which is why `mjolnir live arrays` lists `megalo_objects` in a campaign
mission. New-map setup `0x2aca30` copies the engine index from the game
variant into `+0x846c`, and zeroes it if the engine's own checks fail.

## The interpreter

| piece | RVA | what it does |
|---|---|---|
| action executor | `0x399110` | 11 KB; switch on the action type byte at `+0x10`, 106 types, jump table `0x39bc3c`. 100 have real handlers; 18, 26, 32, 88, 102 and 103 are empty |
| condition evaluator | `0x39e640` | switch on the byte at `+0xc`, 17 types; case 1 compare, 2 object-in-boundary (shape tests), 3 killer-type flags — Reach's order |
| condition/action sequencer | `0x423a70` | 0x10-byte conditions with Reach's or-sequence and action-offset bytes, then the actions |
| trigger runner | `0x39ed40` | 10 trigger types (normal, for each player / team / object, ...) |
| trigger entry | `0x404530` | takes a lock, runs an entry-point trigger; called from Megalo engine slots 8, 10, 64, 79 and 113 |
| script location | `0x404660` | game options `+0x79e8` (variant `+0x63f8`) |
| script encode / decode | `0x3902d0` / `0x392a40` | per-action codec `0x39be20` / `0x39cf20`: 7-bit action type, then per-type parameters |
| variant file chunk | `0x373fa0` | builds a Reach `mpvr` chunk (`0x5028`) and its file header |
| variable sync | `0x403260` (engine slot 79) | numbers, timers, teams, players and objects over the bitstream |

Reach has 99 action types; 106 here fits the MCC-era additions (inferred).

## How the host picks the engine

The shell's event drain `0xe670` handles event `0xb`, "load map" (map path,
difficulty, player data, a has-campaign-variant flag at payload `+0x5a`,
Unreal's `CampaignVariantStorage` at `+0x5b`), and calls `0xf650`. That builds
a `0xfc04`-byte game variant — a 4-byte engine index and a union — through
`0x21c4f0(&variant, 0 or 3)` and stores it into the pending game options with
`0x216300`. Both functions accept indices 1–4; only this caller restricts
them, which is why Unreal's `EBlamGameEngineType` has just `None` and
`Campaign`.

Game options are `0x1ebb0` bytes at game globals `+0x10`, the variant at
`+0x15f0`, the game mode byte at `+0x10` (1 campaign, 2 multiplayer; 3 is seen
at the frontend).

## What still blocks a match

- **No console route.** `game_multiplayer`, `game_set_variant`, `game_start*`,
  `net_load_and_use_game_variant`, `net_build_game_variant`,
  `load_binary_game_engine` and `read_map_variant_and_make_current` are stubs
  in [`../../defs/hce/console.json`](../../defs/hce/console.json). The `mp_*`
  script functions are live.
- **No content.** The Megalo sound table is 94 of 95 slots empty, the
  multiplayer object list holds weapons only (no flag), and the per-mode
  settings tags were cut. A Megalo variant carries its rules itself, so the
  settings tags matter less than they look; the flag object and a scenario's
  multiplayer labels (spawns, goals) still matter.
- **Validation** (inferred risk): `0x2aca30` may reject a multiplayer engine on a
  campaign scenario with no multiplayer data.
- Networking goes through Unreal, not the sim's stubbed `net_*` layer.

## Next experiments, cheapest first

1. **Read only.** In a running mission, read TLS `+0x38` → `+0x846c` on the sim
   thread (the Blam console's native mailbox already runs there). Expect 3,
   and `0x180e70` returning the campaign object.
2. **One change.** At the frontend, hook the `0x216300` store when called from
   `0xf650` and set the engine index to 2, with the default Megalo variant from
   `0x21c4f0(…, 2)`. Start a mission from the menu and re-read `+0x846c`:
   2 and engine object `0xc7a7b8` means the switch held; 0 means the scenario
   was rejected and the next step is a multiplayer-typed scenario.
3. Decode a Reach Slayer variant into the variant through `0x392a40`, and count
   calls into `0x404530`: triggers firing is Megalo running.

The Reach variant format is documented in public by the ReachVariantTool
project; use it for structure only.

## Running it (live, 2026-09-30)

`mjolnir live engine` reads the running engine from outside the process (sim
thread TLS `+0x38` → `+0x846c`) and checks the engine table and vtables in
memory; all four matched. The index is 0 at the menu and 3 in a campaign
mission.

The launch needs four byte changes, all in memory, applied at the main menu
before a mission is started, and all reversible:

| RVA | shipped → patched | why |
|---|---|---|
| `0xf6dd` | `03` → `02` | map-load handler asks `0x21c4f0` for the Megalo engine; the campaign fields are copied in only for engine 3, and the launch mode is derived from the engine (1/2 → 3 multiplayer) |
| `0x55af5a` | `18` → `08` | session readiness `0x55a2a0`, required-parameter mask for session modes 3/4 (`0x8001813e0`): drop bit 20, the map variant ("no map selected") |
| `0x55e8c7` | `74 31` → `74 34` | options-from-session builder `0x55e1c0`: a missing map variant no longer clears the ok flag |
| `0x45b1a7` | `18` → `08` | the in-game step `0x55c730` checks the same mask again through `0x45b160` before building options; same bit |

```text
mjolnir live engine --launch-engine 2 --map-variant-gate skip   # at the menu
mjolnir live engine --launch-engine 3 --map-variant-gate keep   # put it back
```

The mask constant occurs three times in the image; the third (`0x55d2ff`, a
resync that copies the game's map variant back into the session once a game
exists) is left alone. The campaign flow never provides a map variant
(its only session setter is the UI's `0x45adb0`); with the gate skipped the
options keep the default map variant, which options verify `0x208cb0` accepts.

Launch trace (read live by the RE pass): launch-state dispatcher variable
`0x13574e0`, pending flag `0x1357510` (bit 1), pending mode `0x1357518`,
pending variant engine `0x1358af8`, map path `0x135755c`; session lifecycle
state `0xca3428` (states' functions at `0xca3430[i]`, 3 = in game, update
`0x55c730`), session object `*0xca3480` with start status at `+0x595a0`.

Result on Hang 'Em High (standalone HEH, scnr `type` set to multiplayer,
though type is not what gates the launch — the multiplayer-typed map starts
normally under the campaign engine): engine index 2, `megalo_objects` valid,
26 map objects placed, one player, **no unit spawned after 30 s**, black
screen. The default variant from `0x21c4f0(…, 2)` has an empty script; next
is whether the player waits on the variant's respawn settings or on
multiplayer-flagged starts, then decoding a real Slayer variant through
`0x392a40`.

## A player spawns under Megalo (2026-09-30, later)

On B40's own geometry, test level "Megalo test (B40 floor)" (standalone HEH):
engine index 2, four spawn-point scenery objects created, the player's
Spartan created at a spawn point with the default multiplayer loadout
(assault rifle, 32/324), placed weapons resting on the floor, HUD live. What
it took, beyond the four launch patches above:

1. **Spawn points.** Under a multiplayer engine players spawn only at scenery
   whose `multiplayer object` type is *player spawn location* (15); a first
   spawn needs the *valid initial player spawn* flag (spawn loop `0x185b80`,
   location search `0x2f77a0` → `0x2f84e0`, scenery only). The scenario's
   player starting locations are not consulted. None ships, so
   `objects\multi\spawning\player_spawn` is built with
   `mjolnir new-tag --group scenery --from unsc_data_pad --graft "object.multiplayer object=weapon:assault_rifle-weapon:item.object.multiplayer object" --set "object.multiplayer object[0].type=player spawn location" --set "object.multiplayer object[0].flags=valid initial player spawn"`.
   The object needs a model: the variant's object creation (`0x32f450`) skips
   a tag whose `model` is unset (the first build, from the invisible
   `cinematic_anchor`, was skipped).
2. **A map variant palette.** Objects whose tag has a `multiplayer object`
   block (weapons, vehicles, spawn points) are created only through the map
   variant, which new-map builds from the scenario's placements (`0x32cc00`
   → `0x32e0c0`) keeping only tags listed in `map variant palettes`
   (`0x32cd50`). `level bake` writes one when `blam.map_variant` is true.
   Creation (`0x32f450` → `0x5ee0d0`) also checks the game options' map
   options byte (`[TLS+0x60]+0x18f0`, the base variant's `u6` at `o+0x2fc`):
   a multiplayer object of type grenade (2) needs bit 0, equipment (5) bit 2,
   powerup (4) bit 3, turret (10) bit 4, and a shortcut placement bit 1. Bit 5
   makes vehicles indestructible (`0x66ee40`). Our variants set `0x1f`
   (`MAP_FLAGS`); at 0, no placed grenade, overshield or camouflage appeared.
   `cargo run -p blam-live --example mapvar_probe` reads the byte and the
   variant's entries by type.
3. **Keep the variant.** The game engine's zone-set handler (`0x2ad2d0`)
   deletes the variant's objects and resets it after load:
   `--map-variant-reset skip` (`0x2ad2e2` `74 36` → `EB 36`).
4. The scenario's `type` is set to multiplayer (`blam.set`), though it does
   not gate anything found so far.

```text
mjolnir live engine --launch-engine 2 --map-variant-gate skip --map-variant-reset skip
```

On the converted Hang 'Em High the same pipeline creates the weapons, and
they fall through the terrain and are deleted (z ≈ -636): the sim still has
no working collision for converted terrain (`../ce_terrain_collision.md`).

## A variant from a file: Slayer (2026-09-30, offline)

The default variant the switch produces has an empty script, so nothing
scores. Two findings make real modes a file away:

- **The simulation loads variants from disk.** At each round reset
  (`0x2ad560`, run by game start and round start), with the Megalo engine
  running, it checks a name buffer at RVA `0x152a7c0` (0x100 bytes). If set,
  it reads `<name>.mglo` (at most 0x5000 bytes) from a directory the Unreal host
  supplies (path struct `0x180c79d40`, root at `+8`, filled at runtime), decodes
  it into the live variant through slot 5, validates it (`0x40a310`) and clears
  the name.
- **The bitstream grammar** is fully read out of the decoder:
  [megalo_variant_format.md](megalo_variant_format.md).

`crates/blam-megalo` writes that stream and reads it back by the same grammar;
`mjolnir megalo write --mode slayer --score 25 --out mjolnir.mglo` produces a
1,131-byte free-for-all Slayer:

- trigger 0, every tick for each player: if the player died a *kill* death this
  tick (condition 3), fetch the killer into `global.player[0]` (action 29) and,
  unless that is the player themselves (condition 1), add 1 to the killer's
  score (action 1);
- trigger 1, for each player: if their score reaches the score to win
  (number kinds 8 and 16), end the round (action 21).

Scores live in the engine globals at `+0x32c0` (player i at `+i*8`, a 16-bit
score); there is no built-in kill scoring.

## The variant file loader, fixed (2026-09-30, in game)

As shipped, the loader never decodes a file under the Unreal host. Its reader
(`0x3f8bb0` → `0x3f8a00`) resets the variant (slot 2), opens, sizes, reads and
**closes** the file, then asks the size again (`0x74f410`) to bound the
bitstream. With the host's file system present (`[0x2c40028]+0x10`, vtable
`+0xc0` non-null, which it always is) that size query goes by handle, and close
has already set the handle to -1, so it fails and the file is dropped. The
live variant keeps the defaults: encoding version `0x6b` at `o+0x5dc0`, where
a decoded file would leave its own (`0x6a`). Only the Win32 fallback,
which sizes by path, could ever have worked.

The sixth switch patch replaces the size query (`0x3f8a8d`, 15 bytes: `lea rdx,
[rbp+0x5008]; mov rcx, rbx; call 0x74f410`) with `mov dword [rbp+0x5008],
0x5000; mov al, 1`: the bitstream is bounded by the 0x5000-byte buffer. The
decoder reads only what the grammar asks for and checks only that it did not
read past that bound.

Where things live, on CU4:

| What | Where |
|---|---|
| game options | `[TLS+0x60]`, engine byte at `+0x10` |
| variant | `[TLS+0x60] + 0x15f0`: `u16` type (2 = Megalo) at `+0`, object `o` at `+4` (its vtable is at `o`) |
| script getter | `0x404660` returns `[TLS+0x60] + 0x79e8` (= `o + 0x63f4`) for engines 1 to 3 |
| directory | `%LOCALAPPDATA%\Meteorite\Saved\BlamData\HotReload\` (path struct `0xc79d40`, filled on first use) |

The loader also runs for engine 3 (campaign) with a variant of type 1 or 2.

Verified on the converted Blood Gulch: the level file's `"variant": "slayer"`
has MJOLNIRLevelLoader stage `variants/slayer.mglo`; `mjolnir_megalo_variant`
copies it to `HotReload\mjolnir.mglo` (creating the directory) and sets the
name, and the round reset decodes it: version `0x6a`, 2 triggers, 3
conditions, 3 actions, score to win 25, exactly what `mjolnir megalo read`
shows. `mjolnir megalo write --mode tick` (every player +1 each tick, the same
end-of-round trigger) drove a lone player's score up at about 60 a second,
and at the score to win the round ended and the game returned to the main
menu. So the interpreter runs our scripts, including the player score,
score-to-win and end-round kinds.

**Still inferred:** the kill bit of condition 3 (Reach's death-type order,
`1 << 2`) and the killer lookup (action 29); scoring a kill needs a second
player. The base-option defaults this encoder writes load without complaint.

## Rounds, the end of a game, and the next map (2026-10-02, in game)

One player, converted Blood Gulch, CU4, from the multiplayer menu.

**Rounds reset in place.** The base variant's rounds (`u5` at `o+0x2bb`) are
`Variant::rounds` and `mjolnir megalo write --rounds N`. With
`--mode tick --score 450 --rounds 3`, the incidents were:

```text
11:15:48 player_spawn   11:15:56 round_over
11:16:03 player_spawn   11:16:11 round_over
11:16:17 player_spawn   11:16:25 game_over
```

An end of round with rounds left respawns everyone on the same map, with no
travel. At the last round the sim raises `game_over`, and about 15 s later
the host is back at the frontend (seen there at 11:16:41). `round_over` and
`game_over` reach `BPC_MeteoriteIncidentHandlerComponent_C:OnIncident_Event`
with cause and effect -1. A hook on that function registers only once the
class is loaded, so arm it in a map, not at the frontend.

**The next map from inside a map does not start a game.** Both routes fail:
- `BPFL_CampaignMenuHelpers.StartCountdown` called in a map does nothing. The
  countdown lives on `BP_FrontendGameState`.
- `BlamCampaignFlowGameSubsystem:SetAndBeginCampaign(CurrentCampaign, "GPH",
  options)` returns true, and the UE world travels to GPH. The loader
  switches it to Megalo and stages the variant, and the pawn is possessed.
  But the sim holds 1 player with no unit and 0 objects, not even scenery,
  and the screen stays black. `live engine` shows engine 2. `mapvar_probe`
  shows a populated map variant (54 spawn points). No Blam error
  (`GetLastBlamErrorName` = None).
- The failure is the same whether `GameVariant` is the flow subsystem's
  live variant or a fresh `BlamGameEngineCampaignVariant`.
  `RestartLevel()` on the broken GPH changes nothing.
- The control, GPH started from the menu, had 203 objects and a Spartan.

The frontend's own start (`BP_FrontendGameState` export 4 → helpers export
29, `LaunchCampaign`) builds exactly these options. Its only extra is
`SetPerPlayerTraits` per player on a newly spawned variant. So the
difference is native: the CU3 campaign's in-mission switch (A15 → A30)
worked, but a Megalo game in progress blocks the next one. This is
unexplained.

`BlamCampaignFlowGameSubsystem`'s reflected functions: `SetAndBeginCampaign`,
`SetActiveCampaign`, `RevertToLastSave`, `RestartLevel`, `LeaveGame`
(returns to the frontend), `GetLastBlamErrorName`, `EndCampaign`,
`BeginCampaign`, `AcknowledgeLastBlamError`. `BlamOnlineSessionSubsystem`
reflects no properties.

## Quitting from a match (2026-10-05, in game)

**Symptom.** Alt+F4, the window's close button or the console `quit` from
inside a converted multiplayer match closed the window within seconds, but
`HaloCampaignEvolved.exe` never exited. The next launch then failed with
"already running". From the frontend, or after leaving the match for the
lobby, the same quit exits in about 5 s.

**Why.** On exit the Unreal host asks the simulation to stop and waits for
it:

| Where | What |
|---|---|
| exe `0x7b1d8e0` | the wait: calls the stop request, then loops `Sleep(0)` until the host object's state byte (`+0x1a8`) reads 2 |
| exe `0x7b24160` | the stop request: state 0 → 1, sets the stop flag (`[obj+0x140]+0xa`), posts shell event 0/7 into the simulation's queue (`[obj+0x1c8]`, vtable `+0x20` then `+8`, `dl = 7`); the only place in the exe that posts this event |
| sim `0x9e60` | the simulation thread: main loop `0x1af6e0`, then shutdown `0x61f0`, then the host's exit callback, which is what lets the wait end |
| sim `0x1af6e0` | the main loop runs until the byte at `0x1357023` is set |
| sim `0xe670` → `0xeeef` | the event drain, case 0/7: if no game is in progress (`0x209a20`), set `0x1357023`; with a game in progress, set it only when the game options' mode byte (`[TLS+0x60]+0x10`) is 1 (campaign) |

So with a Megalo game running (mode 2) the exit event is dropped. It is
posted only once, so the main loop keeps ticking the match and the host's
wait never ends. The Unreal host never ran a multiplayer game, so it never
hit this.

**Fix.** `mjolnir_map_registry.dll` (MJOLNIRLevelLoader 0.3.1) NOPs the
mode check's `jne` at sim `0xef18` (`0f 85 0d 05 00 00` → `66 0f 1f 44 00
00`). A multiplayer game then exits the loop the way a campaign mission
already does. The patch is the seventh in the Megalo switch's table and
`mjolnir_megalo_off` leaves it in place. Outside a non-campaign game it
changes nothing, because the branch it removes is taken only there.

Checked on CU4, hosting Blood Gulch (private), with the patched DLL:

| Quit from the match | Before | After |
|---|---|---|
| WM_CLOSE (`taskkill` without `/F`) | never exited (90 s+) | exited in 5.2 s |
| Alt+F4 | never exited | 5.3 s |
| console `quit` | not tried | 5.8 s |

Every quit was clean: the log ends with `Gauntlet Shutdown` and no crash
report was written. Before the DLL was changed, setting `0x1357023` by hand
in a process already stuck this way let it exit in 4.6 s, also cleanly.
The pause menu in a match has no quit to desktop. Its SAVE AND EXIT goes to
the frontend and was never affected.
