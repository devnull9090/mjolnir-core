# Enclosed lower facility: authoring notes

The facility implements the approved [indoor-only concept](facility-concept-v3-indoor.png)
and [design brief](facility-concept.json) in editable Blender source. The current
art pass is still being reviewed. It has not been exported to JMS, baked with
HEK, tested in game, or published as a new hub package.

## Layout and source ownership

[`facility_architecture.py`](../facility_architecture.py) joins the lower room
envelope to the existing northern structure, then cuts its connected air space.
This opens the original lower tower cores as well as the new shell. All script
coordinates below are metres; +Y points behind the arena-facing wall. Stored
Blender coordinates use CE units, with 3.048 metres per Blender unit.

| Element | Authored dimensions |
| --- | --- |
| Structural envelope | x=-53..53, y=24.6..39, z=-0.6..6.35. |
| Existing balcony | Underside z=6.45; walking deck z=7.2. |
| Arena boundary | Northern boundary remains y=40. |
| Mirrored entrances | Centres x=-48/+48; approximately 7.11m clear at the floor and 8.8m above the lower chamfers. Top z=4.50 gives 4.20m maximum clearance above the floor. |
| Main hall | x=-51.7..51.7, widest cross-section y=26.2..38.2: 12m overall. Floor z=0.30; ceiling z=4.01, giving 3.71m clear height. The entrance vestibules retain their taller crown. |
| Central piers | Two roof-connected piers at x=-6.44..-3 and x=3..6.44; footprint y=31.0..33.4, narrowing above the battered foot. |
| Central branches | About 4.21m of structural floor north and south of each pier, targeting more than 4m after trim. R9 measured clearance is recorded below. |
| Central cross-gate | Wing walls at x=-0.5..0.5 leave a 3.2m opening at y=30.6..33.8, joining the two halves of the facility indoors. |
| Mirrored turning bays | Checked 2x2m clear areas at x=-2.78..-0.78 / x=0.78..2.78, y=30.2..32.2, with 2m headroom. |

Mirrored bulkheads at x=-39/+39 and -26/+26 turn the route between the
vestibules and central junction. Repeated chamfered ribs and connected ceiling
beams continue through the passages. The split central piers and cross-gate
form a roof-connected junction with visible turns into the opposite wing.
The main interior's vertical design is compressed by 0.70 around the fixed
z=0.30 floor: `z_final = 0.30 + (z_authored - 0.30) * 0.70`. Main collision,
finishes and fixtures follow that transform once; the balcony and entrance
vestibules keep their existing dimensions.

The **only outdoor connections are the two entrances on the same arena wall**.
The route is enclosed above, behind and at both ends. There is no rear exit,
additional outdoor section, courtyard or skylight. Interior turns break long
sightlines without ending the traversable route at a closed door.

[`facility_doors.py`](../facility_doors.py) builds eight decorative service
niches. Six are on the rear wall at y=38.2, centred at x=-48, -18, -8.5, +8.5,
+18 and +48. Two face inward from y=26.2 at x=-8.5/+8.5. Each niche stops
0.45m behind its hall wall; the rear niches retain 0.35m of structural backing.
Their paired leaves, routed angular recesses and slim status indicators are
sealed scenery. The compressed outer surrounds reach z=3.45, remain 4.6m wide,
and fit below the new main ceiling. Two additional channel tiers sit inside
the original routing, cut 14mm and 10mm deep; their authored 4.5cm and 3.5cm
widths compress vertically with the leaf. A shallow 6mm inset transitions into
the amber indicator. Mirrored cuts retain at least 15mm of solid backing in
the 35mm fields; the compressed, beveled door mesh check reported no
non-manifold edges. They have no usable doorway or interaction.
The route passes around the piers and bulkheads and through the open central
gate, never through the decorative leaves.

