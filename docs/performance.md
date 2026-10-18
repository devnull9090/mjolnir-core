# Performance: measuring it and what costs what

**Status:** 2026-10-17. Measured on PC 1 (RTX 5090, Ryzen 9 7950X3D, Epic, a
1710x1073 borderless window over Remote Desktop; 200% runs render 3420x2146)
on Death Island, the heaviest remastered map: 535,000 grass
clumps in 245 instanced meshes, 7,700 cliff-cladding rocks, 790 decor pieces.

Players report that the remastered maps play fine without grass and rocks and
slow down with them. This page covers the tools for seeing where frame time
goes, what was measured, what was changed, and what is left.

## Tools

| Tool | What it tells you | Where |
|---|---|---|
| `stat unit` | Frame, Game, Draw (render thread), RHIT, GPU Time, Draws, Prims. Works in this Shipping build. | console |
| `mjolnir_bench` | The cost of the grass, its shadows and its wind, as an A/B at a held camera. | MJOLNIRHud `Scripts/bench.lua`, `bench.log` |
| `mjolnir_bench <cvar> <value>` | The same A/B for any console variable against its current value. | same |
| `mjolnir_hitches` | Per-map median, p95, p99 and worst frame, every hitch with where the camera was and which of our Lua loops ran. Each map's heading in `hitches.log` now carries the settings line. | MJOLNIRHud `Scripts/hitches.lua`, `hitches.log` |
| `r.ScreenPercentage 200` | Makes a fast GPU the bottleneck, so GPU costs show in frame time. | console |

These were tried and do **not** work in Shipping: `stat gpu`, `stat scenerendering`
(compiled out with STATS), `csvprofile`, `startfpschart`. `HighResShot` does
nothing.

### Reading the numbers

- **Warm-up.** The first minutes after a map loads run slow while shaders,
  pipeline states and textures arrive: Death Island read 12.6 ms a frame
  right after loading and 8.1 ms steady. Never take a baseline in the first
  3 minutes. `mjolnir_bench` warns when it is started earlier.
- **Game includes the GPU wait.** At 50% resolution the Game figure fell from
  8.4 to 5.2 ms with nothing else changed. In this build, stat unit's Game
  time includes the game thread waiting for the GPU, so it is not a pure
  CPU measure. Read GPU Time and Draw for where the work is.
- **A fast GPU hides GPU costs.** At 100% on PC 1 the frame is close to
  CPU-bound, so a GPU saving barely moves it. Bench GPU work at
  `r.ScreenPercentage 200`.
- **Draws and Prims miss instanced geometry.** Hiding all 535,000 grass
  clumps changed Draws by about 140 and Prims not at all. Use frame time.
- **Alternate conditions with the baseline.** Single `stat unit` snapshots
  vary by about ±0.5 ms. `mjolnir_bench` alternates base / condition /
  base over 6-second windows, and its baselines repeat within ±0.1 ms.

### `mjolnir_bench`

Stand where you want to measure and type `mjolnir_bench` in the console. The
camera is held for about a minute while it takes turns (2.5 s to settle,
6 s timed):

```
bench on DTI: base 7.94 ms (126 fps), 4 runs from 7.91 to 7.96
bench on DTI:   no grass                     6.42 ms  -1.52 ms  -19.2%
bench on DTI:   no grass shadows             7.29 ms  -0.65 ms  -8.2%
bench on DTI:   no grass wind                7.04 ms  -0.90 ms  -11.4%
```

