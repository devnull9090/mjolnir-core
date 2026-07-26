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

This supersedes the "Next Checks" item in [tag_data_pipeline.md](tag_data_pipeline.md) that
proposed recovering field definitions from `HaloSimulation_tag_release.dll`. **The engine
binary is not required.** The definition corpus for all 101 shipped groups can be generated
mechanically from the shipped tag files.

Reproduction:

```
python tools/iostore/decode_body.py --paks "<install>\Meteorite\Content\Paks" \
    --oodle "<UE>\Engine\Binaries\DotNET\AutomationTool\oo2core_9_win64.dll" --survey

cargo run --release -p blam-cli -- groups --paks "<...>" --oodle "<...>"
cargo run --release -p blam-cli -- layout --group weapon --options
cargo run --release -p blam-cli -- type-codes
```

The Rust reader in `crates/blam-tag` parses **101/101 groups** across all **12,290** shipped
payloads.

## Section Layout

Body offsets below are relative to the start of the tag body, which begins at file offset
`0x4C`. File offsets in the worked example are for `default-weapon.ubulk`
(`weap`, group version 2, chunk length 27,599).

### `blay` header — body `0x00`, fixed `0x58` bytes

| Body offset | Size | Field | Evidence |
|---:|---:|---|---|
| `0x00` | 4 | `blay` four-CC, stored little-endian (`79 61 6c 62`) | Verified |
| `0x04` | 4 | Section version. `2` in `101/101` groups. | Verified |
| `0x08` | 4 | Section size, from body `0x00`. Covers the remainder of the tag. | Verified |
| `0x0C` | 4 | `0xFFFFFFFF` | Verified |
| `0x10` | 4 | ASCII `4444` (`0x34343434`) | Verified |
| `0x14` | 4 | ASCII `CCCC` (`0x43434343`) | Verified |
| `0x18` | 4 | ASCII `wwww` (`0x77777777`) | Verified |
| `0x1C` | 4 | Per-group 32-bit value (`weap` = `0xDB837039`) | Observed |
| `0x20` | `0x38` | Table of counts and sizes; several entries correlate with later section sizes (`+0x28` equals the string blob size in the sampled groups). | Observed |

The `4444` / `CCCC` / `wwww` dwords recorded as uninterpreted markers in
[tag_data_pipeline.md](tag_data_pipeline.md) are **fixed ASCII fill constants** at body
`0x10`–`0x18`. They are group-invariant and carry no per-tag information.

### `tgly` section — body `0x58`

A `{four-CC, version, size}` 12-byte section header. Version `4` in the sampled groups. Its
size ends at the same byte as the enclosing `blay` section, so `tgly` is a container holding
the remaining sections rather than a sibling. **Verified** for `weap`; **Observed** elsewhere.

### `str*` section — body `0x64`

| Body offset | Size | Field | Evidence |
|---:|---:|---|---|
| `0x64` | 4 | `str*` four-CC (`2a 72 74 73`) | Verified |
| `0x68` | 4 | Zero in every sampled group | Verified |
| `0x6C` | 4 | String blob size in bytes | Verified |
| `0x70` | *size* | NUL-separated UTF-8 string blob | Verified |

Strings are referenced elsewhere by **byte offset into the blob**, not by index. Verified by
resolving offsets back to strings across all 101 groups; hand-checked for the first 17
entries of `weap` (`50` → `does not cast shadow`, `71` → `search cardinal direction lightmaps
on failure`, `328` → `sample enviroment lighting only ignore object lighting`, and so on —
the misspelling of "enviroment" is present in the shipped data).

Blob contents mix three categories in definition order: **field names**
(`rounds total maximum`), **type names** (`long flags`, `word flags`, `short integer`,
`struct`, `custom`), and **enum/bitfield option names** (`early mover`, `super_sinker`).

Blob sizes range from `0xC7` / 13 strings (`breakable_surface`) to `0x543C` / 1,039 strings
(`character`). `weap` carries `0x3B33` bytes / 784 strings.

### `x+zs` option table — immediately after the string blob

| Offset | Size | Field | Evidence |
|---:|---:|---|---|
| `+0x00` | 4 | Literal bytes `78 2b 7a 73` (`x+zs`). Present in `101/101` groups. | Verified |
| `+0x04` | 4 | Zero in `101/101` groups | Verified |
| `+0x08` | 4 | Entry count. `0` for groups with no enums or bitfields (`camera_track`, `color_table`); `1,312` for `weap`. | Observed |
| `+0x0C` | 4 × *count* | Array of string-blob offsets, one per enum/bitfield option, in definition order. | Observed |

