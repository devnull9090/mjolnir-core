# Reading the Simulation's Game State: Objects and Players

**Build:** `2026.08.11.1121610.2-Rel-i343-Meteorite-2607-CU4` (Steam), tag module
`C8C14440…3BF7`
**Code:** `crates/blam-live/src/gamestate.rs`, `crates/blam-live/src/world.rs`,
`mjolnir live objects|players|arrays`
**Date:** 2026-09-29

## Summary

**Verified:** every per-game table the simulation keeps (objects, players,
actors, squads, script threads and about fifty more) is a Blam **data array**,
and the pointer to each array's header is stored in the tag module's static
**thread-local storage** on the simulation thread. None of them is a module
global. So the tables are found without a signature or a per-build address:

1. The TLS slot number comes from the module's own PE TLS directory
   (`AddressOfIndex`, RVA `0xD72730` on CU4). The block is 0x650 bytes.
2. Each thread's `TEB + 0x58` (`ThreadLocalStoragePointer`), indexed by that
   slot, gives the thread's copy of the block.
3. Only the simulation thread's copy is populated. It is the one holding a
   pointer to a header named `object` with the `d@t@` magic at `+0x28`.

Measured in mission A30, from the menu through New Game. Of ~170 threads, one
(the simulation thread) held 59 arrays. At the frontend the same 59 were already
there, but marked invalid.

The header layout is shared by every array, `tag instance` included. The
object datum and player layouts below are CE's own. They descend from Reach,
not from the Xbox engine.

## Data array header (0x70 bytes)

Read off the `players` constructor (RVA `0x181010`) and the `object`/`lights`
constructors (inside `0x59c520`).

| Offset | Field | Notes |
|---|---|---|
| `+0x00` | name, `char[32]` | NUL-terminated, so at most 31 characters survive: `collision hierarchy element hea` |
| `+0x20` | element size, u64 | |
| `+0x28` | magic `0x64407440` (`d@t@`) | |
| `+0x2C` | maximum count, u32 | |
| `+0x31` | valid, u8 | set once reset for a game; 0 at the menu |
| `+0x32` | flags, u16 | constructors OR in 4 |
| `+0x38` | allocator | |
| `+0x44` | high water (first unallocated), u32 | |
| `+0x48` | live count, u32 | |
| `+0x4C` | next identifier (salt), u16 | |
| `+0x50` | elements pointer | `header + 0x70` when allocated inline |
| `+0x58` | in-use bitset pointer | |
| `+0x60` | offset to elements, `0x70` | |
| `+0x68` | offset to bitset | `0x70 + max × size` |

Every element starts with its u16 salt, and a handle is `salt << 16 | index`.
The first salt is the name's first two bytes, little-endian, with the top bit
set, and each allocation takes the next one. So `object` handles start at
`0xE26F`, `players` at `0xEC70`, `tag instance` at `0xE174`. A handle's high
word says which array it came from.

## Where the arrays sit

A selection of the CU4 block. `mjolnir live arrays` prints all of it. The
reader finds arrays by name, so a slot moving in a later build costs nothing.

| TLS offset | Array | Element | Maximum |
|---|---|---|---|
| `+0x020` | `object` | 0x18 | 2048 |
| `+0x028` | `actor` | 0xD10 | 96 |
| `+0x030` | `players` | 0x4B0 | 16 |
| `+0x058` | `squad` | 0xEC | 512 |
| `+0x138` | `fire team` | 0xD4 | 16 |
| `+0x178` | `lights` | 0xBC | 600 |
| `+0x2F0` | `hs globals` | 0x8 | 4096 (1,475 in use in A30) |
| `+0x360` | `det hs thread` | 0x52C | 320 |
| `+0x3A0` | `megalo_objects` | 0x94 | 512 |

`hs globals` holding 1,475 values fits the script compiler's engine-global
references running past index 1471, far beyond the 260 globals in
`defs/hce/console.json`.

## Object header entry (0x18 bytes)

