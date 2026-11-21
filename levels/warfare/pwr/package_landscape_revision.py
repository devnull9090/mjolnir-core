"""Bring an isolated LPE terrain cook into the previously sealed PWR world."""

import argparse
from pathlib import Path
import shutil
import subprocess

from stage_world_playtest import (
    ROOT,
    WORLD,
    jsonfile,
    load_container,
    read_chunk,
    sha,
    world_entries,
    write_json,
)


def run(command, path):
    with path.open("w", encoding="utf-8") as log:
        result = subprocess.run(
            [str(i) for i in command], cwd=ROOT, stdout=log, stderr=subprocess.STDOUT
        )
    if result.returncode:
        raise RuntimeError(f"{path}: {path.read_text(errors='replace')[-1600:]}")


def build(args):
    raw_log = args.cook_log.read_bytes()
    encoding = (
        "utf-16" if raw_log.startswith((b"\xff\xfe", b"\xfe\xff")) else "utf-8-sig"
    )
    log = raw_log.decode(encoding)
    if "BUILD SUCCESSFUL" not in log or any(
        issue in log
        for issue in (
            "Failed to compile Material",
            "Default Material will be used in game",
            "Shadermap pointer is null",
            "Shader is using too many Samplers",
        )
    ):
        raise ValueError(
            f"The cook is missing a working terrain shader: {args.cook_log}"
        )
    base = jsonfile(args.baseline / "receipt.json")
    base_world = args.baseline / "map-input" / (WORLD + ".utoc")
    for ext in (".utoc", ".ucas"):
        file = base_world.with_suffix(ext)
        if sha(file) != base["members_sha256"]["content/" + file.name]:
            raise ValueError("Baseline world disagrees with sealed map")
    if sha(args.bsp) != base["collision"]["sbsp"]:
        raise ValueError("Collision source differs from the previous release")

    out = args.out
    out.mkdir(parents=True, exist_ok=False)
    source = out / "stock"
    source.mkdir()
    for stem in ("global", "pakchunk965-Windows"):
        for ext in (".utoc", ".ucas"):
            name = stem + ext
            shutil.copyfile(args.staged / name, source / name)
    land = out / "land"
    land.mkdir()
    run(
        [
            args.cli,
            "ue",
            "retarget",
            "--paks",
            source,
            "--container",
            "pakchunk965-Windows",
            "--classes",
            "Material,MaterialInstanceConstant,LandscapeGrassType",
            "--rewrite",
            "--name",
            "pakchunk965-MJOLNIRLAND-Windows",
            "--out-dir",
            land,
        ],
        out / "land.log",
    )
    examples = ROOT / "target/release/examples"
    for suffix, dest in (("umap", "LPE.stock.umap"), ("ubulk", "LPE.ubulk")):
        run(
            [
                examples / "extract_file.exe",
                source,
                "Levels/Halo1/Solo/LPE/LPE." + suffix,
                out / dest,
            ],
            out / ("extract-" + suffix + ".log"),
        )
    run(
        [
            examples / "retarget_package.exe",
            source,
            ROOT / "defs/ue/UE-5.5-stock.usmap",
            ROOT / "defs/ue/Meteorite-2607-CU3.usmap",
            out / "LPE.stock.umap",
            out / "LPE.umap",
        ],
        out / "world-layout.log",
    )
    raw = out / "world-bake"
    run(
        [
            args.cli,
            "level",
            "bake",
            args.level,
            "--paks",
            args.paks,
            "--standalone",
            "PWR",
            "--bsp",
            "8=" + str(args.bsp.resolve()),
            "--out-dir",
            raw,
            "--world",
            out / "LPE.umap",
        ],
        out / "bake.log",
    )

    # The newly renamed world can acquire package imports from the new shader.
    # Keep its cooker-generated header, then restore the sealed native scenario.
    old = world_entries(base_world)
    generated = world_entries(raw / base_world.name)
    if old.keys() != generated.keys():
        raise ValueError("Native map inventory changed")
    previous = load_container(base_world)
    replacements = out / "baseline-scenario"
    preserved = []
    for name in old:
        if generated[name] == old[name] or name.endswith(
            ("/PWR/PWR.umap", "/PWR/PWR.ubulk")
        ):
            continue
        if not name.endswith(("/PWR-scenario.uasset", "/PWR-scenario.ubulk")):
            raise ValueError(f"Unintended native bake change to {name}")
        target = replacements / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(read_chunk(previous, previous.chunks[previous.files[name]]))
        preserved.append(name)
    final = out / "world-final"
    if preserved:
        run(
            [
                examples / "replace_members.exe",
                raw / base_world.name,
                replacements,
                final,
            ],
            out / "seal.log",
        )
    else:
        final.mkdir()
        for ext in (".utoc", ".ucas"):
            shutil.copyfile(raw / (WORLD + ext), final / (WORLD + ext))
    actual = world_entries(final / base_world.name)
    expected = {
        k: (generated[k] if k.endswith(("/PWR/PWR.umap", "/PWR/PWR.ubulk")) else v)
        for k, v in old.items()
    }
    if actual != expected:
        raise ValueError(
            "Final world readback disagrees with cooked terrain or native baseline"
        )
    write_json(
        out / "native.json",
        {
            "sealed_baseline": base["sha256"],
            "restored_scenario": preserved,
            "world_changes": [name for name in actual if actual[name] != old[name]],
            "world_sha256": {
                ext: sha(final / (WORLD + ext)) for ext in (".ucas", ".utoc")
            },
        },
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for flag in ("staged", "baseline", "level", "bsp", "paks", "cook-log", "out"):
        parser.add_argument("--" + flag, required=True, type=Path)
    parser.add_argument(
        "--cli", type=Path, default=ROOT / "out/pwr/toolchain-grass-v7/r2/mjolnir.exe"
    )
    build(parser.parse_args())
