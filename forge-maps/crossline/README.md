# Crossline 0.2

Crossline / **FRB** is a standalone **48 × 80 m** Red versus Blue arena for
two to eight players. Version 0.2 doubles the original arena's horizontal
dimensions while retaining its heights: bases and catwalks are 4.5 m above
the floor, and the continuous perimeter remains 9 m high. The sky stays open.

The separate **Foundry Wide 0.1.0** pack supplies 18 structural pieces with
twice Foundry's width and depth, keeping their original heights. Crossline
uses nine of those types for 182 structural placements. Its 96 perimeter
panels are now 8 × 1 × 3 m, stacked in three courses with overlapping corners.
Ramps have twice the run and the same rise, so the main approach is a 25%
slope. Side walkways and lower routes are broader, and doorway openings are
4 m wide with 2.5 m headroom.

The portal frames, flush pads and eight light pieces use **Foundry 0.2.0**
at their original sizes. Their positions move with the larger bases. Two
linked two-way teleporters connect those bases; approaching from inside the
arena leaves the destination facing back into play. Eight player starts,
weapons, grenade pickups and the Spartan's collision retain their original
sizes and heights. There are 204 simulation objects plus the weapon and
equipment placements. This update does not resize Forge Canvas or Roadworks.

## Play and edit

Choose **Crossline → Team Slayer** for Red versus Blue, **Slayer** for
individual play, or **Forge** to edit. The original Foundry palette remains
available alongside all 18 Foundry Wide pieces. Press **B** to switch between
Spartan and Monitor. Use **Left/Right** for categories and **Up/Down** for
pieces; **Insert** places, **V** grabs/drops, **Page Up/Down** changes held
distance, and **comma/period** rotates. **F5** saves, **F6** reloads and **F2**
restores the authored layout. See [Forge controls](../../docs/forge.md).

The map pins Foundry **0.2.0** and Foundry Wide **0.1.0**, plus its tested CE
runtime dependency. Compatible launcher support resolves those releases
before play. Existing 0.1 saved layouts belong to the original map/palette;
keep their `.mvar` and `.mvar.packs` files together. Exact identity checks
prevent silently rebinding an old layout to the wider assets.

Current archives are local development builds until published through the
Hub. Offline collision checks verify the continuous perimeter, open passages
and floor/ramp/base joins; they do not establish multiplayer behavior or
replace live traversal testing. The two-way teleporter channel remains
`alpha` in both bases. This map does not provide bot navigation.

## Rebuild

Generate only this map without touching the other map files:

```powershell
python forge-maps/generate.py --only crossline
```

Build Foundry and Foundry Wide, then create the original 48 × 80 m canvas:

```powershell
cargo run -p blam-sbsp --example forge_canvas -- `
  forge-packs/foundry/build/donors/Levels/Halo1/Solo/B40/_Generated_/BSP_03_1_Chasm_old.scenario_structure_bsp `
  forge-packs/foundry-wide/build/canvas/crossline.sbsp `
  --width-m 48 --depth-m 80 --extent-m 64
```

Use a Paks view containing the game, tested CE runtime and both exact built
packs. The builder selects map version 0.2.0 and this dedicated README:

```powershell
python tools/forge/build_maps.py --only crossline `
  --paks C:/path/to/combined-paks --runtime '^1.17.0'
```

It verifies the palettes, native container bytes, canvas dimensions and
dependency pins, then writes a new retained build directory without installing
anything into the game. Run `python -m unittest discover -s tools/forge -p
test_build_maps.py` for the map regressions.
