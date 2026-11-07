#!/usr/bin/env python3
"""Put a chassis's lights on a CE vehicle's body.

    ce_vehicle_lights.py <numbers.json> <vehicle_sounds.json> <class> [--bones bones.json]
        [--scale 0.5887] [--shift-x 20.5] [--shift-z -10.8]

A light rides a VFX socket of the donor's rig, which keeps the donor's shape at
the rig's scale, so each is moved in its socket's space onto CE's headlight and
taillight markers. Niagara components cannot be edited in the cooked Blueprint,
so MJOLNIRLevelLoader's vehicle_sounds.lua applies this at spawn, on every
client. Lights CE has no marker for, the Warthog's roof pair, are hidden.

CE's markers can sit behind the model's surface: the Mongoose's taillights are
inside their lamps, so the glow is buried and only the light on the ground
shows. `--bones` takes ce_vehicle_skin.py's bones.json, whose lights it moved
clear of the body, in place of the raw markers.
"""
import argparse
import json

import numpy as np

CM = 304.8
# The Warthog's VFX sockets in the actor's space at rig scale 0.5887, measured
# in game: position in cm and rotation as x, y, z, w.
SOCKETS = {
    "VFX_Headlight_L": ((170.8, -25.1, 82.1), (0.006, 0.043, 0.002, 0.999)),
    "VFX_Headlight_R": ((170.6, 25.1, 82.1), (0.006, 0.043, 0.002, 0.999)),
    "VFX_Headlight_LMid": ((170.8, -9.9, 82.3), (0.006, 0.043, 0.002, 0.999)),
    "VFX_Headlight_RMid": ((170.7, 9.5, 82.5), (0.006, 0.043, 0.002, 0.999)),
    "VFX_Taillight_L": ((-172.8, -54.5, 96.0), (0.0, -0.006, 1.0, -0.002)),
    "VFX_Taillight_R": ((-170.8, 55.6, 94.9), (0.0, -0.006, 1.0, -0.002)),
}
# Each component, its socket, and which CE marker takes it: left outer first.
FRONT = {"VFX_Headlight_L": 0, "VFX_Headlight_LMid": 1, "VFX_Headlight_RMid": 2, "VFX_Headlight_R": 3}
REAR = {"VFX_Taillight_L": 0, "VFX_Taillight_R": 1}
COMPONENTS = {
    "Headlight_L": "VFX_Headlight_L", "NS_Headlights_L": "VFX_Headlight_L",
    "Headlight_R": "VFX_Headlight_R", "NS_Headlights_R": "VFX_Headlight_R",
    "NS_Headlights_Mid_L": "VFX_Headlight_LMid", "NS_Headlights_Mid_R": "VFX_Headlight_RMid",
    "Brakelight_L": "VFX_Taillight_L", "NS_Breaklights_L": "VFX_Taillight_L",
    "Brakelight_R": "VFX_Taillight_R", "NS_Breaklights_R": "VFX_Taillight_R",
}
HIDE = ["NS_Headlights_TopL", "NS_Headlights_TopR"]


def rotate_back(q, v):
    """v by the inverse of the unit quaternion q."""
    u = -np.array(q[:3])
    return v + 2 * np.cross(u, np.cross(u, v) + q[3] * v)


def relative(socket, target, scale):
    position, rotation = SOCKETS[socket]
    q = np.array(rotation) / np.linalg.norm(rotation)
    return [round(float(x), 2) for x in rotate_back(q, np.array(target) - np.array(position)) / scale]


def lights(markers, scale, shift_x, shift_z):
    """{ move = { component: offset in its socket's space }, hide = [...] }."""
    def drawn(p):
        return (p[0] * CM + shift_x, -p[1] * CM, p[2] * CM + shift_z)
    front = sorted((drawn(p) for p in markers["headlight"]), key=lambda p: p[1])
    rear = sorted((drawn(p) for p in markers["taillight"]), key=lambda p: p[1])
    move = {}
    for component, socket in COMPONENTS.items():
        target = front[FRONT[socket]] if socket in FRONT else rear[REAR[socket]]
        move[component] = relative(socket, target, scale)
    return {"move": move, "hide": HIDE}


def cleared(manifest):
    """The lights of a bones.json as markers: wu, CE's axes, by kind."""
    parents = {row["bone"]: row["ue_object"]["translation"] for row in manifest["bones"]}
    markers = {"headlight": [], "taillight": []}
    for row in manifest["light_bones"]:
        at = [row["location"][k] + parents[row["bone"]][k] for k in range(3)]
        kind = "taillight" if "Taillight" in row["name"] else "headlight"
        markers[kind].append((at[0] / CM, -at[1] / CM, at[2] / CM))
    return markers


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("numbers")
    ap.add_argument("table")
    ap.add_argument("actor_class")
    ap.add_argument("--bones", help="ce_vehicle_skin.py's bones.json: lights clear of the body")
    ap.add_argument("--scale", type=float, default=0.5887)
    ap.add_argument("--shift-x", type=float, default=20.5)
    ap.add_argument("--shift-z", type=float, default=-10.8)
    a = ap.parse_args()
    markers = json.load(open(a.numbers, encoding="utf-8"))["all_markers"]
    if a.bones:
        markers = cleared(json.load(open(a.bones, encoding="utf-8")))
    table = json.load(open(a.table, encoding="utf-8"))
    table[a.actor_class]["lights"] = lights(markers, a.scale, a.shift_x, a.shift_z)
    with open(a.table, "w", encoding="utf-8") as f:
        json.dump(table, f, indent=1)
    print(json.dumps(table[a.actor_class]["lights"]))


if __name__ == "__main__":
    main()
