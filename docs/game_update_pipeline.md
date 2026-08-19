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

## Known issues

- Two CU4 chunks defeat the built-in Oodle decoder (`OozError`):
  `D40/_Generated_/BSP_Split` and `E20/_Generated_/BSP_Settlement`, both
  `scenario_structure_bsp`. Every other tag (12,290 of 12,292) decodes. No loose
  `oo2core_*_win64.dll` exists to fall back on — UE 5.5 links Oodle statically — so until the
  decoder grows whatever variant these use, `tagdiff` counts them as unreadable rather than
  diffing them.

## What CU4's run measured

The pipeline's first run had no older snapshot to diff against, so the CU4 post leans on the
CU3 lock (file level) and the corpus comparison (schema level):

- 49 of 255 files changed; nothing added or removed.
- Tag definitions byte-identical to the CU2 corpus: 101 groups, 1,779 structs, 13,250 fields.
- 12,292 tags (up from 12,290); `model_animation_graph` 176 → 178, including the anomalous
  `Cinematics/020la_sword/.../jorge_turret` path.
- All four AOB signatures unique; 13 mods clean; bridge answers; `blam-live` locates and reads
  a live payload correctly.

CU4's snapshot is the baseline. The CU5 post gets real field-level diffs.
