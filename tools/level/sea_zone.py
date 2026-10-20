#!/usr/bin/env python3
"""The wading zone of a coast map: how far each spot of the sea lies from
land, and the wall that keeps players inside `--wade` metres of it.

    python tools/level/sea_zone.py <scene.gltf> <out dir> --sea Z [--wade 30] [--ignore tubes_ext,...]

CE's coast maps stand in a sea players can walk into: Yoyorast's floor is a
flat plane 1.5 m under the water, 3.2 km across, so a player could wade to
the horizon, while the upgraded seabed (build_landscape.py) shelves to deep
water a few metres out: they walked on an invisible floor over deep sea
(2026-10-16). One distance field serves both sides, so they agree: the
seabed keeps CE's own floor within `--wade` m of land and falls away beyond
(build_landscape.py --zone), and a wall on the `--wade` m line goes into the
map's collision (upgrade_ce_map.py stage_collision), only where CE has a
floor to stand on (Death Island's open sea has none; there, as in CE, a
player has nowhere to go).

Land is anything over the sea (not water or sky, nor `--ignore` shaders)
at least `--min-width` m across: Yoyorast's 1.3 km pipe across the sea,
70 cm wide, would have made a lane of shallows the length of the map. Writes zone.npz (dist m by cell, floor
z cm, land), zone.json (grid and extents) and wall.json (collision extras
in b30_collision.py's form: triangles in CE world units, materials).

With `--apron`, also `apron` in zone.npz: metres from the waterline of the
named structures (shader substrings), where build_landscape.py raises the
seabed into a shallow apron, as at the foot of a breakwater. Fluid Flux's
waves feel only shallow water: round a tower whose foot lay a metre under
the surface they slowed and calmed, while along Yoyorast's walls and
pillars, which drop to a seabed 25 m down, they ran on as if nothing stood
there (2026-10-16). By the waterline, not the raster: the walls are a
metre thick and the pillars hollow.
"""
import argparse
import json
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from refine_water_gltf import read_accessor  # noqa: E402
from build_landscape import raster  # noqa: E402

WU = 304.8  # cm per CE world unit
SKIP = ("water", "sky", "fog", "wave", "flare")
# The wall: from under CE's floor to this far over the sea (cm): over a
# player's jump, under the bridges and walkways that cross the line.
WALL_UNDER, WALL_OVER = 300.0, 600.0
WALL_MATERIAL = "hard_terrain_stone"


def scene_triangles(gltf, ignore):
    doc = json.load(open(gltf, encoding="utf-8"))
    data = open(os.path.join(os.path.dirname(os.path.abspath(gltf)), doc["buffers"][0]["uri"]), "rb").read()
    out = []
    for mesh in doc["meshes"]:
        for prim in mesh["primitives"]:
            name = doc["materials"][prim["material"]]["name"].lower()
            if any(w in name for w in SKIP) or any(w in name for w in ignore):
                continue
            pos = read_accessor(doc, data, prim["attributes"]["POSITION"]).astype(np.float64)
            pos = np.stack([pos[:, 0] * 100.0, pos[:, 2] * 100.0, pos[:, 1] * 100.0], 1)
            out.append(pos[read_accessor(doc, data, prim["indices"]).reshape(-1, 3)])
    return np.concatenate(out)


def waterline_cells(gltf, tokens, sea, origin, cell, side):
    """Cells the named shaders' surfaces cross the sea in."""
    doc = json.load(open(gltf, encoding="utf-8"))
    data = open(os.path.join(os.path.dirname(os.path.abspath(gltf)), doc["buffers"][0]["uri"]), "rb").read()
    mask = np.zeros((side, side), bool)
    for mesh in doc["meshes"]:
        for prim in mesh["primitives"]:
            if not any(t in doc["materials"][prim["material"]]["name"].lower() for t in tokens):
                continue
            pos = read_accessor(doc, data, prim["attributes"]["POSITION"]).astype(np.float64)
            pos = np.stack([pos[:, 0] * 100.0, pos[:, 2] * 100.0, pos[:, 1] * 100.0], 1)
            for t in pos[read_accessor(doc, data, prim["indices"]).reshape(-1, 3)]:
                z = t[:, 2] - sea
                if not (z.min() < 0 < z.max()):
                    continue
                ends = [t[i] + (t[j] - t[i]) * (z[i] / (z[i] - z[j]))
                        for i, j in ((0, 1), (1, 2), (2, 0)) if (z[i] < 0) != (z[j] < 0)]
                if len(ends) != 2:
                    continue
                k = max(2, int(np.linalg.norm(ends[1] - ends[0]) / (cell / 2)) + 1)
                for f in np.linspace(0.0, 1.0, k):
                    q = ends[0] + (ends[1] - ends[0]) * f
                    c, r = int((q[0] - origin[0]) / cell), int((q[1] - origin[1]) / cell)
                    if 0 <= r < side and 0 <= c < side:
                        mask[r, c] = True
    return mask


