# Pelican Warfare: shipped-quality detail from the base game's own assets

The goal: PWR should look as if 343 shipped it. The base game already contains most of what
a temperate alpine valley needs, and PWR uses only 106 of the 4,955 relevant assets.
`levels/warfare/pwr/data/base-game-assets.md` (and `.json`) catalogues them all, from a
read of every base-game container on 2026-11-23: package path, class, size, vertex count,
which shipped levels use it, and whether PWR already does.

## What the survey found

- **A30 ("Halo") is a whole temperate river-valley biome PWR barely touches.** It ships
  landscape layers for meadow, stony soil, scree and riverbed (`MM_A30_Landscape` blends
  Megascans sets with hex texture bombing, `MF_Hex_TextureBombing`), and art-directed
  PCG assemblies for river boulders, log jams, scree, tree skirts, rushes and sedges.
- **C10 ships a riparian bank kit**: eroded bank modules 45-80 m long, each with a wet
  material instance. These are exactly the river and lake cut banks PWR models by hand.
- **PWR's open meadow is shaded from CE detail textures**, not the Megascans surfaces
  next to them, and three Megascans sets PWR does sample are read for diffuse and normal
  only: their roughness, height and AO maps (`_ORHG`) ship unused.
- **The rocks PWR places all use their `_NoSnow` instances.** The same meshes ship with
  snow-capped instances (`MI_Rock_Glacial_*`, `MI_Rock_AllSnow`), and B40 shipped the
  snow-line surfaces (snow-covered grass, windswept snowy stones, melting snow) that PWR
  jumps over between meadow and peak.
- **No road furniture shipped**: no signs, lamp posts, fences, cones, curbs, puddles or
  tire-mark decals. Roads have to be finished with their verges (gravel shoulders, scree,
  boulders) and the landscape deformation system for tracks.
- **Wrecks ship as meshes**: a destroyed Pelican, a destroyed Scorpion, A30's crashed
  lifepod with 21 debris pieces and its crash mound. A crash site is on-theme for a mode
  called Pelican Warfare.
- **About 2,700 ambience sounds** (A30 river, rapids and waterfall loops among them) sit in
  Wwise; whether level data can trigger them is unverified. Fluid Flux's plain
  `SW_RiverAmbient` works with PWR's emitters today.

## Constraints every step keeps

- Reference base-game assets in place; never copy them into PWR's packs.
- Foliage is already about 18% of the GPU frame: new plants replace plant kinds, they do not
  add on top. Measure frame time before and after every step.
- Cooked decal masters crashed the game (a PSO fatal), so caustic and wet decals are out
  until that is solved; that rules out the Fluid Flux river template's decal pieces.
- Anything a player can touch needs Blam collision (the outcrop hull path, or a crate tag
  that collides and syncs by itself). Rocks and banks must clear
  `check_structure_clearance.py` and stay off roads (`meadow_life.visual_margin`).
- Everything is data the map ships: decor, level `effects`, `lights` and sounds, cooked
  landscape layers. No per-frame Lua.
- Before and after shots from the user's FlyCam set (`MJOLNIR_FlyCam_shots_PWR.json`)
  for every step, plus a two-PC check.

## The work, in order of what a player notices first

1. **Ground that reads as real.** Give `M_PWRPilot` A30's meadow, stony-soil, scree and
   beach-sand-with-pebbles layers with their ORHG maps, height blending and hex texture
   bombing, plus B40's snow-line surfaces between meadow and snow. This changes every
   square metre of the map: no more flat green, no visible tiling, wet and dry variation.
   Needs new layer slots and a landscape cook (`landscape-shaders-in-world-chunk`: the
   LAND chunk changes and the world rebakes).
2. **Rivers and lakes with real edges.** C10's riparian banks (wet instances at the water
   line) on the cut banks; river cobbles on gravel bars; A30's boulder and log-jam
   assemblies at bends and fords (their member meshes re-placed as decor with hulls).
   Lake margins get a shore band: beach sand with pebbles and shoreline beach rocks in the
   landscape, Nordic beach rocks and driftwood (the fallen spruce meshes) on top, so the
   lakes read as beaches rather than grass meeting water.
