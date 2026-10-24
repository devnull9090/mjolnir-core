"""Shared Blender and runtime surface palette; UVMap is the exported UV set.

Authored after the collision/detail geometry is built, before Boolean merging.
The preview keeps these exact materials instead of substituting another look.
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SURFACES = json.loads((ROOT / "surfaces.json").read_text())["surfaces"]
METRES_PER_CE = 3.048


def fitted_style(name):
    if name.startswith("arrival_fitted_titanium_frame"):
        return "fitted_pale"
    if name.startswith(("tower_side_fitted_armor_leaf", "parapet_fitted_cap_plate")):
        return "fitted_inset"
    if name.startswith(("parapet_charcoal_insert", "arrival_inner_jamb_liner",
                        "parapet_clasp_fitted_crown", "arrival_jamb_fitted_dark_insert")):
        return "fitted_charcoal"
    return None


def blender_material(role, detail=False):
    import bpy
    spec = SURFACES[role]
    name = spec["shader"] + ("!" if detail else "")
    if name in bpy.data.materials:
        return bpy.data.materials[name]
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    mat["tst_surface_role"] = role
    mat["mjolnir_pcg_policy"] = "NONE"
    mat["source_shader_tag"] = spec["tag"].replace("/", chr(92))
    mat["surface_library"] = "surfaces.json"
    if detail:
        mat["tst_detail_material"] = spec["shader"]
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    shader = nodes.get("Principled BSDF")
    shader.inputs["Metallic"].default_value = spec["metallic"]
    uv = nodes.new("ShaderNodeUVMap"); uv.uv_map = "UVMap"
    albedo = nodes.new("ShaderNodeTexImage")
    albedo.image = bpy.data.images.load(str(ROOT / spec["albedo"]), check_existing=True)
    links.new(uv.outputs["UV"], albedo.inputs["Vector"])
    soften = nodes.new("ShaderNodeMixRGB")
    soften.inputs[0].default_value = spec["soften"]
    soften.inputs[2].default_value = (.32, .32, .32, 1)
    links.new(albedo.outputs["Color"], soften.inputs[1])
    tint = nodes.new("ShaderNodeMixRGB"); tint.blend_type = "MULTIPLY"
    tint.inputs[0].default_value = 1
    tint.inputs[2].default_value = (*spec["tint"], 1)
    links.new(soften.outputs["Color"], tint.inputs[1])
    links.new(tint.outputs["Color"], shader.inputs["Base Color"])
    rough = nodes.new("ShaderNodeTexImage")
    rough.image = bpy.data.images.load(str(ROOT / spec["roughness_map"]), check_existing=True)
    rough.image.colorspace_settings.name = "Non-Color"
    links.new(uv.outputs["UV"], rough.inputs["Vector"])
    remap = nodes.new("ShaderNodeMapRange")
    remap.inputs["From Min"].default_value = .30
    remap.inputs["From Max"].default_value = .60
    remap.inputs["To Min"].default_value = spec["roughness"][0]
    remap.inputs["To Max"].default_value = spec["roughness"][1]
    links.new(rough.outputs["Color"], remap.inputs["Value"])
    links.new(remap.outputs["Result"], shader.inputs["Roughness"])
    mat.diffuse_color = (*(min(.95, .27*t) for t in spec["tint"]), 1)
    return mat


def assign(scene):
    """Assign existing faces only; preserve collision/render-only flags."""
    counts = {}
    for obj in scene.objects:
        if obj.type != "MESH" or obj.name.startswith("SOURCE_"):
            continue
        detail = bool(obj.get("mjolnir_render_detail"))
        original = list(obj.data.materials)
        slots = {}
        def index(role):
            if role not in slots:
                slots[role] = len(obj.data.materials)
                obj.data.materials.append(blender_material(role, detail))
            return slots[role]
        style = fitted_style(obj.name) if detail else None
        if style:
            main = max(obj.data.polygons, key=lambda f: f.area)
            axis = max(range(3), key=lambda a: abs(main.normal[a]))
        inset = any(word in obj.name for word in ("dark_", "recess", "inlay", "gasket"))
        for face in obj.data.polygons:
            mat = original[face.material_index]
            source = mat.get("tst_detail_material", mat.name)
            if source not in ("metal panels generic ext", "metal plate floor ext"):
                continue
            role = "armor" if source == "metal panels generic ext" else "floor"
            if role == "floor" and (abs(face.normal.z) < .75 or detail):
                role = "recess" if inset and detail else "structure"
            if style:
                threshold = .6 if obj.name.startswith("parapet_clasp_fitted_crown_wrap") else .985
                if obj.get("engraved_armor") and role in ("structure", "recess"):
                    role = "recess"
                elif abs(face.normal[axis]) > threshold:
                    role = style
                else:
                    role = "armor" if style == "fitted_pale" else "structure"
            if detail and role != "recess" and sum(obj.name.encode()) % 4 and any(
                    word in obj.name for word in ("frame", "border", "cap", "surround", "crown", "bright_edge", "precision_lip")):
                verts = [obj.data.vertices[v].co for v in face.vertices]
                perimeter = sum((b-a).length for a,b in zip(verts, verts[1:]+verts[:1]))
                width = 2*face.area*METRES_PER_CE/max(perimeter, 1e-8)
                if .002 < width < .045:
                    role = "edge"
            face.material_index = index(role)
            counts[role] = counts.get(role, 0) + 1
        if slots:
            obj["tst_exported_surfaces"] = True
    missing = set(SURFACES) - set(counts)
    if missing:
        raise RuntimeError(f"Unassigned architectural finishes: {missing}")
    print("TST_EXPORTED_SURFACES", counts)


def project_uv(obj, face, uv, role):
    spec = SURFACES[role]
    dominant = max(range(3), key=lambda a: abs(face.normal[a]))
    axes = [a for a in range(3) if a != dominant]
    tile = spec["tile_m"]
    if tile is None:
        main = max(obj.data.polygons, key=lambda p: p.area)
        axis = max(range(3), key=lambda a: abs(main.normal[a]))
        axes = [a for a in range(3) if a != axis]
        lo = [min(v.co[a] for v in obj.data.vertices) for a in axes]
        hi = [max(v.co[a] for v in obj.data.vertices) for a in axes]
    for loop in face.loop_indices:
        co = obj.data.vertices[obj.data.loops[loop].vertex_index].co
        if tile:
            u,v = (co[a]*METRES_PER_CE/tile for a in axes)
        else:
            u,v = [(co[a]-lo[i])/max(hi[i]-lo[i], 1e-6) for i,a in enumerate(axes)]
            orientation = sum(obj.name.encode()) % 8
            for _ in range(orientation % 4):
                u,v = v,1-u
            if orientation >= 4:
                u = 1-u
        uv.data[loop].uv = (u,v)
