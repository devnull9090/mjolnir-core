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

### The `aux` word

**Verified** by histogramming every field of every group (`mjolnir aux`). `aux` is **zero for all
30-plus plain scalar types** — `real`, `long integer`, `string id`, `tag reference`,
`real point 3d`, and so on. It carries a payload only for the types whose type-table size is zero
or whose meaning needs a target:

| Type | `aux` means | Evidence |
|---|---|---|
| `pad` | Width in bytes. Observed values 1, 2, 3, 4, 6, 8, 12, 24, up to 60. | Verified |
| `struct` | Index into the struct table. | Verified |
| `array` | Index into the `arr!` array table. | Verified |
| `block` | Index into the `blv2` block table. | Verified |
| `*_enum`, `*_flags` | Index into the `sz[]` enum table. | Verified |
| `*_block_index` | Index into the `blv2` block table. | Observed |
| everything else | Unused, always zero. | Verified |

### `sz[]` enum table and `arr!` array table

Two more standard sections, previously seen empty because the sampled group used neither.

`sz[]` holds `{name_offset, option_count, first_option}`. `first_option` indexes the shared option
table, and the runs **tile it exactly**: each entry begins where the previous one ended. Worked
example from `ai_globals`:

```
scenario_structure_bsp_reference_flags_definition   4 options  from 0
object_type_enum_definition                        14 options  from 4
object_source_enum_definition                       6 options  from 18
ai_reference_frame_flags                            1 option   from 24
g_firing_position_flags                             9 options  from 25
```

`0 + 4 = 4`, `4 + 14 = 18`, `18 + 6 = 24`, `24 + 1 = 25`. The running sum holding across every
entry is what **Verifies** this reading.

`arr!` holds `{name_offset, count, struct_index}`. An array field's size is `count` times the size
of the referenced struct.

### Struct table ordering

**Verified.** `stv4` is ordered **root first**, while the terminator-delimited field runs are
emitted **innermost first**. The two are reverses of each other, so a struct-table index `i` maps
to field run `len - 1 - i`.

Reading the index directly produces false cycles. In `water_physics_drag_properties` the naive
reading makes `velocity to pressure` contain `drag` and `drag` contain `velocity to pressure`;
the reversed reading resolves to the real nesting, where `drag` holds the damping values and
`velocity to pressure` holds a curve. Applying the correction moved whole-corpus size resolution
from 96.6% to 98.5%.

## Validation

`mjolnir validate --all` checks the recovered model against every shipped tag.

| Check | Result |
|---|---|
| Container header parses | 12,290 / 12,290 |
| Layout section parses | 12,290 / 12,290 |
| Terminator count equals struct table size | 12,290 / 12,290 |
| Every field's type index in range | 12,290 / 12,290 |
| Every `block` field's `aux` indexes `blv2` | 12,290 / 12,290 |
| Every `struct` field's `aux` indexes a field run | 12,290 / 12,290 |
| Every `array` field resolves to an in-range struct | 12,290 / 12,290 |
| `bdat` data section present | 12,290 / 12,290 |
| Root struct size resolves | 12,111 / 12,290 (98.5%) |

**Open.** Five groups do not resolve a root size: `camera_shake`, `chud_globals_definition`,
`incident_globals_definition`, `shield_impact`, and `simulated_input`. Each hits the recursion
guard, which means the struct index correction above is not the whole story for them. They are
named here so the gap is reproducible rather than hidden.

## The `bdat` Data Payload

**Verified.** Fixed-width fields are packed inline in the element data. Fields whose content is
variable length instead emit a trailing section, one per field in declaration order:

```
block:
  u32   element count
  u32   flags, not yet interpreted
  ..    count * element_size bytes of packed element data
  ..    one `tgst` per element, holding that element's variable-length fields
```

The section magic identifies the field type:

| Magic | Field type |
|---|---|
| `tgbl` | `block` |
| `tgst` | `struct`, and the per-element wrapper |
| `tgsi` | `string id` |
| `tgda` | `data` |
| `tgrf` | `tag reference` |
| `tgal` | `array` |

Also seen but not yet attributed: `tgms`, `tgne`, `tgni`, all rare and concentrated in `scenario`.

The root is not special — the outermost `tgbl` is a block holding one element whose struct is the
group's root. A `struct` field whose target contains nothing variable length emits **no section at
all**, which the walk must anticipate.

Worked example, `camera_track` (304-byte payload), decomposing with nothing left over:

```
+0    u32 count = 1, u32 flags = 0
+8    12 bytes  root struct (one block field)
+20   tgst      element wrapper
+32     tgbl    control points: count = 9, flags = 1
+44       252 bytes  9 x 28-byte control points
```

### Coverage

`mjolnir validate --all` walks the payload and asserts it is consumed exactly.

| Result | Count |
|---|---|
| Walk succeeds | 1,953 / 12,290 (15.9%) |
| Of those, consumed **exactly** | 1,939 (99.3%) |
| Consumed short | 14 |
| Consumed over | 0 |

**The walk is strict by design.** It fails rather than stopping early, so a short read is never
mistaken for a complete one. An earlier tolerant version reported 82.5% success, but 7,361 of those
were silently short — that is a worse outcome than an honest partial result, and it was reverted.

Every group whose walk succeeds is byte-exact, which is strong evidence the model is correct as far
as it goes. The remaining failures are dominated by one symptom: a per-element `tgst` wrapper is
expected but the buffer has ended. Simple groups (`camera_track`, `color_table`, `camo`,
`collision_damage`, `breakable_surface`) all walk exactly; the failures are concentrated in groups
with multi-element blocks whose elements carry variable-length content, which is the one
combination not yet observed directly.

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

1. Find a block with more than one element whose element struct carries variable-length content,
   and confirm how the per-element `tgst` wrappers are laid out. This is the dominant remaining
   data-walk failure.
2. Attribute the `tgms`, `tgne`, and `tgni` data sections.
3. Resolve the five groups whose root size still hits the recursion guard:
   `camera_shake`, `chud_globals_definition`, `incident_globals_definition`, `shield_impact`,
   `simulated_input`.
4. Interpret the remaining empty layout sections: `csbn`, `dtnm`, `rcv2`, `]==[`.
5. Decode the `blay` preamble at body `0x0C`–`0x58` and cross-check against the section sizes it
   appears to duplicate.

## Published Reference

`mjolnir defs` writes the whole corpus to `defs/hce/tag-definitions.json`: 101 groups, 1,779
structs, 13,250 fields of which 11,216 are user-visible. The hub renders it as a searchable
reference at `/docs/tags`, one static page per group.

Only **schema** is published — field names, type names, byte offsets, and enum option names. Tag
**values** are game content and are never emitted, in line with the repository policy that keeps
`extract_tags.py` output local.
6. Establish where the tag *data* begins relative to the layout section.

## Non-Goals

No game content is written to disk by `decode_body.py`; payloads are read into memory only.
Extracted tag data remains local and uncommitted per the repository policy.
