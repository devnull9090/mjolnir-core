# PWR terrain finalization

`levels/warfare/pwr/terrain/finalize_terrain.py` combines the immutable Gaea 2
export (`gaea-v2/source.json`) with the approved-reference XY trace
(`site-plan-v3.json`). It runs offline, without Blender, Unreal or game calls.
Its PEP 723 dependency declaration pins SciPy 1.17.0 and declares NumPy/Pillow;
`uv` supplies an isolated environment.

```powershell
uv run levels/warfare/pwr/terrain/finalize_terrain.py
uv run --with numpy --with scipy==1.17.0 --with pillow python -m unittest discover -s levels/warfare/pwr/terrain -p test_finalize_terrain.py -v
```

The finalizer preserves the original export. It writes a separate
`terrain/final-v3/final-master.json`, float32 height and mask arrays,
`terrain.geometry.json`, and `finalization.receipt.json`. Everything uses
authoring metres, Z up, with rows increasing in Y. The manifest includes source
and site-plan hashes; render, collision and PCG must identify the same final
height hash. This remains a candidate until the separate collision audit and
visual/gameplay reviews pass.

## Physical shaping

The image-derived Gaea field had high valley floors over the lake and extremely
steep narrow waterways. Simply fitting roads to those elevations produced
40–90 m bridge clearances, tall island mesas and sheer lake banks. The current
recipe grades a broad connected lowland before fitting individual roads:

- A gentle north-to-south floor and small rolling variation replace excessive
  lowland relief near the transport/drainage network. The operation feathers
  out with distance and elevation; tall eroded mountain flanks remain.
- The 34 roads use tangent circular fillets, preserving the exact named
  endpoints. A constrained elevation solve shares junction heights, locks
  foundation/apron connections, and accounts for the shorter inside lane on
  tight bends. Minimum fitted radius is approximately 25.57 m.
- Wide smooth earthworks form carriageways and shoulders. Merging arms share
  a plane wherever their widths overlap. Foundation planes feather into the
  surroundings rather than ending at a hard raster step.
- Water levels derive jointly from road crossings: three main bridges have
  20 m water clearance and the western crossing 16 m. The latter needs an
  elevated bridge/culvert structure, not a small drainage pipe. Channel voids
  remain open below all four decks.
- The main river descends from 150 m to the 55 m lake through flowing reaches
  and cascades. The western braid inherits its parent's level at the exact
  junction. A tributary bank cannot overwrite the parent channel bed.
- The lake floor is 48 m, with a broad 180 m shore transition and gentle
  nearshore target. Islands rise roughly 1–8 m above the water instead of
  restoring the source's tall island mesas.

The finalizer rejects road/profile disagreement over 5 cm, excessive lane
grades, too-tight turns, insufficient bridge clearance, uphill/blocked
watercourses, disconnected water levels and misplaced foundation centres.
It samples these against the exported float32 terrain, not an earlier solver
array. The regression suite reproduces the actual build in a temporary folder
and verifies exact height equality, as well as rejecting a floating road and
an uphill river.

## Geometry consumer contract

`terrain.geometry.json` has schema `pwr-terrain-geometry-v1`:

- `nodes`: original node IDs with `position_m: [x,y,z]`.
- `roads`: original road IDs and structural tags, `centreline_m` XYZ samples,
  `cross_section_offsets_m: [-18,-12,0,12,18]`, and `cross_sections_m` with five
  XYZ points per station. Ground-road cross-sections sample the final terrain;
  bridge sections describe the deck. `anchors` record plateau/junction station
  intervals and shared node IDs. Road geometry remains at its physical level;
  a cosmetic overlay may need a small render-only lift.
- `watercourses`: `surface_centreline_m`, channel widths, target depth and
  cascade position/drop/reach-length records. These are sloping water surfaces,
  not one global flat river mesh.
- `lakes`: irregular `polygon_m`, `water_z_m`, `floor_z_m` and island polygons.
  Lake surfaces must cut out island footprints.
- `sites`: `position_m` XYZ, `terrace_z_m`, original footprints and sizes.
  Captures and warmup share their corresponding terrace elevations.
- `crossings`: original route/water relationships and minimum freeboards.
  The associated road centreline supplies deck XYZ. Actual water levels and
  clearances are in the receipt's validation section.

The master supplies `road`, `water`, `shore`, `bases`, `flat`, `walkable` and
`forest` masks on the same grid. `flat` aliases exact foundation interiors.
Forest suitability excludes steep slopes, water, road shoulders and bases.
PCG still makes the deterministic selection and transforms; these masks only
define candidate suitability.

## Validation boundary

The receipt's maximum lane grade is about 8.263%, with zero-grade base aprons;
the maximum ground-road/profile disagreement is approximately 7 mm. These are
terrain-design checks, **not native collision parity**. The independent adaptive
collision build must measure its own error against this exact master, and the
cooked Landscape must report its resampling/quantization error. Large source
cliffs and the finite native surface budget require particular attention.

No installed map, gameplay route, native flight envelope or PCG output becomes
current merely because this file was generated. Those consumers must be rebuilt
from the accepted final field and tested after the visual/collision review.
