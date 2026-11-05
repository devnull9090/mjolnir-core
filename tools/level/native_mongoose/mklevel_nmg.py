"""The skinned Mongoose test level: the rig test's beach, native and shipped Mongooses side by side,
the player about 3 m off the native one's left, looking at it."""
import json, sys
n, b = sys.argv[1], chr(92)
d = json.load(open(sys.argv[2], encoding="utf-8"))
d["name"], d["title"] = "nmg", "Skinned Mongoose test"
d["description"] = "The Mongoose drawn by one skinned mesh on its own nodes, beside the shipped one."
v = d["blam"]["vehicles"]
v[0]["tag"] = b.join(["objects", "mjolnir", "nmg", "mongoose"])
v[1]["tag"] = b.join(["objects", "mjolnir", "vht", "mongoose"])
x, y, z = v[0]["pos"]
assert v[0]["yaw"] == 0  # faces +X, so its left is -Y in Unreal
starts = [[x + dx, y - 300.0, z] for dx in (-150.0, -50.0, 50.0, 150.0)]
yaw = 90.0  # towards +Y
for s, o, at in zip(d["blam"]["player_starts"], d["blam"]["objects"], starts):
    s["pos"], s["yaw"] = at, yaw
    o["pos"], o["rot"] = at, [0, yaw, 0]
json.dump(d, open(n, "w", encoding="utf-8"), indent=2)
