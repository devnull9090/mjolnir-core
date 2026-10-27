# Enclosed lower facility: authoring notes

The facility implements the approved [indoor-only concept](facility-concept-v3-indoor.png)
and [design brief](facility-concept.json) in editable Blender source. The R18
interior art review reached 8.0/10; [actual renders and review notes](review/facility-art-review.md)
record the result and remaining differences. It has not been exported to JMS,
baked with HEK, tested in game, or published as a new hub package.

## Layout and source ownership

[`facility_architecture.py`](../facility_architecture.py) joins the lower room
envelope to the existing northern structure, then cuts its connected air space.
This opens the original lower tower cores as well as the new shell. All script
coordinates below are metres; +Y points behind the arena-facing wall. Stored
Blender coordinates use CE units, with 3.048 metres per Blender unit.

| Element | Authored dimensions |
| --- | --- |
| Structural envelope | x=-53.5..53.5, y=24.6..55.5, z=-0.6..6.35. |
| Existing balcony | Underside z=6.45; walking deck z=7.2. |
| Arena boundary | Original terrain boundary remains y=40. The enclosed indoor air extension reaches y=55 inside the facility shell. |
| Mirrored entrances | Centres x=-48/+48; approximately 7.11m clear at the floor and 8.8m above the lower chamfers. Top z=4.50 gives 4.20m maximum clearance above the floor. |
| Central foyer | x=-8..8, y=33..47; floor z=0.30 and ceiling z=4.01, giving 3.71m clear height. |
| Diverging branches | Four mirrored passage runs around two solid structural wedges. Their cross-section spans 5.2m at mid-height and 4.5m at the floor before fitted ribs. |
| Branch ribs | Six real chamfered arches per passage, with a 4.3m opening at the floor. |
| Enclosed cross-passages | x=37.4..52.5 and its mirror, y=26..54.5. Lateral turns connect each pair of branches to an arena entrance. |
| Blind end caps | x=43.8..44.6 and its mirror, closing the view along branches centred at y=28.5 and y=51.5. Players turn sideways before the caps. |

The interior extends behind the existing retaining wall to give the ribbed
passages real depth. A central foyer splits into two routes around each
roof-connected wedge. Both routes reach the same enclosed cross-passage on
their team's side. The visible end faces are solid walls; the traversable
connection turns before them. This makes a substantial interior facility
without adding another outdoor section.

Each blind end is a closed corner assembly: one continuous inset contour
wraps across a sidewall, short faceted corner, and cap. An 8cm border and
reveal surround broad mineral infill, replacing separate dark slots. From the
foyer the branch is seen obliquely, so the visible face wraps around this real corner.
It does not use a shifted false wall to imitate the concept's perspective.
The enclosed lateral turn stays open before the end assembly.

The original terrain air volume ends at y=40. Before subtracting the facility's
solid structure, the builder joins a second positive-air volume wholly inside
the new shell. Subtracting the shell leaves only the authored rooms and
passages. This is an enclosed BSP extension, not an enlarged outdoor boundary.

The **only outdoor connections are the two entrances on the same arena wall**.
The route is enclosed above, behind and at both ends. There is no rear exit,
additional outdoor section, courtyard or skylight. Interior turns break long
sightlines without ending the traversable route at a closed door.

[`facility_doors.py`](../facility_doors.py) builds eight decorative service
niches. Four face into the central foyer at x=-3/+3 on y=33 and y=47. Two sit
on the rear cross-passage walls at (-48,54.5)/(48,54.5); two sit on the outer
side walls at (-52.5,40)/(52.5,40). Each niche stops 0.45m behind its wall,
retaining at least 0.55m of backing at the outer envelope.

Their paired leaves, routed angular recesses and slim amber indicators are
sealed scenery. The surrounds reach z=3.45 and are 4.6m wide. The 10mm-deep
branch channels retain 25mm of solid backing in the 35mm fields. A shallow
shoulder recess transitions into the indicator. They have no usable doorway
or interaction; the route never passes through the decorative leaves.

Two angular branches in each upper and lower leaf converge into a continuous
vertical stem beneath the amber housing. These are closed, raised meshes
seated into matching shadow channels, with a 30% taper toward each junction.
One secondary angular wing per quadrant joins the outer fork and fills part
of the middle field. Its final 12cm tapers into the join; the added paths
increase contour length by about 42% without creating detached bracket loops.
The amber housing remains a slim vertical fitting, not a usable control.
Each connected relief branch seats 15mm into the field and rises 20mm above
it; visible strips are approximately 21–38mm wide. The tapered shoulder
pockets are 45% narrower than the initial design. The core mount is 22%
narrower, at about 265mm maximum width, while the lens, position and lighting
remain unchanged.

