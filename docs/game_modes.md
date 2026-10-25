# Game modes: what runs, what breaks, and how to add more (CU4)

**Status:** 2026-10-21. Section 1 describes what ships at 772eca0d. Sections 2
to 5 are designs and test plans. **Update 2026-10-22:** the two colour fixes
of section 2 and the CLI's 60-tick default are built on branch
`work/reach-game-mode-support-2eca91` (each fix's *Built* paragraph says
where) and untested in game. None of it ships before the user has tested it
in game.
**Binaries:** `HaloSimulation_tag_release.dll` ("sim", image base
0x180000000) and `HaloCampaignEvolved.exe` ("exe", image base 0x140000000),
CU4 (build lock in [`build_lock.md`](build_lock.md)). Every address is an RVA
and says sim or exe.
**Related:** [`re/reach_game_engine.md`](re/reach_game_engine.md) (the full
map of the sim's game-engine layer and how the host consumes it; this document
is the plan built on it), [`re/megalo_engine.md`](re/megalo_engine.md) (the
engine switch and the variant loader, as worked out),
[`re/megalo_variant_format.md`](re/megalo_variant_format.md) (the bitstream),
[`custom_game_types.md`](custom_game_types.md) (the hub design built on
section 5), [`multiplayer_ctf_plan.md`](multiplayer_ctf_plan.md),
[`host_game_settings.md`](host_game_settings.md),
[`multiplayer_hud.md`](multiplayer_hud.md),
[`multiplayer_postgame.md`](multiplayer_postgame.md),
[`ce_map_conversion.md`](ce_map_conversion.md),
[`game_state_reader.md`](game_state_reader.md),
[`hub_architecture.md`](hub_architecture.md),
[`map_distribution.md`](map_distribution.md). The full grammar the codec reads
is `crates/blam-megalo/grammar/megalo_cu4.json`.

## Sources and how to read this

The facts come from a static research pass on 2026-10-21. Nobody launched the
game for it. Nine first reports (engine, UE host, flags, armour, repository
audit, ReachVariantTool and MCC facts, Bungie corpus, grammar, codec) were each
checked by an adversarial verifier, and four follow-up passes then read the
code the verifiers had left open: what the sim publishes to Unreal each frame,
how a fireteam carries a match, what an untrusted variant can do, and how teams
are assigned.

- **Verified** means someone read the code, data or file that shows it.
  **Inferred** means it rests on names, Reach knowledge, analogy, or a chain
  with one unread link; the link is named.
- **Precedence.** Where reports disagree, the verifier's verdict beats the
  first report, a follow-up pass that read the deciding code beats both, and
  the codec's round trip over Bungie's variants beats any reading of the
  bitstream. Section 7 lists what stays open.
- **Reach is a hint, not proof.** Names of Megalo actions, conditions, enums
  and Reach object types below are ReachVariantTool's. Their CU4 wire format is
  verified; their CU4 behaviour is verified only where an RVA is given.
- **Bungie's variants are Microsoft content.** They are read from the user's
  MCC install for comparison and never committed, published or shipped
  (section 4.3). MJOLNIR writes its own game types.

Notation, as in the Megalo docs: `G` = engine globals `[TLS+0x38]`; `GG` = game
globals `[TLS+0x60]`, with the game options at `GG+0x10`; `v` = the running
variant at `GG+0x15f0` and `o = v+4` (variant-format offsets are o-relative);
`P` = a player datum (`[TLS+0x30]`, 0x4b0 bytes each); `D(h)` = an object datum;
`MP(h)` = its multiplayer block at `D(h) + u16 D(h)+0x182`.

## Summary

1. **Two game types run: free-for-all Slayer and CTF.** MJOLNIR's encoder
   writes both. Team Slayer, KOTH and Oddball exist only as names in menu and
   HUD tables.
2. **The engine is all there.** It is Reach's game-engine layer, and every
   Reach mode is data for it. Read statically, a MJOLNIR match runs with the
   options' mode byte 3 (multiplayer) and 60 ticks a second, and the fireteam
   runs Reach's distributed simulation over the exe's Party transport: the
   host is DistributedServer (5) and runs every trigger; a client is
   DistributedClient (4), runs only the variant's `local` trigger and receives
   everything else.
3. **The sim knows every team exactly and paints team colours. Unreal never
   sees them.** A flag's owner team (`MP+0x19`) and a player's team (`P+0xad`)
   are exact and replicate to clients. The sim computes change colours from
   them, but the per-frame snapshot it pushes to Unreal carries no owner team
   and no colour. It carries the model variant, the region permutations and
   the unit team bytes. Both colour bugs come from Lua guessing what the
   snapshot does not say.
4. **CTF flags** are coloured by a guess keyed to the actor, not the sim object:
   nearest stand, then the last incident of either flag, then red. Eleven paths
   pick the wrong team. The deterministic fix is a second flag tag whose
   default model variant is `blue`, read in Lua through `GetVariantName()`. It
   needs no native code.
5. **Custom armour** is a Blam model variant. Every armour except Mk V Classic
   is a body plus 11 to 17 static armour plates and a static helmet. MJOLNIR
   tints only skeletal meshes, so the plates and helmet keep the player's own
   colours over a red or blue body. Timing paths add misses. The fix makes the
   sim choose Mk V Classic for every Spartan in team games (a hook on sim
   `0x2f2730`, on every machine), then tints on the game's own
   `OnRegionsChanged` events.
6. **Other modes.** Team Slayer is a script and nothing else. After it come
   the modes that need a player colour channel (Juggernaut, Infection), then
   carried objects and zones (Headhunter, Oddball, KOTH), then modes whose
   placements must be authored per map (Territories, Stockpile, Assault), then
   Race. The common blockers are a 20-entry object type list, a HUD channel
   for Megalo widgets, objective text and waypoint icons (none reaches Unreal),
   boundary drawing, and MJOLNIR ending every match at the first round.
7. **Proof.** The codec round-trips 417 of 417 of Bungie's Megalo variants bit
   for bit. `mjolnir megalo dump` lists any variant. A local remap would let
   Bungie's own modes run as an oracle on this PC. CU4 enforces almost no
   limits on a variant, so a validator must, before any hub upload. Every mode
   is then checked on two PCs, by the user, before release.

---

## 1. What runs today

### 1.1 The path of a game type

| Step | Where | What | Status |
|---|---|---|---|
| Encode | `crates/blam-megalo` (`variant.rs`, `script.rs`, `ctf.rs`, `powerups.rs`); `mjolnir megalo write --mode empty\|slayer\|tick\|ctf` (`crates/blam-cli/src/megalo.rs:40-50`, `211-250`) | builds the bitstream; Slayer and CTF get a time-limit trigger, and every mode but empty and tick gets CE health packs unless `--no-health-packs` | Verified |
| Release | `.github/workflows/release-mods.yml:109-110` | writes `variants/slayer.mglo` and `variants/ctf.mglo` with `--vehicle-label-pool`; zipped into the signed MJOLNIRLevelLoader | Verified |
| A map's modes | `tools/level/gen_ce_level.py:1331` | `["slayer"]`, plus `"ctf"` when the CE scenario has flags | Verified |
| Menu | `mods/MJOLNIRLobby/Scripts/main.lua:61-67` (`MODES`), `118-128` (`modesFor`) | five names (slayer, team_slayer, koth, oddball, ctf); a mode is offered only if the map lists it and `variants/<id>.mglo` exists, so only Slayer and CTF appear | Verified |
| Host's choice to its loader | Lobby `main.lua:181-186` writes `pending_variant.txt`; `mods/MJOLNIRLevelLoader/Scripts/main.lua:6031-6043` reads it once in the `SetAndBeginCampaign` hook | | Verified |
| Host's choice to clients | the travel URL's insertion point index; loader `GAME_TYPE_SLOTS` (`main.lua:5919`: 0 slayer, 1 ctf, 2 team_slayer, 3 koth, 4 oddball); FIND GAMES joins through `mods/MJOLNIRLobby/Scripts/games.lua:169, 221` | an id missing from the table falls back to the level's own variant (slayer) on clients | Verified |
| Stage | `native/map_registry/mjolnir_map_registry.c`: seven byte patches (table at `1197-1236`); `mjolnir_megalo_variant` (`1324`) copies `native\variant.mglo` to `HotReload\mjolnir.mglo` and writes `"mjolnir"` to the sim's name buffer (`RVA_MGLO_NAME` 0x152a7c0, line 1279) | | Verified |
| Load | sim round reset `0x2ad560` reads `<name>.mglo`, decodes it through variant vtable slot 5 (sim `0x392a40`), validates it (sim `0x40a310`) and clears the name; there is no simulation-type gate, so every machine loads its own file | | Verified |
| Settings | `mods/MJOLNIRLevelLoader/Scripts/variant_settings.lua` patches base-option bits in the staged copy; `mods/MJOLNIRHud/Scripts/variant.lua` reads the score to win and time limit | both stop at user options, script traits or a compressed string table, so any Reach-authored variant breaks them | Verified |

