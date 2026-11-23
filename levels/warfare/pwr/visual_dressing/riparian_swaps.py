"""PWR river and lake edges: driftwood logs and boulders in the collision slots of rocks they
replace (detail plan step 2, collision half).

The map's collision scene is full (1,199,995 of the pipeline's 1,200,000 surfaces), so a new
piece a player can touch takes an existing rock's place: the rock's decor row goes, the new
piece's row comes, and the new piece's convex hull is written into the rock's own scenery
triangles (each scenery triangle in the scene has vertices of its own, so moving them touches
nothing else). The hull is capped so it never needs more triangles than the rock had; the
rock's spare triangles are lowered SINK_M into the ground, as sink_rock_collision.py does.

    python riparian_swaps.py plan  LEVEL MASK TERRAIN OLD_HULLS NEW_HULLS PLAN.json [--logs N] [--boulders N] [--seed S]
    python riparian_swaps.py level LEVEL PLAN.json OUT_LEVEL.json
    python riparian_swaps.py collide SCENE_DIR LEVEL PLAN.json OLD_HULLS NEW_HULLS OUT_DIR

LEVEL is the carried-forward pwr.level.json; MASK the shore mask (tools/level/shore_mask.py:
R signed metres to the water's edge, -8..24); TERRAIN the runtime heightfield folder;
OLD_HULLS the outcrop hull folder the rocks' collision was made from; NEW_HULLS a folder for
the new pieces' capped hulls (b30_collision.hull_of caches, <leaf>_<budget>.json).
"""
import argparse
import json
import math
import sys
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import check_structure_clearance as structures  # noqa: E402
import b30_collision  # noqa: E402  (tools/level, put on the path by check_structure_clearance)

METRES_PER_WU = 3.048
TOLERANCE_M = 0.01
SINK_M = 30.0
PREFIX = "pwr_riparian_swap_"
ROCKS = ("pcg_v4_shore_", "pwr_v6_riparian_", "pwr_scree_")
GLACIAL = "/Game/Env/Bio/Rock/Glacial/"
SPACING_M = 35.0       # between chosen swaps
EDGE_M = (-0.5, 9.0)   # a swapped rock's centre, metres from the water's edge
ROAD_CLEAR_M = 6.0

# Mesh and scale range. Logs lie along their x axis.
LOGS = [   # driftwood a metre thick: the smaller log scans read as twigs from a few metres
    ("/Game/Megascans/3D_Assets/Fallen_Tree_Log_xiclaj1r/S_Fallen_Tree_Log_xiclaj1r_lod0_Var1", (1.4, 1.8)),
    ("/Game/Megascans/3D_Assets/Large_Fallen_Tree_wd3hfidbw/S_Large_Fallen_Tree_wd3hfidbw_lod0_Var1", (0.8, 1.1)),
]
BOULDERS = [
    ("/Game/Environments/PNW/Assets/Mossy_Boulder_A/SM_Mossy_Boulder_A", (0.45, 0.7)),
    ("/Game/Environments/PNW/Assets/Nordic_Beach_Rocks_A/SM_Nordic_Beach_Rocks_A", (0.45, 0.7)),
    ("/Game/Megascans/3D_Assets/Tundra_Boulder_vivrcjkaw/S_Tundra_Boulder_vivrcjkaw_high_Var1", (0.8, 1.2)),
]


def obj(mesh):
    leaf = mesh.rsplit("/", 1)[-1]
    return f"{mesh}.{leaf}"


def leaf_of(mesh):
    return mesh.rsplit("/", 1)[-1].split(".")[0]


def native_points(local_cm, row):
    """Hull points (local cm) of a decor row in native metres (check_structure_clearance.hull_points)."""
    native = np.asarray(local_cm) / 100.0 * np.array(row.get("scale", [1, 1, 1])) \
        @ b30_collision.rotator_matrix(*row.get("rot", [0, 0, 0])) + np.array(row["pos"]) / 100.0
    return native * np.array([1, -1, 1])


