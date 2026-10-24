# Your first custom map: Blender to the MJOLNIR hub

TST Proving Ground is an editable community example: original terrain and bases,
gameplay placements, a reproducible build, and a map players can install.
This guide follows the existing CE-to-Unreal pipeline. Blender supplies the
authored geometry; the CE BSP supplies gameplay collision; the Unreal cook
supplies runtime visuals. Players need the launcher and dependencies, not the
authoring tools.

**Status: public-beta preparation, October 24, 2026.** The current Blender detail
pass has been exported and rebuilt through HEK structure, lightmaps, cache,
conversion and Unreal cooking. The source traversal check passed all 206 samples.
The release notes record the in-game checks for the downloadable beta. Full-match
balance testing and a clean-machine authoring rebuild remain follow-up work.
This branch also includes candidate Oddball/KOTH rules; a map archive alone
cannot add those to an older code-mod installation.

For the public TST beta, see [the player/release notes](../levels/test/tst/BETA.md).
Use `prepare_runtime.py --release-beta` and `upgrade_ce_map.py TST --release-beta`
to advertise only Slayer, Team Slayer and CTF and use sky controls supported by
the published loader. Candidate Oddball/KOTH experiments below are for source
development, not requirements for installing that beta.

## 1. Set up your source and tools

Check out the same MJOLNIR source revision as the example. Record
`git rev-parse HEAD` for your eventual release. Build the example unchanged before
editing it, so setup errors are separate from map errors.

