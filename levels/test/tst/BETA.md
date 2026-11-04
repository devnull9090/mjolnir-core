# TST Proving Ground — public beta

An original enclosed coastal arena, built as an editable MJOLNIR community map example.
Two bases face across grass, rocks and water. A full-length Forerunner wall adds a broad balcony,
walk-through teleporters, covered tower passages, and alternate routes. Both bases have ramps
with flat landings onto their roofs.

The facility beneath the balcony connects both entrances through enclosed halls.
Recessed green teleporters inside each entrance lead to the balcony and return
to separate indoor landings. Fitted team emblems, backed lights, cleaner metal
finishes, and revised interior lighting complete this art pass.

## Play

Install **TST Proving Ground** from the MJOLNIR hub/launcher, together with its CE runtime
dependency (**1.16.0 or newer compatible 1.x**). Update MJOLNIR multiplayer mods to
**0.41.0 or newer**, including LevelLoader **0.9.6**, before playing this revision.
Host map **TST** with **Slayer, Team Slayer, or Capture the Flag**. The intended starting point is
2–8 players, with 4v4 as the layout target. Balance and performance feedback are welcome.

This is a beta. Oddball and King of the Hill remain source experiments and are not included in
this release's supported mode list. Blender and the native game export share the twelve
architectural surface roles, albedo images, roughness maps, and UVs in `surfaces.json`.
Renderer lighting still differs; preview renders are not screenshots of the downloadable map.
The game uses the CE sky with revised shadow fill and thirty fixture-aligned
facility lights. Native rock layers, grass, and Fluid Flux water are retained.
The bot support and Forge palettes from the preceding release are carried forward;
bots do not use teleporters, so the balcony remains a player route.

## Learn and build

- [Editable map source](https://github.com/devnull9090/mjolnir-core/tree/main/levels/test/tst)
- [Blender-to-hub walkthrough](https://github.com/devnull9090/mjolnir-core/blob/main/docs/custom_map_walkthrough.md)
- [Source pull request](https://github.com/devnull9090/mjolnir-core/pull/213)

The source includes the Blender scene, geometry generators, JMS export, scenario, gameplay
placements, PCG surface permissions, native asset preview adapters, art provenance, and build
scripts. Installed game assets and extracted preview caches are external dependencies and are
not part of the source download. Repository code uses the repository license; stock game assets
retain their original terms.

For a release build, run `rebuild.ps1`, conversion, `prepare_runtime.py --release-beta`, and
`upgrade_ce_map.py TST --release-beta`. The two beta switches keep the advertised modes and sky
compatible with published player dependencies. Package the matching conversion and upgrade
outputs with `pack_local_map.py --sign`. Never package an older game build beside newer source
without identifying the difference.

To retain bot support, apply `tools/level/add_bots.py` to the fresh package before
the final signature. The bot pass rebuilds navigation and squads while preserving
render, lighting, water and gameplay placements. This release also applies main's
0.001-WU (about 3 mm) correction to the duplicate collision shell; its exact byte
change is recorded in the release proof.