def budget_for(slots):
    """hull_of keeps budget + 8 farthest points; a hull of V points has at most 2V - 4 faces."""
    return (slots + 4) // 2 - 8


class Grid:
    def __init__(self, mask_png, rect, terrain):
        m = np.asarray(Image.open(mask_png)).astype(np.float32) / 255.0
        self.bank = m[..., 0] * 32.0 - 8.0
        self.cover = m[..., 2] > 0.5
        self.rect = rect
        self.n = m.shape[0]
        man = json.loads((Path(terrain) / "runtime-master.json").read_text())
        self.h = np.load(Path(terrain) / man["height"]["path"])
        self.road = np.load(Path(terrain) / man["masks"]["road"]["path"]) > 0.5
        self.road_dist = ndimage.distance_transform_edt(~self.road) * man["spacing_m"][0]
        self.origin = np.array(man["origin_m"], float)
        self.step = float(man["spacing_m"][0])
        gy, gx = np.gradient(ndimage.gaussian_filter(self.bank, 2.0))
        self.gx, self.gy = gx, gy

    def mask_at(self, grid, ux, uy):
        c = (np.atleast_1d(ux) - self.rect[0]) / self.rect[2] * self.n - 0.5
        r = (np.atleast_1d(uy) - self.rect[1]) / self.rect[3] * self.n - 0.5
        return ndimage.map_coordinates(grid, [r, c], order=1, mode="nearest")

    def terrain_at(self, grid, ux, uy):
        i = (np.atleast_1d(ux) / 100.0 - self.origin[0]) / self.step
        j = (-np.atleast_1d(uy) / 100.0 - self.origin[1]) / self.step
        return ndimage.map_coordinates(grid, [j, i], order=1, mode="nearest")