The patch table quotes the start of each patched instruction (`0xf6db`,
`0x55af56`, `0x45b1a3`); `re/megalo_engine.md` quotes the changed byte
(`0xf6dd`, `0x55af5a`, `0x45b1a7`). They are the same three patches.

Game type identity is repeated in at least 13 places (Lobby `MODES`,
`games.lua`, `GAME_TYPE_SLOTS`, `TEAM_GAMES`, `START_EVENTS`,
`vehicle_sets.lua`, the HUD scoreboard and settings tables, `level.rs`,
`gen_ce_level.py`, the hub kit and three hub pages). A new type needs edits in
Lua, Rust, Python and the hub. Verified (repository audit, 2026-10-21).

### 1.2 How the sim runs a MJOLNIR match

| Fact | Where | Status |
|---|---|---|
| Engine index 2 (Megalo) at `G+0x846c`; Megalo vtable sim `0x85dae8`, 114 slots | `current_game_engine()` sim `0x180e70`, table sim `0xbd5210` | Verified |
| The options' mode byte `GG+0x10` is **3** (1 campaign, 2 Firefight, 3 multiplayer) | sim `0xf650` sets pending mode 3 for engines 1 and 2; `0x2060f0` turns it into a session mode; the options builder `0x55e1c0` writes 1 for session mode 1, 2 for session mode 6 and 3 for any other; `0x2069e0` installs the options. The incident filter `0x406cf0` maps modes 1/2/3 to the tag flags campaign, firefight, multiplayer | Verified; one link (the session value `0x55e1c0` reads is the one `0x4c1e10` stored) inferred; live read pending |
| Tick rate **60** | options `+6` defaults to 0x3c (sim `0x208a70`, store at `0x208ab9`), is validated 1..300 (`0x208cb0`) and copied to `[TLS+0x98]+6` at map init (`0x20ff70`). The only immediate 30 or 60 store to such a field is that one. Matches the "about 60 a second" score rise in `re/megalo_engine.md` | Verified statically |
| Simulation type `GG+0x11`: host **5** DistributedServer, client **4** DistributedClient | `0x55e1c0` derives it from the session parameter `simulation-protocol` and "local peer is host": protocol 2 gives 5 or 4. Its only launch-time writer `0x4c1f20` asks engine slot 99, which is `0x47d60` (`mov eax, 2`) in all four engines. A session class `session+0x28` of 1 would force protocol 0 | Chain verified; live read pending |
| The sim's own network protocol is live | sim send `0x532d40` and receive `0x4c7350` go through the transport at `+0x28`, which sim `0x4c2d80` takes from host vtable `+0x150` = exe `0x7ba1930` = the exe's Party transport (`launcher+0x190`). `fireteam.log` shows a sim session with two peers, state 6, mode 3 | Verified |
| Who runs which trigger | per tick: engine update `0x2b1170` -> slot 29 `0x3fdad0` -> slot 113 `0x3fe520`. The host runs every trigger whose attribute is 0 (normal) or 6 (local); a type-4 client runs only the `local` entry point (`v+0xe5f8`). Slot 10 `0x3fd740` runs `init` on the host only and `local init` everywhere; slot 8 `0x3fd550` runs `pregame` at a new map; slot 64 `0x3fe6a0` runs `object death` on the host | Verified |
| Round and game end | `0x2b1170` ends the round when a player (reason 6) or team (5) reaches the score to win; `0x2afa70` turns it into game over on the round count (7), early victory (8, 9) or round 0x3ff (10); `0x2aea40` ends it when too few players or teams remain (0, 2); a team-mask mismatch ends the game outright (13). The round timer only raises warning incidents (`0x2b0f60`): a script must end a round on time | Verified |
| Scores | `G+0x32c0`: player i at `+i*8`, team t at `+0x80+t*8`, each {i16, i16, i16 rounds won}. Replicated to clients by the `game-engine-statborg` entity (apply `0x577520`) | Verified; which of `+0`/`+2` is round or game score inferred |
| Teams | `P+0xad` is the team index (0..7), written only by `0x1823c0` from configuration byte `+0x88`. The host's session membership assigns it (`0x4bab20`): a client's desired team if valid, else the smaller team, two teams seeded; in free-for-all the player's slot index. Megalo reasons with the designator `G+0x1c[P+0xad]` (slot 53 `0x3fee90`); MJOLNIR writes designator = index. `P+0xac` is 0xff in mode 3 | Verified |
| Team score | `team_scoring` (`o+0x734`) through `0x2b0180` -> slot 2 `0x3ef690`: 0 sum, 1 minimum, 2 maximum, 3 none (scripts only); MJOLNIR writes 0 | Verified; names from ReachVariantTool |
| The variant reaches clients twice | the session parameter `game-variant` (`session+0x6340`, sent in 0x200-byte chunks) carries the host's variant and every peer's `0x55e1c0` copies it at game start; then each machine's round reset replaces it with its own staged file | Verified; publish-versus-file ordering open |
| Per-tick Megalo state | global, player and team variables and the HUD widgets travel in three replicated entities whose decoders (`0x56fbc0`, `0x573100`, `0x576e70`) walk the **receiving** machine's own declarations and network priorities. There is no identity check: every machine must hold identical declarations, priorities and widget count | Verified |
| Incidents | Megalo's submit (`0x41df50`) refuses string ids in `[0x67ffff, 0xd00070]`, so a script cannot raise engine incidents such as `recharge_health` (hence the borrowed `lap_complete` in `powerups.rs`). Clients receive only incidents addressed to their players (`0x2f6390`); no CU4 incident definition sets "never network" | Verified |

### 1.3 Slayer

`Variant::slayer` (`crates/blam-megalo/src/variant.rs:558-632`): for each
player, if they died a kill death this tick (killer-type bit 2: the death
record observer, slot 62 at sim `0x3fea10`, writes death type 2 for a kill, 1
for a suicide, 3 for a betrayal and 4 for a quit; verified), fetch the killer and, unless it is the player, add 1 to the killer's score; for
each player, end the round at the score to win. The CLI adds the time-limit
trigger and health packs. The released file is 3,907 bytes: 12 conditions, 19
actions, 7 triggers. Verified.

- Suicides and betrayals do not change the score. Verified code.
- The end-on-score trigger is redundant: the engine ends the round on the score
  to win itself (section 1.2), and Bungie's scripts never write one. Harmless.

### 1.4 Team Slayer does not exist

The CLI's `Mode` (`megalo.rs:40-50`) has no team slayer and the release writes
two files. The UI is ready (Lobby `main.lua:63`, the HUD's Team Slayer tallies
at `mods/MJOLNIRHud/Scripts/main.lua:346-348`, the loader's `TEAM_GAMES` at
`main.lua:2556`). What it needs: teams on, a kill scoring the killer (the team
follows through `team_scoring` 0), and a betrayal rule (killer-type bit 3).
The HUD counts a betrayal for the killer's team; that needs fixing with it.
Verified (audit).

### 1.5 CTF

`Variant::ctf` (`crates/blam-megalo/src/ctf.rs:139-422`), as released: 4,471
bytes, 23 conditions, 67 actions, 22 triggers. Verified.

- **Labels.** Stands `ctf_flag_return` (filter 0), flags `ctf_flag` (1), spawn
  labels `ctf_spawn_red`, `ctf_spawn_blue`, `ctf_spawn_none` (2-4)
  (`ctf.rs:42-62`).
- **Spawns.** At `init` and every tick, the spawn labels' owner teams are set
  to 0, 1 and a team nobody is on (`ctf.rs:329-349`); the sim spawns players
  only at scenery whose owner team matches their designator, or neutral
  (sim `0x2f84e0`).
- **Flags.** Each stand without a flag creates one (object type 18, label
  `ctf_flag`), links it to the stand, copies the stand's owner team, sets pickup
  to enemies, pickup priority automatic, a waypoint for everyone, and
  `TEAM_INDEX` = 1 when the team is blue (`ctf.rs:351-390`, `311-327`).
- **Each flag, each tick.** Get the carrier; a carried flag raises
  `flag_grabbed` once and can score at the carrier's stand; a loose flag raises
  `flag_dropped` once, counts down and resets, or is recovered by touch
  (`ctf.rs:393-405`).
- **End.** Each team at the score to win ends the round (`ctf.rs:408-419`).

Defects beyond colour, from comparing it with Bungie's CTF and from the
follow-up reads:

