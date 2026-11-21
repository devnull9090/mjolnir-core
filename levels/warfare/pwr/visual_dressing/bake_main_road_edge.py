# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy>=2,<3", "scipy>=1.15", "pillow>=11", "shapely>=2", "trimesh>=4"]
# ///
"""Bake small pockets of native gravel into the fracture line of dry paved routes."""

import argparse
import json
from pathlib import Path

import numpy as np
from bake_approach_roads import GEOMETRY, lines_from_geometry
from bake_main_road_verges import (
    GATES,
    Site,
    pack_groups,
    pcg_foliage,
    read,
    save,
    sha256,
)
from PIL import Image
from prepare_alpine_verges import ROOT, Camera, lod0_points
from prepare_sweep_gravel import plant_mesh
from scipy.spatial import ConvexHull, cKDTree
from scipy.spatial.transform import Rotation
from shapely import contains_xy
from shapely.geometry import shape
from verify_weathered_asphalt import NETWORK, sample, weights

OWNER = "PWR_MainRoadEdgeGravel"
PREFIX = "PWRMainRoadEdge_"
KEYS = ("Gravel1", "Gravel2", "Gravel3")
SEED = 300761


def mesh_key(point):
    return KEYS[int(np.searchsorted([0.40, 0.72], point["asset_draw"]))]


def deposits(rng, routes):
    points = []
    for route in routes:
        if route["kind"] != "primary":
            continue
        line = route["xy"]
        length = np.r_[0.0, np.cumsum(np.linalg.norm(np.diff(line, axis=0), axis=1))]
        nominal = route.get("width_m", 16.0) / 16.0
        for bank in (-1.0, 1.0):
            station = rng.uniform(1.0, 5.0)
            while station < length[-1] - 1.0:
                count = rng.integers(7, 24)
                along = np.clip(
                    station + rng.normal(0, rng.uniform(0.4, 1.65), count),
                    0.3,
                    length[-1] - 0.3,
                )
                centers = np.column_stack([np.interp(along, length, v) for v in line.T])
                tangent = np.column_stack(
                    [
                        np.interp(along + 0.24, length, v)
                        - np.interp(along - 0.24, length, v)
                        for v in line.T
                    ]
                )
                tangent /= np.linalg.norm(tangent, axis=1)[:, None]
                # A shallow fan of escaped stones tails away from an irregular lip.
                # The next pocket begins after an independent stretch of empty soil.
                out = rng.gamma(1.2, rng.uniform(0.22, 0.55), count)
                lateral = (8.84 + rng.uniform(-0.21, 0.36) + out) * nominal
                normal = np.column_stack([-tangent[:, 1], tangent[:, 0]])
                points.extend(centers + normal * (bank * lateral)[:, None])
                station += rng.uniform(2.8, 8.8)
    return np.asarray(points)


def prepare(folder):
    routes, junctions = lines_from_geometry(read(GEOMETRY), read(GATES))
    rng = np.random.default_rng(SEED)
    xy = deposits(rng, routes)
    atlas = np.array(Image.open(NETWORK).convert("RGBA"))
    edge = abs((sample(atlas, xy)[:, 2] - 0.5) * 32.0)
    allowed = (edge > 8.57) & (edge < 12.65) & (weights(atlas, xy) > 0.10)
    allowed &= cKDTree(junctions).query(xy)[0] > 19.5
    for feature in read(GATES)["features"]:
        if feature["properties"]["role"] in ("court", "rear_pad"):
            allowed &= ~contains_xy(shape(feature["geometry"]).buffer(3), *xy.T)
    site = Site()
    allowed &= site.trunks.query(xy)[0] > 1.45
    for check in (xy, xy + [0.35, 0], xy - [0.35, 0], xy + [0, 0.35], xy - [0, 0.35]):
        for layer in ("water", "shore", "bases"):
            allowed &= (
                site.ground.sample_mask(layer, *check.T, bounds_error=False) < 0.006
            )
    for center, radius in site.protected:
        allowed &= np.sum((xy - center) ** 2, axis=1) > (radius + 0.85) ** 2
    xy, edge = xy[allowed], edge[allowed]
    heights = site.height(xy)
    points = []
    for pos, z, gap in zip(xy, heights, edge - 8.65):
        diameter = np.clip(rng.lognormal(np.log(0.096), 0.47), 0.042, 0.215)
        points.append(
            {
                "id": len(points),
                "position": [*pos, z],
                "normal": [0, 0, 1],
                "biome_mask": 1,
                "density": float(0.77 - 0.07 * max(gap, 0.0)),
                "width_m": float(diameter),
            }
        )
    source = folder / "candidates.json"
    source.write_text(
        json.dumps(
            {"schema": 1, "align_to_normal": False, "points": points},
            separators=(",", ":"),
        )
    )
    jobs = [
        {
            "input": str(source),
            "output": str(folder / f"points{suffix}.json"),
            "seed": SEED,
            "scale_min": 0.88,
            "scale_max": 1.13,
            "graph": "/Game/MJOLNIR/PCGAuthoring/PWRField/PCG_MainRoadEdge" + suffix,
        }
        for suffix in ("", "_repeat")
    ]
    save(folder / "request.json", {"jobs": jobs})
    print(len(points), "native PCG candidates")


