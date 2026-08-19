---
name: game-update-report
description: Run the full game-update pipeline after a Halo Campaign Evolved patch — verify what changed, snapshot the new build, diff tags against the previous snapshot, re-verify the MJOLNIR stack, and draft the blog post. Use when the game has updated, when the user says "new game version", "the game updated", or asks what a patch changed.
---

# Game update report

The pipeline is documented in `docs/game_update_pipeline.md`. This skill is the run book. The
install root is `C:\Program Files (x86)\Steam\steamapps\common\Halo Campaign Evolved`, its Paks
directory is `<root>\Meteorite\Content\Paks`, and the snapshot store is `D:\hce-snapshots`
(override with `HCE_SNAPSHOTS`).

**The rule that makes the post trustworthy: every claim in it traces to a measurement this run
took.** No claim without a command behind it. Game bytes never leave the machine — the post
publishes names, counts and field values only.

## 1. Confirm the update and what it touched

```bash
python tools/build_lock.py "<root>" --verify config/hce-build.lock.json --binaries-only
```

Nonzero exit with a `VERSION MISMATCH` line names the old and new builds. Then the full pass
(minutes, 74 GiB) for the complete changed-file list:

```bash
python tools/build_lock.py "<root>" --verify config/hce-build.lock.json
```

Keep the output — the changed-file list is the post's file-level section.

## 2. Snapshot the new build (also refreshes the lock)

```bash
python tools/game_snapshot.py --store D:/hce-snapshots snapshot "<root>" --lock-out config/hce-build.lock.json
```

Then `python tools/game_snapshot.py --store D:/hce-snapshots verify <new-version>` must report
0 bad, 0 missing. Commit the lock change.

## 3. Diff tags against the previous build

Materialize the previous build's Paks from the store, then run the tag diff. Both are cheap
except the tagdiff read itself (a few minutes):

```bash
python tools/game_snapshot.py --store D:/hce-snapshots materialize <old-version> D:/hce-prev --only Meteorite/Content/Paks
mjolnir tagdiff --paks-a D:/hce-prev/Meteorite/Content/Paks --paks-b "<root>/Meteorite/Content/Paks" \
  --label-a <old-version> --label-b <new-version> --json <scratch>/tagdiff.json
```

The JSON is the post's raw material: added/removed tags, and per-changed-tag field diffs.
Delete `D:/hce-prev` afterwards (hardlinks — costs nothing to recreate).

## 4. Re-verify the MJOLNIR stack

In rough order of how often updates break things:

1. **Signatures**: `python tools/pe/aob_scan.py "<root>/Meteorite/Binaries/Win64/HaloCampaignEvolved.exe" --verbose`
   — must end `4/4 signatures resolve uniquely`. A multi-match is worse than a no-match: UE4SS
   picks one silently and crashes later.
2. **Tag reader**: `mjolnir validate --all --verbose --paks "<paks>"` and `mjolnir roundtrip --paks "<paks>"`.
   Compare failure counts against `docs/game_update_pipeline.md`'s known issues; new failures
   are findings.
3. **Definitions**: `mjolnir defs --paks "<paks>" --out defs/hce/tag-definitions.json --build <new-version>`
   and `mjolnir scripting --paks "<paks>" --build <new-version>`. Diff before committing — a
   schema change (not just tag counts) is the headline finding if it happens, and means the tag
   editor and docs need review.
4. **Live game**: launch via the mjolnir-game MCP tools (or `node tools/mcp/game/cli.mjs`),
   check `game_log` for Lua errors, confirm the bridge answers. Resume a mission (click the
   menu item — see `tools/mcp/game/input.ps1`; keyboard Enter does not activate this menu), then
   `mjolnir poke --locate-only` on a loaded tag to prove `blam-live` still finds payloads.

## 5. Update the record

- `docs/build_lock.md`: new build header, headline hashes (from the lock JSON), what this run
  re-verified, what remains older-measured.
- `docs/game_update_pipeline.md`: known-issue list if failures changed.
- `changelog/` is for *our* releases — game updates do not go there.

## 6. Draft the post

Write `blog/<today>-<slug>.md` per `blog/README.md`. Shape that has worked: what the update is,
the file-level picture, what the tag diff found (lead with gameplay-relevant field changes and
anything anomalous — new content hiding in cinematic/tag paths is exactly what readers care
about), what still works (the stack re-verification), one honest limitations paragraph. Run
`node hub/scripts/sync-blog.mjs` to validate the format, and `pnpm typecheck` in `hub/` if any
hub code changed. The post ships with the next hub deploy; it is public writing, so the user
reviews it before merge.
