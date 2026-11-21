# Direct master heightfield to Landscape

`tools/level/build_landscape.py --heightfield <manifest>` reads the verified
`pwr-heightfield-v1` contract through `tools/level/heightfield.py`. This is an
offline input builder; it does not launch Unreal or alter an installed map.
The regular scene glTF and materials spec remain required for material UVs,
texture bakes and identification of ground mesh slots that the Landscape hides.

The manifest fixes the physical terrain, independent of image dimensions:

```json
{
  "schema": "pwr-heightfield-v1",
  "coordinates": "authoring_metres_z_up",
  "origin_m": [-1000, -1000],
  "spacing_m": [1.9550342130987293, 1.9550342130987293],
  "dimensions": [1024, 1024],
  "row_order": "+y",
  "height": {
    "path": "master.r32",
    "encoding": "float32_raw_le",
    "offset_m": 0,
    "scale_m": 1,
    "sha256": "<SHA-256 of the immutable master.r32 bytes>"
  }
}
```

This example spans exactly 2,000 metres. Values decode as `offset_m + stored *
scale_m`; normalized exports need an explicit physical vertical scale. Origin
always means minimum X/Y, even when `row_order` is `-y`. The reader canonicalizes
rows to increasing Y. It validates dimensions, finite heights and file hashes;
it also supports the other encodings documented by its module and tests.
Do not infer height from reference-image brightness or silently normalize each
export's minimum and maximum. The approved visual references guide authored
geography; the exported physical field is the numerical source of truth.

## Geometry and alignment

The current editor builder uses a square grid of components, each with 63 quads.
Direct import requires square physical bounds. `--components 16` makes 1009²
vertices. Spacing is derived from the manifest's complete extent: a 2,000-metre
field uses approximately 198.4126984 cm quads; a 2,016-metre field uses 200 cm.
An explicitly supplied `--quad` must agree, otherwise the builder fails rather
than cropping or stretching the terrain. With no component count, it chooses
the nearest whole component count to the source resolution (1–64 per side).

Authoring coordinates become Unreal `[100*x, -100*y, 100*z]`, then `--offset`
adds centimetres. Consequently the output height image reverses canonical
authoring Y. Lift defaults to zero for direct fields and remains 8 cm for the
legacy mesh path. Use zero lift for shared terrain alignment.

Direct heights bypass the mesh workflow's settling, steep-step holes, overlap
holes and synthetic seabed. Large erosion features therefore survive even when
the CE mesh is coarser. `--sea`, `--zone` and `--min-z` cannot be combined with
`--heightfield`; changes to the physical ground belong in a revised master.
This path represents one continuous heightfield, not caves or overhangs. Separate
meshes can supply those structures. Lip/foot material masks use the master,
while the colour/lightmap material bakes still come from the CE scene.

Height encoding sets the actor's Z near the middle of the field and expands
Landscape Z scale when relief exceeds the usual approximately 512-metre range.
It reports the resulting vertical quantization and rejects clipping. It does
not replace an out-of-range sample with a clamped height.

## Pipeline use

From the worktree root, add a manifest to an upgrade map entry:

```json
{
  "heightfield": "levels/warfare/pwr/terrain/master.heightfield.json",
  "components": 16,
  "landscape_lift": 0
}
```

Remove a previous `quad` setting unless it exactly matches the new field extent.
The map's other upgrade options remain necessary. `stage_land` resolves the
manifest relative to the repository and fails before process launch if missing.
It forwards the file to the normal Landscape input build. Alternatively:

```powershell
python tools/level/build_landscape.py <scene.gltf> <materials.spec.json> <land-output> --shader <ground-shader> --name LPW --heightfield <master.heightfield.json> --components 16
```

The output remains compatible with the existing editor/cook path:
`landscape.json`, `heights.r16`, `holes.r8`, material bakes and edge masks.
No runtime heightfield reader or PCG plugin is required by these outputs.

## Evidence and limits

Both `landscape.json.heightfield` and `heightfield.receipt.json` record the
manifest/height/output hashes, source/output dimensions, physical bounds, axis
transform, offset/lift, vertical quantization and clipped sample count.
They also record:

