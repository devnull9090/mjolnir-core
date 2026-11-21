"""Make a separate Blender art revision with vehicle-portal guide lights.

Run with the sealed forerunner_bases.blend open in background Blender.
Pass -- --out <new-folder> and optionally --render for approach comparisons.
"""
import argparse
import json
import sys
from pathlib import Path

import bpy
from mathutils import Matrix, Vector


HERE = Path(__file__).resolve().parent
CENTERS = {"red": (0, 0, 0), "blue": (135, 0, 0), "green": (0, 150, 0)}


def build_module(name, obj, center, x, outward, half_width, clear_x):
    """Project the decal onto the existing pier's evaluated face in metres."""
    world = obj.matrix_world
    local = world.inverted()
    ray = (local.to_3x3() @ Vector((0, -outward, 0))).normalized()
    vertices, faces, slots = [], [], []

    def plate(polygon, material, offset):
        projected = []
        for u, v in polygon:
            px = x + u * half_width
            if px <= clear_x:
                raise ValueError(f"{name} enters the vehicle lane")
            origin = center + Vector((px, outward * 43, 1.42 + v))
            ok, hit, normal, _ = obj.ray_cast(local @ origin, ray)
            if not ok:
                raise ValueError(f"{name} misses {obj.name} at {px:.3f}, {origin.z:.3f}")
            surface = world @ hit
            if abs((world.to_3x3().inverted().transposed() @ normal).normalized().y) < .80:
                raise ValueError(f"{name} touches a bevel or side face")
            # The host is flat here. A few millimetres separate the layers.
            surface.y += outward * offset
            projected.append(tuple(surface - center))
        start = len(vertices)
        vertices.extend(projected)
        ids = tuple(range(start, start + len(projected)))
        faces.append(ids if outward < 0 else tuple(reversed(ids)))
        slots.append(material)

    # Two stepped channels echo the engraving around the arch. Each has
    # its own dark reveal, leaving the original armor visible between them.
    for shift, mat in ((-.32, 1), (.35, 2)):
        profile = [(-.42, -.06), (.04, -.44), (.40, -.44), (.40, -.30),
                   (.11, -.30), (-.21, 0), (.14, .30), (.48, .30),
                   (.48, .44), (.06, .44), (-.42, .07)]
        plate([(shift + u * 1.18, v * 1.25) for u, v in profile], 0, .009)
        plate([(shift + u, v) for u, v in profile], mat, .016)
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    for mat in ("FR • shadow channels", "TEAM • red recessed energy", "FR • cool interior light"):
        mesh.materials.append(bpy.data.materials[mat])
    low = min(v[0] for v in vertices)
    for face, slot in zip(mesh.polygons, slots):
        face.material_index = slot
        if face.normal.y * outward < 0:
            face.flip()
    mesh.update()
    mesh["vehicle_lane_margin_m"] = low - clear_x
    mesh["projection_host"] = obj.name
    return mesh


def add_modules(teams):
    graph = bpy.context.evaluated_depsgraph_get()
    front = build_module("Vehicle guide | front toe", bpy.data.objects[
        "facade/gateway/R rooted foot"].evaluated_get(graph), Vector(CENTERS["red"]),
        11.22, -1, .91, 8.45)
    rear = build_module("Vehicle guide | rear jamb", bpy.data.objects[
        "portal/monolithic outer jamb6"].evaluated_get(graph), Vector(CENTERS["red"]),
        4.65, 1, .96, 2.925)
    outer = build_module("Vehicle guide | citadel outer toe", bpy.data.objects[
        "citadel/R rear gateway toe"].evaluated_get(graph), Vector(CENTERS["green"]),
        12.94, 1, .62, 11.05)
    guides = []
    for team, collection in teams.items():
        modules = [("front", front), ("rear", rear)]
        if team == "green":
            modules.append(("outer rear", outer))
        for entry, mesh in modules:
            for side in (-1, 1):
                ob = bpy.data.objects.new(f"{team} | {entry} vehicle guide {side:+d}", mesh)
                collection.objects.link(ob)
                # Both piers use the same mesh. Blue inherits the master's X reflection.
                sign = -side if team == "blue" else side
                ob.matrix_world = Matrix.Translation(CENTERS[team]) @ Matrix.Diagonal((sign, 1, 1, 1))
                ob.material_slots[1].link = 'OBJECT'
                ob.material_slots[1].material = bpy.data.materials[
                    "FR • cool interior light" if team == "green" else f"TEAM • {team} recessed energy"]
                ob["purpose"] = "Visual vehicle route marking"
                ob["collision"] = "none"
                guides.append(ob)
    bpy.context.view_layer.update()
    return guides


