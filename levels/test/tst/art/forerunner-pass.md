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
