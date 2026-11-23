# Base-game assets for Pelican Warfare

A catalogue of assets that ship in Halo: Campaign Evolved (Steam, CU4) that could raise PWR's detail. This is read-only research: nothing in the install or the repos was changed. Generated 2026-11-23 by `out/pwr-assets/_work/build_catalog.py` and `write_md.py`; the full structured data is in `catalog.json`.

**How it was built.** Every non-MJOLNIR `.utoc` was listed (102,878 packages, including the Halo plugins mounted at `/HaloMaterialLibrary`, `/HaloPCG` and `/HaloLandscapeDeformations`). The asset kind comes from the export class in each zen package header, and the imported-package lists were read from the same headers. Vertex counts and bounds come from `mjolnir mesh list` and are render vertices, not triangles. Size is the cooked `.uasset` plus `.ubulk` bytes. "Used in levels" means the package is reachable from a shipped level's umaps (persistent level, World Partition cells and the level's own level-instance packages), directly or through BPs, level instances or materials (Blam tags excluded). For PWR use, **yes** means the built map uses it: PWR's containers import it, or `pwr.level.json` or an upgrade JSON names it. **listed** means only a PWR palette or script names it.

**Totals:** 4955 candidates. River bed, banks and cascade: 255; Lakes and shores: 453; Roads and verges: 167; Forests: 1094; Mountains, cliffs and sky: 690; Open meadow ground and landscape materials: 703; Atmosphere, life, light and sound: 669; Structures, wreckage and other set dressing: 924.

**Constraints applied:** decals are flagged `decal` and kept out of the top 30, because cooked decal masters crashed PWR with a PSO fatal. Anything that adds foliage instances is flagged `foliage` and ranked lower, since foliage is already about 18% of the GPU frame. Render-only meshes are flagged `collision` where players will touch them. Off-biome (tropical, alien, marine) assets are flagged `setting`. Everything recommended is data the map ships: decor, materials, Niagara and Blam objects, with no per-frame Lua.

**Notes.**
- Category counts include part meshes: the Pine family alone contributes about 470 entries (trunks, branch clusters, proxies). Trees are multi-part assemblies; use the A30/B40 assembly recipes.
- pwr_uses 'listed' = named in a PWR palette or script (asset-palette-v3.json, playable-*-palette.json, meadow_life.py, audit scripts) but not in the built map.
- No sign, lamp-post, fence, bollard, traffic-cone, curb or puddle meshes ship under Env/HS or elsewhere (regex sweep). Tire marks exist only as the HaloLandscapeDeformations toolkit.
- PWR already ships its own analogues for some categories (no base-game clones found by basename): SM_PWR_SweepMossBanks, SM_PWR_CutbankRoots, SM_PWR_OutletAlluvium, SM_PWR_SpringCascade, SM_PWR_SweepDeadPine, SM_PWR_SweepLitter_*, T_PWR_RiverCobble_BC/N, T_PWR_FRDiagonal_N/ORHG, M_FR_BridgeLight.

## Top 30 recommendations (ranked)

### 1. Riparian bank kit on the river and lake edges
*Category 1 (River bed, banks and cascade).*

- `/Game/Env/Bio/bank/Riparian/Bank_Riparian_Slopes_Lrg_A/SM_Bank_Riparian_Slopes_Lrg_A` (StaticMesh, 291,876 verts, 49.3x37.9x13.3 m, 9.5 MB, levels C10, PWR no)
- `/Game/Env/Bio/bank/Riparian/Bank_Riparian_Cliff_Lrg_A/SM_Bank_Riparian_Cliff_Lrg_A` (StaticMesh, 327,721 verts, 45.0x13.5x35.6 m, 10.4 MB, levels C10, PWR no)
- `/Game/Env/Bio/bank/Riparian/Bank_Riparian_Trapezoidal_Lrg_A/SM_Bank_Riparian_Trapezoidal_Lrg_A` (StaticMesh, 276,757 verts, 67.9x28.7x40.8 m, 9.0 MB, levels C10, PWR no)
- `/Game/Env/Bio/bank/Riparian/Bank_Riparian_Trapezoidal_Lrg_B/SM_Bank_Riparian_Trapezoidal_Lrg_B` (StaticMesh, 330,173 verts, 80.3x43.5x39.1 m, 11.0 MB, levels C10, PWR no)
- `/Game/Env/Bio/bank/Riparian/Bank_Riparian_Square_Lrg_A/SM_Bank_Riparian_Square_Lrg_A` (StaticMesh, 207,959 verts, 79.3x28.1x41.2 m, 7.1 MB, levels C10, PWR no)
- `/Game/Env/Bio/bank/Riparian/Materials/MIP_Bank_Riparian_Wet` (MaterialInstance, 88KB, levels C10, PWR no)

- **Where:** Cut banks along the river, lake inlets, the cascade's lower course.
- **Why it reads as shipped:** Purpose-built eroded bank modules (45-80 m long, 208-330k verts, mud and damp-soil Megascans textures) with dry and _Wet instances. They give the undercut, layered bank silhouette a heightfield cannot. Only C10 (343 Guilty Spark) places them, on its swamp waterways. PWR's own SM_PWR_SweepMossBanks, SM_PWR_CutbankRoots and SM_PWR_OutletAlluvium cover parts of this; the shipped modules add large-scale bank forms.
- **Cost and risk:** Nanite decor, 7-11 MB each; no foliage. Render-only, so the terrain must still carry Blam collision. Low-medium risk (size and seat on the terrain).

### 2. Adopt A30's river-valley landscape texture sets
*Category 6 (Open meadow ground and landscape materials).*

- `/Game/Megascans/Surfaces/Wild_Grass_and_Weeds_rm5krfp0/T_Wild_Grass_NSVT_D_A30` (Texture, 2.8 MB, levels A30, PWR no)
- `/Game/Megascans/Surfaces/Wild_Grass_and_Weeds_rm5krfp0/T_Wild_Grass_and_Weeds_rm5krfp0_NSVT_N` (Texture, 5.6 MB, levels A30, PWR no)
- `/Game/Megascans/Surfaces/Wild_Grass_and_Weeds_rm5krfp0/T_Wild_Grass_NSVT_ORHG` (Texture, 5.6 MB, levels A30, PWR no)
- `/Game/Megascans/Surfaces/Stones_on_Soil_rmsijrp0/T_Soil_Stone_NSVT_A30_D` (Texture, 2.8 MB, levels A30, PWR no)
- `/Game/Megascans/Surfaces/Gravel_ground_vl1oabbfw/T_Scree_NSVT_A30_D` (Texture, 2.8 MB, levels A30, PWR no)
- `/Game/Megascans/Surfaces/Beach_Sand_With_Pebbles_vl0fdilo/T_Beach_Sand_With_Pebbles_vl0fdilo_2K_NSVT_D` (Texture, 2.8 MB, levels A30,B30, PWR no)
- `/Game/Levels/Halo1/Solo/A30/Landscape/Materials/MM_A30_Landscape` (Material, 55KB, levels A30, PWR no)
- `/HaloMaterialLibrary/MaterialFunctions/MF_Hex_TextureBombing` (MaterialFunction, 0KB, levels A15,A30,A50,B30,B40,C10,C20,C45,D20,D40,E10,E20,E30, PWR no)

- **Where:** Meadow (wild grass and weeds), stony soil on rises, scree band under cliffs, pebble riverbed.
- **Why it reads as shipped:** A30 (Halo) is the shipped temperate river valley. Its master blends exactly these sets (A30-tinted NSVT diffuse copies, plus N/ORHG) with hex texture bombing and a wetness pass. PWR's material can reuse the textures and copy the recipe.
- **Cost and risk:** About 40 MB of textures for four sets. PWR's meadow is shaded from CE detail textures plus its own base map, and the surfaces block has only Rock, Rip, Sand and SandB slots, so new Grass, Scree and Riverbed slots must be added to M_PWRPilot (a material change, then data). MF_* functions are a recipe, not something PWR's master can call. Medium.

### 3. A30's river boulder and log-jam assemblies
*Category 1 (River bed, banks and cascade).*

- `/Game/Levels/Halo1/Solo/A30/PCG/Assemblies/Boulder/LI_BoulderRiver_A` (LevelInstance, 8KB, levels A30, PWR no)
- `/Game/Levels/Halo1/Solo/A30/PCG/Assemblies/River_LogDebris/LI_RiverLogs_A` (LevelInstance, 11KB, levels A30, PWR no)
- `/Game/Levels/Halo1/Solo/A30/PCG/Assemblies/River_LogDebris/BP_RiverLogAssembly_A` (Blueprint, 2KB, levels A30, PWR no)

- **Where:** River bends, the cascade foot, ford approaches.
- **Why it reads as shipped:** Shipped, art-directed clusters: tundra boulders, scree clump, PNW mossy boulder and rock shelf, Nordic beach rocks (boulders); mossy, birch and fallen logs with ferns and tall grass (log jam). Copying a shipped arrangement reads as authored.
- **Cost and risk:** Recipe: read member transforms from the level-instance cells, re-emit as decor. Nanite decor, no new foliage types. Low risk.

### 4. Alpine scree kit and A30 scree assemblies
*Category 5 (Mountains, cliffs and sky).*

- `/Game/Env/Bio/PNW/Meshes/SM_Scree_Alpine_A/SM_scree_alpine_a` (StaticMesh, 16,928 verts, 7.7x6.3x3.0 m, 0.7 MB, levels A30, PWR no)
- `/Game/Env/Bio/PNW/Meshes/SM_Scree_Alpine_B/SM_scree_alpine_b` (StaticMesh, 15,970 verts, 7.0x6.3x3.7 m, 0.6 MB, levels A30, PWR no)
- `/Game/Env/Bio/PNW/Meshes/SM_Scree_Alpine_C/SM_scree_alpine_c` (StaticMesh, 16,202 verts, 7.7x6.8x3.0 m, 0.7 MB, levels A30, PWR no)
- `/Game/Env/Bio/Rock/Scree/Scree_Rock_Clump_A/SM_Scree_Rock_Clump_A` (StaticMesh, 2,627 verts, 1.9x2.1x0.3 m, 0.2 MB, levels A30, PWR no)
- `/Game/Env/Bio/Rock/Scree/Scree_Rock_Clump_B/SM_Scree_Rock_Clump_B` (StaticMesh, 4,684 verts, 3.6x2.0x0.5 m, 0.3 MB, levels A30, PWR no)
- `/Game/Levels/Halo1/Solo/A30/PCG/Assemblies/Scree/LI_Scree_Ground_B` (LevelInstance, 13KB, levels A30, PWR no)

- **Where:** Talus fans under every cliff band and around the glacial rocks.
- **Why it reads as shipped:** 7 m scree aprons (16-17k verts) from A30 plus flat scree clumps; they bed big rocks into the ground, which is what separates shipped rockwork from rocks dropped on grass.
- **Cost and risk:** Low-poly decor. Low risk.

### 5. Snow-capped instances of the rocks PWR already places
*Category 5 (Mountains, cliffs and sky).*

- `/Game/Env/Bio/Rock/Glacial/Rock_Glacial_Lrg_B/Materials/MI_Rock_Glacial_Lrg_B` (MaterialInstance, 87KB, levels B40,C20,C45, PWR no)
- `/Game/Env/Bio/Rock/Glacial/Rock_Glacial_Lrg_C/Materials/MI_Rock_Glacial_Lrg_C` (MaterialInstance, 87KB, levels B40,C20,C45, PWR no)
- `/Game/Env/Bio/Rock/Glacial/Rock_Glacial_Med_B/Materials/MI_Rock_Glacial_Med_B` (MaterialInstance, 0.2 MB, levels B40,C45, PWR no)
- `/Game/Env/Bio/Rock/Glacial/Rock_Glacial_Lrg_B/Materials/MI_Rock_AllSnow` (MaterialInstance, 87KB, levels B40,C45, PWR listed)
- `/Game/Env/Bio/Rock/Scree/Materials/MIP_Rock_Glacial_Scree_Snow` (MaterialInstance, 89KB, levels B40,C45, PWR no)

- **Where:** Glacial rocks above the snow line.
- **Why it reads as shipped:** PWR places the glacial family with the _NoSnow instances everywhere. `ue get` confirms the default instances stream Fresh_Windswept_Snow textures and carry a top vector mask (Color Top); the _NoSnow ones do not. Rocks above the snow line would then match the snow ground.
- **Cost and risk:** Material swap by altitude in the tool; zero new meshes. Very low risk.

### 6. Snow-line transition surfaces from B40
*Category 5 (Mountains, cliffs and sky).*

- `/Game/Megascans/Surfaces/Snow_Covered_Grass_ueolejtn/T_Snow_Covered_Grass_ueolejtn_NSVT_D` (Texture, 2.8 MB, levels B40,C45, PWR no)
- `/Game/Megascans/Surfaces/Fresh_Windswept_Snow_uhpjdeyn/T_Fresh_Windswept_Snow_uhpjdeyn_NSVT_D` (Texture, 2.8 MB, levels B40,C45, PWR no)
- `/Game/Megascans/Surfaces/Windswept_Snowy_Stones_tdloaf1r/T_Windswept_Snowy_Stones_tdloaf1r_NSVT_D` (Texture, 2.8 MB, levels B40,C45, PWR no)
- `/Game/Megascans/Surfaces/Melting_Snow_uepnbikfw/T_Melting_Snow_uepnbikfw_NSVT_D` (Texture, 2.8 MB, levels B40,C45, PWR no)
- `/Game/Levels/Halo1/Solo/B40/Landscape/Materials/MM_Landscape_B40` (Material, 0.2 MB, levels B40,C45, PWR no)

- **Where:** The band between the meadow and the Windswept_Snow peaks, snowy stone fields on the upper slopes.
- **Why it reads as shipped:** PWR jumps from grass to Windswept_Snow. B40 (Assault on the Control Room) shipped the in-between: snow-covered grass, snowy stones, melting snow, each with D/N/ORHG, blended with stochastic snow flakes.
- **Cost and risk:** About 12 MB of textures per set. Like the A30 sets, they need new surface slots in M_PWRPilot (a material change, then data). Medium-low.

### 7. Finish the ground surfaces PWR already samples (add their ORHG maps)
*Category 6 (Open meadow ground and landscape materials).*

- `/Game/Megascans/Surfaces/Ground_Grass_tb3nce2k/T_Ground_Grass_NSVT_4K_OHRG` (Texture, 5.6 MB, levels B30, PWR no)
- `/Game/Megascans/Surfaces/Tundra_mossy_ground_vjulbjjr/T_Tundra_mossy_ground_vjulbjjr_NSVT_ORHG` (Texture, 5.6 MB, levels A30, PWR no)
- `/Game/Megascans/Surfaces/Ground_Gravel_uconcitg/T_Ground_Gravel_uconcitg_sbs_NSVT_ORHG` (Texture, 5.6 MB, levels B40,C45, PWR no)

- **Where:** Gravel road beds (the landscape SandB surface), the distant apron ring (M_PWR_AlpineRidges GrassD/GrassN) and the site-finish rock surfaces (M_CE_PWRRock RockD/RockN with Tundra).
- **Why it reads as shipped:** PWR samples only D and N for these three sets. The packed AO/roughness/height map gives contact shadow, wet/dry roughness and the height that height-blending and Nanite displacement need. Same NSVT format PWR already reads.
- **Cost and risk:** About 17 MB of textures, no meshes, no foliage. There is no O slot for SandB in pwr.level.json's surfaces block, and probably none on AlpineRidges or PWRRock, so PWR's own masters need a texture slot first (a material change, then data). The grass file is spelled _OHRG, so check its channel order. Low-medium.

### 8. River cobbles and their LandscapeGrassType
*Category 1 (River bed, banks and cascade).*

- `/Game/Env/Bio/Rock/River/Rock_River_Stone_01/LG_Rock_River_Stone_01` (LandscapeGrassType, 1KB, levels B40,C45, PWR no)
- `/Game/Env/Bio/Rock/River/Rock_River_Stone_01/SM_Rock_River_Stone_01_C` (StaticMesh, 1,586 verts, 0.4x0.2x0.1 m, 0.2 MB, levels B40,C45, PWR no)
- `/Game/Env/Bio/Rock/River/Rock_River_Stone_01/SM_Rock_River_Stone_01_E` (StaticMesh, 801 verts, 0.3x0.2x0.1 m, 0.2 MB, levels B40,C45, PWR no)
- `/Game/Env/Bio/Rock/River/Rock_River_Stone_01/MIP_Rock_River_Stone_01` (MaterialInstance, 0.1 MB, levels B40,C45, PWR no)

- **Where:** Gravel bars, the riverbed under clear water, cascade pools.
- **Why it reads as shipped:** B40/C45 scatter these 0.2-0.4 m cobbles (279-1586 verts) through LG_Rock_River_Stone_01 on a landscape layer. PWR has a cobble texture (T_PWR_RiverCobble_BC/N) but no cobble geometry, and real stones are what make a riverbed read up close.
- **Cost and risk:** Instances, but tiny and shadowless; keep them inside the riverbed mask. Low-medium (adds to the instance budget).

### 9. C20 snowy mountain backdrop
*Category 5 (Mountains, cliffs and sky).*

- `/Game/Levels/Halo1/Solo/C20/Landscape/Vista/SM_SnowyMountain_Vista_01` (StaticMesh, 237,839 verts, 499.9x499.9x147.6 m, 7.8 MB, levels C20, PWR no)
- `/Game/Levels/Halo1/Solo/C20/Landscape/Vista/MIP_SnowyMountain_Vista` (MaterialInstance, 0.2 MB, levels C20, PWR no)

- **Where:** Mid-distance peaks in front of PWR's render-only mountain ring.
- **Why it reads as shipped:** The only snowy vista mesh that shipped (500 x 500 x 148 m, 238k verts). It adds a sculpted layer between the play space and the ring.
- **Cost and risk:** One 7.7 MB render-only mesh. Low risk; check the MI's tint against PWR's haze.

### 10. Waterfall mist, rainbow and wet-rock drips
*Category 1 (River bed, banks and cascade).*

- `/Game/FX/Library/Environment/PNW/Liquids/LargeWaterfall/NS_PNW_Waterfall_Mist_Lrg` (NiagaraSystem, 46KB, levels A30, PWR no)
- `/Game/FX/Library/Environment/PNW/Liquids/LargeWaterfall/WaterMistRainbow/NS_WaterMistRainbow` (NiagaraSystem, 28KB, levels A30, PWR no)
- `/Game/FX/Library/Environment/PNW/Liquids/WaterDrips/NS_Liquid_WaterDripping_01` (NiagaraSystem, 70KB, levels C10, PWR no)

- **Where:** Cascade plunge pool and wet cliff faces beside it.
- **Why it reads as shipped:** A30 shipped these at its waterfall; PWR uses only the splash and river-splash systems.
- **Cost and risk:** Data-only Niagara through the existing waterfalls[].effects. Low risk; watch translucent overdraw.

### 11. Valley and lake fog, cold mist in the bases
*Category 7 (Atmosphere, life, light and sound).*

- `/Game/FX/Library/Environment/PNW/Atmospherics/Fog/NS_PNW_FogAmbient_01` (NiagaraSystem, 24KB, levels B40,C20,C45,D20, PWR no)
- `/Game/FX/Library/Environment/Forerunner/Atmospherics/Fog/NS_For_ColdFogVapor` (NiagaraSystem, 41KB, levels A30,B40,C45, PWR no)
- `/Game/FX/Library/Environment/Forerunner/Atmospherics/Fog/NS_For_MistGround_01` (NiagaraSystem, 42KB, levels B30,B40,C45, PWR no)

- **Where:** Lake surfaces and river bends; floors of the three Forerunner bases.
- **Why it reads as shipped:** Shipped ambient fog (B40, C20, D20) plus Forerunner cold vapour and ground mist (A30, B30, B40). It layers depth that height fog alone cannot.
- **Cost and risk:** Data-only Niagara placed through effects.placed. Low risk; watch overdraw near spawns.

### 12. Light cones as canopy shafts and base-interior beams
*Category 7 (Atmosphere, life, light and sound).*

- `/Game/Lighting/LightCone_v2/Meshes/SM_LightCone_Plane_1x` (StaticMesh, 4 verts, 1.0x1.0x0.0 m, 3KB, levels A15,A30,A50,B30,B40,C10,C20,C45,D20,D40,E10,E20,E30, PWR no)
- `/Game/Lighting/LightCone_v2/Materials/MI_LightCone_Animated_Fading_Facing_Fogging` (MaterialInstance, 1KB, levels A15,A30,A50,B30,B40,C10,C20,C45,D20,D40,E10,E20,E30, PWR no)
- `/Game/Lighting/LightCone_v2/BP_LightCone` (Blueprint, 15KB, levels A15,A30,A50,B30,B40,C10,C20,C45,D20,D40,E10,E20,E30, PWR no)

- **Where:** Gaps in the pine canopy, Forerunner base interiors and doorways.
- **Why it reads as shipped:** The light-cone system all 13 levels use. It is material-only, so it gives a volumetric look without volumetric cost.
- **Cost and risk:** The MI has no parameter overrides; BPC_LightCone sets colour, intensity and fading at BeginPlay (RefreshMaterial). As decor, bake per-use MIs with `mjolnir ue clone` (data, no per-frame code); the BP route needs loader support. Low-medium.

### 13. Conifer deadfall on the forest floor
*Category 4 (Forests).*

- `/Game/Megascans/3D_Assets/FallenSpruceTree/SM_FallenSpruceTree_01` (StaticMesh, 21,617 verts, 7.3x1.9x0.9 m, 0.8 MB, levels C10, PWR no)
- `/Game/Megascans/3D_Assets/Large_Fallen_Tree_wd3hfidbw/S_Large_Fallen_Tree_wd3hfidbw_lod0_Var1` (StaticMesh, 10,833 verts, 9.4x1.3x1.1 m, 0.4 MB, levels A30, PWR no)
- `/Game/Megascans/3D_Assets/OldFallenTree/SM_OldFallenTree_01` (StaticMesh, 118,623 verts, 2.3x0.7x0.4 m, 3.9 MB, levels C10, PWR no)
- `/Game/Megascans/3D_Assets/Fallen_Tree_Log_xiclcfl/S_Fallen_Tree_Log_xiclcfl_lod0_Var1` (StaticMesh, 4,494 verts, 2.3x0.6x0.8 m, 0.2 MB, levels A30, PWR no)

- **Where:** Inside the pine stands and at road cuts.
- **Why it reads as shipped:** A fallen spruce (7.3 m) and a 9.4 m windthrow trunk fit a conifer forest better than the birch/oak logs. A30/C10 use these.
- **Cost and risk:** Decor (10-125k verts), no foliage. Low risk; author collision if logs sit on paths.

### 14. Lake-shore rock set and the shoreline surface
*Category 2 (Lakes and shores).*

- `/Game/Environments/PNW/Assets/Nordic_Beach_Rocks_A/SM_Nordic_Beach_Rocks_A` (StaticMesh, 43,447 verts, 5.1x2.6x1.4 m, 1.6 MB, levels A30, PWR no)
- `/Game/Environments/PNW/Assets/Nordic_Beach_Rocks_B/SM_Nordic_Beach_Rocks_B` (StaticMesh, 62,943 verts, 2.2x1.9x0.8 m, 2.1 MB, levels A30, PWR no)
- `/Game/Environments/PNW/Assets/Nordic_Beach_Rocks_C/SM_Nordic_Beach_Rocks_C` (StaticMesh, 67,010 verts, 6.2x3.6x2.5 m, 2.3 MB, levels A30, PWR no)
- `/Game/Megascans/3D_Assets/Nordic_Beach_Rock_Formation_vd4iahpga/S_Nordic_Beach_Rock_Formation_vd4iahpga_high_Var1` (StaticMesh, 516,629 verts, 7.7x4.7x1.1 m, 15.5 MB, levels B40,C45, PWR no)
- `/Game/Megascans/Surfaces/Shoreline_Beach_Rocks_ullmagidy/T_Shoreline_Beach_Rocks_ullmagidy_NSVT_D` (Texture, 2.8 MB, levels B30,B40,C45, PWR no)

- **Where:** Both lake shores and the reservoir edge.
- **Why it reads as shipped:** Cold-water Nordic shore rocks (A30, B40) and the shoreline-rocks surface B30/B40 paint at the waterline. They give a shore band instead of grass meeting water.
- **Cost and risk:** Decor plus one texture set. Low risk; the 517k-vert formation should be Nanite.

### 15. Meadow erratics from the PNW boulder set
*Category 6 (Open meadow ground and landscape materials).*

- `/Game/Environments/PNW/Assets/Tundra_Boulder_A/SM_Tundra_Boulder_A` (StaticMesh, 75,792 verts, 2.2x1.4x0.9 m, 2.5 MB, levels A30, PWR no)
- `/Game/Environments/PNW/Assets/Nordic_Boulder_A/SM_Nordic_Boulder_A` (StaticMesh, 124,610 verts, 6.6x8.9x4.1 m, 4.2 MB, levels A30, PWR no)
- `/Game/Environments/PNW/Assets/Mossy_Boulder_A/SM_Mossy_Boulder_A` (StaticMesh, 71,977 verts, 3.2x3.0x2.2 m, 2.0 MB, levels A30, PWR no)
- `/Game/Environments/PNW/Assets/Large_Rock_Shelf_A/SM_Large_Rock_Shelf_A` (StaticMesh, 40,855 verts, 2.6x3.2x1.7 m, 1.3 MB, levels A30, PWR no)

- **Where:** Scattered on the open meadow and along the road verges.
- **Why it reads as shipped:** A small curated set with layered MIs that A30 uses in its boulder assemblies. It breaks up the meadow at the 2-3 m scale between grass and glacial rocks.
- **Cost and risk:** Decor, 40-76k verts each. Low risk.

### 16. Dragonflies over the reeds
*Category 7 (Atmosphere, life, light and sound).*

- `/Game/FX/Library/Environment/PNW/Creatures/Insects/Dragonfly/NS_Creature_Dragonflies_01` (NiagaraSystem, 43KB, levels A30,A50,B30,C10,E30, PWR no)

- **Where:** Reed beds on both lakes and slow river reaches.
- **Why it reads as shipped:** Used in five levels (A30, A50, B30, C10, E30); small motion at the water's edge makes the scene feel alive.
- **Cost and risk:** Data-only Niagara. Very low risk.

### 17. Falling pine needles in the stands
*Category 4 (Forests).*

- `/Game/FX/Library/Environment/PNW/Plants/Trees/PineNeedles/NS_Trees_PineNeedles_Falling` (NiagaraSystem, 50KB, levels A30, PWR no)

- **Where:** Under the mature pines.
- **Why it reads as shipped:** A30's forest uses it; motion in the canopy light.
- **Cost and risk:** Data-only Niagara. Very low risk.

### 18. Snow gusts off the ridges
*Category 7 (Atmosphere, life, light and sound).*

- `/Game/FX/Library/Environment/PNW/Atmospherics/Snow/NS_PNW_SnowGusts_01` (NiagaraSystem, 0.1 MB, levels B40,C45, PWR no)

- **Where:** Ridge crests and the snowfield edges visible from the valley.
- **Why it reads as shipped:** B40/C45 shipped it; it animates the static snow peaks.
- **Cost and risk:** Data-only Niagara. Low risk (keep it on the ring side of the play space).

### 19. Forerunner exterior kit pieces for bases and bridges
*Category 8 (Structures, wreckage and other set dressing).*

- `/Game/Env/HS/FR/HAL/Ext_Bridge_A_Crash_Site/FR_HAL_Ext_Bridge_Crashsite_Abutment_Side_w39_d5_h8_A/SM_FR_HAL_Ext_Bridge_Crashsite_Abutment_Side_w39_d5_h8_A` (StaticMesh, 246,132 verts, 39.4x5.1x7.4 m, 7.8 MB, levels A30, PWR no)
- `/Game/Env/HS/FR/SIL/Ext_Terminals_A/FR_SIL_Ext_Terminal_A_Beach_FrontPillar_w24_d11_h31i25_A/SM_FR_SIL_Ext_Terminal_A_Beach_FrontPillar_w24_d11_h31i25_A` (StaticMesh, 128,789 verts, 22.4x8.4x38.3 m, 4.2 MB, levels B30, PWR no)
- `/Game/Env/HS/FR/ACR/Cave_B_Tarmac/FR_ACR_Ext_Cave_B_Tarmac_Pillar_w10_d14_h20i5_A/SM_FR_ACR_Ext_Cave_B_Tarmac_Pillar_w10_d14_h20i5_A` (StaticMesh, 90,747 verts, 6.5x12.0x26.8 m, 3.9 MB, levels B40,C45, PWR no)

- **Where:** Bridge abutments, base pylons, ridgeline ruins.
- **Why it reads as shipped:** Shipped exterior Forerunner architecture: A30's crash-site bridge abutments and cladding, B30's beach terminals, B40's tarmac pillars. They match PWR's ACR bridge kit.
- **Cost and risk:** Nanite decor; render-only, so author Blam collision for anything walkable. Medium (collision work).

### 20. Re-skin the bases with the shipped Forerunner metal family
*Category 8 (Structures, wreckage and other set dressing).*

- `/HaloMaterialLibrary/Env/Material/HS/FR/MI_FR_Metal_Diagonal_01_B_Mid_Rough2_Mid` (MaterialInstance, 1KB, levels A30,B30,B40,C10,C20,C45, PWR no)
- `/HaloMaterialLibrary/Env/Material/HS/FR/MI_FR_Metal_Diagonal_01_C_Dark_Line_Rough0_Lowest_VCol_HeavyGrime` (MaterialInstance, 0.3 MB, levels A30,B30, PWR no)

- **Where:** Base and bridge surfaces where PWR uses its own materials.
- **Why it reads as shipped:** These are the material instances shipped FR kits use: light/mid/dark, roughness tiers, vertex-colour grime and frost. PWR rebuilt its own FR diagonal textures (T_PWR_FRDiagonal_N/ORHG, T_FR_Diagonal_ORHG) for M_FR_BridgeDeck/Trim; the shipped instances add the grime and wear tiers.
- **Cost and risk:** Material overrides in level data. Low risk (shipped MI on shipped meshes).

### 21. Dead snags at the treeline
*Category 4 (Forests).*

- `/Game/Levels/Halo1/Solo/A30/PCG/Assemblies/PineTree/LI_Tree_Windswept_Dead` (LevelInstance, 20KB, levels A30, PWR no)
- `/Game/Env/Bio/Tree/Pine/Tree_Windswept_Dead/Meshes/SM_Tree_Windswept_Dead_Big_108` (StaticMesh, 5,815 verts, 9.7x11.7x21.8 m, 0.2 MB, levels A30, PWR no)
- `/Game/Env/Bio/Tree/DouglasFir/Tree_DouglasFir_SnowDead_A/Meshes/SM_Tree_DouglasFir_SnowDead_A_Trunk_Tube` (StaticMesh, 137,126 verts, 4.4x4.9x30.6 m, 5.3 MB, levels B40,C45, PWR no)

- **Where:** The upper forest edge and avalanche paths below the snow.
- **Why it reads as shipped:** Windswept dead pines (A30) and snow-laden dead Douglas firs (B40) give the treeline a ragged, weathered edge. They complement PWR's own SM_PWR_SweepDeadPine.
- **Cost and risk:** Multi-part trees (read the A30 assembly for parts); few instances. Medium (part assembly).

### 22. Mossy forest-floor kit
*Category 4 (Forests).*

- `/Game/Env/Bio/Moss/Lumpy/Moss_Lumpy_Lrg_A/SM_Moss_Lumpy_Lrg_A` (StaticMesh, 67,657 verts, 2.6x2.5x1.3 m, 2.9 MB, levels C10, PWR no)
- `/Game/Megascans/3D_Assets/Mossy_Forest_Roots_wgxodhsaw/S_Mossy_Forest_Roots_wgxodhsaw_high_Var1` (StaticMesh, 239,628 verts, 4.6x2.6x0.4 m, 7.9 MB, levels E20, PWR no)
- `/Game/Megascans/3D_Assets/MossyForestBoulder/SM_MossyForestBoulder_04` (StaticMesh, 26,334 verts, 3.2x3.1x2.0 m, 1.2 MB, levels C10, PWR no)
- `/Game/Env/Bio/Mushroom/TurkeyTail/Mushroom_TurkeyTail_Sml_A/SM_Mushroom_TurkeyTail_Sml_A` (StaticMesh, 7,774 verts, 0.3x0.2x0.1 m, 0.4 MB, levels C10, PWR no)
- `/Game/Env/Bio/Fungus/Lichen/Fungus_Lichen_Parasitism_A/SM_Fungus_Lichen_Parasitism_A` (StaticMesh, 75,103 verts, 0.8x0.8x0.2 m, 4.1 MB, levels C10, PWR no)

- **Where:** Shaded forest floor, stumps and logs, root plates on cut banks.
- **Why it reads as shipped:** Moss mounds, exposed roots, shelf fungus and lichen (C10, E20) add the small-scale wet-forest detail.
- **Cost and risk:** Small decor; dense meshes (60-240k verts) need Nanite. Low risk.

### 23. Wet variants and mud at the fords
*Category 1 (River bed, banks and cascade).*

- `/Game/Env/Bio/bank/Riparian/Bank_Riparian_Slopes_Lrg_A/Materials/MI_Bank_Riparian_Slopes_Lrg_A_Wet` (MaterialInstance, 88KB, levels C10, PWR no)
- `/Game/Megascans/Surfaces/Soil_Mud_rm4k21p0/T_Soil_Mud_rm4k21p0_ORHG` (Texture, 6.4 MB, levels A30,B40,C10,C45,D40,E20, PWR no)
- `/Game/Env/Bio/Fungus/Lichen/Materials/MI_Layer_Fungus_Lichen_Parasitism_01_Wet` (MaterialInstance, 79KB, levels C10, PWR no)
- `/HaloMaterialLibrary/MaterialFunctions/MF_Wetness_Albedo_Darkening` (MaterialFunction, 0KB, levels A15,A30,A50,B30,B40,C10,C20,C45,D20,D40,E10,E20,E30, PWR no)

- **Where:** Water line of banks, rocks and logs near the river; vehicle fords.
- **Why it reads as shipped:** Shipped _Wet MIs exist for the bank kit, lichen and turkey tail, plus mud textures. A darkened, glossy band at the waterline is a classic shipped-quality cue.
- **Cost and risk:** Material choices only. Low risk.

### 24. River audio: Fluid Flux river loop now, A30 river/waterfall events later
*Category 7 (Atmosphere, life, light and sound).*

- `/Game/FluidFlux/Surface/Templates/River/Audio/SW_RiverAmbient` (SoundWave, 0.4 MB, levels C10, PWR no)
- `/Game/Audio/Audio_FI/Ambience/A30/Positionals/Exterior/water/WwiseEvents/Play_AMB_ENV_A30_Ext_RiverFast` (WwiseEvent, 3KB, levels A30, PWR no)
- `/Game/Audio/Audio_FI/Ambience/A30/Positionals/Exterior/water/WwiseEvents/Play_AMB_ENV_A30_River_Rapids_LP` (WwiseEvent, 1KB, levels A30, PWR no)
- `/Game/Audio/Audio_FI/Ambience/A30/Positionals/Exterior/water/WwiseEvents/Play_AMB_ENV_A30_Waterfall_Splashes_LP` (WwiseEvent, 1KB, levels A30, PWR no)

- **Where:** River emitters, rapids and the cascade.
- **Why it reads as shipped:** SW_RiverAmbient is a plain SoundWave, the same route PWR's own SW_PWR_Stream emitters use. A30's Wwise positionals cover calm, fast, rapids and waterfall.
- **Cost and risk:** SoundWave: data-only now. Wwise events: integration from level data unverified. Low then medium.

### 25. Collision-backed wreckage and crates (simulation objects)
*Category 8 (Structures, wreckage and other set dressing).*

- `/Game/Tags/objects/levels/halo1/solo/e30/e30_wreckage_big_pipe/e30_wreckage_big_pipe-crate` (BlamTag:crate, 12KB, PWR no)
- `/Game/Tags/objects/levels/halo1/solo/e30/e30_wreckage_girder_support/e30_wreckage_girder_support-crate` (BlamTag:crate, 12KB, PWR no)
- `/Game/Tags/objects/levels/halo1/solo/e30/e30_wreckage_ship_structure/e30_wreckage_ship_structure-crate` (BlamTag:crate, 12KB, PWR no)
- `/Game/Tags/objects/props/UNSC/unsc_gen_prop_crate_a/unsc_gen_prop_crate_a-crate` (BlamTag:crate, 12KB, PWR no)

- **Where:** Cover near contested zones, supply dumps at the LZs.
- **Why it reads as shipped:** Engine-first: crate tags collide and sync with no code, and the e30 wreckage pieces match the UNSC/MAW/Wreckage meshes.
- **Cost and risk:** Placed as Blam objects in the scenario. Low risk; check e30 tag dependencies resolve outside E30.

### 26. A crash site: torn lifepod, debris and smoke
*Category 8 (Structures, wreckage and other set dressing).*

- `/Game/Levels/Halo1/Solo/A30/Vehicle/Lifepod/A30_LifePod_Damaged/SM_A30_Lifepod_Destroyed` (StaticMesh, 411,164 verts, 9.2x13.4x7.0 m, 20.4 MB, levels A30, PWR no)
- `/Game/Levels/Halo1/Solo/A30/Vehicle/Lifepod/A30_LifePod_Damaged/SM_A30_Lifepod_Debris_02` (StaticMesh, 15,933 verts, 4.8x4.5x1.5 m, 0.7 MB, levels A30, PWR no)
- `/Game/Levels/Halo1/Solo/A30/Landscape/Crash_Site_Mound/Mesh/SM_A30_Crash_Site_Mound` (StaticMesh, 84,209 verts, 3.1x2.9x0.8 m, 2.2 MB, levels A30, PWR no)
- `/Game/Env/HS/UNSC/Vehicles/pelican/Damaged/SM_Pelican_Body_Damaged` (StaticMesh, 1,198,261 verts, 30.0x9.6x20.9 m, 67.1 MB, levels B40,C10,C45,D40, PWR no)
- `/Game/FX/Library/Environment/PNW/Destruction/Smoke/SmokeColumns/NS_PNW_SmokeColumn_Lrg_04_Wind` (NiagaraSystem, 0.1 MB, levels D40, PWR no)

- **Where:** One set piece on the meadow or a far slope.
- **Why it reads as shipped:** A30's own crash site (destroyed pod, 21 debris pieces, scorched mud mound) or a wrecked Pelican, with D40's wind-bent smoke column. It is narrative dressing in the Halo idiom.
- **Cost and risk:** Dense: the pod is 411k verts, the Pelican body 1.2M verts, so confirm Nanite. Needs Blam collision. Medium.

### 27. Forerunner exterior light fixtures
*Category 7 (Atmosphere, life, light and sound).*

- `/Game/Env/HS/FR/Gen/Lights/FR_GEN_Light_Fixture_Tall_a/SM_FR_GEN_Light_Fixture_Tall_a` (StaticMesh, 9,823 verts, 0.0x0.2x0.9 m, 0.3 MB, levels A30,B30,B40,C20,C45, PWR no)
- `/Game/Env/HS/FR/Gen/Lights/FR_GEN_Light_Fixture_Panel_a/SM_FR_GEN_Light_Fixture_Panel_a` (StaticMesh, 8,750 verts, 3.6x0.2x0.0 m, 0.3 MB, levels A30,B30,B40,C10,C20,C45, PWR no)
- `/Game/Lighting/LightFixture_BPs/Forerunner/B40/BP_LightFixture_FR_Tall_A_LightBlue_Ext` (Blueprint, 3KB, levels B40,C45, PWR no)

- **Where:** Base walls, bridge decks and landing pads.
- **Why it reads as shipped:** The fixtures B40 lights its exteriors with; PWR's 37 lights are generic interior_light points, plus its own M_FR_BridgeLight.
- **Cost and risk:** Mesh as decor plus level.json lights[] (the BP carries UE lights the loader may not spawn). Low-medium.

### 28. Alpine flowers and moor grass (sparingly)
*Category 6 (Open meadow ground and landscape materials).*

- `/Game/Env/Bio/Plants/AlpinePrimrose/SM_Plant_AlpinePrimrose_Kit_A` (StaticMesh, 29,118 verts, 1.4x0.7x0.5 m, 5.9 MB, levels E30, PWR no)
- `/Game/Env/Bio/Plants/AlpinePrimrose/SM_Plant_AlpinePrimrose_Kit_C` (StaticMesh, 1,598 verts, 0.3x0.3x0.1 m, 0.3 MB, levels E30, PWR no)
- `/Game/Megascans/3D_Plants/Clovers_rbdjz/SM_Clovers_rbdjz_01` (StaticMesh, 684 verts, 0.8x0.6x0.1 m, 87KB, levels A30, PWR no)
- `/Game/Env/Bio/Grass/AutumnMoor/SM_Grass_AutumnMoor` (StaticMesh, 19,994 verts, 1.1x1.0x1.2 m, 3.1 MB, levels A30, PWR no)

- **Where:** Rock crevices, the alpine meadow above the forest, verges.
- **Why it reads as shipped:** AlpinePrimrose (E30) is the only true alpine flower that shipped; clovers and moor grass come from A30.
- **Cost and risk:** Foliage. Foliage is already about 18% of the GPU frame, so add these by replacing existing kinds, not on top. Medium.

### 29. Fluid Flux river surface template
*Category 1 (River bed, banks and cascade).*

- `/Game/FluidFlux/Surface/Templates/River/BP_FluxSurface_River` (Blueprint, 5KB, levels A30, PWR no)
- `/Game/FluidFlux/Surface/Templates/River/Materials/MI_RiverSurfaceOver` (MaterialInstance, 34KB, levels A30, PWR no)
- `/Game/FluidFlux/Surface/Templates/River/Materials/MI_RiverSection` (MaterialInstance, 31KB, levels A30, PWR no)

- **Where:** The PWR river (it currently uses the Coastline template).
- **Why it reads as shipped:** A30's river material: flow-aligned detail waves and seafoam (T_Seafoam_03_NSH) suited to moving water.
- **Cost and risk:** Changes the flux surface binding; test against PWR's baked flux_state. The BP's import closure pulls in M_FluxCausticsDecal and MI_RiverCausticsWetDecal (deferred decals), which is the decal risk. Disable the caustics decal or test for the PSO fatal first. Medium-high.

### 30. Landscape deformation for vehicle tracks
*Category 3 (Roads and verges).*

- `/HaloLandscapeDeformations/Toolkit/BP_LandscapeDeformationManager` (Blueprint, 0.2 MB, levels B30,B40,C45,D40,E10, PWR no)
- `/HaloLandscapeDeformations/Resources/M_TrackExampleMat` (Material, 7KB, PWR no)
- `/Game/Landscape/Deformation/BP_LandscapeDeformationManager_Configured` (Blueprint, 2KB, levels B40,C45,D40, PWR no)

- **Where:** Dirt roads, snow and mud.
- **Why it reads as shipped:** No tire-mark decals or puddle assets shipped. This toolkit is the shipped way to get tracks, and PWR already binds its MPC_DeformationGlobals.
- **Cost and risk:** Runtime system (render targets, a manager BP). Confirm it runs without per-frame Lua. Medium-high.

## Surprises

- **A30 is a complete temperate river-valley biome, and PWR barely uses it.** Its landscape master (`MM_A30_Landscape`) has Riverbed, Scree, ForestGround, Grass, Dirt, Sand and BurntGround layers. It is built on Megascans sets PWR does not sample (Wild_Grass_and_Weeds, Stones_on_Soil, Gravel_ground used as scree, Beach_Sand_With_Pebbles, Soil_Clay, Gravel_Natural), with A30-tinted NSVT diffuse copies, hex texture bombing and a wetness pass. Its PCG folder holds ready-made level-instance recipes for river boulders, river log jams, scree, tree skirts, rushes and sedges.
- **A dedicated river-bank kit that PWR does not use.** `Env/Bio/bank/Riparian` holds five large eroded-bank modules (208-330k verts each) with dry and _Wet instances. Only C10 places them; they fit PWR's river better than anything it uses now.
- **Landscape-grass scatter for river stones already exists** (`LG_Rock_River_Stone_01`, `_Angular`; B40/C45). So do per-level decorator grass types in `Env/Bio/Decorators` (A50, B30).
- **PWR samples only D and N for three Megascans ground sets:** Ground_Grass on the distant apron, Tundra_mossy_ground on the site-finish rock and Ground_Gravel as the SandB road bed. Their ORHG maps ship alongside and are unused. PWR's meadow itself is shaded from CE detail textures and its own base map, not Megascans.
- **B40's snow landscape** blends seven Megascans snow and gravel sets with stochastic flakes and landscape deformation. PWR uses only Windswept_Snow and Rock_Jagged from that palette.
- **There is no green Douglas fir.** The DouglasFir family ships only as SnowDead (snow-laden dead firs). The only conifer families are Pine (Windswept, Windswept_Dead, Tree_Pine, Sapling) and DouglasFir_SnowDead.
- **No road furniture shipped.** A regex sweep found no sign, lamp-post, fence, bollard, traffic-cone, curb, puddle or tire-mark meshes anywhere. The only road-edge pieces are Forerunner barrier, rail and ramp parts from A30's beam-emitter refinery, all named `_TEMP_A`, plus UNSC barriers and barricades. The only road decals are Megascans debris and leakage, plus DirtyDecals soil stains. Vehicle tracks would come from the `/HaloLandscapeDeformations` toolkit.
- **Plain SoundWave river loop:** `FluidFlux/Surface/Templates/River/Audio/SW_RiverAmbient` (C10 plays it) is a SoundWave, not a Wwise event, so it works with PWR's existing emitter route. Separately, `Audio/Audio_FI/Ambience` holds about 2,700 ambience assets, including A30 river, rapids, waterfall, wind-gust, bird and insect positionals.
- **Collision-backed wreckage:** `e30_wreckage_big_pipe`, `girder_support` and `ship_structure` are crate tags (simulation objects) matching the `Env/HS/UNSC/MAW/Wreckage` meshes.
- **Damaged Pelican statics** (body 1.2M verts, wings, engines, doors, gear) and destroyed Scorpion and Warthog bodies ship under `Env/HS/UNSC/Vehicles`.
- **Only one snowy vista mesh shipped:** C20 `SM_SnowyMountain_Vista_01`. The other vistas are desert, canyon or Maw.
- **Light cones are everywhere:** `BP_LightCone` (LightCone_v2) is imported by all 13 levels.

## What could not be inspected

- **Wwise audio content.** Only event names (AkAudioEvent and HaloAudioSound packages) were catalogued. The audio itself sits in the legacy `.pak` files (pakchunk0-13, about 6 GB), and those were not opened. Whether a Wwise event can be triggered from PWR level data is unverified.
- **Material parameter values.** `ue get` was run on `MI_A30_Landscape`, the glacial rock instances (snow and _NoSnow) and the LightCone MI. For the rest, textures come from header import lists, and `parent_inferred` is the first material-like import, not a parameter dump. The material functions with no imports are listed in `catalog.json` `not_inspected`; their internals were not read. These include the 0K `MF_LL_*` landscape-layer stubs and the Megascans `MF_LL_*` functions.
- **Static meshes with no vertex counts or bounds** (exact paths in `catalog.json` under `not_inspected`). These are mostly `PLAY_SM_*_CollisionMesh` collision proxies, plus four Megascans raw meshes without an SM_/S_ prefix (`huge_snow_hill_vdspdazqa_high`, `snow_hill_vdbmabvva_high1`, `limestone_rubble_ubxbejwda_raw1`, `nordic_beach_rock_formation_vckqccbga_raw1`). `mesh list` did not report them, and `ue get` shows a small StaticMesh export, so they may lack render data.
- **Nanite flags.** The tools do not report whether a mesh is Nanite. Meshes over 400k verts are flagged "confirm Nanite".
- **Level-instance contents.** Member meshes come from the generated cell packages' imports, not from instance transforms. Transforms would have to be read to copy a layout exactly.
- **Texture formats and dimensions.** `texture list --detail` was not run across the set. Sizes are cooked bytes only.
- **Visual check.** No asset was rendered for this catalogue. Tints, scale notes and fit are inferred from names, imports, bounds and which levels use them. Snow on the glacial instances is confirmed only by `ue get` (they stream the snow textures).
- **Out of scope:** /Engine/Content, MetaHumans, characters, weapons, vehicles (apart from the static wrecks), UI and L10N. Category 8 has no Covenant set dressing because the setting is Forerunner and UNSC.

## Full catalogue

Columns: path | kind | size (MB) | verts | bounds (m) | shipped levels that use it | PWR | note. Textures are listed after each group's table. `risk` flags are in brackets.

## 1. River bed, banks and cascade (255)

### Reeds and rushes (Env/Bio/Grass) (26)

*Where on PWR:* Water edge of both lakes and slow river reaches

| path | kind | MB | verts | bounds m | levels | PWR | note |
|---|---|---|---|---|---|---|---|
| `/Game/Env/Bio/Grass/AcorusCalamus/Grass_AcorusCalamus_Short_A/Foliage/FT_Grass_AcorusCalamus_Short_A_FoliageType` | FoliageType | 0.00 |  |  | C10 | no | [foliage] |
| `/Game/Env/Bio/Grass/AcorusCalamus/Grass_AcorusCalamus_Short_A/SM_Grass_AcorusCalamus_Short_A` | StaticMesh | 0.05 | 834 | 0.34x0.36x0.46 | C10 | no | [foliage] |
| `/Game/Env/Bio/Grass/AcorusCalamus/Grass_AcorusCalamus_Short_A/SM_Grass_AcorusCalamus_Short_A_Traced` | StaticMesh | 0.16 | 1,771 | 0.35x0.36x0.47 | C10 | no | [foliage] |
| `/Game/Env/Bio/Grass/AcorusCalamus/Grass_AcorusCalamus_Short_B/Foliage/FT_Grass_AcorusCalamus_Short_B_FoliageType` | FoliageType | 0.00 |  |  | C10 | no | [foliage] |
| `/Game/Env/Bio/Grass/AcorusCalamus/Grass_AcorusCalamus_Short_B/SM_Grass_AcorusCalamus_Short_B` | StaticMesh | 0.07 | 583 | 0.3x0.25x0.46 | C10 | no | [foliage] |
| `/Game/Env/Bio/Grass/AcorusCalamus/Grass_AcorusCalamus_Short_C/Foliage/FT_Grass_AcorusCalamus_Short_C_FoliageType` | FoliageType | 0.00 |  |  | C10 | no | [foliage] |
| `/Game/Env/Bio/Grass/AcorusCalamus/Grass_AcorusCalamus_Short_C/SM_Grass_AcorusCalamus_Short_C` | StaticMesh | 0.06 | 371 | 0.25x0.32x0.46 | C10 | no | [foliage] |
| `/Game/Env/Bio/Grass/AcorusCalamus/Materials/MI_Grass_AcorusCalamus_Short_A` | MaterialInstance | 0.03 |  |  | C10 | no | [foliage] |
| `/Game/Env/Bio/Grass/Rushes/Grass_Rushes_A/FT_grass_Rushes_A` | FoliageType | 0.00 |  |  | A30 | no | [foliage]; sibling used by PWR |
| `/Game/Env/Bio/Grass/Rushes/Grass_Rushes_A/SM_Grass_Rushes_A` | StaticMesh | 0.29 | 4,146 | 0.93x0.69x0.77 | A30,C10 | yes | [foliage] |
| `/Game/Env/Bio/Grass/Rushes/Grass_Rushes_B/FT_Grass_Rushes` | FoliageType | 0.00 |  |  | A30 | no | [foliage]; sibling used by PWR |
| `/Game/Env/Bio/Grass/Rushes/Grass_Rushes_B/SM_Grass_Rushes_B` | StaticMesh | 1.12 | 6,683 | 0.48x0.46x0.78 | A30 | yes | [foliage] |
| `/Game/Env/Bio/Grass/Rushes/Materials/MI_Grass_Rushes` | MaterialInstance | 0.03 |  |  | A30,C10 | no | [foliage] |
| `/Game/Env/Bio/Grass/Sedges/Grass_Sedges_A/MI_Grass_Sedges_A_Flowers_A` | MaterialInstance | 0.03 |  |  | A30 | no | [foliage]; sibling used by PWR |
| `/Game/Env/Bio/Grass/Sedges/Grass_Sedges_A/SM_Grass_Sedges_A_Flowers_A` | StaticMesh | 0.34 | 2,108 | 1.05x0.17x0.88 | A30 | no | [foliage]; sibling used by PWR |
| `/Game/Env/Bio/Grass/Sedges/Grass_Sedges_A/SM_Grass_Sedges_A_Flowers_C` | StaticMesh | 0.20 | 1,309 | 0.92x0.13x0.88 | A30 | no | [foliage]; sibling used by PWR |
| `/Game/Env/Bio/Grass/Sedges/Grass_Sedges_A/SM_Grass_Sedges_A_Flowers_E` | StaticMesh | 0.40 | 2,761 | 1.09x0.49x0.75 | A30 | no | [foliage]; sibling used by PWR |
| `/Game/Env/Bio/Grass/Sedges/Grass_Sedges_A/SM_Grass_Sedges_A_Leaves_A` | StaticMesh | 0.24 | 1,758 | 1.04x0.46x0.91 | A30 | yes | [foliage] |
| `/Game/Env/Bio/Grass/Sedges/Grass_Sedges_A/SM_Grass_Sedges_A_Leaves_B` | StaticMesh | 0.43 | 3,642 | 0.85x0.96x0.88 | A30 | no | [foliage]; sibling used by PWR |
| `/Game/Env/Bio/Grass/Sedges/Grass_Sedges_A/SM_Grass_Sedges_A_Leaves_C` | StaticMesh | 0.17 | 1,350 | 0.67x0.55x0.62 | A30 | yes | [foliage] |
| `/Game/Env/Bio/Grass/Sedges/Grass_Sedges_A/SM_Grass_Sedges_A_Leaves_D` | StaticMesh | 0.23 | 1,758 | 0.91x0.69x0.55 | A30 | no | [foliage]; sibling used by PWR |
| `/Game/Env/Bio/Grass/Sedges/Grass_Sedges_A/SM_Grass_Sedges_A_Leaves_E` | StaticMesh | 0.13 | 946 | 1.3x1.29x0.99 | A30 | no | [foliage]; sibling used by PWR |
| `/Game/Env/Bio/Grass/Sedges/Grass_Sedges_B/FT_Grass_Sedges_B` | FoliageType | 0.00 |  |  | A30 | no | [foliage] |
| `/Game/Env/Bio/Grass/Sedges/Grass_Sedges_B/MI_Grass_Sedges_B` | MaterialInstance | 0.03 |  |  | A30,C10 | no | [foliage] |
| `/Game/Env/Bio/Grass/Sedges/Grass_Sedges_B/SM_Grass_Sedges_B` | StaticMesh | 0.90 | 5,142 | 1.23x1.41x0.94 | A30,C10 | no | [foliage] |
| `/Game/Env/Bio/Grass/Sedges/Grass_Sedges_Clump_A/SM_SM_Grass_Sedges_Clump_A` | StaticMesh | 1.54 | 16,318 | 2.53x2.76x1.3 | A30 | no | [foliage] |

*Group note:* Sweet-flag (AcorusCalamus) reeds plus rushes and sedges; PWR already uses Rushes A/B and Sedges A leaves

### Lumpy moss (Env/Bio/Moss) (10)

*Where on PWR:* Wet rocks at the cascade, bank toes and shaded river boulders

| path | kind | MB | verts | bounds m | levels | PWR | note |
|---|---|---|---|---|---|---|---|
| `/Game/Env/Bio/Moss/Lumpy/Moss_Lumpy_Lrg_A/SM_Moss_Lumpy_Lrg_A` | StaticMesh | 2.92 | 67,657 | 2.61x2.47x1.33 | C10 | no |  |
| `/Game/Env/Bio/Moss/Lumpy/Moss_Lumpy_Lrg_B/SM_Moss_Lumpy_Lrg_B` | StaticMesh | 2.14 | 59,344 | 1.82x2.42x0.83 | C10 | no |  |
| `/Game/Env/Bio/Moss/Lumpy/Moss_Lumpy_Lrg_C/SM_Moss_Lumpy_Lrg_C` | StaticMesh | 4.29 | 80,939 | 2.25x2.35x0.97 | C10 | no |  |
| `/Game/Env/Bio/Moss/Lumpy/Moss_Lumpy_Sml_A/SM_Moss_Lumpy_Sml_A` | StaticMesh | 4.30 | 102,887 | 1.55x1.54x0.63 | C10 | no |  |
| `/Game/Env/Bio/Moss/Lumpy/Moss_Lumpy_Sml_B/SM_Moss_Lumpy_Sml_B` | StaticMesh | 3.62 | 76,492 | 1.02x0.89x0.44 | C10 | no |  |
| `/Game/Env/Bio/Moss/Lumpy/Moss_Lumpy_Sml_C/SM_Moss_Lumpy_Sml_C` | StaticMesh | 2.76 | 54,186 | 1.02x1.42x0.56 | C10 | no |  |
| `/Game/Env/Bio/Moss/Lumpy/Moss_Lumpy_Sml_D/SM_Moss_Lumpy_Sml_D` | StaticMesh | 3.54 | 78,605 | 1.14x1.13x0.55 | C10 | no |  |

Textures: `/Game/Env/Bio/Moss/Lumpy/Materials/T_Moss_Lumpy_Lrg_A_D` (0.9 MB), `/Game/Env/Bio/Moss/Lumpy/Materials/T_Moss_Lumpy_Lrg_A_N` (1.7 MB), `/Game/Env/Bio/Moss/Lumpy/Materials/T_Moss_Lumpy_Lrg_A_ORHG` (1.7 MB)

*Group note:* Lumpy moss clump meshes and MIs

### River stones (Env/Bio/Rock/River) (12)

*Where on PWR:* Riverbed gravel bars, cascade pools and the stream mouth; LandscapeGrassType scatters them on a landscape layer

| path | kind | MB | verts | bounds m | levels | PWR | note |
|---|---|---|---|---|---|---|---|
| `/Game/Env/Bio/Rock/River/Rock_River_Stone_01/LG_Rock_River_Stone_01` | LandscapeGrassType | 0.00 |  |  | B40,C45 | no |  |
| `/Game/Env/Bio/Rock/River/Rock_River_Stone_01/LG_Rock_River_Stone_01_Angular` | LandscapeGrassType | 0.00 |  |  | B40,C45 | no |  |
| `/Game/Env/Bio/Rock/River/Rock_River_Stone_01/MIP_Rock_River_Stone_01` | MaterialInstance | 0.13 |  |  | B40,C45 | no |  |
| `/Game/Env/Bio/Rock/River/Rock_River_Stone_01/SM_Rock_River_Stone_01_C` | StaticMesh | 0.18 | 1,586 | 0.37x0.24x0.1 | B40,C45 | no |  |
| `/Game/Env/Bio/Rock/River/Rock_River_Stone_01/SM_Rock_River_Stone_01_C_Snowy` | StaticMesh | 0.18 | 1,586 | 0.37x0.24x0.1 | B40,C45 | no | snow variant |
| `/Game/Env/Bio/Rock/River/Rock_River_Stone_01/SM_Rock_River_Stone_01_D_Snowy` | StaticMesh | 0.09 | 506 | 0.24x0.27x0.13 | B40,C45 | no | snow variant |
| `/Game/Env/Bio/Rock/River/Rock_River_Stone_01/SM_Rock_River_Stone_01_E` | StaticMesh | 0.16 | 801 | 0.27x0.16x0.09 | B40,C45 | no |  |
| `/Game/Env/Bio/Rock/River/Rock_River_Stone_01/SM_Rock_River_Stone_01_G` | StaticMesh | 0.09 | 440 | 0.26x0.16x0.11 | B40,C45 | no |  |
| `/Game/Env/Bio/Rock/River/Rock_River_Stone_01/SM_Rock_River_Stone_01_I` | StaticMesh | 0.06 | 279 | 0.22x0.21x0.2 | B40,C45 | no |  |

Textures: `/Game/Env/Bio/Rock/River/Rock_River_Stone_01/T_Rock_River_Stone_01_D` (3.2 MB), `/Game/Env/Bio/Rock/River/Rock_River_Stone_01/T_Rock_River_Stone_01_N` (6.4 MB), `/Game/Env/Bio/Rock/River/Rock_River_Stone_01/T_Rock_River_Stone_01_ORHG` (6.4 MB)

*Group note:* Small river cobbles (440-1586 verts) incl. Snowy variants and two LandscapeGrassTypes (LG_Rock_River_Stone_01, _Angular) that B40/C45 use to scatter stones procedurally

### Riparian bank kit (Env/Bio/bank/Riparian) (16)

*Where on PWR:* River banks and lake inlets: slope, cliff, square and trapezoid bank modules laid along the water line; _Wet MIs on the lower course

| path | kind | MB | verts | bounds m | levels | PWR | note |
|---|---|---|---|---|---|---|---|
| `/Game/Env/Bio/bank/Riparian/Bank_Riparian_Cliff_Lrg_A/SM_Bank_Riparian_Cliff_Lrg_A` | StaticMesh | 10.39 | 327,721 | 44.95x13.54x35.65 | C10 | no |  |
| `/Game/Env/Bio/bank/Riparian/Bank_Riparian_Slopes_Lrg_A/Materials/MI_Bank_Riparian_Slopes_Lrg_A` | MaterialInstance | 0.09 |  |  | C10 | no |  |
| `/Game/Env/Bio/bank/Riparian/Bank_Riparian_Slopes_Lrg_A/Materials/MI_Bank_Riparian_Slopes_Lrg_A_Wet` | MaterialInstance | 0.09 |  |  | C10 | no | wet variant |
| `/Game/Env/Bio/bank/Riparian/Bank_Riparian_Slopes_Lrg_A/SM_Bank_Riparian_Slopes_Lrg_A` | StaticMesh | 9.46 | 291,876 | 49.34x37.85x13.27 | C10 | no |  |
| `/Game/Env/Bio/bank/Riparian/Bank_Riparian_Square_Lrg_A/Materials/MI_Bank_Riparian_Square_Lrg_A` | MaterialInstance | 0.00 |  |  | C10 | no |  |
| `/Game/Env/Bio/bank/Riparian/Bank_Riparian_Square_Lrg_A/Materials/MI_Bank_Riparian_Square_Lrg_A_Wet` | MaterialInstance | 0.09 |  |  | C10 | no | wet variant |
| `/Game/Env/Bio/bank/Riparian/Bank_Riparian_Square_Lrg_A/SM_Bank_Riparian_Square_Lrg_A` | StaticMesh | 7.11 | 207,959 | 79.3x28.07x41.16 | C10 | no |  |
| `/Game/Env/Bio/bank/Riparian/Bank_Riparian_Trapezoidal_Lrg_A/Materials/MI_Bank_Riparian_Trapezoidal_Lrg_A` | MaterialInstance | 0.09 |  |  | C10 | no |  |
| `/Game/Env/Bio/bank/Riparian/Bank_Riparian_Trapezoidal_Lrg_A/Materials/MI_Bank_Riparian_Trapezoidal_Lrg_A_Wet` | MaterialInstance | 0.09 |  |  | C10 | no | wet variant |
| `/Game/Env/Bio/bank/Riparian/Bank_Riparian_Trapezoidal_Lrg_A/SM_Bank_Riparian_Trapezoidal_Lrg_A` | StaticMesh | 9.00 | 276,757 | 67.91x28.67x40.8 | C10 | no |  |
| `/Game/Env/Bio/bank/Riparian/Bank_Riparian_Trapezoidal_Lrg_B/Materials/MI_Bank_Riparian_Trapezoidal_Lrg_B` | MaterialInstance | 0.00 |  |  | C10 | no |  |
| `/Game/Env/Bio/bank/Riparian/Bank_Riparian_Trapezoidal_Lrg_B/Materials/MI_Bank_Riparian_Trapezoidal_Lrg_B_Wet` | MaterialInstance | 0.09 |  |  | C10 | no | wet variant |
| `/Game/Env/Bio/bank/Riparian/Bank_Riparian_Trapezoidal_Lrg_B/SM_Bank_Riparian_Trapezoidal_Lrg_B` | StaticMesh | 10.99 | 330,173 | 80.32x43.55x39.06 | C10 | no |  |
| `/Game/Env/Bio/bank/Riparian/Materials/MIP_Bank_Riparian` | MaterialInstance | 0.18 |  |  | C10 | no |  |
| `/Game/Env/Bio/bank/Riparian/Materials/MIP_Bank_Riparian_Wet` | MaterialInstance | 0.09 |  |  | C10 | no | wet variant |

Textures: `/Game/Env/Bio/bank/Riparian/Materials/T_Bank_Mask_01` (1.7 MB)

*Group note:* Purpose-built river-bank modules (6.7-10 MB Nanite meshes) with dry and _Wet material instances and a shared bank mask; only C10 places them

### Waterfall, spray and drip FX (PNW Liquids) (17)

*Where on PWR:* Cascade foot, rapids, waterfall face mist, wet rock drips

| path | kind | MB | verts | bounds m | levels | PWR | note |
|---|---|---|---|---|---|---|---|
| `/Game/FX/Library/Environment/PNW/Liquids/LargeWaterfall/BP_PNW_Liquid_Waterfall_DeformedMesh` | Blueprint | 0.07 |  |  | A30 | no | sibling used by PWR |
| `/Game/FX/Library/Environment/PNW/Liquids/LargeWaterfall/NS_PNW_WaterfallSplash_01` | NiagaraSystem | 0.04 |  |  | A30 | yes |  |
| `/Game/FX/Library/Environment/PNW/Liquids/LargeWaterfall/NS_PNW_WaterfallSplash_02` | NiagaraSystem | 0.05 |  |  | A30 | no | sibling used by PWR |
| `/Game/FX/Library/Environment/PNW/Liquids/LargeWaterfall/NS_PNW_WaterfallSplash_Lrg_01` | NiagaraSystem | 0.04 |  |  | A30 | no | sibling used by PWR |
| `/Game/FX/Library/Environment/PNW/Liquids/LargeWaterfall/NS_PNW_Waterfall_Mist_Lrg` | NiagaraSystem | 0.05 |  |  | A30 | no | sibling used by PWR |
| `/Game/FX/Library/Environment/PNW/Liquids/LargeWaterfall/NS_PNW_Waterfall_Rain` | NiagaraSystem | 0.03 |  |  | A30 | no | sibling used by PWR |
| `/Game/FX/Library/Environment/PNW/Liquids/LargeWaterfall/WaterMistRainbow/NS_WaterMistRainbow` | NiagaraSystem | 0.03 |  |  | A30 | no |  |
| `/Game/FX/Library/Environment/PNW/Liquids/Splashes/AmbientRiverSplash/NS_PNW_AmbientRiverSplash_01` | NiagaraSystem | 0.06 |  |  | A30 | yes |  |
| `/Game/FX/Library/Environment/PNW/Liquids/Splashes/Coastline/BP_SplashesCoastLine` | Blueprint | 0.00 |  |  | B30 | no |  |
| `/Game/FX/Library/Environment/PNW/Liquids/Splashes/Coastline/NS_SplashesCoastLine` | NiagaraSystem | 0.06 |  |  | B30 | no |  |
| `/Game/FX/Library/Environment/PNW/Liquids/Splashes/DistantWaveSplash/NS_PNW_DistantWaveSplash_01` | NiagaraSystem | 0.10 |  |  | B30 | no |  |
| `/Game/FX/Library/Environment/PNW/Liquids/Splashes/SmallWaveSplash/NS_PNW_SmallWaveSplash_01` | NiagaraSystem | 0.28 |  |  | B30 | no |  |
| `/Game/FX/Library/Environment/PNW/Liquids/Splashes/Vista/NS_Splashes_SeaStack_01` | NiagaraSystem | 0.07 |  |  | B30 | no |  |
| `/Game/FX/Library/Environment/PNW/Liquids/WaterDrips/NS_Liquid_WaterDripping_01` | NiagaraSystem | 0.07 |  |  | C10 | no |  |
| `/Game/FX/Library/Environment/PNW/Liquids/WaterDrips/NS_Liquid_WaterDripping_Lrg_01` | NiagaraSystem | 0.11 |  |  | C10,D40 | no |  |
| `/Game/FX/Library/Environment/PNW/Liquids/WaterDrips/NS_Liquid_WaterSplash_Lrg_01` | NiagaraSystem | 0.03 |  |  | C10 | no |  |
| `/Game/FX/Library/Environment/PNW/Liquids/WaterDrips/NS_PNW_RainSplash_WaterSurface_01` | NiagaraSystem | 0.03 |  |  | C10 | no |  |

*Group note:* Shipped Niagara systems; PWR uses NS_PNW_WaterfallSplash_01 and NS_PNW_AmbientRiverSplash_01 only

### Water foam textures (6)

*Where on PWR:* Foam for the cascade plunge pool and rapids (material texture inputs)


Textures: `/Game/FX/Textures/Liquids/WaterSplashFoam/T_WaterSplashFoam01_D` (2.8 MB), `/Game/FX/Textures/Liquids/WaterSplashFoam/T_WaterSplashFoam01_N` (0.7 MB), `/Game/FX/Textures/Liquids/WaterSplashFoam/T_WaterSplashFoam03Top_D` (5.6 MB), `/Game/FX/Textures/Liquids/WaterSplashFoam/T_WaterSplashFoam03Top_N` (1.4 MB), `/Game/FX/Textures/Liquids/Water_Foam/T_Water_Foam_D` (2.8 MB), `/Game/FX/Textures/Liquids/Water_Foam/T_Water_Foam_N` (0.4 MB)

*Group note:* FX texture sets

### FluidFlux river and lake surface templates (66)

*Where on PWR:* River and lake water surfaces, underwater fog and caustics

| path | kind | MB | verts | bounds m | levels | PWR | note |
|---|---|---|---|---|---|---|---|
| `/Game/FluidFlux/Interaction/Blueprints/BP_FluxInteractionCapture` | Blueprint | 0.02 |  |  | B30,C10,C20 | no |  |
| `/Game/FluidFlux/Interaction/Blueprints/BP_FluxInteractionComponent` | Blueprint | 0.03 |  |  | B30,C10,C20 | no |  |
| `/Game/FluidFlux/Interaction/Blueprints/BP_FluxSolverComponent` | Blueprint | 0.04 |  |  | B30,C10,C20 | no |  |
| `/Game/FluidFlux/Interaction/Blueprints/BP_FluxSolverRippleComponent` | Blueprint | 0.00 |  |  | B30,C10,C20 | no |  |
| `/Game/FluidFlux/Interaction/Blueprints/Interfaces/BPI_FluxInteraction` | Blueprint | 0.00 |  |  | B30,C10,C20 | no |  |
| `/Game/FluidFlux/Interaction/Blueprints/Interfaces/BPI_FluxInteractionRenderer` | Blueprint | 0.00 |  |  | A30,B30,C10,C20 | no |  |
| `/Game/FluidFlux/Interaction/Functions/MF_EncodeNormal` | MaterialFunction | 0.00 |  |  | A30,B30,C10,C20 | no |  |
| `/Game/FluidFlux/Interaction/Functions/MF_FluxDetailInteraction` | MaterialFunction | 0.00 |  |  | A30,B30,C10,C20 | no |  |
| `/Game/FluidFlux/Interaction/Functions/MF_FluxInteractionMask` | MaterialFunction | 0.00 |  |  | B30,C10,C20 | no |  |
| `/Game/FluidFlux/Interaction/Functions/MF_FluxInteractionUV` | MaterialFunction | 0.00 |  |  | A30,B30,C10,C20 | no |  |
| `/Game/FluidFlux/Interaction/Functions/MF_FluxInteractionUVToWorld` | MaterialFunction | 0.00 |  |  | B30,C10,C20 | no |  |
| `/Game/FluidFlux/Interaction/Functions/MF_FluxWorldToInteractionUV` | MaterialFunction | 0.00 |  |  | A30,B30,C10,C20 | no |  |
| `/Game/FluidFlux/Interaction/Functions/MF_PreviousState` | MaterialFunction | 0.00 |  |  | B30,C10,C20 | no |  |
| `/Game/FluidFlux/Interaction/Functions/MF_ReconstructNormal` | MaterialFunction | 0.00 |  |  | A30,B30,C10,C20 | no |  |
| `/Game/FluidFlux/Interaction/Functions/MF_TextureBorderFalloff` | MaterialFunction | 0.00 |  |  | A30,B30,C10,C20 | no |  |
| `/Game/FluidFlux/Interaction/Materials/MI_InteractionPreview` | MaterialInstance | 0.01 |  |  | B30,C10,C20 | no |  |
| `/Game/FluidFlux/Interaction/Materials/M_GenerateNormalMap` | Material | 0.01 |  |  | B30,C10,C20 | no |  |
| `/Game/FluidFlux/Interaction/Materials/M_InteractionPreview` | Material | 0.03 |  |  | B30,C10,C20 | no |  |
| `/Game/FluidFlux/Interaction/Materials/SolverRipple/MI_GenerateNormalMapRipple` | MaterialInstance | 0.01 |  |  | B30,C10,C20 | no |  |
| `/Game/FluidFlux/Interaction/Materials/SolverRipple/M_InteractionInputSphereRipple` | Material | 0.01 |  |  | B30,C10,C20 | no |  |
| `/Game/FluidFlux/Interaction/Materials/SolverRipple/M_InteractionSolverRipple` | Material | 0.02 |  |  | B30,C10,C20 | no |  |
| `/Game/FluidFlux/Interaction/Splash/Audio/SC_WaterSplash` | SoundCue | 0.00 |  |  | A30,C10 | no |  |
| `/Game/FluidFlux/Interaction/Splash/Audio/SW_WaterSplashTouch01` | SoundWave | 0.01 |  |  | A30,C10 | no |  |
| `/Game/FluidFlux/Interaction/Splash/Audio/SW_WaterSplashTouch02` | SoundWave | 0.01 |  |  | A30,C10 | no |  |
| `/Game/FluidFlux/Interaction/Splash/Audio/SW_WaterSplashTouch03` | SoundWave | 0.01 |  |  | A30,C10 | no |  |
| `/Game/FluidFlux/Interaction/Splash/Effects/NS_SimpleSplash` | NiagaraSystem | 0.05 |  |  | A30,C10 | no |  |
| `/Game/FluidFlux/Interaction/Splash/Materials/M_SplashDrop` | Material | 0.01 |  |  | A30,C10 | no |  |
| `/Game/FluidFlux/Interaction/Splash/Materials/M_SplashFlipbook` | Material | 0.02 |  |  | A30,C10 | no |  |
| `/Game/FluidFlux/Surface/Materials/M_FluxCausticsDecal` | Material | 0.04 |  |  | A30,B30,C10 | no | [decal] |
| `/Game/FluidFlux/Surface/Materials/Textures/VT_CausticsAnimation_01` | VolumeTexture | 0.60 |  |  | A30,B30,B40,C10,E20,E30 | no | virtual-texture copy |
| `/Game/FluidFlux/Surface/Materials/Textures/VT_CausticsAnimation_01_B40_02` | VolumeTexture | 0.60 |  |  | B40 | no | virtual-texture copy |
| `/Game/FluidFlux/Surface/Materials/Textures/VT_OceanWave` | VolumeTexture | 2.40 |  |  | A30,B30,C10,C20 | no | virtual-texture copy |
| `/Game/FluidFlux/Surface/Templates/Color/CP_OceanBlue_01` | DataAsset | 0.00 |  |  | B30 | yes |  |
| `/Game/FluidFlux/Surface/Templates/Color/CP_ShoreDirt_01` | DataAsset | 0.00 |  |  | B30 | no | sibling used by PWR |
| `/Game/FluidFlux/Surface/Templates/Color/CP_ShoreGreen_05` | DataAsset | 0.00 |  |  | B30 | no | sibling used by PWR |
| `/Game/FluidFlux/Surface/Templates/River/Audio/SW_RiverAmbient` | SoundWave | 0.38 |  |  | C10 | no |  |
| `/Game/FluidFlux/Surface/Templates/River/BP_FluxSurface_River` | Blueprint | 0.00 |  |  | A30 | no |  |
| `/Game/FluidFlux/Surface/Templates/River/BP_FluxSurface_River_2` | Blueprint | 0.00 |  |  |  | no |  |
| `/Game/FluidFlux/Surface/Templates/River/Materials/MI_RiverCausticsWetDecal` | MaterialInstance | 0.02 |  |  | A30 | no | [decal] |
| `/Game/FluidFlux/Surface/Templates/River/Materials/MI_RiverFogAbsorptionVolume` | MaterialInstance | 0.01 |  |  | A30 | no |  |
| `/Game/FluidFlux/Surface/Templates/River/Materials/MI_RiverFogScatteringVolume` | MaterialInstance | 0.01 |  |  | A30 | no |  |
| `/Game/FluidFlux/Surface/Templates/River/Materials/MI_RiverPostprocess` | MaterialInstance | 0.01 |  |  | A30 | no |  |
| `/Game/FluidFlux/Surface/Templates/River/Materials/MI_RiverSection` | MaterialInstance | 0.03 |  |  | A30 | no |  |
| `/Game/FluidFlux/Surface/Templates/River/Materials/MI_RiverSurfaceOver` | MaterialInstance | 0.03 |  |  | A30 | no |  |
| `/Game/FluidFlux/Surface/Templates/River/Materials/MI_RiverSurfaceOverStatic` | MaterialInstance | 0.03 |  |  | A30 | no |  |
| `/Game/FluidFlux/Surface/Templates/River/Materials/MI_RiverSurfaceOver_CrashSite` | MaterialInstance | 0.03 |  |  | A30 | no |  |
| `/Game/FluidFlux/Surface/Templates/River/Materials/MI_RiverSurfaceOver_CrashSite_2` | MaterialInstance | 0.03 |  |  | A30 | no |  |
| `/Game/FluidFlux/Surface/Templates/River/Materials/MI_RiverSurfaceUnder` | MaterialInstance | 0.03 |  |  |  | no |  |
| `/Game/FluidFlux/Surface/Templates/water/BP_FluxSurface_Water` | Blueprint | 0.01 |  |  | C10 | no |  |
| `/Game/FluidFlux/Surface/Templates/water/Materials/MI_WaterCausticsWetDecal` | MaterialInstance | 0.00 |  |  | C10 | no | [decal] |
| `/Game/FluidFlux/Surface/Templates/water/Materials/MI_WaterFogAbsorptionVolume` | MaterialInstance | 0.01 |  |  | C10 | no |  |
| `/Game/FluidFlux/Surface/Templates/water/Materials/MI_WaterFogPostProcess` | MaterialInstance | 0.01 |  |  | C10 | no |  |
| `/Game/FluidFlux/Surface/Templates/water/Materials/MI_WaterFogScatteringVolume` | MaterialInstance | 0.01 |  |  | C10 | no |  |
| `/Game/FluidFlux/Surface/Templates/water/Materials/MI_WaterOver` | MaterialInstance | 0.03 |  |  | C10 | no |  |
| `/Game/FluidFlux/Surface/Templates/water/Materials/MI_WaterSection` | MaterialInstance | 0.03 |  |  | C10 | no |  |
| `/Game/FluidFlux/Surface/Templates/water/Materials/MI_WaterUnder` | MaterialInstance | 0.03 |  |  | C10 | no |  |

Textures: `/Game/FluidFlux/Interaction/Splash/Materials/T_NewSplash_N` (0.7 MB), `/Game/FluidFlux/Interaction/Splash/Materials/T_SplashDrop` (0.0 MB), `/Game/FluidFlux/Interaction/Textures/T_DefaultBlack` (0.0 MB), `/Game/FluidFlux/Interaction/Textures/T_DefaultEncoded_N` (0.0 MB), `/Game/FluidFlux/Interaction/Textures/T_DefaultWhite` (0.0 MB), `/Game/FluidFlux/Surface/Materials/Textures/T_DetailWaveTexture_00` (0.3 MB), `/Game/FluidFlux/Surface/Materials/Textures/T_DetailWaveTexture_01` (1.4 MB), `/Game/FluidFlux/Surface/Materials/Textures/T_DetailWaveTexture_02` (1.4 MB), `/Game/FluidFlux/Surface/Materials/Textures/T_Seafoam_03_NSH` (5.6 MB), `/Game/FluidFlux/Surface/Materials/Textures/T_Turbulence` (0.0 MB)

*Group note:* The shipped Fluid Flux templates A30/C10 use; PWR already uses BP_FluxSurface_Coastline + CP_OceanBlue_01. River MIs include CrashSite variants (A30). Caustics are decal materials (see risk)

### A30 river assemblies (PCG level instances) (24)

*Where on PWR:* Recipe for river boulders, log jams, rushes and sedges along the PWR river

| path | kind | MB | verts | bounds m | levels | PWR | note |
|---|---|---|---|---|---|---|---|
| `/Game/Levels/Halo1/Solo/A30/PCG/Assemblies/Boulder/BP_BoulderAssembly_A` | Blueprint | 0.00 |  |  | A30 | no |  |
| `/Game/Levels/Halo1/Solo/A30/PCG/Assemblies/Boulder/BP_BoulderAssembly_HipHeight_A` | Blueprint | 0.00 |  |  | A30 | no |  |
| `/Game/Levels/Halo1/Solo/A30/PCG/Assemblies/Boulder/BP_BoulderB_Assembly_B` | Blueprint | 0.00 |  |  | A30 | no |  |
| `/Game/Levels/Halo1/Solo/A30/PCG/Assemblies/Boulder/BP_BoulderRiver_A` | Blueprint | 0.00 |  |  | A30 | no |  |
| `/Game/Levels/Halo1/Solo/A30/PCG/Assemblies/Boulder/DAPCG_BoulderCover_A` | PCGDataAsset | 0.05 |  |  | A30 | no |  |
| `/Game/Levels/Halo1/Solo/A30/PCG/Assemblies/Boulder/DAPCG_BoulderCover_B` | PCGDataAsset | 0.02 |  |  | A30 | no |  |
| `/Game/Levels/Halo1/Solo/A30/PCG/Assemblies/Boulder/DAPCG_BoulderHipHeight_A` | PCGDataAsset | 0.02 |  |  | A30 | no |  |
| `/Game/Levels/Halo1/Solo/A30/PCG/Assemblies/Boulder/DAPCG_BoulderRiver_A` | PCGDataAsset | 0.02 |  |  | A30 | no |  |
| `/Game/Levels/Halo1/Solo/A30/PCG/Assemblies/Boulder/LI_BoulderCover_A` | LevelInstance | 0.01 |  |  | A30 | no |  |
| `/Game/Levels/Halo1/Solo/A30/PCG/Assemblies/Boulder/LI_BoulderCover_B` | LevelInstance | 0.01 |  |  | A30 | no |  |
| `/Game/Levels/Halo1/Solo/A30/PCG/Assemblies/Boulder/LI_BoulderHipHeight_A` | LevelInstance | 0.01 |  |  | A30 | no |  |
| `/Game/Levels/Halo1/Solo/A30/PCG/Assemblies/Boulder/LI_BoulderRiver_A` | LevelInstance | 0.01 |  |  | A30 | no |  |
| `/Game/Levels/Halo1/Solo/A30/PCG/Assemblies/Boulder/SM_BoulderMarker` | StaticMesh | 44.19 | 1,516,532 | 1.25x2.62x8.47 | A30 | no | very dense: confirm Nanite before placing many |
| `/Game/Levels/Halo1/Solo/A30/PCG/Assemblies/River_LogDebris/BP_RiverLogAssembly_A` | Blueprint | 0.00 |  |  | A30 | no |  |
| `/Game/Levels/Halo1/Solo/A30/PCG/Assemblies/River_LogDebris/DAPCG_RiverLogs_A` | PCGDataAsset | 0.02 |  |  | A30 | no |  |
| `/Game/Levels/Halo1/Solo/A30/PCG/Assemblies/River_LogDebris/LI_RiverLogs_A` | LevelInstance | 0.01 |  |  | A30 | no |  |
| `/Game/Levels/Halo1/Solo/A30/PCG/Assemblies/River_LogDebris/SM_RiverLog_Marker` | StaticMesh | 2.11 | 64,517 | 0.4x0.87x2.82 | A30 | no |  |
| `/Game/Levels/Halo1/Solo/A30/PCG/Assemblies/Rushes/DAPCG_Rushes_A` | PCGDataAsset | 0.01 |  |  |  | no |  |
| `/Game/Levels/Halo1/Solo/A30/PCG/Assemblies/Rushes/LI_Rushes_A` | LevelInstance | 0.01 |  |  | A30 | no |  |
| `/Game/Levels/Halo1/Solo/A30/PCG/Assemblies/Sedges/DAPCG_Sedges_A` | PCGDataAsset | 0.01 |  |  |  | no |  |
| `/Game/Levels/Halo1/Solo/A30/PCG/Assemblies/Sedges/LI_Sedges_A` | LevelInstance | 0.01 |  |  | A30 | no |  |
| `/Game/Levels/Halo1/Solo/A30/PCG/ScatterSplines/BP_ScatterSpline_A30_Scree` | Blueprint | 0.00 |  |  | A30,E30 | no |  |
| `/Game/Levels/Halo1/Solo/A30/PCG/ScatterSplines/BP_ScatterSpline_A30_Sedges` | Blueprint | 0.00 |  |  | A30 | no |  |
| `/Game/Levels/Halo1/Solo/A30/PCG/ScatterSplines/DA_MeshProperties_ScreeSpline` | DataAsset | 0.00 |  |  |  | no |  |

*Group note:* Shipped A30 (Halo) river dressing recipes: LI_ level instances + DAPCG point data + BP assemblies. Read their member meshes and re-place as decor; the LI packages themselves are World partitions, not drop-in meshes

### A30/C10 baked Flux states (21)

*Where on PWR:* Reference only: shipped baked river/waterfall flux states and their height/velocity textures

| path | kind | MB | verts | bounds m | levels | PWR | note |
|---|---|---|---|---|---|---|---|
| `/Game/Levels/Halo1/Solo/A30/Water/Crash_Site_WaterFall_Streams/DA_Crash_Site_WaterFall_Streams` | DataAsset | 0.00 |  |  |  | no |  |
| `/Game/Levels/Halo1/Solo/A30/Water/Crash_Site_WaterFall_Streams/SM_A30_Crashsite_Water_Rectangle` | StaticMesh | 1.39 | 80 | 173.42x135.26x13.28 | A30 | no |  |
| `/Game/Levels/Halo1/Solo/A30/Water/Crash_Site_Waterfalls/DA_Crash_Site_Waterfalls` | DataAsset | 0.00 |  |  | A30 | no |  |
| `/Game/Levels/Halo1/Solo/A30/Water/Holdouts_Waterfall_Streams/DA_Hidden_Waterfall_Waterfalls_Stream` | DataAsset | 0.00 |  |  | A30 | no |  |
| `/Game/Levels/Halo1/Solo/A30/Water/Holdouts_Waterfall_Streams/SM_A30_Holdout_Water_Rectangle` | StaticMesh | 1.44 | 96 | 386.87x457.76x30.98 | A30 | no |  |
| `/Game/Levels/Halo1/Solo/C10/Water/PDA_M06_343_FluxState` | DataAsset | 0.00 |  |  | C10 | no |  |

Textures: `/Game/Levels/Halo1/Solo/A30/Water/Crash_Site_WaterFall_Streams/T_DA_Crash_Site_WaterFall_StreamsA_Ground` (8.4 MB), `/Game/Levels/Halo1/Solo/A30/Water/Crash_Site_WaterFall_Streams/T_DA_Crash_Site_WaterFall_StreamsA_Height` (8.4 MB), `/Game/Levels/Halo1/Solo/A30/Water/Crash_Site_WaterFall_Streams/T_DA_Crash_Site_WaterFall_StreamsA_Velocity` (16.8 MB), `/Game/Levels/Halo1/Solo/A30/Water/Crash_Site_Waterfall_Lrg/T_DA_Crash_Site_Waterfall_Lrg_Ground_2` (11.2 MB), `/Game/Levels/Halo1/Solo/A30/Water/Crash_Site_Waterfall_Lrg/T_DA_Crash_Site_Waterfall_Lrg_Height_2` (11.2 MB), `/Game/Levels/Halo1/Solo/A30/Water/Crash_Site_Waterfall_Lrg/T_DA_Crash_Site_Waterfall_Lrg_Velocity_2` (22.4 MB), `/Game/Levels/Halo1/Solo/A30/Water/Crash_Site_Waterfalls/T_DA_Crash_Site_Waterfalls_Ground` (11.2 MB), `/Game/Levels/Halo1/Solo/A30/Water/Crash_Site_Waterfalls/T_DA_Crash_Site_Waterfalls_Height` (11.2 MB), `/Game/Levels/Halo1/Solo/A30/Water/Crash_Site_Waterfalls/T_DA_Crash_Site_Waterfalls_Velocity` (22.4 MB), `/Game/Levels/Halo1/Solo/A30/Water/Holdouts_Waterfall_Streams/T_DA_Hidden_Waterfall_Waterfalls_Stream_Ground` (44.7 MB), `/Game/Levels/Halo1/Solo/A30/Water/Holdouts_Waterfall_Streams/T_DA_Hidden_Waterfall_Waterfalls_Stream_Height` (44.7 MB), `/Game/Levels/Halo1/Solo/A30/Water/Holdouts_Waterfall_Streams/T_DA_Hidden_Waterfall_Waterfalls_Stream_Velocity` (89.5 MB), `/Game/Levels/Halo1/Solo/C10/Water/T_M06_343_FluxState_Ground_NSVT` (0.7 MB), `/Game/Levels/Halo1/Solo/C10/Water/T_M06_343_FluxState_Height_NSVT` (0.7 MB), `/Game/Levels/Halo1/Solo/C10/Water/T_M06_343_FluxState_Velocity_NSVT` (1.4 MB)

*Group note:* Level-specific simulation states; only useful as reference for authoring PWR's own flux_state

### River debris and small stones (Megascans 3D) (24)

*Where on PWR:* Driftwood on gravel bars, roots on cut banks, stone litter at the waterline

| path | kind | MB | verts | bounds m | levels | PWR | note |
|---|---|---|---|---|---|---|---|
| `/Game/Megascans/3D_Assets/Drift_Wood_Branch_1_we0nehh/Foliage/FT_Drift_Wood_Branch_1_we0nehh_lod0_Var1_FoliageType` | FoliageType | 0.00 |  |  | C10 | no |  |
| `/Game/Megascans/3D_Assets/Drift_Wood_Branch_1_we0nehh/M_MS_HaloTreeWind_Branch_1_we0nehh` | MaterialInstance | 0.00 |  |  | C10,D20 | no |  |
| `/Game/Megascans/3D_Assets/Drift_Wood_Branch_1_we0nehh/S_Drift_Wood_Branch_1_we0nehh_lod0_Var1` | StaticMesh | 0.16 | 3,698 | 1.72x0.57x0.2 | C10,D20 | no |  |
| `/Game/Megascans/3D_Assets/Icelandic_Rocky_Ground_tdbmcflda/MI_Icelandic_Rocky_Ground_tdbmcflda_01` | MaterialInstance | 0.12 |  |  | E20 | no |  |
| `/Game/Megascans/3D_Assets/Icelandic_Rocky_Ground_tdbmcflda/SM_Icelandic_Rocky_Ground_tdbmcflda_01` | StaticMesh | 4.95 | 151,464 | 2.19x1.52x0.21 | E20 | no |  |
| `/Game/Megascans/3D_Assets/Limestone_Rubble_ubxbejwda/MI_Limestone_Rubble_ubxbejwda_Raw` | MaterialInstance | 0.00 |  |  | B40,C45 | no |  |
| `/Game/Megascans/3D_Assets/Limestone_Rubble_ubxbejwda/limestone_rubble_ubxbejwda_raw1` | StaticMesh | 1.08 |  |  | B40,C45 | no |  |
| `/Game/Megascans/3D_Assets/MossyForestRoots/SM_MossyForestRoots_01` | StaticMesh | 18.60 | 521,387 | 3.03x3.02x0.22 | C10 | no | very dense: confirm Nanite before placing many |
| `/Game/Megascans/3D_Assets/MossyRocks/SM_MossyRocks_01` | StaticMesh | 0.73 | 21,824 | 1.85x2.31x0.34 | C10 | no |  |
| `/Game/Megascans/3D_Assets/MossyRocks/SM_MossyRocks_02` | StaticMesh | 5.09 | 153,354 | 3.4x1.86x0.35 | C10 | no |  |
| `/Game/Megascans/3D_Assets/Mossy_Forest_Roots_wgxodhsaw/MI_Mossy_Forest_Roots_wgxodhsaw_8K` | MaterialInstance | 0.00 |  |  | E20 | no |  |
| `/Game/Megascans/3D_Assets/Mossy_Forest_Roots_wgxodhsaw/S_Mossy_Forest_Roots_wgxodhsaw_high_Var1` | StaticMesh | 7.86 | 239,628 | 4.59x2.64x0.42 | E20 | no |  |
| `/Game/Megascans/3D_Assets/Mossy_Rock_plcqz/FT_Mossy_Rock_plcqz` | FoliageType | 0.00 |  |  | A30 | no |  |
| `/Game/Megascans/3D_Assets/Mossy_Rock_plcqz/SM_Mossy_Rock_plcqz` | StaticMesh | 0.11 | 542 | 0.28x0.19x0.21 | A30 | no |  |
| `/Game/Megascans/3D_Assets/SmallStonesPack/SM_SmallStonesPack__Snow` | StaticMesh | 15.89 | 526,312 | 0.12x0.07x0.07 | B40,C45 | no | snow variant; very dense: confirm Nanite before placing many |
| `/Game/Megascans/3D_Assets/SmallStonesPack/SM_SmallStonesPack__Snow_FoliageType` | FoliageType | 0.00 |  |  | B40,C45 | no | snow variant |
| `/Game/Megascans/3D_Assets/Small_Granite_Rock_wgyxag2/S_Small_Granite_Rock_wgyxag2_lod0_Var1_Snow` | StaticMesh | 0.37 | 3,064 | 0.31x0.29x0.13 | B40,C45 | no | snow variant |
| `/Game/Megascans/3D_Assets/Small_Granite_Rock_wgyxag2/S_Small_Granite_Rock_wgyxag2_lod0_Var1_Snow_FoliageType` | FoliageType | 0.00 |  |  | B40,C45 | no | snow variant |
| `/Game/Megascans/3D_Assets/Small_stones_pack_vbuxda0iw/MI_Small_Stones_Pack_PNW_vbuxda0iw_02` | MaterialInstance | 0.13 |  |  | A30 | no |  |
| `/Game/Megascans/3D_Assets/Small_stones_pack_vbuxda0iw/MI_Small_Stones_Pack_vbuxda0iw_01` | MaterialInstance | 0.12 |  |  | A30 | no |  |
| `/Game/Megascans/3D_Assets/Small_stones_pack_vbuxda0iw/SM_Small_Stones_Pack_vbuxda0iw_Var_02` | StaticMesh | 0.38 | 4,925 | 0.1x0.05x0.04 | A30 | no |  |
| `/Game/Megascans/3D_Assets/Small_stones_pack_vbuxda0iw/SM_Small_Stones_Pack_vbuxda0iw_Var_03` | StaticMesh | 0.30 | 5,003 | 0.11x0.08x0.04 | A30 | no |  |
| `/Game/Megascans/3D_Assets/Small_stones_pack_vbuxda0iw/SM_Small_Stones_Pack_vbuxda0iw_Var_04` | StaticMesh | 0.36 | 4,990 | 0.1x0.07x0.03 | A30 | no |  |
| `/Game/Megascans/3D_Assets/Small_stones_pack_vbuxda0iw/SM_Small_Stones_Pack_vbuxda0iw_Var_05` | StaticMesh | 0.35 | 5,003 | 0.09x0.08x0.03 | A30 | no |  |

*Group note:* Megascans scans with their own MIs

### Wet ground surfaces (Megascans) (33)

*Where on PWR:* Riverbed and bank landscape layers, wet mud at fords, mossy stone on the cascade

| path | kind | MB | verts | bounds m | levels | PWR | note |
|---|---|---|---|---|---|---|---|
| `/Game/Megascans/Surfaces/Icelandic_Gravel_Porous_Rock_tcglbihg/MF_LL_Icelandic_Gravel_Pourous_Rock_tcglbihg` | MaterialFunction | 0.00 |  |  | B40,C45 | no |  |
| `/Game/Megascans/Surfaces/NordicMoss/MLI_NordicMoss_01_AoRDp` | MaterialLayerInstance | 0.00 |  |  | A30 | no |  |
| `/Game/Megascans/Surfaces/Rock_Mossy_visscjf/MI_Rock_Mossy_visscjf` | MaterialInstance | 0.15 |  |  | A30 | no |  |
| `/Game/Megascans/Surfaces/Rock_Mossy_visscjf/MLI_Rock_Mossy_visscjf` | MaterialLayerInstance | 0.00 |  |  | A30 | no |  |
| `/Game/Megascans/Surfaces/Rocky_Ground_vjdqcba/MI_Rocky_Ground_vjdqcba_Uber` | MaterialInstance | 0.13 |  |  | A30 | no |  |

Textures: `/Game/Megascans/Surfaces/Icelandic_Gravel_Porous_Rock_tcglbihg/T_Icelandic_Gravel_Pourous_Rock_tcglbihg_NSVT_D` (2.8 MB), `/Game/Megascans/Surfaces/Icelandic_Gravel_Porous_Rock_tcglbihg/T_Icelandic_Gravel_Pourous_Rock_tcglbihg_NSVT_N` (5.6 MB), `/Game/Megascans/Surfaces/Icelandic_Gravel_Porous_Rock_tcglbihg/T_Icelandic_Gravel_Pourous_Rock_tcglbihg_NSVT_ORHG` (5.6 MB), `/Game/Megascans/Surfaces/Icelandic_Rocky_Surface_slumdask/T_Icelandic_Rocky_Surface_slumdask_8K_N` (6.4 MB), `/Game/Megascans/Surfaces/MossyRockyGround/T_MossyRockyGround_01_N` (6.4 MB), `/Game/Megascans/Surfaces/Mossy_Ground_xiboab2r/T_Mossy_Ground_xiboab2r_4K_D` (3.2 MB), `/Game/Megascans/Surfaces/Mossy_Ground_xiboab2r/T_Mossy_Ground_xiboab2r_4K_N` (6.4 MB), `/Game/Megascans/Surfaces/NordicMoss/T_NordicMoss_01_AoRDp` (3.2 MB), `/Game/Megascans/Surfaces/NordicMoss/T_NordicMoss_01_BC` (3.2 MB), `/Game/Megascans/Surfaces/NordicMoss/T_NordicMoss_01_N` (6.4 MB), `/Game/Megascans/Surfaces/Rock_Mossy_visscjf/T_Rock_Mossy_visscjf__D` (3.2 MB), `/Game/Megascans/Surfaces/Rock_Mossy_visscjf/T_Rock_Mossy_visscjf__N` (6.4 MB), `/Game/Megascans/Surfaces/Rock_Mossy_visscjf/T_Rock_Mossy_visscjf__ORHG` (6.4 MB), `/Game/Megascans/Surfaces/Rocky_Ground_vjdqcba/T_Rocky_Ground_vjdqcba_4K_VT_D` (3.2 MB), `/Game/Megascans/Surfaces/Rocky_Ground_vjdqcba/T_Rocky_Ground_vjdqcba_4K_VT_N` (6.4 MB), `/Game/Megascans/Surfaces/Rocky_Ground_vjdqcba/T_Rocky_Ground_vjdqcba_ORHG` (6.4 MB), `/Game/Megascans/Surfaces/Soil_Damp_sbykj0p0/T_Damp_Soil_Cliff_sbykj0p0_2K_D` (3.2 MB), `/Game/Megascans/Surfaces/Soil_Damp_sbykj0p0/T_Damp_Soil_Cliff_sbykj0p0_2K_N` (6.4 MB), `/Game/Megascans/Surfaces/Soil_Damp_sbykj0p0/T_Damp_Soil_Cliff_sbykj0p0_2K_ORHG` (6.4 MB), `/Game/Megascans/Surfaces/Soil_Damp_scnmqbp0/T_Damp_Soil_Cliff_scnmqbp0_2K_D` (3.2 MB), `/Game/Megascans/Surfaces/Soil_Damp_scnmqbp0/T_Damp_Soil_Cliff_scnmqbp0_2K_ORHG` (6.4 MB), `/Game/Megascans/Surfaces/Soil_Mud_rm4k21p0/T_Soil_Mud_rm4k21p0_N` (1.7 MB), `/Game/Megascans/Surfaces/Soil_Mud_rm4k21p0/T_Soil_Mud_rm4k21p0_ORHG` (6.4 MB), `/Game/Megascans/Surfaces/Soil_Mud_ukxjcjhlw/T_Soil_Mud_ukxjcjhlw_4K_N` (6.4 MB), `/Game/Megascans/Surfaces/Soil_Mud_ukxjcjhlw/T_Soil_Mud_ukxjcjhlw_4K_ORHG` (6.4 MB), `/Game/Megascans/Surfaces/Stones_on_Soil_rmsijrp0/T_Soil_Stone_NSVT_A30_D` (2.8 MB), `/Game/Megascans/Surfaces/Stones_on_Soil_rmsijrp0/T_Soil_Stone_NSVT_N` (5.6 MB), `/Game/Megascans/Surfaces/Stones_on_Soil_rmsijrp0/T_Soil_Stone_NSVT_ORHG` (5.6 MB)

*Group note:* Megascans ground texture sets (D/N plus ORHG or ORDp packed roughness/height); usable as extra PWR landscape surfaces with the existing surfaces mechanism

## 2. Lakes and shores (453)

### Sand ground materials (Env/Bio/Ground/Sand, coastline gradients) (9)

*Where on PWR:* Lake beach landscape layer

| path | kind | MB | verts | bounds m | levels | PWR | note |
|---|---|---|---|---|---|---|---|
| `/Game/Env/Bio/Ground/Sand/Materials/MI_Sand_Pile_Uber` | MaterialInstance | 0.17 |  |  | D40 | no |  |
| `/Game/Env/Bio/Ground/Sand/Sand_Pile_A/SM_sand_pile_a` | StaticMesh | 0.21 | 4,634 | 3.48x6.23x1.08 | D40 | no |  |
| `/Game/Env/Bio/Ground/Sand/Sand_Pile_B/SM_sand_pile_b` | StaticMesh | 0.16 | 3,569 | 2.52x3.37x0.8 | D40 | no |  |
| `/Game/Env/Bio/Ground/Sand/Sand_Pile_C/SM_sand_pile_c` | StaticMesh | 0.19 | 4,582 | 2.79x5.14x0.82 | D40 | no |  |
| `/Game/Env/Bio/Ground/Sand/Sand_Pile_D/SM_sand_pile_d` | StaticMesh | 0.07 | 895 | 2.48x2.43x0.22 | D40 | no |  |
| `/Game/Env/Bio/Ground/Sand/Sand_Pile_E/SM_Sand_Pile_E` | StaticMesh | 3.81 | 139,096 | 65.31x51.61x13.29 | E20 | no |  |
| `/Game/Env/Bio/Ground/Sand/Sand_Pile_F/SM_Sand_Pile_F` | StaticMesh | 2.10 | 63,336 | 10.11x6.98x0.94 | E20 | no |  |

Textures: `/Game/Env/Bio/Materials/Gradient/T_Gradient_Coastline_01_NSVT_D` (0.0 MB), `/Game/Env/Bio/Materials/Soil/Sand_Coastal_Grass/T_Sand_Coastal_Grass_ORHG` (6.4 MB)

*Group note:* Env/Bio sand material instances and textures

### Beach erosion and shore life (MarineLife) (33)

*Where on PWR:* Lake shore erosion banks (Sand_Beach_Erosion); shells/anemones are marine and do not fit fresh water

| path | kind | MB | verts | bounds m | levels | PWR | note |
|---|---|---|---|---|---|---|---|
| `/Game/Env/Bio/MarineLife/Anemones/MI_MarineLife_Anemones` | MaterialInstance | 0.02 |  |  |  | no |  |
| `/Game/Env/Bio/MarineLife/Anemones/MI_MarineLife_Anemones_Fresnel` | MaterialInstance | 0.02 |  |  |  | no |  |
| `/Game/Env/Bio/MarineLife/Anemones/SM_MarineLife_Anemones_Lrg_A` | StaticMesh | 0.89 | 6,565 | 0.38x0.41x0.35 |  | no |  |
| `/Game/Env/Bio/MarineLife/Anemones/SM_MarineLife_Anemones_Lrg_B` | StaticMesh | 0.81 | 5,708 | 0.41x0.36x0.25 |  | no |  |
| `/Game/Env/Bio/MarineLife/Anemones/SM_MarineLife_Anemones_Lrg_C` | StaticMesh | 0.95 | 6,564 | 0.35x0.35x0.23 |  | no |  |
| `/Game/Env/Bio/MarineLife/Anemones/SM_MarineLife_Anemones_Lrg_E` | StaticMesh | 1.01 | 6,900 | 0.34x0.42x0.22 |  | no |  |
| `/Game/Env/Bio/MarineLife/Anemones/SM_MarineLife_Anemones_Med_A` | StaticMesh | 0.42 | 2,806 | 0.19x0.17x0.34 |  | no |  |
| `/Game/Env/Bio/MarineLife/Coral/SM_MarineLife_Coral_A` | StaticMesh | 2.36 | 14,630 | 0.53x0.46x0.5 |  | no | off-setting (tropical/alien/marine) [setting] |
| `/Game/Env/Bio/MarineLife/Materials/MI_Env_RVT_Erosion_A_100Normal` | MaterialInstance | 0.01 |  |  | B30 | no |  |
| `/Game/Env/Bio/MarineLife/Materials/MI_Env_RVT_Erosion_A_10Normal` | MaterialInstance | 0.01 |  |  | B30 | no |  |
| `/Game/Env/Bio/MarineLife/Materials/MI_Env_RVT_Erosion_A_25Normal` | MaterialInstance | 0.01 |  |  | B30 | no |  |
| `/Game/Env/Bio/MarineLife/Materials/MI_Env_RVT_Erosion_A_50Normal` | MaterialInstance | 0.01 |  |  | B30 | no |  |
| `/Game/Env/Bio/MarineLife/Materials/MI_Env_RVT_Erosion_B_100Normal` | MaterialInstance | 0.01 |  |  | B30 | no |  |
| `/Game/Env/Bio/MarineLife/Materials/MI_Env_RVT_Erosion_B_10Normal` | MaterialInstance | 0.01 |  |  | B30 | no |  |
| `/Game/Env/Bio/MarineLife/Materials/MI_Env_RVT_Erosion_B_200Normal` | MaterialInstance | 0.01 |  |  | B30 | no |  |
| `/Game/Env/Bio/MarineLife/Materials/MI_Env_RVT_Erosion_B_25Normal` | MaterialInstance | 0.01 |  |  | B30 | no |  |
| `/Game/Env/Bio/MarineLife/Materials/MI_Env_RVT_Erosion_B_50Normal` | MaterialInstance | 0.01 |  |  | B30 | no |  |
| `/Game/Env/Bio/MarineLife/Materials/MI_Env_RVT_Erosion_B_75Normal` | MaterialInstance | 0.01 |  |  | B30 | no |  |
| `/Game/Env/Bio/MarineLife/Materials/MI_Env_RVT_Erosion_C_100Normal` | MaterialInstance | 0.01 |  |  | B30 | no |  |
| `/Game/Env/Bio/MarineLife/Materials/MI_Env_RVT_Erosion_D_100Normal` | MaterialInstance | 0.01 |  |  | B30 | no |  |
| `/Game/Env/Bio/MarineLife/Materials/MI_Env_RVT_Erosion_E_100Normal` | MaterialInstance | 0.01 |  |  | B30 | no |  |
| `/Game/Env/Bio/MarineLife/Materials/MM_Env_MarineLife_Base` | Material | 0.03 |  |  | B30 | no |  |
| `/Game/Env/Bio/MarineLife/Materials/MM_Env_RVT_MarineLife` | Material | 0.02 |  |  | B30 | no |  |
| `/Game/Env/Bio/MarineLife/Oyster/MI_MarineLife_Oyster` | MaterialInstance | 0.00 |  |  |  | no |  |
| `/Game/Env/Bio/MarineLife/Oyster/SM_MarineLife_Oyster_Med_A` | StaticMesh | 1.17 | 8,825 | 0.23x0.19x0.07 |  | no |  |
| `/Game/Env/Bio/MarineLife/SeaSnails/FT_MarineLife_SeaSnails_Med_A_FoliageType` | FoliageType | 0.00 |  |  | B30 | no |  |
| `/Game/Env/Bio/MarineLife/SeaSnails/FT_MarineLife_SeaSnails_Sml_A_FoliageType` | FoliageType | 0.00 |  |  | B30 | no |  |
| `/Game/Env/Bio/MarineLife/SeaSnails/MI_MarineLife_SeaSnails` | MaterialInstance | 0.00 |  |  | B30 | no |  |
| `/Game/Env/Bio/MarineLife/SeaSnails/SM_MarineLife_SeaSnails_Med_A` | StaticMesh | 0.84 | 6,512 | 0.27x0.29x0.22 | B30 | no |  |
| `/Game/Env/Bio/MarineLife/SeaSnails/SM_MarineLife_SeaSnails_Sml_A` | StaticMesh | 0.56 | 4,145 | 0.21x0.21x0.16 | B30 | no |  |
| `/Game/Env/Bio/MarineLife/SeaStar/FT_MarineLife_Seastar_A_FoliageType` | FoliageType | 0.00 |  |  | B30 | no |  |
| `/Game/Env/Bio/MarineLife/SeaStar/MI_MarineLife_Seastar_A` | MaterialInstance | 0.00 |  |  | B30 | no |  |
| `/Game/Env/Bio/MarineLife/SeaStar/SM_MarineLife_Seastar_A` | StaticMesh | 1.74 | 26,387 | 0.68x0.66x0.12 | B30 | no |  |

*Group note:* B30 beach erosion meshes plus marine life (skip the marine items)

### Nordic beach rocky ground (Env/Bio) (2)

*Where on PWR:* Shore shelves where the lake meets rock

| path | kind | MB | verts | bounds m | levels | PWR | note |
|---|---|---|---|---|---|---|---|
| `/Game/Env/Bio/Rock/Nordic_Beach_Rocky_Ground/MI_A30_Mud_Debris` | MaterialInstance | 0.17 |  |  | A30,D40 | no |  |
| `/Game/Env/Bio/Rock/Nordic_Beach_Rocky_Ground/SM_Nordic_Beach_Rocky_Ground` | StaticMesh | 9.93 | 306,320 | 3.69x3.61x0.55 | A30,D40 | no |  |

*Group note:* Env/Bio copy of the Megascans rocky-ground scan

### PNW boulder set (Environments/PNW) (53)

*Where on PWR:* Lake shore and meadow boulders

| path | kind | MB | verts | bounds m | levels | PWR | note |
|---|---|---|---|---|---|---|---|
| `/Game/Environments/PNW/Assets/Large_Rock_Shelf_A/SM_Large_Rock_Shelf_A` | StaticMesh | 1.29 | 40,855 | 2.62x3.23x1.72 | A30 | no |  |
| `/Game/Environments/PNW/Assets/Mossy_Boulder_A/SM_Mossy_Boulder_A` | StaticMesh | 2.00 | 71,977 | 3.22x2.98x2.25 | A30 | no |  |
| `/Game/Environments/PNW/Assets/Mossy_Forest_Boulder_A/SM_Mossy_Forest_Boulder_A` | StaticMesh | 1.40 | 41,379 | 3.25x3.12x1.99 | A30 | no |  |
| `/Game/Environments/PNW/Assets/Nordic_Beach_Rocks_A/SM_Nordic_Beach_Rocks_A` | StaticMesh | 1.58 | 43,447 | 5.14x2.65x1.38 | A30 | no |  |
| `/Game/Environments/PNW/Assets/Nordic_Beach_Rocks_B/SM_Nordic_Beach_Rocks_B` | StaticMesh | 2.11 | 62,943 | 2.25x1.85x0.82 | A30 | no |  |
| `/Game/Environments/PNW/Assets/Nordic_Beach_Rocks_C/SM_Nordic_Beach_Rocks_C` | StaticMesh | 2.33 | 67,010 | 6.2x3.56x2.47 | A30 | no |  |
| `/Game/Environments/PNW/Assets/Nordic_Boulder_A/SM_Nordic_Boulder_A` | StaticMesh | 4.20 | 124,610 | 6.58x8.9x4.06 | A30 | no |  |
| `/Game/Environments/PNW/Assets/Tundra_Boulder_A/SM_Tundra_Boulder_A` | StaticMesh | 2.53 | 75,792 | 2.21x1.44x0.95 | A30 | no |  |
| `/Game/Environments/PNW/Assets/Tundra_Boulder_B/SM_Tundra_Boulder_B` | StaticMesh | 5.09 | 150,641 | 2.87x2.12x1.8 | A30 | no |  |
| `/Game/Environments/PNW/Assets/Tundra_Rocky_Ground_A/SM_Tundra_Rocky_Ground_A` | StaticMesh | 0.75 | 21,551 | 4.89x4.39x0.31 | A30 | no |  |
| `/Game/Environments/PNW/Materials/MI_Env_Lyrd_Granite_Base` | MaterialInstance | 0.17 |  |  | A30,D40 | no |  |
| `/Game/Environments/PNW/Materials/MI_Large_Rock_Shelf_A/MI_Env_Layered_Large_Rock_Shelf_A` | MaterialInstance | 0.17 |  |  | A30 | no |  |
| `/Game/Environments/PNW/Materials/MI_Mossy_Boulder_A/MI_Env_Layered_Mossy_Boulder_A` | MaterialInstance | 0.20 |  |  |  | no |  |
| `/Game/Environments/PNW/Materials/MI_Mossy_Forest_Boulder_A/MI_Env_Layered_Mossy_Forest_Boulder_A` | MaterialInstance | 0.17 |  |  | A30 | no |  |
| `/Game/Environments/PNW/Materials/MI_Mossy_Forest_Boulder_A/MLI_Env_Layered_Mossy_Forest_Boulder_A` | MaterialLayerInstance | 0.00 |  |  | A30 | no |  |
| `/Game/Environments/PNW/Materials/MI_Nordic_Beach_Rocks_A/MI_Env_Layered_Nordic_Beach_Rocks_A` | MaterialInstance | 0.19 |  |  | A30 | no |  |
| `/Game/Environments/PNW/Materials/MI_Nordic_Beach_Rocks_B/MI_Env_Layered_Nordic_Beach_Rocks_B` | MaterialInstance | 0.18 |  |  | A30 | no |  |
| `/Game/Environments/PNW/Materials/MI_Nordic_Beach_Rocks_C/MI_Env_Layered_Nordic_Beach_Rocks_C` | MaterialInstance | 0.17 |  |  | A30 | no |  |
| `/Game/Environments/PNW/Materials/MI_Nordic_Boulder_A/MI_Env_Layered_Nordic_Boulder_A` | MaterialInstance | 0.20 |  |  | A30 | no |  |
| `/Game/Environments/PNW/Materials/MI_Tundra_Boulder_A/MI_Env_Layered_Tundra_Boulder_A` | MaterialInstance | 0.17 |  |  | A30 | no |  |
| `/Game/Environments/PNW/Materials/MI_Tundra_Boulder_A/MLI_Tundra_Boulder_A` | MaterialLayerInstance | 0.00 |  |  | A30,D40 | no |  |
| `/Game/Environments/PNW/Materials/MI_Tundra_Boulder_B/MI_Env_Layered_Tundra_Boulder_B` | MaterialInstance | 0.17 |  |  | A30 | no |  |
| `/Game/Environments/PNW/Materials/MI_Tundra_Boulder_vivvaewaw/MI_Env_Lyrd_Granite_Tundra_Boulder_vivvaewaw` | MaterialInstance | 0.17 |  |  | A30 | no |  |
| `/Game/Environments/PNW/Materials/MI_Tundra_Rocky_Ground_A/MI_Env_Layered_Tundra_Rocky_Ground_A` | MaterialInstance | 0.17 |  |  | A30 | no |  |
| `/Game/Environments/PNW/Materials/MLI_Granite` | MaterialLayerInstance | 0.00 |  |  | A30,D40 | no |  |

Textures: `/Game/Environments/PNW/Textures/T_Large_Rock_Shelf_A/T_Large_Rock_Shelf_A_N` (6.4 MB), `/Game/Environments/PNW/Textures/T_Large_Rock_Shelf_A/T_Large_Rock_Shelf_A_ORHG` (6.4 MB), `/Game/Environments/PNW/Textures/T_Mossy_Forest_Boulder_A/T_Mossy_Forest_Boulder_A_D` (3.2 MB), `/Game/Environments/PNW/Textures/T_Mossy_Forest_Boulder_A/T_Mossy_Forest_Boulder_A_N` (6.4 MB), `/Game/Environments/PNW/Textures/T_Mossy_Forest_Boulder_A/T_Mossy_Forest_Boulder_A_ORHG` (6.4 MB), `/Game/Environments/PNW/Textures/T_Nordic_Beach_Rocks_A/T_Nordic_Beach_Rocks_A_ORDG` (6.4 MB), `/Game/Environments/PNW/Textures/T_Nordic_Beach_Rocks_A/T_Nordic_Beach_Rocks_ukoifj1mw_8K_D` (3.2 MB), `/Game/Environments/PNW/Textures/T_Nordic_Beach_Rocks_A/T_Nordic_Beach_Rocks_ukoifj1mw_8K_N` (6.4 MB), `/Game/Environments/PNW/Textures/T_Nordic_Beach_Rocks_B/T_Nordic_Beach_Rocks_B_ORDG` (6.4 MB), `/Game/Environments/PNW/Textures/T_Nordic_Beach_Rocks_B/T_Nordic_Beach_Rocks_ulznddxva_8K_N` (6.4 MB), `/Game/Environments/PNW/Textures/T_Nordic_Beach_Rocks_C/T_Nordic_Beach_Rocks_vepkcelqx_8K_D` (3.2 MB), `/Game/Environments/PNW/Textures/T_Nordic_Beach_Rocks_C/T_Nordic_Beach_Rocks_vepkcelqx_8K_N` (6.4 MB), `/Game/Environments/PNW/Textures/T_Nordic_Beach_Rocks_C/T_Nordic_Beach_Rocks_vepkcelqx_ORHG` (6.4 MB), `/Game/Environments/PNW/Textures/T_Nordic_Boulder_A/T_Nordic_Boulder_A_D` (3.2 MB), `/Game/Environments/PNW/Textures/T_Nordic_Boulder_A/T_Nordic_Boulder_A_N` (6.4 MB), `/Game/Environments/PNW/Textures/T_Nordic_Boulder_A/T_Nordic_Boulder_A_ORHG` (6.4 MB), `/Game/Environments/PNW/Textures/T_Tiling_Granite/T_granite_rock_D` (3.2 MB), `/Game/Environments/PNW/Textures/T_Tiling_Granite/T_granite_rock_N` (6.4 MB), `/Game/Environments/PNW/Textures/T_Tiling_Granite/T_granite_rock_ORHG` (6.4 MB), `/Game/Environments/PNW/Textures/T_Tundra_Boulder_A/T_Tundra_Boulder_A_D` (3.2 MB), `/Game/Environments/PNW/Textures/T_Tundra_Boulder_A/T_Tundra_Boulder_A_N` (6.4 MB), `/Game/Environments/PNW/Textures/T_Tundra_Boulder_A/T_Tundra_Boulder_A_ORHG` (6.4 MB), `/Game/Environments/PNW/Textures/T_Tundra_Boulder_B/T_Tundra_Boulder_B_D` (3.2 MB), `/Game/Environments/PNW/Textures/T_Tundra_Boulder_B/T_Tundra_Boulder_B_N` (6.4 MB), `/Game/Environments/PNW/Textures/T_Tundra_Boulder_B/T_Tundra_Boulder_B_ORDG` (6.4 MB), `/Game/Environments/PNW/Textures/T_Tundra_Rocky_Ground_A/T_Tundra_Rocky_Ground_A_D` (3.2 MB), `/Game/Environments/PNW/Textures/T_Tundra_Rocky_Ground_A/T_Tundra_Rocky_Ground_A_N` (6.4 MB), `/Game/Environments/PNW/Textures/T_Tundra_Rocky_Ground_A/T_Tundra_Rocky_Ground_A_ORDG` (6.4 MB)

*Group note:* Small curated set (Nordic beach rocks A-C, Tundra/Nordic/Mossy boulders, rock shelf) with own MIs and a tiling granite

### Coastline and wave systems (FluidFlux) (32)

*Where on PWR:* Lake shore wave lapping driven by the Flux coastline

| path | kind | MB | verts | bounds m | levels | PWR | note |
|---|---|---|---|---|---|---|---|
| `/Game/FluidFlux/Coastline/Blueprints/BP_FluxCoastlineDomain` | Blueprint | 0.05 |  |  | B30 | no |  |
| `/Game/FluidFlux/Coastline/Functions/MF_CoastSlope` | MaterialFunction | 0.00 |  |  | A30,A50,B30,C10,C20,D20,E20 | no |  |
| `/Game/FluidFlux/Coastline/Functions/MF_CoastlineColor` | MaterialFunction | 0.00 |  |  | A30,B30,C10,C20 | no |  |
| `/Game/FluidFlux/Coastline/Functions/MF_CoastlineDataGet` | MaterialFunction | 0.00 |  |  | A30,A50,B30,C10,C20,D20,E20 | no |  |
| `/Game/FluidFlux/Coastline/Functions/MF_CoastlineDataSet` | MaterialFunction | 0.00 |  |  | A30,A50,B30,C10,C20,D20,E20 | no |  |
| `/Game/FluidFlux/Coastline/Functions/MF_CoastlineFromMaterial` | MaterialFunction | 0.00 |  |  | A50,B30,C10,D20,E20 | no |  |
| `/Game/FluidFlux/Coastline/Functions/MF_CoastlineOffsets` | MaterialFunction | 0.00 |  |  | A30,A50,B30,C10,C20,D20,E20 | no |  |
| `/Game/FluidFlux/Coastline/Functions/MF_CoastlineProfileUV` | MaterialFunction | 0.00 |  |  | A30,B30,C10,C20 | no |  |
| `/Game/FluidFlux/Coastline/Functions/MF_CoastlineProfileUV_MPC` | MaterialFunction | 0.00 |  |  | A50,B30,C10,D20,E20 | no |  |
| `/Game/FluidFlux/Coastline/Functions/MF_CoastlineSample` | MaterialFunction | 0.00 |  |  | A30,B30,C10,C20 | no |  |
| `/Game/FluidFlux/Coastline/Functions/MF_CoastlineSample_MPC` | MaterialFunction | 0.00 |  |  | A50,B30,C10,D20,E20 | no |  |
| `/Game/FluidFlux/Coastline/Functions/MF_CoastlineTransform` | MaterialFunction | 0.00 |  |  | A30,A50,B30,C10,C20,D20,E20 | no |  |
| `/Game/FluidFlux/Coastline/Functions/MF_CoastlineWater` | MaterialFunction | 0.00 |  |  | A30,B30,C10,C20 | no |  |
| `/Game/FluidFlux/Coastline/Functions/MF_CoastlineWater_MPC` | MaterialFunction | 0.00 |  |  | A50,B30,C10,D20,E20 | no |  |
| `/Game/FluidFlux/Coastline/Functions/MF_EdgeCorrection` | MaterialFunction | 0.00 |  |  | A30,B30,C10,C20 | no |  |
| `/Game/FluidFlux/Coastline/Functions/MF_EdgeCorrection_MPC` | MaterialFunction | 0.00 |  |  | A50,B30,C10,D20,E20 | no |  |
| `/Game/FluidFlux/Coastline/Functions/MF_FluxWorldToCoastlineUV` | MaterialFunction | 0.00 |  |  | A30,B30,C10,C20 | no |  |
| `/Game/FluidFlux/Coastline/Functions/MF_FluxWorldToCoastlineUV_MPC` | MaterialFunction | 0.00 |  |  | A50,B30,C10,D20,E20 | no |  |
| `/Game/FluidFlux/Coastline/Functions/MF_GroundSlope` | MaterialFunction | 0.00 |  |  | A30,B30,C10 | no |  |
| `/Game/FluidFlux/Coastline/Functions/MF_GroundSlope_MPC` | MaterialFunction | 0.00 |  |  | A50,B30,C10,D20,E20 | no |  |
| `/Game/FluidFlux/Coastline/Functions/MF_SampleCoastlineHeight` | MaterialFunction | 0.00 |  |  | A30,B30,C10,C20 | no |  |
| `/Game/FluidFlux/Coastline/Functions/MF_SampleCoastlineHeight_MPC` | MaterialFunction | 0.00 |  |  | A50,B30,C10,D20,E20 | no |  |
| `/Game/FluidFlux/Coastline/Functions/MF_SampleWaveProfile` | MaterialFunction | 0.00 |  |  | A30,B30,C10,C20 | no |  |
| `/Game/FluidFlux/Coastline/Functions/MF_SampleWaveProfile_MPC` | MaterialFunction | 0.00 |  |  | A50,B30,C10,D20,E20 | no |  |
| `/Game/FluidFlux/Coastline/Functions/MF_SlopeNormal` | MaterialFunction | 0.00 |  |  | A30,B30,C10,C20 | no |  |
| `/Game/FluidFlux/Coastline/Functions/MF_SlopeNormal_MPC` | MaterialFunction | 0.00 |  |  | A50,B30,C10,D20,E20 | no |  |
| `/Game/FluidFlux/Coastline/Materials/M_CombineCoastlineData` | Material | 0.01 |  |  | B30 | no |  |
| `/Game/FluidFlux/Waves/Blueprints/BPI_FluxWaveRenderer` | Blueprint | 0.00 |  |  | A30,B30,C10,C20 | no |  |
| `/Game/FluidFlux/Waves/Blueprints/BP_FluxOceanWave` | Blueprint | 0.06 |  |  | A30,B30,C10,C20 | no |  |
| `/Game/FluidFlux/Waves/Materials/MI_TextureWaveGenerator` | MaterialInstance | 0.00 |  |  | A30,B30,C10,C20 | no |  |
| `/Game/FluidFlux/Waves/Materials/M_TextureWaveGenerator` | Material | 0.01 |  |  | A30,B30,C10,C20 | no |  |
| `/Game/FluidFlux/Waves/Materials/M_TextureWavePreview` | Material | 0.02 |  |  | A30,B30,C10,C20 | no |  |

*Group note:* Fluid Flux coastline domain + wave tools

### B30 sea surfaces (8)

*Where on PWR:* Reference only (PWR uses Fluid Flux)

| path | kind | MB | verts | bounds m | levels | PWR | note |
|---|---|---|---|---|---|---|---|
| `/Game/Levels/Halo1/Solo/B30/Meshes/WaterSurfaces/SM_b30_sea_water_surface_1` | StaticMesh | 0.00 | 13 | 232.79x400.0x0.49 | B30 | no |  |
| `/Game/Levels/Halo1/Solo/B30/Meshes/WaterSurfaces/SM_b30_sea_water_surface_1_1` | StaticMesh | 0.00 | 11 | 400.0x241.99x0.49 | B30 | no |  |
| `/Game/Levels/Halo1/Solo/B30/Meshes/WaterSurfaces/SM_b30_sea_water_surface_2` | StaticMesh | 0.00 | 15 | 400.0x212.76x0.49 | B30 | no |  |
| `/Game/Levels/Halo1/Solo/B30/Meshes/WaterSurfaces/SM_b30_sea_water_surface_2_1` | StaticMesh | 0.01 | 24 | 239.72x400.0x0.49 | B30 | no |  |
| `/Game/Levels/Halo1/Solo/B30/Meshes/WaterSurfaces/SM_b30_sea_water_surface_3` | StaticMesh | 0.01 | 13 | 226.64x400.0x0.49 | B30 | no |  |
| `/Game/Levels/Halo1/Solo/B30/Meshes/WaterSurfaces/SM_b30_sea_water_surface_3_1` | StaticMesh | 0.01 | 15 | 400.0x301.12x0.49 | B30 | no |  |
| `/Game/Levels/Halo1/Solo/B30/Meshes/WaterSurfaces/SM_b30_sea_water_surface_4` | StaticMesh | 0.01 | 14 | 400.0x216.86x0.49 | B30 | no |  |
| `/Game/Levels/Halo1/Solo/B30/Meshes/WaterSurfaces/SM_b30_sea_water_surface_4_1` | StaticMesh | 0.00 | 13 | 196.91x400.0x0.49 | B30 | no |  |

*Group note:* B30 sea water surface meshes

### B30 tide pools and waterline scree piles (61)

*Where on PWR:* Recipe for lake-edge rock piles with waterline variants

| path | kind | MB | verts | bounds m | levels | PWR | note |
|---|---|---|---|---|---|---|---|
| `/Game/Levels/Halo1/Solo/B30/PCG/BPs/BP_PCGBlockerVolume_B30` | Blueprint | 0.00 |  |  | B30 | no |  |
| `/Game/Levels/Halo1/Solo/B30/PCG/BPs/BP_PCGSpawnerVolume_B30` | Blueprint | 0.00 |  |  | B30 | no |  |
| `/Game/Levels/Halo1/Solo/B30/PCG/BPs/Cliffs/BP_PCGMesh_Cliff_Uluwatu_B30` | Blueprint | 0.00 |  |  | B30 | no |  |
| `/Game/Levels/Halo1/Solo/B30/PCG/BPs/Cliffs/BP_PCGMesh_Cliff_Uluwatu_BG_B30` | Blueprint | 0.00 |  |  | B30 | no |  |
| `/Game/Levels/Halo1/Solo/B30/PCG/BPs/Cliffs/BP_PCGMesh_Volcano_B30` | Blueprint | 0.00 |  |  | B30 | no |  |
| `/Game/Levels/Halo1/Solo/B30/PCG/BPs/TidePools/BP_PCGMesh_Cliff_Uluwatu_Tidepool_B30` | Blueprint | 0.00 |  |  | B30 | no |  |
| `/Game/Levels/Halo1/Solo/B30/PCG/PLAs/Assemblies/BP_PLA_Uluwatu_Med_Screepile_A` | Blueprint | 0.00 |  |  |  | no |  |
| `/Game/Levels/Halo1/Solo/B30/PCG/PLAs/Assemblies/BP_PLA_Uluwatu_Med_Screepile_A_BG` | Blueprint | 0.00 |  |  | B30 | no |  |
| `/Game/Levels/Halo1/Solo/B30/PCG/PLAs/Assemblies/BP_PLA_Uluwatu_Med_Screepile_A_Waterline` | Blueprint | 0.00 |  |  | B30 | no |  |
| `/Game/Levels/Halo1/Solo/B30/PCG/PLAs/Assemblies/BP_PLA_Uluwatu_Med_Screepile_A_Waterline_BG` | Blueprint | 0.00 |  |  | B30 | no |  |
| `/Game/Levels/Halo1/Solo/B30/PCG/PLAs/Assemblies/BP_PLA_Uluwatu_Med_Screepile_B` | Blueprint | 0.00 |  |  | B30 | no |  |
| `/Game/Levels/Halo1/Solo/B30/PCG/PLAs/Assemblies/BP_PLA_Uluwatu_Med_Screepile_B_BG` | Blueprint | 0.00 |  |  | B30 | no |  |
| `/Game/Levels/Halo1/Solo/B30/PCG/PLAs/Assemblies/BP_PLA_Uluwatu_Med_Screepile_B_Waterline` | Blueprint | 0.00 |  |  | B30 | no |  |
| `/Game/Levels/Halo1/Solo/B30/PCG/PLAs/Assemblies/BP_PLA_Uluwatu_Med_Screepile_B_Waterline_BG` | Blueprint | 0.00 |  |  | B30 | no |  |
| `/Game/Levels/Halo1/Solo/B30/PCG/PLAs/Assemblies/BP_PLA_Uluwatu_Med_Screepile_C` | Blueprint | 0.00 |  |  | B30 | no |  |
| `/Game/Levels/Halo1/Solo/B30/PCG/PLAs/Assemblies/BP_PLA_Uluwatu_Med_Screepile_C_BG` | Blueprint | 0.00 |  |  | B30 | no |  |
| `/Game/Levels/Halo1/Solo/B30/PCG/PLAs/Assemblies/BP_PLA_Uluwatu_Med_Screepile_C_Waterline` | Blueprint | 0.00 |  |  | B30 | no |  |
| `/Game/Levels/Halo1/Solo/B30/PCG/PLAs/Assemblies/BP_PLA_Uluwatu_Med_Screepile_C_Waterline_BG` | Blueprint | 0.00 |  |  | B30 | no |  |
| `/Game/Levels/Halo1/Solo/B30/PCG/PLAs/Assemblies/BP_PLA_Uluwatu_Small_Screepile_D_BG` | Blueprint | 0.00 |  |  | B30 | no |  |
| `/Game/Levels/Halo1/Solo/B30/PCG/PLAs/Assemblies/BP_PLA_Uluwatu_Small_Screepile_E` | Blueprint | 0.00 |  |  |  | no |  |
| `/Game/Levels/Halo1/Solo/B30/PCG/PLAs/Assemblies/BP_PLA_Uluwatu_Small_Screepile_E_BG` | Blueprint | 0.00 |  |  | B30 | no |  |
| `/Game/Levels/Halo1/Solo/B30/PCG/PLAs/Uluwatu/PLAY_SM_Uluwatu_Med_Screepile_A_Play_BG_CollisionMesh` | StaticMesh | 1.46 |  |  |  | no | collision proxy mesh |
| `/Game/Levels/Halo1/Solo/B30/PCG/PLAs/Uluwatu/PLAY_SM_Uluwatu_Med_Screepile_A_Play_CollisionMesh` | StaticMesh | 1.46 |  |  |  | no | collision proxy mesh |
| `/Game/Levels/Halo1/Solo/B30/PCG/PLAs/Uluwatu/PLAY_SM_Uluwatu_Med_Screepile_B_Play_BG_CollisionMesh` | StaticMesh | 2.10 |  |  |  | no | collision proxy mesh |
| `/Game/Levels/Halo1/Solo/B30/PCG/PLAs/Uluwatu/PLAY_SM_Uluwatu_Med_Screepile_B_Play_CollisionMesh` | StaticMesh | 2.10 |  |  |  | no | collision proxy mesh |
| `/Game/Levels/Halo1/Solo/B30/PCG/PLAs/Uluwatu/PLAY_SM_Uluwatu_Med_Screepile_C_Play_BG_CollisionMesh` | StaticMesh | 1.18 |  |  |  | no | collision proxy mesh |
| `/Game/Levels/Halo1/Solo/B30/PCG/PLAs/Uluwatu/PLAY_SM_Uluwatu_Med_Screepile_C_Play_CollisionMesh` | StaticMesh | 1.18 |  |  |  | no | collision proxy mesh |
| `/Game/Levels/Halo1/Solo/B30/PCG/PLAs/Uluwatu/PLAY_SM_Uluwatu_RockPile_A_Play_CollisionMesh` | StaticMesh | 0.38 |  |  |  | no | collision proxy mesh |
| `/Game/Levels/Halo1/Solo/B30/PCG/PLAs/Uluwatu/PLAY_SM_Uluwatu_Small_Screepile_D_Play_BG_CollisionMesh` | StaticMesh | 0.15 |  |  |  | no | collision proxy mesh |
| `/Game/Levels/Halo1/Solo/B30/PCG/PLAs/Uluwatu/PLAY_SM_Uluwatu_Small_Screepile_E_Play_BG_CollisionMesh` | StaticMesh | 0.10 |  |  |  | no | collision proxy mesh |
| `/Game/Levels/Halo1/Solo/B30/PCG/PLAs/Uluwatu/PLAY_SM_Uluwatu_Small_Screepile_E_Play_CollisionMesh` | StaticMesh | 0.10 |  |  |  | no | collision proxy mesh |
| `/Game/Levels/Halo1/Solo/B30/PCG/PLAs/Uluwatu/PLA_Uluwatu_Med_Screepile_A` | LevelInstance | 0.01 |  |  | B30 | no |  |
| `/Game/Levels/Halo1/Solo/B30/PCG/PLAs/Uluwatu/PLA_Uluwatu_Med_Screepile_A_PCG` | PCGDataAsset | 0.00 |  |  |  | no |  |
| `/Game/Levels/Halo1/Solo/B30/PCG/PLAs/Uluwatu/PLA_Uluwatu_Med_Screepile_A_Waterline` | LevelInstance | 0.01 |  |  | B30 | no |  |
| `/Game/Levels/Halo1/Solo/B30/PCG/PLAs/Uluwatu/PLA_Uluwatu_Med_Screepile_A_Waterline_BG` | LevelInstance | 0.01 |  |  | B30 | no |  |
| `/Game/Levels/Halo1/Solo/B30/PCG/PLAs/Uluwatu/PLA_Uluwatu_Med_Screepile_A_Waterline_BG_PCG` | PCGDataAsset | 0.01 |  |  | B30 | no |  |
| `/Game/Levels/Halo1/Solo/B30/PCG/PLAs/Uluwatu/PLA_Uluwatu_Med_Screepile_A_Waterline_PCG` | PCGDataAsset | 0.01 |  |  | B30 | no |  |
| `/Game/Levels/Halo1/Solo/B30/PCG/PLAs/Uluwatu/PLA_Uluwatu_Med_Screepile_A__BG` | LevelInstance | 0.01 |  |  | B30 | no |  |
| `/Game/Levels/Halo1/Solo/B30/PCG/PLAs/Uluwatu/PLA_Uluwatu_Med_Screepile_A__BG_PCG` | PCGDataAsset | 0.00 |  |  | B30 | no |  |
| `/Game/Levels/Halo1/Solo/B30/PCG/PLAs/Uluwatu/PLA_Uluwatu_Med_Screepile_B` | LevelInstance | 0.01 |  |  | B30 | no |  |
| `/Game/Levels/Halo1/Solo/B30/PCG/PLAs/Uluwatu/PLA_Uluwatu_Med_Screepile_B_BG` | LevelInstance | 0.01 |  |  | B30 | no |  |
| `/Game/Levels/Halo1/Solo/B30/PCG/PLAs/Uluwatu/PLA_Uluwatu_Med_Screepile_B_BG_PCG` | PCGDataAsset | 0.01 |  |  | B30 | no |  |
| `/Game/Levels/Halo1/Solo/B30/PCG/PLAs/Uluwatu/PLA_Uluwatu_Med_Screepile_B_PCG` | PCGDataAsset | 0.01 |  |  | B30 | no |  |
| `/Game/Levels/Halo1/Solo/B30/PCG/PLAs/Uluwatu/PLA_Uluwatu_Med_Screepile_B_Waterline` | LevelInstance | 0.01 |  |  | B30 | no |  |
| `/Game/Levels/Halo1/Solo/B30/PCG/PLAs/Uluwatu/PLA_Uluwatu_Med_Screepile_B_Waterline_BG` | LevelInstance | 0.01 |  |  | B30 | no |  |
| `/Game/Levels/Halo1/Solo/B30/PCG/PLAs/Uluwatu/PLA_Uluwatu_Med_Screepile_B_Waterline_BG_PCG` | PCGDataAsset | 0.01 |  |  | B30 | no |  |
| `/Game/Levels/Halo1/Solo/B30/PCG/PLAs/Uluwatu/PLA_Uluwatu_Med_Screepile_B_Waterline_PCG` | PCGDataAsset | 0.01 |  |  | B30 | no |  |
| `/Game/Levels/Halo1/Solo/B30/PCG/PLAs/Uluwatu/PLA_Uluwatu_Med_Screepile_C` | LevelInstance | 0.01 |  |  | B30 | no |  |
| `/Game/Levels/Halo1/Solo/B30/PCG/PLAs/Uluwatu/PLA_Uluwatu_Med_Screepile_C_BG` | LevelInstance | 0.01 |  |  | B30 | no |  |
| `/Game/Levels/Halo1/Solo/B30/PCG/PLAs/Uluwatu/PLA_Uluwatu_Med_Screepile_C_BG_PCG` | PCGDataAsset | 0.01 |  |  | B30 | no |  |
| `/Game/Levels/Halo1/Solo/B30/PCG/PLAs/Uluwatu/PLA_Uluwatu_Med_Screepile_C_PCG` | PCGDataAsset | 0.01 |  |  | B30 | no |  |
| `/Game/Levels/Halo1/Solo/B30/PCG/PLAs/Uluwatu/PLA_Uluwatu_Med_Screepile_C_Waterline` | LevelInstance | 0.01 |  |  | B30 | no |  |
| `/Game/Levels/Halo1/Solo/B30/PCG/PLAs/Uluwatu/PLA_Uluwatu_Med_Screepile_C_Waterline_BG` | LevelInstance | 0.01 |  |  | B30 | no |  |
| `/Game/Levels/Halo1/Solo/B30/PCG/PLAs/Uluwatu/PLA_Uluwatu_Med_Screepile_C_Waterline_BG_PCG` | PCGDataAsset | 0.01 |  |  | B30 | no |  |
| `/Game/Levels/Halo1/Solo/B30/PCG/PLAs/Uluwatu/PLA_Uluwatu_Med_Screepile_C_Waterline_PCG` | PCGDataAsset | 0.01 |  |  | B30 | no |  |
| `/Game/Levels/Halo1/Solo/B30/PCG/PLAs/Uluwatu/PLA_Uluwatu_Small_Screepile_D_BG` | LevelInstance | 0.01 |  |  | B30 | no |  |
| `/Game/Levels/Halo1/Solo/B30/PCG/PLAs/Uluwatu/PLA_Uluwatu_Small_Screepile_D_BG_PCG` | PCGDataAsset | 0.01 |  |  | B30 | no |  |
| `/Game/Levels/Halo1/Solo/B30/PCG/PLAs/Uluwatu/PLA_Uluwatu_Small_Screepile_E` | LevelInstance | 0.01 |  |  | B30 | no |  |
| `/Game/Levels/Halo1/Solo/B30/PCG/PLAs/Uluwatu/PLA_Uluwatu_Small_Screepile_E_BG` | LevelInstance | 0.01 |  |  | B30 | no |  |
| `/Game/Levels/Halo1/Solo/B30/PCG/PLAs/Uluwatu/PLA_Uluwatu_Small_Screepile_E_BG_PCG` | PCGDataAsset | 0.01 |  |  | B30 | no |  |
| `/Game/Levels/Halo1/Solo/B30/PCG/PLAs/Uluwatu/PLA_Uluwatu_Small_Screepile_E_PCG` | PCGDataAsset | 0.01 |  |  |  | no |  |

*Group note:* B30 Uluwatu scree piles with _Waterline variants and PLAY_*_CollisionMesh collision proxies; LI/PLA are packed level actors (recipe)

### B30 PCG biome recipe (40)

*Where on PWR:* Reference: how B30 scatters grass, shrubs and ivy by landscape layer

| path | kind | MB | verts | bounds m | levels | PWR | note |
|---|---|---|---|---|---|---|---|
| `/Game/Levels/Halo1/Solo/B30/PCG/Catagories/DA_Grass_Wild_Catagory_B30` | DataAsset | 0.00 |  |  |  | no |  |
| `/Game/Levels/Halo1/Solo/B30/PCG/Catagories/DA_Ivy_Catagory_B30` | DataAsset | 0.00 |  |  |  | no |  |
| `/Game/Levels/Halo1/Solo/B30/PCG/Catagories/DA_MediumFoliage_Dry_Catagory_B30` | DataAsset | 0.00 |  |  |  | no |  |
| `/Game/Levels/Halo1/Solo/B30/PCG/Catagories/DA_Shrubbery_Catagory_B30` | DataAsset | 0.00 |  |  |  | no |  |
| `/Game/Levels/Halo1/Solo/B30/PCG/Catagories/DA_TidePools_Category_B30` | DataAsset | 0.00 |  |  |  | no |  |
| `/Game/Levels/Halo1/Solo/B30/PCG/Catagories/Playerscale/DA_Grass_PlayerScale_Wild_Catagory_B30` | DataAsset | 0.00 |  |  |  | no |  |
| `/Game/Levels/Halo1/Solo/B30/PCG/Catagories/Playerscale/DA_Ivy_PlayerScale_Catagory_B30` | DataAsset | 0.00 |  |  |  | no |  |
| `/Game/Levels/Halo1/Solo/B30/PCG/Catagories/Playerscale/DA_PlayerScale_MediumFoliage_CenterIsland_Catagory_B30` | DataAsset | 0.00 |  |  |  | no |  |
| `/Game/Levels/Halo1/Solo/B30/PCG/Catagories/Playerscale/DA_PlayerScale_MediumFoliage_Dry_Catagory_B30` | DataAsset | 0.00 |  |  |  | no |  |
| `/Game/Levels/Halo1/Solo/B30/PCG/Catagories/Playerscale/DA_PlayerScale_TidePools_Catagory_B30` | DataAsset | 0.00 |  |  |  | no |  |
| `/Game/Levels/Halo1/Solo/B30/PCG/DA_BiomeSettings_B30` | DataAsset | 0.00 |  |  | B30 | no |  |
| `/Game/Levels/Halo1/Solo/B30/PCG/DA_CliffOverrides` | DataAsset | 0.00 |  |  | B30 | no |  |
| `/Game/Levels/Halo1/Solo/B30/PCG/DA_CliffOverridesTesting` | DataAsset | 0.00 |  |  | B30 | no |  |
| `/Game/Levels/Halo1/Solo/B30/PCG/DA_LandscapeLayerPCGSettings_B30` | DataAsset | 0.00 |  |  |  | no |  |
| `/Game/Levels/Halo1/Solo/B30/PCG/IndividualSpawnables/DA_SpawnableGrass_Wild_B30` | DataAsset | 0.00 |  |  |  | no |  |
| `/Game/Levels/Halo1/Solo/B30/PCG/IndividualSpawnables/DA_SpawnableIvy_Ivy_B30` | DataAsset | 0.00 |  |  |  | no |  |
| `/Game/Levels/Halo1/Solo/B30/PCG/IndividualSpawnables/DA_SpawnableShrubbery_DownyWillow_B30` | DataAsset | 0.00 |  |  |  | no |  |
| `/Game/Levels/Halo1/Solo/B30/PCG/IndividualSpawnables/DA_SpawnableShrubbery_Myricaria_B30` | DataAsset | 0.00 |  |  |  | no |  |
| `/Game/Levels/Halo1/Solo/B30/PCG/IndividualSpawnables/DA_SpawnableShrubbery_Rhazya_B30` | DataAsset | 0.00 |  |  |  | no |  |
| `/Game/Levels/Halo1/Solo/B30/PCG/IndividualSpawnables/DA_SpawnableShrubbery_YellowRabbitBrush_B30` | DataAsset | 0.00 |  |  |  | no |  |
| `/Game/Levels/Halo1/Solo/B30/PCG/IndividualSpawnables/DA_Spawnable_MediumFoliage_DwarfBirch_B30` | DataAsset | 0.00 |  |  |  | no |  |
| `/Game/Levels/Halo1/Solo/B30/PCG/IndividualSpawnables/DA_Spawnable_MediumFoliage_Ferns_B30` | DataAsset | 0.00 |  |  |  | no |  |
| `/Game/Levels/Halo1/Solo/B30/PCG/IndividualSpawnables/Playerscale/DA_Spawnabl_PlayerScale_eShrubbery_Myricaria_B30` | DataAsset | 0.00 |  |  |  | no |  |
| `/Game/Levels/Halo1/Solo/B30/PCG/IndividualSpawnables/Playerscale/DA_SpawnableGrass_PlayerScale_Sea_Campion_B30` | DataAsset | 0.00 |  |  |  | no |  |
| `/Game/Levels/Halo1/Solo/B30/PCG/IndividualSpawnables/Playerscale/DA_SpawnableGrass_PlayerScale_Wild_B30` | DataAsset | 0.00 |  |  |  | no |  |
| `/Game/Levels/Halo1/Solo/B30/PCG/IndividualSpawnables/Playerscale/DA_SpawnableIvy_Ivy_PlayerScale_B30` | DataAsset | 0.00 |  |  |  | no |  |
| `/Game/Levels/Halo1/Solo/B30/PCG/IndividualSpawnables/Playerscale/DA_SpawnableShrubbery_PlayerScale_Rhazya_B31` | DataAsset | 0.00 |  |  |  | no |  |
| `/Game/Levels/Halo1/Solo/B30/PCG/IndividualSpawnables/Playerscale/DA_SpawnableShrubbery_PlayerScale_YellowRabbitBrush_B30` | DataAsset | 0.00 |  |  |  | no |  |
| `/Game/Levels/Halo1/Solo/B30/PCG/IndividualSpawnables/Playerscale/DA_Spawnable_PlayerScale_Anenomes_B30` | DataAsset | 0.00 |  |  |  | no |  |
| `/Game/Levels/Halo1/Solo/B30/PCG/IndividualSpawnables/Playerscale/DA_Spawnable_PlayerScale_MediumFoliage_DwarfBirch_B30` | DataAsset | 0.00 |  |  |  | no |  |
| `/Game/Levels/Halo1/Solo/B30/PCG/IndividualSpawnables/Playerscale/DA_Spawnable_PlayerScale_MediumFoliage_Ferns_B30` | DataAsset | 0.00 |  |  |  | no |  |
| `/Game/Levels/Halo1/Solo/B30/PCG/IndividualSpawnables/Playerscale/DA_Spawnable_PlayerScale_Shrubbery_DownyWillow_B31` | DataAsset | 0.00 |  |  |  | no |  |
| `/Game/Levels/Halo1/Solo/B30/PCG/MeshProperties/DA_MeshProperties_Large_B30` | DataAsset | 0.00 |  |  |  | no |  |
| `/Game/Levels/Halo1/Solo/B30/PCG/MeshProperties/DA_MeshProperties_Medium_B30` | DataAsset | 0.00 |  |  |  | no |  |
| `/Game/Levels/Halo1/Solo/B30/PCG/MeshProperties/DA_MeshProperties_Small_B30` | DataAsset | 0.00 |  |  |  | no |  |
| `/Game/Levels/Halo1/Solo/B30/PCG/ScatterVolumes/MeshProperties/DA_MeshProperties_B30_Vines` | DataAsset | 0.00 |  |  |  | no |  |
| `/Game/Levels/Halo1/Solo/B30/PCG/ScatterVolumes/ScatterParents/BP_ScatterVolume_B30_Bushes` | Blueprint | 0.00 |  |  | B30 | no |  |
| `/Game/Levels/Halo1/Solo/B30/PCG/ScatterVolumes/ScatterParents/BP_ScatterVolume_B30_Bushes_DownyWillow` | Blueprint | 0.00 |  |  | B30 | no |  |
| `/Game/Levels/Halo1/Solo/B30/PCG/ScatterVolumes/ScatterParents/BP_ScatterVolume_B30_Bushes_DwarfBirch` | Blueprint | 0.00 |  |  | B30 | no |  |
| `/Game/Levels/Halo1/Solo/B30/PCG/ScatterVolumes/ScatterParents/BP_ScatterVolume_B30_Vines` | Blueprint | 0.00 |  |  | A30,B30 | no |  |

*Group note:* B30 PCG data assets (biome, categories, spawnables)

### Shore boulders and beach rocks (Megascans 3D) (65)

*Where on PWR:* Lake shores, rocky points and the reservoir dam toe

| path | kind | MB | verts | bounds m | levels | PWR | note |
|---|---|---|---|---|---|---|---|
| `/Game/Megascans/3D_Assets/Beach_Boulder_uisjbbis/MI_Beach_Boulder_uisjbbis_8K` | MaterialInstance | 0.00 |  |  | B40,C45 | no |  |
| `/Game/Megascans/3D_Assets/Beach_Boulder_uisjbbis/MI_Rock_Glacial_Beach_Boulder` | MaterialInstance | 0.00 |  |  | B40,C45 | no |  |
| `/Game/Megascans/3D_Assets/Beach_Boulder_uisjbbis/S_Beach_Boulder_uisjbbis_high` | StaticMesh | 1.22 | 26,363 | 1.2x0.79x0.53 | B40,C45 | no |  |
| `/Game/Megascans/3D_Assets/Beach_Boulder_wenobdn/MI_Beach_Boulder_wenobdn_8K` | MaterialInstance | 0.00 |  |  | B40,C45 | no |  |
| `/Game/Megascans/3D_Assets/Beach_Boulder_wenobdn/S_Beach_Boulder_wenobdn_high_Var1` | StaticMesh | 6.03 | 153,737 | 1.0x0.41x0.51 | B40,C45 | no |  |
| `/Game/Megascans/3D_Assets/Beach_Rock_Small_wdribhj/MI_Beach_Rock_Small_wdribhj_4K` | MaterialInstance | 0.00 |  |  |  | no |  |
| `/Game/Megascans/3D_Assets/Beach_Rock_Small_wdribhj/S_Beach_Rock_Small_wdribhj_lod0_Var1` | StaticMesh | 0.37 | 3,046 | 0.16x0.14x0.05 |  | no |  |
| `/Game/Megascans/3D_Assets/Beach_Rock_wenobjws/MIP_Rock_Glacial_BeachRock_wenobjws` | MaterialInstance | 0.09 |  |  | B40,C45 | no |  |
| `/Game/Megascans/3D_Assets/Beach_Rock_wenobjws/MI_Beach_Rock_wenobjws_8K` | MaterialInstance | 0.00 |  |  | B40,C45 | no |  |
| `/Game/Megascans/3D_Assets/Beach_Rock_wenobjws/S_Beach_Rock_wenobjws_high_Var1` | StaticMesh | 16.07 | 439,732 | 0.66x0.55x0.36 | B40,C45 | no | very dense: confirm Nanite before placing many |
| `/Game/Megascans/3D_Assets/Coral_Stone_wfcmegzr/MI_Coral_Stone_wfcmegzr_4K` | MaterialInstance | 0.00 |  |  | B30 | no | off-setting (tropical/alien/marine) [setting] |
| `/Game/Megascans/3D_Assets/Coral_Stone_wfcmegzr/S_Coral_Stone_wfcmegzr_lod0_Var1` | StaticMesh | 0.10 | 777 | 0.2x0.12x0.06 | B30 | no | off-setting (tropical/alien/marine) [setting] |
| `/Game/Megascans/3D_Assets/NordicBeachRocks/MI_NordicBeachRocks_01` | MaterialInstance | 0.03 |  |  | C10 | no |  |
| `/Game/Megascans/3D_Assets/NordicBeachRocks/SM_NordicBeachRocks_01` | StaticMesh | 15.15 | 516,219 | 5.76x3.56x2.36 | C10 | no | very dense: confirm Nanite before placing many |
| `/Game/Megascans/3D_Assets/NordicBeachRockyGround/SM_NordicBeachRockyGround_02` | StaticMesh | 3.15 | 77,469 | 3.51x3.43x0.24 | B40,C10,C45 | no |  |
| `/Game/Megascans/3D_Assets/Nordic_Beach_Rock_Formation_vckqccbga/MI_Nordic_Beach_Rock_Formation_vckqccbga_Raw` | MaterialInstance | 0.00 |  |  | B40,C45 | no |  |
| `/Game/Megascans/3D_Assets/Nordic_Beach_Rock_Formation_vckqccbga/nordic_beach_rock_formation_vckqccbga_raw1` | StaticMesh | 2.10 |  |  | B40,C45 | no |  |
| `/Game/Megascans/3D_Assets/Nordic_Beach_Rock_Formation_vd4iahpga/MI_Nordic_Beach_Rock_Formation_vd4iahpga_8K` | MaterialInstance | 0.00 |  |  | B40,C45 | no |  |
| `/Game/Megascans/3D_Assets/Nordic_Beach_Rock_Formation_vd4iahpga/S_Nordic_Beach_Rock_Formation_vd4iahpga_high_Var1` | StaticMesh | 15.52 | 516,629 | 7.65x4.72x1.13 | B40,C45 | no | very dense: confirm Nanite before placing many |
| `/Game/Megascans/3D_Assets/Nordic_Beach_Rock_Formation_vfgkajyga/MI_Nordic_Beach_Rock_Formation_vfgkajyga_8K` | MaterialInstance | 0.00 |  |  | B40,C45 | no |  |
| `/Game/Megascans/3D_Assets/Nordic_Beach_Rock_Formation_vfgkajyga/S_Nordic_Beach_Rock_Formation_vfgkajyga_high_Var1` | StaticMesh | 4.79 | 139,459 | 12.48x7.21x3.06 | B40,C45 | no |  |
| `/Game/Megascans/3D_Assets/Nordic_Beach_Rock_uk3nceuva/Preview/MI_Nordic_Beach_Rock_uk3nceuva_1K` | MaterialInstance | 0.00 |  |  | E20 | no |  |
| `/Game/Megascans/3D_Assets/Nordic_Beach_Rock_uk3nceuva/Preview/S_Nordic_Beach_Rock_uk3nceuva_lod5_Var1` | StaticMesh | 0.06 | 321 | 1.1x1.15x0.88 | E20 | no |  |
| `/Game/Megascans/3D_Assets/Nordic_Beach_Rock_uk3ndfyga/MI_Nordic_Beach_Rock_uk3ndfyga_8K` | MaterialInstance | 0.00 |  |  | B40,C45,E20 | no |  |
| `/Game/Megascans/3D_Assets/Nordic_Beach_Rock_uk3ndfyga/MI_Rock_Glacial_Beach_Rock_uk3ndfyga` | MaterialInstance | 0.00 |  |  | B40,C45 | no |  |
| `/Game/Megascans/3D_Assets/Nordic_Beach_Rock_uk3ndfyga/S_Nordic_Beach_Rock_uk3ndfyga_high_Var1` | StaticMesh | 4.32 | 102,762 | 1.27x1.3x1.45 | B40,C45,E20 | no |  |
| `/Game/Megascans/3D_Assets/Nordic_Beach_Rock_vbumba2fa/MI_Nordic_Beach_Rock_` | MaterialInstance | 0.14 |  |  | A30 | no |  |
| `/Game/Megascans/3D_Assets/Nordic_Beach_Rock_vbumba2fa/SM_Nordic_Beach_Rock_vbumba2fa` | StaticMesh | 0.09 | 2,128 | 0.47x0.47x0.19 | A30 | no |  |
| `/Game/Megascans/3D_Assets/Nordic_Beach_Rock_vgjidiqmw/MI_Nordic_Beach_Rock_vgjidiqmw_4K` | MaterialInstance | 0.00 |  |  | A30 | no |  |
| `/Game/Megascans/3D_Assets/Nordic_Beach_Rock_vgjidiqmw/MI_Nordic_Beach_Rock_vgjidiqmw_lod0_Var1` | MaterialInstance | 0.12 |  |  | A30 | no |  |
| `/Game/Megascans/3D_Assets/Nordic_Beach_Rock_vgjidiqmw/S_Nordic_Beach_Rock_vgjidiqmw_lod0_Var1` | StaticMesh | 0.32 | 3,404 | 0.32x0.24x0.12 | A30 | no |  |
| `/Game/Megascans/3D_Assets/Nordic_Beach_Rock_vgjjdb1mw/MI_Nordic_Beach_Rock_vgjjdb1mw_4K` | MaterialInstance | 0.00 |  |  |  | no |  |
| `/Game/Megascans/3D_Assets/Nordic_Beach_Rock_vgjjdb1mw/S_Nordic_Beach_Rock_vgjjdb1mw_lod0_Var1` | StaticMesh | 0.21 | 3,208 | 0.22x0.16x0.12 |  | no |  |
| `/Game/Megascans/3D_Assets/Nordic_Beach_Rocks_vepkcelqx/MI_Nordic_Beach_Rocks_vepkcelqx_8K` | MaterialInstance | 0.12 |  |  | B30 | no |  |
| `/Game/Megascans/3D_Assets/Nordic_Beach_Rocks_vepkcelqx/S_Nordic_Beach_Rocks_vepkcelqx_high_Var1` | StaticMesh | 15.57 | 505,655 | 6.2x3.55x2.42 | B30 | no | very dense: confirm Nanite before placing many |
| `/Game/Megascans/3D_Assets/Nordic_Beach_Rocky_Ground_uknmbblmw/MI_Nordic_Beach_Rocky_Ground_uknmbblmw_8K` | MaterialInstance | 0.00 |  |  | E20 | no |  |
| `/Game/Megascans/3D_Assets/Nordic_Beach_Rocky_Ground_uknmbblmw/S_Nordic_Beach_Rocky_Ground_uknmbblmw_high_Var1` | StaticMesh | 5.65 | 162,960 | 8.65x4.56x1.4 | E20 | no |  |
| `/Game/Megascans/3D_Assets/Nordic_Beach_Rocky_Ground_ukohbbi/MI_Nordic_Beach_Rocky_Ground_ukohbbi_4K` | MaterialInstance | 0.00 |  |  | B30 | no |  |
| `/Game/Megascans/3D_Assets/Nordic_Beach_Rocky_Ground_ukohbbi/S_Nordic_Beach_Rocky_Ground_ukohbbi_lod0` | StaticMesh | 2.17 | 12,887 | 1.73x1.4x0.11 | B30 | no |  |
| `/Game/Megascans/3D_Assets/Nordic_Beach_Rocky_Ground_ukoncdamw/MI_Nordic_Beach_Rocky_Ground_ukoncdamw_8K` | MaterialInstance | 0.12 |  |  | B40,C45 | no |  |
| `/Game/Megascans/3D_Assets/Nordic_Beach_Rocky_Ground_ukoncdamw/S_Nordic_Beach_Rocky_Ground_ukoncdamw_high_Var1_Convex` | StaticMesh | 3.42 | 104,707 | 3.67x3.6x0.57 | B40,C45 | no |  |
| `/Game/Megascans/3D_Assets/Nordic_Beach_Rocky_Ground_ve3qdhmqx/MI_Nordic_Beach_Rocky_Ground_ve3qdhmqx_8K` | MaterialInstance | 0.12 |  |  | B40,C10,C45 | no |  |
| `/Game/Megascans/3D_Assets/Nordic_Beach_Rocky_Ground_ve3qdhmqx/MI_Nordic_Beach_Rocky_Ground_ve3qdhmqx_8K_Wet` | MaterialInstance | 0.08 |  |  | C10 | no | wet variant |
| `/Game/Megascans/3D_Assets/Nordic_Beach_Rocky_Ground_ve3qdhmqx/S_Nordic_Beach_Rocky_Ground_Uluwata_B` | StaticMesh | 0.76 | 20,189 | 3.51x3.42x0.24 | B30,C10 | no |  |
| `/Game/Megascans/3D_Assets/Nordic_Beach_Rocky_Ground_ve3qdhmqx/S_Nordic_Beach_Rocky_Ground_ve3qdhmqx_high_Var1` | StaticMesh | 2.38 | 72,614 | 3.51x3.43x0.24 | B40,C10,C45 | no |  |
| `/Game/Megascans/3D_Assets/Nordic_Beach_Rocky_Ground_vefhef2ga/MI_Nordic_Beach_Rocky_Ground_vefhef2ga_8K` | MaterialInstance | 0.03 |  |  | C10 | no |  |
| `/Game/Megascans/3D_Assets/Nordic_Beach_Rocky_Ground_vefhef2ga/S_Nordic_Beach_Rocky_Ground_vefhef2ga_high_Var1` | StaticMesh | 0.11 | 3,225 | 5.92x5.44x0.62 | C10 | no |  |
| `/Game/Megascans/3D_Assets/Small_Beach_Rock_wd2ocdo/MI_Small_Beach_Rock_wd2ocdo_8K` | MaterialInstance | 0.00 |  |  | B30 | no |  |
| `/Game/Megascans/3D_Assets/Small_Beach_Rock_wd2ocdo/S_Small_Beach_Rock_wd2ocdo_high` | StaticMesh | 0.15 | 1,393 | 0.2x0.23x0.11 | B30 | no |  |
| `/Game/Megascans/3D_Assets/Small_Beach_Rock_wd2ocdo/S_Small_Beach_Rock_wd2ocdo_high_Snow` | StaticMesh | 0.15 | 1,393 | 0.2x0.23x0.11 | B40,C45 | no | snow variant |
| `/Game/Megascans/3D_Assets/Small_Beach_Rock_wd2ocdo/S_Small_Beach_Rock_wd2ocdo_high_Snow_FoliageType` | FoliageType | 0.00 |  |  | B40,C45 | no | snow variant |
| `/Game/Megascans/3D_Assets/Small_Beach_Rock_wd3nech/MI_Small_Beach_Rock_wd3nech_4K` | MaterialInstance | 0.00 |  |  | B30 | no | sibling used by PWR |
| `/Game/Megascans/3D_Assets/Small_Beach_Rock_wd3nech/S_Small_Beach_Rock_wd3nech_lod0_Var1` | StaticMesh | 0.12 | 781 | 0.2x0.09x0.08 | B30 | yes |  |
| `/Game/Megascans/3D_Assets/Small_Beach_Rock_wd5mfgo/MI_Small_Beach_Rock_wd5mfgo_8K` | MaterialInstance | 0.00 |  |  | B30 | no |  |
| `/Game/Megascans/3D_Assets/Small_Beach_Rock_wd5mfgo/S_Small_Beach_Rock_wd5mfgo_high_Var1` | StaticMesh | 0.23 | 2,176 | 0.24x0.14x0.08 | B30 | no |  |
| `/Game/Megascans/3D_Assets/Small_Beach_Rock_wd5nfa1/MI_Small_Beach_Rock_wd5nfa1_8K` | MaterialInstance | 0.00 |  |  | B30 | no | sibling used by PWR |
| `/Game/Megascans/3D_Assets/Small_Beach_Rock_wd5nfa1/S_Small_Beach_Rock_wd5nfa1_high` | StaticMesh | 0.13 | 1,525 | 0.26x0.16x0.11 | B30 | yes |  |
| `/Game/Megascans/3D_Assets/Small_Beach_Rock_webhcal/MI_Small_Beach_Rock_webhcal_8K` | MaterialInstance | 0.00 |  |  | B30 | no |  |
| `/Game/Megascans/3D_Assets/Small_Beach_Rock_webhcal/S_Small_Beach_Rock_webhcal_high_Var1` | StaticMesh | 0.08 | 797 | 0.19x0.12x0.05 | B30 | no |  |
| `/Game/Megascans/3D_Assets/Small_Beach_Rock_webhcal/S_Small_Beach_Rock_webhcal_high_Var1_Snow` | StaticMesh | 0.08 | 797 | 0.19x0.12x0.05 | B40,C45 | no | snow variant |
| `/Game/Megascans/3D_Assets/Small_Beach_Rock_webhcal/S_Small_Beach_Rock_webhcal_high_Var1_Snow_FoliageType` | FoliageType | 0.00 |  |  | B40,C45 | no | snow variant |
| `/Game/Megascans/3D_Assets/Small_Beach_Rock_wfbscavr/MI_Small_Beach_Rock_wfbscavr_4K` | MaterialInstance | 0.00 |  |  | B30 | no | sibling used by PWR |
| `/Game/Megascans/3D_Assets/Small_Beach_Rock_wfbscavr/S_Small_Beach_Rock_wfbscavr_lod0_Var1` | StaticMesh | 0.08 | 781 | 0.22x0.13x0.08 | B30 | yes |  |
| `/Game/Megascans/3D_Assets/Small_Beach_Rock_wfcpeggr/MI_Small_Beach_Rock_wfcpeggr_4K` | MaterialInstance | 0.00 |  |  | B30 | no | sibling used by PWR |
| `/Game/Megascans/3D_Assets/Small_Beach_Rock_wfcpeggr/S_Small_Beach_Rock_wfcpeggr_lod0_Var1` | StaticMesh | 0.08 | 747 | 0.09x0.08x0.08 | B30 | yes |  |

*Group note:* Nordic/beach rock scans; several are used by B40 (snowy shore) under MI_Rock_Glacial_* instances. Coral_Stone is tropical (skip)

### Beach and dune grasses (Megascans plants) (101)

*Where on PWR:* Sandy lake shore and dry banks

| path | kind | MB | verts | bounds m | levels | PWR | note |
|---|---|---|---|---|---|---|---|
| `/Game/Megascans/3D_Plants/Dune_Sword-sedge_ueyoebmia/Foliage/FT_Dune_Sword-sedge_ueyoebmia_0_Var10_lod0` | FoliageType | 0.00 |  |  | B30 | no | [foliage] |
| `/Game/Megascans/3D_Plants/Dune_Sword-sedge_ueyoebmia/Foliage/FT_Dune_Sword-sedge_ueyoebmia_0_Var1_lod0` | FoliageType | 0.00 |  |  | B30 | no | [foliage] |
| `/Game/Megascans/3D_Plants/Dune_Sword-sedge_ueyoebmia/Foliage/FT_Dune_Sword-sedge_ueyoebmia_0_Var2_lod0` | FoliageType | 0.00 |  |  | B30 | no | [foliage] |
| `/Game/Megascans/3D_Plants/Dune_Sword-sedge_ueyoebmia/Foliage/FT_Dune_Sword-sedge_ueyoebmia_0_Var3_lod0` | FoliageType | 0.00 |  |  | B30 | no | [foliage] |
| `/Game/Megascans/3D_Plants/Dune_Sword-sedge_ueyoebmia/Foliage/FT_Dune_Sword-sedge_ueyoebmia_0_Var4_lod0` | FoliageType | 0.00 |  |  | B30 | no | [foliage] |
| `/Game/Megascans/3D_Plants/Dune_Sword-sedge_ueyoebmia/Foliage/FT_Dune_Sword-sedge_ueyoebmia_0_Var5_lod0` | FoliageType | 0.00 |  |  | B30 | no | [foliage] |
| `/Game/Megascans/3D_Plants/Dune_Sword-sedge_ueyoebmia/Foliage/FT_Dune_Sword-sedge_ueyoebmia_0_Var6_lod0` | FoliageType | 0.00 |  |  | B30 | no | [foliage] |
| `/Game/Megascans/3D_Plants/Dune_Sword-sedge_ueyoebmia/Foliage/FT_Dune_Sword-sedge_ueyoebmia_0_Var7_lod0` | FoliageType | 0.00 |  |  | B30 | no | [foliage] |
| `/Game/Megascans/3D_Plants/Dune_Sword-sedge_ueyoebmia/Foliage/FT_Dune_Sword-sedge_ueyoebmia_0_Var8_lod0` | FoliageType | 0.00 |  |  | B30 | no | [foliage] |
| `/Game/Megascans/3D_Plants/Dune_Sword-sedge_ueyoebmia/Foliage/FT_Dune_Sword-sedge_ueyoebmia_0_Var9_lod0` | FoliageType | 0.00 |  |  |  | no | [foliage] |
| `/Game/Megascans/3D_Plants/Dune_Sword-sedge_ueyoebmia/MI_Dune_Sword-sedge_ueyoebmia_8K` | MaterialInstance | 0.05 |  |  | B30,C10 | no | [foliage] |
| `/Game/Megascans/3D_Plants/Dune_Sword-sedge_ueyoebmia/S_Dune_Sword-sedge_ueyoebmia_0_Var10_lod0` | StaticMesh | 0.50 | 6,819 | 0.49x0.51x0.38 | B30,C10 | no | [foliage] |
| `/Game/Megascans/3D_Plants/Dune_Sword-sedge_ueyoebmia/S_Dune_Sword-sedge_ueyoebmia_0_Var1_lod0` | StaticMesh | 0.08 | 532 | 0.15x0.15x0.18 | B30 | no | [foliage] |
| `/Game/Megascans/3D_Plants/Dune_Sword-sedge_ueyoebmia/S_Dune_Sword-sedge_ueyoebmia_0_Var2_lod0` | StaticMesh | 0.26 | 2,586 | 0.4x0.38x0.38 | B30 | no | [foliage] |
| `/Game/Megascans/3D_Plants/Dune_Sword-sedge_ueyoebmia/S_Dune_Sword-sedge_ueyoebmia_0_Var3_lod0` | StaticMesh | 0.17 | 1,244 | 0.25x0.27x0.25 | B30 | no | [foliage] |
| `/Game/Megascans/3D_Plants/Dune_Sword-sedge_ueyoebmia/S_Dune_Sword-sedge_ueyoebmia_0_Var4_lod0` | StaticMesh | 0.22 | 1,799 | 0.21x0.28x0.32 | B30 | no | [foliage] |
| `/Game/Megascans/3D_Plants/Dune_Sword-sedge_ueyoebmia/S_Dune_Sword-sedge_ueyoebmia_0_Var5_lod0` | StaticMesh | 0.23 | 2,247 | 0.22x0.22x0.41 | B30 | no | [foliage] |
| `/Game/Megascans/3D_Plants/Dune_Sword-sedge_ueyoebmia/S_Dune_Sword-sedge_ueyoebmia_0_Var6_lod0` | StaticMesh | 0.15 | 1,087 | 0.27x0.28x0.41 | B30 | no | [foliage] |
| `/Game/Megascans/3D_Plants/Dune_Sword-sedge_ueyoebmia/S_Dune_Sword-sedge_ueyoebmia_0_Var7_lod0` | StaticMesh | 0.19 | 1,305 | 0.29x0.26x0.32 | B30 | no | [foliage] |
| `/Game/Megascans/3D_Plants/Dune_Sword-sedge_ueyoebmia/S_Dune_Sword-sedge_ueyoebmia_0_Var8_lod0` | StaticMesh | 0.47 | 5,376 | 0.42x0.38x0.46 | B30,C10 | no | [foliage] |
| `/Game/Megascans/3D_Plants/Dune_Sword-sedge_ueyoebmia/S_Dune_Sword-sedge_ueyoebmia_0_Var9_lod0` | StaticMesh | 0.53 | 5,836 | 0.39x0.4x0.47 |  | no | [foliage] |
| `/Game/Megascans/3D_Plants/Ribbon_Grass_tbdpec3r/Foliage/FT_Ribbon_Grass_tbdpec3r_Var1_lod0` | FoliageType | 0.00 |  |  |  | no | [foliage] |
| `/Game/Megascans/3D_Plants/Ribbon_Grass_tbdpec3r/Foliage/FT_Ribbon_Grass_tbdpec3r_Var2_lod0` | FoliageType | 0.00 |  |  | B30 | no | [foliage] |
| `/Game/Megascans/3D_Plants/Ribbon_Grass_tbdpec3r/Foliage/FT_Ribbon_Grass_tbdpec3r_Var3_lod0` | FoliageType | 0.00 |  |  | B30 | no | [foliage] |
| `/Game/Megascans/3D_Plants/Ribbon_Grass_tbdpec3r/Foliage/FT_Ribbon_Grass_tbdpec3r_Var4_lod0` | FoliageType | 0.00 |  |  | B30 | no | [foliage] |
| `/Game/Megascans/3D_Plants/Ribbon_Grass_tbdpec3r/Foliage/FT_Ribbon_Grass_tbdpec3r_Var5_lod0` | FoliageType | 0.00 |  |  |  | no | [foliage] |
| `/Game/Megascans/3D_Plants/Ribbon_Grass_tbdpec3r/Foliage/FT_Ribbon_Grass_tbdpec3r_Var6_lod0` | FoliageType | 0.00 |  |  |  | no | [foliage] |
| `/Game/Megascans/3D_Plants/Ribbon_Grass_tbdpec3r/MI_Ribbon_Grass_tbdpec3r_4K` | MaterialInstance | 0.05 |  |  | B30,C10 | no | [foliage] |
| `/Game/Megascans/3D_Plants/Ribbon_Grass_tbdpec3r/MI_Ribbon_Grass_tbdpec3r_Billboard_4K` | MaterialInstance | 0.00 |  |  | B30,C10 | no | [foliage] |
| `/Game/Megascans/3D_Plants/Ribbon_Grass_tbdpec3r/S_Ribbon_Grass_tbdpec3r_Var1_lod0` | StaticMesh | 0.26 | 2,102 | 0.71x0.73x0.54 |  | no | [foliage] |
| `/Game/Megascans/3D_Plants/Ribbon_Grass_tbdpec3r/S_Ribbon_Grass_tbdpec3r_Var2_lod0` | StaticMesh | 0.21 | 1,380 | 0.53x0.63x0.45 | B30 | no | [foliage] |
| `/Game/Megascans/3D_Plants/Ribbon_Grass_tbdpec3r/S_Ribbon_Grass_tbdpec3r_Var3_lod0` | StaticMesh | 0.22 | 1,211 | 0.6x0.52x0.37 | B30 | no | [foliage] |
| `/Game/Megascans/3D_Plants/Ribbon_Grass_tbdpec3r/S_Ribbon_Grass_tbdpec3r_Var4_lod0` | StaticMesh | 0.22 | 1,036 | 0.44x0.48x0.36 | B30 | no | [foliage] |
| `/Game/Megascans/3D_Plants/Ribbon_Grass_tbdpec3r/S_Ribbon_Grass_tbdpec3r_Var5_lod0` | StaticMesh | 0.24 | 2,066 | 0.34x0.29x0.29 | C10 | no | [foliage] |
| `/Game/Megascans/3D_Plants/Ribbon_Grass_tbdpec3r/S_Ribbon_Grass_tbdpec3r_Var6_lod0` | StaticMesh | 0.16 | 1,181 | 0.31x0.34x0.2 |  | no | [foliage] |
| `/Game/Megascans/3D_Plants/Sea_Campion_vkblbbpia/Foliage/FT_Sea_Campion_vkblbbpia_Var10_lod0` | FoliageType | 0.00 |  |  | B30 | no | [foliage] |
| `/Game/Megascans/3D_Plants/Sea_Campion_vkblbbpia/Foliage/FT_Sea_Campion_vkblbbpia_Var11_lod0` | FoliageType | 0.00 |  |  | B30 | no | [foliage] |
| `/Game/Megascans/3D_Plants/Sea_Campion_vkblbbpia/MI_Sea_Campion_vkblbbpia_4K` | MaterialInstance | 0.05 |  |  | A30,B30 | no | [foliage] |
| `/Game/Megascans/3D_Plants/Sea_Campion_vkblbbpia/MI_Sea_Campion_vkblbbpia_Billboard_4K` | MaterialInstance | 0.03 |  |  | B30 | no | [foliage] |
| `/Game/Megascans/3D_Plants/Sea_Campion_vkblbbpia/S_Sea_Campion_vkblbbpia_Var10_lod0` | StaticMesh | 0.23 | 3,236 | 0.36x0.42x0.29 | B30 | no | [foliage] |
| `/Game/Megascans/3D_Plants/Sea_Campion_vkblbbpia/S_Sea_Campion_vkblbbpia_Var10_lod0_Traced` | StaticMesh | 1.37 | 23,419 | 0.36x0.43x0.29 | A30 | no | [foliage] |
| `/Game/Megascans/3D_Plants/Sea_Campion_vkblbbpia/S_Sea_Campion_vkblbbpia_Var11_lod0` | StaticMesh | 0.25 | 3,970 | 0.46x0.38x0.28 | B30 | no | [foliage] |
| `/Game/Megascans/3D_Plants/Sea_Campion_vkblbbpia/S_Sea_Campion_vkblbbpia_Var5_lod0_Traced` | StaticMesh | 0.92 | 17,203 | 0.22x0.28x0.25 | A30 | no | [foliage] |
| `/Game/Megascans/3D_Plants/Sea_Wheatgrass_ui2oagjia/Foliage/FT_Sea_Wheatgrass_ui2oagjia_0_Var10_lod0` | FoliageType | 0.00 |  |  |  | no | [foliage] |
| `/Game/Megascans/3D_Plants/Sea_Wheatgrass_ui2oagjia/Foliage/FT_Sea_Wheatgrass_ui2oagjia_0_Var11_lod0` | FoliageType | 0.00 |  |  | B30 | no | [foliage] |
| `/Game/Megascans/3D_Plants/Sea_Wheatgrass_ui2oagjia/Foliage/FT_Sea_Wheatgrass_ui2oagjia_0_Var12_lod0` | FoliageType | 0.00 |  |  |  | no | [foliage] |
| `/Game/Megascans/3D_Plants/Sea_Wheatgrass_ui2oagjia/Foliage/FT_Sea_Wheatgrass_ui2oagjia_0_Var13_lod0` | FoliageType | 0.00 |  |  |  | no | [foliage] |
| `/Game/Megascans/3D_Plants/Sea_Wheatgrass_ui2oagjia/Foliage/FT_Sea_Wheatgrass_ui2oagjia_0_Var14_lod0` | FoliageType | 0.00 |  |  |  | no | [foliage] |
| `/Game/Megascans/3D_Plants/Sea_Wheatgrass_ui2oagjia/Foliage/FT_Sea_Wheatgrass_ui2oagjia_0_Var15_lod0` | FoliageType | 0.00 |  |  | B30 | no | [foliage] |
| `/Game/Megascans/3D_Plants/Sea_Wheatgrass_ui2oagjia/Foliage/FT_Sea_Wheatgrass_ui2oagjia_0_Var16_lod0` | FoliageType | 0.00 |  |  |  | no | [foliage] |
| `/Game/Megascans/3D_Plants/Sea_Wheatgrass_ui2oagjia/Foliage/FT_Sea_Wheatgrass_ui2oagjia_0_Var17_lod0` | FoliageType | 0.00 |  |  |  | no | [foliage] |
| `/Game/Megascans/3D_Plants/Sea_Wheatgrass_ui2oagjia/Foliage/FT_Sea_Wheatgrass_ui2oagjia_0_Var18_lod0` | FoliageType | 0.00 |  |  |  | no | [foliage] |
| `/Game/Megascans/3D_Plants/Sea_Wheatgrass_ui2oagjia/Foliage/FT_Sea_Wheatgrass_ui2oagjia_0_Var19_lod0` | FoliageType | 0.00 |  |  |  | no | [foliage] |
| `/Game/Megascans/3D_Plants/Sea_Wheatgrass_ui2oagjia/Foliage/FT_Sea_Wheatgrass_ui2oagjia_0_Var1_lod0` | FoliageType | 0.00 |  |  | B30 | no | [foliage] |
| `/Game/Megascans/3D_Plants/Sea_Wheatgrass_ui2oagjia/Foliage/FT_Sea_Wheatgrass_ui2oagjia_0_Var20_lod0` | FoliageType | 0.00 |  |  |  | no | [foliage] |
| `/Game/Megascans/3D_Plants/Sea_Wheatgrass_ui2oagjia/Foliage/FT_Sea_Wheatgrass_ui2oagjia_0_Var21_lod0` | FoliageType | 0.00 |  |  |  | no | [foliage] |
| `/Game/Megascans/3D_Plants/Sea_Wheatgrass_ui2oagjia/Foliage/FT_Sea_Wheatgrass_ui2oagjia_0_Var22_lod0` | FoliageType | 0.00 |  |  |  | no | [foliage] |
| `/Game/Megascans/3D_Plants/Sea_Wheatgrass_ui2oagjia/Foliage/FT_Sea_Wheatgrass_ui2oagjia_0_Var2_lod0` | FoliageType | 0.00 |  |  |  | no | [foliage] |
| `/Game/Megascans/3D_Plants/Sea_Wheatgrass_ui2oagjia/Foliage/FT_Sea_Wheatgrass_ui2oagjia_0_Var3_lod0` | FoliageType | 0.00 |  |  |  | no | [foliage] |
| `/Game/Megascans/3D_Plants/Sea_Wheatgrass_ui2oagjia/Foliage/FT_Sea_Wheatgrass_ui2oagjia_0_Var4_lod0` | FoliageType | 0.00 |  |  |  | no | [foliage] |
| `/Game/Megascans/3D_Plants/Sea_Wheatgrass_ui2oagjia/Foliage/FT_Sea_Wheatgrass_ui2oagjia_0_Var5_lod0` | FoliageType | 0.00 |  |  |  | no | [foliage] |
| `/Game/Megascans/3D_Plants/Sea_Wheatgrass_ui2oagjia/Foliage/FT_Sea_Wheatgrass_ui2oagjia_0_Var6_lod0` | FoliageType | 0.00 |  |  |  | no | [foliage] |
| `/Game/Megascans/3D_Plants/Sea_Wheatgrass_ui2oagjia/Foliage/FT_Sea_Wheatgrass_ui2oagjia_0_Var7_lod0` | FoliageType | 0.00 |  |  |  | no | [foliage] |
| `/Game/Megascans/3D_Plants/Sea_Wheatgrass_ui2oagjia/Foliage/FT_Sea_Wheatgrass_ui2oagjia_0_Var8_lod0` | FoliageType | 0.00 |  |  |  | no | [foliage] |
| `/Game/Megascans/3D_Plants/Sea_Wheatgrass_ui2oagjia/Foliage/FT_Sea_Wheatgrass_ui2oagjia_0_Var9_lod0` | FoliageType | 0.00 |  |  | B30 | no | [foliage] |
| `/Game/Megascans/3D_Plants/Sea_Wheatgrass_ui2oagjia/MI_Sea_Wheatgrass_ui2oagjia_4K` | MaterialInstance | 0.00 |  |  | B30 | no | [foliage] |
| `/Game/Megascans/3D_Plants/Sea_Wheatgrass_ui2oagjia/MI_Sea_Wheatgrass_ui2oagjia_8K` | MaterialInstance | 0.00 |  |  | B30 | no | [foliage] |
| `/Game/Megascans/3D_Plants/Sea_Wheatgrass_ui2oagjia/MI_Sea_Wheatgrass_ui2oagjia_Billboard_4K` | MaterialInstance | 0.00 |  |  | B30 | no | [foliage] |
| `/Game/Megascans/3D_Plants/Sea_Wheatgrass_ui2oagjia/S_Sea_Wheatgrass_ui2oagjia_0_Var10_lod0` | StaticMesh | 0.02 | 106 | 0.2x0.1x0.36 |  | no | [foliage] |
| `/Game/Megascans/3D_Plants/Sea_Wheatgrass_ui2oagjia/S_Sea_Wheatgrass_ui2oagjia_0_Var11_lod0` | StaticMesh | 0.03 | 180 | 0.32x0.29x0.26 | B30 | no | [foliage] |
| `/Game/Megascans/3D_Plants/Sea_Wheatgrass_ui2oagjia/S_Sea_Wheatgrass_ui2oagjia_0_Var12_lod0` | StaticMesh | 0.20 | 1,746 | 0.57x0.61x0.8 |  | no | [foliage] |
| `/Game/Megascans/3D_Plants/Sea_Wheatgrass_ui2oagjia/S_Sea_Wheatgrass_ui2oagjia_0_Var13_lod0` | StaticMesh | 0.04 | 168 | 0.3x0.25x0.1 |  | no | [foliage] |
| `/Game/Megascans/3D_Plants/Sea_Wheatgrass_ui2oagjia/S_Sea_Wheatgrass_ui2oagjia_0_Var14_lod0` | StaticMesh | 0.05 | 258 | 0.31x0.57x0.22 |  | no | [foliage] |
| `/Game/Megascans/3D_Plants/Sea_Wheatgrass_ui2oagjia/S_Sea_Wheatgrass_ui2oagjia_0_Var15_lod0` | StaticMesh | 0.03 | 270 | 0.2x0.21x0.01 | B30 | no | [foliage] |
| `/Game/Megascans/3D_Plants/Sea_Wheatgrass_ui2oagjia/S_Sea_Wheatgrass_ui2oagjia_0_Var16_lod0` | StaticMesh | 0.08 | 494 | 0.51x0.55x0.68 |  | no | [foliage] |
| `/Game/Megascans/3D_Plants/Sea_Wheatgrass_ui2oagjia/S_Sea_Wheatgrass_ui2oagjia_0_Var17_lod0` | StaticMesh | 0.08 | 516 | 0.52x0.42x0.69 |  | no | [foliage] |
| `/Game/Megascans/3D_Plants/Sea_Wheatgrass_ui2oagjia/S_Sea_Wheatgrass_ui2oagjia_0_Var18_lod0` | StaticMesh | 0.08 | 500 | 0.42x0.46x0.64 |  | no | [foliage] |
| `/Game/Megascans/3D_Plants/Sea_Wheatgrass_ui2oagjia/S_Sea_Wheatgrass_ui2oagjia_0_Var19_lod0` | StaticMesh | 0.04 | 194 | 0.22x0.27x0.61 |  | no | [foliage] |
| `/Game/Megascans/3D_Plants/Sea_Wheatgrass_ui2oagjia/S_Sea_Wheatgrass_ui2oagjia_0_Var1_lod0` | StaticMesh | 0.26 | 2,410 | 0.59x0.86x0.91 | B30 | no | [foliage] |
| `/Game/Megascans/3D_Plants/Sea_Wheatgrass_ui2oagjia/S_Sea_Wheatgrass_ui2oagjia_0_Var20_lod0` | StaticMesh | 0.07 | 509 | 0.3x0.22x0.53 |  | no | [foliage] |
| `/Game/Megascans/3D_Plants/Sea_Wheatgrass_ui2oagjia/S_Sea_Wheatgrass_ui2oagjia_0_Var21_lod0` | StaticMesh | 0.07 | 504 | 0.17x0.2x0.46 |  | no | [foliage] |
| `/Game/Megascans/3D_Plants/Sea_Wheatgrass_ui2oagjia/S_Sea_Wheatgrass_ui2oagjia_0_Var22_lod0` | StaticMesh | 0.08 | 536 | 0.19x0.2x0.51 |  | no | [foliage] |
| `/Game/Megascans/3D_Plants/Sea_Wheatgrass_ui2oagjia/S_Sea_Wheatgrass_ui2oagjia_0_Var2_lod0` | StaticMesh | 0.07 | 501 | 0.19x0.2x0.39 |  | no | [foliage] |
| `/Game/Megascans/3D_Plants/Sea_Wheatgrass_ui2oagjia/S_Sea_Wheatgrass_ui2oagjia_0_Var3_lod0` | StaticMesh | 0.07 | 402 | 0.32x0.3x0.37 |  | no | [foliage] |
| `/Game/Megascans/3D_Plants/Sea_Wheatgrass_ui2oagjia/S_Sea_Wheatgrass_ui2oagjia_0_Var4_lod0` | StaticMesh | 0.07 | 427 | 0.17x0.19x0.42 |  | no | [foliage] |
| `/Game/Megascans/3D_Plants/Sea_Wheatgrass_ui2oagjia/S_Sea_Wheatgrass_ui2oagjia_0_Var5_lod0` | StaticMesh | 0.06 | 334 | 0.11x0.11x0.34 |  | no | [foliage] |
| `/Game/Megascans/3D_Plants/Sea_Wheatgrass_ui2oagjia/S_Sea_Wheatgrass_ui2oagjia_0_Var6_lod0` | StaticMesh | 0.07 | 362 | 0.22x0.17x0.56 |  | no | [foliage] |
| `/Game/Megascans/3D_Plants/Sea_Wheatgrass_ui2oagjia/S_Sea_Wheatgrass_ui2oagjia_0_Var7_lod0` | StaticMesh | 0.05 | 228 | 0.22x0.36x0.43 |  | no | [foliage] |
| `/Game/Megascans/3D_Plants/Sea_Wheatgrass_ui2oagjia/S_Sea_Wheatgrass_ui2oagjia_0_Var8_lod0` | StaticMesh | 0.06 | 318 | 0.23x0.35x0.58 |  | no | [foliage] |
| `/Game/Megascans/3D_Plants/Sea_Wheatgrass_ui2oagjia/S_Sea_Wheatgrass_ui2oagjia_0_Var9_lod0` | StaticMesh | 0.03 | 180 | 0.24x0.27x0.32 | B30 | no | [foliage] |
| `/Game/Megascans/3D_Plants/Sea_Wheatgrass_ui2oagjia/S_Sea_Wheatgrass_ui2oagjia_Var1_lod0` | StaticMesh | 0.31 | 902 | 0.58x0.77x0.86 | B30 | no | [foliage] |
| `/Game/Megascans/3D_Plants/Thatching_Grass_uddmcgbia/MI_Thatching_Grass_uddmcgbia_4K` | MaterialInstance | 0.05 |  |  | B30,C10 | no | [foliage]; sibling used by PWR |
| `/Game/Megascans/3D_Plants/Thatching_Grass_uddmcgbia/MI_Thatching_Grass_uddmcgbia_4K_Dark` | MaterialInstance | 0.05 |  |  | C10 | no | [foliage]; sibling used by PWR |
| `/Game/Megascans/3D_Plants/Thatching_Grass_uddmcgbia/MI_Thatching_Grass_uddmcgbia_Billboard_4K` | MaterialInstance | 0.00 |  |  | B30,C10 | no | [foliage]; sibling used by PWR |
| `/Game/Megascans/3D_Plants/Thatching_Grass_uddmcgbia/S_Thatching_Grass_uddmcgbia_Var12_lod0` | StaticMesh | 0.07 | 1,572 | 0.47x0.41x0.42 | C10 | no | [foliage]; sibling used by PWR |
| `/Game/Megascans/3D_Plants/Thatching_Grass_uddmcgbia/S_Thatching_Grass_uddmcgbia_Var15_lod0` | StaticMesh | 0.05 | 996 | 0.42x0.33x0.37 | B30,C10 | yes | [foliage] |
| `/Game/Megascans/3D_Plants/Thatching_Grass_uddmcgbia/S_Thatching_Grass_uddmcgbia_Var16_lod0` | StaticMesh | 0.04 | 442 | 0.24x0.27x0.31 | C10 | no | [foliage]; sibling used by PWR |
| `/Game/Megascans/3D_Plants/Thatching_Grass_uddmcgbia/S_Thatching_Grass_uddmcgbia_Var18_lod0` | StaticMesh | 0.18 | 1,207 | 0.23x0.25x0.23 | C10 | no | [foliage]; sibling used by PWR |
| `/Game/Megascans/3D_Plants/Thatching_Grass_uddmcgbia/S_Thatching_Grass_uddmcgbia_Var1_lod0` | StaticMesh | 0.24 | 975 | 0.41x0.45x0.62 | B30,C10 | yes | [foliage] |
| `/Game/Megascans/3D_Plants/Thatching_Grass_uddmcgbia/S_Thatching_Grass_uddmcgbia_Var3_lod0` | StaticMesh | 0.16 | 1,127 | 0.19x0.18x0.1 | C10 | no | [foliage]; sibling used by PWR |
| `/Game/Megascans/3D_Plants/Thatching_Grass_uddmcgbia/S_Thatching_Grass_uddmcgbia_Var7_lod0` | StaticMesh | 0.20 | 1,389 | 0.16x0.11x0.07 | C10 | no | [foliage]; sibling used by PWR |

*Group note:* Dune/coastal grasses; Thatching_Grass already used by PWR

### Sand and shore surfaces (Megascans) (49)

*Where on PWR:* Lake beaches, shore shelves (pebble beach, shoreline rocks, rippled sand at the lake floor)

| path | kind | MB | verts | bounds m | levels | PWR | note |
|---|---|---|---|---|---|---|---|
| `/Game/Megascans/Surfaces/Beach_Gravel_ue4nbhdlw/MF_LL_Beach_Gravel_ue4nbhdlw` | MaterialFunction | 0.00 |  |  | B30 | no |  |
| `/Game/Megascans/Surfaces/Beach_Sand_With_Pebbles_vl0fdilo/MF_LL_Beach_Sand_With_Pebbles_vl0fdilo` | MaterialFunction | 0.00 |  |  | B30 | no |  |
| `/Game/Megascans/Surfaces/Beach_Sand_xdheagk/MF_LL_Beach_Sand_xdheagk` | MaterialFunction | 0.00 |  |  | B30 | no |  |
| `/Game/Megascans/Surfaces/Shoreline_Beach_Rocks_ullmagidy/MF_LL_T_Shoreline_Beach_Rocks_ullmagidy` | MaterialFunction | 0.00 |  |  | B30,B40,C45 | no |  |
| `/Game/Megascans/Surfaces/Thai_Beach_Sand_tdsmeeko/MF_LL_T_T_Thai_Beach_Sand_tdsmeeko` | MaterialFunction | 0.00 |  |  | B30,E10 | no |  |
| `/Game/Megascans/Surfaces/Thai_Beach_Sand_tdsmeeko/MI_Thai_Beach_Sand_tdsmeeko_2K` | MaterialInstance | 0.00 |  |  | E10,E30 | no |  |
| `/Game/Megascans/Surfaces/Thai_Beach_Sand_tefgafrk/MF_LL_T_Thai_Beach_Sand_tefgafrk` | MaterialFunction | 0.00 |  |  | B30,E10 | no |  |
| `/Game/Megascans/Surfaces/Thai_Rippled_Beach_Sand_vb1ldadn/MF_LL_Thai_Rippled_Beach_Sand_vb1ldadn` | MaterialFunction | 0.00 |  |  | B30 | no |  |
| `/Game/Megascans/Surfaces/Thai_Seaweed_On_Sand_teshfj1q/MF_LL_Thai_Seaweed_On_Sand_teshfj1q` | MaterialFunction | 0.00 |  |  | B30 | no |  |

Textures: `/Game/Megascans/Surfaces/Beach_Gravel_ue4nbhdlw/T_Beach_Gravel_ue4nbhdlw_2K_D` (2.8 MB), `/Game/Megascans/Surfaces/Beach_Gravel_ue4nbhdlw/T_Beach_Gravel_ue4nbhdlw_2K_N` (5.6 MB), `/Game/Megascans/Surfaces/Beach_Gravel_ue4nbhdlw/T_Beach_Gravel_ue4nbhdlw_2K_ORHG` (5.6 MB), `/Game/Megascans/Surfaces/Beach_Sand_With_Pebbles_vl0fdilo/T_Beach_Sand_With_Pebbles_vl0fdilo_2K_NSVT_D` (2.8 MB), `/Game/Megascans/Surfaces/Beach_Sand_With_Pebbles_vl0fdilo/T_Beach_Sand_With_Pebbles_vl0fdilo_2K_NSVT_N` (5.6 MB), `/Game/Megascans/Surfaces/Beach_Sand_With_Pebbles_vl0fdilo/T_Beach_Sand_With_Pebbles_vl0fdilo_2K_NSVT_ORHG` (5.6 MB), `/Game/Megascans/Surfaces/Beach_Sand_xdheagk/T_Beach_Sand_xdheagk_2K_NSVT_D` (2.8 MB), `/Game/Megascans/Surfaces/Beach_Sand_xdheagk/T_Beach_Sand_xdheagk_2K_NSVT_N` (5.6 MB), `/Game/Megascans/Surfaces/Beach_Sand_xdheagk/T_Beach_Sand_xdheagk_2K_NSVT_ORHG` (5.6 MB), `/Game/Megascans/Surfaces/Cracked_Shale_Beach_Rock_ve4lfbng/T_CrackedShaleBeachRock_ve4lfbng_8K_ORDp` (3.2 MB), `/Game/Megascans/Surfaces/Cracked_Shale_Beach_Rock_ve4lfbng/T_Cracked_Shale_Beach_Rock_ve4lfbng_8K_D` (3.2 MB), `/Game/Megascans/Surfaces/Cracked_Shale_Beach_Rock_ve4lfbng/T_Cracked_Shale_Beach_Rock_ve4lfbng_8K_N` (6.4 MB), `/Game/Megascans/Surfaces/Cracked_Shale_Beach_Rock_ve4lfbng/T_Cracked_Shale_Beach_Rock_ve4lfbng_ORHG` (6.4 MB), `/Game/Megascans/Surfaces/Jagged_Shale_Beach_Cliff_vcsncbkew/T_Jagged_Shale_Beach_Cliff_vcsncbkew_8K_N` (6.4 MB), `/Game/Megascans/Surfaces/Layered_Beach_Rock_ud5tachlw/T_LayeredBeachRock_ud5tachlw_2K_ORDp` (3.2 MB), `/Game/Megascans/Surfaces/Layered_Beach_Rock_ud5tachlw/T_Layered_Beach_Rock_ud5tachlw_2K_N` (6.4 MB), `/Game/Megascans/Surfaces/Shoreline_Beach_Rocks_ullmagidy/T_Shoreline_Beach_Rocks_ullmagidy_NSVT_D` (2.8 MB), `/Game/Megascans/Surfaces/Shoreline_Beach_Rocks_ullmagidy/T_Shoreline_Beach_Rocks_ullmagidy_NSVT_N` (5.6 MB), `/Game/Megascans/Surfaces/Shoreline_Beach_Rocks_ullmagidy/T_Shoreline_Beach_Rocks_ullmagidy_NSVT_ORHG` (5.6 MB), `/Game/Megascans/Surfaces/Thai_Beach_Sand_tdsmeeko/T_ThaiBeachSand_tdsmeeko_2K_NSVT_ORDp` (6.4 MB), `/Game/Megascans/Surfaces/Thai_Beach_Sand_tdsmeeko/T_ThaiBeachSand_tdsmeeko_2K_ORDp` (3.2 MB), `/Game/Megascans/Surfaces/Thai_Beach_Sand_tdsmeeko/T_Thai_Beach_Sand_tdsmeeko_2K_D` (3.2 MB), `/Game/Megascans/Surfaces/Thai_Beach_Sand_tdsmeeko/T_Thai_Beach_Sand_tdsmeeko_2K_N` (6.4 MB), `/Game/Megascans/Surfaces/Thai_Beach_Sand_tdsmeeko/T_Thai_Beach_Sand_tdsmeeko_2K_NSVT_D` (2.8 MB), `/Game/Megascans/Surfaces/Thai_Beach_Sand_tdsmeeko/T_Thai_Beach_Sand_tdsmeeko_2K_NSVT_N` (5.6 MB), `/Game/Megascans/Surfaces/Thai_Beach_Sand_tefgafrk/T_ThaiBeachSand_tefgafrk_2K_NSVT_ORDp` (5.6 MB), `/Game/Megascans/Surfaces/Thai_Beach_Sand_tefgafrk/T_ThaiBeachSand_tefgafrk_2K_ORDp` (3.2 MB), `/Game/Megascans/Surfaces/Thai_Beach_Sand_tefgafrk/T_Thai_Beach_Sand_tefgafrk_2K_N` (6.4 MB), `/Game/Megascans/Surfaces/Thai_Beach_Sand_tefgafrk/T_Thai_Beach_Sand_tefgafrk_2K_NSVT_D` (2.8 MB), `/Game/Megascans/Surfaces/Thai_Beach_Sand_tefgafrk/T_Thai_Beach_Sand_tefgafrk_2K_NSVT_N` (5.6 MB), `/Game/Megascans/Surfaces/Thai_Beach_Sand_tejidarl/T_Thai_Beach_Sand_tejidarl_4K_N` (25.4 MB), `/Game/Megascans/Surfaces/Thai_Rippled_Beach_Sand_vb1ldadn/T_ThaiRippledBeachSand_vb1ldadn_2K_NSVT_ORDp` (2.8 MB), `/Game/Megascans/Surfaces/Thai_Rippled_Beach_Sand_vb1ldadn/T_Thai_Rippled_Beach_Sand_vb1ldadn_2K_NSVT_D` (1.4 MB), `/Game/Megascans/Surfaces/Thai_Rippled_Beach_Sand_vb1ldadn/T_Thai_Rippled_Beach_Sand_vb1ldadn_2K_NSVT_N` (2.8 MB), `/Game/Megascans/Surfaces/Thai_Rippled_Sand_tdplebfn/T_Thai_Rippled_Sand_tdplebfn_2K_NSVT_D` (2.8 MB), `/Game/Megascans/Surfaces/Thai_Rippled_Sand_tdplebfn/T_Thai_Rippled_Sand_tdplebfn_2K_NSVT_N` (5.6 MB), `/Game/Megascans/Surfaces/Thai_Rippled_Sand_tdplebfn/T_Thai_Rippled_Sand_tdplebfn_2K_NSVT_ORHG` (5.6 MB), `/Game/Megascans/Surfaces/Thai_Seaweed_On_Sand_teshfj1q/T_Thai_Seaweed_On_Sand_teshfj1q_2K_D` (2.8 MB), `/Game/Megascans/Surfaces/Thai_Seaweed_On_Sand_teshfj1q/T_Thai_Seaweed_On_Sand_teshfj1q_2K_N` (1.4 MB), `/Game/Megascans/Surfaces/Thai_Seaweed_On_Sand_teshfj1q/T_Thai_Seaweed_On_Sand_teshfj1q_2K_ORHG` (5.6 MB)

*Group note:* Megascans sand/shore texture sets incl. MF_LL_* landscape-layer functions; Thai_* are tropical white sand (tint down)

## 3. Roads and verges (167)

### Road debris decals (Megascans/Env/Bio) (28)

*Where on PWR:* Road edges and verges (debris, leakage, soil stains)

| path | kind | MB | verts | bounds m | levels | PWR | note |
|---|---|---|---|---|---|---|---|
| `/Game/Env/Bio/DirtyDecals/Soil/MI_Decal_soil_Curved_01` | MaterialInstance | 0.02 |  |  | C10 | no | [decal] |
| `/Game/Env/Bio/DirtyDecals/Soil/MI_Decal_soil_Vertical_01` | MaterialInstance | 0.03 |  |  | C10 | no | [decal] |
| `/Game/Env/Bio/DirtyDecals/Soil/MI_Decal_soil_Vertical_02` | MaterialInstance | 0.02 |  |  | C10 | no | [decal] |
| `/Game/Env/Bio/Materials/Decals/M_MS_Blood_Decal` | Material | 0.02 |  |  | A15,A50,B30,B40,C10,D20,D40,E20,E30 | no | [decal] |
| `/Game/Megascans/Decals/Debris_phlvmjp2/MI_Debris_phlvmjp2_2K` | MaterialInstance | 0.00 |  |  | B30 | no | [decal] |
| `/Game/Megascans/Decals/Debris_phlvrdp2/MI_Debris_FR_SnowDust` | MaterialInstance | 0.03 |  |  | B40,C45 | no | snow variant [decal] |
| `/Game/Megascans/Decals/Debris_phlvrdp2/MI_Debris_phlvrdp2_LessStones_2K` | MaterialInstance | 0.00 |  |  | B30,B40,C45 | no | [decal] |
| `/Game/Megascans/Decals/Debris_phlvrdp2/MI_Debris_phlvrdp2_LessStones_A30` | MaterialInstance | 0.00 |  |  | A30,B40,C45 | no | [decal] |
| `/Game/Megascans/Decals/Debris_phlvrdp2/MI_Debris_phlvrdp2_LessStones_D40` | MaterialInstance | 0.00 |  |  | D40 | no | [decal] |
| `/Game/Megascans/Decals/Leakage/MI_Leakage_10` | MaterialInstance | 0.00 |  |  | B40,C45 | no | [decal] |
| `/Game/Megascans/Decals/Leakage_tdfdfebc/MI_Leakage_tdfdfebc_4K` | MaterialInstance | 0.00 |  |  | B40,C45 | no | [decal] |
| `/Game/Megascans/Decals/Leakage_tdlbcbrc/MI_Leakage_tdlbcbrc_4K` | MaterialInstance | 0.00 |  |  | B40,C45 | no | [decal] |

Textures: `/Game/Env/Bio/DirtyDecals/Soil/T_Decal_soil_Curved_01_DRO` (12.7 MB), `/Game/Env/Bio/DirtyDecals/Soil/T_Decal_soil_Vertical_01_DRO` (12.7 MB), `/Game/Env/Bio/DirtyDecals/Soil/T_Decal_soil_Vertical_02_DRO` (12.7 MB), `/Game/Megascans/Decals/Debris_phlvmjp2/T_Debris_phlvmjp2_2K_D` (3.2 MB), `/Game/Megascans/Decals/Debris_phlvmjp2/T_Debris_phlvmjp2_2K_DpRA` (3.2 MB), `/Game/Megascans/Decals/Debris_phlvmjp2/T_Debris_phlvmjp2_2K_N` (6.4 MB), `/Game/Megascans/Decals/Debris_phlvrdp2/T_Debris_phlvrdp2_2K_DpRA` (3.2 MB), `/Game/Megascans/Decals/Debris_phlvrdp2/T_Debris_phlvrdp2_LessStone_2K_D` (3.2 MB), `/Game/Megascans/Decals/Debris_phlvrdp2/T_Debris_phlvrdp2_LessStones_2K_N` (6.4 MB), `/Game/Megascans/Decals/Debris_phlvrdp2/T_Frost_Decal_01` (25.4 MB), `/Game/Megascans/Decals/Leakage/T_Leakage_05_BC` (6.4 MB), `/Game/Megascans/Decals/Leakage/T_Leakage_05_DpRM` (6.4 MB), `/Game/Megascans/Decals/Leakage_tdfdfebc/T_Leakage_tdfdfebc_4K_D` (5.6 MB), `/Game/Megascans/Decals/Leakage_tdfdfebc/T_Leakage_tdfdfebc_4K_DpRA` (5.6 MB), `/Game/Megascans/Decals/Leakage_tdlbcbrc/T_Leakage_tdlbcbrc_4K_D` (5.6 MB), `/Game/Megascans/Decals/Leakage_tdlbcbrc/T_Leakage_tdlbcbrc_4K_DpRA` (5.6 MB)

*Group note:* Decal materials/textures. HIGH RISK: cooked decal masters crashed PWR with a PSO fatal

### Forerunner barriers, rails and outpost pieces (A30 beam-emitter refinery) (20)

*Where on PWR:* Forerunner-style road barriers and rails at bridge approaches and base ramps; small outpost 'castle' blocks at junctions

| path | kind | MB | verts | bounds m | levels | PWR | note |
|---|---|---|---|---|---|---|---|
| `/Game/Env/HS/FR/HAL/Ext_Terminal_A_Beam_Emitter/FR_HAL_Ext_Terminal_Refinery_Barrier_Linear_w_d12i75_h_A_TEMP_A/SM_FR_HAL_Ext_Terminal_Refinery_Barrier_Linear_w_d12i75_h_A_TEMP_A` | StaticMesh | 4.11 | 110,929 | 12.81x13.86x5.73 | A30 | no | packed AO/roughness/height map [collision] |
| `/Game/Env/HS/FR/HAL/Ext_Terminal_A_Beam_Emitter/FR_HAL_Ext_Terminal_Refinery_Barrier_Linear_w_d3i5_h_A_TEMP_A/SM_FR_HAL_Ext_Terminal_Refinery_Barrier_Linear_w_d3i5_h_A_TEMP_A` | StaticMesh | 2.34 | 72,912 | 6.37x4.58x6.35 | A30 | no | packed AO/roughness/height map [collision] |
| `/Game/Env/HS/FR/HAL/Ext_Terminal_A_Beam_Emitter/FR_HAL_Ext_Terminal_Refinery_Barrier_Outlook_w_d_h_A_TEMP_A/SM_FR_HAL_Ext_Terminal_Refinery_Barrier_Outlook_w_d_h_A_TEMP_A` | StaticMesh | 16.62 | 513,563 | 8.9x7.61x24.76 | A30 | no | packed AO/roughness/height map; very dense: confirm Nanite before placing many [collision] |
| `/Game/Env/HS/FR/HAL/Ext_Terminal_A_Beam_Emitter/FR_HAL_Ext_Terminal_Refinery_Barrier_Plating_Step1_Linear_Sym_w_d_h_A_TEMP_A/SM_FR_HAL_Ext_Terminal_Refinery_Barrier_Plating_Step1_Linear_Sym_w_d_h_A_TEMP_A` | StaticMesh | 0.02 | 260 | 2.95x2.1x0.5 | A30 | no | packed AO/roughness/height map [collision] |
| `/Game/Env/HS/FR/HAL/Ext_Terminal_A_Beam_Emitter/FR_HAL_Ext_Terminal_Refinery_Barrier_Plating_Step1_Linear_w_d_h_A_TEMP_A/SM_FR_HAL_Ext_Terminal_Refinery_Barrier_Plating_Step1_Linear_w_d_h_A_TEMP_A` | StaticMesh | 2.18 | 68,575 | 2.95x2.8x0.5 | A30 | no | packed AO/roughness/height map [collision] |
| `/Game/Env/HS/FR/HAL/Ext_Terminal_A_Beam_Emitter/FR_HAL_Ext_Terminal_Refinery_Barrier_Plating_Step1_Ramp_w_d_h_A_TEMP_A/SM_FR_HAL_Ext_Terminal_Refinery_Barrier_Plating_Step1_Ramp_w_d_h_A_TEMP_A` | StaticMesh | 2.43 | 74,907 | 2.95x3.6x0.5 | A30 | no | packed AO/roughness/height map [collision] |
| `/Game/Env/HS/FR/HAL/Ext_Terminal_A_Beam_Emitter/FR_HAL_Ext_Terminal_Refinery_Barrier_Plating_Step2_Ramp_w_d_h_A_TEMP_A/SM_FR_HAL_Ext_Terminal_Refinery_Barrier_Plating_Step2_Ramp_w_d_h_A_TEMP_A` | StaticMesh | 0.28 | 9,760 | 2.95x2.4x0.76 | A30 | no | packed AO/roughness/height map [collision] |
| `/Game/Env/HS/FR/HAL/Ext_Terminal_A_Beam_Emitter/FR_HAL_Ext_Terminal_Refinery_Barrier_Rail_A_Linear_Cap_Top_w2_d_h_A_TEMP_A/SM_FR_HAL_Ext_Terminal_Refinery_Barrier_Rail_A_Linear_Cap_Top_w2_d_h_A_TEMP_A` | StaticMesh | 0.38 | 12,383 | 0.39x1.0x1.73 | A30 | no | packed AO/roughness/height map [collision] |
| `/Game/Env/HS/FR/HAL/Ext_Terminal_A_Beam_Emitter/FR_HAL_Ext_Terminal_Refinery_Barrier_Rail_A_Linear_Tile_Switch_w1i25_d_h_A_TEMP_A/SM_FR_HAL_Ext_Terminal_Refinery_Barrier_Rail_A_Linear_Tile_Switch_w1i25_d_h_A_TEMP_A` | StaticMesh | 0.56 | 18,358 | 0.39x1.5x1.73 | A30 | no | packed AO/roughness/height map [collision] |
| `/Game/Env/HS/FR/HAL/Ext_Terminal_A_Beam_Emitter/FR_HAL_Ext_Terminal_Refinery_Barrier_Rail_A_Linear_w1i25_d_h_A_TEMP_A/SM_FR_HAL_Ext_Terminal_Refinery_Barrier_Rail_A_Linear_w1i25_d_h_A_TEMP_A` | StaticMesh | 0.21 | 7,346 | 0.39x6.5x1.73 | A30 | no | packed AO/roughness/height map [collision] |
| `/Game/Env/HS/FR/HAL/Ext_Terminal_A_Beam_Emitter/FR_HAL_Ext_Terminal_Refinery_Barrier_Rail_A_RampCap_w1i25_d_h_A_TEMP_A/SM_FR_HAL_Ext_Terminal_Refinery_Barrier_Rail_A_RampCap_w1i25_d_h_A_TEMP_A` | StaticMesh | 2.47 | 79,933 | 0.39x6.14x1.73 | A30 | no | packed AO/roughness/height map [collision] |
| `/Game/Env/HS/FR/HAL/Ext_Terminal_A_Beam_Emitter/FR_HAL_Ext_Terminal_Refinery_Barrier_Ramp_Deg37i5_w_d_h_A_TEMP_A/SM_FR_HAL_Ext_Terminal_Refinery_Barrier_Ramp_Deg37i5_w_d_h_A_TEMP_A` | StaticMesh | 5.82 | 155,514 | 12.81x11.23x7.28 | A30 | no | packed AO/roughness/height map [collision] |
| `/Game/Env/HS/FR/HAL/Ext_Terminal_A_Beam_Emitter/FR_HAL_Ext_Terminal_Refinery_Barrier_Turn90_In_w_d_h_A_TEMP_A/SM_FR_HAL_Ext_Terminal_Refinery_Barrier_Turn90_In_w_d_h_A_TEMP_A` | StaticMesh | 1.86 | 48,370 | 9.96x9.96x6.35 | A30 | no | packed AO/roughness/height map [collision] |
| `/Game/Env/HS/FR/HAL/Ext_Terminal_A_Beam_Emitter/FR_HAL_Ext_Terminal_Refinery_Outpost_Castle_Corner_A/SM_FR_HAL_Ext_Terminal_Refinery_Outpost_Castle_Corner_A` | StaticMesh | 15.87 | 430,715 | 5.28x5.28x7.66 | A30 | no | very dense: confirm Nanite before placing many [collision] |
| `/Game/Env/HS/FR/HAL/Ext_Terminal_A_Beam_Emitter/FR_HAL_Ext_Terminal_Refinery_Outpost_Castle_Door_A/SM_FR_HAL_Ext_Terminal_Refinery_Outpost_Castle_Door_A` | StaticMesh | 5.38 | 145,363 | 3.25x1.56x3.28 | A30 | no | [collision] |
| `/Game/Env/HS/FR/HAL/Ext_Terminal_A_Beam_Emitter/FR_HAL_Ext_Terminal_Refinery_Outpost_Castle_Doorway_A/SM_FR_HAL_Ext_Terminal_Refinery_Outpost_Castle_Doorway_A` | StaticMesh | 4.30 | 114,597 | 3.85x2.9x3.72 | A30 | no | [collision] |
| `/Game/Env/HS/FR/HAL/Ext_Terminal_A_Beam_Emitter/FR_HAL_Ext_Terminal_Refinery_Outpost_Castle_Floor_A/SM_FR_HAL_Ext_Terminal_Refinery_Outpost_Castle_Floor_A` | StaticMesh | 16.95 | 463,704 | 12.53x12.53x0.1 | A30 | no | very dense: confirm Nanite before placing many [collision] |
| `/Game/Env/HS/FR/HAL/Ext_Terminal_A_Beam_Emitter/FR_HAL_Ext_Terminal_Refinery_Outpost_Castle_Plinth_A/SM_FR_HAL_Ext_Terminal_Refinery_Outpost_Castle_Plinth_A` | StaticMesh | 17.23 | 464,463 | 5.27x5.27x5.24 | A30 | no | very dense: confirm Nanite before placing many [collision] |
| `/Game/Env/HS/FR/HAL/Ext_Terminal_A_Beam_Emitter/FR_HAL_Ext_Terminal_Refinery_Outpost_Castle_Ramp_A/SM_FR_HAL_Ext_Terminal_Refinery_Outpost_Castle_Ramp_A` | StaticMesh | 11.11 | 299,568 | 12.17x6.75x4.98 | A30 | no | [collision] |
| `/Game/Env/HS/FR/HAL/Ext_Terminal_A_Beam_Emitter/FR_HAL_Ext_Terminal_Refinery_Outpost_Castle_Wall_A/SM_FR_HAL_Ext_Terminal_Refinery_Outpost_Castle_Wall_A` | StaticMesh | 8.26 | 219,956 | 6.28x2.21x5.01 | A30 | no | [collision] |

*Group note:* Linear barrier, rail, ramp and turn pieces plus outpost castle parts. Names carry _TEMP_A, so check finish quality before use. Render-only: author collision

### UNSC barriers, containers and crates (27)

*Where on PWR:* Checkpoints at road junctions, base approaches, supply dumps at the Pelican LZs

| path | kind | MB | verts | bounds m | levels | PWR | note |
|---|---|---|---|---|---|---|---|
| `/Game/Env/HS/UNSC/Gen/props/UNSC_Gen_AirConditioner_w0i25_d2i6_h0i85_A/SM_UNSC_Gen_AirConditioner_w0i25_d2i6_h0i85_A` | StaticMesh | 0.98 | 36,866 | 0.26x2.6x0.85 | D40 | no | [collision] |
| `/Game/Env/HS/UNSC/Gen/props/UNSC_Gen_BarricadeSmallVisor/SM_Barricade_Small_Visor` | StaticMesh | 3.59 | 106,111 | 1.77x1.83x2.67 | A15,D40 | no | [collision] |
| `/Game/Env/HS/UNSC/Gen/props/UNSC_Gen_Barrier_w3i6_d4_h2i7_A/SM_UNSC_Gen_Barrier_Gap_w3i6_d4_h2i7_A` | StaticMesh | 4.86 | 145,532 | 3.6x4.02x2.56 | A15,D40 | no | [collision] |
| `/Game/Env/HS/UNSC/Gen/props/UNSC_Gen_Barrier_w3i6_d4_h2i7_A/SM_UNSC_Gen_Barrier_w3i6_d4_h2i7_A` | StaticMesh | 5.49 | 164,741 | 3.6x4.02x2.57 | A15 | no | [collision] |
| `/Game/Env/HS/UNSC/Gen/props/UNSC_Gen_Container_Lrg_w4_d4_h3_A/SM_UNSC_Gen_Container_Lrg_w4_d4_h3_A` | StaticMesh | 2.19 | 68,632 | 4.13x4.0x3.0 | D40 | no | [collision] |
| `/Game/Env/HS/UNSC/Gen/props/UNSC_Gen_Container_Mid_w2i3_d2i4_h1i6_A/SM_UNSC_Gen_Container_Mid_w2i3_d2i4_h1i6_A` | StaticMesh | 7.93 | 242,038 | 2.24x2.42x1.6 | A15,D40 | no | [collision] |
| `/Game/Env/HS/UNSC/Gen/props/UNSC_Gen_Container_Sml_w1_d2_h1_A/SM_UNSC_Gen_Container_Sml_w1_d2_h1_A` | StaticMesh | 2.79 | 87,559 | 1.04x2.04x1.0 | D40 | no | [collision] |
| `/Game/Env/HS/UNSC/Gen/props/UNSC_Gen_Crate_A/SM_UNSC_Gen_Crate_A` | StaticMesh | 2.91 | 90,416 | 0.65x0.92x1.07 | A15,D40,E10,E20 | no | [collision] |
| `/Game/Env/HS/UNSC/Gen/props/UNSC_Gen_Crate_B/SM_UNSC_Gen_Crate_B` | StaticMesh | 9.52 | 308,891 | 1.56x0.92x0.76 | A15,D40,E10,E20 | no | [collision] |
| `/Game/Env/HS/UNSC/Gen/props/UNSC_Gen_Crate_D/SM_UNSC_Gen_Crate_D` | StaticMesh | 5.64 | 185,175 | 1.89x0.41x0.6 | A15,D40,E10,E20 | no | [collision] |
| `/Game/Env/HS/UNSC/Gen/props/UNSC_Gen_Crate_E/BP_UNSC_Gen_Crate_E` | Blueprint | 0.00 |  |  |  | no | [collision] |
| `/Game/Env/HS/UNSC/Gen/props/UNSC_Gen_Crate_E/SM_UNSC_Gen_Crate_E` | StaticMesh | 4.21 | 136,427 | 0.35x0.52x0.51 |  | no | [collision] |
| `/Game/Env/HS/UNSC/Gen/props/UNSC_Gen_Crate_F/BP_UNSC_Gen_Crate_F` | Blueprint | 0.00 |  |  |  | no | [collision] |
| `/Game/Env/HS/UNSC/Gen/props/UNSC_Gen_Crate_F/SM_UNSC_Gen_Crate_F` | StaticMesh | 5.20 | 164,008 | 0.74x0.54x0.31 | D40 | no | [collision] |
| `/Game/Env/HS/UNSC/Gen/props/UNSC_Gen_Crate_G/BP_UNSC_Gen_Crate_G` | Blueprint | 0.00 |  |  |  | no | [collision] |
| `/Game/Env/HS/UNSC/Gen/props/UNSC_Gen_Crate_G/SM_UNSC_Gen_Crate_G` | StaticMesh | 5.17 | 164,495 | 1.02x0.52x0.22 | D40 | no | [collision] |
| `/Game/Env/HS/UNSC/Gen/props/UNSC_Gen_GunRack/SM_UNSC_Gen_GunRack` | StaticMesh | 5.14 | 147,156 | 1.71x2.56x2.05 | A15,D40,E10 | no | [collision] |
| `/Game/Env/HS/UNSC/Gen/props/UNSC_Gen_Holder_w5i5_d3_h3i75_A/SM_UNSC_Gen_Holder_w5i5_d3_h3i75_A` | StaticMesh | 4.15 | 123,925 | 5.56x3.0x3.74 | D40,E30 | no | [collision] |
| `/Game/Env/HS/UNSC/Gen/props/UNSC_Gen_Honeypot/SM_UNSC_Gen_Honeypot_Open` | StaticMesh | 0.90 | 18,578 | 0.44x0.64x0.92 | A15 | no | [collision] |
| `/Game/Env/HS/UNSC/Gen/props/UNSC_Gen_OxyTank_w3i1_d3i1_h2i74_A/SM_UNSC_Gen_OxyTank_w3i1_d3i1_h2i74_A` | StaticMesh | 5.72 | 183,329 | 2.92x2.92x2.73 | A15,D40 | no | [collision] |
| `/Game/Env/HS/UNSC/Gen/props/UNSC_Gen_PipeSet_w4_d8_h4_A/SM_UNSC_Gen_PipeSet_w4_d8_h4_A` | StaticMesh | 5.71 | 174,942 | 4.87x8.12x4.0 | D40,E30 | no | [collision] |
| `/Game/Env/HS/UNSC/Gen/props/UNSC_Gen_Pipeline_Small_w1_d2_h0i375_A/SM_UNSC_Gen_Pipeline_Small_w1_d2_h0i375_A` | StaticMesh | 2.77 | 79,724 | 1.26x2.0x0.33 | D40,E30 | no | [collision] |
| `/Game/Env/HS/UNSC/Gen/props/UNSC_Gen_Prop_Crate_w0i8_d0i7_h0i4_A/BP_UNSC_Gen_Prop_Crate_A` | Blueprint | 0.00 |  |  |  | no | [collision] |
| `/Game/Env/HS/UNSC/Gen/props/UNSC_Gen_Prop_Crate_w0i8_d0i7_h0i4_A/SM_UNSC_Gen_Prop_Crate_w0i8_d0i7_h0i4_A` | StaticMesh | 1.64 | 46,532 | 0.79x0.75x0.43 | A15 | no | [collision] |
| `/Game/Env/HS/UNSC/Gen/props/UNSC_Gen_Prop_Crate_w0i8_d0i7_h0i4_B/SM_UNSC_Gen_Prop_Crate_w0i8_d0i7_h0i4_B` | StaticMesh | 1.52 | 48,975 | 0.79x0.75x0.43 | A15 | no | [collision] |
| `/Game/Env/HS/UNSC/Gen/props/UNSC_Gen_Terminal/SM_UNSC_Gen_Terminal` | StaticMesh | 4.57 | 142,326 | 0.67x0.83x0.98 |  | no | [collision] |
| `/Game/Env/HS/UNSC/Gen/props/UNSC_Gen_WeaponFrame_w0i32_d4i87_h4i58_A/SM_UNSC_Gen_WeaponFrame_w0i32_d4i87_h4i58_A` | StaticMesh | 4.99 | 153,434 | 0.44x5.62x5.26 | D40 | no | [collision] |

*Group note:* UNSC generic props. Decor has no sim collision: for touchable props prefer the Blam crate tags (unsc_gen_prop_crate_*) in the Tags group

### Debris material instances (MM_Debris) (17)

*Where on PWR:* Rock and moss litter along verges and around boulders (for the Megascans rocky-ground and mossy-rock meshes)

| path | kind | MB | verts | bounds m | levels | PWR | note |
|---|---|---|---|---|---|---|---|
| `/Game/Environments/Debris/Materials/MIP_SandstoneRockyGround` | MaterialInstance | 0.03 |  |  | B40,C10,C45,E20 | no |  |
| `/Game/Environments/Debris/Materials/MI_MossyForestRoots_01` | MaterialInstance | 0.00 |  |  | C10 | no |  |
| `/Game/Environments/Debris/Materials/MI_MossyRocks_01` | MaterialInstance | 0.00 |  |  | C10 | no |  |
| `/Game/Environments/Debris/Materials/MI_MossyRocks_Dark` | MaterialInstance | 0.00 |  |  | C10 | no |  |
| `/Game/Environments/Debris/Materials/MI_NordicBeachRockyGround_02` | MaterialInstance | 0.00 |  |  | B40,C10,C45 | no |  |
| `/Game/Environments/Debris/Materials/MI_NordicBeachRockyGround_Dark` | MaterialInstance | 0.03 |  |  | C10 | no |  |
| `/Game/Environments/Debris/Materials/MI_SandstoneRockyGround_01` | MaterialInstance | 0.00 |  |  | E20 | no |  |
| `/Game/Environments/Debris/Materials/MI_SandstoneRockyGround_02` | MaterialInstance | 0.12 |  |  | B40,C10,C45 | no |  |
| `/Game/Environments/Debris/Materials/MI_SandstoneRockyGround_03` | MaterialInstance | 0.00 |  |  | B40,C10,C45,E20 | no |  |
| `/Game/Environments/Debris/Materials/MI_SandstoneRockyGround_03_Desat` | MaterialInstance | 0.00 |  |  | B40,C45 | no |  |
| `/Game/Environments/Debris/Materials/MI_SandstoneRockyGround_03_E20` | MaterialInstance | 0.09 |  |  | E20 | no |  |
| `/Game/Environments/Debris/Materials/MI_SandstoneRockyGround_04` | MaterialInstance | 0.00 |  |  | B40,C45,E20 | no |  |
| `/Game/Environments/Debris/Materials/MI_SandstoneRockyGround_04_Desat` | MaterialInstance | 0.00 |  |  | B40,C45 | no |  |
| `/Game/Environments/Debris/Materials/MI_SandstoneRockyGround_05` | MaterialInstance | 0.00 |  |  | E20 | no |  |
| `/Game/Environments/Debris/Materials/MI_SandstoneRockyGround_06` | MaterialInstance | 0.00 |  |  | E20 | no |  |
| `/Game/Environments/Debris/Materials/MI_SandstoneRockyGround_Canyon` | MaterialInstance | 0.00 |  |  | E20 | no |  |
| `/Game/Environments/Debris/Materials/MI_SandstoneRockyGround_Snow` | MaterialInstance | 0.00 |  |  | B40,C45 | no | snow variant |

*Group note:* Mesh material instances on the MM_Debris master (not decals), incl. Snow, Desat and Canyon variants; C10 uses them

### Megascans decal masters (4)

*Where on PWR:* -

| path | kind | MB | verts | bounds m | levels | PWR | note |
|---|---|---|---|---|---|---|---|
| `/Game/MSPresets/M_MS_Decal_Material/M_MS_Decal_Material` | Material | 0.02 |  |  | B40,C45 | no | [decal] |
| `/Game/MSPresets/M_MS_Decal_Material_VT/M_MS_Decal_Material_VT` | Material | 0.03 |  |  | A30,A50,B30,B40,C10,C45,D40,E20,E30 | no | virtual-texture copy [decal] |
| `/Game/MSPresets/M_MS_Decal_Material_VT/M_MS_Decal_Material_VT_NoEmissive` | Material | 0.03 |  |  | C10,E10 | no | virtual-texture copy [decal] |
| `/Game/MSPresets/M_MS_Decal_Material_VT/M_MS_Decal_Material_VT_NoNormal` | Material | 0.02 |  |  | A15,A50,B40,E20 | no | virtual-texture copy [decal] |

*Group note:* Decal master materials. HIGH RISK (PSO fatal seen before)

### Gravel and path surfaces (Megascans) (33)

*Where on PWR:* Dirt-road beds, gravel shoulders, pull-offs and the base aprons

| path | kind | MB | verts | bounds m | levels | PWR | note |
|---|---|---|---|---|---|---|---|
| `/Game/Megascans/Surfaces/Gravel_Natural_vglndb0g/MF_LL_Gravel_Natural_vglndb0g` | MaterialFunction | 0.00 |  |  | B40,C45 | no |  |
| `/Game/Megascans/Surfaces/Ground_Gravel_uconcitg/MF_LL_Ground_Gravel_uconcitg` | MaterialFunction | 0.00 |  |  | B40,C45 | no | sibling used by PWR |
| `/Game/Megascans/Surfaces/Ground_Gravel_ukxmacclw/MF_LL_Ground_Gravel_ukxmacclw` | MaterialFunction | 0.00 |  |  | B40,C45 | no |  |
| `/Game/Megascans/Surfaces/Sandy_Gravel_Ground_vmndcca/MF_LL_Sandy_Gravel_Ground_vnmdcca_New` | MaterialFunction | 0.00 |  |  | B30 | no |  |
| `/Game/Megascans/Surfaces/Soil_Clay_pjDuk0/MLI_A30_CrashSite_Mud` | MaterialLayerInstance | 0.00 |  |  | A30 | no |  |
| `/Game/Megascans/Surfaces/Soil_Clay_pjDuk0/MLI_Soil_Clay_pjDuk0_4k_Uber` | MaterialLayerInstance | 0.00 |  |  | A30,B30,B40,C10,C45,E20 | no |  |
| `/Game/Megascans/Surfaces/Trampled_Forest_Path_ub4jdihkw/MF_LL_Trampled_Forest_Path_ub4jdihkw_2K` | MaterialFunction | 0.00 |  |  | B30 | no | sibling used by PWR |

Textures: `/Game/Megascans/Surfaces/Gravel_Natural_vglndb0g/T_Gravel_Natural_vglndb0g_4K_NSVT_D` (2.8 MB), `/Game/Megascans/Surfaces/Gravel_Natural_vglndb0g/T_Gravel_Natural_vglndb0g_4K_NSVT_N` (5.6 MB), `/Game/Megascans/Surfaces/Gravel_Natural_vglndb0g/T_Gravel_Natural_vglndb0g_NSVT_ORHG` (5.6 MB), `/Game/Megascans/Surfaces/Gravel_ground_vl1oabbfw/T_Scree_NSVT_A30_D` (2.8 MB), `/Game/Megascans/Surfaces/Gravel_ground_vl1oabbfw/T_gravel_ground_vl1oabbfw_NSVT_N` (5.6 MB), `/Game/Megascans/Surfaces/Gravel_ground_vl1oabbfw/T_gravel_ground_vl1oabbfw_NSVT_ORHG` (5.6 MB), `/Game/Megascans/Surfaces/Ground_Gravel_uconcitg/T_Ground_Gravel_uconcitg_sbs_NSVT_D` (2.8 MB, PWR yes), `/Game/Megascans/Surfaces/Ground_Gravel_uconcitg/T_Ground_Gravel_uconcitg_sbs_NSVT_N` (5.6 MB, PWR yes), `/Game/Megascans/Surfaces/Ground_Gravel_uconcitg/T_Ground_Gravel_uconcitg_sbs_NSVT_ORHG` (5.6 MB), `/Game/Megascans/Surfaces/Ground_Gravel_ukxmacclw/T_Ground_Gravel_ukxmacclw_NSVT_D` (2.8 MB), `/Game/Megascans/Surfaces/Ground_Gravel_ukxmacclw/T_Ground_Gravel_ukxmacclw_NSVT_N` (5.6 MB), `/Game/Megascans/Surfaces/Ground_Gravel_ukxmacclw/T_Ground_Gravel_ukxmacclw_NSVT_ORHG` (5.6 MB), `/Game/Megascans/Surfaces/Sandy_Gravel_Ground_vmndcca/T_Sandy_Gravel_Ground_vmndcca_2K_NSVT_N` (5.6 MB), `/Game/Megascans/Surfaces/Sandy_Gravel_Ground_vmndcca/T_T_Sandy_Gravel_Ground_vmndcca_B_2K_NSVT_D_copy` (2.8 MB), `/Game/Megascans/Surfaces/Sandy_Gravel_Ground_vmndcca/T_T_Sandy_Gravel_Ground_vmndcca_B_2K_NSVT_ORHG` (5.6 MB), `/Game/Megascans/Surfaces/Soil_Clay_pjDuk0/T_Soil_Clay_pjDuk0_4k_D` (3.2 MB), `/Game/Megascans/Surfaces/Soil_Clay_pjDuk0/T_Soil_Clay_pjDuk0_4k_N` (6.4 MB), `/Game/Megascans/Surfaces/Soil_Clay_pjDuk0/T_Soil_Clay_pjDuk0_4k_NSVT_D` (2.8 MB), `/Game/Megascans/Surfaces/Soil_Clay_pjDuk0/T_Soil_Clay_pjDuk0_4k_NSVT_N` (5.6 MB), `/Game/Megascans/Surfaces/Soil_Clay_pjDuk0/T_Soil_Clay_pjDuk0_4k_NSVT_ORHG` (5.6 MB), `/Game/Megascans/Surfaces/Soil_Clay_pjDuk0/T_Soil_Clay_pjDuk0_4k_ORHG` (6.4 MB), `/Game/Megascans/Surfaces/Soil_Rough_tijicf3aw/T_Soil_Rough_tijicf3aw_4K_N` (6.4 MB), `/Game/Megascans/Surfaces/Soil_Rough_tijicf3aw/T_Soil_Rough_tijicf3aw_4K_ORHG` (6.4 MB), `/Game/Megascans/Surfaces/Trampled_Forest_Path_ub4jdihkw/T_Trampled_Forest_Path_ub4jdihkw_NSVT_D` (2.8 MB, PWR yes), `/Game/Megascans/Surfaces/Trampled_Forest_Path_ub4jdihkw/T_Trampled_Forest_Path_ub4jdihkw_NSVT_N` (5.6 MB, PWR yes), `/Game/Megascans/Surfaces/Trampled_Forest_Path_ub4jdihkw/T_Trampled_Forest_Path_ub4jdihkw_NSVT_ORHG` (5.6 MB, PWR yes)

*Group note:* Megascans gravel/soil texture sets; PWR uses Ground_Gravel_uconcitg D/N and Trampled_Forest_Path D/N/ORHG

### Blam crate/scenery tags (collision-backed props) (9)

*Where on PWR:* Touchable props near roads and LZs that must collide and sync

| path | kind | MB | verts | bounds m | levels | PWR | note |
|---|---|---|---|---|---|---|---|
| `/Game/Tags/objects/levels/Shared/device_machines/dm_flare/dm_flare-device_machine` | BlamTag:device_machine | 0.01 |  |  |  | no |  |
| `/Game/Tags/objects/levels/halo1/solo/D40/engine_debris/debris-crate` | BlamTag:crate | 0.01 |  |  |  | no |  |
| `/Game/Tags/objects/levels/halo1/solo/e30/e30_wreckage_big_pipe/e30_wreckage_big_pipe-crate` | BlamTag:crate | 0.01 |  |  |  | no |  |
| `/Game/Tags/objects/levels/halo1/solo/e30/e30_wreckage_girder_support/e30_wreckage_girder_support-crate` | BlamTag:crate | 0.01 |  |  |  | no |  |
| `/Game/Tags/objects/levels/halo1/solo/e30/e30_wreckage_ship_structure/e30_wreckage_ship_structure-crate` | BlamTag:crate | 0.01 |  |  |  | no |  |
| `/Game/Tags/objects/props/UNSC/unsc_gen_prop_crate_a/unsc_gen_prop_crate_a-crate` | BlamTag:crate | 0.01 |  |  |  | no |  |
| `/Game/Tags/objects/props/UNSC/unsc_gen_prop_crate_e/unsc_gen_prop_crate_e-crate` | BlamTag:crate | 0.01 |  |  |  | no |  |
| `/Game/Tags/objects/props/UNSC/unsc_gen_prop_crate_f/unsc_gen_prop_crate_f-crate` | BlamTag:crate | 0.01 |  |  |  | no |  |
| `/Game/Tags/objects/props/UNSC/unsc_gen_prop_crate_g/unsc_gen_prop_crate_g-crate` | BlamTag:crate | 0.01 |  |  |  | no |  |

*Group note:* Simulation objects (crate/scenery tags): engine-first route, they collide and network with no code

### Landscape deformation toolkit (tracks, footprints) (29)

*Where on PWR:* Vehicle tracks and footprints in dirt/snow without decals

| path | kind | MB | verts | bounds m | levels | PWR | note |
|---|---|---|---|---|---|---|---|
| `/HaloLandscapeDeformations/Resources/M_SimpleWriter` | Material | 0.01 |  |  | B30,B40,C45,D40,E10 | no |  |
| `/HaloLandscapeDeformations/Resources/M_TrackExampleMat` | Material | 0.01 |  |  |  | no |  |
| `/HaloLandscapeDeformations/Resources/MeltingBrushes/M_DynamicMeltingHot` | Material | 0.01 |  |  |  | no |  |
| `/HaloLandscapeDeformations/Resources/MeltingBrushes/M_DynamicMeltingHotParam` | Material | 0.01 |  |  |  | no |  |
| `/HaloLandscapeDeformations/Toolkit/AC_TerrainDeformationSurface` | Blueprint | 0.00 |  |  | B30,B40,C45,D40,E10 | no | sibling used by PWR |
| `/HaloLandscapeDeformations/Toolkit/BP_LandscapeDeformationManager` | Blueprint | 0.22 |  |  | B30,B40,C45,D40,E10 | no | sibling used by PWR |
| `/HaloLandscapeDeformations/Toolkit/MF_GetDeformationMask` | MaterialFunction | 0.00 |  |  | A50,B30,B40,C45,D20,D40,E10,E20 | no | sibling used by PWR |
| `/HaloLandscapeDeformations/Toolkit/MPC_DeformationGlobals` | MaterialParameterCollection | 0.00 |  |  | A50,B30,B40,C45,D20,D40,E10,E20 | yes |  |
| `/HaloLandscapeDeformations/Toolkit/M_BrushLODDefaultMaterial` | Material | 0.02 |  |  | B30,B40,C45,D40,E10 | no | sibling used by PWR |
| `/HaloLandscapeDeformations/Toolkit/M_DeformationParticleColor` | Material | 0.01 |  |  |  | no | sibling used by PWR |
| `/HaloLandscapeDeformations/Toolkit/M_DepthToBrushMat` | Material | 0.01 |  |  | B30,B40,C45,D40,E10 | no | sibling used by PWR |
| `/HaloLandscapeDeformations/Toolkit/M_GlobalReaderMain` | Material | 0.01 |  |  | B30,B40,C45,D40,E10 | no | sibling used by PWR |
| `/HaloLandscapeDeformations/Toolkit/M_MeltingMaskCopyWithShift` | Material | 0.01 |  |  | B30,B40,C45,D40,E10 | no | sibling used by PWR |
| `/HaloLandscapeDeformations/Toolkit/NS_SampleDeformationMaskBatched` | NiagaraSystem | 0.02 |  |  | B30,B40,C45,D40,E10 | no | sibling used by PWR |
| `/HaloLandscapeDeformations/Toolkit/RVT_PreDeformationLODDisplacement` | RuntimeVirtualTexture | 0.00 |  |  | A50,B30,B40,C45,D20,D40,E10,E20 | no | sibling used by PWR |
| `/HaloLandscapeDeformations/Toolkit/SC_LandscapeDeformableTile` | Blueprint | 0.08 |  |  | B30,B40,C45,D40,E10 | no | sibling used by PWR |
| `/HaloLandscapeDeformations/Toolkit/SM_BrushLODPlane` | StaticMesh | 0.00 |  |  | B30,B40,C45,D40,E10 | no | sibling used by PWR |
| `/HaloLandscapeDeformations/maps/L_LandscapeDeformationExample_sharedassets/Grass_LayerInfo` | LandscapeLayerInfo | 0.00 |  |  | A30 | no |  |
| `/HaloLandscapeDeformations/maps/RVT_LandscapeH` | RuntimeVirtualTexture | 0.00 |  |  | B30,B40,C45,D40,E10 | no |  |
| `/HaloLandscapeDeformations/maps/RVT_LandscapePBR` | RuntimeVirtualTexture | 0.00 |  |  | B30,B40,C45,D40,E10 | no |  |

Textures: `/HaloLandscapeDeformations/Resources/T_FootStep` (0.0 MB), `/HaloLandscapeDeformations/Resources/T_FootStep2` (0.0 MB), `/HaloLandscapeDeformations/Resources/T_Spartan_Decal_Footprint_11` (5.6 MB), `/HaloLandscapeDeformations/Resources/T_Spartan_Decal_Footprint_13` (5.6 MB), `/HaloLandscapeDeformations/Resources/T_TextureElevation10` (0.0 MB), `/HaloLandscapeDeformations/Resources/T_WheelTexture` (0.0 MB), `/HaloLandscapeDeformations/Resources/T_WheelTextureElevation` (0.0 MB), `/HaloLandscapeDeformations/Resources/T_WheelTextureElevation24` (0.0 MB), `/HaloLandscapeDeformations/Resources/elite_decal_footprint_1` (5.6 MB)

*Group note:* Shipped runtime landscape-deformation system (RVT + render-target brushes, M_TrackExampleMat). PWR already binds MPC_DeformationGlobals (foot_mpc); the manager BP and render targets are a runtime system, so check it stays data-driven

## 4. Forests (1094)

### Black alder (riverside deciduous tree) (11)

*Where on PWR:* River banks and lake shores below the pines

| path | kind | MB | verts | bounds m | levels | PWR | note |
|---|---|---|---|---|---|---|---|
| `/Game/Env/Bio/BlackAlder/Geometry/SimpleWind/SM_BlackAlder_Field_05` | StaticMesh | 10.05 | 47,869 | 6.74x7.01x7.43 | C10 | no | [foliage] |
| `/Game/Env/Bio/BlackAlder/Materials/SimpleWind/MI_BlackAlder` | MaterialInstance | 0.13 |  |  | C10 | no | [foliage] |
| `/Game/Env/Bio/BlackAlder/Materials/SimpleWind/MI_BlackAlder_Decoration` | MaterialInstance | 0.13 |  |  | C10 | no | [foliage] |
| `/Game/Env/Bio/BlackAlder/Materials/SimpleWind/MI_BlackAlder_TwoSided_A` | MaterialInstance | 0.05 |  |  | C10 | no | [foliage] |
| `/Game/Env/Bio/BlackAlder/Materials/SimpleWind/MI_BlackAlder_TwoSided_B` | MaterialInstance | 0.05 |  |  | C10 | no | [foliage] |

Textures: `/Game/Env/Bio/BlackAlder/Textures/Decoration/T_BlackAlder_Decoration_D` (3.2 MB), `/Game/Env/Bio/BlackAlder/Textures/Decoration/T_BlackAlder_Decoration_Mask` (3.2 MB), `/Game/Env/Bio/BlackAlder/Textures/Decoration/T_BlackAlder_Decoration_N` (6.4 MB), `/Game/Env/Bio/BlackAlder/Textures/TwoSided/Summer/T_BlackAlder_TwoSided_Summer_D` (12.7 MB), `/Game/Env/Bio/BlackAlder/Textures/TwoSided/Summer/T_BlackAlder_TwoSided_Summer_Mask` (3.2 MB), `/Game/Env/Bio/BlackAlder/Textures/TwoSided/Summer/T_BlackAlder_TwoSided_Summer_N` (6.4 MB)

*Group note:* SpeedTree-style black alder with summer two-sided leaf cards; NS_FallingLeaves_BlackAlder matches it

### Fungus, lichen and shelf mushrooms (Env/Bio) (21)

*Where on PWR:* Logs, stumps and root plates in the forest

| path | kind | MB | verts | bounds m | levels | PWR | note |
|---|---|---|---|---|---|---|---|
| `/Game/Env/Bio/Fungus/Lichen/Fungus_Lichen_Parasitism_A/SM_Fungus_Lichen_Parasitism_A` | StaticMesh | 4.12 | 75,103 | 0.79x0.8x0.24 | C10 | no |  |
| `/Game/Env/Bio/Fungus/Lichen/Fungus_Lichen_Parasitism_C/SM_Fungus_Lichen_Parasitism_C` | StaticMesh | 3.84 | 75,040 | 0.79x0.8x0.41 | C10 | no |  |
| `/Game/Env/Bio/Fungus/Lichen/Fungus_Lichen_Parasitism_D/SM_Fungus_Lichen_Parasitism_D` | StaticMesh | 4.02 | 71,065 | 0.95x0.8x0.25 | C10 | no |  |
| `/Game/Env/Bio/Fungus/Lichen/Materials/MI_Fungus_Lichen_Parasitism_01` | MaterialInstance | 0.03 |  |  | C10 | no |  |
| `/Game/Env/Bio/Fungus/Lichen/Materials/MI_Layer_Fungus_Lichen_Parasitism_01` | MaterialInstance | 0.12 |  |  | C10 | no |  |
| `/Game/Env/Bio/Fungus/Lichen/Materials/MI_Layer_Fungus_Lichen_Parasitism_01_Wet` | MaterialInstance | 0.08 |  |  | C10 | no | wet variant |
| `/Game/Env/Bio/Fungus/PilophorusAcicularis/Fungus_PilophorusAcicularis_A/SM_Fungus_PilophorusAcicularis_A` | StaticMesh | 0.57 | 17,111 | 1.05x0.98x0.74 | C10 | no |  |
| `/Game/Env/Bio/Fungus/PilophorusAcicularis/Fungus_PilophorusAcicularis_B/SM_Fungus_PilophorusAcicularis_B` | StaticMesh | 0.68 | 20,295 | 0.68x0.67x0.73 | C10 | no |  |
| `/Game/Env/Bio/Fungus/PilophorusAcicularis/Fungus_PilophorusAcicularis_C/SM_Fungus_PilophorusAcicularis_C` | StaticMesh | 0.57 | 17,221 | 0.93x0.84x0.7 | C10 | no |  |
| `/Game/Env/Bio/Ground/TreeRoot/Ground_TreeRoot_Messy_A/SM_Ground_TreeRoot_Messy_A` | StaticMesh | 1.84 | 31,412 | 6.01x6.01x0.43 | C10 | yes |  |
| `/Game/Env/Bio/Mushroom/TurkeyTail/Materials/MM_MS_HaloTreeWind_Mushroom_TurkeyTail_01_Wet` | MaterialInstance | 0.08 |  |  | C10 | no | wet variant |
| `/Game/Env/Bio/Mushroom/TurkeyTail/Materials/M_MS_HaloTreeWind_Mushroom_TurkeyTail_01` | MaterialInstance | 0.12 |  |  | C10 | no |  |
| `/Game/Env/Bio/Mushroom/TurkeyTail/Mushroom_TurkeyTail_Sml_A/SM_Mushroom_TurkeyTail_Sml_A` | StaticMesh | 0.45 | 7,774 | 0.31x0.25x0.12 | C10 | no |  |
| `/Game/Env/Bio/Mushroom/TurkeyTail/Mushroom_TurkeyTail_Sml_B/SM_Mushroom_TurkeyTail_Sml_B` | StaticMesh | 0.41 | 7,690 | 0.29x0.24x0.09 | C10 | no |  |
| `/Game/Env/Bio/Mushroom/TurkeyTail/Mushroom_TurkeyTail_Sml_C/SM_Mushroom_TurkeyTail_Sml_C` | StaticMesh | 0.43 | 7,764 | 0.32x0.23x0.09 | C10 | no |  |

Textures: `/Game/Env/Bio/Fungus/Lichen/Materials/T_Fungus_Lichen_Parasitism_D` (3.2 MB), `/Game/Env/Bio/Fungus/Lichen/Materials/T_Fungus_Lichen_Parasitism_DR` (3.2 MB), `/Game/Env/Bio/Fungus/Lichen/Materials/T_Fungus_Lichen_Parasitism_N` (3.2 MB), `/Game/Env/Bio/Mushroom/TurkeyTail/Materials/T_Mushroom_TurkeyTail_01_D` (0.9 MB), `/Game/Env/Bio/Mushroom/TurkeyTail/Materials/T_Mushroom_TurkeyTail_01_DR` (1.7 MB), `/Game/Env/Bio/Mushroom/TurkeyTail/Materials/T_Mushroom_TurkeyTail_01_N` (1.7 MB)

*Group note:* Lichen, reindeer-moss (Pilophorus) and turkey-tail shelf fungus; AlienMushroom skipped (alien)

### Bark and forest-floor materials (Env/Bio/Materials, Megascans) (25)

*Where on PWR:* Trunk and log materials, forest floor layer

| path | kind | MB | verts | bounds m | levels | PWR | note |
|---|---|---|---|---|---|---|---|
| `/Game/Env/Bio/Materials/Bark/Bark_Debris_01/MI_Tree_WhiteWillow_Debris` | MaterialInstance | 0.12 |  |  | C10 | no |  |
| `/Game/Env/Bio/Materials/Bark/Bark_Debris_01/MI_Tree_WhiteWillow_Debris_Wet` | MaterialInstance | 0.08 |  |  | C10 | no | wet variant |

Textures: `/Game/Env/Bio/Materials/Bark/Bark_Coastwood_01/T_Bark_Coastwood_01_N` (6.4 MB), `/Game/Env/Bio/Materials/Bark/Bark_Debris_01/T_Tree_WhiteWillow_Debris_D` (3.2 MB), `/Game/Env/Bio/Materials/Bark/Bark_Debris_01/T_Tree_WhiteWillow_Debris_N` (6.4 MB), `/Game/Env/Bio/Materials/Bark/Bark_Debris_01/T_Tree_WhiteWillow_Debris_ORHG` (6.4 MB), `/Game/Env/Bio/Materials/Bark/Bark_Forerunner_01/T_Bark_Forerunner_01_D` (3.2 MB), `/Game/Env/Bio/Materials/Bark/Bark_Forerunner_01/T_Bark_Forerunner_01_N` (6.4 MB), `/Game/Env/Bio/Materials/Bark/Bark_Forerunner_01/T_Bark_Forerunner_01_ORHG` (6.4 MB), `/Game/Env/Bio/Materials/Bark/Bark_Mangrove_01/T_Mangrove_Trunk_01_D` (1.6 MB), `/Game/Env/Bio/Materials/Bark/Bark_Mangrove_01/T_Mangrove_Trunk_01_N` (3.3 MB), `/Game/Env/Bio/Materials/Bark/Bark_Mangrove_01/T_Mangrove_Trunk_01_ORHG` (3.3 MB), `/Game/Env/Bio/Materials/Bark/Bark_Mangrove_01/T_Mangrove_Vines_01_D` (0.5 MB), `/Game/Env/Bio/Materials/Bark/Bark_Mangrove_01/T_Mangrove_Vines_01_N` (0.9 MB), `/Game/Env/Bio/Materials/Bark/Bark_Metasequoia_01/T_Bark_Metasequoia_01_D` (3.2 MB), `/Game/Env/Bio/Materials/Bark/Bark_Metasequoia_01/T_Bark_Metasequoia_01_N` (6.4 MB), `/Game/Env/Bio/Materials/Bark/Bark_Metasequoia_01/T_Bark_Metasequoia_01_ORHG` (6.4 MB), `/Game/Megascans/Surfaces/Bark_Other_wghjcggn/T_Bark_Other_wghjcggn_4K_N` (3.3 MB), `/Game/Megascans/Surfaces/Bark_Other_wghjcggn/T_Bark_Other_wghjcggn_4K_ORHG` (12.7 MB), `/Game/Megascans/Surfaces/JandBark/T_JandBark_01_BC` (3.2 MB), `/Game/Megascans/Surfaces/JandBark/T_JandBark_01_N` (6.4 MB), `/Game/Megascans/Surfaces/JandBark/T_JandBark_01_ORHG` (6.4 MB), `/Game/Megascans/Surfaces/Tree_Bark_tf5kfenr/T_Tree_Bark_tf5kfenr_4K_D` (3.2 MB), `/Game/Megascans/Surfaces/Tree_Bark_tjuncgzl/T_Tree_Bark_tjuncgzl_4K_N` (6.4 MB), `/Game/Megascans/Surfaces/Tree_Bark_tjuncgzl/T_Tree_Bark_tjuncgzl_4K_ORHG` (6.4 MB)

*Group note:* Bark material sets (Coastwood etc.)

### Shrubs (Env/Bio/Shrub) (6)

*Where on PWR:* Forest edge and river willow thickets

| path | kind | MB | verts | bounds m | levels | PWR | note |
|---|---|---|---|---|---|---|---|
| `/Game/Env/Bio/Shrub/BetulaRotundifolia/Materials/MI_Shrub_BetulaRotundifolia_01` | MaterialInstance | 0.15 |  |  | C20 | no | [foliage] |
| `/Game/Env/Bio/Shrub/BetulaRotundifolia/Shrub_BetulaRotundifolia_B/SM_Shrub_BetulaRotundifolia_B` | StaticMesh | 12.51 | 325,927 | 0.88x0.95x1.61 | C20 | yes | [foliage] |
| `/Game/Env/Bio/Shrub/Shrub_Willow_Arctic/Materials/MI_Shrub_Willow_Arctic_Branch_A1` | MaterialInstance | 0.03 |  |  | A30,B40,C45 | no | [foliage] |
| `/Game/Env/Bio/Shrub/Shrub_Willow_Arctic/Materials/MI_Shrub_Willow_Arctic_Leaf_A` | MaterialInstance | 0.03 |  |  | A30,B40,C45 | no | [foliage] |
| `/Game/Env/Bio/Shrub/Shrub_Willow_Arctic/SM_Willow_Arctic_Leaf_Cluster_A` | StaticMesh | 0.89 | 10,672 | 1.2x1.33x1.4 | A30,B40,C45 | yes | [foliage] |
| `/Game/Env/Bio/Shrub/Shrub_Willow_Arctic/SM_Willow_Arctic_Leaf_Cluster_B` | StaticMesh | 0.68 | 11,328 | 1.31x1.1x1.84 | A30,B40,C45 | no | [foliage]; sibling used by PWR |

*Group note:* Arctic willow and round-leaf birch; both used by PWR

### Dead trees, burnt trees, roots and stumps (Env/Bio/Tree) (114)

*Where on PWR:* Forest edges, burn scars near the bases, stumps and exposed roots on cut banks; WhiteWillow along the river

| path | kind | MB | verts | bounds m | levels | PWR | note |
|---|---|---|---|---|---|---|---|
| `/Game/Env/Bio/Tree/Burnt/Burnt_Log_vcaeeyfa/SM_Burnt_Log_vcsaeeyfa_01` | StaticMesh | 0.29 | 6,676 | 1.63x0.29x0.29 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Burnt/Burnt_Tree_Trunk_vcpocfoga/MI_Burnt_Tree_Trunk_vcpocfoga` | MaterialInstance | 0.14 |  |  | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Burnt/Burnt_Tree_Trunk_vcpocfoga/SM_Burnt_Tree_Trunk_vcpocfoga` | StaticMesh | 9.46 | 301,621 | 0.67x0.69x1.11 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/DeadTree/Foliage/FT_Dead_Tree_Branch_01_FoliageType` | FoliageType | 0.00 |  |  | D20 | no | [foliage] |
| `/Game/Env/Bio/Tree/DeadTree/Foliage/FT_Dead_Tree_Branch_02_FoliageType` | FoliageType | 0.00 |  |  | D20 | no | [foliage] |
| `/Game/Env/Bio/Tree/DeadTree/Foliage/FT_Dead_Tree_Branch_03_FoliageType` | FoliageType | 0.00 |  |  | D20 | no | [foliage] |
| `/Game/Env/Bio/Tree/DeadTree/Materials/MIP_Dead_Tree_A` | MaterialInstance | 0.30 |  |  | D20 | no | [foliage] |
| `/Game/Env/Bio/Tree/DeadTree/Materials/MI_Dead_Tree_A` | MaterialInstance | 0.28 |  |  | D20 | no | [foliage] |
| `/Game/Env/Bio/Tree/DeadTree/Materials/MI_Dead_Tree_A_Burn` | MaterialInstance | 0.28 |  |  | D20 | no | [foliage] |
| `/Game/Env/Bio/Tree/DeadTree/Materials/MI_Dead_Tree_A_Variant` | MaterialInstance | 0.28 |  |  | D20 | no | [foliage] |
| `/Game/Env/Bio/Tree/Metasequoia/Materials/MIP_Bark_Metasequoia` | MaterialInstance | 0.16 |  |  |  | no | [foliage] |
| `/Game/Env/Bio/Tree/Metasequoia/Materials/MIP_Bark_Metasequoia_Wet` | MaterialInstance | 0.09 |  |  |  | no | wet variant [foliage] |
| `/Game/Env/Bio/Tree/Metasequoia/Materials/MIP_Tree_Metasequoia` | MaterialInstance | 0.19 |  |  | C10 | no | [foliage] |
| `/Game/Env/Bio/Tree/Metasequoia/Materials/MI_Env_Layered_Bark_Metasequoia` | MaterialInstance | 0.12 |  |  | C10,D20,E20,E30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Metasequoia/Materials/MI_Env_Layered_Bark_Metasequoia_Wet` | MaterialInstance | 0.08 |  |  | C10 | no | wet variant [foliage] |
| `/Game/Env/Bio/Tree/Metasequoia/Materials/MI_Env_Layered_Tree_Metasequoia` | MaterialInstance | 0.19 |  |  | C10 | no | [foliage] |
| `/Game/Env/Bio/Tree/Metasequoia/Materials/MI_Env_Layered_Tree_Metasequoia_Wet` | MaterialInstance | 0.09 |  |  | C10 | no | wet variant [foliage] |
| `/Game/Env/Bio/Tree/Metasequoia/Tree_Metasequoia_A/SM_Tree_Metasequoia_A` | StaticMesh | 13.38 | 472,493 | 25.41x24.8x100.19 | C10 | no | very dense: confirm Nanite before placing many [foliage] |
| `/Game/Env/Bio/Tree/Metasequoia/Tree_Metasequoia_B/SM_Tree_Metasequoia_B` | StaticMesh | 11.01 | 395,546 | 28.96x28.68x90.01 | C10 | no | [foliage] |
| `/Game/Env/Bio/Tree/Metasequoia/Tree_Metasequoia_Branch_Dead_Lrg_A/SM_Tree_Metasequoia_Branch_Dead_Lrg_A` | StaticMesh | 0.54 | 14,617 | 7.48x2.63x2.05 | C10,D20 | no | [foliage] |
| `/Game/Env/Bio/Tree/Metasequoia/Tree_Metasequoia_Branch_Dead_Med_A/SM_Tree_Metasequoia_Branch_Dead_Med_A` | StaticMesh | 0.11 | 1,621 | 4.34x1.71x0.66 | C10,D20 | no | [foliage] |
| `/Game/Env/Bio/Tree/Metasequoia/Tree_Metasequoia_Branch_Dead_Med_B/SM_Tree_Metasequoia_Branch_Dead_Med_B` | StaticMesh | 0.07 | 1,231 | 4.86x1.56x0.44 | C10,D20 | no | [foliage] |
| `/Game/Env/Bio/Tree/Metasequoia/Tree_Metasequoia_Branch_Dead_Sml_A/SM_Tree_Metasequoia_Branch_Dead_Sml_A` | StaticMesh | 0.45 | 12,737 | 1.16x0.39x0.16 | C10,D20 | no | [foliage] |
| `/Game/Env/Bio/Tree/Metasequoia/Tree_Metasequoia_Branch_Dead_Sml_B/SM_Tree_Metasequoia_Branch_Dead_Sml_B` | StaticMesh | 0.07 | 1,363 | 2.21x0.86x0.32 | C10,D20 | no | [foliage] |
| `/Game/Env/Bio/Tree/Metasequoia/Tree_Metasequoia_Branch_Dead_Sml_C/SM_Tree_Metasequoia_Branch_Dead_Sml_C` | StaticMesh | 0.05 | 1,031 | 2.55x0.44x0.33 | C10,D20 | no | [foliage] |
| `/Game/Env/Bio/Tree/Metasequoia/Tree_Metasequoia_Branch_Dead_Sml_D/SM_Tree_Metasequoia_Branch_Dead_Sml_D` | StaticMesh | 0.04 | 818 | 1.83x0.58x0.13 | C10,D20 | no | [foliage] |
| `/Game/Env/Bio/Tree/Metasequoia/Tree_Metasequoia_Branch_Dead_Sml_E/SM_Tree_Metasequoia_Branch_Dead_Sml_E` | StaticMesh | 0.08 | 912 | 1.21x0.27x0.13 | D20 | no | [foliage] |
| `/Game/Env/Bio/Tree/Metasequoia/Tree_Metasequoia_Branch_Dead_Sml_F/SM_Tree_Metasequoia_Branch_Dead_Sml_F` | StaticMesh | 0.03 | 615 | 0.92x0.29x0.04 | D20 | no | [foliage] |
| `/Game/Env/Bio/Tree/Metasequoia/Tree_Metasequoia_Root_A/Foliage/FT_Tree_Metasequoia_Root_A_FoliageType` | FoliageType | 0.00 |  |  | C10 | no | [foliage] |
| `/Game/Env/Bio/Tree/Metasequoia/Tree_Metasequoia_Root_A/Materials/MI_Bark_Metasequoia_Root_01` | MaterialInstance | 0.19 |  |  | C10 | no | [foliage] |
| `/Game/Env/Bio/Tree/Metasequoia/Tree_Metasequoia_Root_A/Materials/MI_Bark_Metasequoia_Root_01_Wet` | MaterialInstance | 0.09 |  |  | C10 | no | wet variant [foliage] |
| `/Game/Env/Bio/Tree/Metasequoia/Tree_Metasequoia_Root_A/SM_Tree_Metasequoia_Root_A` | StaticMesh | 0.28 | 6,198 | 0.43x0.4x1.59 | C10 | yes | [foliage] |
| `/Game/Env/Bio/Tree/Metasequoia/Tree_Metasequoia_Root_B/Foliage/FT_Tree_Metasequoia_Root_B_FoliageType` | FoliageType | 0.00 |  |  | C10 | no | [foliage] |
| `/Game/Env/Bio/Tree/Metasequoia/Tree_Metasequoia_Root_B/SM_Tree_Metasequoia_Root_B` | StaticMesh | 0.34 | 6,807 | 0.6x0.38x1.2 | C10 | yes | [foliage] |
| `/Game/Env/Bio/Tree/Metasequoia/Tree_Metasequoia_Root_C/Foliage/FT_Tree_Metasequoia_Root_C_FoliageType` | FoliageType | 0.00 |  |  | C10 | no | [foliage] |
| `/Game/Env/Bio/Tree/Metasequoia/Tree_Metasequoia_Root_C/SM_Tree_Metasequoia_Root_C` | StaticMesh | 0.36 | 7,611 | 0.7x0.59x2.03 | C10 | no | [foliage] |
| `/Game/Env/Bio/Tree/Metasequoia/Tree_Metasequoia_Root_D/Foliage/FT_Tree_Metasequoia_Root_D_FoliageType` | FoliageType | 0.00 |  |  | C10 | no | [foliage] |
| `/Game/Env/Bio/Tree/Metasequoia/Tree_Metasequoia_Root_D/SM_Tree_Metasequoia_Root_D` | StaticMesh | 0.37 | 7,074 | 0.62x0.41x1.3 | C10 | no | [foliage] |
| `/Game/Env/Bio/Tree/Metasequoia/Tree_Metasequoia_Stump_Damage_A/SM_Tree_Metasequoia_Stump_Damage_A` | StaticMesh | 3.69 | 103,237 | 7.62x7.51x4.65 | C10,D20 | no | [foliage] |
| `/Game/Env/Bio/Tree/Metasequoia/Tree_Metasequoia_Stump_Damage_B/SM_Tree_Metasequoia_Stump_Damage_B` | StaticMesh | 3.77 | 106,121 | 6.45x5.67x7.99 | C10,D20 | no | [foliage] |
| `/Game/Env/Bio/Tree/Metasequoia/Tree_Metasequoia_Trunk_Damage_A/SM_Tree_Metasequoia_Trunk_Damage_A` | StaticMesh | 6.69 | 208,821 | 7.92x6.24x23.44 | C10,D20 | no | [foliage] |
| `/Game/Env/Bio/Tree/Metasequoia/Tree_Metasequoia_Trunk_Damage_B/SM_Tree_Metasequoia_Trunk_Damage_B` | StaticMesh | 1.82 | 39,382 | 8.06x8.5x16.93 | C10,D20 | no | [foliage] |
| `/Game/Env/Bio/Tree/Metasequoia/Tree_Metasequoia_Trunk_Damage_C/SM_Tree_Metasequoia_Trunk_Damage_C` | StaticMesh | 6.85 | 283,037 | 6.32x0.81x0.56 | C10,D20 | no | [foliage] |
| `/Game/Env/Bio/Tree/Metasequoia/Tree_Metasequoia_Trunk_Damage_D/SM_Tree_Metasequoia_Trunk_Damage_D` | StaticMesh | 11.27 | 488,945 | 4.98x1.17x0.91 | C10,D20 | no | very dense: confirm Nanite before placing many [foliage] |
| `/Game/Env/Bio/Tree/Metasequoia/Tree_Metasequoia_Trunk_Damage_E/SM_Tree_Metasequoia_Trunk_Damage_E` | StaticMesh | 0.89 | 27,140 | 6.92x3.77x3.34 | C10,D20 | no | [foliage] |
| `/Game/Env/Bio/Tree/Mossy_Wood_Stump/MI_Mossy_Wood_Stump` | MaterialInstance | 0.14 |  |  | A30 | no | [foliage]; sibling used by PWR |
| `/Game/Env/Bio/Tree/Mossy_Wood_Stump/SM_Mossy_Wood_Stump_rgtan` | StaticMesh | 6.60 | 201,548 | 2.4x2.7x1.32 | A30 | yes | [foliage] |
| `/Game/Env/Bio/Tree/Root/Materials/MI_Env_Layered_AlienBanyanTree` | MaterialInstance | 0.16 |  |  | E20,E30 | no | off-setting (tropical/alien/marine) [foliage,setting] |
| `/Game/Env/Bio/Tree/Root/Materials/MI_Env_Layered_AlienBanyanTree_A` | MaterialInstance | 0.16 |  |  | E20 | no | off-setting (tropical/alien/marine) [foliage,setting] |
| `/Game/Env/Bio/Tree/Root/Materials/MI_Env_Layered_AlienBanyanTree_B` | MaterialInstance | 0.16 |  |  | E20 | no | off-setting (tropical/alien/marine) [foliage,setting] |
| `/Game/Env/Bio/Tree/Root/Materials/MI_Env_Layered_AlienBanyanTree_Cut` | MaterialInstance | 0.16 |  |  | E20,E30 | no | off-setting (tropical/alien/marine) [foliage,setting] |
| `/Game/Env/Bio/Tree/Root/SM_AlienBanyanTree_Root_A` | StaticMesh | 1.36 | 38,578 | 19.65x8.88x14.27 | E20 | no | off-setting (tropical/alien/marine) [foliage,setting] |
| `/Game/Env/Bio/Tree/Root/SM_AlienBanyanTree_Root_B` | StaticMesh | 2.39 | 64,134 | 16.76x17.23x10.17 | E20 | no | off-setting (tropical/alien/marine) [foliage,setting] |
| `/Game/Env/Bio/Tree/Root/SM_AlienBanyanTree_Root_C` | StaticMesh | 2.45 | 66,440 | 17.12x20.7x11.02 | E20 | no | off-setting (tropical/alien/marine) [foliage,setting] |
| `/Game/Env/Bio/Tree/Root/SM_AlienBanyanTree_Root_D` | StaticMesh | 1.23 | 35,982 | 17.25x6.6x2.7 | E20 | no | off-setting (tropical/alien/marine) [foliage,setting] |
| `/Game/Env/Bio/Tree/Root/SM_AlienBanyanTree_Root_E` | StaticMesh | 1.35 | 38,603 | 13.46x9.34x1.36 | E20 | no | off-setting (tropical/alien/marine) [foliage,setting] |
| `/Game/Env/Bio/Tree/Root/SM_AlienBanyanTree_Root_F` | StaticMesh | 3.16 | 97,371 | 11.74x6.12x1.18 | E20 | no | off-setting (tropical/alien/marine) [foliage,setting] |
| `/Game/Env/Bio/Tree/Root/SM_AlienBanyanTree_Root_H` | StaticMesh | 1.27 | 37,277 | 11.37x6.37x2.23 | E20,E30 | no | packed AO/roughness/height map; off-setting (tropical/alien/marine) [foliage,setting] |
| `/Game/Env/Bio/Tree/WhiteWillow/+PLA/BPP_PLA_Tree_WhiteWillow_A` | Blueprint | 0.14 |  |  |  | no | [foliage] |
| `/Game/Env/Bio/Tree/WhiteWillow/+PLA/BPP_PLA_Tree_WhiteWillow_B` | Blueprint | 0.11 |  |  |  | no | [foliage] |
| `/Game/Env/Bio/Tree/WhiteWillow/+PLA/BPP_PLA_Tree_WhiteWillow_C` | Blueprint | 0.14 |  |  |  | no | [foliage] |
| `/Game/Env/Bio/Tree/WhiteWillow/+PLA/BPP_PLA_Tree_WhiteWillow_D` | Blueprint | 0.11 |  |  |  | no | [foliage] |
| `/Game/Env/Bio/Tree/WhiteWillow/+PLA/BPP_PLA_Tree_WhiteWillow_Root_A` | Blueprint | 0.02 |  |  |  | no | [foliage] |
| `/Game/Env/Bio/Tree/WhiteWillow/+PLA/BPP_PLA_Tree_WhiteWillow_Root_B` | Blueprint | 0.01 |  |  |  | no | [foliage] |
| `/Game/Env/Bio/Tree/WhiteWillow/+PLA/BPP_SM_Bio_Tree_Swamp_Background_A` | Blueprint | 0.01 |  |  |  | no | [foliage] |
| `/Game/Env/Bio/Tree/WhiteWillow/+PLA/PLAY_SM_Tree_WhiteWillow_Root_A_CollisionMesh` | StaticMesh | 0.13 |  |  |  | no | collision proxy mesh [foliage] |
| `/Game/Env/Bio/Tree/WhiteWillow/Materials/MIP_Layer_Tree_WhiteWillow` | MaterialInstance | 0.19 |  |  | C10,E20,E30 | no | [foliage] |
| `/Game/Env/Bio/Tree/WhiteWillow/Materials/MIP_Layer_Tree_WhiteWillow_Wet` | MaterialInstance | 0.09 |  |  | C10 | no | wet variant [foliage] |
| `/Game/Env/Bio/Tree/WhiteWillow/Materials/MIP_Tree_WhiteWillow` | MaterialInstance | 0.19 |  |  |  | no | [foliage] |
| `/Game/Env/Bio/Tree/WhiteWillow/Materials/MIP_Tree_WhiteWillow_Wet` | MaterialInstance | 0.09 |  |  |  | no | wet variant [foliage] |
| `/Game/Env/Bio/Tree/WhiteWillow/Tree_WhiteWillow_A/Materials/MI_Tree_WhiteWillow_A` | MaterialInstance | 0.16 |  |  | C10 | no | [foliage] |
| `/Game/Env/Bio/Tree/WhiteWillow/Tree_WhiteWillow_A/Materials/MI_Tree_WhiteWillow_A_Wet` | MaterialInstance | 0.09 |  |  | C10 | no | wet variant [foliage] |
| `/Game/Env/Bio/Tree/WhiteWillow/Tree_WhiteWillow_A/PLAY_SM_Tree_WhiteWillow_A_Branches_COL_CollisionMesh` | StaticMesh | 0.10 |  |  |  | no | collision proxy mesh [foliage] |
| `/Game/Env/Bio/Tree/WhiteWillow/Tree_WhiteWillow_A/PLAY_SM_Tree_WhiteWillow_A_Roots_COL_CollisionMesh` | StaticMesh | 0.40 |  |  |  | no | collision proxy mesh [foliage] |
| `/Game/Env/Bio/Tree/WhiteWillow/Tree_WhiteWillow_A/SM_Tree_WhiteWillow_A` | StaticMesh | 3.76 | 84,741 | 44.65x48.98x78.12 | C10 | no | [foliage] |
| `/Game/Env/Bio/Tree/WhiteWillow/Tree_WhiteWillow_B/Materials/MI_Tree_WhiteWillow_B` | MaterialInstance | 0.16 |  |  | C10 | no | [foliage] |
| `/Game/Env/Bio/Tree/WhiteWillow/Tree_WhiteWillow_B/Materials/MI_Tree_WhiteWillow_B_Wet` | MaterialInstance | 0.09 |  |  | C10 | no | wet variant [foliage] |
| `/Game/Env/Bio/Tree/WhiteWillow/Tree_WhiteWillow_B/PLAY_SM_Tree_WhiteWillow_B_Ground_CollisionMesh` | StaticMesh | 0.35 |  |  |  | no | collision proxy mesh [foliage] |
| `/Game/Env/Bio/Tree/WhiteWillow/Tree_WhiteWillow_B/PLAY_SM_Tree_WhiteWillow_B_Top_CollisionMesh` | StaticMesh | 0.08 |  |  |  | no | collision proxy mesh [foliage] |
| `/Game/Env/Bio/Tree/WhiteWillow/Tree_WhiteWillow_B/SM_Tree_WhiteWillow_B` | StaticMesh | 4.68 | 105,002 | 48.48x44.24x61.07 | C10 | no | [foliage] |
| `/Game/Env/Bio/Tree/WhiteWillow/Tree_WhiteWillow_Bark_A/SM_Tree_WhiteWillow_Bark_A` | StaticMesh | 8.71 | 278,859 | 0.57x1.85x0.2 | C10 | no | [foliage] |
| `/Game/Env/Bio/Tree/WhiteWillow/Tree_WhiteWillow_Bark_B/SM_Tree_WhiteWillow_Bark_B` | StaticMesh | 4.55 | 143,242 | 0.36x1.4x0.12 | C10 | no | [foliage] |
| `/Game/Env/Bio/Tree/WhiteWillow/Tree_WhiteWillow_Bark_C/SM_Tree_WhiteWillow_Bark_C` | StaticMesh | 2.34 | 67,840 | 0.37x0.84x0.13 | C10 | no | [foliage] |
| `/Game/Env/Bio/Tree/WhiteWillow/Tree_WhiteWillow_Bark_D/SM_Tree_WhiteWillow_Bark_D` | StaticMesh | 1.75 | 47,964 | 0.3x0.95x0.11 | C10 | no | [foliage] |
| `/Game/Env/Bio/Tree/WhiteWillow/Tree_WhiteWillow_Bark_E/SM_Tree_WhiteWillow_Bark_E` | StaticMesh | 1.54 | 42,760 | 0.19x0.83x0.08 | C10 | no | [foliage] |
| `/Game/Env/Bio/Tree/WhiteWillow/Tree_WhiteWillow_C/Materials/MI_Tree_WhiteWillow_C` | MaterialInstance | 0.16 |  |  | C10 | no | [foliage] |
| `/Game/Env/Bio/Tree/WhiteWillow/Tree_WhiteWillow_C/Materials/MI_Tree_WhiteWillow_C_Wet` | MaterialInstance | 0.09 |  |  | C10 | no | wet variant [foliage] |
| `/Game/Env/Bio/Tree/WhiteWillow/Tree_WhiteWillow_C/PLAY_SM_Tree_WhiteWillow_C_CollisionMesh` | StaticMesh | 1.81 |  |  |  | no | collision proxy mesh [foliage] |
| `/Game/Env/Bio/Tree/WhiteWillow/Tree_WhiteWillow_C/SM_Tree_WhiteWillow_C` | StaticMesh | 4.38 | 97,716 | 63.66x60.06x76.23 | C10 | no | [foliage] |
| `/Game/Env/Bio/Tree/WhiteWillow/Tree_WhiteWillow_D/PLAY_SM_Tree_WhiteWillow_D_CollisionMesh` | StaticMesh | 1.00 |  |  |  | no | collision proxy mesh [foliage] |
| `/Game/Env/Bio/Tree/WhiteWillow/Tree_WhiteWillow_D/SM_Tree_WhiteWillow_D` | StaticMesh | 4.81 | 107,768 | 51.25x43.74x65.21 | C10 | no | [foliage] |
| `/Game/Env/Bio/Tree/WhiteWillow/Tree_WhiteWillow_Debris_A/SM_Tree_WhiteWillow_Debris_A` | StaticMesh | 0.12 | 734 | 1.92x1.74x6.65 | C10 | no | [foliage] |
| `/Game/Env/Bio/Tree/WhiteWillow/Tree_WhiteWillow_Debris_B/SM_Tree_WhiteWillow_Debris_B` | StaticMesh | 0.13 | 796 | 2.31x2.98x6.87 | C10 | no | [foliage] |
| `/Game/Env/Bio/Tree/WhiteWillow/Tree_WhiteWillow_Debris_C/SM_Tree_WhiteWillow_Debris_C` | StaticMesh | 0.10 | 642 | 1.71x2.15x6.17 | C10 | no | [foliage] |
| `/Game/Env/Bio/Tree/WhiteWillow/Tree_WhiteWillow_Debris_D/SM_Tree_WhiteWillow_Debris_D` | StaticMesh | 0.11 | 681 | 3.22x2.01x8.25 | C10 | no | [foliage] |
| `/Game/Env/Bio/Tree/WhiteWillow/Tree_WhiteWillow_Debris_E/SM_Tree_WhiteWillow_Debris_E` | StaticMesh | 0.16 | 959 | 3.78x3.59x11.48 | C10 | no | [foliage] |
| `/Game/Env/Bio/Tree/WhiteWillow/Tree_WhiteWillow_Parasitic_A/SM_Tree_WhiteWillow_Parasitic_A` | StaticMesh | 0.22 | 4,820 | 60.94x62.77x116.93 | C10 | no | [foliage] |
| `/Game/Env/Bio/Tree/WhiteWillow/Tree_WhiteWillow_Parasitic_B/SM_Tree_WhiteWillow_Parasitic_B` | StaticMesh | 0.29 | 5,925 | 45.95x38.16x101.59 | C10 | no | [foliage] |
| `/Game/Env/Bio/Tree/WhiteWillow/Tree_WhiteWillow_Parasitic_D/SM_Tree_WhiteWillow_Parasitic_D` | StaticMesh | 0.12 | 2,464 | 19.16x11.41x76.79 | C10 | no | [foliage] |
| `/Game/Env/Bio/Tree/WhiteWillow/Tree_WhiteWillow_Parasitic_E/SM_Tree_WhiteWillow_parasitic_E` | StaticMesh | 0.22 | 6,011 | 90.58x79.82x115.55 | C10 | no | [foliage] |
| `/Game/Env/Bio/Tree/WhiteWillow/Tree_WhiteWillow_Parasitic_F/SM_Tree_WhiteWillow_parasitic_F` | StaticMesh | 0.13 | 2,804 | 57.18x58.68x107.51 | C10 | no | [foliage] |
| `/Game/Env/Bio/Tree/WhiteWillow/Tree_WhiteWillow_Root_A/Materials/MI_Env_Layered_Tree_WhiteWillow_Root_A` | MaterialInstance | 0.15 |  |  | C10,D20,E20 | no | [foliage] |
| `/Game/Env/Bio/Tree/WhiteWillow/Tree_WhiteWillow_Root_A/Materials/MI_Env_Layered_Tree_WhiteWillow_Root_A_Wet` | MaterialInstance | 0.08 |  |  | C10 | no | wet variant [foliage] |
| `/Game/Env/Bio/Tree/WhiteWillow/Tree_WhiteWillow_Root_A/SM_Tree_WhiteWillow_Root_A` | StaticMesh | 1.34 | 36,060 | 3.36x5.38x0.75 | C10,D20 | no | [foliage] |
| `/Game/Env/Bio/Tree/WhiteWillow/Tree_WhiteWillow_Root_B/SM_Tree_WhiteWillow_Root_B` | StaticMesh | 2.03 | 60,917 | 1.92x3.64x0.22 | C10,D20,E20 | no | [foliage] |
| `/Game/Env/Bio/Tree/WhiteWillow/Tree_WhiteWillow_Root_C/SM_Tree_WhiteWillow_Root_C` | StaticMesh | 2.39 | 68,755 | 2.76x5.04x0.6 | C10,D20,E20 | no | [foliage] |
| `/Game/Env/Bio/Tree/WhiteWillow/Tree_WhiteWillow_Root_D/SM_Tree_WhiteWillow_Root_D` | StaticMesh | 2.50 | 75,438 | 2.67x6.51x0.58 | C10,D20,E20 | no | [foliage] |
| `/Game/Env/Bio/Tree/WhiteWillow/Tree_WhiteWillow_Root_E/SM_Tree_WhiteWillow_Root_E` | StaticMesh | 2.48 | 34,459 | 10.67x9.18x16.98 | C10 | no | [foliage] |
| `/Game/Env/Bio/Tree/WhiteWillow/Tree_WhiteWillow_Root_F/SM_Tree_WhiteWillow_Root_F` | StaticMesh | 5.99 | 114,186 | 10.9x9.9x19.1 | C10 | no | [foliage] |
| `/Game/Env/Bio/Tree/WhiteWillow/Tree_WhiteWillow_Root_G/SM_Tree_WhiteWillow_Root_G` | StaticMesh | 0.21 | 7,652 | 4.38x6.76x6.68 | C10,D20 | no | [foliage] |
| `/Game/Env/Bio/Tree/WhiteWillow/Tree_WhiteWillow_Twigs_A/SM_Tree_WhiteWillow_Twigs_A` | StaticMesh | 1.63 | 14,199 | 67.64x73.99x59.18 | C10 | no | [foliage] |
| `/Game/Env/Bio/Tree/WhiteWillow/Tree_WhiteWillow_Twigs_B/SM_Tree_WhiteWillow_Twigs_B` | StaticMesh | 1.66 | 17,796 | 62.81x69.48x48.6 | C10 | no | [foliage] |
| `/Game/Env/Bio/Tree/WhiteWillow/Tree_WhiteWillow_Twigs_C/SM_Tree_WhiteWillow_Twigs_C` | StaticMesh | 2.04 | 23,912 | 93.64x83.52x58.96 | C10 | no | [foliage] |
| `/Game/Env/Bio/Tree/WhiteWillow/Tree_WhiteWillow_Twigs_D/SM_Tree_WhiteWillow_Twigs_D` | StaticMesh | 2.49 | 38,732 | 69.49x73.03x60.88 | C10 | no | [foliage] |

*Group note:* Env/Bio tree props; Metasequoia is a redwood (use only stumps/roots); PWR uses Metasequoia roots and the mossy stump

### Douglas fir (Env/Bio/Tree/DouglasFir) (59)

*Where on PWR:* Second conifer species for the pine forests (variety in silhouette)

| path | kind | MB | verts | bounds m | levels | PWR | note |
|---|---|---|---|---|---|---|---|
| `/Game/Env/Bio/Tree/DouglasFir/Tree_DouglasFir_SnowDead_A/InstanceMeshDefinitions/SM_Tree_DouglasFir_SnowDead_A_Tree_Windswept_BranchDead_A` | StaticMesh | 0.05 | 1,200 | 10.96x9.03x5.82 | B40,C45 | no | snow variant [foliage] |
| `/Game/Env/Bio/Tree/DouglasFir/Tree_DouglasFir_SnowDead_A/InstanceMeshDefinitions/SM_Tree_DouglasFir_SnowDead_A_Tree_Windswept_BranchDead_A_Proxy` | StaticMesh | 0.03 | 535 | 10.34x8.79x5.75 | B40,C45 | no | snow variant [foliage] |
| `/Game/Env/Bio/Tree/DouglasFir/Tree_DouglasFir_SnowDead_A/Materials/MI_Branch_Mat_LOD0_TwoSided` | MaterialInstance | 0.03 |  |  | B40,C45 | no | [foliage] |
| `/Game/Env/Bio/Tree/DouglasFir/Tree_DouglasFir_SnowDead_A/Materials/MI_bark_Mat_LOD0` | MaterialInstance | 0.00 |  |  | B40,C45 | no | [foliage] |
| `/Game/Env/Bio/Tree/DouglasFir/Tree_DouglasFir_SnowDead_A/Meshes/PLAY_SM_Tree_DouglasFir_SnowDead_A_CollisionMesh` | StaticMesh | 0.58 |  |  | B40 | no | snow variant; collision proxy mesh [foliage] |
| `/Game/Env/Bio/Tree/DouglasFir/Tree_DouglasFir_SnowDead_A/Meshes/SM_Tree_DouglasFir_SnowDead_A_Trunk_Tube` | StaticMesh | 5.32 | 137,126 | 4.37x4.91x30.65 | B40,C45 | no | snow variant [foliage] |
| `/Game/Env/Bio/Tree/DouglasFir/Tree_DouglasFir_SnowDead_A/Meshes/SM_Tree_DouglasFir_SnowDead_A_Tubes` | StaticMesh | 0.75 | 19,766 | 5.64x8.8x6.49 | B40,C45 | no | snow variant [foliage] |
| `/Game/Env/Bio/Tree/DouglasFir/Tree_DouglasFir_SnowDead_A/Meshes/SM_Tree_DouglasFir_SnowDead_A_Tubes_10` | StaticMesh | 0.83 | 22,335 | 7.45x7.17x6.91 | B40,C45 | no | snow variant [foliage] |
| `/Game/Env/Bio/Tree/DouglasFir/Tree_DouglasFir_SnowDead_A/Meshes/SM_Tree_DouglasFir_SnowDead_A_Tubes_11` | StaticMesh | 0.87 | 23,457 | 6.31x7.83x9.91 | B40,C45 | no | snow variant [foliage] |
| `/Game/Env/Bio/Tree/DouglasFir/Tree_DouglasFir_SnowDead_A/Meshes/SM_Tree_DouglasFir_SnowDead_A_Tubes_12` | StaticMesh | 1.50 | 43,847 | 11.94x9.48x16.8 | B40,C45 | no | snow variant [foliage] |
| `/Game/Env/Bio/Tree/DouglasFir/Tree_DouglasFir_SnowDead_A/Meshes/SM_Tree_DouglasFir_SnowDead_A_Tubes_13` | StaticMesh | 1.12 | 32,898 | 7.73x6.08x14.58 | B40,C45 | no | snow variant [foliage] |
| `/Game/Env/Bio/Tree/DouglasFir/Tree_DouglasFir_SnowDead_A/Meshes/SM_Tree_DouglasFir_SnowDead_A_Tubes_14` | StaticMesh | 0.03 | 586 | 1.03x0.86x1.36 | B40,C45 | no | snow variant [foliage] |
| `/Game/Env/Bio/Tree/DouglasFir/Tree_DouglasFir_SnowDead_A/Meshes/SM_Tree_DouglasFir_SnowDead_A_Tubes_15` | StaticMesh | 0.01 | 90 | 0.88x0.47x0.72 | B40,C45 | no | snow variant [foliage] |
| `/Game/Env/Bio/Tree/DouglasFir/Tree_DouglasFir_SnowDead_A/Meshes/SM_Tree_DouglasFir_SnowDead_A_Tubes_16` | StaticMesh | 0.01 | 90 | 1.07x0.49x0.81 | B40,C45 | no | snow variant [foliage] |
| `/Game/Env/Bio/Tree/DouglasFir/Tree_DouglasFir_SnowDead_A/Meshes/SM_Tree_DouglasFir_SnowDead_A_Tubes_17` | StaticMesh | 0.01 | 101 | 0.82x0.79x0.9 | B40,C45 | no | snow variant [foliage] |
| `/Game/Env/Bio/Tree/DouglasFir/Tree_DouglasFir_SnowDead_A/Meshes/SM_Tree_DouglasFir_SnowDead_A_Tubes_18` | StaticMesh | 0.01 | 77 | 0.66x0.64x1.14 | B40,C45 | no | snow variant [foliage] |
| `/Game/Env/Bio/Tree/DouglasFir/Tree_DouglasFir_SnowDead_A/Meshes/SM_Tree_DouglasFir_SnowDead_A_Tubes_19` | StaticMesh | 0.01 | 81 | 0.58x0.82x0.72 | B40,C45 | no | snow variant [foliage] |
| `/Game/Env/Bio/Tree/DouglasFir/Tree_DouglasFir_SnowDead_A/Meshes/SM_Tree_DouglasFir_SnowDead_A_Tubes_2` | StaticMesh | 1.52 | 42,104 | 6.68x11.73x10.7 | B40,C45 | no | snow variant [foliage] |
| `/Game/Env/Bio/Tree/DouglasFir/Tree_DouglasFir_SnowDead_A/Meshes/SM_Tree_DouglasFir_SnowDead_A_Tubes_20` | StaticMesh | 0.01 | 81 | 0.43x0.82x0.68 | B40,C45 | no | snow variant [foliage] |
| `/Game/Env/Bio/Tree/DouglasFir/Tree_DouglasFir_SnowDead_A/Meshes/SM_Tree_DouglasFir_SnowDead_A_Tubes_21` | StaticMesh | 0.01 | 98 | 0.54x0.93x0.68 | B40,C45 | no | snow variant [foliage] |
| `/Game/Env/Bio/Tree/DouglasFir/Tree_DouglasFir_SnowDead_A/Meshes/SM_Tree_DouglasFir_SnowDead_A_Tubes_3` | StaticMesh | 1.30 | 35,694 | 7.97x7.41x12.96 | B40,C45 | no | snow variant [foliage] |
| `/Game/Env/Bio/Tree/DouglasFir/Tree_DouglasFir_SnowDead_A/Meshes/SM_Tree_DouglasFir_SnowDead_A_Tubes_4` | StaticMesh | 0.31 | 7,957 | 2.3x3.07x4.52 | B40,C45 | no | snow variant [foliage] |
| `/Game/Env/Bio/Tree/DouglasFir/Tree_DouglasFir_SnowDead_A/Meshes/SM_Tree_DouglasFir_SnowDead_A_Tubes_5` | StaticMesh | 0.32 | 8,229 | 2.8x2.43x4.09 | B40,C45 | no | snow variant [foliage] |
| `/Game/Env/Bio/Tree/DouglasFir/Tree_DouglasFir_SnowDead_A/Meshes/SM_Tree_DouglasFir_SnowDead_A_Tubes_6` | StaticMesh | 1.34 | 36,823 | 10.44x7.73x10.76 | B40,C45 | no | snow variant [foliage] |
| `/Game/Env/Bio/Tree/DouglasFir/Tree_DouglasFir_SnowDead_A/Meshes/SM_Tree_DouglasFir_SnowDead_A_Tubes_7` | StaticMesh | 1.17 | 32,292 | 7.13x9.67x10.26 | B40,C45 | no | snow variant [foliage] |
| `/Game/Env/Bio/Tree/DouglasFir/Tree_DouglasFir_SnowDead_A/Meshes/SM_Tree_DouglasFir_SnowDead_A_Tubes_8` | StaticMesh | 0.79 | 21,227 | 6.67x6.53x8.85 | B40,C45 | no | snow variant [foliage] |
| `/Game/Env/Bio/Tree/DouglasFir/Tree_DouglasFir_SnowDead_A/Meshes/SM_Tree_DouglasFir_SnowDead_A_Tubes_9` | StaticMesh | 0.64 | 16,900 | 2.88x6.7x5.71 | B40,C45 | no | snow variant [foliage] |
| `/Game/Env/Bio/Tree/DouglasFir/Tree_DouglasFir_SnowDead_B/Meshes/PLAY_SM_Tree_DouglasFir_SnowDead_B_CollisionMesh` | StaticMesh | 0.67 |  |  | B40 | no | snow variant; collision proxy mesh [foliage] |
| `/Game/Env/Bio/Tree/DouglasFir/Tree_DouglasFir_SnowDead_B/Meshes/SM_Tree_DouglasFir_SnowDead_B_Trunk_Tube` | StaticMesh | 7.81 | 201,920 | 5.76x5.89x38.5 | B40,C45 | no | snow variant [foliage] |
| `/Game/Env/Bio/Tree/DouglasFir/Tree_DouglasFir_SnowDead_B/Meshes/SM_Tree_DouglasFir_SnowDead_B_Tubes` | StaticMesh | 0.73 | 21,722 | 8.94x13.29x13.82 | B40,C45 | no | snow variant [foliage] |
| `/Game/Env/Bio/Tree/DouglasFir/Tree_DouglasFir_SnowDead_B/Meshes/SM_Tree_DouglasFir_SnowDead_B_Tubes_10` | StaticMesh | 0.48 | 14,056 | 8.74x5.78x11.91 | B40,C45 | no | snow variant [foliage] |
| `/Game/Env/Bio/Tree/DouglasFir/Tree_DouglasFir_SnowDead_B/Meshes/SM_Tree_DouglasFir_SnowDead_B_Tubes_11` | StaticMesh | 0.03 | 796 | 1.1x1.22x1.41 | B40,C45 | no | snow variant [foliage] |
| `/Game/Env/Bio/Tree/DouglasFir/Tree_DouglasFir_SnowDead_B/Meshes/SM_Tree_DouglasFir_SnowDead_B_Tubes_12` | StaticMesh | 0.03 | 796 | 1.25x1.2x1.54 | B40,C45 | no | snow variant [foliage] |
| `/Game/Env/Bio/Tree/DouglasFir/Tree_DouglasFir_SnowDead_B/Meshes/SM_Tree_DouglasFir_SnowDead_B_Tubes_2` | StaticMesh | 0.65 | 19,318 | 15.23x12.8x16.9 | B40,C45 | no | snow variant [foliage] |
| `/Game/Env/Bio/Tree/DouglasFir/Tree_DouglasFir_SnowDead_B/Meshes/SM_Tree_DouglasFir_SnowDead_B_Tubes_3` | StaticMesh | 0.61 | 17,961 | 16.09x11.68x13.24 | B40,C45 | no | snow variant [foliage] |
| `/Game/Env/Bio/Tree/DouglasFir/Tree_DouglasFir_SnowDead_B/Meshes/SM_Tree_DouglasFir_SnowDead_B_Tubes_4` | StaticMesh | 0.36 | 10,646 | 13.65x12.49x12.49 | B40,C45 | no | snow variant [foliage] |
| `/Game/Env/Bio/Tree/DouglasFir/Tree_DouglasFir_SnowDead_B/Meshes/SM_Tree_DouglasFir_SnowDead_B_Tubes_5` | StaticMesh | 0.51 | 15,298 | 15.44x15.11x15.63 | B40,C45 | no | snow variant [foliage] |
| `/Game/Env/Bio/Tree/DouglasFir/Tree_DouglasFir_SnowDead_B/Meshes/SM_Tree_DouglasFir_SnowDead_B_Tubes_6` | StaticMesh | 0.64 | 19,069 | 20.29x24.91x30.67 | B40,C45 | no | snow variant [foliage] |
| `/Game/Env/Bio/Tree/DouglasFir/Tree_DouglasFir_SnowDead_B/Meshes/SM_Tree_DouglasFir_SnowDead_B_Tubes_7` | StaticMesh | 0.43 | 12,930 | 16.1x14.05x15.05 | B40,C45 | no | snow variant [foliage] |
| `/Game/Env/Bio/Tree/DouglasFir/Tree_DouglasFir_SnowDead_B/Meshes/SM_Tree_DouglasFir_SnowDead_B_Tubes_8` | StaticMesh | 0.37 | 11,123 | 12.73x13.32x16.03 | B40,C45 | no | snow variant [foliage] |
| `/Game/Env/Bio/Tree/DouglasFir/Tree_DouglasFir_SnowDead_B/Meshes/SM_Tree_DouglasFir_SnowDead_B_Tubes_9` | StaticMesh | 0.30 | 8,925 | 15.49x13.05x16.54 | B40,C45 | no | snow variant [foliage] |
| `/Game/Env/Bio/Tree/DouglasFir/Tree_DouglasFir_SnowDead_C/Materials/MI_bark_Mat_LOD0` | MaterialInstance | 0.00 |  |  | B40,C45 | no | [foliage] |
| `/Game/Env/Bio/Tree/DouglasFir/Tree_DouglasFir_SnowDead_C/Meshes/PLAY_SM_Tree_DouglasFir_SnowDead_C_CollisionMesh` | StaticMesh | 0.49 |  |  | B40 | no | snow variant; collision proxy mesh [foliage] |
| `/Game/Env/Bio/Tree/DouglasFir/Tree_DouglasFir_SnowDead_C/Meshes/SM_Tree_DouglasFir_SnowDead_C_Trunk_Tube` | StaticMesh | 7.62 | 200,034 | 3.6x3.52x19.83 | B40,C45 | no | snow variant [foliage] |
| `/Game/Env/Bio/Tree/DouglasFir/Tree_DouglasFir_SnowDead_C/Meshes/SM_Tree_DouglasFir_SnowDead_C_Tubes` | StaticMesh | 0.52 | 13,869 | 5.83x5.39x6.52 | B40,C45 | no | snow variant [foliage] |
| `/Game/Env/Bio/Tree/DouglasFir/Tree_DouglasFir_SnowDead_C/Meshes/SM_Tree_DouglasFir_SnowDead_C_Tubes_10` | StaticMesh | 0.38 | 10,122 | 5.65x3.91x6.7 | B40,C45 | no | snow variant [foliage] |
| `/Game/Env/Bio/Tree/DouglasFir/Tree_DouglasFir_SnowDead_C/Meshes/SM_Tree_DouglasFir_SnowDead_C_Tubes_11` | StaticMesh | 0.31 | 8,272 | 4.41x4.43x7.49 | B40,C45 | no | snow variant [foliage] |
| `/Game/Env/Bio/Tree/DouglasFir/Tree_DouglasFir_SnowDead_C/Meshes/SM_Tree_DouglasFir_SnowDead_C_Tubes_12` | StaticMesh | 0.47 | 12,369 | 4.4x6.27x7.5 | B40,C45 | no | snow variant [foliage] |
| `/Game/Env/Bio/Tree/DouglasFir/Tree_DouglasFir_SnowDead_C/Meshes/SM_Tree_DouglasFir_SnowDead_C_Tubes_13` | StaticMesh | 0.47 | 12,045 | 6.54x5.04x5.53 | B40,C45 | no | snow variant [foliage] |
| `/Game/Env/Bio/Tree/DouglasFir/Tree_DouglasFir_SnowDead_C/Meshes/SM_Tree_DouglasFir_SnowDead_C_Tubes_14` | StaticMesh | 0.29 | 7,569 | 3.38x6.81x4.69 | B40,C45 | no | snow variant [foliage] |
| `/Game/Env/Bio/Tree/DouglasFir/Tree_DouglasFir_SnowDead_C/Meshes/SM_Tree_DouglasFir_SnowDead_C_Tubes_15` | StaticMesh | 0.41 | 10,864 | 5.4x5.78x6.73 | B40,C45 | no | snow variant [foliage] |
| `/Game/Env/Bio/Tree/DouglasFir/Tree_DouglasFir_SnowDead_C/Meshes/SM_Tree_DouglasFir_SnowDead_C_Tubes_2` | StaticMesh | 0.10 | 2,795 | 0.58x0.58x0.63 | B40,C45 | no | snow variant [foliage] |
| `/Game/Env/Bio/Tree/DouglasFir/Tree_DouglasFir_SnowDead_C/Meshes/SM_Tree_DouglasFir_SnowDead_C_Tubes_3` | StaticMesh | 0.01 | 147 | 0.67x1.16x1.29 | B40,C45 | no | snow variant [foliage] |
| `/Game/Env/Bio/Tree/DouglasFir/Tree_DouglasFir_SnowDead_C/Meshes/SM_Tree_DouglasFir_SnowDead_C_Tubes_4` | StaticMesh | 0.10 | 2,795 | 0.75x0.52x0.8 | B40,C45 | no | snow variant [foliage] |
| `/Game/Env/Bio/Tree/DouglasFir/Tree_DouglasFir_SnowDead_C/Meshes/SM_Tree_DouglasFir_SnowDead_C_Tubes_5` | StaticMesh | 0.01 | 129 | 0.85x0.53x0.59 | B40,C45 | no | snow variant [foliage] |
| `/Game/Env/Bio/Tree/DouglasFir/Tree_DouglasFir_SnowDead_C/Meshes/SM_Tree_DouglasFir_SnowDead_C_Tubes_6` | StaticMesh | 0.01 | 117 | 0.78x0.52x0.66 | B40,C45 | no | snow variant [foliage] |
| `/Game/Env/Bio/Tree/DouglasFir/Tree_DouglasFir_SnowDead_C/Meshes/SM_Tree_DouglasFir_SnowDead_C_Tubes_7` | StaticMesh | 0.01 | 81 | 0.53x0.58x0.83 | B40,C45 | no | snow variant [foliage] |
| `/Game/Env/Bio/Tree/DouglasFir/Tree_DouglasFir_SnowDead_C/Meshes/SM_Tree_DouglasFir_SnowDead_C_Tubes_8` | StaticMesh | 0.01 | 99 | 0.68x0.41x0.95 | B40,C45 | no | snow variant [foliage] |
| `/Game/Env/Bio/Tree/DouglasFir/Tree_DouglasFir_SnowDead_C/Meshes/SM_Tree_DouglasFir_SnowDead_C_Tubes_9` | StaticMesh | 0.01 | 147 | 0.56x0.87x1.57 | B40,C45 | no | snow variant [foliage] |

*Group note:* Multi-part tree assets (trunk + branch cards); catalogued per mesh, assemble at recipe level

### Pine family (Env/Bio/Tree/Pine) (472)

*Where on PWR:* Pine forests: windswept, dead and sapling variants; deciduous sets for valley floor

| path | kind | MB | verts | bounds m | levels | PWR | note |
|---|---|---|---|---|---|---|---|
| `/Game/Env/Bio/Tree/Pine/Shared_Resources/Tree_Deciduous/MI_Branch_Deciduous` | MaterialInstance | 0.03 |  |  | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Deciduous/InstanceMeshDefinitions/SM_Tree_Deciduous_Tree_Deciduous_Branch_A` | StaticMesh | 0.06 | 1,406 | 6.76x10.04x4.82 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Deciduous/InstanceMeshDefinitions/SM_Tree_Deciduous_Tree_Deciduous_Branch_A_Proxy` | StaticMesh | 0.05 | 754 | 6.07x8.68x4.15 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Deciduous/Materials/MI_Material_Mat_LOD0_TwoSided` | MaterialInstance | 0.03 |  |  | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Deciduous/Meshes/SM_Tree_Deciduous_Bifurcating_10` | StaticMesh | 0.04 | 740 | 233.55x201.86x341.66 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Deciduous/Meshes/SM_Tree_Deciduous_Bifurcating_11` | StaticMesh | 0.03 | 540 | 125.87x193.86x399.81 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Deciduous/Meshes/SM_Tree_Deciduous_Bifurcating_12` | StaticMesh | 0.03 | 684 | 270.83x312.04x468.3 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Deciduous/Meshes/SM_Tree_Deciduous_Bifurcating_13` | StaticMesh | 0.04 | 736 | 290.32x288.56x539.46 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Deciduous/Meshes/SM_Tree_Deciduous_Bifurcating_14` | StaticMesh | 0.03 | 752 | 297.16x260.24x476.58 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Deciduous/Meshes/SM_Tree_Deciduous_Bifurcating_15` | StaticMesh | 0.02 | 452 | 192.35x320.33x418.42 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Deciduous/Meshes/SM_Tree_Deciduous_Bifurcating_16` | StaticMesh | 0.04 | 885 | 308.65x378.41x629.99 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Deciduous/Meshes/SM_Tree_Deciduous_Bifurcating_17` | StaticMesh | 0.03 | 728 | 337.33x246.25x492.41 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Deciduous/Meshes/SM_Tree_Deciduous_Bifurcating_18` | StaticMesh | 0.03 | 628 | 343.14x349.39x475.87 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Deciduous/Meshes/SM_Tree_Deciduous_Bifurcating_19` | StaticMesh | 0.04 | 793 | 355.17x324.82x645.22 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Deciduous/Meshes/SM_Tree_Deciduous_Bifurcating_2` | StaticMesh | 0.03 | 832 | 104.47x55.35x273.17 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Deciduous/Meshes/SM_Tree_Deciduous_Bifurcating_20` | StaticMesh | 0.03 | 732 | 356.9x385.93x569.66 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Deciduous/Meshes/SM_Tree_Deciduous_Bifurcating_21` | StaticMesh | 0.03 | 784 | 409.34x304.04x477.27 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Deciduous/Meshes/SM_Tree_Deciduous_Bifurcating_22` | StaticMesh | 0.04 | 924 | 345.94x274.01x611.68 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Deciduous/Meshes/SM_Tree_Deciduous_Bifurcating_23` | StaticMesh | 0.03 | 696 | 355.33x329.96x579.04 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Deciduous/Meshes/SM_Tree_Deciduous_Bifurcating_24` | StaticMesh | 0.03 | 700 | 341.3x311.3x511.72 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Deciduous/Meshes/SM_Tree_Deciduous_Bifurcating_25` | StaticMesh | 0.04 | 874 | 380.07x438.06x438.72 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Deciduous/Meshes/SM_Tree_Deciduous_Bifurcating_26` | StaticMesh | 0.03 | 656 | 355.07x322.4x503.62 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Deciduous/Meshes/SM_Tree_Deciduous_Bifurcating_27` | StaticMesh | 0.04 | 966 | 365.6x332.71x557.42 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Deciduous/Meshes/SM_Tree_Deciduous_Bifurcating_28` | StaticMesh | 0.04 | 820 | 374.46x425.99x491.68 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Deciduous/Meshes/SM_Tree_Deciduous_Bifurcating_29` | StaticMesh | 0.04 | 1,016 | 417.17x408.92x472.69 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Deciduous/Meshes/SM_Tree_Deciduous_Bifurcating_3` | StaticMesh | 0.03 | 776 | 167.89x183.24x329.2 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Deciduous/Meshes/SM_Tree_Deciduous_Bifurcating_30` | StaticMesh | 0.03 | 764 | 414.33x469.56x357.98 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Deciduous/Meshes/SM_Tree_Deciduous_Bifurcating_31` | StaticMesh | 0.04 | 845 | 445.44x461.29x461.88 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Deciduous/Meshes/SM_Tree_Deciduous_Bifurcating_32` | StaticMesh | 0.05 | 1,090 | 433.92x460.48x499.14 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Deciduous/Meshes/SM_Tree_Deciduous_Bifurcating_33` | StaticMesh | 0.04 | 868 | 446.93x422.83x428.19 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Deciduous/Meshes/SM_Tree_Deciduous_Bifurcating_34` | StaticMesh | 0.04 | 940 | 447.09x388.34x536.61 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Deciduous/Meshes/SM_Tree_Deciduous_Bifurcating_35` | StaticMesh | 0.04 | 837 | 387.86x554.24x615.11 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Deciduous/Meshes/SM_Tree_Deciduous_Bifurcating_36` | StaticMesh | 0.04 | 884 | 425.91x479.29x553.79 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Deciduous/Meshes/SM_Tree_Deciduous_Bifurcating_37` | StaticMesh | 0.04 | 800 | 430.54x509.74x476.42 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Deciduous/Meshes/SM_Tree_Deciduous_Bifurcating_38` | StaticMesh | 0.04 | 1,036 | 460.89x479.08x600.36 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Deciduous/Meshes/SM_Tree_Deciduous_Bifurcating_39` | StaticMesh | 0.03 | 770 | 444.51x467.83x466.33 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Deciduous/Meshes/SM_Tree_Deciduous_Bifurcating_4` | StaticMesh | 0.04 | 812 | 234.55x167.49x412.16 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Deciduous/Meshes/SM_Tree_Deciduous_Bifurcating_40` | StaticMesh | 0.05 | 1,032 | 494.08x508.93x572.22 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Deciduous/Meshes/SM_Tree_Deciduous_Bifurcating_41` | StaticMesh | 0.05 | 1,104 | 466.81x551.26x559.01 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Deciduous/Meshes/SM_Tree_Deciduous_Bifurcating_42` | StaticMesh | 0.05 | 1,246 | 451.47x524.16x647.49 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Deciduous/Meshes/SM_Tree_Deciduous_Bifurcating_43` | StaticMesh | 0.04 | 926 | 477.58x384.53x483.98 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Deciduous/Meshes/SM_Tree_Deciduous_Bifurcating_44` | StaticMesh | 0.04 | 884 | 516.66x504.57x490.88 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Deciduous/Meshes/SM_Tree_Deciduous_Bifurcating_45` | StaticMesh | 0.04 | 992 | 431.73x508.09x439.24 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Deciduous/Meshes/SM_Tree_Deciduous_Bifurcating_46` | StaticMesh | 0.05 | 1,032 | 543.92x496.15x422.21 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Deciduous/Meshes/SM_Tree_Deciduous_Bifurcating_47` | StaticMesh | 0.04 | 904 | 573.98x481.18x566.16 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Deciduous/Meshes/SM_Tree_Deciduous_Bifurcating_48` | StaticMesh | 0.04 | 866 | 543.14x731.67x672.01 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Deciduous/Meshes/SM_Tree_Deciduous_Bifurcating_49` | StaticMesh | 0.04 | 778 | 672.03x551.26x419.95 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Deciduous/Meshes/SM_Tree_Deciduous_Bifurcating_5` | StaticMesh | 0.04 | 976 | 173.1x227.72x502.98 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Deciduous/Meshes/SM_Tree_Deciduous_Bifurcating_50` | StaticMesh | 0.05 | 1,008 | 732.53x616.07x635.96 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Deciduous/Meshes/SM_Tree_Deciduous_Bifurcating_51` | StaticMesh | 0.04 | 900 | 569.95x719.36x717.44 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Deciduous/Meshes/SM_Tree_Deciduous_Bifurcating_52` | StaticMesh | 0.04 | 826 | 614.1x717.64x593.04 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Deciduous/Meshes/SM_Tree_Deciduous_Bifurcating_53` | StaticMesh | 0.03 | 642 | 567.93x559.51x453.02 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Deciduous/Meshes/SM_Tree_Deciduous_Bifurcating_54` | StaticMesh | 0.05 | 960 | 675.25x472.69x490.53 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Deciduous/Meshes/SM_Tree_Deciduous_Bifurcating_55` | StaticMesh | 0.04 | 816 | 604.87x688.34x559.02 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Deciduous/Meshes/SM_Tree_Deciduous_Bifurcating_6` | StaticMesh | 0.02 | 532 | 134.39x106.9x278.93 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Deciduous/Meshes/SM_Tree_Deciduous_Bifurcating_7` | StaticMesh | 0.02 | 512 | 29.85x41.14x220.65 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Deciduous/Meshes/SM_Tree_Deciduous_Bifurcating_8` | StaticMesh | 0.02 | 512 | 179.84x113.34x447.76 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Deciduous/Meshes/SM_Tree_Deciduous_Bifurcating_9` | StaticMesh | 0.04 | 776 | 202.46x190.59x380.36 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Deciduous/Meshes/SM_Tree_Deciduous_Trunk_2` | StaticMesh | 7.39 | 152,915 | 174.31x185.9x2543.93 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_DeciduousDead/Meshes/SM_Tree_DeciduousDead_Big_2` | StaticMesh | 0.02 | 522 | 0.63x0.35x0.73 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_DeciduousDead/Meshes/SM_Tree_DeciduousDead_Big_3` | StaticMesh | 0.02 | 506 | 0.35x0.39x0.72 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_DeciduousDead/Meshes/SM_Tree_DeciduousDead_Big_4` | StaticMesh | 0.02 | 586 | 0.27x0.55x0.62 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_DeciduousDead/Meshes/SM_Tree_DeciduousDead_Big_5` | StaticMesh | 0.03 | 858 | 0.45x0.46x0.65 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_DeciduousDead/Meshes/SM_Tree_DeciduousDead_Big_6` | StaticMesh | 0.02 | 442 | 0.28x0.3x0.43 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_DeciduousDead/Meshes/SM_Tree_DeciduousDead_Trunk` | StaticMesh | 7.58 | 197,766 | 2.66x2.77x4.35 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_DeciduousDead/Meshes/SM_Tree_DeciduousDead_Trunk_2` | StaticMesh | 0.01 | 135 | 0.22x0.18x0.15 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_DeciduousDead/Meshes/SM_Tree_DeciduousDead_Trunk_3` | StaticMesh | 0.01 | 135 | 0.16x0.24x0.13 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_DeciduousDead/Meshes/SM_Tree_DeciduousDead_Trunk_4` | StaticMesh | 0.01 | 135 | 0.19x0.23x0.13 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_DeciduousDead/Meshes/SM_Tree_DeciduousDead_Trunk_5` | StaticMesh | 0.27 | 8,075 | 1.67x1.54x1.04 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_DeciduousDead/Meshes/SM_Tree_DeciduousDead_Trunk_6` | StaticMesh | 18.94 | 482,523 | 16.85x13.07x25.88 | A30 | no | very dense: confirm Nanite before placing many [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Deciduous_B/Meshes/SM_Tree_Deciduous_B_Tree_Deciduous_Big_Branches` | StaticMesh | 0.01 | 229 | 50.29x44.33x115.96 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Deciduous_B/Meshes/SM_Tree_Deciduous_B_Tree_Deciduous_Big_Branches_10` | StaticMesh | 0.07 | 1,468 | 434.93x356.09x315.59 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Deciduous_B/Meshes/SM_Tree_Deciduous_B_Tree_Deciduous_Big_Branches_11` | StaticMesh | 0.03 | 591 | 224.22x278.98x218.55 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Deciduous_B/Meshes/SM_Tree_Deciduous_B_Tree_Deciduous_Big_Branches_12` | StaticMesh | 0.11 | 2,302 | 547.27x478.79x519.71 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Deciduous_B/Meshes/SM_Tree_Deciduous_B_Tree_Deciduous_Big_Branches_13` | StaticMesh | 0.09 | 1,787 | 426.91x518.04x407.07 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Deciduous_B/Meshes/SM_Tree_Deciduous_B_Tree_Deciduous_Big_Branches_14` | StaticMesh | 0.08 | 1,715 | 393.63x561.5x346.19 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Deciduous_B/Meshes/SM_Tree_Deciduous_B_Tree_Deciduous_Big_Branches_15` | StaticMesh | 0.17 | 3,709 | 592.47x787.87x510.98 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Deciduous_B/Meshes/SM_Tree_Deciduous_B_Tree_Deciduous_Big_Branches_16` | StaticMesh | 0.14 | 2,872 | 841.23x498.82x210.61 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Deciduous_B/Meshes/SM_Tree_Deciduous_B_Tree_Deciduous_Big_Branches_17` | StaticMesh | 0.11 | 2,369 | 546.8x605.46x451.69 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Deciduous_B/Meshes/SM_Tree_Deciduous_B_Tree_Deciduous_Big_Branches_18` | StaticMesh | 0.14 | 2,843 | 502.86x665.27x407.98 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Deciduous_B/Meshes/SM_Tree_Deciduous_B_Tree_Deciduous_Big_Branches_19` | StaticMesh | 0.11 | 2,392 | 799.67x543.65x467.12 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Deciduous_B/Meshes/SM_Tree_Deciduous_B_Tree_Deciduous_Big_Branches_2` | StaticMesh | 0.05 | 1,034 | 286.21x285.45x462.31 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Deciduous_B/Meshes/SM_Tree_Deciduous_B_Tree_Deciduous_Big_Branches_20` | StaticMesh | 0.12 | 2,552 | 698.53x461.09x337.53 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Deciduous_B/Meshes/SM_Tree_Deciduous_B_Tree_Deciduous_Big_Branches_21` | StaticMesh | 0.12 | 2,533 | 472.3x636.58x244.51 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Deciduous_B/Meshes/SM_Tree_Deciduous_B_Tree_Deciduous_Big_Branches_22` | StaticMesh | 0.08 | 1,763 | 600.15x413.12x276.41 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Deciduous_B/Meshes/SM_Tree_Deciduous_B_Tree_Deciduous_Big_Branches_23` | StaticMesh | 0.04 | 834 | 436.47x418.37x321.73 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Deciduous_B/Meshes/SM_Tree_Deciduous_B_Tree_Deciduous_Big_Branches_24` | StaticMesh | 0.03 | 587 | 423.81x225.67x323.9 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Deciduous_B/Meshes/SM_Tree_Deciduous_B_Tree_Deciduous_Big_Branches_25` | StaticMesh | 0.05 | 1,081 | 528.93x527.73x408.42 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Deciduous_B/Meshes/SM_Tree_Deciduous_B_Tree_Deciduous_Big_Branches_26` | StaticMesh | 0.11 | 2,317 | 592.69x565.63x309.33 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Deciduous_B/Meshes/SM_Tree_Deciduous_B_Tree_Deciduous_Big_Branches_27` | StaticMesh | 0.15 | 3,230 | 680.83x615.23x362.06 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Deciduous_B/Meshes/SM_Tree_Deciduous_B_Tree_Deciduous_Big_Branches_28` | StaticMesh | 0.04 | 801 | 542.29x286.42x279.07 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Deciduous_B/Meshes/SM_Tree_Deciduous_B_Tree_Deciduous_Big_Branches_29` | StaticMesh | 0.11 | 2,433 | 733.14x486.25x353.68 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Deciduous_B/Meshes/SM_Tree_Deciduous_B_Tree_Deciduous_Big_Branches_3` | StaticMesh | 0.11 | 2,347 | 585.59x449.77x422.73 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Deciduous_B/Meshes/SM_Tree_Deciduous_B_Tree_Deciduous_Big_Branches_30` | StaticMesh | 0.12 | 2,675 | 533.78x789.53x358.84 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Deciduous_B/Meshes/SM_Tree_Deciduous_B_Tree_Deciduous_Big_Branches_31` | StaticMesh | 0.09 | 1,725 | 560.26x559.42x364.93 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Deciduous_B/Meshes/SM_Tree_Deciduous_B_Tree_Deciduous_Big_Branches_32` | StaticMesh | 0.16 | 3,379 | 583.6x787.08x359.48 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Deciduous_B/Meshes/SM_Tree_Deciduous_B_Tree_Deciduous_Big_Branches_33` | StaticMesh | 0.01 | 232 | 31.95x43.06x20.13 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Deciduous_B/Meshes/SM_Tree_Deciduous_B_Tree_Deciduous_Big_Branches_34` | StaticMesh | 0.02 | 367 | 344.75x218.31x313.31 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Deciduous_B/Meshes/SM_Tree_Deciduous_B_Tree_Deciduous_Big_Branches_35` | StaticMesh | 0.02 | 368 | 391.54x196.84x322.7 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Deciduous_B/Meshes/SM_Tree_Deciduous_B_Tree_Deciduous_Big_Branches_36` | StaticMesh | 0.02 | 297 | 216.54x300.89x333.88 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Deciduous_B/Meshes/SM_Tree_Deciduous_B_Tree_Deciduous_Big_Branches_37` | StaticMesh | 0.02 | 373 | 262.33x418.79x311.18 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Deciduous_B/Meshes/SM_Tree_Deciduous_B_Tree_Deciduous_Big_Branches_38` | StaticMesh | 0.02 | 363 | 302.15x192.52x317.62 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Deciduous_B/Meshes/SM_Tree_Deciduous_B_Tree_Deciduous_Big_Branches_39` | StaticMesh | 0.02 | 367 | 302.77x261.95x313.67 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Deciduous_B/Meshes/SM_Tree_Deciduous_B_Tree_Deciduous_Big_Branches_4` | StaticMesh | 0.04 | 768 | 300.39x300.87x297.27 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Deciduous_B/Meshes/SM_Tree_Deciduous_B_Tree_Deciduous_Big_Branches_40` | StaticMesh | 0.02 | 314 | 183.85x198.19x338.64 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Deciduous_B/Meshes/SM_Tree_Deciduous_B_Tree_Deciduous_Big_Branches_41` | StaticMesh | 0.02 | 326 | 241.96x196.38x341.59 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Deciduous_B/Meshes/SM_Tree_Deciduous_B_Tree_Deciduous_Big_Branches_42` | StaticMesh | 0.02 | 383 | 359.9x579.89x318.46 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Deciduous_B/Meshes/SM_Tree_Deciduous_B_Tree_Deciduous_Big_Branches_43` | StaticMesh | 0.02 | 384 | 235.66x622.78x277.72 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Deciduous_B/Meshes/SM_Tree_Deciduous_B_Tree_Deciduous_Big_Branches_44` | StaticMesh | 0.02 | 344 | 264.74x233.47x322.31 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Deciduous_B/Meshes/SM_Tree_Deciduous_B_Tree_Deciduous_Big_Branches_45` | StaticMesh | 0.02 | 358 | 254.83x365.49x307.64 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Deciduous_B/Meshes/SM_Tree_Deciduous_B_Tree_Deciduous_Big_Branches_46` | StaticMesh | 0.02 | 304 | 278.98x269.85x332.26 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Deciduous_B/Meshes/SM_Tree_Deciduous_B_Tree_Deciduous_Big_Branches_47` | StaticMesh | 0.02 | 266 | 218.58x213.72x317.52 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Deciduous_B/Meshes/SM_Tree_Deciduous_B_Tree_Deciduous_Big_Branches_48` | StaticMesh | 0.02 | 342 | 253.35x460.93x319.29 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Deciduous_B/Meshes/SM_Tree_Deciduous_B_Tree_Deciduous_Big_Branches_49` | StaticMesh | 0.02 | 378 | 489.31x245.86x365.26 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Deciduous_B/Meshes/SM_Tree_Deciduous_B_Tree_Deciduous_Big_Branches_5` | StaticMesh | 0.09 | 1,825 | 461.51x406.57x310.88 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Deciduous_B/Meshes/SM_Tree_Deciduous_B_Tree_Deciduous_Big_Branches_50` | StaticMesh | 0.02 | 364 | 269.35x312.9x360.79 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Deciduous_B/Meshes/SM_Tree_Deciduous_B_Tree_Deciduous_Big_Branches_51` | StaticMesh | 0.02 | 344 | 228.94x273.09x365.98 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Deciduous_B/Meshes/SM_Tree_Deciduous_B_Tree_Deciduous_Big_Branches_52` | StaticMesh | 0.02 | 379 | 448.45x548.0x343.22 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Deciduous_B/Meshes/SM_Tree_Deciduous_B_Tree_Deciduous_Big_Branches_53` | StaticMesh | 0.02 | 326 | 204.84x233.77x318.35 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Deciduous_B/Meshes/SM_Tree_Deciduous_B_Tree_Deciduous_Big_Branches_54` | StaticMesh | 0.02 | 358 | 289.37x217.91x328.59 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Deciduous_B/Meshes/SM_Tree_Deciduous_B_Tree_Deciduous_Big_Branches_55` | StaticMesh | 0.02 | 378 | 369.61x460.85x316.83 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Deciduous_B/Meshes/SM_Tree_Deciduous_B_Tree_Deciduous_Big_Branches_56` | StaticMesh | 0.02 | 372 | 221.29x450.3x347.46 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Deciduous_B/Meshes/SM_Tree_Deciduous_B_Tree_Deciduous_Big_Branches_57` | StaticMesh | 0.02 | 297 | 230.18x262.51x339.84 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Deciduous_B/Meshes/SM_Tree_Deciduous_B_Tree_Deciduous_Big_Branches_58` | StaticMesh | 0.02 | 372 | 404.78x218.81x357.45 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Deciduous_B/Meshes/SM_Tree_Deciduous_B_Tree_Deciduous_Big_Branches_59` | StaticMesh | 0.05 | 1,072 | 251.25x386.08x246.39 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Deciduous_B/Meshes/SM_Tree_Deciduous_B_Tree_Deciduous_Big_Branches_6` | StaticMesh | 0.09 | 1,778 | 427.76x511.84x259.5 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Deciduous_B/Meshes/SM_Tree_Deciduous_B_Tree_Deciduous_Big_Branches_60` | StaticMesh | 0.23 | 5,117 | 788.26x854.58x463.53 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Deciduous_B/Meshes/SM_Tree_Deciduous_B_Tree_Deciduous_Big_Branches_61` | StaticMesh | 0.16 | 3,552 | 748.26x517.14x296.87 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Deciduous_B/Meshes/SM_Tree_Deciduous_B_Tree_Deciduous_Big_Branches_62` | StaticMesh | 0.20 | 4,579 | 905.92x686.96x377.03 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Deciduous_B/Meshes/SM_Tree_Deciduous_B_Tree_Deciduous_Big_Branches_63` | StaticMesh | 0.07 | 1,546 | 294.73x565.24x266.57 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Deciduous_B/Meshes/SM_Tree_Deciduous_B_Tree_Deciduous_Big_Branches_64` | StaticMesh | 0.13 | 2,776 | 629.46x544.11x287.25 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Deciduous_B/Meshes/SM_Tree_Deciduous_B_Tree_Deciduous_Big_Branches_65` | StaticMesh | 0.02 | 306 | 39.51x46.49x160.76 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Deciduous_B/Meshes/SM_Tree_Deciduous_B_Tree_Deciduous_Big_Branches_66` | StaticMesh | 0.02 | 385 | 37.62x83.2x298.23 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Deciduous_B/Meshes/SM_Tree_Deciduous_B_Tree_Deciduous_Big_Branches_67` | StaticMesh | 0.02 | 302 | 65.2x87.0x307.68 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Deciduous_B/Meshes/SM_Tree_Deciduous_B_Tree_Deciduous_Big_Branches_68` | StaticMesh | 0.02 | 388 | 55.82x89.88x336.04 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Deciduous_B/Meshes/SM_Tree_Deciduous_B_Tree_Deciduous_Big_Branches_69` | StaticMesh | 0.02 | 381 | 106.94x45.25x296.52 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Deciduous_B/Meshes/SM_Tree_Deciduous_B_Tree_Deciduous_Big_Branches_7` | StaticMesh | 0.09 | 1,867 | 607.23x437.22x238.49 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Deciduous_B/Meshes/SM_Tree_Deciduous_B_Tree_Deciduous_Big_Branches_70` | StaticMesh | 0.19 | 4,243 | 541.51x579.42x532.87 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Deciduous_B/Meshes/SM_Tree_Deciduous_B_Tree_Deciduous_Big_Branches_8` | StaticMesh | 0.12 | 2,520 | 561.17x559.88x383.82 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Deciduous_B/Meshes/SM_Tree_Deciduous_B_Tree_Deciduous_Big_Branches_9` | StaticMesh | 0.08 | 1,627 | 497.01x377.64x475.39 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Deciduous_B/Meshes/SM_Tree_Deciduous_B_Tree_Deciduous_Trunk_Center` | StaticMesh | 0.30 | 5,616 | 291.56x327.65x2910.45 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Pine/Tree_Pine_A/Meshes/SM_Tree_Pine_A_Big_10` | StaticMesh | 0.03 | 662 | 4.6x5.37x3.68 | A30 | no | [foliage]; sibling used by PWR |
| `/Game/Env/Bio/Tree/Pine/Tree_Pine/Tree_Pine_A/Meshes/SM_Tree_Pine_A_Big_100` | StaticMesh | 0.14 | 3,931 | 28.74x24.32x10.28 | A30 | no | [foliage]; sibling used by PWR |
| `/Game/Env/Bio/Tree/Pine/Tree_Pine/Tree_Pine_A/Meshes/SM_Tree_Pine_A_Big_11` | StaticMesh | 0.22 | 5,941 | 11.38x19.92x12.95 | A30 | no | [foliage]; sibling used by PWR |
| `/Game/Env/Bio/Tree/Pine/Tree_Pine/Tree_Pine_A/Meshes/SM_Tree_Pine_A_Big_12` | StaticMesh | 0.18 | 4,824 | 20.67x13.75x11.28 | A30 | no | [foliage]; sibling used by PWR |
| `/Game/Env/Bio/Tree/Pine/Tree_Pine/Tree_Pine_A/Meshes/SM_Tree_Pine_A_Big_13` | StaticMesh | 0.06 | 1,595 | 4.13x7.66x3.73 | A30 | no | [foliage]; sibling used by PWR |
| `/Game/Env/Bio/Tree/Pine/Tree_Pine/Tree_Pine_A/Meshes/SM_Tree_Pine_A_Big_14` | StaticMesh | 0.14 | 3,628 | 12.49x13.21x13.24 | A30 | no | [foliage]; sibling used by PWR |
| `/Game/Env/Bio/Tree/Pine/Tree_Pine/Tree_Pine_A/Meshes/SM_Tree_Pine_A_Big_15` | StaticMesh | 0.09 | 2,174 | 9.43x10.24x7.1 | A30 | no | [foliage]; sibling used by PWR |
| `/Game/Env/Bio/Tree/Pine/Tree_Pine/Tree_Pine_A/Meshes/SM_Tree_Pine_A_Big_16` | StaticMesh | 0.04 | 852 | 6.05x6.91x4.84 | A30 | no | [foliage]; sibling used by PWR |
| `/Game/Env/Bio/Tree/Pine/Tree_Pine/Tree_Pine_A/Meshes/SM_Tree_Pine_A_Big_17` | StaticMesh | 0.10 | 2,643 | 7.64x8.3x6.61 | A30 | no | [foliage]; sibling used by PWR |
| `/Game/Env/Bio/Tree/Pine/Tree_Pine/Tree_Pine_A/Meshes/SM_Tree_Pine_A_Big_18` | StaticMesh | 0.23 | 6,044 | 23.9x13.37x17.82 | A30 | no | [foliage]; sibling used by PWR |
| `/Game/Env/Bio/Tree/Pine/Tree_Pine/Tree_Pine_A/Meshes/SM_Tree_Pine_A_Big_19` | StaticMesh | 0.17 | 4,665 | 9.2x15.79x8.99 | A30 | no | [foliage]; sibling used by PWR |
| `/Game/Env/Bio/Tree/Pine/Tree_Pine/Tree_Pine_A/Meshes/SM_Tree_Pine_A_Big_2` | StaticMesh | 0.03 | 565 | 2.22x2.83x1.35 | A30 | no | [foliage]; sibling used by PWR |
| `/Game/Env/Bio/Tree/Pine/Tree_Pine/Tree_Pine_A/Meshes/SM_Tree_Pine_A_Big_20` | StaticMesh | 0.15 | 4,011 | 11.62x9.75x7.91 | A30 | no | [foliage]; sibling used by PWR |
| `/Game/Env/Bio/Tree/Pine/Tree_Pine/Tree_Pine_A/Meshes/SM_Tree_Pine_A_Big_21` | StaticMesh | 0.27 | 7,474 | 13.99x24.55x14.01 | A30 | no | [foliage]; sibling used by PWR |
| `/Game/Env/Bio/Tree/Pine/Tree_Pine/Tree_Pine_A/Meshes/SM_Tree_Pine_A_Big_22` | StaticMesh | 0.09 | 2,340 | 10.85x10.26x9.06 | A30 | no | [foliage]; sibling used by PWR |
| `/Game/Env/Bio/Tree/Pine/Tree_Pine/Tree_Pine_A/Meshes/SM_Tree_Pine_A_Big_23` | StaticMesh | 0.18 | 4,835 | 13.85x13.63x8.89 | A30 | no | [foliage]; sibling used by PWR |
| `/Game/Env/Bio/Tree/Pine/Tree_Pine/Tree_Pine_A/Meshes/SM_Tree_Pine_A_Big_24` | StaticMesh | 0.22 | 6,013 | 14.05x16.63x12.54 | A30 | no | [foliage]; sibling used by PWR |
| `/Game/Env/Bio/Tree/Pine/Tree_Pine/Tree_Pine_A/Meshes/SM_Tree_Pine_A_Big_25` | StaticMesh | 0.19 | 5,195 | 18.73x16.14x11.5 | A30 | no | [foliage]; sibling used by PWR |
| `/Game/Env/Bio/Tree/Pine/Tree_Pine/Tree_Pine_A/Meshes/SM_Tree_Pine_A_Big_26` | StaticMesh | 0.18 | 4,750 | 16.49x9.31x10.4 | A30 | no | [foliage]; sibling used by PWR |
| `/Game/Env/Bio/Tree/Pine/Tree_Pine/Tree_Pine_A/Meshes/SM_Tree_Pine_A_Big_27` | StaticMesh | 0.21 | 5,690 | 14.79x21.99x12.79 | A30 | no | [foliage]; sibling used by PWR |
| `/Game/Env/Bio/Tree/Pine/Tree_Pine/Tree_Pine_A/Meshes/SM_Tree_Pine_A_Big_28` | StaticMesh | 0.09 | 2,189 | 13.99x12.13x13.55 | A30 | no | [foliage]; sibling used by PWR |
| `/Game/Env/Bio/Tree/Pine/Tree_Pine/Tree_Pine_A/Meshes/SM_Tree_Pine_A_Big_29` | StaticMesh | 0.18 | 4,807 | 12.9x23.02x12.19 | A30 | no | [foliage]; sibling used by PWR |
| `/Game/Env/Bio/Tree/Pine/Tree_Pine/Tree_Pine_A/Meshes/SM_Tree_Pine_A_Big_3` | StaticMesh | 0.03 | 732 | 3.57x3.99x2.68 | A30 | no | [foliage]; sibling used by PWR |
| `/Game/Env/Bio/Tree/Pine/Tree_Pine/Tree_Pine_A/Meshes/SM_Tree_Pine_A_Big_30` | StaticMesh | 0.12 | 2,993 | 12.04x12.65x10.89 | A30 | no | [foliage]; sibling used by PWR |
| `/Game/Env/Bio/Tree/Pine/Tree_Pine/Tree_Pine_A/Meshes/SM_Tree_Pine_A_Big_31` | StaticMesh | 0.21 | 5,450 | 19.53x17.62x16.06 | A30 | no | [foliage]; sibling used by PWR |
| `/Game/Env/Bio/Tree/Pine/Tree_Pine/Tree_Pine_A/Meshes/SM_Tree_Pine_A_Big_32` | StaticMesh | 0.19 | 5,180 | 16.62x15.82x15.03 | A30 | no | [foliage]; sibling used by PWR |
| `/Game/Env/Bio/Tree/Pine/Tree_Pine/Tree_Pine_A/Meshes/SM_Tree_Pine_A_Big_33` | StaticMesh | 0.21 | 5,460 | 21.39x22.14x15.48 | A30 | no | [foliage]; sibling used by PWR |
| `/Game/Env/Bio/Tree/Pine/Tree_Pine/Tree_Pine_A/Meshes/SM_Tree_Pine_A_Big_34` | StaticMesh | 0.18 | 4,657 | 22.0x17.22x14.52 | A30 | no | [foliage]; sibling used by PWR |
| `/Game/Env/Bio/Tree/Pine/Tree_Pine/Tree_Pine_A/Meshes/SM_Tree_Pine_A_Big_35` | StaticMesh | 0.13 | 3,351 | 12.32x17.59x11.86 | A30 | no | [foliage]; sibling used by PWR |
| `/Game/Env/Bio/Tree/Pine/Tree_Pine/Tree_Pine_A/Meshes/SM_Tree_Pine_A_Big_36` | StaticMesh | 0.12 | 2,980 | 20.67x15.36x12.49 | A30 | no | [foliage]; sibling used by PWR |
| `/Game/Env/Bio/Tree/Pine/Tree_Pine/Tree_Pine_A/Meshes/SM_Tree_Pine_A_Big_37` | StaticMesh | 0.14 | 3,488 | 13.01x16.8x11.99 | A30 | no | [foliage]; sibling used by PWR |
| `/Game/Env/Bio/Tree/Pine/Tree_Pine/Tree_Pine_A/Meshes/SM_Tree_Pine_A_Big_38` | StaticMesh | 0.18 | 4,777 | 15.29x15.06x10.8 | A30 | no | [foliage]; sibling used by PWR |
| `/Game/Env/Bio/Tree/Pine/Tree_Pine/Tree_Pine_A/Meshes/SM_Tree_Pine_A_Big_39` | StaticMesh | 0.15 | 4,052 | 19.29x22.87x18.33 | A30 | no | [foliage]; sibling used by PWR |
| `/Game/Env/Bio/Tree/Pine/Tree_Pine/Tree_Pine_A/Meshes/SM_Tree_Pine_A_Big_4` | StaticMesh | 0.05 | 1,139 | 3.58x4.21x2.91 | A30 | no | [foliage]; sibling used by PWR |
| `/Game/Env/Bio/Tree/Pine/Tree_Pine/Tree_Pine_A/Meshes/SM_Tree_Pine_A_Big_40` | StaticMesh | 0.37 | 10,281 | 25.03x24.23x22.09 | A30 | no | [foliage]; sibling used by PWR |
| `/Game/Env/Bio/Tree/Pine/Tree_Pine/Tree_Pine_A/Meshes/SM_Tree_Pine_A_Big_41` | StaticMesh | 0.29 | 7,952 | 17.37x16.75x19.47 | A30 | no | [foliage]; sibling used by PWR |
| `/Game/Env/Bio/Tree/Pine/Tree_Pine/Tree_Pine_A/Meshes/SM_Tree_Pine_A_Big_42` | StaticMesh | 0.19 | 5,048 | 25.39x16.15x14.34 | A30 | no | [foliage]; sibling used by PWR |
| `/Game/Env/Bio/Tree/Pine/Tree_Pine/Tree_Pine_A/Meshes/SM_Tree_Pine_A_Big_43` | StaticMesh | 0.16 | 4,227 | 12.9x16.51x12.85 | A30 | no | [foliage]; sibling used by PWR |
| `/Game/Env/Bio/Tree/Pine/Tree_Pine/Tree_Pine_A/Meshes/SM_Tree_Pine_A_Big_44` | StaticMesh | 0.25 | 6,500 | 28.65x18.89x24.88 | A30 | no | [foliage]; sibling used by PWR |
| `/Game/Env/Bio/Tree/Pine/Tree_Pine/Tree_Pine_A/Meshes/SM_Tree_Pine_A_Big_45` | StaticMesh | 0.26 | 6,728 | 16.94x32.86x21.47 | A30 | no | [foliage]; sibling used by PWR |
| `/Game/Env/Bio/Tree/Pine/Tree_Pine/Tree_Pine_A/Meshes/SM_Tree_Pine_A_Big_46` | StaticMesh | 0.40 | 10,319 | 14.44x20.57x13.01 | A30 | no | [foliage]; sibling used by PWR |
| `/Game/Env/Bio/Tree/Pine/Tree_Pine/Tree_Pine_A/Meshes/SM_Tree_Pine_A_Big_47` | StaticMesh | 0.44 | 11,185 | 15.98x18.72x18.3 | A30 | no | [foliage]; sibling used by PWR |
| `/Game/Env/Bio/Tree/Pine/Tree_Pine/Tree_Pine_A/Meshes/SM_Tree_Pine_A_Big_48` | StaticMesh | 0.23 | 5,875 | 23.72x9.06x14.05 | A30 | no | [foliage]; sibling used by PWR |
| `/Game/Env/Bio/Tree/Pine/Tree_Pine/Tree_Pine_A/Meshes/SM_Tree_Pine_A_Big_49` | StaticMesh | 0.23 | 6,102 | 18.67x10.15x12.73 | A30 | no | [foliage]; sibling used by PWR |
| `/Game/Env/Bio/Tree/Pine/Tree_Pine/Tree_Pine_A/Meshes/SM_Tree_Pine_A_Big_5` | StaticMesh | 0.09 | 2,387 | 6.1x6.93x4.51 | A30 | no | [foliage]; sibling used by PWR |
| `/Game/Env/Bio/Tree/Pine/Tree_Pine/Tree_Pine_A/Meshes/SM_Tree_Pine_A_Big_50` | StaticMesh | 0.28 | 7,348 | 7.76x18.62x10.43 | A30 | no | [foliage]; sibling used by PWR |
| `/Game/Env/Bio/Tree/Pine/Tree_Pine/Tree_Pine_A/Meshes/SM_Tree_Pine_A_Big_51` | StaticMesh | 0.24 | 6,399 | 11.83x12.91x9.05 | A30 | no | [foliage]; sibling used by PWR |
| `/Game/Env/Bio/Tree/Pine/Tree_Pine/Tree_Pine_A/Meshes/SM_Tree_Pine_A_Big_52` | StaticMesh | 0.37 | 9,747 | 12.25x15.48x11.64 | A30 | no | [foliage]; sibling used by PWR |
| `/Game/Env/Bio/Tree/Pine/Tree_Pine/Tree_Pine_A/Meshes/SM_Tree_Pine_A_Big_53` | StaticMesh | 0.24 | 6,300 | 12.39x19.33x14.0 | A30 | no | [foliage]; sibling used by PWR |
| `/Game/Env/Bio/Tree/Pine/Tree_Pine/Tree_Pine_A/Meshes/SM_Tree_Pine_A_Big_54` | StaticMesh | 0.17 | 4,356 | 14.68x10.0x9.26 | A30 | no | [foliage]; sibling used by PWR |
| `/Game/Env/Bio/Tree/Pine/Tree_Pine/Tree_Pine_A/Meshes/SM_Tree_Pine_A_Big_55` | StaticMesh | 0.75 | 19,683 | 24.86x10.54x14.89 | A30 | no | [foliage]; sibling used by PWR |
| `/Game/Env/Bio/Tree/Pine/Tree_Pine/Tree_Pine_A/Meshes/SM_Tree_Pine_A_Big_56` | StaticMesh | 0.73 | 19,340 | 13.82x23.41x13.73 | A30 | no | [foliage]; sibling used by PWR |
| `/Game/Env/Bio/Tree/Pine/Tree_Pine/Tree_Pine_A/Meshes/SM_Tree_Pine_A_Big_57` | StaticMesh | 0.61 | 15,957 | 21.35x20.14x11.3 | A30 | no | [foliage]; sibling used by PWR |
| `/Game/Env/Bio/Tree/Pine/Tree_Pine/Tree_Pine_A/Meshes/SM_Tree_Pine_A_Big_58` | StaticMesh | 0.28 | 7,437 | 16.37x18.59x13.88 | A30 | no | [foliage]; sibling used by PWR |
| `/Game/Env/Bio/Tree/Pine/Tree_Pine/Tree_Pine_A/Meshes/SM_Tree_Pine_A_Big_59` | StaticMesh | 0.25 | 6,417 | 19.47x15.66x13.05 | A30 | no | [foliage]; sibling used by PWR |
| `/Game/Env/Bio/Tree/Pine/Tree_Pine/Tree_Pine_A/Meshes/SM_Tree_Pine_A_Big_6` | StaticMesh | 0.01 | 102 | 2.43x1.3x1.28 | A30 | no | [foliage]; sibling used by PWR |
| `/Game/Env/Bio/Tree/Pine/Tree_Pine/Tree_Pine_A/Meshes/SM_Tree_Pine_A_Big_60` | StaticMesh | 0.12 | 2,930 | 12.94x13.22x8.57 | A30 | no | [foliage]; sibling used by PWR |
| `/Game/Env/Bio/Tree/Pine/Tree_Pine/Tree_Pine_A/Meshes/SM_Tree_Pine_A_Big_61` | StaticMesh | 0.18 | 4,848 | 14.6x14.67x9.61 | A30 | no | [foliage]; sibling used by PWR |
| `/Game/Env/Bio/Tree/Pine/Tree_Pine/Tree_Pine_A/Meshes/SM_Tree_Pine_A_Big_62` | StaticMesh | 0.15 | 4,058 | 14.08x13.45x7.21 | A30 | no | [foliage]; sibling used by PWR |
| `/Game/Env/Bio/Tree/Pine/Tree_Pine/Tree_Pine_A/Meshes/SM_Tree_Pine_A_Big_63` | StaticMesh | 0.16 | 4,251 | 14.86x16.16x10.87 | A30 | no | [foliage]; sibling used by PWR |
| `/Game/Env/Bio/Tree/Pine/Tree_Pine/Tree_Pine_A/Meshes/SM_Tree_Pine_A_Big_64` | StaticMesh | 0.25 | 6,691 | 15.77x16.79x12.1 | A30 | no | [foliage]; sibling used by PWR |
| `/Game/Env/Bio/Tree/Pine/Tree_Pine/Tree_Pine_A/Meshes/SM_Tree_Pine_A_Big_65` | StaticMesh | 0.08 | 2,059 | 11.35x11.13x7.01 | A30 | no | [foliage]; sibling used by PWR |
| `/Game/Env/Bio/Tree/Pine/Tree_Pine/Tree_Pine_A/Meshes/SM_Tree_Pine_A_Big_66` | StaticMesh | 0.07 | 1,994 | 15.4x10.25x8.34 | A30 | no | [foliage]; sibling used by PWR |
| `/Game/Env/Bio/Tree/Pine/Tree_Pine/Tree_Pine_A/Meshes/SM_Tree_Pine_A_Big_67` | StaticMesh | 0.14 | 3,622 | 14.94x15.79x11.26 | A30 | no | [foliage]; sibling used by PWR |
| `/Game/Env/Bio/Tree/Pine/Tree_Pine/Tree_Pine_A/Meshes/SM_Tree_Pine_A_Big_68` | StaticMesh | 0.09 | 2,382 | 15.34x12.32x7.92 | A30 | no | [foliage]; sibling used by PWR |
| `/Game/Env/Bio/Tree/Pine/Tree_Pine/Tree_Pine_A/Meshes/SM_Tree_Pine_A_Big_69` | StaticMesh | 0.06 | 1,473 | 12.45x11.3x6.85 | A30 | no | [foliage]; sibling used by PWR |
| `/Game/Env/Bio/Tree/Pine/Tree_Pine/Tree_Pine_A/Meshes/SM_Tree_Pine_A_Big_7` | StaticMesh | 0.05 | 1,284 | 3.9x3.97x2.85 | A30 | no | [foliage]; sibling used by PWR |
| `/Game/Env/Bio/Tree/Pine/Tree_Pine/Tree_Pine_A/Meshes/SM_Tree_Pine_A_Big_70` | StaticMesh | 0.11 | 2,801 | 14.26x12.27x9.61 | A30 | no | [foliage]; sibling used by PWR |
| `/Game/Env/Bio/Tree/Pine/Tree_Pine/Tree_Pine_A/Meshes/SM_Tree_Pine_A_Big_71` | StaticMesh | 0.09 | 2,314 | 12.66x14.28x7.93 | A30 | no | [foliage]; sibling used by PWR |
| `/Game/Env/Bio/Tree/Pine/Tree_Pine/Tree_Pine_A/Meshes/SM_Tree_Pine_A_Big_72` | StaticMesh | 0.13 | 3,244 | 16.12x14.21x11.46 | A30 | no | [foliage]; sibling used by PWR |
| `/Game/Env/Bio/Tree/Pine/Tree_Pine/Tree_Pine_A/Meshes/SM_Tree_Pine_A_Big_73` | StaticMesh | 0.10 | 2,714 | 12.97x22.63x9.63 | A30 | no | [foliage]; sibling used by PWR |
| `/Game/Env/Bio/Tree/Pine/Tree_Pine/Tree_Pine_A/Meshes/SM_Tree_Pine_A_Big_74` | StaticMesh | 0.12 | 3,351 | 15.23x14.39x10.76 | A30 | no | [foliage]; sibling used by PWR |
| `/Game/Env/Bio/Tree/Pine/Tree_Pine/Tree_Pine_A/Meshes/SM_Tree_Pine_A_Big_75` | StaticMesh | 0.07 | 1,929 | 12.88x9.85x10.8 | A30 | no | [foliage]; sibling used by PWR |
| `/Game/Env/Bio/Tree/Pine/Tree_Pine/Tree_Pine_A/Meshes/SM_Tree_Pine_A_Big_76` | StaticMesh | 0.05 | 1,259 | 13.01x13.45x6.97 | A30 | no | [foliage]; sibling used by PWR |
| `/Game/Env/Bio/Tree/Pine/Tree_Pine/Tree_Pine_A/Meshes/SM_Tree_Pine_A_Big_77` | StaticMesh | 0.13 | 3,303 | 20.15x11.37x7.93 | A30 | no | [foliage]; sibling used by PWR |
| `/Game/Env/Bio/Tree/Pine/Tree_Pine/Tree_Pine_A/Meshes/SM_Tree_Pine_A_Big_78` | StaticMesh | 0.06 | 1,460 | 13.44x12.97x7.73 | A30 | no | [foliage]; sibling used by PWR |
| `/Game/Env/Bio/Tree/Pine/Tree_Pine/Tree_Pine_A/Meshes/SM_Tree_Pine_A_Big_79` | StaticMesh | 0.12 | 3,306 | 13.22x16.69x7.86 | A30 | no | [foliage]; sibling used by PWR |
| `/Game/Env/Bio/Tree/Pine/Tree_Pine/Tree_Pine_A/Meshes/SM_Tree_Pine_A_Big_8` | StaticMesh | 0.05 | 1,281 | 4.34x3.66x2.75 | A30 | no | [foliage]; sibling used by PWR |
| `/Game/Env/Bio/Tree/Pine/Tree_Pine/Tree_Pine_A/Meshes/SM_Tree_Pine_A_Big_80` | StaticMesh | 0.13 | 3,445 | 15.31x19.56x11.93 | A30 | no | [foliage]; sibling used by PWR |
| `/Game/Env/Bio/Tree/Pine/Tree_Pine/Tree_Pine_A/Meshes/SM_Tree_Pine_A_Big_81` | StaticMesh | 0.06 | 1,620 | 16.3x11.33x8.93 | A30 | no | [foliage]; sibling used by PWR |
| `/Game/Env/Bio/Tree/Pine/Tree_Pine/Tree_Pine_A/Meshes/SM_Tree_Pine_A_Big_82` | StaticMesh | 0.08 | 2,090 | 15.88x13.9x9.78 | A30 | no | [foliage]; sibling used by PWR |
| `/Game/Env/Bio/Tree/Pine/Tree_Pine/Tree_Pine_A/Meshes/SM_Tree_Pine_A_Big_83` | StaticMesh | 0.07 | 1,847 | 16.58x12.4x8.65 | A30 | no | [foliage]; sibling used by PWR |
| `/Game/Env/Bio/Tree/Pine/Tree_Pine/Tree_Pine_A/Meshes/SM_Tree_Pine_A_Big_84` | StaticMesh | 0.08 | 1,930 | 13.3x13.39x9.48 | A30 | no | [foliage]; sibling used by PWR |
| `/Game/Env/Bio/Tree/Pine/Tree_Pine/Tree_Pine_A/Meshes/SM_Tree_Pine_A_Big_85` | StaticMesh | 0.11 | 2,837 | 16.62x21.66x12.08 | A30 | no | [foliage]; sibling used by PWR |
| `/Game/Env/Bio/Tree/Pine/Tree_Pine/Tree_Pine_A/Meshes/SM_Tree_Pine_A_Big_86` | StaticMesh | 0.11 | 3,044 | 14.05x17.74x10.37 | A30 | no | [foliage]; sibling used by PWR |
| `/Game/Env/Bio/Tree/Pine/Tree_Pine/Tree_Pine_A/Meshes/SM_Tree_Pine_A_Big_87` | StaticMesh | 0.12 | 3,286 | 15.19x21.25x13.66 | A30 | no | [foliage]; sibling used by PWR |
| `/Game/Env/Bio/Tree/Pine/Tree_Pine/Tree_Pine_A/Meshes/SM_Tree_Pine_A_Big_88` | StaticMesh | 0.08 | 2,118 | 14.29x16.07x9.02 | A30 | no | [foliage]; sibling used by PWR |
| `/Game/Env/Bio/Tree/Pine/Tree_Pine/Tree_Pine_A/Meshes/SM_Tree_Pine_A_Big_89` | StaticMesh | 0.12 | 3,047 | 17.54x11.53x9.97 | A30 | no | [foliage]; sibling used by PWR |
| `/Game/Env/Bio/Tree/Pine/Tree_Pine/Tree_Pine_A/Meshes/SM_Tree_Pine_A_Big_9` | StaticMesh | 0.01 | 114 | 1.77x1.66x0.87 | A30 | no | [foliage]; sibling used by PWR |
| `/Game/Env/Bio/Tree/Pine/Tree_Pine/Tree_Pine_A/Meshes/SM_Tree_Pine_A_Big_90` | StaticMesh | 0.13 | 3,463 | 21.9x16.01x11.29 | A30 | no | [foliage]; sibling used by PWR |
| `/Game/Env/Bio/Tree/Pine/Tree_Pine/Tree_Pine_A/Meshes/SM_Tree_Pine_A_Big_91` | StaticMesh | 0.10 | 2,614 | 17.45x21.29x10.62 | A30 | no | [foliage]; sibling used by PWR |
| `/Game/Env/Bio/Tree/Pine/Tree_Pine/Tree_Pine_A/Meshes/SM_Tree_Pine_A_Big_92` | StaticMesh | 0.09 | 2,252 | 16.47x15.52x9.88 | A30 | no | [foliage]; sibling used by PWR |
| `/Game/Env/Bio/Tree/Pine/Tree_Pine/Tree_Pine_A/Meshes/SM_Tree_Pine_A_Big_93` | StaticMesh | 0.07 | 1,792 | 12.89x13.38x9.31 | A30 | no | [foliage]; sibling used by PWR |
| `/Game/Env/Bio/Tree/Pine/Tree_Pine/Tree_Pine_A/Meshes/SM_Tree_Pine_A_Big_94` | StaticMesh | 0.07 | 1,696 | 19.48x13.55x9.62 | A30 | no | [foliage]; sibling used by PWR |
| `/Game/Env/Bio/Tree/Pine/Tree_Pine/Tree_Pine_A/Meshes/SM_Tree_Pine_A_Big_95` | StaticMesh | 0.07 | 1,710 | 16.17x18.29x9.94 | A30 | no | [foliage]; sibling used by PWR |
| `/Game/Env/Bio/Tree/Pine/Tree_Pine/Tree_Pine_A/Meshes/SM_Tree_Pine_A_Big_96` | StaticMesh | 0.07 | 1,907 | 16.22x19.69x8.36 | A30 | no | [foliage]; sibling used by PWR |
| `/Game/Env/Bio/Tree/Pine/Tree_Pine/Tree_Pine_A/Meshes/SM_Tree_Pine_A_Big_97` | StaticMesh | 0.14 | 3,978 | 19.38x26.06x11.06 | A30 | no | [foliage]; sibling used by PWR |
| `/Game/Env/Bio/Tree/Pine/Tree_Pine/Tree_Pine_A/Meshes/SM_Tree_Pine_A_Big_98` | StaticMesh | 0.12 | 3,418 | 23.56x19.32x13.72 | A30 | no | [foliage]; sibling used by PWR |
| `/Game/Env/Bio/Tree/Pine/Tree_Pine/Tree_Pine_A/Meshes/SM_Tree_Pine_A_Big_99` | StaticMesh | 0.12 | 3,095 | 19.22x25.12x11.81 | A30 | no | [foliage]; sibling used by PWR |
| `/Game/Env/Bio/Tree/Pine/Tree_Pine/Tree_Pine_A/Meshes/SM_Tree_Pine_A_Tree_Windswept_Big_Branches__5` | StaticMesh | 0.01 | 55 | 0.7x0.95x9.48 | A30 | no | [foliage]; sibling used by PWR |
| `/Game/Env/Bio/Tree/Pine/Tree_Pine/Tree_Pine_A/Meshes/SM_Tree_Pine_A_Trunk` | StaticMesh | 13.24 | 287,812 | 21.97x21.37x224.35 | A30 | listed | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Pine_Sapling_A/Materials/MI_Tree_Pine_Sapling_A_Bark` | MaterialInstance | 0.05 |  |  | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Pine_Sapling_A/Materials/MI_Tree_Pine_Sapling_A_Leaves` | MaterialInstance | 0.03 |  |  | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Pine_Sapling_A/Meshes/SM_Tree_Pine_Sapling_A` | StaticMesh | 0.96 | 23,712 | 1.16x1.45x2.11 | A30 | yes | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Windswept/Materials/MI_Pine_Tree_Mat_LOD0` | MaterialInstance | 0.00 |  |  | A30 | yes | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Windswept/Meshes/SM_Tree_Windswept_Stump_2` | StaticMesh | 5.34 | 116,576 | 6.19x4.8x63.04 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Windswept_A/InstanceMeshDefinitions/SM_Tree_Windswept_A_Tree_Protoype_Branch` | StaticMesh | 0.20 | 4,536 | 7.5x9.91x3.81 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Windswept_A/InstanceMeshDefinitions/SM_Tree_Windswept_A_Tree_Protoype_Branch_Proxy` | StaticMesh | 0.04 | 583 | 7.63x9.67x3.89 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Windswept_A/Materials/MI_Branch_Mat_LOD0_TwoSided` | MaterialInstance | 0.03 |  |  | A30 | yes | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Windswept_A/Materials/MI_SaplingBranch` | MaterialInstance | 0.03 |  |  | A30 | no | [foliage]; sibling used by PWR |
| `/Game/Env/Bio/Tree/Pine/Tree_Windswept_A/Materials/MI_SaplingBranch_ScatterVolumes` | MaterialInstance | 0.03 |  |  | A30 | no | [foliage]; sibling used by PWR |
| `/Game/Env/Bio/Tree/Pine/Tree_Windswept_A/Materials/MI_SaplingTrunk` | MaterialInstance | 0.10 |  |  | A30 | no | [foliage]; sibling used by PWR |
| `/Game/Env/Bio/Tree/Pine/Tree_Windswept_A/Materials/MI_bark_Mat_LOD0` | MaterialInstance | 0.00 |  |  | A30 | no | [foliage]; sibling used by PWR |
| `/Game/Env/Bio/Tree/Pine/Tree_Windswept_A/Meshes/SM_Tree_Sapling_Optimized` | StaticMesh | 12.46 | 158,730 | 12.49x12.65x21.5 | A30 | listed | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Windswept_A/Meshes/SM_Tree_Windswept_A_Branches` | StaticMesh | 0.04 | 1,022 | 0.53x0.69x1.63 | A30 | no | [foliage]; sibling used by PWR |
| `/Game/Env/Bio/Tree/Pine/Tree_Windswept_A/Meshes/SM_Tree_Windswept_A_Branches_1` | StaticMesh | 0.07 | 1,647 | 1.66x2.67x2.35 | A30 | no | [foliage]; sibling used by PWR |
| `/Game/Env/Bio/Tree/Pine/Tree_Windswept_A/Meshes/SM_Tree_Windswept_A_Branches_10` | StaticMesh | 0.08 | 1,952 | 2.33x2.59x2.39 | A30 | no | [foliage]; sibling used by PWR |
| `/Game/Env/Bio/Tree/Pine/Tree_Windswept_A/Meshes/SM_Tree_Windswept_A_Branches_11` | StaticMesh | 0.05 | 1,311 | 2.73x2.11x2.42 | A30 | no | [foliage]; sibling used by PWR |
| `/Game/Env/Bio/Tree/Pine/Tree_Windswept_A/Meshes/SM_Tree_Windswept_A_Branches_12` | StaticMesh | 0.06 | 1,389 | 0.9x2.72x2.13 | A30 | no | [foliage]; sibling used by PWR |
| `/Game/Env/Bio/Tree/Pine/Tree_Windswept_A/Meshes/SM_Tree_Windswept_A_Branches_13` | StaticMesh | 0.08 | 1,916 | 3.19x1.66x2.43 | A30 | no | [foliage]; sibling used by PWR |
| `/Game/Env/Bio/Tree/Pine/Tree_Windswept_A/Meshes/SM_Tree_Windswept_A_Branches_14` | StaticMesh | 0.04 | 851 | 1.51x0.93x1.92 | A30 | no | [foliage]; sibling used by PWR |
| `/Game/Env/Bio/Tree/Pine/Tree_Windswept_A/Meshes/SM_Tree_Windswept_A_Branches_15` | StaticMesh | 0.05 | 1,049 | 1.26x1.14x1.73 | A30 | no | [foliage]; sibling used by PWR |
| `/Game/Env/Bio/Tree/Pine/Tree_Windswept_A/Meshes/SM_Tree_Windswept_A_Branches_16` | StaticMesh | 0.09 | 2,166 | 2.02x2.66x2.59 | A30 | no | [foliage]; sibling used by PWR |
| `/Game/Env/Bio/Tree/Pine/Tree_Windswept_A/Meshes/SM_Tree_Windswept_A_Branches_17` | StaticMesh | 0.11 | 2,725 | 3.62x2.9x2.85 | A30 | no | [foliage]; sibling used by PWR |
| `/Game/Env/Bio/Tree/Pine/Tree_Windswept_A/Meshes/SM_Tree_Windswept_A_Branches_18` | StaticMesh | 0.09 | 2,317 | 3.7x2.25x2.56 | A30 | no | [foliage]; sibling used by PWR |
| `/Game/Env/Bio/Tree/Pine/Tree_Windswept_A/Meshes/SM_Tree_Windswept_A_Branches_19` | StaticMesh | 0.05 | 1,147 | 0.79x1.9x1.95 | A30 | no | [foliage]; sibling used by PWR |
| `/Game/Env/Bio/Tree/Pine/Tree_Windswept_A/Meshes/SM_Tree_Windswept_A_Branches_2` | StaticMesh | 0.05 | 1,155 | 0.98x0.87x1.95 | A30 | no | [foliage]; sibling used by PWR |
| `/Game/Env/Bio/Tree/Pine/Tree_Windswept_A/Meshes/SM_Tree_Windswept_A_Branches_20` | StaticMesh | 0.13 | 3,535 | 4.18x5.15x2.78 | A30 | no | [foliage]; sibling used by PWR |
| `/Game/Env/Bio/Tree/Pine/Tree_Windswept_A/Meshes/SM_Tree_Windswept_A_Branches_21` | StaticMesh | 0.05 | 1,028 | 1.35x1.72x2.0 | A30 | no | [foliage]; sibling used by PWR |
| `/Game/Env/Bio/Tree/Pine/Tree_Windswept_A/Meshes/SM_Tree_Windswept_A_Branches_22` | StaticMesh | 0.06 | 1,396 | 3.31x1.34x2.1 | A30 | no | [foliage]; sibling used by PWR |
| `/Game/Env/Bio/Tree/Pine/Tree_Windswept_A/Meshes/SM_Tree_Windswept_A_Branches_23` | StaticMesh | 0.05 | 1,141 | 2.12x1.57x2.15 | A30 | no | [foliage]; sibling used by PWR |
| `/Game/Env/Bio/Tree/Pine/Tree_Windswept_A/Meshes/SM_Tree_Windswept_A_Branches_24` | StaticMesh | 0.03 | 604 | 0.41x1.15x1.73 | A30 | no | [foliage]; sibling used by PWR |
| `/Game/Env/Bio/Tree/Pine/Tree_Windswept_A/Meshes/SM_Tree_Windswept_A_Branches_25` | StaticMesh | 0.02 | 396 | 1.36x0.51x1.88 | A30 | no | [foliage]; sibling used by PWR |
| `/Game/Env/Bio/Tree/Pine/Tree_Windswept_A/Meshes/SM_Tree_Windswept_A_Branches_26` | StaticMesh | 0.07 | 1,779 | 4.17x2.6x2.44 | A30 | no | [foliage]; sibling used by PWR |
| `/Game/Env/Bio/Tree/Pine/Tree_Windswept_A/Meshes/SM_Tree_Windswept_A_Branches_27` | StaticMesh | 0.14 | 3,720 | 4.63x4.04x3.09 | A30 | no | [foliage]; sibling used by PWR |
| `/Game/Env/Bio/Tree/Pine/Tree_Windswept_A/Meshes/SM_Tree_Windswept_A_Branches_28` | StaticMesh | 0.05 | 1,321 | 3.72x1.89x2.69 | A30 | no | [foliage]; sibling used by PWR |
| `/Game/Env/Bio/Tree/Pine/Tree_Windswept_A/Meshes/SM_Tree_Windswept_A_Branches_29` | StaticMesh | 0.11 | 2,855 | 2.98x4.57x2.7 | A30 | no | [foliage]; sibling used by PWR |
| `/Game/Env/Bio/Tree/Pine/Tree_Windswept_A/Meshes/SM_Tree_Windswept_A_Branches_3` | StaticMesh | 0.01 | 230 | 0.42x0.6x1.33 | A30 | no | [foliage]; sibling used by PWR |
| `/Game/Env/Bio/Tree/Pine/Tree_Windswept_A/Meshes/SM_Tree_Windswept_A_Branches_30` | StaticMesh | 0.08 | 1,939 | 1.89x3.38x2.24 | A30 | no | [foliage]; sibling used by PWR |
| `/Game/Env/Bio/Tree/Pine/Tree_Windswept_A/Meshes/SM_Tree_Windswept_A_Branches_31` | StaticMesh | 0.12 | 3,121 | 5.24x3.87x3.31 | A30 | no | [foliage]; sibling used by PWR |
| `/Game/Env/Bio/Tree/Pine/Tree_Windswept_A/Meshes/SM_Tree_Windswept_A_Branches_32` | StaticMesh | 0.08 | 1,920 | 3.65x3.66x2.81 | A30 | no | [foliage]; sibling used by PWR |
| `/Game/Env/Bio/Tree/Pine/Tree_Windswept_A/Meshes/SM_Tree_Windswept_A_Branches_33` | StaticMesh | 0.11 | 2,744 | 3.92x5.19x3.29 | A30 | no | [foliage]; sibling used by PWR |
| `/Game/Env/Bio/Tree/Pine/Tree_Windswept_A/Meshes/SM_Tree_Windswept_A_Branches_34` | StaticMesh | 0.13 | 3,348 | 3.84x4.2x4.01 | A30 | no | [foliage]; sibling used by PWR |
| `/Game/Env/Bio/Tree/Pine/Tree_Windswept_A/Meshes/SM_Tree_Windswept_A_Branches_35` | StaticMesh | 0.14 | 3,579 | 5.3x5.21x3.73 | A30 | no | [foliage]; sibling used by PWR |
| `/Game/Env/Bio/Tree/Pine/Tree_Windswept_A/Meshes/SM_Tree_Windswept_A_Branches_36` | StaticMesh | 0.04 | 1,010 | 2.09x1.47x2.18 | A30 | no | [foliage]; sibling used by PWR |
| `/Game/Env/Bio/Tree/Pine/Tree_Windswept_A/Meshes/SM_Tree_Windswept_A_Branches_37` | StaticMesh | 0.04 | 864 | 1.66x2.55x2.72 | A30 | no | [foliage]; sibling used by PWR |
| `/Game/Env/Bio/Tree/Pine/Tree_Windswept_A/Meshes/SM_Tree_Windswept_A_Branches_38` | StaticMesh | 0.13 | 3,242 | 4.76x3.78x3.47 | A30 | no | [foliage]; sibling used by PWR |
| `/Game/Env/Bio/Tree/Pine/Tree_Windswept_A/Meshes/SM_Tree_Windswept_A_Branches_39` | StaticMesh | 0.13 | 3,301 | 3.08x3.76x3.14 | A30 | no | [foliage]; sibling used by PWR |
| `/Game/Env/Bio/Tree/Pine/Tree_Windswept_A/Meshes/SM_Tree_Windswept_A_Branches_4` | StaticMesh | 0.05 | 1,229 | 0.94x1.21x1.57 | A30 | no | [foliage]; sibling used by PWR |
| `/Game/Env/Bio/Tree/Pine/Tree_Windswept_A/Meshes/SM_Tree_Windswept_A_Branches_40` | StaticMesh | 0.10 | 2,566 | 4.39x3.93x2.85 | A30 | no | [foliage]; sibling used by PWR |
| `/Game/Env/Bio/Tree/Pine/Tree_Windswept_A/Meshes/SM_Tree_Windswept_A_Branches_41` | StaticMesh | 0.09 | 2,468 | 4.06x4.38x4.5 | A30 | no | [foliage]; sibling used by PWR |
| `/Game/Env/Bio/Tree/Pine/Tree_Windswept_A/Meshes/SM_Tree_Windswept_A_Branches_42` | StaticMesh | 0.08 | 1,921 | 4.17x3.65x2.42 | A30 | no | [foliage]; sibling used by PWR |
| `/Game/Env/Bio/Tree/Pine/Tree_Windswept_A/Meshes/SM_Tree_Windswept_A_Branches_43` | StaticMesh | 0.12 | 3,019 | 4.5x5.44x3.66 | A30 | no | [foliage]; sibling used by PWR |
| `/Game/Env/Bio/Tree/Pine/Tree_Windswept_A/Meshes/SM_Tree_Windswept_A_Branches_44` | StaticMesh | 0.08 | 2,060 | 3.07x2.58x2.36 | A30 | no | [foliage]; sibling used by PWR |
| `/Game/Env/Bio/Tree/Pine/Tree_Windswept_A/Meshes/SM_Tree_Windswept_A_Branches_45` | StaticMesh | 0.08 | 1,969 | 3.43x4.04x3.26 | A30 | no | [foliage]; sibling used by PWR |
| `/Game/Env/Bio/Tree/Pine/Tree_Windswept_A/Meshes/SM_Tree_Windswept_A_Branches_46` | StaticMesh | 0.05 | 1,285 | 4.07x2.93x2.73 | A30 | no | [foliage]; sibling used by PWR |
| `/Game/Env/Bio/Tree/Pine/Tree_Windswept_A/Meshes/SM_Tree_Windswept_A_Branches_47` | StaticMesh | 0.05 | 1,253 | 2.83x3.45x2.72 | A30 | no | [foliage]; sibling used by PWR |
| `/Game/Env/Bio/Tree/Pine/Tree_Windswept_A/Meshes/SM_Tree_Windswept_A_Branches_48` | StaticMesh | 0.07 | 1,630 | 1.67x2.28x1.65 | A30 | no | [foliage]; sibling used by PWR |
| `/Game/Env/Bio/Tree/Pine/Tree_Windswept_A/Meshes/SM_Tree_Windswept_A_Branches_49` | StaticMesh | 0.07 | 1,667 | 2.27x2.35x1.95 | A30 | no | [foliage]; sibling used by PWR |
| `/Game/Env/Bio/Tree/Pine/Tree_Windswept_A/Meshes/SM_Tree_Windswept_A_Branches_5` | StaticMesh | 0.02 | 425 | 0.85x0.52x1.6 | A30 | no | [foliage]; sibling used by PWR |
| `/Game/Env/Bio/Tree/Pine/Tree_Windswept_A/Meshes/SM_Tree_Windswept_A_Branches_50` | StaticMesh | 0.06 | 1,550 | 1.53x2.0x2.02 | A30 | no | [foliage]; sibling used by PWR |
| `/Game/Env/Bio/Tree/Pine/Tree_Windswept_A/Meshes/SM_Tree_Windswept_A_Branches_51` | StaticMesh | 0.06 | 1,363 | 1.35x1.79x2.16 | A30 | no | [foliage]; sibling used by PWR |
| `/Game/Env/Bio/Tree/Pine/Tree_Windswept_A/Meshes/SM_Tree_Windswept_A_Branches_52` | StaticMesh | 0.06 | 1,474 | 1.63x1.98x2.22 | A30 | no | [foliage]; sibling used by PWR |
| `/Game/Env/Bio/Tree/Pine/Tree_Windswept_A/Meshes/SM_Tree_Windswept_A_Branches_53` | StaticMesh | 0.07 | 1,662 | 1.47x2.13x2.18 | A30 | no | [foliage]; sibling used by PWR |
| `/Game/Env/Bio/Tree/Pine/Tree_Windswept_A/Meshes/SM_Tree_Windswept_A_Branches_54` | StaticMesh | 0.05 | 1,288 | 1.46x1.49x1.93 | A30 | no | [foliage]; sibling used by PWR |
| `/Game/Env/Bio/Tree/Pine/Tree_Windswept_A/Meshes/SM_Tree_Windswept_A_Branches_55` | StaticMesh | 0.05 | 1,234 | 1.29x2.03x1.97 | A30 | no | [foliage]; sibling used by PWR |
| `/Game/Env/Bio/Tree/Pine/Tree_Windswept_A/Meshes/SM_Tree_Windswept_A_Branches_56` | StaticMesh | 0.05 | 1,251 | 1.77x1.26x2.66 | A30 | no | [foliage]; sibling used by PWR |
| `/Game/Env/Bio/Tree/Pine/Tree_Windswept_A/Meshes/SM_Tree_Windswept_A_Branches_57` | StaticMesh | 0.05 | 1,141 | 2.2x1.42x1.74 | A30 | no | [foliage]; sibling used by PWR |
| `/Game/Env/Bio/Tree/Pine/Tree_Windswept_A/Meshes/SM_Tree_Windswept_A_Branches_58` | StaticMesh | 0.07 | 1,657 | 1.82x1.7x2.53 | A30 | no | [foliage]; sibling used by PWR |
| `/Game/Env/Bio/Tree/Pine/Tree_Windswept_A/Meshes/SM_Tree_Windswept_A_Branches_59` | StaticMesh | 0.08 | 1,877 | 2.11x1.57x2.16 | A30 | no | [foliage]; sibling used by PWR |
| `/Game/Env/Bio/Tree/Pine/Tree_Windswept_A/Meshes/SM_Tree_Windswept_A_Branches_6` | StaticMesh | 0.05 | 1,287 | 0.95x1.24x1.73 | A30 | no | [foliage]; sibling used by PWR |
| `/Game/Env/Bio/Tree/Pine/Tree_Windswept_A/Meshes/SM_Tree_Windswept_A_Branches_60` | StaticMesh | 0.07 | 1,613 | 1.9x3.49x2.53 | A30 | no | [foliage]; sibling used by PWR |
| `/Game/Env/Bio/Tree/Pine/Tree_Windswept_A/Meshes/SM_Tree_Windswept_A_Branches_61` | StaticMesh | 0.07 | 1,690 | 3.07x2.91x3.36 | A30 | no | [foliage]; sibling used by PWR |
| `/Game/Env/Bio/Tree/Pine/Tree_Windswept_A/Meshes/SM_Tree_Windswept_A_Branches_62` | StaticMesh | 0.05 | 1,299 | 2.32x1.74x1.91 | A30 | no | [foliage]; sibling used by PWR |
| `/Game/Env/Bio/Tree/Pine/Tree_Windswept_A/Meshes/SM_Tree_Windswept_A_Branches_63` | StaticMesh | 0.07 | 1,888 | 2.47x3.28x2.84 | A30 | no | [foliage]; sibling used by PWR |
| `/Game/Env/Bio/Tree/Pine/Tree_Windswept_A/Meshes/SM_Tree_Windswept_A_Branches_64` | StaticMesh | 0.08 | 2,073 | 5.13x2.06x2.96 | A30 | no | [foliage]; sibling used by PWR |
| `/Game/Env/Bio/Tree/Pine/Tree_Windswept_A/Meshes/SM_Tree_Windswept_A_Branches_65` | StaticMesh | 0.05 | 1,255 | 1.82x1.75x2.21 | A30 | no | [foliage]; sibling used by PWR |
| `/Game/Env/Bio/Tree/Pine/Tree_Windswept_A/Meshes/SM_Tree_Windswept_A_Branches_66` | StaticMesh | 0.06 | 1,497 | 2.42x2.63x2.95 | A30 | no | [foliage]; sibling used by PWR |
| `/Game/Env/Bio/Tree/Pine/Tree_Windswept_A/Meshes/SM_Tree_Windswept_A_Branches_67` | StaticMesh | 0.05 | 1,186 | 1.92x1.72x2.22 | A30 | no | [foliage]; sibling used by PWR |
| `/Game/Env/Bio/Tree/Pine/Tree_Windswept_A/Meshes/SM_Tree_Windswept_A_Branches_68` | StaticMesh | 0.04 | 1,124 | 1.73x1.84x2.12 | A30 | no | [foliage]; sibling used by PWR |
| `/Game/Env/Bio/Tree/Pine/Tree_Windswept_A/Meshes/SM_Tree_Windswept_A_Branches_69` | StaticMesh | 0.05 | 1,137 | 1.41x1.74x2.12 | A30 | no | [foliage]; sibling used by PWR |
| `/Game/Env/Bio/Tree/Pine/Tree_Windswept_A/Meshes/SM_Tree_Windswept_A_Branches_7` | StaticMesh | 0.01 | 129 | 0.13x0.43x0.17 | A30 | no | [foliage]; sibling used by PWR |
| `/Game/Env/Bio/Tree/Pine/Tree_Windswept_A/Meshes/SM_Tree_Windswept_A_Branches_70` | StaticMesh | 0.06 | 1,530 | 1.77x2.77x2.24 | A30 | no | [foliage]; sibling used by PWR |
| `/Game/Env/Bio/Tree/Pine/Tree_Windswept_A/Meshes/SM_Tree_Windswept_A_Branches_71` | StaticMesh | 0.08 | 2,150 | 2.39x2.27x2.92 | A30 | no | [foliage]; sibling used by PWR |
| `/Game/Env/Bio/Tree/Pine/Tree_Windswept_A/Meshes/SM_Tree_Windswept_A_Branches_72` | StaticMesh | 0.05 | 1,312 | 2.27x1.86x1.96 | A30 | no | [foliage]; sibling used by PWR |
| `/Game/Env/Bio/Tree/Pine/Tree_Windswept_A/Meshes/SM_Tree_Windswept_A_Branches_73` | StaticMesh | 0.07 | 1,734 | 2.25x2.99x2.9 | A30 | no | [foliage]; sibling used by PWR |
| `/Game/Env/Bio/Tree/Pine/Tree_Windswept_A/Meshes/SM_Tree_Windswept_A_Branches_74` | StaticMesh | 0.06 | 1,677 | 2.61x3.57x3.47 | A30 | no | [foliage]; sibling used by PWR |
| `/Game/Env/Bio/Tree/Pine/Tree_Windswept_A/Meshes/SM_Tree_Windswept_A_Branches_75` | StaticMesh | 0.05 | 1,396 | 2.54x2.46x3.44 | A30 | no | [foliage]; sibling used by PWR |
| `/Game/Env/Bio/Tree/Pine/Tree_Windswept_A/Meshes/SM_Tree_Windswept_A_Branches_76` | StaticMesh | 0.04 | 815 | 1.78x2.12x3.45 | A30 | no | [foliage]; sibling used by PWR |
| `/Game/Env/Bio/Tree/Pine/Tree_Windswept_A/Meshes/SM_Tree_Windswept_A_Branches_77` | StaticMesh | 0.06 | 1,474 | 2.03x1.71x1.88 | A30 | no | [foliage]; sibling used by PWR |
| `/Game/Env/Bio/Tree/Pine/Tree_Windswept_A/Meshes/SM_Tree_Windswept_A_Branches_78` | StaticMesh | 0.06 | 1,494 | 1.91x1.44x2.07 | A30 | no | [foliage]; sibling used by PWR |
| `/Game/Env/Bio/Tree/Pine/Tree_Windswept_A/Meshes/SM_Tree_Windswept_A_Branches_79` | StaticMesh | 0.03 | 661 | 1.71x1.26x2.45 | A30 | no | [foliage]; sibling used by PWR |
| `/Game/Env/Bio/Tree/Pine/Tree_Windswept_A/Meshes/SM_Tree_Windswept_A_Branches_8` | StaticMesh | 0.09 | 2,084 | 2.96x1.88x2.11 | A30 | no | [foliage]; sibling used by PWR |
| `/Game/Env/Bio/Tree/Pine/Tree_Windswept_A/Meshes/SM_Tree_Windswept_A_Branches_80` | StaticMesh | 0.06 | 1,595 | 1.6x1.72x2.17 | A30 | no | [foliage]; sibling used by PWR |
| `/Game/Env/Bio/Tree/Pine/Tree_Windswept_A/Meshes/SM_Tree_Windswept_A_Branches_81` | StaticMesh | 0.05 | 1,115 | 2.04x1.26x2.24 | A30 | no | [foliage]; sibling used by PWR |
| `/Game/Env/Bio/Tree/Pine/Tree_Windswept_A/Meshes/SM_Tree_Windswept_A_Branches_82` | StaticMesh | 0.07 | 1,784 | 1.78x2.79x1.88 | A30 | no | [foliage]; sibling used by PWR |
| `/Game/Env/Bio/Tree/Pine/Tree_Windswept_A/Meshes/SM_Tree_Windswept_A_Branches_83` | StaticMesh | 0.05 | 1,447 | 1.86x2.08x1.31 | A30 | no | [foliage]; sibling used by PWR |
| `/Game/Env/Bio/Tree/Pine/Tree_Windswept_A/Meshes/SM_Tree_Windswept_A_Branches_9` | StaticMesh | 0.06 | 1,431 | 1.4x1.27x1.88 | A30 | no | [foliage]; sibling used by PWR |
| `/Game/Env/Bio/Tree/Pine/Tree_Windswept_A/Meshes/SM_Tree_Windswept_A_Trunk` | StaticMesh | 7.64 | 185,991 | 5.22x5.58x46.22 | A30 | no | [foliage]; sibling used by PWR |
| `/Game/Env/Bio/Tree/Pine/Tree_Windswept_Dead/Meshes/SM_Tree_Windswept_Dead_Big_10` | StaticMesh | 0.20 | 5,000 | 18.61x11.61x7.77 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Windswept_Dead/Meshes/SM_Tree_Windswept_Dead_Big_100` | StaticMesh | 0.01 | 283 | 0.86x1.91x3.21 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Windswept_Dead/Meshes/SM_Tree_Windswept_Dead_Big_101` | StaticMesh | 0.01 | 177 | 1.77x1.49x2.02 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Windswept_Dead/Meshes/SM_Tree_Windswept_Dead_Big_102` | StaticMesh | 0.01 | 195 | 0.69x1.99x2.51 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Windswept_Dead/Meshes/SM_Tree_Windswept_Dead_Big_103` | StaticMesh | 0.02 | 404 | 1.8x1.31x5.54 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Windswept_Dead/Meshes/SM_Tree_Windswept_Dead_Big_104` | StaticMesh | 0.13 | 3,323 | 7.37x8.15x10.8 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Windswept_Dead/Meshes/SM_Tree_Windswept_Dead_Big_105` | StaticMesh | 0.07 | 1,816 | 4.68x6.29x9.62 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Windswept_Dead/Meshes/SM_Tree_Windswept_Dead_Big_106` | StaticMesh | 0.01 | 195 | 1.28x1.26x3.0 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Windswept_Dead/Meshes/SM_Tree_Windswept_Dead_Big_107` | StaticMesh | 0.27 | 6,703 | 14.82x6.33x11.38 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Windswept_Dead/Meshes/SM_Tree_Windswept_Dead_Big_108` | StaticMesh | 0.24 | 5,815 | 9.71x11.71x21.79 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Windswept_Dead/Meshes/SM_Tree_Windswept_Dead_Big_109` | StaticMesh | 0.04 | 973 | 5.46x3.96x4.75 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Windswept_Dead/Meshes/SM_Tree_Windswept_Dead_Big_11` | StaticMesh | 0.22 | 5,517 | 16.34x17.07x9.81 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Windswept_Dead/Meshes/SM_Tree_Windswept_Dead_Big_110` | StaticMesh | 0.01 | 195 | 1.91x1.24x2.99 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Windswept_Dead/Meshes/SM_Tree_Windswept_Dead_Big_111` | StaticMesh | 0.03 | 756 | 4.04x3.15x4.95 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Windswept_Dead/Meshes/SM_Tree_Windswept_Dead_Big_112` | StaticMesh | 0.22 | 5,245 | 11.68x16.47x11.8 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Windswept_Dead/Meshes/SM_Tree_Windswept_Dead_Big_113` | StaticMesh | 0.27 | 6,650 | 10.75x10.39x25.98 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Windswept_Dead/Meshes/SM_Tree_Windswept_Dead_Big_114` | StaticMesh | 0.25 | 5,946 | 18.71x10.84x22.1 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Windswept_Dead/Meshes/SM_Tree_Windswept_Dead_Big_115` | StaticMesh | 0.01 | 206 | 1.03x1.61x2.77 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Windswept_Dead/Meshes/SM_Tree_Windswept_Dead_Big_116` | StaticMesh | 0.01 | 206 | 2.23x0.78x2.04 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Windswept_Dead/Meshes/SM_Tree_Windswept_Dead_Big_117` | StaticMesh | 0.05 | 1,161 | 2.35x8.67x4.95 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Windswept_Dead/Meshes/SM_Tree_Windswept_Dead_Big_118` | StaticMesh | 0.01 | 195 | 1.31x1.98x1.93 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Windswept_Dead/Meshes/SM_Tree_Windswept_Dead_Big_119` | StaticMesh | 0.15 | 3,812 | 11.43x4.6x10.85 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Windswept_Dead/Meshes/SM_Tree_Windswept_Dead_Big_12` | StaticMesh | 0.07 | 1,573 | 10.63x6.42x5.79 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Windswept_Dead/Meshes/SM_Tree_Windswept_Dead_Big_120` | StaticMesh | 0.01 | 206 | 1.38x1.82x2.7 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Windswept_Dead/Meshes/SM_Tree_Windswept_Dead_Big_121` | StaticMesh | 0.06 | 1,327 | 5.59x2.62x10.0 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Windswept_Dead/Meshes/SM_Tree_Windswept_Dead_Big_122` | StaticMesh | 0.22 | 5,138 | 8.92x12.95x12.77 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Windswept_Dead/Meshes/SM_Tree_Windswept_Dead_Big_123` | StaticMesh | 0.25 | 6,079 | 7.48x13.57x14.08 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Windswept_Dead/Meshes/SM_Tree_Windswept_Dead_Big_124` | StaticMesh | 0.21 | 5,291 | 6.83x13.44x14.74 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Windswept_Dead/Meshes/SM_Tree_Windswept_Dead_Big_125` | StaticMesh | 0.01 | 195 | 1.31x0.8x3.15 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Windswept_Dead/Meshes/SM_Tree_Windswept_Dead_Big_126` | StaticMesh | 0.14 | 3,392 | 15.24x7.43x7.3 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Windswept_Dead/Meshes/SM_Tree_Windswept_Dead_Big_127` | StaticMesh | 0.09 | 2,269 | 5.72x8.05x7.05 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Windswept_Dead/Meshes/SM_Tree_Windswept_Dead_Big_128` | StaticMesh | 0.01 | 206 | 1.69x1.11x3.27 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Windswept_Dead/Meshes/SM_Tree_Windswept_Dead_Big_129` | StaticMesh | 0.02 | 390 | 7.46x5.28x10.55 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Windswept_Dead/Meshes/SM_Tree_Windswept_Dead_Big_13` | StaticMesh | 0.14 | 3,338 | 12.3x16.62x6.08 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Windswept_Dead/Meshes/SM_Tree_Windswept_Dead_Big_130` | StaticMesh | 0.01 | 150 | 2.23x1.44x2.96 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Windswept_Dead/Meshes/SM_Tree_Windswept_Dead_Big_131` | StaticMesh | 0.02 | 380 | 8.53x6.32x9.14 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Windswept_Dead/Meshes/SM_Tree_Windswept_Dead_Big_132` | StaticMesh | 0.01 | 210 | 2.0x2.87x4.52 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Windswept_Dead/Meshes/SM_Tree_Windswept_Dead_Big_14` | StaticMesh | 0.12 | 2,968 | 11.63x8.26x6.78 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Windswept_Dead/Meshes/SM_Tree_Windswept_Dead_Big_15` | StaticMesh | 0.09 | 2,197 | 5.44x9.63x4.91 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Windswept_Dead/Meshes/SM_Tree_Windswept_Dead_Big_16` | StaticMesh | 0.08 | 1,861 | 7.57x10.5x5.37 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Windswept_Dead/Meshes/SM_Tree_Windswept_Dead_Big_17` | StaticMesh | 0.16 | 3,957 | 20.99x9.46x6.98 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Windswept_Dead/Meshes/SM_Tree_Windswept_Dead_Big_18` | StaticMesh | 0.03 | 592 | 1.1x0.74x2.2 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Windswept_Dead/Meshes/SM_Tree_Windswept_Dead_Big_19` | StaticMesh | 0.11 | 2,606 | 13.69x7.1x7.33 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Windswept_Dead/Meshes/SM_Tree_Windswept_Dead_Big_2` | StaticMesh | 0.03 | 793 | 1.68x2.01x3.94 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Windswept_Dead/Meshes/SM_Tree_Windswept_Dead_Big_20` | StaticMesh | 0.13 | 3,242 | 9.35x15.42x7.37 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Windswept_Dead/Meshes/SM_Tree_Windswept_Dead_Big_21` | StaticMesh | 0.26 | 6,371 | 19.68x15.72x13.01 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Windswept_Dead/Meshes/SM_Tree_Windswept_Dead_Big_22` | StaticMesh | 0.26 | 6,453 | 22.88x17.05x8.83 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Windswept_Dead/Meshes/SM_Tree_Windswept_Dead_Big_23` | StaticMesh | 0.13 | 3,184 | 13.24x11.39x11.39 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Windswept_Dead/Meshes/SM_Tree_Windswept_Dead_Big_24` | StaticMesh | 0.34 | 8,481 | 20.83x20.53x14.33 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Windswept_Dead/Meshes/SM_Tree_Windswept_Dead_Big_25` | StaticMesh | 0.29 | 7,288 | 25.99x17.26x14.76 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Windswept_Dead/Meshes/SM_Tree_Windswept_Dead_Big_26` | StaticMesh | 0.36 | 8,975 | 23.34x26.73x12.22 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Windswept_Dead/Meshes/SM_Tree_Windswept_Dead_Big_27` | StaticMesh | 0.30 | 7,461 | 13.96x26.11x16.33 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Windswept_Dead/Meshes/SM_Tree_Windswept_Dead_Big_28` | StaticMesh | 0.26 | 6,440 | 26.56x14.36x17.32 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Windswept_Dead/Meshes/SM_Tree_Windswept_Dead_Big_29` | StaticMesh | 0.30 | 7,435 | 28.52x13.04x16.41 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Windswept_Dead/Meshes/SM_Tree_Windswept_Dead_Big_3` | StaticMesh | 0.06 | 1,473 | 4.14x4.41x7.73 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Windswept_Dead/Meshes/SM_Tree_Windswept_Dead_Big_30` | StaticMesh | 0.13 | 3,191 | 8.28x17.11x9.57 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Windswept_Dead/Meshes/SM_Tree_Windswept_Dead_Big_31` | StaticMesh | 0.18 | 4,546 | 17.61x18.9x8.89 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Windswept_Dead/Meshes/SM_Tree_Windswept_Dead_Big_32` | StaticMesh | 0.12 | 2,895 | 16.21x9.95x10.34 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Windswept_Dead/Meshes/SM_Tree_Windswept_Dead_Big_33` | StaticMesh | 0.19 | 4,659 | 21.68x8.78x12.4 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Windswept_Dead/Meshes/SM_Tree_Windswept_Dead_Big_34` | StaticMesh | 0.09 | 2,175 | 13.92x11.32x8.38 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Windswept_Dead/Meshes/SM_Tree_Windswept_Dead_Big_35` | StaticMesh | 0.07 | 1,674 | 12.05x7.44x4.87 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Windswept_Dead/Meshes/SM_Tree_Windswept_Dead_Big_36` | StaticMesh | 0.08 | 2,071 | 9.81x16.41x9.32 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Windswept_Dead/Meshes/SM_Tree_Windswept_Dead_Big_37` | StaticMesh | 0.06 | 1,537 | 7.08x11.12x6.39 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Windswept_Dead/Meshes/SM_Tree_Windswept_Dead_Big_38` | StaticMesh | 0.06 | 1,534 | 11.52x6.67x5.68 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Windswept_Dead/Meshes/SM_Tree_Windswept_Dead_Big_39` | StaticMesh | 0.15 | 3,611 | 18.14x8.5x12.5 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Windswept_Dead/Meshes/SM_Tree_Windswept_Dead_Big_4` | StaticMesh | 0.13 | 3,215 | 9.71x15.84x6.93 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Windswept_Dead/Meshes/SM_Tree_Windswept_Dead_Big_40` | StaticMesh | 0.41 | 9,971 | 20.59x29.38x18.41 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Windswept_Dead/Meshes/SM_Tree_Windswept_Dead_Big_41` | StaticMesh | 0.26 | 6,504 | 21.25x20.26x12.79 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Windswept_Dead/Meshes/SM_Tree_Windswept_Dead_Big_42` | StaticMesh | 0.24 | 5,950 | 28.26x10.74x12.81 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Windswept_Dead/Meshes/SM_Tree_Windswept_Dead_Big_43` | StaticMesh | 0.22 | 5,367 | 15.2x17.13x13.69 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Windswept_Dead/Meshes/SM_Tree_Windswept_Dead_Big_44` | StaticMesh | 0.13 | 3,296 | 8.05x13.69x19.36 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Windswept_Dead/Meshes/SM_Tree_Windswept_Dead_Big_45` | StaticMesh | 0.17 | 4,401 | 18.11x16.68x10.63 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Windswept_Dead/Meshes/SM_Tree_Windswept_Dead_Big_46` | StaticMesh | 0.17 | 4,463 | 14.58x9.16x8.81 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Windswept_Dead/Meshes/SM_Tree_Windswept_Dead_Big_47` | StaticMesh | 0.24 | 5,851 | 18.49x18.56x15.68 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Windswept_Dead/Meshes/SM_Tree_Windswept_Dead_Big_48` | StaticMesh | 0.15 | 3,785 | 4.26x6.47x8.23 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Windswept_Dead/Meshes/SM_Tree_Windswept_Dead_Big_49` | StaticMesh | 0.16 | 3,988 | 5.99x6.96x4.89 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Windswept_Dead/Meshes/SM_Tree_Windswept_Dead_Big_5` | StaticMesh | 0.08 | 1,975 | 5.66x9.98x6.33 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Windswept_Dead/Meshes/SM_Tree_Windswept_Dead_Big_50` | StaticMesh | 0.18 | 4,624 | 7.09x4.46x6.43 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Windswept_Dead/Meshes/SM_Tree_Windswept_Dead_Big_51` | StaticMesh | 0.12 | 2,790 | 4.51x3.61x5.19 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Windswept_Dead/Meshes/SM_Tree_Windswept_Dead_Big_52` | StaticMesh | 0.15 | 3,559 | 3.94x6.83x8.18 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Windswept_Dead/Meshes/SM_Tree_Windswept_Dead_Big_53` | StaticMesh | 0.36 | 8,960 | 9.55x10.22x11.6 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Windswept_Dead/Meshes/SM_Tree_Windswept_Dead_Big_54` | StaticMesh | 0.28 | 6,735 | 9.89x5.26x9.13 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Windswept_Dead/Meshes/SM_Tree_Windswept_Dead_Big_55` | StaticMesh | 0.24 | 5,984 | 11.95x7.51x10.0 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Windswept_Dead/Meshes/SM_Tree_Windswept_Dead_Big_56` | StaticMesh | 0.01 | 127 | 0.65x0.88x2.06 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Windswept_Dead/Meshes/SM_Tree_Windswept_Dead_Big_57` | StaticMesh | 0.20 | 5,100 | 7.16x8.95x12.7 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Windswept_Dead/Meshes/SM_Tree_Windswept_Dead_Big_58` | StaticMesh | 0.18 | 4,308 | 8.82x10.17x12.37 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Windswept_Dead/Meshes/SM_Tree_Windswept_Dead_Big_59` | StaticMesh | 0.22 | 5,157 | 7.46x8.29x12.41 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Windswept_Dead/Meshes/SM_Tree_Windswept_Dead_Big_6` | StaticMesh | 0.07 | 1,693 | 4.33x8.02x7.08 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Windswept_Dead/Meshes/SM_Tree_Windswept_Dead_Big_60` | StaticMesh | 0.01 | 127 | 1.37x0.77x2.0 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Windswept_Dead/Meshes/SM_Tree_Windswept_Dead_Big_61` | StaticMesh | 0.23 | 5,615 | 8.44x10.06x11.1 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Windswept_Dead/Meshes/SM_Tree_Windswept_Dead_Big_62` | StaticMesh | 0.01 | 151 | 1.07x1.12x2.38 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Windswept_Dead/Meshes/SM_Tree_Windswept_Dead_Big_63` | StaticMesh | 0.30 | 7,273 | 18.38x15.34x28.29 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Windswept_Dead/Meshes/SM_Tree_Windswept_Dead_Big_64` | StaticMesh | 0.18 | 4,418 | 6.38x8.62x10.13 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Windswept_Dead/Meshes/SM_Tree_Windswept_Dead_Big_65` | StaticMesh | 0.19 | 4,765 | 7.73x6.04x14.61 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Windswept_Dead/Meshes/SM_Tree_Windswept_Dead_Big_66` | StaticMesh | 0.08 | 1,932 | 7.85x5.9x7.03 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Windswept_Dead/Meshes/SM_Tree_Windswept_Dead_Big_67` | StaticMesh | 0.20 | 4,995 | 8.31x10.11x11.42 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Windswept_Dead/Meshes/SM_Tree_Windswept_Dead_Big_68` | StaticMesh | 0.24 | 5,774 | 7.38x7.32x8.5 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Windswept_Dead/Meshes/SM_Tree_Windswept_Dead_Big_69` | StaticMesh | 0.19 | 4,586 | 11.32x6.16x12.31 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Windswept_Dead/Meshes/SM_Tree_Windswept_Dead_Big_7` | StaticMesh | 0.11 | 2,578 | 12.35x6.18x6.17 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Windswept_Dead/Meshes/SM_Tree_Windswept_Dead_Big_70` | StaticMesh | 0.05 | 1,107 | 1.93x3.75x6.81 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Windswept_Dead/Meshes/SM_Tree_Windswept_Dead_Big_71` | StaticMesh | 0.15 | 3,853 | 5.65x9.4x7.93 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Windswept_Dead/Meshes/SM_Tree_Windswept_Dead_Big_72` | StaticMesh | 0.01 | 177 | 1.86x0.57x1.78 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Windswept_Dead/Meshes/SM_Tree_Windswept_Dead_Big_73` | StaticMesh | 0.23 | 5,766 | 9.53x12.53x9.41 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Windswept_Dead/Meshes/SM_Tree_Windswept_Dead_Big_74` | StaticMesh | 0.01 | 195 | 0.59x1.38x2.6 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Windswept_Dead/Meshes/SM_Tree_Windswept_Dead_Big_75` | StaticMesh | 0.20 | 5,004 | 11.37x11.71x10.11 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Windswept_Dead/Meshes/SM_Tree_Windswept_Dead_Big_76` | StaticMesh | 0.15 | 3,658 | 7.85x5.83x6.99 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Windswept_Dead/Meshes/SM_Tree_Windswept_Dead_Big_77` | StaticMesh | 0.17 | 4,182 | 7.75x3.89x10.33 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Windswept_Dead/Meshes/SM_Tree_Windswept_Dead_Big_78` | StaticMesh | 0.18 | 4,261 | 9.57x4.76x9.95 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Windswept_Dead/Meshes/SM_Tree_Windswept_Dead_Big_79` | StaticMesh | 0.05 | 1,223 | 2.74x3.09x4.81 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Windswept_Dead/Meshes/SM_Tree_Windswept_Dead_Big_8` | StaticMesh | 0.06 | 1,310 | 8.46x4.89x3.77 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Windswept_Dead/Meshes/SM_Tree_Windswept_Dead_Big_80` | StaticMesh | 0.21 | 5,198 | 7.35x9.66x12.77 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Windswept_Dead/Meshes/SM_Tree_Windswept_Dead_Big_81` | StaticMesh | 0.19 | 4,588 | 6.94x9.77x11.05 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Windswept_Dead/Meshes/SM_Tree_Windswept_Dead_Big_82` | StaticMesh | 0.10 | 2,587 | 4.75x8.39x11.95 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Windswept_Dead/Meshes/SM_Tree_Windswept_Dead_Big_83` | StaticMesh | 0.01 | 195 | 0.76x2.0x2.11 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Windswept_Dead/Meshes/SM_Tree_Windswept_Dead_Big_84` | StaticMesh | 0.01 | 206 | 0.74x2.23x2.09 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Windswept_Dead/Meshes/SM_Tree_Windswept_Dead_Big_85` | StaticMesh | 0.01 | 195 | 0.81x1.68x2.85 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Windswept_Dead/Meshes/SM_Tree_Windswept_Dead_Big_86` | StaticMesh | 0.26 | 6,399 | 4.87x10.84x8.12 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Windswept_Dead/Meshes/SM_Tree_Windswept_Dead_Big_87` | StaticMesh | 0.21 | 5,336 | 9.8x7.44x11.29 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Windswept_Dead/Meshes/SM_Tree_Windswept_Dead_Big_88` | StaticMesh | 0.18 | 4,494 | 11.06x6.24x10.27 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Windswept_Dead/Meshes/SM_Tree_Windswept_Dead_Big_89` | StaticMesh | 0.14 | 3,484 | 5.36x6.34x9.04 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Windswept_Dead/Meshes/SM_Tree_Windswept_Dead_Big_9` | StaticMesh | 0.07 | 1,641 | 12.04x4.7x2.78 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Windswept_Dead/Meshes/SM_Tree_Windswept_Dead_Big_90` | StaticMesh | 0.08 | 2,128 | 6.83x4.63x5.48 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Windswept_Dead/Meshes/SM_Tree_Windswept_Dead_Big_91` | StaticMesh | 0.21 | 5,184 | 6.2x9.72x9.59 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Windswept_Dead/Meshes/SM_Tree_Windswept_Dead_Big_92` | StaticMesh | 0.19 | 4,730 | 6.6x10.92x9.23 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Windswept_Dead/Meshes/SM_Tree_Windswept_Dead_Big_93` | StaticMesh | 0.01 | 206 | 1.87x1.14x2.31 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Windswept_Dead/Meshes/SM_Tree_Windswept_Dead_Big_94` | StaticMesh | 0.12 | 3,084 | 4.14x9.33x7.35 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Windswept_Dead/Meshes/SM_Tree_Windswept_Dead_Big_95` | StaticMesh | 0.01 | 195 | 1.91x0.88x2.4 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Windswept_Dead/Meshes/SM_Tree_Windswept_Dead_Big_96` | StaticMesh | 0.01 | 177 | 1.82x0.91x2.46 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Windswept_Dead/Meshes/SM_Tree_Windswept_Dead_Big_97` | StaticMesh | 0.01 | 206 | 1.76x1.64x1.92 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Windswept_Dead/Meshes/SM_Tree_Windswept_Dead_Big_98` | StaticMesh | 0.17 | 4,120 | 7.09x8.37x9.52 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Windswept_Dead/Meshes/SM_Tree_Windswept_Dead_Big_99` | StaticMesh | 0.11 | 2,673 | 7.08x5.92x10.43 | A30 | no | [foliage] |
| `/Game/Env/Bio/Tree/Pine/Tree_Windswept_Dead/Meshes/SM_Tree_Windswept_Dead_Trunk_3` | StaticMesh | 4.27 | 89,725 | 15.65x12.42x211.4 | A30 | no | [foliage] |

*Group note:* Large multi-part pine family (Tree_Pine, Windswept, Windswept_Dead, Deciduous, DeciduousDead, Sapling). PWR uses Windswept_A materials and Sapling_A. Lone trunk/branch meshes are parts, not trees

### Forest FX (falling needles, leaves) (5)

*Where on PWR:* Pine stands (needles) and deciduous groves (leaves)

| path | kind | MB | verts | bounds m | levels | PWR | note |
|---|---|---|---|---|---|---|---|
| `/Game/FX/Library/Environment/PNW/Plants/Trees/BlowingPetals/NS_Plants_Petals_Blowing` | NiagaraSystem | 0.06 |  |  | A30 | no |  |
| `/Game/FX/Library/Environment/PNW/Plants/Trees/FallingLeaves/NS_FallingLeaves_Banyan_Lp_01` | NiagaraSystem | 0.14 |  |  | E20 | no | off-setting (tropical/alien/marine) [setting] |
| `/Game/FX/Library/Environment/PNW/Plants/Trees/FallingLeaves/NS_FallingLeaves_BlackAlder` | NiagaraSystem | 0.14 |  |  | B30 | no |  |
| `/Game/FX/Library/Environment/PNW/Plants/Trees/FallingLeaves/NS_FallingLeaves_BlackAlder_CPU` | NiagaraSystem | 0.18 |  |  | B30 | no |  |
| `/Game/FX/Library/Environment/PNW/Plants/Trees/PineNeedles/NS_Trees_PineNeedles_Falling` | NiagaraSystem | 0.05 |  |  | A30 | no |  |

*Group note:* Shipped Niagara

### Burnt wood (Fab Megascans) (23)

*Where on PWR:* Burn scars around shelled bases

| path | kind | MB | verts | bounds m | levels | PWR | note |
|---|---|---|---|---|---|---|---|
| `/Game/Fab/Megascans/3D/Burnt_Log_vcsaeeyfa/Raw/FT_burnt_log_vcsaeeyfa_tier_0_FoliageType` | FoliageType | 0.00 |  |  | B30 | no |  |
| `/Game/Fab/Megascans/3D/Burnt_Log_vcsaeeyfa/Raw/MI_burnt_log_vcsaeeyfa` | MaterialInstance | 0.00 |  |  | B30,C10 | no |  |
| `/Game/Fab/Megascans/3D/Burnt_Log_vcsaeeyfa/Raw/SM_burnt_log_vcsaeeyfa_tier_0` | StaticMesh | 16.69 | 506,630 | 1.63x0.3x0.3 | B30,C10 | no | very dense: confirm Nanite before placing many |
| `/Game/Fab/Megascans/3D/Burnt_Tree_Branch_vdkhbivdb/Raw/FT_burnt_log_vdkhbivdb_tier_0_FoliageType` | FoliageType | 0.00 |  |  | B30 | no |  |
| `/Game/Fab/Megascans/3D/Burnt_Tree_Branch_vdkhbivdb/Raw/MI_burnt_tree_vdkhbivdb` | MaterialInstance | 0.05 |  |  | B30,C10 | no |  |
| `/Game/Fab/Megascans/3D/Burnt_Tree_Branch_vdkhbivdb/Raw/SM_burnt_log_vdkhbivdb_tier_0` | StaticMesh | 19.05 | 505,781 | 0.96x0.16x0.11 | B30,C10 | no | very dense: confirm Nanite before placing many |
| `/Game/Fab/Megascans/3D/Burnt_Tree_raBd7/Raw/MI_burnt_tree_raBd7` | MaterialInstance | 0.02 |  |  | C10 | no |  |
| `/Game/Fab/Megascans/3D/Burnt_Tree_raBd7/Raw/SM_burnt_tree_raBd7_tier_0` | StaticMesh | 16.20 | 465,980 | 1.23x1.26x3.15 | C10 | no | very dense: confirm Nanite before placing many |
| `/Game/Fab/Megascans/3D/Burnt_Wood_ulkhaanjw/Raw/FT_burnt_log_ulkhaanjw_tier_0_FoliageType` | FoliageType | 0.00 |  |  | B30 | no |  |
| `/Game/Fab/Megascans/3D/Burnt_Wood_ulkhaanjw/Raw/MI_burnt_tree_ulkhaanjw` | MaterialInstance | 0.05 |  |  | B30,C10 | no |  |
| `/Game/Fab/Megascans/3D/Burnt_Wood_ulkhaanjw/Raw/SM_burnt_log_ulkhaanjw_tier_0` | StaticMesh | 14.87 | 371,762 | 0.23x0.07x0.02 | B30,C10 | no |  |

Textures: `/Game/Fab/Megascans/3D/Burnt_Log_vcsaeeyfa/Raw/T_vcsaeeyfa_8K_B` (3.2 MB), `/Game/Fab/Megascans/3D/Burnt_Log_vcsaeeyfa/Raw/T_vcsaeeyfa_8K_N` (6.4 MB), `/Game/Fab/Megascans/3D/Burnt_Log_vcsaeeyfa/Raw/T_vcsaeeyfa_8K_ORM` (3.2 MB), `/Game/Fab/Megascans/3D/Burnt_Tree_Branch_vdkhbivdb/Raw/T_vdkhbivdb_8K_B` (3.2 MB), `/Game/Fab/Megascans/3D/Burnt_Tree_Branch_vdkhbivdb/Raw/T_vdkhbivdb_8K_N` (6.4 MB), `/Game/Fab/Megascans/3D/Burnt_Tree_Branch_vdkhbivdb/Raw/T_vdkhbivdb_8K_ORM` (3.2 MB), `/Game/Fab/Megascans/3D/Burnt_Tree_raBd7/Raw/T_raBd7_8K_N` (6.4 MB), `/Game/Fab/Megascans/3D/Burnt_Tree_raBd7/Raw/T_raBd7_8K_ORM` (3.2 MB), `/Game/Fab/Megascans/3D/Burnt_Wood_ulkhaanjw/Raw/T_ulkhaanjw_4K_B` (3.2 MB), `/Game/Fab/Megascans/3D/Burnt_Wood_ulkhaanjw/Raw/T_ulkhaanjw_4K_N` (6.4 MB), `/Game/Fab/Megascans/3D/Burnt_Wood_ulkhaanjw/Raw/T_ulkhaanjw_4K_ORM` (3.2 MB), `/Game/Fab/Megascans/Surfaces/Damp_Soil_scnmqbp0/High/T_scnmqbp0_4K_B` (3.2 MB)

*Group note:* Fab-imported burnt log/branch/tree scans

### A30/B40 tree assemblies (PCG recipes) (38)

*Where on PWR:* Recipe for assembled pines, tree skirts and snowy dead firs

| path | kind | MB | verts | bounds m | levels | PWR | note |
|---|---|---|---|---|---|---|---|
| `/Game/Levels/Halo1/Solo/A30/PCG/Assemblies/PineTree/BP_PineTree_Base` | Blueprint | 0.00 |  |  | A30 | no |  |
| `/Game/Levels/Halo1/Solo/A30/PCG/Assemblies/PineTree/BP_Tree_Deciduous` | Blueprint | 0.00 |  |  | A30 | no |  |
| `/Game/Levels/Halo1/Solo/A30/PCG/Assemblies/PineTree/BP_Tree_Deciduous_B` | Blueprint | 0.00 |  |  | A30 | no |  |
| `/Game/Levels/Halo1/Solo/A30/PCG/Assemblies/PineTree/BP_Tree_Windswept` | Blueprint | 0.00 |  |  | A30 | no |  |
| `/Game/Levels/Halo1/Solo/A30/PCG/Assemblies/PineTree/BP_Tree_Windswept_A` | Blueprint | 0.00 |  |  | A30 | no |  |
| `/Game/Levels/Halo1/Solo/A30/PCG/Assemblies/PineTree/BP_Tree_Windswept_Dead` | Blueprint | 0.00 |  |  | A30 | no |  |
| `/Game/Levels/Halo1/Solo/A30/PCG/Assemblies/PineTree/DAPCG_Tree_Deciduous` | PCGDataAsset | 0.85 |  |  | A30 | no |  |
| `/Game/Levels/Halo1/Solo/A30/PCG/Assemblies/PineTree/DAPCG_Tree_Deciduous_B` | PCGDataAsset | 0.28 |  |  | A30 | no |  |
| `/Game/Levels/Halo1/Solo/A30/PCG/Assemblies/PineTree/DAPCG_Tree_Deciduous_Dead` | PCGDataAsset | 0.01 |  |  | A30 | no |  |
| `/Game/Levels/Halo1/Solo/A30/PCG/Assemblies/PineTree/DAPCG_Tree_Windswept` | PCGDataAsset | 0.24 |  |  | A30 | no |  |
| `/Game/Levels/Halo1/Solo/A30/PCG/Assemblies/PineTree/DAPCG_Tree_Windswept_A` | PCGDataAsset | 0.32 |  |  | A30 | no |  |
| `/Game/Levels/Halo1/Solo/A30/PCG/Assemblies/PineTree/DAPCG_Tree_Windswept_Dead` | PCGDataAsset | 0.28 |  |  | A30 | no |  |
| `/Game/Levels/Halo1/Solo/A30/PCG/Assemblies/PineTree/LI_Tree_Deciduous` | LevelInstance | 0.05 |  |  | A30 | no |  |
| `/Game/Levels/Halo1/Solo/A30/PCG/Assemblies/PineTree/LI_Tree_Deciduous_B` | LevelInstance | 0.02 |  |  | A30 | no |  |
| `/Game/Levels/Halo1/Solo/A30/PCG/Assemblies/PineTree/LI_Tree_Deciduous_Dead` | LevelInstance | 0.01 |  |  | A30 | no |  |
| `/Game/Levels/Halo1/Solo/A30/PCG/Assemblies/PineTree/LI_Tree_Windswept` | LevelInstance | 0.02 |  |  | A30 | no |  |
| `/Game/Levels/Halo1/Solo/A30/PCG/Assemblies/PineTree/LI_Tree_Windswept_A` | LevelInstance | 0.02 |  |  | A30 | no |  |
| `/Game/Levels/Halo1/Solo/A30/PCG/Assemblies/PineTree/LI_Tree_Windswept_Dead` | LevelInstance | 0.02 |  |  | A30 | no |  |
| `/Game/Levels/Halo1/Solo/A30/PCG/Assemblies/PineTree/PLAY_PineTree_CollisionMesh` | StaticMesh | 0.38 |  |  | A30 | no | collision proxy mesh |
| `/Game/Levels/Halo1/Solo/A30/PCG/Assemblies/Tree/Tree_Skirts/BP_TreeSkirt_Assembly` | Blueprint | 0.00 |  |  | A30 | no |  |
| `/Game/Levels/Halo1/Solo/A30/PCG/Assemblies/Tree/Tree_Skirts/DAPCG_TreeSkirt_01` | PCGDataAsset | 0.01 |  |  | A30 | no |  |
| `/Game/Levels/Halo1/Solo/A30/PCG/Assemblies/Tree/Tree_Skirts/LI_TreeSkirt_01` | LevelInstance | 0.01 |  |  | A30 | no |  |
| `/Game/Levels/Halo1/Solo/A30/PCG/Assemblies/Willow_Arctic/DAPCG_Willow_Arctic_A` | PCGDataAsset | 0.00 |  |  |  | no |  |
| `/Game/Levels/Halo1/Solo/A30/PCG/Assemblies/Willow_Arctic/LI_Willow_Arctic_A` | LevelInstance | 0.01 |  |  | A30 | no |  |
| `/Game/Levels/Halo1/Solo/B40/PCG/Assemblies/Arctic_Willow/BP_Willow_Arctic_A` | Blueprint | 0.00 |  |  | B40,C45 | no |  |
| `/Game/Levels/Halo1/Solo/B40/PCG/Assemblies/DouglasFir_SnowDead/BP_DouglasFir_SnowDead_A` | Blueprint | 0.00 |  |  | B40,C45 | no | snow variant; sibling used by PWR |
| `/Game/Levels/Halo1/Solo/B40/PCG/Assemblies/DouglasFir_SnowDead/BP_DouglasFir_SnowDead_B` | Blueprint | 0.00 |  |  | B40,C45 | no | snow variant; sibling used by PWR |
| `/Game/Levels/Halo1/Solo/B40/PCG/Assemblies/DouglasFir_SnowDead/BP_DouglasFir_SnowDead_Base` | Blueprint | 0.00 |  |  | B40,C45 | no | snow variant; sibling used by PWR |
| `/Game/Levels/Halo1/Solo/B40/PCG/Assemblies/DouglasFir_SnowDead/BP_DouglasFir_SnowDead_C` | Blueprint | 0.00 |  |  | B40,C45 | no | snow variant; sibling used by PWR |
| `/Game/Levels/Halo1/Solo/B40/PCG/Assemblies/DouglasFir_SnowDead/DAPCG_DouglasFir_SnowDead_A` | PCGDataAsset | 0.10 |  |  | B40,C45 | no | snow variant; sibling used by PWR |
| `/Game/Levels/Halo1/Solo/B40/PCG/Assemblies/DouglasFir_SnowDead/DAPCG_DouglasFir_SnowDead_B` | PCGDataAsset | 0.03 |  |  | B40,C45 | no | snow variant; sibling used by PWR |
| `/Game/Levels/Halo1/Solo/B40/PCG/Assemblies/DouglasFir_SnowDead/DAPCG_DouglasFir_SnowDead_C` | PCGDataAsset | 0.03 |  |  | B40,C45 | no | snow variant; sibling used by PWR |
| `/Game/Levels/Halo1/Solo/B40/PCG/Assemblies/DouglasFir_SnowDead/LI_DouglasFir_SnowDead_A` | LevelInstance | 0.01 |  |  | B40 | no | snow variant; sibling used by PWR |
| `/Game/Levels/Halo1/Solo/B40/PCG/Assemblies/DouglasFir_SnowDead/LI_DouglasFir_SnowDead_B` | LevelInstance | 0.01 |  |  | B40 | no | snow variant; sibling used by PWR |
| `/Game/Levels/Halo1/Solo/B40/PCG/Assemblies/DouglasFir_SnowDead/LI_DouglasFir_SnowDead_C` | LevelInstance | 0.01 |  |  | B40 | no | snow variant; sibling used by PWR |
| `/Game/Levels/Halo1/Solo/B40/PCG/Assemblies/DouglasFir_SnowDead/MI_DouglasFirBranch_Snow` | MaterialInstance | 0.10 |  |  | B40,C45 | listed | snow variant |
| `/Game/Levels/Halo1/Solo/B40/PCG/Assemblies/DouglasFir_SnowDead/MI_DouglasFirTrunk_Snow` | MaterialInstance | 0.03 |  |  | B40,C45 | listed | snow variant |
| `/Game/Levels/Halo1/Solo/B40/PCG/Assemblies/DouglasFir_SnowDead/SM_PineBranchSnow_Large` | StaticMesh | 0.32 | 8,322 | 1.07x1.63x0.89 | B40 | no | snow variant; sibling used by PWR |

*Group note:* Shipped assemblies (BP + DAPCG + LI) of the Pine/DouglasFir parts; read the members, then place as decor/foliage

### Fallen logs, branches and stumps (Megascans 3D) (86)

*Where on PWR:* Forest floor deadfall, log piles at road cuts, windthrow on slopes

| path | kind | MB | verts | bounds m | levels | PWR | note |
|---|---|---|---|---|---|---|---|
| `/Game/Megascans/3D_Assets/Birch_Log_thksahyda/MI_Birch_Log_thksahyda_4K` | MaterialInstance | 0.00 |  |  | A30 | no |  |
| `/Game/Megascans/3D_Assets/Birch_Log_thksahyda/MI_Birch_Log_thksahyda_DeSat` | MaterialInstance | 0.12 |  |  | A30 | no |  |
| `/Game/Megascans/3D_Assets/Birch_Log_thksahyda/S_Birch_Log_thksahyda_lod0` | StaticMesh | 0.09 | 2,434 | 1.45x0.16x0.16 | A30 | no |  |
| `/Game/Megascans/3D_Assets/BrokenTreeAssembly/MI_BrokenTreeAssembly_01` | MaterialInstance | 0.03 |  |  | C10 | no |  |
| `/Game/Megascans/3D_Assets/BrokenTreeAssembly/MI_BrokenTreeAssembly_01_Dark` | MaterialInstance | 0.03 |  |  | C10 | no |  |
| `/Game/Megascans/3D_Assets/BrokenTreeAssembly/SM_BrokenTreeAssembly_01` | StaticMesh | 5.56 | 153,214 | 4.7x3.96x1.44 | C10 | no |  |
| `/Game/Megascans/3D_Assets/BrokenTreeBranch/MI_BrokenTreeBranch_01` | MaterialInstance | 0.00 |  |  | C10 | no |  |
| `/Game/Megascans/3D_Assets/BrokenTreeBranch/SM_BrokenTreeBranch_01` | StaticMesh | 1.38 | 43,298 | 1.02x0.34x0.21 | C10 | no |  |
| `/Game/Megascans/3D_Assets/Broken_Tree_Bark_wjhiecy/MI_Broken_Tree_Bark_wjhiecy_4K` | MaterialInstance | 0.03 |  |  | C10 | no | sibling used by PWR |
| `/Game/Megascans/3D_Assets/Broken_Tree_Bark_wjhiecy/S_Broken_Tree_Bark_wjhiecy_lod0_Var1` | StaticMesh | 0.89 | 4,975 | 0.77x0.17x0.12 | C10 | yes |  |
| `/Game/Megascans/3D_Assets/Burnt_Log_vcsaeeyfa/MI_Burnt_Log_vcsaeeyfa_01` | MaterialInstance | 0.12 |  |  | A30 | no |  |
| `/Game/Megascans/3D_Assets/Burnt_Log_vcsaeeyfa/SM_Burnt_Log_vcsaeeyfa_01` | StaticMesh | 0.35 | 6,676 | 1.63x0.29x0.29 | A30 | no |  |
| `/Game/Megascans/3D_Assets/Burnt_Tree_Branch_vdkhbivdb/MI_Burnt_Tree_Branch_vdkhbivdb_8K` | MaterialInstance | 0.00 |  |  | C10 | no |  |
| `/Game/Megascans/3D_Assets/Burnt_Tree_Branch_vdkhbivdb/S_Burnt_Tree_Branch_vdkhbivdb_high_Var1` | StaticMesh | 16.15 | 513,938 | 0.96x0.16x0.11 | C10 | no | very dense: confirm Nanite before placing many |
| `/Game/Megascans/3D_Assets/Burnt_Tree_Stump_vdpjddcga/MI_Burnt_Tree_Stump_vdpjddcga_01` | MaterialInstance | 0.12 |  |  | A30 | no |  |
| `/Game/Megascans/3D_Assets/Burnt_Tree_Stump_vdpjddcga/SM_Burnt_Tree_Stump_vdpjddcga_01` | StaticMesh | 0.27 | 7,392 | 1.69x1.67x2.47 | A30 | no |  |
| `/Game/Megascans/3D_Assets/Burnt_Tree_Trunk_vcpocfoga/MI_Burnt_Tree_Trunk_vcpocfoga` | MaterialInstance | 0.14 |  |  | A30 | no |  |
| `/Game/Megascans/3D_Assets/Dead_Branches_qjuwd/MI_Dead_Branches_qjuwd_8K` | MaterialInstance | 0.12 |  |  | A30,C45 | no |  |
| `/Game/Megascans/3D_Assets/Dead_Branches_qjuwd/S_Dead_Branches_qjuwd_high_Var1` | StaticMesh | 0.26 | 7,767 | 0.07x0.32x0.04 | A30 | no |  |
| `/Game/Megascans/3D_Assets/Dead_Branches_qjuwd/S_Dead_Branches_qjuwd_high_Var2` | StaticMesh | 5.16 | 158,919 | 0.31x0.41x0.11 | C45 | no |  |
| `/Game/Megascans/3D_Assets/Dead_Branches_qjuwd/S_Dead_Branches_qjuwd_high_Var3` | StaticMesh | 0.31 | 8,898 | 0.23x0.3x0.05 | C45 | no |  |
| `/Game/Megascans/3D_Assets/Dead_Branches_qjuwd/S_Dead_Branches_qjuwd_high_Var5` | StaticMesh | 1.95 | 64,605 | 0.15x0.34x0.06 | C45 | no |  |
| `/Game/Megascans/3D_Assets/Dead_Tree_rlthg/MI_Env_Layered_Dead_Tree_rlthg` | MaterialInstance | 0.12 |  |  | C10 | no |  |
| `/Game/Megascans/3D_Assets/Dead_Tree_rlthg/MI_Env_Layered_Dead_Tree_rlthg_Wet` | MaterialInstance | 0.08 |  |  | C10 | no | wet variant |
| `/Game/Megascans/3D_Assets/Dead_Tree_rlthg/S_Dead_Tree_rlthg_high` | StaticMesh | 4.51 | 134,090 | 4.26x3.0x8.78 | C10 | no |  |
| `/Game/Megascans/3D_Assets/DryBranches/MI_DryBranches_01` | MaterialInstance | 0.00 |  |  | B30 | no | sibling used by PWR |
| `/Game/Megascans/3D_Assets/DryBranches/SM_DryBranches_01` | StaticMesh | 0.05 | 569 | 0.16x0.5x0.06 | B30 | yes |  |
| `/Game/Megascans/3D_Assets/DryBranches/SM_DryBranches_02` | StaticMesh | 0.04 | 446 | 0.04x0.46x0.02 | B30 | no | sibling used by PWR |
| `/Game/Megascans/3D_Assets/FallenSpruceTree/MI_FallenSpruceTree_01` | MaterialInstance | 0.03 |  |  | C10 | no |  |
| `/Game/Megascans/3D_Assets/FallenSpruceTree/SM_FallenSpruceTree_01` | StaticMesh | 0.78 | 21,617 | 7.29x1.93x0.9 | C10 | no |  |
| `/Game/Megascans/3D_Assets/Fallen_Tree_Log_xiclaj1r/MI_Fallen_Tree_Log_xiclaj1r_4K` | MaterialInstance | 0.01 |  |  | A30 | no | sibling used by PWR |
| `/Game/Megascans/3D_Assets/Fallen_Tree_Log_xiclaj1r/S_Fallen_Tree_Log_xiclaj1r_lod0_Var1` | StaticMesh | 1.14 | 13,702 | 5.51x0.71x0.81 | A30 | yes |  |
| `/Game/Megascans/3D_Assets/Fallen_Tree_Log_xiclbgu/Foliage/FT_Fallen_Tree_Log_xiclbgu_lod0_Var1_FoliageType` | FoliageType | 0.00 |  |  | C10 | no |  |
| `/Game/Megascans/3D_Assets/Fallen_Tree_Log_xiclbgu/MI_Env_Layered_Log_xiclbgu` | MaterialInstance | 0.12 |  |  | C10 | no |  |
| `/Game/Megascans/3D_Assets/Fallen_Tree_Log_xiclbgu/MI_Env_Layered_Log_xiclbgu_Wet` | MaterialInstance | 0.08 |  |  | C10 | no | wet variant |
| `/Game/Megascans/3D_Assets/Fallen_Tree_Log_xiclbgu/S_Fallen_Tree_Log_xiclbgu_lod0_Var1` | StaticMesh | 0.09 | 2,225 | 3.38x0.36x0.29 | C10 | no |  |
| `/Game/Megascans/3D_Assets/Fallen_Tree_Log_xiclcfl/MI_Fallen_Tree_Log_xiclcfl_4K` | MaterialInstance | 0.00 |  |  | A30 | no |  |
| `/Game/Megascans/3D_Assets/Fallen_Tree_Log_xiclcfl/MI_Fallen_Tree_Log_xiclcfl_DeSat` | MaterialInstance | 0.12 |  |  | A30 | no |  |
| `/Game/Megascans/3D_Assets/Fallen_Tree_Log_xiclcfl/S_Fallen_Tree_Log_xiclcfl_lod0_Var1` | StaticMesh | 0.17 | 4,494 | 2.34x0.6x0.8 | A30 | no |  |
| `/Game/Megascans/3D_Assets/Large_Fallen_Tree_wd3hfidbw/MI_Large_Fallen_Tree_wd3hfidbw_4K` | MaterialInstance | 0.01 |  |  | A30 | no |  |
| `/Game/Megascans/3D_Assets/Large_Fallen_Tree_wd3hfidbw/MI_Large_Fallen_Tree_wd3hfidbw_DeSat` | MaterialInstance | 0.13 |  |  | A30 | no |  |
| `/Game/Megascans/3D_Assets/Large_Fallen_Tree_wd3hfidbw/S_Large_Fallen_Tree_wd3hfidbw_lod0_Var1` | StaticMesh | 0.44 | 10,833 | 9.4x1.34x1.14 | A30 | no |  |
| `/Game/Megascans/3D_Assets/Mossy_Tree_Log_rdkeg/MI_Mossy_Tree_Log_rdkeg_8K` | MaterialInstance | 0.01 |  |  | A30 | no | sibling used by PWR |
| `/Game/Megascans/3D_Assets/Mossy_Tree_Log_rdkeg/MI_Mossy_Tree_Log_rdkeg_DeSat` | MaterialInstance | 0.12 |  |  | A30 | no | sibling used by PWR |
| `/Game/Megascans/3D_Assets/Mossy_Tree_Log_rdkeg/S_Mossy_Tree_Log_rdkeg_high` | StaticMesh | 1.36 | 38,635 | 4.97x0.84x0.67 | A30 | yes |  |
| `/Game/Megascans/3D_Assets/Nordic_Forest_Tree_Branch_Pine_Small_xiejago/MI_Nordic_Forest_Tree_Branch_Pine_Small_xiejago_8K` | MaterialInstance | 0.01 |  |  | A30 | no |  |
| `/Game/Megascans/3D_Assets/Nordic_Forest_Tree_Branch_Pine_Small_xiejago/MI_Nordic_Forest_Tree_Branch_Pine_Small_xiejago_DeSat` | MaterialInstance | 0.12 |  |  | A30 | no |  |
| `/Game/Megascans/3D_Assets/Nordic_Forest_Tree_Branch_Pine_Small_xiejago/S_Nordic_Forest_Tree_Branch_Pine_Small_xiejago_high` | StaticMesh | 0.16 | 3,670 | 2.14x1.03x0.59 | A30 | no |  |
| `/Game/Megascans/3D_Assets/Nordic_Forest_Tree_Branch_Small_xiekedo/MI_Nordic_Forest_Tree_Branch_Small_xiekedo_8K` | MaterialInstance | 0.00 |  |  | A30 | no |  |
| `/Game/Megascans/3D_Assets/Nordic_Forest_Tree_Branch_Small_xiekedo/S_Nordic_Forest_Tree_Branch_Small_xiekedo_high_Var1` | StaticMesh | 0.08 | 2,238 | 1.93x0.3x0.14 | A30 | no |  |
| `/Game/Megascans/3D_Assets/Oak_Tree_Branch_wd0pcgibw/Foliage/FT_Oak_Tree_Branch_wd0pcgibw_lod0_Var1_FoliageType` | FoliageType | 0.00 |  |  | C10 | no |  |
| `/Game/Megascans/3D_Assets/Oak_Tree_Branch_wd0pcgibw/MI_Oak_Tree_Branch_wd0pcgibw_4K` | MaterialInstance | 0.00 |  |  | C10 | no |  |
| `/Game/Megascans/3D_Assets/Oak_Tree_Branch_wd0pcgibw/S_Oak_Tree_Branch_wd0pcgibw_lod0_Var1` | StaticMesh | 0.12 | 2,678 | 2.59x0.94x0.34 | C10 | no |  |
| `/Game/Megascans/3D_Assets/OldFallenTree/MI_OldFallenTree_01` | MaterialInstance | 0.00 |  |  | C10 | no |  |
| `/Game/Megascans/3D_Assets/OldFallenTree/MI_OldFallenTree_02` | MaterialInstance | 0.00 |  |  | C10 | no |  |
| `/Game/Megascans/3D_Assets/OldFallenTree/SM_OldFallenTree_01` | StaticMesh | 3.85 | 118,623 | 2.29x0.66x0.4 | C10 | no |  |
| `/Game/Megascans/3D_Assets/OldFallenTree/SM_OldFallenTree_02` | StaticMesh | 4.01 | 125,330 | 3.57x0.3x0.19 | C10 | no |  |
| `/Game/Megascans/3D_Assets/OldTreeBranch/Foliage/FT_OldTreeBranch_02_FoliageType` | FoliageType | 0.00 |  |  | C10 | no |  |
| `/Game/Megascans/3D_Assets/OldTreeBranch/Foliage/FT_OldTreeBranch_05_FoliageType` | FoliageType | 0.00 |  |  | C10 | no |  |
| `/Game/Megascans/3D_Assets/OldTreeBranch/MI_Env_Layered_OldTreeBranch_02` | MaterialInstance | 0.12 |  |  | C10 | no |  |
| `/Game/Megascans/3D_Assets/OldTreeBranch/MI_OldTreeBranch_02` | MaterialInstance | 0.03 |  |  | C10 | no |  |
| `/Game/Megascans/3D_Assets/OldTreeBranch/MI_OldTreeBranch_06` | MaterialInstance | 0.03 |  |  | C10 | no |  |
| `/Game/Megascans/3D_Assets/OldTreeBranch/SM_OldTreeBranch_02` | StaticMesh | 0.15 | 3,894 | 6.83x0.6x0.27 | C10 | no |  |
| `/Game/Megascans/3D_Assets/OldTreeBranch/SM_OldTreeBranch_05` | StaticMesh | 0.30 | 6,501 | 2.94x1.44x1.39 | C10 | no |  |
| `/Game/Megascans/3D_Assets/Old_Tree_Branch_wd3lcgcbw/MI_Env_Layered_Old_Tree_Branch_wd3lcgcbw_4K` | MaterialInstance | 0.12 |  |  | C10 | no |  |
| `/Game/Megascans/3D_Assets/Old_Tree_Branch_wd3lcgcbw/MI_Env_Layered_Old_Tree_Branch_wd3lcgcbw_4K_Wet` | MaterialInstance | 0.08 |  |  | C10 | no | wet variant |
| `/Game/Megascans/3D_Assets/Old_Tree_Branch_wd3lcgcbw/S_Old_Tree_Branch_wd3lcgcbw_lod0_Var1` | StaticMesh | 0.66 | 7,899 | 1.66x1.11x0.4 | C10 | no |  |
| `/Game/Megascans/3D_Assets/Old_Tree_Branch_wdyjbgqbw/MI_Old_Tree_Branch_wdyjbgqbw_4K` | MaterialInstance | 0.12 |  |  | A30 | no |  |
| `/Game/Megascans/3D_Assets/Old_Tree_Branch_wdyjbgqbw/S_Old_Tree_Branch_wdyjbgqbw_lod0_Var1` | StaticMesh | 0.20 | 5,699 | 1.47x0.6x0.54 | A30 | no |  |
| `/Game/Megascans/3D_Assets/Old_wooden_log_wcjgeel/MI_old_wooden_log_wcjgeel_01` | MaterialInstance | 0.12 |  |  | A30 | no |  |
| `/Game/Megascans/3D_Assets/Old_wooden_log_wcjgeel/SM_old_wooden_log_wcjgeel` | StaticMesh | 0.37 | 5,231 | 3.16x0.37x0.38 | A30 | no |  |
| `/Game/Megascans/3D_Assets/Pruned_Tree_vcrwcdqfa/MI_Pruned_Tree_vcrwcdqfa_8K` | MaterialInstance | 0.00 |  |  | D20 | no |  |
| `/Game/Megascans/3D_Assets/Pruned_Tree_vcrwcdqfa/S_Pruned_Tree_vcrwcdqfa_high_Var1` | StaticMesh | 1.85 | 53,915 | 2.83x2.29x6.68 | D20 | no |  |
| `/Game/Megascans/3D_Assets/Pruned_Tree_vcwhcexqx/MI_Pruned_Tree_vcwhcexqx_8K` | MaterialInstance | 0.00 |  |  | D20 | no |  |
| `/Game/Megascans/3D_Assets/Pruned_Tree_vcwhcexqx/S_Pruned_Tree_vcwhcexqx_high_Var1` | StaticMesh | 0.97 | 26,921 | 2.89x1.69x5.93 | D20 | no |  |
| `/Game/Megascans/3D_Assets/Pruned_Tree_vdfhcjmfa/MI_Pruned_Tree_vdfhcjmfa_8K` | MaterialInstance | 0.03 |  |  | C10,D20 | no |  |
| `/Game/Megascans/3D_Assets/Pruned_Tree_vdfhcjmfa/S_Pruned_Tree_vdfhcjmfa_high_Var1` | StaticMesh | 1.76 | 52,391 | 1.98x1.51x6.42 | C10,D20 | no |  |
| `/Game/Megascans/3D_Assets/birch_log_thkpajbda/MI_birch_log_thkpajbda_01` | MaterialInstance | 0.12 |  |  | A30 | no |  |
| `/Game/Megascans/3D_Assets/birch_log_thkpajbda/SM_birch_log_thkpajbda` | StaticMesh | 0.31 | 2,658 | 3.84x0.52x0.28 | A30 | no |  |
| `/Game/Megascans/3D_Assets/dry_branches_pdye3/MI_dry_branches_pdye3_01` | MaterialInstance | 0.12 |  |  | A30,E20 | no |  |
| `/Game/Megascans/3D_Assets/dry_branches_pdye3/SM_dry_branches_pdye3_01` | StaticMesh | 0.01 | 155 | 0.16x0.5x0.06 | E20 | no |  |
| `/Game/Megascans/3D_Assets/dry_branches_pdye3/SM_dry_branches_pdye3_06` | StaticMesh | 0.02 | 75 | 0.04x0.32x0.02 | A30 | no |  |
| `/Game/Megascans/3D_Assets/mossy_birch_log_tjsicjffa/MI_mossy_birch_log_tjsicjffa_01` | MaterialInstance | 0.12 |  |  | A30 | no |  |
| `/Game/Megascans/3D_Assets/mossy_birch_log_tjsicjffa/SM_mossy_birch_log_tjsicjffa` | StaticMesh | 0.55 | 5,501 | 1.31x0.23x0.23 | A30 | no |  |
| `/Game/Megascans/3D_Assets/old_wooden_log_wcolfi1/MI_old_wooden_log_wcolfi1_01` | MaterialInstance | 0.12 |  |  | A30 | no |  |
| `/Game/Megascans/3D_Assets/old_wooden_log_wcolfi1/SM_old_wooden_log_wcolfi1` | StaticMesh | 0.45 | 5,247 | 3.79x0.48x0.44 | A30 | no |  |

*Group note:* Megascans wood scans; PWR uses a few (Fallen_Tree_Log_xiclaj1r, Mossy_Tree_Log, DryBranches_01, Broken_Tree_Bark)

### Forest rocks (Megascans 3D) (34)

*Where on PWR:* Moss-covered boulders and outcrops inside the pine stands

| path | kind | MB | verts | bounds m | levels | PWR | note |
|---|---|---|---|---|---|---|---|
| `/Game/Megascans/3D_Assets/Forest_Rock_Formation_wgprdcp/MI_Forest_Rock_Formation_wgprdcp_4K` | MaterialInstance | 0.00 |  |  | B40,C45 | no |  |
| `/Game/Megascans/3D_Assets/Forest_Rock_Formation_wgprdcp/S_Forest_Rock_Formation_wgprdcp_lod0_Var1` | StaticMesh | 0.95 | 7,414 | 3.27x1.38x0.2 | B40,C45 | no |  |
| `/Game/Megascans/3D_Assets/MossyForestBoulder/MI_MossyForestBoulder_03` | MaterialInstance | 0.00 |  |  | C10 | no |  |
| `/Game/Megascans/3D_Assets/MossyForestBoulder/MI_MossyForestBoulder_03_Dark` | MaterialInstance | 0.00 |  |  | C10 | no |  |
| `/Game/Megascans/3D_Assets/MossyForestBoulder/MI_MossyForestBoulder_04` | MaterialInstance | 0.00 |  |  | C10 | no |  |
| `/Game/Megascans/3D_Assets/MossyForestBoulder/MI_MossyForestBoulder_04_Dark` | MaterialInstance | 0.00 |  |  | C10 | no |  |
| `/Game/Megascans/3D_Assets/MossyForestBoulder/MI_MossyForestBoulder_06` | MaterialInstance | 0.00 |  |  | C10 | no |  |
| `/Game/Megascans/3D_Assets/MossyForestBoulder/SM_MossyForestBoulder_02` | StaticMesh | 0.89 | 145 | 0.92x0.77x0.6 | C10 | no |  |
| `/Game/Megascans/3D_Assets/MossyForestBoulder/SM_MossyForestBoulder_03` | StaticMesh | 0.99 | 457 | 1.98x1.98x1.3 | C10 | no |  |
| `/Game/Megascans/3D_Assets/MossyForestBoulder/SM_MossyForestBoulder_04` | StaticMesh | 1.18 | 26,334 | 3.25x3.11x1.99 | C10 | no |  |
| `/Game/Megascans/3D_Assets/MossyForestRock/MI_MossyForestRock_02` | MaterialInstance | 0.03 |  |  | C10 | no |  |
| `/Game/Megascans/3D_Assets/MossyForestRock/MI_MossyForestRock_Dark` | MaterialInstance | 0.03 |  |  | C10 | no |  |
| `/Game/Megascans/3D_Assets/MossyForestRock/SM_MossyForestRock_02` | StaticMesh | 0.88 | 196 | 1.2x1.06x0.71 | C10 | no |  |
| `/Game/Megascans/3D_Assets/Mossy_Forest_Rock_vikrdcnaw/FT_Mossy_Forest_Rock_vkrdcnaw` | FoliageType | 0.00 |  |  | A30 | no |  |
| `/Game/Megascans/3D_Assets/Mossy_Forest_Rock_vikrdcnaw/MI_Rock_Mossy_visscjf_v02` | MaterialInstance | 0.15 |  |  | A30 | no |  |
| `/Game/Megascans/3D_Assets/Mossy_Forest_Rock_vikrdcnaw/SM_Mossy_Forest_Rock_vkrdcnaw` | StaticMesh | 0.70 | 6,850 | 0.7x0.54x0.43 | A30 | no |  |
| `/Game/Megascans/3D_Assets/Mossy_stones_pack_tliiadmva/FT_Mossy_Stones_Pack_tliiadmva_Var_01` | FoliageType | 0.00 |  |  | A30 | no | sibling used by PWR |
| `/Game/Megascans/3D_Assets/Mossy_stones_pack_tliiadmva/FT_Mossy_Stones_Pack_tliiadmva_Var_02` | FoliageType | 0.00 |  |  | A30 | no | sibling used by PWR |
| `/Game/Megascans/3D_Assets/Mossy_stones_pack_tliiadmva/FT_Mossy_Stones_Pack_tliiadmva_Var_03` | FoliageType | 0.00 |  |  | A30 | no | sibling used by PWR |
| `/Game/Megascans/3D_Assets/Mossy_stones_pack_tliiadmva/FT_Mossy_Stones_Pack_tliiadmva_Var_04` | FoliageType | 0.00 |  |  | A30 | no | sibling used by PWR |
| `/Game/Megascans/3D_Assets/Mossy_stones_pack_tliiadmva/SM_Mossy_Stones_Pack_tliiadmva_Var_01` | StaticMesh | 0.27 | 2,162 | 0.16x0.23x0.13 | A30 | yes |  |
| `/Game/Megascans/3D_Assets/Mossy_stones_pack_tliiadmva/SM_Mossy_Stones_Pack_tliiadmva_Var_02` | StaticMesh | 0.22 | 2,372 | 0.34x0.23x0.18 | A30 | yes |  |
| `/Game/Megascans/3D_Assets/Mossy_stones_pack_tliiadmva/SM_Mossy_Stones_Pack_tliiadmva_Var_03` | StaticMesh | 0.20 | 2,204 | 0.08x0.15x0.08 | A30 | no | sibling used by PWR |
| `/Game/Megascans/3D_Assets/Mossy_stones_pack_tliiadmva/SM_Mossy_Stones_Pack_tliiadmva_Var_04` | StaticMesh | 0.34 | 2,748 | 0.13x0.11x0.08 | A30 | yes |  |
| `/Game/Megascans/3D_Assets/Nordic_Forest_Cluster_Rock_Medium_xfplcbf/MIP_Nordic_Forest_Cluster_Rock_Medium_xfplcbf_Layered` | MaterialInstance | 0.12 |  |  | C10 | no |  |
| `/Game/Megascans/3D_Assets/Nordic_Forest_Cluster_Rock_Medium_xfplcbf/MIP_Nordic_Forest_Cluster_Rock_Medium_xfplcbf_Layered_Wet` | MaterialInstance | 0.08 |  |  | C10 | no | wet variant |
| `/Game/Megascans/3D_Assets/Nordic_Forest_Cluster_Rock_Medium_xfplcbf/S_Nordic_Forest_Cluster_Rock_Medium_xfplcbf_high_Var1` | StaticMesh | 0.84 | 25,550 | 1.85x2.0x1.01 | C10 | no |  |
| `/Game/Megascans/3D_Assets/Nordic_Forest_Rock_Small_xjiifd1/MI_Nordic_Forest_Rock_Small_xjiifd1_01` | MaterialInstance | 0.12 |  |  | A30 | no |  |
| `/Game/Megascans/3D_Assets/Nordic_Forest_Rock_Small_xjiifd1/SM_Nordic_Forest_Rock_Small_xjiifd1_01` | StaticMesh | 0.41 | 4,650 | 0.82x0.7x0.37 | A30 | no |  |
| `/Game/Megascans/3D_Assets/Nordic_Forest_Rock_Small_xjijbgx/MI_Nordic_Forest_Rock_Small_xjijbgx` | MaterialInstance | 0.12 |  |  | A30 | no |  |
| `/Game/Megascans/3D_Assets/Nordic_Forest_Rock_Small_xjijbgx/SM_Nordic_Forest_Rock_Small_xjijbgx` | StaticMesh | 0.18 | 3,672 | 1.17x0.9x0.56 | A30 | no |  |
| `/Game/Megascans/3D_Assets/Rough_Forest_Rock_reFto/MI_Rough_Forest_Rock_reFto_4K` | MaterialInstance | 0.00 |  |  | C10 | no |  |
| `/Game/Megascans/3D_Assets/Rough_Forest_Rock_reFto/MI_Rough_Forest_Rock_reFto_4K_Dark` | MaterialInstance | 0.03 |  |  | C10 | no |  |
| `/Game/Megascans/3D_Assets/Rough_Forest_Rock_reFto/SM_Rough_Forest_Rock_reFto_LOD0` | StaticMesh | 1.23 | 12,332 | 1.84x1.55x0.16 | C10 | no |  |

*Group note:* Megascans forest rock scans; Mossy_stones_pack partly used

### Understory plants (Megascans) (200)

*Where on PWR:* Forest floor, clearings and forest edges

| path | kind | MB | verts | bounds m | levels | PWR | note |
|---|---|---|---|---|---|---|---|
| `/Game/Megascans/3D_Plants/BeechFern/Foliage/FT_BeechFern_02_FoliageType` | FoliageType | 0.00 |  |  | E20 | no | [foliage] |
| `/Game/Megascans/3D_Plants/BeechFern/Foliage/FT_BeechFern_12_FoliageType` | FoliageType | 0.00 |  |  | E20 | no | [foliage] |
| `/Game/Megascans/3D_Plants/BeechFern/Foliage/FT_BeechFern_13_FoliageType` | FoliageType | 0.00 |  |  | E20 | no | [foliage] |
| `/Game/Megascans/3D_Plants/BeechFern/MI_BeechFern_02` | MaterialInstance | 0.00 |  |  | C10,E20 | no | [foliage]; sibling used by PWR |
| `/Game/Megascans/3D_Plants/BeechFern/SM_BeechFern_01` | StaticMesh | 2.33 | 55,440 | 0.17x0.1x0.11 | E20 | no | [foliage]; sibling used by PWR |
| `/Game/Megascans/3D_Plants/BeechFern/SM_BeechFern_02` | StaticMesh | 2.05 | 47,806 | 0.12x0.1x0.15 | E20 | no | [foliage]; sibling used by PWR |
| `/Game/Megascans/3D_Plants/BeechFern/SM_BeechFern_03` | StaticMesh | 2.16 | 52,738 | 0.12x0.12x0.1 | E20 | no | [foliage]; sibling used by PWR |
| `/Game/Megascans/3D_Plants/BeechFern/SM_BeechFern_05` | StaticMesh | 24.27 | 631,893 | 0.48x0.49x0.22 | C10 | no | very dense: confirm Nanite before placing many [foliage]; sibling used by PWR |
| `/Game/Megascans/3D_Plants/BeechFern/SM_BeechFern_11` | StaticMesh | 7.51 | 167,035 | 0.35x0.29x0.19 | C10,E20 | no | [foliage]; sibling used by PWR |
| `/Game/Megascans/3D_Plants/BeechFern/SM_BeechFern_12` | StaticMesh | 5.37 | 118,770 | 0.26x0.24x0.18 | E20 | no | [foliage]; sibling used by PWR |
| `/Game/Megascans/3D_Plants/BeechFern/SM_BeechFern_13` | StaticMesh | 3.44 | 76,160 | 0.21x0.2x0.19 | E20 | no | [foliage]; sibling used by PWR |
| `/Game/Megascans/3D_Plants/BeechFern/SM_BeechFern_14` | StaticMesh | 0.25 | 6,402 | 0.12x0.1x0.15 | E20 | yes | [foliage] |
| `/Game/Megascans/3D_Plants/BeechFern/SM_BeechFern_15` | StaticMesh | 2.16 | 42,724 | 0.44x0.4x0.24 | C10 | yes | [foliage] |
| `/Game/Megascans/3D_Plants/Blackberry_vkmofctha/FT_Blackberry_vkmofctha_0_Var11_lod0` | FoliageType | 0.00 |  |  | A30 | no | [foliage]; sibling used by PWR |
| `/Game/Megascans/3D_Plants/Blackberry_vkmofctha/Foliage/FT_Blackberry_vkmofctha_Var11_lod0` | FoliageType | 0.00 |  |  | C10 | no | [foliage] |
| `/Game/Megascans/3D_Plants/Blackberry_vkmofctha/Foliage/FT_Blackberry_vkmofctha_Var12_lod0` | FoliageType | 0.00 |  |  | C10 | no | [foliage] |
| `/Game/Megascans/3D_Plants/Blackberry_vkmofctha/Foliage/FT_Blackberry_vkmofctha_Var7_lod0` | FoliageType | 0.00 |  |  | C10 | no | [foliage] |
| `/Game/Megascans/3D_Plants/Blackberry_vkmofctha/MI_Blackberry_vkmofctha_4K` | MaterialInstance | 0.05 |  |  | A30,C10 | no | [foliage]; sibling used by PWR |
| `/Game/Megascans/3D_Plants/Blackberry_vkmofctha/MI_Blackberry_vkmofctha_Billboard_4K` | MaterialInstance | 0.03 |  |  | C10 | no | [foliage]; sibling used by PWR |
| `/Game/Megascans/3D_Plants/Blackberry_vkmofctha/S_Blackberry_vkmofctha_0_Var10_lod0` | StaticMesh | 0.08 | 1,314 | 0.44x0.54x0.44 | C10 | no | [foliage]; sibling used by PWR |
| `/Game/Megascans/3D_Plants/Blackberry_vkmofctha/S_Blackberry_vkmofctha_0_Var11_lod0` | StaticMesh | 0.05 | 672 | 0.34x0.44x0.31 | A30,C10 | no | [foliage]; sibling used by PWR |
| `/Game/Megascans/3D_Plants/Blackberry_vkmofctha/S_Blackberry_vkmofctha_0_Var12_lod0` | StaticMesh | 0.15 | 2,723 | 1.14x0.37x0.46 | A30,C10 | no | [foliage]; sibling used by PWR |
| `/Game/Megascans/3D_Plants/Blackberry_vkmofctha/S_Blackberry_vkmofctha_0_Var1_lod0` | StaticMesh | 0.31 | 5,989 | 1.31x1.88x0.95 | A30,C10 | no | [foliage]; sibling used by PWR |
| `/Game/Megascans/3D_Plants/Blackberry_vkmofctha/S_Blackberry_vkmofctha_0_Var2_lod0` | StaticMesh | 0.03 | 431 | 0.32x0.27x0.28 | A30,C10 | no | [foliage]; sibling used by PWR |
| `/Game/Megascans/3D_Plants/Blackberry_vkmofctha/S_Blackberry_vkmofctha_0_Var3_lod0` | StaticMesh | 0.07 | 1,232 | 0.85x0.55x0.51 | C10 | no | [foliage]; sibling used by PWR |
| `/Game/Megascans/3D_Plants/Blackberry_vkmofctha/S_Blackberry_vkmofctha_0_Var4_lod0` | StaticMesh | 0.12 | 2,259 | 0.82x0.93x0.63 | A30,C10 | no | [foliage]; sibling used by PWR |
| `/Game/Megascans/3D_Plants/Blackberry_vkmofctha/S_Blackberry_vkmofctha_0_Var5_lod0` | StaticMesh | 0.47 | 8,660 | 1.34x1.77x0.81 | A30,C10 | no | [foliage]; sibling used by PWR |
| `/Game/Megascans/3D_Plants/Blackberry_vkmofctha/S_Blackberry_vkmofctha_0_Var6_lod0` | StaticMesh | 0.29 | 5,500 | 1.83x1.38x0.59 | A30,C10 | no | [foliage]; sibling used by PWR |
| `/Game/Megascans/3D_Plants/Blackberry_vkmofctha/S_Blackberry_vkmofctha_0_Var7_lod0` | StaticMesh | 0.53 | 10,296 | 1.53x2.0x0.8 | A30,C10 | no | [foliage]; sibling used by PWR |
| `/Game/Megascans/3D_Plants/Blackberry_vkmofctha/S_Blackberry_vkmofctha_0_Var8_lod0` | StaticMesh | 0.27 | 5,093 | 0.87x0.57x0.77 | A30,C10 | no | [foliage]; sibling used by PWR |
| `/Game/Megascans/3D_Plants/Blackberry_vkmofctha/S_Blackberry_vkmofctha_0_Var9_lod0` | StaticMesh | 0.04 | 516 | 0.24x0.21x0.46 | C10 | no | [foliage]; sibling used by PWR |
| `/Game/Megascans/3D_Plants/Blackberry_vkmofctha/S_Blackberry_vkmofctha_Var10_lod0` | StaticMesh | 0.08 | 1,314 | 0.44x0.54x0.44 | C10 | no | [foliage]; sibling used by PWR |
| `/Game/Megascans/3D_Plants/Blackberry_vkmofctha/S_Blackberry_vkmofctha_Var11_lod0` | StaticMesh | 0.05 | 672 | 0.34x0.44x0.31 | C10 | no | [foliage]; sibling used by PWR |
| `/Game/Megascans/3D_Plants/Blackberry_vkmofctha/S_Blackberry_vkmofctha_Var12_lod0` | StaticMesh | 0.15 | 2,723 | 1.14x0.37x0.46 | C10 | no | [foliage]; sibling used by PWR |
| `/Game/Megascans/3D_Plants/Blackberry_vkmofctha/S_Blackberry_vkmofctha_Var1_lod0` | StaticMesh | 0.31 | 5,989 | 1.31x1.88x0.95 | C10 | yes | [foliage] |
| `/Game/Megascans/3D_Plants/Blackberry_vkmofctha/S_Blackberry_vkmofctha_Var2_lod0` | StaticMesh | 0.03 | 431 | 0.32x0.27x0.28 | C10 | no | [foliage]; sibling used by PWR |
| `/Game/Megascans/3D_Plants/Blackberry_vkmofctha/S_Blackberry_vkmofctha_Var5_lod0` | StaticMesh | 0.47 | 8,660 | 1.34x1.77x0.81 | C10 | no | [foliage]; sibling used by PWR |
| `/Game/Megascans/3D_Plants/BostonFern/MI_BostonFern_01` | MaterialInstance | 0.03 |  |  | E20 | no | [foliage] |
| `/Game/Megascans/3D_Plants/BostonFern/SM_BostonFern_02_Traced` | StaticMesh | 2.72 | 101,577 | 0.15x0.15x0.07 | E20 | no | [foliage] |
| `/Game/Megascans/3D_Plants/Clovers_rbdjz/FT_Clovers_rbdjz_01` | FoliageType | 0.00 |  |  | A30 | no | [foliage] |
| `/Game/Megascans/3D_Plants/Clovers_rbdjz/FT_Clovers_rbdjz_02` | FoliageType | 0.00 |  |  | A30 | no | [foliage] |
| `/Game/Megascans/3D_Plants/Clovers_rbdjz/FT_Clovers_rbdjz_03` | FoliageType | 0.00 |  |  | A30 | no | [foliage] |
| `/Game/Megascans/3D_Plants/Clovers_rbdjz/MI_Clovers_rbdjz_01` | MaterialInstance | 0.03 |  |  | A30 | no | [foliage] |
| `/Game/Megascans/3D_Plants/Clovers_rbdjz/SM_Clovers_rbdjz_01` | StaticMesh | 0.09 | 684 | 0.79x0.61x0.14 | A30 | no | [foliage] |
| `/Game/Megascans/3D_Plants/Clovers_rbdjz/SM_Clovers_rbdjz_02` | StaticMesh | 0.14 | 1,121 | 0.79x0.79x0.16 | A30 | no | [foliage] |
| `/Game/Megascans/3D_Plants/Clovers_rbdjz/SM_Clovers_rbdjz_03` | StaticMesh | 0.11 | 893 | 0.75x0.72x0.15 | A30 | no | [foliage] |
| `/Game/Megascans/3D_Plants/DeadLeaves/MI_DeadLeaves_01` | MaterialInstance | 0.08 |  |  | E20 | no | [foliage]; sibling used by PWR |
| `/Game/Megascans/3D_Plants/DeadLeaves/SM_DeadLeaves_13` | StaticMesh | 0.17 | 3,066 | 1.69x1.73x0.07 | E20 | yes | [foliage] |
| `/Game/Megascans/3D_Plants/Downy_Willow_wknlfiuqx/Custom_Combinations/SM_Downy_Willow_Combined_A` | StaticMesh | 4.19 | 76,090 | 1.3x1.47x1.38 | A30 | no | [foliage] |
| `/Game/Megascans/3D_Plants/Downy_Willow_wknlfiuqx/Custom_Combinations/SM_Downy_Willow_Combined_B` | StaticMesh | 11.04 | 205,861 | 1.87x3.08x1.78 | A30 | no | [foliage] |
| `/Game/Megascans/3D_Plants/Downy_Willow_wknlfiuqx/Foliage/FT_Downy_Willow_wknlfiuqx_0_Var10_lod0` | FoliageType | 0.00 |  |  | C10 | no | [foliage] |
| `/Game/Megascans/3D_Plants/Downy_Willow_wknlfiuqx/Foliage/FT_Downy_Willow_wknlfiuqx_0_Var13_lod0` | FoliageType | 0.00 |  |  | C10 | no | [foliage] |
| `/Game/Megascans/3D_Plants/Downy_Willow_wknlfiuqx/Foliage/FT_Downy_Willow_wknlfiuqx_0_Var14_lod0` | FoliageType | 0.00 |  |  | B30 | no | [foliage] |
| `/Game/Megascans/3D_Plants/Downy_Willow_wknlfiuqx/Foliage/FT_Downy_Willow_wknlfiuqx_0_Var15_lod0` | FoliageType | 0.00 |  |  | C10 | no | [foliage] |
| `/Game/Megascans/3D_Plants/Downy_Willow_wknlfiuqx/Foliage/FT_Downy_Willow_wknlfiuqx_0_Var1_lod0_FoliageType_E20` | FoliageType | 0.00 |  |  | E20 | no | [foliage] |
| `/Game/Megascans/3D_Plants/Downy_Willow_wknlfiuqx/MI_Downy_Willow_wknlfiuqx_8K` | MaterialInstance | 0.03 |  |  | A30,B30,C10,E20,E30 | no | [foliage]; sibling used by PWR |
| `/Game/Megascans/3D_Plants/Downy_Willow_wknlfiuqx/MI_Downy_Willow_wknlfiuqx_8K_Wet` | MaterialInstance | 0.03 |  |  | C10 | no | wet variant [foliage]; sibling used by PWR |
| `/Game/Megascans/3D_Plants/Downy_Willow_wknlfiuqx/S_Downy_Willow_wknlfiuqx_0_Var10_lod0` | StaticMesh | 2.81 | 38,606 | 1.23x1.27x0.94 | B30,C10,E20 | yes | [foliage] |
| `/Game/Megascans/3D_Plants/Downy_Willow_wknlfiuqx/S_Downy_Willow_wknlfiuqx_0_Var11_lod0` | StaticMesh | 0.88 | 15,776 | 1.2x0.78x0.58 | C10,E20 | no | [foliage]; sibling used by PWR |
| `/Game/Megascans/3D_Plants/Downy_Willow_wknlfiuqx/S_Downy_Willow_wknlfiuqx_0_Var12_lod0` | StaticMesh | 6.13 | 100,216 | 2.02x1.97x1.15 | A30,B30,C10,E20 | no | [foliage]; sibling used by PWR |
| `/Game/Megascans/3D_Plants/Downy_Willow_wknlfiuqx/S_Downy_Willow_wknlfiuqx_0_Var13_lod0` | StaticMesh | 2.77 | 48,582 | 1.86x1.65x1.16 | A30,C10,E20 | no | [foliage]; sibling used by PWR |
| `/Game/Megascans/3D_Plants/Downy_Willow_wknlfiuqx/S_Downy_Willow_wknlfiuqx_0_Var14_lod0` | StaticMesh | 1.77 | 29,961 | 1.27x1.28x0.83 | B30,C10,E20 | no | [foliage]; sibling used by PWR |
| `/Game/Megascans/3D_Plants/Downy_Willow_wknlfiuqx/S_Downy_Willow_wknlfiuqx_0_Var15_lod0` | StaticMesh | 6.25 | 82,415 | 1.08x1.27x1.05 | A30,C10 | no | [foliage]; sibling used by PWR |
| `/Game/Megascans/3D_Plants/Downy_Willow_wknlfiuqx/S_Downy_Willow_wknlfiuqx_0_Var17_lod0` | StaticMesh | 3.01 | 39,236 | 1.25x0.92x1.59 | A30 | yes | [foliage] |
| `/Game/Megascans/3D_Plants/Downy_Willow_wknlfiuqx/S_Downy_Willow_wknlfiuqx_0_Var18_lod0` | StaticMesh | 3.98 | 49,698 | 1.14x1.03x1.18 | A30 | no | [foliage]; sibling used by PWR |
| `/Game/Megascans/3D_Plants/Downy_Willow_wknlfiuqx/S_Downy_Willow_wknlfiuqx_0_Var19_lod0` | StaticMesh | 4.05 | 45,022 | 1.03x0.87x0.63 | A30,C10 | no | [foliage]; sibling used by PWR |
| `/Game/Megascans/3D_Plants/Downy_Willow_wknlfiuqx/S_Downy_Willow_wknlfiuqx_0_Var1_lod0` | StaticMesh | 2.49 | 44,770 | 2.19x1.76x1.23 | A30,B30,C10,E20,E30 | no | [foliage]; sibling used by PWR |
| `/Game/Megascans/3D_Plants/Downy_Willow_wknlfiuqx/S_Downy_Willow_wknlfiuqx_0_Var3_lod0` | StaticMesh | 0.98 | 8,898 | 0.51x0.62x0.47 | C10 | no | [foliage]; sibling used by PWR |
| `/Game/Megascans/3D_Plants/Downy_Willow_wknlfiuqx/S_Downy_Willow_wknlfiuqx_0_Var8_lod0` | StaticMesh | 0.55 | 7,891 | 0.76x1.28x1.53 | B30 | no | [foliage]; sibling used by PWR |
| `/Game/Megascans/3D_Plants/Dwarf_Birch_xblnaabqx/Foliage/FT_Dwarf_Birch_xblnaabqx_Var10_lod0` | FoliageType | 0.00 |  |  | B30 | no | [foliage] |
| `/Game/Megascans/3D_Plants/Dwarf_Birch_xblnaabqx/Foliage/FT_Dwarf_Birch_xblnaabqx_Var13_lod0` | FoliageType | 0.00 |  |  | B30 | no | [foliage] |
| `/Game/Megascans/3D_Plants/Dwarf_Birch_xblnaabqx/Foliage/FT_Dwarf_Birch_xblnaabqx_Var14_lod0` | FoliageType | 0.00 |  |  | B30 | no | [foliage] |
| `/Game/Megascans/3D_Plants/Dwarf_Birch_xblnaabqx/Foliage/FT_Dwarf_Birch_xblnaabqx_Var6_lod0` | FoliageType | 0.00 |  |  | B30 | no | [foliage] |
| `/Game/Megascans/3D_Plants/Dwarf_Birch_xblnaabqx/MI_Dwarf_Birch_xblnaabqx_4K` | MaterialInstance | 0.03 |  |  | B30,C10 | no | [foliage]; sibling used by PWR |
| `/Game/Megascans/3D_Plants/Dwarf_Birch_xblnaabqx/MI_Dwarf_Birch_xblnaabqx_Billboard_4K` | MaterialInstance | 0.03 |  |  | B30,C10 | no | [foliage]; sibling used by PWR |
| `/Game/Megascans/3D_Plants/Dwarf_Birch_xblnaabqx/S_Dwarf_Birch_xblnaabqx_Var10_lod0` | StaticMesh | 1.07 | 22,193 | 1.78x1.49x1.32 | B30 | yes | [foliage] |
| `/Game/Megascans/3D_Plants/Dwarf_Birch_xblnaabqx/S_Dwarf_Birch_xblnaabqx_Var11_lod0` | StaticMesh | 1.29 | 19,881 | 1.64x1.73x0.99 | B30 | no | [foliage]; sibling used by PWR |
| `/Game/Megascans/3D_Plants/Dwarf_Birch_xblnaabqx/S_Dwarf_Birch_xblnaabqx_Var12_lod0` | StaticMesh | 0.72 | 12,444 | 1.65x1.4x0.92 | B30 | no | [foliage]; sibling used by PWR |
| `/Game/Megascans/3D_Plants/Dwarf_Birch_xblnaabqx/S_Dwarf_Birch_xblnaabqx_Var13_lod0` | StaticMesh | 0.90 | 14,714 | 1.11x1.11x0.85 | B30 | no | [foliage]; sibling used by PWR |
| `/Game/Megascans/3D_Plants/Dwarf_Birch_xblnaabqx/S_Dwarf_Birch_xblnaabqx_Var14_lod0` | StaticMesh | 2.49 | 37,982 | 0.78x0.63x1.04 | B30 | no | [foliage]; sibling used by PWR |
| `/Game/Megascans/3D_Plants/Dwarf_Birch_xblnaabqx/S_Dwarf_Birch_xblnaabqx_Var15_lod0` | StaticMesh | 0.53 | 7,602 | 0.86x0.83x0.79 | B30 | no | [foliage]; sibling used by PWR |
| `/Game/Megascans/3D_Plants/Dwarf_Birch_xblnaabqx/S_Dwarf_Birch_xblnaabqx_Var1_lod0` | StaticMesh | 0.97 | 16,293 | 1.69x1.65x0.72 | B30 | no | [foliage]; sibling used by PWR |
| `/Game/Megascans/3D_Plants/Dwarf_Birch_xblnaabqx/S_Dwarf_Birch_xblnaabqx_Var2_lod0` | StaticMesh | 0.53 | 4,258 | 0.25x0.16x0.27 | C10 | no | [foliage]; sibling used by PWR |
| `/Game/Megascans/3D_Plants/Dwarf_Birch_xblnaabqx/S_Dwarf_Birch_xblnaabqx_Var3_lod0` | StaticMesh | 0.52 | 6,516 | 0.9x0.82x0.89 | B30 | yes | [foliage] |
| `/Game/Megascans/3D_Plants/Dwarf_Birch_xblnaabqx/S_Dwarf_Birch_xblnaabqx_Var4_lod0` | StaticMesh | 0.39 | 5,586 | 0.87x0.5x1.33 | B30 | yes | [foliage] |
| `/Game/Megascans/3D_Plants/Dwarf_Birch_xblnaabqx/S_Dwarf_Birch_xblnaabqx_Var5_lod0` | StaticMesh | 0.18 | 2,084 | 0.37x0.35x0.86 | B30 | yes | [foliage] |
| `/Game/Megascans/3D_Plants/Dwarf_Birch_xblnaabqx/S_Dwarf_Birch_xblnaabqx_Var6_lod0` | StaticMesh | 21.87 | 601,329 | 1.97x1.81x1.59 | B30 | no | very dense: confirm Nanite before placing many [foliage]; sibling used by PWR |
| `/Game/Megascans/3D_Plants/Dwarf_Birch_xblnaabqx/S_Dwarf_Birch_xblnaabqx_Var7_lod0` | StaticMesh | 2.57 | 38,009 | 0.9x0.78x0.17 | B30 | no | [foliage]; sibling used by PWR |
| `/Game/Megascans/3D_Plants/Dwarf_Birch_xblnaabqx/S_Dwarf_Birch_xblnaabqx_Var8_lod0` | StaticMesh | 1.70 | 13,357 | 3.13x2.25x0.79 | B30 | no | [foliage]; sibling used by PWR |
| `/Game/Megascans/3D_Plants/Dwarf_Willow_xd3jbamja/MI_Dwarf_Willow_xd3jbamja_8K` | MaterialInstance | 0.00 |  |  | B30 | no | [foliage] |
| `/Game/Megascans/3D_Plants/Dwarf_Willow_xd3jbamja/S_Dwarf_Willow_xd3jbamja_0_Var5_lod0` | StaticMesh | 1.17 | 17,579 | 0.43x0.48x0.08 | B30 | no | [foliage] |
| `/Game/Megascans/3D_Plants/Elderberry/Custom_Combinations/SM_Elderberry_Bush_Combined_01_BBC2F015` | StaticMesh | 6.22 | 140,577 | 1.5x2.11x1.32 | A30 | no | [foliage] |
| `/Game/Megascans/3D_Plants/Elderberry/Custom_Combinations/SM_Elderberry_Bush_Combined_78DF3984` | StaticMesh | 4.10 | 87,377 | 2.51x1.92x1.33 | A30 | no | [foliage] |
| `/Game/Megascans/3D_Plants/Elderberry/Custom_Combinations/SM_Elderberry_Bush_Small_Combined_C` | StaticMesh | 2.25 | 53,541 | 1.27x1.55x0.96 | A30 | no | [foliage] |
| `/Game/Megascans/3D_Plants/Elderberry/MI_Elderberry_01` | MaterialInstance | 0.03 |  |  | A30,C10 | no | [foliage] |
| `/Game/Megascans/3D_Plants/Elderberry/MI_Elderberry_01_Wet` | MaterialInstance | 0.03 |  |  | C10 | no | wet variant [foliage] |
| `/Game/Megascans/3D_Plants/Elderberry/SM_Elderberry_01` | StaticMesh | 2.96 | 87,344 | 0.86x0.91x0.73 | A30 | no | [foliage] |
| `/Game/Megascans/3D_Plants/Elderberry/SM_Elderberry_02` | StaticMesh | 1.75 | 53,323 | 1.0x0.85x0.85 | A30 | no | [foliage] |
| `/Game/Megascans/3D_Plants/Elderberry/SM_Elderberry_03` | StaticMesh | 0.60 | 18,386 | 0.63x0.62x0.52 | A30 | no | [foliage] |
| `/Game/Megascans/3D_Plants/Elderberry/SM_Elderberry_04` | StaticMesh | 1.21 | 35,666 | 0.63x0.5x0.57 | A30 | no | [foliage] |
| `/Game/Megascans/3D_Plants/Elderberry/SM_Elderberry_05` | StaticMesh | 2.12 | 59,011 | 0.96x1.19x1.21 | A30 | no | [foliage] |
| `/Game/Megascans/3D_Plants/Elderberry/SM_Elderberry_06` | StaticMesh | 3.32 | 86,576 | 1.17x1.09x1.07 | A30 | no | [foliage] |
| `/Game/Megascans/3D_Plants/Elderberry/SM_Elderberry_07` | StaticMesh | 7.67 | 207,112 | 1.1x1.19x1.19 | A30 | no | [foliage] |
| `/Game/Megascans/3D_Plants/Elderberry/SM_Elderberry_08` | StaticMesh | 13.13 | 365,692 | 2.3x2.24x1.49 | A30 | no | [foliage] |
| `/Game/Megascans/3D_Plants/Elderberry/SM_Elderberry_09` | StaticMesh | 5.22 | 121,660 | 2.04x1.95x1.65 | A30 | no | [foliage] |
| `/Game/Megascans/3D_Plants/Elderberry/SM_Elderberry_10` | StaticMesh | 1.82 | 55,103 | 1.06x1.25x0.92 | A30 | no | [foliage] |
| `/Game/Megascans/3D_Plants/Elderberry/SM_Elderberry_11` | StaticMesh | 1.60 | 48,647 | 1.02x0.98x0.9 | A30 | no | [foliage] |
| `/Game/Megascans/3D_Plants/Elderberry/SM_Elderberry_12` | StaticMesh | 2.47 | 76,466 | 1.0x1.04x0.85 | A30,C10 | no | [foliage] |
| `/Game/Megascans/3D_Plants/Elderberry/SM_Elderberry_13` | StaticMesh | 1.11 | 34,013 | 0.73x1.18x0.69 | A30 | no | [foliage] |
| `/Game/Megascans/3D_Plants/Elderberry_wfzobb2ia/Foliage/S_Elderberry_wfzobb2ia_Var10_lod0_E20` | FoliageType | 0.00 |  |  | E20 | no | [foliage] |
| `/Game/Megascans/3D_Plants/Elderberry_wfzobb2ia/Foliage/S_Elderberry_wfzobb2ia_Var3_lod0_E20` | FoliageType | 0.00 |  |  | E20 | no | [foliage] |
| `/Game/Megascans/3D_Plants/Elderberry_wfzobb2ia/Foliage/S_Elderberry_wfzobb2ia_Var5_lod0_E20` | FoliageType | 0.00 |  |  | E20 | no | [foliage] |
| `/Game/Megascans/3D_Plants/Elderberry_wfzobb2ia/MI_Elderberry_wfzobb2ia_4K` | MaterialInstance | 0.05 |  |  | E20 | no | [foliage]; sibling used by PWR |
| `/Game/Megascans/3D_Plants/Elderberry_wfzobb2ia/MI_Elderberry_wfzobb2ia_Billboard_4K` | MaterialInstance | 0.00 |  |  | E20 | no | [foliage]; sibling used by PWR |
| `/Game/Megascans/3D_Plants/Elderberry_wfzobb2ia/S_Elderberry_wfzobb2ia_Var10_lod0` | StaticMesh | 0.57 | 13,690 | 0.86x0.9x0.73 | E20 | no | [foliage]; sibling used by PWR |
| `/Game/Megascans/3D_Plants/Elderberry_wfzobb2ia/S_Elderberry_wfzobb2ia_Var3_lod0` | StaticMesh | 1.17 | 28,508 | 1.1x1.2x1.19 | E20 | listed | [foliage] |
| `/Game/Megascans/3D_Plants/Elderberry_wfzobb2ia/S_Elderberry_wfzobb2ia_Var5_lod0` | StaticMesh | 1.57 | 39,023 | 2.06x1.95x1.65 | E20 | no | [foliage]; sibling used by PWR |
| `/Game/Megascans/3D_Plants/EuropeanHornbeam/Geometry/SimpleWind/SM_EuropeanHornbeam_Sapling_08` | StaticMesh | 1.12 | 11,174 | 1.14x1.13x0.98 | C10 | no | [foliage] |
| `/Game/Megascans/3D_Plants/EuropeanHornbeam/Materials/SimpleWind/MI_EuropeanHornbeam_TwoSided` | MaterialInstance | 0.05 |  |  | C10 | no | [foliage] |
| `/Game/Megascans/3D_Plants/Fern/MI_Fern_01` | MaterialInstance | 0.05 |  |  | A30 | no | [foliage]; sibling used by PWR |
| `/Game/Megascans/3D_Plants/Fern/SM_Fern_01` | StaticMesh | 0.06 | 1,199 | 1.55x1.88x1.03 | A30 | yes | [foliage] |
| `/Game/Megascans/3D_Plants/Fern/SM_Fern_02` | StaticMesh | 0.10 | 847 | 1.67x1.75x0.95 | A30 | no | [foliage]; sibling used by PWR |
| `/Game/Megascans/3D_Plants/Fern/SM_Fern_03` | StaticMesh | 0.08 | 902 | 1.49x1.38x0.63 | A30 | no | [foliage]; sibling used by PWR |
| `/Game/Megascans/3D_Plants/Fern/SM_Fern_04` | StaticMesh | 0.05 | 1,031 | 1.79x1.65x0.73 | A30 | no | [foliage]; sibling used by PWR |
| `/Game/Megascans/3D_Plants/Fern/SM_Fern_05` | StaticMesh | 0.07 | 1,420 | 2.02x1.87x0.91 | A30 | no | [foliage]; sibling used by PWR |
| `/Game/Megascans/3D_Plants/Fern/SM_Fern_06` | StaticMesh | 0.06 | 482 | 1.57x1.59x0.66 | A30 | no | [foliage]; sibling used by PWR |
| `/Game/Megascans/3D_Plants/Fern_rmAsg/MI_Fern_rmAsg_8K` | MaterialInstance | 0.00 |  |  | E20 | no | [foliage] |
| `/Game/Megascans/3D_Plants/Fern_rmAsg/S_Fern_rmAsg_0_Var5_lod0` | StaticMesh | 0.07 | 1,420 | 2.02x1.87x0.91 | E20 | no | [foliage] |
| `/Game/Megascans/3D_Plants/Greater_Burdock_xh5pdgiqx/MI_Greater_Burdock_xh5pdgiqx_4K` | MaterialInstance | 0.00 |  |  | C10 | no | [foliage]; sibling used by PWR |
| `/Game/Megascans/3D_Plants/Greater_Burdock_xh5pdgiqx/MI_Greater_Burdock_xh5pdgiqx_Billboard_4K` | MaterialInstance | 0.00 |  |  | C10 | no | [foliage]; sibling used by PWR |
| `/Game/Megascans/3D_Plants/Greater_Burdock_xh5pdgiqx/M_MS_HaloTreeWind_reater_Burdock_xh5pdgiqx` | MaterialInstance | 0.03 |  |  | C10 | no | [foliage]; sibling used by PWR |
| `/Game/Megascans/3D_Plants/Greater_Burdock_xh5pdgiqx/S_Greater_Burdock_xh5pdgiqx_Var1_lod0` | StaticMesh | 5.33 | 114,070 | 0.83x0.82x1.1 | C10 | yes | [foliage] |
| `/Game/Megascans/3D_Plants/Greater_Burdock_xh5pdgiqx/S_Greater_Burdock_xh5pdgiqx_Var2_lod0` | StaticMesh | 3.28 | 70,593 | 0.76x0.81x0.94 | C10 | no | [foliage]; sibling used by PWR |
| `/Game/Megascans/3D_Plants/Greater_Burdock_xh5pdgiqx/S_Greater_Burdock_xh5pdgiqx_Var3_lod0` | StaticMesh | 0.44 | 5,746 | 0.71x0.8x0.59 | C10 | no | [foliage]; sibling used by PWR |
| `/Game/Megascans/3D_Plants/Greater_Burdock_xh5pdgiqx/S_Greater_Burdock_xh5pdgiqx_Var4_lod0` | StaticMesh | 0.21 | 2,041 | 0.39x0.43x0.16 | C10 | no | [foliage]; sibling used by PWR |
| `/Game/Megascans/3D_Plants/Ivy/MI_Ivy_01` | MaterialInstance | 0.03 |  |  | A30,B30 | no | [foliage] |
| `/Game/Megascans/3D_Plants/Ivy/SM_Ivy_12` | StaticMesh | 6.72 | 129,813 | 0.77x0.6x2.14 | B30 | no | [foliage] |
| `/Game/Megascans/3D_Plants/Ivy/SM_Ivy_15` | StaticMesh | 1.27 | 16,900 | 0.26x0.22x1.32 | B30 | no | [foliage] |
| `/Game/Megascans/3D_Plants/Ivy/SM_Ivy_16` | StaticMesh | 1.53 | 24,534 | 0.68x0.34x1.45 | A30,B30 | no | [foliage] |
| `/Game/Megascans/3D_Plants/Ivy/SM_Ivy_16_FoliageType` | FoliageType | 0.00 |  |  | B30 | no | [foliage] |
| `/Game/Megascans/3D_Plants/Ivy/SM_Ivy_20` | StaticMesh | 1.60 | 23,868 | 1.06x0.39x1.07 | A30,B30 | no | [foliage] |
| `/Game/Megascans/3D_Plants/Ivy/SM_Ivy_23` | StaticMesh | 0.63 | 8,765 | 0.23x0.29x2.26 | A30,B30 | no | [foliage] |
| `/Game/Megascans/3D_Plants/Lady_Fern_wdvlditia/MIP_Lady_Ferns` | MaterialInstance | 0.03 |  |  | A30 | no | [foliage]; sibling used by PWR |
| `/Game/Megascans/3D_Plants/Lady_Fern_wdvlditia/MI_Lady_Fern_wdvlditia_01` | MaterialInstance | 0.05 |  |  | A30 | no | [foliage]; sibling used by PWR |
| `/Game/Megascans/3D_Plants/Lady_Fern_wdvlditia/SM_Lady_Fern_wdvlditia_01` | StaticMesh | 0.98 | 13,147 | 0.95x0.98x0.5 | A30 | yes | [foliage] |
| `/Game/Megascans/3D_Plants/Lady_Fern_wdvlditia/SM_Lady_Fern_wdvlditia_01_Traced` | StaticMesh | 2.44 | 48,301 | 0.94x0.97x0.5 | A30 | no | [foliage]; sibling used by PWR |
| `/Game/Megascans/3D_Plants/Lady_Fern_wdvlditia/SM_Lady_Fern_wdvlditia_03` | StaticMesh | 0.69 | 9,753 | 0.67x0.67x0.42 | A30 | no | [foliage]; sibling used by PWR |
| `/Game/Megascans/3D_Plants/Lady_Fern_wdvlditia/SM_Lady_Fern_wdvlditia_10` | StaticMesh | 0.18 | 1,687 | 0.45x0.33x0.21 | A30 | no | [foliage]; sibling used by PWR |
| `/Game/Megascans/3D_Plants/Leafy_Weeds_rbcuh/FT_Leafy_Weeds_rbcuh_01` | FoliageType | 0.00 |  |  | A30 | no | [foliage] |
| `/Game/Megascans/3D_Plants/Leafy_Weeds_rbcuh/FT_Leafy_Weeds_rbcuh_02` | FoliageType | 0.00 |  |  | A30 | no | [foliage] |
| `/Game/Megascans/3D_Plants/Leafy_Weeds_rbcuh/MI_Leafy_Weeds_rbcuh_01` | MaterialInstance | 0.03 |  |  | A30 | no | [foliage] |
| `/Game/Megascans/3D_Plants/Leafy_Weeds_rbcuh/SM_Leafy_Weeds_rbcuh_01` | StaticMesh | 0.08 | 495 | 0.79x0.83x0.16 | A30 | no | [foliage] |
| `/Game/Megascans/3D_Plants/Leafy_Weeds_rbcuh/SM_Leafy_Weeds_rbcuh_01_Traced` | StaticMesh | 0.38 | 14,018 | 0.79x0.83x0.15 | A30 | no | [foliage] |
| `/Game/Megascans/3D_Plants/Leafy_Weeds_rbcuh/SM_Leafy_Weeds_rbcuh_02` | StaticMesh | 0.05 | 210 | 0.51x0.52x0.13 | A30 | no | [foliage] |
| `/Game/Megascans/3D_Plants/Myricaria_tfbldaor/MI_Myricaria_tfbldaor_4K` | MaterialInstance | 0.00 |  |  |  | no | [foliage]; sibling used by PWR |
| `/Game/Megascans/3D_Plants/Myricaria_tfbldaor/MI_Myricaria_tfbldaor_Billboard_4K` | MaterialInstance | 0.00 |  |  |  | no | [foliage]; sibling used by PWR |
| `/Game/Megascans/3D_Plants/Myricaria_tfbldaor/S_Myricaria_tfbldaor_Var1_lod0` | StaticMesh | 0.42 | 6,937 | 0.64x0.52x1.02 |  | yes | [foliage] |
| `/Game/Megascans/3D_Plants/Myricaria_tfbldaor/S_Myricaria_tfbldaor_Var2_lod0` | StaticMesh | 0.33 | 4,825 | 0.51x0.45x0.95 |  | no | [foliage]; sibling used by PWR |
| `/Game/Megascans/3D_Plants/Myricaria_tfbldaor/S_Myricaria_tfbldaor_Var3_lod0` | StaticMesh | 0.23 | 3,466 | 0.46x0.28x0.76 |  | no | [foliage]; sibling used by PWR |
| `/Game/Megascans/3D_Plants/Myricaria_tfbldaor/S_Myricaria_tfbldaor_Var4_lod0` | StaticMesh | 0.17 | 2,382 | 0.27x0.29x0.53 |  | no | [foliage]; sibling used by PWR |
| `/Game/Megascans/3D_Plants/Myricaria_tfbldaor/S_Myricaria_tfbldaor_Var5_lod0` | StaticMesh | 0.07 | 476 | 0.16x0.14x0.33 |  | no | [foliage]; sibling used by PWR |
| `/Game/Megascans/3D_Plants/Periwinkle_tfclbger/MI_Periwinkle_tfclbger_4K` | MaterialInstance | 0.03 |  |  | A30 | no | [foliage]; sibling used by PWR |
| `/Game/Megascans/3D_Plants/Periwinkle_tfclbger/SM_Periwinkle_Combined_A30` | StaticMesh | 1.08 | 36,354 | 0.54x0.64x0.92 | A30 | yes | [foliage] |
| `/Game/Megascans/3D_Plants/Prickly_Lettuce_tcfobfvr/Foliage/FT_Prickly_Lettuce_tcfobfvr_Var1_lod0` | FoliageType | 0.00 |  |  | B30 | no | [foliage] |
| `/Game/Megascans/3D_Plants/Prickly_Lettuce_tcfobfvr/Foliage/FT_Prickly_Lettuce_tcfobfvr_Var2_lod0` | FoliageType | 0.00 |  |  | B30 | no | [foliage] |
| `/Game/Megascans/3D_Plants/Prickly_Lettuce_tcfobfvr/MI_Prickly_Lettuce_tcfobfvr_4K` | MaterialInstance | 0.05 |  |  | B30 | no | [foliage]; sibling used by PWR |
| `/Game/Megascans/3D_Plants/Prickly_Lettuce_tcfobfvr/MI_Prickly_Lettuce_tcfobfvr_Billboard_4K` | MaterialInstance | 0.00 |  |  | B30 | no | [foliage]; sibling used by PWR |
| `/Game/Megascans/3D_Plants/Prickly_Lettuce_tcfobfvr/S_Prickly_Lettuce_tcfobfvr_Var1_lod0` | StaticMesh | 0.66 | 6,289 | 1.06x1.07x2.37 | B30 | yes | [foliage] |
| `/Game/Megascans/3D_Plants/Prickly_Lettuce_tcfobfvr/S_Prickly_Lettuce_tcfobfvr_Var2_lod0` | StaticMesh | 0.23 | 1,911 | 0.5x0.38x1.78 | B30 | yes | [foliage] |
| `/Game/Megascans/3D_Plants/Small_Balsam_xefmcgrqx/FT_Small_Balsam_xefmcgrqx_03` | FoliageType | 0.00 |  |  | A30 | no | [foliage]; sibling used by PWR |
| `/Game/Megascans/3D_Plants/Small_Balsam_xefmcgrqx/FT_Small_Balsam_xefmcgrqx_04` | FoliageType | 0.00 |  |  | A30 | no | [foliage]; sibling used by PWR |
| `/Game/Megascans/3D_Plants/Small_Balsam_xefmcgrqx/FT_Small_Balsam_xefmcgrqx_07` | FoliageType | 0.00 |  |  | A30 | no | [foliage]; sibling used by PWR |
| `/Game/Megascans/3D_Plants/Small_Balsam_xefmcgrqx/Foliage/FT_Small_Balsam_xefmcgrqx_06_FoliageType_E20` | FoliageType | 0.00 |  |  | E20 | no | [foliage] |
| `/Game/Megascans/3D_Plants/Small_Balsam_xefmcgrqx/Foliage/FT_Small_Balsam_xefmcgrqx_07_FoliageType_E20` | FoliageType | 0.00 |  |  | E20 | no | [foliage] |
| `/Game/Megascans/3D_Plants/Small_Balsam_xefmcgrqx/Foliage/FT_Small_Balsam_xefmcgrqx_08_FoliageType_E20` | FoliageType | 0.00 |  |  | E20 | no | [foliage] |
| `/Game/Megascans/3D_Plants/Small_Balsam_xefmcgrqx/MI_Small_Balsam_xefmcgrqx_01` | MaterialInstance | 0.03 |  |  | A30,E20 | no | [foliage]; sibling used by PWR |
| `/Game/Megascans/3D_Plants/Small_Balsam_xefmcgrqx/SM_Small_Balsam_xefmcgrqx_03` | StaticMesh | 0.29 | 4,618 | 0.49x0.47x0.45 | A30 | yes | [foliage] |
| `/Game/Megascans/3D_Plants/Small_Balsam_xefmcgrqx/SM_Small_Balsam_xefmcgrqx_04` | StaticMesh | 0.59 | 11,021 | 0.58x0.53x0.63 | A30 | no | [foliage]; sibling used by PWR |
| `/Game/Megascans/3D_Plants/Small_Balsam_xefmcgrqx/SM_Small_Balsam_xefmcgrqx_06` | StaticMesh | 0.26 | 6,736 | 0.57x0.61x0.41 | E20 | yes | [foliage] |
| `/Game/Megascans/3D_Plants/Small_Balsam_xefmcgrqx/SM_Small_Balsam_xefmcgrqx_07` | StaticMesh | 0.53 | 14,051 | 0.73x0.77x0.52 | A30,E20 | no | [foliage]; sibling used by PWR |
| `/Game/Megascans/3D_Plants/Small_Balsam_xefmcgrqx/SM_Small_Balsam_xefmcgrqx_08` | StaticMesh | 0.38 | 9,909 | 0.68x0.6x0.31 | E20 | no | [foliage]; sibling used by PWR |
| `/Game/Megascans/3D_Plants/YellowArchangel/Foliage/FT_YellowArchangel_04_FoliageType` | FoliageType | 0.00 |  |  | E20 | no | [foliage] |
| `/Game/Megascans/3D_Plants/YellowArchangel/Foliage/FT_YellowArchangel_08_FoliageType` | FoliageType | 0.00 |  |  | C10 | no | [foliage] |
| `/Game/Megascans/3D_Plants/YellowArchangel/Foliage/FT_YellowArchangel_09_FoliageType` | FoliageType | 0.00 |  |  | C10 | no | [foliage] |
| `/Game/Megascans/3D_Plants/YellowArchangel/Foliage/FT_YellowArchangel_Alien_FoliageType` | FoliageType | 0.00 |  |  | E20 | no | off-setting (tropical/alien/marine) [foliage,setting] |
| `/Game/Megascans/3D_Plants/YellowArchangel/MI_YellowArchangel_Biomes_A_HS` | MaterialInstance | 0.05 |  |  | C10,E20 | no | [foliage] |
| `/Game/Megascans/3D_Plants/YellowArchangel/SM_YellowArchangel_03` | StaticMesh | 0.11 | 2,135 | 0.1x0.11x0.04 | E20 | no | [foliage] |
| `/Game/Megascans/3D_Plants/YellowArchangel/SM_YellowArchangel_04` | StaticMesh | 0.40 | 8,810 | 0.2x0.2x0.11 | C10,E20 | no | [foliage] |
| `/Game/Megascans/3D_Plants/YellowArchangel/SM_YellowArchangel_06` | StaticMesh | 0.08 | 1,573 | 0.09x0.09x0.08 | E20 | no | [foliage] |
| `/Game/Megascans/3D_Plants/YellowArchangel/SM_YellowArchangel_08` | StaticMesh | 0.37 | 6,965 | 0.2x0.19x0.11 | C10,E20 | no | [foliage] |
| `/Game/Megascans/3D_Plants/YellowArchangel/SM_YellowArchangel_09` | StaticMesh | 0.24 | 4,238 | 0.14x0.14x0.1 | C10 | no | [foliage] |
| `/Game/Megascans/3D_Plants/Yellow_Rabbitbrush_vdtlcbjia/Foliage/FT_Yellow_Rabbitbrush_vdtlcbjia_0_Var7_lod0` | FoliageType | 0.00 |  |  | B30 | no | [foliage] |
| `/Game/Megascans/3D_Plants/Yellow_Rabbitbrush_vdtlcbjia/Foliage/FT_Yellow_Rabbitbrush_vdtlcbjia_0_Var9_lod0` | FoliageType | 0.00 |  |  | A50,B30 | no | [foliage] |
| `/Game/Megascans/3D_Plants/Yellow_Rabbitbrush_vdtlcbjia/MI_Yellow_Rabbitbrush_vdtlcbjia_8K` | MaterialInstance | 0.00 |  |  | A50,B30 | no | [foliage]; sibling used by PWR |
| `/Game/Megascans/3D_Plants/Yellow_Rabbitbrush_vdtlcbjia/SM_Yellow_Rabbitbrush_vdtlcbjia_0_Var9_lod0_Traced` | StaticMesh | 0.50 | 15,883 | 0.59x0.72x0.59 | A50,B30 | no | [foliage]; sibling used by PWR |
| `/Game/Megascans/3D_Plants/Yellow_Rabbitbrush_vdtlcbjia/S_Yellow_Rabbitbrush_vdtlcbjia_0_Var10_lod0` | StaticMesh | 0.23 | 2,420 | 1.64x1.65x1.67 |  | yes | [foliage] |
| `/Game/Megascans/3D_Plants/Yellow_Rabbitbrush_vdtlcbjia/S_Yellow_Rabbitbrush_vdtlcbjia_0_Var11_lod0` | StaticMesh | 0.22 | 2,296 | 0.49x0.53x0.38 |  | no | [foliage]; sibling used by PWR |
| `/Game/Megascans/3D_Plants/Yellow_Rabbitbrush_vdtlcbjia/S_Yellow_Rabbitbrush_vdtlcbjia_0_Var1_lod0` | StaticMesh | 1.14 | 10,798 | 2.38x2.18x1.92 |  | yes | [foliage] |
| `/Game/Megascans/3D_Plants/Yellow_Rabbitbrush_vdtlcbjia/S_Yellow_Rabbitbrush_vdtlcbjia_0_Var7_lod0` | StaticMesh | 0.82 | 8,430 | 0.88x0.75x0.75 |  | no | [foliage]; sibling used by PWR |
| `/Game/Megascans/3D_Plants/Yellow_Rabbitbrush_vdtlcbjia/S_Yellow_Rabbitbrush_vdtlcbjia_0_Var9_lod0` | StaticMesh | 0.24 | 5,450 | 0.64x0.74x0.61 |  | no | [foliage]; sibling used by PWR |

*Group note:* Megascans plants; many already in PWR's meadow_life/forest-floor palettes (see 'used')

## 5. Mountains, cliffs and sky (690)

### Frozen/glacial ice (Env/Bio/Frozen) (26)

*Where on PWR:* Snowfields and ice on the high ring mesh

| path | kind | MB | verts | bounds m | levels | PWR | note |
|---|---|---|---|---|---|---|---|
| `/Game/Env/Bio/Frozen/Glacial/+Materials/MI_Frozen_Snowpile_Med` | MaterialInstance | 0.00 |  |  | B40,C45 | no | snow variant |
| `/Game/Env/Bio/Frozen/Glacial/+Materials/MI_Glacier_Snow` | MaterialInstance | 0.14 |  |  | B40,C45 | no | snow variant |
| `/Game/Env/Bio/Frozen/Glacial/+Materials/MI_Icecave` | MaterialInstance | 0.14 |  |  | B40,C45 | no |  |
| `/Game/Env/Bio/Frozen/Glacial/+Materials/MI_Icicle_NoSnow` | MaterialInstance | 0.14 |  |  | B40,C45 | no | snow-free variant |
| `/Game/Env/Bio/Frozen/Glacial/+Materials/MI_Icicle_Snow` | MaterialInstance | 0.14 |  |  | B40,C45 | no | snow variant |
| `/Game/Env/Bio/Frozen/Glacial/+Materials/MM_Frozen_Glacial_Icewatefall` | Material | 0.03 |  |  | B40,C45 | no |  |
| `/Game/Env/Bio/Frozen/Glacial/+Materials/MM_Frozen_Snowpile_Med` | Material | 0.01 |  |  | B40,C45 | no | snow variant |
| `/Game/Env/Bio/Frozen/Glacial/Frozen_Glacial_Icewatefall_A/SM_Frozen_Glacial_Icewatefall_A` | StaticMesh | 4.59 | 137,430 | 57.56x42.52x90.18 | B40,C45 | no |  |
| `/Game/Env/Bio/Frozen/Glacial/Frozen_Glacial_Icewatefall_B/SM_Frozen_Glacial_Icewatefall_B` | StaticMesh | 2.27 | 52,683 | 43.94x51.68x29.63 | B40,C45 | no |  |
| `/Game/Env/Bio/Frozen/Glacial/Frozen_Glacial_Icewatefall_C/SM_Frozen_Glacial_Icewatefall_C` | StaticMesh | 3.33 | 101,571 | 51.27x43.82x30.08 | B40,C45 | no |  |
| `/Game/Env/Bio/Frozen/Glacial/Frozen_Glacial_Icewatefall_D/SM_Frozen_Glacial_Icewatefall_D` | StaticMesh | 5.12 | 151,778 | 6.88x1.77x4.43 | B40,C45 | no |  |
| `/Game/Env/Bio/Frozen/Glacial/Frozen_Glacial_Icewatefall_G/SM_Frozen_Glacial_Icewatefall_G` | StaticMesh | 21.23 | 707,989 | 3.62x1.95x5.04 | B40,C45 | no | very dense: confirm Nanite before placing many |
| `/Game/Env/Bio/Frozen/Glacial/Frozen_Glacial_Icewatefall_G/SM_Frozen_Glacial_Icewatefall_G_Cut` | StaticMesh | 2.40 | 64,882 | 2.8x1.37x4.29 | B40,C45 | no |  |
| `/Game/Env/Bio/Frozen/Glacial/Frozen_Glacial_Icewatefall_H/SM_Frozen_Glacial_Icewatefall_H` | StaticMesh | 6.69 | 194,530 | 5.0x2.47x4.1 | B40,C45 | no | packed AO/roughness/height map |
| `/Game/Env/Bio/Frozen/Glacial/Frozen_Glacial_Icewatefall_H/SM_Frozen_Glacial_Icewatefall_H_Cut` | StaticMesh | 6.87 | 198,616 | 4.71x1.86x3.41 | B40,C45 | no | packed AO/roughness/height map |
| `/Game/Env/Bio/Frozen/Glacial/Frozen_Glacial_Icicles_A/SM_Frozen_Glacial_Icicles_A` | StaticMesh | 0.73 | 22,533 | 1.7x1.74x18.67 | B40,C45 | no |  |
| `/Game/Env/Bio/Frozen/Glacial/Frozen_Glacial_Icicles_B/SM_Frozen_Glacial_Icicles_B` | StaticMesh | 0.72 | 21,555 | 4.5x2.84x23.8 | B40,C45 | no |  |
| `/Game/Env/Bio/Frozen/Glacial/Frozen_Glacial_Icicles_C/SM_Frozen_Glacial_Icicles_C` | StaticMesh | 1.67 | 42,801 | 9.46x5.45x24.1 | B40,C45 | no |  |
| `/Game/Env/Bio/Frozen/Glacial/Frozen_Glacial_Icicles_D/PLAY_SM_Frozen_Glacial_Icicles_D_CollisionMesh` | StaticMesh | 0.14 |  |  | B40 | no | collision proxy mesh |
| `/Game/Env/Bio/Frozen/Glacial/Frozen_Glacial_Icicles_D/SM_Frozen_Glacial_Icicles_D` | StaticMesh | 1.59 | 47,010 | 10.6x2.89x30.8 | B40,C45 | no |  |
| `/Game/Env/Bio/Frozen/Glacial/Frozen_Glacial_Icicles_E/SM_Frozen_Glacial_Icicles_E` | StaticMesh | 1.71 | 42,496 | 6.64x4.57x27.82 | B40,C45 | no |  |
| `/Game/Env/Bio/Frozen/Glacial/Frozen_Glacial_Icicles_F/SM_Frozen_Glacial_Icicles_F` | StaticMesh | 1.25 | 37,639 | 3.9x2.99x14.82 | B40,C45 | no |  |
| `/Game/Env/Bio/Frozen/Glacial/Frozen_Glacial_Icicles_G/SM_Frozen_Glacial_Icicles_G` | StaticMesh | 1.41 | 43,864 | 4.04x2.35x18.37 | B40,C45 | no |  |
| `/Game/Env/Bio/Frozen/Glacial/Frozen_Glacial_Lake_A/SM_Frozen_Glacial_Lake_A` | StaticMesh | 0.06 | 204 | 104.17x114.36x0.0 | B40,C45 | no |  |
| `/Game/Env/Bio/Frozen/Glacial/Frozen_Snowpile_Med_A/SM_Frozen_Snowpile_Med_A` | StaticMesh | 2.97 | 71,818 | 2.28x1.62x0.35 | B40,C45 | no | snow variant |
| `/Game/Env/Bio/Frozen/Glacial/Frozen_Snowpile_Med_B/SM_Frozen_Snowpile_Med_B` | StaticMesh | 2.33 | 54,232 | 4.09x1.85x0.89 | B40,C45 | no | snow variant |

*Group note:* Glacial ice meshes and materials

### Alpine scree (Env/Bio/Rock/Scree, PNW scree, ScreeSpline) (33)

*Where on PWR:* Talus fans under every cliff, scree slopes on the mountain flanks

| path | kind | MB | verts | bounds m | levels | PWR | note |
|---|---|---|---|---|---|---|---|
| `/Game/Env/Bio/PCG/BP_Assembly` | Blueprint | 0.01 |  |  | A30,A50,B30,B40,C10,C45 | no |  |
| `/Game/Env/Bio/PCG/BP_ScatterVolume` | Blueprint | 0.01 |  |  | A30,B30,B40,C45 | no |  |
| `/Game/Env/Bio/PCG/BP_TreeAssembly_Base` | Blueprint | 0.00 |  |  | A30,A50,B30,B40,C10,C45 | no |  |
| `/Game/Env/Bio/PCG/SM_BlankMarker` | StaticMesh | 0.01 | 108 | 0.21x0.88x2.82 | A30,A50,B30,B40,C10,C45 | no |  |
| `/Game/Env/Bio/PCG/ScreeSpline/BP_ScatterSpline` | Blueprint | 0.00 |  |  | A30,E30 | no |  |
| `/Game/Env/Bio/PNW/+PLA/DAPCG_Scree_Mass_a` | PCGDataAsset | 0.07 |  |  |  | no |  |
| `/Game/Env/Bio/PNW/+PLA/PLA_Scree_Mass_a` | LevelInstance | 0.00 |  |  |  | no |  |
| `/Game/Env/Bio/PNW/Meshes/SM_Crab_Grass/MIP_Decorator_Grass_Crab` | MaterialInstance | 0.04 |  |  | A30,C10,E20,E30 | no | off-setting (tropical/alien/marine) [setting]; sibling used by PWR |
| `/Game/Env/Bio/PNW/Meshes/SM_Crab_Grass/SM_Crab_Grass_Clump_A` | StaticMesh | 1.27 | 26,076 | 2.25x2.35x0.37 | A30,E20,E30 | no | off-setting (tropical/alien/marine) [setting]; sibling used by PWR |
| `/Game/Env/Bio/PNW/Meshes/SM_Crab_Grass/SM_Crab_Grass_Clump_B` | StaticMesh | 0.66 | 13,678 | 1.67x1.7x0.35 | A30,C10,E20,E30 | yes | off-setting (tropical/alien/marine) [setting] |
| `/Game/Env/Bio/PNW/Meshes/SM_Crab_Grass/SM_Crab_Grass_Clump_C` | StaticMesh | 1.24 | 12,143 | 1.62x1.7x0.37 | A30 | no | off-setting (tropical/alien/marine) [setting]; sibling used by PWR |
| `/Game/Env/Bio/PNW/Meshes/SM_Crab_Grass/SM_Crab_Grass_Clump_D` | StaticMesh | 1.75 | 25,873 | 2.79x2.79x0.69 | A30 | no | off-setting (tropical/alien/marine) [setting]; sibling used by PWR |
| `/Game/Env/Bio/PNW/Meshes/SM_Scree_Alpine_A/SM_scree_alpine_a` | StaticMesh | 0.65 | 16,928 | 7.65x6.26x2.95 | A30 | no |  |
| `/Game/Env/Bio/PNW/Meshes/SM_Scree_Alpine_B/SM_scree_alpine_b` | StaticMesh | 0.62 | 15,970 | 7.01x6.35x3.66 | A30 | no |  |
| `/Game/Env/Bio/PNW/Meshes/SM_Scree_Alpine_C/SM_scree_alpine_c` | StaticMesh | 0.74 | 16,202 | 7.66x6.75x2.96 | A30 | no |  |
| `/Game/Env/Bio/Rock/Scree/Materials/MIP_Rock_Glacial_Scree_NoSnow` | MaterialInstance | 0.19 |  |  | B40,C45 | no | snow-free variant |
| `/Game/Env/Bio/Rock/Scree/Materials/MIP_Rock_Glacial_Scree_Snow` | MaterialInstance | 0.09 |  |  | B40,C45 | no | snow variant |
| `/Game/Env/Bio/Rock/Scree/Scree_Rock_A/SM_Scree_Rock_01` | StaticMesh | 0.75 | 27,458 | 0.45x0.53x0.3 | B40,C45 | no |  |
| `/Game/Env/Bio/Rock/Scree/Scree_Rock_A/SM_Scree_Rock_NoSnow_02` | StaticMesh | 0.75 | 27,458 | 0.45x0.53x0.3 | B40,C45 | no | snow-free variant |
| `/Game/Env/Bio/Rock/Scree/Scree_Rock_B/SM_Scree_Rock_02` | StaticMesh | 0.68 | 24,042 | 0.33x0.45x0.17 | B40,C45 | no |  |
| `/Game/Env/Bio/Rock/Scree/Scree_Rock_B/SM_Scree_Rock_NoSnow_02` | StaticMesh | 0.68 | 24,042 | 0.33x0.45x0.17 | B40,C45 | no | snow-free variant |
| `/Game/Env/Bio/Rock/Scree/Scree_Rock_C/SM_Scree_Rock_03` | StaticMesh | 0.78 | 29,991 | 0.19x0.18x0.1 | B40,C45 | no |  |
| `/Game/Env/Bio/Rock/Scree/Scree_Rock_C/SM_Scree_Rock_NoSnow_03` | StaticMesh | 0.78 | 29,991 | 0.19x0.18x0.1 | B40,C45 | no | snow-free variant |
| `/Game/Env/Bio/Rock/Scree/Scree_Rock_Clump_A/+Materials/MI_Scree_Rock_Clump_A` | MaterialInstance | 0.05 |  |  | A30 | no |  |
| `/Game/Env/Bio/Rock/Scree/Scree_Rock_Clump_A/SM_Scree_Rock_Clump_A` | StaticMesh | 0.22 | 2,627 | 1.94x2.15x0.28 | A30 | no |  |
| `/Game/Env/Bio/Rock/Scree/Scree_Rock_Clump_B/SM_Scree_Rock_Clump_B` | StaticMesh | 0.26 | 4,684 | 3.64x2.05x0.46 | A30 | no |  |

Textures: `/Game/Env/Bio/PNW/Gen/+Materials/T_PNW_Gen_Rock_Detail_Granite_01_ORDG` (6.4 MB), `/Game/Env/Bio/PNW/Meshes/SM_Crab_Grass/Materials/T_Crab_Grass_ORTG` (1.7 MB), `/Game/Env/Bio/PNW/Meshes/SM_Crab_Grass/T_Crab_Grass_Clump_A_N` (6.4 MB), `/Game/Env/Bio/Rock/Scree/Materials/T_Scree_01_M` (0.1 MB), `/Game/Env/Bio/Rock/Scree/Scree_Rock_Clump_A/+Materials/T_Scree_Rock_Clump_A_D` (3.2 MB), `/Game/Env/Bio/Rock/Scree/Scree_Rock_Clump_A/+Materials/T_Scree_Rock_Clump_A_N` (6.4 MB), `/Game/Env/Bio/Rock/Scree/Scree_Rock_Clump_A/+Materials/T_Scree_Rock_Clump_A_ORHG` (6.4 MB)

*Group note:* Scree rocks (snow and NoSnow), scree clumps, SM_Scree_Alpine A-C (A30), PLA_Scree_Mass and a PCG scree spline

### Desert, canyon and Uluwatu rocks (Env/Bio/Rock) (214)

*Where on PWR:* Only as distant cliff mass with re-tinted MIs

| path | kind | MB | verts | bounds m | levels | PWR | note |
|---|---|---|---|---|---|---|---|
| `/Game/Env/Bio/Rock/Canyon/Materials/MIP_Rock_Canyon_Cliff_A` | MaterialInstance | 0.29 |  |  | D20,E20 | no |  |
| `/Game/Env/Bio/Rock/Canyon/Materials/MI_Rock_Canyon_Generic` | MaterialInstance | 0.09 |  |  | D20 | no |  |
| `/Game/Env/Bio/Rock/Canyon/Materials/MI_Rock_Canyon_Stone_Generic` | MaterialInstance | 0.28 |  |  | D20 | no |  |
| `/Game/Env/Bio/Rock/Canyon/Rock_BiologyRock/Materials/MIP_Rock_BiologyRock_01` | MaterialInstance | 0.09 |  |  | E20 | no |  |
| `/Game/Env/Bio/Rock/Canyon/Rock_BiologyRock/SM_BiologyRock_01` | StaticMesh | 1.18 | 25,070 | 8.4x3.23x10.75 | E20 | no |  |
| `/Game/Env/Bio/Rock/Canyon/Rock_BiologyRock/SM_BiologyRock_02` | StaticMesh | 0.84 | 15,454 | 6.99x2.05x10.66 | E20 | no |  |
| `/Game/Env/Bio/Rock/Canyon/Rock_Canyon_Arches_A/Materials/MI_Rock_Canyon_Arches_A` | MaterialInstance | 0.28 |  |  | D20 | no |  |
| `/Game/Env/Bio/Rock/Canyon/Rock_Canyon_Arches_A/Materials/MI_Rock_Canyon_Arches_A_Ground` | MaterialInstance | 0.28 |  |  | D20 | no |  |
| `/Game/Env/Bio/Rock/Canyon/Rock_Canyon_Arches_B/Materials/MI_Rock_Canyon_Arches_B` | MaterialInstance | 0.28 |  |  | D20 | no |  |
| `/Game/Env/Bio/Rock/Canyon/Rock_Canyon_Arches_B/Materials/MI_Rock_Canyon_Arches_B_Rough` | MaterialInstance | 0.28 |  |  | D20 | no |  |
| `/Game/Env/Bio/Rock/Canyon/Rock_Canyon_Arches_C/Materials/MI_Rock_Canyon_Arches_C` | MaterialInstance | 0.28 |  |  | D20 | no |  |
| `/Game/Env/Bio/Rock/Canyon/Rock_Canyon_Arches_D/Materials/MI_Rock_Canyon_Arches_D` | MaterialInstance | 0.00 |  |  | D20 | no |  |
| `/Game/Env/Bio/Rock/Canyon/Rock_Canyon_Blouder_D/SM_Rock_Canyon_Blouder_D` | StaticMesh | 7.61 | 191,258 | 6.24x6.82x3.64 | E20 | no |  |
| `/Game/Env/Bio/Rock/Canyon/Rock_Canyon_Boulder_A/Materials/MI_Rock_Canyon_Boulder_A` | MaterialInstance | 0.28 |  |  | D20 | no |  |
| `/Game/Env/Bio/Rock/Canyon/Rock_Canyon_Boulder_A/Materials/MI_Rock_Canyon_Boulder_A_Peak` | MaterialInstance | 0.28 |  |  | D20 | no |  |
| `/Game/Env/Bio/Rock/Canyon/Rock_Canyon_Boulder_B/Materials/MI_Rock_Canyon_Boulder_B` | MaterialInstance | 0.28 |  |  | D20 | no |  |
| `/Game/Env/Bio/Rock/Canyon/Rock_Canyon_Boulder_C/Materials/MI_Rock_Canyon_Boulder_C` | MaterialInstance | 0.28 |  |  | D20 | no |  |
| `/Game/Env/Bio/Rock/Canyon/Rock_Canyon_Cliff_A/Materials/MI_Rock_Canyon_Cliff_A` | MaterialInstance | 0.28 |  |  | D20 | no |  |
| `/Game/Env/Bio/Rock/Canyon/Rock_Canyon_Cliff_B/Materials/MI_Rock_Canyon_Cliff_B` | MaterialInstance | 0.28 |  |  | D20 | no |  |
| `/Game/Env/Bio/Rock/Canyon/Rock_Canyon_Cliff_B/Materials/MI_Rock_Canyon_Cliff_B_Ground` | MaterialInstance | 0.28 |  |  | D20 | no |  |
| `/Game/Env/Bio/Rock/Canyon/Rock_Canyon_Cliff_B/Materials/MI_Rock_Canyon_Cliff_B_Peak` | MaterialInstance | 0.28 |  |  | D20 | no |  |
| `/Game/Env/Bio/Rock/Canyon/Rock_Canyon_Cliff_B/Materials/MI_Rock_Canyon_Cliff_B_Rough` | MaterialInstance | 0.28 |  |  | D20 | no |  |
| `/Game/Env/Bio/Rock/Canyon/Rock_Canyon_Cliff_C/Materials/MI_Rock_Canyon_Cliff_C` | MaterialInstance | 0.28 |  |  | D20 | no |  |
| `/Game/Env/Bio/Rock/Canyon/Rock_Canyon_Cliff_C/Materials/MI_Rock_Canyon_Cliff_C_Peak` | MaterialInstance | 0.28 |  |  | D20 | no |  |
| `/Game/Env/Bio/Rock/Canyon/Rock_Canyon_Cliff_C/Materials/MI_Rock_Canyon_Cliff_C_Rough` | MaterialInstance | 0.28 |  |  | D20 | no |  |
| `/Game/Env/Bio/Rock/Canyon/Rock_Canyon_Cliff_D/Materials/MI_Rock_Canyon_Cliff_D` | MaterialInstance | 0.28 |  |  | D20 | no |  |
| `/Game/Env/Bio/Rock/Canyon/Rock_Canyon_Grikes_A/Materials/MI_Rock_Canyon_Grikes_A` | MaterialInstance | 0.28 |  |  | D20,E20 | no |  |
| `/Game/Env/Bio/Rock/Canyon/Rock_Canyon_Grikes_A/SM_Rock_Canyon_Grikes_A` | StaticMesh | 2.18 | 54,282 | 7.86x10.01x6.08 | D20,E20 | no |  |
| `/Game/Env/Bio/Rock/Canyon/Rock_Canyon_Grikes_C/Materials/MI_Rock_Canyon_Grikes` | MaterialInstance | 0.26 |  |  | E20 | no |  |
| `/Game/Env/Bio/Rock/Canyon/Rock_Canyon_Grikes_C/SM_Rock_Canyon_Grikes_C` | StaticMesh | 2.22 | 55,226 | 21.17x14.5x7.1 | E20 | no |  |
| `/Game/Env/Bio/Rock/Canyon/Rock_Canyon_Grikes_D/SM_Rock_Canyon_Grikes_D` | StaticMesh | 2.59 | 57,953 | 87.18x79.97x18.91 | E20 | no |  |
| `/Game/Env/Bio/Rock/Canyon/Rock_Canyon_Grikes_E/SM_Rock_Canyon_Grikes_E` | StaticMesh | 2.31 | 51,763 | 78.78x88.21x21.12 | E20 | no |  |
| `/Game/Env/Bio/Rock/Canyon/Rock_Canyon_Grikes_F/SM_Rock_Canyon_Grikes_F` | StaticMesh | 2.49 | 57,845 | 114.97x84.3x17.4 | E20 | no |  |
| `/Game/Env/Bio/Rock/Canyon/Rock_Canyon_Plane_A/SM_Rock_Canyon_Plane_A` | StaticMesh | 11.28 | 286,248 | 12.0x6.96x2.27 | E20 | no |  |
| `/Game/Env/Bio/Rock/Canyon/Rock_Canyon_Round_A/Materials/MI_Rock_Canyon_Round_A` | MaterialInstance | 0.28 |  |  | D20 | no |  |
| `/Game/Env/Bio/Rock/Canyon/Rock_Canyon_Round_A/Materials/MI_Rock_Canyon_Round_A_Rough` | MaterialInstance | 0.28 |  |  | D20 | no |  |
| `/Game/Env/Bio/Rock/Canyon/Rock_Canyon_Rubble_A/Materials/MI_Rock_Canyon_Rubble_A` | MaterialInstance | 0.28 |  |  | D20 | no |  |
| `/Game/Env/Bio/Rock/Canyon/Rock_Canyon_Rubble_B/Materials/MI_Rock_Canyon_Rubble_B` | MaterialInstance | 0.28 |  |  | D20 | no |  |
| `/Game/Env/Bio/Rock/Canyon/Rock_Canyon_Sandstone_A/Materials/MIP_Rock_Canyon_Sandstone` | MaterialInstance | 0.27 |  |  | E10,E20,E30 | no |  |
| `/Game/Env/Bio/Rock/Canyon/Rock_Canyon_Sandstone_A/Materials/MIP_Rock_Canyon_Sandstone_03` | MaterialInstance | 0.24 |  |  | E20 | no |  |
| `/Game/Env/Bio/Rock/Canyon/Rock_Canyon_Sandstone_A/Materials/MIP_Rock_Canyon_Sandstone_04` | MaterialInstance | 0.23 |  |  | E20 | no |  |
| `/Game/Env/Bio/Rock/Canyon/Rock_Canyon_Sandstone_A/Materials/MIP_Rock_Canyon_Sandstone_NoLeak` | MaterialInstance | 0.26 |  |  | E20 | no |  |
| `/Game/Env/Bio/Rock/Canyon/Rock_Canyon_Sandstone_A/Materials/MIP_Rock_Canyon_Sandstone_RVT` | MaterialInstance | 0.26 |  |  | E20 | no |  |
| `/Game/Env/Bio/Rock/Canyon/Rock_Canyon_Sandstone_A/Materials/MIP_Rock_Canyon_Sandstone_Rocks_RVT_E30` | MaterialInstance | 0.15 |  |  | E20 | no |  |
| `/Game/Env/Bio/Rock/Canyon/Rock_Canyon_Sandstone_A/Materials/MIP_Rock_Canyon_Sandstone_Vista` | MaterialInstance | 0.23 |  |  | E20,E30 | no |  |
| `/Game/Env/Bio/Rock/Canyon/Rock_Canyon_Sandstone_A/Materials/MIP_Rock_Canyon_Sandstone_Vista_03` | MaterialInstance | 0.21 |  |  | E20 | no |  |
| `/Game/Env/Bio/Rock/Canyon/Rock_Canyon_Sandstone_A/Materials/MIP_Rock_Canyon_Sandstone_Vista_04` | MaterialInstance | 0.24 |  |  | E20 | no |  |
| `/Game/Env/Bio/Rock/Canyon/Rock_Canyon_Sandstone_A/Materials/MI_PNWGL_Rock_Macro_01` | MaterialInstance | 0.27 |  |  | E20 | no |  |
| `/Game/Env/Bio/Rock/Canyon/Rock_Canyon_Sandstone_A/Materials/MI_Rock_Canyon_Sandstone_01` | MaterialInstance | 0.09 |  |  | E20 | no |  |
| `/Game/Env/Bio/Rock/Canyon/Rock_Canyon_Sandstone_A/Materials/MI_Rock_Canyon_Sandstone_02` | MaterialInstance | 0.26 |  |  | E20 | no |  |
| `/Game/Env/Bio/Rock/Canyon/Rock_Canyon_Sandstone_A/Materials/MI_Rock_Canyon_Sandstone_FullRed` | MaterialInstance | 0.09 |  |  | E20,E30 | no |  |
| `/Game/Env/Bio/Rock/Canyon/Rock_Canyon_Sandstone_A/Materials/MI_Rock_Canyon_Sandstone_FullRed_RVT` | MaterialInstance | 0.26 |  |  | E20 | no |  |
| `/Game/Env/Bio/Rock/Canyon/Rock_Canyon_Sandstone_A/Materials/MI_Rock_Canyon_Sandstone_NoBBoxGrad` | MaterialInstance | 0.08 |  |  | E20,E30 | no |  |
| `/Game/Env/Bio/Rock/Canyon/Rock_Canyon_Sandstone_A/Materials/MI_Rock_Canyon_Sandstone_Top` | MaterialInstance | 0.10 |  |  | E20 | no |  |
| `/Game/Env/Bio/Rock/Canyon/Rock_Canyon_Sandstone_B/SM_Rock_Canyon_Sandstone_B` | StaticMesh | 6.54 | 236,660 | 19.8x20.89x32.0 | E20,E30 | no |  |
| `/Game/Env/Bio/Rock/Canyon/Rock_Canyon_Sandstone_Base_A/SM_Rock_Canyon_Sandstone_Base_A` | StaticMesh | 33.23 | 1,586,090 | 10.82x11.2x4.37 | E20,E30 | no | very dense: confirm Nanite before placing many |
| `/Game/Env/Bio/Rock/Canyon/Rock_Canyon_Sandstone_Base_B/SM_Rock_Canyon_Sandstone_Base_B` | StaticMesh | 3.09 | 153,759 | 5.73x5.83x5.06 | E20,E30 | no |  |
| `/Game/Env/Bio/Rock/Canyon/Rock_Canyon_Sandstone_Base_C/SM_Rock_Canyon_Sandstone_Base_C` | StaticMesh | 2.16 | 104,773 | 5.73x5.83x5.06 | E20 | no |  |
| `/Game/Env/Bio/Rock/Canyon/Rock_Canyon_Sandstone_C/SM_Rock_Canyon_Sandstone_C` | StaticMesh | 12.34 | 357,986 | 44.22x27.34x22.17 | E20,E30 | no |  |
| `/Game/Env/Bio/Rock/Canyon/Rock_Canyon_Sandstone_Cave_A/SM_Rock_Canyon_Sandstone_Cave_A` | StaticMesh | 6.89 | 110,730 | 11.33x14.9x56.48 | E20,E30 | no |  |
| `/Game/Env/Bio/Rock/Canyon/Rock_Canyon_Sandstone_Cave_B/SM_Rock_Canyon_Sandstone_Cave_B` | StaticMesh | 3.65 | 99,677 | 11.32x12.89x30.43 | E20,E30 | no |  |
| `/Game/Env/Bio/Rock/Canyon/Rock_Canyon_Sandstone_Corroded_A/SM_Rock_Canyon_Sandstone_Corroded_A` | StaticMesh | 7.28 | 214,300 | 19.06x21.0x34.75 | E20,E30 | no |  |
| `/Game/Env/Bio/Rock/Canyon/Rock_Canyon_Sandstone_Corroded_B/SM_Rock_Canyon_Sandstone_Corroded_B` | StaticMesh | 11.54 | 336,732 | 58.37x33.95x59.45 | E20,E30 | no |  |
| `/Game/Env/Bio/Rock/Canyon/Rock_Canyon_Sandstone_E/SM_Rock_Canyon_Sandstone_E` | StaticMesh | 12.42 | 355,392 | 34.42x51.27x33.64 | E20 | no |  |
| `/Game/Env/Bio/Rock/Canyon/Rock_Canyon_Sandstone_F/SM_Rock_Canyon_Sandstone_F` | StaticMesh | 19.57 | 587,507 | 122.17x179.9x100.47 | E20 | no | very dense: confirm Nanite before placing many |
| `/Game/Env/Bio/Rock/Canyon/Rock_Canyon_Sandstone_G/SM_Rock_Canyon_Sandstone_G` | StaticMesh | 16.29 | 493,526 | 57.68x89.84x55.48 | E20 | no | very dense: confirm Nanite before placing many |
| `/Game/Env/Bio/Rock/Canyon/Rock_Canyon_Sandstone_Ground_A/SM_Rock_Canyon_Sandstone_Ground_A` | StaticMesh | 12.37 | 480,648 | 68.74x106.24x17.12 | E20 | no | very dense: confirm Nanite before placing many |
| `/Game/Env/Bio/Rock/Canyon/Rock_Canyon_Sandstone_I/SM_Rock_Canyon_Sandstone_I` | StaticMesh | 3.80 | 109,800 | 60.13x20.91x54.97 | E20 | no |  |
| `/Game/Env/Bio/Rock/Canyon/Rock_Canyon_Sandstone_Short_A/SM_Rock_Canyon_Sandstone_short_A` | StaticMesh | 1.55 | 44,414 | 1.08x1.18x1.15 | E20,E30 | no |  |
| `/Game/Env/Bio/Rock/Canyon/Rock_Canyon_Sandstone_Short_B/SM_Rock_Canyon_Sandstone_short_B` | StaticMesh | 0.86 | 32,832 | 1.09x0.91x0.94 | E20,E30 | no |  |
| `/Game/Env/Bio/Rock/Canyon/Rock_Canyon_Sandstone_Short_C/SM_Rock_Canyon_Sandstone_Short_C` | StaticMesh | 1.24 | 30,289 | 5.56x5.49x6.76 | E20,E30 | no |  |
| `/Game/Env/Bio/Rock/Canyon/Rock_Canyon_Sandstone_Short_D/SM_Rock_Canyon_Sandstone_Short_D` | StaticMesh | 0.98 | 33,416 | 5.84x5.83x8.88 | E20,E30 | no |  |
| `/Game/Env/Bio/Rock/Canyon/Rock_Canyon_Sandstone_Single_A/SM_Rock_Canyon_Sandstone_Single_A` | StaticMesh | 5.01 | 149,615 | 9.64x7.8x33.13 | E10,E20,E30 | no |  |
| `/Game/Env/Bio/Rock/Canyon/Rock_Canyon_Sandstone_Single_B/SM_Rock_Canyon_Sandstone_Single_B` | StaticMesh | 0.83 | 20,396 | 4.33x3.97x9.53 | E20,E30 | no |  |
| `/Game/Env/Bio/Rock/Canyon/Rock_Canyon_Sandstone_Single_B/SM_Rock_Canyon_Sandstone_Single_C` | StaticMesh | 0.65 | 15,161 | 3.76x3.3x5.2 | E20 | no |  |
| `/Game/Env/Bio/Rock/Canyon/Rock_Canyon_Sandstone_Single_B/SM_Rock_Canyon_Sandstone_Single_D` | StaticMesh | 1.54 | 65,330 | 5.29x3.25x15.11 | E20 | no |  |
| `/Game/Env/Bio/Rock/Canyon/Rock_Canyon_Sandstone_Single_B/SM_Rock_Canyon_Sandstone_Single_E` | StaticMesh | 0.84 | 30,409 | 3.8x3.12x13.01 | E20 | no |  |
| `/Game/Env/Bio/Rock/Canyon/Rock_Canyon_Sandstone_Single_B/SM_Rock_Canyon_Sandstone_Single_F` | StaticMesh | 0.85 | 30,622 | 2.58x2.39x6.81 | E20,E30 | no |  |
| `/Game/Env/Bio/Rock/Canyon/Rock_Canyon_Sandstone_Single_B/SM_Rock_Canyon_Sandstone_Single_G` | StaticMesh | 1.57 | 56,633 | 3.74x2.87x11.08 | E20,E30 | no |  |
| `/Game/Env/Bio/Rock/Canyon/Rock_Canyon_Sandstone_Single_H/SM_Rock_Canyon_Sandstone_Single_H` | StaticMesh | 4.04 | 117,186 | 5.39x5.65x18.46 | E10,E20,E30 | no | packed AO/roughness/height map |
| `/Game/Env/Bio/Rock/Canyon/Rock_Canyon_Sandstone_Single_I/SM_Rock_Canyon_Sandstone_Single_I` | StaticMesh | 3.10 | 88,589 | 12.99x10.84x21.95 | E10,E20,E30 | no |  |
| `/Game/Env/Bio/Rock/Canyon/Rock_Canyon_Sandstone_Sml_A/SM_Rock_Canyon_Sandstone_Sml_A` | StaticMesh | 5.76 | 200,627 | 19.91x15.73x15.06 | E20 | no |  |
| `/Game/Env/Bio/Rock/Canyon/Rock_Canyon_Sandstone_Top_A/Materials/MIP_Rock_Canyon_Sandstone_Top` | MaterialInstance | 0.26 |  |  | E20,E30 | no |  |
| `/Game/Env/Bio/Rock/Canyon/Rock_Canyon_Sandstone_Top_A/SM_Rock_Canyon_Sandstone_Top_A` | StaticMesh | 6.82 | 190,367 | 60.95x53.86x29.53 | E20,E30 | no |  |
| `/Game/Env/Bio/Rock/Canyon/Rock_Canyon_Sandstone_Top_B/SM_Rock_Canyon_Sandstone_Top_B` | StaticMesh | 4.00 | 142,305 | 43.74x45.57x14.88 | E20,E30 | no |  |
| `/Game/Env/Bio/Rock/Canyon/Rock_Canyon_Sandstone_Top_C/SM_Rock_Canyon_Sandstone_Top_C` | StaticMesh | 11.46 | 338,418 | 59.47x47.31x19.34 | E20,E30 | no |  |
| `/Game/Env/Bio/Rock/Canyon/Rock_Canyon_Sandstone_Top_D/SM_Rock_Canyon_Sandstone_Top_D` | StaticMesh | 16.68 | 515,413 | 59.01x46.95x22.39 | E20,E30 | no | very dense: confirm Nanite before placing many |
| `/Game/Env/Bio/Rock/Canyon/Rock_Canyon_Sandstone_thin_G/SM_Rock_Canyon_Sandstone_thin_G` | StaticMesh | 10.53 | 393,539 | 54.7x89.84x58.53 | E20 | no |  |
| `/Game/Env/Bio/Rock/Desert/Materials/MIP_Rock_Desert_Cliff_A_CL` | MaterialInstance | 0.26 |  |  | A50,D20,D40,E20 | no |  |
| `/Game/Env/Bio/Rock/Desert/Materials/MIP_Rocks_Desert_Arches_D_VectorSand` | MaterialInstance | 0.28 |  |  | A50,D20,E20 | no |  |
| `/Game/Env/Bio/Rock/Desert/Rock_Desert_Boulder_A/Materials/MI_Rock_Desert_Boulder_A` | MaterialInstance | 0.24 |  |  | A50,D20,D40,E20 | no |  |
| `/Game/Env/Bio/Rock/Desert/Rock_Desert_Boulder_A/Materials/MI_Rock_Desert_Boulder_A2` | MaterialInstance | 0.24 |  |  | D40 | no |  |
| `/Game/Env/Bio/Rock/Desert/Rock_Desert_Boulder_A/Materials/MI_Rock_Desert_Boulder_A2_D40VistaInheritance` | MaterialInstance | 0.23 |  |  | D40 | no |  |
| `/Game/Env/Bio/Rock/Desert/Rock_Desert_Boulder_A/Materials/MI_Rock_Desert_Boulder_A_Darker_NoStraining` | MaterialInstance | 0.23 |  |  | A50 | no |  |
| `/Game/Env/Bio/Rock/Desert/Rock_Desert_Boulder_A/Materials/MI_Rock_Desert_Boulder_A_Inheritance` | MaterialInstance | 0.24 |  |  | A50 | no |  |
| `/Game/Env/Bio/Rock/Desert/Rock_Desert_Boulder_A/Materials/MI_Rock_Desert_Boulder_A_NoStraining` | MaterialInstance | 0.23 |  |  | A50 | no |  |
| `/Game/Env/Bio/Rock/Desert/Rock_Desert_Boulder_A/SM_Rock_Desert_Boulder_A` | StaticMesh | 2.25 | 51,053 | 3.81x3.15x2.27 | A50,D20,D40,E20 | no |  |
| `/Game/Env/Bio/Rock/Desert/Rock_Desert_Boulder_B/Materials/MI_Rock_Desert_Boulder_B` | MaterialInstance | 0.24 |  |  | A50,D20,E20 | no |  |
| `/Game/Env/Bio/Rock/Desert/Rock_Desert_Boulder_B/SM_Rock_Desert_Boulder_B` | StaticMesh | 0.27 | 2,879 | 2.21x2.07x1.96 | A50,D20,E20 | no |  |
| `/Game/Env/Bio/Rock/Desert/Rock_Desert_Boulder_C/Materials/MI_Rock_Desert_Boulder_C` | MaterialInstance | 0.24 |  |  | A50,D20,E20 | no |  |
| `/Game/Env/Bio/Rock/Desert/Rock_Desert_Boulder_C/Materials/MI_Rock_Desert_Boulder_C_Inheritance` | MaterialInstance | 0.23 |  |  | A50 | no |  |
| `/Game/Env/Bio/Rock/Desert/Rock_Desert_Boulder_C/SM_Rock_Desert_Boulder_C` | StaticMesh | 0.30 | 5,921 | 1.92x1.38x1.21 | A50,D20,E20 | no |  |
| `/Game/Env/Bio/Rock/Desert/Rock_Desert_Cliff_A/Materials/MI_Rock_Desert_Cliff_A` | MaterialInstance | 0.26 |  |  | A50,D20 | no |  |
| `/Game/Env/Bio/Rock/Desert/Rock_Desert_Cliff_A/Materials/MI_Rock_Desert_Cliff_A_Inheritance` | MaterialInstance | 0.26 |  |  | A50 | no |  |
| `/Game/Env/Bio/Rock/Desert/Rock_Desert_Cliff_A/Materials/MI_Rock_Desert_Cliff_A_NoStaining` | MaterialInstance | 0.26 |  |  | A50 | no |  |
| `/Game/Env/Bio/Rock/Desert/Rock_Desert_Cliff_A/Materials/MI_Rock_Desert_Cliff_A_Vista` | MaterialInstance | 0.26 |  |  | A50 | no |  |
| `/Game/Env/Bio/Rock/Desert/Rock_Desert_Cliff_A/SM_Rock_Desert_Cliff_A` | StaticMesh | 5.91 | 145,745 | 33.9x35.68x28.68 | A50,D20 | yes |  |
| `/Game/Env/Bio/Rock/Desert/Rock_Desert_Cliff_B/Materials/MI_Rock_Desert_Cliff_B` | MaterialInstance | 0.26 |  |  | A50,D20 | no |  |
| `/Game/Env/Bio/Rock/Desert/Rock_Desert_Cliff_B/Materials/MI_Rock_Desert_Cliff_B_Inheritance` | MaterialInstance | 0.26 |  |  | A50 | no |  |
| `/Game/Env/Bio/Rock/Desert/Rock_Desert_Cliff_B/Materials/MI_Rock_Desert_Cliff_B_NoStaining` | MaterialInstance | 0.26 |  |  | A50 | no |  |
| `/Game/Env/Bio/Rock/Desert/Rock_Desert_Cliff_B/Materials/MI_Rock_Desert_Cliff_B_NoStaining_Inheritance` | MaterialInstance | 0.26 |  |  | A50 | no |  |
| `/Game/Env/Bio/Rock/Desert/Rock_Desert_Cliff_B/SM_Rock_Desert_Cliff_B` | StaticMesh | 4.92 | 122,373 | 37.37x27.55x25.09 | A50,D20 | yes |  |
| `/Game/Env/Bio/Rock/Desert/Rock_Desert_Cliff_C/Materials/MI_Rock_Desert_Cliff_C` | MaterialInstance | 0.27 |  |  | A50,D20 | no |  |
| `/Game/Env/Bio/Rock/Desert/Rock_Desert_Cliff_C/Materials/MI_Rock_Desert_Cliff_C_NoStaining` | MaterialInstance | 0.26 |  |  | A50 | no |  |
| `/Game/Env/Bio/Rock/Desert/Rock_Desert_Cliff_C/Materials/MI_Rock_Desert_Cliff_C_NoStaining_Inheritance` | MaterialInstance | 0.26 |  |  | A50 | no |  |
| `/Game/Env/Bio/Rock/Desert/Rock_Desert_Cliff_C/Materials/MI_Rock_Desert_Cliff_C_Vista` | MaterialInstance | 0.27 |  |  | A50 | no |  |
| `/Game/Env/Bio/Rock/Desert/Rock_Desert_Cliff_C/SM_Rock_Desert_Cliff_C` | StaticMesh | 3.78 | 83,039 | 26.01x29.62x28.36 | A50,D20 | yes |  |
| `/Game/Env/Bio/Rock/Desert/Rock_Desert_Cliff_D/Materials/MI_Rock_Desert_Cliff_D` | MaterialInstance | 0.27 |  |  | A50,D20 | no |  |
| `/Game/Env/Bio/Rock/Desert/Rock_Desert_Cliff_D/SM_Rock_Desert_Cliff_D` | StaticMesh | 3.18 | 91,522 | 51.09x27.63x29.19 | A50,D20 | yes |  |
| `/Game/Env/Bio/Rock/Desert/Rock_Desert_Cliff_Round_A/Materials/MI_Rock_Desert_Cliff_Round_A` | MaterialInstance | 0.27 |  |  | A50,D20 | no |  |
| `/Game/Env/Bio/Rock/Desert/Rock_Desert_Cliff_Round_A/Materials/MI_Rock_Desert_Cliff_Round_A_StainingDecal` | MaterialInstance | 0.00 |  |  | A50 | no | [decal] |
| `/Game/Env/Bio/Rock/Desert/Rock_Desert_Cliff_Round_A/Materials/MI_Rock_Desert_Cliff_Round_A_Variant` | MaterialInstance | 0.26 |  |  | A50 | no |  |
| `/Game/Env/Bio/Rock/Desert/Rock_Desert_Cliff_Round_A/SM_Rock_Desert_Cliff_Round_A` | StaticMesh | 3.09 | 90,878 | 16.38x23.7x14.49 | A50,D20 | no |  |
| `/Game/Env/Bio/Rock/Desert/Rock_Desert_Rubble_A/Material/MI_Rock_Desert_Rubble_A` | MaterialInstance | 0.28 |  |  | A50,D20,E20 | no |  |
| `/Game/Env/Bio/Rock/Desert/Rock_Desert_Rubble_A/Material/MI_Rock_Desert_Rubble_A_E10` | MaterialInstance | 0.09 |  |  | E20 | no |  |
| `/Game/Env/Bio/Rock/Desert/Rock_Desert_Rubble_A/SM_Rock_Desert_Rubble_A` | StaticMesh | 1.54 | 39,610 | 27.52x13.39x9.37 | A50,D20,E20 | no |  |
| `/Game/Env/Bio/Rock/Desert/Rock_Desert_Rubble_B/Material/MI_Rock_Desert_Rubble_B` | MaterialInstance | 0.28 |  |  | A50,D20,E20 | no |  |
| `/Game/Env/Bio/Rock/Desert/Rock_Desert_Rubble_B/Material/MI_Rock_Desert_Rubble_B_E20` | MaterialInstance | 0.18 |  |  | E20 | no |  |
| `/Game/Env/Bio/Rock/Desert/Rock_Desert_Rubble_B/SM_Rock_Desert_Rubble_B` | StaticMesh | 0.73 | 18,806 | 5.28x3.05x0.51 | A50,D20,E20 | no |  |
| `/Game/Env/Bio/Rock/Desert/Rock_Desert_Stone_A/Materials/MI_Rock_Desert_Stone_A` | MaterialInstance | 0.24 |  |  | A50,D20,E20 | no |  |
| `/Game/Env/Bio/Rock/Desert/Rock_Desert_Stone_A/Materials/MI_Rock_Desert_Stone_A_NoStraining` | MaterialInstance | 0.23 |  |  | A50 | no |  |
| `/Game/Env/Bio/Rock/Desert/Rock_Desert_Stone_A/PLAY_SM_Rock_Desert_Stone_A_CollisionMesh` | StaticMesh | 0.09 |  |  |  | no | collision proxy mesh |
| `/Game/Env/Bio/Rock/Desert/Rock_Desert_Stone_A/SM_Rock_Desert_Stone_A` | StaticMesh | 0.09 | 501 | 0.56x0.46x0.32 | A50,D20,E20 | no |  |
| `/Game/Env/Bio/Rock/Desert/Rock_Desert_Stone_B/Materials/MI_Rock_Desert_Stone_B` | MaterialInstance | 0.24 |  |  | A50,D20,E20 | no |  |
| `/Game/Env/Bio/Rock/Desert/Rock_Desert_Stone_B/Materials/MI_Rock_Desert_Stone_B_NoStaining` | MaterialInstance | 0.23 |  |  | A50 | no |  |
| `/Game/Env/Bio/Rock/Desert/Rock_Desert_Stone_B/PLAY_SM_Rock_Desert_Stone_B_CollisionMesh` | StaticMesh | 0.06 |  |  |  | no | collision proxy mesh |
| `/Game/Env/Bio/Rock/Desert/Rock_Desert_Stone_B/SM_Rock_Desert_Stone_B` | StaticMesh | 0.06 | 309 | 0.34x0.32x0.31 | A50,D20,E20 | no |  |
| `/Game/Env/Bio/Rock/Desert/Rock_Desert_Stone_C/Materials/MI_Rock_Desert_Stone_C` | MaterialInstance | 0.24 |  |  | A50,D20,E20 | no |  |
| `/Game/Env/Bio/Rock/Desert/Rock_Desert_Stone_C/Materials/MI_Rock_Desert_Stone_C_NoStaining` | MaterialInstance | 0.23 |  |  | A50 | no |  |
| `/Game/Env/Bio/Rock/Desert/Rock_Desert_Stone_C/PLAY_SM_Rock_Desert_Stone_C_CollisionMesh` | StaticMesh | 0.04 |  |  |  | no | collision proxy mesh |
| `/Game/Env/Bio/Rock/Desert/Rock_Desert_Stone_C/SM_Rock_Desert_Stone_C` | StaticMesh | 0.05 | 250 | 0.36x0.27x0.24 | A50,D20,E20 | no |  |
| `/Game/Env/Bio/Rock/Desert/Rocks_Desert_Arches_A/Materials/MI_Rocks_Desert_Arches_A` | MaterialInstance | 0.27 |  |  | A50,D20 | no |  |
| `/Game/Env/Bio/Rock/Desert/Rocks_Desert_Arches_A/Materials/MI_Rocks_Desert_Arches_A_NoStraining` | MaterialInstance | 0.27 |  |  | A50 | no |  |
| `/Game/Env/Bio/Rock/Desert/Rocks_Desert_Arches_A/Materials/MI_Rocks_Desert_Arches_A_NoStraining_Inheritance` | MaterialInstance | 0.26 |  |  | A50 | no |  |
| `/Game/Env/Bio/Rock/Desert/Rocks_Desert_Arches_A/SM_Rocks_Desert_Arches_A` | StaticMesh | 3.75 | 91,324 | 20.75x32.15x11.36 | A50,D20 | no |  |
| `/Game/Env/Bio/Rock/Desert/Rocks_Desert_Arches_B/Materials/MI_Rocks_Desert_Arches_B` | MaterialInstance | 0.26 |  |  | A50,D20 | no |  |
| `/Game/Env/Bio/Rock/Desert/Rocks_Desert_Arches_B/SM_Rocks_Desert_Arches_B` | StaticMesh | 0.97 | 25,925 | 20.1x16.06x11.21 | A50,D20 | no |  |
| `/Game/Env/Bio/Rock/Desert/Rocks_Desert_Arches_C/Materials/MI_Rocks_Desert_Arches_C` | MaterialInstance | 0.26 |  |  | A50,D20 | no |  |
| `/Game/Env/Bio/Rock/Desert/Rocks_Desert_Arches_C/SM_Rocks_Desert_Arches_C` | StaticMesh | 0.99 | 26,231 | 30.01x8.89x5.84 | A50,D20 | no |  |
| `/Game/Env/Bio/Rock/Desert/Rocks_Desert_Arches_D/Materials/MI_Rocks_Desert_Arches_D` | MaterialInstance | 0.28 |  |  | A50,D20 | no |  |
| `/Game/Env/Bio/Rock/Desert/Rocks_Desert_Arches_D/Materials/MI_Rocks_Desert_Arches_D_Inherit` | MaterialInstance | 0.27 |  |  | A50 | no |  |
| `/Game/Env/Bio/Rock/Desert/Rocks_Desert_Arches_D/SM_Rocks_Desert_Arches_D` | StaticMesh | 4.56 | 136,080 | 50.97x18.96x14.86 | A50,D20 | no |  |
| `/Game/Env/Bio/Rock/Swamp/Rock_Swamp_Lrg_A/Materials/MI_Env_Layered_Rock_Swamp_Lrg_A` | MaterialInstance | 0.16 |  |  | A30,C10,E20 | no |  |
| `/Game/Env/Bio/Rock/Swamp/Rock_Swamp_Lrg_A/Materials/MI_Env_Layered_Rock_Swamp_Lrg_A_Wet` | MaterialInstance | 0.08 |  |  | C10 | no | wet variant |
| `/Game/Env/Bio/Rock/Swamp/Rock_Swamp_Lrg_A/Materials/MI_Env_Layered_Rock_Swamp_Lrg_B` | MaterialInstance | 0.15 |  |  | C10,E20 | no |  |
| `/Game/Env/Bio/Rock/Swamp/Rock_Swamp_Lrg_A/Materials/MI_Env_Layered_Rock_Swamp_Lrg_B_Wet` | MaterialInstance | 0.08 |  |  | C10 | no | wet variant |
| `/Game/Env/Bio/Rock/Swamp/Rock_Swamp_Lrg_A/Materials/MI_Env_Layered_Rock_Swamp_Lrg_C` | MaterialInstance | 0.16 |  |  | C10 | no |  |
| `/Game/Env/Bio/Rock/Swamp/Rock_Swamp_Lrg_A/Materials/MI_Env_Layered_Rock_Swamp_Lrg_C_Wet` | MaterialInstance | 0.15 |  |  | C10 | no | wet variant |
| `/Game/Env/Bio/Rock/Swamp/Rock_Swamp_Lrg_A/Materials/MI_Env_Layered_Rock_Swamp_Sml_Wet` | MaterialInstance | 0.15 |  |  | C10 | no | wet variant |
| `/Game/Env/Bio/Rock/Swamp/Rock_Swamp_Lrg_A/SM_Rock_Swamp_Lrg_A` | StaticMesh | 0.99 | 25,135 | 11.85x8.43x7.21 | A30,C10 | no |  |
| `/Game/Env/Bio/Rock/Swamp/Rock_Swamp_Lrg_B/SM_Rock_Swamp_Lrg_B` | StaticMesh | 0.67 | 15,955 | 10.43x10.31x7.34 | C10 | no |  |
| `/Game/Env/Bio/Rock/Swamp/Rock_Swamp_Med_A/SM_Rock_Swamp_Med_A` | StaticMesh | 0.33 | 4,923 | 3.56x3.59x2.36 | C10 | no |  |
| `/Game/Env/Bio/Rock/Swamp/Rock_Swamp_Med_B/SM_Rock_Swamp_Med_B` | StaticMesh | 0.29 | 3,257 | 2.67x3.1x2.14 | C10,E20 | no |  |
| `/Game/Env/Bio/Rock/Swamp/Rock_Swamp_Sml_A/SM_Rock_Swamp_Sml_A` | StaticMesh | 0.24 | 2,595 | 1.17x0.9x0.56 | C10,E20 | no |  |
| `/Game/Env/Bio/Rock/Swamp/Rock_Swamp_Sml_B/SM_Rock_Swamp_Sml_B` | StaticMesh | 0.31 | 2,134 | 1.01x0.86x0.72 | C10 | no |  |
| `/Game/Env/Bio/Rock/Swamp/Rock_Swamp_Sml_C/SM_Rock_Swamp_Sml_C` | StaticMesh | 0.19 | 1,852 | 0.82x0.69x0.37 | C10 | no |  |
| `/Game/Env/Bio/Rock/Swamp/Rock_Swamp_Sml_D/SM_Rock_Swamp_Sml_D` | StaticMesh | 0.08 | 2,372 | 0.34x0.23x0.18 | C10,E20 | no |  |
| `/Game/Env/Bio/Rock/Uluwatu/Materials/MIP_Rock_Uluwatu_Med` | MaterialInstance | 0.17 |  |  | A15,B30,C10 | no |  |
| `/Game/Env/Bio/Rock/Uluwatu/Materials/MI_Rock_Uluwatu_Asteroids_ClosePlanet` | MaterialInstance | 0.00 |  |  | E30 | no |  |
| `/Game/Env/Bio/Rock/Uluwatu/Materials/MI_Rock_Uluwatu_Asteroids_HOTDistance` | MaterialInstance | 0.00 |  |  | E30 | no |  |
| `/Game/Env/Bio/Rock/Uluwatu/Materials/M_Rock_Uluwatu_Asteroids` | Material | 0.01 |  |  | E30 | no |  |
| `/Game/Env/Bio/Rock/Uluwatu/Rock_Uluwatu_Cliff_B/Materials/MIP_Rock_Uluwatu_Cliff_B` | MaterialInstance | 0.18 |  |  | A30,B30,C10 | listed |  |
| `/Game/Env/Bio/Rock/Uluwatu/Rock_Uluwatu_Cliff_B/Materials/MIP_Rock_Uluwatu_Cliff_B_Cave` | MaterialInstance | 0.00 |  |  | B30 | no | sibling used by PWR |
| `/Game/Env/Bio/Rock/Uluwatu/Rock_Uluwatu_Cliff_B/Materials/MIP_Rock_Uluwatu_Cliff_B_CaveFloor` | MaterialInstance | 0.17 |  |  | B30 | no | sibling used by PWR |
| `/Game/Env/Bio/Rock/Uluwatu/Rock_Uluwatu_Cliff_B/Materials/MIP_Rock_Uluwatu_Cliff_B_Lessinheritance` | MaterialInstance | 0.00 |  |  | B30 | no | sibling used by PWR |
| `/Game/Env/Bio/Rock/Uluwatu/Rock_Uluwatu_Cliff_B/Materials/MIP_Rock_Uluwatu_Cliff_B_NoVector_02` | MaterialInstance | 0.09 |  |  | B30 | no | sibling used by PWR |
| `/Game/Env/Bio/Rock/Uluwatu/Rock_Uluwatu_Cliff_B/Materials/MIP_Rock_Uluwatu_Cliff_B_NoVector_NoStaining` | MaterialInstance | 0.09 |  |  | B30 | no | sibling used by PWR |
| `/Game/Env/Bio/Rock/Uluwatu/Rock_Uluwatu_Cliff_B/Materials/MIP_Rock_Uluwatu_Cliff_B_NoVector_Reduced` | MaterialInstance | 0.09 |  |  | B30 | no | sibling used by PWR |
| `/Game/Env/Bio/Rock/Uluwatu/Rock_Uluwatu_Cliff_B/Materials/MIP_Rock_Uluwatu_Cliff_B_NoVector_StainingInvert` | MaterialInstance | 0.17 |  |  | B30 | no | sibling used by PWR |
| `/Game/Env/Bio/Rock/Uluwatu/Rock_Uluwatu_Cliff_B/Materials/MIP_Rock_Uluwatu_Cliff_B_NoVector_StainingInvert_Vegetation` | MaterialInstance | 0.19 |  |  | B30 | no | sibling used by PWR |
| `/Game/Env/Bio/Rock/Uluwatu/Rock_Uluwatu_Cliff_B/Materials/MIP_Rock_Uluwatu_Cliff_B_NoVector_StainingInvert_Vegetation_lite` | MaterialInstance | 0.19 |  |  | B30 | no | sibling used by PWR |
| `/Game/Env/Bio/Rock/Uluwatu/Rock_Uluwatu_Cliff_B/Materials/MIP_Rock_Uluwatu_Cliff_B_SandVector` | MaterialInstance | 0.19 |  |  | B30 | no | sibling used by PWR |
| `/Game/Env/Bio/Rock/Uluwatu/Rock_Uluwatu_Cliff_B/Materials/MIP_Rock_Uluwatu_Cliff_B_Vegetation` | MaterialInstance | 0.19 |  |  | B30 | no | sibling used by PWR |
| `/Game/Env/Bio/Rock/Uluwatu/Rock_Uluwatu_Cliff_B/Materials/MIP_Rock_Uluwatu_Cliff_B_Vegetation_Med` | MaterialInstance | 0.19 |  |  | B30 | no | sibling used by PWR |
| `/Game/Env/Bio/Rock/Uluwatu/Rock_Uluwatu_Cliff_B/Materials/MIP_Rock_Uluwatu_Cliff_B_Vegetation_lite` | MaterialInstance | 0.19 |  |  | B30 | no | sibling used by PWR |
| `/Game/Env/Bio/Rock/Uluwatu/Rock_Uluwatu_Cliff_B/Materials/MIP_Rock_Uluwatu_Cliff_B_Waterline` | MaterialInstance | 0.09 |  |  | A30,B30 | no | sibling used by PWR |
| `/Game/Env/Bio/Rock/Uluwatu/Rock_Uluwatu_Cliff_B/Materials/MIP_Rock_Uluwatu_Cliff_B_Waterline_Vegetation` | MaterialInstance | 0.19 |  |  | B30 | no | sibling used by PWR |
| `/Game/Env/Bio/Rock/Uluwatu/Rock_Uluwatu_Cliff_B/Materials/MIP_Rock_Uluwatu_Cliff_B_Waterline_Vegetation_NoWetness` | MaterialInstance | 0.19 |  |  | B30 | no | sibling used by PWR |
| `/Game/Env/Bio/Rock/Uluwatu/Rock_Uluwatu_Cliff_B/Materials/MIP_Rock_Uluwatu_VistaBlank` | MaterialInstance | 0.12 |  |  | B30 | no | sibling used by PWR |
| `/Game/Env/Bio/Rock/Uluwatu/Rock_Uluwatu_Cliff_B/Materials/MI_Rock_Uluwatu_Cliff_B_LiteVector` | MaterialInstance | 0.09 |  |  | B30 | no | sibling used by PWR |
| `/Game/Env/Bio/Rock/Uluwatu/Rock_Uluwatu_Cliff_B/Materials/MI_Rock_Uluwatu_Cliff_B_Waterline_NoVectorRVT` | MaterialInstance | 0.09 |  |  | B30 | no | sibling used by PWR |
| `/Game/Env/Bio/Rock/Uluwatu/Rock_Uluwatu_Cliff_B/Materials/MI_Rock_Uluwatu_Cliff_B_Waterline_NoVectorRVT_LowerRock_Inst` | MaterialInstance | 0.17 |  |  | B30 | no | sibling used by PWR |
| `/Game/Env/Bio/Rock/Uluwatu/Rock_Uluwatu_Cliff_B/SM_Rock_B30_TunnelMesh_01` | StaticMesh | 0.61 | 10,159 | 47.42x38.51x14.46 | B30 | no | sibling used by PWR |
| `/Game/Env/Bio/Rock/Uluwatu/Rock_Uluwatu_Cliff_B/SM_Rock_B30_TunnelMesh_OG_02` | StaticMesh | 0.66 | 10,176 | 50.98x44.55x26.4 | B30 | no | sibling used by PWR |
| `/Game/Env/Bio/Rock/Uluwatu/Rock_Uluwatu_Cliff_B/SM_Rock_Uluwatu_Cliff_B` | StaticMesh | 11.35 | 286,547 | 61.38x58.52x60.46 | B30 | yes |  |
| `/Game/Env/Bio/Rock/Uluwatu/Rock_Uluwatu_Cliff_B/SM_Rock_Uluwatu_Cliff_B_BG` | StaticMesh | 11.35 | 286,547 | 61.38x58.52x60.46 | B30,C10 | no | sibling used by PWR |
| `/Game/Env/Bio/Rock/Uluwatu/Rock_Uluwatu_Cliff_B/_GENERATED/SM_Rock_Uluwatu_Cliff_B_8MsingleUV/SM_ChunkedPart_0_4CC4B5` | StaticMesh | 32.62 | 1,010,260 | 29.97x28.94x30.22 | C10 | no | very dense: confirm Nanite before placing many |
| `/Game/Env/Bio/Rock/Uluwatu/Rock_Uluwatu_Cliff_B/_GENERATED/SM_Rock_Uluwatu_Cliff_B_8MsingleUV/SM_ChunkedPart_2_D6A162` | StaticMesh | 36.62 | 1,133,024 | 30.69x29.26x29.41 | C10 | no | very dense: confirm Nanite before placing many |
| `/Game/Env/Bio/Rock/Uluwatu/Rock_Uluwatu_Cliff_B/_GENERATED/SM_Rock_Uluwatu_Cliff_B_8MsingleUV/SM_ChunkedPart_4_47053B` | StaticMesh | 41.29 | 1,282,212 | 30.69x28.31x29.86 | C10 | no | very dense: confirm Nanite before placing many |
| `/Game/Env/Bio/Rock/Uluwatu/Rock_Uluwatu_Cliff_B/_GENERATED/SM_Rock_Uluwatu_Cliff_B_8MsingleUV/SM_ChunkedPart_6_0B5D4D` | StaticMesh | 38.12 | 1,176,074 | 30.47x26.42x29.25 | C10 | no | very dense: confirm Nanite before placing many |
| `/Game/Env/Bio/Rock/Uluwatu/Rock_Uluwatu_Med_A/MI_Rock_Uluwatu_Med_A` | MaterialInstance | 0.00 |  |  | A15,B30 | no |  |
| `/Game/Env/Bio/Rock/Uluwatu/Rock_Uluwatu_Med_A/Materials/MI_Rock_Uluwatu_Med_A_Waterline` | MaterialInstance | 0.17 |  |  | B30 | no |  |
| `/Game/Env/Bio/Rock/Uluwatu/Rock_Uluwatu_Med_A/SM_Rock_Uluwatu_Med_A` | StaticMesh | 3.11 | 82,607 | 1.57x2.26x1.49 | A15,B30 | no |  |
| `/Game/Env/Bio/Rock/Uluwatu/Rock_Uluwatu_Med_A/SM_Rock_Uluwatu_Med_A_Asteroid` | StaticMesh | 2.67 | 82,102 | 1.57x2.26x1.49 | E30 | no |  |
| `/Game/Env/Bio/Rock/Uluwatu/Rock_Uluwatu_Med_B/Materials/MI_Rock_Uluwatu_Med_B` | MaterialInstance | 0.17 |  |  | A15,B30,C10 | no |  |
| `/Game/Env/Bio/Rock/Uluwatu/Rock_Uluwatu_Med_B/Materials/MI_Rock_Uluwatu_Med_B_Waterline` | MaterialInstance | 0.17 |  |  | B30 | no |  |
| `/Game/Env/Bio/Rock/Uluwatu/Rock_Uluwatu_Med_B/Materials/MI_Rock_Uluwatu_Med_B_Wet` | MaterialInstance | 0.09 |  |  | C10 | no | wet variant |
| `/Game/Env/Bio/Rock/Uluwatu/Rock_Uluwatu_Med_B/SM_Rock_Uluwatu_Med_B` | StaticMesh | 3.25 | 82,276 | 3.44x3.09x2.67 | A15,B30,C10 | no |  |
| `/Game/Env/Bio/Rock/Uluwatu/Rock_Uluwatu_Med_B/SM_Rock_Uluwatu_Med_B_Asteroid` | StaticMesh | 2.82 | 82,236 | 3.44x3.09x2.67 | E30 | no |  |
| `/Game/Env/Bio/Rock/Uluwatu/Rock_Uluwatu_Med_C/MI_Rock_Uluwatu_Med_C` | MaterialInstance | 0.09 |  |  | A15,B30,C10 | no |  |
| `/Game/Env/Bio/Rock/Uluwatu/Rock_Uluwatu_Med_C/MI_Rock_Uluwatu_Med_C_Wet` | MaterialInstance | 0.09 |  |  | C10 | no | wet variant |
| `/Game/Env/Bio/Rock/Uluwatu/Rock_Uluwatu_Med_C/Materials/MI_Rock_Uluwatu_Med_C_Waterline` | MaterialInstance | 0.17 |  |  | B30 | no |  |
| `/Game/Env/Bio/Rock/Uluwatu/Rock_Uluwatu_Med_C/SM_Rock_Uluwatu_Med_C` | StaticMesh | 3.30 | 82,373 | 3.63x2.93x3.68 | A15,B30 | no |  |
| `/Game/Env/Bio/Rock/Uluwatu/Rock_Uluwatu_Med_C/SM_Rock_Uluwatu_Med_C_Asteroid` | StaticMesh | 2.87 | 82,372 | 3.63x2.93x3.68 | E30 | no |  |

*Group note:* Warm desert/canyon/tropical rock families; PWR already uses Desert_Cliff A-D and Uluwatu_Cliff_B

### Cliff kits (Env/Bio/Rock/Cliff*, Massive tundra, Limestone) (18)

*Where on PWR:* Cliff bands above the river and around the bases

| path | kind | MB | verts | bounds m | levels | PWR | note |
|---|---|---|---|---|---|---|---|
| `/Game/Env/Bio/Rock/Cliff/Rock_Cliff_Kit_D/PLAY_SM_Rock_Cliff_Kit_D_CollisionMesh` | StaticMesh | 0.41 |  |  |  | no | collision proxy mesh |
| `/Game/Env/Bio/Rock/CliffFlat/Rock_CliffFlat_Kit_B/SM_Rock_CliffFlat_Kit_B` | StaticMesh | 27.61 | 822,098 | 16.85x34.47x9.53 | E20 | yes | very dense: confirm Nanite before placing many |
| `/Game/Env/Bio/Rock/Cliff_Rocks/Materials/MI_Huge_Icelandic_Lava_Cliff` | MaterialInstance | 0.17 |  |  | A30 | no |  |
| `/Game/Env/Bio/Rock/Cliff_Rocks/SM_Huge_Icelandic_Lava_Cliff_siEoZ_high` | StaticMesh | 2.79 | 72,759 | 15.47x5.15x4.36 | A30 | no |  |
| `/Game/Env/Bio/Rock/Limestone/Limestone_Slab_A/SM_Limestone_Slab_A` | StaticMesh | 6.51 | 196,605 | 0.69x1.57x0.39 | A30 | no |  |
| `/Game/Env/Bio/Rock/Limestone/Limestone_Slab_B/SM_Limestone_Slab_B` | StaticMesh | 1.66 | 45,789 | 0.65x0.83x0.27 | A30 | no |  |
| `/Game/Env/Bio/Rock/Limestone/Limestone_Slab_C/SM_Limestone_Slab_C` | StaticMesh | 1.41 | 41,032 | 2.23x1.41x0.84 | A30 | no |  |
| `/Game/Env/Bio/Rock/Massive_Tundra_Rock_Formation/MI_Massive_Tundra_Rock_Formation_01` | MaterialInstance | 0.13 |  |  | A30 | listed |  |
| `/Game/Env/Bio/Rock/Massive_Tundra_Rock_Formation/SM_MassiveTundraRockFormation_01` | StaticMesh | 7.55 | 228,150 | 77.12x28.55x12.44 | A30 | yes |  |
| `/Game/Env/Bio/Rock/Materials/MLIM_Rock_Base` | MaterialLayerInstance | 0.00 |  |  | A30,B40,C20,C45 | no |  |
| `/Game/Env/Bio/Rock/Materials/MLIM_Rock_Macro_Tile` | MaterialLayerInstance | 0.00 |  |  | A30,B40,C20,C45 | no |  |

Textures: `/Game/Env/Bio/Rock/Cliff_Rocks/Materials/T_Huge_Icelandic_Lava_Cliff_Albedo` (6.4 MB), `/Game/Env/Bio/Rock/Cliff_Rocks/Materials/T_Huge_Icelandic_Lava_Cliff_N` (6.4 MB), `/Game/Env/Bio/Rock/Cliff_Rocks/Materials/T_Huge_Icelandic_Lava_Cliff_ORHG` (6.4 MB), `/Game/Env/Bio/Rock/Massive_Tundra_Rock_Formation/T_MassiveTundraRockFormation_01_BC` (25.4 MB), `/Game/Env/Bio/Rock/Massive_Tundra_Rock_Formation/T_MassiveTundraRockFormation_01_N` (6.4 MB), `/Game/Env/Bio/Rock/Massive_Tundra_Rock_Formation/T_Massive_Tundra_Rock_Formation_wcrmbiar_ORHG` (6.4 MB), `/Game/Env/Bio/Rock/Materials/T_Rock_Swamp_01_M` (0.3 MB)

*Group note:* Env/Bio cliff and outcrop kits; CliffFlat_Kit_B and MassiveTundra already used

### Glacial rocks (Env/Bio/Rock/Glacial) (20)

*Where on PWR:* Boulders and outcrops everywhere; AllSnow/Snow MIs for the high slopes

| path | kind | MB | verts | bounds m | levels | PWR | note |
|---|---|---|---|---|---|---|---|
| `/Game/Env/Bio/Rock/Glacial/Materials/MIP_Rock_Glacial` | MaterialInstance | 0.19 |  |  | A30,B40,C20,C45 | no |  |
| `/Game/Env/Bio/Rock/Glacial/Materials/MIP_Rock_Glacial_Inst` | MaterialInstance | 0.09 |  |  | B40,C45 | no |  |
| `/Game/Env/Bio/Rock/Glacial/Rock_Glacial_Icecave_C/SM_Rock_Glacial_Icecave_C` | StaticMesh | 7.72 | 275,377 | 61.58x58.22x60.19 | B40,C45 | no |  |
| `/Game/Env/Bio/Rock/Glacial/Rock_Glacial_Lrg_A/Materials/MI_Rock_Glacial_Lrg_A` | MaterialInstance | 0.19 |  |  | B40,C45 | no |  |
| `/Game/Env/Bio/Rock/Glacial/Rock_Glacial_Lrg_A/SM_Rock_Glacial_Lrg_A` | StaticMesh | 4.30 | 109,123 | 9.3x9.76x8.63 | B40,C45 | yes |  |
| `/Game/Env/Bio/Rock/Glacial/Rock_Glacial_Lrg_B/Materials/MI_Rock_AllSnow` | MaterialInstance | 0.09 |  |  | B40,C45 | listed | snow variant |
| `/Game/Env/Bio/Rock/Glacial/Rock_Glacial_Lrg_B/Materials/MI_Rock_Glacial_Lrg_B` | MaterialInstance | 0.09 |  |  | B40,C20,C45 | no | sibling used by PWR |
| `/Game/Env/Bio/Rock/Glacial/Rock_Glacial_Lrg_B/Materials/MI_Rock_Glacial_Lrg_B_NoSnow` | MaterialInstance | 0.19 |  |  | B40,C45 | yes | snow-free variant |
| `/Game/Env/Bio/Rock/Glacial/Rock_Glacial_Lrg_B/SM_Rock_Glacial_Lrg_B` | StaticMesh | 4.28 | 109,962 | 11.49x14.92x8.87 | B40,C20,C45 | yes |  |
| `/Game/Env/Bio/Rock/Glacial/Rock_Glacial_Lrg_C/Materials/MI_Rock_Glacial_Lrg_C` | MaterialInstance | 0.09 |  |  | B40,C20,C45 | no | sibling used by PWR |
| `/Game/Env/Bio/Rock/Glacial/Rock_Glacial_Lrg_C/Materials/MI_Rock_Glacial_Lrg_C_NoSnow` | MaterialInstance | 0.19 |  |  | B40,C45 | yes | snow-free variant |
| `/Game/Env/Bio/Rock/Glacial/Rock_Glacial_Lrg_C/SM_Rock_Glacial_Lrg_C` | StaticMesh | 4.40 | 110,213 | 11.66x21.44x12.16 | B40,C20,C45 | yes |  |
| `/Game/Env/Bio/Rock/Glacial/Rock_Glacial_Med_A/Materials/MI_Rock_Glacial_Med_A` | MaterialInstance | 0.09 |  |  | B40,C45 | no | sibling used by PWR |
| `/Game/Env/Bio/Rock/Glacial/Rock_Glacial_Med_A/Materials/MI_Rock_Glacial_Med_A_NoSnow` | MaterialInstance | 0.19 |  |  | B40,C45 | yes | snow-free variant |
| `/Game/Env/Bio/Rock/Glacial/Rock_Glacial_Med_A/SM_Rock_Glacial_Med_A` | StaticMesh | 2.53 | 64,230 | 6.49x5.29x3.8 | B40,C45 | yes |  |
| `/Game/Env/Bio/Rock/Glacial/Rock_Glacial_Med_B/Materials/MI_Rock_Glacial_Med_B` | MaterialInstance | 0.19 |  |  | B40,C45 | no | sibling used by PWR |
| `/Game/Env/Bio/Rock/Glacial/Rock_Glacial_Med_B/Materials/MI_Rock_Glacial_Med_B_NoSnow` | MaterialInstance | 0.19 |  |  | B40,C45 | yes | snow-free variant |
| `/Game/Env/Bio/Rock/Glacial/Rock_Glacial_Med_B/SM_Rock_Glacial_Med_B` | StaticMesh | 3.12 | 79,802 | 4.48x3.55x2.92 | B40,C45 | yes |  |
| `/Game/Env/Bio/Rock/Glacial/Rock_Glacial_Med_C/SM_Rock_Glacial_Med_C` | StaticMesh | 2.27 | 58,594 | 5.42x4.31x2.95 | B40,C45 | yes |  |
| `/Game/Env/Bio/Rock/Glacial/Rock_Glacial_Sma_B/SM_Rock_Glacial_Sma_B` | StaticMesh | 0.53 | 17,337 | 1.35x1.7x0.26 | B40,C45 | no |  |

*Group note:* PWR's main rock family (Lrg/Med A-C); snow MIs unused so far

### PNW rocks (Env/Bio/Rock/PNW) (40)

*Where on PWR:* Mountain flanks and forest outcrops

| path | kind | MB | verts | bounds m | levels | PWR | note |
|---|---|---|---|---|---|---|---|
| `/Game/Env/Bio/Rock/PNW/+Materials/MIP_Rock_PNW_Granite_Large` | MaterialInstance | 0.28 |  |  | A30,B40,C45,E20 | no |  |
| `/Game/Env/Bio/Rock/PNW/+Materials/MIP_Rock_PNW_Granite_Large_A30` | MaterialInstance | 0.09 |  |  | A30,B40,C45,E20 | no |  |
| `/Game/Env/Bio/Rock/PNW/+Materials/MIP_Rock_PNW_Granite_Large_A30_NoStain` | MaterialInstance | 0.27 |  |  | A30 | no |  |
| `/Game/Env/Bio/Rock/PNW/MI_Rock_PNW` | MaterialInstance | 0.17 |  |  | A30 | no |  |
| `/Game/Env/Bio/Rock/PNW/PNWGL_Rock_Macro_B/BP_pnwgl_rock_macro_b` | Blueprint | 0.00 |  |  | A30 | no | sibling used by PWR |
| `/Game/Env/Bio/Rock/PNW/PNWGL_Rock_Macro_B/MI_PNWGL_Quarry_Cliff_A_PNW_Inst` | MaterialInstance | 0.27 |  |  | A30 | no | sibling used by PWR |
| `/Game/Env/Bio/Rock/PNW/PNWGL_Rock_Macro_B/MI_PNWGL_Quarry_Cliff_B_PNW_Inst` | MaterialInstance | 0.27 |  |  | A30 | no | sibling used by PWR |
| `/Game/Env/Bio/Rock/PNW/PNWGL_Rock_Macro_B/MI_PNWGL_Rock_Large_A_FOUNDRY_PNW` | MaterialInstance | 0.09 |  |  | A30 | no | sibling used by PWR |
| `/Game/Env/Bio/Rock/PNW/PNWGL_Rock_Macro_B/MI_PNWGL_Rock_Macro_B` | MaterialInstance | 0.29 |  |  | A30,B40,C45,E20 | listed |  |
| `/Game/Env/Bio/Rock/PNW/PNWGL_Rock_Macro_B/MI_PNWGL_Rock_Macro_B_Dark_Granite` | MaterialInstance | 0.21 |  |  | B40,C45 | no | sibling used by PWR |
| `/Game/Env/Bio/Rock/PNW/PNWGL_Rock_Macro_B/MI_PNWGL_Rock_Macro_B_FOUNDRY_PNW` | MaterialInstance | 0.09 |  |  | A30 | no | sibling used by PWR |
| `/Game/Env/Bio/Rock/PNW/PNWGL_Rock_Macro_B/MI_PNWGL_Rock_Macro_B_NoGrass_NoStain_Inheritance` | MaterialInstance | 0.28 |  |  | A30 | no | sibling used by PWR |
| `/Game/Env/Bio/Rock/PNW/PNWGL_Rock_Macro_B/MI_PNWGL_Rock_Macro_B_NoGrass_NoStain_NoInheritance` | MaterialInstance | 0.28 |  |  | A30 | no | sibling used by PWR |
| `/Game/Env/Bio/Rock/PNW/PNWGL_Rock_Macro_B/MI_PNWGL_Rock_Macro_B_NoStain` | MaterialInstance | 0.28 |  |  | A30 | no | sibling used by PWR |
| `/Game/Env/Bio/Rock/PNW/PNWGL_Rock_Macro_B/MI_PNWGL_Rock_Macro_B_Snow` | MaterialInstance | 0.22 |  |  | B40,C45 | no | snow variant; sibling used by PWR |
| `/Game/Env/Bio/Rock/PNW/PNWGL_Rock_Macro_B/MI_PNWGL_Rock_Macro_B_Vista_A30` | MaterialInstance | 0.31 |  |  | A30 | no | sibling used by PWR |
| `/Game/Env/Bio/Rock/PNW/PNWGL_Rock_Macro_B/MI_PNWGL_Rock_Macro_B_Wet` | MaterialInstance | 0.09 |  |  |  | no | wet variant; sibling used by PWR |
| `/Game/Env/Bio/Rock/PNW/PNWGL_Rock_Macro_B/MI_PNWGL_Rock_Macro_B_ZGradient` | MaterialInstance | 0.09 |  |  | A30 | no | sibling used by PWR |
| `/Game/Env/Bio/Rock/PNW/PNWGL_Rock_Macro_B/SM_PNWGL_Rock_Macro_B` | StaticMesh | 11.00 | 227,070 | 214.52x164.52x256.75 | A30,B40,C45,E20 | yes |  |
| `/Game/Env/Bio/Rock/PNW/PNWGL_Rock_Macro_B/SM_pnwgl_rock_macro_b_MRR` | StaticMesh | 9.56 | 226,836 | 214.54x164.49x256.75 | A30,E20 | no | sibling used by PWR |
| `/Game/Env/Bio/Rock/PNW/Rock_Large_A/MI_Rock_PNW_Large_A` | MaterialInstance | 0.00 |  |  | A30,B40,C45 | no |  |
| `/Game/Env/Bio/Rock/PNW/Rock_Large_A/MI_Rock_PNW_Large_A_Inheritance` | MaterialInstance | 0.27 |  |  | A30 | no |  |
| `/Game/Env/Bio/Rock/PNW/Rock_Large_A/MI_Rock_PNW_Large_A_NoGrass` | MaterialInstance | 0.26 |  |  | A30 | no |  |
| `/Game/Env/Bio/Rock/PNW/Rock_Large_A/MI_Rock_PNW_Large_A_NoGrass_NoStain_Inheritance` | MaterialInstance | 0.28 |  |  | A30 | no |  |
| `/Game/Env/Bio/Rock/PNW/Rock_Large_A/MI_Rock_PNW_Large_A_NoGrass_NoStain_NoInheritance` | MaterialInstance | 0.28 |  |  | A30 | no |  |
| `/Game/Env/Bio/Rock/PNW/Rock_Large_A/MI_Rock_PNW_Large_A_NoStain` | MaterialInstance | 0.00 |  |  | A30 | no |  |
| `/Game/Env/Bio/Rock/PNW/Rock_Large_A/MI_Rock_PNW_Large_A_Snow` | MaterialInstance | 0.22 |  |  | B40,C45 | no | snow variant |
| `/Game/Env/Bio/Rock/PNW/Rock_Large_A/MI_Rock_PNW_Large_A_ZGradient` | MaterialInstance | 0.09 |  |  | A30 | no |  |
| `/Game/Env/Bio/Rock/PNW/Rock_Large_A/SM_PNWGL_Rock_Large_A` | StaticMesh | 4.07 | 84,929 | 2.35x3.31x8.81 | A30,B40,C45 | no |  |
| `/Game/Env/Bio/Rock/PNW/Rock_PNW_Lrg_A/Materials/MI_Rock_PNW_Lrg_A` | MaterialInstance | 0.21 |  |  | A30 | yes |  |
| `/Game/Env/Bio/Rock/PNW/Rock_PNW_Lrg_A/Materials/MI_Rock_PNW_Lrg_A_NoInherit` | MaterialInstance | 0.20 |  |  | A30 | no | sibling used by PWR |
| `/Game/Env/Bio/Rock/PNW/Rock_PNW_Lrg_A/SM_Rock_PNW_Lrg_A` | StaticMesh | 2.67 | 66,811 | 9.3x9.76x8.63 | A30 | no |  |
| `/Game/Env/Bio/Rock/PNW/Rock_Ramp_A/MI_Rock_PNW_Ramp_A` | MaterialInstance | 0.09 |  |  | A30 | no |  |
| `/Game/Env/Bio/Rock/PNW/Rock_Ramp_A/SM_Rock_Ramp_A_hi_UV_transferred` | StaticMesh | 2.28 | 49,494 | 2.49x4.46x2.17 | A30 | no |  |

Textures: `/Game/Env/Bio/Rock/PNW/Boulder_A/Textures/T_Pnwgl_rock_boulder_a_macro_D` (3.2 MB), `/Game/Env/Bio/Rock/PNW/PNWGL_Rock_Macro_B/Materials/T_PNWGL_Rock_Macro_B_D` (3.2 MB), `/Game/Env/Bio/Rock/PNW/Rock_Large_A/T_PNWGL_Rock_large_a_D` (3.2 MB), `/Game/Env/Bio/Rock/PNW/Rock_Ramp_A/T_pnwgl_rock_ramp_a_D` (3.2 MB), `/Game/Env/Bio/Rock/PNW/Textures/PNW_Rock_Rough/T_Rough_Rock_xbkgbab_D` (3.2 MB), `/Game/Env/Bio/Rock/PNW/Textures/PNW_Rock_Rough/T_Rough_Rock_xbkgbab_ORHG` (6.4 MB)

*Group note:* Pacific-northwest rock set; Rock_PNW_Lrg_A MI and PNWGL_Rock_Macro_B used

### Env/Bio vista (volcano) (2)

*Where on PWR:* Not a fit (volcano backdrop)

| path | kind | MB | verts | bounds m | levels | PWR | note |
|---|---|---|---|---|---|---|---|
| `/Game/Env/Bio/Vista/MIP_Bio_Vista_Volcano` | MaterialInstance | 0.16 |  |  | B30 | no |  |
| `/Game/Env/Bio/Vista/SM_Bio_Vista_Volcano` | StaticMesh | 0.25 | 4,554 | 92.31x70.27x37.29 | B30 | no |  |

*Group note:* Single volcano vista mesh

### Sky domes and cloud textures (Env/SkyBox, Lighting/Clouds) (132)

*Where on PWR:* Sky

| path | kind | MB | verts | bounds m | levels | PWR | note |
|---|---|---|---|---|---|---|---|
| `/Game/Env/SkyBox/BP/PlanetGlasser/Material/MI_GlassingCrater` | MaterialInstance | 0.00 |  |  | E30 | no |  |
| `/Game/Env/SkyBox/BP/PlanetGlasser/Material/M_GlassingCrater` | Material | 0.02 |  |  | E10,E30 | no |  |
| `/Game/Env/SkyBox/BP/PlanetGlasser/MaterialFunction/MF_CraterStorm` | MaterialFunction | 0.00 |  |  | E10,E30 | no |  |
| `/Game/Env/SkyBox/BP/PlanetGlasser/MaterialFunction/MF_ExtendChannelIntoVector` | MaterialFunction | 0.00 |  |  | E10,E30 | no |  |
| `/Game/Env/SkyBox/BP/PlanetGlasser/MaterialFunction/MF_Flowmaps_Alt` | MaterialFunction | 0.00 |  |  | E10,E30 | no |  |
| `/Game/Env/SkyBox/BP/PlanetGlasser/MaterialFunction/MF_Glistering` | MaterialFunction | 0.00 |  |  | E10,E30 | no |  |
| `/Game/Env/SkyBox/BP_Planet_Basis_v2` | Blueprint | 0.00 |  |  | A15,A30,A50,B30,C45,D20,D40 | no |  |
| `/Game/Env/SkyBox/BP_Planet_EMission` | Blueprint | 0.01 |  |  | E10,E30 | no |  |
| `/Game/Env/SkyBox/BP_Planet_v2` | Blueprint | 0.02 |  |  | A15,A30,A50,B30,C45,D20,D40 | no |  |
| `/Game/Env/SkyBox/BP_Planet_v2_Threshold` | Blueprint | 0.00 |  |  | A15,A30,A50,B30,D20,D40 | no |  |
| `/Game/Env/SkyBox/Materials/MF/MF_Env_Skybox_CloudMovement` | MaterialFunction | 0.00 |  |  | E10,E30 | no |  |
| `/Game/Env/SkyBox/Materials/MF/MF_Env_Skybox_PromiseEmissive` | MaterialFunction | 0.00 |  |  | E10,E30 | no |  |
| `/Game/Env/SkyBox/Materials/MF/MF_Env_Skybox_PromiseLandShadow` | MaterialFunction | 0.00 |  |  | E10,E30 | no |  |
| `/Game/Env/SkyBox/Materials/MF/MF_Env_Skybox_PromiseOcean` | MaterialFunction | 0.00 |  |  | E10,E30 | no |  |
| `/Game/Env/SkyBox/Materials/MF/MF_Env_Skybox_PromiseSurface` | MaterialFunction | 0.00 |  |  | E10,E30 | no |  |
| `/Game/Env/SkyBox/Materials/MF/MF_Env_Skybox_Promise_GetCustomData` | MaterialFunction | 0.00 |  |  | E10,E30 | no |  |
| `/Game/Env/SkyBox/Materials/MF/MF_Env_Skybox_Promise_SetCustomData` | MaterialFunction | 0.00 |  |  | E10,E30 | no |  |
| `/Game/Env/SkyBox/Materials/MF/MF_NoiseWrapUV` | MaterialFunction | 0.00 |  |  | E10,E30 | no |  |
| `/Game/Env/SkyBox/Materials/MF/MF_UVTilingOffset` | MaterialFunction | 0.00 |  |  | A15,E10,E30 | no |  |
| `/Game/Env/SkyBox/Materials/MF/MLBM_Env_Skybox_PromiseOpacityBlend` | MaterialLayerBlend | 0.00 |  |  | E10,E30 | no |  |
| `/Game/Env/SkyBox/Materials/MF/MLI_Env_Skybox_ScorchedGround` | MaterialLayerInstance | 0.00 |  |  | E10,E30 | no |  |
| `/Game/Env/SkyBox/Materials/MF/MLM_Env_Skybox_Hurricane` | MaterialLayer | 0.00 |  |  | E10,E30 | no |  |
| `/Game/Env/SkyBox/Materials/MF/MLM_Env_Skybox_PromiseMask` | MaterialLayer | 0.00 |  |  | E10,E30 | no |  |
| `/Game/Env/SkyBox/Materials/MF/MLM_Env_Skybox_ScorchedGround` | MaterialLayer | 0.00 |  |  | E10,E30 | no |  |
| `/Game/Env/SkyBox/Materials/MF/MLM_SimpleCloud` | MaterialLayer | 0.00 |  |  | E10,E30 | no |  |
| `/Game/Env/SkyBox/Materials/MF_FlowMaps_Planet` | MaterialFunction | 0.00 |  |  | A15,A30,A50,B30,C45,D20,D40 | no |  |
| `/Game/Env/SkyBox/Materials/MF_FlowMaps_Planet_3Blend` | MaterialFunction | 0.00 |  |  | A15,A30,A50,B30,C45,D20,D40 | no |  |
| `/Game/Env/SkyBox/Materials/MF_Planet_Shadow` | MaterialFunction | 0.00 |  |  | A15,A30,A50,B30,C45,D20,D40 | no |  |
| `/Game/Env/SkyBox/Materials/MF_SampleCurveAtlas` | MaterialFunction | 0.00 |  |  | A15,A30,A50,B30,C45,D20,D40 | no |  |
| `/Game/Env/SkyBox/Materials/MI_Atmosphere_Threshold_A15` | MaterialInstance | 0.00 |  |  | A15,A30,A50,B30,C45,D20,D40 | no |  |
| `/Game/Env/SkyBox/Materials/MI_Aurora_A15` | MaterialInstance | 0.00 |  |  | A15,A30,A50,B30,C45,D20,D40 | no |  |
| `/Game/Env/SkyBox/Materials/MI_Aurora_A30` | MaterialInstance | 0.00 |  |  | A30 | no |  |
| `/Game/Env/SkyBox/Materials/MI_Aurora_A50` | MaterialInstance | 0.00 |  |  | A50 | no |  |
| `/Game/Env/SkyBox/Materials/MI_Aurora_B30` | MaterialInstance | 0.00 |  |  | B30 | no |  |
| `/Game/Env/SkyBox/Materials/MI_Basis_A15` | MaterialInstance | 0.01 |  |  | A15,A30,A50,B30,C45,D20,D40 | no |  |
| `/Game/Env/SkyBox/Materials/MI_Basis_A30` | MaterialInstance | 0.01 |  |  | A30,A50,B30,C45,D20,D40 | no |  |
| `/Game/Env/SkyBox/Materials/MI_Env_SkyBox_GlowRainBow` | MaterialInstance | 0.01 |  |  | A15,A30,A50,B30,C45,D20,D40 | no |  |
| `/Game/Env/SkyBox/Materials/MI_Env_SkyBox_GlowRainBow_A15` | MaterialInstance | 0.01 |  |  | A15,A30,A50,B30,C45,D20,D40 | no |  |
| `/Game/Env/SkyBox/Materials/MI_Env_SkyBox_GlowRainBow_A50` | MaterialInstance | 0.01 |  |  | A50 | no |  |
| `/Game/Env/SkyBox/Materials/MI_Env_SkyBox_RainBowAurora_FX_A15` | MaterialInstance | 0.01 |  |  | A15,A30,A50,B30,C45,D20,D40 | no |  |
| `/Game/Env/SkyBox/Materials/MI_Env_SkyBox_RainBowAurora_FX_A30` | MaterialInstance | 0.01 |  |  | A30 | no |  |
| `/Game/Env/SkyBox/Materials/MI_Env_SkyBox_RainBowAurora_FX_A50` | MaterialInstance | 0.01 |  |  | A50 | no |  |
| `/Game/Env/SkyBox/Materials/MI_Env_SkyBox_RainBowAurora_FX_B30` | MaterialInstance | 0.01 |  |  | B30 | no |  |
| `/Game/Env/SkyBox/Materials/MI_Planet_Atmosphere_Basis_A15` | MaterialInstance | 0.00 |  |  | A15,A30,A50,B30,C45,D20,D40 | no |  |
| `/Game/Env/SkyBox/Materials/MI_Planet_Threshold_A15` | MaterialInstance | 0.01 |  |  | A15,A30,A50,B30,C45,D20,D40 | no |  |
| `/Game/Env/SkyBox/Materials/MM_Env_Skybox_PromiseSurface` | Material | 0.03 |  |  | E10,E30 | no |  |
| `/Game/Env/SkyBox/Materials/M_Aurora` | Material | 0.01 |  |  | A15,A30,A50,B30,C45,D20,D40 | no |  |
| `/Game/Env/SkyBox/Materials/M_Env_SkyBox_RainBowAurora` | Material | 0.01 |  |  | A15,A30,A50,B30,C45,D20,D40 | no |  |
| `/Game/Env/SkyBox/Materials/M_NonNanite` | Material | 0.00 |  |  | A15,A30,A50,B30,C45,D20,D40 | no |  |
| `/Game/Env/SkyBox/Materials/M_Planet` | Material | 0.01 |  |  | A15,A30,A50,B30,C45,D20,D40 | no |  |
| `/Game/Env/SkyBox/Materials/M_Planet2` | Material | 0.01 |  |  | A15,A30,A50,B30,C45,D20,D40 | no |  |
| `/Game/Env/SkyBox/Materials/M_Planet_Atmosphere_v2` | Material | 0.01 |  |  | A15,A30,A50,B30,C45,D20,D40 | no |  |
| `/Game/Env/SkyBox/SM_Aurora` | StaticMesh | 0.90 | 13,496 | 2.03x2.03x0.97 | A15,A30,A50,B30,C45,D20,D40 | no |  |
| `/Game/Env/SkyBox/SM_AuroraRainBow` | StaticMesh | 0.01 | 52 | 0.06x1.39x0.36 | A15,A30,A50,B30,C45,D20,D40 | no |  |
| `/Game/Env/SkyBox/SM_Basis_HS` | StaticMesh | 0.30 | 6,878 | 2.0x2.0x2.0 | A15,A30,A50,B30,C45,D20,D40 | no |  |
| `/Game/Env/SkyBox/SM_Sphere_64Seg` | StaticMesh | 0.86 | 4,223 | 2.0x2.0x2.0 | A15,A30,A50,B30,C45,D20,D40 | no |  |
| `/Game/Env/SkyBox/SM_Threshold` | StaticMesh | 0.15 | 4,352 | 2.0x2.0x2.0 | A15,A30,A50,B30,C45,D20,D40 | no |  |
| `/Game/Env/SkyBox/SkyDome/BP_UltraSky` | Blueprint | 0.01 |  |  | A15,A30,A50,B30,B40,C45,D20,D40,E10,E30 | no |  |
| `/Game/Env/SkyBox/SkyDome/E20_Sky/MF_Select4Vector2DWithWeightedRange` | MaterialFunction | 0.00 |  |  | E20 | no |  |
| `/Game/Env/SkyBox/SkyDome/E20_Sky/MI_Sky_E20` | MaterialInstance | 0.02 |  |  | E20 | no |  |
| `/Game/Env/SkyBox/SkyDome/E20_Sky/M_Sky_E20` | Material | 0.03 |  |  | E20 | no |  |
| `/Game/Env/SkyBox/SkyDome/E20_Sky/SM_E20_Skydome` | StaticMesh | 3.42 | 7,945 | 140.17x140.14x73.88 | E20 | no |  |
| `/Game/Env/SkyBox/SkyDome/E20_Sky/TC_CloudBake_E20_NoStars_HDR` | TextureCube | 16.78 |  |  | E20 | no |  |
| `/Game/Env/SkyBox/SkyDome/E20_Sky/TC_Cloud_E20` | TextureCube | 8.39 |  |  | E20 | no |  |
| `/Game/Env/SkyBox/SkyDome/E30_Sky/MI_E30_Skybox` | MaterialInstance | 0.06 |  |  | E10,E30 | no |  |
| `/Game/Env/SkyBox/SkyDome/E30_Sky/Meshes/SM_E30_Skybox` | StaticMesh | 0.07 | 1,126 | 73.59x73.59x6.99 | E10,E30 | no |  |
| `/Game/Env/SkyBox/SkyDome/SM_Sphere_FlipNormal_100cm` | StaticMesh | 0.03 | 559 | 2.0x2.0x2.0 | A15,A30,A50,B30,B40,C45,D20,D40,E10,E30 | no |  |
| `/Game/Env/SkyBox/SkyDome/Universe/MF_CustomTiling` | MaterialFunction | 0.00 |  |  | A15,A30,A50,B30,B40,C45,D20,D40,E10,E30 | no |  |
| `/Game/Env/SkyBox/SkyDome/Universe/MF_ProceduralStarSky` | MaterialFunction | 0.00 |  |  | A15,A30,A50,B30,B40,C45,D20,D40,E10,E30 | no |  |
| `/Game/Env/SkyBox/SkyDome/Universe/MI_Universe_A15` | MaterialInstance | 0.02 |  |  | A15,A30,A50,B30,B40,C45,D20,D40,E10,E30 | no |  |
| `/Game/Env/SkyBox/SkyDome/Universe/MI_Universe_A30` | MaterialInstance | 0.02 |  |  | A30 | no |  |
| `/Game/Env/SkyBox/SkyDome/Universe/MI_Universe_A50` | MaterialInstance | 0.00 |  |  | A50 | no |  |
| `/Game/Env/SkyBox/SkyDome/Universe/MI_Universe_B30` | MaterialInstance | 0.02 |  |  | B30 | no |  |
| `/Game/Env/SkyBox/SkyDome/Universe/MI_Universe_B40` | MaterialInstance | 0.01 |  |  | B40 | no |  |
| `/Game/Env/SkyBox/SkyDome/Universe/MI_Universe_C45` | MaterialInstance | 0.00 |  |  | C45 | no |  |
| `/Game/Env/SkyBox/SkyDome/Universe/MI_Universe_D20` | MaterialInstance | 0.00 |  |  | D20 | no |  |
| `/Game/Env/SkyBox/SkyDome/Universe/MI_Universe_D40` | MaterialInstance | 0.00 |  |  | D40 | no |  |
| `/Game/Env/SkyBox/SkyDome/Universe/MI_Universe_E10` | MaterialInstance | 0.02 |  |  | E10 | no |  |
| `/Game/Env/SkyBox/SkyDome/Universe/MI_Universe_E30` | MaterialInstance | 0.02 |  |  | E30 | no |  |
| `/Game/Env/SkyBox/SkyDome/Universe/M_Universe` | Material | 0.02 |  |  | A15,A30,A50,B30,B40,C45,D20,D40,E10,E30 | no |  |
| `/Game/Levels/Halo1/Solo/B30/Materials/Clouds/MF_B30_CloudNoiseBuilder` | MaterialFunction | 0.00 |  |  | B30 | no |  |
| `/Game/Levels/Halo1/Solo/B30/Materials/Clouds/MF_B30_NoiseSampler` | MaterialFunction | 0.00 |  |  | B30,D40 | no |  |
| `/Game/Levels/Halo1/Solo/B30/Materials/Clouds/MI_B30_Clouds` | MaterialInstance | 0.00 |  |  | B30 | no |  |
| `/Game/Levels/Halo1/Solo/B30/Materials/Clouds/M_B30_Clouds` | Material | 0.04 |  |  | B30 | no |  |
| `/Game/Lighting/Clouds/T_PerlinWorley_Balanced` | VolumeTexture | 8.39 |  |  | A15,A30,A50,B30,B40,C10,C20,C45,D20,D40,E10,E20,E30 | no |  |

Textures: `/Game/Env/SkyBox/BP/PlanetGlasser/Blueprint/T_E30_Base_Mask_1` (1.7 MB), `/Game/Env/SkyBox/BP/PlanetGlasser/Blueprint/T_E30_Crater_Mask1` (1.7 MB), `/Game/Env/SkyBox/BP/PlanetGlasser/Blueprint/T_E30_Hurricane_Mask1` (1.7 MB), `/Game/Env/SkyBox/BP/PlanetGlasser/Blueprint/T_E30__Mask_0` (6.8 MB), `/Game/Env/SkyBox/BP/PlanetGlasser/Blueprint/T_E30__Mask_1` (6.8 MB), `/Game/Env/SkyBox/BP/PlanetGlasser/Texture/T_E30_InnerOuterCloudCrater_Masks` (6.8 MB), `/Game/Env/SkyBox/BP/PlanetGlasser/Texture/T_SwirlMap_d` (0.9 MB), `/Game/Env/SkyBox/Glassing/T_E30_InnerOuterCloudCrater_Masks` (101.4 MB), `/Game/Env/SkyBox/Glassing/Textures/T_E30_Skybox_RingFire_D` (3.2 MB), `/Game/Env/SkyBox/Glassing/Textures/T_E30_Skybox_RingFire_M` (6.4 MB), `/Game/Env/SkyBox/Glassing/Textures/T_E30_Skybox_RingFire_N` (6.4 MB), `/Game/Env/SkyBox/SkyDome/E20_Sky/T_Noise_BlueNoiseRGB` (0.2 MB), `/Game/Env/SkyBox/SkyDome/E20_Sky/T_Skydome_E20_Glitch_Pattern_02_d` (3.2 MB), `/Game/Env/SkyBox/SkyDome/E20_Sky/T_Skydome_E20_LEDBulb_01_d` (3.2 MB), `/Game/Env/SkyBox/SkyDome/E20_Sky/T_Skydome_E20_RandomGlitchInfo_d` (3.2 MB), `/Game/Env/SkyBox/SkyDome/E20_Sky/T_Skydome_E20_ShapeEdge_d` (3.2 MB), `/Game/Env/SkyBox/SkyDome/E20_Sky/T_Skydome_E20_WhiteNoise_01_d` (0.1 MB), `/Game/Env/SkyBox/SkyDome/E30_Sky/Textures/T_E30_Skybox_D` (50.6 MB), `/Game/Env/SkyBox/SkyDome/E30_Sky/Textures/T_E30_Skybox_M` (101.1 MB), `/Game/Env/SkyBox/SkyDome/E30_Sky/Textures/T_E30_Skybox_NNRH` (101.1 MB), `/Game/Env/SkyBox/SkyDome/Universe/T_Nebula_Butterfly_01` (0.7 MB), `/Game/Env/SkyBox/SkyDome/Universe/T_Nebula_Eye_01` (1.4 MB), `/Game/Env/SkyBox/SkyDome/Universe/T_Nebula_Guardian_01` (1.4 MB), `/Game/Env/SkyBox/SkyDome/Universe/T_Nebula_Styx_01` (1.4 MB), `/Game/Env/SkyBox/SkyDome/Universe/T_Skydome_Starscape_01` (0.5 MB), `/Game/Env/SkyBox/Textures/T_AuroraRay_D` (0.9 MB), `/Game/Env/SkyBox/Textures/T_Basis_HS_D` (25.4 MB), `/Game/Env/SkyBox/Textures/T_Basis_HS_N` (6.4 MB), `/Game/Env/SkyBox/Textures/T_Basis_HS_R` (12.7 MB), `/Game/Env/SkyBox/Textures/T_CircleSoft_D_02` (0.5 MB), `/Game/Env/SkyBox/Textures/T_ColorGradAurora_D` (3.2 MB), `/Game/Env/SkyBox/Textures/T_Default_NNRH` (0.1 MB), `/Game/Env/SkyBox/Textures/T_Default_WindMap` (2.1 MB), `/Game/Env/SkyBox/Textures/T_Flowmap_1x1` (0.1 MB), `/Game/Env/SkyBox/Textures/T_Grad_VertBoxSoft_Clamped_D_02` (0.3 MB), `/Game/Env/SkyBox/Textures/T_Skybox_E30_Cloud_M` (12.7 MB), `/Game/Env/SkyBox/Textures/T_Skybox_E30_Cloud_NNH` (25.4 MB), `/Game/Env/SkyBox/Textures/T_Threshold_N` (6.4 MB), `/Game/Env/SkyBox/Textures/T_Threshold_New_D` (25.4 MB), `/Game/Env/SkyBox/Textures/T_Threshold_Updated_D` (25.4 MB), `/Game/Env/SkyBox/Textures/T_Threshold_Updated_N` (6.4 MB), `/Game/Lighting/Clouds/CloudTextures/T_PNW_Sun_Cloudshadows_Tiled` (0.4 MB), `/Game/Lighting/Clouds/CloudTextures/T_PNW_Sun_Cloudshadows_TiledDuplicated` (1.0 MB), `/Game/Lighting/Clouds/Collection/T_Cloud2dNoise2` (5.6 MB), `/Game/Lighting/Clouds/Collection/T_Cloud2dNoise3` (22.4 MB), `/Game/Lighting/Clouds/T_Cloud2dNoise7` (11.2 MB), `/Game/Lighting/Clouds/T_CloudMask2` (1.4 MB)

*Group note:* Shipped sky domes, planets, cloud cards and B30 cloud material

### Vista mountains and backdrops (64)

*Where on PWR:* Ring of distant mountains outside the play space

| path | kind | MB | verts | bounds m | levels | PWR | note |
|---|---|---|---|---|---|---|---|
| `/Game/Levels/Halo1/Solo/A30/Landscape/Vista/CloudSea/SM_Gigantic_Sandstone_Terrain_wldhdhxva_high_Var2` | StaticMesh | 13.94 | 400,191 | 576.07x365.39x107.66 | A30 | no | very dense: confirm Nanite before placing many |
| `/Game/Levels/Halo1/Solo/A50/Landscape/Vista/Materials/MI_Rock_Desert_Cliff_Vista` | MaterialInstance | 0.19 |  |  | A50 | no |  |
| `/Game/Levels/Halo1/Solo/A50/Landscape/Vista/Materials/MI_Rock_Desert_Cliff_Vista_Base` | MaterialInstance | 0.19 |  |  | A50 | no |  |
| `/Game/Levels/Halo1/Solo/A50/Landscape/Vista/Materials/MI_Rock_Desert_Cliff_Vista_Far` | MaterialInstance | 0.17 |  |  | A50,D20 | no |  |
| `/Game/Levels/Halo1/Solo/A50/Landscape/Vista/Materials/MI_Rock_Desert_Cliff_Vista_Near` | MaterialInstance | 0.18 |  |  | A50 | no |  |
| `/Game/Levels/Halo1/Solo/A50/Landscape/Vista/Materials/MI_Rock_Desert_Cliff_Vista_Near_Top` | MaterialInstance | 0.17 |  |  | A50 | no |  |
| `/Game/Levels/Halo1/Solo/A50/Landscape/Vista/Rock_Desert_Vista_A/Materials/MI_Rock_Desert_Vista_A` | MaterialInstance | 0.25 |  |  | A50 | no |  |
| `/Game/Levels/Halo1/Solo/A50/Landscape/Vista/Rock_Desert_Vista_A/SM_Rock_Desert_Vista_A` | StaticMesh | 7.54 | 151,916 | 200.04x200.02x40.03 | A50,D20 | no |  |
| `/Game/Levels/Halo1/Solo/A50/Landscape/Vista/Rock_Desert_Vista_B/Materials/MI_Rock_Desert_Vista_Mountain_B` | MaterialInstance | 0.26 |  |  | A50,D20 | no |  |
| `/Game/Levels/Halo1/Solo/A50/Landscape/Vista/Rock_Desert_Vista_B/SM_Rock_Desert_Vista_Base` | StaticMesh | 10.65 | 312,566 | 100.0x100.0x8.67 | A50,D20 | no |  |
| `/Game/Levels/Halo1/Solo/A50/Landscape/Vista/Rock_Desert_Vista_B/SM_Rock_Desert_Vista_Mountain_B` | StaticMesh | 1.07 | 31,494 | 84.35x79.08x14.76 | A50,D20 | no |  |
| `/Game/Levels/Halo1/Solo/A50/Landscape/Vista/Rock_Desert_Vista_B/SM_Rock_Desert_Vista_Mountain_B_Low` | StaticMesh | 0.03 | 602 | 83.45x78.78x15.02 | A50 | no |  |
| `/Game/Levels/Halo1/Solo/C20/Landscape/Vista/MIP_SnowyMountain_Vista` | MaterialInstance | 0.22 |  |  | C20 | no | snow variant |
| `/Game/Levels/Halo1/Solo/C20/Landscape/Vista/MI_FR_Metal_Diagonal_01_A_Light_Rough3_High_VCol_Frost_Vista` | MaterialInstance | 0.32 |  |  | C20 | no |  |
| `/Game/Levels/Halo1/Solo/C20/Landscape/Vista/SM_Library_Silhouette` | StaticMesh | 5.84 | 191,345 | 69.28x69.28x34.45 | C20 | no |  |
| `/Game/Levels/Halo1/Solo/C20/Landscape/Vista/SM_SnowyMountain_Vista_01` | StaticMesh | 7.75 | 237,839 | 499.92x499.92x147.63 | C20 | no | snow variant |
| `/Game/Levels/Halo1/Solo/D20/Landscape/Vista/Materials/MI_Rock_Canyon_Vista_Crevice` | MaterialInstance | 0.09 |  |  | D20 | no |  |
| `/Game/Levels/Halo1/Solo/D20/Landscape/Vista/Materials/MI_Rock_Canyon_Vista_Grikes_A` | MaterialInstance | 0.29 |  |  | D20 | no |  |
| `/Game/Levels/Halo1/Solo/D20/Landscape/Vista/Materials/MI_Rock_Canyon_Vista_Rubble_A` | MaterialInstance | 0.28 |  |  | D20 | no |  |
| `/Game/Levels/Halo1/Solo/D40/Landscape/Vista/Flattop_01/MI_MawVista_Flattops_01` | MaterialInstance | 0.21 |  |  | D40 | no |  |
| `/Game/Levels/Halo1/Solo/D40/Landscape/Vista/Flattop_01/SM_MawVista_Flattop_01` | StaticMesh | 0.55 | 15,532 | 516.67x506.65x102.78 | D40 | no |  |
| `/Game/Levels/Halo1/Solo/D40/Landscape/Vista/Flattop_04/MI_MawVista_Flattop_04` | MaterialInstance | 0.21 |  |  | D40 | no |  |
| `/Game/Levels/Halo1/Solo/D40/Landscape/Vista/Flattop_04/MI_MawVista_Flattop_NoInheritance_04` | MaterialInstance | 0.20 |  |  | D40 | no |  |
| `/Game/Levels/Halo1/Solo/D40/Landscape/Vista/Flattop_04/SM_MawVista_Flatop_04` | StaticMesh | 0.67 | 18,956 | 516.12x515.13x100.74 | D40 | no |  |
| `/Game/Levels/Halo1/Solo/D40/Landscape/Vista/Flattop_05/MI_MawVista_Flattop_05` | MaterialInstance | 0.21 |  |  | D40 | no |  |
| `/Game/Levels/Halo1/Solo/D40/Landscape/Vista/Flattop_05/SM_MawVista_Flatop_05` | StaticMesh | 0.94 | 17,613 | 508.63x509.25x94.34 | D40 | no |  |
| `/Game/Levels/Halo1/Solo/D40/Landscape/Vista/MIP_MawVista_Flattop` | MaterialInstance | 0.22 |  |  | D40 | no |  |
| `/Game/Levels/Halo1/Solo/D40/Landscape/Vista/MIP_SandDunes_Vista` | MaterialInstance | 0.20 |  |  | D40 | no |  |
| `/Game/Levels/Halo1/Solo/D40/Landscape/Vista/MI_SandDunes_Vista_01` | MaterialInstance | 0.14 |  |  | D40 | no |  |
| `/Game/Levels/Halo1/Solo/D40/Landscape/Vista/MI_SandDunes_Vista_03` | MaterialInstance | 0.14 |  |  | D40 | no |  |
| `/Game/Levels/Halo1/Solo/D40/Landscape/Vista/MawEdge/MI_MawVista_Edge` | MaterialInstance | 0.21 |  |  | D40 | no |  |
| `/Game/Levels/Halo1/Solo/D40/Landscape/Vista/MawEdge/SM_MawEdge_02V2` | StaticMesh | 4.33 | 132,646 | 10.0x5.15x1.23 | D40 | no |  |
| `/Game/Levels/Halo1/Solo/D40/Landscape/Vista/SM_ReverseBacking` | StaticMesh | 0.00 | 20 | 27.56x27.56x27.56 | D40 | no |  |
| `/Game/Levels/Halo1/Solo/D40/Landscape/Vista/SandDunes/MI_SandDunes_Vista_02` | MaterialInstance | 0.08 |  |  | D40 | no |  |
| `/Game/Levels/Halo1/Solo/D40/Landscape/Vista/SandDunes/MI_SandDunes_Vista_03` | MaterialInstance | 0.08 |  |  | D40 | no |  |
| `/Game/Levels/Halo1/Solo/D40/Landscape/Vista/SandDunes/SM_Gaea_SandDune` | StaticMesh | 0.19 | 4,389 | 4033.29x4033.29x234.81 | D40 | no |  |

Textures: `/Game/Levels/Halo1/Solo/A50/Landscape/Vista/Materials/T_Rock_Desert_Cliff_Vista_Near` (6.4 MB), `/Game/Levels/Halo1/Solo/A50/Landscape/Vista/Rock_Desert_Vista_A/Materials/T_Rock_Desert_Vista_A` (3.2 MB), `/Game/Levels/Halo1/Solo/A50/Landscape/Vista/Rock_Desert_Vista_A/Materials/T_Rock_Desert_Vista_A_ORHG` (6.4 MB), `/Game/Levels/Halo1/Solo/A50/Landscape/Vista/Rock_Desert_Vista_B/Materials/T_Rock_Desert_Vista_Base_D` (3.2 MB), `/Game/Levels/Halo1/Solo/A50/Landscape/Vista/Rock_Desert_Vista_B/Materials/T_Rock_Desert_Vista_Base_N` (6.4 MB), `/Game/Levels/Halo1/Solo/C20/Landscape/Vista/T_SnowyMountain_Vista_01_D` (3.2 MB), `/Game/Levels/Halo1/Solo/C20/Landscape/Vista/T_SnowyMountain_Vista_01_M` (12.7 MB), `/Game/Levels/Halo1/Solo/C20/Landscape/Vista/T_SnowyMountain_Vista_01_N` (6.4 MB), `/Game/Levels/Halo1/Solo/D20/Landscape/Vista/Materials/T_Rock_Canyon_Vista_Crevice_D` (12.7 MB), `/Game/Levels/Halo1/Solo/D40/Landscape/Vista/Flattop_01/T_MawVista_Flattop_01_02_N` (25.4 MB), `/Game/Levels/Halo1/Solo/D40/Landscape/Vista/Flattop_01/T_MawVista_Flattop_01_Lighter_D` (3.2 MB), `/Game/Levels/Halo1/Solo/D40/Landscape/Vista/Flattop_01/T_MawVista_Flattop_01_M` (3.2 MB), `/Game/Levels/Halo1/Solo/D40/Landscape/Vista/Flattop_01/T_MawVista_Flattop_01_ORHG` (6.4 MB), `/Game/Levels/Halo1/Solo/D40/Landscape/Vista/Flattop_04/T_MawVista_Flattop_04_02_N` (25.4 MB), `/Game/Levels/Halo1/Solo/D40/Landscape/Vista/Flattop_04/T_MawVista_Flattop_04_Lighter_D` (3.2 MB), `/Game/Levels/Halo1/Solo/D40/Landscape/Vista/Flattop_04/T_MawVista_Flattop_04_M` (3.2 MB), `/Game/Levels/Halo1/Solo/D40/Landscape/Vista/Flattop_04/T_MawVista_Flattop_04_ORHG` (6.4 MB), `/Game/Levels/Halo1/Solo/D40/Landscape/Vista/Flattop_05/T_MawVista_Flatop_Lighter_05_D` (3.2 MB), `/Game/Levels/Halo1/Solo/D40/Landscape/Vista/Flattop_05/T_MawVista_Flattop_05_02_N` (25.4 MB), `/Game/Levels/Halo1/Solo/D40/Landscape/Vista/Flattop_05/T_MawVista_Flattop_05_M` (3.2 MB), `/Game/Levels/Halo1/Solo/D40/Landscape/Vista/Flattop_05/T_MawVista_Flattop_05_ORHG` (6.4 MB), `/Game/Levels/Halo1/Solo/D40/Landscape/Vista/MawEdge/T_MawEdge02_V2_N` (25.4 MB), `/Game/Levels/Halo1/Solo/D40/Landscape/Vista/MawEdge/T_MawEdge02_V2_ORHG` (3.2 MB), `/Game/Levels/Halo1/Solo/D40/Landscape/Vista/MawEdge/T_MawEdge_02_V3_D` (3.2 MB), `/Game/Levels/Halo1/Solo/D40/Landscape/Vista/SandDunes/T_Gaea_SandDune_M` (3.2 MB), `/Game/Levels/Halo1/Solo/D40/Landscape/Vista/SandDunes/T_Gaea_SandDune_N` (6.4 MB), `/Game/Levels/Halo1/Solo/D40/Landscape/Vista/SandDunes/T_Gaea_SandDune_ORGH` (6.4 MB), `/Game/Levels/Halo1/Solo/D40/Landscape/Vista/T_Sand_Macro_D` (0.7 MB)

*Group note:* Shipped backdrop meshes; C20 SM_SnowyMountain_Vista_01 is the only snowy one, desert/maw vistas need re-tint

### A30 scree assemblies (PCG recipes) (6)

*Where on PWR:* Recipe for scree fans under PWR's cliffs

| path | kind | MB | verts | bounds m | levels | PWR | note |
|---|---|---|---|---|---|---|---|
| `/Game/Levels/Halo1/Solo/A30/PCG/Assemblies/Scree/BP_ScreeAssembly_A` | Blueprint | 0.00 |  |  | A30 | no |  |
| `/Game/Levels/Halo1/Solo/A30/PCG/Assemblies/Scree/BP_ScreeAssembly_Ground_B` | Blueprint | 0.00 |  |  | A30 | no |  |
| `/Game/Levels/Halo1/Solo/A30/PCG/Assemblies/Scree/DAPCG_Scree_A` | PCGDataAsset | 0.05 |  |  | A30 | no |  |
| `/Game/Levels/Halo1/Solo/A30/PCG/Assemblies/Scree/DAPCG_Scree_Ground_B` | PCGDataAsset | 0.04 |  |  | A30 | no |  |
| `/Game/Levels/Halo1/Solo/A30/PCG/Assemblies/Scree/LI_Scree_A` | LevelInstance | 0.01 |  |  | A30 | no |  |
| `/Game/Levels/Halo1/Solo/A30/PCG/Assemblies/Scree/LI_Scree_Ground_B` | LevelInstance | 0.01 |  |  | A30 | no |  |

*Group note:* A30 LI_Scree_A / LI_Scree_Ground_B level instances + DAPCG/BP; members are the Env/Bio scree rocks

### B40 snow and ice material layers (19)

*Where on PWR:* Snowfields, frozen lake option, snow on rock

| path | kind | MB | verts | bounds m | levels | PWR | note |
|---|---|---|---|---|---|---|---|
| `/Game/Levels/Halo1/Solo/B40/Materials/IceSnow/MF/MF_Env_IceFeature_V2` | MaterialFunction | 0.00 |  |  | B40,C45 | no |  |
| `/Game/Levels/Halo1/Solo/B40/Materials/IceSnow/MF/MF_Env_SnowFeature` | MaterialFunction | 0.00 |  |  | B40,C20,C45 | no | snow variant |
| `/Game/Levels/Halo1/Solo/B40/Materials/IceSnow/MF/MF_ParallaxOcclusionMapping` | MaterialFunction | 0.00 |  |  | B40,C45 | no |  |
| `/Game/Levels/Halo1/Solo/B40/Materials/IceSnow/MF/MF_ProcedualGlint` | MaterialFunction | 0.00 |  |  | B40,C20,C45 | no |  |
| `/Game/Levels/Halo1/Solo/B40/Materials/IceSnow/MF/MF_RelaxedConeStepMapping` | MaterialFunction | 0.00 |  |  | B40,C45 | no |  |
| `/Game/Levels/Halo1/Solo/B40/Materials/IceSnow/MF/MF_ScatteringEffect` | MaterialFunction | 0.00 |  |  | B40,C45 | no |  |
| `/Game/Levels/Halo1/Solo/B40/Materials/IceSnow/MF/MF_UVSelector` | MaterialFunction | 0.00 |  |  | B40,C45 | no |  |
| `/Game/Levels/Halo1/Solo/B40/Materials/IceSnow/MIC/MI_Frozen_Glacial_Cliff_IceRock` | MaterialInstance | 0.16 |  |  | B40,C45 | no |  |
| `/Game/Levels/Halo1/Solo/B40/Materials/IceSnow/MIC/MI_Frozen_Glacial_Lake_A` | MaterialInstance | 0.44 |  |  | B40,C45 | no |  |
| `/Game/Levels/Halo1/Solo/B40/Materials/IceSnow/ML/MLM_Env_Uber_Ice_V2` | MaterialLayer | 0.00 |  |  | B40,C45 | no |  |
| `/Game/Levels/Halo1/Solo/B40/Materials/IceSnow/ML/MLM_Env_Uber_Snow` | MaterialLayer | 0.00 |  |  | B40,C20,C45 | no | snow variant |

Textures: `/Game/Levels/Halo1/Solo/B40/Materials/IceSnow/Textures/T_Frozen_Glacial_Lake_A_DetailMap_NNH` (6.4 MB), `/Game/Levels/Halo1/Solo/B40/Materials/IceSnow/Textures/T_Frozen_Glacial_Lake_A_HC_NSVT` (2.8 MB), `/Game/Levels/Halo1/Solo/B40/Materials/IceSnow/Textures/T_Frozen_Glacial_Lake_A_N` (6.4 MB), `/Game/Levels/Halo1/Solo/B40/Materials/IceSnow/Textures/T_Frozen_Glacial_Lake_A_NNHC_NSVT` (1.4 MB), `/Game/Levels/Halo1/Solo/B40/Materials/IceSnow/Textures/T_Frozen_Glacial_Lake_A_ORHG` (6.4 MB), `/Game/Levels/Halo1/Solo/B40/Materials/IceSnow/Textures/T_Ice_Default_DetailMap_NNH` (6.4 MB), `/Game/Levels/Halo1/Solo/B40/Materials/IceSnow/Textures/T_Ice_Default_HC_NSVT` (0.7 MB), `/Game/Levels/Halo1/Solo/B40/Materials/IceSnow/Textures/T_Ice_Default_NNHC_NSVT` (5.6 MB)

*Group note:* Uber snow/ice material layers with POM and procedural glint (B40)

### Snow mounds and tundra (Megascans 3D) (49)

*Where on PWR:* Snow patches on the upper slopes, tundra boulders, quarry-cut cliffs at the bases

| path | kind | MB | verts | bounds m | levels | PWR | note |
|---|---|---|---|---|---|---|---|
| `/Game/Megascans/3D_Assets/GiganticSandstoneTerrain/MI_GiganticSandstoneTerrain_01` | MaterialInstance | 0.00 |  |  | B30,C10 | no |  |
| `/Game/Megascans/3D_Assets/GiganticSandstoneTerrain/MI_GiganticSandstoneTerrain_FakeShadowing` | MaterialInstance | 0.00 |  |  | B30 | no |  |
| `/Game/Megascans/3D_Assets/GiganticSandstoneTerrain/SM_GiganticSandstoneTerrain_01` | StaticMesh | 10.22 | 251,508 | 575.95x365.39x107.57 | B30,C10 | no |  |
| `/Game/Megascans/3D_Assets/Huge_Snow_Hill_vdspdazqa/MI_Huge_Snow_Hill_vdspdazqa_High` | MaterialInstance | 0.00 |  |  | B40,C45 | no | snow variant |
| `/Game/Megascans/3D_Assets/Huge_Snow_Hill_vdspdazqa/huge_snow_hill_vdspdazqa_high` | StaticMesh | 0.31 |  |  | B40,C45 | no | snow variant |
| `/Game/Megascans/3D_Assets/Huge_Snow_Pile_vcyjaf1ga/MI_Huge_Snow_Pile_vcyjaf1ga_8K` | MaterialInstance | 0.00 |  |  | B40 | no | snow variant |
| `/Game/Megascans/3D_Assets/Icelandic_Rock_skjsK/S_Icelandic_Rock_skjsK_lod0` | StaticMesh | 0.80 | 24,531 | 1.7x1.46x0.91 | A30 | no |  |
| `/Game/Megascans/3D_Assets/Icelandic_Rock_skjsK/S_Tundra_Boulder_Snowy_3` | StaticMesh | 0.67 | 12,496 | 1.71x1.5x0.91 | B40 | no | snow variant |
| `/Game/Megascans/3D_Assets/MassiveSandstoneCliff/MI_MassiveSandstoneCliff_03` | MaterialInstance | 0.00 |  |  | C10 | no |  |
| `/Game/Megascans/3D_Assets/MassiveSandstoneCliff/MI_MassiveSandstoneCliff_03_Wet` | MaterialInstance | 0.00 |  |  | C10 | no | wet variant |
| `/Game/Megascans/3D_Assets/MassiveSandstoneCliff/SM_MassiveSandstoneCliff_03` | StaticMesh | 5.18 | 159,734 | 20.85x9.68x29.1 | C10 | no |  |
| `/Game/Megascans/3D_Assets/MassiveTundraRockFormation/MI_MassiveTundraRockFormation_02` | MaterialInstance | 0.03 |  |  | A30 | no |  |
| `/Game/Megascans/3D_Assets/MassiveTundraRockFormation/SM_MassiveTundraRockFormation_02` | StaticMesh | 5.39 | 155,348 | 29.06x20.44x6.79 | A30 | no |  |
| `/Game/Megascans/3D_Assets/Quarry_Cliff_ubhvccfda/MI_Quarry_Cliff_ubhvccfda` | MaterialInstance | 0.00 |  |  | A30 | no |  |
| `/Game/Megascans/3D_Assets/Quarry_Cliff_ubhvccfda/SM_Quarry_Cliff_ubhvccfda` | StaticMesh | 16.26 | 497,532 | 13.45x9.21x14.26 | A30 | no | very dense: confirm Nanite before placing many |
| `/Game/Megascans/3D_Assets/Quarry_Cliff_uchwaffda/MI_Quarry_Cliff_uchwaffda_4K` | MaterialInstance | 0.00 |  |  | A30 | no |  |
| `/Game/Megascans/3D_Assets/Quarry_Cliff_uchwaffda/SM_Quarry_Cliff_uchwaffda` | StaticMesh | 14.75 | 446,894 | 8.77x2.93x4.35 | A30 | no | very dense: confirm Nanite before placing many |
| `/Game/Megascans/3D_Assets/SandstoneRockyGround/MI_SandstoneRockyGround_03_E20` | MaterialInstance | 0.00 |  |  | E20 | no |  |
| `/Game/Megascans/3D_Assets/SandstoneRockyGround/SM_SandstoneRockyGround_01` | StaticMesh | 1.27 | 37,969 | 2.64x2.21x0.17 | E20 | no |  |
| `/Game/Megascans/3D_Assets/SandstoneRockyGround/SM_SandstoneRockyGround_02` | StaticMesh | 1.26 | 38,625 | 3.22x2.52x0.3 | B40,C10,C45 | no |  |
| `/Game/Megascans/3D_Assets/SandstoneRockyGround/SM_SandstoneRockyGround_03` | StaticMesh | 1.22 | 37,673 | 2.92x2.46x0.33 | B40,C10,C45,E20 | no |  |
| `/Game/Megascans/3D_Assets/SandstoneRockyGround/SM_SandstoneRockyGround_04` | StaticMesh | 1.00 | 29,534 | 2.21x1.8x0.31 | B40,C45,E20 | no |  |
| `/Game/Megascans/3D_Assets/SandstoneRockyGround/SM_SandstoneRockyGround_05` | StaticMesh | 2.65 | 78,505 | 7.74x5.09x0.54 | E20 | no |  |
| `/Game/Megascans/3D_Assets/Sandstone_rocky_ground_vd3oeic/MI_sandstone_rocky_ground_vd3oeic` | MaterialInstance | 0.12 |  |  | C10 | no |  |
| `/Game/Megascans/3D_Assets/Sandstone_rocky_ground_vd3oeic/MI_sandstone_rocky_ground_vd3oeic_Dark` | MaterialInstance | 0.12 |  |  | C10 | no |  |
| `/Game/Megascans/3D_Assets/Sandstone_rocky_ground_vd3oeic/MI_sandstone_rocky_ground_vd3oeic_Dark_Wet` | MaterialInstance | 0.08 |  |  | C10 | no | wet variant |
| `/Game/Megascans/3D_Assets/Sandstone_rocky_ground_vd3oeic/SM_sandstone_rocky_ground_vd3oeic` | StaticMesh | 0.93 | 10,742 | 2.64x2.21x0.17 | C10 | no |  |
| `/Game/Megascans/3D_Assets/Snow_Embankment_vcsibaiga/MI_Sand_Embankment_vcsibaiga_8K` | MaterialInstance | 0.00 |  |  | B30,E10,E30 | no |  |
| `/Game/Megascans/3D_Assets/Snow_Embankment_vcsibaiga/S_Sand_Embankment_vcsibaiga_high_Var1` | StaticMesh | 13.82 | 494,645 | 4.62x2.77x0.52 | B30 | no | very dense: confirm Nanite before placing many |
| `/Game/Megascans/3D_Assets/Snow_Hill_vdbmabvva/MI_Snow_Hill_vdbmabvva_High` | MaterialInstance | 0.00 |  |  | B40,C45 | no | snow variant |
| `/Game/Megascans/3D_Assets/Snow_Hill_vdbmabvva/snow_hill_vdbmabvva_high1` | StaticMesh | 0.40 |  |  | B40,C45 | no | snow variant |
| `/Game/Megascans/3D_Assets/TundraRockyGround/MI_TundraRockyGround_01` | MaterialInstance | 0.03 |  |  | C10 | no |  |
| `/Game/Megascans/3D_Assets/TundraRockyGround/SM_TundraRockyGround_01` | StaticMesh | 2.58 | 81,803 | 6.04x4.73x0.84 | C10 | no |  |
| `/Game/Megascans/3D_Assets/Tundra_Boulder_viurbeqaw/MI_Tundra_Boulder_viurbeqaw_Uber` | MaterialInstance | 0.17 |  |  | A30 | no |  |
| `/Game/Megascans/3D_Assets/Tundra_Boulder_viurbeqaw/S_Tundra_Boulder_viurbeqaw_high_Var1` | StaticMesh | 4.90 | 149,834 | 2.54x2.05x1.31 | A30 | no |  |
| `/Game/Megascans/3D_Assets/Tundra_Boulder_vivrcjkaw/MI_Tundra_Boulder_Snowy` | MaterialInstance | 0.15 |  |  | B40 | no | snow variant |
| `/Game/Megascans/3D_Assets/Tundra_Boulder_vivrcjkaw/MI_Tundra_Boulder_Snowy_Var2` | MaterialInstance | 0.00 |  |  | B40 | no | snow variant |
| `/Game/Megascans/3D_Assets/Tundra_Boulder_vivrcjkaw/MI_Tundra_Boulder_Snowy_Var3` | MaterialInstance | 0.00 |  |  | B40 | no | snow variant |
| `/Game/Megascans/3D_Assets/Tundra_Boulder_vivrcjkaw/S_Tundra_Boulder_Snowy` | StaticMesh | 2.88 | 80,737 | 2.21x1.44x0.95 | B40 | no | snow variant |
| `/Game/Megascans/3D_Assets/Tundra_Boulder_vivrcjkaw/S_Tundra_Boulder_vivrcjkaw_high_Var1` | StaticMesh | 2.63 | 80,737 | 2.21x1.44x0.95 | A30 | no |  |
| `/Game/Megascans/3D_Assets/Tundra_Boulder_vivvaewaw/S_Tundra_Boulder_Snowy_2` | StaticMesh | 0.24 | 3,540 | 2.4x2.05x0.95 | B40 | no | snow variant |
| `/Game/Megascans/3D_Assets/Tundra_Boulder_vivvaewaw/S_Tundra_Boulder_vivvaewaw_high_Var1` | StaticMesh | 0.12 | 3,540 | 2.4x2.05x0.95 | A30 | no |  |
| `/Game/Megascans/3D_Assets/Tundra_Boulder_vjdraddmw/MI_Tundra_Boulder_vjdraddmw_8K` | MaterialInstance | 0.00 |  |  | A30 | no |  |
| `/Game/Megascans/3D_Assets/Tundra_Rocky_Ground_vjeodizmw/MI_Tundra_Rocky_Ground_vjeodizmw_8K` | MaterialInstance | 0.00 |  |  | B30 | no |  |
| `/Game/Megascans/3D_Assets/Tundra_Rocky_Ground_vjeodizmw/S_Tundra_Rocky_Ground_vjeodizmw_high_Var1` | StaticMesh | 1.67 | 51,425 | 4.9x4.4x0.32 | B30 | no |  |
| `/Game/Megascans/3D_Assets/quarry_cliff_ubhubhyda/MI_Quarry_Cliff_ubhubhyda` | MaterialInstance | 0.00 |  |  | A30 | no |  |
| `/Game/Megascans/3D_Assets/quarry_cliff_ubhubhyda/SM_Quarry_Cliff_ubhubhyda` | StaticMesh | 10.24 | 298,943 | 13.82x5.52x6.59 | A30 | no |  |
| `/Game/Megascans/3D_Assets/quarry_cliff_uchofe0fa/MI_Quarry_Cliff_uchofe0fa` | MaterialInstance | 0.00 |  |  | A30 | no |  |
| `/Game/Megascans/3D_Assets/quarry_cliff_uchofe0fa/SM_Quarry_Cliff_uchofe0fa` | StaticMesh | 12.79 | 398,138 | 4.46x1.67x3.2 | A30 | no |  |

*Group note:* Megascans landform scans; sandstone sets are warm-toned (distance only)

### Snow and rock surfaces (Megascans) (53)

*Where on PWR:* Snow line, cliff faces, rock landscape layer

| path | kind | MB | verts | bounds m | levels | PWR | note |
|---|---|---|---|---|---|---|---|
| `/Game/Megascans/Surfaces/Fresh_Windswept_Snow_uhpjdeyn/MF_LL_Fresh_Windswept_Snow_uhpjdeyn` | MaterialFunction | 0.00 |  |  | B40,C45 | no | snow variant |
| `/Game/Megascans/Surfaces/Melting_Snow_uepnbikfw/MF_LL_Melting_Snow_uepnbikfw` | MaterialFunction | 0.00 |  |  | B40,C45 | no | snow variant |
| `/Game/Megascans/Surfaces/Rock_Jagged_udemcebew/MF_LL_Rock_Jagged_udemcebew` | MaterialFunction | 0.00 |  |  | B40,C45 | no | sibling used by PWR |
| `/Game/Megascans/Surfaces/Rock_Rough_tbphbbeg/MF_LL_Rock_Rough_tbphbbeg` | MaterialFunction | 0.00 |  |  | B40,C45 | no |  |
| `/Game/Megascans/Surfaces/Snow_Coarse_ueiqbiefw/MI_Snow_Coarse_ueiqbiefw_4K_Uber` | MaterialInstance | 0.14 |  |  | C20 | no | snow variant |
| `/Game/Megascans/Surfaces/Snow_Covered_Grass_ueolejtn/MF_LL_Snow_Covered_Grass_ueolejtn_ORHG` | MaterialFunction | 0.00 |  |  | B40,C45 | no | snow variant; packed AO/roughness/height map |
| `/Game/Megascans/Surfaces/Snow_Covered_Ground_sinjagua/MF_LL_Snow_Covered_Ground_sinjagua` | MaterialFunction | 0.00 |  |  | B40,C45 | no | snow variant |
| `/Game/Megascans/Surfaces/Windswept_Snow_uephfgudy/MF_LL_Windswept_Snow_uephfgudy` | MaterialFunction | 0.00 |  |  | B40,C45 | no | snow variant; sibling used by PWR |
| `/Game/Megascans/Surfaces/Windswept_Snowy_Stones_tdloaf1r/MF_LL_Windswept_Snowy_Stones_tdloaf1r` | MaterialFunction | 0.00 |  |  | B40,C45 | no | snow variant |

Textures: `/Game/Megascans/Surfaces/Fresh_Windswept_Snow_uhpjdeyn/T_Fresh_Windswept_Snow_uhpjdeyn_NSVT_D` (2.8 MB), `/Game/Megascans/Surfaces/Fresh_Windswept_Snow_uhpjdeyn/T_Fresh_Windswept_Snow_uhpjdeyn_NSVT_N` (5.6 MB), `/Game/Megascans/Surfaces/Fresh_Windswept_Snow_uhpjdeyn/T_Fresh_Windswept_Snow_uhpjdeyn_NSVT_ORHG` (5.6 MB), `/Game/Megascans/Surfaces/IcelandicQuarryRock/T_IcelandicQuarryRock_01_AoRDp` (0.9 MB), `/Game/Megascans/Surfaces/IcelandicQuarryRock/T_IcelandicQuarryRock_01_BC` (0.9 MB), `/Game/Megascans/Surfaces/Jagged_Rock_umrjbbmlw/T_Jagged_Rock_D` (3.2 MB), `/Game/Megascans/Surfaces/Jagged_Rock_umrjbbmlw/T_Jagged_Rock_N` (6.4 MB), `/Game/Megascans/Surfaces/Jagged_Rock_umrjbbmlw/T_Jagged_Rock_ORHG` (6.4 MB), `/Game/Megascans/Surfaces/Jagged_Rock_umrjbbmlw/T_Jagged_Rock_umrjbbmlw_N` (6.4 MB), `/Game/Megascans/Surfaces/Jagged_Rock_umrjbbmlw/T_Jagged_Rock_umrjbbmlw_ORHG` (6.4 MB), `/Game/Megascans/Surfaces/Melting_Snow_uepnbikfw/T_MeltingSnow_uepnbikfw_2K_ORDp` (3.2 MB), `/Game/Megascans/Surfaces/Melting_Snow_uepnbikfw/T_Melting_Snow_uepnbikfw_2K_D` (3.2 MB), `/Game/Megascans/Surfaces/Melting_Snow_uepnbikfw/T_Melting_Snow_uepnbikfw_2K_N` (6.4 MB), `/Game/Megascans/Surfaces/Melting_Snow_uepnbikfw/T_Melting_Snow_uepnbikfw_NSVT_D` (2.8 MB), `/Game/Megascans/Surfaces/Melting_Snow_uepnbikfw/T_Melting_Snow_uepnbikfw_NSVT_N` (5.6 MB), `/Game/Megascans/Surfaces/Melting_Snow_uepnbikfw/T_Melting_Snow_uepnbikfw_NSVT_ORHG` (5.6 MB), `/Game/Megascans/Surfaces/Rock_Cliff_vl1lbbylw/T_Rock_Cliff_vl1lbbylw_4K_D` (3.2 MB), `/Game/Megascans/Surfaces/Rock_Cliff_vl1lbbylw/T_Rock_Cliff_vl1lbbylw_4K_N` (6.4 MB), `/Game/Megascans/Surfaces/Rock_Jagged_udemcebew/T_Rock_Jagged_udemcebew_NSVT_D` (2.8 MB, PWR yes), `/Game/Megascans/Surfaces/Rock_Jagged_udemcebew/T_Rock_Jagged_udemcebew_NSVT_N` (5.6 MB, PWR yes), `/Game/Megascans/Surfaces/Rock_Jagged_udemcebew/T_Rock_Jagged_udemcebew_NSVT_ORHG` (5.6 MB, PWR yes), `/Game/Megascans/Surfaces/Rock_Rough_tbphbbeg/T_Rock_Rough_tbphbbeg_4K_NSVT_D` (2.8 MB), `/Game/Megascans/Surfaces/Rock_Rough_tbphbbeg/T_Rock_Rough_tbphbbeg_4K_NSVT_N` (5.6 MB), `/Game/Megascans/Surfaces/Rock_Rough_tbphbbeg/T_Rock_Rough_tbphbbeg_NSVT_ORHG` (5.6 MB), `/Game/Megascans/Surfaces/Snow_Coarse_ueiqbiefw/T_Snow_Coarse_ueiqbiefw_4K_N` (6.4 MB), `/Game/Megascans/Surfaces/Snow_Coarse_ueiqbiefw/T_Snow_Coarse_ueiqbiefw_4K_RHG` (6.4 MB), `/Game/Megascans/Surfaces/Snow_Covered_Grass_ueolejtn/T_Snow_Covered_Grass_ueolejtn_NSVT_D` (2.8 MB), `/Game/Megascans/Surfaces/Snow_Covered_Grass_ueolejtn/T_Snow_Covered_Grass_ueolejtn_NSVT_N` (5.6 MB), `/Game/Megascans/Surfaces/Snow_Covered_Grass_ueolejtn/T_Snow_Covered_Grass_ueolejtn_NSVT_ORHG` (5.6 MB), `/Game/Megascans/Surfaces/Snow_Covered_Ground_sinjagua/T_Snow_Covered_Ground_sinjagua_NSVT_D` (2.8 MB), `/Game/Megascans/Surfaces/Snow_Covered_Ground_sinjagua/T_Snow_Covered_Ground_sinjagua_NSVT_N` (5.6 MB), `/Game/Megascans/Surfaces/Snow_Covered_Ground_sinjagua/T_Snow_Covered_Ground_sinjagua_NSVT_ORHG` (5.6 MB), `/Game/Megascans/Surfaces/Windswept_Snow_uephfgudy/T_Windswept_Snow_AO` (6.4 MB), `/Game/Megascans/Surfaces/Windswept_Snow_uephfgudy/T_Windswept_Snow_D` (3.2 MB), `/Game/Megascans/Surfaces/Windswept_Snow_uephfgudy/T_Windswept_Snow_H` (6.4 MB), `/Game/Megascans/Surfaces/Windswept_Snow_uephfgudy/T_Windswept_Snow_N` (6.4 MB), `/Game/Megascans/Surfaces/Windswept_Snow_uephfgudy/T_Windswept_Snow_NSVT_D` (2.8 MB, PWR yes), `/Game/Megascans/Surfaces/Windswept_Snow_uephfgudy/T_Windswept_Snow_NSVT_N` (5.6 MB, PWR yes), `/Game/Megascans/Surfaces/Windswept_Snow_uephfgudy/T_Windswept_Snow_R` (6.4 MB), `/Game/Megascans/Surfaces/Windswept_Snow_uephfgudy/T_Windswept_Snow_uephfgudy_NSVT_ORHG` (5.6 MB, PWR yes), `/Game/Megascans/Surfaces/Windswept_Snow_uephfgudy/T_Windswept_Snow_uephfgudy_ORHG` (6.4 MB), `/Game/Megascans/Surfaces/Windswept_Snowy_Stones_tdloaf1r/T_Windswept_Snowy_Stones_tdloaf1r_NSVT_D` (2.8 MB), `/Game/Megascans/Surfaces/Windswept_Snowy_Stones_tdloaf1r/T_Windswept_Snowy_Stones_tdloaf1r_NSVT_N` (5.6 MB), `/Game/Megascans/Surfaces/Windswept_Snowy_Stones_tdloaf1r/T_Windswept_Snowy_Stones_tdloaf1r_NSVT_ORHG` (5.6 MB)

*Group note:* Megascans snow/rock texture sets; PWR uses Rock_Jagged and Windswept_Snow

### Rural Australia ridge (dirt) (1)

*Where on PWR:* Distant dirt ridges


Textures: `/Game/RuralAustralia/StaticMeshes/Rocks/Ridge_Dirt_01/T_Ridge_Dirt_02_CA` (11.2 MB)

*Group note:* Single ridge texture set

### Cloud sea and fake cloud volumes (VFX/VolumetricEffects) (13)

*Where on PWR:* Valley fog below the far peaks

| path | kind | MB | verts | bounds m | levels | PWR | note |
|---|---|---|---|---|---|---|---|
| `/Game/VFX/VolumetricEffects/CloudSea/BP/BP_CloudWindIndicator` | Blueprint | 0.00 |  |  | A30 | no |  |
| `/Game/VFX/VolumetricEffects/CloudSea/Gigantic_Sandstone_Terrain_wldhdhxva/M_CloudSeaMountain_Temp` | Material | 0.01 |  |  | A30 | no |  |
| `/Game/VFX/VolumetricEffects/CloudSea/Gigantic_Sandstone_Terrain_wldhdhxva/SM_Gigantic_Sandstone_Terrain_wldhdhxva_high_Var1` | StaticMesh | 6.75 | 201,459 | 575.95x365.18x107.67 | A30 | no |  |
| `/Game/VFX/VolumetricEffects/CloudSea/PP_CloudSea` | Material | 0.01 |  |  | A30 | no |  |
| `/Game/VFX/VolumetricEffects/CloudSea/PP_CloudSea_NoCloudsInstance` | MaterialInstance | 0.00 |  |  | A30 | no |  |
| `/Game/VFX/VolumetricEffects/CloudSea/SplineCloudSea/BP_Spline_FakeCloudSea` | Blueprint | 0.01 |  |  | A30 | no |  |
| `/Game/VFX/VolumetricEffects/CloudSea/SplineCloudSea/MI_FakeCloudSea` | MaterialInstance | 0.00 |  |  | A30 | no |  |
| `/Game/VFX/VolumetricEffects/CloudSea/SplineCloudSea/M_FakeCloudSea` | Material | 0.01 |  |  | A30 | no |  |
| `/Game/VFX/VolumetricEffects/CloudSea/SplineCloudSea/SM_Plane_100segOnX_100x100` | StaticMesh | 0.03 | 202 | 1.0x1.0x0.0 | A30 | no |  |

Textures: `/Game/VFX/VolumetricEffects/CloudSea/Gigantic_Sandstone_Terrain_wldhdhxva/T_GiganticSandstoneTerrain_wldhdhxva_4K_DpRF` (12.7 MB), `/Game/VFX/VolumetricEffects/CloudSea/Gigantic_Sandstone_Terrain_wldhdhxva/T_Gigantic_Sandstone_Terrain_wldhdhxva_4K_D` (12.7 MB), `/Game/VFX/VolumetricEffects/CloudSea/Gigantic_Sandstone_Terrain_wldhdhxva/T_Gigantic_Sandstone_Terrain_wldhdhxva_4K_N` (6.4 MB), `/Game/VFX/VolumetricEffects/CloudSea/Textures/T_VolumetricCloud_PerlinWorley_01` (4.2 MB)

*Group note:* A30 cloud-sea backdrop (Gigantic sandstone terrain + spline cloud sea)

## 6. Open meadow ground and landscape materials (703)

### Ground soil and grass materials (Env/Bio) (69)

*Where on PWR:* Meadow and forest ground layers

| path | kind | MB | verts | bounds m | levels | PWR | note |
|---|---|---|---|---|---|---|---|
| `/Game/Env/Bio/Decorators/LG_A50_grass_assets` | LandscapeGrassType | 0.00 |  |  | A50 | no |  |
| `/Game/Env/Bio/Decorators/LG_A50_stone_assets` | LandscapeGrassType | 0.00 |  |  | A50 | no |  |
| `/Game/Env/Bio/Decorators/LG_B30_grass_assets` | LandscapeGrassType | 0.01 |  |  | B30 | no |  |
| `/Game/Env/Bio/Decorators/LG_B30_rippledsand_assets` | LandscapeGrassType | 0.00 |  |  | B30 | no |  |
| `/Game/Env/Bio/Decorators/LG_B30_rock_assets` | LandscapeGrassType | 0.00 |  |  | B30 | no |  |
| `/Game/Env/Bio/Decorators/LG_B30_sand_assets` | LandscapeGrassType | 0.00 |  |  | B30 | no |  |
| `/Game/Env/Bio/Decorators/LG_B30_stone_assets` | LandscapeGrassType | 0.00 |  |  | B30 | no |  |
| `/Game/Env/Bio/Decorators/LG_C10_grass_assets` | LandscapeGrassType | 0.00 |  |  | C10 | no |  |
| `/Game/Env/Bio/Decorators/LG_C10_leavesrotting_assets` | LandscapeGrassType | 0.00 |  |  | C10 | no |  |
| `/Game/Env/Bio/Decorators/LG_C10_rock_assets` | LandscapeGrassType | 0.00 |  |  | C10 | no |  |
| `/Game/Env/Bio/Decorators/LG_C10_soil_assets` | LandscapeGrassType | 0.00 |  |  | C10 | no |  |
| `/Game/Env/Bio/Decorators/LG_C10_wetsoil_assets` | LandscapeGrassType | 0.00 |  |  | C10 | no | wet variant |
| `/Game/Env/Bio/Decorators/LG_E20_grass_assets` | LandscapeGrassType | 0.00 |  |  | E20 | no |  |
| `/Game/Env/Bio/Ground/Grass/Ground_Grass_Plane_A/SM_Ground_Grass_Plane_A` | StaticMesh | 0.08 | 1,235 | 12.5x11.08x1.06 | A30 | no |  |
| `/Game/Env/Bio/Ground/Soil/Ground_Soil_Pile_A/SM_Ground_Soil_Pile_A` | StaticMesh | 1.66 | 48,036 | 6.0x12.52x1.23 | A30,B40,C10,C45,D40 | no |  |
| `/Game/Env/Bio/Ground/Soil/Ground_Soil_Pile_B/SM_Ground_Soil_Pile_B` | StaticMesh | 0.75 | 22,573 | 8.61x5.77x1.66 | A30,C10,D40 | no |  |
| `/Game/Env/Bio/Ground/Soil/Ground_Soil_Pile_B_Half/SM_Ground_Soil_Pile_B_Half` | StaticMesh | 0.26 | 6,980 | 4.05x5.77x1.64 | D40 | no |  |
| `/Game/Env/Bio/Ground/Soil/Ground_Soil_Pile_B_Rocky/SM_Ground_Soil_Pile_B_Rocky` | StaticMesh | 7.23 | 222,599 | 8.65x5.69x1.5 | A30 | no |  |
| `/Game/Env/Bio/Ground/Soil/Ground_Soil_Pile_C/SM_Ground_Soil_Pile_C` | StaticMesh | 1.31 | 17,900 | 4.73x5.84x0.95 | A30,B40,C10,C45,D40 | no |  |
| `/Game/Env/Bio/Ground/Soil/Ground_Soil_Pile_D/Materials/MI_Ground_Soil_Pile_D` | MaterialInstance | 0.00 |  |  | C10,E20 | no |  |
| `/Game/Env/Bio/Ground/Soil/Ground_Soil_Pile_D/Materials/MI_Ground_Soil_Pile_D_Wet` | MaterialInstance | 0.08 |  |  | C10 | no | wet variant |
| `/Game/Env/Bio/Ground/Soil/Ground_Soil_Pile_D/SM_Ground_Soil_Pile_D` | StaticMesh | 2.47 | 69,112 | 23.11x16.24x11.74 | C10,E20 | no |  |
| `/Game/Env/Bio/Ground/Soil/Ground_Soil_Pile_E/SM_Ground_Soil_Pile_E` | StaticMesh | 0.97 | 24,709 | 26.51x16.13x3.52 | A30,B40,C10,C45,D40 | no |  |
| `/Game/Env/Bio/Ground/Soil/Ground_Soil_Pile_E_Half/SM_Ground_Soil_Pile_E_Half` | StaticMesh | 0.38 | 10,351 | 26.13x8.18x3.39 | D40 | no |  |
| `/Game/Env/Bio/Ground/Soil/Ground_Soil_Pile_E_Smooth/SM_Ground_Soil_Pile_E_Smooth` | StaticMesh | 2.01 | 47,591 | 26.48x16.09x3.49 | C10 | no |  |
| `/Game/Env/Bio/Ground/Soil/Ground_Soil_Transition/MIP_Soil_Transition` | MaterialInstance | 0.17 |  |  | C10 | no |  |
| `/Game/Env/Bio/Ground/Soil/Ground_Soil_Transition/MIP_Soil_Transition_Wet` | MaterialInstance | 0.09 |  |  | C10 | no | wet variant |
| `/Game/Env/Bio/Ground/Soil/Ground_Soil_Transition/SM_Ground_Soil_Transition_01` | StaticMesh | 1.63 | 49,925 | 14.25x13.6x0.45 | C10 | no |  |
| `/Game/Env/Bio/Ground/Soil/Materials/MIP_Ground_Soil_Pile` | MaterialInstance | 0.17 |  |  | C10 | no | sibling used by PWR |
| `/Game/Env/Bio/Ground/Soil/Materials/MIP_Ground_Soil_Pile_Wet` | MaterialInstance | 0.10 |  |  | C10 | no | wet variant; sibling used by PWR |
| `/Game/Env/Bio/Ground/Soil/Materials/MIP_Layered_Sand_Pile` | MaterialInstance | 0.13 |  |  |  | no | sibling used by PWR |
| `/Game/Env/Bio/Ground/Soil/Materials/MIP_Layered_Soil_Pile` | MaterialInstance | 0.16 |  |  | A30,B40,C10,C45,D40,E20 | no | sibling used by PWR |
| `/Game/Env/Bio/Ground/Soil/Materials/MIP_Layered_Soil_Pile_Wet` | MaterialInstance | 0.08 |  |  | C10 | no | wet variant; sibling used by PWR |
| `/Game/Env/Bio/Ground/Soil/Materials/MI_Crash_Site_Mud_A` | MaterialInstance | 0.15 |  |  | A30 | no | sibling used by PWR |
| `/Game/Env/Bio/Ground/Soil/Materials/MI_Soil_Snow` | MaterialInstance | 0.12 |  |  | B40,C45 | listed | snow variant |
| `/Game/Env/Bio/Materials/Rock/pnwgl_rock_macrotile_03/MLI_PNWGL_Rock_Macrotile_03` | MaterialLayerInstance | 0.00 |  |  | B40,C45 | no |  |

Textures: `/Game/Env/Bio/+Materials/Textures/Ground/Soil/T_Soil_N` (6.4 MB), `/Game/Env/Bio/+Materials/Textures/Ground/Soil/T_Soil_ORHG` (6.4 MB), `/Game/Env/Bio/Ground/Soil/Ground_Soil_Transition/T_Soil_Transition_mask_01` (1.7 MB), `/Game/Env/Bio/Ground/Soil/Materials/T_Ground_Soil_Pile_01_M` (1.7 MB), `/Game/Env/Bio/Materials/Mask/T_Biome_Mask_01` (6.4 MB), `/Game/Env/Bio/Materials/Mask/T_Biome_Mask_02` (6.4 MB), `/Game/Env/Bio/Materials/Rock/Frozen/Ice_Lake_01/T_Ice_Lake_01_D` (12.7 MB), `/Game/Env/Bio/Materials/Rock/Frozen/Ice_Lake_01/T_Ice_Lake_01_ORHG` (6.4 MB), `/Game/Env/Bio/Materials/Rock/Rock_Swamp_Lrg_A/T_Rock_Swamp_Lrg_A_D` (3.2 MB), `/Game/Env/Bio/Materials/Rock/Rock_Swamp_Lrg_A/T_Rock_Swamp_Lrg_A_N` (6.4 MB), `/Game/Env/Bio/Materials/Rock/Rock_Swamp_Lrg_A/T_Rock_Swamp_Lrg_A_ORHG` (6.4 MB), `/Game/Env/Bio/Materials/Rock/Rock_Uluwatu_Surface_B/T_Rock_Uluwatu_Surface_B_N` (6.4 MB), `/Game/Env/Bio/Materials/Rock/Rock_Uluwatu_Surface_B/T_Rock_Uluwatu_Surface_B_ORHG` (6.4 MB), `/Game/Env/Bio/Materials/Rock/Rock_Uluwatu_Surface_C/T_Rock_Uluwatu_Surface_C_ORHG` (6.4 MB), `/Game/Env/Bio/Materials/Rock/Rock_Uluwatu_Surface_Rough_A/T_Rock_Uluwatu_Rough_A_N` (1.7 MB), `/Game/Env/Bio/Materials/Rock/bme_rock_cliff_scanpatch_05/T_BME_Rock_Cliff_Scanpatch_05_N` (6.4 MB), `/Game/Env/Bio/Materials/Rock/bme_rock_surface_granite_01/T_BME_Rock_Surface_Granite_01_N` (6.4 MB), `/Game/Env/Bio/Materials/Rock/bme_rock_surface_granite_01/T_BME_Rock_Surface_Granite_01_ORHG` (6.4 MB), `/Game/Env/Bio/Materials/Rock/bme_rock_surface_granite_01/T_Granite_ORME` (0.5 MB), `/Game/Env/Bio/Materials/Rock/pnwgl_rock_macrotile_03/T_PNWGL_Rock_Macrotile_03_N` (6.4 MB), `/Game/Env/Bio/Materials/Rock/pnwgl_rock_macrotile_03/T_PNWGL_Rock_Macrotile_03_ORHG` (6.4 MB), `/Game/Env/Bio/Materials/Soil/Mud_Swamp_Drag/T_Decal_Soil_Vertical_D` (3.2 MB), `/Game/Env/Bio/Materials/Soil/Mud_Swamp_Drag/T_Swamp_Drag_Slosh_D` (3.2 MB), `/Game/Env/Bio/Materials/Soil/Mud_Swamp_Drag/T_Swamp_Drag_Slosh_N` (6.4 MB), `/Game/Env/Bio/Materials/Soil/Mud_Swamp_Drag/T_Swamp_Drag_Slosh_ORHG` (3.2 MB), `/Game/Env/Bio/Materials/Soil/Mud_Swamp_Drag/T_Swamp_Drag_Trace_D` (3.2 MB), `/Game/Env/Bio/Materials/Soil/Mud_Swamp_Drag/T_Swamp_Drag_Trace_N` (6.4 MB), `/Game/Env/Bio/Materials/Soil/Mud_Swamp_Drag/T_Swamp_Drag_Wet_N` (6.4 MB), `/Game/Env/Bio/Materials/Soil/Mud_Swamp_Drag/T_Swamp_Drag_Wet_ORHG` (6.4 MB), `/Game/Env/Bio/Materials/Soil/Mud_Swamp_Drag/T_Swamp_Ground_Soil_Wet_A_4K_NSVT_D` (3.2 MB), `/Game/Env/Bio/Materials/Soil/Mud_Swamp_Drag/T_Swamp_Ground_Soil_Wet_A_4K_NSVT_N` (6.4 MB), `/Game/Env/Bio/Materials/Soil/Mud_Swamp_Drag/T_Swamp_Ground_Soil_Wet_A_4K_NSVT_ORHG` (6.4 MB), `/Game/Env/Bio/Materials/Soil/T_Ground_Snow_Clumpy_01_N` (6.4 MB)

*Group note:* Env/Bio ground MIs/textures (soil snow, coastal grass sand etc.)

### Alpine flowers and ground plants (Env/Bio) (35)

*Where on PWR:* Alpine meadow and dry slopes

| path | kind | MB | verts | bounds m | levels | PWR | note |
|---|---|---|---|---|---|---|---|
| `/Game/Env/Bio/Grass/AutumnMoor/FT_Grass_AutumnMoor` | FoliageType | 0.00 |  |  | A30 | no | [foliage] |
| `/Game/Env/Bio/Grass/AutumnMoor/MI_Grass_AutumnMoor_Blend` | MaterialInstance | 0.03 |  |  | A30 | no | [foliage] |
| `/Game/Env/Bio/Grass/AutumnMoor/SM_Grass_AutumnMoor` | StaticMesh | 3.07 | 19,994 | 1.09x1.02x1.17 | A30 | no | [foliage] |
| `/Game/Env/Bio/Grass/CanyonPrinceWildRye/FT_Grass_CanyonPrinceWildRye` | FoliageType | 0.00 |  |  | A30 | no | [foliage]; sibling used by PWR |
| `/Game/Env/Bio/Grass/CanyonPrinceWildRye/MI_Grass_CanyonPrinceWildRye` | MaterialInstance | 0.03 |  |  | A30 | no | [foliage]; sibling used by PWR |
| `/Game/Env/Bio/Grass/CanyonPrinceWildRye/SM_Grass_CanyonPrinceWildRye` | StaticMesh | 1.99 | 11,258 | 1.64x1.48x1.03 | A30 | yes | [foliage] |
| `/Game/Env/Bio/Grass/GroundcoverClump/Grass_GroundcoverClump_A/SM_Grass_GroundcoverClump_A` | StaticMesh | 0.71 | 8,618 | 0.49x0.61x0.21 | C10 | yes | [foliage] |
| `/Game/Env/Bio/Plants/AlpinePrimrose/MI_Plant_AlpinePrimrose` | MaterialInstance | 0.08 |  |  | E30 | no | [foliage] |
| `/Game/Env/Bio/Plants/AlpinePrimrose/SM_Plant_AlpinePrimrose_Kit_A` | StaticMesh | 5.92 | 29,118 | 1.39x0.7x0.47 | E30 | no | [foliage] |
| `/Game/Env/Bio/Plants/AlpinePrimrose/SM_Plant_AlpinePrimrose_Kit_B` | StaticMesh | 3.22 | 16,526 | 1.39x0.64x0.38 | E30 | no | [foliage] |
| `/Game/Env/Bio/Plants/AlpinePrimrose/SM_Plant_AlpinePrimrose_Kit_C` | StaticMesh | 0.31 | 1,598 | 0.35x0.33x0.15 | E30 | no | [foliage] |
| `/Game/Env/Bio/Plants/Sagebrush/Materials/MI_Plants_Sagebrush_01` | MaterialInstance | 0.03 |  |  | A50,C10 | no | [foliage] |
| `/Game/Env/Bio/Plants/Sagebrush/Plants_Sagebrush_A/Foliage/FT_Plants_Sagebrush_A_FoliageType` | FoliageType | 0.00 |  |  | A50 | no | [foliage] |
| `/Game/Env/Bio/Plants/Sagebrush/Plants_Sagebrush_A/SM_Plants_Sagebrush_A` | StaticMesh | 3.15 | 99,864 | 1.78x1.83x1.22 | A50 | yes | [foliage] |
| `/Game/Env/Bio/Plants/Sagebrush/Plants_Sagebrush_B/Foliage/FT_Plants_Sagebrush_B_FoliageType` | FoliageType | 0.00 |  |  | A50 | no | [foliage] |
| `/Game/Env/Bio/Plants/Sagebrush/Plants_Sagebrush_B/SM_Plants_Sagebrush_B` | StaticMesh | 6.48 | 184,639 | 2.02x2.49x1.63 | A50 | no | [foliage] |
| `/Game/Env/Bio/Plants/Sagebrush/Plants_Sagebrush_C/Foliage/FT_Plants_Sagebrush_C_FoliageType` | FoliageType | 0.00 |  |  | A50 | no | [foliage] |
| `/Game/Env/Bio/Plants/Sagebrush/Plants_Sagebrush_C/SM_Plants_Sagebrush_C` | StaticMesh | 1.87 | 61,470 | 1.07x0.93x1.09 | A50 | no | [foliage] |
| `/Game/Env/Bio/Plants/Sagebrush/Plants_Sagebrush_D/Foliage/FT_Plants_Sagebrush_D_FoliageType` | FoliageType | 0.00 |  |  | A50 | no | [foliage] |
| `/Game/Env/Bio/Plants/Sagebrush/Plants_Sagebrush_D/SM_Plants_Sagebrush_D` | StaticMesh | 5.22 | 162,649 | 1.74x1.31x1.56 | A50,C10 | no | [foliage] |
| `/Game/Env/Bio/Plants/Sagebrush/Plants_Sagebrush_E/Foliage/FT_Plants_Sagebrush_E_FoliageType` | FoliageType | 0.00 |  |  | A50 | no | [foliage] |
| `/Game/Env/Bio/Plants/Sagebrush/Plants_Sagebrush_E/SM_Plants_Sagebrush_E` | StaticMesh | 3.62 | 110,002 | 2.35x1.75x1.59 | A50 | no | [foliage] |

Textures: `/Game/Env/Bio/Grass/AutumnMoor/T_Grass_AutumnMoor_D` (0.3 MB), `/Game/Env/Bio/Grass/AutumnMoor/T_Grass_AutumnMoor_N` (0.3 MB), `/Game/Env/Bio/Grass/AutumnMoor/T_Grass_AutumnMoor_ORT` (0.5 MB), `/Game/Env/Bio/Grass/CanyonPrinceWildRye/T_Grass_CanyonPrinceWildRye_D` (0.8 MB, PWR yes), `/Game/Env/Bio/Grass/CanyonPrinceWildRye/T_Grass_CanyonPrinceWildRye_N` (0.8 MB, PWR yes), `/Game/Env/Bio/Grass/CanyonPrinceWildRye/T_Grass_CanyonPrinceWildRye_ORT` (1.7 MB, PWR yes), `/Game/Env/Bio/Plants/AlpinePrimrose/T_Plant_AlpinePrimrose_D` (1.7 MB), `/Game/Env/Bio/Plants/AlpinePrimrose/T_Plant_AlpinePrimrose_M` (0.8 MB), `/Game/Env/Bio/Plants/AlpinePrimrose/T_Plant_AlpinePrimrose_N` (1.7 MB), `/Game/Env/Bio/Plants/AlpinePrimrose/T_Plant_AlpinePrimrose_ORHG` (1.7 MB), `/Game/Env/Bio/Plants/Sagebrush/Materials/T_Plants_Sagebrush_D` (3.2 MB), `/Game/Env/Bio/Plants/Sagebrush/Materials/T_Plants_Sagebrush_N` (6.4 MB), `/Game/Env/Bio/Plants/Sagebrush/Materials/T_Plants_Sagebrush_ORME` (3.2 MB)

*Group note:* AlpinePrimrose is the only true alpine flower; AutumnMoor is a moor grass

### Engine landscape support (Landscape/) (4)

*Where on PWR:* Landscape deformation/layer support

| path | kind | MB | verts | bounds m | levels | PWR | note |
|---|---|---|---|---|---|---|---|
| `/Game/Landscape/Deformation/BP_LandscapeDeformationManager_Configured` | Blueprint | 0.00 |  |  | B40,C45,D40 | no |  |
| `/Game/Landscape/LandscapeLayers/CoastalLayers/MF_LandscapeLayer_Grass_Coastal` | MaterialFunction | 0.00 |  |  | B30 | no |  |
| `/Game/Landscape/LayerInfo/PacificNorthwestLandscape/Dirt_LayerInfo` | LandscapeLayerInfo | 0.00 |  |  | A30 | no |  |
| `/Game/Landscape/VirtualTextures/LandscapeRuntimeVirtualTextureHeight` | RuntimeVirtualTexture | 0.00 |  |  | B30 | no |  |

*Group note:* Global landscape helpers

### Shipped landscape materials, layers and grass (197)

*Where on PWR:* Recipe + texture source for PWR's landscape material (A30 riverbed/scree/forest/grass; B40 snow/rocky gravel; C10 rotting leaves/roots/wet soil; B30 sand/wetness)

| path | kind | MB | verts | bounds m | levels | PWR | note |
|---|---|---|---|---|---|---|---|
| `/Game/Levels/Halo1/Solo/A30/Landscape/LayerInfo/Deprecated/LL_Wetness_LayerInfo` | LandscapeLayerInfo | 0.00 |  |  | A30 | no | wet variant |
| `/Game/Levels/Halo1/Solo/A30/Landscape/LayerInfo/LL_Burnt_Ground_LayerInfo` | LandscapeLayerInfo | 0.00 |  |  | A30 | no |  |
| `/Game/Levels/Halo1/Solo/A30/Landscape/LayerInfo/LL_Dirt_LayerInfo` | LandscapeLayerInfo | 0.00 |  |  | A30 | no |  |
| `/Game/Levels/Halo1/Solo/A30/Landscape/LayerInfo/LL_Forest_Ground_LayerInfo` | LandscapeLayerInfo | 0.00 |  |  | A30 | no |  |
| `/Game/Levels/Halo1/Solo/A30/Landscape/LayerInfo/LL_Grass_LayerInfo` | LandscapeLayerInfo | 0.00 |  |  | A30 | no |  |
| `/Game/Levels/Halo1/Solo/A30/Landscape/LayerInfo/LL_Riverbed_LayerInfo` | LandscapeLayerInfo | 0.00 |  |  | A30 | no |  |
| `/Game/Levels/Halo1/Solo/A30/Landscape/LayerInfo/LL_Sand_LayerInfo` | LandscapeLayerInfo | 0.00 |  |  | A30 | no |  |
| `/Game/Levels/Halo1/Solo/A30/Landscape/LayerInfo/LL_Scree_LayerInfo` | LandscapeLayerInfo | 0.00 |  |  | A30 | no |  |
| `/Game/Levels/Halo1/Solo/A30/Landscape/Materials/Landscape_MF/MF_LL_BurntGround` | MaterialFunction | 0.00 |  |  | A30 | no |  |
| `/Game/Levels/Halo1/Solo/A30/Landscape/Materials/Landscape_MF/MF_LL_Dirt` | MaterialFunction | 0.00 |  |  | A30 | no |  |
| `/Game/Levels/Halo1/Solo/A30/Landscape/Materials/Landscape_MF/MF_LL_ForestGround` | MaterialFunction | 0.00 |  |  | A30 | no |  |
| `/Game/Levels/Halo1/Solo/A30/Landscape/Materials/Landscape_MF/MF_LL_Grass` | MaterialFunction | 0.00 |  |  | A30 | no |  |
| `/Game/Levels/Halo1/Solo/A30/Landscape/Materials/Landscape_MF/MF_LL_Riverbed` | MaterialFunction | 0.00 |  |  | A30 | no |  |
| `/Game/Levels/Halo1/Solo/A30/Landscape/Materials/Landscape_MF/MF_LL_Sand` | MaterialFunction | 0.00 |  |  | A30 | no |  |
| `/Game/Levels/Halo1/Solo/A30/Landscape/Materials/Landscape_MF/MF_LL_Scree` | MaterialFunction | 0.00 |  |  | A30 | no |  |
| `/Game/Levels/Halo1/Solo/A30/Landscape/Materials/MI_A30_Landscape` | MaterialInstance | 0.03 |  |  | A30 | no |  |
| `/Game/Levels/Halo1/Solo/A30/Landscape/Materials/MM_A30_Landscape` | Material | 0.05 |  |  | A30 | no |  |
| `/Game/Levels/Halo1/Solo/A30/Landscape/Mud_Mounds/Mud_Mounds_Small/Mesh/SM_Mud_Mounds_Small_01` | StaticMesh | 1.68 | 45,121 | 1.5x1.81x0.77 | A30 | no |  |
| `/Game/Levels/Halo1/Solo/A30/Landscape/Mud_Mounds/Mud_Mounds_Small/Mesh/SM_Mud_Mounds_Small_02` | StaticMesh | 1.76 | 49,492 | 1.52x1.76x0.83 | A30 | no |  |
| `/Game/Levels/Halo1/Solo/A30/Landscape/Mud_Mounds/Mud_Mounds_Small/Mesh/SM_Mud_Mounds_Small_03` | StaticMesh | 2.03 | 54,564 | 1.71x1.83x0.77 | A30 | no |  |
| `/Game/Levels/Halo1/Solo/A30/Landscape/PCG/DA_LandscapeLayerSettings_A30` | DataAsset | 0.00 |  |  |  | no |  |
| `/Game/Levels/Halo1/Solo/A50/Landscape/GrassLayer/Wild_Grass_vdilbaiia/MI_Wild_Grass_vdilbaiia_4K_Green` | MaterialInstance | 0.00 |  |  | A50 | no |  |
| `/Game/Levels/Halo1/Solo/A50/Landscape/GrassLayer/Wild_Grass_vdilbaiia/SM_Wild_Grass_vdilbaiia_Var12_lod0` | StaticMesh | 0.18 | 2,938 | 1.44x1.23x0.94 | A50 | no |  |
| `/Game/Levels/Halo1/Solo/A50/Landscape/GrassLayer/Wild_Grass_vdilbaiia/SM_Wild_Grass_vdilbaiia_Var22_lod0` | StaticMesh | 0.46 | 8,985 | 1.49x1.06x0.78 | A50 | no |  |
| `/Game/Levels/Halo1/Solo/A50/Landscape/GrassLayer/Wild_Grass_vdilbaiia/SM_Wild_Grass_vdilbaiia_Var3_lod0` | StaticMesh | 0.31 | 6,296 | 0.88x0.92x0.69 | A50 | no |  |
| `/Game/Levels/Halo1/Solo/A50/Landscape/LayerInfo/LL_A50_Gravel_LayerInfo` | LandscapeLayerInfo | 0.00 |  |  | A50 | no |  |
| `/Game/Levels/Halo1/Solo/A50/Landscape/LayerInfo/LL_A50_Hide_Grass_LayerInfo` | LandscapeLayerInfo | 0.00 |  |  | A50 | no |  |
| `/Game/Levels/Halo1/Solo/A50/Landscape/LayerInfo/LL_A50_Rock_LayerInfo` | LandscapeLayerInfo | 0.00 |  |  | A50 | no |  |
| `/Game/Levels/Halo1/Solo/A50/Landscape/LayerInfo/LL_A50_Sand_LayerInfo` | LandscapeLayerInfo | 0.00 |  |  | A50 | no |  |
| `/Game/Levels/Halo1/Solo/A50/Landscape/LayerInfo/LL_A50_Stone_LayerInfo` | LandscapeLayerInfo | 0.00 |  |  | A50 | no |  |
| `/Game/Levels/Halo1/Solo/A50/Landscape/Materials/MF_LL_Desert_Ground_Gravel_A` | MaterialFunction | 0.00 |  |  | A50 | no |  |
| `/Game/Levels/Halo1/Solo/A50/Landscape/Materials/MF_LL_Desert_Ground_Gravel_B` | MaterialFunction | 0.00 |  |  | A50 | no |  |
| `/Game/Levels/Halo1/Solo/A50/Landscape/Materials/MF_LL_Desert_Ground_Rock_A` | MaterialFunction | 0.00 |  |  | A50 | no |  |
| `/Game/Levels/Halo1/Solo/A50/Landscape/Materials/MF_LL_Desert_Ground_Sand_A` | MaterialFunction | 0.00 |  |  | A50 | no |  |
| `/Game/Levels/Halo1/Solo/A50/Landscape/Materials/MF_LL_Desert_Ground_Stone_A` | MaterialFunction | 0.00 |  |  | A50 | no |  |
| `/Game/Levels/Halo1/Solo/A50/Landscape/Materials/MI_Landscape_A50` | MaterialInstance | 0.11 |  |  | A50 | no |  |
| `/Game/Levels/Halo1/Solo/A50/Landscape/Materials/MI_Landscape_A50_Mask` | MaterialInstance | 0.00 |  |  | A50 | no |  |
| `/Game/Levels/Halo1/Solo/A50/Landscape/Materials/MM_Landscape_A50` | Material | 0.13 |  |  | A50 | no |  |
| `/Game/Levels/Halo1/Solo/A50/Landscape/VirtualTexture/LandscapeRVTHeight_A50` | RuntimeVirtualTexture | 0.00 |  |  | A50,D20 | no |  |
| `/Game/Levels/Halo1/Solo/A50/Landscape/VirtualTexture/LandscapeRVT_A50` | RuntimeVirtualTexture | 0.00 |  |  | A50,D20 | no |  |
| `/Game/Levels/Halo1/Solo/B30/Landscape/LayerInfo/LL_Flat_Sand_LayerInfo` | LandscapeLayerInfo | 0.00 |  |  | B30 | no |  |
| `/Game/Levels/Halo1/Solo/B30/Landscape/LayerInfo/LL_Grass_LayerInfo` | LandscapeLayerInfo | 0.00 |  |  | B30 | no |  |
| `/Game/Levels/Halo1/Solo/B30/Landscape/LayerInfo/LL_Hide_Decorators_LayerInfo` | LandscapeLayerInfo | 0.00 |  |  | B30 | no |  |
| `/Game/Levels/Halo1/Solo/B30/Landscape/LayerInfo/LL_RippledSand_LayerInfo` | LandscapeLayerInfo | 0.00 |  |  | B30 | no |  |
| `/Game/Levels/Halo1/Solo/B30/Landscape/LayerInfo/LL_Rock_LayerInfo` | LandscapeLayerInfo | 0.00 |  |  | B30 | no |  |
| `/Game/Levels/Halo1/Solo/B30/Landscape/LayerInfo/LL_Sand_Debris_LayerInfo` | LandscapeLayerInfo | 0.00 |  |  | B30 | no |  |
| `/Game/Levels/Halo1/Solo/B30/Landscape/LayerInfo/LL_Sand_LayerInfo` | LandscapeLayerInfo | 0.00 |  |  | B30 | no |  |
| `/Game/Levels/Halo1/Solo/B30/Landscape/LayerInfo/LL_Stones_LayerInfo` | LandscapeLayerInfo | 0.00 |  |  | B30 | no |  |
| `/Game/Levels/Halo1/Solo/B30/Landscape/LayerInfo/LL_wetness_LayerInfo` | LandscapeLayerInfo | 0.00 |  |  | B30 | no | wet variant |
| `/Game/Levels/Halo1/Solo/B30/Landscape/Materials/MI_Landscape_B30` | MaterialInstance | 0.13 |  |  | B30 | no |  |
| `/Game/Levels/Halo1/Solo/B30/Landscape/Materials/MI_Landscape_B30_mask` | MaterialInstance | 0.00 |  |  | B30 | no |  |
| `/Game/Levels/Halo1/Solo/B30/Landscape/Materials/MM_Landscape_B30` | Material | 0.17 |  |  | B30 | no |  |
| `/Game/Levels/Halo1/Solo/B40/Landscape/LayerInfo/LL_Ice_LayerInfo` | LandscapeLayerInfo | 0.00 |  |  | B40,C45 | no |  |
| `/Game/Levels/Halo1/Solo/B40/Landscape/LayerInfo/LL_JaggedRock_LayerInfo` | LandscapeLayerInfo | 0.00 |  |  | B40,C45 | no |  |
| `/Game/Levels/Halo1/Solo/B40/Landscape/LayerInfo/LL_Rock_LayerInfo` | LandscapeLayerInfo | 0.00 |  |  | B40,C45 | no |  |
| `/Game/Levels/Halo1/Solo/B40/Landscape/LayerInfo/LL_RockyGravel_LayerInfo` | LandscapeLayerInfo | 0.00 |  |  | B40,C45 | no |  |
| `/Game/Levels/Halo1/Solo/B40/Landscape/LayerInfo/LL_SandyGravel_LayerInfo` | LandscapeLayerInfo | 0.00 |  |  | B40,C45 | no |  |
| `/Game/Levels/Halo1/Solo/B40/Landscape/LayerInfo/LL_SandyRockGravel_LayerInfo` | LandscapeLayerInfo | 0.00 |  |  | B40,C45 | no |  |
| `/Game/Levels/Halo1/Solo/B40/Landscape/LayerInfo/LL_SnowRock_LayerInfo` | LandscapeLayerInfo | 0.00 |  |  | B40,C45 | no | snow variant |
| `/Game/Levels/Halo1/Solo/B40/Landscape/LayerInfo/LL_Snow_LayerInfo` | LandscapeLayerInfo | 0.00 |  |  | B40,C45 | no | snow variant |
| `/Game/Levels/Halo1/Solo/B40/Landscape/LayerInfo/LL_SnowyGrass_LayerInfo` | LandscapeLayerInfo | 0.00 |  |  | B40,C45 | no | snow variant |
| `/Game/Levels/Halo1/Solo/B40/Landscape/LayerInfo/LL_Stone_LayerInfo` | LandscapeLayerInfo | 0.00 |  |  | B40,C45 | no |  |
| `/Game/Levels/Halo1/Solo/B40/Landscape/LayerInfo/LL_Wetness_LayerInfo` | LandscapeLayerInfo | 0.00 |  |  | B40,C45 | no | wet variant |
| `/Game/Levels/Halo1/Solo/B40/Landscape/Materials/MI_Landscape_B40` | MaterialInstance | 0.12 |  |  | B40,C45 | no |  |
| `/Game/Levels/Halo1/Solo/B40/Landscape/Materials/MM_Landscape_B40` | Material | 0.16 |  |  | B40,C45 | no |  |
| `/Game/Levels/Halo1/Solo/C10/Landscape/LayerInfo/LL_Global_Wetness_LayerInfo` | LandscapeLayerInfo | 0.00 |  |  | C10 | no | wet variant |
| `/Game/Levels/Halo1/Solo/C10/Landscape/LayerInfo/LL_Grass_LayerInfo` | LandscapeLayerInfo | 0.00 |  |  | C10 | no |  |
| `/Game/Levels/Halo1/Solo/C10/Landscape/LayerInfo/LL_Hide_Decorators_LayerInfo` | LandscapeLayerInfo | 0.00 |  |  | C10 | no |  |
| `/Game/Levels/Halo1/Solo/C10/Landscape/LayerInfo/LL_Leaves_Rotting_LayerInfo` | LandscapeLayerInfo | 0.00 |  |  | C10 | no |  |
| `/Game/Levels/Halo1/Solo/C10/Landscape/LayerInfo/LL_Rock_LayerInfo` | LandscapeLayerInfo | 0.00 |  |  | C10 | no |  |
| `/Game/Levels/Halo1/Solo/C10/Landscape/LayerInfo/LL_Root_LayerInfo` | LandscapeLayerInfo | 0.00 |  |  | C10 | no |  |
| `/Game/Levels/Halo1/Solo/C10/Landscape/LayerInfo/LL_Soil_LayerInfo` | LandscapeLayerInfo | 0.00 |  |  | C10 | no |  |
| `/Game/Levels/Halo1/Solo/C10/Landscape/LayerInfo/LL_Wet_Soil_LayerInfo` | LandscapeLayerInfo | 0.00 |  |  | C10 | no | wet variant |
| `/Game/Levels/Halo1/Solo/C10/Landscape/LayerInfo/LL_Wetness_LayerInfo` | LandscapeLayerInfo | 0.00 |  |  | C10 | no | wet variant |
| `/Game/Levels/Halo1/Solo/C10/Landscape/Material/MF_LL_Swamp_Ground_Grass_A` | MaterialFunction | 0.00 |  |  | C10 | no |  |
| `/Game/Levels/Halo1/Solo/C10/Landscape/Material/MF_LL_Swamp_Ground_Leaves_Rotting_A` | MaterialFunction | 0.00 |  |  | C10 | no |  |
| `/Game/Levels/Halo1/Solo/C10/Landscape/Material/MF_LL_Swamp_Ground_Rock_A` | MaterialFunction | 0.00 |  |  | C10 | no |  |
| `/Game/Levels/Halo1/Solo/C10/Landscape/Material/MF_LL_Swamp_Ground_Soil_A` | MaterialFunction | 0.00 |  |  | C10 | no |  |
| `/Game/Levels/Halo1/Solo/C10/Landscape/Material/MF_LL_Swamp_Ground_Soil_Wet_A` | MaterialFunction | 0.00 |  |  | C10 | no | wet variant |
| `/Game/Levels/Halo1/Solo/C10/Landscape/Material/MF_LL_Swamp_Ground_Tree_Root_A` | MaterialFunction | 0.00 |  |  | C10 | no |  |
| `/Game/Levels/Halo1/Solo/C10/Landscape/Material/MI_Landscape_C10` | MaterialInstance | 0.03 |  |  | C10 | no |  |
| `/Game/Levels/Halo1/Solo/C10/Landscape/Material/MI_Landscape_C10_Mask` | MaterialInstance | 0.05 |  |  | C10 | no |  |
| `/Game/Levels/Halo1/Solo/C10/Landscape/Material/MM_Landscape_C10` | Material | 0.06 |  |  | C10 | no |  |
| `/Game/Levels/Halo1/Solo/D20/Landscape/LayerInfo/LL_D20_CrackMud_LayerInfo` | LandscapeLayerInfo | 0.00 |  |  | D20 | no |  |
| `/Game/Levels/Halo1/Solo/D20/Landscape/LayerInfo/LL_D20_FreshMud_LayerInfo` | LandscapeLayerInfo | 0.00 |  |  | D20 | no |  |
| `/Game/Levels/Halo1/Solo/D20/Landscape/LayerInfo/LL_D20_Mud_LayerInfo` | LandscapeLayerInfo | 0.00 |  |  | D20 | no |  |
| `/Game/Levels/Halo1/Solo/D20/Landscape/LayerInfo/LL_D20_Rock_LayerInfo` | LandscapeLayerInfo | 0.00 |  |  | D20 | no |  |
| `/Game/Levels/Halo1/Solo/D20/Landscape/LayerInfo/LL_D20_Soil_LayerInfo` | LandscapeLayerInfo | 0.00 |  |  | D20 | no |  |
| `/Game/Levels/Halo1/Solo/D20/Landscape/Materials/MF_LL_Canyon_Ground_CrackMud_D20` | MaterialFunction | 0.00 |  |  | D20 | no |  |
| `/Game/Levels/Halo1/Solo/D20/Landscape/Materials/MF_LL_Canyon_Ground_FreshMud_D20` | MaterialFunction | 0.00 |  |  | D20 | no |  |
| `/Game/Levels/Halo1/Solo/D20/Landscape/Materials/MF_LL_Canyon_Ground_Mud_D20` | MaterialFunction | 0.00 |  |  | D20 | no |  |
| `/Game/Levels/Halo1/Solo/D20/Landscape/Materials/MF_LL_Canyon_Ground_Rock_D20` | MaterialFunction | 0.00 |  |  | D20 | no |  |
| `/Game/Levels/Halo1/Solo/D20/Landscape/Materials/MF_LL_Canyon_Ground_Soil_D20` | MaterialFunction | 0.00 |  |  | D20 | no |  |
| `/Game/Levels/Halo1/Solo/D20/Landscape/Materials/MI_Landscape_D20` | MaterialInstance | 0.11 |  |  | D20 | no |  |
| `/Game/Levels/Halo1/Solo/D20/Landscape/Materials/MM_Landscape_D20` | Material | 0.12 |  |  | D20 | no |  |
| `/Game/Levels/Halo1/Solo/D40/Landscape/LayerInfo/LL_Agitated_Sand_LayerInfo` | LandscapeLayerInfo | 0.00 |  |  | D40 | no |  |
| `/Game/Levels/Halo1/Solo/D40/Landscape/LayerInfo/LL_Dark_Sand_LayerInfo` | LandscapeLayerInfo | 0.00 |  |  | D40 | no |  |
| `/Game/Levels/Halo1/Solo/D40/Landscape/LayerInfo/LL_Oily_Sand_LayerInfo` | LandscapeLayerInfo | 0.00 |  |  | D40 | no |  |
| `/Game/Levels/Halo1/Solo/D40/Landscape/LayerInfo/LL_Rippled_Sand_LayerInfo` | LandscapeLayerInfo | 0.00 |  |  | D40 | no |  |
| `/Game/Levels/Halo1/Solo/D40/Landscape/LayerInfo/LL_Rocky_Sand_LayerInfo` | LandscapeLayerInfo | 0.00 |  |  | D40 | no |  |
| `/Game/Levels/Halo1/Solo/D40/Landscape/LayerInfo/LL_Wetness_LayerInfo` | LandscapeLayerInfo | 0.00 |  |  | D40 | no | wet variant |
| `/Game/Levels/Halo1/Solo/D40/Landscape/LayerInfo_Vista/LL_Agitated_Sand_Vista_LayerInfo` | LandscapeLayerInfo | 0.00 |  |  | D40 | no |  |
| `/Game/Levels/Halo1/Solo/D40/Landscape/LayerInfo_Vista/LL_Dark_Sand_Vista_LayerInfo` | LandscapeLayerInfo | 0.00 |  |  | D40 | no |  |
| `/Game/Levels/Halo1/Solo/D40/Landscape/LayerInfo_Vista/LL_Flat_Sand_Vista_LayerInfo` | LandscapeLayerInfo | 0.00 |  |  | D40 | no |  |
| `/Game/Levels/Halo1/Solo/D40/Landscape/LayerInfo_Vista/LL_Oily_Sand_Vista_LayerInfo` | LandscapeLayerInfo | 0.00 |  |  | D40 | no |  |
| `/Game/Levels/Halo1/Solo/D40/Landscape/LayerInfo_Vista/LL_Rippled_Sand_Vista_LayerInfo` | LandscapeLayerInfo | 0.00 |  |  | D40 | no |  |
| `/Game/Levels/Halo1/Solo/D40/Landscape/LayerInfo_Vista/LL_Rocky_Sand_Vista_LayerInfo` | LandscapeLayerInfo | 0.00 |  |  | D40 | no |  |
| `/Game/Levels/Halo1/Solo/D40/Landscape/LayerInfo_Vista/LL_Sand_Debris_Vista_LayerInfo` | LandscapeLayerInfo | 0.00 |  |  | D40 | no |  |
| `/Game/Levels/Halo1/Solo/D40/Landscape/Materials/MF_LL_Desert_Sand` | MaterialFunction | 0.00 |  |  | D40 | no |  |
| `/Game/Levels/Halo1/Solo/D40/Landscape/Materials/MF_LL_Desert_Sand_Rocky` | MaterialFunction | 0.00 |  |  | D40 | no |  |
| `/Game/Levels/Halo1/Solo/D40/Landscape/Materials/MF_LL_Dry_Sand_A` | MaterialFunction | 0.00 |  |  | D40 | no |  |
| `/Game/Levels/Halo1/Solo/D40/Landscape/Materials/MF_LL_Ground_Dry_Rocky_A` | MaterialFunction | 0.00 |  |  | D40 | no |  |
| `/Game/Levels/Halo1/Solo/D40/Landscape/Materials/MF_LL_Sand_Oil` | MaterialFunction | 0.00 |  |  | D40 | no |  |
| `/Game/Levels/Halo1/Solo/D40/Landscape/Materials/MF_LL_Sand_Rippled_A` | MaterialFunction | 0.00 |  |  | D40 | no |  |
| `/Game/Levels/Halo1/Solo/D40/Landscape/Materials/MF_LL_Sand_Soot` | MaterialFunction | 0.00 |  |  | D40 | no |  |
| `/Game/Levels/Halo1/Solo/D40/Landscape/Materials/MI_Landscape_D40` | MaterialInstance | 0.12 |  |  | D40 | no |  |
| `/Game/Levels/Halo1/Solo/D40/Landscape/Materials/MI_Landscape_D40_mask` | MaterialInstance | 0.00 |  |  | D40 | no |  |
| `/Game/Levels/Halo1/Solo/D40/Landscape/Materials/MI_Vista_Landscape_D40` | MaterialInstance | 0.03 |  |  | D40 | no |  |
| `/Game/Levels/Halo1/Solo/D40/Landscape/Materials/MM_Landscape_D40` | Material | 0.14 |  |  | D40 | no |  |
| `/Game/Levels/Halo1/Solo/D40/Landscape/Materials/MM_Vista_Landscape_D40` | Material | 0.06 |  |  | D40 | no |  |

Textures: `/Game/Levels/Halo1/Solo/A50/Landscape/GrassLayer/Wild_Grass_vdilbaiia/T_Wild_Grass_vdilbaiia_4K_Green_D` (12.7 MB), `/Game/Levels/Halo1/Solo/A50/Landscape/Materials/T_Ground_Gravel_A_D` (2.8 MB), `/Game/Levels/Halo1/Solo/A50/Landscape/Materials/T_Ground_Gravel_A_N` (5.6 MB), `/Game/Levels/Halo1/Solo/A50/Landscape/Materials/T_Ground_Gravel_A_ORHG` (5.6 MB), `/Game/Levels/Halo1/Solo/A50/Landscape/Materials/T_SandDebris_phlvsop0_4K_NSVT_ORDp` (5.6 MB), `/Game/Levels/Halo1/Solo/A50/Landscape/Materials/T_SandDebris_seuiec0a_4K_ORDp` (5.6 MB), `/Game/Levels/Halo1/Solo/A50/Landscape/Materials/T_Sand_Debris_phlvsop0_4K_D` (2.8 MB), `/Game/Levels/Halo1/Solo/A50/Landscape/Materials/T_Sand_Debris_phlvsop0_4K_NSVT_N` (5.6 MB), `/Game/Levels/Halo1/Solo/A50/Landscape/Materials/T_Sand_Debris_phlvsop0_4K_NSVT_NSVT_D` (2.8 MB), `/Game/Levels/Halo1/Solo/A50/Landscape/Materials/T_Sand_Debris_seuiec0a_4K_D` (2.8 MB), `/Game/Levels/Halo1/Solo/A50/Landscape/Materials/T_Sand_Debris_seuiec0a_4K_N` (5.6 MB), `/Game/Levels/Halo1/Solo/A50/Landscape/Materials/T_ThaiBeachSand_tdsmeeko_2K_NSVT_ORDp` (5.6 MB), `/Game/Levels/Halo1/Solo/A50/Landscape/Materials/T_ThaiBeachSand_tdsmeeko_2K_VT_ORDp` (6.4 MB), `/Game/Levels/Halo1/Solo/A50/Landscape/Materials/T_Thai_Beach_Sand_tdsmeeko_2K_NSVT_D` (2.8 MB), `/Game/Levels/Halo1/Solo/A50/Landscape/Materials/T_Thai_Beach_Sand_tdsmeeko_2K_VT_D` (3.2 MB), `/Game/Levels/Halo1/Solo/A50/Landscape/Materials/T_Thai_Beach_Sand_tdsmeeko_2K_VT_N` (6.4 MB), `/Game/Levels/Halo1/Solo/C10/Landscape/Material/T_Swamp_Ground_Grass_A_4K_NSVT_D` (2.8 MB), `/Game/Levels/Halo1/Solo/C10/Landscape/Material/T_Swamp_Ground_Grass_A_4K_NSVT_N` (5.6 MB), `/Game/Levels/Halo1/Solo/C10/Landscape/Material/T_Swamp_Ground_Grass_A_4K_NSVT_ORHG` (5.6 MB), `/Game/Levels/Halo1/Solo/C10/Landscape/Material/T_Swamp_Ground_Leaves_Rotting_A_4K_NSVT_D` (2.8 MB), `/Game/Levels/Halo1/Solo/C10/Landscape/Material/T_Swamp_Ground_Leaves_Rotting_A_4K_NSVT_N` (5.6 MB), `/Game/Levels/Halo1/Solo/C10/Landscape/Material/T_Swamp_Ground_Leaves_Rotting_A_4K_NSVT_ORHG` (5.6 MB), `/Game/Levels/Halo1/Solo/C10/Landscape/Material/T_Swamp_Ground_Rock_A_4K_NSVT_D` (2.8 MB), `/Game/Levels/Halo1/Solo/C10/Landscape/Material/T_Swamp_Ground_Rock_A_4K_NSVT_N` (5.6 MB), `/Game/Levels/Halo1/Solo/C10/Landscape/Material/T_Swamp_Ground_Rock_A_4K_NSVT_ORHG` (5.6 MB), `/Game/Levels/Halo1/Solo/C10/Landscape/Material/T_Swamp_Ground_Soil_A_4K_NSVT_D` (2.8 MB), `/Game/Levels/Halo1/Solo/C10/Landscape/Material/T_Swamp_Ground_Soil_A_4K_NSVT_N` (5.6 MB), `/Game/Levels/Halo1/Solo/C10/Landscape/Material/T_Swamp_Ground_Soil_A_4K_NSVT_ORHG` (5.6 MB), `/Game/Levels/Halo1/Solo/C10/Landscape/Material/T_Swamp_Ground_Soil_Wet_A_4K_NSVT_D` (2.8 MB), `/Game/Levels/Halo1/Solo/C10/Landscape/Material/T_Swamp_Ground_Soil_Wet_A_4K_NSVT_N` (5.6 MB), `/Game/Levels/Halo1/Solo/C10/Landscape/Material/T_Swamp_Ground_Soil_Wet_A_4K_NSVT_ORHG` (5.6 MB), `/Game/Levels/Halo1/Solo/C10/Landscape/Material/T_Swamp_Ground_Tree_Root_A_4K_NSVT_D` (2.8 MB), `/Game/Levels/Halo1/Solo/C10/Landscape/Material/T_Swamp_Ground_Tree_Root_A_4K_NSVT_N` (5.6 MB), `/Game/Levels/Halo1/Solo/C10/Landscape/Material/T_Swamp_Ground_Tree_Root_A_4K_NSVT_ORHG` (5.6 MB), `/Game/Levels/Halo1/Solo/D20/Landscape/Materials/T_Canyon_Ground_Burn_4K_D` (2.8 MB), `/Game/Levels/Halo1/Solo/D20/Landscape/Materials/T_Canyon_Ground_Burn_4K_N` (5.6 MB), `/Game/Levels/Halo1/Solo/D20/Landscape/Materials/T_Canyon_Ground_CrackMud_4K_D` (2.8 MB), `/Game/Levels/Halo1/Solo/D20/Landscape/Materials/T_Canyon_Ground_CrackMud_4K_N` (5.6 MB), `/Game/Levels/Halo1/Solo/D20/Landscape/Materials/T_Canyon_Ground_CrackMud_4K_ORHG` (5.6 MB), `/Game/Levels/Halo1/Solo/D20/Landscape/Materials/T_Canyon_Ground_FreshMud_4K_D` (2.8 MB), `/Game/Levels/Halo1/Solo/D20/Landscape/Materials/T_Canyon_Ground_FreshMud_4K_N` (5.6 MB), `/Game/Levels/Halo1/Solo/D20/Landscape/Materials/T_Canyon_Ground_FreshMud_4K_ORHG` (5.6 MB), `/Game/Levels/Halo1/Solo/D20/Landscape/Materials/T_Canyon_Ground_Mud_4K_D` (2.8 MB), `/Game/Levels/Halo1/Solo/D20/Landscape/Materials/T_Canyon_Ground_Mud_4K_N` (5.6 MB), `/Game/Levels/Halo1/Solo/D20/Landscape/Materials/T_Canyon_Ground_Mud_4K_ORHG` (5.6 MB), `/Game/Levels/Halo1/Solo/D20/Landscape/Materials/T_Canyon_Ground_Rocky_4K_N` (5.6 MB), `/Game/Levels/Halo1/Solo/D20/Landscape/Materials/T_Canyon_Ground_Rocky_4K_ORHG` (5.6 MB), `/Game/Levels/Halo1/Solo/D20/Landscape/Materials/T_Canyon_Ground_Rocky_4k_D` (2.8 MB), `/Game/Levels/Halo1/Solo/D20/Landscape/Materials/T_Canyon_Ground_Soil_4K_D` (2.8 MB), `/Game/Levels/Halo1/Solo/D20/Landscape/Materials/T_Canyon_Ground_Soil_4K_N` (5.6 MB), `/Game/Levels/Halo1/Solo/D20/Landscape/Materials/T_Canyon_Ground_Soil_4K_ORHG` (5.6 MB), `/Game/Levels/Halo1/Solo/D40/Landscape/Materials/Textures/Desert_Sand/T_wkjgche_4K_N` (5.6 MB), `/Game/Levels/Halo1/Solo/D40/Landscape/Materials/Textures/Desert_Sand/T_wkjgche_4K_ORDp` (5.6 MB), `/Game/Levels/Halo1/Solo/D40/Landscape/Materials/Textures/Desert_Sand/T_wkjgche_Black_4K_D` (2.8 MB), `/Game/Levels/Halo1/Solo/D40/Landscape/Materials/Textures/Desert_Sand/T_wkjgche_Darker_4K_D` (2.8 MB), `/Game/Levels/Halo1/Solo/D40/Landscape/Materials/Textures/Desert_Sand_Rocky/T_xfgpdgj_4K_N` (5.6 MB), `/Game/Levels/Halo1/Solo/D40/Landscape/Materials/Textures/Desert_Sand_Rocky/T_xfgpdgj_4K_ORDp` (5.6 MB), `/Game/Levels/Halo1/Solo/D40/Landscape/Materials/Textures/Desert_Sand_Rocky/T_xfgpdgj_Darker_4K_D` (2.8 MB), `/Game/Levels/Halo1/Solo/D40/Landscape/Materials/Textures/Dry_Sand/T_xfipfar_4K_N` (5.6 MB), `/Game/Levels/Halo1/Solo/D40/Landscape/Materials/Textures/Dry_Sand/T_xfipfar_Darker_4K_D` (2.8 MB), `/Game/Levels/Halo1/Solo/D40/Landscape/Materials/Textures/Rippled_Sand/T_xd0mda1_Darker_NSVT_4K_D` (2.8 MB), `/Game/Levels/Halo1/Solo/D40/Landscape/Materials/Textures/Rippled_Sand/T_xd0mda1_Darker_VT_4K_D` (3.2 MB), `/Game/Levels/Halo1/Solo/D40/Landscape/Materials/Textures/Rippled_Sand/T_xd0mda1_NSVT_4K_N` (5.6 MB), `/Game/Levels/Halo1/Solo/D40/Landscape/Materials/Textures/Rippled_Sand/T_xd0mda1_NSVT_4k_ORDp` (5.6 MB), `/Game/Levels/Halo1/Solo/D40/Landscape/Materials/Textures/Rippled_Sand/T_xd0mda1_VT_4K_N` (6.4 MB), `/Game/Levels/Halo1/Solo/D40/Landscape/Materials/Textures/Rippled_Sand/T_xd0mda1_VT_4k_ORDp` (6.4 MB), `/Game/Levels/Halo1/Solo/D40/Landscape/Materials/Textures/Sand_Desert/T_xfltaax_4K_NSVT_N` (5.6 MB), `/Game/Levels/Halo1/Solo/D40/Landscape/Materials/Textures/Sand_Desert/T_xfltaax_4K_VT_N` (6.4 MB), `/Game/Levels/Halo1/Solo/D40/Landscape/Materials/Textures/Sand_Desert/T_xfltaax_4K_VT_ORDp` (6.4 MB), `/Game/Levels/Halo1/Solo/D40/Landscape/Materials/Textures/Sand_Desert/T_xfltaax_Darker_4K_NSVT_D` (2.8 MB), `/Game/Levels/Halo1/Solo/D40/Landscape/Materials/Textures/Sand_Desert/T_xfltaax_Darker_4K_VT_D` (3.2 MB), `/Game/Levels/Halo1/Solo/D40/Landscape/Materials/Textures/Sand_Oil/T_Sand_Oiil_D` (2.8 MB), `/Game/Levels/Halo1/Solo/D40/Landscape/Materials/Textures/Sand_Oil/T_Sand_Oil_02_N` (5.6 MB), `/Game/Levels/Halo1/Solo/D40/Landscape/Materials/Textures/Sand_Oil/T_Sand_Oil_02_ORDp` (5.6 MB), `/Game/Levels/Halo1/Solo/D40/Landscape/Materials/Textures/T_ThaiBeachSand_tefgafrk_2K_ORHG` (6.4 MB), `/Game/Levels/Halo1/Solo/D40/Landscape/Materials/Textures/T_Thai_Beach_Sand_tefgafrk_Darker_2k_D` (3.2 MB), `/Game/Levels/Halo1/Solo/D40/Landscape/Materials/Textures/T_Thai_Beach_Sand_tefgafrk_Lighter_2k_D` (3.2 MB)

*Group note:* MM_/MI_Landscape_* masters, LL_* layer infos and MF_LL_* layer functions (0K stubs that reference textures elsewhere). They need landscape layer weights; treat as recipes and texture sources, not drop-in materials

### Megascans foliage master materials (48)

*Where on PWR:* -

| path | kind | MB | verts | bounds m | levels | PWR | note |
|---|---|---|---|---|---|---|---|
| `/Game/MSPresets/Foliage_Material/Foliage_Material` | Material | 0.05 |  |  | B30 | no |  |
| `/Game/MSPresets/MS_Foliage_Material/MasterMaterials/MA_Foliage` | Material | 0.14 |  |  | C10 | no |  |
| `/Game/MSPresets/MS_Foliage_Material/MaterialFunctions/Foliage/MF_AdvancedWind` | MaterialFunction | 0.00 |  |  | C10 | no |  |
| `/Game/MSPresets/MS_Foliage_Material/MaterialFunctions/Foliage/MF_AdvancedWind_Level` | MaterialFunction | 0.00 |  |  | C10 | no |  |
| `/Game/MSPresets/MS_Foliage_Material/MaterialFunctions/Foliage/MF_BarkDetailer` | MaterialFunction | 0.00 |  |  | C10 | no |  |
| `/Game/MSPresets/MS_Foliage_Material/MaterialFunctions/Foliage/MF_BranchBlending` | MaterialFunction | 0.00 |  |  | C10 | no |  |
| `/Game/MSPresets/MS_Foliage_Material/MaterialFunctions/Foliage/MF_DecorationBlending` | MaterialFunction | 0.00 |  |  | C10 | no |  |
| `/Game/MSPresets/MS_Foliage_Material/MaterialFunctions/Foliage/MF_DefaultLit_Trunk` | MaterialFunction | 0.00 |  |  | C10 | no |  |
| `/Game/MSPresets/MS_Foliage_Material/MaterialFunctions/Foliage/MF_GenerateBranchMask` | MaterialFunction | 0.00 |  |  | B30,C10,E20 | no |  |
| `/Game/MSPresets/MS_Foliage_Material/MaterialFunctions/Foliage/MF_HealthSeason` | MaterialFunction | 0.00 |  |  | C10 | no |  |
| `/Game/MSPresets/MS_Foliage_Material/MaterialFunctions/Foliage/MF_LightInfluenceColorVariation` | MaterialFunction | 0.00 |  |  | B30,C10,E20 | no |  |
| `/Game/MSPresets/MS_Foliage_Material/MaterialFunctions/Foliage/MF_Opacity` | MaterialFunction | 0.00 |  |  | C10 | no |  |
| `/Game/MSPresets/MS_Foliage_Material/MaterialFunctions/Foliage/MF_Roughness` | MaterialFunction | 0.00 |  |  | C10 | no |  |
| `/Game/MSPresets/MS_Foliage_Material/MaterialFunctions/Foliage/MF_SimpleWind` | MaterialFunction | 0.00 |  |  | C10 | no |  |
| `/Game/MSPresets/MS_Foliage_Material/MaterialFunctions/Foliage/MF_TwoSidedRoughness` | MaterialFunction | 0.00 |  |  | B30,C10,E20 | no |  |
| `/Game/MSPresets/MS_Foliage_Material/MaterialFunctions/Foliage/MF_TwoSided_Decoration` | MaterialFunction | 0.00 |  |  | C10 | no |  |
| `/Game/MSPresets/MS_Foliage_Material/MaterialFunctions/Foliage/MF_TwoSided_Leaves` | MaterialFunction | 0.00 |  |  | C10 | no |  |
| `/Game/MSPresets/MS_Foliage_Material/MaterialFunctions/Foliage/MF_WindGust` | MaterialFunction | 0.00 |  |  | C10 | no |  |
| `/Game/MSPresets/MS_Foliage_Material/MaterialFunctions/Foliage/MF_WorldspaceColorVariation` | MaterialFunction | 0.00 |  |  | C10 | no |  |
| `/Game/MSPresets/MS_Foliage_Material/MaterialFunctions/Foliage/MF_adjustBaseColor` | MaterialFunction | 0.00 |  |  | C10 | no |  |
| `/Game/MSPresets/MS_Foliage_Material/MaterialFunctions/Foliage/MF_adjustNormal` | MaterialFunction | 0.00 |  |  | C10 | no |  |
| `/Game/MSPresets/MS_Foliage_Material/MaterialFunctions/Foliage/MF_adjustTwoSidedBaseColor` | MaterialFunction | 0.00 |  |  | C10 | no |  |
| `/Game/MSPresets/MS_Foliage_Material/MaterialFunctions/Foliage/MF_adjustTwoSidedNormal` | MaterialFunction | 0.00 |  |  | B30,C10,C20,C45,D20,E20,E30 | no |  |
| `/Game/MSPresets/MS_Foliage_Material/MaterialFunctions/Foliage/MF_generateSpecular` | MaterialFunction | 0.00 |  |  | C10 | no |  |
| `/Game/MSPresets/MS_Foliage_Material/MaterialFunctions/Foliage/MF_generateTranslucency` | MaterialFunction | 0.00 |  |  | B30,C10,E20 | no |  |
| `/Game/MSPresets/MS_Foliage_Material/MaterialFunctions/Foliage/MF_generateTwoSidedSpecular` | MaterialFunction | 0.00 |  |  | B30,C10,E20 | no |  |
| `/Game/MSPresets/MS_Foliage_Material_LATEST/MaterialFunctions/Foliage/MF_GenerateBranchMask` | MaterialFunction | 0.00 |  |  | E20 | no |  |
| `/Game/MSPresets/MS_Foliage_Material_LATEST/MaterialFunctions/Foliage/MF_LocalGradient_Z` | MaterialFunction | 0.00 |  |  | E20 | no |  |
| `/Game/MSPresets/MS_Foliage_Material_LATEST/MaterialFunctions/Foliage/MF_SimpleWind` | MaterialFunction | 0.00 |  |  | E20 | no |  |
| `/Game/MSPresets/MS_Foliage_Material_LATEST/MaterialFunctions/Foliage/MF_TwoSidedBaseColor` | MaterialFunction | 0.00 |  |  | E20 | no |  |
| `/Game/MSPresets/MS_Foliage_Material_LATEST/MaterialFunctions/Foliage/MF_WindGust` | MaterialFunction | 0.00 |  |  | E20 | no |  |
| `/Game/MSPresets/MS_Foliage_Material_LATEST/MaterialFunctions/Foliage/MF_WorldspaceColorVariation` | MaterialFunction | 0.00 |  |  | E20 | no |  |
| `/Game/MSPresets/M_MS_Billboard_Material/M_MS_Billboard_Material` | Material | 0.05 |  |  | A50,B30,C10,E20 | no |  |
| `/Game/MSPresets/M_MS_Default_Fuzz_Material/M_MS_Default_Fuzz_Material` | Material | 0.01 |  |  | A30,B40,C45 | no |  |
| `/Game/MSPresets/M_MS_Default_Fuzz_Material_VT/Functions/MF_Fuzz` | MaterialFunction | 0.00 |  |  |  | no |  |
| `/Game/MSPresets/M_MS_Default_Fuzz_Material_VT/M_MS_Default_Fuzz_Material_VT` | Material | 0.01 |  |  | A30,B40,C10,C45,E20 | no | virtual-texture copy |
| `/Game/MSPresets/M_MS_Default_Material/M_MS_Default_Material` | Material | 0.01 |  |  | A30,B30,B40,C45,E10,E20,E30 | no |  |
| `/Game/MSPresets/M_MS_Default_Material_VT/M_MS_Default_Material_VT` | Material | 0.03 |  |  | A30,B30,B40,C10,C45,D20,E20 | no | virtual-texture copy |
| `/Game/MSPresets/M_MS_Default_Transmission_Material/M_MS_Default_Transmission_Material` | Material | 0.01 |  |  | B40 | no |  |
| `/Game/MSPresets/M_MS_Foliage_Material/M_MS_Foliage_Material_VT` | Material | 0.05 |  |  | A50,B30,C10,E20 | no | virtual-texture copy |
| `/Game/MSPresets/M_MS_Surface_Material_VT/M_MS_Surface_Material_VT` | Material | 0.01 |  |  | C10,D20,E10,E30 | no | virtual-texture copy |

Textures: `/Game/MSPresets/MSVTTextures/BlackPlaceholder` (0.1 MB), `/Game/MSPresets/MSVTTextures/DefaultDiffuse` (0.9 MB), `/Game/MSPresets/MSVTTextures/Placeholder_Normal` (0.1 MB), `/Game/MSPresets/MS_Foliage_Material/AssetZooMaterials/T_FloorGrid` (0.7 MB), `/Game/MSPresets/MS_Foliage_Material/MaterialFunctions/Textures/T_WindNoise` (11.2 MB), `/Game/MSPresets/MS_Foliage_Material_LATEST/MaterialFunctions/Textures/T_WindNoise` (2.8 MB), `/Game/MS_GardenLawn/Master_Materials/noise_mask` (2.8 MB)

*Group note:* Masters behind the Megascans plants (wind, subsurface); reference only

### Meadow flowers and ground cover (Megascans) (173)

*Where on PWR:* Meadow, verges and alpine grassland

| path | kind | MB | verts | bounds m | levels | PWR | note |
|---|---|---|---|---|---|---|---|
| `/Game/Megascans/3D_Assets/Blue_lupin_tjtjfinia/MI_Blue_Lupin` | MaterialInstance | 0.03 |  |  | E30 | no | [foliage] |
| `/Game/Megascans/3D_Plants/Goldenrods_xg1lbfxia/MI_Goldenrods_xg1lbfxia_4K` | MaterialInstance | 0.03 |  |  | A30 | no | [foliage] |
| `/Game/Megascans/3D_Plants/Goldenrods_xg1lbfxia/S_Goldenrods_xg1lbfxia_Var1_lod0_Traced` | StaticMesh | 16.04 | 606,295 | 0.52x0.46x1.73 | A30 | no | very dense: confirm Nanite before placing many [foliage] |
| `/Game/Megascans/3D_Plants/Goldenrods_xg1lbfxia/S_Goldenrods_xg1lbfxia_Var2_lod0_Traced` | StaticMesh | 7.08 | 256,548 | 0.47x0.5x1.41 | A30 | no | [foliage] |
| `/Game/Megascans/3D_Plants/Goldenrods_xg1lbfxia/S_Goldenrods_xg1lbfxia_Var3_lod0_Traced` | StaticMesh | 1.19 | 29,468 | 0.64x0.63x1.28 | A30 | no | [foliage] |
| `/Game/Megascans/3D_Plants/Kikuyu_Grass_wiljearqx/Foliage/FT_Kikuyu_Grass_wiljearqx_Var12_lod0` | FoliageType | 0.00 |  |  | C10 | no | [foliage] |
| `/Game/Megascans/3D_Plants/Kikuyu_Grass_wiljearqx/Foliage/FT_Kikuyu_Grass_wiljearqx_Var15_lod0` | FoliageType | 0.00 |  |  | C10 | no | [foliage] |
| `/Game/Megascans/3D_Plants/Kikuyu_Grass_wiljearqx/Foliage/FT_Kikuyu_Grass_wiljearqx_Var2_lod0` | FoliageType | 0.00 |  |  | C10 | no | [foliage] |
| `/Game/Megascans/3D_Plants/Leafy_Dandelions_qmbrl/FT_Leafy_Dandelions_qmbrl_01` | FoliageType | 0.00 |  |  | A30 | no | [foliage] |
| `/Game/Megascans/3D_Plants/Leafy_Dandelions_qmbrl/FT_Leafy_Dandelions_qmbrl_02` | FoliageType | 0.00 |  |  | A30 | no | [foliage] |
| `/Game/Megascans/3D_Plants/Leafy_Dandelions_qmbrl/FT_Leafy_Dandelions_qmbrl_03` | FoliageType | 0.00 |  |  | A30 | no | [foliage] |
| `/Game/Megascans/3D_Plants/Leafy_Dandelions_qmbrl/MI_Leafy_Dandelions_qmbrl_01` | MaterialInstance | 0.03 |  |  | A30 | no | [foliage] |
| `/Game/Megascans/3D_Plants/Leafy_Dandelions_qmbrl/SM_Leafy_Dandelions_qmbrl_01` | StaticMesh | 0.10 | 819 | 0.45x0.45x0.23 | A30 | no | [foliage] |
| `/Game/Megascans/3D_Plants/Leafy_Dandelions_qmbrl/SM_Leafy_Dandelions_qmbrl_01_Traced` | StaticMesh | 0.49 | 18,082 | 0.44x0.44x0.23 | A30 | no | [foliage] |
| `/Game/Megascans/3D_Plants/Leafy_Dandelions_qmbrl/SM_Leafy_Dandelions_qmbrl_02` | StaticMesh | 0.08 | 495 | 0.27x0.26x0.1 | A30 | no | [foliage] |
| `/Game/Megascans/3D_Plants/Leafy_Dandelions_qmbrl/SM_Leafy_Dandelions_qmbrl_02_Traced` | StaticMesh | 0.21 | 7,612 | 0.27x0.25x0.1 | A30 | no | [foliage] |
| `/Game/Megascans/3D_Plants/Leafy_Dandelions_qmbrl/SM_Leafy_Dandelions_qmbrl_03` | StaticMesh | 0.09 | 657 | 0.43x0.4x0.24 | A30 | no | [foliage] |
| `/Game/Megascans/3D_Plants/Leafy_Dandelions_qmbrl/SM_Leafy_Dandelions_qmbrl_03_Traced` | StaticMesh | 0.42 | 16,036 | 0.42x0.39x0.23 | A30 | no | [foliage] |
| `/Game/Megascans/3D_Plants/Tall_Grass_rbeki/MI_Tall_Grass_rbeki_01` | MaterialInstance | 0.03 |  |  | A30 | no | [foliage]; sibling used by PWR |
| `/Game/Megascans/3D_Plants/Tall_Grass_rbeki/SM_Tall_Grass_rbeki_01` | StaticMesh | 0.19 | 1,660 | 0.6x0.67x0.9 | A30 | yes | [foliage] |
| `/Game/Megascans/3D_Plants/Tundra_Grass_wk2oaeyqx/MI_Tundra_Grass_wk2oaeyqx_4K` | MaterialInstance | 0.03 |  |  | C10 | no | [foliage] |
| `/Game/Megascans/3D_Plants/WhiteWindflower/FT_WhiteWindflower_02` | FoliageType | 0.00 |  |  | A30 | no | [foliage]; sibling used by PWR |
| `/Game/Megascans/3D_Plants/WhiteWindflower/FT_WhiteWindflower_04` | FoliageType | 0.00 |  |  | A30 | no | [foliage]; sibling used by PWR |
| `/Game/Megascans/3D_Plants/WhiteWindflower/MI_WhiteWindflower_01` | MaterialInstance | 0.03 |  |  | A30,C10 | no | [foliage]; sibling used by PWR |
| `/Game/Megascans/3D_Plants/WhiteWindflower/SM_WhiteWindflower_02` | StaticMesh | 0.36 | 7,174 | 0.83x0.74x0.95 | A30 | yes | [foliage] |
| `/Game/Megascans/3D_Plants/WhiteWindflower/SM_WhiteWindflower_04` | StaticMesh | 0.25 | 5,149 | 0.81x0.8x0.86 | A30 | no | [foliage]; sibling used by PWR |
| `/Game/Megascans/3D_Plants/WhiteWindflower/SM_WhiteWindflower_05` | StaticMesh | 1.74 | 39,684 | 0.8x0.79x0.84 | A30 | yes | [foliage] |
| `/Game/Megascans/3D_Plants/WhiteWindflower/SM_WhiteWindflower_07` | StaticMesh | 0.25 | 4,947 | 0.77x0.76x0.62 | C10 | no | [foliage]; sibling used by PWR |
| `/Game/Megascans/3D_Plants/Wild_Grass_vczndjqja/Foliage/FT_Wild_Grass_vczndjqja_Var10_lod0` | FoliageType | 0.00 |  |  | B30 | no | [foliage] |
| `/Game/Megascans/3D_Plants/Wild_Grass_vczndjqja/Foliage/FT_Wild_Grass_vczndjqja_Var11_lod0` | FoliageType | 0.00 |  |  | B30 | no | [foliage] |
| `/Game/Megascans/3D_Plants/Wild_Grass_vczndjqja/Foliage/FT_Wild_Grass_vczndjqja_Var12_lod0` | FoliageType | 0.00 |  |  | B30 | no | [foliage] |
| `/Game/Megascans/3D_Plants/Wild_Grass_vczndjqja/Foliage/FT_Wild_Grass_vczndjqja_Var13_lod0` | FoliageType | 0.00 |  |  | B30 | no | [foliage] |
| `/Game/Megascans/3D_Plants/Wild_Grass_vczndjqja/Foliage/FT_Wild_Grass_vczndjqja_Var14_lod0` | FoliageType | 0.00 |  |  | B30 | no | [foliage] |
| `/Game/Megascans/3D_Plants/Wild_Grass_vczndjqja/Foliage/FT_Wild_Grass_vczndjqja_Var15_lod0` | FoliageType | 0.00 |  |  | B30 | no | [foliage] |
| `/Game/Megascans/3D_Plants/Wild_Grass_vczndjqja/Foliage/FT_Wild_Grass_vczndjqja_Var16_lod0` | FoliageType | 0.00 |  |  | B30 | no | [foliage] |
| `/Game/Megascans/3D_Plants/Wild_Grass_vczndjqja/Foliage/FT_Wild_Grass_vczndjqja_Var17_lod0` | FoliageType | 0.00 |  |  |  | no | [foliage] |
| `/Game/Megascans/3D_Plants/Wild_Grass_vczndjqja/Foliage/FT_Wild_Grass_vczndjqja_Var18_lod0` | FoliageType | 0.00 |  |  |  | no | [foliage] |
| `/Game/Megascans/3D_Plants/Wild_Grass_vczndjqja/Foliage/FT_Wild_Grass_vczndjqja_Var19_lod0` | FoliageType | 0.00 |  |  | B30 | no | [foliage] |
| `/Game/Megascans/3D_Plants/Wild_Grass_vczndjqja/Foliage/FT_Wild_Grass_vczndjqja_Var1_lod0` | FoliageType | 0.00 |  |  | B30 | no | [foliage] |
| `/Game/Megascans/3D_Plants/Wild_Grass_vczndjqja/Foliage/FT_Wild_Grass_vczndjqja_Var20_lod0` | FoliageType | 0.00 |  |  |  | no | [foliage] |
| `/Game/Megascans/3D_Plants/Wild_Grass_vczndjqja/Foliage/FT_Wild_Grass_vczndjqja_Var21_lod0` | FoliageType | 0.00 |  |  | A50,B30 | no | [foliage] |
| `/Game/Megascans/3D_Plants/Wild_Grass_vczndjqja/Foliage/FT_Wild_Grass_vczndjqja_Var22_lod0` | FoliageType | 0.00 |  |  |  | no | [foliage] |
| `/Game/Megascans/3D_Plants/Wild_Grass_vczndjqja/Foliage/FT_Wild_Grass_vczndjqja_Var2_lod0` | FoliageType | 0.00 |  |  |  | no | [foliage] |
| `/Game/Megascans/3D_Plants/Wild_Grass_vczndjqja/Foliage/FT_Wild_Grass_vczndjqja_Var3_lod0` | FoliageType | 0.00 |  |  |  | no | [foliage] |
| `/Game/Megascans/3D_Plants/Wild_Grass_vczndjqja/Foliage/FT_Wild_Grass_vczndjqja_Var4_lod0` | FoliageType | 0.00 |  |  |  | no | [foliage] |
| `/Game/Megascans/3D_Plants/Wild_Grass_vczndjqja/Foliage/FT_Wild_Grass_vczndjqja_Var5_lod0` | FoliageType | 0.00 |  |  | A50 | no | [foliage] |
| `/Game/Megascans/3D_Plants/Wild_Grass_vczndjqja/Foliage/FT_Wild_Grass_vczndjqja_Var6_lod0` | FoliageType | 0.00 |  |  | A50 | no | [foliage] |
| `/Game/Megascans/3D_Plants/Wild_Grass_vczndjqja/Foliage/FT_Wild_Grass_vczndjqja_Var7_lod0` | FoliageType | 0.00 |  |  |  | no | [foliage] |
| `/Game/Megascans/3D_Plants/Wild_Grass_vczndjqja/Foliage/FT_Wild_Grass_vczndjqja_Var8_lod0` | FoliageType | 0.00 |  |  |  | no | [foliage] |
| `/Game/Megascans/3D_Plants/Wild_Grass_vczndjqja/Foliage/FT_Wild_Grass_vczndjqja_Var9_lod0` | FoliageType | 0.00 |  |  |  | no | [foliage] |
| `/Game/Megascans/3D_Plants/Wild_Grass_vczndjqja/MI_Wild_Grass_vczndjqja_4K` | MaterialInstance | 0.05 |  |  | A50,B30 | no | [foliage]; sibling used by PWR |
| `/Game/Megascans/3D_Plants/Wild_Grass_vczndjqja/MI_Wild_Grass_vczndjqja_Billboard_4K` | MaterialInstance | 0.00 |  |  | A50,B30 | no | [foliage]; sibling used by PWR |
| `/Game/Megascans/3D_Plants/Wild_Grass_vczndjqja/S_Wild_Grass_vczndjqja_Var10_lod0` | StaticMesh | 0.02 | 85 | 0.27x0.23x0.01 | B30 | no | [foliage]; sibling used by PWR |
| `/Game/Megascans/3D_Plants/Wild_Grass_vczndjqja/S_Wild_Grass_vczndjqja_Var11_lod0` | StaticMesh | 0.01 | 17 | 0.22x0.18x0.0 | B30 | no | [foliage]; sibling used by PWR |
| `/Game/Megascans/3D_Plants/Wild_Grass_vczndjqja/S_Wild_Grass_vczndjqja_Var12_lod0` | StaticMesh | 0.39 | 2,659 | 1.22x1.32x0.7 | B30 | yes | [foliage] |
| `/Game/Megascans/3D_Plants/Wild_Grass_vczndjqja/S_Wild_Grass_vczndjqja_Var13_lod0` | StaticMesh | 0.01 | 17 | 0.15x0.15x0.0 | B30 | no | [foliage]; sibling used by PWR |
| `/Game/Megascans/3D_Plants/Wild_Grass_vczndjqja/S_Wild_Grass_vczndjqja_Var14_lod0` | StaticMesh | 0.01 | 17 | 0.13x0.12x0.0 | B30 | no | [foliage]; sibling used by PWR |
| `/Game/Megascans/3D_Plants/Wild_Grass_vczndjqja/S_Wild_Grass_vczndjqja_Var15_lod0` | StaticMesh | 0.01 | 17 | 0.17x0.17x0.0 | B30 | no | [foliage]; sibling used by PWR |
| `/Game/Megascans/3D_Plants/Wild_Grass_vczndjqja/S_Wild_Grass_vczndjqja_Var16_lod0` | StaticMesh | 0.78 | 8,657 | 1.31x1.32x0.7 | B30 | no | [foliage]; sibling used by PWR |
| `/Game/Megascans/3D_Plants/Wild_Grass_vczndjqja/S_Wild_Grass_vczndjqja_Var17_lod0` | StaticMesh | 0.97 | 10,754 | 1.09x1.09x0.59 |  | no | [foliage]; sibling used by PWR |
| `/Game/Megascans/3D_Plants/Wild_Grass_vczndjqja/S_Wild_Grass_vczndjqja_Var18_lod0` | StaticMesh | 0.81 | 7,946 | 1.23x1.0x0.53 |  | no | [foliage]; sibling used by PWR |
| `/Game/Megascans/3D_Plants/Wild_Grass_vczndjqja/S_Wild_Grass_vczndjqja_Var19_lod0` | StaticMesh | 0.44 | 2,882 | 1.09x1.21x0.83 | B30 | no | [foliage]; sibling used by PWR |
| `/Game/Megascans/3D_Plants/Wild_Grass_vczndjqja/S_Wild_Grass_vczndjqja_Var1_lod0` | StaticMesh | 0.86 | 8,770 | 1.58x1.49x0.9 | B30 | no | [foliage]; sibling used by PWR |
| `/Game/Megascans/3D_Plants/Wild_Grass_vczndjqja/S_Wild_Grass_vczndjqja_Var20_lod0` | StaticMesh | 0.29 | 2,618 | 1.03x0.7x0.57 |  | no | [foliage]; sibling used by PWR |
| `/Game/Megascans/3D_Plants/Wild_Grass_vczndjqja/S_Wild_Grass_vczndjqja_Var21_lod0` | StaticMesh | 0.08 | 1,146 | 0.89x0.76x0.9 | A50,B30 | no | [foliage]; sibling used by PWR |
| `/Game/Megascans/3D_Plants/Wild_Grass_vczndjqja/S_Wild_Grass_vczndjqja_Var22_lod0` | StaticMesh | 0.41 | 3,898 | 1.2x1.39x0.84 |  | no | [foliage]; sibling used by PWR |
| `/Game/Megascans/3D_Plants/Wild_Grass_vczndjqja/S_Wild_Grass_vczndjqja_Var2_lod0` | StaticMesh | 0.21 | 1,704 | 0.64x0.6x0.42 |  | no | [foliage]; sibling used by PWR |
| `/Game/Megascans/3D_Plants/Wild_Grass_vczndjqja/S_Wild_Grass_vczndjqja_Var3_lod0` | StaticMesh | 0.13 | 1,105 | 0.71x0.54x0.49 |  | no | [foliage]; sibling used by PWR |
| `/Game/Megascans/3D_Plants/Wild_Grass_vczndjqja/S_Wild_Grass_vczndjqja_Var4_lod0` | StaticMesh | 0.07 | 436 | 0.54x0.48x0.32 |  | no | [foliage]; sibling used by PWR |
| `/Game/Megascans/3D_Plants/Wild_Grass_vczndjqja/S_Wild_Grass_vczndjqja_Var5_lod0` | StaticMesh | 0.09 | 1,416 | 0.5x0.6x0.14 | A50 | no | [foliage]; sibling used by PWR |
| `/Game/Megascans/3D_Plants/Wild_Grass_vczndjqja/S_Wild_Grass_vczndjqja_Var6_lod0` | StaticMesh | 0.03 | 230 | 0.23x0.24x0.09 | A50 | no | [foliage]; sibling used by PWR |
| `/Game/Megascans/3D_Plants/Wild_Grass_vczndjqja/S_Wild_Grass_vczndjqja_Var7_lod0` | StaticMesh | 0.08 | 714 | 0.59x0.62x0.04 |  | no | [foliage]; sibling used by PWR |
| `/Game/Megascans/3D_Plants/Wild_Grass_vczndjqja/S_Wild_Grass_vczndjqja_Var8_lod0` | StaticMesh | 0.07 | 535 | 0.43x0.56x0.03 |  | no | [foliage]; sibling used by PWR |
| `/Game/Megascans/3D_Plants/Wild_Grass_vczndjqja/S_Wild_Grass_vczndjqja_Var9_lod0` | StaticMesh | 0.03 | 102 | 0.41x0.36x0.0 |  | no | [foliage]; sibling used by PWR |
| `/Game/Megascans/3D_Plants/Wild_Grass_vdilbaiia/Foliage/FT_Wild_Grass_vdilbaiia_Var10_lod0` | FoliageType | 0.00 |  |  |  | no | [foliage] |
| `/Game/Megascans/3D_Plants/Wild_Grass_vdilbaiia/Foliage/FT_Wild_Grass_vdilbaiia_Var11_lod0` | FoliageType | 0.00 |  |  | B30 | no | [foliage] |
| `/Game/Megascans/3D_Plants/Wild_Grass_vdilbaiia/Foliage/FT_Wild_Grass_vdilbaiia_Var12_lod0` | FoliageType | 0.00 |  |  | A50,B30 | no | [foliage] |
| `/Game/Megascans/3D_Plants/Wild_Grass_vdilbaiia/Foliage/FT_Wild_Grass_vdilbaiia_Var13_lod0` | FoliageType | 0.00 |  |  |  | no | [foliage] |
| `/Game/Megascans/3D_Plants/Wild_Grass_vdilbaiia/Foliage/FT_Wild_Grass_vdilbaiia_Var14_lod0` | FoliageType | 0.00 |  |  |  | no | [foliage] |
| `/Game/Megascans/3D_Plants/Wild_Grass_vdilbaiia/Foliage/FT_Wild_Grass_vdilbaiia_Var15_lod0` | FoliageType | 0.00 |  |  |  | no | [foliage] |
| `/Game/Megascans/3D_Plants/Wild_Grass_vdilbaiia/Foliage/FT_Wild_Grass_vdilbaiia_Var16_lod0` | FoliageType | 0.00 |  |  |  | no | [foliage] |
| `/Game/Megascans/3D_Plants/Wild_Grass_vdilbaiia/Foliage/FT_Wild_Grass_vdilbaiia_Var17_lod0` | FoliageType | 0.00 |  |  |  | no | [foliage] |
| `/Game/Megascans/3D_Plants/Wild_Grass_vdilbaiia/Foliage/FT_Wild_Grass_vdilbaiia_Var18_lod0` | FoliageType | 0.00 |  |  |  | no | [foliage] |
| `/Game/Megascans/3D_Plants/Wild_Grass_vdilbaiia/Foliage/FT_Wild_Grass_vdilbaiia_Var19_lod0` | FoliageType | 0.00 |  |  |  | no | [foliage] |
| `/Game/Megascans/3D_Plants/Wild_Grass_vdilbaiia/Foliage/FT_Wild_Grass_vdilbaiia_Var1_lod0` | FoliageType | 0.00 |  |  |  | no | [foliage] |
| `/Game/Megascans/3D_Plants/Wild_Grass_vdilbaiia/Foliage/FT_Wild_Grass_vdilbaiia_Var20_lod0` | FoliageType | 0.00 |  |  | B30 | no | [foliage] |
| `/Game/Megascans/3D_Plants/Wild_Grass_vdilbaiia/Foliage/FT_Wild_Grass_vdilbaiia_Var21_lod0` | FoliageType | 0.00 |  |  | A50 | no | [foliage] |
| `/Game/Megascans/3D_Plants/Wild_Grass_vdilbaiia/Foliage/FT_Wild_Grass_vdilbaiia_Var22_lod0` | FoliageType | 0.00 |  |  |  | no | [foliage] |
| `/Game/Megascans/3D_Plants/Wild_Grass_vdilbaiia/Foliage/FT_Wild_Grass_vdilbaiia_Var23_lod0` | FoliageType | 0.00 |  |  |  | no | [foliage] |
| `/Game/Megascans/3D_Plants/Wild_Grass_vdilbaiia/Foliage/FT_Wild_Grass_vdilbaiia_Var24_lod0` | FoliageType | 0.00 |  |  |  | no | [foliage] |
| `/Game/Megascans/3D_Plants/Wild_Grass_vdilbaiia/Foliage/FT_Wild_Grass_vdilbaiia_Var25_lod0` | FoliageType | 0.00 |  |  | A50 | no | [foliage] |
| `/Game/Megascans/3D_Plants/Wild_Grass_vdilbaiia/Foliage/FT_Wild_Grass_vdilbaiia_Var26_lod0` | FoliageType | 0.00 |  |  |  | no | [foliage] |
| `/Game/Megascans/3D_Plants/Wild_Grass_vdilbaiia/Foliage/FT_Wild_Grass_vdilbaiia_Var2_lod0` | FoliageType | 0.00 |  |  |  | no | [foliage] |
| `/Game/Megascans/3D_Plants/Wild_Grass_vdilbaiia/Foliage/FT_Wild_Grass_vdilbaiia_Var3_lod0` | FoliageType | 0.00 |  |  |  | no | [foliage] |
| `/Game/Megascans/3D_Plants/Wild_Grass_vdilbaiia/Foliage/FT_Wild_Grass_vdilbaiia_Var4_lod0` | FoliageType | 0.00 |  |  | B30 | no | [foliage] |
| `/Game/Megascans/3D_Plants/Wild_Grass_vdilbaiia/Foliage/FT_Wild_Grass_vdilbaiia_Var5_lod0` | FoliageType | 0.00 |  |  |  | no | [foliage] |
| `/Game/Megascans/3D_Plants/Wild_Grass_vdilbaiia/Foliage/FT_Wild_Grass_vdilbaiia_Var6_lod0` | FoliageType | 0.00 |  |  |  | no | [foliage] |
| `/Game/Megascans/3D_Plants/Wild_Grass_vdilbaiia/Foliage/FT_Wild_Grass_vdilbaiia_Var7_lod0` | FoliageType | 0.00 |  |  |  | no | [foliage] |
| `/Game/Megascans/3D_Plants/Wild_Grass_vdilbaiia/Foliage/FT_Wild_Grass_vdilbaiia_Var8_lod0` | FoliageType | 0.00 |  |  | A50 | no | [foliage] |
| `/Game/Megascans/3D_Plants/Wild_Grass_vdilbaiia/Foliage/FT_Wild_Grass_vdilbaiia_Var9_lod0` | FoliageType | 0.00 |  |  |  | no | [foliage] |
| `/Game/Megascans/3D_Plants/Wild_Grass_vdilbaiia/MI_Wild_Grass_vdilbaiia_4K` | MaterialInstance | 0.05 |  |  | A50,B30 | no | [foliage]; sibling used by PWR |
| `/Game/Megascans/3D_Plants/Wild_Grass_vdilbaiia/MI_Wild_Grass_vdilbaiia_Billboard_4K` | MaterialInstance | 0.00 |  |  | A50,B30 | no | [foliage]; sibling used by PWR |
| `/Game/Megascans/3D_Plants/Wild_Grass_vdilbaiia/S_Wild_Grass_vdilbaiia_Var10_lod0` | StaticMesh | 0.22 | 1,728 | 0.79x0.68x0.16 |  | no | [foliage]; sibling used by PWR |
| `/Game/Megascans/3D_Plants/Wild_Grass_vdilbaiia/S_Wild_Grass_vdilbaiia_Var11_lod0` | StaticMesh | 0.18 | 980 | 0.48x0.58x0.22 | B30 | no | [foliage]; sibling used by PWR |
| `/Game/Megascans/3D_Plants/Wild_Grass_vdilbaiia/S_Wild_Grass_vdilbaiia_Var12_lod0` | StaticMesh | 0.18 | 2,938 | 1.44x1.23x0.94 | A50,B30 | no | [foliage]; sibling used by PWR |
| `/Game/Megascans/3D_Plants/Wild_Grass_vdilbaiia/S_Wild_Grass_vdilbaiia_Var13_lod0` | StaticMesh | 0.24 | 1,290 | 0.68x0.68x0.25 |  | no | [foliage]; sibling used by PWR |
| `/Game/Megascans/3D_Plants/Wild_Grass_vdilbaiia/S_Wild_Grass_vdilbaiia_Var14_lod0` | StaticMesh | 0.06 | 450 | 0.77x0.67x0.04 |  | no | [foliage]; sibling used by PWR |
| `/Game/Megascans/3D_Plants/Wild_Grass_vdilbaiia/S_Wild_Grass_vdilbaiia_Var15_lod0` | StaticMesh | 0.04 | 166 | 0.71x0.62x0.08 |  | no | [foliage]; sibling used by PWR |
| `/Game/Megascans/3D_Plants/Wild_Grass_vdilbaiia/S_Wild_Grass_vdilbaiia_Var16_lod0` | StaticMesh | 0.01 | 29 | 0.18x0.2x0.0 |  | no | [foliage]; sibling used by PWR |
| `/Game/Megascans/3D_Plants/Wild_Grass_vdilbaiia/S_Wild_Grass_vdilbaiia_Var17_lod0` | StaticMesh | 0.01 | 25 | 0.22x0.13x0.0 |  | no | [foliage]; sibling used by PWR |
| `/Game/Megascans/3D_Plants/Wild_Grass_vdilbaiia/S_Wild_Grass_vdilbaiia_Var18_lod0` | StaticMesh | 0.01 | 25 | 0.17x0.18x0.0 |  | no | [foliage]; sibling used by PWR |
| `/Game/Megascans/3D_Plants/Wild_Grass_vdilbaiia/S_Wild_Grass_vdilbaiia_Var19_lod0` | StaticMesh | 0.01 | 27 | 0.15x0.22x0.0 |  | no | [foliage]; sibling used by PWR |
| `/Game/Megascans/3D_Plants/Wild_Grass_vdilbaiia/S_Wild_Grass_vdilbaiia_Var1_lod0` | StaticMesh | 0.72 | 9,103 | 2.23x2.03x1.29 |  | yes | [foliage] |
| `/Game/Megascans/3D_Plants/Wild_Grass_vdilbaiia/S_Wild_Grass_vdilbaiia_Var20_lod0` | StaticMesh | 1.00 | 12,080 | 0.73x0.98x0.71 | B30 | no | [foliage]; sibling used by PWR |
| `/Game/Megascans/3D_Plants/Wild_Grass_vdilbaiia/S_Wild_Grass_vdilbaiia_Var21_lod0` | StaticMesh | 0.59 | 11,415 | 1.05x1.15x0.67 | A50 | no | [foliage]; sibling used by PWR |
| `/Game/Megascans/3D_Plants/Wild_Grass_vdilbaiia/S_Wild_Grass_vdilbaiia_Var22_lod0` | StaticMesh | 0.74 | 8,985 | 1.49x1.06x0.78 |  | no | [foliage]; sibling used by PWR |
| `/Game/Megascans/3D_Plants/Wild_Grass_vdilbaiia/S_Wild_Grass_vdilbaiia_Var23_lod0` | StaticMesh | 1.09 | 13,657 | 1.58x1.14x0.68 |  | no | [foliage]; sibling used by PWR |
| `/Game/Megascans/3D_Plants/Wild_Grass_vdilbaiia/S_Wild_Grass_vdilbaiia_Var24_lod0` | StaticMesh | 0.28 | 2,652 | 1.36x0.64x0.51 |  | no | [foliage]; sibling used by PWR |
| `/Game/Megascans/3D_Plants/Wild_Grass_vdilbaiia/S_Wild_Grass_vdilbaiia_Var25_lod0` | StaticMesh | 0.16 | 2,862 | 1.29x0.85x0.64 | A50 | no | [foliage]; sibling used by PWR |
| `/Game/Megascans/3D_Plants/Wild_Grass_vdilbaiia/S_Wild_Grass_vdilbaiia_Var26_lod0` | StaticMesh | 0.20 | 1,558 | 1.07x0.6x0.29 |  | no | [foliage]; sibling used by PWR |
| `/Game/Megascans/3D_Plants/Wild_Grass_vdilbaiia/S_Wild_Grass_vdilbaiia_Var2_lod0` | StaticMesh | 0.17 | 1,734 | 0.88x0.62x0.49 |  | no | [foliage]; sibling used by PWR |
| `/Game/Megascans/3D_Plants/Wild_Grass_vdilbaiia/S_Wild_Grass_vdilbaiia_Var3_lod0` | StaticMesh | 0.51 | 6,296 | 0.88x0.92x0.69 |  | no | [foliage]; sibling used by PWR |
| `/Game/Megascans/3D_Plants/Wild_Grass_vdilbaiia/S_Wild_Grass_vdilbaiia_Var4_lod0` | StaticMesh | 0.22 | 1,254 | 0.88x0.79x0.49 | B30 | no | [foliage]; sibling used by PWR |
| `/Game/Megascans/3D_Plants/Wild_Grass_vdilbaiia/S_Wild_Grass_vdilbaiia_Var5_lod0` | StaticMesh | 0.21 | 1,851 | 0.96x0.88x0.28 |  | no | [foliage]; sibling used by PWR |
| `/Game/Megascans/3D_Plants/Wild_Grass_vdilbaiia/S_Wild_Grass_vdilbaiia_Var6_lod0` | StaticMesh | 0.24 | 3,077 | 0.94x0.66x0.5 |  | no | [foliage]; sibling used by PWR |
| `/Game/Megascans/3D_Plants/Wild_Grass_vdilbaiia/S_Wild_Grass_vdilbaiia_Var7_lod0` | StaticMesh | 0.29 | 2,200 | 0.88x0.72x0.24 |  | no | [foliage]; sibling used by PWR |
| `/Game/Megascans/3D_Plants/Wild_Grass_vdilbaiia/S_Wild_Grass_vdilbaiia_Var8_lod0` | StaticMesh | 0.10 | 1,515 | 0.79x0.73x0.26 | A50 | no | [foliage]; sibling used by PWR |
| `/Game/Megascans/3D_Plants/Wild_Grass_vdilbaiia/S_Wild_Grass_vdilbaiia_Var9_lod0` | StaticMesh | 0.34 | 2,058 | 0.88x0.79x0.28 |  | no | [foliage]; sibling used by PWR |
| `/Game/Megascans/3D_Plants/Wild_Grass_vlkhcbxia/Foliage/FT_Wild_Grass_vlkhcbxia_0_Var10_lod0` | FoliageType | 0.00 |  |  |  | no | [foliage] |
| `/Game/Megascans/3D_Plants/Wild_Grass_vlkhcbxia/Foliage/FT_Wild_Grass_vlkhcbxia_0_Var11_lod0` | FoliageType | 0.00 |  |  |  | no | [foliage] |
| `/Game/Megascans/3D_Plants/Wild_Grass_vlkhcbxia/Foliage/FT_Wild_Grass_vlkhcbxia_0_Var12_lod0` | FoliageType | 0.00 |  |  |  | no | [foliage] |
| `/Game/Megascans/3D_Plants/Wild_Grass_vlkhcbxia/Foliage/FT_Wild_Grass_vlkhcbxia_0_Var13_lod0` | FoliageType | 0.00 |  |  | B30 | no | [foliage] |
| `/Game/Megascans/3D_Plants/Wild_Grass_vlkhcbxia/Foliage/FT_Wild_Grass_vlkhcbxia_0_Var14_lod0` | FoliageType | 0.00 |  |  |  | no | [foliage] |
| `/Game/Megascans/3D_Plants/Wild_Grass_vlkhcbxia/Foliage/FT_Wild_Grass_vlkhcbxia_0_Var15_lod0` | FoliageType | 0.00 |  |  | A50 | no | [foliage] |
| `/Game/Megascans/3D_Plants/Wild_Grass_vlkhcbxia/Foliage/FT_Wild_Grass_vlkhcbxia_0_Var16_lod0` | FoliageType | 0.00 |  |  |  | no | [foliage] |
| `/Game/Megascans/3D_Plants/Wild_Grass_vlkhcbxia/Foliage/FT_Wild_Grass_vlkhcbxia_0_Var17_lod0` | FoliageType | 0.00 |  |  |  | no | [foliage] |
| `/Game/Megascans/3D_Plants/Wild_Grass_vlkhcbxia/Foliage/FT_Wild_Grass_vlkhcbxia_0_Var18_lod0` | FoliageType | 0.00 |  |  |  | no | [foliage] |
| `/Game/Megascans/3D_Plants/Wild_Grass_vlkhcbxia/Foliage/FT_Wild_Grass_vlkhcbxia_0_Var19_lod0` | FoliageType | 0.00 |  |  |  | no | [foliage] |
| `/Game/Megascans/3D_Plants/Wild_Grass_vlkhcbxia/Foliage/FT_Wild_Grass_vlkhcbxia_0_Var1_lod0` | FoliageType | 0.00 |  |  |  | no | [foliage] |
| `/Game/Megascans/3D_Plants/Wild_Grass_vlkhcbxia/Foliage/FT_Wild_Grass_vlkhcbxia_0_Var20_lod0` | FoliageType | 0.00 |  |  |  | no | [foliage] |
| `/Game/Megascans/3D_Plants/Wild_Grass_vlkhcbxia/Foliage/FT_Wild_Grass_vlkhcbxia_0_Var2_lod0` | FoliageType | 0.00 |  |  |  | no | [foliage] |
| `/Game/Megascans/3D_Plants/Wild_Grass_vlkhcbxia/Foliage/FT_Wild_Grass_vlkhcbxia_0_Var3_lod0` | FoliageType | 0.00 |  |  |  | no | [foliage] |
| `/Game/Megascans/3D_Plants/Wild_Grass_vlkhcbxia/Foliage/FT_Wild_Grass_vlkhcbxia_0_Var4_lod0` | FoliageType | 0.00 |  |  |  | no | [foliage] |
| `/Game/Megascans/3D_Plants/Wild_Grass_vlkhcbxia/Foliage/FT_Wild_Grass_vlkhcbxia_0_Var5_lod0` | FoliageType | 0.00 |  |  |  | no | [foliage] |
| `/Game/Megascans/3D_Plants/Wild_Grass_vlkhcbxia/Foliage/FT_Wild_Grass_vlkhcbxia_0_Var6_lod0` | FoliageType | 0.00 |  |  |  | no | [foliage] |
| `/Game/Megascans/3D_Plants/Wild_Grass_vlkhcbxia/Foliage/FT_Wild_Grass_vlkhcbxia_0_Var7_lod0` | FoliageType | 0.00 |  |  |  | no | [foliage] |
| `/Game/Megascans/3D_Plants/Wild_Grass_vlkhcbxia/Foliage/FT_Wild_Grass_vlkhcbxia_0_Var8_lod0` | FoliageType | 0.00 |  |  |  | no | [foliage] |
| `/Game/Megascans/3D_Plants/Wild_Grass_vlkhcbxia/Foliage/FT_Wild_Grass_vlkhcbxia_0_Var9_lod0` | FoliageType | 0.00 |  |  |  | no | [foliage] |
| `/Game/Megascans/3D_Plants/Wild_Grass_vlkhcbxia/MI_Wild_Grass_vlkhcbxia_8K` | MaterialInstance | 0.00 |  |  | A50,B30 | no | [foliage]; sibling used by PWR |
| `/Game/Megascans/3D_Plants/Wild_Grass_vlkhcbxia/S_Wild_Grass_vlkhcbxia_0_Var11_lod0` | StaticMesh | 0.51 | 7,432 | 0.5x0.48x0.15 |  | no | [foliage]; sibling used by PWR |
| `/Game/Megascans/3D_Plants/Wild_Grass_vlkhcbxia/S_Wild_Grass_vlkhcbxia_0_Var12_lod0` | StaticMesh | 0.32 | 3,238 | 0.5x0.49x0.39 |  | yes | [foliage] |
| `/Game/Megascans/3D_Plants/Wild_Grass_vlkhcbxia/S_Wild_Grass_vlkhcbxia_0_Var13_lod0` | StaticMesh | 0.31 | 4,695 | 0.28x0.33x0.13 | B30 | no | [foliage]; sibling used by PWR |
| `/Game/Megascans/3D_Plants/Wild_Grass_vlkhcbxia/S_Wild_Grass_vlkhcbxia_0_Var14_lod0` | StaticMesh | 0.29 | 2,606 | 0.36x0.41x0.27 |  | no | [foliage]; sibling used by PWR |
| `/Game/Megascans/3D_Plants/Wild_Grass_vlkhcbxia/S_Wild_Grass_vlkhcbxia_0_Var15_lod0` | StaticMesh | 0.09 | 1,538 | 0.41x0.36x0.18 | A50 | no | [foliage]; sibling used by PWR |
| `/Game/Megascans/3D_Plants/Wild_Grass_vlkhcbxia/S_Wild_Grass_vlkhcbxia_0_Var16_lod0` | StaticMesh | 0.23 | 2,120 | 0.36x0.4x0.23 |  | yes | [foliage] |
| `/Game/Megascans/3D_Plants/Wild_Grass_vlkhcbxia/S_Wild_Grass_vlkhcbxia_0_Var17_lod0` | StaticMesh | 0.28 | 4,088 | 0.29x0.29x0.16 |  | no | [foliage]; sibling used by PWR |
| `/Game/Megascans/3D_Plants/Wild_Grass_vlkhcbxia/S_Wild_Grass_vlkhcbxia_0_Var18_lod0` | StaticMesh | 0.20 | 1,940 | 0.24x0.3x0.13 |  | no | [foliage]; sibling used by PWR |
| `/Game/Megascans/3D_Plants/Wild_Grass_vlkhcbxia/S_Wild_Grass_vlkhcbxia_0_Var19_lod0` | StaticMesh | 0.21 | 2,238 | 0.25x0.2x0.11 |  | no | [foliage]; sibling used by PWR |
| `/Game/Megascans/3D_Plants/Wild_Grass_vlkhcbxia/S_Wild_Grass_vlkhcbxia_0_Var1_lod0` | StaticMesh | 0.23 | 3,220 | 0.53x0.49x0.41 |  | yes | [foliage] |
| `/Game/Megascans/3D_Plants/Wild_Grass_vlkhcbxia/S_Wild_Grass_vlkhcbxia_0_Var20_lod0` | StaticMesh | 0.28 | 2,686 | 0.19x0.26x0.12 |  | no | [foliage]; sibling used by PWR |
| `/Game/Megascans/3D_Plants/Wild_Grass_vlkhcbxia/S_Wild_Grass_vlkhcbxia_0_Var2_lod0` | StaticMesh | 0.32 | 2,936 | 0.27x0.25x0.09 |  | no | [foliage]; sibling used by PWR |
| `/Game/Megascans/3D_Plants/Wild_Grass_vlkhcbxia/S_Wild_Grass_vlkhcbxia_0_Var3_lod0` | StaticMesh | 0.25 | 3,228 | 0.25x0.23x0.13 |  | no | [foliage]; sibling used by PWR |
| `/Game/Megascans/3D_Plants/Wild_Grass_vlkhcbxia/S_Wild_Grass_vlkhcbxia_0_Var4_lod0` | StaticMesh | 0.23 | 3,360 | 0.33x0.28x0.19 |  | no | [foliage]; sibling used by PWR |
| `/Game/Megascans/3D_Plants/Wild_Grass_vlkhcbxia/S_Wild_Grass_vlkhcbxia_0_Var5_lod0` | StaticMesh | 0.09 | 618 | 0.16x0.19x0.3 |  | no | [foliage]; sibling used by PWR |
| `/Game/Megascans/3D_Plants/Wild_Grass_vlkhcbxia/S_Wild_Grass_vlkhcbxia_0_Var6_lod0` | StaticMesh | 0.07 | 444 | 0.17x0.15x0.3 |  | no | [foliage]; sibling used by PWR |
| `/Game/Megascans/3D_Plants/Wild_Grass_vlkhcbxia/S_Wild_Grass_vlkhcbxia_0_Var7_lod0` | StaticMesh | 0.05 | 306 | 0.1x0.1x0.17 |  | no | [foliage]; sibling used by PWR |
| `/Game/Megascans/3D_Plants/Wild_Grass_vlkhcbxia/S_Wild_Grass_vlkhcbxia_0_Var8_lod0` | StaticMesh | 0.07 | 471 | 0.09x0.12x0.18 |  | no | [foliage]; sibling used by PWR |
| `/Game/Megascans/3D_Plants/Wild_Grass_vlkhcbxia/S_Wild_Grass_vlkhcbxia_0_Var9_lod0` | StaticMesh | 0.09 | 690 | 0.11x0.14x0.15 |  | no | [foliage]; sibling used by PWR |
| `/Game/Megascans/3D_Plants/Willowherb_tbfpbbhr/Foliage/FT_Willowherb_tbfpbbhr_Var1_lod0` | FoliageType | 0.00 |  |  | A50,B30 | no | [foliage] |
| `/Game/Megascans/3D_Plants/Willowherb_tbfpbbhr/Foliage/FT_Willowherb_tbfpbbhr_Var2_lod0` | FoliageType | 0.00 |  |  | A50,B30 | no | [foliage] |
| `/Game/Megascans/3D_Plants/Willowherb_tbfpbbhr/MI_Willowherb_tbfpbbhr_4K` | MaterialInstance | 0.00 |  |  | A50,B30 | no | [foliage]; sibling used by PWR |
| `/Game/Megascans/3D_Plants/Willowherb_tbfpbbhr/SM_Willowherb_tbfpbbhr_Var1_lod0_Traced` | StaticMesh | 0.54 | 11,328 | 0.62x0.52x1.51 | A50,B30 | yes | [foliage] |
| `/Game/Megascans/3D_Plants/Willowherb_tbfpbbhr/SM_Willowherb_tbfpbbhr_Var2_lod0_Traced` | StaticMesh | 0.32 | 7,127 | 0.67x0.46x1.08 | A50,B30 | yes | [foliage] |

*Group note:* Megascans flowers and grasses; several already used

### Meadow ground surfaces (Megascans) (27)

*Where on PWR:* Meadow grass ground layer, alpine tundra, grass with snow


Textures: `/Game/Megascans/Surfaces/Ground_Grass_tb3nce2k/T_Ground_Grass_NSVT_4K_N` (5.6 MB, PWR yes), `/Game/Megascans/Surfaces/Ground_Grass_tb3nce2k/T_Ground_Grass_NSVT_4K_OHRG` (5.6 MB), `/Game/Megascans/Surfaces/Ground_Grass_tb3nce2k/T_Ground_Grass_tb3nce2k_4K_N` (6.4 MB), `/Game/Megascans/Surfaces/Ground_Grass_tb3nce2k/T_Ground_Grass_tb3nce_4K_OHRG` (6.4 MB), `/Game/Megascans/Surfaces/Ground_Grass_tb3nce2k/T_Ground_Grass_tb3nce_Desat_4K_D` (3.2 MB), `/Game/Megascans/Surfaces/Ground_Grass_tb3nce2k/T_Ground_Grass_tb3nce_Desat_4K_NSVT_D` (0.7 MB, PWR yes), `/Game/Megascans/Surfaces/Grunge_tedwfbhc/T_Grunge_tedwfbhc_4K_MR` (3.2 MB), `/Game/Megascans/Surfaces/Grunge_tedwfbhc/T_Grunge_tedwfbhc_4K_ORHG` (6.4 MB), `/Game/Megascans/Surfaces/Grunge_tedwfhdc/T_Grunge_tedwfhdc_4K_ORH` (6.4 MB), `/Game/Megascans/Surfaces/Tundra_mossy_ground_vjulbjjr/T_Tundra_NOmossy_ground_vjulbjjr_NSVT_D` (2.8 MB), `/Game/Megascans/Surfaces/Tundra_mossy_ground_vjulbjjr/T_Tundra_mossy_ground_vjulbjjr_N` (6.4 MB), `/Game/Megascans/Surfaces/Tundra_mossy_ground_vjulbjjr/T_Tundra_mossy_ground_vjulbjjr_NSVT_D` (2.8 MB, PWR yes), `/Game/Megascans/Surfaces/Tundra_mossy_ground_vjulbjjr/T_Tundra_mossy_ground_vjulbjjr_NSVT_N` (5.6 MB, PWR yes), `/Game/Megascans/Surfaces/Tundra_mossy_ground_vjulbjjr/T_Tundra_mossy_ground_vjulbjjr_NSVT_ORHG` (5.6 MB), `/Game/Megascans/Surfaces/Tundra_mossy_ground_vjulbjjr/T_Tundra_mossy_ground_vjulbjjr_ORHG` (6.4 MB), `/Game/Megascans/Surfaces/Wild_Grass_and_Weeds_rm5krfp0/T_Wild_Grass_D` (3.2 MB), `/Game/Megascans/Surfaces/Wild_Grass_and_Weeds_rm5krfp0/T_Wild_Grass_H` (6.4 MB), `/Game/Megascans/Surfaces/Wild_Grass_and_Weeds_rm5krfp0/T_Wild_Grass_N` (6.4 MB), `/Game/Megascans/Surfaces/Wild_Grass_and_Weeds_rm5krfp0/T_Wild_Grass_NSVT_D_A30` (2.8 MB), `/Game/Megascans/Surfaces/Wild_Grass_and_Weeds_rm5krfp0/T_Wild_Grass_NSVT_ORHG` (5.6 MB), `/Game/Megascans/Surfaces/Wild_Grass_and_Weeds_rm5krfp0/T_Wild_Grass_ORHG` (6.4 MB), `/Game/Megascans/Surfaces/Wild_Grass_and_Weeds_rm5krfp0/T_Wild_Grass_and_Weeds_rm5krfp0_D` (3.2 MB), `/Game/Megascans/Surfaces/Wild_Grass_and_Weeds_rm5krfp0/T_Wild_Grass_and_Weeds_rm5krfp0_N` (6.4 MB), `/Game/Megascans/Surfaces/Wild_Grass_and_Weeds_rm5krfp0/T_Wild_Grass_and_Weeds_rm5krfp0_NSVT_D` (2.8 MB), `/Game/Megascans/Surfaces/Wild_Grass_and_Weeds_rm5krfp0/T_Wild_Grass_and_Weeds_rm5krfp0_NSVT_N` (5.6 MB), `/Game/Megascans/Surfaces/Wild_Grass_and_Weeds_rm5krfp0/T_Wild_Grass_and_Weeds_rm5krfp0_NSVT_ORHG` (5.6 MB), `/Game/Megascans/Surfaces/Wild_Grass_and_Weeds_rm5krfp0/T_Wild_Grass_and_Weeds_rm5krfp0_ORHG` (6.4 MB)

*Group note:* PWR samples Ground_Grass D/N and Tundra_mossy_ground D/N; check the unused ORHG/height siblings

### Noise textures (generic/Noise) (1)

*Where on PWR:* Macro variation for meadow colour


Textures: `/Game/generic/Noise/T_CloudNoise_VarietyScale_D` (2.8 MB)

*Group note:* Shared noise

### Tiling textures and material layers (shaders/) (58)

*Where on PWR:* Macro/micro variation and detail normals for the PWR ground and cliffs

| path | kind | MB | verts | bounds m | levels | PWR | note |
|---|---|---|---|---|---|---|---|
| `/Game/shaders/MaterialBlends/MLB_CVW_Channel_Select` | MaterialLayerBlend | 0.00 |  |  | A15,C10 | no |  |
| `/Game/shaders/MaterialBlends/MLB_CVW_Replace` | MaterialLayerBlend | 0.00 |  |  | A15,C10,E10,E20 | no |  |
| `/Game/shaders/MaterialFunctions/MF_CVW_MasterMaterialWrapper` | MaterialFunction | 0.00 |  |  | A15,A30,A50,B30,B40,C10,C20,C45,D20,D40,E10,E20,E30 | no |  |
| `/Game/shaders/MaterialFunctions/MF_FoliageWind` | MaterialFunction | 0.00 |  |  | A30 | no |  |
| `/Game/shaders/MaterialLayers/Basic/ML_CVW_Basic` | MaterialLayer | 0.00 |  |  | A15,A30,A50,B30,B40,C10,C20,C45,D20,D40,E10,E20,E30 | no |  |
| `/Game/shaders/MaterialLayers/Basic/ML_CVW_Default_Background` | MaterialLayer | 0.00 |  |  | A15,A30,A50,B30,B40,C10,C20,C45,D20,D40,E10,E20,E30 | no |  |
| `/Game/shaders/MaterialLayers/Basic/ML_CVW_Fresnel` | MaterialLayer | 0.00 |  |  | A15,A30,A50,B30,B40,C10,C20,C45,D20,D40,E10,E20,E30 | no |  |
| `/Game/shaders/MaterialLayers/covenant/Metal/metal_carapace/ML_CVW_Carapace_Blue` | MaterialLayerInstance | 0.00 |  |  | A15,A30,A50,B30,B40,C10,C20,C45,D20,D40,E10,E20,E30 | no |  |
| `/Game/shaders/MaterialLayers/covenant/Metal/metal_carapace/ML_CVW_Carapace_Blurple` | MaterialLayerInstance | 0.00 |  |  | C20 | no |  |
| `/Game/shaders/MaterialLayers/covenant/Metal/metal_carapace/ML_CVW_Carapace_DarkViolet` | MaterialLayerInstance | 0.00 |  |  | C20 | no |  |
| `/Game/shaders/MaterialLayers/covenant/Metal/metal_carapace/ML_CVW_Carapace_Gold` | MaterialLayerInstance | 0.00 |  |  | A15,A30,A50,B30,B40,C10,C20,C45,D20,D40,E10,E20,E30 | no |  |
| `/Game/shaders/MaterialLayers/covenant/Metal/metal_carapace/ML_CVW_Carapace_Orange` | MaterialLayerInstance | 0.00 |  |  |  | no |  |
| `/Game/shaders/MaterialLayers/covenant/Metal/metal_carapace/ML_CVW_Carapace_Red` | MaterialLayerInstance | 0.00 |  |  | C20 | no |  |
| `/Game/shaders/MaterialLayers/covenant/Metal/metal_carapace/ML_CVW_Carapace_Sacristan` | MaterialLayerInstance | 0.00 |  |  | C20 | no |  |
| `/Game/shaders/MaterialLayers/covenant/Metal/metal_carapace/ML_CVW_Carapace_White` | MaterialLayerInstance | 0.00 |  |  |  | no |  |
| `/Game/shaders/MaterialLayers/covenant/Metal/metal_carapace/ML_Cov_Carapace_DarkTone` | MaterialLayerInstance | 0.00 |  |  | C20 | no |  |
| `/Game/shaders/MaterialLayers/covenant/Worms/MLBM_CVW_Worms` | MaterialLayerBlend | 0.00 |  |  |  | no |  |
| `/Game/shaders/MaterialLayers/flood/MLM_CVW_FloodPustule` | MaterialLayer | 0.00 |  |  |  | no |  |

Textures: `/Game/shaders/GlobalTextures/T_Default_Greyscale_NonVT` (0.0 MB), `/Game/shaders/GlobalTextures/T_Default_N` (0.1 MB), `/Game/shaders/GlobalTextures/T_Default_ORME` (0.1 MB), `/Game/shaders/GlobalTextures/T_Default_ORMH_50` (0.1 MB), `/Game/shaders/GlobalTextures/T_Flat_Default_N` (0.1 MB), `/Game/shaders/GlobalTextures/T_Flat_White_Default_D` (0.1 MB), `/Game/shaders/Tiling/Plastic/Noise/T_Plastic_Noise_01_N` (1.7 MB), `/Game/shaders/Tiling/Plastic/Noise/T_Plastic_Noise_01_ORME` (1.7 MB), `/Game/shaders/Tiling/Skin/Jackal/T_Chicken_Pores_Skin_N` (0.5 MB), `/Game/shaders/Tiling/Skin/Jackal/T_Chicken_Pores_Skin_ORME` (0.5 MB), `/Game/shaders/Tiling/Skin/grunt/T_Shell_Grunt_N` (1.7 MB), `/Game/shaders/Tiling/Skin/grunt/T_Shell_Grunt_ORME` (1.7 MB), `/Game/shaders/Tiling/Skin/grunt/T_Skin_Grunt_N` (1.7 MB), `/Game/shaders/Tiling/Skin/grunt/T_Skin_Grunt_ORME` (1.7 MB), `/Game/shaders/Tiling/Stone/T_Spartans_Stone_N` (0.5 MB), `/Game/shaders/Tiling/Textile/Cotton/T_Fabric_Cotton_ORME` (1.7 MB), `/Game/shaders/Tiling/Textile/Cotton/T_Textile_Cotton_01_N` (0.5 MB), `/Game/shaders/Tiling/Textile/Cotton/T_Textile_Cotton_01_ORME` (0.5 MB), `/Game/shaders/Tiling/Textile/Linen/T_Dotted_Linen_N` (1.7 MB), `/Game/shaders/Tiling/Textile/Linen/T_Dotted_Linen_ORME` (1.7 MB), `/Game/shaders/Tiling/Textile/Linen/T_Moleskin_Fabric_N` (1.7 MB), `/Game/shaders/Tiling/Textile/Linen/T_Moleskin_Fabric_ORME` (1.7 MB), `/Game/shaders/Tiling/Textile/Nylon/T_Fabric_Denim_002_N` (6.4 MB), `/Game/shaders/Tiling/Textile/Nylon/T_Fabric_Denim_ORME` (1.7 MB), `/Game/shaders/Tiling/Textile/Nylon/T_Textile_Nylon_01_N` (0.5 MB), `/Game/shaders/Tiling/Textile/Nylon/T_Textile_Nylon_01_ORME` (0.5 MB), `/Game/shaders/Tiling/Textile/Nylon/T_Textile_Nylon_02_N` (0.5 MB), `/Game/shaders/Tiling/Textile/Nylon/T_Textile_Nylon_02_ORME` (0.5 MB), `/Game/shaders/Tiling/Textile/Nylon/T_Textile_Nylon_03_N` (0.2 MB), `/Game/shaders/Tiling/Textile/Nylon/T_Textile_Nylon_03_ORME` (0.2 MB), `/Game/shaders/Tiling/Textile/Nylon/T_Textile_Nylon_04_N` (0.5 MB), `/Game/shaders/Tiling/Textile/Nylon/T_Textile_Nylon_04_ORME` (0.5 MB), `/Game/shaders/Tiling/Textile/Nylon/T_Textile_Nylon_05_N` (0.5 MB), `/Game/shaders/Tiling/Textile/Nylon/T_Textile_Nylon_05_ORME` (0.5 MB), `/Game/shaders/Tiling/Textile/Velcro/T_Textile_Velcro_01_N` (1.7 MB), `/Game/shaders/Tiling/Textile/Velcro/T_Textile_Velcro_01_ORME` (1.7 MB), `/Game/shaders/Tiling/Worms/T_Worms_D` (0.9 MB), `/Game/shaders/Tiling/Worms/T_Worms_N` (1.7 MB), `/Game/shaders/Tiling/Worms/T_Worms_NormalPacked` (6.4 MB), `/Game/shaders/Tiling/Worms/T_Worms_ORME` (1.7 MB)

*Group note:* Shared tiling detail textures and layer blends

### Halo material library: landscape and blend functions (41)

*Where on PWR:* Recipe for PWR's own landscape/rock materials (anti-tiling, wetness, macro/detail, height blend, flakes)

| path | kind | MB | verts | bounds m | levels | PWR | note |
|---|---|---|---|---|---|---|---|
| `/HaloMaterialLibrary/Landscape/LandscapeRuntimeVirtualTextureSubsurface` | RuntimeVirtualTexture | 0.00 |  |  |  | no |  |
| `/HaloMaterialLibrary/Landscape/LandscapeRuntimeVirtualTexture_GlobalWetness` | RuntimeVirtualTexture | 0.00 |  |  | A15,A30,A50,B30,B40,C10,C20,C45,D20,D40,E10,E20,E30 | no |  |
| `/HaloMaterialLibrary/Landscape/RVT_Landscape_Height` | RuntimeVirtualTexture | 0.00 |  |  | A15,A30,A50,B30,B40,C10,C20,C45,D20,D40,E10,E20,E30 | no |  |
| `/HaloMaterialLibrary/Landscape/RVT_Landscape_Subsurface` | RuntimeVirtualTexture | 0.00 |  |  | A15,A30,A50,B30,B40,C10,C20,C45,D20,D40,E10,E20,E30 | no |  |
| `/HaloMaterialLibrary/Landscape/RVT_Landscape_Surface` | RuntimeVirtualTexture | 0.00 |  |  | A15,A30,A50,B30,B40,C10,C20,C45,D20,D40,E10,E20,E30 | no |  |
| `/HaloMaterialLibrary/Landscape/Templates/MI_Full_Landscape_Inheritance` | MaterialInstance | 0.00 |  |  | A30,D40,E20 | no |  |
| `/HaloMaterialLibrary/Landscape/Templates/MM_Full_Landscape_Inheritance` | Material | 0.02 |  |  | A30,D40,E20 | no |  |
| `/HaloMaterialLibrary/MaterialFunctions/MF_Advanced_Landscape_To_Asset_Blend` | MaterialFunction | 0.00 |  |  | A15,A30,A50,B30,B40,C10,C20,C45,D20,D40,E10,E20,E30 | no |  |
| `/HaloMaterialLibrary/MaterialFunctions/MF_Env_BoundingBox_Z_Gradient` | MaterialFunction | 0.00 |  |  | A15,A30,A50,B30,B40,C10,C20,C45,D20,D40,E10,E20,E30 | no |  |
| `/HaloMaterialLibrary/MaterialFunctions/MF_Env_Detail` | MaterialFunction | 0.00 |  |  | A15,A30,A50,B30,B40,C10,C20,C45,D20,D40,E10,E20,E30 | no |  |
| `/HaloMaterialLibrary/MaterialFunctions/MF_Env_Detail_Far` | MaterialFunction | 0.00 |  |  |  | no |  |
| `/HaloMaterialLibrary/MaterialFunctions/MF_Env_Foliage_RVT_Sample` | MaterialFunction | 0.00 |  |  |  | no |  |
| `/HaloMaterialLibrary/MaterialFunctions/MF_Env_HeightBlendMaterialAttributes` | MaterialFunction | 0.00 |  |  | A30,B30,B40,C10,C45,D20,D40,E10,E20 | no |  |
| `/HaloMaterialLibrary/MaterialFunctions/MF_Env_HeightBlend_ColorFalloff` | MaterialFunction | 0.00 |  |  | A15,A30,A50,B30,B40,C10,C20,C45,D20,D40,E10,E20,E30 | no |  |
| `/HaloMaterialLibrary/MaterialFunctions/MF_Env_HeightLerp_Only` | MaterialFunction | 0.00 |  |  | A15,A30,A50,B30,B40,C10,C20,C45,D20,D40,E10,E20,E30 | no |  |
| `/HaloMaterialLibrary/MaterialFunctions/MF_Env_Landscape_Z_Gradient` | MaterialFunction | 0.00 |  |  | A15,A30,A50,B30,B40,C10,C20,C45,D20,D40,E10,E20,E30 | no |  |
| `/HaloMaterialLibrary/MaterialFunctions/MF_Env_Macro` | MaterialFunction | 0.00 |  |  | A15,A30,A50,B30,B40,C10,C20,C45,D20,D40,E10,E20,E30 | no |  |
| `/HaloMaterialLibrary/MaterialFunctions/MF_Env_PivotRadius_Z_Gradient` | MaterialFunction | 0.00 |  |  | A30,B30,B40,C10,C45,D20 | no |  |
| `/HaloMaterialLibrary/MaterialFunctions/MF_Env_Uber_Blend` | MaterialFunction | 0.00 |  |  | A15,A30,A50,B30,B40,C10,C20,C45,D20,D40,E10,E20,E30 | no |  |
| `/HaloMaterialLibrary/MaterialFunctions/MF_Env_Uber_Blend_Layer1` | MaterialFunction | 0.00 |  |  | A15,A30,A50,B30,B40,C10,C20,C45,D20,D40,E10,E20,E30 | no |  |
| `/HaloMaterialLibrary/MaterialFunctions/MF_Env_Uber_Blend_Layer2` | MaterialFunction | 0.00 |  |  | A15,A30,A50,B30,B40,C10,C20,C45,D20,D40,E10,E20,E30 | no |  |
| `/HaloMaterialLibrary/MaterialFunctions/MF_Env_Uber_Blend_Layer3` | MaterialFunction | 0.00 |  |  | A15,A30,A50,B30,B40,C10,C20,C45,D20,D40,E10,E20,E30 | no |  |
| `/HaloMaterialLibrary/MaterialFunctions/MF_Env_Wetness` | MaterialFunction | 0.00 |  |  |  | no | wet variant |
| `/HaloMaterialLibrary/MaterialFunctions/MF_Env_Z_Gradient` | MaterialFunction | 0.00 |  |  | A15,A30,A50,B30,B40,C10,C20,C45,D20,D40,E10,E20,E30 | no |  |
| `/HaloMaterialLibrary/MaterialFunctions/MF_Flakes` | MaterialFunction | 0.00 |  |  | A30,B30,B40,C20,C45,D40,E10 | no |  |
| `/HaloMaterialLibrary/MaterialFunctions/MF_GlobalWetnessFromRVT` | MaterialFunction | 0.00 |  |  | A15,A30,A50,B30,B40,C10,C20,C45,D20,D40,E10,E20,E30 | no |  |
| `/HaloMaterialLibrary/MaterialFunctions/MF_Halo_RVT_Unpack` | MaterialFunction | 0.00 |  |  | A15,A30,A50,B30,B40,C10,C20,C45,D20,D40,E10,E20,E30 | no |  |
| `/HaloMaterialLibrary/MaterialFunctions/MF_HexGrid` | MaterialFunction | 0.00 |  |  | A15,A30,A50,B30,B40,C10,C20,C45,D20,D40,E10,E20,E30 | no |  |
| `/HaloMaterialLibrary/MaterialFunctions/MF_Hex_TextureBombing` | MaterialFunction | 0.00 |  |  | A15,A30,A50,B30,B40,C10,C20,C45,D20,D40,E10,E20,E30 | no |  |
| `/HaloMaterialLibrary/MaterialFunctions/MF_InstanceLandscapeInheritance` | MaterialFunction | 0.00 |  |  | A30,A50,B30,B40,C10,C45,D20,E10,E20,E30 | no |  |
| `/HaloMaterialLibrary/MaterialFunctions/MF_NormalStrength` | MaterialFunction | 0.00 |  |  | A15,A30,A50,B30,B40,C10,C20,C45,D20,D40,E10,E20,E30 | no |  |
| `/HaloMaterialLibrary/MaterialFunctions/MF_NormalStrength_Cheap` | MaterialFunction | 0.00 |  |  | A15,A30,A50,B30,B40,C10,C20,C45,D20,D40,E10,E20,E30 | no |  |
| `/HaloMaterialLibrary/MaterialFunctions/MF_RVT_projection_inheritance` | MaterialFunction | 0.00 |  |  | A30,B40,C45,D40 | no |  |
| `/HaloMaterialLibrary/MaterialFunctions/MF_SampleHex_Normal` | MaterialFunction | 0.00 |  |  | A15,A30,A50,B30,B40,C10,C20,C45,D20,D40,E10,E20,E30 | no |  |
| `/HaloMaterialLibrary/MaterialFunctions/MF_SampleHex_RGBA` | MaterialFunction | 0.00 |  |  | A15,A30,A50,B30,B40,C10,C20,C45,D20,D40,E10,E20,E30 | no |  |
| `/HaloMaterialLibrary/MaterialFunctions/MF_SampleLandscapeLayer` | MaterialFunction | 0.00 |  |  | A30,A50,B30,B40,C10,C45,D20,D40,E10,E20 | no |  |
| `/HaloMaterialLibrary/MaterialFunctions/MF_Stochastic_Flakes_Voronoi` | MaterialFunction | 0.00 |  |  | A30,B30,B40,C20,C45,D40,E10 | no |  |
| `/HaloMaterialLibrary/MaterialFunctions/MF_Wetness` | MaterialFunction | 0.00 |  |  | A15,A30,A50,B30,B40,C10,C20,C45,D20,D40,E10,E20,E30 | no | wet variant |
| `/HaloMaterialLibrary/MaterialFunctions/MF_Wetness_Albedo_Darkening` | MaterialFunction | 0.00 |  |  | A15,A30,A50,B30,B40,C10,C20,C45,D20,D40,E10,E20,E30 | no | wet variant |
| `/HaloMaterialLibrary/MaterialFunctions/MF_Wetness_Custom_Prim_Data` | MaterialFunction | 0.00 |  |  |  | no | wet variant |
| `/HaloMaterialLibrary/MaterialFunctions/MF_stochastic_flakes` | MaterialFunction | 0.00 |  |  | B40,C45 | no |  |

*Group note:* Plugin material functions the shipped landscapes call: MF_Hex_TextureBombing, MF_SampleHex_*, MF_Wetness(_Albedo_Darkening), MF_Env_Macro/Detail(_Far), MF_Env_HeightBlendMaterialAttributes, MF_stochastic_flakes, MF_Advanced_Landscape_To_Asset_Blend, RVT_Landscape_*

### Halo PCG framework (biomes, roads, scatter) (50)

*Where on PWR:* Reference: how shipped levels scatter by biome/landscape layer and carve roads (BP_PCGRoad)

| path | kind | MB | verts | bounds m | levels | PWR | note |
|---|---|---|---|---|---|---|---|
| `/HaloPCG/Blueprints/DataStructures/BP_BiomeOverrides` | Blueprint | 0.00 |  |  | A30,B30 | no |  |
| `/HaloPCG/Blueprints/DataStructures/BP_BiomeSettings` | Blueprint | 0.00 |  |  | A30,B30,C10 | no |  |
| `/HaloPCG/Blueprints/DataStructures/BP_CategoryDebugColors` | Blueprint | 0.00 |  |  |  | no |  |
| `/HaloPCG/Blueprints/DataStructures/BP_CategoryDefaultSeeds` | Blueprint | 0.00 |  |  |  | no |  |
| `/HaloPCG/Blueprints/DataStructures/BP_IndividualSpawnableSettings` | Blueprint | 0.00 |  |  |  | no |  |
| `/HaloPCG/Blueprints/DataStructures/BP_LandscapeLayerPCGSettings` | Blueprint | 0.00 |  |  | A30,B30,C10 | no |  |
| `/HaloPCG/Blueprints/DataStructures/BP_MeshComponentProperties` | Blueprint | 0.00 |  |  |  | no |  |
| `/HaloPCG/Blueprints/DataStructures/BP_SpatialWeightedSpawnables` | Blueprint | 0.00 |  |  |  | no |  |
| `/HaloPCG/Blueprints/DataStructures/BP_SpawnableCategoryAlgorithmGraph` | Blueprint | 0.00 |  |  | A30,B30,C10 | no |  |
| `/HaloPCG/Blueprints/Generation/BPFL_PCGGeneration` | Blueprint | 0.00 |  |  | A30,B30,C10 | no |  |
| `/HaloPCG/Blueprints/Generation/BPI_PCGGeneration` | Blueprint | 0.00 |  |  | A30,A50,B30,B40,C10,C45 | no |  |
| `/HaloPCG/Blueprints/ParentBlueprints/BP_MacroRock` | Blueprint | 0.00 |  |  | A30,B30 | no |  |
| `/HaloPCG/Blueprints/ParentBlueprints/BP_PCGAssembly` | Blueprint | 0.00 |  |  | B30 | no |  |
| `/HaloPCG/Blueprints/ParentBlueprints/BP_PCGEnvironment` | Blueprint | 0.00 |  |  | A30,B30,C10 | no |  |
| `/HaloPCG/Blueprints/ParentBlueprints/BP_PCGLandscape` | Blueprint | 0.01 |  |  | A30,B30,C10 | no |  |
| `/HaloPCG/Blueprints/ParentBlueprints/BP_PCGMesh` | Blueprint | 0.01 |  |  | A30,B30 | no |  |
| `/HaloPCG/DataAssets/DA_BiomeSettings_Default` | DataAsset | 0.00 |  |  | A30,B30,C10 | no |  |
| `/HaloPCG/DataAssets/DA_MeshProperties_Small_Default` | DataAsset | 0.00 |  |  |  | no |  |
| `/HaloPCG/DataAssets/DA_NoOverrides` | DataAsset | 0.00 |  |  | A30,B30 | no |  |
| `/HaloPCG/EnvironmentFeatures/BP_PCGRoad` | Blueprint | 0.01 |  |  |  | no |  |
| `/HaloPCG/EnvironmentModifiers/BP_PCGBlockerSpline` | Blueprint | 0.00 |  |  |  | no |  |
| `/HaloPCG/EnvironmentModifiers/BP_PCGBlockerVolume` | Blueprint | 0.00 |  |  | B30 | no |  |
| `/HaloPCG/EnvironmentModifiers/BP_PCGSpawnerSpline` | Blueprint | 0.00 |  |  |  | no |  |
| `/HaloPCG/EnvironmentModifiers/BP_PCGSpawnerVolume` | Blueprint | 0.00 |  |  |  | no |  |
| `/HaloPCG/EnvironmentModifiers/Internal/BPFL_PCGSpawnableCategoryHelpers` | Blueprint | 0.01 |  |  | B30 | no |  |
| `/HaloPCG/EnvironmentModifiers/Internal/BP_PCGEnvironmentModifier` | Blueprint | 0.01 |  |  | B30 | no |  |
| `/HaloPCG/EnvironmentModifiers/Internal/BP_PCGModifierCollection` | Blueprint | 0.01 |  |  | B30 | no |  |
| `/HaloPCG/EnvironmentModifiers/Internal/ModifierGraphs/PCG_ModifierSpline` | PCGGraph | 0.14 |  |  |  | no |  |
| `/HaloPCG/EnvironmentModifiers/Internal/ModifierGraphs/PCG_ModifierVolume` | PCGGraph | 0.08 |  |  | B30 | no |  |
| `/HaloPCG/Graphs/Subgraphs/Functions/PCG_CreateVolumeEdgeGrid` | PCGGraph | 0.08 |  |  | B30 | no |  |
| `/HaloPCG/Graphs/Subgraphs/Functions/PCG_DebugCategories` | PCGGraph | 0.01 |  |  | A30,B30,C10 | no |  |
| `/HaloPCG/Graphs/Subgraphs/Functions/PCG_DensityToScale` | PCGGraph | 0.01 |  |  |  | no |  |
| `/HaloPCG/Graphs/Subgraphs/Functions/PCG_DifferenceByPriority` | PCGGraph | 0.02 |  |  |  | no |  |
| `/HaloPCG/Graphs/Subgraphs/Functions/PCG_GetEnvironmentModifiers` | PCGGraph | 0.03 |  |  |  | no |  |
| `/HaloPCG/Graphs/Subgraphs/Functions/PCG_GetLocalGenerationVolume` | PCGGraph | 0.02 |  |  |  | no |  |
| `/HaloPCG/Graphs/Subgraphs/Functions/PCG_PrepareSpawnableCategories` | PCGGraph | 0.05 |  |  |  | no |  |
| `/HaloPCG/Graphs/Subgraphs/Generators/PCG_GenericSpatialGenerator` | PCGGraph | 0.12 |  |  | A30,B30,C10 | no |  |
| `/HaloPCG/Graphs/TransformGraphs/PCG_GroundSinkTransform` | PCGGraph | 0.03 |  |  |  | no |  |
| `/HaloPCG/Graphs/TransformGraphs/PCG_MeshHeightCutoff` | PCGGraph | 0.04 |  |  |  | no |  |
| `/HaloPCG/Nodes/BPFL_PCGNodeHelpers` | Blueprint | 0.01 |  |  | A30,B30,C10 | no |  |
| `/HaloPCG/Nodes/BP_ApplySpawnableTags` | Blueprint | 0.01 |  |  | B30 | no |  |
| `/HaloPCG/Nodes/BP_GetGenerationVolume` | Blueprint | 0.00 |  |  |  | no |  |
| `/HaloPCG/Nodes/BP_GetSpawnableCategory` | Blueprint | 0.00 |  |  | A30,B30,C10 | no |  |
| `/HaloPCG/Nodes/BP_HangLerp` | Blueprint | 0.01 |  |  |  | no |  |
| `/HaloPCG/Nodes/BP_LandscapeLayerToDensity` | Blueprint | 0.02 |  |  | A30,B30,C10 | no |  |
| `/HaloPCG/Nodes/BP_RandomFloatFromSeed` | Blueprint | 0.00 |  |  | A30,B30,C10 | no |  |
| `/HaloPCG/Nodes/BP_TransferTags` | Blueprint | 0.01 |  |  | B30 | no |  |
| `/HaloPCG/Settings/DA_CategoryDebugColors` | DataAsset | 0.00 |  |  |  | no |  |
| `/HaloPCG/Settings/DA_CategoryDefaultSeeds` | DataAsset | 0.00 |  |  |  | no |  |
| `/HaloPCG/Settings/DA_LandscapeLayerPCGSettings_Default` | DataAsset | 0.00 |  |  | A30,B30,C10 | no |  |

*Group note:* Runtime/editor PCG graphs and data structures; PWR bakes its scatter offline, so read these as recipes

## 7. Atmosphere, life, light and sound (669)

### Exterior ambience (Audio_FI, Wwise) (140)

*Where on PWR:* River, waterfalls, wind gusts, birds and insects across the valley

| path | kind | MB | verts | bounds m | levels | PWR | note |
|---|---|---|---|---|---|---|---|
| `/Game/Audio/Audio_FI/Ambience/A30/BaseAirs/Exteriors/WwiseEvents/Play_AMB_BaseAir_A30_Ext_General` | WwiseEvent | 0.00 |  |  | A30 | no |  |
| `/Game/Audio/Audio_FI/Ambience/A30/BaseAirs/Exteriors/WwiseEvents/Play_AMB_BaseAir_A30_Ext_General_Filtered` | WwiseEvent | 0.00 |  |  | A30 | no |  |
| `/Game/Audio/Audio_FI/Ambience/A30/BaseAirs/Exteriors/WwiseEvents/Play_AMB_BaseAir_A30_Ext_Passage_Narrow` | WwiseEvent | 0.00 |  |  | A30 | no |  |
| `/Game/Audio/Audio_FI/Ambience/A30/BaseAirs/Interiors/WwiseEvents/Play_AMB_BaseAir_A30_Int_Cavernous_Room_A` | WwiseEvent | 0.00 |  |  | A30 | no |  |
| `/Game/Audio/Audio_FI/Ambience/A30/BaseAirs/Interiors/WwiseEvents/Play_AMB_BaseAir_A30_Int_General` | WwiseEvent | 0.00 |  |  | A30 | no |  |
| `/Game/Audio/Audio_FI/Ambience/A30/BaseAirs/Interiors/WwiseEvents/Play_AMB_BaseAir_A30_Int_Hallway_C` | WwiseEvent | 0.00 |  |  | A30 | no |  |
| `/Game/Audio/Audio_FI/Ambience/A30/BaseAirs/Interiors/WwiseEvents/Play_AMB_BaseAir_A30_Int_Medium_B` | WwiseEvent | 0.00 |  |  | A30 | no |  |
| `/Game/Audio/Audio_FI/Ambience/A30/BaseAirs/Interiors/WwiseEvents/Play_AMB_BaseAir_A30_Int_Small_A` | WwiseEvent | 0.00 |  |  | A30 | no |  |
| `/Game/Audio/Audio_FI/Ambience/A30/BaseAirs/Interiors/WwiseEvents/Play_AMB_BaseAir_A30_Int_UNSC_EscapePod` | WwiseEvent | 0.00 |  |  | A30 | no |  |
| `/Game/Audio/Audio_FI/Ambience/A30/Positionals/Exterior/Fauna/AlienAnimals/WwiseEvents/Play_AMB_ENV_A30_AlienAnimal_D` | WwiseEvent | 0.00 |  |  | A30 | no | off-setting (tropical/alien/marine) [setting] |
| `/Game/Audio/Audio_FI/Ambience/A30/Positionals/Exterior/Fauna/AlienAnimals/WwiseEvents/Play_AMB_ENV_A30_AlienAnimal_E` | WwiseEvent | 0.00 |  |  | A30 | no | off-setting (tropical/alien/marine) [setting] |
| `/Game/Audio/Audio_FI/Ambience/A30/Positionals/Exterior/Fauna/AlienAnimals/WwiseEvents/Play_AMB_ENV_A30_AlienAnimal_F` | WwiseEvent | 0.00 |  |  | A30 | no | off-setting (tropical/alien/marine) [setting] |
| `/Game/Audio/Audio_FI/Ambience/A30/Positionals/Exterior/Fauna/AlienAnimals/WwiseEvents/Play_AMB_ENV_A30_AlienAnimal_G` | WwiseEvent | 0.00 |  |  | A30 | no | off-setting (tropical/alien/marine) [setting] |
| `/Game/Audio/Audio_FI/Ambience/A30/Positionals/Exterior/Fauna/AlienAnimals/WwiseEvents/Play_AMB_ENV_A30_AlienAnimal_H` | WwiseEvent | 0.00 |  |  | A30 | no | packed AO/roughness/height map; off-setting (tropical/alien/marine) [setting] |
| `/Game/Audio/Audio_FI/Ambience/A30/Positionals/Exterior/Fauna/AlienAnimals/WwiseEvents/Play_AMB_ENV_A30_AlienAnimal_I` | WwiseEvent | 0.00 |  |  | A30 | no | off-setting (tropical/alien/marine) [setting] |
| `/Game/Audio/Audio_FI/Ambience/A30/Positionals/Exterior/Fauna/AlienAnimals/WwiseEvents/Play_AMB_ENV_A30_Ext_AlienAnimal_A` | WwiseEvent | 0.00 |  |  | A30 | no | off-setting (tropical/alien/marine) [setting] |
| `/Game/Audio/Audio_FI/Ambience/A30/Positionals/Exterior/Fauna/AlienAnimals/WwiseEvents/Play_AMB_ENV_A30_Ext_AlienAnimal_B` | WwiseEvent | 0.00 |  |  | A30 | no | off-setting (tropical/alien/marine) [setting] |
| `/Game/Audio/Audio_FI/Ambience/A30/Positionals/Exterior/Fauna/AlienAnimals/WwiseEvents/Play_AMB_ENV_A30_Ext_AlienAnimal_C` | WwiseEvent | 0.00 |  |  | A30 | no | off-setting (tropical/alien/marine) [setting] |
| `/Game/Audio/Audio_FI/Ambience/A30/Positionals/Exterior/Fauna/Birds/WwiseEvents/Play_AMB_ENV_A30_AlienBirds_A` | WwiseEvent | 0.00 |  |  | A30 | no | off-setting (tropical/alien/marine) [setting] |
| `/Game/Audio/Audio_FI/Ambience/A30/Positionals/Exterior/Fauna/Birds/WwiseEvents/Play_AMB_ENV_A30_AlienBirds_B` | WwiseEvent | 0.00 |  |  | A30 | no | off-setting (tropical/alien/marine) [setting] |
| `/Game/Audio/Audio_FI/Ambience/A30/Positionals/Exterior/Fauna/Birds/WwiseEvents/Play_AMB_ENV_A30_AlienBirds_C` | WwiseEvent | 0.00 |  |  | A30 | no | off-setting (tropical/alien/marine) [setting] |
| `/Game/Audio/Audio_FI/Ambience/A30/Positionals/Exterior/Fauna/Birds/WwiseEvents/Play_AMB_ENV_A30_AlienBirds_D` | WwiseEvent | 0.00 |  |  | A30 | no | off-setting (tropical/alien/marine) [setting] |
| `/Game/Audio/Audio_FI/Ambience/A30/Positionals/Exterior/Fauna/Birds/WwiseEvents/Play_AMB_ENV_A30_AlienBirds_E` | WwiseEvent | 0.00 |  |  | A30 | no | off-setting (tropical/alien/marine) [setting] |
| `/Game/Audio/Audio_FI/Ambience/A30/Positionals/Exterior/Fauna/Birds/WwiseEvents/Play_AMB_ENV_A30_AlienBirds_F` | WwiseEvent | 0.00 |  |  | A30 | no | off-setting (tropical/alien/marine) [setting] |
| `/Game/Audio/Audio_FI/Ambience/A30/Positionals/Exterior/Fauna/Birds/WwiseEvents/Play_AMB_ENV_A30_AlienBirds_G` | WwiseEvent | 0.00 |  |  | A30 | no | off-setting (tropical/alien/marine) [setting] |
| `/Game/Audio/Audio_FI/Ambience/A30/Positionals/Exterior/Fauna/Birds/WwiseEvents/Play_AMB_ENV_A30_AlienBirds_H` | WwiseEvent | 0.00 |  |  | A30 | no | packed AO/roughness/height map; off-setting (tropical/alien/marine) [setting] |
| `/Game/Audio/Audio_FI/Ambience/A30/Positionals/Exterior/Fauna/Birds/WwiseEvents/Play_AMB_ENV_A30_AlienBirds_I` | WwiseEvent | 0.00 |  |  | A30 | no | off-setting (tropical/alien/marine) [setting] |
| `/Game/Audio/Audio_FI/Ambience/A30/Positionals/Exterior/Fauna/Birds/WwiseEvents/Play_AMB_ENV_A30_Ext_Bird_A` | WwiseEvent | 0.02 |  |  | A30 | no |  |
| `/Game/Audio/Audio_FI/Ambience/A30/Positionals/Exterior/Fauna/Birds/WwiseEvents/Play_AMB_ENV_A30_Ext_Bird_B` | WwiseEvent | 0.02 |  |  | A30 | no |  |
| `/Game/Audio/Audio_FI/Ambience/A30/Positionals/Exterior/Fauna/Birds/WwiseEvents/Play_AMB_ENV_A30_Ext_Bird_C` | WwiseEvent | 0.02 |  |  | A30 | no |  |
| `/Game/Audio/Audio_FI/Ambience/A30/Positionals/Exterior/Fauna/Birds/WwiseEvents/Play_AMB_ENV_A30_Ext_Bird_D` | WwiseEvent | 0.02 |  |  | A30 | no |  |
| `/Game/Audio/Audio_FI/Ambience/A30/Positionals/Exterior/Fauna/Birds/WwiseEvents/Play_AMB_ENV_A30_Ext_Bird_E` | WwiseEvent | 0.02 |  |  | A30 | no |  |
| `/Game/Audio/Audio_FI/Ambience/A30/Positionals/Exterior/Fauna/Birds/WwiseEvents/Play_AMB_ENV_A30_Ext_Bird_F` | WwiseEvent | 0.02 |  |  | A30 | no |  |
| `/Game/Audio/Audio_FI/Ambience/A30/Positionals/Exterior/Fauna/Birds/WwiseEvents/Play_AMB_ENV_A30_Ext_Bird_G` | WwiseEvent | 0.02 |  |  | A30 | no |  |
| `/Game/Audio/Audio_FI/Ambience/A30/Positionals/Exterior/Fauna/Birds/WwiseEvents/Play_AMB_ENV_A30_Ext_Bird_H` | WwiseEvent | 0.02 |  |  | A30 | no | packed AO/roughness/height map |
| `/Game/Audio/Audio_FI/Ambience/A30/Positionals/Exterior/Fauna/Birds/WwiseEvents/Play_AMB_ENV_A30_Ext_Bird_K` | WwiseEvent | 0.02 |  |  | A30 | no |  |
| `/Game/Audio/Audio_FI/Ambience/A30/Positionals/Exterior/Fauna/Birds/WwiseEvents/Play_AMB_ENV_A30_Ext_Bird_L` | WwiseEvent | 0.02 |  |  | A30 | no |  |
| `/Game/Audio/Audio_FI/Ambience/A30/Positionals/Exterior/Fauna/Birds/WwiseEvents/Play_AMB_ENV_A30_Ext_Bird_Peacock_A` | WwiseEvent | 0.00 |  |  | A30 | no |  |
| `/Game/Audio/Audio_FI/Ambience/A30/Positionals/Exterior/Fauna/Birds/WwiseEvents/Play_AMB_ENV_A30_Ext_Bird_Peacock_B` | WwiseEvent | 0.00 |  |  | A30 | no |  |
| `/Game/Audio/Audio_FI/Ambience/A30/Positionals/Exterior/Fauna/Insects/WwiseEvents/Play_AMB_ENV_A30_AlienInsect_LP_A` | WwiseEvent | 0.00 |  |  | A30 | no | off-setting (tropical/alien/marine) [setting] |
| `/Game/Audio/Audio_FI/Ambience/A30/Positionals/Exterior/Fauna/Insects/WwiseEvents/Play_AMB_ENV_A30_Cicadas_LP_A` | WwiseEvent | 0.00 |  |  | A30 | no |  |
| `/Game/Audio/Audio_FI/Ambience/A30/Positionals/Exterior/Fauna/Insects/WwiseEvents/Play_AMB_ENV_A30_Insects_LP_A` | WwiseEvent | 0.00 |  |  | A30 | no |  |
| `/Game/Audio/Audio_FI/Ambience/A30/Positionals/Exterior/Fauna/Insects/WwiseEvents/Play_AMB_ENV_A30_Insects_LP_B` | WwiseEvent | 0.00 |  |  | A30 | no |  |
| `/Game/Audio/Audio_FI/Ambience/A30/Positionals/Exterior/Fauna/Insects/WwiseEvents/Play_AMB_ENV_A30_Insects_LP_C` | WwiseEvent | 0.00 |  |  | A30 | no |  |
| `/Game/Audio/Audio_FI/Ambience/A30/Positionals/Exterior/Fauna/Insects/WwiseEvents/Play_AMB_ENV_A30_Insects_LP_D` | WwiseEvent | 0.00 |  |  | A30 | no |  |
| `/Game/Audio/Audio_FI/Ambience/A30/Positionals/Exterior/Fauna/Insects/WwiseEvents/Play_AMB_ENV_A30_Insects_LP_E` | WwiseEvent | 0.00 |  |  | A30 | no |  |
| `/Game/Audio/Audio_FI/Ambience/A30/Positionals/Exterior/Fires/WwiseEvents/Play_AMB_ENV_A30_Fire_Coals_Small` | WwiseEvent | 0.00 |  |  | A30 | no |  |
| `/Game/Audio/Audio_FI/Ambience/A30/Positionals/Exterior/Fires/WwiseEvents/Play_AMB_ENV_A30_Fire_Flare` | WwiseEvent | 0.00 |  |  | A30 | no |  |
| `/Game/Audio/Audio_FI/Ambience/A30/Positionals/Exterior/Fires/WwiseEvents/Play_AMB_ENV_A30_Fire_Grass_Large` | WwiseEvent | 0.00 |  |  | A30 | no |  |
| `/Game/Audio/Audio_FI/Ambience/A30/Positionals/Exterior/Fires/WwiseEvents/Play_AMB_ENV_A30_Fire_Grass_Medium` | WwiseEvent | 0.00 |  |  | A30 | no |  |
| `/Game/Audio/Audio_FI/Ambience/A30/Positionals/Exterior/Fires/WwiseEvents/Play_AMB_ENV_A30_Fire_Grass_Small_LP` | WwiseEvent | 0.00 |  |  | A30 | no |  |
| `/Game/Audio/Audio_FI/Ambience/A30/Positionals/Exterior/Fires/WwiseEvents/Play_AMB_ENV_A30_Fire_Metal_Small` | WwiseEvent | 0.00 |  |  | A30 | no |  |
| `/Game/Audio/Audio_FI/Ambience/A30/Positionals/Exterior/Fires/WwiseEvents/Play_AMB_ENV_A30_Fire_Tree_Large` | WwiseEvent | 0.00 |  |  | A30 | no |  |
| `/Game/Audio/Audio_FI/Ambience/A30/Positionals/Exterior/Fires/WwiseEvents/Play_AMB_ENV_A30_Fire_Tree_Medium` | WwiseEvent | 0.00 |  |  | A30 | no |  |
| `/Game/Audio/Audio_FI/Ambience/A30/Positionals/Exterior/Winds/WwiseEvents/Play_AMB_ENV_A30_Ext_WindGusts_A` | WwiseEvent | 0.00 |  |  | A30,B40 | no |  |
| `/Game/Audio/Audio_FI/Ambience/A30/Positionals/Exterior/Winds/WwiseEvents/Play_AMB_ENV_A30_Ext_WindGusts_B` | WwiseEvent | 0.00 |  |  | A30 | no |  |
| `/Game/Audio/Audio_FI/Ambience/A30/Positionals/Exterior/Winds/WwiseEvents/Play_AMB_ENV_A30_Ext_WindGusts_C` | WwiseEvent | 0.00 |  |  | A30 | no |  |
| `/Game/Audio/Audio_FI/Ambience/A30/Positionals/Exterior/Winds/WwiseEvents/Play_AMB_ENV_A30_Ext_WindGusts_D` | WwiseEvent | 0.00 |  |  | A30 | no |  |
| `/Game/Audio/Audio_FI/Ambience/A30/Positionals/Exterior/water/WwiseEvents/Play_AMB_ENV_A30_Ext_LargeWaterfall` | WwiseEvent | 0.00 |  |  | A30 | no |  |
| `/Game/Audio/Audio_FI/Ambience/A30/Positionals/Exterior/water/WwiseEvents/Play_AMB_ENV_A30_Ext_MediumWaterfall` | WwiseEvent | 0.00 |  |  | A30 | no |  |
| `/Game/Audio/Audio_FI/Ambience/A30/Positionals/Exterior/water/WwiseEvents/Play_AMB_ENV_A30_Ext_River` | WwiseEvent | 0.00 |  |  | A30 | no |  |
| `/Game/Audio/Audio_FI/Ambience/A30/Positionals/Exterior/water/WwiseEvents/Play_AMB_ENV_A30_Ext_RiverCalm` | WwiseEvent | 0.00 |  |  | A30 | no |  |
| `/Game/Audio/Audio_FI/Ambience/A30/Positionals/Exterior/water/WwiseEvents/Play_AMB_ENV_A30_Ext_RiverFast` | WwiseEvent | 0.00 |  |  | A30 | no |  |
| `/Game/Audio/Audio_FI/Ambience/A30/Positionals/Exterior/water/WwiseEvents/Play_AMB_ENV_A30_Ext_SmallWaterfall` | WwiseEvent | 0.00 |  |  | A30 | no |  |
| `/Game/Audio/Audio_FI/Ambience/A30/Positionals/Exterior/water/WwiseEvents/Play_AMB_ENV_A30_River_Rapids_LP` | WwiseEvent | 0.00 |  |  | A30 | no |  |
| `/Game/Audio/Audio_FI/Ambience/A30/Positionals/Exterior/water/WwiseEvents/Play_AMB_ENV_A30_River_Splashes_Large_LP` | WwiseEvent | 0.00 |  |  | A30 | no |  |
| `/Game/Audio/Audio_FI/Ambience/A30/Positionals/Exterior/water/WwiseEvents/Play_AMB_ENV_A30_Waterfall_Splashes_LP` | WwiseEvent | 0.00 |  |  | A30 | no |  |
| `/Game/Audio/Audio_FI/Ambience/A50/A50_BaseAirs/A50_Exteriors/WwiseEvents/Play_AMB_BaseAir_A50_Ext_Plateau_General` | WwiseEvent | 0.00 |  |  | A50 | no |  |
| `/Game/Audio/Audio_FI/Ambience/A50/A50_BaseAirs/A50_Exteriors/WwiseEvents/Play_AMB_BaseAir_A50_Ext_Plateau_GravLift` | WwiseEvent | 0.00 |  |  | A50 | no |  |
| `/Game/Audio/Audio_FI/Ambience/A50/A50_BaseAirs/A50_Exteriors/WwiseEvents/Play_AMB_Baseair_A50_Ext_Medium` | WwiseEvent | 0.00 |  |  | A50 | no |  |
| `/Game/Audio/Audio_FI/Ambience/B30/Exterior/Fire/WwiseEvents/Play_AMB_ENV_B30_Fire_Coals_Small` | WwiseEvent | 0.00 |  |  | B30 | no |  |
| `/Game/Audio/Audio_FI/Ambience/B30/Exterior/Fire/WwiseEvents/Play_AMB_ENV_B30_Fire_Flare` | WwiseEvent | 0.00 |  |  | B30 | no |  |
| `/Game/Audio/Audio_FI/Ambience/B30/Exterior/Fire/WwiseEvents/Play_AMB_ENV_B30_Fire_Grass_Large` | WwiseEvent | 0.00 |  |  | B30 | no |  |
| `/Game/Audio/Audio_FI/Ambience/B30/Exterior/Fire/WwiseEvents/Play_AMB_ENV_B30_Fire_Grass_Medium` | WwiseEvent | 0.00 |  |  | B30 | no |  |
| `/Game/Audio/Audio_FI/Ambience/B30/Exterior/Fire/WwiseEvents/Play_AMB_ENV_B30_Fire_Grass_Small_LP` | WwiseEvent | 0.00 |  |  | B30 | no |  |
| `/Game/Audio/Audio_FI/Ambience/B30/Exterior/Fire/WwiseEvents/Play_AMB_ENV_B30_Fire_Metal_Small` | WwiseEvent | 0.00 |  |  | B30 | no |  |
| `/Game/Audio/Audio_FI/Ambience/B30/Exterior/Fire/WwiseEvents/Play_AMB_ENV_B30_Fire_Tree_Large` | WwiseEvent | 0.00 |  |  | B30 | no |  |
| `/Game/Audio/Audio_FI/Ambience/B30/Exterior/Fire/WwiseEvents/Play_AMB_ENV_B30_Fire_Tree_Medium` | WwiseEvent | 0.00 |  |  | B30 | no |  |
| `/Game/Audio/Audio_FI/Ambience/B30/Exterior/Ocean/WwiseEvents/Play_AMB_BaseAir_B30_Ext_Ocean_Water_A_LP` | WwiseEvent | 0.00 |  |  | B30 | no |  |
| `/Game/Audio/Audio_FI/Ambience/B30/Exterior/Ocean/WwiseEvents/Play_AMB_BaseAir_Ext_Beachfront_LP` | WwiseEvent | 0.00 |  |  | B30 | no |  |
| `/Game/Audio/Audio_FI/Ambience/B30/Exterior/Ocean/WwiseEvents/Play_AMB_ENV_B30_Ext_Wind_Gusts_Cliffside_Vista_A_LP` | WwiseEvent | 0.00 |  |  | B30 | no |  |
| `/Game/Audio/Audio_FI/Ambience/B30/Interior/BaseAir/WwiseEvents/Play_AMB_BaseAir_B30_Int_Cavernous_Room` | WwiseEvent | 0.00 |  |  | B30 | no |  |
| `/Game/Audio/Audio_FI/Ambience/B30/Interior/BaseAir/WwiseEvents/Play_AMB_BaseAir_B30_Int_General` | WwiseEvent | 0.00 |  |  | B30 | no |  |
| `/Game/Audio/Audio_FI/Ambience/B30/Interior/BaseAir/WwiseEvents/Play_AMB_BaseAir_B30_Int_Large_Room` | WwiseEvent | 0.00 |  |  | B30 | no |  |
| `/Game/Audio/Audio_FI/Ambience/B30/Interior/BaseAir/WwiseEvents/Play_AMB_BaseAir_B30_Int_Med_Hallway` | WwiseEvent | 0.00 |  |  | B30 | no |  |
| `/Game/Audio/Audio_FI/Ambience/B30/Interior/BaseAir/WwiseEvents/Play_AMB_BaseAir_B30_Int_Med_Room` | WwiseEvent | 0.00 |  |  | B30 | no |  |
| `/Game/Audio/Audio_FI/Ambience/B30/Interior/BaseAir/WwiseEvents/Play_AMB_BaseAir_B30_Int_Sm_Hallway` | WwiseEvent | 0.00 |  |  | B30 | no |  |
| `/Game/Audio/Audio_FI/Ambience/B30/Interior/BaseAir/WwiseEvents/Play_AMB_BaseAir_B30_Int_Sm_Room` | WwiseEvent | 0.00 |  |  | B30 | no |  |
| `/Game/Audio/Audio_FI/Ambience/B30/Interior/BaseAir/WwiseEvents/Play_Forerunner_Interior_EntranceHallway` | WwiseEvent | 0.00 |  |  | B30 | no |  |
| `/Game/Audio/Audio_FI/Ambience/B40/BaseAirs/Exteriors/WwiseEvents/Play_AMB_BaseAir_B40_Ext_General` | WwiseEvent | 0.00 |  |  | B40 | no |  |
| `/Game/Audio/Audio_FI/Ambience/B40/BaseAirs/Exteriors/WwiseEvents/Play_AMB_BaseAir_B40_Ext_HeightWind` | WwiseEvent | 0.00 |  |  | B40 | no |  |
| `/Game/Audio/Audio_FI/Ambience/B40/BaseAirs/Exteriors/WwiseEvents/Play_AMB_BaseAir_B40_Ext_SmallCave` | WwiseEvent | 0.00 |  |  | B40 | no |  |
| `/Game/Audio/Audio_FI/Ambience/B40/BaseAirs/Interiors/WwiseEvents/Play_AMB_BaseAir_B40_Int_ElevatorShaft` | WwiseEvent | 0.00 |  |  | B40 | no |  |
| `/Game/Audio/Audio_FI/Ambience/B40/BaseAirs/Interiors/WwiseEvents/Play_AMB_BaseAir_B40_Int_Hallway_A` | WwiseEvent | 0.00 |  |  | B40 | no |  |
| `/Game/Audio/Audio_FI/Ambience/B40/BaseAirs/Interiors/WwiseEvents/Play_AMB_BaseAir_B40_Int_Hallway_C` | WwiseEvent | 0.00 |  |  | B40 | no |  |
| `/Game/Audio/Audio_FI/Ambience/B40/BaseAirs/Interiors/WwiseEvents/Play_AMB_BaseAir_B40_Int_Large_A` | WwiseEvent | 0.00 |  |  | B40 | no |  |
| `/Game/Audio/Audio_FI/Ambience/B40/BaseAirs/Interiors/WwiseEvents/Play_AMB_BaseAir_B40_Int_Large_B` | WwiseEvent | 0.00 |  |  | B40 | no |  |
| `/Game/Audio/Audio_FI/Ambience/B40/BaseAirs/Interiors/WwiseEvents/Play_AMB_BaseAir_B40_Int_Med_A` | WwiseEvent | 0.00 |  |  | B40 | no |  |
| `/Game/Audio/Audio_FI/Ambience/B40/BaseAirs/Interiors/WwiseEvents/Play_AMB_BaseAir_B40_Int_Medium_B` | WwiseEvent | 0.00 |  |  | B40 | no |  |
| `/Game/Audio/Audio_FI/Ambience/B40/BaseAirs/Interiors/WwiseEvents/Play_AMB_BaseAir_B40_Int_Small_A` | WwiseEvent | 0.00 |  |  | B40 | no |  |
| `/Game/Audio/Audio_FI/Ambience/B40/BaseAirs/Interiors/WwiseEvents/Play_AMB_BaseAir_B40_Int_Small_B` | WwiseEvent | 0.00 |  |  | B40 | no |  |
| `/Game/Audio/Audio_FI/Ambience/B40/Positionals/Exterior/Fauna/AlienAnimals/WwiseEvents/Play_AMB_ENV_B40_Ext_AlienAnimal_A` | WwiseEvent | 0.00 |  |  | B40 | no | off-setting (tropical/alien/marine) [setting] |
| `/Game/Audio/Audio_FI/Ambience/B40/Positionals/Exterior/Fauna/AlienAnimals/WwiseEvents/Play_AMB_ENV_B40_Ext_AlienAnimal_B` | WwiseEvent | 0.00 |  |  | B40 | no | off-setting (tropical/alien/marine) [setting] |
| `/Game/Audio/Audio_FI/Ambience/B40/Positionals/Exterior/Fauna/AlienAnimals/WwiseEvents/Play_AMB_ENV_B40_Ext_AlienAnimal_C` | WwiseEvent | 0.00 |  |  | B40 | no | off-setting (tropical/alien/marine) [setting] |
| `/Game/Audio/Audio_FI/Ambience/B40/Positionals/Exterior/Fauna/AlienAnimals/WwiseEvents/Play_AMB_ENV_B40_Ext_AlienAnimal_D` | WwiseEvent | 0.00 |  |  | B40 | no | off-setting (tropical/alien/marine) [setting] |
| `/Game/Audio/Audio_FI/Ambience/B40/Positionals/Exterior/Fires/WwiseEvents/Play_AMB_ENV_B40_Fire_Coals_Small` | WwiseEvent | 0.00 |  |  | B40 | no |  |
| `/Game/Audio/Audio_FI/Ambience/B40/Positionals/Exterior/Fires/WwiseEvents/Play_AMB_ENV_B40_Fire_Grass_Large` | WwiseEvent | 0.00 |  |  | B40 | no |  |
| `/Game/Audio/Audio_FI/Ambience/B40/Positionals/Exterior/Fires/WwiseEvents/Play_AMB_ENV_B40_Fire_Grass_Medium` | WwiseEvent | 0.00 |  |  | B40 | no |  |
| `/Game/Audio/Audio_FI/Ambience/B40/Positionals/Exterior/Fires/WwiseEvents/Play_AMB_ENV_B40_Fire_Grass_Small_LP` | WwiseEvent | 0.00 |  |  | B40 | no |  |
| `/Game/Audio/Audio_FI/Ambience/B40/Positionals/Exterior/Fires/WwiseEvents/Play_AMB_ENV_B40_Fire_Metal_Small` | WwiseEvent | 0.00 |  |  | B40 | no |  |
| `/Game/Audio/Audio_FI/Ambience/B40/Positionals/Exterior/Fires/WwiseEvents/Play_AMB_ENV_B40_Fire_Tree_Large` | WwiseEvent | 0.00 |  |  | B40 | no |  |
| `/Game/Audio/Audio_FI/Ambience/B40/Positionals/Exterior/Flora/Winds/WwiseEvents/Play_AMB_ENV_B40_Ext_WindGusts_A` | WwiseEvent | 0.00 |  |  | B40 | no |  |
| `/Game/Audio/Audio_FI/Ambience/B40/Positionals/Exterior/Flora/Winds/WwiseEvents/Play_AMB_ENV_B40_Ext_WindGusts_B` | WwiseEvent | 0.00 |  |  | B40 | no |  |
| `/Game/Audio/Audio_FI/Ambience/B40/Positionals/Exterior/Flora/Winds/WwiseEvents/Play_AMB_ENV_B40_Ext_WindGusts_C` | WwiseEvent | 0.00 |  |  | B40 | no |  |
| `/Game/Audio/Audio_FI/Ambience/B40/Positionals/Exterior/Flora/Winds/WwiseEvents/Play_AMB_ENV_B40_Ext_WindGusts_D` | WwiseEvent | 0.00 |  |  | B40 | no |  |
| `/Game/Audio/Audio_FI/Ambience/B40/Positionals/Exterior/Flora/Winds/WwiseEvents/Play_AMB_ENV_B40_Ext_Wind_Gusts_Cliffside_Vista_A_LP` | WwiseEvent | 0.00 |  |  | B40 | no |  |
| `/Game/Audio/Audio_FI/Ambience/B40/Positionals/Exterior/Flora/ice/WwiseEvents/Play_AMB_ENV_B40_IceGroans` | WwiseEvent | 0.00 |  |  | B40 | no |  |
| `/Game/Audio/Audio_FI/Ambience/B40/Positionals/Exterior/objects/GravBridgeBeam/WwiseEvents/Play_AMB_ENV_B40_GravBridgeBeam_LP` | WwiseEvent | 0.00 |  |  | B40 | no |  |
| `/Game/Audio/Audio_FI/Ambience/B40/Positionals/Exterior/objects/ZigguratTowerBeam/WwiseEvents/Play_AMB_ENV_B40_ZigguratTowerBeam_Energy_LP` | WwiseEvent | 0.00 |  |  | B40 | no |  |
| `/Game/Audio/Audio_FI/Ambience/C10/C10_Positionals/C10_Exterior/C10_Fires/WwiseEvents/Play_AMB_ENV_C10_Cov_Flames_Large_LP` | WwiseEvent | 0.00 |  |  | C10 | no |  |
| `/Game/Audio/Audio_FI/Ambience/C10/C10_Positionals/C10_Exterior/C10_Fires/WwiseEvents/Play_AMB_ENV_C10_Fire_Coals_Small` | WwiseEvent | 0.00 |  |  | C10 | no |  |
| `/Game/Audio/Audio_FI/Ambience/C10/C10_Positionals/C10_Exterior/C10_Fires/WwiseEvents/Play_AMB_ENV_C10_Fire_Grass_Large` | WwiseEvent | 0.00 |  |  | C10 | no |  |
| `/Game/Audio/Audio_FI/Ambience/C10/C10_Positionals/C10_Exterior/C10_Fires/WwiseEvents/Play_AMB_ENV_C10_Fire_Grass_Medium` | WwiseEvent | 0.00 |  |  | C10 | no |  |
| `/Game/Audio/Audio_FI/Ambience/C10/C10_Positionals/C10_Exterior/C10_Fires/WwiseEvents/Play_AMB_ENV_C10_Fire_Grass_Small_LP` | WwiseEvent | 0.00 |  |  | C10 | no |  |
| `/Game/Audio/Audio_FI/Ambience/C10/C10_Positionals/C10_Exterior/C10_Fires/WwiseEvents/Play_AMB_ENV_C10_Fire_Metal_Small` | WwiseEvent | 0.00 |  |  | C10 | no |  |
| `/Game/Audio/Audio_FI/Ambience/C10/C10_Positionals/C10_Exterior/C10_Fires/WwiseEvents/Play_AMB_ENV_C10_Fire_Tree_Large` | WwiseEvent | 0.00 |  |  | C10 | no |  |
| `/Game/Audio/Audio_FI/Ambience/C10/C10_Positionals/C10_Exterior/C10_Fires/WwiseEvents/Play_AMB_ENV_C10_Fire_Tree_Medium` | WwiseEvent | 0.00 |  |  | C10 | no |  |
| `/Game/Audio/Audio_FI/Ambience/C20/BaseAirs/WwiseEvents/Play_AMB_BaseAir_C20_Int_ElevatorShaft` | WwiseEvent | 0.00 |  |  | C20 | no |  |
| `/Game/Audio/Audio_FI/Ambience/C20/BaseAirs/WwiseEvents/Play_AMB_BaseAir_C20_Int_FloodGeneral` | WwiseEvent | 0.00 |  |  | C20 | no |  |
| `/Game/Audio/Audio_FI/Ambience/C20/BaseAirs/WwiseEvents/Play_AMB_BaseAir_C20_Int_General` | WwiseEvent | 0.00 |  |  | C20 | no |  |
| `/Game/Audio/Audio_FI/Ambience/C20/BaseAirs/WwiseEvents/Play_AMB_BaseAir_C20_Int_Hallway_Spooky_A` | WwiseEvent | 0.00 |  |  | C20 | no |  |
| `/Game/Audio/Audio_FI/Ambience/C20/BaseAirs/WwiseEvents/Play_AMB_BaseAir_C20_Int_Large` | WwiseEvent | 0.00 |  |  | C20 | no |  |
| `/Game/Audio/Audio_FI/Ambience/C20/BaseAirs/WwiseEvents/Play_AMB_BaseAir_C20_Int_Large_Spooky_A` | WwiseEvent | 0.00 |  |  | C20 | no |  |
| `/Game/Audio/Audio_FI/Ambience/C20/BaseAirs/WwiseEvents/Play_AMB_BaseAir_C20_Int_Large_Spooky_B` | WwiseEvent | 0.00 |  |  | C20 | no |  |
| `/Game/Audio/Audio_FI/Ambience/C20/BaseAirs/WwiseEvents/Play_AMB_BaseAir_C20_Int_Large_Spooky_C` | WwiseEvent | 0.00 |  |  | C20 | no |  |
| `/Game/Audio/Audio_FI/Ambience/C20/BaseAirs/WwiseEvents/Play_AMB_BaseAir_C20_Int_Med` | WwiseEvent | 0.00 |  |  | C20 | no |  |
| `/Game/Audio/Audio_FI/Ambience/C20/BaseAirs/WwiseEvents/Play_AMB_BaseAir_C20_Int_Med_Spooky_A` | WwiseEvent | 0.00 |  |  | C20 | no |  |
| `/Game/Audio/Audio_FI/Ambience/C20/BaseAirs/WwiseEvents/Play_AMB_BaseAir_C20_Int_Med_Spooky_B` | WwiseEvent | 0.00 |  |  | C20 | no |  |
| `/Game/Audio/Audio_FI/Ambience/C20/BaseAirs/WwiseEvents/Play_AMB_BaseAir_C20_Int_Small_Spooky_A` | WwiseEvent | 0.00 |  |  | C20 | no |  |
| `/Game/Audio/Audio_FI/Ambience/C20/BaseAirs/WwiseEvents/Play_AMB_BaseAir_C20_Int_Small_Spooky_B` | WwiseEvent | 0.00 |  |  | C20 | no |  |

*Group note:* Wwise events (AkAudioEvent). PWR plays its own SoundWaves; Wwise integration from level data is unverified

### Forerunner light fixture meshes and kits (54)

*Where on PWR:* Base exteriors, bridge decks, landing pads

| path | kind | MB | verts | bounds m | levels | PWR | note |
|---|---|---|---|---|---|---|---|
| `/Game/Env/HS/FR/Gen/Lights/FR_GEN_Light_Fixture_Arrow_A/SM_FR_GEN_Light_Fixture_Arrow_A` | StaticMesh | 0.53 | 17,501 | 1.18x0.8x0.1 | B30,B40,C20,C45 | no |  |
| `/Game/Env/HS/FR/Gen/Lights/FR_GEN_Light_Fixture_Bend_a/SM_FR_GEN_Light_Fixture_Bend_a` | StaticMesh | 0.54 | 11,146 | 0.62x0.18x0.21 | A30,B40,C20,C45 | no |  |
| `/Game/Env/HS/FR/Gen/Lights/FR_GEN_Light_Fixture_Bend_b/SM_FR_GEN_Light_Fixture_Bend_b` | StaticMesh | 0.88 | 23,876 | 0.47x0.18x0.21 | B30,C10,C45 | no |  |
| `/Game/Env/HS/FR/Gen/Lights/FR_GEN_Light_Fixture_Ceiling_Small_a/SM_FR_GEN_Light_Fixture_Ceiling_Small_a` | StaticMesh | 3.93 | 105,282 | 0.52x0.52x0.33 | B40,C45 | no |  |
| `/Game/Env/HS/FR/Gen/Lights/FR_GEN_Light_Fixture_Panel_a/SM_FR_GEN_Light_Fixture_Panel_a` | StaticMesh | 0.26 | 8,750 | 3.61x0.18x0.03 | A30,B30,B40,C10,C20,C45 | no |  |
| `/Game/Env/HS/FR/Gen/Lights/FR_GEN_Light_Fixture_Panel_b/SM_FR_GEN_Light_Fixture_Panel_b` | StaticMesh | 1.01 | 17,287 | 5.04x0.72x0.05 | A30,B30,B40,C10,C45 | no |  |
| `/Game/Env/HS/FR/Gen/Lights/FR_GEN_Light_Fixture_Puck_Med_a/SM_FR_GEN_Light_Fixture_Puck_Med_a` | StaticMesh | 0.31 | 10,949 | 0.68x0.1x0.24 | A30,B30,B40,C10,C20,C45 | no |  |
| `/Game/Env/HS/FR/Gen/Lights/FR_GEN_Light_Fixture_Puck_a/SM_FR_GEN_Light_Fixture_Puck_a` | StaticMesh | 0.49 | 10,555 | 0.2x0.14x0.12 | A30,B30,B40,C20,C45 | no |  |
| `/Game/Env/HS/FR/Gen/Lights/FR_GEN_Light_Fixture_Puck_c/SM_FR_GEN_Light_Fixture_Puck_c` | StaticMesh | 0.29 | 8,719 | 0.3x0.3x0.21 | B30 | no |  |
| `/Game/Env/HS/FR/Gen/Lights/FR_GEN_Light_Fixture_Tall_a/SM_FR_GEN_Light_Fixture_Tall_a` | StaticMesh | 0.33 | 9,823 | 0.04x0.18x0.89 | A30,B30,B40,C20,C45 | no |  |
| `/Game/Env/HS/FR/Gen/Lights/FR_GEN_Light_Fixture_Tall_a/SM_FR_GEN_Light_Fixture_Tall_a_Mirrored` | StaticMesh | 0.31 | 9,102 | 0.04x0.18x0.89 | A15,A30,A50,B30,B40,C10,C20,C45,D20,D40,E10,E20,E30 | no |  |
| `/Game/Env/HS/FR/Gen/Lights/FR_Gen_Light_Fixture_Base_Plate_Trapezoid_cm_w158_d6_h78_A/SM_FR_Gen_Light_Fixture_Base_Plate_Trapezoid_cm_w158_d6_h78_A` | StaticMesh | 2.00 | 58,898 | 0.05x1.59x0.78 | B40,C45 | no |  |
| `/Game/Env/HS/FR/Gen/Lights/FR_Gen_Light_Fixture_Base_Plate_Trapezoid_cm_w158_d6_h78_A/SM_FR_Gen_Light_Fixture_Base_Plate_Trapezoid_cm_w158_d6_h78_B` | StaticMesh | 0.63 | 20,565 | 0.05x1.59x0.78 | A30,B30,B40,C10,C20,C45 | no |  |
| `/Game/Env/HS/FR/Gen/Lights/FR_Gen_Light_Fixture_SIL_Med_A_cm_w45_d15_h55_A/SM_FR_Gen_Light_Fixture_SIL_Med_A_cm_w45_d15_h55_A` | StaticMesh | 0.08 | 484 | 0.45x1.38x1.69 | B30 | no |  |
| `/Game/Env/HS/FR/Gen/Lights/FR_Gen_Light_Fixture_SIL_Med_A_cm_w45_d15_h55_A/SM_FR_Gen_Light_Fixture_SIL_Med_A_cm_w45_d15_h55_b` | StaticMesh | 0.06 | 455 | 0.33x0.38x1.75 | B30 | no |  |
| `/Game/Env/HS/FR/Gen/Lights/FR_Gen_Light_Fixture_SIL_Sml_Beam_A_cm_w28_d29_h1_A/SM_FR_Gen_Light_Fixture_SIL_Sml_Beam_A_cm_w28_d29_h1_A` | StaticMesh | 1.43 | 48,662 | 0.28x0.3x0.01 | B30,C45 | no |  |
| `/Game/Env/HS/FR/Gen/Lights/FR_Gen_Light_Fixture_Sconce_Large_A/SM_FR_Gen_Light_Fixture_Sconce_Large_A` | StaticMesh | 1.81 | 34,236 | 0.49x1.39x1.13 | B30 | no |  |
| `/Game/Env/HS/FR/Gen/Lights/SM_FR_Ceiling_Light_Round_A_fr_ceiling_light_a` | StaticMesh | 0.16 | 1,096 | 1.7x1.7x0.18 | B30 | no |  |
| `/Game/Env/HS/FR/Gen/Lights/SM_FR_GEN_Light_Fixture_pucka` | StaticMesh | 0.08 | 772 | 0.2x0.14x0.13 | A30,B30 | no |  |
| `/Game/Env/HS/FR/Gen/Lights/SM_FR_GEN_Light_Fixture_puckb` | StaticMesh | 0.06 | 396 | 0.25x0.3x0.09 | B30 | no |  |
| `/Game/Env/HS/FR/Gen/Lights/SM_FR_GEN_Light_Fixture_puckc` | StaticMesh | 0.04 | 829 | 0.3x0.3x0.21 | A30,B30 | no |  |
| `/Game/Env/HS/FR/Gen/Lights/SM_FR_GEN_Light_Fixture_tall` | StaticMesh | 0.18 | 1,274 | 0.03x0.18x0.89 | A30,C20 | no |  |
| `/Game/Env/HS/FR/Gen/Lights/SM_FR_Wall_Light_Med_A` | StaticMesh | 0.04 | 568 | 0.47x1.44x0.92 | A30 | no |  |
| `/Game/Env/HS/FR/Gen/Lights/SM_FR_Wall_Light_Med_B` | StaticMesh | 0.10 | 491 | 0.19x1.11x1.55 | A30 | no |  |
| `/Game/Env/HS/FR/Gen/Lights/SM_FR_Wall_Light_Small_A` | StaticMesh | 0.22 | 1,609 | 1.22x1.22x0.7 | B30 | no |  |
| `/Game/Env/HS/FR/Gen/Lights/SM_Socket_Generic_Trapezoid` | StaticMesh | 0.03 | 259 | 0.02x0.03x0.0 |  | no |  |
| `/Game/Lighting/Lighting_Kits/Forerunner/A30_Lights/BP_A30_Highlight_Blue` | Blueprint | 0.00 |  |  | A30 | no |  |
| `/Game/Lighting/Lighting_Kits/Forerunner/A30_Lights/BP_A30_wallpucks_small` | Blueprint | 0.00 |  |  | A30 | no |  |
| `/Game/Lighting/Lighting_Kits/Forerunner/A30_Lights/BP_FR_GEN_Light_Fixture_Puck_Med_HallA30` | Blueprint | 0.01 |  |  | A30 | no |  |
| `/Game/Lighting/Lighting_Kits/Forerunner/A30_Lights/BP_FR_GEN_Light_HallFloor_A30_LG` | Blueprint | 0.01 |  |  | A30 | no |  |
| `/Game/Lighting/Lighting_Kits/Forerunner/B40_lights/BP_FR_GEN_Light_Fixture_TallHall` | Blueprint | 0.00 |  |  | A30,B40 | no |  |
| `/Game/Lighting/Lighting_Kits/Forerunner/Meshes/MI_tempemissive_dim` | MaterialInstance | 0.00 |  |  | A30,B30,C20 | no |  |
| `/Game/Lighting/Lighting_Kits/Forerunner/Meshes/MI_tempemissive_dim_greenish` | MaterialInstance | 0.00 |  |  | B30 | no |  |
| `/Game/Lighting/Lighting_Kits/Forerunner/Meshes/M_TempEmissiveOverhead` | Material | 0.01 |  |  | B30 | no |  |
| `/Game/Lighting/Lighting_Kits/Forerunner/Meshes/M_tempemissive` | Material | 0.01 |  |  | A30,B30,C20 | no |  |
| `/Game/Lighting/Meshes/Forerunner/SM_Frunner_fixtureplate1` | StaticMesh | 0.08 | 1,590 | 6.6x0.56x6.6 | A30,B30,B40,C45 | no |  |
| `/Game/Lighting/Meshes/Forerunner/SM_Frunner_fixtureplate2` | StaticMesh | 0.03 | 640 | 3.57x0.46x5.0 | B30,C10 | no |  |
| `/Game/Lighting/Meshes/Forerunner/SM_Frunner_frame` | StaticMesh | 0.14 | 1,448 | 2.55x0.27x4.68 | A30 | no |  |
| `/Game/Lighting/Puck_BPs/Forerunner/B40/BP_FRPuck_Fixture_03` | Blueprint | 0.00 |  |  | B40,C45 | no |  |
| `/Game/Lighting/Puck_BPs/Forerunner/BP_FRPuck_Master` | Blueprint | 0.05 |  |  | A15,A30,A50,B30,B40,C10,C20,C45,D20,D40,E10,E20,E30 | no |  |
| `/Game/Lighting/Puck_BPs/Forerunner/C20/BP_FRPuck_C20_ArenaPillarPuck_A` | Blueprint | 0.00 |  |  | C20 | no |  |
| `/Game/Lighting/Puck_BPs/Forerunner/C20/BP_FRPuck_C20_Blue` | Blueprint | 0.00 |  |  | C20 | no |  |
| `/Game/Lighting/Puck_BPs/Forerunner/C20/BP_FRPuck_C20_Blue_Lgt_Rect` | Blueprint | 0.00 |  |  | C20 | no |  |
| `/Game/Lighting/Puck_BPs/Forerunner/C20/BP_FRPuck_C20_Blue_Lgt_Rect_Sm` | Blueprint | 0.00 |  |  | C20 | no |  |
| `/Game/Lighting/Puck_BPs/Forerunner/C20/BP_FRPuck_C20_CylixEmissives` | Blueprint | 0.00 |  |  | C20 | no |  |
| `/Game/Lighting/Puck_BPs/Forerunner/C20/BP_FRPuck_C20_CylixEmissives_wLights` | Blueprint | 0.00 |  |  | C20 | no |  |
| `/Game/Lighting/Puck_BPs/Forerunner/C20/BP_FRPuck_C20_ElevatorHallPuckLight_A` | Blueprint | 0.00 |  |  | C20 | no |  |
| `/Game/Lighting/Puck_BPs/Forerunner/C20/BP_FRPuck_C20_FR_Mask_A` | Blueprint | 0.00 |  |  | C20 | no |  |
| `/Game/Lighting/Puck_BPs/Forerunner/C20/BP_FRPuck_C20_FR_Sticker_07_ThreeDash` | Blueprint | 0.00 |  |  | C20 | no |  |
| `/Game/Lighting/Puck_BPs/Forerunner/C20/BP_FRPuck_C20_MaintenanceTunnelPillarPuck_A` | Blueprint | 0.00 |  |  | C20 | no |  |
| `/Game/Lighting/Puck_BPs/Forerunner/C20/BP_FRPuck_C20_Neutral` | Blueprint | 0.00 |  |  | C20 | no |  |
| `/Game/Lighting/Puck_BPs/Forerunner/C20/BP_FRPuck_C20_ObeliskPuckLight_A` | Blueprint | 0.00 |  |  | C20 | no |  |
| `/Game/Lighting/Puck_BPs/Forerunner/C20/BP_FRPuck_C20_panel_long_Light_Rect` | Blueprint | 0.00 |  |  | C20 | no |  |
| `/Game/Lighting/Puck_BPs/Forerunner/C20/Meshes/SM_CylixPuck` | StaticMesh | 0.01 | 32 | 5.08x0.68x4.1 | C20 | no |  |

*Group note:* FR fixture meshes (tall, panel, puck, sconce, trapezoid plate) and the A30/B40 lighting-kit BPs

### UNSC light fixtures (17)

*Where on PWR:* UNSC LZ beacons/flood lights on the bases

| path | kind | MB | verts | bounds m | levels | PWR | note |
|---|---|---|---|---|---|---|---|
| `/Game/Env/HS/UNSC/Gen/Lights/SM_UNSC_Light_Door_Small_A` | StaticMesh | 0.18 | 1,418 | 0.18x0.93x0.33 | A30 | no |  |
| `/Game/Env/HS/UNSC/Gen/Lights/SM_UNSC_Light_Flush_Small_A` | StaticMesh | 0.09 | 1,598 | 0.47x0.61x0.1 | A30 | no |  |
| `/Game/Env/HS/UNSC/Gen/Lights/UNSC_Gen_EmergencyLight_Ceiling_w0i23_d0i23_h0i11_A/SM_UNSC_Gen_EmergencyLight_Ceiling_w0i23_d0i23_h0i11_A` | StaticMesh | 1.21 | 38,016 | 0.2x0.2x0.09 | A15,D40 | no |  |
| `/Game/Env/HS/UNSC/Gen/Lights/UNSC_Gen_HangingCeilingLightDoubleWide_Mudium_w1i27_d0i39_h0i12_A/SM_UNSC_Gen_HangingCeilingLightDoubleWide_Mudium_w1i27_d0i39_h0i12_A` | StaticMesh | 3.57 | 112,617 | 1.26x0.35x0.1 | A15,D40 | no |  |
| `/Game/Env/HS/UNSC/Gen/Lights/UNSC_Gen_HangingCeilingLight_Large_w1i5_d0i25_h0i85_A/SM_UNSC_Gen_HangingCeilingLight_Large_w1i5_d0i25_h0i85_A` | StaticMesh | 2.13 | 65,225 | 1.26x0.18x0.1 | A15,D40 | no |  |
| `/Game/Env/HS/UNSC/Gen/Lights/UNSC_Gen_HangingCeilingLight_Medium_w0i63_d0i17_h0i12_A/SM_UNSC_Gen_HangingCeilingLight_Medium_w0i63_d0i17_h0i12_A` | StaticMesh | 3.08 | 81,611 | 0.63x0.18x0.1 | A15,D40 | no |  |
| `/Game/Env/HS/UNSC/Gen/Lights/UNSC_Gen_HangingCeilingLight_Small_w0i25_d0i17_h0i08_A/SM_UNSC_Gen_HangingCeilingLight_Small_w0i25_d0i17_h0i08_A` | StaticMesh | 2.92 | 74,933 | 0.27x0.18x0.1 | A15,D40 | no |  |
| `/Game/Env/HS/UNSC/Gen/Lights/UNSC_Gen_InsetCeilingLight_Large_w1i2_d0i4_h0i05_A/SM_UNSC_Gen_InsetCeilingLight_Large_w1i2_d0i4_h0i05_A` | StaticMesh | 1.74 | 58,789 | 1.22x0.41x0.1 | A15,D40 | no |  |
| `/Game/Env/HS/UNSC/Gen/Lights/UNSC_Gen_InsetCeilingLight_Medium_w1i2_d0i29_h0i05_A/SM_UNSC_Gen_InsetCeilingLight_Medium_w1i2_d0i29_h0i05_A` | StaticMesh | 0.52 | 16,486 | 1.06x0.28x0.1 | A15,D40 | no |  |
| `/Game/Env/HS/UNSC/Gen/Lights/UNSC_Gen_InsetCeilingLight_Small_w0i85_d0i23_h0i05_A/SM_UNSC_Gen_InsetCeilingLight_Small_w0i85_d0i23_h0i05_A` | StaticMesh | 0.48 | 15,523 | 0.85x0.24x0.1 | A15 | no |  |
| `/Game/Env/HS/UNSC/Gen/Lights/UNSC_Gen_MedicalLight_Small_w0i42_d0i42_h0i10_A/SM_UNSC_Gen_MedicalLight_Small_w0i42_d0i42_h0i10_A` | StaticMesh | 2.14 | 56,693 | 0.42x0.42x0.1 | A15 | no |  |
| `/Game/Env/HS/UNSC/Gen/Lights/UNSC_Gen_PuckLight_w0i21_d0i18_h0i04_B/SM_UNSC_Gen_PuckLight_w0i21_d0i18_h0i04_B` | StaticMesh | 1.46 | 38,000 | 0.22x0.18x0.04 | A15,D40 | no |  |
| `/Game/Env/HS/UNSC/Gen/Lights/UNSC_Gen_PuckLight_w0i22_d0i22_h0i04_D/SM_UNSC_Gen_PuckLight_w0i22_d0i22_h0i04_D` | StaticMesh | 1.18 | 38,678 | 0.23x0.23x0.04 | A15,D40 | no |  |
| `/Game/Env/HS/UNSC/Gen/Lights/UNSC_Gen_PuckLight_w0i5_d0i15_h0i03_A/SM_UNSC_Gen_PuckLight_w0i5_d0i15_h0i03_A` | StaticMesh | 1.01 | 33,015 | 0.15x0.5x0.03 | A15,A30,A50,B30,B40,C10,C20,C45,D20,D40,E10,E20,E30 | no |  |
| `/Game/Env/HS/UNSC/Gen/Lights/UNSC_Gen_StripLight_Small_w0i25_h1i5_A/SM_UNSC_Gen_StripLight_Small_w0i25_h1i5_A` | StaticMesh | 0.03 | 604 | 0.0x0.03x0.15 | A15,D40 | no |  |
| `/Game/Env/HS/UNSC/Gen/Lights/UNSC_Gen_WallLight_Medium_w0i62_d0i12_h0i25_A/PLAY_SM_UNSC_Gen_WallLight_Medium_w0i62_d0i12_h0i25_A_CollisionMesh` | StaticMesh | 0.20 |  |  | A15 | no | collision proxy mesh |
| `/Game/Env/HS/UNSC/Gen/Lights/UNSC_Gen_WallLight_Small_w0i5_d0i17_h0i23_A/SM_UNSC_Gen_WallLight_Small_w0i5_d0i17_h0i23_A` | StaticMesh | 4.98 | 106,368 | 0.17x0.5x0.23 | A15,D40 | no |  |

*Group note:* Interior-scale UNSC fixtures

### Forerunner and swamp fog (17)

*Where on PWR:* Cold mist pooling inside the Forerunner bases, ground fog at the lakes at dawn

| path | kind | MB | verts | bounds m | levels | PWR | note |
|---|---|---|---|---|---|---|---|
| `/Game/FX/Library/Environment/Desert/Atmospherics/NS_HeatShimmer` | NiagaraSystem | 0.01 |  |  | E20 | no |  |
| `/Game/FX/Library/Environment/Forerunner/Atmospherics/FireSpline/BP_For_FireSpline` | Blueprint | 0.01 |  |  | C20 | no |  |
| `/Game/FX/Library/Environment/Forerunner/Atmospherics/FireSpline/NS_For_FireSpline` | NiagaraSystem | 0.07 |  |  | C20 | no |  |
| `/Game/FX/Library/Environment/Forerunner/Atmospherics/Fog/NS_For_ColdFogVapor` | NiagaraSystem | 0.04 |  |  | A30,B40,C45 | no |  |
| `/Game/FX/Library/Environment/Forerunner/Atmospherics/Fog/NS_For_FixturePanelMist_01` | NiagaraSystem | 0.08 |  |  | B40,C10,C45 | no |  |
| `/Game/FX/Library/Environment/Forerunner/Atmospherics/Fog/NS_For_FogEnergyCard_01` | NiagaraSystem | 0.02 |  |  | C10 | no |  |
| `/Game/FX/Library/Environment/Forerunner/Atmospherics/Fog/NS_For_FogFalling` | NiagaraSystem | 0.03 |  |  | B40 | no |  |
| `/Game/FX/Library/Environment/Forerunner/Atmospherics/Fog/NS_For_LightFixurePanel_01` | NiagaraSystem | 0.13 |  |  | B30 | no |  |
| `/Game/FX/Library/Environment/Forerunner/Atmospherics/Fog/NS_For_MistGround_01` | NiagaraSystem | 0.04 |  |  | B30,B40,C45 | no |  |
| `/Game/FX/Library/Environment/Forerunner/Atmospherics/Fog/NS_For_MistPatch_01` | NiagaraSystem | 0.02 |  |  | B30,C10 | no |  |
| `/Game/FX/Library/Environment/Forerunner/Atmospherics/Fog/NS_For_MistPatch_02` | NiagaraSystem | 0.02 |  |  | B30,C10 | no |  |
| `/Game/FX/Library/Environment/Forerunner/Atmospherics/Fog/NS_For_Mist_01` | NiagaraSystem | 0.03 |  |  | B30,C10 | no |  |
| `/Game/FX/Library/Environment/Forerunner/Atmospherics/LensFlares/NS_For_FlareHallway` | NiagaraSystem | 0.06 |  |  | B30 | no |  |
| `/Game/FX/Library/Environment/Forerunner/Atmospherics/LensFlares/NS_For_FlareWalkway` | NiagaraSystem | 0.06 |  |  | C10 | no |  |
| `/Game/FX/Library/Environment/Forerunner/Atmospherics/LensFlares/XGTGLensFlare/BP_For_XGTGLensFlare_Interior` | Blueprint | 0.00 |  |  | A30,C20,D20 | no |  |
| `/Game/FX/Library/Environment/Swamp/Atmospherics/Fog/NS_Swamp_FogAmbient_01` | NiagaraSystem | 0.01 |  |  | C10 | no |  |
| `/Game/FX/Library/Environment/Swamp/Atmospherics/Fog/NS_Swamp_GasPlumeFogCard_01` | NiagaraSystem | 0.04 |  |  | C10 | no |  |

*Group note:* Shipped Niagara

### Atmospherics (PNW): mist, dust, snow, pollen (36)

*Where on PWR:* Valley fog, snow gusts on peaks, dust motes in forests, rock-fall dust on cliffs

| path | kind | MB | verts | bounds m | levels | PWR | note |
|---|---|---|---|---|---|---|---|
| `/Game/FX/Library/Environment/PNW/Atmospherics/Dust/NS_SandBlowing_Const_Lp_01` | NiagaraSystem | 0.05 |  |  | D40 | no |  |
| `/Game/FX/Library/Environment/PNW/Atmospherics/DustMotes/BP_MoteController` | Blueprint | 0.01 |  |  | A15,A30,B30,C10,C20,D20,D40 | no | sibling used by PWR |
| `/Game/FX/Library/Environment/PNW/Atmospherics/DustMotes/NS_Ash_Falling` | NiagaraSystem | 0.04 |  |  | A15,A30,B30,D40 | no | sibling used by PWR |
| `/Game/FX/Library/Environment/PNW/Atmospherics/DustMotes/NS_DustMotes_Camera` | NiagaraSystem | 0.05 |  |  | A30,E20 | no | sibling used by PWR |
| `/Game/FX/Library/Environment/PNW/Atmospherics/DustMotes/NS_DustMotes_CameraAttached` | NiagaraSystem | 0.06 |  |  | A15,A30,B30,D40 | yes |  |
| `/Game/FX/Library/Environment/PNW/Atmospherics/DustMotes/NS_DustMotes_Camera_SplitScreen` | NiagaraSystem | 0.05 |  |  | A15,A30,B30,D40 | no | sibling used by PWR |
| `/Game/FX/Library/Environment/PNW/Atmospherics/DustMotes/NS_DustMotes_Med` | NiagaraSystem | 0.06 |  |  | A15,B40,C10,D40 | no | sibling used by PWR |
| `/Game/FX/Library/Environment/PNW/Atmospherics/DustMotes/NS_GravLift_DustMotes` | NiagaraSystem | 0.04 |  |  | D20 | no | sibling used by PWR |
| `/Game/FX/Library/Environment/PNW/Atmospherics/FallingRocks/NS_Dust_RockFallingLedges_01` | NiagaraSystem | 0.32 |  |  | A30,B30,E20 | no |  |
| `/Game/FX/Library/Environment/PNW/Atmospherics/FallingRocks/NS_Dust_RockFallingLedges_02` | NiagaraSystem | 0.15 |  |  | A30,A50,B40,C45,D20,E20 | no |  |
| `/Game/FX/Library/Environment/PNW/Atmospherics/FallingSand/BP_Dust_SandFallingLedgesSpline` | Blueprint | 0.01 |  |  | B40,D40 | no |  |
| `/Game/FX/Library/Environment/PNW/Atmospherics/FallingSand/NS_PNW_SandFallingLedges_01` | NiagaraSystem | 0.15 |  |  | A30,B40,D40 | no |  |
| `/Game/FX/Library/Environment/PNW/Atmospherics/Fog/NS_Fog_Ground` | NiagaraSystem | 0.03 |  |  | D20 | no |  |
| `/Game/FX/Library/Environment/PNW/Atmospherics/Fog/NS_PNW_FogAmbient_01` | NiagaraSystem | 0.02 |  |  | B40,C20,C45,D20 | no |  |
| `/Game/FX/Library/Environment/PNW/Atmospherics/LensFlares/BP_XGTGLensFlare_Sun` | Blueprint | 0.00 |  |  | B30 | no |  |
| `/Game/FX/Library/Environment/PNW/Atmospherics/Rain/BP_RainController` | Blueprint | 0.02 |  |  | B40,C10,C45 | no |  |
| `/Game/FX/Library/Environment/PNW/Atmospherics/Rain/BP_RainControllerC10` | Blueprint | 0.01 |  |  | C10 | no |  |
| `/Game/FX/Library/Environment/PNW/Atmospherics/Rain/BP_RainTrigger` | Blueprint | 0.01 |  |  | B40,C10,C45 | no |  |
| `/Game/FX/Library/Environment/PNW/Atmospherics/Rain/BP_WeatherVolume` | Blueprint | 0.01 |  |  | B40,C10,C45 | no |  |
| `/Game/FX/Library/Environment/PNW/Atmospherics/Rain/NS_PNW_Rain_Camera` | NiagaraSystem | 0.06 |  |  | C10 | no |  |
| `/Game/FX/Library/Environment/PNW/Atmospherics/Rain/NS_PNW_Rain_Camera_SplitScreen` | NiagaraSystem | 0.05 |  |  | C10 | no |  |
| `/Game/FX/Library/Environment/PNW/Atmospherics/Rain/NS_PNW_Rain_Simple` | NiagaraSystem | 0.01 |  |  | C10 | no |  |
| `/Game/FX/Library/Environment/PNW/Atmospherics/SandBlowing/BP_Dust_WindAlongCliffs` | Blueprint | 0.00 |  |  | A30,B40,C45 | no |  |
| `/Game/FX/Library/Environment/PNW/Atmospherics/SandBlowing/NS_PNW_SandBlowingGust_Lrg_01` | NiagaraSystem | 0.08 |  |  | A30,B30,D40 | no |  |
| `/Game/FX/Library/Environment/PNW/Atmospherics/SandBlowing/NS_PNW_SandBlowingGust_Med_01` | NiagaraSystem | 0.09 |  |  | A30,B30,E20 | no |  |
| `/Game/FX/Library/Environment/PNW/Atmospherics/SandBlowing/NS_PNW_SandBlowingGust_Med_NoGoundDust_01` | NiagaraSystem | 0.05 |  |  | A50,D40 | no |  |
| `/Game/FX/Library/Environment/PNW/Atmospherics/SandBlowing/NS_PNW_SandBlowingGust_Med_Vista_01` | NiagaraSystem | 0.09 |  |  | A50,D20,D40,E20 | no |  |
| `/Game/FX/Library/Environment/PNW/Atmospherics/SandBlowing/NS_PNW_SandBlowingGust_Sml_01` | NiagaraSystem | 0.08 |  |  | B30,D40 | no |  |
| `/Game/FX/Library/Environment/PNW/Atmospherics/SandBlowing/NS_PNW_WindAlongCliffs` | NiagaraSystem | 0.06 |  |  | A30,B40,C45 | no |  |
| `/Game/FX/Library/Environment/PNW/Atmospherics/Smoke/GroundFlare/NS_Smk_SignalFlare_01` | NiagaraSystem | 0.24 |  |  |  | no |  |
| `/Game/FX/Library/Environment/PNW/Atmospherics/Smoke/Smolder/NS_SmolderSmoke_Fast_01` | NiagaraSystem | 0.06 |  |  | D40 | no |  |
| `/Game/FX/Library/Environment/PNW/Atmospherics/Snow/NS_PNW_AmbientFallingSnow_Splitscreen` | NiagaraSystem | 0.10 |  |  | B40,C45 | no | snow variant |
| `/Game/FX/Library/Environment/PNW/Atmospherics/Snow/NS_PNW_AmbientFallingSnow_System` | NiagaraSystem | 0.11 |  |  | B40,C45 | no | snow variant |
| `/Game/FX/Library/Environment/PNW/Atmospherics/Snow/NS_PNW_FallingIceChunks_01` | NiagaraSystem | 0.13 |  |  | B40,C45 | no |  |
| `/Game/FX/Library/Environment/PNW/Atmospherics/Snow/NS_PNW_FallingTreeSnow_01` | NiagaraSystem | 0.07 |  |  | B40,C45 | no | snow variant |
| `/Game/FX/Library/Environment/PNW/Atmospherics/Snow/NS_PNW_SnowGusts_01` | NiagaraSystem | 0.15 |  |  | B40,C45 | no | snow variant |

*Group note:* Shipped Niagara; PWR uses NS_DustMotes_CameraAttached

### Creatures (PNW): birds, insects, fish, frogs (22)

*Where on PWR:* Birds over the valley, dragonflies/fireflies at the lakes, fish in the river

| path | kind | MB | verts | bounds m | levels | PWR | note |
|---|---|---|---|---|---|---|---|
| `/Game/FX/Library/Environment/PNW/Creatures/Birds/BP_BirdFlocks` | Blueprint | 0.01 |  |  | C10 | no |  |
| `/Game/FX/Library/Environment/PNW/Creatures/Birds/Gull/NS_GullFly` | NiagaraSystem | 0.04 |  |  | A30,B30,E20 | no | sibling used by PWR |
| `/Game/FX/Library/Environment/PNW/Creatures/Birds/Gull/NS_GullFlyCircle` | NiagaraSystem | 0.03 |  |  | A30,B30 | yes |  |
| `/Game/FX/Library/Environment/PNW/Creatures/Birds/NS_BirdFlock_Spline` | NiagaraSystem | 0.06 |  |  | C10 | no |  |
| `/Game/FX/Library/Environment/PNW/Creatures/Crab/Meshes/BP_Crab` | Blueprint | 0.00 |  |  | A15,A30,A50,B30,B40,C10,C20,C45,D20,D40,E10,E20,E30 | no | off-setting (tropical/alien/marine) [setting] |
| `/Game/FX/Library/Environment/PNW/Creatures/Crab/NS_CrabFlee` | NiagaraSystem | 0.09 |  |  | B30 | no | off-setting (tropical/alien/marine) [setting] |
| `/Game/FX/Library/Environment/PNW/Creatures/Crab/NS_PNW_Crab_01` | NiagaraSystem | 0.14 |  |  | B30 | no | off-setting (tropical/alien/marine) [setting] |
| `/Game/FX/Library/Environment/PNW/Creatures/Fish/FishOcean/BP_Creature_FishSplineBait` | Blueprint | 0.02 |  |  | B30 | no |  |
| `/Game/FX/Library/Environment/PNW/Creatures/Fish/FishOcean/NS_Creature_FishSplineBait` | NiagaraSystem | 0.06 |  |  | B30 | no |  |
| `/Game/FX/Library/Environment/PNW/Creatures/Fish/FishOcean/NS_Creature_FishTank_01` | NiagaraSystem | 0.03 |  |  | A30,B30 | no |  |
| `/Game/FX/Library/Environment/PNW/Creatures/Frog/NS_PNW_FrogsJumping` | NiagaraSystem | 0.06 |  |  | C10 | no |  |
| `/Game/FX/Library/Environment/PNW/Creatures/Insects/Butterfly/NS_Creature_ButterflySwarm_01` | NiagaraSystem | 0.04 |  |  | A30,B30 | yes |  |
| `/Game/FX/Library/Environment/PNW/Creatures/Insects/Dragonfly/NS_Creature_Dragonflies_01` | NiagaraSystem | 0.04 |  |  | A30,A50,B30,C10,E30 | no |  |
| `/Game/FX/Library/Environment/PNW/Creatures/Insects/FireFly/NS_Creature_Fireflies_01` | NiagaraSystem | 0.05 |  |  | A30,A50,C10,E30 | no |  |
| `/Game/FX/Library/Environment/PNW/Creatures/Insects/Flies/NS_Fly_Swarm` | NiagaraSystem | 0.04 |  |  | A30,B30,E20,E30 | no |  |
| `/Game/FX/Library/Environment/PNW/Creatures/Insects/Mosquitos/NS_Mosquito_Swarm_Wandering` | NiagaraSystem | 0.06 |  |  | A30,B30,C10,D20,E30 | no |  |
| `/Game/FX/Library/Environment/PNW/Creatures/Insects/Moth/NS_Creature_Moth` | NiagaraSystem | 0.04 |  |  | A30,A50,C10,D20,E20 | no |  |
| `/Game/FX/Library/Environment/PNW/Creatures/Insects/SandGnats/NS_PNW_SandGnats_01` | NiagaraSystem | 0.17 |  |  | A30,A50,B30,E20,E30 | no |  |
| `/Game/FX/Library/Environment/PNW/Creatures/Manta/NS_MantaDive` | NiagaraSystem | 0.23 |  |  | B30 | no | off-setting (tropical/alien/marine) [setting] |
| `/Game/FX/Library/Environment/PNW/Creatures/Manta/NS_MantaFly` | NiagaraSystem | 0.04 |  |  | B30 | no | off-setting (tropical/alien/marine) [setting] |
| `/Game/FX/Library/Environment/PNW/Creatures/SpiderLizard/NS_PNW_SpiderLizard` | NiagaraSystem | 0.12 |  |  | C10,E20 | no | off-setting (tropical/alien/marine) [setting] |
| `/Game/FX/Library/Environment/PNW/Creatures/SpiderLizard/NS_PNW_SpiderLizard_LimitedRadius` | NiagaraSystem | 0.13 |  |  | A50 | no | off-setting (tropical/alien/marine) [setting] |

*Group note:* Shipped Niagara creatures; PWR uses gulls and butterflies. Crab/manta/spider-lizard are off-setting

### Battlefield smoke columns (PNW Destruction) (15)

*Where on PWR:* Distant smoke columns over contested zones, vista smoke

| path | kind | MB | verts | bounds m | levels | PWR | note |
|---|---|---|---|---|---|---|---|
| `/Game/FX/Library/Environment/PNW/Destruction/Debris/NS_PNW_Debris_D40` | NiagaraSystem | 0.06 |  |  | D40 | no |  |
| `/Game/FX/Library/Environment/PNW/Destruction/Smoke/SmokeColumnDistance/NS_PNW_SmokeColumn_Vista_A30` | NiagaraSystem | 0.02 |  |  | A30 | no |  |
| `/Game/FX/Library/Environment/PNW/Destruction/Smoke/SmokeColumns/NS_PNW_SmokeColumn_Lrg_03` | NiagaraSystem | 0.10 |  |  | A30,D40 | no |  |
| `/Game/FX/Library/Environment/PNW/Destruction/Smoke/SmokeColumns/NS_PNW_SmokeColumn_Lrg_03b` | NiagaraSystem | 0.08 |  |  | A30,B30,C10,D40 | no |  |
| `/Game/FX/Library/Environment/PNW/Destruction/Smoke/SmokeColumns/NS_PNW_SmokeColumn_Lrg_04` | NiagaraSystem | 0.09 |  |  | D40 | no |  |
| `/Game/FX/Library/Environment/PNW/Destruction/Smoke/SmokeColumns/NS_PNW_SmokeColumn_Lrg_04_Wind` | NiagaraSystem | 0.11 |  |  | D40 | no |  |
| `/Game/FX/Library/Environment/PNW/Destruction/Smoke/SmokeColumns/NS_PNW_SmokeColumn_Med_01` | NiagaraSystem | 0.18 |  |  | A15,D40 | no |  |
| `/Game/FX/Library/Environment/PNW/Destruction/Smoke/SmokeColumns/NS_PNW_SmokeColumn_Med_02` | NiagaraSystem | 0.10 |  |  | B30,D40 | no |  |
| `/Game/FX/Library/Environment/PNW/Destruction/Smoke/SmokeColumns/NS_PNW_SmokeColumn_Med_03` | NiagaraSystem | 0.07 |  |  | A30,B30,D40 | no |  |
| `/Game/FX/Library/Environment/PNW/Destruction/Smoke/SmokeColumns/NS_PNW_SmokeColumn_Sml_01` | NiagaraSystem | 0.10 |  |  | D40 | no |  |
| `/Game/FX/Library/Environment/PNW/Destruction/Smoke/SmokeColumns/NS_PNW_SmokeColumn_Sml_02` | NiagaraSystem | 0.10 |  |  | B30 | no |  |
| `/Game/FX/Library/Environment/PNW/Destruction/Smoke/SmokeColumns/NS_PNW_SmokeColumn_Sml_03` | NiagaraSystem | 0.07 |  |  | A15,B30,D40 | no |  |
| `/Game/FX/Library/Environment/PNW/Destruction/Smoke/Transmissive/NS_PNW_SmokeColumn_Med_03` | NiagaraSystem | 0.07 |  |  | A30,B30,C10,D40 | no |  |
| `/Game/FX/Library/Environment/PNW/Destruction/Smoke/Transmissive/NS_PNW_SmokeColumn_Med_04` | NiagaraSystem | 0.05 |  |  | A30,B30,D40 | no |  |
| `/Game/FX/Library/Environment/PNW/Destruction/Smoke/Transmissive/NS_PNW_SmokeColumn_Vista` | NiagaraSystem | 0.04 |  |  | A30 | no |  |

*Group note:* Shipped Niagara

### Emissive and light-function materials (216)

*Where on PWR:* Glow strips on FR structures, light functions

| path | kind | MB | verts | bounds m | levels | PWR | note |
|---|---|---|---|---|---|---|---|
| `/Game/Lighting/EmissiveFillLight/BP_EmissiveFillLight` | Blueprint | 0.01 |  |  | A15,A30,A50,C10,D20,D40,E20 | no |  |
| `/Game/Lighting/EmissiveFillLight/M_EmissiveFill` | Material | 0.01 |  |  | A15,A30,A50,C10,D20,D40,E20 | no |  |
| `/Game/Lighting/EnvLensFlare/Assets/BP_DA_EnviroLensFlarePreset` | Blueprint | 0.00 |  |  | A15,A30,A50,B30,B40,C10,C20,C45,D20,D40,E10,E20,E30 | no |  |
| `/Game/Lighting/EnvLensFlare/Assets/BP_DA_LensFlarePresetMap` | Blueprint | 0.00 |  |  | A15,A30,A50,B30,B40,C10,C20,C45,D20,D40,E10,E20,E30 | no |  |
| `/Game/Lighting/EnvLensFlare/BPC_EnvLensFlare` | Blueprint | 0.03 |  |  | A15,A30,A50,B30,B40,C10,C20,C45,D20,D40,E10,E20,E30 | no |  |
| `/Game/Lighting/EnvLensFlare/BP_EnvLensFlare` | Blueprint | 0.00 |  |  | B40,C10,C20,C45,D20,D40 | no |  |
| `/Game/Lighting/EnvLensFlare/Materials/MI_LensFlare_1Layer` | MaterialInstance | 0.00 |  |  | A15,A30,A50,B30,B40,C10,C20,C45,D20,D40,E10,E20,E30 | no |  |
| `/Game/Lighting/EnvLensFlare/Materials/MI_LensFlare_2Layer` | MaterialInstance | 0.01 |  |  | A15,A30,A50,B30,B40,C10,C20,C45,D20,D40,E10,E20,E30 | no |  |
| `/Game/Lighting/EnvLensFlare/Materials/MI_LensFlare_3Layer` | MaterialInstance | 0.01 |  |  | A15,A30,A50,B30,B40,C10,C20,C45,D20,D40,E10,E20,E30 | no |  |
| `/Game/Lighting/EnvLensFlare/Materials/MI_LensFlare_4Layer` | MaterialInstance | 0.01 |  |  | A15,A30,A50,B30,B40,C10,C20,C45,D20,D40,E10,E20,E30 | no |  |
| `/Game/Lighting/EnvLensFlare/Materials/MI_LensFlare_5Layer` | MaterialInstance | 0.01 |  |  | A15,A30,A50,B30,B40,C10,C20,C45,D20,D40,E10,E20,E30 | no |  |
| `/Game/Lighting/EnvLensFlare/Materials/M_LensFlare` | Material | 0.01 |  |  | A15,A30,A50,B30,B40,C10,C20,C45,D20,D40,E10,E20,E30 | no |  |
| `/Game/Lighting/EnvLensFlare/Materials/M_PurpleDebug` | Material | 0.01 |  |  | A15,A30,A50,B30,B40,C10,C20,C45,D20,D40,E10,E20,E30 | no |  |
| `/Game/Lighting/Lighting_Mats/EmissiveMaterials/B40/MI_FREmissive_Solid_B40_Blue` | MaterialInstance | 0.01 |  |  | C45 | yes |  |
| `/Game/Lighting/Lighting_Mats/EmissiveMaterials/B40/MI_FREmissive_Solid_B40_Blue_Dark` | MaterialInstance | 0.01 |  |  | B40,C45 | no | sibling used by PWR |
| `/Game/Lighting/Lighting_Mats/EmissiveMaterials/B40/MI_FREmissive_Solid_B40_Blue_Light` | MaterialInstance | 0.01 |  |  | B40 | no | sibling used by PWR |
| `/Game/Lighting/Lighting_Mats/EmissiveMaterials/B40/MI_FREmissive_Solid_B40_Orange` | MaterialInstance | 0.03 |  |  | B40 | no | sibling used by PWR |
| `/Game/Lighting/Lighting_Mats/EmissiveMaterials/B40/MI_FREmissive_Solid_B40_White_Cold` | MaterialInstance | 0.03 |  |  | B40,C45 | no | sibling used by PWR |
| `/Game/Lighting/Lighting_Mats/EmissiveMaterials/B40/MI_FREmissive_Solid_B40_White_Small` | MaterialInstance | 0.03 |  |  | B40,C45 | no | sibling used by PWR |
| `/Game/Lighting/Lighting_Mats/EmissiveMaterials/B40/MI_FREmissive_Solid_B40_White_Small2` | MaterialInstance | 0.03 |  |  | B40,C45 | no | sibling used by PWR |
| `/Game/Lighting/Lighting_Mats/EmissiveMaterials/B40/MI_FREmissive_Solid_B40_White_Warm` | MaterialInstance | 0.01 |  |  | C45 | no | sibling used by PWR |
| `/Game/Lighting/Lighting_Mats/EmissiveMaterials/C20/MI_FREmissive_Solid_White_Dim_C20` | MaterialInstance | 0.00 |  |  |  | no |  |
| `/Game/Lighting/Lighting_Mats/EmissiveMaterials/C20/MI_FREmissive_Solid__Warm_Dim_Small_C20` | MaterialInstance | 0.00 |  |  |  | no |  |
| `/Game/Lighting/Lighting_Mats/EmissiveMaterials/C45/MI_FR_Bump_Emissive_Gen_Blue_Small_Bright1_02` | MaterialInstance | 0.00 |  |  | B40,C45 | no |  |
| `/Game/Lighting/Lighting_Mats/EmissiveMaterials/C45/MI_FR_Bump_Emissive_Mural_White_Lrg_c45_02` | MaterialInstance | 0.03 |  |  | C45 | no |  |
| `/Game/Lighting/Lighting_Mats/EmissiveMaterials/M_FR_Bump_Emissive` | Material | 0.03 |  |  | A15,A30,A50,B30,B40,C10,C20,C45,D20,D40,E10,E20,E30 | no |  |
| `/Game/Lighting/Lighting_Mats/EmissiveMaterials/MaterialInstances/FR_Bump_Emissive/C10_Massive_WallFixtures/MI_FREmissive_Solid_Teal_Small_2` | MaterialInstance | 0.00 |  |  | C10 | no |  |
| `/Game/Lighting/Lighting_Mats/EmissiveMaterials/MaterialInstances/FR_Bump_Emissive/C10_Massive_WallFixtures/MI_FREmissive_Solid_Teal_Small_Inst` | MaterialInstance | 0.00 |  |  | C10 | no |  |
| `/Game/Lighting/Lighting_Mats/EmissiveMaterials/MaterialInstances/FR_Bump_Emissive/MI_FREmissive_Solid_Cold_Dim_Small` | MaterialInstance | 0.02 |  |  | A30,B30 | no |  |
| `/Game/Lighting/Lighting_Mats/EmissiveMaterials/MaterialInstances/FR_Bump_Emissive/MI_FREmissive_Solid_Cold_Large` | MaterialInstance | 0.00 |  |  | A15,B30 | no |  |
| `/Game/Lighting/Lighting_Mats/EmissiveMaterials/MaterialInstances/FR_Bump_Emissive/MI_FREmissive_Solid_Cold_Large_Bright` | MaterialInstance | 0.01 |  |  | B30 | no |  |
| `/Game/Lighting/Lighting_Mats/EmissiveMaterials/MaterialInstances/FR_Bump_Emissive/MI_FREmissive_Solid_Cold_Small` | MaterialInstance | 0.02 |  |  | A30,B30,C45,D40 | no |  |
| `/Game/Lighting/Lighting_Mats/EmissiveMaterials/MaterialInstances/FR_Bump_Emissive/MI_FREmissive_Solid_Cool_EvenMoreBright` | MaterialInstance | 0.01 |  |  | B30 | no |  |
| `/Game/Lighting/Lighting_Mats/EmissiveMaterials/MaterialInstances/FR_Bump_Emissive/MI_FREmissive_Solid_Green` | MaterialInstance | 0.00 |  |  | B30,D40 | no |  |
| `/Game/Lighting/Lighting_Mats/EmissiveMaterials/MaterialInstances/FR_Bump_Emissive/MI_FREmissive_Solid_Green_Dim` | MaterialInstance | 0.00 |  |  | B30 | no |  |
| `/Game/Lighting/Lighting_Mats/EmissiveMaterials/MaterialInstances/FR_Bump_Emissive/MI_FREmissive_Solid_Green_MoreDim_Small` | MaterialInstance | 0.00 |  |  | B30 | no |  |
| `/Game/Lighting/Lighting_Mats/EmissiveMaterials/MaterialInstances/FR_Bump_Emissive/MI_FREmissive_Solid_LessCold` | MaterialInstance | 0.02 |  |  | A30,B30,B40,C45 | no |  |
| `/Game/Lighting/Lighting_Mats/EmissiveMaterials/MaterialInstances/FR_Bump_Emissive/MI_FREmissive_Solid_LessCold_Dim_Small` | MaterialInstance | 0.02 |  |  | B30 | no |  |
| `/Game/Lighting/Lighting_Mats/EmissiveMaterials/MaterialInstances/FR_Bump_Emissive/MI_FREmissive_Solid_LessCold_MoreDim_Small` | MaterialInstance | 0.02 |  |  | A30,B30 | no |  |
| `/Game/Lighting/Lighting_Mats/EmissiveMaterials/MaterialInstances/FR_Bump_Emissive/MI_FREmissive_Solid_MoreGreen` | MaterialInstance | 0.02 |  |  | B30 | no |  |
| `/Game/Lighting/Lighting_Mats/EmissiveMaterials/MaterialInstances/FR_Bump_Emissive/MI_FREmissive_Solid_MoreGreen_Small` | MaterialInstance | 0.02 |  |  | B30 | no |  |
| `/Game/Lighting/Lighting_Mats/EmissiveMaterials/MaterialInstances/FR_Bump_Emissive/MI_FREmissive_Solid_Neutral_Dim_Small` | MaterialInstance | 0.02 |  |  | A30,B30 | no |  |
| `/Game/Lighting/Lighting_Mats/EmissiveMaterials/MaterialInstances/FR_Bump_Emissive/MI_FREmissive_Solid_Neutral_Dimmer` | MaterialInstance | 0.02 |  |  | A30 | no |  |
| `/Game/Lighting/Lighting_Mats/EmissiveMaterials/MaterialInstances/FR_Bump_Emissive/MI_FREmissive_Solid_Neutral_Small` | MaterialInstance | 0.02 |  |  | B30 | no |  |
| `/Game/Lighting/Lighting_Mats/EmissiveMaterials/MaterialInstances/FR_Bump_Emissive/MI_FREmissive_Solid_Neutral_Very_Dim` | MaterialInstance | 0.02 |  |  | A30 | no |  |
| `/Game/Lighting/Lighting_Mats/EmissiveMaterials/MaterialInstances/FR_Bump_Emissive/MI_FREmissive_Solid_Purple_Dim` | MaterialInstance | 0.01 |  |  | A30,B30 | no |  |
| `/Game/Lighting/Lighting_Mats/EmissiveMaterials/MaterialInstances/FR_Bump_Emissive/MI_FREmissive_Solid_Purple_MoreDim` | MaterialInstance | 0.01 |  |  | B30 | no |  |
| `/Game/Lighting/Lighting_Mats/EmissiveMaterials/MaterialInstances/FR_Bump_Emissive/MI_FREmissive_Solid_Teal_Dim_Small` | MaterialInstance | 0.01 |  |  | A30,B30,B40,C20,C45 | no |  |
| `/Game/Lighting/Lighting_Mats/EmissiveMaterials/MaterialInstances/FR_Bump_Emissive/MI_FREmissive_Solid_Teal_Small` | MaterialInstance | 0.01 |  |  | A15,A30,A50,B30,B40,C10,C20,C45,D20,D40,E10,E20,E30 | no |  |
| `/Game/Lighting/Lighting_Mats/EmissiveMaterials/MaterialInstances/FR_Bump_Emissive/MI_FREmissive_Solid_Warm` | MaterialInstance | 0.02 |  |  | A15,A30,B30,B40 | no |  |
| `/Game/Lighting/Lighting_Mats/EmissiveMaterials/MaterialInstances/FR_Bump_Emissive/MI_FREmissive_Solid_Warm_Bright` | MaterialInstance | 0.01 |  |  | A30,B30,B40 | no |  |
| `/Game/Lighting/Lighting_Mats/EmissiveMaterials/MaterialInstances/FR_Bump_Emissive/MI_FREmissive_Solid_Warm_EvenMoreBright` | MaterialInstance | 0.01 |  |  | B30 | no |  |
| `/Game/Lighting/Lighting_Mats/EmissiveMaterials/MaterialInstances/FR_Bump_Emissive/MI_FREmissive_Solid_White` | MaterialInstance | 0.02 |  |  | B30 | no |  |
| `/Game/Lighting/Lighting_Mats/EmissiveMaterials/MaterialInstances/FR_Bump_Emissive/MI_FREmissive_Solid_WhiteGreen_Small` | MaterialInstance | 0.02 |  |  | B30 | no |  |
| `/Game/Lighting/Lighting_Mats/EmissiveMaterials/MaterialInstances/FR_Bump_Emissive/MI_FREmissive_Solid_White_Dim` | MaterialInstance | 0.02 |  |  |  | no |  |
| `/Game/Lighting/Lighting_Mats/EmissiveMaterials/MaterialInstances/FR_Bump_Emissive/MI_FREmissive_Solid_White_Dim_Small` | MaterialInstance | 0.02 |  |  | A30,B30 | no |  |
| `/Game/Lighting/Lighting_Mats/EmissiveMaterials/MaterialInstances/FR_Bump_Emissive/MI_FREmissive_Solid_White_LessDim_Small` | MaterialInstance | 0.02 |  |  | B30 | no |  |
| `/Game/Lighting/Lighting_Mats/EmissiveMaterials/MaterialInstances/FR_Bump_Emissive/MI_FREmissive_Solid_White_Small` | MaterialInstance | 0.01 |  |  | A30,B30,C45 | no |  |
| `/Game/Lighting/Lighting_Mats/EmissiveMaterials/MaterialInstances/FR_Bump_Emissive/MI_FREmissive_Solid__Warm_Dim_Small` | MaterialInstance | 0.02 |  |  | B30 | no |  |
| `/Game/Lighting/Lighting_Mats/EmissiveMaterials/MaterialInstances/FR_Bump_Emissive/MI_FR_Bump_Emissive_Gen_Blue_Green_Dimmer_Small` | MaterialInstance | 0.00 |  |  | B30,C10 | no |  |
| `/Game/Lighting/Lighting_Mats/EmissiveMaterials/MaterialInstances/FR_Bump_Emissive/MI_FR_Bump_Emissive_Gen_Blue_Small_B` | MaterialInstance | 0.03 |  |  | A30,B30,B40,C10,C45 | no |  |
| `/Game/Lighting/Lighting_Mats/EmissiveMaterials/MaterialInstances/FR_Bump_Emissive/MI_FR_Bump_Emissive_Gen_Blue_Small_B_Green` | MaterialInstance | 0.00 |  |  | B30,C10 | no |  |
| `/Game/Lighting/Lighting_Mats/EmissiveMaterials/MaterialInstances/FR_Bump_Emissive/MI_FR_Bump_Emissive_Gen_Blue_Small_B_Purple_Dim_Small` | MaterialInstance | 0.00 |  |  | C10 | no |  |
| `/Game/Lighting/Lighting_Mats/EmissiveMaterials/MaterialInstances/FR_Bump_Emissive/MI_FR_Bump_Emissive_Gen_Blue_Small_B_Warm` | MaterialInstance | 0.00 |  |  | B30 | no |  |
| `/Game/Lighting/Lighting_Mats/EmissiveMaterials/MaterialInstances/FR_Bump_Emissive/MI_FR_Bump_Emissive_Gen_Blue_Small_B_Warm_Dim` | MaterialInstance | 0.00 |  |  | B30 | no |  |
| `/Game/Lighting/Lighting_Mats/EmissiveMaterials/MaterialInstances/FR_Bump_Emissive/MI_FR_Bump_Emissive_Gen_Blue_Small_Bright` | MaterialInstance | 0.00 |  |  | B30 | no |  |
| `/Game/Lighting/Lighting_Mats/EmissiveMaterials/MaterialInstances/FR_Bump_Emissive/MI_FR_Bump_Emissive_Gen_Blue_Small_VeryBright` | MaterialInstance | 0.00 |  |  | B30 | no |  |
| `/Game/Lighting/Lighting_Mats/EmissiveMaterials/MaterialInstances/FR_Bump_Emissive/MI_FR_Bump_Emissive_Gen_Green_Small_Dim` | MaterialInstance | 0.03 |  |  | A30,C10 | no |  |
| `/Game/Lighting/Lighting_Mats/EmissiveMaterials/MaterialInstances/FR_Bump_Emissive/MI_FR_Bump_Emissive_Gen_Med_Green_Bright` | MaterialInstance | 0.03 |  |  | C10 | no |  |
| `/Game/Lighting/Lighting_Mats/EmissiveMaterials/MaterialInstances/FR_Bump_Emissive/MI_FR_Bump_Emissive_Gen_Med_Trap` | MaterialInstance | 0.03 |  |  | A30 | no |  |
| `/Game/Lighting/Lighting_Mats/EmissiveMaterials/MaterialInstances/FR_Bump_Emissive/MI_FR_Bump_Emissive_Gen_Med_Trap_A30` | MaterialInstance | 0.03 |  |  | A30 | no |  |
| `/Game/Lighting/Lighting_Mats/EmissiveMaterials/MaterialInstances/FR_Bump_Emissive/MI_FR_Bump_Emissive_Gen_Med_Trap_B30` | MaterialInstance | 0.03 |  |  | A30,B30,B40,C10,C20,C45 | no |  |
| `/Game/Lighting/Lighting_Mats/EmissiveMaterials/MaterialInstances/FR_Bump_Emissive/MI_FR_Bump_Emissive_Gen_Med_Trap_B30_Bright` | MaterialInstance | 0.00 |  |  | A30,B30,B40,C10,C20,C45 | no |  |
| `/Game/Lighting/Lighting_Mats/EmissiveMaterials/MaterialInstances/FR_Bump_Emissive/MI_FR_Bump_Emissive_Gen_Med_Trap_B30_Bright_Solid` | MaterialInstance | 0.01 |  |  | A30,B30,B40,C10,C20,C45 | no |  |
| `/Game/Lighting/Lighting_Mats/EmissiveMaterials/MaterialInstances/FR_Bump_Emissive/MI_FR_Bump_Emissive_Gen_Med_Trap_B30_Dim` | MaterialInstance | 0.00 |  |  | B30 | no |  |
| `/Game/Lighting/Lighting_Mats/EmissiveMaterials/MaterialInstances/FR_Bump_Emissive/MI_FR_Bump_Emissive_Gen_Med_Trap_B30_Exterior` | MaterialInstance | 0.00 |  |  | B30 | no |  |
| `/Game/Lighting/Lighting_Mats/EmissiveMaterials/MaterialInstances/FR_Bump_Emissive/MI_FR_Bump_Emissive_Gen_Med_Trap_B30_Warm` | MaterialInstance | 0.03 |  |  | B30 | no |  |
| `/Game/Lighting/Lighting_Mats/EmissiveMaterials/MaterialInstances/FR_Bump_Emissive/MI_FR_Bump_Emissive_Gen_Med_Trap_B30_Warm_Bright` | MaterialInstance | 0.03 |  |  | B30 | no |  |
| `/Game/Lighting/Lighting_Mats/EmissiveMaterials/MaterialInstances/FR_Bump_Emissive/MI_FR_Bump_Emissive_Mural_Blue_Lrg1` | MaterialInstance | 0.03 |  |  | A30 | no |  |
| `/Game/Lighting/Lighting_Mats/EmissiveMaterials/MaterialInstances/FR_Bump_Emissive/MI_FR_Bump_Emissive_Mural_White_Lrg` | MaterialInstance | 0.03 |  |  | B30 | no |  |
| `/Game/Lighting/Lighting_Mats/EmissiveMaterials/MaterialInstances/FR_Bump_Emissive/MI_FR_Bump_Emissive_Mural_White_Lrg_VeryBright` | MaterialInstance | 0.00 |  |  | B30 | no |  |
| `/Game/Lighting/Lighting_Mats/EmissiveMaterials/MaterialInstances/FR_Bump_Emissive/MI_FR_Clover_Blue_Exterior` | MaterialInstance | 0.03 |  |  | B30 | no |  |
| `/Game/Lighting/Lighting_Mats/EmissiveMaterials/MaterialInstances/FR_Bump_Emissive/MI_FR_Corner_Blue` | MaterialInstance | 0.03 |  |  | A30,B30,C10,C20 | no |  |
| `/Game/Lighting/Lighting_Mats/EmissiveMaterials/MaterialInstances/FR_Bump_Emissive/MI_FR_Corner_Blue_Exterior` | MaterialInstance | 0.03 |  |  | B30 | no |  |
| `/Game/Lighting/Lighting_Mats/EmissiveMaterials/MaterialInstances/FR_Bump_Emissive/MI_FR_Corner_Blue_Sat` | MaterialInstance | 0.03 |  |  | A30 | no |  |
| `/Game/Lighting/Lighting_Mats/EmissiveMaterials/MaterialInstances/FR_Bump_Emissive/MI_FR_Corner_White` | MaterialInstance | 0.00 |  |  | B30,C10 | no |  |
| `/Game/Lighting/Lighting_Mats/EmissiveMaterials/MaterialInstances/FR_Bump_Emissive/MI_FR_Corner_White_Bright` | MaterialInstance | 0.00 |  |  | B30 | no |  |
| `/Game/Lighting/Lighting_Mats/EmissiveMaterials/MaterialInstances/FR_Bump_Emissive/MI_FR_Corner_White_Dim` | MaterialInstance | 0.00 |  |  | B30 | no |  |
| `/Game/Lighting/Lighting_Mats/EmissiveMaterials/MaterialInstances/FR_Bump_Emissive/MI_FR_Corner_White_MoreBright` | MaterialInstance | 0.00 |  |  | B30 | no |  |
| `/Game/Lighting/Lighting_Mats/EmissiveMaterials/MaterialInstances/FR_Bump_Emissive/MI_FR_Emissive_Solid_Arrow` | MaterialInstance | 0.01 |  |  | C45 | no |  |
| `/Game/Lighting/Lighting_Mats/EmissiveMaterials/MaterialInstances/FR_Bump_Emissive/MI_FR_Fixture_01` | MaterialInstance | 0.03 |  |  | B30 | no |  |
| `/Game/Lighting/Lighting_Mats/EmissiveMaterials/MaterialInstances/FR_Bump_Emissive/MI_FR_Fixture_02` | MaterialInstance | 0.03 |  |  | B30 | no |  |
| `/Game/Lighting/Lighting_Mats/EmissiveMaterials/MaterialInstances/FR_Bump_Emissive/MI_FR_Fixture_02_White_MoreDim_Small` | MaterialInstance | 0.03 |  |  | C10 | no |  |
| `/Game/Lighting/Lighting_Mats/EmissiveMaterials/MaterialInstances/FR_Bump_Emissive/MI_FR_Fixture_03` | MaterialInstance | 0.03 |  |  | A30,B30,C10,C45 | no |  |
| `/Game/Lighting/Lighting_Mats/EmissiveMaterials/MaterialInstances/FR_Bump_Emissive/MI_FR_Fixture_03_Blue_Dim_Small` | MaterialInstance | 0.03 |  |  | C10 | no |  |
| `/Game/Lighting/Lighting_Mats/EmissiveMaterials/MaterialInstances/FR_Bump_Emissive/MI_FR_Fixture_03_Blue_Dim_Small_nomask` | MaterialInstance | 0.03 |  |  | A30 | no |  |
| `/Game/Lighting/Lighting_Mats/EmissiveMaterials/MaterialInstances/FR_Bump_Emissive/MI_FR_Fixture_03_Bright_Blue` | MaterialInstance | 0.00 |  |  | B30 | no |  |
| `/Game/Lighting/Lighting_Mats/EmissiveMaterials/MaterialInstances/FR_Bump_Emissive/MI_FR_Fixture_03_Cold` | MaterialInstance | 0.00 |  |  | B30,C45 | no |  |
| `/Game/Lighting/Lighting_Mats/EmissiveMaterials/MaterialInstances/FR_Bump_Emissive/MI_FR_Fixture_03_Dim` | MaterialInstance | 0.03 |  |  | C10 | no |  |
| `/Game/Lighting/Lighting_Mats/EmissiveMaterials/MaterialInstances/FR_Bump_Emissive/MI_FR_Fixture_03_Dim_Cold` | MaterialInstance | 0.03 |  |  | C10 | no |  |
| `/Game/Lighting/Lighting_Mats/EmissiveMaterials/MaterialInstances/FR_Bump_Emissive/MI_FR_Fixture_03_Dim_Cold_Small` | MaterialInstance | 0.03 |  |  | B30,C10 | no |  |
| `/Game/Lighting/Lighting_Mats/EmissiveMaterials/MaterialInstances/FR_Bump_Emissive/MI_FR_Fixture_03_Dim_Small` | MaterialInstance | 0.03 |  |  | C10 | no |  |
| `/Game/Lighting/Lighting_Mats/EmissiveMaterials/MaterialInstances/FR_Bump_Emissive/MI_FR_Fixture_03_LessBright_Cold` | MaterialInstance | 0.00 |  |  | B30 | no |  |
| `/Game/Lighting/Lighting_Mats/EmissiveMaterials/MaterialInstances/FR_Bump_Emissive/MI_FR_Fixture_03_LessDim` | MaterialInstance | 0.03 |  |  | C10 | no |  |
| `/Game/Lighting/Lighting_Mats/EmissiveMaterials/MaterialInstances/FR_Bump_Emissive/MI_FR_Fixture_03_LessDim_Cold` | MaterialInstance | 0.03 |  |  | A30,B30,C10 | no |  |
| `/Game/Lighting/Lighting_Mats/EmissiveMaterials/MaterialInstances/FR_Bump_Emissive/MI_FR_Fixture_03_LessDim_Cold_Small` | MaterialInstance | 0.03 |  |  | A30,B30 | no |  |
| `/Game/Lighting/Lighting_Mats/EmissiveMaterials/MaterialInstances/FR_Bump_Emissive/MI_FR_Fixture_03_LessDim_White` | MaterialInstance | 0.03 |  |  | B30 | no |  |
| `/Game/Lighting/Lighting_Mats/EmissiveMaterials/MaterialInstances/FR_Bump_Emissive/MI_FR_Fixture_03_MidBright` | MaterialInstance | 0.00 |  |  | B30 | no |  |
| `/Game/Lighting/Lighting_Mats/EmissiveMaterials/MaterialInstances/FR_Bump_Emissive/MI_FR_Fixture_03_MidBright_Blue` | MaterialInstance | 0.00 |  |  | A30,B30 | no |  |
| `/Game/Lighting/Lighting_Mats/EmissiveMaterials/MaterialInstances/FR_Bump_Emissive/MI_FR_Fixture_03_MidBright_Cold` | MaterialInstance | 0.00 |  |  | A30,B30 | no |  |
| `/Game/Lighting/Lighting_Mats/EmissiveMaterials/MaterialInstances/FR_Bump_Emissive/MI_FR_Fixture_03_MoreBright_Cold` | MaterialInstance | 0.00 |  |  | B30 | no |  |
| `/Game/Lighting/Lighting_Mats/EmissiveMaterials/MaterialInstances/FR_Bump_Emissive/MI_FR_Fixture_03_Small` | MaterialInstance | 0.03 |  |  | B30 | no |  |
| `/Game/Lighting/Lighting_Mats/EmissiveMaterials/MaterialInstances/FR_Bump_Emissive/MI_FR_Fixture_03_White_Purple_Dim_Small` | MaterialInstance | 0.03 |  |  | C10 | no |  |
| `/Game/Lighting/Lighting_Mats/EmissiveMaterials/MaterialInstances/FR_Bump_Emissive/MI_FR_Fixture_03_white_Dim_Small_nomask1` | MaterialInstance | 0.03 |  |  | A30 | no |  |
| `/Game/Lighting/Lighting_Mats/EmissiveMaterials/MaterialInstances/FR_Bump_Emissive/MI_FR_Fixture_04` | MaterialInstance | 0.03 |  |  | B30,C10 | no |  |
| `/Game/Lighting/Lighting_Mats/EmissiveMaterials/MaterialInstances/FR_Bump_Emissive/MI_FR_Fixture_04_Blue_Exterior` | MaterialInstance | 0.00 |  |  | A30 | no |  |
| `/Game/Lighting/Lighting_Mats/EmissiveMaterials/MaterialInstances/FR_Bump_Emissive/MI_FR_Fixture_04_Bright_Blue` | MaterialInstance | 0.00 |  |  | B30 | no |  |
| `/Game/Lighting/Lighting_Mats/EmissiveMaterials/MaterialInstances/FR_Bump_Emissive/MI_FR_Fixture_04_Dim_Blue_Exterior` | MaterialInstance | 0.00 |  |  | B30 | no |  |
| `/Game/Lighting/Lighting_Mats/EmissiveMaterials/MaterialInstances/FR_Bump_Emissive/MI_FR_Fixture_04_Dim_Cold_Small` | MaterialInstance | 0.03 |  |  | B30 | no |  |
| `/Game/Lighting/Lighting_Mats/EmissiveMaterials/MaterialInstances/FR_Bump_Emissive/MI_FR_Fixture_05` | MaterialInstance | 0.03 |  |  | B30 | no |  |
| `/Game/Lighting/Lighting_Mats/EmissiveMaterials/MaterialInstances/FR_Bump_Emissive/MI_FR_Fixture_06_Blue_Exterior` | MaterialInstance | 0.03 |  |  | B30 | no |  |
| `/Game/Lighting/Lighting_Mats/EmissiveMaterials/MaterialInstances/FR_Bump_Emissive/MI_FR_Fixture_07` | MaterialInstance | 0.03 |  |  | B30 | no |  |
| `/Game/Lighting/Lighting_Mats/EmissiveMaterials/MaterialInstances/FR_Bump_Emissive/MI_FR_Fixture_07_Dim` | MaterialInstance | 0.00 |  |  | B30 | no |  |
| `/Game/Lighting/Lighting_Mats/EmissiveMaterials/MaterialInstances/FR_Bump_Emissive/MI_FR_Fixture_A30` | MaterialInstance | 0.03 |  |  | A30 | no |  |
| `/Game/Lighting/Lighting_Mats/EmissiveMaterials/MaterialInstances/FR_Bump_Emissive/MI_FR_Fixture_A30_Cool_Dim_Small_nomask` | MaterialInstance | 0.02 |  |  | A30 | no |  |
| `/Game/Lighting/Lighting_Mats/EmissiveMaterials/MaterialInstances/FR_Bump_Emissive/MI_FR_Fixture_A30_Purple_Dim_Small_nomask` | MaterialInstance | 0.03 |  |  | A30 | no |  |
| `/Game/Lighting/Lighting_Mats/EmissiveMaterials/MaterialInstances/FR_Bump_Emissive/MI_FR_Fixture_A30_Purple_ExtraDim_Small_nomask1` | MaterialInstance | 0.03 |  |  | A30 | no |  |
| `/Game/Lighting/Lighting_Mats/EmissiveMaterials/MaterialInstances/FR_Bump_Emissive/MI_FR_Fixture_B_Bright_Blue_Exterior` | MaterialInstance | 0.00 |  |  | B30 | no |  |
| `/Game/Lighting/Lighting_Mats/EmissiveMaterials/MaterialInstances/FR_Bump_Emissive/MI_FR_Fixture_Blue_Exterior` | MaterialInstance | 0.03 |  |  | B30 | no |  |
| `/Game/Lighting/Lighting_Mats/EmissiveMaterials/MaterialInstances/FR_Bump_Emissive/MI_FR_Fixture_C_Bright_Blue` | MaterialInstance | 0.00 |  |  | B30 | no |  |
| `/Game/Lighting/Lighting_Mats/EmissiveMaterials/MaterialInstances/FR_Bump_Emissive/MI_FR_Fixture_E_Bright_Blue` | MaterialInstance | 0.00 |  |  | B30 | no |  |
| `/Game/Lighting/Lighting_Mats/EmissiveMaterials/MaterialInstances/FR_Bump_Emissive/MI_FR_Fixture_Long_Dash_Dim_Blue` | MaterialInstance | 0.03 |  |  | A30 | no |  |
| `/Game/Lighting/Lighting_Mats/EmissiveMaterials/MaterialInstances/FR_Bump_Emissive/MI_FR_Fixture_Purple_08` | MaterialInstance | 0.03 |  |  | A30 | no |  |
| `/Game/Lighting/Lighting_Mats/EmissiveMaterials/MaterialInstances/FR_Bump_Emissive/MI_FR_Fixture_Stripes_Blue_Exterior` | MaterialInstance | 0.03 |  |  | B30 | no |  |
| `/Game/Lighting/Lighting_Mats/EmissiveMaterials/MaterialInstances/FR_Bump_Emissive/MaskA_CornerClaw/MI_FR_Emissive_CornerClaw_Green_25Base` | MaterialInstance | 0.00 |  |  | C20 | no |  |
| `/Game/Lighting/Lighting_Mats/EmissiveMaterials/MaterialInstances/FR_Bump_Emissive/MaskA_RectBevel/MI_FR_Emissive_BevelRect_B30_White_Dim_50IN` | MaterialInstance | 0.03 |  |  | B30 | no |  |
| `/Game/Lighting/Lighting_Mats/EmissiveMaterials/MaterialInstances/FR_Bump_Emissive/MaskA_RectBevel/MI_FR_Emissive_BevelRect_Blue_Dim_100IN` | MaterialInstance | 0.03 |  |  | B30,C10 | no |  |
| `/Game/Lighting/Lighting_Mats/EmissiveMaterials/MaterialInstances/FR_Bump_Emissive/MaskA_RectBevel/MI_FR_Emissive_BevelRect_Blue_Dim_25IN` | MaterialInstance | 0.03 |  |  | C10 | no |  |
| `/Game/Lighting/Lighting_Mats/EmissiveMaterials/MaterialInstances/FR_Bump_Emissive/MaskA_RectBevel/MI_FR_Emissive_BevelRect_Blue_Dim_30Base` | MaterialInstance | 0.03 |  |  | C10 | no |  |
| `/Game/Lighting/Lighting_Mats/EmissiveMaterials/MaterialInstances/FR_Bump_Emissive/MaskA_RectBevel/MI_FR_Emissive_BevelRect_Blue_Dim_Base50_IN10` | MaterialInstance | 0.03 |  |  | C10 | no |  |
| `/Game/Lighting/Lighting_Mats/EmissiveMaterials/MaterialInstances/FR_Bump_Emissive/MaskA_RectBevel/MI_FR_Emissive_BevelRect_Green_Dim_25ase` | MaterialInstance | 0.03 |  |  | C10 | no |  |
| `/Game/Lighting/Lighting_Mats/EmissiveMaterials/MaterialInstances/FR_Bump_Emissive/MaskA_RectBevel/MI_FR_Emissive_BevelRect_Green_Dim_50Base_5IN` | MaterialInstance | 0.03 |  |  | C10 | no |  |
| `/Game/Lighting/Lighting_Mats/EmissiveMaterials/MaterialInstances/FR_Bump_Emissive/MaskA_RectBevel/MI_FR_Emissive_BevelRect_Purple_Dim_100IN` | MaterialInstance | 0.03 |  |  | C10 | no |  |
| `/Game/Lighting/Lighting_Mats/EmissiveMaterials/MaterialInstances/FR_Bump_Emissive/MaskA_RectBevel/MI_FR_Emissive_BevelRect_Teal_Dim_100Base_IN5` | MaterialInstance | 0.03 |  |  | C10 | no |  |
| `/Game/Lighting/Lighting_Mats/EmissiveMaterials/MaterialInstances/FR_Bump_Emissive/MaskB_Visor/MI_FR_Emissive_Visor_Blue_Dim_100IN` | MaterialInstance | 0.00 |  |  | C10 | no |  |
| `/Game/Lighting/Lighting_Mats/EmissiveMaterials/MaterialInstances/FR_Bump_Emissive/MaskB_Visor/MI_FR_Emissive_Visor_Blue_Dim_50IN` | MaterialInstance | 0.00 |  |  | C10 | no |  |
| `/Game/Lighting/Lighting_Mats/EmissiveMaterials/MaterialInstances/FR_Bump_Emissive/MaskB_Visor/MI_FR_Emissive_Visor_Blue_Dim_Base50_IN5` | MaterialInstance | 0.00 |  |  | C10 | no |  |
| `/Game/Lighting/Lighting_Mats/EmissiveMaterials/MaterialInstances/FR_Bump_Emissive/MaskB_Visor/MI_FR_Emissive_Visor_Green_Dim_15Base` | MaterialInstance | 0.00 |  |  | C10 | no |  |
| `/Game/Lighting/Lighting_Mats/EmissiveMaterials/MaterialInstances/FR_Bump_Emissive/MaskB_Visor/MI_FR_Emissive_Visor_Green_Dim_25IN` | MaterialInstance | 0.00 |  |  | B30 | no |  |
| `/Game/Lighting/Lighting_Mats/EmissiveMaterials/MaterialInstances/FR_Bump_Emissive/MaskB_Visor/MI_FR_Emissive_Visor_Green_Dim_50IN` | MaterialInstance | 0.00 |  |  | C10 | no |  |
| `/Game/Lighting/Lighting_Mats/EmissiveMaterials/MaterialInstances/FR_Bump_Emissive/MaskB_Visor/MI_FR_Emissive_Visor_Green_Dim_Base50_IN6` | MaterialInstance | 0.00 |  |  | C10 | no |  |
| `/Game/Lighting/Lighting_Mats/EmissiveMaterials/MaterialInstances/FR_Bump_Emissive/MaskD_Bow/MI_FR_Emissive_Bow_Green_Dim_100IN` | MaterialInstance | 0.03 |  |  | C10 | no |  |
| `/Game/Lighting/Lighting_Mats/EmissiveMaterials/MaterialInstances/FR_Bump_Emissive/MaskF_3LeafClover/MI_FR_Emissive_Triangle_Blue_Dim_50Base_5IN` | MaterialInstance | 0.03 |  |  | C10 | no |  |
| `/Game/Lighting/Lighting_Mats/EmissiveMaterials/MaterialInstances/FR_Bump_Emissive/MaskF_3LeafClover/MI_FR_Emissive_Triangle_Green_Dim_50IN1` | MaterialInstance | 0.03 |  |  | C10 | no |  |
| `/Game/Lighting/Lighting_Mats/EmissiveMaterials/MaterialInstances/FR_Bump_Emissive/MaskG_3Stripes/MI_FR_Emissive_3Stripes_Blue_Dim_50Base_25IN` | MaterialInstance | 0.03 |  |  | C10 | no |  |
| `/Game/Lighting/Lighting_Mats/EmissiveMaterials/MaterialInstances/FR_Bump_Emissive/MaskG_3Stripes/MI_FR_Emissive_3Stripes_Green_Dim_50Base_IN1` | MaterialInstance | 0.03 |  |  | C10 | no |  |
| `/Game/Lighting/Lighting_Mats/EmissiveMaterials/MaterialInstances/FR_Bump_Emissive/MaskG_3Stripes/MI_FR_Emissive_3Stripes_Green_Dim_50IN` | MaterialInstance | 0.03 |  |  | C10 | no |  |
| `/Game/Lighting/Lighting_Mats/EmissiveMaterials/MaterialInstances/FR_Bump_Emissive/MaskG_CircleRitual/MI_FR_Emissive_CircleRitual_Blue_Dim_50IN` | MaterialInstance | 0.03 |  |  | B30 | no |  |
| `/Game/Lighting/Lighting_Mats/EmissiveMaterials/MaterialInstances/FR_Bump_Emissive/MaskP_Triangle/MI_FR_Emissive_Triangle_Blue_Dim_25Base_5IN1` | MaterialInstance | 0.03 |  |  | C10 | no |  |
| `/Game/Lighting/Lighting_Mats/EmissiveMaterials/MaterialInstances/FR_Bump_Emissive/MaskP_Triangle/MI_FR_Emissive_Triangle_Green_Dim_50IN` | MaterialInstance | 0.03 |  |  | C10 | no |  |
| `/Game/Lighting/Lighting_Mats/EmissiveMaterials/MaterialInstances/FR_Bump_Emissive/MaskR_TailLight/MI_FR_Emissive_TailLight_Blue_Dim_35Base_10IN` | MaterialInstance | 0.03 |  |  | C10 | no |  |
| `/Game/Lighting/Lighting_Mats/EmissiveMaterials/MaterialInstances/FR_Bump_Emissive/MaskR_TailLight/MI_FR_Emissive_TailLight_Blue_Dim_50Base_1IN` | MaterialInstance | 0.03 |  |  | C10 | no |  |
| `/Game/Lighting/Lighting_Mats/EmissiveMaterials/MaterialInstances/FR_Bump_Emissive/MaskR_TailLight/MI_FR_Emissive_TailLight_Blue_Dim_50IN` | MaterialInstance | 0.03 |  |  | C10 | no |  |
| `/Game/Lighting/Lighting_Mats/EmissiveMaterials/MaterialInstances/FR_Bump_Emissive/MaskR_TailLight/MI_FR_Emissive_TailLight_Green_Dim_50IN` | MaterialInstance | 0.03 |  |  | B30,C10 | no |  |
| `/Game/Lighting/Lighting_Mats/EmissiveMaterials/MaterialInstances/FR_Bump_Emissive/NoMask/MI_FR_Emissive_NoMask_Green_Dim_25Base` | MaterialInstance | 0.03 |  |  | C10,C20 | no |  |
| `/Game/Lighting/Lighting_Mats/EmissiveMaterials/MaterialInstances/FR_Bump_Emissive/NoMask/MI_FR_Emissive_NoMask_White_BendLight_Dim_25Base1` | MaterialInstance | 0.02 |  |  | C10 | no |  |
| `/Game/Lighting/Lighting_Mats/EmissiveMaterials/MaterialInstances/FR_Bump_Emissive/Square/MI_FR_Emissive_Sqaure_Blue_50IN` | MaterialInstance | 0.02 |  |  | B30 | no |  |
| `/Game/Lighting/Lighting_Mats/EmissiveMaterials/MaterialInstances/FR_Bump_Emissive/Square/MI_FR_Emissive_Sqaure_Blue_Base15_5` | MaterialInstance | 0.02 |  |  | C10 | no |  |
| `/Game/Lighting/Lighting_Mats/EmissiveMaterials/MaterialInstances/FR_Bump_Emissive/Square/MI_FR_Emissive_Sqaure_Blue_Base35_IN8` | MaterialInstance | 0.02 |  |  | C10 | no |  |
| `/Game/Lighting/Lighting_Mats/EmissiveMaterials/MaterialInstances/FR_Bump_Emissive/Square/MI_FR_Emissive_Sqaure_Blue_Base50_IN10` | MaterialInstance | 0.02 |  |  | C10 | no |  |
| `/Game/Lighting/Lighting_Mats/EmissiveMaterials/MaterialInstances/FR_Bump_Emissive/Square/MI_FR_Emissive_Sqaure_Blue_Base65_IN15` | MaterialInstance | 0.02 |  |  | C10 | no |  |
| `/Game/Lighting/Lighting_Mats/EmissiveMaterials/MaterialInstances/FR_Bump_Emissive/Square/MI_FR_Emissive_Sqaure_Green_25Base` | MaterialInstance | 0.02 |  |  | C10 | no |  |
| `/Game/Lighting/Lighting_Mats/EmissiveMaterials/MaterialInstances/FR_Bump_Emissive/Square/MI_FR_Emissive_Sqaure_Green_25Base_1IN` | MaterialInstance | 0.02 |  |  | C10 | no |  |
| `/Game/Lighting/Lighting_Mats/EmissiveMaterials/MaterialInstances/FR_Bump_Emissive/Square/MI_FR_Emissive_Sqaure_Green_50Base_In2` | MaterialInstance | 0.02 |  |  | C10 | no |  |
| `/Game/Lighting/Lighting_Mats/EmissiveMaterials/MaterialInstances/FR_Bump_Emissive/Square/MI_FR_Emissive_Sqaure_White_50IN` | MaterialInstance | 0.02 |  |  | B30 | no |  |
| `/Game/Lighting/Lighting_Mats/FixtureMaterials/FR_Instances/MI_FR_Bump_Emissive_Primitive_Default` | MaterialInstance | 0.03 |  |  | A15,A30,A50,B30,B40,C10,C20,C45,D20,D40,E10,E20,E30 | no |  |
| `/Game/Lighting/Lighting_Mats/FixtureMaterials/FR_Instances/MI_FR_Bump_Emissive_Primitive_Projected` | MaterialInstance | 0.03 |  |  | A15,A30,A50,B30,B40,C10,C20,C45,D20,D40,E10,E20,E30 | no |  |
| `/Game/Lighting/Lighting_Mats/FixtureMaterials/FR_Instances/MI_FR_Bump_Emissive_Primitive_Projected_TwoSided` | MaterialInstance | 0.03 |  |  | A15,A30,A50,B30,B40,C10,C20,C45,D20,D40,E10,E20,E30 | no |  |
| `/Game/Lighting/Lighting_Mats/FixtureMaterials/FR_Instances/MI_FR_Bump_Emissive_Primitive_TwoSided` | MaterialInstance | 0.03 |  |  | A15,A30,A50,B30,B40,C10,C20,C45,D20,D40,E10,E20,E30 | no |  |
| `/Game/Lighting/Lighting_Mats/FixtureMaterials/M_FR_Bump_Emissive_Primitive` | Material | 0.03 |  |  | A15,A30,A50,B30,B40,C10,C20,C45,D20,D40,E10,E20,E30 | no |  |
| `/Game/Lighting/Lighting_Mats/Instances/Forerunner/C10/MI_FR_Bump_Emissive_C10` | MaterialInstance | 0.00 |  |  | C10 | no |  |
| `/Game/Lighting/Lighting_Mats/Instances/Forerunner/C10/MI_FR_Bump_Emissive_C10_BrighterKey` | MaterialInstance | 0.00 |  |  | C10 | no |  |
| `/Game/Lighting/Lighting_Mats/Instances/Forerunner/C10/MI_FR_Bump_Emissive_FloorSymbol` | MaterialInstance | 0.03 |  |  | C10 | no |  |
| `/Game/Lighting/Lighting_Mats/Instances/Forerunner/C10/MI_FR_Bump_Emissive_Gen_Blue_Small_C10_Key` | MaterialInstance | 0.03 |  |  | C10 | no |  |
| `/Game/Lighting/Lighting_Mats/Instances/Forerunner/C10/MI_FR_Bump_Emissive_Hallways_C10` | MaterialInstance | 0.00 |  |  | C10 | no |  |
| `/Game/Lighting/Lighting_Mats/Light_Functions/Instances/MI_LF_Cov_Caustic_B30_DoorCINE` | MaterialInstance | 0.00 |  |  | E30 | no |  |
| `/Game/Lighting/Lighting_Mats/Light_Functions/Instances/MI_LF_Cov_E30_Hydroponic` | MaterialInstance | 0.00 |  |  | E30 | no |  |
| `/Game/Lighting/Lighting_Mats/Light_Functions/Instances/MI_LF_Noise_Flicker_C45_ControlRoom` | MaterialInstance | 0.00 |  |  | B40,C45 | no |  |
| `/Game/Lighting/Lighting_Mats/Light_Functions/Instances/MI_LF_ShineLight_B30` | MaterialInstance | 0.00 |  |  | B30 | no |  |
| `/Game/Lighting/Lighting_Mats/Light_Functions/Instances/MI_LF_ShineLight_B40_Ice1` | MaterialInstance | 0.00 |  |  | B40 | no |  |
| `/Game/Lighting/Lighting_Mats/Light_Functions/Instances/MI_LF_ShineLight_E20` | MaterialInstance | 0.00 |  |  | E20,E30 | no |  |
| `/Game/Lighting/Lighting_Mats/Light_Functions/Instances/MI_LF_Standalone_Firelight_A15` | MaterialInstance | 0.00 |  |  | C10 | no |  |
| `/Game/Lighting/Lighting_Mats/Light_Functions/Instances/MI_Lighting_CloudShadows_A50_Inst` | MaterialInstance | 0.00 |  |  | A50 | no |  |
| `/Game/Lighting/Lighting_Mats/Light_Functions/Instances/MI_Lighting_FakeBreakup` | MaterialInstance | 0.00 |  |  | A50,C10,E20 | no |  |
| `/Game/Lighting/Lighting_Mats/Light_Functions/Instances/MI_Lighting_FakeBreakup_A30` | MaterialInstance | 0.00 |  |  | E20 | no |  |
| `/Game/Lighting/Lighting_Mats/Light_Functions/Instances/MI_Lighting_FakeTowerLineLight_C10` | MaterialInstance | 0.00 |  |  | C10 | no |  |
| `/Game/Lighting/Lighting_Mats/Light_Functions/Instances/MI_Lighting_FakeTreeShadows_C10` | MaterialInstance | 0.00 |  |  | C10 | no |  |
| `/Game/Lighting/Lighting_Mats/Light_Functions/Instances/MI_Lighting_FakeTreeShadows_C10_2` | MaterialInstance | 0.00 |  |  | A50,C10 | no |  |
| `/Game/Lighting/Lighting_Mats/Light_Functions/MI_Lighting_Shadows_Tiled_Static_MultiTexture_C10_TowerLineLight` | MaterialInstance | 0.00 |  |  | E10 | no |  |
| `/Game/Lighting/Lighting_Mats/Light_Functions/M_A30_sun_redux` | Material | 0.03 |  |  | A30,A50 | no |  |
| `/Game/Lighting/Lighting_Mats/Light_Functions/M_LF_Cov_A50_GravLiftWraith` | Material | 0.03 |  |  | A50,D20,E10,E30 | no |  |
| `/Game/Lighting/Lighting_Mats/Light_Functions/M_LF_Cov_Caustic_A` | Material | 0.03 |  |  | E30 | no |  |
| `/Game/Lighting/Lighting_Mats/Light_Functions/M_LF_Cov_Ghost` | Material | 0.03 |  |  | E10,E30 | no |  |
| `/Game/Lighting/Lighting_Mats/Light_Functions/M_LF_Cov_Hex` | Material | 0.03 |  |  | E30 | no |  |
| `/Game/Lighting/Lighting_Mats/Light_Functions/M_LF_Cov_Wraith` | Material | 0.03 |  |  | E30 | no |  |
| `/Game/Lighting/Lighting_Mats/Light_Functions/M_LF_FR_Light_Pulse` | Material | 0.03 |  |  | B40,C20,C45 | no |  |
| `/Game/Lighting/Lighting_Mats/Light_Functions/M_LF_FakingFades` | Material | 0.03 |  |  | C10 | no |  |
| `/Game/Lighting/Lighting_Mats/Light_Functions/M_LF_Flashlight` | Material | 0.03 |  |  |  | no |  |
| `/Game/Lighting/Lighting_Mats/Light_Functions/M_LF_Flood_Gobo` | Material | 0.03 |  |  | C20,D20 | no |  |
| `/Game/Lighting/Lighting_Mats/Light_Functions/M_LF_GenericLightFunction_UNSC` | Material | 0.03 |  |  | A15 | no |  |
| `/Game/Lighting/Lighting_Mats/Light_Functions/M_LF_Noise_Flicker_01` | Material | 0.03 |  |  | B40,C45 | no |  |
| `/Game/Lighting/Lighting_Mats/Light_Functions/M_LF_ShineLight` | Material | 0.04 |  |  | B30,E20,E30 | no |  |
| `/Game/Lighting/Lighting_Mats/Light_Functions/M_LF_ShineLight_B40` | Material | 0.04 |  |  | B40 | no |  |
| `/Game/Lighting/Lighting_Mats/Light_Functions/M_LF_Standalone_Firelight` | Material | 0.03 |  |  | C10,D20,E10,E20,E30 | no |  |
| `/Game/Lighting/Lighting_Mats/Light_Functions/M_LF_TreeDabble_Panning_C10` | Material | 0.03 |  |  | C10 | no |  |
| `/Game/Lighting/Lighting_Mats/Light_Functions/M_Lighting_CloudShadows_A50` | Material | 0.04 |  |  | A50 | no |  |

*Group note:* PWR uses MI_FREmissive_Solid_B40_Blue

### Light cones and volumetric shafts (82)

*Where on PWR:* Canopy light shafts in the pine stands, base interiors

| path | kind | MB | verts | bounds m | levels | PWR | note |
|---|---|---|---|---|---|---|---|
| `/Game/Lighting/LightCone/BP_LightCone_Child_Chieflights` | Blueprint | 0.00 |  |  | D20 | no |  |
| `/Game/Lighting/LightCone/BP_LightCone_Child_daryl` | Blueprint | 0.00 |  |  | A50,D20 | no |  |
| `/Game/Lighting/LightCone/BP_LightCone_og_deprecated` | Blueprint | 0.02 |  |  | A15,A30,A50,B30,B40,C10,C20,C45,D20,D40,E10,E20,E30 | no |  |
| `/Game/Lighting/LightCone/SupportingContent/M_LightCone_Animated` | MaterialInstance | 0.01 |  |  | A15,A30,A50,B30,B40,C10,C20,C45,D20,D40,E10,E20,E30 | no |  |
| `/Game/Lighting/LightCone/SupportingContent/M_LightCone_BonusCheap` | Material | 0.01 |  |  | A15,A30,A50,B30,B40,C10,C20,C45,D20,D40,E10,E20,E30 | no |  |
| `/Game/Lighting/LightCone/SupportingContent/M_LightCone_BonusCheap_Animated` | MaterialInstance | 0.01 |  |  | A15,A30,A50,B30,B40,C10,C20,C45,D20,D40,E10,E20,E30 | no |  |
| `/Game/Lighting/LightCone/SupportingContent/M_LightCone_Cheap` | Material | 0.01 |  |  | A15,A30,A50,B30,B40,C10,C20,C45,D20,D40,E10,E20,E30 | no |  |
| `/Game/Lighting/LightCone/SupportingContent/M_LightCone_Cheap_Animated` | MaterialInstance | 0.01 |  |  | A15,A30,A50,B30,B40,C10,C20,C45,D20,D40,E10,E20,E30 | no |  |
| `/Game/Lighting/LightCone/SupportingContent/M_LightCone_MASTER` | Material | 0.01 |  |  | A15,A30,A50,B30,B40,C10,C20,C45,D20,D40,E10,E20,E30 | no |  |
| `/Game/Lighting/LightCone/SupportingContent/SM_LightCone_Plane` | StaticMesh | 0.00 | 4 | 1.0x0.0x0.01 | A15,A30,A50,B30,B40,C10,C20,C45,D20,D40,E10,E20,E30 | no |  |
| `/Game/Lighting/LightCone_Volumetric/BPC_LightCone_Volumetric` | Blueprint | 0.03 |  |  | A15,A30,A50,B30,B40,C10,C20,C45,D20,D40,E10,E20,E30 | no |  |
| `/Game/Lighting/LightCone_Volumetric/BP_LightCone_Volumetric` | Blueprint | 0.01 |  |  | A15,A30,A50,B30,B40,C10,C20,C45,D20,D40,E10,E20,E30 | no |  |
| `/Game/Lighting/LightCone_Volumetric/Materials/MI_LightCone_Volume_Rectlight` | MaterialInstance | 0.01 |  |  | A15,A30,A50,B30,B40,C10,C20,C45,D20,D40,E10,E20,E30 | no |  |
| `/Game/Lighting/LightCone_Volumetric/Materials/MI_LightCone_Volume_Rectlight_NearFade` | MaterialInstance | 0.01 |  |  | A15,A30,A50,B30,B40,C10,C20,C45,D20,D40,E10,E20,E30 | no |  |
| `/Game/Lighting/LightCone_Volumetric/Materials/MI_LightCone_Volume_Spotlight` | MaterialInstance | 0.00 |  |  | A15,A30,A50,B30,B40,C10,C20,C45,D20,D40,E10,E20,E30 | no |  |
| `/Game/Lighting/LightCone_Volumetric/Materials/MI_LightCone_Volume_Spotlight_NearFade` | MaterialInstance | 0.01 |  |  | A15,A30,A50,B30,B40,C10,C20,C45,D20,D40,E10,E20,E30 | no |  |
| `/Game/Lighting/LightCone_Volumetric/Materials/M_LightCone_Volume` | Material | 0.02 |  |  | A15,A30,A50,B30,B40,C10,C20,C45,D20,D40,E10,E20,E30 | no |  |
| `/Game/Lighting/LightCone_Volumetric/Meshes/SM_LightCone_Cube` | StaticMesh | 0.01 | 24 | 1.0x1.0x1.0 | A15,A30,A50,B30,B40,C10,C20,C45,D20,D40,E10,E20,E30 | no |  |
| `/Game/Lighting/LightCone_v2/BPC_LightCone` | Blueprint | 0.02 |  |  | A15,A30,A50,B30,B40,C10,C20,C45,D20,D40,E10,E20,E30 | no |  |
| `/Game/Lighting/LightCone_v2/BP_LightCone` | Blueprint | 0.02 |  |  | A15,A30,A50,B30,B40,C10,C20,C45,D20,D40,E10,E20,E30 | no |  |
| `/Game/Lighting/LightCone_v2/BP_LightCone_Deprecated` | Blueprint | 0.02 |  |  | A15,A30,A50,B30,B40,C10,C20,C45,D20,D40,E10,E20,E30 | no |  |
| `/Game/Lighting/LightCone_v2/Materials/MI_LightCone` | MaterialInstance | 0.01 |  |  | A15,A30,A50,B30,B40,C10,C20,C45,D20,D40,E10,E20,E30 | no |  |
| `/Game/Lighting/LightCone_v2/Materials/MI_LightCone_Animated` | MaterialInstance | 0.01 |  |  | A15,A30,A50,B30,B40,C10,C20,C45,D20,D40,E10,E20,E30 | no |  |
| `/Game/Lighting/LightCone_v2/Materials/MI_LightCone_Animated_Facing` | MaterialInstance | 0.01 |  |  | A15,A30,A50,B30,B40,C10,C20,C45,D20,D40,E10,E20,E30 | no |  |
| `/Game/Lighting/LightCone_v2/Materials/MI_LightCone_Animated_Facing_Fogging` | MaterialInstance | 0.01 |  |  | A15,A30,A50,B30,B40,C10,C20,C45,D20,D40,E10,E20,E30 | no |  |
| `/Game/Lighting/LightCone_v2/Materials/MI_LightCone_Animated_Fading` | MaterialInstance | 0.01 |  |  | A15,A30,A50,B30,B40,C10,C20,C45,D20,D40,E10,E20,E30 | no |  |
| `/Game/Lighting/LightCone_v2/Materials/MI_LightCone_Animated_Fading_Facing` | MaterialInstance | 0.00 |  |  | A15,A30,A50,B30,B40,C10,C20,C45,D20,D40,E10,E20,E30 | no |  |
| `/Game/Lighting/LightCone_v2/Materials/MI_LightCone_Animated_Fading_Facing_Fogging` | MaterialInstance | 0.00 |  |  | A15,A30,A50,B30,B40,C10,C20,C45,D20,D40,E10,E20,E30 | no |  |
| `/Game/Lighting/LightCone_v2/Materials/MI_LightCone_Animated_Fading_Fogging` | MaterialInstance | 0.01 |  |  | A15,A30,A50,B30,B40,C10,C20,C45,D20,D40,E10,E20,E30 | no |  |
| `/Game/Lighting/LightCone_v2/Materials/MI_LightCone_Animated_Fogging` | MaterialInstance | 0.01 |  |  | A15,A30,A50,B30,B40,C10,C20,C45,D20,D40,E10,E20,E30 | no |  |
| `/Game/Lighting/LightCone_v2/Materials/MI_LightCone_Facing` | MaterialInstance | 0.01 |  |  | A15,A30,A50,B30,B40,C10,C20,C45,D20,D40,E10,E20,E30 | no |  |
| `/Game/Lighting/LightCone_v2/Materials/MI_LightCone_Facing_Fading` | MaterialInstance | 0.01 |  |  | A15,A30,A50,B30,B40,C10,C20,C45,D20,D40,E10,E20,E30 | no |  |
| `/Game/Lighting/LightCone_v2/Materials/MI_LightCone_Facing_Fading_Fogging` | MaterialInstance | 0.01 |  |  | A15,A30,A50,B30,B40,C10,C20,C45,D20,D40,E10,E20,E30 | no |  |
| `/Game/Lighting/LightCone_v2/Materials/MI_LightCone_Facing_Fogging` | MaterialInstance | 0.01 |  |  | A15,A30,A50,B30,B40,C10,C20,C45,D20,D40,E10,E20,E30 | no |  |
| `/Game/Lighting/LightCone_v2/Materials/MI_LightCone_Fading` | MaterialInstance | 0.01 |  |  | A15,A30,A50,B30,B40,C10,C20,C45,D20,D40,E10,E20,E30 | no |  |
| `/Game/Lighting/LightCone_v2/Materials/MI_LightCone_Fading_Fogging` | MaterialInstance | 0.01 |  |  | A15,A30,A50,B30,B40,C10,C20,C45,D20,D40,E10,E20,E30 | no |  |
| `/Game/Lighting/LightCone_v2/Materials/MI_LightCone_Fogging` | MaterialInstance | 0.01 |  |  | A15,A30,A50,B30,B40,C10,C20,C45,D20,D40,E10,E20,E30 | no |  |
| `/Game/Lighting/LightCone_v2/Materials/M_LightCone_MASTER` | Material | 0.02 |  |  | A15,A30,A50,B30,B40,C10,C20,C45,D20,D40,E10,E20,E30 | no |  |
| `/Game/Lighting/LightCone_v2/Materials/M_LightCone_MASTER_Fogging` | Material | 0.02 |  |  | A15,A30,A50,B30,B40,C10,C20,C45,D20,D40,E10,E20,E30 | no |  |
| `/Game/Lighting/LightCone_v2/Meshes/SM_LightCone_Plane_1x` | StaticMesh | 0.00 | 4 | 1.0x1.0x0.0 | A15,A30,A50,B30,B40,C10,C20,C45,D20,D40,E10,E20,E30 | no |  |

Textures: `/Game/Lighting/LightCone/Textures/Space/T_LightCone_Noise_Swirl_D` (0.2 MB), `/Game/Lighting/LightCone/Textures/Space/T_LightCone_Stars` (0.2 MB), `/Game/Lighting/LightCone/Textures/Space/T_LightCone_Swirl_Comet` (0.2 MB), `/Game/Lighting/LightCone/Textures/Space/T_Lightcone_Space_Rays_B` (0.4 MB), `/Game/Lighting/LightCone/Textures/Space/T_Lightcone_Space_Rays_C_Starry` (0.2 MB), `/Game/Lighting/LightCone/Textures/T_A_Mask` (0.0 MB), `/Game/Lighting/LightCone/Textures/T_A_Mask2` (0.0 MB), `/Game/Lighting/LightCone/Textures/T_A_Mask3` (0.0 MB), `/Game/Lighting/LightCone/Textures/T_Cloud_wide_01` (0.4 MB), `/Game/Lighting/LightCone/Textures/T_Cloud_wide_02` (0.2 MB), `/Game/Lighting/LightCone/Textures/T_Cloud_wide_03` (0.2 MB), `/Game/Lighting/LightCone/Textures/T_Helmet_lights_2` (0.2 MB), `/Game/Lighting/LightCone/Textures/T_LightCone_FR_Puck_Tri_Side` (0.2 MB), `/Game/Lighting/LightCone/Textures/T_LightCone_Mask01` (2.8 MB), `/Game/Lighting/LightCone/Textures/T_LightShaft_01` (0.1 MB), `/Game/Lighting/LightCone/Textures/T_Lightcone_FR_Long_Wrench` (0.2 MB), `/Game/Lighting/LightCone/Textures/T_Lightcone_Flood_Noise_A` (0.2 MB), `/Game/Lighting/LightCone/Textures/T_Lightcone_Mask_Noise_A` (1.4 MB), `/Game/Lighting/LightCone/Textures/T_Lightcone_Mask_Noise_B` (0.2 MB), `/Game/Lighting/LightCone/Textures/T_Lightcone_MidSource_A` (0.0 MB), `/Game/Lighting/LightCone/Textures/T_Lightcone_NarrowSource_A` (0.2 MB), `/Game/Lighting/LightCone/Textures/T_Lightcone_Rays_Harsh` (0.0 MB), `/Game/Lighting/LightCone/Textures/T_Lightcone_Rays_Soft_MidSource` (0.2 MB), `/Game/Lighting/LightCone/Textures/T_Lightcone_Rays_Soft_Wide` (0.2 MB), `/Game/Lighting/LightCone/Textures/T_Lightcone_Shape_Snow_A` (0.2 MB), `/Game/Lighting/LightCone/Textures/T_Lightcone_Soft_Wide_A` (0.0 MB), `/Game/Lighting/LightCone/Textures/T_Lightcone_Streaked_ClosedSource` (0.2 MB), `/Game/Lighting/LightCone/Textures/T_Lightcone_V` (0.1 MB), `/Game/Lighting/LightCone/Textures/T_Lightcone_Wide_A` (0.0 MB), `/Game/Lighting/LightCone/Textures/T_Lightcone_Wide_A_Line` (0.0 MB), `/Game/Lighting/LightCone/Textures/T_Lightcone_Wide_A_Rays_Harsh` (0.0 MB), `/Game/Lighting/LightCone/Textures/T_Lightcone_Wide_Glow` (0.2 MB), `/Game/Lighting/LightCone/Textures/T_Lightcone_Wide_LowFog` (0.0 MB), `/Game/Lighting/LightCone/Textures/T_TilingNoise02_M` (1.4 MB), `/Game/Lighting/LightCone/Textures/T_smoke_harsh_a` (0.2 MB), `/Game/Lighting/LightCone/Textures/T_smoke_harsh_b` (0.2 MB), `/Game/Lighting/LightCone/Textures/T_smoke_harsh_c_` (0.0 MB), `/Game/Lighting/LightCone/Textures/TilingNoise/T_LightCone_Cloud_Moisture` (0.2 MB), `/Game/Lighting/LightCone/Textures/TilingNoise/T_LightCone_Cloud_Moisture_B` (0.2 MB), `/Game/Lighting/LightCone/Textures/TilingNoise/T_Lightcone_Cloud_Snow_A` (0.2 MB), `/Game/Lighting/LightCone/Textures/TilingNoise/T_Lightcone_Flood_Noise_A` (0.2 MB), `/Game/Lighting/LightCone/Textures/TilingNoise/T_TilingNoise_SnowB` (0.2 MB)

*Group note:* Material-only light shafts (cheap, data-only)

### Forerunner exterior light fixture BPs (B40/A30) (61)

*Where on PWR:* Uplights on base walls and towers, outdoor pucks along bridge decks

| path | kind | MB | verts | bounds m | levels | PWR | note |
|---|---|---|---|---|---|---|---|
| `/Game/Lighting/LightFixture_BPs/Forerunner/A30/BP_FrunnerTower_puckrig` | Blueprint | 0.02 |  |  | A30 | no |  |
| `/Game/Lighting/LightFixture_BPs/Forerunner/A30/BP_LightFixture_FR_Large_Tall_A30_Purple_NoLight` | Blueprint | 0.00 |  |  | A30 | no |  |
| `/Game/Lighting/LightFixture_BPs/Forerunner/B40/BP_LightFixture_FR_Bend_a_ceilling_White_Spot_Ext` | Blueprint | 0.00 |  |  | B40,C45 | no |  |
| `/Game/Lighting/LightFixture_BPs/Forerunner/B40/BP_LightFixture_FR_Panel_A_Big_Blue_Tower` | Blueprint | 0.00 |  |  | B40,C45 | no |  |
| `/Game/Lighting/LightFixture_BPs/Forerunner/B40/BP_LightFixture_FR_Panel_A_White_Ext` | Blueprint | 0.00 |  |  | B40,C45 | no |  |
| `/Game/Lighting/LightFixture_BPs/Forerunner/B40/BP_LightFixture_FR_Panel_A_White_Rect_Ext` | Blueprint | 0.00 |  |  | B40 | no |  |
| `/Game/Lighting/LightFixture_BPs/Forerunner/B40/BP_LightFixture_FR_Panel_A_White_Rect_Ext_2` | Blueprint | 0.00 |  |  | B40,C45 | no |  |
| `/Game/Lighting/LightFixture_BPs/Forerunner/B40/BP_LightFixture_FR_Panel_B_ArenaEdge` | Blueprint | 0.00 |  |  | C45 | no |  |
| `/Game/Lighting/LightFixture_BPs/Forerunner/B40/BP_LightFixture_FR_Panel_B_TowerTop` | Blueprint | 0.00 |  |  | B40,C45 | no |  |
| `/Game/Lighting/LightFixture_BPs/Forerunner/B40/BP_LightFixture_FR_Puck_A_Sml_LightBlue_Spot_Ext` | Blueprint | 0.00 |  |  | B40,C45 | no |  |
| `/Game/Lighting/LightFixture_BPs/Forerunner/B40/BP_LightFixture_FR_Puck_A_Sml_LightBlue_Spot_Ext_Ziggurart_Uplight` | Blueprint | 0.00 |  |  | B40,C45 | no |  |
| `/Game/Lighting/LightFixture_BPs/Forerunner/B40/BP_LightFixture_FR_Tall_A_LightBlue_Ext` | Blueprint | 0.00 |  |  | B40,C45 | no |  |
| `/Game/Lighting/LightFixture_BPs/Forerunner/B40/BP_LightFixture_FR_Tall_A_WhiteDark_Ext` | Blueprint | 0.00 |  |  | B40,C45 | no |  |
| `/Game/Lighting/LightFixture_BPs/Forerunner/B40/BP_LightFixture_FR_Tall_B_WhiteCold_Spot_Ext` | Blueprint | 0.00 |  |  | B40 | no |  |
| `/Game/Lighting/LightFixture_BPs/Forerunner/B40/BP_LightFixture_Puck_Med_A_Cold_Spot_Ext` | Blueprint | 0.00 |  |  | B40,C45 | no |  |
| `/Game/Lighting/LightFixture_BPs/Forerunner/B40/BP_LightFixture_Puck_Med_A_White_Spot_Ext` | Blueprint | 0.00 |  |  | B40,C45 | no |  |
| `/Game/Lighting/LightFixture_BPs/Forerunner/B40/BP_LightFixture_Puck_Sticker_03_White_01_Rect_Ext` | Blueprint | 0.00 |  |  | B40 | no |  |
| `/Game/Lighting/LightFixture_BPs/Forerunner/B40/BP_LightFixture_Tall_B_WhiteCold_Rect_Ext` | Blueprint | 0.00 |  |  | B40,C45 | no |  |
| `/Game/Lighting/LightFixture_BPs/Forerunner/B40/BP_LightFixture_Tall_B_WhiteWarm_Ext` | Blueprint | 0.00 |  |  | B40,C45 | no |  |
| `/Game/Lighting/LightFixture_BPs/Forerunner/B40/BP_LightFixture_Tall_B_WhiteWarm_Spot_Ext` | Blueprint | 0.00 |  |  | B40,C45 | no |  |
| `/Game/Lighting/LightFixture_BPs/Forerunner/B40/BP_LightFixture_Tall_B_White_Outdoor_01` | Blueprint | 0.00 |  |  | B40,C45 | no |  |
| `/Game/Lighting/LightFixture_BPs/Forerunner/B40/BP_LightFixture_Tall_B_White_Outdoor_Rect_01` | Blueprint | 0.00 |  |  | B40,C45 | no |  |
| `/Game/Lighting/LightFixture_BPs/Forerunner/B40/Puck/BP_LightFixture_Puck_Box_Gradient_Blue_Big_Ext` | Blueprint | 0.00 |  |  | B40,C45 | no |  |
| `/Game/Lighting/LightFixture_BPs/Forerunner/B40/Puck/BP_LightFixture_Puck_Box_Gradient_Blue_Ext` | Blueprint | 0.00 |  |  | B40,C45 | no |  |
| `/Game/Lighting/LightFixture_BPs/Forerunner/B40/Puck/BP_LightFixture_Puck_Box_Gradient_Dark_Blue_Big_Ext` | Blueprint | 0.00 |  |  | B40,C45 | no |  |
| `/Game/Lighting/LightFixture_BPs/Forerunner/B40/Puck/BP_LightFixture_Puck_Box_Gradient_Light_Blue_02_Ext` | Blueprint | 0.00 |  |  | B40,C45 | no |  |
| `/Game/Lighting/LightFixture_BPs/Forerunner/B40/Puck/BP_LightFixture_Puck_Box_Gradient_Light_Blue_Ext` | Blueprint | 0.00 |  |  | B40,C45 | no |  |
| `/Game/Lighting/LightFixture_BPs/Forerunner/B40/Puck/BP_LightFixture_Puck_Box_Gradient_Light_Blue_Rect_Ext` | Blueprint | 0.00 |  |  | B40,C45 | no |  |
| `/Game/Lighting/LightFixture_BPs/Forerunner/B40/Puck/BP_LightFixture_Puck_Box_Gradient_Light_Grey_Ext` | Blueprint | 0.00 |  |  | B40,C45 | no |  |
| `/Game/Lighting/LightFixture_BPs/Forerunner/B40/Puck/BP_LightFixture_Puck_Box_Gradient_Violet_Ext` | Blueprint | 0.00 |  |  | B40,C45 | no |  |
| `/Game/Lighting/LightFixture_BPs/Forerunner/B40/Puck/BP_LightFixture_Puck_Box_Gradient_White_Ext` | Blueprint | 0.00 |  |  | B40,C45 | no |  |
| `/Game/Lighting/LightFixture_BPs/Forerunner/B40/Puck/BP_LightFixture_Puck_Box_Gradient_White_Ext_02` | Blueprint | 0.00 |  |  | B40,C45 | no |  |
| `/Game/Lighting/LightFixture_BPs/Forerunner/B40/Puck/BP_LightFixture_Puck_Box_Gradient_White_Ext_03` | Blueprint | 0.00 |  |  | B40,C45 | no |  |
| `/Game/Lighting/LightFixture_BPs/Forerunner/B40/Puck/BP_LightFixture_Puck_Box_Gradient_White_Rect_Ext` | Blueprint | 0.00 |  |  | B40,C45 | no |  |
| `/Game/Lighting/LightFixture_BPs/Forerunner/B40/Puck/BP_LightFixture_Puck_Box_Sml_HotOrage_Spot_Ext` | Blueprint | 0.00 |  |  | C45 | no |  |
| `/Game/Lighting/LightFixture_BPs/Forerunner/B40/Puck/BP_LightFixture_Puck_FR_Mask_F_Blue_01_Ext` | Blueprint | 0.00 |  |  | B40,C45 | no |  |
| `/Game/Lighting/LightFixture_BPs/Forerunner/B40/Puck/BP_LightFixture_Puck_FR_Mask_F_Blue_02_Ext` | Blueprint | 0.00 |  |  | B40,C45 | no |  |
| `/Game/Lighting/LightFixture_BPs/Forerunner/B40/Puck/BP_LightFixture_Puck_Mask_B_Big_HotOrage_Spot_Ext` | Blueprint | 0.00 |  |  | C45 | no |  |
| `/Game/Lighting/LightFixture_BPs/Forerunner/B40/Puck/BP_LightFixture_Puck_Mask_B_Blue_Sml_Ext` | Blueprint | 0.00 |  |  | B40,C45 | no |  |
| `/Game/Lighting/LightFixture_BPs/Forerunner/B40/Puck/BP_LightFixture_Puck_Mask_B_Blue_Spot_Sml_Ext` | Blueprint | 0.00 |  |  | B40,C45 | no |  |
| `/Game/Lighting/LightFixture_BPs/Forerunner/B40/Puck/BP_LightFixture_Puck_Mask_B_White_Spot_Ext` | Blueprint | 0.00 |  |  | B40,C45 | no |  |
| `/Game/Lighting/LightFixture_BPs/Forerunner/B40/Puck/BP_LightFixture_Puck_Mask_B_White_Spot_Sml_Ext` | Blueprint | 0.00 |  |  | B40,C45 | no |  |
| `/Game/Lighting/LightFixture_BPs/Forerunner/B40/Puck/BP_LightFixture_Puck_Mask_C_Sml_Cold_Ext` | Blueprint | 0.00 |  |  | B40,C45 | no |  |
| `/Game/Lighting/LightFixture_BPs/Forerunner/B40/Puck/BP_LightFixture_Puck_Mask_C_Sml_Cold_flip_Ext` | Blueprint | 0.00 |  |  | B40,C45 | no |  |
| `/Game/Lighting/LightFixture_BPs/Forerunner/B40/Puck/BP_LightFixture_Puck_Mask_E_Sml_Cold_Ext` | Blueprint | 0.00 |  |  | B40,C45 | no |  |
| `/Game/Lighting/LightFixture_BPs/Forerunner/B40/Puck/BP_LightFixture_Puck_Mask_E_Sml_Cold_flip_Ext` | Blueprint | 0.00 |  |  | B40,C45 | no |  |
| `/Game/Lighting/LightFixture_BPs/Forerunner/B40/Puck/BP_LightFixture_Puck_Panel_Sml_Blue_01_Ext` | Blueprint | 0.00 |  |  | B40,C45 | no |  |
| `/Game/Lighting/LightFixture_BPs/Forerunner/B40/Puck/BP_LightFixture_Puck_Panel_Sml_Light_Blue_01_Ext` | Blueprint | 0.00 |  |  | B40,C45 | no |  |
| `/Game/Lighting/LightFixture_BPs/Forerunner/B40/Puck/BP_LightFixture_Puck_Panel_Sml_White_02_Ext` | Blueprint | 0.00 |  |  | C45 | no |  |
| `/Game/Lighting/LightFixture_BPs/Forerunner/B40/Puck/BP_LightFixture_Puck_Sticker_03_Blue_01_Ext` | Blueprint | 0.00 |  |  | B40,C45 | no |  |
| `/Game/Lighting/LightFixture_BPs/Forerunner/B40/Puck/BP_LightFixture_Puck_Sticker_03_Blue_02_Ext` | Blueprint | 0.00 |  |  | B40,C45 | no |  |
| `/Game/Lighting/LightFixture_BPs/Forerunner/B40/Puck/BP_LightFixture_Puck_Sticker_03_Blue_Ext` | Blueprint | 0.00 |  |  | B40,C45 | no |  |
| `/Game/Lighting/LightFixture_BPs/Forerunner/B40/Puck/BP_LightFixture_Puck_Sticker_03_Cold_Ext` | Blueprint | 0.00 |  |  | B40,C45 | no |  |
| `/Game/Lighting/LightFixture_BPs/Forerunner/B40/Puck/BP_LightFixture_Puck_Sticker_03_Cold_Rect_Ext` | Blueprint | 0.00 |  |  | C45 | no |  |
| `/Game/Lighting/LightFixture_BPs/Forerunner/B40/Puck/BP_LightFixture_Puck_Sticker_03_Grey_Ext` | Blueprint | 0.00 |  |  | B40,C45 | no |  |
| `/Game/Lighting/LightFixture_BPs/Forerunner/B40/Puck/BP_LightFixture_Puck_Sticker_04_Blue_Ext` | Blueprint | 0.00 |  |  | B40,C45 | no |  |
| `/Game/Lighting/LightFixture_BPs/Forerunner/B40/Puck/BP_LightFixture_Puck_Sticker_04_Light_Blue_Ext` | Blueprint | 0.00 |  |  | B40,C45 | no |  |
| `/Game/Lighting/LightFixture_BPs/Forerunner/B40/Puck/BP_LightFixture_Puck_Sticker_06_Blue_Spot_Ext` | Blueprint | 0.00 |  |  | B40,C45 | no |  |
| `/Game/Lighting/LightFixture_BPs/Forerunner/B40/Puck/BP_LightFixture_Puck_Sticker_06_Grey_Spot_Ext` | Blueprint | 0.00 |  |  | B40,C45 | no |  |
| `/Game/Lighting/LightFixture_BPs/Forerunner/B40/Puck/BP_LightFixture_Puck_Sticker_06_Light_Blue_Rect_Ext` | Blueprint | 0.00 |  |  | B40,C45 | no |  |
| `/Game/Lighting/LightFixture_BPs/Forerunner/B40/Puck/BP_LightFixture_Puck_Sticker_06_Violet_Ext` | Blueprint | 0.00 |  |  | B40,C45 | no |  |

*Group note:* B40 exterior-tagged fixture BPs (mesh + UE light + emissive). BPs carry UE light components: verify the loader can spawn a BP, else rebuild as decor mesh + level.json lights[]

### Meteorite level ambience events (9)

*Where on PWR:* Birdsong, insects, tree-snow falls

| path | kind | MB | verts | bounds m | levels | PWR | note |
|---|---|---|---|---|---|---|---|
| `/Game/WwiseAudio/Events/Meteorite/Ambience/A50/A50_Positionals/A50_Exterior/A50_Ext_Objects/Play_AMB_ENV_A50_Ext_Plateau_Rocks_Hits` | WwiseEvent | 0.00 |  |  |  | no |  |
| `/Game/WwiseAudio/Events/Meteorite/Ambience/B30/B30_Positionals/B30_Exteriors/BirdSong/Play_AMB_ENV_B30_Ext_Fauna_Parakeet_A_LP` | WwiseEvent | 0.00 |  |  | B30 | no |  |
| `/Game/WwiseAudio/Events/Meteorite/Ambience/B30/B30_Positionals/B30_Exteriors/BirdSong/Play_AMB_ENV_B30_Ext_Fauna_Parakeet_B_LP` | WwiseEvent | 0.00 |  |  | B30 | no |  |
| `/Game/WwiseAudio/Events/Meteorite/Ambience/B30/B30_Positionals/B30_Exteriors/BirdSong/Play_AMB_ENV_B30_Ext_Fauna_Starling_A_LP` | WwiseEvent | 0.00 |  |  | B30 | no |  |
| `/Game/WwiseAudio/Events/Meteorite/Ambience/B30/B30_Positionals/B30_Exteriors/Insects/Play_AMB_ENV_B30_Ext_Insects_DragonFlies_LP` | WwiseEvent | 0.00 |  |  |  | no |  |
| `/Game/WwiseAudio/Events/Meteorite/Ambience/B30/B30_Positionals/B30_Exteriors/Insects/Play_AMB_ENV_B30_Ext_Insects_Moths_LP` | WwiseEvent | 0.00 |  |  |  | no |  |
| `/Game/WwiseAudio/Events/Meteorite/Ambience/B30/B30_Positionals/B30_Exteriors/objects/Play_AMB_ENV_A50_IdleLargeCovenantShip_LP_01` | WwiseEvent | 0.00 |  |  | A50 | no |  |
| `/Game/WwiseAudio/Events/Meteorite/Ambience/B40/B40_Positionals/Play_AMB_ENV_B40_Ice_Chunks_Fall` | WwiseEvent | 0.00 |  |  | B40,C45 | no |  |
| `/Game/WwiseAudio/Events/Meteorite/Ambience/B40/B40_Positionals/Play_AMB_ENV_B40_Tree_Snow_Fall` | WwiseEvent | 0.00 |  |  | B40,C45 | no | snow variant |

*Group note:* Wwise events; integration unverified

## 8. Structures, wreckage and other set dressing (924)

### Forerunner exterior kits (Silent Cartographer, Halo, Control Room) (317)

*Where on PWR:* Base dressing, ruins on ridgelines, bridge abutments, outposts

| path | kind | MB | verts | bounds m | levels | PWR | note |
|---|---|---|---|---|---|---|---|
| `/Game/Env/HS/FR/ACR/Canyon_A_Tower/FR_ACR_Int_Canyon_A_Tower_Ceiling_w18_d33_h2_A/SM_FR_ACR_Int_Canyon_A_Tower_Ceiling_w18_d33_h2_A` | StaticMesh | 0.86 | 12,831 | 18.21x32.57x2.05 | B40,C45 | no |  |
| `/Game/Env/HS/FR/ACR/Canyon_A_Tower/FR_ACR_Int_Canyon_A_Tower_Ceiling_w28_d38_h12_A/SM_FR_ACR_Int_Canyon_A_Tower_Ceiling_w28_d38_h12_A` | StaticMesh | 1.60 | 26,189 | 28.42x37.88x11.71 | B40,C45 | no |  |
| `/Game/Env/HS/FR/ACR/Canyon_A_Tower/FR_ACR_Int_Canyon_A_Tower_Ceiling_w28_d46_h19_A/SM_FR_ACR_Int_Canyon_A_Tower_Ceiling_w28_d46_h19_A` | StaticMesh | 6.78 | 128,034 | 45.52x28.21x19.12 | B40,C45 | no |  |
| `/Game/Env/HS/FR/ACR/Canyon_A_Tower/FR_ACR_Int_Canyon_A_Tower_Ceiling_w29_d26_h12_A/SM_FR_ACR_Int_Canyon_A_Tower_Ceiling_w29_d26_h12_A` | StaticMesh | 1.41 | 22,766 | 28.78x26.23x11.72 | B40,C45 | no |  |
| `/Game/Env/HS/FR/ACR/Canyon_A_Tower/FR_ACR_Int_Canyon_A_Tower_Ceiling_w32_d32_h9_A/SM_FR_ACR_Int_Canyon_A_Tower_Ceiling_w32_d32_h9_A` | StaticMesh | 3.51 | 74,222 | 31.51x31.51x9.11 | B40,C45 | no |  |
| `/Game/Env/HS/FR/ACR/Canyon_A_Tower/FR_ACR_Int_Canyon_A_Tower_Ceiling_w33_d33_h9_A/SM_FR_ACR_Int_Canyon_A_Tower_Ceiling_w33_d33_h9_A` | StaticMesh | 1.95 | 36,315 | 33.26x33.28x8.97 | B40,C45 | no |  |
| `/Game/Env/HS/FR/ACR/Canyon_A_Tower/FR_ACR_Int_Canyon_A_Tower_Ceiling_w34_d34_h8_A/SM_FR_ACR_Int_Canyon_A_Tower_Ceiling_w34_d34_h8_A` | StaticMesh | 2.88 | 67,595 | 33.83x33.82x8.21 | B40,C45 | no |  |
| `/Game/Env/HS/FR/ACR/Canyon_A_Tower/FR_ACR_Int_Canyon_A_Tower_Ceiling_w36_d36_h2_A/SM_FR_ACR_Int_Canyon_A_Tower_Ceiling_w36_d36_h2_A` | StaticMesh | 0.78 | 13,702 | 35.68x35.68x2.41 | B40,C45 | no |  |
| `/Game/Env/HS/FR/ACR/Canyon_A_Tower/FR_ACR_Int_Canyon_A_Tower_Ceiling_w37_d20_h1_A/SM_FR_ACR_Int_Canyon_A_Tower_Ceiling_w37_d20_h1_A` | StaticMesh | 0.75 | 10,231 | 37.27x19.79x1.15 | B40,C45 | no |  |
| `/Game/Env/HS/FR/ACR/Canyon_A_Tower/FR_ACR_Int_Canyon_A_Tower_Ceiling_w37_d30_h12_A/SM_FR_ACR_Int_Canyon_A_Tower_Ceiling_w37_d30_h12_A` | StaticMesh | 1.65 | 25,958 | 37.21x29.57x11.71 | B40,C45 | no |  |
| `/Game/Env/HS/FR/ACR/Canyon_A_Tower/FR_ACR_Int_Canyon_A_Tower_Ceiling_w37_d37_h3_A/SM_FR_ACR_Int_Canyon_A_Tower_Ceiling_w37_d37_h3_A` | StaticMesh | 1.17 | 22,710 | 37.19x37.19x3.43 | B40,C45 | no |  |
| `/Game/Env/HS/FR/ACR/Canyon_A_Tower/FR_ACR_Int_Canyon_A_Tower_Ceiling_w39_d20_h12_A/SM_FR_ACR_Int_Canyon_A_Tower_Ceiling_w39_d20_h12_A` | StaticMesh | 1.84 | 28,134 | 39.17x19.68x11.72 | B40,C45 | no |  |
| `/Game/Env/HS/FR/ACR/Canyon_A_Tower/FR_ACR_Int_Canyon_A_Tower_Ceiling_w77_d77_h17_A/SM_FR_ACR_Int_Canyon_A_Tower_Ceiling_w77_d77_h17_A` | StaticMesh | 8.41 | 251,944 | 153.21x153.27x11.73 | C20 | no |  |
| `/Game/Env/HS/FR/ACR/Canyon_A_Tower/FR_ACR_Int_Canyon_A_Tower_Ceiling_w90_d51_65h_A/SM_FR_ACR_Int_Canyon_A_Tower_Ceiling_w90_d51_65h_A` | StaticMesh | 9.85 | 222,949 | 9.05x51.55x64.83 | B40,C45 | no |  |
| `/Game/Env/HS/FR/ACR/Canyon_A_Tower/FR_ACR_Int_Canyon_A_Tower_Device_w12_d6_h3_A/SM_FR_ACR_Int_Canyon_A_Tower_Device_w12_d6_h3_A` | StaticMesh | 2.30 | 36,687 | 11.77x5.59x2.95 | B40,C45 | no |  |
| `/Game/Env/HS/FR/ACR/Canyon_A_Tower/FR_ACR_Int_Canyon_A_Tower_Device_w32_d40_h14_A/SM_FR_ACR_Int_Canyon_A_Tower_Device_w32_d40_h14_A` | StaticMesh | 7.73 | 119,070 | 31.29x39.68x13.92 | B40,C45 | no |  |
| `/Game/Env/HS/FR/ACR/Canyon_A_Tower/FR_ACR_Int_Canyon_A_Tower_Device_w39_d21_h14_A/SM_FR_ACR_Int_Canyon_A_Tower_Device_w39_d21_h14_A` | StaticMesh | 7.59 | 108,588 | 39.19x21.11x13.9 | B40,C45 | no |  |
| `/Game/Env/HS/FR/ACR/Canyon_A_Tower/FR_ACR_Int_Canyon_A_Tower_Device_w43_d85_h3_A/BP_B40SpinningRings` | Blueprint | 0.03 |  |  | B40 | no |  |
| `/Game/Env/HS/FR/ACR/Canyon_A_Tower/FR_ACR_Int_Canyon_A_Tower_Device_w43_d85_h3_A/SM_FR_ACR_Int_Canyon_A_Tower_Device_w43_d85_h3_A` | StaticMesh | 1.30 | 37,895 | 43.65x85.14x3.48 | B40,C45 | no |  |
| `/Game/Env/HS/FR/ACR/Canyon_A_Tower/FR_ACR_Int_Canyon_A_Tower_Floor_w126_d132_h1_A/SM_FR_ACR_Int_Canyon_A_Tower_Floor_w126_d132_h1_A` | StaticMesh | 0.24 | 6,611 | 126.68x132.92x1.5 | B40,C45 | no |  |
| `/Game/Env/HS/FR/ACR/Canyon_A_Tower/FR_ACR_Int_Canyon_A_Tower_Floor_w21_d37_h5_D/SM_FR_ACR_Int_Canyon_A_Tower_Floor_w21_d37_h5_D` | StaticMesh | 2.49 | 77,436 | 21.72x37.34x5.35 | B40,C45 | no |  |
| `/Game/Env/HS/FR/ACR/Canyon_A_Tower/FR_ACR_Int_Canyon_A_Tower_Floor_w23_d31_h15_A/SM_FR_ACR_Int_Canyon_A_Tower_Floor_w23_d31_h15_A` | StaticMesh | 9.12 | 274,698 | 23.57x31.49x15.74 | B40,C45 | no |  |
| `/Game/Env/HS/FR/ACR/Canyon_A_Tower/FR_ACR_Int_Canyon_A_Tower_Floor_w23_d32_h5_B/SM_FR_ACR_Int_Canyon_A_Tower_Floor_w23_d32_h5_B` | StaticMesh | 1.98 | 60,712 | 23.05x32.27x5.65 | B40,C45 | no |  |
| `/Game/Env/HS/FR/ACR/Canyon_A_Tower/FR_ACR_Int_Canyon_A_Tower_Floor_w29_d37_h5_C/SM_FR_ACR_Int_Canyon_A_Tower_Floor_w29_d37_h5_C` | StaticMesh | 3.65 | 112,715 | 29.66x37.27x5.35 | B40,C45 | no |  |
| `/Game/Env/HS/FR/ACR/Canyon_A_Tower/FR_ACR_Int_Canyon_A_Tower_Floor_w70_d6_h8_A/SM_FR_ACR_Int_Canyon_A_Tower_Floor_w70_d6_h8_A` | StaticMesh | 0.52 | 14,583 | 158.22x102.31x152.47 | B40,C45 | no |  |
| `/Game/Env/HS/FR/ACR/Canyon_A_Tower/FR_ACR_Int_Canyon_A_Tower_Floor_w70_d86_h13_A/SM_FR_ACR_Int_Canyon_A_Tower_Floor_w70_d86_h13_A` | StaticMesh | 2.30 | 64,294 | 70.5x86.34x13.04 | B40,C45 | no |  |
| `/Game/Env/HS/FR/ACR/Canyon_A_Tower/FR_ACR_Int_Canyon_A_Tower_Pillar_w13_d18_h125_A/SM_FR_ACR_Int_Canyon_A_Tower_Pillar_w13_d18_h125_A` | StaticMesh | 10.89 | 222,706 | 13.42x19.08x125.9 | B40,C45 | no |  |
| `/Game/Env/HS/FR/ACR/Canyon_A_Tower/FR_ACR_Int_Canyon_A_Tower_Pillar_w14_d55_h49_A/SM_FR_ACR_Int_Canyon_A_Tower_Pillar_w14_d55_h49_A` | StaticMesh | 5.73 | 105,245 | 13.41x54.52x49.09 | B40,C45 | no |  |
| `/Game/Env/HS/FR/ACR/Canyon_A_Tower/FR_ACR_Int_Canyon_A_Tower_Pillar_w16_d67_h44_A/SM_FR_ACR_Int_Canyon_A_Tower_Pillar_w16_d67_h44_A` | StaticMesh | 5.79 | 104,796 | 16.36x67.22x44.04 | B40,C45 | no |  |
| `/Game/Env/HS/FR/ACR/Canyon_A_Tower/FR_ACR_Int_Canyon_A_Tower_Pillar_w17_d16_h40_A/SM_FR_ACR_Int_Canyon_A_Tower_Pillar_w17_d16_h40_A` | StaticMesh | 1.60 | 33,011 | 16.51x15.9x39.81 | B40,C45 | no |  |
| `/Game/Env/HS/FR/ACR/Canyon_A_Tower/FR_ACR_Int_Canyon_A_Tower_Pillar_w17_d17_h51_A/SM_FR_ACR_Int_Canyon_A_Tower_Pillar_w17_d17_h51_A` | StaticMesh | 13.77 | 397,908 | 16.99x16.98x51.03 | B40,C45 | no |  |
| `/Game/Env/HS/FR/ACR/Canyon_A_Tower/FR_ACR_Int_Canyon_A_Tower_Pillar_w17_d18_h37_A/SM_FR_ACR_Int_Canyon_A_Tower_Pillar_w17_d18_h37_A` | StaticMesh | 6.18 | 135,651 | 16.51x18.0x37.75 | B40,C45 | no |  |
| `/Game/Env/HS/FR/ACR/Canyon_A_Tower/FR_ACR_Int_Canyon_A_Tower_Pillar_w17_d18_h38_A/SM_FR_ACR_Int_Canyon_A_Tower_Pillar_w17_d18_h38_A` | StaticMesh | 8.76 | 182,996 | 16.51x18.0x37.65 | B40,C45 | no |  |
| `/Game/Env/HS/FR/ACR/Canyon_A_Tower/FR_ACR_Int_Canyon_A_Tower_Pillar_w17_d18_h40_A/SM_FR_ACR_Int_Canyon_A_Tower_Pillar_w17_d18_h40_A` | StaticMesh | 12.60 | 257,608 | 16.77x18.01x39.75 | B40,C45 | no |  |
| `/Game/Env/HS/FR/ACR/Canyon_A_Tower/FR_ACR_Int_Canyon_A_Tower_Pillar_w20_d6_h37_A/SM_FR_ACR_Int_Canyon_A_Tower_Pillar_w20_d6_h37_A` | StaticMesh | 7.91 | 149,813 | 19.83x6.01x36.69 | B40,C45 | no |  |
| `/Game/Env/HS/FR/ACR/Canyon_A_Tower/FR_ACR_Int_Canyon_A_Tower_Pillar_w20_d6_h39_A/SM_FR_ACR_Int_Canyon_A_Tower_Pillar_w20_d6_h39_A` | StaticMesh | 8.13 | 154,757 | 19.73x6.05x39.23 | B40,C45 | no |  |
| `/Game/Env/HS/FR/ACR/Canyon_A_Tower/FR_ACR_Int_Canyon_A_Tower_Pillar_w20_d70_h43_A/SM_FR_ACR_Int_Canyon_A_Tower_Pillar_w20_d70_h43_A` | StaticMesh | 8.76 | 172,629 | 19.67x70.4x50.23 | B40,C45 | no |  |
| `/Game/Env/HS/FR/ACR/Canyon_A_Tower/FR_ACR_Int_Canyon_A_Tower_Pillar_w22_d18_h39_A/SM_FR_ACR_Int_Canyon_A_Tower_Pillar_w22_d18_h39_A` | StaticMesh | 8.16 | 166,214 | 22.17x18.0x39.44 | B40,C45 | no |  |
| `/Game/Env/HS/FR/ACR/Canyon_A_Tower/FR_ACR_Int_Canyon_A_Tower_Pillar_w25_d8_h36_A/SM_FR_ACR_Int_Canyon_A_Tower_Pillar_w25_d8_h36_A` | StaticMesh | 10.91 | 232,683 | 24.72x8.34x36.3 | B40,C45 | no |  |
| `/Game/Env/HS/FR/ACR/Canyon_A_Tower/FR_ACR_Int_Canyon_A_Tower_Pillar_w27_d13_h39_A/SM_FR_ACR_Int_Canyon_A_Tower_Pillar_w27_d13_h39_A` | StaticMesh | 7.91 | 148,227 | 26.88x12.85x39.24 | B40,C45 | no |  |
| `/Game/Env/HS/FR/ACR/Canyon_A_Tower/FR_ACR_Int_Canyon_A_Tower_Pillar_w28_d25_h21_A/SM_FR_ACR_Int_Canyon_A_Tower_Pillar_w28_d25_h21_A` | StaticMesh | 22.77 | 447,658 | 28.83x24.93x21.66 | B40,C45 | no | very dense: confirm Nanite before placing many |
| `/Game/Env/HS/FR/ACR/Canyon_A_Tower/FR_ACR_Int_Canyon_A_Tower_Pillar_w30_d30_h60_A/SM_FR_ACR_Int_Canyon_A_Tower_Pillar_w30_d30_h60_A` | StaticMesh | 11.62 | 290,935 | 30.36x30.36x59.73 | B40,C45 | no |  |
| `/Game/Env/HS/FR/ACR/Canyon_A_Tower/FR_ACR_Int_Canyon_A_Tower_Pillar_w35_d25_h28_A/SM_FR_ACR_Int_Canyon_A_Tower_Pillar_w35_d25_h28_A` | StaticMesh | 20.92 | 408,669 | 35.66x24.93x28.53 | B40,C45 | no | very dense: confirm Nanite before placing many |
| `/Game/Env/HS/FR/ACR/Canyon_A_Tower/FR_ACR_Int_Canyon_A_Tower_Pillar_w39_d16_h14_A/SM_FR_ACR_Int_Canyon_A_Tower_Pillar_w39_d16_h14_A` | StaticMesh | 4.45 | 91,031 | 39.29x16.18x14.12 | B40,C45 | no |  |
| `/Game/Env/HS/FR/ACR/Canyon_A_Tower/FR_ACR_Int_Canyon_A_Tower_Pillar_w39_d18_h18_A/SM_FR_ACR_Int_Canyon_A_Tower_Pillar_w39_d18_h18_A` | StaticMesh | 2.82 | 62,353 | 38.79x18.01x17.94 | B40,C45 | no |  |
| `/Game/Env/HS/FR/ACR/Canyon_A_Tower/FR_ACR_Int_Canyon_A_Tower_Pillar_w39_d18_h39_A/SM_FR_ACR_Int_Canyon_A_Tower_Pillar_w39_d18_h39_A` | StaticMesh | 2.43 | 46,278 | 38.8x18.03x38.84 | B40,C45 | no |  |
| `/Game/Env/HS/FR/ACR/Canyon_A_Tower/FR_ACR_Int_Canyon_A_Tower_Pillar_w8_d19_h28_A/SM_FR_ACR_Int_Canyon_A_Tower_Pillar_w8_d19_h28_A` | StaticMesh | 18.04 | 346,412 | 8.14x18.61x27.64 | B40,C45 | no |  |
| `/Game/Env/HS/FR/ACR/Canyon_A_Tower/FR_ACR_Int_Canyon_A_Tower_Platform_w19_d39_h6_A/SM_FR_ACR_Int_Canyon_A_Tower_Platform_w19_d39_h6_A` | StaticMesh | 8.41 | 156,194 | 18.8x39.32x6.0 | B40,C45 | no |  |
| `/Game/Env/HS/FR/ACR/Canyon_A_Tower/FR_ACR_Int_Canyon_A_Tower_Platform_w20_d22_h0i3_A/SM_FR_ACR_Int_Canyon_A_Tower_Platform_w20_d22_h0i3_A` | StaticMesh | 2.15 | 47,658 | 19.42x21.87x0.32 | B40,C45 | no |  |
| `/Game/Env/HS/FR/ACR/Canyon_A_Tower/FR_ACR_Int_Canyon_A_Tower_Platform_w24_d17_h0i4_A/SM_FR_ACR_Int_Canyon_A_Tower_Platform_w24_d17_h0i4_A` | StaticMesh | 4.25 | 107,142 | 23.44x16.69x0.39 | B40,C45 | no |  |
| `/Game/Env/HS/FR/ACR/Canyon_A_Tower/FR_ACR_Int_Canyon_A_Tower_Platform_w24_d22_h0i3_A/SM_FR_ACR_Int_Canyon_A_Tower_Platform_w24_d22_h0i3_A` | StaticMesh | 2.69 | 61,210 | 23.98x21.6x0.31 | B40,C45 | no |  |
| `/Game/Env/HS/FR/ACR/Canyon_A_Tower/FR_ACR_Int_Canyon_A_Tower_Platform_w24_d39_h0i5_A/SM_FR_ACR_Int_Canyon_A_Tower_Platform_w24_d39_h0i5_A` | StaticMesh | 3.10 | 73,580 | 23.51x38.64x0.45 | B40,C45 | no |  |
| `/Game/Env/HS/FR/ACR/Canyon_A_Tower/FR_ACR_Int_Canyon_A_Tower_Platform_w25_d28_h0i3_A/SM_FR_ACR_Int_Canyon_A_Tower_Platform_w25_d28_h0i3_A` | StaticMesh | 3.32 | 67,836 | 24.16x27.74x0.3 | B40,C45 | no |  |
| `/Game/Env/HS/FR/ACR/Canyon_A_Tower/FR_ACR_Int_Canyon_A_Tower_Platform_w25_d33_h0i3_A/SM_FR_ACR_Int_Canyon_A_Tower_Platform_w25_d33_h0i3_A` | StaticMesh | 2.42 | 54,844 | 24.51x32.43x0.3 | B40,C45 | no |  |
| `/Game/Env/HS/FR/ACR/Canyon_A_Tower/FR_ACR_Int_Canyon_A_Tower_Platform_w26_d28_h0i3_A/SM_FR_ACR_Int_Canyon_A_Tower_Platform_w26_d28_h0i3_A` | StaticMesh | 3.32 | 68,148 | 25.37x27.28x0.31 | B40,C45 | no |  |
| `/Game/Env/HS/FR/ACR/Canyon_A_Tower/FR_ACR_Int_Canyon_A_Tower_Platform_w28_d32_h0i3_A/SM_FR_ACR_Int_Canyon_A_Tower_Platform_w28_d32_h0i3_A` | StaticMesh | 1.88 | 39,209 | 27.33x31.92x0.31 | B40,C45 | no |  |
| `/Game/Env/HS/FR/ACR/Canyon_A_Tower/FR_ACR_Int_Canyon_A_Tower_Platform_w30_d28_h0i3_A/SM_FR_ACR_Int_Canyon_A_Tower_Platform_w30_d28_h0i3_A` | StaticMesh | 2.37 | 46,174 | 29.71x27.81x0.3 | B40,C45 | no |  |
| `/Game/Env/HS/FR/ACR/Canyon_A_Tower/FR_ACR_Int_Canyon_A_Tower_Platform_w30_d36_h12_A/SM_FR_ACR_Int_Canyon_A_Tower_Platform_w30_d36_h12_A` | StaticMesh | 1.96 | 42,762 | 30.06x36.39x11.7 | B40,C45 | no |  |
| `/Game/Env/HS/FR/ACR/Canyon_A_Tower/FR_ACR_Int_Canyon_A_Tower_Platform_w33_d35_h0i3_A/SM_FR_ACR_Int_Canyon_A_Tower_Platform_w33_d35_h0i3_A` | StaticMesh | 2.22 | 45,830 | 32.75x34.55x0.31 | B40,C45 | no |  |
| `/Game/Env/HS/FR/ACR/Canyon_A_Tower/FR_ACR_Int_Canyon_A_Tower_Platform_w34_d36_h12_A/SM_FR_ACR_Int_Canyon_A_Tower_Platform_w34_d36_h12_A` | StaticMesh | 4.65 | 91,534 | 34.26x35.58x11.51 | B40,C45 | no |  |
| `/Game/Env/HS/FR/ACR/Canyon_A_Tower/FR_ACR_Int_Canyon_A_Tower_Platform_w34_d39_h12_A/SM_FR_ACR_Int_Canyon_A_Tower_Platform_w34_d39_h12_A` | StaticMesh | 7.07 | 163,606 | 34.45x39.46x11.51 | B40,C45 | no |  |
| `/Game/Env/HS/FR/ACR/Canyon_A_Tower/FR_ACR_Int_Canyon_A_Tower_Platform_w34_d39_h1_A/SM_FR_ACR_Int_Canyon_A_Tower_Platform_w34_d39_h1_A` | StaticMesh | 3.69 | 64,699 | 34.12x38.35x1.05 | B40,C45 | no |  |
| `/Game/Env/HS/FR/ACR/Canyon_A_Tower/FR_ACR_Int_Canyon_A_Tower_Platform_w37_d36_h13_A/SM_FR_ACR_Int_Canyon_A_Tower_Platform_w37_d36_h13_A` | StaticMesh | 2.52 | 53,800 | 37.13x36.45x12.74 | B40,C45 | no |  |
| `/Game/Env/HS/FR/ACR/Canyon_A_Tower/FR_ACR_Int_Canyon_A_Tower_Platform_w38_d39_d11_A/SM_FR_ACR_Int_Canyon_A_Tower_Platform_w38_d39_d11_A` | StaticMesh | 5.59 | 133,552 | 38.42x39.4x11.0 | B40,C45 | no |  |
| `/Game/Env/HS/FR/ACR/Canyon_A_Tower/FR_ACR_Int_Canyon_A_Tower_Platform_w38_d39_h13_A/SM_FR_ACR_Int_Canyon_A_Tower_Platform_w38_d39_h13_A` | StaticMesh | 1.66 | 30,365 | 37.9x38.71x12.74 | B40,C45 | no |  |
| `/Game/Env/HS/FR/ACR/Canyon_A_Tower/FR_ACR_Int_Canyon_A_Tower_Platform_w39_d39_h1_A/SM_FR_ACR_Int_Canyon_A_Tower_Platform_w39_d39_h1_A` | StaticMesh | 6.32 | 171,511 | 36.95x39.2x1.05 | B40,C45 | no |  |
| `/Game/Env/HS/FR/ACR/Canyon_A_Tower/FR_ACR_Int_Canyon_A_Tower_Platform_w39_d40_h12_A/SM_FR_ACR_Int_Canyon_A_Tower_Platform_w39_d40_h12_A` | StaticMesh | 8.06 | 170,867 | 39.41x39.55x11.99 | B40,C45 | no |  |
| `/Game/Env/HS/FR/ACR/Canyon_A_Tower/FR_ACR_Int_Canyon_A_Tower_Wall_w20_d6_h40_A/SM_FR_ACR_Int_Canyon_A_Tower_Wall_w20_d6_h40_A` | StaticMesh | 2.57 | 44,327 | 20.3x5.47x39.33 | B40,C45 | no |  |
| `/Game/Env/HS/FR/ACR/Canyon_A_Tower/FR_ACR_Int_Canyon_A_Tower_Wall_w20_d6_h40_B/SM_FR_ACR_Int_Canyon_A_Tower_Wall_w20_d6_h40_B` | StaticMesh | 2.46 | 39,457 | 20.3x4.87x35.29 | B40,C45 | no |  |
| `/Game/Env/HS/FR/ACR/Canyon_A_Tower/FR_ACR_Int_Canyon_A_Tower_Wall_w20_d6_h40_C/SM_FR_ACR_Int_Canyon_A_Tower_Wall_w20_d6_h40_C` | StaticMesh | 1.77 | 32,614 | 20.3x4.87x37.54 | B40,C45 | no |  |
| `/Game/Env/HS/FR/ACR/Canyon_A_Tower/FR_ACR_Int_Canyon_A_Tower_Wall_w20i5_d8_h30_A/SM_FR_ACR_Int_Canyon_A_Tower_Wall_w20i5_d8_h30_A` | StaticMesh | 3.39 | 69,829 | 12.81x69.34x90.51 | B40,C45 | no |  |
| `/Game/Env/HS/FR/ACR/Canyon_A_Tower/FR_ACR_Int_Canyon_A_Tower_Wall_w30_d2_h30_A/SM_FR_ACR_Int_Canyon_A_Tower_Wall_w30_d2_h30_A` | StaticMesh | 5.31 | 103,428 | 12.8x69.19x94.56 | B40,C45 | no |  |
| `/Game/Env/HS/FR/ACR/Canyon_A_Tower/FR_ACR_Int_Canyon_A_Tower_Wall_w34_d7_h32_A/SM_FR_ACR_Int_Canyon_A_Tower_Wall_w34_d7_h32_A` | StaticMesh | 1.44 | 29,648 | 34.67x7.01x61.19 | B40,C45 | no |  |
| `/Game/Env/HS/FR/ACR/Canyon_A_Tower/FR_ACR_Int_Canyon_A_Tower_Wall_w34_d7_h32_B/SM_FR_ACR_Int_Canyon_A_Tower_Wall_w34_d7_h32_B` | StaticMesh | 2.18 | 44,668 | 34.68x7.02x46.46 | B40,C45 | no |  |
| `/Game/Env/HS/FR/ACR/Canyon_A_Tower/FR_ACR_Int_Canyon_A_Tower_Wall_w34_d7_h32_C/SM_FR_ACR_Int_Canyon_A_Tower_Wall_w34_d7_h32_C` | StaticMesh | 2.32 | 44,278 | 34.68x7.02x35.86 | B40,C45 | no |  |
| `/Game/Env/HS/FR/ACR/Canyon_A_Tower/FR_ACR_Int_Canyon_A_Tower_Wall_w37_d30_h87_A/SM_FR_ACR_Int_Canyon_A_Tower_Wall_w37_d30_h87_A` | StaticMesh | 3.42 | 63,448 | 28.82x58.45x111.0 | B40,C45 | no |  |
| `/Game/Env/HS/FR/ACR/Canyon_A_Tower/FR_ACR_Int_Canyon_A_Tower_Wall_w40_d42_h87_A/SM_FR_ACR_Int_Canyon_A_Tower_Wall_w40_d42_h87_A` | StaticMesh | 3.33 | 71,047 | 35.2x58.53x111.04 | B40,C45 | no |  |
| `/Game/Env/HS/FR/ACR/Canyon_A_Tower/FR_ACR_Int_Canyon_A_Tower_Wall_w5_d38_h39_A/SM_FR_ACR_Int_Canyon_A_Tower_Wall_w5_d38_h39_A` | StaticMesh | 3.78 | 81,996 | 5.27x37.79x39.4 | B40,C45 | no |  |
| `/Game/Env/HS/FR/ACR/Canyon_A_Tower/FR_ACR_Int_Canyon_A_Tower_Wall_w6_d28_h37_A/SM_FR_ACR_Int_Canyon_A_Tower_Wall_w6_d28_h37_A` | StaticMesh | 11.46 | 255,198 | 6.4x27.58x37.32 | B40,C45 | no |  |
| `/Game/Env/HS/FR/ACR/Canyon_A_Tower/FR_ACR_Int_Canyon_A_Tower_Wall_w6_d30_h37_A/SM_FR_ACR_Int_Canyon_A_Tower_Wall_w6_d30_h37_A` | StaticMesh | 3.57 | 73,040 | 6.36x30.67x36.76 | B40,C45 | no |  |
| `/Game/Env/HS/FR/ACR/Canyon_A_Tower/FR_ACR_Int_Canyon_A_Tower_Wall_w6_d35_h37_A/SM_FR_ACR_Int_Canyon_A_Tower_Wall_w6_d35_h37_A` | StaticMesh | 2.33 | 49,757 | 6.07x34.7x37.46 | B40,C45 | no |  |
| `/Game/Env/HS/FR/ACR/Canyon_A_Tower/FR_ACR_Int_Canyon_A_Tower_Wall_w6_d35_h38_A/SM_FR_ACR_Int_Canyon_A_Tower_Wall_w6_d35_h38_A` | StaticMesh | 4.58 | 99,011 | 6.2x34.67x38.15 | B40,C45 | no |  |
| `/Game/Env/HS/FR/ACR/Canyon_A_Tower/FR_ACR_Int_Canyon_A_Tower_Wall_w7_d20_h38_A/SM_FR_ACR_Int_Canyon_A_Tower_Wall_w7_d20_h38_A` | StaticMesh | 5.03 | 115,425 | 7.45x20.31x38.07 | B40,C45 | no |  |
| `/Game/Env/HS/FR/ACR/Canyon_A_Tower/FR_ACR_Int_Canyon_A_Tower_Wall_w7_d20_h39_A/SM_FR_ACR_Int_Canyon_A_Tower_Wall_w7_d20_h39_A` | StaticMesh | 5.69 | 126,633 | 7.45x20.3x39.42 | B40,C45 | no |  |
| `/Game/Env/HS/FR/ACR/Canyon_A_Tower/FR_ACR_Int_Canyon_A_Tower_Wall_w7_d28_h39_A/SM_FR_ACR_Int_Canyon_A_Tower_Wall_w7_d28_h39_A` | StaticMesh | 4.09 | 91,478 | 6.65x27.75x39.42 | B40,C45 | no |  |
| `/Game/Env/HS/FR/ACR/Cave_B_Bunker/FR_ACR_Cave_B_Bunker_Base_w20_d13_h8_A/SM_FR_ACR_Cave_B_Bunker_Base_w20_d13_h8_A` | StaticMesh | 13.51 | 321,338 | 13.39x20.35x8.24 | B40,C20,C45 | no |  |
| `/Game/Env/HS/FR/ACR/Cave_B_Bunker/FR_ACR_Cave_B_Bunker_Base_w27_d13_h13_A/SM_FR_ACR_Cave_B_Bunker_Base_w27_d13_h13_A` | StaticMesh | 14.94 | 333,180 | 13.09x27.3x13.59 | B40,C20,C45 | no |  |
| `/Game/Env/HS/FR/ACR/Cave_B_Bunker/FR_ACR_Cave_B_Bunker_Door_w2_d9_h16_A/SM_FR_ACR_Cave_B_Bunker_Door_w2_d9_h16_A` | StaticMesh | 6.27 | 129,659 | 6.48x14.34x19.0 | B40,C45 | no |  |
| `/Game/Env/HS/FR/ACR/Cave_B_Bunker/FR_ACR_Cave_B_Bunker_Floor_w30_d28_h1_A/SM_FR_ACR_Cave_B_Bunker_Floor_w30_d28_h1_A` | StaticMesh | 6.17 | 152,448 | 30.0x28.01x1.02 | B40,C45 | no |  |
| `/Game/Env/HS/FR/ACR/Cave_B_Bunker/FR_ACR_Cave_B_Bunker_Floor_w30_d30_h1_A/SM_FR_ACR_Cave_B_Bunker_Floor_w30_d30_h1_A` | StaticMesh | 5.15 | 131,420 | 30.0x30.53x1.01 | B40,C45 | no |  |
| `/Game/Env/HS/FR/ACR/Cave_B_Bunker/FR_ACR_Cave_B_Bunker_Wall_w1_d28_h17_A/SM_FR_ACR_Cave_B_Bunker_Wall_w1_d28_h17_A` | StaticMesh | 5.43 | 136,668 | 1.29x28.01x16.42 | B40,C45 | no |  |
| `/Game/Env/HS/FR/ACR/Cave_B_Bunker/FR_ACR_Cave_B_Bunker_Wall_w1_d30_h12_A/SM_FR_ACR_Cave_B_Bunker_Wall_w1_d30_h12_A` | StaticMesh | 3.30 | 76,939 | 1.6x29.99x12.03 | B40,C45 | no |  |
| `/Game/Env/HS/FR/ACR/Cave_B_Bunker/FR_ACR_Cave_B_Bunker_Wall_w1_d30_h17_A/SM_FR_ACR_Cave_B_Bunker_Wall_w1_d30_h17_A` | StaticMesh | 5.02 | 112,101 | 1.09x30.5x16.42 | B40,C45 | no |  |
| `/Game/Env/HS/FR/ACR/Cave_B_Bunker/FR_ACR_Cave_B_Bunker_Wall_w1_d8_h12_A/SM_FR_ACR_Cave_B_Bunker_Wall_w1_d8_h12_A` | StaticMesh | 1.52 | 29,985 | 0.5x7.93x12.0 | B40,C45 | no |  |
| `/Game/Env/HS/FR/ACR/Cave_B_Tarmac/FR_ACR_Ext_Cave_B_Tarmac_Floor_Top_A/SM_FR_ACR_Ext_Cave_B_Tarmac_Floor_Top_A` | StaticMesh | 4.33 | 131,663 | 81.3x81.48x0.32 | B40,C45 | no |  |
| `/Game/Env/HS/FR/ACR/Cave_B_Tarmac/FR_ACR_Ext_Cave_B_Tarmac_Floor_w17i5_d41i5_h2_A/SM_FR_ACR_Ext_Cave_B_Tarmac_Floor_w17i5_d41i5_h2_A` | StaticMesh | 6.98 | 132,419 | 17.5x41.38x2.55 | B40,C45 | no |  |
| `/Game/Env/HS/FR/ACR/Cave_B_Tarmac/FR_ACR_Ext_Cave_B_Tarmac_Floor_w5_d2_h1_A/SM_FR_ACR_Ext_Cave_B_Tarmac_Floor_w5_d2_h1_A` | StaticMesh | 1.42 | 40,550 | 4.6x2.0x0.5 | B40,C45 | no |  |
| `/Game/Env/HS/FR/ACR/Cave_B_Tarmac/FR_ACR_Ext_Cave_B_Tarmac_Pillar_w10_d14_h20i5_A/SM_FR_ACR_Ext_Cave_B_Tarmac_Pillar_w10_d14_h20i5_A` | StaticMesh | 3.93 | 90,747 | 6.54x12.0x26.84 | B40,C45 | no |  |
| `/Game/Env/HS/FR/ACR/Cave_B_Tarmac/FR_ACR_Ext_Cave_B_Tarmac_Pillar_w10_d14_h23i5_A/SM_FR_ACR_Ext_Cave_B_Tarmac_Pillar_w10_d14_h23i5_A` | StaticMesh | 3.36 | 72,757 | 6.54x12.0x26.81 | B40,C45 | no |  |
| `/Game/Env/HS/FR/ACR/Cave_B_Tarmac/FR_ACR_Ext_Cave_B_Tarmac_Pillar_w10_d14_h60i5_A/SM_FR_ACR_Ext_Cave_B_Tarmac_Pillar_w10_d14_h60i5_A` | StaticMesh | 14.87 | 320,264 | 10.17x14.8x18.11 | B40,C20,C45 | no |  |
| `/Game/Env/HS/FR/ACR/Cave_B_Tarmac/FR_ACR_Ext_Cave_B_Tarmac_Trim_Top_A/SM_FR_ACR_Ext_Cave_B_Tarmac_Trim_Top_A` | StaticMesh | 2.03 | 62,112 | 83.79x41.76x26.01 | B40,C45 | no |  |
| `/Game/Env/HS/FR/ACR/Cave_B_Tarmac/FR_ACR_Ext_Cave_B_Tarmac_Wall_Massive_A/SM_FR_ACR_Ext_Cave_B_Tarmac_Wall_Massive_A` | StaticMesh | 3.89 | 126,728 | 18.9x38.37x111.17 | B40,C45 | no |  |
| `/Game/Env/HS/FR/ACR/Cave_B_Tarmac/FR_ACR_Ext_Cave_B_Tarmac_Wall_Massive_B/SM_FR_ACR_Ext_Cave_B_Tarmac_Wall_Massive_B` | StaticMesh | 2.23 | 63,823 | 48.42x23.42x133.04 | B40,C45 | no |  |
| `/Game/Env/HS/FR/ACR/Cave_B_Tarmac/FR_ACR_Ext_Cave_B_Tarmac_Wall_w10_d34_h10i5_A/SM_FR_ACR_Ext_Cave_B_Tarmac_Wall_w10_d34_h10i5_A` | StaticMesh | 1.71 | 30,930 | 18.79x41.02x10.24 | B40,C45 | no |  |
| `/Game/Env/HS/FR/ACR/Cave_B_Tarmac/FR_ACR_Ext_Cave_B_Tarmac_Wall_w10i5_d18i5_h167_A/SM_FR_ACR_Ext_Cave_B_Tarmac_Wall_w10i5_d18i5_h167_A` | StaticMesh | 6.18 | 121,475 | 5.97x17.48x109.78 | B40,C45 | no |  |
| `/Game/Env/HS/FR/ACR/Cave_B_Tarmac/FR_ACR_Ext_Cave_B_Tarmac_Wall_w10i5_d18i5_h29_A/SM_FR_ACR_Ext_Cave_B_Tarmac_Wall_w10i5_d18i5_h29_A` | StaticMesh | 4.19 | 87,229 | 10.79x16.59x31.28 | B40,C45 | no |  |
| `/Game/Env/HS/FR/ACR/Cave_B_Tarmac/FR_ACR_Ext_Cave_B_Tarmac_Wall_w10i5_d18i5_h29i5_A/SM_FR_ACR_Ext_Cave_B_Tarmac_Wall_w10i5_d18i5_h29i5_A` | StaticMesh | 7.17 | 166,147 | 5.01x17.7x30.45 | B40,C45 | no |  |
| `/Game/Env/HS/FR/ACR/Cave_B_Tarmac/FR_ACR_Ext_Cave_B_Tarmac_Wall_w29i5_d21i5_h22i5_A/SM_FR_ACR_Ext_Cave_B_Tarmac_Wall_w29i5_d21i5_h22i5_A` | StaticMesh | 4.22 | 77,334 | 21.11x35.2x22.18 | B40,C45 | no |  |
| `/Game/Env/HS/FR/ACR/Cave_B_Tarmac/FR_ACR_Ext_Cave_B_Tarmac_Wall_w2_d22i5_h35_A/SM_FR_ACR_Ext_Cave_B_Tarmac_Wall_w2_d22i5_h35_A` | StaticMesh | 5.72 | 118,374 | 4.65x24.93x37.22 | B40,C45 | no |  |
| `/Game/Env/HS/FR/ACR/Cave_B_Tarmac/FR_ACR_Ext_Cave_B_Tarmac_Wall_w2_d25i5_h45_A/SM_FR_ACR_Ext_Cave_B_Tarmac_Wall_w2_d25i5_h45_A` | StaticMesh | 1.17 | 25,615 | 3.06x29.5x51.48 | B40,C45 | no |  |
| `/Game/Env/HS/FR/ACR/Cave_B_Tarmac/FR_ACR_Ext_Cave_B_Tarmac_Wall_w8i5_d21i5_h178_A/SM_FR_ACR_Ext_Cave_B_Tarmac_Wall_w8i5_d21i5_h178_A` | StaticMesh | 5.82 | 110,968 | 19.94x12.48x133.03 | B40,C45 | no |  |
| `/Game/Env/HS/FR/ACR/Cave_B_Tarmac/FR_ACR_Ext_Cave_B_Tarmac_Wall_w8i5_d21i5_h29_A/SM_FR_ACR_Ext_Cave_B_Tarmac_Wall_w8i5_d21i5_h29_A` | StaticMesh | 5.00 | 103,239 | 22.35x15.06x29.24 | B40,C45 | no |  |
| `/Game/Env/HS/FR/ACR/Cave_B_Tarmac/FR_ACR_Ext_Cave_B_Tarmac_Wall_w8i5_d21i5_h29i5_A/SM_FR_ACR_Ext_Cave_B_Tarmac_Wall_w8i5_d21i5_h29i5_A` | StaticMesh | 5.33 | 103,919 | 22.35x12.24x29.53 | B40,C45 | no |  |
| `/Game/Env/HS/FR/ACR/Cave_B_Tarmac/FR_ACR_Ext_Cave_B_Tarmac_Wall_w9_d33i5_h68i5_A/SM_FR_ACR_Ext_Cave_B_Tarmac_Wall_w9_d33i5_h68i5_A` | StaticMesh | 1.76 | 35,953 | 7.42x34.93x67.76 | B40,C45 | no |  |
| `/Game/Env/HS/FR/ACR/Cave_B_Tarmac/FR_ACR_Int_Cave_B_Tarmac_Ceiling_w36_d23i5_h1_A/SM_FR_ACR_Int_Cave_B_Tarmac_Ceiling_w36_d23i5_h1_A` | StaticMesh | 1.46 | 45,008 | 36.16x23.21x1.12 | B40,C45 | no |  |
| `/Game/Env/HS/FR/ACR/Cave_B_Tarmac/FR_ACR_Int_Cave_B_Tarmac_Floor_w24_d17i5_h1_A/SM_FR_ACR_Int_Cave_B_Tarmac_Floor_w24_d17i5_h1_A` | StaticMesh | 2.62 | 68,476 | 23.88x18.77x1.25 | B40,C45 | no |  |
| `/Game/Env/HS/FR/ACR/Cave_B_Tarmac/FR_ACR_Int_Cave_B_Tarmac_Floor_w36_d23i5_h1_A/SM_FR_ACR_Int_Cave_B_Tarmac_Floor_w36_d23i5_h1_A` | StaticMesh | 6.77 | 179,508 | 18.48x22.7x1.25 | B40,C45 | no |  |
| `/Game/Env/HS/FR/ACR/Cave_B_Tarmac/FR_ACR_Int_Cave_B_Tarmac_Wall_w1_d12_h182_A/SM_FR_ACR_Int_Cave_B_Tarmac_Wall_w1_d12_h182_A` | StaticMesh | 2.50 | 53,174 | 1.55x11.96x129.14 | B40,C45 | no |  |
| `/Game/Env/HS/FR/ACR/Cave_B_Tarmac/FR_ACR_Int_Cave_B_Tarmac_Wall_w1_d12_h29_A/SM_FR_ACR_Int_Cave_B_Tarmac_Wall_w1_d12_h29_A` | StaticMesh | 2.98 | 93,503 | 2.72x11.98x29.7 | B40,C45 | no |  |
| `/Game/Env/HS/FR/ACR/Cave_B_Tarmac/FR_ACR_Int_Cave_B_Tarmac_Wall_w1_d12_h29i5_A/SM_FR_ACR_Int_Cave_B_Tarmac_Wall_w1_d12_h29i5_A` | StaticMesh | 4.15 | 93,582 | 1.55x11.96x29.67 | B40,C45 | no |  |
| `/Game/Env/HS/FR/ACR/Cave_B_Tarmac/FR_ACR_Int_Cave_B_Tarmac_Wall_w1_d15_h182_A/SM_FR_ACR_Int_Cave_B_Tarmac_Wall_w1_d15_h182_A` | StaticMesh | 2.04 | 42,446 | 1.55x14.78x129.14 | B40,C45 | no |  |
| `/Game/Env/HS/FR/ACR/Cave_B_Tarmac/FR_ACR_Int_Cave_B_Tarmac_Wall_w1_d15_h29_A/SM_FR_ACR_Int_Cave_B_Tarmac_Wall_w1_d15_h29_A` | StaticMesh | 6.46 | 142,831 | 2.55x14.8x29.7 | B40,C45 | no |  |
| `/Game/Env/HS/FR/ACR/Cave_B_Tarmac/FR_ACR_Int_Cave_B_Tarmac_Wall_w1_d15_h30_A/SM_FR_ACR_Int_Cave_B_Tarmac_Wall_w1_d15_h30_A` | StaticMesh | 3.82 | 89,889 | 1.55x14.78x29.67 | B40,C45 | no |  |
| `/Game/Env/HS/FR/ACR/Cave_B_Tarmac/FR_ACR_Int_Cave_B_Tarmac_Wall_w1_d26_h116_A/SM_FR_ACR_Int_Cave_B_Tarmac_Wall_w1_d26_h116_A` | StaticMesh | 2.69 | 51,688 | 1.45x26.02x115.82 | B40,C45 | no |  |
| `/Game/Env/HS/FR/ACR/Cave_B_Tarmac/FR_ACR_Int_Cave_B_Tarmac_Wall_w1_d26_h26_A/SM_FR_ACR_Int_Cave_B_Tarmac_Wall_w1_d26_h26_A` | StaticMesh | 2.99 | 60,550 | 1.61x26.01x26.15 | B40,C45 | no |  |
| `/Game/Env/HS/FR/ACR/Cave_B_Tarmac/FR_ACR_Int_Cave_B_Tarmac_Wall_w1_d26_h28i5_A/SM_FR_ACR_Int_Cave_B_Tarmac_Wall_w1_d26_h28i5_A` | StaticMesh | 3.65 | 81,403 | 1.42x26.01x28.58 | B40,C45 | no |  |
| `/Game/Env/HS/FR/ACR/Cave_B_Tarmac/FR_ACR_Int_Cave_B_Tarmac_Wall_w1_d27i5_h182_A/SM_FR_ACR_Int_Cave_B_Tarmac_Wall_w1_d27i5_h182_A` | StaticMesh | 6.63 | 163,062 | 2.0x26.02x29.5 | B40,C45 | no |  |
| `/Game/Env/HS/FR/ACR/Cave_B_Tarmac/FR_ACR_Int_Cave_B_Tarmac_Wall_w20_d3i5_h23_A/SM_FR_ACR_Int_Cave_B_Tarmac_Wall_w20_d3i5_h23_A` | StaticMesh | 2.28 | 57,937 | 17.41x3.52x21.5 | B40,C45 | no |  |
| `/Game/Env/HS/FR/ACR/Cave_B_Tarmac/FR_ACR_Int_Cave_B_Tarmac_Wall_w6_d30_h125_A/SM_FR_ACR_Int_Cave_B_Tarmac_Wall_w6_d30_h125_A` | StaticMesh | 10.92 | 203,403 | 21.83x23.11x125.25 | B40,C45 | no |  |
| `/Game/Env/HS/FR/ACR/Cave_B_Tarmac/FR_ACR_Int_Cave_B_Tarmac_Wall_w6_d30_h29_A/SM_FR_ACR_Int_Cave_B_Tarmac_Wall_w6_d30_h29_A` | StaticMesh | 13.01 | 256,075 | 21.83x23.11x29.55 | B40,C45 | no |  |
| `/Game/Env/HS/FR/ACR/Cave_B_Tarmac/FR_ACR_Int_Cave_B_Tarmac_Wall_w6i5_d33_h182_A/SM_FR_ACR_Int_Cave_B_Tarmac_Wall_w6i5_d33_h182_A` | StaticMesh | 17.37 | 391,025 | 21.83x23.11x30.0 | B40,C45 | no |  |
| `/Game/Env/HS/FR/HAL/Ext_Bridge_A_Crash_Site/+PLA/BPP_PLA_FR_HAL_Ext_Bridge_Crashsite_A` | Blueprint | 0.06 |  |  |  | no |  |
| `/Game/Env/HS/FR/HAL/Ext_Bridge_A_Crash_Site/+PLA/BPP_PLA_FR_HAL_Ext_Bridge_Crashsite_Cladding_A` | Blueprint | 0.02 |  |  |  | no |  |
| `/Game/Env/HS/FR/HAL/Ext_Bridge_A_Crash_Site/FR_HAL_Ext_Bridge_Crashsite_Abutment_Mid_Slat_cm34_w72_d80_h35_A/SM_FR_HAL_Ext_Bridge_Crashsite_Abutment_Mid_Slat_cm34_w72_d80_h35_A` | StaticMesh | 1.55 | 44,702 | 0.81x0.71x0.35 | A30 | no |  |
| `/Game/Env/HS/FR/HAL/Ext_Bridge_A_Crash_Site/FR_HAL_Ext_Bridge_Crashsite_Abutment_Mid_w34_d8_h8_A/SM_FR_HAL_Ext_Bridge_Crashsite_Abutment_Mid_w34_d8_h8_A` | StaticMesh | 0.95 | 29,625 | 33.39x8.36x7.66 | A30 | no |  |
| `/Game/Env/HS/FR/HAL/Ext_Bridge_A_Crash_Site/FR_HAL_Ext_Bridge_Crashsite_Abutment_Side_A_Clasp_cm25_w10_d375_h139_A/SM_FR_HAL_Ext_Bridge_Crashsite_Abutment_Side_A_Clasp_cm25_w10_d375_h139_A` | StaticMesh | 1.02 | 31,773 | 3.72x0.1x1.39 | A30 | no |  |
| `/Game/Env/HS/FR/HAL/Ext_Bridge_A_Crash_Site/FR_HAL_Ext_Bridge_Crashsite_Abutment_Side_A_Slats_cm45_w141_d137_h11_A/SM_FR_HAL_Ext_Bridge_Crashsite_Abutment_Side_A_Slats_cm45_w141_d137_h11_A` | StaticMesh | 1.03 | 31,097 | 1.41x1.36x0.1 | A30 | no |  |
| `/Game/Env/HS/FR/HAL/Ext_Bridge_A_Crash_Site/FR_HAL_Ext_Bridge_Crashsite_Abutment_Side_w39_d5_h8_A/SM_FR_HAL_Ext_Bridge_Crashsite_Abutment_Side_w39_d5_h8_A` | StaticMesh | 7.83 | 246,132 | 39.43x5.11x7.41 | A30 | no |  |
| `/Game/Env/HS/FR/HAL/Ext_Bridge_A_Crash_Site/FR_HAL_Ext_Bridge_Crashsite_Cladding_Top_Abutment_Mid_w28_d1_h7_A/SM_FR_HAL_Ext_Bridge_Crashsite_Cladding_Top_Abutment_Mid_w28_d1_h7_A` | StaticMesh | 0.40 | 12,466 | 27.65x7.14x0.6 | A30 | no |  |
| `/Game/Env/HS/FR/HAL/Ext_Bridge_A_Crash_Site/FR_HAL_Ext_Bridge_Crashsite_Cladding_Top_Abutment_Side_w32_d3_h2_A/SM_FR_HAL_Ext_Bridge_Crashsite_Cladding_Top_Abutment_Side_w32_d3_h2_A` | StaticMesh | 0.91 | 28,429 | 31.87x3.11x1.56 | A30 | no |  |
| `/Game/Env/HS/FR/HAL/Ext_Bridge_A_Crash_Site/FR_HAL_Ext_Bridge_Crashsite_Cladding_Top_Span_Center_Mid_w39_d4_h3_A/SM_FR_HAL_Ext_Bridge_Crashsite_Cladding_Top_Span_Center_Mid_w39_d4_h3_A` | StaticMesh | 0.83 | 25,050 | 38.96x3.75x2.47 | A30 | no |  |
| `/Game/Env/HS/FR/HAL/Ext_Bridge_A_Crash_Site/FR_HAL_Ext_Bridge_Crashsite_Cladding_Top_Span_Center_Side_w37_d2_h2_A/SM_FR_HAL_Ext_Bridge_Crashsite_Cladding_Top_Span_Center_Side_w37_d2_h2_A` | StaticMesh | 0.82 | 25,700 | 37.34x2.04x1.71 | A30 | no |  |
| `/Game/Env/HS/FR/HAL/Ext_Bridge_A_Crash_Site/FR_HAL_Ext_Bridge_Crashsite_Span_Center_Mid_w33_d4_h4_A/SM_FR_HAL_Ext_Bridge_Crashsite_Span_Center_Mid_w33_d4_h4_A` | StaticMesh | 3.03 | 95,348 | 32.91x3.75x3.85 | A30 | no |  |
| `/Game/Env/HS/FR/HAL/Ext_Bridge_A_Crash_Site/FR_HAL_Ext_Bridge_Crashsite_Span_Center_Side_w32_d3_h4_A/SM_FR_HAL_Ext_Bridge_Crashsite_Span_Center_Side_w32_d3_h4_A` | StaticMesh | 4.71 | 147,261 | 31.3x2.53x3.81 | A30 | no |  |
| `/Game/Env/HS/FR/HAL/Ext_Unnatural_Cave/FR_HAL_Ext_Unnatural_Cave_Bridge_w30_d20_h07_A/SM_FR_HAL_Ext_Unnatural_Cave_Bridge_w30_d20_h07_A` | StaticMesh | 1.82 | 56,176 | 30.02x20.47x7.0 | A30 | no |  |
| `/Game/Env/HS/FR/HAL/Ext_Unnatural_Cave/FR_HAL_Ext_Unnatural_Cave_Bridge_w30_d20_h07_B/SM_FR_HAL_Ext_Unnatural_Cave_Bridge_w30_d20_h07_B` | StaticMesh | 1.64 | 50,533 | 30.01x20.36x7.0 | A30 | no |  |
| `/Game/Env/HS/FR/HAL/Ext_Unnatural_Cave/FR_HAL_Ext_Unnatural_Cave_Bridge_w30_d20_h07_C/SM_FR_HAL_Ext_Unnatural_Cave_Bridge_w30_d20_h07_C` | StaticMesh | 1.88 | 57,849 | 30.01x20.47x7.0 | A30 | no |  |
| `/Game/Env/HS/FR/HAL/Ext_Unnatural_Cave/FR_HAL_Ext_Unnatural_Cave_Bridge_w30_d20_h07_D/SM_FR_HAL_Ext_Unnatural_Cave_Bridge_w30_d20_h07_D` | StaticMesh | 1.61 | 50,519 | 30.02x20.36x7.0 | A30 | no |  |
| `/Game/Env/HS/FR/HAL/Ext_Unnatural_Cave/FR_HAL_Ext_Unnatural_Cave_Bridge_w30_d20_h07_E/SM_FR_HAL_Ext_Unnatural_Cave_Bridge_w30_d20_h07_E` | StaticMesh | 2.14 | 66,047 | 31.64x22.82x7.0 | A30 | no |  |
| `/Game/Env/HS/FR/HAL/Ext_Unnatural_Cave/FR_HAL_Ext_Unnatural_Cave_Bridge_w30_d20_h07_F/SM_FR_HAL_Ext_Unnatural_Cave_Bridge_w30_d20_h07_F` | StaticMesh | 1.89 | 57,891 | 34.19x27.34x7.0 | A30 | no |  |
| `/Game/Env/HS/FR/HAL/Ext_Unnatural_Cave/FR_HAL_Ext_Unnatural_Cave_Bridge_w30_d20_h07_G/SM_FR_HAL_Ext_Unnatural_Cave_Bridge_w30_d20_h07_G` | StaticMesh | 2.34 | 70,096 | 35.73x31.04x7.0 | A30 | no |  |
| `/Game/Env/HS/FR/HAL/Ext_Unnatural_Cave/FR_HAL_Ext_Unnatural_Cave_Bridge_w30_d20_h07_H/SM_FR_HAL_Ext_Unnatural_Cave_Bridge_w30_d20_h07_H` | StaticMesh | 1.60 | 49,857 | 36.18x33.8x7.0 | A30 | no | packed AO/roughness/height map |
| `/Game/Env/HS/FR/HAL/Ext_Unnatural_Cave/FR_HAL_Ext_Unnatural_Cave_Pillar_w11i5_d10_h17_F/SM_FR_HAL_Ext_Unnatural_Cave_Pillar_w11i5_d10_h17_F` | StaticMesh | 2.80 | 84,520 | 10.23x13.27x16.72 | A30 | no |  |
| `/Game/Env/HS/FR/HAL/Ext_Unnatural_Cave/FR_HAL_Ext_Unnatural_Cave_Pillar_w16_d10_h28_E/SM_FR_HAL_Ext_Unnatural_Cave_Pillar_w16_d10_h28_E` | StaticMesh | 4.48 | 133,175 | 10.27x20.73x23.69 | A30 | no |  |
| `/Game/Env/HS/FR/HAL/Ext_Unnatural_Cave/FR_HAL_Ext_Unnatural_Cave_Pillar_w18_d10_h25i5_D/SM_FR_HAL_Ext_Unnatural_Cave_Pillar_w18_d10_h25i5_D` | StaticMesh | 3.45 | 105,487 | 10.27x18.54x20.2 | A30 | no |  |
| `/Game/Env/HS/FR/HAL/Ext_Unnatural_Cave/FR_HAL_Ext_Unnatural_Cave_Pillar_w25i25_d10_h29i75_C/SM_FR_HAL_Ext_Unnatural_Cave_Pillar_w25i25_d10_h29i75_C` | StaticMesh | 2.91 | 87,039 | 10.46x25.6x26.61 | A30 | no |  |
| `/Game/Env/HS/FR/HAL/Ext_Unnatural_Cave/FR_HAL_Ext_Unnatural_Cave_Pillar_w25i5_d10i5_h21i5_B/SM_FR_HAL_Ext_Unnatural_Cave_Pillar_w25i5_d10i5_h21i5_B` | StaticMesh | 2.10 | 61,895 | 10.27x25.73x22.65 | A30 | no |  |
| `/Game/Env/HS/FR/HAL/Ext_Unnatural_Cave/FR_HAL_Ext_Unnatural_Cave_Pillar_w5_d5_h12_A/SM_FR_HAL_Ext_Unnatural_Cave_Pillar_w5_d5_h12_A` | StaticMesh | 1.80 | 56,102 | 4.61x4.93x12.55 | A30 | no |  |
| `/Game/Env/HS/FR/HAL/Ext_Unnatural_Cave/FR_HAL_Ext_Unnatural_Cave_Pillar_w9i5_d1_h25_G/SM_FR_HAL_Ext_Unnatural_Cave_Pillar_w9i5_d1_h25_G` | StaticMesh | 4.43 | 131,393 | 12.09x11.94x26.71 | A30 | no |  |
| `/Game/Env/HS/FR/HAL/Ext_Unnatural_Cave/FR_HAL_Ext_Unnatural_Cave_Wall_w10_d10_h10_K/SM_FR_HAL_Ext_Unnatural_Cave_Wall_w10_d10_h10_K` | StaticMesh | 0.90 | 26,550 | 10.29x20.0x10.0 | A30 | no |  |
| `/Game/Env/HS/FR/HAL/Ext_Unnatural_Cave/FR_HAL_Ext_Unnatural_Cave_Wall_w20_d05_h25_C/SM_FR_HAL_Ext_Unnatural_Cave_Wall_w20_d05_h25_C` | StaticMesh | 1.10 | 33,766 | 19.39x20.05x19.74 | A30 | no |  |
| `/Game/Env/HS/FR/HAL/Ext_Unnatural_Cave/FR_HAL_Ext_Unnatural_Cave_Wall_w20_d13_h3i5_I/SM_FR_HAL_Ext_Unnatural_Cave_Wall_w20_d13_h3i5_I` | StaticMesh | 3.36 | 98,868 | 16.62x29.77x27.62 | A30 | no |  |
| `/Game/Env/HS/FR/HAL/Ext_Unnatural_Cave/FR_HAL_Ext_Unnatural_Cave_Wall_w22_d13_h3i5_J/SM_FR_HAL_Ext_Unnatural_Cave_Wall_w22_d13_h3i5_J` | StaticMesh | 1.02 | 32,613 | 16.62x25.01x18.37 | A30 | no |  |
| `/Game/Env/HS/FR/HAL/Ext_Unnatural_Cave/FR_HAL_Ext_Unnatural_Cave_Wall_w25_d05_h14_A/SM_FR_HAL_Ext_Unnatural_Cave_Wall_w25_d05_h14_A` | StaticMesh | 1.38 | 42,412 | 19.39x21.3x14.89 | A30 | no |  |
| `/Game/Env/HS/FR/HAL/Ext_Unnatural_Cave/FR_HAL_Ext_Unnatural_Cave_Wall_w25_d05_h14_D/SM_FR_HAL_Ext_Unnatural_Cave_Wall_w25_d05_h14_D` | StaticMesh | 0.97 | 31,288 | 19.42x25.01x8.74 | A30 | no |  |
| `/Game/Env/HS/FR/HAL/Ext_Unnatural_Cave/FR_HAL_Ext_Unnatural_Cave_Wall_w25_d05_h14_E/SM_FR_HAL_Ext_Unnatural_Cave_Wall_w25_d05_h14_E` | StaticMesh | 0.85 | 26,343 | 19.42x25.02x8.74 | A30 | no |  |
| `/Game/Env/HS/FR/HAL/Ext_Unnatural_Cave/FR_HAL_Ext_Unnatural_Cave_Wall_w25_d13_h25_F/SM_FR_HAL_Ext_Unnatural_Cave_Wall_w25_d13_h25_F` | StaticMesh | 2.65 | 78,892 | 16.62x28.3x24.91 | A30 | no |  |
| `/Game/Env/HS/FR/HAL/Ext_Unnatural_Cave/FR_HAL_Ext_Unnatural_Cave_Wall_w25_d13_h25_G/SM_FR_HAL_Ext_Unnatural_Cave_Wall_w25_d13_h25_G` | StaticMesh | 2.02 | 58,990 | 16.62x28.36x24.91 | A30 | no |  |
| `/Game/Env/HS/FR/HAL/Ext_Unnatural_Cave/FR_HAL_Ext_Unnatural_Cave_Wall_w25_d13_h25_H/SM_FR_HAL_Ext_Unnatural_Cave_Wall_w25_d13_h25_H` | StaticMesh | 2.68 | 77,787 | 16.63x28.36x24.91 | A30 | no | packed AO/roughness/height map |
| `/Game/Env/HS/FR/HAL/Ext_Unnatural_Cave/FR_HAL_Ext_Unnatural_Cave_Wall_w30_d05_h25_B/SM_FR_HAL_Ext_Unnatural_Cave_Wall_w30_d05_h25_B` | StaticMesh | 1.26 | 38,146 | 19.39x30.1x19.74 | A30 | no |  |
| `/Game/Env/HS/FR/HAL/Int_Outpost/FR_HAL_Int_Outpost_A30_Ceiling_w10_d10_h0i5_A/SM_FR_HAL_Int_Outpost_A30_Ceiling_w10_d10_h0i5_A` | StaticMesh | 3.65 | 109,141 | 9.85x9.99x0.48 | A30 | no |  |
| `/Game/Env/HS/FR/HAL/Int_Outpost/FR_HAL_Int_Outpost_A30_Floor_w13i5_d10_h0i3_A/SM_FR_HAL_Int_Outpost_A30_Floor_w13i5_d10_h0i3_A` | StaticMesh | 4.28 | 129,750 | 13.52x10.0x0.25 | A30 | no |  |
| `/Game/Env/HS/FR/HAL/Int_Outpost/FR_HAL_Int_Outpost_A30_Pillar_w1i3_d2_h4_A/SM_FR_HAL_Int_Outpost_A30_Pillar_w1i3_d2_h4_A` | StaticMesh | 4.81 | 147,781 | 1.3x2.06x4.0 | A30 | no |  |
| `/Game/Env/HS/FR/HAL/Int_Outpost/FR_HAL_Int_Outpost_A30_Wall_w9i3_d1i1_h4_A/SM_FR_HAL_Int_Outpost_A30_Wall_w9i3_d1i1_h4_A` | StaticMesh | 3.37 | 104,035 | 9.28x1.15x4.0 | A30 | no |  |
| `/Game/Env/HS/FR/HAL/Int_Outpost/FR_HAL_Int_Outpost_A30_Wall_w9i3_d1i2_h4_B/SM_FR_HAL_Int_Outpost_A30_Wall_w9i3_d1i2_h4_B` | StaticMesh | 3.99 | 119,588 | 9.25x1.2x4.0 | A30 | no |  |
| `/Game/Env/HS/FR/SIL/Ext_Terminals_A/FR_SIL_Ext_Terminal_A_Beach_Floor_w40_d22i25_h4i5_G/SM_FR_SIL_Ext_Terminal_A_Beach_Floor_w40_d22i25_h4i5_G` | StaticMesh | 2.41 | 71,455 | 37.44x26.76x4.57 | B30 | no |  |
| `/Game/Env/HS/FR/SIL/Ext_Terminals_A/FR_SIL_Ext_Terminal_A_Beach_Floor_w44i5_d8i75_h7i25_H/SM_FR_SIL_Ext_Terminal_A_Beach_Floor_w44i5_d8i75_h7i25_H` | StaticMesh | 1.62 | 49,208 | 52.54x16.25x6.38 | B30 | no | packed AO/roughness/height map |
| `/Game/Env/HS/FR/SIL/Ext_Terminals_A/FR_SIL_Ext_Terminal_A_Beach_Floor_w44i5_d8i75_h7i25_I/SM_FR_SIL_Ext_Terminal_A_Beach_Floor_w44i5_d8i75_h7i25_I` | StaticMesh | 1.18 | 35,508 | 39.28x12.4x6.37 | B30 | no |  |
| `/Game/Env/HS/FR/SIL/Ext_Terminals_A/FR_SIL_Ext_Terminal_A_Beach_Floor_w46_d15i25_h05_A/SM_FR_SIL_Ext_Terminal_A_Beach_Floor_w46_d15i25_h05_A` | StaticMesh | 1.90 | 57,232 | 29.67x8.84x0.63 | B30 | no |  |
| `/Game/Env/HS/FR/SIL/Ext_Terminals_A/FR_SIL_Ext_Terminal_A_Beach_Floor_w47_d10i5_h10i75_F/SM_FR_SIL_Ext_Terminal_A_Beach_Floor_w47_d10i5_h10i75_F` | StaticMesh | 2.02 | 60,512 | 32.57x21.81x13.83 | B30 | no |  |
| `/Game/Env/HS/FR/SIL/Ext_Terminals_A/FR_SIL_Ext_Terminal_A_Beach_Floor_w53i25_d19i25_h10_C/SM_FR_SIL_Ext_Terminal_A_Beach_Floor_w53i25_d19i25_h10_C` | StaticMesh | 1.29 | 37,650 | 35.17x26.81x7.07 | B30 | no |  |
| `/Game/Env/HS/FR/SIL/Ext_Terminals_A/FR_SIL_Ext_Terminal_A_Beach_Floor_w60i25_d5i5_h11i75_E/SM_FR_SIL_Ext_Terminal_A_Beach_Floor_w60i25_d5i5_h11i75_E` | StaticMesh | 1.52 | 44,158 | 76.67x5.4x11.71 | B30 | no |  |
| `/Game/Env/HS/FR/SIL/Ext_Terminals_A/FR_SIL_Ext_Terminal_A_Beach_Floor_w70_d20i25_h03_B/SM_FR_SIL_Ext_Terminal_A_Beach_Floor_w70_d20i25_h03_B` | StaticMesh | 1.34 | 40,278 | 32.64x21.81x5.81 | B30 | no |  |
| `/Game/Env/HS/FR/SIL/Ext_Terminals_A/FR_SIL_Ext_Terminal_A_Beach_Floor_w81i5_d4i75_h14i5_D/SM_FR_SIL_Ext_Terminal_A_Beach_Floor_w81i5_d4i75_h14i5_D` | StaticMesh | 1.52 | 43,376 | 89.0x6.01x14.57 | B30 | no |  |
| `/Game/Env/HS/FR/SIL/Ext_Terminals_A/FR_SIL_Ext_Terminal_A_Beach_FrontPillar_w24_d11_h31i25_A/SM_FR_SIL_Ext_Terminal_A_Beach_FrontPillar_w24_d11_h31i25_A` | StaticMesh | 4.19 | 128,789 | 22.45x8.4x38.28 | B30 | no |  |
| `/Game/Env/HS/FR/SIL/Ext_Terminals_A/FR_SIL_Ext_Terminal_A_Beach_FrontPillar_w25_d10i25_h38i5_B/SM_FR_SIL_Ext_Terminal_A_Beach_FrontPillar_w25_d10i25_h38i5_B` | StaticMesh | 4.58 | 140,752 | 19.51x9.71x29.59 | B30 | no |  |
| `/Game/Env/HS/FR/SIL/Ext_Terminals_A/FR_SIL_Ext_Terminal_A_Beach_MainBody_w16_d12_h13_H/SM_FR_SIL_Ext_Terminal_A_Beach_MainBody_w16_d12_h13_H` | StaticMesh | 1.99 | 61,536 | 24.17x12.0x13.67 | B30 | no | packed AO/roughness/height map |
| `/Game/Env/HS/FR/SIL/Ext_Terminals_A/FR_SIL_Ext_Terminal_A_Beach_MainBody_w23i25_d12_h32i75_D/SM_FR_SIL_Ext_Terminal_A_Beach_MainBody_w23i25_d12_h32i75_D` | StaticMesh | 1.07 | 31,767 | 54.48x15.24x14.18 | B30 | no |  |
| `/Game/Env/HS/FR/SIL/Ext_Terminals_A/FR_SIL_Ext_Terminal_A_Beach_MainBody_w23i75_d8i5_h2i75_I/SM_FR_SIL_Ext_Terminal_A_Beach_MainBody_w23i75_d8i5_h2i75_I` | StaticMesh | 2.98 | 89,783 | 52.64x12.0x6.97 | B30 | no |  |
| `/Game/Env/HS/FR/SIL/Ext_Terminals_A/FR_SIL_Ext_Terminal_A_Beach_MainBody_w28i5_d12_h18i75_G/SM_FR_SIL_Ext_Terminal_A_Beach_MainBody_w28i5_d12_h18i75_G` | StaticMesh | 1.64 | 49,993 | 49.37x12.0x21.22 | B30 | no |  |
| `/Game/Env/HS/FR/SIL/Ext_Terminals_A/FR_SIL_Ext_Terminal_A_Beach_MainBody_w30_d12_h24i5_F/SM_FR_SIL_Ext_Terminal_A_Beach_MainBody_w30_d12_h24i5_F` | StaticMesh | 1.25 | 37,907 | 46.05x12.0x25.1 | B30 | no |  |
| `/Game/Env/HS/FR/SIL/Ext_Terminals_A/FR_SIL_Ext_Terminal_A_Beach_MainBody_w37i5_d12_h30_E/SM_FR_SIL_Ext_Terminal_A_Beach_MainBody_w37i5_d12_h30_E` | StaticMesh | 1.61 | 49,567 | 48.12x12.0x32.26 | B30 | no |  |
| `/Game/Env/HS/FR/SIL/Ext_Terminals_A/FR_SIL_Ext_Terminal_A_Beach_MainBody_w51i5_d15i25_h23i75_A/SM_FR_SIL_Ext_Terminal_A_Beach_MainBody_w51i5_d15i25_h23i75_A` | StaticMesh | 1.21 | 37,362 | 33.02x15.24x42.26 | B30 | no |  |
| `/Game/Env/HS/FR/SIL/Ext_Terminals_A/FR_SIL_Ext_Terminal_A_Beach_MainBody_w83i25_d15i25_h23i75_C/SM_FR_SIL_Ext_Terminal_A_Beach_MainBody_w83i25_d15i25_h23i75_C` | StaticMesh | 1.36 | 40,451 | 74.74x15.24x19.85 | B30 | no |  |
| `/Game/Env/HS/FR/SIL/Ext_Terminals_A/FR_SIL_Ext_Terminal_A_Beach_MainBody_w85i25_d15i25_h18_B/SM_FR_SIL_Ext_Terminal_A_Beach_MainBody_w85i25_d15i25_h18_B` | StaticMesh | 1.59 | 48,669 | 48.0x15.24x32.92 | B30 | no |  |
| `/Game/Env/HS/FR/SIL/Ext_Terminals_A/FR_SIL_Ext_Terminal_A_Beach_MiddlePillar_w22i5_d12_h28i5_A/SM_FR_SIL_Ext_Terminal_A_Beach_MiddlePillar_w22i5_d12_h28i5_A` | StaticMesh | 5.57 | 167,658 | 24.58x13.04x24.34 | B30 | no |  |
| `/Game/Env/HS/FR/SIL/Ext_Terminals_A/FR_SIL_Ext_Terminal_A_Beach_MiddlePillar_w23i75_d17i25_h28i75_B/SM_FR_SIL_Ext_Terminal_A_Beach_MiddlePillar_w23i75_d17i25_h28i75_B` | StaticMesh | 5.73 | 174,522 | 27.09x20.33x23.68 | B30,C20 | no |  |
| `/Game/Env/HS/FR/SIL/Ext_Terminals_A/SM_FR_SIL_Ext_Terminal_B_Coffee_Entry_Hull_wall` | StaticMesh | 3.81 | 119,566 | 20.2x3.94x0.15 | B30 | no |  |
| `/Game/Env/HS/FR/SIL/Ext_Terminals_B/FR_SIL_Ext_Terminal_B_Coffee_A_Housing_Door_Frame_Cap_A_w0i5_d3_h6_A/SM_FR_SIL_Ext_Terminal_B_Coffee_A_Housing_Door_Frame_Cap_A_w0i5_d3_h6_A` | StaticMesh | 1.43 | 45,863 | 0.45x3.23x6.07 | B30 | no |  |
| `/Game/Env/HS/FR/SIL/Ext_Terminals_B/FR_SIL_Ext_Terminal_B_Coffee_A_Housing_Door_Frame_Cap_B_w0i125_d3_h6_A/SM_FR_SIL_Ext_Terminal_B_Coffee_A_Housing_Door_Frame_Cap_B_w0i125_d3_h6_A` | StaticMesh | 0.30 | 9,266 | 0.09x1.82x4.9 | B30 | no |  |
| `/Game/Env/HS/FR/SIL/Ext_Terminals_B/FR_SIL_Ext_Terminal_B_Coffee_A_Housing_Door_Frame_Mid_A_w0i75_d3_h6_A/SM_FR_SIL_Ext_Terminal_B_Coffee_A_Housing_Door_Frame_Mid_A_w0i75_d3_h6_A` | StaticMesh | 1.01 | 32,694 | 0.75x3.23x6.07 | B30 | no |  |
| `/Game/Env/HS/FR/SIL/Ext_Terminals_B/FR_SIL_Ext_Terminal_B_Coffee_A_Housing_Door_Frame_Top_Cap_w4_d0i5_h1_A/SM_FR_SIL_Ext_Terminal_B_Coffee_A_Housing_Door_Frame_Top_Cap_w4_d0i5_h1_A` | StaticMesh | 2.05 | 66,881 | 0.45x3.81x0.82 | B30 | no |  |
| `/Game/Env/HS/FR/SIL/Ext_Terminals_B/FR_SIL_Ext_Terminal_B_Coffee_A_Housing_Door_Frame_Top_Mid_w4_d0i5_h1_A/SM_FR_SIL_Ext_Terminal_B_Coffee_A_Housing_Door_Frame_Top_Mid_w4_d0i5_h1_A` | StaticMesh | 1.07 | 34,185 | 0.36x3.81x0.82 | B30 | no |  |
| `/Game/Env/HS/FR/SIL/Ext_Terminals_B/FR_SIL_Ext_Terminal_B_Coffee_A_Housing_Girder_Mid_w3_d3_h14_A/SM_FR_SIL_Ext_Terminal_B_Coffee_A_Housing_Girder_Mid_w3_d3_h14_A` | StaticMesh | 0.33 | 10,279 | 2.9x2.27x14.4 | B30 | no |  |
| `/Game/Env/HS/FR/SIL/Ext_Terminals_B/FR_SIL_Ext_Terminal_B_Coffee_A_Housing_Girder_Side_w1_d3_h14_A/SM_FR_SIL_Ext_Terminal_B_Coffee_A_Housing_Girder_Side_w1_d3_h14_A` | StaticMesh | 1.91 | 61,243 | 2.77x0.79x14.39 | B30 | no |  |
| `/Game/Env/HS/FR/SIL/Ext_Terminals_B/FR_SIL_Ext_Terminal_B_Coffee_A_Housing_Shell_A_w17_d8_h9_A/SM_FR_SIL_Ext_Terminal_B_Coffee_A_Housing_Shell_A_w17_d8_h9_A` | StaticMesh | 4.71 | 129,666 | 19.57x9.58x8.77 | B30 | no |  |
| `/Game/Env/HS/FR/SIL/Ext_Terminals_B/FR_SIL_Ext_Terminal_B_Coffee_A_Housing_Shell_Door_Top_w4_d1_h1_A/SM_FR_SIL_Ext_Terminal_B_Coffee_A_Housing_Shell_Door_Top_w4_d1_h1_A` | StaticMesh | 0.61 | 17,937 | 0.94x3.81x1.09 | B30 | no |  |
| `/Game/Env/HS/FR/SIL/Ext_Terminals_B/FR_SIL_Ext_Terminal_B_Coffee_A_Housing_Shell_Entry_Trim_w5_d6_h10_A/SM_FR_SIL_Ext_Terminal_B_Coffee_A_Housing_Shell_Entry_Trim_w5_d6_h10_A` | StaticMesh | 4.67 | 138,930 | 6.35x2.26x9.57 | B30 | no |  |
| `/Game/Env/HS/FR/SIL/Ext_Terminals_B/FR_SIL_Ext_Terminal_B_Coffee_A_Housing_Shell_Entry_Wall_w2i5_d2_h9_A/SM_FR_SIL_Ext_Terminal_B_Coffee_A_Housing_Shell_Entry_Wall_w2i5_d2_h9_A` | StaticMesh | 2.06 | 63,933 | 2.67x2.08x9.15 | B30 | no |  |
| `/Game/Env/HS/FR/SIL/Ext_Terminals_B/FR_SIL_Ext_Terminal_B_Coffee_A_Platform_Ballast_Rib_x1_w0i75_d4_h13_A/SM_FR_SIL_Ext_Terminal_B_Coffee_A_Platform_Ballast_Rib_x1_w0i75_d4_h13_A` | StaticMesh | 1.64 | 51,916 | 4.14x0.79x12.38 | B30 | no |  |
| `/Game/Env/HS/FR/SIL/Ext_Terminals_B/FR_SIL_Ext_Terminal_B_Coffee_A_Platform_Ballast_Rib_x6_w0i75_d4_h13_A_Cut_A/SM_FR_SIL_Ext_Terminal_B_Coffee_A_Platform_Ballast_Rib_x6_w0i75_d4_h13_A_Cut_A` | StaticMesh | 6.98 | 221,971 | 4.14x4.48x12.39 | B30 | no |  |
| `/Game/Env/HS/FR/SIL/Ext_Terminals_B/FR_SIL_Ext_Terminal_B_Coffee_A_Platform_Ballast_Support_w22_d35_h21_A/SM_FR_SIL_Ext_Terminal_B_Coffee_A_Platform_Ballast_Support_w22_d35_h21_A` | StaticMesh | 7.86 | 239,386 | 34.87x23.74x22.33 | B30 | no |  |
| `/Game/Env/HS/FR/SIL/Ext_Terminals_B/FR_SIL_Ext_Terminal_B_Coffee_A_Platform_Deck_A_w16_d21_h0i5_A/SM_FR_SIL_Ext_Terminal_B_Coffee_A_Platform_Deck_A_w16_d21_h0i5_A` | StaticMesh | 5.85 | 179,626 | 29.13x20.91x0.7 | B30 | no |  |
| `/Game/Env/HS/FR/SIL/Ext_Terminals_B/FR_SIL_Ext_Terminal_B_Coffee_A_Platform_Deck_C_w27_d19_h0i5_A/SM_FR_SIL_Ext_Terminal_B_Coffee_A_Platform_Deck_C_w27_d19_h0i5_A` | StaticMesh | 3.77 | 111,585 | 18.54x29.67x0.41 | B30 | no |  |
| `/Game/Env/HS/FR/SIL/Ext_Terminals_B/FR_SIL_Ext_Terminal_B_Coffee_A_Platform_Deck_D_w23_d15_h0i5_A/SM_FR_SIL_Ext_Terminal_B_Coffee_A_Platform_Deck_D_w23_d15_h0i5_A` | StaticMesh | 3.14 | 99,260 | 22.66x29.93x0.45 | B30 | no |  |
| `/Game/Env/HS/FR/SIL/Ext_Terminals_B/FR_SIL_Ext_Terminal_B_Coffee_A_Platform_Deck_E_w15_d13_h0i5_A/SM_FR_SIL_Ext_Terminal_B_Coffee_A_Platform_Deck_E_w15_d13_h0i5_A` | StaticMesh | 1.68 | 50,788 | 12.56x21.13x0.41 | B30 | no |  |
| `/Game/Env/HS/FR/SIL/Ext_Terminals_B/FR_SIL_Ext_Terminal_B_Coffee_A_Platform_Deck_F_w6i5_d6i5_h0i5_A/SM_FR_SIL_Ext_Terminal_B_Coffee_A_Platform_Deck_F_w6i5_d6i5_h0i5_A` | StaticMesh | 0.55 | 16,236 | 6.74x6.5x0.73 | B30 | no |  |
| `/Game/Env/HS/FR/SIL/Ext_Terminals_B/FR_SIL_Ext_Terminal_B_Coffee_A_Platform_Entry_Aux_Mid_w2i5_d20_h1_A/SM_FR_SIL_Ext_Terminal_B_Coffee_A_Platform_Entry_Aux_Mid_w2i5_d20_h1_A` | StaticMesh | 7.32 | 230,254 | 17.25x5.15x1.2 | B30 | no |  |
| `/Game/Env/HS/FR/SIL/Ext_Terminals_B/FR_SIL_Ext_Terminal_B_Coffee_A_Platform_Entry_Aux_Side_w2i5_d20_h1_A/SM_FR_SIL_Ext_Terminal_B_Coffee_A_Platform_Entry_Aux_Side_w2i5_d20_h1_A` | StaticMesh | 10.45 | 340,169 | 17.25x3.33x1.21 | B30 | no |  |
| `/Game/Env/HS/FR/SIL/Ext_Terminals_B/FR_SIL_Ext_Terminal_B_Coffee_A_Platform_Entry_Front_Side_w2i5_d21_h2_A/SM_FR_SIL_Ext_Terminal_B_Coffee_A_Platform_Entry_Front_Side_w2i5_d21_h2_A` | StaticMesh | 5.27 | 149,243 | 18.09x7.61x1.41 | B30 | no |  |
| `/Game/Env/HS/FR/SIL/Ext_Terminals_B/FR_SIL_Ext_Terminal_B_Coffee_A_Platform_Entry_Mid_w2i5_d17_h2_A/SM_FR_SIL_Ext_Terminal_B_Coffee_A_Platform_Entry_Mid_w2i5_d17_h2_A` | StaticMesh | 9.42 | 299,598 | 17.75x8.35x1.4 | B30 | no |  |
| `/Game/Env/HS/FR/SIL/Ext_Terminals_B/FR_SIL_Ext_Terminal_B_Coffee_A_Platform_Entry_Ramp_Mid_w3i5_d7_h1_A/SM_FR_SIL_Ext_Terminal_B_Coffee_A_Platform_Entry_Ramp_Mid_w3i5_d7_h1_A` | StaticMesh | 0.70 | 22,518 | 7.56x4.13x1.23 | B30 | no |  |
| `/Game/Env/HS/FR/SIL/Ext_Terminals_B/FR_SIL_Ext_Terminal_B_Coffee_A_Platform_Entry_Ramp_Side_w3i5_d8_h1_A/SM_FR_SIL_Ext_Terminal_B_Coffee_A_Platform_Entry_Ramp_Side_w3i5_d8_h1_A` | StaticMesh | 1.14 | 35,931 | 8.15x3.38x1.19 | B30 | no |  |
| `/Game/Env/HS/FR/SIL/Ext_Terminals_B/FR_SIL_Ext_Terminal_B_Coffee_A_Platform_Girder_w5_d6_h21_A/SM_FR_SIL_Ext_Terminal_B_Coffee_A_Platform_Girder_w5_d6_h21_A` | StaticMesh | 6.29 | 192,153 | 13.22x7.28x22.55 | B30 | no |  |
| `/Game/Env/HS/FR/SIL/Ext_Terminals_B/FR_SIL_Ext_Terminal_B_Coffee_A_Platform_Spar_Mid_w13_d35_h20_A/SM_FR_SIL_Ext_Terminal_B_Coffee_A_Platform_Spar_Mid_w13_d35_h20_A` | StaticMesh | 1.61 | 50,994 | 34.77x12.71x20.08 | B30 | no |  |
| `/Game/Env/HS/FR/SIL/Ext_Terminals_B/FR_SIL_Ext_Terminal_B_Coffee_A_Platform_Spar_Side_w37_d33_h20_A/SM_FR_SIL_Ext_Terminal_B_Coffee_A_Platform_Spar_Side_w37_d33_h20_A` | StaticMesh | 2.83 | 89,304 | 33.01x37.02x20.07 | B30 | no |  |
| `/Game/Env/HS/FR/SIL/Ext_Terminals_B/FR_SIL_Ext_Terminal_B_Coffee_A_Sail_Mid_A_Base_w10_d49_h43_A/SM_FR_SIL_Ext_Terminal_B_Coffee_A_Sail_Mid_A_Base_w10_d49_h43_A` | StaticMesh | 0.96 | 27,367 | 49.08x9.16x43.75 | B30 | no |  |
| `/Game/Env/HS/FR/SIL/Ext_Terminals_B/FR_SIL_Ext_Terminal_B_Coffee_A_Sail_Mid_B_Low_w16_d80_h60_A/SM_FR_SIL_Ext_Terminal_B_Coffee_A_Sail_Mid_B_Low_w16_d80_h60_A` | StaticMesh | 0.73 | 21,332 | 79.81x15.9x60.12 | B30 | no |  |
| `/Game/Env/HS/FR/SIL/Ext_Terminals_B/FR_SIL_Ext_Terminal_B_Coffee_A_Sail_Mid_C_Mid_w15_d42_h58_A/SM_FR_SIL_Ext_Terminal_B_Coffee_A_Sail_Mid_C_Mid_w15_d42_h58_A` | StaticMesh | 1.02 | 32,078 | 41.75x14.85x58.19 | B30 | no |  |
| `/Game/Env/HS/FR/SIL/Ext_Terminals_B/FR_SIL_Ext_Terminal_B_Coffee_A_Sail_Mid_D_High_w12_d30_h44_A/SM_FR_SIL_Ext_Terminal_B_Coffee_A_Sail_Mid_D_High_w12_d30_h44_A` | StaticMesh | 1.03 | 30,909 | 30.34x12.18x43.82 | B30 | no |  |
| `/Game/Env/HS/FR/SIL/Ext_Terminals_B/FR_SIL_Ext_Terminal_B_Coffee_A_Sail_Mid_E_Top_w11_d24_h45_A/SM_FR_SIL_Ext_Terminal_B_Coffee_A_Sail_Mid_E_Top_w11_d24_h45_A` | StaticMesh | 1.38 | 41,228 | 24.82x10.22x45.06 | B30 | no |  |
| `/Game/Env/HS/FR/SIL/Ext_Terminals_B/FR_SIL_Ext_Terminal_B_Coffee_A_Sail_Side_A_Base_Shell_w13_d49_h44_A/SM_FR_SIL_Ext_Terminal_B_Coffee_A_Sail_Side_A_Base_Shell_w13_d49_h44_A` | StaticMesh | 9.36 | 269,042 | 49.08x12.82x44.28 | B30 | no |  |
| `/Game/Env/HS/FR/SIL/Ext_Terminals_B/FR_SIL_Ext_Terminal_B_Coffee_A_Sail_Side_B_Base_Truss_w13_d75_h58_A/SM_FR_SIL_Ext_Terminal_B_Coffee_A_Sail_Side_B_Base_Truss_w13_d75_h58_A` | StaticMesh | 6.43 | 189,789 | 74.61x12.83x57.7 | B30 | no |  |
| `/Game/Env/HS/FR/SIL/Ext_Terminals_B/FR_SIL_Ext_Terminal_B_Coffee_A_Sail_Side_C_Sail_Low_w8_d46_h60_A/SM_FR_SIL_Ext_Terminal_B_Coffee_A_Sail_Side_C_Sail_Low_w8_d46_h60_A` | StaticMesh | 4.57 | 133,230 | 45.98x7.91x59.25 | B30 | no |  |
| `/Game/Env/HS/FR/SIL/Ext_Terminals_B/FR_SIL_Ext_Terminal_B_Coffee_A_Sail_Side_D_Sail_Mid_w8_d39_h60_A/SM_FR_SIL_Ext_Terminal_B_Coffee_A_Sail_Side_D_Sail_Mid_w8_d39_h60_A` | StaticMesh | 3.59 | 105,504 | 38.88x7.36x60.55 | B30 | no |  |
| `/Game/Env/HS/FR/SIL/Ext_Terminals_B/FR_SIL_Ext_Terminal_B_Coffee_A_Sail_Side_E_Sail_High_w6_d29_h45_A/SM_FR_SIL_Ext_Terminal_B_Coffee_A_Sail_Side_E_Sail_High_w6_d29_h45_A` | StaticMesh | 4.89 | 151,679 | 28.75x6.02x44.81 | B30 | no |  |
| `/Game/Env/HS/FR/SIL/Ext_Terminals_B/FR_SIL_Ext_Terminal_B_Coffee_A_Sail_Side_F_Sail_Top_w5_d22_h45_A/SM_FR_SIL_Ext_Terminal_B_Coffee_A_Sail_Side_F_Sail_Top_w5_d22_h45_A` | StaticMesh | 2.44 | 71,221 | 21.28x5.35x44.92 | B30 | no |  |
| `/Game/Env/HS/FR/SIL/Ext_Terminals_B/FR_SIL_Ext_Terminal_B_Coffee_A_Sail_Slat_A_w1i25_1d_h4i5_A/SM_FR_SIL_Ext_Terminal_B_Coffee_A_Sail_Slat_A_w1i25_1d_h4i5_A` | StaticMesh | 1.87 | 59,155 | 0.78x4.54x1.03 | B30 | no |  |
| `/Game/Env/HS/FR/SIL/Ext_Terminals_B/FR_SIL_Ext_Terminal_B_Coffee_A_Tower_Base_Mid_w11_d63_h39_A/SM_FR_SIL_Ext_Terminal_B_Coffee_A_Tower_Base_Mid_w11_d63_h39_A` | StaticMesh | 7.58 | 225,500 | 63.05x11.13x38.46 | B30 | no |  |
| `/Game/Env/HS/FR/SIL/Ext_Terminals_B/FR_SIL_Ext_Terminal_B_Coffee_A_Tower_Base_Mid_w8_d40_h20_A/SM_FR_SIL_Ext_Terminal_B_Coffee_A_Tower_Base_Mid_w8_d40_h20_A` | StaticMesh | 1.27 | 36,074 | 41.81x9.56x20.31 | B30 | no |  |
| `/Game/Env/HS/FR/SIL/Ext_Terminals_B/FR_SIL_Ext_Terminal_B_Slat_A_w1i5_d1_h0i25_A/SM_FR_SIL_Ext_Terminal_B_Slat_A_w1i5_d1_h0i25_A` | StaticMesh | 0.47 | 14,667 | 0.63x1.43x0.31 | B30 | no |  |
| `/Game/Env/HS/FR/SIL/Ext_Terminals_B/FR_SIL_Ext_Terminal_B_Slat_B_w1i5_d1_h0i25_A/SM_FR_SIL_Ext_Terminal_B_Slat_B_w1i5_d1_h0i25_A` | StaticMesh | 0.59 | 18,302 | 0.63x1.43x0.31 | B30 | no |  |
| `/Game/Env/HS/FR/SIL/Ext_Terminals_C/FR_SIL_Ext_Terminal_C_Vinyl_Bridge_Beam_w18_d4i75_h3i5_A/SM_FR_SIL_Ext_Terminal_C_Vinyl_Bridge_Beam_w18_d4i75_h3i5_A` | StaticMesh | 2.18 | 66,499 | 18.0x4.77x3.43 | B30 | no |  |
| `/Game/Env/HS/FR/SIL/Ext_Terminals_C/FR_SIL_Ext_Terminal_C_Vinyl_Bridge_w13i5_d2i5_h07_E/SM_FR_SIL_Ext_Terminal_C_Vinyl_Bridge_w13i5_d2i5_h07_E` | StaticMesh | 1.32 | 38,804 | 13.44x2.43x7.0 | B30 | no |  |
| `/Game/Env/HS/FR/SIL/Ext_Terminals_C/FR_SIL_Ext_Terminal_C_Vinyl_Bridge_w16_d8i25_h12i25_C/SM_FR_SIL_Ext_Terminal_C_Vinyl_Bridge_w16_d8i25_h12i25_C` | StaticMesh | 2.49 | 74,152 | 16.0x8.26x12.15 | B30 | no |  |
| `/Game/Env/HS/FR/SIL/Ext_Terminals_C/FR_SIL_Ext_Terminal_C_Vinyl_Bridge_w16i75_d8i25_h5i25_D/SM_FR_SIL_Ext_Terminal_C_Vinyl_Bridge_w16i75_d8i25_h5i25_D` | StaticMesh | 1.30 | 39,401 | 16.74x8.21x5.16 | B30 | no |  |
| `/Game/Env/HS/FR/SIL/Ext_Terminals_C/FR_SIL_Ext_Terminal_C_Vinyl_Bridge_w18i25_d8i25_h15i5_B/SM_FR_SIL_Ext_Terminal_C_Vinyl_Bridge_w18i25_d8i25_h15i5_B` | StaticMesh | 2.27 | 69,188 | 18.2x8.2x15.41 | B30 | no |  |
| `/Game/Env/HS/FR/SIL/Ext_Terminals_C/FR_SIL_Ext_Terminal_C_Vinyl_Bridge_w25i75_d7i25_h4i25_A/SM_FR_SIL_Ext_Terminal_C_Vinyl_Bridge_w25i75_d7i25_h4i25_A` | StaticMesh | 3.39 | 102,642 | 25.64x7.2x4.3 | B30 | no |  |
| `/Game/Env/HS/FR/SIL/Ext_Terminals_C/FR_SIL_Ext_Terminal_C_Vinyl_Cliff_Connector_Center_w19_d09_h16i5_A/SM_FR_SIL_Ext_Terminal_C_Vinyl_Cliff_Connector_Center_w19_d09_h16i5_A` | StaticMesh | 0.98 | 29,163 | 19.07x9.0x16.39 | B30 | no |  |
| `/Game/Env/HS/FR/SIL/Ext_Terminals_C/FR_SIL_Ext_Terminal_C_Vinyl_Cliff_Connector_Side_w20_d10i5_h16_A/SM_FR_SIL_Ext_Terminal_C_Vinyl_Cliff_Connector_Side_w20_d10i5_h16_A` | StaticMesh | 1.95 | 58,947 | 19.48x3.23x16.23 | B30 | no |  |
| `/Game/Env/HS/FR/SIL/Ext_Terminals_C/FR_SIL_Ext_Terminal_C_Vinyl_Cliff_Connector_w14_d11_h6i25_B/SM_FR_SIL_Ext_Terminal_C_Vinyl_Cliff_Connector_w14_d11_h6i25_B` | StaticMesh | 0.32 | 8,951 | 14.18x11.89x6.2 | B30 | no |  |
| `/Game/Env/HS/FR/SIL/Ext_Terminals_C/FR_SIL_Ext_Terminal_C_Vinyl_Disc_w10_d13i75_h0i25_B/SM_FR_SIL_Ext_Terminal_C_Vinyl_Disc_w10_d13i75_h0i25_B` | StaticMesh | 1.77 | 53,778 | 10.0x13.81x0.41 | B30 | no |  |
| `/Game/Env/HS/FR/SIL/Ext_Terminals_C/FR_SIL_Ext_Terminal_C_Vinyl_Disc_w13i75_d22i25_h0i25_F/SM_FR_SIL_Ext_Terminal_C_Vinyl_Disc_w13i75_d22i25_h0i25_F` | StaticMesh | 1.58 | 47,522 | 13.76x22.12x0.36 | B30 | no |  |
| `/Game/Env/HS/FR/SIL/Ext_Terminals_C/FR_SIL_Ext_Terminal_C_Vinyl_Disc_w14i25_d16i25_h0i25_C/SM_FR_SIL_Ext_Terminal_C_Vinyl_Disc_w14i25_d16i25_h0i25_C` | StaticMesh | 1.42 | 42,961 | 14.27x16.25x0.53 | B30 | no |  |
| `/Game/Env/HS/FR/SIL/Ext_Terminals_C/FR_SIL_Ext_Terminal_C_Vinyl_Disc_w21_d21_h0i25_E/SM_FR_SIL_Ext_Terminal_C_Vinyl_Disc_w21_d21_h0i25_E` | StaticMesh | 0.91 | 26,989 | 14.27x18.11x0.37 | B30 | no |  |
| `/Game/Env/HS/FR/SIL/Ext_Terminals_C/FR_SIL_Ext_Terminal_C_Vinyl_Disc_w24i5_d29i5_h0i25_D/SM_FR_SIL_Ext_Terminal_C_Vinyl_Disc_w24i5_d29i5_h0i25_D` | StaticMesh | 1.69 | 51,244 | 24.5x29.5x0.39 | B30 | no |  |
| `/Game/Env/HS/FR/SIL/Ext_Terminals_C/FR_SIL_Ext_Terminal_C_Vinyl_Disc_w42i5_d15i25_h1i5_A/SM_FR_SIL_Ext_Terminal_C_Vinyl_Disc_w42i5_d15i25_h1i5_A` | StaticMesh | 2.05 | 60,960 | 42.43x16.3x1.5 | B30 | no |  |
| `/Game/Env/HS/FR/SIL/Ext_Terminals_C/FR_SIL_Ext_Terminal_C_Vinyl_Tower_w18i75_d2i75_h36i25_A/SM_FR_SIL_Ext_Terminal_C_Vinyl_Tower_w18i75_d2i75_h36i25_A` | StaticMesh | 4.49 | 137,576 | 18.5x2.98x36.26 | B30 | no |  |
| `/Game/Env/HS/FR/SIL/Ext_Terminals_C/FR_SIL_Ext_Terminal_C_Vinyl_Tower_w19_d3i5_h24_B/SM_FR_SIL_Ext_Terminal_C_Vinyl_Tower_w19_d3i5_h24_B` | StaticMesh | 4.14 | 126,265 | 19.06x3.8x24.04 | B30 | no |  |
| `/Game/Env/HS/FR/SIL/Ext_Terminals_D/FR_SIL_Ext_Terminal_D_UAP_Bow_w06i25_d22i5_h06i25_C/SM_FR_SIL_Ext_Terminal_D_UAP_Bow_w06i25_d22i5_h06i25_C` | StaticMesh | 2.55 | 415 | 22.28x6.48x6.93 | B30 | no |  |
| `/Game/Env/HS/FR/SIL/Ext_Terminals_D/FR_SIL_Ext_Terminal_D_UAP_Bow_w22i5_d31i5_h17i5_A/SM_FR_SIL_Ext_Terminal_D_UAP_Bow_w22i5_d31i5_h17i5_A` | StaticMesh | 2.69 | 359 | 31.85x22.63x15.58 | B30 | no |  |
| `/Game/Env/HS/FR/SIL/Ext_Terminals_D/FR_SIL_Ext_Terminal_D_UAP_Bow_w23_d32i5_h10i75_B/SM_FR_SIL_Ext_Terminal_D_UAP_Bow_w23_d32i5_h10i75_B` | StaticMesh | 3.30 | 333 | 32.82x23.22x11.14 | B30 | no |  |
| `/Game/Env/HS/FR/SIL/Ext_Terminals_D/FR_SIL_Ext_Terminal_D_UAP_Cliff_Connector_w02i5_d08i25_h18i25_B/SM_FR_SIL_Ext_Terminal_D_UAP_Cliff_Connector_w02i5_d08i25_h18i25_B` | StaticMesh | 0.26 | 41 | 3.08x8.24x18.35 | B30 | no |  |
| `/Game/Env/HS/FR/SIL/Ext_Terminals_D/FR_SIL_Ext_Terminal_D_UAP_Cliff_Connector_w05i5_d20i25_h11i5_C/SM_FR_SIL_Ext_Terminal_D_UAP_Cliff_Connector_w05i5_d20i25_h11i5_C` | StaticMesh | 1.62 | 179 | 5.51x19.87x9.62 | B30 | no |  |
| `/Game/Env/HS/FR/SIL/Ext_Terminals_D/FR_SIL_Ext_Terminal_D_UAP_Cliff_Connector_w06i25_d17i25_h10i5_D/SM_FR_SIL_Ext_Terminal_D_UAP_Cliff_Connector_w06i25_d17i25_h10i5_D` | StaticMesh | 1.09 | 68 | 17.57x7.69x9.73 | B30 | no |  |
| `/Game/Env/HS/FR/SIL/Ext_Terminals_D/FR_SIL_Ext_Terminal_D_UAP_Cliff_Connector_w07i5_d10_h21i5_E/SM_FR_SIL_Ext_Terminal_D_UAP_Cliff_Connector_w07i5_d10_h21i5_E` | StaticMesh | 2.75 | 318 | 7.89x10.15x21.15 | B30 | no |  |
| `/Game/Env/HS/FR/SIL/Ext_Terminals_D/FR_SIL_Ext_Terminal_D_UAP_Cliff_Connector_w17i5_d17i5_h08i25_A/SM_FR_SIL_Ext_Terminal_D_UAP_Cliff_Connector_w17i5_d17i5_h08i25_A` | StaticMesh | 0.94 | 148 | 19.04x17.68x9.18 | B30 | no |  |
| `/Game/Env/HS/FR/SIL/Ext_Terminals_D/FR_SIL_Ext_Terminal_D_UAP_Disc_Wings_w02i5_d15i25_h25i75_B/SM_FR_SIL_Ext_Terminal_D_UAP_Disc_Wings_w02i5_d15i25_h25i75_B` | StaticMesh | 3.06 | 212 | 15.92x2.35x25.76 | B30 | no |  |
| `/Game/Env/HS/FR/SIL/Ext_Terminals_D/FR_SIL_Ext_Terminal_D_UAP_Disc_Wings_w04_d17i75_h20_A/SM_FR_SIL_Ext_Terminal_D_UAP_Disc_Wings_w04_d17i75_h20_A` | StaticMesh | 3.27 | 445 | 18.29x4.77x19.98 | B30 | no |  |
| `/Game/Env/HS/FR/SIL/Ext_Terminals_D/FR_SIL_Ext_Terminal_D_UAP_Disc_w04_d08i25_h03_C/SM_FR_SIL_Ext_Terminal_D_UAP_Disc_w04_d08i25_h03_C` | StaticMesh | 0.22 | 57 | 12.57x17.96x3.04 | B30 | no |  |
| `/Game/Env/HS/FR/SIL/Ext_Terminals_D/FR_SIL_Ext_Terminal_D_UAP_Disc_w25i75_d27_h04_D/SM_FR_SIL_Ext_Terminal_D_UAP_Disc_w25i75_d27_h04_D` | StaticMesh | 1.33 | 357 | 29.47x25.52x4.06 | B30 | no |  |
| `/Game/Env/HS/FR/SIL/Ext_Terminals_D/FR_SIL_Ext_Terminal_D_UAP_Disc_w30i5_d30i5_h09i25_B/SM_FR_SIL_Ext_Terminal_D_UAP_Disc_w30i5_d30i5_h09i25_B` | StaticMesh | 2.10 | 465 | 30.83x30.74x9.64 | B30 | no |  |
| `/Game/Env/HS/FR/SIL/Ext_Terminals_D/FR_SIL_Ext_Terminal_D_UAP_Disc_w30i75_d30i75_h09i25_A/SM_FR_SIL_Ext_Terminal_D_UAP_Disc_w30i75_d30i75_h09i25_A` | StaticMesh | 2.72 | 554 | 30.86x30.82x9.8 | B30 | no |  |
| `/Game/Env/HS/FR/SIL/Ext_Terminals_D/FR_SIL_Ext_Terminal_D_UAP_Pillar_w01_d05_h02_C/SM_FR_SIL_Ext_Terminal_D_UAP_Pillar_w01_d05_h02_C` | StaticMesh | 2.10 | 256 | 1.29x5.13x2.1 | B30 | no |  |
| `/Game/Env/HS/FR/SIL/Ext_Terminals_D/FR_SIL_Ext_Terminal_D_UAP_Pillar_w09i5_d17i75_h09i5_A/SM_FR_SIL_Ext_Terminal_D_UAP_Pillar_w09i5_d17i75_h09i5_A` | StaticMesh | 2.16 | 101 | 17.6x9.42x7.53 | B30 | no |  |
| `/Game/Env/HS/FR/SIL/Ext_Terminals_D/FR_SIL_Ext_Terminal_D_UAP_Pillar_w09i75_d05i75_h07_B/SM_FR_SIL_Ext_Terminal_D_UAP_Pillar_w09i75_d05i75_h07_B` | StaticMesh | 1.17 | 141 | 5.08x9.83x4.74 | B30 | no |  |
| `/Game/Env/HS/FR/SIL/Ext_Terminals_D/FR_SIL_Ext_Terminal_D_UAP_Rig_Arm_w04i5_d04i5_h03i25_C/SM_FR_SIL_Ext_Terminal_D_UAP_Rig_Arm_w04i5_d04i5_h03i25_C` | StaticMesh | 1.29 | 307 | 5.58x5.59x3.61 | B30 | no |  |
| `/Game/Env/HS/FR/SIL/Ext_Terminals_D/FR_SIL_Ext_Terminal_D_UAP_Rig_Arm_w07_d10i5_h02i5_E/SM_FR_SIL_Ext_Terminal_D_UAP_Rig_Arm_w07_d10i5_h02i5_E` | StaticMesh | 0.38 | 99 | 7.52x10.54x2.52 | B30 | no |  |
| `/Game/Env/HS/FR/SIL/Ext_Terminals_D/FR_SIL_Ext_Terminal_D_UAP_Rig_Arm_w08i5_d06i5_h03i5_G/SM_FR_SIL_Ext_Terminal_D_UAP_Rig_Arm_w08i5_d06i5_h03i5_G` | StaticMesh | 2.30 | 98 | 8.86x6.45x3.52 | B30 | no |  |
| `/Game/Env/HS/FR/SIL/Ext_Terminals_D/FR_SIL_Ext_Terminal_D_UAP_Rig_Arm_w08i5_d11i5_h03i5_H/SM_FR_SIL_Ext_Terminal_D_UAP_Rig_Arm_w08i5_d11i5_h03i5_H` | StaticMesh | 2.12 | 69 | 8.87x11.78x3.58 | B30 | no | packed AO/roughness/height map |
| `/Game/Env/HS/FR/SIL/Ext_Terminals_D/FR_SIL_Ext_Terminal_D_UAP_Rig_Arm_w09i5_d05i25_h08i75_D/SM_FR_SIL_Ext_Terminal_D_UAP_Rig_Arm_w09i5_d05i25_h08i75_D` | StaticMesh | 0.78 | 99 | 13.64x17.66x2.43 | B30 | no |  |
| `/Game/Env/HS/FR/SIL/Ext_Terminals_D/FR_SIL_Ext_Terminal_D_UAP_Rig_Arm_w11i5_d24i5_h10i5_J/SM_FR_SIL_Ext_Terminal_D_UAP_Rig_Arm_w11i5_d24i5_h10i5_J` | StaticMesh | 0.43 | 51 | 23.33x11.49x9.1 | B30 | no |  |
| `/Game/Env/HS/FR/SIL/Ext_Terminals_D/FR_SIL_Ext_Terminal_D_UAP_Rig_Arm_w12_d16i25_h03i5_B/SM_FR_SIL_Ext_Terminal_D_UAP_Rig_Arm_w12_d16i25_h03i5_B` | StaticMesh | 1.67 | 161 | 16.9x12.06x2.91 | B30 | no |  |
| `/Game/Env/HS/FR/SIL/Ext_Terminals_D/FR_SIL_Ext_Terminal_D_UAP_Rig_Arm_w16i5_d18i25_h08i75_F/SM_FR_SIL_Ext_Terminal_D_UAP_Rig_Arm_w16i5_d18i25_h08i75_F` | StaticMesh | 0.68 | 173 | 24.64x17.55x7.67 | B30 | no |  |
| `/Game/Env/HS/FR/SIL/Ext_Terminals_D/FR_SIL_Ext_Terminal_D_UAP_Rig_Arm_w22i5_d10i25_h08i75_A/SM_FR_SIL_Ext_Terminal_D_UAP_Rig_Arm_w22i5_d10i25_h08i75_A` | StaticMesh | 1.84 | 138 | 22.57x8.51x1.59 | B30 | no |  |
| `/Game/Env/HS/FR/SIL/Ext_Terminals_D/FR_SIL_Ext_Terminal_D_UAP_Rig_w13i5_d23i5_h09i5_B/SM_FR_SIL_Ext_Terminal_D_UAP_Rig_w13i5_d23i5_h09i5_B` | StaticMesh | 1.94 | 274 | 26.19x14.4x9.65 | B30 | no |  |
| `/Game/Env/HS/FR/SIL/Ext_Terminals_D/FR_SIL_Ext_Terminal_D_UAP_Rig_w17i5_d23_h05i25_C/SM_FR_SIL_Ext_Terminal_D_UAP_Rig_w17i5_d23_h05i25_C` | StaticMesh | 4.33 | 668 | 26.15x19.74x7.81 | B30 | no |  |
| `/Game/Env/HS/FR/SIL/Ext_Terminals_D/FR_SIL_Ext_Terminal_D_UAP_Rig_w31i25_d41i5_h12i5_D/SM_FR_SIL_Ext_Terminal_D_UAP_Rig_w31i25_d41i5_h12i5_D` | StaticMesh | 6.16 | 590 | 43.25x30.53x14.25 | B30 | no |  |
| `/Game/Env/HS/FR/SIL/Ext_Terminals_D/FR_SIL_Ext_Terminal_D_UAP_Rig_w33i5_d36i5_h07i25_A/SM_FR_SIL_Ext_Terminal_D_UAP_Rig_w33i5_d36i5_h07i25_A` | StaticMesh | 2.29 | 365 | 36.99x34.64x7.29 | B30 | no |  |
| `/Game/Env/HS/FR/SIL/Ext_Terminals_D/FR_SIL_Ext_Terminal_D_UAP_Stern_w28_d38_h10_A/SM_FR_SIL_Ext_Terminal_D_UAP_Stern_w28_d38_h10_A` | StaticMesh | 2.60 | 236 | 40.79x28.91x10.87 | B30 | no |  |
| `/Game/Env/HS/FR/SIL/Ext_Terminals_D/FR_SIL_Ext_Terminal_D_UAP_Stern_w30i25_d60_h12i25_C/SM_FR_SIL_Ext_Terminal_D_UAP_Stern_w30i25_d60_h12i25_C` | StaticMesh | 5.24 | 440 | 62.98x30.25x13.4 | B30 | no |  |
| `/Game/Env/HS/FR/SIL/Ext_Terminals_D/FR_SIL_Ext_Terminal_D_UAP_Stern_w33i5_d52i5_h21i75_B/SM_FR_SIL_Ext_Terminal_D_UAP_Stern_w33i5_d52i5_h21i75_B` | StaticMesh | 3.69 | 252 | 53.56x35.09x17.07 | B30 | no |  |
| `/Game/Env/HS/FR/SIL/Gen_Golden_Path_Details/FR_SIL_Int_Chamber_A3_FloorDetail_A/SM_FR_SIL_Int_Chamber_A3_FloorDetail_A` | StaticMesh | 0.05 | 1,768 | 12.01x5.22x0.09 | B30 | no |  |
| `/Game/Env/HS/FR/SIL/Gen_Golden_Path_Details/FR_SIL_Int_Chamber_A3_StairDetail_A/SM_FR_SIL_Int_Chamber_A3_StairDetail_A` | StaticMesh | 0.09 | 3,784 | 11.84x4.48x6.88 | B30 | no |  |
| `/Game/Env/HS/FR/SIL/Gen_Golden_Path_Details/FR_SIL_Int_Chamber_A4_StairDetail_A/SM_FR_SIL_Int_Chamber_A4_Shaft_StairDetail_A` | StaticMesh | 0.06 | 1,817 | 9.67x5.55x5.3 | B30 | no |  |
| `/Game/Env/HS/FR/SIL/Gen_Golden_Path_Details/FR_SIL_Int_Chamber_A4_StairDetail_B/SM_FR_SIL_Int_Chamber_A4_Shaft_StairDetail_B` | StaticMesh | 0.06 | 1,940 | 9.49x5.42x5.34 | B30 | no |  |
| `/Game/Env/HS/FR/SIL/Gen_Golden_Path_Details/FR_SIL_Int_Chamber_A5_Shaft_StairDetail_A/SM_FR_SIL_Int_Chamber_A5_Shaft_StairDetail_A` | StaticMesh | 0.10 | 3,618 | 3.59x9.08x5.68 | B30 | no |  |
| `/Game/Env/HS/FR/SIL/Gen_Golden_Path_Details/FR_SIL_Int_Chamber_A5_StairDetail_A/SM_FR_SIL_Int_Chamber_A5_StairDetail_A` | StaticMesh | 0.05 | 1,816 | 8.0x3.15x6.17 | B30 | no |  |
| `/Game/Env/HS/FR/SIL/Gen_Golden_Path_Details/FR_SIL_Int_HallRamp_4to5_StairDetail_A/SM_FR_SIL_Int_HallRamp_4to5_StairDetail_A` | StaticMesh | 0.09 | 3,720 | 12.09x17.95x9.65 | B30 | no |  |
| `/Game/Env/HS/FR/SIL/Gen_Golden_Path_Details/FR_SIL_Int_SmallRoom_StairDetail_A/SM_FR_SIL_Int_SmallRoom_StairDetail_A` | StaticMesh | 0.23 | 9,144 | 20.98x15.91x13.7 | B30 | no |  |
| `/Game/Env/HS/FR/SIL/Gen_Pillars/FR_SIL_Int_Gen_Pillar_w01_d03_h03i75_A/SM_FR_SIL_Int_Gen_Pillar_w01_d03_h03i75_A` | StaticMesh | 1.06 | 32,082 | 1.03x3.1x3.75 | B30 | no |  |
| `/Game/Env/HS/FR/SIL/Gen_Pillars/FR_SIL_Int_Gen_Pillar_w01i5_d01i25_h05i75_A/SM_FR_SIL_Int_Gen_Pillar_w01i5_d01i25_h05i75_A` | StaticMesh | 1.42 | 45,897 | 0.94x1.3x5.82 | B30 | no |  |
| `/Game/Env/HS/FR/SIL/Gen_Pillars/FR_SIL_Pillar_A_Lrg_Top_Tall_w03_d08_h12_A/SM_FR_SIL_Pillar_A_Lrg_Top_Tall_w03_d08_h12_A` | StaticMesh | 0.05 | 1,541 | 7.5x3.0x33.0 | B30 | no |  |
| `/Game/Env/HS/FR/TWB/Canyon_C_Generator_A/FR_TWB_Int_Canyon_C_Generator_A_Ceiling_w24_d24_h15_A/SM_FR_TWB_Int_Canyon_C_Generator_A_Ceiling_w24_d24_h15_A` | StaticMesh | 4.15 | 91,291 | 26.82x24.01x15.9 | B40,C45 | no |  |
| `/Game/Env/HS/FR/TWB/Canyon_C_Generator_A/FR_TWB_Int_Canyon_C_Generator_A_Ceiling_w26_d23_h11_A/SM_FR_TWB_Int_Canyon_C_Generator_A_Ceiling_w26_d23_h11_A` | StaticMesh | 2.28 | 49,491 | 26.55x22.5x11.17 | B40,C45 | no |  |
| `/Game/Env/HS/FR/TWB/Canyon_C_Generator_A/FR_TWB_Int_Canyon_C_Generator_A_Ceiling_w2_d4_h2_A/SM_FR_TWB_Int_Canyon_C_Generator_A_Ceiling_w2_d4_h2_A` | StaticMesh | 2.51 | 60,081 | 1.98x3.98x2.22 | B40,C45 | no |  |
| `/Game/Env/HS/FR/TWB/Canyon_C_Generator_A/FR_TWB_Int_Canyon_C_Generator_A_Device_w3_d6_h13i5_A/SM_FR_TWB_Int_Canyon_C_Generator_A_Device_w3_d6_h13i5_A` | StaticMesh | 8.55 | 219,552 | 3.24x7.16x13.59 | B40,C45 | no |  |
| `/Game/Env/HS/FR/TWB/Canyon_C_Generator_A/FR_TWB_Int_Canyon_C_Generator_A_Device_w5_d5_h14_A/SM_FR_TWB_Int_Canyon_C_Generator_A_Device_w5_d5_h14_A` | StaticMesh | 15.19 | 375,831 | 5.75x5.75x12.07 | B40,C45 | no |  |
| `/Game/Env/HS/FR/TWB/Canyon_C_Generator_A/FR_TWB_Int_Canyon_C_Generator_A_Floor_w16_d16_h1_A/SM_FR_TWB_Int_Canyon_C_Generator_A_Floor_w16_d16_h1_A` | StaticMesh | 17.43 | 433,935 | 24.56x32.92x0.7 | B40,C45 | no | very dense: confirm Nanite before placing many |
| `/Game/Env/HS/FR/TWB/Canyon_C_Generator_A/FR_TWB_Int_Canyon_C_Generator_A_Floor_w16_d16_h1_B/SM_FR_TWB_Int_Canyon_C_Generator_A_Floor_w16_d16_h1_B` | StaticMesh | 16.22 | 408,970 | 17.03x32.92x0.69 | B40,C45 | no | very dense: confirm Nanite before placing many |
| `/Game/Env/HS/FR/TWB/Canyon_C_Generator_A/FR_TWB_Int_Canyon_C_Generator_A_Pillar_w2_d12_h7_A/SM_FR_TWB_Int_Canyon_C_Generator_A_Pillar_w2_d12_h7_A` | StaticMesh | 4.09 | 105,993 | 1.87x12.16x6.22 | B40,C45 | no |  |
| `/Game/Env/HS/FR/TWB/Canyon_C_Generator_A/FR_TWB_Int_Canyon_C_Generator_A_Wallcorner_w11_d11_h16_A/SM_FR_TWB_Int_Canyon_C_Generator_A_Wallcorner_w11_d11_h16_A` | StaticMesh | 8.36 | 202,501 | 11.27x11.29x16.02 | B40,C45 | no |  |
| `/Game/Env/HS/FR/TWB/Canyon_C_Generator_A/FR_TWB_lnt_Canyon_C_Generator_A_EnergyControlValve_A_w2i3_d1i6_h2i6_A/SM_FR_TWB_lnt_Canyon_C_Generator_A_EnergyControlValve_A_w2i3_d1i6_h2i6_A` | StaticMesh | 19.49 | 518,247 | 1.3x2.36x2.69 | C20 | no | very dense: confirm Nanite before placing many |
| `/Game/Env/HS/FR/TWB/Canyon_C_Generator_A/FR_TWB_lnt_Canyon_C_Generator_A_EnergyControlValve_Glass_w0i8_d1_h2i3_A/SM_FR_TWB_lnt_Canyon_C_Generator_A_EnergyControlValve_Glass_w0i8_d1_h2i3_A_Side1` | StaticMesh | 0.07 | 890 | 0.01x0.91x2.36 |  | no |  |
| `/Game/Env/HS/FR/TWB/Canyon_C_Generator_A/FR_TWB_lnt_Canyon_C_Generator_A_EnergyControlValve_Glass_w0i8_d1_h2i3_A/SM_FR_TWB_lnt_Canyon_C_Generator_A_EnergyControlValve_Glass_w0i8_d1_h2i3_A_Side2` | StaticMesh | 0.07 | 896 | 0.01x0.91x2.36 |  | no |  |
| `/Game/Env/HS/FR/TWB/Canyon_C_Generator_A/FR_TWB_lnt_Canyon_C_Generator_A_EnergyControlValve_Glass_w0i8_d1_h2i3_A/SM_FR_TWB_lnt_Canyon_C_Generator_A_EnergyControlValve_Glass_w0i8_d1_h2i3_A_Side3` | StaticMesh | 0.03 | 446 | 1.08x0.18x0.3 |  | no |  |
| `/Game/Env/HS/FR/TWB/Canyon_C_Generator_A/FR_TWB_lnt_Canyon_C_Generator_A_EnergyControlValve_Mid_A_w3_d1i6_h3_A/SM_FR_TWB_lnt_Canyon_C_Generator_A_EnergyControlValve_Mid_A_w3_d1i6_h3_A` | StaticMesh | 19.87 | 535,284 | 1.6x2.78x2.75 | C20 | no | very dense: confirm Nanite before placing many |

*Group note:* Shipped FR exterior pieces (B30 beach terminals, A30 crash-site bridge, B40 tarmac/bunker/tower). Render-only: author Blam collision for anything walkable

### Forerunner megastructures, patterns, holograms (103)

*Where on PWR:* Distant ring/megastructure silhouettes, base trims

| path | kind | MB | verts | bounds m | levels | PWR | note |
|---|---|---|---|---|---|---|---|
| `/Game/Env/HS/FR/Gen/Holograms/FR_Gen_Holo_Glyph/MIP_Holo_Glyph` | MaterialInstance | 0.00 |  |  | C10,C20 | no |  |
| `/Game/Env/HS/FR/Gen/Holograms/FR_Gen_Holo_Glyph/MIP_Holo_Glyph_Amber` | MaterialInstance | 0.00 |  |  | C10 | no |  |
| `/Game/Env/HS/FR/Gen/Holograms/FR_Gen_Holo_Glyph/MIP_Holo_Glyph_Blue` | MaterialInstance | 0.00 |  |  | C10,C20 | no |  |
| `/Game/Env/HS/FR/Gen/Holograms/FR_Gen_Holo_Glyph/MIP_Holo_Glyph_White` | MaterialInstance | 0.00 |  |  | C10 | no |  |
| `/Game/Env/HS/FR/Gen/Holograms/FR_Gen_Holo_Glyph/MI_Holo_Glyph` | MaterialInstance | 0.00 |  |  | C10,C20 | no |  |
| `/Game/Env/HS/FR/Gen/Holograms/FR_Gen_Holo_Glyph/MI_Holo_Glyph_01_Amber` | MaterialInstance | 0.00 |  |  | C10 | no |  |
| `/Game/Env/HS/FR/Gen/Holograms/FR_Gen_Holo_Glyph/MI_Holo_Glyph_01_Blue` | MaterialInstance | 0.00 |  |  | C10 | no |  |
| `/Game/Env/HS/FR/Gen/Holograms/FR_Gen_Holo_Glyph/MI_Holo_Glyph_02_Blue` | MaterialInstance | 0.00 |  |  | C10 | no |  |
| `/Game/Env/HS/FR/Gen/Holograms/FR_Gen_Holo_Glyph/MI_Holo_Glyph_03_Blue` | MaterialInstance | 0.00 |  |  | C10 | no |  |
| `/Game/Env/HS/FR/Gen/Holograms/FR_Gen_Holo_Glyph/MI_Holo_Glyph_05_Blue` | MaterialInstance | 0.00 |  |  | C10 | no |  |
| `/Game/Env/HS/FR/Gen/Holograms/FR_Gen_Holo_Glyph/MI_Holo_Glyph_06_Blue` | MaterialInstance | 0.00 |  |  | C10 | no |  |
| `/Game/Env/HS/FR/Gen/Holograms/FR_Gen_Holo_Glyph/MI_Holo_Glyph_07_Amber` | MaterialInstance | 0.00 |  |  | C10 | no |  |
| `/Game/Env/HS/FR/Gen/Holograms/FR_Gen_Holo_Glyph/MI_Holo_Glyph_08_White` | MaterialInstance | 0.00 |  |  | C10 | no |  |
| `/Game/Env/HS/FR/Gen/Holograms/FR_Gen_Holo_Glyph/MI_Holo_Glyph_09_Blue` | MaterialInstance | 0.00 |  |  | C10 | no |  |
| `/Game/Env/HS/FR/Gen/Holograms/FR_Gen_Holo_Glyph/MI_Holo_Glyph_09_White` | MaterialInstance | 0.00 |  |  | C10 | no |  |
| `/Game/Env/HS/FR/Gen/Holograms/FR_Gen_Holo_Glyph/SM_FR_Gen_Holo_Glyph` | StaticMesh | 0.00 | 4 | 1.0x1.0x0.0 | C10,C20 | no |  |
| `/Game/Env/HS/FR/Gen/Holograms/FR_Gen_Holo_Panel_SIL_Sml_Octo_A_cm_w14_d0i25_h7_A/SM_FR_Gen_Holo_Panel_SIL_Sml_Octo_A_cm_w14_d0i25_h7_A` | StaticMesh | 0.03 | 110 | 0.01x0.42x0.21 | B30 | no |  |
| `/Game/Env/HS/FR/Gen/MegaStructures/FR_FloatingSpire_Single01/SM_FloatingSpire_Single01` | StaticMesh | 1.78 | 21,662 | 7854.64x6809.86x23167.62 | B30 | no |  |
| `/Game/Env/HS/FR/Gen/MegaStructures/FR_Gen_MS_Ring_14th_Deg25i714_Hull_RetainingWall_Sym_Emis_Scale_km_0i01_w032_d2222_h022_A/SM_FR_Gen_MS_Ring_14th_Deg25i714_Hull_RetainingWall_Sym_Emis_Scale_km_0i01_w032_d2222_h022_A` | StaticMesh | 7.71 | 380,223 | 0.77x216.46x50.23 | A50 | no |  |
| `/Game/Env/HS/FR/Gen/MegaStructures/FR_Gen_MS_Ring_14th_Deg25i714_Hull_RetainingWall_Sym_Scale_km_0i01_w032_d2222_h022_A/SM_FR_Gen_MS_Ring_14th_Deg25i714_Hull_RetainingWall_Sym_Scale_km_0i01_w032_d2222_h022_A` | StaticMesh | 22.47 | 921,266 | 3.27x217.8x52.54 | A30,A50,B30,C45,D20,D40 | no | very dense: confirm Nanite before placing many |
| `/Game/Env/HS/FR/Gen/MegaStructures/FR_Gen_MS_Ring_14x1_14th_Deg25i714_Exoskeleton_km_0i01_w036_d2222_h540_A/SM_FR_Gen_MS_Ring_14x1_14th_Deg25i714_Exoskeleton_km_0i01_w036_d2222_h540_A` | StaticMesh | 17.53 | 535,215 | 3.63x229.14x53.9 | A15 | no | very dense: confirm Nanite before placing many |
| `/Game/Env/HS/FR/Gen/MegaStructures/FR_Gen_MS_Ring_14x1_14th_Deg25i714_Exoskeleton_km_0i01_w036_d2222_h540_A_Emis_A/SM_FR_Gen_MS_Ring_14x1_14th_Deg25i714_Exoskeleton_km_0i01_w036_d2222_h540_A_Emis_A` | StaticMesh | 17.80 | 742,195 | 2.81x198.06x44.1 | A15 | no | very dense: confirm Nanite before placing many |
| `/Game/Env/HS/FR/Gen/MegaStructures/FR_Gen_MS_Ring_14x2_28th_Deg12i857_Keel_Emitter_km_0i01_w500_d500_h155_A/SM_FR_Gen_MS_Ring_14x2_28th_Deg12i857_Keel_Emitter_km_0i01_w500_d500_h155_A` | StaticMesh | 37.92 | 1,149,076 | 35.98x45.42x9.45 | A15 | no | very dense: confirm Nanite before placing many |
| `/Game/Env/HS/FR/Gen/MegaStructures/FR_Gen_MS_Ring_14x2_28th_Deg12i857_Keel_Emitter_km_0i01_w500_d500_h155_A_Emis_A/SM_FR_Gen_MS_Ring_14x2_28th_Deg12i857_Keel_Emitter_km_0i01_w500_d500_h155_A_Emis_A` | StaticMesh | 9.49 | 418,861 | 32.38x33.05x5.57 | A15 | no | very dense: confirm Nanite before placing many |
| `/Game/Env/HS/FR/Gen/MegaStructures/FR_Gen_MS_Ring_14x2_28th_Deg12i857_Keel_Shield_km_0i01_w100_d1300_h170_A/SM_FR_Gen_MS_Ring_14x2_28th_Deg12i857_Keel_Shield_km_0i01_w100_d1300_h170_A` | StaticMesh | 14.31 | 449,460 | 10.01x133.75x14.43 | A15 | no | very dense: confirm Nanite before placing many |
| `/Game/Env/HS/FR/Gen/MegaStructures/FR_Gen_MS_Ring_14x2_28th_Deg12i857_Keel_Shield_km_0i01_w100_d1300_h170_A_Emis_A/SM_FR_Gen_MS_Ring_14x2_28th_Deg12i857_Keel_Shield_km_0i01_w100_d1300_h170_A_Emis_A` | StaticMesh | 6.69 | 289,481 | 6.56x76.94x4.41 | A15 | no |  |
| `/Game/Env/HS/FR/Gen/MegaStructures/FR_Gen_MS_Ring_14x4_56th_Deg6i428_Hull_Flange_km_0i01_w180_d800_h180_A/SM_FR_Gen_MS_Ring_14x4_56th_Deg6i428_Hull_Flange_km_0i01_w180_d800_h180_A` | StaticMesh | 9.32 | 280,139 | 18.63x80.01x18.09 | A15 | no |  |
| `/Game/Env/HS/FR/Gen/MegaStructures/FR_Gen_MS_Ring_14x4_56th_Deg6i428_Hull_Flange_km_0i01_w180_d800_h180_A_Emis_A/SM_FR_Gen_MS_Ring_14x4_56th_Deg6i428_Hull_Flange_km_0i01_w180_d800_h180_A_Emis_A` | StaticMesh | 1.72 | 76,416 | 15.14x35.35x12.42 | A15 | no |  |
| `/Game/Env/HS/FR/Gen/MegaStructures/FR_Gen_MS_Ring_14x4_56th_Deg6i428_Hull_Lattice_km_0i01_w062_d640_h165_A/SM_FR_Gen_MS_Ring_14x4_56th_Deg6i428_Hull_Lattice_km_0i01_w062_d640_h165_A` | StaticMesh | 9.58 | 280,365 | 6.23x64.08x16.6 | A15 | no |  |
| `/Game/Env/HS/FR/Gen/MegaStructures/FR_Gen_MS_Ring_14x4_56th_Deg6i428_Hull_Lattice_km_0i01_w062_d640_h165_A_Emis_A/SM_FR_Gen_MS_Ring_14x4_56th_Deg6i428_Hull_Lattice_km_0i01_w062_d640_h165_A_Emis_A` | StaticMesh | 6.23 | 270,500 | 5.06x54.02x10.59 | A15 | no |  |
| `/Game/Env/HS/FR/Gen/MegaStructures/FR_Gen_MS_Ring_14x5_70th_Deg5i143_Keel_Slewing_km_0i01_w230_d540_h132_A/SM_FR_Gen_MS_Ring_14x5_70th_Deg5i143_Keel_Slewing_km_0i01_w230_d540_h132_A` | StaticMesh | 9.77 | 292,642 | 22.95x53.82x13.19 | A15 | no |  |
| `/Game/Env/HS/FR/Gen/MegaStructures/FR_Gen_MS_Ring_14x5_70th_Deg5i143_Keel_Slewing_km_0i01_w230_d540_h132_A_Emis_A/SM_FR_Gen_MS_Ring_14x5_70th_Deg5i143_Keel_Slewing_km_0i01_w230_d540_h132_A_Emis_A` | StaticMesh | 4.22 | 168,306 | 2.27x46.72x1.78 | A15 | no |  |
| `/Game/Env/HS/FR/Gen/MegaStructures/FR_Gen_MS_Ring_14x6_84th_Deg4i286_Hull_Strake_km_0i01_w183_d473_h156_A/SM_FR_Gen_MS_Ring_14x6_84th_Deg4i286_Hull_Strake_km_0i01_w183_d473_h156_A` | StaticMesh | 10.99 | 328,715 | 18.3x47.3x15.61 | A15 | no |  |
| `/Game/Env/HS/FR/Gen/MegaStructures/FR_Gen_MS_Ring_14x6_84th_Deg4i286_Hull_Strake_km_0i01_w183_d473_h156_A_Emis_A/SM_FR_Gen_MS_Ring_14x6_84th_Deg4i286_Hull_Strake_km_0i01_w183_d473_h156_A_Emis_A` | StaticMesh | 14.91 | 663,187 | 17.32x38.18x13.08 | A15 | no | very dense: confirm Nanite before placing many |
| `/Game/Env/HS/FR/Gen/MegaStructures/FR_Gen_MS_Ring_14x8_112th_Deg3i214_Hull_Frame_km_0i01_w0246_d311_h145_A/SM_FR_Gen_MS_Ring_14x8_112th_Deg3i214_Hull_Frame_km_0i01_w0246_d311_h145_A` | StaticMesh | 23.18 | 689,066 | 24.63x31.08x14.5 | A15 | no | very dense: confirm Nanite before placing many |
| `/Game/Env/HS/FR/Gen/MegaStructures/FR_Gen_MS_Ring_14x8_112th_Deg3i214_Hull_Frame_km_0i01_w0246_d311_h145_A_Emis_A/SM_FR_Gen_MS_Ring_14x8_112th_Deg3i214_Hull_Frame_km_0i01_w0246_d311_h145_A_Emis_A` | StaticMesh | 1.43 | 60,185 | 19.25x27.4x4.24 | A15 | no |  |
| `/Game/Env/HS/FR/Gen/MegaStructures/FR_Gen_MS_Ring_Alpha_Scale_km_0i01_w500_d10000_h135_A/+Materials/MIC_FREmissive_Solid_Cold_Large` | MaterialInstance | 0.00 |  |  | A15 | no |  |
| `/Game/Env/HS/FR/Gen/MegaStructures/FR_Gen_MS_Ring_Alpha_Scale_km_0i01_w500_d10000_h135_A/+Materials/MIC_FREmissive_Solid_Cold_Large_SpaceScale_CityLights_A` | MaterialInstance | 0.01 |  |  | A15 | no |  |
| `/Game/Env/HS/FR/Gen/MegaStructures/FR_Gen_MS_Ring_Alpha_Scale_km_0i01_w500_d10000_h135_A/+Materials/MIC_FR_Metal_Diagonal_01_C_Dark_Rough1_Low_OS` | MaterialInstance | 0.34 |  |  | A15 | no |  |
| `/Game/Env/HS/FR/Gen/MegaStructures/FR_Gen_MS_Ring_Alpha_Scale_km_0i01_w500_d10000_h135_A/+Materials/MIC_FR_Metal_Diagonal_01_C_Dark_Rough1_Low_OS_B` | MaterialInstance | 0.00 |  |  | A15 | no |  |
| `/Game/Env/HS/FR/Gen/MegaStructures/FR_Gen_MS_Ring_Alpha_Scale_km_0i01_w500_d10000_h135_A/+Materials/MIC_FR_Metal_Diagonal_01_C_Dark_Rough1_Low_VCol` | MaterialInstance | 0.34 |  |  | A30,A50,B30,C45,D20,D40 | no |  |
| `/Game/Env/HS/FR/Gen/MegaStructures/FR_Gen_MS_Ring_Bio_Terrain_Scale_km_0i01_w500_d31415_h022_A/+Materials/MIC_FR_Gen_MS_Ring_Alpha_Scale_A_Skybox_UDIM_A_A30_HAL` | MaterialInstance | 0.02 |  |  | A30 | no |  |
| `/Game/Env/HS/FR/Gen/MegaStructures/FR_Gen_MS_Ring_Bio_Terrain_Scale_km_0i01_w500_d31415_h022_A/+Materials/MIC_FR_Gen_MS_Ring_Alpha_Scale_A_Skybox_UDIM_A_A50_TAR` | MaterialInstance | 0.02 |  |  | A50 | no |  |
| `/Game/Env/HS/FR/Gen/MegaStructures/FR_Gen_MS_Ring_Bio_Terrain_Scale_km_0i01_w500_d31415_h022_A/+Materials/MIC_FR_Gen_MS_Ring_Alpha_Scale_A_Skybox_UDIM_A_B30_SIL` | MaterialInstance | 0.02 |  |  | B30 | no |  |
| `/Game/Env/HS/FR/Gen/MegaStructures/FR_Gen_MS_Ring_Bio_Terrain_Scale_km_0i01_w500_d31415_h022_A/+Materials/MIC_FR_Gen_MS_Ring_Alpha_Scale_A_Skybox_UDIM_A_C45_TWB` | MaterialInstance | 0.02 |  |  | C45 | no |  |
| `/Game/Env/HS/FR/Gen/MegaStructures/FR_Gen_MS_Ring_Bio_Terrain_Scale_km_0i01_w500_d31415_h022_A/+Materials/MIC_FR_Gen_MS_Ring_Alpha_Scale_A_Skybox_UDIM_A_D20_KEY` | MaterialInstance | 0.02 |  |  | D20 | no |  |
| `/Game/Env/HS/FR/Gen/MegaStructures/FR_Gen_MS_Ring_Bio_Terrain_Scale_km_0i01_w500_d31415_h022_A/+Materials/MIC_FR_Gen_MS_Ring_Alpha_Scale_A_Skybox_UDIM_A_D40_MAW` | MaterialInstance | 0.02 |  |  | D40 | no |  |
| `/Game/Env/HS/FR/Gen/MegaStructures/FR_Gen_MS_Ring_Bio_Terrain_Scale_km_0i01_w500_d31415_h022_A/+Materials/MI_FR_Gen_MS_Ring_Alpha_Scale_A_Skybox_UDIM_A` | MaterialInstance | 0.02 |  |  | A15,A30,A50,B30,B40,C45,D20,D40 | no |  |
| `/Game/Env/HS/FR/Gen/MegaStructures/FR_Gen_MS_Ring_Bio_Terrain_Scale_km_0i01_w500_d31415_h022_A/SM_FR_Gen_MS_Ring_Bio_Terrain_Scale_km_0i01_w500_d31415_h022_A` | StaticMesh | 20.01 | 468,675 | 49.18x1000.47x1000.47 | A15,A30,A50,B30,C45,D20,D40 | no | very dense: confirm Nanite before placing many |
| `/Game/Env/HS/FR/Gen/MegaStructures/FR_Gen_Mega_Structure_Ring_Scale_0i001_km_dia10000_w318_h80_A/MI_FR_Mega_Structure_Ring_Frame_Placeholder` | MaterialInstance | 0.01 |  |  | B30 | no |  |
| `/Game/Env/HS/FR/Gen/MegaStructures/FR_Gen_Mega_Structure_Ring_Scale_0i001_km_dia10000_w318_h80_A/MI_FR_Mega_Structure_Ring_landscape_A30_Halo` | MaterialInstance | 0.00 |  |  | A30 | no |  |
| `/Game/Env/HS/FR/Gen/MegaStructures/FR_Gen_Mega_Structure_Ring_Scale_0i001_km_dia10000_w318_h80_A/MI_FR_Mega_Structure_Ring_landscape_A50` | MaterialInstance | 0.00 |  |  | A50 | no |  |
| `/Game/Env/HS/FR/Gen/MegaStructures/FR_Gen_Mega_Structure_Ring_Scale_0i001_km_dia10000_w318_h80_A/MI_FR_Mega_Structure_Ring_landscape_B30` | MaterialInstance | 0.01 |  |  | B30 | no |  |
| `/Game/Env/HS/FR/Gen/MegaStructures/FR_Gen_Mega_Structure_Ring_Scale_0i001_km_dia10000_w318_h80_A/NewRingMaterial/MI_FR_Ring` | MaterialInstance | 0.02 |  |  | A15,A30,A50,B30,B40,C45,D20,D40 | no |  |
| `/Game/Env/HS/FR/Gen/MegaStructures/FR_Gen_Mega_Structure_Ring_Scale_0i001_km_dia10000_w318_h80_A/NewRingMaterial/MI_FR_Ring_B30` | MaterialInstance | 0.02 |  |  | C45,D20,D40 | no |  |
| `/Game/Env/HS/FR/Gen/MegaStructures/FR_Gen_Mega_Structure_Ring_Scale_0i001_km_dia10000_w318_h80_A/NewRingMaterial/MI_FR_Ring_D20` | MaterialInstance | 0.02 |  |  | D20 | no |  |
| `/Game/Env/HS/FR/Gen/MegaStructures/FR_Gen_Mega_Structure_Ring_Scale_0i001_km_dia10000_w318_h80_A/NewRingMaterial/MI_FR_Ring_D40` | MaterialInstance | 0.02 |  |  | D40 | no |  |
| `/Game/Env/HS/FR/Gen/MegaStructures/FR_Gen_Mega_Structure_Ring_Scale_0i001_km_dia10000_w318_h80_A/SM_FR_Gen_Mega_Structure_Ring_Scale_0i001_km_dia10000_w318_h80_A` | StaticMesh | 0.50 | 9,988 | 2.83x101.91x101.92 | A30,A50,B30 | no |  |
| `/Game/Env/HS/FR/Gen/MegaStructures/FR_Gen_Mega_Structure_Ring_Scale_0i001_km_dia10000_w318_h80_A/SM_Ring_Biome` | StaticMesh | 0.58 | 655 | 42.89x907.89x907.89 | C45,D20,D40 | no |  |
| `/Game/Env/HS/FR/Gen/Patterns/FR_Gen_Pattern_H1_Grate_Tech_Mesh_A/SM_FR_Gen_Pattern_H1_Grate_Tech_Mesh_A` | StaticMesh | 4.62 | 151,865 | 4.0x3.0x0.12 | B30,C10 | no |  |
| `/Game/Env/HS/FR/Gen/Patterns/SM_FR_Gen_Pattern_H1_Floor_Plate_A/MIC_FR_Metal_Diagonal_01_A_Light_Rough1_Low` | MaterialInstance | 0.00 |  |  | B30 | no |  |
| `/Game/Env/HS/FR/Gen/Patterns/SM_FR_Gen_Pattern_H1_Floor_Plate_A/MIC_FR_Metal_Diagonal_01_B_Mid_Rough1_Low` | MaterialInstance | 0.00 |  |  | B30 | no |  |
| `/Game/Env/HS/FR/Gen/Patterns/SM_FR_Gen_Pattern_H1_Floor_Plate_A/SM_FR_Gen_Pattern_H1_Floor_Plate_A` | StaticMesh | 15.76 | 504,374 | 5.85x5.73x0.16 | B30 | no | very dense: confirm Nanite before placing many |
| `/Game/Env/HS/FR/Gen/Patterns/SM_FR_Gen_Pattern_H1_Floor_Plate_A/SM_FR_Gen_Pattern_H1_Floor_Plate_A_Cut_SIL_A` | StaticMesh | 5.38 | 168,153 | 5.27x2.27x0.15 | B30 | no |  |
| `/Game/Env/HS/FR/Gen/Patterns/SM_FR_Gen_Pattern_H1_Panel_A/SM_FR_Gen_Pattern_H1_Panel_A` | StaticMesh | 7.28 | 237,536 | 2.5x5.0x0.12 | B30,C10,C20 | no |  |
| `/Game/Env/HS/FR/Gen/Patterns/SM_FR_Gen_Pattern_H1_Panel_A/SM_FR_Gen_Pattern_H1_Panel_A_Skew_Deg22i5_Gen_Hallway_a` | StaticMesh | 2.95 | 78,181 | 1.87x1.9x4.03 | B30 | no |  |
| `/Game/Env/HS/FR/Gen/Patterns/SM_FR_Gen_Pattern_H1_Panel_Decorative_Wide_A/MIC_FR_Gen_Metal_Simple_01_Bronze_Dark_Glossy` | MaterialInstance | 0.08 |  |  | B30 | no |  |
| `/Game/Env/HS/FR/Gen/Patterns/SM_FR_Gen_Pattern_H1_Panel_Decorative_Wide_A/MIC_FR_Gen_Metal_Simple_01_Bronze_Light_Glossy` | MaterialInstance | 0.08 |  |  | A30,B30,C20 | no |  |
| `/Game/Env/HS/FR/Gen/Patterns/SM_FR_Gen_Pattern_H1_Panel_Decorative_Wide_A/MIC_FR_Gen_Metal_Simple_01_Grey_Light` | MaterialInstance | 0.09 |  |  | A30,B30,C20 | no |  |
| `/Game/Env/HS/FR/Gen/Patterns/SM_FR_Gen_Pattern_H1_Panel_Decorative_Wide_A/MIC_FR_Gen_Metal_Simple_01_Grey_Light_Glossy` | MaterialInstance | 0.17 |  |  | B30 | no |  |
| `/Game/Env/HS/FR/Gen/Patterns/SM_FR_Gen_Pattern_H1_Panel_Decorative_Wide_A/MIC_FR_Gen_Metal_Simple_01_Grey_Light_Glossy+1` | MaterialInstance | 0.09 |  |  | B30 | no |  |
| `/Game/Env/HS/FR/Gen/Patterns/SM_FR_Gen_Pattern_H1_Panel_Decorative_Wide_A/MIC_FR_Metal_Diagonal_01_Bronze_A_Dark_Rough2_Low_VCol` | MaterialInstance | 0.00 |  |  | B30 | no |  |
| `/Game/Env/HS/FR/Gen/Patterns/SM_FR_Gen_Pattern_H1_Panel_Decorative_Wide_A/MIC_FR_Metal_Diagonal_01_Bronze_A_Light_Rough1_Low_VCol` | MaterialInstance | 0.00 |  |  | B30 | no |  |
| `/Game/Env/HS/FR/Gen/Patterns/SM_FR_Gen_Pattern_H1_Panel_Decorative_Wide_A/SM_FR_Gen_Pattern_H1_Panel_Decorative_Wide_A_Circuits_ISO_A` | StaticMesh | 11.95 | 238,416 | 5.0x0.84x0.03 | B30 | no |  |
| `/Game/Env/HS/FR/Gen/Patterns/SM_FR_Gen_Pattern_H1_Panel_Decorative_Wide_A/SM_FR_Gen_Pattern_H1_Panel_Decorative_Wide_A_Circuits_ISO_A_Sml_A` | StaticMesh | 0.17 | 4,367 | 5.0x0.25x0.03 | B30 | no |  |
| `/Game/Env/HS/FR/Gen/Patterns/SM_FR_Gen_Pattern_H1_Panel_Decorative_Wide_A/SM_FR_Gen_Pattern_H1_Panel_Decorative_Wide_A_Circuits_ISO_A_Sym_A_B` | StaticMesh | 11.46 | 278,134 | 5.0x1.64x0.03 | B30 | no |  |
| `/Game/Env/HS/FR/Gen/Patterns/SM_FR_Gen_Pattern_H1_Panel_Decorative_Wide_A/SM_FR_Gen_Pattern_H1_Panel_Decorative_Wide_A_Circuits_ISO_A_Sym_A_C` | StaticMesh | 3.78 | 103,756 | 5.01x1.09x0.03 | B30 | no |  |
| `/Game/Env/HS/FR/Gen/Patterns/SM_FR_Gen_Pattern_H1_Panel_Decorative_Wide_A/SM_FR_Gen_Pattern_H1_Panel_Decorative_Wide_A_Mid_A` | StaticMesh | 3.62 | 108,232 | 5.67x3.83x0.06 | B30 | no |  |
| `/Game/Env/HS/FR/Gen/Patterns/SM_FR_Gen_Pattern_H1_Panel_Decorative_Wide_A/SM_FR_Gen_Pattern_H1_Panel_Decorative_Wide_A_Top_Circuits_A` | StaticMesh | 3.49 | 60,480 | 5.0x5.0x0.03 | B30 | no |  |
| `/Game/Env/HS/FR/Gen/Patterns/SM_FR_Gen_Pattern_H1_Panel_Decorative_Wide_A/SM_FR_Gen_Pattern_H1_Panel_Decorative_Wide_A_Top_Sun_A` | StaticMesh | 5.90 | 182,566 | 5.42x3.2x0.06 | B30 | no |  |
| `/Game/Env/HS/FR/Gen/Patterns/SM_FR_Gen_Pattern_H1_Panel_Thin_Strips_A/A_B/MIC_FR_Gen_Metal_Simple_01_Bronze_Dark` | MaterialInstance | 0.11 |  |  | B30 | no |  |
| `/Game/Env/HS/FR/Gen/Patterns/SM_FR_Gen_Pattern_H1_Panel_Thin_Strips_A/A_B/MIC_FR_Gen_Metal_Simple_01_Bronze_Light` | MaterialInstance | 0.08 |  |  | B30 | no |  |
| `/Game/Env/HS/FR/Gen/Patterns/SM_FR_Gen_Pattern_H1_Panel_Thin_Strips_A/A_B/MIC_FR_Gen_Metal_Simple_01_Bronze_Light_Glossy` | MaterialInstance | 0.08 |  |  | B30 | no |  |
| `/Game/Env/HS/FR/Gen/Patterns/SM_FR_Gen_Pattern_H1_Panel_Thin_Strips_A/A_B/MIC_FR_Gen_Metal_Simple_01_Grey_Dark_Glossy` | MaterialInstance | 0.11 |  |  | B30 | no |  |
| `/Game/Env/HS/FR/Gen/Patterns/SM_FR_Gen_Pattern_H1_Panel_Thin_Strips_A/A_B/SM_FR_Gen_Pattern_H1_Panel_Thin_Strips_A_B_Low_A` | StaticMesh | 0.06 | 275 | 0.83x5.0x0.04 | B30 | no |  |
| `/Game/Env/HS/FR/Gen/Patterns/SM_FR_Gen_Pattern_H1_Panel_Thin_Strips_A/A_B/SM_FR_Gen_Pattern_H1_Panel_Thin_Strips_A_B_Top_A` | StaticMesh | 0.88 | 18,458 | 0.83x5.0x0.04 | B30 | no |  |
| `/Game/Env/HS/FR/Gen/Patterns/SM_FR_Gen_Pattern_H1_Panel_Thin_Strips_A/A_B/SM_FR_Gen_Pattern_H1_Panel_Thin_Strips_A_B_Top_A_Turn90_In_r25_A` | StaticMesh | 1.56 | 31,246 | 0.83x0.57x0.57 | B30 | no |  |
| `/Game/Env/HS/FR/Gen/Patterns/SM_FR_Gen_Pattern_H1_Panel_Thin_Strips_A/A_B/SM_FR_Gen_Pattern_H1_Panel_Thin_Strips_A_B_w1i75_A` | StaticMesh | 1.54 | 30,723 | 0.83x0.88x0.08 | B30 | no |  |
| `/Game/Env/HS/FR/Gen/Patterns/SM_FR_Gen_Pattern_H1_Panel_Thin_Strips_A/A_B/SM_FR_Gen_Pattern_H1_Panel_Thin_Strips_A_B_w2_A` | StaticMesh | 2.91 | 59,553 | 0.83x2.0x0.08 | B30 | no |  |
| `/Game/Env/HS/FR/Gen/Patterns/SM_FR_Gen_Pattern_H1_Panel_Thin_Strips_A/A_C/MIC_FR_Gen_Metal_Simple_01_Bronze_Dark` | MaterialInstance | 0.11 |  |  | B30 | no |  |
| `/Game/Env/HS/FR/Gen/Patterns/SM_FR_Gen_Pattern_H1_Panel_Thin_Strips_A/A_C/MIC_FR_Gen_Metal_Simple_01_Bronze_Dark_Glossy` | MaterialInstance | 0.08 |  |  | B30 | no |  |
| `/Game/Env/HS/FR/Gen/Patterns/SM_FR_Gen_Pattern_H1_Panel_Thin_Strips_A/A_C/SM_FR_Gen_Pattern_H1_Panel_Thin_Strips_A_C` | StaticMesh | 6.08 | 122,803 | 0.58x5.0x0.18 | B30,C10 | no |  |
| `/Game/Env/HS/FR/Gen/Patterns/SM_FR_Gen_Pattern_H1_Panel_Thin_Strips_A/A_C/SM_FR_Gen_Pattern_H1_Panel_Thin_Strips_A_C_Base_A` | StaticMesh | 0.82 | 15,081 | 0.58x5.0x0.15 | B30 | no |  |
| `/Game/Env/HS/FR/Gen/Patterns/SM_FR_Gen_Pattern_H1_Panel_Thin_Strips_A/A_C/SM_FR_Gen_Pattern_H1_Panel_Thin_Strips_A_C_Mid_A` | StaticMesh | 3.31 | 58,057 | 0.34x5.0x0.13 | B30 | no |  |
| `/Game/Env/HS/FR/Gen/Patterns/SM_FR_Gen_Pattern_H1_Panel_Thin_Strips_A/A_C/SM_FR_Gen_Pattern_H1_Panel_Thin_Strips_A_C_Side_A` | StaticMesh | 0.51 | 9,319 | 0.14x5.0x0.01 | B30 | no |  |
| `/Game/Env/HS/FR/Gen/Patterns/SM_FR_Gen_Pattern_H1_Panel_Thin_Strips_A/A_C/SM_FR_Gen_Pattern_H1_Panel_Thin_Strips_A_C_Side_B` | StaticMesh | 0.52 | 9,320 | 0.14x5.0x0.01 | B30 | no |  |
| `/Game/Env/HS/FR/Gen/Patterns/SM_FR_Gen_Pattern_H1_Panel_Thin_Strips_A/A_D/MIC_FR_Gen_Metal_Simple_01_Bronze_Dark_Glossy` | MaterialInstance | 0.08 |  |  |  | no |  |
| `/Game/Env/HS/FR/Gen/Patterns/SM_FR_Gen_Pattern_H1_Panel_Thin_Strips_A/A_D/MIC_FR_Gen_Metal_Simple_01_Grey_Dark_Glossy` | MaterialInstance | 0.11 |  |  |  | no |  |
| `/Game/Env/HS/FR/Gen/Patterns/SM_FR_Gen_Pattern_H1_Panel_Thin_Strips_A/A_D/SM_FR_Gen_Pattern_H1_Panel_Thin_Strips_A_D_Base_A` | StaticMesh | 2.17 | 69,641 | 2.02x5.0x0.12 | B30 | no |  |
| `/Game/Env/HS/FR/Gen/Patterns/SM_FR_Gen_Pattern_H1_Panel_Thin_Strips_A/A_D/SM_FR_Gen_Pattern_H1_Panel_Thin_Strips_A_D_Screw_Single_A` | StaticMesh | 1.32 | 33,354 | 0.16x0.16x0.03 | B30 | no |  |
| `/Game/Env/HS/FR/Gen/Patterns/SM_FR_Gen_Pattern_H1_Panel_Thin_Strips_A/A_D/SM_FR_Gen_Pattern_H1_Panel_Thin_Strips_A_D_Skew_Deg22i5_Gen_Hallway_A` | StaticMesh | 2.61 | 68,009 | 0.73x2.5x1.77 | B30 | no |  |
| `/Game/Env/HS/FR/Gen/Patterns/SM_FR_Gen_Pattern_H1_Panel_Thin_Strips_A/A_D/SM_FR_Gen_Pattern_H1_Panel_Thin_Strips_A_D_Tile_Crop_A` | StaticMesh | 3.11 | 102,190 | 2.02x5.0x0.15 | B30 | no |  |
| `/Game/Env/HS/FR/Gen/props/FR_Gen_Int_Operationplatform_LargeHallway_w1_d3_h2_A/SM_FR_Gen_Int_Operationplatform_LargeHallway_w1_d3_h2_A` | StaticMesh | 8.10 | 187,492 | 0.88x2.78x2.09 | A30,B40,C10,C20,C45 | no |  |

*Group note:* Generic FR pieces

### UNSC wreckage (Maw) (121)

*Where on PWR:* A crashed-frigate debris field on a far slope

| path | kind | MB | verts | bounds m | levels | PWR | note |
|---|---|---|---|---|---|---|---|
| `/Game/Env/HS/UNSC/MAW/Ext_Desert/SM_UNSC_MAW_Desert_Ext_D_Center_Ramp_A_Merged` | StaticMesh | 23.83 | 637,460 | 33.43x41.77x25.59 | D40 | no | very dense: confirm Nanite before placing many [collision] |
| `/Game/Env/HS/UNSC/MAW/Ext_Desert/SM_UNSC_MAW_Desert_Ext_D_Center_Ramp_B_Merged` | StaticMesh | 11.69 | 323,791 | 29.41x29.59x13.46 | D40 | no | [collision] |
| `/Game/Env/HS/UNSC/MAW/Ext_Desert/SM_UNSC_MAW_Desert_Ext_D_Center_Ramp_C_Merged` | StaticMesh | 9.62 | 256,219 | 43.41x20.9x21.65 | D40 | no | [collision] |
| `/Game/Env/HS/UNSC/MAW/Ext_Desert/SM_UNSC_MAW_Desert_Ext_Falloff_Ramp_A_Merged` | StaticMesh | 13.52 | 377,982 | 21.21x43.37x13.86 | D40 | no | [collision] |
| `/Game/Env/HS/UNSC/MAW/Ext_Desert/SM_UNSC_MAW_Desert_Ext_Falloff_Ramp_B_Merged` | StaticMesh | 14.14 | 399,275 | 26.55x42.69x15.75 | D40 | no | [collision] |
| `/Game/Env/HS/UNSC/MAW/Ext_Desert/SM_UNSC_MAW_Desert_Ext_Falloff_Ramp_C_Merged` | StaticMesh | 14.65 | 413,489 | 30.73x45.87x18.13 | D40 | no | very dense: confirm Nanite before placing many [collision] |
| `/Game/Env/HS/UNSC/MAW/Ext_Desert/SM_UNSC_MAW_Desert_Ext_Falloff_Ramp_D_Merged` | StaticMesh | 14.37 | 406,625 | 31.85x43.2x20.52 | D40 | no | very dense: confirm Nanite before placing many [collision] |
| `/Game/Env/HS/UNSC/MAW/Ext_Desert/SM_UNSC_MAW_Desert_Ext_Falloff_Ramp_E_Merged` | StaticMesh | 13.09 | 372,366 | 28.22x36.33x21.68 | D40 | no | [collision] |
| `/Game/Env/HS/UNSC/MAW/Ext_Desert/SM_UNSC_MAW_Desert_Ext_Falloff_Ramp_F_Merged` | StaticMesh | 14.16 | 401,154 | 25.9x38.41x24.75 | D40 | no | very dense: confirm Nanite before placing many [collision] |
| `/Game/Env/HS/UNSC/MAW/Ext_Desert/SM_UNSC_MAW_Desert_Ext_Falloff_Ramp_G_Merged` | StaticMesh | 9.80 | 266,280 | 17.86x35.0x17.93 | D40 | no | [collision] |
| `/Game/Env/HS/UNSC/MAW/Ext_Desert/SM_UNSC_MAW_Desert_Ext_First_Cover_A_Merged` | StaticMesh | 25.60 | 651,835 | 38.52x37.88x55.91 | D40 | no | very dense: confirm Nanite before placing many [collision] |
| `/Game/Env/HS/UNSC/MAW/Ext_Desert/SM_UNSC_MAW_Desert_Ext_First_Cover_B_Merged` | StaticMesh | 29.76 | 738,168 | 48.43x39.4x62.79 | D40 | no | very dense: confirm Nanite before placing many [collision] |
| `/Game/Env/HS/UNSC/MAW/Wreckage/+Merge/SM_UNSC_MAW_Dmg_Hallway_A_Part_A_Merged` | StaticMesh | 27.40 | 728,160 | 38.32x40.57x17.94 | D40 | no | very dense: confirm Nanite before placing many [collision] |
| `/Game/Env/HS/UNSC/MAW/Wreckage/+Merge/SM_UNSC_MAW_Dmg_Hallway_A_Part_B_Merged` | StaticMesh | 25.73 | 663,186 | 46.72x42.78x36.53 | D40 | no | very dense: confirm Nanite before placing many [collision] |
| `/Game/Env/HS/UNSC/MAW/Wreckage/+Merge/SM_UNSC_MAW_Dmg_Hallway_A_Part_C_Merged` | StaticMesh | 35.19 | 1,120,915 | 30.05x24.02x15.01 | D40,E30 | no | very dense: confirm Nanite before placing many [collision] |
| `/Game/Env/HS/UNSC/MAW/Wreckage/+Merge/SM_UNSC_MAW_Dmg_Hallway_B_Part_A_Merged` | StaticMesh | 11.58 | 244,945 | 51.22x42.01x20.17 | D40,E30 | no | [collision] |
| `/Game/Env/HS/UNSC/MAW/Wreckage/+Merge/SM_UNSC_MAW_Dmg_Hallway_B_Part_B_Merged` | StaticMesh | 49.34 | 1,303,663 | 52.86x41.54x33.78 | D40,E30 | no | very dense: confirm Nanite before placing many [collision] |
| `/Game/Env/HS/UNSC/MAW/Wreckage/+Merge/SM_UNSC_MAW_Hull_Aframe_A_Merged` | StaticMesh | 38.67 | 912,848 | 40.45x72.25x19.22 | D40,E30 | no | very dense: confirm Nanite before placing many [collision] |
| `/Game/Env/HS/UNSC/MAW/Wreckage/+Merge/SM_UNSC_MAW_Hull_Aframe_B_Part_A_Merged` | StaticMesh | 36.90 | 894,370 | 41.95x43.54x29.18 | D40,E30 | no | very dense: confirm Nanite before placing many [collision] |
| `/Game/Env/HS/UNSC/MAW/Wreckage/+Merge/SM_UNSC_MAW_Hull_Aframe_B_Part_B_Merged` | StaticMesh | 29.09 | 679,884 | 40.45x43.54x24.25 | D40,E30 | no | very dense: confirm Nanite before placing many [collision] |
| `/Game/Env/HS/UNSC/MAW/Wreckage/+Merge/SM_UNSC_MAW_Hull_Aframe_C_Merged` | StaticMesh | 24.42 | 595,096 | 40.45x34.7x17.16 | D40,E30 | no | very dense: confirm Nanite before placing many [collision] |
| `/Game/Env/HS/UNSC/MAW/Wreckage/+Merge/SM_UNSC_MAW_Hull_Flat_A_Merged` | StaticMesh | 30.06 | 774,675 | 39.8x96.03x10.16 | D40,E30 | no | very dense: confirm Nanite before placing many [collision] |
| `/Game/Env/HS/UNSC/MAW/Wreckage/+Merge/SM_UNSC_MAW_Hull_Support_A_Merged` | StaticMesh | 20.83 | 522,485 | 26.17x4.57x8.46 | D40,E30 | no | very dense: confirm Nanite before placing many [collision] |
| `/Game/Env/HS/UNSC/MAW/Wreckage/+Merge/SM_UNSC_MAW_Hull_Uframe_A_Merged` | StaticMesh | 22.22 | 487,350 | 28.78x42.34x6.9 | D40,E30 | no | very dense: confirm Nanite before placing many [collision] |
| `/Game/Env/HS/UNSC/MAW/Wreckage/+Merge/SM_UNSC_MAW_Hull_Wing_A_Merged` | StaticMesh | 24.04 | 565,122 | 19.23x88.33x85.61 | D40,E30 | no | very dense: confirm Nanite before placing many [collision] |
| `/Game/Env/HS/UNSC/MAW/Wreckage/+Merge/SM_UNSC_MAW_Wreckage_Girder_Support_A_Merged` | StaticMesh | 6.76 | 156,478 | 36.46x5.16x1.96 | D40,E30 | no | [collision] |
| `/Game/Env/HS/UNSC/MAW/Wreckage/+Merge/SM_UNSC_MAW_Wreckage_Pipe_System_A_Merged` | StaticMesh | 5.12 | 138,085 | 30.47x7.69x1.46 | D40 | no | [collision] |
| `/Game/Env/HS/UNSC/MAW/Wreckage/+Merge/SM_UNSC_MAW_Wreckage_Uhull_support_A_Merged` | StaticMesh | 2.70 | 60,228 | 1.31x28.21x6.84 | D40,E30 | no | [collision] |
| `/Game/Env/HS/UNSC/MAW/Wreckage/UNSC_MAW_Wreckage_Big_Pipe_A/SM_UNSC_MAW_Wreckage_Big_Pipe_A` | StaticMesh | 5.80 | 160,369 | 33.66x23.41x23.41 | D40,E30 | no | [collision] |
| `/Game/Env/HS/UNSC/MAW/Wreckage/UNSC_MAW_Wreckage_Big_Pipe_B/SM_UNSC_MAW_Wreckage_Big_Pipe_B` | StaticMesh | 1.59 | 44,332 | 26.73x13.23x9.55 | D40,E30 | no | [collision] |
| `/Game/Env/HS/UNSC/MAW/Wreckage/UNSC_MAW_Wreckage_Bridge_Ext_A/SM_UNSC_MAW_Wreckage_Bridge_Ext_A` | StaticMesh | 1.84 | 47,948 | 52.01x62.96x33.47 | D40 | no | [collision] |
| `/Game/Env/HS/UNSC/MAW/Wreckage/UNSC_MAW_Wreckage_Bridge_Ext_B/SM_UNSC_MAW_Wreckage_Bridge_Ext_B` | StaticMesh | 2.63 | 58,887 | 29.12x28.0x15.74 | D40 | no | [collision] |
| `/Game/Env/HS/UNSC/MAW/Wreckage/UNSC_MAW_Wreckage_Bridge_Ext_C/SM_UNSC_MAW_Wreckage_Bridge_Ext_C` | StaticMesh | 1.33 | 35,184 | 7.47x6.16x3.31 | D40 | no | [collision] |
| `/Game/Env/HS/UNSC/MAW/Wreckage/UNSC_MAW_Wreckage_Bridge_Sensor_A/SM_UNSC_MAW_Wreckage_Bridge_Sensor_A` | StaticMesh | 1.62 | 44,536 | 36.91x187.07x51.82 | D40 | no | [collision] |
| `/Game/Env/HS/UNSC/MAW/Wreckage/UNSC_MAW_Wreckage_Bridge_Shell_A/SM_UNSC_MAW_Wreckage_Bridge_Shell_A` | StaticMesh | 0.66 | 18,439 | 83.14x110.08x76.95 | D40 | no | [collision] |
| `/Game/Env/HS/UNSC/MAW/Wreckage/UNSC_MAW_Wreckage_Bridge_Shell_B/SM_UNSC_MAW_Wreckage_Bridge_Shell_B` | StaticMesh | 1.26 | 33,180 | 184.19x57.47x137.0 | D40 | no | [collision] |
| `/Game/Env/HS/UNSC/MAW/Wreckage/UNSC_MAW_Wreckage_Bridge_Turret_A/SM_UNSC_MAW_Wreckage_Bridge_Turret_A` | StaticMesh | 1.66 | 48,403 | 27.61x71.0x28.65 | D40 | no | [collision] |
| `/Game/Env/HS/UNSC/MAW/Wreckage/UNSC_MAW_Wreckage_DamagedCasing/SM_PillarOfAutumn_DamagedCasing_F` | StaticMesh | 1.08 | 35,340 | 31.12x31.12x44.06 | D40 | no | [collision] |
| `/Game/Env/HS/UNSC/MAW/Wreckage/UNSC_MAW_Wreckage_DamagedCasing/SM_PillarOfAutumn_DamagedCasing_H` | StaticMesh | 0.17 | 2,638 | 29.76x5.85x15.26 | D40 | no | packed AO/roughness/height map [collision] |
| `/Game/Env/HS/UNSC/MAW/Wreckage/UNSC_MAW_Wreckage_Debris_Small_A/SM_UNSC_MAW_Wreckage_Debris_Small_A` | StaticMesh | 0.41 | 13,263 | 1.23x0.93x0.09 | A15,D40,E30 | no | [collision] |
| `/Game/Env/HS/UNSC/MAW/Wreckage/UNSC_MAW_Wreckage_Debris_Small_B/SM_UNSC_MAW_Wreckage_Debris_Small_B` | StaticMesh | 0.42 | 13,511 | 1.24x1.14x0.09 | A15,D40 | no | [collision] |
| `/Game/Env/HS/UNSC/MAW/Wreckage/UNSC_MAW_Wreckage_Debris_Small_C/SM_UNSC_MAW_Wreckage_Debris_Small_C` | StaticMesh | 0.30 | 9,419 | 2.16x1.25x0.05 | A15,D40 | no | [collision] |
| `/Game/Env/HS/UNSC/MAW/Wreckage/UNSC_MAW_Wreckage_Floor_A/SM_UNSC_MAW_Wreckage_Floor_A` | StaticMesh | 0.08 | 2,401 | 2.5x2.5x0.05 | D40 | no | [collision] |
| `/Game/Env/HS/UNSC/MAW/Wreckage/UNSC_MAW_Wreckage_Floor_B/SM_UNSC_MAW_Wreckage_Floor_B` | StaticMesh | 0.19 | 5,975 | 2.51x2.51x0.14 | D40 | no | [collision] |
| `/Game/Env/HS/UNSC/MAW/Wreckage/UNSC_MAW_Wreckage_Floor_C/SM_UNSC_MAW_Wreckage_Floor_C` | StaticMesh | 0.18 | 5,487 | 2.5x2.51x0.18 | D40 | no | [collision] |
| `/Game/Env/HS/UNSC/MAW/Wreckage/UNSC_MAW_Wreckage_Floor_D/SM_UNSC_MAW_Wreckage_Floor_D` | StaticMesh | 0.23 | 6,862 | 2.5x2.5x0.2 | D40 | no | [collision] |
| `/Game/Env/HS/UNSC/MAW/Wreckage/UNSC_MAW_Wreckage_Floor_E/SM_UNSC_MAW_Wreckage_Floor_E` | StaticMesh | 0.22 | 6,541 | 2.5x2.51x0.13 | D40 | no | [collision] |
| `/Game/Env/HS/UNSC/MAW/Wreckage/UNSC_MAW_Wreckage_Floor_F/SM_UNSC_MAW_Wreckage_Floor_F` | StaticMesh | 0.23 | 6,904 | 2.5x2.5x0.16 | D40 | no | [collision] |
| `/Game/Env/HS/UNSC/MAW/Wreckage/UNSC_MAW_Wreckage_Floor_Foundation_A/SM_UNSC_MAW_Wreckage_Floor_Foundation_A` | StaticMesh | 0.96 | 30,008 | 12.5x12.5x0.55 | D40 | no | [collision] |
| `/Game/Env/HS/UNSC/MAW/Wreckage/UNSC_MAW_Wreckage_Floor_Grating_A/SM_UNSC_MAW_Wreckage_Floor_Grating_A` | StaticMesh | 0.93 | 23,766 | 2.3x2.3x0.05 | D40 | no | [collision] |
| `/Game/Env/HS/UNSC/MAW/Wreckage/UNSC_MAW_Wreckage_Floor_Int_A/SM_UNSC_MAW_Wreckage_Floor_Int_A` | StaticMesh | 2.26 | 68,644 | 2.53x2.55x0.23 | D40,E30 | no | [collision] |
| `/Game/Env/HS/UNSC/MAW/Wreckage/UNSC_MAW_Wreckage_Floor_Support_A/SM_UNSC_MAW_Wreckage_Floor_Support_A` | StaticMesh | 0.46 | 13,895 | 3.7x3.69x0.23 | D40 | no | [collision] |
| `/Game/Env/HS/UNSC/MAW/Wreckage/UNSC_MAW_Wreckage_Floor_Support_B/SM_UNSC_MAW_Wreckage_Floor_Support_B` | StaticMesh | 0.37 | 11,065 | 2.5x3.69x0.23 | D40 | no | [collision] |
| `/Game/Env/HS/UNSC/MAW/Wreckage/UNSC_MAW_Wreckage_Floor_Support_D/SM_UNSC_MAW_Wreckage_Floor_Support_D` | StaticMesh | 0.30 | 9,056 | 1.0x1.0x0.07 | D40 | no | [collision] |
| `/Game/Env/HS/UNSC/MAW/Wreckage/UNSC_MAW_Wreckage_Floor_Support_E/SM_UNSC_MAW_Wreckage_Floor_Support_E` | StaticMesh | 0.23 | 7,384 | 1.7x0.2x0.07 | D40 | no | [collision] |
| `/Game/Env/HS/UNSC/MAW/Wreckage/UNSC_MAW_Wreckage_GIrder_Support_A/SM_UNSC_MAW_Wreckage_GIrder_Support_A` | StaticMesh | 1.17 | 35,644 | 14.22x5.16x1.96 | D40,E30 | no | [collision] |
| `/Game/Env/HS/UNSC/MAW/Wreckage/UNSC_MAW_Wreckage_GIrder_Support_B/SM_UNSC_MAW_Wreckage_GIrder_Support_B` | StaticMesh | 1.84 | 57,915 | 10.56x0.29x3.71 | D40,E30 | no | [collision] |
| `/Game/Env/HS/UNSC/MAW/Wreckage/UNSC_MAW_Wreckage_GIrder_Support_C/SM_UNSC_MAW_Wreckage_GIrder_Support_C` | StaticMesh | 1.67 | 51,383 | 10.19x0.46x1.95 | D40,E30 | no | [collision] |
| `/Game/Env/HS/UNSC/MAW/Wreckage/UNSC_MAW_Wreckage_Girder_Support_D/SM_UNSC_MAW_Wreckage_Girder_Support_D` | StaticMesh | 2.23 | 70,175 | 22.69x4.59x1.66 | D40,E30 | no | [collision] |
| `/Game/Env/HS/UNSC/MAW/Wreckage/UNSC_MAW_Wreckage_Girder_Support_E/SM_UNSC_MAW_Wreckage_Girder_Support_E` | StaticMesh | 1.57 | 33,747 | 7.43x28.68x4.89 | D40,E30 | no | [collision] |
| `/Game/Env/HS/UNSC/MAW/Wreckage/UNSC_MAW_Wreckage_Hallway_Panel_A/SM_UNSC_MAW_Wreckage_Hallway_Panel_A` | StaticMesh | 0.29 | 7,877 | 8.42x11.79x9.51 | D40,E30 | no | [collision] |
| `/Game/Env/HS/UNSC/MAW/Wreckage/UNSC_MAW_Wreckage_Hallway_Panel_B/SM_UNSC_MAW_Wreckage_Hallway_Panel_B` | StaticMesh | 0.34 | 10,218 | 8.72x4.21x5.26 | D40,E30 | no | [collision] |
| `/Game/Env/HS/UNSC/MAW/Wreckage/UNSC_MAW_Wreckage_Hallway_Panel_C/SM_UNSC_MAW_Wreckage_Hallway_Panel_C` | StaticMesh | 0.20 | 4,906 | 8.74x7.63x3.33 | D40,E30 | no | [collision] |
| `/Game/Env/HS/UNSC/MAW/Wreckage/UNSC_MAW_Wreckage_Hallway_Panel_D/SM_UNSC_MAW_Wreckage_Hallway_Panel_D` | StaticMesh | 0.27 | 8,060 | 16.56x3.35x1.23 | D40,E30 | no | [collision] |
| `/Game/Env/HS/UNSC/MAW/Wreckage/UNSC_MAW_Wreckage_Hallway_Panel_E/SM_UNSC_MAW_Wreckage_Hallway_Panel_E` | StaticMesh | 0.33 | 10,130 | 16.6x0.52x4.08 | D40,E30 | no | [collision] |
| `/Game/Env/HS/UNSC/MAW/Wreckage/UNSC_MAW_Wreckage_Hallway_Panel_F/SM_UNSC_MAW_Wreckage_Hallway_Panel_F` | StaticMesh | 0.33 | 10,267 | 16.51x8.54x4.64 | D40,E30 | no | [collision] |
| `/Game/Env/HS/UNSC/MAW/Wreckage/UNSC_MAW_Wreckage_Hallway_Panel_G/SM_UNSC_MAW_Wreckage_Hallway_Panel_G` | StaticMesh | 0.26 | 7,542 | 27.99x0.5x2.9 | D40,E30 | no | [collision] |
| `/Game/Env/HS/UNSC/MAW/Wreckage/UNSC_MAW_Wreckage_Hallway_Panel_H/SM_UNSC_MAW_Wreckage_Hallway_Panel_H` | StaticMesh | 1.13 | 33,773 | 14.12x15.39x6.23 | D40,E30 | no | packed AO/roughness/height map [collision] |
| `/Game/Env/HS/UNSC/MAW/Wreckage/UNSC_MAW_Wreckage_Hallway_Panel_J/SM_UNSC_MAW_Wreckage_Hallway_Panel_J` | StaticMesh | 1.02 | 31,175 | 12.7x0.68x3.56 | D40,E30 | no | [collision] |
| `/Game/Env/HS/UNSC/MAW/Wreckage/UNSC_MAW_Wreckage_Hallway_Panel_K/SM_UNSC_MAW_Wreckage_Hallway_Panel_K` | StaticMesh | 0.56 | 16,243 | 8.27x33.52x0.51 | D40,E30 | no | [collision] |
| `/Game/Env/HS/UNSC/MAW/Wreckage/UNSC_MAW_Wreckage_Hallway_Support_A/SM_UNSC_MAW_Wreckage_Hallway_Support_A` | StaticMesh | 1.02 | 32,084 | 19.64x0.88x16.0 | D40,E30 | no | [collision] |
| `/Game/Env/HS/UNSC/MAW/Wreckage/UNSC_MAW_Wreckage_Hallway_Support_B/SM_UNSC_MAW_Wreckage_Hallway_Support_B` | StaticMesh | 0.45 | 14,470 | 3.71x24.0x3.05 | D40,E30 | no | [collision] |
| `/Game/Env/HS/UNSC/MAW/Wreckage/UNSC_MAW_Wreckage_Hallway_Support_C/SM_UNSC_MAW_Wreckage_Hallway_Support_C` | StaticMesh | 1.73 | 56,645 | 1.49x28.76x1.22 | D40,E30 | no | [collision] |
| `/Game/Env/HS/UNSC/MAW/Wreckage/UNSC_MAW_Wreckage_Hallway_Support_D/SM_UNSC_MAW_Wreckage_Hallway_Support_D` | StaticMesh | 0.48 | 14,988 | 12.82x1.1x8.85 | D40,E30 | no | [collision] |
| `/Game/Env/HS/UNSC/MAW/Wreckage/UNSC_MAW_Wreckage_Hull_Dmg_A/SM_UNSC_MAW_Wreckage_Hull_Dmg_A` | StaticMesh | 3.29 | 88,038 | 19.87x1.98x12.41 | D40,E30 | no | [collision] |
| `/Game/Env/HS/UNSC/MAW/Wreckage/UNSC_MAW_Wreckage_Hull_Dmg_B/SM_UNSC_MAW_Wreckage_Hull_Dmg_B` | StaticMesh | 2.05 | 55,565 | 23.92x2.21x8.6 | D40,E30 | no | [collision] |
| `/Game/Env/HS/UNSC/MAW/Wreckage/UNSC_MAW_Wreckage_ShipExterior_Intro_A/SM_UNSC_MAW_Wreckage_ShipExterior_Intro_A1` | StaticMesh | 0.15 | 1,374 | 157.39x9.1x88.9 | D40 | no | [collision] |
| `/Game/Env/HS/UNSC/MAW/Wreckage/UNSC_MAW_Wreckage_ShipExterior_Intro_A/SM_UNSC_MAW_Wreckage_ShipExterior_Intro_A1_Details` | StaticMesh | 1.59 | 48,349 | 158.26x20.69x84.9 | D40 | no | [collision] |
| `/Game/Env/HS/UNSC/MAW/Wreckage/UNSC_MAW_Wreckage_ShipExterior_Intro_A/SM_UNSC_MAW_Wreckage_ShipExterior_Intro_A2` | StaticMesh | 0.60 | 12,284 | 158.29x137.1x210.03 | D40 | no | [collision] |
| `/Game/Env/HS/UNSC/MAW/Wreckage/UNSC_MAW_Wreckage_ShipExterior_Intro_A/SM_UNSC_MAW_Wreckage_ShipExterior_Intro_A2_Details` | StaticMesh | 1.10 | 33,594 | 159.95x114.62x193.41 | D40 | no | [collision] |
| `/Game/Env/HS/UNSC/MAW/Wreckage/UNSC_MAW_Wreckage_ShipExterior_Intro_A/SM_UNSC_MAW_Wreckage_ShipExterior_Intro_A3` | StaticMesh | 0.11 | 2,255 | 157.28x138.27x174.78 | D40 | no | [collision] |
| `/Game/Env/HS/UNSC/MAW/Wreckage/UNSC_MAW_Wreckage_ShipExterior_Intro_A/SM_UNSC_MAW_Wreckage_ShipExterior_Intro_A3_Details` | StaticMesh | 0.82 | 26,919 | 138.11x64.47x141.09 | D40 | no | [collision] |
| `/Game/Env/HS/UNSC/MAW/Wreckage/UNSC_MAW_Wreckage_ShipExterior_Intro_A/SM_UNSC_MAW_Wreckage_ShipExterior_Intro_A4` | StaticMesh | 0.11 | 1,425 | 67.8x16.48x23.45 | D40 | no | [collision] |
| `/Game/Env/HS/UNSC/MAW/Wreckage/UNSC_MAW_Wreckage_ShipExterior_Intro_A/SM_UNSC_MAW_Wreckage_ShipExterior_Intro_A5` | StaticMesh | 5.44 | 171,980 | 6.32x0.48x4.82 | D40 | no | [collision] |
| `/Game/Env/HS/UNSC/MAW/Wreckage/UNSC_MAW_Wreckage_ShipExterior_Intro_A/SM_UNSC_MAW_Wreckage_ShipExterior_Intro_C` | StaticMesh | 2.84 | 80,687 | 6.0x3.37x5.13 | D40 | no | [collision] |
| `/Game/Env/HS/UNSC/MAW/Wreckage/UNSC_MAW_Wreckage_ShipExterior_Intro_A/SM_UNSC_MAW_Wreckage_ShipExterior_Intro_C2` | StaticMesh | 2.81 | 82,895 | 6.0x3.28x5.13 | A15 | no | [collision] |
| `/Game/Env/HS/UNSC/MAW/Wreckage/UNSC_MAW_Wreckage_ShipExterior_Intro_A/SM_UNSC_MAW_Wreckage_ShipExterior_Intro_D` | StaticMesh | 0.36 | 6,370 | 121.34x154.81x516.4 | D40 | no | [collision] |
| `/Game/Env/HS/UNSC/MAW/Wreckage/UNSC_MAW_Wreckage_ShipExterior_Intro_A/SM_UNSC_MAW_Wreckage_ShipExterior_Intro_D_Details` | StaticMesh | 3.15 | 91,394 | 121.36x100.78x515.61 | D40 | no | [collision] |
| `/Game/Env/HS/UNSC/MAW/Wreckage/UNSC_MAW_Wreckage_Ship_Structure_A/SM_UNSC_MAW_Wreckage_Ship_Structure_A` | StaticMesh | 2.06 | 70,795 | 70.03x56.0x4.75 | D40,E30 | no | [collision] |
| `/Game/Env/HS/UNSC/MAW/Wreckage/UNSC_MAW_Wreckage_Ship_Structure_Dmg_A/SM_UNSC_MAW_Wreckage_Ship_Structure_Dmg_A` | StaticMesh | 0.66 | 19,662 | 70.02x6.77x4.76 | D40,E30 | no | [collision] |
| `/Game/Env/HS/UNSC/MAW/Wreckage/UNSC_MAW_Wreckage_Ship_Structure_Dmg_B/SM_UNSC_MAW_Wreckage_Ship_Structure_Dmg_B` | StaticMesh | 0.69 | 20,279 | 69.91x6.3x5.78 | D40,E30 | no | [collision] |
| `/Game/Env/HS/UNSC/MAW/Wreckage/UNSC_MAW_Wreckage_Uhull_panel_A/SM_UNSC_MAW_Wreckage_Uhull_panel_A` | StaticMesh | 0.76 | 19,939 | 8.31x12.9x0.21 | D40,E30 | no | [collision] |
| `/Game/Env/HS/UNSC/MAW/Wreckage/UNSC_MAW_Wreckage_Uhull_panel_B/SM_UNSC_MAW_Wreckage_Uhull_panel_B` | StaticMesh | 0.34 | 9,067 | 8.27x2.02x0.21 | D40,E30 | no | [collision] |
| `/Game/Env/HS/UNSC/MAW/Wreckage/UNSC_MAW_Wreckage_Uhull_panel_C/SM_UNSC_MAW_Wreckage_Uhull_panel_C` | StaticMesh | 0.35 | 9,339 | 2.03x8.79x2.44 | D40,E30 | no | [collision] |
| `/Game/Env/HS/UNSC/MAW/Wreckage/UNSC_MAW_Wreckage_Uhull_panel_D/SM_UNSC_MAW_Wreckage_Uhull_panel_D` | StaticMesh | 0.38 | 9,980 | 2.66x8.76x3.22 | D40,E30 | no | [collision] |
| `/Game/Env/HS/UNSC/MAW/Wreckage/UNSC_MAW_Wreckage_Uhull_panel_E/SM_UNSC_MAW_Wreckage_Uhull_panel_E` | StaticMesh | 0.35 | 9,184 | 7.48x4.24x3.42 | D40,E30 | no | [collision] |
| `/Game/Env/HS/UNSC/MAW/Wreckage/UNSC_MAW_Wreckage_Uhull_panel_F/SM_UNSC_MAW_Wreckage_Uhull_panel_F` | StaticMesh | 0.35 | 9,227 | 3.41x4.33x1.12 | D40,E30 | no | [collision] |
| `/Game/Env/HS/UNSC/MAW/Wreckage/UNSC_MAW_Wreckage_Uhull_panel_G/SM_UNSC_MAW_Wreckage_Uhull_panel_G` | StaticMesh | 0.37 | 10,340 | 3.38x4.35x2.26 | D40,E30 | no | [collision] |
| `/Game/Env/HS/UNSC/MAW/Wreckage/UNSC_MAW_Wreckage_Uhull_support_A/SM_UNSC_MAW_Wreckage_Uhull_support_A` | StaticMesh | 0.66 | 20,114 | 14.1x1.31x6.84 | D40,E30 | no | [collision] |
| `/Game/Env/HS/UNSC/MAW/Wreckage/UNSC_MAW_Wreckage_Uhull_support_B/SM_UNSC_MAW_Wreckage_Uhull_support_B` | StaticMesh | 1.07 | 28,836 | 14.21x0.26x6.35 | D40,E30 | no | [collision] |
| `/Game/Env/HS/UNSC/MAW/Wreckage/UNSC_MAW_Wreckage_Uhull_support_C/SM_UNSC_MAW_Wreckage_Uhull_support_C` | StaticMesh | 0.61 | 16,230 | 0.68x8.26x0.44 | D40,E30 | no | [collision] |
| `/Game/Env/HS/UNSC/MAW/Wreckage/UNSC_MAW_Wreckage_Uhull_support_D/SM_UNSC_MAW_Wreckage_Uhull_support_D` | StaticMesh | 0.21 | 5,385 | 4.08x1.41x0.4 | D40,E30 | no | [collision] |
| `/Game/Env/HS/UNSC/MAW/Wreckage/UNSC_MAW_Wreckage_Uhull_support_E/SM_UNSC_MAW_Wreckage_Uhull_support_E` | StaticMesh | 3.70 | 100,831 | 1.65x2.81x2.13 | D40,E30 | no | [collision] |
| `/Game/Env/HS/UNSC/MAW/Wreckage/UNSC_MAW_Wreckage_Uhull_support_F/SM_UNSC_MAW_Wreckage_Uhull_support_F` | StaticMesh | 1.43 | 43,106 | 2.3x2.06x2.28 | D40,E30 | no | [collision] |
| `/Game/Env/HS/UNSC/MAW/Wreckage/UNSC_MAW_Wreckage_Uhull_support_H/SM_UNSC_MAW_Wreckage_Uhull_support_H` | StaticMesh | 1.06 | 34,115 | 2.52x20.64x1.09 | D40,E30 | no | packed AO/roughness/height map [collision] |
| `/Game/Env/HS/UNSC/MAW/Wreckage/UNSC_MAW_Wreckage_Uhull_tech_panel_A/SM_UNSC_MAW_Wreckage_Uhull_tech_panel_A` | StaticMesh | 1.87 | 58,875 | 11.82x10.42x3.68 | D40,E30 | no | [collision] |
| `/Game/Env/HS/UNSC/MAW/Wreckage/UNSC_MAW_Wreckage_Uhull_tech_panel_B/SM_UNSC_MAW_Wreckage_Uhull_tech_panel_B` | StaticMesh | 0.87 | 25,742 | 7.59x5.6x1.01 | D40,E30 | no | [collision] |
| `/Game/Env/HS/UNSC/MAW/Wreckage/UNSC_MAW_Wreckage_Uhull_tech_panel_C/SM_UNSC_MAW_Wreckage_Uhull_tech_panel_C` | StaticMesh | 0.42 | 12,904 | 10.51x3.31x1.01 | D40,E30 | no | [collision] |
| `/Game/Env/HS/UNSC/MAW/Wreckage/UNSC_MAW_Wreckage_Wing_Bottom_Armor_A/SM_UNSC_MAW_Wreckage_Wing_Bottom_Armor_A` | StaticMesh | 1.72 | 42,810 | 15.44x72.44x32.43 | D40,E30 | no | [collision] |
| `/Game/Env/HS/UNSC/MAW/Wreckage/UNSC_MAW_Wreckage_Wing_Skel_A/SM_UNSC_MAW_Wreckage_Wing_Skel_A` | StaticMesh | 16.69 | 425,272 | 16.98x88.73x85.61 | D40,E30 | no | very dense: confirm Nanite before placing many [collision] |
| `/Game/Env/HS/UNSC/MAW/Wreckage/UNSC_MAW_Wreckage_Wing_Top_Armor_A/SM_UNSC_MAW_Wreckage_Wing_Top_Armor_A` | StaticMesh | 2.17 | 54,448 | 7.5x88.15x49.37 | D40,E30 | no | [collision] |
| `/Game/Env/HS/UNSC/MAW/Wreckage/UNSC_MAW_Wreckage_detail_A/SM_UNSC_MAW_Wreckage_detail_A` | StaticMesh | 0.51 | 15,746 | 2.29x0.64x0.91 | D40,E30 | no | [collision] |
| `/Game/Env/HS/UNSC/MAW/Wreckage/UNSC_MAW_Wreckage_detail_B/SM_UNSC_MAW_Wreckage_detail_B` | StaticMesh | 0.49 | 15,193 | 1.71x0.17x0.87 | D40,E30 | no | [collision] |
| `/Game/Env/HS/UNSC/MAW/Wreckage/UNSC_MAW_Wreckage_pipe_A/SM_UNSC_MAW_Wreckage_pipe_A` | StaticMesh | 0.21 | 6,200 | 0.77x4.0x0.78 | D40,E30 | no | [collision] |
| `/Game/Env/HS/UNSC/MAW/Wreckage/UNSC_MAW_Wreckage_pipe_B/SM_UNSC_MAW_Wreckage_pipe_B` | StaticMesh | 0.26 | 8,021 | 0.78x2.0x0.78 | D40,E30 | no | [collision] |
| `/Game/Env/HS/UNSC/MAW/Wreckage/UNSC_MAW_Wreckage_pipe_C/SM_UNSC_MAW_Wreckage_pipe_C` | StaticMesh | 1.12 | 36,011 | 0.9x1.65x0.91 | D40,E30 | no | [collision] |
| `/Game/Env/HS/UNSC/MAW/Wreckage/UNSC_MAW_Wreckage_pipe_D/SM_UNSC_MAW_Wreckage_pipe_D` | StaticMesh | 0.32 | 8,937 | 2.23x2.75x0.78 | D40,E30 | no | [collision] |
| `/Game/Env/HS/UNSC/MAW/Wreckage/UNSC_MAW_Wreckage_pipe_E/SM_UNSC_MAW_Wreckage_pipe_E` | StaticMesh | 0.37 | 10,557 | 1.13x3.63x1.39 | D40,E30 | no | [collision] |
| `/Game/Env/HS/UNSC/MAW/Wreckage/UNSC_MAW_Wreckage_tech_A/SM_UNSC_MAW_Wreckage_tech_A` | StaticMesh | 4.79 | 151,011 | 10.25x2.63x4.24 | D40,E30 | no | [collision] |
| `/Game/Env/HS/UNSC/MAW/Wreckage/UNSC_MAW_Wreckage_tech_B/SM_UNSC_MAW_Wreckage_tech_B` | StaticMesh | 4.10 | 129,601 | 4.83x1.97x2.04 | D40,E30 | no | [collision] |
| `/Game/Env/HS/UNSC/MAW/Wreckage/UNSC_MAW_Wreckage_tech_C/SM_UNSC_MAW_Wreckage_tech_C` | StaticMesh | 0.88 | 27,850 | 3.69x12.34x3.0 | D40,E30 | no | [collision] |

*Group note:* Pillar of Autumn hull, girders, pipes; e30 wreckage has matching Blam crate tags

### Escape pod exterior (A15) (9)

*Where on PWR:* Crash site

| path | kind | MB | verts | bounds m | levels | PWR | note |
|---|---|---|---|---|---|---|---|
| `/Game/Env/HS/UNSC/POA/EscapePods_Exterior_A15/SM_EscapePods_Exterior_A15` | StaticMesh | 0.04 | 427 | 3.41x38.59x76.44 | A15 | no |  |
| `/Game/Env/HS/UNSC/POA/EscapePods_Exterior_A15/SM_UNSC_EscapePods_Exterior_A15_B` | StaticMesh | 0.18 | 5,749 | 67.02x8.07x88.9 | A15 | no |  |
| `/Game/Env/HS/UNSC/POA/EscapePods_Exterior_A15/SM_UNSC_EscapePods_Exterior_A15_B_Details` | StaticMesh | 0.55 | 16,762 | 70.28x7.15x74.16 | A15 | no |  |
| `/Game/Env/HS/UNSC/POA/EscapePods_Exterior_A15/SM_UNSC_EscapePods_Exterior_A15_C` | StaticMesh | 0.92 | 24,354 | 37.38x153.92x516.12 | A15 | no |  |
| `/Game/Env/HS/UNSC/POA/EscapePods_Exterior_A15/SM_UNSC_EscapePods_Exterior_A15_C_Details` | StaticMesh | 1.49 | 46,127 | 18.11x90.86x422.96 | A15 | no |  |
| `/Game/Env/HS/UNSC/POA/EscapePods_Exterior_A15/SM_UNSC_EscapePods_Exterior_A15_D` | StaticMesh | 0.06 | 1,578 | 94.54x115.51x158.65 | A15 | no |  |
| `/Game/Env/HS/UNSC/POA/EscapePods_Exterior_A15/SM_UNSC_EscapePods_Exterior_A15_D_Details` | StaticMesh | 0.24 | 7,295 | 80.26x83.58x147.36 | A15 | no |  |
| `/Game/Env/HS/UNSC/POA/EscapePods_Exterior_A15/SM_UNSC_EscapePods_Exterior_A15_E` | StaticMesh | 0.15 | 4,629 | 79.65x135.83x173.39 | A15 | no |  |
| `/Game/Env/HS/UNSC/POA/EscapePods_Exterior_A15/SM_UNSC_EscapePods_Exterior_A15_F` | StaticMesh | 1.59 | 44,250 | 3.85x21.81x83.74 | A15 | no |  |

*Group note:* A15 escape pod exterior pieces

### Crashed UNSC vehicles (static) (18)

*Where on PWR:* Crash sites on the meadow, wreck at a river ford

| path | kind | MB | verts | bounds m | levels | PWR | note |
|---|---|---|---|---|---|---|---|
| `/Game/Env/HS/UNSC/Vehicles/Longsword/SM_Longsword_Closed_Static` | StaticMesh | 17.98 | 491,736 | 33.36x33.71x6.84 | D40 | no | very dense: confirm Nanite before placing many [collision] |
| `/Game/Env/HS/UNSC/Vehicles/Longsword/SM_Longsword_OpenGlass_Static` | StaticMesh | 0.13 | 2,114 | 4.08x1.38x5.08 | D40 | no | [collision] |
| `/Game/Env/HS/UNSC/Vehicles/Longsword/SM_Longsword_Open_Static` | StaticMesh | 20.95 | 562,926 | 33.36x33.71x10.75 | D40 | no | very dense: confirm Nanite before placing many [collision] |
| `/Game/Env/HS/UNSC/Vehicles/Scorpion/Damaged/SM_Scorpion_Full_Destroyed` | StaticMesh | 33.90 | 754,051 | 7.94x11.38x4.86 | D40 | no | very dense: confirm Nanite before placing many [collision] |
| `/Game/Env/HS/UNSC/Vehicles/Scorpion/Damaged/SM_Scorpion_Turret_Abscission_Damaged` | StaticMesh | 6.53 | 169,219 | 3.49x5.22x2.01 | D40 | no | [collision] |
| `/Game/Env/HS/UNSC/Vehicles/pelican/Damaged/SM_Pelican_Body_Damaged` | StaticMesh | 67.09 | 1,198,261 | 30.04x9.61x20.86 | B40,C10,C45,D40 | no | very dense: confirm Nanite before placing many [collision] |
| `/Game/Env/HS/UNSC/Vehicles/pelican/Damaged/SM_Pelican_DoorA_Damaged` | StaticMesh | 3.12 | 55,241 | 2.0x4.39x1.36 | B40,C10,C45 | no | [collision] |
| `/Game/Env/HS/UNSC/Vehicles/pelican/Damaged/SM_Pelican_DoorB_Damaged` | StaticMesh | 1.73 | 36,256 | 1.62x3.52x1.02 | B40,C45 | no | [collision] |
| `/Game/Env/HS/UNSC/Vehicles/pelican/Damaged/SM_Pelican_Engine_Leftt_Damaged` | StaticMesh | 7.13 | 120,328 | 7.2x4.98x4.5 | B40,C10,C45,D40 | no | [collision] |
| `/Game/Env/HS/UNSC/Vehicles/pelican/Damaged/SM_Pelican_Engine_Right_Damaged` | StaticMesh | 7.42 | 119,222 | 7.2x5.0x4.4 | B40,C10,C45,D40 | no | [collision] |
| `/Game/Env/HS/UNSC/Vehicles/pelican/Damaged/SM_Pelican_Gun_Damaged` | StaticMesh | 3.41 | 62,700 | 2.74x0.93x0.89 | B40,C45 | no | [collision] |
| `/Game/Env/HS/UNSC/Vehicles/pelican/Damaged/SM_Pelican_LangingGear_Left_Damaged` | StaticMesh | 2.90 | 47,472 | 7.94x2.41x3.68 | B40,C10,C45 | no | [collision] |
| `/Game/Env/HS/UNSC/Vehicles/pelican/Damaged/SM_Pelican_LangingGear_Right_Damaged` | StaticMesh | 2.87 | 49,216 | 7.94x2.42x3.68 | B40,C10,C45 | no | [collision] |
| `/Game/Env/HS/UNSC/Vehicles/pelican/Damaged/SM_Pelican_WingFlap_Damaged` | StaticMesh | 0.23 | 2,042 | 1.02x3.1x0.34 | B40,C45 | no | [collision] |
| `/Game/Env/HS/UNSC/Vehicles/pelican/Damaged/SM_Pelican_Wing_Left_Damaged` | StaticMesh | 8.04 | 141,549 | 8.38x7.61x5.27 | B40,C10,C45,D40 | no | [collision] |
| `/Game/Env/HS/UNSC/Vehicles/pelican/Damaged/SM_Pelican_Wing_Right_Damaged` | StaticMesh | 7.73 | 148,688 | 8.39x8.74x5.27 | B40,C45,D40 | no | [collision] |
| `/Game/Env/HS/UNSC/Vehicles/warthog/SM_Warthog_BodyPanels_Static` | StaticMesh | 0.45 | 9,555 | 5.82x2.75x1.06 | D40 | no | [collision] |
| `/Game/Env/HS/UNSC/Vehicles/warthog/SM_Warthog_Body_Static` | StaticMesh | 3.67 | 91,553 | 5.96x3.07x2.34 | D40 | no | [collision] |

*Group note:* Damaged Pelican parts, destroyed Scorpion, Warthog body, Longsword statics

### Forerunner FX objects (beams, light bridges, holograms) (41)

*Where on PWR:* Base cores, beacon beams, light bridge shimmer, sentinels in the sky

| path | kind | MB | verts | bounds m | levels | PWR | note |
|---|---|---|---|---|---|---|---|
| `/Game/FX/Library/Environment/Forerunner/Creatures/ConstructorSentinel/BP_For_ConstructionSentinels_OpenSpline` | Blueprint | 0.01 |  |  | A30,A50,B30 | no |  |
| `/Game/FX/Library/Environment/Forerunner/Creatures/ConstructorSentinel/NS_For_ConstructionSentinel_Boids` | NiagaraSystem | 0.10 |  |  | A30,A50,B30 | no |  |
| `/Game/FX/Library/Environment/Forerunner/Creatures/Quadwing/BP_Quadwing` | Blueprint | 0.01 |  |  | A30 | no |  |
| `/Game/FX/Library/Environment/Forerunner/Creatures/Quadwing/NS_Quadwing_Fly` | NiagaraSystem | 0.03 |  |  | A30 | no |  |
| `/Game/FX/Library/Environment/Forerunner/objects/BlueEnergyBeam/NS_BlueEnergyBeam_Base_Idle` | NiagaraSystem | 0.09 |  |  | A30 | no |  |
| `/Game/FX/Library/Environment/Forerunner/objects/BlueEnergyBeam/NS_BlueEnergyBeam_Projectile` | NiagaraSystem | 0.27 |  |  | A30 | no |  |
| `/Game/FX/Library/Environment/Forerunner/objects/CloudSpire/NS_Skybeam_CloudGlow` | NiagaraSystem | 0.03 |  |  | B30 | no |  |
| `/Game/FX/Library/Environment/Forerunner/objects/EnergyColumn/NS_For_EnergyColumn_Accelerator` | NiagaraSystem | 0.02 |  |  | B40,C45 | no |  |
| `/Game/FX/Library/Environment/Forerunner/objects/EnergyColumn/NS_For_EnergyColumn_Back` | NiagaraSystem | 0.06 |  |  | B40,C45 | no |  |
| `/Game/FX/Library/Environment/Forerunner/objects/EnergyColumn/NS_For_EnergyColumn_FrontBeam` | NiagaraSystem | 0.22 |  |  | B40,C45 | no |  |
| `/Game/FX/Library/Environment/Forerunner/objects/FloatingEnergyBeam/NS_For_FloatingEnergyBeam_01` | NiagaraSystem | 0.21 |  |  | B40 | no |  |
| `/Game/FX/Library/Environment/Forerunner/objects/ForBridgeEnergyTether/BP_For_BridgeEnergyTether` | Blueprint | 0.00 |  |  | B40,C45 | no |  |
| `/Game/FX/Library/Environment/Forerunner/objects/ForBridgeEnergyTether/NS_For_BrigdeEnergyTether_01` | NiagaraSystem | 0.08 |  |  | B40,C45 | no |  |
| `/Game/FX/Library/Environment/Forerunner/objects/ForerunnerTower/A30_ForTowers/BP_Forerunner_Beam_Fire` | Blueprint | 0.02 |  |  | A30 | no |  |
| `/Game/FX/Library/Environment/Forerunner/objects/ForerunnerTower/A30_ForTowers/NS_ForTower_BeamChargeup` | NiagaraSystem | 0.09 |  |  | A30 | no |  |
| `/Game/FX/Library/Environment/Forerunner/objects/ForerunnerTower/A30_ForTowers/NS_ForTower_BeamFiring` | NiagaraSystem | 0.10 |  |  | A30 | no |  |
| `/Game/FX/Library/Environment/Forerunner/objects/ForerunnerTower/B30_ForStructure/NS_B30_ForStructure_CoreBeam` | NiagaraSystem | 0.07 |  |  | B30 | no |  |
| `/Game/FX/Library/Environment/Forerunner/objects/ForerunnerTower/NS_ForTower_ChargeupEnergy` | NiagaraSystem | 0.08 |  |  | A30 | no |  |
| `/Game/FX/Library/Environment/Forerunner/objects/ForerunnerTower/NS_ForTower_Idle_Energy` | NiagaraSystem | 0.07 |  |  | A30 | no |  |
| `/Game/FX/Library/Environment/Forerunner/objects/Holograms/C20/Navigation/NS_For_Forerunner_Navigation_01` | NiagaraSystem | 0.08 |  |  | C20 | no |  |
| `/Game/FX/Library/Environment/Forerunner/objects/Holograms/C20/Navigation/NS_For_Forerunner_Navigation_02` | NiagaraSystem | 0.07 |  |  | C20 | no |  |
| `/Game/FX/Library/Environment/Forerunner/objects/Holograms/C20/Navigation/NS_For_Forerunner_Navigation_03` | NiagaraSystem | 0.03 |  |  | C20 | no |  |
| `/Game/FX/Library/Environment/Forerunner/objects/Holograms/NS_For_HoloSymbols_Row` | NiagaraSystem | 0.04 |  |  | B30 | no |  |
| `/Game/FX/Library/Environment/Forerunner/objects/Holograms/SnowBridgeNavigation/BP_FOR_Hologram_Snow_Bridge_A` | Blueprint | 0.00 |  |  | B40,C45 | no | snow variant |
| `/Game/FX/Library/Environment/Forerunner/objects/Holograms/SnowBridgeNavigation/BP_FOR_Hologram_Snow_Bridge_B` | Blueprint | 0.00 |  |  | B40,C45 | no | snow variant |
| `/Game/FX/Library/Environment/Forerunner/objects/Holograms/SnowBridgeNavigation/BP_FOR_Hologram_Snow_Bridge_Int_A_NC` | Blueprint | 0.00 |  |  | B40,C45 | no | snow variant |
| `/Game/FX/Library/Environment/Forerunner/objects/Holograms/SnowBridgeNavigation/BP_FOR_Hologram_Snow_Bridge_Int_B_NC` | Blueprint | 0.00 |  |  | B40,C45 | no | snow variant |
| `/Game/FX/Library/Environment/Forerunner/objects/Holograms/SnowBridgeNavigation/BP_FOR_Hologram_Snow_Bridge_Int_C_NC` | Blueprint | 0.00 |  |  | B40,C45 | no | snow variant |
| `/Game/FX/Library/Environment/Forerunner/objects/Holograms/SnowBridgeNavigation/BP_FOR_Hologram_Snow_Bridge_Int_D_NC` | Blueprint | 0.00 |  |  | B40,C45 | no | snow variant |
| `/Game/FX/Library/Environment/Forerunner/objects/Holograms/SnowBridgeNavigation/NS_FOR_Hologram_Snow_Bridge_A` | NiagaraSystem | 0.03 |  |  | B40,C45 | no | snow variant |
| `/Game/FX/Library/Environment/Forerunner/objects/Holograms/SnowBridgeNavigation/NS_FOR_Hologram_Snow_Bridge_B` | NiagaraSystem | 0.03 |  |  | B40,C45 | no | snow variant |
| `/Game/FX/Library/Environment/Forerunner/objects/Holograms/SnowBridgeNavigation/NS_FOR_Hologram_Snow_Bridge_Int_A` | NiagaraSystem | 0.03 |  |  | B40,C45 | no | snow variant |
| `/Game/FX/Library/Environment/Forerunner/objects/Holograms/SnowBridgeNavigation/NS_FOR_Hologram_Snow_Bridge_Int_B` | NiagaraSystem | 0.03 |  |  | B40,C45 | no | snow variant |
| `/Game/FX/Library/Environment/Forerunner/objects/Holograms/SnowBridgeNavigation/NS_FOR_Hologram_Snow_Bridge_Int_C` | NiagaraSystem | 0.03 |  |  | B40,C45 | no | snow variant |
| `/Game/FX/Library/Environment/Forerunner/objects/Holograms/SnowBridgeNavigation/NS_FOR_Hologram_Snow_Bridge_Int_D` | NiagaraSystem | 0.03 |  |  | B40,C45 | no | snow variant |
| `/Game/FX/Library/Environment/Forerunner/objects/Holograms/SnowBridgeNavigation/NS_FOR_Hologram_Snow_Bridge_Int_D_2` | NiagaraSystem | 0.02 |  |  | B40,C45 | no | snow variant |
| `/Game/FX/Library/Environment/Forerunner/objects/LightBridge/A30/NS_For_LightBridge_A30` | NiagaraSystem | 0.01 |  |  | A30 | no |  |
| `/Game/FX/Library/Environment/Forerunner/objects/LightBridge/C10/NS_For_LightBridge_C10_Flickering` | NiagaraSystem | 0.07 |  |  | C10 | no |  |
| `/Game/FX/Library/Environment/Forerunner/objects/LightBridge/NS_FR_LightBridge_Shared` | NiagaraSystem | 0.07 |  |  | A30,B40,C10,C20,C45 | no |  |
| `/Game/FX/Library/Environment/Forerunner/objects/LightBridge/NS_Lightbridge_Flare` | NiagaraSystem | 0.08 |  |  | A30,B40,C10,C20,C45 | no |  |
| `/Game/FX/Library/Environment/Forerunner/objects/conduit/NS_ConduitAmbient` | NiagaraSystem | 0.16 |  |  |  | no |  |

*Group note:* Shipped Niagara

### UNSC FX (steam, sparks, fire) (32)

*Where on PWR:* Burning wrecks, sparking crash sites

| path | kind | MB | verts | bounds m | levels | PWR | note |
|---|---|---|---|---|---|---|---|
| `/Game/FX/Library/Environment/UNSC/Atmospherics/Frost/NS_UNSC_Frost_TankVapor` | NiagaraSystem | 0.04 |  |  | A15 | no |  |
| `/Game/FX/Library/Environment/UNSC/Atmospherics/SprayingSteamHose/BP_UNSC_SprayingSteamHose` | Blueprint | 0.01 |  |  | A15 | no |  |
| `/Game/FX/Library/Environment/UNSC/Atmospherics/SprayingSteamHose/NS_USNC_SprayingSteam_01` | NiagaraSystem | 0.07 |  |  | A15 | no |  |
| `/Game/FX/Library/Environment/UNSC/Atmospherics/Steam/NS_UNSC_SteamBurst` | NiagaraSystem | 0.14 |  |  | D40 | no |  |
| `/Game/FX/Library/Environment/UNSC/Atmospherics/Steam/NS_UNSC_SteamBurst_Small` | NiagaraSystem | 0.14 |  |  |  | no |  |
| `/Game/FX/Library/Environment/UNSC/Atmospherics/Steam/NS_USNC_SteamJet_Sml_01` | NiagaraSystem | 0.10 |  |  | A15,D40 | no |  |
| `/Game/FX/Library/Environment/UNSC/Atmospherics/Steam/NS_USNC_Steam_Lrg_01` | NiagaraSystem | 0.10 |  |  | D40 | no |  |
| `/Game/FX/Library/Environment/UNSC/Atmospherics/Steam/NS_USNC_Steam_Med_01` | NiagaraSystem | 0.10 |  |  | C20,D40 | no |  |
| `/Game/FX/Library/Environment/UNSC/Atmospherics/Steam/NS_USNC_Steam_Sml_01` | NiagaraSystem | 0.13 |  |  | A15,D40 | no |  |
| `/Game/FX/Library/Environment/UNSC/Atmospherics/Steam/NS_USNC_Steam_XLrg_01_NoRibbon` | NiagaraSystem | 0.07 |  |  | D40 | no |  |
| `/Game/FX/Library/Environment/UNSC/Destruction/Electricity/Sparks/NS_Elec_PeriodicSparks` | NiagaraSystem | 0.23 |  |  | C10 | no |  |
| `/Game/FX/Library/Environment/UNSC/Destruction/Electricity/Sparks/NS_Elec_SparkBurst_With_Collision` | NiagaraSystem | 0.14 |  |  | A15,B30,D40 | no |  |
| `/Game/FX/Library/Environment/UNSC/Destruction/Electricity/Sparks/NS_UNSC_Elec_Spark` | NiagaraSystem | 0.18 |  |  | D40 | no |  |
| `/Game/FX/Library/Environment/UNSC/Destruction/Electricity/Sparks/NS_UNSC_Elec_Spark_Burst_Lrg` | NiagaraSystem | 0.11 |  |  |  | no |  |
| `/Game/FX/Library/Environment/UNSC/Destruction/Electricity/Sparks/NS_UNSC_Elec_Spark_Shower` | NiagaraSystem | 0.12 |  |  |  | no |  |
| `/Game/FX/Library/Environment/UNSC/Destruction/Electricity/Sparks/NS_UNSC_SparkBurst_01` | NiagaraSystem | 0.15 |  |  | A15,A30,C10,D40 | no |  |
| `/Game/FX/Library/Environment/UNSC/Destruction/Electricity/Sparks/NS_UNSC_SparkBurst_NET25000` | NiagaraSystem | 0.19 |  |  | D40 | no |  |
| `/Game/FX/Library/Environment/UNSC/Destruction/Electricity/Sparks/NS_UNSC_SparkBurst_NET7500` | NiagaraSystem | 0.19 |  |  | A15,C45,D40 | no |  |
| `/Game/FX/Library/Environment/UNSC/Destruction/Electricity/Sparks/NS_USNC_Sparks_01` | NiagaraSystem | 0.18 |  |  | D40 | no |  |
| `/Game/FX/Library/Environment/UNSC/Destruction/Fire/NS_UNSC_FireDripping` | NiagaraSystem | 0.14 |  |  | A30,B30,B40,C10,D20,D40 | no |  |
| `/Game/FX/Library/Environment/UNSC/Destruction/Fire/NS_UNSC_FireLedge_Hor_01` | NiagaraSystem | 0.11 |  |  | A15,A30,B30,C10,D20,D40 | no |  |
| `/Game/FX/Library/Environment/UNSC/Destruction/Fire/NS_UNSC_FireLedge_Hor_02` | NiagaraSystem | 0.14 |  |  | A15,C10,D20,D40 | no |  |
| `/Game/FX/Library/Environment/UNSC/Destruction/Fire/NS_UNSC_FireLedge_Hor_03` | NiagaraSystem | 0.11 |  |  | D40 | no |  |
| `/Game/FX/Library/Environment/UNSC/Destruction/Fire/NS_UNSC_FireLedge_Lean_01` | NiagaraSystem | 0.14 |  |  | B40,D20,D40 | no |  |
| `/Game/FX/Library/Environment/UNSC/Destruction/Fire/NS_UNSC_FirePipeLrg_01` | NiagaraSystem | 0.05 |  |  | D40 | no |  |
| `/Game/FX/Library/Environment/UNSC/Destruction/Fire/NS_UNSC_Fire_BurnmarkDecal_01` | NiagaraSystem | 0.02 |  |  | A15,A30,B30,C10 | no | [decal] |
| `/Game/FX/Library/Environment/UNSC/Destruction/Fire/NS_UNSC_Fire_Circle_01` | NiagaraSystem | 0.07 |  |  | A30 | no |  |
| `/Game/FX/Library/Environment/UNSC/Destruction/Smoke/SmokeCrawling/NS_UNSC_Smk_Crawling_Transmissive` | NiagaraSystem | 0.05 |  |  | A30 | no |  |
| `/Game/FX/Library/Environment/UNSC/Destruction/Smoke/SmokeCrawling/NS_UNSC_SmokeCrawling` | NiagaraSystem | 0.09 |  |  | A15,B30,D40 | no |  |
| `/Game/FX/Library/Environment/UNSC/Destruction/Smoke/SmokeCrawling/NS_UNSC_SmokeCrawling_NoBase` | NiagaraSystem | 0.05 |  |  | A15,A30,B30,B40,C10,C45,D40 | no |  |
| `/Game/FX/Library/Environment/UNSC/Destruction/Smoke/SmokeCrawling/NS_UNSC_SmokeCrawling_NoBase_A15` | NiagaraSystem | 0.05 |  |  | A15,D40 | no |  |
| `/Game/FX/Library/Environment/UNSC/Destruction/Smoke/SmokeCrawling/NS_UNSC_SmokeCrawling_NoBase_Unlit` | NiagaraSystem | 0.05 |  |  | D40 | no |  |

*Group note:* Shipped Niagara

### A30 lifepod crash debris and crash mound (45)

*Where on PWR:* Crash site near an LZ: torn lifepod, 21 debris pieces, scorched mud mound

| path | kind | MB | verts | bounds m | levels | PWR | note |
|---|---|---|---|---|---|---|---|
| `/Game/Levels/Halo1/Solo/A30/Landscape/Crash_Site_Mound/Mesh/MI_Crash_Site_Mud` | MaterialInstance | 0.15 |  |  | A30,C10,D40 | no | [collision] |
| `/Game/Levels/Halo1/Solo/A30/Landscape/Crash_Site_Mound/Mesh/MI_Crash_Site_Mud_Wet` | MaterialInstance | 0.08 |  |  | C10 | no | wet variant [collision] |
| `/Game/Levels/Halo1/Solo/A30/Landscape/Crash_Site_Mound/Mesh/MI_Soil_Clay` | MaterialInstance | 0.12 |  |  | A30 | no | [collision] |
| `/Game/Levels/Halo1/Solo/A30/Landscape/Crash_Site_Mound/Mesh/SM_A30_Crash_Site_Mound` | StaticMesh | 2.17 | 84,209 | 3.09x2.85x0.76 | A30 | no | [collision] |
| `/Game/Levels/Halo1/Solo/A30/Landscape/Crash_Site_Mound/Mesh/SM_Crash_Site_01` | StaticMesh | 1.21 | 35,134 | 16.98x38.94x5.1 | A30 | no | [collision] |
| `/Game/Levels/Halo1/Solo/A30/Vehicle/Lifepod/A30_LifePod_Damaged/Material/MI_LifePod_Button` | MaterialInstance | 0.14 |  |  | A30 | no | [collision] |
| `/Game/Levels/Halo1/Solo/A30/Vehicle/Lifepod/A30_LifePod_Damaged/Material/MI_LifePod_External_Bare_Metal` | MaterialInstance | 0.36 |  |  | A30 | no | [collision] |
| `/Game/Levels/Halo1/Solo/A30/Vehicle/Lifepod/A30_LifePod_Damaged/Material/MI_LifePod_External_Body_01` | MaterialInstance | 0.25 |  |  | A30 | no | [collision] |
| `/Game/Levels/Halo1/Solo/A30/Vehicle/Lifepod/A30_LifePod_Damaged/Material/MI_LifePod_External_Body_02` | MaterialInstance | 0.31 |  |  | A30 | no | [collision] |
| `/Game/Levels/Halo1/Solo/A30/Vehicle/Lifepod/A30_LifePod_Damaged/Material/MI_LifePod_External_Metal` | MaterialInstance | 0.30 |  |  | A30 | no | [collision] |
| `/Game/Levels/Halo1/Solo/A30/Vehicle/Lifepod/A30_LifePod_Damaged/Material/MI_LifePod_Interior_01` | MaterialInstance | 0.36 |  |  | A30 | no | [collision] |
| `/Game/Levels/Halo1/Solo/A30/Vehicle/Lifepod/A30_LifePod_Damaged/Material/MI_LifePod_Interior_02` | MaterialInstance | 0.33 |  |  | A30 | no | [collision] |
| `/Game/Levels/Halo1/Solo/A30/Vehicle/Lifepod/A30_LifePod_Damaged/Material/MI_LifePod_Interior_Lights` | MaterialInstance | 0.13 |  |  | A30 | no | [collision] |
| `/Game/Levels/Halo1/Solo/A30/Vehicle/Lifepod/A30_LifePod_Damaged/Material/MI_LifePod_Interior_Screen` | MaterialInstance | 0.13 |  |  | A30 | no | [collision] |
| `/Game/Levels/Halo1/Solo/A30/Vehicle/Lifepod/A30_LifePod_Damaged/Material/ML_UNSC_DMG_01` | MaterialLayerInstance | 0.00 |  |  | A30 | no | [collision] |
| `/Game/Levels/Halo1/Solo/A30/Vehicle/Lifepod/A30_LifePod_Damaged/Material/ML_UNSC_Mud_01` | MaterialLayerInstance | 0.00 |  |  | A30 | no | [collision] |
| `/Game/Levels/Halo1/Solo/A30/Vehicle/Lifepod/A30_LifePod_Damaged/SM_A30_Lifepod_Debris_01` | StaticMesh | 0.21 | 3,588 | 1.93x2.08x0.93 | A30 | no | [collision] |
| `/Game/Levels/Halo1/Solo/A30/Vehicle/Lifepod/A30_LifePod_Damaged/SM_A30_Lifepod_Debris_02` | StaticMesh | 0.73 | 15,933 | 4.78x4.46x1.49 | A30 | no | [collision] |
| `/Game/Levels/Halo1/Solo/A30/Vehicle/Lifepod/A30_LifePod_Damaged/SM_A30_Lifepod_Debris_03` | StaticMesh | 0.33 | 7,211 | 2.25x2.79x0.86 | A30 | no | [collision] |
| `/Game/Levels/Halo1/Solo/A30/Vehicle/Lifepod/A30_LifePod_Damaged/SM_A30_Lifepod_Debris_04` | StaticMesh | 0.59 | 12,752 | 1.35x6.83x1.42 | A30 | no | [collision] |
| `/Game/Levels/Halo1/Solo/A30/Vehicle/Lifepod/A30_LifePod_Damaged/SM_A30_Lifepod_Debris_05` | StaticMesh | 0.09 | 1,439 | 1.02x2.33x0.32 | A30 | no | [collision] |
| `/Game/Levels/Halo1/Solo/A30/Vehicle/Lifepod/A30_LifePod_Damaged/SM_A30_Lifepod_Debris_06` | StaticMesh | 0.18 | 2,230 | 1.33x1.18x0.73 |  | no | [collision] |
| `/Game/Levels/Halo1/Solo/A30/Vehicle/Lifepod/A30_LifePod_Damaged/SM_A30_Lifepod_Debris_07` | StaticMesh | 1.14 | 20,499 | 3.71x2.63x1.85 | A30 | no | [collision] |
| `/Game/Levels/Halo1/Solo/A30/Vehicle/Lifepod/A30_LifePod_Damaged/SM_A30_Lifepod_Debris_08` | StaticMesh | 1.21 | 23,422 | 3.61x5.13x2.07 |  | no | [collision] |
| `/Game/Levels/Halo1/Solo/A30/Vehicle/Lifepod/A30_LifePod_Damaged/SM_A30_Lifepod_Debris_09` | StaticMesh | 1.43 | 28,091 | 1.45x2.35x0.6 | A30 | no | [collision] |
| `/Game/Levels/Halo1/Solo/A30/Vehicle/Lifepod/A30_LifePod_Damaged/SM_A30_Lifepod_Debris_10` | StaticMesh | 0.09 | 1,075 | 0.94x0.94x0.33 |  | no | [collision] |
| `/Game/Levels/Halo1/Solo/A30/Vehicle/Lifepod/A30_LifePod_Damaged/SM_A30_Lifepod_Debris_11` | StaticMesh | 0.15 | 2,400 | 0.85x1.0x0.28 |  | no | [collision] |
| `/Game/Levels/Halo1/Solo/A30/Vehicle/Lifepod/A30_LifePod_Damaged/SM_A30_Lifepod_Debris_12` | StaticMesh | 0.11 | 1,723 | 0.7x1.09x0.65 |  | no | [collision] |
| `/Game/Levels/Halo1/Solo/A30/Vehicle/Lifepod/A30_LifePod_Damaged/SM_A30_Lifepod_Debris_13` | StaticMesh | 0.09 | 1,286 | 1.28x0.86x0.33 |  | no | [collision] |
| `/Game/Levels/Halo1/Solo/A30/Vehicle/Lifepod/A30_LifePod_Damaged/SM_A30_Lifepod_Debris_14` | StaticMesh | 0.08 | 876 | 0.99x0.99x0.28 |  | no | [collision] |
| `/Game/Levels/Halo1/Solo/A30/Vehicle/Lifepod/A30_LifePod_Damaged/SM_A30_Lifepod_Debris_15` | StaticMesh | 0.13 | 1,886 | 1.15x0.8x0.66 |  | no | [collision] |
| `/Game/Levels/Halo1/Solo/A30/Vehicle/Lifepod/A30_LifePod_Damaged/SM_A30_Lifepod_Debris_16` | StaticMesh | 0.10 | 1,590 | 1.79x1.27x0.43 |  | no | [collision] |
| `/Game/Levels/Halo1/Solo/A30/Vehicle/Lifepod/A30_LifePod_Damaged/SM_A30_Lifepod_Debris_17` | StaticMesh | 0.26 | 5,179 | 0.49x1.03x0.1 |  | no | [collision] |
| `/Game/Levels/Halo1/Solo/A30/Vehicle/Lifepod/A30_LifePod_Damaged/SM_A30_Lifepod_Debris_18` | StaticMesh | 0.04 | 167 | 0.15x0.8x0.56 |  | no | [collision] |
| `/Game/Levels/Halo1/Solo/A30/Vehicle/Lifepod/A30_LifePod_Damaged/SM_A30_Lifepod_Debris_19` | StaticMesh | 0.12 | 2,551 | 0.65x0.67x0.1 |  | no | [collision] |
| `/Game/Levels/Halo1/Solo/A30/Vehicle/Lifepod/A30_LifePod_Damaged/SM_A30_Lifepod_Debris_20` | StaticMesh | 0.20 | 3,185 | 0.55x0.67x0.28 |  | no | [collision] |
| `/Game/Levels/Halo1/Solo/A30/Vehicle/Lifepod/A30_LifePod_Damaged/SM_A30_Lifepod_Debris_21` | StaticMesh | 0.08 | 908 | 1.18x1.22x0.72 |  | no | [collision] |
| `/Game/Levels/Halo1/Solo/A30/Vehicle/Lifepod/A30_LifePod_Damaged/SM_A30_Lifepod_Destroyed` | StaticMesh | 20.45 | 411,164 | 9.18x13.38x6.99 | A30 | no | very dense: confirm Nanite before placing many [collision] |

Textures: `/Game/Levels/Halo1/Solo/A30/Landscape/Crash_Site_Mound/Mesh/T_Burnt_Soil_D` (3.2 MB), `/Game/Levels/Halo1/Solo/A30/Landscape/Crash_Site_Mound/Mesh/T_Burnt_Soil_E` (6.4 MB), `/Game/Levels/Halo1/Solo/A30/Landscape/Crash_Site_Mound/Mesh/T_Burnt_Soil_N` (6.4 MB), `/Game/Levels/Halo1/Solo/A30/Landscape/Crash_Site_Mound/Mesh/T_Burnt_Soil_ORHG` (6.4 MB), `/Game/Levels/Halo1/Solo/A30/Vehicle/Lifepod/A30_LifePod_Damaged/Texture/T_A30_Lifepod_Destroyed_Glass_D` (3.2 MB), `/Game/Levels/Halo1/Solo/A30/Vehicle/Lifepod/A30_LifePod_Damaged/Texture/T_A30_Lifepod_Destroyed_Glass_N` (6.4 MB), `/Game/Levels/Halo1/Solo/A30/Vehicle/Lifepod/A30_LifePod_Damaged/Texture/T_A30_Lifepod_Destroyed_M` (63.2 MB)

*Group note:* A30 crash-site set (burnt soil textures, mud MIs)

### Forerunner and UNSC surface materials (HaloMaterialLibrary/Env) (238)

*Where on PWR:* Re-skinning PWR's Forerunner bases and bridges with the shipped FR metal family (diagonal panels, grime, vertex-colour wear)

| path | kind | MB | verts | bounds m | levels | PWR | note |
|---|---|---|---|---|---|---|---|
| `/HaloMaterialLibrary/Env/Material/HS/FR/+Master/MI_FR_Metal_Diagonal_01_Master` | MaterialInstance | 0.31 |  |  | A15,A30,A50,B30,B40,C10,C20,C45,D20,D40,E10,E20,E30 | no |  |
| `/HaloMaterialLibrary/Env/Material/HS/FR/MI_FR_Metal_Diagonal_01_0_ExtraLight_Rough1_Low_VCol` | MaterialInstance | 0.32 |  |  | C10 | no |  |
| `/HaloMaterialLibrary/Env/Material/HS/FR/MI_FR_Metal_Diagonal_01_0_ExtraLight_Rough1_Low_VCol_Wet` | MaterialInstance | 0.09 |  |  | C10 | no | wet variant |
| `/HaloMaterialLibrary/Env/Material/HS/FR/MI_FR_Metal_Diagonal_01_0_ExtraLight_Rough2_Mid_VCol` | MaterialInstance | 0.00 |  |  | C10 | no |  |
| `/HaloMaterialLibrary/Env/Material/HS/FR/MI_FR_Metal_Diagonal_01_0_ExtraLight_Rough2_Mid_VCol_Wet` | MaterialInstance | 0.09 |  |  | C10 | no | wet variant |
| `/HaloMaterialLibrary/Env/Material/HS/FR/MI_FR_Metal_Diagonal_01_0_ExtraLight_Rough3_High_VCol` | MaterialInstance | 0.32 |  |  | C10 | no |  |
| `/HaloMaterialLibrary/Env/Material/HS/FR/MI_FR_Metal_Diagonal_01_0_ExtraLight_Rough3_High_VCol_Wet` | MaterialInstance | 0.09 |  |  | C10 | no | wet variant |
| `/HaloMaterialLibrary/Env/Material/HS/FR/MI_FR_Metal_Diagonal_01_1_Light_Rough1_Low_VCol` | MaterialInstance | 0.31 |  |  | A15,A30,A50,B30,B40,C10,C20,C45,D20,D40,E10,E20,E30 | no |  |
| `/HaloMaterialLibrary/Env/Material/HS/FR/MI_FR_Metal_Diagonal_01_1_Light_Rough1_Low_VCol_Exterior` | MaterialInstance | 0.34 |  |  | E20 | no |  |
| `/HaloMaterialLibrary/Env/Material/HS/FR/MI_FR_Metal_Diagonal_01_1_Light_Rough1_Low_VCol_Exterior_Vista` | MaterialInstance | 0.09 |  |  | E20 | no |  |
| `/HaloMaterialLibrary/Env/Material/HS/FR/MI_FR_Metal_Diagonal_01_1_Light_Rough1_Low_VCol_Wet` | MaterialInstance | 0.09 |  |  | C10 | no | wet variant |
| `/HaloMaterialLibrary/Env/Material/HS/FR/MI_FR_Metal_Diagonal_01_1_Light_Rough2_Mid_VCol` | MaterialInstance | 0.31 |  |  | A30,B30,B40,C10,C20,C45 | no |  |
| `/HaloMaterialLibrary/Env/Material/HS/FR/MI_FR_Metal_Diagonal_01_1_Light_Rough2_Mid_VCol_Wet` | MaterialInstance | 0.09 |  |  | C10 | no | wet variant |
| `/HaloMaterialLibrary/Env/Material/HS/FR/MI_FR_Metal_Diagonal_01_1_Light_Rough3_High_VCol` | MaterialInstance | 0.31 |  |  | A15,A30,A50,B30,B40,C10,C20,C45,D20,D40,E10,E20,E30 | no |  |
| `/HaloMaterialLibrary/Env/Material/HS/FR/MI_FR_Metal_Diagonal_01_1_Light_Rough3_High_VCol_Exterior` | MaterialInstance | 0.34 |  |  | E20 | no |  |
| `/HaloMaterialLibrary/Env/Material/HS/FR/MI_FR_Metal_Diagonal_01_1_Light_Rough3_High_VCol_Exterior_Vista` | MaterialInstance | 0.34 |  |  | E20 | no |  |
| `/HaloMaterialLibrary/Env/Material/HS/FR/MI_FR_Metal_Diagonal_01_1_Light_Rough3_High_VCol_Wet` | MaterialInstance | 0.09 |  |  | C10 | no | wet variant |
| `/HaloMaterialLibrary/Env/Material/HS/FR/MI_FR_Metal_Diagonal_01_2_Mid_Rough1_Low_VCol` | MaterialInstance | 0.31 |  |  | A15,A30,A50,B30,B40,C10,C20,C45,D20,D40,E10,E20,E30 | no |  |
| `/HaloMaterialLibrary/Env/Material/HS/FR/MI_FR_Metal_Diagonal_01_2_Mid_Rough1_Low_VCol_Wet` | MaterialInstance | 0.09 |  |  | C10 | no | wet variant |
| `/HaloMaterialLibrary/Env/Material/HS/FR/MI_FR_Metal_Diagonal_01_2_Mid_Rough2_Mid_VCol` | MaterialInstance | 0.09 |  |  | A15,A30,A50,B30,B40,C10,C20,C45,E10,E30 | no |  |
| `/HaloMaterialLibrary/Env/Material/HS/FR/MI_FR_Metal_Diagonal_01_2_Mid_Rough2_Mid_VCol_Wet` | MaterialInstance | 0.09 |  |  | C10 | no | wet variant |
| `/HaloMaterialLibrary/Env/Material/HS/FR/MI_FR_Metal_Diagonal_01_2_Mid_Rough3_High_VCol` | MaterialInstance | 0.31 |  |  | A15,A30,A50,B30,B40,C10,C20,C45,D20,D40,E10,E20,E30 | no |  |
| `/HaloMaterialLibrary/Env/Material/HS/FR/MI_FR_Metal_Diagonal_01_2_Mid_Rough3_High_VCol_Wet` | MaterialInstance | 0.09 |  |  | C10 | no | wet variant |
| `/HaloMaterialLibrary/Env/Material/HS/FR/MI_FR_Metal_Diagonal_01_3_Dark_Rough1_Low_VCol` | MaterialInstance | 0.32 |  |  | B30,B40,C20,C45,D20 | no |  |
| `/HaloMaterialLibrary/Env/Material/HS/FR/MI_FR_Metal_Diagonal_01_3_Dark_Rough2_Mid_VCol` | MaterialInstance | 0.09 |  |  | B40,C20,C45 | no |  |
| `/HaloMaterialLibrary/Env/Material/HS/FR/MI_FR_Metal_Diagonal_01_3_Dark_Rough3_High_VCol` | MaterialInstance | 0.32 |  |  | B40,C45,D20 | no |  |
| `/HaloMaterialLibrary/Env/Material/HS/FR/MI_FR_Metal_Diagonal_01_A_Light_Rough1_Low` | MaterialInstance | 0.00 |  |  | A30,B30,B40,C10,C20,C45 | no |  |
| `/HaloMaterialLibrary/Env/Material/HS/FR/MI_FR_Metal_Diagonal_01_A_Light_Rough1_Low_VCol_Frost` | MaterialInstance | 0.31 |  |  | B40 | no |  |
| `/HaloMaterialLibrary/Env/Material/HS/FR/MI_FR_Metal_Diagonal_01_A_Light_Rough1_Low_VCol_HeavyGrime` | MaterialInstance | 0.32 |  |  | A30,B30 | no |  |
| `/HaloMaterialLibrary/Env/Material/HS/FR/MI_FR_Metal_Diagonal_01_A_Light_Rough2_Mid` | MaterialInstance | 0.00 |  |  | B30,C10,C20 | no |  |
| `/HaloMaterialLibrary/Env/Material/HS/FR/MI_FR_Metal_Diagonal_01_A_Light_Rough2_Mid_VCol_Frost` | MaterialInstance | 0.31 |  |  | B40,C20,C45 | no |  |
| `/HaloMaterialLibrary/Env/Material/HS/FR/MI_FR_Metal_Diagonal_01_A_Light_Rough2_Mid_VCol_HeavyGrime` | MaterialInstance | 0.31 |  |  | A30,B30 | no |  |
| `/HaloMaterialLibrary/Env/Material/HS/FR/MI_FR_Metal_Diagonal_01_A_Light_Rough3_High` | MaterialInstance | 0.00 |  |  | C10 | no |  |
| `/HaloMaterialLibrary/Env/Material/HS/FR/MI_FR_Metal_Diagonal_01_A_Light_Rough3_High_VCol_Frost` | MaterialInstance | 0.31 |  |  | B40,C45 | no |  |
| `/HaloMaterialLibrary/Env/Material/HS/FR/MI_FR_Metal_Diagonal_01_A_Light_Rough3_High_VCol_HeavyGrime` | MaterialInstance | 0.32 |  |  | C10 | no |  |
| `/HaloMaterialLibrary/Env/Material/HS/FR/MI_FR_Metal_Diagonal_01_A_Light_Rough3_High_VCol_HeavyGrime_RVTGrunge` | MaterialInstance | 0.35 |  |  | C10 | no |  |
| `/HaloMaterialLibrary/Env/Material/HS/FR/MI_FR_Metal_Diagonal_01_A_Light_Rough3_High_VCol_HeavyGrime_RVTGrunge_Wet` | MaterialInstance | 0.10 |  |  | C10 | no | wet variant |
| `/HaloMaterialLibrary/Env/Material/HS/FR/MI_FR_Metal_Diagonal_01_A_Light_Rough3_High_Wet` | MaterialInstance | 0.09 |  |  | C10 | no | wet variant |
| `/HaloMaterialLibrary/Env/Material/HS/FR/MI_FR_Metal_Diagonal_01_B_Mid_Rough1_Low` | MaterialInstance | 0.00 |  |  | A30,B30,C10,C20,E10 | no |  |
| `/HaloMaterialLibrary/Env/Material/HS/FR/MI_FR_Metal_Diagonal_01_B_Mid_Rough1_Low_VCol_Frost` | MaterialInstance | 0.31 |  |  | B40,C20,C45 | no |  |
| `/HaloMaterialLibrary/Env/Material/HS/FR/MI_FR_Metal_Diagonal_01_B_Mid_Rough1_Low_VCol_HeavyGrime` | MaterialInstance | 0.32 |  |  | A30,B30,C10 | no |  |
| `/HaloMaterialLibrary/Env/Material/HS/FR/MI_FR_Metal_Diagonal_01_B_Mid_Rough1_Low_VCol_HeavyGrime_RVTGrunge` | MaterialInstance | 0.35 |  |  | C10 | no |  |
| `/HaloMaterialLibrary/Env/Material/HS/FR/MI_FR_Metal_Diagonal_01_B_Mid_Rough1_Low_VCol_HeavyGrime_RVTGrunge_Wet` | MaterialInstance | 0.10 |  |  | C10 | no | wet variant |
| `/HaloMaterialLibrary/Env/Material/HS/FR/MI_FR_Metal_Diagonal_01_B_Mid_Rough1_Low_VCol_HeavyGrime_RVTGrunge_Wet_Top` | MaterialInstance | 0.10 |  |  | C10 | no | wet variant |
| `/HaloMaterialLibrary/Env/Material/HS/FR/MI_FR_Metal_Diagonal_01_B_Mid_Rough1_Low_Wet` | MaterialInstance | 0.09 |  |  | C10 | no | wet variant |
| `/HaloMaterialLibrary/Env/Material/HS/FR/MI_FR_Metal_Diagonal_01_B_Mid_Rough2_Mid` | MaterialInstance | 0.00 |  |  | A30,B30,B40,C10,C20,C45 | no |  |
| `/HaloMaterialLibrary/Env/Material/HS/FR/MI_FR_Metal_Diagonal_01_B_Mid_Rough2_Mid_VCol_Frost` | MaterialInstance | 0.31 |  |  | B40,C20,C45 | no |  |
| `/HaloMaterialLibrary/Env/Material/HS/FR/MI_FR_Metal_Diagonal_01_B_Mid_Rough2_Mid_VCol_HeavyGrime` | MaterialInstance | 0.32 |  |  | A30,B30,B40,C20,C45 | no |  |
| `/HaloMaterialLibrary/Env/Material/HS/FR/MI_FR_Metal_Diagonal_01_B_Mid_Rough2_Mid_Wet` | MaterialInstance | 0.09 |  |  | C10 | no | wet variant |
| `/HaloMaterialLibrary/Env/Material/HS/FR/MI_FR_Metal_Diagonal_01_B_Mid_Rough3_High` | MaterialInstance | 0.00 |  |  | B30,C20 | no |  |
| `/HaloMaterialLibrary/Env/Material/HS/FR/MI_FR_Metal_Diagonal_01_B_Mid_Rough3_High_VCol_Frost` | MaterialInstance | 0.31 |  |  | B40,C20,C45 | no |  |
| `/HaloMaterialLibrary/Env/Material/HS/FR/MI_FR_Metal_Diagonal_01_Bronze_A_Light_Rough1_Low_VCol` | MaterialInstance | 0.31 |  |  | B30,B40,C10,C20,C45 | no |  |
| `/HaloMaterialLibrary/Env/Material/HS/FR/MI_FR_Metal_Diagonal_01_Bronze_A_Light_Rough2_Mid_VCol` | MaterialInstance | 0.09 |  |  | B40,C10,C20,C45 | no |  |
| `/HaloMaterialLibrary/Env/Material/HS/FR/MI_FR_Metal_Diagonal_01_Bronze_A_Light_Rough2_Mid_VCol_Frost` | MaterialInstance | 0.31 |  |  | B40,C45 | no |  |
| `/HaloMaterialLibrary/Env/Material/HS/FR/MI_FR_Metal_Diagonal_01_Bronze_B_Mid_Rough1_Low_VCol` | MaterialInstance | 0.31 |  |  | A15,A30,A50,B30,B40,C10,C20,C45,D20,D40,E10,E20,E30 | no |  |
| `/HaloMaterialLibrary/Env/Material/HS/FR/MI_FR_Metal_Diagonal_01_Bronze_B_Mid_Rough1_Low_VCol_Frost` | MaterialInstance | 0.31 |  |  | B40,C20,C45 | no |  |
| `/HaloMaterialLibrary/Env/Material/HS/FR/MI_FR_Metal_Diagonal_01_Bronze_B_Mid_Rough1_Low_VCol_HeavyGrime` | MaterialInstance | 0.32 |  |  | C10 | no |  |
| `/HaloMaterialLibrary/Env/Material/HS/FR/MI_FR_Metal_Diagonal_01_Bronze_B_Mid_Rough1_Low_VCol_HeavyGrime_RVTGrunge` | MaterialInstance | 0.35 |  |  | C10 | no |  |
| `/HaloMaterialLibrary/Env/Material/HS/FR/MI_FR_Metal_Diagonal_01_Bronze_B_Mid_Rough1_Low_VCol_HeavyGrime_RVTGrunge_Wet` | MaterialInstance | 0.10 |  |  | C10 | no | wet variant |
| `/HaloMaterialLibrary/Env/Material/HS/FR/MI_FR_Metal_Diagonal_01_Bronze_B_Mid_Rough1_Low_VCol_HeavyGrime_RVTGrunge_Wet_Top` | MaterialInstance | 0.34 |  |  | C10 | no | wet variant |
| `/HaloMaterialLibrary/Env/Material/HS/FR/MI_FR_Metal_Diagonal_01_Bronze_B_Mid_Rough1_Low_VCol_Wet` | MaterialInstance | 0.09 |  |  | C10 | no | wet variant |
| `/HaloMaterialLibrary/Env/Material/HS/FR/MI_FR_Metal_Diagonal_01_Bronze_B_Mid_Rough2_Mid_VCol` | MaterialInstance | 0.00 |  |  | B30,B40,C10,C20,C45 | no |  |
| `/HaloMaterialLibrary/Env/Material/HS/FR/MI_FR_Metal_Diagonal_01_Bronze_B_Mid_Rough2_Mid_VCol_Frost` | MaterialInstance | 0.31 |  |  | B40,C45 | no |  |
| `/HaloMaterialLibrary/Env/Material/HS/FR/MI_FR_Metal_Diagonal_01_Bronze_B_Mid_Rough2_Mid_VCol_Wet` | MaterialInstance | 0.09 |  |  | C10 | no | wet variant |
| `/HaloMaterialLibrary/Env/Material/HS/FR/MI_FR_Metal_Diagonal_01_Bronze_B_Mid_Rough3_High_VCol` | MaterialInstance | 0.00 |  |  | A15,A30,A50,B30,B40,C10,C20,C45,D20,D40,E10,E20,E30 | no |  |
| `/HaloMaterialLibrary/Env/Material/HS/FR/MI_FR_Metal_Diagonal_01_Bronze_C_Dark_Rough1_Low_VCol` | MaterialInstance | 0.31 |  |  |  | no |  |
| `/HaloMaterialLibrary/Env/Material/HS/FR/MI_FR_Metal_Diagonal_01_Bronze_C_Dark_Rough2_Mid_Vcol` | MaterialInstance | 0.09 |  |  |  | no |  |
| `/HaloMaterialLibrary/Env/Material/HS/FR/MI_FR_Metal_Diagonal_01_C_Dark_Line_Rough0_Lowest` | MaterialInstance | 0.00 |  |  | A30,B30,B40,C10,C45 | no |  |
| `/HaloMaterialLibrary/Env/Material/HS/FR/MI_FR_Metal_Diagonal_01_C_Dark_Line_Rough0_Lowest_VCol` | MaterialInstance | 0.31 |  |  | A30,B30,B40,C45 | no |  |
| `/HaloMaterialLibrary/Env/Material/HS/FR/MI_FR_Metal_Diagonal_01_C_Dark_Line_Rough0_Lowest_VCol_Frost` | MaterialInstance | 0.31 |  |  | B40,C45 | no |  |
| `/HaloMaterialLibrary/Env/Material/HS/FR/MI_FR_Metal_Diagonal_01_C_Dark_Line_Rough0_Lowest_VCol_HeavyGrime` | MaterialInstance | 0.31 |  |  | A30,B30 | no |  |
| `/HaloMaterialLibrary/Env/Material/HS/FR/MI_FR_Metal_Diagonal_01_C_Dark_Line_Rough0_Lowest_Wet` | MaterialInstance | 0.09 |  |  | C10 | no | wet variant |
| `/HaloMaterialLibrary/Env/Material/HS/FR/MI_FR_Metal_Diagonal_01_C_Dark_Rough1_Low` | MaterialInstance | 0.31 |  |  | A15,A30,B30,B40,C10,C20,C45 | no |  |
| `/HaloMaterialLibrary/Env/Material/HS/FR/MI_FR_Metal_Diagonal_01_C_Dark_Rough1_Low_VCol_Frost` | MaterialInstance | 0.31 |  |  | B40,C20,C45 | no |  |
| `/HaloMaterialLibrary/Env/Material/HS/FR/MI_FR_Metal_Diagonal_01_C_Dark_Rough1_Low_VCol_HeavyGrime` | MaterialInstance | 0.00 |  |  | A15,A30,B30,B40,C10,C20,C45 | no |  |
| `/HaloMaterialLibrary/Env/Material/HS/FR/MI_FR_Metal_Diagonal_01_C_Dark_Rough1_Low_Wet` | MaterialInstance | 0.09 |  |  | C10 | no | wet variant |
| `/HaloMaterialLibrary/Env/Material/HS/FR/MI_FR_Metal_Diagonal_01_C_Dark_Rough2_Mid` | MaterialInstance | 0.09 |  |  | A30,B30,B40,C10,C20,C45 | no |  |
| `/HaloMaterialLibrary/Env/Material/HS/FR/MI_FR_Metal_Diagonal_01_C_Dark_Rough2_Mid_VCol_Frost` | MaterialInstance | 0.31 |  |  | B40,C20,C45 | no |  |
| `/HaloMaterialLibrary/Env/Material/HS/FR/MI_FR_Metal_Diagonal_01_C_Dark_Rough2_Mid_VCol_HeavyGrime` | MaterialInstance | 0.31 |  |  | A15,A30,B30,B40,C10,C20,C45 | no |  |
| `/HaloMaterialLibrary/Env/Material/HS/FR/MI_FR_Metal_Diagonal_01_C_Dark_Rough2_Mid_VCol_HeavyGrime_RVTGrunge` | MaterialInstance | 0.35 |  |  | C10 | no |  |
| `/HaloMaterialLibrary/Env/Material/HS/FR/MI_FR_Metal_Diagonal_01_C_Dark_Rough2_Mid_VCol_HeavyGrime_RVTGrunge_Wet` | MaterialInstance | 0.10 |  |  | C10 | no | wet variant |
| `/HaloMaterialLibrary/Env/Material/HS/FR/MI_FR_Metal_Diagonal_01_C_Dark_Rough2_Mid_Wet` | MaterialInstance | 0.09 |  |  | C10 | no | wet variant |
| `/HaloMaterialLibrary/Env/Material/HS/FR/MI_FR_Metal_Diagonal_01_C_Dark_Rough3_High` | MaterialInstance | 0.00 |  |  | B30 | no |  |
| `/HaloMaterialLibrary/Env/Material/HS/FR/MI_FR_Metal_Diagonal_01_C_Dark_Rough3_High_VCol_Frost` | MaterialInstance | 0.31 |  |  | B40,C45 | no |  |
| `/HaloMaterialLibrary/Env/Material/HS/FR/MI_FR_Metal_Diagonal_01_C_Dark_Rough3_High_VCol_HeavyGrime` | MaterialInstance | 0.32 |  |  | B40,C20,C45 | no |  |
| `/HaloMaterialLibrary/Env/Material/HS/FR/MI_FR_Metal_Diagonal_01_Dark` | MaterialInstance | 0.00 |  |  | A15,A30,B30,B40,C10,C20,C45 | no |  |
| `/HaloMaterialLibrary/Env/Material/HS/FR/MI_FR_Metal_Diagonal_01_Dark_Linework` | MaterialInstance | 0.00 |  |  | A15,A30,B30,B40,C10,C20,C45 | no |  |
| `/HaloMaterialLibrary/Env/Material/HS/FR/MI_FR_Metal_Diagonal_01_Dark_Linework_Wet` | MaterialInstance | 0.09 |  |  | C10 | no | wet variant |
| `/HaloMaterialLibrary/Env/Material/HS/FR/MI_FR_Metal_Diagonal_01_Dark_RVT` | MaterialInstance | 0.32 |  |  | B30 | no |  |
| `/HaloMaterialLibrary/Env/Material/HS/FR/MI_FR_Metal_Diagonal_01_Dark_Wet` | MaterialInstance | 0.09 |  |  | C10 | no | wet variant |
| `/HaloMaterialLibrary/Env/Material/HS/FR/MI_FR_Metal_Diagonal_01_Mid` | MaterialInstance | 0.00 |  |  | A30,B30,B40,C10,C20,C45 | no |  |
| `/HaloMaterialLibrary/Env/Material/HS/FR/MI_FR_Metal_Diagonal_01_Mid_Gilded` | MaterialInstance | 0.00 |  |  | B40,C10,C20,C45 | no |  |
| `/HaloMaterialLibrary/Env/Material/HS/FR/MI_FR_Metal_Diagonal_01_Mid_Gilded_Wet` | MaterialInstance | 0.09 |  |  | C10 | no | wet variant |
| `/HaloMaterialLibrary/Env/Material/HS/FR/MI_FR_Metal_Diagonal_01_Mid_Vert` | MaterialInstance | 0.09 |  |  | A30 | no |  |
| `/HaloMaterialLibrary/Env/Material/HS/FR/MI_FR_Metal_Diagonal_01_Mid_Wet` | MaterialInstance | 0.09 |  |  | C10 | no | wet variant |
| `/HaloMaterialLibrary/Env/Material/HS/FR/MI_FR_Metal_Diagonal_02_Mid_Rough_High` | MaterialInstance | 0.00 |  |  | A30 | no |  |
| `/HaloMaterialLibrary/Env/Material/HS/FR/ObjectSpace/MI_FR_Metal_Diagonal_01_1_Light_Rough2_Mid_VCol_OS` | MaterialInstance | 0.09 |  |  |  | no |  |
| `/HaloMaterialLibrary/Env/Material/HS/FR/ObjectSpace/MI_FR_Metal_Diagonal_01_2_Mid_Rough2_Mid_VCol_OS` | MaterialInstance | 0.09 |  |  |  | no |  |
| `/HaloMaterialLibrary/Env/Material/HS/FR/ObjectSpace/MI_FR_Metal_Diagonal_01_3_Dark_Rough1_Low_VCol_OS` | MaterialInstance | 0.09 |  |  |  | no |  |
| `/HaloMaterialLibrary/Env/Material/HS/FR/ObjectSpace/MI_FR_Metal_Diagonal_01_A_Light_Rough1_Low_OS` | MaterialInstance | 0.09 |  |  | B30,B40,C10,C20,C45 | no |  |
| `/HaloMaterialLibrary/Env/Material/HS/FR/ObjectSpace/MI_FR_Metal_Diagonal_01_B_Mid_Rough2_Mid_OS` | MaterialInstance | 0.09 |  |  | C20 | no |  |
| `/HaloMaterialLibrary/Env/Material/HS/FR/ObjectSpace/MI_FR_Metal_Diagonal_01_Bronze_B_Mid_Rough2_Mid_VCol_OS` | MaterialInstance | 0.09 |  |  |  | no |  |
| `/HaloMaterialLibrary/Env/Material/HS/FR/ObjectSpace/MI_FR_Metal_Diagonal_01_Bronze_C_Dark_Rough1_Low_VCol_OS` | MaterialInstance | 0.09 |  |  |  | no |  |
| `/HaloMaterialLibrary/Env/Material/HS/FR/ObjectSpace/MI_FR_Metal_Diagonal_01_Bronze_C_Dark_Rough2_Mid_Vcol_OS` | MaterialInstance | 0.09 |  |  |  | no |  |
| `/HaloMaterialLibrary/Env/Material/HS/FR/ObjectSpace/MI_FR_Metal_Diagonal_01_C_Dark_Rough1_Low_OS` | MaterialInstance | 0.09 |  |  | A15 | no |  |
| `/HaloMaterialLibrary/Env/Material/HS/FR/ObjectSpace/MI_FR_Metal_Diagonal_01_C_Dark_Rough1_Low_VCol_HeavyGrime_OS` | MaterialInstance | 0.09 |  |  |  | no |  |
| `/HaloMaterialLibrary/Env/Material/HS/FR/ObjectSpace/MI_FR_Metal_Diagonal_01_C_Dark_Rough2_Mid_VCol_HeavyGrime_OS` | MaterialInstance | 0.09 |  |  | A15 | no |  |
| `/HaloMaterialLibrary/Env/Material/HS/FR/ObjectSpace/MI_FR_Metal_Diagonal_01_Dark_Linework_OS` | MaterialInstance | 0.09 |  |  | A15,C20 | no |  |
| `/HaloMaterialLibrary/Env/Material/HS/FR/ObjectSpace/MI_FR_Metal_Diagonal_01_Mid_Gilded_OS` | MaterialInstance | 0.09 |  |  | C20 | no |  |
| `/HaloMaterialLibrary/Env/Material/HS/FR/ObjectSpace/MI_FR_Metal_Diagonal_01_Mid_OS` | MaterialInstance | 0.09 |  |  |  | no |  |
| `/HaloMaterialLibrary/Env/Material/HS/FR/TEMP_Instances/MI_FR_Metal_Diagonal_01_A_Bronze_Dark_TEMP` | MaterialInstance | 0.00 |  |  | C10 | no |  |
| `/HaloMaterialLibrary/Env/Material/HS/FR/TEMP_Instances/MI_FR_Metal_Diagonal_01_A_Bronze_Light_TEMP` | MaterialInstance | 0.00 |  |  | C10 | no |  |
| `/HaloMaterialLibrary/Env/Material/HS/FR/TEMP_Instances/MI_FR_Metal_Diagonal_01_A_Light_Rough3_High_TEMP` | MaterialInstance | 0.00 |  |  | C10 | no |  |
| `/HaloMaterialLibrary/Env/Material/HS/FR/TEMP_Instances/MI_FR_Metal_Diagonal_01_A_Light_Rough3_High_TEMP_Wet` | MaterialInstance | 0.09 |  |  | C10 | no | wet variant |
| `/HaloMaterialLibrary/Env/Material/HS/FR/TEMP_Instances/MI_FR_Metal_Diagonal_01_Dark_Linework_TEMP` | MaterialInstance | 0.00 |  |  | C10 | no |  |
| `/HaloMaterialLibrary/Env/Material/HS/UNSC/MIP_UNSC_Metal` | MaterialInstance | 0.31 |  |  | A15,A30,A50,B30,B40,C10,C20,C45,D20,D40,E10,E20,E30 | no |  |
| `/HaloMaterialLibrary/Env/Material/HS/UNSC/MIP_UNSC_PaintedMetal` | MaterialInstance | 0.31 |  |  | A15,D40,E10,E20,E30 | no |  |
| `/HaloMaterialLibrary/Env/Material/HS/UNSC/MIP_UNSC_PaintedMetal_Beige` | MaterialInstance | 0.00 |  |  | A15,D40,E10,E20,E30 | no |  |
| `/HaloMaterialLibrary/Env/Material/HS/UNSC/MIP_UNSC_PaintedMetal_Blue` | MaterialInstance | 0.00 |  |  | A15,D40 | no |  |
| `/HaloMaterialLibrary/Env/Material/HS/UNSC/MIP_UNSC_PaintedMetal_Damaged` | MaterialInstance | 0.28 |  |  | A15,D40,E30 | no |  |
| `/HaloMaterialLibrary/Env/Material/HS/UNSC/MIP_UNSC_PaintedMetal_Grey` | MaterialInstance | 0.00 |  |  | A15,D40,E10,E20,E30 | no |  |
| `/HaloMaterialLibrary/Env/Material/HS/UNSC/MIP_UNSC_PaintedMetal_Grey_1Dark` | MaterialInstance | 0.00 |  |  | A15,D40,E10,E20,E30 | no |  |
| `/HaloMaterialLibrary/Env/Material/HS/UNSC/MIP_UNSC_PaintedMetal_Grey_3Light` | MaterialInstance | 0.00 |  |  | A15,D40,E30 | no |  |
| `/HaloMaterialLibrary/Env/Material/HS/UNSC/MIP_UNSC_PaintedMetal_Orange` | MaterialInstance | 0.00 |  |  | A15,D40,E10,E20 | no |  |
| `/HaloMaterialLibrary/Env/Material/HS/UNSC/MIP_UNSC_PaintedMetal_OrangeDark` | MaterialInstance | 0.00 |  |  | A15,D40,E20,E30 | no |  |
| `/HaloMaterialLibrary/Env/Material/HS/UNSC/MIP_UNSC_PaintedMetal_Red` | MaterialInstance | 0.00 |  |  | A15,D40,E30 | no |  |
| `/HaloMaterialLibrary/Env/Material/HS/UNSC/MIP_UNSC_Plastic` | MaterialInstance | 0.29 |  |  | A15,A30,A50,B30,B40,C10,C20,C45,D20,D40,E10,E20,E30 | no |  |
| `/HaloMaterialLibrary/Env/Material/HS/UNSC/MIP_UNSC_PlasticDamaged` | MaterialInstance | 0.23 |  |  | A15,D40,E30 | no |  |
| `/HaloMaterialLibrary/Env/Material/HS/UNSC/MIP_UNSC_Plastic_Beige` | MaterialInstance | 0.29 |  |  | A15,A30,A50,B30,B40,C10,C20,C45,D20,D40,E10,E20,E30 | no |  |
| `/HaloMaterialLibrary/Env/Material/HS/UNSC/MIP_UNSC_Plastic_Black` | MaterialInstance | 0.00 |  |  | A15,A30,A50,B30,B40,C10,C20,C45,D20,D40,E10,E20,E30 | no |  |
| `/HaloMaterialLibrary/Env/Material/HS/UNSC/MIP_UNSC_Plastic_Blue` | MaterialInstance | 0.00 |  |  | A15,D40,E30 | no |  |
| `/HaloMaterialLibrary/Env/Material/HS/UNSC/MIP_UNSC_Plastic_Grey` | MaterialInstance | 0.00 |  |  | A15,A30,A50,B30,B40,C10,C20,C45,D20,D40,E10,E20,E30 | no |  |
| `/HaloMaterialLibrary/Env/Material/HS/UNSC/MIP_UNSC_Plastic_Orange` | MaterialInstance | 0.00 |  |  | A15,D40,E30 | no |  |
| `/HaloMaterialLibrary/Env/Material/HS/UNSC/MIP_UNSC_Plastic_Red` | MaterialInstance | 0.00 |  |  | A15,D40,E30 | no |  |
| `/HaloMaterialLibrary/Env/Material/HS/UNSC/MIP_UNSC_Plastic_White` | MaterialInstance | 0.00 |  |  | A15,D40,E10,E20 | no |  |
| `/HaloMaterialLibrary/Env/Material/HS/UNSC/MIP_UNSC_Plastic_Yellow` | MaterialInstance | 0.00 |  |  | A15,D40 | no |  |
| `/HaloMaterialLibrary/Env/Material/HS/UNSC/MI_UNSC_Metal_Damaged` | MaterialInstance | 0.28 |  |  | A15,D40,E30 | no |  |
| `/HaloMaterialLibrary/Env/Material/HS/UNSC/MI_UNSC_Metal_Damaged_Sand` | MaterialInstance | 0.28 |  |  | D40 | no |  |
| `/HaloMaterialLibrary/Env/Material/HS/UNSC/MI_UNSC_Metal_Rough1_Low` | MaterialInstance | 0.00 |  |  | A15,A30,A50,B30,B40,C10,C20,C45,D20,D40,E10,E20,E30 | no |  |
| `/HaloMaterialLibrary/Env/Material/HS/UNSC/MI_UNSC_Metal_Rough1_Low_Char` | MaterialInstance | 0.31 |  |  | D40 | no |  |
| `/HaloMaterialLibrary/Env/Material/HS/UNSC/MI_UNSC_Metal_Rough2_Mid` | MaterialInstance | 0.00 |  |  | A15,D40 | no |  |
| `/HaloMaterialLibrary/Env/Material/HS/UNSC/MI_UNSC_Metal_Rough2_Mid_Char` | MaterialInstance | 0.31 |  |  | D40 | no |  |
| `/HaloMaterialLibrary/Env/Material/HS/UNSC/MI_UNSC_Metal_Rough3_High` | MaterialInstance | 0.00 |  |  | A15,D40,E30 | no |  |
| `/HaloMaterialLibrary/Env/Material/HS/UNSC/MI_UNSC_Metal_Steel_Worn_01` | MaterialInstance | 0.20 |  |  | A15,D40,E30 | no |  |
| `/HaloMaterialLibrary/Env/Material/HS/UNSC/MI_UNSC_PaintedMetal_Beige_Rough1_Low` | MaterialInstance | 0.00 |  |  | A15,D40 | no |  |
| `/HaloMaterialLibrary/Env/Material/HS/UNSC/MI_UNSC_PaintedMetal_Beige_Rough2_Mid` | MaterialInstance | 0.00 |  |  | A15,D40,E10,E20,E30 | no |  |
| `/HaloMaterialLibrary/Env/Material/HS/UNSC/MI_UNSC_PaintedMetal_Beige_Rough2_Mid_Char` | MaterialInstance | 0.31 |  |  | D40 | no |  |
| `/HaloMaterialLibrary/Env/Material/HS/UNSC/MI_UNSC_PaintedMetal_Beige_Rough3_High` | MaterialInstance | 0.00 |  |  | A15,D40,E30 | no |  |
| `/HaloMaterialLibrary/Env/Material/HS/UNSC/MI_UNSC_PaintedMetal_Blue_Rough1_Low` | MaterialInstance | 0.00 |  |  | A15,D40 | no |  |
| `/HaloMaterialLibrary/Env/Material/HS/UNSC/MI_UNSC_PaintedMetal_Blue_Rough3_High` | MaterialInstance | 0.00 |  |  | A15,D40 | no |  |
| `/HaloMaterialLibrary/Env/Material/HS/UNSC/MI_UNSC_PaintedMetal_Damaged_Beige` | MaterialInstance | 0.00 |  |  | A15,D40,E30 | no |  |
| `/HaloMaterialLibrary/Env/Material/HS/UNSC/MI_UNSC_PaintedMetal_Damaged_Beige_Rough3_High` | MaterialInstance | 0.00 |  |  | D40,E30 | no |  |
| `/HaloMaterialLibrary/Env/Material/HS/UNSC/MI_UNSC_PaintedMetal_Damaged_Beige_Sand` | MaterialInstance | 0.00 |  |  | D40 | no |  |
| `/HaloMaterialLibrary/Env/Material/HS/UNSC/MI_UNSC_PaintedMetal_Damaged_Grey` | MaterialInstance | 0.00 |  |  | A15,D40,E30 | no |  |
| `/HaloMaterialLibrary/Env/Material/HS/UNSC/MI_UNSC_PaintedMetal_Damaged_Grey_Sand` | MaterialInstance | 0.00 |  |  | A15,D40 | no |  |
| `/HaloMaterialLibrary/Env/Material/HS/UNSC/MI_UNSC_PaintedMetal_Damaged_Orange` | MaterialInstance | 0.00 |  |  | A15,D40,E30 | no |  |
| `/HaloMaterialLibrary/Env/Material/HS/UNSC/MI_UNSC_PaintedMetal_Damaged_Orange_Sand` | MaterialInstance | 0.00 |  |  | D40 | no |  |
| `/HaloMaterialLibrary/Env/Material/HS/UNSC/MI_UNSC_PaintedMetal_Damaged_Red` | MaterialInstance | 0.00 |  |  | A15,D40,E30 | no |  |
| `/HaloMaterialLibrary/Env/Material/HS/UNSC/MI_UNSC_PaintedMetal_Damaged_Red_Sand` | MaterialInstance | 0.00 |  |  | D40 | no |  |
| `/HaloMaterialLibrary/Env/Material/HS/UNSC/MI_UNSC_PaintedMetal_Damaged_Yellow` | MaterialInstance | 0.00 |  |  | A15,D40,E30 | no |  |
| `/HaloMaterialLibrary/Env/Material/HS/UNSC/MI_UNSC_PaintedMetal_Damaged_Yellow_Sand` | MaterialInstance | 0.00 |  |  | D40 | no |  |
| `/HaloMaterialLibrary/Env/Material/HS/UNSC/MI_UNSC_PaintedMetal_Green_Rough2_Mid` | MaterialInstance | 0.00 |  |  | A15,D40,E10,E20 | no |  |
| `/HaloMaterialLibrary/Env/Material/HS/UNSC/MI_UNSC_PaintedMetal_Grey_1Dark_Rough1_Low` | MaterialInstance | 0.00 |  |  | A15,D40,E10,E20,E30 | no |  |
| `/HaloMaterialLibrary/Env/Material/HS/UNSC/MI_UNSC_PaintedMetal_Grey_1Dark_Rough1_Low_Char` | MaterialInstance | 0.31 |  |  | D40 | no |  |
| `/HaloMaterialLibrary/Env/Material/HS/UNSC/MI_UNSC_PaintedMetal_Grey_1Dark_Rough2_Mid` | MaterialInstance | 0.00 |  |  | A15,D40,E10,E30 | no |  |
| `/HaloMaterialLibrary/Env/Material/HS/UNSC/MI_UNSC_PaintedMetal_Grey_1Dark_Rough3_High` | MaterialInstance | 0.00 |  |  | A15,D40,E30 | no |  |
| `/HaloMaterialLibrary/Env/Material/HS/UNSC/MI_UNSC_PaintedMetal_Grey_1Dark_Rough3_High_Char` | MaterialInstance | 0.31 |  |  | D40 | no |  |
| `/HaloMaterialLibrary/Env/Material/HS/UNSC/MI_UNSC_PaintedMetal_Grey_2Mid_Rough1_Low` | MaterialInstance | 0.00 |  |  | A15,D40,E30 | no |  |
| `/HaloMaterialLibrary/Env/Material/HS/UNSC/MI_UNSC_PaintedMetal_Grey_2Mid_Rough2_Mid` | MaterialInstance | 0.00 |  |  | A15,D40,E10,E20,E30 | no |  |
| `/HaloMaterialLibrary/Env/Material/HS/UNSC/MI_UNSC_PaintedMetal_Grey_2Mid_Rough2_Mid_Char` | MaterialInstance | 0.31 |  |  | D40 | no |  |
| `/HaloMaterialLibrary/Env/Material/HS/UNSC/MI_UNSC_PaintedMetal_Grey_2Mid_Rough3_High` | MaterialInstance | 0.00 |  |  | A15,D40,E30 | no |  |
| `/HaloMaterialLibrary/Env/Material/HS/UNSC/MI_UNSC_PaintedMetal_Grey_3Light_Rough1_Low` | MaterialInstance | 0.00 |  |  | A15,D40 | no |  |
| `/HaloMaterialLibrary/Env/Material/HS/UNSC/MI_UNSC_PaintedMetal_Grey_3Light_Rough1_Low_Char` | MaterialInstance | 0.31 |  |  | D40 | no |  |
| `/HaloMaterialLibrary/Env/Material/HS/UNSC/MI_UNSC_PaintedMetal_Grey_3Light_Rough2_Mid` | MaterialInstance | 0.00 |  |  | A15,D40,E30 | no |  |
| `/HaloMaterialLibrary/Env/Material/HS/UNSC/MI_UNSC_PaintedMetal_Grey_3Light_Rough2_Mid_Char` | MaterialInstance | 0.31 |  |  | D40 | no |  |
| `/HaloMaterialLibrary/Env/Material/HS/UNSC/MI_UNSC_PaintedMetal_Grey_3Light_Rough3_High` | MaterialInstance | 0.00 |  |  | A15,D40 | no |  |
| `/HaloMaterialLibrary/Env/Material/HS/UNSC/MI_UNSC_PaintedMetal_Grey_3Light_Rough3_High_Char` | MaterialInstance | 0.31 |  |  | D40 | no |  |
| `/HaloMaterialLibrary/Env/Material/HS/UNSC/MI_UNSC_PaintedMetal_LessRed_Rough3_High` | MaterialInstance | 0.00 |  |  | A15 | no |  |
| `/HaloMaterialLibrary/Env/Material/HS/UNSC/MI_UNSC_PaintedMetal_OrangeDark_Rough1_Low` | MaterialInstance | 0.00 |  |  | A15,D40,E30 | no |  |
| `/HaloMaterialLibrary/Env/Material/HS/UNSC/MI_UNSC_PaintedMetal_OrangeDark_Rough1_Low_Char` | MaterialInstance | 0.31 |  |  | D40 | no |  |
| `/HaloMaterialLibrary/Env/Material/HS/UNSC/MI_UNSC_PaintedMetal_OrangeDark_Rough2_Mid` | MaterialInstance | 0.00 |  |  | D40,E20 | no |  |
| `/HaloMaterialLibrary/Env/Material/HS/UNSC/MI_UNSC_PaintedMetal_OrangeDark_Rough2_Mid_Char` | MaterialInstance | 0.31 |  |  | D40 | no |  |
| `/HaloMaterialLibrary/Env/Material/HS/UNSC/MI_UNSC_PaintedMetal_Orange_Rough1_Low` | MaterialInstance | 0.00 |  |  | A15,D40,E10,E20 | no |  |
| `/HaloMaterialLibrary/Env/Material/HS/UNSC/MI_UNSC_PaintedMetal_Orange_Rough1_Low_Char` | MaterialInstance | 0.31 |  |  | D40 | no |  |
| `/HaloMaterialLibrary/Env/Material/HS/UNSC/MI_UNSC_PaintedMetal_Orange_Rough2_Mid` | MaterialInstance | 0.00 |  |  | A15,D40 | no |  |
| `/HaloMaterialLibrary/Env/Material/HS/UNSC/MI_UNSC_PaintedMetal_Orange_Rough3_High` | MaterialInstance | 0.00 |  |  | A15,D40 | no |  |
| `/HaloMaterialLibrary/Env/Material/HS/UNSC/MI_UNSC_PaintedMetal_Red_Rough1_Low` | MaterialInstance | 0.00 |  |  | A15,D40 | no |  |
| `/HaloMaterialLibrary/Env/Material/HS/UNSC/MI_UNSC_PaintedMetal_Red_Rough2_Mid` | MaterialInstance | 0.00 |  |  | A15,D40 | no |  |
| `/HaloMaterialLibrary/Env/Material/HS/UNSC/MI_UNSC_PaintedMetal_Red_Rough3_High` | MaterialInstance | 0.00 |  |  | A15,D40 | no |  |
| `/HaloMaterialLibrary/Env/Material/HS/UNSC/MI_UNSC_Painted_Metal_Beige_Rough1_Low` | MaterialInstance | 0.00 |  |  | A15,D40,E30 | no |  |
| `/HaloMaterialLibrary/Env/Material/HS/UNSC/MI_UNSC_PlasticDamaged_Beige` | MaterialInstance | 0.00 |  |  | D40 | no |  |
| `/HaloMaterialLibrary/Env/Material/HS/UNSC/MI_UNSC_PlasticDamaged_Black` | MaterialInstance | 0.00 |  |  | A15,D40,E30 | no |  |
| `/HaloMaterialLibrary/Env/Material/HS/UNSC/MI_UNSC_PlasticDamaged_Black_Sand` | MaterialInstance | 0.00 |  |  | D40 | no |  |
| `/HaloMaterialLibrary/Env/Material/HS/UNSC/MI_UNSC_PlasticDamaged_Blue` | MaterialInstance | 0.00 |  |  | D40 | no |  |
| `/HaloMaterialLibrary/Env/Material/HS/UNSC/MI_UNSC_PlasticDamaged_Blue_Sand` | MaterialInstance | 0.00 |  |  | D40 | no |  |
| `/HaloMaterialLibrary/Env/Material/HS/UNSC/MI_UNSC_PlasticDamaged_Grey` | MaterialInstance | 0.00 |  |  | A15,D40 | no |  |
| `/HaloMaterialLibrary/Env/Material/HS/UNSC/MI_UNSC_PlasticDamaged_Grey_Sand` | MaterialInstance | 0.00 |  |  | D40 | no |  |
| `/HaloMaterialLibrary/Env/Material/HS/UNSC/MI_UNSC_PlasticDamaged_Orange` | MaterialInstance | 0.00 |  |  | D40 | no |  |
| `/HaloMaterialLibrary/Env/Material/HS/UNSC/MI_UNSC_PlasticDamaged_Orange_Sand` | MaterialInstance | 0.00 |  |  | D40 | no |  |
| `/HaloMaterialLibrary/Env/Material/HS/UNSC/MI_UNSC_PlasticDamaged_Red` | MaterialInstance | 0.00 |  |  | A15,D40 | no |  |
| `/HaloMaterialLibrary/Env/Material/HS/UNSC/MI_UNSC_PlasticDamaged_Red_Sand` | MaterialInstance | 0.00 |  |  | D40 | no |  |
| `/HaloMaterialLibrary/Env/Material/HS/UNSC/MI_UNSC_PlasticDamaged_White` | MaterialInstance | 0.00 |  |  | D40 | no |  |
| `/HaloMaterialLibrary/Env/Material/HS/UNSC/MI_UNSC_PlasticDamaged_Yellow` | MaterialInstance | 0.00 |  |  | A15,D40,E30 | no |  |
| `/HaloMaterialLibrary/Env/Material/HS/UNSC/MI_UNSC_Plastic_Beige_Rough1_Low` | MaterialInstance | 0.00 |  |  | A15,A30,A50,B30,B40,C10,C20,C45,D20,D40,E10,E20,E30 | no |  |
| `/HaloMaterialLibrary/Env/Material/HS/UNSC/MI_UNSC_Plastic_Black_Rough1_Low` | MaterialInstance | 0.00 |  |  | A15,A30,A50,B30,B40,C10,C20,C45,D20,D40,E10,E20,E30 | no |  |
| `/HaloMaterialLibrary/Env/Material/HS/UNSC/MI_UNSC_Plastic_Black_Rough3_High` | MaterialInstance | 0.00 |  |  | A15,D40,E30 | no |  |
| `/HaloMaterialLibrary/Env/Material/HS/UNSC/MI_UNSC_Plastic_Black_Rough3_High_Char` | MaterialInstance | 0.29 |  |  | D40 | no |  |
| `/HaloMaterialLibrary/Env/Material/HS/UNSC/MI_UNSC_Plastic_Blue_Rough1_Low` | MaterialInstance | 0.00 |  |  | A15,D40,E30 | no |  |
| `/HaloMaterialLibrary/Env/Material/HS/UNSC/MI_UNSC_Plastic_Blue_Rough3_High` | MaterialInstance | 0.00 |  |  | A15,D40 | no |  |
| `/HaloMaterialLibrary/Env/Material/HS/UNSC/MI_UNSC_Plastic_Grey_Rough1_Low` | MaterialInstance | 0.00 |  |  | A15,A30,A50,B30,B40,C10,C20,C45,D20,D40,E10,E20,E30 | no |  |
| `/HaloMaterialLibrary/Env/Material/HS/UNSC/MI_UNSC_Plastic_Grey_Rough3_High` | MaterialInstance | 0.00 |  |  | A15,D40 | no |  |
| `/HaloMaterialLibrary/Env/Material/HS/UNSC/MI_UNSC_Plastic_Orange_Rough1_Low` | MaterialInstance | 0.00 |  |  | A15,D40 | no |  |
| `/HaloMaterialLibrary/Env/Material/HS/UNSC/MI_UNSC_Plastic_Orange_Rough3_High` | MaterialInstance | 0.00 |  |  | A15,D40,E30 | no |  |
| `/HaloMaterialLibrary/Env/Material/HS/UNSC/MI_UNSC_Plastic_Red_Rough1_Low` | MaterialInstance | 0.00 |  |  | A15,D40,E30 | no |  |
| `/HaloMaterialLibrary/Env/Material/HS/UNSC/MI_UNSC_Plastic_Red_Rough3_High` | MaterialInstance | 0.00 |  |  | A15,D40 | no |  |
| `/HaloMaterialLibrary/Env/Material/HS/UNSC/MI_UNSC_Plastic_White_Rough1_Low` | MaterialInstance | 0.00 |  |  | A15,D40,E10,E20 | no |  |
| `/HaloMaterialLibrary/Env/Material/HS/UNSC/MI_UNSC_Plastic_White_Rough3_High` | MaterialInstance | 0.00 |  |  | A15,D40,E10,E20 | no |  |
| `/HaloMaterialLibrary/Env/Material/HS/UNSC/MI_UNSC_Plastic_Yellow_Rough1_Low` | MaterialInstance | 0.00 |  |  | A15,D40 | no |  |
| `/HaloMaterialLibrary/Env/Material/HS/UNSC/MI_UNSC_Plastic_Yellow_Rough3_High` | MaterialInstance | 0.00 |  |  | A15,D40 | no |  |
| `/HaloMaterialLibrary/Env/Material/HS/UNSC/MI_UNSC_Ship_Greeble_01_Damaged` | MaterialInstance | 0.20 |  |  | A15,D40,E30 | no |  |
| `/HaloMaterialLibrary/Env/Material/HS/UNSC/MI_UNSC_Ship_Greeble_01_Damaged_Burning` | MaterialInstance | 0.21 |  |  | E30 | no |  |
| `/HaloMaterialLibrary/Env/Material/HS/UNSC/MI_UNSC_Ship_Greeble_01_Damaged_OS` | MaterialInstance | 0.09 |  |  |  | no |  |
| `/HaloMaterialLibrary/Env/Material/HS/UNSC/MI_UNSC_Ship_Greeble_02_Damaged` | MaterialInstance | 0.09 |  |  | E30 | no |  |
| `/HaloMaterialLibrary/Env/Material/HS/UNSC/MI_UNSC_Ship_Greeble_03_Damaged` | MaterialInstance | 0.00 |  |  | D40,E30 | no |  |
| `/HaloMaterialLibrary/Env/Material/HS/UNSC/ObjectSpace/MI_UNSC_Metal_Damaged_OS` | MaterialInstance | 0.28 |  |  | A15,D40 | no |  |
| `/HaloMaterialLibrary/Env/Material/HS/UNSC/ObjectSpace/MI_UNSC_Metal_Rough1_Low_OS` | MaterialInstance | 0.09 |  |  | A15,D40 | no |  |
| `/HaloMaterialLibrary/Env/Material/HS/UNSC/ObjectSpace/MI_UNSC_Metal_Rough2_Mid_OS` | MaterialInstance | 0.09 |  |  | A15,D40 | no |  |
| `/HaloMaterialLibrary/Env/Material/HS/UNSC/ObjectSpace/MI_UNSC_PaintedMetal_Beige_Rough2_Mid_OS` | MaterialInstance | 0.09 |  |  | A15,D40 | no |  |
| `/HaloMaterialLibrary/Env/Material/HS/UNSC/ObjectSpace/MI_UNSC_PaintedMetal_Green_Rough2_Mid_OS` | MaterialInstance | 0.09 |  |  |  | no |  |
| `/HaloMaterialLibrary/Env/Material/HS/UNSC/ObjectSpace/MI_UNSC_PaintedMetal_Grey_1Dark_Rough1_Low_OS` | MaterialInstance | 0.09 |  |  | A15,D40 | no |  |
| `/HaloMaterialLibrary/Env/Material/HS/UNSC/ObjectSpace/MI_UNSC_PaintedMetal_Grey_1Dark_Rough2_Mid_OS` | MaterialInstance | 0.09 |  |  | D40 | no |  |
| `/HaloMaterialLibrary/Env/Material/HS/UNSC/ObjectSpace/MI_UNSC_PaintedMetal_Grey_2Mid_Rough2_Mid_OS` | MaterialInstance | 0.09 |  |  | A15,D40 | no |  |
| `/HaloMaterialLibrary/Env/Material/HS/UNSC/ObjectSpace/MI_UNSC_PaintedMetal_Grey_2Mid_Rough3_High_OS` | MaterialInstance | 0.09 |  |  | A15,D40 | no |  |
| `/HaloMaterialLibrary/Env/Material/HS/UNSC/ObjectSpace/MI_UNSC_PaintedMetal_Orange_Rough2_Mid_OS` | MaterialInstance | 0.09 |  |  | A15,D40 | no |  |
| `/HaloMaterialLibrary/Env/Material/HS/UNSC/ObjectSpace/MI_UNSC_PaintedMetal_Red_Rough2_Mid_OS` | MaterialInstance | 0.09 |  |  | A15,D40 | no |  |
| `/HaloMaterialLibrary/Env/Material/HS/UNSC/ObjectSpace/MI_UNSC_Painted_Metal_Beige_Rough1_Low_OS` | MaterialInstance | 0.09 |  |  | A15 | no |  |
| `/HaloMaterialLibrary/Env/Material/HS/UNSC/ObjectSpace/MI_UNSC_Plastic_Black_Rough1_Low_OS` | MaterialInstance | 0.09 |  |  | A15,D40 | no |  |
| `/HaloMaterialLibrary/Env/Material/HS/UNSC/ObjectSpace/MI_UNSC_Plastic_Blue_Rough3_High_OS` | MaterialInstance | 0.09 |  |  | A15,D40 | no |  |

*Group note:* Shipped FR/UNSC metal material instances (Rough/Light/Dark/Vcol/HeavyGrime/Frost variants)