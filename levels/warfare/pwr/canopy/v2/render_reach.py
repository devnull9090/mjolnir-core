"""Blender inspection of handle reach on a locally converted, skinned CE multiplayer Spartan.

Open pwr_insertion.blend and set PWR_SPARTAN_FIT_REFERENCE to the CE biped glTF.
This preview uses its original skin and hand markers. Retail FP/TP grip solving
is tested separately against the actual Mk V Classic shoulder, wrist and finger bones.
"""

import json
import math
import os
from pathlib import Path

import bpy
from mathutils import Matrix, Vector


def point_at(obj, point):
    obj.rotation_euler = (
        (Vector(point) - obj.location).to_track_quat("-Z", "Y").to_euler()
    )


def aim_bone(bone, direction, desired):
    rotation = direction.rotation_difference(desired)
    pivot = Matrix.Translation(bone.head)
    bone.matrix = pivot @ rotation.to_matrix().to_4x4() @ pivot.inverted() @ bone.matrix
    bpy.context.view_layer.update()


def pose(armature, side, sign, marker, handle):
    def joint(name):
        return armature.pose.bones[f"bip01 {side} {name}"]

    shoulder, elbow, wrist = (joint(name) for name in ("upperarm", "forearm", "hand"))
    start, mid, hand = (bone.head.copy() for bone in (shoulder, elbow, wrist))
    palm = marker.matrix_world.translation.copy()
    hand_to_palm = wrist.matrix.inverted() @ palm
    palm_direction = Vector((0.55, 0, 0.835)).normalized()
    wrist_target = handle - palm_direction * (palm - hand).length
    upper, lower = (mid - start).length, (hand - mid).length
    axis = (wrist_target - start).normalized()
    distance = (wrist_target - start).length
    projection = (upper**2 + distance**2 - lower**2) / (2 * distance)
    pole = Vector((-0.065, sign * 0.36, -0.36))
    bend = (pole - axis * pole.dot(axis)).normalized()
    elbow_target = (
        start + axis * projection + bend * math.sqrt(upper**2 - projection**2)
    )

    for bone in (shoulder, elbow, wrist):
        bone.rotation_mode = "QUATERNION"
        bone.keyframe_insert("rotation_quaternion", frame=1)
    aim_bone(shoulder, mid - start, elbow_target - start)
    aim_bone(elbow, wrist.head - elbow.head, wrist_target - elbow.head)
    aim_bone(wrist, (wrist.matrix @ hand_to_palm) - wrist.head, palm_direction)
    for bone in (shoulder, elbow, wrist):
        bone.keyframe_insert("rotation_quaternion", frame=9)
    error = ((wrist.matrix @ hand_to_palm) - handle).length
    if error > 0.002:
        raise ValueError(f"{side} hand marker missed its grip by {error:.4f} m")


def render():
    scene = bpy.context.scene
    reference = Path(os.environ["PWR_SPARTAN_FIT_REFERENCE"])
    existing = set(scene.objects)
    bpy.ops.import_scene.gltf(filepath=str(reference))
    added = set(scene.objects) - existing
    armature = next(o for o in added if o.type == "ARMATURE")
    report = Path(__file__).with_name("geometry-report.json")
    sockets = json.loads(report.read_text())["grip_sockets_ue_cm"]
    for side, name, sign in (("l", "left", 1), ("r", "right", -1)):
        marker = next(o for o in added if o.name.startswith("marker_" + name + " hand"))
        # The neutral reference armature has +Y left. UE has +Y right.
        forward, right, up = sockets["grip_" + side]
        handle = Vector((forward, -right, up)) / 100
        pose(armature, side, sign, marker, handle)
    armature.matrix_world = (
        Matrix.Rotation(-math.pi / 2, 4, "Z") @ armature.matrix_world
    )
    scene.frame_set(9)
    scene.frame_start, scene.frame_end = 1, 24
    scene.render.fps = 24
    scene.timeline_markers.new("Free hands", frame=1)
    scene.timeline_markers.new("Hands on steering loops", frame=9)
    for o in added:
        if o.type == "MESH" and "cyborg" not in o.name:
            o.hide_render = True
    # The CE source material uses its texture for the armor and a gold visor on its separate slot.
    for mat in bpy.data.materials:
        if "cyborg_shaders" not in mat.name or not mat.use_nodes:
            continue
        shader = next(n for n in mat.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
        if "visor" in mat.name:
            for link in list(shader.inputs["Base Color"].links):
                mat.node_tree.links.remove(link)
            shader.inputs["Base Color"].default_value = (0.45, 0.19, 0.035, 1)
            shader.inputs["Roughness"].default_value = 0.23
            shader.inputs["Metallic"].default_value = 0.82
        elif "armor" in mat.name and shader.inputs["Base Color"].is_linked:
            tex = shader.inputs["Base Color"].links[0].from_socket
            tint = mat.node_tree.nodes.new("ShaderNodeMixRGB")
            tint.blend_type = "MULTIPLY"
            tint.inputs[0].default_value = 0.64
            tint.inputs[2].default_value = (0.25, 0.34, 0.17, 1)
            mat.node_tree.links.new(tex, tint.inputs[1])
            mat.node_tree.links.new(tint.outputs[0], shader.inputs["Base Color"])
            shader.inputs["Metallic"].default_value = 0.36
            shader.inputs["Roughness"].default_value = 0.49
        for link in list(shader.inputs["Alpha"].links):
            mat.node_tree.links.remove(link)
        shader.inputs["Alpha"].default_value = 1

    scene.world = bpy.data.worlds.new("Fit review studio")
    scene.world.use_nodes = True
    scene.world.node_tree.nodes["Background"].inputs[0].default_value = (
        0.10,
        0.13,
        0.14,
        1,
    )
    for position, energy, size in [
        ((-4, -6, 8), 720, 5),
        ((4, -3, 4), 420, 3),
        ((2, 3, 6), 1300, 4),
    ]:
        bpy.ops.object.light_add(type="AREA", location=position)
        light = bpy.context.object
        light.data.energy, light.data.size = energy, size
        point_at(light, (0, 0, 2.4))
    bpy.ops.object.camera_add()
    camera = bpy.context.object
    scene.camera = camera
    camera.data.type = "ORTHO"
    scene.cycles.samples = 24
    output = Path(__file__).resolve().parents[5] / "out/pwr/chute-v2"
    output.mkdir(parents=True, exist_ok=True)
    for name, target, direction, width, size in [
        ("ce-spartan-deployed", (0, 0, 2.91), (0.20, -1, 0.27), 7.06, (1100, 960)),
        ("ce-spartan-grips", (0, -0.03, 1.78), (0.18, -1, 0.10), 1.62, (950, 750)),
    ]:
        camera.location = Vector(target) + Vector(direction) * 9
        point_at(camera, target)
        camera.data.ortho_scale = width
        scene.render.resolution_x, scene.render.resolution_y = size
        scene.render.resolution_percentage = 100
        scene.render.filepath = str(output / (name + ".png"))
        bpy.ops.render.render(write_still=True)
    bpy.ops.wm.save_as_mainfile(
        filepath=str(output / "spartan-reach-review.blend"), compress=True
    )


if __name__ == "__main__":
    render()
