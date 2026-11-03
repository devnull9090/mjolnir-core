# Foundry Wide 0.2.0

Foundry Wide is a **38-piece construction kit** on a 4 m module, with 0.5 m placement increments and bottom-centre origins. Version 0.2 adds 20 pieces for larger rooms, glazed enclosures, broad ramps, junctions, doors and utility stations. All 18 original Wide pieces retain their exact geometry, collision, IDs and catalog order.

This is a separate `foundry-wide` pack. Original Foundry 0.2.0 remains unchanged, including its portals, teleporter pads and lights. Existing Roadworks and Blank Canvas dependencies retain their exact original assets. Maps must explicitly use the new `objects\mjolnir\forge\foundry-wide\<id>` tags to select the wide pieces; installing this pack does not resize existing maps.

## Original 18 pieces

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

These 18 pieces preserve the original Foundry structural pieces' heights, collision topology and material assignments; their X/Y source coordinates are doubled. Bevels remain cosmetic, with the original small bevel widths; collision keeps exact flat abutting faces. Ramps meet 2 m block tops without a vertical lip. The native model draw distance is authored as a finite 200 m for all Wide pieces.

## New construction and utility pieces

| Piece ID | Dimensions | Use |
| --- | --- | --- |
| `glass_wall` | 8 × 1 × 3 | Framed 7 × 2.5 m glass pane |
| `window_glazed` | 8 × 1 × 3 | Original window frame with a 4 × 1.5 m glass pane |
| `doorway_tall` | 8 × 1 × 4 | Threshold-free **4 × 3.5 m** opening |
| `doorway_vehicle` | 12 × 1 × 6 | Threshold-free **8 × 5.5 m** opening |
| `ramp_wide` | 8 × 8 × 2 | 8 m-wide, 1:4 slope |
| `ramp_high` | 4 × 16 × 4 | 4 m rise, 1:4 slope |
| `ramp_wide_high` | 8 × 16 × 4 | 8 m-wide, 4 m rise, 1:4 slope |
| `ramp_wide_shallow` | 8 × 16 × 2 | 8 m-wide, gentle 1:8 slope |
| `landing_guarded` | 8 × 8 × 2 | 0.5 m deck, 1.5 m side rails; 7 m clear mouths at ±Y |
| `bridge_t` | 12 × 12 × 0.5 | Three 4 m-wide paths; mouth centres **(−6, 4), (6, 4), (0, −6)** |
| `bridge_cross` | 12 × 12 × 0.5 | Four 4 m-wide paths; mouth centres **(±6, 0), (0, ±6)** |
| `bridge_corner_wide` | 16 × 16 × 0.5 | 8 m-wide L deck, open towards +X/+Y |
| `lift_station` | 8 × 8 × 1.5 | 0.5 m deck with four 1:4 walk-up ramps, corner housings and cyan centre inset |
| `teleporter_housing` | 8 × 1 × 4 | 4 × 3.5 m clear throat with a green visual field |
| `floor_4x4` | 16 × 16 × 0.5 | Large floor spanning four modules per side |
| `wall_long` | 16 × 1 × 3 | Long enclosure wall; stacks at 3 m intervals |
| `glass_corner` | 8 × 8 × 3 | L-shaped glazed wall on −X/−Y edges |
| `door_panel` | 4 × 0.5 × 3.5 | Separate infantry door leaf |
| `door_vehicle_panel` | 8 × 0.5 × 5.5 | Separate vehicle door leaf |
| `teleporter_pad_wide` | 4 × 4 × 0.5 | Solid pad with a green visual inset |

Glass panes are solid and non-breakable. The green teleporter fields have **no collision**; the housing and pad remain physical. Teleport travel uses separate paired gameplay markers. Put a pad's bottom 0.5 m below the adjoining finished floor to keep its top flush.

The two door panels are separate from their frames. Align their X/Z origins and place the panel **0.75 m toward the frame's local −Y side**, so the back of its 0.5 m-thick leaf meets the frame's front face. A 4 m infantry lift or 6 m vehicle lift clears the matching opening without moving the frame. Automatic door activation is supplied by the Forge runtime, separately from the geometry.

The lift station has a central 4 × 4 m flat deck at **Z = 0.5 m**. Four 4 m-wide ramps rise from ground level over a 2 m run, so players can walk on from any cardinal side without jumping. The corner housings remain 1.5 m tall inside the same 8 × 8 m footprint, and the centre has 8 m of unobstructed overhead space. The catalog's activation volume begins at Z = 0.45 m, overlapping the deck by 5 cm, and extends 3.5 m upward. It directs acceleration along local +Z while preserving horizontal steering; runtime validation and tuning are separate from collision validation. A landing at 4.5 m is 4 m above the station deck.

