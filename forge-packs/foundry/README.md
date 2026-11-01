# Foundry modular Forge pack

Original industrial construction geometry for MJOLNIR Forge. The kit has **18
pieces**, a **2 m module**, **0.5 m placement snap**, and concrete, gunmetal and
amber materials. It contains no extracted Halo models or textures. Source and
generated geometry are covered by the repository's MIT license.

## Rebuild

From the repository root, using normal Python and Blender 5.2 LTS:

```powershell
python forge-packs/foundry/generate.py
python forge-packs/foundry/validate.py
& 'C:\Program Files\Blender Foundation\Blender 5.2\blender.exe' `
  --background --factory-startup `
  --python forge-packs/foundry/build_blender.py -- --render
```

The first two commands need only the Python standard library. The Blender build
regenerates and validates sources before exporting. No Blender MCP, add-ons,
network services or texture downloads are required. Tested with Blender 5.2.3
LTS (`e13b728c6880`). Omit `--render` for a fast asset rebuild.

`catalog.json` is the authoring manifest input. Runtime installation additionally
requires cooked tag/visual content produced by the game's packaging pipeline;
these source GLBs are not themselves an installable game pack.

## Outputs

| Path | Purpose |
| --- | --- |
| `catalog.json` | Names, stable IDs, tag paths, categories, dimensions and snap |
| `source/geometry.json` | Authoritative portable mesh/collision data, in metres and Z-up |
| `build/models/*.glb` | One visual asset per piece, conventional glTF metres and Y-up |
| `build/models/*.gltf` + `*.bin` | Equivalent unpacked glTF for the native mesh cooker |
| `build/collision/*.json` | Collision vertices, triangle indices and separate convex hulls |
| `build/collision/*.obj` | Same collision in metres/Z-up, with a group per hull |
| `build/foundry.blend` | Editable mesh asset library and contact-sheet scene |
| `build/foundry-contact-sheet.png` | Actual Blender render of all 18 models |
| `art/foundry-contact-sheet.png` | Reviewed render copied into Git for the pack/PR preview |
| `build/export-report.json` | Blender version, file sizes and triangle counts |

Generated `build/` artifacts are ignored by Git. The small JSON geometry is
committed so collision conversion can run without Blender. `generate.py` is the
editable source; regenerate the JSON after changing it. The `.blend` places
objects on a presentation grid, while the exported GLBs keep each object's local
origin at zero. In Blender, asset drag/drop uses that local origin.

## Coordinate and collision contract

- Source coordinates are **metres**, right-handed **Z-up**. Blender is configured
  with a metre unit scale. The glTF exporter performs its normal Y-up conversion.
- All origins are at the centre of the bounding footprint, on the bottom plane.
  A 2 m cube therefore spans `[-1,-1,0]` through `[1,1,2]`.
- Ramp/stair low ends face `-Y`; high ends face `+Y`. Both ramps rise exactly 2 m.
- Dimensions describe collision bounds. Decorative bevels and material inserts
  stay inside those bounds; walkable faces and nominal docking planes align.
- Each `collision.hulls[]` entry is an independently closed, outward-wound,
  triangulated convex solid. `collision.vertices` and `collision.triangles` are
  the concatenated equivalent with triangle indices already offset.
- Composite objects contain multiple hulls. Preserve them when cooking: taking
  one bounding convex hull would seal the doorway/window or fill the L corner.
- Shared internal faces between abutting hulls may occur. Do not interpret a
  whole composite as one manifold shell; cook the separate hulls or union them.
- Door opening: 2 m wide × 2.5 m high. Window opening: 2 m wide, Z=1..2.5 m.
- Stairs have eight 0.25 m rises and 0.5 m treads. Their collision follows the
  visible stairs; the separate ramp pieces provide smooth alternatives.

`validate.py` checks finite coordinates, outward winding, nondegenerate triangles,
closed edges, convex hulls, dimensions, origins, empty apertures and ramp joins.
These authoring checks do not replace runtime collision and placement tests.

## Native collision and physics

The native collision builder creates exact triangle BSPs and MOPPs from these
sources. It seeds two distinct open leaves and links every two-sided face, then
checks short rays through every face and full-axis sweeps against the original
triangles. For this kit, 9,950 rays pass without a miss, phantom or displaced hit.

```powershell
# Paks and CLI paths are local developer installations. Extracted donors and
# cooked outputs are game-specific local build artifacts and stay under build/.
$paks = 'C:\Program Files (x86)\Steam\steamapps\common\Halo Campaign Evolved\Meteorite\Content\Paks'
$cli = 'target\debug\mjolnir.exe'
& $cli extract --paks $paks --group collision_model --filter crate_space_a `
  --shipped-only --verify --out forge-packs/foundry/build/donors
cargo run -p blam-sbsp --example forge_collision -- `
  forge-packs/foundry/source/geometry.json `
  forge-packs/foundry/build/donors/objects/props/covenant/crate_space_a/crate_space_a.collision_model `
  forge-packs/foundry/build/blam-collision
python tools/forge/build_collision.py forge-packs/foundry/source/geometry.json `
  forge-packs/foundry/build/blam-physics --mjolnir $cli --paks $paks `
  --payload-out forge-packs/foundry/build/blam-collision
```

The physics builder uses each source convex hull directly, with outward plane
equations and grouped four-vector data. Compound parts reference a list of
separate polyhedra, preserving all openings. Rigid bodies are fixed at node 0,
and Havok inflation radius is zero to preserve grid bounds. Metres become Blam
units by division by 3.048, without changing the source axes. The game handles
Blam-to-Unreal coordinate conversion. Both the cooked physics containers and
verified raw payloads are emitted without touching the installed game. Use
`--only block_1x1` for a single-part build or `--commands-only` to inspect edits.

See [design research](../../docs/forge_pack_design.md) for references and future sets.
