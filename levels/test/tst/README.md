# TST Proving Ground source

Start with [the complete authoring walkthrough](../../../docs/custom_map_walkthrough.md).
The [design brief](DESIGN.md) records the intended layout and acceptance criteria.

Open `tst.blend` to inspect the authored terrain and base geometry. Read its
embedded `README - TST AUTHORING` text and enable the named guide collections to see
gameplay placements. Guides are annotations, not rendered or collision geometry.
The source keeps stock game content external. A separate preview can load actual
native scenery with the [MJOLNIR Blender add-on](../../../tools/blender/mjolnir_level/README.md),
using runtime tree/rock recipes and local textures. Unreal material graphs and
wind remain approximate in Blender.

`build_geometry.py`, `terrain_form.py`, `perimeter_architecture.py`,
`facility_architecture.py`, `facility_doors.py` and `facility_edge_wear.py` are the
reproducible geometry source. The current design is an enclosed basin: three
continuous cliff sides and a full-length northern wall with a 7.2 m balcony.
Channels 2 and 3 reach sheltered balcony arrivals; channels 4 and 5 return
through green shield doorways. Ground landing points are separated from the
senders to prevent immediate return trips. The former blocky stepped exits
have been removed and their parapet gaps closed; use the return shields to descend.
The balcony floor extends from y=21.8 to 34.7 m. Projecting towers contain
5.2 m wide, 3.7 m high transverse passages; an outer walk connects the bays.

The [lower facility authoring notes](art/facility-build.md) cover the new
indoor-only connection beneath that balcony, its mirrored front entrances,
sealed decorative doors, terrain excavation and native-rock exclusions. This
facility pass is being reviewed in Blender with `--no-export`; it has not yet
been baked or tested in game. Its fixed views are `facility-red`,
`facility-blue`, `facility-interior`, `facility-route` and `facility-door`.

Light lenses use the Blood Gulch `mp lights small strips` atlas. The UVs select
one capsule at pixels (326,2)-(380,23) on the 1024x256 sheet. Long fixtures are
split into repeated capsules to retain their proportions. The Blender preview
uses this same texture and UVs instead of hiding them under a flat glow.
The sealed facility doors use the separate gold atlas crop with the map-owned
amber shader defined by `amber_light.json`; the stock atlas remains external.
The doorway surfaces use the stock tutorial teleporter shader, which layers
the original CE teleporter shield dust and mask textures. They are render-only;
scenario sender/receiver flags supply the actual teleport behavior.
Continuous irregular talus joins the rock formations below the wall, with
protected saddles around gameplay markers and former terrace locations. The
pond has an authored shallow shelf and earth bank; these are source terrain, not decorative overlays.
Running `rebuild.ps1`
regenerates the Blender scene, JMS and placements, then compiles the CE cache.
It overwrites hand edits to those generated files. For hand editing, save a
separate Blender copy, export JMS, and use `rebuild.ps1 -SkipGeometry`.
`build_scenario.py` places gameplay objects from `placements.json`.
`prepare_runtime.py` adds the objective markers and compiles the candidate modes
after CE conversion and before the visual upgrade.

`tst.surfaces.json` stores PCG permissions independently of CE materials.
The generator writes ground/both/none defaults; the add-on can paint face
overrides in a hand-edited scene. Render `--views pcg` to inspect the permissions.
See the add-on guide for exporting overrides and loading a cyborg reference.

For fast structural checks, run Blender without HEK or Unreal:

```powershell
& 'C:/Program Files/Blender Foundation/Blender 5.1/blender.exe' `
  --background --factory-startup --python-exit-code 1 `
  --python levels/test/tst/inspect_layout.py
```

It checks floor support, a 2.4 m headroom envelope and 0.4 m radial clearance
at starts, flags, teleporter endpoints and balcony samples. It
also casts 360 horizontal rays at 9 m to check enclosure without PCG. Inspect
the JSON report in `.dream-loop/blender-preview/`. Regenerate the report after
any geometry revision. This is an authored-structure check, not certification
of scenery/game collision.