def render_views(scene, teams, guides, out):
    import contextlib
    # Put each base at the review site's origin for identical light and scale.
    collections = list(teams.values())
    originals = {ob: ob.matrix_world.copy() for c in collections for ob in c.objects}
    cam = scene.camera
    scene.render.resolution_x, scene.render.resolution_y = 1100, 560
    scene.render.resolution_percentage = 100
    scene.cycles.samples = 12
    scene.cycles.use_denoising = True
    with contextlib.suppress(RuntimeError, TypeError):
        prefs = bpy.context.preferences.addons['cycles'].preferences
        prefs.compute_device_type = 'OPTIX'
        prefs.refresh_devices()
        gpu = [dev for dev in prefs.devices if dev.type == 'OPTIX']
        if gpu:
            for dev in prefs.devices:
                dev.use = dev in gpu
            scene.cycles.device = 'GPU'
    for team, c in teams.items():
        for other in collections:
            other.hide_render = other != c
        back = Matrix.Translation(-Vector(CENTERS[team]))
        for ob in c.objects:
            ob.matrix_world = back @ originals[ob]
        for direction in ("front", "rear"):
            end = -1 if direction == "front" else 1
            cam.location = (1.8, end * (62 if team == "green" and end == 1 else 50), 4.6)
            cam.rotation_euler = (Vector((0, end * 15, 3.1)) - cam.location).to_track_quat('-Z', 'Y').to_euler()
            cam.data.lens = 36
            for version in (("before", "after") if team == "red" else ("after",)):
                for guide in guides:
                    guide.hide_render = version == "before"
                bpy.context.view_layer.update()
                scene.render.filepath = str(out / f"{team}-{direction}-{version}.png")
                bpy.ops.render.render(write_still=True)
        for ob in c.objects:
            ob.matrix_world = originals[ob]


def export_meshes(guides, out):
    sys.path.insert(0, str(HERE))
    from runtime_visuals import mesh_arrays, write_gltf
    graph = bpy.context.evaluated_depsgraph_get()
    inputs = {}
    for team, center in CENTERS.items():
        by_material = {}
        for guide in guides:
            if guide.name.startswith(team + " |"):
                parts, _ = mesh_arrays(guide, graph, center)
                for key, _, values, triangles in parts:
                    by_material.setdefault(key, []).append((values, triangles))
        inputs[team] = write_gltf("SM_PWR_PortalGuides_" + team.title(), by_material, out)
    return inputs


def main():
    opts = argparse.ArgumentParser(description=__doc__)
    opts.add_argument("--out", required=True, type=Path)
    opts.add_argument("--render", action="store_true")
    args = opts.parse_args(sys.argv[sys.argv.index("--") + 1:])
    if Path(bpy.data.filepath).resolve() != (HERE / "forerunner_bases.blend").resolve():
        raise ValueError("Open the sealed Forerunner bases art scene first")
    scene = bpy.context.scene
    teams = {team: next(c for c in bpy.data.collections if c.name.startswith(prefix))
             for team, prefix in zip(CENTERS, ("01_RED", "02_BLUE", "03_GREEN"))}
    guides = add_modules(teams)
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    preview = out / "forerunner-portal-guides.blend"
    scene["portal_guides"] = "Front and rear vehicle entries, Green outer arcade. Visual-only."
    bpy.ops.wm.save_as_mainfile(filepath=str(preview))
    receipt = {"blender": bpy.app.version_string, "source": str(HERE / "forerunner_bases.blend"),
               "revision": str(preview), "placements": len(guides),
               "meshes": export_meshes(guides, out),
               "modules": {ob.data.name: {"projection_host": ob.data["projection_host"],
                                          "lane_margin_m": ob.data["vehicle_lane_margin_m"]}
                           for ob in guides}}
    (out / "portal-guides.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    if args.render:
        render_views(scene, teams, guides, out)


if __name__ == "__main__":
    main()
