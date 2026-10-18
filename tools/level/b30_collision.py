#!/usr/bin/env python3
"""Collision for the B30 meshes an upgraded CE map draws (scenery_swap.py's
rocks and tree trunks, scatter_foliage.py's stones and driftwood), as
triangles for merge_ce_collision.py --extra.

    python tools/level/b30_collision.py <level.json> <foliage.bin> <swap.json> <out.json> [--hulls DIR]

The Blam simulation does all of a map's collision; it never sees Unreal
geometry, so the swapped rocks and trees were walked through (2026-10-12).
Each mesh collides as a convex hull of its coarsest LOD (at most HULL_POINTS
points), exported once with `mjolnir mesh export` and kept in --hulls.
Out: {"triangles": [[x, y, z] x 3 ...] in CE world units, "materials":
[game material per triangle], "skip_entries": [placement indices whose CE
collision the swap replaced]}.
"""
import argparse
import json
import math
import os
import random
import struct
import subprocess
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
PAKS = os.environ.get("HCE_PAKS", "C:/Program Files (x86)/Steam/steamapps/common/Halo Campaign Evolved/Meteorite/Content/Paks")
MJOLNIR = os.environ.get("MJOLNIR_DEBUG", os.path.join(REPO, "target", "debug", "mjolnir.exe"))
WU = 304.8  # cm per CE world unit (3.048 m)
HULL_POINTS = int(os.environ.get("B30_HULL_POINTS", 48))
# What collides, by mesh path: (substring, game material). Leaves, ferns,
# grass and pebbles stay walk-through, as in B30.
SOLID = [("/Rock/", "hard_terrain_stone"), ("Rock_", "hard_terrain_stone"), ("_Trunk", "tough_organic_wood"),
         ("Driftwood", "tough_organic_wood"), ("Log_", "tough_organic_wood")]
# Foliage rules that collide, and the smallest that does (cm of height).
FOLIAGE_RULES = {"stones": 45.0, "driftwood": 25.0}
# The cliffs' cladding rocks (thousands a map) collide only where a player
# can reach them: some hull point within CLAD_REACH above walkable ground,
# each a coarser hull.
CLAD_REACH = 250.0
CLAD_POINTS = 16  # hull budget: 16 // 1 + 8 = 24 points, about 40 triangles
WALKABLE = 0.6  # the ground normal's least z a player stands on


def material_for(mesh):
    return next((m for k, m in SOLID if k in mesh), None)


# --- convex hull -------------------------------------------------------------

def farthest_points(p, k):
    if len(p) <= k:
        return p
    chosen = [int(np.argmax(np.linalg.norm(p - p.mean(0), axis=1)))]
    d = np.linalg.norm(p - p[chosen[0]], axis=1)
    while len(chosen) < k:
        i = int(np.argmax(d))
        chosen.append(i)
        d = np.minimum(d, np.linalg.norm(p - p[i], axis=1))
    return p[chosen]


def convex_hull(p):
    """Triangles (index triples, outward) of the convex hull of p (n x 3),
    by incremental insertion; fine for the few dozen points used here."""
    p = np.asarray(p, dtype=np.float64)
    n = len(p)
    # A starting tetrahedron of well-spread points.
    i0 = int(np.argmin(p[:, 0]))
    i1 = int(np.argmax(np.linalg.norm(p - p[i0], axis=1)))
    line = p[i1] - p[i0]
    i2 = int(np.argmax(np.linalg.norm(np.cross(p - p[i0], line), axis=1)))
    nrm = np.cross(p[i1] - p[i0], p[i2] - p[i0])
    i3 = int(np.argmax(np.abs((p - p[i0]) @ nrm)))
    if abs((p[i3] - p[i0]) @ nrm) < 1e-9:
        return []
    centre = p[[i0, i1, i2, i3]].mean(0)
    faces = []

    def add(a, b, c):
        if np.cross(p[b] - p[a], p[c] - p[a]) @ (p[a] - centre) < 0:
            b, c = c, b
        faces.append((a, b, c))

    for f in ((i0, i1, i2), (i0, i1, i3), (i0, i2, i3), (i1, i2, i3)):
        add(*f)
    for i in range(n):
        if i in (i0, i1, i2, i3):
            continue
        visible = []
        for f in faces:
            a, b, c = f
            nf = np.cross(p[b] - p[a], p[c] - p[a])
            if nf @ (p[i] - p[a]) > 1e-7 * max(1.0, np.linalg.norm(nf)):
                visible.append(f)
        if not visible:
            continue
        edges = {}
        for a, b, c in visible:
            for e in ((a, b), (b, c), (c, a)):
                edges[e] = edges.get(e, 0) + 1
        horizon = [e for e in edges if (e[1], e[0]) not in edges]
        faces = [f for f in faces if f not in visible]
        for a, b in horizon:
            faces.append((a, b, i))
    return faces