| Defect | Evidence | Status |
|---|---|---|
| Flag reset and health-pack respawn run at half length | the CLI counts ticks at `--tick-rate` 30 (`megalo.rs:93-95`, used at `226` and `240`); the sim runs 60 (section 1.2). Megalo timers are unaffected: they are declared in seconds and multiplied by the tick rate at init (sim `0x408d00`). Fix: default 60, or move both countdowns to Megalo timers | Verified; the default is 60 on the branch (2026-10-22), so the next released variants count 1,800 ticks for 30 s |
| Waypoint icon 7 is "skull" in Reach's enum; Bungie's flag uses 6 | `ctf.rs:47`; corpus dump | Inferred for CU4; invisible today because no Megalo waypoint icon reaches Unreal (section 2.1) |
| `flag_dropped` and `flag_reset` have no player cause | `Subject::None` (`ctf.rs:242`, `259`) encodes the "all players" group; the submitter `0x41df50` passes non-player subjects through the team resolver `0x41fb90`. Bungie gives the carrier or last carrier | Verified not a player; the team it yields is not traced |
| A capture scores the team only | `ScoreTarget::Team` (`ctf.rs:191`); the player scoreboard never shows captures. Bungie scores the carrier and lets `team_scoring` sum it | Verified |
| No out-of-bounds reset | Bungie resets a flag on `Object Out Of Bounds`; on converted maps that condition is always false (no kill or safe volumes, no soft-kill ceilings; sim `0x424150`, Blood Gulch tag) | Verified |
| A carried flag loses its waypoint | the script keeps the flag's waypoint on everyone; the sim hides a carried weapon's waypoint (`0x3ff6b0`). Bungie moves the marker to the carrier | Script verified; effect inferred |
| Deleting the flag inside the flag label loop | safe: runner `0x39ed40` case 5 reads the next link before the body | Verified (settles an audit worry) |
| A capture in the tick the own flag is recreated | `HOME_FLAG = stand.link` can be none for one tick; a number of an object without Megalo data reads the declaration's default (0, "home") per the evaluator `0x420580` kind 2 | Inferred (whether "no object" takes that path is unread); minor |
| String cap too high | the CLI refuses more than 127 strings (`megalo.rs:298`), but each language row holds 112 offsets (`o+0x738`, stride 0xe0); a 113th string overwrites the next language's row. CTF uses 76 today | Verified |
| Incident indices hard-coded | 108-119 (`ctf.rs:33-38`); CU4's `game_incident` has the same names at every index Bungie uses | Verified |

### 1.6 HUD, announcer and relay

- The HUD rebuilds scores from incidents and never reads the sim's
  (`mods/MJOLNIRHud/Scripts/main.lua:341-348`, `461-480`). Clients hold the
  host's scores in their own `G+0x32c0` through statborg, so a native reader
  could replace the tallies on every machine. Verified.
- Only 3 of the 339 announcer sound references in `game_engine_globals` ship as
  sound tags, and the Megalo sound table has 1 of 95 slots set. Lua voices
  incidents by name through `mods/MJOLNIRLevelLoader/events.json`. Verified.
- The host relays `flag_*` and voiced incidents by `ClientMessage`
  (`main.lua:2425-2465`); a client drops a relayed name once it has received it
  natively (`2487`, `2540`). Verified.
- Any incident name the game's Blueprint handler does not know falls to a
  default branch whose only live effect is a HUD banner, and only when the name
  matches a row of the banner DataTable. Its achievement, skull and terminal
  handlers are debug prints. Verified (`ue disasm` of
  `BPC_MeteoriteIncidentHandlerComponent`).

---

## 2. The two colour bugs

### 2.1 What the engine knows, and what reaches Unreal

| Fact | Where | Status |
|---|---|---|
| An object's owner team is `MP+0x19` | written by sim `0x66af70` (Megalo's team setter `0x41fd80` case 5 -> `0x4089b0` -> `0x66af70`), read by `0x4088d0` | Verified |
| It replicates to clients | object state bit 9: decode sim `0x508a10`, apply `0x504ea0` -> `0x5b3220` -> `0x66af70`. Only the host (type 5) marks it dirty (`0x4d21b0` acts only for type 5) | Verified |
| The sim paints team colours | objects: `0x66bf30` sets change colour 0 from the owner team on every team change; player units: `0x182cb0` sets all four change colours every tick, with the team colour in mode 3 when teams are on; both publish ARGB to the sim's render cache `[TLS+0x218]` (`0x4586e0`) | Verified |
| **None of that reaches Unreal** | the per-frame snapshot is pushed by the sim (`0x1af290` -> producer `0xce50` -> per object `0x11d20`). Nothing within four call levels reads `D+0x182`, `D+0x178` or `D+0x17a`; the forced-colour trait becomes one "traits differ" bit; the exe has no 0x1e8-stride walk of the render cache | Verified negative (follow-up pass over the producer tree) |
| **What does reach Unreal: the model variant and permutations** | mesh-state word 0 is `0x5b3190(object)` = the hlmt variant name at `D+0xea` (the resolved variant, not the stored placement id); the pairs are the current permutation per region. In the exe, `0x7a20850` sets `VariantName` (`+0x154`, read by `GetVariantName`, exe `0x79f2210`) and broadcasts `OnVariantChanged` (`+0x188`); meshes and `MaterialOverrides` follow the permutations (`0x7a21080` -> `0x7a26040`), which broadcasts `OnRegionsChanged` (`+0xb0`) last | Verified |
| The unit's team bytes | `UBlamGameTeamComponent +0xa8/+0xa9` (exe `0x7a18f30`) = unit `+0x1ba/+0x1bb` (sim `0x11d20` stack struct `+0x70/+0x71`, copied by exe `0x7a0f7a0` to record `+0x80/+0x81`) = `P+0xac/P+0xad`. In mode 3, `+0xa8` is 0xff for every player and `+0xa9` is the team index | Verified |
| Only units carry a team component | exe `0x7a1a0c0` adds it (through `0x7a234a0`) for bipeds, vehicles, giants and creatures. Weapons, so the CTF flag, never have one | Verified |
| `ActorTeamIs*` is wrong in Megalo games | exe `0x7b3a270` (`ActorTeamIsEnemy`) and its siblings index `BlamGameAllegianceSubsystem` tables by `+0xa8`; with 0xff, Enemy is true for teammates and Ally false | Code verified; that the subsystem exists in a match inferred |
| From an actor to its sim object | `BlamObjectSynchronizationComponent.BlamObjectIndex` (`+0xf8`, the sim object handle and the key of the object-to-actor map exe `0x7a13a70`) and `BlamTagDefinitionIndex` (`+0xfc`), BlueprintReadOnly, readable from Lua | Verified |

So the only native, sim-driven colour channel Unreal has is an object's model
variant and its permutations. Bungie's modes colour flags, hills and bombs by
owner team through change colours. On CU4 that colour is computed and never
drawn.

### 2.2 CTF flags change colour

**How it works today.** The flag is a weapon tag cloned from the assault bomb,
drawn by the oddball's `BP_SkullActor` (`tools/level/build_ctf_flag.sh:50-55`),
object type list entry 18 (`81-87`). The loader hides the skull and attaches
CE's flag mesh in a team's materials. The team of each new actor is guessed
(`mods/MJOLNIRLevelLoader/Scripts/main.lua:1976-2009`): the nearest stand
within `FLAG_AT_STAND_CM` (400 cm, line 1902) unless that team's flag is
believed home; otherwise wait up to 15 x 100 ms for any newer flag incident
and take its team; otherwise the nearest stand's team at any distance;
otherwise red. The first-person flag takes the local player's last grab, then
the last flag incident, then red (`2023-2034`).

The script side is right. The flag's owner team and `TEAM_INDEX` come from the
stand's owner team (`ctf.rs:368-371`, `311-327`), and Megalo's team write has
no "team present" check (sim `0x41c8b0` -> `0x41fd80` case 5 -> `0x4089b0` ->
`0x66af70`). Bungie's CTF also sets a flag's owner team once, when it creates
or adopts the flag, not every tick. Verified.

**Every wrong-colour path** (`main.lua` lines; host and client unless noted):

| # | Path | Lines | Status |
|---|---|---|---|
| P1 | A flag dropped or re-grabbed within 4 m of a stand whose own flag is away is dressed in that stand's colours and pinned onto it: a blue carrier killed near the blue stand in a standoff turns the red flag blue | 1980-1989, 2005-2008 | Verified |
| P2 | The wait ends on the next incident of **either** flag (`flagSerial`, `lastFlagTeam` count both): two flag events within 1.5 s give the first actor the second flag's team | 1996-2003, 2354-2359 | Verified |
| P3 | Incident before actor: if the flag's own incident drained before the actor's watch captured its serial, the wait needs a second incident (P2) or times out on a value another incident may have overwritten | 2087, 1996, 2359 | Race verified; which side wins inferred |
| P4 | No incident for the actor at all (late join, a re-created actor, a missed relay): after 1.5 s the last incident of either flag, else red | 2003-2005, 2032 | Fallbacks verified; triggers inferred |
| P5 | Client: the relay arrives later than 1.5 s | 1996-1997, 2025-2026, 2444-2462 | Timeout verified; latency inferred |
| P6 | The 3 s sweep reaches a new actor before the watch's 50 ms handler, dresses it with no wait, and marks it so the watch returns | 2069-2075, 2088, 2044-2046 | Verified |
| P7 | Host: `flag_grabbed` unpins the home flag before the new carried actor is dressed, so the carried actor (still within 4 m) is pinned onto the stand and recorded as home; captures hit the same staleness | 2368, 2088, 1989, 2008, 1948, 1967-1972 | Ordering verified; actor-per-pickup lifecycle inferred |
| P8 | First person: `carriedTeam` changes only when the cause is the local player, and `flag_dropped` has no cause, so a drop never clears it; `quenchFlags` then recolours every first-person flag to the stale value | 2023-2034, 2107-2126, 2362-2366 | Verified |
| P9 | Flags and their meshes are keyed by full name, the skull set by address; a reused name would skip a new actor | 1866, 1924, 2044-2046 | Keys verified; reuse inferred (low) |
| P10 | Rounds reset in place, but `lastFlagTeam`, `carriedTeam` and `flagSerial` reset only per world | 296-298, 5299-5309 | Verified |
| P11 | Client: relayed copies of a name are ignored once that name arrived natively once | 2487, 2540 | Gate verified; trigger inferred |

