#!/usr/bin/env python3
"""Find Forge pack pieces that pass into one another or z-fight.

Pieces may touch: floors meet walls and wall courses stack. Two faults are
reported. A penetration is a visual part overlapping another piece's part by
more than the tolerance along every separating axis, which a player sees as a
lamp inside a wall. A coplanar overlap is two faces sharing a plane and an
area, which flickers as the camera moves: faces that point the same way
always do, and with a translucent (two-sided) material, such as glass, faces
back to back do too. Maps are checked between pieces; a pack is checked
between the parts of each piece. Each part is treated as convex (the pack
sources author boxes and prisms), so a report on a concave part is
conservative.

    python tools/forge/check_overlaps.py forge-maps/crossline/crossline.level.json
    python tools/forge/check_overlaps.py --pack foundry-wide
"""
import argparse
import json
import math
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[2]
PREFIX = "objects\\mjolnir\\forge\\"
# Penetrations the reference maps make on purpose: wall and railing runs that
# overlap at joins and corners so no gap or ledge shows (offset so that no
# face is shared), the wide teleporter pad sunk into the deck, and barrier
# walls bedded into the pit deck. Coplanar faces are never allowed.
JOINS = {("wall_long", "wall_long"), ("railing", "railing"), ("wall_half", "wall_half"),
         ("floor_2x2", "teleporter_pad_wide"), ("straight_48", "wall_half")}


def source(pack):
    path = REPO / "forge-packs" / pack / "source/geometry.json"
    return json.loads(path.read_text(encoding="utf-8"))


def pieces(pack):
    return {p["id"]: p for p in source(pack)["pieces"]}


def two_sided(pack):
    """Materials drawn from both sides: the translucent ones (alpha below 1)."""
    return {name for name, m in source(pack)["materials"].items() if m.get("base_color", [0, 0, 0, 1])[3] < 1}


def placements(level):
    """Pack pieces with authored metres and yaw (generate.py's `ue` reversed)."""
    out = []
    for index, item in enumerate(level["blam"]["objects"]):
        tag = item.get("tag", "")
        if not tag.startswith(PREFIX):
            continue
        pack, ident = tag[len(PREFIX):].split("\\")
        rot = item.get("rot", [0, 0, 0])
        if rot[0] or rot[2]:
            raise ValueError(f"object {index} is pitched or rolled; only yaw is supported")
        pos = item["pos"]
        out.append({"index": index, "pack": pack, "id": ident,
                    "origin": np.array([pos[0] / 100, -pos[1] / 100, pos[2] / 100]),
                    "yaw": -rot[1]})
    return out


def axes_of(vertices, triangles):
    normals, edges = [], []
    for a, b, c in triangles:
        n = np.cross(vertices[b] - vertices[a], vertices[c] - vertices[a])
        if np.linalg.norm(n) > 1e-9:
            normals.append(n / np.linalg.norm(n))
        for p, q in ((a, b), (b, c), (c, a)):
            e = vertices[q] - vertices[p]
            if np.linalg.norm(e) > 1e-9:
                edges.append(e / np.linalg.norm(e))
    return unique(normals), unique(edges)


def unique(vectors):
    seen, out = set(), []
    for v in vectors:
        v = v if (v[0], v[1], v[2]) > (0, 0, 0) else -v
        key = tuple(np.round(v, 5))
        if key not in seen:
            seen.add(key)
            out.append(v)
    return out


def parts(piece, placement, sided=frozenset()):
    a = math.radians(placement["yaw"])
    r = np.array([[math.cos(a), -math.sin(a), 0], [math.sin(a), math.cos(a), 0], [0, 0, 1]])
    out = []
    for part in piece["visual"]:
        v = np.array(part["vertices"], dtype=float) @ r.T + placement["origin"]
        normals, edges = axes_of(v, part["triangles"])
        out.append({"v": v, "tris": part["triangles"], "normals": normals, "edges": edges,
                    "material": part["material"], "two_sided": part["material"] in sided,
                    "lo": v.min(axis=0), "hi": v.max(axis=0)})
    return out


def overlap_2d(a, b):
    """Overlap depth of two 2D triangles along their edge normals; <= 0 apart."""
    depth = math.inf
    for tri in (a, b):
        for i in range(3):
            e = tri[(i + 1) % 3] - tri[i]
            n = np.array([-e[1], e[0]])
            if np.linalg.norm(n) < 1e-12:
                return 0.0
            n /= np.linalg.norm(n)
            pa, pb = a @ n, b @ n
            depth = min(depth, min(pa.max(), pb.max()) - max(pa.min(), pb.min()))
            if depth <= 0:
                return depth
    return depth


