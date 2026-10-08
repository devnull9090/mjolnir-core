# blam-radiosity

Classic Halo CE lit its levels with a progressive-refinement radiosity solver
in the HEK's `tool.exe lightmaps`. This crate re-solves that lighting from a
converted map's staging (the halo2ue export merged by
`tools/level/merge_ce_scene.py`) so the lightmaps can be rendered at any
resolution, on every core, and later on the GPU. The algorithm below is what
tool.exe does, recovered from its code (2026-10-07, Ghidra over the MCC and
2004 builds; the constants are the binary's own), and its output is the
acceptance test: run at tool.exe's own element density the solver must match
tool.exe's lightmap texel for texel within a small tolerance.

## Inputs

- `scene.gltf`: every triangle of the BSP (and the placed scenery, which only
  occludes) with its lightmap page (`__lmN` material suffix) and lightmap UVs.
  glTF is metres, y up: CE (x, y, z) world units are glTF (x, z, -y) x 3.048.
- `materials.json`: per shader, the radiosity header (`power`,
  `color_of_emitted_light`, `tint_color`, `detail_level`, flags: bit 0 simple
  parameterization, bit 1 ignore normals, bit 2 transparent lit) and the base
  map, whose colour is the surface's reflectance.
- `placement.json`: the sky's `lights` (sun and fill: colour, power, yaw,
  pitch, diameter, affects exteriors/interiors) and its indoor and outdoor
  ambient (colour x power).
- `bsp/clusters_0.json`: each cluster's sky index (-1 = interior), each
  surface's cluster, and the cluster visibility rows (the PVS tool.exe
  computed at structure build).
- `bsp/collision_0.json`: the collision BSP (the solid test below) and its
  materials: which shaders a shadow ray can meet at all, and which are
  water (material type 28).
- `scene_lights.json` beside the scene (`merge_ce_scene.py --lights`): the
  `light` tags placed objects carry, only with `--placed-lights` (below).

## Elements

Only surfaces whose shader is `shader_environment`, `shader_model` or
`shader_transparent_meter`, or that emit (`power != 0`), are lit. Each BSP
triangle starts as one element with its emission `color_of_emitted_light x
power` as unshot energy, then every element is split (`initial subdivision`)
until no edge needs more than one segment of the quality row's
`maximum_segment_length`:

| detail level | gradient tolerance | minimum segment | emissive segment | non-emissive segment |
|---|---|---|---|---|
| 0 high | 0.5 | 0.125 | 0.5 | 0.9 |
| 1 medium | 0.7 | 0.3 | 1.2 | 2.4 |
| 2 low | 0.8 | 0.5 | 2 | 4 |
| 3 turd | never | 20 | 40 | 80 |

(final quality; the draft quality's rows are 1/0.5/2/4, 2/1/4/8, 3/2/8/16 and
the same last row.) Lengths are CE world units (1 wu = 3.048 m). An edge with
`segments = ceil(length / maximum_segment_length)`: when all three edges need
splitting the triangle splits four ways, otherwise the edge with most segments
is bisected at `k/segments` with `k = ceil(segments/2)` or `floor` so the cut
lands on the side of the foot of the altitude from the opposite vertex. New
vertices are shared through a (position, normal) hash, their normals the
normalised lerp. Each element's area is half its cross product, its plane the
triangle's, and its reflectance the mean of three base-map samples at its
corners' texture UVs (0 for a shader without a base map).

During the solve an element whose vertices' irradiance differs across an edge
by more than `gradient tolerance x max(endpoints)` (floor 0.005) halves its
segment length and splits again, down to `2 x minimum segment`.

## Light

Vertices accumulate irradiance; elements accumulate unshot energy.

