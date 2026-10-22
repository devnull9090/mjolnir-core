# TST: CE pipeline test map

TST is a small, authored CTF/Slayer map for checking the complete Blender →
classic HEK → CE conversion → Unreal upgrade → local game pipeline. Its CE
cache builds successfully as of 2026-10-19. The first build loaded and spawned
a player after correcting its spawn lift. The revised visual build (r1) is
rebuilt from source. TST merged to main with PR #208 (2026-10-20). Of the
in-game checks below, the trees (3) were found clean after a recipe fix,
check 1 was observed on the first build only, and the rest are pending.

The approved ImageGen concept is stored locally at `.dream-loop/concept.png`
(ignored). Dream-loop comparison should use actual game screenshots, especially
the view beneath a tree, after installing the current TST build.

## Sources and features

Authoring sources live in [`levels/test/tst/`](../levels/test/tst/):
`build_geometry.py`, `build_scenario.py`, `placements.json`, `tst.blend`,
`data/levels/test/tst/models/tst.JMS`, and the authored scenario under
`tags/levels/test/tst/`. The geometry script regenerates the Blender scene, JMS,
and placements; the scenario script writes and reads back the binary scenario
to verify its gameplay fields. Positions in the placement JSON are metres;
one CE world unit is 3.048 m. Stock HEK assets stay in the installed kit.

| Feature | Authored contents and pipeline coverage |
|---|---|
| Terrain | Approximately 120 × 60 m; rolling grass, a central hill, and a cliff along one side. Exercises ground extraction, Landscape, cliff materials and collision. |
| Bases | Red/blue BSP structures centred at X = −46/+46 m, each with a flag, two team starts, assault rifle and pistol pickup. Tests CTF/Slayer placement and structure materials. |
| Trees | Three `scenery\trees\tree_leafy_medium\tree_leafy_medium` instances at (−12,−12), (−22,20), and (25,0) m, all yaw/permutation 0. Their model height is 13.57 m; TST pins one replacement recipe per tree, B30's `Lrg_D`, `Lrg_B` and `Lrg_C` in placement order, so one map compares three tree types. |
| Boulders | Three `boulder_granite_medium` scenery instances; tests swapped visuals, near-face bullet hits and player collision. |
| Pond | Shallow basin near (30,−17) m, water surface at −0.18 m. Uses the local `tst_water` shader, derived from the installed B30 water tag, for Fluid Flux conversion. |
| Extras | One Warthog, health pack, one-way teleporter pair from the red side to the blue side, sky sun, and one placed light fixture. |

The TST entry in [`ce_upgrade_maps.json`](../tools/level/ce_upgrade_maps.json)
uses conversion directory `C:/haloce/ce_conversions/test/TST`, Landscape `LTT`,
chunk **969**, four components a side, `bake_foliage: true`,
`tree_variant: Lrg_D,Lrg_B,Lrg_C`, and beach rocks. Ground/cliff tokens are
`levels_b30_shaders_beach` and `levels_test_tst_shaders_tst_cliffs`, from the
installed B30 shader tags. Ground UVs are `(x / 120 + 0.5, y / 120 + 0.5)`
in metres; cliffs use 6 m per repeat, and B30 base panels/floors use 2 m.
Half-metre doorway strips use Danger Canyon's matching red/blue emblem
shaders, with one full emblem per strip. The pond targets B30's
`levels_b30_bitmaps_water_mask` texture, uses `M_CE_Water` with `flux_only`,
and holds the Flux level at −18 cm near Unreal (3000,1700) cm. Verify that
the converted water slot matches this token before treating the pond as tested.

The first screenshots (`.dream-loop/tst-overview-r0.png` and
`.dream-loop/tst-pond-r0.png`) exposed 28.92 m trees and repeated tutorial
ground markings. The original common 6 m UV period repeated a map-sized
ground bitmap across the arena. Revision r1 uses the 13.57 m medium tree,
B30's island bitmap with broad UVs, and separate UV scales for architecture.
It also has a TST-specific `LTT` ground/cliff palette, neutral daylight, clouds,
haze and an ocean horizon at −150 cm. These are source corrections awaiting
fresh visual comparison, not evidence that the concept has been matched.

## Tools and rebuild

