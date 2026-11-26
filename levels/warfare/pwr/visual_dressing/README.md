# PWR terrain dressing: v5 candidate and v4 rollback

This pass preserves the frozen `runtime-v3/runtime-master.json`, existing roads,
base floors, objectives and vehicle placements. It adds substantial native
rock geometry and an outer render-only mountain apron. All extracted geometry,
PCG assets and generated containers remain under `out/pwr/visual-v4`; no script
in this folder installs or calls the game.

The runtime terrain SHA is pinned in `build_candidate.py`. Generation fails
when it changes. The scripts resolve the repository from their source path,
so they work in an isolated checkout without assuming `C:/haloce`.

## Reprojecting a later accepted terrain

The v4 defaults remain reproducible. An explicit `--master` selects another
hash-verified runtime field and requires an independent `--out`. Reuse the
already-audited stock cache with `--assets` and `--rock-hulls`; no new extraction
is needed. `prepare` also requires explicit selected `--trees`, `nonsnow` needs
new `--rocks`, and the final audit requires the new `--grass` input. These checks
prevent silently mixing old placements with new terrain. Export rejects PCG
candidates whose recorded master hash differs from the selected runtime field.

After the new actual-PCG trees/grass/boulders have been generated, the equivalent
v5 calls are:

```powershell
$dressing = @('--master', 'levels/warfare/pwr/terrain/runtime-v5/runtime-master.json', '--out', 'out/pwr/visual-v5', '--trees', 'out/pwr/pcg-v5/trees.selected.json', '--rocks', 'out/pwr/pcg-v5/rocks/authored_decor.json', '--grass', 'out/pwr/pcg-v5/grass/foliage.json', '--assets', 'out/pwr/visual-v4/assets', '--rock-hulls', 'out/pwr/pcg-v3/rocks/hulls')
python levels/warfare/pwr/visual_dressing/build_candidate.py prepare @dressing
powershell -NoProfile -File tools/ue/run_pwr_pcg.ps1 -Request out/pwr/visual-v5/request.json
python levels/warfare/pwr/visual_dressing/build_candidate.py export @dressing
python levels/warfare/pwr/visual_dressing/build_candidate.py nonsnow @dressing
python levels/warfare/pwr/visual_dressing/build_shore.py prepare @dressing
powershell -NoProfile -File tools/ue/run_pwr_pcg.ps1 -Request out/pwr/visual-v5/shore/request.json
python levels/warfare/pwr/visual_dressing/build_shore.py export @dressing
python levels/warfare/pwr/visual_dressing/build_candidate.py apron @dressing
python levels/warfare/pwr/visual_dressing/package_apron.py @dressing
```

Generate the new native outcrop/shore hull receipts from those exact placements,
reuse/copy the verified stock hull caches, and export the new apron container for
readback before running `audit_candidate.py @dressing`. The audit checks the new
apron seam against the selected master and filters the new grass with the actual
placed hulls. Counts are measured afresh; the historical v4 counts below are not
assumed for a replacement landscape. Nothing installs itself.

## Current verified output

The later v5 output is isolated under `out/pwr/visual-v5`, on runtime hash
`cfa587ac8c9bc565270c035ee3a281b8611c8197fb7c6c0833990b1b6c4ee45f`:
2,291 actual-PCG trees; 298 boulders, 108 outcrops and 218 shore rocks;
287,785 grass instances after 2,028 exact-transform hull exclusions. The denser
apron has 45,108 triangles and at most 100 m radial ring spacing. Packaged readback
measured 0.515 mm maximum world error and 0.180 mm seam error. It uses the shipped
`MI_Rock_Glacial_Med_A` height/slope Snowblend material for live review;
`--apron-snow off` restores the audited NoSnow counterpart. These are generation
and geometry receipts, not final in-game appearance/performance acceptance.

V5 is installed locally with recovery backups; live map/vehicle/Flux acceptance
and FPS remain pending. The
candidate config consumes `rocks-and-outcrops.authored-decor.json` through
`assemble_dressing_v5.py`, `grass/foliage.json` after exclusions, and
`apron/runtime_decor.json` plus chunk 963. Root retains all v4 defaults and
`upgrade.json`; the candidate is explicitly selected with `upgrade-v5.json`.

