# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy>=2,<3", "scipy>=1.15", "shapely>=2", "pillow>=11"]
# ///
"""Seat native, mixed-size stones in the surveyed gravel islands between the wheel paths."""

import argparse
from collections import defaultdict
from hashlib import sha256 as bytes_hash
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
from scipy.spatial import ConvexHull
from scipy.spatial.transform import Rotation

from build_sweep_banks import pack_groups, save
from prepare_alpine_verges import Camera, ROOT, lod0_points, read, sha256
from prepare_sweep_forest_floor import Road, Site
from southwest_bend_survey import fit_station_curve


ART = ROOT / "out/pwr/sweep-polish"
BASE = ART / "round18"
SURVEY = BASE / "earth/roadbed.json"
BEND = (82.0, 154.0)
GRAVEL = ("Gravel1", "Gravel2", "Gravel3")


class Bend:
    def __init__(self, road, marks):
        self.road = road
        self.s = road.ds
        left = fit_station_curve(self.s, marks["left"], -2.86, 16.25)
        right = fit_station_curve(self.s, marks["right"], 2.43, 16.25)
        half = np.clip((right - left) / 2, 1.65, 3.8)
        mid = (right + left) / 2
        self.left, self.right = mid - half, mid + half
        median = fit_station_curve(self.s, marks["median"], -0.24, 15.0)
        self.median = np.clip(median, self.left + 0.8, self.right - 0.8)

    def curves(self, station):
        return [
            np.interp(station, self.s, a) for a in (self.left, self.median, self.right)
        ]

    def ground_xy(self, station, offset):
        centre, normal = self.road.frame(station)
        return centre + normal * offset[:, None]


def loose_deposits(bend, site, rng):
    """An uneven seam of mineral fines with coarse clusters on its lips."""
    candidates = []
    # Wide lenses form at the apex and beside the existing wet depressions.
    # Remaining lenses have asymmetric narrow tails, with exposed soil between.
    fixed = [
        (97.4, 2.2, 0.56),
        (109.5, 1.7, 0.44),
        (116.8, 1.4, 0.45),
        (122.3, 1.0, 0.57),
        (126.6, 0.75, 0.39),
        (128.5, 0.65, 0.53),
        (129.85, 0.80, 0.60),
    ]
    sites = [(s, length, half, 0) for s, length, half in fixed]
    for sign in (0, -1, 1):
        station = BEND[0] + rng.uniform(0, 2.6)
        while station < BEND[1]:
            if sign or all(abs(station - s) > 1.4 for s, _, _ in fixed):
                sites.append(
                    (station, rng.uniform(0.35, 1.65), rng.uniform(0.28, 0.62), sign)
                )
            station += rng.uniform(1.25, 3.2) if sign == 0 else rng.uniform(2.7, 6.5)
    for anchor, length, half, shoulder in sites:
        density = 100 if shoulder else 260
        n = rng.poisson(density * length * half)
        station = anchor + np.clip(rng.normal(size=n), -2.3, 2.3) * length
        left, median, right = bend.curves(station)
        if shoulder:
            centre = left - 1.53 if shoulder < 0 else right + 1.57
            # Fans broaden toward the outside of the bend.
            half *= 1.26
        else:
            centre = median + rng.uniform(-0.24, 0.24)
        curl = rng.uniform(-0.29, 0.29)
        across = rng.normal(0, 1, size=n) * half + curl * np.sin(
            (station - anchor) * 2.6
        )
        offset = centre + across
        wheel_distance = np.minimum(abs(offset - left), abs(offset - right))
        approved = (
            (station >= BEND[0]) & (station <= BEND[1]) & (wheel_distance >= 0.85)
        )
        # A little coarse material sits on the rim; keep the shallow water visible.
        for place, side, along, cross in (
            (128.58, -0.74, 0.65, 0.36),
            (121.95, -1.2, 0.75, 0.33),
            (116.0, 0.40, 0.7, 0.35),
            (104.4, 5.5, 0.64, 0.28),
            (141.9, 0.9, 0.64, 0.35),
        ):
            approved &= ((station - place) / along) ** 2 + (
                (offset - side) / cross
            ) ** 2 > 1.0
        width = rng.triangular(0.024, 0.051, 0.122, n)
        coarse = (rng.random(n) < 0.15) & (abs(across) > 0.35 * half)
        width[coarse] = rng.uniform(0.072, 0.12, coarse.sum())
        sizes = rng.choice(GRAVEL, n, p=[0.23, 0.43, 0.34])
        xy = bend.ground_xy(station, offset)
        for mask in ("water", "shore", "bases"):
            approved &= site.ground.sample_mask(mask, *xy.T) < 0.006
        for idx in np.flatnonzero(approved):
            candidates.append(
                (
                    sizes[idx],
                    *xy[idx],
                    width[idx],
                    station[idx],
                    offset[idx],
                    wheel_distance[idx],
                    shoulder,
                )
            )
    rng.shuffle(candidates)
    # Separate actual coarse stones inside each lens, retaining fine spaces.
    occupied = defaultdict(list)
    chosen = defaultdict(list)
    for key, x, y, size, s, offset, wd, shoulder in candidates:
        cell = tuple(np.floor(np.array([x, y]) / 0.14).astype(int))
        nearby = (
            p
            for a in (-1, 0, 1)
            for b in (-1, 0, 1)
            for p in occupied[cell[0] + a, cell[1] + b]
        )
        if any(
            (x - px) ** 2 + (y - py) ** 2 < (0.31 * (size + old)) ** 2
            for px, py, old in nearby
        ):
            continue
        occupied[cell].append((x, y, size))
        chosen[key].append((x, y, size, s, offset, wd, shoulder))
    return chosen


