"""Cook the PWR canopy and detachable pack. Outputs stay in out/pwr/canopy-v2."""
import argparse
import hashlib
import json
import os
import re
import shutil
import struct
import subprocess
import sys
from pathlib import Path


SOURCE = Path(__file__).resolve().parent
REPO = SOURCE.parents[4]
OUTPUT = REPO / "out/pwr/canopy-v2"
PROJECT = REPO / "unreal/MJOLNIRMaterials"
STAGE = PROJECT / "Saved/StagedBuilds/Windows/Meteorite/Content/Paks"
CONTAINER = "pakchunk957-MJOLNIRPWRCHUTEV2_P"
sys.path.insert(0, str(REPO / "tools/iostore"))
from iostore import load_container


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def cli_path(variable, local_build):
    candidates = [os.environ.get(variable), local_build, os.environ.get("MJOLNIR"),
                  REPO / "target/release/mjolnir.exe", REPO / "target/debug/mjolnir.exe"]
    for path in candidates:
        if path and Path(path).is_file():
            return Path(path).resolve()
    raise FileNotFoundError(f"Build blam-cli or set {variable} to a compatible mjolnir.exe")


def run(label, args, env):
    result = subprocess.run([str(arg) for arg in args], cwd=REPO, env=env, capture_output=True, text=True)
    log = result.stdout + result.stderr
    (OUTPUT / (label + ".log")).write_text(log, encoding="utf-8")
    if result.returncode:
        raise RuntimeError(f"{label} failed ({result.returncode}): {log[-1600:]}")
    return log


def packages(container):
    mount = container.mount_point.rstrip("/") + "/"
    return {(mount + path).split("/Content/", 1)[1].removesuffix(".uasset")
            for path in container.files if path.endswith(".uasset")}


