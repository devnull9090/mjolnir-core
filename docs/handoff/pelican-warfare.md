# Pelican Warfare WIP handoff

## Open this checkout

Use `C:/Users/will/.codex/worktrees/pelican-warfare/haloce` on **`codex/pelican-warfare-wip-43`**. The starting commit was `f5c06ca8` on `codex/pelican-warfare`. The checkout at `C:/haloce` is separate launcher work. All paths below are relative to the Pelican Warfare checkout.

Use this existing worktree for another cook. It holds the UE 5.5 editor project, the installed game content, the earlier sealed releases, and the Python environment used for the rehearsal. A fresh clone needs those local inputs. [Local asset paths and SHA-256 hashes](../../levels/warfare/pwr/handoff/local-assets.json)

For portable Blender editing, use the [authored bases and citadel](../../levels/warfare/pwr/handoff/bases-authored.blend) and [authored canopy and pack](../../levels/warfare/pwr/handoff/canopy-authored.blend). Both were reopened independently. The bases snapshot includes the vehicle halls, ramps, roof sockets, fins and authored atlas. The local full scene also contains stock corridor panels, pillars and later presentation or playtest polish. The local canopy scene adds the retail Spartan fit reference. Their exact locations and hashes are in the asset inventory above.

## Last playable build

The verified release is **`out/pwr/river-riparian/saturday.43/`**. The map is `pelican-warfare-0.1.0-playtest.43.mjolnir`, SHA-256 `c150968c5c0a689d0582f2c6279ad4951000fc5cfbc8d3c8763320d92687492f`. Pair it with the same folder’s `pelican-warfare-runtime-0.1.0-playtest.43.zip` for multiplayer, or the zip under `solo/` for a private rehearsal. The paired runtimes have the same filename and different contents. [Map receipt](../../out/pwr/river-riparian/saturday.43/receipt.json) · [Multiplayer pairing](../../out/pwr/river-riparian/saturday.43/developer-runtime-receipt.json) · [Solo pairing](../../out/pwr/river-riparian/saturday.43/solo/developer-runtime-receipt.json)

This checkpoint includes the native warfare rules, HUD and overview map, insertion and chute work, bases, terrain generation, roads, vegetation, Fluid Flux integration, editor tooling and tests present in this checkout. The latest end-to-end test was a **solo shoreline visual and performance rehearsal**. Two-client match readiness on this exact build is still open.

## What changed at the lake

Both shores now use 6,979 grass, rush and willow placements, including 240 downy willows. A two-tier spring feeds the Fluid Flux lake. The left bank has an undercut, 80 main roots, 325 forks, and 958 rounded stones. The raised shelf has native collision. All 72 changed collision faces were read back from the cooked BSP. The latest root mesh is reproducible from its authored source, SHA-256 `8fd4da2bcfe3136ddd718d2847157cd8ee8d321fb87ab25a8db9c0a53c3af9d9`.

The original `.39` and final `.43` were photographed at the same poses and settings. The 60 FPS-capped outlet test sampled 2,700 frames per build. GPU time went from 7.175 to 7.521 ms, p95 frame time was 18 ms in both runs and neither had a frame over 33 ms. Live game readbacks passed. The shared Steam installation and profile were restored and verified.

[Matched outlet](../../out/pwr/river-riparian/review-riparian-shore-43/outlet.jpg) · [Roots and cascade close-ups](../../out/pwr/river-riparian/review-riparian-shore-43/bank-and-spring.jpg) · [Cascade in motion](../../out/pwr/alpine-target/bench/riparian-shore-43/water/inlet.mp4) · [Performance results](../../out/pwr/river-riparian/review-riparian-shore-43/results.json)

## Where to resume

1. **Use the visual baseline before changing assets.** Compare the approved [target](../../.dream-loop/river-erosion/target.png), the [latest capture](../../.dream-loop/river-erosion/captures/round-10.png), and the [independent critique](../../.dream-loop/river-erosion/verdicts/round-10.json). The overall score was 3.9/10, against 2.6 for the original shoreline. The last two versions differed by only 0.1 in the final side-by-side review.
2. **For the next art pass, start with the water and light.** The foreground gravel still reads brown and dry from the wide camera. Try localized broken blue-grey reflections wrapping the three outlet boulders and a softer reflection under the cascade. The current `DetailWaveHeight=3` affects the entire upper river. Keep it as the control. On the left bank, soften the continuous dark line beneath the sod and vary the spacing of the exposed root groups. Check both the wide outlet and the low cutbank camera.
3. **For playtest readiness, run a dedicated two-client acceptance pass.** Use red and blue clients and check warmup, each Pelican, jump, chute, capture and respawn on both clients. Record the exact map and runtime hashes. Use the Halo MCP bridge and background captures. The owner requested no desktop, mouse or keyboard control. Restore and verify the shared Steam install after temporary rehearsal.

## Build and verification entry points

- Native mode and runtime live in `crates/blam-megalo/src/warfare.rs`, `native/lobby/` and `mods/MJOLNIRLevelLoader/`. The HUD and input live in `mods/MJOLNIRHud/`. Base authoring is under `levels/warfare/pwr/bases_v1/`, chute art under `levels/warfare/pwr/canopy/v2/` and terrain under `levels/warfare/pwr/terrain/`.
- Shore planners are `plan_cutbank_roots.py`, `plan_riparian_canopy.py` and `terrain/plan_spring_cascade.py` under `levels/warfare/pwr/`. Their Unreal authoring modules are under `unreal/MJOLNIRMaterials/Scripts/`. If changing a planner, run it explicitly with `out/pwr/headwater-lake/python/Scripts/python.exe` before building. The build reuses existing survey files.
- The isolated Unreal project is `out/pwr/river-riparian/editor/Meteorite/Meteorite.uproject`. For a new candidate, run `./levels/warfare/pwr/build_riparian_shore.ps1 -Version 44 -Step All` from the worktree root after the art changes. This applies the art, reopens the level, cooks Shipping and seals the paired map and runtimes. The packager uses sealed `.39` as its base. Preserve the existing `saturday.43` folder.
- For another authorized private capture on this machine, run `out/pwr/headwater-lake/python/Scripts/python.exe out/pwr/river-riparian/rehearse.py out/pwr/river-riparian/saturday.44 riparian-shore-44`. Use a new benchmark label each time. Then run `out/pwr/headwater-lake/python/Scripts/python.exe out/pwr/river-riparian/compare_live.py out/pwr/river-riparian/saturday.44 riparian-shore-44`. The reference and live evidence are under `out/pwr/alpine-target/bench/`. Check `water/verification.json`, `steam/restored.json` and `visual-profile-restored.json` for the new run.
- The [QA source inventory](../../levels/warfare/pwr/handoff/qa-source-paths.txt) lists the bridge, capture, timing, restoration, motion and comparison scripts committed at their original locations. A live rerun also uses the local frame sampler, earlier rehearsal map chunks and receipts, and Steam's registered game installation.