- Master-versus-CE-mesh disagreement at Landscape vertices: coverage, maximum,
  95th percentile and RMS vertical error. This is diagnostic; the converted
  render mesh is not proof of the installed native collision mesh.
- Reconstruction error at every source grid vertex after resampling and R16
  encoding. Bilinear error and the larger error of both possible triangle
  diagonals are reported. This measures sampled detail loss, not a continuous
  surface bound or inspection of the cooked Landscape triangles.

Native collision parity remains explicitly **unmeasured** in this receipt.
An accepted map still needs the separate adaptive collision error report,
surface/budget validation, and live player/vehicle checks. Reproject trees,
grass, roads and bases against the accepted final master before rerunning PCG.
The previous flat-map PCG receipts do not validate a revised terrain field.

The offline regression suite covers axis/row orientation, offsets, exact bounds,
rejection of mismatched spacing, tall-relief quantization, detection of detail
lost between output vertices, retention of detailed ground over a flat proxy,
legacy mesh behaviour and upgrade config forwarding:

```powershell
python -m unittest discover -s tools/level -p test_build_landscape.py -v
python -m unittest discover -s tools/level -p test_upgrade_ce_map.py -v
```

## Water depths and shores on the runtime field

For PWR's river and lake at different elevations, the coarse CE core is not a
valid source of water depth. Set `FROZEN_HEIGHTFIELD` to the **decoded runtime
Landscape field**, not the original Gaea source, before `convert_ce_map.sh`:

```powershell
$env:FROZEN_HEIGHTFIELD = (Resolve-Path 'levels/warfare/pwr/terrain/runtime-v3/runtime-master.json').Path
```

The converter passes this through `build_terrain_meshes.py --heightfield` to
`refine_water_gltf.bake_shore`. Other maps without the option retain the existing
coastal bake. For a standalone refinement:

```powershell
python tools/level/refine_water_gltf.py <water.gltf> <water-dense.gltf> --heightfield <runtime-master.json> --shore-cell 2
```

Every water vertex receives `TEXCOORD_1 = [shore_distance_m, depth_m]`. Depth is
its own surface elevation minus `field.sample(x, -gltf_z)`, clamped to 0–50 m;
the runtime manifest selects the verified Landscape triangle interpolation.
There is no common sea elevation. The shoreline raster is the union of the
authored water triangles where the local water surface is above the terrain.
Dry island cells and the outside of the water footprint are both shore. An
exact Euclidean distance transform of those raster cells supplies distance,
bilinearly sampled at vertices and limited to 200 m. The default 2 m raster
is a discretized shoreline, not an exact vector contour or continuous error
bound. A dry/occluded water vertex has zero shore distance and depth.

glTF input must contain applied node transforms in pre-offset authoring metres
(`x, z, -y`); nonidentity node transforms, out-of-bounds vertices, changed
heightfield hashes, and malformed UV buffers fail before publishing. Later
mesh normalization/actor placement is unchanged. A `.shore.json` beside the
water glTF records source/output hashes, field hash, interpolation, grid size,
depth/shore ranges, and float32 depth precision.

The isolated actual PWR proof is in `out/pwr/water-heightfield-proof/`. All
54,950 vertices agree with the frozen runtime triangles to **0.000000477 m**;
all nonshore attributes remain unchanged. Of 9,563 vertices over less than
1 m of water, none now incorrectly reports depth above 3 m (previously 9,252)
or shore distance above 50 m (previously 8,202). Water elevations remain
55–150 m, and measured local depths are 0–9.396 m. The proof does not certify
live transparency, water collision, or swimming behavior. The explicit PWR
`Shelf=[0,40,5,0]` and `ShoreParams=[0,14,0.12,0]` keep the ocean material's
synthetic shelf and incoming beach waves off for this freshwater layout.

`out/pwr/water-heightfield-proof/rebuild_water.ps1` can apply that verified
proof to the matching conversion: it checks hashes, rewrites only the water
mesh, and repacks the existing map mesh container. It does not install files.
Future conversions should use the environment hook instead of this one-off
receipt-bound script.

```powershell
python -m unittest discover -s tools/level -p test_refine_water_heightfield.py -v
```