[`facility_edge_wear.py`](../facility_edge_wear.py) identifies actual generated
bevel faces on nearby ribs, coffers and foyer door surrounds. It divides the
same closed mesh at shared vertices and applies an existing darker finish to
varied 7.5–11cm sections. Each strip has three transverse lanes with angular,
tapered boundaries staggered by 1.2–2.8cm. Local splits preserve the original
patch coverage without extending cuts across entire objects. Main faces and the outer silhouette stay intact;
there are no overlapping decals, extra shells or displaced chips. Geometry
checks verify that this treatment preserves manifold solids.

The final fitted returns narrow the visible paired leaves to 3.3425m inside
the unchanged 4.6m assembly. The engraved fields scale with those leaves.
Seven closed return pieces bridge the transition to the existing surround;
the visible shadow jamb is 0.455m deep and its front remains behind the
surround face. The actual blind excavation stays 0.45m deep.

The collision structure is merged into the sealed BSP by
[`build_geometry.py`](../build_geometry.py). Precision finishes remain named,
editable render-detail meshes; hidden `SOURCE_` copies preserve construction
solids for study. Save hand experiments in a separate `.blend`: regeneration
replaces the generated source. `facility_service_` door objects use final world
coordinates with explicit wall-facing placement transforms.

## Terrain, PCG and local game assets

[`terrain_form.py`](../terrain_form.py) caps the terrain under the room at
z=0.18, below the structural floor. Its excavation fades from y=22 to the
facility footprint. Each entrance apron rises from z=-0.10 at y=22.1 to
z=0.30 at y=24.6. The buried lower toe joins the terrain without an exposed
vertical lip: the actual walking surface is the higher of the triangulated
terrain and the ramp. Geometry integration assigns `NONE` PCG permissions
inside the facility.

[`perimeter_dressing.py`](../perimeter_dressing.py) filters native rock
placements using transformed mesh bounds, including rotation and nonuniform
scale. Intersecting ledge/rubble instances are removed; oversized distant
backdrops move north enough to clear the enclosure. Stable IDs and the
`facility_excluded_ids` / `facility_relocated_backdrops` fields in the generated
JSON record these changes. Checking only object origins would miss the wide
cliff shelf meshes.

The source also moves teleporter channel 0's exit to (-12,21.5), two granite
boulders to (20,21)/(25,21), and the blue Warthog to (38,10), clear of the new
facility approach. Heights are regenerated from the same terrain function.
Other teleporter destinations remain as authored.

The native preview reads installed rock, grass, tree and cyborg assets into
local caches. The actual cyborg establishes scale; original texture masks
supply its olive reference colour and dark undersuit. CE teleporter effects
use their original dust/mask textures with a static additive approximation.
These preview shader studies do not reproduce every runtime effect.

Native mesh bounds are authoring metadata. Extracted game meshes/textures,
`.dream-loop` caches and the assembled `preview.blend` are local dependencies,
not community source assets to redistribute. Source hashes deliberately reject
stale native/PCG manifests after geometry or placement edits.

## Materials and lighting

[`surfaces.json`](../surfaces.json) retains the existing eight exterior roles
and adds four facility finishes: `facility_armor`, `facility_structure`,
`facility_recess` and `facility_floor`. These warmer, worn composite surfaces
use owned albedo, roughness and tangent-normal images. Fitted door fields and
narrow trim retain the established palette. All twelve roles use the same
source definitions and exported UVs in Blender and native material conversion.

The renderer guards the actual face assignments as well as these material
definitions. Legacy stock-material fallbacks could overwrite explicit authored
roles later in preview preparation. Those loops now skip authored faces;
`snapshot_authored_surfaces` and `assert_authored_surfaces` compare their roles,
source shader tags, topology and exported `UVMap` before the preview is saved.
The manifest records this check as `authored_surface_preservation`. Installed
stock/native approximation materials and hidden construction copies are outside
its scope.

The optional `normal_map`, `normal_convention` and `normal_strength` fields
describe tangent normals. The facility maps use OpenGL +Y, with strength 0.45
on walls/structure and 0.60 on floors. Blender reads them as Non-Color data;
Unreal imports normal compression and flips green once for its DirectX
convention. Strength blends from a flat tangent normal before normalization.
These are source material definitions, not evidence of a completed Unreal cook.

