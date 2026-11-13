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
- **A black strip under the sea.** With the landscape reaching the water
  (`landscape_square`), a coast's `seabed` shelving pushed its floor down
  by up to 8 m away from the shore. That is for CE's flat sea floors a
  metre under the water; Zanzibar has a real sloping bed, and the lowered
  copy opened a gap against it, black with Flux off and a dark wedge in
  the water with it on. Zanzibar's coast now has `"seabed": false`: the
  landscape keeps Halo 2's own bed heights.
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
  0.6; weathering streaks at 0.5; and two of the cliffs' effects a set
  can ask for: `foot` (contact shade where it meets the ground) and `wet`
  (dark and glossy within 70 cm of the sea). (`drape`, the cliffs' stains
  from a wall's top, was used here at first and removed: see "Bubbled
  floors".)
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
- **Bubbled floors: `drape` is not for structures.** The base's concrete
  floors drew a bubbly default texture. `drape` turns on the cliffs' turf
  and earth at a lip, which a structure set gives no textures for, so the
  master's defaults drew over every flat surface under a wall top.
  Zanzibar's sets no longer set `drape`; the streaks from `far` stay.
  (First blamed on the large layer's normal map, because the live test had
  silently dropped `drape`, `foot` and `wet`; removing each in turn showed
  it was `drape` alone.)
- **The crane deck.** Its floor (`zanzibar_grating`) is a 128 pixel map
  over 6 m, a texel nearly 5 cm across. It and the crane's body now draw
  in Metal Plate 02, tinted darker, with the base map's share at 0.65 so
  the panel lines stay.
- **Every sign was drawn twice.** Assemble added its own quad a decal
  (`ce_decal_<n>`, square) over the conversion's (`h2_decal_<n>`, at the
  decal's aspect): two images at different sizes, fighting. Assemble now
  adds none when the conversion placed them. Coagulation has no decals, so
  it was not affected.
- **Not done:** metals are drawn as painted steel (the master has no
  metallic input); props, signs and the crane keep Halo 2's textures;
  other Halo 2 maps have no `structure_surfaces` yet.

## Built: the texture audit on Zanzibar

2026-11-12, local builds on PC 1, seen in game, not published.

- **`tools/level/texture_audit.py <CODE>`** lists every shader with its
  area, base map size and the size of a texel on the surface, worst
  first. Zanzibar: 81 shaders. Its `treatment` column is derived from the
  config by name and is wrong for hidden slots (the shoreline waves show
  as converted): it should read the assembled level.
- **The fresh conversion's containers were never installed.** The remaster
  install puts in the map and landscape containers only; the texture and
  mesh containers (`MJOLNIRCOOK-ZAN`, `MJOLNIRMESH-ZAN`) stayed the hub's,
  from an older conversion. 516 texture lookups failed at load (detail
  maps, alpha variants), so most slots drew without their detail maps for
  the whole of the earlier tuning. Installed as local builds by hand
  (`mjolnir dev install`), as Coagulation's were: 0 failures. The install
  stage now does it for a map with `"conversion_containers": true` (both
  Halo 2 maps), and stops before touching the game when one is missing.
- **Wholesale upscaling, tried and removed.** The base maps of
  everything the remaster leaves as converted, and the wall decals, went
  through Upscayl's Real-ESRGAN build (55 textures, 111 slots). The
  results looked bad in game, the signs worst, and the step is gone
  (`upscale_textures.py`, the `upscale` key, the imported copies). No
  texture is enlarged by a model unless someone chose it and said what
  it shows: see "Redrawn, one at a time" below.
- **What an upscaler cannot do.** A 64 by 32 sign stays rough: three
  models each invented different letter shapes. The palm bark is 16 by
  128. Those need new art.
- **`structure_metal: false`.** Assemble dresses any slot whose base map
  name holds "metal", "strip", "pipe" and so on as Forerunner plate.
  Zanzibar's hazard stripes ("strip") drew with silver blobs. Off for
  Zanzibar: a human installation.
- **Dark shaded walls.** A wall out of the sun had only the sky's light
  and a fill of 0.5: 0.10 to 0.24 mean luma in the tour's shaded and
  interior views. Every set's fill is now 1.3 and the base map's baked
  shade share (`look[2]`) 0.2: those views read 0.20 to 0.47. The sunlit
  big wall from the beach went from 0.60 to 0.65 with 8% of the frame
  clipped, which is hot. Measured over four of the tour's seven spots;
  at the other three the player had died and respawned elsewhere, so
  those views do not compare.
- **Weathering ("too clean").** Sharp surfaces with nothing settled on
  them. Zanzibar's concrete now takes `drape` again, done properly: the
  loader gives a set with `drape` the cliffs' soil and the ground's grass
  textures (the missing ones were the bubbled floors' cause), a `moss`
  tint, and `CliffLedge` 0, a new parameter of M_CE_CliffPBR that turns
  off turf on every up-facing surface, so floors stay concrete (Level
  Loader 0.13.9; the trial masters rebuilt). Earth and a moss fringe under
  each wall top, stains 9 m down, the stained layer's share 0.75,
  streaks 0.7. `"grime": "soil"` lays the soil decals at wall feet
  without the leaks (117 on Zanzibar). The concrete was then too bright
  in sun to show any of it: tint 0.8 and base gain 0.48 took the big
  wall's view from 8% to 4% clipped. Checked at the big wall and one
  interior corridor (clean floor).
- **Flat steps: the baked corners were thrown away.** An interior
  stairwell drew with no shape: no sun reaches it, the emissive fill is
  uniform, and the 64 pixel lightmap is flat there (following it at full
  share changed nothing). The conversion's own bake (`lightmap_bake`, red:
  corner occlusion at four times the lightmap's resolution) is what the
  CE masters shade corners with, and M_CE_CliffPBR ignored it. It now
  takes `Bake` and `CliffBakeAO` (power; 0 off, the cliffs' default), a
  set's `bake_ao` (Level Loader 0.13.11). Risers and wall joints shade.
  Zanzibar settled at `bake_ao` 1.6, `fill_occlusion` [0.25, 1.0] and a
  fill of 1.6: at 2 with a 0.45 share the room at the stairwell's foot
  measured 0.17 mean luma with 8% near black; now 0.21 to 0.23 with 6 to
  7%, a dim interior, and the beach clips 3%.
- **Steel weathering.** The steel sets' rust layer was a faint 0.25 to
  0.35 share in patches 25 m across, streaks 0.3: clean plate. Now 0.5
  to 0.65 in 13 to 15 m patches with streaks 0.65 (`mix[0]`, `tiles[2]`,
  `far[2]`); the wheel, the corrugated walls and the gantry read rusted
  where rain runs. Config only.
- **Soil decals dropped too, and a stick that swayed.** The soil decals
  at wall feet (`"grime": "soil"`) drew as streaked translucent
  rectangles on the concrete, the same on every wall: off for Zanzibar,
  so it has no grime decals at all. A dry branch on the beach rocked in
  the wind: the coast's and desert's dead wood is now `static` (a scatter
  rule's flag, carried to the group); the default rules are unchanged.
  The decals' removal was written up before it landed: the config kept
  `"grime": "soil"` and the user found the same streaks again. It is out
  now (0 grime decals in the installed level, the wall foot clean in a
  frame), and the branch is still across three frames a second apart.
- **Occlusion and atmosphere.** The walls' fill is emissive, so nothing
  occludes it: the engine's SSAO and bent normals, switched on live, made
  no visible difference. `fill_occlusion` [share, power] (CliffFillDir's
  z and w, Level Loader 0.13.10) makes the fill follow the map's baked
  lightmap shade instead, so corners and overhangs darken where Halo 2
  shaded them. 0.85 at power 1.5 turned shaded walls black again; 0.45
  at 1 keeps them readable (0.31 to 0.41 mean luma at the crane).
  `haze_look` overrides the CE-derived fog: Zanzibar's started 1.5 km
  out, now 10 m, density 0.03, with a warm glow towards the sun
  (`haze.sun`). `environment.post` gains `vignette`; Zanzibar sets bloom
  0.5 and vignette 0.3. Tuned at two spots only.
- **Detail and bump maps.** `texture_audit.py` now measures them too
  (`detail_cm`, `bump_cm`, `sharpest_cm`). Zanzibar, of what the remaster
  leaves as converted: five shaders (1,915 m2, mostly cliff tree leaves)
  have every layer over 1 cm a texel, and seven have a base map alone.
  Of those seven, two are sky and one the hidden wave sheet; the rest is
  the wheel (metal_wheel, flywheel_metal, carbon_blade: 2,425 m2), which
  turns, so a world-space structure surface would swim on it.
  `detail_fill` gives base-only slots one of the conversion's own detail
  maps (the rusted metal one, 24 times a copy: 5 slots, no cook). The
  effect on the wheel is slight. The audit sizes the converted textures, not a redrawn copy.
- **Not done:** the wheel and the small props still have no bump map of
  their own. The baseline tour for
  comparison was captured looking down by mistake, so there is no
  like-for-like map-wide before and after.
- **Redrawn, one at a time** (`tools/level/redraw_texture.py`,
  `"redrawn": true`). An image model given the magnified texture, what
  it is and what it reads ("NOTICE / ENTRANCE FOR / EMPLOYEES / ONLY")
  draws the same sign again, legible, at 1024 on its long side; the
  source's alpha is kept, so a cut-out's outline is Halo 2's. Each
  result is looked at beside its original before it goes in. A file in
  `<work>/redrawn/` named for the texture is imported by the editor
  stage (which removes any other from the map's `Up` folder) and
  assemble points the level's `Base` and `Map0` at it. Zanzibar: 14 of
  its 16 wall decals and the no-swimming sign, each with a description
  and its words read off the original by hand (text, pictograms and the
  hazard placard came back in place; colours run more saturated than
  Halo 2's). The two 4:1 caution strips are as converted: over the
  model's 3:1 limit, and their shape is in the alpha. So is everything
  else that was upscaled: the wheel, hazard stripes, props, tree
  leaves. The key comes from `OPENAI_API_KEY` or `.env.local` (ignored
  by git); the texture is sent to OpenAI.
- **Bump maps for a redraw** (`redraw_texture.py --normal-map`, then
  `tools/level/redraw_bump.py`). A colour map redrawn at four times the
  size sat on a bump map a quarter as sharp. Tried on the tyre props
  (256 to 1024). Guessing relief from the colour alone was not tried:
  it discards the rim, bolts and tread depth Halo 2's artists built.
  Integrating the original normal map to a height, enlarging it along
  the redraw's edges and deriving normals again gave soft, lumpy bevels,
  worse than a plain enlargement. Asking the image model to redraw the
  normal map itself worked: clean bevels, the same layout, and slopes
  that still agree with the original's (0.83 and 0.88 correlation in x
  and y). `redraw_bump.py` then makes the picture a normal map again:
  unit length, its broad slopes and overall strength held to the
  original's, the colour redraw's grain added as fine relief, and a
  warning when the model's slopes agree under 0.6. Assemble swaps a
  redrawn `Bump` as it does `Base` and `Map0`. `--alpha smooth` keeps a
  specular mask's levels instead of cutting an outline.
- **DeepBump, compared in game** (`tools/level/deepbump_normals.py`;
  DeepBump is GPL-3.0, cloned outside the repo and run as a tool, with
  `onnxruntime`). Each candidate was swapped into the running game
  through the level file (a file texture, `linear`) and captured from one
  camera, so only the bump map differs. Tyres: the image model's redraw
  of the bump map stayed best; DeepBump from the colour map read lumpy
  (slopes agree with Halo 2's 0.43 / 0.51); its 4x enlargement of the
  original was close to the original and little sharper. Fusion coil
  body (the military props' 256 atlas): the image model's redraw of the
  bump map failed the check (0.45 / 0.56) and its 4x looked like the
  original, but DeepBump from the redrawn colour gave the panels grooved
  edges and the end caps deeper rings, so that is what the build uses,
  though its slopes agree with Halo 2's only 0.20 / 0.24 and it reads
  some dark grime as dents. The wrapper puts its green in the source's
  convention and keeps the source's alpha. Which tool wins is per
  texture: look at both in game.
- **CE maps unchanged.** Blood Gulch, Death Island, Rat Race, Ice Fields
  and Timberland assemble to the same bytes with this branch's pipeline
  as with its merge-base's.

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
