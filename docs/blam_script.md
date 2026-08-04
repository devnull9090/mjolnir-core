# Blam Script (HSC) in Halo Campaign Evolved

**Build:** `2026.06.26.1097863.1-Rel-i343-Meteorite-2606-CU2` (Steam)
**Crates:** `crates/blam-hsc`, exposed through `mjolnir script`, `mjolnir scripting` and `mjolnir compile`
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
cargo run --release -p blam-cli -- script --recompile
cargo run --release -p blam-cli -- scripting --build "<build string>"

# No game installation needed; reads the committed corpus.
cargo run --release -p blam-cli -- compile my_mod.hsc --show
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
| `0x00` | 2 | generation | Pairs with the array index to form this node's handle |
| `0x02` | 2 | opcode | Engine function, script index, or global index |
| `0x04` | 2 | value type | Indexes the scenario's own value-type enum |
| `0x06` | 2 | expression type | See below |
| `0x08` | 4 | next | Handle of the next sibling |
| `0x0c` | 4 | string offset | Into `script string data` |
| `0x10` | 4 | data | First child for a call; the literal payload otherwise |
| `0x14` | 2 | line number | 1-based, in the source file it came from |
| `0x16` | 2 | — | The definitions call it `HMM`; zero in every shipped datum |

A **handle** is `index` in the low half and a **generation** counter in the high half;
`0xFFFFFFFF` is null. Comparing the generation against the target's own is what makes a
stale handle detectable rather than silently resolving to whatever later took the slot.

Blam tooling calls this half-word the datum's *salt*, and the shipped definitions call
its field `datum header`. `crates/blam-hsc` calls it `generation`, because that is what
it does: an ABA counter for a slab allocator, nothing to do with cryptography.

A **free slot** reads as `0xBA` fill with a zeroed generation. 56,415 of the campaign's
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

## Syntax worth knowing

Three things bit the lexer, all confirmed against the shipped source:

- **`;*` … `*;` is a block comment.** `global_scripts` uses them, and reading one as a
  line comment leaves the rest of the block as stray top-level tokens — and made `a30`
  look like it had an unbalanced paren at line 2030 when it does not.
- **A `;` inside a string is text**, not a comment. The dialogue lines are full of them.
- **A backslash in a tag path is a literal character**, not an escape:
  `"objects\characters\marine"` is a path, not an escape for `\c`.

Source files are NUL-terminated in the tag; the terminator is not whitespace, so a lexer
that keeps it reads a stray token at the end of every file.

## How well the decompiler does

`mjolnir script --verify` decompiles all 6,827 campaign scripts and compares each
against the source the same scenario carries, as token streams — comments cannot come
back, and the compiler coerces `-1` to `-1.0` and accepts `0` for `false`.

| Outcome | Scripts |
|---|---:|
| Token-for-token match | 6,284 (92.0%) |
| Differ only because the source used `cond` | 205 |
| No source block to compare against | 150 |
| Genuinely differ | 188 |

**Every one of the 188 is a quoting disagreement** — same text, quoted on one side and
bare on the other. Nothing else is unexplained.

## The compiler

`crates/blam-hsc/src/compile.rs` goes the other way: HSC source into an expression tree,
string blob, and `scripts`/`globals` blocks. `mjolnir compile <file.hsc>` runs it against
the committed corpus and needs no game installation.

What it reproduces is the tree **semantically**, not byte for byte. Three things are
deliberately the compiler's own:

- **Datum generations.** The shipped arrays use two generation bases per scenario, an
  artifact of the engine compiler's datum allocator wrapping mid-run. A handle only has
  to agree with its target, so this emits one base throughout.
- **Free slots.** A shipped array is sparse; this emits a dense one.
- **String blob.** The shipped blob repeats strings — 9,168 distinct offsets across
  2,806 distinct strings in `a30` — and this interns instead.

Everything the engine reads is reproduced: expression types, opcodes, value types,
sibling chains, and the rule that a call's first child names it and carries the same
opcode. Rules confirmed against the shipped data rather than assumed:

| Node | `opcode` | `data` |
|---|---|---|
| Group (call) | the engine function | handle of the first child |
| Script reference | index into `scripts` | handle of the first child |
| Globals reference | the value type | index into `globals` |
| Parameter reference | the value type | the parameter's index |
| Literal | its own value type | the packed value |

The type of a literal is chosen by asking the position what it usually holds and then
checking the token can actually be that. Taking the position's commonest type alone gets
real cases wrong: the corpus says `set` usually takes a `boolean`, which compiled
`(set s_music_trigger 30)` to `true`, and it says `<` usually takes a `short`, which
compiled `0.6` to `0`. Candidates are now tried commonest-first and the first one that
fits the token wins.

### How well it does

`mjolnir script --recompile` compiles each scenario's own source files, decompiles the
result, and compares against the source that went in:

| Outcome | Scripts |
|---|---:|
| Token-for-token match | 6,284 (94.1%) |
| Differ only because the source used `cond` | 205 |
| Differ | 188 |
| Compile errors | 0 |

Again **all 188 are the quoting disagreement**, which is a decompiler rendering question,
not a compiler one. The check that separates the two is the fixpoint: compiling the
decompiled output a second time must produce the same tree, since both trees are the
compiler's own. **All 13 scenarios reach it.** 78 literals across the whole campaign had
no usable type from either the position or the token, and are reported as warnings.

## In the tag editor

A `scenario` tag gets a third view alongside Form and Tree. It shows the shipped source
files with HSC highlighting, an outline of every script and global that jumps to its
declaration, and export to `.hsc`. When a scenario carries no source — a stripped or
hand-built mod — it shows decompiled output instead and says so. It is read-only until
the write-back below lands.

## Not done yet

**Writing a compiled section back into a scenario tag**, and therefore import in the
editor. The compiler produces the section; what is missing is the ability to substitute
whole *blocks* when re-serialising a tag. `blam_tag::write::write_block_subst` can
replace one section's content, which covers `script string data`, but `hs syntax datums`,
`scripts` and `globals` are `tgbl` blocks whose element count and packed bytes both
change. That is a `blam-tag` extension, not a compiler one. After it: bake through
`blam-pack` into a `_P` override container, as other tag edits already do.

**The 188 quoting disagreements.** Both directions now hit exactly this one class. It is
the only thing standing between the round-trip and 100%.
