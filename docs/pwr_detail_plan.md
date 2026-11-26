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

### Step 2, first part: a shore band along every lake and river (2026-11-23)

**What did not work.** Scattering the base game's rocky-beach patches and beach stones along
the banks as decor: the patches are scanned half-discs made to blend into a landscape, and
drew as hard-edged discs (`S_Nordic_Beach_Rocky_Ground_ukohbbi` drew black); 20 cm stones
read as specks on banks tens of metres long. The collision scene is also full (1,199,995 of
the pipeline's 1,200,000 surfaces), so anything a player could walk into has to reuse hull
slots. The single stones draw correctly and stay candidates for that later round.

**What was built (release 48, on PC 1 as dev chunks; not packed or released).** The banks' surface itself:

- `tools/level/shore_mask.py` bakes a mask from the map's own baked Fluid Flux water (any map
  with `flux_state/`): signed metres from the water's edge, height above that water, and
  coverage, 2048 px over `landscape.pbr.rect`.
- `unreal/MJOLNIRMaterials/Scripts/apply_pwr_shore_band.py` binds it to `M_PWRPilot`'s valley
  node (`PWRShoreData`, plus `LandRect` for its placement) and replaces the northern lake's
  compiled-in shoreline (48 hand-entered spans) with the same beach drawn wherever the mask
  has water: damp earth, gravel toward the water, darker and glossier at the wet line. A mask
  with no coverage draws nothing.
- GPU cost at 4K, shots 1, 3, 8: 12.88 / 14.27 / 11.65 ms against 13.03 / 14.40 / 11.49.

**How it is built** (release 48 in the pelican-warfare Codex worktree):

1. `python tools/level/shore_mask.py <map folder>/pwr.level.json T_PWRShoreData.png`.
2. `.dream-loop/vegetation/round_shore.sh` (a copy of `round.sh` there, which is gitignored)
   adds one step: with `SHORE=<mask png>` it runs `apply_pwr_shore_band.py` (apply, then
   verify in a fresh editor) right after the round restores `M_PWRPilot`, **before** the grass
   step, and declares `M_PWRPilot` and `T_PWRShoreData` as allowed landscape changes. The
   order matters: the landscape grass maps bake from the material, and an edit after them
   left most of the meadow tufts missing (round 47).
3. Same command as 0.1.2's round with `SHORE=` added and version 48.
4. **The world bake (997) has to be redone from the new round's `LPE.umap`.** The landscape
   draws through a `LandscapeMaterialInstanceConstant` stored in the world, with the shaders
   of the material it was cooked against: a new 965 under the old 997 draws the old ground.
   0.1.2's bake command with `--world` the new round's `packaging/LPE.umap`.

A plain `round.sh` restores the old `M_PWRPilot` and silently drops the band; only
`round_shore.sh` with `SHORE=` keeps it. Checked: the band touches road only under the
bridge decks (the road atlas, offline), no outline from the air, release 48 differs from 46
only in 965 and 997.

**Gravel.** The band first drew its stones from the `SandBD/N` slot, which road shoulders,
tracks and the riverbed share. Of seven base-game surfaces tried there,
`Shoreline_Beach_Rocks_ullmagidy` was the only one where cobbles read on a bank, but from
the air it outlined every road and the dirt track in pale stone. So that slot keeps the
ground gravel, and the band samples the river cobble scan the outlet already uses
(`RiverCobble`/`RiverCobbleN`), which touches no road. Release 49 (2026-11-23): real cobbles
at the water on every river and lake, roads unchanged from the air.

**Driftwood and boulders, in recycled collision slots.**
`levels/warfare/pwr/visual_dressing/riparian_swaps.py` swaps 48 of the 133 shore rocks
(Glacial Med/Lrg rows within 9 m of the water, 35 m apart, clear of roads and decks) for
24 driftwood logs (A30's large fallen tree, the 5.5 m fallen log at 1.4-1.8x; the smaller
log scans read as twigs) and 24 boulders (mossy boulder, Nordic beach rocks, tundra
boulder). Logs lie along the shore, pitched to the ground under both ends. Each new piece's
convex hull is capped to the rock's own triangle count (`budget = (slots + 4) / 2 - 8`) and
written into the rock's triangles; spare triangles sink 30 m. 2,154 triangles written,
1,490 sunk, the scene's size unchanged. Log triangles get the scene's `tough_organic_wood`
material (they sound and spark as wood), boulders `hard_terrain_stone`; a plane index's flip
flag is honoured (none of the swapped surfaces has it). The plan is `levels/warfare/pwr/data/riparian-swaps.json`.

    riparian_swaps.py plan  <level> <shore mask> <terrain> visual-v6/scenery/hulls <new hulls> plan.json
    riparian_swaps.py level <level> plan.json <out level>
    riparian_swaps.py collide <0.1.2 physics> <level> plan.json visual-v6/scenery/hulls <new hulls> <out>
    mjolnir level collision <out>/collision_scene.json ... --out pwr.sbsp   (as cook_riparian_toe.py)
    mjolnir level bake ... --bsp 8=<that pwr.sbsp> --world <round 49 LPE.umap>

