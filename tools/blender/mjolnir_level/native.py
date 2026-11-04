"""Local game geometry cache and preview import; no extracted files ship here."""
from pathlib import Path
import re
import subprocess
import bpy
from .asset_cache import cache_asset


def cache_mesh(cli, paks, cache, asset):
    """Use the installed game's exporter, with argument arrays (never a shell)."""
    return cache_asset(cli, paks, cache, asset)


def import_reference(path, target=None, name=None):
    """Preserve glTF metre scale and hierarchy, including non-unit CE scenes."""
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=str(Path(path).resolve()))
    objects = set(bpy.data.objects)-before
    target = target or bpy.context.scene.collection
    anchor = bpy.data.objects.new(name or Path(path).stem, None)
    target.objects.link(anchor)
    anchor["mjolnir_preview_only"] = True
    anchor["reference_file"] = str(Path(path).resolve())
    anchor["reference_material_fidelity"] = "Imported glTF materials; native exports need explicit texture bindings"
    for obj in objects:
        # CLI exports every cooked LOD as a separate node. Displaying them all
        # superimposes shells and grass cards; keep only the highest-detail LOD.
        if re.search(r'_LOD[1-9][0-9]*(?:\.|$)',obj.name):
            obj.hide_render = True
            obj.hide_viewport = True
        if any(c.hide_render for c in obj.users_collection):
            obj.hide_render = True
        for c in list(obj.users_collection):
            c.objects.unlink(obj)
        target.objects.link(obj)
        obj["mjolnir_preview_only"] = True
        if obj.parent not in objects:
            obj.parent = anchor
        if hasattr(obj, "mjolnir"):
            obj.mjolnir.kind = "NONE"
    return anchor, objects


class MJOLNIR_OT_load_native(bpy.types.Operator):
    """Extract actual shipped geometry to a local cache and import a reference"""
    bl_idname = "mjolnir.load_native"
    bl_label = "Load actual game mesh…"
    bl_options = {"REGISTER", "UNDO"}
    asset: bpy.props.StringProperty(name="Exact UE asset path / mesh name")

    def execute(self, context):
        s = context.scene.mjolnir
        if not self.asset.strip() or not s.cli_path or not s.paks_path or not s.asset_cache:
            self.report({"ERROR"}, "Set CLI, Paks, cache and an exact mesh path/name")
            return {"CANCELLED"}
        try:
            path = cache_mesh(bpy.path.abspath(s.cli_path), bpy.path.abspath(s.paks_path),
                              bpy.path.abspath(s.asset_cache), self.asset.strip())
            collection = bpy.data.collections.get("MJOLNIR - LOCAL REFERENCES")
            if collection is None:
                collection = bpy.data.collections.new("MJOLNIR - LOCAL REFERENCES")
                context.scene.collection.children.link(collection)
                collection["mjolnir_preview_only"] = True
            anchor, _ = import_reference(path, collection)
            anchor["ue_asset"] = self.asset
            anchor.location = context.scene.cursor.location
            bpy.ops.object.select_all(action="DESELECT")
            anchor.select_set(True)
            context.view_layer.objects.active = anchor
        except (OSError, RuntimeError, subprocess.SubprocessError) as error:
            self.report({"ERROR"}, str(error))
            return {"CANCELLED"}
        self.report({"INFO"}, "Imported local reference geometry; UE material graphs are not reproduced")
        return {"FINISHED"}

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)


class MJOLNIR_OT_load_reference(bpy.types.Operator):
    """Import a locally converted cyborg or another glTF as a scale reference"""
    bl_idname = "mjolnir.load_reference"
    bl_label = "Load local glTF reference…"
    bl_options = {"REGISTER", "UNDO"}
    filepath: bpy.props.StringProperty(subtype="FILE_PATH")
    filter_glob: bpy.props.StringProperty(default="*.glb;*.gltf", options={"HIDDEN"})

    def execute(self, context):
        try:
            anchor, _ = import_reference(self.filepath)
        except (OSError, RuntimeError) as error:
            self.report({"ERROR"}, str(error))
            return {"CANCELLED"}
        anchor.location = context.scene.cursor.location
        return {"FINISHED"}

    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {"RUNNING_MODAL"}
