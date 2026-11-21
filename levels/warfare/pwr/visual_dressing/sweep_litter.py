"""Native centimetre-scale needles, sedges, cones, fractured chips and weathered wood."""

import math
import numpy as np

from prepare_alpine_verges import ROOT, read, sha256

FOLDER = "/Game/MJOLNIR/GrassPilot/Playable"
OUT = ROOT / "out/pwr/sweep-polish/round18/verges"
# Eight cells. Bark and end grain use the lower half of this same 1K atlas.
REGIONS = {
    "needle": (0, 0, 0.25, 0.25),
    "grass": (0.25, 0, 0.25, 0.25),
    "gold": (0.5, 0, 0.25, 0.25),
    "stone": (0.75, 0, 0.25, 0.25),
    "cone": (0, 0.25, 0.25, 0.25),
    "twig": (0.25, 0.25, 0.25, 0.25),
    "moss": (0.5, 0.25, 0.25, 0.25),
    "shade": (0.75, 0.25, 0.25, 0.25),
    "bark": (0, 0.5, 0.5, 0.5),
    "end": (0.5, 0.5, 0.5, 0.5),
}


class Mesh:
    def __init__(self):
        self.v = []
        self.uv = []
        self.f = []
        self.parts = {}

    def part(self, name, points, faces, tex, uv):
        index = len(self.v)
        self.v.extend(points)
        u, v, w, h = REGIONS[tex]
        self.uv.extend(
            [(u + w * (0.014 + 0.972 * s), v + h * (0.014 + 0.972 * t)) for s, t in uv]
        )
        self.f.extend([[index + i for i in f] for f in faces])
        self.parts[name] = self.parts.get(name, 0) + len(faces)

    def data(self):
        p = np.array(self.v)
        f = np.array(self.f)
        n = np.zeros_like(p)
        t = p[f]
        nf = np.cross(t[:, 1] - t[:, 0], t[:, 2] - t[:, 0])
        for i in range(3):
            np.add.at(n, f[:, i], nf)
        n /= np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-10)
        # UE MeshDescription uses clockwise winding. Values are authored directly in engine local cm.
        return dict(
            positions=p.round(5).tolist(),
            normals=n.round(6).tolist(),
            faces=f[:, [0, 2, 1]].tolist(),
            uv=np.asarray(self.uv).round(6).tolist(),
            parts=self.parts,
        )


def blade(m, part, base, az, length, high, width, tex, rng):
    f = np.array([np.cos(az), np.sin(az), 0])
    side = np.array([-f[1], f[0], 0])
    b = np.asarray(base)
    mid = b + f * (length * 0.53) + [0, 0, high * 0.73]
    end = b + f * length + [0, 0, high + rng.uniform(-0.14, 0.14)]
    points = [
        b - side * width * 0.47,
        b + side * width * 0.47,
        mid - side * width * 0.37,
        mid + side * width * 0.37,
        end,
    ]
    m.part(
        part,
        points,
        [(0, 2, 1), (1, 2, 3), (2, 4, 3)],
        tex,
        [(0.18, 0.93), (0.82, 0.93), (0.26, 0.48), (0.74, 0.48), (0.50, 0.05)],
    )


def twig(m, a, b, ra, rb, tex, rng):
    a = np.asarray(a, dtype=float)
    b = np.asarray(b, dtype=float)
    axis = b - a
    axis /= np.linalg.norm(axis)
    t = np.cross(axis, [0, 0, 1])
    t /= max(np.linalg.norm(t), 0.0001)
    s = np.cross(axis, t)
    points = []
    uv = []
    faces = []
    for j, (p, r) in enumerate(((a, ra), (b, rb))):
        for k in range(5):
            theta = k * np.pi * 2 / 5
            points.append(p + r * (np.cos(theta) * t + np.sin(theta) * s))
            uv.append((k / 5, 0.94 - 0.88 * j))
    for k in range(5):
        l = (k + 1) % 5
        faces.extend([(k, l, 5 + k), (l, 5 + l, 5 + k)])
    m.part("wood splinters", points, faces, tex, uv)


