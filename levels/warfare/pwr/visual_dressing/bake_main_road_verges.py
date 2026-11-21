"""Grow low grass and embedded stones outwards from the painted asphalt footprint."""

import argparse
import json
import sys
from pathlib import Path

import numpy as np
from bake_approach_roads import GEOMETRY, lines_from_geometry
from build_sweep_banks import pack_groups
from PIL import Image
from prepare_alpine_verges import ROOT, Site, read, sha256
from prepare_sweep_road_dressing import fit_debris
from scipy.ndimage import distance_transform_edt, map_coordinates
from scipy.spatial import cKDTree
from shapely import contains_xy
from shapely.geometry import shape

sys.path.insert(0, str(ROOT / "tools/level"))
import pcg_foliage

SEED = 250924
ROAD = ROOT / "out/pwr/base-approaches/roads/road-network.png"
GATES = ROOT / "out/pwr/base-approaches/geometry/gate-routes.geojson"
OWNER = "PWR_MainRoadVerges"
KEYS = ("FescueA", "FescueB", "Gravel1", "Gravel2")


def save(path, value):
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def maps():
    with Image.open(ROAD) as source:
        atlas = np.asarray(source.convert("RGBA"), dtype=float) / 255
    cover = atlas[:, :, 0]
    primary = (cover > 0.70) & (atlas[:, :, 1] > 0.65 * cover)
    return atlas, distance_transform_edt(~primary) * 2000 / len(cover)


def sample(field, xy):
    scale = len(field) / 2000
    coordinates = np.array(
        [(1000 - xy[:, 1]) * scale - 0.5, (xy[:, 0] + 1000) * scale - 0.5]
    )
    return map_coordinates(field, coordinates, order=1, mode="nearest", prefilter=False)


def candidates(folder):
    rng = np.random.default_rng(SEED)
    atlas, distance = maps()
    road_art = read(ROAD.with_name("roads.json"))
    if sha256(ROAD) != road_art["sha256"]:
        raise ValueError("The planted verge needs the released road footprint")
    anchors = np.argwhere((distance >= 1.2) & (distance < 5.8))
    anchors = anchors[
        rng.choice(len(anchors), size=min(2150, len(anchors)), replace=False)
    ]
    xy = np.column_stack(
        (
            (anchors[:, 1] + 0.5) * 2000 / len(distance) - 1000,
            1000 - (anchors[:, 0] + 0.5) * 2000 / len(distance),
        )
    )
    # Clusters vary in footprint and density; bare dirt separates successive colonies.
    sizes = rng.integers(5, 14, len(xy))
    spreads = np.repeat(rng.uniform(0.45, 1.60, len(xy)), sizes)
    xy = (
        np.repeat(xy, sizes, axis=0)
        + rng.normal(size=(sum(sizes), 2)) * spreads[:, None]
    )
    gap = sample(distance, xy)
    inside = (gap >= 1.30) & (gap <= 6.30)
    # Keep points off crossing service tracks, bridge beds, paved courts, pads and spawns.
    footprint = sample(atlas[:, :, 0], xy)
    side = np.abs((sample(atlas[:, :, 2], xy) - 0.5) * 32)
    inside &= (footprint < 0.32) | (side > 9.25)
    approaches = read(GATES)
    _, joins = lines_from_geometry(read(GEOMETRY), approaches)
    inside &= cKDTree(joins).query(xy)[0] > 19.0
    for feature in approaches["features"]:
        if feature["properties"]["role"] in ("court", "rear_pad"):
            polygon = shape(feature["geometry"]).buffer(3)
            inside &= ~contains_xy(polygon, xy[:, 0], xy[:, 1])
    site = Site()
    for offset in ((0, 0), (0.75, 0), (-0.75, 0), (0, 0.75), (0, -0.75)):
        check = xy + offset
        for layer in ("water", "shore", "bases"):
            inside &= (
                site.ground.sample_mask(layer, *check.T, bounds_error=False) < 0.006
            )
    inside &= site.trunks.query(xy)[0] > 1.45
    # Each protected disc has its own radius, including the base and objective volumes.
    for centre, radius in site.protected:
        inside &= np.sum((xy - centre) ** 2, axis=1) > (radius + 0.85) ** 2
    xy, gap = xy[inside], gap[inside]
    if not len(xy):
        raise ValueError("Road and gameplay masks excluded every verge point")
    z = site.height(xy)
    slope_x = site.height(xy + [0.5, 0]) - site.height(xy - [0.5, 0])
    slope_y = site.height(xy + [0, 0.5]) - site.height(xy - [0, 0.5])
    normals = np.column_stack((-slope_x, -slope_y, np.ones(len(z))))
    normals /= np.linalg.norm(normals, axis=1)[:, None]
    points = []
    for i, (position, height, normal, edge) in enumerate(zip(xy, z, normals, gap)):
        grass_bias = float(np.clip((edge - 1.1) / 4.8, 0.03, 0.92))
        points.append(
            {
                "id": i,
                "position": [*position, height],
                "normal": normal.tolist(),
                "density": float(0.40 + 0.27 * grass_bias),
                "biome_mask": 1,
                "verge_gap_m": float(edge),
                "grass_bias": grass_bias,
            }
        )
    source = folder / "candidates.json"
    source.write_text(
        json.dumps(
            {"schema": 1, "align_to_normal": True, "points": points},
            separators=(",", ":"),
        )
    )
    jobs = []
    for suffix in ("", "_repeat"):
        jobs.append(
            {
                "input": str(source),
                "output": str(folder / f"points{suffix}.json"),
                "seed": SEED,
                "scale_min": 0.73,
                "scale_max": 1.16,
                "graph": "/Game/MJOLNIR/PCGAuthoring/PWRField/PCG_AsphaltVerges"
                + suffix,
            }
        )
    save(folder / "request.json", {"jobs": jobs})
    print(len(points), "source points")


