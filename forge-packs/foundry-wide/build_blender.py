"""Export full-size Foundry Wide assets, then arrange a common-scale preview.

blender --background --factory-startup --python build_blender.py -- --render
Only this pack's source/build files are written. Pure mesh/material helpers
come from Foundry's builder; its main/generation functions are never called.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import sys

import bpy
from mathutils import Vector

ROOT = Path(__file__).resolve().parent


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


gen = load_module("foundry_wide_generator", ROOT / "generate.py")
validation = load_module("foundry_wide_validation", ROOT / "validate.py")
original = load_module("foundry_original_primitives", ROOT.parent / "foundry" / "generate.py")


def load_helpers():
    # Foundry's builder imports its neighbouring generator/validator by name.
    # Isolate those imports so another pack loaded in this Blender process
    # cannot supply them accidentally. Importing executes no generation.
    old_path = sys.path[:]
    saved = {name: sys.modules.pop(name, None) for name in ("generate", "validate")}
    try:
        sys.path.insert(0, str(ROOT.parent / "foundry"))
        return load_module("foundry_shared_blender_helpers", ROOT.parent / "foundry" / "build_blender.py")
    finally:
        sys.path[:] = old_path
        for name, module in saved.items():
            sys.modules.pop(name, None)
            if module is not None:
                sys.modules[name] = module


helpers = load_helpers()
select_only, label = helpers.select_only, helpers.text_object


def material(name, spec):
    result = helpers.material(name, spec)
    shader = result.node_tree.nodes.get("Principled BSDF")
    if spec["base_color"][3] < 1:
        shader.inputs["Alpha"].default_value = spec["base_color"][3]
        result.surface_render_method = "DITHERED"
    if "transmission_weight" in spec:
        shader.inputs["Transmission Weight"].default_value = spec["transmission_weight"]
        shader.inputs["IOR"].default_value = spec["ior"]
    return result


def mesh_object(name, component, collection):
    obj = helpers.mesh_object(name, component, collection)
    if "uvs" in component:
        layer = obj.data.uv_layers.new(name="UVMap")
        for polygon in obj.data.polygons:
            for index in polygon.loop_indices:
                layer.data[index].uv = component["uvs"][obj.data.loops[index].vertex_index]
    return obj


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--render", action="store_true")
    parser.add_argument("--output", type=Path, default=ROOT / "build")
    parser.add_argument("--only", help="Export one piece without replacing the full contact sheet or blend")
    options = parser.parse_args(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else [])
    output = options.output.resolve()
    for folder in (output, output / "models", output / "collision"):
        folder.mkdir(parents=True, exist_ok=True)
    original_hash = hashlib.sha256(gen.BASE.read_bytes()).hexdigest()
    source = gen.write_sources()
    validation.main()
    if options.only and options.only not in {p["id"] for p in source["pieces"]}:
        parser.error("Unknown piece ID")
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    scene = bpy.context.scene
    scene.unit_settings.system, scene.unit_settings.scale_length = "METRIC", 1.0
    mats = {name: material("Foundry Wide / " + name, spec) for name, spec in source["materials"].items()}
    assets = bpy.data.collections.new("Foundry Wide / Assets")
    collisions = bpy.data.collections.new("Foundry Wide / Collision")
    studio = bpy.data.collections.new("Foundry Wide / Presentation")
    for collection in (assets, collisions, studio):
        scene.collection.children.link(collection)
    collisions.hide_render = True
    models, report = [], []
    for piece in source["pieces"]:
        if options.only and piece["id"] != options.only:
            continue
        parts = []
        for index, component in enumerate(piece["visual"]):
            obj = mesh_object(f"{piece['id']}_{index:02}", component, assets)
            obj.data.materials.append(mats[component["material"]])
            if component["bevel_m"] > 0:
                select_only([obj])
                bevel = obj.modifiers.new("Cosmetic inward bevel", "BEVEL")
                bevel.width, bevel.segments = component["bevel_m"], 2
                bevel.limit_method, bevel.angle_limit = "ANGLE", math.radians(20)
                bpy.ops.object.modifier_apply(modifier=bevel.name)
            parts.append(obj)
        select_only(parts)
        bpy.ops.object.join()
        model = bpy.context.view_layer.objects.active
        model.name = "foundry_wide_" + piece["id"]
        model["forge_pack"], model["forge_id"] = "foundry-wide", piece["id"]
        model["origin_convention"], model["snap_m"] = "bottom_center", 0.5
        model["dimensions_m"] = piece["dimensions_m"]
        model.asset_mark()
        model.asset_data.author = "MJOLNIR Core contributors"
        model.asset_data.description = piece["name"] + ". " + piece["notes"]
        for tag in ("Foundry Wide", piece["category"], "4 m module"):
            model.asset_data.tags.new(tag)
        # All exports precede presentation transforms. glTF is metres/Y-up;
        # source and collision remain metres/Z-up with bottom-centre origins.
        select_only([model])
        assert tuple(model.location) == (0, 0, 0) and tuple(model.scale) == (1, 1, 1)
        for extension, format_name in (("gltf", "GLTF_SEPARATE"), ("glb", "GLB")):
            bpy.ops.export_scene.gltf(filepath=str(output / "models" / f"{piece['id']}.{extension}"),
                                     export_format=format_name, use_selection=True, export_yup=True,
                                     export_apply=True, export_extras=True, export_cameras=False, export_lights=False)
        collision = {"id": piece["id"], "units": "meters", "axes": "right_handed_z_up",
                     "dimensions_m": piece["dimensions_m"], **piece["collision"]}
        (output / "collision" / f"{piece['id']}.json").write_text(json.dumps(collision, indent=2) + "\n", encoding="utf-8")
        with (output / "collision" / f"{piece['id']}.obj").open("w", encoding="utf-8") as stream:
            stream.write("# Foundry Wide collision; metres/Z-up; closed convex hulls\n")
            for vertex in collision["vertices"]:
                stream.write("v " + " ".join(f"{v:.9f}" for v in vertex) + "\n")
            offset = 0
            for index, hull in enumerate(collision["hulls"]):
                stream.write(f"g hull_{index:02}\n")
                for triangle in hull["triangles"]:
                    stream.write("f " + " ".join(str(v + offset + 1) for v in triangle) + "\n")
                offset += len(hull["vertices"])
        collider = mesh_object("COL_" + piece["id"], piece["collision"], collisions)
        collider.display_type = "WIRE"
        collider.hide_set(True)
        model.data.calc_loop_triangles()
        models.append((model, collider, piece))
        report.append({"id": piece["id"], "visual_triangles": len(model.data.loop_triangles),
                       "collision_triangles": len(collision["triangles"]), "collision_hulls": len(collision["hulls"]),
                       "dimensions_m": piece["dimensions_m"], "origin": "bottom_center"})
    assert hashlib.sha256(gen.BASE.read_bytes()).hexdigest() == original_hash, "Original Foundry was modified."
    report_name = "export-report" + ("-" + options.only if options.only else "") + ".json"
    (output / report_name).write_text(json.dumps({
        "blender": bpy.app.version_string,
        "source_sha256": hashlib.sha256((ROOT / "source" / "geometry.json").read_bytes()).hexdigest(),
        "export_scale": 1, "presentation_scale": 0.38, "pieces": report}, indent=2) + "\n", encoding="utf-8")
    print(f"FOUNDRY_WIDE_EXPORTS_READY: {len(models)} full-size glTF+bin, GLB and collision JSON/OBJ pairs", flush=True)
    if options.only:
        return

    backdrop = material("Studio / background", {"base_color": [.017, .025, .032, 1], "metallic": 0, "roughness": .9})
    cards = material("Studio / cards", {"base_color": [.045, .063, .072, 1], "metallic": 0, "roughness": .85})
    white = material("Studio / type", {"base_color": [.85, .9, .88, 1], "metallic": 0, "roughness": .7})
    gray = material("Studio / secondary", {"base_color": [.42, .53, .57, 1], "metallic": 0, "roughness": .8})
    rows = math.ceil(len(models)/6)
    half_height = rows*10.5/2
    ground = mesh_object("Studio ground", original.box(65, rows*10.5+14, .1, z=-.25), studio)
    ground.data.materials.append(backdrop)
    for index, (model, collider, piece) in enumerate(models):
        x, y = (index % 6 - 2.5) * 9, ((rows-1)/2 - index // 6) * 10.5
        model.scale = (.38, .38, .38)
        model.location = (x, y + .7, 0)
        model.rotation_euler.z = math.radians(-25)
        collider.location, collider.rotation_euler, collider.scale = model.location, model.rotation_euler, model.scale
        card = mesh_object("Tile " + piece["id"], original.box(8.6, 10, .06, x, y, -.1), studio)
        card.data.materials.append(cards)
        title = piece['name'].removeprefix("Wide ").upper()
        label(f"{index+1:02}  {title}", x - 3.9, y - 3.9, .29, white, studio)
        label(" x ".join(f"{v:g}" for v in piece["dimensions_m"]) + " m", x - 3.9, y - 4.55, .34, gray, studio)
    label("FOUNDRY WIDE  /  0.2", -26.4, half_height+4, 1.65, white, studio)
    label("38 PIECES  /  GLASS, DOORS, RAMPS & UTILITIES  /  ORIGINAL 18 PRESERVED", -26.2, half_height+2.5, .4, mats["amber"], studio)
    label("4 m MODULE  /  0.5 m SNAP  /  ALL PIECES SHOWN AT THE SAME SCALE", -26.2, -half_height-2, .43, mats["amber"], studio)
    label("Actual meshes. Glass and energy are Blender material previews; native rendering is validated separately.", -26.2, -half_height-3, .32, gray, studio)
    camera_data = bpy.data.cameras.new("Contact sheet camera")
    camera = bpy.data.objects.new("Contact sheet camera", camera_data)
    studio.objects.link(camera)
    camera.location = (0, -32, 100)
    camera.rotation_euler = (Vector((0, 0, 0)) - camera.location).to_track_quat("-Z", "Y").to_euler()
    camera_data.type, camera_data.ortho_scale = "ORTHO", max(59, rows*10.5+12)
    scene.camera = camera
    for name, position, energy, size in (("Key", (-18, -12, 35), 15000, 25), ("Fill", (18, 5, 25), 12000, 20), ("Rim", (0, 20, 18), 9000, 15)):
        data = bpy.data.lights.new(name, "AREA")
        data.energy, data.shape, data.size = energy, "DISK", size
        light = bpy.data.objects.new(name, data)
        studio.objects.link(light)
        light.location = position
        light.rotation_euler = (Vector((0, 0, 0)) - light.location).to_track_quat("-Z", "Y").to_euler()
    scene.world.use_nodes = True
    scene.world.node_tree.nodes["Background"].inputs["Color"].default_value = (.23, .27, .3, 1)
    scene.world.node_tree.nodes["Background"].inputs["Strength"].default_value = .35
    scene.render.engine = "CYCLES"
    scene.cycles.samples, scene.cycles.use_denoising = 32, True
    scene.render.resolution_x, scene.render.resolution_y = 2400, 3500
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.filepath = str(output / "foundry-wide-contact-sheet.png")
    scene.view_settings.view_transform = "AgX"
    bpy.ops.wm.save_as_mainfile(filepath=str(output / "foundry-wide.blend"))
    if options.render:
        bpy.ops.render.render(write_still=True)
    print("FOUNDRY_WIDE_BUILD_OK", flush=True)


if __name__ == "__main__":
    main()
