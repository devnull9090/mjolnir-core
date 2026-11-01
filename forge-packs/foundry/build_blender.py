"""Build/export Foundry with Blender 5.2 LTS, including a real model contact sheet.

  blender --background --factory-startup --python build_blender.py -- --render

The Python source is authoritative. build/ contains generated GLBs, collision
OBJs/JSON, a .blend asset library, the render and an export report. No add-on,
network access, purchased textures or game-extracted resources are required.
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
sys.path.insert(0, str(ROOT))
from generate import write_sources
from validate import main as validate_sources


def args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--render", action="store_true", help="Render the actual exported models.")
    parser.add_argument("--output", type=Path, default=ROOT / "build")
    return parser.parse_args(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else [])


def material(name, spec):
    result = bpy.data.materials.new(name)
    result.use_nodes = True
    shader = result.node_tree.nodes.get("Principled BSDF")
    shader.inputs["Base Color"].default_value = spec["base_color"]
    shader.inputs["Metallic"].default_value = spec["metallic"]
    shader.inputs["Roughness"].default_value = spec["roughness"]
    result.diffuse_color = spec["base_color"]
    return result


def mesh_object(name, component, collection):
    data = bpy.data.meshes.new(name)
    data.from_pydata(component["vertices"], [], component["triangles"])
    data.update()
    obj = bpy.data.objects.new(name, data)
    collection.objects.link(obj)
    return obj


def select_only(objects):
    bpy.ops.object.select_all(action="DESELECT")
    for obj in objects:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = objects[0]


def text_object(text, x, y, size, mat, collection, align="LEFT"):
    curve = bpy.data.curves.new(text, "FONT")
    curve.body = text
    curve.size = size
    curve.align_x = align
    curve.extrude = 0
    obj = bpy.data.objects.new(text, curve)
    obj.location = (x, y, 0.02)
    curve.materials.append(mat)
    collection.objects.link(obj)
    return obj


def main():
    options = args()
    output = options.output.resolve()
    for folder in (output, output / "models", output / "collision"):
        folder.mkdir(parents=True, exist_ok=True)
    source = write_sources()
    validate_sources()
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    scene = bpy.context.scene
    scene.unit_settings.system = "METRIC"
    scene.unit_settings.scale_length = 1.0
    materials = {name: material("Foundry / " + name, spec) for name, spec in source["materials"].items()}
    visual_collection = bpy.data.collections.new("Foundry / Assets")
    collision_collection = bpy.data.collections.new("Foundry / Collision")
    presentation = bpy.data.collections.new("Foundry / Presentation")
    for collection in (visual_collection, collision_collection, presentation):
        scene.collection.children.link(collection)
    collision_collection.hide_render = True
    report, models = [], []
    for piece in source["pieces"]:
        components = []
        for index, geometry in enumerate(piece["visual"]):
            obj = mesh_object(f"{piece['id']}_{index:02}", geometry, visual_collection)
            obj.data.materials.append(materials[geometry["material"]])
            if geometry["bevel_m"] > 0:
                select_only([obj])
                modifier = obj.modifiers.new("Small inward edge bevel", "BEVEL")
                modifier.width = geometry["bevel_m"]
                modifier.segments = 2
                modifier.limit_method = "ANGLE"
                modifier.angle_limit = math.radians(20)
                bpy.ops.object.modifier_apply(modifier=modifier.name)
            components.append(obj)
        select_only(components)
        bpy.ops.object.join()
        model = bpy.context.view_layer.objects.active
        model.name = "foundry_" + piece["id"]
        model["forge_pack"] = "foundry"
        model["forge_id"] = piece["id"]
        model["snap_m"] = 0.5
        model["dimensions_m"] = piece["dimensions_m"]
        model["origin_convention"] = "bottom_center"
        model.asset_mark()
        model.asset_data.description = piece["name"] + ". " + piece["notes"]
        model.asset_data.author = "MJOLNIR Core contributors"
        model.asset_data.tags.new("Foundry")
        model.asset_data.tags.new(piece["category"])
        model.asset_data.tags.new("2 m module")
        select_only([model])
        model.data.calc_loop_triangles()
        glb_path = output / "models" / (piece["id"] + ".glb")
        # Blender exports conventional glTF metre/Y-up coordinates. geometry.json
        # and collision exports deliberately remain metre/Z-up for native baking.
        bpy.ops.export_scene.gltf(filepath=str(glb_path), export_format="GLB", use_selection=True,
                                  export_yup=True, export_apply=True, export_extras=True,
                                  export_cameras=False, export_lights=False)
        bpy.ops.export_scene.gltf(filepath=str(output / "models" / (piece["id"] + ".gltf")),
                                  export_format="GLTF_SEPARATE", use_selection=True,
                                  export_yup=True, export_apply=True, export_extras=True,
                                  export_cameras=False, export_lights=False)
        collision = {"id": piece["id"], "units": "meters", "axes": "right_handed_z_up",
                     "dimensions_m": piece["dimensions_m"], **piece["collision"]}
        (output / "collision" / (piece["id"] + ".json")).write_text(json.dumps(collision, indent=2) + "\n")
        with (output / "collision" / (piece["id"] + ".obj")).open("w") as stream:
            stream.write("# Foundry collision; metres, Z-up; closed convex components\n")
            for point in collision["vertices"]:
                stream.write("v " + " ".join(f"{v:.6f}" for v in point) + "\n")
            offset = 0
            for index, hull in enumerate(collision["hulls"]):
                stream.write(f"g hull_{index:02}\n")
                for triangle in hull["triangles"]:
                    stream.write("f " + " ".join(str(v + offset + 1) for v in triangle) + "\n")
                offset += len(hull["vertices"])
        collider = mesh_object("COL_" + piece["id"], piece["collision"], collision_collection)
        collider.display_type = "WIRE"
        collider.hide_set(True)
        models.append((model, collider, piece))
        report.append({"id": piece["id"], "vertices": len(model.data.vertices),
                       "visual_triangles": len(model.data.loop_triangles),
                       "collision_triangles": len(collision["triangles"]),
                       "collision_hulls": len(collision["hulls"]),
                       "glb_bytes": glb_path.stat().st_size})

    backdrop = material("Presentation / backdrop", {"base_color": [0.017,0.025,0.032,1], "metallic": 0, "roughness": 0.9})
    cards = material("Presentation / cards", {"base_color": [0.045,0.063,0.072,1], "metallic": 0, "roughness": 0.85})
    white = material("Presentation / type", {"base_color": [0.85,0.9,0.88,1], "metallic": 0, "roughness": 0.7})
    gray = material("Presentation / secondary", {"base_color": [0.42,0.53,0.57,1], "metallic": 0, "roughness": 0.8})
    from generate import box
    ground = mesh_object("Studio ground", box(65, 52, 0.1, z=-0.25), presentation)
    ground.data.materials.append(backdrop)
    for index, (model, collider, piece) in enumerate(models):
        col, row = index % 6, index // 6
        x, y = (col-2.5)*9, (1-row)*10.5
        model.location = (x,y,0)
        model.rotation_euler.z = math.radians(-25)
        collider.location, collider.rotation_euler = model.location, model.rotation_euler
        card = mesh_object("Tile " + piece["id"], box(8.6, 10, 0.06, x, y, -0.1), presentation)
        card.data.materials.append(cards)
        text_object(f"{index+1:02}  {piece['name'].upper()}", x-3.9, y-3.9, 0.39, white, presentation)
        dimensions = " x ".join(f"{v:g}" for v in piece["dimensions_m"])
        text_object(dimensions + " m", x-3.9, y-4.55, 0.34, gray, presentation)
    text_object("FOUNDRY", -26.4, 18.5, 1.9, white, presentation)
    text_object("18 ORIGINAL MODULAR PIECES  /  2 m MODULE  /  0.5 m SNAP", -26.2, 17.1, 0.48, materials["amber"], presentation)
    text_object("MJOLNIR CORE    /    FORGE PACK 01", -26.2, -17.5, 0.45, materials["amber"], presentation)
    text_object("Actual Blender meshes. Collision hulls preserve door, window and corner openings.", -26.2, -18.3, 0.37, gray, presentation)
    camera_data = bpy.data.cameras.new("Contact sheet camera")
    camera = bpy.data.objects.new("Contact sheet camera", camera_data)
    presentation.objects.link(camera)
    camera.location = (0,-40,58)
    camera.rotation_euler = (Vector((0,0,0))-camera.location).to_track_quat("-Z","Y").to_euler()
    camera_data.type = "ORTHO"
    camera_data.ortho_scale = 58
    scene.camera = camera
    for name, position, energy, size in [("Key",(-18,-12,35),15000,25), ("Fill",(18,5,25),12000,20), ("Rim",(0,20,18),9000,15)]:
        light_data = bpy.data.lights.new(name, "AREA")
        light_data.energy, light_data.shape, light_data.size = energy, "DISK", size
        light = bpy.data.objects.new(name, light_data)
        presentation.objects.link(light)
        light.location = position
        light.rotation_euler = (Vector((0,0,0))-light.location).to_track_quat("-Z","Y").to_euler()
    scene.world.use_nodes = True
    scene.world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.23,0.27,0.3,1)
    scene.world.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.35
    scene.render.engine = "CYCLES"
    scene.cycles.samples = 32
    scene.cycles.use_denoising = True
    scene.render.resolution_x = 2400
    scene.render.resolution_y = 1800
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.filepath = str(output / "foundry-contact-sheet.png")
    scene.view_settings.view_transform = "AgX"
    bpy.ops.wm.save_as_mainfile(filepath=str(output / "foundry.blend"))
    (output / "export-report.json").write_text(json.dumps({"blender": bpy.app.version_string, "pieces": report}, indent=2)+"\n")
    if options.render:
        bpy.ops.render.render(write_still=True)
    print(f"FOUNDRY_BUILD_OK: {len(models)} GLBs, collision exports and {output / 'foundry.blend'}")


if __name__ == "__main__":
    main()