def cone(m, base, rng):
    az = rng.uniform(0, 2 * np.pi)
    axis = np.array([np.cos(az), np.sin(az), 0.26])
    axis /= np.linalg.norm(axis)
    side = np.array([-np.sin(az), np.cos(az), 0])
    up = np.cross(axis, side)
    base = np.array(base)
    length = rng.uniform(4.6, 6.1)
    rad = length * 0.30
    for j in range(7):
        q = (j + 0.5) / 7
        r = rad * (np.sin(q * np.pi) ** 0.66)
        for k in range(7):
            theta = 2 * np.pi * (k + j * 0.40) / 7
            out = np.cos(theta) * side + np.sin(theta) * up
            across = np.cross(axis, out)
            c = base + axis * length * q + out * r * 0.60
            a = c + out * r * 0.34 - axis * 0.35
            tip = c + out * r * 0.54 + axis * 0.38
            pts = [
                a - across * 0.44,
                a + across * 0.44,
                tip + across * 0.42,
                tip - across * 0.41,
                tip + out * 0.24,
            ]
            m.part(
                "cone scales",
                pts,
                [(0, 1, 4), (1, 2, 4), (2, 3, 4), (3, 0, 4)],
                "cone",
                [(0.2, 0.98), (0.80, 0.98), (0.93, 0.36), (0.12, 0.40), (0.5, 0.12)],
            )


def chip(m, p, r, rng):
    p = np.array(p)
    a = rng.uniform(0, 6.28)
    x = rng.uniform(0.55, 1.20)
    pts = [p + [0, 0, r * 0.37]]
    for j in range(5):
        t = a + j * np.pi * 2 / 5
        pts.append(
            p + [np.cos(t) * r, np.sin(t) * r * x, -0.06 + rng.uniform(-0.04, 0.075)]
        )
    m.part(
        "chips",
        pts,
        [(0, j + 1, 1 + (j + 1) % 5) for j in range(5)],
        "stone",
        [
            (0.45, 0.44),
            (0.07, 0.39),
            (0.39, 0.04),
            (0.88, 0.23),
            (0.80, 0.84),
            (0.23, 0.87),
        ],
    )


def patch(index):
    rng = np.random.default_rng(615017 + index)
    m = Mesh()
    for fan in range([8, 10, 6][index]):
        x, y = rng.normal(0, [14.0, 9.0])
        a = rng.uniform(0, 2 * np.pi)
        for j in range(rng.integers(7, 13)):
            az = a + rng.normal(0, 0.57)
            base = [
                x + rng.normal(0, 2.8),
                y + rng.normal(0, 2.8),
                rng.uniform(0.32, 0.86),
            ]
            for side in (-1, 1):
                blade(
                    m,
                    "paired needles",
                    base,
                    az + side * rng.uniform(0.05, 0.28),
                    rng.uniform(4.3, 11.2),
                    rng.uniform(-0.15, 1.09),
                    rng.uniform(0.23, 0.43),
                    "gold" if rng.random() < 0.38 else "needle",
                    rng,
                )
    for clump in range([4, 2, 6][index]):
        x, y = rng.normal(0, [14.0, 8.0])
        phase = rng.uniform(0, 6.28)
        for j in range(rng.integers(8, 14)):
            az = phase + rng.uniform(-2.3, 2.3)
            blade(
                m,
                "sedge blades",
                [x + rng.normal(0, 1.3), y + rng.normal(0, 1.3), -0.15],
                az,
                rng.uniform(5.0, 15.0),
                rng.uniform(5.5, 22.0),
                rng.uniform(0.47, 0.96),
                "grass" if rng.random() < 0.82 else "gold",
                rng,
            )
    for j in range(3 if index != 2 else 1):
        p = np.r_[rng.uniform([-17, -14], [17, 14]), 0.59]
        a = rng.uniform(0, 6.28)
        b = p + [
            np.cos(a) * rng.uniform(12, 22),
            np.sin(a) * rng.uniform(12, 22),
            rng.uniform(0.0, 1.00),
        ]
        twig(m, p, b, 0.43, 0.21, "twig", rng)
        end = b + [np.cos(a + 0.70) * 6, np.sin(a + 0.70) * 6, 0.64]
        twig(m, 0.35 * p + 0.65 * b, end, 0.25, 0.075, "twig", rng)
    for j in range(8 if index == 1 else 4):
        chip(
            m, [*rng.uniform([-23, -19], [23, 19]), 0.03], rng.uniform(0.77, 2.95), rng
        )
    if index == 1:
        cone(m, [2.6, 4.0, 1.05], rng)
    return m.data()


