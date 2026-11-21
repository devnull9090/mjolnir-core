"""Fit rooted sod, graded alluvium and their physical support to the final registered apron."""

import hashlib
import json
import math
from pathlib import Path
import os
import sys

import numpy as np
from scipy.spatial import ConvexHull
from matplotlib.tri import Triangulation

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "terrain"))
import headwater_dressing as d
import outlet_apron as apron

OUT = Path(os.environ.get("PWR_HEADWATER_OUTPUT", d.ROOT / "out/pwr/river-apron"))
ART = OUT / "bank"
ORIGIN = np.array([-300.0, 820.0, 141.0])
REFLECT = np.array([100.0, -100.0, 100.0])
rng = np.random.default_rng(36049)


def save(name, data):
    (ART / name).write_text(json.dumps(data, separators=(",", ":"), allow_nan=False))


def build():
    field = d.load_heightfield(OUT / "terrain/runtime-master.json")
    (river,) = [
        r
        for r in d.read(OUT / "terrain/terrain.geometry.json")["watercourses"]
        if r["id"] == "central_river"
    ]
    line = np.asarray(river["erosion_reach"]["centreline_m"])
    left, right = apron.curves(line)
    A, B = apron.FORWARD_XY, apron.RIGHT[:2]

    def xy(s, side):
        return (
            apron.EYE[:2]
            + np.asarray(s)[..., None] * A
            + np.asarray(side)[..., None] * B
        )

    def grade(p):
        return d.sample(field, np.asarray(p))

    def world(s, side):
        p = xy(s, side)
        return np.r_[p, grade(p)]

    rock_polys = []
    cache = {}
    for row in d.read(OUT / "dressing/decor-moves.json")["decor"]:
        offset = d.world_foot(row, cache)[:, :2] * d.UE_TO_WORLD
        centre = np.asarray(row["new_pos_ue_cm"][:2]) * d.UE_TO_WORLD
        rock_polys.append(
            (
                centre,
                np.linalg.norm(offset, axis=1).max() + 0.35,
                centre + offset[ConvexHull(offset).vertices] * 1.05,
            )
        )

    def occupied(p):
        return any(
            np.linalg.norm(p - c) < radius and d.inside_polygon(p[:1], p[1:], poly)[0]
            for c, radius, poly in rock_polys
        )

    vertices, colors, uv, faces, physics = [], [], [], [], []
    plants = []

    def vert(p, color, tex=None):
        vertices.append(p)
        colors.append(color)
        uv.append(p[:2] / 1.65 if tex is None else tex)
        return len(vertices) - 1

    def face(a, b, c, reverse=False):
        faces.append((b, a, c) if reverse else (a, b, c))

    # 18 coarse native sections share their anchors with a much finer, ragged visual mesh.
    # Ends feather into the measured slope; the landward seam is buried eight cm.
    start, stop = 13.0, 58.0

    def profile(s):
        taper = 0.25 + 0.75 * np.clip(min((s - start) / 3, (stop - s) / 5), 0, 1)
        ripple = 0.10 * math.sin(s * 1.43) + 0.045 * math.sin(s * 3.84 + 0.3)
        lip = float(left(s)) + ripple
        water = float(apron.surface(xy(s, lip), line))
        base = world(s, lip - 1.45)
        edge = world(s, lip - 0.58)
        height = (
            max(edge[2] + 0.13, water + 0.42 + 0.12 * math.sin(s * 0.50)) + taper * 0.17
        )
        # Top skin, front of sod, shadowed undercut, exposed stratified dirt, buried toe.
        items = [(base[0], base[1], base[2] - 0.08)]
        for offset, z in [
            (-0.81, max(height - 0.04, grade(xy(s, lip - 0.81)) + 0.04)),
            (-0.06 + 0.12 * taper, height),
            (0.05 + 0.10 * taper, height - (0.10 + 0.11 * taper)),
            (-0.18, height - 0.30 * taper - 0.10),
            (-0.31, water + 0.19 + 0.055 * math.sin(s * 0.75)),
            (0.38, grade(xy(s, lip + 0.38)) - 0.12),
        ]:
            items.append((*xy(s, lip + offset), z))
        return np.array(items)

    distances = np.linspace(start, stop, 181)
    profiles = np.stack([profile(s) for s in distances])
    soil_colors = np.array(
        [
            [0.105, 0.112, 0.046],
            [0.15, 0.16, 0.058],
            [0.143, 0.145, 0.047],
            [0.072, 0.055, 0.025],
            [0.047, 0.034, 0.021],
            [0.13, 0.091, 0.056],
            [0.112, 0.090, 0.060],
        ]
    )
    for i, (s, prof) in enumerate(zip(distances, profiles)):
        for j, p in enumerate(prof):
            tint = (
                0.92 + 0.09 * math.sin(s * 0.79 + j * 0.32) + rng.uniform(-0.055, 0.055)
            )
            vert(
                p,
                [*(soil_colors[j] * tint), 0.0],
                (s / 2.35, p[2] / 1.7 if j >= 3 else np.dot(p[:2], B) / 2.35),
            )
        if i:
            for j in range(6):
                k = (i - 1) * 7 + j
                face(k, k + 7, k + 1)
                face(k + 7, k + 8, k + 1)
    # Source-space A x B is negative Z: the top triangles must face upwards.
    faces[:] = (
        [f[::-1] for f in faces]
        if np.cross(
            np.array(vertices)[faces[0][1]] - vertices[faces[0][0]],
            np.array(vertices)[faces[0][2]] - vertices[faces[0][0]],
        )[2]
        < 0
        else faces
    )
    for prev, nxt in zip(profiles[::10][:-1], profiles[::10][1:]):
        for a, b in ((0, 2), (2, 4), (4, 6)):
            for tri in ((prev[a], nxt[a], prev[b]), (nxt[a], nxt[b], prev[b])):
                physics.append((np.array(tri)[::-1], 5))
    surf = profiles[:, :3].reshape(-1, 3)
    topidx = []
    for i in range(len(distances) - 1):
        for j in range(2):
            k = i * 3 + j
            topidx.extend(((k, k + 3, k + 1), (k + 3, k + 4, k + 1)))
    top = Triangulation(*surf[:, :2].T, triangles=topidx)
    from matplotlib.tri import LinearTriInterpolator

    top_z = LinearTriInterpolator(top, surf[:, 2])

    # Tangled, draping roots occur in colonies separated by bare soil and embedded stones.
    def root(s, size):
        section = profile(s)
        head = section[2] + np.r_[B * 0.03, -0.05]
        length = rng.uniform(0.18, 0.48) * size
        slide = rng.uniform(-0.21, 0.21) * size

        def strand(begin, length, width, offset):
            last = None
            for t in [0.0, 0.23, 0.56, 0.79, 1.0]:
                centre = (
                    begin
                    + np.r_[
                        A * (offset * t + 0.035 * math.sin(t * 8 + s))
                        + B * (0.045 * math.sin(t * 5 + s) - 0.15 * t),
                        -length * t,
                    ]
                )
                ring = []
                for a in range(4):
                    angle = a * math.pi * 0.5
                    p = (
                        centre
                        + np.r_[
                            (A * math.cos(angle) + B * math.sin(angle))
                            * width
                            * (1.0 - 0.91 * t),
                            0.0,
                        ]
                    )
                    ring.append(
                        vert(p, [0.123, 0.087, 0.043, 0.0], (s * 0.53 + t, a * 0.23))
                    )
                if last:
                    for a in range(4):
                        b = (a + 1) % 4
                        face(last[a], ring[a], last[b])
                        face(ring[a], ring[b], last[b])
                last = ring

        strand(head, length, rng.uniform(0.012, 0.023) * size, slide)
        strand(
            head + np.r_[A * slide * 0.35, -length * 0.38],
            length * 0.50,
            0.010 * size,
            -slide * 0.57,
        )

    for s in rng.uniform(start + 0.7, stop - 0.7, 105):
        for ds in rng.uniform(-0.20, 0.2, rng.integers(2, 5)):
            root(s + ds, rng.uniform(0.70, 1.35))

    palette = np.array(
        [
            [0.162, 0.150, 0.124],
            [0.232, 0.212, 0.176],
            [0.104, 0.116, 0.111],
            [0.155, 0.126, 0.094],
            [0.255, 0.249, 0.220],
            [0.149, 0.143, 0.134],
            [0.12, 0.134, 0.127],
        ]
    )
    pebbles = 0
    large = 0
    for attempt in range(10000):
        major = large < 12
        if not major and pebbles >= 1570:
            break
        s = rng.uniform(12.0, 57.0)
        outer = float(right(s))
        beyond = rng.uniform(-4.8, 3.7) if not major else rng.uniform(-1.7, 1.4)
        p = world(s, outer + beyond)
        water = float(apron.surface(p[:2], line))
        rel = p[2] - water
        if occupied(p[:2]) or not -0.98 < rel < 0.82:
            continue
        lobe = 0.5 + 0.5 * math.sin(s * 0.56 + 0.88 * math.sin(s * 0.29))
        weight = np.exp(
            -(((beyond + 0.3 + 0.8 * math.sin(0.28 * s)) / (1.8 + 0.8 * lobe)) ** 2)
        ) * (0.25 + 0.75 * lobe)
        if not major and rng.random() > weight:
            continue
        radius = (
            rng.uniform(0.26, 0.43)
            if major
            else rng.uniform(0.035, 0.17) * (0.82 + 0.3 * lobe)
        )
        aspect = rng.uniform(0.54, 0.86)
        angle = rng.uniform(0, math.pi)
        u = np.array([math.cos(angle), math.sin(angle)]) * radius
        v = np.array([-math.sin(angle), math.cos(angle)]) * radius * aspect
        cap = (
            rng.uniform(0.12, 0.19)
            if major
            else min(0.089, radius * rng.uniform(0.30, 0.58))
        )
        tint = palette[rng.integers(len(palette))] * rng.uniform(0.84, 1.14)
        count = 6 if major else rng.integers(5, 9)
        rings = []
        for k in range(count):
            a = (2 * math.pi / count) * (k + rng.uniform(-0.16, 0.16))
            q = (math.cos(a) * u + math.sin(a) * v) * rng.uniform(0.88, 1.1)
            rings.append(q)
        top_point = (
            p + np.r_[u * rng.uniform(-0.18, 0.18) + v * rng.uniform(-0.22, 0.22), cap]
        )
        upper = vert(top_point, [*tint, 1.0], p[:2] * 0.21)
        rim = []
        shoulder = []
        for q in rings:
            near = p[:2] + q
            z = grade(near)
            rim.append(vert(np.r_[near, z - 0.021], [*(tint * 0.68), 1.0], near * 0.21))
            shoulder.append(
                vert(
                    np.r_[p[:2] + q * 0.70, z + cap * rng.uniform(0.65, 0.88)],
                    [*(tint * 0.92), 1.0],
                    near * 0.21,
                )
            )
        for k in range(count):
            nxt = (k + 1) % count
            face(shoulder[k], shoulder[nxt], upper)
            face(rim[k], rim[nxt], shoulder[k])
            face(rim[nxt], shoulder[nxt], shoulder[k])
            if major:
                physics.append(
                    (np.array([vertices[rim[k]], vertices[rim[nxt]], top_point]), 2)
                )
        large += int(major)
        pebbles += 1
    if large != 12 or len(physics) != 180:
        raise ValueError((large, len(physics)))

    def plant(s, side, kind, height):
        p = world(s, side)
        if occupied(p[:2]):
            return
        water = float(apron.surface(p[:2], line))
        on_lip = top_z(*p[:2])
        if not np.ma.is_masked(on_lip):
            p[2] = max(p[2], float(on_lip))
        if p[2] < water + 0.09:
            return
        plants.append(
            dict(
                kind=kind,
                position=(p * REFLECT - [0, 0, 1.4]).round(3).tolist(),
                height_cm=round(height, 3),
                yaw=round(rng.uniform(-180, 180), 4),
                breadth=round(rng.uniform(0.88, 1.29), 4),
            )
        )

    for s in rng.uniform(start + 0.2, stop - 0.2, 3200):
        inland = rng.uniform(0.01, 5.6)
        # An interlocking crest runs to the edge, with occasional long ochre seed-heads.
        if inland > 1.9 and rng.random() < 0.39:
            continue
        kind = str(
            rng.choice(
                ["wild_a", "wild_b", "rye", "sedge", "rush"],
                p=[0.31, 0.25, 0.25, 0.12, 0.07],
            )
        )
        plant(
            s,
            float(left(s)) - inland,
            kind,
            rng.uniform(38, 79) * (1.12 if kind == "rye" else 1.0),
        )
    for s in rng.uniform(start, stop, 1050):
        inland = rng.uniform(1.2, 7.6) + 0.68 * math.sin(0.48 * s)
        if rng.random() > 0.62 + 0.35 * math.sin(s * 0.48 + inland * 0.43):
            continue
        kind = str(
            rng.choice(["wild_a", "wild_b", "rye", "sedge"], p=[0.28, 0.22, 0.29, 0.21])
        )
        plant(s, float(right(s)) + inland, kind, rng.uniform(30, 67))
    for previous in d.read(d.ROOT / "out/pwr/river-erosion/shore-finish/planting.json"):
        p = np.array(previous["position"]) / REFLECT
        s, side = apron.coordinates(p[:2])
        if (
            10.0 <= s <= 65.0
            and left(max(s, left.x[0])) - 7.0 < side < right(max(s, right.x[0])) + 8.0
        ):
            continue
        if occupied(p[:2]) or grade(p[:2]) - float(apron.surface(p[:2], line)) < 0.11:
            continue
        plants.append(
            dict(
                previous,
                position=[
                    *previous["position"][:2],
                    round(grade(p[:2]) * 100.0 - 1.4, 3),
                ],
            )
        )
    vertices = np.asarray(vertices)
    faces = np.asarray(faces)
    normal = np.zeros_like(vertices)
    tris = vertices[faces]
    normals = np.cross(tris[:, 1] - tris[:, 0], tris[:, 2] - tris[:, 0])
    for col in range(3):
        np.add.at(normal, faces[:, col], normals)
    normal /= np.maximum(np.linalg.norm(normal, axis=1, keepdims=True), 1.0e-12)
    ART.mkdir(exist_ok=True)
    save(
        "surface.json",
        dict(
            origin_cm=(ORIGIN * REFLECT).tolist(),
            positions=((vertices - ORIGIN) * REFLECT).round(3).tolist(),
            faces=faces.tolist(),
            normals=(normal * [1.0, -1.0, 1.0]).round(5).tolist(),
            uv=np.round(uv, 5).tolist(),
            colors=np.round(colors, 4).tolist(),
        ),
    )
    np.savez_compressed(
        ART / "support.npz",
        triangles_m=np.stack([t for t, _ in physics]),
        materials=np.array([m for _, m in physics], dtype=np.int16),
    )
    save("planting.json", plants)
    bounds = np.array(
        [
            [float(left(max(s, left.x[0]))), float(right(max(s, right.x[0])))]
            for s in np.arange(10, 69, 1.0)
        ]
    )
    save("banks.json", dict(distance_range=[10, 68], banks=bounds.round(5).tolist()))
    save(
        "survey.json",
        dict(
            sod_length_m=stop - start,
            sod_sections=180,
            cobbles=pebbles,
            large_cobbles=large,
            planting=len(plants),
            physics_faces=len(physics),
            faces=len(faces),
            terrain_sha256=hashlib.sha256(
                (OUT / "terrain/runtime-master.r16").read_bytes()
            ).hexdigest(),
            rock_ledger_sha256=hashlib.sha256(
                (OUT / "dressing/decor-moves.json").read_bytes()
            ).hexdigest(),
        ),
    )
    print(d.read(ART / "survey.json"))


if __name__ == "__main__":
    build()
