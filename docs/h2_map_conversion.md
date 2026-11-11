# Converting a Halo 2 Map

**Status:** 2026-10-22. Lockout and Ascension convert through the same
command as the Halo 1 maps and start from MULTIPLAYER (`mjolnir_auto host LOK
slayer private`, `host ASC ctf private`): their own worlds, the Spartan
standing in the BSP, the pickups resting where Halo 2 put them, every
material applied. Lockout was played by a person on 2026-10-21; the glass,
snow and sky they found wrong are fixed (reflecting tinted glass, the
chambers' gas behind it, snow where Halo 2 puts it, cloud banks in place of
flat white planes). Ascension was compared side by side with MCC on
2026-10-22: its turning antennas and storm sky match. The Halo 1 pipeline is unchanged; its outputs for Chill
Out and TST are byte-identical before and after the Halo 2 work.

MCC's Halo 2 multiplayer maps (`halo2/h2_maps_win64_dx11/*.map`) become
standalone Campaign Evolved maps the way classic CE maps do
([ce_map_conversion.md](ce_map_conversion.md)): their own collision, render
geometry, materials and lightmaps, player starts, pickups and markers, under
the Megalo engine.

```bash
export HCE_PAKS=".../Halo Campaign Evolved/Meteorite/Content/Paks"
MCC=".../Halo The Master Chief Collection/halo2/h2_maps_win64_dx11"
tools/level/convert_ce_map.sh "$MCC/lockout.map" LOK out/lok --install
```

`shared.map` and `textures.dat` must sit beside the map (they do in an
install): every weapon, vehicle and most shaders live in `shared.map`, every
bitmap's pixels in `textures.dat`.

## Which game a map is from

