#!/usr/bin/env python3
"""Original Forge Canvas and Crossline layouts; authored metres, Z-up.

Run from any directory. JSON outputs use the level format's UE centimetres,
including its Y/yaw reflection. Geometry remains editable in this script.
"""
import argparse
import importlib.util
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent
CATALOG = REPO / "forge-packs/foundry/catalog.json"
SPAWN = r"objects\multi\spawning\player_spawn"
TELE = r"objects\multi\teleporters\teleporter_"
COLORS = {"red": [.8, .035, .025, 1], "blue": [.025, .18, .9, 1]}
CLEAR_BLOCKS = ["scenery", "machines", "terminals", "controls", "effect scenery",
    "sound scenery", "giants", "squad groups", "zones", "actual cues", "quick cues",
    "trigger volumes", "zone set switch trigger volumes", "scenario kill triggers",
    "cutscene titles", "cutscene camera points", "cutscene spline points", "crates",
    "device groups", "object names", "cutscene flags", "cinematics", "ai objectives",
    "reference frames", "user interface objectives block", "ai user hint data", "scripting data"]


def ue(p):
    return [round(p[0] * 100, 4), round(-p[1] * 100, 4), round(p[2] * 100, 4)]


def ref(ident):
    return rf"objects\mjolnir\forge\foundry\{ident}"


def base(name, title, width, depth, modes):
    catalog = json.loads(CATALOG.read_text())
    return {
        "schema_version": 1, "name": name, "title": title,
        "description": "", "game": "halo1", "multiplayer": True,
        "variant": modes[0], "modes": modes, "kill_floor": -600,
        "canvas": {"scenario": "B40", "origin": [0, 0, 0]},
        "environment": {"sun": {"pitch": -48, "yaw": 25, "intensity": 4,
                                "atmosphere_sun": True},
            "skylight": {"intensity": 1.6, "physical": True}, "atmosphere": True,
            # The packs' rough UNSC materials look the same from Lumen's cache
            # as traced, for 1.75 ms less at 4K (level_format.md). Keep it
            # off for near-mirror materials: the cache turns them blotchy.
            "post": {"manual_exposure": True, "exposure_bias": 0,
                     "tone_curve": 0, "expand_gamut": 0, "blue_correction": 0,
                     "max_traced_roughness": 0.1}},
        "blam": {"clear": {"squads": True, "bipeds": True, "weapons": True,
            "vehicles": True, "equipment": True, "scripts": True, "blocks": CLEAR_BLOCKS},
            "active_bsps": [8], "single_bsp": 8, "map_variant": True,
            "world_bounds": [{"bsp": 8, "min": [-64/3.048, -64/3.048, -8/3.048],
                               "max": [64/3.048, 64/3.048, 64/3.048]}],
            "set": {"type": "multiplayer", "zone sets[0].structure design zone flags": "0x0",
                    "zone sets[0].sruntime tructure design zone flags": "0x0"},
            "player_starts": [], "objects": [], "weapons": [], "equipment": [],
            "forge_packs": [{"slug": "foundry", "version": catalog["version"],
                "blocks": [{"id": b["id"], "tag": b["tag"]} for b in catalog["forge_pack"]["blocks"]]}],
            "forge_objects": [{"group": "scenery", "tag": tag} for tag in
                [SPAWN, TELE + "sender", TELE + "receiver", TELE + "2way"]]},
        "decor": [{"id": "canvas_slab", "mesh": "/Engine/BasicShapes/Cube.Cube",
            "pos": [0, 0, -50], "scale": [width, depth, 1], "tint": [.19, .23, .27, 1]}],
    }


def cube(level, name, position, dimensions, color):
    level["decor"].append({"id": name, "mesh": "/Engine/BasicShapes/Cube.Cube",
        "pos": ue(position), "scale": list(dimensions), "tint": color})