**The fix.** Make each flag's team a property of its tag, which the sim
publishes to Unreal as the model variant name. No native code.

Tags (`tools/level/build_ctf_flag.sh`):

1. Keep `objects\weapons\multiplayer\flag\flag` as the red flag, entry 18. Its
   `default model variant` is empty, which the sim resolves to variant index 0,
   `default`, and publishes by name (sim `0x5a7d90`, `0x5b3190`), so
   `GetVariantName()` should already read `default` today. Verified chain; the
   in-game read below confirms it. Setting the field to `default` explicitly is
   cheap insurance.
2. Add `objects\weapons\multiplayer\flag\flag_blue`: the same recipe plus
   `default model variant = blue`, in its own container
   (`pakchunk990-MJOLNIRFLAGB`). The assault bomb model already has variants
   `default` and `blue`. Verified.
3. Add object type list entry 20 = `flag_blue`. Check that `pack --duplicate`
   appends, as the script already assumes.
4. Ship the variant, the type list override and the blue container together.
   The new variant sets bit 20 of its object types; if the installed list has
   no entry 20, validation (`0x409c40` -> `0x40a310`) wipes the whole script and
   there is no CTF at all. Verified.

Why two tags and not one tag plus a variant name at creation: the Megalo
string-id table (57 entries) has no `red` or `blue`, and an object's model
variant travels only in its creation data, so a variant set after creation
never reaches clients (sim `0x503140`, `0x508a10`, `0x504ea0`). A tag's default
reaches every machine with the tag index, and `0x5a7d90` maps an empty or
unknown name back to the tag default. Verified; which variant id a client's
replicated creation passes is unread, and the tag default covers both answers.

Megalo (`crates/blam-megalo/src/ctf.rs`, `crates/blam-cli/src/megalo.rs`):

1. `Ctf` gains `blue_flag_type` (CLI `--blue-flag-type`, default 20);
   `object_types` becomes the red and blue types.
2. The stand trigger clears `NEW_FLAG`, then calls three subroutines: create
   the red type when the stand's owner team is 0; create the blue type and set
   `TEAM_INDEX` = 1 when it is 1; and, when `NEW_FLAG` is set, link, copy the
   owner team, set pickup, priority and waypoint. Each branch is its own
   subroutine because a trigger stops at its first failed condition (sim
   `0x423a70`).
3. While there: give `flag_dropped` the last carrier as its cause, use Reach's
   flag icon value, score the carrier as a player (the team follows by sum),
   and default the tick rate to 60.
4. Update the fingerprint and range tests (`ctf.rs:425-458`).

Lua (`mods/MJOLNIRLevelLoader/Scripts/main.lua`):

1. A flag's team is `actor.BlamMeshSynchronization:GetVariantName()`: `blue`
   is blue, anything else non-empty is red. While it reads empty, retry every
   100 ms for about 2 s, then log the actor and leave it undressed rather than
   guess.
2. Log and cross-check `BlamObjectSynchronization.BlamTagDefinitionIndex`,
   which differs between the two types.
3. Pin a flag to its stand only when it has no attach parent and lies within
   about 150 cm of the stand of **its own** team.
4. First person: the enemy of the local pawn's team, because pickup is
   enemies-only. The pawn's team comes from `pawn:GetBlamObjectActor()` (exe
   `0x7b0b0a0`) and its `BlamGameTeam` multiplayer half. Retry while it is
   empty; never default.
5. Remove `flagSerial`, the serial capture, the wait, and `lastFlagTeam`,
   `carriedTeam` and every `"red"` default from colour decisions. Incident
   values stay for the announcer and HUD.
6. The sweep re-reads each flag's team and repairs a mismatch. Key actors by
   address and full name. Reset the remaining flag state at each round start.

A replacement path for later, generic: read `MP+0x19` of the actor's
`BlamObjectIndex` in the sim. The owner team replicates to clients, so it gives
the same answer on every machine; it needs a cross-thread read through the sim
thread's TLS. Keep it for objects whose team changes during play (a KOTH hill,
an Oddball ball, an Assault bomb, a territory), which the model-variant route
cannot follow after creation.

Side note: `VariantName` does not change meshes, the permutation pairs do
(exe `0x7a20850` rebuilds only on a pair change). The flag's visible mesh is
CE's, attached by Lua, so this does not matter for CTF.

**Built (2026-10-22, branch `work/reach-game-mode-support-2eca91`, untested
in game).**

- Tags: `tools/level/build_ctf_flag.sh` writes `flag_blue` (default model
  variant `blue`) into `pakchunk990-MJOLNIRFLAGB_P`, sets the red flag's to
  `default`, and appends object type list entry 20. Built into a scratch
  folder with the debug CLI; the list has 18 flag, 19 health_pack,
  20 flag_blue.
- Megalo: `Ctf::blue_flag_type` (`crates/blam-megalo/src/ctf.rs`); the stand
  trigger clears `global.object[0]`, calls a subroutine that creates type 18
  for a stand of team 0 and one that creates type 20 for team 1, then the
  old setup, gated on a flag having been made. The bitset names 18, 19 and
  20. `mjolnir megalo write --mode ctf` defaults to `--blue-flag-type 20`;
  `--single-flag` writes the old one-type script, byte for byte the same at
  the same tick rate (pinned by a test).
- Lua: the flag and armour code moved out of the loader's `main.lua` into
  `mods/MJOLNIRLevelLoader/Scripts/teams.lua` (the loader went from 200
  top-level locals to 156). A world flag's team is its mesh-sync
  component's `GetVariantName()`; while that reads empty it retries for 2 s
  and then leaves the flag as the skull it is drawn by, logged, rather than
  guess. Every dress logs the variant, `BlamTagDefinitionIndex`,
  `BlamObjectIndex` and `ParentObjectIndex`. Pinning follows the rule above;
  the first-person flag is the enemy of `GetBlamObjectActor()`'s team. The
  serial wait, `lastFlagTeam`, `carriedTeam` and every red default are gone.
- Release order: the CE runtime pack (`MJOLNIRFLAG_P`, `MJOLNIRFLAGB_P`,
  `MJOLNIRMOTL_P`) ships before or with the mods release whose `ctf.mglo`
  names type 20, on every machine. MJOLNIRLobby offers CTF only when
  `pakchunk990-MJOLNIRFLAGB_P` is installed, and the loader logs a warning
  on any machine that stages CTF without it.

**Checks in game before release (the user):**

1. Read only, before any change: on host and client, log for every
   `BP_SkullActor_C` its `GetVariantName()`, `BlamTagDefinitionIndex`,
   `BlamObjectIndex` and `ParentObjectIndex`. Expect `default`. Also log the
   actor's address and full name at a grab and a drop, to settle whether a
   pickup makes a new actor.
2. After the change: flags appear at both stands (no script wipe); red reads
   `default` and blue reads `blue` on host and fireteam client, at home,
   carried and dropped; the two tag indices differ.
3. The old paths: a blue carrier killed within 4 m of the blue stand while the
   blue flag is away (P1); both flags dropped within 1 s (P2); a client joining
   while one flag is carried and the other dropped (P4); a client with the
   relay disabled (P5, P11).
4. First person: grab and drop several times on host and client.
5. Unchanged: announcer lines, HUD scores, the oddball skull on a non-CTF map,
   both flags recreated in the right colours after a round reset.

### 2.3 Custom armour does not show red or blue

**How armour works.**

