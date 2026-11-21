"""Find coplanar, overlapping faces between (and within) a level's decor meshes: what z-fights.

Two faces flicker when they lie in the same plane (within `--gap` cm), face the same way and
overlap. Reads level.json decor and each mesh's cooked LOD0 (`mjolnir mesh export` .glb files
in --meshes, named <asset>.glb), in world centimetres.

    python coplanar_overlaps.py <level.json> --meshes <dir> [--match red] [--gap 0.6] [--min-area 0.05]

Prints, per pair of (decor, material slot): overlapping area in m2, the plane, and where.
Used by decor_separation.py to nudge whole decor pieces apart.
"""
import argparse
import json
import math
import struct
from collections import defaultdict
from pathlib import Path

import numpy as np


def glb_sections(path):
    b = Path(path).read_bytes()
    jl = struct.unpack_from("<I", b, 12)[0]
    doc = json.loads(b[20:20 + jl])
    data = b[20 + jl + 8:]

    def acc(i, comps, fmt):
        a = doc["accessors"][i]; v = doc["bufferViews"][a["bufferView"]]
        off = v.get("byteOffset", 0) + a.get("byteOffset", 0)
        return np.frombuffer(data, dtype=fmt, count=a["count"] * comps, offset=off).reshape(a["count"], comps)
    out = {}
    for p in doc["meshes"][0]["primitives"]:
        pos = acc(p["attributes"]["POSITION"], 3, "<f4")[:, [0, 2, 1]] * 100.0
        ia = doc["accessors"][p["indices"]]
        idx = acc(p["indices"], 1, {5123: "<u2", 5125: "<u4"}[ia["componentType"]]).reshape(-1, 3)
        out.setdefault(doc["materials"][p["material"]]["name"], []).append(pos[idx])
    return {k: np.concatenate(v) for k, v in out.items()}


def world(tris, d):
    s = np.asarray(d.get("scale") or [1, 1, 1], float)
    rot = d.get("rot") or [0, 0, 0]
    if any(abs(r) > 1e-6 for i, r in enumerate(rot) if i != 1):
        return None
    yaw = math.radians(rot[1])
    t = tris * s
    c, sn = math.cos(yaw), math.sin(yaw)
    t = np.stack([t[..., 0] * c - t[..., 1] * sn, t[..., 0] * sn + t[..., 1] * c, t[..., 2]], -1)
    return t + np.asarray(d["pos"], float)


def planes(level, meshes, match):
    """{(normal key, offset key): {(decor id, slot): [2D polygons in the plane]}} and each plane's frame."""
    groups = defaultdict(lambda: defaultdict(list))
    frames = {}
    for d in level.get("decor", []):
        if match and match.lower() not in d["id"].lower():
            continue
        name = (d.get("mesh") or "").rsplit(".", 1)[-1]
        glb = Path(meshes) / f"{name}.glb"
        if not glb.is_file():
            continue
        for slot, tris in glb_sections(glb).items():
            w = world(tris, d)
            if w is None:
                continue
            n = np.cross(w[:, 1] - w[:, 0], w[:, 2] - w[:, 0])
            area = np.linalg.norm(n, axis=1) / 2
            ok = area > 4.0            # cm2: skip slivers
            w, n = w[ok], n[ok] / (2 * area[ok, None])
            off = np.einsum("ij,ij->i", n, w[:, 0])
            nk = np.round(n / 0.02).astype(int)
            for i in range(len(w)):
                frames.setdefault(tuple(nk[i]), n[i])
                groups[(tuple(nk[i]), )][(d["id"], slot)].append((w[i], off[i]))
    return groups, frames


def overlaps(groups, frames, gap, min_area):
    import shapely                      # only the overlap search needs it; the mesh readers do not
    from shapely.ops import unary_union
    found = []
    for (nk,), owners in groups.items():
        n = frames[nk]
        # A stable 2D frame in the plane.
        a = np.cross(n, [0, 0, 1.0]) if abs(n[2]) < 0.9 else np.cross(n, [1.0, 0, 0])
        a /= np.linalg.norm(a); b = np.cross(n, a)
        layers = defaultdict(lambda: defaultdict(list))
        for owner, rows in owners.items():
            for tri, off in rows:
                layers[int(math.floor(off / gap))][owner].append((tri, off))
        keys = sorted(layers)
        done = set()
        for k in keys:
            # Faces within `gap` of each other fall in this bin or the next.
            bins = [layers[k]] + ([layers[k + 1]] if k + 1 in layers else [])
            merged = defaultdict(list)
            for layer in bins:
                for owner, rows in layer.items():
                    merged[owner].extend(rows)
            polys = {}
            for owner, rows in merged.items():
                ps = [shapely.Polygon([(float(p @ a), float(p @ b)) for p in tri]) for tri, _ in rows]
                polys[owner] = (unary_union([p for p in ps if p.is_valid and p.area > 0]),
                                float(np.mean([o for _, o in rows])), rows)
            names = sorted(polys)
            for i, x in enumerate(names):
                for y in names[i + 1:]:
                    if abs(polys[x][1] - polys[y][1]) > gap:
                        continue
                    inter = polys[x][0].intersection(polys[y][0])
                    if inter.area / 1e4 >= min_area and (nk, k, x, y) not in done and (nk, k - 1, x, y) not in done:
                        done.add((nk, k, x, y))
                        c = inter.centroid
                        at = a * c.x + b * c.y + n * polys[x][1]
                        found.append({"a": x, "b": y, "area_m2": round(inter.area / 1e4, 2),
                                      "normal": [round(float(v), 2) for v in n],
                                      "gap_cm": round(polys[y][1] - polys[x][1], 3),
                                      "at": [round(float(v)) for v in at]})
    return sorted(found, key=lambda f: -f["area_m2"])


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("level", type=Path)
    ap.add_argument("--meshes", type=Path, required=True)
    ap.add_argument("--match")
    ap.add_argument("--gap", type=float, default=0.6)
    ap.add_argument("--min-area", type=float, default=0.05)
    ap.add_argument("--json", type=Path)
    a = ap.parse_args()
    groups, frames = planes(json.loads(a.level.read_text()), a.meshes, a.match)
    found = overlaps(groups, frames, a.gap, a.min_area)
    if a.json:
        a.json.write_text(json.dumps(found, indent=1))
    total = defaultdict(float)
    for f in found:
        total[(f["a"][0], f["b"][0])] += f["area_m2"]
    for k, v in sorted(total.items(), key=lambda kv: -kv[1]):
        print(f"{v:9.1f} m2  {k[0]}  x  {k[1]}")
    for f in found[:40]:
        print(f)


if __name__ == "__main__":
    main()