The broad facility armor, structure and recesses use metallic values 0.18,
0.10 and 0.25 respectively, giving them a diffuse mineral-composite response.
Door leaves, fitted inserts and exposed trim retain their metal response. The
facility floor uses sixteen varied 2m plates in an 8m repeat, with aligned
owned albedo, roughness and tangent-normal maps. Its 0.30 metallic value and
0.18–0.70 roughness range distinguish intact and irregularly abraded regions.
The exterior floor keeps its previous maps and settings.

Fitted ceiling borders are 11.5cm deep and stop before transverse ribs. Four
canted shoulder plates connect the central piers to the ceiling, above z=3.55.
Quiet chamfered fields fill the foyer walls beside the doors. A 25mm cyan floor
channel follows each battered pier toe and joins the branch traces with shared
mitered vertices, avoiding overlapping coplanar strips.

The external stock Blood Gulch light atlas is unchanged at 1024x256. Blue-white
lamps select pixels (326,2)..(380,23); amber service indicators select
(755,186)..(786,201). `light_atlas_pixels` controls each fixture's UV rectangle
and repeated capsule aspect ratio. The atlas is an installed-game dependency,
not an image bundled with this source.

[`amber_light.json`](../amber_light.json) defines the shared amber RGB
`[1.0, 0.28, 0.025]`, atlas selection and unique `tst_lights_amber!` material.
[`amber_light.py`](../amber_light.py) generates the map-owned
`levels/test/tst/shaders/tst_lights_amber.shader_environment`, retaining the
stock atlas as both base and self-illumination mask. Material color and the
constant primary on/off colors use that authored amber; secondary/plasma
channels remain black. The ordinary rebuild regenerates and reads back this
tag in the source tree, then stages it before structure compilation. Blender
uses the same tint and atlas red-channel mask. Both materials keep one-sided
faces; fixture validation checks winding against the room-facing direction.

Eight door-core lenses measure 0.05x0.455m, each with a 16.128W preview area light.
Eight additional physical jamb indicators have wall-attached housings and
0.06x0.65m lenses, each with a 10.08W preview area light. Both use emission strength
1.8 in Blender. They signal sealed service doors and have no interaction.
Four ceiling-attached wall washers illuminate the blind branch ends at
134.55W each; their housings stay above z=3.61. Visible downward fixtures use
authored spread angles to control floor illumination. There are no concealed
ceiling uplights.

Ten shallow ceiling fixtures add restrained warm-neutral light to the pier,
cross-beams and foyer walls: two at 1.8W, four at 2W and four at 12W. Their
housings attach to the roof and remain above approximately z=3.60. The actual
area-light centres account for the renderer's 25mm lens offset. Amber lenses
keep their saturated source tint; the explicitly separate `preview_spill_color`
uses softer reflected color `[1.0, 0.52, 0.22]` in the Blender lighting study.

Twenty-six existing long floor-strip lenses supply upward light at 6W per
metre: warm-neutral along the foyer edges and restrained cyan in the branches.
Each rectangular area light follows its strip's actual tangent and width.
This reveals the upper architecture through the authored lighting locations
without adding invisible ambient fill or raising exposure. The ten short
decorative pier-toe segments remain unpowered.

These are authored metre-space wattages; the renderer divides area-light power
by 3.048 squared for its CE-unit scene. Wattages, area-light spread, emission
strength, exposure and bounce lighting describe an **unbaked Blender study**.
The CE shader's radiosity power
is separately authored as 80; it is not a conversion of Blender watts. The
source floor palette uses the aligned roughness texture documented in
[the art provenance](README.md). Shared tint, atlas UVs and geometry are
exported source data; game lighting and visual testing remain later steps.

## Rebuild and review in Blender

From the repository root in PowerShell 7:

```powershell
& ./levels/test/tst/preview-native.ps1 `
  -RebuildGeometry `
  -Out '.dream-loop/blender-preview/facility-current' `
  -Views @('facility-red', 'facility-blue', 'facility-interior', 'facility-route', 'facility-door') `
  -Samples 64
```

This regenerates geometry with `--no-export`, annotates the source, runs the
layout/facility/native-clearance checks, refreshes native assets and PCG, then
renders the five views. It does not launch the game or run HEK. Omit
`-RebuildGeometry` to render an already generated source. Set `-BlenderExe`,
`-Conversion`, `-Paks`, `-Cyborg` and `-PythonExe` for another installation.

