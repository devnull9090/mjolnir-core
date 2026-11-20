"""Build low-profile road receivers, paving folds, pad backs and under-deck fascias.

The visible drive stays on the surfaces already present in the Saturday collision.
The triangle splitter uses the actual cooked Nanite court plus the authoritative
landscape. It never places a flat road through a sloping threshold.
"""

import json
import sys

import numpy as np
from shapely import constrained_delaunay_triangles
from shapely.affinity import translate
from shapely.geometry import LineString, Polygon, box
from shapely.ops import unary_union

from base_approach_paths import ROOT, OUT, PLAN, emit_designs

sys.path.insert(0, str(ROOT / "levels/warfare/pwr"))
from base_paving import polygon_parts
from package_base_paving import read_glb
from heightfield import load_heightfield

LIFT = 0.018
SLOTS = ["Drive", "Shoulder", "Seam", "Amber"]
WIT = OUT / "witnesses"
MASTER = ROOT / "levels/warfare/pwr/terrain/runtime-v5/runtime-master.json"


def strip(points, width):
    return LineString(points).buffer(width / 2, cap_style="flat", join_style="mitre")


def material_polygons(d):
    # All construction here is in base-local metres, north up. The court throat
    # is short of the existing team-specific road tongue and its bolt detailing.
    summit = d["team"] == "green"
    toe = -180 if summit else -76.5
    front = Polygon(
        [
            [-8, toe],
            [8, toe],
            [8, -53],
            [6.4, -42],
            [5.0, -36],
            [4.65, -24.15],
            [-4.65, -24.15],
            [-5, -36],
            [-6.4, -42],
            [-8, -53],
        ]
    )
    rear_start = 23.5
    rear = Polygon(
        [
            [-4.3, rear_start],
            [4.3, rear_start],
            [4.3, 29],
            [7, 40],
            [7, 103],
            [-7, 103],
            [-7, 40],
            [-4.3, 29],
        ]
    )
    x, y = d["center"]
    rear_pad = translate(d["rear_pad"], -x, -y)
    carriage = unary_union([front, rear, rear_pad])
    wing = []
    side_bands = []
    for sign in (-1, 1):

        def mirror(points):
            return [(sign * u, v) for u, v in points]

        wing.append(
            Polygon(
                mirror(
                    [
                        (6.1, -40),
                        (8.2, -55),
                        (13, -48),
                        (29, -38),
                        (35, -37),
                        (35, -32),
                        (28, -32),
                        (23, -35),
                        (12, -40),
                        (8, -37),
                    ]
                )
            )
        )
        side_bands.append(
            strip(mirror([(12, -46), (23, -39), (30, -35.7), (34, -35.7)]), 0.24)
        )
    supports = unary_union(wing)
    summary = unary_union([carriage, supports])
    # Subject the edge bands to the same topological partition as the road,
    # avoiding stacked/copied faces where an entry meets its receiving head.
    shoulder = unary_union(
        [carriage.boundary.buffer(0.48, join_style="mitre"), supports, *side_bands]
    ).intersection(summary)
    # Keep both open interfaces free of thin transverse sill pieces.
    shoulder = shoulder.difference(box(-12, toe - 1, 12, toe + 0.52))
    shoulder = shoulder.difference(box(-6, -24.9, 6, -23))
    shoulder = shoulder.difference(box(-5, 23, 5, 24.1))
    seams = []
    inlays = []
    for j in range(int(toe) + 6, -33, 8):
        seams.append(strip([(-8.5, j), (0, j + 2.4), (8.5, j)], 0.115))
    for j in range(34, 118, 8):
        seams.append(strip([(-24, j), (0, j - 2.4), (24, j)], 0.115))
    for sign in (-1, 1):
        # Slender continuous edge rail with inset tabs and paired tapered
        # yellow markings. The repeating breaks leave the front center calm.
        for j in range(int(toe) + 7, -48, 14):
            inlays.append(strip([(sign * 7.72, j), (sign * 7.72, j + 2.4)], 0.18))
        for j in range(45, 85, 13):
            inlays.append(strip([(sign * 6.74, j), (sign * 6.74, j + 2.15)], 0.18))
        for j in (97, 105, 113) if summit else (96, 104):
            inlays.append(
                strip(
                    [
                        (sign * (17 if summit else 11), j),
                        (sign * (14 if summit else 8), j + 1.4),
                    ],
                    0.23,
                )
            )
        seams.extend(side_bands)
        # Small parallel scored channels lead out to the chamfered receiving
        # head and make the compact rear turning area read at driver height.
        for offset in (0, 1.15):
            seams.append(
                strip(
                    [
                        (sign * (6.9 + offset), 87),
                        (sign * (12.2 + offset), 93),
                        (sign * (12.2 + offset), 106),
                    ],
                    0.13,
                )
            )
    if summit:
        for sign in (-1, 1):
            seams.append(
                strip(
                    [
                        (sign * 3.9, -177),
                        (sign * 3.9, -141),
                        (sign * 5.3, -135),
                        (sign * 5.3, -92),
                        (sign * 3.9, -87),
                        (sign * 3.9, -62),
                    ],
                    0.18,
                )
            )
        for j in (-158, -127, -96):
            for sign in (-1, 1):
                inlays.append(strip([(sign * 6.3, j), (sign * 4.2, j + 1.65)], 0.23))
    seam = unary_union(seams).intersection(summary)
    amber = unary_union(inlays).intersection(summary)
    seam = seam.difference(amber)
    shoulder = shoulder.difference(seam).difference(amber)
    deck = summary.difference(unary_union([shoulder, seam, amber]))
    return {k: translate(v, x, y) for k, v in zip(SLOTS, [deck, shoulder, seam, amber])}


