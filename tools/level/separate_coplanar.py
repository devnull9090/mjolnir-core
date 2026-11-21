"""Separate coplanar, overlapping faces in a set of glTF meshes that share one frame: no z-fighting.

Authored architecture stacks finish panels exactly on its shell (an inset on a wall, floor
finishes over each other, a court under an apron). Two materials in one plane flicker. Here
each material slot gets one lift level and its whole surface moves out along its normals by
level x `--step`: the largest surface stays put and every other slot takes the lowest level
that leaves each face it overlaps at least a step clear. One pass, nothing left to chance.
Vertices move by millimetres; counts, indices, normals and UVs are untouched, so collision
built from the same source still fits.

    python separate_coplanar.py <manifest.json> <out dir> [--step 0.003] [--reach 0.03]

The manifest is a base visual export's (bases_v1/runtime_visuals.py): `assets` with `gltf`,
`gltf_sha256`, `bin_sha256`. Meshes are grouped by `--group` regex on the asset name (default:
the team word in SM_PWR_<team>_*), each group one assembly. Writes the meshes and an updated
manifest into <out dir>, and separation.json (each slot's level, what overlapped, what is left).
"""
import argparse
import hashlib
import json
import re
from collections import defaultdict
from pathlib import Path

import numpy as np
import shapely
from shapely.ops import unary_union


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class Mesh:
    def __init__(self, spec):
        self.spec = spec
        self.path = Path(spec["gltf"])
        self.doc = json.loads(self.path.read_text())
        self.bin_path = self.path.parent / self.doc["buffers"][0]["uri"]
        self.data = bytearray(self.bin_path.read_bytes())
        self.prims = []
        for p in self.doc["meshes"][0]["primitives"]:
            pos = self.view(p["attributes"]["POSITION"], 3, "<f4")
            ia = self.doc["accessors"][p["indices"]]
            idx = self.view(p["indices"], 1, {5123: "<u2", 5125: "<u4"}[ia["componentType"]]).reshape(-1, 3)
            self.prims.append({"slot": self.doc["materials"][p["material"]]["name"], "pos": pos, "idx": idx,
                               "accessor": p["attributes"]["POSITION"], "moved": 0.0})

    def view(self, i, comps, fmt):
        a = self.doc["accessors"][i]; v = self.doc["bufferViews"][a["bufferView"]]
        if v.get("byteStride") not in (None, np.dtype(fmt).itemsize * comps):
            raise ValueError("Interleaved buffers are not supported")
        off = v.get("byteOffset", 0) + a.get("byteOffset", 0)
        return np.frombuffer(self.data, dtype=fmt, count=a["count"] * comps, offset=off).reshape(a["count"], comps)

    def write(self, out):
        for p in self.prims:
            a = self.doc["accessors"][p["accessor"]]
            if p["moved"] and "min" in a:
                a["min"], a["max"] = p["pos"].min(0).tolist(), p["pos"].max(0).tolist()
        out = Path(out).resolve()      # the editor reads the manifest from another working directory
        gltf, binf = out / self.path.name, out / self.bin_path.name
        binf.write_bytes(bytes(self.data))
        gltf.write_text(json.dumps(self.doc, separators=(",", ":")) + "\n")
        spec = dict(self.spec, gltf=str(gltf), gltf_sha256=sha(gltf), bin_sha256=sha(binf))
        return spec, max(p["moved"] for p in self.prims)


def constraints(meshes, reach, min_area):
    """{(owner a, owner b): {signed gap b - a, metres}} for same-facing faces that overlap within
    `reach` of each other, the overlap area per pair, and the owners (one per mesh material slot)."""
    owners, rows, tri_pts, normals = [], [], [], []
    for m in meshes:
        for p in m.prims:
            t = p["pos"][p["idx"]].astype(np.float64)
            n = np.cross(t[:, 1] - t[:, 0], t[:, 2] - t[:, 0])
            area = np.linalg.norm(n, axis=1) / 2
            ok = np.flatnonzero(area > 4e-4)     # m2: slivers cannot be seen to flicker
            owners.append({"mesh": m.spec["name"], "slot": p["slot"], "prim": p, "area": float(area.sum())})
            rows.append(np.full(len(ok), len(owners) - 1))
            tri_pts.append(t[ok]); normals.append(n[ok] / (2 * area[ok, None]))
    own = np.concatenate(rows); tri_pts = np.concatenate(tri_pts); normals = np.concatenate(normals)
    found = defaultdict(set)
    areas = defaultdict(float)
    # Faces are compared within bins of facing. Two binnings, half a bin apart, so two panels of
    # one plane whose normals straddle a bin edge still meet in the other.
    groups = []
    for shift in (0.0, 0.5):
        nk = np.floor(normals / 0.02 + shift).astype(np.int64)
        key = nk[:, 0] * 1000003 + nk[:, 1] * 1009 + nk[:, 2]
        groups.extend(np.flatnonzero(key == k) for k in np.unique(key))
    for sel in groups:
        if len(np.unique(own[sel])) < 2:
            continue
        n = normals[sel].mean(0); n /= np.linalg.norm(n)
        a = np.cross(n, [0, 1.0, 0]) if abs(n[1]) < 0.9 else np.cross(n, [1.0, 0, 0])
        a /= np.linalg.norm(a); b = np.cross(n, a)
        off = tri_pts[sel].mean(1) @ n
        polys = shapely.polygons(np.stack([tri_pts[sel] @ a, tri_pts[sel] @ b], -1))
        # One sheet per (owner, plane): an owner's faces at one height (to 0.1 mm).
        level = np.round(off / 1e-4).astype(np.int64)
        sheets = []
        for o in np.unique(own[sel]):
            mine = np.flatnonzero(own[sel] == o)
            for lv in np.unique(level[mine]):
                part = mine[level[mine] == lv]
                sheets.append((float(off[part].mean()), int(o), unary_union(polys[part])))
        sheets.sort(key=lambda x: x[0])
        for i, (ox, o1, g1) in enumerate(sheets):
            for oy, o2, g2 in sheets[i + 1:]:
                if oy - ox > reach:
                    break
                if o1 == o2 or not g1.intersects(g2):
                    continue
                area = g1.intersection(g2).area
                if area >= min_area:
                    x, y, g = (o1, o2, oy - ox) if o1 < o2 else (o2, o1, ox - oy)
                    if round(g, 5) not in found[(x, y)]:
                        areas[(x, y)] += area
                    found[(x, y)].add(round(g, 5))
    return found, areas, owners


