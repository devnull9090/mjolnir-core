#!/usr/bin/env python3
"""Read a Custom Edition vehicle's handling and collision out of its map.

    ce_vehicle_numbers.py <map> <tags.json> <vehicle tag> <out dir> [--baseline <vehicle tag>]

Writes `numbers.json`, for tools/level/ce_vehicle.py, and each collision BSP as
`<node>.bsp.json` and `.bsp.bin` in that node's own space. The baseline is the
vehicle CE's numbers are read against, the donor's CE self.
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
VEHICLE_FIELDS = ("forward_speed", "reverse_speed", "acceleration", "deceleration", "steering_left", "steering_right")


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


def markers(s, datum):
    """The model's markers in the vehicle's space, in CE world units: every
    instance of each name. Nodes are summed without their rotation, which
    only a steering column has at rest."""
    o = s.map.off(s.map.tags[datum][2])
    m = s.map.off(s.map.tags[tag_reference(s, o + OBJECT_MODEL)][2])
    count, nodes = block(s, m + NODES)
    table = [(s.i16(nodes + NODE_SIZE * i + 36), s.f(nodes + NODE_SIZE * i + 0x28, 3)) for i in range(count)]

    def rest(i):
        at = [0.0, 0.0, 0.0]
        while i >= 0:
            parent, offset = table[i]
            at = [at[k] + offset[k] for k in range(3)]
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
            node = rest(s.b[e + 2])
            offset = s.f(e + 4, 3)
            out.setdefault(name, []).append([node[k] + offset[k] for k in range(3)])
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
    a = ap.parse_args()
    s = ce_scenario.Scenario(a.map, a.tags)
    os.makedirs(a.out, exist_ok=True)

    datum = datum_of(s, a.vehicle)
    vehicle, coll = numbers(s, datum)
    baseline, _ = numbers(s, datum_of(s, a.baseline))
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
