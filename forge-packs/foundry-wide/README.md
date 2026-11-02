# Foundry Wide 0.1.0

Foundry Wide provides 18 structural pieces with **twice the original Foundry footprint and unchanged heights**. It uses a 4 m module, 0.5 m placement increments and bottom-centre origins. Wider paths and gentler ramps leave the player, cover and doorway headroom at their existing scale.

This is a separate `foundry-wide` pack. Original Foundry 0.2.0 remains unchanged, including its portals, teleporter pads and lights. Existing Roadworks and Blank Canvas dependencies retain their exact original assets. Maps must explicitly use the new `objects\mjolnir\forge\foundry-wide\<id>` tags to select the wide pieces; installing this pack does not resize existing maps.

## Piece guide

Dimensions are **X width × Y depth/run × Z height**, in metres. IDs stay familiar within the new pack namespace. Names in Forge begin with **Wide**.

| Piece ID | Dimensions | Use |
| --- | --- | --- |
| `block_1x1` | 4 × 4 × 2 | Raised foundation; same 2 m height |
| `block_1x2` | 4 × 8 × 2 | Long raised foundation |
| `floor_1x1` | 4 × 4 × 0.5 | Square floor |
| `floor_1x2` | 4 × 8 × 0.5 | Long floor |
| `floor_2x2` | 8 × 8 × 0.5 | Large square floor |
| `bridge_straight` | 4 × 8 × 0.5 | 4 m-wide bridge |
| `bridge_corner` | 8 × 8 × 0.5 | L-shaped deck; upper-right quadrant open |
| `ramp` | 4 × 8 × 2 | 1:4 rise/run; low end −Y |
| `ramp_shallow` | 4 × 16 × 2 | 1:8 rise/run; low end −Y |
| `wall` | 8 × 1 × 3 | Full wall; stack at 3 m intervals |
| `wall_half` | 8 × 1 × 1.5 | Solid half wall |
| `wall_corner` | 4 × 4 × 3 | L-shaped wall; opens towards +X/+Y |
| `doorway` | 8 × 1 × 3 | Clear opening **4 × 2.5 m** |
| `window` | 8 × 1 × 3 | Clear aperture **4 × 1.5 m**, sill at 1 m |
| `railing` | 8 × 0.5 × 1 | Open rail with separate collision bars |
| `column` | 2 × 2 × 4 | Support column |
| `cover` | 4 × 1.5 × 1 | Cover stays 1 m high |
| `stairs` | 4 × 8 × 2 | Eight 0.25 m rises; 1 m treads |

All heights, collision topology and material assignments are preserved from the original structural pieces. Only X/Y source coordinates double. Bevels remain cosmetic, with the original small bevel widths; collision keeps exact flat abutting faces. Ramps meet 2 m block tops without a vertical lip. The native model draw distance is authored as a finite 200 m.

The separate original Foundry Portal Frame and Teleporter Pad can be placed alongside Wide structures. Their scale is unchanged, and their teleporter behavior still comes from separate gameplay markers. Foundry lights also retain their original size and intensity.

## Reproduce and check

From the repository root:

```powershell
python forge-packs/foundry-wide/generate.py
python forge-packs/foundry-wide/validate.py
& 'C:\Program Files\Blender Foundation\Blender 5.2\blender.exe' --background --factory-startup --python forge-packs/foundry-wide/build_blender.py -- --render
```

The generator reads the committed original [Foundry source](../foundry/source/geometry.json) and pins its canonical JSON SHA-256. The pin ignores newline formatting while detecting semantic source changes. Provenance and the exact `[2, 2, 1]` transform are recorded in [source/geometry.json](source/geometry.json). It never calls Foundry's source writer or rewrites the original pack.

The portable validator checks all 18 pieces against the pinned source: exact coordinate transform, unchanged Z/topology, closed outward convex hulls, fourfold volume, aggregate collision meshes, bounds/origins, empty openings, ramp faces/seams and stair heights. It currently checks **35 collision hulls, 412 triangles and 766 opening/slope/step probes**. Native collision cooking and in-game traversal are separate checks.

Blender reuses the original mesh/material helpers. It exports full-size metre glTF + BIN and GLB visuals, plus metre/Z-up collision JSON/OBJ, before applying any presentation transform. `build/foundry-wide.blend`, exports and the contact sheet are reproducible local artifacts under ignored `build/`. Every contact-sheet piece uses the same 0.45 presentation scale; the exported assets remain full size.

Original geometry and scripts are MIT-licensed. No proprietary model geometry or textures are included in these authoring sources; the game build uses the existing native material mappings.
