"""Read the actual 965 package, verify its two native material imports and both cooked LODs."""

import argparse
import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[4]
sys.path[:0] = [str(ROOT / "tools/iostore"), str(ROOT / "tools/level")]
from iostore import load_container, read_chunk
from verify_conifer_attributes_v4 import digest
from verify_conifer_attributes_v4 import read as gltf
from verify_pwr_pine import compare_triangles, load
from verify_pwr_surface_cook import imported_packages

LEAF = "SM_PWR_SweepBendPine_OpenA"
MESH = "/Game/MJOLNIR/GrassPilot/Playable/" + LEAF
PARENT = ROOT / "out/pwr/visual-v5/outcrops-v4/trees"
OODLE = Path(
    "C:/Program Files/Epic Games/UE_5.5/Engine/Binaries/DotNET/UnrealBuildTool/oo2core_9_win64.dll"
)


def source_subset(folder):
    witness = json.loads((folder / "canopy.json").read_text())
    source = folder / "open-canopy.glb"
    original = PARENT / "mature-pine-a.glb"
    if (
        digest(source) != witness["glb_sha256"]
        or digest(original) != witness["original_sha256"]
        or witness["target_mesh"] != MESH
    ):
        raise ValueError("Open crown source hashes differ")
    d, a = gltf(original)
    r, b = gltf(source)
    removed = np.array(witness["removed_authoring_cluster_indices"])
    keep = np.ones(592, bool)
    keep[removed] = False
    if len(removed) != 24 or len(np.unique(removed)) != 24:
        raise ValueError("Unexpected open crown inventory")
    for i, (before, after) in enumerate(
        zip(d["meshes"][0]["primitives"], r["meshes"][0]["primitives"], strict=True)
    ):
        if set(before["attributes"]) != set(after["attributes"]):
            raise ValueError("Original source attributes missing")
        for key in before["attributes"]:
            if not np.array_equal(
                a(before["attributes"][key]), b(after["attributes"][key])
            ):
                raise ValueError("Source attributes differ: " + key)
        indices = a(before["indices"]).ravel()
        if i == 1:
            indices = indices.reshape(592, 137 * 3)[keep].ravel()
        if not np.array_equal(indices, b(after["indices"]).ravel()):
            raise ValueError("Open canopy retained triangles differ")
    return witness


def counts(meshes):
    return {
        m["name"]: {s["name"]: len(s["attrs"]["POSITION"]) for s in m["primitives"]}
        for m in meshes
    }


def verify(paks, art, cli):
    paks, art, cli = Path(paks).resolve(), Path(art).resolve(), Path(cli).resolve()
    folder = art / "pine"
    report = folder / "cooked-canopy.json"
    witness = source_subset(folder)
    (toc,) = tuple(paks.glob("pakchunk965*.utoc"))
    owner = load_container(toc)
    name = LEAF + ".uasset"
    (path,) = tuple(p for p in owner.files if Path(p).name == name)
    if not path.replace("\\", "/").endswith("MJOLNIR/GrassPilot/Playable/" + name):
        raise ValueError("Different 965 pine package")
    siblings = {
        p: hashlib.sha256(
            read_chunk(owner, owner.chunks[j], oodle_roots=[OODLE])
        ).hexdigest()
        for p, j in owner.files.items()
        if Path(p).stem == LEAF
    }
    raw = read_chunk(owner, owner.chunks[owner.files[path]], oodle_roots=[OODLE])
    digest0 = hashlib.sha256(raw).hexdigest()
    editor = json.loads((folder / "editor-import.receipt.json").read_text())
    if (
        editor["source_sha256"] != witness["glb_sha256"]
        or editor["mesh"].split(".")[0] != MESH
        or editor["chunk"] != 965
    ):
        raise ValueError("Different editor pine")
    proof_key = {
        "package_hashes": siblings,
        "source_sha256": witness["glb_sha256"],
        "pruning_proof_sha256": digest(folder / "canopy.json"),
        "verifier_sha256": digest(Path(__file__)),
        "triangle_audit_sha256": digest(ROOT / "tools/level/verify_pwr_pine.py"),
    }
    if report.exists():
        cached = json.loads(report.read_text())
        if cached.get("key") == proof_key and cached.get("passed"):
            return cached
    with tempfile.TemporaryDirectory(dir=folder) as td:
        temp = Path(td)
        asset = temp / name
        asset.write_bytes(raw)
        refs = imported_packages(asset)
        material_paths = [v.split(".")[0] for v in editor["materials"].values()]
        if refs != material_paths:
            raise ValueError(f"Wrong cooked pine material imports {refs}")
        cooked = temp / "readback.glb"
        command = [
            str(cli),
            "mesh",
            "export",
            "--paks",
            str(paks),
            "--asset",
            LEAF,
            "--out",
            str(cooked),
        ]
        if OODLE.is_file():
            command += ["--oodle", str(OODLE)]
        result = subprocess.run(command, check=True, capture_output=True, text=True)
        (folder / "cooked-mesh-export.log").write_text(result.stdout + result.stderr)
        src = load(folder / "open-canopy.glb")[0]
        meshes = load(cooked)
        (classic,) = tuple(
            m for m in meshes if m["extras"].get("decodedUvColorComplete")
        )
        (nanite,) = tuple(
            m for m in meshes if not m["extras"].get("decodedUvColorComplete")
        )
        if len(meshes) != 2 or classic["extras"].get("nativeUvChannelCount") != 3:
            raise ValueError("Expected native Nanite plus full-attribute fallback")
        original_counts = counts(load(PARENT / "native/package-readback.glb"))
        new_counts = counts(meshes)
        if any(
            t != {"MI_Pine_Tree_Mat": 30043, "MI_Branch_Mat": 77816}
            for t in new_counts.values()
        ):
            raise ValueError("Different cooked canopy triangle counts")
        full = [
            compare_triangles(a, b)
            for a, b in zip(src["primitives"], classic["primitives"], strict=True)
        ]
        geometry = [
            compare_triangles(a, b, False)
            for a, b in zip(src["primitives"], nanite["primitives"], strict=True)
        ]
        proof = {
            "schema": "pwr-pruned-single-pine-cooked-v1",
            "passed": True,
            "key": proof_key,
            "package": path,
            "chunk": 965,
            "cooked_package_sha256": digest0,
            "cooked_export_sha256": digest(cooked),
            "parent_cooked_lod_slot_counts": original_counts,
            "open_crown_cooked_lod_slot_counts": new_counts,
            "cooked_material_imports": refs,
            "source_whole_sprays_removed": witness["removed_sprays"],
            "source_all_wood_triangles_exact": True,
            "source_retained_attributes_exact": True,
            "classic_full_attribute_triangle_parity": full,
            "nanite_geometry_parity": geometry,
        }
    report.write_text(json.dumps(proof, indent=2) + "\n")
    return proof


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--paks", type=Path, required=True)
    parser.add_argument("--art", type=Path, required=True)
    parser.add_argument("--cli", type=Path, default=ROOT / "target/release/mjolnir.exe")
    args = parser.parse_args()
    print(json.dumps(verify(args.paks, args.art, args.cli), indent=2))
