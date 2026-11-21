"""Blender-only presentation stage for the Forerunner base art review.

Call ``stage_scene(api)`` after building a base at the origin. Nothing in this
module exports, launches the game, or changes gameplay assets. The stock pine
and Warthog are existing local reference assets; tree copies share mesh data.
The module has no execution side effects when imported.
"""
from pathlib import Path
import math
import random

import bpy
from mathutils import Matrix, Vector, noise


ROOT = Path(__file__).resolve().parents[4]
PINE = ROOT / "out/pwr/visual-v5/outcrops-v4/trees/mature-pine-a.glb"
STOCK_TEXTURES = Path("C:/haloce/ce_conversions/release11/DCN/staging/textures")
GRASS = STOCK_TEXTURES / "levels_a30_bitmaps_detail_grass.png"
DIRT = STOCK_TEXTURES / "levels_a30_bitmaps_detail_ground.png"
PINE_TEXTURES = ROOT / "out/pwr/visual-v5/outcrops-v4/trees/assets"
WARTHOG = Path("C:/haloce/ce_conversions/release11/DCN/staging/models/vehicles_warthog_mp_warthog__vehi.gltf")
OWNER = "pwr_base_art_stage_v1"


def _collection(name):
    col = bpy.data.collections.get(name)
    if col is None:
        col = bpy.data.collections.new(name)
    if col.name not in bpy.context.scene.collection.children:
        bpy.context.scene.collection.children.link(col)
    col["presentation_only"] = True
    return col


def _own(obj, col):
    for old in list(obj.users_collection):
        old.objects.unlink(obj)
    col.objects.link(obj)
    obj["presentation_only"] = True
    obj["stage_owner"] = OWNER
    return obj


def _mesh(name, vertices, faces, col, material=None):
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    _own(obj, col)
    if material:
        mesh.materials.append(material)
    for polygon in mesh.polygons:
        polygon.use_smooth = True
    return obj


def _height(x, y):
    """Flat authored pad; small rolling banks outside the review architecture."""
    distance = max(abs(x) - 56.0, abs(y) - 48.0, 0.0)
    transition = min(distance / 60.0, 1.0)
    transition = transition * transition * (3.0 - 2.0 * transition)
    detail = noise.fractal(Vector((x * .013, y * .013, 4.8)), .85, 2.0, 4.0)
    rise = 4.5 + 5.0 * detail + 2.0 * math.sin(x * .012 + y * .008)
    # The entrance road remains a shallow drivable valley into the distance.
    valley = 1.0 - .8 * math.exp(-(x / 15.0) ** 2) if y < -26 else 1.0
    return -.16 + transition * max(.3, rise) * valley


