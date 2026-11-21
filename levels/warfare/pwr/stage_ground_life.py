"""Seal surveyed terrain, grass and loose ground into the existing Pelican Warfare release."""

import argparse
from pathlib import Path
import os
import shutil
import subprocess
import sys
import tempfile

import numpy as np
from PIL import Image

from stage_world_playtest import (
    ROOT,
    LAND,
    WORLD,
    SURFACES,
    jsonfile,
    sha,
    verify_world,
    world_entries,
    write_json,
    load_container,
    read_chunk,
)

sys.path.insert(0, str(Path(__file__).resolve().parent / "bases_v1"))
from stage_base_polish import seal_release, unpack_map


OODLE = Path(
    "C:/Program Files/Epic Games/UE_5.5/Engine/Binaries/DotNET/UnrealBuildTool/oo2core_9_win64.dll"
)


def substitute_field(source, old, folder):
    staged, original = load_container(source), load_container(old)
    root = folder / "field-members"
    for name, index in original.files.items():
        if Path(name).stem != "T_PWR_ApronField":
            continue
        found = [n for n in staged.files if n.endswith("/" + Path(name).name)]
        if len(found) != 1:
            raise ValueError("Missing unique cooked geology field " + name)
        dest = root / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(
            read_chunk(
                staged, staged.chunks[staged.files[found[0]]], oodle_roots=[OODLE]
            )
        )
    result = folder / "surfaces"
    subprocess.run(
        [ROOT / "target/release/examples/replace_members.exe", old, root, result],
        check=True,
    )
    pair = result / old.name
    a, b = world_entries(old), world_entries(pair)
    changed = sorted(k for k in a if a[k] != b[k])
    if a.keys() != b.keys() or {Path(k).name for k in changed} != {
        "T_PWR_ApronField.uasset",
        "T_PWR_ApronField.ubulk",
    }:
        raise ValueError("Unexpected change to exterior materials: " + str(changed))
    return pair


def verify_pixels(args, folder, land, surfaces):
    folder.mkdir()
    for toc in [args.staged / "global.utoc", land, surfaces]:
        for ext in (".utoc", ".ucas"):
            src = toc.with_suffix(ext)
            try:
                os.link(src, folder / src.name)
            except OSError:
                shutil.copyfile(src, folder / src.name)
    readback = {}
    for leaf in ("T_LandBase", "T_PWR_ApronField"):
        got = folder / (leaf + ".png")
        subprocess.run(
            [
                args.cli,
                "texture",
                "export",
                "--paks",
                folder,
                "--asset",
                leaf,
                "--out",
                got,
            ],
            check=True,
        )
        want = args.ridges / (leaf + ".png")
        a, b = (np.asarray(Image.open(f).convert("RGBA")) for f in (got, want))
        if a.shape != b.shape or not np.array_equal(a, b):
            raise ValueError(
                f"{leaf}: cooked pixels do not match source, {(a != b).sum(axis=(0, 1)).tolist()} channels"
            )
        readback[leaf] = {
            "identical_rgba_texels": int(a.shape[0] * a.shape[1]),
            "source_sha256": sha(want),
            "export_sha256": sha(got),
        }
    return readback


