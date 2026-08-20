# Export the Blender scene as a .level.json map variant.
#
# Conventions (the one table, mirrored from docs/level_format.md):
#
#   position   UE = (bl.x * 100, -bl.y * 100, bl.z * 100)      meters → cm, Y negates
#   rotation   the mirror across Y negates every rotation angle:
#              UE [pitch, yaw, roll] = [-deg(bl.ry), -deg(bl.rz), -deg(bl.rx)]
#              (verified for single-axis rotations; compound rotations differ in
#              composition order between the two engines — prefer yaw-only)
#   scale      unitless, carried through as-is
#
# All positions are RELATIVE to the Blender world origin; the scene's
# `origin` property says where that lands on the canvas map in UE cm.

import json
import math

import bpy


def _round(v):
    # `round` keeps the sign of -0.0; adding 0.0 normalises it away.
    return round(v, 3) + 0.0


def _pos(obj):
    l = obj.matrix_world.translation
    return [_round(l.x * 100.0), _round(-l.y * 100.0), _round(l.z * 100.0)]


def _rot(obj):
    e = obj.matrix_world.to_euler("XYZ")
    return [
        _round(-math.degrees(e.y)),  # pitch
        _round(-math.degrees(e.z)),  # yaw
        _round(-math.degrees(e.x)),  # roll
    ]


def _yaw(obj):
    return _rot(obj)[1]


def _slug(name):
    out = "".join(c if c.isalnum() else "_" for c in name.lower())
    return out.strip("_") or "item"


def build_level(scene):
    """The .level.json document for a scene, as plain Python data."""
    # matrix_world is stale for objects created since the last depsgraph
    # evaluation (always the case in headless scripts); refresh first.
    bpy.context.view_layer.update()
    s = scene.mjolnir
    level = {
        "schema_version": 1,
        "name": s.level_name,
        "title": s.level_title,
        "canvas": {
            "scenario": s.scenario,
            "origin": [round(v, 3) for v in s.origin],
        },
        "blam": {
            "player_starts": [],
            "vehicles": [],
            "weapons": [],
            "equipment": [],
            "objects": [],
        },
        "decor": [],
        "markers": [],
    }
    problems = []

    for obj in scene.objects:
        m = getattr(obj, "mjolnir", None)
        if m is None or m.kind == "NONE":
            continue
        if m.kind == "PLAYER_START":
            level["blam"]["player_starts"].append({"pos": _pos(obj), "yaw": _yaw(obj)})
        elif m.kind in {"VEHICLE", "WEAPON", "EQUIPMENT"}:
            if not m.type_name:
                problems.append(f"{obj.name}: {m.kind.lower()} needs a type")
                continue
            key = {"VEHICLE": "vehicles", "WEAPON": "weapons", "EQUIPMENT": "equipment"}[m.kind]
            level["blam"][key].append(
                {"type": m.type_name, "pos": _pos(obj), "yaw": _yaw(obj)}
            )
        elif m.kind == "OBJECT":
            if not m.tag_path:
                problems.append(f"{obj.name}: structure needs a tag path")
                continue
            level["blam"]["objects"].append(
                {
                    "tag": m.tag_path,
                    "group": m.object_group,
                    "pos": _pos(obj),
                    "rot": _rot(obj),
                }
            )
        elif m.kind == "DECOR":
            item = {
                "id": _slug(obj.name),
                "mesh": m.mesh_path,
                "pos": _pos(obj),
                "rot": _rot(obj),
                "scale": [round(v, 3) for v in obj.scale],
            }
            if m.use_tint:
                item["tint"] = [round(v, 3) for v in m.tint]
            level["decor"].append(item)
        elif m.kind == "MARKER":
            level["markers"].append({"name": _slug(obj.name), "pos": _pos(obj), "yaw": _yaw(obj)})

    # Drop empty sections so small levels stay small.
    level["blam"] = {k: v for k, v in level["blam"].items() if v}
    for key in ("decor", "markers"):
        if not level[key]:
            del level[key]
    return level, problems


class MJOLNIR_OT_export_level(bpy.types.Operator):
    """Write the scene as a .level.json file"""

    bl_idname = "mjolnir.export_level"
    bl_label = "Export .level.json"

    filepath: bpy.props.StringProperty(subtype="FILE_PATH")

    def execute(self, context):
        level, problems = build_level(context.scene)
        for p in problems:
            self.report({"WARNING"}, p)
        path = self.filepath or bpy.path.abspath(f"//{level['name']}.level.json")
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            json.dump(level, f, indent=2)
            f.write("\n")
        starts = len(level.get("blam", {}).get("player_starts", []))
        self.report(
            {"INFO"},
            f"wrote {path} ({starts} start(s), "
            f"{sum(len(v) for v in level.get('blam', {}).values())} blam item(s), "
            f"{len(level.get('decor', []))} decor)",
        )
        return {"FINISHED"}

    def invoke(self, context, event):
        self.filepath = f"{context.scene.mjolnir.level_name}.level.json"
        context.window_manager.fileselect_add(self)
        return {"RUNNING_MODAL"}
