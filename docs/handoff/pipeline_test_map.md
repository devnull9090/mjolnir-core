# Handoff: build a pipeline test map ("TST")

**Status (2026-10-21):** done; [pipeline_test_map.md](../pipeline_test_map.md) is the current
record. TST was built on `work/foliage-bake-a63bc3` itself and merged with PR #208 (0d20304c,
2026-10-20): its sources are in `levels/test/tst/` (built with the Halo Asset Blender
Development Toolset Release 425) and its entry, chunk 969, is in `ce_upgrade_maps.json`. The
tree-twig bug below got a recipe fix in 8a4da432, after which TST's three trees were found
clean. A new local map installs with `--stages install --local-install`, not plain
`--stages install`, and B30 loads through the campaign menu: on CU4 `mjolnir_mission` from the
main menu never starts the mission. The worktree, branch, open PR and free-chunk notes below are as of
2026-10-19; the brief is kept as written, apart from the rules line that named a private
account.

Paste everything below the line into the agent.

---

You are taking over one task on the MJOLNIR project: build a small, known-good
Halo CE map and take it through our CE-to-Unreal conversion pipeline, so the
pipeline can be tested against a map whose every feature we know. Think of it
as a unit test for the pipeline. Work on Windows 11, on the machine below,
with computer use where an app has no command line (Blender, Sapien,
Guerilla, the game).

## Before you start: confirm the plan with me

Ask me these in one message, then wait for my answers:

1. **Size and layout.** My default: a symmetric two-base map about 120 x 60 m
   (CE units: about 40 x 20). Red base at one end, blue at the other, open
   ground between, one hill or ridge, one cliff wall along a side. Is that
   right, or do you want something else?
2. **What it must contain.** My list is below ("The map"). Anything to add
   or drop?
3. **Game modes.** CTF and Slayer by default. Any others?
4. **The Blender add-on.** CE geometry is exported from Blender with the
   community "Halo Asset Blender Development Toolset" (it writes JMS for
   tool.exe). It is not installed here. May I download and install it? Give
   me the exact source URL and version first.
5. **Trees.** The pipeline swaps CE trees for the game's B30 trees (Maned
   Kuenovo). Should the map use one tree type in a few places, or several
   types?

## Where things are

- **Repository** (a git worktree of `devnull9090/mjolnir-core`):
  `C:\haloce\.claude\worktrees\remastered-maps-stutter-diagnosis-1a468e`