| Input | Purpose |
|---|---|
| Supported Campaign Evolved installation | Local game data used by conversion; actual playtests. |
| MJOLNIR launcher, multiplayer mods and CE runtime | Loads maps, gameplay rules and presentation. Record the versions tested. |
| Blender 5.1 + Halo Asset Blender Development Toolset Release 425 | Exports classic CE JMS geometry. Use the isolated add-on setup and checksum in [TST tool versions](pipeline_test_map.md#tools-and-rebuild). |
| Classic HEK | `tool.exe`, its supporting DLLs, `data`, `tags`, and `maps`; compiles the CE map. |
| Installed HCEEK tags | Stock dependencies referenced by the source. The rebuild stages required missing inputs. |
| Unreal Engine 5.5 + MJOLNIRMaterials project | Cooks the runtime world/materials. Follow [project setup](../unreal/MJOLNIRMaterials/README.md#setup), including target receipts and fork-layout plugins. |
| Rust, Python, PowerShell 7, Git Bash | Builds and runs the repository tools. |
| Built HalcyonRing `halo2ue-export` | Extracts the authored CE cache for conversion. |

Keep installed game archives and editing kits outside your source release.
See [asset provenance](../levels/test/tst/README.md#asset-provenance).

## 2. Open and understand the example

Open `levels/test/tst/tst.blend`. Read its embedded source README. Inspect the
terrain, sealed playable air volume, base openings, material slots, and UVs.
Named non-mesh guides show spawns, teams, objectives, scenery bounds, parking,
lights and teleporter pairs. They are annotations and never exported as geometry.

| File | Role |
|---|---|
| `build_geometry.py` | Reproducible original geometry, materials, UVs and placement design. |
| `terrain_form.py` | Shared terrain height and surface classification for the mesh and placements. |
| `perimeter_architecture.py` | Continuous northern wall, recessed bays, balcony, sheltered teleporter arrivals and exit terraces. |
| `tst.blend` | Editable source scene, annotated after JMS export. |
| `data/levels/test/tst/models/tst.JMS` | CE geometry export consumed by HEK. |
| `placements.json` | Gameplay/scenery/light placements in metres. |
| `build_scenario.py` | Writes the scenario from the placements and stock dependencies. |
| `tags/levels/test/tst/tst.scenario` | Authored scenario output. |
| `annotate_blend.py` | Adds non-exported guides and embedded documentation. |
| `render_preview.py` | Isolated six-camera Blender design preview, with optional locally available scenery. |
| `inspect_layout.py` | Fast authored-mesh placement clearance checks. |
| `art/` | Generated visual references and texture candidates, with provenance. |
| `prepare_runtime.py` | Adds objective markers and compiles candidate rules after conversion. |
| `rebuild.ps1` | Runs and validates the Blender-to-CE-cache sequence. |
| `tools/level/ce_upgrade_maps.json` | Conversion directory, scenery/material choices, water, lighting and map chunk. |

Blender uses metres with Z up. CE uses 3.048 metres per world unit. Runtime
Unreal positions use centimetres with the authored Y axis flipped: `[100*x,
-100*y, 100*z]`. The scripts perform these conversions; do not apply them twice.

## 3. Establish the gameplay layout

Choose the map's player count and primary mode. TST targets 4v4 with two bases
and three routes: central, rear cliff, and pond edge. Mark team starts, neutral
starts, flag rooms, weapon pickups, vehicle routes and teleporter exits first.

Use equivalent team travel distances, two exits from each flag room, cover near
spawns and exposed teleporter exits. Keep long sightlines intentional. A tree
can provide visual concealment but is not a substitute for reliable rock cover.
Check route width against players and vehicles, and overhead clearance against
the player capsule. A 150-by-84-metre footprint is a scale reference, not a
guarantee of balance.

## 4. Iterate visually in Blender before cooking

Keep repeatable cameras for the exterior overview, top-down layout, side
silhouette, and each base interior. Render those views after each meaningful
change and compare them against the approved target at the same framing.
Use image generation for material/detail studies or texture candidates, then
implement the chosen details in the actual scene. Label generated references,
Blender previews and in-game captures distinctly.

First settle shape, scale, routes and silhouettes. Then refine sloped supports,
portal bevels, layered roofs, recesses, terrain transitions and lighting. Check
interiors with a player-height camera. Annotated layout views should show
objective locations, spawn visibility, sightlines and teleporter links.

`render_preview.py` creates all six fixed views and a separate `preview.blend`.
See the [copyable render command](../levels/test/tst/README.md) for local asset
references and the authored alloy texture option. Use `--views red-interior
side` to inspect only the surfaces being changed. Its manifest records source
hashes and local asset references, so a render can be traced to its inputs.

For generated geometry, invoke Blender with `--python build_geometry.py --
--no-export`; add `--out-dir` to preserve a separate experiment. This skips the
Halo exporter and marks the scene `tst_export_pending=true`. It deliberately
leaves the previous JMS/cache untouched. Do not assume a successful preview
means those older game outputs contain the new design.

`inspect_layout.py`, run through Blender's `--background --python` command,
checks floor support, headroom and radial structure clearance at starts,
flags and teleporter exits. It produces a JSON review report in seconds.
Its 2.4 m by 0.4 m envelope is a preview constraint; it does not simulate the
game's capsule or include swapped tree/rock collision.

Preview materials are not proof of runtime shading. Keep preview-only lighting,
scenery and helpers in separate non-exported collections. At milestones, export
and test in the game: collision, scoring, networking and performance are only
validated there.

For installed-game rocks/trees and a cyborg scale reference, use the
[MJOLNIR Blender add-on](../tools/blender/mjolnir_level/README.md#native-scenery-in-the-tst-design-preview).
It loads native mesh geometry into a local cache, and the TST helper assembles
trees using the runtime recipes. The same add-on assigns **PCG surface permissions**
to selected faces: ground scatter, cliff dressing, both or neither. Export the
`.surfaces.json` alongside the geometry. A rock-looking material does not have
to receive cliff dressing. Keep authored entrances and ledges explicitly clear,
and use the `pcg` review view to inspect the permissions. They feed the existing
scatter stage; Blender does not execute Unreal PCG graphs.

Choose one authoring workflow:

- **Reproducible:** edit `build_geometry.py`, then regenerate. This overwrites
  generated `.blend`, JMS and placement files.
- **Hand-edited:** save a separate Blender working copy, preserve the exporter
  conventions, export JMS to the expected source path, edit placements, and run
  `rebuild.ps1 -SkipGeometry`. Do not accidentally regenerate over that work.

HEK geometry must have coherent normals, sealed boundaries and usable UVs.
Very small Boolean slivers can pass mesh topology checks and still fail HEK
lightmaps. Inspect the compiler's error geometry rather than ignoring the error.

### Preview the actual native grass and cliffs

For TST, run the complete local design loop from the repository root:

```powershell
pwsh -File levels/test/tst/preview-native.ps1 -RebuildGeometry
```

Set `-Conversion`, `-Paks`, `-BlenderExe` and `-Cyborg` to your local inputs.
Pass `-Cyborg ''` if no converted reference exists. Omit `-RebuildGeometry`
when reviewing hand edits to the current source. The script annotates the source
with non-mesh guides, then checks it, samples dressing and renders a separate
`.dream-loop/blender-preview/native-current/preview.blend`. It does not invoke
HEK, lightmap baking, cooking, the game or the hub. Logs identify a failed stage.

The adapter `tools/blender/export_scatter_source.py` reads the current Blender
triangles and PCG permissions. It feeds the same `scatter_foliage.py` sampler
used by the runtime upgrade, with the existing CE material specification and a
neutral, explicitly unbaked lightmap. This preview enables wild grass, short
groundcover, leafy weeds/clover/dandelions and cliff cladding; it does not claim
to preview every foliage rule.
TST uses grass at 0.42 times the default mesh scale and four times the placement
density. These settings live in `ce_upgrade_maps.json` as `foliage_scale` and
`foliage_density`, and the preview passes the matching `--rule-scale` and
`--rule-density` options. Change both when tuning this recipe. These are
per-map overrides; other maps keep their defaults.
`prepare_pcg_preview.py` extracts those meshes and textures from your installed
game. Geometry Nodes shares the meshes across thousands of instances and reads
the sampler's MJF3 positions, rotations and scales directly.
Those records are exact for this preview run. Selecting a subset of rules,
using current Blender triangles and omitting the baked landscape/lightmap can
produce different placements from a later full runtime build; this is not a
byte-for-byte preview of that future build.

The large surrounding formations are deliberate placements, separate from
surface cladding. `perimeter_dressing.py` generates `perimeter_dressing.json`;
the same file feeds the Blender preview and TST's runtime scenery swap through
`ce_upgrade_maps.json`. This makes a rock's intended transform inspectable and
reproducible. `inspect_native_decor.py` checks these render meshes against the
103 authored player envelopes, including the two roof ramps. Neither check validates Unreal collision shapes,
movement, vehicle physics or multiplayer balance.

The southern rock crown has explicit CLIFF face overrides: cladding is allowed
but grass is not, avoiding a continuous turf strip. Submerged pond faces use
NONE. Other cliff faces retain BOTH as their material default. Inspect the
`pcg.png` view or paint face overrides in the add-on to see this distinction.

Only LOD0 is displayed. Grass opacity uses the native packed texture's red
channel. Native mesh topology, texture images and placements are real game data;
Blender lighting, wind, layered materials and water are approximations. The
Desert/CliffFlat macro meshes use the authored coastal-granite preview material
instead of their Unreal layered shader. Source and placement hashes reject
stale preview manifests. Rebuild the local asset cache after game updates.

The recipe supports native `Lrg_A` tree assemblies, complete `Pine_Optimized`
and `Pine_Sapling_A` conifers, and an explicit `leaf_cluster_scale`. TST enlarges
the three basin trees' leaf clusters by 43% while preserving attachment
positions and pivots. Twenty-eight native conifers form eight small groups
behind the wall. Complete pine meshes use separate bark/needle material slots.
These settings affect the shared runtime recipe too. Background scenery
remains outside the playable enclosure.

Open `preview.blend` for a visual review and `tst.blend` for authoring. Keep the
entire `.dream-loop` cache and preview file out of the community source archive:
they contain extracted game content. Share the scripts, placement recipes,
authored geometry/textures, permissions and required asset paths instead.

TST additionally uses `foliage_cluster: {"grass": [12, 0.10, 0.60]}` and the matching
preview argument `--rule-cluster grass=12,0.10,0.60`. This creates deterministic
12 m density patches with smooth probabilistic edges between the two noise
thresholds. Other maps retain their default scatter rules. The Blender meadow
underlay and foliage shader colors are preview studies, separate from these
shared runtime placement settings.


## 5. Place objectives, equipment and lights

Red starts use team 0, blue team 1, and neutral starts -1. Place one flag per
team. Keep starts clear of walls and ceilings, with multiple escape directions.
Use unique teleporter channels; pair each sender with its receiver, and face
the arriving player away from obstructions or another sender boundary.
The TST balcony demonstrates a green walk-through shield: a render-only mesh
uses `example_tutorial_teleporter`, while separate scenario flags supply the
trigger and destination. Set `to_scenery: false` (or `scenery: false` for both
ends) to omit the stock floor pad where the doorway already supplies the visual.
For TST's 4.7 m wide doors, `shield_return: true` makes `prepare_runtime.py`
add two overlapping sender volumes beside the central one on the same channel.
This covers the whole doorway and raises the trigger to its 3.35 m height.
Keep the receiving position outside these volumes to avoid an immediate return.

Inspect light bitmaps before assigning UVs. `mp lights small strips` is a
1024x256 atlas of many fixtures, not a tileable strip. TST samples one capsule
at pixels (326,2)-(380,23), converts top-left image coordinates to Blender UVs,
and repeats separate quads along long lenses. Use the actual atlas in previews
so a flat emission color cannot conceal stretching or the wrong atlas region.

Place light fixtures as actual scenario objects. Colored trim identifies bases;
it does not replace readable interior lighting. Conversion with
`LIGHTMAP_ARGS=--placed-lights` includes fixtures in the light solve. Test final
interior illumination in game after the visual milestone.

TST's `objective_markers` specify the neutral ball and three moving hills.
`prepare_runtime.py` turns these into runtime labels. The rules, marker boundaries,
HUD and matching code-mod version must all agree before a mode is advertised.

## 6. Compile the CE cache

From the repository root in PowerShell 7:

```powershell
pwsh -File levels/test/tst/rebuild.ps1
# Or consume your hand-exported JMS and edited placements:
pwsh -File levels/test/tst/rebuild.ps1 -SkipGeometry
```

Override `-HekRoot`, `-BlenderExe`, `-PythonExe`, `-AddonRoot`, and `-MccTagsRoot`
for your machine. The add-on root ends in `io_scene_halo`.

The wrapper runs geometry export, Blender annotation, structure, scenario,
lightmaps and cache compilation. Read its logs under `.dream-loop/tst-rebuild/`.
It checks error text and fresh output timestamps because `tool.exe` can report
failure with exit code zero. Never continue with a stale map. It temporarily
moves `bitmaps.map` aside to embed lightmaps and restores it in `finally`.
The resulting cache is `<HEK>/maps/tst.map`.

## 7. Convert and upgrade a visual milestone

Build the helper executables listed in [the rebuild reference](pipeline_test_map.md#tools-and-rebuild).
From Git Bash, set explicit paths to this revision's tools:

```bash
export TST_REPO="$(pwd -W)"
export HCE_GAME="C:/Program Files (x86)/Steam/steamapps/common/Halo Campaign Evolved"
export HCE_PAKS="$HCE_GAME/Meteorite/Content/Paks"
export MJOLNIR="$TST_REPO/target/release/mjolnir.exe"
export MJOLNIR_DEBUG="$MJOLNIR"
export MJOLNIR_EXAMPLES="$TST_REPO/target/release/examples"
export EXAMPLES="$TST_REPO/target/debug/examples"
export HALO2UE_EXPORT="C:/your-tools/halo2ue-export.exe"
export PYTHONUTF8=1
export CE_COOK=1
export CE_SURFACE_LIBRARY="$TST_REPO/levels/test/tst/surfaces.json"
export LIGHTMAP_ARGS="--placed-lights"
export CE_START_LIFT=0.1
export TITLE="TST Proving Ground"

bash tools/level/convert_ce_map.sh C:/haloce/hek/maps/tst.map TST C:/haloce/ce_conversions/community/TST
python levels/test/tst/prepare_runtime.py --release-beta
python tools/level/upgrade_ce_map.py TST --release-beta --work C:/haloce/ce_conversions/community-upgrade
```

Change the TST conversion path in `ce_upgrade_maps.json` when using another
output directory, and pass `prepare_runtime.py --level` accordingly. Run one
editor/cook at a time and do not edit a running build script. The 0.1-CE-unit
spawn lift adds 30.48 cm; check ceiling clearance when changing it.

`CE_SURFACE_LIBRARY` is required for TST's authored architectural finish.
`surfaces.json` supplies the same albedo, roughness, tint and metal values to
Blender and the native cook. `architecture_surfaces.py` assigns real export
slots and writes fitted plate coordinates into UVMap. Omitting the library
uses the stock CE fallback tags and loses the material separation. The cook
owns these shaders under `/Game/MJOLNIR/Maps/TST/SurfaceMaterials`; it does not
require a private replacement for the shared CE runtime. Classic CE uses the
stock fallback materials; the authored PBR finish is a MJOLNIR build feature.

Conversion produces the collision/scenario, materials and meshes. Upgrade
adds the Landscape, scenery, swapped-object collision, foliage, water and world.
Keep all outputs from the same source build together. Watch for missing texture
or shader errors; a successful process exit alone is insufficient.

## 8. Install locally and playtest

Close the game, then use the same tool environment:

```bash
python tools/level/upgrade_ce_map.py TST --release-beta --stages install --local-install \
  --work C:/haloce/ce_conversions/community-upgrade
```

For the supported-mode beta, `--release-beta --local-install` preserves the
published loader and CE runtime. Install those dependencies from the launcher
first; testing with private copies of shared materials or scripts can hide
compatibility errors. Back up any prior local map before replacing it.

Candidate Oddball/KOTH development requires matching HUD scripts and compiled
variant files. Those experiments are separate from the supported-mode beta.

Launch through Steam, reach the main menu and host privately:

```text
mjolnir_auto host TST slayer private
```

Return to the menu before testing `team_slayer` and `ctf`. Test `oddball` and
`koth` only in a development build with their matching code mods. Use
[game automation](game_automation.md) for repeatable captures. Record the game
build, source revision, runtime/code-mod versions and hardware with your results.

| Test | Required evidence |
|---|---|
| Starts | Repeated spawn/death/respawn on both teams without trapping. |
| Slayer | Two players can damage each other, kills score and a round ends. |
| CTF | Both directions: pickup, drop, return, capture and scoring. |
| Oddball | Pickup, timed score, drop/death, abandoned-ball reset and round end. |
| Moving hill | Solo scoring, contested/empty pauses, rotation and round end. |
| Routes | Walk all three routes and each base exit; drive the vehicle route. |
| Collision | Players and bullets stop at expected structure, rock and trunk surfaces. |
| Visuals | Player-height exterior/interior captures; stable water, readable lighting, no seams. |
| Performance | Representative route and fight, with frame times; initial target 60 FPS. |
| Networking | Second machine joins and sees consistent objectives, scores and scenery. |

## 9. Package the first release

`pack_remastered.py` updates existing hub installations. For a new original map,
use `pack_local_map.py`, which reads conversion/upgrade outputs without a hub cache:

```powershell
python tools/level/pack_local_map.py TST `
  --work C:/haloce/ce_conversions/community-upgrade `
  --version 0.1.0-beta.1 --runtime '^1.13.0' `
  --slug tst-proving-ground --name 'TST Proving Ground' `
  --summary 'An editable community custom-map example.' `
  --readme levels/test/tst/BETA.md --size medium --players 2-8 --vehicles true `
  --out C:/haloce/ce_conversions/packages/tst-proving-ground-0.1.0-beta.1.mjolnir `
  --sign
```

The version/range are examples: use versions actually tested. `--cli` selects
your executable. A fresh staging folder is retained beside the archive, and
existing archives are not overwritten. Inspect the world, landscape, meshes,
textures, registration, level file, foliage, decals and referenced water state.

TST's `map_mesh_chunk: true` puts generated cliff, river, capture-bed and shadow
meshes under `/Game/MJOLNIR/Maps/TST/Generated` in its own map chunk. Their unique
package paths prevent an older shared runtime mesh from overriding them. Verify
these paths in the packaged containers, not just the editor scene.

Before packaging water, host the map, wait for `flux: river filled`, then run
`mjolnir_flux_bake`. Close the game and rerun `--release-beta --stages assemble`
with the same work directory. This copies the settled state into the build.
Reinstall and verify that the river starts full. Rebake after changing the bed;
matching domain dimensions alone do not prove an old water state is still valid.

The beta advertises only Slayer, Team Slayer and CTF. Additional objective modes
need published, tested rules, loader and HUD support before advertising them.

The hub requires an author signature. Register a device key through the supported
publishing/signing workflow, then add `--sign` to the final packaging command.
Keep private keys out of source and do not alter an archive after signing.
See [map distribution](map_distribution.md) and [archive format](mjolnir_format.md).

## 10. Upload to the hub and verify player installation

Use an authenticated publishing client/API with `mods:write`. This revision's
route prefix is `/api/v1`; do not assume every tag-editor build has a map-upload
button. Check the deployed API's current limits and response schemas.

1. Create a draft with `POST /mods`, supplying `slug`, `name`, `summary`,
   `description_md`, and `category`. Link the exact source revision and guide.
   Reuse an existing listing's slug for an update.
2. Create a release with `POST /mods/{slug}/releases`, supplying a new `version`,
   `channel` (`beta` for playtests), and `changelog_md`. Save the returned ID.
3. Upload the signed archive as raw bytes to `PUT /releases/{id}/archive`.
   This source revision accepts up to 90 MiB in one request. Larger files use
   the multipart routes in `hub/src/lib/api/publish.ts`, with a 400 MiB total cap.
4. Call `POST /releases/{id}/complete`. Read scan findings and status. A successful
   upload is not proof that the release was published.
5. Fix rejected packages, rebuild and re-sign. Some releases require moderator
   review; do not announce them as public while pending.
6. Install from the published listing on a clean player setup. Confirm dependency
   installation, registration, menu visibility, hosting and another player's join.

Release the editable source separately: Blender, JMS, scenario, placements,
scripts, configuration, tool versions, provenance, license/notices and exact
revision. Players need the runtime package; authors need the source and tools.
Publish a new version for fixes so players can identify the build they have.

## Troubleshooting

| Symptom | First check |
|---|---|
| Hand edits disappeared | Regeneration overwrote generated files; use a separate hand-edited scene and `-SkipGeometry`. |
| HEK lightmap failure | Error geometry, thin Boolean slivers and UV degeneracy; do not reuse the old cache. |
| Scene looks right but collision is wrong | Confirm the collision/BSP and visuals came from the same source build. |
| Only the author can load the map | Inspect package-owned meshes, dependencies and a clean launcher installation. |
| Foliage is washed out under atmospheric sky | Physical sky captures already include sun radiance; do not amplify the capture twice. |
| Objectives appear but do not score | Matching labels, required variant files, code-mod version and active game type. |
| Upload completed but map is not public | Read scan/review status and resolve the reported findings. |


### Native rock material variants

TST's `native_rock_materials` build option preserves the shipped native material
instance, including its compiled layer data, then applies the map's roughness and
coastal color parameters. Build the helper with
`cargo build -p blam-pack --example native_material_clone` before the upgrade bake.
The bake emits `pakchunk970-MJOLNIRROCK-TST_P`; the local installer and packer
require it when that option is enabled. Plain editor-created children of the
placeholder native materials lost the real layer data and rendered black or
white in game; a successful editor cook alone did not catch that failure.
Native game assets remain an installed build dependency, not editable source
files redistributed in this repository.

The TST beta also bakes an ambient cubemap into its world (`MJ_AMBIENT_CUBEMAP` in
`build_ce_landscape.py`). This supplies stable indirect fill with the published loader,
whose realtime sky capture is disabled in the game. The beta disables the runtime
skylight contribution to avoid double lighting; the original CE sky remains visible.
