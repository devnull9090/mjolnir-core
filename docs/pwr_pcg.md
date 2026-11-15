# PWR editor PCG generation

## Current v5 reproduction

V5 uses `terrain/runtime-v5/runtime-master.json` for **both biome decisions and
height projection**. This differs from the historical v3 split described below.
Manifest SHA256:
`cfa587ac8c9bc565270c035ee3a281b8611c8197fb7c6c0833990b1b6c4ee45f`.
Run from the repository root; the actual editor runner uses the project mutex.

```powershell
uv run --with numpy --with pillow python tools/level/pcg_pwr_inputs.py --heightfield levels/warfare/pwr/terrain/runtime-v5/runtime-master.json --out out/pwr/pcg-v5 --target 290000 --trees 2300 --seed 20568
powershell -NoProfile -File tools/ue/run_pwr_pcg.ps1 -Request out/pwr/pcg-v5/request.json
python tools/level/pcg_foliage.py verify out/pwr/pcg-v5/trees.candidates.json out/pwr/pcg-v5/trees.pcg.json out/pwr/pcg-v5/trees_repeat.pcg.json --receipt out/pwr/pcg-v5/trees.verification.json
python tools/level/pcg_foliage.py adapt out/pwr/pcg-v5/trees.candidates.json out/pwr/pcg-v5/trees.pcg.json out/pwr/pcg-v5/palette.json out/pwr/pcg-v5 --name trees
python tools/level/pcg_foliage.py verify out/pwr/pcg-v5/grass.candidates.json out/pwr/pcg-v5/grass.pcg.json out/pwr/pcg-v5/grass_repeat.pcg.json --receipt out/pwr/pcg-v5/grass.verification.json
python tools/level/pcg_foliage.py adapt out/pwr/pcg-v5/grass.candidates.json out/pwr/pcg-v5/grass.pcg.json out/pwr/pcg-v5/palette.json out/pwr/pcg-v5/grass

python tools/level/pcg_rocks.py prepare levels/warfare/pwr/terrain/runtime-v5/runtime-master.json levels/warfare/pwr/asset-palette-v3.json out/pwr/pcg-v5/trees.selected.json out/pwr/pcg-v5/rocks
powershell -NoProfile -File tools/ue/run_pwr_pcg.ps1 -Request out/pwr/pcg-v5/rocks/request.json
python tools/level/pcg_foliage.py verify out/pwr/pcg-v5/rocks/rocks.candidates.json out/pwr/pcg-v5/rocks/rocks.pcg.json out/pwr/pcg-v5/rocks/rocks_repeat.pcg.json --receipt out/pwr/pcg-v5/rocks/verification.json
python tools/level/pcg_rocks.py export out/pwr/pcg-v5/rocks/rocks.candidates.json out/pwr/pcg-v5/rocks/rocks.pcg.json levels/warfare/pwr/asset-palette-v3.json out/pwr/pcg-v5/rocks/authored_decor.json
```

Actual repeated graphs selected **2,291 trees** from 11,449 candidates and
**289,813 grass clumps** from 940,900 candidates. The rock graph selected 298
boulders. Follow `levels/warfare/pwr/visual_dressing/README.md` to generate
108 outcrops, 218 shore rocks, the apron and exact-hull grass exclusions. The
integrated grass source is `out/pwr/visual-v5/grass/foliage.json`: **287,785**
instances after 2,028 exclusions, with retained transforms unchanged.

The v5 editor receipt verifies 2,291 pines in 113 HISM components, zero position
error, quaternion-dot error 4.002e-8 and no duplicate decor actors. Its requested
cull range is **160,000–300,000 cm**, read from the generated group/metadata
request and checked against actual components. The 90,000–180,000 cm default
remains available to other maps. This editor proof is at
`world-v5/upgrade/PWR/foliage_bake/pine_hism.verification.json` under the isolated
conversion root. Cook, installed visuals and frame times have separate gates;
the backed-up v5 installation is complete, but live acceptance/FPS are not
established by these PCG receipts.

## Shared implementation and historical v3 evidence

PWR now runs actual Unreal Engine 5.5.4 `UPCGGraph` assets in the editor. Python
prepares projected terrain candidates and adapts graph output; it does not
choose the final points or generate their random rotation/scale. Runtime
gameplay still runs in Blam. The shipped Unreal world contains ordinary baked
instances and no PCG component, graph or runtime plugin dependency.

