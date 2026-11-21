# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy","scipy","shapely","pillow"]
# ///
"""Clear the surveyed driving arc and cluster weathered litter along the worn shoulders."""

from hashlib import sha256 as hash_bytes
import numpy as np
from scipy.spatial.transform import Rotation

from prepare_sweep_gravel import (
    ART,
    GRAVEL,
    Bend,
    Site,
    Road,
    Camera,
    ROOT,
    read,
    save,
    sha256,
    lod0_points,
    pack_groups,
    plant_mesh,
)
from southwest_bend_survey import fit_station_curve
from prepare_sweep_forest_floor import smooth

BASE, OUT = ART / "round19", ART / "round20"
ALPINE = ROOT / "out/pwr/alpine-target/verges"
ACTORS = [
    ("PWR_SweepForestFloor", "PWRSweep_", BASE / "floor", OUT / "floor"),
    ("PWR_SweepBanks", "PWRSweepBank_", BASE / "verges", OUT / "verges"),
    ("PWR_AlpineVerges", "PWRVerge_", ALPINE, OUT / "alpine-edits"),
]
VEGETATION = {
    "Bark",
    "Branch",
    "Fern14",
    "Fern15",
    "Ferns",
    "FescueA",
    "FescueB",
    "Moss",
    "Sedge",
    "Tufts",
}
WET = [
    (121.95, -1.2, 0.62, 0.32),
    (116.0, 0.4, 0.59, 0.32),
    (104.4, 5.5, 0.65, 0.24),
    (141.9, 0.9, 0.69, 0.34),
    (154.1, -1.3, 0.54, 0.29),
]


def digest(mat):
    return hash_bytes(np.asarray(mat, dtype="<f4").tobytes()).hexdigest()


def additions(bend, marks, rng):
    stations = bend.s
    left, mid, right = bend.curves(stations)
    duff = fit_station_curve(stations, marks["duff_edge"], -5.15, 14.0)
    duff = np.where(stations < 110.5, np.maximum(duff, left - 1.4), duff) + 0.18
    right_edge = right + np.interp(
        stations, [0, 98, 119, 131, 170, stations[-1]], [3.8, 2.05, 3.18, 4.9, 3.7, 3.8]
    )
    pockets = {k: [] for k in ["Branch", "Bark", *GRAVEL]}
    # Compact fans nest against the real shoulder, leaving long open sections between.
    for sign, anchors in [
        (
            -1,
            [
                77,
                85.3,
                93.7,
                101.5,
                110.0,
                116.2,
                120.5,
                124.1,
                126.6,
                128.9,
                130.1,
                136,
                146,
            ],
        ),
        (1, [78, 86.7, 92.2, 100.5, 108.3, 113.9, 119.9, 126.3, 131.4, 139, 148]),
    ]:
        for s0 in anchors:
            ln, depth = rng.uniform(0.27, 1.1), rng.uniform(0.17, 0.50)
            for key, n, low, high in [
                ("Bark", 13, 0.05, 0.25),
                ("Branch", 6, 0.08, 0.31),
                ("Gravel1", 8, 0.025, 0.064),
                ("Gravel2", 11, 0.036, 0.100),
                ("Gravel3", 9, 0.035, 0.091),
            ]:
                s = s0 + np.clip(rng.normal(0, ln, n), -2.3, 2.3)
                edge = np.interp(s, stations, duff if sign < 0 else right_edge)
                off = edge + sign * (
                    rng.normal(0.13, depth, n) + 0.22 * np.sin((s - s0) * 2.5)
                )
                l, m, r = bend.curves(s)
                keep = (off < l - 1.25) if sign < 0 else (off > r + 1.25)
                xy = bend.ground_xy(s, off)
                pockets[key].extend(np.c_[xy, rng.uniform(low, high, n)][keep].tolist())
    # Break the hard ring of wet soil with sparse, partly embedded small stones.
    for s, off, length, width in WET:
        n = rng.integers(7, 15)
        angles = rng.uniform(-np.pi, np.pi, n)
        sta = s + length * np.cos(angles) * rng.uniform(0.78, 1.18, n)
        side = off + width * np.sin(angles) * rng.uniform(0.78, 1.18, n)
        for pt in bend.ground_xy(sta, side):
            pockets[rng.choice(GRAVEL)].append([*pt, rng.uniform(0.022, 0.067)])
    # The three near glints share a depression surveyed in world coordinates.
    near = np.array([-588.944, -541.320])
    for dx, dy, w, n in [
        (-0.028, -0.061, 0.20, 10),
        (0.195, 0.178, 0.10, 5),
        (-0.275, 0.070, 0.07, 4),
    ]:
        angles = rng.uniform(0, 2 * np.pi, n)
        xy = near + [dx, -dy] + np.c_[np.cos(angles), np.sin(angles)] * w * [1, 0.50]
        for pt in xy:
            pockets[rng.choice(GRAVEL)].append([*pt, rng.uniform(0.025, 0.062)])
    return pockets


