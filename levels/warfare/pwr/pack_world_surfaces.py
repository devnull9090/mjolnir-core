"""Seal the uniquely named PWR surface container after editor_cmd and the normal Unreal cook."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import struct
import sys

from world_surfaces import MATERIALS, SURFACES


REPO = Path(__file__).resolve().parents[3]
STAGE = REPO / "unreal/MJOLNIRMaterials/Saved/StagedBuilds/Windows/Meteorite/Content/Paks"
OUTPUT = REPO / "out/pwr/world-surfaces"
STEM = "pakchunk956-MJOLNIRPWRSURFACES_P"
sys.path[:0] = [str(REPO / "tools/iostore"), str(REPO / "tools/ue/shader_archive")]
from iostore import load_container, read_chunk
from shaderlib import parse_library
from zen_class import load_name_batch


def package_rows(container):
    prefix = container.mount_point.rstrip("/") + "/"
    return {"/Game/" + (prefix + name).split("/Content/", 1)[1].removesuffix(".uasset"): index
            for name, index in container.files.items() if name.endswith(".uasset")}


def seal(oodle):
    destination = OUTPUT / "cooked"
    destination.mkdir(exist_ok=True)
    candidate = load_container(STAGE / "pakchunk956-Windows.utoc")
    expected = set(json.loads((OUTPUT / "editor-assets.json").read_text()))
    owned = package_rows(candidate)
    if owned.keys() != expected or any(not name.startswith(SURFACES + "/") for name in owned):
        raise ValueError(f"Wrong 956 asset ownership: {sorted(expected.symmetric_difference(owned))}")
    for toc in STAGE.glob("pakchunk*-Windows.utoc"):
        if toc == candidate.utoc_path:
            continue
        if expected.intersection(package_rows(load_container(toc))):
            raise ValueError(f"Map surface package is also owned by {toc}")
    shaders = [i for name, i in candidate.files.items()
               if name.endswith("ShaderArchive-Meteorite_Chunk956-PCD3D_SM6-PCD3D_SM6.ushaderbytecode")]
    if len(shaders) != 1:
        raise ValueError("Missing PWR's own SM6 shader archive")

    def data(index):
        return read_chunk(candidate, candidate.chunks[index], oodle_roots=[oodle])

    library = parse_library(data(shaders[0]))
    groups = {chunk.chunk_id.to_bytes(8, "little") + chunk.chunk_index.to_bytes(2, "big")
              for chunk in candidate.chunks if chunk.type_name == "ShaderCode" and chunk.length}
    if not library.group_ids or not all(key[:10] in groups for key in library.group_ids):
        raise ValueError("Shader bytecode group is missing from the isolated PWR container")
    materials = {}
    for leaf in MATERIALS:
        name = SURFACES + "/" + leaf
        content = data(owned[name])
        imports, _ = load_name_batch(content, struct.unpack_from("<i", content, 48)[0])
        if any(key not in owned and not key.startswith("/Engine/") for key in imports):
            raise ValueError(f"Unexpected external material dependency for {name}: {imports}")
        maps = [key.hex() for key in library.map_hashes if key in content]
        if not maps:
            raise ValueError(f"{leaf} has no cooked shader map in its own library")
        materials[name] = {"imports": imports, "shader_maps": maps}
    files = {}
    for ext in ("pak", "utoc", "ucas"):
        target = destination / f"{STEM}.{ext}"
        temp = target.with_suffix(target.suffix + ".tmp")
        shutil.copy2(STAGE / f"pakchunk956-Windows.{ext}", temp)
        with temp.open("rb") as stream:
            files[target.name] = hashlib.file_digest(stream, "sha256").hexdigest()
        temp.replace(target)
    receipt = {"container": STEM, "files_sha256": files, "owned_packages": sorted(owned), "materials": materials,
               "shader_group_count": len(groups), "shader_count": len(library.shader_hashes)}
    temp = destination / "receipt.json.tmp"
    temp.write_text(json.dumps(receipt, indent=2) + "\n")
    temp.replace(destination / "receipt.json")
    print(f"Verified {len(owned)} surface packages, {len(library.shader_hashes)} SM6 shaders in {destination}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--oodle", type=Path, default=os.environ.get("OODLE_DLL",
        "C:/Program Files/Epic Games/UE_5.5/Engine/Binaries/DotNET/UnrealBuildTool/oo2core_9_win64.dll"))
    seal(parser.parse_args().oodle)
