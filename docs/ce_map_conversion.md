# Converting a Classic CE Map

**Status:** 2026-09-30. Verified in game on Blood Gulch and Sidewinder,
started from the menu with nothing done by hand: own collision at CE
coordinates, terrain mesh, spawns, vehicles and weapons, the Megalo engine and
the Slayer script (loaded, and the interpreter shown running it; a kill has not
been scored, since that needs a second player).

A classic Halo CE `.map` becomes a standalone multiplayer mission in Halo:
Campaign Evolved: its own scenario, its own collision, its players, vehicles
and weapons placed where CE put them, running under the simulation's Megalo
multiplayer engine.

```bash
export HCE_PAKS=".../Halo Campaign Evolved/Meteorite/Content/Paks"
tools/level/convert_ce_map.sh maps/bloodgulch.map BGL out/bgl --install
```

`CODE` is the new scenario's three-character codename. `--install` writes the
containers into the game and the level file into MJOLNIRLevelLoader; without
it everything lands in the output folder.

### Custom Edition maps

Community maps convert the same way (`TITLE="Yoyorast Island"
tools/level/convert_ce_map.sh "maps/Yoyorast Island V2.map" YOY out/yoy`).
Their file name becomes `[a-z0-9_]` for file and asset names; `TITLE` is the
menu name. Three things differ from the stock maps:

- **Protected maps** (Yoyorast Island V2): a protection tool replaced every
  primary tag class with `ztpt` and every tag path with `<zteam>`. halo2ue
  repairs the index in memory (HalcyonRing `map-core/src/parsers/deprotect.rs`)
  before anything reads it. Every tag reference inside the tag data (and the
  BSP's own region) still carries the real class, so each tag's class is the
  majority of the references to it; the scenario comes from the header. The
  names come back by fingerprinting each tag (its data with pointers masked
  and references replaced by the referenced tag's fingerprint, a few rounds)
  against the unprotected maps in the same folder (`--reference-maps`).
  Yoyorast: all 3,091 classes and 1,261 of 1,838 names, every stock weapon,
  power-up and item collection among them. The rest get
  `protected\<class>\<index>`, and a second copy of a stock tag
  `<stock path>__p<index>` (placed as the stock tag). halo2ue writes the
  repaired index to `staging/tags.json` for `ce_sounds.py`.
- **Custom vehicles** the tag map does not list are placed by the CE vehicle
  type halo2ue stages (`vehicle_type`): jeep as warthog, tank as scorpion,
  scout as ghost, fighter as banshee, turret as shade (`vehicle_types` in
  `defs/level/ce-tag-map.json`).
- **Big BSPs.** Coldsnap's BSP is 35,173 surfaces once its polygons are split
  into triangles, past a definition's 32,767. Where triangles do not fit, the
  split makes quads instead (32,257); see
  [ce_terrain_collision.md](ce_terrain_collision.md). Its second BSP is a copy
  of the first.

Sounds a custom map keeps inside the `.map` (not in `sounds.map`) are not
extracted.

## What the command does

| Step | Tool | Result |
|---|---|---|
| 1 | `halo2ue-export` (HalcyonRing) | the `.map` staged: collision BSP, placements, netgame flags |
| 2 | `merge_ce_collision.py`, `mjolnir level collision --own-bsp` | the structure BSP, scenery collision included |
| 3 | `merge_ce_scene.py`, `ce_material_spec.py`, `build_terrain_meshes.py` (`mesh_rewrite` + `package_override`), `unreal/MJOLNIRMaterials` | the terrain, scenery and sky as two meshes (over `/Engine/BasicShapes/Cylinder` and `Cone`), and their CE materials and bitmaps (`pakchunk988-MJOLNIRMAT`) |
| 4 | `tools/level/gen_ce_level.py` | the level file |
| 5 | `mjolnir level bake --standalone CODE --bsp 8=…` | scenario and registration containers, on the map's own empty Unreal world |
| 6 | `tools/level/build_spawn_point.sh` | the spawn-point and teleporter scenery every converted map places |

**The world must be a Blam world.** Step 5 gives the bare MapKit world
`BlamWorldSettings` with a `DefaultScenario` path (`blam_world_settings` in
`crates/blam-cli/src/level.rs`). Four world subsystems are created only when
the glue engine subsystem accepts the world (CU4 `+0x7b93a50`: the settings
are a `BlamWorldSettings` whose `DefaultScenario` soft path is set):

- `HaloMaterialResponseWorldSubsystem`
- `BlamMapGlueOuterSubsystem`
- `BlamSynchronizationPrecreateObjectActorWorldSubsystem`
- `BlamBreakableSurfaceSaveGameSubsystem`

On plain `WorldSettings` none of them existed, and bullet impacts, tracers
and surface footsteps were missing. A shipped level points `DefaultScenario`
at its `BlamScenario` actor. Ours names `PersistentLevel.BlamScenario`, which
the gate does not resolve, and with it the world has the same 35 subsystems
as B40.

Build the tools first: `cargo build --release -p blam-cli -p ue-asset --example
mesh_rewrite -p blam-pack --example package_override -p ue-texture --example
lightmap_bake`. Without `lightmap_bake` the map converts without its baked
corners and sun.

Step 3 also re-solves the map's lightmaps (`mjolnir level lightmaps`,
[crates/blam-radiosity](../crates/blam-radiosity/README.md): tool.exe's own
radiosity, on every core, the sun and sky fill evaluated per texel) at
`LIGHTMAP_SCALE` times the shipped pages' size (`auto` by default: the
power of two that brings the lit surfaces' median texel density to 4 per
metre, no page over 2048; Blood Gulch comes out at 8x, Danger Canyon at
8x, Hang 'Em High at 4x); the shipped pages are 1x and blur every shadow
edge, and at 2x a pillar's shadow on a base roof was still a soft blob
beside the traced shadow's hard edge. `LIGHTMAP_SCALE=0` keeps the
shipped pages. A map's interior light is its emitting shaders' (Death
Island's red and blue strips, the door glyphs): they shoot before the
progressive loop, which would otherwise starve them on a large map, and
their bounce fills the bases as CE's pages have them. The `light` tags
placed objects carry go to `scene_lights.json` (`merge_ce_scene.py
--lights`) but light nothing unless `--placed-lights`: tool.exe's own
pages show no pool beside Death Island's twenty fixtures. Surfaces whose
collision material is water take tool.exe's constant (230 230 255), and a
rendered surface with no collision (water, strips) never blocks a ray, so
the sea floor is lit through the water. The solved pages replace the shipped ones in the material
spec (`ce_material_spec.py --lightmaps`), the bake's pages take their size,
and the bake's sun channel (where CE's sun reaches) comes from the solver's
`<page>_sunvis.png`. The solver's `<page>_sunshare.png` (each texel's light
without the sun) goes to the materials as `SunShare`: the masters run CE's
texture pass over it for the emissive, so CE's ambient, fill and bounce are
drawn, rebuild the sunlit lightmap per channel from it and the sky's sun
(`environment.sun.ce_light`) for the sun's albedo (at N.L no lower than 0.3,
so a face turned from the sun keeps a colour for headlights and flashes:
at its own N.L it had none, and Death Island's headlights stopped at a hard
line where a cliff turned away), and Unreal's sun, shadowed
by the terrain copy, draws every sun shadow; the lightmap's own
texel-stepped shadow edge never shows inside the crisp one. Such a level has no sun mask (`gen_ce_level.py --no-sun-mask`):
the copy's shadows are the sun's shadows, and the mask's metre-wide
transition would soften them. Placed scenery stays as CE lights it: the
light sampled under each object from the lightmap, shaded by its incident
direction, with no Unreal sun on it. CE never shadowed scenery dynamically,
and under the copy's shadows a boulder beneath a tree drew half bright and
half black, and boughs shadowed each other black.

