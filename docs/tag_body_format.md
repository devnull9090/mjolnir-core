# Blam Tag Body Format (`blay` Layout Section)

**Build:** `2026.06.26.1097863.1-Rel-i343-Meteorite-2606-CU2` (Steam)
**Artifacts:** `Meteorite/Content/Paks/*.utoc` + `*.ucas`, 28 containers
**Tool:** `crates/blam-cli` (`mjolnir`)
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
cargo run --release -p blam-cli -- sections               # tgly tables + blay preamble
cargo run --release -p blam-cli -- data --group weapon --trace
cargo run --release -p blam-cli -- validate --all
cargo run --release -p blam-cli -- roundtrip --all        # re-serialise and compare
cargo run --release -p blam-cli -- data-versions          # bdat section version words
cargo run --release -p blam-cli -- values --group weapon  # fields with decoded values
cargo run --release -p blam-cli -- recode --all           # decode/encode identity
```

The Rust reader in `crates/blam-tag` parses **101/101 groups** across all **12,290** shipped
payloads, recovers a complete field list for **101/101**, and decodes the field *values* of
**12,281 / 12,290** payloads byte for byte. Every one of those decodes back to its original
bytes exactly, which is the precondition for editing tags rather than only reading them.

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
| `0x20` | 8 | Two words with no candidate that holds across all 101 groups. | Observed |
| `0x28` | `0x30` | Record count for each `tgly` child table, in a fixed order. | Verified |
| `0x58` | — | First child section (`tgly`). | Verified |

The `4444` / `CCCC` / `wwww` dwords recorded as uninterpreted markers in
[tag_data_pipeline.md](tag_data_pipeline.md) are **fixed ASCII fill constants** at body
`0x10`–`0x18`. They are group-invariant and carry no per-tag information.

#### The preamble count table — body `0x28`–`0x58`

**Verified.** The twelve words from body `0x28` are a manifest: one record count per `tgly`
child table, in a fixed order. Each was identified by testing every word against every
candidate derived from the parsed tables and keeping only candidates that hold in **all 101
groups**; each of the twelve has exactly one such candidate.

| Body offset | Counts | Record width |
|---:|---|---:|
| `0x28` | `str*` string blob | 1 (a byte count, not a record count) |
| `0x2C` | `sz+x` enum and bitfield options | 4 |
| `0x30` | `sz[]` enum and bitfield definitions | 12 |
| `0x34` | `csbn` | 4 |
| `0x38` | `dtnm` | 4 |
| `0x3C` | `arr!` arrays | 12 |
| `0x40` | `tgft` types | 12 |
| `0x44` | `gras` fields | 12 |
| `0x48` | `stv4` structs | 28 |
| `0x4C` | `blv2` blocks | 12 |
| `0x50` | `rcv2` | 12 |
| `0x54` | `]==[` | 24 |

`mjolnir validate --all` cross-checks every count against the section it counts:
**12,290 / 12,290** tags agree on all twelve. That turns the preamble from an opaque blob into
a checkable manifest, and it is what pins the record widths of `csbn`, `dtnm`, `rcv2` and
`]==[` — tables that are empty in most groups, so their widths cannot be read off their own
contents. Reproduce with `mjolnir sections`.

The two words at body `0x20`–`0x28` remain unidentified. No count, byte size, or size-over-width
quotient from any table matches them across all 101 groups.

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

### `sz+x` option table — immediately after the string blob

A standard section holding an array of string-blob offsets, one per enum or bitfield option, in
declaration order. **Verified.**

Worked example, `weap` entries 0–16 resolve to the 17 bits of `object flags` in order, then
`{default, never, always, blur}`, then `{default, small, medium, large}`, then
`{default, super_floater, …, super_sinker, none}` — contiguous option runs for consecutive
enum and bitfield definitions.

**Superseded 2026-07-26.** An earlier revision read the section's `size` word as an *entry
count* and reported that the count overran the enclosing section in 16 of 101 groups. That was a
misreading: the word is the section size **in bytes**, consistent with every other section.
`weap` declares `1,312` bytes, which is `328` options, not `1,312`.

**Superseded 2026-07-26.** A later revision said the magic varies between groups and located the
section positionally. It does not vary: the magic is `sz+x` in **101/101** groups, and the
`tgly` child chain is in the same fixed order everywhere (see below). The reader now finds it by
name and keeps the positional lookup only as a fallback.

### Definition tables

Sibling sections under `tgly`, all using the standard 12-byte header. Empty tables are present
with `size = 0` rather than omitted. **Verified** across all 101 groups, which all carry the
same twelve children in the same order:

```text
str*  sz+x  sz[]  csbn  dtnm  arr!  tgft  gras  blv2  rcv2  ]==[  stv4
```

| Magic | Record | Meaning |
|---|---|---|
| `tgft` | `{name_offset, size, flags}` | Type table. `size` is the on-disk width in bytes; `flags` is non-zero for composite types such as `block`. |
| `gras` | `{name_offset, type_index, aux}` | Field list. `type_index` indexes `tgft`. |
| `blv2` | `{name_offset, max_count, aux}` | Block table. `max_count` is the element limit Guerilla enforced; `aux` is a `stv4` index. |
| `stv4` | `{guid[16], name_offset, first_field, aux}` | Struct table. `first_field` is a `gras` index; see below. |

**Superseded 2026-07-26.** An earlier revision listed `sz[]`, `csbn`, `dtnm`, `arr!`, `rcv2` and
`]==[` as "present, empty in the sampled groups". All twelve tables are present in **101/101**
groups, and four of the six do carry content somewhere:

| Magic | Groups where non-empty | Largest | Record width |
|---|---:|---:|---:|
| `sz[]` | 79 / 101 | 1,476 B | 12 |
| `arr!` | 12 / 101 | 132 B | 12 |
| `dtnm` | 41 / 101 | 16 B | 4 |
| `csbn` | 9 / 101 | 60 B | 4 |
| `rcv2` | 3 / 101 | 36 B | 12 |
| `]==[` | 2 / 101 | 72 B | 24 |

`sz[]` and `arr!` are decoded below. `csbn`, `dtnm`, `rcv2` and `]==[` still have no
interpretation, but their record widths are now known from the preamble manifest, and the groups
that carry content are named here so the next attempt has somewhere to start.

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
| `pageable resource` | Unused, always zero; the resource is a section in `bdat`. | Verified |
| `struct` | Index into the struct table. | Verified |
| `array` | Index into the `arr!` array table. | Verified |
| `block` | Index into the `blv2` block table. | Verified |
| `*_enum`, `*_flags` | Index into the `sz[]` enum table. | Verified |
| `*_block_index` | Index into the `blv2` block table. | Verified |
| everything else | Unused, always zero. | Verified |

### `sz[]` enum table and `arr!` array table

Two more standard sections. Both are present in all 101 groups; `sz[]` carries content in 79 of
them and `arr!` in 12.

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

### Struct-to-field-run mapping

**Verified.** `stv4`'s record is `{guid[16], name_offset, first_field, aux}`. `first_field` is
the index of the struct's first entry in the `gras` field list, which is exactly the start of
its terminator-delimited run. The struct-to-fields link is therefore a **lookup, not an
inference**.

`mjolnir validate --all` checks that every `stv4` entry's `first_field` lands on a run start:
**12,290 / 12,290** tags pass, across every group.

**Superseded 2026-07-26.** An earlier revision did not read `first_field` and instead inferred
the mapping, on the theory that `stv4` was ordered root first while the field runs were emitted
innermost first, making the two exact reverses. That holds only for groups whose structs happen
to be declared in nesting order. `shield_impact` is the counterexample: its real run starts are
`{14, 4, 0, 9}`, which the reversal maps to `{3, 2, 1, 0}` — correct for the root and wrong for
the other three. The false cycles that produced are what drove those groups into the recursion
guard.

Reading `first_field` directly fixes both symptoms at once:

| Measure | Reversal | `first_field` |
|---|---:|---:|
| Root struct size resolves | 12,111 / 12,290 (98.5%) | **12,290 / 12,290 (100%)** |
| Data walk succeeds | 1,953 / 12,290 (15.9%) | **12,281 / 12,290 (99.9%)** |

The five groups previously listed as unresolved — `camera_shake`, `chud_globals_definition`,
`incident_globals_definition`, `shield_impact` and `simulated_input` — all resolve. They were not
five separate anomalies; they were the groups where the ordering assumption broke.

## Validation

`mjolnir validate --all` checks the recovered model against every shipped tag.

| Check | Result |
|---|---|
| Container header parses | 12,290 / 12,290 |
| Layout section parses | 12,290 / 12,290 |
| Terminator count equals struct table size | 12,290 / 12,290 |
| `blay` preamble counts match their tables | 12,290 / 12,290 |
| Every `stv4` `first_field` lands on a run start | 12,290 / 12,290 |
| Every field's type index in range | 12,290 / 12,290 |
| Every `block` field's `aux` indexes `blv2` | 12,290 / 12,290 |
| Every `*_block_index` field's `aux` indexes `blv2` | 12,290 / 12,290 |
| Every `struct` field's `aux` resolves to a field run | 12,290 / 12,290 |
| Every `array` field resolves to an in-range struct | 12,290 / 12,290 |
| `bdat` data section present | 12,290 / 12,290 |
| Root struct size resolves | 12,290 / 12,290 |

## The `bdat` Data Payload

**Verified.** Fixed-width fields are packed inline in the element data. Fields whose content is
variable length instead write a trailing section, in declaration order:

```
block:
  u32   element count
  u32   flags, not yet interpreted
  ..    count * element_size bytes of packed element data
  ..    one `tgst` per element, holding that element's variable-length fields
```

The root is not special — the outermost `tgbl` is a block holding one element whose struct is the
group's root.

### What each field type writes

**Verified** against every shipped tag: with these rules the walk consumes **12,281 / 12,290**
payloads byte for byte, and the 9 that fail all fail on one field slot (see *Open* below).

| Field type | Writes |
|---|---|
| `block` | `tgbl`: `{count, flags}`, the packed elements, then one `tgst` per element |
| `struct` | `tgst`, **always** |
| `string id` | `tgsi` |
| `data` | `tgda` |
| `tag reference` | `tgrf` |
| `pageable resource` | a section whose magic reads `tg?c` |
| `array` | nothing of its own; its elements' sections follow inline |
| everything else | nothing; the value is inline in the packed element data |

A block writes its per-element `tgst` wrappers when its own header `flags` word is `0`; see
**The block `flags` word** below. `camera_track`'s 9 control points are flagged `1`, so that
block carries no wrappers at all.

Four of these rules replace earlier readings, and each was forced by a specific failure.

**A `struct` always writes its `tgst`.** The previous revision said a struct whose target has no
variable-length content "emits no section at all". It does write one — empty. `structure_seams`
is the clean case: its `structure_manifest_struct` run declares two `struct` fields that target a
run of six `long integer`s, and the file writes two empty `tgst` before the next field's `tgbl`.
Applying this rule alone moved the per-group walk from 81/101 to 93/101, and made every success
byte-exact.

**An `array` writes no wrapper.** `tgal` appears in the earlier revision's magic table but is
**never used**: no array in the shipped corpus writes a section of its own. An array is an inline
repetition — its fixed-width part is already inside the packed element data, counted by
`field_size` as `count × element_size` — and when its element struct has variable-length content,
each element's sections simply follow back to back. `game_engine_settings_definition` is the
worked case: its 8-element `teams` array writes 8 bare `tgsi`, with no `tgal` and no per-element
`tgst`. An array whose element struct writes nothing does not appear in the stream at all.

**A `pageable resource` writes a section.** The earlier revision treated it as an 8-byte inline
value only. It also writes a 12-byte section whose magic reads `tg?c`, where the third character
is `r` when a resource is attached and NUL when it is not. That NUL is why it went unnoticed: a
four-CC scan that requires printable characters skips it, and the generic section reader rejects
it. Only three groups declare the type — `model_animation_graph`, `scenario_structure_bsp` and
`shader` — and `shader` is the tightest evidence: its `render_method_postprocess_block` element
came up **exactly 12 bytes** short until this section was read.

**A `tgst` of declared size zero has no children**, even when its struct declares fields that
would write. The section header is the authority on what is present; the shipped scenario tags
use an empty `tgst` for a struct left at its defaults.

### The block `flags` word

**Verified.** The second word of a `tgbl` header decides whether per-element `tgst` wrappers
follow the packed element data: `0` means one wrapper per element, `1` means none.

It is **not** derivable from the definition. A block whose element struct declares nothing
variable length still writes one *empty* `tgst` per element when `flags` is `0`. Two shipped
cases pin this down: `chud_globals_definition`'s `curvature infos` writes 5 empty wrappers, and
`scenario_structure_bsp`'s `super node mappings` writes 2,048 of them — 24,576 bytes of pure
structure that the element field list gives no hint of.

An earlier revision decided wrappers from the element struct's field list instead. That reads
those two blocks 60 and 24,576 bytes short, and — because a parent advances by a child's
*declared* size — the shortfall was invisible until the round-trip below compared bytes.

### Re-serialising: the writer

**Verified.** `crates/blam-tag/src/write.rs` turns a decoded value tree back into `bdat` bytes.
`mjolnir roundtrip --all` reads every shipped tag, writes the tree back out, and requires the
result to be identical:

| Result | Count |
|---|---:|
| Re-serialised **byte for byte** | **12,281 / 12,281** |
| Differs | 0 |
| Bytes reproduced | 5,767,589,556 |

The nine tags absent from that total are the `effect scenery` cases that do not read; a tag that
cannot be read is not offered to the writer.

This identity is the precondition for editing. A writer that cannot reproduce an untouched tag
cannot be trusted with a modified one, and the failure mode is silent corruption of somebody's
game install.

Section header words are **not** stored in the value tree, because they are all reconstructable.
Measured over every section the walk reads:

| Magic | Version word | Sections measured |
|---|---|---:|
| `tgbl` | always `0` | 66,002 |
| `tgst` | always equals its own content size | 66,604 |
| `tgsi` | always `0` | 22,384 |
| `tgrf` | always `0` | 23,950 |
| `tgda` | always `0` | 125 |

So a `tgst`'s second word is not a version at all — it duplicates the size. Reproduce with
`mjolnir data-versions`.

The round-trip earned its place immediately: it was what exposed the `flags` rule above. The
reader reported those two blocks as fully consumed, every structural invariant passed, and only
comparing regenerated bytes against the original showed 26,232 bytes unaccounted for.

### Writing a field value back

**Verified.** `blam-tag::value` decodes a field's fixed-width bytes by type name, and encodes a
value back the same way. The two are inverses, and that is checked over the shipped corpus rather
than asserted: `mjolnir recode --all` decodes every fixed-width field of every tag and immediately
writes the same value back, requiring the bytes to be unchanged.

That property is what editing rests on. Saving a tag re-encodes *every* field, not only the one
the user touched, so any type whose decode and encode disagree would quietly corrupt fields nobody
edited. A per-type unit test cannot establish it — only the real corpus contains the values the
shipped data actually uses.

The check found two such disagreements, neither of which a hand-written test would have contained,
because both depend on values only the shipped data happens to hold.

**Fixed-width strings.** A string decodes as the bytes up to its first NUL, and the encoder was
clearing the rest of the field. But **80 `long string` fields carry non-zero bytes past their
terminator** — remnants of longer values written earlier — so clearing the tail rewrote bytes
nobody had asked to change. The encoder now writes the text, terminates it, and leaves the
remainder alone, which is both what the shipping tools did and what makes write-back an identity.

**Block indices.** `-1` is the conventional "unset" sentinel, so the decoder collapsed every
negative index to "none" and the encoder wrote `-1` back. **108 `custom short block index` fields
hold a negative value that is not `-1`**, and every one of them was being silently rewritten. The
decode now keeps the raw index and only the *display* treats negatives as unset, which also means
an unusual sentinel is shown rather than hidden.

The encoder is deliberately strict, because its output goes into somebody's game data:

- A value out of range is **refused, not truncated**, and nothing is written.
- A vector of the wrong arity is refused rather than padded.
- A value of the wrong kind for the field is refused.
- A `#rrggbb` colour leaves the alpha byte alone, because it says nothing about alpha.
- Section-backed types — `string id`, `data`, `tag reference` — are refused outright. Changing one
  resizes the tag rather than overwriting bytes in place, so it is a different operation and is not
  smuggled in through this path.

| Check | Result |
|---|---:|
| Tags walked | 12,281 |
| Fixed-width fields decoded and re-encoded | 1,672,489,373 |
| Unchanged | **1,672,489,373 (100%)** |
| Changed | **0** |
| Refused as not editable in place | 654,273 |

The traversal that does this allocates nothing. Building the value tree for every tag instead cost
**29 GB** on `scenario_structure_bsp` alone, which is also why the tree an editor renders is
bounded — see below.

### Bounding the value tree

A tag's value tree is not safe to materialise in full. `scenario_structure_bsp` carries millions
of elements; building a node for each cost tens of gigabytes and hung the process. The tree an
interface renders is therefore capped, both per block and in total nodes, and each block node
carries the count it really has so a partial list is labelled rather than mistaken for the whole.

Checks that genuinely need every element walk without building anything.

### Reading a nested section strictly

**Verified.** Consuming the outermost payload exactly is *not* sufficient. A parent advances over
a child by the child's declared size, so bytes left unread **inside** a nested `tgst` are
invisible to a whole-payload byte count. The walk therefore asserts that every nested `tgst`
**and** `tgbl` is consumed exactly, not just the root.

Adding that check for `tgst` is what exposed the `pageable resource` section: before it,
`shader` and `model_animation_graph` both "passed" while silently skipping 12 bytes inside a
nested wrapper. Extending it to `tgbl` exposed the `flags` rule.

### The `tgms`, `tgne` and `tgni` magics

**Resolved: they are not sections.** The earlier revision listed them as seen but unattributed,
found by scanning payloads for `tg`-prefixed four-CCs. Since the walk now consumes 12,281
payloads byte for byte without ever reading one, every occurrence necessarily falls inside a
region the walk treats as opaque — packed element data, or the content of a `tgda`, `tgsi` or
`tgrf`. They are incidental byte patterns, not structure. The same argument disposes of the
`tgal` occurrences in `scenario`.

### Worked example

`camera_track` (304-byte payload), decomposing with nothing left over:

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
| Walk succeeds | **12,281 / 12,290 (99.9%)** |
| Of those, consumed **exactly** | 12,281 (100%) |
| Consumed short | 0 |
| Consumed over | 0 |

Previous revision, for comparison: 1,953 walks succeeded (15.9%), of which 14 were short.

**The walk is strict by design.** It fails rather than stopping early, so a short read is never
mistaken for a complete one. An earlier tolerant version reported 82.5% success, but 7,361 of those
were silently short — that is a worse outcome than an honest partial result, and it was reverted.
A second tolerance, ending a struct run once its section's content was spent, was tried during
this revision and then removed: with the rules above correct it never fired on any of the 12,290
tags, so it could only ever have masked a real gap.

Failures name the field path rather than a buffer offset, which is what makes a new one
diagnosable:

```
root.[0].render geometry.compression info constant buffers:
  expected a tgbl section at offset 134436 of 134468, found "<none>" [63 00 67 74 ...]
```

**Open — one field slot, 9 tags.** Every remaining failure is the same one:
`root.[0].effect scenery.[0]` in 9 of the 13 `scenario` tags, which reads 104 of the 164 bytes the
element's `tgst` declares. The evidence is narrow and specific:

- `scenario_effect_scenery_block` declares `custom, short block index, custom,
  short block index, struct object data, custom, struct multiplayer data`.
- The sibling `scenario_scenery_block` declares the same shape but with a fourth `struct`,
  `permutation data`, exactly where effect scenery has its third `custom`. It walks byte-exact.
- The file writes three sections for an effect scenery element: `object data` (80 bytes), an
  **empty `tgst`**, then `multiplayer data` (48 bytes). The empty one sits precisely in the slot
  where the sibling block has `permutation data`.

So that third `custom` occupies a struct slot and is written as an empty `tgst`, while `custom`
elsewhere is a Guerilla editor annotation that writes nothing. Three candidate discriminators
were tested against the whole corpus; all three made matters worse, so none is recorded here as
the rule:

| Rule tried | Per-group walk |
|---|---:|
| No `custom` ever writes (current) | 100 / 101 |
| `custom` writes when the next field writes | 46 / 101 |
| `custom` writes when the next field is a `struct` | 77 / 101 |
| `custom` writes when it sits between two `struct` fields | 92 / 101 |

The discriminator is therefore not the neighbouring field types. The next thing to check is
whether the three `custom` entries differ within their own `gras` record: all three resolve to
the empty string, but their `name_offset` values point at different NULs in the string blob and
have not been compared.

## Group Coverage

**Verified:** all 101 shipped groups parse end to end — `blay` version `2`, a `str*` blob, an
option table, a `tgft` type table, a `gras` field list, and a `bdat` data section. All twelve
`tgly` child tables are present in every group, in the same order. `weap` carries 783 strings,
328 options, 30 types, 503 fields, 30 blocks, and 46 structs.

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
4. Values, not just schema, are now readable: 99.9% of shipped payloads decode into a byte-exact
   value tree, which is what an editor needs in order to show a field's current setting.
5. Those trees re-serialise to identical bytes, so an editor can write a tag back having changed
   only what the user changed. Without that identity, saving is corruption.

## Next Checks

1. Identify what distinguishes the `custom` field that occupies a struct slot in
   `scenario_effect_scenery_block` from the `custom` fields that write nothing. Start by comparing
   the three entries' `gras` records directly, including their distinct `name_offset` values. This
   is the only remaining data-walk failure, at 9 of 12,290 tags.
2. Interpret `csbn`, `dtnm`, `rcv2` and `]==[`. Their record widths are now known (4, 4, 12 and 24
   bytes) and the groups that populate them are named above, which is where to look.
3. Identify the two `blay` preamble words at body `0x20`–`0x28`, and the per-group value at
   `0x1C`.
4. Confirm what the third character of the `pageable resource` magic (`tg?c`) selects. Only `r`
   and NUL have been seen, in three groups.
5. Package a modified tag so the game loads it. Tags live inside read-only UE5 IoStore
   containers, so writing one back means emitting an override container or loose package, which
   `ue-iostore` cannot yet do. This, not the tag format, is now what stands between an edit and
   seeing it in game.
6. Test the container-header `0x34` group-version hypothesis against a known Reach or Halo 4 tag
   definition set.

## Published Reference

`mjolnir defs` writes the whole corpus to `defs/hce/tag-definitions.json`: 101 groups, 1,779
structs, 13,250 fields of which 11,216 are user-visible, with a root size resolved for 101/101
groups. The hub renders it as a searchable reference at `/docs/tags`, one static page per group.

Only **schema** is published — field names, type names, byte offsets, and enum option names. Tag
**values** are game content and are never emitted, in line with the repository policy that keeps
`extract_tags.py` output local.

## Non-Goals

No game content is written to disk by any of these tools; payloads are read into memory only.
Extracted tag data remains local and uncommitted per the repository policy.
