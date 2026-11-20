"""Check new gate lanes against the actual cooked foliage and parked vehicle locations."""

import argparse
import json
from pathlib import Path
import sys

import numpy as np
from shapely import contains_xy
from shapely.geometry import LineString, Point
from shapely.ops import unary_union

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "levels/warfare/pwr"))
sys.path.insert(0, str(ROOT / "levels/warfare/pwr/visual_dressing"))
from verify_distance_colonies import (
    GAME,
    decode,
    identity_ancestors,
    native_matrices,
    number,
    package,
    world_from_container,
)
from stage_world_playtest import sha


def check(world_file, game, features):
    doc, data = decode(world_file, GAME), world_file.read_bytes()
    by_id = {r["export"]: r for r in doc["exports"]}
    lanes = {}
    for f in features:
        p = f["properties"]
        if p["role"] in ("front", "rear"):
            line = LineString(f["geometry"]["coordinates"])
            footprint = line.buffer(p["width_m"] / 2, cap_style="flat")
            lanes[p["site"] + "-" + p["role"]] = (line, footprint)
    if len(lanes) != 6:
        raise ValueError("Expected a front and rear drive at each base")
    footprint = unary_union([polygon for _, polygon in lanes.values()])
    sightings = {}
    total = 0
    for row in by_id.values():
        if row["class"] != "HierarchicalInstancedStaticMeshComponent":
            continue
        count = int(number(row["properties"].get("NumBuiltInstances")))
        identity_ancestors(row, by_id)
        xy = native_matrices(data, row, count)[:, 3, :2] * [0.01, -0.01]
        total += count
        hit = contains_xy(footprint, xy[:, 0], xy[:, 1])
        if np.any(hit):
            mesh = package(row, "StaticMesh").rsplit("/", 1)[-1]
            sightings.setdefault(mesh, []).extend(np.round(xy[hit], 3).tolist())
    # The spawn positions are native scenario inputs, in UE centimetres.
    parking = []
    for entry in game["blam"]["vehicles"]:
        if not entry.get("pos"):
            continue
        x, y = entry["pos"][:2]
        origin = Point(x * 0.01, -y * 0.01)
        which, distance = min(
            ((k, line.distance(origin)) for k, (line, _) in lanes.items()),
            key=lambda t: t[1],
        )
        edge = footprint.distance(origin)
        parking.append(
            {
                "vehicle": entry.get("name", entry["type"]),
                "lane": which,
                "centerline_distance_m": round(distance, 2),
                "lane_edge_distance_m": round(edge, 2),
            }
        )
    parking.sort(key=lambda v: v["lane_edge_distance_m"])
    return {
        "world_package": doc["package"],
        "lane_lengths_m": {k: round(v[0].length, 2) for k, v in lanes.items()},
        "foliage_roots_checked": total,
        "roots_on_a_lane": sightings,
        "nearest_parked_vehicles": parking[:8],
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--routes", type=Path, required=True)
    parser.add_argument("--world", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    world = world_from_container(args.world, args.out / "drive-check.umap")
    result = check(
        world,
        json.loads((args.baseline / "map-input/pwr.level.json").read_text()),
        json.loads(args.routes.read_text())["features"],
    )
    result.update(world_sha256=sha(world), routes_sha256=sha(args.routes))
    if result["roots_on_a_lane"] or any(
        v["lane_edge_distance_m"] == 0 for v in result["nearest_parked_vehicles"]
    ):
        raise ValueError(f"An approach is obstructed: {result}")
    (args.out / "clearance.json").write_text(json.dumps(result, indent=2) + "\n")
    print(
        json.dumps(
            {
                **result,
                "roots_on_a_lane": {
                    k: len(v) for k, v in result["roots_on_a_lane"].items()
                },
            }
        )
    )
