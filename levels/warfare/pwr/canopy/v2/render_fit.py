"""Render the rig alongside the locally installed Mk V Classic LOD0 for fit review.

Reads the reference export and generated blend. Product meshes contain no Spartan geometry.
"""

import bpy, math
from pathlib import Path
from mathutils import Vector, Matrix

ROOT = Path(__file__).resolve().parents[5]
OUT = ROOT / "out/pwr/chute-v2"


def render():
    scene = bpy.context.scene
    # Run immediately after authoring, or open pwr_insertion.blend before this script.
    from_objects = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=str(OUT / "Spartan.glb"))
    bpy.context.view_layer.update()
    ref = [
        o
        for o in bpy.data.objects
        if o not in from_objects and o.type == "MESH" and "LOD0" in o.name
    ][0]
    ref.matrix_world = Matrix.Rotation(-math.pi / 2, 4, "Z") @ ref.matrix_world
    armor = bpy.data.materials.new("Fit reference • Mk V Classic")
    armor.diffuse_color = (0.18, 0.215, 0.165, 1)
    armor.use_nodes = True
    armor.node_tree.nodes["Principled BSDF"].inputs[
        "Base Color"
    ].default_value = armor.diffuse_color
    armor.node_tree.nodes["Principled BSDF"].inputs["Metallic"].default_value = 0.5
    ref.data.materials.clear()
    ref.data.materials.append(armor)
    scene.world = bpy.data.worlds.new("Inspection studio")
    scene.world.use_nodes = True
    scene.world.node_tree.nodes["Background"].inputs[0].default_value = (
        0.175,
        0.19,
        0.205,
        1,
    )
    scene.world.node_tree.nodes["Background"].inputs[1].default_value = 0.55

    def look(o, target):
        o.rotation_euler = (
            (Vector(target) - o.location).to_track_quat("-Z", "Y").to_euler()
        )

    for pos, watts, size, col in [
        ((-4, -5, 8), 800, 5, (1, 0.94, 0.79)),
        ((4, -3, 6), 550, 4, (0.77, 0.86, 1)),
        ((1, 3, 7), 1250, 3, (1, 0.9, 0.69)),
    ]:
        bpy.ops.object.light_add(type="AREA", location=pos)
        light = bpy.context.object
        light.data.energy = watts
        light.data.shape = "DISK"
        light.data.size = size
        light.data.color = col
        look(light, (0, 0, 2.5))
    bpy.ops.object.camera_add()
    cam = bpy.context.object
    scene.camera = cam
    scene.render.engine = "CYCLES"
    scene.cycles.samples = 24
    scene.cycles.use_denoising = True
    scene.render.resolution_percentage = 100

    def shot(name, at, direction, width, res):
        cam.location = Vector(at) + Vector(direction) * 10
        look(cam, at)
        cam.data.type = "ORTHO"
        cam.data.ortho_scale = width
        scene.render.resolution_x, scene.render.resolution_y = res
        scene.render.filepath = str(OUT / (name + ".png"))
        bpy.ops.render.render(write_still=True)

    def show(group, val):
        for o in bpy.data.collections[group].objects:
            o.hide_render = not val

    show("pack", False)
    ref.hide_render = True
    shot("canopy-front", (0, 0, 3.69), (0, -1, 0.49), 6.5, (1152, 815))
    ref.hide_render = False
    show("pack", True)
    shot("spartan-fit", (0, 0, 2.89), (0.22, -1, 0.28), 7.05, (1100, 960))
    show("wing", False)
    show("rig", False)
    shot("pack-fit", (0, 0.05, 1.40), (0.58, 1, 0.20), 1.66, (860, 920))
    ref.hide_render = True
    shot("pack-detail", (0, 0.33, 1.52), (0.55, 1, 0.21), 0.92, (700, 770))
    print("Saved studio renders", OUT)


if __name__ == "__main__":
    render()