def _ground_material():
    mat = bpy.data.materials.new("PWR presentation meadow and approach")
    mat.use_nodes = True
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    bsdf = nodes.get("Principled BSDF")
    bsdf.inputs["Roughness"].default_value = .93
    geo = nodes.new("ShaderNodeNewGeometry")
    xyz = nodes.new("ShaderNodeSeparateXYZ")
    links.new(geo.outputs["Position"], xyz.inputs[0])

    def math_node(operation, a=None, b=None):
        n = nodes.new("ShaderNodeMath")
        n.operation = operation
        for i, value in enumerate((a, b)):
            if value is not None:
                if isinstance(value, (float, int)):
                    n.inputs[i].default_value = value
                else:
                    links.new(value, n.inputs[i])
        return n.outputs[0]

    broad = nodes.new("ShaderNodeTexNoise")
    broad.inputs["Scale"].default_value = .31
    broad.inputs["Detail"].default_value = 3.0
    links.new(geo.outputs["Position"], broad.inputs["Vector"])
    ramp = nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].color = (.58, .54, .40, 1)
    ramp.color_ramp.elements[1].color = (.82, .78, .62, 1)
    links.new(broad.outputs["Fac"], ramp.inputs[0])
    meadow_color = ramp.outputs["Color"]
    if GRASS.is_file():
        tex = nodes.new("ShaderNodeTexImage")
        tex.image = bpy.data.images.load(str(GRASS), check_existing=True)
        mapping = nodes.new("ShaderNodeVectorMath")
        mapping.operation = "SCALE"
        mapping.inputs[3].default_value = .85
        links.new(geo.outputs["Position"], mapping.inputs[0])
        links.new(mapping.outputs[0], tex.inputs["Vector"])
        mix = nodes.new("ShaderNodeMixRGB")
        mix.blend_type = "MULTIPLY"
        mix.inputs[0].default_value = 1.0
        links.new(ramp.outputs["Color"], mix.inputs[1])
        links.new(tex.outputs["Color"], mix.inputs[2])
        earth_tint = nodes.new("ShaderNodeHueSaturation")
        earth_tint.inputs["Saturation"].default_value = .70
        earth_tint.inputs["Value"].default_value = .72
        links.new(mix.outputs[0], earth_tint.inputs["Color"])
        meadow_color = earth_tint.outputs["Color"]

    # Irregular soft shoulder edges on a ten-metre-wide approach.
    half_width = math_node("ADD", math_node("MULTIPLY", broad.outputs["Fac"], 1.2), 4.3)
    shoulder = math_node("SUBTRACT", half_width, math_node("ABSOLUTE", xyz.outputs["X"]))
    feather = nodes.new("ShaderNodeMapRange")
    feather.inputs["From Min"].default_value = -.14
    feather.inputs["From Max"].default_value = .12
    feather.clamp = True
    links.new(shoulder, feather.inputs["Value"])
    front = math_node("LESS_THAN", xyz.outputs["Y"], -25.0)
    road_mask = math_node("MULTIPLY", feather.outputs["Result"], front)
    road_color = nodes.new("ShaderNodeValToRGB")
    road_color.color_ramp.elements[0].color = (.095, .066, .037, 1)
    road_color.color_ramp.elements[1].color = (.18, .132, .077, 1)
    links.new(broad.outputs["Fac"], road_color.inputs[0])
    dirt_color = road_color.outputs["Color"]
    if DIRT.is_file():
        soil_tex = nodes.new("ShaderNodeTexImage")
        soil_tex.image = bpy.data.images.load(str(DIRT), check_existing=True)
        soil_scale = nodes.new("ShaderNodeVectorMath")
        soil_scale.operation = "SCALE"
        soil_scale.inputs[3].default_value = 1.6
        links.new(geo.outputs["Position"], soil_scale.inputs[0])
        links.new(soil_scale.outputs[0], soil_tex.inputs["Vector"])
        soil_mix = nodes.new("ShaderNodeMixRGB")
        soil_mix.blend_type = "MULTIPLY"
        soil_mix.inputs[0].default_value = .75
        links.new(road_color.outputs["Color"], soil_mix.inputs[1])
        links.new(soil_tex.outputs["Color"], soil_mix.inputs[2])
        dirt_color = soil_mix.outputs[0]
    surface = nodes.new("ShaderNodeMixRGB")
    links.new(road_mask, surface.inputs[0])
    links.new(meadow_color, surface.inputs[1])
    links.new(dirt_color, surface.inputs[2])
    rut = math_node("LESS_THAN", math_node("ABSOLUTE", math_node("SUBTRACT", math_node("ABSOLUTE", xyz.outputs["X"]), 1.22)), .27)
    rut = math_node("MULTIPLY", rut, road_mask)
    rut_mix = nodes.new("ShaderNodeMixRGB")
    links.new(math_node("MULTIPLY", rut, .22), rut_mix.inputs[0])
    links.new(surface.outputs[0], rut_mix.inputs[1])
    rut_mix.inputs[2].default_value = (.075, .055, .032, 1)
    links.new(rut_mix.outputs[0], bsdf.inputs["Base Color"])
    fine = nodes.new("ShaderNodeTexNoise")
    fine.inputs["Scale"].default_value = 32
    fine.inputs["Detail"].default_value = 2
    links.new(geo.outputs["Position"], fine.inputs["Vector"])
    bump = nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = .3
    bump.inputs["Distance"].default_value = .035
    links.new(surface.outputs[0], bump.inputs["Height"])
    links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    return mat


def _import_templates(path):
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=str(path))
    imported = set(bpy.data.objects) - before
    parts = [(ob.data, ob.matrix_world.copy()) for ob in imported if ob.type == "MESH"]
    for ob in imported:
        bpy.data.objects.remove(ob, do_unlink=True)
    return parts