def seat(site, definition, records, rng):
    vertices = np.unique(lod0_points(ROOT / definition["source_glb"]) * 0.01, axis=0)
    hull = vertices[ConvexHull(vertices).vertices]
    transforms = plant_mesh(site, vertices, records, rng)
    crowns = []
    for group in np.array_split(transforms, max(1, len(transforms) // 160)):
        rotation = Rotation.from_quat(group[:, 3:7]).as_matrix()
        world = np.einsum(
            "ijk,ivk->ivj", rotation, hull[None, :, :] * group[:, None, 7:]
        ) * [1, -1, 1]
        world += group[:, None, :3] * [0.01, -0.01, 0.01]
        height = site.height(world[:, :, :2].reshape(-1, 2)).reshape(world.shape[:2])
        rel = world[:, :, 2] - height
        # Seat each individual scanned shape into the actual triangular surface.
        desired = np.minimum(
            0.047, (rel.max(1) - rel.min(1)) * rng.uniform(0.36, 0.66, len(group))
        )
        group[:, 2] += (desired - rel.max(1)) * 100
        if np.any(rel.min(1) + desired - rel.max(1) >= 0):
            raise ValueError("A gravel piece has no buried base")
        crowns.extend(desired)
    return transforms, np.round(np.percentile(crowns, [0, 50, 100]), 5).tolist()


def finalize(folder, parent):
    source = folder / "candidates.json"
    first, repeat = folder / "points.json", folder / "points_repeat.json"
    proof = pcg_foliage.compare(source, first, repeat)
    submitted = read(source)["points"]
    groups = {key: [] for key in KEYS}
    selected = read(first)["points"]
    for point in sorted(selected, key=lambda row: row["id"]):
        candidate = submitted[point["id"]]
        key = mesh_key(point)
        groups[key].append(
            [*candidate["position"][:2], candidate["width_m"] * point["scale_xyz"][0]]
        )
    rng = np.random.default_rng(SEED + 1)
    site = Site()
    catalog = {g["key"]: g for g in read(parent / "floor/verges.json")["groups"]}
    result, heights = [], {}
    for key, records in groups.items():
        poses, heights[key] = seat(site, catalog[key], np.asarray(records), rng)
        result.append((catalog[key], poses))
    pack_groups(folder, OWNER, result)
    positions = np.vstack([r[:, :3] for _, r in result]) * [0.01, -0.01, 0.01]
    poses = read(parent / "paved/survey.json")["sites"]
    nearby, on_screen = {}, {}
    for key, site_pose in poses.items():
        camera = Camera(site_pose["pose"])
        horizontal = np.linalg.norm(positions[:, :2] - camera.eye[:2], axis=1)
        nearby[key] = int((horizontal < 24.0).sum())
        uvz = camera.project(positions)
        inside = (uvz[:, 2] > 0) & ((uvz[:, :2] > 0) & (uvz[:, :2] < 1)).all(axis=1)
        distance = np.linalg.norm(positions - camera.eye, axis=1)
        on_screen[key] = {
            str(metres): int((inside & (distance < metres)).sum())
            for metres in (24, 46)
        }
    if any(site["24"] < 12 for site in on_screen.values()):
        raise ValueError(
            "Insufficient physical edge detail at the review approaches: "
            + str(on_screen)
        )
    save(
        folder / "survey.json",
        {
            "actor": OWNER,
            "count": len(selected),
            "seed": SEED,
            "graph": read(first)["graph"],
            "deterministic_repeat": proof,
            "road_field_sha256": sha256(NETWORK),
            "crown_range_m": heights,
            "within_24m_of_driver": nearby,
            "projected_pivots_by_distance_m": on_screen,
            "width_range_m": [
                float(min(r[2] for rows in groups.values() for r in rows)),
                float(max(r[2] for rows in groups.values() for r in rows)),
            ],
        },
    )
    print({k: len(v) for k, v in groups.items()}, heights, on_screen)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "finalize"))
    parser.add_argument("folder", type=Path)
    parser.add_argument("--parent", type=Path, required=True)
    args = parser.parse_args()
    out = args.folder.resolve()
    out.mkdir(parents=True, exist_ok=True)
    if args.action == "prepare":
        prepare(out)
    else:
        finalize(out, args.parent)
