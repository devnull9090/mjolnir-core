# Map variants (Forge layouts) in CU4

**Status:** 2026-10-24. The codec is VERIFIED against every map variant MCC
ships for Halo Reach: 277 of 277 round-trip bit for bit, and each decodes to
the last byte of its declared payload.
**Binary:** `HaloSimulation_tag_release.dll`, CU4. Every address is an RVA.
**Code:** `crates/blam-megalo` (`blf::map_variant`, `raw::decode_map_variant`,
`raw::round_trip_map_variant`, the `map_variant` list in
`grammar/megalo_cu4.json`), test `bungie_reach_map_variants_round_trip`,
example `mvar_summary`.
**See also:** [forge_engine.md](forge_engine.md) (the editor that makes
them), [megalo_variant_format.md](megalo_variant_format.md) (game variants,
the same container and content header).

A map variant is what Forge edits and saves: which objects are placed on a
map, where, and with what Forge properties. In Reach it is a file of its own
(`.mvar`), separate from the game type, so any game type plays on any
layout. That separation is what lets layouts be shared like game types.

## What the simulation has

| Piece | Address | Status |
|---|---|---|
| Decode (map variant from a bitstream) | `0x32d810` | VERIFIED (read and modelled; the codec built from it round-trips 277 files) |
| Encode (the mirror: 28 bit writes against the decoder's 28 reads) | `0x32cfb0` | VERIFIED as the writer by its call shape; not read field by field |
| Session parameter: a presence bit, then a map variant | `0x532330` (decode) | VERIFIED (code) |
| Normalise: encode into a 0x7000-byte buffer, decode back | `0x5323a0` | VERIFIED (code) |
| In-memory map variant (651 objects of 0x4c at `+0x14fc`) | `0x32b600()` | VERIFIED (live, [forge_engine.md](forge_engine.md)) |
| File commands `read_map_variant_and_make_current`, `write_current_map_variant`, `net_load_and_use_map_variant`, `net_build_map_variant`, `net_verify_map_variant` | strings only | stubs, like the rest of the console ([`../blam_console.md`](../blam_console.md)) |

So the simulation can serialise a layout and send it across a session (which
is how every fireteam member would see the host's Forge edits), but nothing
reads or writes a layout file. Saving and loading are ours to build, from a
native hook that calls the encoder and decoder, as the `.mglo` loader fix did
for game variants ([megalo_engine.md](megalo_engine.md)).

## The file (`.mvar`)

All 277 MCC files have the same layout and the same size (29,945 bytes):
`_blf` 1.2, `chdr` 10.2, `mvar` 31.1, `_eof` 1.1, all chunks with 12-byte
big-endian headers (signature, size including header, major, minor). The
`mvar` body is a 20-byte hash, a big-endian u32 payload length, and the
payload: the bitstream below, from bit 0, padded with zeros to a fixed
chunk size. The hash algorithm was not checked.

MCC's files: `haloreach/map_variants` (11, the built-in layouts of Forge
World and the DLC maps) and `haloreach/hopper_map_variants` (266,
matchmaking layouts). They are Microsoft content: a local reference only.

## The bitstream (`0x32d810`)

MSB-first, the same reader as game variants (`0x2abe70`). Names follow Halo
Reach's Forge where the meaning was confirmed by the decoded values;
`unkXXX` fields are named for where CU4 stores them.

| Field | Bits | Notes |
|---|---|---|
| content header | (`0x38f5d0`) | shared with game variants; content type 5 (map variant), title and description (UTF-16), authors, game mode |
| encoding version | 8 | 31 in every MCC file; below 31 the decoder stops |
| unk2ec, unk2f0 | 32, 32 | |
| quota count | 9 | the palette-quota list at the end; objects and quotas are read only when this is at most 256 |
| map id | 32 | 3006 = Forge World in Bungie's files |
| built-in, unk2ea | 1, 1 | |
| world bounds | 6 × f32 | x min, x max, y min, y max, z min, z max; positions are quantised inside these |
| unk2e0, unk2e4 | f32, 32 | |
| label count | 9 | then per label: a bit, and when it is 1 a 12-bit index into the label strings |
| label strings | 13 + 1 (+13) + bytes | only when there are labels: size, compressed bit, compressed size when set, then the bytes |
| unk2b8, unk2bc, unk2be, unk2c0 | 32, 16, 16, 64 | only for version > 31 (no MCC file); if all are zero the decoder fails |
| objects | 651 × | below |
| quotas | quota count × (8, 8, 8) | minimum, maximum, placed per palette entry |

Each of the 651 object slots: a presence bit, and when present:

| Field | Bits | Notes |
|---|---|---|
| flags | 2 | |
| palette entry | opt 8 | index into the scenario's **sandbox palette** |
| variant | opt 5 | the object's variant |
| position | 1 + x + y + z | x, y and z widths from the bounds (below) |
| up | opt 20 | absent = straight up; else a 20-bit unit vector (`0x3f57d0`) |
| yaw | 14 | radians = raw × 0.000383495 − 3.141401 |
| parent | 10, minus 1 | spawn-relative object; -1 none |
| Forge properties | (`0x330230`) | below |

**Position widths** (`0x50e990` with precision 21, widths from `0x512fc0`):
the step is 1/60 world unit divided by 2^(precision − 16), so 1/1920 at 21.
Each axis gets `ceil(log2(ceil(span / step)))` bits, at most 26 (and 26 on
every axis when the step falls below 0.0001). A value decodes to
`min + span / 2^bits × (raw + 0.5)`. Forge World's bounds give 20, 21 and 19
bits. The decoder only *reads* positions inside the bounds. Every one of the
objects in the two files checked decoded inside them.

**Forge properties** (`0x330230`):

| Field | Bits | Notes |
|---|---|---|
| shape | 2 + 11 per dimension | 0 none, 1 sphere (radius), 2 cylinder (radius, top, bottom), 3 box (width, length, top, bottom); 0.0977 world units per step after 1, 0x7ff = 200 |
| spawn sequence | s8 | |
| respawn time | 8 | seconds (180, 60, 45 in Paradiso) |
| object type | 5 | multiplayer object type; picks the extra fields |
| label | opt 8 | Megalo label index |
| flags | 8 | |
| team | 4, minus 1 | 0 red, 1 blue, ..., 8 neutral in Bungie's files |
| color | opt 3 | |
| type 1 (weapon) | 8 | spare clips |
| types 12, 13, 14 (teleporters) | 5, 5 | channel, passability |
| type 19 | 8, minus 1 | location name |

## Checks

`cargo run -p blam-megalo --example mvar_summary -- <file.mvar> 6` decodes a
file and reprints it in world units:

```
hr_forgeWorld_paradiso.mvar
  title "$HReach_MPMap_R-23_Title"   map id 3006   version 31
  bounds x -203.60..277.66 y -360.83..324.92 z -25.01..117.79  position bits [20, 21, 19]
  labels 27, 308 bytes of label strings, 144 quotas
  objects placed 629 of 651, outside the bounds: 0
atom.mvar
  title "Atom"  "Set up for all Slayer/TS Variants, CTF, KOTH, Headhunter & Stockpile. ..."
  objects placed 478 of 651, outside the bounds: 0
```

Run the round trip with
`MCC_REACH=<haloreach dir> cargo test -p blam-megalo --test roundtrip`.

## For CE maps

A Reach layout names Reach's palette entries and Forge World's bounds, so it
does not carry over to a CE map as-is. A layout made in our Forge would use
the converted scenario's own sandbox palette, map id and bounds. What stays
the same is the format, the codec, and the simulation's own encoder,
decoder and session transport, which is what a hub content type for layouts
needs.

## Next steps

1. A native save/load: call `0x32cfb0` on the live map variant (`0x32b600()`)
   and write the bytes, and the reverse through `0x32d810`, then make it
   current. Find what the stubbed `read_map_variant_and_make_current`
   should have called.
2. Give converted CE scenarios a full sandbox palette and record their
   bounds, so a layout made in game is valid there.
3. A hub content type for layouts (map + layout, played with any game type),
   and fireteam delivery the way `.mglo` files travel now.
