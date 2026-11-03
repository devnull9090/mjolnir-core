# Roadworks Circuit

A standalone Warthog driving map built from the original Roadworks modular
road kit and Foundry utility pieces. **Roadworks Circuit / RWC** uses a
320 × 320 m recovery deck, with the driving surface 3 m above it. The elevated
roads have their own collision; the floor below cannot conceal missing road
surfaces during testing.

Version 0.2.0 doubles the original circuit's horizontal dimensions. The closed
route is approximately 731 m in plan, with a 16 m clear lane, 24 m and 48 m
straights, 40 m centreline-radius curves, two 90° corners and two corners
assembled from pairs of 45° bends. The west side has a 24 m approach, a
gradual 48 m climb, a 24 m high deck at 7 m, and a 48 m descent. The rise stays
4 m: four-metre level noses and eight-metre transitions limit the grade to 12.5%.
The ramp ends are level, and every piece uses its authored connector position
and flow tangent. Roadworks guards protect the route; solid Foundry half-walls
close the pit junction and test pad perimeter.

A guarded 48 m spur connects the course to a 52.8 × 48 m test pad at the same
height. There are three stock Warthogs: one on the pad, and two side by side
on the flat approach before the climb, facing opposite directions. Their
centres are 8 m apart; the 3.25 m visual widths leave 4.75 m between vehicles
and 2.375 m to each outside guard. These are static clearances; steering and
passing still need playtesting. Player starts are beside the pit
vehicle, and a flush two-metre paint bar helps compare the real Spartan and
Warthog with the road. The stock Spartan standing collision is about 1.98 m
high; the Warthog's rendered envelope is about 6.13 × 3.25 × 2.43 m.

## Play

Choose **Roadworks Circuit → Slayer** to drive, or **Forge** to rearrange the
road pieces. This is a driving and construction test map; it does not include
race checkpoints, lap timing or bot navigation. The recovery floor catches a
vehicle that leaves the course. It is not a ramp back up to the elevated road;
restart the layout or use Forge to place another vehicle if needed.

The map requires **Roadworks 0.2.0**, **Foundry 0.2.0**, and the compatible CE
runtime listed in its manifest. Once published with compatible launcher
support, installing the map resolves those dependencies before play. Current
artifacts are local development builds. No public release is implied.

Foundry half-walls and lights, stock vehicles and player dimensions retain
their original sizes. The scale bar remains 2 m long. Earlier Roadworks 0.1
saved layouts require their matching map/pack release; their exact pack
bindings intentionally prevent applying them to this resized palette.

Forge controls and saved-layout bindings are described in the
[map guide](../README.md) and [Forge controls](../../docs/forge.md).

## Rebuild

Run `python forge-maps/generate_roadworks.py` to regenerate this map and its
connector-layout receipt. This generator does not rewrite Forge Canvas or
Crossline. Road dimensions and connectors come from
`forge-packs/roadworks/catalog.json`; the source models live beside that catalog.

Build the Foundry and Roadworks native packs, then generate the original
canvas collision using the locally extracted one-supernode donor:

```powershell
cargo run -p blam-sbsp --example forge_canvas -- `
  forge-packs/foundry/build/donors/Levels/Halo1/Solo/B40/_Generated_/BSP_03_1_Chasm_old.scenario_structure_bsp `
  forge-packs/roadworks/build/canvas/circuit.sbsp `
  --width-m 320 --depth-m 320 --extent-m 192
```

With a read-only Paks view containing the game, tested CE runtime and exact
containers from both built packs:

```powershell
python tools/forge/build_maps.py --only roadworks `
  --paks C:/path/to/combined-paks --runtime '^1.17.0'
```

The builder defaults Roadworks and Crossline to version 0.2.0; Forge Canvas
remains at 0.1.0. The default manifests are each pack's
`build/game/all/mjolnir.json`. Repeat
`--pack-manifest` to override them. The builder verifies every required
container pair, palette, version and canvas bound before baking, then checks
the map archive's pack dependency lines and vehicle listing. It creates a
fresh output folder and never installs into the game.

Run `python -m unittest discover -s tools/forge -p test_build_maps.py` for
collision-surface and connector-seam checks, including the reversed descent,
pit access, guards, vehicle spawn surfaces and dependency validation.