| Step | Where | Status |
|---|---|---|
| The player's choice | `UBlamGameUserSettings.ObjectCustomizationNames` (`+0x858`) -> exe `0x7b57a60` writes up to 10 (customization, selection) byte pairs into the Blam profile -> the player configuration's appearance (`P+0xd8`) | Verified |
| Variant chosen in the sim | sim `0x2f2730` looks the player's pair up in `globals\player_model_customization` (`object customization selections`; the Spartans entry has 26 selections, the first `og_001`, Mk V Classic) and returns a variant name; `0x182ef0` writes it to the placement and returns early. A player with no pair gets the representation's variant plus `spartan model defaults` (`body = default`, `head = default`), which win in `0x5a7e60` | Verified |
| Re-applied everywhere | `0x1823c0` re-runs this on every configuration update and writes the unit's variant (`+0xea`). Configurations reach every machine's sim as sim message 9 (`0x4feac0`) | Verified |
| What Unreal builds | `BP_SpartansBipedActor`'s mesh sync `RuntimeRegions`: every armour except `og_001` is a body skeletal mesh plus 11 to 17 `BPC_StaticMesh_C` plates and a static helmet (Spartan: two head statics). Coatings put their material on body, plates and helmet (Ship_003 and Ship_008 on 9 and 10 of 17 plates). `sparta_001` and `wolf_001` add a second `BPC_SkeletalMesh_C` (cloth); `mkiv_001` adds two plain `SkeletalMeshComponent` thighs. First person (`BP_MeteoritePawn`): 6 arm and 9 leg static plates for `default`, none for `og_001` | Verified (cooked data) |
| When it applies | asynchronously (`Blam.MeshSynchronization.EnableAsyncLoad` defaults to 1): exe `0x7a21080` requests the load; completion `0x7a26040` sets the loaded mesh on the existing same-class component, applies `MaterialOverrides`, rebuilds the plates, then broadcasts `OnRegionsChanged` | Verified; slot names (`SetSkeletalMesh` and so on) inferred |
| Actors are pooled | `Halo.ActorPooling.Enabled` and `Blam.Synchronization.PrecreateObjects.Enabled` default to 1; exe `0x75ae950` pops a pooled actor or creates one; exe `0x7a19690` calls `BP_OnGameplayStart(VariantName, ObjectGameStateIdentifier)` when an actor is bound to a sim object | Verified; whether a respawn reuses a pooled actor is not established |

**What MJOLNIR does** (`main.lua:2549-2711`). In a team game (`TEAM_GAMES`,
`2556`: ctf and team_slayer) it swaps every component of class
`BPC_SkeletalMesh_C` or `BPC_TranslucentSkeletalMesh_C` to Mk V Classic
(`BIPED_ROLES`, `2596`) and gives it a dynamic material with `Armor Color` red
or blue (layer parameter 0; the comment at `2561` calls it global). The team is
the `EBlamMultiplayerTeam` half of `GetGameTeamString()` (`bipedTeam`, `2581`).
Triggers: the class watch plus 300 and 2000 ms; `retintSoon` at 300, 1500 and
4000 ms after `player_spawn` or `respawn_final_tick` (`2382-2384`,
`2699-2709`); the CTF sweep every ~3 s on levels with a `ctf` block. First
person takes the team of the Spartan nearest the camera (`2683-2697`).

**Root causes, ranked by evidence:**

| # | Cause | Evidence | Status |
|---|---|---|---|
| 1 | **The plates and helmet are static meshes MJOLNIR never touches.** `dressMeshes` enumerates `SkeletalMeshComponent` only (`2617-2618`). Every armour but Mk V Classic keeps its plates and helmet, in its own coating, over the tinted Mk V body. This is why custom armour never reads as red or blue while Mk V Classic players look right | cooked `RuntimeRegions`; `main.lua` | Verified (data and code); on-screen look inferred |
| 2 | Roles are keyed by component class: Lone Wolf and Spartan get two Mk V bodies (body and cloth both swapped), MkIV keeps its thighs | same | Verified; look inferred |
| 3 | A late asynchronous apply puts the player's own body mesh back on the swapped component, leaving the Mk V material on a foreign mesh; a remote player's appearance arriving on a client re-triggers it | exe `0x7a21080`, `0x7a26040`; sim `0x1823c0` | Mechanism verified; timing inferred |
| 4 | Trigger timing: the class watch fires when the pool builds an actor, often before it has a team (`tintBiped` gives up without one, `2646-2652`), not when a pooled actor is reused. On a client, other players' spawns raise no re-tint (`player_spawn` is not relayed, `2427`; their `respawn_final_tick` is personal and dropped, `2377`). The client's own spawn does re-tint, and CTF levels re-tint every 3 s, so the gap is remote spawns on levels without a `ctf` block | `main.lua` | Verified code; frequency inferred |
| 5 | First person takes the nearest biped's team: wrong in melee, vehicles and deaths | `2683-2697` | Verified code |
| - | **Not a cause:** the team value. The multiplayer half of the team component is `P+0xad` on every machine, refreshed with each update. Do not switch to `ActorTeamIs*` or the allegiance half (0xff) | section 2.1 | Verified |

**The fix.**

A. **The sim chooses Mk V Classic for everyone in team games** (native, in
`mjolnir_map_registry.dll`). Hook sim `0x2f2730` after the call: when team
armour is on and the object is the Spartans biped, return `og_001`'s string id
(read once from the Spartans entry's first selection). Every player, with or
without a choice, then takes `0x182ef0`'s early return with `og_001` and no
legacy overrides, at spawn (`0x189e90`) and on every configuration update
(`0x1823c0`). Weapon skins (entries 1 to 7) pass through. Constraints:

- Install it on **every** machine. Every sim re-evaluates every player's
  variant on each configuration update, and a variant the host changes after
  creation does not replicate through the base object update (section 2.2;
  the biped-specific decoder was not read), so a host-only hook would be
  undone on clients. Verified chain; on-screen result inferred.
- It answers only while sim `DAT_1813762f4 == 2` (a map is loaded, checked by
  `0x2f2870`). Verified.
- Byte-checked like the existing patch table, but installed once and never
  removed: the simulation thread may be inside the call, and restoring code
  under a running Megalo game froze clients before (2026-10-02). "Off" only
  clears the flag the hook reads.

The mesh sync then loads the Mk V body with no plates and no helmet, first
person included, and nothing fights the tint any more.

B. **Tint on the game's own events** (Blueprint hooks, each fired once per
spawn or apply):

- `BP_SpartansBipedActor_C:BP_OnGameplayStart`: an actor now represents a
  biped; record it by full name and tint on the next tick and ~0.5 s later.
- The biped's `OnRegionsChanged` handler
  (`BndEvt__BP_EliteBipedActor_BlamMeshSynchronization_K2Node_ComponentBoundEvent_4_OnRegionsChanged__DelegateSignature`),
  which runs after every mesh apply: tint now.
- `BP_MeteoritePawn`'s arms and legs `OnRegionsChanged` handlers, for first
  person, with the team from `pawn:GetBlamObjectActor()`.
- Tint only components whose first material is `MI_Spartans_MkV_Classic` or an
  MJOLNIR instance. A check every 1-2 s over the recorded actors repairs pool
  reuse with no mesh event. The fixed timers and the nearest-biped rule go.

Within the project's rules: the loader's `main.lua` is at the 200-local limit,
so the block moves to its own module; no `FindAllOf` or `StaticFindObject` in
loops; actors keyed by full name; only Blueprint functions hooked.

C. **Interim, Lua only:** on the same hooks, also hide every
`BPC_StaticMesh_C`, `BPC_FP_StaticMesh_C` and `BPC_PAWN_StaticMesh_C`, swap
only the body (hide the cloth and the thighs), and redo it on each
`OnRegionsChanged`. The game still loads and briefly shows the player's own
armour after each apply.

