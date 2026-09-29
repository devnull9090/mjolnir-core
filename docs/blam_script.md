# Blam Script (HSC) in Halo Campaign Evolved

**Build:** `2026.06.26.1097863.1-Rel-i343-Meteorite-2606-CU2` (Steam)
**Crates:** `crates/blam-hsc`, exposed through `mjolnir script`, `mjolnir scripting` and `mjolnir compile`
**Artifacts:** `defs/hce/scripting.json`
**Date:** 2026-08-03

> **Build label:** this note is stamped CU2; the installed build is CU3. See
> [`build_lock.md`](build_lock.md) for what has been re-verified against CU3 and for a
> caveat about CU2-stamped notes dated after 2026-08-01.

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

**The blob ends with a 0x1000-byte reserve.** In all thirteen shipped scenarios the
last string ends exactly 4,096 bytes before the blob does, and those bytes hold
leftovers — non-zero in every one of the thirteen — rather than strings. It is room the
engine keeps for strings it adds at runtime, such as a line typed at the console, so
a writer that packs the blob tight hands those writes whatever follows it. The
compiler appends the same 4,096 bytes, as zeros
(`blam_hsc::emit::STRING_DATA_RESERVE`), and `mjolnir script --rebuild-check` checks
the blob, reserve included, reads back unchanged.

## The expression datum

`hs syntax datums` is a Blam **datum array**, not a list: nodes address each other by
handle, and freed slots stay in place. 24 bytes each:

| Offset | Size | Field | Notes |
|---:|---:|---|---|
| `0x00` | 2 | generation | Pairs with the array index to form this node's handle |
| `0x02` | 2 | opcode | Engine function, script index, or global index |
| `0x04` | 2 | value type | Indexes the scenario's own value-type enum |
| `0x06` | 2 | flags | What the node is; a bitfield, see below |
| `0x08` | 4 | next | Handle of the next sibling |
| `0x0c` | 4 | string or source offset | Into `script string data` for a name, string or variable read; into the source files for a call or a number (below) |
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

**The flags** at `0x06` are a bitfield — the definitions name the field `flags` — not
an enum, though only five combinations ever occur:

| Bit | Name | Set on |
|---:|---|---|
| 1 | primitive | every leaf; clear on a call |
| 2 | script index | a call whose `opcode` indexes `scripts` |
| 4 | variable | a global or parameter read |
| 8 | permanent | every live node shipped |
| 16 | parameter | parameter reads only — the one bit not in the Reach-era set |

| Value | Bits | Kind |
|---:|---|---|
| 8 | permanent | Group — a call. `data` points at the child that names the callee |
| 9 | permanent, primitive | Expression — a leaf: either that name, or a literal |
| 10 | permanent, script index | Script reference — a call to a script in this scenario |
| 13 | permanent, variable, primitive | Globals reference — `data` indexes `globals` |
| 29 | parameter, permanent, variable, primitive | Parameter reference |

`blam_hsc::expr::NodeFlags` holds the raw bits, and `ExpressionType` is the
classification of the five; any other combination is carried through untouched.

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

### Source offsets, and `cond`

`+0x0c` is only a string offset on a node that has a string. On a call, and on a
number, boolean or `void` leaf, it is a **byte offset into the scenario's source files
taken end to end** in block order, each file followed by its NUL. The definitions name
the field `source_offset`, and the data agrees: all 72,611 call nodes across the
thirteen scenarios land on a `(`, and all 24,531 numeric and boolean literals that are
not a `cond`'s trailing else land on their own token.

That is what makes `cond` recoverable. It has no opcode — it is desugared to nested `if`
before any node is emitted — but every `if` and `begin` the desugaring makes, and the
literal it adds as the last clause's else, record the offset of the `cond` itself: 1,162
`if`s across the campaign point at the text `(cond`. The decompiler puts one back
wherever an `if` does, provided the shape matches exactly:

```
(if test1 (begin body1…) (if test2 (begin body2…) <zero of the cond's type>))
```

Every shipped `cond` ends in that zero: a `void` leaf in 207 of 230, a boolean or short
`0` in the rest. The compiler writes the same shape and the same offsets, so a compiled
tree decompiles back to `cond` too. Without the source files — a stripped scenario — a
`cond` still renders as the `if`s it is.

One thing the tree does not preserve: **special forms are not marked.** The value-type
enum has a `special_form` entry, but no node in any of the 272,190 shipped datums
carries it.

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

