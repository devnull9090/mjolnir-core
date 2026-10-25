# MJOLNIR Materials

The Unreal Engine 5.5 project that builds and cooks the materials and bitmaps
of converted Halo CE maps ([docs/ce_map_conversion.md](../../docs/ce_map_conversion.md),
"Materials"), and for the remastered maps their Landscape worlds, tessellated
cliffs and water masters. `tools/level/convert_ce_map.sh` drives it, and
`tools/level/upgrade_ce_map.py` for the remastered maps. This page covers
setting it up and running it by hand.

It is a separate project from [`MJOLNIRMapKit`](../MJOLNIRMapKit), which cooks
empty worlds, because the two cook with opposite shader settings. Materials
need the shared shader library (`bShareMaterialShaderCode`): its name,
`Meteorite_Chunk988`, is the game's project name plus the container's chunk,
and the game opens a library named that way when the container mounts. That
is also why the project must be named **Meteorite**.

## What it reproduces of the game's engine

The game runs 343's fork of UE 5.5.4. A material cooked by a stock editor
binds and draws in it only once the editor matches the fork in the places
that end up inside compiled shaders and cooked packages ([docs/re/fork_renderer.md](../../docs/re/fork_renderer.md)).

| Difference | Reproduced by |
|---|---|
| 24 global uniform buffer layouts | `Plugins/MjolnirForkLayouts` (module `MjolnirForkLayouts`), from `Config/ForkUniformBuffers.json` |
| GPU-scene primitive stride 44 (stock 43), custom data from element 35 | the same plugin, module `MjolnirForkShaders`: `/Engine/Shared` and `/Engine/Private` remapped to patched copies under `Intermediate/` |
| The game's renderer settings (they decide which permutations cook) | `Config/DefaultEngine.ini` `[/Script/Engine.RendererSettings]` |
| No editor selection colour in the shaders | `r.CompileShadersForDevelopment=0` |
| Nanite raster: a 992-byte `FPackedNaniteView`, the HW raster's clip position handed to the pixel shader, `FRasterizePassParameters` at the fork's offsets | `MjolnirForkShaders` (patched `Private/Nanite/*`) and `MjolnirForkLayouts` (the parameter offsets) |
| Property blocks are laid out differently (343's `Material` and `PrimitiveComponent` carry extra slots) | `tools/ue/cook.ps1` re-encodes every staged chunk container in the game's layout after the cook (`mjolnir ue retarget --rewrite`; materials and material instances by default, `-Classes` adds more) |
| Game assets our masters and instances read (`MPC_DeformationGlobals`, the game's foliage meshes and materials) | never-cooked stand-ins at the game's paths (`Plugins/HaloLandscapeDeformations`, `/Game/Env`, `/Game/Megascans`; `DirectoriesToNeverCook`): in game the references resolve to the game's own. No parameter collection of ours is cooked, and the CE masters' per-slot instances are made at runtime by the level loader |

The engine install itself is never modified. The shader override applies to
this project only; `-MjolnirStockShaders` turns it off. The editor's own
renderer still uses the stock layouts, so the project is for cooking, not
for viewing materials in the editor.

## Setup

1. UE 5.5 from the Epic Games Launcher (the converter expects
   `C:/Program Files/Epic Games/UE_5.5`).
2. Build the plugin once into its `Binaries`:

   ```powershell
   & "C:\Program Files\Epic Games\UE_5.5\Engine\Build\BatchFiles\RunUAT.bat" BuildPlugin `
       -Plugin="$PWD\unreal\MJOLNIRMaterials\Plugins\MjolnirForkLayouts\MjolnirForkLayouts.uplugin" `
       -Package="$env:TEMP\MjolnirForkLayoutsBuild" -TargetPlatforms=Win64
   Copy-Item "$env:TEMP\MjolnirForkLayoutsBuild\Binaries" unreal\MJOLNIRMaterials\Plugins\MjolnirForkLayouts -Recurse -Force
   ```

3. Build the project's editor and Shipping targets once. The project enables
   CommonUI (MJOLNIR's menu screens derive from `CommonActivatableWidget`),
   which makes UAT treat it as a code project: the cook needs both target
   receipts. Both builds take under a minute (the engine plugins come
   precompiled):

   ```powershell
   $bat = "C:\Program Files\Epic Games\UE_5.5\Engine\Build\BatchFiles\Build.bat"
   & $bat MeteoriteEditor Win64 Development -Project="$PWD\unreal\MJOLNIRMaterials\Meteorite.uproject" -WaitMutex
   & $bat Meteorite Win64 Shipping -Project="$PWD\unreal\MJOLNIRMaterials\Meteorite.uproject" -WaitMutex
   ```

   The editor build also compiles both project plugins.

4. After a game update, re-dump the uniform buffers with the game running
   (`tools/ue/ub_dump.py HaloCampaignEvolved.exe HaloCampaignEvolved.exe
   unreal/MJOLNIRMaterials/Config/ForkUniformBuffers.json`) and check the
   cook log line `fork layouts: … 0 do not`.

## Running it

The scripts run the editor as a commandlet at below-normal priority, on every
core unless `-Mask` or `MJ_CPU_MASK` (hex) limits them. With a mask set, the
editor resets its own affinity once up, so keep a watcher re-pinning
`UnrealEditor-Cmd` and `ShaderCompileWorker` while they run. Every editor run
and cook takes the named mutex `MjolnirMeteoriteProject`, so only one Unreal
process works on the project at a time; conversions running side by side wait
for it.

```powershell
powershell -File tools/ue/editor_cmd.ps1 -Script Scripts/build_ce_materials.py   # masters, defaults, chunk label
$env:MJ_CE_SPEC = "out\bgl\materials.spec.json"
powershell -File tools/ue/editor_cmd.ps1 -Script Scripts/build_ce_level.py       # one level's bitmaps
powershell -File tools/ue/cook.ps1                                               # every chunk, re-encoded for the game
HCE_PAKS="<game>/Meteorite/Content/Paks" bash tools/ue/install_cook.sh           # 988 into the game (closed)
```

`cook.ps1` re-encodes each staged container in the game's property layout with
`mjolnir ue retarget --rewrite`, so build the CLI first (`target/release/mjolnir.exe`)
or point `MJOLNIR` at one; without it the cook prints a warning and the
materials are misread in game. Copy containers out of staging only after it
returns.

`Content/` is build output: every level built so far stays in it. What lands
in which container:

| Chunk | What | Built by |
|---|---|---|
| 988 | the CE masters, shared textures, event sounds, and the maps converted before per-map chunks (`/Game/MJOLNIR/Levels`) | `Scripts/build_ce_materials.py`, `build_ce_textures.py`, `build_ce_sounds.py` |
| a map's own | a map with a code of its own (`/Game/MJOLNIR/Maps/<CODE>`): its bitmaps and ambient sounds, shipped in its map pack ([docs/map_distribution.md](../../docs/map_distribution.md)) | `Scripts/build_ce_level.py`, `build_ce_sounds.py` |
| 984 | MJOLNIR's widgets (see [Widgets](#widgets)) | `Scripts/build_mjolnir_ui.py` |
| 983 | the trial masters and the tessellated cliffs | `Scripts/build_ce_materials.py` (`MJ_CE_ROOT=/Game/MJOLNIR/CETrial`, `MJ_CE_CHUNK=983`), `build_ce_cliffs.py` |
| 982 | the water masters | `Scripts/build_ce_water.py` |
| one per remastered map (`MJ_LANDSCAPE_CHUNK`; 979 is Death Island's) | the map's Landscape world, its bakes and its baked foliage | `Scripts/build_ce_landscape.py`, cooked with `cook.ps1 -Map`; `tools/level/bake_editor_world.sh` bakes the world into the map's own container and keeps this one for its shader library |

## Widgets

The project also builds MJOLNIR's own Widget Blueprints (`/Game/MJOLNIR/UI`,
chunk 984) with `Scripts/build_mjolnir_ui.py` and the editor-only
`Plugins/MjolnirUIBuilder`. See [docs/custom_ui.md](../../docs/custom_ui.md).