def levels(found, owners, step):
    """A lift level per owner so every overlapping pair ends at least `step` apart: the largest
    surface stays put, each next owner takes the lowest level that clears its neighbours."""
    level = {}
    near = defaultdict(list)
    for (x, y), gaps in found.items():
        near[x].append((y, gaps, 1)); near[y].append((x, gaps, -1))
    for o in sorted(near, key=lambda o: -owners[o]["area"]):
        for cand in range(64):
            # sign 1: the gaps are other - o. After the lifts: gap + (L_other - cand) * step.
            if all(abs(sign * g + (level[other] - cand) * step) >= step - 1e-6
                   for other, gaps, sign in near[o] if other in level for g in gaps):
                level[o] = cand
                break
        else:
            raise ValueError("No lift level separates " + owners[o]["slot"])
    return level


def inflate(prim, amount):
    """Move every vertex of a primitive out by `amount` along its faces' normals (mitred where faces meet)."""
    idx = prim["idx"].astype(np.int64)
    t = prim["pos"][idx].astype(np.float64)
    n = np.cross(t[:, 1] - t[:, 0], t[:, 2] - t[:, 0])
    length = np.linalg.norm(n, axis=1)
    good = length > 1e-12
    n = n[good] / length[good, None]; idx = idx[good]
    total = np.zeros(prim["pos"].shape, np.float64)
    for c in range(3):
        np.add.at(total, idx[:, c], n)
    norm = np.linalg.norm(total, axis=1)
    mitre = np.where(norm[:, None] > 1e-9, total / np.maximum(norm[:, None], 1e-9), 0.0)
    least = np.ones(len(total))
    for c in range(3):
        np.minimum.at(least, idx[:, c], np.einsum("ij,ij->i", mitre[idx[:, c]], n))
    move = mitre * (amount / np.clip(least, 0.34, 1.0))[:, None]
    prim["pos"][:] = (prim["pos"].astype(np.float64) + move).astype(np.float32)     # a view into the buffer
    prim["moved"] = float(np.linalg.norm(move, axis=1).max())


def separate(meshes, step, reach, min_area):
    found, areas, owners = constraints(meshes, reach, min_area)
    level = levels(found, owners, step)
    for o, lv in level.items():
        if lv:
            inflate(owners[o]["prim"], lv * step)

    def label(o):
        return owners[o]["mesh"] + "/" + owners[o]["slot"]
    report = {label(x) + " x " + label(y): round(area, 2) for (x, y), area in areas.items()
              if any(abs(g) < step for g in found[(x, y)])}
    lifted = {label(o): lv for o, lv in level.items() if lv}
    # What is still closer than the step after the lift (a mitred corner tilts a face slightly).
    _, after, _ = constraints(meshes, step * 0.8, min_area)
    return report, lifted, round(sum(after.values()), 2)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("manifest", type=Path)
    ap.add_argument("out", type=Path)
    ap.add_argument("--step", type=float, default=0.003)
    ap.add_argument("--reach", type=float, default=0.03, help="faces this close (m) are kept in order")
    ap.add_argument("--min-area", type=float, default=0.02)
    ap.add_argument("--group", default=r"^SM_PWR_(red|blue|green)_")
    a = ap.parse_args()
    manifest = json.loads(a.manifest.read_text())
    a.out.mkdir(parents=True, exist_ok=True)
    groups = defaultdict(list)
    for spec in manifest["assets"]:
        if sha(spec["gltf"]) != spec["gltf_sha256"]:
            raise ValueError("Changed mesh " + spec["name"])
        m = re.search(a.group, spec["name"])
        groups[m.group(1) if m else spec["name"]].append(Mesh(spec))
    summary, specs = {}, {}
    for name, meshes in groups.items():
        report, lifted, left = separate(meshes, a.step, a.reach, a.min_area)
        moved = 0.0
        for m in meshes:
            spec, d = m.write(a.out)
            specs[spec["name"]] = spec
            moved = max(moved, d)
        summary[name] = {"overlap_m2": round(sum(report.values()), 2), "pairs": len(report), "levels": lifted,
                         "overlap_left_m2": left, "largest_vertex_move_m": round(moved, 4),
                         "top": sorted(((v, k) for k, v in report.items()), reverse=True)[:8]}
        print(name, json.dumps(summary[name])[:700], flush=True)
    manifest["assets"] = [specs[s["name"]] for s in manifest["assets"]]
    manifest["coplanar_separation"] = {"step_m": a.step, "reach_m": a.reach, "source_manifest_sha256": sha(a.manifest)}
    (a.out / "manifest.json").write_text(json.dumps(manifest, indent=1))
    (a.out / "separation.json").write_text(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main()