(Death Island's beach camera, after the cull fix, 2026-10-17.)

Above each table, `bench.log` records the size actually drawn (the viewport,
not the saved resolution, which borderless ignores), window mode, vsync, every
`sg.*` quality level, `r.ScreenPercentage`, the GPU's name and score (from the
game's own `Saved/GpuBenchmark.json`) and the CPU. A player can send that
file, and the numbers can be compared with ours.

The bench runs on the HUD's frame hook. `mjolnir_hitches off` pauses that
hook, and the bench with it.

## What was measured (Death Island)

ABAB, 6 s windows, after warm-up.

**Beach view (the DTI test camera), 100%:**

| Condition | Frame | vs base |
|---|---|---|
| base | 8.1 ms | |
| no grass | 6.6 ms | -1.5 ms (-18%) |
| grass, no shadows | 7.4 ms | -0.7 ms |
| grass, no wind | 7.15 ms | -0.9 ms |
| 7,700 cladding rocks hidden | 7.8 ms | -0.3 ms |

**Island overview, `r.ScreenPercentage 200` (GPU-bound):**

| Condition | Frame | vs base |
|---|---|---|
| base | 13.3 ms | |
| no grass | 10.8 ms | -2.5 ms (-19%) |
| grass, no wind | 12.0 ms | -1.25 ms |
| grass, no shadows | 13.15 ms | -0.15 ms |
| cull fix (below) | 13.2 ms | -0.1 ms |
| wind only within 20 m (`WorldPositionOffsetDisableDistance`) | 13.26 ms | none |

What this says:

- **Grass is a fifth of the frame**, and almost all of it is GPU work. The
  render thread and RHI barely change without it (Draw 3.2 → 3.0 ms, RHIT
  4.3 → 4.0 ms), so the number of components and draw calls is not the
  problem.
- **The cost is geometry, not pixels.** It stays about the same from 100% to
  200% resolution. The meshes are Megascans grass at 570–1,650 triangles
  per clump (LOD0), with two LODs and no Nanite. A GPU with a fifth of a
  5090's throughput pays roughly five times as much: 7–12 ms, which matches
  "slows down with the grass".
- **Wind is half of the grass cost.** World position offset makes every
  clump go through the velocity pass and keeps shadow pages invalid. The
  loader sets the "Rigid" shadow-cache mode, but swaying grass still costs.
  `WorldPositionOffsetDisableDistance` (sway near the camera only) has no
  effect in this build.
- **The rocks are effectively free** (-0.3 ms): the Uluwatu cliff meshes are
  Nanite.
- **Keep virtual shadow maps.** `mjolnir_bench r.Shadow.Virtual.Enable 0`
  read +1.76 ms (+22%) at the beach view: the fallback shadow maps cost more.

## Changes from this investigation

- **Grass that never culled** (MJOLNIRLevelLoader). UE4SS passes a
  fractional Lua number to an `int32` parameter as 0, and an end cull
  distance of 0 means never cull. Foliage bands whose distance worked out
  to a fraction (5000 + 7000 × 1/3 = 7333.3) were drawn across the whole map:
  26 of Death Island's 245 grass components, 51,000 clumps, mostly the
  1,657-triangle groundcover. The lower foliage qualities multiply distances
  by 0.45–0.8, which made more bands fractional, so the setting meant to
  help weak PCs made this worse. Distances are now whole centimetres. After
  the fix, 0 of 245 components are uncullable.
- **No wind at Low and Medium foliage quality** (`Foliage.QUALITY.still`): -9% of
  GPU frame time on the overview. High and Epic are unchanged.
- **Dry zones loop** (MJOLNIRLevelLoader): looked up the GameplayStatics CDO and
  built a name string every 100 ms, 12–13 ms of game thread per second.
  It now reads the camera through the cached controller and compares by
  address.
- **Tooling:** `mjolnir_bench`, and the settings line in `hitches.log`.

## Questions this answers

**Would baking the grass and walls into the paks help?** Not the frame
rate. An instance renders the same whether it comes from a cooked level or
from `AddInstance` at load. Baking would save the 6 s foliage spawn and part
of the 14–16 s dressing, at the cost of a per-map cook pipeline, which has been
fragile for this fork ([ue_mesh_write.md](ue_mesh_write.md): stock-UE cooks
do not load). It is worth doing for load time, not for "slow with grass".

**Nanite?** The rocks already are, and they cost almost nothing. The grass
is not, and we cannot rebuild the game's meshes as Nanite. Nanite foliage
with world position offset is expensive in UE 5.5 anyway. The grass levers
are fewer clumps, shorter cull distances, and wind.

**Is our Lua slow?** Mostly no. The hitch log names every loop that reads
1 ms or more. Apart from the dry zones loop above and the lobby's main-menu
watch (10–21 ms every 1.5 s at the menu only), long frames show "none of our
timed loops". The frame budget is in the GPU.

## What is left

- **Measure a weaker PC.** Every number above is from a 5090. Run
  `mjolnir_bench` on PC 2, or have a player send `bench.log`, to turn "slow
  with grass" into numbers.
- **Pick the foliage tier from the GPU.** `sg.FoliageQuality` only helps
  players who open Video settings. `Saved/GpuBenchmark.json` has a `gpuScore`
  (2060 on the 5090). With calibration across a few cards, the loader could
  choose `keep` / `cull` / `still` from it.
- **Fewer, cheaper clumps on Epic.** Death Island has 535,000. The `bands`
  and cull ranges (100–300 m for grass) were chosen for looks. A density or
  range pass, checked with `mjolnir_bench` and screenshots, is the biggest
  remaining lever.
- **Collect benches and hitch summaries from players** through the crash
  report upload path, opt-in, so we see real hardware.
- Two leads the tools should catch: the user's own Blood Gulch session had
  bursts of 15–25 ms frames with no Lua in them, and ended in a GPU crash
  (device lost) after 39 minutes. Process memory read 13–16 GB in `stat
  unit` on Death Island.