## Graph and ownership

`MjolnirPCGLibrary::GeneratePoints` imports the candidate JSON into a saved
`UPCGDataAsset`, builds a graph from stock PCG settings, attaches it to an
editor-only bounded actor, and calls `UPCGComponent::GenerateLocalGetTaskId`.
It ticks the PCG subsystem until generation completes, then exports
`GetGeneratedGraphOutput`. The saved graph nodes are:

1. Load PCG Data Asset: projected source points and stable candidate IDs.
2. Attribute Filter: `BiomeMask >= 0.5`, including authored road, water and
   foundation exclusions.
3. Density Filter: remove zero-density candidates.
4. Attribute Noise: PCG's seeded random density draw.
5. Attribute Filter: retain draws below each point's authored density.
6. Attribute Noise: PCG's independent seeded mesh choice.
7. Transform Points: seeded yaw and uniform scale, without positional offsets.
8. Graph Output: transforms plus original candidate IDs.

Graphs and source assets live in `/Game/MJOLNIR/PCGAuthoring/PWR`. Open the
saved `PCG_trees` or `PCG_grass` graph in the editor to inspect or extend it.
This folder is explicitly never cooked. PCG is enabled only for the Editor
target in the project and editor plugin descriptors. The bridge itself belongs
to the existing editor-only `MjolnirUIBuilder` module.

The approved 1024² master supplies biome/exclusion decisions; its derived
1009² runtime master supplies actual rendered heights. The latter uses the
verified Unreal cell diagonal (`triangle_nw_se` after the authoring-Y flip)
and already contains decoded R16 quantization. PCG candidates retain the same
IDs, XY positions, densities and biome decisions when reprojected to that
runtime surface. No plant relies on the rejected analytical `layout.py` terrain.

Trees use an 18 m candidate grid with deterministic offsets applied before
projection and a broad irregular woodland density field. Grass uses a 2 m
candidate grid. Roads, water, foundations and steep slopes remain excluded.
The saved UE graph still owns selection, mesh draw, yaw and scale; Python does
not choose final instances. Input generation verifies both master hashes and
editor generation rejects source changes during a graph run.

Each candidate has an integer `id`, `position` in authored metres Z-up,
`normal`, `density` in [0,1], `biome_mask` in [0,1], and `kind`. `allowed:false`
is another hard exclusion. Grass enables `align_to_normal`; substantial trees
remain upright. Unreal coordinates are `[100*x,-100*y,100*z]` centimetres.

## Reproduce

Run from the repository root. Do not overlap the editor plugin rebuild with a
cook/editor process using the same project. The editor runner uses the existing
project mutex and requires a newly written receipt, so a failed commandlet
cannot silently reuse previous results.

```powershell
$project = "$PWD/unreal/MJOLNIRMaterials/Meteorite.uproject"
& 'C:/Program Files/Epic Games/UE_5.5/Engine/Build/BatchFiles/Build.bat' `
    MeteoriteEditor Win64 Development "-Project=$project" -WaitMutex -MaxParallelActions=4

# Use the frozen biome master plus the exact rendered runtime grid.
python tools/level/pcg_pwr_inputs.py --out out/pwr/pcg-v3 --trees 2300 --target 290000 `
    --heightfield levels/warfare/pwr/terrain/final-v3/final-master.json `
    --projection-heightfield levels/warfare/pwr/terrain/runtime-v3/runtime-master.json
powershell -NoProfile -File tools/ue/run_pwr_pcg.ps1 -Request out/pwr/pcg-v3/request.json

python tools/level/pcg_foliage.py verify out/pwr/pcg-v3/trees.candidates.json `
    out/pwr/pcg-v3/trees.pcg.json out/pwr/pcg-v3/trees_repeat.pcg.json `
    --receipt out/pwr/pcg-v3/trees.verification.json
python tools/level/pcg_foliage.py adapt out/pwr/pcg-v3/trees.candidates.json `
    out/pwr/pcg-v3/trees.pcg.json out/pwr/pcg-v3/palette.json out/pwr/pcg-v3 --name trees
python tools/level/pcg_foliage.py verify out/pwr/pcg-v3/grass.candidates.json `
    out/pwr/pcg-v3/grass.pcg.json out/pwr/pcg-v3/grass_repeat.pcg.json `
    --receipt out/pwr/pcg-v3/grass.verification.json
python tools/level/pcg_foliage.py adapt out/pwr/pcg-v3/grass.candidates.json `
    out/pwr/pcg-v3/grass.pcg.json out/pwr/pcg-v3/palette.json out/pwr/pcg-v3/grass
