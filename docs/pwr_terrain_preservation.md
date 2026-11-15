# Replacing PWR relief without moving its gameplay contract

The v5 preservation path accepts a new Gaea heightfield. It does not execute the
legacy sine hills, broad basin compression, road-height optimization or terrace
height selection. The byte-identical v3 `terrain.geometry.json` keeps the complete
3D road sections, bridge decks, waterways and foundations. The native layout
remains a separately verified contract; replacing terrain never authorizes
regenerating lower flight paths or moving spawns.

The reference is `terrain/runtime-v3/runtime-master.json`, the actual quantized
1009-square Unreal Landscape surface. The protected region includes road masks
above .001, bases/flat above .5, water above .01, shore above .5, road/water/support
sample cells, sixteen 12 m vehicle support discs, and a two-cell interpolation
collar. That initial mask protects 300,815 vertices (29.55%). Existing steep banks
in bounded road/water gaps are also preserved, followed only when necessary by
measured failing boundary clusters extended at most 12 m from the original core.
The measured bank-only exception can follow an existing steep bank to its gentle
toe/rim, first within 24 m and at most 40 m; it never enlarges the NE road or a
global collar. The receipt records every added region and both masks. All other relief comes
from the replacement Gaea field, corrected by a sparse biharmonic displacement
solve. Its full-grid boundary rows minimize curvature across the fixed/free
boundary; no nearest-donor seams or old unprotected mountain samples enter the
result. PyAMG preconditions the solve and has a fixed seed.

The default 180 m transition rejects a correction gradient above .75, both before
and after Unreal R16 quantization. A rejected
candidate needs more compatible source valley elevations or a deliberately
reviewed wider transition. The terrain must remain within the preserved scenario
bounds and below 400 m, retaining the existing 150 m flight clearance. This is a
numerical candidate gate, not approval of the terrain's appearance.

## Generate and verify the shared master

Run from the repository. Replace the source path with the verified new Gaea
manifest. Commands write only isolated v5/proof directories.

```powershell
uv run levels/warfare/pwr/terrain/finalize_terrain.py --source levels/warfare/pwr/terrain/gaea-v5c/source.json --preserve-runtime levels/warfare/pwr/terrain/runtime-v3/runtime-master.json --preserve-layout levels/warfare/pwr/native-contract-v3/layout.json --out levels/warfare/pwr/terrain/final-v5/final-master.json

uv run --with numpy --with pillow python tools/level/derive_runtime_heightfield.py --source levels/warfare/pwr/terrain/final-v5/final-master.json --out levels/warfare/pwr/terrain/runtime-v5/runtime-master.json --components 16
```

`constrained-terrain.receipt.json` reports exact protected equality, the geometry
and layout hashes, full road/water support equality, road grades, bridge
freeboards, water depths, earthwork slope and correction magnitude. Its diagnostic
NPZ contains the sampled source, earthwork displacement, final slope and protected
mask. Discrete boundary-normal grade changes are measured against the baseline;
the quantized triangle surface is not described as literally C1. Rejections
preserve separate source/blend/mask-labelled diagnostic artifacts and publish no
master. The original geometry bytes and all frozen source files remain unchanged.

`landscape_encoding_policy` explicitly retains center 22,400 cm and Z scale 100,
with the original 1009-square grid, spacing and XY origin. Both the direct
Landscape builder and runtime derivation honor this policy, reject changed
grid/transform/lift or clipping, and do not automatically refit the vertical
range. The representable interval is -32 to 479.9921875 m, in 7.8125 mm steps.
The derivation independently verifies protected samples against the baseline
after the R16 roundtrip and records `preservation.protected_runtime_heights_exact`.
The canonical surface remains `triangle_nw_se`, reflecting Unreal's Y axis.

