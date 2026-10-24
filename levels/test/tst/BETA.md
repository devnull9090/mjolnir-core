# TST Proving Ground — public beta

An original enclosed coastal arena, built as an editable MJOLNIR community map example.
Two bases face across grass, rocks and water. A full-length Forerunner wall adds a broad balcony,
walk-through teleporters, covered tower passages, and alternate routes. Both bases have ramps
with flat landings onto their roofs.

## Play

Install **TST Proving Ground** from the MJOLNIR hub/launcher, together with its CE runtime
dependency (**1.13.0 or newer compatible 1.x**). Use MJOLNIR multiplayer mods **0.32.0 or newer**.
Host map **TST** with **Slayer, Team Slayer, or Capture the Flag**. The intended starting point is
2–8 players, with 4v4 as the layout target. Balance and performance feedback are welcome.

This is a beta. Oddball and King of the Hill remain source experiments and are not included in
this release's supported mode list. The Blender material/lighting studies are design references;
the beta uses the published game's material pipeline and CE sky. Do not treat preview renders
as screenshots of the downloadable game map.

## Learn and build

- [Editable map source](https://github.com/devnull9090/mjolnir-core/tree/codex/tst-community-map/levels/test/tst)
- [Blender-to-hub walkthrough](https://github.com/devnull9090/mjolnir-core/blob/codex/tst-community-map/docs/custom_map_walkthrough.md)
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
