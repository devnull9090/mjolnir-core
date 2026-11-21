"""Stage the PWR map, portal markings, canopy and two match profiles offline."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import zipfile


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / "tools/level"))
from pack_local_map import prepare


def load(path):
    return Path(path).read_text(encoding="utf-8")


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, type=Path, help="New playtest folder")
    parser.add_argument("--guides", required=True, type=Path, help="Verified portal package.json")
    parser.add_argument("--canopy", required=True, type=Path, help="Verified canopy receipt.json")
    parser.add_argument("--runtime", required=True, help="Installed CE content version or range")
    parser.add_argument("--version", default="0.1.0-playtest.2")
    args = parser.parse_args()
    cli = ROOT / "target/release/mjolnir.exe"
    original = json.loads(load(HERE / "upgrade-bases-v1.json"))["PWR"]
    world = Path(original["conversion"]).parent / "upgrade"
    guides, canopy = json.loads(load(args.guides)), json.loads(load(args.canopy))
    guide_stem = Path(guides["stem"])
    canopy_stem = args.canopy.resolve().parent / canopy["container"]
    # The first mode bundle owned the passenger Pelican and the fallback
    # canopy separately from the landscape. Clean player installs need both.
    pelican_root = ROOT / "out/pwr/pelican"
    pelican = json.loads(load(pelican_root / "pelican-build.json"))
    pelican_stem = pelican_root / "pakchunk971-MJOLNIRPWRPELICAN_P"
    legacy_root = ROOT / "out/pwr/canopy"
    legacy = json.loads(load(legacy_root / "canopy.runtime.json"))
    fallback_stem = legacy_root / legacy["container"]
    hashes = {guide_stem.with_suffix(ext): sha for ext, sha in guides["files"].items()}
    hashes.update({canopy_stem.parent / name: sha for name, sha in canopy["files_sha256"].items()})
    hashes.update({pelican_root / row["name"]: row["sha256"] for row in pelican["files"]})
    hashes.update({fallback_stem.with_suffix(ext): row["sha256"] for ext, row in legacy["files"].items()})
    for path, expected in hashes.items():
        if digest(path) != expected:
            raise ValueError(f"Changed art package since verification: {path}")
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    insertion = [str(path) for path in (guide_stem, canopy_stem, pelican_stem, fallback_stem)]
    config = dict(original, extra_containers=[*original["extra_containers"], *insertion])
    stage = prepare("PWR", config, world, out / "map-input")
    level_path = stage / "pwr.level.json"
    original_level = json.loads(load(level_path))
    level = dict(original_level, decor=[*original_level["decor"], *guides["decor"]])
    ids = [row["id"] for row in level["decor"] if "id" in row]
    if len(ids) != len(set(ids)):
        raise ValueError("Portal guides conflict with other level decorations")
    level_path.write_text(json.dumps(level, indent=2) + "\n", encoding="utf-8")
    profiles = {}
    for name, extra in (("fireteam", []), ("solo-rehearsal", ["--minimum-players", "1", "--warmup-seconds", "5"])):
        rules = out / "variants" / name / "warfare.mglo"
        rules.parent.mkdir(parents=True)
        subprocess.run([cli, "megalo", "write", "--mode", "warfare", "--vehicle-label-pool",
                        "--allow-mounted-capture", *extra, "--out", rules], check=True, cwd=ROOT)
        profiles[name] = {p.name: digest(p) for p in (rules, rules.with_suffix(".layout.json"))}
    archive = out / f"pelican-warfare-{args.version}.mjolnir"
    subprocess.run([cli, "map", "pack", stage, "--code", "PWR", "--runtime", args.runtime,
                    "--version", args.version, "--slug", "pelican-warfare", "--name", "Pelican Warfare",
                    "--size", "large", "--vehicles", "true", "--out", archive], check=True, cwd=ROOT)
    # Check the archive itself. Match every staged pair and every loose map
    # member. Registration is typed and reserialized by the packer.
    expected = {}
    for path in stage.rglob("*"):
        if not path.is_file() or path.suffix == ".pak":
            continue
        if path.suffix in (".utoc", ".ucas"):
            member = "content/" + path.name
        elif path == level_path:
            member = "map/level.json"
        elif path.name == "PWR.registration.json":
            member = "map/registration.json"
        else:
            member = "map/" + path.relative_to(stage).as_posix()
        expected[member] = path
    with zipfile.ZipFile(archive) as packed:
        if sorted(packed.namelist()) != sorted([*expected, "mjolnir.json"]):
            raise ValueError("Archive members differ from the complete stage")
        for member, path in expected.items():
            with packed.open(member) as stream:
                if member == "map/registration.json":
                    valid = json.load(stream) == json.loads(load(path))
                else:
                    valid = hashlib.file_digest(stream, "sha256").hexdigest() == digest(path)
                if not valid:
                    raise ValueError(f"Incorrect archived content: {member}")
    receipt = {"archive": archive.name, "sha256": digest(archive), "bytes": archive.stat().st_size,
               "ce_content_runtime": args.runtime, "complete_map_members": sorted(expected),
               "new_placement_ids": [row["id"] for row in guides["decor"]], "variants": profiles,
               "map_source": str(world / "PWR" / "level.json"), "installed": False}
    (out / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(f"Verified {archive} ({receipt['sha256']})")


if __name__ == "__main__":
    main()
