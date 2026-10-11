#!/usr/bin/env python3
"""Refine a converted map's water glTF into triangles small enough to carry
waves: the game's ocean (Fluid Flux, MJOLNIRLevelLoader `mjolnir_water`)
shapes its surface per vertex, and CE's water is a few huge triangles (Death
Island's near water: 40 of them, edges up to 443 m), on which the waves
average out to a flat sheet.

    refine_water_gltf.py <in.gltf> <out.gltf> [--near 4] [--growth 0.08]
        [--center x,z --radius r | --placement <staging>/placement.json]

Longest-edge bisection (Rivara): a triangle whose longest edge is longer
than the target splits that edge at its middle, and so does the triangle
across it, first refining that neighbour until the shared edge is its
longest too. Every split is shared by both sides, so the mesh never has a
T-junction, and a crack between two sections would open as soon as the
waves moved the vertices. Sections (primitives) are refined together:
their vertices are matched by position, so an edge two sections share is
split once for both.

The target edge length is `--near` metres within `--radius` of `--center`
(the playable area; by default the middle of the water, radius 0) and grows by
`--growth` metres per metre beyond it, so the sea near the map is dense and
the distant ring stays cheap. glTF units are metres, y up.

Every attribute is interpolated at the midpoint (normals and tangents
renormalized, the tangent's handedness kept), and the output gets a buffer
of its own.
"""
import argparse
import json
import math
import os
import sys

import numpy as np

FLOAT = 5126
COMPONENTS = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4}


def read_accessor(doc, data, index):
    a = doc["accessors"][index]
    view = doc["bufferViews"][a["bufferView"]]
    k = COMPONENTS[a["type"]]
    dtype = {FLOAT: np.float32, 5125: np.uint32, 5123: np.uint16, 5121: np.uint8}[a["componentType"]]
    itemsize = np.dtype(dtype).itemsize
    stride = view.get("byteStride") or itemsize * k
    start = view.get("byteOffset", 0) + a.get("byteOffset", 0)
    raw = np.frombuffer(data, dtype=np.uint8, count=stride * (a["count"] - 1) + itemsize * k, offset=start)
    rows = np.lib.stride_tricks.as_strided(raw, shape=(a["count"], itemsize * k), strides=(stride, 1))
    return np.ascontiguousarray(rows).view(dtype).reshape(a["count"], k)


class Section:
    """One primitive: its attribute arrays (grown as edges split) and its
    triangles as local vertex indices."""

    def __init__(self, names, arrays):
        self.names = names
        self.columns = {n: [row for row in arrays[n].astype(np.float64)] for n in names}
        self.midpoints = {}

    def vertex_count(self):
        return len(self.columns["POSITION"])

    def midpoint(self, key, a, b, position):
        """The local vertex halfway along the global edge `key`, made once."""
        got = self.midpoints.get(key)
        if got is not None:
            return got
        for n in self.names:
            col = self.columns[n]
            v = (col[a] + col[b]) * 0.5
            if n == "POSITION":
                v = position.copy()
            elif n == "NORMAL":
                v = v / (np.linalg.norm(v) or 1.0)
            elif n == "TANGENT":
                xyz = v[:3] / (np.linalg.norm(v[:3]) or 1.0)
                v = np.concatenate([xyz, col[a][3:4]])
            col.append(v)
        self.midpoints[key] = self.vertex_count() - 1
        return self.midpoints[key]


