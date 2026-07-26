# Blam Tag Body Format (`blay` Layout Section)

**Build:** `2026.06.26.1097863.1-Rel-i343-Meteorite-2606-CU2` (Steam)
**Artifacts:** `Meteorite/Content/Paks/*.utoc` + `*.ucas`, 28 containers
**Tool:** `tools/iostore/decode_body.py`
**Date:** 2026-07-26

## Summary

**Verified:** the Blam tag body that follows the `0x4C`-byte container header is
**self-describing**. Every shipped tag carries a `blay` ("blam layout") section containing a
string blob of field names, type names, and enum/bitfield option names, plus tables that
reference them by byte offset.

The entire body is built from **one repeating shape**: a 12-byte header of
`{magic: four-CC, version: u32, size: u32}` followed by `size` bytes of content, where `size`
excludes the header. Sections chain as siblings and nest as children, at every level. A second
top-level `bdat` section holds the tag's actual field values.

This supersedes the "Next Checks" item in [tag_data_pipeline.md](tag_data_pipeline.md) that
proposed recovering field definitions from `HaloSimulation_tag_release.dll`. **The engine
binary is not required.** Definitions for all 101 shipped groups are generated mechanically
from the shipped tag files.

Reproduction:

```
$env:HCE_PAKS = "<install>\Meteorite\Content\Paks"
$env:OODLE    = "<UE>\Engine\Binaries\DotNET\AutomationTool\oo2core_9_win64.dll"

cargo run --release -p blam-cli -- groups
cargo run --release -p blam-cli -- layout --group camera_track --tables
cargo run --release -p blam-cli -- fields --group weapon
cargo run --release -p blam-cli -- types
```

The Rust reader in `crates/blam-tag` parses **101/101 groups** across all **12,290** shipped
payloads, and recovers a complete field list for **101/101**.

## Section Layout

The body is a chain of sections. Every section, at every level, is:

```
+0x00  four-CC magic, stored reversed
+0x04  u32 version
+0x08  u32 content size, EXCLUDING this 12-byte header
+0x0C  content
```

The tag body contains two top-level sections:

```
blay                    layout: the tag's own field definitions
  tgly                  container
    str*                NUL-separated UTF-8 string blob
    <options>           enum and bitfield option name offsets
    tgft                type table
    gras                field list
    blv2                block table
    stv4                struct table
bdat                    data: the tag's field values
  tgbl                  container
```

Body offsets below are relative to the start of the tag body, which begins at file offset
`0x4C`. File offsets in the worked example are for `default-weapon.ubulk`
(`weap`, group version 2, chunk length 27,599).

### `blay` header — body `0x00`, fixed `0x58` bytes

### `blay` header — body `0x00`

A standard 12-byte section header, followed by a fixed `0x4C`-byte preamble before its first
child section.

| Body offset | Size | Field | Evidence |
|---:|---:|---|---|
| `0x00` | 4 | `blay` four-CC, stored reversed (`79 61 6c 62`) | Verified |
| `0x04` | 4 | Section version. `2` in `101/101` groups. | Verified |
| `0x08` | 4 | Content size, excluding this 12-byte header. | Verified |
| `0x0C` | 4 | `0xFFFFFFFF` | Verified |
| `0x10` | 4 | ASCII `4444` (`0x34343434`) | Verified |
| `0x14` | 4 | ASCII `CCCC` (`0x43434343`) | Verified |
| `0x18` | 4 | ASCII `wwww` (`0x77777777`) | Verified |
| `0x1C` | 4 | Per-group 32-bit value (`weap` = `0xDB837039`) | Observed |
| `0x20` | `0x38` | Table of counts and sizes, uninterpreted. | Observed |
| `0x58` | — | First child section (`tgly`). | Verified |

The `4444` / `CCCC` / `wwww` dwords recorded as uninterpreted markers in
[tag_data_pipeline.md](tag_data_pipeline.md) are **fixed ASCII fill constants** at body
`0x10`–`0x18`. They are group-invariant and carry no per-tag information.