```

`trees.selected.json` contains selected authoring positions, yaw, scale and
exact Unreal transforms. The native palette is 88% complete `Pine_Optimized`
(21.50 m nominal height), 12% `Pine_Sapling_A` (2.11 m nominal height), selected
from PCG's existing asset draw. Both use 0.7–1.3 uniform scale: saplings remain
small. Native expansion adjusts each mesh's root pivot and retains the exact
same transform for visuals and bark/trunk-only collision. Needles are excluded
from native collision.

Trees have `mesh:null` in the PCG selection because `pcg_tree_decor.py` expands
the native recipes. Complete static pines then pass through the existing
`BakeFoliage` HISM path in 250 m spatial cells, with shadows on, WPO off and
900–1800 m distance culling. The current 2,300 trees form 113 HISM groups.
Their original `swap.decor` records remain available to native collision;
render consumers omit the duplicate baked/runtime actor copies. Custom-material
or nonstatic tree records retain their original actor path.

The Landscape editor build checks actual pine instance/component counts, exact
sidecar transform parity, cull distances and absence of scheduled actor copies.
It writes `pine_hism.verification.json` next to the bake spec. Input grouping
is separately recorded in `out/pwr/pcg-v3/pine_bake_inputs.receipt.json`;
that input receipt is not proof of a completed editor/cook build.The full editor proof has now passed with all **2,300 instances in 113 HISMcomponents**, zero position error, quaternion-dot error about `4.0e-8` andscale error about `1.1e-15`. It directly verified shadows on, WPO off,900–1800 m culling and no decor actor copies. The saved world is`/Game/MJOLNIR/PCGAuthoring/PWR/Pine_BakeProof`; receipt and log are in`out/pwr/pcg-v3/pine-proof/`. Its stand-ins use verified native mesh bounds;the actual tree visuals resolve to shipped meshes in game. The normal mapeditor/cook stage repeats this verification against its own baked world.

Grass output is the existing `foliage.json`/MJF3 format, with exact `.xfN`
sidecars containing location, quaternion and scale as ten floats. The sidecars
avoid MJF's compact yaw/scale quantization. `foliage_bake.py` preserves them and
`BakeFoliage` reads them into ordinary HISM components. To replace legacy grass
while preserving rock/cliff/detail groups:

```powershell
python tools/level/pcg_foliage.py merge <upgrade-work>/foliage/foliage.json `
    out/pwr/pcg-v3/grass/foliage.json
```

The merger validates the binary structure and sidecars before writing, drops
legacy grass/short grass/tall grass/tufts/lip grass/weeds, preserves other
groups, and renumbers sidecars. `pcg:true` identifies imported groups, making a
repeat merge idempotent. The upgrade driver owns this integration step.

## Separate glacial boulders

`pcg_rocks.py` prepares a separate graph request, leaving tree and grass
exports unchanged. It projects onto the exact runtime master and checks a
17 m footprint clearance from roads, shores, foundations and selected tree
trunks. Low slopes at mountain feet receive candidates; steep inaccessible
faces and flat base aprons are excluded. The six glacial meshes come from the
verified `asset-palette-v3.json` inventory.

```powershell
python tools/level/pcg_rocks.py prepare `
    levels/warfare/pwr/terrain/runtime-v3/runtime-master.json `
    levels/warfare/pwr/asset-palette-v3.json out/pwr/pcg-v3/trees.selected.json `
    out/pwr/pcg-v3/rocks
powershell -NoProfile -File tools/ue/run_pwr_pcg.ps1 -Request out/pwr/pcg-v3/rocks/request.json
python tools/level/pcg_foliage.py verify out/pwr/pcg-v3/rocks/rocks.candidates.json `
    out/pwr/pcg-v3/rocks/rocks.pcg.json out/pwr/pcg-v3/rocks/rocks_repeat.pcg.json `
    --receipt out/pwr/pcg-v3/rocks/verification.json