def finalize(folder, parent):
    source = folder / "candidates.json"
    first, repeat = folder / "points.json", folder / "points_repeat.json"
    proof = pcg_foliage.compare(source, first, repeat)
    points = read(source)["points"]
    selected = sorted(read(first)["points"], key=lambda v: v["id"])
    catalog = {row["key"]: row for row in read(parent / "floor/verges.json")["groups"]}
    site = Site()
    pieces = {key: [] for key in KEYS}
    poses = {key: [] for key in KEYS}
    gap_values = []
    for point in selected:
        src = points[point["id"]]
        edge, draw = src["verge_gap_m"], point["asset_draw"]
        size = point["scale_xyz"][0]
        gap_values.append(edge)
        if draw < src["grass_bias"]:
            key = "FescueA" if draw < src["grass_bias"] * 0.64 else "FescueB"
            scale = size * np.clip(0.41 + 0.113 * (edge - 1.3), 0.41, 0.97)
            pos = point["position_cm"].copy()
            pos[2] -= 0.55
            poses[key].append([*pos, *point["rotation_xyzw"], scale, scale, scale])
        else:
            prop = (draw - src["grass_bias"]) / (1 - src["grass_bias"])
            key = "Gravel1" if prop < 0.74 else "Gravel2"
            width = size * (0.044 + 0.080 * prop)
            pieces[key].append([*src["position"][:2], width])
    rng = np.random.default_rng(SEED + 1)
    entries = []
    for key in KEYS:
        data = (
            np.asarray(poses[key], dtype="<f4")
            if key.startswith("Fescue")
            else fit_debris(site, catalog[key], np.asarray(pieces[key]), rng)
        )
        if not len(data):
            raise ValueError("No planted instances of " + key)
        entries.append((catalog[key], data))
    pack_groups(folder, OWNER, entries)
    survey = {
        "actor": OWNER,
        "road_field": str(ROAD.relative_to(ROOT)),
        "road_field_sha256": sha256(ROAD),
        "graph": read(first)["graph"],
        "seed": SEED,
        "deterministic_repeat": proof,
        "editor_receipt": read(folder / "request.receipt.json"),
        "source_count": len(points),
        "count": len(selected),
        "minimum_pivot_distance_to_asphalt_m": min(gap_values),
        "maximum_distance_m": max(gap_values),
        "exclusions": [
            "driving surface",
            "junctions within 19 m",
            "water, shore and bases",
            "spawn and objective volumes",
            "trees and existing protected props",
            "courts and rear pads",
        ],
        "groups": {
            definition["key"]: {
                "count": len(rows),
                "mesh": definition["mesh"],
                "cull": definition["cull"],
                "source_mesh_sha256": definition["sha256"],
            }
            for definition, rows in entries
        },
    }
    save(folder / "survey.json", survey)
    print(
        survey["count"], "baked points", survey["minimum_pivot_distance_to_asphalt_m"]
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["prepare", "finalize"])
    parser.add_argument("folder", type=Path)
    parser.add_argument(
        "--parent", type=Path, default=ROOT / "out/pwr/sweep-polish/round24"
    )
    args = parser.parse_args()
    out = args.folder.resolve()
    out.mkdir(exist_ok=True, parents=True)
    if args.action == "prepare":
        candidates(out)
    else:
        finalize(out, args.parent)