def pack():
    editor = json.loads((OUTPUT / "editor-import.json").read_text())
    if any(digest(SOURCE / name) != value for mesh in editor["meshes"] for name, value in mesh["source_sha256"].items()):
        raise ValueError("Canopy sources changed since import")
    if digest(SOURCE / "geometry-report.json") != editor["source_report_sha256"]:
        raise ValueError("Grip positions changed since import")
    for name, expected_hash in editor["textile_source_sha256"].items():
        if digest(SOURCE / name) != expected_hash:
            raise ValueError(f"Textile source changed since import: {name}")
    container = load_container(STAGE / "pakchunk957-Windows.utoc")
    owned = packages(container)
    expected = {path.removeprefix("/Game/") for path in editor["packages"]}
    if owned != expected:
        raise ValueError(f"Unexpected contents for chunk 957: {owned.symmetric_difference(expected)}")
    shaders = [path for path in container.files if path.endswith(".ushaderbytecode")]
    if len(shaders) != 1 or "Chunk957-PCD3D_SM6" not in shaders[0] or not any(
        entry.type_name == "ShaderCode" and entry.length for entry in container.chunks
    ):
        raise ValueError("Chunk 957 is missing its SM6 shader library or shader payload")
    for toc in STAGE.glob("pakchunk*-Windows.utoc"):
        if toc.name == "pakchunk957-Windows.utoc":
            continue
        if expected.intersection(packages(load_container(toc))):
            raise ValueError(f"Duplicate ownership of parachute content in {toc.name}")
    audit = OUTPUT / "readback"
    audit.mkdir(exist_ok=True)
    files = {}
    for suffix in ("pak", "ucas", "utoc"):
        source = STAGE / f"pakchunk957-Windows.{suffix}"
        target = audit / f"{CONTAINER}.{suffix}"
        shutil.copy2(source, target)
        files[target.name] = digest(target)
    for suffix in ("ucas", "utoc"):
        source = STAGE / f"global.{suffix}"
        shutil.copy2(source, audit / source.name)
    cli = cli_path("MJOLNIR_MESH_EXPORT", REPO / "out/pwr/toolchain-mesh-attrs-v2/mjolnir.exe")
    for mesh in editor["meshes"]:
        package, name = mesh["mesh"].split(".")
        output = audit / (name + ".glb")
        run(name, [cli, "mesh", "export", "--paks", audit, "--asset", package.removeprefix("/Game/"),
                   "--out", output], os.environ)
        data = output.read_bytes()
        length = struct.unpack_from("<I", data, 12)[0]
        glb = json.loads(data[20:20 + length])
        lods = [lod["primitives"] for lod in glb["meshes"]]
        primitives = lods[0]
        slots = [glb["materials"][p["material"]]["name"] for p in primitives]
        counts = [sum(glb["accessors"][p["indices"]]["count"] for p in lod) // 3 for lod in lods]
        if slots != mesh["slots"] or counts != mesh["lod_triangles"] or counts[0] != mesh["triangles"]:
            raise ValueError(f"{name}: cooked slots {slots} or LOD counts {counts} differ from source")
        if any("TEXCOORD_1" not in p["attributes"] for p in primitives):
            raise ValueError(f"{name}: missing the metric fabric UV channel")
        mesh["cooked_lod_triangles"] = counts
    socket_data = run("cooked-sockets", [cli, "ue", "scan", "--paks", audit, "--package", "SM_PWR_ParachuteV2",
        "--class", "StaticMeshSocket"], os.environ)
    sockets = re.findall(r"SocketName = (\w+).*?RelativeLocation = ([-.\d,]+)", socket_data, re.S)
    points = {name: [float(x) for x in coords.split(",")] for name, coords in sockets}
    if points != editor["meshes"][0]["grip_sockets_ue_cm"]:
        raise ValueError(f"Cooked grip positions differ: {points}")
    texture = run("cooked-ripstop", [cli, "texture", "info", "--paks", audit, "--asset", "T_PWR_Ripstop"], os.environ)
    if not re.search(r"size\s+256x256\b", texture) or not re.search(r"mips\s+9\b", texture):
        raise ValueError("Missing expected 256px fabric tile and mip chain")
    textile_readback = {}
    for name, formats in (("T_PWR_GripTextile", {"PF_DXT5","PF_BC7"}), ("T_PWR_GripNormal", {"PF_BC5"})):
        info = run("cooked-" + name, [cli,"texture","info","--paks",audit,"--asset",name], os.environ)
        if not re.search(r"size\s+1024x512\b",info) or not re.search(r"mips\s+11\b",info):
            raise ValueError(f"Missing expected full 512px textile mip chain for {name}")
        match = re.search(r"format\s+(\w+)", info)
        if not match or match[1] not in formats:
            raise ValueError(f"Incorrect textile texture channels for {name}")
        textile_readback[name] = {"size":[1024,512], "mips":11,"format":match[1]}
    receipt = {"meshes": editor["meshes"], "files_sha256": files, "container": CONTAINER,
               "textile_source_sha256":editor["textile_source_sha256"],"textile_readback":textile_readback,
               "owned_packages": sorted(owned), "shaders": shaders, "installed": False}
    dest = OUTPUT / "cooked"
    dest.mkdir(exist_ok=True)
    for name in files:
        temp = dest / (name + ".tmp")
        shutil.copy2(audit / name, temp)
        temp.replace(dest / name)
    temp = dest / "receipt.json.tmp"
    temp.write_text(json.dumps(receipt, indent=2) + "\n")
    temp.replace(dest / "receipt.json")
    print(f"Verified {len(owned)} packages for {CONTAINER} in {dest}", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package-only", action="store_true", help="Verify a completed game-layout cook")
    args = parser.parse_args()
    OUTPUT.mkdir(parents=True, exist_ok=True)
    if not args.package_only:
        env = os.environ.copy()
        env.setdefault("MJ_CPU_MASK", "0F")
        env["MJOLNIR_RETARGET"] = str(cli_path("MJOLNIR_RETARGET", REPO / "out/pwr/toolchain-grass-v7/r2/mjolnir.exe"))
        run("editor", ["pwsh", "-NoProfile", "-File", "tools/ue/editor_cmd.ps1", "-Script", "Scripts/build_pwr_canopy.py"], env)
        print("Imported rig, pack, materials and handle sockets", flush=True)
        run("cook-retarget", ["pwsh", "-NoProfile", "-File", "tools/ue/cook.ps1", "-Classes",
                              "Material,MaterialInstanceConstant,StaticMesh,StaticMeshSocket"], env)
        print("Unreal cook and retarget complete", flush=True)
    pack()


if __name__ == "__main__":
    main()
