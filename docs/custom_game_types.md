# Custom game types on the hub

**Status:** 2026-10-21. Design. Nothing in this document is built unless a
line says so. Build CU4 (build lock in [build_lock.md](build_lock.md)).
"sim" is `HaloSimulation_tag_release.dll` (image base `0x180000000`), "exe"
is `HaloCampaignEvolved.exe` (image base `0x140000000`); every address is an
RVA into one of them, and says which. Each engine fact is marked
**VERIFIED** (the code or data that shows it was read) or **INFERRED**
(names, Reach knowledge, analogy, or a chain with an unread link).

**What exists today.** MJOLNIR ships two game types, Slayer and Capture the
Flag, as Megalo variants (`.mglo`) that `crates/blam-megalo` writes in CI
(`.github/workflows/release-mods.yml:101-110`) and that ship inside the
signed MJOLNIRLevelLoader zip. Team Slayer, King of the Hill and Oddball
exist only as names in UI tables. The engine side is in
[re/megalo_engine.md](re/megalo_engine.md) and the bitstream in
[re/megalo_variant_format.md](re/megalo_variant_format.md).

**In the working tree on 2026-10-21, not committed yet:**
a grammar-driven codec in `crates/blam-megalo` (`src/raw.rs`, `src/blf.rs`,
`src/dump.rs`, `grammar/megalo_cu4.json`, `tests/roundtrip.rs`) and the
command `mjolnir megalo dump` (`crates/blam-cli/src/megalo.rs:30-37`, `356`).
This design builds on them. Until they are merged and released, no shipped
tool has them.

The engine behind this design is mapped in
[re/reach_game_engine.md](re/reach_game_engine.md); what runs today, the
colour bugs and the other Reach modes are in [game_modes.md](game_modes.md),
whose section 5 lists the requirements this document turns into a design.

The goal: players write a game type, the hub checks it and lists it, the
launcher installs it, and a host can run it with a fireteam on any map that
has what it needs.

## Contents

