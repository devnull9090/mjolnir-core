# PWR terrain refinement source

## Current v5 source

The current candidate is `pwr_world_native_v5c.terrain`: native Gaea Alpine
landforms, foothills and two Erosion2 passes, with no image-luminance input.
Its real Gaea 2.3.1 Community UI build succeeded at 1024². Recreate the graph,
build it in Gaea's UI, then import the verified output:

```powershell
python levels/warfare/pwr/terrain/build_gaea_v5.py --variant v5c --southeast-x 1.16 --peripheral-shoulders
# Open pwr_world_native_v5c.terrain in Gaea and build to out/pwr/gaea-world-v5c.
uv run --with numpy python levels/warfare/pwr/terrain/import_gaea_v5.py --variant v5c --datum 70 --height-range 400
```

`gaea-v5c/source.json` preserves graph, raw output and report hashes. Calibration
is 70 m + normalized R32 × 400 m, with north-first rows flipped to canonical +Y;
the raw source spans 70.641–383.597 m. The approved concept images remain visual
direction, not final elevation samples. `final-v5` constrains this source around
the immutable v3 gameplay surfaces, then `runtime-v5` retains the exact 1009²
Unreal R16 grid and triangle diagonal. Use `docs/pwr_terrain_preservation.md`
for the finalizer/derivation commands and gates. Never run the legacy finalizer
over these directories or refit the fixed vertical encoding.

The final runtime manifest is
`cfa587ac8c9bc565270c035ee3a281b8611c8197fb7c6c0833990b1b6c4ee45f`.
Its offline preservation and collision checks pass. The local candidate is
installed with backups and its native traversal/insertion suite passed. Actual
game visual acceptance and FPS remain pending; new scenery collision requires
fresh probes even though the terrain field remains unchanged.
Keep `gaea-v5`, `gaea-v5b`
and their rejected fits as diagnostics; `final-v3`/`runtime-v3` remain rollback.

## Historical image-derived v3 source

`pwr_world_refined.terrain` is the preserved v3 Gaea project. Its input is
`world-height-seed-v2.png`, derived from the approved world reference described
in `world-reference-v1.json`. The older `terrain-seed-v1.png` is experimental
and does not define the accepted map layout.

The graph uses the official Gaea2Houdini SimpleErosion project structure:
File, a small native Blur modifier, Erosion2, and four exports for height,
flow, wear and deposits. Dimensions are 2000 m square with a 400 m height range;
the Standard build is 1024 square. The modest erosion settings are an initial
art direction choice and require inspection of the resulting terrain.

Open and build in Gaea's UI. The source retains the observed `GaeaRaw` format
enum. In the UI, change height and data exports to Float Raw32 and matching
`.r32` paths, or choose 16-bit PNG. The intended output directory is
`out/pwr/gaea-world-v2` under this checkout. UI export and height calibration
must succeed before the output becomes collision or rendering input.

The external heightfield manifest must record actual output encoding, size,
orientation, hash, offset and scale. For calibrated normalized R32, metres are
`offset_m + sample * scale_m`; a project height of 400 m is the intended scale,
not proof of an exported file's range or orientation. Do not infer the scale
only from its extrema. Flight routes, homes and capture sites must be validated
against the final heightfield and updated in the shared layout separately.

`make_gaea_project.py` reproduces the initial project and checks its graph links
and serialization references. Running it replaces the project; preserve any
subsequent UI-authored adjustments before regenerating. It never runs Gaea or
uses a paid automation feature.

The source template and its license are retained in `reference/`. Template:
[QuadSpinner Gaea2Houdini SimpleErosion](https://github.com/QuadSpinner/Gaea2Houdini/blob/main/src/misc/gaea/SimpleErosion.terrain).
The Blur modifier schema was inspected in Gaea 2.3.1's bundled
`Structure - Side Carved Mountains.terrain` example. Erosion property names and
ranges were inspected in the bundled examples and the source template.

Required visible game/map credit under the included template license:
**Terrains powered by QuadSpinner Gaea.**
