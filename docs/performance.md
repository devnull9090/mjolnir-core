# Performance: measuring it and what costs what

**Status:** 2026-10-18. Measured on PC 1 (RTX 5090, Ryzen 9 7950X3D, Epic) on
Death Island, the heaviest remastered map: 535,000 grass clumps in 245
instanced meshes, 7,700 cliff-cladding rocks, 790 decor pieces. Most runs were
at 1710x1073 (a borderless window over Remote Desktop; the 200% runs render
3420x2146), and the last at 3840x2160. On 2026-10-18 the campaign (B30) was
measured against Blood Gulch and Death Island at the same settings
([Campaign against our maps](#campaign-against-our-maps-2026-10-18)).

Players report that the remastered maps play fine without grass and rocks and
slow down with them. This page covers the tools for seeing where frame time
goes, what was measured, what was changed, and what is left.

## Tools

| Tool | What it tells you | Where |
|---|---|---|
| `stat unit` | Frame, Game, Draw (render thread), RHIT, GPU Time, Draws, Prims. Works in this Shipping build. | console |
| `/bench` (match chat) | The foliage bench below, its result in your chat, and sent to the hub with its settings; admins read them on the moderation page's Benchmarks tab. For players. | MJOLNIRHud `Scripts/bench.lua`, hub `POST /benches` |
| `mjolnir_bench` | The cost of the loader's foliage, its shadows and its wind, as an A/B at a held camera. `mjolnir_bench send` also sends it, as `/bench` does. | MJOLNIRHud `Scripts/bench.lua`, `bench.log` |
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
bench on DTI:   no foliage                   6.42 ms  -1.52 ms  -19.2%
bench on DTI:   no foliage shadows           7.29 ms  -0.65 ms  -8.2%
bench on DTI:   no foliage wind              7.04 ms  -0.90 ms  -11.4%
```

(Death Island's beach camera, after the cull fix, 2026-10-17.)

Above each table, `bench.log` records the size actually drawn (the viewport,
not the saved resolution, which borderless ignores), window mode, vsync, every
`sg.*` quality level, `r.ScreenPercentage`, the GPU's name and score (from the
game's own `Saved/GpuBenchmark.json`) and the CPU. A player can send that
file, and the numbers can be compared with ours.

The bench runs on the HUD's frame hook. `mjolnir_hitches off` pauses that
hook, and the bench with it.

### Where a frame goes

Each row also carries `stat unit`'s split for its turns, averaged over every
timed frame, and `bench.log` records the held camera (`view:`):

```
bench on BGL: base 7.93 ms (126 fps), 4 runs from 7.20 to 9.86  [game 7.36, draw 2.97, rhit 4.48, gpu 5.70]
bench on BGL:   no foliage                   6.50 ms  -1.43 ms  -18.0%  [game 5.97, draw 2.70, rhit 3.94, gpu 4.87]
```

(Blood Gulch at 1280x720 on PC 1 seconds after loading, 2026-10-18: a CPU-bound
frame, GPU 5.7 ms of 7.9.)

A frame is as slow as the slowest of the game thread, the render thread (Draw)
and the GPU, so a cost that lands on the GPU saves nothing while the game
thread is the slow one. Game includes the game thread's wait for the GPU (see
above); the report also carries `game_cp` and `draw_cp`, the critical paths
without waits, and RHIT.

Nothing reflected holds these numbers, so MJOLNIRHud reads them through
`native\mjolnir_frame_times.dll` (`native/frame_times`, built in CI like the
other native halves). It finds `FStatUnitData::DrawStat` in the exe by a byte
pattern and decodes the engine globals that function reads
(`GGameThreadTime`, `GRenderThreadTime`, `GRHIThreadTime`, their critical
paths, and `GDynamicRHI->RHIGetGPUFrameCycles(0)`) from its RIP-relative loads.
They update every frame with `stat unit` off. After a game update that
changes DrawStat the pattern stops matching: the bench still runs, its rows
have no split, and `bench.log` says `no frame times`. After each game update
run `python tools/pe/statunit_pattern.py "<Win64>/HaloCampaignEvolved.exe"`:
it says whether the pattern still matches once and, if not, prints a new one.

### `/bench` and the hub

A player types `/bench` in match chat. It refuses in the first two minutes on
a map, then runs the same foliage bench at the player's own camera, prints
the result in their chat, and writes `bench_<id>.json` beside MJOLNIRHud,
named in the `match_outbox.txt` MJOLNIRLobby sends match records from:

```
Bench on DTI at 3840x2160: 64 fps (15.5 ms a frame).
Foliage costs 2.5 ms (16%): its shadows 0.5, its wind 1.3.
Sending it to the MJOLNIR team. Thanks!
```

MJOLNIRLobby posts it to `POST /api/v1/benches` with the launcher's key
(scope `lobbies:write`, as match reports), so any player signed in to the hub
through the launcher can send one. A hub that does not have the route yet
answers 404, which keeps the file for a later try. The hub stores the settings
line's fields with the sender's account (migrations/0021), and from MJOLNIRHud
0.11.0 the held camera and each condition's frame split (migrations/0022).
Only admins read them: the moderation page's **Benchmarks** tab
(`/moderation#benchmarks`) averages foliage runs by GPU, map, height drawn and
foliage quality, and lists recent runs with who sent each, which of game,
draw and GPU bound the frame, and where the camera stood; `GET /admin/benches` and
`GET /admin/benches/summary` serve the same data. A run taken in the first two
minutes on a map is kept but left out of the averages.

## What was measured (Death Island)

**At 3840x2160, Epic, by `mjolnir_bench`:**

| View | Base | No foliage | Foliage shadows | Foliage wind |
|---|---|---|---|---|
| Beach camera | 14.5 ms (69 fps) | -2.54 ms (-17.5%) | -0.58 ms | -1.28 ms |
| Island overview | 14.8 ms (68 fps) | -2.69 ms (-18.1%) | -0.25 ms | -1.29 ms |

A 5090 holds under 70 fps at 4K on Death Island. By the ratio of GPU
throughput, a mid-range card at 1440p should be well below 60 with the foliage
on; players' `/bench` runs are where that gets measured rather than estimated.

The tables below are from the 1710x1073 runs.

ABAB, 6 s windows, after warm-up. "Grass" in these tables is every instanced
mesh the loader scatters (grass, tufts, pebbles, shells, driftwood, tree
leaves); grass and tufts are about 97% of the 535,000 instances.

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

## Campaign against our maps (2026-10-18)

A player (RX 9060 XT, 2560x1440 at 58.8% screen percentage, Epic) reported
up to 240 fps in the campaign and about 51-58 fps on our maps, choppy. Their
`/bench` on Blood Gulch read 19.6 ms base, foliage 5.5 ms, of which wind was
5.2 ms. This section measures the campaign and both maps on PC 1 at one
set of settings, to see where that gap comes from.

**Settings, every run:** 1710x1073 borderless (Remote Desktop's display;
the bench camera letterboxes it to 1710x962, see below), every `sg.*` at 3
(Epic), `r.ScreenPercentage` 100, vsync off, no fps limit, MJOLNIRHud
0.11.0 (stat unit split from `mjolnir_frame_times.dll`). The game's own
Frame Generation setting was on (`bFrameGeneration=True`), which does not
touch these numbers: the bench and `stat unit` read engine frame times, not
presented frames. Each map had more than 3 minutes to warm up first.

- **Campaign:** The Silent Cartographer (B30) at the user's checkpoint
  (Resume Solo Game), the beach beside the Warthog at (18930, -16518, 810).
- **Blood Gulch:** `mjolnir_auto host BGL slayer private`, the spawn view
  at (9313, 27259, 226), grass and a tree in view.
- **Death Island:** `mjolnir_auto host DTI slayer private`. The spawn is
  indoors, so a CameraActor was set as the view target at the beach test
  camera (2323, -13154, 2784), which the bench then holds.

### The table

From `bench.log` (each base is 4 alternated 6 s windows; the three bases per
map agree within 0.08 ms):

| | Campaign (B30) | Blood Gulch | Death Island |
|---|---|---|---|
| Base frame | 8.29-8.34 ms (120 fps) | 8.09-8.17 ms (123 fps) | 8.02-8.04 ms (124 fps) |
| Game / Draw / RHIT / GPU | 5.0 / 4.2 / **6.3** / 5.95 | **8.0** / 2.8 / 3.7 / 6.7 | **7.9** / 3.0 / 4.1 / 6.5 |
| Bound by | RHI thread | GPU (Game is waiting on it) | GPU |
| `r.ScreenPercentage 200` | 13.47 ms, GPU 11.65 | 12.87 ms, GPU 11.48 | 12.51 ms, GPU 10.99 |
| `r.ScreenPercentage 50` | 8.22 ms, GPU 4.31 | 6.86 ms, GPU 5.43 | 6.87 ms, GPU 5.38 |
| GPU: fixed + per megapixel | 3.8 ms + 1.19 ms/MP | 5.0 ms + 0.98 ms/MP | 5.0 ms + 0.91 ms/MP |
| GPU at the player's 1.27 MP | 5.3 ms | 6.3 ms | 6.2 ms |
| `stat unit` Draws / Prims | 964 / 123K | 859 / 278K | 1,090 / 501K |
| Hitches, 3 min standing | 2, worst 22 ms, no Lua | 1, 78 ms: LevelLoader footprints 70 ms | 2, worst 158 ms: LevelLoader pulses 150 ms |

The fixed and per-megapixel GPU figures are a straight line through the 50%
and 200% points (0.41 and 6.58 MP drawn); it predicts the 100% GPU time
within 0.2 ms on all three.

What this says:

- **At the same settings the campaign is not lighter.** On PC 1 the three
  run within 0.3 ms of each other, and at 200% our maps cost slightly less
  GPU time than the campaign's beach. B30 is held back by its RHI thread
  (6.3 ms), ours by the GPU.
- **Ours carry about 1.1 ms more GPU work that does not shrink with
  resolution** (5.4 against 4.3 ms at 50%). That is the foliage: removing it
  saves 1.40 ms on Blood Gulch and 1.56 ms on Death Island, mostly GPU
  (6.7 → 5.1 ms on BGL).
- **At the player's internal resolution our maps should cost about 17% more
  GPU time than the campaign, not 4 times.** On a card about 3x slower than
  a 5090 (their 19.6 ms against our 6.3 ms of GPU on BGL), B30's beach
  would read about 16-17 ms, roughly 60 fps of engine frames.
- **So the 240 fps is most likely presented frames, not engine frames.**
  58.8% is an upscaler's Balanced preset, and the game has a Frame Generation
  option (on, on this box). FSR frame generation doubles what an overlay
  counts; `/bench` counts engine frames. A lighter view (interiors) would add
  to it. This was not measured here: there is no presented-frame counter on
  PC 1, and the FSR path cannot run on an NVIDIA card. The DLSS one
  (`r.Streamline.DLSSG.Enable 1`) stays on in our maps.
- **The player's wind cost is out of proportion.** Wind is 0.95 of 1.4-1.6 ms
  of foliage here (about 60%) and was 5.2 of 5.5 ms (95%) in their run. If
  that repeats, world position offset on grass costs far more on their GPU
  (RDNA 4) than on ours. One run so far, so this is a lead.

### What costs what on our maps (PC 1, 1710x962)

| Rank | Cost | Saving when removed | How measured |
|---|---|---|---|
| 1 | Foliage (grass, tufts, leaves) | -1.40 ms BGL, -1.56 ms DTI (17-19%) | `mjolnir_bench` |
| | of which wind | -0.95 ms on both | same |
| | of which shadows | -0.53 ms BGL, -0.71 ms DTI | same |
| 2 | CE placed lights' shadows (DTI, outside a base, 6 lights at 12-37 m) | -0.75 ms all 20 shadows off; -0.25 ms at the engine's 25 m shadow distance instead of our 80 m | held camera, two bases 1 min apart; `mjolnir_bench r.LightMaxShadowDistanceScale 0.3125` |
| 3 | Fluid Flux coast (DTI beach) | at most -0.38 ms (GPU 6.48 → 6.16) | held camera, two bases 1 min apart, the sea not drawn at all, so an upper bound |

- The lights cost nothing at the beach, 90-190 m from any of them
  (`r.LightMaxShadowDistanceScale 0.3125` read +0.02 ms there): only views
  near a base pay.
- **Keep virtual shadow maps:** `r.Shadow.Virtual.Enable 0` read +3.04 ms
  (+37%) on Blood Gulch, as it did on Death Island (+1.76 ms).
- Rows 2 and 3 are two bases taken a minute apart with the light shadows or
  the Flux actors (domain, surface, wave) switched by Lua between them, not
  the bench's alternated turns; the baselines repeat within 0.1 ms, so the
  sign and size hold, the second decimal does not.

### Choppy: what the hitches show

Hitch counts come from `mjolnir_hitches reset` windows with nothing else
running. A bench makes its own hitches (a 200 ms frame each time it switches
a condition, on every map, the campaign included), so its minutes are left
out.

- **Standing still, the worst frames on our maps are our own Lua.** The
  campaign's worst in 3 minutes was 22 ms. Blood Gulch's one hitch was
  `LevelLoader footprints` at 70 ms and Death Island's worst was
  `LevelLoader pulses` at 150 ms. The same session's log also has
  `LevelLoader weather` at 53 ms and footprints at 82 and 91 ms. Across
  `hitches.log` (all sessions since the logger shipped), `Hud tick` reached
  95 ms. Most hitches name none of our loops, but every 50-150 ms frame in
  today's quiet windows does.
- **No first-sight stalls on a warm cache.** Two passes of a teleport tour
  over eight Death Island views (bases, the overview, both shores) read 15
  hitches, worst 26 ms, then 9, worst 27 ms. The same teleports hitched on
  both passes, so they are camera cuts, not new pipeline states. PC 1 has
  played these maps many times, so its driver shader cache is warm. A first
  run on a new PC, or after a driver update, is untested, so runtime PSO
  compiles of our cooked materials (chunks 983/990) are neither confirmed
  nor ruled out.

### Recommended fixes (none made in this session)

| Fix | Expected saving |
|---|---|
| Wind off at High/Epic on slower GPUs (by `gpuScore`, or per vendor if more AMD benches repeat the 95%) | 0.95 ms here (12%); about 5 ms of the player's 19.6 ms |
| Lua spike budgets: split `pulses`, `footprints`, `weather` and the Hud tick so no run takes more than a few ms | removes the 50-150 ms frames, the only large hitches standing still |
| A foliage density and cull pass on Epic | part of the remaining 0.45-0.6 ms of foliage outside wind; more on slower GPUs |
| Placed lights: `shadow_distance` back toward 2500-4000, or no shadows on small fill lights | 0.25-0.75 ms near bases |
| Flux coast: lower `res` or update rate | under 0.38 ms; last |

For the tools:

- **The bench camera letterboxes non-16:9 windows.** `lockView` spawns a
  CameraActor with `bConstrainAspectRatio` on, so on 1710x1073 every bench
  drew 1710x962. Comparisons on one PC hold; a 16:10 player's absolute
  numbers read about 10% light. Set the component's `bConstrainAspectRatio`
  to false.
- **Ask the player** whether Frame Generation is on, and what their overlay
  counts. A campaign-side bench players can run (`/bench` lives in match
  chat) would let the hub compare their campaign and our maps directly.
- **A cold-cache run** (a new PC, or after clearing the driver's shader
  cache) with `mjolnir_hitches` while walking, to settle the PSO question.

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
  GPU frame time on the overview. High and Epic are unchanged. It covers every
  foliage group, trees' leaf clusters included. At Medium, the beach bench now reads
  base 6.86 ms, no foliage -0.38 ms, no foliage wind +0.03 ms. The loader's
  `foliage:` log line says `still` when it applies.
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

- **Measure weaker PCs.** Every number above is from a 5090. `/bench` on
  PC 2, and from players, fills the Benchmarks tab with real hardware.
- **Pick the foliage tier from the GPU.** `sg.FoliageQuality` only helps
  players who open Video settings. `Saved/GpuBenchmark.json` has a `gpuScore`
  (2060 on the 5090), and every bench report carries it with the foliage
  cost. Once the Benchmarks tab holds a few cards, the loader can choose
  `keep` / `cull` / `still` from the score; picking thresholds before that
  would be a guess.
- **Fewer, cheaper clumps on Epic.** Death Island has 535,000. The `bands`
  and cull ranges (100–300 m for grass) were chosen for looks. A density or
  range pass, checked with `mjolnir_bench` and screenshots, is the biggest
  remaining lever.
- **Hitch summaries from players.** `/bench` covers the steady frame rate;
  the hitch log's per-map summary (median, p95, hitches) could go the same
  way, opt-in.
- Two leads the tools should catch: the user's own Blood Gulch session had
  bursts of 15–25 ms frames with no Lua in them, and ended in a GPU crash
  (device lost) after 39 minutes. Process memory read 13–16 GB in `stat
  unit` on Death Island.
