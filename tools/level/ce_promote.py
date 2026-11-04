#!/usr/bin/env python3
"""Mark scenery a CE script creates and destroys as a device, before a map is
converted.

    ce_promote.py <map.map> <staging> --names <object name>...

A map's scenery goes into its BSP's collision and its terrain mesh, where
nothing can move it. A machine stays out of the collision, and
tools/level/add_devices.py can lift its triangles out of the mesh, so the
staging's entry for each name becomes kind "machine" (`promoted` holds its
object name). tools/level/ce_machines.py then builds it as a shield, which
stands for created and destroyed. The names come from
tools/ce_scripts/ce_translate.py's report (`promote`), and this has to run
before convert_ce_map.sh.
"""
import argparse
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "ce_scripts"))
import ce_scenario  # noqa: E402


def promote(entries, objects, names):
    """Flip the scenery entry at each name's position; returns the names done."""
    done = []
    for name in names:
        o = objects.get(name)
        if o is None or o["kind"] != "scenery":
            sys.exit(f"{name}: not a scenery placement")
        hits = [e for e in entries if e.get("kind") == "scenery" and math.dist(e["pos"], o["position"]) < 1e-3]
        hits = hits or [e for e in entries if e.get("promoted") == name]
        if len(hits) != 1:
            sys.exit(f"{name}: {len(hits)} staged entries at {o['position']}")
        hits[0].update(kind="machine", promoted=name)
        done.append(name)
    return done


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("map")
    ap.add_argument("staging")
    ap.add_argument("--names", nargs="+", required=True)
    a = ap.parse_args()
    path = os.path.join(a.staging, "placement.json")
    placement = json.load(open(path, encoding="utf-8"))
    scenario = ce_scenario.Scenario(a.map, os.path.join(a.staging, "tags.json"))
    done = promote(placement["entries"], scenario.named_objects(), a.names)
    json.dump(placement, open(path, "w", encoding="utf-8"))
    print(f"{len(done)} scenery placement(s) now machines: {' '.join(done)}")


if __name__ == "__main__":
    main()
