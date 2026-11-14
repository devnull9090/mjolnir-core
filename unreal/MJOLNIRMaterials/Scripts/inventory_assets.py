"""Inventory content packs in the project: what each mesh is and how its
authors scatter it.

    $env:MJ_INVENTORY_ROOTS = "/Game/Namaqualand;/Game/STF"
    $env:MJ_INVENTORY_OUT = "C:/haloce/ce_conversions/inventory/packs.json"
    powershell -File tools/ue/editor_cmd.ps1 -Script Scripts/inventory_assets.py

Reads, never saves. Per root:

  meshes         every StaticMesh: bounds about its pivot (cm, the shape of
                 tools/level/data/b30_scenery_bounds.json), triangles and
                 vertices of LOD 0, LODs, Nanite, collision shapes, and its
                 material slots with each material's parent
  foliage_types  every FoliageType_InstancedStaticMesh: its mesh and the
                 authors' own placement settings (density, scale, slope,
                 height, align, cull, collision radius)
  grass_types    every LandscapeGrassType: its varieties' mesh, density,
                 scale and cull
  other          a count of every other asset class

MJ_INVENTORY_LOAD=0 lists from the asset registry alone (class and name,
no bounds): seconds for a pack whose meshes would each build Nanite data.
"""
import json
import os

import unreal

ROOTS = [r for r in os.environ.get("MJ_INVENTORY_ROOTS", "").split(";") if r]
OUT = os.environ.get("MJ_INVENTORY_OUT", "")
LOAD = os.environ.get("MJ_INVENTORY_LOAD", "1") != "0"
if not ROOTS or not OUT:
    raise RuntimeError("set MJ_INVENTORY_ROOTS and MJ_INVENTORY_OUT")

registry = unreal.AssetRegistryHelpers.get_asset_registry()
# The subsystem is None under the pythonscript commandlet; the library it
# replaced still answers there.
sm_lib = unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem) or unreal.EditorStaticMeshLibrary


def prop(obj, name, default=None):
    try:
        return obj.get_editor_property(name)
    except Exception:
        return default


def interval(v):
    if v is None:
        return None
    return [round(prop(v, "min", 0.0), 3), round(prop(v, "max", 0.0), 3)]


def path_of(obj):
    return obj.get_path_name() if obj else None


def parent_chain(material):
    """A material instance's parents up to its master, by path."""
    chain = []
    while material is not None and isinstance(material, unreal.MaterialInstance) and len(chain) < 8:
        material = prop(material, "parent")
        if material is not None:
            chain.append(material.get_path_name())
    return chain


def mesh_row(data):
    row = {"path": str(data.package_name) + "." + str(data.asset_name)}
    if not LOAD:
        for tag in ("Triangles", "Vertices", "LODs", "NaniteEnabled", "ApproxSize", "CollisionPrims", "Materials"):
            value = data.get_tag_value(tag)
            if value is not None:
                row[tag] = str(value)
        return row
    mesh = data.get_asset()
    box = mesh.get_bounding_box()
    row["min"] = [round(box.min.x, 1), round(box.min.y, 1), round(box.min.z, 1)]
    row["max"] = [round(box.max.x, 1), round(box.max.y, 1), round(box.max.z, 1)]
    row["verts"] = sm_lib.get_number_verts(mesh, 0)
    for tag in ("Triangles", "NaniteTriangles", "ApproxSize"):
        value = data.get_tag_value(tag)
        if value is not None:
            row[tag] = str(value)
    try:
        row["tris"] = mesh.get_num_triangles(0)
    except Exception:
        pass
    row["lods"] = sm_lib.get_lod_count(mesh)
    nanite = prop(mesh, "nanite_settings")
    row["nanite"] = bool(nanite and prop(nanite, "enabled", False))
    row["collision"] = sm_lib.get_simple_collision_count(mesh)
    slots = []
    for slot in prop(mesh, "static_materials", []) or []:
        material = prop(slot, "material_interface")
        slots.append({"material": path_of(material), "parents": parent_chain(material)})
    row["materials"] = slots
    return row


FOLIAGE_FIELDS = ("density", "density_adjustment_factor", "radius", "align_to_normal", "align_max_angle",
                  "random_yaw", "random_pitch_angle", "collision_radius", "shade_radius", "num_steps",
                  "average_spread_distance", "seeds_per_step", "cast_shadow", "mobility")


def foliage_row(data):
    row = {"path": str(data.package_name) + "." + str(data.asset_name)}
    if not LOAD:
        return row
    ft = data.get_asset()
    row["mesh"] = path_of(prop(ft, "mesh"))
    for name in FOLIAGE_FIELDS:
        value = prop(ft, name)
        if value is not None:
            row[name] = value if isinstance(value, (bool, int, float)) else str(value)
    for name in ("scale_x", "scale_y", "scale_z", "ground_slope_angle", "height", "z_offset", "procedural_scale"):
        value = interval(prop(ft, name))
        if value is not None:
            row[name] = value
    cull = prop(ft, "cull_distance")
    if cull is not None:
        row["cull"] = [int(prop(cull, "min", 0)), int(prop(cull, "max", 0))]
    return row


def grass_row(data):
    row = {"path": str(data.package_name) + "." + str(data.asset_name)}
    if not LOAD:
        return row
    varieties = []
    for v in prop(data.get_asset(), "grass_varieties", []) or []:
        density = prop(v, "grass_density")
        varieties.append({"mesh": path_of(prop(v, "grass_mesh")),
                          "density": prop(density, "default") if density is not None else None,
                          "scale_x": interval(prop(v, "scale_x")), "scale_z": interval(prop(v, "scale_z")),
                          "cull": [str(prop(v, "start_cull_distance")), str(prop(v, "end_cull_distance"))],
                          "align": prop(v, "align_to_surface"), "random_rotation": prop(v, "random_rotation")})
    row["varieties"] = varieties
    return row


doc = {}
for root in ROOTS:
    assets = registry.get_assets_by_path(root, recursive=True)
    meshes, foliage, grass, other = [], [], [], {}
    for data in assets:
        cls = str(data.asset_class_path.asset_name)
        try:
            if cls == "StaticMesh":
                meshes.append(mesh_row(data))
            elif cls == "FoliageType_InstancedStaticMesh":
                foliage.append(foliage_row(data))
            elif cls == "LandscapeGrassType":
                grass.append(grass_row(data))
            else:
                other[cls] = other.get(cls, 0) + 1
        except Exception as e:  # one unreadable asset does not end the inventory
            unreal.log_warning(f"MJOLNIR inventory: {data.package_name}: {e}")
            other["unreadable"] = other.get("unreadable", 0) + 1
    doc[root] = {"meshes": meshes, "foliage_types": foliage, "grass_types": grass, "other": other}
    unreal.log(f"MJOLNIR inventory: {root}: {len(meshes)} mesh(es), {len(foliage)} foliage type(s), "
               f"{len(grass)} grass type(s), {sum(other.values())} other")

os.makedirs(os.path.dirname(OUT), exist_ok=True)
with open(OUT, "w", encoding="utf-8") as f:
    json.dump(doc, f, indent=1, default=str)
unreal.log(f"MJOLNIR inventory: wrote {OUT}")