def stage(args, out):
    inputs, previous, expected, manifest = unpack_map(args.baseline, out)
    native = args.native
    if jsonfile(native / "native.json")["sealed_baseline"] != previous["sha256"]:
        raise ValueError("Wrong world baseline")
    old_world = inputs / (WORLD + ".utoc")
    world = native / "world-final" / old_world.name
    proof = verify_world(old_world, world)
    old_land = inputs / (LAND + ".utoc")
    (land,) = (native / "land").glob("*.utoc")
    a, b = world_entries(old_land), world_entries(land)
    added = set(b) - set(a)
    changed = sorted(k for k in a if k in b and a[k] != b[k])
    allowed = {
        "M_PWRPilot",
        "T_LandBase",
        "GT_PWRPilot",
        "LPE",
        "MI_PWR_ExteriorCliffs_9c8b739f48f3",
    }
    if set(a) - set(b) or any(
        Path(k).stem not in allowed and not k.endswith(".ushaderbytecode")
        for k in changed
    ):
        raise ValueError("Unexpected previous terrain asset changed: " + str(changed))
    if not {"M_PWRPilot", "T_LandBase", "GT_PWRPilot"}.issubset(
        {Path(k).stem for k in changed}
    ):
        raise ValueError("Cook omitted a playable terrain or grass edit")
    new_assets = {
        "T_PWR_EarthDetail",
        "M_PWR_WindBlade",
        *{
            p + f
            for p in ("MI_PWR_Wind_", "T_PWR_Wind_")
            for f in ("B30", "Tundra", "Canyon")
        },
    }
    expected_material = jsonfile(args.ridges / "geology.material.json")
    surveyed_material = (
        "/Game/MJOLNIR/GrassPilot/Playable/M_PWR_AlpineRidges.M_PWR_AlpineRidges"
    )
    if expected_material["parent"] == surveyed_material:
        new_assets.update(
            {
                "M_PWR_AlpineRidges",
                "T_PWR_ApronField",
                "T_CE_White",
                "SM_PWR_FineFescue_A",
                "SM_PWR_FineFescue_B",
                "MI_PWR_Wind_Fescue",
            }
        )
    if {Path(k).stem for k in added} != new_assets:
        raise ValueError("Unexpected new asset inventory: " + str(added))
    old_surface = inputs / (SURFACES + ".utoc")
    ridges = args.ridges
    art = jsonfile(ridges / "package.receipt.json")
    native_ridges = Path(art["container_stem"]).with_suffix(".utoc")
    with tempfile.TemporaryDirectory(dir=out) as temp:
        tmp = Path(temp)
        surface = substitute_field(
            args.staged / "pakchunk956-Windows.utoc", old_surface, tmp
        )
        # Both chunks own dependencies of the level's native granite material.
        # Mount order must always resolve to byte-identical material inputs.
        surface_entries = world_entries(surface)
        for entry in b.keys() & surface_entries.keys():
            if b[entry] != surface_entries[entry]:
                raise ValueError("Ambiguous mountain material dependency: " + entry)
        textures = verify_pixels(args, tmp / "texture-readback", land, surface)
        (old_ridges,) = inputs.glob("pakchunk963-*.utoc")
        for src, dst in (
            (surface, old_surface),
            (native_ridges, old_ridges),
            (land, old_land),
            (world, old_world),
        ):
            for ext in (".utoc", ".ucas"):
                file = src.with_suffix(ext)
                if src == native_ridges and art["files"][ext]["sha256"] != sha(file):
                    raise ValueError("Mountain mesh differs from native readback")
                dest = dst.with_suffix(ext)
                shutil.copyfile(file, dest)
                expected["content/" + dest.name] = sha(dest)
    level_file = inputs / "pwr.level.json"
    level = jsonfile(level_file)
    (new_actor,) = jsonfile(ridges / "runtime_decor.json")["decor"]
    (row,) = [i for i, v in enumerate(level["decor"]) if v.get("id") == new_actor["id"]]
    old = level["decor"][row]
    if new_actor.get("materials") != [expected_material]:
        raise ValueError("Terrain binding no longer matches the geometry receipt")
    if old["materials"][0]["textures"] != expected_material["textures"]:
        raise ValueError("The existing campaign surface textures changed")
    if {k for k in old.keys() | new_actor.keys() if old.get(k) != new_actor.get(k)} - {
        "pos",
        "scale",
        "materials",
    }:
        raise ValueError("Unexpected mountain material, mesh or gameplay change")
    level["decor"][row] = new_actor
    write_json(level_file, level)
    expected["map/level.json"] = sha(level_file)
    ridge_proof = jsonfile(ridges / "roundtrip.verification.json")
    if ridge_proof["package_receipt_sha256"] != sha(
        ridges / "package.receipt.json"
    ) or ridge_proof["geometry_receipt_sha256"] != sha(ridges / "receipt.json"):
        raise ValueError("Mountain receipt is stale")
    revision = {
        "level_sections": ["decor"],
        "world_packages": proof,
        "terrain_assets_added": sorted(added),
        "terrain_assets_changed": changed,
        "geology_pixels": textures,
        "ridge_geometry": jsonfile(ridges / "receipt.json"),
        "ridge_native": ridge_proof,
        "earth": jsonfile(args.art / "earth/editor-verify.json"),
        "stone_contact": jsonfile(args.art / "earth/stone-contact-readback.json"),
        "grass": jsonfile(args.art / "grass/editor-saved.json"),
        "collision": previous["collision"],
        "art_scene_sha256": previous["art_scene_sha256"],
        "native_gate_witnesses": previous["native_gate_witnesses"],
    }
    if (ridges / "contact.verification.json").exists():
        contacts = jsonfile(ridges / "contact.verification.json")
        if contacts["geometry_sha256"] != sha(ridges / "receipt.json"):
            raise ValueError("Mismatched foothill geometry")
        revision["foothill_contacts"] = contacts
    if expected_material["parent"] == surveyed_material:
        from collections import Counter
        from visual_dressing.verify_distance_terrain import FREQ, parse_library

        cont = load_container(land)

        def payload(key):
            (n,) = [n for n in cont.files if n.endswith(key)]
            return read_chunk(cont, cont.chunks[cont.files[n]], oodle_roots=[OODLE])

        lib = parse_library(payload("Chunk965-PCD3D_SM6-PCD3D_SM6.ushaderbytecode"))
        subject = payload("/M_PWR_AlpineRidges.uasset")
        stages = {}
        for i, h in enumerate(lib.map_hashes):
            if h in subject:
                indices = lib.map_shaders(i)
                if any(lib.shader_size(j) == 0 for j in indices):
                    raise ValueError("Empty alpine shader")
                stages[h.hex()] = dict(
                    Counter(FREQ.get(lib.shader_entries[j][0], "?") for j in indices)
                )
        if not any(st.get("PS") and st.get("VS") for st in stages.values()):
            raise ValueError("Cook omitted the native alpine surface shader")
        revision["ridge_material"] = {
            "parent": surveyed_material,
            "shader_maps": stages,
            "rock_source_sha256": sha(
                ROOT / "unreal/MJOLNIRMaterials/Scripts/pwr_ridge_granite.ush"
            ),
        }
    if args.grass_proof:
        revision["grass"] = jsonfile(args.grass_proof)
    if args.earth_proof:
        revision["earth_finish"] = jsonfile(args.earth_proof)
    seal_release(args, out, inputs, previous, expected, manifest, revision)


if __name__ == "__main__":
    ps = argparse.ArgumentParser(description=__doc__)
    for key in ("art", "baseline", "native", "staged", "out"):
        ps.add_argument("--" + key, type=Path, required=True)
    ps.add_argument("--ridges", type=Path)
    ps.add_argument("--grass-proof", type=Path)
    ps.add_argument("--earth-proof", type=Path)
    ps.add_argument("--cli", type=Path, default=ROOT / "target/release/mjolnir.exe")
    ps.add_argument("--version", default="0.1.0-playtest.11")
    args = ps.parse_args()
    args.ridges = args.ridges or args.art / "mountains/ridges"
    if args.out.exists():
        raise FileExistsError(args.out)
    with tempfile.TemporaryDirectory(dir=args.out.parent) as temp:
        release = Path(temp) / "release"
        release.mkdir()
        stage(args, release)
        release.rename(args.out)