The collision structure is merged into the sealed BSP by
[`build_geometry.py`](../build_geometry.py). Precision finishes remain named,
editable render-detail meshes; hidden `SOURCE_` copies preserve construction
solids for study. Save hand experiments in a separate `.blend`: regeneration
replaces the generated source. `facility_service_` door objects use final world
coordinates and are deliberately excluded from the hall's width remapping.

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

The facility uses the same eight architectural roles in
[`surfaces.json`](../surfaces.json): `armor`, `structure`, `recess`, `floor`,
`fitted_pale`, `fitted_inset`, `fitted_charcoal` and `edge`. Their authored
textures and exported UVs remain shared with the rest of the map.

The separate stock light atlas is 1024x256. Blue-white lamps select pixels
(326,2)..(380,23); service indicators select the gold region
(755,186)..(786,201). `light_atlas_pixels` controls each fixture's UV rectangle
and repeated capsule aspect ratio. The preview preserves that texture mapping;
it does not tint gold indicators through the generic cyan treatment.

Fixture metadata drives local Blender area lights, including warm sealed-door
spill and concealed ceiling uplights. This is an **unbaked lighting study**.
The service lamps retain their gold atlas crop; compressed lenses measure
0.05x0.455m and use 22.4W preview area lights.
The existing atlas UVs and architectural surfaces are real source data, but
Blender illumination is not evidence of runtime lighting parity. Game export,
lighting and visual testing remain later steps.

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
| `facility-interior` | Split piers, central cross-gate, generous branch silhouettes and enclosed ceiling. |
| `facility-route` | Ribs, alternating bends and visible passage continuity. |
| `facility-door` | Blind recess depth, sealed leaves, routed detail and indicator UVs. |

## Validation status and limits

The R9 offline geometry checks pass with zero reported issues for source SHA-256
`7da6af30266b33f54d2030fd0b71465bd3a2d900a2ab432629ad52e54bd0e62a`.
The reports are local artifacts under
`.dream-loop/blender-preview/facility-r9/`; render and art review remain in
progress, so these results do not establish visual approval.

| R9 check | Result |
| --- | --- |
| Main ceiling | 20 probes at z=4.01, confirming 3.71m clear height above the floor. |
| Central branches | 16 cross-sections; minimum clear width **4.162 m**, above the 4 m target. |
| Central gate | Five cross-sections; minimum clear width **3.196 m**, above the 3 m validation target. |
| Turning bays | Two 2x2m areas sampled on a 10cm grid, 441 points per side; level structural floor and 2m headroom checked. |
| Sampled walking route | 641 samples, plus approach continuity/slope and enclosure checks. |
| Enclosure | Roof, rear and side closure checked; exactly two arena-facing front openings. |
| Structure and materials | Zero non-manifold edges; PCG permissions and all 120 light fixtures' atlas UVs checked. |
| Authored native rocks | 121 native instances checked against 673 route/approach markers; zero overlapping candidates or reported issues. |
| Source integrity | The facility check left the source unchanged. |

The fine bevels on render-detail floor plates sit above a level collision floor;
they do not introduce a gameplay step. The turning-bay checks require the BSP
floor to stay horizontal, visible finishes to remain within 25mm of it, and
the body/head clearance to stay open. A cosmetic bevel's tilted normal alone
does not fail that check.

For a new revision, rerun the checks and read its fresh reports; the R9 results
apply only to the source hash above:

- `facility-check.json`: current source hash, sampled route and approach
  clearance, ramp continuity/slope, roof/rear/side enclosure, exactly two front
  openings, manifold structure, PCG permissions and per-fixture atlas UVs.
- `facility-native-clearance.json`: those route/approach markers against the
  locally installed authored native rock render meshes.
- `layout-check.json` / `native-clearance.json`: the original map's spawns,
  teleporters, balcony and base-roof routes.
- `preview-manifest.json`: camera positions, renderer, source provenance and
  texture/reference bindings. It records whether rendering left source intact.

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