- [What the engine gives a game type](#what-the-engine-gives-a-game-type)
- [The package](#the-package)
- [Authoring](#authoring)
- [Map compatibility](#map-compatibility)
- [Distribution](#distribution)
- [Safety](#safety)
- [Roadmap](#roadmap)
- [Open questions](#open-questions)

## What the engine gives a game type

A game type is data. The sim's Megalo engine (engine index 2) interprets it:
triggers, conditions and actions, plus the options, traits, teams and labels
the variant carries. These are the facts the rest of the design rests on.

| # | Fact | Where | Status |
|---|---|---|---|
| 1 | At every round reset, with the Megalo engine running, the sim reads `<name>.mglo` (at most `0x5000` bytes) from `HotReload\` when its name buffer is set, decodes it into the live variant and validates it. MJOLNIR sets the name and patches the reader's size query. | sim `0x2ad560`, reader `0x3f8bb0`, name buffer `0x152a7c0`, patch at `0x3f8a8d`; `native/map_registry/mjolnir_map_registry.c:1279`, `1324-1351` | VERIFIED |
| 2 | The decoder takes encoding versions `0x6a` and `0x6b` only. The grammar is complete: all 417 Megalo variants in MCC's Reach folders, and MJOLNIR's own, decode and encode back bit for bit. | sim `0x392a40`; `crates/blam-megalo/tests/roundtrip.rs` | VERIFIED |
| 3 | If the variant's object-type bitset names a type the loaded `multiplayer_object_type_list` (motl) does not have, with a tag, the sim wipes the whole script and the match runs with no rules. Nothing reports it. | sim `0x409c40`, `0x40a310` | VERIFIED |
| 4 | The decoder enforces almost none of the format's counts or sizes; the runtime trusts most indices. | sim `0x392a40`, `0x3949c0`, executor `0x399110`, sequencer `0x423a70` | VERIFIED; see [Safety](#safety) |
| 5 | A fireteam host runs as a distributed server (simulation type 5) and a client as a distributed client (4): every engine asks for protocol 2, and only a session of class 1 forces protocol 0. | sim engine slot 99 `0x47d60` (`mov eax, 2`), session setter `0x4c1f20`, options builder `0x55e1c0` | chain VERIFIED; a live read of `[TLS+0x60]+0x11` is still pending |
| 6 | Each tick, a type-4 client runs only the trigger named by the variant's `local` entry point; the host runs every trigger whose attribute is 0 or 6. The `init` entry point runs on the host only; `local init` and `pregame` run on every machine at their events. | sim `0x3fe520` (Megalo vtable slot 113), slot 10 `0x3fd740`, slot 8 `0x3fd550` | VERIFIED |
| 7 | Megalo global, player and team variables and HUD widget state travel to clients in the sim's replicated game-engine entities, and every machine decodes them against **its own** variant's declarations, network priorities and widget count. There is no identity check. Trigger code is not on the wire. | sim decoders `0x56fbc0`, `0x4053e0`, `0x573100`, `0x576e70`; apply `0x564ac0` | VERIFIED code; the effect of a mismatch (silent wrong values or dropped updates) INFERRED |
| 8 | The sim's own session parameter `game-variant` carries the host's variant to every peer at game start, and each peer copies it into its options. MJOLNIR then replaces it on every machine at the round reset with the staged file. | sim `0x4c1f20`, `0x55c730`, `0x55e1c0` (session `+0x6340`, chunks of `0x200`) | VERIFIED; which arrives last on a client is open |
| 9 | Player and team scores (`G+0x32c0`, `G = [TLS+0x38]`) replicate into each client's sim. | sim `0x577520` (`game-engine-statborg` apply) | VERIFIED |
| 10 | An object's owner team (its multiplayer block `+0x19`) replicates to clients. | sim `0x508a10`, `0x504ea0`, `0x5b3220`, `0x66af70` | VERIFIED |
| 11 | Unreal's per-frame snapshot carries no Megalo HUD widget, objective text or icon, waypoint icon, change colour, owner team or forced-colour trait. HCE draws none of them today. | sim producer `0xce50` and its call tree; exe snapshot readers | VERIFIED negative |
| 12 | Megalo can submit incidents to Unreal, except names in `[0x67ffff, 0xd00070]`, which are the engine's own (`kill`, `death`, `player_spawn`, `round_over` ...). Those are refused. | sim `0x41df50` (test at `0x41e11d`) | VERIFIED |
| 13 | An incident name Unreal's handler does not know falls into its default branch, which shows a HUD banner when the name is a row of the banner table and otherwise only prints debug text. No achievement, skull or terminal is awarded. | `BPC_MeteoriteIncidentHandlerComponent` (`mjolnir ue disasm`, exports 3, 4, 8, 9) | VERIFIED; the banner table's asset path INFERRED |
| 14 | The engine ends a round itself when a score reaches the score to win, and ends the game on the round count. It does not end a round on the time limit; a script must. | sim `0x2b1170`, `0x2afa70` | VERIFIED |
| 15 | The trigger loop runs 60 times a second. The CLI assumed 30 (`crates/blam-cli/src/megalo.rs:93-95`), so the tick-counted timers of every released variant run at half length; 60 is its default on branch `work/reach-game-mode-support-2eca91` since 2026-10-22. | sim `0x208a70` (options `+6` = `0x3c`), `0x20ff70` | VERIFIED statically |
| 16 | Teams are assigned by the host sim's session layer: the client's desired team if valid, else the least populated team. A script cannot move a player to another team in a team game. With teams off, `player.team = ...` gives script teams (Infection, Juggernaut) that the sim honours. | sim `0x4bab20`, `0x1823c0`, `0x408b20`, slot 53 `0x3fee90` | VERIFIED |
| 17 | In a Megalo game every player's allegiance byte is `0xff`, so the exe's `ActorTeamIsEnemy` calls teammates enemies. Only the multiplayer-team half of `BlamGameTeam` is usable. | sim `0x1823c0`; exe `0x7b3a270` | VERIFIED code; that the allegiance subsystem exists in a match INFERRED |
| 18 | The game-options mode byte of a Megalo game is 3 (multiplayer). `re/megalo_engine.md` says 2; that is superseded. | sim `0xf650`, `0x2055d0`, `0x55e1c0` | VERIFIED statically |
| 19 | Side swaps per round (designator rotate or shuffle) act from round index 1. MJOLNIR ends a match at the first `round_over` ([multiplayer_postgame.md](multiplayer_postgame.md)), so they never act. | sim slot 13 `0x3efae0` | VERIFIED |
| 20 | The sim's network layer runs over the exe's Party transport. The stubbed `net_*` names are console commands. `re/megalo_engine.md` ("Networking goes through Unreal") is superseded. | sim `0x4c2d80`, `0x532d40`, `0x4c7350`; exe `0x7ba1930` | VERIFIED |

Two consequences shape everything below.

- **Every machine must run byte-identical declarations.** Fact 7 means a
  client with a different variant decodes the host's state into the wrong
  variables. Today that is guaranteed by every machine staging the same file
  with the same settings line.
- **A game type is only as readable as what Unreal draws.** Fact 11 means a
  Bungie-style script that leans on widgets, waypoint icons or forced colours
  plays correctly but cannot be read on screen. The design keeps game types
  to what HCE draws until the channels in
  [Phase 4](#phase-4-presentation) exist.

## The package

A game type is a `.mjolnir` release archive ([mjolnir_format.md](mjolnir_format.md))
of a new manifest type, `gametype`.

```text
mjolnir.json              manifest: type "gametype", plus the gametype block
signature.json            the author's signature (the hub requires one)
gametype/variant.mglo     the variant, as the sim reads it (at most 0x5000 bytes)
gametype/layout.json      bit offsets of the fields a host may set (written by the compiler)
gametype/icon.png         256 x 256, for the hub, the launcher and the lobby
gametype/source.megalo    optional: the source text the variant was compiled from
docs/README.md            optional
```

The `.mglo` is the unit of exchange because it is what the sim loads (fact
1). It is also the community's format: MCC's Hot Reload loads a bare `.mglo`,
and 343's MegaloEdit compiles to it
(<https://www.halowaypoint.com/news/halo-mcc-august-update>). CU4 keeps the
`HotReload` directory name (sim string `0x7b6a80`, copied into the path
struct by sim `0x25d0`). VERIFIED.

### The manifest

```json
{
  "schema_version": 1,
  "name": "Headshots Only",
  "version": "1.0.0",
  "type": "gametype",
  "gametype": {
    "id": "headshots",
    "title": "Headshots Only",
    "description": "Free for all. Only a headshot scores.",
    "teams": "ffa",
    "players": { "min": 2, "max": 16 },
    "score_label": "headshots",
    "rounds": "one",
    "icon": "gametype/icon.png",
    "variant_sha256": "<hex>",
    "labels": [{ "name": "ce_health_pack", "min": 0 }],
    "object_types": ["health_pack"],
    "options": [
      { "index": 0, "name": "Kill bonus", "values": [0, 1, 2], "default": 1 }
    ]
  },
  "compat": { "min_build": "2026.06.26.1097863.1" },
  "deps": [{ "slug": "mjolnir-ce-runtime", "range": "^1.13.0" }]
}
```

| Field | Rule | Written by | Hub check |
|---|---|---|---|
| `id` | `^[a-z_]{1,24}$`, the regex lobbies and map modes already use (`hub/src/lib/api/lobby.ts:36`, `hub/src/lib/api/manifest.ts:31`). Unique across the hub; one listing owns an id for good, as a map owns its code. Reserved: `slayer`, `team_slayer`, `ctf`, `koth`, `oddball`, `empty`, `tick`. | author | unique, not reserved |
| `title`, `description` | 1 to 40 and up to 300 characters (proposed). The compiler also writes them into the variant's own name and description tables, which today always say "MJOLNIR". | author | length |
| `teams` | `"ffa"` or `2` | derived from the variant: teams flag (`o+0x2b8` bit 0) and enabled teams | agrees with the decode; 3 to 8 teams refused until [Phase 4](#phase-4-presentation) |
| `players` | `min`, `max` in 1 to 16 | author | range |
| `score_label` | what one point is ("kills", "captures"); `^[a-z ]{1,16}$` | author | shape |
| `rounds` | `"one"` (the match is the first round, as MJOLNIR runs every game now) or `"variant"` (the sim plays the variant's rounds) | author | `"variant"` refused until Phase 4 |
| `icon` | PNG, 256 x 256 | author | decodes, size |
| `variant_sha256` | SHA-256 of `gametype/variant.mglo` | derived | recomputed |
| `labels` | the variant's object filters: label name, minimum count, team and type constraints | derived | re-derived from the decode |
| `object_types` | names of every type the bitset sets, in the runtime's motl | derived | re-derived against the runtime at the `deps` floor |
| `options` | the variant's user options a host may set: name, values or range, default | derived (user options not marked hidden in the variant's `megalo_options_hidden` word, `o+0xe844`) | re-derived |
| `compat.min_build` | the game build, as for maps (`manifest.ts:53-58`) | author | as today |
| `deps` | must include `mjolnir-ce-runtime` | author | as today (`manifest.ts:59-66`) |

**The `.mglo` is the source of truth.** Every derived field is a cache for
readers that cannot decode a variant (the Lua lobby, the website). The
compiler writes them, and the hub decodes the variant on upload and refuses
an archive whose manifest disagrees. The meaning of the hidden word is
ReachVariantTool's name for the field (INFERRED); its offset is VERIFIED
(`crates/blam-megalo/grammar/megalo_cu4.json`, `megalo_options_hidden`).

**Why the runtime pack is the "min runtime".** Object types are indices into
the motl, and MJOLNIR's motl is an override that ships in the CE runtime pack
(`pakchunk990-MJOLNIRMOTL_P`, [map_distribution.md](map_distribution.md),
"The CE runtime pack"). It adds the CTF flag at 18 and the health pack at 19
to the 18 shipped weapons (`tools/level/build_ctf_flag.sh:80-87`). A
variant compiled against one motl is wrong against another (fact 3). So:

- a game type names its object types by name in the manifest, and depends on
  the runtime pack range whose motl has them;
- the runtime's motl becomes **append-only**: an entry, once released, keeps
  its index, so a game type compiled against runtime 1.x keeps working on
  every later 1.x.

`deps` and `compat` already exist and the launcher already installs a
dependency's floor first ([map_distribution.md](map_distribution.md),
"Dependencies"), so no new mechanism is needed. Like a map, type `gametype`
implies the code mods (MJOLNIRCore, MJOLNIRLevelLoader, MJOLNIRLobby,
MJOLNIRHud), at a version that understands game type packages.

### `layout.json`

The level loader patches the host's settings into each machine's copy of the
variant before staging it (`mods/MJOLNIRLevelLoader/Scripts/main.lua:5976-5992`).
Today it walks the variant with a Lua grammar reader
(`mods/MJOLNIRLevelLoader/Scripts/variant_settings.lua`), which stops at the
first player trait, user option or compressed string table (`:75`, `:155`).
MJOLNIRHud's reader has the same limits (`mods/MJOLNIRHud/Scripts/variant.lua:7-8`).
Any variant with user options, which is any useful custom game type, breaks
both.

Instead, the compiler writes the bit offset and width of each field a host
may set: score to win, time limit, the respawn and trait fields the settings
screen offers, and each user option's current value (a `u3` index or an
`s10` value, [re/megalo_variant_format.md](re/megalo_variant_format.md)).
Each has a fixed width in a given file, so writing a new value in place
leaves every later bit where it was. Lua then writes bits at
known offsets and needs no grammar. The CLI already does this for vehicle-set
labels (`filters_at` in `<out>.layout.json`, `crates/blam-cli/src/megalo.rs:308-320`;
read by `mods/MJOLNIRLevelLoader/Scripts/vehicle_sets.lua`). The hub
recomputes the offsets from its own decode and refuses a layout that
disagrees.

## Authoring

### The language

A text language, compiled by `blam-megalo`, is [Phase 3](#phase-3-the-language).
It is not built. Its principles:

- **Model it on what the community already knows.** Reach modders write
  Megalo in ReachVariantTool's dialect: Lua-like blocks, `for each player`,
  event blocks for the entry points, aliases for variable slots, declarations
  with network priorities, one name per opcode. ReachVariantTool's manual is
  CC0, so its names and descriptions can be reused freely. Its code is GPLv3
  and MJOLNIR is MIT: none of it is copied, translated or linked. The compiler
  is written from MJOLNIR's own grammar file, `grammar/megalo_cu4.json`,
  which already carries Reach's names as hints (`reach_names`).
- **One source of grammar.** The compiler, the decompiler, the validator and
  the hub's checks all read `grammar/megalo_cu4.json`. The decoder already
  does.
- **CU4's vocabulary, not Reach's.** Object types resolve by name against
  the runtime's motl; incidents against CU4's `game_incident` tag (all 123
  incident indices Bungie's variants raise have the same names there,
  VERIFIED by tag dump); waypoint icons, sounds and widget icons are Reach's
  names and are not checked for CU4.
- **Seconds, not ticks.** Timers are declared in seconds and scaled by the
  sim (sim `0x408d00`). Counting ticks bakes in a tick rate, which is how the
  CLI's CTF flag reset and health-pack respawn came to run at half length
  (fact 15).
- **The compiler owns declarations.** It allocates variable slots, sets
  network priorities and builds the object-type bitset from every type the
  script uses. Bungie's bitsets are exactly the union of the types their
  opcodes and labels name (VERIFIED over the corpus), so nothing is lost.
- **Client code is explicit.** On fireteam clients only the `local`,
  `local init` and `pregame` entry points run (fact 6). The language keeps
  per-player presentation in those blocks, and says so in its errors.

An example, in illustrative syntax that is not final:

```text
game type team_kills
  teams 2
  score to win 50
  score label "kills"

every tick, for each player:
  if current_player died this tick by a kill:
    killer = killer of current_player
    if killer.team != current_player.team:
      killer.score += 1
```

This is a whole Team Slayer. It compiles to one trigger that runs for each
player (trigger type 1), a Killer Type condition with the kill bit
(condition 3), Get Killer (action 29), a Compare on the two teams
(condition 1) and Modify Score (action 1). The team's total follows from the
player scores, because the variant's team scoring is `sum` (sim `0x2b0180`
→ slot 2 `0x3ef690`, mode 0). The engine ends the round at the score to win
(fact 14), so the script needs no end check.

### The decompiler

`mjolnir megalo dump <file.mglo|file.bin> [--out <file>]` lists everything a
variant holds through the grammar: header, options, traits, teams, user
options, strings in every language, statistics, variables, widgets, entry
points, the object-type bitset, labels, and the script as triggers with named
conditions and actions placed at their action offsets. It reads MCC `.bin`
files (BLF) as well as bare `.mglo`, refuses non-Megalo engines, and states
in its header whether the file encodes back bit for bit
(`crates/blam-cli/src/megalo.rs:356-406`, `crates/blam-megalo/src/dump.rs:1074`).
Not committed yet, as above.

When the language lands, `dump` prints it, and the tests require
`compile(dump(x)) == x` bit for bit over MJOLNIR's variants and, on a
machine with MCC installed, Bungie's.

### Tool commands

| Command | Does | State |
|---|---|---|
| `mjolnir megalo dump` | decompile and round-trip check | working tree, not committed |
| `mjolnir megalo write --mode slayer\|ctf\|...` | MJOLNIR's built-in game types | shipped |
| `mjolnir megalo check <file> [--runtime <dir>]` | the validator below, against the installed runtime's motl | proposed (Phase 1) |
| `mjolnir megalo compile <source> --out <dir>` | source to `variant.mglo`, `layout.json` and the derived manifest fields | proposed (Phase 3) |
| `mjolnir megalo import <file.bin\|.mglo>` | an author's own Reach variant: remap Reach object-type indices, trait and loadout weapon indices to CU4's by name | proposed (Phase 3) |
| `mjolnir gametype pack <dir> --sign` | build and sign the archive, as `mjolnir map pack` does | proposed (Phase 2) |

`import` is for variants an author made. Bungie's variants in an MCC install
are Microsoft content: they may be read on the user's machine as a test
oracle, never committed, uploaded or shipped. Two CU4 differences make a
ReachVariantTool file misread unless it goes through `import`: a type-5
trigger with no label is one bit in CU4 and five in ReachVariantTool, and
CU4's content header has no hopper id for activity 2 (sim `0x38f5d0`).
VERIFIED. Reach object-type indices also differ: Reach's flag is 3, CU4's
(MJOLNIR's) is 18, and CU4's 3 is the magnum.

### Validation

`blam_megalo::validate` runs over the decoded tree (`raw::Tree`), wherever a
variant is about to be decoded by the sim: the compiler, `megalo check`, the
hub on upload, the launcher on install and, in part, the native loader before
staging. CU4 checks almost nothing itself (fact 4), so these rules are the
boundary. Rejected:

| Area | Rule | Why (sim) |
|---|---|---|
| File | at most `0x5000` bytes; version `0x6a` or `0x6b`; decodes strictly and encodes back bit for bit, with zero padding bits | reader buffer (fact 1); a misaligned file shows here |
| Main string table | at most 112 strings; data at most `0x4c00` bytes; if compressed, the embedded big-endian size equals the stream's size field, is at most `0x4c00`, and inflates to exactly that | `0x392a40`, `0x3949c0`, `0x32a620` |
| Other string tables | name and category data at most `0x180`; description `0xc00`; team names `0x20` | `0x394590`, `0x394d30`, `0x397f80` |
| Counts | script traits 16; user options 16, values per option 8; conditions 512; actions 1024; triggers 320; statistics 4; labels 16; HUD widgets **4**; variables per scope at their grammar maxima; map permissions 32 | each store is exactly the maximum and the next field follows it, so one more overwrites it; a fifth widget overwrites player 0's engine state (`0x40a130`) |
| Opcodes | condition type at most 17; action type at most 106; trigger type at most 5; compare operator at most 5 | 6 and 7 index six-entry jump tables and crash (`0x39ed40`, `0x423fc0`) |
| Ranges | every trigger's conditions and actions inside the arrays; every action offset inside its trigger | the sequencer trusts them (`0x423a70`) |
| Nesting | every Run Nested Trigger index below the trigger count; no cycle among nested calls; depth at most 32 | no bound and no depth limit (executor case `0x14` in `0x399110`) |
| Object types | every set bit names a motl entry with a tag in the target runtime; every type operand (Create Object, Create Object Equidistant, Add Weapon To Biped, respawn vehicles, Object Type condition, label type filters) is a set bit | the bitset check wipes the script (fact 3); type operands index the motl unbounded (`0x41c3b0`, `0x421b80`) |
| Incidents | an index that names a CU4 incident outside the refused range (the list comes from CU4's `game_incident` tag, as `defs/hce` holds other tag facts) | out-of-range behaviour is undefined (`0x41df50`); refused names are dropped (fact 12) |
| Teams | `ffa` or two enabled teams with distinct designators | two teams on one designator both get the points (`0x41c080`) |
| Actions 97, 100 | Record Griefer Penalty and Call HaloScript Function refused | see [Safety](#safety) |

Warnings, shown to the author and the reviewer:

- sounds (actions 16 and 51): the Megalo sound table has 1 entry of 95 set,
  so most are silent (VERIFIED, tag dump);
- waypoints, widgets, objective text, progress bars and forced colours: not
  drawn by HCE (fact 11);
- a label filter count that leaves no room for the map's vehicle-set labels,
  which share the 16 slots ([Map compatibility](#map-compatibility));
- Kill Feed Message, Play Sound, Submit Incident or Create Object in a
  trigger with no condition, which runs every tick.

**One discrepancy to fix in Phase 1.** The main string table's offsets are
stored per language in `0xe0` bytes, 112 entries (`0x738 + 12 × 0xe0 =
0x11b8`, where the string data begins). A 113th string writes into the next
language's offsets, and for the last language into the string data. The CLI
allows 127 strings (`crates/blam-cli/src/megalo.rs:298`). Shipped variants
stay well under 112 (the CTF variant has 76), so nothing is broken today;
the CLI limit should be 112.

## Map compatibility

**Today.** A map names its game types: the level file's `modes`
(`tools/level/gen_ce_level.py:1331`: Slayer, plus CTF when the CE scenario
has flags), copied into `maps.json` and the map pack's manifest
(`manifest.ts:31`) and into the hub's `map_listings.modes`
(`hub/migrations/0012_maps_and_lobbies.sql:17-18`). The lobby offers a mode
when the map lists it and `variants\<id>.mglo` exists
(`mods/MJOLNIRLobby/Scripts/main.lua:118-128`). Nothing checks that the
variant's labels are on the map. A hub game type cannot be listed by every
map author in advance, so this does not scale.

**Proposed: labels, as Reach did.** A Megalo variant already states what it
needs from a map. Each object filter (label) has a name, optional type, team
and number constraints, and a "map must have at least" count
([re/megalo_variant_format.md](re/megalo_variant_format.md), LABEL).
Bungie's CTF, for example, requires at least one `ctf_flag_return` object
(VERIFIED, decode of `ctf_054`). The map side is already there: a scenario
placement's multiplayer data carries a Megalo label, an owner team, a spawn
order and a boundary shape (`defs/hce/tag-definitions.json`, scenario
multiplayer object struct), and the conversion writes labels for CTF stands,
spawns and health spots (`tools/level/gen_ce_level.py:1080`, `:1121`).

1. **Maps publish a label inventory.** `mjolnir level bake` (or the
   launcher's registration rebuild, which already reads every installed
   level) writes a `labels` list into `maps.json`: each label with its count
   per team. Converted maps also keep CE's other netgame markers as level
   markers (oddball spawns, hill points, race checkpoints,
   `defs/level/ce-tag-map.json:56-66`), so Oddball, KOTH and Race positions
   exist; a CE hill is a set of points, and the converter must fit a
   cylinder or box to it (INFERRED).
2. **A game type is offered on a map when** every label filter's minimum is
   met (with its team and type constraints), every object type it names is in
   the installed runtime's motl, the map's player range overlaps the game
   type's, and the map is a multiplayer level. A game type with no label
   requirements (a Slayer variant needs only spawn points) fits every
   multiplayer map.
3. **`modes` stays** as the map author's explicit list for the built-in game
   types, and as an override that hides a type the labels would allow.
4. **The hub** filters `GET /maps?mode=` and the game type pages by the same
   rule, from `map_listings` and the new game type listing.

**Shared budgets.** A variant holds 16 label filters, and CE's vehicle sets
use the same slots: the loader appends one filter per vehicle label the
host's settings pick and drops what does not fit
(`mods/MJOLNIRLevelLoader/Scripts/main.lua:5993-6022`). Seventeen filters put
every object out of play and lost the GPU device on Death Island
(`crates/blam-cli/src/megalo.rs:280-282`). The vehicle-label pool also takes
70 strings (`ce_<type>_<rank>`, `megalo.rs:283-300`). A game type that wants
CE vehicle sets must leave room for both, and the compiler reports how much
it leaves.

## Distribution

### On the hub

A game type is a `content` mod, as a map is. `mods.type` is a trust tier
(`hub/migrations/0001_init.sql:64`) and stays one; what makes a mod a game
type is a side table, the pattern maps use (`0012_maps_and_lobbies.sql:13-23`).

| Change | Where | What |
|---|---|---|
| Manifest | `hub/src/lib/api/manifest.ts:25` | `type` gains `"gametype"`; a `gametype` block, required for that type only (the refinement at `:68-71` extends to it) |
| Scanner | `hub/src/lib/api/scan.ts:37`, `:289-295` | allow `gametype/variant.mglo`, `gametype/layout.json`, `gametype/icon.png` and `gametype/source.megalo` for that type only; `.mglo` stays forbidden everywhere else |
| Scanner | `scan.ts:330-356` | for a game type: decode and validate the variant ([Validation](#validation)), compare every derived manifest field, and skip the "at least one container" rule (`:356`), since a game type carries none |
| Validator in the Worker | new | the Rust validator built to WASM, so the hub and the launcher run the same code; a TypeScript port would be a second grammar to keep in step |
| Schema | new migration (`0023`) | `gametype_listings`: `mod_id`, unique `game_type` id, `title`, `teams`, `score_label`, `labels` JSON, `object_types` JSON, `options` JSON, `variant_sha256`, `official`, `updated_at` |
| Review | `hub/src/lib/api/publish.ts:78`, `:617-631`; `release_reviews` (`0012:29-37`) | a release from an author below trust level 2 waits for a moderator, exactly as a map does. The reviewer sees the scanner's warnings and the `megalo dump` listing |
| Signing | [mod_signing_design.md](mod_signing_design.md) | unchanged: `REQUIRE_SIGNED_UPLOADS` is on, so every release carries the author's `signature.json` |
| Lobbies | new migration, like `0016_lobby_map_release.sql:7-8` | `game_type_release_id`, `game_type_version`, `game_type_sha256` |
| Matches | `0014_matches.sql:33-34` | `game_type_release_id`, so a match's results are attributed to the exact game type. `team IN ('red', 'blue')` (`:61`) stays while game types are limited to two teams |
| Website | `hub/src/kit/types.ts:669-675`; `hub/src/app/games/page.tsx:22`, `maps/page.tsx:19`, `matches/page.tsx:23` | names and mode filters come from `GET /api/v1/gametypes`, not three hard-coded arrays |

The hub stores what is derived, so the lobby list, FIND GAMES and the website
never decode a variant.

### The launcher

| Piece | Model | What |
|---|---|---|
| Install folder | `ue4ss\MJOLNIRMaps\<CODE>\` (`apps/launcher/src-tauri/src/maps.rs:1-16`) | `ue4ss\MJOLNIRGameTypes\<id>\`: `variant.mglo`, `layout.json`, `gametype.json` (the manifest's block), `icon.png`, and the `.mjolnirhub` marker. Never inside the signed loader's `variants\`: the launcher digests code mod folders, and hand-installed or hub files there would mix reviewed and unreviewed content and read as "Modified" ([map_distribution.md](map_distribution.md), "Where things go") |
| Index | `ue4ss\MJOLNIRMaps\maps.json` | `MJOLNIRGameTypes\gametypes.json`, rewritten on every install, update or removal |
| Check on install | `verify_installed` re-hashes cached files (`apps/launcher/src-tauri/src/hub.rs:1487`) | the launcher links `blam-megalo` and runs the validator against the installed runtime before it writes the folder |
| Live install | `--install-map <CODE> [--release <id>] --progress <file>` (`hub.rs:1341-1345`, `lib.rs:1929`; [live_map_install.md](live_map_install.md)) | `--install-gametype <id> [--release <id>] --progress <file>`. No mount, no restart: the loader reads the file when the match starts |
| Links | `mjolnir://map/<CODE>` (`links.rs`) | `mjolnir://gametype/<id>` |
| Dependencies | a map's `deps` floor installed first | the same, for the runtime pack |

MJOLNIR's own Slayer and CTF become official game type packages in the same
format, shipped by CI. Then one code path reads every game type, and the
built-in table in the lobby goes away.

### The lobby lists installed game types

Today the lobby has a fixed table of five modes
(`mods/MJOLNIRLobby/Scripts/main.lua:61-67`), and MJOLNIRHud a table of three
(`mods/MJOLNIRHud/Scripts/scoreboard.lua:5-9`). A mode's identity is repeated
in at least 13 places across Lua, Rust, Python and the hub.

Proposed:

- `MODES` is built at screen time from the official game types and
  `MJOLNIRGameTypes\gametypes.json`: id, title, description, teams.
- `modesFor(map)` (`main.lua:118-128`) applies the
  [compatibility rule](#map-compatibility) instead of a file-exists check.
- The settings screen offers the game type's `options` beside the existing
  universal settings ([host_game_settings.md](host_game_settings.md)), as
  keys `opt.<id>.<index>=<value>` in the settings line. Per-type keys keep
  the line right when a post-game vote changes the game type, as
  `score.<mode>` does today. The hub's settings regex
  (`lobby.ts:44-49`) allows digits only, so a range option with negative
  values needs a sign added there.
- MJOLNIRHud takes the title, `score_label` and teams for its scoreboard from
  `gametype.json`. Its scores come from incidents per known mode
  (`scoreboard.lua`), which cannot follow an arbitrary script; facts 9 and
  14 allow reading the sim's own scores on every machine instead
  ([Phase 4](#phase-4-presentation)).

### From the host to every fireteam client

**Today** the host's game type reaches clients through the insertion point
index of the host's travel:

| Channel | Carries | Where |
|---|---|---|
| `pending_variant.txt` | the mode id, host only | Lobby `main.lua:181-186` → loader `main.lua:6031-6043` |
| travel URL `InsertionPointIndex` | slot 0 to 7 | Lobby `main.lua:177` → loader `switchForUrl` (`main.lua:6045-6056`), mapped by `GAME_TYPE_SLOTS` (`main.lua:5919`) |
| join under way | slot from the listing's `game_type` | `mods/MJOLNIRLobby/Scripts/games.lua:169`, `:221` |
| `lobby` message | map, mode id, settings line, map index, map release | Lobby `broadcastLobby` (`main.lua:3077-3088`) → client handler (`main.lua:3015-3075`); the mode id reaches the UI only |

A converted map keeps 8 copies of its insertion point
(`crates/blam-cli/src/level.rs:646-647`), so at most 8 game types can be
told apart this way, and an id missing from `GAME_TYPE_SLOTS` makes a client
fall back to the level's default variant (`main.lua:5967`), Slayer, while
the host runs something else. VERIFIED code. That fallback, more than any
hub schema, is what blocks custom game types.

**Proposed** (the lobby already hands the settings line to the loader the
same way):

1. The `lobby` message keeps the mode id in field 2 and adds the game type's
   hub release id, version and SHA-256 as fields 7 to 9. The post-game
   `vote` message (`main.lua:2441-2452`) carries the same three for each
   option, since a vote can change the game type.
2. A client that lacks that release offers to fetch it, as
   `Live.offerHostMap` does for maps (`main.lua:2984`), through the
   launcher's `--install-gametype`.
3. Host and client write the chosen id and SHA-256 to a file the loader
   reads at travel, as they write `variant_settings.txt` today
   (`main.lua:147-155`, `:3046`; `games.lua:482-486` for a join from FIND
   GAMES).
4. The loader's `switchFor` (`main.lua:5942`) takes the game type from that
   file, reads `MJOLNIRGameTypes\<id>\variant.mglo`, checks its SHA-256
   against the file, patches the settings through `layout.json`, and stages
   it. `GAME_TYPE_SLOTS` stays only as the fallback for a peer on an older
   MJOLNIR; hub game types always start at slot 0.
5. A join under way gets the release id and SHA-256 from the hub listing
   (the new `lobbies` columns), fetches the game type if needed, and writes
   the same file before the join goes out.

The settings patch and the vehicle-set filters are computed from the same
settings line and the same level on every machine
(`main.lua:5993-5996`), so every machine stages byte-identical bytes.

### Do clients need the file?

**Yes, today and through Phases 1 and 2.** Two facts decide it.

- Each machine decodes the host's per-tick Megalo state against its own
  declarations (fact 7). Byte-identical staging guarantees they match.
- MJOLNIR's loader replaces the live variant on every machine at the round
  reset (fact 1), which overwrites whatever the session delivered (fact 8).

A client never runs the host's rules (fact 6), so what it needs from the
file is the declarations, its `local`, `local init` and `pregame` triggers,
and the options and strings its HUD shows.

**It may become no.** If a client that stages nothing still ends up with the
host's file variant through the `game-variant` session parameter, the
client's copy comes from the host by construction and cannot mismatch. One
live read settles it: on a client with no `.mglo` staged, after the first
round reset, read the live variant (`o = [TLS+0x60]+0x15f4`): its encoding
version at `o+0x5dc0` (the default variant has `0x6b`, MJOLNIR's files
`0x6a`) and its trigger count at `o+0x63f4`, and compare with the host.
The lobby DLL already reads `[TLS+0x60]` on the sim thread
(`native/lobby/mjolnir_lobby.c:2776-2790`).
Even then a client wants `gametype.json` for its lobby and HUD, which the
lobby message can carry instead of a download.

## Safety

### What a Megalo variant can and cannot do

Lua mods are code: UE4SS Lua has `io`, `os.execute` and `package.loadlib`,
which is why the hub ships Lua only from reviewed, signed CI
([hub_architecture.md](hub_architecture.md), section 2). A Megalo variant
is data for an interpreter with a fixed instruction set: action ids 0 to 106
and condition ids 0 to 17, where 0 is "none" in both.

| It cannot | Evidence | Status |
|---|---|---|
| read or write files, open sockets, load libraries or call native code | every action handler acts on sim state (sim executor `0x399110`); the only effects outside the match are incidents, kill-feed and sound events, and a theater film marker written only while a film records (`0x41e310`) | VERIFIED |
| raise the engine's own incidents (`kill`, `death`, `player_spawn`, `round_over`, `game_over` ...) | refused range at sim `0x41e11d` | VERIFIED |
| unlock achievements, skulls or terminals | Unreal's default incident branch only prints debug text for them | VERIFIED |
| move a player to another team in a team game | sim slot 53 `0x3fee90` ignores the script's team byte when teams are on | VERIFIED |
| crash the executor with an unknown opcode | action types 107 to 127 fall to the switch's no-op default | VERIFIED |

| It can, inside the match | Evidence | Status |
|---|---|---|
| change any score, end the round, kill, heal, give weapons, apply traits, create and delete objects | the action table | VERIFIED |
| show a HUD banner: any incident it may submit (by index into CU4's incident list) whose name is a row of the banner table | default branch, `HandleHudBannerMessage` | VERIFIED |
| flood the kill feed or the sound queue every tick (actions 16, 51) | posts engine event `0x1e` per recipient (sim `0x5132f0`) | VERIFIED |
| accrue a griefer penalty on any player every tick (action 97) | sim `0x35d530` | VERIFIED call; that it can boot a player INFERRED |
| run any HaloScript function the loaded scenario carries (action 100) | sim `0x36c1a0`, `0x1f6b60`, `0x1fcf30`, bounded to scripts that exist | VERIFIED bound; converted maps are cloned from campaign canvases, so campaign scripts may be reachable (INFERRED) |
| fill the 512-entry `megalo_objects` pool | Create Object | what happens when it is full is open |

Hub game types refuse actions 97 and 100 ([Validation](#validation)).
Scores a script sets are whatever the script says, so match records carry
the game type release (the `matches` change above) and are never mixed with
official game types' statistics.

### Unvalidated input is not safe data

CU4's decoder trusts the file. A crafted `.mglo` can do worse than misbehave:

- **The main string table overruns its buffer with chosen bytes.** The
  reader copies the string data into a `0x4c00`-byte buffer at `o+0x11b8`
  with no comparison against `0x4c00`. Uncompressed, the length is the
  stream's `u15` size, at most `0x7fff` bytes; by arithmetic the overrun
  then stays inside the `0xf860`-byte variant object but covers the encoding
  version and the whole script region. Compressed, the inflater's output
  length is the stream's own big-endian `u32`, which CU4 never checks, and
  zlib can expand the at most `0x5000` input bytes far beyond the buffer.
  VERIFIED (sim `0x3949c0`, `0x32a620`); the inflater itself (sim
  `0x6c7b20`) was not read, and whether the overrun can be turned into code
  execution has not been examined. Treat it as if it could.
- **Counts past the stores overwrite the next field** (table under
  [Validation](#validation)), and a fifth HUD widget overwrites player 0's
  engine state. VERIFIED (sim `0x392a40`, `0x40a130`).
- **Indices the runtime trusts:** nested trigger calls with no bound and no
  depth limit (a self-call exhausts the stack), trigger condition and action
  ranges, object-type operands into the motl, and the six-entry jump tables
  behind compare operators and trigger types. VERIFIED (sim `0x399110`,
  `0x423a70`, `0x41c3b0`, `0x421b80`, `0x39ed40`, `0x423fc0`).

So "sandboxed like a game type" ([map_distribution.md](map_distribution.md))
holds only for a variant that passed the validator. The validator is the
security boundary, and it runs at every point where bytes could come from
someone else:

1. **The hub, on upload.** Nothing that fails it is listed or downloadable.
2. **The launcher, on install.** A tampered cache or a bypassed hub is
   caught on the player's machine.
3. **The native loader, before staging.** `mjolnir_megalo_variant` copies
   `native\variant.mglo` to `HotReload\mjolnir.mglo` with no check
   (`native/map_registry/mjolnir_map_registry.c:1339`). Before that copy it
   refuses a file over `0x5000` bytes, a version other than `0x6a`/`0x6b`,
   and any string table whose sizes break the rules above, with a log line
   and no name written, so the sim runs the default variant. That is a few
   dozen lines of C over the start of the stream. The full validation
   happened at install.
4. **After the round reset, a read-back.** The native half reads the live
   variant's version (`o+0x5dc0`) and trigger count (`o+0x63f4`) on the sim
   thread and logs "decoded" or "wiped", so a game type the sim silently
   rejected (fact 3) is visible. `o` is `[TLS+0x60]+0x15f4`.

This is why a game type can live in the content tier, with open upload,
signing and review for new authors, rather than with Lua and native code:
once validated, what its bytes can do is bounded by the interpreter, not by
who wrote them.

Runtime patches that bound the sim's own checks are a fallback only. They
would track CU4 addresses across game updates like the seven switch patches
(`mjolnir_map_registry.c:1193-1236`), and validating before decode makes them
unnecessary.

**An open risk outside the hub.** The `game-variant` session parameter
(fact 8) delivers the host's variant to clients natively. Its serializer was
not traced, so whether a modified host can push a malformed variant into a
client's sim this way is unknown. The risk exists today, with or without hub
game types. It needs its own look before Phase 2 ships.

### Content terms

HCE ships no EULA text in its install, and the Steam EULA was not reviewed.
Halo fan content falls under Microsoft's Game Content Usage Rules
(<https://www.xbox.com/en-US/developers/rules>): no selling, a notice that the
game is Microsoft's and the item is not endorsed, and nothing objectionable.
The hub's terms for game types restate these. Bungie's and 343's own variants
are Microsoft content and are never accepted as uploads; a moderator checks,
and the hub can refuse an archive whose variant hash matches one of the
distinct Bungie payloads (hashes computed on a maintainer's machine, not the
files). ReachVariantTool's code is GPLv3 and is not used; its CC0 manual is.

## Roadmap

### Phase 1: local game types (smallest useful step)

No hub change. Each step is useful on its own:

1. **`blam_megalo::validate` and `mjolnir megalo check`**, with the CLI's
   string limit set to 112 and its tick-rate default to 60 (or its two
   tick-counted timers moved to Megalo timers).
2. **The game type folder.** `MJOLNIRGameTypes\<id>\` with `variant.mglo`,
   `layout.json` and `gametype.json`. The lobby builds its list from it and
   the HUD its scoreboard modes. Team Slayer can then ship as a folder
   instead of edits in 13 places (KOTH and Oddball need the object types
   of [Phase 5](#phase-5-reachs-roles-in-the-runtime) first), and a tester
   can try a variant on several PCs by copying one folder.
3. **The game type id travels in the lobby message**, and the loader reads
   it instead of `GAME_TYPE_SLOTS`, which stays as the fallback for older
   peers.
4. **The native size and structure gate** before `CopyFileA`, and the
   decode read-back in the log.

### Phase 2: the hub

The manifest type and scanner rules, the WASM validator, `gametype_listings`
and review, the `lobbies` and `matches` columns, the launcher's install, live
install and `mjolnir://gametype/<id>` link, the in-game offer to fetch a
missing game type, settings through `layout.json`, and the website reading
game types from the listing. Before it ships: the session-parameter
serializer look ([Safety](#unvalidated-input-is-not-safe-data)). Until Phase 3,
authors write variants with the typed builder in `crates/blam-megalo`, or
bring files from other tools that pass `megalo check`.

### Phase 3: the language

`mjolnir megalo compile`, `dump` printing the same language, `import` for an
author's own Reach variants with name-based remapping, and the
`compile(dump(x)) == x` tests. Editor support (syntax highlighting) can
follow.

### Phase 4: presentation

What makes Bungie-style game types readable in HCE:

- a native reader of the sim's scores on every machine (fact 9), feeding the
  HUD instead of incident tallies;
- a native reader of objects' owner team (fact 10), the generic fix for any
  game type's team-coloured objects, CTF flags included;
- the forced-colour trait (Infection, Juggernaut) and script teams under a
  free-for-all header, which the `BlamGameTeam` component does not show
  (fact 16);
- Megalo widgets, objective text and waypoints, for example mirrored into
  the HaloScript navpoint list Unreal already draws (sim `0x473960`), which
  has a priority and a label but no icon (INFERRED, untried);
- `rounds: "variant"`: let the sim play a variant's rounds, which side-swap
  modes need (fact 19);
- three to eight teams: the lobby, armour, HUD and the hub's `matches` team
  values are red and blue only.

### Phase 5: Reach's roles in the runtime

Append motl entries and tags for the objects Bungie's modes use and CU4
lacks: the bomb, the skull, the hill marker, flag stands and capture plates,
respawn zones (multiplayer type 16, which CU4's spawn scoring honours, sim
`0x307d10`), kill and safe volumes (types 25 and 26, sim `0x424150`). Each
lands in the runtime pack under the append-only rule, and the language gains
the names.

## Open questions

| Question | What settles it |
|---|---|
| Does a fireteam run simulation types 5 and 4? | live read of `[TLS+0x60]+0x11` on host and client during a match |
| Does the native `game-variant` copy reach a client that stages nothing? | the live read under [Do clients need the file?](#do-clients-need-the-file) |
| Can a host push a malformed variant through that session parameter? | trace the parameter's serializer and the client's copy (sim `0x51d0c0`, `0x51d480`, `0x216300`) |
| What does Create Object do when `megalo_objects` is full? | read sim `0x41c3b0`'s failure path |
| Which code consumes a Megalo sound index? | trace engine event `0x1e` after sim `0x5132f0` |
| Do Megalo waypoints mirrored into the navpoint list draw? | a live test with one waypoint |
| Does `BlamGameAllegianceSubsystem` exist in a match? | call `ActorTeamIsEnemy` on two teammates |
| Is the trigger loop 60 a second live? | read `[TLS+0x98]+6` in a match |
| Can MJOLNIR let the sim play several rounds without the post-game flow ending the match? | a Phase 4 change to MJOLNIRHud's end detection, then a two-PC test |

## Related documents

- [re/reach_game_engine.md](re/reach_game_engine.md): the full map of the
  sim's game-engine layer and what the host does with it; the source of the
  facts table above.
- [game_modes.md](game_modes.md): what runs today, the flag and armour
  colour fixes, the other Reach modes and how to prove a mode correct. Its
  section 5 leaves the trust tier undecided; this document decides it
  ([Safety](#safety)).
- [re/megalo_engine.md](re/megalo_engine.md): the engine switch, the file
  loader and its patch. Its mode byte (2) and its networking line are
  superseded by facts 18 and 20.
- [re/megalo_variant_format.md](re/megalo_variant_format.md): the
  bitstream. Its grouping of actions 30 and 31 with the trigger-block action
  is wrong: both take a player and a number, and only action 99 reads a
  trigger block. `grammar/megalo_cu4.json` is the full grammar.
- [map_distribution.md](map_distribution.md): map packs, the runtime pack,
  dependencies. Its Phase 6 ("custom game types per map") becomes this
  document; map packs still carry no `.mglo`.
- [hub_architecture.md](hub_architecture.md), [mod_signing_design.md](mod_signing_design.md),
  [mjolnir_format.md](mjolnir_format.md): trust tiers, signing, the archive.
- [live_map_install.md](live_map_install.md): the live install this
  design copies.
- [host_game_settings.md](host_game_settings.md): the settings line.
- [multiplayer_hud.md](multiplayer_hud.md), [multiplayer_postgame.md](multiplayer_postgame.md):
  the HUD and the one-round match.
</content>
</invoke>
