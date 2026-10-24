# The Reach game engine in the simulation, and how the host uses it (CU4)

**Status:** 2026-10-21. A map, read statically, of how the CU4 simulation runs
game modes and what the Unreal host does with the result. It was checked
against Bungie's own Reach variants and by second, adversarial passes over
the first readings. Nothing here was measured in a running game unless it
says so. The live reads that would settle what is still open are listed at
the end.
**Binaries:** `HaloSimulation_tag_release.dll` CU4 ("sim", image base
`0x180000000`) and `HaloCampaignEvolved.exe` CU4 ("exe", image base
`0x140000000`); build lock in [`../build_lock.md`](../build_lock.md). Every
address is an RVA. Exe addresses always say exe; any address with no binary
named is a sim RVA.

How MJOLNIR switches the simulation to the Megalo engine and loads its own
`.mglo` files is in [megalo_engine.md](megalo_engine.md) (the working
history). The variant bitstream, with every action, condition and operand, is
in [megalo_variant_format.md](megalo_variant_format.md). Built on this map:
[`../game_modes.md`](../game_modes.md) (what runs today, the two colour
bugs and their fixes, the other Reach modes, how to prove a mode) and
[`../custom_game_types.md`](../custom_game_types.md) (the hub design for
custom game types). Player-facing pieces:
[`../host_game_settings.md`](../host_game_settings.md),
[`../multiplayer_hud.md`](../multiplayer_hud.md),
[`../multiplayer_postgame.md`](../multiplayer_postgame.md),
[`../game_state_reader.md`](../game_state_reader.md).

Each claim is marked **VERIFIED** (the code or data that shows it was read)
or **INFERRED** (names, Reach knowledge, or a chain with one unread link).
Reach knowledge is a hint for CU4, never proof. Names of actions,
conditions, operand kinds and enum values come from ReachVariantTool
(GPLv3), used for names only; no code of it is in this repository.

## Conventions

| Name | Meaning |
|---|---|
| `G` | engine globals, `[TLS+0x38]`, 0x8480 bytes (allocated by sim `0x2ac210`) |
| `GG` | game globals, `[TLS+0x60]`; the game options (0x1ebb0 bytes) start at `GG+0x10` |
| `v` | the running game variant, `GG+0x15f0`: a u16 engine type at `v+0`, then the variant object |
| `o` | the variant object, `v+4`. The bitstream doc quotes `o`-relative stores; engine code reads `v`-relative ones, so `o+X` is `v+X+4` |
| `P` | player datum: `[[TLS+0x30]+0x50] + i*0x4b0` |
| `D(h)` | object datum of handle `h` (header array `[TLS+0x20]`, entry `+0x10`) |
| `MP(h)` | the object's multiplayer block, `D + u16 D+0x182` (none when the u16 is `0xffff`) |
| `MO` | the object's `megalo_objects` element (`[TLS+0x3a0]`, 512 x 0x94), index at `D+0x148` |
| team index | a variant team slot, 0 to 7 |
| designator | the team the engine reasons with, `G+0x1c[index]` (8 is neutral) |

Object types (`D+0x8e`): 0 biped, 1 vehicle, 2 weapon, 3 equipment,
4 terminal, 5 projectile, 6 scenery, 7 machine, 8 control, 9 sound scenery,
10 crate, 11 creature, 12 giant, 13 effect scenery
(`defs/hce/tag-definitions.json`). Mask `0x1003` (biped, vehicle, giant) is
"unit" throughout both binaries.

## The picture in one page

1. The simulation keeps Reach's four game engines. Engine 2, Megalo, runs
   every multiplayer mode as data. The host only ever asks for campaign;
   MJOLNIR's byte patches switch it ([megalo_engine.md](megalo_engine.md)).
2. In a Megalo match the game options' mode byte is **3** (1 campaign,
   2 Firefight, 3 multiplayer), not 2 as `megalo_engine.md` says. The
   simulation type is **5** (distributed server) on the host and **4**
   (distributed client) on every other fireteam machine. Both are VERIFIED
   statically, each with one inferred link; neither has been read live.
3. Every fireteam machine runs a whole simulation. The sims talk Reach's own
   distributed protocol over the exe's PlayFab Party transport. The host runs
   every trigger; a client runs only the variant's `local` entry point and
   receives scores, variables, objects, owner teams and incidents from the
   host. Each machine decodes that state against **its own** copy of the
   variant, so all copies must declare the same variables.
4. Teams are assigned by the host's session layer (sim `0x4bab20`), not by
   the script and not by MJOLNIR. `P+0xad` is the team index. `P+0xac` is
   `0xff` in a Megalo game.
5. The simulation knows every object's owner team (`MP+0x19`) and computes
   team change colours. **None of that reaches Unreal.** The host draws the
   model variant and region permutations the sim selects, plus a team
   component on units only.
6. Incidents are the event channel to Unreal: sim `0x406560` hands each one
   to exe `0x7b96d10`, which builds an `FBlamIncident`. Megalo cannot raise
   the engine's own incidents (string ids `0x68xxxx`). A client hears only
   incidents addressed to its own players.
7. Megalo waypoints, HUD widgets, objective text and progress meters stay in
   the simulation. The navpoints the host draws are HaloScript's
   `chud_track_*` list.
8. The engine ends a round by itself on score to win, round count and early
   victory, never on the time limit. The simulation ticks 60 times a second.

## The four engines

`current_game_engine()` (sim `0x180e70`) reads the engine index at
`G+0x846c` and returns `game_engines[index]` from the table at sim `0xbd5210`
(slot 0 empty). Slot 0 of each vtable returns the engine's own index. All
VERIFIED (memory read of the table and the vtables).

| Index | Engine | Object (sim) | Vtable (sim), slots | Slot 0 returns | Variant size |
|---|---|---|---|---|---|
| 1 | sandbox (Forge) | `0xbd52d0` | `0x85d740`, 114 | `0x6970`: 1 | `0xf890` |
| 2 | **Megalo** | `0xc7a7b8` | `0x85dae8`, 114 | `0x47d60`: 2 | `0xf860` |
| 3 | campaign | `0x9cbdc0` | `0x855b48`, 112 | `0xa91c0`: 3 | `0x838` |
| 4 | survival (Firefight) | `0x9b1f78` | `0x845388`, 112 | `0x34870`: 4 | `0x9d0` |

The names of 1 and 4 are INFERRED from Reach's order. Slots equal in Megalo
and sandbox are the shared multiplayer base (functions around sim
`0x3fd000`-`0x404000`); slots equal in all four are the game-engine base
(around `0x3ef000`-`0x3f4000`). The variant decoder is a different vtable:
the variant object's, sim `0x83c3b8` slot 5 (`0x392a40`).

## The Megalo engine's vtable (sim `0x85dae8`)

"M=S" marks a slot shared with sandbox. Roles were read from each body and
from the callers found after `0x180e70`.