MIN_HULL_SOURCE = 200  # vertices: a desert boulder's last LOD has 18


def glb_positions(path):
    """Vertex positions (Unreal cm, mesh local) of the glb's coarsest LOD
    with at least MIN_HULL_SOURCE vertices (`mjolnir mesh export` writes
    LODs in order), else its first."""
    b = open(path, "rb").read()
    jl = struct.unpack_from("<I", b, 12)[0]
    doc = json.loads(b[20:20 + jl])
    data = b[20 + jl + 8:]

    def count(mesh):
        return sum(doc["accessors"][p["attributes"]["POSITION"]]["count"] for p in mesh["primitives"])

    rich = [m for m in doc["meshes"] if count(m) >= MIN_HULL_SOURCE]
    mesh = rich[-1] if rich else doc["meshes"][0]
    pts = []
    for prim in mesh["primitives"]:
        acc = doc["accessors"][prim["attributes"]["POSITION"]]
        view = doc["bufferViews"][acc["bufferView"]]
        start = view.get("byteOffset", 0) + acc.get("byteOffset", 0)
        stride = view.get("byteStride") or 12
        for k in range(acc["count"]):
            x, y, z = struct.unpack_from("<fff", data, start + k * stride)
            pts.append((x * 100.0, z * 100.0, y * 100.0))  # glTF metres, +Y up -> Unreal cm, +Z up
    return np.array(pts)


# A leaning trunk's one hull is a slab of air beside it; trunks collide as a
# stack of hulls, each a band of the trunk's height.
TRUNK_SLICES = int(os.environ.get("B30_TRUNK_SLICES", 3))
TRUNK_POINTS = int(os.environ.get("B30_TRUNK_POINTS", 24))  # 24 // 3 + 8 = 16 points a slice