Because `size` excludes the header, `blay` content spans `[0x0C, 0x0C + size)` and the `bdat`
section begins exactly at `0x0C + size`. This was **Verified** against `weap`, where
`0x0C + 0x6297 = 0x62A3` lands precisely on the `bdat` header.

### `tgly` section — body `0x58`

A standard section, version `4`, containing every definition table as sibling children. Its
content ends at the same byte as the enclosing `blay` content, so it is a container rather than
a sibling. **Verified** across all 101 groups.

### `str*` section — first child of `tgly`

A standard section whose content is a NUL-separated UTF-8 string blob.

Strings are referenced elsewhere by **byte offset into the blob**, not by index. Verified by
resolving offsets back to strings across all 101 groups; hand-checked for the first 17
entries of `weap` (`50` → `does not cast shadow`, `71` → `search cardinal direction lightmaps
on failure`, `328` → `sample enviroment lighting only ignore object lighting`, and so on —
the misspelling of "enviroment" is present in the shipped data).

An offset pointing directly at a NUL resolves to the empty string, which the shipped data uses
for **unnamed fields** such as padding and terminators.

Blob contents mix three categories in definition order: **field names**
(`rounds total maximum`), **type names** (`long flags`, `word flags`, `short integer`,
`struct`, `custom`), and **enum/bitfield option names** (`early mover`, `super_sinker`).

Blob sizes range from 12 strings (`breakable_surface`) to 1,038 (`character`). `weap` carries
783.

**Note:** the blob is byte-packed, so the section that follows it frequently begins on an offset
that is not 4-byte aligned. Do not assume dword alignment anywhere in the layout section.

### `x+zs` option table — immediately after the string blob

A standard section. Its magic varies between groups (`x+zs` in most, `sz[]` and others
elsewhere), so it is located positionally as the section following `str*` rather than by name.
Content is an array of string-blob offsets, one per enum or bitfield option, in declaration
order. **Verified.**

Worked example, `weap` entries 0–16 resolve to the 17 bits of `object flags` in order, then
`{default, never, always, blur}`, then `{default, small, medium, large}`, then
`{default, super_floater, …, super_sinker, none}` — contiguous option runs for consecutive
enum and bitfield definitions.

**Superseded 2026-07-26.** An earlier revision of this note read the section's `size` word as an
*entry count* and reported that the count overran the enclosing section in 16 of 101 groups. That
was a misreading: the word is the section size **in bytes**, consistent with every other section.
`weap` declares `1,312` bytes, which is `328` options, not `1,312`. Reading it as a byte size
resolves all 16 groups, and no group overruns.

### Definition tables

Sibling sections under `tgly`, all using the standard 12-byte header. Empty tables are present
with `size = 0` rather than omitted. **Verified** across all 101 groups.

| Magic | Record | Meaning |
|---|---|---|
| `tgft` | `{name_offset, size, flags}` | Type table. `size` is the on-disk width in bytes; `flags` is non-zero for composite types such as `block`. |
| `gras` | `{name_offset, type_index, aux}` | Field list. `type_index` indexes `tgft`. |
| `blv2` | `{name_offset, max_count, aux}` | Block table. `max_count` is the element limit Guerilla enforced. |
| `stv4` | `{guid[16], name_offset, aux[2]}` | Struct table. Struct definitions carry a GUID, characteristic of third-generation Blam. |

Also present, empty in the sampled groups: `sz[]`, `csbn`, `dtnm`, `arr!`, `rcv2`, `]==[`.

Worked example — `camera_track`, the smallest group, decodes completely:

```
types:  [0] block            12b  flags 1
        [1] real vector 3d   12b
        [2] real quaternion  16b
        [3] terminator X      0b

fields: +0   12b  real vector 3d   position
        +12  16b  real quaternion  orientation
        +28   0b  terminator X     <unnamed>
        +28  12b  block            control points
        +40   0b  terminator X     <unnamed>

blocks: camera_track_control_point_block  max 16
        camera_track_block                max 1
```

