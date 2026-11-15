"""Build the small cosmetic parachute with the established native mesh writer.

No UE editor cook or game installation. The source geometry is original; the
generated package imports the installed BasicShapeMaterial. Runtime must disable
collision on the spawned mesh component, whose donor carries a body setup.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[3]
PACKAGE = "/Game/MJOLNIR/Maps/PWR/SM_PWR_Parachute"
MATERIAL = "/Engine/BasicShapes/BasicShapeMaterial"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--paks", type=Path, default=Path("C:/Program Files (x86)/Steam/steamapps/common/Halo Campaign Evolved/Meteorite/Content/Paks"))
    parser.add_argument("--output", type=Path, default=REPO / "out/pwr/canopy")
    parser.add_argument("--blender", type=Path, default=Path("C:/Program Files/Blender Foundation/Blender 5.1/blender.exe"))
    parser.add_argument("--skip-geometry", action="store_true")
    parser.add_argument("--preview", action="store_true")
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    if output == args.paks.resolve() or args.paks.resolve() in output.parents:
        raise ValueError("Build outputs must stay outside the game installation")

    def run(name, command):
        result = subprocess.run([str(c) for c in command], cwd=REPO, capture_output=True, text=True)
        log = result.stdout + result.stderr
        (output / (name + ".log")).write_text(log, encoding="utf-8")
        if result.returncode or "MISMATCH" in log or "Traceback (most recent" in log:
            raise RuntimeError(f"{name} failed; see {output / (name + '.log')}:\n{log[-1500:]}")
        print(f"PWR canopy: {name} passed", flush=True)
        return log

    if not args.skip_geometry:
        command = [args.blender, "--background", "--factory-startup", "--python-exit-code", "1",
                   "--python", ROOT / "build_geometry.py", "--", "--output", ROOT]
        if args.preview:
            command += ["--preview", output / "preview.png"]
        run("geometry", command)
    uasset = output / "SM_PWR_Parachute.uasset"
    log = run("mesh", [REPO / "target/release/examples/mesh_rewrite.exe", args.paks,
                       "basicshapes/cylinder", ROOT / "pwr_canopy.gltf", uasset,
                       "--offset", "0,0,0", "--rename", PACKAGE,
                       "--material", f"Canopy={MATERIAL}=*",
                       "--material", f"Cords={MATERIAL}=cords$", "--asset-imports", "--selftest"])
    match = re.search(r"SPAWN: location \(([-\d.]+), ([-\d.]+), ([-\d.]+)\) cm, uniform scale ([\d.]+)", log)
    if not match:
        raise RuntimeError("Mesh writer did not report its normalization transform")
    x, y, z, scale = map(float, match.groups())
    name = "pakchunk964-MJOLNIRPWRCHUTE_P"
    run("package", [REPO / "target/release/examples/package_add.exe", args.paks, output,
                    "--name", name, "--package", f"{PACKAGE}={uasset}"])
    # An installed empty stub accompanies the IoStore pair for mounting.
    stub = args.paks / "pakchunk115-Windows.pak"
    if not stub.is_file():
        raise FileNotFoundError(f"Established IoStore mount stub missing: {stub}")
    shutil.copy2(stub, output / (name + ".pak"))
    geometry = json.loads((ROOT / "geometry-report.json").read_text())
    metadata = {
        "mesh": PACKAGE + ".SM_PWR_Parachute",
        "relative_offset_cm": [x, y, z], "relative_rotation_deg": [0, 0, 0],
        "uniform_scale": scale, "collision_enabled": False, "cast_shadow": False,
        "visible_phase": "native player stage 4 only; presentation, never simulation",
        "material_slots": [
            {"index": 0, "name": "Canopy", "material": MATERIAL + ".BasicShapeMaterial",
             "vector_parameter": "Color", "color": [.16, .22, .11, 1]},
            {"index": 1, "name": "Cords", "material": MATERIAL + ".BasicShapeMaterial",
             "vector_parameter": "Color", "color": [.06, .07, .055, 1]},
        ],
        "source_geometry": geometry,
        "container": name,
        "files": {suffix: {"path": str(output / (name + suffix)),
                            "sha256": hashlib.sha256((output / (name + suffix)).read_bytes()).hexdigest()}
                  for suffix in (".utoc", ".ucas", ".pak")},
    }
    (output / "canopy.runtime.json").write_text(json.dumps(metadata, indent=2) + "\n")
    print(json.dumps({k: metadata[k] for k in ("mesh", "relative_offset_cm", "uniform_scale", "container")}, indent=2))


if __name__ == "__main__":
    main()
