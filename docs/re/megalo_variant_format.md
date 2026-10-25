# The Megalo variant bitstream (CU4)

**Source:** static reading of the CU4 simulation's own decoder,
`HaloSimulation_tag_release.dll` `0x392a40` (Megalo vtable `0x83c3b8` slot 5)
and everything it calls, 2026-09-30. Field order and widths are verified from
the decompiled readers; meanings are named where the code or ReachVariantTool's
public layout makes them clear. Written by `crates/blam-megalo`
(`mjolnir megalo write`); overview and the loading path in
[megalo_engine.md](megalo_engine.md).

**Update 2026-10-21:** the whole grammar is now read out, including every
action's parameters (per-action decoder sim `0x39cf20`, executor sim
`0x399110`), and proven by a round trip: all 417 of Bungie's Reach Megalo
variants in MCC decode and re-encode bit for bit (section *The round trip*
below). It lives in one file, `crates/blam-megalo/grammar/megalo_cu4.json`,
which the codec and `mjolnir megalo dump` read. The tables after the grammar
block give every action, condition, operand kind and option field. How the
engine runs a variant, and what the Unreal host does with it, is in
[reach_game_engine.md](reach_game_engine.md); how MJOLNIR's game types use
it, in [`../game_modes.md`](../game_modes.md). Every address on this page is
a sim RVA.

```text
CU4 HaloSimulation_tag_release.dll - Megalo variant bitstream grammar as read by 0x392a40 (vtable 0x83c3b8 slot 5)
All RVAs CU4. "o" = variant object (= variant + 4). Store offsets are o-relative.

BIT READER (0x2abe70 u(n), 0x206580 bool, 0x2abf60 u64, 0x2abc60 bytes)
  - MSB-first; the byte stream is consumed as big-endian 64-bit words; u(n) returns the next n bits unsigned.
  - bool = 1 bit, 1 = true.  "opt(n)" below = bool, if bool==1 -> absent (0xff / -1) else u(n)  [unless marked PRESENT-IF-1]
  - "v-1" = stored value is read value minus 1 (so encode stored+1; 0 encodes "none"/-1)
  - signed10 = u(10) sign-extended from bit 9
  - past the end of the buffer the reader returns zeros (CU4); the repo codec reports an error instead

TOP LEVEL (0x392a40)
  u32  encoding version -> o+0x5dc0; must be 0x6a or 0x6b else decoder returns immediately
  u32  (ignored; build/engine version)
  BASE                                         (0x396790)
  u5   player trait count (max 16); each:  u7 name string idx (o+0x5df8)  u7 desc string idx  TRAITS
  u5   user option count; each:
         u7 name idx, u7 desc idx, bool is_range
         if !is_range: u3 default index, u4 value count, then per value: signed10 value, u7 name, u7 desc
         if  is_range: signed10 default, signed10 min, signed10 max
         then current value: is_range ? signed10 : u3 index             (-> o+0x63d4 + i*2)
  STRINGS(7,15,15)  main string table (o+0x5dbc / o+0x738 / data o+0x11b8)
  u7   base name string idx (v-1)              (o+0xe6fc)
  STRINGS(1,9,9)    localized name             (0x394590 / 0x394c50)
  STRINGS(1,12,12)  description (inline + 0x394d30)
  STRINGS(1,9,9)    category name
  u5   icon index (v-1)                         (o+0xf7ac)
  u5   category index (v-1)                     (o+0xf7a8)
  u6   map permission count (<=32); each u16 map id; then bool exception type (o+0xf7f8)
       (a count above 32 reads neither the ids nor the bool)
  15 x u32  rating params (floats)              (o+0xf7fc)
  u1   flag                                     (o+0xf838)  [RVE: show in scoreboard]
  u16  score to win                             (o+0xf83c)  [number operand kind 16 reads it]
  bool                                          (o+0xf83e)  [vt+0x40 getter; RVE: fireteams enabled]
  bool                                          (o+0xf83f)  [RVE: symmetric]
  2 x (40 x u32)   engine option toggles (disabled, hidden)  (0x3941a0)
  2 x (1 x u32)    megalo option toggles (disabled, hidden)  (0x3942f0)
  CONDITIONS, ACTIONS, TRIGGERS (below)
  u3 statistics count; each: u7 name, u2 format, u2 sort order (v-1), u1 grouping
  VARIABLES (below)
  u3 HUD widget count; each u4 position
  7 x u9 entry points (v-1 = trigger index; 0 = none), order:
        init, local init, host migration, double host migration, object death, local, pregame
        (stored o+0xe5e0..o+0xe5f8 = v+0xe5e4..v+0xe5fc)
  64 x u32  object type reference bitset (2048 bits, o+0xe5fc)  -- VALIDATION: every set bit i must be < motl
             entry count and motl entry i must have a tag, else 0x409c40 fails and 0x40a310 wipes the script
  u5 object filter (label) count; each:
        u7 label string idx (v-1); u3 flags;
        if flags&1: opt(11) object type ; if flags&2: u4 team (v-1) ; if flags&4: u16 number ; then u7 min count
  if version >= 0x6b (MCC TU):  u32 flags (o+0xf840); then 7 x u8 quantized:
        first 5: 0 -> 0.0, 255 -> 2.0, else ((q-1)+0.5)*(1/127)
        6th: 25/26 special (if flags&1 clear -> 1.0 else treated as 25), 0 -> 0, 255 -> 10.0, else ((q-1)+0.5)*(10/254)
        7th: 0 -> 0, 255 -> 10.0, else ((q-1)+0.5)*(10/254)

STRINGS(cw, ow, sw)  (cw = count width, ow = offset width, sw = size width)
  u(cw) count
  per string: 12 languages x { bool present, if present u(ow) byte offset into data }
  if count > 0:  u(sw) uncompressed size ; bool compressed ;
                 if compressed: u(sw) compressed size, then that many bytes = [u32 BE uncompressed size][zlib stream]
                 else: size bytes raw (UTF-8, NUL-terminated strings)
  Empty table = u(cw)=0 and nothing else.  (main 7/15/15, name 1/9/9, desc 1/12/12, category 1/9/9, team names 1/5/6)

BASE (0x396790)
  CONTENT HEADER (0x38f5d0):
    u4 content type (v-1)  [game variant = 6 -> encode 7]
    u32 ; u64 ; u64 ; u64 ; u64
    u3 activity (v-1) ; u3 game mode (+0x29) ; u3 engine (+0x2a)
    u32 map id ; u8 engine category
    AUTHOR x2 (0x38f9f0): u64, u64, up to 16 x u8 chars NUL-terminated, u1
    title: up to 128 x u16 chars, NUL-terminated ; description: up to 128 x u16, NUL-terminated
    if content type (stored) in {3,4}: u32   elif == 6: u8
    if game mode == 1: u8,u2,u2,u8 then u32 ; elif game mode == 2: u2 then u32 ; else nothing
    (defaults from 0x21c4f0(v,2): type 6, activity 3, game mode 3, engine 2, map id -1, category 0xff)
  bool (o+0x732 bit0)
  MISC: 4 x bool (o+0x2b8 bits0..3) ; u8 round time limit (<61) ; u5 rounds (o+0x2bb) ; u4 (o+0x2b9, <6) ;
        u7 sudden death time (v-1, o+0x2bc) ; u5 grace period (o+0x2be)
  RESPAWN (0x395220): 4 x bool ; u6 lives ; u7 team lives ; u8 respawn time ; u8 suicide penalty ;
        u8 betrayal penalty ; u4 respawn growth ; u4 loadout cam time ; u6 traits duration ; TRAITS (respawn traits)
  bool (ignored)
  SOCIAL: u2 (o+0x2fa, <3) ; 5 x bool (o+0x2f8 bits0..4)
  MAP: u6 (o+0x2fc) ; TRAITS (base player traits) ; u8 weapon set (signed) ; u8 vehicle set (signed) ;
       TRAITS x3 (red/blue/yellow powerup) ; u7 x3 powerup durations (<=120)
  TEAM: u3 scoring method (o+0x734, <4) ; u3 (o+0x3b8) ; u2 (o+0x3b9)
       8 teams x { u4 flags ; STRINGS(1,5,6) team name ; u4 initial designator (v-1) ; u1 ;
                   u32 primary color ; u32 secondary ; u32 text ; u5 fireteam count }
  LOADOUTS: u2 flags (o+0x67c) ; 6 palettes x 5 loadouts x { u1 ; opt(7) name ; u8 primary ; u8 secondary ;
            u8 armor ability ; u4 grenades }

TRAITS (0x21e4e0 = 0x21cb20, 0x21d0a0, 0x21d450, 0x21d7f0, 0x21da20)
  shields/health: u4 u3 u4 u3 u4 u4 u2 u3 u2 u2
  weapons:        u4 u4 u8 u8 u4 u2 u2 u2 u2 u2 u2 u8
  movement:       u5 u4 u4 u2 ; bool PRESENT-IF-1 then u9
  appearance:     u3 u2 u2 u3 u4
  sensors:        u3 u3 u2
  (all-zero decodes to "unchanged" per clamps; values out of range are clamped by the reader)

CONDITIONS (store o+0x7304, 16 B each; runtime evaluator 0x39e640)
  u10 count (<=512); each:
    u5 type  (0 = none: nothing else read)
    bool negate (+0xd) ; u9 or-sequence (+0xe) ; u10 action offset (+0xf) ; then params by type:
      1 compare:        VAR a ; VAR b ; u3 op  (0 <, 1 >, 2 ==, 3 <=, 4 >=, 5 != ; for player/object/team: 2 is ==, anything else !=)
      2 in boundary:    OBJECT ; OBJECT
      3 killer type is: PLAYER ; u5 flags  (bit (1<<death type) of this tick's death record for that player)
      4 team disposition: TEAM ; TEAM ; u2
      5 timer is zero:  TIMER
      6 object type is: OBJECT ; opt(11) type
      7 team has players: TEAM
      8 out of bounds, 13 equipment in use: OBJECT
      9 fireteam leader, 12 not respawning, 14/15/16 species: PLAYER
      10 assisted kill of: PLAYER ; PLAYER
      11 has label:     OBJECT ; opt(4) label
      17 in forge:      (no params)
      18..31:           (no params; evaluate true)
  Sequencing (0x423a70): a condition gates actions whose index >= its action offset; consecutive conditions
  with the same or-sequence are OR-ed, a new or-sequence value starts an AND.

ACTIONS (store o+0x930c, 20 B each; u11 count <= 1024; decoder 0x39cf20; executor 0x399110)
  u7 type (0 = none); 1..106 dispatch through 106-entry tables; 107..127 read nothing and do nothing.
  Every type and its parameters: the Actions table below. Shared parameter types: below the table.
    operators (0x408730): 0 add, 1 sub, 2 mul, 3 div, 4 set, 5 mod, 6 and, 7 or, 8 xor, 9 not (a = ~b),
                          10 shl, 11 sar, 12 abs (a = |b|); 13..15 jump past the 13-entry table
    99 run inline nested trigger: TRIGGER-BLOCK (u9 u10 u10 u11), indices into the flat condition/action arrays
    (30 and 31 read PLAYER ; NUMBER, not a trigger block; earlier versions of this page had that wrong)

TRIGGERS (store o+0x63fc, 12 B each)
  u9 count (<=320); each:
    u3 type (0 do, 1 each player, 2 each player random, 3 each team, 4 each object, 5 each object with label;
             6, 7 crash the runner 0x39ed40: its table has 6 entries)
    u3 attribute (runtime: host per-tick loop 0x3fe520 runs attribute 0 and 6; entry points are separate)
         names (ReachVariantTool; every Bungie entry-point trigger carries the matching one):
         0 normal, 1 subroutine, 2 init, 3 local init, 4 host migration, 5 object death, 6 local, 7 pregame
    if type == 5: opt(4) label index   (ReachVariantTool writes 5 raw bits here; a labelless one misaligns CU4)
    u9 first condition ; u10 condition count ; u10 first action ; u11 action count   (0x423cb0)

VARIABLES (counts, then per entry)
  global:  u4 numbers {NUMBER default ; u2 net priority} ; u4 timers {NUMBER} ; u4 teams {u4 team (v-1) ; u2} ;
           u4 players {u2} ; u5 objects {u2}
  player:  u4 numbers {NUMBER ; u2} ; u3 timers {NUMBER} ; u3 teams {u4 (v-1) ; u2} ; u3 players {u2} ; u3 objects {u2}
  object:  u4 numbers {NUMBER ; u2} ; u3 timers {NUMBER} ; u2 teams {u4 (v-1) ; u2} ; u3 players {u2} ; u3 objects {u2}
  team:    u4 numbers {NUMBER ; u2} ; u3 timers {NUMBER} ; u3 teams {u4 (v-1) ; u2} ; u3 players {u2} ; u3 objects {u2}

OPERANDS (every kind, with what CU4 reads: the Operands tables below)
  VAR (0x4227d0):   u3 kind: 0 NUMBER, 1 PLAYER, 2 OBJECT, 3 TEAM, 4 TIMER ; 5..7 nothing
  NUMBER (0x421a00): u6 kind:
      0 constant: u16 (signed)
      1 player.number[i]: u5 player ref, u3 i        2 object.number[i]: u5 object ref, u3 i
      3 team.number[i]: u5 team ref (v-1), u3 i       4 global.number[i]: u4 i
      5 user option i: u4 i                           44 temporary number i: u4 i
      6, 8, 9, 10: u5 ref                             7: u5 (v-1)
      11: u5 ref, u2                                  12: u5 (v-1), u2
      other kinds 13..43, 45..63: no payload
      Verified: 8 = player score (u5 player ref), 16 = score to win (no payload)
  PLAYER (0x41fab0): u2 kind: 0 -> u5 player ref ; 1 -> u5 player ref, u2 player var ;
                               2 -> u5 object ref, u2 ; 3 -> u5 team ref (v-1), u2
      player ref (0x441380): 0 none, 1..16 player index+1, 17..24 global.player[0..7],
                             25 current player (trigger iterator), 26/27 (0x4045e0 [0]/[1]),
                             28 killer player (engine globals +0x1d4, set by object-death event), 29..31 temporaries
  OBJECT (0x422640): u3 kind: 0,4 -> u5 ; 1,2,5,6 -> u5, u2 ; 3 -> u5 (v-1), u3 ; 7 -> u5 (v-1), u2
  TEAM (0x420480):   u3 kind: 0 -> u5 (v-1) ; 1 -> u5, u2 ; 2 -> u5, u1 ; 3 -> u5 (v-1), u2 ; 4,5 -> u5 ; 6,7 nothing
  TIMER (0x4239e0):  u3 kind: 0 -> u3 ; 1,3 -> u5, u2 ; 2 -> u5 (v-1), u2 ; 4,5,6 round/sudden death/grace ; 7 nothing
```