### The structure BSP (step 2)

Built on `BSP_03_1_Chasm_old`, a small shipped BSP with one kd supernode, one
cluster and one instance, of which only the file format is kept
(`blam_sbsp::convert::convert_own`, [ce_terrain_collision.md](ce_terrain_collision.md)):

- the CE collision tree goes into the **world shell**, which decides what is
  inside the world;
- and into **definition 0 behind instance 0**, which the collision queries
  test (the instance is listed at the collision kd hierarchy's root);
- the BSP's static Havok body, **`structure_physics`**, is recompiled with one
  key per CE surface. This is what players, vehicles and items stand on;
  nothing rebuilds it at load.

The map keeps its CE coordinates. It is built for **index 0**
(`level collision --bsp-index 0`): every kd hierarchy header and instance
shape names the BSP's index, and the donor's own say 7.

**A scenario of its own.** The scenario is still cloned from B40's, but the
bake leaves none of B40 in it (`blam.single_bsp`, applied after `--bsp 8=`
has pointed slot 8 at the map's BSP):

- `structure bsps`, `ai pathfinding data`, `scenario cluster data` and each
  PVS's and audibility's per-BSP mappings keep slot 8's element, now index 0.
  The cluster data's BSP reference names the map's own BSP.
- Only zone set 0 stays, with its PVS and audibility entries. Its masks,
  each PVS cluster's bit vectors and its seam cluster references name BSP 0
  alone.
- The designs (B40's soft ceilings), the soft ceilings and both seams
  references are cleared, as are B40's other insertion points and their 36
  player starts.
- Every placement's origin BSP is 0 and it may attach to BSP 0.
- B40's mission content goes with the rest of the clears: crates (on BSP 0
  they would spawn in the map), device groups, object names, cutscene flags,
  cinematics, AI objectives, reference frames, UI objectives, AI hints and the
  script point sets (the last two name B40's BSPs by index).

The baked scenario shrinks from 7.1 MB to about 0.27 MB. `CANVAS_BSPS=1
convert_ce_map.sh` keeps the canvas's BSPs (index 8, `blam.active_bsps` only).

**Scenery collision.** The game ships no Blam rocks or trees whose collision a
placement could borrow, so `tools/level/merge_ce_collision.py` adds the
scenery's own collision models to the BSP's collision first:

- the exporter stages each scenery tag's collision triangles
  (`collision/*.json`);
- every placement's triangles go in as standalone two-sided surfaces;
- the compiled MOPP gives every surface a key, so players and vehicles stand
  on and run into rocks and trees as in CE;
- `mjolnir level collision` puts them into the BSP tree as well
  (`blam_sbsp::scenery`), so queries that walk the tree, projectiles among
  them, meet them too: every leaf a scenery triangle passes through is split
  on the triangle's plane into two flagged copies of itself that name the
  triangle, the rule the simulation's line test uses for two-sided surfaces
  between open leaves. Where the scenery does not fit the BSP's 16-bit tables
  it goes to instances of its own, each with such a tree (until 2026-10-03 no
  leaf named a scenery surface, and bullets went through the Covenant
  shields).

**Surface materials.** The game picks footstep sounds, tire dust and bullet
impacts from each collision surface's material. Each surface keeps its CE
collision material (`convert::Options::keep_materials`), and `mjolnir level
collision` writes the BSP's `collision materials` block with one entry per CE
material. Each entry's render method is the game's own `shaders\<material>`,
and its runtime global material index is that shader's `material name` looked
up in `globals`.

| CE shader `material type` (header +34) | game material |
|---|---|
| dirt, sand, stone, snow | `tough_terrain_dirt`, `_sand`, `hard_terrain_stone`, `soft_terrain_snow` |
| wood, leaves | `tough_organic_wood`, `soft_organic_plant` |
| metal hollow / thin, metal thick | `hard_metal_thin`, `hard_metal_thick` |
| rubber, glass, force field, water, ice | `tough_inorganic_rubber`, `brittle_glass`, `energy_hologram`, `liquid_thin_water`, `hard_terrain_ice` |
| anything else | `default_material` |

`merge_ce_collision.py` adds two corrections before the conversion:

- **Grass.** CE has no grass type. Blood Gulch's ground is one "sand" shader,
  blended, whose secondary detail map is grass. Each of its surfaces is
  sampled through the render geometry: the base map's alpha at the surface's
  points (low alpha shows the secondary detail). Surfaces that are mostly
  grass get `tough_terrain_grass`, 1,178 of 2,423 on Blood Gulch.
- **Scenery** carries no shader, so its material comes from its name: rock,
  wood or plant, and the Covenant shield (`c_field_generator`) takes the
  Jackal shield's `energy_shield_thick_cov_jackal`, an energy material made to
  stop small-arms fire (`energy_hologram` is the hologram decoy's). Whether
  every projectile stops on it is still to be seen in game.

Gephyrophobia has more than 8,191 surfaces, so its `structure_physics` uses
one whole-instance key (see above). Havok contacts there may report one
material even though the surfaces carry theirs. Untested.

### The terrain, scenery and sky (step 3)

`tools/level/merge_ce_scene.py` puts everything static into the BSP's glTF.

- **Scenery:** every scenery placement's model goes in at its CE position and
  rotation. CE's rotation (yaw, pitch, roll) is (Rz(-yaw) Ry(pitch)
  Rx(-roll))^-1: yaw about z, then pitch and roll about the world's y and x
  axes, the Halo Asset Blender Development Toolset's order. The collision
  merge, the lens flares and the sound emitters use the same order. Until
  2026-10-08 they pitched and rolled in the object's own frame, so a
  placement with yaw and a tilt leaned the wrong way: Ice Fields' beacons
  stood on one edge. Over the 19 maps' tilted scenery, the toolset's order
  sits a placement's base flatter on the BSP in 58 of the 73 placements
  where the two differ.
- **Beacons are seated** (`tools/level/ce_seat.py`). CE leaves some beacons
  rocking on one edge of their base: upright on a slope, or tilted one way on
  ground that falls two ways. A beacon whose base spans more than 0.1 m over
  the BSP is turned onto the plane fitted to the ground under its base,
  keeping its heading, and set 0.03 m above it, as CE's well-placed ones are.
  The scene and collision merges and the lens flares all seat from the same
  placement. On Ice Fields 8 of 51 beacons move. Flag bases, which CE puts
  0.011 wu (3.4 cm) over the floor on every map, are all set down to 5 mm.
- Scenery is lit as CE lights objects. An object has no lightmap of its own:
  CE samples the ground under its bounding sphere's centre and four points
  0.7071 of its radius out, averages the lightmap colour L, the incident
  direction and the floor's base colour, and lights the object with an
  ambient of 0.4 L + 0.03, a light of colour L from the incident direction,
  and a bounce of the floor colour (times L's brightness) off the ground,
  which lights the faces that look down. The merge writes each placement's
  brightest lighting as one texel of `object_lighting.png` (materials
  `<shader>__lmobj`) and gives each vertex an incident direction whose dot
  with its normal is that vertex's share, so the environment master's
  bumped-lightmap term (full weight) shades it. Without it, Longest's dark
  steel barricades drew as flat black shapes.
  The page has eight columns of the same blocks: the light, CE's reflection
  tint for the object (`clamp(3D + 0.5) × clamp(2L + 0.25)`, times
  `clamp(1.5 × brightness + 0.25)`), then the object's change colours A–D.
  A change colour comes from the tag's permutations as CE picks it: the
  weights are running cut-offs against a value drawn from the placement's
  position, and the colour is a blend between the permutation's bounds.
  The draw is our own hash, so the mix of colours matches CE but a given
  crate's colour may not.
- **Machines:** placed like scenery, in their rest pose. A part a machine's
  `device position` animation moves (Infinity's beam emitters: the beam
  rises 1,089 wu out of the base and grows from half size to full) draws
  with a material of its own on a device variant of its master
  (`M_CE_Transparent…Device`), which moves it as a World Position Offset:
  the node's offset and scale between the animation's first and last
  frames, about the node's origin, by the device position. A gear runs its
  position from 0 to 1 over its position transition time and starts again;
  any other machine (doors, platforms) is drawn at the position it is
  placed at, because the simulation moves it and Unreal never hears of it.
  A part that turns, whose parent node moves, or whose frames leave the
  line between the first and last stays still, as do opaque parts (no
  opaque device master yet). The mesh's bounds scale (`bounds_scale` in
  the spec) keeps it drawn wherever the part goes. halo2ue stages the
  machine's device and machine fields, its placement's device flags and
  the animation's frames in `placement.json` (`device`).
- **Sky:** the sky model (dome, ring, clouds, horizon) goes in with its
  origin, the viewer, at the map's centre. It is scaled so its nearest layer
  is 3 km away (the ring ends up about 46 km out).

The scene becomes two meshes, written into shipped basic shapes in the game's
own serialisation ([ue_mesh_write.md](ue_mesh_write.md)). Each is normalised
into its donor's bounds, and MJOLNIRLevelLoader spawns it at the position and
scale that undo the normalisation.

| Mesh | Donor | Container | Holds |
|---|---|---|---|
| Opaque | `/Engine/BasicShapes/Cylinder` | `pakchunk989-MJOLNIRMESH` | terrain and scenery |
| Transparent | `/Engine/BasicShapes/Cone` | `pakchunk987-MJOLNIRMESHT` | sky, lights, teleporter fields |

A rewritten mesh enters Unreal's translucency pass only through its single
donor slot ([re/fork_renderer.md](re/fork_renderer.md)), so the transparent
mesh's slot 0 is its first section, the sky.

Each mesh carries:

- one section per glTF material, i.e. per (CE shader, lightmap page);
- the CE lightmap UVs as a second UV channel (`--lightmap-uvs`);
- CE's bump tangents;
- the incident radiosity vector, in each vertex's tangent frame, as the
  vertex colour: the unit direction in rgb, and in alpha its length, which
  weights the bumped-lightmap term.

CE's bitmaps import with their own mip chains (DDS). CE's detail maps fade
their smaller levels to neutral grey, which is what keeps detail tiling from
showing at a distance; a regenerated chain would not.

### Materials (step 3)

The terrain draws with real materials that reproduce CE's shaders.

**How they're built and shipped.** The Unreal project in
[`unreal/MJOLNIRMaterials`](../unreal/MJOLNIRMaterials) (UE 5.5) builds and
cooks them:

1. `tools/level/ce_material_spec.py` lists every bitmap a surface samples,
   lightmap pages and cube maps included, and one material per mesh section
   with the CE shader's fields as parameters.
2. `Scripts/build_ce_materials.py` builds the master materials.
3. `Scripts/build_ce_level.py` imports the level's bitmaps.
4. `tools/ue/cook.ps1` cooks them into `pakchunk988-MJOLNIRMAT`.
5. At load, MJOLNIRLevelLoader makes a dynamic instance of a master per mesh
   slot and sets that slot's textures and parameters.

Cooked material instances are not used: the game crashes loading one.

**What it took to make a stock-cooked material draw in the fork.** See
[re/fork_renderer.md](re/fork_renderer.md):

- the fork's uniform buffer layouts;
- its 44-float4 GPU-scene primitive stride;
- `r.CompileShadersForDevelopment=0`.

The project's `MjolnirForkLayouts` plugin recreates the first two before
anything compiles.

**The shading.** It is CE's fixed-function math, done in the bitmaps' own
gamma space as the hardware did.

| Pass | What the material does |
|---|---|
| Texture | Base map, then the primary/secondary detail blend: by the base map's alpha for *blended* shaders, by the secondary map's alpha for *normal* ones. Then the micro detail. Each with its function: 0 `2·B·D`, 1 `B·D`, 2 `B + 2D − 1`. Each step clamped. |
| Lightmap | `lightmap × material colour × mix(1, N·L, incident weight)`. N is the bump normal, L the baked incident direction. Plus self-illumination: primary, secondary and plasma channels, each animated between its off and on colour by CE's periodic functions. |
| Frame | lightmap pass × texture pass, no 2× |
| Specular lightmap | Shaders with the "lightmap" specular flag. `mix(parallel, perpendicular colour, N·E) × brightness × lightmap luminance × (R·L)⁸`; ³² for "extra shiny", ×2 for "overbright". |
| Reflection | The cube map, in D3D face order, sampled along the eye vector reflected about the bump normal (the vertex normal for a flat cube map). `mix(c⁸, c, tint) × brightness`, where tint and brightness go from their parallel to their perpendicular values by the squared view term. Added, masked by bump alpha × the texture pass's specular mask. |
| Alpha test | On the bump map's alpha: `> 0x7F` passes. |
| Fog | The sky's outdoor atmospheric fog: `max density × saturate((depth − start) / (opaque − start))` towards its colour. |
| Corners and sun | Not CE's: `lightmap_bake` (crates/ue-texture) traces the merged scene for each lightmap page, at up to 16 times its size (2,048 at most), into a texture of its own (`<lightmap>_bake`, BC1 with mips). Red is ambient occlusion within 1 m, divided by a knee of 0.85 (`--ao-knee`) and raised to 1.3 (`--ao-curve`), so the mild folds between a cliff's facets read as open while a wall's foot keeps its darkness: as traced, every fold took a dark line and the cliffs showed their triangles (Blood Gulch, 2026-10-05). `--ao-smooth` (world-space smoothing) is off by default; at 1 m it washed out the wall-floor corners and drew dashes along them. The masters read it through a 3 x 3 tent a texel apart. Blue is the sky's detail: sky visibility (`--sky-rays`, to any distance) over its mean across 1.5 m of surface facing the same way, x 0.5, so 0.5 is as CE's lightmap has it; where CE had shade the masters multiply the lightmap by it (`SkyDetail`, clamped to 0.5-1.5; `mjolnir_terrain_shadows sky <strength>`), which shades the overhangs and crevices CE's lightmap is too coarse for. A bake the loader imports at runtime (`mjolnir_terrain_shadows lightmap`) goes through `M_CE_LinearCopy`: `ImportFileAsTexture2D` is always sRGB, and drawn as it was every runtime bake and sun mask arrived sRGB-decoded (128 as 55), too dark. The lightmap is multiplied by `red ^ BakeAO` (1.4: Blood Gulch was approved at 2.5, found a little dark across the maps at 2.0, and with the knee and curve chosen at 1.4). Green is where CE's sun reaches: the share of the colour drawn as Unreal sun light (so a player or vehicle shadows the ground) is kept to it, and taken down only as far as the lightmap's shadow level (`environment.sun.lightmap_sun`, which `gen_ce_level.py` measures on sun-facing surfaces: the lower quartile of the lightmap's luminance where the bake has shadow, since lamp-lit interiors count as shadow too, and the median where it has sun). A shadow therefore never reaches through a roof onto ground CE had in shade, and a baked shadow is not darkened twice. |

Object shaders (`shader_model`: Covenant crates, rocks, trees, vehicles)
use the same master with `ModelShader` on, for the terms that differ:

- the multipurpose map's masks, in the PC order: red auxiliary, green
  self-illumination, blue reflection, alpha change colour;
- the detail map applies where the detail mask says (none, or one of those
  four masks, plain or inverted);
- the object's change colour (from the object lighting page) tints its light
  where the change-colour mask is set; this is where Covenant crates get
  their white, teal, red or purple panels;
- the reflection is the cube map's colour as it is, times the tint and
  brightness between parallel and perpendicular, masked by the reflection
  mask, faded between the falloff and cutoff distances, and scaled by the
  object's reflection tint;
- "detail after reflection" (flag bit 0) applies the detail function to the
  lit, reflected colour instead of the base map;
- self-illumination animates between its lower and upper colour, masked by
  green.

Transparent chicago shaders (lights, the teleporter field) work like this:

- up to four maps, each with its own UV scale, offset, rotation and
  scrolling animation;
- each stage folds the next map in with its colour and alpha functions
  (current, next, multiply, double multiply, add, add-signed, subtract,
  blend by alpha);
- the result is drawn with the shader's framebuffer blend: alpha blend, add,
  or multiply. Subtract, min and max have no Unreal blend mode and fall back
  to alpha blending;
- a shader with no bitmap on any stage (Danger Canyon's and Ice Fields'
  light shaders reference none) draws nothing, as in CE: it is added at a
  zero tint. Drawn with the master's default white map, it was a solid
  white box;
- a shader with CE's two-sided flag (bit 2: the Covenant shields, the
  teleporter shields and cones, the powerups) takes a two-sided master,
  `M_CE_Transparent{Add,Alpha,Mul}TwoSided`, since an instance cannot turn
  two-sided on. With one-sided masters the shields drew from one side only
  (playtest, 2026-10-03). halo2ue's `double_sided` is true for every
  transparent shader, so only the flag decides.

Water (`shader_transparent_water`: Death Island, Battle Creek, Gephyrophobia,
Damnation) is drawn by `M_CE_Water`, in the transparent mesh:

- the reflection cube map, sampled along the view reflected about a normal
  bent by two panning layers of the ripple map (the shader's ripple angle,
  velocity and scale);
- tinted and faded by the view angle, from the perpendicular brightness and
  tint (looking straight down) to the parallel ones (grazing), on a steep
  curve (`FresnelPower` 3);
- added over what is under the water, scaled by the brightness and, when
  the shader's first water flag is set, by the base map's alpha: the base
  map is a mask, never a colour (drawn as one, the sea was an opaque white
  sheet, 2026-10-02). Brightness is not opacity: Battle Creek's water is 1.0
  at every angle and its creek bed still shows. The second flag (the base
  map's colour tints the background) has no additive form and is not drawn.

halo2ue's water parser read every field after the base map at the wrong
offset (its tag lookup moves the reader), so brightness, tint, ripples and
the reflection map all came out zero; it reads them at their fixed offsets
now.

**Colour reaching the screen unchanged.** Each material:

1. decodes its result to linear;
2. divides out the camera's exposure (`EyeAdaptationInverse`);
3. hands the tonemapper CE's own colour.

The level's post-process volume (`environment.post`) turns the filmic curve,
gamut expansion and blue correction off, so the tonemapper leaves it as it is.

**Where the data comes from.** `halo2ue-export` stages:

- the lightmap vertices: in a cache file they follow the rendered vertices
  in the same blob;
- cube maps as six faces, plus the specular colours, the three
  self-illumination channels, every chicago stage and the sky's fog;
- each vehicle's team and per-game-type spawn flags, from which a match
  picks CE's vehicle sets (see "Vehicle sets").

Without the Unreal editor (`CE_COOK=0`) the converter falls back to
`tools/level/ce_textures.py`: one composited texture per shader on a shipped
material, with no lightmaps.

### Ambient sound (step 3)

The game ships none of CE's ambience as Blam sound tags. Its 163 looping
sounds are material, vehicle and weapon loops, and the remake's ambience
lives in its own Unreal levels. CE's sounds therefore come from CE's files
and play through Unreal's own audio engine, which the game runs beside its
own.

1. **Extract.** `tools/level/ce_sounds.py <map> <sounds.map> <staging> <out>`
   reads a Custom Edition map (cache version 609). Its sound tags are
   indexed: `sounds.map` holds each whole tag as `<path>` and its samples as
   `<path>__permutations`; the docstring has the layouts. The script
   extracts:
   - the **sound scenery** (halo2ue's `sound_scenery` placements), such as
     the teleporter hum;
   - the **looping sounds placed objects carry** as attachments (halo2ue's
     `sounds` on an entry), each an emitter at its marker: the Covenant
     shield generator's and uplink's hum, the teleporters' loop, Wizard's
     klaxons, the beam emitters. A marker on a machine's moving part moves
     with it (`marker_motion`, the part's device motion): Infinity's beam
     loop hangs on the beam, which rises 1089 wu every 15 s, so CE plays it
     for about a second as the beam fires. Held at the marker's rest it
     played all the time (2026-10-08). The loader moves it on the world's
     clock and keeps it PlayWhenSilent: with Restart it did not come back
     in time;
   - the **background sound**, the looping sounds the BSP block depends on;
   - each looping sound's **tracks** and detail sounds.

   Xbox ADPCM is decoded to WAV and Ogg is kept as is. A loop's permutations
   are joined into one `_loop` file, because CE plays them back to back.
2. **Import.** `unreal/MJOLNIRMaterials/Scripts/build_ce_sounds.py` imports
   them under `/Game/MJOLNIR/Levels/<map>/Sounds`, which cooks into
   `pakchunk988`. Loops are marked looping, and the compression is ADPCM:
   the default, Bink, needs a decoder the game may not ship.
3. **Play.** `gen_ce_level.py --sounds` writes `environment.sounds`, and
   MJOLNIRLevelLoader plays it:
   - background loops in 2D, map-wide;
   - emitters in 3D at the CE positions, falling off linearly over CE's
     distance bounds.

Detail sounds (random one-shots) are extracted but not yet played.

**Event sounds.** The game engine still has Reach's event list:
`game_engine_globals` holds 510 events, each with a sound and announcer line,
and `megalogamengine_sounds` names 95 mode announcements. But 336 of the 339
sound tags the events name were cut from the build, and 94 of the 95
announcements are empty. The events themselves still fire, and they reach
Unreal as `BlamIncident`s on the game state's
`BPC_MeteoriteIncidentHandlerComponent` (`OnIncident_Event`, which can be
hooked), for example:

- `teleporter_used`
- `respawn_tick`, `respawn_final_tick`
- `death`, `suicide`, `player_spawn`

`ce_sounds.py --events <sounds.map> <out>` extracts every CE announcer line
(Ogg Vorbis; Unreal's importer decodes it) and the UI sounds the events need,
and writes `mods/MJOLNIRLevelLoader/events.json` (event name to waves).
`build_ce_sounds.py` imports them under `/Game/MJOLNIR/Sounds/Events`, and
the loader plays an event's sound on converted multiplayer levels only.
Personal events (teleport, respawn ticks, multikills and sprees) play only
for the player who caused them, taken to be absolute index 0, the host's
first local player. A networked client's index is not exposed to scripts
yet.

The waves are loaded when the level is furnished, and the hook only queues
the event; a 100 ms game-thread loop plays it. Loading and playing inside
the hook froze the game on the first teleport. No game-start event is
raised on a converted map, so the game type's announcement ("Slayer",
"King of the Hill" and so on) plays once per match, picked by the variant
the menu started. It plays when the player's pawn first exists, because the
opening spawn raises no `player_spawn` (only respawns do), or at the first
`player_spawn` if that comes sooner.

### The level file (step 4)

- **Spawn points.** Under a multiplayer engine players spawn only at scenery
  whose multiplayer type is *player spawn location*; the scenario's player
  starts are not read. One is placed at every CE start (neutral team).
- **Vehicles, weapons, pickups** through `defs/level/ce-tag-map.json`; each CE
  tag maps to the first equivalent the game has a type for
  (`defs/level/palette-map.json`). The bake adds a type the canvas palette
  lacks: the shotgun and the fuel rod (Reach's `flak_cannon`) are not in
  B40's. What has no equivalent is reported as dropped: the flamethrower
  (none ships).
- **Map variant palette** (`blam.map_variant`). Objects with multiplayer data
  exist only through the map variant, which is built from the placements whose
  tags a palette lists. A model variant gets an entry of its own. Grenades,
  the overshield and camouflage also need the game variant's map options
  (grenades, equipment and powerups on map), which `megalo write` sets.
- **Vehicles:** every vehicle the CE scenario places (`--game-type all`),
  hidden until a match's vehicle set picks it (see "Vehicle sets" below).
  The rocket Warthog spawns as the chaingun Warthog
  (`VEHICLE_VARIANTS` is empty): as the Warthog's `rocket` model variant
  (`permutation data.variant name`) its turret had no Unreal actor
  Blueprint, so the gun was invisible and the gunner vanished (playtest,
  2026-10-03). Banshees and Scorpions start 0.3 wu above CE's height and
  every other vehicle 0.05 wu (`VEHICLE_LIFT`), with the at-rest placement
  flag cleared so they fall into place: at CE's height on Blood Gulch's roofs
  the Banshees started inside them and were thrown on their sides.
- **Weapons and equipment** start 0.05 wu above CE's height (`ITEM_LIFT`)
  with the at-rest flag cleared, and fall into place. CE places items
  0.001 wu over the floor, and the bake creates objects at rest (placement
  flag `0x20`), so the part of a weapon below its origin stayed in the floor
  (playtest, 2026-10-03). Levitating powerups (CE's `levitate`, on Battle
  Creek, Hang 'Em High, Rat Race and Timberland) stay at rest where CE put
  them.
- **Respawn times.** Each weapon and pickup respawns after CE's time: its
  placement's, else its item collection's (halo2ue's
  `collection_spawn_time`), else 30 s. Vehicles respawn after 30 s and are
  given back 30 s after being left away from their spot. A map variant object
  with spawn time 0 never came back. Every respawn time is spread by 0-10 s
  per placement (`RESPAWN_SPREAD`): with flat times, every object the
  simulation had not placed came back in the same tick, and on Death Island
  that stall reset the round every ~34 s, putting every player at a spawn
  point without a death (2026-10-08).
- **Teleporters:** a sender at every CE "teleport from" flag and a receiver at
  every "teleport to" flag. The simulation keeps Reach's multiplayer
  teleporters, which pair ends by channel. CE numbers a map's channels freely
  (Gephyrophobia uses 2–7, 13 and 14; Infinity 11–24), so the generator
  renumbers each map's channels from alpha in CE order, across the scenario's
  26 (alpha to zulu), and warns about a channel missing either end. Past
  zulu the field takes the raw number, which pairs just as well: the
  simulation compares the channel byte. The first version kept only channels
  0–5 and dropped the rest silently, which left Gephyrophobia with half its
  pads.
- **At most 32 teleporters.** The simulation keeps a table of 32
  teleporters, filled from the map's sender, receiver and 2-way scenery
  (`HaloSimulation_tag_release.dll` 0x1803e7670 on CU4). An end past the 32nd
  sends nothing, and nothing lands on it. Chiron TL-34 placed 60 ends, so
  about half its pads did nothing. The generator warns past 32.
- **Two-way pads.** CE has no two-way teleporter. A pad that both sends and
  receives is two channels whose "teleport from" and "teleport to" flags sit
  on top of each other at both ends. All of Chiron TL-34's pads are like this,
  as are Gephyrophobia's, Sidewinder's, Boarding Action's and others. Where a
  channel's "from" flag lands within the sender's boundary of another
  channel's "to" flag, the reverse holds too, and the facings agree, the
  generator merges the two channels into one. It places a "teleporter 2way"
  at each pad, at the "to" flag with its facing. That halves the ends:
  Chiron's 60 become 30 on 15 channels.
- **Room to land.** The simulation lands a player at the receiver's (or
  2-way's) origin, but only if a Spartan fits there. It tests the biped's
  shape (radius 0.175, standing height 0.65, from 0.2 up) against the
  collision. A receiver that fails is skipped, and a sender with none left
  raises `teleporter_blocked`. CE has no such test and puts its "teleport to"
  flags at the back of their alcoves. Every Chiron TL-34 landing spot had
  0.17–0.25 to the wall behind it, and pads landing at 0.166 and 0.182 never
  sent. The generator moves each landing end forward along its exit facing,
  up to 0.15, until the Spartan clears CE's collision (the staging export's
  `bsp/collision_N`) by 0.25. On Chiron 28 of 30 move, by 0.02–0.09.

  The two games turn the player differently:
  - **CE** turns the player to the "teleport to" flag's facing.
  - **Reach** keeps the facing relative to the sender, whose front faces the
    player walking in.

  With CE's flag facings, players had to walk in backwards to exit the right
  way. So each sender is turned 180° from its CE flag, and walking in head-on
  exits facing the receiver's direction, as in CE.
- **The post-process volume** (`environment.post`): fixed exposure, no local
  exposure, no filmic curve. The CE materials then show CE's colours
  ([re/fork_renderer.md](re/fork_renderer.md)).
- `"multiplayer": true`, `blam.active_bsps`, `blam.single_bsp`, the scenario
  `type` set to multiplayer.

### Capture the Flag

A map whose CE scenario has a CTF flag for each team offers CTF in the
multiplayer menu (`"modes": ["slayer", "ctf"]`). No CTF ships in this build:
there is no variant, no flag object and no flag mesh, so each piece is ours.

- **The rules** are a Megalo variant, `variants/ctf.mglo`
  (`mjolnir megalo write --mode ctf`, `crates/blam-megalo/src/ctf.rs`). The
  script makes each team's flag on its stand, scores a capture when the
  carrier stands in their own stand's boundary while their own flag is home,
  returns a dropped flag when its own team touches it or after 30 s, and ends
  the round at 3 captures. The flag incidents (`flag_grabbed` 110,
  `flag_dropped` 112, `flag_scored` 116, `flag_reset` 118, `flag_recovered`
  119) carry the flag's team as their value (Unreal's `CustomValue`), so
  the loader plays CE's team lines ("Red team has the flag", "Blue team
  score", "Red team flag returned"). The action and condition encodings
  match ReachVariantTool's opcode list; they are checked against the CU4
  decoder in [re/megalo_variant_format.md](re/megalo_variant_format.md).
- **Teams.** Each CE start is labelled `ctf_spawn_red`, `ctf_spawn_blue` or
  `ctf_spawn_none` and placed neutral. The variant gives the red and blue
  spawn points their teams, and parks the rest on a team no player is on.
  It waits 2 s before the first spawn (the loadout camera time), so the
  first tick has set the teams up; a spawn on tick 0 used them neutral.
- **The flag** (`tools/level/build_ctf_flag.sh`) is a weapon cloned from the
  assault bomb, which ships whole and is carried the same way. It is entry
  18 of the multiplayer object type list, which the script needs before it
  can create one. The bomb binds no Unreal actor, so the flag borrows the
  oddball's `BP_SkullActor`. MJOLNIRLevelLoader hides the skull, removes its
  fire effect and whispering audio, and attaches CE's own flag mesh in its
  team's colours. The mesh is exported by halo2ue and rewritten into
  `/Game/MJOLNIR/CTF/SM_CE_Flag`; its textures come from
  `tools/level/ce_flag_textures.py`. The stand needs no mesh: CE's own flag
  base scenery sits at each flag and comes in with the map.
- **Armour colours.** In a team game the loader puts every Spartan in the
  classic Mk V armour, whatever the player picked: only its material takes a
  colour. The others (Chief's default, MkIV, Blamite, Lone Wolf, the
  coatings) bake theirs into textures, so a Chief-armoured player stayed
  olive on Blue. Each mesh component's class (`BPC_SkeletalMesh_C`,
  `BPC_FP_SkeletalMesh_C`, ...) names the Mk V mesh it gets. The loader then
  gives each Spartan's armour,
  and the local player's first-person arms, legs and shadow, a dynamic
  instance with `Armor Color` set to red or blue. The parameter is read at
  global association with index **0**: the plain setter writes index -1,
  which this layered material never reads, so it must be set by info. A
  respawn reuses the actor and puts the stock armour back, so the loader
  re-tints after every spawn.

### Vehicle sets

CE decides a map's vehicles per game type. Each scenario vehicle has a team
index (0 red, 1 blue) and spawn flags: bits `0x1`-`0x8` put it in Slayer's,
CTF's, King's and Oddball's **default** set, bits `0x100`-`0x800` **allow**
it when a game variant uses custom vehicle settings. A game variant picks a
set per team: DEFAULT, NONE, one type (WARTHOGS, GHOSTS, SCORPIONS, ROCKET
WARTHOGS, BANSHEES, GUN TURRETS), or CUSTOM (0-4 of each type). Placing
every game type's vehicles at once put 46 on Death Island, more than the
simulation keeps, and it reset the round every ~34 s (2026-10-08).

Reach does the same with Megalo labels:

- `gen_ce_level.py` places every vehicle with the spawn flag "hide unless
  megalo required" (`0x4`), its CE team as the owner team (defender/attacker),
  and a label `ce_<type>_<rank>`. The type is CE's set category (a rocket
  Warthog stays `rwarthog`). Within a team, a type's vehicles rank by how
  many game types they are default in, and the k-th of each team share the
  label. The level's `vehicle_sets` lists every vehicle's type, team, label
  and CE's default and allowed game types.
- The simulation places a hidden object only if the game variant has an
  object filter on its label; a filter with a team constraint places only
  that team's (both seen on Death Island, 2026-10-08). The variant holds 16
  filters: 17 put every object out of play and lost the GPU device, and so
  did a filter minimum count above 0. Hence the shared labels: the stock
  maps' sets are symmetric, and a default set needs at most 9 filters.
- `mjolnir megalo write --vehicle-label-pool` writes every label
  (`ce_<type>_1..10`) into the variant's string table and a
  `<mode>.layout.json` beside it: the bit the filters start at (they end the
  stream), the variant's own filters, and each label's string index.
- When a match starts, MJOLNIRLevelLoader (`vehicle_sets.lua`) reads the
  host's vehicle settings from the settings line (`vehicles.<team>`,
  `vehicles.<team>.<type>`), picks each team's labels, and appends one filter
  per label: none of a team constraint if both teams take it, else the team's.
  A custom count takes the lowest ranks CE allows in the game type; filters
  past 16 are left out, highest ranks first, and logged. Every machine
  computes the same filters from the same line and level.
- The host sets them on the RED VEHICLES and BLUE VEHICLES pages of GAME
  SETTINGS (`MJOLNIRLobby/Scripts/settings.lua`).

Death Island places Banshees and Warthogs when the round begins, and its
Ghosts, Scorpions and Shades only when their respawn time (30-40 s) runs out,
with or without labels; Infinity places everything at once. Not yet
explained.

### Health packs

This game ships no health pack (no object, no Unreal asset, none placed in
the campaign), and its health never recharges, as CE's did not. So every
variant the loader ships carries CE's health packs as Megalo script
(`crates/blam-megalo/src/powerups.rs`, on by default in
`mjolnir megalo write`):

- Each CE health pack becomes a spot, invisible scenery labelled
  `ce_health_pack` (`objects\multi\powerups\health_pack_spot`).
- Each tick, a spot with no pack whose countdown has run out creates one: the
  equipment `objects\multi\powerups\health_pack`, multiplayer object type list
  entry 19, which nobody can pick up.
- A living player whose biped comes within reach of the pack (8 feet, origin
  to origin, by the Get Distance action) and whose health is under 100% is
  healed to full (Modify Object Health); the pack goes, and comes back after
  30 s. Shields are left alone.
- The pickup raises Race's `lap_complete` incident, and the loader plays CE's
  `pickup_health` to that player. `recharge_health` would be the natural
  incident, but the simulation never hands it to Unreal.
- The pack is cloned from the battle rifle ammo pickup (no CE map places
  battle rifle ammo), and the loader puts CE's health pack mesh
  (`/Game/MJOLNIR/CE/Powerups/SM_CE_HealthPack`) on that actor in place of
  its own. The pack is made 0.1 wu above its spot and falls, so the crate can
  come to rest tipped on its side. The mesh keeps the world's up and the
  crate's heading, with its base (CE's model origin) at the crate's lowest
  corner, which is on the ground, and is seated again 2 s and 5 s after the
  pack appears.

The actions are Reach's (54/55 get shields/health, 64/65 modify, 66 get
distance), at the same numbers in CU4's decoder.

## Playing it

CAMPAIGN → NEW GAME → the map (the last mission). `"multiplayer": true` tells
MJOLNIRLevelLoader's native half to switch the simulation to the Megalo engine
when that mission starts, and back before any other mission; `"variant":
"slayer"` makes it install `variants/slayer.mglo` (written by `--install`)
where the simulation's variant loader reads it. It needs
`native/mjolnir_map_registry.dll` built from this revision. The patches and
why each is needed are in [re/megalo_engine.md](re/megalo_engine.md); the
manual form of the engine switch, without the variant, is:

```bash
mjolnir live engine --launch-engine 2 --map-variant-gate skip --map-variant-reset skip   # at the main menu
```

The level spawns its terrain once the player pawn exists, so the first
seconds after the loading screen are dark.

## Limits

- **Visuals.** No decals or weather yet. A light a placed object carries
  (the base beacons) is drawn as its lens flare only, never as a light, and
  the flare's brightness follows the object function that scales the light
  (Danger Canyon's beacons: a 1 s cosine; MJOLNIRLevelLoader updates it
  every 40 ms). Dynamic lights
  (headlights, muzzle flashes, the flashlight) light players, vehicles and
  weapons but not the terrain: its base colour holds only the sun's share
  of the baked light (object shadows), and it sits on lighting channel 1,
  which only the level's sun shares. `mjolnir_terrain_lights on` (an
  experiment, needing the trial masters in chunk 983) lights it too: the
  masters top the base colour up to the surface's albedo and take the sun's
  light on the top-up back out of the baked colour, the terrain joins
  channel 0, and the terrain's hidden shadow copy, drawn two-sided, keeps the
  Unreal sun out of CE's shade. The copy's sharp shadow edges and the
  bake's texel steps never quite meet, so with a bake the sun share is
  drawn only where the bake is sunlit all round and the top-up only where it
  is shaded all round (`BakeMargin`, 1.5 texels; `mjolnir_terrain_lights
  margin <texels>`); between them the colour is CE's. At margin 0 Blood
  Gulch's bases traced their crenellations in black around the wall foot
  (verified on Blood Gulch and Coldsnap, 2026-10-05).
  Since 2026-10-06 the default (MJOLNIRLevelLoader 0.4.0, runtime pack
  1.3.0, maps 1.2.0; `mjolnir_terrain_lights hybrid` brings the mode above
  back for comparison) hands the terrain's direct light to Unreal: its base
  colour is CE's sunlit colour (the texel's own lightmap level where CE had
  sun, the level's sunlit level in CE's shade), CE's bump map is its normal,
  and its emissive is CE's colour less what Unreal's sun adds, never below
  CE's ambient. The sun mask (`<stem>_sunmask`, CE's lightmap seen from
  above at 1 m, cooked with the map and named by `environment.sun_mask`,
  tent-filtered) is the sun's light function, so CE's broad
  soft shadows stay and objects darken in them. A trial
  (`mjolnir_terrain_lights on trial`) reads the trial masters and a bake in
  the loader's `bake\` folder in one respawn (two quick respawns were
  followed twice by a GPU crash). `mjolnir_terrain_debug <layer>` shows one
  layer of the terrain's light at a time. Keep the sun's angular size at the
  engine's 0.54 degrees: at 3 the virtual shadow maps leaked light in lines
  across shaded ground and around the first-person gun. Those lights are physical and tuned
  for the campaign's exposure, so the level's sun and sky are raised by
  `environment.light_scale` (256) with the exposure lowered to match
  (docs/level_format.md); without that a headlight turned what it reached
  white. Scenery has CE's object lighting (ambient,
  dominant light, floor bounce, reflection tint) but not its shadow colour
  or point lights; a self-illumination colour that takes a change colour
  does not take it. One converted
  map installed at a time: its meshes override the two donor shapes.
