"""Isolated, deterministic candidate preparation for actual UE PCG forest infill.

Existing tree records are immutable. This script publishes probabilities and
clearances; the editor graph selects additions and supplies every yaw/scale.
"""
from __future__ import annotations
import argparse
import copy
import json
import math
from pathlib import Path
import sys
import numpy as np
from scipy.ndimage import distance_transform_edt
from scipy.spatial import ConvexHull, cKDTree

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "tools/level"))
sys.path.insert(0, str(ROOT / "levels/warfare/pwr"))
import b30_collision
import pcg_foliage
import pcg_tree_decor
from heightfield import load_heightfield, sha256
from world_placements import placements

OUT = ROOT / "out/pwr/visual-v5/forest-v2"
MASTER = ROOT / "levels/warfare/pwr/terrain/runtime-v5/runtime-master.json"
BASE = ROOT / "out/pwr/pcg-v5/trees.selected.json"
GRID = ROOT / "out/pwr/pcg-v5/trees.candidates.json"
ROCKS = ROOT / "out/pwr/visual-v5/outcrops-v2/rocks-and-outcrops.authored-decor.json"
HULLS = ROOT / "out/pwr/visual-v5/outcrops-v2/hulls"
PAVING = ROOT / "out/pwr/visual-v5/base-paving/footprints.geojson"
LAYOUT = ROOT / "out/pwr/world-v5/layout.json"
SEED = 20601
GAP = 7.0


def dump(path, value, compact=False):
    Path(path).write_text(json.dumps(value, separators=(",", ":") if compact else None,
                                    indent=None if compact else 2) + "\n", encoding="utf-8")


def ring_distance(points, ring):
    """Euclidean distance to a polygon boundary and even/odd containment."""
    points, ring = np.asarray(points, float), np.asarray(ring, float)
    inside = np.zeros(len(points), bool)
    distance2 = np.full(len(points), np.inf)
    for a, b in zip(ring, np.roll(ring, -1, axis=0)):
        direction = b - a
        if np.dot(direction, direction) == 0:
            continue
        t = np.clip((points - a) @ direction / np.dot(direction, direction), 0, 1)
        distance2 = np.minimum(distance2, np.sum((points - a - t[:, None] * direction)**2, axis=1))
        crossing = (a[1] > points[:, 1]) != (b[1] > points[:, 1])
        if b[1] != a[1]:
            inside ^= crossing & (points[:, 0] < (b[0]-a[0])*(points[:, 1]-a[1])/(b[1]-a[1])+a[0])
    return np.sqrt(distance2), inside


def polygon_clearance(points, rings):
    """Distance to filled polygon, preserving holes and irregular paving edges."""
    distances, outer = ring_distance(points, rings[0])
    filled = outer.copy()
    for ring in rings[1:]:
        distance, inside = ring_distance(points, ring)
        distances = np.minimum(distances, distance)
        filled &= ~inside
    return np.where(filled, 0., distances)


def spaced_candidates(xy, allowed, weights, minimum):
    """Preselect a candidate lattice with a guaranteed gap, before UE selection."""
    keep = np.zeros(len(xy), bool)
    buckets = {}
    # Prefer dense woodland candidates if lattice jitter creates a close pair.
    for i in np.lexsort((np.arange(len(xy)), -weights)):
        if not allowed[i]:
            continue
        cell = tuple(np.floor(xy[i] / minimum).astype(int))
        neighbors = [j for dx in (-1, 0, 1) for dy in (-1, 0, 1)
                     for j in buckets.get((cell[0]+dx, cell[1]+dy), [])]
        if neighbors and np.min(np.linalg.norm(xy[neighbors]-xy[i], axis=1)) < minimum:
            continue
        keep[i] = True
        buckets.setdefault(cell, []).append(i)
    return keep


def density_for_target(weights, allowed, target):
    weight = np.where(allowed, weights, 0.)
    if target > np.count_nonzero(weight) * .98:
        raise ValueError(f"Cannot fit {target} additions with retained clump headroom; "
                         f"only {np.count_nonzero(weight)} clear candidate cells")
    lo, hi = 0., 1.
    while np.minimum(weight * hi, 1.).sum() < target:
        hi *= 2
    for _ in range(55):
        mid = (lo + hi) / 2
        if np.minimum(weight * mid, 1.).sum() < target:
            lo = mid
        else:
            hi = mid
    return np.minimum(weight * ((lo+hi)/2), 1.)