def refine(doc, data, near, growth, center, radius):
    mesh_sections = []  # (mesh index, primitive index, Section)
    positions = {}      # rounded position -> global id
    global_pos = []     # global id -> position (float64, exact)
    tris = []           # [section index, (l0, l1, l2), (g0, g1, g2)] or None once split
    for mi, mesh in enumerate(doc["meshes"]):
        for pi, prim in enumerate(mesh["primitives"]):
            names = list(prim["attributes"].keys())
            arrays = {n: read_accessor(doc, data, prim["attributes"][n]) for n in names}
            if any(doc["accessors"][prim["attributes"][n]]["componentType"] != FLOAT for n in names):
                sys.exit(f"mesh {mi} primitive {pi}: only float attributes are interpolated")
            sec = Section(names, arrays)
            gid = []
            for p in arrays["POSITION"].astype(np.float64):
                key = tuple(np.round(p, 4))
                if key not in positions:
                    positions[key] = len(global_pos)
                    global_pos.append(p)
                gid.append(positions[key])
            sec.gid = gid
            si = len(mesh_sections)
            mesh_sections.append((mi, pi, sec))
            idx = read_accessor(doc, data, prim["indices"]).reshape(-1)
            for t in range(0, len(idx), 3):
                local = (int(idx[t]), int(idx[t + 1]), int(idx[t + 2]))
                glob = tuple(gid[v] for v in local)
                if len(set(glob)) == 3:
                    tris.append([si, local, glob])

    allp = np.array(global_pos)
    if center is None:
        # No playable area given: the water's middle, growing from there.
        lo, hi = allp.min(axis=0), allp.max(axis=0)
        center = ((lo[0] + hi[0]) / 2, (lo[2] + hi[2]) / 2)
    radius = radius or 0.0

    def target(p):
        d = math.hypot(p[0] - center[0], p[2] - center[1])
        return near + growth * max(0.0, d - radius)

    def edge_key(a, b):
        return (a, b) if a < b else (b, a)

    def length(key):
        return float(np.linalg.norm(global_pos[key[0]] - global_pos[key[1]]))

    # Edge -> live triangles holding it; longest edge with a fixed tie-break,
    # which bisection needs to terminate.
    by_edge = {}

    def edges_of(t):
        g = tris[t][2]
        return [edge_key(g[0], g[1]), edge_key(g[1], g[2]), edge_key(g[2], g[0])]

    def longest(t):
        return max(edges_of(t), key=lambda k: (length(k), k))

    def add(t):
        for k in edges_of(t):
            by_edge.setdefault(k, set()).add(t)

    def remove(t):
        for k in edges_of(t):
            by_edge[k].discard(t)
        tris[t] = None

    for t in range(len(tris)):
        add(t)

    def too_long(t):
        k = longest(t)
        mid = (global_pos[k[0]] + global_pos[k[1]]) * 0.5
        return length(k) > target(mid)

    def split_edge(k):
        """Split every live triangle on edge k at its midpoint, keeping
        winding; returns the new triangles."""
        a, b = k
        mid_pos = (global_pos[a] + global_pos[b]) * 0.5
        global_pos.append(mid_pos)
        m = len(global_pos) - 1
        made = []
        for t in list(by_edge.get(k, ())):
            si, local, glob = tris[t]
            sec = mesh_sections[si][2]
            # Rotate so the split edge is (0, 1): its winding is kept.
            r = next(i for i in range(3) if edge_key(glob[i], glob[(i + 1) % 3]) == k)
            gl = [glob[(r + i) % 3] for i in range(3)]
            lo = [local[(r + i) % 3] for i in range(3)]
            lm = sec.midpoint(k, lo[0], lo[1], mid_pos)
            remove(t)
            for new_local, new_glob in (((lo[0], lm, lo[2]), (gl[0], m, gl[2])),
                                        ((lm, lo[1], lo[2]), (m, gl[1], gl[2]))):
                tris.append([si, new_local, new_glob])
                add(len(tris) - 1)
                made.append(len(tris) - 1)
        return made

    def refine_triangle(t):
        """Bisect t's longest edge, first refining the neighbour across it
        until that edge is its longest too (the longest-edge propagation
        path), so both sides split together."""
        stack = [t]
        while stack:
            cur = stack[-1]
            if tris[cur] is None:
                stack.pop()
                continue
            k = longest(cur)
            nbrs = [n for n in by_edge.get(k, ()) if n != cur]
            blocking = [n for n in nbrs if longest(n) != k]
            if blocking:
                stack.append(blocking[0])
                continue
            split_edge(k)
            stack.pop()

    work = [t for t in range(len(tris)) if tris[t] is not None]
    while work:
        nxt = []
        for t in work:
            if tris[t] is not None and too_long(t):
                refine_triangle(t)
        # Newly made triangles may still be too long.
        nxt = [t for t in range(len(tris)) if tris[t] is not None and too_long(t)]
        if not nxt:
            break
        work = nxt

    # Write: one buffer, each section's attributes and indices.
    blob = bytearray()
    doc["bufferViews"], doc["accessors"] = [], []

    def put(arr, ctype, kind, target_kind=None, minmax=False):
        nonlocal blob
        while len(blob) % 4:
            blob += b"\0"
        view = {"buffer": 0, "byteOffset": len(blob), "byteLength": arr.nbytes}
        if target_kind:
            view["target"] = target_kind
        blob += arr.tobytes()
        doc["bufferViews"].append(view)
        acc = {"bufferView": len(doc["bufferViews"]) - 1, "componentType": ctype,
               "count": int(arr.shape[0]), "type": kind}
        if minmax:
            acc["min"] = [float(v) for v in arr.min(axis=0)]
            acc["max"] = [float(v) for v in arr.max(axis=0)]
        doc["accessors"].append(acc)
        return len(doc["accessors"]) - 1

    total = 0
    for si, (mi, pi, sec) in enumerate(mesh_sections):
        prim = doc["meshes"][mi]["primitives"][pi]
        idx = np.array([v for t in tris if t is not None and t[0] == si for v in t[1]], dtype=np.uint32)
        total += len(idx) // 3
        for n in sec.names:
            arr = np.array(sec.columns[n], dtype=np.float32)
            kind = {1: "SCALAR", 2: "VEC2", 3: "VEC3", 4: "VEC4"}[arr.shape[1]]
            prim["attributes"][n] = put(arr, FLOAT, kind, 34962, minmax=(n == "POSITION"))
        prim["indices"] = put(idx.reshape(-1, 1), 5125, "SCALAR", 34963)
    return bytes(blob), total, center, radius