## The round trip, `mjolnir megalo dump`, and the grammar file

The codec, the grammar file, the tests and the command below are on branch
`work/reach-game-mode-support-2eca91`, not yet committed as of 2026-10-21; no
released tool has them until they are merged.

| Piece | Where | What |
|---|---|---|
| grammar | `crates/blam-megalo/grammar/megalo_cu4.json` | types, enums, conditions 0-31, actions 0-127, the top-level read order, store offsets and clamps, and Reach name hints; `_meta` holds the conventions |
| codec | `crates/blam-megalo/src/raw.rs` | `decode`, `decode_at`, `encode`, `round_trip`, `locate`; walks the grammar both ways, refuses a tree that no longer fits it, and names the first differing bit by field path |
| BLF reader | `crates/blam-megalo/src/blf.rs` | MCC `.bin` files: `mpvr` and `gvar` chunks |
| listing | `crates/blam-megalo/src/dump.rs:1074`, `crates/blam-cli/src/megalo.rs:356` | `mjolnir megalo dump` |
| tests | `crates/blam-megalo/tests/roundtrip.rs` | three round-trip tests (below) |

`mjolnir megalo dump <file.mglo|file.bin> [--out FILE]` reads a raw `.mglo`
stream or an MCC Reach `.bin` (Megalo engine type 2 only), states whether it
encodes back bit for bit, and lists every field in read order: header,
options, traits as the fields that change something, teams, loadouts, user
options with their values, strings (English, then every translation that
differs), statistics, variables of the four scopes, HUD widgets, entry
points, object types and labels, then the script. Each trigger is printed
with its entry point, its conditions placed before the action at their
action offset (with or-group and negation), and operands written as
references (`current_player.team == team[1]`). Object-type, sound, incident
and icon names it prints are Reach's (`reach:` hints); on MJOLNIR's maps type
18 is the CTF flag and 19 the health pack, not the Reach names.

The tests:

| Test | Checks |
|---|---|
| `mjolnir_variants_round_trip` | seven variants the typed builder writes (empty, Slayer, Slayer with a time limit, tick, CTF, CTF with time limit and health packs, Slayer with health packs) re-encode bit for bit with fewer than 8 zero pad bits |
| `fixture_variants_round_trip` | every `.mglo` under `tools/tests/fixtures` |
| `bungie_reach_variants_round_trip` | **gated**: runs only when `MCC_REACH` names an MCC `haloreach` folder, and otherwise passes without checking. Every Megalo variant in its `game_variants` and `hopper_game_variants`, from bit 4 of the `mpvr` payload, must re-encode bit for bit with only zero padding |

```text
MCC_REACH="C:/Program Files (x86)/Steam/steamapps/common/Halo The Master Chief Collection/haloreach" \
  cargo test -p blam-megalo --test roundtrip
```

Results on 2026-10-21, all VERIFIED:

- 417 of 417 Megalo variants round-trip bit for bit, each ending within the
  last byte of its payload (46 in `game_variants`, which are byte-identical
  copies of hopper files, and 371 in `hopper_game_variants`; 89 at version
  `0x6a`, 328 at `0x6b`). Skipped with a message: 55 Firefight, 1 Forge,
  1 campaign.
