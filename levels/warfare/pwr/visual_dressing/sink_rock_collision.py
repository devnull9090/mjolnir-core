# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy>=2,<3", "shapely>=2,<3"]
# ///
"""Take one decor rock's native collision out of a PWR collision scene, keeping its topology.

    python levels/warfare/pwr/visual_dressing/sink_rock_collision.py SCENE_DIR LEVEL HULLS ROCK_ID OUT_DIR

SCENE_DIR holds collision_scene.json/.bin (CE arrays, halo wu; the input of
`mjolnir level collision`), LEVEL the level.json whose decor row ROCK_ID is the rock,
HULLS the outcrop hull folder (check_structure_clearance.py). The rock's surfaces are
the scenery triangles whose three vertices all lie on its transformed hull, within
TOLERANCE; every scenery triangle in the scene has vertices of its own, so nothing
else moves. They are lowered SINK metres into the ground (planes recomputed), which
keeps every array and index as it was, and the counts are checked against the hull's
own face count. Writes OUT_DIR/collision_scene.json/.bin; SCENE_DIR is never changed.
For the rock that stood through the middle bridge's deck (pwr_bank_desert_b_806),
whose render row is dropped from the level at the same time.
"""
from pathlib import Path
import argparse, json, shutil, sys

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import check_structure_clearance as structures  # noqa: E402

METRES_PER_WU = 3.048
TOLERANCE_M = 0.01
SINK_M = 30.0


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


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("scene_dir", type=Path)
    p.add_argument("level", type=Path)
    p.add_argument("hulls", type=Path)
    p.add_argument("rock")
    p.add_argument("out_dir", type=Path)
    a = p.parse_args()
    doc = json.loads((a.scene_dir / "collision_scene.json").read_text())
    raw = bytearray((a.scene_dir / doc["bin"]).read_bytes())
    lay = arrays(raw, doc)
    level = json.loads(a.level.read_text(encoding="utf-8"))
    row = next(r for r in level["decor"] if r["id"] == a.rock)
    hull = json.loads((a.hulls / (row["mesh"].rsplit("/", 1)[-1].split(".")[0] + ".json")).read_text())
    pts = structures.hull_points(a.hulls, row) / METRES_PER_WU          # native wu
    faces = np.array(hull["faces"])
    # Each hull face as a plane; a vertex is "on the hull" when it lies on some face plane
    # within tolerance and inside the hull (all plane distances <= tolerance).
    tri = pts[faces]
    n = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    n /= np.linalg.norm(n, axis=1)[:, None]
    d = (n * tri[:, 0]).sum(axis=1)
    centre = pts.mean(axis=0)
    flip = (n @ centre - d) > 0
    n[flip], d[flip] = -n[flip], -d[flip]
    tol = TOLERANCE_M / METRES_PER_WU
    vo, vc, vs = lay["vertices"]
    verts = np.frombuffer(raw, "<f4", vc * 4, vo).reshape(vc, 4)[:, :3].astype(np.float64)
    lo, hi = pts.min(axis=0) - tol, pts.max(axis=0) + tol
    box = np.nonzero(((verts >= lo) & (verts <= hi)).all(axis=1))[0]
    dist = verts[box] @ n.T - d                                          # (k, faces)
    on = (dist <= tol).all(axis=1) & (np.abs(dist) <= tol).any(axis=1)
    on_hull = np.zeros(vc, bool)
    on_hull[box[on]] = True
    eo, ec, es = lay["edges"]
    edges = np.frombuffer(raw, "<i4", ec * 6, eo).reshape(ec, 6)
    so, sc, ss = lay["surfaces"]
    # A surface is the rock's when every edge bounding it joins two on-hull vertices.
    touching = on_hull[edges[:, 0]] & on_hull[edges[:, 1]]
    total = np.zeros(sc, np.int64)
    good = np.zeros(sc, np.int64)
    for side in (4, 5):
        s = edges[:, side]
        valid = s >= 0
        np.add.at(total, s[valid], 1)
        np.add.at(good, s[valid], touching[valid].astype(np.int64))
    rock = np.nonzero((total > 0) & (good == total))[0]
    if len(rock) != len(faces):
        raise SystemExit(f"{a.rock}: {len(rock)} surfaces match its hull, which has {len(faces)} faces; nothing written")
    ids = np.unique(np.concatenate([edges[(edges[:, 4] == s) | (edges[:, 5] == s)][:, :2].ravel() for s in rock]))
    sink = SINK_M / METRES_PER_WU
    v = np.frombuffer(raw, "<f4", vc * 4, vo).reshape(vc, 4).copy()
    v[ids, 2] -= sink
    raw[vo:vo + vc * vs] = v.tobytes()
    po, pc, ps = lay["planes"]
    planes = np.frombuffer(raw, "<f4", pc * 4, po).reshape(pc, 4).copy()
    surf = np.frombuffer(raw, "<i4", sc * 3, so).reshape(sc, 3)
    for s in rock:
        pid = int(surf[s, 0]) & 0x7FFFFFFF
        planes[pid, 3] -= planes[pid, 2] * sink                          # same normal, lowered
    raw[po:po + pc * ps] = planes.tobytes()
    a.out_dir.mkdir(parents=True, exist_ok=True)
    (a.out_dir / doc["bin"]).write_bytes(bytes(raw))
    doc["rock_removed"] = {"id": a.rock, "surfaces": [int(s) for s in rock], "vertices": len(ids),
                           "sunk_m": SINK_M, "tolerance_m": TOLERANCE_M}
    (a.out_dir / "collision_scene.json").write_text(json.dumps(doc, indent=2))
    print(f"{a.rock}: {len(rock)} surfaces ({len(ids)} vertices) lowered {SINK_M} m; hull has {len(faces)} faces")


if __name__ == "__main__":
    main()
