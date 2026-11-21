"""Repair the tangent frames of the base meshes a visual manifest names (after build_pwr_bases.py).

    env MJ_PWR_BASE_MANIFEST=<manifest.json>

The attributed mesh builder leaves source corners without usable tangent frames; Nanite's explicit
tangents then shade panels wrongly. MjolnirUIBuilder repairs them in place. Writes
tangent-editor.json beside the manifest.
"""
import json
import os
from pathlib import Path

import unreal

source = Path(os.environ["MJ_PWR_BASE_MANIFEST"])
rows = {}
for row in json.loads(source.read_text())["assets"]:
    mesh = unreal.load_asset(row["asset"])
    count = unreal.MjolnirUIBuilderLibrary.repair_static_mesh_tangent_frames(mesh)
    if count < 0 or not unreal.EditorAssetLibrary.save_loaded_asset(mesh):
        raise RuntimeError("Tangent repair failed: " + row["name"])
    rows[row["id"]] = {"repaired_source_corners": count,
                       "nanite_explicit_tangents": mesh.get_editor_property("nanite_settings").get_editor_property("explicit_tangents")}
    unreal.log("PWR_NATIVE_FRAME " + row["name"] + " " + str(rows[row["id"]]))
(source.parent / "tangent-editor.json").write_text(json.dumps(rows, indent=2))
unreal.log("PWR base frames repaired: " + str(len(rows)))