- In all 419 dumps (those plus MJOLNIR's Slayer and CTF): every trigger's
  condition and action range lies inside the arrays, every entry point names
  a trigger with the matching attribute (init 2, local init 3, host
  migration and double host migration 4, object death 5, local 6,
  pregame 7), every nested call is in range, and every condition and action
  belongs to some trigger.
- Every main string table in the corpus is zlib-compressed and inflates to
  its stated size. Sizes run from 18,798 to 142,518 bits; the largest script
  has 272 triggers, 492 conditions and 889 actions.
- No grammar correction was needed: the two static readings were right for
  every bit of the corpus on the first full run.

**What the corpus does not exercise**, so their wire format rests on the
decoder cases in `0x39cf20` alone: actions 18, 26, 32, 38, 39, 42, 47, 63, 69,
71, 81, 85-89, 92, 97 and 99-106 (80 of the 106 real action types are used);
conditions 9, 10, 16, 17; NUMBER kinds 9, 12, 14, 17, 21, 22, 24-30, 32-44;
OBJECT kinds 5, 7; TEAM kinds 1, 3; trigger attribute 3; team-name string
tables; labels with flags 2 or 4. No Bungie variant uses action 99; all
nesting is action 20 into subroutine triggers.

**Containers.** An MCC `.bin` is a BLF file: chunks of a 12-byte big-endian
header (signature, size including the header, major, minor) and a body;
`_blf`, `chdr` (v10.2), `mpvr` (v54.1), `_eof`, then 464 bytes of padding.
The `mpvr` body is a 20-byte hash, 4 bytes, a big-endian u32 payload length
and the payload, whose bits 0-3 are the engine type (1 Forge, 2 Megalo,
3 campaign, 4 Firefight) with the variant from bit 4. One hopper file uses a
`gvar` chunk whose body is the payload alone. A bare `.mglo` is the payload
from the u32 encoding version on, with no engine nibble, hash or BLF: MCC's
Hot Reload format and what CU4's loader reads. VERIFIED.

## Conventions

- Fields read as N separate bools set bit 0 from the **first** bool read.
  ReachVariantTool reads the general, respawn and social flags as one N-bit
  number, so its bit constants are reversed against CU4's stores; use the
  names, not its constants. Fields CU4 reads as one number (map flags, team
  flags, label flags, TU1 flags) keep ReachVariantTool's bit values.
  VERIFIED against NUMBER kinds 18, 21 and 33.
- Enum keys on this page are **decoded** values: for a `v-1` field, -1 is
  raw 0.
- Names of fields, kinds and enum values are ReachVariantTool's unless the
  code shows them; such names are INFERRED for CU4. Widths, order, stores and
  clamps are VERIFIED.
- CU4 clamps some values after reading them; the bits read do not change.

## Top level, in read order

| # | Field | Width | Store (`o+`) | Notes |
|---|---|---|---|---|
| 1 | encoding version | u32 | `0x5dc0` | not `0x6a`/`0x6b`: the decoder returns at once |
| 2 | engine version | u32 | | ignored |
| 3 | base options | below | | `0x396790` |
| 4 | script traits | u5 count; each u7 name, u7 description, TRAITS | `0x5dcc + i*0x30` | 16 fit |
| 5 | user options | u5 count; each USER_OPTION | `0x60d4 + i*0x30` | 16 fit |
| 6 | main strings | STRINGS(7,15,15) | count `0x5dbc`, offsets `0x738` (per language `0xe0`), data `0x11b8` (`0x4c00`) | |
| 7 | base name | u7 v-1 | `0xe6fc` | a main string index |
| 8-10 | localized name, description, category | STRINGS(1,9,9), (1,12,12), (1,9,9) | `0xe848`, `0xe9e8`/`0xea00`, `0xf608` | |
| 11 / 12 | engine icon / engine category | u5 v-1 | `0xf7ac` / `0xf7a8` | |
| 13-14 | map permissions | u6 count; if count <= 32: count x u16 map id, bool exception type | `0xf7b0`, `0xf7b8`, `0xf7f8` | above 32 reads nothing more |
| 15 | rating parameters | 15 x f32 | `0xf7fc` | |
| 16 | show in scoreboard | u1 | `0xf838` | |
| 17 | score to win | u16 | `0xf83c` | read by the engine (slot 1) and NUMBER kind 16 |
| 18 | fireteams enabled | bool | `0xf83e` | read by condition 7, engine slots 4 and 54 |
| 19 | symmetric | bool | `0xf83f` | the engine's symmetry value comes from elsewhere |
| 20 | engine option toggles | 2 x 40 x u32 (disabled, hidden) | `0xe700`, `0xe7a0` | |
| 21 | Megalo option toggles | 2 x 1 x u32 | `0xe840`, `0xe844` | |
| 22 | conditions | u10 count; CONDITION | count `0x72fc`, records `0x7304` (16 B) | 512 fit |
| 23 | actions | u11 count; ACTION | count `0x9304`, records `0x930c` (20 B) | 1024 fit |
| 24 | triggers | u9 count; TRIGGER | count `0x63f4`, records `0x63fc` (12 B) | 320 fit |
| 25 | statistics | u3 count; each u7 name, u2 format, u2 sort order v-1, u1 group by team | count `0xe30c`, records `0xe314` | 4 fit |
| 26 | variables | four scopes | `0xe324`..`0xe4c8` | |
| 27 | HUD widgets | u3 count; each u4 position | count `0xe4cc`, `0xe4d4` | the engine keeps only 4 |
| 28 | entry points | 7 x u9 v-1 | `0xe5e0`..`0xe5f8` | init, local init, host migration, double host migration, object death, local, pregame |
| 29 | object type references | 64 x u32 | `0xe5fc` | bit `i` = word `i/32` bit `i%32` |
| 30 | labels | u5 count; LABEL | count `0xe4d8`, records `0xe4e0` (16 B) | 16 fit |
| 31 | TU1 options | if version >= `0x6b` | `0xf840`.. | |

## Content header (`0x38f5d0`)

| Field | Width | Notes |
|---|---|---|
| content type | u4 v-1 | 6 game variant (encode 7); -1 none, 0 DLC, 1 campaign save, 2 screenshot, 3 film, 4 film clip, 5 map variant, 7 playlist |
| file length | u32 | |
| four values | 4 x u64 | |
| activity | u3 v-1 | Bungie files: 3 or 4 |
| game mode | u3 | 1 campaign, 2 Firefight, 3 matchmaking; Bungie files: 3 |
| engine | u3 | 2 in every Bungie Megalo file |
| map id | u32 | |
| engine category | u8 | |
| created by, modified by | AUTHOR x 2 (`0x38f9f0`): u64 time, u64 id, up to 16 u8 characters, u1 online id | |
| title, description | up to 128 u16 characters each, NUL-terminated | |
| by content type | 3 or 4: u32; 6: u8 engine icon | |
| by game mode | 1: u8 campaign, u2 difficulty, u2 scoring, u8, u32; 2: u2 difficulty, u32 | |

CU4 reads no hopper id for activity 2; MCC and ReachVariantTool read a u16
there, so an activity-2 header from them misaligns CU4 by 16 bits. Bungie's
shipped files are activity 3 or 4. VERIFIED both sides.

## Base options (`0x396790`)

| Group | Field | Width | Store (`o+`) | Status |
|---|---|---|---|---|
| | built in | bool | `0x732` bit 0 | VERIFIED |
| general | teams enabled | bool | `0x2b8` bit 0 | VERIFIED (NUMBER 18) |
| | new round resets map | bool | `0x2b8` bit 1 | name INFERRED |
| | new round resets players | bool | `0x2b8` bit 2 | name INFERRED |
| | perfection enabled | bool | `0x2b8` bit 3 | VERIFIED (NUMBER 21) |
| | round time limit (minutes; above 60 becomes 8) | u8 | `0x2ba` | VERIFIED |
| | round limit | u5 | `0x2bb` | VERIFIED |
| | rounds to win, early victory (above 5 becomes 2) | u4 | `0x2b9` | VERIFIED |
| | sudden death time (-1 indefinite) | u7 v-1 | `0x2bc` | VERIFIED |
| | grace period | u5 | `0x2be` | VERIFIED |
| respawn (`0x395220`) | respawn on kills, at location, with teammate, synchronized with team | 4 bools | `0x2c0` bits 0-3 | names INFERRED |
| | lives per round, team lives per round, respawn time, suicide penalty, betrayal penalty, respawn growth, loadout camera time, respawn traits duration | u6, u7, u8, u8, u8, u4, u4, u6 | `0x2c1`..`0x2c8` | VERIFIED (NUMBER 25-32) |
| | respawn traits | TRAITS | `0x2cc` | VERIFIED |
| social | observers | bool | read and discarded | VERIFIED |
| | team changes (0 off, 1 on, 2 balancing only; 3 ignored) | u2 | `0x2fa` | VERIFIED |
| | friendly fire, betrayal booting, proximity voice, don't team-restrict chat, dead players can talk | 5 bools | `0x2f8` bits 0-4 | VERIFIED (NUMBER 33-37) |
| map | map flags: 1 grenades, 2 shortcuts, 4 abilities, 8 powerups, 16 turrets, 32 indestructible vehicles | u6 | `0x2fc` | VERIFIED |
| | base player traits | TRAITS | `0x300` | VERIFIED |
| | weapon set, vehicle set | s8, s8 | `0x32c`, `0x32e` | VERIFIED |
| | red, blue, yellow powerup traits | 3 x TRAITS | `0x330`, `0x35c`, `0x388` | VERIFIED |
| | red, blue, yellow powerup durations (above 120 become 5, 30, 30) | 3 x u7 | `0x3b4`..`0x3b6` | VERIFIED |
| team | team scoring: 0 sum, 1 minimum, 2 maximum, 3 none (above 3 becomes 0) | u3 | `0x734` | VERIFIED code |
| | team species: 0 player's choice, 1 Spartan, 2 Elite, 3 per team, 4 Elite for designator 1 | u3 | `0x3b8` | VERIFIED code |
| | designator switch: 0 fixed, 1 rotate, 2 shuffle | u2 | `0x3b9` | VERIFIED code |
| | 8 teams | TEAM_ENTRY | `0x3bc + t*0x58` | VERIFIED |
| loadouts | loadout flags | u2 | `0x67c` | VERIFIED |
| | 6 palettes x 5 loadouts: visible u1, name opt(7), primary s8, secondary s8, ability s8, grenade count u4 | | `0x67d + p*0x1e + l*6` | VERIFIED widths; palette order (Spartan tier 1, Elite tier 1, Spartan tier 2, ...) INFERRED |

TEAM_ENTRY: u4 flags (1 enabled, 2 override primary colour, 4 override
secondary, 8 override text colour), name STRINGS(1,5,6), u4 v-1 initial
designator, u1 species, u32 primary colour, u32 secondary, u32 text colour
(0x00RRGGBB), u5 fireteam count. The engine uses a team's own primary colour
only when teams are on and flags 1 and 2 are both set; otherwise it uses
`multiplayer_globals` ([reach_game_engine.md](reach_game_engine.md)).
Bungie's variants leave the override bits off (flags 1, colours
`0xffffffff`); so does MJOLNIR's encoder (flags 1, colours 0).

