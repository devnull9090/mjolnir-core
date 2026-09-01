# The GUObjectArray reader: loaded-tag identities without a scan

The live-mode census finds loaded tags by sweeping ~13 GB of the game's memory
for their bytes. This is the other half of the picture the research note
[`live_tag_locating.md`](live_tag_locating.md) pointed at: reaching UE's own
tables so "what is loaded" is a bounded pointer chase, not a sweep.

It works, end to end, verified against the shipped build
(`…Meteorite-2607-CU3`, UE 5.5.4) in mission a30. New code lives in
`crates/blam-live`: `objects.rs` (the object table), `names.rs` (the name
pool), and module-base lookup in `sys.rs`.

## The chain, all signature-resolved

1. **Module base** — `Process::module("HaloCampaignEvolved.exe")` via a Toolhelp
   snapshot. ASLR moves the image each launch; every static RVA is added to this.
2. **`GUObjectArray`** — the AOB in `signatures/GUObjectArray.lua` matches once in
   `.text`; its `LEA` displacement decodes to the array's RVA. UE 5.5 layout:
   `FUObjectArray + 0x10` is the chunked store, `Objects` (chunk-pointer array)
   at `+0x00`, `NumElements` at `+0x14`, 64K `FUObjectItem`s (24 bytes each) per
   chunk; each item's first qword is the `UObjectBase*`.
3. **Walk** — one read per chunk plus one per live object for its header
   (`ClassPrivate +0x10`, `NamePrivate +0x18`, `OuterPrivate +0x20`). 291,671
   elements, 263,374 live, in about a second.
4. **Name pool** — no signature ships for it (UE4SS resolves names by calling
   into the engine, which an external reader can't). So `names::find_pool`
   decodes the RIP-relative references out of the `FName` constructor *and the
   functions it calls* (the pool ref sits in `GetNamePool`, a one-line
   `lea rax,[NamePoolData]; ret`), and tests each candidate against a known
   `(id, text)` pair. It bootstraps from `FName` id 0, which is `"None"` in
   every UE build — so **no oracle is needed**. Layout: `FNameEntryId =
   block<<16 | offset`, entry at `Blocks[block] + offset*2`, `Blocks` at
   `FNamePool + 0x10`, entry header `{bIsWide:1; hash:5; len:10}`.

Verified: the pool was found at rva `0xd418e80` from the `"None"` bootstrap
alone, and **135/135** bridge-supplied tag names resolved byte-identically. A
known object's class pointer matched the game bridge exactly.

## The catch: "object exists" is not "data resident"

`GUObjectArray` lists **9,147** tag-asset objects under `/Game/Tags/`. The
census finds **369** with resident data. So nearly every tag in the catalog has
a live `UObject` whose bulk data is *unloaded* — the object existing says
nothing about whether its data section is in memory to poke. `GUObjectArray`
alone over-reports the editable set by ~25×.

That means the reader does **not** replace the census for "which tags can I
live-edit right now." What it does give, instantly and exactly:

- **Level detection.** Exactly one `BlamScenarioTagDataAsset` is loaded under
  `/Game/Tags/` — a30's — so the level is read directly from its package name.
  No fingerprinting, no ambiguity, and correct where the census's
  scenario-fingerprint fallback was noisy.
- **A full identity index.** Every present tag asset, name resolved and mapped
  to the catalog via `Catalog::tag_by_package` (the package name is the cooked
  path `tag_by_package` already parses). Useful for browse/"present in this
  build's session," distinct from "data-resident."

## Settled: the buffer is not reachable from the `UObject`

`tests/residency_probe.rs` answers this properly, and the answer is no.

Method matters here, because two earlier attempts produced convincing-looking
false positives:

- Comparing a fixed 512-byte window scored `ClassPrivate` at **74%** — tag data
  sections are zero-dominated, so any mostly-zero memory "matches."
- Whole-section `blam_live::verify` scored a *deliberately wrong* address at
  **72%**. It works inside the census only because candidates arrive there
  already established by high-entropy run agreement; as a standalone
  discriminator it is worthless.

The metric that works is the census's own: several **unique high-entropy
48-byte runs** reproduced at exactly the file's relative spacing. With it:

| measure | result |
| --- | --- |
| census-resident tags that also have a `UObject` | **366 / 369** |
| ground truth — probed tags verified at the census base | **252 / 288** |
| control — runs agreeing at a deliberately wrong address | **0** |
| **resident tags whose buffer is reachable from their `UObject`** | **0 / 288** |

The ground-truth row proves the probe detects a real buffer when one is there,
and the control proves it does not fire on noise. So the negative is real: for
tags known to be resident, the data buffer is **not** in the `UObject`'s first
1 KB, nor one pointer hop from any pointer-shaped field in it. The tag-asset
`UObject` is a name-and-class shell; the parsed buffer belongs to a separate
Blam-side structure, as `docs/live_tag_locating.md` found from the other
direction (scattered per-tag records, no dense table).

## Where this meets the census

Combining them is still the prize, with one hypothesis now eliminated:

- **Identity and level: use the reader.** 366 of 369 resident tags have a
  `UObject`, so coverage is effectively complete, and exactly one scenario
  object is loaded — instant, exact level detection.
- **Pokeable: still the sweep.** `UObject` presence is necessary but not
  sufficient (9,147 present vs 369 resident), and the buffer is not reachable
  from the object.
- **Untested lead:** a *residency flag* — some field that differs between the
  369 resident and the 9,147 merely-present objects. It would not give the
  buffer address, but it would let the sweep carry only the ~369 resident
  fingerprints instead of ~1,926, shrinking the matcher table and the sweep
  with it, and let the UI mark "live-editable" instantly. Both sets are now
  cheap to obtain, so this is a contained experiment.

The reader ships as `#[ignore]`d live tests documenting each layer
(`objects::tests::walk_live_object_table`, `names::tests::discover_name_pool`);
they need the game running and `MJOLNIR_EXE` set.
