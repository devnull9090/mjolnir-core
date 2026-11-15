"""Inspect shipped grass geometry before authoring the visual6 meadow candidate.

This CPU-only extraction does not change the installed map, select PCG points,
or launch an editor. Native materials and existing source UV/color data remain
owned by each shipped mesh.
"""
from pathlib import Path
import argparse
import hashlib
import json
import struct
import subprocess

ROOT = Path(__file__).resolve().parents[4]
OUT = ROOT / "out/pwr/visual-v6/scenery/native-grass-source"
PAKS = Path("C:/Program Files (x86)/Steam/steamapps/common/Halo Campaign Evolved/Meteorite/Content/Paks")
ASSETS = [
    "/Game/Megascans/3D_Plants/Tall_Grass_rbeki/SM_Tall_Grass_rbeki_01",
    "/Game/Env/Bio/Grass/Sedges/Grass_Sedges_A/SM_Grass_Sedges_A_Leaves_A",
    "/Game/Env/Bio/Grass/Sedges/Grass_Sedges_A/SM_Grass_Sedges_A_Leaves_C",
    "/Game/Env/Bio/Grass/Rushes/Grass_Rushes_A/SM_Grass_Rushes_A",
    "/Game/Env/Bio/Grass/GroundcoverClump/Grass_GroundcoverClump_A/SM_Grass_GroundcoverClump_A",
]


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def extract(cli, out=OUT, paks=PAKS):
    out = Path(out)
    folder = out / "assets"
    folder.mkdir(parents=True, exist_ok=True)
    assets = []
    for asset in ASSETS:
        leaf = asset.rsplit("/", 1)[-1]
        glb = folder / (leaf + ".glb")
        if not glb.is_file():
            run = subprocess.run([str(cli), "mesh", "export", "--paks", str(paks),
                                  "--asset", asset.removeprefix("/Game/"), "--out", str(glb)],
                                 capture_output=True, text=True)
            (folder / (leaf + ".log")).write_text(run.stdout + run.stderr)
            if run.returncode:
                raise RuntimeError(f"Native mesh extraction failed for {asset}; see saved log")
        data = glb.read_bytes()
        document = json.loads(data[20:20 + struct.unpack_from("<I", data, 12)[0]])
        lods = []
        for mesh in document["meshes"]:
            mins, maxs = [], []
            for primitive in mesh["primitives"]:
                accessor = document["accessors"][primitive["attributes"]["POSITION"]]
                mins.append(accessor["min"])
                maxs.append(accessor["max"])
            low = [min(row[i] for row in mins) for i in range(3)]
            high = [max(row[i] for row in maxs) for i in range(3)]
            # Exporter glTF Y-up metres -> native Unreal centimetres (X,Z,Y).
            bounds = {"minimum_ue_cm": [low[0]*100, low[2]*100, low[1]*100],
                      "maximum_ue_cm": [high[0]*100, high[2]*100, high[1]*100]}
            lods.append({"name": mesh.get("name"), "bounds": bounds,
                         "height_m": high[1] - low[1],
                         "width_m": high[0] - low[0], "depth_m": high[2] - low[2],
                         "triangles": sum(document["accessors"][p["indices"]]["count"] // 3 for p in mesh["primitives"]),
                         "native_attributes": mesh.get("extras", {}),
                         "material_slots": [document["materials"][p["material"]]["name"] for p in mesh["primitives"]]})
        assets.append({"mesh": asset + "." + leaf, "glb": str(glb.resolve()), "sha256": digest(glb), "lods": lods})
        print(json.dumps({"asset": leaf, "lod0": lods[0], "lod_count": len(lods)}), flush=True)
    result = {"schema": "pwr-native-meadow-inspection-v1", "assets": assets,
              "exporter": str(Path(cli).resolve()), "exporter_sha256": digest(cli),
              "scope": "Actual shipped geometry inspection only; candidate placement, actual PCG and installed appearance/FPS pending."}
    (out / "assets.receipt.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cli", type=Path, default=ROOT / "out/pwr/toolchain-mesh-attrs-v2/mjolnir.exe")
    parser.add_argument("--out", type=Path, default=OUT)
    parser.add_argument("--paks", type=Path, default=PAKS)
    args = parser.parse_args()
    extract(args.cli, args.out, args.paks)
