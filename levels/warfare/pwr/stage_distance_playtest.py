"""Stage the distance landscape over a verified PWR map and its paired profiles."""
import argparse
import os
from pathlib import Path
import shutil
import sys
import tempfile

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "bases_v1"))
from stage_base_polish import ROOT, seal_release, unpack_map
from stage_world_playtest import WORLD, jsonfile, sha, verify_world, world_entries


def stage(args, out):
    inputs, previous, expected, manifest = unpack_map(args.baseline, out)
    world = verify_world(inputs / (WORLD + ".utoc"), args.world)
    old_land, = inputs.glob("pakchunk965-*.utoc")
    old_payload = world_entries(old_land)
    new_payload = world_entries(args.land)
    if old_payload.keys() != new_payload.keys():
        raise ValueError("The landscape asset inventory changed")
    changed = sorted(k for k in old_payload if old_payload[k] != new_payload[k])
    if not any(k.endswith("/T_PWR_BiomeColor.ubulk") for k in changed):
        raise ValueError("The cooked biome field is identical to the previous release")
    if not any(k.endswith("/M_PWRPilot.uasset") for k in changed):
        raise ValueError("The new distance material is missing")
    colony = jsonfile(args.vegetation / "editor-verify.json")
    authored = jsonfile(args.vegetation / "receipts.json")
    if sum(c["count"] for c in colony["components"].values()) != authored["instances"]:
        raise ValueError("Reopened map disagrees with PCG output")
    if any(c["collision"] for c in colony["components"].values()):
        raise ValueError("Distance foliage interferes with vehicle collision")
    field = jsonfile(args.terrain / "terrain-field.json")
    compiled = jsonfile(args.terrain / "editor-field.json")
    if compiled["source_sha256"] != field["sha256"] or sha(args.terrain / field["file"]) != field["sha256"]:
        raise ValueError("The material input differs from the reviewed distance field")
    texture_proof = jsonfile(args.terrain / "cooked-terrain-readback.json")
    if any(texture_proof["container_sha256"][ext] != sha(args.land.with_suffix(ext))
           or texture_proof["before_container_sha256"][ext] != sha(old_land.with_suffix(ext))
           for ext in (".utoc", ".ucas")):
        raise ValueError("The texture readback belongs to a different landscape package")
    vegetation_proof = jsonfile(args.vegetation / "cooked-proof" / "final.json")
    if vegetation_proof["utoc_sha256"] != sha(args.world) or vegetation_proof["ucas_sha256"] != sha(args.world.with_suffix(".ucas")):
        raise ValueError("The vegetation readback belongs to a different world")
    changes = []
    # The previous base-art archive truncated a byte of an unindexed shader
    # group's ID. Keep the bytes of every base asset and its shader payload.
    repair = jsonfile(args.base_shader_repair / "repair.json")
    old_toc, = inputs.glob("pakchunk955-*.utoc")
    fixed_toc = args.base_shader_repair / old_toc.name
    if (sha(old_toc) != repair["old_toc_sha256"] or sha(fixed_toc) != repair["corrected_toc_sha256"]
        or sha(old_toc.with_suffix(".ucas")) != repair["identical_ucas_sha256"]
        or sha(fixed_toc.with_suffix(".ucas")) != repair["identical_ucas_sha256"]
        or not repair["all_payloads_identical"] or not repair["shader_payload_matches_validated_pre_splice_group"]
        or world_entries(old_toc) != world_entries(fixed_toc)):
        raise ValueError("Base shader fix changed asset data or does not match its runtime lookup proof")
    shutil.copyfile(fixed_toc, old_toc)
    changes.append("content/" + old_toc.name)
    expected[changes[-1]] = sha(old_toc)
    for source, destination in ((args.world, inputs / (WORLD + ".utoc")), (args.land, old_land)):
        for ext in (".utoc", ".ucas"):
            member = destination.with_suffix(ext)
            shutil.copyfile(source.with_suffix(ext), member)
            key = "content/" + member.name
            expected[key] = sha(member)
            if expected[key] != previous["members_sha256"][key]:
                changes.append(key)
    seal_release(args, out, inputs, previous, expected, manifest, {
        "world_packages": world, "landscape_modified_payloads": changed,
        "changed_map_members": sorted(changes), "collision": previous["collision"],
        "art_scene_sha256": previous["art_scene_sha256"], "native_gate_witnesses": previous["native_gate_witnesses"],
        "terrain_field_sha256": field["sha256"], "distance_vegetation": colony,
        "cooked_terrain": texture_proof, "cooked_vegetation": vegetation_proof, "base_shader_repair": repair,
    })


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("baseline", "world", "land", "vegetation", "terrain", "base-shader-repair", "out"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--cli", type=Path, default=ROOT / "target/release/mjolnir.exe")
    parser.add_argument("--version", default="0.1.0-playtest.8")
    args = parser.parse_args()
    if args.out.exists():
        parser.error("Choose a fresh release directory")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=args.out.parent) as tmp:
        release = Path(tmp) / "release"
        release.mkdir()
        stage(args, release)
        os.rename(release, args.out)
