"""Render the actual Forge level JSON with its original pack source meshes.

blender --background --factory-startup --python forge-maps/render.py
blender --background --factory-startup --python forge-maps/render.py -- --blank
blender --background --factory-startup --python forge-maps/render.py -- --opposite

Reads the baked-level inputs, including reflected UE centimetre positions and
yaw, decorative cubes, and light metadata. Invisible gameplay markers and stock
weapon models are counted in the report but omitted from the image. Rendering
uses Blender lighting and authored materials, not a captured game framebuffer.
Point-light power uses an approximate 179 lm/W conversion from authored candela;
--light-scale changes only presentation power, never source/runtime metadata.
Stock vehicles, weapons and invisible gameplay markers are omitted. The script
never writes or regenerates level JSON or the pack source files.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import sys

import bpy
from mathutils import Euler, Vector

ROOT = Path(__file__).resolve().parent
PACK = ROOT.parent / "forge-packs/foundry"
sys.path.insert(0, str(PACK))
from build_blender import material, mesh_object, select_only
from generate import box


def options():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--blank", action="store_true", help="Render Forge Canvas instead of Crossline.")
    parser.add_argument("--level", type=Path, help="Explicit .level.json input, overriding --blank.")
    parser.add_argument("--output", type=Path, help="PNG output path.")
    views = parser.add_mutually_exclusive_group()
    views.add_argument("--top", action="store_true", help="Orthographic overhead review instead of the hero angle.")
    views.add_argument("--opposite", action="store_true", help="Show the opposite side of the arena.")
    parser.add_argument("--light-scale", type=float, default=1.0, help="Preview-only multiplier for fixture power.")
    args = sys.argv[sys.argv.index("--")+1:] if "--" in sys.argv else []
    parsed = parser.parse_args(args)
    if not math.isfinite(parsed.light_scale) or parsed.light_scale < 0:
        parser.error("--light-scale must be finite and nonnegative")
    return parsed


def metre_position(position, origin):
    x, y, z = [position[i] + origin[i] for i in range(3)]
    return Vector((x/100, -y/100, z/100))


def authored_rotation(rot):
    # Level format is UE pitch/yaw/roll. Current maps use only yaw; reject a
    # future tilted placement rather than silently previewing its orientation.
    pitch, yaw, roll = rot
    if abs(pitch) > 1e-8 or abs(roll) > 1e-8:
        raise ValueError("Preview currently supports yaw-only level placements")
    return Euler((0, 0, math.radians(-yaw)), "XYZ")


def prototype(piece, materials, collection):
    parts = []
    for index, geometry in enumerate(piece["visual"]):
        obj = mesh_object(f"{piece['id']}_{index:02}", geometry, collection)
        obj.data.materials.append(materials[geometry["material"]])
        if geometry["bevel_m"] > 0:
            select_only([obj])
            bevel = obj.modifiers.new("Authored edge bevel", "BEVEL")
            bevel.width = geometry["bevel_m"]
            bevel.segments = 2
            bevel.limit_method = "ANGLE"
            bevel.angle_limit = math.radians(20)
            bpy.ops.object.modifier_apply(modifier=bevel.name)
        parts.append(obj)
    select_only(parts)
    bpy.ops.object.join()
    result = bpy.context.view_layer.objects.active
    result.name = "Prototype / " + piece["id"]
    return result


def main():
    args = options()
    path = args.level or ROOT / ("blank/forge_canvas.level.json" if args.blank else "crossline/crossline.level.json")
    level_bytes = path.read_bytes()
    level = json.loads(level_bytes)
    sources, geometry_hashes = {}, {}
    for binding in level["blam"]["forge_packs"]:
        slug = binding["slug"]
        # Only known, checked-in authoring sources supply this preview. The
        # level's exact palette tags select models; unknown pack tags fail.
        pack_root = ROOT.parent / "forge-packs" / slug
        if pack_root.resolve().parent != (ROOT.parent / "forge-packs").resolve():
            raise ValueError("Invalid pack source path: " + slug)
        source_bytes = (pack_root / "source/geometry.json").read_bytes()
        sources[slug] = json.loads(source_bytes)
        geometry_hashes[slug] = hashlib.sha256(source_bytes).hexdigest()
    origin = level.get("canvas", {}).get("origin", [0, 0, 0])
    suffix = "-top" if args.top else "-opposite" if args.opposite else ""
    output = args.output or ROOT / "art" / (level["name"] + suffix + ".png")
    output.parent.mkdir(parents=True, exist_ok=True)
    (ROOT / "build").mkdir(exist_ok=True)

    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    scene = bpy.context.scene
    scene.unit_settings.system = "METRIC"
    scene.unit_settings.scale_length = 1
    assembly = bpy.data.collections.new("Level / Pack placements")
    decor = bpy.data.collections.new("Level / Visible decor")
    lighting = bpy.data.collections.new("Level / Lighting")
    library = bpy.data.collections.new("Unplaced prototypes")
    for collection in (assembly, decor, lighting, library):
        scene.collection.children.link(collection)
    materials = {slug: {name: material(slug + " / " + name, spec)
                        for name, spec in source["materials"].items()}
                 for slug, source in sources.items()}
    by_tag = {f"objects\\mjolnir\\forge\\{slug}\\{piece['id']}": (slug, piece)
              for slug, source in sources.items() for piece in source["pieces"]}
    prototypes, invisible, placed, lights = {}, [], [], []
    prefix = "objects\\mjolnir\\forge\\"
    for index, item in enumerate(level["blam"]["objects"]):
        tag = item["tag"].lower()
        if not tag.startswith(prefix):
            invisible.append(tag)
            continue
        if tag not in by_tag:
            raise ValueError("Missing authoring geometry for " + tag)
        slug, piece = by_tag[tag]
        ident = piece["id"]
        if tag not in prototypes:
            prototypes[tag] = prototype(piece, materials[slug], library)
        obj = prototypes[tag].copy()
        obj.name = f"{index:03} / {ident}"
        obj.location = metre_position(item["pos"], origin)
        obj.rotation_euler = authored_rotation(item.get("rot", [0, 0, 0]))
        obj.scale = (1, 1, 1)
        obj["source_tag"] = item["tag"]
        assembly.objects.link(obj)
        placed.append({"pack": slug, "id": ident, "position_m": list(obj.location), "yaw_deg": -item.get("rot", [0, 0, 0])[1]})
        if spec := piece.get("light"):
            data = bpy.data.lights.new(obj.name + " / Point light", "POINT")
            data.color = spec["color_rgb"]
            # Approximate white-light luminous efficacy for the preview only;
            # runtime retains the exact authored candela and attenuation radius.
            data.energy = 4*math.pi*spec["intensity_cd"]/179*args.light_scale
            data.shadow_soft_size = 0.12
            data.use_shadow = False
            light = bpy.data.objects.new(data.name, data)
            lighting.objects.link(light)
            light.location = obj.location + obj.rotation_euler.to_matrix() @ Vector(spec["offset_m"])
            light["authored_intensity_cd"] = spec["intensity_cd"]
            light["authored_radius_m"] = spec["radius_m"]
            lights.append({"id": ident, "position_m": list(light.location),
                           "preview_power_w": data.energy, **spec})
    library.hide_render = True
    library.hide_viewport = True

    for item in level.get("decor", []):
        if item["mesh"] != "/Engine/BasicShapes/Cube.Cube":
            raise ValueError("Unsupported decor mesh " + item["mesh"])
        w, d, h = item.get("scale", [1, 1, 1])
        obj = mesh_object(item["id"], box(w, d, h, z=-h/2), decor)
        obj.location = metre_position(item.get("pos", [0, 0, 0]), origin)
        obj.rotation_euler = authored_rotation(item.get("rot", [0, 0, 0]))
        obj.data.materials.append(material("Decor / " + item["id"], {
            "base_color": item.get("tint", [.5, .5, .5, 1]), "metallic": 0.05, "roughness": 0.8}))

    slab = next(item for item in level["decor"] if item["id"] == "canvas_slab")
    width, depth = slab["scale"][:2]
    centre = metre_position(slab["pos"], origin)
    centre.z = 1.5 if placed else 0
    camera_data = bpy.data.cameras.new("Layout preview camera")
    camera = bpy.data.objects.new(camera_data.name, camera_data)
    lighting.objects.link(camera)
    if args.top:
        camera.location = centre + Vector((0, 0, max(width, depth)*1.4))
    elif placed:
        # An elevated midfield view shows the actual interior above the
        # perimeter walls. The opposite view exposes the far-side lower lane.
        side = -1 if args.opposite else 1
        camera.location = centre + Vector((side*width*1.5, -side*depth*0.35, max(width, depth)*2))
    else:
        camera.location = centre + Vector((width*1.55, -depth*1.3, max(width, depth)*1.25))
    camera.rotation_euler = (centre-camera.location).to_track_quat("-Z", "Y").to_euler()
    camera_data.type = "ORTHO"
    scene.camera = camera
    sun_data = bpy.data.lights.new("Preview sun", "SUN")
    sun_data.energy = 2
    sun_data.angle = math.radians(8)
    sun = bpy.data.objects.new(sun_data.name, sun_data)
    lighting.objects.link(sun)
    sun.rotation_euler = (math.radians(24), math.radians(-28), math.radians(-25))
    area_data = bpy.data.lights.new("Soft preview fill", "AREA")
    area_data.energy = 12000
    area_data.shape, area_data.size = "DISK", max(width, depth)
    area = bpy.data.objects.new(area_data.name, area_data)
    lighting.objects.link(area)
    area.location = centre + Vector((12, 10, 30))
    area.rotation_euler = (centre-area.location).to_track_quat("-Z", "Y").to_euler()
    scene.world.use_nodes = True
    scene.world.node_tree.nodes["Background"].inputs["Color"].default_value = (.09, .13, .18, 1)
    scene.world.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.4
    scene.render.engine = "CYCLES"
    scene.cycles.samples = 48
    scene.cycles.use_denoising = True
    scene.render.resolution_x = 2000
    scene.render.resolution_y = 1600
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.filepath = str(output.resolve())
    scene.view_settings.view_transform = "AgX"
    bpy.context.view_layer.update()
    inverse = camera.matrix_world.inverted()
    points = [inverse @ (obj.matrix_world @ Vector(corner))
              for collection in (assembly, decor) for obj in collection.objects for corner in obj.bound_box]
    lo = [min(v[k] for v in points) for k in range(2)]
    hi = [max(v[k] for v in points) for k in range(2)]
    ratio = scene.render.resolution_x / scene.render.resolution_y
    camera_data.ortho_scale = max(hi[0]-lo[0], (hi[1]-lo[1])*ratio)*1.14
    camera.location += camera.rotation_euler.to_matrix() @ Vector(((lo[0]+hi[0])/2, (lo[1]+hi[1])/2, 0))
    report = {"level": str(path), "level_sha256": hashlib.sha256(level_bytes).hexdigest(),
              "geometry_sha256": geometry_hashes,
              "view": "top" if args.top else "opposite" if args.opposite else "hero",
              "preview_light_scale": args.light_scale, "preview_luminous_efficacy_lm_per_w": 179,
              "name": level["name"], "pack_placements": placed,
              "foundry_placements": [p for p in placed if p["pack"] == "foundry"],
              "decor_count": len(level.get("decor", [])), "lights": lights,
              "invisible_markers": invisible,
              "stock_vehicle_count": len(level["blam"].get("vehicles", [])),
              "stock_weapon_count": len(level["blam"].get("weapons", [])),
              "stock_equipment_count": len(level["blam"].get("equipment", []))}
    (ROOT / "build" / (output.stem + ".preview.json")).write_text(json.dumps(report, indent=2)+"\n")
    bpy.ops.wm.save_as_mainfile(filepath=str(ROOT / "build" / (output.stem + ".blend")))
    bpy.ops.render.render(write_still=True)
    print(f"FORGE_PREVIEW_OK: {len(placed)} pack placements, {len(level['decor'])} decor, {len(lights)} lights -> {output}")


if __name__ == "__main__":
    main()