def coplanar(p, q, plane=0.002, area=0.005):
    """Widest shared strip (m) of two parts' coplanar faces that would fight."""
    if np.any(p["lo"] > q["hi"] + plane) or np.any(q["lo"] > p["hi"] + plane):
        return 0.0
    widest = 0.0
    for ta in p["tris"]:
        a = p["v"][list(ta)]
        n = np.cross(a[1] - a[0], a[2] - a[0])
        if np.linalg.norm(n) < 1e-12:
            continue
        n /= np.linalg.norm(n)
        for tb in q["tris"]:
            b = q["v"][list(tb)]
            m = np.cross(b[1] - b[0], b[2] - b[0])
            if np.linalg.norm(m) < 1e-12:
                continue
            m /= np.linalg.norm(m)
            facing = float(n @ m)
            if abs(facing) < 0.9999 or abs(float(n @ (b[0] - a[0]))) > plane:
                continue
            if facing < 0 and not (p["two_sided"] or q["two_sided"]):
                continue  # back to back: each hides the other
            u = a[1] - a[0]
            u /= np.linalg.norm(u)
            w = np.cross(n, u)
            d = overlap_2d(np.stack([a @ u, a @ w], axis=1), np.stack([b @ u, b @ w], axis=1))
            widest = max(widest, d)
    return widest if widest > area else 0.0


def penetration(p, q):
    """Smallest overlap along the separating axes; <= 0 when apart."""
    axes = p["normals"] + q["normals"]
    for e in p["edges"]:
        for f in q["edges"]:
            n = np.cross(e, f)
            if np.linalg.norm(n) > 1e-6:
                axes.append(n / np.linalg.norm(n))
    depth = math.inf
    for n in axes:
        a, b = p["v"] @ n, q["v"] @ n
        depth = min(depth, min(a.max(), b.max()) - max(a.min(), b.min()))
        if depth <= 0:
            return depth
    return depth


def overlaps(level, tolerance=0.02):
    """Pairs of pieces that penetrate deeper than `tolerance` or share a
    fighting face, deepest first."""
    sources, sided = {}, {}
    placed = []
    for p in placements(level):
        piece = sources.setdefault(p["pack"], pieces(p["pack"]))[p["id"]]
        shapes = parts(piece, p, sided.setdefault(p["pack"], two_sided(p["pack"])))
        placed.append((p, shapes, np.min([s["lo"] for s in shapes], axis=0),
                       np.max([s["hi"] for s in shapes], axis=0)))
    found = []
    for i, (p, ps, plo, phi) in enumerate(placed):
        for q, qs, qlo, qhi in placed[i + 1:]:
            if np.any(plo > qhi) or np.any(qlo > phi):
                continue
            worst = {}
            for s in ps:
                for t in qs:
                    if np.any(s["lo"] > t["hi"]) or np.any(t["lo"] > s["hi"]):
                        continue
                    d = penetration(s, t)
                    for fault, value in (("penetrates", d if d > tolerance else 0), ("coplanar", coplanar(s, t))):
                        if value > 0 and value > worst.get(fault, (0,))[0]:
                            worst[fault] = (value, s["material"], t["material"])
            for fault, (value, *materials) in worst.items():
                found.append({"a": p, "b": q, "fault": fault, "depth_m": round(float(value), 3),
                              "materials": materials})
    return sorted(found, key=lambda f: (f["fault"], -f["depth_m"]))


def problems(level, tolerance=0.02, joins=JOINS):
    """The faults a map may not ship with: any coplanar face, and any
    penetration between pieces other than the deliberate `joins`."""
    return [f for f in overlaps(level, tolerance)
            if f["fault"] == "coplanar" or tuple(sorted((f["a"]["id"], f["b"]["id"]))) not in joins]


def pack_faults(pack):
    """Coplanar fighting faces between the parts of each piece in a pack."""
    sided = two_sided(pack)
    origin = {"origin": np.zeros(3), "yaw": 0}
    found = []
    for ident, piece in pieces(pack).items():
        shapes = parts(piece, origin, sided)
        for i, s in enumerate(shapes):
            for t in shapes[i + 1:]:
                w = coplanar(s, t)
                if w:
                    found.append({"id": ident, "width_m": round(float(w), 3), "materials": (s["material"], t["material"])})
    return found


def describe(f):
    a, b = f["a"], f["b"]
    at = lambda p: "(" + ", ".join(f"{c:g}" for c in np.round(p["origin"], 3)) + ")"
    return (f"{f['fault']:<10} {f['depth_m']:.3f} m  {a['id']} #{a['index']} {at(a)}  x  "
            f"{b['id']} #{b['index']} {at(b)}  [{f['materials'][0]} / {f['materials'][1]}]")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("level", type=Path, nargs="?")
    parser.add_argument("--pack", help="check the parts of every piece in forge-packs/<pack> instead")
    parser.add_argument("--tolerance", type=float, default=0.02, help="metres of overlap ignored (default 0.02)")
    parser.add_argument("--strict", action="store_true", help="fail on the deliberate joins too")
    args = parser.parse_args()
    if args.pack:
        found = pack_faults(args.pack)
        for f in found:
            print(f"coplanar   {f['width_m']:.3f} m  {f['id']}  [{f['materials'][0]} / {f['materials'][1]}]")
        failed = found
    elif args.level:
        level = json.loads(args.level.read_text(encoding="utf-8"))
        found = overlaps(level, args.tolerance)
        failed = found if args.strict else problems(level, args.tolerance)
        for f in found:
            print(describe(f) + ("" if any(f is g for g in failed) else "  (deliberate join)"))
    else:
        parser.error("name a level file or --pack")
    print(f"{len(found)} fault(s), {len(failed)} not allowed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