1. The light phase shoots every light at every vertex of every element in the
   light's clusters. Sky lights: for the exterior set, the sky's lights with
   `affects exteriors`, for the interior set those with `affects interiors`,
   each as an `n x n` grid (`n` = 4 final, 2 draft) of directional lights
   spread `-diameter..+diameter` radians in yaw and pitch with `power / n^2`
   each, travelling along `-(cos yaw cos pitch, sin yaw cos pitch, sin pitch)`
   (z up: yaw and pitch point at the sun), then one ambient light of the set's
   ambient colour x power. Then every emitting element (a shader with a
   radiosity power: lamps, light strips, door glyphs) shoots, each one,
   before the progressive loop: its stop is an area-weighted mean, which on a
   large map is met before a few bright square metres ever shoot (Death
   Island's strips, 29 m2 at power 60, never shot while tool.exe's pages
   carry their light; with them shooting first the base interior's pages
   score 20-48/255 -> 9-17). tool.exe's code reads placed `light` objects
   as point or spot lights (`1/d^2`, radius `sqrt(255 x power)`, a cosine
   ramp between the cutoff and falloff angles); its pages show none of it:
   Death Island's twenty fixtures (intensity 3, white) leave no pool on the
   walls beside them (shipped 0.13-0.34 within 1.5 m, our solve without
   them 0.09-0.25, with them at any scale worse), so they are off unless
   `--placed-lights`. A directional
   light tests visibility with one ray towards the sun; ambient needs none.
   The light's colour reaches the vertex times the ray's transmission and the
   receiver cosine (the code as read shows none, but without it Danger
   Canyon scores far worse against tool.exe's pages; `Options::sun_cosine`).
   A ray that starts inside the collision BSP's solid is blocked, and one
   between surfaces that ends inside it too (`bsp/collision_0.json`; tool.exe
   walks that tree for its shadow rays): a structure's panels drawn a little
   inside its simpler collision hull are dark in CE's lightmaps, and without
   the test every crease and bridge-frame edge lit up.
2. Then progressive shooting: the element with the most unshot energy
   `(r+g+b) x area` shoots at every vertex of every element in the clusters
   its cluster sees (and its own), with the form factor of three samples on
   the shooter (`u, v` = 1/6, 1/6; 2/3, 1/6; 1/6, 2/3):
   `F = sum cos_s cos_r (A/3) / (pi r^2 + A/3)` over the samples that face the
   receiver and are visible from it, clamped to [0, 1]; a ray that meets a
   two-sided collision surface carrying a rendered material passes on
   attenuated by that shader's `tint_color`, anything else blocks. A
   rendered surface the collision BSP does not carry (water, light strips,
   glow decals) is not in a ray's way at all: Death Island's sea floor is
   lit through its water (page 1: 59/255 -> 18 once the water stopped
   blocking the sun). The
   receiver cosine is 1 for `ignore normals` shaders. The vertex gains
   `F x unshot` as irradiance and `direction x luma(gain)` into its incident
   accumulator; each receiving patch's element gains
   `(patch area / element area) x F_mean x reflectance` as unshot energy
   (`F_mean` the three corners' mean); the shooter's unshot energy is zeroed.
3. Stop when the area-weighted mean unshot energy `(r+g+b)` drops below the
   stop threshold. tool.exe prints 0.01 as its final target, but its pages
   hold more bounce than a solve stopped there: Death Island's exterior
   pages score 25.6 -> 20.4/255 going from 0.01 to 0.001 and Danger
   Canyon's 15.6 -> 15.4, nothing worsens, so 0.001 is the default
   (`--stop`), about twice the shots.
4. An emitting surface's own lightmap shows its emission on top of what it
   gathers (a patch's radiosity starts at its emission). A surface whose
   collision material is water is not solved at all: its chart is the
   constant (0.9, 0.9, 1.0), every texel of Death Island's sea floor being
   230 230 255 in the shipped pages.

## Output

Per vertex: irradiance (divided by its maximum channel when that exceeds 1,
then clamped), the incident direction (the accumulator normalised) and its
directional ratio (`|accumulator| / luma(irradiance)`, clamped to 1). tool.exe
rasterises the patches onto page charts of a size set by the patch density
(`sqrt(patches per area) x 0.7 / 256`, charts capped at 252 texels, 1 texel
padding, 3x supersampled, dilated); this crate draws onto the map's existing
lightmap UV layout at a chosen multiple of the shipped pages: the bounce and
ambient light Gouraud between the patch corners, and the sun and fill
evaluated again at every texel from its own position and normal
(`Options::texel_direct`), so a shadow's edge lands where the geometry puts
it rather than stepping along the patch boundaries (at 2x the steps showed
on Danger Canyon's cliffs). The pages are supersampled 3x, dilated the same
way, and written as PNGs the conversion cooks in place of the shipped pages.

## Running it

`mjolnir level lightmaps <staging> <scene.gltf> <out> [--scale auto|N] [--finer 2] [--placed-lights] [--verbose]`
(`crates/blam-cli/src/level_lightmaps.rs`) solves and writes the pages
(`--verbose` also reports each emitting shader: its elements, energy, what
stayed unshot, and how lit the surfaces within 1.5 m ended up)
(`auto`: the power of two that brings the lit surfaces' median texel
density to `--density` 4/m within `--max-page` 2048 and `--max-texels`
48 M; the dilation grows with the scale so a mip chain never averages the
empty page into a chart);
it also writes two companions per page from the same rays, antialiased:
`<page>_sunvis.png`, the sun's visibility, which `lightmap_bake` takes as its
green channel in place of its own hard per-texel trace; and
`<page>_sunshare.png`, the texel's light without the sun (CE's ambient,
fill and bounce as a lightmap page of its own). With that page
(`ce_material_spec.py` SunShare, HasSunShare) the runtime masters run CE's
texture pass over it for the terrain's emissive, rebuild each texel's sunlit
lightmap per channel from it and the sky's sun (`environment.sun.ce_light`,
colour x power, at the texel's N.L, clamped as tool.exe clamps) for the sun's
albedo, and leave every sun shadow to Unreal's sun and the terrain copy's
shadows, so the lightmap's own
shadow edge (its texels, bilinear, scalloped at any scale) never shows
inside the crisp one, and the level carries no sun mask (gen_ce_level.py
`--no-sun-mask`), whose metre-wide transition would soften each edge. The
ambient is a page and not a share of the lightmap because two bilinear
samples multiplied are not the bilinear sample of the product: a share drew
a bright rim along every shadow's texel contour;
`tools/level/convert_ce_map.sh` runs it at `LIGHTMAP_SCALE` (default auto, 0
keeps the shipped pages) and hands the directory to `ce_material_spec.py
--lightmaps`. `--scale 1 --finer 1 --compare` is the acceptance test against
the shipped pages: Danger Canyon scores a mean difference of 15/255 over the
drawn texels and Death Island 16.5/255 (its base interior's pages 6-17,
its sea floor under 2), the remainder being tool.exe's placed-object
shadows and its own chart raster.

The example `radiosity_bake` is the same solve with every knob exposed
(`--no-sun-cosine`, `--no-bsp-solid`, `--fill-spread`, `--dump <csv>` of
every patch corner's solved light for analysis).