def opening(mask, k):
    """Morphological opening by a k x k square: features narrower than k
    cells go, the rest keeps its shape."""
    def shift_all(m, op):
        r = k // 2
        pm = np.pad(m, r, constant_values=(op is np.logical_and))
        out = None
        for dy in range(k):
            for dx in range(k):
                v = pm[dy:dy + m.shape[0], dx:dx + m.shape[1]]
                out = v if out is None else op(out, v)
        return out
    eroded = shift_all(mask, np.logical_and)
    return shift_all(eroded, np.logical_or) & mask


def distance(land, cell_m, reach_m):
    """Metres to the nearest land cell (8-neighbour steps), up to reach."""
    size_y, size_x = land.shape
    dist = np.where(land, 0.0, np.inf)
    for _ in range(int(math.ceil(reach_m / cell_m)) + 1):
        pd = np.pad(dist, 1, constant_values=np.inf)
        best = dist
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                if dy or dx:
                    step = cell_m * (math.sqrt(2.0) if dy and dx else 1.0)
                    best = np.minimum(best, pd[1 + dy:size_y + 1 + dy, 1 + dx:size_x + 1 + dx] + step)
        dist = best
    return dist


def contour(f):
    """Marching squares on f (by grid vertex) at 0: segments as pairs of
    (row, col) points, interpolated along the cells' edges."""
    segs = []
    a, b, c, d = f[:-1, :-1], f[:-1, 1:], f[1:, 1:], f[1:, :-1]  # corners: tl tr br bl
    idx = (a > 0) * 1 + (b > 0) * 2 + (c > 0) * 4 + (d > 0) * 8
    rows, cols = np.nonzero((idx > 0) & (idx < 15))

    def cross(p, q, fp, fq):
        t = fp / (fp - fq) if fp != fq else 0.5
        return (p[0] + (q[0] - p[0]) * t, p[1] + (q[1] - p[1]) * t)

    for r, k in zip(rows, cols):
        tl, tr, br, bl = (r, k), (r, k + 1), (r + 1, k + 1), (r + 1, k)
        v = {tl: f[tl], tr: f[tr], br: f[br], bl: f[bl]}
        edges = []
        for p, q in ((tl, tr), (tr, br), (br, bl), (bl, tl)):
            if (v[p] > 0) != (v[q] > 0):
                edges.append(cross(p, q, v[p], v[q]))
        if len(edges) == 2:
            segs.append((edges[0], edges[1]))
        elif len(edges) == 4:  # a saddle: pair them by the centre's sign
            if (v[tl] + v[tr] + v[br] + v[bl]) / 4 > 0:
                segs += [(edges[0], edges[1]), (edges[2], edges[3])]
            else:
                segs += [(edges[0], edges[3]), (edges[1], edges[2])]
    return segs


def chain(segs):
    """Segments joined end to end into polylines."""
    key = lambda p: (round(p[0], 4), round(p[1], 4))
    ends = {}
    for i, (p, q) in enumerate(segs):
        ends.setdefault(key(p), []).append((i, 0))
        ends.setdefault(key(q), []).append((i, 1))
    used = [False] * len(segs)
    lines = []
    for i in range(len(segs)):
        if used[i]:
            continue
        used[i] = True
        line = [segs[i][0], segs[i][1]]
        for forward in (True, False):
            while True:
                tip = line[-1] if forward else line[0]
                nxt = None
                for j, e in ends.get(key(tip), []):
                    if not used[j]:
                        nxt = (j, e)
                        break
                if not nxt:
                    break
                j, e = nxt
                used[j] = True
                other = segs[j][1 - e]
                if forward:
                    line.append(other)
                else:
                    line.insert(0, other)
        lines.append(line)
    return lines


def simplify(points, tol):
    """Douglas-Peucker, iterative."""
    pts = np.asarray(points)
    if len(pts) < 3:
        return pts
    keep = np.zeros(len(pts), bool)
    keep[[0, -1]] = True
    stack = [(0, len(pts) - 1)]
    while stack:
        i, j = stack.pop()
        if j <= i + 1:
            continue
        a, b = pts[i], pts[j]
        ab = b - a
        n = np.hypot(*ab)
        seg = pts[i + 1:j]
        if n < 1e-9:
            dd = np.hypot(*(seg - a).T)
        else:
            dd = np.abs(ab[0] * (seg[:, 1] - a[1]) - ab[1] * (seg[:, 0] - a[0])) / n
        k = int(np.argmax(dd))
        if dd[k] > tol:
            keep[i + 1 + k] = True
            stack += [(i, i + 1 + k), (i + 1 + k, j)]
    return pts[keep]


