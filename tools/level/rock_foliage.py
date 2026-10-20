#!/usr/bin/env python3
"""Clear the foliage inside the swapped B30 rocks, by each rock's own hull.

    python tools/level/rock_foliage.py <foliage.bin> <swap.json> <staging dir> [--hulls DIR] [--margin cm] [--biome snow]

scatter_foliage.py runs before scenery_swap.py, so it cannot know which B30
rock stands where a CE boulder stood; it cleared a circle of 80% of the CE
boulder's widest reach. Around a long boulder that left bands of bare ground
up to 2 m wide along its sides, where the swapped rock (a different mesh,
fitted to the CE one's height) was narrower still (Danger Canyon, 2026-10-19).
With `scatter_foliage.py --swapped-rocks` it clears none for them; this,
after the swap, drops every foliage instance whose foot lies inside a
swapped rock's convex hull (b30_collision.py's, the one the simulation
collides with) grown by --margin, so the grass meets the rock. A boulder
the swap kept as CE drew it (no bounds for its mesh) gets the old circle.

Rewrites foliage.bin in place; running it again removes nothing more.
"""
import argparse
import json
import os
import struct
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from b30_collision import hull_of, rotator_matrix  # noqa: E402
from scatter_foliage import FOLIAGE_MAGIC, SCENERY_DEPTH_SLACK, scenery_footprints  # noqa: E402
from scenery_swap import swap_rule  # noqa: E402

RECORD = 19
CELL = 1000.0


def rock_hulls(swap, hulls_dir):
    """Each swapped rock as (planes n x 4, xy min, xy max): outward unit
    normals and offsets, in the level's Unreal cm."""
    out = {}
    for d in swap["decor"]:
        parts = d["id"].split("_")
        if len(parts) != 2 or not parts[1].isdigit() or "/Rock/" not in d["mesh"]:
            continue
        pts, faces = hull_of(d["mesh"], hulls_dir)
        m = rotator_matrix(*d["rot"])
        w = (pts * np.array(d["scale"])) @ m + np.array(d["pos"])
        f = np.array(faces)
        a, b, c = w[f[:, 0]], w[f[:, 1]], w[f[:, 2]]
        n = np.cross(b - a, c - a)
        keep = np.linalg.norm(n, axis=1) > 1e-6
        n = n[keep] / np.linalg.norm(n[keep], axis=1)[:, None]
        # Outward: every hull point on or behind each face.
        centre = w.mean(0)
        flip = np.einsum("ij,ij->i", centre - a[keep], n) > 0
        n[flip] = -n[flip]
        out[int(parts[1])] = (np.hstack([n, -np.einsum("ij,ij->i", n, a[keep])[:, None]]),
                              w[:, :2].min(0), w[:, :2].max(0), w[:, 2].min(), w[:, 2].max())
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("bin")
    ap.add_argument("swap")
    ap.add_argument("staging")
    ap.add_argument("--hulls", default="C:/haloce/ce_conversions/upgrade/hulls")
    ap.add_argument("--margin", type=float, default=15.0,
                    help="cm the hull is grown by: grass this close to the rock's face goes too")
    ap.add_argument("--biome", default="b30")
    a = ap.parse_args()
    os.makedirs(a.hulls, exist_ok=True)
    swap = json.load(open(a.swap, encoding="utf-8"))
    placement = json.load(open(os.path.join(a.staging, "placement.json"), encoding="utf-8"))
    hulls = rock_hulls(swap, a.hulls)
    # Boulders the swap left as CE drew them: the old circle.
    snow = a.biome == "snow"
    scenery = [i for i, e in enumerate(placement["entries"]) if e.get("kind") == "scenery" and e.get("model")]
    circles = [fp for i, fp in zip(scenery, scenery_footprints(None, [0, 0, 0], a.staging))
               if i not in hulls and (swap_rule(placement["entries"][i], a.staging, snow) or ("",))[0] in ("rock", "bigrock")]
    shapes = [("hull", h) for h in hulls.values()] + [("circle", c) for c in circles]
    grid = {}
    for k, (kind, s) in enumerate(shapes):
        if kind == "hull":
            lo, hi = s[1] - a.margin, s[2] + a.margin
        else:
            lo, hi = np.array(s[:2]) - s[2], np.array(s[:2]) + s[2]
        for i in range(int(lo[0] // CELL), int(hi[0] // CELL) + 1):
            for j in range(int(lo[1] // CELL), int(hi[1] // CELL) + 1):
                grid.setdefault((i, j), []).append(k)

    def inside(x, y, z):
        for k in grid.get((int(x // CELL), int(y // CELL)), ()):
            kind, s = shapes[k]
            if kind == "hull":
                planes, lo, hi, zlo, zhi = s
                if not (lo[0] - a.margin <= x <= hi[0] + a.margin and lo[1] - a.margin <= y <= hi[1] + a.margin
                        and z <= zhi + a.margin):
                    continue
                # In the rock, or under it: where the ground dips below a
                # rock's underside (a boulder across a hollow), the grass
                # stood under it in the dark.
                for zz in (z,) if z >= zlo else np.linspace(zlo, zhi, 8):
                    if np.all(planes[:, :3] @ (x, y, zz) + planes[:, 3] <= a.margin):
                        return True
            else:
                sx, sy, r, sz, tall = s
                if (x - sx) ** 2 + (y - sy) ** 2 < r * r and abs(z - sz) < tall + SCENERY_DEPTH_SLACK:
                    return True
        return False

    raw = open(a.bin, "rb").read()
    if raw[:4] != FOLIAGE_MAGIC:
        sys.exit(f"{a.bin}: not a foliage file")
    version, groups = struct.unpack_from("<II", raw, 4)
    at, out, before, after = 12, [raw[:12]], 0, 0
    for _ in range(groups):
        (n,) = struct.unpack_from("<I", raw, at)
        at += 4
        kept = []
        for i in range(n):
            rec = raw[at + RECORD * i: at + RECORD * (i + 1)]
            x, y, z = struct.unpack_from("<fff", rec)
            if not inside(x, y, z):
                kept.append(rec)
        at += RECORD * n
        before += n
        after += len(kept)
        out.append(struct.pack("<I", len(kept)) + b"".join(kept))
    if at != len(raw):
        sys.exit(f"{a.bin}: {len(raw) - at} trailing byte(s); not the format this reads")
    open(a.bin, "wb").write(b"".join(out))
    print(f"{before - after} of {before} foliage instance(s) inside {len(hulls)} swapped rock(s)"
          f" and {len(circles)} kept CE boulder(s) removed")


if __name__ == "__main__":
    main()
