PWR fractured banks and ridge shelves are an isolated authored assembly on the frozen runtime-v5 field. They do not change terrain, water, roads, layouts, or vehicle origins. The reviewed lake pilot is preserved in `lake-pilot-v3.json`; the rest uses deterministic seeded selection. This pass is not represented as an Unreal PCG run.

Visual4 was cooked, compiled and locally installed on 2026-11-09 with **804 rocks, 4,264 trees and 284,852 grass instances**. The gray world-space rock material compiled successfully. Actual installed appearance, refreshed movement checks and visual4 frame times remain pending; earlier visual3 acceptance does not certify this collision revision.

From the repository root, reproduce source assets and placements:

```powershell
uv run levels/warfare/pwr/visual_dressing/prepare_outcrops_v3_assets.py
uv run levels/warfare/pwr/visual_dressing/outcrops_v3.py
uv run levels/warfare/pwr/visual_dressing/outcrops_v3.py --region ridge
uv run levels/warfare/pwr/visual_dressing/finish_outcrops_v3.py
```

Outputs live under `out/pwr/visual-v5/outcrops-v3`. The merged decoration preserves all 574 prior rocks and adds 63 bank formations, 32 partially buried ridge shelves, and 135 small toe rocks. Gray material overrides use the native Jagged Rock textures through the dedicated world-space `M_CE_PWRRock` parent; the Blender previews use approximate neutral gray and do not prove the game material.

`trees.selected.json` retains 4,264 exact records: 32 roots are removed by the final paving-v3 footprint with a 0.75 m buffer, and three trunks intersect new rock. Harmless crown overhangs remain. `grass/foliage.json` retains 284,852 byte-exact transforms. Full source LOD0 vertices and sampled native hull faces are checked against dry-water, road, base and paving clearance; only buried geometry may overlap these protected regions. Coarse sampled clearance is not a continuous intersection theorem, so installed movement review remains required.

The retained tree recipes are 3,787 `Pine_Optimized` and 477 `Pine_Sapling_A`. Selection metadata records 4,264 survivors and preserves the original 4,299-tree PCG union as source lineage. The metadata correction changed no instance records and claims no new PCG execution. The actual `pcg_tree_decor.py` adapter passed with the current native recipes, merged authored decoration and `--max-trees 4600`; `tree-conversion.receipt.json` records this check. `finish_outcrops_v3.py` now writes the filtered counts automatically and `verify_outcrops_v3.py` invokes the actual adapter.

The additional native hull proof contains 136,544 triangles. Finite corresponding vertices move at most 0.276 mm through CE round4 and float32 storage; no serialized triangle degenerates. This does not claim exact infinite halfspace containment or Havok acceptance. The conservative total before removed tree hulls is 737,737 surfaces under the 800,000 configured ceiling.

The completed integrated native compile contains **734,761 surfaces**, including nine core surfaces. Its receipt is `C:/haloce/ce_conversions/warfare/PWR/expansion/world-v5/upgrade/PWR/native-collision-receipt.json`, SHA256 `5a048eb32688f400bdae115b5ed5eef548a58f7cdb895564c8f51c7c60c0be7c`; output SBSP SHA256 is `bddc3c71652a7fbe9ed5eaf0fb1cdcd9454f12f3ec6bb30563a1f9ed567a79b9`. Compilation passed; live contact and movement acceptance remain separate.

Generate the independent canonical collision proof (do not append it separately if the ordinary authored-decoration path already generates these hulls):

```powershell
'{}' | Set-Content -Encoding utf8 out/pwr/visual-v5/outcrops-v3/empty-level.json
python tools/level/b30_collision.py out/pwr/visual-v5/outcrops-v3/empty-level.json out/pwr/visual-v5/outcrops-v3/unused.bin out/pwr/visual-v5/outcrops-v3/outcrops.authored-decor.json out/pwr/visual-v5/outcrops-v3/native-hulls.proof.json --hulls out/pwr/visual-v5/outcrops-v3/hulls --only swap
uv run --with scipy --with shapely --with pillow python levels/warfare/pwr/visual_dressing/test_outcrops_v3.py
```

The actual Blender MCP preview executes `preview_outcrops_v3.py` with `PWR_FULL=True` through `tools/blender/mcp_client.py execute_blender_code`; it saves an isolated scene and the four `combined-*.png` views. After that preview, `uv run levels/warfare/pwr/visual_dressing/verify_outcrops_v3.py` checks current preview provenance, every native proof triangle, unchanged prior rocks, retained tree records, stable grass byte subsequences, and the actual tree adapter, then writes `seal.json`. Three focused regressions pass. The seal retains the status at source handoff; its pending compilation/live field is historical and is not mutated after downstream compilation.

Final source seal SHA256 is `0d87c7d21088110b60a185369a541ddd1b0f64fb41304083e86e7faad8c0f98d`. Its immutable input hashes include:

| Artifact under `out/pwr/visual-v5/outcrops-v3/` | SHA256 |
| --- | --- |
| `rocks-and-outcrops.authored-decor.json` | `338963ec64c3b3517fe615ef9a01bd29ecbb29ea7b551bb3e9b70561f62d20e3` |
| `trees.selected.json` | `e62be15594fab14a4df005da31fabf8d65cf47f5c6545b870c06e82abd2a6665` |
| `grass/foliage.bin` | `e719c1fe1ca0911e808c3a3e0fbf94a30d2845a3ce8e9bd4c98ab7eea0b71bb2` |
| `receipt.json` | `506c6ec5796c52da197b921155ddce0f9fa76c1adb2d24703be1ceffe3435fa7` |

Fresh compiled probes, installed appearance, gameplay and frame-time acceptance must bind to this installed revision. Blender previews and earlier native receipts do not supply that acceptance.
