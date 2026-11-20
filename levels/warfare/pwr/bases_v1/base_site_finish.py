"""Surface polygons for .10 court wings, compacted spur flares and equipment pads."""

import json
import numpy as np
from shapely.affinity import affine_transform
from shapely.geometry import LineString, Polygon, mapping
from shapely.ops import unary_union
from base_approach_paths import ROOT, PLAN

FINISH = ROOT / "out/pwr/base-approaches/site-finish/geometry"
BASE9 = ROOT / "out/pwr/base-approaches/saturday.9"

# Deliberately unequal side service courts. Reflect the whole pattern at blue.
HOME_ISLANDS = [
    [
        (-82, -64),
        (-70, -60),
        (-59, -52),
        (-52, -53),
        (-46, -45),
        (-46, -25),
        (-53, -18),
        (-57, -17),
        (-57, -4),
        (-64, 3),
        (-63, 17),
        (-79, 28),
        (-87, 26),
    ],
    [
        (-87, 27),
        (-74, 32),
        (-62, 30),
        (-54, 36),
        (-48, 36),
        (-37, 49),
        (-34, 58),
        (-24, 69),
        (-23, 84),
        (-56, 84),
        (-86, 62),
    ],
    [
        (86, -39),
        (73, -42),
        (66, -37),
        (62, -36),
        (52, -27),
        (48, -20),
        (48, 2),
        (57, 10),
        (60, 10),
        (60, 23),
        (71, 36),
        (86, 39),
    ],
    [
        (86, 48),
        (71, 44),
        (57, 46),
        (48, 53),
        (39, 54),
        (32, 63),
        (24, 66),
        (24, 84),
        (58, 84),
        (82, 67),
    ],
]
SUMMIT_ISLANDS = [
    [
        (-84, -68),
        (-67, -64),
        (-58, -60),
        (-47, -60),
        (-39, -51),
        (-38, -40),
        (-44, -37),
        (-52, -37),
        (-58, -28),
        (-58, -21),
        (-70, -13),
        (-85, -17),
    ],
    [
        (-85, -5),
        (-70, -9),
        (-58, 2),
        (-54, 15),
        (-46, 22),
        (-44, 37),
        (-33, 44),
        (-30, 57),
        (-21, 66),
        (-20, 80),
        (-64, 84),
        (-85, 55),
    ],
    [
        (85, -66),
        (69, -63),
        (55, -58),
        (46, -60),
        (38, -54),
        (39, -40),
        (46, -36),
        (53, -36),
        (61, -24),
        (61, -18),
        (72, -12),
        (86, -13),
    ],
    [
        (84, -6),
        (72, -10),
        (58, 3),
        (54, 15),
        (46, 24),
        (44, 38),
        (34, 47),
        (30, 57),
        (22, 64),
        (20, 82),
        (65, 85),
        (85, 54),
    ],
]
SLOTS = ["Aggregate", "ServiceSoil", "Pewter", "Retainer", "Inlay"]


def band(points, width):
    return LineString(points).buffer(width / 2, cap_style="flat", join_style="mitre")


