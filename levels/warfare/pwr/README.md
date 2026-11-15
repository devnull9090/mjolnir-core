# Pelican Warfare: alpine battlefield

## Offline base integration — November 11

The reviewed red, blue and green Forerunner bases are assembled with the full
world in `out/pwr/base-integration/pwr-world-bases-v1.blend`. Connected courts,
vehicle bypasses and gallery/roof-ramp thresholds replace the old structures.
Offline geometry, clearance and floor-support checks pass. The installed game
and its collision remain unchanged; no game was launched for this integration.
See [the integration notes](bases_v1/INTEGRATION.md) for renders, reproduction,
preserved contracts and the remaining native collision/export work.

## V5 candidate: current work

V5 replaces the image-derived mountain relief with native Gaea Alpine masses,
foothills and two erosion passes. The 2,000 × 2,000 m terrain preserves the full
v3 road, waterbed, foundation and gameplay contract. **Final visual acceptance
remains pending.** Fresh installed v5 native tests passed both manual
and automatic insertion, twelve floor probes, four compiled seam crossings,
three vehicle types, respawn and capture; see `out/pwr/world-v5/native-acceptance-v5.json`.
These results bind to its recorded collision; a later outcrop replacement needs
new compiled probes and renewed acceptance. Offline terrain, editor PCG,
native collision, cook, owned-package verification and bake/assembly pass.
The backed-up local candidate installation completed on 2026-11-09. A cook
or the historical v3 tests below do not certify the installed v5 map.

| Input/output | Candidate path |
| --- | --- |
| Native Gaea graph | `terrain/pwr_world_native_v5c.terrain` |
| Calibrated 1024² source | `terrain/gaea-v5c/source.json` |
| Constrained earthworks | `terrain/final-v5/final-master.json` |
| Exact 1009² rendered/native/PCG field | `terrain/runtime-v5/runtime-master.json` |
| Immutable gameplay baseline | `native-contract-v3/` |
| Installed visual5 configuration | `upgrade-v5-visual5.json` |
| Generated decor | `out/pwr/world-v5/visual5/authored-decor.json` |

The runtime manifest SHA256 is
`cfa587ac8c9bc565270c035ee3a281b8611c8197fb7c6c0833990b1b6c4ee45f`.
Fixed R16 encoding retains center 22,400 cm and Z scale 100; all 310,750
protected vertices and 79 checked support samples remain exact. Terrain spans
48–383.461 m. Protocol 20569/layout 3, 550 m flight paths and the 650 m ceiling
are preserved. See `docs/pwr_terrain_preservation.md` for measured earthworks.

Installed visual5 contains **4,470 trees, 804 rocks and 279,388 grass instances**.
Actual editor PCG selected 4,016 complete mature pines and 454 saplings. The
mature pine preserves the source's three UV channels and RGBA masks, uses
native bark/needle materials, and is owned exclusively by Nanite chunk 959.
Its ground datum is distinct from the lowest buried root vertex. The forest
and native hulls are sealed under `out/pwr/visual-v5/outcrops-v4/`; the QA wrapper
`out/pwr/world-v5/visual5/scenery-qa-seal.v2.json` also binds final cooked proofs
and the documented packaging-metadata amendment. Integrated native collision
contains 1,122,959 surfaces within the explicit 1.2M budget. Native
terrain remains 135,836 triangles followed
by 8,336 preserved architecture/detail triangles, supplied exactly once.

The render-only `visual-v5/apron-v4` extends the background to an 8 km square;
the playable terrain remains 2 km square. It uses an independent native Gaea
8 km field with erosion and a 2D transition. All 4,032 seam vertices are copied
exactly; packaged error is below 0.639 mm globally and 0.168 mm at the seam.
Terrain masks, stochastic world-space materials and correctly rotated normals
replace the repeated surface grids. The road-detail texture preserves Base and
road alpha byte-for-byte. Broad terrain-conforming Forerunner courts add
106,665 m² of paving, with no road/structure overlap and submillimetre native
readback error. See `docs/pwr_surface_materials.md` and
`visual_dressing/outcrops-v3.md`; final installed review is still required.