The loadout name opt(7) is not a main-string index: Bungie's values (74-79)
lie past every variant's string table. What it indexes is open.

## Player traits (TRAITS)

One block is 117 bits, 126 with a jump height. The crate's table
(`crates/blam-megalo/src/variant.rs:356`) has the same 34 fields. Value
names are ReachVariantTool's; 0 is "unchanged" throughout.

| Group | Field | Width | CU4 clamp | Values |
|---|---|---|---|---|
| defense | damage resistance | u4 | | 1 10%, 2 50%, 3 90%, 4 100%, 5 110%, 6 150%, 7 200%, 8 300%, 9 500%, 10 1000%, 11 2000%, 12 invulnerable |
| | health multiplier | u3 | | 1 0%, 2 100%, 3 150%, 4 200%, 5 300%, 6 400% |
| | health regeneration | u4 | | 1 -25%, 2 -10%, 3 -5%, 4 0%, 5 50%, 6 90%, 7 100%, 8 110%, 9 200% |
| | shield multiplier | u3 | | as health multiplier |
| | shield regeneration | u4 | | 1 -25%, 2 -10%, 3 -5%, 4 0%, 5 10%, 6 25%, 7 50%, 8 75%, 9 90%, 10 100%, 11 110%, 12 125%, 13 150%, 14 200% |
| | overshield regeneration | u4 | | as shield regeneration |
| | headshot immunity | u2 | | 1 off, 2 on |
| | shield vampirism | u3 | | 1 0%, 2 10%, 3 25%, 4 50%, 5 100% |
| | assassination immunity, cannot die from damage | u2, u2 | | 1 off, 2 on |
| offense | damage multiplier, melee damage multiplier | u4, u4 | | 1 0%, 2 25%, 3 50%, 4 75%, 5 90%, 6 100%, 7 110%, 8 125%, 9 150%, 10 200%, 11 300%, 12 instant kill |
| | primary weapon, secondary weapon | s8, s8 | outside -4..63 becomes -3 | -4 weighted random, -3 unchanged, -2 the scenario's starting profile, -1 none, 0.. an index into the object type list's `weapons` collection |
| | grenade count | u4 | above 14 becomes 1 | 1 map default, 2 none, 3-6 frag 1-4, 7-10 plasma 1-4, 11-14 each 1-4 |
| | infinite ammo | u2 | | 1 off, 2 on, 3 bottomless |
| | grenade regeneration, weapon pickup | u2, u2 | above 2 becomes 1 / 2 | 1 off, 2 on |
| | ability usage | u2 | | 1 off, 2 not with objectives, 3 on |
| | abilities drop on death, infinite ability | u2, u2 | above 2 becomes 1 | 1 off, 2 on |
| | ability | s8 | outside -4..31 becomes -3 | as weapons, over the list's `equipment` collection |
| movement | speed | u5 | | 1 0%, 2 25%, 3 50%, 4 75%, 5 90%, 6 100%, 7-16 110%-200%, 17 300% |
| | gravity | u4 | | 1 50%, 2 75%, 3 100%, 4 150%, 5 200% |
| | vehicle use | u4 | above 8 becomes 8 | 1 none, 2 passenger only, 3 driver only, 4 gunner only, 5 no passenger, 6 no driver, 7 no gunner, 8 full |
| | double jump | u2 | | 1 off, 2 on, 3 on with lunge |
| | jump height | bool, then u9 **if the bool is 1** | above 400 becomes absent | percent; absent = unchanged |
| appearance | active camo | u3 | above 5 becomes 0 | 1 off, 2 worst, 3 poor, 4 good, 5 best |
| | waypoint, visible name | u2, u2 | | 1 none, 2 allies, 3 everyone |
| | aura | u3 | above 4 becomes 0 | 1 none, 2 team colour, 3 darken armour, 4 brighten armour |
| | forced colour | u4 | above 13 becomes 0 | 1 none, 2 red, 3 blue, 4 green, 5 orange, 6 purple, 7 gold, 8 brown, 9 pink, 10 white, 11 black, 12 zombie, 13 pink 2 |
| sensors | radar state | u3 | above 4 becomes 3 | 1 off, 2 allies, 3 normal, 4 enhanced |
| | radar range | u3 | | 1 10 m, 2 15 m, 3 25 m, 4 50 m, 5 75 m, 6 100 m, 7 150 m |
| | directional damage indicator | u2 | above 2 becomes 2 | |

The weapon and ability lists are VERIFIED (`0x30c9a0`, `0x30ceb0`): the
multiplayer object type list in use (the scenario's, else the globals') has
`weapons` and `equipment` collections, and trait indices count into those,
not into Reach's lists. The forced colour, aura and team colour are applied
by sim `0x2b3710` but never reach Unreal
([reach_game_engine.md](reach_game_engine.md)).

## Script traits and user options

A script trait is u7 name, u7 description (main string indices) and TRAITS,
stored at `o+0x5dcc + i*0x30`. VERIFIED.

USER_OPTION (VERIFIED, stores relative to the 0x30-byte entry at
`o+0x60d4 + i*0x30`):

| Field | Width | Store |
|---|---|---|
| name, description | u7, u7 | `+0`, `+1` |
| is range | bool | `+2` |
| list: default index; value count; each value s10, name u7, description u7 | u3; u4; | `+4`; `+8`; `+0x10 + j*4` |
| range: default, minimum, maximum | s10 x 3, no names | `+4`, `+0x10`, `+0x14` |
| current value | s10 for a range, else a u3 index | `o+0x63d4 + i*2` |

NUMBER kind 5 returns the current value, looked up in the value table for a
list option. Eight values fit; the u4 count is not capped (see *Limits*).

## String tables

STRINGS(cw, ow, sw): u(cw) count; per string, 12 languages (English,
Japanese, German, French, Spanish, Mexican Spanish, Italian, Korean,
Traditional Chinese, Simplified Chinese, Portuguese, Polish) of {bool
present; u(ow) byte offset if present}; then, only when the count is not 0,
u(sw) uncompressed size and bool compressed; compressed data is u(sw) bytes
holding a big-endian u32 size and a zlib stream, otherwise the
uncompressed size in bytes of NUL-terminated UTF-8.

| Table | cw/ow/sw | Data store | Data reader |
|---|---|---|---|
| main | 7/15/15 | `0x4c00` bytes at `o+0x11b8` | `0x3949c0` |
| localized name | 1/9/9 | 0x180 | `0x394590` → `0x394c50` |
| localized description | 1/12/12 | 0xc00 | inline + `0x394d30` |
| localized category | 1/9/9 | 0x180 | `0x394590` → `0x394c50` |
| team name | 1/5/6 | 0x20 | inline + `0x397f80` |

The inflater call (`0x32a620` → `0x6c7b20`) takes its output size from the
embedded big-endian u32, not from the stream's u(sw) and not from the store
size. A writer must keep the two sizes equal and within the store. VERIFIED.

## Triggers, statistics, variables, labels

