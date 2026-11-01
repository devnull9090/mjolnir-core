"""Write a portable 16 x 16 m Foundry assembly, in authored metre/Z-up space.

This is an authoring/traversal fixture, not a native Forge save or a baked map.
Every placement references one stable catalog ID. Runtime adapters must convert
positions by /3.048 into Blam units and resolve the installed pack's palette.
"""

import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def build():
    placements = []

    def place(block, x, y, z, yaw=0, role="structure"):
        placements.append({"id": f"p{len(placements)+1:03}", "block": block,
                           "position_m": [x,y,z], "rotation_deg": [0,0,yaw], "role": role})

    for x in (-6,-2,2,6):
        for y in (-6,-2,2,6):
            place("floor_2x2", x,y,0, role="ground")
    # Two opposed upper decks, reached by eight metres of climbing route.
    for x in (2,6):
        place("floor_2x2", x,-6,4, role="upper_deck")
    for x in (-7,-5):
        place("bridge_straight", x,6,4, role="upper_deck")
    for x in (-3,-1):
        place("floor_1x2", x,6,4, role="upper_deck")
    place("bridge_corner", 0,0,4, role="upper_bridge")
    place("floor_1x1", -1,3,4, role="upper_bridge")
    place("floor_1x1", 1,-3,4, role="upper_bridge")
    place("ramp", -6,-6,0.5,-90, "south_ascent")
    place("ramp", -2,-6,2.5,-90, "south_ascent")
    place("stairs", 6,6,0.5,90, "north_ascent")
    place("ramp", 2,6,2.5,90, "north_ascent")
    place("ramp_shallow", 4,-3,0.5, role="alternate_ascent")
    place("block_1x2", 4,3,0.5, role="intermediate_landing")
    place("block_1x1", -4,0,0.5, role="ground_cover")
    for x,y in [(-7,5),(-7,7),(-1,7),(1,-7),(7,-7),(7,-5)]:
        place("column", x,y,0, role="deck_support")
    for x,y,yaw in [(-6,7.875,0),(-2,7.875,0),(-7.875,6,90),(-6,4.125,0),
                    (2,-7.875,0),(6,-7.875,0),(7.875,-6,90),(6,-4.125,0)]:
        place("railing", x,y,4.5,yaw, "upper_guardrail")
    for x,y,z in [(-6,6,4.5),(6,-6,4.5),(-2,0,0.5)]:
        place("cover", x,y,z, role="cover")
    place("wall", -7.75,0,0.5,90, "perimeter")
    place("wall_corner", -7,3,0.5, role="perimeter")
    place("doorway", 7.75,0,0.5,90, "opening_test")
    place("window", -2,-7.75,0.5, role="opening_test")
    place("wall_half", 2,7.75,0.5, role="perimeter")
    return {"schema_version":1, "name":"Foundry / Crosswalk", "kind":"authoring_layout",
            "units":"meters", "axes":"right_handed_z_up", "footprint_m":[16,16],
            "requires":{"pack":"foundry", "version":"0.1.0"},
            "main_walk_heights_m":[0.5,4.5], "bridge_clearance_m":3.5,
            "notes":["Portable authoring fixture; requires a runtime adapter/bake to play.",
                     "Yaw is counterclockwise about authored +Z; each part keeps its bottom-centre origin.",
                     "Main play surfaces are 4 m apart. The alternate route has a 2.5 m intermediate landing.",
                     "The bridge underside is 3.5 m above the lower walking surface."],
            "checks":["Walk both consecutive ramps across their exact 2 m join.",
                      "Walk the stair-to-ramp route and inspect the last tread.",
                      "Cross the L bridge and both 1 x 1 landing seams.",
                      "Walk beneath the bridge; fire through the window; walk through the doorway.",
                      "Duplicate/rotate/delete a part, save and reload; then test missing-pack download."],
            "placements":placements}


def validate(layout):
    source = json.loads((ROOT/"source/geometry.json").read_text())
    by_id = {p["id"]:p for p in source["pieces"]}
    used = {p["block"] for p in layout["placements"]}
    assert used == set(by_id), "The demo must exercise all 18 part types"
    for placement in layout["placements"]:
        yaw = math.radians(placement["rotation_deg"][2])
        c,s = math.cos(yaw),math.sin(yaw)
        px,py,pz = placement["position_m"]
        for x,y,z in by_id[placement["block"]]["collision"]["vertices"]:
            wx,wy,wz = px+c*x-s*y, py+s*x+c*y, pz+z
            assert abs(wx) <= 8+1e-6 and abs(wy) <= 8+1e-6 and wz >= 0, placement["id"]
    assert layout["bridge_clearance_m"] == 4-0.5


if __name__ == "__main__":
    layout = build()
    validate(layout)
    folder = ROOT / "demo"
    folder.mkdir(exist_ok=True)
    (folder/"crosswalk.layout.json").write_text(json.dumps(layout,indent=2)+"\n",encoding="utf-8")
    print(f"PASS: {len(layout['placements'])} placements, all 18 types inside 16 x 16 m")
