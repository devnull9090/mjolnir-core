"""Author the cosmetic PWR ram-air canopy for the fork-compatible Unreal cook."""
import hashlib
import json
import math
import struct
from pathlib import Path

import unreal


REPO = Path(__file__).resolve().parents[3]
SOURCE = REPO / "levels/warfare/pwr/canopy/v2"
OUTPUT = REPO / "out/pwr/canopy-v2"
FOLDER = "/Game/MJOLNIR/Insertion/PWR"
MATERIAL_FOLDER = FOLDER + "/CanopyV2"
NAME = "SM_PWR_ParachuteV2"
SLOTS = {"Canopy", "Tip", "Binding", "Webbing", "Line", "Metal", "Toggle", "Mark", "GripTextile"}
library = unreal.EditorAssetLibrary
assets = unreal.AssetToolsHelpers.get_asset_tools()
materials = unreal.MaterialEditingLibrary


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def asset(name, folder, cls, factory):
    existing = unreal.load_asset(folder + "/" + name)
    if existing is not None:
        if not isinstance(existing, cls):
            raise ValueError(f"Unexpected asset class for {folder}/{name}")
        return existing
    return assets.create_asset(name, folder, cls, factory)


def weave_texture():
    # A 56 mm repeat contains eight reinforced ripstop cells over individual
    # alternating threads. Mipmaps average the weave naturally at distance.
    size = 256
    pixels = bytearray()
    for v in range(size):
        for u in range(size):
            warp = math.cos(math.tau * u / 4)
            weft = math.cos(math.tau * v / 4)
            thread = warp if (u // 4 + v // 4) % 2 else weft
            rib = max((.5 + .5 * math.cos(math.tau * t / 32)) ** 28 for t in (u, v))
            reflectance = .958 + .022 * thread - .085 * rib
            finish = .51 + .14 * thread - .22 * rib
            pixels.extend((0, round(255 * finish), round(255 * reflectance)))
    OUTPUT.mkdir(exist_ok=True, parents=True)
    path = OUTPUT / "T_PWR_Ripstop.tga"
    header = struct.pack("<BBBHHBHHHHBB", 0, 0, 2, 0, 0, 0, 0, 0, size, size, 24, 32)
    path.write_bytes(header + pixels)
    task = unreal.AssetImportTask()
    task.set_editor_properties({"filename": str(path), "destination_path": MATERIAL_FOLDER,
                                "destination_name": path.stem, "automated": True,
                                "replace_existing": True, "save": False})
    assets.import_asset_tasks([task])
    texture = unreal.load_asset(MATERIAL_FOLDER + "/" + path.stem)
    texture.set_editor_properties({"srgb": False, "compression_settings": unreal.TextureCompressionSettings.TC_MASKS,
                                   "address_x": unreal.TextureAddress.TA_WRAP, "address_y": unreal.TextureAddress.TA_WRAP})
    library.save_loaded_asset(texture)
    return texture


def make_materials(recipes, texture):
    master = asset("M_PWR_CanopyFabric", MATERIAL_FOLDER, unreal.Material, unreal.MaterialFactoryNew())
    master.set_editor_properties({"two_sided": True, "used_with_static_lighting": False})
    materials.delete_all_material_expressions(master)
    def node(cls, **props):
        expression = materials.create_material_expression(master, cls)
        expression.set_editor_properties(props)
        return expression

    def connect(source, pin, dest, target):
        if not materials.connect_material_expressions(source, pin, dest, target):
            raise RuntimeError(f"Could not connect fabric shader input {target}")

    tint = node(unreal.MaterialExpressionVectorParameter, parameter_name="Tint")
    roughness = node(unreal.MaterialExpressionScalarParameter, parameter_name="Roughness")
    metallic = node(unreal.MaterialExpressionScalarParameter, parameter_name="Metallic")
    weave = node(unreal.MaterialExpressionScalarParameter, parameter_name="FabricWeight")
    uv = node(unreal.MaterialExpressionTextureCoordinate, coordinate_index=1)
    sample = node(unreal.MaterialExpressionTextureSample, texture=texture,
                  sampler_type=unreal.MaterialSamplerType.SAMPLERTYPE_MASKS)
    connect(uv, "", sample, "UVs")
    variation = node(unreal.MaterialExpressionLinearInterpolate, const_a=1)
    connect(sample, "R", variation, "B")
    connect(weave, "", variation, "Alpha")
    color = node(unreal.MaterialExpressionMultiply)
    connect(tint, "", color, "A")
    connect(variation, "", color, "B")
    centered = node(unreal.MaterialExpressionSubtract, const_b=.5)
    connect(sample, "G", centered, "A")
    strength = node(unreal.MaterialExpressionMultiply, const_b=.24)
    connect(weave, "", strength, "A")
    relief = node(unreal.MaterialExpressionMultiply)
    connect(centered, "", relief, "A")
    connect(strength, "", relief, "B")
    finish = node(unreal.MaterialExpressionAdd)
    connect(roughness, "", finish, "A")
    connect(relief, "", finish, "B")
    for expr, prop in ((color, unreal.MaterialProperty.MP_BASE_COLOR), (finish, unreal.MaterialProperty.MP_ROUGHNESS),
                       (metallic, unreal.MaterialProperty.MP_METALLIC)):
        if not materials.connect_material_property(expr, "", prop):
            raise RuntimeError(f"Could not connect fabric shader output {prop}")
    materials.recompile_material(master)
    library.save_loaded_asset(master)
    result = {}
    for name, recipe in recipes.items():
        instance = asset("MI_PWR_Chute_" + name, MATERIAL_FOLDER, unreal.MaterialInstanceConstant,
                         unreal.MaterialInstanceConstantFactoryNew())
        materials.set_material_instance_parent(instance, master)
        materials.set_material_instance_vector_parameter_value(instance, "Tint",
            unreal.LinearColor(*recipe.get("baseColorFactor", [1, 1, 1, 1])))
        materials.set_material_instance_scalar_parameter_value(instance, "Roughness", recipe.get("roughnessFactor", 1))
        materials.set_material_instance_scalar_parameter_value(instance, "Metallic", recipe.get("metallicFactor", 1))
        materials.set_material_instance_scalar_parameter_value(instance, "FabricWeight",
            {"Canopy": 1, "Tip": 1, "Binding": .7, "Webbing": .85}.get(name, 0))
        materials.update_material_instance(instance)
        library.save_loaded_asset(instance)
        result[name] = instance
    return master, result


def accessor(document, data, index):
    a = document["accessors"][index]
    view = document["bufferViews"][a["bufferView"]]
    width = {"VEC3": 3, "VEC2": 2, "SCALAR": 1}[a["type"]]
    fmt = {5121: "B", 5123: "H", 5125: "I", 5126: "f"}[a["componentType"]]
    row = struct.Struct("<" + fmt * width)
    offset = a.get("byteOffset", 0) + view.get("byteOffset", 0)
    stride = view.get("byteStride", row.size)
    return [row.unpack_from(data, offset + stride * i) for i in range(a["count"])]


def grip_textile():
    material = asset("M_PWR_GripTextile", MATERIAL_FOLDER, unreal.Material, unreal.MaterialFactoryNew())
    materials.delete_all_material_expressions(material)
    material.set_editor_properties({"two_sided": False, "used_with_static_lighting": False,
        "blend_mode":unreal.BlendMode.BLEND_MASKED, "opacity_mask_clip_value":.25})
    objects = []
    sources = {}
    for name, is_normal in (("T_PWR_GripTextile", False), ("T_PWR_GripNormal", True)):
        path = SOURCE / (name + ".tga")
        sources[path.name] = digest(path)
        task = unreal.AssetImportTask()
        task.set_editor_properties({"filename": str(path), "destination_path": MATERIAL_FOLDER,
            "destination_name": name, "automated": True, "replace_existing": True, "save": False})
        assets.import_asset_tasks([task])
        texture = unreal.load_asset(MATERIAL_FOLDER + "/" + name)
        texture.set_editor_properties({"srgb": not is_normal, "address_y": unreal.TextureAddress.TA_WRAP,
            "compression_settings": unreal.TextureCompressionSettings.TC_NORMALMAP if is_normal else unreal.TextureCompressionSettings.TC_DEFAULT,
            "flip_green_channel": is_normal, "compression_no_alpha": False})
        library.save_loaded_asset(texture, only_if_is_dirty=False)
        sampler = materials.create_material_expression(material, unreal.MaterialExpressionTextureSample)
        sampler.set_editor_properties({"texture": texture,"sampler_type":
            unreal.MaterialSamplerType.SAMPLERTYPE_NORMAL if is_normal else unreal.MaterialSamplerType.SAMPLERTYPE_COLOR})
        pins = [("RGB",unreal.MaterialProperty.MP_NORMAL)] if is_normal else [
            ("RGB",unreal.MaterialProperty.MP_BASE_COLOR),("A",unreal.MaterialProperty.MP_ROUGHNESS),
            ("A",unreal.MaterialProperty.MP_OPACITY_MASK)]
        for channel,target in pins:
            if not materials.connect_material_property(sampler,channel,target):
                raise ValueError(f"Could not connect {name}.{channel} to {target}")
        objects.append(texture)
    materials.recompile_material(material)
    library.save_loaded_asset(material, only_if_is_dirty=False)
    return material, objects, sources


def build_mesh(name, gltf, document, sockets, finishes):
    nodes = [n for n in document["nodes"] if "mesh" in n]
    if len(nodes) != 1 or len(document["meshes"]) != 1:
        raise ValueError("Export one joined canopy mesh in biped foot space")
    if any(k in nodes[0] for k in ("matrix", "translation", "rotation", "scale")):
        raise ValueError("Apply transforms to the exported canopy mesh")
    binary = gltf.parent / document["buffers"][0]["uri"]
    source_hashes = {path.name: digest(path) for path in (gltf, binary)}
    data = binary.read_bytes()
    positions, normals, corner_uvs, indices, sections, names = [], [], [], [], [], []
    collapsed = 0
    for part in document["meshes"][0]["primitives"]:
        if part.get("mode", 4) != 4:
            raise ValueError("Export canopy surfaces as indexed triangles")
        material = document["materials"][part["material"]]["name"]
        if material not in names:
            names.append(material)
        slot = names.index(material)
        attr = part["attributes"]
        pos = accessor(document, data, attr["POSITION"])
        norm = accessor(document, data, attr["NORMAL"])
        uv = accessor(document, data, attr["TEXCOORD_0"]) if "TEXCOORD_0" in attr else None
        base = len(positions)
        # glTF +Z faces forward, +X is the wearer's right, +Y is up.
        # This cyclic axis map preserves cross products. Reverse index winding
        # for Unreal's clockwise surface front, keeping authored normals.
        positions.extend(unreal.Vector(z * 100, x * 100, y * 100) for x, y, z in pos)
        normals.extend(unreal.Vector(z, x, y) for x, y, z in norm)
        local = [value[0] for value in accessor(document, data, part["indices"])]
        for i in range(0, len(local), 3):
            a, b, c = local[i:i + 3]
            ab = [y - x for x, y in zip(pos[a], pos[b])]
            ac = [y - x for x, y in zip(pos[a], pos[c])]
            face = (ab[1]*ac[2] - ab[2]*ac[1], ab[2]*ac[0] - ab[0]*ac[2], ab[0]*ac[1] - ab[1]*ac[0])
            if sum(value * value for value in face) <= 1e-16:
                # Some coincident rib caps and glyph outlines triangulate to
                # zero area. Exclude them before the native tangent bake.
                collapsed += 1
                continue
            axis = max(range(3), key=lambda k: abs(face[k]))
            for index in (a, c, b):
                indices.append(base + index)
                plane = [pos[index][k] for k in range(3) if k != axis]
                corner_uvs.append(unreal.Vector2D(*(uv[index] if uv is not None else plane)))
                corner_uvs.append(unreal.Vector2D(plane[0] / .056, plane[1] / .056))
            sections.append(slot)
    mesh = asset(name, FOLDER, unreal.StaticMesh, None)
    # The native builder replaces all source LODs. Clear the previous group
    # on reimport so its settings will be reapplied to the new LOD0.
    if str(mesh.get_editor_property("lod_group")) != "None":
        mesh.set_editor_property("lod_group", "None")
    colors = [unreal.Color(r=255, g=255, b=255, a=255)] * len(positions)
    if not unreal.MjolnirUIBuilderLibrary.build_attributed_static_mesh(
            mesh, positions, normals, indices, corner_uvs, 2, sections, names, colors):
        raise RuntimeError("Canopy MeshDescription build failed")
    slots = [slot.copy() for slot in mesh.get_editor_property("static_materials")]
    for slot, material in zip(slots, names):
        slot.set_editor_property("material_interface", finishes[material])
    mesh.set_editor_properties({"static_materials": slots, "light_map_coordinate_index": 0,
                                "has_navigation_data": False})
    # Setting the editor property rebuilds through UStaticMesh::SetLODGroup.
    # Commandlets do not instantiate the interactive StaticMeshEditorSubsystem.
    mesh.set_editor_property("lod_group", "LargeProp" if gltf.stem == "pwr_canopy" else "SmallProp")
    if mesh.get_num_lods() != 4:
        raise RuntimeError("Failed to build distance LODs")
    body = mesh.get_editor_property("body_setup")
    collision = body.get_editor_property("default_instance").copy()
    collision.set_editor_property("collision_profile_name", "NoCollision")
    body.set_editor_properties({"never_needs_cooked_collision_data": True, "default_instance": collision,
                                "collision_trace_flag": unreal.CollisionTraceFlag.CTF_USE_SIMPLE_AS_COMPLEX})
    for name, point in sockets.items():
        socket = mesh.find_socket(name)
        if socket is None:
            socket = unreal.new_object(unreal.StaticMeshSocket, outer=mesh)
            socket.set_editor_property("socket_name", name)
            mesh.add_socket(socket)
        socket.set_editor_property("relative_location", unreal.Vector(*point))
        actual = mesh.find_socket(name).get_editor_property("relative_location")
        if any(abs(value - expected) > .001 for value, expected in zip((actual.x, actual.y, actual.z), point)):
            raise RuntimeError(f"Socket {name} did not retain its authored location")
    if not library.save_loaded_asset(mesh, only_if_is_dirty=False):
        raise RuntimeError("Could not save parachute")
    bounds = mesh.get_bounds()
    minimum, maximum = bounds.origin - bounds.box_extent, bounds.origin + bounds.box_extent
    receipt = {"mesh": mesh.get_path_name(), "slots": names, "triangles": len(sections),
               "grip_sockets_ue_cm": sockets, "uniform_scale": 1, "relative_offset_cm": [0, 0, 0],
               "bounds_ue_cm": [[minimum.x, minimum.y, minimum.z], [maximum.x, maximum.y, maximum.z]],
               "source_sha256": source_hashes, "collapsed_source_triangles": collapsed,
               "lod_triangles": [mesh.get_num_triangles(i) for i in range(mesh.get_num_lods())]}
    unreal.log(f"Built {mesh.get_path_name()} with {len(sections)} triangles and sockets {list(sockets)}")
    return mesh, receipt


def build():
    report = SOURCE / "geometry-report.json"
    geometry = json.loads(report.read_text())
    sockets = geometry["grip_sockets_ue_cm"]
    if set(sockets) != {"grip_l", "grip_r"}:
        raise ValueError("Both handle centers must be present")
    specs = [(NAME, SOURCE / "pwr_canopy.gltf", sockets),
             ("SM_PWR_ParachutePackV2", SOURCE / "pwr_pack.gltf", {})]
    documents = []
    recipes = {}
    for _, gltf, _ in specs:
        document = json.loads(gltf.read_text())
        documents.append(document)
        for material in document["materials"]:
            name = material["name"]
            recipe = material["pbrMetallicRoughness"]
            if name in recipes and recipes[name] != recipe:
                raise ValueError(f"Conflicting PBR recipe for shared material {name}")
            recipes[name] = recipe
    if set(recipes) != SLOTS:
        raise ValueError(f"Unexpected authored material slots {set(recipes)}")
    texture = weave_texture()
    master, finishes = make_materials({k:v for k,v in recipes.items() if k != "GripTextile"}, texture)
    grip_material, grip_textures, grip_sources = grip_textile()
    finishes["GripTextile"] = grip_material
    objects = [texture, master, *finishes.values(), *grip_textures]
    meshes = []
    for (name, gltf, grips), document in zip(specs, documents):
        mesh, result = build_mesh(name, gltf, document, grips, finishes)
        if name == "SM_PWR_ParachutePackV2":
            result["relative_offset_cm"] = geometry["pack_mount_ue_cm"]
        objects.append(mesh)
        meshes.append(result)
    label = asset("PAL_PWR_Chute957", MATERIAL_FOLDER, unreal.PrimaryAssetLabel, unreal.DataAssetFactory())
    rules = label.get_editor_property("rules")
    rules.set_editor_properties({"chunk_id": 957, "priority": 1000, "apply_recursively": True,
                                 "cook_rule": unreal.PrimaryAssetCookRule.ALWAYS_COOK})
    label.set_editor_properties({"rules": rules, "explicit_assets": objects, "label_assets_in_my_directory": False})
    library.save_loaded_asset(label)
    receipt = {"meshes": meshes, "source_report_sha256": digest(report), "textile_source_sha256": grip_sources,
               "packages": [item.get_path_name().split(".")[0] for item in objects]}
    OUTPUT.mkdir(exist_ok=True, parents=True)
    (OUTPUT / "editor-import.json").write_text(json.dumps(receipt, indent=2) + "\n")


build()
