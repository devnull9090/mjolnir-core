# PWR v5 collision and probe refresh

Run from the repository root in PowerShell. This path keeps the accepted runtime
heightfield, layout3/protocol20569, 135,836 terrain triangles, 3,776 architecture
triangles and 4,560 base-detail triangles fixed. Foliage/rock hull changes can
alter the actual compiled piece boundaries even when terrain bytes are unchanged.
The previous v5 live proof is `out/pwr/world-v5/native-acceptance-v5.json`.

1. Finish the new authored decor and corresponding render input. Keep the
   retained pine transforms and frozen native gameplay contract intact. Filtered
   trees must carry accurate selection counts and pass `pcg_tree_decor.py`.
   Pin the
   reviewed CLI, then regenerate scenery collision through the existing pipeline:

   ```powershell
   $env:MJOLNIR = (Resolve-Path 'out/pwr/toolchain-v3/mjolnir.exe').Path
   python levels/warfare/pwr/upgrade.py --config levels/warfare/pwr/upgrade-v5.json --work C:/haloce/ce_conversions/warfare/PWR/expansion/world-v5/upgrade --stages foliage,swap,collision
   ```

   Require successful completion and a fresh
   `world-v5/upgrade/PWR/native-collision-receipt.json`. The compiler's actual
   piece counts/source ranges are authoritative; do not reuse candidate batch
   boundaries or manually copy the previous probe hashes. No terrain extra is
   appended outside that pipeline, which already merges the 8,336 fixed trailing
   architecture/detail surfaces exactly once.

2. Refresh against the actual compiled binary. Pick a **new** evidence directory
   for each revision (the example uses `rocks-r2`). The runner validates all
   ordered terrain triangles, produces 12 probes including four actual seams,
   patches a staged level twice to check idempotence, runs the full frozen
   native contract, checks the 550 m flights/static envelope and input hashes,
   and only then atomically replaces isolated `converted/pwr.level.json`.

   ```powershell
   python levels/warfare/pwr/refresh_native_probes.py --out out/pwr/world-v5/visual4/native-refresh --vehicle-spawn-policy levels/warfare/pwr/vehicle-spawn-policy-v1.json --apply
   ```

   Omitting `--apply` verifies a staged copy without replacing the converted
   scenario. Never use an installed map directory as input. Inspect
   `refresh.receipt.json`, `native-contract.json`, `flight-envelope.json`, and
   `commands.log` in that new directory. Any failure stops before replacement.
   `pwr.level.before-probes.json` retains the previous converted metadata.

   The visual4 correction policy is mandatory for the reviewed eight Tank/Banshee
   origin-Z and four probe-volume-Z changes. Apply it to a separate proposal with
   `vehicle_spawn_policy.py patch` and publish only its verified twelve-value diff
   into the isolated converted scenario before refresh. The default comparator
   continues to reject those changes without the explicit sealed policy. All
   timers, vehicle XY/yaw, native DLL, layout, terrain and player supports remain
   unchanged. Any later `prepare_runtime.py` regeneration requires reapplying it.

3. Bake **after** the successful refresh. Complete required editor/cook stages
   for changed visuals first, then use the existing `bake,assemble` stages.
   Do not rerun `prepare_runtime.py` or restore an older level over the refreshed
   flags. If another tool changes native metadata, rerun the complete refresh.

   ```powershell
   python levels/warfare/pwr/upgrade.py --config levels/warfare/pwr/upgrade-v5.json --work C:/haloce/ce_conversions/warfare/PWR/expansion/world-v5/upgrade --stages bake,assemble
   ```

4. Back up/install the matching package separately with the game closed, then
   seal the actual installed files. These commands require explicit ownership
   of the private sole-player game bridge. Host uses the separately installed
   SoloPreview variant; there is no variant modification in the harnesses.

   ```powershell
   node native/lobby/smoke-warfare.mjs --host --keyboard --jump --respawn --capture-a --transports --screenshots --seconds=210 --out=out/pwr/world-v5/rocks-r2/loop-manual.jsonl
   node native/lobby/smoke-warfare-terrain.mjs --probe --walk --screenshots --plan=out/pwr/world-v5/rocks-r2/native-refresh/terrain-probe-plan.json --out=out/pwr/world-v5/rocks-r2/terrain-test.jsonl
   node native/lobby/smoke-warfare-vehicles.mjs --drive --screenshots --banshee-ascend --out=out/pwr/world-v5/rocks-r2/vehicle-test.jsonl
   ```

   Idle vehicles can recycle while another vehicle is being tested. Preserve a
   stopped run and inspect the missing vehicle's live inventory/health. Once it
   naturally respawns in the correct authored volume, an explicit
   `--vehicle=banshee` (or `hog`/`tank`) repeats that subset with the same guards.
   Never move the target, expand its volume or lower an occupancy/health gate
   solely to pass a test.

5. For a fresh automatic drop, return to the main menu through the existing
   private lobby command and run the observer with no jump flags:

   ```powershell
   node native/lobby/smoke-warfare.mjs --host --transports --screenshots --seconds=185 --out=out/pwr/world-v5/rocks-r2/loop-automatic.jsonl
   ```

   Require no jump/deploy requests, seated flight followed by exit at 54–56 s,
   automatic canopy, landing on the same alive unit, and aircraft counts 0/2/0.
   Seal the installed hashes again and record the exact plan/collision/log
   hashes. This is sampled local native acceptance, not remote multiplayer,
   frame-budget, Flux buoyancy or automatic next-round acceptance. Renderer-only
   changes retain native proof only while collision/layout/DLL hashes remain
   identical; renew the package seal and perform visual/FPS checks separately.
