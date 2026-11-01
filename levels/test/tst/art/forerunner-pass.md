# Forerunner architecture pass — 20 October 2026

User scope: research references, then improve the existing map through image generation and Blender renders. No game launch, game bake, install or upload in this pass.

## Reviewed Blender result

Latest follow-up: [R16 roof-access and railing correction](roof-access-and-rail-pass.md).
The shared `review/` images and validation report show the latest correction;
the R14 score and R15 notes below document those earlier milestones.

The R14 dream-loop review scored the preceding result **8.0/10** against the generated
target. Shape, lighting and material gates passed; remaining polish differences
include more readable localized wear, clearer tower engraving separation, and a
stronger left floor-route detour. See [the full review](review/forerunner-art-review.md).

The R15 source retained fitted angular portal plates, deeply recessed shoulder lamps,
three nested ribs through each tower passage, shallow paired tower engravings,
segmented parapet armor, and fine double floor routes. The stock segmented light
atlas UVs and green walk-through portal reference remain intact. Imagegen supplied
the fixed-camera target and metal/floor surface images; the visible architectural
depth is editable mesh geometry, not a generated image painted over the render.

- [Actual balcony render](review/forerunner-balcony.png)
- [Full arena](review/forerunner-exterior.png)
- [Wall](review/forerunner-wall.png), [portal](review/forerunner-portal.png),
  [tower passage](review/forerunner-tower-passage.png), [top-down](review/forerunner-topdown.png)
- [Straight-on tower elevation](review/forerunner-tower-elevation.png)
- [Machine-readable validation](review/forerunner-validation.json)

R15 corrects the user's three annotated issues: all tower panel profiles and
beacons share one mirror axis; passage ribs follow the real core taper and cover
the exposed front return; the field tree moves from (-24, 23) to (-24, 12) metres.
The full field-tree canopy now clears the balcony metalwork by at least 1.514 m
using conservative mesh bounds. Reflection testing on 4,044 tower vertices finds
a maximum surface discrepancy of 0.504 mm after beveling. `inspect_architecture.py`
runs automatically at the end of `preview-native.ps1` to catch these regressions.
The R15 corrections were checked in seven rendered views; the R14 art score above
is historical, not a new numerical review of these fixes.

Validation: 445 closed precision-detail meshes (51,904 triangles), 14 parts with
verified recessed faces, 71 light fixtures / 223 faces checked against the correct
atlas region, and 170 sampled route clearances without issues. All 360 boundary
ray directions hit enclosure geometry at the checked height. These are offline
geometry checks, not multiplayer playtesting or engine collision validation.

The 1672 x 941 Cycles renders use 96 samples on the local RTX 5090. Per-view
timings are recorded in the validation JSON, excluding scene preparation. This is offline render time,
not gameplay FPS. The preview preserved the source file's hash.

Editable source: `../tst.blend`, `../perimeter_architecture.py`, and the generated
images below. Reproduce the complete local preview with `../preview-native.ps1`;
the reviewed scene is `.dream-loop/blender-preview/forerunner-r15/preview.blend`
relative to the repository root. Installed game assets remain local dependencies.
Generated material graphs and new geometry still need runtime integration and
export validation when an in-game pass is requested.

## Reference research