Checked on PC 1 by dropping the player on log root ends 4-4.6 m from where the old rocks
stood: it came to rest 0.58 and 0.64 m above the ground, on the logs, against bare ground
3 m away (28.64 wu, heightfield 28.65). No new footprint touches the road atlas or comes
within 4 m of any of the level's 262 gameplay points (15 m for zone candidates). Only the
tops were tested in game; sides and bullets use the same triangles. GPU at 4K, shots 1, 3, 8:
12.94 / 14.42 / 11.49 ms.

**River stones and the band without tiling (release 51, 2026-11-23).** From the air the
band's cobble repeated every 2.6 m along a bank, and up close it was a photo on flat ground.

- The band now samples the cobble scan the way the surveyed reach does
  (`pwr_scanned_riverbank.ush`): a skewed triangle lattice of about 3.7 m picks three
  rotated, offset, rescaled copies and blends them by sharpened barycentric weight.
- `levels/warfare/pwr/visual_dressing/river_stones.py` scatters real stone meshes over the
  same band, from the shore mask and the heightfield: about 64,700 cobbles (River Stone 01
  C/E/G at 1-2.1x, 25-75 cm, densest just under the water and halving every 1.4 m up the
  bank) and 7,200 larger stones with shadows (River Stone 01 I and Nordic Beach Rock
  vbumba2fa at 1.4-2.8x). They sit a third sunk and tilt half way to the ground. None on
  slopes steeper than 0.7, within 2.5 m of a road, or within 2 m of a bridge corridor. The
  Megascans scan `Nordic_Beach_Rock_vgjidiqmw` draws black in game and is left out. They
  bake into LPE as static instances (`apply_pwr_river_stones.py`, actor `PWR_RiverStones`,
  through `bake_foliage` like the meadow life) and have no collision.
- Cull: cobbles 90-110 m, stones 100-120 m. At 40-55 m (release 50) the cobbles were gone
  from FlyCam shot 4, where the bank is 60-100 m off.
- Cost: none measurable. With the stones hidden or shown, frame 15.39 / 16.67 / 14.00 ms and
  GPU 12.92 / 14.37 / 11.55 ms at shots 1, 3, 8. This session's game thread ran about 1.5 ms
  higher than the afternoon's at the same shots, stones hidden or not; GPU matched.

Build: `round_shore.sh` with `STONES=<river_stones.py output>` bakes them right after the
meadow life (round 51), then the world bake (997) from that round's `LPE.umap`, as above.

    river_stones.py <level> <shore mask> <terrain dir> <out>

**Reflections behind the saplings.** At FlyCam shot 1 the headwater lake drew a pale column
behind every sapling in front of it. The screen-trace thickness (0.03, 2026-11-21) never
fixed it: 0.03, 0.1 and 0.5 look the same. With hardware ray tracing, Lumen gives a surface
its lighting cards only within `r.RayTracing.Culling.Radius`, and the game ships it at -1, so
no surface had cards (Lumen's overview shows the terrain yellow, "no mesh cards"). A
reflection ray that left the screen behind a sapling found the terrain unlit and fell through
to the sky. LevelLoader 0.21.2 sets the radius from `environment.reflections.trace_radius`;
PWR's `vista.json` sets 30000 (300 m). The columns are gone for +0.05-0.09 ms. Other maps
with Lumen reflections may have the same dead cards ("far = black" on Containment, for one),
not yet tried.

Next for step 2: the bank shapes themselves (long smooth slopes no texture fixes).

Each step is its own dressing round through the existing pipeline (the vegetation round
for landscape and baked plants, the outcrop and decor passes for meshes with hulls,
level data for effects, lights and sound), sealed as a numbered build and compared with
the last release (`release_loss.py`) like 0.1.2 (`docs/pwr_map_0.1.2.md`).