After the v5 exports above, the remaining isolated hull/readback steps are:

```powershell
$env:MJOLNIR_DEBUG = (Resolve-Path target/release/mjolnir.exe).Path
python tools/level/b30_collision.py out/pwr/pcg-v3/rocks/empty.level.json out/pwr/pcg-v5/grass/foliage.bin out/pwr/visual-v5/outcrops.authored-decor.json out/pwr/visual-v5/outcrops.native-hulls.json --hulls out/pwr/visual-v5/hulls --only swap
python tools/level/b30_collision.py out/pwr/pcg-v3/rocks/empty.level.json out/pwr/pcg-v5/grass/foliage.bin out/pwr/visual-v5/shore/shore.authored-decor.json out/pwr/visual-v5/shore/native-hulls.json --hulls out/pwr/pcg-v3/rocks/hulls --only swap
# Prepare apron/audit-paks with the existing global.utoc/global.ucas and the new apron container.
target/release/mjolnir.exe mesh export --paks out/pwr/visual-v5/apron/audit-paks --asset SM_PWR_DistantApron --out out/pwr/visual-v5/apron/roundtrip.glb
python levels/warfare/pwr/visual_dressing/audit_candidate.py @dressing
python levels/warfare/pwr/assemble_dressing_v5.py
```

Reuse the three audited outcrop hulls in `visual-v5/hulls` and the six stock
rock hulls in `pcg-v3/rocks/hulls`. These exported hull JSONs are proof inputs;
do not append them as a second collision extra when normal scenery collision
already consumes the same decor. The apron is render-only and supplies no
native collision. The independently preserved 60 base attachments are merged
from `visual-v4/base-details`, with their collision supplied only in the 8,336
triangle architecture tail.

The historical v4 measurements follow.

- **101 actual UE5.5 PCG outcrops:** 5 PNW macro formations, 70 Uluwatu cliffs,
  26 tundra shelves. Three repeated graph runs produced identical transforms.
  Masks protect each asset's maximum yaw-independent footprint plus 12 m from
  roads, water, shores and foundations, and plus 8 m from existing tree roots.
  Conservative native collision: **8,122 triangles**, using the same actors.
- **218 actual PCG shore boulders:** native Glacial Med A/B/C meshes at
  0.35–0.9 scale with stock NoSnow materials, concentrated on the real shore
  mask. Road/base clearance is 12 m, bridge-axis clearance 20 m and tree-root
  clearance 7 m. Conservative native collision: **16,598 triangles**.
- **298 existing PCG boulders:** snow materials replaced; IDs, mesh paths,
  positions, rotations and scales remain identical to v3. Lrg A uses the stock
  PNW Lrg A counterpart material. Med C originally uses Lrg C's material, so it
  receives Lrg C NoSnow. Native collision remains unchanged.
- **8 km apron:** 16,128 vertices and 27,972 triangles, with all 4,032 inner
  boundary vertices copied from the exact runtime field. Graded annular rings
  join without internal cracks; the two intentional open boundaries contain
  exactly 4,284 edges. Native packaged readback measured **0.462 mm maximum
  seam error**, **0.678 mm maximum world-position error**. No triangle enters
  the frozen playable square. Irregular distant massifs rise to about 875 m.
  The actor has no native collision and the existing decor loader disables
  its Unreal collision. This apron is an ordinary low-complexity mesh;
  the three stock cliff families retain their existing Nanite resources.
- **286,712 grass clumps:** 3,223 clumps removed from the original 289,935
  actual-PCG output where expanded rock hulls intersect their canopy. Every
  retained exact transform and compact record remains byte-identical.

These receipts prove generation, exclusions, transforms and native package
readback. They do **not** certify the final game's appearance, distant material
blend, native collision compile or frame rate. Those require root's cook and
live checks. The approximate convex rock hulls are not triangle-exact visual
collision, particularly on concave formations; the full-footprint clearances
keep their approximation away from the established routes and foundations.

## Reproduce

Run from the repository root, with the existing CLI/examples built. The first
command only reads installed stock packages. No asset purchase is required.

