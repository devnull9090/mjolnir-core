# Game Update Pipeline

**Since:** CU4 (`2026.08.11.1121610.2-Rel-i343-Meteorite-2607-CU4`), 2026-08-18

Steam updates the game in place. The moment a patch lands, the previous build is gone, and with
it any chance of asking "what did this update actually change" — CU4 taught us that the hard
way: we can prove 17 container sets changed (the CU3 lock's hashes say so) but never what
changed inside them, because nobody kept the CU3 bytes.

So every build gets kept from now on. The pipeline has three stages — snapshot, diff, publish —
and ends in a blog post on [mjolnircore.com/blog](https://mjolnircore.com/blog) naming what the
update changed.

---

## 1. Snapshot — `tools/game_snapshot.py`

A content-addressed archive of the install, taken after every update (and, ideally, *before*
letting Steam patch a build you care about):

```bash
python tools/game_snapshot.py --store D:/hce-snapshots snapshot \
  "C:\Program Files (x86)\Steam\steamapps\common\Halo Campaign Evolved" \
  --lock-out config/hce-build.lock.json
```

File bodies live under `objects/` named by SHA-256; each build is a manifest of paths pointing
into that pool. Unchanged files are stored once, so the first snapshot costs the full ~74 GiB
and each later one only what the update touched. `--lock-out` stamps out the repo's
[build lock](build_lock.md) from the same hashing pass.

The skip rules (`ue4ss/`, `LogicMods/`, `dwmapi.dll`, `*.log`, `*.dmp`) are imported from
`build_lock.py`, not duplicated — a snapshot and a lock taken from the same install must agree
about what "the install" is.

Other verbs: `list`, `verify` (store integrity), `diff` (file-level, `--json` for machines), and
`materialize`, which rebuilds a build's file tree out of the pool with hardlinks:

```bash
python tools/game_snapshot.py --store D:/hce-snapshots materialize CU3 D:/cu3 --only Meteorite/Content/Paks
```

`--only Meteorite/Content/Paks` is the usual form — it is exactly what `mjolnir --paks` wants,
so every existing tool runs unchanged against a dead build.

**The store holds copyrighted game content. It is a private local backup of an install the user
owns — it stays off the repository and off the network.** What gets published is the *diff*:
names, counts and field values, not game bytes.

## 2. Diff — `mjolnir tagdiff`

Field-level comparison of two builds' shipped tags:

```bash
mjolnir tagdiff --paks-a D:/cu3/Meteorite/Content/Paks \
                --paks-b "C:\...\Halo Campaign Evolved\Meteorite\Content\Paks" \
                --label-a CU3 --label-b CU4 --json cu3-cu4.json
```

Every tag is sorted into added, removed, changed or identical by payload bytes; changed tags are
decoded on both sides and reported field by field — "`jump velocity`: 2.3 → 2.5", with block
element counts for anything past the materialisation cap (`--elements`, default 256). The byte
comparison is ground truth; the field list is what makes it readable. `--json` carries the full
report for the blog post; the console shows `--show` differences per tag.

File-level context (binaries, containers, third-party DLLs) comes from
`game_snapshot.py diff <old> <new>`, which needs no materialisation at all.

## 3. Publish — `blog/` and the update report

A game-update post is written into `blog/` (see [`blog/README.md`](../blog/README.md) for the
format) and ships with the next hub deploy. The repo skill **`game-update-report`**
(`.claude/skills/game-update-report/SKILL.md`) walks an agent through the whole run — verify,
snapshot, diff, re-verify the stack, draft the post — with the rule that makes the post
trustworthy: *every claim traces to a measurement the pipeline took this run*.

---

## Recovering an older build

A build that was never snapshotted is not necessarily lost: Steam's CDN keeps old depot
manifests around, and `tools/steam_depot_fetch.py` wraps
[DepotDownloader](https://github.com/SteamRE/DepotDownloader) to pull one into an
install-shaped directory and ingest it straight into the store:

```bash
python tools/steam_depot_fetch.py --list
python tools/steam_depot_fetch.py 457322918737678760 --name cu3 --qr --store D:/hce-snapshots
```

Login is interactive and stays between the user and Steam — `--qr` is a Steam Mobile scan, or
`--username` makes DepotDownloader prompt for the password itself; nothing is typed into or
stored by our tooling. The game is app `2806050`; the content lives in depot `2806051` and the
never-changed DigitalExtras in depot `4192200`. Manifests SteamDB had seen as of 2026-08-18:

| Depot 2806051 manifest | Seen | Build |
|:--|:--|:--|
| `5851394981381786761` | 2026-08-17 | CU4 — snapshotted live |
| `457322918737678760` | 2026-07-29 | **CU3, confirmed** — recovered 2026-08-18, hashed identical to the CU3 lock |
| `8153709523381701809` | 2026-07-23 | CU2 (launch-era), unconfirmed until fetched |

The build is whatever version stamp the downloaded exe carries — the snapshot reads it from
there, so a wrong guess in `--name` mislabels the scratch directory, never the store. The
`.DepotDownloader` state directory is excluded from hashing (see `build_lock.py`), so a
recovered build hashes identically to the same build caught live.

Two caveats. Steam grants manifest *request codes* per manifest, and codes for old manifests
are not guaranteed forever — if DepotDownloader reports the code was denied, that build is
gone through official channels, which is the whole argument for snapshotting on the day an
update lands. And SteamDB's "seen" dates are its crawler's, not the release's, so the
build-to-manifest mapping above is confirmed only when the downloaded exe says so.

## Known issues

- ~~Two chunks defeat the built-in Oodle decoder (`OozError`)~~ — **fixed 2026-08-19.**
  `D40/_Generated_/BSP_Split` and `E20/_Generated_/BSP_Settlement` (both
  `scenario_structure_bsp`) failed identically on CU2, CU3 and CU4, so it was never an
  update regression. It was also not a missing codec variant: `oozextract` mishandles two
  unaligned tail reads that ooz itself performs. Both readers fetch a 32-bit word that ooz
  lets run past the end of the compressed region, relying on the surplus bits being masked
  off before they reach a value.

  - `decode_multi_array`'s forward varbits reader clamped the read to the bytes remaining
    and right-aligned the short result, which shifts the whole word down 8 bits per missing
    byte. On `BSP_Split` that turned an interval length of 65238 into 32894, leaving 32344
    bytes of an entropy array unconsumed.
  - `TansDecoder::tans_forward_bits` did not clamp at all and failed the decode outright as
    out of bounds.

  Both now pad the tail with zeroes, keeping the surviving bits in position. Verified by
  decoding every Oodle block of every container on CU2, CU3 and CU4 with the stock and
  patched decoders side by side: 5 blocks per build newly decode, and every block that
  already decoded is byte-for-byte unchanged. The fix lives in a fork wired up through
  `[patch.crates-io]` in the workspace `Cargo.toml`; drop it once it lands in a published
  `oozextract` release — [upstream PR](https://github.com/lvlvllvlvllvlvl/oozextract/pull/3).
  There is still no loose `oo2core_*_win64.dll` to fall back on — UE 5.5 links Oodle
  statically — but the pure decoder no longer needs one.

## What CU4's run measured

The pipeline's first run started with no older snapshot — and then recovered one:
`steam_depot_fetch.py` pulled the CU3 depot manifest and it hashed **bit-for-bit identical**
to the CU3 lock on all 252 shipped files, which both rescued the CU3→CU4 diff and validated
the whole recovery path. The full `tagdiff` (labels CU3 → CU4) reported:

- **1 added** (`a10/unsc_cryo_capsule` animation graph), **0 removed**, **358 changed**,
  11,931 byte-identical, 2 unreadable (the Oodle pair below).
- Substantive: `ai/generic-character` (+2 firing patterns, 199 field diffs) and
  `floodcombat_base-character` retuned; `jackal-model` hitbox targets reworked (elbows →
  hands, a headshot flag); `globals` camo `biped speed reference` 3.25 → 3.7;
  `game_engine_settings` encounter-remix seeds changed; scenario script edits in E10 (a new
  script), e30 (unit seat definitions) and C45 (one squad template).
- Cook noise, correctly ignored in the write-up: 176 animation graphs with byte changes but
  zero visible field diffs (uniform stamp at offset ~56), 120 BSPs whose diffs are runtime
  pointers/vtables/mopp bookkeeping, 31 lighting-info checksums, seam-ID renumbering.
- The CU4 re-cook changed directory *casing* inside containers (`Cinematics/A10/` →
  `Cinematics/a10/`), which is why `tagdiff` matches paths case-insensitively.
- File level: 49 of 252 shipped files changed; nothing added or removed. Tag definitions
  byte-identical to the CU2 corpus (101 groups, 1,779 structs, 13,250 fields).
- Timeline note: the oddly named `Cinematics/020la_sword/.../jorge_turret` animation graph is
  already present in vanilla CU3 — it predates CU4, whatever it is.
- All four AOB signatures unique; 13 mods clean; bridge answers; `blam-live` locates and reads
  a live payload correctly.
