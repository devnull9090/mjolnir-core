"""Carry the verified grass, rock and mountain cook forward with a scoped forest placement edit."""

from pathlib import Path
import argparse
import sys
import tempfile
import shutil
import subprocess

from stage_world_playtest import (
    ROOT,
    LAND,
    WORLD,
    jsonfile,
    load_container,
    read_chunk,
    sha,
    verify_world,
    world_entries,
)

sys.path.insert(0, str(Path(__file__).resolve().parent / "bases_v1"))
from stage_base_polish import seal_release, unpack_map


def stage(args, out):
    inputs, old, expected, manifest = unpack_map(args.baseline, out)
    native = jsonfile(args.native / "native.json")
    if native["sealed_baseline"] != old["sha256"]:
        raise ValueError("Wrong source map")
    original = inputs / (WORLD + ".utoc")
    updated = args.native / "world-final" / original.name
    proof = verify_world(original, updated)
    old_land = inputs / (LAND + ".utoc")
    (fresh_land,) = (args.native / "land").glob("*.utoc")
    a, b = world_entries(old_land), world_entries(fresh_land)
    changed = {n for n in a if n in b and a[n] != b[n]}
    # IoStore can reorder an equivalent shader archive when preparing a world.
    # Verify the mapping and retain the previous archive with its group indices.
    from visual_dressing.verify_distance_terrain import parse_library

    def shader_signature(toc, name):
        container = load_container(toc)
        key = container.files[name]
        lib = parse_library(read_chunk(container, container.chunks[key]))
        return (
            {
                h: tuple(lib.shader_hashes[j] for j in lib.map_shaders(i))
                for i, h in enumerate(lib.map_hashes)
            },
            set(lib.group_ids),
        )

    if a.keys() != b.keys():
        raise ValueError("The forest edit changed the asset inventory")
    for name in list(changed):
        if name.endswith(".ushaderbytecode"):
            if shader_signature(old_land, name) != shader_signature(fresh_land, name):
                raise ValueError(
                    "The forest planting unexpectedly changed shipped shader maps"
                )
            changed.remove(name)
    if not changed or any(
        not n.endswith(("/LPE/LPE.umap", "/LPE/LPE.ubulk")) for n in changed
    ):
        raise ValueError("Unexpected authored asset change: " + str(changed))
    # The old release also contains non-indexed shader code. Replace only the
    # LPE provisional world in its owning chunk so all shader bytecode survives.
    with tempfile.TemporaryDirectory(dir=out) as tmp:
        root = Path(tmp)
        owner = load_container(fresh_land)
        for name in changed:
            dest = root / "members" / name
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(read_chunk(owner, owner.chunks[owner.files[name]]))
        subprocess.run(
            [
                ROOT / "target/release/examples/replace_members.exe",
                old_land,
                root / "members",
                root / "fixed",
            ],
            check=True,
        )
        result = root / "fixed" / old_land.name
        if world_entries(result) != {n: b[n] if n in changed else a[n] for n in a}:
            raise ValueError("Readback lost a foliage world member")
        for src, dst in ((result, old_land), (updated, original)):
            for ext in (".ucas", ".utoc"):
                data = src.with_suffix(ext)
                dest = dst.with_suffix(ext)
                shutil.copyfile(data, dest)
                expected["content/" + dest.name] = sha(dest)
    placement = jsonfile(args.placement)
    revision = {
        "world_packages": proof,
        "landscape_world_members": sorted(changed),
        "forest_floor": placement,
        "baseline_map": old["archive"],
        "inherited_visual_fields": [
            "geology_pixels",
            "ridge_geometry",
            "ridge_material",
            "earth_finish",
        ],
        **{
            k: old[k]
            for k in (
                "collision",
                "art_scene_sha256",
                "native_gate_witnesses",
                "geology_pixels",
                "ridge_geometry",
                "ridge_material",
                "earth_finish",
            )
        },
    }
    seal_release(args, out, inputs, old, expected, manifest, revision)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("baseline", "native", "placement", "out"):
        p.add_argument("--" + name, type=Path, required=True)
    p.add_argument("--cli", type=Path, default=ROOT / "target/release/mjolnir.exe")
    p.add_argument("--version", default="0.1.0-playtest.13")
    args = p.parse_args()
    if args.out.exists():
        raise FileExistsError(args.out)
    with tempfile.TemporaryDirectory(dir=args.out.parent) as temp:
        release = Path(temp) / "release"
        release.mkdir()
        stage(args, release)
        release.rename(args.out)