That is the real `camera_track` definition, including Halo's actual 16 control-point limit.
`terminator X` fields delimit struct boundaries, so the field list is a **flattened tree** rather
than a nested one.

### Field type vocabulary

**Verified.** 54 distinct type names appear across the 101 groups, and **every one has the same
size in every group it appears in**. That consistency is the strongest available check on the
type table decode.

| Size | Types |
|---:|---|
| 0 | `array`, `custom`, `pad`, `struct`, `terminator X` |
| 1 | `byte flags`, `byte integer`, `char block index`, `char enum`, `char integer` |
| 2 | `custom short block index`, `short block index`, `short enum`, `short integer`, `word flags`, `word integer` |
| 4 | `angle`, `argb color`, `custom long block index`, `dword integer`, `long block flags`, `long block index`, `long enum`, `long flags`, `long integer`, `real`, `real fraction`, `rgb color`, `short integer bounds`, `string id`, `tag` |
| 8 | `angle bounds`, `fraction bounds`, `int64 integer`, `pageable resource`, `real bounds`, `real euler angles 2d`, `real point 2d`, `real vector 2d`, `rectangle 2d` |
| 12 | `api interop`, `block`, `real euler angles 3d`, `real plane 2d`, `real point 3d`, `real rgb color`, `real vector 3d` |
| 16 | `real argb color`, `real plane 3d`, `real quaternion`, `tag reference` |
| 20 | `data` |
| 32 | `string` |
| 256 | `long string` |

The zero-size types are the composite and special cases where the field record's `aux` word
carries the payload; `pad` in particular must consume bytes despite a zero type size.

### `bdat` data section — after `blay`

**Verified.** The second top-level section of the tag body holds the field values. It wraps a
single `tgbl` child, mirroring how `blay` wraps `tgly`.

```
0x62ef  bdat  ver 1  size 0x8D4
0x62fb    tgbl  ver 0  size 0x8C8
0x6307      field values
```

For `default-weapon` the payload is `2,248` bytes; `camera_track` carries `304`. This resolves the
"where does the tag data begin" question left open by the previous revision: it begins immediately
where the layout section ends.

## Group Coverage

**Verified:** all 101 shipped groups parse end to end — `blay` version `2`, a `str*` blob, an
option table, a `tgft` type table, a `gras` field list, and a `bdat` data section. `weap` carries
783 strings, 328 options, 30 types, 503 fields, 30 blocks, and 46 structs.

Group versions at container header `0x34` vary independently (`bsdt` = 0, `bipd` = 3, `effe` = 4,
`jpt!` = 6, `coll` = 10), confirming that value is a per-group definition version rather than a
format version.

## Why This Matters

1. A complete, authoritative definition corpus for all 101 groups is derivable from the shipped
   data alone, including **human-readable field names and option names** — the same strings
   Guerilla displayed.
2. It removes `HaloSimulation_tag_release.dll` from the critical path for a tag editor.
3. Because each tag carries its own layout, a reader can be **fully generic**: no hand-coded
   per-group parsers and no hardcoded offsets.

## Next Checks

1. Determine how `aux` encodes payload for the zero-size types: `pad` length, `struct` and
   `array` targets, `custom` semantics, and which option run an enum or bitfield field owns.
2. Walk the `tgbl` data using the field list and assert it consumes the payload exactly, for all
   12,290 shipped payloads. This is the round-trip oracle.
3. Reconstruct the nested struct tree from the flattened field list plus `terminator X` markers,
   and cross-check against the `stv4` struct table and its GUIDs.
4. Decode the `blay` preamble at body `0x0C`–`0x58` and cross-check against the section sizes it
   appears to duplicate.
5. Confirm whether the layout section is byte-identical between two tags of the same group and
   group version. If so, definitions can be extracted once per group rather than per tag.
6. Establish where the tag *data* begins relative to the layout section.

## Non-Goals

No game content is written to disk by `decode_body.py`; payloads are read into memory only.
Extracted tag data remains local and uncommitted per the repository policy.
