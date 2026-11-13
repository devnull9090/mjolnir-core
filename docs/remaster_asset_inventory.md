# Remaster dressing: asset inventory and placement proposal

2026-11-12. What the remasters' scatter (`tools/level/scatter_foliage.py`) and
scenery swap (`tools/level/scenery_swap.py`) could place, from two sources:
the game's own shipped meshes and the free Fab packs added to
`unreal/MJOLNIRMaterials`. The desert biome is built on Coagulation ("Built" below); the rest is a
proposal.

## How the inventories were made

| Inventory | File (outside the repo) | Made by |
| --- | --- | --- |
| Game, `/Game/Env/Bio` (1431 meshes) | `C:/haloce/ce_conversions/inventory/game_env_bio.json` | `mjolnir mesh list --filter Env/Bio/` |
| Game, `/Game/Megascans` (443 meshes) | `.../game_megascans.json` | `mjolnir mesh list --filter Megascans/` |
| Packs, registry only (all three) | `.../packs_registry.json` | `Scripts/inventory_assets.py`, `MJ_INVENTORY_LOAD=0` |
| Packs, loaded (Namaqualand, Landscape Pro) | `.../packs_loaded.json` | `Scripts/inventory_assets.py` |

In Git Bash set `MSYS2_ARG_CONV_EXCL="*"` for `--filter`: a filter starting
with `/` is rewritten as a Windows path and matches nothing. The whole-game
`mesh list` runs past ten minutes without Oodle; a filtered one takes about
two.

`inventory_assets.py` reads and never saves. Loaded, it records each mesh's
bounds about its pivot (the shape of `tools/level/data/b30_scenery_bounds.json`),
Nanite and fallback triangles, material masters, and every foliage type's
and landscape grass type's settings: the authors' own placement rules.

## What the scatter uses today

One rule set for every map that is not snow, taken from B30's beach: wild
grass, groundcover clump, tall grass and sedges, dandelions and clover,
sea wheatgrass tufts, Nordic rocky-ground slabs, Uluwatu stones, coral
shells, beach pebbles, dry branches. Blood Gulch and Coagulation differ only
by tints and by desert boulders in the scenery swap. So a canyon is dressed
as a beach with the colours changed, and a forest river the same.

That is about 40 meshes out of 1874 shipped nature meshes.

## The game's own assets we do not use

No download, no licence question, no cook: a stand-in at the mesh's path is
enough (`foliage_bake.py`). Sizes are height by width in cm at scale 1.

**Desert and canyon**

| Asset | Size | Use |
| --- | --- | --- |
| `Megascans/3D_Plants/Thatching_Grass` (7) | 7–62 × 16–47 | Dry bunch grass on dirt, where a canyon has no grass at all |
| `Megascans/3D_Plants/Yellow_Rabbitbrush` (6) | 38–192 × 53–238 | The small two (38, 61 cm) in play; the large ones at cliff feet |
| `Env/Bio/Plants/Sagebrush` (5) | 109–163 × 107–249 | Cliff feet and ledges only: above knee height, no collision |
| `Megascans/3D_Plants/Rhazya`, `Leptadenia`, `Myricaria` (15) | 33–176 | Desert shrubs, same rule as sagebrush by height |
| `Env/Bio/Grass/CanyonPrinceWildRye` | 103 × 164 | Lip grass for a canyon rim |
| `Env/Bio/Plants/Lava_Cactus` (2) | 49–97 | Sparse accent on rock and dirt |
| `Megascans/3D_Assets/SandstoneRockyGround` (6) | 17–54 × 221–774 | Slabs in place of the Nordic beach slabs |
| `Env/Bio/Rock/Desert/Rock_Desert_Stone_A–C` | 24–32 × 34–56 | Stones in place of scaled-down Uluwatu |
| `Env/Bio/Rock/Scree` (8), `Rock_Desert_Rubble_B` | 10–51 | Rubble skirts at cliff feet |
| `Megascans/3D_Assets/Small_stones_pack` (4) | 2–4 × 10 | Pebbles on dirt |
| `Megascans/3D_Assets/Dead_Branches` (4) | 4–11 × 30–41 | In place of driftwood |
| `Env/Bio/Tree/QuiverTree` (10), `BottleTree` (5) | 8.5–40 m | Swap targets for desert trees |

