"""Face/object/material PCG permissions, exported independently of CE shaders."""
import json
from pathlib import Path
import bpy
import bmesh

ATTRIBUTE = "mjolnir_pcg_policy"
NAMES = ("AUTO", "NONE", "GROUND", "CLIFF", "BOTH")
ITEMS = [(name, label, detail) for name,label,detail in (
    ("AUTO", "Inherit / automatic", "Inherit object/material permission, then existing biome and slope rules"),
    ("NONE", "No procedural dressing", "No ground scatter or cliff cladding"),
    ("GROUND", "Ground scatter only", "Allow ground rules; prohibit cliff cladding"),
    ("CLIFF", "Cliff dressing only", "Allow cliff cladding; prohibit ground scatter"),
    ("BOTH", "Ground + cliff", "Permit both rule families, subject to normal placement checks"))]


def build_surface_policy(scene):
    if bpy.context.mode != "OBJECT":
        raise ValueError("Switch to Object Mode before exporting surface policies")
    bpy.context.view_layer.update()
    triangles, counts = [], {name: 0 for name in NAMES}
    scale = scene.unit_settings.scale_length
    depsgraph = bpy.context.evaluated_depsgraph_get()
    for obj in scene.objects:
        if obj.type != "MESH" or obj.hide_render or obj.get("mjolnir_preview_only"):
            continue
        if any("SOURCE" in c.name.upper() or c.get("mjolnir_preview_only") for c in obj.users_collection):
            continue
        evaluated = obj.evaluated_get(depsgraph)
        mesh = evaluated.to_mesh(preserve_all_data_layers=True, depsgraph=depsgraph)
        try:
            mesh.calc_loop_triangles()
            attribute = mesh.attributes.get(ATTRIBUTE)
            if attribute and (attribute.domain != "FACE" or attribute.data_type != "INT"):
                raise ValueError(f"{obj.name}: {ATTRIBUTE} must be a face integer attribute")
            for tri in mesh.loop_triangles:
                poly = mesh.polygons[tri.polygon_index]
                mat = mesh.materials[poly.material_index] if mesh.materials else None
                if mat and "sky" in mat.name.lower():
                    continue
                value = attribute.data[poly.index].value if attribute else 0
                if not 0 <= value < len(NAMES):
                    raise ValueError(f"{obj.name}: invalid PCG face value {value}")
                name = NAMES[value]
                if name == "AUTO":
                    name = obj.get(ATTRIBUTE, "AUTO")
                if name == "AUTO" and mat:
                    name = mat.get(ATTRIBUTE, "AUTO")
                if name not in NAMES:
                    raise ValueError(f"{obj.name}: unknown PCG policy {name}")
                if name == "AUTO":
                    continue
                points = [(obj.matrix_world @ mesh.vertices[i].co)*scale for i in tri.vertices]
                triangles.append({"policy": name, "vertices": [[round(v,5) for v in p] for p in points]})
                counts[name] += 1
        finally:
            evaluated.to_mesh_clear()
    return {"schema_version": 1, "coordinates": "blender_world_metres_z_up",
            "source_blend": Path(bpy.data.filepath).name, "counts": counts,
            "meaning": "Permissions only; existing biome/slope/clearance rules still apply. No collision changes.",
            "triangles": triangles}


def review_materials(scene):
    """Color the isolated preview copy; never call on the editable source."""
    colors = {"AUTO":(.35,.35,.35,1),"NONE":(.20,.23,.28,1),
              "GROUND":(.12,.65,.23,1),"CLIFF":(.65,.15,.65,1),"BOTH":(.05,.55,.72,1)}
    for obj in scene.objects:
        if obj.type != "MESH" or obj.hide_render or obj.get("mjolnir_preview_only"):
            continue
        attribute = obj.data.attributes.get(ATTRIBUTE)
        policies = []
        for poly in obj.data.polygons:
            value = attribute.data[poly.index].value if attribute else 0
            name = NAMES[value]
            if name == "AUTO": name = obj.get(ATTRIBUTE,"AUTO")
            if name == "AUTO" and obj.data.materials:
                mat = obj.data.materials[poly.material_index]
                name = mat.get(ATTRIBUTE,"AUTO") if mat else "AUTO"
            policies.append(name)
        start = len(obj.data.materials)
        for name in NAMES:
            material = bpy.data.materials.get("PCG PERMISSION - "+name)
            if material is None:
                material = bpy.data.materials.new("PCG PERMISSION - "+name)
                material.diffuse_color = colors[name]
                material.use_nodes = True
                bsdf = material.node_tree.nodes.get("Principled BSDF")
                bsdf.inputs["Base Color"].default_value = colors[name]
                bsdf.inputs["Emission Color"].default_value = colors[name]
                bsdf.inputs["Emission Strength"].default_value = .3
                bsdf.inputs["Roughness"].default_value = 1
            obj.data.materials.append(material)
        for poly,name in zip(obj.data.polygons,policies):
            poly.material_index = start+NAMES.index(name)
    return {name:list(color[:3]) for name,color in colors.items()}


def write_surface_policy(scene, path):
    doc = build_surface_policy(scene)
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(doc, separators=(",", ":"))+"\n", encoding="utf-8")
    return doc


class MJOLNIR_OT_pcg_faces(bpy.types.Operator):
    """Assign procedural dressing permissions to selected faces or objects"""
    bl_idname = "mjolnir.pcg_faces"
    bl_label = "Assign PCG permission"
    bl_options = {"REGISTER", "UNDO"}
    policy: bpy.props.EnumProperty(name="Permission", items=ITEMS, default="NONE")

    def execute(self, context):
        objects = context.objects_in_mode_unique_data if context.mode == "EDIT_MESH" else context.selected_objects
        for obj in objects:
            if obj.type != "MESH":
                continue
            if context.mode == "EDIT_MESH":
                bm = bmesh.from_edit_mesh(obj.data)
                layer = bm.faces.layers.int.get(ATTRIBUTE) or bm.faces.layers.int.new(ATTRIBUTE)
                for face in bm.faces:
                    if face.select:
                        face[layer] = NAMES.index(self.policy)
                bmesh.update_edit_mesh(obj.data)
            else:
                obj[ATTRIBUTE] = self.policy
        return {"FINISHED"}

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)


class MJOLNIR_OT_export_surface(bpy.types.Operator):
    bl_idname = "mjolnir.export_surface"
    bl_label = "Export PCG surface permissions"
    filepath: bpy.props.StringProperty(subtype="FILE_PATH")

    def execute(self, context):
        try:
            doc = write_surface_policy(context.scene, self.filepath)
        except (ValueError, OSError) as error:
            self.report({"ERROR"}, str(error))
            return {"CANCELLED"}
        self.report({"INFO"}, f"Exported {len(doc['triangles'])} surface triangles")
        return {"FINISHED"}

    def invoke(self, context, event):
        self.filepath = str(Path(bpy.data.filepath).with_suffix(".surfaces.json")) if bpy.data.filepath else "level.surfaces.json"
        context.window_manager.fileselect_add(self)
        return {"RUNNING_MODAL"}
