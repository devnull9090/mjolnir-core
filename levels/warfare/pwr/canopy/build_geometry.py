"""Generate the original PWR cosmetic parachute in Blender; no collision.

All geometry uses metres, Z up, with the player actor origin at (0, 0, 0).
The exported glTF has baked transforms and one mesh with two opaque materials.
"""
import argparse
import json
import math
from pathlib import Path
import sys

import bpy
from mathutils import Vector


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument("--preview", type=Path)
    args = parser.parse_args(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else [])
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)

    def material(name, color):
        mat = bpy.data.materials.new(name)
        mat.diffuse_color = (*color, 1)
        mat.use_nodes = True
        bsdf = mat.node_tree.nodes.get("Principled BSDF")
        bsdf.inputs["Base Color"].default_value = (*color, 1)
        bsdf.inputs["Roughness"].default_value = .86
        return mat

    fabric = material("Canopy", (.16, .22, .11))
    cords = material("Cords", (.06, .07, .055))
    segments, rings = 32, 6
    vertices, faces = [], []
    # An open crown vent and shallow scallops make the simple cloth readable.
    for j in range(rings):
        theta = .065 + (math.pi / 2 - .065) * j / (rings - 1)
        for i in range(segments):
            angle = math.tau * i / segments
            scallop = .04 * math.cos(angle * 8) * (j / (rings - 1)) ** 3
            vertices.append((2.05 * math.sin(theta) * math.cos(angle),
                             1.5 * math.sin(theta) * math.sin(angle),
                             3.05 + 1.15 * math.cos(theta) + scallop))
    for j in range(rings - 1):
        for i in range(segments):
            a, b = j * segments + i, j * segments + (i + 1) % segments
            faces.append((a, a + segments, b + segments, b))
    mesh = bpy.data.meshes.new("PWR_CanopyCloth")
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    canopy = bpy.data.objects.new("PWR_CanopyCloth", mesh)
    bpy.context.collection.objects.link(canopy)
    mesh.materials.append(fabric)
    bpy.context.view_layer.objects.active = canopy
    canopy.select_set(True)
    shell = canopy.modifiers.new("Opaque cloth underside", "SOLIDIFY")
    shell.thickness = .012
    bpy.ops.object.modifier_apply(modifier=shell.name)
    for face in canopy.data.polygons:
        face.use_smooth = True

    def cord(start, end):
        delta = Vector(end) - Vector(start)
        bpy.ops.mesh.primitive_cylinder_add(vertices=6, radius=.012, depth=delta.length,
                                           location=(Vector(start) + Vector(end)) * .5)
        obj = bpy.context.object
        obj.name = "PWR_SuspensionCord"
        obj.rotation_euler = delta.to_track_quat("Z", "Y").to_euler()
        obj.data.materials.append(cords)

    # Eight visible suspension lines converge at the shoulders. These are only
    # visuals; the native fall-control implementation owns the movement.
    for i in range(8):
        angle = math.tau * i / 8
        top = (2.05 * math.cos(angle), 1.5 * math.sin(angle), 3.09)
        bottom = (.20 if math.cos(angle) >= 0 else -.20,
                  .14 if math.sin(angle) >= 0 else -.14, 1.30)
        cord(bottom, top)
    bpy.ops.object.select_all(action="SELECT")
    bpy.context.view_layer.objects.active = canopy
    bpy.ops.object.join()
    canopy.name = "SM_PWR_Parachute"
    bpy.context.scene.cursor.location = (0, 0, 0)
    bpy.ops.object.origin_set(type="ORIGIN_CURSOR")
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.smart_project(angle_limit=math.radians(66), island_margin=.01)
    bpy.ops.object.mode_set(mode="OBJECT")
    canopy.data.calc_loop_triangles()
    geometry = {
        "authoring_units": "metres; Z up; biped actor origin at zero",
        "vertices": len(canopy.data.vertices), "triangles": len(canopy.data.loop_triangles),
        "materials": [m.name for m in canopy.data.materials],
        "collision": False, "original_geometry": True,
        "bounds_m": {
            "min": [min(v.co[i] for v in canopy.data.vertices) for i in range(3)],
            "max": [max(v.co[i] for v in canopy.data.vertices) for i in range(3)],
        },
    }
    (output / "geometry-report.json").write_text(json.dumps(geometry, indent=2) + "\n")
    bpy.ops.wm.save_as_mainfile(filepath=str(output / "pwr_canopy.blend"))
    bpy.ops.export_scene.gltf(filepath=str(output / "pwr_canopy.gltf"),
                              export_format="GLTF_SEPARATE", use_selection=True,
                              export_apply=True, export_yup=True, export_materials="EXPORT")
    print("PWR CANOPY:", json.dumps(geometry))
    if args.preview:
        # The preview is deliberately separate from the saved/exported asset.
        scene = bpy.context.scene
        scene.render.engine = "CYCLES"
        scene.cycles.samples = 24
        scene.world.color = (.24, .28, .34)
        bpy.ops.object.light_add(type="AREA", location=(3, -4, 7))
        bpy.context.object.data.energy = 900
        bpy.context.object.data.shape = "DISK"
        bpy.context.object.data.size = 5
        bpy.ops.object.camera_add(location=(6.5, -8, 4.5))
        camera = bpy.context.object
        camera.rotation_euler = (Vector((0, 0, 2.75)) - camera.location).to_track_quat("-Z", "Y").to_euler()
        camera.data.type = "ORTHO"
        camera.data.ortho_scale = 5.6
        scene.camera = camera
        scene.render.resolution_x = 800
        scene.render.resolution_y = 800
        scene.render.resolution_percentage = 100
        args.preview.parent.mkdir(parents=True, exist_ok=True)
        scene.render.filepath = str(args.preview.resolve())
        bpy.ops.render.render(write_still=True)


if __name__ == "__main__":
    main()
