"""Halo 2's instanced geometry as scenery the swap can read.

    python tools/level/instance_scenery.py <staging> <out dir> <shader token>=<rule> [...]

A Halo 2 level's trees and boulders are often instanced geometry: pieces of
the BSP, not scenery, so the conversion draws them into the terrain mesh and
`placement.json` never names them. scenery_swap.py swaps what
`placement.json` names. This writes, from the staging's `bsp/instances.json`
(`mjolnir cache stage`), a second staging folder holding only those
instances as scenery entries:

    <out dir>/placement.json    entries of kind scenery, one an instance
    <out dir>/models/*.gltf     a stub a model: its shaders and its bounds

An instance is taken when one of its shaders' names holds a token; its
entry's asset is `instances\\<rule>\\<name>`, so the rule (a key of
scenery_swap.RULES: `tree_pine`, `boulder`, ...) picks what stands in for
it. The stub carries the instance's own size (its world bounds about its
origin): the swap sizes a tree to the model's height, and an instance has a
scale where scenery has none. upgrade_ce_map.py's swap stage runs this for a
map with `instance_swap` and hands the folder to the swap as its staging.
"""
import json
import math
import os
import sys

WU_M = 3.048


def main():
    if len(sys.argv) < 4:
        sys.exit(__doc__)
    staging, out = sys.argv[1], sys.argv[2]
    rules = [a.split("=", 1) for a in sys.argv[3:]]
    listing = os.path.join(staging, "bsp", "instances.json")
    if not os.path.exists(listing):
        sys.exit(f"{listing} is missing: stage the map again with a current `mjolnir cache stage`")
    doc = json.load(open(listing, encoding="utf-8"))
    os.makedirs(os.path.join(out, "models"), exist_ok=True)
    entries, taken = [], {}
    for inst in doc["instances"]:
        shaders = [s.lower() for s in inst["shaders"]]
        rule = next((r for token, r in rules if any(token.lower() in s for s in shaders)), None)
        if not rule:
            continue
        pos, lo, hi = inst["pos"], inst["min"], inst["max"]
        # glTF metres, y up, about the instance's origin (scenery_swap.model_box
        # reads the accessor's min and max, nothing else of the mesh).
        gmin = [(lo[0] - pos[0]) * WU_M, (lo[2] - pos[2]) * WU_M, -(hi[1] - pos[1]) * WU_M]
        gmax = [(hi[0] - pos[0]) * WU_M, (hi[2] - pos[2]) * WU_M, -(lo[1] - pos[1]) * WU_M]
        model = f"models/instance_{inst['index']}.gltf"
        json.dump({"asset": {"version": "2.0", "generator": "instance_scenery.py"},
                   "materials": [{"name": s} for s in inst["shaders"]],
                   "meshes": [{"primitives": [{"attributes": {"POSITION": 0}}]}],
                   "accessors": [{"min": gmin, "max": gmax}]},
                  open(os.path.join(out, model), "w", encoding="utf-8"))
        f = inst["forward"]
        entries.append({"kind": "scenery", "asset": f"instances\\{rule}\\{inst.get('name') or inst['index']}",
                        "model": model, "pos": pos, "rot": [math.atan2(f[1], f[0]), 0.0, 0.0],
                        "instance": inst["index"]})
        taken[rule] = taken.get(rule, 0) + 1
    json.dump({"world_unit_meters": WU_M, "rotation_convention": "halo_yaw_pitch_roll_radians", "entries": entries},
              open(os.path.join(out, "placement.json"), "w", encoding="utf-8"), indent=1)
    print(f"{len(entries)} instance(s) as scenery {taken} -> {out}")


if __name__ == "__main__":
    main()