Fluid Flux uses two baked states, `upper_river` and `lower_lake`, with six native
Texture2D inputs. Visual5 live readback verified two finite surfaces, one native
lake wave actor, zero runtime domains/sources/capture beds and no wave render
target. Water follows the same authoritative bed; it supplies presentation,
not native swimming or vehicle buoyancy. State and readback evidence is under
`out/pwr/flux-v5/` and `out/pwr/visual-v5-qa/`.

Visual5 measured 13.93 ms/72 FPS at 3840×2160, Epic, 100% resolution in the
red-base overlook. A separate 79-second held view recorded p95 15 ms, p99 16 ms
and one 67 ms hitch. This is one warm local view, not full-map or multiplayer
certification (`out/pwr/visual-v5-qa/visual5-perf-red/`). Later visual changes
require a new measurement. The current art self-review still rejects uniform
meadows, overly large paving seams and insufficient distant alpine zoning.

Fresh visual3 movement checks passed, but testing found stationary tanks and
Banshees recycling after their initial drop exceeded the engine's 1.524 m moved
threshold. `vehicle-spawn-policy-v1.json` seals only eight corrected origin
heights and four matching probe-volume heights. It preserves the native DLL,
layout and respawn/abandonment timers. The next native refresh must explicitly
pass this policy, and final acceptance requires 180-second idle retention plus
normal abandonment and destruction respawn checks; those live checks are pending.

### Candidate reproduction and rollback

Run from the repository root after the source, PCG, native extra and Flux
artifacts exist. Detailed generation is documented in `docs/pwr_pcg.md`,
`docs/pwr_terrain_preservation.md` and `visual_dressing/README.md`.

```powershell
python levels/warfare/pwr/assemble_dressing_v5.py
powershell -NoProfile -File out/pwr/run-upgrade-v5.ps1 -Stages land,foliage,swap,collision
powershell -NoProfile -File out/pwr/run-upgrade-v5.ps1 -Stages editor,cook
# Refresh prepared metadata/probe flags and pass the native contract gate before bake.
powershell -NoProfile -File out/pwr/run-upgrade-v5.ps1 -Stages bake,assemble
```

The local runner sets `HCE_PAKS`, `MJOLNIR`, `MJOLNIR_DEBUG`, `EXAMPLES`,
`MJOLNIR_EXAMPLES`, `OODLE` and `PYTHONUTF8`, then invokes the tracked wrapper:

```powershell
python levels/warfare/pwr/upgrade.py --config levels/warfare/pwr/upgrade-v5.json --work C:/haloce/ce_conversions/warfare/PWR/expansion/world-v5/upgrade --stages editor,cook
```

Custom configurations require an explicit work directory. The unchanged default
`upgrade.json` and `world-v3` outputs remain the rollback path; do not promote
them during candidate testing. V5 uses `world-v5/{source-build,converted,upgrade}`,
Landscape LPW/chunk 965, filtered `visual-v5/grass`, new `pcg-v5` trees and
apron chunk 963. The original source/geometry reuse has its own receipts.
Installation remains a separate explicit step with recovery receipts.
This candidate's recovery records are `out/pwr/map-backup-20261109-093641/receipt.json`
and `out/pwr/runtime-20261109-093641/install-receipt.json`; the native DLL is unchanged.
`out/pwr/world-v5/audit-checklist.json` must remain unsealed until package hashes,
installation, actual game screenshots, native checks and frame times are recorded.

## Historical v3 baseline and rollback

PWR revision 3 is a 2,000 × 2,000 metre team-warfare map built from the approved
world concept. It contains eroded mountain flanks, a rolling vehicle basin,
a branching river, a southeastern lake with two low islands, winding 24 m
roads, three main bridges, two team bases and a northern Forerunner citadel.
The earlier revision 2 analytic scaffold is obsolete.

