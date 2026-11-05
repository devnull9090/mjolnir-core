#!/usr/bin/env python3
"""King, Oddball and Race placements from a level's own CE netgame markers.

gen_ce_level.py keeps CE's HillFlag, OddballSpawn and RaceTrack flags in the
level's `markers`. This turns them into what blam-megalo's King, Oddball and
Race variants look for: invisible scenery labelled `koth_hill`, `oddball_spawn`
and `race_flag`.

A CE hill is a polygon: its corners are the HillFlags that share a team index,
and that index is the hill's number. The simulation's boundaries are simple
shapes, so each hill becomes a cylinder of the polygon's area around its
centre, tall enough for every corner. Hills rotate in team index order, which
the script reads from each object's spawn order.

CE reads a hill's first 12 flags in tag order and no more, and `markers` keeps
tag order, so a CE map's hill uses those 12. One flag alone is a 2 by 2 wu
square around it.

A race track is its RaceTrack flags in team index order. Indices have gaps
(Derelict skips 9, Longest has no 0), so spawn order is the sorted rank, 0 to
n-1, and the script walks ranks. A checkpoint is a cylinder; a map has one
radius for all of them, small enough that two flags in a row never overlap.

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
RACE_LABEL = "race_flag"
HEALTH_LABEL = "ce_health_pack"
LABEL = "multiplayer data.megalo label"
# The spawn search takes any scenery with a multiplayer block whose owner team
# is the player's, or neutral: it never asks for a spawn location (sim
# 0x2f84e0). Neutral markers and health pack spots took most of Prisoner's
# respawns. No game type plays an eighth team.
MARKER_TEAM = "eighth party"
CM_PER_WORLD_UNIT = 304.8
# A polygon needs this many corners. One flag is CE's square (below); a map
# whose only HillFlag is a stray one, as Night-Lockout's, still has no hill.
HILL_MIN_CORNERS = 3
# find_netgame_flags stops at MAXIMUM_HILL_POINTS, in tag order. Halo 2's
# hills are another engine's, so they keep every corner.
HILL_MAX_FLAGS = 12
# king.c: one flag gives corners 1 wu either way of it.
HILL_LONE_FLAG_HALF = 1.0    # world units
# A hill stays big enough to stand in and reaches above its highest corner by
# a Spartan's jump.
HILL_MIN_RADIUS = 0.5    # world units
HILL_HEADROOM = 1.5
HILL_FOOTROOM = 0.5
# CE touches at 1.5 wu on foot and 2.5 wu in a vehicle (race.c); one boundary
# has to serve both, so it starts at 6 m and shrinks until flags in a row, the
# closing leg included, are two radii apart. Flags stacked on two floors stand
# 5 m apart at the least (Derelict), so the height stays under that: a racer
# on one floor never touches the flag on the other. CE has no height limit in
# a vehicle, but no vehicle track stacks its flags that tightly.
RACE_RADIUS = 600.0      # cm
RACE_MIN_RADIUS = 250.0  # cm
RACE_TOP = 1.5           # world units
RACE_BOTTOM = 1.0


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


def _lone_flag_corners(pos):
    """CE's square around a hill of one flag (cm)."""
    half = HILL_LONE_FLAG_HALF * CM_PER_WORLD_UNIT
    return [[pos[0] + dx, pos[1] + dy, pos[2]] for dx in (-half, half) for dy in (-half, half)]


def _hills(markers, max_flags):
    """Each hill's corners, in team index order."""
    hills = defaultdict(list)
    for m in markers:
        if m["type"] == "hill":
            hills[m["team"]].append(m["pos"])
    if not any(len(c) >= HILL_MIN_CORNERS for c in hills.values()):
        return []
    ordered = []
    for team in sorted(hills):
        corners = hills[team][:max_flags]
        if len(corners) == 1:
            ordered.append(_lone_flag_corners(corners[0]))
        elif len(corners) >= HILL_MIN_CORNERS:
            ordered.append(corners)
    return ordered