The accepted numerical v5 candidate uses native Gaea v5c and a 180 m biharmonic transition. Its
remaining bank-stencil incompatibilities were projected locally after the solve:
90 free vertices changed by at most 0.5672 m, within 12 m of the offending stencils.
Protected/far samples stayed exact. Quantized correction grade is 0.745212, below
the unchanged 0.75 gate. Maximum boundary-normal grade change is 0.33075 (baseline
0.27956), with 95th percentile 0.063. This describes discrete triangle gradients,
not an assertion of perfect analytic smoothness.

Final runtime manifest SHA256:
`cfa587ac8c9bc565270c035ee3a281b8611c8197fb7c6c0833990b1b6c4ee45f`.
The recorded intermediate solve can reproduce the accepted projection without
repeating four AMG solves:

```powershell
uv run levels/warfare/pwr/terrain/finalize_terrain.py --source levels/warfare/pwr/terrain/gaea-v5c/source.json --preserve-runtime levels/warfare/pwr/terrain/runtime-v3/runtime-master.json --preserve-layout levels/warfare/pwr/native-contract-v3/layout.json --out levels/warfare/pwr/terrain/final-v5/final-master.json --resume-rejected levels/warfare/pwr/terrain/final-v5/rejected/b26005fe6a8a-b180-m7d0e9fb0/rejected-fit.npz
```

The accepted receipt records intermediate NPZ SHA256
`76f78176e4a8632a8f15779251c41c186c8f6dd447e38cfcdcf92365737d247a`.
Resume verifies its source/baseline/geometry contract, exact core mask, bounded
protection and protected heights, then applies all final numerical checks.

## Regenerate terrain-dependent assets

Use the new runtime master for both biome decisions and height projection. Old
PCG output, collision, apron edges and their hashes do not certify a new field.

```powershell
uv run --with numpy --with scipy --with pillow python tools/level/adaptive_heightfield.py levels/warfare/pwr/terrain/runtime-v5/runtime-master.json --out out/pwr/world-v5/collision-runtime-final --terrain-budget 800000 --reserve-surfaces 4000 --reserve-edges 16000 --ground-error .5 --road-error .15 --shore-error .25 --refinement-iterations 3 --chunked --cliff-error 2 --hierarchy-threshold .7

uv run --with numpy --with pillow python tools/level/pcg_pwr_inputs.py --heightfield levels/warfare/pwr/terrain/runtime-v5/runtime-master.json --out out/pwr/pcg-v5 --target 290000 --trees 2300 --seed 20568
```

The second command creates new candidates and `request.json`; it does **not**
pretend to run UE PCG. Execute those requests through the existing actual editor
PCG workflow, adapt the new outputs, then regenerate rock candidates using the
new selected trees and new runtime master. Refresh authored decor, matching
native collision and the outer apron. Fluid Flux must capture the new ground;
the unchanged physical riverbed, water profiles and bridge clearances remain
the native gameplay contract.

After native compilation, generate probes from the *actual* new piece receipt.
Require road error <= .15 m, shore <= .25 m, foundations <= .10 m and walkable
ground <= .50 m. Repeat the floor, compiled seam, vehicle and insertion checks.
The v3 runtime results are historical evidence, not acceptance of v5.

The completed v5 adaptive output contains 135,836 terrain triangles: measured
lane error 0.11035 m, all-road error 0.14844 m, shore 0.25 m, bases 0.09961 m
and walkable ground 0.50 m. The exporter appends 8,336 frozen/detail structure
triangles exactly once. `out/pwr/world-v5/native-contract.json` verifies the
compiled collision, complete layout and twelve new probes; its explicit
`live_acceptance_required:true` remains in force. The backed-up local v5 install
is complete; its fresh native tests passed and are recorded in
`out/pwr/world-v5/native-acceptance-v5.json`. Visual refinement and FPS remain
pending, and any later scenery collision change requires renewed probes/tests.
The compact provenance checklist is
`out/pwr/world-v5/audit-checklist.json`; no default configuration is promoted.