def context(xy):
    """Independent clearance arrays for new points; no existing point is moved."""
    field = load_heightfield(MASTER)
    base, rocks, paving, layout = [pcg_foliage.load(p) for p in (BASE, ROCKS, PAVING, LAYOUT)]
    geometry_path = (field.path.parent / field.metadata["geometry"]).resolve()
    geometry = pcg_foliage.load(geometry_path)
    assert sha256(geometry_path) == field.metadata["geometry_sha256"]
    assert len(base["instances"]) == 2291 and len(rocks["decor"]) == 574
    pins = {str(p): sha256(p) for p in (MASTER, BASE, GRID, ROCKS, PAVING, LAYOUT, geometry_path)}
    x, y = xy.T
    delta = min(field.spacing_m) * .5
    z = field.sample(x, y)
    dx = (field.sample(x+delta, y)-field.sample(x-delta, y))/(2*delta)
    dy = (field.sample(x, y+delta)-field.sample(x, y-delta))/(2*delta)
    normal = np.c_[-dx, -dy, np.ones(len(x))]
    normal /= np.linalg.norm(normal, axis=1)[:, None]
    forbidden = ((field.masks["road"] > .002) | (field.masks["water"] > .002)
                 | (field.masks["shore"] > .02) | (field.masks["bases"] > .002))
    distances = distance_transform_edt(~forbidden, sampling=field.spacing_m[::-1])
    # Nearest-grid lookup minus a full grid diagonal is a conservative bound.
    ij = np.rint((xy-np.array(field.origin_m))/field.spacing_m).astype(int)
    corridor = distances[ij[:, 1], ij[:, 0]] - math.hypot(*field.spacing_m)
    paving_distance = np.full(len(xy), np.inf)
    for feature in paving["features"]:
        geo = feature["geometry"]
        polygons = geo["coordinates"] if geo["type"] == "MultiPolygon" else [geo["coordinates"]]
        for polygon in polygons:
            paving_distance = np.minimum(paving_distance, polygon_clearance(xy, polygon))
    rock_distance = np.full(len(xy), np.inf)
    for item in rocks["decor"]:
        path = HULLS / (item["mesh"].split(".")[-1] + ".json")
        pins[str(path)] = sha256(path)
        hull = pcg_foliage.load(path)
        world = np.array(hull["points"])*np.array(item["scale"]) @ b30_collision.rotator_matrix(*item.get("rot", [0, 0, 0])) + item["pos"]
        footprint = world[:, :2] * [0.01, -0.01]
        footprint = footprint[ConvexHull(footprint).vertices]
        rock_distance = np.minimum(rock_distance, polygon_clearance(xy, [footprint]))
    features = []
    for key, point in layout["homes_m"].items(): features.append(("home_"+key, point[:2], 60.))
    features.append(("warmup", layout["warmup_m"][:2], 40.))
    for i, point in enumerate(layout["captures_m"]): features.append((f"capture_{i}", point[:2], 45.))
    for i, vehicle in enumerate(placements(layout, geometry, field)["vehicles"]):
        features.append((f"vehicle_{i}", vehicle["position_m"][:2], 24.))
    # Both teams' observed manual/automatic insertion endpoints, mirrored in Y.
    for xval in (-755.534, -602.841, 602.841, 755.534):
        for yval in (-179.287, 179.287):
            features.append((f"insertion_{xval}_{yval}", [xval, yval], 35.))
    feature_distance = np.full(len(xy), np.inf)
    for _, point, radius in features:
        feature_distance = np.minimum(feature_distance, np.linalg.norm(xy-point, axis=1)-radius)
    existing = np.array([row["position"][:2] for row in base["instances"]])
    existing_distance = cKDTree(existing).query(xy)[0]
    forest = field.sample_mask("forest", x, y)
    woodland = .5 + .25*np.sin(x/177+.7*np.sin(y/113)) + .25*np.cos(y/149+.7*np.sin(x/121))
    patch = np.clip((woodland-.28)/.62, 0, 1)
    weights = forest * (.08+.92*patch*patch*(3-2*patch))
    tests = {"playable_inset": np.max(np.abs(xy), axis=1) <= 935,
             "forest_biome": forest > .08, "slope": normal[:, 2] >= .85,
             "road_water_shore_base_collar_8m": corridor >= 8.,
             "extended_paving_collar_8m": paving_distance >= 8.,
             "all574_native_rock_footprints_collar_4m": rock_distance >= 4.,
             "gameplay_clearance_discs": feature_distance >= 0.,
             "existing_trunk_gap_7m": existing_distance >= GAP}
    arrays = {"corridor_m": corridor, "paving_m": paving_distance, "rock_m": rock_distance,
              "gameplay_disc_margin_m": feature_distance, "existing_trunk_m": existing_distance,
              "normal_z": normal[:, 2], "forest": forest, "clump_weight": weights}
    return field, base, pins, z, normal, weights, tests, arrays, features


