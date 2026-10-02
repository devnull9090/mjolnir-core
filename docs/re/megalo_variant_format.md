# The Megalo variant bitstream (CU4)

**Source:** static reading of the CU4 simulation's own decoder,
`HaloSimulation_tag_release.dll` `0x392a40` (Megalo vtable `0x83c3b8` slot 5)
and everything it calls, 2026-09-30. Field order and widths are verified from
the decompiled readers; meanings are named where the code or ReachVariantTool's
public layout makes them clear. Written by `crates/blam-megalo`
(`mjolnir megalo write`); overview and the loading path in
[megalo_engine.md](megalo_engine.md).

```text
CU4 HaloSimulation_tag_release.dll - Megalo variant bitstream grammar as read by 0x392a40 (vtable 0x83c3b8 slot 5)
All RVAs CU4. "o" = variant object (= variant + 4). Store offsets are o-relative.

BIT READER (0x2abe70 u(n), 0x206580 bool, 0x2abf60 u64, 0x2abc60 bytes)
  - MSB-first; the byte stream is consumed as big-endian 64-bit words; u(n) returns the next n bits unsigned.
  - bool = 1 bit, 1 = true.  "opt(n)" below = bool, if bool==1 -> absent (0xff / -1) else u(n)  [unless marked PRESENT-IF-1]
  - "v-1" = stored value is read value minus 1 (so encode stored+1; 0 encodes "none"/-1)
  - signed10 = u(10) sign-extended from bit 9

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
  15 x u32  rating params (floats)              (o+0xf7fc)
  u1   flag                                     (o+0xf838)
  u16  score to win                             (o+0xf83c)  [number operand kind 16 reads it]
  bool                                          (o+0xf83e)  [vt+0x40 getter]
  bool                                          (o+0xf83f)
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
      7:                TEAM
      8, 13:            OBJECT
      9, 12, 14, 15, 16: PLAYER
      10:               PLAYER ; PLAYER
      11 has label:     OBJECT ; opt(4) label
  Sequencing (0x423a70): a condition gates actions whose index >= its action offset; consecutive conditions
  with the same or-sequence are OR-ed, a new or-sequence value starts an AND.

ACTIONS (store o+0x930c, 20 B each; u11 count <= 1024; decoder 0x39cf20; executor 0x399110)
  u7 type (0 = none); needed ones:
    1  modify score : u2 target (1 = PLAYER, 0 = TEAM) ; operand ; u4 operator ; NUMBER value
        operators (0x408730): 0 add, 1 sub, 2 mul, 3 div, 4 set, 5 mod, 6 and, 7 or, 8 xor, 9 not, 10 shl, 11 sar, 12 abs
    20 call trigger : u9 trigger index
    21 end round    : (no params)   -> 0x2afa70, engine globals +0x845c = 2
    29 get killer   : PLAYER victim ; PLAYER out  (finds victim in this tick's death records, writes killer)
    30, 31, 99      : TRIGGER-BLOCK (u9 u10 u10 u11) nested/inline block
  Full per-type decoder: scratch/megalo/d_39cf20.c

TRIGGERS (store o+0x63fc, 12 B each)
  u9 count (<=320); each:
    u3 type (0 do, 1 each player, 2 each player random, 3 each team, 4 each object, 5 each object with label)
    u3 attribute (runtime: host per-tick loop 0x3fe520 runs attribute 0 and 6; entry points are separate)
         RVT numbering (Inferred): 0 normal, 1 subroutine, 2 init, 3 local init, 4 host migration,
         5 object death, 6 local, 7 pregame
    if type == 5: opt(4) label index
    u9 first condition ; u10 condition count ; u10 first action ; u11 action count   (0x423cb0)

VARIABLES (counts, then per entry)
  global:  u4 numbers {NUMBER default ; u2 net priority} ; u4 timers {NUMBER} ; u4 teams {u4 team (v-1) ; u2} ;
           u4 players {u2} ; u5 objects {u2}
  player:  u4 numbers {NUMBER ; u2} ; u3 timers {NUMBER} ; u3 teams {u4 (v-1) ; u2} ; u3 players {u2} ; u3 objects {u2}
  object:  u4 numbers {NUMBER ; u2} ; u3 timers {NUMBER} ; u2 teams {u4 (v-1) ; u2} ; u3 players {u2} ; u3 objects {u2}
  team:    u4 numbers {NUMBER ; u2} ; u3 timers {NUMBER} ; u3 teams {u4 (v-1) ; u2} ; u3 players {u2} ; u3 objects {u2}

OPERANDS
  VAR (0x4227d0):   u3 kind: 0 NUMBER, 1 PLAYER, 2 OBJECT, 3 TEAM, 4 TIMER
  NUMBER (0x421a00): u6 kind:
      0 constant: u16 (signed)
      1 player.number[i]: u5 player ref, u3 i        2 object.number[i]: u5 object ref, u3 i
      3 team.number[i]: u5 team ref (v-1), u3 i       4 global.number[i]: u4 i
      5 user option i: u4 i                           44: u4
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
  TEAM (0x420480):   u3 kind: 0 -> u5 (v-1) ; 1 -> u5, u2 ; 2 -> u5, u1 ; 3 -> u5 (v-1), u2 ; 4,5 -> u5
  TIMER (0x4239e0):  u3 kind: 0 -> u3 ; 1,3 -> u5, u2 ; 2 -> u5 (v-1), u2
```
