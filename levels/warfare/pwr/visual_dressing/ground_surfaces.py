"""Give a PWR level.json the base game's A30 ground surfaces (detail plan step 1).

PWR builds carry the last release's pwr.level.json forward (docs/pwr_map_0.1.2.md, step 6),
so run this on it before packing. tools/level/build_landscape.py holds the same values for a
level generated from scratch.

usage: ground_surfaces.py <in level.json> <out level.json> [grass tint r,g,b,a]
Only landscape.pbr changes: surfaces bound by the loader at load, and the tints for them."""
import json
import sys

src, dst = sys.argv[1], sys.argv[2]
level = json.load(open(src, encoding="utf-8"))
pbr = level["landscape"]["pbr"]
S = pbr.setdefault("surfaces", {})

# Meadow: A30's wild grass and weeds (coloured, ORHG; the shader reads .r occlusion and
# clamps grass roughness to 0.92 itself, so ORHG vs OHRG only moves which channel it ignores).
S["GrassD"] = "Wild_Grass_and_Weeds_rm5krfp0/T_Wild_Grass_NSVT_D_A30"
S["GrassN"] = "Wild_Grass_and_Weeds_rm5krfp0/T_Wild_Grass_and_Weeds_rm5krfp0_NSVT_N"
S["GrassO"] = "Wild_Grass_and_Weeds_rm5krfp0/T_Wild_Grass_NSVT_ORHG"
# Tracks (Alpine.w > 1.5 branch): SandD stays packed earth; MidD is the stone in the wheel
# ruts and shoulders, A30's stones on soil in place of the default sandy gravel.
S["MidD"] = "Stones_on_Soil_rmsijrp0/T_Soil_Stone_NSVT_A30_D"
S["MidN"] = "Stones_on_Soil_rmsijrp0/T_Soil_Stone_NSVT_N"
S["MidO"] = "Stones_on_Soil_rmsijrp0/T_Soil_Stone_NSVT_ORHG"
# Gravel (SandB) stays the ground gravel: it also draws road shoulders and tracks, and
# Shoreline_Beach_Rocks there outlined every road in pale stone from the air (2026-11-23).

# The old grass was a desaturated texture painted green by the tint; A30's is already green.
pbr["grass_tint"] = [float(v) for v in sys.argv[3].split(",")] if len(sys.argv) > 3 else [1.0, 1.05, 0.9, 1.0]

json.dump(level, open(dst, "w", encoding="utf-8"), indent=1)
print("wrote", dst)
