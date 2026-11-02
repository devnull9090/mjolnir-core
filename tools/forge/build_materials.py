#!/usr/bin/env python3
"""Prepare/cook self-contained Forge surface profiles, using local CE textures.

python tools/forge/build_materials.py forge-packs/foundry-wide --ce-textures <staging/textures> --chunk 967 --cook
The explicit chunk must be unused by the developer's installed packs. The
numeric filename is retained so Unreal opens its matching shader library.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[2]
PROFILES = ROOT / "mods/MJOLNIRForge/Scripts/material_profiles.json"
PROFILE_MATERIALS = {"glass_cyan": (7, "glass", "M_ForgeGlassCyan"),
                     "teleporter_green": (8, "portal_green", "M_ForgePortalGreen")}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def validate_slug(slug):
    if not isinstance(slug, str) or not re.fullmatch(r"[a-z0-9][a-z0-9-]{1,63}", slug):
        raise ValueError("Invalid Forge pack slug")
    return slug


def prepare(pack, texture_dir, chunk):
    pack, texture_dir = Path(pack).resolve(), Path(texture_dir).resolve()
    manifest = json.loads((pack / "catalog.json").read_text(encoding="utf-8"))
    slug = validate_slug(manifest["forge_pack"]["id"])
    if isinstance(chunk, bool) or not isinstance(chunk, int) or not 900 <= chunk <= 999:
        raise ValueError("Reserve an unused shader chunk in 900..999")
    profiles = json.loads(PROFILES.read_text(encoding="utf-8"))
    if profiles["schema_version"] != 1 or set(profiles["profiles"]) != set(PROFILE_MATERIALS):
        raise ValueError("Unexpected bundled surface profiles")
    textures = []
    for texture in profiles["textures"]:
        source = texture_dir / texture["source"]
        if not source.is_file() or source.stat().st_size > 16*1024*1024 or source.read_bytes()[:4] != b"DDS ":
            raise ValueError(f"Missing/invalid local CE DDS: {source}")
        textures.append({"name": texture["name"], "file": str(source), "sha256": sha(source)})
    output = pack / "build/materials"
    output.mkdir(parents=True, exist_ok=True)
    spec = {"schema_version": 1, "slug": slug, "root": f"/Game/MJOLNIR/Forge/{slug}", "chunk": chunk,
            "profiles_sha256": sha(PROFILES), "profiles": profiles["profiles"],
            "provenance": profiles["provenance"], "textures": textures}
    path = output / "materials.spec.json"
    path.write_text(json.dumps(spec, indent=2)+"\n", encoding="utf-8")
    return path, spec


def verified_content(pack, slug):
    """Fail closed if a requested surface cook is absent or stale."""
    output = Path(pack) / "build/materials"
    receipt = json.loads((output / "receipt.json").read_text(encoding="utf-8"))
    if receipt.get("schema_version") != 1 or receipt.get("slug") != validate_slug(slug) or receipt.get("profiles_sha256") != sha(PROFILES):
        raise ValueError("Forge material cook is for another pack or an outdated profile")
    spec = output / "materials.spec.json"
    if receipt.get("spec_sha256") != sha(spec):
        raise ValueError("Forge material specification changed after cooking")
    build_spec = json.loads(spec.read_text(encoding="utf-8"))
    chunk = receipt.get("chunk")
    if isinstance(chunk, bool) or not isinstance(chunk, int) or not 900 <= chunk <= 999 or build_spec.get("chunk") != chunk:
        raise ValueError("Invalid Forge material shader chunk")
    stem = f"pakchunk{chunk}-MJOLNIRFORGEMAT-{slug}_P"
    if set(receipt.get("files", {})) != {stem+suffix for suffix in (".utoc", ".ucas", ".pak")}:
        raise ValueError("Forge material cook requires its matching container triple")
    files = []
    for name, digest in receipt["files"].items():
        if Path(name).name != name or Path(name).suffix not in (".utoc", ".ucas", ".pak"):
            raise ValueError("Invalid cooked material filename")
        source = output / "content" / name
        if not source.is_file() or sha(source) != digest:
            raise ValueError(f"Forge material cook missing/changed: {name}")
        files.append(source)
    if {f.suffix for f in files} != {".utoc", ".ucas", ".pak"}:
        raise ValueError("Forge material cook requires a complete container triple")
    return files


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pack", type=Path)
    parser.add_argument("--ce-textures", type=Path, required=True)
    parser.add_argument("--chunk", type=int, required=True)
    parser.add_argument("--cook", action="store_true")
    parser.add_argument("--cli", type=Path, default=ROOT / "target/debug/mjolnir.exe")
    options = parser.parse_args()
    spec_path, spec = prepare(options.pack, options.ce_textures, options.chunk)
    print(f"Prepared {spec_path}", flush=True)
    if not options.cook:
        return
    env = os.environ.copy()
    env["MJ_FORGE_SPEC"], env["MJOLNIR"] = str(spec_path), str(options.cli.resolve())
    env["MJ_CPU_MASK"] = "FF"
    output = spec_path.parent
    for name, command, success in (
        ("import", ["powershell", "-NoProfile", "-File", str(ROOT / "tools/ue/editor_cmd.ps1"),
                    "-Script", "Scripts/build_forge_materials.py"], "editor exit 0"),
        ("cook", ["powershell", "-NoProfile", "-File", str(ROOT / "tools/ue/cook.ps1")], "cook exit 0"),
    ):
        result = subprocess.run(command, cwd=ROOT, env=env, capture_output=True, text=True)
        (output / (name+".log")).write_text(result.stdout+result.stderr, encoding="utf-8")
        if result.returncode or success not in result.stdout or "NOT re-encoded" in result.stdout or "failed; its materials" in result.stdout:
            raise RuntimeError(f"Forge material {name} failed; inspect {output / (name+'.log')}")
        print(f"Forge material {name} completed", flush=True)
    staged = ROOT / "unreal/MJOLNIRMaterials/Saved/StagedBuilds/Windows/Meteorite/Content/Paks"
    content = output / "content"
    content.mkdir(exist_ok=True)
    stem = f"pakchunk{spec['chunk']}-MJOLNIRFORGEMAT-{spec['slug']}_P"
    files = []
    for suffix in (".utoc", ".ucas"):
        source = staged / f"pakchunk{spec['chunk']}-Windows{suffix}"
        target = content / (stem+suffix)
        shutil.copyfile(source, target)
        files.append(target)
    from build_pack import write_pak_stub
    pak = content / (stem+".pak")
    write_pak_stub(pak)
    files.append(pak)
    receipt = {"schema_version": 1, "slug": spec["slug"], "chunk": spec["chunk"],
               "spec_sha256": sha(spec_path), "profiles_sha256": sha(PROFILES),
               "files": {f.name: sha(f) for f in files}}
    (output / "receipt.json").write_text(json.dumps(receipt, indent=2)+"\n", encoding="utf-8")
    verified_content(options.pack, spec["slug"])
    print(f"Verified Forge material container: {stem}")


if __name__ == "__main__":
    main()
