"""Seal PWR's vehicle approaches, native road shading and unchanged match rules."""

import argparse
import os
from pathlib import Path
import shutil
import sys
import tempfile

from stage_world_playtest import (
    ROOT,
    WORLD,
    LAND,
    jsonfile,
    load_container,
    sha,
    verify_world,
    world_entries,
    write_json,
)

sys.path.insert(0, str(Path(__file__).resolve().parent / "bases_v1"))
from stage_base_polish import seal_release, unpack_map


def owns_meshes(toc, actors):
    container = load_container(toc)
    root = container.mount_point.lstrip("./")
    assets = {root + p for p in container.files}
    requested = {
        actor["mesh"].split(".", 1)[0].replace("/Game/", "Meteorite/Content/")
        + ".uasset"
        for actor in actors
    }
    return assets == requested


def stage(args, out):
    inputs, previous, expected, manifest = unpack_map(args.baseline, out)
    old_world = inputs / (WORLD + ".utoc")
    world = args.native / "world-final" / old_world.name
    package = jsonfile(args.native / "native.json")
    if package["sealed_baseline"] != previous["sha256"]:
        raise ValueError("World belongs to a different baseline")
    world_proof = verify_world(old_world, world)
    old_land = inputs / (LAND + ".utoc")
    (land,) = (args.native / "land").glob("*.utoc")
    before, after = world_entries(old_land), world_entries(land)
    added = set(after) - set(before)
    field_leaf = args.site_field or "T_PWR_RoadNetwork"
    if (
        set(before) - set(after)
        or not added
        or any(Path(n).stem != field_leaf for n in added)
    ):
        raise ValueError(f"Unexpected terrain inventory changes: {added}")
    changes = sorted(n for n in before if before[n] != after[n])
    if not any(n.endswith("/M_PWRPilot.uasset") for n in changes):
        raise ValueError("No cooked road shader")
    # Preserve all the previous meadow/wetland inputs, grass types and textures.
    allowed = (
        "/M_PWRPilot.uasset",
        "/LPE.umap",
        "/MI_PWR_ExteriorCliffs_9c8b739f48f3.uasset",
        ".ushaderbytecode",
    )
    if args.site_field:
        allowed += ("/T_PWR_BiomeColor.uasset", "/T_PWR_BiomeColor.ubulk")
    if any(not n.endswith(allowed) for n in changes):
        raise ValueError(f"Unexpected changes to previous terrain assets: {changes}")

    art = jsonfile(args.geometry)
    stem = Path(art["container_stem"])
    prefix = "pakchunk951-" if args.site_field else "pakchunk952-"
    if not stem.name.startswith(prefix) or list(inputs.glob(prefix + "*")):
        raise ValueError("Native approach chunk conflicts with another asset")
    new_actors = jsonfile(Path(art["runtime_decor"]))["decor"]
    level_path = inputs / "pwr.level.json"
    level = jsonfile(level_path)
    old_ids = (
        set()
        if args.site_field
        else {
            "pwr_paving_red_home",
            "pwr_paving_blue_home",
            "pwr_paving_citadel_plateau",
        }
    )
    if (
        new_actors != art["decor"]
        or set(art.get("remove_decor_ids", [])) != old_ids
        or not art["validation"]["passed"]
    ):
        raise ValueError("Roads or courts disagree with verified geometry")
    (bsp_name,) = [
        k
        for k in world_proof["preserved"]
        if k.endswith("scenario_structure_bsp.ubulk")
    ]
    collision_key = "unchanged_bsp_sha256" if args.site_field else "bsp_sha256"
    if world_proof["preserved"][bsp_name] != art["validation"][collision_key]:
        raise ValueError("Approach tests refer to another collision surface")
    old = [a for a in level["decor"] if a["id"] in old_ids]
    if (
        len(old) != len(old_ids)
        or {a["id"] for a in old} != old_ids
        or len(new_actors) != 3
    ):
        raise ValueError("Unexpected site placements")
    if not owns_meshes(stem.with_suffix(".utoc"), new_actors):
        raise ValueError(
            "Approach actor references a mesh outside its verified package"
        )
    if old:
        (old_paving,) = inputs.glob("pakchunk961-*.utoc")
        if not owns_meshes(old_paving, old):
            raise ValueError("Old paving chunk owns unexpected content")
        # Retire only the spoke meshes in the temporary, unpacked release.
        for ext in (".utoc", ".ucas"):
            member = old_paving.with_suffix(ext)
            del expected["content/" + member.name]
            member.unlink()
    replaced = {a["mesh"] for a in old}
    level["decor"] = [a for a in level["decor"] if a["id"] not in old_ids] + new_actors
    ids = [a["id"] for a in level["decor"]]
    if len(set(ids)) != len(ids) or any(a["mesh"] in replaced for a in level["decor"]):
        raise ValueError("Duplicate actor or retained reference to retired paving")
    write_json(level_path, level)
    expected["map/level.json"] = sha(level_path)
    for ext in (".utoc", ".ucas"):
        for source, dest in (
            (world, old_world),
            (land, old_land),
            (stem, inputs / stem.name),
        ):
            src, dst = source.with_suffix(ext), dest.with_suffix(ext)
            shutil.copyfile(src, dst)
            expected["content/" + dst.name] = sha(dst)
    roads = jsonfile(args.roads)
    clearance = jsonfile(args.clearance)
    if (
        clearance["world_sha256"]
        != world_entries(world)["Meteorite/Content/Levels/Halo1/Solo/PWR/PWR.umap"]
        or clearance["routes_sha256"]
        != (
            previous["traffic_clearance"]["routes_sha256"]
            if args.site_field
            else roads["approach_sha256"]
        )
        or clearance["roots_on_a_lane"]
    ):
        raise ValueError(
            "Foliage and parking check does not match the cooked approach lanes"
        )
    for ext in (".utoc", ".ucas"):
        if roads["container_sha256"][ext] != sha(land.with_suffix(ext)):
            raise ValueError("Road readback is for another landscape cook")
        if (
            args.site_field
            and roads["prior_09_container_sha256"][ext]
            != previous["members_sha256"]["content/" + old_land.with_suffix(ext).name]
        ):
            raise ValueError("Site finish was compared against another road release")
        proof = art["files"][ext]
        if sha(stem.with_suffix(ext)) != (
            proof["sha256"] if isinstance(proof, dict) else proof
        ):
            raise ValueError("Native approach geometry changed after verification")
    seal_release(
        args,
        out,
        inputs,
        previous,
        expected,
        manifest,
        {
            "level_sections": ["decor"],
            "retired_decor": sorted(old_ids),
            "approach_actors": [a["id"] for a in new_actors],
            "world_packages": world_proof,
            "terrain_assets_added": sorted(added),
            "terrain_assets_changed": changes,
            "collision": previous["collision"],
            "native_gate_witnesses": previous["native_gate_witnesses"],
            "art_scene_sha256": previous["art_scene_sha256"],
            "approach_geometry": art,
            "roads": roads,
            "traffic_clearance": clearance,
        },
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ("baseline", "native", "geometry", "roads", "clearance", "out"):
        parser.add_argument("--" + key, type=Path, required=True)
    parser.add_argument("--cli", type=Path, default=ROOT / "target/release/mjolnir.exe")
    parser.add_argument("--version", default="0.1.0-playtest.9")
    parser.add_argument(
        "--site-field",
        help="Additional perimeter texture when extending the sealed road release",
    )
    args = parser.parse_args()
    if args.out.exists():
        parser.error("Choose a fresh release directory")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=args.out.parent) as scratch:
        release = Path(scratch) / "release"
        release.mkdir()
        stage(args, release)
        os.rename(release, args.out)