| Offset | Field |
|---|---|
| `+0x00` | salt, u16 |
| `+0x02` | flags, u8 (`0x87` on the player's Spartan, `0x81` on most others) |
| `+0x04` | object type, u16: Reach's enum |
| `+0x06` | datum size, u16 |
| `+0x08` | datum offset in the object pool, u32. Consecutive datums sit `size + 0x10` apart |
| `+0x0C` | the entry's own index, u16. The reader refuses the table if this does not match |
| `+0x10` | datum pointer |

Type codes seen with a matching tag group: 0 biped (`bipd`), 2 weapon (`weap`),
3 equipment (`eqip`), 4 terminal (`term`), 7 machine (`mach`), 13 effect
scenery (`efsc`). The rest follow the same enum: 1 vehicle, 5 projectile,
6 scenery, 8 control, 9 sound scenery, 10 crate, 11 creature, 12 giant.

## Object datum

| Offset | Field |
|---|---|
| `+0x00` | definition tag handle: resolves in the tag table |
| `+0x0C` | next sibling object handle |
| `+0x10` | first child object handle |
| `+0x14` | parent object handle |
| `+0x20` | bounding sphere centre (3 floats) and radius |
| `+0x44` | position. Relative to the parent when attached: a held rifle reads `(0.00, 0.02, 0.01)` |
| `+0x50` | forward vector |
| `+0x5C` | up vector |
| `+0x68` | translational velocity |
| `+0x74` | angular velocity |
| `+0x80` | scale |
| `+0x108` | maximum body vitality (Spartan 45, marine 100) |
| `+0x10C` | maximum shield vitality (Spartan 70) |
| `+0x174` | damage section records: byte size, u16 |
| `+0x176` | damage section records: offset from the datum, u16 |

**Vitality lives in the section records**, 0x18 bytes each. The float at
`+0x10` is the current vitality as a fraction, and `+0x0E` is `-1` for a
section not in play.

- **Body:** `object_get_health` (RVA `0x5b7e60`) reads section 0.
- **Shield:** `unit_get_shield` (`0x5b8230`) reads the section named by the
  model. The chain (`0x5b83b0`) is:
  1. the object tag's handle at `+0x00`;
  2. that tag's root `+0x60`, the model reference's handle;
  3. that model's root `+0xF0`, an i16 shield section index. The Spartan's is 2.

**Checked live:** `unit_set_current_vitality (player_get 0) 20 35` put section 0
at 0.469 and section 2 at 0.578 on the next 10 Hz sample. The shield recharged
to 1.0 within 1.2 s and the body regenerated over about 8 s. `unit_get_shield`
answered 0.672 in the middle of that. The marines around the crashed lifeboat
at the start of A30 read 0: they are the dead crew.

## Player datum (0x4B0 bytes)

| Offset | Field |
|---|---|
| `+0x00` | salt (`0xEC70` for player 0) |
| `+0x28` | controlled unit handle: what `player_get` (RVA `0x1b21e0`) returns |
| `+0x34` | the same handle again in A30. Meaning not established |
| `+0x38` | a position near the unit's |

The gamertag is not in the datum.

## Using it

```
mjolnir live arrays                       every data array, offset, fill, size
mjolnir live players                      each player, its unit and position
mjolnir live objects [--group bipd] [--filter marine] [--tsv out.tsv]
mjolnir live status                       now also names the simulation thread
```

A call takes about half a second, because the whole process's thread list is
walked once. `arrays` needs no build profile. `objects` and `players` also name
each object's tag, so they use the tag table's profile, as `live tags` does.

## What this does not do yet

- Reads only. Writing position or vitality is a plain write at these offsets.
  But object state is game state: a checkpoint revert restores it, and the
  simulation overwrites the transform of anything physics or animation is
  driving.
- The datum offsets are CU4's. A game update keeps the TLS walk and the
  array headers working. It can move the datum fields, and the entry
  self-index and tag-handle checks are what would notice.
