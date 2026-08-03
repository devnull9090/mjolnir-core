# Mod Authoring: Design

**Status:** implemented through publishing (tag editor ≥ 0.3); texture assets and recipe
distribution are future phases.

How a community member goes from "I changed a value in the Tag Editor" to "players are
rating my mod on the hub", and why it is built the way it is.

## The one decision everything follows from

**A mod is authored as a recipe, not as baked binaries.** The Tag Editor's document model
is a *mod project*: a folder holding `mod.json` (identity: name, slug, semver version,
summary) and `edits.json` (a list of `{group, tag, field, value}` entries). Containers
are baked from the recipe only at the moments they are needed — test, export, publish.

Why a recipe:

- **Stability across game updates.** Edits are keyed by `(group, tag path, field path)`,
  never by catalog index or byte offset. A recipe re-applies against whatever the
  player's installation ships; anything that no longer resolves is flagged *stale* and
  blocks export rather than silently shipping wrong bytes.
- **Legibility.** A five-line JSON file is diffable, reviewable, remixable and safe to
  share anywhere — it contains none of the game's data.
- **It is the Phase 4 delta format.** `hub_architecture.md` §4 wants mods shipped as
  deltas applied against each player's own install. Mods authored as recipes from day
  one make that a distribution change, not an authoring change.

## The pipeline

```
edit in the editor ──► edits.json (autosave, per edit)
                              │ bake (blam-pack)
                              ▼
              <slug>_P.utoc / .ucas   one override container per shipped
                              │        source container, chunk IDs reused,
                              │        read back and byte-verified
        ┌─────────────────────┼──────────────────────┐
        ▼                     ▼                      ▼
  Test in game          Export archive           Publish
  Paks folder as        build/<slug>-<ver>       POST /mods → releases →
  pakchunk999-          .mjolnir (manifest +     PUT archive → complete,
  MJOLNIRDEV-…          content/, spec-exact)    findings shown in-panel
```

- **`crates/blam-pack`** is the single implementation of container baking — chunk-ID
  reuse, the `BinaryBlobSize` rewrite for resized payloads, and read-back verification.
  The `mjolnir pack` CLI and the editor both call it; neither carries its own copy.
- **Test installs** are the only thing the editor ever writes into the game folder, and
  every file carries the `-MJOLNIRDEV-` marker so removal is exact. The stub `.pak` trick
  matches the launcher's installer.
- **Export** produces a spec-exact `.mjolnir` (see `mjolnir_format.md`) and mirrors the
  hub's limits client-side (50 MiB, manifest rules) so most rejections happen before any
  upload.

## Publishing auth

Device pairing deliberately excludes `mods:write` — a paired launcher must not be able to
publish as you. The editor therefore publishes with a **user-minted API key** (hub
account page → key with `mods:write`), pasted once and stored locally. This keeps the
security posture (explicit, revocable, scoped) while making publish a button in the
editor. A future, friendlier option is an elevated pairing flow whose approval page says
"this device will be able to publish mods as you"; the API needs no changes for it.

`MJOLNIR_HUB` overrides the hub origin for local development.

## Known constraints, stated on purpose

- **Resized payloads work in game** (verified 2026-08-02: an assault rifle rewired to the
  needler's projectile — a resizing tag-reference edit — fired needler shards from a
  two-chunk container). The remaining content hazard is **novel string ids**: a `string id`
  set to text the game's string table does not already contain makes the game reject the
  whole tag, degrading to the pistol-fallback. The editor warns on string-id edits at
  test/export time; it cannot see the game's string table, so it warns rather than blocks.
- **Texture replacement does not exist yet.** Viewing and PNG export work; writing needs
  a BC encoder and a virtual-texture tile writer (the inverse of `assemble_mip`), which
  is its own project. The recipe format reserves an `assets/` folder for it.
- **Block counts, `data` fields** — same editing limits as the editor generally
  (`tag_editing_guide.md`).
- **Ratings, comments, conflict pages** live on the hub; the editor links out rather than
  reimplementing them.

## Phases

1. ~~Project model: recipe folder, autosave, change list, stable keys~~ ✅
2. ~~Bake and test: blam-pack, Test in game, Export `.mjolnir`~~ ✅
3. ~~Publish: API-key flow, upload, findings surfaced in the panel~~ ✅
4. Texture swaps: encoder + VT writer, `assets/` in the recipe
5. Recipe distribution (hub Phase 4): ship `edits.json`, bake on the player's machine
6. Conflict pre-check: a hub endpoint taking chunk IDs, so the editor can warn about
   overlaps with published mods *before* upload

Author-facing walkthrough: [`making_your_first_mod.md`](making_your_first_mod.md).
