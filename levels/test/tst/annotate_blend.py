"""Add inspectable, non-exported placement guides to the generated TST scene.

Run after build_geometry.py, including a source-only --no-export build::

    blender --background --factory-startup --python annotate_blend.py
    blender --background --factory-startup --python annotate_blend.py -- --out inspect.blend

The .blend is the only output. No JMS, placement JSON, or game asset changes.
All guides are unparented empties/cameras in a hidden-from-render collection.
The geometry generator clears the scene before its next export; run this helper
again after that export. Preview objects never become gameplay placements.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import sys

import bpy
from mathutils import Vector


ROOT = Path(__file__).resolve().parent
METRES_PER_CE = 3.048
COLLECTION_NAME = "MJOLNIR_AUTHORING_PREVIEW"
OWNED = "mjolnir_authoring_preview"
COLORS = {
    "red": (0.95, 0.12, 0.08, 1),
    "blue": (0.12, 0.38, 1.0, 1),
    "neutral": (0.95, 0.85, 0.28, 1),
    "scenery": (0.30, 0.85, 0.36, 1),
    "light": (1.0, 0.70, 0.20, 1),
    "teleport": (0.20, 0.90, 1.0, 1),
    "planned": (0.85, 0.30, 0.95, 1),
}

README = """TST PROVING GROUND — SOURCE SCENE

START HERE
This Blender file shows the authored BSP and placement guides. It is not an
in-game render. Trees, boulders, vehicles and fixtures are labeled PROXY bounds;
their stock game meshes/materials are resolved by the conversion pipeline.
Render the finished map in Campaign Evolved to judge lighting and materials.

FAST NATIVE PREVIEW
Run pwsh -File levels/test/tst/preview-native.ps1 from the repository root.
This reads locally installed native cliff, grass and tree meshes, runs the
shared runtime dressing sampler on current triangles, checks placements and
renders fixed views. Open .dream-loop/blender-preview/native-current/preview.blend
for that complete local study. Keep tst.blend as the clean authoring source.
Use -RebuildGeometry only when regenerating from scripts, as it replaces edits.
To inspect the enclosed facility from PowerShell, use:
  & ./levels/test/tst/preview-native.ps1 -Views @('facility-interior',
      'facility-route','facility-door','facility-red','facility-blue')
perimeter_dressing.py/json records native rock and ridge-tree placements shared
with the runtime upgrade. Preview shaders approximate Unreal materials.
Do not distribute the extracted cache or preview.blend in community sources.

UNITS
Authoring scripts and placements.json use metres. Mesh coordinates in this
file use CE world units: 1 Blender unit = 1 CE unit = 3.048 metres. Scene unit
scale is 3.048. The CE JMS exporter uses scale_enum="1" (x100). Do not apply an
extra metre-to-centimetre scale. The outdoor arena remains about 150 by 84
metres. The sealed indoor facility extends north to y=55.5 m; this extra air
is contained inside the architectural walls, floor and roof.

OUTLINER
TST_sealed_terrain_and_sky is the merged gameplay BSP air boundary.
pond_surface and team accents are the intended render-only surfaces.
SOURCE - terrain and base construction contains hidden construction copies.
Unhide those to inspect each base, ramp, terrain and control platform in
isolation. These copies explain the generated geometry; edits to copies are
not automatically re-merged into the exported boundary.
MJOLNIR_AUTHORING_PREVIEW contains only empties and an inspection camera.
Hide that whole collection for an uncluttered view. Its child collections
separate player starts, flags, scenery, vehicles, pickups, lights, teleporters,
and PLANNED objectives. Red/blue names and colors identify team assignments.
Select a marker and inspect Custom Properties for its original coordinates,
tag, modes and other placement data. Arrow direction is the placement yaw.

