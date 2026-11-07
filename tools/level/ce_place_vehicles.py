#!/usr/bin/env python3
"""Move a converted CE map's vehicles from where CE parks them to where its
script takes them, and ship the containers of any custom vehicle with the map.

    ce_place_vehicles.py <base level> <runtime level> <plan.json> <out dir>
        --map <map> --tags <staging tags.json> --collision <collision_scene.bin>
        --name <map name> [--paks ...] [--sounds vehicle_sounds.json]

A CE map can park its vehicles out of reach and teleport them out by script
(Yoyorast's vehicletrigger). A converted vehicle has no such script: it spawns,
and comes back, at its placement. So the placement moves to the flag, standing
on the collision under it.

A level's `blam.vehicles` and `vehicle_sets` keep the scenario's order, which
names them. The plan (tools/level/data/yoy_vehicles.json) says where each goes
and what is dropped; a vehicle it leaves out stays put. Its `tag` makes a
placement a custom vehicle, and its `label` replaces the vehicle set label, so
vehicles that always go together can share one when a map has more than a
variant's 16 filters hold. Spawn data stays as it was.

Writes to <out dir>: <name>.level.json (runtime, what `map pack` takes), the
containers the plan renames with their stub .pak, read from Paks so they hold
the tested bytes, and vehicle_sounds.json. The base level goes to <out dir>/build
with its script beside it. Then, from <out dir>/build:

    mjolnir level bake <base level> --standalone <CODE> --bsp 8=<sbsp> --world <umap> --out-dir ..

`map pack` needs a name ending in -<CODE>_P, and a file's name can differ from
its contents: the launcher renames every container anyway. The renames keep each
chunk number, so one with a shader library would keep its shaders.
"""
import argparse
import json
import math
import os
import shutil
import struct
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "ce_scripts"))
import ce_scenario  # noqa: E402

CM = 304.8
# A vehicle starts this far over the ground at least (gen_ce_level.py
# VEHICLE_LIFT_DEFAULT).
LIFT = 0.05
# A flag further than this over the ground is over something else.
MAX_DROP = 1.0
# The same spot, in cm, allowing for rounding.
SAME_SPOT = 2.0
LABEL = "multiplayer data.megalo label"


def load_triangles(path):
    """A `collision_scene.bin`: each array, a u32 count and its elements."""
    data, at, arrays = open(path, "rb").read(), 0, []
    for _, size in ce_scenario.BSP_ARRAYS:
        count = struct.unpack_from("<I", data, at)[0]
        arrays.append((count, data[at + 4:at + 4 + count * size]))
        at += 4 + count * size
    return np.array(ce_scenario.triangles({"arrays": arrays}))


def heights(tri, x, y):
    """Every surface straight above or below (x, y), in wu."""
    a, b, c = tri[:, 0], tri[:, 1], tri[:, 2]
    d = (b[:, 1] - c[:, 1]) * (a[:, 0] - c[:, 0]) + (c[:, 0] - b[:, 0]) * (a[:, 1] - c[:, 1])
    flat = np.abs(d) < 1e-9
    d = np.where(flat, 1, d)
    u = ((b[:, 1] - c[:, 1]) * (x - c[:, 0]) + (c[:, 0] - b[:, 0]) * (y - c[:, 1])) / d
    v = ((c[:, 1] - a[:, 1]) * (x - c[:, 0]) + (a[:, 0] - c[:, 0]) * (y - c[:, 1])) / d
    w = 1 - u - v
    inside = ~flat & (u >= -1e-5) & (v >= -1e-5) & (w >= -1e-5)
    return sorted((u * a[:, 2] + v * b[:, 2] + w * c[:, 2])[inside].tolist())


def ground_under(surfaces, z):
    """The surface a thing at height z stands on, or None."""
    below = [s for s in surfaces if s <= z + LIFT]
    return below[-1] if below and z - below[-1] <= MAX_DROP else None


def to_ue(p):
    return [round(p[0] * CM, 1), round(-p[1] * CM, 1), round(p[2] * CM, 1)]


def placed(flag, ground):
    """A flag's spot as a placement: its position and yaw, off the ground."""
    x, y, z = flag["position"]
    return {"pos": to_ue([x, y, max(z, ground + LIFT)]), "yaw": round(-math.degrees(flag["facing"][0]), 1) + 0.0}


