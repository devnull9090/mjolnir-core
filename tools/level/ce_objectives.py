#!/usr/bin/env python3
"""King and Oddball placements from a level's own CE netgame markers.

gen_ce_level.py keeps CE's HillFlag and OddballSpawn flags in the level's
`markers`. This turns them into what blam-megalo's `koth` and `oddball`
variants look for: invisible scenery labelled `koth_hill` and `oddball_spawn`.

A CE hill is a polygon: its corners are the HillFlags that share a team index,
and that index is the hill's number. The simulation's boundaries are simple
shapes, so each hill becomes a cylinder of the polygon's area around its
centre, tall enough for every corner. Hills rotate in team index order, which
the script reads from each object's spawn order.

Run on a level already converted, this replaces its placements and rewrites
its `modes`, so a map gains the modes without a new conversion:

    python tools/level/ce_objectives.py path/to/map.level.json
"""
import argparse
import json
import math
from collections import defaultdict
from pathlib import Path

# Invisible scenery with a multiplayer block (tools/level/build_ctf_flag.sh).
MARKER_SCENERY = r"objects\multi\ctf\flag_stand"
HILL_LABEL = "koth_hill"
BALL_LABEL = "oddball_spawn"
LABEL = "multiplayer data.megalo label"
# The spawn search takes any scenery with a multiplayer block whose owner team
# is the player's, or neutral: it never asks for a spawn location (sim
# 0x2f84e0). Neutral markers took a third of Prisoner's respawns. No game type
# plays an eighth team.
MARKER_TEAM = "eighth party"
CM_PER_WORLD_UNIT = 304.8
# Fewer corners than this draw no area (Nightfall's one stray HillFlag).
HILL_MIN_CORNERS = 3
# A hill stays big enough to stand in and reaches above its highest corner by
# a Spartan's jump.
HILL_MIN_RADIUS = 0.5    # world units
HILL_HEADROOM = 1.5
HILL_FOOTROOM = 0.5


def _hull(points):
    """The convex hull of (x, y) points, in order (Andrew's monotone chain)."""
    points = sorted(set(points))
    if len(points) < 3:
        return points

    def half(seq):
        out = []
        for p in seq:
            while len(out) >= 2 and ((out[-1][0] - out[-2][0]) * (p[1] - out[-2][1])
                                     - (out[-1][1] - out[-2][1]) * (p[0] - out[-2][0])) <= 0:
                out.pop()
            out.append(p)
        return out[:-1]

    return half(points) + half(reversed(points))


def _area_and_centre(hull):
    """A polygon's area and centroid; the corners' mean if it has no area."""
    twice = cx = cy = 0.0
    for (x0, y0), (x1, y1) in zip(hull, hull[1:] + hull[:1]):
        cross = x0 * y1 - x1 * y0
        twice += cross
        cx += (x0 + x1) * cross
        cy += (y0 + y1) * cross
    if abs(twice) < 1e-6:
        return 0.0, (sum(p[0] for p in hull) / len(hull), sum(p[1] for p in hull) / len(hull))
    return abs(twice) / 2, (cx / (3 * twice), cy / (3 * twice))


def fit_hill(corners):
    """The cylinder for one hill's corners (Unreal cm): centre (cm), then its
    radius, height above and depth below in world units."""
    area, (x, y) = _area_and_centre(_hull([(c[0], c[1]) for c in corners]))
    radius = max(math.sqrt(area / math.pi) / CM_PER_WORLD_UNIT, HILL_MIN_RADIUS)
    low, high = min(c[2] for c in corners), max(c[2] for c in corners)
    return ([round(x, 3), round(y, 3), round(low, 3)], round(radius, 4),
            round((high - low) / CM_PER_WORLD_UNIT + HILL_HEADROOM, 4), HILL_FOOTROOM)


def _marker_object(pos, label, order, radius, top, bottom):
    return {
        "tag": MARKER_SCENERY,
        "group": "scenery",
        "pos": pos,
        "rot": [0, 0, 0],
        "set": {
            LABEL: label,
            "multiplayer data.owner team": MARKER_TEAM,
            "multiplayer data.spawn order": f"{order}",
            "multiplayer data.boundary shape": "cylinder",
            "multiplayer data.boundary width or radius": f"{radius}",
            "multiplayer data.boundary positive height": f"{top}",
            "multiplayer data.boundary negative height": f"{bottom}",
        },
    }


def objective_objects(markers):
    """The level objects for a level's markers, and the modes they allow."""
    hills = defaultdict(list)
    for m in markers:
        if m["type"] == "hill":
            hills[m["team"]].append(m["pos"])
    objects, modes = [], []
    ordered = [hills[t] for t in sorted(hills) if len(hills[t]) >= HILL_MIN_CORNERS]
    for order, corners in enumerate(ordered):
        pos, radius, top, bottom = fit_hill(corners)
        objects.append(_marker_object(pos, HILL_LABEL, order, radius, top, bottom))
    if ordered:
        modes.append("koth")
    balls = [m for m in markers if m["type"] == "oddball"]
    for m in sorted(balls, key=lambda b: b["team"]):
        objects.append(_marker_object(m["pos"], BALL_LABEL, 0, 1, 1, 0.5))
    if balls:
        modes.append("oddball")
    return objects, modes


def hill_list(objects):
    """What MJOLNIRHud's hill marker reads: each hill's x, y, z and radius in
    Unreal cm, in rotation order."""
    hills = [o for o in objects if o["set"].get(LABEL) == HILL_LABEL]
    hills.sort(key=lambda o: int(o["set"]["multiplayer data.spawn order"]))
    return [[*o["pos"], round(float(o["set"]["multiplayer data.boundary width or radius"]) * CM_PER_WORLD_UNIT, 1)]
            for o in hills]


def apply(level):
    """Put a level's objective placements and modes in place. Idempotent."""
    objects = level["blam"]["objects"]
    objects[:] = [o for o in objects if o.get("set", {}).get(LABEL) not in (HILL_LABEL, BALL_LABEL)]
    added, modes = objective_objects(level.get("markers") or [])
    objects.extend(added)
    level["modes"] = [m for m in level.get("modes", ["slayer"]) if m not in ("koth", "oddball")] + modes
    level.pop("koth_hills", None)
    if "koth" in modes:
        level["koth_hills"] = hill_list(added)
    return level


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("level", type=Path)
    args = parser.parse_args()
    level = apply(json.loads(args.level.read_text(encoding="utf-8")))
    args.level.write_text(json.dumps(level, indent=2) + "\n", encoding="utf-8")
    print(f"{args.level}: modes {level['modes']}, "
          f"{sum(o.get('set', {}).get(LABEL) == HILL_LABEL for o in level['blam']['objects'])} hills, "
          f"{sum(o.get('set', {}).get(LABEL) == BALL_LABEL for o in level['blam']['objects'])} ball spawns")


if __name__ == "__main__":
    main()