AUTHORITATIVE SOURCES
build_geometry.py creates terrain, bases, meshes, JMS and placements.json.
facility_architecture.py builds the enclosed diverging hallways and their
editable fitted finishes; facility_doors.py builds the sealed service doors.
facility_edge_wear.py refines selected generated bevel faces after beveling.
Read art/facility-build.md for the design, shared materials and validation.
build_scenario.py turns placements.json into the CE scenario.
rebuild.ps1 performs the validated CE structure/lightmaps/cache pipeline.
annotate_blend.py adds this inspection layer after source generation. A
--no-export build saves the source without changing JMS or the game build.
When the scene property tst_export_pending is true, the older JMS does not
contain the current facility changes; the source still needs export/bake.

To make repeatable geometry or placement changes, edit the relevant generator
and regenerate. A full rebuild overwrites tst.blend and placements.json. Save hand
experiments to a separate .blend before regenerating. Moving a guide here does
not change placements.json or the game. Direct scenario-only JSON edits need
the skip-geometry rebuild route, and will be replaced by the next full build.

EXPORT SAFETY
All preview guides are non-mesh, have no frame parent, and are hidden from
renders. Their collection is marked mjolnir_authoring_preview. The supported
generator clears this entire scene before exporting the fresh BSP. Do not
export the inspection scene as a replacement for that reproducible process.
This helper saves only .blend; it never writes JMS or gameplay placements.

MODE STATUS
CTF and Slayer have implemented variants. Magenta Oddball and King markers
are design intent only until their runtime variants and objectives are built
and tested. A marker is not evidence of a working game mode.