def to_ce(p):
    q = np.asarray(p, dtype=np.float64) / WU
    return [float(q[0]), float(-q[1]), float(q[2])]


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("gltf")
    ap.add_argument("out")
    ap.add_argument("--sea", type=float, required=True, help="sea level (cm)")
    ap.add_argument("--wade", type=float, default=30.0, help="m from land players may wade")
    ap.add_argument("--reach", type=float, default=150.0, help="m of sea the field covers past land")
    ap.add_argument("--cell", type=float, default=100.0, help="cm a cell")
    ap.add_argument("--ignore", default="", help="shader name substrings that are not land, comma-separated")
    ap.add_argument("--min-width", type=float, default=3.0, help="m: narrower land is not land (a pipe, a railing)")
    ap.add_argument("--tolerance", type=float, default=50.0, help="cm the wall may stray from the line")
    ap.add_argument("--apron", default="", help="shader name substrings of structures standing in the sea, "
                                                "comma-separated: their apron field (m from their waterline)")
    ap.add_argument("--apron-reach", type=float, default=60.0, help="m the apron field covers")
    a = ap.parse_args()
    ignore = [t.lower() for t in a.ignore.split(",") if t]
    tris = scene_triangles(a.gltf, ignore)
    over = tris[tris[..., 2].max(1) >= a.sea]
    lo, hi = over[..., :2].min((0, 1)), over[..., :2].max((0, 1))
    pad = a.reach * 100.0
    origin = lo - pad
    size = (np.ceil((hi - lo + 2 * pad) / a.cell)).astype(int) + 1
    side = int(size.max())
    near = tris[(tris[..., :2].max(1) >= origin).all(1) & (tris[..., :2].min(1) <= origin + side * a.cell).all(1)]
    top, _ = raster(near, origin, a.cell, side, [], highest=True)
    low, _ = raster(near, origin, a.cell, side, [])
    land = np.isfinite(top) & (top >= a.sea)
    # Land narrower than --min-width is not land: a pipe, a railing.
    k = max(1, int(round(a.min_width * 100.0 / a.cell)))
    if k > 1:
        land = opening(land, k)
    floor = np.where(np.isfinite(low) & (low < a.sea), low, np.nan)
    dist = distance(land, a.cell / 100.0, a.reach)
    os.makedirs(a.out, exist_ok=True)
    extra = {}
    tokens = [t.lower() for t in a.apron.split(",") if t]
    if tokens:
        struct = waterline_cells(a.gltf, tokens, a.sea, origin, a.cell, side)
        apron = distance(struct, a.cell / 100.0, a.apron_reach)
        extra["apron"] = np.where(np.isfinite(apron), apron, 1e6).astype(np.float32)
        print(f"apron: {int(struct.sum())} waterline cell(s) on {a.apron}")
    np.savez_compressed(os.path.join(a.out, "zone.npz"), dist=dist.astype(np.float32), floor=floor.astype(np.float32),
                        land=land, **extra)
    ys, xs = np.nonzero(land)
    land_rect = [float(origin[0] + xs.min() * a.cell), float(origin[1] + ys.min() * a.cell),
                 float(origin[0] + xs.max() * a.cell), float(origin[1] + ys.max() * a.cell)]
    meta = {"origin": origin.tolist(), "cell": a.cell, "size": side, "sea": a.sea, "wade": a.wade,
            "land_rect": land_rect}
    json.dump(meta, open(os.path.join(a.out, "zone.json"), "w"), indent=1)

    # The wall on the wade line, where a floor runs on past it.
    f = np.where(np.isfinite(dist), dist, 1e6) - a.wade
    tris_out, length, kept = [], 0.0, 0
    for line in chain(contour(f)):
        pts = np.asarray(line)
        # (row, col) to cm.
        xy = np.stack([origin[0] + pts[:, 1] * a.cell, origin[1] + pts[:, 0] * a.cell], 1)
        # A run only where CE has a floor just outside the line.
        r = np.clip(np.round(pts[:, 0]).astype(int), 0, side - 1)
        c = np.clip(np.round(pts[:, 1]).astype(int), 0, side - 1)
        has = np.isfinite(floor[r, c])
        runs, start = [], None
        for i, h in enumerate(has):
            if h and start is None:
                start = i
            if (not h or i == len(has) - 1) and start is not None:
                end = i if h else i - 1
                if end > start:
                    runs.append((start, end))
                start = None
        for s, e in runs:
            sub = simplify(xy[s:e + 1], a.tolerance)
            zfl = floor[r[s:e + 1], c[s:e + 1]]
            bottom = float(np.nanmin(zfl)) - WALL_UNDER
            top_z = a.sea + WALL_OVER
            for p, q in zip(sub[:-1], sub[1:]):
                length += float(np.hypot(*(q - p)))
                A, B = [p[0], p[1], bottom], [q[0], q[1], bottom]
                C, D = [q[0], q[1], top_z], [p[0], p[1], top_z]
                tris_out += [[to_ce(A), to_ce(B), to_ce(C)], [to_ce(A), to_ce(C), to_ce(D)]]
            kept += 1
    json.dump({"triangles": tris_out, "materials": [WALL_MATERIAL] * len(tris_out)},
              open(os.path.join(a.out, "wall.json"), "w"))
    wading = np.isfinite(floor) & (dist <= a.wade) & ~land
    print(f"sea zone: {int(land.sum())} land cells, {int(wading.sum() * (a.cell / 100) ** 2)} m2 of wading sea; "
          f"wall {length / 100:.0f} m in {kept} run(s), {len(tris_out)} triangles")


if __name__ == "__main__":
    main()
