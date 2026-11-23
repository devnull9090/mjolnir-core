"""Verify and stage the private PWR tactical widget after an editor cook."""
import argparse
import hashlib
import json
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile
from pathlib import Path


ART = Path(__file__).resolve().parent
REPO = ART.parents[3]
STAGE = REPO / "unreal/MJOLNIRMaterials/Saved/StagedBuilds/Windows/Meteorite/Content/Paks"
OUTPUT = REPO / "out/pwr/tactical-map-ui-v2"
STEM = "pakchunk958-MJOLNIRTACTICALMAP_P"
WIDGET = "/Game/MJOLNIR/UI/WBP_MJOLNIRTacticalMap"
# The warfare zone tiles under the score (build_pwr_warfare_zones.py) share the chunk.
ZONES = "/Game/MJOLNIR/UI/WBP_MJOLNIRWarfareZones"
# Its hexagon badges (tools/ue/draw_zone_badges.py), imported as T_PWR_Zone<name>.
ZONE_BADGES = ("HexRim", "HexFill")
sys.path.insert(0, str(REPO / "tools/iostore"))
from iostore import load_container


def packages(toc):
    container = load_container(toc)
    return {(container.mount_point.rstrip("/") + "/" + name).split("/Content/", 1)[1]
            for name in container.files if name.endswith(".uasset")}


def inspect(cli, arguments):
    return subprocess.run([str(cli), *map(str, arguments)], cwd=REPO, capture_output=True,
                          text=True, check=True).stdout


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    candidates = [REPO / "target/release/mjolnir.exe", REPO / "target/debug/mjolnir.exe",
                  REPO / "out/pwr/toolchain-mesh-attrs-v2/mjolnir.exe"]
    parser.add_argument("--cli", type=Path, default=os.environ.get("MJOLNIR") or
                        next((path for path in candidates if path.is_file()), None))
    args = parser.parse_args()
    if not args.cli or not args.cli.is_file():
        parser.error("Build blam-cli or provide --cli with its path")
    images = json.loads((ART / "manifest.json").read_text())["files"]
    widget = WIDGET.removeprefix("/Game/") + ".uasset"
    expected = {widget, ZONES.removeprefix("/Game/") + ".uasset",
                *("MJOLNIR/TacticalMap/T_PWR_" + Path(row["path"]).stem + ".uasset" for row in images),
                *(f"MJOLNIR/TacticalMap/T_PWR_Zone{name}.uasset" for name in ZONE_BADGES)}
    source = STAGE / "pakchunk958-Windows.utoc"
    if packages(source) != expected:
        raise ValueError("Expected the private overview widget, the zone bars, their two badges and eight map textures in chunk 958")
    for toc in STAGE.glob("pakchunk*-Windows.utoc"):
        if toc != source and packages(toc).intersection(expected):
            raise ValueError(f"Another staged chunk also owns tactical content: {toc.name}")
    OUTPUT.mkdir(parents=True, exist_ok=True)
    dest = OUTPUT / "cooked"
    dest.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(dir=OUTPUT) as temp:
        audit = Path(temp)
        for suffix in ("ucas", "utoc"):
            name = f"global.{suffix}"
            shutil.copy2(STAGE / name, audit / name)
        files = []
        for suffix in ("pak", "ucas", "utoc"):
            item = audit / f"{STEM}.{suffix}"
            shutil.copy2(source.with_suffix("." + suffix), item)
            files.append({"path": str(dest / item.name), "sha256": hashlib.sha256(item.read_bytes()).hexdigest(),
                          "bytes": item.stat().st_size})
        layout = inspect(args.cli, ["ue", "get", "--paks", audit, "--package", WIDGET])
        class_name = WIDGET.split("/")[-1] + "_C"
        required = [class_name + " : WidgetBlueprintGeneratedClass", "MapClip : CanvasPanel", "Overview : Image",
                    "MapMarks : CanvasPanel", "ScoreTitle : TextBlock"]
        required.extend(f"Mark{i} : Image" for i in range(64))
        required.extend(f"Label{i} : TextBlock" for i in range(64))
        if not layout.startswith(WIDGET) or any(pattern not in layout for pattern in required):
            raise ValueError("Cooked overview class, map canvas or 64 marker and label pairs did not read back")
        (OUTPUT / "widget-readback.txt").write_text(layout)
        zones = inspect(args.cli, ["ue", "get", "--paks", audit, "--package", ZONES])
        needed = [f"Zone{i}{part}" for i in range(3) for part in ("Rim", "Tint", "Letter", "State", "Fill", "Ink",
                                                                  "RedPipSize", "BluePipSize")]
        if not zones.startswith(ZONES) or any(name not in zones for name in needed):
            raise ValueError("Cooked zone tiles did not read back")
        (OUTPUT / "zones-readback.txt").write_text(zones)
        for row in images:
            png = REPO / row["path"]
            data = png.read_bytes()
            if hashlib.sha256(data).hexdigest() != row["sha256"]:
                raise ValueError(f"Map art has changed since the terrain manifest was recorded: {png.name}")
            width, height = struct.unpack(">II", data[16:24])
            description = inspect(args.cli, ["texture", "info", "--paks", audit, "--asset", "T_PWR_" + png.stem])
            if not re.search(rf"size\s+{width}x{height}\b", description):
                raise ValueError(f"Cooked map texture dimensions differ: {png.name}")
        for row in files:
            target = Path(row["path"])
            (audit / target.name).replace(target)
        receipt = {"schema": "pwr-tactical-map-cook-v3", "widget_class": f"{WIDGET}.{class_name}",
                   "pooled_markers": 64, "zone_widget": f"{ZONES}.{ZONES.split('/')[-1]}_C", "owned_packages": sorted(expected), "installed": False, "files": files}
        proof = audit / "receipt.json"
        proof.write_text(json.dumps(receipt, indent=2) + "\n")
        proof.replace(dest / proof.name)
    print(f"Verified the PWR overview, 64 markers and {len(images)} textures in {dest}")


if __name__ == "__main__":
    main()