- **Scenery collision** stops players, vehicles and, since 2026-10-03,
  projectiles (checked offline, `scenery_probe`; not yet in game). Each
  node of a collision model is placed by its model node's rest pose: before
  halo2ue did that, a tree's canopy hull sat around its trunk at head
  height (Infinity, 2026-10-04), so maps converted earlier need converting
  again. The trees cost table space: Danger Canyon's 43,646 scenery
  triangles need 17 scenery instances instead of 6, and the maps that keep
  scenery in the BSP grow their 2D references several times over (Blood
  Gulch 55,634 and Boarding Action 58,539 of the 65,535 limit; a map past it
  moves its scenery to instances of its own). See `ce_terrain_collision.md`,
  "Scenery in the tree".
- **Object light colour.** Players, vehicles and weapons are lit by the
  Unreal sun and sky light. On a map with a real sun (its lightmap at 0.8
  or more where the bake has sun) they take that sunlit lightmap's colour,
  since CE lit an object by the lightmap under it; otherwise the sky's
  outdoor ambient colour, or the lightmaps' average when that colour lacks
  a channel. The sky's colour alone can be anything: Infinity's test sky is
  (0.5, 0.5, 0), which turned everything yellow.
- **Approximations in the materials.** CE's noise, jitter and wander
  functions are a value noise; the variable-period functions use their
  nominal period. The plasma self-illumination band's width and the
  "add signed" chicago functions are estimates. The reflection's view term
  uses the per-pixel eye vector where CE used the camera's forward vector.
  Water (`swat`), glass (`sgla`) and the reflection lightmap mask are not
  reproduced.
