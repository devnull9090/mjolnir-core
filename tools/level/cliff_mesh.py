"""A converted map's cliffs as one mesh for Nanite tessellation.

    python tools/level/cliff_mesh.py <level.json> <scene.gltf> <out.json> [--landscape landscape.json]
    python tools/level/cliff_mesh.py <level.json> <scene.gltf> <out.json> --parent M_CE_Plasma

With --parent, the slots on that master instead, as they are (no welding,
splitting or fade): translucent surfaces a conversion left on the opaque
terrain mesh, which can draw no translucency (Yoyorast's plasma beams), as
a mesh of their own (MJOLNIRLevelLoader level.slot_meshes).

CE's cliffs are slots of the map's terrain mesh (SM_<CODE>_Terrain, a
classic mesh), the slots whose detail map is one of level.landscape.cliff's
`details` (or build_landscape.py's landscape.json's). Nanite tessellation needs a Nanite mesh, so this takes those
slots' triangles from the conversion's scene.gltf (terrain slot i is the
glTF's material i - 1, checked by lightmap page) and writes them in Unreal
centimetres, one section a slot, for Scripts/build_ce_cliffs.py to build.

Displacement moves a vertex along its normal, so every corner at one
position gets one normal (area-weighted over the faces there): CE's BSP
splits vertices per plane, and per-face normals would open a crack along
every edge. The cliffs' outer border (edges one cliff triangle
uses) is where they meet the ground mesh or the landscape, which do not
move: each vertex's colour is its distance from it over FADE, 0 on it, and
the material fades displacement by it. Shading keeps CE's own normals
(`shade`, a corner each, into UV2 and UV3): with the welded ones its
triplanar rock smeared across every crease and the ledge test drew turf
along ridges (Yoyorast, 2026-10-13). Vertex colours interpolate across a
triangle, and CE's cliff triangles span tens of metres, a wall often one
strip with every corner on the border, so the mesh is first split until no
edge is over SPLIT (bisecting the longest edges, both triangles at an edge
at its one midpoint, so it stays welded).
"""
import argparse
import heapq
import json
import os
import re
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
WELD = 0.1  # cm: corners closer than this are one vertex
SPLIT = 400.0  # cm: the longest edge left after subdivision
FADE = 250.0  # cm from the border to full displacement


def page_of(name):
    """A slot's lightmap page: glTF `__lmK`, texture `..._nK` (page 0 bare)."""
    m = re.search(r"__lm(\d+)$", name or "")
    return int(m.group(1)) if m else None


def texture_page(path):
    leaf = (path or "").split(".")[-1]
    m = re.search(r"_n(\d+)$", leaf)
    # A protected map's page 0 is its bitmap's own number (T_protected_bitm_n2943;
    # page 2 is T_protected_bitm_2943_n2): no map has a hundred pages.
    return int(m.group(1)) if m and int(m.group(1)) < 100 else 0