def deadpine():
    rng = np.random.default_rng(180016)
    m = Mesh()
    nr = 15
    nl = 13
    phase = rng.uniform(-1, 1, nr)
    pts = []
    uvs = []
    faces = []
    # Deflected limbs, a decayed top strip and a splintered cut preserve the tree's tapered silhouette.
    directions = np.arange(nr) * math.tau / nr
    for j in range(nl):
        f = j / (nl - 1)
        for k, t in enumerate(directions):
            x = (
                450 * (f - 0.5)
                + (1 - f) ** 7 * (4.5 * np.sin(3 * t) + 2.1 * np.cos(7 * t))
                + f**8 * 9.0 * phase[k]
            )
            r = (29.3 - 8.9 * f) * (
                1 + 0.076 * phase[k] + 0.075 * np.sin(2 * t + x * 0.013)
            )
            if k in (3, 4):
                r *= 0.86 + 0.14 * np.sin(3 * f)
            pts.append(
                [
                    x,
                    np.cos(t) * r + 3.5 * np.sin(4 * f),
                    np.sin(t) * r + 3 * np.sin(5 * f),
                ]
            )
            uvs.append((0.014 + 0.972 * (k / (nr - 1)), f))
    for j in range(nl - 1):
        for k in range(nr):
            a = j * nr + k
            b = j * nr + (k + 1) % nr
            c = a + nr
            d = b + nr
            faces.extend([(a, b, c), (b, d, c)])
    m.part("ribbed bark", pts, faces, "bark", uvs)
    for j in [0, nl - 1]:
        ring = np.array(pts[j * nr : j * nr + nr])
        center = ring.mean(0)
        center[0] += (1 if j == 0 else -1) * 2.8
        uv = [(0.5, 0.5)] + [
            (0.50 + 0.46 * np.cos(t), 0.50 + 0.46 * np.sin(t)) for t in directions
        ]
        order = [(0, k + 1, 1 + (k + 1) % nr) for k in range(nr)]
        if j == 0:
            order = [(a, c, b) for a, b, c in order]
        m.part("broken heartwood", np.vstack((center, ring)), order, "end", uv)
    for a, b, ra, rb in [
        ([-31, 17, 14], [-42, 36, 22], 7.8, 4.5),
        ([81, -16, 10], [107, -29, 21], 5.7, 3.1),
        ([153, 18, 4], [175, 32, 8], 3.7, 1.9),
    ]:
        twig(m, a, b, ra, rb, "bark", rng)
    return m.data()


def write_sources():
    from build_sweep_banks import save

    plants = []
    for i, name in enumerate(
        [
            "SM_PWR_SweepLitter_A",
            "SM_PWR_SweepLitter_B",
            "SM_PWR_SweepLitter_C",
            "SM_PWR_SweepDeadPine",
        ]
    ):
        data = patch(i) if i < 3 else deadpine()
        p = OUT / (name + ".json")
        save(p, data)
        plants.append(
            dict(
                name=name,
                package=FOLDER + "/" + name,
                file=p.name,
                sha256=sha256(p),
                vertices=len(data["positions"]),
                triangles=len(data["faces"]),
                slot="ForestDebris",
                parts=data["parts"],
            )
        )
    return plants