def support_planes(base, field):
    team = base["id"]
    cx, cy, _ = base["terrace_center_m"]
    xyz, _, idx, _ = read_glb(WIT / ("SM_PWR_" + team + "_court.glb"))
    # glTF decoded into Unreal centimetres. The world authoring Y convention
    # is inverted relative to Unreal at the actor's authored origin.
    xyz = xyz * np.array([0.01, -0.01, 0.01]) + base["normalize_then_translate_m"]
    tri = xyz[idx]
    patches = []
    for points in tri:
        normal = np.cross(points[1] - points[0], points[2] - points[0])
        if abs(normal[2]) < 1e-8:
            continue
        # The exported mesh winds clockwise. Select upward FACING top via
        # the ordering-independent upper envelope, including all overlap faces.
        poly = Polygon(points[:, :2])
        d = -np.dot(normal, points[0])
        plane = np.array([-normal[0], -normal[1], -d]) / normal[2]
        patches.append((points[:, 2].mean(), poly, plane))
    # Across each used patch top triangles are either coplanar or well above
    # their backing bodies. Stable high-to-low clipping follows sloped tops.
    patches.sort(key=lambda v: -v[0])
    return patches


def triangulate(poly, plane, lift):
    result = []
    for shape in polygon_parts(poly):
        if shape.area < 1e-8:
            continue
        for tri in constrained_delaunay_triangles(shape).geoms:
            xy = np.array(tri.exterior.coords)[:3]
            area = np.linalg.det(np.vstack([xy[1] - xy[0], xy[2] - xy[0]]))
            if abs(area) < 1e-9:
                continue
            if area < 0:
                xy = xy[[0, 2, 1]]
            z = xy @ plane[:2] + plane[2] + lift
            result.append(np.column_stack((xy, z)))
    return result


def drape(poly, planes, field):
    current = poly
    faces = []
    for _, patch, plane in planes:
        if current.is_empty:
            break
        if not current.intersects(patch):
            continue
        clip = current.intersection(patch)
        if clip.area <= 1e-8:
            continue
        # Terrain can poke a few mm through the lower toe of the processional.
        faces.extend(triangulate(clip, plane, LIFT))
        current = current.difference(patch)
    if not current.is_empty and current.area > 1e-7:
        from base_paving import drape as terrain_drape

        # The only exterior zones in our geometry are the receiving heads
        # and approach toe. These are flat runtime-v5 terrace triangles.
        v, t, _ = terrain_drape(current, field, LIFT)
        faces.extend(v[t])
    return faces


def fascia(base, field):
    # The front deck has two protected aircraft parking notches, each with
    # a visible air gap below its edge. A stepped dark fascia sits just inside
    # the slab lip. It does not raise the bays or project into the Warthog drive.
    x, y, _ = base["terrace_center_m"]
    result = []
    for sign in (-1, 1):
        for a, b in [(12.1, 20.25), (20.29, 28.05), (28.09, 35.9)]:
            xa, xb = sorted((x + sign * a, x + sign * b))
            yt = y - 70 - 0.018
            feet = np.array([field.sample(xa, yt), field.sample(xb, yt)]) - 0.024
            high = base["floor_world_z_m"] - 0.151
            verts = np.array(
                [
                    [xa, yt, high],
                    [xb, yt, high],
                    [xb, yt - 0.035, feet[1]],
                    [xa, yt - 0.035, feet[0]],
                ]
            )
            # Forward (-Y) face exposed below the existing slab's 16cm lip.
            result.extend([verts[[0, 2, 1]], verts[[0, 3, 2]]])
    return result


def build():
    OUT.mkdir(parents=True, exist_ok=True)
    field = load_heightfield(MASTER)
    bases = {v["id"]: v for v in json.loads(PLAN.read_text())["bases"]}
    summaries = {}
    for d in emit_designs():
        team = d["team"]
        base = bases[team]
        planes = support_planes(base, field)
        groups = {}
        for key, poly in material_polygons(d).items():
            faces = drape(poly, planes, field)
            if key == "Seam":
                faces += fascia(base, field)
            groups[key] = np.array(faces, dtype=np.float64)
        np.savez_compressed(OUT / (team + "-surfaces.npz"), **groups)
        summaries[team] = {key: len(v) for key, v in groups.items()}
    return summaries


if __name__ == "__main__":
    print(build())
