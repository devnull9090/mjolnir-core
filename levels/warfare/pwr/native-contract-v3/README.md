# Frozen native contract and v5 acceptance

These reference files preserve the accepted v3 gameplay. They are not regenerated
from a candidate. `check_native_contract.py` pins their hashes and checks every
gameplay layout field, all native scenario inputs, and exact protected floor
vertices. It ignores only replacement `terrain_probe_*` flags and presentation
metadata. The separately checked new probe plan binds those flags to actual
compiled piece boundaries.

Layout 3 / protocol 20569 may remain when this entire contract passes. In
particular, homes, all sixteen spawns, capture radii, fleet/pickup placements,
timings, bounds, marker positions and routes must remain unchanged. The runtime
guard alone checks only ten marker positions; it is not a terrain-content hash.
Any gameplay change requires an explicit new layout/protocol decision and a
matching native DLL, variant, bootstrap, HUD, map and harness update. The
preflight never silently increments versions or relaxes tolerances.

This establishes controller compatibility, not interchangeability of old and
new terrain packages between peers. Every participant still needs the same new
map/collision package hashes. Layout 3's runtime marker guard does not negotiate
a terrain SHA; remote-peer package and simulation acceptance remains separate.

The routes remain at 550 m, even over lower replacement hills, and the ceiling
remains 650 m. Terrain plus the reserved architectural envelope cannot exceed
400 m. Accepted v3 static foliage extended to 418.220333 m; the package check
separately enforces that maximum (+1 mm arithmetic allowance). Thus the proven
global obstacle envelope leaves 131.779667 m below the flight plane, not 150 m
above every tree. Fixed Landscape encoding is centre 22400 cm, Z scale 100,
16 components / 1009 vertices, exact extent ±1000 m, and UE's authored
`triangle_nw_se` surface.

## Regeneration sequence

Run from the repository root. Substitute the agreed isolated v5 paths; do not
overwrite `final-v3`, `runtime-v3`, or `out/pwr/world-v3` evidence.

1. Produce the constrained final-v5 master using the frozen geometry and this
   `layout.json`. Derive runtime-v5 through fixed R16 encoding. Require zero
   protected-vertex change and exact R16 re-encoding. Do not rerun unconstrained
   road/site fitting. Generate a candidate layout with `final_layout.py --master
   <runtime-v5-master> --out <candidate-layout>`, then run the intermediate gate:

   ```powershell
   python levels/warfare/pwr/check_native_contract.py --runtime <runtime-v5-master> --layout <candidate-layout> --terrain-only --out out/pwr/world-v5/terrain-contract.json
   ```

2. The accepted 14-face CE membership shell, nine-surface converted core, fixed
   architecture/water geometry and fleet placements may be reused. The explicit
   allowlist is `out/pwr/world-v5/native-source-reuse-plan.json`: verify every
   source hash, copy only those entries to its isolated destination, and record
   matching destination hashes. Preserve original build receipts as historical
   provenance. Reused CE source is not a new-terrain validation. Do not copy old
   cooked packages, terrain extras, upgraded collision tails, PCG output or dense
   water meshes. New 4560-triangle base details, if selected, are added once as a
   separate identified architecture input.

3. Rebuild the adaptive terrain from the exact runtime-v5 surface:

   ```powershell
   python tools/level/adaptive_heightfield.py <runtime-v5-master> --out out/pwr/world-v5/collision-runtime-final --terrain-budget 800000 --reserve-surfaces 4000 --reserve-edges 16000 --ground-error .5 --road-error .15 --shore-error .25 --cliff-error 2 --hierarchy-threshold .7 --refinement-iterations 5 --chunked
   python tools/level/export_terrain_collision.py <runtime-v5-master> --mesh-dir out/pwr/world-v5/collision-runtime-final --architecture <verified-fixed-architecture-extra> --architecture-detail out/pwr/visual-v4/base-details/native-collision-extra.json --out <v5-source-build>/terrain-collision-extra.json
   ```

   Require `accuracy_and_mesh_budget_pass=true`; the research command can finish
   successfully while reporting a failed tolerance. Terrain is followed by
   architecture in this extra stream: 3776 fixed triangles, then 4560 details,
   giving an 8336-triangle tail. The exporter rejects duplicate inputs and checks
   the detail's frozen geometry/layout/baseline provenance. Preserve ordered NPZ
   and the exact tail count. A candidate 8192-triangle boundary is not a compiled seam.