def refine_file(src, dst, near=4.0, growth=0.08, center=None, radius=None):
    """Refine the glTF `src` into `dst` (with a buffer of its own beside it).
    Returns the triangle counts before and after, and the area used."""
    doc = json.load(open(src, encoding="utf-8"))
    data = open(os.path.join(os.path.dirname(os.path.abspath(src)), doc["buffers"][0]["uri"]), "rb").read()
    before = sum(doc["accessors"][p["indices"]]["count"] // 3 for m in doc["meshes"] for p in m["primitives"])
    blob, after, center, radius = refine(doc, data, near, growth, center, radius)
    bin_name = os.path.splitext(os.path.basename(dst))[0] + ".bin"
    doc["buffers"] = [{"uri": bin_name, "byteLength": len(blob)}]
    open(os.path.join(os.path.dirname(os.path.abspath(dst)), bin_name), "wb").write(blob)
    json.dump(doc, open(dst, "w", encoding="utf-8"))
    return before, after, center, radius


def playable_area(placement, margin=30.0):
    """The playable area of a staged CE map (halo2ue's placement.json): the
    centre and radius, in glTF metres, of its player starts and netgame
    flags, plus `margin`. glTF is CE (x, z, -y) in metres."""
    p = json.load(open(placement, encoding="utf-8"))
    k = p.get("world_unit_meters", 3.048)
    pts = [(q["pos"][0] * k, -q["pos"][1] * k)
           for q in p.get("player_starts", []) + p.get("netgame_flags", [])]
    if not pts:
        return None, None
    cx = (min(x for x, _ in pts) + max(x for x, _ in pts)) / 2
    cz = (min(z for _, z in pts) + max(z for _, z in pts)) / 2
    return (cx, cz), max(math.hypot(x - cx, z - cz) for x, z in pts) + margin


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("src")
    ap.add_argument("dst")
    ap.add_argument("--near", type=float, default=4.0, help="target edge length near the map, metres")
    ap.add_argument("--growth", type=float, default=0.08, help="metres added per metre beyond --radius")
    ap.add_argument("--center", help="x,z of the playable area (glTF metres)")
    ap.add_argument("--radius", type=float, help="radius of the playable area, metres")
    ap.add_argument("--placement", help="a staging placement.json to take the playable area from")
    a = ap.parse_args()
    center = tuple(float(v) for v in a.center.split(",")) if a.center else None
    radius = a.radius
    if a.placement and center is None:
        center, radius = playable_area(a.placement)
    before, after, center, radius = refine_file(a.src, a.dst, a.near, a.growth, center, radius)
    print(f"{os.path.basename(a.src)}: {before} -> {after} triangle(s), {a.near} m near "
          f"({center[0]:.0f}, {center[1]:.0f}) r {radius:.0f} m, +{a.growth} m/m beyond")


if __name__ == "__main__":
    main()