For repeatable visual reviews, render the fixed cameras:

```powershell
& 'C:/Program Files/Blender Foundation/Blender 5.1/blender.exe' `
  --background --factory-startup --python-exit-code 1 `
  --python levels/test/tst/render_preview.py -- `
  --staging C:/haloce/ce_conversions/community/TST/staging `
  --alloy-albedo levels/test/tst/art/textures/forerunner_titanium_albedo.png `
  --floor-albedo levels/test/tst/art/textures/forerunner_floor_albedo.png `
  --cliff-albedo levels/test/tst/art/textures/coastal_granite_lichen_albedo.png `
  --views exterior topdown side wall balcony red-interior blue-interior layout
```

This example selects eight overview views. Without `--views`, the renderer
renders every named view except `pcg`, including facility and detail cameras.
Use `--views wall balcony` for the northern structure or
`--views red-interior side` for a focused check. The initial
1600-by-900 Cycles pass at 64 samples took about 87 seconds on CPU. Automatic
OptiX selection on the development RTX 5090 reduced individual views to a few
seconds. The manifest records the selected device; use `--device cpu` when
needed. Times depend on hardware. The command writes renders, `preview.blend`
and a provenance manifest under `.dream-loop/blender-preview/`, without changing
the source or exporting the map. Omit `--staging` to use explicit scenery bounds
instead of locally extracted CE reference models. These references differ from
the final runtime scenery replacements.

Regenerate geometry for a visual iteration with `build_geometry.py -- --no-export`.
Use `--out-dir` to keep an experiment separate. This skips JMS and marks the
Blender scene's `tst_export_pending` property: the current preview can be newer
than the last game build. Run the full rebuild only at a visual milestone.

### Full native preview loop

Run `pwsh -File levels/test/tst/preview-native.ps1 -RebuildGeometry` for current
source geometry, clearance checks, native tree/rock assemblies, actual PCG grass,
groundcover, weeds and cliff cladding, and fixed-camera renders. Omit `-RebuildGeometry` to preserve
hand edits. See the [walkthrough](../../../docs/custom_map_walkthrough.md#preview-the-actual-native-grass-and-cliffs)
for local path overrides and provenance limits. No HEK bake or game launch runs.

`perimeter_dressing.py` produces the native macro-rock placement recipe used by
both preview and runtime upgrade. `preview_surface_detail.py` supplies the
isolated ground/water material study; `render_preview.py` copies the scene and
adds its lights. These preview shaders are not exported. The `native-current`
output folder contains `preview.blend`, images, logs, source hashes and both
structure/native-rock clearance reports.

Include `facility-panel-bays` in the preview's `-Views` to automatically check
the player view where a hall panel previously appeared behind an illuminated
support. To run the check independently on such an assembled preview:

```powershell
& 'C:/Program Files/Blender Foundation/Blender 5.1/blender.exe' `
  --background --factory-startup --python-exit-code 1 `
  --python levels/test/tst/inspect_panel_perspective.py -- `
  --blend .dream-loop/blender-preview/native-current/preview.blend `
  --out .dream-loop/blender-preview/native-current/panel-perspective-check.json
