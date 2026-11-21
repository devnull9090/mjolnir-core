"""Stage trusted PWR match data beside a private runtime overlay."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys


ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools/iostore"))
from iostore import load_container


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--saturday", required=True, type=Path, help="Output of stage_playtest.py")
    parser.add_argument("--stage", required=True, type=Path, help="Private runtime build folder under out/")
    parser.add_argument("--tactical", type=Path, help="Reviewed cook receipt for the optional map UI")
    args = parser.parse_args()
    stage = args.stage.resolve()
    if not stage.is_relative_to((ROOT / "out").resolve()) or not (stage / "mods").is_dir():
        raise ValueError("Expected an existing private runtime build folder")
    build = json.loads((args.saturday / "receipt.json").read_text())
    loader = Path("mods/MJOLNIRLevelLoader")
    descriptor = loader / "Scripts/mode_descriptors.lua"
    sources = [(ROOT / descriptor, descriptor, digest(ROOT / descriptor))]
    for name in ("warfare.mglo", "warfare.layout.json"):
        path = args.saturday / "variants/fireteam" / name
        sources.append((path, loader / "variants" / name, build["variants"]["fireteam"][name]))
    widget_path = None
    if args.tactical:
        assets = args.tactical.resolve().parent
        tactical = json.loads(args.tactical.read_text())
        expected = "pakchunk958-MJOLNIRTACTICALMAP_P"
        widget_path = "Meteorite/Content/MJOLNIR/UI/WBP_MJOLNIRTacticalMap.uasset"
        container = load_container(assets / (expected + ".utoc"))
        if not any((container.mount_point.rstrip("/") + "/" + p).endswith(widget_path) for p in container.files):
            raise ValueError("Tactical UI cook lacks the expected UI widget")
        for ext in (".pak", ".ucas", ".utoc"):
            name = expected + ext
            row, = [r for r in tactical["files"] if Path(r["path"]).name == name]
            sources.append((assets / name, Path("content/paks") / name, row["sha256"]))
    for src, dst, sha in sources:
        if digest(src) != sha:
            raise ValueError(f"Staging source changed: {src}")
        if (stage / dst).exists() and digest(stage / dst) != sha:
            raise ValueError(f"Different candidate already exists: {stage / dst}")
    for src, dst, sha in sources:
        dest = stage / dst
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
        if digest(dest) != sha:
            raise ValueError(f"Write verification failed: {dest}")
    report = {"profile": "fireteam", "minimum_players": 2, "warmup_seconds": 30,
              "insertion_seconds": 60, "installed": False, "container_widget": widget_path,
              "files": {dst.as_posix(): sha for _, dst, sha in sources}}
    (stage / "mode-data.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"Verified {len(sources)} mode, layout and UI files under {stage}")


if __name__ == "__main__":
    main()
