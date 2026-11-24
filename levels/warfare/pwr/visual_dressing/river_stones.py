"""River stones: real stone meshes along every lake and river bank, where the shore band draws cobble.

The landscape shader's shore band (unreal/MJOLNIRMaterials/Scripts/apply_pwr_shore_band.py) paints
cobble from the map's shore mask (tools/level/shore_mask.py), but a photo on the ground reads flat.
This scatters the base game's scanned river stones over the same band: many small cobbles at the
water's edge thinning up the bank, and a few larger stones with shadows. They bake into the level as
static instances (the meadow-life route: build_sweep_banks.pack_groups -> apply_pwr_river_stones.py
-> MjolnirUIBuilderLibrary.bake_foliage), so nothing runs at load.

They have no collision: the largest is under half a metre across and they sit a third sunk.

  python river_stones.py LEVEL.json SHORE_MASK.png TERRAIN_DIR OUT_DIR [--seed 53]

Everything comes from the mask and the terrain, so any map with a baked shore mask gets the same.
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np
import shapely
from scipy import ndimage
from scipy.spatial.transform import Rotation

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import check_structure_clearance as structures  # noqa: E402
from build_sweep_banks import pack_groups  # noqa: E402
from riparian_swaps import Grid  # noqa: E402

sys.path.insert(0, str(HERE.parents[3] / "tools/level"))
from foliage_bake import PAKS, mesh_info  # noqa: E402

OWNER = "PWR_RiverStones"
RS, MA = "/Game/Env/Bio/Rock/River/Rock_River_Stone_01/", "/Game/Megascans/3D_Assets/"


def m(path):
    return path + "." + path.rsplit("/", 1)[-1]


# kind -> meshes (each in one group only), cull cm, flags (2 static + 32 exact, +1 shadow),
# scale range, stones per square metre at the water's edge, half-density distance up the bank (m).
KINDS = {
    "cobble": ([m(RS + "SM_Rock_River_Stone_01_C"), m(RS + "SM_Rock_River_Stone_01_E"),
                m(RS + "SM_Rock_River_Stone_01_G")],
               (9000, 11000), 34, (1.0, 2.1), 3.2, 1.4),
    # Not the Megascans Nordic_Beach_Rock_vgjidiqmw scan: it draws black in game, as
    # Nordic_Beach_Rocky_Ground_ukohbbi did.
    "stone": ([m(RS + "SM_Rock_River_Stone_01_I"),
               m(MA + "Nordic_Beach_Rock_vbumba2fa/SM_Nordic_Beach_Rock_vbumba2fa")],
              (10000, 12000), 35, (1.4, 2.8), 0.30, 2.2),
}
BANK_M = (-1.2, 6.0)     # metres from the water's edge (negative = under water)
LEVEL_M = (-0.30, 2.6)   # metres above the nearest water: shallow enough to show, low enough to be shore
MAX_SLOPE = 0.70         # rise over run: steeper cut banks keep their earth
ROAD_CLEAR_M = 2.5
DECK_CLEAR_M = 2.0
SINK = 0.35              # of a stone's height, so it sits in the bed and does not perch


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("level")
    ap.add_argument("mask")
    ap.add_argument("terrain")
    ap.add_argument("out")
    ap.add_argument("--seed", type=int, default=53)
    a = ap.parse_args()
    level = json.loads(Path(a.level).read_text(encoding="utf-8"))
    rect = level["landscape"]["pbr"]["rect"]
    grid = Grid(a.mask, rect, a.terrain)
    from PIL import Image
    raw = np.asarray(Image.open(a.mask)).astype(np.float32) / 255.0
    height_above = raw[..., 1] * 16.0 - 4.0
    rng = np.random.default_rng(a.seed)
    slope = np.hypot(*np.gradient(grid.h, grid.step))
    decks = structures.decks(json.loads(structures.GEOMETRY.read_text()))
    corridors = shapely.union_all([d["corridor"] for d in decks]).buffer(DECK_CLEAR_M) if decks else None

    # Candidate cells: mask texels in the band. Each kind draws a Poisson count per texel.
    n = grid.n
    texel = rect[2] / n / 100.0
    rows, cols = np.nonzero((raw[..., 2] > 0.5) & (grid.bank >= BANK_M[0]) & (grid.bank <= BANK_M[1])
                            & (height_above >= LEVEL_M[0]) & (height_above <= LEVEL_M[1]))
    bank = grid.bank[rows, cols]
    cx = rect[0] + (cols + 0.5) / n * rect[2]
    cy = rect[1] + (rows + 0.5) / n * rect[3]
    entries, report = [], {"texels": int(len(rows)), "band_m2": round(len(rows) * texel * texel)}
    for kind, (meshes, cull, flags, (s0, s1), edge_density, half_m) in KINDS.items():
        # Densest from just under the water to a metre up, halving every half_m beyond.
        falloff = np.where(bank < 1.0, 1.0, 0.5 ** ((bank - 1.0) / half_m))
        counts = rng.poisson(edge_density * falloff * texel * texel)
        idx = np.repeat(np.arange(len(rows)), counts)
        ux = cx[idx] + rng.uniform(-0.5, 0.5, len(idx)) * texel * 100
        uy = cy[idx] + rng.uniform(-0.5, 0.5, len(idx)) * texel * 100
        keep = grid.terrain_at(slope, ux, uy) < MAX_SLOPE
        keep &= grid.terrain_at(grid.road_dist, ux, uy) > ROAD_CLEAR_M
        if corridors is not None:
            keep &= ~shapely.contains_xy(corridors, ux / 100.0, -uy / 100.0)
        report[kind] = {"drawn": int(len(idx)), "steep_road_deck": int((~keep).sum())}
        ux, uy = ux[keep], uy[keep]
        pick = rng.integers(len(meshes), size=len(ux))
        scale = rng.uniform(s0, s1, len(ux)) ** 1.0
        # Terrain normal from the heightfield (metres), in UE axes: x east, y = -authoring y.
        dx = (grid.terrain_at(grid.h, ux + 100, uy) - grid.terrain_at(grid.h, ux - 100, uy)) / 2.0
        dy = (grid.terrain_at(grid.h, ux, uy + 100) - grid.terrain_at(grid.h, ux, uy - 100)) / 2.0
        ground = grid.terrain_at(grid.h, ux, uy) * 100.0
        for k, mesh in enumerate(meshes):
            sel = np.nonzero(pick == k)[0]
            if not len(sel):
                continue
            info = mesh_info(str(HERE.parents[3] / "target/release/mjolnir.exe"), PAKS, mesh)
            lo_z = info["origin"][2] - info["extent"][2]
            tall = 2 * info["extent"][2]
            xf = np.zeros((len(sel), 10), dtype="<f4")
            for j, i in enumerate(sel):
                normal = np.array([-dx[i], -dy[i], 1.0])
                normal = normal / np.linalg.norm(normal)
                # Half way to the ground's tilt, plus a few degrees of its own.
                up = normal + np.array([0, 0, 1.0])
                up += rng.normal(0, 0.08, 3)
                up /= np.linalg.norm(up)
                yaw = rng.uniform(0, 2 * np.pi)
                flat = np.array([np.cos(yaw), np.sin(yaw), 0.0])
                t = flat - up * np.dot(up, flat)
                t /= np.linalg.norm(t)
                q = Rotation.from_matrix(np.column_stack((t, np.cross(up, t), up))).as_quat()
                s = scale[i]
                z = ground[i] - lo_z * s - SINK * tall * s
                xf[j] = [ux[i], uy[i], z, *q, s, s, s]
            leaf = mesh.rsplit(".", 1)[-1]
            definition = dict(key=f"{kind}{k + 1}", mesh=mesh, cull=list(cull), flags=flags, wpo=0,
                              material=None, origin=info["origin"], extent=info["extent"],
                              standin_slots=info["slots"])
            entries.append((definition, xf))
            report.setdefault("groups", {})[f"{kind}{k + 1}"] = {"mesh": leaf, "count": len(sel)}
    out = Path(a.out)
    pack_groups(out, OWNER, entries)
    report["count"] = int(sum(len(x) for _, x in entries))
    report["seed"] = a.seed
    (out / "survey.json").write_text(json.dumps(report, indent=1))
    print(json.dumps(report))


if __name__ == "__main__":
    main()
