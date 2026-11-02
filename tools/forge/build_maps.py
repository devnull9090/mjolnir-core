#!/usr/bin/env python3
"""Bake and package the original Forge maps locally.

Reads a Paks view containing the game, CE runtime and each required Forge pack.
Keeps every build in a fresh folder; never installs files or starts the game.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re
import shutil
import subprocess
import uuid
import zipfile


ROOT = Path(__file__).resolve().parents[2]
MAPS = {
    "blank": {"code": "FBK", "slug": "forge-canvas", "name": "Forge Canvas",
              "source": "blank/forge_canvas.level.json", "bsp": "blank.sbsp",
              "size": "large", "players": "1-16", "dimensions": [64, 64, 1]},
    "crossline": {"code": "FRB", "slug": "crossline", "name": "Crossline",
                  "source": "crossline/crossline.level.json", "bsp": "arena.sbsp",
                  "size": "small", "players": "2-8", "dimensions": [24, 40, 1]},
    "roadworks": {"code": "RWC", "slug": "roadworks-circuit", "name": "Roadworks Circuit",
                  "source": "roadworks/roadworks_circuit.level.json", "bsp": "circuit.sbsp",
                  "collision_dir": "forge-packs/roadworks/build/canvas",
                  "readme": "forge-maps/roadworks/README.md", "vehicles": True,
                  "size": "large", "players": "1-8", "dimensions": [160, 160, 1]},
}


def sha256(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def check_level(level, spec, packs, collision):
    """Bind the portable source to the exact pack and canvas being baked."""
    if level.get("canvas") != {"scenario": "B40", "origin": [0, 0, 0]}:
        raise ValueError("Forge maps must use the B40 donor at origin zero")
    blam = level.get("blam", {})
    if not level.get("multiplayer") or not blam.get("map_variant"):
        raise ValueError("Forge maps require multiplayer and blam.map_variant")
    if blam.get("active_bsps") != [8] or blam.get("single_bsp") != 8:
        raise ValueError("Canvas must use only source BSP 8, renumbered to zero")
    if isinstance(packs, dict):
        packs = [packs]
    catalogs = {p.get("forge_pack", {}).get("id"): p for p in packs}
    declared = blam.get("forge_packs", [])
    if len(catalogs) != len(packs) or not declared or len({p["slug"] for p in declared}) != len(declared):
        raise ValueError("Forge pack dependencies must be present and unique")
    wanted = []
    for dependency in declared:
        pack = catalogs.get(dependency["slug"], {})
        catalog = pack.get("forge_pack", {})
        blocks = [{"id": b["id"], "tag": b["tag"]} for b in catalog.get("blocks", [])]
        if not blocks:
            raise ValueError(f"Missing built Forge pack: {dependency['slug']}")
        wanted.append({"slug": catalog.get("id"), "version": pack.get("version"), "blocks": blocks})
    if declared != wanted:
        raise ValueError("Level Forge palette differs from the built pack; regenerate the levels or rebuild the pack")
    if bool(blam.get("vehicles")) != spec.get("vehicles", False):
        raise ValueError("Map vehicle metadata differs from its authored placements")
    slab = collision.get("slab_m", {})
    if [slab.get(k) for k in ("width", "depth", "thickness")] != spec["dimensions"] or slab.get("top_z") != 0:
        raise ValueError("Canvas collision dimensions do not match this map")
    if collision.get("bsp_index") != 0:
        raise ValueError("Canvas collision must be built for BSP index zero")
    bounds = blam.get("world_bounds", [])
    expected = collision.get("world_bounds_wu", {})
    if len(bounds) != 1 or bounds[0].get("bsp") != 8:
        raise ValueError("Level needs one world-bounds record for source BSP 8")
    for field in ("min", "max"):
        actual = bounds[0].get(field, [])
        target = expected.get(field, [])
        if len(actual) != 3 or len(target) != 3 or any(
            not math.isfinite(x) or not math.isclose(x, y, abs_tol=0.00001)
            for x, y in zip(actual, target)
        ):
            raise ValueError("Level world bounds differ from the canvas collision")


def check_pack_view(paks, manifest_path):
    pack = read_json(manifest_path)
    slug = pack.get("forge_pack", {}).get("id", "")
    if pack.get("type") != "content" or not re.fullmatch(r"[a-z0-9][a-z0-9-]{1,63}", slug):
        raise ValueError("--pack-manifest must describe a built Forge content pack")
    name = slug.capitalize()
    content = manifest_path.parent / "content"
    sources = sorted(p for p in content.iterdir() if p.suffix in (".utoc", ".ucas", ".pak"))
    if not sources or not any(p.suffix == ".utoc" for p in sources):
        raise FileNotFoundError(f"Build {name} content before baking maps")
    fingerprints = {}
    for path in sources:
        if path.suffix == ".utoc" and not path.with_suffix(".ucas").is_file():
            raise FileNotFoundError(f"Incomplete {name} container: {path}")
        # Offline lookup uses IoStore pairs; .pak mount siblings are not read
        # by the bake. The final pack/launcher supplies those at installation.
        if path.suffix == ".pak":
            continue
        candidate = paks / path.name
        fingerprint = sha256(path)
        if not candidate.is_file() or sha256(candidate) != fingerprint:
            raise ValueError(f"Paks view is missing or has different {name} content: {path.name}")
        fingerprints[str(candidate)] = fingerprint
    return pack, fingerprints


def unchanged(fingerprints):
    for path, expected in fingerprints.items():
        if sha256(path) != expected:
            raise ValueError(f"Build input changed while baking: {path}; rerun after the other build finishes")


def verify_archive(archive, spec, level, version, runtime, signed):
    with zipfile.ZipFile(archive) as z:
        names = z.namelist()
        if len(names) != len(set(names)):
            raise ValueError("Archive contains duplicate members")
        manifest = json.loads(z.read("mjolnir.json"))
        if manifest.get("type") != "map" or manifest.get("version") != version:
            raise ValueError("Archive is not the requested map release")
        map_info = manifest.get("map", {})
        if map_info.get("code") != spec["code"] or map_info.get("modes") != level["modes"]:
            raise ValueError("Archive map code or modes differ from the source")
        if map_info.get("vehicles", False) != spec.get("vehicles", False):
            raise ValueError("Archive vehicle flag differs from the source")
        expected_deps = [{"slug": "mjolnir-ce-runtime", "range": runtime}] + [
            {"slug": p["slug"], "range": "=" + p["version"]} for p in level["blam"]["forge_packs"]]
        if manifest.get("deps") != expected_deps:
            raise ValueError("Archive does not pin its Forge pack dependencies")
        if json.loads(z.read("map/level.json")) != level:
            raise ValueError("Archive did not preserve the complete authored level")
        registration = json.loads(z.read("map/registration.json"))
        if registration.get("code") != spec["code"] or registration.get("from") != "B40":
            raise ValueError("Archive registration points to the wrong scenario")
        if spec["code"] not in registration.get("world", ""):
            raise ValueError("Archive registration has no map-owned world")
        stem = f"content/pakchunk997-MJOLNIRMAP-{spec['code']}_P"
        for extension in ("utoc", "ucas"):
            if not z.getinfo(f"{stem}.{extension}").file_size:
                raise ValueError("Archive contains an empty map container")
        if any("MJOLNIRREG" in name or name.endswith((".dll", ".lua", ".mvar")) for name in names):
            raise ValueError("Map archive contains registration overrides, code or a private Forge save")
        if signed != ("signature.json" in names):
            raise ValueError("Archive signing state differs from the request")
    return {"file": str(archive), "sha256": sha256(archive), "bytes": archive.stat().st_size,
            "code": spec["code"], "slug": spec["slug"], "version": version,
            "signed": signed, "deps": expected_deps, "modes": level["modes"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--paks", type=Path, required=True, help="Read-only game + CE runtime + required Forge pack container view")
    parser.add_argument("--runtime", required=True, help="Tested CE runtime version range, e.g. ^1.17.0")
    parser.add_argument("--version", default="0.1.0")
    parser.add_argument("--only", choices=MAPS)
    parser.add_argument("--cli", type=Path, default=ROOT / "target/debug/mjolnir.exe")
    parser.add_argument("--world", type=Path, default=ROOT / "defs/level/empty_world.umap")
    parser.add_argument("--collision-dir", type=Path, help="Override the selected maps' default canvas folders")
    parser.add_argument("--pack-manifest", type=Path, action="append",
                        help="Repeat for each built pack; defaults to each required slug's build/game/all/mjolnir.json")
    parser.add_argument("--out", type=Path, default=ROOT / "forge-maps/build")
    signing = parser.add_mutually_exclusive_group()
    signing.add_argument("--sign", action="store_true")
    signing.add_argument("--sign-seed", type=Path)
    args = parser.parse_args()
    if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+(?:-[0-9A-Za-z.-]+)?", args.version) or len(args.version) > 96:
        parser.error("--version must be a Hub semantic version without build metadata, at most 96 characters")
    if not args.runtime.strip() or len(args.runtime) > 120:
        parser.error("--runtime must name the tested dependency range (1–120 characters)")
    for field in ("paks", "out", "cli", "world", "collision_dir", "sign_seed"):
        if getattr(args, field) is not None:
            setattr(args, field, getattr(args, field).resolve())
    if not args.paks.is_dir() or not args.cli.is_file() or not args.world.is_file():
        parser.error("Paks, CLI and bare world must exist")
    if args.out.is_relative_to(args.paks):
        parser.error("Build output must be outside the input Paks folder")
    selected = [(key, spec) for key, spec in MAPS.items() if not args.only or args.only == key]
    levels = {key: read_json(ROOT / "forge-maps" / spec["source"]) for key, spec in selected}
    slugs = sorted({p["slug"] for level in levels.values() for p in level["blam"]["forge_packs"]})
    manifests = args.pack_manifest or [ROOT / "forge-packs" / slug / "build/game/all/mjolnir.json" for slug in slugs]
    packs, fingerprints = [], {}
    for path in manifests:
        path = path.resolve()
        pack, content_hashes = check_pack_view(args.paks, path)
        packs.append(pack)
        fingerprints.update(content_hashes)
        fingerprints[str(path)] = sha256(path)
    for path in [args.cli, args.world]:
        fingerprints[str(path.resolve())] = sha256(path)
    world_bulk = args.world.with_suffix(".ubulk")
    if world_bulk.exists():
        fingerprints[str(world_bulk.resolve())] = sha256(world_bulk)
    inputs = []
    for key, spec in selected:
        source = ROOT / "forge-maps" / spec["source"]
        bsp = (args.collision_dir or ROOT / spec.get("collision_dir", "forge-packs/foundry/build/canvas")) / spec["bsp"]
        receipt = Path(str(bsp) + ".canvas.json")
        level = levels[key]
        check_level(level, spec, packs, read_json(receipt))
        readme = ROOT / spec.get("readme", "forge-maps/README.md")
        for path in [source, bsp, receipt, readme]:
            fingerprints[str(path.resolve())] = sha256(path)
        inputs.append((key, spec, source, bsp, level))
    # No output exists until every input passes preflight. A fresh build has
    # no old registration/container files that could leak into an archive.
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]
    output = args.out / stamp
    output.mkdir(parents=True, exist_ok=False)
    log = output / "build.log"

    def run(*command):
        command = [str(v) for v in command]
        result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace")
        with log.open("a", encoding="utf-8") as stream:
            stream.write("\n" + repr(command) + "\n" + result.stdout + result.stderr)
        if result.returncode:
            raise RuntimeError(f"Build failed ({result.returncode}); see {log}\n{result.stderr[-3000:]}\n{result.stdout[-3000:]}")

    archives = []
    for key, spec, source, bsp, level in inputs:
        staging = output / key
        staging.mkdir()
        snapshot = staging / source.name
        shutil.copy2(source, snapshot)
        print(f"Baking {spec['name']} ({spec['code']})...", flush=True)
        run(args.cli, "level", "validate", snapshot)
        run(args.cli, "level", "bake", snapshot, "--paks", args.paks,
            "--standalone", spec["code"], "--bsp", f"8={bsp.resolve()}",
            "--world", args.world.resolve(), "--out-dir", staging)
        unchanged(fingerprints)
        archive = output / f"{spec['slug']}-{args.version}.mjolnir"
        command = [args.cli, "map", "pack", staging, "--code", spec["code"],
                   "--version", args.version, "--slug", spec["slug"], "--name", spec["name"],
                   "--summary", level["description"], "--runtime", args.runtime,
                   "--size", spec["size"], "--players", spec["players"],
                   "--vehicles", str(spec.get("vehicles", False)).lower(),
                   "--readme", ROOT / spec.get("readme", "forge-maps/README.md"), "--out", archive]
        if args.sign:
            command.append("--sign")
        if args.sign_seed:
            command.extend(["--sign-seed", args.sign_seed.resolve()])
        run(*command)
        archives.append(verify_archive(archive, spec, level, args.version, args.runtime,
                                       bool(args.sign or args.sign_seed)))
        print(f"Verified {archive} ({archives[-1]['bytes']:,} bytes)", flush=True)
    unchanged(fingerprints)
    (output / "build-report.json").write_text(json.dumps({"schema_version": 1,
        "inputs": fingerprints, "archives": archives}, indent=2) + "\n", encoding="utf-8")
    print(f"Build complete: {output}")


if __name__ == "__main__":
    main()