def plant_mesh(site, mesh, records, rng):
    xy, diam = records[:, :2], records[:, 2]
    envelope = np.ptp(mesh, axis=0)
    scale = diam / max(envelope[:2])
    # In the largest stones most mass remains below grade. The crown visible to a
    # driver therefore has a perimeter and a side face without adding a road obstacle.
    relief = np.minimum(
        0.029, np.maximum(0.004, diam * rng.uniform(0.13, 0.31, len(diam)))
    )
    sz = np.maximum(scale * 0.40, relief / envelope[2] * 1.23)
    z = site.height(xy) + relief - mesh[:, 2].max() * sz
    slope_x = (site.height(xy + [0.12, 0]) - site.height(xy - [0.12, 0])) / 0.24
    slope_y = (site.height(xy + [0, 0.12]) - site.height(xy - [0, 0.12])) / 0.24
    normals = np.column_stack((-slope_x, slope_y, np.ones(len(diam))))
    normals /= np.linalg.norm(normals, axis=1)[:, None]
    angle = rng.uniform(0, 2 * np.pi, len(diam))
    along = np.column_stack((np.cos(angle), np.sin(angle), np.zeros(len(diam))))
    along -= normals * np.sum(along * normals, axis=1)[:, None]
    along /= np.linalg.norm(along, axis=1)[:, None]
    rot = Rotation.from_matrix(
        np.stack((along, np.cross(normals, along), normals), axis=-1)
    )
    scales = np.c_[scale, scale * rng.uniform(0.83, 1.14, len(scale)), sz]
    xyz = np.c_[xy, z] * [100, -100, 100]
    return np.asarray(np.c_[xyz, rot.as_quat(), scales], dtype="<f4")


