"""Rebuild complete authored tangent frames before cooking the widened Nanite gate meshes."""

import json
import os
from pathlib import Path

import unreal

manifest_path = Path(os.environ["MJ_PWR_BASE_MANIFEST"])
mesh_rows = json.loads(manifest_path.read_text(encoding="utf-8"))["assets"]
reports = {}
for row in mesh_rows:
    if not row["id"].endswith("_architecture"):
        continue
    mesh = unreal.load_asset(row["asset"])
    count = unreal.MjolnirUIBuilderLibrary.repair_static_mesh_tangent_frames(mesh)
    if count < 0 or not unreal.EditorAssetLibrary.save_loaded_asset(mesh):
        raise RuntimeError(f"Could not repair native tangent frames on {row['asset']}")
    reports[row["id"]] = {
        "repaired_source_corners": count,
        "nanite_explicit_tangents": mesh.get_editor_property(
            "nanite_settings"
        ).get_editor_property("explicit_tangents"),
    }
    unreal.log(f"{row['id']}: {count} repaired tangent frames")

if set(reports) != {name + "_architecture" for name in ("red", "blue", "green")}:
    raise RuntimeError("The input must contain all three base architecture assemblies")
(manifest_path.parent / "tangent-editor.json").write_text(
    json.dumps(reports, indent=2) + "\n"
)
