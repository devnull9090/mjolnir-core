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
python tools/build_lock.py "<root>" --binaries-only
```

Seconds: it prints a binaries-only lock to stdout. A `version` or `host_sha256` that differs
from `config/hce-build.lock.json` means the game updated. Then the full check (minutes, 74 GiB;
`--verify` always hashes every file in the lock, `--binaries-only` does not apply to it) for the
complete changed-file list. It prints `VERSION MISMATCH: lock <old>, install <new>` first and
exits nonzero on any changed or missing file:

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

If the previous build was never snapshotted, it may still be recoverable from Steam's depot
history — `python tools/steam_depot_fetch.py --list`, then fetch with `--store` to ingest
(interactive Steam login: the user runs it). See "Recovering an older build" in
`docs/game_update_pipeline.md`.

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
   check `game_log` for Lua errors, confirm the bridge answers. Resume a mission with a
   `{"click":[x,y]}` input step on the menu item (window-client pixels; screenshot first and
   scale — the frontend menu ignores keyboard Enter, and relative mouse moves are warped by
   pointer acceleration), then `mjolnir poke --locate-only` on a loaded tag to prove
   `blam-live` still finds payloads. In-mission tags only: nothing is locatable at the
   frontend, not even `globals`. `not read: tag module <sha> has no profile; sweeping instead`
   on the `table` line means the new tag DLL has no measured profile and the four anchors in
   `crates/blam-live/src/tagtable.rs` no longer resolve it (`signatures/README.md`, "The tag
   module's anchors"). Add the new build's profile to `PROFILES` and run the gated
   `anchors_reproduce_the_measured_profile` test; it fails against the installed module
   until all four anchors resolve again, whatever `PROFILES` holds.
5. **Native mods**: they call the exe and the simulation DLL at per-build addresses and refuse
   a build they do not know, so the stack is not verified until these are updated.
   - `native/map_registry/mjolnir_map_registry.c` keeps one `exe_profiles` row per exe PE
     timestamp, Steam's and the Xbox app's, and logs `refused: exe timestamp ... is no build we
     have addresses for` otherwise. `native/signatures/port_rvas.py` finds the old row's
     functions and globals in the new exe by their code (the old exe comes from the snapshot
     store: `materialize <old-version> <dir> --only Meteorite/Binaries/Win64`). The Xbox
     app's exe updates too and cannot be read on disk: `port_rvas.py --dump` reads a memory
     image dumped from the running game instead (docs/game_pass.md has the recipe).
   - `native/blam_console/mjolnir_blam_console.c` accepts two simulation-DLL timestamps (Steam's
     and the Xbox app's); re-derive its RVAs per docs/blam_console.md, "After a game update".
   - `python tools/pe/statunit_pattern.py "<root>/Meteorite/Binaries/Win64/HaloCampaignEvolved.exe"`
     checks `native/frame_times`' DrawStat pattern and prints a new one if it no longer matches.

## 5. Update the record

- `docs/build_lock.md`: new build header, headline hashes (from the lock JSON), what this run
  re-verified, what remains older-measured.
- `docs/game_update_pipeline.md`: known-issue list if failures changed.
- `changelog/` is for *our* releases — game updates do not go there.

## 6. Draft the post

Write `blog/<ship-date>-<slug>.md` per `blog/README.md`: the date is the day the update shipped
on Steam (SteamDB's build history), not today. Shape that has worked: what the update is,
the file-level picture, what the tag diff found (lead with gameplay-relevant field changes and
anything anomalous — new content hiding in cinematic/tag paths is exactly what readers care
about), what still works (the stack re-verification), one honest limitations paragraph. Run
`pnpm sync` in `hub/`: it validates the post's format and regenerates the hub's snapshots of
`blog/`, `docs/` and `defs/` (`build_lock.md` and `game_update_pipeline.md` are published
notes). Commit what it regenerates under `hub/src/generated/` and `hub/public/` with the post;
CI's `pnpm sync:check` fails on drift. Run `pnpm typecheck` in `hub/` too if any hub code
changed. The post ships with the next hub deploy; it is public writing, so the user
reviews it before merge.