D. **Fully native, later** (it also gives Infection and Juggernaut a player
colour channel): the Spartans model already has 18 unused `og_<colour>` body
permutations (`og_red`, `og_blue`, and the rest of CE's palette). Add `og_red`
and `og_blue` keys, with Mk V meshes and coloured material overrides, to the
body `RuntimeRegions` of `BP_SpartansBipedActor` and the arms and legs of
`BP_MeteoritePawn`, and have the sim select them by team through placement
override pairs (`0x2f2990` -> `0x5a7e60`). The keys must exist first: a
permutation missing from `RuntimeRegions` empties the region, so the body
would vanish (exe `0x7a20850`, `0x7a21080`, `0x7a26040`). Verified. Cost:
cooked overrides of two large Blueprints.

**Built (2026-10-22, branch `work/reach-game-mode-support-2eca91`, untested
in game).**

- A (native): `native/map_registry/mjolnir_map_registry.c`, exports
  `mjolnir_team_armor_on` and `_off`. The aligned qword at sim `0x182f08`
  (`f8 e8 22 f8 16 00 8b d8`, the call of `0x2f2730` at `0x182f09`) is
  checked and rewritten in one locked 8-byte write, so the call goes to a
  12-byte `mov rax, imm64; jmp rax` stub allocated within 1.75 GB below
  the simulation, and from there to `team_armor_pick` in the DLL. With
  forcing on, that asks the original for a made-up appearance whose only
  pair is (0, 0): `0x2f2730` matches the definition against the
  customization entries before it reads a pair, so only the Spartans biped
  (entry 0, selection 0 `og_001`) gets an answer; anything else is asked
  again with its real appearance. `0x2f2730` reads only RCX (+0x19, +5+2i,
  +6+2i) and EDX, and `0x182ef0` reads only EAX after the call (verified in
  the disassembly, and the built wrapper's code was read back with
  `dumpbin /disasm`). It never logs per call, only once when it first
  forces. A build with other bytes is refused and logged; the Megalo switch
  is unaffected either way.
- B (Lua, `teams.lua`): hooks `BP_SpartansBipedActor_C:BP_OnGameplayStart`
  (the Blueprint implements it with its own bytecode), the Spartan's
  `OnRegionsChanged` handler and `BP_MeteoritePawn`'s arms and legs
  handlers. Each event records the actor and tints on the next pass: a body
  that is not Mk V Classic (the hook missing or refused) is swapped, and its
  plates, helmet, cloth and extra parts are hidden; then `Armor Color` is set
  on an MJOLNIR instance of the Mk V material. A pass every 1.5 s repairs
  recorded actors by full name. The loader switches the hook on for `ctf`
  and `team_slayer` and off for anything else; with an older DLL it logs
  once and the Lua swap does the work.

**Checks in game before release (the user):**

1. Two PCs, team game, one player in a coating (Blue_001) and one in Chief
   default: screenshots in third and first person, before the change (cause 1).
2. Log the full name in a `BP_OnGameplayStart` hook across respawns (pool
   reuse) and the time of each `OnRegionsChanged` against the old timers
   (causes 3 and 4).
3. With the hook on both PCs: the coated player and the default player both
   spawn in Mk V with no plates or helmet, in third and first person, on host
   and client, after respawns and after a player joins mid-match.
4. On a Team Slayer map (no `ctf` block): remote players' colours after their
   respawns, on the client.
5. Optional: whether the `Color` parameter of `MI_Chief_Armor` (layer index 2)
   tints Chief's own armour in place.

---

## 3. Other Reach game types

Every Bungie mode family is one script; its sub-variants (One Flag, Neutral
Bomb, Crazy King, SWAT and so on) are the same triggers with different option
values. MJOLNIR writes its own scripts. Bungie's are a reference for behaviour.

### 3.1 The building blocks most modes share

| # | Block | Today | What it takes | Needed by |
|---|---|---|---|---|
| B1 | Tick rate | the sim runs 60; the CLI assumed 30 until the branch made 60 its default (2026-10-22) | Megalo timers for new countdowns | every countdown |
| B2 | Object owner-team colour | not drawn (section 2.1) | per-team model variants for objects whose team is fixed at creation (as CTF); a native `MP+0x19` reader by `BlamObjectIndex` for objects that change team | CTF variants, Oddball, KOTH, Territories, Stockpile, Assault |
| B3 | Player colour by trait or script team | the forced-colour trait (byte `+0x24` of the player's applied traits at `P+0x340`, read by sim `0x2b3710`) and a script-set team (`G+0x3b9+p*0xf0`) are not in the snapshot; in free-for-all the team component shows the slot index (0..15) | a native read of both, driving the armour tint (2.3 B or D) | Infection, Juggernaut, Grifball |
| B4 | Megalo HUD | widgets (`G+0x2a4`), objective text and icon, progress meters and waypoint icons never reach the snapshot; Unreal's navpoints come only from the HaloScript `chud_track` list (`[TLS+0x428]+0xcd0`) | read them natively and draw with UMG from Lua; or mirror waypoints into the HaloScript list (sim `0x473960`, per player), which shows a label and priority but no icon (inferred feasibility) | every objective mode |
| B5 | Boundaries | the snapshot has no shape; whether the sim's own boundary drawing (slot 29 -> `0x66b900`/`0x66ba00`) reaches the screen is unknown, probably not (inferred) | a zone actor drawn from the object's shape (`MP+0x00..+0x10`) | KOTH, Territories, Infection havens, Headhunter, Stockpile, Assault |
| B6 | Object type list | 20 entries: 18 weapons, MJOLNIR's flag (18) and health pack (19) | list entries and tags (section 3.2) | all but Slayer and Infection |
| B7 | Map placements | converted maps carry flag stands, CTF spawn labels and vehicle labels; CE's `OddballSpawn`, `HillFlag` and `RaceTrack` markers are kept in the level file (`defs/level/ce-tag-map.json:56-66`, `gen_ce_level.py:1290-1294`) but not placed as labelled objects | placements with label, owner team, spawn order and shape; a CE hill polygon fitted to one shape (inferred) | Oddball, KOTH, Race; Headhunter, Territories, Stockpile, Assault need authoring |
| B8 | Rounds | MJOLNIR ends a match at the first `round_over`; designator switching acts only from round index 1 | let the sim play the variant's rounds | one-flag CTF, one-bomb Assault, any side swap |
| B9 | Announcer | 3 of 339 sounds ship | `events.json` lines by incident name, as for CTF | all |
| B10 | Out of bounds | always false on converted maps | kill (MP type 26) or safe (25) volume objects with shapes in levels | CTF, Assault, Oddball, Headhunter resets |
| B11 | Game type identity | 13 places, insertion-point slot to clients | one descriptor; the lobby carries id, release and hash | all |
| B12 | Trait weapons | Reach trait and loadout weapon indices index CU4's object type list `weapons` collection, abilities its `equipment` collection (empty in CU4) | write fresh, or remap | SWAT, Pro, Juggernaut, Infection, Escalation |

Engine behaviour an author relies on (all sim, verified unless marked):

| Topic | Behaviour |
|---|---|
| Team assignment | host's session (`0x4bab20`); no script or Lua can move a player in a team game. A team picker would set the client's desired team (configuration `+0x66`). A player's team change kills the unit, zeroes its round score and raises `player_switched_team` (`0x1823c0`) |
| Script teams under a free-for-all header (Infection, Juggernaut) | `player.team = X` writes `G+0x3b9+p*0xf0`; slot 53 returns it when teams are off, so enemies, spawns and label filters follow it. Unreal's team component still shows `P+0xad` (the slot index) |
| `team_changes` (`o+0x2fa`) | read only by a session predicate (`0x20c230`); no effect in MJOLNIR |
| Species and model override (`o+0x3b8`, team `+0x45`) | picks the spawned representation: Spartan, Elite or Forge monitor (`0x187a90`). An Elite in Unreal is untested (inferred risk) |
| `fireteams_enabled` (`o+0xf83e`) | 1 switches friend or foe to designators, and makes "team has players" true for designators 0 and 1 |
| Respawn zones | honoured: scenery with MP type 16 (or 21..24 for fireteams) and a shape becomes a spawn influencer (`0x307d10`, `0x2f77a0`); a negative weight as an anti-zone is inferred |
| Label loops and deletion | safe (section 1.5); objects created during a pass are not visited until the next |
| Forge-only branches | `0x2b5520` returns the variant's engine type; designator forcing and the `round_over`-instead-of-game-over branch apply only to type 1 (sandbox). MJOLNIR runs type 2 |
| Call HaloScript (action 100) | runs only scripts the loaded scenario has (`0x36c1a0`, `0x1f6b60`) |

### 3.2 Object types

The sim takes the scenario's own `multiplayer object types` reference, else
the globals list (`0x3112c0`); converted maps have none, so the globals list,
overridden by `pakchunk990-MJOLNIRMOTL_P`, applies. Validation wipes a script
whose declared type bitset names an entry with no tag (`0x409c40`); action
operands are not checked against the list (section 4.4). Verified.

| Reach type (index) | CU4 today | What it takes |
|---|---|---|
| flag (3) | entry 18 (MJOLNIR), plus `flag_blue` at 20 after the CTF fix | remap |
| assault rifle 14, needle rifle 18, energy sword 20, magnum 21, needler 22, plasma rifle 23, rocket launcher 24, shotgun 25, sniper 26, fuel rod 161 | entries 0, 11, 15, 3, 10, 7, 6, 5, 4, 13 | remap |
| health pack (76) | entry 19 by role (MJOLNIR's is equipment, Reach's a device) | remap |
| bomb (4), skull (5), DMR, plasma repeater, spartan laser, gravity hammer (30), focus rifle, plasma launcher, concussion rifle, grenade launcher, grenades, warthog, ghost, scorpion, wraith, banshee, jetpack | a CU4 tag exists, no entry; the bomb has no Unreal actor of its own (the flag borrows the skull's) | entries; for vehicles, the empty `vehicles` collection too |
| hill marker (6), flag stand (7), capture plate (8), respawn zone (60), weak anti respawn zone (151), mongoose, landmine, golf ball and club, data and power cores, fire emitter (141), Invasion props | no CU4 tag | new invisible scenery with a multiplayer block, a model and a shape (as MJOLNIR's flag stand); respawn zones need MP type 16. Mongoose, golf, cores and Invasion props: substitute or drop |

Hub game types should name object types; the hub or loader resolves names to
the installed list's indices, which differ from Reach's and will move as
MJOLNIR adds entries.

### 3.3 Per-mode matrix, cheapest first

Map labels are Bungie's (with the minimum count the map must carry). "Reach
types" are the object types the script creates or tests. Blocks refer to
section 3.1.

| # | Mode | Map needs | Reach types -> CU4 | Unreal host | Engine and unknowns | Blocks | Cost |
|---|---|---|---|---|---|---|---|
| 1 | **Team Slayer** | nothing new | health pack 76 -> 19 | armour fix (2.3); HUD tallies exist (fix betrayal counting) | teams on; team score sums player scores; betrayal = killer-type bit 3 | B1, B9 | Low: one script |
| 2 | Slayer variants (Pro, Classic, SWAT) | as Slayer | 76 -> 19; trait weapons | objective text; leader marker | death damage modifier values (headshot, pummel and so on) untested on CU4 | B4, B12 | Low |
| 3 | Juggernaut | `juggernaut` | gravity hammer 30 (tag exists), fire emitter 141 (drop) | forced white and black colours; Juggernaut waypoint | script teams under a free-for-all header work in the sim; Unreal sees the slot index | B3, B4, B6, B12 | Low-medium |
| 4 | Infection (Safe Havens) | `infection`, `inf_spawn`, `inf_haven` (1) with shapes | none; zombie trait weapon -> CU4 energy sword, ability none | forced zombie colour (essential); haven boundary; widget | as Juggernaut | B3, B4, B5, B7, B12 | Medium |
| 5 | Headhunter | `headhunter`, `hh_drop_point` (1) with shapes | skull 5 | carrier skull-count waypoint; drop-point boundaries; widget; kill-feed text | skull pickup by walking untested | B4, B5, B6, B7 | Medium |
| 6 | Oddball (Team, Hot Potato) | `oddball`, `oddball_ball` (1), from CE `OddballSpawn` markers | skull 5, bomb 4, anti zone 151; flag stand and capture plate only tested | ball waypoint following the carrier; ball colour follows the carrier's team | the ball's team changes during play | B2 (native), B4, B6, B7, B10 | Medium |
| 7 | KOTH (Crazy King) | `koth`, `koth_hill` (1) with map-authored shape, from CE `HillFlag` polygons | anti zone 151 | hill boundary in the holder's colour (essential); crown waypoint | the hill's team changes during play | B2 (native), B4, B5, B6, B7 | Medium |
| 8 | Escalation (Gun Game) | Slayer's | 18 weapon types: 7 remap, 9 need entries (tags exist), golf club absent | weapon-tier widgets | `Add Weapon To Biped` untested | B4, B6 | Medium |
| 9 | CTF variants (One Flag, Neutral, Multi-team) | have `ctf_flag_return` with teams; neutral needs a placed flag; multi-team 3-4 stands; optional `ctf_res_zone`, `ctf_res_zone_away` | flag 3, hill marker 6 | colours for 3-4 teams (`EBlamMultiplayerTeam` has 8); attack and defend markers; return progress bar | side swap per round | B2, B4, B6, B8 | Medium-high |
| 10 | Territories (Land Grab, 3-Plot) | `territories`, `terr_object` (1) with spawn order | flag 3 per territory, anti zone 151 | boundaries; letter waypoints (icons absent); progress bars; territory flag colour that changes on capture | placements authored per map | B2 (native), B4, B5, B6, B7 | High |
| 11 | Stockpile | `stockpile`, `stp_flag` (1), `stp_goal` (1) | flag 3, respawn zone 60 | flag and goal markers; goal boundary; flag colour that changes in a goal | respawn zones honoured | B2 (native), B4, B5, B6, B7 | High |
| 12 | Assault (One Bomb, Neutral, Grifball) | `assault`, `as_bomb` (1), `as_goal` (1), authored (CE has no bomb data) | bomb 4 (needs an Unreal actor), hill marker 6, anti zone 151; Grifball adds hammer 30 | three widgets; arm and defuse progress bars; bomb colour that changes when planted; goal boundary | attach to the goal; detonation effect; side swap | B2 (native), B4, B5, B6, B7, B8 | High |
| 13 | Race and Rally | `race`, `race_spawn`, `race_flag` (1) in order, from CE `RaceTrack` markers | warthog, ghost, banshee (tags exist), mongoose (none), landmine (none, optional) | per-player waypoints with text and distance; speed widgets from the `local` trigger | `Force Player Into Vehicle` untested; the `local` trigger is what clients run | B4, B6, B7 | High |
| - | Invasion, Invasion Slayer, HaloBall | map devices, cinematic interpolators, cores, Elite tiers, Reach-only props | - | - | - | - | Not realistic |

Two colour channels decide whether team modes read correctly in Unreal: the
owner team of objects (B2) and the forced colour or script team of players
(B3). Both are exact in the sim and absent from the host today.

---

## 4. Proving a mode correct

### 4.1 The bitstream: Bungie's corpus round trip

The codec and its tests land with branch `work/reach-game-mode-support-2eca91`;
at 772eca0d only the typed builder exists.

`crates/blam-megalo/src/raw.rs` decodes and encodes any variant by the grammar
in `crates/blam-megalo/grammar/megalo_cu4.json`, which was read out of the CU4
decoder (sim `0x392a40` and every callee). It is strict: a read past the
buffer or a tree that no longer fits the grammar is an error.

```text
MCC_REACH="C:/Program Files (x86)/Steam/steamapps/common/Halo The Master Chief Collection/haloreach" \
  cargo test -p blam-megalo --test roundtrip
```

`crates/blam-megalo/tests/roundtrip.rs` checks MJOLNIR's own variants, the 9
fixtures under `tools/tests/fixtures`, and, when `MCC_REACH` is set, every
Megalo variant in `game_variants` and `hopper_game_variants`. Result on
2026-10-21: **417 of 417** round-trip bit for bit, each ending within its last
byte with zero padding (55 Firefight, 1 Forge and 1 campaign file skipped).
Without `MCC_REACH` the Bungie test passes without checking. Verified.

What it proves: the wire format of every opcode Bungie used (80 of the 106
action types; every condition but 9, 10, 16 and 17). The rest were checked by
reading their cases in the decoder (sim `0x39cf20`). It settled one doc error:
actions 30 and 31 take a player and an output number; only action 99 is a
nested trigger block. What it does not prove: what any opcode does.

### 4.2 Golden dumps

`mjolnir megalo dump <file.mglo|file.bin> [--out <file>]`
(`crates/blam-cli/src/megalo.rs:356`) lists every field in read order, string
text, teams, traits, labels, and the script as triggers with named conditions
and actions, and states the round-trip result and its checks (trigger ranges,
entry points against attributes, nested calls in range, every condition and
action owned by a trigger).

Proposed (not built):

- Commit golden dumps of MJOLNIR's own released variants, built the way the
  release builds them, and fail CI when a variant's dump changes without its
  golden file. A reviewer then reads a script diff, not bytes.
- Compare a new MJOLNIR mode with Bungie's by reading the two dumps side by
  side on this PC (Bungie's dumps stay local).

### 4.3 Bungie's modes as a local oracle

Bungie's files fit the loader: the largest payload is 17,816 bytes, under the
0x5000 bound, and both encoding versions (0x6a, 0x6b) decode. Unmapped they
are wrong: Slayer (type 76), KOTH (151), Oddball, Territories and Assault are
wiped by validation; Bungie's CTF and Headhunter load but create a magnum and a
rocket launcher, or shotguns, because CU4's low indices are weapons; Infection
loads with wrong trait weapons. Verified from the bitsets.

A local remap tool over `raw.rs` trees would rewrite the object type bitset,
the type operands (Create Object, Object Type, label filters, Add Weapon), and
trait and loadout weapon and ability indices, with the missing list entries
as a local override and Bungie's labels on a test map. Then Bungie's KOTH and
MJOLNIR's KOTH can be played on the same map, expecting the same incidents and
scores. Design; not built.

The boundary is legal, not technical: read the files from the MCC folder at
test time; never commit them, their dumps or remapped copies; never upload or
ship them.

### 4.4 Validate before the sim sees a variant

CU4's decoder and runtime enforce almost no limits. The full table is in
[`re/megalo_variant_format.md`](re/megalo_variant_format.md) (limits) and
[`re/reach_game_engine.md`](re/reach_game_engine.md) ("The safety envelope of
a variant"). The worst cases:

| Risk | Where (sim) | Status |
|---|---|---|
| The main string data is written to its 0x4c00-byte buffer (`o+0x11b8`) with no cap, uncompressed (u15 size) or inflated (to the stream's own length): it overruns the encoding version and the whole script | `0x3949c0`, `0x32a620` | Verified |
| More than 4 HUD widgets overwrite player 0's Megalo state (`G+0x344`) | `0x40a130` | Verified |
| Run Nested Trigger takes any index 0..511 and has no depth limit: a cycle recurses until the stack is gone | executor `0x399110` case 0x14 -> `0x39ed40` | Verified |
| Object type operands are not bounded by the list size | `0x41c3b0`, `0x421b80` | Verified |
| A trigger's condition and action ranges are trusted | `0x423a70` | Verified |
| Counts past the store overwrite the next field (script traits 16, user options 16, option values 8, conditions 512, actions 1024, triggers 320, statistics 4, labels 16, strings 112 per language) | `0x392a40` | Verified |
| Compare operators 6 and 7, trigger types 6 and 7 jump through 6-entry tables and crash | `0x423fc0`, `0x39ed40` | Verified |

Safe as it stands: undefined actions 107-127 do nothing; every player, object,
team and timer reference resolves to a defined slot; the incident index is
bounded by its iterator; action 100 runs only scripts the scenario has. Action
97 (griefer penalty) can get a player booted, so a validator should refuse it.

The validator runs at hub upload and again at install, over the decoded tree,
and rejects any variant past these caps: file at most 0x5000 bytes; main string
data at most 0x4c00 bytes (compressed: the embedded length too) and at most 112
strings; the counts above; HUD widgets at most 4; condition type at most 17,
action type at most 106, trigger type at most 5, compare operator at most 5;
each trigger's ranges inside the arrays; nested trigger indices inside the
trigger count and no cycle; every object type operand declared in the bitset;
incident indices from the known list. A native guard in
`mjolnir_megalo_variant` repeats the check (or verifies the validator's hash)
before it copies the file and writes the name buffer, and refuses anything
larger than 0x5000 bytes.

**Read-back.** Validation that fails wipes the script region and sets every
entry point to none (`0x40a310`). A staged variant decoded and survived if the
live variant's encoding version (`o+0x5dc0`) is 0x6a or 0x6b, its trigger count
(`o+0x63f4`) is what was written and its entry points (`o+0xe5e0..`) are
not all none. The loader should log that after each round reset. It needs a
stable way to reach `o` through the sim thread's TLS. Verified offsets; not
built.

### 4.5 Live reads that settle what static reading cannot

All are reads. `mjolnir live engine`, `mjolnir live players`, the
`mapvar_probe` example and `mjolnir_sim_game_globals` in
`native/lobby/mjolnir_lobby.c` already reach most of them.

| Read | Expect (host / client) | Settles |
|---|---|---|
| `[TLS+0x60]+0x10` | 3 / 3 | the mode byte |
| `[TLS+0x60]+0x11` | 5 / 4 | distributed simulation; who runs triggers |
| `[TLS+0x60]+0x1da`; world type `[[sim 0x2c0c978]+0x10]` | 0, 7 / 0, 8 | no playback; world type |
| session `simulation-protocol`; `session+0x28` | 2; not 1 | why it is distributed |
| `[TLS+0x98]+6` | 60 / 60 | tick rate |
| live variant `o+0x5dc0`, trigger count after the round reset | 0x6a and the written count | the file decoded |
| on a client with no staged file, the same two | the host's values if the session copy carries the host's file | whether the native `game-variant` path alone can distribute hub types |
| `BP_SkullActor_C` `GetVariantName()` | `default` | the flag fix's premise |
| both bytes of a red and of a blue player's team component, on each machine | red 0xff and 0, blue 0xff and 1, on both | the armour key |

### 4.6 In-game checks for any mode (the user, two PCs)

1. The variant decoded and was not wiped (read-back log) on host and client.
2. Host and client show the same scores (sim and HUD), the same round end and
   the same winner.
3. Every incident the mode raises reaches the host's and the client's HUD and
   announcer.
4. Every team-coloured object and every player shows the right colour on both
   machines, after respawns and after a mid-match join.
5. The lobby offers the mode only on maps that carry its labels; every object
   spawns and stays on the ground.
6. Timers measured with a stopwatch.
7. Quitting from the match exits cleanly; the post-game flow returns the
   fireteam.

Nothing is tagged or published before the user has run these in game.

---

## 5. Custom game types on the hub

The design that turns these requirements into a package, a language, a
validator and a roadmap is [`custom_game_types.md`](custom_game_types.md).

The publish unit is a `.mglo`: the bare variant bitstream that MCC's Hot Reload
loads and MegaloEdit and ReachVariantTool write, and that CU4's loader already
reads (the sim keeps the `HotReload` directory name). What the research fixes
as requirements:

1. **The same bytes on every machine.** Per-tick Megalo state is decoded
   against each machine's own declarations (section 1.2), so the lobby must
   carry the game type id, release and hash, and every client must stage that
   file. The insertion-point slot channel (8 slots, unknown ids run Slayer)
   cannot carry it. Alternatively, if the live read in 4.5 shows the session's
   `game-variant` copy carries the host's file, clients could skip their own
   load.
2. **Validation** at upload and install, and the native guard at staging
   (section 4.4).
3. **A descriptor:** id, title, teams, player counts, score choices, required
   labels with minimum counts and teams, object types by name, game build
   range. Maps declare the labels they carry; the lobby offers only pairs that
   fit.
4. **Presentation from the descriptor and the sim:** score unit and teams from
   the descriptor, scores read from `G+0x32c0` rather than rebuilt from
   incidents.
5. **Plug points** (repository audit): a `gametype` manifest type
   (`hub/src/lib/api/manifest.ts:25`), `.mglo` allowed only for it
   (`hub/src/lib/api/scan.ts:37`), a listings side table like
   `map_listings` (`hub/migrations/0012_maps_and_lobbies.sql`), the lobby API's
   release id and hash, wider match teams than red and blue
   (`hub/migrations/0014_matches.sql:61`), an install folder of its own rather
   than the signed loader's `variants\`, and a descriptor-driven mode list in
   the lobby and HUD.
6. **Trust tier.** [`map_distribution.md`](map_distribution.md) both calls game
   types reviewed loader content and calls Megalo sandboxed. Section 4.4 shows
   it is not sandboxed without a validator. Undecided.
7. **Authoring.** There is no compiler yet; the `raw.rs` tree supports edit
   and re-encode with the grammar checking the result. A clean-room script
   language can follow ReachVariantTool's public script names (facts) and its
   CC0 manual; its code is GPLv3 and must not be copied into this MIT
   repository.
8. **Terms.** Microsoft's Game Content Usage Rules
   (<https://www.xbox.com/en-US/developers/rules>): non-commercial, a notice
   that the game is Microsoft's and the item is not endorsed, no
   objectionable content. Bungie's variants never go on the hub.

---

## 6. Corrections to other documents

| Document | Says | Correct |
|---|---|---|
| [`re/megalo_engine.md`](re/megalo_engine.md), "How the host picks the engine" | game mode byte 1 campaign, 2 multiplayer, 3 at the frontend | 1 campaign, 2 Firefight, 3 multiplayer; a Megalo match runs with 3 |
| `re/megalo_engine.md`, "What still blocks a match" | networking goes through Unreal, not the sim's stubbed `net_*` layer | the `net_*` console commands are stubs; the sim's own distributed simulation runs over the exe's Party transport |
| `re/megalo_engine.md`, "Quitting from a match" | "a Megalo game running (mode 2)" | mode 3; the fix holds because the check passes only mode 1 |
| `re/megalo_engine.md`, the interpreter table | slot 79 (`0x403260`) is the variable sync | slot 79 imports Megalo state after a host migration (`0x4fe150` -> `0x382480`); per-tick variables travel in the engine entities (section 1.2) |
| `re/megalo_engine.md`, "Still inferred" | the kill bit of condition 3 is inferred | verified: slot 62 (`0x3fea10`) writes death type 2 for a kill |
| [`re/megalo_variant_format.md`](re/megalo_variant_format.md), ACTIONS | actions 30, 31 and 99 are trigger blocks | 30 and 31 take a player and an output number; only 99 is a block. The full grammar is `crates/blam-megalo/grammar/megalo_cu4.json` |
| [`game_state_reader.md`](game_state_reader.md) | player `+0xAD`: 0 red, 1 blue ... -1 none | the team index in team games; the slot index (0..15) in free-for-all |
| [`host_game_settings.md`](host_game_settings.md), open question on a client's variant | open | a client's declarations decode the host's per-tick state, and the client runs its own `local` trigger |
| `crates/blam-megalo/src/powerups.rs`, `ce_map_conversion.md` | the sim never hands `recharge_health` to Unreal | Megalo refuses to submit it (sim `0x41df50`); the engine itself could |
| `crates/blam-cli/src/megalo.rs:93-95` | 30 ticks per second | 60 (the default on the branch since 2026-10-22) |
| loader `main.lua:2561` | `Armor Color` association 0 is global | association 0 is a layer parameter (layer 0) |

---

## 7. Open questions

| Question | What settles it |
|---|---|
| The live values of the mode byte, simulation type, world type and tick rate | the reads in section 4.5 |
| Whether the session's `game-variant` copy alone gives a client the host's file | a client with no staged file, section 4.5 |
| Which variant id a client's replicated flag creation passes | moot for the two-tag fix; matters for a one-tag design |
| Whether a pickup makes a new flag actor, and whether a respawn reuses a pooled biped | the logs in sections 2.2 and 2.3 |
| Whether `BlamGameAllegianceSubsystem` exists in a match | call `ActorTeamIsEnemy` on two teammates |
| Whether the first-person flag actor's mesh sync is ever updated | log its `GetVariantName()` |
| Whether any exe code writes a player's desired or assigned team | read membership `+0x1496`, `+0x14b8`, `+0x14b9` on the host at match start |
| Whether the sim's boundary drawing reaches the screen | set a visible shape on an object in a test variant |
| What happens when the 512-entry `megalo_objects` pool is full | read `0x41c3b0`'s failure path |
| The consumer of Megalo sound indices (actions 16 and 51) | not traced |
| The HCE end-user licence terms for user content | read at release; only Microsoft's general rules were reviewed |
