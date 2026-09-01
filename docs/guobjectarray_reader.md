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

## Where this meets the census

The prize is combining them: `GUObjectArray` for identity and level (instant),
the residency signal for "pokeable." The likely residency signal is a
load-state flag or a bulk-data descriptor on the tag-asset `UObject` — now that
names resolve, a known-resident tag's `UObject` can be diffed against a
known-unloaded one to find the field that distinguishes the 369 from the 9,147
(and, ideally, the buffer pointer itself, making poke a pointer chase too).
That is the next step; see `live_tag_locating.md` for the buffer-side findings.

The reader ships as `#[ignore]`d live tests documenting each layer
(`objects::tests::walk_live_object_table`, `names::tests::discover_name_pool`);
they need the game running and `MJOLNIR_EXE` set.