LIGHTING
Fixture markers record scenario placements; they are not Blender lights and
do not add light to the exported game. HEK lightmaps and the Unreal upgrade
determine in-game lighting. Solid viewport colors are material identifiers,
not previews of the resolved game textures.
"""


def arguments():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--blend", type=Path, default=ROOT / "tst.blend")
    parser.add_argument("--placements", type=Path, default=ROOT / "placements.json")
    parser.add_argument("--out", type=Path)
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    return parser.parse_args(argv)


def remove_old_preview():
    existing = bpy.data.collections.get(COLLECTION_NAME)
    if not existing:
        return
    collections = [existing, *existing.children_recursive]
    if not all(c.get(OWNED) for c in collections):
        raise RuntimeError("Preview name is occupied by a user collection; rename it first.")
    objects = list(existing.all_objects)
    if not all(o.get(OWNED) for o in objects):
        raise RuntimeError("Move user-added objects out of the preview collection before regenerating.")
    for obj in objects:
        data = obj.data
        bpy.data.objects.remove(obj, do_unlink=True)
        if isinstance(data, bpy.types.Camera) and data.users == 0:
            bpy.data.cameras.remove(data)
    for collection in reversed(collections):
        bpy.data.collections.remove(collection)


def child(parent, name):
    collection = bpy.data.collections.new(name)
    collection[OWNED] = True
    collection.hide_render = True
    parent.children.link(collection)
    return collection


def marker(collection, name, position_m, *, display="PLAIN_AXES", size_m=1.5,
           color="neutral", yaw=0, arrow=False, original=None):
    obj = bpy.data.objects.new(name, None)
    collection.objects.link(obj)
    obj[OWNED] = True
    obj["position_m"] = [float(v) for v in position_m]
    obj["yaw_degrees"] = float(yaw)
    obj["export"] = "Preview only; modify generator/placements, not this guide"
    if original:
        obj["placement_json"] = json.dumps(original, sort_keys=True)
        if "tag" in original:
            obj["tag"] = original["tag"]
        if "modes" in original:
            obj["modes"] = ", ".join(original["modes"])
    obj.location = Vector(position_m) / METRES_PER_CE
    obj.rotation_euler = (0, math.pi / 2 if arrow else 0, math.radians(yaw))
    obj.empty_display_type = "SINGLE_ARROW" if arrow else display
    obj.empty_display_size = size_m / METRES_PER_CE
    obj.color = COLORS[color]
    obj.show_in_front = True
    obj.show_name = False
    obj.hide_render = True
    return obj


def main():
    args = arguments()
    source = args.blend.resolve(strict=True)
    destination = (args.out or source).resolve()
    placements = json.loads(args.placements.read_text(encoding="utf-8"))
    bpy.ops.wm.open_mainfile(filepath=str(source), load_ui=True)
    scene = bpy.context.scene
    mesh_count = sum(obj.type == "MESH" for obj in scene.objects)
    remove_old_preview()
    preview = bpy.data.collections.new(COLLECTION_NAME)
    preview[OWNED] = True
    preview["purpose"] = "Placement inspection only — no game meshes and no export"
    preview.hide_render = True
    scene.collection.children.link(preview)
    starts = child(preview, "01 - player starts (arrows point forward)")
    flags = child(preview, "02 - CTF flags")
    scenery = child(preview, "03 - scenery PROXY bounds")
    vehicles = child(preview, "04 - vehicle parking PROXY bounds")
    pickups = child(preview, "05 - pickups")
    lights = child(preview, "06 - scenario light fixtures")
    teleporters = child(preview, "07 - paired teleporter channels")
    objectives = child(preview, "08 - PLANNED objectives (not supported modes)")
    views = child(preview, "09 - inspection camera")

    for index, item in enumerate(placements.get("spawns", []), 1):
        team = {0: "red", 1: "blue"}.get(item.get("team"), "neutral")
        marker(starts, f"START {index:02d} - {team.upper()}", item["position_m"],
               color=team, yaw=item.get("yaw_degrees", 0), arrow=True,
               size_m=2.5, original=item)
    for index, item in enumerate(placements.get("flags", []), 1):
        team = "red" if item.get("team") == 0 else "blue"
        marker(flags, f"FLAG {index:02d} - {team.upper()}", item["position_m"],
               color=team, display="SINGLE_ARROW", size_m=3.5, original=item)
    for index, item in enumerate(placements.get("scenery", []), 1):
        is_tree = "trees" in item["tag"]
        height_m, radius_m = (13.57, 3.5) if is_tree else (3.0, 1.8)
        center = list(item["position_m"])
        center[2] += height_m / 2
        obj = marker(scenery, f"{'TREE' if is_tree else 'ROCK'} {index:02d} - PROXY",
                     center, display="CUBE", size_m=1, color="scenery",
                     yaw=item.get("yaw_degrees", 0), original=item)
        obj.scale = (radius_m, radius_m, height_m / 2)
        obj["proxy_note"] = "Approximate study bounds, not the stock asset or its collision"
        obj["placement_origin_m"] = item["position_m"]
    for index, item in enumerate(placements.get("vehicles", []), 1):
        team = "red" if item.get("team") == 0 else "blue"
        center = list(item["position_m"])
        center[2] += 1.2
        obj = marker(vehicles, f"WARTHOG {index:02d} - {team.upper()} PROXY", center,
                     display="CUBE", size_m=1, color=team,
                     yaw=item.get("yaw_degrees", 0), original=item)
        obj.scale = (2.5, 1.5, 1.2)
        obj["placement_origin_m"] = item["position_m"]
    for index, item in enumerate(placements.get("pickups", []), 1):
        label = item["tag"].rsplit("\\", 1)[-1].upper()
        marker(pickups, f"PICKUP {index:02d} - {label}", item["position_m"],
               display="SPHERE", size_m=.7, original=item)
    for index, item in enumerate(placements.get("lights", []), 1):
        marker(lights, f"LIGHT {index:02d} - scenario fixture PROXY", item["position_m"],
               display="SPHERE", size_m=.65, color="light", original=item)
    for item in placements.get("teleporters", []):
        channel = item["channel"]
        for key, label in [("from", "SENDER"), ("to", "RECEIVER")]:
            position = item[f"{key}_m"]
            marker(teleporters, f"TELEPORT {channel} - {label}", position,
                   display="CIRCLE", size_m=1.7, color="teleport", original=item)
            marker(teleporters, f"TELEPORT {channel} - {label} facing", position,
                   size_m=2.7, color="teleport", arrow=True,
                   yaw=item.get(f"{key}_yaw_degrees", 0), original=item)
    for mode, spec in placements.get("objective_markers", {}).items():
        positions = spec.get("positions_m") or [spec["position_m"]]
        for index, position in enumerate(positions, 1):
            marker(objectives, f"PLANNED {mode.upper()} {index} - not a working objective",
                   position, display="CIRCLE", size_m=4.5, color="planned", original=spec)

    camera_data = bpy.data.cameras.new("TST inspection camera")
    camera = bpy.data.objects.new("VIEW - arena overview (not exported)", camera_data)
    views.objects.link(camera)
    camera[OWNED] = True
    camera.hide_render = True
    camera.location = Vector((0, -112, 90)) / METRES_PER_CE
    target = Vector((0, 1, 1.5)) / METRES_PER_CE
    camera.rotation_euler = (target - camera.location).to_track_quat("-Z", "Y").to_euler()
    camera_data.type = "PERSP"
    camera_data.lens = 35
    camera_data.clip_end = 1000 / METRES_PER_CE
    scene.camera = camera
    scene.render.resolution_x = 1600
    scene.render.resolution_y = 900
    scene.render.resolution_percentage = 100
    scene.unit_settings.system = "METRIC"
    scene.unit_settings.scale_length = METRES_PER_CE
    for screen in bpy.data.screens:
        for area in screen.areas:
            if area.type != "VIEW_3D":
                continue
            space = area.spaces.active
            space.shading.type = "SOLID"
            space.shading.color_type = "MATERIAL"
            space.shading.light = "STUDIO"
            space.shading.show_cavity = True
            space.shading.cavity_type = "BOTH"
            space.shading.background_type = "WORLD"
            space.overlay.show_floor = False
            space.overlay.show_axis_x = False
            space.overlay.show_axis_y = False
            space.clip_end = 1000 / METRES_PER_CE
            space.region_3d.view_perspective = "PERSP"
            space.region_3d.view_location = target
            space.region_3d.view_rotation = camera.rotation_euler.to_quaternion()
            space.region_3d.view_distance = (camera.location - target).length
    for obj in scene.objects:
        obj.select_set(False)
    scene.cursor.location = (0, 0, 0)
    text_block = bpy.data.texts.get("README - TST AUTHORING") or bpy.data.texts.new("README - TST AUTHORING")
    text_block.clear()
    text_block.write(README)
    scene["source_readme"] = text_block.name
    scene["authoring_units"] = "1 CE/Blender unit = 3.048 metres; placement JSON uses metres"
    if mesh_count != sum(obj.type == "MESH" for obj in scene.objects):
        raise RuntimeError("Annotation unexpectedly changed the scene's mesh count")
    if any(obj.type not in {"EMPTY", "CAMERA"} or obj.parent for obj in preview.all_objects):
        raise RuntimeError("Inspection guides must stay non-mesh and unparented")
    destination.parent.mkdir(parents=True, exist_ok=True)
    # Resolve against the opened source first, then relativize to the actual
    # save destination. No image content is changed and no game cache is packed.
    for image in bpy.data.images:
        if image.source == 'FILE' and image.filepath:
            absolute=bpy.path.abspath(image.filepath)
            image.filepath=bpy.path.relpath(absolute,start=str(destination.parent)).replace('\\','/')
    bpy.ops.wm.save_as_mainfile(filepath=str(destination),relative_remap=False)
    print(f"TST_ANNOTATED {destination}: {len(preview.all_objects)} non-mesh guides; {mesh_count} meshes unchanged")


if __name__ == "__main__":
    main()