def fit_debris(site, row, pieces, rng):
    mesh = np.unique(lod0_points(ROOT / row["source_glb"]) * 0.01, axis=0)
    if row["key"] in GRAVEL:
        return plant_mesh(site, mesh, pieces, rng)
    # Follow the local slope and seat long bark/sticks inside the soil at their bases.
    xy, width = pieces[:, :2], pieces[:, 2]
    scale = width / max(np.ptp(mesh, axis=0)[:2])
    scale_z = scale * rng.uniform(0.41, 0.75, len(xy))
    z = site.height(xy) - scale_z * np.quantile(mesh[:, 2], 0.24) - 0.002
    slope_x = (site.height(xy + [0.12, 0]) - site.height(xy - [0.12, 0])) / 0.24
    slope_y = (site.height(xy + [0, 0.12]) - site.height(xy - [0, 0.12])) / 0.24
    normal = np.c_[-slope_x, slope_y, np.ones(len(z))]
    normal /= np.linalg.norm(normal, axis=1)[:, None]
    angle = rng.uniform(0, 2 * np.pi, len(z))
    v = np.c_[np.cos(angle), np.sin(angle), np.zeros(len(z))]
    v -= normal * np.sum(v * normal, axis=1)[:, None]
    v /= np.linalg.norm(v, axis=1)[:, None]
    quat = Rotation.from_matrix(
        np.stack((v, np.cross(normal, v), normal), axis=-1)
    ).as_quat()
    return np.asarray(
        np.c_[np.c_[xy, z] * [100, -100, 100], quat, scale, scale, scale_z], dtype="<f4"
    )


def keep_indices(actor, key, mat, bend, source_i, rng):
    xy = mat[:, :2] * [0.01, -0.01]
    s, d = bend.road.surveys(xy)
    l, mid, r = bend.curves(s)
    # The two traffic ribbons and adjacent 1.3 m must be free of tall growth.
    # The terrain material extends farther into the feathered, planted roadside.
    arc = smooth(53.0, 66.0, s) * (1.0 - smooth(102.0, 117.0, s))
    inside = arc * (1.0 - smooth(1.0, 2.75, np.maximum(l - d, d - r)))
    if key in VEGETATION:
        # Include overhanging fronds and a little fragmented bark at the contacts.
        return ~(inside > 0.38)
    if actor == "PWR_SweepForestFloor" and key in GRAVEL:
        # The .19 pass appended these lenses. Leave original stones intact,
        # and scour windows in several of the recent near-camera deposits.
        old = read(ART / "round18/floor/verges.json")["groups"][source_i - 1]["count"]
        trough = np.zeros(len(s))
        for anchor, length, centre, breadth in [
            (129.2, 0.45, -0.46, 0.8),
            (126.4, 0.49, 0.10, 0.90),
            (123.7, 0.62, 0.05, 0.97),
            (122.0, 0.45, 0.29, 0.84),
            (116.8, 0.62, -0.12, 0.86),
            (110.7, 0.80, 0.18, 1.06),
        ]:
            trough = np.maximum(
                trough,
                np.exp(
                    -1.2 * ((s - anchor) / length) ** 2
                    - 0.85 * ((d - mid - centre) / breadth) ** 2
                ),
            )
        return ~((np.arange(len(mat)) >= old) & (rng.random(len(mat)) < 0.92 * trough))
    return np.ones(len(mat), dtype=bool)