def verify_crowns(site, camera, mesh, transforms, image):
    # The convex hull contains the extremal native LOD0 vertices. Test it against
    # the actual triangular heightfield, then project only the exposed part.
    hull = mesh[ConvexHull(mesh).vertices]
    worst, deepest_minimum, above, visible = 0.0, -1.0, [], 0
    draw = ImageDraw.Draw(image)
    for group in np.array_split(transforms, max(1, len(transforms) // 180)):
        rot = Rotation.from_quat(group[:, 3:7]).as_matrix()
        world = np.einsum(
            "ijk,ivk->ivj", rot, hull[None, :, :] * group[:, None, 7:]
        ) * [1, -1, 1]
        world += group[:, None, :3] * [0.01, -0.01, 0.01]
        relative = world[:, :, 2] - site.height(world[:, :, :2].reshape(-1, 2)).reshape(
            world.shape[:2]
        )
        worst = max(worst, float(relative.max()))
        deepest_minimum = max(deepest_minimum, float(relative.min(1).max()))
        above.extend(relative.max(1))
        screen = camera.project(world.reshape(-1, 3)).reshape(world.shape)
        for verts, z in zip(screen, relative):
            p = verts[(verts[:, 2] > 0.1) & (verts[:, 2] < 46.0) & (z > -0.002)]
            if len(p) < 3 or np.any(p[:, :2].min(0) > 1) or np.any(p[:, :2].max(0) < 0):
                continue
            pix = np.round(p[:, :2] * [1600, 900]).astype(int)
            if (
                len(np.unique(pix, axis=0)) > 2
                and np.linalg.matrix_rank(pix - pix[0]) == 2
            ):
                draw.polygon(
                    [tuple(t) for t in pix[ConvexHull(pix).vertices]], fill=255
                )
            visible += 1
    return {
        "maximum_exposed_cm": round(worst * 100, 3),
        "highest_mesh_bottom_cm": round(deepest_minimum * 100, 3),
        "median_exposed_cm": round(float(np.median(above)) * 100, 3),
        "visible_within_native_cull": visible,
    }


def generate(destination):
    site = Site()
    source = BASE / "floor"
    baseline = read(source / "verges.json")
    survey = read(SURVEY)
    camera = Camera(survey["reference_camera_pose"][:6])
    corridor = Bend(Road(site), survey["reference_landmarks"])
    rng = np.random.default_rng(1919917)
    chosen = loose_deposits(corridor, site, rng)
    groups, changes = [], {}
    image = Image.new("L", (1600, 900))
    old_rocks, added_rocks = [], []
    for i, row in enumerate(baseline["groups"], 1):
        path = source / (baseline["file"] + f".xf{i}")
        if sha256(path) != row["transform_sha256"]:
            raise ValueError("Wrong .18 source transforms for " + row["key"])
        transforms = np.fromfile(path, dtype="<f4").reshape(-1, 10)
        if row["key"] in GRAVEL:
            old_rocks.append(transforms[:, :2] * [0.01, -0.01])
            mesh_file = ROOT / row["source_glb"]
            if sha256(mesh_file) != row["sha256"]:
                raise ValueError(
                    "Native stock mesh differs from the verified inventory"
                )
            mesh = np.unique(lod0_points(mesh_file) * 0.01, axis=0)
            candidates = np.asarray(chosen[row["key"]])
            added_rocks.append(candidates[:, :2])
            new = plant_mesh(site, mesh, candidates, rng)
            crowns = verify_crowns(site, camera, mesh, new, image)
            info = {
                "base_count": len(transforms),
                "added_count": len(new),
                "count": len(transforms) + len(new),
                "base_sha256": row["transform_sha256"],
                "append_sha256": bytes_hash(new.tobytes()).hexdigest(),
                "minimum_wheel_center_distance_m": round(
                    float(candidates[:, 5].min()), 3
                ),
                "median_count": int((candidates[:, 6] == 0).sum()),
                "width_range_m": np.round(
                    [candidates[:, 2].min(), candidates[:, 2].max()], 4
                ).tolist(),
                **crowns,
            }
            if (
                info["maximum_exposed_cm"] > 3.1
                or info["highest_mesh_bottom_cm"] > 0
                or info["minimum_wheel_center_distance_m"] < 0.84
            ):
                raise ValueError(
                    f"Loose gravel projection/clearance failed for {row['key']}: {info}"
                )
            transforms = np.concatenate((transforms, new))
            info["sha256"] = bytes_hash(transforms.tobytes()).hexdigest()
            changes[row["key"]] = info
        groups.append((row, transforms))
    pack_groups(destination, baseline["actor"], groups)
    old_xy, new_xy = np.concatenate(old_rocks), np.concatenate(added_rocks)
    counts = []
    for mark in survey["reference_landmarks"]["median"]:
        centre = mark["xyz_m"][:2]
        original = int(np.sum(np.linalg.norm(old_xy - centre, axis=1) < 1))
        extra = int(np.sum(np.linalg.norm(new_xy - centre, axis=1) < 1))
        counts.append(
            {
                "station_m": mark["station_m"],
                "screen_uv": mark["uv"],
                "baseline_within_1m": original,
                "candidate_within_1m": original + extra,
            }
        )
    box = (640, 648, 1088, 792)
    proof = {
        "base_manifest_sha256": sha256(source / "verges.json"),
        "station_range_m": BEND,
        "baseline": "round18/floor",
        "groups": changes,
        "collision_changes": 0,
        "median_reference_stone_counts": counts,
        "projected_exposed_hull_coverage_central_crop_percent": round(
            100 * np.asarray(image.crop(box), dtype=bool).mean(), 2
        ),
        "projected_central_crop_px": box,
        "final_manifest_sha256": sha256(destination / "verges.json"),
    }
    save(destination / "gravel-edit.json", proof)
    image.save(destination / "projected-gravel-mask.png")
    print(proof)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--destination", type=Path, default=ART / "round19/floor")
    generate(parser.parse_args().destination)