| Slot | Function (sim) | M=S | Role | Status |
|---|---|---|---|---|
| 0 | `0x47d60` | | engine index, `mov eax,2` | VERIFIED |
| 1 | `0x2ae2a0` | all | score to win: variant vt+0x48, `o+0xf83c` | VERIFIED |
| 2 | `0x3ef690` | all | modify team score (team, value, mode 0 add, 1 minimum, 2 maximum of members); clamps to +/-30000; marks the score entity dirty | VERIFIED |
| 4 | `0x400660` | | build one player's sim HUD state: objective text, caption, icon, progress meter, visible Megalo widgets, timed messages; then slot 109 when `fireteams_enabled` | VERIFIED (caller `0x753bb0`) |
| 7 | `0x3ef910` | | "enough teams": false when `G+0xc` has two or more teams and `G+0x1a` fewer than two | VERIFIED |
| 8 | `0x3fd550` | | new map: zero Megalo state, validate the variant (`0x40a310`), run the **pregame** entry point | VERIFIED |
| 9 | `0x3fd710` | | dispose: mark `megalo_objects` invalid | VERIFIED |
| 10 | `0x3fd740` | | new round: initialise player, team and global variables; run **init** (not on a type-4 client) and **local init** | VERIFIED |
| 13 | `0x3fd980` | all | thunk to `0x3efae0`: team setup, enabled-team mask `G+8`, designators `G+0x1c` under the designator switch type | VERIFIED |
| 14 | `0x3fee00` | M=S | initialise one player's Megalo variables (`+0x75` team override = `0xff`, `0x408d00`) | VERIFIED |
| 18 | `0x3fecb0` | M=S | copy one player's Megalo state to another slot | VERIFIED |
| 26 | `0x3ff760` | M=S | build a local user's Megalo navpoints into the sim's chud list (`0x4728b0`) | VERIFIED |
| 29 | `0x3fdad0` | | per tick: clear applied traits, run triggers (slot 113), tick timers, draw boundary shapes in the owner's colour, raise `pre_game_over`, clear death records | VERIFIED |
| 30 | `0x3f09b0` | | per player per tick: grenade regeneration, shield callback, recompute and push the unit's change colours (`0x182cb0`) | VERIFIED |
| 31 / 32 | `0x3f0ca0` / `0x3ff1b0` | M=S / | apply base player traits (`v+0x304`) / apply Megalo trait sets | VERIFIED |
| 39 | `0x401c00` | | may this player pick up this object (`MO+0x1c` against player and object team) | VERIFIED |
| 40 / 41 | `0x401d70` / `0x401cd0` | M=S | pickup priority automatic (`MO+3 == 2`) / hold (`MO+3 == 1`) | VERIFIED |
| 42 / 43 | `0x4011d0` / `0x401300` | | does a placement / an object about to be created match a label filter | VERIFIED |
| 45 / 46 | `0x3f1040` / `0x3f1110` | all | weapon set / vehicle set | VERIFIED |
| 49 | `0x401420` | M=S | object created: link into label lists, recolour | VERIFIED (caller `object_new` `0x5a0fc0`) |
| 50 | `0x401470` | | object deleted: clear every Megalo variable naming it, unlink labels, free its `MO` | VERIFIED |
| 51 / 52 | `0x401930` / `0x401a30` | M=S | object team about to change / changed: relink team-filtered labels, recolour | VERIFIED (caller `0x66af70`) |
| 53 | `0x3fee90` | M=S | a player's team: teams on, `G+0x1c[P+0xad]`; teams off, the per-player override `G+0x3b9+i*0xf0` | VERIFIED |
| 54 / 55 | `0x3fef50` / `0x3ff050` | M=S | are two players / two teams enemies | VERIFIED |
| 59 | `0x3febf0` | M=S | add an assist bit to this tick's death record | VERIFIED |
| 61 / 62 / 63 | `0x3fe940` / `0x3fea10` / `0x3fe9a0` | M=S / / M=S | incidents begin (reset the death record) / observe kills and deaths into it / end (append it to the tick's list) | VERIFIED |
| 64 | `0x3fe6a0` | | object died: set the death context, run the **object death** entry point (not on a type-4 client), raise `first_blood` once a round | VERIFIED |
| 73 / 74 | `0x1e700` / `0x67550` | | "round should end" hook: false / round timers tick: true | VERIFIED |
| 79 | `0x403260` | | host-migration import of Megalo state, then the **host migration** or **double host migration** entry point | VERIFIED |
| 82 | `0x404370` | M=S | force a full resync (all dirty bits) | VERIFIED |
| 83 / 84 / 85 | `0x3f3070` / `0x3f3120` / `0x3f3b40` | all | engine-globals entity: default / compare and encode / apply (`G+0x128` from mask bit 2) | VERIFIED |
| 86 / 87 / 88 | `0x401e20` / `0x401ee0` / `0x4022b0` | | Megalo globals entity: build / diff / apply (global variables, HUD widgets; apply re-sets every object's team) | VERIFIED |
| 89 / 90 / 91 | `0x4024f0` / `0x402650` / `0x402860` | M=S | per-player entity: init / diff / apply | VERIFIED |
| 97 | `0x3f17a0` | all | `multiplayer_globals` universal entry for this engine | VERIFIED |
| 99 | `0x47d60` | all four | simulation protocol to ask for at launch: 2 (distributed) | VERIFIED |
| 103 / 104 / 105 | `0x67550` | | need two teams or players / update the per-object tables / re-roll spawn random bias: all true | VERIFIED |
| 109 / 110 | `0x3f1870` / `0x3f1940` | all | teammate HUD entries | VERIFIED |
| 112 | `0x400c50` | M=S | HUD widget meters per local user | VERIFIED (partial) |
| 113 | `0x3fe520` | | run triggers: host, every trigger whose attribute is 0 or 6; type-4 client, only the **local** entry point | VERIFIED |

The other slots are trivial in Megalo: 5, 6, 67, 70, 93, 101 return 0; 12,
44, 57, 65, 71, 95, 100, 102 return 1; 47, 60, 96 return -1; 11, 15, 16, 17,
19-25, 33, 66, 72, 76, 81, 98, 108 are `ret`. Sandbox overrides slots 16,
19, 21, 23, 29, 30, 32, 39, 42, 43, 50, 56, 62, 64, 66, 72-74, 79, 86-88 and
113 (Forge). VERIFIED.

Game-engine subsystem init (sim `0x2ac210`) allocates the engine globals, the
local and render globals, and `megalo_objects` (512 x 0x94, `[TLS+0x3a0]`)
on every run, campaign included. New-map setup (sim `0x2aca30`) copies the
engine index from the variant into `G+0x846c`. VERIFIED.

## Game options: mode byte, simulation type, tick rate

| `GG+` | Field | Values | Status |
|---|---|---|---|
| `+0x10` | game mode | 1 campaign, 2 Firefight, 3 multiplayer | VERIFIED (below) |
| `+0x11` | simulation type | 0 none, 1 local, 2 synchronous client, 3 synchronous server, 4 distributed client, 5 distributed server (name table sim `0x7b1620`, read by `0x107a4`) | VERIFIED |
| `+0x12` | session class, copied from `session+0x28` | 1 forces the local protocol | VERIFIED copy; meaning INFERRED |
| `+0x16` | ticks per second (options `+6`) | default 60 (`0x208a70`), validated 1-300 (`0x208cb0`), copied to `[TLS+0x98]+6` at map init (`0x20ff70`) | VERIFIED |
| `+0x1da` | playback type | non-zero = film playback; turns replication off | VERIFIED |
| `+0x15f0` | game variant | u16 engine type, then the variant object | VERIFIED |
| `+0x18f0` | the base variant's map flags (`o+0x2fc`) | read by object creation | VERIFIED ([megalo_engine.md](megalo_engine.md)) |
| `+0x1ebcc` | game over | set once the game ends | VERIFIED use |

**The mode byte is 3 in a Megalo match.** The map-load handler sim `0xf650`
sets the pending mode (`0x1357518`) to 3 for engines 1 and 2, 1 for
campaign and 2 for Firefight. Launch state 6 (`0x2060f0`) turns it into a
session type; the options builder `0x55e1c0` writes the mode byte (3 for any
session type other than 1 and 6); `0x2069e0` copies the options to
`GG+0x10`. An independent check: `0x406cf0` maps mode 1, 2, 3 to an
incident definition's "disallowed game modes" bits campaign, Firefight,
multiplayer. VERIFIED, except that the session value `0x55e1c0` reads is the
one `0x4c1e10` stored (INFERRED). Several team paths test `== 3` (`0x182cb0`,
`0x1823c0`, `0x32b600`, `0x2afa70`), so they run in MJOLNIR matches.

**The simulation type.** `0x55e1c0` writes `GG+0x11` from the session
parameter `simulation-protocol` (`session+0x5eb8`; name string sim
`0x8c0fd0`) and whether the local peer is the session host: protocol 0 gives
1, protocol 1 gives 2 or 3, protocol 2 gives 4 (client) or 5 (host). The
launch writer `0x4c1f20` asks the engine through slot 99, which is
`mov eax,2` in all four engines, so every game asks for the distributed
protocol unless the session class (`session+0x28`) is 1 or there is no
variant. The host's in-game step `0x55c730` republishes what it runs.
VERIFIED chain; the runtime value of `session+0x28` was not read.

The simulation world (`[sim 0x2c0c978]` = sim `0xd5ccb0`) carries a world
type at `+0x10`, written by `0x4f6d10` at simulation start: options type 1,
2, 3, 4, 5 become world types 1, 4, 3, 8, 7; playback types 1, 2, 3 become
2, 5, 6. Host migration writes 7 (`0x4fdd80`). The setter `0x4d94e0` maps a
world type back to `GG+0x11` and `GG+0x1da` (jump table `0x4da160`; the
"second table" `0x4da184` is the same array from index 9). VERIFIED.

The three replication gates (`0x4d21b0` objects, `0x4d1d40` entities,
`0x2f61b0` incident events) reduce to **`GG+0x11 == 5` and no playback**:
only the distributed host marks state dirty or sends incidents. VERIFIED.

**Tick rate.** The only immediate store of 30 or 60 to a `+6` options field
is the 60 in `0x208a70`. Megalo timers are declared in seconds and scaled by
`[TLS+0x98]+6` at initialisation (`0x408d00`), so they are unaffected. A
script that counts ticks in a number must assume 60. VERIFIED statically,
and it fits the observed score of "about 60 a second" from a variant that
scores every tick ([megalo_engine.md](megalo_engine.md)).

## Engine globals (`G`, `[TLS+0x38]`)

| `G+` | Type | Meaning | Status |
|---|---|---|---|
| `+0x00` | u32 flags | bit 0 standings dirty, bit 3 **teams on** (the variant's teams flag, `v+0x2bc` bit 0; tested by `0x180e10`) | VERIFIED |
| `+0x06` | u16 | designators of enabled teams | VERIFIED |
| `+0x08` | u16 | enabled variant teams (bit = team index) | VERIFIED |
| `+0x0a`, `+0x0c` | u16 | team masks used by the end checks and slot 7 | VERIFIED use, meaning INFERRED |
| `+0x0e` | 8 x i8 | previous designator mapping (rotate) | VERIFIED |
| `+0x16` / `+0x18` | u16 | teams with players now / teams that have had players (`0x20bee0`) | VERIFIED |
| `+0x1a` | u16 | designators in use | VERIFIED |
| `+0x1c` | 8 x i8 | **designator of each variant team** (`0x20bb90`; reverse map `0x20bb00`) | VERIFIED |
| `+0x24` | bytes | copied from the respawn options at round reset | VERIFIED copy, meaning INFERRED |
| `+0x2c`, `+0x48`, `+0xa8`, `+0xe8` | handles | replicated entity handles, resolved by `0x382310`: `+0x2c` engine-globals entities, `+0x48` score entities (16 players, then 8 teams), `+0xa8` and `+0xe8` the per-player and per-team Megalo entities | VERIFIED; which of `+0xa8`/`+0xe8` is which INFERRED |
| `+0x128` | u16 | game state: 1 playing, 2 round over, 3 between rounds | VERIFIED values, names INFERRED |
| `+0x12a` | i16 | round index (cap `0x3ff`) | VERIFIED |
| `+0x12c` | i32 | round start tick | VERIFIED |
| `+0x134` / `+0x138` / `+0x13c` | timers | round timer, sudden death, grace period | VERIFIED |
| `+0x140`..`+0x1bb` | | standings snapshot (`0x3f8e10`) | VERIFIED |
| `+0x1bc` / `+0x1c0` / `+0x1c4` | | Megalo trigger context: current object, current player, current team (-1 before each run) | VERIFIED |
| `+0x1cc` / `+0x1d0` / `+0x1d4` / `+0x1d8` | | death context: killed object, killer object, **killer player**, death damage type byte | VERIFIED writes (slot 64); `+0x1d0` name INFERRED |
| `+0x1dc`..`+0x1eb` | 16 B | this tick's death record being built: victim, killer `+4`, damage type `+8`, modifier `+9`, death type `+0xa`, assist mask `+0xc` | VERIFIED |
| `+0x1ec` | | global Megalo variables: 16 objects, teams at `+0x22c`, 12 numbers at `+0x234`, timers at `+0x264`, players at `+0x284` | VERIFIED layout |
| `+0x294` | ptr | temporaries | VERIFIED (via NUMBER kind 44) |
| `+0x29c` / `+0x2a4` | i32 / 4 x 0x28 | Megalo HUD widget count / widgets (position, visibility mask, text, value text, meter, icon) | VERIFIED layout |
| `+0x344` | 16 x 0xf0 | per-player Megalo state (below) | VERIFIED |
| `+0x1244` | 9 x 0x58 | per-team Megalo state (objects, teams, 8 numbers at `+0x1c`, timers at `+0x3c`) | VERIFIED |
| `+0x155c` | 16 x u32 | head of each label's object list | VERIFIED |
| `+0x159c` / `+0x15a4` | i32 / 16 B each | this tick's death records (layout as `+0x1dc`) | VERIFIED |
| `+0x32c0` | | **score block**: player `i` at `+i*8`, team `t` at `+0x80+t*8`; each {i16, i16, i16 rounds won, byte} | VERIFIED; which i16 is round and which game score INFERRED (getters read `+2` once `GG+0x1ebcc` is set) |
| `+0x3624` / `+0x62d4` | 715 entries | per-object engine tables, objects deleted at round change | VERIFIED use, meaning INFERRED |
| `+0x8458` | i32 | round-over / round-start countdown | VERIFIED |
| `+0x845c` | i32 | round phase: 1 active, 2 over, 3 between | VERIFIED |
| `+0x8460` | u8 | game over processed | VERIFIED |
| `+0x846c` | i32 | engine index | VERIFIED |
| `+0x8478` | u8 | first blood raised this round | VERIFIED |

The NUMBER operand readers agree with this layout: player numbers at Megalo
state `+0x19c+i*0xf0` (= `G+0x344+0x14`), team numbers at `+0x10a4+t*0x58`
(= `G+0x1244+0x1c`), global numbers at `+0x78` (= `G+0x234`), with the
Megalo state at `G+0x1bc` (sim `0x404620`). VERIFIED.

Per-player Megalo state, relative to `G+0x344+i*0xf0`: `+0x00` 4 objects,
`+0x10` teams, `+0x14` 8 numbers, `+0x34` timers, `+0x44` player variable,
`+0x48` net countdown, `+0x58` navpoint state, `+0x64` shape, **`+0x75` team
override** (the script-set team, see Teams), `+0x78` objective text, `+0x88`
icon caption, `+0x90` objective icon, `+0x98` co-op spawning byte, `+0x9c`
shape visibility, `+0xa4` shape owner, `+0xa8` applied trait count, `+0xb0`
applied trait list (16). Writers VERIFIED; field names INFERRED from the
actions that write them.

`megalo_objects` element (0x94, made by sim `0x3f5bf0`): `+0x02` spawn
fireteams (action 14), `+0x03` pickup priority (action 44), `+0x04` waypoint
record (icon `+0xa`, priority `+0x14`, timer `+0x15`, minimum and maximum
distance `+0x16`/`+0x17`, from actions 5-8), `+0x1c` pickup permission
(action 12), `+0x24` spawn permission (action 13), `+0x2c` shape visibility,
`+0x34` shape owner, `+0x38` object handle, `+0x3c` 4 objects, `+0x4c`
teams, `+0x50` numbers, `+0x70` timers, `+0x84` net countdown, `+0x88`
progress-bar visibility and `+0x90` its timer (action 15). VERIFIED from the
executor cases. A new element allows pickup by everyone.

## Teams

### Who puts a player on a team

The player configuration is 0x90 bytes: a 0x68-byte client part and a
0x28-byte host part (decoders sim `0x514190`, `0x514590`).

| Config | Field | Status |
|---|---|---|
| `+0x28` | appearance (0x3c bytes); species at `+0x2c`, clamped 0-2 and copied to `P+0xdc`; armour customization pairs | VERIFIED |
| `+0x66` | **desired team** (the client's preference), u5 minus 1 | VERIFIED read; name INFERRED |
| `+0x88` | **team**, u5 minus 1; becomes `P+0xad` | VERIFIED (disassembly of `0x1823c0`; the decompiler shows `+0x48`, which is wrong) |
| `+0x89` | the host's assignment scratch | VERIFIED |

The host's session layer assigns teams in sim `0x4bab20` (inputs from
`0x4ba330` and `0x55b2c0`: the running variant's teams flag and enabled
team count):

- teams off: team = player slot index (0-15);
- teams on: a valid desired team replaces the current assignment; unassigned
  players join the candidate team with the fewest members, lowest index on a
  tie; at least two teams are kept as candidates. Nobody is ever moved after
  joining (no caller passes the "reassign all" mode).

The result reaches each simulation as player-update message 9 (sub-type 3
add, 4 update), through `0x5468c0` → `0x4db920` → `0x4feac0`, and at game
start through the options' player list (`0x55e1c0` copies 16 x 0xb0
entries; `0x20f530` creates the players). VERIFIED, except that the session
player list `0x55e1c0` copies is the same membership data (INFERRED).
MJOLNIR's lobby writes no team, so every player is balanced over teams 0
and 1 in join order (INFERRED: no exe path writing the membership team was
looked for).

**The only writer of `P+0xac` and `P+0xad`** is sim `0x1823c0` (byte stores
at `0x1827be`, `0x1827c6`; a scan of every store to those offsets found no
other player-array writer):

| Mode (`GG+0x10`) | `P+0xac` | `P+0xad` |
|---|---|---|
| 1 campaign | 1 | config `+0x88` |
| 2 Firefight | 1, 7 or `0xff` by species or the variant's model choice | config `+0x88` |
| **3 multiplayer** | **`0xff`** | **config `+0x88`** |
| other | `0xff` | `0xff` |

VERIFIED. `P+0xac` is the campaign allegiance (`EBlamAllegianceTeam`, where
1 is Player and 7 CovenantPlayer); species drives it only in Firefight.

A team change in `0x1823c0` (engine present, teams on, not a type-4 client)
kills the player's unit, raises the respawn delay, zeroes the player's round
score, recomputes team presence and both teams' scores, and raises
`player_switched_team` (`0x68000b`). VERIFIED.

### Team index and designator

`P+0xad` is the **team index**. The engine reasons with the **designator**
`G+0x1c[P+0xad]` for spawns, object teams and the Megalo `player.team`
operand (slot 53). Scores, colours and, with `fireteams_enabled` off, friend
or foe use the index. VERIFIED.

Slot 13 (`0x3efae0`) fills `G+0x1c` from each team's initial designator
(`v+0x404+t*0x58`) under the designator switch type (`v+0x3bd` = `o+0x3b9`):

| Value | Rule | At round index 0 |
|---|---|---|
| 0 fixed | the initial designator | as set |
| 1 rotate | follow the previous mapping `G+0x12a` times | identity |
| 2 shuffle | a cyclic shift of the designators in use by `G+0x12a` (not random) | identity |

In a sandbox (Forge) game started under mode 3 the switch is forced to 0.
VERIFIED. Since MJOLNIR ends a match at the first `round_over`, round index
0 is the only one played and the switch never acts.

Two teams sharing a designator are both credited by Megalo's team score
action, which adds to every team index whose designator matches (action 1,
`0x41c080`). VERIFIED.

### The variant's team options

| Option | Store | Effect in CU4 | Status |
|---|---|---|---|
| team scoring | `o+0x734` | `0x2b0180` passes it to slot 2 on every player score change and team change: 0 sum, 1 minimum, 2 maximum of members' scores, 3 team score only from scripts | VERIFIED code; names INFERRED |
| team species | `o+0x3b8` | spawn representation through `0x187980` → `0x187a90`: 0 the player's choice, 1 Spartan, 2 Elite, 3 per team (`+0x45`), 4 Elite for designator 1. CU4's globals hold three representations: spartans, elite, monitor_editor | VERIFIED; whether Unreal can draw a player as the campaign Elite is untested |
| designator switch | `o+0x3b9` | as above | VERIFIED |
| team changes | `o+0x2fa` | read only by `0x20c230`, a "may this player change team" predicate on a session path; the host's assignment ignores it | VERIFIED |
| fireteams enabled | `o+0xf83e` (variant vt+0x40) | on: condition 7 is true for designators 0 and 1, slot 54 compares designators, slot 4 adds teammate HUD entries | VERIFIED |
| per team | 8 x 0x58 at `o+0x3bc` | flags (bit 0 enabled, bit 1 primary colour override, bits 2 and 3 secondary and text INFERRED), name table, initial designator, model override `+0x45`, primary `+0x48`, secondary `+0x4c`, text colour `+0x50` (0x00RRGGBB), fireteam count | VERIFIED offsets (`v`-relative here: `+0x48` is `v+0x408+t*0x58`) |

### Teams set by a script

Megalo's team setter (sim `0x41fd80`) writes `player.team` (kind 4) through
`0x408b20` into the per-player override `G+0x3b9+i*0xf0`, and `object.team`
(kind 5) through `0x4089b0`. VERIFIED.

- **Team header** (teams on): slot 53 ignores the override, so a script
  cannot move a player to another team. Writing `object.team` on a player's
  own biped writes only the same override (`0x4089b0` returns before the
  biped's own team).
- **Free-for-all header** (Infection, Juggernaut): slot 53 returns the
  override, so enemy checks, spawn filtering and `player.team` reads follow
  the script's teams. `P+0xad` stays the slot index. Change colours ignore
  teams in this case (`0x182cb0` passes no team), so a script-set team shows
  only through the forced-colour trait.

### Team colours inside the simulation

| Step | Sim | What | Status |
|---|---|---|---|
| lookup | `0x21c320(out, v, index)` | the variant's own colour only when teams are on and the team's flags have bits 0 and 1; else, in Firefight, `firefight_globals`; otherwise `multiplayer_globals` universal team colours (11: red (0.677, 0.027, 0.027), blue (0.041, 0.178, 0.604), green, orange, purple, gold, brown, pink, white, black, olive); default (1.0, 0.41, 0.7). Callers pass a team index | VERIFIED |
| player | `0x2b3710` | appearance colours, then primary and secondary = team colour when a team is passed; then three overrides: the forced-colour trait (byte `+0x24` of the trait block, values 2-13), the aura (`+0x23`: blend, darken, brighten), and up to three objects attached to the unit whose tag flags have `0x10000`/`0x20000` | VERIFIED code; trait names INFERRED |
| unit | `0x182cb0` | copies `P+0xac`..`+0xad` to `D+0x1ba`; always writes change colours 0-3 from `0x2b3710`, passing the team only in mode 3 with teams on; slot 30 re-runs it every tick | VERIFIED |
| object | `0x66bf30` | change colour 0 = the map-variant colour index, else the owner team's colour (`0x408ba0`; grey 0.5 for neutral or none) | VERIFIED |
| gate | `0x4089b0`, `0x401a30`, `0x409820` | every non-biped object with a multiplayer block is recoloured on a team change; a biped only when `D+0x100` bit 3 is set, which object creation sets from placement flag `0x800`, which Megalo's Create Object always sets | VERIFIED |
| render cache | `0x5a9520` → `0x4586e0` | each colour is also packed as `0xffRRGGBB` into the "cached object render states" (`[TLS+0x218]`, 1024 x 0x1e8, `+0x1c8`..`+0x1d4`) | VERIFIED |

MJOLNIR's variants write team flags 1 and zero colours
(`crates/blam-megalo/src/variant.rs:838-849`), so every lookup falls back to
`multiplayer_globals`. Bungie's variants do the same (flags 1, colours
`0xffffffff`). VERIFIED. None of these colours reaches Unreal (see The host
interface).

## Objects: ownership, carriers, the multiplayer block

| Field | Where | Writer / reader (sim) | Status |
|---|---|---|---|
| type | `D+0x8e` | | VERIFIED |
| parent | `D+0x14` | sent to Unreal as the creation record's parent | VERIFIED |
| map-variant placement index | `D+0x1c` (u16, < 651) | `0x66bf30`, `0x32f940` | VERIFIED |
| model variant index | `D+0xea` | `0x5a7d10` / `0x5a7d90` | VERIFIED |
| Megalo-created | `D+0x100` bit 3 | `object_new` `0x5a0fc0` from placement flag `0x800` | VERIFIED |
| `megalo_objects` index | `D+0x148` | `0x3f5bf0` | VERIFIED |
| change colours | count `u16 D+0x178 / 0x18`, data at `D + u16 D+0x17a` (current, then render copies; 12-byte RGB) | `0x5a9520` | VERIFIED |
| multiplayer block | `D+0x182` (u16 offset) | everywhere | VERIFIED |
| carrier of a weapon or equipment | `D+0x1a4` (a unit) | Megalo action 19 | VERIFIED |
| unit's team copy | `D+0x1ba` (`P+0xac`), `D+0x1bb` (`P+0xad`) | `0x182cb0` | VERIFIED |
| unit's player | `D+0x1bc` | `0x4088d0`, action 19 | VERIFIED |
| boundary shape | `MP+0x00`..`+0x10` (kind at `+0x10`: 1 sphere, 2 cylinder, 3 box) | `0x32f940`, `0x5b3220`, `0x309a10` | VERIFIED |
| multiplayer object type | `MP+0x11` (15 spawn location, 16 respawn zone, 21-24 fireteam respawn zones, 25 safe volume, 26 kill volume) | `0x307d10`, `0x41cd90` | VERIFIED |
| flags | `MP+0x12` (u16; bit 2 initial spawn, `0x4000` zone disabled) | `0x32f940`, `0x5b3220`, action 82 | VERIFIED |
| symmetry | `MP+0x17` | `0x32f940` | VERIFIED |
| **owner team** | `MP+0x19` (i8; 8 neutral, -1 none) | set by `0x66af70`, read by `0x4088d0` | VERIFIED |
| spawn order / number | `MP+0x1a` | `0x2f84e0`, `0x424460` | VERIFIED |
| spawn weight / random bias | `MP+0x24` / `MP+0x28` | `0x2f77a0` | VERIFIED |
| label list links | `MP+0x44+4*label` | `0x409820`, `0x409980` | VERIFIED |
| label index | `MP+0x84` (into the map variant's labels) | `0x4246a0` | VERIFIED |

The owner-team getter `0x4088d0` returns the player's team (slot 53) for a
unit with a player, else `MP+0x19`. The setter `0x4089b0` writes the
per-player override for a unit with a player, returns early for a player's
own biped, else calls `0x66af70`, which writes `MP+0x19` (no-op when
unchanged), runs slots 51 and 52, recolours, and marks the object for
replication (`0x4d21b0(obj, 0x200)`). VERIFIED.

A native reader can follow the same arithmetic on the sim thread:
`crates/blam-live/src/world.rs` reads object datums only up to `0x178`
(`DATUM_HEAD`); reading to `0x1c0` would give `+0x182`, `+0x1a4` and
`+0x1bc`. INFERRED (not built).

## Labels and map objects

- **Filters** ("labels") live at `v+0xe4e4` (count `v+0xe4dc`), 0x10 each:
  `+0` label string index (-1 none), `+4` object type, `+8` number, `+0xa`
  team (9 = any), `+0xb` flags (bit 0 type, bit 1 team, bit 2 number).
  VERIFIED (`0x424460`, `0x401300`).
- An object matches when type, team (`MP+0x19`), number (`MP+0x1a`) and
  label agree. The label compares **by name**: `MP+0x84` indexes the map
  variant's label offsets (`mapvar+0x12f8`) into its string data
  (`mapvar+0x2f4`), compared over 32 characters (`0x424710`) with the
  variant's string. A filter with no label matches any. VERIFIED
  (`0x4246a0`).
- The map variant (`0x32b600()`) exists only in mode 3. The validator
  `0x40a310` interns each filter's name into the map variant's string table,
  bounded at 0xfff bytes. VERIFIED.
- Map-variant placements: 0x4c bytes each at `mapvar+0x14fc`, at most 651:
  `+0x30` shape, `+0x41` number, `+0x43` multiplayer object type, `+0x44`
  label index, `+0x46` flags, `+0x47` team, `+0x48`/`+0x49` type data,
  `+0x4a` colour index. VERIFIED (`0x32f940`, `0x66bf30`). The map variant
  is built from the scenario's placements, keeping only tags in its map
  variant palettes ([megalo_engine.md](megalo_engine.md)).
- A scenario placement's multiplayer data carries everything Bungie's
  labels use: Megalo label, symmetry, owner team, spawn order, quotas,
  spawn flags, boundary shape and natural respawn weight
  (`scenario_multiplayer_object_struct` in `defs/hce/tag-definitions.json`).
  VERIFIED.
- Labelled objects are kept in per-label linked lists (heads `G+0x155c`,
  links `MP+0x44+4*label`), updated on create (slot 49), placement
  (`0x32f940`), team change (slots 51, 52) and delete (slot 50). VERIFIED.

**"For each object with label" and deletion** (runner `0x39ed40` case 5):
the next link is read before the body runs, and objects flagged as being
deleted are skipped. VERIFIED. So:

| Case | Outcome |
|---|---|
| delete the current object | safe; later `current_object` references in the same body resolve to nothing |
| delete the next labelled object | the pass ends early this tick |
| create a labelled object | linked at the head, not visited this pass |

## Spawning

| Step | Sim | What | Status |
|---|---|---|---|
| spawn loop | `0x185b80` | per player | VERIFIED |
| search | `0x2f77a0` | collects candidates, scores them (`MP+0x24 + MP+0x28` plus influencers), treats MP type 15 with `MP+0x12` bit 2 as initial spawns, sorts, takes the first that fits the biped (`0x2f7290`) | VERIFIED |
| candidates | `0x2f84e0` | scenery with a multiplayer block, in four passes on team (slot 53 against `MP+0x19`) and `MP+0x1a` against the player's fireteam `P+0x4a4`; neutral (8) points serve everyone | VERIFIED |
| influencers | `0x307d10` | respawn zones (MP type 16) for everyone and fireteam zones (21-24) for that fireteam, filtered by team, skipped when `MP+0x12` bit `0x4000` is set; enemies, allies and recent deaths; at most 16 zones | VERIFIED |
| zone shape | `0x309a10` | team `MP+0x19`, weight `MP+0x24`, shape `MP+0x10`; no shape, no influence | VERIFIED |
| random bias | slot 105 | re-rolls `MP+0x28` each tick from `multiplayer_globals` | VERIFIED |
| respawn object | actions 60 and 61 → `0x1974d0` | a team's or player's primary respawn object | VERIFIED |

A player spawns only at scenery of MP type 15; the scenario's starting
locations are not used ([megalo_engine.md](megalo_engine.md)). Team spawns
need each point's owner team to be the team's designator. Respawn zones work
when a scenery object of MP type 16 with a shape exists (placed or created
by a script). Danger zones (type 20) pass the type test but not the iterator
filter, so they do nothing. VERIFIED.

Actions 13 and 14 (spawn permissions and fireteams) apply only to objects
whose MP type is **not** 15: `0x41cd90` returns false for a player spawn
location, true for any other object or one with no multiplayer block.
VERIFIED (read 2026-10-21). They target objects used as respawn objects
(INFERRED).

**Object Out Of Bounds** (condition 8, `0x424150`) is true inside an MP kill
volume (type 26) or outside every MP safe volume (type 25), inside a
scenario kill trigger or outside every scenario safe zone, or against a
structure design's soft-kill ceiling. Converted maps have none of these
(Blood Gulch: no kill triggers, no safe zones, designs not loaded), so it is
always false there unless a level or script adds volume objects. VERIFIED.

## Incidents

### The pipeline

| Step | Sim | What | Status |
|---|---|---|---|
| raise | `0x2f4e90(name)`, `0x2f4510(name, record)` | engine code | VERIFIED |
| raise from Megalo | actions 75/76 → `0x41df50` | takes the n-th incident definition (`0x36b5d0`/`0x36b6a0`: globals `incident global properties` → definitions → incidents; the walk stops at the count, so a large index cannot read out of bounds, though which incident it then posts is undefined) and **skips any whose name string id is in `[0x67ffff, 0xd00070]`** (`0x41e11b`) | VERIFIED |
| filter | `0x2f4510` | drops an incident whose definition disallows the current game mode (`0x406cf0`); queues it at `[TLS+0x68]+0x2c20` (0x24 per entry) and expands derived incidents | VERIFIED |
| flush | `0x2f3b90` → `0x2f36f0` | slot 61, each entry, slot 63 | VERIFIED |
| dispatch | `0x2f36f0` | when `[TLS+0x68]+0x12b84` is set: straight to Unreal. Otherwise, unless a type-4 client: the 256-entry ring (`+0xf748`, 0x34 each), replication through `0x2f61b0`, game reaction `0x2f1560`, campaign or Firefight scoring `0x2d1400`, statistics `0x3779b0` | VERIFIED |
| drain | `0x2f6980` | after 0.15 s (2 s for "use long delay" definitions); at once on game over | VERIFIED |
| to Unreal | `0x2f38e0` → `0x406560` | `host = 0xcdc0()`, `sink = host->vt[0xb8]()`, `sink->vt[0x20](record)`, then the definition's responses. Nothing is delivered when `0xcdc0` returns null | VERIFIED |

The refused range holds every engine-reserved incident (`kill` `0x680000` to
`0x680071`, `recharge_health` `0x680040`, and every `0x70xxxx` key). Megalo
can raise only the tag-defined incidents (`flag_grabbed` `0x825d`,
`lap_complete` `0x82c5`, ...). The 123 incident indices Bungie's variants use
have the same names in CU4's `game_incident` (418 entries), and none is
refused. Incidents the engine raises itself include `kill`, `death`,
`suicide`, `kill_betrayal`, `guardian_kill`, `player_quit`,
`player_joined`, `player_switched_team`, `round_over` (`0x68001b`), the
time warnings `0x68001c`-`0x680021`, `game_over` (`0x680022`), `first_blood`
(`0x680024`), `player_spawn` (`0x680026`) and `pre_game_over` (`0x68005b`).
VERIFIED (ids from `defs/hce/string-ids.json`).

### Which machines hear an incident

Incident definitions carry flags (`globals\incident\*` tags): bit 0 never
network, bit 1 always network to everyone, bit 2 long delay, bit 3 force a
game-engine event display in campaign. **No CU4 definition sets bit 0**
(651 definitions in six tags). Bit 1 is set on 152, all campaign,
collectible or activity incidents. VERIFIED. So every multiplayer incident
(`kill`, `death`, `flag_*`, `round_over`, `game_over`) is sent only to its
"interested parties" (`0x2f6390`: the incident's effect player, or players
an audience response matches). That is why fireteam clients see few
incidents.

A type-4 client receives host incidents two ways: the simulation event
"incident" (handler `0x596aa0`, which fills the ring with the client's own
counters, drained by `0x2f6980`) and message `0x2d` (element 6, sub-type 10:
each record is raised with `+0x12b84` set, so it goes to Unreal at once).
Incidents a client raises itself go nowhere. VERIFIED.

A native fix for a client kill feed would be an override of `game_incident`
setting bit 1 on the feed's incidents. INFERRED, untested.

### On the host side

`BlamIncidentSubsystem` (a GameInstance subsystem; StaticClass exe
`0x7b05990`) registers exe `0x7b96d10` with the sim's callback; it builds an
`FBlamIncident` and broadcasts `OnIncident` (`+0x78`). VERIFIED.

| Sim record | `FBlamIncident` field |
|---|---|
| `+0x00` string id | `Name` |
| `+0x04` | `CausePlayerAbsoluteIndex` |
| `+0x08` object | `CauseObjectActor` (through the object-to-actor map; null when -1) |
| `+0x0c` | `EffectPlayerAbsoluteIndex` |
| `+0x10` object | `EffectObjectActor` |
| `+0x14` string id | `CustomString` (0 = none) |
| `+0x18` **u16** | `CustomValue`, zero-extended (a sim -1 arrives as 65535) |
| `+0x1a` / `+0x1b` | `DamageReportingInfo.Modifier` / `.Type` |

There is **no team field**. A team reaches Unreal only as `CustomValue` or
through an actor's team component. VERIFIED.

`BPC_MeteoriteIncidentHandlerComponent` (the game state's incident handler)
switches on the name (VERIFIED, `mjolnir ue disasm`):

| Incident | Handling |
|---|---|
| `kill`, `kill_betrayal` | `HandleKill` |
| `death` | `HandlePlayerDeath`, then a music event |
| `player_quit` | a music event |
| `game_won`, `game_lost`, `player_spawn` | nothing |
| any other name | `HandleSkull`, `HandleTerminal`, `HandleAchievement` (each prints only in a debug mode), then `HandleHudBannerMessage`, which posts a HUD banner when a banner DataTable row has the incident's name |

So a custom game type's incidents land in the default branch, and their only
built-in effect is a banner for a name the DataTable already lists. They
cannot award achievements. Other subscribers: `BlamPlayerController`, the
gamepad event handler, and the progress and achievement local-player
subsystems (VERIFIED binders). MJOLNIR hooks `OnIncident_Event` from Lua.

## Waypoints, HUD widgets and objective text

What a Megalo script sets stays in the simulation:

| Feature | Sim storage | Status |
|---|---|---|
| waypoints (actions 4-8, 53) | `MO+0x04` record, or the player state for a player's biped | VERIFIED |
| HUD widgets (actions 46-50) | `G+0x2a4`, 4 x 0x28 | VERIFIED |
| objective text, caption, icon (56-58) | per-player state `+0x78`, `+0x88`, `+0x90` | VERIFIED |
| progress bars (15) | `MO+0x88`, `MO+0x90` | VERIFIED |
| boundary shapes (10, 22, 98) | `MP` shape, drawn by slot 29 through `0x66b900`/`0x66ba00` in the owner's colour | VERIFIED; whether anything reaches the screen under Unreal is open |

Slot 26 turns waypoints into the sim's own per-user chud navpoint list
(`0x45f750(user)+0x5f94`, 20 x 0x8c, adder `0x4728b0`), and slot 4 packs
widgets and objective text into the sim's per-user HUD state (`0x753bb0` ←
`0x45f9e0`). VERIFIED. **Neither reaches Unreal.** The per-frame snapshot
the host reads (next section) builds each user's HUD record in sim
`0x1abd0` from the player, the reticle target, the camera and the
HaloScript chud state `[TLS+0x428]`. A scan of the 259 functions within four
calls of the producer found no reference to `[TLS+0x458]`, to the Megalo
decoder or executor, to the engine slots or to `0x753bb0`. VERIFIED.

The navpoints the host draws are the HaloScript `chud_track_*` list:
16 x 0x20 per player at `[TLS+0x428]+0xcd0+p*0xc8c`, written only by
`0x473bb0` and `0x473960` (HaloScript evaluators) and the network apply
`0x580470`. A source entry holds kind, id, position, priority, label string
id and vertical offset; **there is no icon field**. The record entry the
host reads (0x1c bytes) holds id, object handle, position, a priority byte
and a label string id. VERIFIED.

On the host, `AMeteoriteHUD` slot 252 (exe `0x7c79670`) copies that list
into `ScriptedNavpoints` (`+0x440`) and broadcasts
`ChangedScriptedNavpointsDelegate` (`+0x570`).
`HudDataAssetNavpoints.SetScriptedNavpoints` picks a widget from
`ObjectivesNavpointWidgetClassByPriority`, keyed by
`EBlamScriptedNavpointPriority` (Objective, Destination, Recon, Neutralize,
Interface, Hostile, Recover). VERIFIED.

A route for Megalo waypoints would be to mirror them into that list per
player (`0x473960`); they would show with a priority and a label but no
icon. INFERRED, not tried.

## Carry objects (flag, ball, bomb)

- They are weapons. `multiplayer_globals` names the oddball and the bomb;
  there is no flag reference there. VERIFIED.
- **Pickup permission** `MO+0x1c` (action 12), checked by slot 39 from the
  pickup code (`0x5c4570`, `0x60a680`). **Pickup priority** `MO+3`
  (action 44: 0 normal, 1 hold, 2 automatic), read by slots 40 and 41.
  VERIFIED; value names INFERRED.
- **Carrier**: `D(weapon)+0x1a4` → unit → `+0x1bc` player (action 19).
  A carried weapon's waypoint is suppressed (`0x3ff6b0`). VERIFIED.
- **Owner team** is set once by the script when it creates or adopts the
  object, in Bungie's CTF and in MJOLNIR's alike; it stays until the object
  is deleted. VERIFIED from the scripts.
- **The model variant at creation.** Create Object (`0x41c3b0`) uses the
  tag's default model variant (tag `+0x50`) unless its name parameter names
  a variant through the `megalo_string_id_table` (57 entries; none is `red`
  or `blue`). Object creation resolves the variant with `0x5a7d90`; a name
  the model lacks falls back to the default. VERIFIED.
- **What Unreal sees of it**: the mesh-state word the snapshot sends is
  `hlmt.variants[D+0xea].name` (`0x5b3190`), the resolved variant, and the
  meshes follow the region permutation pairs sent with it (see The host
  interface). VERIFIED.
- The model variant reaches clients only in the creation data
  (`0x503140`); no later object update carries it, and `object_set_variant`
  (`0x1b7d10` → `0x5a7d10`) never marks the object dirty. VERIFIED for the
  base object path; the biped-specific path was not read.
- MJOLNIR's flag (`objects\weapons\multiplayer\flag\flag`, cloned from the
  assault bomb, `tools/level/build_ctf_flag.sh:50`) has one change colour
  with permutations `default` (red) and `blue`. The assault bomb model has
  variants `default` and `blue`. VERIFIED (`mjolnir values`).
- Drop on death was not traced.

## Rounds and the end of a game

| Step | Sim | What | Status |
|---|---|---|---|
| new map | `0x2aca30` | engine index from the variant; slot 8 (pregame entry) | VERIFIED |
| round reset | `0x2ad560` | loads `<name>.mglo` when the name buffer (`0x152a7c0`) is set and the variant is Megalo; clears standings; sets the timers (`0x2b0df0`); resets players and the map variant (`0x32f6a0`); team setup (`0x20bc30`: slot 13, presence masks, re-applies every player's configuration); slot 10 (init entries) | VERIFIED |
| update | `0x2b1170` | each tick: timers (`0x2b0f60`), players (slot 30), slot 29 (Megalo), standings, end checks | VERIFIED |
| state machine | `0x2b2520` | state 2 counts `G+0x8458` down, deletes the per-object table's objects and sets the phase `G+0x845c` to 3; state 3 counts down and sets it to 1; on game over raises `game_over` once and flushes incidents | VERIFIED |

End reasons, passed to `0x2afa70(winner, game_over, reason)`:

| Reason | Raised by | Result |
|---|---|---|
| 0 | Megalo End Round (action 21: `0x2afa70(-1, 0, 0)`) | round over |
| 0 or 2 | too few players or teams left (`0x2aea40`; which reason is which was not read) | round over |
| 5 / 6 | a team / a player reached score to win (`0x2b1170`; only when score to win > 0) | round over |
| 7 | the round count (`o+0x2bb`) is reached | game over |
| 8 / 9 | a team / a player won the early-victory count of rounds (`o+0x2b9`) | game over |
| 10 | round index past `0x3fe` | game over |
| 13 | teams on: the team masks disagree, or slot 7 says too few teams | game over at once |

With rounds left, a round over raises `round_over` and every player respawns
on the same map. Under a sandbox variant the game-over branch is skipped
(`0x2b5520` returns the variant's engine type; 1 is sandbox). VERIFIED.

**The time limit only warns.** `0x2b0f60` counts the round timer
(`o+0x2ba` minutes) and raises the `*_remaining` warnings; nothing ends the
round on time, so a script must (Bungie's do, and so do MJOLNIR's). The
sudden-death and grace timers tick in `G+0x138`/`G+0x13c` for scripts to
read. VERIFIED.

**Score to win is the engine's job.** No Bungie Slayer, CTF or King of the
Hill script ends the round on score; their only End Round actions are on the
round timer, sudden death or mode-specific wins. VERIFIED (dumps of the
corpus below).

### When triggers run

| Entry or attribute | Run by | Machines |
|---|---|---|
| pregame (`v+0xe5fc`) | slot 8, new map | all |
| init (`v+0xe5e4`) | slot 10, round start | not on a type-4 client |
| local init (`v+0xe5e8`) | slot 10 | all |
| object death (`v+0xe5f4`) | slot 64 | not on a type-4 client |
| host migration / double host migration (`v+0xe5ec` / `v+0xe5f0`) | slot 79, after a host-migration state import (`0x4fe150`) | distributed types (4, 5) only |
| attributes 0 (normal) and 6 (local), every tick | slot 113 from slot 29 | host (and any non-client type) |
| local (`v+0xe5f8`), every tick | slot 113 | type-4 client only |

Slot 113 runs only while `0x2af760` holds: `G+0x128 == 1` and either a
type-4 client or `G+0x845c == 1`. VERIFIED. The runner (`0x39ed40`) handles
trigger types 0 to 5 through a six-entry table with no bounds check; the
sequencer `0x423a70` applies the conditions. Run Nested Trigger (action 20)
saves and restores the context `G+0x1bc`..`+0x1c4` around the call.
VERIFIED.

## The host interface

### Shell, host interface and the per-frame snapshot

The sim exports only `CreateBlamEngineShell` (sim `0x6980`). The exe
(`0x7b20a70`) builds a host interface (vtable exe `0x14c1657b0`, owner at
`+0x40`) and passes it to the shell; the sim reaches it through `0xcdc0()`
(`[0x2c40028]+0x10`). VERIFIED. Its getters, each a two-instruction exe
function:

| Host vt | Returns | Used for |
|---|---|---|
| `+0xa0` | `[owner+0x70]+0x20` | sound |
| `+0xa8` | synchronization manager `+0x1320` | camera |
| `+0xb8` | `[owner+0x60]` | event sink: HUD text (`+0x0`), first-person animation (`+0x18`), **incidents (`+0x20`)**, chud id changes (`+0x58`), flush (`+0x78`) |
| `+0xc0` | `[owner+0x78]` | file system |
| `+0xd0` | `[owner+0x98]` | first-person manager |
| `+0xe0` | `[owner+0x40]` | host event queue |
| **`+0xe8`** | **`[owner+0x50]`** | **synchronization manager** |
| `+0xf8` | synchronization manager `+0x1330` | HUD records |
| `+0x100` / `+0x108` | | input / profile and controls |
| `+0x150` | `[owner+0x190]` | **the exe's Party network transport** |

VERIFIED (exe `0x7ba1720`-`0x7ba1930`).

**The snapshot is pushed, not read.** Once per sim frame, sim `0x1af290`
calls `syncmgr->vt[0x00](frame)` (resets the write block and points the
exe's TLS slot at it on the sim thread), runs the producer sim
`0xce50(host, syncmgr)` (globals `0x1a870`, objects `0x11950`, players
`0x1bf50`, HUD `0x1abd0`, camera), then publishes with `vt[0x08]`. The exe
keeps three 0x648-byte blocks (`syncmgr+0x12e8`/`+0x12f0`/`+0x12f8`); the
game-thread drain `0x7b258e0` swaps them and installs the read block in the
same TLS slot. VERIFIED.

| Block offset | Content (stride) |
|---|---|
| `+0x10` | creation records (0x68) |
| `+0x20` / `+0x30` / `+0x40` / `+0x50` | transforms / node ranges / node transforms / damage |
| `+0x60`..`+0xf0` | per-type records: biped (0xc8), control, creature (0x14), equipment, giant, machine, projectile, terminal, vehicle (0x338), weapon (0xa8) |
| `+0x100` | mesh state (0x20): model variant name and region permutations |
| `+0x110 + user*0x110` | four per-user HUD records |
| `+0x568`, `+0x620`, `+0x638` | globals, player mask, players |

Scenery, sound scenery, crates and effect scenery get no per-type record.
VERIFIED.

Creation record (0x68), as sim `0x11d20` fills it (VERIFIED):

| Offset | Field |
|---|---|
| `+0x00` | tag index |
| `+0x08` | object handle (the key Unreal uses) |
| `+0x10` | object game-state identifier (u16) |
| `+0x12` | object type |
| `+0x14` | model variant name (`0x5b3190`) |
| `+0x2c` / `+0x30` | parent handle (`D+0x14`) / root ancestor |
| `+0x34`.. | transform (the exe scales position by 304.8 to centimetres and negates Y) |
| `+0x54`..`+0x64` | indices into the transform, node, damage, mesh-state and per-type arrays |

What the snapshot does **not** carry: owner team, change colours, the render
cache, the forced-colour trait (only one "traits differ from default" bit),
Megalo widgets, objective text and waypoints. VERIFIED negative over the
producer's call tree to four levels, and the exe has no 0x1e8-stride walk
over the render cache.

### From a sim object to an actor

- The drain spawns an actor for each new record (exe `0x7a195f0` →
  `0x7a19690`). The class comes from the tag's data asset:
  `AssetReference` (`+0x70`), else `DefaultAssetReference` (`+0x78`)
  (`0x7a23140`). The flag weapon tag names `BP_SkullActor`; the Spartan
  biped names `BP_SpartansBipedActor`. VERIFIED.
- Actors are pooled and pre-created (`Halo.ActorPooling.Enabled` and
  `Blam.Synchronization.PrecreateObjects.Enabled`, both 1 by default). A new
  sim object takes a pooled actor when one of its class is free, then gets
  `BP_OnGameplayStart(VariantName, ObjectGameStateIdentifier)`. VERIFIED.
  Whether a respawn reuses a particular actor depends on the pool
  (INFERRED).
- Components are added by object type (exe `0x7a1a0c0`). Every actor gets
  `BlamObjectSynchronizationComponent` and a mesh-sync component; units
  (`0x1003`) and creatures get **`BlamGameTeamComponent`**; weapons and
  equipment get item and weapon or equipment components and **no team
  component**. VERIFIED.
- `BlamObjectSynchronizationComponent` reflects `BlamObjectIndex` (`+0xf8`,
  the sim object handle), `BlamTagDefinitionIndex` (`+0xfc`),
  `ParentObjectIndex`, `ParentBoneIndex` and
  `BlamObjectGameStateIdentifier` (`+0x10c`), all BlueprintReadOnly and not
  replicated. `BlamObjectIndex` is the key of the exe's object-to-actor map
  (`syncmgr+0x1350`, lookup exe `0x7a13a70`), which incidents, the HUD
  target and navpoints use. VERIFIED.
- Units add `BlamUnitComponent.GetControllingPlayerDatumIndex()` (`+0x2d0`).
  Player states carry `BlamAbsolutePlayerIndex` (replicated).
  `ABlamPawn.GetBlamObjectActor()` (exe `0x7b0b0a0`) returns the actor of
  the pawn's own unit. VERIFIED.

### The team component

`UBlamGameTeamComponent` (0xb0 bytes, no reflected properties, one function
`GetGameTeamString`, exe `0x79ee780`) holds two bytes, written from the
snapshot by exe `0x7a18f30` whenever an update's state bit is set and at the
first update:

| Byte | Enum | Source | In a Megalo game |
|---|---|---|---|
| `+0xa8` | `EBlamAllegianceTeam` | unit `+0x1ba` = `P+0xac` | `0xff` (None) for every player |
| `+0xa9` | `EBlamMultiplayerTeam` (Red 0, Blue 1, Green 2, Yellow 3, Purple 4, Orange 5, Brown 6, Grey 7, None 255) | unit `+0x1bb` = `P+0xad` | the team index; the slot index 0-15 in free-for-all |

VERIFIED end to end (sim `0x11d20` stores the unit's two bytes into a stack
structure at `+0x70`/`+0x71`; exe `0x7a0f7a0` copies it to record `+0x10`;
exe `0x7a18f30` copies record `+0x80`/`+0x81`). Each machine fills it from
its own simulation; it is not replicated by Unreal.

Consequences, VERIFIED in code:

- `GetGameTeamString()` reads `EBlamAllegianceTeam::None|EBlamMultiplayerTeam::<team>`
  in a Megalo team game. A byte with no enum name (8-15 in free-for-all)
  prints as None. MJOLNIR's Lua compares only the second half, which is
  right.
- `BlamSynchronizationHelperLibrary.ActorTeamIsEnemy`/`Ally`/`Friendly`/
  `Traitor` index `BlamGameAllegianceSubsystem` tables by the allegiance
  byte. With `0xff` on both sides, `ActorTeamIsEnemy` is true for
  teammates and the others false; the native reticle never rates a
  teammate friendly. This holds whenever that subsystem exists in a match
  (INFERRED that it does). Do not use these functions for player teams in
  Megalo games.
- The snapshot's HUD record carries the sim's own reticle friend bit
  (record `+0x28` bit 0, from the mode-aware `0x27e6d0`).

### Appearance: model variants and permutations, not colours

The mesh sync (exe `0x7a186e0` → `0x7a20850` → `0x7a21080` → `0x7a26040`)
mirrors the sim's mesh-state record onto every `BlamMeshSynchronization`
component:

1. word 0 becomes the variant name (`+0x154`, `GetVariantName()`) and
   `OnVariantChanged` fires;
2. each (region, permutation) pair is matched against `RuntimeRegions`; on
   any change the assets are loaded, asynchronously by default
   (`Blam.MeshSynchronization.EnableAsyncLoad` = 1);
3. the completion reuses or creates mesh components, applies the
   permutation's `MaterialOverrides`, rebuilds static plates, and fires
   `OnRegionsChanged` last.

VERIFIED. A permutation missing from `RuntimeRegions` leaves its region with
**no mesh** (no fallback); a missing region is skipped. VERIFIED, except
that the slot that removes the components is `DestroyComponent` (INFERRED).
The meshes follow the pairs, not the variant name: a variant change with
identical permutations rebuilds nothing.

Nothing read in the exe moves a change colour: there is no change-colour
string in the exe, no walk over the render cache, and nothing in the
snapshot. The shipped
`MPC_CVW_TeamAssignment` collection (eight team colours) is imported by none
of the 2,912 packages scanned under `characters/Spartans/`, `Vehicles/`,
`weapons/` and `HaloMaterialLibrary/`. VERIFIED. So a team colour on screen
needs a team-specific model variant or permutation selected in the sim, or
code that reads the sim and paints.

Player armour is a model variant chosen in the sim from the player's
customization (`0x2f2730` → `0x182ef0` → `0x5a7e60`, re-run by `0x1823c0`
on every configuration update). Every armour but Mk V Classic (`og_001`)
draws 11-17 static-mesh plates and a static-mesh helmet over the body, each
with the coating's material. The Spartans model's body region also carries
18 unused `og_<colour>` permutations that no variant and no `RuntimeRegions`
lists. VERIFIED (`mjolnir ue get`, `mjolnir values`).

### What the host reflects about game modes

`BlamGameEngineCampaignVariant` is the only variant class (flags, a remix
seed, four per-player trait blocks, four XUIDs); `EBlamGameEngineType` is
None or Campaign. There is no reflected multiplayer variant, Megalo, score
or team-score class. Team queries are reflected (`GetGameTeamString`,
`ActorTeamIs*`). `BlamGameEngineTimer` is reflected and unused. VERIFIED.
A custom game type therefore has no Unreal-side representation: the host
draws only its consequences (objects, variants and permutations, the HUD
record, incidents).

## Fireteam clients: who runs the simulation

Every fireteam machine runs its own simulation, and the simulations talk
Reach's distributed protocol:

| Piece | Where | Status |
|---|---|---|
| transport | exe `0x7b21cf0` builds it (vtable exe `0x14c11b418`: open, ready, send, receive) at `owner+0x190`; sim `0x4c2d80` installs it from host vt `+0x150` | VERIFIED |
| wire | PlayFab Party endpoints 0 (in-channel) and 1 (out-of-band); endpoint ids replicated on `BlamNetworkPlayerStateComponent` | VERIFIED |
| fallback | the sim's own Winsock sockets (ports 2000/2001) only when no transport is installed (`0x532d40`) | VERIFIED |
| receive | `0x4c7350`: message `0x29` → the world's queues (`0x500910`), drained to `0x4feac0`; `0x2d` incident batches; `0x2c` force a resync (slot 82) | VERIFIED |
| evidence | `ue4ss/Mods/MJOLNIRLobby/native/fireteam.log`: the sim session held two peers, state 6 (host), session game mode 3, life cycle 3 (in game) | VERIFIED (log) |

The `net_*` console commands are stubs; the network layer is not.

**What the host sends and how a client applies it:**

| Data | Path | Status |
|---|---|---|
| engine state (`G+0x128`, team masks, designators) | engine-globals entity, slot 85 | VERIFIED |
| Megalo global variables (by network priority 1, 2) and HUD widgets | `custom-engine-globals` entity (vtable sim `0x8c2ff0`), decoder `0x56fbc0` | VERIFIED |
| per-player Megalo variables | `game-engine-player` entity (`0x8c3b10`), decoder `0x573100` | VERIFIED |
| team Megalo variables | `game-engine-megalo-team` entity (`0x8c3c00`), decoder `0x576e70` | VERIFIED |
| scores (`G+0x32c0`) | `game-engine-statborg` entity (`0x8c3cf0`), apply `0x577520` writes the client's own score block | VERIFIED |
| owner team and multiplayer properties | object state bit 9 (`0x508a10`), applied by `0x504ea0` → `0x5b3220` → `0x66af70` | VERIFIED |
| model variant | creation data only (`0x503140`) | VERIFIED (base object path) |
| player configurations (team, appearance) | message 9 → `0x4feac0` → `0x1823c0` | VERIFIED |
| incidents | simulation event and message `0x2d`, to interested parties only | VERIFIED |
| the variant itself | session parameter `game-variant` (`session+0x6340`, sent in 0x200-byte chunks), set at launch and republished by the host; every peer's options builder copies it | VERIFIED |

Variables with network priority 0 are never sent. VERIFIED.

**Every machine needs the same variable declarations.** Each entity decoder
walks the **receiving** machine's variant: its declaration counts, network
priority bytes (`v+0xe328`, `v+0xe3b8`, `v+0xe470`) and widget count
(`v+0xe4d0`). There is no identity check. A mismatch shifts the bit cursor:
a decode failure at receive time drops the rest of the packet (`0x542e00`),
an over-read at apply time drops the update (`0x564ac0`), an under-read
applies values to the wrong variables silently. VERIFIED code; consequences
INFERRED. Trigger code is not on the wire.

**Which variant a client runs.** The engine ships the host's variant through
the session parameter, but MJOLNIR then overwrites the live variant on every
machine at the round reset from the locally staged `.mglo` (the loader in
`0x2ad560` has no simulation-type gate). Whether the host republishes after
its own file decode early enough for a joining client to copy the file's
variant is open. VERIFIED code; ordering open.

**What runs where**, assuming the host is type 5 and clients type 4:

| Machine | Runs | Receives |
|---|---|---|
| host | every normal and local trigger, init, object death, the engine's end checks, scoring, team assignment | player configurations |
| client | its own `local` entry point, local init, pregame; each player's configuration when an update arrives (`0x1823c0`, which re-picks the armour variant) | everything in the table above |

So a hub game type's rules run on the host, its per-player presentation
belongs in the `local` trigger, and every machine must hold a variant with
identical declarations, priorities and widget count.

## The safety envelope of a variant

CU4 trusts the variant almost everywhere. The decoder enforces none of the
stores' sizes, and the executor checks few indices (VERIFIED, full table in
[megalo_variant_format.md](megalo_variant_format.md#limits-a-validator-must-enforce)).
The worst cases:

- the main string table's data is written into a 0x4c00-byte buffer with no
  check against that size, past the encoding version and the whole script
  (sim `0x3949c0`, `0x32a620`);
- 5 to 7 HUD widgets overwrite player 0's Megalo state at load
  (`0x40a130`);
- Run Nested Trigger has no index bound and no depth limit; a trigger that
  calls itself overflows the stack (`0x399110` case 20);
- object-type operands index the multiplayer object type list with no bound
  (`0x41c3b0`, `0x421b80`);
- compare operators 6 and 7 and trigger types 6 and 7 jump past six-entry
  tables.

Undefined action types 107-127 are no-ops, every reference value resolves to
a defined slot, the incident index cannot read out of bounds, and action 100
can run only a HaloScript the loaded scenario has. VERIFIED. A hub must
therefore validate every variant before any machine's simulation decodes it;
the validator `0x40a310` checks only the object-type bitset and wipes the
script when it fails.

## MJOLNIR today, read against this map

| Area | What MJOLNIR does | What the map says | Status |
|---|---|---|---|
| engine switch | seven byte patches, the sixth of which fixes the `.mglo` loader (`native/map_registry/mjolnir_map_registry.c`) | [megalo_engine.md](megalo_engine.md) | VERIFIED |
| game types | Slayer and CTF from `crates/blam-megalo`; Team Slayer, KOTH and Oddball exist only as names in UI tables | | VERIFIED |
| teams in the variant | flags 1 for teams 0 and 1, colours 0, designator = index, `fireteams_enabled` 0, team scoring 0 (`variant.rs:838-849`) | colours fall back to `multiplayer_globals`; designators equal indices | VERIFIED |
| who sets teams | nobody; Lua reads `BlamGameTeam` | the host's session (`0x4bab20`) | VERIFIED |
| CTF flag colour | Lua guesses each new `BP_SkullActor` actor's team from stand distance and recent flag incidents | flags have no team component; the deterministic sources are the model variant (`GetVariantName`, needs a per-team flag tag) or `MP+0x19` read natively (replicated to clients) | VERIFIED |
| armour colour | Lua swaps skeletal meshes to Mk V and tints them | the plates and helmet are static meshes the swap never touches; pooled actors and the async mesh apply undo or skip the tint | VERIFIED code; on-screen effect INFERRED |
| HUD scores | rebuilt from incidents | the sim's scores replicate to clients (`G+0x32c0`) | VERIFIED |
| game type to clients | the insertion-point slot (8 per map) mapped through Lua tables | the engine ships the variant itself; MJOLNIR's loader then overwrites it per machine | VERIFIED |
| tick counts | `mjolnir megalo write --tick-rate` defaulted to 30 (`crates/blam-cli/src/megalo.rs:93-95`); 60 since 2026-10-22 on branch `work/reach-game-mode-support-2eca91` | the sim runs 60, so in released variants the CTF flag reset and the health-pack respawn last half the stated seconds | VERIFIED static |
| `recharge_health` | borrowed `lap_complete` for health packs | Megalo refuses every `0x68xxxx` incident at `0x41df50`; it is never submitted | VERIFIED |
| rounds | 31 rounds; the match ends at the first `round_over` | designator switching and side swaps never happen | VERIFIED |

## Bungie's variants as ground truth

MCC's Reach variants on this PC (417 Megalo files, 371 distinct payloads)
decode and re-encode bit for bit with CU4's grammar
([megalo_variant_format.md](megalo_variant_format.md)). Read as scripts
(`mjolnir megalo dump`), they show how Reach builds modes (VERIFIED from the
dumps):

- one script per family; sub-variants (One Flag, Neutral Flag, Crazy King,
  Pro, SWAT, ...) are user-option values and header settings;
- state lives in object, player and team variables; branching is a
  subroutine trigger called by action 20 (21,382 calls), because a trigger
  stops at its first failed condition;
- a mode's map contract is its label filters: a label name, a team and a
  "map must have at least" count (CTF needs `ctf_flag_return` objects with a
  team);
- colour comes from the owner team of objects and from the forced-colour
  trait for players (Infection, Juggernaut); no Megalo action sets a colour.

They do not run unchanged on CU4. CU4's `multiplayer_object_type_list`
ships 18 weapons (MJOLNIR adds 18 flag and 19 health pack), while Bungie's
scripts use 49 Reach type indices: a bitset bit past the list wipes the
script (Slayer, KOTH, Oddball, Territories, Assault), and Reach indices 3, 5
and 6 create CU4 weapons (CTF, Headhunter). Trait and loadout weapons index
the list's `weapons` collection and abilities its `equipment` collection
(`0x30c9a0`, `0x30ceb0`), so they need remapping too. VERIFIED. Bungie's
files are Microsoft content: read them locally for comparison, never commit
or publish them or anything decoded from them.

## Corrections to other documents

| Document | Says | Correct | Source |
|---|---|---|---|
| [megalo_engine.md](megalo_engine.md), "How the host picks the engine" and "Quitting from a match" | game mode byte 2 = multiplayer, 3 at the frontend; "a Megalo game running (mode 2)" | 1 campaign, 2 Firefight, 3 multiplayer; a Megalo game runs with 3 (the quit fix is unaffected: it removes the `== 1` check) | sim `0xf650`, `0x55e1c0`, `0x406cf0` |
| [megalo_engine.md](megalo_engine.md), "What still blocks a match" | networking goes through Unreal, not the sim's stubbed `net_*` layer | the `net_*` console commands are stubs; the sims run Reach's distributed protocol over the exe's Party transport | sim `0x4c2d80`, `0x4c7350`, `0x532d40`; exe `0x7ba1930` |
| [megalo_engine.md](megalo_engine.md), the interpreter table | slot 79 is the variable sync | slot 79 imports Megalo state after a host migration; per-tick variables travel in entities (slots 86-91) | sim `0x382480`, `0x4fe150` |
| [megalo_engine.md](megalo_engine.md), "Still inferred" | the kill bit of condition 3 | VERIFIED: slot 62 writes death type 2 for a kill, so bit `1 << 2` | sim `0x3fea10` |
| [`../game_state_reader.md`](../game_state_reader.md) `+0xAD` | 0 red, 1 blue, ... 8 neutral, -1 none | the team index in team games; the slot index 0-15 in free-for-all | sim `0x4bab20`, `0x4feac0` |
| `crates/blam-megalo/src/powerups.rs:30`, [`../ce_map_conversion.md`](../ce_map_conversion.md) line 818 | the simulation never hands `recharge_health` to Unreal | Megalo refuses to submit it; nothing downstream drops it | sim `0x41e11b` |
| `crates/blam-cli/src/megalo.rs:93-95` | 30 ticks per second | 60 | sim `0x208a70` |
| [megalo_variant_format.md](megalo_variant_format.md) before 2026-10-21 | actions 30, 31 and 99 are trigger blocks | only 99; 30 and 31 read a player and a number | decoder `0x39cf20`; the round trip |

## Open, and the live reads that settle it

Every item is a read, and `mjolnir_sim_game_globals`
(`native/lobby/mjolnir_lobby.c`) already finds `[TLS+0x60]` on the
simulation thread.

| Question | Read | Expect |
|---|---|---|
| mode byte in a match | `[TLS+0x60]+0x10` | 3 |
| simulation type | `[TLS+0x60]+0x11` on host and client | 5 / 4 |
| playback, world type | `[TLS+0x60]+0x1da`; `[[sim 0x2c0c978]+0x10]` | 0; 7 / 8 |
| session class and protocol | `session+0x28`; `simulation-protocol` | 2 or 3; 2 |
| tick rate | `[TLS+0x98]+6` | 60 |
| does the session variant alone reach a client | on a client with no staged `.mglo`: the live variant's version (`o+0x5dc0`) and trigger count after the first round reset | the host's file |
| does `BlamGameAllegianceSubsystem` exist in a match | `ActorTeamIsEnemy` on two teammates | true (broken) |
| who writes the membership team | membership `+0x1496`/`+0x14b8`/`+0x14b9` per player on the host at match start | |
| a staged variant decoded and survived validation | version `o+0x5dc0` in {`0x6a`, `0x6b`}, trigger count `o+0x63f4` > 0, an entry point other than -1 (a wipe zeroes the script and sets every entry to -1) | needs a stable locator for `o` |
| do Megalo boundaries reach the screen | set a shape visible to everyone and look | |
| does a respawn reuse a pooled actor; is a carried flag a new actor | log `GetFullName()` in `BP_OnGameplayStart` across respawns, grabs and drops | |
| which variant sid a client's replicated creation passes | log `GetVariantName()` of every flag actor on a client | |
| the client's model-variant path for bipeds | read the biped definition's decode | |
| drop-on-death of objective weapons | trace the unit's weapon drop | |

## Sources

Everything above was read from the CU4 binaries with Ghidra (read only), the
cooked game data through `mjolnir values`, `mjolnir ue get` and
`mjolnir ue disasm`, the CU3 usmap for property layouts, the repository at
`772eca0d`, and MCC's Reach variants decoded by `mjolnir megalo dump`
(2026-10-21). ReachVariantTool's source and its CC0 manual were used for
names only.
