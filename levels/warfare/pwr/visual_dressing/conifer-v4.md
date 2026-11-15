# Mature native conifer candidate

The Visual5 woodland uses an assembled shipped `Tree_Pine` recipe:101 bark components and592 needle clusters,111,147 indexed triangles after removing one duplicate source face. Its102 classic component meshes are exported with all native UV channels and raw RGBA masks. This candidate replaces the previous dispersed sapling silhouette; the playable heightfield, roads and bases remain frozen.

The isolated output directory is `out/pwr/visual-v5/outcrops-v4/trees`. The accepted source model is `mature-pine-a.glb`,SHA256 `68bdcb09e0af2dc2030b50b543f45d28a7284264bd7ce188484759b320cdf405`. `native-attributes.receipt.json` independently compares every indexed UV/color signature to the source recipe:three bark UV channels,one needle UV channel,original RGBA bytes exact. Needle UV1/UV2 are padded channels after assembly. Blender's generic BYTE_COLOR import was avoided because its sRGB storage changed linear mask bytes; the MCP authoring script creates FLOAT_COLOR directly from original accessors.

The exporter must use the corrected native-clockwise winding build. Both the source and assembled normal checks are part of verification. The approved Blender image is an albedo/lighting approximation, not proof of the cooked native foliage material.

`recipes.json` is a copy of the baseline recipe library plus the exact `PWR_MaturePine_A` entry. The runtime mesh is `/Game/MJOLNIR/Scenery/PWR/SM_PWR_MaturePine_A`. Its measured bound minimum is−195.2270508cm and full height 3091.2410736 cm. **The soil datum is `root_z:0`, not the minimum bound.** Native geometry below the authored origin represents buried roots. The preserved `native-conifer-root-contact.png` demonstrates why minimum-bound placement is rejected; `native-conifer-root-datum-contact.png` shows the approved placement. Renderer and native collision use the same datum and uniform scale.

Material slots, in order:

1. `MI_Pine_Tree_Mat` → `/Game/Env/Bio/Tree/Pine/Tree_Windswept/Materials/MI_Pine_Tree_Mat_LOD0`.
2. `MI_Branch_Mat` → `/Game/Env/Bio/Tree/Pine/Tree_Windswept_A/Materials/MI_Branch_Mat_LOD0_TwoSided`.

`prepare_conifer_v4.py --cli out/pwr/toolchain-mesh-attrs-v2/mjolnir.exe --require-attributes --force` extracts the actual sources. Execute `preview_conifer_v4.py` through the configured Blender MCP, then run `verify_conifer_attributes_v4.py`. Export is limited to the active scene and selected complete tree; the validator rejects unrelated geometry/materials. Reassembly changes source hashes and requires a new measured recipe, trunk-cache receipt and cooked readback.

`forest_stands_v4.py` authors clearance-tested stand anchors only. `pcg_forest_stands_v4.py prepare --target 4500` produces the actual editor request, followed by `tools/ue/run_pwr_pcg.ps1 -Request out/pwr/visual-v5/outcrops-v4/trees/request.json`. Run `uv run levels/warfare/pwr/visual_dressing/pcg_forest_stands_v4.py export` only after both editor runs finish. The adapter preserves the engine-selected poses, compares deterministic repeats and enforces the reviewed4000–5000tree budget.

`finish_forest_stands_v4.py` preserves all 804 reviewed rock records and filters grass against the measured tree hull footprints. The default native-surface budget remains 800,000; this revision may explicitly use `--max-native-surfaces 1200000` following the approved accuracy tradeoff. The receipt records the actual projected count and chosen limit. Native compilation, complete-map appearance, movement and performance remain separate acceptance gates.

The exact custom pine alone is whitelisted for static HISM baking. Its real editor asset must exist before HISM creation; no stand-in is created at its path. Other custom paths remain rejected. Trunk collision requires the hash-bound measured original-trunk cache; crown branches sharing the bark material are not accepted as trunk collision.