def plan(a):
    level = json.loads(Path(a.level).read_text(encoding="utf-8"))
    grid = Grid(a.mask, level["landscape"]["pbr"]["rect"], a.terrain)
    rng = np.random.default_rng(a.seed)
    spans = structures.decks(json.loads(structures.GEOMETRY.read_text()))
    old_hulls, new_hulls = Path(a.old_hulls), Path(a.new_hulls)
    new_hulls.mkdir(parents=True, exist_ok=True)
    cands = []
    for r in level["decor"]:
        if not r["id"].startswith(ROCKS) or not r["mesh"].startswith(GLACIAL):
            continue
        hull = old_hulls / (leaf_of(r["mesh"]) + ".json")
        if not hull.is_file():
            continue
        ux, uy = r["pos"][:2]
        if not grid.mask_at(grid.cover.astype(np.float32), ux, uy)[0] > 0.5:
            continue
        b = float(grid.mask_at(grid.bank, ux, uy)[0])
        if not EDGE_M[0] <= b <= EDGE_M[1]:
            continue
        if float(grid.terrain_at(grid.road_dist, ux, uy)[0]) < ROAD_CLEAR_M:
            continue
        cands.append((r, len(json.loads(hull.read_text())["faces"]), b))
    rng.shuffle(cands)
    chosen, taken = [], []
    want = [("log", a.logs), ("boulder", a.boulders)]
    kinds = [k for k, n in want for _ in range(n)]
    rng.shuffle(kinds)
    skipped = {"spacing": 0, "deck": 0, "ground": 0, "road": 0}
    for r, slots, b in cands:
        if not kinds:
            break
        ux, uy = r["pos"][:2]
        if any(math.hypot(ux - x, uy - y) < SPACING_M * 100 for x, y in taken):
            skipped["spacing"] += 1
            continue
        kind = kinds[-1]
        pool = LOGS if kind == "log" else BOULDERS
        mesh, (s0, s1) = pool[rng.integers(len(pool))]
        budget = budget_for(slots)
        pts, faces = b30_collision.hull_of(obj(mesh), str(new_hulls), budget)
        pts = np.asarray(pts)
        if len(faces) > slots:
            raise ValueError(f"{mesh}: capped hull has {len(faces)} faces for {slots} slots")
        s = float(rng.uniform(s0, s1))
        lo, hi = pts.min(0), pts.max(0)
        if kind == "log":
            # Along the shore (across the water's gradient), give or take 25 degrees, and
            # pitched to the ground under its two ends.
            gx = float(grid.mask_at(grid.gx, ux, uy)[0])
            gy = float(grid.mask_at(grid.gy, ux, uy)[0])
            yaw = math.degrees(math.atan2(gx, -gy)) + float(rng.uniform(-25, 25))
            half = (hi[0] - lo[0]) * s / 2.0
            dx, dy = math.cos(math.radians(yaw)) * half, math.sin(math.radians(yaw)) * half
            za = float(grid.terrain_at(grid.h, ux - dx, uy - dy)[0]) * 100
            zb = float(grid.terrain_at(grid.h, ux + dx, uy + dy)[0]) * 100
            if abs(zb - za) > 0.45 * 2 * half:
                skipped["ground"] += 1
                continue
            pitch = math.degrees(math.atan2(zb - za, 2 * half))
            ends = [grid.terrain_at(grid.road_dist, ux + k * dx, uy + k * dy)[0] for k in (-1, 1)]
            if min(ends) < ROAD_CLEAR_M:
                skipped["road"] += 1
                continue
            sink = 0.25 * (hi[2] - lo[2]) * s
            z = (za + zb) / 2 - lo[2] * s - sink
            rot = [round(pitch, 2), round(yaw, 2), 0.0]
        else:
            g = float(grid.terrain_at(grid.h, ux, uy)[0]) * 100
            sink = 0.18 * (hi[2] - lo[2]) * s
            z = g - lo[2] * s - sink
            rot = [0.0, round(float(rng.uniform(0, 360)), 2), 0.0]
        row = {"id": f"{PREFIX}{kind}_{len(chosen)}", "mesh": obj(mesh), "pos": [round(ux, 1), round(uy, 1), round(z, 1)],
               "rot": rot, "scale": [round(s, 3)] * 3, "static": True}
        if structures.intrusion(spans, native_points(pts, row)) is not None:
            skipped["deck"] += 1
            continue
        kinds.pop()
        taken.append((ux, uy))
        chosen.append({"old": r["id"], "old_mesh": r["mesh"], "slots": slots, "budget": budget,
                       "faces": len(faces), "bank_m": round(b, 2), "new": row})
    out = {"schema": "pwr-riparian-swaps-v1", "seed": a.seed, "swaps": chosen, "skipped": skipped,
           "candidates": len(cands)}
    Path(a.out).write_text(json.dumps(out, indent=1))
    print(json.dumps({"swaps": len(chosen), "logs": sum(c["new"]["id"].split("_")[3] == "log" for c in chosen),
                      "candidates": len(cands), "skipped": skipped}))


def level_patch(a):
    level = json.loads(Path(a.level).read_text(encoding="utf-8"))
    swaps = json.loads(Path(a.plan).read_text())["swaps"]
    by_old = {s["old"]: s["new"] for s in swaps}
    out, done = [], 0
    for r in level["decor"]:
        if r["id"] in by_old:
            out.append(by_old[r["id"]])
            done += 1
        else:
            out.append(r)
    if done != len(swaps):
        raise SystemExit(f"{len(swaps) - done} swapped rows are not in the level")
    level["decor"] = out
    Path(a.out).write_text(json.dumps(level, indent=1), encoding="utf-8")
    print(f"{done} rows swapped")


def arrays(raw, doc):
    out, at = {}, 0
    for key in doc["array_order"]:
        count = int(np.frombuffer(raw, "<u4", 1, at)[0])
        size = doc["element_sizes"][key]
        out[key] = (at + 4, count, size)
        at += 4 + count * size
    if at != len(raw):
        raise ValueError("collision_scene.bin does not match its manifest")
    return out


