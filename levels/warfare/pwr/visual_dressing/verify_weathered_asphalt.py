"""Check .25 pavement eligibility against the shipping road atlas and real drive corridors."""

import argparse
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[4]
NETWORK = ROOT / "out/pwr/base-approaches/roads/native-road-network.png"
GEOMETRY = ROOT / "levels/warfare/pwr/terrain/final-v5/terrain.geometry.json"
GATES = ROOT / "out/pwr/base-approaches/geometry/gate-routes.geojson"
SHADER = ROOT / "unreal/MJOLNIRMaterials/Scripts/pwr_weathered_asphalt.ush"
sys.path.insert(0, str(SHADER.parent))
from pwr_asphalt_source import wearing_course


def digest(file):
    return hashlib.sha256(file.read_bytes()).hexdigest()


def smooth(a, b, x):
    t = np.clip((x - a) / (b - a), 0, 1)
    return t * t * (3 - 2 * t)


def sample(tex, xy):
    # Survey uses north-positive y. The normalized texture y follows native UE.
    n = tex.shape[0]
    uv = (np.asarray(xy) * [1, -1] + 1000.0) * (n / 2000.0) - 0.5
    uv = np.clip(uv, 0, n - 1.001)
    i, j = np.floor(uv).astype(int).T
    f, g = (uv - np.floor(uv)).T[:, :, None]
    return (
        (1 - g) * ((1 - f) * tex[j, i] + f * tex[j, i + 1])
        + g * ((1 - f) * tex[j + 1, i] + f * tex[j + 1, i + 1])
    ) / 255.0


def weights(tex, points):
    fields = sample(tex, points)
    cover, green, encoded, _ = fields.T
    side = (encoded - 0.5) * 32.0
    local = smooth(0.43, 0.68, green / np.maximum(cover, 0.001))
    # At mip 0, finite differences in two independent world-space directions
    # recover the same inboard unit vector as the shader's camera Jacobian.
    east = (
        sample(tex, points + [0.125, 0])[:, 2] - sample(tex, points - [0.125, 0])[:, 2]
    )
    north = (
        sample(tex, points + [0, 0.125])[:, 2] - sample(tex, points - [0, 0.125])[:, 2]
    )
    v = np.stack([east, north], axis=1)
    v /= np.maximum(np.linalg.norm(v, axis=1)[:, None], 1e-12)
    inward = points - np.sign(side)[:, None] * v * 4.9
    near = sample(tex, inward)
    ring = (abs(side) > 6.2) & (abs(side) < 14.2)
    inboard = smooth(0.46, 0.67, near[:, 1] / np.maximum(near[:, 0], 0.001))
    local = np.where(ring, np.maximum(inboard, local), local)
    return np.where(
        cover > 0.002, local * cover * (1 - smooth(10.1, 13.1, abs(side))), 0
    )


def section(route, station, offsets):
    line = np.asarray(route["centreline_m"])[:, :2]
    arc = np.r_[0.0, np.cumsum(np.linalg.norm(np.diff(line, axis=0), axis=1))]
    station = np.asarray(station, dtype=float).reshape(-1)
    points = np.column_stack([np.interp(station, arc, line[:, i]) for i in range(2)])
    along = np.column_stack(
        [
            np.interp(station + 0.7, arc, line[:, i])
            - np.interp(station - 0.7, arc, line[:, i])
            for i in range(2)
        ]
    )
    normal = np.stack([-along[:, 1], along[:, 0]], axis=-1)
    normal /= np.linalg.norm(normal, axis=1)[:, None]
    return points[:, None, :] + normal[:, None, :] * np.asarray(offsets)[None, :, None]