def _forest(env):
    if not PINE.is_file():
        return {"trees": 0, "warning": "No real pine source present; omitted forest."}
    templates = _import_templates(PINE)
    # COLOR_0 is an Unreal wind/layer mask, not visible vertex paint. The glTF
    # importer multiplies it into albedo by default, yielding purple needles
    # and yellow bark. Use the original albedo/UV0 directly for presentation.
    for mesh, _basis in templates:
        for index, original in enumerate(list(mesh.materials)):
            needles = "Branch" in original.name
            mat = bpy.data.materials.new("PWR presentation pine needles" if needles else "PWR presentation pine bark")
            mat.use_nodes = True
            nodes, links = mat.node_tree.nodes, mat.node_tree.links
            bsdf = nodes.get("Principled BSDF")
            bsdf.inputs["Roughness"].default_value = .87
            bsdf.inputs["Metallic"].default_value = 0
            bsdf.inputs["Specular IOR Level"].default_value = .20
            tex = nodes.new("ShaderNodeTexImage")
            tex.image = bpy.data.images.load(str(PINE_TEXTURES / ("needle-albedo.png" if needles else "bark-albedo.png")), check_existing=True)
            uv = nodes.new("ShaderNodeUVMap")
            uv.uv_map = mesh.uv_layers[0].name
            links.new(uv.outputs["UV"], tex.inputs["Vector"])
            shade = nodes.new("ShaderNodeHueSaturation")
            shade.inputs["Saturation"].default_value = .78 if needles else .62
            shade.inputs["Value"].default_value = .62 if needles else .58
            links.new(tex.outputs["Color"], shade.inputs["Color"])
            links.new(shade.outputs["Color"], bsdf.inputs["Base Color"])
            mesh.materials[index] = mat
    rng = random.Random(74021)
    locations = []
    # Tight irregular groves with clearings, rather than isolated orchard rows.
    groves = [(-105, 65, 18, 21), (-68, 112, 23, 19), (-25, 125, 25, 20),
              (28, 105, 19, 22), (77, 98, 23, 19), (113, 54, 16, 25)]
    for cx, cy, rx, ry in groves:
        placed = 0
        for _attempt in range(150):
            angle, radius = rng.uniform(0, math.tau), math.sqrt(rng.random())
            x, y = cx + rx * radius * math.cos(angle), cy + ry * radius * math.sin(angle)
            if any((x - px) ** 2 + (y - py) ** 2 < 4.8 ** 2 for px, py in locations):
                continue
            locations.append((x, y))
            placed += 1
            if placed == 11:
                break
    for index, (x, y) in enumerate(locations):
        scale = rng.uniform(.57, .90)
        # The source includes roots extending below its authored zero datum.
        transform = Matrix.Translation((x, y, _height(x, y))) @ Matrix.Rotation(rng.uniform(0, math.tau), 4, "Z") @ Matrix.Scale(scale, 4)
        for part, (mesh, basis) in enumerate(templates):
            obj = bpy.data.objects.new(f"PWR native pine {index:03d}.{part}", mesh)
            _own(obj, env)
            obj.matrix_world = transform @ basis
    return {"trees": len(locations), "source": str(PINE), "mesh_data_shared": True}


