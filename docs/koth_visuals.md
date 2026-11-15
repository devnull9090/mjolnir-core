# KOTH field visuals

The hill uses a dedicated energy-field material so its boundary stays readable
while players can see through it. Restrained moving plasma, a visible translucent
veil and glowing rails define the field; a layered beacon 1.1 metres in diameter
and a ground anchor mark the centre. The hill's state colours remain
gold when empty, cyan for you, orange-red for another player, violet when
contested, and the owning team's colour in team modes.

The runtime is `mods/MJOLNIRHud/Scripts/hill.lua`. These are client-side visual
actors: changing their rendering does not change the simulation's scoring
boundary. The existing player/height approximation and multiplayer limitations
are described in [game_modes.md](game_modes.md#34-king-and-oddball-on-converted-ce-maps).

## Assets and reserved container

**Shader chunk 966 is reserved for KOTH and the CTF flag's cloth.** Its shared
shader library must keep the `Meteorite_Chunk966` identity when packaging and
installing. The cloth master (`/Game/MJOLNIR/Cloth/M_CE_FlagCloth`,
`Scripts/build_flag_cloth.py`) shares the chunk rather than taking a number of
its own: the launcher numbers other hub containers 900 + their load order, so
a new 9NN number would collide with some player's map container. A 966 built
by `build_koth.ps1` alone lacks the cloth master; MJOLNIRLevelLoader then
moves the cloth's strips from Lua.

| Asset | Purpose |
|---|---|
| `/Game/MJOLNIR/KOTH/M_KOTH_Field` | Translucent perimeter field and glowing rails |
| `/Game/MJOLNIR/KOTH/M_KOTH_Beacon` | Central vertical beacon |
| `pakchunk966-MJOLNIRKOTH-Windows.{pak,utoc,ucas}` | Dedicated KOTH materials and shader library |

`unreal/MJOLNIRMaterials/Scripts/build_koth_materials.py` creates the materials
and their chunk label. The classic `M_CE_Plasma` masters are unchanged. If the
dedicated KOTH assets are unavailable, the runtime falls back to the existing
CE plasma material; if neither is available, the direction line remains.

The container ships in the CE runtime pack from 1.19.0
(`tools/level/build_ce_runtime.sh`). The launcher names it
`pakchunk966-MJOLNIRHUB-mjolnir-ce-runtime-<j>_P`: `hub::shader_chunk` keeps the
966 because the container carries a shader library. The helper below is for
trying a new build of the materials on one PC; take its container out of Paks
again afterwards, or it hides whatever the hub is missing.

## Build locally

Use UE 5.5 and this branch's `Meteorite` cook project. The fork-layout plugins,
shader settings and property retargeting are required; see the
[project setup](../unreal/MJOLNIRMaterials/README.md). On a fresh checkout, build
the two target receipts first from the repository root:

```powershell
$build = 'C:\Program Files\Epic Games\UE_5.5\Engine\Build\BatchFiles\Build.bat'
$project = "$PWD\unreal\MJOLNIRMaterials\Meteorite.uproject"
& $build MeteoriteEditor Win64 Development "-Project=$project" -WaitMutex -MaxParallelActions=4
& $build Meteorite Win64 Shipping "-Project=$project" -WaitMutex -MaxParallelActions=4
cargo build -p blam-cli
```

Build a reviewable package:

```powershell
powershell -NoProfile -File tools/ue/build_koth.ps1
```

The helper runs the material builder through `editor_cmd.ps1`, then `cook.ps1`.
It rejects compiler errors, stale logs, failed fork-layout validation, and a
missing successful retarget of the two KOTH materials. Each run creates a new
directory under ignored `.dream-loop/koth-package/` containing `content/`,
editor/cook logs, an input snapshot and a SHA-256 `receipt.json`. Inputs must
remain unchanged through packaging. `-OutputDir` selects another package root.
Nothing is installed by default.

The default CPU mask is `0x0F` (four logical CPUs), following the cook script's
documented all-core power issue. `-Mask` selects a different nonzero affinity;
the helper temporarily overrides `MJ_CPU_MASK` and re-applies affinity to its
own editor and shader-worker descendants when the editor resets it. It restores
the environment afterward. Build and cook share the project's named mutex, so
another conversion cannot replace staging before the package is copied.

## Install and inspect

Close the game, then explicitly request a build and install:

```powershell
powershell -NoProfile -File tools/ue/build_koth.ps1 -Install
# Or select an install explicitly (Xbox: the directory named Content):
powershell -NoProfile -File tools/ue/build_koth.ps1 -Install -GameDir 'C:\Games\Halo Campaign Evolved'
```

Steam libraries are discovered automatically; `MJOLNIR_GAME_DIR` is also
supported. Installation refuses while `HaloCampaignEvolved` is running. It
copies only the three named chunk966 files into `Meteorite/Content/Paks`, saves
previous versions under the run's `previous-install/`, checks installed hashes,
and writes `installed.json`. Copy or hash failures trigger rollback of those
files while the game remains stopped; a failure record preserves recovery
details. It does not deploy HUD Lua or other containers.
Deploy the branch's HUD scripts separately using the normal local mod workflow.
To undo an installed update, close the game and restore those three previous
files. For a first install with no previous files, remove only the three KOTH
files; the HUD will use its fallback. Keep the package and backups until the
visual check is complete. This helper does not publish a release.

For live checks, follow [game automation](game_automation.md): launch, finish
stock sign-in, verify `mjolnir_auto state` reports `signed_in=1`, then host a
private match with `mjolnir_auto host PRS koth private` or use BGL. Confirm the
loaded mode: released maps without KOTH in their mode list can fall back to
Slayer. A bridge-loaded visual preview in that case checks rendering only.
Capture the
3D world with `foreground:true`; the default window capture can show a black
world. Compare the hill from outside, inside, and across a roof edge, and check
empty, owned and contested states. A stand-in player list is useful for colour
inspection but does not prove live multiplayer state replication.

## Validation status

The branch-local Editor Development and Shipping targets built successfully.
`lua tools/tests/test_hill_marker.lua` passes, including mocked material
selection, actor reuse, parameter updates, material recreation, fallback,
retry and visibility checks. The build helper passed six temporary-filesystem
simulations covering installation, rollback and input-change detection.

The final material cook compiled both materials, passed fork-layout validation,
retargeted both packages and installed the three chunk966 files with matching
hashes. The local evidence is under
`.dream-loop/koth-package/20261105-025531-639818/` (ignored build output).

Live bridge previews loaded the workspace's hill module in private PRS and BGL
matches; the final wider beacon and stronger field were inspected on BGL.
Gold and cyan were visually sampled; other state transitions are covered by
the Lua tests. The installed released HUD differs from this branch, so these
previews do not establish deployed HUD integration or end-to-end KOTH scoring.
Two-PC replication and a controlled final-effect GPU performance comparison
have not been performed. Generated concept images remain design references;
the screenshots capture the running game. No release was published.