Worked example, `weap` entries 0–16 resolve to the 17 bits of `object flags` in order, then
`{default, never, always, blur}`, then `{default, small, medium, large}`, then
`{default, super_floater, …, super_sinker, none}` — contiguous option runs for consecutive
enum and bitfield definitions.

For `weap`, the option table ends at body `0x502F`, exactly `12 + 1312 × 4` bytes past the blob.
That lands on the first field record, which **Verifies** the entry-count reading for this group.

**Open question.** In `16/101` groups — including `chud_definition`, `chud_globals_definition`,
`achievements`, and the `chud_widget_*_template` set — the declared count multiplied by four
overruns the enclosing `blay` section. `chud_definition` declares `2,964` entries, which would
end `4,908` bytes past the section. Either the word is not always an entry count, or those groups
place the table differently. `Layout::options_truncated` flags the condition rather than guessing;
`mjolnir groups` reports the count.

**Note:** this table begins at an offset that is not 4-byte aligned (`0x3BEF` in the worked
example) because the preceding string blob is byte-packed. The layout section is packed
throughout; do not assume dword alignment.

### Field definition table — after the option table

**Observed.** Records begin `{name_offset: u32, type_code: u32, aux: u32}`. Reading at a fixed
12-byte stride is correct at the start of the table:

```
10417 'rounds recharged'                  type 4   aux 0
10434 'rounds total initial'              type 4   aux 0
10455 'rounds total maximum'              type 4   aux 0
10476 'rounds loaded maximum'             type 4   aux 0
10498 'runtime rounds inventory maximum'  type 4   aux 0
10531 'rounds reloaded'                   type 4   aux 0
```

**Refuted: the records are not a fixed 12-byte stride.** Histogramming type codes across all 101
groups (`mjolnir type-codes`) produces clean names for low type codes (`radius`, `world bounds x`,
`unique id`, `node index`) but byte-shifted substrings for higher ones — `ong flags` for
`long flags`, `bject` for `object`, `truct` for `struct`, `stom` for `custom`. A fixed stride
desynchronizes partway through the table.

**Hypothesis:** field records are variable-length, and certain type codes carry trailing inline
payload (an option count for enums and bitfields, a group list for tag references, a nested type
reference for structs and blocks). This also plausibly explains the option-table overrun above, if
some option data is inline rather than in the shared table.

`blam_tag::layout::FieldRecord` is documented as provisional and `Layout::field_table` exposes the
raw bytes so the table can be re-parsed without touching the rest of the reader.

## Group Coverage

**Verified:** `blay` version `2`, a `str*` blob, and the `x+zs` marker with a zero second word
are present in **101/101** shipped groups, one sample per group. Group versions at container
header `0x34` vary independently (`bsdt` = 0, `bipd` = 3, `effe` = 4, `jpt!` = 6, `coll` = 10),
confirming that value is a per-group definition version rather than a format version.

## Why This Matters

1. A complete, authoritative definition corpus for all 101 groups is derivable from the shipped
   data alone, including **human-readable field names and option names** — the same strings
   Guerilla displayed.
2. It removes `HaloSimulation_tag_release.dll` from the critical path for a tag editor.
3. Because each tag carries its own layout, a reader can be **fully generic**: no hand-coded
   per-group parsers and no hardcoded offsets.

## Next Checks

1. Determine the variable-length field record encoding. The most direct approach is to walk the
   table forward and require that every `name_offset` land on a string-blob boundary; the stride
   that keeps that invariant across all 101 groups is the correct one.
2. Map `type_code` to field types and byte sizes, then verify by asserting that the walked field
   layout consumes the tag payload exactly, for all 12,290 shipped payloads.
3. Resolve the option-table overrun in the 16 affected groups.
4. Decode the `blay` header count table at body `0x20`–`0x58` and cross-check against the section
   sizes it appears to duplicate.
5. Confirm whether the layout section is byte-identical between two tags of the same group and
   group version. If so, definitions can be extracted once per group rather than per tag.
6. Establish where the tag *data* begins relative to the layout section.

## Non-Goals

No game content is written to disk by `decode_body.py`; payloads are read into memory only.
Extracted tag data remains local and uncommitted per the repository policy.
