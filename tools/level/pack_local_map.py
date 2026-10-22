"""Package a freshly built original map without an existing hub installation.

Uses the conversion and upgrade outputs, never the installed game's containers.
The staging folder is retained beside the archive so authors can inspect it.
"""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import uuid


REPO = Path(__file__).resolve().parents[2]


def prepare(code, config, work, staging):
    if not re.fullmatch(r"[A-Z0-9]{3}", code):
        raise ValueError("Map code must be three uppercase ASCII letters/digits")
    conv = Path(config["conversion"])
    upgraded = Path(work) / code
    level_path = upgraded / "level.json"
    level = json.loads(level_path.read_text(encoding="utf-8"))
    bake = conv if config.get("indoor") else upgraded / "bake"
    registration = bake / f"{code}.registration.json"
    if json.loads(registration.read_text(encoding="utf-8")).get("code") != code:
        raise ValueError("Registration code does not match the requested map")
    copies = [(level_path, f"{code.lower()}.level.json"),
              (registration, f"{code}.registration.json")]
    containers = [
        (conv / f"pakchunk985-MJOLNIRCOOK-{code}_P", None),
        (Path(config.get("mesh_container", conv / f"pakchunk986-MJOLNIRMESH-{code}_P")),
         f"pakchunk986-MJOLNIRMESH-{code}_P"),
        (bake / f"pakchunk997-MJOLNIRMAP-{code}_P", None),
    ]
    if not config.get("indoor"):
        containers.append((bake / f"pakchunk{config['chunk']}-MJOLNIRLAND-Windows",
                           f"pakchunk{config['chunk']}-MJOLNIRLAND-{code}_P"))
    for source, rename in containers:
        for extension in ("utoc", "ucas"):
            copies.append((Path(f"{source}.{extension}"), f"{rename or source.name}.{extension}"))

    def auxiliary(relative):
        # Level-controlled file names must stay within this map's work folder.
        path = Path(relative)
        source = (upgraded / path).resolve()
        if path.is_absolute() or not source.is_relative_to(upgraded.resolve()):
            raise ValueError(f"Auxiliary path escapes the map: {relative}")
        return source, path

    foliage = (level.get("foliage") or {}).get("file")
    if foliage:
        source, relative = auxiliary(foliage)
        copies.append((source, str(relative)))
    directories = []
    if (level.get("flux") or {}).get("state"):
        # flux.state is metadata; the binary textures live in flux_state/.
        if not isinstance(level["flux"]["state"], dict):
            raise ValueError("flux.state must contain baked domain metadata")
        source, relative = auxiliary("flux_state")
        if not (source / "state.json").is_file():
            raise FileNotFoundError(f"Missing baked water state: {source}")
        directories.append((source, relative))
    if (upgraded / "decals").is_dir():
        directories.append((upgraded / "decals", Path("decals")))
    missing = [str(source) for source, _ in copies if not source.is_file()]
    if missing:
        raise FileNotFoundError("Incomplete map build:\n" + "\n".join(missing))
    staging = Path(staging)
    staging.mkdir(parents=True, exist_ok=False)
    for source, relative in copies:
        destination = staging / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
    for source, relative in directories:
        if relative == Path("."):
            raise ValueError("Water state must be inside a named subfolder")
        shutil.copytree(source, staging / relative, dirs_exist_ok=True)
    return staging


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("code")
    parser.add_argument("--config", type=Path, default=REPO / "tools/level/ce_upgrade_maps.json")
    parser.add_argument("--work", type=Path, default=Path("C:/haloce/ce_conversions/upgrade"))
    parser.add_argument("--version", required=True)
    parser.add_argument("--runtime", required=True, help="Tested CE runtime version range")
    parser.add_argument("--slug", required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument("--summary", default="")
    parser.add_argument("--readme", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--cli", default=os.environ.get("MJOLNIR", str(REPO / "target/release/mjolnir.exe")))
    parser.add_argument("--sign", action="store_true")
    args = parser.parse_args()
    if args.out.exists():
        parser.error("Output already exists; choose a new release filename")
    config = json.loads(args.config.read_text(encoding="utf-8"))
    if args.code not in config:
        parser.error(f"Unknown map code: {args.code}")
    staging = args.out.resolve().parent / f"{args.code}-staging-{uuid.uuid4().hex[:8]}"
    prepare(args.code, config[args.code], args.work, staging)
    command = [args.cli, "map", "pack", str(staging), "--code", args.code,
               "--version", args.version, "--runtime", args.runtime, "--slug", args.slug,
               "--name", args.name, "--summary", args.summary, "--out", str(args.out.resolve())]
    if args.readme:
        command += ["--readme", str(args.readme.resolve())]
    if args.sign:
        command.append("--sign")
    print(f"Inspectable staging: {staging}", flush=True)
    subprocess.run(command, check=True)


if __name__ == "__main__":
    main()
