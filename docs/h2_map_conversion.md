# Converting a Halo 2 Map

**Status:** 2026-10-21. Lockout converts through the same command as the
Halo 1 maps and starts from MULTIPLAYER as a Slayer game (`mjolnir_auto host
LOK slayer private`): its own world, the Spartan standing in the BSP
(`object_get_bsp` 0), the pickups resting where Halo 2 put them, every
material applied. The Halo 1 pipeline is unchanged; its outputs for Chill Out
and TST are byte-identical before and after the Halo 2 work. Not yet played
by a person.

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
  slots and tiling are read in the template's order (`h2::render::template`).
  Opaque shaders become environment-master summaries (base, detail, second
  detail blended by the base's alpha, bump, self-illumination; alpha tested on
  the base map for the alpha-test templates); transparent ones single-stage
  chicago summaries, alpha blended (glass) or additive (plasma, the grav
  lifts), drawn in the translucent mesh.
- **Placements.** Halo 2 spawns every multiplayer pickup and vehicle through
  netgame equipment (item and vehicle collections): each becomes halo2ue's
  `netgame_equipment` or `vehicle` entry naming the collection's item.
  Netgame flags take CE's names where CE has the thing (`CtfFlag`,
  `OddballSpawn`, `HillFlag` with its hill index, `TeleportFrom`/`TeleportTo`
  paired by identifier); assault, territories and headhunter keep names the
  tag map leaves out. Halo 2 spawns by influence, so its player starts carry
  no CTF side (Lockout's are all team 0); each start takes the side of the
  nearer CTF flag spawn, so a CTF game has red and blue spawns. Props are
  scenery and crates (`bloc`), staged with their
  render and collision models. Game-type props (the CTF and territory flag
  bases) are left out: the level's own CTF stands replace them.
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

## Not yet done

- Only BSP 0 is converted (every multiplayer map has one).
- Placed object models are staged without node transforms, and only each
  region's first permutation. Lockout's props are single-node; on other maps
  the collision a prop keeps on a child node (hinged lights, cranes, trees)
  is left out, and staging says which.
- Vertex-lit instanced geometry (3 of Lockout's 13 definitions) is drawn on
  a flat page of the level's average light: Halo 2 lights it from per-vertex
  buckets not read yet.
- Lockout's snow and sunlit exteriors come out close to white with the
  doubled pages and the level's default sun; the exposure is not tuned.
- Cube maps (environment reflections) and animated shader parameters are not
  converted; sounds are not extracted.
- On another map, CTF sides and vehicle teams come from the nearer CTF flag
  and vehicle game types from Halo 2's; only Lockout has been checked in game.
- Install the way a local test map is installed (`level bake --install-test`
  and the map's 985/986 containers): `--install` also copies this project's
  material cook over chunk 988, which on a box with the hub's runtime
  replaces the runtime's masters.
- All 24 multiplayer maps stage (2026-10-21); only Lockout has been converted
  end to end and started.