def apply_plan(vehicles, sets, rows, flags, plan, surfaces):
    """The kept vehicles and their set rows, and a line for each of `rows`.
    `rows` are the scenario's, in order: name, tag, position in wu."""
    if not len(vehicles) == len(sets) == len(rows):
        sys.exit(f"{len(vehicles)} vehicles, {len(sets)} set rows, {len(rows)} in the scenario")
    kept, kept_sets, report = [], [], []
    for vehicle, row_set, row in zip(vehicles, sets, rows):
        at = to_ue(row["position"])
        if max(abs(at[k] - vehicle["pos"][k]) for k in range(2)) > SAME_SPOT:
            sys.exit(f"{row['name']} is at {at} in the scenario, {vehicle['pos']} in the level: not this level's order")
        name = row["name"] or "(unnamed)"
        was = [round(v, 2) for v in row["position"]]
        if row["tag"] in plan["drop_tags"] or row["name"] in plan["drop_names"]:
            report.append(f"{name} {row['tag']} {was} -> dropped")
            continue
        move = plan["moves"].get(row["name"])
        vehicle = dict(vehicle)
        if move:
            flag = flags[move["flag"]]
            ground = ground_under(surfaces(*flag["position"][:2]), flag["position"][2])
            if ground is None:
                sys.exit(f"no ground under flag {move['flag']}")
            vehicle.update(placed(flag, ground))
            if "tag" in move:
                vehicle["tag"] = move["tag"]
            if "label" in move:
                vehicle["set"] = {**vehicle["set"], LABEL: move["label"]}
                row_set = {**row_set, "label": move["label"]}
            report.append(f"{name} {row['tag']} {was} -> {move['flag']} "
                          f"{[round(v / CM, 2) for v in vehicle['pos']]} yaw {vehicle['yaw']} "
                          f"ground {ground:.2f}{' as ' + move['tag'] if 'tag' in move else ''}")
        else:
            report.append(f"{name} {row['tag']} {was} stays")
        kept.append(vehicle)
        kept_sets.append(row_set)
    return kept, kept_sets, report


def relabel(level, rows, plan):
    """The plan's labels on a level already placed, as a published pack's is:
    its vehicles keep the scenario's order, less what the plan dropped. Stops if
    a custom vehicle is not where the plan says, which means another order."""
    named = [r for r in rows if r["tag"] not in plan["drop_tags"] and r["name"] not in plan["drop_names"]]
    vehicles, sets = level["blam"]["vehicles"], level["vehicle_sets"]
    if not len(vehicles) == len(sets) == len(named):
        sys.exit(f"{len(vehicles)} vehicles, {len(sets)} set rows, {len(named)} kept in the scenario")
    for vehicle, row_set, row in zip(vehicles, sets, named):
        move = plan["moves"].get(row["name"], {})
        if move.get("tag") != vehicle.get("tag"):
            sys.exit(f"{row['name']} is {vehicle.get('tag')} in the level: not this level's order")
        if "label" in move:
            vehicle["set"][LABEL] = move["label"]
            row_set["label"] = move["label"]
    return level


def scenario_rows(s):
    names, palette, rows = s.names(), s.palette(0x24C), []
    for at in s.block(s.s, 0x240, 120):
        n = s.i16(at + 2)
        rows.append({"name": names[n] if 0 <= n < len(names) else None,
                     "tag": s.path_of(palette[s.i16(at)]), "position": s.f(at + 8, 3)})
    return rows


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    for name in ("base", "runtime", "plan", "out"):
        ap.add_argument(name)
    ap.add_argument("--map", required=True)
    ap.add_argument("--tags", required=True)
    ap.add_argument("--collision", required=True)
    ap.add_argument("--name", required=True, help="the map's level file name, as yoyorast_island_v2")
    ap.add_argument("--paks", default=os.environ.get("HCE_PAKS"))
    ap.add_argument("--sounds", help="vehicle_sounds.json, for the level's folder")
    a = ap.parse_args()

    plan = json.load(open(a.plan, encoding="utf-8"))
    s = ce_scenario.Scenario(a.map, a.tags)
    rows = scenario_rows(s)
    flags = {f["name"]: f for f in s.cutscene_flags()}
    tri = load_triangles(a.collision)
    build = os.path.join(a.out, "build")
    os.makedirs(build, exist_ok=True)

    report = []
    for src, dst in ((a.base, os.path.join(build, os.path.basename(a.base))),
                     (a.runtime, os.path.join(a.out, a.name + ".level.json"))):
        level = json.load(open(src, encoding="utf-8"))
        level["blam"]["vehicles"], level["vehicle_sets"], report = apply_plan(
            level["blam"]["vehicles"], level["vehicle_sets"], rows, flags, plan,
            lambda x, y: heights(tri, x, y))
        with open(dst, "w", encoding="utf-8") as stream:
            json.dump(level, stream, indent=1)
    print("\n".join(report))

    script = json.load(open(a.base, encoding="utf-8"))["blam"].get("script")
    if script:
        shutil.copyfile(os.path.join(os.path.dirname(a.base), script), os.path.join(build, script))
    for old, new in plan.get("containers", {}).items():
        for ext in ("utoc", "ucas", "pak"):
            shutil.copyfile(os.path.join(a.paks, f"{old}.{ext}"), os.path.join(a.out, f"{new}.{ext}"))
    if a.sounds:
        shutil.copyfile(a.sounds, os.path.join(a.out, "vehicle_sounds.json"))


if __name__ == "__main__":
    main()