def prepare(target=2000):
    OUT.mkdir(parents=True, exist_ok=True)
    original = pcg_foliage.load(GRID)
    xy = np.array([row["position"][:2] for row in original["points"]])
    field, base, pins, z, normal, weights, tests, arrays, features = context(xy)
    ids = np.array([row["id"] for row in original["points"]])
    selected_ids = {row["id"] for row in base["instances"]}
    indexed_original = {row["id"]: row for row in original["points"]}
    if len(indexed_original) != len(original["points"]):
        raise ValueError("Original candidate grid has duplicate IDs")
    for row in base["instances"]:
        if row["id"] not in indexed_original or row["position"][:2] != indexed_original[row["id"]]["position"][:2]:
            raise ValueError("Preserved tree no longer matches its original candidate cell")
    tests["unselected_original_cell"] = np.array([pid not in selected_ids for pid in ids])
    allowed = np.logical_and.reduce(list(tests.values()))
    before_gap = int(allowed.sum())
    allowed = spaced_candidates(xy, allowed, weights, GAP)
    density = density_for_target(weights, allowed, target)
    points = [{"id": int(ids[i]), "position": [float(xy[i, 0]), float(xy[i, 1]), round(float(z[i]), 6)],
               "normal": [round(float(v), 8) for v in normal[i]], "density": round(float(density[i]), 8),
               "biome_mask": int(allowed[i]), "kind": "tree", "biome": "woodland"} for i in range(len(xy))]
    source = OUT / "infill.candidates.json"
    dump(source, {"schema": 1, "align_to_normal": False, "master_sha256": field.manifest_sha256,
         "height_sha256": field.metadata["height"]["sha256"], "base_selection_sha256": sha256(BASE),
         "original_candidate_grid_sha256": sha256(GRID), "points": points}, True)
    dump(OUT/"palette.json", {"kinds": {"tree": {"recipes": [
        {"recipe": "Pine_Optimized", "weight": .88}, {"recipe": "Pine_Sapling_A", "weight": .12}]}}})
    dump(OUT/"request.json", {"jobs": [{"input": str(source), "output": str(OUT/f"infill{suffix}.pcg.json"),
         "graph": "/Game/MJOLNIR/PCGAuthoring/PWRForestV2/PCG_infill"+suffix,
         "seed": SEED, "scale_min": .7, "scale_max": 1.3} for suffix in ("", "_repeat")]})
    receipt = {"schema": "pwr-forest-infill-input-v1", "pins": pins, "existing_count": len(base["instances"]),
         "candidate_count": len(points), "allowed_before_new_gap": before_gap, "allowed": int(allowed.sum()),
         "excluded_per_independent_gate": {k: int((~v).sum()) for k,v in tests.items()},
         "expected_additions": float(density.sum()), "maximum_combined": 4600,
         "minimum_new_trunk_gap_m": GAP, "clearance_discs": features,
         "source_sha256": sha256(source), "palette_sha256": sha256(OUT/"palette.json"),
         "clump_policy": "Same continuous woodland field as original; probability rescaled only after all exclusions",
         "density_saturated_candidates": int((density >= .999999).sum()),
         "baseline_scope": "Existing 2291 records remain byte-equivalent JSON values; clearance tests constrain additions"}
    dump(OUT/"inputs.receipt.json", receipt)
    print(json.dumps({k: receipt[k] for k in ("existing_count", "allowed_before_new_gap", "allowed", "expected_additions", "density_saturated_candidates")}))
    return receipt


