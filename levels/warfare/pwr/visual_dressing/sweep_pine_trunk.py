"""Fit an enclosing tapered wood shell to the original native trunk. Units are centimetres."""

import numpy as np
from build_mature_pine_collision import BARK, SCALE, read_mesh
from scipy.optimize import linprog
from scipy.spatial import ConvexHull


def source(path):
    verts, faces, _ = read_mesh(path, 1, BARK)
    verts *= SCALE
    edges = np.unique(
        np.sort(
            np.concatenate([faces[:, [0, 1]], faces[:, [1, 2]], faces[:, [2, 0]]]),
            axis=1,
        ),
        axis=0,
    )
    return verts, verts[edges]


def section(edges, z):
    a, b = edges[:, 0], edges[:, 1]
    sel = (a[:, 2] - z) * (b[:, 2] - z) < 0
    if not np.any(sel):
        return edges.reshape(-1, 3)[np.abs(edges.reshape(-1, 3)[:, 2] - z) < 1.0e-6]
    a, b = a[sel], b[sel]
    t = (z - a[:, 2]) / (b[:, 2] - a[:, 2])
    return a + (b - a) * t[:, None]


def shell(verts, edges, heights, sides, az):
    h = np.asarray(heights)
    theta = np.radians(az) + np.arange(sides) * 2 * np.pi / sides
    normal = np.c_[np.cos(theta), np.sin(theta)]
    sections = [section(edges, z) for z in h]
    inputs = [
        np.vstack(
            (v, sections[i + 1], verts[(verts[:, 2] > h[i]) & (verts[:, 2] < h[i + 1])])
        )
        for i, v in enumerate(sections[:-1])
    ]
    # The linear support bound only needs convex vertices in (height,support).
    # Constraints are exact for every source triangle, including sliced edges.
    supports = []
    for axis in normal:
        rows = []
        data = []
        for i, p in enumerate(inputs):
            u = np.c_[(p[:, 2] - h[i]) / (h[i + 1] - h[i]), p[:, :2] @ axis]
            ex = u[ConvexHull(u).vertices]
            step = np.zeros((len(ex), len(h)))
            step[:, i] = 1 - ex[:, 0]
            step[:, i + 1] = ex[:, 0]
            rows.append(step)
            data.append(ex[:, 1])
        cost = np.array([1.1, 1.6, *([1.0] * max(0, len(h) - 3)), 0.65])
        lp = linprog(
            cost,
            A_ub=-np.vstack(rows),
            b_ub=-np.hstack(data),
            bounds=(None, None),
            method="highs",
        )
        if not lp.success:
            raise ValueError(lp.message)
        supports.append(lp.x + 0.015)
    s = np.array(supports).T
    columns = []
    for i in range(sides):
        i2 = (i + 1) % sides
        columns.append(np.linalg.solve(normal[[i, i2]], s[:, [i, i2]].T).T)
    ring = np.stack(columns, axis=1)
    if (ring @ normal.T - s[:, None, :]).max() > 0.001:
        raise ValueError("Non-convex contour")
    pts = np.c_[ring.reshape(-1, 2), np.repeat(h, sides)]
    faces = []
    for i in range(len(h) - 1):
        for k in range(sides):
            a = i * sides + k
            b = i * sides + (k + 1) % sides
            faces.extend([[a, b, b + sides], [a, b + sides, a + sides]])
    for i in range(1, sides - 1):
        faces.append([0, i + 1, i])
        z = (len(h) - 1) * sides
        faces.append([z, z + i, z + i + 1])
    return pts, np.array(faces), ring, normal, s, inputs


def compare(verts, edges, heights, sides, az):
    pts, faces, rings, normal, support, inputs = shell(verts, edges, heights, sides, az)
    maxdef = max(
        np.max(
            src[:, :2] @ normal.T
            - ((1 - r[:, None]) * support[i] + r[:, None] * support[i + 1])
        )
        for i, src in enumerate(inputs)
        for r in [(src[:, 2] - heights[i]) / (heights[i + 1] - heights[i])]
    )
    # Horizontal-section distances from the enclosing shell to the nearest actual
    # bark intersection point. Using points rather than entire edges is conservative.
    samples = np.r_[
        np.linspace(heights[0], 200, 31),
        np.linspace(200, heights[-1] - 0.5, 65),
        heights[1:-1],
    ]
    all_gaps = []
    zs = []
    for z in samples:
        i = np.searchsorted(heights, z, side="right") - 1
        i = np.clip(i, 0, len(heights) - 2)
        t = (z - heights[i]) / (heights[i + 1] - heights[i])
        r = rings[i] * (1 - t) + rings[i + 1] * t
        s = (
            r[:, None, :]
            + (np.roll(r, -1, axis=0) - r)[:, None, :]
            * np.linspace(0, 1, 9, endpoint=False)[None, :, None]
        ).reshape(-1, 2)
        cut = section(edges, z)
        ds = np.sqrt(np.sum((s[:, None, :] - cut[None, :, :2]) ** 2, axis=2)).min(
            axis=1
        )
        all_gaps.extend(ds)
        zs.extend([z] * len(ds))
    gaps, zs = np.array(all_gaps), np.array(zs)
    stats = {
        key: {
            "p95_cm": round(float(np.percentile(gaps[m], 95)), 3),
            "max_cm": round(float(gaps[m].max()), 3),
        }
        for key, m in [
            ("ground_to_2m", (zs >= 0) & (zs <= 200)),
            ("above_2m", zs > 200),
            ("shallow_subsurface", zs < 0),
        ]
    }
    return (
        pts,
        faces,
        {
            "continuous_max_enclosure_deficit_cm": float(maxdef),
            "horizontal_bark_gap_samples": len(gaps),
            "gaps": stats,
        },
    )
