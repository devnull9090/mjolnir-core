"""Bake driver-scale mineral shoulders, pine litter and wet depressions on two PWR roads.

Each 256 m tile is kept separate to retain half-metre survey data in one small
mipmapped atlas. Coordinates come from the shipped splines, pine instances and
terrain. Rendering and collision share their original heightfield.
"""

import argparse
import json
from pathlib import Path
import sys

import numpy as np
from PIL import Image
from scipy.ndimage import gaussian_filter
from scipy.spatial import cKDTree

from bake_approach_roads import GEOMETRY, ROOT, sha, smooth
from bake_site_finish import noise
from ground_life_earth import MASTER, TREES

sys.path.insert(0, str(ROOT / "tools/level"))
from heightfield import load_heightfield

OUT = ROOT / "out/pwr/alpine-target/earth"
CAPTURES = ROOT / "out/pwr/ground-life/visual-review"
DEFAULT_LEVEL = ROOT / "out/pwr/ground-life/saturday.13/map-input/pwr.level.json"
TILES = (
    ("teton-road", "red_upper_approach", (-400.0, -112.0), True),
    ("southwest-forest-road-driver", "southwest_sweep", (-580.0, -540.0), False),
)
SPAN = 256
SIZE = 512
STEP = SPAN / SIZE