**Beach and tropics**

| Asset | Size | Use |
| --- | --- | --- |
| `Env/Bio/MarineLife` anemones, sea stars, snails, oysters, coral (10) | 7–50 | On the sea bed and tide line, where there is nothing now |
| `Megascans/3D_Plants/Sea_Campion` (4) | 25–29 × 28–46 | Flowering clumps where grass gives way to sand |
| `Megascans/3D_Assets/Beach_Boulder`, `Drift_Wood_Branch_1` | 51 × 110, 20 × 172 | Larger beach litter |
| `Env/Bio/Rock/Limestone` slabs (3) | 27–84 × 83–223 | A second slab kind beside the Nordic one |
| Zamia, lady, Alexandra and cat palms, `Taro`, `Ginger_Plant`, `BananaTree` | 43–381 | Undergrowth under trees and at cliff feet; swap for beach bushes |
| `Env/Bio/Tree/Banyan` (14), `Mangrove` (75) | to 76 m | Swap targets; mangroves at the water's edge |

There is still no tall palm in the game or in the five packs.

**Forest and river**

| Asset | Size | Use |
| --- | --- | --- |
| `BeechFern` (9), `Lady_Fern` (4), `Fern` (7) | 10–103 | Under trees and along banks |
| `YellowArchangel` (5), `Clovers`, `Small_Balsam` (5) | 4–63 | Flowering ground cover in grass |
| `WhiteWindflower` (4), `Goldenrods`, `Willowherb` | 62–173 | Tall flowers at the edges, by the height rule |
| `Blackberry` (18), `Elderberry` (19), `Dwarf_Birch` (14) | 17–172 | Shrubs at cliff feet and under trees |
| `Mossy_stones_pack` (4), `Mossy_Rock`, `MossyForestRock` | 8–71 | Stones in place of beach pebbles |
| `Env/Bio/Rock/River/Rock_River_Stone_01` | 9–20 × 22–37 | On river beds and banks |
| `MossyForestRoots`, logs (`Fallen_Tree_Log`, `birch_log`, `Mossy_Tree_Log`) | 16–81 × 131–551 | Forest floor; a log is walk-through, so off the paths |
| `DeadLeaves_13`, `Env/Bio/Moss/Lumpy` (7), `Mushroom/TurkeyTail` (3) | 7–133 | Leaf litter under trees, moss on shaded rock |
| `Env/Bio/Tree/WhiteWillow` (30), `DouglasFir` (53), `Metasequoia` (22) | — | Swap targets beyond the Kuenovo and pines |

## The packs

| Pack | Licence | Meshes | Verdict |
| --- | --- | --- | --- |
| Namaqualand (Poly Haven) | CC BY 4.0 | 101, each as Nanite (`_NN`) and low-poly (`_LP`) | Use, for what the game lacks (below) |
| Landscape Pro 2.0 (STF3d) | Fab Standard | 61, LOD meshes, no Nanite | Reference only: older and lower-poly than the game's own |
| Procedural Nature Pack (PurePolygons) | Fab Standard, "no AI use" | 48 | Reference only; not loaded |
| Medieval Village (Megascans) | Fab Standard | a 5.3 project, 22 GB | Not opened: no installed engine matches |
| African Slate Quarry (Megascans) | — | — | Did not download |

Namaqualand by family (Nanite versions; fallback triangles in brackets are
what a non-Nanite path would draw):