```powershell
python levels/warfare/pwr/visual_dressing/audit_assets.py
python levels/warfare/pwr/visual_dressing/build_candidate.py prepare
powershell -NoProfile -File tools/ue/run_pwr_pcg.ps1 -Request out/pwr/visual-v4/request.json
python levels/warfare/pwr/visual_dressing/build_candidate.py export
python levels/warfare/pwr/visual_dressing/build_candidate.py nonsnow
python levels/warfare/pwr/visual_dressing/build_shore.py prepare
powershell -NoProfile -File tools/ue/run_pwr_pcg.ps1 -Request out/pwr/visual-v4/shore/request.json
python levels/warfare/pwr/visual_dressing/build_shore.py export

$env:MJOLNIR_DEBUG = (Resolve-Path target/release/mjolnir.exe).Path
python tools/level/b30_collision.py out/pwr/pcg-v3/rocks/empty.level.json out/pwr/pcg-v3/grass/foliage.bin out/pwr/visual-v4/outcrops.authored-decor.json out/pwr/visual-v4/outcrops.native-hulls.json --hulls out/pwr/visual-v4/hulls --only swap
python tools/level/b30_collision.py out/pwr/pcg-v3/rocks/empty.level.json out/pwr/pcg-v3/grass/foliage.bin out/pwr/visual-v4/shore/shore.authored-decor.json out/pwr/visual-v4/shore/native-hulls.json --hulls out/pwr/pcg-v3/rocks/hulls --only swap

python levels/warfare/pwr/visual_dressing/build_candidate.py apron
python levels/warfare/pwr/visual_dressing/package_apron.py
```

For the packaged-readback audit, create `out/pwr/visual-v4/apron/audit-paks`,
copy the game's `global.utoc`/`global.ucas` there together with the new
`pakchunk963-MJOLNIRPWRVISTA_P` container, then export:

```powershell
target/release/mjolnir.exe mesh export --paks out/pwr/visual-v4/apron/audit-paks --asset SM_PWR_DistantApron --out out/pwr/visual-v4/apron/roundtrip.glb
python levels/warfare/pwr/visual_dressing/audit_candidate.py
python -m unittest discover -s tools/level -p test_foliage_bake.py
```

`audit_candidate.py` writes `rocks-and-outcrops.authored-decor.json`, the
filtered `grass/foliage.json` plus exact sidecars, the apron verification,
and a labelled placement proof. Root merges its base-detail records separately.

## Integration contract

- Merge **617 rock records** from `rocks-and-outcrops.authored-decor.json`
  into the authored-decor input, replacing the original 298 rocks. Keep the
  original nine buttresses and any separately reviewed base details.
- Feed that decor through the usual `b30_collision` path **once**. The two
  standalone hull JSONs are verification/integration alternatives; adding
  them as extras as well would duplicate collision.
- Point `pcg_foliage` to `out/pwr/visual-v4/grass/foliage.json`.
- Append `apron/runtime_decor.json` through the render-only runtime-decor hook,
  and `apron/pakchunk963-MJOLNIRPWRVISTA_P` through `extra_containers`.
  Do not place this uninstalled custom mesh in foliage bake inputs.
- PWR `pine_cull_cm: [160000,300000]` becomes
  `foliage_bake.py --pine-cull 160000,300000`; other maps retain 900–1800 m.
  Final performance must be measured after the wider forest visibility cook.

The apron uses verified stock
`/Game/Env/Bio/Rock/Glacial/Rock_Glacial_Med_A/Materials/MI_Rock_Glacial_Med_A_NoSnow`.
This historical binding was rejected in actual v5 review: the stock material's
object-space projection interacts with the mesh writer's approximately 8,000×
normalization transform and produces stretched surround textures.

## Follow-on v5 candidates

`apron-v2` replaces the Gaussian/reflected relief with one continuously sampled
native Gaea v5c field. It has 101,304 triangles, maximum horizontal edge 88.889 m,
an exact copied 4,032-vertex source seam, and native readback errors below 0.842 mm.
The new `M_CE_AlpineApron` binding uses world coordinates and verified native
textures. Its geometry/material files and readback receipt are isolated under
`out/pwr/visual-v5/apron-v2`; no playable heights or native collision change.