The source records `tst_export_pending`; its geometry is newer than the last
playable build. Open `levels/test/tst/tst.blend` for authoring, or the output
`preview.blend` for the local assembled study. The preview selects the interior
camera when requested; other named cameras remain available.

| View | Review purpose |
| --- | --- |
| `facility-red` / `facility-blue` | Mirrored entrances, approaches and relationship to the existing balcony/bases. |
| `facility-interior` | Central structural wedge, diverging ribbed passages and enclosed ceiling. |
| `facility-route` | Ribs, cross-passage turns and visible passage continuity. |
| `facility-door` | Blind recess depth, sealed leaves, routed detail and indicator UVs. |

## Validation status and limits

R18 passes the offline geometry and material checks with zero reported issues
for source SHA-256
`f403a49b17d3769fbf642ac6db5d3298285e9f4bf9beab3b9b99f79c732e0c51`.
Its full reports are local artifacts under
`.dream-loop/blender-preview/facility-r18/`. Geometry checks do not by themselves
establish visual approval or runtime correctness.
The portable [validation record](review/facility-validation.json) includes
the measured results, source/image hashes and owned-asset provenance.

| R18 check | Result |
| --- | --- |
| Main ceiling | 33 probes at z=4.01, confirming 3.71m clear height above the floor. |
| Branch widths | 24 cross-sections; minimum measured clear width **4.463m**. The fitted rib floor openings are 4.3m by design. |
| Turning bays | Four 2x2m areas sampled on a 10cm grid, 1,764 points total; level structural floor and 2.4m headroom checked. |
| Sampled walking routes | Both front/rear alternatives: **1,470 samples** using a 2.4m height / 0.4m radius envelope, plus approach continuity/slope checks. |
| Enclosure | 12 sealed-end checks, 1,416 boundary probes, 895 roof probes and 32 recorded air-side offsets for probes exactly on a wall. Exactly two arena-facing front openings. |
| Structure and materials | Zero non-manifold edges; PCG permissions and all **162** light fixtures' atlas UVs and face directions checked. |
| Authored native rocks | 121 native instances checked against 1,502 route/approach markers; zero overlapping candidates or reported issues. |
| Existing map | All 206 original layout samples pass. |
| Source integrity | Inspection leaves the source unchanged; all ten authored image files resolve with relative paths and remain unpacked. |
| Preview face preservation | 97,244 used authored faces checked; zero changes to roles, source shader tags, topology or exported UVs. |

Six headless Blender regression tests in
[`test_authored_preview_preservation.py`](../../../../tools/blender/test_authored_preview_preservation.py)
pass for the new guard. The shared material/normal and amber-shader suites add
thirteen passing focused tests. These test results do not replace fresh
geometry, render and source-hash checks after an art edit.

Thin render-detail floor inlays sit above a level collision floor; they do not
introduce a gameplay step. The turning-bay checks require the BSP
floor to stay horizontal, visible finishes to remain within 25mm of it, and
the 2.4m body/head clearance to stay open. A cosmetic bevel's tilted normal alone
does not fail that check.

For a new revision, rerun the checks and read its fresh reports; these results
apply only to the source hash above:

- `facility-check.json`: current source hash, sampled route and approach
  clearance, ramp continuity/slope, roof/rear/side enclosure, exactly two front
  openings, manifold structure, PCG permissions and per-fixture atlas UVs.
- `facility-native-clearance.json`: those route/approach markers against the
  locally installed authored native rock render meshes.
- `layout-check.json` / `native-clearance.json`: the original map's spawns,
  teleporters, balcony and base-roof routes.
- `preview-manifest.json`: camera positions, renderer, source provenance and
  texture/reference bindings. It records whether rendering left source intact,
  plus the authored face-assignment, topology and exported-UV preservation check.

[`inspect_facility.py`](../inspect_facility.py) can also run independently;
its compatible `checks` list feeds `tools/blender/inspect_native_decor.py`.
Inspect the reports rather than inferring success from a rendered image.

The native clearance check covers authored native rock render meshes, not all
runtime-generated cliff cladding or PCG instances. These offline checks also do
not reproduce Unreal's simplified collision, game lighting, multiplayer balance
or frame time. Review both entrance thresholds, every turn, door recesses and
material joins in Blender first. No JMS export, HEK bake or in-game validation
has been performed for this facility revision; those steps remain necessary
before a playable build or hub update.
