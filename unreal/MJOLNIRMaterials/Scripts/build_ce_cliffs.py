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
eal = unreal.EditorAssetLibrary


def log(msg):
    unreal.log("MJOLNIR cliffs: " + msg)


def build(code, spec_path):
    spec = json.load(open(spec_path, encoding="utf-8"))
    name = code if code.startswith("SM_") else f"SM_{code}_CliffTess"
    path = f"{ROOT}/{name}"
    if eal.does_asset_exist(path):
        eal.delete_asset(path)
    mesh = unreal.AssetToolsHelpers.get_asset_tools().create_asset(name, ROOT, unreal.StaticMesh, None)
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
    material = unreal.load_asset(f"{ROOT}/{spec.get('material', 'M_CE_CliffTess')}")
    for i in range(len(spec["slots"])):
        mesh.set_material(i, material)
    eal.save_loaded_asset(mesh)
    log(f"{code}: {path}, {len(spec['indices']) // 3} triangle(s), slots {spec['slots']}, nanite "
        f"{mesh.get_editor_property('nanite_settings').get_editor_property('enabled')}")


for item in filter(None, os.environ.get("MJ_CLIFF_MESHES", "").split(";")):
    code, spec_path = item.split("=", 1)
    build(code, spec_path)
log("built")