- **One standalone map installed at a time:** each ships its own override of
  `DT_Scenarios`.
- **More than 8,191 surfaces** (Sidewinder, Infinity, Death Island, ...): the
  static body lists the terrain as one whole-instance key instead of one key
  per surface. Verified on Sidewinder: players walk and vehicles rest on it.
- **One BSP per map.** A map's second BSP is not converted (Coldsnap's is a
  copy of its first).
- **The canvas palette.** Weapons and vehicles the canvas mission never
  places (shotgun, flamethrower, fuel rod, health packs) are dropped.
- **No rocket Warthog.** Rocket hogs spawn as chaingun hogs until the rocket
  turret's tag wrapper points at an actor Blueprint (the chaingun turret's,
  via `ue-asset` tagwrap, or a rewritten mesh with CE's rocket pod).
- **Extent.** Keep a map inside the canvas level's overall extent: lifted 800 wu
  above B40, Havok flung objects hundreds of wu.
- **Game modes.** Slayer only (`mjolnir megalo write --mode slayer --score N
  --out .../MJOLNIRLevelLoader/variants/slayer.mglo` changes the score to
  win). Without the file the map runs the empty default variant: players
  spawn, nothing scores. `--mode tick` scores every player every tick, a
  smoke test for the interpreter. CTF, Oddball and King need their scripts
  written.