python tools/level/pcg_rocks.py export out/pwr/pcg-v3/rocks/rocks.candidates.json `
    out/pwr/pcg-v3/rocks/rocks.pcg.json levels/warfare/pwr/asset-palette-v3.json `
    out/pwr/pcg-v3/rocks/authored_decor.json
```

The actual graph selected **298 of 9,025 candidates** identically on repeat.
The output hash is
`e79b6f4b96680d49d484dd25f75181038134f87f6269a17591ef3b5ac0a74695`.
The actor adapter preserves PCG XY/yaw/uniform scale and applies one explicit
mesh-bounds grounding offset, embedding 20% of each rock's scaled height.
That same root-adjusted transform supplies both rendering and native hulls.
The rocks use native static decor actors, avoiding the existing renderer's
documented layered-material instancing caveat. No second MJF rock copy is
created, and no cladding reach lookup against the buried CE shell occurs.

`b30_collision.py --only swap` successfully generated **23,374 native hull
triangles for all 298 rocks**, with stone material and zero cladding entries.
The exported triangles and six hull caches are in `out/pwr/pcg-v3/rocks/`.
This verifies hull generation and placement inputs; it is not a live collision
test. The map's extra-static collision integration must include that budget.

The integration's combined `out/pwr/pcg-v3/authored-decor.json` contains these
298 rocks plus nine authored buttresses, with source hashes. The upgrade map's
`authored_decor` points to that combined file; the existing tree adapter merges
its 2,300 tree recipes into it. Preserve both sources when regenerating it.

## Evidence and limits

The small-tile graph proof selected 135 of 256 candidates identically in two
runs of seed 20568. Seed 20569 selected 134 and changed transforms. Excluded
points were absent and all projected positions were preserved. Receipts and
the actual editor log are in `out/pwr/pcg/proof/`.

The editor HISM integration proof baked all 135 selected points into 12 HISM
components. Maximum position error was approximately 1.14e-13 cm, maximum
scale error 5.88e-8, and the saved proof world contained zero PCG runtime
actors/components. See `proof/bake.verification.json` and `proof/bake.editor.log`.
This verifies editor graph → export → MJF exact sidecar → existing HISM bake.
It does not establish final-map visual quality or multiplayer performance.

The final runtime-grid PCG run selected **2,300 trees from 11,449 candidates**
(**2,021 mature pines and 279 saplings**) and **289,935 grass clumps from
940,900 candidates**. Repeated full graph runs produced identical selections
and transforms; every hard exclusion and projected point was preserved.

- Biome master: `dbf21bef91497c28405c5f7c0826d0f0ac1a06c64472176ae693e9a9b2f93d1e`.
- Runtime master: `814c7a8b3796394f2a8027c10b9577424acff5c23972d65265f9d86f3b7fd3ec`.
- Runtime height array: `aae13c42fffcbbd2f248e057a8792fc966aaf48971c407b7a2bc2a0173ce1ad7`.
- Tree graph output: `69166f72670762f95b718793f0dac9a2ed3896d29b0ea8934ccb74786ffc1057`.
- Grass graph output: `8f8fede74acac39dcffc7f04e6252c4da247b58d3ddef5032c03657905d0df52`.

`out/pwr/pcg-v3/` contains input, graph, repeat verification and export receipts.
The earlier 886-tree/285,259-grass analytical-terrain run in `out/pwr/pcg/` is
superseded. Re-run current exports after any approved terrain/mask change.
Runtime native terrain collision, full-map performance and multiplayer still
require their separate acceptance checks; PCG repeatability proves none of them.

```powershell
python -m unittest discover -s tools/level -p test_pcg_foliage.py
python -m unittest discover -s tools/level -p test_pcg_pwr_inputs.py
python -m unittest discover -s tools/level -p test_foliage_bake.py
```

This first implementation uses a normal editor world and CPU PCG nodes. It
does not depend on runtime PCG, World Partition or experimental GPU graph
execution. UE's installed source supports editor partitioned generation if
future authoring budgets require it; the current game-world retargeter still
needs separate verification before shipping World Partition external actors.
The stock PCG workflow and larger-world choices are documented by Epic in
[PCG generation modes](https://dev.epicgames.com/documentation/en-us/unreal-engine/using-pcg-generation-modes-in-unreal-engine?application_version=5.5)
and [PCG builder commandlets](https://dev.epicgames.com/documentation/en-us/unreal-engine/world-partition-builder-commandlet-reference?application_version=5.5).