def footprint(base, plan):
    x, y = base["terrace_center_m"][:2]
    team = base["id"]
    flip = -1 if team == "blue" else 1

    def local(shape):
        return affine_transform(shape, [flip, 0, 0, 1, x, y])

    edge = [
        [-68, -76],
        [68, -76],
        [80, -64],
        [80, 64],
        [68, 76],
        [-68, 76],
        [-80, 64],
        [-80, -64],
    ]
    toe = local(Polygon(edge))
    # Actual open aircraft notches have a vertical edge at -70 before the
    # landscape resumes. Our surfacing follows only the extant top and side surfaces.
    desired = [
        local(Polygon(p)) for p in (SUMMIT_ISLANDS if team == "green" else HOME_ISLANDS)
    ]
    wings = unary_union(desired).intersection(toe)
    service_beds = []
    raw_flare = Polygon()
    track = []
    stops = []
    if team != "green":
        # Both halves have real equipment parking. The campward half also
        # receives the angled dirt spur, which enters red and blue at slightly
        # different native coordinates. Never shift the mirrored vehicle bays.
        for sign in (-1, 1):

            def shape(coords):
                return local(Polygon([(sign * a, b) for a, b in coords]))

            def line(coords, width):
                return local(band([(sign * a, b) for a, b in coords], width))

            service_beds.append(
                shape(
                    [
                        (25, -66),
                        (31, -72),
                        (45, -72),
                        (56, -65),
                        (59, -59),
                        (59, -44),
                        (53, -37),
                        (44, -37),
                        (42, -39),
                        (28, -39),
                        (23, -46),
                        (23, -59),
                    ]
                )
            )
            # Broad paired flush service plates, with separate relief gaps and
            # dull amber parking stops cut into the surface, at the first and last axles.
            for xx in [31.8, 48.2]:
                track.append(
                    shape(
                        [
                            (xx - 1.50, -54),
                            (xx + 0.55, -54),
                            (xx + 1.55, -52),
                            (xx + 1.55, -41),
                            (xx + 0.7, -40.2),
                            (xx - 1.50, -40.2),
                        ]
                    )
                )
                stops.append(line([(xx - 1.9, -40.65), (xx + 1.9, -40.65)], 0.23))
            for xx in [36.1, 43.9]:
                track.append(
                    shape(
                        [
                            (xx - 1.35, -68),
                            (xx + 0.65, -68),
                            (xx + 1.3, -67),
                            (xx + 1.3, -57),
                            (xx + 0.4, -56.3),
                            (xx - 1.35, -56.3),
                        ]
                    )
                )
        row = next(
            s for s in plan["surfaces"] if s["id"] == team + "_original_road_court_link"
        )
        old = Polygon([p[:2] for p in row["top_polygon_m"]])
        external = base["connections"][-1]
        a = np.array(external["start_world_m"][:2])
        b = np.array(external["end_world_m"][:2])
        f = (b - a) / np.linalg.norm(b - a)
        side = np.array([-f[1], f[0]])
        approach = Polygon(
            [
                a - 8 * f + 4.7 * side,
                a - 3 * f + 7.7 * side,
                a + 4 * f + 9.7 * side,
                b + 3 * f + 10.5 * side,
                b + 7 * f - 8.5 * side,
                b - 8.8 * side,
                a + 4 * f - 9.7 * side,
                a - 3 * f - 7.7 * side,
                a - 8 * f - 4.7 * side,
            ]
        )
        bay = local(
            Polygon(
                [
                    (27, -73),
                    (33, -76),
                    (48, -76),
                    (55, -67),
                    (51, -53),
                    (38, -48),
                    (25, -56),
                ]
            )
        )
        # Unioning the *physical* diagonal link and the flare gives every old
        # square corner new dirt coverage. Then trim to a chamfered service tongue.
        raw_flare = unary_union([old.buffer(0.75, join_style="bevel"), approach, bay])
    else:
        # Paired freight laybys beside the processional, leaving a forty-metre
        # center aisle clear in the forecourt and the capture road outside it.
        for sign in (-1, 1):
            points = [
                (23, -68),
                (30, -73),
                (55, -73),
                (62, -66),
                (59, -57),
                (47, -52),
                (41, -45),
                (29, -45),
                (22, -52),
            ]
            service_beds.append(local(Polygon([(sign * a, b) for a, b in points])))
            for dx in (28.5, 40.5):
                track.append(
                    local(
                        band(
                            [
                                (sign * dx, -62),
                                (sign * (dx + 5), -57),
                                (sign * (dx + 10), -57),
                            ],
                            2.1,
                        )
                    )
                )
                stops.append(
                    local(
                        band([(sign * (dx + 8.4), -57), (sign * (dx + 10), -57)], 0.27)
                    )
                )
    beds = unary_union(service_beds)
    trim = []
    seams = []
    # Interrupted hard retainers follow only the inward-facing edge of each
    # maintenance terrace. Soft gravel on the exterior meets the terrain agent’s paint.
    for i, p in enumerate(SUMMIT_ISLANDS if team == "green" else HOME_ISLANDS):
        q = local(band(p[2:-3], 1.08 if i % 2 == 0 else 0.78))
        trim.append(q.intersection(wings))
        for k in range(3, len(p) - 4, 3):
            a, b = np.array(p[k]), np.array(p[k + 1])
            v = b - a
            angle = np.array([-v[1], v[0]]) / np.linalg.norm(v)
            seams.append(
                local(
                    band([(a - angle * 1.7).tolist(), (a + angle * 1.7).tolist()], 0.23)
                )
            )
    for bed in service_beds:
        trim.append(bed.boundary.buffer(0.36, join_style="mitre").intersection(bed))
    # A small number of chamfered steel service plates breaks the surface up
    # at full vehicle scale. Never encircle the entire legacy slab in a band.
    metal = unary_union(track)
    inlays = unary_union(stops).intersection(metal.buffer(0.5))
    trim = (
        unary_union(trim + seams)
        .difference(raw_flare)
        .difference(metal)
        .difference(inlays)
    )
    metal = metal.difference(inlays)
    aggregate = (
        unary_union([wings, beds])
        .difference(raw_flare)
        .difference(trim)
        .difference(metal)
        .difference(inlays)
    )
    soil = raw_flare.difference(trim).difference(metal).difference(inlays)
    if team == "green":
        soil = (
            unary_union([bed.buffer(-2.6, join_style="mitre") for bed in service_beds])
            .difference(metal)
            .difference(inlays)
            .difference(trim)
        )
        aggregate = aggregate.difference(soil)
    return (
        {
            "Aggregate": aggregate,
            "ServiceSoil": soil,
            "Pewter": metal,
            "Retainer": trim,
            "Inlay": inlays,
        },
        desired,
        toe,
    )


def write_footprints():
    FINISH.mkdir(exist_ok=True, parents=True)
    plan = json.loads(PLAN.read_text())
    features = []
    for base in plan["bases"]:
        surfaces, wings, toe = footprint(base, plan)
        for i, p in enumerate(wings):
            features.append(
                {
                    "type": "Feature",
                    "properties": {
                        "site": base["id"],
                        "role": "verge",
                        "index": i,
                        "native_surface_cutoff": "toe",
                    },
                    "geometry": mapping(p),
                }
            )
        for role, p in [("toe", toe), ("spur_and_bay", surfaces["ServiceSoil"])]:
            features.append(
                {
                    "type": "Feature",
                    "properties": {"site": base["id"], "role": role},
                    "geometry": mapping(p),
                }
            )
    (FINISH / "site-footprints.geojson").write_text(
        json.dumps(
            {
                "type": "FeatureCollection",
                "features": features,
                "units": "authoring_xy_metres_y_north",
            },
            indent=2,
        )
        + "\n"
    )


if __name__ == "__main__":
    write_footprints()
