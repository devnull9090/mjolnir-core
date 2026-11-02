#!/usr/bin/env python3
"""Original Forge Canvas and Crossline layouts; authored metres, Z-up.

Run from any directory. JSON outputs use the level format's UE centimetres,
including its Y/yaw reflection. Geometry remains editable in this script.
"""
import argparse
import json
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
            "post": {"manual_exposure": True, "exposure_bias": 0,
                     "tone_curve": 0, "expand_gamut": 0, "blue_correction": 0}},
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


def perimeter(level):
    """Close the 24x40m deck with three courses of solid 4x0.5x3m walls.

    Outer faces align with the deck edge; perpendicular panels overlap at
    each corner. The flush 9m barrier has no jumpable intermediate ledges,
    and stands 4.5m above the highest playable decks. Keep the sky open.
    """
    for z in (0, 3, 6):
        for x in (-11.75, 11.75):
            for y in range(-18, 19, 4):
                piece(level, "wall", (x, y, z), 90)
        for y in (-19.75, 19.75):
            for x in range(-10, 11, 4):
                piece(level, "wall", (x, y, z))


def spawn(level, position, yaw=0, team="neutral"):
    level["blam"]["player_starts"].append({"pos": ue(position), "yaw": -yaw})
    level["blam"]["objects"].append({"group": "scenery", "tag": SPAWN,
        "pos": ue(position), "rot": [0, -yaw, 0],
        "set": {"multiplayer data.owner team": team}})


