#!/usr/bin/env python3
"""Roadworks Circuit: connector-driven road assembly in metres, Z-up.

This separate generator never rewrites Forge Canvas or Crossline. Road origins
and endpoint tangents come from the authored pack, including reversed ramps.
"""
import importlib.util
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent
spec = importlib.util.spec_from_file_location("forge_maps_common", ROOT / "generate.py")
common = importlib.util.module_from_spec(spec)
spec.loader.exec_module(common)


def rotate(point, yaw):
    angle = math.radians(yaw)
    c, s = math.cos(angle), math.sin(angle)
    return [point[0] * c - point[1] * s, point[0] * s + point[1] * c, point[2]]


def add(a, b):
    return [x + y for x, y in zip(a, b)]


def clean(values):
    return [round(v, 9) for v in values]


def place(level, block, origin, yaw):
    index = len(level["blam"]["objects"])
    level["blam"]["objects"].append({"group": "crates", "tag": block["tag"],
        "pos": common.ue(origin), "rot": [0, round(-yaw, 9), 0],
        "set": {"multiplayer data.owner team": "neutral"}})
    return index


def connected(level, block, position, forward, reverse=False):
    """Align an entry connector to a world-space position and flow tangent."""
    connectors = block["road"]["connectors"]
    start, end = (connectors[1], connectors[0]) if reverse else connectors
    direction = [-v for v in start["forward"]] if reverse else start["forward"]
    yaw = math.degrees(math.atan2(forward[1], forward[0]) - math.atan2(direction[1], direction[0]))
    origin = clean(add(position, [-v for v in rotate(start["position_m"], yaw)]))
    index = place(level, block, origin, yaw)
    endpoint = clean(add(origin, rotate(end["position_m"], yaw)))
    tangent = clean(rotate([-v for v in end["forward"]] if reverse else end["forward"], yaw))
    return endpoint, tangent, {"id": block["id"], "object_index": index, "reverse": reverse}


def barrier(level, axis, coordinate, start, end):
    """Continuous solid 4m half-walls; partial end spans overlap safely."""
    length = end - start
    count = math.ceil(length / 4)
    centres = [(start + end) / 2] if count == 1 else [
        start + 2 + i * (length - 4) / (count - 1) for i in range(count)]
    for value in centres:
        point = (coordinate, value, 3) if axis == "x" else (value, coordinate, 3)
        common.piece(level, "wall_half", point, 90 if axis == "x" else 0)


def circuit():
    catalog = json.loads((REPO / "forge-packs/roadworks/catalog.json").read_text())
    blocks = {b["id"]: b for b in catalog["forge_pack"]["blocks"]}
    level = common.base("roadworks_circuit", "Roadworks Circuit", 160, 160, ["slayer", "forge"])
    level["description"] = (
        "A Warthog test circuit with 8 m lanes, 12/24 m straights, R20 curves, a gradual 4 m climb "
        "and a connected vehicle test pad. Guarded roads stand 3 m above a 160 m recovery deck.")
    level["blam"]["world_bounds"] = [{"bsp": 8,
        "min": [-96 / 3.048, -96 / 3.048, -8 / 3.048],
        "max": [96 / 3.048, 96 / 3.048, 64 / 3.048]}]
    level["blam"]["forge_packs"].append({"slug": "roadworks", "version": catalog["version"],
        "blocks": [{"id": b["id"], "tag": b["tag"]} for b in blocks.values()]})
    # Keep the recovery floor visually distinct from the actual road surface.
    level["decor"][0]["tint"] = [.095, .12, .135, 1]
    common.grid(level, 160, 160, 8)
    position, forward = [44, -36, 3], [0, 1, 0]
    sequence = [
        ("straight_24_guarded", False), ("straight_24", False),
        ("straight_12_guarded", False), ("straight_12_guarded", False),
        ("curve_90_guarded", False),
        ("straight_24_guarded", False), ("straight_24_guarded", False),
        ("curve_45_guarded", False), ("curve_45_guarded", False),
        ("straight_12_guarded", False), ("ramp_24_guarded", False),
        ("straight_12_guarded", False), ("ramp_24_guarded", True),
        ("curve_90_guarded", False),
        ("straight_24_guarded", False), ("straight_24_guarded", False),
        ("curve_45_guarded", False), ("curve_45_guarded", False),
    ]
    loop = []
    for ident, reverse in sequence:
        position, forward, record = connected(level, blocks[ident], position, forward, reverse)
        loop.append(record)
    if math.dist(position, [44, -36, 3]) > 0.00001 or math.dist(forward, [0, 1, 0]) > 0.00001:
        raise ValueError("Road connector changes left the circuit open")
    # The bare segment's inner side opens onto a perpendicular, guarded spur.
    # The spur ends exactly at the pit's right edge: no raised deck lips.
    _, _, spur = connected(level, blocks["straight_24_guarded"], [39.6, 0, 3], [-1, 0, 0])
    pad = [place(level, blocks["straight_24"], (x, -12, 2.5), 0) for x in (-6.4, 2.4, 11.2)]
    barrier(level, "x", 48.25, -12, 12)
    for lo, hi in [(-12, -4.4), (4.4, 12)]:
        barrier(level, "x", 39.75, lo, hi)
    barrier(level, "x", -10.55, -12, 12)
    for y in (-11.75, 11.75):
        barrier(level, "y", y, -10.8, 15.6)
    for lo, hi in [(-12, -4.4), (4.4, 12)]:
        barrier(level, "x", 15.35, lo, hi)
    # Vehicle origins sit above the road so the native suspension settles.
    # Positive source Y corresponds to UE yaw -90, because vehicle forward is X.
    level["blam"]["vehicles"] = [
        {"type": "warthog", "pos": common.ue((2.4, -3, 3.8)), "yaw": -90},
        {"type": "warthog", "pos": common.ue((-44, 30, 3.8)), "yaw": 90},
    ]
    # The first live Spartan is beside the pit Warthog for an honest scale view.
    for x, y, yaw in [(-1.4, -3, 0), (-5, 2, 0), (6, 6, 180), (10, -7, 90)]:
        common.spawn(level, (x, y, 3.35), yaw)
    for x, y in [(-8, -9), (-8, 9), (13, -9), (13, 9)]:
        common.piece(level, "light_pylon", (x, y, 3))
    # Flush paint forms a start stripe and a two-metre scale bar on the pit.
    common.cube(level, "start_line", (44, -18, 3.012), (7.8, .18, .012), [.94, .94, .88, 1])
    common.cube(level, "scale_2m", (-3.3, -3, 3.012), (.08, 2, .012), [1, .55, .06, 1])
    for y in (-4, -3, -2):
        common.cube(level, "scale_tick_" + str(y), (-3.3, y, 3.012), (.4, .06, .012), [1, .55, .06, 1])
    common.validate(level)
    layout = {"schema_version": 1, "units": "metres_z_up", "surface_m": 3,
              "loop": loop, "spur": spur, "pad_object_indices": pad,
              "lap_plan_length_m": 240 + 40 * math.pi}
    return level, layout


def main():
    level, layout = circuit()
    destination = ROOT / "roadworks"
    destination.mkdir(exist_ok=True)
    for suffix, data in [("level", level), ("layout", layout)]:
        path = destination / f"roadworks_circuit.{suffix}.json"
        path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        print(path)


if __name__ == "__main__":
    main()