def placements(field, road, data, cam):
    from build_sweep_banks import save

    # Surveyed wheel-track margins, east/north in metres. Width of the growth changes
    # independently of camera position and the strip continues past both ends of the view.
    edge = np.array(
        [
            [-586.9, -552.2],
            [-589.4, -546.15],
            [-591.28, -543.13],
            [-591.72, -542.48],
            [-592.33, -541.25],
            [-593.10, -538.91],
            [-594.15, -535.27],
            [-596.9, -531.8],
            [-599.3, -526.1],
            [-600.6, -521.0],
        ]
    )
    dist = np.r_[0, np.cumsum(np.linalg.norm(np.diff(edge, axis=0), axis=1))]
    rng = np.random.default_rng(180631)
    out = [[] for i in range(3)]
    nearverts = [
        np.asarray(read(OUT / ("SM_PWR_SweepLitter_" + s + ".json"))["positions"])
        for s in "ABC"
    ]
    # Elongated depositional pockets. Leave gaps of bare rut and densely overlap the inside fringes.
    cluster = np.arange(0.5, dist[-1], 0.72) + rng.uniform(
        -0.30, 0.30, len(np.arange(0.5, dist[-1], 0.72))
    )
    uvzone = []
    for k, s in enumerate(cluster):
        i = np.clip(np.searchsorted(dist, s) - 1, 0, len(edge) - 2)
        direction = edge[i + 1] - edge[i]
        direction /= np.linalg.norm(direction)
        normal = np.array([-direction[1], direction[0]])
        p0 = np.array([np.interp(s, dist, edge[:, j]) for j in (0, 1)])
        width = 0.76 + 0.41 * np.sin(1.62 * s) + 0.34 * np.cos(0.58 * s)
        for j in range(rng.integers(5, 11)):
            t = rng.normal(0, 0.34)
            offset = rng.uniform(-0.11, max(0.32, width)) * 1.45 + 0.18 * np.sin(
                s * 0.91
            )
            xy = p0 + direction * t + normal * offset
            bi = rng.choice(3, p=[0.44, 0.20, 0.36])
            scale = rng.uniform(0.68, 1.27)
            if bi == 1 and rng.random() < 0.28:
                scale *= 1.14
            yaw = np.degrees(-np.arctan2(direction[1], direction[0])) + rng.uniform(
                -73, 73
            )
            rot = field.rotation(xy, yaw)
            h = float(field.height(xy))
            xf = np.r_[
                xy * [100, -100],
                (h + 0.002) * 100,
                rot.as_quat(),
                [scale, scale, scale],
            ]
            out[bi].append(xf)
            w = (rot.apply(nearverts[bi] * scale) * 0.01 + xf[:3] * 0.01) * [1, -1, 1]
            uv = cam.project(w)
            count = (
                (uv[:, 2] > 0)
                & (uv[:, 0] >= 0)
                & (uv[:, 0] < 0.17)
                & (uv[:, 1] >= 0.72)
                & (uv[:, 1] <= 0.98)
            ).sum()
            if count:
                uvzone.append(
                    dict(
                        variant="ABC"[bi],
                        station=float(s),
                        world_xy=xy.tolist(),
                        silhouette_vertices=int(count),
                        bounds=[uv[:, :2].min(0).tolist(), uv[:, :2].max(0).tolist()],
                    )
                )
    if len(uvzone) < 8 or len({v["variant"] for v in uvzone}) != 3:
        raise ValueError(
            "Surveyed left margin does not place all three physical details in the near driver's frame"
        )
    save(
        OUT / "foreground-projection.json",
        dict(
            region=[0, 0.72, 0.17, 0.98],
            clusters_intersected=len(uvzone),
            actual_mesh_vertices_inside=sum(v["silhouette_vertices"] for v in uvzone),
            instances=uvzone,
        ),
    )
    return out


def wood_pose(field, data):
    from build_sweep_banks import bank_top

    row = read(OUT / "SM_PWR_SweepDeadPine.json")
    v = np.array(row["positions"]) * 0.01
    a, b = np.array([-598.28, -534.18]), np.array([-597.41, -529.71])
    mid = (a + b) * 0.5
    direction = b - a
    yaw = -np.degrees(np.arctan2(*direction[::-1]))
    rot = field.rotation(mid, yaw)
    offset = rot.apply(v)
    xy = mid + offset[:, :2] * [1, -1]
    top = bank_top(xy, field, data)
    z = float(np.quantile(top - offset[:, 2], 0.986)) - 0.014
    xyz = np.column_stack((xy, z + offset[:, 2]))
    xf = np.r_[mid * [100, -100], z * 100, rot.as_quat(), 1.0, 1.0, 1.0]
    # Core faces including knots are shared directly with Blam rather than a cylinder approximation.
    tri = xyz[np.array(row["faces"])[:, [0, 2, 1]]]
    # Unreal-to-world Y reflection reverses its native clockwise winding.
    tri = tri[:, [0, 2, 1]]
    return (
        xf,
        tri,
        dict(
            source=sha256(OUT / "SM_PWR_SweepDeadPine.json"),
            faces=len(tri),
            support_burial_m=0.014,
        ),
    )