`mjolnir cache info <map>` reads the header and names the game, the build and
the tool that stages it ([h2_cache_format.md](h2_cache_format.md), "Telling the
games apart"). `convert_ce_map.sh` asks it first:

| map | stager |
|---|---|
| Halo 1 PC or Custom Edition (version 7, 609) | halo2ue (HalcyonRing), unchanged |
| Halo 2 MCC (version 13, game index 1) | `mjolnir cache stage` (crates/blam-cache) |
| Halo 1 MCC, Halo 3, ODST, Reach, Halo 4, H2A | refused, by name, before anything runs |

The staging's `manifest.json` says which game it came from (`source`:
`halo_ce` or `halo2_mcc`), and the few steps that are CE's alone branch on it:
`ce_fog.py` and `ce_sounds.py` (they read the CE `.map` itself), the
lightmap solver (CE's radiosity: `LIGHTMAP_SCALE` defaults to 0, keeping Halo
2's own pages) and the foliage (CE detail maps: `FOLIAGE` defaults to 0).
`gen_ce_level.py` takes its tag map (`defs/level/h2-tag-map.json`), menu name
and description from the same field.

## What staging does differently

`mjolnir cache stage` writes the files halo2ue writes for Halo 1, in the same
units and axes, so every later step reads them unchanged:

- **Collision.** Halo 2's 16-bit tables are widened into the CE element layout
  (`collision_0.bin`, `layout: "ce_pc_v7"`). Instanced geometry, which CE never
  had, is placed in world space (scale, forward/left/up, position), each
  polygon fan-split into standalone two-sided triangles that keep their
  material and flags, and appended as the `scenery_surfaces` tail CE scenery
  uses; `merge_ce_collision.py` adds the props after it. Lockout: 3,162 BSP
  surfaces, 75 instances (7,312 triangles), 15 crates (840), more than one
  16-bit tree holds, so `level collision` puts the tail behind an instance of
  its own (as Timberland's trees).
- **Surface materials.** A Halo 2 shader names a global material
  (`hard_terrain_concrete`), not a CE material type; staging maps it onto the
  29 the game ships: the same name, else an alias (concrete is stone,
  `energy` is `energy_hologram`), else the name shortened a word at a time
  and tried again the same way (`hard_metal_thin_hum_grating` to
  `hard_metal_thin`), else `default_material`. Each substitution is printed.
- **Render geometry.** Clusters and instanced geometry go into one
  `bsp_0.gltf`, a primitive per (shader, lightmap page), with each cluster's
  and instance's page from the lightmap tag and Halo 2's lightmap
  coordinates. Halo 2's triangles already wind counter-clockwise, so their
  order is kept (CE's are flipped).
- **Shaders.** MCC keeps no shader parameter names; each template's bitmap
  slots and tiling are read in the template's order (`h2::render::template`),
  and what the compiled shaders do was read back from the DXBC in the
  shader pass tags ([h2_cache_format.md](h2_cache_format.md)). Opaque shaders
  become environment-master summaries (base, detail, second detail blended
  by the base's alpha where it is high, the reverse of CE's, bump,
  self-illumination; alpha tested on the base map for the alpha-test
  templates, except the single-pass ones, whose compiled lightmap pass
  discards where the bump map's alpha rounds to 0: Zanzibar's palm fronds,
  beach bushes and tree foliage keep their outline only there, so their
  base map is staged with the bump map's alpha as `<stem>__cut.png`).
  `tex_bump_plasma_one_channel_illum` (Zanzibar's fusion coil cores) is a
  lit base and detail plus the plasma pass's glow from bitmap 3: red times
  a band of its alpha around pixel constant 2's, plus green and blue each
  times a pink pixel constant. It becomes CE's three-channel
  self-illumination (`<stem>__glow.png`: green, blue, and red x the band
  baked at the shader's level, tinted by pixel constants 3, 4 and 5; a
  colour image in one channel drew white). Read as a detail map, its
  magenta channels drew a pink and black grid. `overlay` (Zanzibar's Camp Froman sign, the
  military crates' stencils) is 2 x base x tint, drawn as a double
  multiply. On Zanzibar the multiply master draws nothing in the after-DOF
  translucency pass (a black multiply on the sign stayed invisible, and
  appeared with `r.SeparateTranslucency 0`; the same black multiply draws
  on Chill Out's glass, cause not found), so the multiply is baked into an
  alpha-blended copy,
  `<stem>__overlay.png`: black at 1 - m where the overlay darkens the
  frame by m (exact), clear at neutral grey and where it brightens: no
  blend brightens whatever lies under it, and as its hue at (m - 1) / 2 a
  crack map's near-grey laid a pale sheet over Sanctuary's dark ceilings. `water_edge_blend` (Zanzibar's flat plane at sea level)
  writes its map's alpha into the frame's alpha only, a mask the water
  fades by; its geometry is left out (drawn opaque without a map, it was a
  big white patch on the beach). Water (`water_pool`, `water_pool_cube`:
  Beaver Creek's creek, Coagulation's cave pool, Sanctuary's streams) mixes
  the rippled frame behind with its reflection map by a fresnel term (its
  fresnel map's alpha: 0 looking straight down, 0.72 at a grazing angle).
  It goes in as CE's own water (`swat`, M_CE_Water): the reflection (a cube,
  or a 2D reflection map on all six faces) along the normal rippled by its
  ripple map (bitmap 0, a normal map as CE's ripples are, in two scrolling
  layers), added into the frame, weighted from 0 straight down to 0.72 at
  the edge (flag 0 over the master's white base). Drawn as a chicago cube
  blended over the frame, Beaver Creek's creek was an unmoving glossy
  picture of its reflection map. Waterfalls (`waves`) are
  min(1, mask x A + mask x B) x C, each scrolling: CE's four-stage chain
  as (A + B) x mask x C. `tex_bump_illum_3_channel` (Backwash's blue lights)
  has a grey detail before its base, and its glow map's channels tinted by
  pixel constants 4, 6 and 7 as CE's three self-illumination colours. An
  alpha-tested template that cuts out on its bump map keeps a placeholder
  base (Backwash's canopy, color_black), taken to the bump map's size.
  `tex_detail_blend` (Sanctuary's ground, the Mombasa trees) is a base and
  two details blended by its alpha, the details' scales in vertex constants
  2 and 3; `tex_illum` and `tex_illum_bloom` (Backwash's fungus,
  Triplicate's lights) a base, a detail and a glow map; `decal_simple`
  (Street Sweeper's road stripes, Headlong's signs) its one map alpha
  blended. A template with no slot layout falls back to the shader's
  runtime diffuse map, drawn opaque, which is how these lost their details,
  glow and cut-outs.
  Halo 2 tiles each map by a u and a v scale, and many are uneven (the palm
  bark's detail and bump 2 x 12, the beach's sand 128 x 64); CE's
  environment shader takes one scale per map. The base map's tiling is in
  the UVs; a detail or bump map tiled unevenly relative to it is staged as
  a copy repeated to the ratio (`<stem>__x<nu>y<nv>.png`, at most 16 a
  side) and drawn at the smaller scale. Read as u alone, the palm's detail
  was stretched six times along the trunk.
- **Decals.** The scenario's decals (Zanzibar's 40 caution, safety and
  warning signs, the CAUTION over the beach gate) go to the placement's
  `decals` with their bitmap, radius and the bitmap's aspect.
  tools/level/gen_ce_level.py lays each as a quad on the nearest surface
  within 3 m, by true distance over every triangle whose bounds come that
  close (by centre, the flywheel room's sign missed its big wall triangle
  and went onto a slanted face, tilted and half buried), its longer side twice the
  radius, drawn with the transparent alpha master over the cooked bitmap;
  tools/level/ce_material_spec.py cooks the bitmaps with the map's. By
  layer: lit alpha blend (0, 1) as it is; multiply (3) and double multiply
  (2: bullet holes, scorches, Desolation's and Warlock's team emblems) with
  the multiply baked into an alpha-blended copy (`<stem>__mul<gain>.png`,
  as the overlays, times the bitmap's alpha); max (4) and add (5) on the
  additive master. Drawn as plain alpha, the rust decals were orange blobs
  and the emblems solid bars. Glass (`one_alpha_env`) becomes CE's glass shader: the base
  map tinted by the albedo and facing tints, blended by its alpha, unlit, and
  the environment cube map reflected through the specular mask with the
  environment tint; the cube's six faces are staged in D3D order. The
  two-layer glass (`two_alpha_env_illum`: Turf's storefront and stairwell
  doors, Triplicate's glass rails, the medical tent's panels) has the same
  slots and pixel constants, a second glass layer in slot 4, and goes in
  the same way; `two_alpha_env_detail` (the Forerunner "invisible" glass)
  has only placeholders and draws nothing. Read through the transparent
  catch-all, slot 0's reflection cube was drawn as a picture: Turf's
  stairwell door was an opaque dark sheet with nothing behind it to stop
  a player. `tex_bump_env_alpha_test_combined` cuts out on the base's
  alpha times bitmap 1's (Turf's damaged stucco: a solid door base, the
  splintered boards in `base_stucco1_damaged_01_alpha`; the chainlink
  fence keeps its holes in the base, alpha_white in slot 1).
  Change colours (`tex_bump_one_change_color`: Turf's panel trucks and
  crates) are base x lerp(1, the object's colour, bitmap 2) in the compiled
  lightmap pass; the mask goes in as CE's shader_model multipurpose alpha
  (`<stem>__mp.png`) and each prop placement carries its object's colour
  permutations (obje +0xAC) as `change_colors`, Halo 2's weights (shares:
  the truck's off-white 0.4, red 0.2, tan 0.2) summed into CE's running
  cut-offs, so tools/level/merge_ce_scene.py draws one per placement into
  the object lighting page as it does for CE scenery; a placement's own
  colours (active bits at +0x38, ARGB at +0x3C) win. Read without the mask,
  every truck drew its untinted off-white base.
  Self-illumination (`tex_bump_illum` and its kin) is a pass of its own,
  `default_self_illumination`: saturate(glow map x pass constant 1),
  added over the lit surface, not lit with it (Turf's light fixtures are
  black where they glow). The template's remapping table names the pixel
  constant (2 for tex_bump_illum, 0 for tex_bump_illum_no_specular); an
  animated parameter on descriptor 0x81 drives it instead, a periodic
  colour function going in as its wave between its darkest and brightest
  non-zero colour (the storefront signs jitter between 0.46 and 0.5). The
  environment master adds it after the fog when `SelfIllumAdd` is set. The "two
  plus two" shaders (the sky's cloud banks, the containment gas) are mask x
  layer x layer, tiled and scrolling as the shader animates them, alpha
  blended; the plasma shaders (`plasma_alpha`: Zanzibar's flywheel
  lightning, the teleporter beams, Lockout's grav lifts) draw with
  `M_H2_PlasmaAlpha` (`unreal/MJOLNIRMaterials/Scripts/build_h2_materials.py`,
  `/Game/MJOLNIR/H2`, chunk 981 beside the runtime pack), the compiled
  shader as it is: noise A's blue and noise B's red, each scrolling, banded
  into a sharp ridge where they meet and twice more inside it, coloured
  between pixel constants 1 and 0 by the second band plus 3 on the
  innermost, faded by the mask's alpha, added. The staging keeps a chicago
  approximation beside it (`h2_plasma` in the shader summary; without the
  master, noise x noise x mask in the bands' mean colour drew soft clouds). All of these draw in the
  translucent mesh.
  Opaque `env` templates (the `tex_bump_env` family) reflect their cube map
  as Halo 2's lightmap pass does: the cube along the reflected eye vector,
  times a colour and a brightness each between the glancing and the facing
  value, masked by the albedo's alpha and dimmed with the light, added to
  the lit surface. The cube is whichever of the shader's bitmaps is one;
  the template's black placeholder cube reflects nothing. 22 of the 24 maps
  have such surfaces (Lockout only its grav pads; Ascension its Forerunner
  windows and panels).
- **Sky layers.** Besides the alpha and "two plus two" layers, Ascension's
  sky uses two more templates, read back from their compiled shaders: the
  cloud cover (`sky_two_alpha_clouds`: a cloud map tiled 8x and scrolling,
  times a cover mask, colour and alpha, alpha blended) and the sun shafts
  (`sky_one_add_illum_detail`: a mask's colour times its alpha, times a
  scrolling detail, tinted, added). Drawn as one map each, the cloud map
  covered the whole dome in flat grey and the shafts were white wedges.
  Additive clouds (`two_add_clouds`, `sky_two_add_clouds`: Tombstone's sky
  dome, Gemini's sky, the recharge stations' glow) are min(1, 2 x bitmap 0
  x bitmap 1), faded by pixel constant 0's alpha: CE's double multiply, or
  bitmap 0 alone where bitmap 1 is default_multiplicative (50% grey).
  The Covenant holo panels (`two_add_detail_masked`: Midship, Desolation,
  Gemini) compile to the same product of the panel map and a static map,
  plus a readout tiled 4 x through the panel's alpha; they go in as the
  clouds do, without the readout. Drawn from the static alone, they were
  solid white blocks.
  Lightning (Colossus, Triplicate) has that alpha at 0 and flashes by an
  animation the conversion doesn't carry, so it isn't drawn. The fusion
  coils' bloom (`two_add_env_illum`) is bitmap 3 tinted by pixel constant
  3, added; the storm layers and horizon gradients
  (`sky_one_alpha_env_clamped`, Colossus, Containment) take
  `one_alpha_env`'s slots. Read with the catch-all additive slots (bitmap
  1), these drew nothing or only their mask. `add_illum_detail` (Gemini's
  hologram halo: a ring map through scrolling scanlines) and
  `one_add_illum_detail` (the light volumes of Gemini, Containment and
  Waterworks) are the sun shafts' template outside the sky, drawn the same
  way; the facing colour's alpha (vertex constant 6.w: 1 on the sun shafts,
  0.15 on Gemini's white volumes) scales the tint, and `add_illum_detail`,
  whose five constants are only the maps' transforms, has no facing colour.
  Drawn from bitmap 1 alone, the halo was a solid grey ring of scanlines.
  These and the holo template fade by view angle: the vertex colour's
  alpha runs from a glancing alpha to a facing one by N.V (constants 7.w
  and 6.w; the holo template's 11.w and 10.w), so where the facing alpha is
  higher a volume seen edge-on vanishes. That goes in as CE's
  `framebuffer_fade_mode` 2 (|N.V|); without it Desolation's light shafts
  (a holo-template volume with a white mask) were solid white slabs. A
  transparent template's textures, transforms and scrolls are read the way
  halo2.dll reads them: a constant's descriptor names its texture slot
  (bits 10-12) and row (bits 5-9: 14 and 15, the 2D affine rows), the
  template's remapping table names each slot's bitmap, and an overlay's
  function is evaluated as the engine's evaluator does (identity,
  transition, periodic slide, linear with its own slope; the engine adds
  the translation, as CE's masters add their animation).
- **Sky.** The sky's lights (yaw, pitch, colour, power, diameter, whether
  the lightmaps used them), outdoor ambient and atmospheric fog go to the
  placement as halo2ue puts a CE sky's, so the level's sun, sky light and
  fog follow them. Halo 2 stores the ambient as a colour alone; it goes in
  at CE's usual power, 0.2 (at 1, Ascension's lit the player and weapons
  3.8 times too bright). Lockout's light lit nothing (its radiosity flags are
  clear; the sky model lit the lightmaps), so its sun comes from the
  lightmaps' incident directions, as for a CE map without one. Halo 2's
  atmospheric fog covers the sky as well: one at full density (Backwash's
  swamp, opaque at 20 world units) also gives the level `sky_fog`, so
  everything past the opaque distance, the black sky dome included, is the
  fog's colour (gen_ce_level.py `sky_and_weather`; Backwash's sky drew
  black above the fog).
- **Placements.** Halo 2 spawns every multiplayer pickup and vehicle through
  netgame equipment (item and vehicle collections): each becomes halo2ue's
  `netgame_equipment` or `vehicle` entry naming the collection's item.
  Netgame flags take CE's names where CE has the thing (`CtfFlag`,
  `OddballSpawn`, `HillFlag` with its hill index, `TeleportFrom`/`TeleportTo`
  paired by identifier); assault, territories and headhunter keep names the
  tag map leaves out. Halo 2 spawns by influence, so its player starts carry
  no CTF side (Lockout's are all team 0); each start takes the side of the
  nearer CTF flag spawn, so a CTF game has red and blue spawns. A start
  (0x34 bytes) lists four game types at `0x14` (CE's numbers, plus 6
  Headhunter, 7 Juggernaut and 8 Territories) and a spawn type for each at
  `0x1C` (0 both, 1 initial spawn only, 2 respawn only), staged as
  `game_types` and `spawn_types`. A start that lists no game type serves
  every one: Containment, Relic, Sanctuary and Warlock list none on any
  start, and Terminal's 88 untyped starts stand beside 61 All games ones.
  The level generator places them by game type ([ce_map_conversion.md](ce_map_conversion.md),
  "Spawn sets"); spawn types are not used yet. Props are
  scenery and crates (`bloc`), staged with their
  render and collision models. Game-type props (the CTF and territory flag
  bases) are left out: the level's own CTF stands replace them.
- **Planar fog.** A BSP's fog plane (Ascension's cloud deck, Lockout's
  haze below the map, the water of Dune, Needle and Zanzibar) goes to
  `fog.json` as `ce_fog.py` writes a CE map's, so the masters fog what lies
  below the plane by its depth under it and its distance, as CE's planar
  fog does. Halo 2 draws planar fog per surface only (every opaque
  template's `fog_planar` pass; no fog-plane mesh, no full-screen pass), so
  that is all there is to it. The cloud sea MCC shows under Ascension's
  island, wisps drifting through it, is not fog: it is a transparent cloud
  plane in the BSP 12.6 wu under the fog plane (`ascension_clouds`, a
  `two_alpha_clouds` shader), a static disk of cloud puffs times a cloud
  tile scrolled over it, drawn unfogged over the sky's lower half. Drawn as
  one static grey map, it was the flat pale plane the rocks stood in.
  Halo 2's transparent templates other than glass have no fog in their
  compiled shaders, so they go in `fogged: false` and the material spec
  leaves their fog out. Where the view passes below the plane and finds no
  surface, MCC draws the fog's colour (its fog pass lays a depth copy for
  the engine's full-screen fog shaders): the rocks' fogged lower ends vanish
  into it, where ours stood out against the sky's dark lower edge. A level
  plane gets that as the loader's height fog at the plane, in the fog's
  colour, starting 1.5 km out past the cloud plane
  (`gen_ce_level.h2_fog_fill`, `environment.haze`). The plane names its fog through the scenario's
  planar fog palette; Beaver Creek's names an entry the scenario does not
  have and gets none.
- **Machines.** A gear whose device animation turns its one node about one
  fixed axis is placed like scenery, with its turn: the axis and the keys
  of its `device:position` animation as (seconds, degrees) over its
  position transition time, read by `crate::h2::animation` (the keyframe
  codecs 4-7, and codec 3, which stores every frame). That covers
  Ascension's three antennas (the big arms that swing around the central
  pillar every 40 s, about +Z), Zanzibar's big wheel, its blades and three
  flywheels (+Y; two flywheels are placed tilted) and Foundation's two fans.
  `merge_ce_scene.py --machines` writes each such placement as a mesh of
  its own (`scene_machine_<k>.gltf`, built as `SM_<code>_Machine<k>`; its
  transparent parts, such as the flywheels' lightning, as
  `scene_machine_<k>t.gltf`, since a rewritten mesh enters the translucency
  pass by its slot 0) with its pivot, keys and, when the axis is not the
  world's +Z, the axis in
  Unreal's axes beside it (`.motion.json`); the level's decor entry carries
  them as `motion`, and MJOLNIRLevelLoader turns the actor about the pivot.
  Every other machine's motion (doors, lifts, Triplicate's train, Backwash's
  monitor) is left out as before, listed in staging's notes: still, a
  closed gate or a parked train would block a way Halo 2 opens. A lift's
  push does not need its motion; see the next item.
- **Lifts, jump pads and vents.** Halo 2 pushes through physics model
  phantoms (`crate::h2::phantom`): shapes nothing collides with, each with a
  phantom type (accelerations and top speeds along a render model marker's
  forward, towards its axis and towards its point, and whether it holds off
  gravity). The stage writes every placed object's phantoms that push
  players to placement.json `lifts` (object space, whether or not the prop
  is drawn), `gen_ce_level.py` puts them in the level file in Unreal space
  (`lifts`: planes or a pill, a bounding sphere, the marker, the pushes in
  cm). MJOLNIRLevelLoader's `lifts.lua` hands them, in the simulation's
  units, to MJOLNIRLobby's DLL once a map, and the DLL sets the velocity of
  a player inside one through `(object_set_velocity (player_get N) ...)` on
  every simulation tick (`native/lobby/lifts_runtime.h`,
  [re/lift_push.md](re/lift_push.md)).
  Each game pushes its own players only: a joiner's motion is its own game's,
  and a push the host sends a joiner's unit does nothing (two PCs,
  2026-10-25). Maps with player lifts: Lockout, Midship, Cyclotron (Ivory
  Tower), Colossus, Coagulation, Headlong, High Plains (Tombstone, hvac),
  Backwash, Foundation, Warlock, Derelict (Desolation), Dune (Relic,
  watchtowers), Ascension and Gemini (jump pads).
  `lifts` is a key only the loader reads, so a published pack gets them
  without a rebake: `tools/level/add_lifts.py` stages the map, adds the block
  to the pack's level file and packs the next version, and checks nothing
  else changed (the bots stay as baked). Those 14 maps shipped this way at
  1.3.0 on 2026-11-04, with the gaps in testing listed in
  `docs/h2_lifts_release.md`. The other 11 maps have no phantom that pushes
  players and stay at 1.2.0.
- **Moving collision.** The simulation does all collision, never reads
  Unreal geometry, and its structure BSP cannot move: an arm's collision
  baked at rest stood where the arm only sometimes is. Rewriting a live
  object's transform moves the object but not its Havok body; a device
  machine moves its collision with its animation. So each turning part
  becomes a machine of the simulation's own (`tools/level/h2_machines.py`,
  run by `convert_ce_map.sh`), five tags cloned from B40's elevator, whose
  nodes and Havok layouts agree, each a container
  `pakchunk986-MJOLNIRMACH-<CODE>-<k><g>` under `objects\mjolnir\<code>\`:
  - an animation graph whose one resource member turns the root by the
    part's keys, every frame with codec 3 (the shipped turning props' own;
    its header is Halo 2's), beside the static pose, node flags, an
    uncompressed copy and object-space frames the resource carries;
  - a collision model holding the part's own Halo 2 collision BSP, which
    staging writes as `collision/<part>.bsp.json` and `mjolnir level
    machine-collision` packs with its Havok MOPP. Bipeds meet a machine's
    collision model, not its physics model's shapes: a player dropped on an
    arm built of physics boxes alone fell through it;
  - a physics model of boxes over the part's triangles, for what moves
    through Havok (the elevator's lift phantom goes with it);
  - a model, and a gear machine whose "position transition time" is the
    rate 1 / period (the engine reads it as a rate: 40 ran the antennas 40
    times a second, aliased into a seven-second wobble). The engine shows a
    gear at frame position x N, held at the last frame (Halo 2 used N - 1),
    so frame f is the angle at f / N of the turn, one every 0.1 s: with
    Halo 2's five frames Zanzibar's wheel turned a full circle in 24 s of
    its 30 and stood still for 6.

  The generator places each machine where its part is, with its full
  rotation (`blam.objects`, group `machines`), and gives the part's mesh
  `motion.follow`; the merge leaves the part's collision out of the BSP
  (`merge_ce_collision.py --sim-machines`). The machine draws through the
  elevator's Blueprint, whose turning part follows the root; the loader
  hides that part's mesh, attaches the Halo 2 mesh to it, and fits the
  turn's phase (the simulation starts its gears about 25 s off the world
  clock) for the sounds. Checked on Ascension: a player dropped on an arm
  stands on it and is carried round as it turns.
- **Teleporters.** Halo 2's teleporter scenery (Ascension's
  `2way_teleporter` bases) is placed like any other prop: the generator's
  working pads on the teleporter flags draw nothing. Its beam is a
  `plasma_alpha` shader, its glow a `one_add_illum` (the base map times
  pixel constant 0, added). The bases have no collision model.
- **Sound.** Halo 2's samples are not in the maps but in headerless
  `sounds_*.dat` files beside them (Opus and Xbox ADPCM;
  `docs/h2_cache_format.md`, "Sound"). `crate::h2::sound` stages them as
  `ce_sounds.py` stages a CE map's, `staging/sounds_out` (`sounds.json` and
  its files), which `convert_ce_map.sh` imports with `build_ce_sounds.py`
  and the generator plays: the BSP clusters' background loops (2D), the
  sound scenery and the loops placed objects carry (3D, at the object's
  origin), and the one-shots a turning machine's animation raises
  (Ascension's 12 antenna cues, at their frames). Opus packets go into an
  Ogg Opus file as they are, which the editor imports (Ascension's
  `antenna1` came in at its tag's 2.240 s); ADPCM is decoded to WAV. A
  sound's playback gain (dB) and random pitch bounds (cents) become the
  entry's `gain` and `pitch` (Ascension's humming light plays 5 semitones
  down); a loop's distance bounds come from its `lsnd` (most loop samples
  carry none) unless the sound scenery overrides them. An attachment scaled
  by an object function (the jump pads' launch loop, `phantom_power`) is
  left out: it sounds only while the object drives it.
- **Lightmaps.** Halo 2 keeps its pages at half their light and doubles
  them in the shader; the CE masters take a page as it is, so the pages are
  staged doubled (clamped). Without that Lockout's interiors were nearly
  black. Its 65 small pages would each bake at 2,048 under lightmap_bake's
  default 16x, so Halo 2 maps bake at most 4x (`BAKE_ARGS` default).
- **Render models** (the sky, props) store positions and texture
  coordinates in -1..1 across the model's compression bounds; read raw,
  Lockout's sky was a 3 m knot at the origin and drew nothing.
- **Weapons the game lacks** take the nearest role (`defs/level/h2-tag-map.json`):
  the battle rifle the assault rifle, the brute shot the fuel rod gun, the
  carbine, brute plasma rifle and sentinel beam the plasma rifle.

## Specular

A Halo 2 template's postprocess definition (stem +0x58) lists its passes,
each pass's implementations and what each implementation feeds its shaders
(`specular_constants` in render.rs reads it; the example
`h2_template_blocks` prints it). Most opaque templates draw
`default_light_combined_tangentspace_specular_sphere`. Its vertex shader
passes vertex registers 10 and 11, fed from two of the shader's vertex
constants, to the pixel shader, which adds sat(R.L)^8 x the light x
lerp(register 11, register 10, sat(N.L)) through the frame's alpha (R the
view reflected about the bumped normal, L the light's direction). The
template's lightmap pass wrote that alpha first:

- min(1, 2 x base alpha x the light) for `lightmap_tex_detail` and nearly
  every other lightmap pass (`tex`, the detail blends, two and three detail,
  illum, shiny, tiling, change colour, honor guard), so the base map's alpha
  is a specular mask;
- 0 for the env passes, `detail_overlay` and `detail_no_specular`: those
  surfaces never shine, whatever their passes;
- the cut-out or other terms for the alpha-tested passes. Only
  `alpha_test_no_bump`'s (the cut-out, which is the base alpha) matches
  what staging writes; the others are left without.

That is CE's lightmap specular (`SpecLightmap`: the lobe from the
lightmap's incident direction, masked by the base map's alpha), its colour
going from parallel to perpendicular by N.V rather than N.L: perpendicular
takes register 10's constant, parallel register 11's. A template that cuts
out on another map's alpha has the cut staged in the base's alpha, so it
would shine all over; it gets none. Turf's door frames and posts
(`metal_grey_dark` on `matte_grey`, brushed streaks in the alpha: vertex
constants 7 and 8, 1.0 and 0.75 grey) drew flat grey without it. Placed objects (lit from the object lighting
page) are left without: they have no incident direction per texel, so a
flat face took one and saturated white (Turf's dumpster). 25
templates take it, 61% of the multiplayer maps' triangles
(docs/h2_shader_census.md).

## Decorators

Halo 2 scatters grass, rocks, debris, litter and decals from its scenario's
decorator sets (`DECR`) over each structure BSP (`crates/blam-cache/src/h2/decorator.rs`;
the example `h2_decorators` prints a map's). The BSP's decorators block
(+0x234) is an octree of 8-unit cells around a centre (cells per side x 8
units across); each leaf names groups, and a group a run of placements in a
raw cache block, six words each. MCC's `halo2.dll` decodes them (0x979eeb;
no tag carries the finished geometry, so the decode was read from there):

- position: the leaf cell's corner + (bits 0-9 x 8/1023, bits 10-19 x
  8/1023, bits 20-31 x 8/4095) world units;
- internal word: bits 0-2 the class, 3-8 the permutation, 9-12 the yaw
  (v/15 of a turn), 13-15 the tint blend, 16-19 the scale (v/15 across the
  permutation's range), 20-31 an up vector the "align to normal"
  permutations turn to: the yaw then turns from Halo 2's own perpendicular
  to it (0x6fcf30: the smallest component zeroed, the other two swapped,
  one negated), and any other perpendicular turns every aligned piece by a
  fixed angle (Turf's cans lay 180 degrees round);
- tint and lightmap colours, two light directions.

On Zanzibar, Turf and Beaver Creek the decoded placements lie on the BSP's
surface (median 0.1 units). The 20 maps with decorators hold 38,600:
31,000 models, 6,300 floating decals and 1,300 camera-facing sprites
(Zanzibar's, all). A group's own type byte disagrees with its class's on
Turf, so the class's (`DECR` class +0x04) decides.

DXT1 bitmaps decode with their one-bit alpha (a three-colour block's
index 3 is transparent black, as D3D samples it). Read opaque, the debris
atlas drew each piece in a black box where Halo 2 cuts it out; elsewhere
one to five textures a map gain transparent texels (Coagulation's light
bands, Ascension's light strips, Zanzibar's hazard strips).

Model decorators are staged as scenery: each set's model
(`models/<set>__decorator<k>.gltf`, its run of the set's indices, double
sided, `decorator_tex` cut out on its base map's alpha), one placement entry
each with its rotation as `basis` (forward, left, up) and `scale`, which
merge_ce_scene.py places like any object (lit from the object page).

Decal decorators need no decode: the map stores them as geometry. Each
cache block carries decal vertices (locator 0x08: 0x20 each, position,
texture coordinate, a second coordinate, colour) and indices (0x10), 4
vertices and 6 indices a placement over its group's run (+0x0C vertex
start and count, +0x10 index start and count); `halo2.dll` draws them as
they are (0x9795c0). Their coordinates already point into the decal
bitmap's atlas. `decorator::decals` reads them; staging writes one mesh a
group and shader (`models/<set>__decals<group>_<shader>.gltf`, at the
quads' centre): `decorator_decal_paint` alpha blended,
`decorator_decal_paint_multiply` (stains, blast scorches) multiplying the
frame by the map where its alpha covers, baked into an alpha blend as the
overlay's is. Turf's 322 (posters, rubble, stains) draw in game. A group's
own type byte calls Turf's posters and rubble models; their class and
their decal vertices say decals.

Not done: the camera-facing sprites (Zanzibar's), the placements' own tint
and lightmap colours, and a lighter path for the maps with thousands (Coagulation's
16,800: one object page texel and one merged copy each).

## Breakable glass

Halo 2's glass (Turf's stairwell doors) is solid until shot, meleed or hit
hard, then breaks and lets players through, as in Halo 2.

- **Collision.** `mjolnir level collision` (Halo 2 sources only) makes the
  glass breakable surfaces of the sim's own kind
  (`blam_sbsp::convert::rebuild_breakable`): each polygon is a pane (its
  front and back), each connected sheet a set, closed at its edges so the
  sim's flood fill never reads a missing surface. `brittle_glass` takes the
  `brittle_glass_reinforced` material: plain `globals\glass` breaks at any
  touch, so walking into it broke it.
- **Drawing.** The sheets go beside the BSP (`<map>.sbsp.breakables.json`,
  world units); `tools/level/split_breakable_glass.py` moves each sheet's
  transparent triangles into mesh slots of their own, and the level entry
  lists them (`breakables`: sheet, box in cm, slots). The level loader
  hooks the game's break effect (`BP_BaseBreakableSurfaceEffect_C:Spawn`,
  which names the point it broke at): the sheet there loses its slots
  (`M_CE_Hidden`) and throws glass chips (`NS_Impact_Glass_Lrg` without its crack decal, over a 3 x 3
  grid). A sheet stays broken until the map loads again.
- Not done: the break's sound (the game's `HaloAudioSound` has no script
  call to play it), and glass in the structure BSP itself (the world shell's
  packing drops the breakable bit; Turf's is all instanced geometry).

## How the open items were closed

- A prop's collision on a child node (Zanzibar's crane and hinged lights,
  Derelict's trees) is placed by the render model's rest pose; a scaled
  placement (Zanzibar's bushes at 2x to 4x) gets a copy of the model and
  collision with the scale baked in (`<name>_x2__scen.gltf`).
- Every instance's incident light direction, and the light of vertex-lit
  instanced geometry (Lockout's 26 light fixtures), come from Halo 2's
  lightmap vertex buckets. A vertex-lit instance draws its vertices' mean
  light from a texel of its own on a page after the last (the CE masters
  sample light through lightmap coordinates, so per-vertex colour has no
  slot); the incident direction still varies per vertex.
- Cube maps and the scrolling shader animations (cloud banks, gas, grav
  lifts) are converted; see Shaders above.

## Not yet done

- Only BSP 0 is converted (every multiplayer map has one).
- Placed object models take each region's first permutation at its most
  detailed level.
- Specular's colour blends by the view (N.V) where Halo 2's blends by the
  light (N.L), and alpha-tested templates other than `tex_alpha_test` have
  none (see Specular).
- The sun shafts' fade towards edge-on (the vertex colour going from the
  facing colour to black as (N.V)^2) has no CE chicago equivalent; they draw
  at their facing colour.
- An env reflection's colour is one hue (the mean of the facing and
  glancing colours) baked into a copy of the cube, and its facing-to-glancing
  blend uses CE's squared view term rather than Halo 2's linear one.
- `plasma_alpha`'s fade comes from its vertex shader
  (`transparent_generic_reflection`), not read back: M_H2_PlasmaAlpha takes
  it as the facing term |N.V|, weighted by pixel constant 2's alpha as the
  pixel shader weights it. The level needs chunk 981
  (`pakchunk981-MJOLNIRH2-Windows`) installed: without it the level
  loader finds no parent for the plasma's slots ("parent material not
  found").
- The loops' detail sounds (Ascension's thunder and wind gusts, at random
  periods and directions) are staged in `sounds.json` but not played; a
  loop attached to a marker plays at the object's origin.
- On maps other than Lockout, CTF sides and vehicle teams come from the
  nearer CTF flag and vehicle game types from Halo 2's; Lockout and
  Ascension have been started, Ascension only by a test camera.
- Install the way a local test map is installed (`level bake --install-test`
  and the map's 985/986 containers): `--install` also copies this project's
  material cook over chunk 988, which on a box with the hub's runtime
  replaces the runtime's masters.
- All 24 multiplayer maps stage; Lockout, Ascension and Zanzibar have been
  converted end to end and started.