New ramps face uphill toward +Y and have exact zero-height noses. Place a 0.5 m landing slab at `ramp origin Z + rise − 0.5 m` to join its high end flush. Corner and junction pieces retain their empty quadrants; collision is a union of the visible solid parts, never a box enclosing an opening.

The separate original Foundry Portal Frame and Teleporter Pad can be placed alongside Wide structures. Their scale is unchanged, and their teleporter behavior still comes from separate gameplay markers. Foundry lights also retain their original size and intensity.

## Reproduce and check

From the repository root:

```powershell
python forge-packs/foundry-wide/generate.py
python forge-packs/foundry-wide/validate.py
& 'C:\Program Files\Blender Foundation\Blender 5.2\blender.exe' --background --factory-startup --python forge-packs/foundry-wide/build_blender.py -- --render
```

The generator reads the committed original [Foundry source](../foundry/source/geometry.json) and pins its canonical JSON SHA-256. The pin ignores newline formatting while detecting semantic source changes. Provenance and the exact `[2, 2, 1]` transform are recorded in [source/geometry.json](source/geometry.json). It never calls Foundry's source writer or rewrites the original pack.

The portable validator keeps the original 18-piece fingerprint and exact transform checks. It also checks every new closed convex hull, aggregate mesh, origin, dimension and glass/energy UV range. Actual triangle rays verify open door throats, solid panes, closed/open door leaves, ramp surfaces and landing seams, junction voids, full floor coverage, standing infantry/Warthog aperture clearance and lift headroom. It currently checks **92 collision hulls, 1,064 triangles, 766 legacy probes and 6,082 extension probes**. Native collision cooking, material appearance and in-game traversal are separate checks.

Blender reuses the original mesh/material helpers and adds explicit planar UVs for new glass and green fields. It exports full-size metre glTF + BIN and GLB visuals, plus metre/Z-up collision JSON/OBJ, before applying any presentation transform. `build/foundry-wide.blend`, exports and the contact sheet are reproducible local artifacts under ignored `build/`. Every contact-sheet piece uses the same 0.38 presentation scale; the exported assets remain full size. The sheet shows Blender's glass/energy material preview; native material appearance must be checked in the game.

## Native glass and portal surfaces

The solid cyan panes use a two-sided, lit translucent material with opacity 0.24, roughness 0.12 and specular 0.7. The green field reuses Halo CE's `levels\test\tutorial\shaders\example_tutorial_teleporter`: its four-stage `shader_transparent_chicago` graph, two dust stages and two mask stages. The exact scalar/vector parameters and original texture names are recorded in [material_profiles.json](../../mods/MJOLNIRForge/Scripts/material_profiles.json). Map-specific TST fog is omitted. Animation uses the material's GPU time; Forge does not advance texture coordinates from Lua.

Materials and textures are cooked under `/Game/MJOLNIR/Forge/<pack-id>/`, and the archive includes its own shader library and texture containers. It has no TST map dependency. The bounded `surfaces` metadata selects a known profile and material slot; the runtime creates an instance once when a bound actor becomes active and reassigns it after pooling or map travel. It does not retain Blueprint/world wrappers across polls or load classes while polling. Ordinary pieces keep the existing seven-material build path.

After exporting the models and cooking collision/physics as described in [Forge packs](../../docs/forge_packs.md), build the material container before `build_pack.py`:

```powershell
# Supply the two locally converted CE DDS files. Chunk 967 must be unused
# by another installed shader library; retain that number in its filename.
python tools/forge/build_materials.py forge-packs/foundry-wide --ce-textures <local-CE-staging/textures> --chunk 967 --cook
python tools/forge/build_pack.py forge-packs/foundry-wide --paks <local-base-and-runtime-paks>
python -m unittest discover -s tools/forge -p test_build_materials.py
lua tools/tests/test_forge_materials.lua
```

`build/materials/materials.spec.json` records the full profile and input texture hashes; `receipt.json` fingerprints the cooked container triple. The pack build rejects missing, modified, mismatched or stale material receipts. The reference dust DDS SHA-256 is `087075684f5f8793ccc68df8f9032f8e493fffa51f32a008225875636009704d`; the mask is `84a9e25d316c8707f275b92aa9c1492cdc2a35cb3fafe9bded658fca844bcd31`. These are local build inputs, not files checked into this repository.

Original geometry and scripts are MIT-licensed. No proprietary model geometry or textures are included in these authoring sources. The built archive includes the locally converted CE portal textures; its other surfaces use the shipped native material mappings. The concept image is design artwork and the contact sheet is a Blender preview, not an in-game screenshot. Cold-load tests verified transparent glass with collision from both sides and animated green fields. Moving, pooling and restoring those surface placements remain separate live checks; see the [validation record](../../docs/forge_pack_validation.md).