def load(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def densify(line):
    distance = np.r_[0.0, np.cumsum(np.linalg.norm(np.diff(line, axis=0), axis=1))]
    station = np.linspace(0.0, distance[-1], int(np.ceil(distance[-1] / 0.25)) + 1)
    return np.column_stack([np.interp(station, distance, v) for v in line.T])


def paint(tile, field, level, roads, trees, camera, existing):
    name, route, centre, paved = tile
    axis = (np.arange(SIZE) + 0.5) * STEP - SPAN / 2
    x, y = np.meshgrid(centre[0] + axis, centre[1] - axis)
    xy = np.c_[x.ravel(), y.ravel()]
    points = densify(roads[route])
    distance, index = cKDTree(points).query(xy)
    point = points[index]
    tangent = (
        points[np.minimum(index + 1, len(points) - 1)]
        - points[np.maximum(index - 1, 0)]
    )
    tangent /= np.linalg.norm(tangent, axis=1)[:, None]
    nearest = xy - point
    side = (nearest[:, 1] * tangent[:, 0] - nearest[:, 0] * tangent[:, 1]).reshape(
        x.shape
    )
    distance = distance.reshape(x.shape)
    root_gap = cKDTree(trees).query(xy)[0].reshape(x.shape)
    crown_gap = cKDTree(trees).query(xy, k=3)[0][:, -1].reshape(x.shape)
    other = np.concatenate([points for key, points in roads.items() if key != route])
    other_gap = cKDTree(other).query(xy)[0].reshape(x.shape)

    water = field.sample_mask("water", x, y)
    shore = field.sample_mask("shore", x, y)
    protected = (
        (field.sample_mask("bases", x, y) > 0.002) | (water > 0.006) | (shore > 0.02)
    )
    for group in (
        level["markers"],
        level["blam"]["vehicles"],
        level["blam"]["player_starts"],
    ):
        for obj in group:
            px, py = obj["pos"][:2]
            protected |= (x - 0.01 * px) ** 2 + (y + 0.01 * py) ** 2 < 13**2
    for px, py, _, radius, *_ in level["koth_hills"]:
        protected |= (x - 0.01 * px) ** 2 + (y + 0.01 * py) ** 2 < (
            0.01 * radius + 9
        ) ** 2
    for bx, by in ((-590, -80), (600, -80), (0, 690)):
        protected |= (abs(x - bx) < 112) & (y > by - 125) & (y < by + 142)

    # A collective litter bed follows both isolated roots and connected crowns.
    broad = noise(x, y, 11.3, 44)
    fine = noise(x, y, 2.6, 29)
    sheltered = 1 - smooth(10, 25, crown_gap)
    root = 1 - smooth(1.3, 7 + 3.0 * sheltered + 1.45 * broad + 0.8 * fine, root_gap)
    duff = np.maximum(
        root, sheltered * (1 - smooth(6.0, 14.5 + broad * 2.0, root_gap)) * 0.79
    )
    # Even the inner verge remains outside the target's nominal clear slab.
    # On the dirt road, gravel replaces the broad barrenness gradually at 6–10 m.
    inner = 8.78 if paved else 5.55
    duff *= smooth(inner + 0.45, inner + 3.2, distance + 0.68 * fine) * (
        0.89 + 0.10 * fine
    )
    shoulder = inner + (1.1 if paved else 1.55) + 0.9 * broad + 0.43 * fine
    edge = 1 - smooth(0.18, 2.3 if paved else 3.5, abs(distance - shoulder))
    # Deposit fans occupy the downhill verge; tire wear displaces coarse gravel.
    height = field.sample(x, y)
    grad_north, grad_east = np.gradient(height, -STEP, STEP)
    slope = np.hypot(grad_north, grad_east)
    relief = gaussian_filter(height, sigma=4.0 / STEP) - height
    hollow = smooth(-0.018, 0.043, relief)
    tracks = np.exp2(-(((abs(side + 0.20 * broad) - 1.40) / 0.52) ** 2))
    gravel = edge * (0.64 + 0.15 * fine + 0.12 * broad + 0.11 * hollow)
    if not paved:
        gravel = np.maximum(
            gravel,
            (1 - smooth(5.0, 8.3, distance))
            * (0.23 + 0.24 * (0.5 + 0.5 * broad) + 0.17 * (0.5 + 0.5 * fine))
            * (1 - 0.89 * tracks),
        )
    gravel *= 1 - 0.78 * duff

    wet = np.zeros(x.shape)
    if not paved:
        # Sky-reflecting pockets on low-grade wheel paths and washouts. The
        # water/shore masks and all Flux lakes/riverbanks remain excluded.
        pockets = smooth(0.12, 0.58, 0.66 * fine + 0.34 * broad)
        wet = (1 - smooth(0.085, 0.225, slope)) * (0.22 + 0.78 * hollow) * pockets
        wet *= np.maximum(tracks, 0.64 * edge) * (1 - smooth(7.2, 9.7, distance))

    border = np.maximum(abs(x - centre[0]), abs(y - centre[1]))
    tile_fade = (1 - smooth(107.0, 121.0, border)) * smooth(11.0, 21.0, other_gap)
    area = np.maximum(1 - smooth(11.8, 15.2, distance), duff)
    active = np.where(protected, 0.0, area * tile_fade)
    channels = np.stack((active, active * gravel, active * duff, active * wet), axis=-1)
    result = np.rint(255 * np.clip(channels, 0, 1)).astype(np.uint8)
    if result[protected].any() or np.any(result[:, :, 1:] > result[:, :, :1]):
        raise ValueError("Filtered blend or protected site changed")
    if (
        result[:9].any()
        or result[-9:].any()
        or result[:, :9].any()
        or result[:, -9:].any()
    ):
        raise ValueError("Atlas needs a zero guard band")
    near = (x - camera[0]) ** 2 + (y - camera[1]) ** 2 < 95**2
    core = (distance < 5.2) & near
    if np.any(result[core, 2]):
        raise ValueError("Pine litter intrudes on the driving lanes")
    at_trunks = (root_gap < 2.2) & (distance > inner + 3.0) & near & (active > 0.8)
    at_shoulder = (abs(distance - inner - 1) < 1.5) & near & (active > 0.8)
    report = dict(
        camera_authoring_xy_m=camera,
        route=route,
        centre_xy_m=centre,
        existing_trunks_within_95m=int(
            (np.linalg.norm(trees[:existing] - camera, axis=1) < 95).sum()
        ),
        proposed_trunks_within_95m=int(
            (np.linalg.norm(trees[existing:] - camera, axis=1) < 95).sum()
        ),
        applied_m2=round(float(active.sum() * STEP**2), 1),
        zero_on_protected_and_guard_texels=True,
        pine_litter_inside_10_4m_drive_m2=0,
        near_camera_duff_at_live_trunks_median=round(
            float(np.median(duff[at_trunks])), 3
        ),
        near_camera_gravel_edge_median=round(float(np.median(gravel[at_shoulder])), 3),
        near_camera_damp_patch_m2=round(
            float(((wet > 0.22) & near & (active > 0.8)).sum() * STEP**2), 2
        ),
        near_camera_wet_peak=float(wet[near & (active > 0.8)].max()),
        median_verge_width_m=round(float(np.median(shoulder[at_shoulder]) - inner), 2),
    )
    if (
        report["near_camera_duff_at_live_trunks_median"] < 0.60
        or report["near_camera_gravel_edge_median"] < 0.22
    ):
        raise ValueError("Root and verge probes miss native road geometry")
    if not paved and report["near_camera_damp_patch_m2"] < 2.0:
        raise ValueError("Dirt track lacks low-lying damp pockets")
    return result, report


def main(args):
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    field = load_heightfield(MASTER)
    level = load(args.level)
    roads = {
        r["id"]: np.asarray(r["centreline_m"])[:, :2] for r in load(GEOMETRY)["roads"]
    }
    trees = np.array([v["position"][:2] for v in load(TREES)["instances"]])
    capture = (
        load(CAPTURES / "cameras.json")
        | load(CAPTURES / "field-check-cameras.json")["cameras"]
    )
    inputs = [
        MASTER,
        GEOMETRY,
        TREES,
        args.level,
        CAPTURES / "cameras.json",
        CAPTURES / "field-check-cameras.json",
    ]
    existing = len(trees)
    if args.new_trees:
        inputs.append(args.new_trees)
        offsets = np.array(
            [r["position_m"][:2] for r in load(args.new_trees) if r["kind"] == "Pine"],
            dtype=float,
        ).reshape(-1, 2)
        if not np.isfinite(offsets).all():
            raise ValueError("Invalid candidate tree centre")
        trees = np.vstack((trees, offsets))
    tiles, reports = [], {}
    for tile in TILES:
        pose = capture[tile[0]]["pose"]
        packed, report = paint(
            tile,
            field,
            level,
            roads,
            trees,
            [pose[0] * 0.01, -pose[1] * 0.01],
            existing,
        )
        tiles.append(packed)
        reports[tile[0]] = report
    atlas = out / "alpine-roadbed.png"
    Image.fromarray(np.concatenate(tiles, axis=1)).save(atlas)
    for key in ("red-shoulder", "valley-ridge"):
        pose = capture[key]["pose"]
        pos = np.array([pose[0] * 0.01, -pose[1] * 0.01])
        reports[key] = {
            "camera_outside_both_authoring_tiles": all(
                max(abs(pos - np.array(tile[2]))) > SPAN / 2 for tile in TILES
            )
        }
        if not reports[key]["camera_outside_both_authoring_tiles"]:
            raise ValueError(f"{key} regression control overlaps authoring tile")
    receipt = dict(
        file=atlas.name,
        sha256=sha(atlas),
        size=[SIZE * 2, SIZE],
        tile_metres=SPAN,
        metres_per_texel=STEP,
        rasters="R coverage, G gravel, B pine litter, A wet pockets; premultiplied",
        source={p.resolve().relative_to(ROOT).as_posix(): sha(p) for p in inputs},
        heightfield_mutations=0,
        collision_mutations=0,
        cameras=reports,
    )
    (out / "roadbed.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(reports, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=OUT)
    parser.add_argument("--level", type=Path, default=DEFAULT_LEVEL)
    parser.add_argument(
        "--new-trees",
        type=Path,
        help="Structural placement JSON containing Pine instances in authored metres",
    )
    main(parser.parse_args())