| Family | n | Height × width | Authors' density | Fills a gap? |
| --- | --- | --- | --- | --- |
| Flowers: gazania, ursinia, stinkkruid, empodium | 22 | 4–26 × 13–42 | 2–20 a m² in patches | Yes: the game has almost no small flowers |
| Heliophila | 3 | 27–40 × 34–166 | 1 a m² | Yes |
| Succulents: cheiridopsis, leipoldtia, ice plant | 20 | 2–31 × 6–93 | 0.1–3 a m² | Yes: none in the game |
| Wild rooibos bush | 5 | 30–53 × 27–74 | 2 a m² | Yes: a shrub below knee height |
| Othonna, didelta, searsia | 20 | 46–321 | 0.01–0.1 a m² | Partly: the game has sagebrush and rabbitbrush |
| Stones, rocks, small boulders | 11 | 4–25 × 8–59 | 0.5–6 a m² | Partly: warmer granite than the game's |
| Boulders 02–06 | 5 | 54–190 × 121–307 | 0.1 a m² | No: desert boulders ship |
| Cliffs, cliff side | 3 | 4–7 m | placed by hand | No |
| Quiver trees | 2 | 147–272 | by hand | No: the game has ten |
| Bark debris, dead quiver wood, dry leaves | 9 | 7–53 | 1 a m² | Small: dead branches ship |

All foliage sits on `MM_MasterMat_Foliage_01a`, the rest on
`MM_MasterMat_General_01a`: two masters to prove in the game.

## What the authors' settings teach

- **Namaqualand** scatters small things thickly and big things rarely:
  stones at 6 a m², flowers 2 to 20, bushes 0.01 to 0.1. Ours runs pebbles
  at 0.8 and has no flowers. Everything aligns to the ground and stops at 45
  degrees; rocks are sunk 1 to 20 cm, which we already do.
- **Landscape Pro** ties a grass type to each landscape layer: grass gets
  grass and the odd flower, dirt gets boughs, ferns and stones, forest
  floor gets clover, ferns and nettles. Its smallest things (clover, stone
  groups) are culled at 10 to 20 m and its grass at 40 to 80 m, so the
  dense small layer costs little. Ours keys almost everything to two
  classes, grass and sand.
- **Procedural Nature Pack** speeds a river by its slope and puts foam at
  the top and foot of each fall. Our Flux rivers have no such foam rule.

## Built: the desert biome on Coagulation

`"biome": "desert"` in `tools/level/ce_upgrade_maps.json` selects
`DESERT_RULES` in `scatter_foliage.py`. Built 2026-11-12 on Coagulation as
local builds on PC 1 and seen in game; not published.

| Rule | From | Where |
| --- | --- | --- |
| grass, short grass, tall grass, weeds, lip grass | the default rules, unchanged | grass |
| bunch grass, dry tufts | game: thatching grass | dirt, and the grass's thin edge |
| scrub | game: small rabbitbrush | any ground, in loose stands |
| foot brush | game: sagebrush, large rabbitbrush | cliff feet only (over knee height) |
| foot rubble | game: desert stones | cliff feet |
| slabs | game: sandstone rocky ground | flat dirt, a few to a road |
| dead wood | game: dead branches | any ground |
| stones, pebbles | Namaqualand: granite rocks, small boulders, stones | dirt |
| flowers | Namaqualand: gazania, ursinia, stinkkruid, empodium (low-poly) | where grass thins to dirt |
| meadow flowers | Namaqualand: heliophila (low-poly) | drifts through the grass |
| succulents, ice plants | Namaqualand: cheiridopsis, leipoldtia, ice plant | dirt, in colonies |
| rooibos | Namaqualand: wild rooibos bush | dirt along the roads |

About 110,000 pieces over the default grass. What the build settled:

- **A pack mesh cooks and draws.** A mesh under a `foliage_bake.COOKED`
  prefix gets no stand-in; the landscape world names the real asset, and
  the cook puts it, its material instances, the pack's two masters and its
  textures into the map's own landscape container (chunk 1001). `mjolnir ue
  retarget` re-encoded them with the rest; the game draws them lit and
  shadowed with no loader change.
- **Textures decide the size.** The pack's maps are 4K: the container went
  from 333 MB to 1.2 GB. `Scripts/cap_pack_textures.py` sets Maximum
  Texture Size 1024 on the pack's 199 larger textures (the source art
  stays in the package): 212 MB, and the pieces still draw.
- **Frame cost.** At one meadow spot on PC 1 at 4K the foliage cost 4.6 ms
  with every Namaqualand mesh as Nanite and long cull distances, and 3.1 ms
  with the small flowers as the pack's low-poly meshes and the culls pulled
  in. The same map's foliage measured about 2.5 ms before the biome, at
  another spot, so the comparison is rough.
- **CE maps unchanged.** Blood Gulch's and Death Island's scatter output
  (`foliage.bin`, `foliage.json`) is byte for byte the same from the
  committed code and from this change.
- **Grey scree in a red canyon** read wrong and was dropped from the foot
  rubble; the game's small-stones pack is grey too, which is why the
  stones are Namaqualand's.
- **Needs the pack.** A machine without `/Game/Namaqualand` in
  `unreal/MJOLNIRMaterials` cannot build a desert map. The pack is not in
  the repo (`Content/` is ignored): add it from Fab, version 5.4, then run
  `cap_pack_textures.py`.
- **Credit.** Namaqualand is CC BY 4.0: a published map that uses it must
  credit Poly Haven. It is on the Hub's credits page
  (`hub/src/lib/credits.ts`), marked as not yet in a release;
  docs/credits.md says how the list is kept.

## Built: the coast biome on Zanzibar

`"biome": "coast"` selects `COAST_RULES`: every default beach rule as it
is, plus the rows below. Built 2026-11-12 on Zanzibar as local builds on
PC 1 and seen in game; not published.

| Rule | From | Where |
| --- | --- | --- |
| sea life, sea stars | game: anemones, snails, oysters, coral, sea star | the sea bed, 0.25 to 3.5 m down |
| sea campion | game | where grass thins to sand |
| foot palms | game: zamia, lady and Alexandra palms, taro, ginger | wall feet only |
| limestone, drift branches | game | sand near the water |
| ice plants, succulents | Namaqualand | dry sand above the tide |
| beach bushes | game: young Alexandra and cat palms | swapped for Halo 2's seven `bush_beach_a` |

What Zanzibar needed beyond the rules:

- **A sea of its own.** The conversion has no water surface (Halo 2 draws
  Zanzibar's sea as fog over the bed). The Flux coast sits at the fog
  plane's height, -903 cm, and the shoreline wave overlays are hidden.
- **Sand and grass the right way round.** The ground master reads base
  alpha 1 as sand, CE's order. Zanzibar's ground shaders list their weeds
  first, so the beach drew as a lawn with the pebbles on it. The landscape's
  bake flips the alpha of such a shader (`build_landscape --grass-primary`,
  from the config's `details`), and the terrain mesh's own slots of it take
  `LandMix` with its edges swapped (`cut.looks`), since they read the
  unflipped base map.
- **A crack across the beach.** The landscape is a square around the first
  ground shader's ground, Zanzibar's inland dirt, so it stopped part way
  down the beach; past its edge the terrain mesh draws 8 cm lower, and the
  step was a dark slit with the sea showing through. `landscape_square`
  names the shaders the square is drawn around (the dirt and the beach
  proper): the landscape went from 189 m to 252 m a side, its bake from 18
  to 25 cm a texel.
- **Frame cost** on the beach at 4K on PC 1: 12.4 ms, foliage 0.8 ms of it.
- Blood Gulch's scatter and landscape bake are byte for byte the same from
  the committed code and from this change.

- **Its two cliff trees stay Halo 2's.** They lean 35 degrees out of the
  rock face with their origin half way up their bounds, in the air beside
  it. Swapped as standing trees, an upright 13 m tree hung in the sky
  there. `instance_scenery.py` now leaves out any instance whose origin
  is more than a quarter of the way up its bounds; Coagulation's cedars
  (a tenth) still swap.

Not checked on Zanzibar: collision against the new pieces, the far side
of the map, and the sea from inside the base's tunnels (one cut zone was
made there).

## Built: structure walls in PBR surfaces

A converted map's concrete and steel are one small colour map stretched
over tens of metres: flat paint beside the remastered rock. Zanzibar's now
draw in a real surface (2026-11-12, local builds, seen in game, not
published).

- **How.** `structure_surfaces` in the map's config names structure
  shaders and a surface. The loader (`Land.structures`, Level Loader
  0.13.8) draws their slots with the cliffs' master, `M_CE_CliffPBR`: the
  surface projected in world space at real size, the map's own base map
  as its colour at 0.85 (so Halo 2's rust streaks, panel lines and tide
  stain stay where they were) and its lightmap as shade. No new master.
- **Surfaces.** `Scripts/build_surfaces.py` imports a Poly Haven texture
  set (CC0) as three maps, as the game's Megascans rock has them: colour,
  normal, and occlusion, roughness and height packed in one. They live in
  `/Game/MJOLNIR/CETrial/Surfaces` and cook into the runtime container
  (983), at about 13 MB a set. (A third set, a stained plaster, was
  tried as the large layer, read orange and was removed.)
- **Zanzibar.** Concrete Wall 008 over nine concrete shaders (the sea
  wall, the base's massive concrete, the pier, painted and interior
  concrete, floors, the rubble chunks), Rusty Metal Sheet over five metal
  ones (the wheel, weathered steel, pipes, roofs): 195 slots.
- **Tuning that mattered.** The first build was tan and overbright: the
  cliffs' warm bounce fill at full strength, and a stained-plaster set as
  the large layer. The fill is now neutral at 0.3, the base map's gain
  0.75, and one concrete serves both layers. Tile variation is off for
  concrete (it chops formwork lines) and on for steel.
- **The polish pass on the big wall.** Up close in full sun it was still
  near white with nothing to see. What fixed it: the base map's gain down
  to 0.5 and its share to 0.7; grain contrast 2.2 and normal strength 2;
  a second, stained concrete (Concrete Wall 006) as the large layer at
  0.6; weathering streaks at 0.5; and three of the cliffs' effects a set
  can now ask for: `drape` (stains running 9 m down from a wall's top, by
  the landscape's edge map, with no turf), `foot` (contact shade where it
  meets the ground) and `wet` (dark and glossy within 70 cm of the sea).
- **Grime decals were tried and dropped.** With `"grime": true` the
  pipeline laid 517 soil and leak decals on the concrete; in game the
  leaks drew as small dark blurry rectangles on the wall. `grime_decals`
  now takes the `structure_surfaces` shaders as structure, but Zanzibar
  leaves grime off.
- **Frame cost.** 7.7 ms at 4K on PC 1 facing the big wall from the beach
  (not a matched before and after).
- **A sawtooth shadow edge.** Lit by the real sun, a smooth wall the sun
  skims showed its shadow's edge as a row of teeth: shadow texels
  stretched down the face (they grew with a coarser shadow map and shrank
  with a finer one). `environment.sun.shadow_normal_bias` (Level Loader
  0.13.8) sets `r.Shadow.Virtual.NormalBias` for the map, restored with its
  other shadow settings; the engine's 0.5 left the teeth, 2 shrank them,
  3 cleared them. Zanzibar uses 3. Side effects elsewhere on the map
  (contact shadows starting off an object's base) have not been looked for.
- **Steel, second pass.** One rust sheet over every metal read as orange
  blotches on the upper decks. Weathered steel, the wheel and pipes now
  take Metal Plate 02 and the roofs and rippled panels Corrugated Iron 02,
  each with the rust sheet as its large layer only. The darker concrete
  settings left interiors too dim: the base map's gain went back up to
  0.62 and the fill to 0.5.
- **Halo 2's wall decals flashed as the player walked.** A sign went from
  clear to a dark smear between two side steps. Not occlusion culling (the
  same with occlusion queries off) and not the upscaler alone (one dark
  frame with anti-aliasing off). With auto exposure forced off the scene
  blew out and the decal stayed dim: it is an unlit, alpha-blended quad
  that does not follow the scene's exposure, so it changed against the
  wall whenever the exposure adapted. Assemble now makes each alpha-blended
  `h2_decal_<n>` a lit cut-out (`M_CE_EnvironmentMasked`, no lightmap);
  steady over the same steps. Additive decals are unchanged, and a sign in
  shade is now as dim as its wall.
- **Every sign was drawn twice.** Assemble added its own quad a decal
  (`ce_decal_<n>`, square) over the conversion's (`h2_decal_<n>`, at the
  decal's aspect): two images at different sizes, fighting. Assemble now
  adds none when the conversion placed them. Coagulation has no decals, so
  it was not affected.
- **Not done:** metals are drawn as painted steel (the master has no
  metallic input); props, signs and the crane keep Halo 2's textures;
  other Halo 2 maps have no `structure_surfaces` yet.

## Proposal

1. **Biomes, opt-in, as `SNOW_RULES` is.** `desert` (Blood Gulch,
   Coagulation), `forest` (Timberland, Battle Creek, Danger Canyon), and the
   default beach rules extended for `coast` maps (Death Island, Yoyorast,
   Zanzibar). The default `RULES` stays as it is, so a map with no biome
   scatters byte for byte what it does now.
2. **Game assets first.** Every row in "The game's own assets" needs no
   cook and no licence. A desert rule set from them: thatching grass on
   dirt, small rabbitbrush, sandstone slabs, desert stones, scree at cliff
   feet, small stones, dead branches, canyon rye on the lips.
3. **New placement keys**, each from data the pipeline already has:
   - `foot`: within a few metres of a cliff's base (the landscape's edge
     map knows lips; the foot is the same test from below). For scree,
     shrubs taller than a knee, ferns.
   - `under`: within a swapped tree's crown (`swap.json` has every tree).
     For ferns, dead leaves, mushrooms, shade plants.
   - `bed` and `bank`: below and just above a Flux river or coast's water.
     For river stones, marine life, mangroves.
   - `around`: a ring round a swapped rock. For flowers and tufts that hug
     boulders.
4. **Height rule kept.** Anything over about 50 cm goes only where a player
   cannot walk (cliff feet behind the collision, ledges, the sea bed), or
   is a swap for scenery that already has collision.
5. **Namaqualand second, after a cook proof.** Flowers, succulents, rooibos
   and the small granite stones are what the game cannot supply.

## Not proven

- **Tints and bands on pack meshes.** The desert rules set no tint on a
  Namaqualand mesh, so whether the loader's tint reaches the pack's
  masters is untested. Band culling is used and the pieces do thin out.
- **Looks beyond Coagulation.** The forest and coast lists are still
  chosen by name and size, not by seeing them.
- **The new placement keys** (`under`, `bed`, `bank`, `around`) are not
  built; `foot` already existed as `"wall": "foot"`.
- **No fixed-camera before and after**, and no bench at a matched spot.
- **Collision.** None of the new pieces collides; the tall ones are kept
  to cliff feet for that reason, and nobody has walked the map to check.
- **Licences.** Only Namaqualand (CC BY 4.0, needs a credit line) is clear
  to ship. The Fab Standard packs are reference until their terms on
  redistributing cooked assets in a free mod are read.
- **Blood Gulch is published.** Changing its dressing is a release.