def rock_surfaces(pts_wu, faces, verts, edges, sc):
    """The scene surfaces whose every edge joins two vertices on this hull (sink_rock_collision)."""
    tri = pts_wu[np.asarray(faces)]
    n = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    n /= np.linalg.norm(n, axis=1)[:, None]
    d = (n * tri[:, 0]).sum(axis=1)
    centre = pts_wu.mean(axis=0)
    flip = (n @ centre - d) > 0
    n[flip], d[flip] = -n[flip], -d[flip]
    tol = TOLERANCE_M / METRES_PER_WU
    lo, hi = pts_wu.min(axis=0) - tol, pts_wu.max(axis=0) + tol
    box = np.nonzero(((verts >= lo) & (verts <= hi)).all(axis=1))[0]
    dist = verts[box] @ n.T - d
    on = (dist <= tol).all(axis=1) & (np.abs(dist) <= tol).any(axis=1)
    on_hull = np.zeros(len(verts), bool)
    on_hull[box[on]] = True
    touching = on_hull[edges[:, 0]] & on_hull[edges[:, 1]]
    total = np.zeros(sc, np.int64)
    good = np.zeros(sc, np.int64)
    for side in (4, 5):
        s = edges[:, side]
        valid = s >= 0
        np.add.at(total, s[valid], 1)
        np.add.at(good, s[valid], touching[valid].astype(np.int64))
    return np.nonzero((total > 0) & (good == total))[0]


def surface_loop(s, first_edge, edges):
    """A surface's vertices in its edge loop's order (CE: start/end vertex, forward/reverse edge,
    left/right surface)."""
    out, e = [], first_edge
    for _ in range(8):
        a0, a1, fwd, rev, left, right = edges[e]
        if left == s:
            out.append(a0)
            e = fwd
        else:
            out.append(a1)
            e = rev
        if e == first_edge:
            break
    return out


