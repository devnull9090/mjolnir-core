# MJOLNIR Level — author Halo: Campaign Evolved custom levels in Blender.
#
# The scene maps to a .level.json map variant (docs/level_format.md): tag any
# object with a MJOLNIR role in the sidebar panel (N → MJOLNIR), set the scene's
# canvas scenario and origin, and export. Blender works in meters, Z-up,
# right-handed; the exporter emits UE centimeters, Z-up, left-handed (Y and all
# rotation angles negate — see export.py).
#
# Every action is a plain operator so blender-mcp / headless bpy can drive the
# whole authoring flow without the UI.

bl_info = {
    "name": "MJOLNIR Level",
    "author": "MJOLNIR project",
    "version": (0, 3, 0),
    "blender": (4, 0, 0),
    "location": "3D Viewport sidebar → MJOLNIR",
    "description": "Author Halo: Campaign Evolved custom levels (map variants) and export .level.json",
    "category": "Import-Export",
}

import bpy  # noqa: E402

from . import export, library, native, surface  # noqa: E402

SCENARIOS = [
    ("A15", "A15 — Pillar of Autumn", ""),
    ("A30", "A30 — Halo", ""),
    ("A50", "A50 — Truth and Reconciliation", ""),
    ("B30", "B30 — Silent Cartographer", ""),
    ("B40", "B40 — Assault on the Control Room", ""),
    ("C10", "C10 — 343 Guilty Spark", ""),
    ("C20", "C20 — The Library", ""),
    ("C45", "C45 — Two Betrayals", ""),
    ("D20", "D20 — Keyes", ""),
    ("D40", "D40 — The Maw", ""),
    ("E10", "E10", ""),
    ("E20", "E20", ""),
    ("E30", "E30", ""),
]

KINDS = [
    ("NONE", "Not exported", "Plain Blender object, ignored by the exporter"),
    ("DECOR", "Decor mesh (visual only)", "Runtime-spawned UE mesh — NOT solid"),
    ("PLAYER_START", "Player start", "Spawn point (≥2 for co-op)"),
    ("VEHICLE", "Vehicle", "Solid, drivable — baked into the scenario"),
    ("WEAPON", "Weapon", "Weapon pickup — baked into the scenario"),
    ("EQUIPMENT", "Equipment", "Grenades / powerups / ammo — baked into the scenario"),
    ("OBJECT", "Structure (Blam object)", "Solid scenery or crate placement — baked into the scenario"),
    ("MARKER", "Marker", "Named point for future game modes"),
]


class MjolnirObjectProps(bpy.types.PropertyGroup):
    kind: bpy.props.EnumProperty(name="Role", items=KINDS, default="NONE")
    type_name: bpy.props.StringProperty(
        name="Type",
        description="Friendly type for vehicles/weapons/equipment (see defs/level/palette-map.json)",
        default="",
    )
    tag_path: bpy.props.StringProperty(
        name="Tag path",
        description="Blam tag path for a structure, e.g. objects\\props\\...\\crate",
        default="",
    )
    object_group: bpy.props.EnumProperty(
        name="Group",
        items=[("scenery", "scenery", ""), ("crates", "crates", "")],
        default="scenery",
    )
    mesh_path: bpy.props.StringProperty(
        name="UE mesh",
        description="UE object path for decor, e.g. /Engine/BasicShapes/Cube.Cube",
        default="/Engine/BasicShapes/Cube.Cube",
    )
    use_tint: bpy.props.BoolProperty(name="Tint", default=False)
    tint: bpy.props.FloatVectorProperty(
        name="Tint color",
        subtype="COLOR",
        size=4,
        min=0.0,
        max=1.0,
        default=(0.8, 0.8, 0.8, 1.0),
    )


class MjolnirSceneProps(bpy.types.PropertyGroup):
    cli_path: bpy.props.StringProperty(name="MJOLNIR CLI", subtype="FILE_PATH")
    paks_path: bpy.props.StringProperty(name="Installed game Paks", subtype="DIR_PATH")
    asset_cache: bpy.props.StringProperty(name="Local asset cache", subtype="DIR_PATH", default="//.mjolnir-cache/")
    level_name: bpy.props.StringProperty(
        name="Level slug", description="[a-z0-9_]+", default="my_level"
    )
    level_title: bpy.props.StringProperty(name="Title", default="My Level")
    scenario: bpy.props.EnumProperty(name="Canvas", items=SCENARIOS, default="B40")
    origin: bpy.props.FloatVectorProperty(
        name="Origin (UE cm)",
        description="Where the Blender origin lands on the canvas map, in UE centimeters",
        size=3,
        default=(9609.0, -10200.0, 14780.0),
    )
    catalog_path: bpy.props.StringProperty(
        name="Mesh catalog",
        description="JSON from `mjolnir mesh list --out ...`",
        subtype="FILE_PATH",
        default="",
    )


class MJOLNIR_PT_scene(bpy.types.Panel):
    bl_label = "MJOLNIR Level"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "MJOLNIR"

    def draw(self, context):
        s = context.scene.mjolnir
        col = self.layout.column()
        col.prop(s, "level_name")
        col.prop(s, "level_title")
        col.prop(s, "scenario")
        col.prop(s, "origin")
        col.separator()
        col.prop(s, "catalog_path")
        col.operator("mjolnir.place_mesh", icon="MESH_CUBE")
        col.prop(s, "cli_path")
        col.prop(s, "paks_path")
        col.prop(s, "asset_cache")
        col.operator("mjolnir.load_native", icon="IMPORT")
        col.operator("mjolnir.load_reference", icon="ARMATURE_DATA")
        col.label(text="References: local geometry, approximate materials")
        col.separator()
        col.operator("mjolnir.pcg_faces")
        col.operator("mjolnir.export_surface", icon="EXPORT")
        col.separator()
        col.operator("mjolnir.export_level", icon="EXPORT")


class MJOLNIR_PT_object(bpy.types.Panel):
    bl_label = "MJOLNIR Object"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "MJOLNIR"

    @classmethod
    def poll(cls, context):
        return context.active_object is not None

    def draw(self, context):
        o = context.active_object.mjolnir
        col = self.layout.column()
        col.prop(o, "kind")
        if context.active_object.get("mjolnir_preview_only"):
            col.label(text="Local reference: excluded from level export", icon="INFO")
        col.label(text="PCG: "+str(context.active_object.get("mjolnir_pcg_policy", "AUTO")))
        if o.kind in {"VEHICLE", "WEAPON", "EQUIPMENT"}:
            col.prop(o, "type_name")
        elif o.kind == "OBJECT":
            col.prop(o, "object_group")
            col.prop(o, "tag_path")
        elif o.kind == "DECOR":
            col.prop(o, "mesh_path")
            col.prop(o, "use_tint")
            if o.use_tint:
                col.prop(o, "tint")


CLASSES = (
    MjolnirObjectProps,
    MjolnirSceneProps,
    MJOLNIR_PT_scene,
    MJOLNIR_PT_object,
    export.MJOLNIR_OT_export_level,
    library.MJOLNIR_OT_place_mesh,
    native.MJOLNIR_OT_load_native,
    native.MJOLNIR_OT_load_reference,
    surface.MJOLNIR_OT_pcg_faces,
    surface.MJOLNIR_OT_export_surface,
)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.Object.mjolnir = bpy.props.PointerProperty(type=MjolnirObjectProps)
    bpy.types.Scene.mjolnir = bpy.props.PointerProperty(type=MjolnirSceneProps)


def unregister():
    del bpy.types.Scene.mjolnir
    del bpy.types.Object.mjolnir
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
