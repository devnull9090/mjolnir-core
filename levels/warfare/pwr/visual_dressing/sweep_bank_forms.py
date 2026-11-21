"""Surveyed shoulder forms, exposed granite, and bank-foot plant communities for round 17."""

from collections import defaultdict
import numpy as np
from scipy.spatial.transform import Rotation

BANKS = [
    ("west outcrop", (-602.7, -531.7), (5.0, 2.85), -6, 0.51),
    ("west forest apron", (-601.5, -535.4), (5.3, 2.9), 24, 0.52),
    ("east road bank", (-576.9, -518.9), (16.75, 5.1), 72, 0.81),
    ("east root collar", (-570.5, -505.7), (9.5, 4.65), 55, 0.69),
    ("granite brow", (-601.96, -532.13), (2.24, 1.29), -13, 1.22),
    ("granite knuckle", (-603.96, -532.69), (1.60, 1.18), -24, 1.12),
]


def smooth(a, b, x):
    t = np.clip((x - a) / (b - a), 0, 1)
    return t * t * (3 - 2 * t)


def tile(i):
    if i < 4:
        return i % 2 * 0.5, i // 2 * 0.25, 0.5, 0.25
    return (i - 4) * 0.5, 0.5, 0.5, 0.5


def footprint(angle, index):
    if index >= 4:
        return (
            0.94
            + 0.073 * np.sin(3 * angle + 0.6 * index)
            + 0.044 * np.cos(5 * angle - 1.1 * index)
        )
    return (
        0.89
        + 0.131 * np.sin(3 * angle + 0.45 * index)
        + 0.093 * np.cos(5 * angle + index)
        + 0.047 * np.sin(8 * angle - 0.6 * index)
    )


def surface(i, lx, ly, r, x, y, side, rootdist):
    """Returns metres above the graded terrain. Below-grade skirt cannot appear at grazing angles."""
    if i >= 4:
        if i == 4:
            dome = np.interp(r, [0, 0.25, 0.5, 0.75, 1], [1, 0.99, 0.89, 0.62, -0.16])
            fractured = (
                0.99
                + 0.056 * np.cos(3.1 * x + 2.2 * y)
                + 0.047 * np.sin(6.0 * ly + 1.8 * lx)
            )
        else:
            dome = np.interp(r, [0, 0.25, 0.5, 0.75, 1], [1, 0.95, 0.85, 0.52, -0.17])
            fractured = (
                1 + 0.070 * np.cos(2.3 * x - 3.3 * y) + 0.04 * np.sin(5 * lx - 2 * ly)
            )
        return BANKS[i][4] * dome * fractured
    lip = 1 - smooth(0.30, 0.94, r)
    # Expose the tree's actual flared shoulders between these eroded lobes.
    root = 0.10 + 0.90 * smooth(0.75, 2.60, rootdist)
    lobe = (
        0.71
        + 0.22 * np.sin(x * 1.13 + y * 0.76)
        + 0.13 * np.sin(y * 1.71 - x * 0.58)
        + 0.09 * np.cos(x * 2.63 + y * 1.26)
    )
    h = BANKS[i][4] * lip * lobe * root
    h *= smooth(7.9, 12.35, np.abs(side))
    h = np.minimum(h, 0.024 + 0.85 * smooth(8.15, 13.15, np.abs(side)))
    return h - 0.29 * smooth(0.70, 0.99, r)


def communities(field, road, data):
    from build_sweep_banks import bank_top, to_xy

    rng = np.random.default_rng(170711)
    pats = defaultdict(list)
    centers = []
    for i, (name, center, radii, az, h) in enumerate(BANKS[:4]):
        # Visible groups separated by open litter. Shoots differ in height and inclination.
        n = [23, 27, 62, 43][i]
        a = rng.uniform(0, 2 * np.pi, n)
        r = np.sqrt(rng.uniform(0.09, 1.33, n))
        for p in to_xy(BANKS[i], r * np.cos(a), r * np.sin(a)):
            centers.append(
                (
                    p,
                    i,
                    rng.choice(["Ferns", "Tufts", "Sedge"], p=[0.28, 0.42, 0.30]),
                    False,
                )
            )
    for i in (4, 5):
        a = np.linspace(0, 2 * np.pi, 20, endpoint=False) + 0.2
        r = rng.uniform(0.86, 1.22, len(a))
        for j, p in enumerate(to_xy(BANKS[i], r * np.cos(a), r * np.sin(a))):
            centers.append((p, i, "Ferns" if j % 3 else "Tufts", True))
    pos = []
    meta = []
    for p, i, k, hero in centers:
        n = rng.integers(4, 9) if k == "Ferns" else rng.integers(7, 14)
        spread = rng.uniform(0.41, 0.91)
        phase = rng.uniform(0, 2 * np.pi)
        for j, t in enumerate(np.linspace(0, 2 * np.pi, n, endpoint=False)):
            a = t + phase + rng.uniform(-0.36, 0.36)
            rad = spread * np.sqrt(rng.random())
            pos.append(p + rad * np.array([np.cos(a), np.sin(a)]))
            meta.append((k, hero, rad))
    pos = np.array(pos)
    z = bank_top(pos, field, data)
    earth = bank_top(pos, field, data[:4])
    _, d = road.surveys(pos)
    trees = field.trunks.query(pos)[0]
    for j, p in enumerate(pos):
        key, hero, r = meta[j]
        if abs(d[j]) < 7.0 or trees[j] < 0.47 or z[j] - earth[j] > 0.21:
            continue
        if key == "Ferns":
            s = rng.uniform(1.25, 2.75) * (1.18 if hero else 1.0)
            h = s * rng.uniform(0.85, 1.22)
        elif key == "Sedge":
            s = rng.uniform(0.65, 1.46)
            h = rng.uniform(1.1, 2.4) * s
        else:
            s = rng.uniform(0.57, 1.15)
            h = rng.uniform(1.45, 2.6) * s
        rot = Rotation.from_euler(
            "zyx",
            [rng.uniform(-180, 180), rng.uniform(-8, 8), rng.uniform(-6, 6)],
            degrees=True,
        )
        pats[key].append(
            [p[0] * 100, -p[1] * 100, (z[j] - 0.009) * 100, *rot.as_quat(), s, s, h]
        )
    return pats