def grid(level, width, depth, step=2):
    for x in range(-width//2, width//2 + 1, step):
        cube(level, f"grid_x_{x}", (x, 0, .006), (.018, depth, .008), [.31, .37, .42, 1])
    for y in range(-depth//2, depth//2 + 1, step):
        cube(level, f"grid_y_{y}", (0, y, .006), (width, .018, .008), [.31, .37, .42, 1])


def piece(level, ident, position, yaw=0):
    level["blam"]["objects"].append({"group": "crates", "tag": ref(ident),
        "pos": ue(position), "rot": [0, -yaw, 0],
        "set": {"multiplayer data.owner team": "neutral"}})


def spawn(level, position, yaw=0, team="neutral"):
    level["blam"]["player_starts"].append({"pos": ue(position), "yaw": -yaw})
    level["blam"]["objects"].append({"group": "scenery", "tag": SPAWN,
        "pos": ue(position), "rot": [0, -yaw, 0],
        "set": {"multiplayer data.owner team": team}})


def teleporter(level, position, yaw, channel="alpha"):
    # On the eighth team, which no game type plays: left unset, a pad is red's
    # (team 0), and the respawn search takes any scenery a team owns, so red
    # respawned on teleporter pads (#346). Any team may use a pad.
    level["blam"]["objects"].append({"group": "scenery", "tag": TELE + "2way",
        "pos": ue(position), "rot": [0, -yaw, 0], "set": {
            "multiplayer data.owner team": "eighth party",
            "multiplayer data.teleporter channel": channel,
            "multiplayer data.boundary shape": "cylinder",
            "multiplayer data.boundary width or radius": "0.35",
            "multiplayer data.boundary positive height": "0.6",
            "multiplayer data.boundary negative height": "0.1"}})


def blank():
    level = base("forge_canvas", "Forge Canvas", 64, 64, ["forge", "slayer"])
    level["description"] = "A clean 64 m construction deck with a 2 m grid, open sky and the full Foundry palette. Start building here."
    grid(level, 64, 64)
    for x, y, yaw in [(0, -4, 90), (-4, 0, 0), (0, 4, -90), (4, 0, 180)]:
        spawn(level, (x, y, .35), yaw)
    # One quiet origin cross. The starting layout contains no construction pieces.
    cube(level, "origin_x", (0, 0, .012), (2, .06, .012), [.95, .5, .08, 1])
    cube(level, "origin_y", (0, 0, .012), (.06, 2, .012), [.95, .5, .08, 1])
    return level


WIDE_PREFIX = ("block_1x1", "block_1x2", "floor_1x1", "floor_1x2", "floor_2x2",
    "bridge_straight", "bridge_corner", "ramp", "ramp_shallow", "wall", "wall_half",
    "wall_corner", "doorway", "window", "railing", "column", "cover", "stairs")
SHOWCASE_IDS = ("floor_4x4", "wall_long", "glass_wall", "window_glazed", "glass_corner",
    "doorway_tall", "doorway_vehicle", "door_panel", "door_vehicle_panel", "ramp_wide",
    "ramp_high", "ramp_wide_high", "ramp_wide_shallow", "landing_guarded", "bridge_t",
    "bridge_cross", "bridge_corner_wide", "lift_station", "teleporter_housing", "teleporter_pad_wide")


def arena_layout():
    """Crossline 0.3: original gameplay routes and optional utility test bays.

    Coordinates below are authored metres, not Unreal's reflected Y. The
    companion layout records routes/fixture identities for independent
    collision tests and authoring previews; it is not a private Forge save.
    """
    level = base("crossline", "Crossline", 96, 160, ["team_slayer", "slayer", "forge"])
    wide = json.loads((REPO / "forge-packs/foundry-wide/catalog.json").read_text())
    blocks = wide["forge_pack"]["blocks"]
    if wide["version"] != "0.2.0" or wide["forge_pack"]["id"] != "foundry-wide":
        raise ValueError("Crossline 0.3 requires Foundry Wide 0.2.0")
    if tuple(b["id"] for b in blocks[:18]) != WIDE_PREFIX or set(b["id"] for b in blocks[18:]) != set(SHOWCASE_IDS):
        raise ValueError("Preserve the original Wide palette prefix and append the twenty showcase pieces")
    level["blam"]["forge_packs"].append({"slug": "foundry-wide", "version": wide["version"],
        "blocks": [{"id": b["id"], "tag": b["tag"]} for b in blocks]})
    level["blam"]["world_bounds"] = [{"bsp": 8, "min": [-96/3.048, -96/3.048, -8/3.048],
                                     "max": [96/3.048, 96/3.048, 64/3.048]}]
    level["description"] = ("A 96 × 160 m Red versus Blue construction showcase: raised bases, broad ramps, "
        "side galleries, a ground-level Warthog route, green teleporters and bypassable door, glass and lift bays. "
        "All 38 Foundry Wide pieces are available in Forge.")
    grid(level, 96, 160, 4)
    layout = {"schema_version": 1, "version": "0.3.0", "units": "metres", "axes": "right_handed_z_up",
        "dimensions_m": [96, 160], "deck_height_m": 4.5, "perimeter_height_m": 9,
        "routes": [], "doors": [], "lifts": [], "showcase": [], "perimeter": [], "teleporters": []}

    def put(ident, position, yaw=0, feature=None):
        index = len(level["blam"]["objects"])
        level["blam"]["objects"].append({"group": "crates", "tag": rf"objects\mjolnir\forge\foundry-wide\{ident}",
            "pos": ue(position), "rot": [0, -yaw, 0], "set": {"multiplayer data.owner team": "neutral"}})
        if feature:
            layout["showcase"].append({"name": feature, "id": ident, "object_index": index})
        return index

    def route(name, points, width, kind="walk"):
        layout["routes"].append({"name": name, "kind": kind, "width_m": width, "points_m": points})

    # Sixteen-metre panels halve the old-piece perimeter budget. All three
    # courses overlap at the corners, leaving no ledges on the inner face.
    # The corner end walls sit 1 cm in and down, so the shared corner has
    # no coplanar faces to z-fight (tools/forge/check_overlaps.py).
    for z in (0, 3, 6):
        for x in (-47.5, 47.5):
            for y in range(-72, 73, 16):
                layout["perimeter"].append(put("wall_long", (x, y, z), 90))
        for y in (-79.5, 79.5):
            for x in range(-40, 41, 16):
                inset = .01 if abs(x) == 40 else 0
                layout["perimeter"].append(put("wall_long", (x - math.copysign(inset, x),
                    y - math.copysign(inset, y), z - inset)))

    for sign, color, team in [(-1, "red", "defender"), (1, "blue", "attacker")]:
        # Forty-eight by twenty-four metre bases. Large floors meet the
        # eight-metre rear row and side galleries exactly, without scaling.
        for x in (-16, 0, 16):
            put("floor_4x4", (x, sign*56, 4), feature=color + " base platform")
            put("wall_long", (x, sign*71.5, 4.5))
        for x in (-20, -12, -4, 4, 12, 20):
            put("floor_2x2", (x, sign*68, 4))
        for x in (-20, 20):
            for y in (52, 68):
                put("column", (x, sign*y, 0))
            put("cover", (x, sign*56, 4.5))
            # 2.5 m outside the teleporter housing, whose end is at x = +/-20.
            piece(level, "light_pylon_" + color, (x + math.copysign(2.5, x), sign*68, 4.5))
        for x in (-12, -4, 4, 12):
            spawn(level, (x, sign*60, 4.85), -sign*90, team)
        for x in (-8, 8):
            put("floor_2x2", (x, sign*12, 0))
            for y, z in ((24, .5), (40, 2.5)):
                put("ramp_wide_shallow", (x, sign*y, z), 0 if sign > 0 else 180,
                    color + " broad approach")
            route(color + f" main ramp {x}", [[x, sign*y, z] for y, z in
                ((8, .5), (16, .5), (32, 2.5), (48, 4.5), (60, 4.5))], 8)
        # The clear centre lane runs beneath the platforms, not through the
        # ramp solids. A stock Warthog under each base preserves symmetry.
        level["blam"].setdefault("vehicles", []).append({"type": "warthog",
            "pos": ue((0, sign*64, .8)), "yaw": sign*90})
        portal = (sign*16, sign*68, 4.5)
        put("teleporter_housing", portal, feature=color + " green teleporter")
        # Sunk into the deck with its top 3 cm proud: at 2 cm the pad's body
        # met the floor's deck panel and flickered through the green field.
        put("teleporter_pad_wide", (portal[0], portal[1], 4.03))
        marker_index = len(level["blam"]["objects"])
        teleporter(level, (portal[0], portal[1], 4.57), -sign*90)
        layout["teleporters"].append({"object_index": marker_index, "support_z_m": 4.53,
            "exit_direction": [0, -sign, 0], "rearm_clearance_m": 3.5})
        cube(level, color + "_base_stripe", (0, sign*70.8, 4.51), (46, .16, .014), COLORS[color])
        level["blam"]["weapons"].append({"type": "battle_rifle", "pos": ue((0, sign*56, 4.9)),
            "yaw": -sign*90, "set": {"multiplayer data.spawn time": "30"}})
        level["blam"]["equipment"].append({"type": "frag_grenade", "pos": ue((sign*8, sign*64, 4.9)),
            "set": {"multiplayer data.spawn time": "30"}})

    # Continuous galleries meet the bases along their entire side edges.
    # Their inner rails leave the central crossbridge and base joins open.
    for x in (-28, 28):
        for y in range(-68, 69, 8):
            put("floor_2x2", (x, y, 4))
            if x < 0 or y not in (-36, 12, 20, 60):
                put("railing", (x + (-3.75 if x < 0 else 3.75), y, 4.5), 90)
            if 4 < abs(y) < 48:
                put("railing", (x + (3.75 if x < 0 else -3.75), y, 4.5), 90)
        # End rails cross the outer rail's end post; 1 cm in and down, their
        # faces stay off the post's, which would z-fight.
        for y in (-71.75, 71.75):
            put("railing", (x - math.copysign(.01, x), y - math.copysign(.01, y), 4.49))
        route("west gallery" if x < 0 else "east gallery", [[x, -68, 4.5], [x, 68, 4.5]], 7)
    for x in (-20, -12, -4, 4, 12, 20):
        put("floor_2x2", (x, 0, 4))
    route("central crossbridge", [[-28, 0, 4.5], [28, 0, 4.5]], 8)
    route("ground vehicle corridor", [[0, -72, 0], [0, 72, 0]], 8, "vehicle")
    route("red ground cross-route", [[-40, -72, 0], [40, -72, 0]], 8, "vehicle")
    level["blam"]["weapons"].append({"type": "rocket_launcher", "pos": ue((0, 0, 4.9)),
        "set": {"multiplayer data.spawn time": "120"}})

    # West lane: automatic doors are useful obstacles, with a walkable
    # bypass to the east. Panels slide along the frame's front, not through
    # its solid lintel, and their full upward travel has open sky.
    for name, y, frame, panel, opening, travel in (
        ("vehicle gate", -48, "doorway_vehicle", "door_vehicle_panel", [8, 5.5], 6),
        ("infantry door", -16, "doorway_tall", "door_panel", [4, 3.5], 4)):
        frame_i = put(frame, (-40, y, 0), feature=name)
        panel_i = put(panel, (-40, y-.75, 0), feature=name + " moving panel")
        layout["doors"].append({"name": name, "frame_index": frame_i, "panel_index": panel_i,
            "opening_m": opening, "travel_m": travel, "bypass_m": [[-33, y-6, 0], [-33, y+6, 0]]})
    route("vehicle gate test", [[-40, -64, 0], [-40, -36, 0]], 8, "vehicle_door")
    put("glass_wall", (-40, 8, 0), feature="solid glass wall")
    put("window_glazed", (-40, 16, 0), feature="glazed window")
    put("glass_corner", (-40, 24, 0), feature="glass corner")
    # Three real bridge footprints form a walkable display route; no
    # invisible square floor fills the T, cross or L cutouts.
    put("floor_1x1", (-40, 28, 0))
    put("bridge_t", (-40, 36, 0), feature="T bridge")
    put("floor_1x1", (-40, 44, 0))
    put("bridge_cross", (-40, 52, 0), feature="cross bridge")
    put("bridge_corner_wide", (-38, 66, 0), feature="wide corner bridge")
    route("bridge shape tour", [[-40, 28, .5], [-40, 62, .5], [-32, 62, .5]], 3)
    route("west utility bypass", [[-33, -56, 0], [-33, 28, 0]], 1.5)

    # East lane: broad/high ramps, a guarded landing and an optional lift.
    # Every raised bay connects to the conventional gallery/ramp routes.
    put("ramp_wide_high", (40, -48, .5), feature="wide high ramp")
    put("floor_2x2", (40, -60, 0))
    put("floor_2x2", (40, -36, 4))
    put("floor_1x1", (34, -36, 4))
    route("wide high ramp", [[40, -60, .5], [40, -56, .5], [40, -40, 4.5], [40, -36, 4.5], [28, -36, 4.5]], 3)
    put("ramp_wide", (40, -16, .5), feature="wide short ramp")
    put("floor_2x2", (40, -24, 0))
    put("landing_guarded", (40, -8, 2), feature="guarded landing")
    put("stairs", (40, 0, .5), 180)
    put("floor_1x1", (40, 6, 0))
    route("short ramp and guarded landing", [[40, -24, .5], [40, -20, .5], [40, -12, 2.5], [40, -4, 2.5]], 3)
    lift_i = put("lift_station", (38, 16, 0), feature="gravity lift station")
    landing_i = put("floor_1x2", (34, 16, 4))
    layout["lifts"].append({"object_index": lift_i, "landing_index": landing_i,
        "launch_m": [38, 16, .5], "landing_m": [34, 16, 4.5], "clear_top_m": 8.5,
        "note": "Steer west onto the adjacent gallery landing; main ramps provide a bypass."})
    put("ramp_high", (40, 48, .5), feature="narrow high ramp")
    put("floor_1x1", (40, 38, 0))
    put("floor_2x2", (40, 60, 4))
    put("floor_1x1", (34, 60, 4))
    route("narrow high ramp", [[40, 38, .5], [40, 40, .5], [40, 56, 4.5], [40, 60, 4.5], [28, 60, 4.5]], 3)
    for x, y in ((-35, -28), (35, 32)):
        piece(level, "light_pylon", (x, y, 0))
    for side in (-1, 1):
        cube(level, f"utility_lane_{side}", (side*33, -16, .012), (.08, 96, .012), [.95, .5, .08, 1])

    # Multiplayer ignores campaign player_starts. FFA players cannot use
    # red/blue-only spawn scenery, so keep neutral starts in common ground
    # without changing the eight team-owned base starts or existing indices.
    for x in (-20, 20):
        for y in (-24, 24):
            spawn(level, (x, y, .35), 90 if y < 0 else -90)

    placed = {o["tag"].split("\\")[-1] for o in level["blam"]["objects"] if "\\foundry-wide\\" in o["tag"]}
    if not set(SHOWCASE_IDS).issubset(placed):
        raise ValueError("Every new Wide piece needs a visible showcase placement")
    layout["authored_object_count"] = sum(len(level["blam"].get(k, [])) for k in ("objects", "weapons", "equipment", "vehicles"))
    if layout["authored_object_count"] > 500:
        raise ValueError("Keep at least 151 of the native 651 object slots available for editing")
    return level, layout


def arena():
    return arena_layout()[0]


def validate(level):
    known = {b["tag"] for p in level["blam"]["forge_packs"] for b in p["blocks"]}
    for item in level["blam"]["objects"]:
        if item["group"] == "crates" and item["tag"] not in known:
            raise ValueError("undeclared piece " + item["tag"])
    if not any(o["tag"] == SPAWN for o in level["blam"]["objects"]):
        raise ValueError("multiplayer requires spawn scenery")
    if "slayer" in level.get("modes", []) and not any(
            o["tag"] == SPAWN and o.get("set", {}).get("multiplayer data.owner team") == "neutral"
            for o in level["blam"]["objects"]):
        raise ValueError("Slayer requires neutral player spawn scenery; campaign starts cannot provide FFA spawns")
    # Pieces may touch but not pass into one another (beyond the deliberate
    # joins) or share a face, which z-fights.
    spec = importlib.util.spec_from_file_location("check_overlaps", REPO / "tools/forge/check_overlaps.py")
    overlaps = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(overlaps)
    found = overlaps.problems(level)
    if found:
        raise ValueError(level["name"] + " pieces collide:\n  " + "\n  ".join(map(overlaps.describe, found)))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--only", choices=("blank", "crossline"))
    args = parser.parse_args()
    for folder, generate in [("blank", blank), ("crossline", arena)]:
        if args.only and args.only != folder:
            continue
        if folder == "crossline":
            level, layout = arena_layout()
        else:
            level, layout = generate(), None
        validate(level)
        target = ROOT / folder
        target.mkdir(exist_ok=True)
        (target / (level["name"] + ".level.json")).write_text(json.dumps(level, indent=2) + "\n")
        if layout is not None:
            (target / (level["name"] + ".layout.json")).write_text(json.dumps(layout, indent=2) + "\n")
        print(folder, len(level["blam"]["objects"]), "simulation objects")


if __name__ == "__main__":
    main()