- [Rogelio Olguin, Forerunner environment-content team](https://rogelio.artstation.com/blog/bRW0/halo-infinite-ect-hard-surface-part-1-forerunner): modular construction and careful texture placement support the classic Halo direction.
- [John Flath, architectural landmarks](https://johnflath.artstation.com/projects/d0LA2Q): landmark construction, tonal shifts and restrained metal accents.
- [Official Halo interior concept](https://www.halowaypoint.com/news/inside-infinite-march-2021): visually inspected the linked interior image. Tall faceted silhouettes, nested polygonal frames, deep reveals, broad quiet plates, sparse geometric channels and small cyan accents.
- [Official exterior concept](https://content.halocdn.com/media/Default/community/CANON_FODDER_Franchise/hd_haloinfinite_conceptart_025-c9794675d0f04914a72b696a51e790cb.jpg): visually inspected the image. Long tapered silhouettes and sparse energy accents carry the scale; detail concentrates at joints rather than filling every face.

These are design references only. No web artwork is bundled as a map texture or model.

## Design translation

Preserve the expanded balcony, tower passages, enclosed arena and native scenery. Model nested passage ribs, layered teleporter housing, large inset parapet panels and tower-side armor. Keep the 2.4 m player envelope clear. Replace the porous concrete appearance with satin titanium, and reserve patterned floor plates for walking surfaces.

Actual source geometry lives in perimeter_architecture.py and is rebuilt into tst.blend. Existing CE shader assignments remain; the new alloy and physical metal shader are Blender material studies pending a later runtime-material integration pass.

Precision armor is separated into the named DETAIL collection, with render-only (!) versions of the existing shader names and explicit NONE PCG policy. The sealed BSP provides collision underneath. Source rebuild checks manifoldness; layout checks verify headroom, clearance and a continuous 7.2 m balcony floor. Export and in-game validation of this new detail layer remain pending by user request.

## Generated assets

Built-in image_gen tool, not CLI/API fallback.

- textures/forerunner_fitted_plate_albedo.png — one plate's fine metal abrasion with localized edge wear. The preview maps this once per fitted armor part using a separate `PREVIEW fitted plate UV` set. Stock CE UVs are retained. Pale, inset and charcoal finishes share the image with different reflectance values. This is a structural material change from repeating mineral-like patina; no lighting is baked into the image intentionally.

### Fitted plate prompt

Use case: photorealistic-natural. Asset type: game diffuse albedo texture for ONE fitted square titanium armor plate, not a beauty render. Flat orthographic front-on, edge to edge square panel. Halo-inspired ancient precision-machined alloy with a very clear metallic surface character: dark neutral gunmetal gray, subtle directional hairline abrasion, fine silver scratches, sparse small worn silver chips concentrated within 1 percent of the four outer edges. Central 85 percent stays calm, with only very faint directional brushing, a few fine diagonal rubbed scratches and subtle gray tonal variation. Tiny chipped patches along edges should be irregular and discontinuous, never a solid white border. No broad cloudy patterns, no mineral veins, no pores, no stone or concrete. The entire image is one planar surface with no bolts, no grooves, no inset panel outlines, no circuitry and no symbols. Uniform diffuse illumination with NO baked highlights, shadows, bevel shading, vignette or perspective. Medium-dark steel gray average sRGB 110, fine pale metallic abrasion may reach sRGB 165. Square texture. This will be UV mapped once onto a real modeled plate whose geometry supplies the chamfers, so do not draw any 3D panel construction.

- textures/forerunner_titanium_roughness.png — a separate generated grayscale micro-abrasion study, loaded as Non-Color data and remapped to satin roughness. Also supplies an estimated submillimetre bump; it is not a measured normal map. The albedos are still separate assets.

### Roughness prompt

Use case: photorealistic-natural. Asset type: seamless material roughness map, grayscale, for ancient precision-machined satin titanium in a Halo-inspired Forerunner structure. Flat orthographic image, texture only, no object outline. A quiet neutral midgray field (roughly RGB 115) with fine irregular abrasion, numerous extremely thin sparse hairline scratches, a few softly scuffed patches (RGB 140) and narrow polished scratches (RGB 80). Visually like the microsurface of a maintained brushed titanium plate, not cloudy concrete, stone or mineral veins. Scratches mostly short, 1–5 percent image width, crossing at restrained angles; variation in the quieter field is extremely subtle. No black or white regions, no broad directional light gradients, no baked shadows, no specular highlights, no panel lines, no borders, no symbols or text. Seamless across both axes. This is a linear roughness-data image with a narrow grayscale range 80–145, not a beauty photograph. Square 1024 texture.

- textures/forerunner_floor_albedo.png — broad quiet plate layout replacing the circuit-heavy floor study in the preview. Old source texture retained.

### Floor prompt

Use case: photorealistic-natural. Asset type: seamless PBR diffuse albedo for a six metre square floor tile in a Forerunner science-fiction structure.
Perfectly flat orthographic texture, four large square satin titanium floor plates in a precise 2 by 2 grid. Thin straight charcoal assembly seams, about 2 cm at actual scale, no beveled shading. Plates subtly differ in neutral gray value, with quiet warm-gray wear and fine scuff scratches. Fine brushed metal with a few restrained cloudy oxidation patches. Medium gunmetal gray, sRGB average 130, subtle 110-150 plate variation. No circuitry, no bolts, no symbols, no ornament, no geometric engraving, no small repeating panels, no text. Uniform diffuse light: no highlights, shadow gradients or vignette. Seamless repeat on all four edges, outer seams half width so adjacent tiles join correctly. Square image, game texture.

- textures/forerunner_titanium_worn_albedo.png — intermediate richer patina variant. The final direction returns to the quiet original on structural metal and uses the fitted-plate image on hero armor; the broad mottling in this variant read too much like stone.

### Worn variant prompt

Use case: photorealistic-natural. Asset type: seamless diffuse albedo texture for a 2 x 2 metre patch of ancient Forerunner titanium armor. Orthographic front-on flat texture, no object outline. Mid-gray satin titanium, with visible irregular mineral oxidation stains ranging from 5 to 25 cm, warm gray nickel and darker graphite patches, restrained pale abrasion scratches around 1 mm wide, subtle directional metal grain. Variation is visibly richer than uniform brushed metal, but clean engineered metal not concrete, stone, marble or corroded rust. Diffuse texture only: uniformly lit, no cast shadows, no specular highlights, no bevels, no bolts, no seams, no panels, no symbols, no text, no vignette. Slight pale scuffed clusters occupy about 15 percent of the surface; quiet broad areas occupy 60 percent. Overall middle grey sRGB average 145, range mostly 110–180. Tile seamlessly both axes. Realistic game texture with fine convincing wear, not white speckled noise. Square.

- reference/forerunner_balcony_target.png — edit of the current balcony-final/balcony.png. This is a target image, NOT a Blender render.
- textures/forerunner_titanium_albedo.png — newly generated metal microstructure; base color only, no authored normal/roughness map. Seamlessness was requested but is not a certified texture property.

### Target prompt

Use case: precise-object-edit. Asset type: in-engine screenshot target for a real Blender map upgrade.
Edit target: attached current Blender balcony render. Keep exactly the camera, perspective, balcony width and floor elevation, five-tower wall layout, green walk-through teleporter at left, clear tower passage in center, right-hand guardrail, tree positions, cliffs, daylight and sky. Do not change map layout or invent new buildings.
Upgrade only this existing Forerunner architecture using Halo CE / Halo Infinite classic design language: monumental clean gunmetal and warm titanium armor, large precise chamfers, nested six-sided frames, recessed dark channels, sparse geometric circuit engravings, stepped collars and a few restrained pale cyan lights. Replace the pale rough concrete appearance on portal and rail with satin brushed weathered titanium. Portal housing should have layered dark and silver beveled frames and purposeful recessed panels, preserving green energy. The rectangular tower opening becomes a broad chamfered hexagonal passage with three nested metal arch ribs, a defined lit soffit and recessed wall panels, keeping human walkable space open. Guardrail has deep large segmented geometric inset panels and a dark beveled cap with small spaced cyan markers. Floor has deliberate large plate scale and a narrow inset border band, no repeating decorative clutter. Tall tower face includes a giant recessed angular panel with dark boundary and a slender central cyan light, rather than an empty tiled slab. Introduce 3D construction depth, with material variation subordinate to large silhouettes.
Photorealistic high quality in-engine screenshot achievable in Blender, same bright coastal daylight and exposure, subtle edge wear, precise metal reflectance. No grain, no wet glossy floor, no excessive greebles, no gold ornaments, no text, no HUD. Preserve every major object and framing. Landscape 16:9.

### Albedo prompt

Use case: photorealistic-natural. Asset type: seamless PBR base-color texture for modeled Halo-inspired Forerunner titanium armor in Blender.
Create a square seamless tile of weathered warm-gray titanium alloy, viewed perfectly orthographically flat, edge to edge. Neutral middle-light gunmetal grey, very subtle cloudy oxidation and fine directional brushed metal grain, occasional restrained hairline scratches. Uniform diffuse flat illumination, NO highlights, no ambient shadow, no shading gradients. This is only metal surface microstructure, geometry supplies all panels and chamfers. No panel seams, no bolts, no borders, no sci-fi greebles, no symbols, no baked bevels, no concrete pores, no cracks, no rust flakes. Elegant ancient precision alloy, NOT marble or stone. Main color roughly sRGB 150 153 155, variations about plus/minus 15. Fine details at believable scale for a 2-metre patch. Game-ready albedo, seamless both axes.

## Retail material audit — 2026-10-31

This is an audit of the locally installed Campaign Evolved cooked assets and the
TST source settings at the start of the visual review. It is not a claim that the
Blender preview reproduces the game's layered shaders or that proposed settings
have passed an in-game comparison. Extracted retail textures stay in the ignored
`.dream-loop/retail-material-audit` reference cache, outside the community source
archive. No retail asset or source tuning was changed by this audit.

### Verified campaign dependencies

The checks below use cooked package imports, rather than assuming that an asset
is used in a map because it exists somewhere in the installation. Imports prove
the world/material dependency; they do not establish which visible pixel or
particular screenshot uses it.

- B30's `/Game/Levels/Halo1/Solo/B30/B30` world imports
  `/Game/Levels/Halo1/Solo/B30/Landscape/Materials/MI_Landscape_B30` and its mask
  variant. That instance imports `MM_Landscape_B30` in the same folder. The master
  imports all three D/N/packed-data families for the grass, path and sand listed
  below, together with height blending, hex texture sampling, wetness, Fluid Flux
  coastline integration and B30 grass/rock/sand decorators.
- B40's cooked world
  `/Game/Levels/Halo1/Solo/B40/LI_SnowMissions_Landscape/_Generated_/04QEAYH6V0YFXZ4QCWC2EJV9Z`
  imports `/Game/Levels/Halo1/Solo/B40/Landscape/Materials/MI_Landscape_B40`, whose
  parent is `MM_Landscape_B40`. That master imports Fresh Windswept Snow
  (`uhpjdeyn`), Windswept Snow (`uephfgudy`), Snow Covered Grass (`ueolejtn`),
  Windswept Snowy Stones (`tdloaf1r`), Rock Jagged (`udemcebew`) and Ground Gravel
  (`uconcitg`) material families. This verifies a second campaign landscape
  pipeline; its snow treatment is not a proposed replacement for TST's coast.
- B30 generated cells `3BC8KJ9KAAVWRRWMQJ898LYLR` and
  `9Y0XE0Y806U3WWM6VYBFUOCOH`, under `/Game/Levels/Halo1/Solo/B30/B30/_Generated_/`,
  import `/Game/Env/HS/FR/Gen/+Materials/MI_FR_Gen_Metal_Simple_01_Grey_MidDark_Glossy_Mid`.
  The instance's parent is `MI_FR_Gen_Metal_Simple_01_Grey_MidDark_Glossy`; its
  dependency list includes `+MLIP_FR_Gen_Metal` and the MidDark/Glossy layer
  variants. This is actual B30 world dependency evidence for the shared metal
  kit, not a global asset-name match.

### Native samples and measured parameters

All terrain paths below are relative to `/Game/Megascans/Surfaces/`:

| Role | Verified native texture |
| --- | --- |
| B30 grass albedo | `Ground_Grass_tb3nce2k/T_Ground_Grass_tb3nce_Desat_4K_NSVT_D` |
| B30 grass normal / packed data | `Ground_Grass_tb3nce2k/T_Ground_Grass_NSVT_4K_N`, `T_Ground_Grass_NSVT_4K_OHRG` |
| B30 path albedo / normal / packed data | `Trampled_Forest_Path_ub4jdihkw/T_Trampled_Forest_Path_ub4jdihkw_NSVT_D`, `_N`, `_ORHG` |
| B30 flat sand albedo / normal | `Thai_Beach_Sand_tefgafrk/T_Thai_Beach_Sand_tefgafrk_2K_NSVT_D`, `_N` |
| B30 flat sand packed data | `Thai_Beach_Sand_tefgafrk/T_ThaiBeachSand_tefgafrk_2K_NSVT_ORDp` |
| B30 rippled sand albedo / normal | `Thai_Rippled_Beach_Sand_vb1ldadn/T_Thai_Rippled_Beach_Sand_vb1ldadn_2K_NSVT_D`, `_N` |
| B30 rippled sand packed data | `Thai_Rippled_Beach_Sand_vb1ldadn/T_ThaiRippledBeachSand_vb1ldadn_2K_NSVT_ORDp` |
| B30 sandy gravel albedo | `Sandy_Gravel_Ground_vmndcca/T_T_Sandy_Gravel_Ground_vmndcca_B_2K_NSVT_D_copy` |
| B40 gravel albedo, also referenced by TST | `Ground_Gravel_uconcitg/T_Ground_Gravel_uconcitg_sbs_NSVT_D` |

The native grass diffuse is muted tan and gray-green; the native path is brown
and gray. TST already samples these retail textures through `Land.SURFACES` in
`mods/MJOLNIRLevelLoader/Scripts/main.lua`. TST uses its own `M_CE_LandscapePBR`
shader and its own distribution/tints; it does **not** use the full B30 landscape
material, authored layer weights, RVT state or coastline data merely by sharing
these images.

`MI_Landscape_B30` records Flat Sand normal strength `1`, roughness min/max
`0.8/1`; Rippled Sand normal strength `1.6`, roughness `0.88/0.88`; Sand B
roughness `0.6/1`; Stones roughness `0.6/0.9`. These are layer-specific values,
not a single multiplier over every terrain surface. `MI_Landscape_B40` records
Occlusion Contribution to Albedo `0`, Sediment Opacity `0.05` and explicit
height/blend settings per terrain layer. Its values should not be transplanted
into a different shader by name alone.

The B30-linked metal instance above records Base - Color `(0.3,0.3,0.3,1)` and
Base - Roughness `0.27432`. Its texture streaming metadata names
`T_Greeble_Test_N`, `T_Greeble_Test_ORHG`,
`T_Green_Rusty_Metal_Sheet_tklmeeso_8K_N`, `T_Grunge_tedwfbhc_4K_ORHG` and
`T_ModeratelyScratchedSurface_slnqfdtc_4K_ORH`, all on UV channel index `2`.
The common layer `/Game/Env/HS/FR/Gen/+Materials/+MLIP_FR_Gen_Metal` records
base roughness `0.38`, base normal strength `0.15`, greeble normal strength `0.1`,
greeble roughness modulation `-0.03` to `0.05`, plus separate wear and grime
controls. Its static settings include Base/Wear Use UV2 and Use UV3. The base
layer values are not the final composite appearance of every child instance.

The layer directly imports
`/Game/_Prototyping/Users/ChiyoLai/T_FR_Gen_Metal_01_ORHG` and
`/Game/_Prototyping/Users/ChiyoLai/T_Greeble_Test_ORHG`. These are packed data
textures, not diffuse color images. Their conspicuous false colors in a PNG
viewer should never be copied into a base-color slot. Direct native material
reuse needs compatible UVs and the expected layer/control inputs; current TST
authored masters sample UV0. A blind slot swap is not a verified integration.

### TST differences and next comparison

At the audit snapshot, `tools/level/build_landscape.py`'s `MAP_LOOKS["LTT"]`
applies grass tint `(0.42,0.52,0.30)`, dirt tint `(0.78,0.73,0.62)` and
`look = (2.6,1.3,0.5,0.35)`. In the custom shader these are, in order, normal
strength, sand grain contrast, legacy CE lightmap shading used as AO, and the
second-sand blend. Thus TST imposes substantially stronger normals and its own
olive tint on native samples. Its grass shader also forces roughness to at least
`0.92` and specular to `0`; these are shared renderer decisions, not measured
B30 settings.

There is no hidden conversion from exterior `0.96` metallic to low facility
metallic. `surfaces.json` explicitly defines facility armor/structure/recess/floor
metallic as `0.18/0.10/0.25/0.30`; the converted `materials.spec.json` retains
those values. `tools/level/authored_surfaces.py` copies the library and
`unreal/MJOLNIRMaterials/Scripts/build_ce_level.py::build_authored_surface`
connects its metallic value directly. The facility additionally reuses the worn
albedo whose broad mottling was rejected earlier in this document, with an armor
tint `(1.74,1.420588,1.016111)`. The floor's roughness range is `0.18–0.70`.
Those choices help explain the warm mineral-like walls and uneven polished floor;
this is a material diagnosis, not proof that material settings are the only
cause of the current shadow problem.

Candidate comparison, **unvalidated**: change only TST's palette first, using
the quiet titanium texture for facility plates, a neutral color hierarchy and
restrained normal strength; compare roughness centered near `0.38` against the
current broad floor range. For terrain, A/B a normal multiplier around `1–1.3`,
less legacy baked AO and less strongly colored tint, while retaining the native
texture families. Do not raise metallic across the facility before validating
its reflected environment and indirect lighting: dark reflections can turn a
metallic wall nearly black. Preserve shared campaign/runtime materials and
scope experiments to TST. Capture the same outdoor, entrance and interior
cameras after each change; a Blender-only render cannot certify UE lighting or
shader parity.

### Reproducing the inspection

Run from the repository root against the user's installed game. The example
tools are read-only; `texture export` writes a local reference file. Build the
examples with `cargo build -p ue-asset --example world_imports` if needed.

```powershell
$auditPaks = 'C:/Program Files (x86)/Steam/steamapps/common/Halo Campaign Evolved/Meteorite/Content/Paks'
.\target\debug\examples\world_imports.exe $auditPaks '/B30/B30.umap' 'Landscape'
.\target\debug\examples\world_imports.exe $auditPaks '/B30/Landscape/Materials/MM_Landscape_B30.uasset'
.\target\debug\examples\world_imports.exe $auditPaks '/B40/Landscape/Materials/MM_Landscape_B40.uasset'
.\target\release\mjolnir.exe ue get --paks $auditPaks --package '/Game/Levels/Halo1/Solo/B30/Landscape/Materials/MI_Landscape_B30'
.\target\release\mjolnir.exe ue get --paks $auditPaks --package '/Game/Env/HS/FR/Gen/+Materials/MI_FR_Gen_Metal_Simple_01_Grey_MidDark_Glossy_Mid'
.\target\release\mjolnir.exe texture list --paks $auditPaks --filter 'Ground_Grass'
New-Item -ItemType Directory -Force .dream-loop/retail-material-audit | Out-Null
.\target\release\mjolnir.exe texture export --paks $auditPaks --asset 'T_Ground_Grass_tb3nce_Desat_4K_NSVT_D' --out '.dream-loop/retail-material-audit/native-grass.png' --mip 1
```

`world_imports` enumerates package dependencies, while `ue get` decodes actual
parameter values. `material_survey` is useful for discovery, but its guessed
parent grouping is not proof of a specific material's parent. `texture export`
supports PNG/TIFF per mip or DDS for the cooked mip chain. Keep extracted assets
local and reproduce them from the installation rather than committing them.

### Lighting and controlled material study

The final `tst-facility-entry-sightline-20261031` staging output has skylight
intensity zero and atmosphere disabled. The `--release-beta` branch in
`upgrade_ce_map.py` substitutes a post-process ambient cubemap using classic CE
b30's water-reflection cube at intensity `0.65`, tint `(1,0.9,0.7,1)`. This is a
compatibility path, not the shipped B30 lighting setup. The runtime sun was
measured at intensity `32768` with source angle about `0.536` degrees.

A temporary runtime skylight test changed only existing TST sun/sky components.
Recapturing at intensity `512` visibly overexposed the fixed exterior view;
reducing to `1` restored approximately baseline exposure with a small shade
change. Neither value is a proposed final setting. The session ended before
the intermediate-value and indoor tests completed. There was no new crash
report, and a separate game process subsequently loaded another map; the exit
cannot be attributed to the skylight experiment. No installed files changed.

No authored-surface gamma defect was established: the material builder uses
sRGB albedo, linear roughness and normal-map compression with the documented
normal convention. These facility materials are ordinary Unreal-lit PBR, with
no CE lightmap. Terrain is different: its custom shader also derives AO from
legacy baked shade, which may compound dark runtime shadows. Test this
separately instead of changing global gamma or exposure to hide it.

The disposable study under `.dream-loop/retail-look-audit/blender-study` renders
the same assembled scene, camera and lighting before and after changing only
facility materials. `study.json` records the input hash and parameters. Cleaner
authored albedo, neutral tints, narrower roughness and weaker normals reduce
stone-like mottling and wet floor patches. Independent review found the first
candidate too uniformly blue-gray with weak floor seams, so material separation
and joint readability need to be retained. This is a Blender experiment using
authored textures, not an integration of the shipped layered shader or an
in-game validation. Source material settings remain unchanged.

The second study (`candidate2.png`, parameters in `study2.json`) keeps the same
camera, geometry and lighting. Slightly warmer armor, darker cooler structure
and lighter inset values restore restrained material separation. A shader mix
of 30% original floor albedo and 70% clean floor albedo retains more visible
joints without restoring the heavy blotches; no texture images were edited.
The scene remains cool overall and its recesses still need lighting work.
Neither candidate establishes shipped-material parity or final in-game values.

Implementation order: establish TST-scoped sky/reflection and indoor fill first;
then tune terrain tint, per-layer normals and legacy AO at fixed exposure;
finally integrate the cleaner facility material hierarchy and validate its UV
mapping. Compare fixed exterior, doorway and interior views at each stage.

### First production candidate, 2026-10-31

The follow-on implementation uses the existing clean titanium albedo for all
four facility roles, with distinct armor, structure and inset tints. The floor
uses the existing clean albedo/roughness/normal triplet at a 4 m tile instead of
the worn 8 m tile. Its two panels per tile preserve 2 m physical joint spacing.
The Blender material constructor was used for a fresh comparison at the same
camera and lighting; the old source preview was preserved.

`MAP_LOOKS["LTT"]` alone changes grass tint from `(0.42,0.52,0.30)` to
`(0.48,0.62,0.38)`, blended normal strength from `2.6` to `1.2`, and legacy baked
shade AO share from `0.5` to `0.15`. Native texture families, dirt/sand tint,
masking and physical tile scales remain the same. The shared terrain shader
does not expose independent normal multipliers for each layer.

The installed published loader supports sky recapture and sun source angle;
the earlier beta comment claiming capture was disabled was inaccurate. It lacks
the newer physical-skylight scaling option, so the release conversion now
divides a physical intensity by `light_scale` before removing that option.
An authored intensity of `4` becomes `0.00048828125` at scale `8192`, then resolves
back to `4` at runtime. Exposure remains at the previous beta value. A regression
test exercises this through the real config/CLI path at two light scales.

Fixed-camera live tests at sky intensity `4` lifted outdoor shade; `16` washed
out upper rocks and foliage. The provisional sun source angle is `1` degree.
Independent review preferred `4` over the zero-fill baseline but flagged a
cool/pale bias on upper metal and foliage to reassess after materials are built.
A native `TC_DaylightAmbientCubemap_Blurred` was loaded into a disposable runtime
post-process override, but it produced no useful visible change in this test.
A separate experiment changing the SkyLight source type and realtime capture
mode crashed that process; no source-type or native cube substitution is included.

The local material-only rebuild records its reuse of the verified entry-sightline
CE geometry/lightmaps in a new provenance manifest. Only material UV0 density is
changed for the floor; positions, normals, indices and lightmap UVs are checked
unchanged. It regenerates the native mesh/material/map packages and terrain
configuration without re-running the HEK lightmap solver.

### Runtime lighting follow-through

The first fresh launch exposed a capture-order problem: the SkyLight actor had
the intended intensity, but captured before the runtime sky/decor was ready.
The new loader option `environment.skylight.recapture_after_load` requests one
delayed capture after decor, guarded against reload, travel and destroyed actors.
TST opts in; other maps retain their existing behavior. This captures the rendered
sky **including the configured haze**. A live comparison clearing haze during
capture lost the desired outdoor shadow fill. This is an intentional TST art
choice, not a claim to reproduce B30's lighting rig. TST's landscape `pbr.light`
allows its `pbr.haze` to be promoted into the runtime environment.

The beta's legacy water-reflection cubemap was also providing most of the hall's
ambient lighting. Temporarily setting its intensity to zero exposed almost black
interiors despite visible emissive fixtures. Reducing it from `0.65` to `0.20`,
with neutral tint, retains readable fill while reducing the blue wash. The final
grass tint is intermediate: the first `(0.68,0.74,0.62)` test made the turf too
pale and dry after the sky fill was enabled.

Thirty symmetric facility point lights now cover the long branches, foyer,
vestibules, concourses and blind-end washers, aligned with modeled fixtures.
Their source intensity ranges from `1.2` to `3.0`, multiplied by the existing
8192 light scale. Falloff is 2, radius is 6.5 or 9 m, and color is `(1,.93,.83)`.
An optional 30 cm source radius and specular scale `0.25` soften the distracting
round highlights from point-light approximations. The twelve existing base
lights are unchanged. These are runtime approximations of the Blender area
lights; the preview's 152 lights are not copied wholesale into the game.

The refreshed annotated `tst.blend` and full source JMS include the already
verified entry geometry fixes and updated floor UVs. The previous tracked JMS
was stale; its large diff is the corrected full source export, not new geometry
introduced by this material pass. Checks against the October 31 corrected
authoring bundle preserve all 219,824 triangles' positions, normals, regions
and material assignments; only 380 floor triangles have doubled UV density.
Owned textures remain portable and extracted native reference assets stay local.

Fixed-camera game comparisons show cleaner floor joints, stronger separation
between inset panels and supports, and more readable exterior shade. Remaining
limits include the point-light approximation, some sharp reflections in the
older base interiors, and the custom terrain blend rather than B30's full
layered material. This pass does not establish retail shader or visual parity.

The candidate is local only. Delayed recapture and per-light source/specular
controls require a loader update before publishing this lighting setup to the
Hub. The existing beta is not replaced by these experiments. Revision manifests
under `tst-retail-look-20261031/evidence` distinguish the material cook, runtime
revision 2 and the subsequent revision 3 rebuild; screenshots from live tuning
are not substitutes for validating the installed revision after a fresh launch.

Revision 3 passed a fresh private TST Slayer launch and `mjolnir_level_reload`:
both triggered the post-decor capture, and runtime inspection found all 30
facility lights with the expected emitter settings, sky intensity 4 and ambient
intensity 0.20. The five unretouched game images and source hashes are in
[`review/retail-look-20261031`](review/retail-look-20261031/validation.json).
Independent visual review found no new clipping/geometry/texture blocker in the
hall and exterior views, while noting darker interior panels and only modest
ground-color improvement. Forty focused Python/Lua tests pass. A stationary
44-second exterior sample at 1600x900 recorded 7 ms median, 8 ms p95/p99 and a
45 ms worst frame; this is not a full gameplay or multiplayer performance test.