TRIGGER (12 bytes at `o+0x63fc`): u3 type, u3 attribute, for type 5 an
opt(4) label, then u9 first condition, u10 condition count, u10 first
action, u11 action count (`0x423cb0`). Trigger types, run by `0x39ed40`:
0 do, 1 for each player, 2 for each player in random order (the sim's LCG),
3 for each team (0-8, neutral included), 4 for each object (skipping objects
being deleted), 5 for each object with a label (the label's list). VERIFIED.

STAT (`o+0xe314 + i*4`): u7 name, u2 format (0 number, 1 signed number,
2 percentage, 3 time), u2 sort order stored minus 1, u1 group by team.
VERIFIED widths; names INFERRED.

VARIABLES, VERIFIED (the maximum each count field allows is in brackets):

| Scope | Numbers {NUMBER initial, u2 priority} | Timers {NUMBER initial} | Teams {u4 v-1 team, u2 priority} | Players {u2} | Objects {u2} |
|---|---|---|---|---|---|
| global | u4 (12) | u4 (8) | u4 (8) | u4 (8) | u5 (16) |
| player | u4 (8) | u3 (4) | u3 (4) | u3 (4) | u3 (4) |
| object | u4 (8) | u3 (4) | u2 (2) | u3 (4) | u3 (4) |
| team | u4 (8) | u3 (4) | u3 (4) | u3 (4) | u3 (6) |

Network priority: 0 none (never sent), 1 low, 2 high. A team's initial value
is -1 none, 0-7 team 1-8, 8 neutral. Timers count in seconds and are scaled
by the tick rate at initialisation (`0x408d00`). Every fireteam machine
decodes the host's variable updates against its own declarations, so these
counts and priorities must match on all of them
([reach_game_engine.md](reach_game_engine.md)).

LABEL (`o+0xe4e0 + i*0x10`): u7 v-1 name (a main string index); u3 flags;
flag 1: opt(11) object type; flag 2: u4 v-1 team; flag 4: u16 number; u7
"map must have at least". The engine matches labels by **name** against the
map variant's labels. VERIFIED.

## TU1 options (version `0x6b`)

u32 flags at `o+0xf840` (1 bleed through, 2 armour lock cannot shed
stickies, 4 armour lock can be stuck, 8 active camo modifiers, 16 limit
sword block to sword, 32 automatic magnum; names INFERRED), then 7 x u8
quantized values at `o+0xf844`..`o+0xf85c`: precision bloom, armour lock
damage drain, armour lock damage drain limit, active camo energy curve
maximum, active camo energy curve minimum (q0 → 0, q255 → 2.0, else
((q-1)+0.5)/127); magnum damage (q25 or q26 with flags bit 0 clear → exactly
1.0; q0 → 0; q255 → 10.0; else ((q-1)+0.5)*10/254); magnum fire delay
(q0 → 0, q255 → 10.0, else ((q-1)+0.5)*10/254). VERIFIED.

## Conditions

Each condition reads u5 type; type 0 reads nothing more. Every other type
reads bool negate, u9 or-sequence and u10 action offset, then its
parameters. Decoder switch at `0x3932c6` (table `0x3940d8`), evaluator
`0x39e640` (table `0x39ecf4`). "Used" = in Bungie's corpus. All rows
VERIFIED in the decoder and evaluator; names INFERRED.

| Id | Name | Parameters | What CU4 evaluates | Used |
|---|---|---|---|---|
| 0 | None | none | true | |
| 1 | Compare | VAR a; VAR b; u3 operator | numbers and timers: signed compare, 0 <, 1 >, 2 ==, 3 <=, 4 >=, 5 != (6 and 7 index past the six-entry table and crash). Player, object, team: 2 is ==, anything else !=. When `a` is a player, object or team, `b` is read as that type whatever its kind; a number against a non-number reads `b` as a timer (`0x423fc0`) | yes |
| 2 | Object In Boundary | OBJECT a; OBJECT b | `a`'s centre inside `b`'s shape; `b` may be a player-biped form | yes |
| 3 | Killer Type | PLAYER victim; u5 flags | the victim's death record this tick has death type bit set: 1 guardians, 2 suicide, 4 kill, 8 betrayal, 16 quit | yes |
| 4 | Team Alliance Status | TEAM a; TEAM b; u2 status (0 neutral, 1 friendly, 2 enemy) | either neutral (8): status 0; either none: status 2; else status == (a != b) + 1 | yes |
| 5 | Timer Is Zero | TIMER | value & 0xffffff == 0 | yes |
| 6 | Object Type | OBJECT; opt(11) type | the object's tag is that object type list entry's tag | yes |
| 7 | Team Has Players | TEAM | with fireteams enabled: true for designators 0 and 1; else the designator's team has players | yes |
| 8 | Object Out Of Bounds | OBJECT | inside an MP kill volume or outside every MP safe volume, a scenario kill trigger or safe zone, or a soft-kill ceiling (`0x424150`); always false on converted maps | yes |
| 9 | Player Is Fireteam Leader | PLAYER | always false | no |
| 10 | Player Assisted Kill Of | PLAYER attacker; PLAYER victim | the victim's death record has the attacker's assist bit | no |
| 11 | Object Has Label | OBJECT; opt(4) label | the object matches that label (`0x424460`); none is false | yes |
| 12 | Player Is Not Respawning | PLAYER | player flags: bit 1 clear, bit 0 set | yes |
| 13 | Equipment In Use | OBJECT | equipment (type 3) whose `+0x1c8` is not -1 | yes |
| 14 | Species Is Spartan | PLAYER | species 0 (`0x187980`) | yes |
| 15 | Species Is Elite | PLAYER | species 1 | yes |
| 16 | Species Is Monitor | PLAYER | the monitor test (`0x2fedc0`) | no |
| 17 | In Forge | none | a game engine exists, mode 3 and a sandbox variant | no |
| 18-31 | | none | true (then negate) | no |

The killer-type bits are VERIFIED for CU4: engine slot 62 writes death type
0 guardian, 1 suicide, 2 kill, 3 betrayal, 4 quit into the record
(`0x3fea10`). Corpus counts: Compare 41,324; Timer Is Zero 4,517; Killer
Type 3,199; Team Has Players 1,208; Object In Boundary 1,182; Object Type 856.

## Actions

Each action reads u7 type, then its parameters in the order shown. Stores
are 20-byte records (16 parameter bytes, the type at `+0x10`). Shared
parameter types (PLAYER_SET, FORMAT_STRING and the rest) are defined after
the table. "Used" = in Bungie's corpus. Wire format: VERIFIED for every row
(by the round trip for the 80 used types, by the decoder case for the
others). Behaviour: read in the executor `0x399110` on 2026-10-21; "twice"
marks rows a second pass re-read; INFERRED marks rows whose behaviour rests
on names. Names are ReachVariantTool's.

| Id | Name | Parameters | What CU4 does | Used | Behaviour |
|---|---|---|---|---|---|
| 0 | None | | nothing | | read |
| 1 | Modify Score | PLAYER_OR_GROUP target; u4 operator; NUMBER | changes a player's score (`G+0x32c0+i*8`) or a team's (`+0x80+t*8`, clamped to +/-30000); a team target credits every team index whose designator matches; all players through the recipient mask; skipped unless the round is live (`0x41c080`) | yes | twice |
| 2 | Create Object | opt(11) type; OBJECT result; OBJECT basis; opt(4) label; u3 flags; VECTOR3 offset; u8 v-1 name | creates the type at basis + offset (yaw-only frame unless absolute orientation), with the tag's default model variant unless `name` names one through the Megalo string-id table; marks it Megalo-created (placement flag `0x800`); stores it in `result` (`0x41c3b0`) | yes | twice |
| 3 | Delete Object | OBJECT | deletes it (`0x5a2c30`); engine slot 50 clears every variable naming it | yes | twice |
| 4 | Set Waypoint Visibility | OBJECT; PLAYER_SET | who sees the waypoint; a player-biped form sets that player's own waypoint | yes | read |
| 5 | Set Waypoint Icon | OBJECT; WAYPOINT_ICON | the icon; the territory icon stores 11 + clamp(n-1, 0, 8) | yes | read |
| 6 | Set Waypoint Priority | OBJECT; u2 priority | 0 low, 1 normal, 2 high, 3 blink | yes | read |
| 7 | Set Waypoint Timer | OBJECT; opt(2) object timer | the timer shown on the waypoint | yes | read |
| 8 | Set Waypoint Distance | OBJECT; NUMBER min; NUMBER max | visibility range, capped at 100, negative = none | yes | read |
| 9 | Modify Variable | VAR a; VAR b; u4 operator | numbers: a = a op b (a timer `b` gives its value); player, object, team: a = b, operator ignored (team writes through `0x41fd80`); timers: copy, or op in seconds x tick rate, clamped (`0x41c8b0`) | yes | twice |
| 10 | Set Object Shape | OBJECT; SHAPE | the object's boundary (a player-biped form sets the player's shape); each NUMBER x 0.1 clamped to [0, 200] (`0x41cb00`) | yes | read |
| 11 | Apply Player Traits | PLAYER; u4 script traits | adds the trait set to the player's list for this tick (16 at most) | yes | read |
| 12 | Set Weapon Pickup Permissions | OBJECT; PLAYER_SET | who may pick it up (`MO+0x1c`, engine slot 39) | yes | twice |
| 13 | Set Spawn Location Permissions | OBJECT; PLAYER_SET | who may spawn on it (`MO+0x24`), only when the object is **not** a player spawn location (MP type 15; `0x41cd90`) | yes | twice |
| 14 | Set Spawn Location Fireteams | OBJECT; u8 fireteam mask | `MO+0x02`, same gate as 13 | yes | twice |
| 15 | Set Object Progress Bar | OBJECT; PLAYER_SET; opt(2) object timer | who sees a progress bar and which timer drives it | yes | read |
| 16 | Kill Feed Message | PLAYER_OR_GROUP; u7 v-1 sound; FORMAT_STRING | formats the text for each recipient, merges duplicates, posts it with the sound; not on a distributed client (`0x41cdf0`) | yes | read |
| 17 | Set Timer Rate | TIMER; u5 rate | the timer's rate (table below) | yes | read |
| 18 | Debug Print | FORMAT_STRING | nothing | no | read |
| 19 | Get Item Carrier | OBJECT; PLAYER result | a weapon's or equipment's holder; none otherwise | yes | twice |
| 20 | Run Nested Trigger | u9 trigger | runs that trigger, saving and restoring the iteration context; no bound and no depth limit | yes | twice |
| 21 | End Round | | `0x2afa70(-1, 0, 0)` | yes | twice |
| 22 | Set Object Shape Visibility | OBJECT; PLAYER_SET | who sees the boundary | yes | read |
| 23 | Kill Object Instantly | OBJECT; bool silent | a lethal damage event unless the object cannot die; `silent` sets a damage flag (no statistics, INFERRED) (`0x41d160`) | yes | read |
| 24 | Set Object Invincibility | OBJECT; NUMBER | invincible while non-zero | yes | read |
| 25 | Random Number | NUMBER cap; NUMBER result | a value in [0, cap) from the sim's LCG; nothing when cap <= 0 | yes | read |
| 26 | Break into Debugger | | nothing | no | read |
| 27 | Get Object Orientation | OBJECT; NUMBER | 1-6: which of the object's axes points most nearly up | yes | read |
| 28 | Get Speed | OBJECT; NUMBER | round(speed x 10); 0 below 0.1 | yes | read |
| 29 | Get Killer | PLAYER victim; PLAYER result | the killer from this tick's death records; written only when the victim is found | yes | twice |
| 30 | Get Death Damage Type | PLAYER; NUMBER | the record's damage type; unchanged when not found | yes | read |
| 31 | Get Death Damage Modifier | PLAYER; NUMBER | 1 melee, 2 assassination, 3 splatter, 4 sticky, 5 headshot; unchanged when not found | yes | twice |
| 32 | Debugging: Enable Tracing | bool | nothing | no | read |
| 33 | Attach Objects | OBJECT subject; OBJECT target; VECTOR3; bool relative | moves the subject to target + offset and attaches it to the nearest node (`0x41d370`) | yes | read |
| 34 | Detach Objects | OBJECT | detaches it | yes | read |
| 35 | Get Player Scoreboard Position | PLAYER; NUMBER | standing + 1, or 0 | yes | read |
| 36 | Get Team Scoreboard Position | TEAM; NUMBER | standing + 1 | yes | read |
| 37 | Get Player Killstreak | PLAYER; NUMBER | the player's spree statistic | yes | read |
| 38 | Modify Player Requisition Money | PLAYER; u4 operator; NUMBER | money op operand, applied as a change | no | read |
| 39 | Set Player Requisition Purchase Modes | PLAYER; NUMBER enable; u5 flags | sets or clears purchase flags (1 alive weapons, 2 alive equipment, 4 alive vehicles, 8 dead weapons, 16 dead equipment) | no | read |
| 40 | Get Player Vehicle | PLAYER; OBJECT | the vehicle the player's unit is in, else none | yes | read |
| 41 | Force Player Into Vehicle | PLAYER; OBJECT vehicle | seats the player; with no vehicle, an exit action (INFERRED) | yes | read |
| 42 | Set Player Biped | PLAYER; OBJECT biped | an unowned biped becomes the player's unit | no | read |
| 43 | Reset Timer | TIMER | back to its initial value | yes | read |
| 44 | Set Weapon Pickup Priority | OBJECT; u2 priority | weapons only: 0 normal, 1 hold, 2 automatic (`MO+3`, engine slots 40/41) | yes | twice |
| 45 | Push Object Up | OBJECT | a random upward impulse scaled by mass (`0x41d8c0`) | yes | read |
| 46 | Set Widget Text | opt(2) widget; FORMAT_STRING | the widget's text | yes | read |
| 47 | Set Widget Value Text | opt(2) widget; FORMAT_STRING | the widget's value text | no | read |
| 48 | Set Meter Parameters | opt(2) widget; METER | the widget's meter | yes | read |
| 49 | Set Widget Icon | opt(2) widget; opt(6) icon | the widget's icon | yes | read |
| 50 | Set Widget Visibility | opt(2) widget; PLAYER; bool | shows or hides it for one player | yes | read |
| 51 | Play Sound | u7 v-1 sound; bool immediate; PLAYER_OR_GROUP | posts the sound to the recipients; not on a distributed client | yes | read |
| 52 | Modify Object Scale | OBJECT; NUMBER | scale = max(0, n x 0.01) | yes | read |
| 53 | Set Waypoint Text | OBJECT; FORMAT_STRING | the waypoint's text | yes | read |
| 54 | Get Object Shields | OBJECT; NUMBER | shield vitality x 100, 0-400 | yes | read |
| 55 | Get Object Health | OBJECT; NUMBER | health vitality x 100 | yes | read |
| 56 | Set Objective Description for Player | PLAYER; FORMAT_STRING | the player's objective text | yes | read |
| 57 | Set Objective Icon Caption for Player | PLAYER; FORMAT_STRING | the objective caption | yes | read |
| 58 | Set Objective Icon for Player | PLAYER; opt(7) icon | the objective icon | yes | read |
| 59 | Enable/Disable Co-Op Spawning | TEAM; bool | every team member's co-op spawning flag | yes | read |
| 60 | Set Primary Respawn Object for Team | TEAM; OBJECT | for the team's players the object's spawn permissions allow (`0x41daf0`) | yes | read |
| 61 | Set Primary Respawn Object for Player | PLAYER; OBJECT | the player's respawn object; none clears it | yes | read |
| 62 | Get Player Fireteam | PLAYER; NUMBER | the player's fireteam (0 when none) | yes | read |
| 63 | Set Player Fireteam | PLAYER; NUMBER | sets it when below 17 | no | read |
| 64 | Modify Object Shields | OBJECT; u4 operator; NUMBER | operand x 0.01, operators 0-4 only, clamped to [0, 4] | yes | read |
| 65 | Modify Object Health | OBJECT; u4 operator; NUMBER | clamped to [0, 1]; 0 kills (`0x41dd00`) | yes | read |
| 66 | Get Distance | OBJECT a; OBJECT b; NUMBER | round(distance x 10); 0 when either is none | yes | read |
| 67 | Modify Object Max Shields | OBJECT; u4 operator; NUMBER | maximum shields; current shields rescaled | yes | read |
| 68 | Modify Object Max Health | OBJECT; u4 operator; NUMBER | maximum health; 0 kills | yes | read |
| 69 | Set Player Requisition Palette | PLAYER; u4 palette | the palette (above 12 becomes 0) | no | read |
| 70 | Set Device Power | OBJECT; NUMBER | power = clamp(n x 0.01, 0, 1) | yes | read |
| 71 | Get Device Power | OBJECT; NUMBER | power x 100 | no | read |
| 72 | Set Device Position | OBJECT; NUMBER | position = clamp(n x 0.01, 0, 1) | yes | read |
| 73 | Get Device Position | OBJECT; NUMBER | position x 100 | yes | read |
| 74 | Modify Player Grenades | PLAYER; u1 type (0 frag, 1 plasma); u4 operator; NUMBER | grenade count, clamped to [0, 4] | yes | read |
| 75 | Submit Incident | u10 v-1 incident; PLAYER_OR_GROUP cause; PLAYER_OR_GROUP effect | raises the n-th incident definition, skipping the engine's own (string ids `0x67ffff`-`0xd00070`) (`0x41df50`) | yes | twice |
| 76 | Submit Incident with value | as 75; NUMBER value | the same with a 16-bit value (out-of-range becomes 0) | yes | twice |
| 77 | Set Player Loadout Palette | PLAYER_OR_GROUP; u3 v-1 palette | a player's or every team member's palette, then a loadout refresh (`0x41e140`) | yes | read |
| 78 | Set Device Position Track | OBJECT; u8 v-1 animation; NUMBER | selects a device animation track | yes | read |
| 79 | Animate Device Position | OBJECT; NUMBER target; NUMBER duration; NUMBER acceleration; NUMBER deceleration | animates the device to the target over the time | yes | read |
| 80 | Set Device Actual Position | OBJECT; NUMBER | sets the position at once | yes | read |
| 81 | Insert Theater Film Marker | NUMBER offset; FORMAT_STRING | a marker of at most 32 ASCII characters, only while a film records (`0x41e310`) | no | read |
| 82 | Enable/Disable Spawn Zone | OBJECT; NUMBER | clears or sets the zone's disabled bit (`MP+0x12` bit `0x4000`), which takes it out of spawn scoring | yes | read |
| 83 | Get Player Weapon | PLAYER; bool (0 secondary, 1 primary); OBJECT | the weapon, else none | yes | read |
| 84 | Get Player Armor Ability | PLAYER; OBJECT | the unit's ability, else none | yes | read |
| 85 | Enable/Disable Object Garbage Collection | OBJECT; NUMBER | keeps the object from being collected while non-zero | no | read |
| 86 | Get Player Target Object | PLAYER; OBJECT | the unit's aim target, else none | no | read |
| 87 | Create Object Equidistant | OBJECT a; OBJECT b; opt(11) type; NUMBER radius; OBJECT result | creates the type midway between a and b, facing from a to b (`0x41e540`) | no | read |
| 88 | Debug: Force Splitscreen Count | NUMBER | nothing | no | read |
| 89 | Add Weapon to Player | PLAYER; OBJECT weapon | gives an existing weapon | no | read |
| 90 | Set Co-op Spawning for Player | PLAYER; bool | the player's co-op spawning flag | yes | read |
| 91 | Copy Object Rotation | OBJECT a; OBJECT b; bool all axes | an unattached `a` takes `b`'s orientation, or only its heading (`0x41e810`) | yes | read |
| 92 | Point Object Toward Object | OBJECT a; OBJECT b; VECTOR3 | turns an unattached `a` toward `b` + offset (`0x41eb90`) | no | read |
| 93 | Add Weapon To Biped | OBJECT biped; opt(11) weapon; u2 mode (0 primary, 1 secondary, 2 force) | creates the weapon and gives it to a biped that does not already hold that type (`0x41ef90`) | yes | read |
| 94 | Remove Weapon From | OBJECT biped; bool (0 secondary, 1 primary); bool delete | takes the weapon away, deleting it if asked | yes | read |
| 95 | Set Scenario Interpolator State | NUMBER which (1-32); NUMBER state | starts or stops a scenario interpolator (`0x41f1d0`) | yes | INFERRED meaning |
| 96 | Get Random Object With Label | OBJECT exclude; OBJECT result; opt(4) label | a random member of the label's list other than `exclude`; none when empty (`0x41f350`) | yes | read |
| 97 | Record Griefer Penalty | PLAYER; NUMBER | adds n x 0.01 to the player's griefer penalty (`0x35d530`) | no | read |
| 98 | Set Shape Owner | OBJECT; opt(2) player variable | the shape's colour follows that player | yes | read |
| 99 | Run Inline Nested Trigger | TRIGGER_BLOCK | runs a range of the flat condition and action arrays through the sequencer | no | read |
| 100 | Call HaloScript Function | u8 v-1 function | maps the index to a string id and runs the scenario script of that name, if the scenario has one (`0x36c1a0`, `0x1f6b60`, `0x1fcf30`) | no | twice; names INFERRED |
| 101 | Get Button Press Duration | PLAYER; u5 button; NUMBER | a per-player input timing (the decompile is truncated) | no | INFERRED |
| 102 | Toggle Vehicle Spawning for Team | TEAM; bool | nothing | no | read |
| 103 | Toggle Vehicle Spawning for Player | PLAYER; bool | nothing | no | read |
| 104 | Set Respawn Vehicle for Player | opt(11) vehicle; PLAYER | the player's respawn vehicle | no | read |
| 105 | Set Respawn Vehicle for Team | opt(11) vehicle; TEAM | the same for every team member | no | read |
| 106 | Hide Object | OBJECT; bool | hides or shows the object | no | read |
| 107-127 | | | nothing is read; the executor ignores them | no | read |

Ids 99-106 are MCC's 2023 additions to Reach (ReachVariantTool). Corpus
counts of the busiest: Modify Variable 32,865; Run Nested Trigger 21,382;
Set Timer Rate 5,710; Submit Incident 4,170; Reset Timer 2,406; Delete
Object 2,255; Modify Score 2,237; Get Killer 2,013.

### Parameter types used by actions

All VERIFIED in the decoder; names of the values INFERRED unless noted.

| Type | Reader | Read as |
|---|---|---|
| PLAYER_OR_GROUP | inline (actions 1, 16, 51, 75-77) | u2: 0 TEAM, 1 PLAYER, 2 all players (nothing more), 3 nothing (resolved like a team) |
| PLAYER_SET | inline (actions 4, 12, 13, 15, 22) | u3: 0 no one, 1 everyone, 2 allies, 3 enemies, 4 one player (PLAYER, then NUMBER: add when non-zero, remove when zero), 5 default, 6-7 nothing. 0, 1 and 4 VERIFIED in behaviour |
| FORMAT_STRING | `0x422be0` | u7 v-1 main string index, then u2 count of tokens (at most 2; a third overwrites the index) |
| FORMAT_TOKEN | `0x422be0` | u3 v-1: -1 none, 0 PLAYER, 1 TEAM, 2 OBJECT, 3 NUMBER, 4 TIMER, 5-6 nothing |
| VECTOR3 | `0x39e0e0` | three s8 (x, y, z), each x 0.1 world units |
| SHAPE | inline (action 10) | u2: 0 none, 1 sphere (NUMBER radius), 2 cylinder (NUMBER radius, top, bottom), 3 box (NUMBER width, length, top, bottom); each x 0.1 |
| WAYPOINT_ICON | inline (action 5) | u5 v-1, then a NUMBER when the icon is 11 (territory; the number picks the letter) |
| METER | `0x423ef0` | u2: 0 none, 1 NUMBER value and NUMBER maximum, 2 TIMER, 3 nothing |
| TRIGGER_BLOCK | `0x423cb0` | u9 first condition, u10 condition count, u10 first action, u11 action count |
| object type | | opt(11): an index into the multiplayer object type list in use |
| incident | | u10 v-1: an index into the flattened incident definitions (the first 418 are `game_incident`) |
| sound | | u7 v-1: an index into the Megalo sound table (one of its 95 slots is filled in CU4) |

Waypoint icons (decoded): -1 none, 0 speaker, 1 dead teammate, 2 lightning
bolt, 3 bullseye, 4 diamond, 5 bomb, 6 flag, 7 skull, 8 crown, 9 VIP,
10 padlock, 11 territory letter, 12-19 territories B-I, 20 supply, 21 supply
health, 22 air drop, 23 ammo, 24 arrow, 25 defend, 26 ordnance, 27 inward.
Unreal draws no Megalo waypoint, so no icon shows today. MJOLNIR's CTF writes
7, skull in this list, where Bungie's flag uses 6
(`crates/blam-megalo/src/ctf.rs:47`; the dumps show `icon: skull` and
`icon: flag`).

Timer rates (u5): 0 0%, 1 -10%, 2 -25%, 3 -50%, 4 -75%, 5 -100%, 6 -125%,
7 -150%, 8 -175%, 9 -200%, 10 -300%, 11 -400%, 12 -500%, 13 -1000%, 14 10%,
15 25%, 16 50%, 17 75%, 18 100%, 19 125%, 20 150%, 21 175%, 22 200%,
23 300%, 24 400%, 25 500%, 26 1000%.

Create Object flags (u3): 1 never garbage collect, 2 suppress effect,
4 absolute orientation.

Loadout palettes (u3 v-1): -1 none, 0 Spartan tier 1, 1 Elite tier 1,
2 Spartan tier 2, 3 Elite tier 2, 4 Spartan tier 3, 5 Elite tier 3.

Buttons (action 101, u5): 0 jump, 1 switch grenade, 2 switch weapon,
3 context, 4 melee, 5 equipment, 6 throw grenade, 7 fire, 8 crouch, 9 zoom,
10 night vision, 11 fire secondary, 12 fire tertiary, 13 vehicle trick.

## Operands

### NUMBER (`0x421a00`, evaluator `0x420580`)

u6 kind. Payloads VERIFIED from the jump table; every kind checked against
what the evaluator reads. "Megalo state" is `G+0x1bc` (`0x404620`).

| Kind | Name | Payload | CU4 reads |
|---|---|---|---|
| 0 | constant | s16 | the value |
| 1 | player number | PLAYER_REF, u3 index | per-player state number |
| 2 | object number | OBJECT_REF, u3 index | the object's `MO` number (an object with no `MO`: the declaration's initial value) |
| 3 | team number | TEAM_REF, u3 index | per-team state number |
| 4 | global number | u4 index | global number |
| 5 | user option | u4 index | the option's current value |
| 6 | spawn sequence | OBJECT_REF | `MP+0x1a` (signed byte) |
| 7 | team score | TEAM_REF | `0x2adf80` |
| 8 | player score | PLAYER_REF | `0x2adc70` |
| 9 | player money | PLAYER_REF | `0x42abd0` |
| 10 | player rating | PLAYER_REF | from the 15 rating parameters |
| 11 | player statistic | PLAYER_REF, u2 index | the script statistic |
| 12 | team statistic | TEAM_REF, u2 index | the script statistic |
| 13 | current round | | `0x2af7c0()` |
| 14, 15 | symmetry, symmetry (pregame) | | the same getter, engine globals `+0x1c8`; not the variant's symmetric bool |
| 16 | score to win | | `o+0xf83c` |
| 17 | fireteams enabled | | `o+0xf83e` |
| 18 | teams enabled | | `o+0x2b8` bit 0 |
| 19 | round time limit | | `o+0x2ba` x 60 |
| 20 | round limit | | `o+0x2bb` |
| 21 | perfection enabled | | `o+0x2b8` bit 3 |
| 22 | rounds to win | | `o+0x2b9` |
| 23 | sudden death time | | `o+0x2bc` |
| 24 | grace period | | `o+0x2be` |
| 25-32 | lives per round, team lives, respawn time, suicide penalty, betrayal penalty, respawn growth, loadout camera time, respawn traits duration | | `o+0x2c1`..`o+0x2c8` |
| 33-37 | friendly fire, betrayal booting, proximity voice, don't team-restrict chat, dead players can talk | | `o+0x2f8` bits 0-4 |
| 38 | grenades on map | | `o+0x2fc` bit 0 |
| 39 | indestructible vehicles | | `o+0x2fc` bit 5 |
| 40-42 | red, blue, yellow powerup duration | | `o+0x3b4`..`o+0x3b6` |
| 43 | death event damage type | | Megalo state `+0x1c` (`G+0x1d8`) |
| 44 | temporary number | u4 index | the temporaries block |
| 45-63 | | none | 0 |