```

The inspector rejects a moved reference camera or support and fails if its
annotated sightline hits a branch panel between the support and the structural
wall. It reports the ray hits and source hash without saving the preview. This
checks one Blender viewpoint; inspect the other turns and test the cooked game
separately.

### Forerunner architecture study

The [reference research and exact imagegen prompts](art/forerunner-pass.md)
document the balcony art pass. `perimeter_architecture.py` models the nested
passage arches, segmented rail cladding, floor borders, tower inlays and
teleporter armor. The source Blender file groups the fine parts under
`DETAIL - Forerunner precision armor (render only)`; they are individually
editable meshes with explicit NONE PCG policy and render-only `!` shader slots.
The sealed underlying shell supplies collision. This avoids forcing small
armor bevels through the collision boundary's coarser welding tolerance.

The source uses generated titanium/patina and floor-plate albedos, image-driven
roughness, and optional tangent normals. `surfaces.json` feeds both Blender and
native material authoring: eight established exterior finishes plus four worn
facility finishes. Stock light-atlas UVs remain in the correct capsule regions.
The new facility remains export-pending until a game integration pass; its
Blender lighting study does not establish runtime collision or lighting parity.

The renderer also checks the used faces, not just the material library. Earlier
stock-material fallback loops could overwrite explicit authored assignments.
They now skip those faces, and a snapshot/assert check rejects changes to their
surface roles, source shader tags, topology or exported `UVMap` before saving
the preview. Six headless Blender regression tests cover this guard; the
material/normal and amber-shader suites add thirteen focused tests.

Hero armor uses a generated fitted-plate image mapped once per part through
the exported `UVMap`, with separate pale, inset and charcoal finishes.
Plate orientation and small reflectance variations prevent identical wear on
every piece. Structural finishes use tiled images; the facility adds worn
mineral relief and sixteen varied floor plates. Separate Non-Color images
control roughness and tangent normals. These maps and their exact prompts
are in `art/`.

The tower and jamb engravings are shallow cuts in closed detail meshes;
the floor's paired inlays sit only millimetres above the walking surface.
The geometry builder checks every beveled detail mesh for manifoldness before
saving. Keep these precision pieces separate from the coarsely welded collision
shell when experimenting with the source.

The native preview also runs `inspect_architecture.py`: it reflects the finished
tower panels about their shared centerline and checks complete native field-tree
canopy bounds against the balcony front edge. The `tower-elevation` camera gives
an orthographic view for checking panel symmetry without perspective distortion.
The passage ribs track the structural core's taper so it cannot poke out beside
the entrance trim. `art/review/forerunner-validation.json` records the earlier
balcony pass; the latest facility results and actual renders are linked from
[the facility review](art/review/facility-art-review.md).

Both roof ramps end in a four-metre level landing at the inset roof's 6.40 m
height, with an open connection through the roof rim. Landing samples check
horizontal normals and flush elevation. Railing module bounds are also checked
against the central support bays to prevent intersecting caps and panel ends.
See [the roof-access and railing pass](art/roof-access-and-rail-pass.md) for the
imagegen study, implemented design, and close-up Blender renders.

## Asset provenance

| Source | Use |
|---|---|
| This project's `build_geometry.py` | Original terrain, playable air shell, bases, architectural trim, central platform, UV layout and placement design. |
| Classic HEK / installed HCEEK tags | Named ground, cliff and metal shaders; stock CE scenery, light fixtures, equipment, vehicle and teleporter dependencies. Paths remain in the scripts and placements. |
| User's installed Campaign Evolved data | B30 tree parts and leaves, rock/foliage meshes, material surfaces, effects, weapons and vehicles referenced by the upgrade. |
| MJOLNIR source | Conversion, collision, rendering, packaging, gameplay rules and HUD code. |
| Generated visual studies and owned surface maps | See [art provenance](art/README.md). Selected maps feed the shared architectural palette; unselected studies remain references. The new facility's source materials still require a native cook and in-game validation. |

Do not bundle installed editing kits, game archives, or extracted stock assets
into a source download. Keep their references and document the required local
inputs. The repository's license governs repository code; it does not grant
rights to stock game content. Preserve its license and notices when sharing.

The runtime `.mjolnir` package and source download serve different audiences.
Players install the runtime through the launcher. Authors need this source
folder, the matching repository revision, toolchain, and their local game data.
Record that revision, tool versions, and the actual playtest results alongside
each source release. See the walkthrough's release checklist before uploading.
