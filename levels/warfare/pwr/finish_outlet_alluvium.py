"""Grade only the saved outlet's sod, wet mineral surface and six planted rows."""

from pathlib import Path
import json
import math
import sys
import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "terrain"))
import headwater_dressing as d
import outlet_apron as a

BASE = d.ROOT / "out/pwr/river-apron"
WORK = BASE / "finish37"
SCALE = np.array([100.0, -100.0, 100.0])
RNG = np.random.default_rng(37051)


def write(name, obj):
    (WORK / name).write_text(json.dumps(obj, allow_nan=False, separators=(",", ":")))


def build():
    field = d.load_heightfield(BASE / "terrain/runtime-master.json")
    river = d.read(BASE / "terrain/terrain.geometry.json")["watercourses"][0]
    line = np.asarray(river["erosion_reach"]["centreline_m"])
    left, right = a.curves(line)
    art = d.read(BASE / "bank/surface.json")
    origin = np.array(art["origin_cm"]) / SCALE
    verts = np.asarray(art["positions"]) / SCALE + origin
    colors = np.asarray(art["colors"])
    uv = np.asarray(art["uv"])
    s, side = a.coordinates(verts[:, :2])
    # Keep the delivered physical cap and its silhouette; break the highlight along its front.
    ramp = verts[: 181 * 7].reshape(181, 7, 3)
    sod_colors = colors[: 181 * 7].reshape(181, 7, 4)
    for i, section in enumerate(ramp):
        along = s[7 * i]
        rind = 0.5 + 0.5 * math.sin(along * 1.73 + 0.88 * math.sin(along * 0.63))
        crumb = 0.5 + 0.5 * math.sin(along * 4.57)
        section[2:5, :2] += a.RIGHT[:2] * (
            0.053 * math.sin(along * 3.75) + 0.043 * math.cos(along * 7.1)
        )
        section[2:5, 2] -= 0.11 * (1 - rind) * (0.4 + 0.6 * crumb)
        pal = np.array(
            [
                [0.067, 0.066, 0.033],
                [0.081, 0.080, 0.040],
                [0.074, 0.066, 0.039],
                [0.11, 0.084, 0.060],
                [0.147, 0.120, 0.091],
                [0.142, 0.115, 0.085],
                [0.107, 0.098, 0.075],
            ]
        )
        pal[1:4] *= np.array(
            [0.59 + 0.51 * rind, 0.65 + 0.42 * rind, 0.69 + 0.4 * rind]
        )
        sod_colors[i, :, :3] = pal * (
            0.86 + 0.15 * crumb + 0.085 * math.sin(along * 2.3)
        )
    roots = (colors[:, 3] < 0.05) & (np.arange(len(verts)) >= 181 * 7)
    colors[roots, :3] = np.clip(colors[roots, :3] * [1.45, 1.55, 1.7], 0.0, 1.0)
    old_pebbles = colors[:, 3] > 0.98
    # The photographic material was too bright in direct sunlight. Darken individual
    # exposed clasts independently; preserve their silhouettes and contact shadows.
    damp = np.clip(
        (
            np.array([field.sample(*p) for p in verts[old_pebbles, :2]])
            - verts[old_pebbles, 2]
        )
        / 0.11,
        -1.0,
        1.0,
    )
    colors[old_pebbles, :3] *= (0.35 + 0.035 * damp[:, None]) * [0.90, 0.95, 1.04]
    tris = np.asarray(art["faces"])
    # Retain each measured contact and high point while rounding the existing flat shoulders.
    from scipy.sparse import coo_matrix
    from scipy.sparse.csgraph import connected_components
    from scipy.interpolate import CubicSpline

    first = int(np.flatnonzero(old_pebbles)[0])
    oldfaces = tris[tris[:, 0] >= first] - first
    edges = oldfaces[:, [0, 1, 1, 2, 2, 0]].reshape(-1, 2)
    graph = coo_matrix((np.ones(len(edges)), edges.T), shape=(len(verts) - first,) * 2)
    count_groups, labels = connected_components(graph, directed=False)
    oldv, oldc = verts, colors
    curved_v = []
    curved_f = []
    curved_c = []
    curved_uv = []
    for group in range(count_groups):
        ids = first + np.flatnonzero(labels == group)
        crown = oldv[ids[0]]
        rim = oldv[ids[1::2]]
        count = 8 if len(rim) < 7 else 11
        ring = CubicSpline(
            np.arange(len(rim) + 1), np.vstack((rim, rim[0])), bc_type="periodic"
        )(np.arange(count) * len(rim) / count)
        center = np.mean(rim, axis=0)
        phase = RNG.uniform(-np.pi, np.pi)
        az = np.arange(count) * 2 * np.pi / count
        tint = oldc[ids[0], :3]
        start = first + len(curved_v)
        # A broad rounded shoulder runs down past the damp contact in the gravel.
        rings = [(1.0, 0.0), (0.94, 0.30), (0.73, 0.64), (0.43, 0.86), (0.18, 0.967)]
        for radial, elevation in rings:
            q = radial * ring[:, :2] + (1 - radial) * crown[:2]
            h = (
                ring[:, 2] * (1 - elevation)
                + elevation * crown[2]
                + 0.065
                * (crown[2] - center[2])
                * np.sin(az * 2 + phase)
                * np.sin(elevation * np.pi)
            )
            curved_v.extend(np.column_stack((q, h)))
            curved_c.extend([[*(tint * (0.76 + 0.24 * elevation)), 1.0]] * count)
            curved_uv.extend(q * 0.8 + h[:, None] * np.array([0.25, 0.43]))
        last = start + 4 * count
        tip = start + 5 * count
        curved_v.append(crown)
        curved_c.append([*tint, 1.0])
        curved_uv.append(crown[:2] * 0.8 + crown[2] * np.array([0.25, 0.43]))
        for k in range(count):
            j = (k + 1) % count
            for ring_i in range(4):
                v0 = start + ring_i * count
                curved_f.extend(
                    (
                        (v0 + k, v0 + j, v0 + count + k),
                        (v0 + j, v0 + count + j, v0 + count + k),
                    )
                )
            curved_f.append((last + k, last + j, tip))
    verts = np.vstack((oldv[:first], curved_v))
    colors = np.vstack((oldc[:first], curved_c))
    uv = np.vstack((uv[:first], curved_uv))
    tris = np.vstack((tris[tris[:, 0] < first], curved_f))
    # Accumulate rounded, visibly separated wet deposit. Flat caps sit 0.03-0.105 m above grade.
    newv = []
    newf = []
    newuv = []
    newc = []
    rocks = d.read(BASE / "dressing/flow-rocks.json")["rocks"]
    polygons = [np.array(r["footprint_m"]) for r in rocks]
    palette = np.array(
        [
            [0.187, 0.192, 0.177],
            [0.100, 0.130, 0.101],
            [0.158, 0.127, 0.076],
            [0.121, 0.139, 0.146],
            [0.254, 0.253, 0.212],
            [0.188, 0.145, 0.086],
            [0.086, 0.094, 0.094],
            [0.206, 0.181, 0.127],
        ]
    )
    pebble_count = 0
    for attempt in range(18000):
        if len(newf) >= 53000:
            break
        dist = RNG.uniform(10.98, 48.0)
        lo, hi = float(left(dist)), float(right(dist))
        cross = RNG.uniform(lo + 0.35, hi - 0.65)
        p = a.EYE[:2] + a.FORWARD_XY * dist + a.RIGHT[:2] * cross
        h = float(field.sample(*p))
        depth = float(a.surface(p, line)) - h
        if not 0.09 < depth < 1.19 or any(
            d.inside_polygon(p[:1], p[1:], poly)[0] for poly in polygons
        ):
            continue
        streak = 0.5 + 0.5 * math.sin(
            0.94 * cross + 0.18 * dist + 0.91 * math.sin(0.26 * dist)
        )
        if RNG.random() > 0.32 + 0.65 * streak:
            continue
        along = RNG.uniform(-0.57, 0.57)
        direction = a.FORWARD_XY * math.cos(along) + a.RIGHT[:2] * math.sin(along)
        other = np.array([-direction[1], direction[0]])
        radius = (
            RNG.uniform(0.085, 0.255)
            if RNG.random() < 0.68
            else RNG.uniform(0.22, 0.44)
        )
        rad2 = radius * RNG.uniform(0.52, 0.91)
        cap = min(RNG.uniform(0.055, 0.105), radius * RNG.uniform(0.29, 0.52))
        color = palette[RNG.integers(len(palette))] * RNG.uniform(0.82, 1.17)
        count = int(RNG.integers(5, 8))
        off = len(verts) + len(newv)
        jitter = RNG.uniform(-0.13, 0.13, count)
        ring = 2 * np.pi * (np.arange(count) + jitter) / count
        silhouette = (
            np.cos(ring)[:, None] * direction * radius
            + np.sin(ring)[:, None] * other * rad2
        ) * RNG.uniform(0.88, 1.10, (count, 1))
        rim = p + silhouette
        ground = field.sample(*rim.T)
        mid = p + silhouette * RNG.uniform(0.64, 0.79)
        top = (*tuple(p + direction * radius * RNG.uniform(-0.22, 0.22)), h + cap)
        newv.extend(np.column_stack((rim, ground - 0.018)))
        newv.extend(
            np.column_stack(
                (mid, field.sample(*mid.T) + cap * RNG.uniform(0.53, 0.83, count))
            )
        )
        newv.append(top)
        pebble_count += 1
        for j in range(count):
            k = (j + 1) % count
            newf.extend(
                (
                    (off + j, off + k, off + count + j),
                    (off + k, off + count + k, off + count + j),
                    (off + count + j, off + count + k, off + 2 * count),
                )
            )
        newc.extend(
            [[*(color * 0.71), 0.92]] * count
            + [[*(color * 0.96), 0.92]] * count
            + [[*color, 0.92]]
        )
        newuv.extend([q * 0.51 for q in rim] + [q * 0.51 for q in mid] + [p * 0.51])
    v = np.vstack((verts, newv))
    f = np.vstack((tris, newf))
    normal = np.zeros_like(v)
    for j in range(3):
        np.add.at(
            normal, f[:, j], np.cross(v[f[:, 1]] - v[f[:, 0]], v[f[:, 2]] - v[f[:, 0]])
        )
    normal /= np.maximum(1.0e-9, np.linalg.norm(normal, axis=1, keepdims=True))
    # Alpha distinguishes sky-exposed gravel, immersed stones, and dark root/soil.
    art.update(
        positions=((v - origin) * SCALE).round(3).tolist(),
        normals=(normal * [1, -1, 1]).round(5).tolist(),
        faces=f.tolist(),
        uv=np.vstack((uv, newuv)).round(5).tolist(),
        colors=np.vstack((colors, newc)).round(4).tolist(),
    )
    write("surface.json", art)
    plants = d.read(BASE / "bank/planting.json")
    ids = {}
    newplants = {}
    stats = {}
    for row in plants:
        kind = row["kind"]
        idx = ids.get(kind, 0)
        ids[kind] = idx + 1
        p = np.array(row["position"]) / SCALE
        dist, cross = a.coordinates(p[:2])
        if (
            kind == "willow"
            or not 12 < dist < 59
            or not -6.7 < cross - left(dist) < 0.7
        ):
            continue
        phase = 0.5 + 0.5 * math.sin(
            0.55 * dist + 0.97 * math.sin(0.42 * dist) + 0.52 * cross
        )
        native = {
            "wild_a": 0.26,
            "wild_b": 0.32,
            "rye": 0.56,
            "sedge": 0.38,
            "rush": 0.43,
        }[kind]
        choice = RNG.random()
        if choice < native + 0.19 * phase:
            # Narrow, flattened blades and occasional taller clumps give broken light at the lip.
            factors = [
                RNG.uniform(0.33, 0.68),
                RNG.uniform(0.34, 0.66),
                RNG.uniform(0.49, 0.95),
            ]
            newplants.setdefault(kind, []).append(dict(index=idx, scale=factors))
        elif choice < 0.88:
            newplants.setdefault(kind, []).append(dict(index=idx, remove=True))
            if RNG.random() < 0.86:
                key = "fine_a" if RNG.random() < 0.56 else "fine_b"
                newplants.setdefault(key, []).append(
                    dict(
                        position=row["position"],
                        yaw=row["yaw"],
                        height=RNG.uniform(30.0, 59.0) * (0.73 + 0.42 * phase),
                        breadth=RNG.uniform(0.77, 1.31),
                    )
                )
    for bank, number in (("right", 67), ("left", 32)):
        for _ in range(number):
            s0 = RNG.uniform(14.0, 54.0)
            off = RNG.uniform(1.55, 7.6) if bank == "right" else -RNG.uniform(3.1, 7.3)
            extent = RNG.uniform(0.55, 1.75)
            for _ in range(RNG.integers(5, 15)):
                st = s0 + RNG.normal(0, 0.86 * extent)
                cs = (
                    (right(st) if bank == "right" else left(st))
                    + off
                    + np.clip(RNG.normal(0, extent), -1.4, 1.4)
                )
                point = a.EYE[:2] + a.FORWARD_XY * st + a.RIGHT[:2] * cs
                h = field.sample(*point)
                if h - float(a.surface(point, line)) < 0.22 or any(
                    d.inside_polygon(point[:1], point[1:], poly)[0] for poly in polygons
                ):
                    continue
                key = "fine_a" if RNG.random() < 0.55 else "fine_b"
                newplants.setdefault(key, []).append(
                    dict(
                        position=(np.r_[point, h] * SCALE - [0, 0, 1.4])
                        .round(3)
                        .tolist(),
                        yaw=RNG.uniform(-180.0, 180.0),
                        height=RNG.uniform(26.0, 68.0),
                        breadth=RNG.uniform(0.74, 1.4),
                    )
                )
    for k, rows in newplants.items():
        stats[k] = dict(
            total=len(rows), removed=sum(bool(r.get("remove")) for r in rows)
        )
    write("vegetation.json", newplants)
    write(
        "survey.json",
        dict(
            new_submerged_stones=pebble_count,
            triangles=len(f),
            added_bed_triangles=len(newf),
            decorative_cap_height_max_m=0.105,
            vegetation=stats,
        ),
    )
    print(len(v), len(f), stats)


if __name__ == "__main__":
    build()