def race_radius(track):
    """One checkpoint radius for a track's flags (cm positions in rank order),
    in world units."""
    closest = min(math.dist(a, b) for a, b in zip(track, track[1:] + track[:1]))
    return round(min(max(closest / 2, RACE_MIN_RADIUS), RACE_RADIUS) / CM_PER_WORLD_UNIT, 4)


def _race_track(markers):
    """A track's flags in rank order; a track needs two."""
    flags = sorted((m for m in markers if m["type"] == "race_track"), key=lambda m: m["team"])
    teams = [m["team"] for m in flags]
    if len(set(teams)) != len(teams):
        raise ValueError(f"two race flags share an index: {teams}")
    return [m["pos"] for m in flags] if len(flags) >= 2 else []


def objective_objects(markers, hill_flags=HILL_MAX_FLAGS):
    """The level objects for a level's markers, and the modes they allow.
    `hill_flags` is how many of a hill's flags count, None for all of them."""
    objects, modes = [], []
    ordered = _hills(markers, hill_flags)
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
    track = _race_track(markers)
    if track:
        radius = race_radius(track)
        for rank, pos in enumerate(track):
            objects.append(_marker_object(pos, RACE_LABEL, rank, radius, RACE_TOP, RACE_BOTTOM))
        modes.append("race")
    return objects, modes


def _in_order(objects, label):
    """Each object with a label as x, y, z and radius in Unreal cm, by spawn
    order."""
    found = [o for o in objects if o["set"].get(LABEL) == label]
    found.sort(key=lambda o: int(o["set"]["multiplayer data.spawn order"]))
    return [[*o["pos"], round(float(o["set"]["multiplayer data.boundary width or radius"]) * CM_PER_WORLD_UNIT, 1)]
            for o in found]


def hill_list(objects):
    """What MJOLNIRHud's hill marker reads, in rotation order."""
    return _in_order(objects, HILL_LABEL)


def race_list(objects):
    """What MJOLNIRHud's checkpoint marker reads, by rank."""
    return _in_order(objects, RACE_LABEL)


def hill_flags_for(game):
    """How many flags of a hill count on a map from this game."""
    return None if game == "halo2" else HILL_MAX_FLAGS


def apply(level):
    """Put a level's objective placements and modes in place. Idempotent."""
    objects = level["blam"]["objects"]
    objects[:] = [o for o in objects if o.get("set", {}).get(LABEL) not in (HILL_LABEL, BALL_LABEL, RACE_LABEL)]
    for o in objects:
        if o.get("set", {}).get(LABEL) == HEALTH_LABEL:
            o["set"]["multiplayer data.owner team"] = MARKER_TEAM
    added, modes = objective_objects(level.get("markers") or [], hill_flags_for(level.get("game")))
    objects.extend(added)
    level["modes"] = [m for m in level.get("modes", ["slayer"]) if m not in ("koth", "oddball", "race")] + modes
    level.pop("koth_hills", None)
    level.pop("race_flags", None)
    if "koth" in modes:
        level["koth_hills"] = hill_list(added)
    if "race" in modes:
        level["race_flags"] = race_list(added)
    return level


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("level", type=Path)
    args = parser.parse_args()
    level = apply(json.loads(args.level.read_text(encoding="utf-8")))
    args.level.write_text(json.dumps(level, indent=2) + "\n", encoding="utf-8")
    print(f"{args.level}: modes {level['modes']}, "
          f"{sum(o.get('set', {}).get(LABEL) == HILL_LABEL for o in level['blam']['objects'])} hills, "
          f"{sum(o.get('set', {}).get(LABEL) == BALL_LABEL for o in level['blam']['objects'])} ball spawns, "
          f"{sum(o.get('set', {}).get(LABEL) == RACE_LABEL for o in level['blam']['objects'])} race flags")


if __name__ == "__main__":
    main()