4. Reproject/regenerate PCG against runtime-v5, regenerate foliage collision and
   merge it with the clean core plus new terrain/architecture exactly once. Run
   the native collision compiler with its receipt option. Verify source and
   output hashes, real instance ranges, table limits and the static obstacle
   envelope. Landscape, PCG, native terrain and Fluid Flux shore inputs must
   reference the same runtime-v5 master. Fluid Flux rendering/UE buoyancy does
   not establish Blam water physics.

5. Apply `prepare_runtime.py --layout <candidate-layout>` to the reused prepared
   level, build the fresh plan and patch its flags before final scenario bake:

   ```powershell
   python native/lobby/prepare_terrain_probe.py build --master <runtime-v5-master> --layout <candidate-layout> --receipt <v5-upgrade>/native-collision-receipt.json --ordered <v5-source-build>/terrain-collision-extra.ordered.npz --terrain-receipt <v5-source-build>/terrain-collision-extra.receipt.json --collision-proof out/pwr/world-v5/collision-runtime-final/collision-report.json --out out/pwr/world-v5/live-probes/terrain-probe-plan.json
   python native/lobby/prepare_terrain_probe.py patch out/pwr/world-v5/live-probes/terrain-probe-plan.json <v5-converted>/pwr.level.json
   python levels/warfare/pwr/check_native_contract.py --runtime <runtime-v5-master> --layout <candidate-layout> --level <v5-converted>/pwr.level.json --collision-receipt <v5-upgrade>/native-collision-receipt.json --probe-plan out/pwr/world-v5/live-probes/terrain-probe-plan.json --out out/pwr/world-v5/native-contract.json
   ```

   V5's clipped outer corner at `(-1000,+1000)` has a measured 0.285156 m
   collision approximation. The probe builder permits only outer boundary grid
   vertices supported by the matching adaptive proof and their region tolerance,
   capped at 0.5 m. Interior vertices retain the 1 mm identity check. This
   explicit diagnostic is recorded in the plan; exhaustive ordered-triangle
   matching to compiled collision remains unchanged.

6. Bake/cook and install only the coordinated complete package. Retain the
   accepted v3 DLL if gameplay constants are unchanged; a different provenance
   hash alone does not alter its behavior. If rebuilding for provenance, generate
   its header from the candidate layout and run the portable native tests before
   deploying with the matching map. Keep private solo test variants separate
   from production minimum-player/scoring settings.

## Private live acceptance

Only one harness owns the game bridge at a time. Start after the coordinated
install and a fresh private single-local-player match, with FlyCam disabled.
These commands deliberately move the local test player; do not run during
another person's match or simultaneously with UI/input tools.

```powershell
node native/lobby/smoke-warfare.mjs --host --keyboard --jump --respawn --capture-a --transports --screenshots --seconds=210 --out=out/pwr/world-v5/loop-test.jsonl
node native/lobby/smoke-warfare-terrain.mjs --probe --walk --screenshots --plan=out/pwr/world-v5/live-probes/terrain-probe-plan.json --out=out/pwr/world-v5/terrain-test.jsonl
node native/lobby/smoke-warfare-vehicles.mjs --drive --screenshots --out=out/pwr/world-v5/vehicle-test.jsonl
```

Require protocol/layout readiness; real Space exit and canopy deployment; safe
landing/respawn; capture scores; named transports 0/2/0; twelve sampled floors
and four actual compiled-seam traversals; same healthy unit through each probe;
and actual parent/position changes for Hog, Scorpion and Banshee. Also observe a
fresh automatic insertion without Space and retain its native log. No input
continues after a failed guard. Sampled native acceptance does not replace visual
review of new landforms/Fluid Flux, frame-time measurement, or remote-peer QA.

Accepted v3 evidence remains in `out/pwr/world-v3/native-acceptance-v3.json` and
the source receipts it references. The baseline package self-check is recorded
separately at `out/pwr/world-v5/baseline-native-contract.json`.
