# Halo 2 shader census

Every shader on the Halo 2 multiplayer maps (MCC's `h2_maps_win64_dx11`, the
25 `.map` files besides `shared` and `mainmenu`), grouped by template. For
each template the census compares what Halo 2 draws (the passes its template
runs) with what `mjolnir cache stage` makes of it, and weights it by the
triangles that use it in the staged BSPs and placed models. Run on
2026-11-10, with specular read from each template's passes.

How to run it again:

```
cargo run --release -p blam-cache --example h2_shader_census -- "<h2_maps_win64_dx11>" <dir>/shader_census.json
mjolnir cache stage <map>.map --out <dir>/staged/<map>      # each map
python tools/level/h2_shader_census.py <dir>
```

## Headline

- 141 templates in all; 97 are used by the maps themselves and 44 only by
  `shared.map` (weapons, characters, vehicles, effects, which the
  conversion does not draw from Halo 2).
- 88 templates reach a converted map, over 692,409 triangles. `tex_bump`
  alone is 43% of them; the top ten templates are 79%.
- Every drawn template but four has a branch of its own in
  `crates/blam-cache/src/h2/render.rs`. The four on the default branch
  (diffuse map, opaque) are 0.3% of triangles: `prt_simple`,
  `plasma_mask_offset`, `tex_env_3_channel_illum` and
  `roadsign_glass_newmombasa`.
- Specular: 25 templates, 61% of all triangles, shine as in Halo 2 (the
  base map's alpha as the mask); the env, overlay and no-specular templates
  draw the specular pass but their lightmap pass leaves no mask, so they
  never shine in Halo 2 either (below).
- Twelve templates the maps use are never drawn, among them every
  decorator (grass, rubble, debris and blast marks on 11 maps) and the open
  water of Headlong, Dune, Needle and Zanzibar.

The census measures coverage, not likeness. "Handled" means a template has
a branch that reads its maps and constants as its compiled shaders use
them; only Lockout, Ascension, Zanzibar and Turf have been compared in game.
Triangle share is not screen share: a sky dome or a sea is few triangles
and much of the picture.

## The heaviest templates

| Template | Share | Maps | Converter | Gap |
|---|---|---|---|---|
| `tex_bump` | 43.2% | 25 | generic `tex_bump`, specular | - |
| `tex_bump_env` | 7.2% | 12 | `tex_bump_env` reflection | - |
| `tex_bump_env_combined` | 5.9% | 20 | `tex_bump_env` reflection | - |
| `tex_bump_alpha_test_single_pass` | 5.6% | 16 | cut-out on the bump alpha | - |
| `tex_env` | 4.2% | 8 | base + detail | - |
| `tex_bump_env_no_detail` | 3.0% | 4 | `tex_bump_env` reflection | - |
| `tex_bump_detail_blend` | 2.9% | 11 | details first, specular | - |
| `tex_alpha_test` | 2.8% | 9 | cut-out, specular | - |
| `tex_bump_detail_overlay` | 2.4% | 5 | detail family | - |
| `tex_bump_env_detail_overlay` | 2.2% | 3 | `tex_bump_env` reflection | - |
| `tex_bump_detail_blend_detail` | 1.8% | 6 | detail family, specular | - |
| `tex_bump_illum` | 1.7% | 20 | glow pass tint, specular | - |
| `tex_bump_detail_keep` | 1.5% | 7 | detail family, specular | - |
| `tex_bump_three_detail_blend` | 1.5% | 3 | detail family, specular | - |
| `tex_bump_alpha_test` | 1.3% | 13 | cut-out | - |
| `one_alpha_env` | 1.2% | 20 | glass | - |
| `tex_bump_one_change_color` | 1.1% | 5 | change colour, specular | - |

`tools/level/h2_shader_census.py` prints all 88.

## Specular

Nearly every opaque template draws Halo 2's
`default_light_combined_tangentspace_specular_sphere` pass, but it only
shows where the template's lightmap pass wrote a mask into the frame's
alpha (docs/h2_map_conversion.md, Specular). The census reads each
template's passes from its postprocess definition (the earlier byte scan
missed every other pass) and takes a template as specular where the
specular pass has its colours (vertex registers 10 and 11) and every
lightmap pass writes the base alpha mask:

- specular (25 templates, 61% of triangles): `tex_bump`, the detail
  blends and keeps, two and three detail, `tex_bump_illum` and its
  variants, `tex_bump_shiny`, `tex_bump_one_change_color` and
  `four_change_color`, `tex_alpha_test`, `tex_illum`, `tex_detail_blend`,
  the tiling and honor guard variants;
- no specular in Halo 2 (alpha 0): every env lightmap pass
  (`tex_bump_env*`, `tex_env`), `tex_bump_detail_overlay` and
  `tex_bump_illum_no_specular`;
- not converted: the alpha-tested templates whose cut-out is staged in the
  base alpha (`tex_bump_alpha_test_single_pass` and the clamped and env
  alpha tests). Their lightmap passes write other terms; read as the
  staged alpha, a frond would shine all over.

## Never drawn

| Template | Maps | What it is |
|---|---|---|
| `decorator_tex` | backwash, beavercreek, coagulation, containment, cyclotron, deltatap, derelict, dune, highplains, warlock, zanzibar | decorators: grass, rocks, debris |
| `decorator_decal_paint`, `_multiply` | derelict, highplains, triplicate, headlong | decorator decals: rubble, blast marks, blood |
| `ocean_static`, `ocean_static_opaque_blend` | headlong, dune | the open sea |
| `water_static` | needle, zanzibar | still water |
| `prt_scarab` | triplicate, turf | the scarab's hull |
| `prt_simple_lm_emissive` | containment | the base shield gear |
| `tex_bump_env_clamped_combined` | containment, midship, triplicate, zanzibar | the door keypads |
| `plasma_light_gel` | coagulation, foundation | the underwater caustic light |
| `particle_alpha_test` | coagulation, midship, turf | particle models (concrete chunks) |
| `tex_bump_env_alpha_test` | derelict | character and vehicle shaders kept in the map |

Staging has no decorator code at all (the scenario's decorator sets are
not read). The seas fit the Fluid Flux water work. Why the scarab, the
shield gear, the keypads and the light gels are missing has not been
looked into: their shaders are in the maps, but no staged BSP or model
surface uses them.

## Smaller gaps

- Reflection is missing on `tex_bump_env_illum_3_channel_combined` (0.2%)
  and the tiling and honor guard env variants.
- The glow is missing on `tex_env_3_channel_illum` and `illum_opaque`.
- The sky's `one_alpha_env` layers draw without a cube, as their cube is
  black.
