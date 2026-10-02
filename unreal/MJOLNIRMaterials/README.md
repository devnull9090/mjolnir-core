# MJOLNIR Materials

The Unreal Engine 5.5 project that builds and cooks the materials and bitmaps
of converted Halo CE maps ([docs/ce_map_conversion.md](../../docs/ce_map_conversion.md),
"Materials"). `tools/level/convert_ce_map.sh` drives it. This page covers
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
that end up inside compiled shaders ([docs/re/fork_renderer.md](../../docs/re/fork_renderer.md)).

| Difference | Reproduced by |
|---|---|
| 24 global uniform buffer layouts | `Plugins/MjolnirForkLayouts` (module `MjolnirForkLayouts`), from `Config/ForkUniformBuffers.json` |
| GPU-scene primitive stride 44 (stock 43), custom data from element 35 | the same plugin, module `MjolnirForkShaders`: `/Engine/Shared` and `/Engine/Private` remapped to patched copies under `Intermediate/` |
| The game's renderer settings (they decide which permutations cook) | `Config/DefaultEngine.ini` `[/Script/Engine.RendererSettings]` |
| No editor selection colour in the shaders | `r.CompileShadersForDevelopment=0` |
| Material instances and parameter collections serialize differently | not cooked: the level loader makes dynamic instances at runtime |

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

3. After a game update, re-dump the uniform buffers with the game running
   (`tools/ue/ub_dump.py HaloCampaignEvolved.exe HaloCampaignEvolved.exe
   unreal/MJOLNIRMaterials/Config/ForkUniformBuffers.json`) and check the
   cook log line `fork layouts: … 0 do not`.

## Running it

The scripts run the editor as a commandlet, limited to 8 cores at
below-normal priority: full-machine shader compiles have powered the dev box
off. The editor resets its own affinity once up, so keep a watcher re-pinning
`UnrealEditor-Cmd` and `ShaderCompileWorker` while they run.

```powershell
powershell -File tools/ue/editor_cmd.ps1 -Script Scripts/build_ce_materials.py   # masters, defaults, chunk label
$env:MJ_CE_SPEC = "out\bgl\materials.spec.json"
powershell -File tools/ue/editor_cmd.ps1 -Script Scripts/build_ce_level.py       # one level's bitmaps
powershell -File tools/ue/cook.ps1                                               # pakchunk988
bash tools/ue/install_cook.sh                                                    # into the game (closed)
```

`Content/` is build output: every level built so far stays in it, so one
container carries them all.

## Widgets

The project also builds MJOLNIR's own Widget Blueprints (`/Game/MJOLNIR/UI`,
chunk 984) with `Scripts/build_mjolnir_ui.py` and the editor-only
`Plugins/MjolnirUIBuilder`. See [docs/custom_ui.md](../../docs/custom_ui.md).