### PLAYER, OBJECT, TEAM, TIMER, VAR

| Type | Decoder | Kinds |
|---|---|---|
| PLAYER u2 | `0x41fab0` | 0 PLAYER_REF; 1 PLAYER_REF's player variable (u2); 2 OBJECT_REF's player variable (u2); 3 TEAM_REF's player variable (u2) |
| OBJECT u3 | `0x422640` | 0 OBJECT_REF; 1 PLAYER_REF's object (u2); 2 OBJECT_REF's object (u2); 3 TEAM_REF's object (u3); 4 PLAYER_REF's biped; 5 a player variable's biped (PLAYER_REF, u2); 6 an object's player's biped (OBJECT_REF, u2); 7 a team's player's biped (TEAM_REF, u2) |
| TEAM u3 | `0x420480` | 0 TEAM_REF; 1 PLAYER_REF's team variable (u2); 2 OBJECT_REF's team variable (u1); 3 TEAM_REF's team variable (u2); 4 PLAYER_REF's team; 5 OBJECT_REF's owner team; 6-7 nothing |
| TIMER u3 | `0x4239e0`, resolver `0x4235e0` | 0 global timer (u3); 1 PLAYER_REF's (u2); 2 TEAM_REF's (u2); 3 OBJECT_REF's (u2); 4 round timer, 5 sudden death, 6 grace period (engine globals `+0x134`/`+0x138`/`+0x13c`; names by order); 7 nothing |
| VAR u3 | `0x4227d0` | 0 NUMBER, 1 PLAYER, 2 OBJECT, 3 TEAM, 4 TIMER; 5-7 nothing |

