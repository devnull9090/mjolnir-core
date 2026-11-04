"""A converted map's shadow shell: its walls again, a little behind themselves.

    python tools/level/shadow_shell.py <level.json> <scene.gltf> <out.json> [--swap swap.json] [--depth 20]

CE's level is one-sided planes with nothing behind them, and the loader's
terrain shadow copy (MJOLNIRLevelLoader spawnShadowProxy) casts exactly
those planes. Where two walls meet in a room's inside corner, the sun's way
out passes through the neighbouring wall at no distance at all, inside the
shadow map's bias, and nothing else stands behind it: a lit sliver ran down
every inside corner of Sidewinder's rooms, crawling with the shadow map's
dither (2026-10-14; a hidden block 10 cm behind one wall put it out).

So every solid terrain triangle again, moved back along its own normal (into
the solid it faces away from), with a strip across the back of each inside
corner where the two moved faces part by `--depth` cm, or by under half the distance
to the nearest surface behind it, so a thin wall's copy never stands out in
the room beyond. The copy is added to the proxy, not swapped for it (the
moved faces open at convex edges; the planes themselves still close them).
Left out: the slots a landscape cuts (the landscape casts the ground), the
masked ones (grates and ladders keep their pattern), anything not on the CE
environment masters (plasma) and the CE boulders a swap hides.

Writes build_ce_cliffs.py's mesh spec (built as SM_<CODE>_ShadowShell,
Unreal cm at the origin, one section, not Nanite).
"""
import argparse
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
CELL = 200.0  # cm: the grid the behind-test searches


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("level")
    ap.add_argument("scene")
    ap.add_argument("out")
    ap.add_argument("--swap", help="scenery_swap.py's swap.json: its hidden slots are left out")
    ap.add_argument("--depth", type=float, default=20.0, help="cm behind each face")
    ap.add_argument("--min", type=float, default=3.0, help="cm: faces with less room behind are left out")
    a = ap.parse_args()
    sys.path.insert(0, HERE)
    from refine_water_gltf import read_accessor

    level = json.load(open(a.level, encoding="utf-8"))
    terrain = next(i for i in level["decor"] if str(i.get("id", "")).endswith("_terrain"))
    mats = terrain.get("materials") or []
    cut = set(((level.get("landscape") or {}).get("cut") or {}).get("slots") or [])
    hide = json.load(open(a.swap, encoding="utf-8")).get("hide", []) if a.swap and os.path.exists(a.swap) else []

    def solid(slot):
        m = mats[slot] if 0 <= slot < len(mats) else None
        if not isinstance(m, dict) or m in hide or slot in cut:
            return False
        parent = str(m.get("parent") or "")
        # Authored surface-library masters are opaque Default Lit materials.
        # Their hulls need the same sealed shadow backing as CE metal.
        return (("M_CE_Environment" in parent and "Masked" not in parent)
                or "/SurfaceMaterials/M_Authored_" in parent)

    doc = json.load(open(a.scene, encoding="utf-8"))
    data = open(os.path.join(os.path.dirname(a.scene), doc["buffers"][0]["uri"]), "rb").read()
    allt, keep = [], []
    for mesh in doc["meshes"]:
        for p in mesh["primitives"]:
            att = p["attributes"]
            P = read_accessor(doc, data, att["POSITION"]).astype(np.float64)[:, [0, 2, 1]] * 100.0
            N = read_accessor(doc, data, att["NORMAL"]).astype(np.float64)[:, [0, 2, 1]]
            idx = read_accessor(doc, data, p["indices"]).reshape(-1, 3).astype(np.int64)
            tri = P[idx]
            allt.append(tri)
            if solid(p["material"] + 1):
                keep.append((tri, N[idx].sum(1)))
    if not keep:
        sys.exit("no solid terrain slots")
    allt = np.concatenate(allt)
    tris = np.concatenate([k[0] for k in keep])
    vn = np.concatenate([k[1] for k in keep])

    # Face normals, turned to agree with the exported (playable-side) normals.
    n = np.cross(tris[:, 1] - tris[:, 0], tris[:, 2] - tris[:, 0])
    ln = np.linalg.norm(n, axis=1)
    good = ln > 1e-6
    tris, vn, n, ln = tris[good], vn[good], n[good], ln[good]
    n /= ln[:, None]
    n[(n * vn).sum(1) < 0] *= -1.0

    # Every triangle by grid cell (its box), for the behind-test.
    lo_all = allt.min(1)
    hi_all = allt.max(1)
    grid = {}
    for i in range(len(allt)):
        c0 = np.floor(lo_all[i] / CELL).astype(int)
        c1 = np.floor(hi_all[i] / CELL).astype(int)
        for x in range(c0[0], c1[0] + 1):
            for y in range(c0[1], c1[1] + 1):
                for z in range(c0[2], c1[2] + 1):
                    grid.setdefault((x, y, z), []).append(i)
    A, B, C = allt[:, 0], allt[:, 1], allt[:, 2]
    reach = a.depth / 0.45

    def behind(o, d):
        """Nearest surface along d from o within `reach` (cm), else reach."""
        cells = set()
        for s in (0.0, 0.5, 1.0):
            q = o + d * reach * s
            c = np.floor(q / CELL).astype(int)
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    for dz in (-1, 0, 1):
                        cells.add((c[0] + dx, c[1] + dy, c[2] + dz))
        cand = np.unique(np.fromiter((i for c in cells for i in grid.get(c, ())), dtype=np.int64))
        if not len(cand):
            return reach
        a_, b_, c_ = A[cand], B[cand], C[cand]
        e1, e2 = b_ - a_, c_ - a_
        pv = np.cross(d, e2)
        det = (e1 * pv).sum(1)
        ok = np.abs(det) > 1e-9
        inv = np.where(ok, 1.0 / np.where(ok, det, 1.0), 0.0)
        s = o - a_
        u = (s * pv).sum(1) * inv
        qv = np.cross(s, e1)
        v = (qv * d).sum(1) * inv
        t = (e2 * qv).sum(1) * inv
        hit = ok & (u >= 0) & (v >= 0) & (u + v <= 1) & (t > 0.5) & (t < reach)
        return float(t[hit].min()) if hit.any() else reach

    out_tris = []
    depth_of = np.zeros(len(tris))
    for i in range(len(tris)):
        tri, d = tris[i], -n[i]
        c = tri.mean(0)
        # The centroid and the corners drawn a little in: the nearest surface
        # behind any part of the face.
        room = min(behind(p + d * 0.1, d) for p in (c, *(tri + (c - tri) * 0.15)))
        depth = min(a.depth, 0.45 * room)
        if depth < a.min:
            continue
        out_tris.append(tri + d * depth)
        depth_of[i] = depth
    if not out_tris:
        sys.exit("no faces with room behind them")
    depths = depth_of[depth_of > 0]
    # Inside corners: the two faces moved back part, leaving a wedge open
    # behind the crease, and a sun coming in across the corner went through
    # it (the floor's foot, the bends of Sidewinder's rooms). A strip from
    # one face's moved edge to the other's closes it; it lies behind both
    # faces, in the solid the corner turns about.
    key = lambda q: (round(q[0], 1), round(q[1], 1), round(q[2], 1))
    edges = {}
    for i, tri in enumerate(tris):
        for k in range(3):
            e = tuple(sorted((key(tri[k]), key(tri[(k + 1) % 3]))))
            edges.setdefault(e, []).append(i)
    fillers = 0
    for e, faces in edges.items():
        if len(faces) != 2:
            continue
        i, j = faces
        if depth_of[i] <= 0 and depth_of[j] <= 0:
            continue
        if abs(n[i] @ n[j]) > 0.98:
            continue
        p0, p1 = np.array(e[0]), np.array(e[1])
        if (tris[j].mean(0) - p0) @ n[i] <= 0:
            continue  # convex: the moved faces meet inside the solid already
        oi, oj = -n[i] * depth_of[i], -n[j] * depth_of[j]
        out_tris.append(np.array([p0 + oi, p1 + oi, p1 + oj]))
        out_tris.append(np.array([p0 + oi, p1 + oj, p0 + oj]))
        fillers += 1
    shell = np.stack(out_tris)
    corners = shell.reshape(-1, 3)
    # One normal a corner, the face's own: the shell is never drawn.
    m = np.cross(shell[:, 1] - shell[:, 0], shell[:, 2] - shell[:, 0])
    m /= np.maximum(np.linalg.norm(m, axis=1, keepdims=True), 1e-9)
    normals = np.repeat(m, 3, axis=0)
    count = len(corners)
    out = {
        "positions": corners.round(2).tolist(),
        "normals": normals.round(4).tolist(),
        "indices": list(range(count)),
        "uv0": [[0.0, 0.0]] * count,
        "uv1": [[0.0, 0.0]] * count,
        "sections": [0] * (count // 3),
        "slots": [0],
        "weight": [1.0] * count,
        "nanite": False,
        "material": "M_CE_Environment",
    }
    json.dump(out, open(a.out, "w", encoding="utf-8"))
    dep = np.array(depths)
    print(f"{len(dep)} shell triangle(s) of {len(tris)} solid ({len(tris) - len(dep)} without room behind) and "
          f"{fillers} inside corner(s) closed; depth {dep.min():.1f}..{dep.max():.1f} cm, "
          f"{int((dep < a.depth).sum())} clamped")


if __name__ == "__main__":
    main()