def subdivide(verts, tris, uv0, uv1, section, longest, shade):
    """Bisect edges longer than `longest`, longest first. Both triangles at
    an edge split at its one midpoint (the mesh stays welded); each corner's
    UVs are its triangle's own, the midpoint's the mean of the edge's ends."""
    verts = [tuple(v) for v in verts]
    tris = [list(t) for t in tris.tolist()]
    uv0 = [list(map(tuple, t)) for t in uv0.tolist()]
    uv1 = [list(map(tuple, t)) for t in uv1.tolist()]
    shade = [list(map(tuple, t)) for t in shade.tolist()]
    section = list(section)
    at = {}  # edge -> triangles

    def key(a, b):
        return (a, b) if a < b else (b, a)

    def length(e):
        a, b = verts[e[0]], verts[e[1]]
        return ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 + (a[2] - b[2]) ** 2) ** 0.5

    heap = []

    def add(t):
        for k in range(3):
            e = key(tris[t][k], tris[t][(k + 1) % 3])
            at.setdefault(e, set()).add(t)
            n = length(e)
            if n > longest:
                heapq.heappush(heap, (-n, e))

    for t in range(len(tris)):
        add(t)
    while heap:
        _, e = heapq.heappop(heap)
        users = at.get(e)
        if not users:
            continue  # already split
        a, b = e
        m = len(verts)
        verts.append(tuple((verts[a][k] + verts[b][k]) / 2.0 for k in range(3)))
        del at[e]
        for t in list(users):
            tri = tris[t]
            ia, ib = tri.index(a), tri.index(b)
            ic = 3 - ia - ib
            c = tri[ic]
            mid0 = tuple((uv0[t][ia][k] + uv0[t][ib][k]) / 2.0 for k in range(2))
            mid1 = tuple((uv1[t][ia][k] + uv1[t][ib][k]) / 2.0 for k in range(2))
            mids = tuple((shade[t][ia][k] + shade[t][ib][k]) / 2.0 for k in range(3))
            for k in range(3):
                at.get(key(tri[k], tri[(k + 1) % 3]), set()).discard(t)
            # Keep the winding: replace b by m in this triangle, and add one
            # with a replaced by m.
            new_tri, new_u0, new_u1, new_sh = list(tri), list(uv0[t]), list(uv1[t]), list(shade[t])
            tri[ib], uv0[t][ib], uv1[t][ib], shade[t][ib] = m, mid0, mid1, mids
            new_tri[ia], new_u0[ia], new_u1[ia], new_sh[ia] = m, mid0, mid1, mids
            tris.append(new_tri)
            uv0.append(new_u0)
            uv1.append(new_u1)
            shade.append(new_sh)
            section.append(section[t])
            add(t)
            add(len(tris) - 1)
    return (np.array(verts), np.array(tris), np.array(uv0), np.array(uv1), np.array(section), np.array(shade))


