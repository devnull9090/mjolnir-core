"""Build converted maps' cliffs as Nanite meshes for tessellation.

    set MJ_CLIFF_MESHES=BGL=C:/.../BGL/cliff_mesh.json;DTI=...
    powershell -File tools/ue/editor_cmd.ps1 -Script Scripts/build_ce_cliffs.py

Each tools/level/cliff_mesh.py output becomes /Game/MJOLNIR/CETrial/
SM_<CODE>_CliffTess (chunk 983 with the trial masters): Unreal centimetres
(placed at the origin, unscaled), one slot a terrain cliff slot, named
`slot_<terrain slot>` so MJOLNIRLevelLoader gives each its slot's rock
(Land.cliffs), M_CE_CliffTess until it does. The vertex colour is the
distance from the cliffs' border, which the material fades displacement by;
UV2 and UV3 carry CE's own normals (`shade`), which the material shades by.

An entry named SM_... (`SM_YOY_Plasma=...plasma_mesh.json`) is a slot mesh
(cliff_mesh.py --parent): built under that name, Nanite only if the spec
says so, its slots on the spec's `material` (a translucent master: a mesh
enters the translucency pass by its own slots' materials).
"""
import json
import os

import unreal

ROOT = "/Game/MJOLNIR/CETrial"
OWNED = json.loads(os.environ.get("MJ_MAP_MESH_CHUNKS", "{}"))
eal = unreal.EditorAssetLibrary

def mesh_root(name):
    for code in OWNED:
        if name.startswith(f"SM_{code}_"):
            return f"/Game/MJOLNIR/Maps/{code}/Generated"
    return ROOT



def log(msg):
    unreal.log("MJOLNIR cliffs: " + msg)


def build(code, spec_path):
    spec = json.load(open(spec_path, encoding="utf-8"))
    name = code if code.startswith("SM_") else f"SM_{code}_CliffTess"
    root = mesh_root(name)
    path = f"{root}/{name}"
    if eal.does_asset_exist(path):
        eal.delete_asset(path)
    mesh = unreal.AssetToolsHelpers.get_asset_tools().create_asset(name, root, unreal.StaticMesh, None)
    v = unreal.Vector
    ok = unreal.MjolnirUIBuilderLibrary.build_static_mesh(
        mesh,
        [v(*p) for p in spec["positions"]],
        [v(*n) for n in spec["normals"]],
        spec["indices"],
        [unreal.Vector2D(*t) for t in spec["uv0"]],
        [unreal.Vector2D(*t) for t in spec["uv1"]],
        spec["sections"],
        [f"slot_{s}" for s in spec["slots"]],
        [unreal.LinearColor(w, w, w, 1.0) for w in spec["weight"]],
        [v(*n) for n in spec.get("shade", [])],
    )
    if not ok:
        unreal.log_error(f"MJOLNIR cliffs: {code}: mesh not built")
        return
    nanite = mesh.get_editor_property("nanite_settings")
    nanite.set_editor_property("enabled", bool(spec.get("nanite", True)))
    mesh.set_editor_property("nanite_settings", nanite)
    want = spec.get("material", "M_CE_CliffTess")
    material = unreal.load_asset(want if want.startswith("/") else f"{ROOT}/{want}")
    for i in range(len(spec["slots"])):
        mesh.set_material(i, material)
    eal.save_loaded_asset(mesh)
    log(f"{code}: {path}, {len(spec['indices']) // 3} triangle(s), slots {spec['slots']}, nanite "
        f"{mesh.get_editor_property('nanite_settings').get_editor_property('enabled')}")


for item in filter(None, os.environ.get("MJ_CLIFF_MESHES", "").split(";")):
    code, spec_path = item.split("=", 1)
    build(code, spec_path)
# Original community maps must carry their own generated geometry. Assign
# only these meshes at higher priority than the shared CETrial directory;
# dependencies (the shared material masters) stay in the runtime package.
for code, chunk in OWNED.items():
    names = [item.split("=", 1)[0] for item in os.environ["MJ_CLIFF_MESHES"].split(";")]
    names = [f"SM_{name}_CliffTess" if name == code else name for name in names
             if name == code or name.startswith(f"SM_{code}_")]
    meshes = [unreal.load_asset(f"{mesh_root(name)}/{name}") for name in names]
    if not meshes or any(mesh is None for mesh in meshes):
        raise RuntimeError(f"{code}: missing map-owned meshes")
    label_name = f"PAL_MJOLNIR_{code}_Meshes"
    label = unreal.load_asset(f"{ROOT}/{label_name}")
    if label is None:
        label = unreal.AssetToolsHelpers.get_asset_tools().create_asset(
            label_name, ROOT, unreal.PrimaryAssetLabel, unreal.DataAssetFactory())
    rules = label.get_editor_property("rules")
    rules.set_editor_property("chunk_id", int(chunk))
    rules.set_editor_property("priority", 100)
    rules.set_editor_property("apply_recursively", False)
    rules.set_editor_property("cook_rule", unreal.PrimaryAssetCookRule.ALWAYS_COOK)
    label.set_editor_property("rules", rules)
    label.set_editor_property("label_assets_in_my_directory", False)
    label.set_editor_property("explicit_assets", meshes)
    eal.save_loaded_asset(label)
log("built")