def report_screen(mat, camera):
    if not len(mat):
        return 0
    uv = camera.project(mat[:, :3] * [0.01, -0.01, 0.01])
    return int(
        np.sum((uv[:, 2] > 0) & np.all((uv[:, :2] >= 0) & (uv[:, :2] <= 1), axis=1))
    )


def build():
    site = Site()
    survey = read(ART / "round18/earth/roadbed.json")
    bend = Bend(Road(site), survey["reference_landmarks"])
    cams = {
        "driver": Camera(survey["reference_camera_pose"][:6]),
        "bend": Camera(
            read(ROOT / "out/pwr/alpine-target/bench/sweep-19/photos/bend-ahead.json")[
                "frame"
            ]["camera_before"][:6]
        ),
    }
    rng = np.random.default_rng(2020111)
    pockets = additions(bend, survey["reference_landmarks"], rng)
    changes = []
    for actor, prefix, src, dst in ACTORS:
        baseline = read(src / "verges.json")
        entries = []
        source_sha = sha256(src / "verges.json")
        for index, row in enumerate(baseline["groups"], 1):
            raw = src / (baseline["file"] + f".xf{index}")
            mat = np.fromfile(raw, dtype="<f4").reshape(-1, 10)
            if digest(mat) != row["transform_sha256"]:
                raise ValueError(f"Unexpected {actor} source")
            if actor == "PWR_AlpineVerges" and row["key"] == "Outcrop":
                # Only the Teton member still belongs to this group since the .16 snow-free split.
                mat = mat[np.argmax(mat[:, 0])][None, :]
            keep = keep_indices(actor, row["key"], mat, bend, index, rng)
            removed = np.flatnonzero(~keep)
            extra = np.empty((0, 10), dtype="<f4")
            if actor == "PWR_SweepForestFloor" and row["key"] in pockets:
                extra = fit_debris(site, row, np.asarray(pockets[row["key"]]), rng)
            result = np.concatenate((mat[keep], extra))
            if len(removed) or len(extra):
                changes.append(
                    {
                        "actor": actor,
                        "component": prefix + row["key"],
                        "key": row["key"],
                        "source_manifest": (src / "verges.json")
                        .relative_to(ROOT)
                        .as_posix(),
                        "source_manifest_sha256": source_sha,
                        "target_manifest": (dst / "verges.json")
                        .relative_to(ROOT)
                        .as_posix(),
                        "source_transforms": raw.relative_to(ROOT).as_posix(),
                        "target_transforms": (dst / raw.name)
                        .relative_to(ROOT)
                        .as_posix(),
                        "base_count": len(mat),
                        "removed_indices": removed.tolist(),
                        "added_count": len(extra),
                        "count": len(result),
                        "base_sha256": digest(mat),
                        "append_sha256": digest(extra),
                        "sha256": digest(result),
                        "projected_changes": {
                            n: {
                                "removed": report_screen(mat[~keep], cam),
                                "added": report_screen(extra, cam),
                            }
                            for n, cam in cams.items()
                        },
                    }
                )
            entries.append((row, result))
        pack_groups(dst, actor, entries)
    receipt = {
        "base_release": 19,
        "groups": changes,
        "structural_changes": 0,
        "collision_changes": 0,
        "survey": "graded_apex from the traced .18 wheel lines; remove crossing vegetation where the local road footprint exceeds 0.38",
        "stone_changes": "Six near median washes among the .19 deposits, partly buried glint rims and irregular side pockets.",
    }
    save(OUT / "road-dressing.json", receipt)
    for r in changes:
        print(
            r["actor"],
            r["key"],
            "remove",
            len(r["removed_indices"]),
            "add",
            r["added_count"],
        )


if __name__ == "__main__":
    build()