`outcrops-v2` reduces the 108 repeated formations to 58 reviewed irregular anchors:
2 embedded macros, 12 embedded cliffs, 24 horizontal shelves and 20 CliffFlat
ledges. Exact native mesh before/after previews are Blender approximations.
Actual editor PCG produces seeded yaw draws bounded to ±14° of each local
terrain contour; asset role, scale and irregular anchor XY remain authored.
Two excluded fixtures and repeated graphs verify selection/projection and
determinism. This is a documented hybrid, not a claim that the preview's Python
selection was already an Unreal PCG run.

```powershell
uv run --with numpy --with scipy --with pillow python levels/warfare/pwr/visual_dressing/pcg_outcrops_v2.py prepare
powershell -NoProfile -File tools/ue/run_pwr_pcg.ps1 -Request out/pwr/visual-v5/outcrops-v2/request.json
uv run --with numpy --with scipy --with pillow python levels/warfare/pwr/visual_dressing/pcg_outcrops_v2.py export
# Supply the audited native hull caches before filtering the original grass.
uv run --with numpy --with scipy --with pillow python levels/warfare/pwr/visual_dressing/pcg_outcrops_v2.py grass
```

Final rock input is `outcrops-v2/rocks-and-outcrops.authored-decor.json`: 574 records,
including the existing 298 boulders and 218 shore rocks unchanged. The 2,291 trees
also remain unchanged. Candidate grass is written to `outcrops-v2/grass` from the
original exact PCG transforms. Integration requires reviewed new hulls, native
collision recompilation, `refresh_native_probes.py`, and fresh live acceptance;
the passing previous collision receipt cannot certify changed rock placements.

## Splitting the apron into sectors (performance, 2026-11-26)

The shipped apron (`out/pwr/vista/apron-v9b`, 3.24M triangles) is one mesh
whose bounds always hold the camera, so the engine drew all of it every frame,
whichever way the player looked. On PC3 (GTX 1080 Ti, Medium, 1080p) hiding it
saved 1.7-2.7 ms from the map's centre looking out and 0.9 ms looking at the
ground (`mjolnir_bench hide DistantApron`).

`split_apron.py` cuts a finished apron folder into angular sectors of equal
triangle count and cooks each as its own mesh. `mesh_rewrite --fit-axes` gives
each sector a box fitted per axis (a per-axis spawn scale). With one uniform
scale, a flat sector's box was a cube reaching over a kilometre under the
ground, and looking down still drew it. The triangles, normals and UVs are the
apron's own, so the joins are exact.

```sh
cargo build --release -p ue-asset --example mesh_rewrite
cargo build --release -p blam-pack --example package_add
python levels/warfare/pwr/visual_dressing/split_apron.py \
  --apron-dir out/pwr/vista/apron-v9b --out out/pwr/apron-sectors-12b --sectors 12
```

The output folder has package_apron's layout (chunk 963 plus a
`runtime_decor.json`, now with a row per sector), so `VISTA_APRON=<it>` stages
it. `stage_vista.py` replaces the level's range row with one row per sector,
each keeping the level's materials and vista.json's values. The first sector
keeps the id `pwr_distant_apron`. Stage from a level that still has the single
range row: vista.json finds the range by its mesh.

Measured on PC3 with 12 sectors, `hide DistantApron` (what the ring costs) at
three views, two runs each, the same session procedure:

| View | One mesh | 12 sectors, cube bounds | 12 sectors, fitted bounds |
|---|---|---|---|
| Centre, looking out | 2.72 / 1.68 ms | 0.24 / 0.33 ms | 0.40 / -0.20 ms |
| Centre, looking down | 0.93 ms | 1.43 ms | -0.22 ms |
| Red base, looking across the map | 2.64 / 2.93 ms | 2.86 / 2.59 ms | 2.80 / 3.57 ms |

Across the whole map the mountains fill the view and their sectors are drawn:
no change there. A lower-detail ring for lower Geometry qualities is the
lever left for that view; it changes the look.

Ray tracing is not the cost on this card: `r.RayTracing.Geometry.StaticMeshes
0`, `r.Lumen.HardwareRayTracing 0` and a 300 m `r.RayTracing.Culling.Radius`
each changed the look-down frame by less than 0.2 ms.

Twelve headings from 300 m showed the range whole, with no gaps at the joins.
Tested with the sector container installed beside the released map (as
`pakchunk10990-MJOLNIRAPRONTEST_P`) and the level file's row swapped. Not
released: the next map build carries it.