def collide(a):
    doc = json.loads((Path(a.scene_dir) / "collision_scene.json").read_text())
    raw = bytearray((Path(a.scene_dir) / doc["bin"]).read_bytes())
    lay = arrays(raw, doc)
    level = json.loads(Path(a.level).read_text(encoding="utf-8"))
    rows = {r["id"]: r for r in level["decor"]}
    swaps = json.loads(Path(a.plan).read_text())["swaps"]
    vo, vc, vs = lay["vertices"]
    v = np.frombuffer(raw, "<f4", vc * 4, vo).reshape(vc, 4).copy()
    verts = v[:, :3].astype(np.float64)
    eo, ec, es = lay["edges"]
    edges = np.frombuffer(raw, "<i4", ec * 6, eo).reshape(ec, 6)
    so, sc, ss = lay["surfaces"]
    surf = np.frombuffer(raw, "<i4", sc * 3, so).reshape(sc, 3)
    po, pc, ps = lay["planes"]
    planes = np.frombuffer(raw, "<f4", pc * 4, po).reshape(pc, 4).copy()
    sink = SINK_M / METRES_PER_WU
    flip_bit = int(doc["plane_encoding"]["flip_flag"], 16)
    mats = {m.get("game_material"): m["index"] for m in doc["materials"] if m.get("game_material")}
    # The surface's material (i16 at byte 10 of each 12-byte surface): logs are wood, boulders stone.
    material = np.frombuffer(raw, "<i2", sc * 6, so).reshape(sc, 6)[:, 5].copy()
    pid_count = np.bincount(surf[:, 0] & 0x7FFFFFFF, minlength=pc)
    report = []
    for sw in swaps:
        old = rows[sw["old"]]
        old_hull = json.loads((Path(a.old_hulls) / (leaf_of(old["mesh"]) + ".json")).read_text())
        old_wu = native_points(old_hull["points"], old) / METRES_PER_WU
        mine = rock_surfaces(old_wu, old_hull["faces"], verts, edges, sc)
        if len(mine) != len(old_hull["faces"]):
            raise SystemExit(f"{sw['old']}: {len(mine)} surfaces match its hull of {len(old_hull['faces'])} faces")
        new = sw["new"]
        pts, faces = b30_collision.hull_of(obj(new["mesh"].split(".")[0]), str(Path(a.new_hulls)), sw["budget"])
        new_wu = native_points(pts, new) / METRES_PER_WU
        centre = new_wu.mean(axis=0)
        if len(faces) > len(mine):
            raise SystemExit(f"{new['id']}: {len(faces)} faces for {len(mine)} slots")
        wood = "_log_" in new["id"]
        want = mats.get("tough_organic_wood" if wood else "hard_terrain_stone")
        for k, s in enumerate(mine):
            loop = surface_loop(s, int(surf[s, 1]), edges)
            if len(loop) != 3:
                raise SystemExit(f"surface {s} is not a triangle ({len(loop)})")
            pid = int(surf[s, 0]) & 0x7FFFFFFF
            flipped = bool(int(surf[s, 0]) & flip_bit)
            if pid_count[pid] != 1:
                raise SystemExit(f"surface {s} shares plane {pid}")
            p_old = verts[loop]
            n_old = np.cross(p_old[1] - p_old[0], p_old[2] - p_old[0])
            # The scene's own handedness: the stored plane's normal against this loop's cross.
            stored = -planes[pid, :3] if flipped else planes[pid, :3]
            same = float(np.dot(n_old, stored)) > 0
            if k < len(faces):
                tri = new_wu[list(faces[k])]
                nrm = np.cross(tri[1] - tri[0], tri[2] - tri[0])
                if np.dot(nrm, tri.mean(axis=0) - centre) < 0:     # outward
                    tri = tri[[0, 2, 1]]
                    nrm = -nrm
                nrm /= np.linalg.norm(nrm)
                if not same:                                        # loop order to the scene's convention
                    tri = tri[[0, 2, 1]]
                for vid, p in zip(loop, tri):
                    v[vid, :3] = p
                # The effective plane faces out of the hull; a flipped index reads it negated.
                sign = -1.0 if flipped else 1.0
                planes[pid, :3] = sign * nrm
                planes[pid, 3] = sign * float(np.dot(nrm, tri[0]))
                if want is not None:
                    material[s] = want
            else:
                for vid in loop:
                    v[vid, 2] -= sink
                planes[pid, 3] -= planes[pid, 2] * sink
        report.append({"old": sw["old"], "new": new["id"], "slots": len(mine), "faces": len(faces),
                       "sunk": len(mine) - len(faces)})
    raw[vo:vo + vc * vs] = v.tobytes()
    raw[po:po + pc * ps] = planes.tobytes()
    surf_bytes = np.frombuffer(raw, "<i2", sc * 6, so).reshape(sc, 6).copy()
    surf_bytes[:, 5] = material
    raw[so:so + sc * ss] = surf_bytes.tobytes()
    out = Path(a.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / doc["bin"]).write_bytes(bytes(raw))
    doc["riparian_swaps"] = report
    (out / "collision_scene.json").write_text(json.dumps(doc, indent=2))
    print(f"{len(report)} swaps written: {sum(r['faces'] for r in report)} triangles, {sum(r['sunk'] for r in report)} sunk")


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    q = sub.add_parser("plan")
    for k in ("level", "mask", "terrain", "old_hulls", "new_hulls", "out"):
        q.add_argument(k)
    q.add_argument("--logs", type=int, default=24)
    q.add_argument("--boulders", type=int, default=24)
    q.add_argument("--seed", type=int, default=47)
    q.set_defaults(fn=plan)
    q = sub.add_parser("level")
    for k in ("level", "plan", "out"):
        q.add_argument(k)
    q.set_defaults(fn=level_patch)
    q = sub.add_parser("collide")
    for k in ("scene_dir", "level", "plan", "old_hulls", "new_hulls", "out_dir"):
        q.add_argument(k)
    q.set_defaults(fn=collide)
    a = p.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