def conformal_uv(corners, uv, section, unit):
    """New texture coordinates for the cliff triangles (corners, 3 a
    triangle), evenly scaled: CE's cliff UVs stretch a wall's strip of rock
    13 times further along than up in places (Sidewinder, 2026-10-14), which
    no one tiling undoes. Each of CE's own charts (triangles joined by
    corners that share position and UV) is flattened again by least squares
    conformal maps (no stretch, only a scale that varies slowly), turned so
    its "down" is the world's (v grows downward, as CE's did), mirrored to
    CE's handedness and scaled to `unit` cm a UV unit."""
    n = len(corners) // 3
    key = {}
    vid = np.array([key.setdefault((tuple(np.round(corners[i], 1)), tuple(np.round(uv[i], 5)), int(section[i // 3])),
                                   len(key)) for i in range(len(corners))])
    tris = vid.reshape(-1, 3)
    pos = np.zeros((len(key), 3))
    pos[vid] = corners
    # Charts: triangles joined across shared edges.
    parent = list(range(n))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    seen = {}
    for t, tri in enumerate(tris):
        for k in range(3):
            e = (min(tri[k], tri[(k + 1) % 3]), max(tri[k], tri[(k + 1) % 3]))
            if e in seen:
                parent[find(t)] = find(seen[e])
            else:
                seen[e] = t
    charts = {}
    for t in range(n):
        charts.setdefault(find(t), []).append(t)
    out = np.array(uv, dtype=np.float64)
    for ts in charts.values():
        ts = np.array(ts)
        verts = np.unique(tris[ts])
        local = {v: i for i, v in enumerate(verts)}
        T = np.array([[local[v] for v in tri] for tri in tris[ts]])
        P = pos[verts]
        m = len(verts)
        if m < 3:
            continue
        # Each triangle in its own plane: the conformality condition's rows.
        a_, b_, c_ = P[T[:, 0]], P[T[:, 1]], P[T[:, 2]]
        e1, e2 = b_ - a_, c_ - a_
        l1 = np.maximum(np.linalg.norm(e1, axis=1), 1e-9)
        xa = e1 / l1[:, None]
        nrm = np.cross(e1, e2)
        area = np.linalg.norm(nrm, axis=1) / 2
        ok = area > 1e-6
        ya = np.cross(nrm / np.maximum(2 * area, 1e-12)[:, None], xa)
        X = np.stack([np.zeros(len(T)), l1, (e2 * xa).sum(1)], 1)
        Y = np.stack([np.zeros(len(T)), np.zeros(len(T)), (e2 * ya).sum(1)], 1)
        sc = 1.0 / np.sqrt(np.maximum(2 * area, 1e-12))
        rows, cols, vals = [], [], []
        r = 0
        for t in np.where(ok)[0]:
            for j in range(3):
                j1, j2 = (j + 1) % 3, (j + 2) % 3
                wr, wi = (X[t, j2] - X[t, j1]) * sc[t], (Y[t, j2] - Y[t, j1]) * sc[t]
                v = T[t, j]
                rows += [r, r, r + 1, r + 1]
                cols += [v, m + v, v, m + v]
                vals += [wr, -wi, wi, wr]
            r += 2
        rows, cols, vals = np.array(rows), np.array(cols), np.array(vals)
        # Pins: the chart's two farthest-apart corners, at their own distance.
        i1 = int(np.argmax(np.linalg.norm(P - P[0], axis=1)))
        i0 = int(np.argmax(np.linalg.norm(P - P[i1], axis=1)))
        x = np.zeros(2 * m)
        x[i1] = np.linalg.norm(P[i1] - P[i0])
        pinned = np.zeros(2 * m, bool)
        pinned[[i0, i1, m + i0, m + i1]] = True

        def A(z):
            return np.bincount(rows, weights=vals * z[cols], minlength=r)

        def At(y):
            return np.bincount(cols, weights=vals * y[rows], minlength=2 * m)
        # Conjugate gradients on the normal equations, over the free unknowns.
        rhs = -At(A(np.where(pinned, x, 0.0)))
        rhs[pinned] = 0
        z = np.zeros(2 * m)
        res = rhs.copy()
        d = res.copy()
        rr = res @ res
        stop = 1e-20 * max(rr, 1e-30)
        for _ in range(20 * m):
            q = At(A(d))
            q[pinned] = 0
            alpha = rr / max(d @ q, 1e-30)
            z += alpha * d
            res -= alpha * q
            rr2 = res @ res
            if rr2 < stop:
                break
            d = res + (rr2 / rr) * d
            rr = rr2
        x = np.where(pinned, x, z)
        U = np.stack([x[:m], x[m:]], 1)
        # World down as v, CE's handedness, `unit` cm a UV unit.
        g = np.zeros(2)
        hand = 0.0
        for t in np.where(ok)[0]:
            tri3, tri2 = P[T[t]], U[T[t]]
            d1, d2 = tri2[1] - tri2[0], tri2[2] - tri2[0]
            det = d1[0] * d2[1] - d1[1] * d2[0]
            if abs(det) < 1e-12:
                continue
            q1, q2 = tri3[1] - tri3[0], tri3[2] - tri3[0]
            # dz/du, dz/dv on the triangle, weighted by its area.
            g += area[t] * np.array([(q1[2] * d2[1] - q2[2] * d1[1]) / det, (q2[2] * d1[0] - q1[2] * d2[0]) / det])
            ce = uv[3 * ts[t]:3 * ts[t] + 3]
            c1, c2 = ce[1] - ce[0], ce[2] - ce[0]
            hand += area[t] * np.sign(det) * np.sign(c1[0] * c2[1] - c1[1] * c2[0])
        if hand < 0:
            U[:, 0] *= -1
            g[0] *= -1
        if np.linalg.norm(g) > 1e-9:
            # Turn the chart so z grows towards -v.
            ang = np.arctan2(-1.0, 0.0) - np.arctan2(g[1], g[0])
            c, s_ = np.cos(ang), np.sin(ang)
            U = U @ np.array([[c, s_], [-s_, c]])
        area_uv = 0.0
        for t in np.where(ok)[0]:
            d1, d2 = U[T[t, 1]] - U[T[t, 0]], U[T[t, 2]] - U[T[t, 0]]
            area_uv += abs(d1[0] * d2[1] - d1[1] * d2[0]) / 2
        U *= np.sqrt(area[ok].sum() / max(area_uv, 1e-12)) / unit
        for k, t in enumerate(ts):
            out[3 * t:3 * t + 3] = U[T[k]]
    return out, len(charts)


def border_fade(verts, border_edges, fade):
    """Each vertex's distance from the border edges over `fade`, clamped to
    1, by a grid of points along them (a quarter of `fade` apart)."""
    pts = []
    for a, b in border_edges:
        pa, pb = verts[a], verts[b]
        n = max(1, int(np.ceil(np.linalg.norm(pb - pa) / (fade / 4.0))))
        for k in range(n + 1):
            pts.append(pa + (pb - pa) * (k / n))
    pts = np.array(pts) if pts else np.zeros((0, 3))
    cell = fade
    grid = {}
    for i, c in enumerate(np.floor(pts / cell).astype(int)):
        grid.setdefault(tuple(c), []).append(i)
    out = np.ones(len(verts))
    for i, v in enumerate(verts):
        c = np.floor(v / cell).astype(int)
        near = [j for dx in (-1, 0, 1) for dy in (-1, 0, 1) for dz in (-1, 0, 1)
                for j in grid.get((c[0] + dx, c[1] + dy, c[2] + dz), ())]
        if near:
            out[i] = min(1.0, float(np.min(np.linalg.norm(pts[near] - v, axis=1))) / fade)
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("level")
    ap.add_argument("scene")
    ap.add_argument("out")
    ap.add_argument("--landscape", help="build_landscape.py's landscape.json, for the cliff details")
    ap.add_argument("--parent", help="take the slots on this master as they are (see above)")
    ap.add_argument("--item", default="_terrain",
                    help="the decor item whose slots these are, by the end of its id (the translucent mesh: _terrain_1)")
    ap.add_argument("--slot-offset", type=int, default=1,
                    help="a slot's glTF material is slot - this: 1 on the terrain mesh (slot 0 the fallback), "
                         "0 on the translucent one (build_terrain_meshes.py)")
    ap.add_argument("--texture", default="", help="with --parent: only slots with a texture whose path holds this")
    ap.add_argument("--material", help="with --parent: the built mesh's material (an object path), else the parent's")
    ap.add_argument("--flat", action="store_true",
                    help="the cliff triangles as CE has them (its own normals, no welding or subdivision): "
                         "a copy only to carry --conformal UVs, with no displacement")
    ap.add_argument("--conformal", type=float, default=0.0, metavar="CM",
                    help="new UVs, evenly scaled, CM cm a UV unit (conformal_uv)")
    ap.add_argument("--swap", help="scenery_swap.py's swap.json: its hidden slots are not cliffs (CE boulders "
                                   "baked into the terrain, which B30's own replace)")
    a = ap.parse_args()
    sys.path.insert(0, HERE)
    from refine_water_gltf import read_accessor

    level = json.load(open(a.level, encoding="utf-8"))
    land = json.load(open(a.landscape, encoding="utf-8")) if a.landscape else level.get("landscape") or {}
    details = set((land.get("cliff") or {}).get("details") or [])
    terrain = next(i for i in level["decor"] if str(i.get("id", "")).endswith(a.item))
    doc = json.load(open(a.scene, encoding="utf-8"))
    data = open(os.path.join(os.path.dirname(a.scene), doc["buffers"][0]["uri"]), "rb").read()
    names = [m.get("name") for m in doc["materials"]]

    hide = json.load(open(a.swap, encoding="utf-8")).get("hide", []) if a.swap and os.path.exists(a.swap) else []
    slots = []
    for i, m in enumerate(terrain.get("materials") or []):
        if m in hide:
            continue
        g = i - a.slot_offset
        name = names[g] if 0 <= g < len(names) else None
        if a.parent:
            if isinstance(m, dict) and (m.get("parent") or "").endswith("." + a.parent)                     and a.texture.lower() in json.dumps(m.get("textures") or {}).lower():
                slots.append((i, g, name))
            continue
        t = m.get("textures") if isinstance(m, dict) else None
        # cliff.slots (build_landscape.py --cliff-shaders) names the slots
        # exactly; else a slot is a cliff by its primary detail map.
        exact = (land.get("cliff") or {}).get("slots")
        if not t or (i not in exact if exact else (t.get("Primary") or "").split(".")[-1] not in details):
            continue
        lm = t.get("Lightmap") or ""
        if "object_lighting" not in lm and page_of(name) != texture_page(lm):
            sys.exit(f"terrain slot {i}: glTF material {name} is not on the slot's lightmap page {lm}")
        slots.append((i, g, name))
    if not slots:
        sys.exit("no slots on " + a.parent if a.parent else "no cliff slots")

    # Corners of every cliff triangle, Unreal cm: glTF (x, y, z) m -> (x, z, y) * 100.
    pos, nrm, uv0, uv1, section = [], [], [], [], []
    for p in [q for mesh in doc["meshes"] for q in mesh["primitives"]]:
        k = next((s for s, (_, g, _) in enumerate(slots) if g == p["material"]), None)
        if k is None:
            continue
        att = p["attributes"]
        P = read_accessor(doc, data, att["POSITION"]).astype(np.float64)[:, [0, 2, 1]] * 100.0
        N = read_accessor(doc, data, att["NORMAL"]).astype(np.float64)[:, [0, 2, 1]]
        T0 = read_accessor(doc, data, att["TEXCOORD_0"]).astype(np.float64)
        T1 = read_accessor(doc, data, att["TEXCOORD_1"]).astype(np.float64)
        idx = read_accessor(doc, data, p["indices"]).reshape(-1, 3).astype(np.int64)
        # The axis swap mirrors the mesh: keep the face whose winding (UE:
        # (c - a) x (b - a)) agrees with the exported normals.
        a_, b_, c_ = P[idx[:, 0]], P[idx[:, 1]], P[idx[:, 2]]
        face = np.cross(c_ - a_, b_ - a_)
        flip = (face * (N[idx[:, 0]] + N[idx[:, 1]] + N[idx[:, 2]])).sum(1) < 0
        idx[flip] = idx[flip][:, [0, 2, 1]]
        pos.append(P[idx].reshape(-1, 3))
        nrm.append(N[idx].reshape(-1, 3))
        # (After the flip: N is per vertex, so the corners keep their own.)
        uv0.append(T0[idx].reshape(-1, 2))
        uv1.append(T1[idx].reshape(-1, 2))
        section += [k] * len(idx)
    corners = np.concatenate(pos)
    uv0, uv1 = np.concatenate(uv0), np.concatenate(uv1)
    shade = np.concatenate(nrm)
    if a.conformal > 0:
        uv0, nc = conformal_uv(corners, uv0, np.asarray(section), a.conformal)
        print(f"conformal UVs on {nc} chart(s), {a.conformal:g} cm a unit")
    if a.flat:
        # Corners that agree in everything share a vertex, and the copy is a
        # classic mesh: as Nanite, loose triangles simplified apart and a
        # hairline of lit snow showed through between them (Sidewinder,
        # 2026-10-14).
        key = {}
        attrs = np.concatenate([corners.round(2), uv0.round(5), uv1.round(5), shade.round(4)], 1)
        index = np.array([key.setdefault(tuple(r), len(key)) for r in attrs])
        first = np.zeros(len(key), dtype=np.int64)
        first[index[::-1]] = np.arange(len(index))[::-1]
        out = {
            "item": terrain["id"], "slots": [s for s, _, _ in slots], "names": [n for _, _, n in slots],
            # Positions, normals and weights a vertex; UVs and shade a corner
            # (as the welded path writes them).
            "positions": corners[first].round(3).tolist(), "normals": shade[first].round(5).tolist(),
            "indices": index.tolist(), "uv0": uv0.round(6).tolist(), "uv1": uv1.round(6).tolist(),
            "shade": shade.round(5).tolist(), "sections": list(section), "weight": [0.0] * len(first),
            "nanite": False,
        }
        json.dump(out, open(a.out, "w", encoding="utf-8"))
        print(f"{len(corners) // 3} cliff triangle(s), flat, from {len(slots)} slot(s) {[s for s, _, _ in slots]}")
        return

    if a.parent:
        out = {
            "item": terrain["id"], "slots": [s for s, _, _ in slots], "names": [n for _, _, n in slots],
            "positions": corners.round(3).tolist(), "normals": shade.round(5).tolist(),
            "indices": list(range(len(corners))), "uv0": uv0.round(6).tolist(), "uv1": uv1.round(6).tolist(),
            "sections": list(section), "weight": [1.0] * len(corners), "nanite": False,
            "material": a.material or a.parent,
        }
        json.dump(out, open(a.out, "w", encoding="utf-8"))
        print(f"{len(corners) // 3} triangle(s) on {a.parent} from {len(slots)} slot(s) {[s for s, _, _ in slots]}")
        return

    # Weld by position.
    key = np.round(corners / WELD).astype(np.int64)
    _, first, inverse = np.unique(key, axis=0, return_index=True, return_inverse=True)
    inverse = inverse.reshape(-1)
    verts = corners[first]
    tris = inverse.reshape(-1, 3)
    keep = (tris[:, 0] != tris[:, 1]) & (tris[:, 1] != tris[:, 2]) & (tris[:, 0] != tris[:, 2])
    tris, section = tris[keep], np.asarray(section)[keep]
    uv0, uv1 = uv0.reshape(-1, 3, 2)[keep], uv1.reshape(-1, 3, 2)[keep]
    shade = shade.reshape(-1, 3, 3)[keep]

    # Border first, on the welded mesh as CE has it.
    edges = np.sort(np.concatenate([tris[:, [0, 1]], tris[:, [1, 2]], tris[:, [2, 0]]]), axis=1)
    uniq, counts = np.unique(edges, axis=0, return_counts=True)
    border_edges = uniq[counts == 1]

    verts, tris, uv0, uv1, section, shade = subdivide(verts, tris, uv0, uv1, section, SPLIT, shade)

    # Area-weighted normals per welded vertex (the face cross product's length).
    a_, b_, c_ = verts[tris[:, 0]], verts[tris[:, 1]], verts[tris[:, 2]]
    face = np.cross(c_ - a_, b_ - a_)
    normals = np.zeros_like(verts)
    for k in range(3):
        np.add.at(normals, tris[:, k], face)
    normals /= np.maximum(np.linalg.norm(normals, axis=1, keepdims=True), 1e-9)

    weight = border_fade(verts, border_edges, FADE)

    out = {
        "item": terrain["id"],
        "slots": [s for s, _, _ in slots],
        "names": [n for _, _, n in slots],
        "positions": verts.round(3).tolist(),
        "normals": normals.round(5).tolist(),
        "indices": tris.reshape(-1).tolist(),
        "uv0": uv0.reshape(-1, 2).round(6).tolist(),
        "uv1": uv1.reshape(-1, 2).round(6).tolist(),
        "shade": shade.reshape(-1, 3).round(5).tolist(),
        "sections": section.tolist(),
        "weight": weight.round(3).tolist(),
    }
    json.dump(out, open(a.out, "w", encoding="utf-8"))
    lo, hi = verts.min(0), verts.max(0)
    print(f"{len(tris)} cliff triangle(s), {len(verts)} vertices ({int((weight == 0).sum())} on the border) "
          f"from {len(slots)} slot(s) {[s for s, _, _ in slots]}; bounds {lo.round()} .. {hi.round()}")


if __name__ == "__main__":
    main()
