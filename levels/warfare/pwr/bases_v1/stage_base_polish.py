"""Stage new Forerunner base art and collision onto the verified Saturday map."""
import argparse
import copy
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import zipfile
import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from stage_world_playtest import (
    WORLD, PWR, ROOT, verified, world_entries, jsonfile, write_json, stage_name, sha,
    load_container, read_chunk, member_hash, pair_runtime,
)


def checked_world(inputs, args, physics):
    old = world_entries(inputs/(WORLD+".utoc"))
    control = world_entries(args.control/(WORLD+".utoc"))
    if old != control:
        raise ValueError("Collision control bake does not reproduce every baseline world entry")
    new = world_entries(args.bake/(WORLD+".utoc"))
    if new.keys() != old.keys():
        raise ValueError("World inventory changed")
    changes = sorted(k for k in old if old[k] != new[k])
    stem = "bsp_01_1_start-scenario_structure_bsp"
    if {Path(s).name.lower() for s in changes} != {stem+".uasset",stem+".ubulk"}:
        raise ValueError(f"Unexpected world package changes: {changes}")
    # The bake lowers only the pre-existing duplicate shell by 0.001 wu. This is
    # an in-place placement adjustment. Confirm exact native tag size and isolate
    # these bytes in both the reproducible baseline bake and the candidate.
    control_delta = None
    for directory, raw, expected in ((args.control,args.baseline_bsp,physics["base_sbsp"]),
                                     (args.bake,args.collision/"pwr.sbsp",physics["sbsp"])):
        if sha(raw) != expected:
            raise ValueError(f"Unexpected raw BSP {raw}")
        container = load_container(directory/(WORLD+".utoc"))
        bulk, = [s for s in changes if s.endswith(".ubulk")]
        packed = read_chunk(container,container.chunks[container.files[bulk]])
        body = raw.read_bytes()
        if len(body) != len(packed):
            raise ValueError("Unexpected serialized native body size")
        offsets = np.flatnonzero(np.frombuffer(packed,"u1") != np.frombuffer(body,"u1"))
        if not 1 <= len(offsets) <= 16:
            raise ValueError(f"Unexpected shell landing adjustment: {len(offsets)} bytes")
        delta = [(int(i-offsets[0]),body[i],packed[i]) for i in offsets]
        if control_delta is None:
            control_delta = delta
        elif delta != control_delta:
            raise ValueError("Cooked BSP did not receive the verified control shell adjustment")
    return {"modified":changes, "preserved":{k:v for k,v in old.items() if k not in changes},
            "control_reproduces_entire_previous_world":True}


def unpack_map(baseline, out):
    archive, info = verified(baseline, "receipt.json")
    inputs = out/"map-input"
    inputs.mkdir()
    expected = dict(info["members_sha256"])
    with zipfile.ZipFile(archive) as prior:
        if set(prior.namelist()) != {"mjolnir.json", *expected}:
            raise ValueError("Incomplete previous map receipt")
        old_manifest = json.loads(prior.read("mjolnir.json"))
        for name, digest in expected.items():
            to = inputs/stage_name(name)
            to.parent.mkdir(parents=True,exist_ok=True)
            with prior.open(name) as stream, to.open("xb") as target:
                shutil.copyfileobj(stream,target)
            if sha(to) != digest:
                raise ValueError(f"Incorrect baseline map member: {name}")
    return inputs, info, expected, old_manifest