Use Blender 5.1, classic HEK at `C:\haloce\hek`, UE 5.5, and the CLI and
helpers built from this checkout. The installed Halo Asset Blender
Development Toolset is
[Release 425](https://github.com/General-101/Halo-Asset-Blender-Development-Toolset/releases/tag/master-425),
add-on 2.425.0, commit `f1351fe1b3b2bb655a195e57a894e7147d8ae4d3`.
The approved [Lite ZIP](https://github.com/General-101/Halo-Asset-Blender-Development-Toolset/releases/download/master-425/halo-asset-blender-toolset-lite-v425%40f1351fe.zip)
has SHA-256 `c5702009f85db5616ef6622a4830337212f957fbd8854643e8c7ebd9cce426a2`.
It is loaded from `C:\haloce\tools\halo-blender-425\addons`; no global Blender
preferences or extra Python packages are required. Local installation evidence
is in that directory's parent `install.json`.

From the repository root, using PowerShell 7:

```powershell
pwsh -File levels/test/tst/rebuild.ps1
# To reuse the already exported geometry and placements:
pwsh -File levels/test/tst/rebuild.ps1 -SkipGeometry
```

The script exports JMS, stages the water shader, compiles the structure,
authors the scenario, runs draft lightmaps (`0 0.1`), and builds
`C:\haloce\hek\maps\tst.map`. It copies the authored scenario into the source
tree; BSP, lightmap and map outputs remain in HEK. It temporarily moves the
shared `maps\bitmaps.map` aside so the new lightmap is embedded, then restores
it in `finally`. Existing backup files must be resolved before rerunning.
Logs are in `.dream-loop/tst-rebuild/<run>/`; nonzero exits, logged errors and
missing or stale outputs fail the build. Known optional add-on warnings and
the expected hidden-bitmap-cache diagnostic are handled explicitly.

The rebuild also stages the installed HCEEK B30 `beach`/`cliffs` shaders and
`beach.bitmap` into classic HEK when absent, retaining their stock references.
`-MccTagsRoot` selects another installed tag directory. A differing existing
HEK file stops the rebuild instead of overwriting it; stock assets remain
outside this repository. A local `tst_cliffs` copy preserves B30's references
and avoids HEK resolving the ambiguous `cliffs` name to the Mirror shader.
The medium CE tree has no stock collision reference;
the upgrade's collision stage supplies collision from the swapped B30 trunk.

The r1 full rebuild passed at `.dream-loop/tst-rebuild/20261019-214210-419/`.
The compiled BSP references were checked for the intended B30 beach, local
`tst_cliffs`, B30 exterior panels/floor and Danger Canyon trims; no tutorial or
Mirror shader remained. Scenario readback matched the authored placements:
eight scenery entries, four player starts, four netgame flags, five pickups,
one vehicle and one light fixture. The shared bitmap cache was restored.

Run conversion and upgrade sequentially from **Git Bash at this worktree's
root**. Explicit paths avoid accidentally using an older CLI from another
checkout:

```bash
# Build the helpers from this checkout when setting up or changing source.
cargo build --release -p blam-cli
cargo build --release -p ue-asset --example mesh_rewrite
cargo build --release -p blam-pack --example package_override --example package_add
cargo build --release -p ue-texture --example lightmap_bake
cargo build -p ue-iostore --example extract_file
cargo build -p ue-asset --example retarget_package

export TST_REPO="$(pwd -W)"
export HCE_GAME="C:/Program Files (x86)/Steam/steamapps/common/Halo Campaign Evolved"
export HCE_PAKS="$HCE_GAME/Meteorite/Content/Paks"
export MJOLNIR="$TST_REPO/target/release/mjolnir.exe"
export MJOLNIR_DEBUG="$MJOLNIR"
export MJOLNIR_EXAMPLES="$TST_REPO/target/release/examples"
export EXAMPLES="$TST_REPO/target/debug/examples"
export HALO2UE_EXPORT="C:/Users/will/prj/HalcyonRing-devnull9090/tools/halo2ue/exporter/target/release/halo2ue-export.exe"
export PYTHONUTF8=1
export CE_COOK=1
export LIGHTMAP_ARGS="--placed-lights"
export CE_START_LIFT=0.1

bash tools/level/convert_ce_map.sh \
  C:/haloce/hek/maps/tst.map TST C:/haloce/ce_conversions/test/TST

# Every upgrade stage except install; output defaults to ce_conversions/upgrade/TST.
python tools/level/upgrade_ce_map.py TST

# Close the game before installing the completed local build.
python tools/level/upgrade_ce_map.py TST --stages install --local-install
```

TST uses `CE_START_LIFT=0.1` CE world units (30.48 cm) for its low-ceiling
base interiors. This raises each authored start from 65 cm to 95.48 cm and
applies to both player starts and spawn-point scenery. The converter forwards
this setting as `gen_ce_level.py --start-lift`; leaving it unset preserves the
existing 1.0-unit default. The initial TST load with that default placed starts
at 369.8 cm beneath a 410 cm ceiling and created no player biped. Regenerating,
baking and installing with the lower lift produced a valid player unit in
the next Slayer test. Recheck after each source rebuild.

`--local-install` requires the CE runtime, loader/native DLL and game variants
already installed. It installs this local map and refreshes registration/menu
data without requiring a hub listing. The game was closed during the initial
build; check again before each install. Run only one conversion, Unreal editor
or cook against this project at a time. Do not edit running scripts.

## In-game acceptance

Use the repository's game MCP bridge for this task's control, inspection and
screenshots, as requested by the user. Its `game_status`, `game_console`,
`game_lua`, `game_input` and `game_screenshot` tools are described in
[game automation](game_automation.md). If those MCP tools are not loaded,
`node tools/mcp/game/cli.mjs` exposes the same bridge. General desktop
automation is outside this task's selected workflow. World screenshots need
`game_screenshot` with `foreground: true`; the default PrintWindow capture
can show the HUD over a black 3D view.

Launch through Steam, press Enter at the title screen, and wait for
`MULTIPLAYER is on the main menu` in
`Meteorite/Binaries/Win64/ue4ss/UE4SS.log`. Host with
`mjolnir_auto host TST slayer private`, then repeat in CTF using
`mjolnir_auto host TST ctf private`. Return to the main menu and load the
reference mission, B30 (The Silent Cartographer), through the game's own
campaign menu: on CU4, `mjolnir_mission` from the frontend loads the world but
never starts the mission ([multiplayer investigation notes](multiplayer_investigation_notes.md)).

The first build's post-fix CTF load is recorded in
`.dream-loop/tst-ctf-r0.log`: 10,409 baked clumps in 549 meshes, 142 baked
rocks and 0.1 s foliage setup. Its initial measured load frame was 439 ms,
including a 375 ms loader tick (plus 37 ms for flags and 21 ms for health
packs). Those counts and timings describe r0; repeat the measurement for r1.
The later full-session summary also records a one-second frame, so the
initial-load measurement does not establish stutter-free play throughout.

| # | Required observation | Status / evidence |
|---|---|---|
| 1 | Hosting loads TST and spawns the player; loader log confirms baked foliage and a load frame under 1 s. | Observed on r0 after the spawn-lift fix: valid player unit, baked foliage, 439 ms initial load frame / 375 ms loader tick. Repeat on r1. |
| 2 | Both bases, team starts and flags support CTF, including flag pickup/return/capture. | Pending in-game test. |
| 3 | From beneath each swapped tree (`Lrg_D`, `Lrg_B`, `Lrg_C`), twigs join limbs without detached bare stems; compare the same B30 tree type from the same angle. | After the recipe fix of 2026-10-19 (8a4da432: no neighbour's twigs), the user found all three of TST's trees clean. The side-by-side B30 comparison is not recorded. |
| 4 | Bullets stop at the near faces of swapped rocks and tree trunks. | Pending in-game test. |
| 5 | Players collide correctly with rocks, trunks and the cliff. | Pending in-game test. |
| 6 | Pond renders as Flux water with shallow edges and no water sheets on walls/cliffs. | Pending in-game test. |
| 7 | Trees and grass remain assembled and stable, apart from light flutter. | Pending in-game test. |

Record a screenshot or log line for each result. Also exercise the teleporter,
health pickup and Warthog. Never inspect properties of baked `MJDecor_*` or
`MJClad_*` actors through UE4SS Lua; those reads have crashed the game. B30's
own components may be inspected for the reference comparison. The loader is
at Lua's 200-local limit, so do not add top-level locals when instrumenting it.

This is a local test build: no release tags or hub publication. Other installed
maps are not acceptance evidence for TST and still require their own rebuilds
and release testing. For pipeline details, see [CE conversion](ce_map_conversion.md),
[terrain collision](ce_terrain_collision.md), and [performance](performance.md).
