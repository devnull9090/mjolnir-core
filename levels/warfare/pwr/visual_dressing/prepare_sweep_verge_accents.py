"""Build low native stone, woody litter and fine grass pockets on Southwest Sweep's road verges."""

import numpy as np
from prepare_sweep_gravel import (
    ART,
    GRAVEL,
    ROOT,
    Bend,
    Camera,
    Road,
    Site,
    pack_groups,
    read,
    save,
)
from prepare_sweep_road_dressing import fit_debris

OWNER = "PWR_SweepVergeAccents"
# Survey stations are metres along the road. Clusters sit on the outer side of
# each compacted wheel path, with longer gaps around the apex and between deposits.
POCKETS = {
    "left": [
        (96, 0.95),
        (104.6, 1.4),
        (112.9, 0.85),
        (117.1, 1.8),
        (121.7, 1.25),
        (126.5, 1.3),
        (129.45, 0.9),
        (132.8, 1.8),
    ],
    "right": [
        (85.3, 1.1),
        (93.1, 1.25),
        (100.2, 1.5),
        (104.9, 1.9),
        (109.6, 0.85),
        (114.7, 1.4),
        (118.9, 1.1),
        (124.15, 1.9),
        (128.2, 1.1),
    ],
}


def grass_poses(site, items, rng):
    xy, scale = items[:, :2], items[:, 2]
    z = site.height(xy) - 0.009 * scale
    rot = np.array(
        [
            site.rotation(p, a, vertical=True).as_quat()
            for p, a in zip(xy, rng.uniform(0, 360, len(xy)))
        ]
    )
    return np.asarray(
        np.c_[
            np.c_[xy, z] * [100, -100, 100],
            rot,
            scale,
            scale * rng.uniform(0.76, 1.14, len(xy)),
            scale * rng.uniform(0.73, 1.05, len(xy)),
        ],
        dtype="<f4",
    )


def build():
    out = ART / "round21/accents"
    site = Site()
    survey = read(ART / "round18/earth/roadbed.json")
    road = Road(site)
    bend = Bend(road, survey["reference_landmarks"])
    catalog = {r["key"]: r for r in read(ART / "round20/floor/verges.json")["groups"]}
    keys = [*GRAVEL, "Bark", "Branch", "FescueA"]
    records = {key: [] for key in keys}
    rng = np.random.default_rng(97331)
    for hand, stations in POCKETS.items():
        sign = -1 if hand == "left" else 1
        for station, width in stations:
            offset = rng.uniform(0.91, 1.55)
            # One larger exposed facet anchors a fan; smallest fragments
            # taper off asymmetrically along the driven direction.
            quantities = [
                ("Gravel1", 13, 0.043, 0.105),
                ("Gravel2", 7, 0.097, 0.205),
                ("Gravel3", 5, 0.13, 0.24),
                ("Branch", 3, 0.23, 0.51),
                ("Bark", 5, 0.13, 0.31),
                ("FescueA", 4, 0.74, 1.19),
            ]
            for key, count, lo, hi in quantities:
                sta = station + np.clip(rng.normal(0, 0.48, count), -1.1, 1.5) * width
                left, _, right = bend.curves(sta)
                edge = left if sign < 0 else right
                fringe = (
                    rng.uniform(0.10, 0.67, count)
                    if key == "FescueA"
                    else rng.normal(0, 0.18, count)
                )
                across = edge + sign * np.maximum(
                    0.76, offset + fringe + 0.11 * np.sin(sta * 2.1)
                )
                xy = bend.ground_xy(sta, across)
                vals = rng.uniform(lo, hi, count)
                actual_station, actual_side = road.surveys(xy)
                actual_left, _, actual_right = bend.curves(actual_station)
                distance = (
                    actual_left - actual_side
                    if sign < 0
                    else actual_side - actual_right
                )
                # At the sharpest turn the closest polyline sample can switch
                # segments. Keep only the instances verifiably outside the rut.
                clear = distance >= (0.81 if key == "FescueA" else 0.73)
                records[key].extend(np.c_[xy, vals][clear])
    entries = []
    cameras = {
        "driver": Camera(survey["reference_camera_pose"][:6]),
        "turn": Camera(
            read(ROOT / "out/pwr/alpine-target/bench/sweep-20/photos/bend-ahead.json")[
                "frame"
            ]["camera_before"][:6]
        ),
    }
    proof = {
        "pockets": POCKETS,
        "mesh_sources": "existing .20 HISM bindings",
        "groups": {},
    }
    for key in keys:
        items = np.asarray(records[key])
        row = catalog[key].copy()
        poses = (
            grass_poses(site, items, rng)
            if key == "FescueA"
            else fit_debris(site, row, items, rng)
        )
        entries.append((row, poses))
        xyz = poses[:, :3] * [0.01, -0.01, 0.01]
        sta, side = road.surveys(xyz[:, :2])
        left, _, right = bend.curves(sta)
        edge = np.maximum(left - side, side - right)
        if edge.min() < 0.68:
            raise ValueError("A verge patch intrudes on a wheel core")
        counts = {}
        for name, cam in cameras.items():
            uv = cam.project(xyz)
            counts[name] = int(
                np.sum(
                    (uv[:, 2] > 0) & np.all((uv[:, :2] >= 0) & (uv[:, :2] <= 1), axis=1)
                )
            )
        proof["groups"][key] = {
            "count": len(poses),
            "camera_visible_pivots": counts,
            "nearest_wheel_path_m": round(float(edge.min()), 3),
        }
    pack_groups(out, OWNER, entries)
    save(out / "survey.json", proof)
    print(
        {
            k: (v["count"], v["camera_visible_pivots"])
            for k, v in proof["groups"].items()
        }
    )


if __name__ == "__main__":
    build()
