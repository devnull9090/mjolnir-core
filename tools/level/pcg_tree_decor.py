"""Turn verified UE PCG tree transforms into the shared native tree recipe input.

The same expanded tree-part transforms reach the renderer and Blam collision.
This adapter never selects, jitters, or resamples PCG points.
"""
import argparse
import json
import math
from pathlib import Path
import re
from authored_decor import PINE_SAPLING_HEIGHT, PWR_MATURE_PINE_RECIPE, complete_tree_recipe

# Shipped mesh bounds in cm, independently verified with `mjolnir mesh list`.
# expand_background_trees uses these same heights to recover exact PCG scale.
NATIVE_PINE_HEIGHTS = {"Pine_Optimized": 2150.125, "Pine_Sapling_A": PINE_SAPLING_HEIGHT}


def finite(values, length):
    return (isinstance(values, list) and len(values) == length
            and all(isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) for v in values))


def convert(source, recipes, base=None, max_trees=1000):
    if source.get("schema") != 1 or not source.get("generator") or not source.get("graph"):
        raise ValueError("Expected a versioned UE PCG selection with graph provenance")
    for key in ("source_sha256", "pcg_output_sha256"):
        if not re.fullmatch(r"[0-9a-fA-F]{64}", str(source.get(key, ""))):
            raise ValueError("Missing PCG provenance hash: " + key)
    rows = source.get("instances")
    if (not isinstance(rows, list) or source.get("selected_count") != len(rows)
            or not isinstance(source.get("input_count"), int) or source["input_count"] < len(rows)):
        raise ValueError("PCG selection counts do not match the exported instances")
    if len(rows) > max_trees:
        raise ValueError(f"PCG tree budget exceeded: {len(rows)} > {max_trees}")
    doc = json.loads(json.dumps(base)) if base else {
        "schema_version": 1, "coordinates": "unreal_centimetres", "decor": [], "background_trees": []}
    ids = {item["id"] for item in doc.get("decor", []) + doc.get("background_trees", [])}
    trees = doc.setdefault("background_trees", [])
    for row in rows:
        ident = row.get("id")
        if isinstance(ident, int) and not isinstance(ident, bool) and ident >= 0:
            ident = f"pcg_tree_{ident}"
        if not isinstance(ident, str) or not ident or ident in ids:
            raise ValueError("Duplicate or invalid PCG tree ID")
        ids.add(ident)
        if row.get("kind") != "tree" or row.get("mesh") is not None:
            raise ValueError("PCG tree recipes must not also create a duplicate mesh")
        recipe = row.get("recipe")
        measured = complete_tree_recipe(recipe,recipes) if recipe==PWR_MATURE_PINE_RECIPE else None
        if measured is None and recipe not in NATIVE_PINE_HEIGHTS and (recipe != "Lrg_A" or recipe not in recipes):
            raise ValueError("Unsupported native PCG tree recipe")
        position, position_cm = row.get("position"), row.get("position_cm")
        if not finite(position, 3) or not finite(position_cm, 3):
            raise ValueError("Invalid PCG tree coordinates")
        expected_cm = [position[0]*100, -position[1]*100, position[2]*100]
        if any(abs(a-b) > .05 for a, b in zip(expected_cm, position_cm)):
            raise ValueError("PCG metre/centimetre coordinate reflection disagrees")
        scale, yaw = row.get("scale"), row.get("yaw_degrees")
        if not finite([scale, yaw], 2) or scale <= 0:
            raise ValueError("Invalid PCG tree scale or yaw")
        if not finite(row.get("scale_xyz"), 3) or any(abs(v-scale) > 1e-5 for v in row["scale_xyz"]):
            raise ValueError("Native tree recipes require uniform PCG scale")
        height = NATIVE_PINE_HEIGHTS.get(recipe) if recipe in NATIVE_PINE_HEIGHTS else recipes[recipe].get("height")
        if not finite([height], 1) or height <= 0:
            raise ValueError("Invalid native tree recipe height")
        trees.append({"id": ident, "position_m": position, "yaw_degrees": yaw,
                      "height_m": height*scale/100, "variant": recipe})
        if measured is not None:
            doc.setdefault("complete_tree_provenance",{})[recipe] = {
                key: measured[key] for key in ("complete_mesh","min_z","height","root_z","geometry_sha256","bark_material_slots")}
    doc["pcg_provenance"] = {key: source.get(key) for key in
                             ("generator", "graph", "seed", "source_sha256", "pcg_output_sha256",
                              "input_count", "selected_count")}
    return doc


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("recipes", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--base", type=Path)
    parser.add_argument("--max-trees", type=int, default=1000)
    args = parser.parse_args()
    read = lambda p: json.loads(p.read_text(encoding="utf-8-sig"))
    doc = convert(read(args.source), read(args.recipes), read(args.base) if args.base else None, args.max_trees)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    print(f"PCG: {doc['pcg_provenance']['selected_count']} tree recipes retain generated transforms for rendering and collision")


if __name__ == "__main__":
    main()
