# Pelican Warfare map 0.1.2: how it was built

Map 0.1.2 is 0.1.1 with four changes, built on 2026-11-23 and not yet released:

- **No grass or plants on the approach roads.** `meadow_life.visual_margin` measured
  asphalt against the terrain geometry's road list only. The approach roads are asphalt
  in the road atlas but not in that list, so the baked meadow plants and the grass field
  grew across them (shot 8: the blue base's approach). The editor bakes both into the
  landscape level, so the fix needs the vegetation round re-run. The loose
  `foliage.bin` is not what draws them.
- **No rock through the middle bridge.** `pwr_bank_desert_b_806` stood 5.5 m up through
  the deck (shot 9). Its render row is dropped from the level, and its collision is sunk
  30 m into the bank (`visual_dressing/sink_rock_collision.py`). The new rule in
  `outcrops_v3.py` and `check_structure_clearance.py` keeps the next outcrop pass off
  bridge and culvert decks.
- **Zone bars in the top left**, the rebuilt chunk 958 (`build_pwr_warfare_zones.py`).
- **The branch's level additions** baked into chunk 997: bots, pathfinding, the
  Covenant wave squads, Spirits, Pelican staging and the moved-zone candidates.

## Inputs, pinned by hash

0.1.1 is `saturday.45/map-input` in the pelican-warfare Codex worktree
(`C:/Users/will/.codex/worktrees/pelican-warfare/haloce/out/pwr/river-riparian/`), which
is `saturday.44` with the newer chunk 958. Every `.ucas`, `pwr.level.json` and
`foliage.bin` matched PC 1's installed 0.1.1. Four `.utoc` files differ there only
because the launcher renames shader libraries at install (`ue-iostore` `shader_library`).

`saturday.44` was sealed from round 9031's content with this command, recovered from the
session that ran it (the receipts do not record the round's inputs):

```sh
RELEASE=1 UI=out/pwr/tactical-map-ui-v2/cooked GRASS=out/pwr/meadow-life/grass-r14/grass-mix.json \
  BRIDGES=out/pwr/bridges/fit RIDGES=1 VISTA_APRON=out/pwr/vista/apron-v9b AMBIENCE=out/pwr/ambience/sounds \
  BASES_COOKED=out/pwr/base-polish/gate6-native/Meteorite/Saved/StagedBuilds/Windows/Meteorite/Content/Paks \
  BASES_MANIFEST=out/pwr/base-int/art2/import.manifest.json \
  bash .dream-loop/vegetation/round.sh out/pwr/meadow-life/r12 44
```

A backup of that worktree's Unreal project, every saturday round, its Python environment
and `.dream-loop/vegetation` is on the NAS:
`\\UNAS-Pro\TheBigShareDrive\Unreal Projects\pelican-warfare-20261123` (90 GB).

## Steps

All new folders, nothing earlier overwritten; the Codex checkout ends clean.

1. **Plants** (`out/pwr/meadow-life/r13-roadfix`): `r12`'s eight inputs (candidates, both
   PCG outputs, home and edge shrubs, request, receipt, prepare) copied, then
   `meadow_life.py finalize` with the fixed script and `PWR_LEVEL_JSON` at the released
   level. `finalize` now drops plants on roads by `candidates()`'s own margins, so the
   PCG pass is not re-run: 903 of 388,953 plants go, nothing else changes.
2. **Grass field** (`out/pwr/meadow-life/grass-r15`): `meadow_grass_field.py` with the same
   command as `grass-r14`, plus a copy of its `grass-mix.json`. 915 texels change, 854 go
   to zero (shot 8's road: 81-104 to 0), none gain grass.
3. **Round** `saturday.46`: the command above with `r13-roadfix`, `grass-r15` and
   `UI=out/pwr/tactical-map-ui-v3/cooked`, version 46. The Codex worktree needed its own
   CLI and six example binaries built first (`blam-cli`; `ue-asset` retarget_package,
   mesh_rewrite, world_imports; `ue-iostore` extract_file, replace_members; `blam-pack`
   package_add). Against `saturday.45` only 958, 965 (landscape) and 997 (world bake)
   differ; `BakeFoliage` baked exactly 388,050 plants.
4. **Collision**: `sink_rock_collision.py` on `river-riparian/native/physics`
   (1174 triangles matched the rock hull's 1174 faces), then `mjolnir level collision`
   as `cook_riparian_toe.py` runs it. The untouched scene re-cooks to the released BSP
   byte for byte (`b03b92e6`); the new one differs in instance 21's bounds only. A ray
   at the rock's old top met it at 38.43 wu before and passes to the deck after, and in
   game a player walked through the spot.
5. **Final bake** of 997: the round's `river-basin/native/native-level.json` plus the
   branch's `blam` bots, pathfinding, objects, object names, vehicles and
   `warfare.capture_candidates` (equal to `out/pwr-nav/pwr-ai.level.json` without the rock),
   with `--bsp 8=` the new BSP and `--world` round 46's `river-riparian/packaging/LPE.umap`.
   This branch's CLI re-bakes the round's own level to the round's 997 byte for byte.
6. **Pack**: `saturday.46/map-input` with the new 997 and `pwr.level.json` (0.1.1's, rock
   row out, candidates in), `map pack --version 0.1.2 --sign` with 0.1.1's metadata.
   `release_loss.py` against 0.1.1: nothing lost. Members changed: 958, 965, 997,
   `map/level.json` (and `mjolnir.json`, `signature.json`).

Working files are in this worktree's `out/pwr-rebuild/` (not in git): the signed
`pelican-warfare-0.1.2.mjolnir`, `map-input-final`, `physics`, `bake-final`.

## Proven

On PC 1 with the pack's containers as developer builds (`mjolnir dev install`):
shot 8's road is bare, shot 9's deck is clear and walkable, the zone bars load from the new
958, the seated rider reads ZONES OPEN IN 0:46, and every one of the 11 wave places holds
its four squads. Not yet: the tactical map opened with M (its widget only loads when
opened), and a two-PC match on 0.1.2.
