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


def barrier(level, axis, coordinate, start, end, drop=0.0):
    """Continuous solid 4m half-walls; partial end spans overlap safely.

    Overlapping walls would share faces and z-fight, so every other wall sits
    1 cm to one side and 1 cm lower: in each overlap one wall's faces lie in
    front of the other's (tools/forge/check_overlaps.py). `drop` lowers a
    whole run, so two runs meeting at a corner keep different tops.
    """
    length = end - start
    count = math.ceil(length / 4)
    centres = [(start + end) / 2] if count == 1 else [
        start + 2 + i * (length - 4) / (count - 1) for i in range(count)]
    for i, value in enumerate(centres):
        side = .01 * (i % 2)
        z = 3 - drop - side
        point = (coordinate + side, value, z) if axis == "x" else (value, coordinate + side, z)
        common.piece(level, "wall_half", point, 90 if axis == "x" else 0)


def circuit():
    catalog = json.loads((REPO / "forge-packs/roadworks/catalog.json").read_text())
    if catalog["version"] != "0.2.0":
        raise ValueError("The enlarged circuit requires Roadworks 0.2.0")
    blocks = {b["id"]: b for b in catalog["forge_pack"]["blocks"]}
    level = common.base("roadworks_circuit", "Roadworks Circuit", 320, 320, ["slayer", "forge"])
    level["description"] = (
        "A Warthog test circuit with 16 m lanes, 24/48 m straights, R40 curves, a gradual 4 m climb "
        "and a connected vehicle test pad. Guarded roads stand 3 m above a 320 m recovery deck.")
    level["blam"]["world_bounds"] = [{"bsp": 8,
        "min": [-192 / 3.048, -192 / 3.048, -8 / 3.048],
        "max": [192 / 3.048, 192 / 3.048, 64 / 3.048]}]
    level["blam"]["forge_packs"].append({"slug": "roadworks", "version": catalog["version"],
        "blocks": [{"id": b["id"], "tag": b["tag"]} for b in blocks.values()]})
    # Keep the recovery floor visually distinct from the actual road surface.
    level["decor"][0]["tint"] = [.095, .12, .135, 1]
    common.grid(level, 320, 320, 16)
    position, forward = [88, -72, 3], [0, 1, 0]
    sequence = [
        ("straight_48_guarded", False), ("straight_48", False),
        ("straight_24_guarded", False), ("straight_24_guarded", False),
        ("curve_90_guarded", False),
        ("straight_48_guarded", False), ("straight_48_guarded", False),
        ("curve_45_guarded", False), ("curve_45_guarded", False),
        ("straight_24_guarded", False), ("ramp_48_guarded", False),
        ("straight_24_guarded", False), ("ramp_48_guarded", True),
        ("curve_90_guarded", False),
        ("straight_48_guarded", False), ("straight_48_guarded", False),
        ("curve_45_guarded", False), ("curve_45_guarded", False),
    ]
    loop = []
    for ident, reverse in sequence:
        position, forward, record = connected(level, blocks[ident], position, forward, reverse)
        loop.append(record)
    if math.dist(position, [88, -72, 3]) > 0.00001 or math.dist(forward, [0, 1, 0]) > 0.00001:
        raise ValueError("Road connector changes left the circuit open")
    # The bare segment's inner side opens onto a perpendicular, guarded spur.
    # The spur ends exactly at the pit's right edge: no raised deck lips.
    _, _, spur = connected(level, blocks["straight_48_guarded"], [79.2, 0, 3], [-1, 0, 0])
    pad = [place(level, blocks["straight_48"], (x, -24, 2.5), 0) for x in (-12.8, 4.8, 22.4)]
    # Foundry walls stay 4m long and 0.5m thick. The inside junction walls
    # reach the deck edge so they meet the spur guards without a corner gap.
    # Runs stop 2 cm short of the deck's ends and 2 cm inside the wall they
    # cross at the pit's corners, and the long runs sit 4 cm lower (clear of
    # the 2.1 and 2.5 cm steps between a wall's own layers), so no two faces
    # share a plane.
    barrier(level, "x", 96.25, -23.98, 23.98)
    for lo, hi in [(-23.98, -8.8), (8.8, 23.98)]:
        barrier(level, "x", 79.45, lo, hi)
    barrier(level, "x", -21.35, -23.98, 23.98)
    for y in (-23.75, 23.75):
        barrier(level, "y", y, -21.58, 31.18, drop=.04)
    for lo, hi in [(-23.98, -8.8), (8.8, 23.98)]:
        barrier(level, "x", 30.95, lo, hi)
    # Vehicle origins sit above the road so the native suspension settles.
    # Positive source Y corresponds to UE yaw -90, because vehicle forward is X.
    level["blam"]["vehicles"] = [
        {"type": "warthog", "pos": common.ue((4.8, -6, 3.8)), "yaw": -90},
        {"type": "warthog", "pos": common.ue((-92, 60, 3.8)), "yaw": 90},
        {"type": "warthog", "pos": common.ue((-84, 60, 3.8)), "yaw": -90},
    ]
    # The first live Spartan is beside the pit Warthog for an honest scale view.
    for x, y, yaw in [(1, -6, 0), (-10, 4, 0), (12, 12, 180), (20, -14, 90)]:
        common.spawn(level, (x, y, 3.35), yaw)
    for x, y in [(-16, -18), (-16, 18), (26, -18), (26, 18)]:
        common.piece(level, "light_pylon", (x, y, 3))
    # Flush paint forms a start stripe and a two-metre scale bar on the pit.
    common.cube(level, "start_line", (88, -36, 3.012), (15.8, .18, .012), [.94, .94, .88, 1])
    common.cube(level, "scale_2m", (-.9, -6, 3.012), (.08, 2, .012), [1, .55, .06, 1])
    for y in (-7, -6, -5):
        common.cube(level, "scale_tick_" + str(y), (-.9, y, 3.012), (.4, .06, .012), [1, .55, .06, 1])
    common.validate(level)
    layout = {"schema_version": 1, "units": "metres_z_up", "surface_m": 3,
              "loop": loop, "spur": spur, "pad_object_indices": pad,
              "lap_plan_length_m": 480 + 80 * math.pi}
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
