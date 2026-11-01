"""Fast authored-mesh clearance checks in Blender; not a game physics test.

blender --background --factory-startup --python inspect_layout.py -- --out report.json
"""
import argparse
import json
import math
from pathlib import Path
import sys

import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree

ROOT = Path(__file__).resolve().parent
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--blend", type=Path, default=ROOT / "tst.blend")
parser.add_argument("--placements", type=Path, default=ROOT / "placements.json")
parser.add_argument("--out", type=Path, default=ROOT.parents[2] / ".dream-loop/blender-preview/layout-check.json")
args = parser.parse_args(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else [])
bpy.ops.wm.open_mainfile(filepath=str(args.blend.resolve()))
scale = bpy.context.scene.unit_settings.scale_length
vertices, faces = [], []
for obj in bpy.context.scene.objects:
    if obj.type != "MESH" or obj.hide_render:
        continue
    if any("SOURCE" in c.name.upper() for c in obj.users_collection):
        continue
    start = len(vertices)
    vertices.extend((obj.matrix_world @ v.co) * scale for v in obj.data.vertices)
    for poly in obj.data.polygons:
        mat = obj.data.materials[poly.material_index] if obj.data.materials else None
        if mat and ("sky" in mat.name.lower() or "water" in mat.name.lower() or "teleporter" in mat.name.lower()):
            continue
        faces.append(tuple(start + i for i in poly.vertices))
bvh = BVHTree.FromPolygons(vertices, faces)
placements = json.loads(args.placements.read_text(encoding="utf-8"))


def ray(point, direction, distance):
    hit, normal, index, length = bvh.ray_cast(Vector(point), Vector(direction), distance)
    return None if hit is None else {"point_m": list(hit), "normal": list(normal), "distance_m": length}


def check(name, position):
    x, y, z = position
    floor = ray([x, y, z + .3], [0, 0, -1], 2.0)
    issues = []
    if floor is None:
        issues.append("No authored floor within 1.7 m below marker")
        return {"name": name, "position_m": position, "issues": issues}
    foot = floor["point_m"][2]
    if name.startswith(('balcony_walk_','tower_passage_')) and abs(foot-7.2)>.10:
        issues.append(f"Balcony floor {foot:.2f} m differs from the continuous 7.2 m deck")
    if '_roof_landing_' in name and (abs(foot-6.4)>.015 or floor['normal'][2]<.999):
        issues.append(f"Roof landing must be flat and flush at 6.40 m; found {foot:.3f} m")
    if floor["normal"][2] < .65:
        issues.append("Floor is steeper than the preview limit")
    ceiling = ray([x, y, foot + .05], [0, 0, 1], 2.35)
    if ceiling:
        issues.append(f"Headroom {ceiling['distance_m'] + .05:.2f} m is below 2.4 m preview envelope")
    nearest = None
    for height in (.35, 1.1, 1.9):
        for i in range(16):
            angle = 2 * math.pi * i / 16
            hit = ray([x, y, foot + height], [math.cos(angle), math.sin(angle), 0], .4)
            if hit:
                nearest = min(nearest or .4, hit["distance_m"])
    if nearest is not None:
        issues.append(f"Structure within {nearest:.2f} m of player axis (0.4 m preview radius)")
    return {"name": name, "position_m": position, "floor_m": round(foot, 3),
            "headroom_at_least_m": 2.4 if ceiling is None else round(ceiling["distance_m"] + .05, 3),
            "issues": issues}


checks = [check(f"spawn_{i:02d}_team_{s['team']}", s["position_m"])
          for i, s in enumerate(placements["spawns"])]
for p in placements["teleporters"]:
    checks.append(check(f"teleporter_{p['channel']}_exit", p["to_m"]))
    checks.append(check(f"teleporter_{p['channel']}_entrance", p["from_m"]))
for f in placements["flags"]:
    checks.append(check(f"flag_team_{f['team']}", f["position_m"]))
for item in placements.get("structure_review_points",[]):
    checks.append(check(item["name"],item["position_m"]))
# The architectural enclosure must exist without PCG. At 9 m the rays clear
# low bases and scenery and reach cliffs or the northern retaining structure.
enclosure = []
for degrees in range(360):
    angle = math.radians(degrees)
    hit = ray((0,0,9),(math.cos(angle),math.sin(angle),0),100)
    if hit is None:
        enclosure.append(degrees)
report = {"scope": "Authored structure/terrain only; excludes scenery collision, physics, scoring and networking",
          "player_preview": {"height_m": 2.4, "radius_m": .4},
          "checks": checks, "enclosure_missing_degrees_at_9m":enclosure,
          "issue_count": sum(bool(c["issues"]) for c in checks)+len(enclosure)}
args.out.parent.mkdir(parents=True, exist_ok=True)
args.out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
print(f"TST layout: {len(checks)} placements, {report['issue_count']} needing review -> {args.out}")
if report["issue_count"]:
    raise SystemExit(1)
