"""Separate native glacial boulder PCG pass on the exact runtime terrain.

Prepare candidates, run the real editor graph, then export native decor.
Visual actors and native hulls consume the same root-adjusted transform.
"""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np

from heightfield import load_heightfield
import pcg_foliage


def object_path(path):
    return path if "." in path else path + "." + path.rsplit("/", 1)[-1]


def prepare(master, catalogue, trees, out, target=300):
    field = load_heightfield(master)
    out = Path(out); out.mkdir(parents=True, exist_ok=True)
    assets = json.loads(Path(catalogue).read_text())["glacial_rocks"]
    if len(assets) != 6:
        raise ValueError("Expected the six verified native glacial rock assets")
    lo, hi = field.bounds_m
    nx, ny = [int((hi[i] - lo[i] - 100) // 20) for i in range(2)]
    c, r = np.meshgrid(np.arange(nx), np.arange(ny))
    x = lo[0] + 50 + (c + .5) * 20 + 6 * np.sin(c * 2.399 + r * 1.113)
    y = lo[1] + 50 + (r + .5) * 20 + 6 * np.sin(r * 2.173 + c * 1.719)
    x, y = x.ravel(), y.ravel(); z = field.sample(x, y)
    dx = (field.sample(x + 2, y) - field.sample(x - 2, y)) / 4
    dy = (field.sample(x, y + 2) - field.sample(x, y - 2)) / 4
    slope = np.hypot(dx, dy)
    allowed = (slope > .045) & (slope < .45) & (z > 100)
    # Verify the full possible boulder footprint plus clearance, not only its
    # pivot. Large-C's widest native footprint is about21m before scale.
    for theta in np.linspace(0, np.pi * 2, 17)[:-1]:
        xx, yy = x + 17 * np.cos(theta), y + 17 * np.sin(theta)
        allowed &= ((field.sample_mask("road", xx, yy) < .005)
                    & (field.sample_mask("water", xx, yy) < .005)
                    & (field.sample_mask("shore", xx, yy) < .1)
                    & (field.sample_mask("bases", xx, yy) < .005))
    selected_trees = json.loads(Path(trees).read_text())["instances"]
    tree_xy = np.asarray([t["position"][:2] for t in selected_trees])
    for start in range(0, len(x), 256):
        points = np.c_[x[start:start + 256], y[start:start + 256]]
        closest = np.min(np.sum((points[:, None] - tree_xy[None]) ** 2, axis=2), axis=1)
        allowed[start:start + 256] &= closest >= 17 ** 2
    patch = .55 + .25 * np.sin(x / 137 + np.sin(y / 83)) + .2 * np.cos(y / 111)
    density = np.where(allowed, np.clip(slope / .3, .1, 1) * patch, 0)
    low, high = 0.0, 100.0
    expected = min(target, int(allowed.sum()) * .98)
    for _ in range(48):
        factor = (low + high) / 2
        if np.minimum(density * factor, 1).sum() < expected:
            low = factor
        else:
            high = factor
    density = np.minimum(density * ((low + high) / 2), 1)
    points = [{"id": i, "position": [round(float(x[i]), 6), round(float(y[i]), 6), round(float(z[i]), 6)],
               "normal": [0, 0, 1], "density": round(float(density[i]), 6), "biome_mask": int(allowed[i]),
               "kind": "rock", "biome": "mountain_foot"} for i in range(len(x))]
    candidate = out / "rocks.candidates.json"
    candidate.write_text(json.dumps({"schema": 1, "align_to_normal": False,
        "master_sha256": field.manifest_sha256, "height_sha256": field.metadata["height"]["sha256"],
        "points": points}, separators=(",", ":")))
    palette = {"kinds": {"rock": {"meshes": [object_path(a["mesh"]) for a in assets],
               "rule": "stones", "shadow": True, "static": True, "cull": [30000, 90000]}}}
    (out / "palette.json").write_text(json.dumps(palette, indent=2))
    jobs = [{"input": str(candidate.resolve()), "output": str((out / f"rocks{suffix}.pcg.json").resolve()),
             "graph": f"/Game/MJOLNIR/PCGAuthoring/PWR/PCG_rocks{suffix}", "seed": 20571,
             "scale_min": .65, "scale_max": 1.15} for suffix in ("", "_repeat")]
    (out / "request.json").write_text(json.dumps({"jobs": jobs}, indent=2))
    receipt = {"master_sha256": field.manifest_sha256, "candidates": len(points),
               "allowed": int(allowed.sum()), "expected": round(float(density.sum()), 3),
               "source_sha256": pcg_foliage.digest(candidate), "tree_clearance_m": 17,
               "footprint_exclusion_radius_m": 17, "render_path": "native static decor actors"}
    (out / "inputs.receipt.json").write_text(json.dumps(receipt, indent=2))
    return receipt


def export(source_path, generated_path, catalogue, out):
    source, generated = pcg_foliage.load(source_path), pcg_foliage.load(generated_path)
    if generated.get("source_sha256") != pcg_foliage.digest(source_path):
        raise ValueError("Rock candidate source changed since PCG generation")
    assets = json.loads(Path(catalogue).read_text())["glacial_rocks"]
    pairs = pcg_foliage.validate_output(source, generated)
    if len(pairs) > 400:
        raise ValueError("Rock PCG budget exceeded400")
    decor, transforms = [], []
    for original, point in pairs:
        asset = assets[min(len(assets) - 1, int(point["asset_draw"] * len(assets)))]
        scale = point["scale_xyz"][0]
        if max(point["scale_xyz"]) - min(point["scale_xyz"]) > 1e-6:
            raise ValueError("Native boulder recipe requires uniform PCG scale")
        bottom = asset["bounds_cm"]["min"][2]
        height = asset["bounds_cm"]["max"][2] - bottom
        position = list(point["position_cm"])
        position[2] += (-bottom - .20 * height) * scale
        item = {"id": f"pcg_rock_{original['id']}", "mesh": object_path(asset["mesh"]), "pos": position,
                "rot": [0, -pcg_foliage.authored_yaw(point["rotation_xyzw"]), 0],
                "scale": point["scale_xyz"], "static": True}
        decor.append(item)
        transforms.append({"id": item["id"], "support_position_m": original["position"],
                           "actor_position_cm": position, "root_offset_cm": (-bottom - .20 * height) * scale,
                           "mesh": item["mesh"], "scale": scale})
    document = {"schema_version": 1, "coordinates": "unreal_centimetres", "decor": decor,
                "background_trees": [], "pcg_provenance": {
                    "generator": generated["generator"], "graph": generated["graph"], "seed": generated["seed"],
                    "source_sha256": pcg_foliage.digest(source_path), "pcg_output_sha256": pcg_foliage.digest(generated_path)}}
    out = Path(out); out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(document, indent=2))
    receipt = {"selected_count": len(decor), "native_hull_source": "same authored_decor records become swap.decor",
               "cladding_reach_lookup": False, "duplicate_MJF_meshes": False, "instances": transforms}
    out.with_suffix(".receipt.json").write_text(json.dumps(receipt, indent=2))
    return {"count": len(decor), "authored_decor": str(out)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    prepare_parser = sub.add_parser("prepare")
    prepare_parser.add_argument("master"); prepare_parser.add_argument("catalogue")
    prepare_parser.add_argument("trees"); prepare_parser.add_argument("out")
    prepare_parser.add_argument("--target", type=int, default=300)
    export_parser = sub.add_parser("export")
    export_parser.add_argument("source"); export_parser.add_argument("generated")
    export_parser.add_argument("catalogue"); export_parser.add_argument("out")
    args = parser.parse_args()
    if args.command == "prepare":
        print(json.dumps(prepare(args.master, args.catalogue, args.trees, args.out, args.target)))
    else:
        print(json.dumps(export(args.source, args.generated, args.catalogue, args.out)))