Several actions (4-8, 10, 22, 53, 85) treat OBJECT kinds 4-7 (a player's
biped) as the player: a waypoint or shape set that way is the player's own.

### References

| Enum | Values (raw for PLAYER_REF and OBJECT_REF, decoded for TEAM_REF) | Resolver |
|---|---|---|
| PLAYER_REF u5 | 0 none; 1-16 player 0-15; 17-24 `global.player[0..7]` (`G+0x284`); 25 current player; 26 HUD player; 27 HUD target player; 28 killer player (`G+0x1d4`); 29-31 temporaries 0-2 | `0x441380` |
| OBJECT_REF u5 | 0 none; 1-16 `global.object[0..15]` (`G+0x1ec`); 17 current object; 18 HUD target object; 19 killed object; 20 killer object; 21 always none in CU4; 22-29 temporaries 0-7; 30-31 none | `0x441530` |
| TEAM_REF u5 v-1 | -1 none; 0-7 team 0-7; 8 neutral; 9-16 `global.team[0..7]` (`G+0x22c`); 17 current team; 18 HUD player's team; 19 HUD target's team; 20-25 temporaries 0-5; 26-30 as 19 | `0x441610` |

Every value resolves to a defined slot; none reads out of bounds. VERIFIED.
The names of 26, 27 (players) and 18 (objects, teams) are INFERRED.

