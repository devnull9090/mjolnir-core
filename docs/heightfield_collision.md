# Master heightfields and adaptive collision prototype

`tools/level/heightfield.py` is shared by terrain rendering and collision
research. A `pwr-heightfield-v1` manifest explicitly states metre-space origin,
spacing, dimensions, axis order, encoded-height scale/offset and SHA-256 hashes.
It never normalizes a terrain to its observed minimum/maximum. The origin is
always minimum X/Y; `row_order: "-y"` means the stored image starts at maximum Y
and is flipped when loaded. Decoded arrays always increase in authoring Y.

```json
{
  "schema": "pwr-heightfield-v1",
  "coordinates": "authoring_metres_z_up",
  "origin_m": [-1000, -1000],
  "spacing_m": [1.9550342130987293, 1.9550342130987293],
  "dimensions": [1024, 1024],
  "row_order": "+y",
  "height": {
    "path": "terrain.r32",
    "encoding": "float32_raw_le",
    "offset_m": 0,
    "scale_m": 400,
    "sha256": "replace-with-the-export-file-sha256"
  }
}
```

That example assumes a calibrated normalized R32 export. If the export stores
actual metres, use scale 1. Supported heights include 16-bit PNG/TIFF/raw LE and
float32 NPY/TIFF/raw LE. Eight-bit concept images cannot masquerade as 16-bit
terrain. Optional same-grid masks decode to `[0,1]`; `road`, `shore`, `flat` or
`bases` supply collision priorities. Metadata such as `water_level_m`, generator
settings and source receipts is preserved.

`load_heightfield(path)` returns `Heightfield`: `heights_m`, `origin_m`,
`spacing_m`, `dimensions`, `bounds_m`, `masks`, `metadata`, `manifest_sha256`,
`sample(x,y)`, `sample_mask(...)` and `resample_grid(dimensions)`. Sampling is
bilinear unless `surface_interpolation: "triangle_nw_se"` explicitly selects
the actual Unreal Landscape triangles in canonical +Y authoring space. Masks
remain bilinear. Sampling rejects out-of-bounds coordinates by default. Input hashes,
dimensions, finite values and explicit height calibration are checked.

## Adaptive research command

```powershell
python tools/level/adaptive_heightfield.py <final-master.json> `
  --out out/pwr/terrain-collision --terrain-budget 26000 `
  --reserve-surfaces 4000 --reserve-edges 10000 --refinement-iterations 5
```

The NumPy-only RTIN hierarchy pads edge samples to a `2^k+1` working grid at
the original spacing, then clips the mesh back to the original domain. It does
not stretch1024 samples into1025: that shifts sharp features before collision
approximation even begins. It uses shared edge decisions, then independently rasterizes
the resulting mesh at every original master vertex and cell centre. Measured
failures guide subsequent priority adjustments under the same triangle budget.
This follows the right-triangulated hierarchy concept described in
[Mapbox Martini](https://github.com/mapbox/martini); the implementation and
measurement code live in this repository.

Outputs are `collision-surface.npz` (`vertices_m`, `triangles`) and
`collision-report.json`. The latter includes region maxima/RMS/percentiles,
signed offsets, topology, reserved architectural surfaces, estimated closure
surfaces/edges, and native table headroom. Default measured targets are 0.50 m
ground, 0.15 m roads, 0.25 m shore and 0.10 m flat foundations. Budget changes
must preserve the native 32,767-surface and 65,534-edge limits after architecture
and the world enclosure. Reported reserves are estimates, not compiler counts.

`accuracy_and_mesh_budget_pass` is an explicit acceptance gate. A completed
research command can exit successfully while truthfully reporting a failed
accuracy target; consumers must inspect that gate. `runtime_ready` is always
false: this output is an open height surface, not a native collision package.
World closure, architecture intersections, packed BSP table validation, native
ray probes, vehicle handling and multiplayer remain separate requirements.

For bilinear source fields, sampled measurements do not establish a mathematical continuous error bound.
They include full original source resolution and cell centres, not only retained
mesh vertices. Rendering must use the same finalized master. Any road cut/fill
or proposed local visual adjustment creates a new master and must regenerate
dependent masks, placements and error reports.

## Dense static terrain

`--chunked --hierarchy-threshold 0.2 --cliff-error 2` measures dense terrain for
the existing standalone-static collision path. This requires an explicit
walkable mask. `--terrain-budget` is a total triangle cap, not a claim that the
whole terrain fits one 16-bit definition. The native compiler must validate
each actual piece and report its real surface ranges.

Uniform runtime NW–SE triangles require special care: RTIN alternates diagonal
directions, and a saddle may have zero midpoint residual while differing at its
cell centre. The builder forces implicated cells to leaves, then changes paired
unit-cell diagonals to match Unreal. The independent source-grid/centre audit
then covers the complete overlay of the axis/45-degree triangle meshes.

`export_terrain_collision.py` checks the accuracy and hash receipt and exports
Morton-ordered CE-world-unit triangles. It also writes an ordered NPZ and a
candidate seam receipt. Native splitting can take fewer than 8,192 surfaces
when tree tables grow, so candidate seams must not be presented as verified
compiled boundaries. `upgrade_ce_map.py` validates the exported master hash
before appending these surfaces to the foliage/architecture collision tail.

## Reproducible proof

```powershell
python -m unittest discover -s tools/level -p test_heightfield.py -v
python tools/level/probe_adaptive_heightfield.py --out out/pwr/terrain-prototype
```

The synthetic 2 km fixture is explicitly not PWR geography. It exercises curved
graded roads, a lake shore, rolling relief and a flat foundation. Its reports
demonstrate both attainable precision and insufficient-budget failures. A
flat plane remains two triangles with exact sampled height. The test suite also
checks Gaea-style raw calibration, axis direction, content tampering, source
format rejection and non-power-of-two source coverage.
