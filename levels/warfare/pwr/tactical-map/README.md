# PWR tactical-map art

`overview.png` is a 2048 × 2048 north-up map of the actual PWR geography. Its bounds are exactly −1000 to +1000 authoring metres on both axes. It includes shaded heightfield relief, restrained 20 m contours, actual water and islands, all 34 graded 24 m road footprints, existing paving and structural footprints, and soft density from the 4,702 placed trees. It has no baked labels, grid, objectives or player markers.

The seven 128 × 128 icons are white RGBA masks for runtime team tint. All directional icons point up/north. Their silhouettes are schematic vehicle symbols. Alpha is antialiased; the RGB channels stay white even in transparent pixels.

## Coordinate contract

| Input | Horizontal U | Vertical V |
| --- | --- | --- |
| Authoring metres | `(x + 1000) / 2000` | `(1000 - y) / 2000` |
| Native CE units | `(3.048*x + 1000) / 2000` | `(1000 - 3.048*y) / 2000` |
| Unreal centimetres | `(X + 100000) / 200000` | `(Y + 100000) / 200000` |

Image top is authoring +Y / Unreal −Y; right is +X. Position a runtime marker at `UV * displayed_map_size`, relative to the displayed map's top-left corner. Raster pixel-centre coordinates are `UV * 2048 - 0.5`. Clip or indicate out-of-bounds contacts in the presenter; the map contains no invented outskirts. The five home/capture alignment checks are in `manifest.json`.

## Rebuild

From the repository root:

```powershell
uv run --python 3.12 --with-requirements tools/level/requirements-alpine.txt python levels/warfare/pwr/tactical-map/build.py
```

The repeatable render reads the repository's hash-checked runtime-v5 heightfield/masks and graded terrain geometry, plus this folder's frozen `geography.json`. It does not need the original transient dressing outputs. `prepare_geography.py` records how that snapshot was derived from the actual existing trees, paving and closed macro bodies; only rerun it when deliberately updating those source placements.

`manifest.json` records every image and render-input SHA-256. Previews and the same receipt are written to `out/pwr/tactical-map-v1`. The background's water colour is a cartographic shoreline-distance cue, not measured bathymetry. Sub-map-scale native facade/cladding details are omitted. No proposed V9 buildings or grass expansion is included.

The UE builder owns the package and chunk assignment. This art generator never calls UE, creates packages or changes installed content.
