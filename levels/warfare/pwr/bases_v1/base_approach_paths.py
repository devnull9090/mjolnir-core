"""Gate-aligned native surface and service footprints in map authoring metres."""

import json
from pathlib import Path

import numpy as np
from shapely.geometry import LineString, Polygon, mapping

ROOT = Path(__file__).resolve().parents[4]
PLAN = ROOT / "out/pwr/base-integration/placement-plan.json"
ROADS = ROOT / "levels/warfare/pwr/terrain/final-v5/terrain.geometry.json"
OUT = ROOT / "out/pwr/base-approaches/geometry"


def road_entry(road, y):
    points = np.asarray(road["centreline_m"])[:, :2]
    for a, b in zip(points, points[1:]):
        if min(a[1], b[1]) <= y <= max(a[1], b[1]):
            tangent = (b - a) * np.sign(b[1] - a[1])
            return a + (b - a) * (y - a[1]) / (b[1] - a[1]), tangent / np.linalg.norm(
                tangent
            )
    raise ValueError(road["id"])


def bezier(controls, stations=80):
    a, b, c, d = np.asarray(controls)
    t = np.linspace(0, 1, stations)[:, None]
    return (
        (1 - t) ** 3 * a + 3 * (1 - t) ** 2 * t * b + 3 * (1 - t) * t**2 * c + t**3 * d
    )


def site_design(base, roads):
    team = base["id"]
    center = np.asarray(base["terrace_center_m"][:2])
    x, y = center
    if team == "green":
        front = np.array(
            [[x, 510], [x, y - 76], [x, y - 70], [x, y - 31], [x, y - 24.05]]
        )
    else:
        entry, tangent = road_entry(roads[team + "_apron"], -205.0)
        # Peel away from the occupied tank bays, ending tangent to the middle
        # transition. Keep the final approach, through-bore and unloading pad axial.
        curve = bezier([entry, entry + 37 * tangent, [x, y - 145], [x, y - 84]])
        front = np.vstack(
            [curve, [x, y - 76], [x, y - 70], [x, y - 31], [x, y - 24.05]]
        )
    rear_start = y + (30.5 if team == "green" else 29)
    rear = np.array([[x, rear_start], [x, y + 70], [x, y + 76], [x, y + 103]])
    # A short chamfered receiving court permits a Warthog to reverse or turn.
    # The citadel's larger eight-sided truck head serves its central causeway.
    half = 22 if team == "green" else 16
    back = 122 if team == "green" else 115
    pad = Polygon(
        center
        + np.array(
            [
                [-7, 83],
                [-half, 91],
                [-half, back - 5],
                [-half + 5, back],
                [half - 5, back],
                [half, back - 5],
                [half, 91],
                [7, 83],
            ]
        )
    )
    return {
        "team": team,
        "front": LineString(front),
        "rear": LineString(rear),
        "rear_pad": pad,
        "court": Polygon(base["court_outer_polygon_m"]),
        "center": center,
    }


def emit_designs():
    OUT.mkdir(parents=True, exist_ok=True)
    bases = json.loads(PLAN.read_text())["bases"]
    roads = {s["id"]: s for s in json.loads(ROADS.read_text())["roads"]}
    designs = [site_design(base, roads) for base in bases]
    features = []
    for d in designs:
        for key, width in (
            ("front", 16),
            ("rear", 14),
            ("rear_pad", None),
            ("court", None),
        ):
            features.append(
                {
                    "type": "Feature",
                    "properties": {
                        "site": d["team"],
                        "role": key,
                        "width_m": width,
                        "exterior_gravel_verge_m": 3 if key != "court" else 0,
                    },
                    "geometry": mapping(d[key]),
                }
            )
    path = OUT / "gate-routes.geojson"
    path.write_text(
        json.dumps(
            {
                "type": "FeatureCollection",
                "coordinates": "authored_xy_m_y_north",
                "features": features,
            },
            indent=2,
        )
        + "\n"
    )
    return designs


if __name__ == "__main__":
    emit_designs()
