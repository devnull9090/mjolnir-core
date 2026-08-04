# Blam Script (HSC) in Halo Campaign Evolved

**Build:** `2026.06.26.1097863.1-Rel-i343-Meteorite-2606-CU2` (Steam)
**Crates:** `crates/blam-hsc`, exposed through `mjolnir script` and `mjolnir scripting`
**Artifacts:** `defs/hce/scripting.json`
**Date:** 2026-08-03

## Summary

Halo Campaign Evolved's missions are scripted in HSC, the same S-expression language
Bungie shipped from *Halo: Combat Evolved* onward, and it lives in the `scenario` tag.
Two findings make it unusually tractable:

1. **The original `.hsc` source ships verbatim**, comments and all. `a30` alone carries
   nine source files totalling 231 KB, the largest 4,449 lines. Nothing had to be
   recovered to read the campaign's scripting — it is sitting in the tag.
2. **The compiled expression tree ships too**, so the two can be checked against each
   other. Across the thirteen campaign scenarios: **215,775 live expression nodes,
   6,827 scripts, 1,801 globals**.

The opcode table is Halo Campaign Evolved's own — of the 483 opcodes the campaign
calls, 24 agree with Halo Reach's table and 7 with Halo 4's — but it did **not** need
reverse-engineering out of `HaloSimulation_tag_release.dll`, for the same reason the
tag definitions did not: the data describes itself. See
[tag_body_format.md](tag_body_format.md).

Reproduction:

```
$env:HCE_PAKS = "<install>\Meteorite\Content\Paks"

cargo run --release -p blam-cli -- script --tag a30 --declarations
cargo run --release -p blam-cli -- script --tag a30 --source a30
cargo run --release -p blam-cli -- script --tag a15 --decompile f_md_3d_play
cargo run --release -p blam-cli -- script --verify
cargo run --release -p blam-cli -- scripting --build "<build string>"
```

## Where it lives

Seven fields of `scenario_block_struct`, all in one run at `0x3c8`:

| Offset | Field | Block | Holds |
|---:|---|---|---|
| `0x3c8` | `scripts` | `hs_scripts_block` (max 2048) | name, type, return type, root expression |
| `0x3d4` | `globals` | `hs_globals_block` (max 512) | name, type, initializer expression |
| `0x3e0` | `references` | `hs_references_block` (max 512) | tags the scripts pull in |
| `0x3ec` | `source files` | `hs_source_files_block` (max 16) | **the original `.hsc` text** |
| `0x3f8` | `scripting data` | `cs_script_data_block` | AI point sets |
| `0x450` | `hs unit seats` | `hs_unit_seat_block` | seat mappings |
| `0x498` | `hs syntax datums` | `hs_syntax_datum_block` (max 64512) | the compiled tree |

Plus `script string data`, a `data` field holding the string blob every node's
`string_offset` points into (35–68 KB per scenario).

## The expression datum

`hs syntax datums` is a Blam **datum array**, not a list: nodes address each other by
handle, and freed slots stay in place. 24 bytes each:

| Offset | Size | Field | Notes |
|---:|---:|---|---|
| `0x00` | 2 | salt | Pairs with the array index to form this node's handle |
| `0x02` | 2 | opcode | Engine function, script index, or global index |
| `0x04` | 2 | value type | Indexes the scenario's own value-type enum |
| `0x06` | 2 | expression type | See below |
| `0x08` | 4 | next | Handle of the next sibling |
| `0x0c` | 4 | string offset | Into `script string data` |
| `0x10` | 4 | data | First child for a call; the literal payload otherwise |
| `0x14` | 2 | line number | 1-based, in the source file it came from |
| `0x16` | 2 | — | The definitions call it `HMM`; zero in every shipped datum |

A **handle** is `index` in the low half and `salt` in the high half; `0xFFFFFFFF` is
null. Comparing the salt against the target's own is what makes a stale handle
detectable rather than silently resolving to whatever later took the slot.

A **free slot** reads as `0xBA` fill with a zeroed salt. 56,415 of the campaign's
272,190 slots are free; walking the array without checking would decode garbage.

**Expression types** use the Reach-era numbering, even though the opcodes do not:

| Value | Meaning |
|---:|---|
| 8 | Group — a call. `data` points at the child that names the callee |
| 9 | Expression — a leaf: either that name, or a literal |
| 10 | Script reference — a call to a script in this scenario; `opcode` indexes `scripts` |
| 13 | Globals reference — `opcode` indexes `globals` |
| 29 | Parameter reference |

## Recovering the opcode table

A call node points at a child whose `string_offset` names the callee. Reading that for
every `Group` node across all thirteen scenarios yields **483 opcodes with no
disagreement** — no opcode ever resolved to two different names, which is the check
that the rule is right (`mjolnir scripting` fails rather than exporting if it ever
does).

`defs/hce/scripting.json` records, per opcode: the name, observed return types, argument
count range, per-position argument types, and the call-site and scenario counts behind
each. **Signatures are inferred from use, not read from the engine**: a function the
campaign never calls is absent, and 46 of the 483 rest on a single call site. The file
carries those counts so a consumer can tell the difference.

Two things the tree does not preserve:

- **`cond` does not survive compilation.** It is desugared to nested `if` before any
  node is emitted, so no opcode exists for it even though the source files use it
  freely. 205 scripts decompile to `if` where the source said `cond`.
- **Special forms are not marked.** The value-type enum has a `special_form` entry, but
  no node in any of the 272,190 shipped datums carries it.

### Quoting

Whether a literal is written `"like this"` or bare is not recorded anywhere in the tag —
a `damage` literal and an `ai` literal are both just a string offset. It is recovered by
asking how the source that produced the tree wrote each string, with two corrections
that matter:

- A string the source writes **both** ways is evidence for neither. `easy` is a bare
  `game_difficulty` in `(= (game_difficulty_get_real) easy)` and a quoted `string` in
  `(print "easy")` a few tokens away; counting it for both made each type look like the
  other and inverted the result.
- Quoting is partly a property of the **argument position**, not just the type. A
  `string_id` is quoted as the marker name in `(object_at_marker x "primary_weapon")`
  and bare in plenty of other places, so a position with its own evidence overrules the
  type-level rule.

## How well the decompiler does

`mjolnir script --verify` decompiles all 6,827 campaign scripts and compares each
against the source the same scenario carries, as token streams — comments cannot come
back, and the compiler coerces `-1` to `-1.0` and accepts `0` for `false`.

| Outcome | Scripts |
|---|---:|
| Token-for-token match | 6,241 (91.4%) |
| Differ only because the source used `cond` | 205 |
| No source block to compare against | 150 |
| Genuinely differ | 231 |

Of the 231, **186 are a quoting disagreement** and 45 are unexplained. That residue is
worth closing before anyone relies on decompiled output for a scenario whose source was
stripped; it does not affect reading a shipped scenario, where the original source is
right there in the tag.

## In the tag editor

A `scenario` tag gets a third view alongside Form and Tree. It shows the shipped source
files with HSC highlighting, an outline of every script and global that jumps to its
declaration, and export to `.hsc`. When a scenario carries no source — a stripped or
hand-built mod — it shows decompiled output instead and says so.

## Not done yet

**Compiling edited script back into a scenario.** The game runs the expression tree, not
the text, so changing a script means rebuilding the tree, the string blob, and the
`scripts`/`globals` blocks. `crates/blam-hsc` has the reader, the lexer and the corpus a
compiler needs, but the compiler itself is not written, and the editor's script view is
therefore read-only. The acceptance test for it already has an obvious shape: recompile
each shipped source file and compare against the shipped tree.
