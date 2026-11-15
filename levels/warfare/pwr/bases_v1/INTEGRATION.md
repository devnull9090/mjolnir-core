# Bases in the PWR world

The offline world assembly combines the reviewed red, blue and green bases with the existing 2 km playable terrain and 8 km background apron. It is saved separately from the original base art scene and the installed game. It does not launch the game or Unreal.

Open `out/pwr/base-integration/pwr-world-bases-v1.blend` from this repository. The `Review | ...` cameras include each base, its surrounding connections, an overview and a top-down map.

## Placement

Authoring coordinates are metres, Z up. All bases face south, with zero yaw. Blue already contains the reviewed reflection and must not be reflected again.

| Base | World translation of local origin | Floor elevation |
| --- | --- | --- |
| Red | −590, −80, 107.74976349 | 107.94976349 m |
| Blue | 600, −80, 111.74544541 | 111.94544541 m |
| Green | 0, 690, 129.53493956 | 129.73493956 m |

The old podiums, hubs, wings and buttresses are removed from this assembly. New courts have real holes around the buildings so they cannot fill the recessed interior floor seams. Recessed foundation beds close exposed gaps below the model, and six separate backing slabs support the side-gallery tile joints without changing the sealed art meshes. Thresholds connect the main tunnels, side galleries and roof ramps to the courts. Vehicle bypasses remain on both sides. The southern approaches preserve existing infantry and vehicle support heights, including the lower Banshee bays.

The authoritative terrain remains `terrain/runtime-v5/runtime-master.json`, SHA256 `cfa587ac8c9bc565270c035ee3a281b8611c8197fb7c6c0833990b1b6c4ee45f`. The assembly uses all 1,018,081 samples and the same NW–SE triangle diagonal. Existing road geometry and waterbed data are immutable. Only the Blender road shading beneath new courts is trimmed.

The world uses the saved PCG placements: 4,702 interior trees and 1,072 rock/cliff instances, plus the existing 600 exterior conifers and 96 apron cliffs. Mesh data is shared among instances. No population is randomly regenerated for the preview. All four authoritative bridge decks are present, including the braid culvert. Sapling render origins follow the native loader's root-height correction.

## Offline verification

The assembled scene passes 8,019 half-metre route support samples, conservative vehicle-envelope air checks, and the rooftop cannon reservations. All 85 added court, threshold, foundation and backing surfaces are closed triangulated meshes. The numeric plan preserves 33 spawn/vehicle support positions. Per-base evaluated mesh, vertex and triangle counts match the reviewed art exactly; maximum normalized bound error is 0.0077 mm. All 19 sealed art files and 41 protected runtime inputs remained unchanged.

## Build and inspect

1. Run `python levels/warfare/pwr/bases_v1/world_placement.py` to prepare and validate the surface/placement plan.
2. Run `python levels/warfare/pwr/bases_v1/integrate_contract.py` to verify the frozen runtime inputs and inventory the exact old structure ranges.
3. Through the existing Blender MCP connection, open `out/pwr/visual-v8/foothills/preview-clustered/foothills-v8.blend` and execute `integrate_world.py`. The script writes a separate world file and rejects an edited source scene.
4. Execute `validate_world.py` in the assembled scene, then `render_world.py` for actual Blender renders.

MCP requests and receipts, the source plan, assembly receipt, clearance report and renders are in `out/pwr/base-integration/`. The original reviewed asset package remains `forerunner_bases.blend`; its sealed source manifest is not changed by integration.

## Runtime boundary

This is an offline Blender world assembly. It is not an installed playable revision. Blender approximates Unreal terrain, rock and sapling materials; grass instances are omitted from this inspection scene. The water surfaces are inspection proxies, not Fluid Flux simulations. The existing Fluid Flux state/package is preserved. These renders are not evidence of engine performance or game behavior.

`runtime-handoff.json` inventories the future replacement precisely: remove 1,968 legacy base structure triangles and 4,560 base-detail triangles; preserve 135,836 terrain triangles and 1,808 bridge triangles. It also records the 69 obsolete visual decoration records. The existing native probe refresher hardcodes the old architecture counts and must be updated for a new collision contract. Do not append the new bases over those old hulls, and do not run `prepare_runtime` over the frozen expansion.

Native mesh/material conversion, replacement collision construction, cooking and gameplay testing remain separate work. The native spawn/capture/vehicle contract and installed runtime have not been changed. The rooftop cannon reservation remains available; the exact emitter is not installed.