3. **Mountains that belong to the valley.** Snow-capped instances on every rock above the
   snow line; alpine scree fans under cliffs (`SM_Scree_Alpine_A-C`, scree clumps, A30's
   scree assembly) to bed boulders into the ground; C20's snowy mountain vista in front of
   the distant ring for a nearer silhouette; snow gusts on the ridge crests.
4. **Forest floors with depth.** Deadfall (fallen spruce and old fallen trees), mossy roots
   and boulders, lumpy moss, turkey-tail mushrooms and lichen, swapped in for some of the
   current understory kinds; windswept dead snags at the treeline; falling pine needles
   and light cones (`SM_LightCone_Plane_1x` with its animated fading instance) in the
   pine stands.
5. **Life and air.** The waterfall mist and rainbow set on the cascade; ambient ground fog
   over the lakes and river bends; dragonflies over the reeds; river and rapids audio
   along the water.
6. **Bases and roads.** Forerunner tall and panel light fixtures with real lights on base
   walls and pads; the shipped Forerunner metal instances with grime tiers on base and
   bridge surfaces; Forerunner exterior ruins (crash-site abutments, beach terminal
   pillars, tarmac pillars) on ridges; gravel shoulders and boulders along the roads;
   vehicle tracks through the landscape deformation system.
7. **A landmark.** A crashed-Pelican site: the destroyed Pelican hull, lifepod debris and
   crash mound, a wind-bent smoke column, and the E30 wreckage crate tags for collision
   that syncs with no code.

## Progress

### Step 1, first half: A30 ground as level data (2026-11-23)

The landscape textures are not baked into `M_PWRPilot`: the loader binds them at load from
`landscape.pbr.surfaces` (`Land.pbr` in the level loader). So the first half of step 1 is
level data, with no cook. PWR builds carry the last release's `pwr.level.json` forward
(`docs/pwr_map_0.1.2.md`, step 6), so the next pack runs
`levels/warfare/pwr/visual_dressing/ground_surfaces.py` on it; PWR's look in
`tools/level/build_landscape.py` holds the same values for a level generated from scratch:

- **Meadow** (`GrassD/N/O`): A30's wild grass and weeds (`T_Wild_Grass_NSVT_D_A30`, its
  normal and ORHG) in place of a desaturated grass the tint painted green. Up close the flat
  green felt becomes clover, leaf litter and soil; `grass_tint` goes from 0.40/0.62/0.36 to
  1.0/1.05/0.9.
- **Track stone** (`MidD/N/O`): A30's stones on soil in the wheel ruts and shoulders. PWR
  runs the shader's alpine branch (`Alpine.w > 1.5`), where `SandD` is the track's earth
  and `MidD` its stone; `SandB*` is not read there. Putting stony soil in `SandD` (the
  first try) turned the forest tracks grey, so the earth stays.
- The default grass map is OHRG and A30's is ORHG. The shader reads `.r` (occlusion) the
  same and floors grass roughness at 0.92, so only partial-grass edges read height as
  roughness. Nothing visible came of it.

Tested on PC 1 by swapping the loose `level.json` and rehosting, FlyCam shots 1-9 before and
after in one session (`out/pwr-detail/before2`, `afterB`). Frame cost at 4K, GPU ms:

| shot | before | after |
| --- | --- | --- |
| 1 (lake meadow) | 13.00 | 13.03 |
| 3 (lake shore) | 14.43 | 14.40 |
| 8 (road) | 11.62 | 11.49 |

Same sampler count and no measurable GPU cost; a little more texture memory (A30's grass
is 2048 px where the old one was 1024). From the air (FlyCam at 480 m over the south
meadow) the valley reads olive and khaki instead of lawn green, with no tiling carpet
and no seam against the distant ring.

Still to do for step 1, and these need the shader and a landscape cook: the beach band
at lake shores (PWR has no sea, so the shader draws no shore band; it needs a shore mask),
and B40's snow-line surfaces between meadow and snow (`Rip*` holds the snow itself, and
there is no slot for a band between them).

Each step is its own dressing round through the existing pipeline (the vegetation round
for landscape and baked plants, the outcrop and decor passes for meshes with hulls,
level data for effects, lights and sound), sealed as a numbered build and compared with
the last release (`release_loss.py`) like 0.1.2 (`docs/pwr_map_0.1.2.md`).
