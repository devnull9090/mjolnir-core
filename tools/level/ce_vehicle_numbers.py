#!/usr/bin/env python3
"""Read a Custom Edition vehicle's handling and collision out of its map.

    ce_vehicle_numbers.py <map> <tags.json> <vehicle tag> <out dir> [--baseline <vehicle tag>] [--baseline-map <map>]

Writes `numbers.json`, for tools/level/ce_vehicle.py, and each collision BSP as
`<node>.bsp.json` and `.bsp.bin` in that node's own space. The baseline is the
vehicle CE's numbers are read against, the donor's CE self; a map that lacks it,
as Coldsnap lacks every stock vehicle, names one that has it with --baseline-map.
`tags.json` may be empty for a map whose tag names are not protected.
"""
import argparse
import json
import os
import re
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "ce_scripts"))
import ce_scenario  # noqa: E402

B = chr(92)
BASELINE = B.join(["vehicles", "warthog", "mp_warthog"])
# Offsets into a CE object, its vehicle block and its physics tag.
OBJECT_MODEL, OBJECT_COLLISION, OBJECT_PHYSICS, VEHICLE = 0x28, 0x70, 0x80, 0x2F0
# A CE model's marker and node blocks, and the sizes of their elements.
MARKERS, NODES, MARKER_SIZE, INSTANCE_SIZE, NODE_SIZE = 0xAC, 0xB8, 64, 32, 156
VEHICLE_FIELDS = ("forward_speed", "reverse_speed", "acceleration", "deceleration", "steering_left", "steering_right",
                  "wheel_circumference", "turn_rate")


def tag_reference(s, at):
    return struct.unpack_from("<I", s.b, at + 12)[0]


def numbers(s, datum):
    """A vehicle's handling, and the datum of its collision model."""
    o = s.map.off(s.map.tags[datum][2])
    out = dict(zip(VEHICLE_FIELDS, s.f(o + VEHICLE + 8, len(VEHICLE_FIELDS))))
    p = s.map.off(s.map.tags[tag_reference(s, o + OBJECT_PHYSICS)][2])
    out["mass"] = s.f(p + 8)
    out["center_of_mass"] = s.f(p + 0xC, 3)
    out["ground_friction"] = s.f(p + 0x20)
    out["ground_depth"] = s.f(p + 0x24)
    return out, tag_reference(s, o + OBJECT_COLLISION)


def block(s, at):
    """A tag block's count and file offset."""
    count, address = struct.unpack_from("<II", s.b, at)
    return count, s.map.off(address) if count else 0


def unturned(q, v):
    """v through a CE node's rotation, which is stored inverted."""
    u, w = [-q[0], -q[1], -q[2]], q[3]

    def cross(a, b):
        return [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]]

    t = [2 * x for x in cross(u, v)]
    r = cross(u, t)
    return [v[k] + w * t[k] + r[k] for k in range(3)]


def markers(s, datum):
    """The model's markers in the vehicle's space, in CE world units: every
    instance of each name, through each node's rest rotation (a jet's root
    node is turned a quarter; a steering column is tilted)."""
    o = s.map.off(s.map.tags[datum][2])
    m = s.map.off(s.map.tags[tag_reference(s, o + OBJECT_MODEL)][2])
    count, nodes = block(s, m + NODES)
    table = [(s.i16(nodes + NODE_SIZE * i + 36), s.f(nodes + NODE_SIZE * i + 0x28, 3),
              s.f(nodes + NODE_SIZE * i + 0x34, 4)) for i in range(count)]

    def place(i, point):
        """A point in node i's space, in the vehicle's."""
        at = list(point)
        while i >= 0:
            parent, offset, turn = table[i]
            at = [a + b for a, b in zip(unturned(turn, at), offset)]
            i = parent
        return at

    out = {}
    count, block_at = block(s, m + MARKERS)
    for i in range(count):
        q = block_at + MARKER_SIZE * i
        name = s.b[q:q + 32].split(bytes(1))[0].decode("latin1")
        instances, at = block(s, q + 0x34)
        for j in range(instances):
            e = at + INSTANCE_SIZE * j
            out.setdefault(name, []).append(place(s.b[e + 2], s.f(e + 4, 3)))
    return out


def datum_of(s, path):
    want = path.replace("/", B).lower()
    found = [t["datum"] for t in s.by_datum.values() if t["path"].lower() == want and t["class"].strip() == "vehi"]
    found += [d for d, t in s.map.tags.items() if t[0] == "vehi" and t[1].lower() == want]
    if not found:
        sys.exit(f"no vehicle {path!r} in the map")
    return found[0]


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("map")
    ap.add_argument("tags")
    ap.add_argument("vehicle")
    ap.add_argument("out")
    ap.add_argument("--baseline", default=BASELINE)
    ap.add_argument("--baseline-map", help="the map holding the baseline, if not <map>")
    a = ap.parse_args()
    s = ce_scenario.Scenario(a.map, a.tags)
    os.makedirs(a.out, exist_ok=True)

    datum = datum_of(s, a.vehicle)
    vehicle, coll = numbers(s, datum)
    other = ce_scenario.Scenario(a.baseline_map) if a.baseline_map else s
    baseline, _ = numbers(other, datum_of(other, a.baseline))
    nodes = {}
    for bsp in s.collision(coll):
        leaf = re.sub(r"\W+", "_", bsp["node"])
        ce_scenario.write_bsp(bsp, os.path.join(a.out, leaf))
        nodes[bsp["node"]] = leaf + ".bsp.json"
    found = markers(s, datum)
    with open(os.path.join(a.out, "numbers.json"), "w", encoding="utf-8") as f:
        json.dump({"vehicle": vehicle, "baseline": baseline, "collision": nodes,
                   "markers": {k: v[0] for k, v in found.items()}, "all_markers": found}, f, indent=1)
    print(f"{len(nodes)} BSP(s), mass {vehicle['mass']:g} against {baseline['mass']:g}, in {a.out}")


if __name__ == "__main__":
    main()