def teleporter(level, position, yaw, channel="alpha"):
    level["blam"]["objects"].append({"group": "scenery", "tag": TELE + "2way",
        "pos": ue(position), "rot": [0, -yaw, 0], "set": {
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


def _arena_layout():
    level = base("crossline", "Crossline", 24, 40, ["team_slayer", "slayer", "forge"])
    level["description"] = "Red versus Blue across an enclosed, open-sky Foundry arena: raised bases, twin ramps, side walks and linked portal pads, surrounded by 9 m perimeter walls. Built for 2–8 players."
    grid(level, 24, 40, 4)
    # Raised bases: eight4m floor tiles each, surfaces at4.5m. The same
    # geometry is mirrored through the origin, including spawn/weapon distances.
    for sign, color, team in [(-1, "red", "defender"), (1, "blue", "attacker")]:
        for x in [-6, -2, 2, 6]:
            for y in [12, 16]:
                piece(level, "floor_2x2", (x, sign*y, 4))
            piece(level, "wall", (x, sign*18, 4.5))
        for x in [-6, 6]:
            for y in [12, 16]:
                piece(level, "column", (x, sign*y, 0))
            piece(level, "railing", (sign*8, sign*14 + x/3, 4.5), 90)
        for x in [-2, 2]:
            for y, z in [(4, .5), (8, 2.5)]:
                piece(level, "ramp", (x, sign*y, z), 0 if sign > 0 else 180)
            if sign < 0:
                piece(level, "floor_2x2", (x, 0, 0))
        for x in [-5, -1, 1, 5]:
            spawn(level, (x, sign*14.5, 4.85), -sign*90, team)
        for x in [-4, 4]:
            piece(level, "cover", (x, sign*12, 4.5))
            piece(level, "light_pylon_" + color, (x, sign*17, 4.5))
        # The frame is four metres tall;3m headroom remains above the pad.
        # Put entrances behind the spawn line. Approaching from the arena
        # side exits the opposite pad facing back into play.
        portal = (sign*6, sign*16, 4.5)
        piece(level, "portal_frame", portal)
        # Inset the pad into the deck: a 2cm lip is walkable without jumping.
        piece(level, "teleporter_pad", (portal[0], portal[1], 4.02))
        teleporter(level, (portal[0], portal[1], 4.57), -sign*90)
        cube(level, color + "_stripe", (0, sign*17.75, 4.51), (15.5, .12, .014), COLORS[color])
        for x in [-6, -2, 2, 6]:
            cube(level, f"{color}_back_{x}", (x, sign*17.73, 6), (3.6, .035, 1), COLORS[color])
        level["blam"]["weapons"].append({"type": "battle_rifle", "pos": ue((0, sign*13, 4.9)),
            "yaw": -sign*90, "set": {"multiplayer data.spawn time": "30"}})
        level["blam"]["equipment"].append({"type": "frag_grenade", "pos": ue((sign*4, sign*15, 4.9)),
            "set": {"multiplayer data.spawn time": "30"}})
    for x in [-7, 7]:
        for y in [-8, -4, 0, 4, 8]:
            piece(level, "bridge_straight", (x, y, 4))
        for y in [-6, 6]:
            piece(level, "column", (x, y, 0))
        for y in [-8, -4, 0, 4, 8]:
            piece(level, "railing", (x + (1 if x > 0 else -1), y, 4.5), 90)
        piece(level, "light_strip", (x, 0, 3.5))
    for x in [-4, 0, 4]:
        piece(level, "floor_2x2", (x, 0, 4))
    for x in [-4, 4]:
        piece(level, "cover", (x, 0, 4.5))
    piece(level, "cover", (0, 0, .5))
    for x in [-10, 10]:
        for y in [-8, 8]:
            piece(level, "wall_half", (x, y, 0), 90)
        piece(level, "doorway", (x, 0, 0), 90)
        piece(level, "light_pylon", (x, -4 if x > 0 else 4, 0))
    perimeter(level)
    level["blam"]["weapons"].append({"type": "rocket_launcher", "pos": ue((0, 0, 4.9)),
        "set": {"multiplayer data.spawn time": "120"}})
    return level


def widen_crossline(level):
    """Double Crossline's plan using separate geometry, keeping every height.

    Stock objects and Foundry portal/light models move to the wider layout
    at their original sizes. Only structural tags switch to Foundry Wide.
    This transform is deliberately local to Crossline, not a base() option.
    """
    wide = json.loads((REPO / "forge-packs/foundry-wide/catalog.json").read_text())
    if wide["version"] != "0.1.0" or wide["forge_pack"]["id"] != "foundry-wide":
        raise ValueError("Crossline 0.2 requires Foundry Wide 0.1.0")
    replacements = {ref(b["id"]): b["tag"] for b in wide["forge_pack"]["blocks"]}
    for section in ("objects", "player_starts", "vehicles", "weapons", "equipment"):
        for item in level["blam"].get(section, []):
            item["pos"][:2] = [round(value * 2, 4) for value in item["pos"][:2]]
            if item.get("tag") in replacements:
                item["tag"] = replacements[item["tag"]]
    for item in level["decor"]:
        item["pos"][:2] = [round(value * 2, 4) for value in item["pos"][:2]]
        item["scale"][:2] = [round(value * 2, 4) for value in item["scale"][:2]]
    level["blam"]["forge_packs"].append({"slug": "foundry-wide", "version": wide["version"],
        "blocks": [{"id": b["id"], "tag": b["tag"]} for b in wide["forge_pack"]["blocks"]]})
    level["description"] = (
        "Red versus Blue across a 48 × 80 m open-sky Foundry Wide arena with broader routes and gradual ramps. "
        "Bases remain 4.5 m high, perimeter walls 9 m, and linked portals and lights retain their original size.")
    return level


def arena():
    return widen_crossline(_arena_layout())


def validate(level):
    known = {b["tag"] for p in level["blam"]["forge_packs"] for b in p["blocks"]}
    for item in level["blam"]["objects"]:
        if item["group"] == "crates" and item["tag"] not in known:
            raise ValueError("undeclared piece " + item["tag"])
    if not any(o["tag"] == SPAWN for o in level["blam"]["objects"]):
        raise ValueError("multiplayer requires spawn scenery")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--only", choices=("blank", "crossline"))
    args = parser.parse_args()
    for folder, generate in [("blank", blank), ("crossline", arena)]:
        if args.only and args.only != folder:
            continue
        level = generate()
        validate(level)
        target = ROOT / folder
        target.mkdir(exist_ok=True)
        (target / (level["name"] + ".level.json")).write_text(json.dumps(level, indent=2) + "\n")
        print(folder, len(level["blam"]["objects"]), "simulation objects")


if __name__ == "__main__":
    main()