- **Branch to start from:** `work/foliage-bake-a63bc3` (open PR #208). It
  holds the latest pipeline, including the foliage bake and the tree
  recipes. Make your own branch from it: `work/pipeline-test-map`.
- **Halo CE editing kit (HEK, classic 2004):** `C:\haloce\hek`. It has
  `tool.exe`, `sapien.exe`, `guerilla.exe`, `tags\`, `data\`, `maps\`. Use
  `tags\levels\test\` and `data\levels\test\` for the new level. The kit
  ships no stock scenario or BSP tags; missing tags can be copied from the
  MCC kit at `C:\Program Files (x86)\Steam\steamapps\common\HCEEK\tags`.
- **Blender:** `C:\Program Files\Blender Foundation\Blender 5.1`.
- **Unreal Engine 5.5:** `C:\Program Files\Epic Games\UE_5.5`. Our project is
  `unreal\MJOLNIRMaterials` in the repository (`Meteorite.uproject`).
- **The game (Steam):**
  `C:\Program Files (x86)\Steam\steamapps\common\Halo Campaign Evolved`.
  Mods and the UE4SS log are under
  `Meteorite\Binaries\Win64\ue4ss\`.
- **Converted maps and work folders:** `C:\haloce\ce_conversions\` (the
  release conversions are in `release11\<CODE>`, the upgrade work in
  `upgrade\<CODE>`).

Read these first:

- `docs/ce_map_conversion.md`: how a CE map becomes a game map.
- `docs/ce_terrain_collision.md`: the collision the game simulates.
- `docs/level_format.md` and `docs/level_authoring.md`: the level file.
- `docs/performance.md`, section "Baked foliage (2026-10-18)": what the
  upgrade bakes into the world.
- `tools/level/convert_ce_map.sh` (its header lists every step) and
  `tools/level/upgrade_ce_map.py` (its header lists every stage).
- `tools/level/ce_upgrade_maps.json`: per-map settings for the upgrade.
- `tools/level/scenery_swap.py`: how CE trees and rocks are matched to game
  meshes (by the CE asset's path and kind).

## The pipeline, end to end

1. **Author the CE level.** Model the terrain in Blender and export it as
   JMS. In the HEK: `tool structure levels\test\tst tst`, then place
   everything in Sapien (spawns, flags, scenery, items), then
   `tool lightmaps levels\test\tst\tst tst 0 0.1` for a draft lightmap (or
   `1 0.01` for final), then `tool build-cache-file levels\test\tst\tst`.
   Notes from earlier use of this kit:
   - `ogg.dll`, `vorbis.dll` and `vorbisfile.dll` must sit beside tool.exe.
   - `maps\bitmaps.map`, `sounds.map` and `loc.map` must be in `maps\`. Move
     `bitmaps.map` aside while building, or the new lightmap does not ship.
2. **Convert:** with `HCE_PAKS` set to the game's
   `Meteorite\Content\Paks`, run
   `tools/level/convert_ce_map.sh C:\haloce\hek\maps\tst.map TST C:\haloce\ce_conversions\test\TST`.
   It needs the HalcyonRing exporter, `halo2ue-export`, which the script
   finds by its default path.
3. **Upgrade:** add a `TST` entry to `tools/level/ce_upgrade_maps.json`,
   modelled on Blood Gulch's (`BGL`) entry, with `bake_foliage: true`, a
   free landscape chunk number (the ten maps use 970-979; check what is
   free), its ground and cliff shaders, and water settings if it has water.
   Then run `python tools/level/upgrade_ce_map.py TST` with no `--stages`
   for every stage, and `--stages install` with the game closed.
4. **Play it:** start the game through Steam and press Enter at
   "PRESS ENTER TO START". Wait until `ue4ss\UE4SS.log` contains
   "MULTIPLAYER is on the main menu". Then, in the game's console (the ~
   key), run `mjolnir_auto host TST slayer private`.

## The map

Every feature exists to exercise one part of the pipeline. Keep it small.

- **Terrain:** one landscape-like ground with a CE ground shader (to the
  landscape stage it is grass or sand); a hill; a cliff wall (cliff
  tessellation and cladding rocks).
- **Red base and blue base:** small structures (BSP geometry, not
  scenery) at each end, each with a CTF flag spawn, team spawn points, and a
  weapon or two.
- **Trees:** two or three CE tree scenery pieces the swap turns into B30
  Kuenovo trees. Put one somewhere a player can stand right under it and
  look up.
- **Rocks:** two or three boulder scenery pieces (swapped rocks; bullets
  must stop on them).
- **Water:** a small pond or stream in the BSP with a CE water shader (Flux
  water, shallow edges).
- **A teleporter pair, a health pack, a vehicle** (the Warthog), if cheap.
- **Lights:** the sun from the sky, plus one placed light near a base.

## Pass criteria (what "the pipeline works" means)

Check each in game and report it with a screenshot or a log line.

1. The map loads by `mjolnir_auto host` and spawns the player; the loader's
   log reports the foliage baked and its load frame under 1 s.
2. Red and blue bases, flags and spawns work: CTF can be played.
3. **Trees look like B30's.** Stand under a swapped tree and look up: the
   twigs must join the limbs, with no bare stems standing off them. Then
   load B30 (`mjolnir_mission B30` from the main menu) and compare the same
   tree type from the same angle. This is the open bug: on Infinity, swapped
   trees still show bare twig stems between the leaves after every fix so
   far (see the last commits on the branch). A clean map with one tree is
   the place to settle it.
4. Bullets stop on the swapped rocks and tree trunks, at the near face.
5. Players collide with rocks, trunks and the cliff.
6. The water is Flux water, with no sheets on walls or cliffs.
7. Trees and grass hold still apart from a light flutter. Nothing thrashes
   or comes apart.

## Rules of this project (hard)

- Commit and push only as `devnull9090`. Open PRs against `main` from your
  branch. Never push to `main`.
- **No release tags and no hub publishes.** The owner tests in game first,
  every time.
- Never write the owner's private account name in commits, PRs, docs or
  changelogs (say "HalcyonRing").
- Never edit a script while it is running (a bash script re-reads itself as
  it runs).
- Never `rm -rf` a path built from shell variables.
- One Unreal editor or cook at a time on `unreal\MJOLNIRMaterials`, and never
  two conversions at once: they share the project.
- Close the game before any `--stages install`. After a crash, kill
  `CrashReportClient.exe` or Steam will not relaunch it.
- `mods/MJOLNIRLevelLoader/Scripts/main.lua` is at Lua's 200-local limit:
  add no top-level `local`, put new state in existing tables.
- Do not read properties of baked world actors (`MJDecor_*`, `MJClad_*`)
  from UE4SS Lua: it crashed the game twice. Reading the game's own B30
  components is fine.
- Use the whole CPU; do not throttle builds.

## What to hand back

- The branch and PR link, with the `.blend`, JMS and HEK data in the
  repository under `levels/test/tst/` (no build outputs), the TST entry in
  `ce_upgrade_maps.json`, and a short `docs/pipeline_test_map.md`: how to
  rebuild TST and what each feature tests.
- The pass-criteria results, with what failed and why if anything did.
- Anything in the pipeline you had to change, as separate commits with
  their reasons.