def export():
    receipt = pcg_foliage.load(OUT/"inputs.receipt.json")
    for path, expected in receipt["pins"].items():
        if sha256(path) != expected: raise ValueError("Input changed after candidate preparation: "+path)
    source, first, repeat = (OUT/"infill.candidates.json", OUT/"infill.pcg.json", OUT/"infill_repeat.pcg.json")
    assert sha256(source) == receipt["source_sha256"]
    assert sha256(OUT/"palette.json") == receipt["palette_sha256"]
    comparison = pcg_foliage.compare(source, first, repeat)
    additions = pcg_foliage.adapt(source, first, OUT/"palette.json", OUT, "infill")
    xy = np.array([row["position"][:2] for row in additions["instances"]])
    field, base, pins, z, normals, weights, tests, arrays, _ = context(xy)
    if not all(np.all(test) for test in tests.values()): raise ValueError("Independent final clearance check failed")
    if len(xy) > 1 and cKDTree(xy).query(xy, k=2)[0][:, 1].min() < GAP:
        raise ValueError("Generated additions violate minimum trunk spacing")
    existing_ids = {row["id"] for row in base["instances"]}
    assert not existing_ids.intersection(row["id"] for row in additions["instances"])
    assert max(abs(row["position"][2]-height) for row, height in zip(additions["instances"], z)) < 1e-5
    combined = copy.deepcopy(additions)
    combined["instances"] = copy.deepcopy(base["instances"]) + additions["instances"]
    combined["selected_count"] = len(combined["instances"])
    assert 2291 < combined["selected_count"] <= 4600
    combined["generator"] += " / immutable prior PCG selection + independently generated infill"
    combined["composition"] = {"schema": "pwr-pcg-selection-union-v1", "base": str(BASE),
         "base_sha256": sha256(BASE), "base_count": 2291, "base_prefix_exact": True,
         "infill": str(OUT/"infill.selected.json"), "infill_sha256": sha256(OUT/"infill.selected.json"),
         "infill_count": additions["selected_count"], "request_receipt_sha256": sha256(OUT/"request.receipt.json"),
         "repeat_sha256": sha256(repeat), "input_receipt_sha256": sha256(OUT/"inputs.receipt.json")}
    pcg_tree_decor.convert(combined, {}, max_trees=4600)
    dump(OUT/"trees.selected.json", combined, True)
    written = pcg_foliage.load(OUT/"trees.selected.json")
    assert written["instances"][:2291] == base["instances"]
    tops = [row["position"][2]+pcg_tree_decor.NATIVE_PINE_HEIGHTS[row["recipe"]]*row["scale"]/100
            for row in written["instances"]]
    assert max(tops) < 500, "Tree crowns encroach on reserved 550 m flight corridor"
    report = {"schema": "pwr-forest-infill-audit-v1", "pins": pins, "determinism": comparison,
         "base_prefix_exact": True, "existing_count": 2291, "added_count": len(xy),
         "combined_count": len(written["instances"]), "combined_sha256": sha256(OUT/"trees.selected.json"),
         "new_selected_minimum": {k: float(v.min()) for k,v in arrays.items()},
         "new_to_new_minimum_m": float(cKDTree(xy).query(xy, k=2)[0][:, 1].min()),
         "maximum_tree_top_m": max(tops), "minimum_flight_vertical_clearance_m": 550-max(tops),
         "native_recipe_counts": {key: sum(row["recipe"] == key for row in written["instances"])
                                   for key in pcg_tree_decor.NATIVE_PINE_HEIGHTS},
         "scope": "Offline additions and preserved baseline only; no installation, live collision, render performance or remote-peer claim"}
    dump(OUT/"clearance.receipt.json", report)
    overview(field, base["instances"], additions["instances"])
    print(json.dumps({k:report[k] for k in ("existing_count", "added_count", "combined_count", "new_to_new_minimum_m", "maximum_tree_top_m")}))
    return report


def overview(field, old, new):
    from PIL import Image, ImageDraw
    h = field.heights_m
    shade = np.clip(70+(h-h.min())/(h.max()-h.min())*100, 0, 255).astype(np.uint8)
    rgb = np.stack((shade, shade, shade), axis=-1)[::-1]
    im = Image.fromarray(rgb).resize((1200, 1200))
    draw = ImageDraw.Draw(im)
    for rows, color, radius in ((old, (51, 108, 65), 2), (new, (80, 235, 110), 3)):
        for row in rows:
            x, y = row["position"][:2]; u, v = (x+1000)*.6, (1000-y)*.6
            draw.ellipse((u-radius, v-radius, u+radius, v+radius), fill=color)
    draw.rectangle((10, 10, 520, 60), fill=(20, 25, 20))
    draw.text((20, 20), f"Existing {len(old)} dark green; actual UE PCG additions {len(new)} bright green", fill="white")
    draw.text((20, 40), "2 km square; north up; road/water/base/paving/rock clearances retained", fill="white")
    im.save(OUT/"forest-overview.png")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("prepare", "export"))
    parser.add_argument("--target", type=int, default=2000)
    args = parser.parse_args()
    prepare(args.target) if args.command == "prepare" else export()