def verify(art):
    tex = np.asarray(Image.open(NETWORK).convert("RGBA"))
    geo = json.loads(GEOMETRY.read_text())
    roads = {r["id"]: r for r in geo["roads"]}
    poses = json.loads((art / "paved/survey.json").read_text())["sites"]
    offsets = [
        -16.0,
        -13.5,
        -12.0,
        -10.5,
        -9.5,
        -8.0,
        -6.0,
        0.0,
        6.0,
        8.0,
        9.5,
        10.5,
        12.0,
        13.5,
        16.0,
    ]
    profiles = {}
    for key in ("primary", "secondary"):
        site = poses[key]
        road = roads[site["route"]]
        sta = site["station_m"] + np.arange(-12.0, 12.1, 2.0)
        points = section(road, sta, offsets)
        profile = weights(tex, points.reshape(-1, 2)).reshape(points.shape[:2])
        med = np.median(profile, axis=0)
        if min(med[i] for i, d in enumerate(offsets) if abs(d) <= 8) < 0.96:
            raise ValueError(f"Unfinished asphalt at {key}")
        if max(med[0], med[-1]) != 0 or min(med[4], med[-5]) < 0.7:
            raise ValueError(f"Paved edge fell outside the graded shoulder at {key}")
        profiles[key] = {
            "route": site["route"],
            "station_m": site["station_m"],
            "ground_route_weight_median": med.round(4).tolist(),
            "original_graded_width_m": road["width_m"],
        }

    inventory = {}
    for row in json.loads((NETWORK.parent / "roads.json").read_text())["routes"]:
        if row["kind"] != "primary" or row["id"] not in roads:
            continue
        rid = row["id"]
        length = np.linalg.norm(
            np.diff(np.asarray(roads[rid]["centreline_m"])[:, :2], axis=0), axis=1
        ).sum()
        survey = np.linspace(length * 0.09, length * 0.91, 55)
        points = section(roads[rid], survey, [-6.0, 0.0, 6.0])
        current = sample(tex, points.reshape(-1, 2))
        eligible = (current[:, 0] > 0.95) & (
            current[:, 1] / np.maximum(0.001, current[:, 0]) > 0.69
        )
        changed = weights(tex, points.reshape(-1, 2))
        if np.any(changed[eligible] < 0.93):
            raise ValueError(f"A surveyed paved lane was missed on {rid}")
        inventory[rid] = {
            "probes": len(eligible),
            "dry_primary_lane_samples": int(eligible.sum()),
        }

    # Check the road itself before applying the additional Alpine local exclusion.
    stations = np.arange(35.0, 175.1, 0.8)
    sweep = section(roads["southwest_sweep"], stations, np.arange(-15.0, 15.1, 0.3))
    sweep_values = weights(tex, sweep.reshape(-1, 2))
    if np.any(sweep_values):
        raise ValueError(
            "Pavement survey falls on the certified Southwest driver segment"
        )
    gates = json.loads(GATES.read_text())
    pads = {}
    for feature in gates["features"]:
        role = feature["properties"]["role"]
        if role not in ("court", "rear_pad"):
            continue
        boundary = np.asarray(feature["geometry"]["coordinates"][0])[:, :2]
        centre = np.mean(boundary[:-1], axis=0)
        interior = np.vstack([centre, centre + 0.85 * (boundary[:-1] - centre)])
        maximum = float(weights(tex, interior).max())
        if maximum != 0:
            raise ValueError("Grade overlaps a solid native court/pad")
        pads[feature["properties"]["site"] + "_" + role] = maximum
    if len(pads) != 6:
        raise ValueError("Expected distinct court and rear pad at all three bases")
    report = {
        "material": "/Game/MJOLNIR/GrassPilot/Playable/M_PWRPilot",
        "shader_sha256": digest(SHADER),
        "shipping_road_atlas_png_sha256": digest(NETWORK),
        "geometry_sha256": digest(GEOMETRY),
        "survey_sha256": digest(art / "paved/survey.json"),
        "offsets_m": offsets,
        "profiles": profiles,
        "main_route_inventory": inventory,
        "protected_courts_and_pads": pads,
        "southwest_samples": int(sweep_values.size),
        "southwest_max_influence": float(sweep_values.max()),
        "physical_inputs": [
            "SweepFloorDetail (gravel relief/normal)",
            "PathGravel",
            "PathGravelNormal",
            "SiteEarth",
            "RoadAtlas",
        ],
        "required_new_native_packages": [],
        "physics_or_elevation_writes": 0,
        "note": "Mipped road eligibility at near-field precision. The local weathered side varies with the stock material scans.",
    }
    reopened = art / "earth/editor-verified.json"
    if reopened.exists():
        native = json.loads(reopened.read_text())
        graph = (art / "earth/actual-graph.hlsl").read_text(encoding="cp1252")
        marker = wearing_course(native["revision"])
        graph_sha = hashlib.sha256(graph.encode()).hexdigest()
        if (
            native["revision"] < 25
            or native["shader_sha256"] != graph_sha
            or graph.count(marker) != 1
            or not graph.rstrip().endswith(marker + "\nreturn originalGround;")
        ):
            raise ValueError(
                "Saved native terrain material is not the tested asphalt shader"
            )
        report["reopened_editor"] = {
            "material": native["material"],
            "saved_full_shader_sha256": graph_sha,
            "receipt_sha256": digest(reopened),
            "scoped_asphalt_detail_reads": native["scoped_asphalt_detail_reads"],
        }
        report["compiled_asphalt_source_sha256"] = hashlib.sha256(marker.encode()).hexdigest()
    (art / "paved/material-scope.json").write_text(json.dumps(report, indent=2) + "\n")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("art", type=Path)
    args = parser.parse_args()
    print(json.dumps(verify(args.art.resolve()), indent=2))
