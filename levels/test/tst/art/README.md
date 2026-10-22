# Authored visual studies

`reference/approved_coastal_concept.png` is the user-approved overall generated
direction: a larger coastal arena with two detailed bases, warm interiors,
three routes, trees, cliffs and water. It is a target for the design, not an
image of a completed map. The original generation prompt is not reproduced here;
the approved design brief is recorded in `../DESIGN.md`.

`reference/base_detail_study.png` is an AI-generated design reference, not a
Blender render or in-game screenshot. It refines a render of the actual r2 base
without changing its entrance positions, dimensions or roof silhouette.

`textures/weathered_alloy_albedo.png` is an AI-generated base-color candidate
for previewing weathered architectural plates. It is not a normal/roughness map.
Inspect repetition and edge continuity before using it at large scale. It is
not yet bound to a compiled CE shader or included in a runtime release.

`reference/interior_detail_study.png` is an AI-generated refinement of the
actual Blender interior view. It preserves the two door locations and room
proportions while proposing ribs, ceiling beams, inset panels and warm lighting.
It is a modeling reference, not a completed map render.

These were generated on October 20, 2026 with the built-in image generation tool.
The base references were the actual Blender geometry render and the previously
approved coastal arena concept. No downloaded asset library was used.

## Base detail prompt

Create a high-quality architectural detail study of the existing playable
sci-fi base, matching the coastal Forerunner-style arena direction. Preserve
the exact camera, roof height, footprint, both entrance positions and widths,
ramps, walls, sloped supports and stepped roof silhouette. Use believable
weathered pale graphite alloy and light grey stone-metal armor, layered wall
plates, recessed seams, restrained worn edges, red team identifiers, warm
lintel/interior lights and roof panels modelable with a few dozen intentional
pieces. Add bevels and 5–15 cm inset strips with clear assembly hierarchy.
No clutter, crates, blocked openings/roofs/ramps, extra wings, grain, clipped
highlights or text labels. Preserve terrain silhouette. Favor physical
construction and consistent scale over decorative noise.

## Albedo prompt

A seamless tileable PBR base-color/albedo texture for pale warm-grey weathered
sci-fi architectural alloy, 2 metres square coverage, orthographic flat scan
filling a square image. Muted light-grey titanium with subtle mineral mottling,
small scattered pits, delicate hairline scratches and faint warm-grey grime.
Calm broad uniform values; realistic material detail, not noise. No panels,
grooves, bolts, text, symbols, borders, perspective, lighting, shadows, specular
highlights, bevels, objects, flakes, glitter or vignette. Neutral evenly lit
albedo, edge-to-edge tiling continuity horizontally and vertically.

## Interior detail prompt summary

Refine the actual interior render using the approved exterior detail language.
Preserve both openings, room dimensions and camera. Introduce shallow grey and
graphite wall ribs, a coherent ceiling beam grid, flush floor plates, red base
identification and warm cove lighting. Keep player paths and objective space
clear. Favor physically plausible construction and readable large forms over
clutter or decorative noise.

## Floor plate albedo

`textures/graphite_floor_plates_albedo.png` was generated on October 20, 2026
as a 4-by-4-metre, two-by-two plate base-color study. The prompt requested a
seamless orthographic scan of neutral dark-grey machined titanium, thin joints,
restrained angular corner insets, flush fasteners, subtle wear and calm broad
surfaces, without lighting, text, colored stripes or debris. The generated
result includes some apparent relief in its line work; it is not a calibrated
PBR scan or a normal map. Inspect tiling and material response in the render.
Like the alloy texture, this remains an explicit preview material until it is
bound to a runtime shader and verified in game.

## Coastal granite albedo

`textures/coastal_granite_albedo.png` was generated on October 20, 2026 for
6-by-6-metre rock coverage. The prompt requested a tileable orthographic albedo
scan of pale grey coastal granite, broad angular fractured plates, oblique
dark fissures, fine pits and subtle staining, with uniform diffuse light and
no objects, vegetation, text or scene context. This candidate supplies surface
detail on the modeled cliff; it does not replace the silhouette or collision.
It is a preview substitution, with estimated rather than authored micro relief.