`mjolnir script --verify` decompiles all 6,829 campaign scripts and compares each
against the source the same scenario carries, as token streams — comments cannot come
back, and the compiler coerces `-1` to `-1.0` and accepts `0` for `false`. On CU4:

| Outcome | Scripts |
|---|---:|
| Token-for-token match | 6,463 (94.6%) |
| Source used `cond`, and still differs | 27 |
| No source block to compare against | 151 |
| Genuinely differ | 188 |

Before `cond` was recovered the second row was 205. The 27 left are scripts that use
`cond` *and* have a quoting disagreement: with quotes ignored, all 27 match. **Every one
of the 188 is a quoting disagreement** too — same text, quoted on one side and bare on
the other. Nothing else is unexplained.

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
sibling chains, source offsets, and the rule that a call's first child names it and
carries the same opcode. Compiling `a30`'s own source and walking each script against
the shipped tree, all 5,845 call nodes and all 1,937 numeric, boolean and `void` leaves
carry the shipped source offset. Rules confirmed against the shipped data rather than
assumed:

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
| Token-for-token match | 6,463 (96.8%) |
| Source used `cond`, and still differs | 27 |
| Differ | 188 |
| Compile errors | 0 |

Again **all 215 are the quoting disagreement**, which is a decompiler rendering question,
not a compiler one. The check that separates the two is the fixpoint: compiling the
decompiled output a second time must produce the same tree, since both trees are the
compiler's own. **All of them reach it** (14 of 14 on CU4). 78 literals across the whole campaign had
no usable type from either the position or the token, and are reported as warnings.

## Writing it back

`crates/blam-hsc/src/emit.rs` serialises a section into the bytes a scenario holds, and
`blam_tag::patch::rewrite` rebuilds the tag around it. Five things move together:

| Field | Section |
|---|---|
| `script string data` | `tgda` |
| `hs syntax datums` | `tgbl` |
| `scripts` | `tgbl` |
| `globals` | `tgbl` |
| `source files` | `tgbl` |

Two facts the shipped data forced, neither of them obvious:

- **A `block` field carries its element count inline** — the first four of its twelve
  inline bytes — duplicating the one in the `tgbl` header. A `data` field carries its
  byte length the same way. Resizing a block without fixing the enclosing element's copy
  leaves a scenario claiming a different number of scripts than it has.
- **Nothing outside the script section indexes the datum array.** AI task fragments
  (`script_fragment_block`) and performance lines reference scripts *by name* and carry
  their own source text, so rebuilding the tree cannot dangle them.

`mjolnir script --rewrite-check` writes each shipped section back unmodified and asserts
the tag comes out byte for byte identical: **13 of 13**. That is the check that the
writer is exact rather than approximately right.

`mjolnir script --rebuild-check` goes the whole way — compile the scenario's own source,
write it back, and re-read the result from nothing but the bytes. **13 of 13** rebuild
and read back cleanly, each about 100 KB smaller than it shipped, because the datum array
comes out dense and the string blob interned.

### What a rebuild loses

A rebuild produces only the scripts the source declares, and 150 scripts across the
campaign have no source block — 9 in `a15`, 12 in `a30`. Those disappear. Since task
fragments call scripts by name, a missing one can break behaviour far from the file being
edited, so the editor reports the exact list before an edit is applied rather than letting
the count quietly drop.

The `references` block is also left as it shipped: a script that newly names a tag will
not add it there.

## In the tag editor

A `scenario` tag gets a third view alongside Form and Tree. It shows the shipped source
files with HSC highlighting, an outline of every script and global that jumps to its
declaration, and export to `.hsc`. When a scenario carries no source — a stripped or
hand-built mod — it shows decompiled output instead and says so.

**Edit** makes the current file editable. Compilation runs half a second after typing
stops, so errors appear against their lines as you work, and **Apply to mod** is disabled
until it builds. Applying compiles the script into the scenario, records the `.hsc` files
under `scripts/<group>/<tag>/` in the project folder, and marks the tag changed; the
existing test, export and publish paths bake it like any other edit. The decompiled view
is never editable — it is a rendering of the tree, and compiling it back would silently
make it the mod's source of truth.

## Not done yet

**The quoting disagreements** — 188, plus 27 in scripts that use `cond`. Both
round-trip directions hit exactly this one class. It is the only thing standing between
them and 100%.

**Preserving source-less scripts through a rebuild.** They could be decompiled and
appended, but the decompiler is at 92% and injecting output that might be subtly wrong is
worse than reporting the loss.
