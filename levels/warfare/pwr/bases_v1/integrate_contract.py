# /// script
# dependencies = ["numpy"]
# ///
"""Inventory the offline base replacement; never export, compile, cook or install.

Run: uv run levels/warfare/pwr/bases_v1/integrate_contract.py
The only output is out/pwr/base-integration/runtime-handoff.json. Source-local
surface ranges are proved against existing triangle arrays, not guessed from
compiled BSP piece boundaries. No Blender, Unreal or game process is invoked.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

import numpy as np

HERE = Path(__file__).resolve().parent
PWR = HERE.parent
ROOT = PWR.parents[2]
WORLD = Path("C:/haloce/ce_conversions/warfare/PWR/expansion/world-v5-visual8")
SITES = ("red_home", "blue_home", "citadel_plateau")
MASTER_SHA = "cfa587ac8c9bc565270c035ee3a281b8611c8197fb7c6c0833990b1b6c4ee45f"
SBSP_SHA = "cced25ac9d464a3517f6920d15c4a25fe4ec8897fef82f5ab1edb1211ff162f0"
sys.path[:0] = [str(PWR), str(ROOT / "tools/level")]
from world_geometry import base_parts, bridge_parts, orient_closed
from b30_collision import rotator_matrix


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def digest(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def canonical_digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     allow_nan=False).encode()).hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def site_of(name):
    return next((site for site in SITES if name.startswith(site + "_")), None)


def triangle_array(part):
    vertices = np.asarray(part["vertices_m"], dtype=np.float64) / 3.048
    faces = orient_closed(part["vertices_m"], part["faces"])
    return np.asarray([vertices[[face[0], face[j], face[j + 1]]]
                       for face in faces for j in range(1, len(face) - 1)])


def build():
    master_path = PWR / "terrain/runtime-v5/runtime-master.json"
    config_path = PWR / "upgrade-v5-visual8.json"
    master = read(master_path)
    config = read(config_path)["PWR"]
    geometry_path = (master_path.parent / master["geometry"]).resolve()
    geometry = read(geometry_path)
    decor_path = ROOT / config["authored_decor"]
    decor = read(decor_path)["decor"]
    runtime_path = ROOT / config["runtime_decor"]
    runtime = read(runtime_path)["decor"]
    tail_receipt_path = WORLD / "source-build/terrain-collision-extra.receipt.json"
    tail_receipt = read(tail_receipt_path)
    sources = tail_receipt["architecture_sources"]
    require(len(sources) == 2, "Unexpected legacy architecture source count")
    architecture_path = Path(sources[0]["path"])
    detail_path = Path(sources[1]["path"])
    architecture = read(architecture_path)
    detail = read(detail_path)
    proposal_path = ROOT / "out/pwr/visual-v4/base-details/proposal.json"
    proposal = read(proposal_path)
    assembly_path = architecture_path.parent / "assembly.json"
    assembly = read(assembly_path)
    hull_path = ROOT / "out/pwr/architecture-stock/hulls/SM_FR_ACR_Ext_Canyon_B_Ziggurat_Pillar_w10_d40_h62_A_96.json"
    hull = read(hull_path)
    require(digest(master_path) == MASTER_SHA, "Accepted runtime field changed")
    require(digest(geometry_path) == master["geometry_sha256"], "Geometry contract changed")
    require(digest(WORLD / "upgrade/PWR/pwr.sbsp") == SBSP_SHA, "V8 compiled collision changed")
    for entry in sources:
        require(digest(entry["path"]) == entry["sha256"], "Legacy collision source changed")
    require(tail_receipt["triangles"] == 135836 and tail_receipt["trailing_architecture_surfaces"] == 8336,
            "Unexpected baseline terrain/structure counts")
    terrain_extra_path = WORLD / "source-build/terrain-collision-extra.json"
    require(digest(terrain_extra_path) == tail_receipt["sha256"], "Configured extra differs from its receipt")
    terrain_extra = read(terrain_extra_path)
    extra_triangles = np.asarray(terrain_extra["triangles"], dtype=float)
    for source, document in zip(sources, (architecture, detail)):
        start, count = source["first_extra_surface"], source["triangles"]
        require(np.array_equal(extra_triangles[start:start + count], np.asarray(document["triangles"])),
                "Declared collision source range differs from configured extra")
    require(len(extra_triangles) == 144172, "Unexpected configured extra triangle count")

    # Reconstruct using pure geometry and the existing read-only stock cache.
    # Do not call collision_parts/hull_of: those helpers can create a cache or
    # extract a missing native asset. Every used cache must already exist.
    parts = base_parts(geometry)
    saved_modules = {row["name"]: row for row in assembly["modules"]}
    legacy_pose_differences = []
    for row in decor:
        if not site_of(row["id"]) or "_stock_buttress_" not in row["id"]:
            continue
        points = np.asarray(hull["points"], dtype=float)
        world = (points * np.asarray(row["scale"])) @ rotator_matrix(*row["rot"]) + np.asarray(row["pos"])
        authoring = world * [0.01, -0.01, 0.01]
        # Saved frozen collision predates a later visual buttress reposition.
        # Restore its authoritative saved module center; never substitute the
        # current helper's placement for the old hull we must remove.
        correction = np.asarray(saved_modules[row["id"] + "_collision"]["position_m"]) - (authoring.min(0) + authoring.max(0)) * .5
        authoring += correction
        if np.max(abs(correction)) > 1e-7:
            legacy_pose_differences.append({"id": row["id"], "collision_minus_current_visual_translation_m": correction.tolist()})
        parts.append({"name": row["id"] + "_collision", "module": "stock_buttress_hull",
                      "vertices_m": authoring.tolist(),
                      "faces": [tuple(reversed(face)) for face in hull["faces"]],
                      "collision": True, "material": "clip"})
    parts += bridge_parts(geometry, None)
    require([part["name"] for part in parts] == [row["name"] for row in assembly["modules"]],
            "Reconstructed source IDs/order differ from saved assembly")
    architecture_triangles = np.asarray(architecture["triangles"], dtype=float)
    inventories, bridge_inventory = [], []
    cursor = 0
    for part in parts:
        if not part["collision"]:
            continue
        triangles = triangle_array(part)
        count = len(triangles)
        actual = architecture_triangles[cursor:cursor + count]
        require(actual.shape == triangles.shape and np.max(np.abs(actual - triangles)) < 1e-10,
                "Legacy source geometry mismatch: " + part["name"])
        entry = {"id": part["name"], "module": part["module"], "site": site_of(part["name"]),
                 "source_first_surface": cursor, "surface_count": count,
                 "terrain_extra_first_surface": sources[0]["first_extra_surface"] + cursor,
                 "triangle_f64_le_sha256": hashlib.sha256(actual.astype("<f8").tobytes()).hexdigest(),
                 "action": "replace" if site_of(part["name"]) else "preserve_exactly"}
        inventories.append(entry)
        if not site_of(part["name"]):
            bridge_inventory.append(entry)
        cursor += count
    require(cursor == len(architecture_triangles) == sources[0]["triangles"], "Unassigned architecture triangles")

    details, cursor = [], 0
    detail_triangles = np.asarray(detail["triangles"], dtype=float)
    for item in proposal["items"]:
        triangles = np.asarray([(np.asarray(item["vertices_m"])[face] / 3.048).tolist()
                                for face in item["faces"]])
        count = len(triangles)
        actual = detail_triangles[cursor:cursor + count]
        require(actual.shape == triangles.shape and np.array_equal(actual, triangles),
                "Legacy detail source changed: " + item["decor"]["id"])
        details.append({"id": item["decor"]["id"], "site": item["site"],
                        "source_first_surface": cursor, "surface_count": count,
                        "terrain_extra_first_surface": sources[1]["first_extra_surface"] + cursor,
                        "triangle_f64_le_sha256": hashlib.sha256(actual.astype("<f8").tobytes()).hexdigest(),
                        "action": "replace"})
        cursor += count
    require(cursor == 4560 and cursor == len(detail_triangles), "Unassigned detail triangles")
    legacy_decor = [row for row in decor if site_of(row["id"])]
    require(len(legacy_decor) == 69 and len(details) == 60, "Unexpected legacy visual count")
    protected = [master_path, geometry_path, config_path, decor_path, runtime_path, tail_receipt_path,
                 architecture_path, detail_path, proposal_path, assembly_path, hull_path,
                 PWR / "asset-palette-v3.json", PWR / "forerunner_stock.py", PWR / "world_geometry.py",
                 PWR / "forerunner_kit.py", Path(__file__),
                 WORLD / "source-build/terrain-collision-extra.json",
                 WORLD / "source-build/terrain-collision-extra.ordered.npz",
                 WORLD / "upgrade/PWR/pwr.sbsp", WORLD / "upgrade/PWR/native-collision-receipt.json",
                 WORLD / "converted/pwr.level.json", ROOT / "out/pwr/world-v5/layout.json",
                 PWR / "native-contract-v3/layout.json", PWR / "vehicle-spawn-policy-v1.json",
                 HERE / "forerunner_bases.blend", ROOT / "out/pwr/base-art/geometry-validation.json"]
    for entry in [master["height"], *master["masks"].values()]:
        path = master_path.parent / entry["path"]
        require(digest(path) == entry["sha256"], "Terrain array changed: " + str(path))
        protected.append(path)
    for key in ("pcg_trees", "pcg_foliage", "render_only_hism", "render_only_pines", "paving_graphic"):
        if config.get(key):
            protected.append(ROOT / config[key])
    files = [{"path": str(path.resolve()), "sha256": digest(path), "bytes": path.stat().st_size}
             for path in dict.fromkeys(protected)]
    return {
        "schema": "pwr-base-integration-runtime-handoff-v1",
        "scope": "Offline inventory and handoff; no render export, native collision export, cook, install, or game check is performed.",
        "status": "authoring_integration_only_runtime_pending",
        "completed": {"legacy_inventory": True, "legacy_triangle_ranges_verified": True,
                      "new_runtime_mesh_export": False, "new_native_collision": False,
                      "runtime_configuration_changed": False, "installed": False},
        "authoritative_inputs": files,
        "coordinates": {"authoring": "metres Z-up", "unreal": "[100*x,-100*y,100*z] centimetres",
                        "blam": "[x,y,z]/3.048 world units", "base_front": "local -Y",
                        "new_base_floor_local_z_m": 0.2,
                        "placement": "Use the separate reviewed world-assembly placement manifest; authoring centers are not runtime placements."},
        "site_anchors": [{"id": site["id"], "position_m": site["position_m"],
                          "heading_degrees": site.get("heading_degrees", 0)}
                         for site in geometry["sites"] if site["id"] in SITES],
        "replace_visual_decor": legacy_decor,
        "legacy_stock_visual_collision_pose_differences": legacy_pose_differences,
        "replace_source_structure_ids": [row["name"] for row in assembly["modules"] if site_of(row["name"])],
        "replace_source_visual_ids": [part["name"] for part in parts if site_of(part["name"]) and part["material"] != "clip"],
        "preserve_source_structure_ids": [row["name"] for row in assembly["modules"] if not site_of(row["name"])],
        "collision_inventory": {"range_convention": "Zero-based first + count in named input JSON, not compiled BSP surfaces.",
                                "architecture_source": str(architecture_path), "architecture": inventories,
                                "detail_source": str(detail_path), "details": details,
                                "preserved_terrain_count": 135836,
                                "preserved_terrain_triangle_f64_le_sha256": hashlib.sha256(extra_triangles[:135836].astype("<f8").tobytes()).hexdigest(),
                                "preserved_terrain_materials_sha256": canonical_digest(terrain_extra["materials"][:135836]),
                                "preserved_bridge_count": sum(row["surface_count"] for row in bridge_inventory),
                                "replace_base_architecture_count": sum(row["surface_count"] for row in inventories if row["action"] == "replace"),
                                "replace_detail_count": 4560},
        "preserve_semantics": {
            "roads_sha256": canonical_digest(geometry["roads"]),
            "watercourses_sha256": canonical_digest(geometry["watercourses"]),
            "lakes_sha256": canonical_digest(geometry["lakes"]),
            "unrelated_authored_decor_sha256": canonical_digest([row for row in decor if not site_of(row["id"])]),
            "unrelated_authored_decor_count": len(decor) - len(legacy_decor),
            "runtime_decor_ids": [row["id"] for row in runtime],
            "runtime_decor_sha256": canonical_digest(runtime),
            "flux_configuration_sha256": canonical_digest(config["flux"]),
            "terrain_heightfield_encoding_and_gameplay_layout": "preserve exact existing bytes",
            "base_paving": "Retain current terrain-conforming court actors; replace only if an independently reviewed overlap correction needs it."},
        "blocked_runtime_steps": [
            {"path": str(PWR / "refresh_native_probes.py"), "symbol": "verify_terrain_tail",
             "constraint": "Hardcoded 135836 terrain + 3776 architecture + 4560 details = 144172 total.",
             "required": "Add an explicit reviewed replacement-architecture contract with exact preserved terrain/bridge hashes and measured new hull ranges; do not simply relax counts."},
            {"path": str(PWR / "assemble_dressing_v5.py"), "symbol": "main",
             "constraint": "Hardcoded nine stock buttresses plus 60 old base details and 8336 collision-tail description.",
             "required": "Build a new isolated assembly excluding the exact 69 listed legacy decor IDs and retaining every unrelated scenery record."},
            {"path": str(PWR / "build_world_v3.py"), "symbol": "base_parts + bridge_parts source assembly",
             "constraint": "Old base visual structures share converted terrain/material meshes with preserved infrastructure.",
             "required": "Replace named source modules and rebuild an isolated mesh source while preserving the four bridge modules. Do not delete the complete pwr_terrain actor to hide bases."},
            {"path": str(ROOT / "tools/level/export_terrain_collision.py"), "symbol": "architecture_parts",
             "constraint": "Legacy detail provenance describes preserved v3 architecture, not the newly authored bases.",
             "required": "Export separate closed floor/wall/roof solids around open vehicle tunnels; retain terrain and bridge arrays once. Do not convex-fill a whole base."},
            {"path": str(ROOT / "tools/level/authored_decor.py"), "symbol": "load_authored_decor_document",
             "constraint": "Native decor requires positive scale components.",
             "required": "Bake the blue reflection into copied export geometry with repaired winding/normals/tangents, and export positive transforms."},
            {"path": str(HERE / "finishing_materials.py"), "symbol": "Blender node materials",
             "constraint": "The reviewed procedural Blender shader is not an automatically compatible runtime material.",
             "required": "Choose module reuse, bake/verify texture and UV data, preserve reused native attributes, and package reviewed runtime materials with readback proof."}],
        "future_offline_path": [
            "Create a new isolated world-v5-base-integration directory and configuration; keep visual8 and installed packages unchanged.",
            "Export reviewed modules/materials using a new adaptation of package_base_paving.py or an owned Unreal cook; the existing script is paving-specific, not a ready base exporter.",
            "Prepare new source structure and native triangle contracts using the exact replacement inventories above, then rebuild collision and renew compiled probes.",
            "Keep all runtime completion flags false until those artifacts and their validation exist. Do not rerun prepare_runtime.py over refreshed metadata."],
        "preserved_after_inventory": True,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=ROOT / "out/pwr/base-integration/runtime-handoff.json")
    args = parser.parse_args()
    output = args.out.resolve()
    require(output.is_relative_to((ROOT / "out/pwr/base-integration").resolve()),
            "Output must remain in the isolated base-integration evidence directory")
    report = build()
    for entry in report["authoritative_inputs"]:
        require(digest(entry["path"]) == entry["sha256"], "Input changed during inventory: " + entry["path"])
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(output), "legacy_visual_decor": len(report["replace_visual_decor"]),
                      "legacy_source_structures": len(report["replace_source_structure_ids"]),
                      "collision": {key: value for key, value in report["collision_inventory"].items() if key.endswith("count")},
                      "protected_files": len(report["authoritative_inputs"]),
                      "runtime_export_complete": False}))


if __name__ == "__main__":
    main()