def import_warthog(position=(0, -34, .03), heading=-math.pi / 2):
    """Import the original textured Warthog as a presentation-only scale reference.

    glTF axis conversion is left to Blender's importer. ``position.z`` is the
    tyre contact height; +X vehicle forward is rotated toward -Y by default.
    """
    if not WARTHOG.is_file():
        return None
    presentation = _collection("Presentation")
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=str(WARTHOG))
    imported = set(bpy.data.objects) - before
    root = bpy.data.objects.new("Warthog | original geometry scale reference", None)
    _own(root, presentation)
    for obj in imported:
        _own(obj, presentation)
        if obj.parent is None:
            matrix = obj.matrix_world.copy()
            obj.parent = root
            obj.matrix_world = matrix
    root.rotation_euler.z = heading
    bpy.context.view_layer.update()
    points, tyre_points = [], []
    depsgraph = bpy.context.evaluated_depsgraph_get()
    for ob in imported:
        if ob.type != "MESH":
            continue
        evaluated = ob.evaluated_get(depsgraph)
        mesh = evaluated.to_mesh()
        try:
            world_vertices = [evaluated.matrix_world @ v.co for v in mesh.vertices]
            points.extend(world_vertices)
            tire_slots = {i for i, mat in enumerate(mesh.materials) if mat and "tire" in mat.name.lower()}
            tire_indices = {index for polygon in mesh.polygons if polygon.material_index in tire_slots for index in polygon.vertices}
            tyre_points.extend(world_vertices[i] for i in tire_indices)
        finally:
            evaluated.to_mesh_clear()
    if points:
        centre_x = (min(v.x for v in points) + max(v.x for v in points)) * .5
        centre_y = (min(v.y for v in points) + max(v.y for v in points)) * .5
        root.location = (position[0] - centre_x, position[1] - centre_y, position[2] - min(v.z for v in (tyre_points or points)))
    else:
        root.location = position
    root["source_gltf"] = str(WARTHOG)
    root["original_materials_retained"] = True
    root["tyre_contact_height"] = position[2]
    root["evaluated_tyre_vertex_count"] = len(tyre_points)
    return root


def _lighting(presentation):
    scene = bpy.context.scene
    world = bpy.data.worlds.new("PWR base art daylight")
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs["Color"].default_value = (.54, .67, .86, 1)
    world.node_tree.nodes["Background"].inputs["Strength"].default_value = .45
    scene.world = world
    data = bpy.data.lights.new("PWR afternoon sun", "SUN")
    data.energy = 2.7
    data.angle = math.radians(1.3)
    data.color = (1.0, .94, .83)
    sun = _own(bpy.data.objects.new(data.name, data), presentation)
    sun.location = (-70, -95, 135)
    sun.rotation_euler = (Vector((0, 0, 0)) - sun.location).to_track_quat("-Z", "Y").to_euler()
    data = bpy.data.lights.new("PWR broad camera fill", "AREA")
    data.energy = 2600
    data.shape = "DISK"
    data.size = 65
    data.color = (.74, .84, 1.0)
    fill = _own(bpy.data.objects.new(data.name, data), presentation)
    fill.location = (35, -75, 65)
    fill.rotation_euler = (Vector((0, 0, 6)) - fill.location).to_track_quat("-Z", "Y").to_euler()
    scene.view_settings.view_transform = "AgX"


def stage_scene(api=None, include_vehicle=True, include_forest=True):
    """Add the meadow stage and hero camera, preserving all base collections.

    ``api`` is accepted for the base builder's shared interface, but the stage
    deliberately manages only its own Env/Presentation objects. Repeated calls
    replace only objects bearing this module's ownership tag.
    """
    for obj in list(bpy.data.objects):
        if obj.get("stage_owner") == OWNER:
            bpy.data.objects.remove(obj, do_unlink=True)
    env = _collection("Env")
    presentation = _collection("Presentation")
    steps, extent = 160, 280.0
    vertices = []
    for j in range(steps + 1):
        y = -extent + 2 * extent * j / steps
        for i in range(steps + 1):
            x = -extent + 2 * extent * i / steps
            vertices.append((x, y, _height(x, y)))
    faces = []
    row = steps + 1
    for j in range(steps):
        for i in range(steps):
            a = j * row + i
            faces.append((a, a + 1, a + row + 1, a + row))
    terrain = _mesh("PWR presentation meadow | not gameplay terrain", vertices, faces, env, _ground_material())
    forest_receipt = _forest(env) if include_forest else {"trees": 0}
    vehicle = import_warthog() if include_vehicle else None
    _lighting(presentation)
    data = bpy.data.cameras.new("PWR base hero camera")
    camera = _own(bpy.data.objects.new(data.name, data), presentation)
    camera.location = (102, -158, 84)
    camera.rotation_euler = (Vector((0, 0, 7)) - camera.location).to_track_quat("-Z", "Y").to_euler()
    data.lens = 50
    data.clip_end = 2000
    bpy.context.scene.camera = camera
    bpy.context.view_layer.update()
    return {"environment": env, "presentation": presentation, "terrain": terrain,
            "camera": camera, "vehicle": vehicle, "forest": forest_receipt}