def stage(args, out):
    inputs, info, expected, old_manifest = unpack_map(args.baseline,out)
    art_package = jsonfile(args.render/"package.json")
    art = jsonfile(Path(art_package["source"])/"base-polish.json")
    physics = jsonfile(args.collision/"collision-proof.json")
    if (physics["core_export_sha256"] != art["collision_sha256"] or
        not physics["root_and_definition_havok_verified_per_face"] or not physics["compiled_instance_bounds_checked"]
        or sha(Path(art["scene"])) != art["scene_sha256"]):
        raise ValueError("Cook and review do not refer to the same art")
    world = checked_world(inputs,args,physics)
    assets, = list(inputs.glob("pakchunk955-*.utoc"))
    common = load_container(assets)
    cooked_paths = {(common.mount_point.lstrip("./")+f).lower() for f in common.files}
    for site,row in art_package["teams"].items():
        if row["triangles"] != art["meshes"][site]["triangles"]:
            raise ValueError(f"Unverified visual asset for {site}")
        for material in row["material_packages"]:
            path = "Meteorite/Content/"+material.removeprefix("/Game/")+".uasset"
            if path.lower() not in cooked_paths:
                raise ValueError(f"Material is absent in Saturday map: {material}")
    stem = Path(art_package["stem"])
    if list(inputs.glob(stem.name.split("-")[0]+"-*")):
        raise ValueError("New static mesh container collides with an existing map asset")
    for ext in (".utoc",".ucas"):
        source = stem.with_suffix(ext)
        if sha(source) != art_package["files"][ext]:
            raise ValueError("Stale rendered package")
        for src in (source,args.bake/(WORLD+ext)):
            target = inputs/src.name
            shutil.copyfile(src,target)
            expected["content/"+target.name] = sha(target)
    level_file = inputs/"pwr.level.json"
    level = jsonfile(level_file)
    old = copy.deepcopy(level)
    new_decor = art_package["decor"]
    if {p["id"] for p in new_decor} != {"pwr_base_polish_"+t for t in ("red","blue","green")}:
        raise ValueError("Unexpected new placements")
    if any(r["id"] == d["id"] for r in level["decor"] for d in new_decor):
        raise ValueError("Previously staged base polish")
    for addition in new_decor:
        team = addition["id"].removeprefix("pwr_base_polish_")
        anchor, = (row for row in level["decor"] if row["id"] == f"pwr_newbase_{team}_architecture")
        native = art_package["teams"][team]
        baseline_origin = np.array(anchor["pos"])
        if (anchor["rot"] != [0,0,0] or anchor["scale"] != [1,1,1] or
            not np.allclose(addition["pos"],baseline_origin+native["center_cm"],atol=1e-7,rtol=0) or
            not np.allclose(physics["site_origins_blender_m"][team],baseline_origin*[.01,-.01,.01],atol=1e-8,rtol=0)):
            raise ValueError("Cooked visual and collision do not share baseline placement for " + team)
    level["decor"].extend(new_decor)
    if {k for k in old.keys() | level.keys() if old.get(k) != level.get(k)} != {"decor"}:
        raise ValueError("Base art changed other level sections")
    write_json(level_file,level)
    expected["map/level.json"] = sha(level_file)
    seal_release(args,out,inputs,info,expected,old_manifest,{"level_sections":["decor"],"world_packages":world,
        "art_scene_sha256":art["scene_sha256"],"art_package":art_package,"collision":physics})


def seal_release(args,out,inputs,info,expected,old_manifest,revision):
    filename = f"{PWR}-{args.version}.mjolnir"
    result = out/filename
    runtime = info["ce_content_runtime"]
    subprocess.run([args.cli,"map","pack",inputs,"--code","PWR","--runtime",runtime,
                    "--slug",PWR,"--version",args.version,"--name","Pelican Warfare",
                    "--size","large","--vehicles","true","--out",result],check=True)
    with zipfile.ZipFile(result) as packed:
        if (set(packed.namelist()) != set(expected)|{"mjolnir.json"} or
            json.loads(packed.read("mjolnir.json")) != dict(old_manifest,version=args.version)):
            raise ValueError("Unexpected packed map manifest, additions or omissions")
        for name,value in expected.items():
            if member_hash(packed,name) != value:
                raise ValueError("Map archive readback failed for " + name)
    paired = {"name":filename,"sha256":sha(result),"content_runtime":runtime}
    for folder in (Path("."),Path("solo")):
        previous = args.baseline/folder
        if jsonfile(previous/"developer-runtime-receipt.json")["paired_map"]["sha256"] != info["sha256"]:
            raise ValueError("Runtime is paired with a different map")
        pair_runtime(previous,out/folder,paired,args.version)
    shutil.copytree(args.baseline/"variants",out/"variants")
    for profile, files in info["variants"].items():
        if any(sha(out/"variants"/profile/p) != h for p,h in files.items()):
            raise ValueError("A gameplay variant changed")
    write_json(out/"receipt.json",{"archive":filename,"sha256":paired["sha256"],"bytes":result.stat().st_size,
        "ce_content_runtime":runtime,"variants":info["variants"],"baseline_sha256":info["sha256"],
        "members_sha256":expected,"installed":False,**revision})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("baseline","render","collision","control","bake","baseline-bsp","out"):
        parser.add_argument("--"+name,type=Path,required=True)
    parser.add_argument("--cli",type=Path,default=ROOT/"target/release/mjolnir.exe")
    parser.add_argument("--version",default="0.1.0-playtest.5")
    args = parser.parse_args()
    if args.out.exists():
        parser.error("Choose a fresh output folder")
    args.out.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(dir=args.out.parent) as temp:
        release = Path(temp)/"release"
        release.mkdir()
        stage(args,release)
        os.rename(release,args.out)
    print(args.out)
