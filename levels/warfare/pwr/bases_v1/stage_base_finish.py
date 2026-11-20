"""Seal the cosmetic .7 overlay on the verified .6 map and both runtime profiles."""
import argparse
import os
from pathlib import Path
import shutil
import tempfile

import numpy as np

from stage_base_polish import ROOT, unpack_map, seal_release
from stage_wide_gate import contents
from stage_world_playtest import load_container, sha, write_json, jsonfile


def stage(args,out):
    inputs,info,expected,old_manifest = unpack_map(args.baseline,out)
    art = jsonfile(args.art/"base-polish.json")
    native = jsonfile(args.render/"package.json")
    old_art = jsonfile(args.old_art/"base-polish.json")
    cores = sha(args.art/"solid-cores.json")
    if (sha(Path(art["scene"])) != art["scene_sha256"] or cores != art["collision_sha256"] or
        cores != info["collision"]["core_export_sha256"] or cores != old_art["collision_sha256"] or
        old_art["scene_sha256"] != info["art_scene_sha256"] or Path(native["source"]).resolve() != args.art.resolve()):
        raise ValueError("Cosmetic finish failed source or physical-core lineage")
    if any(not check["passed"] for boxes in art["clearances"].values() for check in boxes.values()):
        raise ValueError("Cosmetic finish blocks a swept vehicle, gallery or roof reservation")
    stem = Path(native["stem"])
    if stem.name != "pakchunk953-MJOLNIRBASEPOLISH-PWR_P" or not (inputs/(stem.name+".utoc")).is_file():
        raise ValueError("Expected the existing .6 additive render package")
    prior_contents = contents(inputs/(stem.name+".utoc"))
    rendered = contents(stem.with_suffix(".utoc"))
    if prior_contents.keys() != rendered.keys():
        raise ValueError("Cosmetic overlay changed internal asset inventory")
    changed_content = sorted(k for k in rendered if rendered[k] != prior_contents[k])
    sites = ("red","blue","green")
    meshes = {f"SM_PWR_BasePolish_{s.title()}.uasset" for s in sites}
    changed_assets = {Path(k).name for k in changed_content if not k.startswith("<ContainerHeader:")}
    if changed_assets != meshes:
        raise ValueError("Expected only the three finished render meshes and their package store")
    assets, = inputs.glob("pakchunk955-*.utoc")
    palette = load_container(assets)
    material_paths = {(palette.mount_point.lstrip("./")+p).lower() for p in palette.files}
    for site in sites:
        team = native["teams"][site]
        if (team["triangles"] != art["meshes"][site]["triangles"] or not team["cylinder_culling_bounds_verified"]
            or team["maximum_uv_error"]>1e-6 or team["maximum_vertex_error_m"]>.002):
            raise ValueError(f"Invalid native finish readback for {site}")
        for material in team["material_packages"]:
            if ("Meteorite/Content/"+material.removeprefix("/Game/")+".uasset").lower() not in material_paths:
                raise ValueError("Missing material in unchanged .6 palette: "+material)
    for ext in (".utoc",".ucas"):
        src = stem.with_suffix(ext)
        if sha(src) != native["files"][ext]:
            raise ValueError("Additive render container changed after its native readback")
        dest = inputs/src.name
        shutil.copyfile(src,dest)
        expected["content/"+dest.name] = sha(dest)
    level_file = inputs/"pwr.level.json"
    level = jsonfile(level_file)
    additions = {d["id"]:d for d in native["decor"]}
    if set(additions) != {"pwr_base_polish_"+site for site in sites}:
        raise ValueError("Unexpected actor IDs in final rendering")
    changed = []
    for i,old in enumerate(level["decor"]):
        if old["id"] not in additions:
            continue
        team = old["id"].removeprefix("pwr_base_polish_")
        fresh = additions.pop(old["id"])
        anchor, = [r for r in level["decor"] if r["id"] == f"pwr_newbase_{team}_architecture"]
        if (set(old) != set(fresh) or any(old[k]!=fresh[k] for k in old if k not in ("pos","scale"))
            or not np.allclose(fresh["pos"],np.array(anchor["pos"])+native["teams"][team]["center_cm"],rtol=0,atol=1e-8)
            or fresh["scale"] != [native["teams"][team]["scale"]]*3):
            raise ValueError("Unreviewed actor settings or geometry alignment for "+team)
        if old != fresh:
            changed.append(old["id"])
            level["decor"][i] = fresh
    if additions:
        raise ValueError("Missing .6 visual placement in map")
    if changed:
        write_json(level_file,level)
        expected["map/level.json"] = sha(level_file)
    differences = {k for k in info["members_sha256"] if info["members_sha256"][k]!=expected[k]}
    allowed = {"content/"+stem.name+ext for ext in (".utoc",".ucas")}
    if changed:
        allowed.add("map/level.json")
    if not differences <= allowed:
        raise ValueError("Cosmetic finish changed terrain, collision, native architecture, guides or gameplay")
    seal_release(args,out,inputs,info,expected,old_manifest,{"baseline_art_scene_sha256":old_art["scene_sha256"],
        "art_scene_sha256":art["scene_sha256"],"art_package":native,"collision":info["collision"],
        "native_gate_witnesses":info["native_gate_witnesses"],"native_visual_changes":{stem.name:changed_content},
        "level_sections":["decor"] if changed else [],"changed_actors":changed,"changed_map_members":sorted(differences),
        "preserved_map_members":len(expected)-len(differences),"physical_cores_identical_to_baseline":True})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for k in ("baseline","render","art","old-art","out"):
        parser.add_argument("--"+k,type=Path,required=True)
    parser.add_argument("--version",default="0.1.0-playtest.7")
    parser.add_argument("--cli",type=Path,default=ROOT/"target/release/mjolnir.exe")
    args = parser.parse_args()
    if args.out.exists():
        parser.error("Choose a fresh output directory")
    args.out.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(dir=args.out.parent) as scratch:
        release = Path(scratch)/"release"
        release.mkdir()
        stage(args,release)
        os.rename(release,args.out)
    print(args.out)