## Where CU4 differs from ReachVariantTool

| Item | CU4 | ReachVariantTool | Effect |
|---|---|---|---|
| general, respawn and social flags | N bools, first read = bit 0 | one N-bit number | names agree; bit constants do not |
| trigger type 5 label | opt(4) (CU4's own encoder `0x382060` agrees) | 5 raw bits, none = `11111` | a labelless type-5 trigger it writes misaligns CU4 by 4 bits |
| content header, activity 2 | no hopper id | u16 hopper id | misaligns CU4 by 16 bits |
| content types 3 and 4 | a u32 | nothing | films only |
| statistic sort order | stores raw - 1 | casts the raw value | Bungie uses raw 0 and 1 |
| NUMBER 14 and 15 | one getter | read-only versus pregame-writable | the variant's symmetric bool is not what they read |
| condition 7 | gated on fireteams enabled | not described | with it set, designators 0 and 1 always have players |
| OBJECT_REF 21 | always none | unknown object | |
| out-of-range selectors (TEAM_REF raw 27-31, VAR 5-7, TEAM 6-7, TIMER 7, NUMBER 45-63) | read, no error | load errors | CU4 is more permissive |
| counts and table sizes | not enforced | enforced | see *Limits* |
| object type ids | the CU4 list in use (18 weapons; MJOLNIR adds 18 flag and 19 health pack) | Reach's list (flag 3, hill marker 6, ...) | a Reach script's bitset fails validation or creates the wrong objects; trait and loadout weapon indices need remapping too |

## Limits a validator must enforce

CU4's decoder enforces almost none of the store sizes above, and the
executor checks few indices. Every store equals ReachVariantTool's maximum
and the next field follows it directly, so a larger count overwrites the
next field. All rows VERIFIED in the decoder or executor
(2026-10-21).

At load:

| Field | Safe limit | What a larger value hits |
|---|---|---|
| whole `.mglo` file | 0x5000 bytes | the patched loader's buffer ([megalo_engine.md](megalo_engine.md)) |
| main string data | 0x4c00 bytes uncompressed, and the embedded size of compressed data | `0x3949c0` writes past `o+0x11b8` over the string count, the encoding version and the whole script; with zlib the bytes are the author's |
| main string count | **112** (one language's offset row is 0xe0 bytes) | the next language's row; the last one reaches the string data. `mjolnir megalo write` refuses only above 127 (`crates/blam-cli/src/megalo.rs:298`) |
| localized name and category / description / team name data | 0x180 / 0xc00 / 0x20 bytes | |
| HUD widgets | **4** (the stream allows 7) | the engine's widget records run into player 0's Megalo state (`0x40a130`) |
| script traits, user options | 16, 16 | the next counter |
| user option values | 8 | the next option |
| conditions, actions, triggers | 512, 1024, 320 | the next counter |
| statistics, labels | 4, 16 | the next field |
| variables | each scope's maximum (table above) | the next scope |
| map permissions | 32 | a larger count skips the ids and the bool (misalignment) |

At run time:

| Item | Check in CU4 | Consequence |
|---|---|---|
| Run Nested Trigger (20) index and nesting | none; no depth limit | an index past the triggers runs a garbage record; a trigger that reaches itself overflows the stack |
| a trigger's condition and action ranges | none (`0x423a70`) | records past the arrays are evaluated and executed |
| object types in actions 2, 87, 93, 104, 105 | none against the list's count (`0x41c3b0`, `0x421b80`) | reads past the type list; only the bitset is validated |
| compare operator 6-7, trigger type 6-7 | none | jumps past six-entry tables: a crash |
| math operator 13-15 | none | jumps past the 13-entry table |
| action types 107-127, references, incident index, HaloScript index (100) | yes | nothing, a defined slot, a walk bounded by the count, an existing script only |
| sound index (16, 51) | not traced | open |

A hub validator should therefore reject: any count above the limits above;
condition types above 17, action types above 106, trigger types above 5,
compare operators above 5, math operators above 12; a trigger whose ranges
leave the arrays or whose conditions point past its actions; a Run Nested
Trigger index past the triggers or any cycle through actions 20 and 99 (and
cap the depth); an object type in an action or condition that the variant's
bitset does not declare; an incident index outside the known definitions;
and the selector values ReachVariantTool rejects. It must run wherever a
variant is decoded: at upload and again on every machine before staging
(the hub design in [`../custom_game_types.md`](../custom_game_types.md)).
After a round reset, a variant that decoded and survived validation has
version `0x6a` or `0x6b` at `o+0x5dc0`, a trigger count above 0 at
`o+0x63f4` and entry points other than -1; a script the validator `0x40a310`
wiped has its whole script region zeroed and every entry point -1.

## Corrections to this page

- Before 2026-10-21 the ACTIONS section listed actions 30, 31 and 99 as
  trigger blocks. Only 99 reads a trigger block; 30 and 31 read a PLAYER and
  a NUMBER (Get Death Damage Type and Modifier). Every Slayer, Headhunter,
  Oddball and title-update variant uses them, and the round trip confirms
  the layout.
- The operator list called 9 "not" without saying what it computes: it
  assigns `~b` (`0x40879d`), ignoring `a`.
- The "needed ones" list of actions is replaced by the full table above.
- The decompile once cited for the per-type decoder (`scratch/megalo/d_39cf20.c`)
  is not in the repository; the grammar file now carries what it showed.