The 2 km expansion is installed and its private single-player loop has passed:
warmup, Pelican boarding, actual Space exit, parachute landing, base respawn,
capture scoring and transport cleanup. Warthog, Scorpion and Banshee movement
also passed with verified driver attachment and no player health loss.
The visual refinement pass and final frame-time measurements remain in progress;
these local results do not certify remote multiplayer or a full player count.

## V3 source and shared coordinate contract

- `terrain/world-reference-v1.json` identifies the approved images.
- `terrain/pwr_world_refined.terrain` is the Gaea source project.
- `terrain/final-v3/final-master.json` preserves the refined authoring terrain.
- `terrain/runtime-v3/runtime-master.json` is the exact 1009² quantized Unreal
  Landscape grid, with its verified NW–SE triangle diagonal. Rendering, PCG
  projection and native collision consume this surface.
- `terrain/final-v3/terrain.geometry.json` owns roads, watercourses and terraces.
- `layout.json` is the generated native gameplay contract: protocol 20569,
  layout 3, 550 m Pelican routes and a 650 m world ceiling.

Authoring uses metres with Z up. Unreal uses `[100*x,-100*y,100*z]` centimetres;
Blam uses metres divided by 3.048. The canvas origin is zero. Never independently
rerandomize a PCG transform or change a field without rebuilding its dependents.

## Modular construction and native collision

`build_world_v3.py` authors the scene through the actual Blender MCP connection
(Blender 5.2.3, mcp-for-blender 2.2.7, addon 1.8/protocol 15). `forerunner_kit.py`
provides original reusable plaza, wing, hub, ramp and perimeter modules;
`forerunner_stock.py` places nine detailed shipped buttresses using measured
asset pivots. The `.blend` retains 100 reusable module instances.

The tiny closed core defines world membership. Detailed terrain and separate
solid structures use native static collision pieces, with spatially ordered
triangles and independent Havok/projectile trees. Their accuracy and native
compiled piece receipts are required. Do not replace these with the earlier
26k-triangle approximation: it failed accuracy on the eroded mountains.

All map-owned build output is isolated under:
`C:/haloce/ce_conversions/warfare/PWR/expansion/world-v3/`
with `source-build`, `converted` and `upgrade` subdirectories. The shared HEK
and the original installed prototype are not source build destinations.

## Historical v3 PCG and rendering

The actual Unreal editor graphs select 2,021 mature pines, 279 saplings,
289,935 grass clumps and 298 glacial boulders. Repeat graph runs are identical.
The complete pines bake into 113 spatial HISM components with exact transforms,
shadows, disabled WPO and 900–1800 m culling. Their native bark hulls remain.
Rocks use stock materials and matching native hull transforms. Grass and
foliage do not require a runtime PCG plugin.

See `docs/pwr_pcg.md`, `docs/pwr_terrain_finalization.md`,
`docs/heightfield_landscape.md` and `docs/heightfield_collision.md` for the
reproduction and acceptance details. Local extracted stock meshes stay in
ignored build caches; source control contains paths and assembly rules.

## Gameplay

Native code owns warmup, team Pelicans, ejection, parachute descent, capture,
scoring and respawns. The map metadata and DLL reject mismatched layout
versions. Lua handles presentation and initial renderer setup. Red and Blue
are implemented; a third team and an increased player cap are future work.

Run `prepare_runtime.py` after conversion and before the final bake, then the
private upgrade stages. Install matching map and native artifacts together
only after all offline gates pass. Keep the install recovery receipts.

## Credits

Terrains powered by QuadSpinner Gaea.

The official Gaea example-derived project retains its license at
`terrain/reference/LICENSE.Gaea2Houdini`. Halo game assets are referenced from
the user's existing installation. Original modular source, terrain edits and
PCG assembly are authored for this project.