def hull_of(mesh, hulls_dir, budget=HULL_POINTS):
    """The mesh's hull(s) as (points, faces), cached in hulls_dir: one hull,
    or TRUNK_SLICES for a tree trunk, their faces indexing the points."""
    leaf = mesh.split(".")[0].rsplit("/", 1)[-1]
    cache = os.path.join(hulls_dir, leaf + ("" if budget == HULL_POINTS else f"_{budget}") + ".json")
    if os.path.exists(cache):
        h = json.load(open(cache, encoding="utf-8"))
        return np.array(h["points"]), h["faces"]
    glb = os.path.join(hulls_dir, leaf + ".glb")
    asset = mesh.split(".")[0].lstrip("/").replace("Game/", "", 1)
    subprocess.run([MJOLNIR, "mesh", "export", "--paks", PAKS, "--asset", asset, "--out", glb], check=True,
                   capture_output=True, env=dict(os.environ, MSYS_NO_PATHCONV="1"))
    every = glb_positions(glb)
    os.remove(glb)
    if "_Trunk" in leaf:
        lo, hi = every[:, 2].min(), every[:, 2].max()
        edges = np.linspace(lo, hi, TRUNK_SLICES + 1)
        parts = [every[(every[:, 2] >= edges[i] - 1) & (every[:, 2] <= edges[i + 1] + 1)] for i in range(TRUNK_SLICES)]
    else:
        parts = [every]
    points, faces = [], []
    for part in parts:
        if len(part) < 4:
            continue
        pts = farthest_points(part, budget // len(parts) + 8)
        hull = convex_hull(pts)
        used = sorted({i for f in hull for i in f})
        base = len(points)
        remap = {old: base + new for new, old in enumerate(used)}
        points += pts[used].tolist()
        faces += [[remap[i] for i in f] for f in hull]
    points = np.array(points)
    json.dump({"mesh": mesh, "points": points.round(2).tolist(), "faces": faces}, open(cache, "w", encoding="utf-8"))
    return points, faces


# --- transforms --------------------------------------------------------------

def rotator_matrix(pitch, yaw, roll):
    """Unreal's FRotationMatrix (row vectors: X, Y, Z axes), degrees."""
    p, y, r = (math.radians(v) for v in (pitch, yaw, roll))
    sp, cp, sy, cy, sr, cr = math.sin(p), math.cos(p), math.sin(y), math.cos(y), math.sin(r), math.cos(r)
    return np.array([
        [cp * cy, cp * sy, sp],
        [sr * sp * cy - cr * sy, sr * sp * sy + cr * cy, -sr * cp],
        [-(cr * sp * cy + sr * sy), cy * sr - cr * sp * sy, cr * cp],
    ])


def foliage_matrix(yaw, nx, ny):
    """MJOLNIRLevelLoader's Foliage.rotation: yaw about z, then the up axis
    tilted onto the ground normal (nx, ny); row vectors."""
    c, s = math.cos(yaw), math.sin(yaw)
    rz = np.array([[c, s, 0.0], [-s, c, 0.0], [0.0, 0.0, 1.0]])
    s2 = nx * nx + ny * ny
    if s2 < 1e-8:
        return rz
    nz = math.sqrt(max(0.0, 1.0 - s2))
    k = np.array([-ny, nx, 0.0]) / math.sqrt(s2)
    th = math.acos(min(1.0, nz))
    kx = np.array([[0, -k[2], k[1]], [k[2], 0, -k[0]], [-k[1], k[0], 0]])
    tilt = np.eye(3) + math.sin(th) * kx + (1 - math.cos(th)) * (kx @ kx)  # column-vector rotation
    return rz @ tilt.T


def to_ce(points_cm):
    q = np.asarray(points_cm) / WU
    return np.stack([q[:, 0], -q[:, 1], q[:, 2]], axis=1)


def foliage_records(path):
    raw = open(path, "rb").read()
    _version, groups = struct.unpack_from("<II", raw, 4)
    at = 12
    out = []
    for _ in range(groups):
        (n,) = struct.unpack_from("<I", raw, at)
        at += 4
        recs = [struct.unpack_from("<fffBBbbBBB", raw, at + 19 * i) for i in range(n)]
        at += 19 * n
        out.append(recs)
    return out


class Ground:
    """Heights of the conversion's scene (scene.gltf, CE in glTF metres:
    Unreal = (x, z, y) * 100) straight below a point, by a grid of
    triangles."""

    def __init__(self, scene_gltf, cell=500.0):
        sys.path.insert(0, HERE)
        from refine_water_gltf import read_accessor
        doc = json.load(open(scene_gltf, encoding="utf-8"))
        data = open(os.path.join(os.path.dirname(scene_gltf), doc["buffers"][0]["uri"]), "rb").read()
        tris = []
        for mesh in doc["meshes"]:
            for prim in mesh["primitives"]:
                pos = read_accessor(doc, data, prim["attributes"]["POSITION"]).astype(np.float64)
                idx = read_accessor(doc, data, prim["indices"]).reshape(-1, 3)
                tris.append(pos[idx][:, :, [0, 2, 1]] * 100.0)
        self.t = np.concatenate(tris)
        self.cell = cell
        lo = np.floor(self.t[:, :, :2].min(1) / cell).astype(int)
        hi = np.floor(self.t[:, :, :2].max(1) / cell).astype(int)
        self.grid = {}
        for i in range(len(self.t)):
            if (hi[i] - lo[i]).max() > 40:
                continue  # sky domes and the sea plane
            for gx in range(lo[i][0], hi[i][0] + 1):
                for gy in range(lo[i][1], hi[i][1] + 1):
                    self.grid.setdefault((gx, gy), []).append(i)

    def below(self, x, y, z):
        """Height of the first surface at or below z at (x, y), or None."""
        ids = self.grid.get((int(math.floor(x / self.cell)), int(math.floor(y / self.cell))))
        if not ids:
            return None
        t = self.t[ids]
        a, b, c = t[:, 0], t[:, 1], t[:, 2]
        # Barycentric (x, y) test, then the plane's height.
        v0, v1 = b[:, :2] - a[:, :2], c[:, :2] - a[:, :2]
        v2 = np.array([x, y]) - a[:, :2]
        den = v0[:, 0] * v1[:, 1] - v1[:, 0] * v0[:, 1]
        ok = np.abs(den) > 1e-9
        den = np.where(ok, den, 1.0)
        u = (v2[:, 0] * v1[:, 1] - v1[:, 0] * v2[:, 1]) / den
        v = (v0[:, 0] * v2[:, 1] - v2[:, 0] * v0[:, 1]) / den
        inside = ok & (u >= 0) & (v >= 0) & (u + v <= 1)
        h = a[:, 2] + u * (b[:, 2] - a[:, 2]) + v * (c[:, 2] - a[:, 2])
        h = h[inside & (h <= z + 1.0)]
        return float(h.max()) if len(h) else None

    def walkable(self, x, y, h, d=40.0):
        """Whether the ground at height h under (x, y) is flat enough to
        stand on, by its slope over d cm either side."""
        hx = [self.below(x + d, y, h + 60.0), self.below(x - d, y, h + 60.0)]
        hy = [self.below(x, y + d, h + 60.0), self.below(x, y - d, h + 60.0)]
        if None in hx or None in hy:
            return False
        gx, gy = (hx[0] - hx[1]) / (2 * d), (hy[0] - hy[1]) / (2 * d)
        return 1.0 / math.sqrt(1.0 + gx * gx + gy * gy) >= WALKABLE


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("level")
    ap.add_argument("foliage_bin")
    ap.add_argument("swap")
    ap.add_argument("out")
    ap.add_argument("--hulls", default="C:/haloce/ce_conversions/upgrade/hulls")
    ap.add_argument("--scene", help="the conversion's scene.gltf: the ground under the cliffs' cladding")
    ap.add_argument("--only", help="comma-separated kinds to keep: swap, foliage, cladding (default all)")
    ap.add_argument("--clad-limit", type=int, help="keep only this many cladding rocks, the biggest")
    a = ap.parse_args()
    os.makedirs(a.hulls, exist_ok=True)
    level = json.load(open(a.level, encoding="utf-8"))
    swap = json.load(open(a.swap, encoding="utf-8")) if os.path.exists(a.swap) else {"decor": []}
    tris, mats, counts = [], [], {}

    def place(mesh, matrix, scale, origin, material, points=HULL_POINTS):
        pts, faces = hull_of(mesh, a.hulls, points)
        world = (np.asarray(pts) * scale) @ matrix + origin
        ce = to_ce(world)
        # The hull is wound outward in Unreal's frame; to_ce mirrors Y, which
        # turns it inward (merge_ce_collision.py takes the plane from the
        # winding). The sim's projectile test accepts a two-sided surface only
        # from the side its plane faces (FUN_1802f0170, CU4), so an inward
        # hull stopped bullets on its far wall, from inside: shots went
        # "through" swapped rocks and trunks. Wind every face back outward,
        # a mirroring scale included.
        mirrored = np.linalg.det(np.diag(np.broadcast_to(np.asarray(scale, dtype=np.float64), (3,))) @ np.asarray(matrix)) * -1 < 0
        for f in faces:
            f = (f[0], f[2], f[1]) if mirrored else tuple(f)
            tris.append(ce[list(f)].round(4).tolist())
            mats.append(material)
        counts[material] = counts.get(material, 0) + 1

    kinds = set((a.only or "swap,foliage,cladding").split(","))
    skip = set()
    for item in swap.get("decor", []) if "swap" in kinds else []:
        ident = str(item.get("id", ""))
        if ident.startswith("swap_"):
            skip.add(int(ident.split("_")[1]))
        material = material_for(item["mesh"])
        if not material:
            continue
        r = item.get("rot", [0, 0, 0])
        place(item["mesh"], rotator_matrix(r[0], r[1], r[2]), np.asarray(item.get("scale", [1, 1, 1])),
              np.asarray(item["pos"]), material, TRUNK_POINTS if "_Trunk" in item["mesh"] else HULL_POINTS)

    # A level file's foliage, or scatter_foliage.py's own foliage.json.
    groups = (level.get("foliage") or level).get("groups") or []
    records = foliage_records(a.foliage_bin) if groups else []
    ground = Ground(a.scene) if a.scene else None
    clad = []
    for g, recs in zip(groups, records):
        if g.get("rule") == "cladding" and "cladding" not in kinds:
            continue
        if g.get("rule") != "cladding" and "foliage" not in kinds:
            continue
        if g.get("rule") == "cladding" and ground:
            pts, _faces = hull_of(g["mesh"], a.hulls, CLAD_POINTS)
            for x, y, z, yaw, scale, nx, ny, *_ in recs:
                s = scale / 100.0
                m = foliage_matrix(yaw * math.pi / 128.0, nx / 127.0, ny / 127.0)
                # Rocks at a cliff's foot have their origin inside the
                # cliff, with no ground below it: test under every hull
                # point, keeping the rock when any is within reach of
                # ground a player can stand on.
                world = (np.asarray(pts) * s) @ m + [x, y, z]
                if not any((h := ground.below(p[0], p[1], p[2])) is not None and p[2] - h <= CLAD_REACH
                           and ground.walkable(p[0], p[1], h) for p in world):
                    continue
                clad.append((s, g["mesh"], m, np.array([x, y, z])))
            continue
        floor = FOLIAGE_RULES.get(g.get("rule"))
        if floor is None:
            continue
        material = material_for(g["mesh"]) or "hard_terrain_stone"
        pts, _faces = hull_of(g["mesh"], a.hulls)
        height = float(pts[:, 2].max() - pts[:, 2].min())
        for x, y, z, yaw, scale, nx, ny, *_ in recs:
            s = scale / 100.0
            if height * s < floor:
                continue
            place(g["mesh"], foliage_matrix(yaw * math.pi / 128.0, nx / 127.0, ny / 127.0), s,
                  np.array([x, y, z]), material)

    # The cliffs' cladding last, biggest first: what fits the BSP's tables.
    clad.sort(key=lambda c: -c[0])
    for s, mesh, m, at in clad[:a.clad_limit] if a.clad_limit is not None else clad:
        place(mesh, m, s, at, "hard_terrain_stone", CLAD_POINTS)
    json.dump({"triangles": tris, "materials": mats, "skip_entries": sorted(skip), "objects": sum(counts.values())},
              open(a.out, "w", encoding="utf-8"))
    kept = len(clad) if a.clad_limit is None else min(len(clad), a.clad_limit)
    print(f"{len(tris)} collision triangle(s) for {sum(counts.values())} object(s) {counts}; "
          f"{len(skip)} CE placement(s) replaced; {kept} cladding rock(s) of {len(clad)}")


if __name__ == "__main__":
    main()
