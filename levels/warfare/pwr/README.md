# Pelican Warfare: alpine battlefield

## Saturday playtest variant

For the November 21 playtest, the standard Megalo writer can build Warfare
with vehicle occupants eligible to capture and contest a site. The released
variant reader supports every instruction in this version. Build from the
worktree root in PowerShell:

```powershell
$rules = 'out/pwr/playtest-20261121/variants/fireteam'
New-Item -ItemType Directory -Force $rules | Out-Null
cargo run --release -p blam-cli --bin mjolnir -- megalo write --mode warfare --vehicle-label-pool --allow-mounted-capture --out "$rules/warfare.mglo"
```

Keep `warfare.mglo` and the generated `warfare.layout.json` together. This
profile waits for two players, runs a 30-second warmup, and allows 60 seconds
for Pelican insertion. For a solo rehearsal, write to a separate directory and
add `--minimum-players 1 --warmup-seconds 5`. Omitting
`--allow-mounted-capture` produces the original infantry-only capture rules.

On November 18, both playtest files passed the released variant reader and all
38 installed map files matched the November 11 installation receipt. The host
also needs the Warfare lobby, HUD and native controller. The shared runtime
files on the development install changed after that receipt. The playtest
profiles still need an in-game insertion, capture and respawn check with a
second player.

### Build the map and both profiles

The November 18 playtest adds paired illuminated vehicle-entry markings to
the front and rear of all three bases. Green has an additional pair on its
outer arcade. Blue mirrors Red. Three batched visual meshes reuse the
existing base materials. The closest marking sits 0.94 m beyond the edge of
the rear driving lane. Cooked mesh readback matched the 504 Blender triangles
with a maximum vertex placement error of 0.38 mm.

From this worktree, the following PowerShell commands rebuild the package
from the reviewed base scene, the existing verified map cook, and the cooked
insertion assets. Each output argument takes a new folder.

```powershell
$review = 'out/pwr/playtest-20261121'
$editor = 'C:/Program Files/Blender Foundation/Blender 5.3/blender.exe'
$paks = 'C:/Program Files (x86)/Steam/steamapps/common/Halo Campaign Evolved/Meteorite/Content/Paks'
$base = 'levels/warfare/pwr/bases_v1'
& $editor --background --factory-startup "$base/forerunner_bases.blend" --python-exit-code 1 --python "$base/portal_guides.py" -- --out "$review/portal-inlays" --render
uv run --python 3.12 --with-requirements tools/level/requirements-alpine.txt --with OpenEXR python "$base/package_portal_guides.py" --paks $paks --art "$review/portal-inlays" --out "$review/portal-cooked"
uv run --python 3.12 --with-requirements tools/level/requirements-alpine.txt --with OpenEXR python levels/warfare/pwr/stage_playtest.py --guides "$review/portal-cooked/package.json" --canopy out/pwr/canopy-v2/cooked/receipt.json --runtime '=1.24.0' --out "$review/saturday"
```

The output includes a private map archive, both rules profiles and a hash
receipt. The archive contains the cooked base structures, entry markings,
passenger Pelican, canopy, pack, fallback chute and both baked water domains. The launcher builds mount
sidecars locally. CE content version 1.24.0 is the version on the development
machine when the archive was staged.

The published launcher applies profiles to map content. Its code mods share
one signed, installation-wide release. For the private development build,
`stage_mode_data.py` stages the Fireteam rules and layout, the PWR-only
mode descriptor and the cooked tactical-map widget alongside the matching
runtime. Its `--saturday` argument points to the folder above, `--stage`
to the private runtime overlay and `--tactical` to the widget cook receipt.
The staged widget lives in `/Game/MJOLNIR/UI` and uses the existing class
retention rules.

The coordinated private runtime supplies the Warfare lobby and native
transport integration. Both players need matching content and runtime
versions. Select PWR and **Pelican Warfare** in the ordinary Host Game
lobby. The private rehearsal install selects the solo rules and saves that
map/mode pair using the lobby's own previous-game setting.

### Alpine world playtest

The landscape build starts with the verified flight release. It adds a PWR-owned
surface package for mountain rock, erosion, snow, and Forerunner paving. The
playable terrain uses three native grass meshes, with denser growth on 230 of
the 256 landscape components and a 40–60 m fade. The baked PCG vegetation
has 16,690 instances across 18 mesh groups, with willows and rushes along
wet banks, scrub in open areas and young pines below the peaks. Roadways,
base entrances and vehicle routes have dedicated clearance masks. The map
reuses B30’s original Clear Afternoon sky mesh from chunk 986 and its textures
from 985. Three stock gull effects circle the water. The lake uses a glacial
blue surface finish. Both Fluid Flux domains use the original riverbed and lakebed.

After cooking the surfaces, grass and world, build both Saturday profiles with
the following command. Each output must be a fresh directory.

```powershell
$flight = 'out/pwr/playtest-20261121'
$world = 'out/pwr/world-art/foliage-r2/bake'
python levels/warfare/pwr/stage_world_playtest.py `
    --baseline "$flight/saturday-flight.3" --solo "$flight/flight-candidate/saturday" `
    --surfaces out/pwr/world-surfaces/cooked/pakchunk956-MJOLNIRPWRSURFACES_P.utoc `
    --land "$world/pakchunk965-MJOLNIRLAND-Windows.utoc" `
    --world "$world/pakchunk997-MJOLNIRMAP-PWR_P.utoc" --out out/pwr/world-art/saturday-b30.4
```

The root runtime ZIP contains the two-player Fireteam rules. The `solo` folder
contains the one-player runtime for rehearsals. Both use the same map archive.

### Spartan insertion rig

Open `canopy/v2/pwr_insertion.blend` to edit the deployed wing, suspension
lines, steering loops and detachable pack. The canopy origin is at the
rider's feet. The pack has its own origin at its base so the same mesh can
sit on the ground after touchdown. `canopy/v2/geometry-report.json` records
the two handle centers and the pack mounting point in Unreal centimetres.

The mapped Jump action (Space by default) exits the Pelican. Press it again
in freefall to open the canopy. Steer with the movement controls and hold
Shift or click and hold the left stick to brake. The flight HUD shows total
speed, vertical speed, ground track and terrain clearance. Its hollow diamond
follows the direction of travel when that direction is inside the visor.
Landing releases the pack and restores the starting loadout.

The center underside cell carries the MJOLNIR Core crest. A small woven label
on the detachable pack carries the maker's URL. The master prints are in
`canopy/v2/print` and `canopy/v2/build_prints.py` generates them.

To regenerate the authored geometry and cook both assets from the repository
root, run the following in PowerShell with the project's Unreal tools installed.

```powershell
$chute = 'levels/warfare/pwr/canopy/v2'
& $editor --background --factory-startup --python-exit-code 1 --python "$chute/build_rig.py"
python "$chute/cook.py"
```

The cook reads the delivered meshes back and verifies each grip socket, its
four distance levels, material assignments and fabric texture. The local
fit studies use reference Spartans from the developer's game files. For the
skinned CE multiplayer hand study, set `PWR_SPARTAN_FIT_REFERENCE` to a local
converted CE multiplayer biped glTF and run `render_reach.py` in the authored
Blender scene. Frames 1–9 of the resulting review scene show the reach.

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
