"""Seat CE's beacons on the ground under them.

CE's level designers tilted some beacons onto their slope and left others
upright, or tilted them one way on ground that falls two ways, so in CE
those rock on one edge of their base (Ice Fields' red beacon at
(14.9, 17.5) stands 0.22 m higher on one side whatever its rotation). A
beacon whose base spans more than SPREAD over the BSP is turned onto the
plane fitted to the ground under its base, keeping its heading, and set a
little above it (SEATED), the height CE gives its well-placed ones. Flag
bases, which CE floats 3.4 cm over the floor, are all set down the same way.

Every tool that places a placement's model or what hangs on it (the scene
and collision merges, the lens flares, the sound emitters) calls seat()
right after loading placement.json, so they all move together.
"""
import math
import os

import numpy as np

from merge_ce_scene import WU_TO_M, ce_rotation, ce_to_gltf, load_gltf, primitives

# The props seated, by a substring of their tag path: how far above the
# ground a seated base sits (metres), and whether every placement is seated
# or only one whose base spans more than SPREAD over the ground.
# - CE's beacons (mp_beacon_red/blue, small red/blue beacon): CE's flush
#   ones stand 0.03 above the ground, and only the rocking ones move.
# - The CTF flag base: a thin plate CE puts 0.011 wu (3.4 cm) over the floor
#   on every map, which reads as floating (2026-10-08); all of them go down
#   to 5 mm.
SEATED = {"beacon": (0.03, False), "flag_base": (0.005, True)}
# A base spread (metres, highest point of the base over the ground minus
# the lowest) above which a beacon is seated. CE's flush ones measure 0-0.09.
SPREAD = 0.1
SWAP = np.array([[1, 0, 0], [0, 0, 1], [0, -1, 0]], dtype=np.float64)  # glTF = SWAP @ CE


class _Heights:
    """Heights of the BSP's triangles under points (glTF metres, y up), on
    an xz grid."""

    def __init__(self, staging, cell=2.0):
        g, buf = load_gltf(os.path.join(staging, "bsp", "bsp_0.gltf"))
        self.t = np.concatenate([p["pos"][p["idx"].reshape(-1, 3)] for p in primitives(g, buf)])
        self.cell = cell
        self.grid = {}
        lo = np.floor(self.t[:, :, [0, 2]].min(axis=1) / cell).astype(int)
        hi = np.floor(self.t[:, :, [0, 2]].max(axis=1) / cell).astype(int)
        for i, (a, b) in enumerate(zip(lo, hi)):
            for gx in range(a[0], b[0] + 1):
                for gz in range(a[1], b[1] + 1):
                    self.grid.setdefault((gx, gz), []).append(i)

    def near(self, x, y, z, reach=0.5):
        """The ground height under (x, z) closest to y, within `reach`."""
        best = None
        for i in self.grid.get((math.floor(x / self.cell), math.floor(z / self.cell)), ()):
            a, b, c = self.t[i]
            d = (b[2] - c[2]) * (a[0] - c[0]) + (c[0] - b[0]) * (a[2] - c[2])
            if abs(d) < 1e-12:
                continue
            l1 = ((b[2] - c[2]) * (x - c[0]) + (c[0] - b[0]) * (z - c[2])) / d
            l2 = ((c[2] - a[2]) * (x - c[0]) + (a[0] - c[0]) * (z - c[2])) / d
            l3 = 1 - l1 - l2
            if min(l1, l2, l3) < -1e-6:
                continue
            h = l1 * a[1] + l2 * b[1] + l3 * c[1]
            if abs(h - y) <= reach and (best is None or abs(h - y) < abs(best - y)):
                best = h
        return best


def rotation_angles(r_gltf):
    """(yaw, pitch, roll) for a glTF-space rotation, the inverse of
    ce_rotation: CE R = Rx(roll) Ry(pitch) Rz(yaw), with ce_rotation's Ry."""
    r = SWAP.T @ r_gltf @ SWAP
    pitch = math.asin(max(-1.0, min(1.0, -r[0][2])))
    yaw = math.atan2(-r[0][1], r[0][0])
    roll = math.atan2(-r[1][2], r[2][2])
    return [yaw, pitch, roll]


def _align(a, b):
    """The rotation turning unit vector a onto unit vector b."""
    v = np.cross(a, b)
    c = float(a @ b)
    if np.linalg.norm(v) < 1e-9:
        return np.eye(3)
    k = np.array([[0, -v[2], v[1]], [v[2], 0, -v[0]], [-v[1], v[0], 0]])
    return np.eye(3) + k + k @ k / (1 + c)


def seat(placement, staging, log=print):
    """Seat the beacons of `placement` (halo2ue's placement.json, loaded) in
    place: their `rot` and `pos` change, and they are marked `seated`.
    Returns how many moved."""
    heights = None
    bases = {}
    moved = 0
    for e in placement.get("entries", []):
        prop = next((k for k in SEATED if k in e.get("asset", "").lower()), None)
        if e.get("kind") != "scenery" or prop is None:
            continue
        clearance, always = SEATED[prop]
        path = os.path.join(staging, e.get("model") or "")
        if not e.get("model") or not os.path.exists(path):
            continue
        r0 = ce_rotation(*e.get("rot", [0, 0, 0]))
        if (r0 @ [0, 1, 0])[1] < 0.7:
            continue  # hung upside down or on a wall
        if path not in bases:
            g, buf = load_gltf(path)
            v = np.concatenate([p["pos"] for p in primitives(g, buf)])
            h = v[:, 1]
            bases[path] = v[h <= h.min() + 0.03 * (h.max() - h.min())]
        base = bases[path]
        if len(base) < 3:
            continue
        if heights is None:
            heights = _Heights(staging)
        t = ce_to_gltf(e["pos"])

        def gaps(r, t):
            w = base @ r.T + t
            out = []
            for x, y, z in w:
                gh = heights.near(x, y, z)
                if gh is not None:
                    out.append((x, z, gh, y - gh))
            return out

        placed = gaps(r0, t)
        if len(placed) < 0.7 * len(base):
            continue
        spread = max(p[3] for p in placed) - min(p[3] for p in placed)
        if spread <= SPREAD and not always:
            continue
        # The ground's plane under the base: y = a x + b z + c.
        pts = np.array([(x, z, gh) for x, z, gh, _ in placed])
        (a, b, _), *_ = np.linalg.lstsq(np.c_[pts[:, 0], pts[:, 1], np.ones(len(pts))], pts[:, 2], rcond=None)
        normal = np.array([-a, 1.0, -b])
        normal /= np.linalg.norm(normal)
        r_new = _align(np.array([0.0, 1.0, 0.0]), normal) @ ce_rotation(e["rot"][0], 0, 0)
        rot = rotation_angles(r_new)
        r_new = ce_rotation(*rot)
        after = gaps(r_new, t)
        if not after:
            continue
        lift = clearance - float(np.median([p[3] for p in after]))
        t_new = t + np.array([0.0, lift, 0.0])
        new_spread = max(p[3] for p in after) - min(p[3] for p in after)
        log(f"  seated   {e['asset'].split(chr(92))[-1]} at ({e['pos'][0]:.1f}, {e['pos'][1]:.1f}): "
            f"base spread {spread:.2f} -> {new_spread:.2f} m, lifted {lift:+.2f} m")
        e["rot"] = rot
        e["pos"] = [float(t_new[0] / WU_TO_M), float(-t_new[2] / WU_TO_M), float(t_new[1] / WU_TO_M)]
        e["seated"] = True
        moved += 1
    return moved