## Enclosed basin and infrastructure wall

`reference/enclosed_basin_wall_concept.png` was generated with the built-in image
tool on October 20, 2026, editing the actual native-assets Blender overview.
The user requested full cliff enclosure, a full-length Forerunner wall on one
side, and teleporter access to a balcony. This generated image is a target;
it is not a Blender render, gameplay proof, or a separately approved final design.
The source implements the structure and route as an iteration of the previously
approved build direction. Runtime dressing and materials remain to be checked.

Generation prompt:

Use case: precise-object-edit. Edit this current Blender map screenshot into a
realistic in-engine visual target for the SAME Halo-style multiplayer arena.
Keep camera angle, wide 16:9 composition, two low bases at left/right, central
circular pad, tree locations and pond at front-right recognizable. Primary
change: enclose the entire rectangular arena with continuous tall natural
fractured granite cliffs along front and both short sides, joined seamlessly
into a monumental Forerunner infrastructure wall that spans the ENTIRE rear
long edge. No ocean openings or gaps in boundary. Rear structure is about 150
metres long, 24 metres tall, cool weathered metallic stone, strong large angular
buttresses, deep recessed panels, stepped chamfered crown and restrained cyan
seams. It is an ancient retaining structure embedded into cliffs, not a
collection of towers. Add a usable inset balcony about 7 metres above arena
floor, 5 metres deep, with segmented chest-high cover and two sheltered luminous
teleporter alcoves widely separated toward left/right. Balcony has interrupted
sightlines and modest drop-down landings, not an exposed sniper rail. Show
coherent large-scale architecture with bevels, dark mechanical recesses, pale
panel faces, warm interior illumination contrasting cyan accents. Foreground
cliffs should clearly close the arena while allowing this elevated overview
to see the playing field. Realistic high-quality game screenshot, clean
controlled materials, natural grass and rock detail, clear bright daytime
lighting, no grain, no text, no annotations, no extra bases, no floating objects.
This is a feasible modeled design, avoid overdecorated visual noise.

`textures/weathered_megastructure_albedo.png` is a second built-in imagegen
material study, generated October 20, 2026. Its full prompt and provenance are
in [weathered_megastructure_prompt.txt](weathered_megastructure_prompt.txt).
It depicts pale weathered titanium/concrete composite with rain streaks and
mineral staining, without panel divisions or baked directional light. The
preview applies it at a 12 m scale with estimated micro relief; it is not yet a
runtime CE shader.

`textures/coastal_granite_lichen_albedo.png` is a built-in imagegen edit of the
earlier granite texture. Its complete prompt is saved in
[coastal_granite_lichen_prompt.txt](coastal_granite_lichen_prompt.txt). Localized
charcoal, ivory and ochre lichen and restrained moss add mineral variation.
Native Desert/CliffFlat geometry mixes this authored image in localized patches
over the quieter original granite at an 8 m local scale, with native normal/AO
maps where available and approximate weathering. The BSP
cliff preview uses the same image at 6 m. These are explicitly Blender material
studies; the images do not replace the installed game's layered rock shaders.

`textures/coastal_meadow_albedo.png` is a built-in imagegen ground-underlay
study at 8 m scale, beneath the actual native PCG grass meshes. The full prompt
and provenance are in [coastal_meadow_prompt.txt](coastal_meadow_prompt.txt).
It supplies fine olive grass and earth detail in the Blender preview, retaining
the installed beach-alpha mask and soil detail. It is not a runtime material
replacement. Dry patches shared by the ground and blades are an art-directed
Blender shader approximation.

The October 20 Forerunner TLC pass adds a fixed-camera balcony target and
fine titanium albedo. Research, exact built-in imagegen prompts and the
distinction between source armor geometry and preview materials are recorded
in [forerunner-pass.md](forerunner-pass.md).
