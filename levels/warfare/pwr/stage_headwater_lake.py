"""Seal the northern headwater lake onto the Saturday .31 playtest release."""
import argparse
import json
from pathlib import Path
import shutil
import sys
import tempfile
from zipfile import ZipFile

from bases_v1.stage_base_polish import seal_release, unpack_map
from stage_world_playtest import LAND, ROOT, WORLD, jsonfile, sha, stage_name, world_entries, write_json

sys.path.insert(0, str(ROOT/"tools/level"))
from flux_heightfield import verify_state_files

PARENT = "b5164c903de051e9d313785e8667d376cfcdac3abd7aa590ebe021bb21cf2582"
VERIFY_WORLD = {"pwr.umap","pwr.ubulk","bsp_01_1_start-scenario_structure_bsp.uasset",
                "bsp_01_1_start-scenario_structure_bsp.ubulk"}


def validate_cook(old, new, stem):
    before = world_entries(old/(stem+".utoc"))
    after = world_entries(new/(stem+".utoc"))
    if before.keys() != after.keys():
        raise ValueError("A cooked package was added or removed in " + stem)
    changed = sorted(k for k in before if before[k] != after[k])
    filenames = {Path(k).name.lower() for k in changed}
    if stem == WORLD:
        if not {"pwr.umap","bsp_01_1_start-scenario_structure_bsp.ubulk"} <= filenames <= VERIFY_WORLD:
            raise ValueError(f"Unexpected changes to the world or gameplay tags: {changed}")
    else:
        allowed = {"shaderarchive-meteorite_chunk965-pcd3d_sm6-pcd3d_sm6.ushaderbytecode",
                   "mjolnir/grasspilot/playable/m_pwrpilot.uasset",
                   "levels/halo1/solo/lpe/lpe.umap","levels/halo1/solo/lpe/lpe.ubulk"}
        if {k.lower() for k in changed} != allowed:
            raise ValueError(f"Unexpected terrain asset changes: {changed}")
    return {"modified":changed, "preserved_count":len(before)-len(changed)}


def stage(args, folder):
    work = args.work
    water_dir = args.water or work/"water-fix"
    inputs, info, hashes, manifest = unpack_map(args.baseline,folder)
    if info["sha256"] != PARENT:
        raise ValueError("The lake was built for a different baseline")
    original = dict(hashes)
    terrain = jsonfile(work/"terrain/headwater-terrain.receipt.json")
    water = jsonfile(water_dir/"receipt.json")
    native = jsonfile(work/"native/landscape-collision.json")
    dressing = jsonfile(work/"dressing/dressing-receipt.json")
    shore = jsonfile(work/"shore-material.json")
    terrain_sha = sha(work/"terrain/runtime-master.json")
    if (terrain_sha != terrain["runtime_manifest_sha256"] or water["inputs"]["terrain"] != terrain_sha
            or water["inputs"]["geometry"] != sha(work/"terrain/terrain.geometry.json")
            or terrain["r16_sha256"] != sha(work/"terrain/runtime-master.r16")
            or not terrain["closed_sill_containment_verified"] or not water["same_wet_component"]):
        raise ValueError("The terrain and water were not validated against each other")
    if (dressing["terrain_sha256"] != terrain_sha or dressing["original_level_sha256"] != hashes["map/level.json"]
            or dressing["original_foliage_sha256"] != hashes["map/foliage.bin"]):
        raise ValueError("Shoreline dressing used a different terrain or baseline")
    for name,digest in dressing["files_sha256"].items():
        if sha(work/"dressing"/name) != digest:
            raise ValueError("Dressing proof does not match " + name)

    def replace(member, source):
        if member not in original:
            raise ValueError(f"Unknown release member: {member}")
        dest = inputs/stage_name(member)
        shutil.copyfile(source,dest)
        hashes[member] = sha(dest)

    packages = {}
    cooked = work/"native/map-input"
    physical = jsonfile(work/native["physical_queries"])
    if (not physical["root_and_definition_havok_queries"] or physical["compiled_bsp_sha256"] != native["sbsp"]
            or sha(work/"native/physics/pwr.sbsp") != native["sbsp"]):
        raise ValueError("Physics readback differs from the cooked BSP")
    for stem in (WORLD,LAND):
        packages[stem] = validate_cook(inputs,cooked,stem)
        for ext in (".ucas",".utoc"):
            if sha(cooked/(stem+ext)) != native["native_members"][stem+ext]:
                raise ValueError("Native package changed since the cook inspection")
            replace("content/"+stem+ext,cooked/(stem+ext))

    level_file = inputs/"pwr.level.json"
    level = jsonfile(level_file)
    flux = jsonfile(water_dir/"flux.json")
    if [d["id"] for d in flux["domains"]] != ["upper_river","lower_lake"]:
        raise ValueError("Changed domain inventory")
    old_domains = level["flux"]["domains"]
    if flux["domains"][1] != old_domains[1]:
        raise ValueError("The southeast lake domain has changed")
    upper = flux["domains"][0]
    allowed = {"provenance","state","sources"}
    surface_reference = {}
    if args.river_reference:
        with ZipFile(args.river_reference) as archive:
            reference = json.loads(archive.read("map/level.json"))["flux"]
        if not {"domain","state","sources"} <= reference.keys():
            raise ValueError("The optical reference must contain a playable river")
        if (water["inputs"]["rocks"] != sha(work/"dressing/flow-rocks.json")
                or native["dressing_ledger_sha256"] != sha(work/"dressing/decor-moves.json")
                or native["terrain_r16_sha256"] != terrain["r16_sha256"]
                or water["timberland_parent_sha256"] != sha(args.river_reference)):
            raise ValueError("The water, installed art and collision use different reference inputs")
        keys = {"color_preset","surface_vectors","surface_scalars"}
        for key in keys | {"surface"}:
            if (key in upper) != (key in reference) or upper.get(key) != reference.get(key):
                raise ValueError("Northern surface differs from the reference river at " + key)
        allowed |= {k for k in keys if upper.get(k) != old_domains[0].get(k)}
        surface_reference = {"river_reference":args.river_reference.name,
                             "reference_sha256":sha(args.river_reference)}
    if {k for k in upper.keys()|old_domains[0].keys() if upper.get(k) != old_domains[0].get(k)} != allowed:
        raise ValueError("Unexpected changes to the northern water domain")
    for domain in flux["domains"]:
        state = domain["state"].copy()
        if state != jsonfile(water_dir/"flux_state"/domain["id"]/"state.json"):
            raise ValueError("Packed Flux state differs from level descriptor")
        verify_state_files(water_dir,state)
    for name, digest in water["files"].items():
        member = "map/"+name
        source = water_dir/name
        if sha(source) != digest:
            raise ValueError("Water proof does not match " + name)
        if name.startswith("flux_state/lower_lake/"):
            if original[member] != digest:
                raise ValueError("Southern water changed")
        elif name.startswith("flux_state/upper_river/"):
            replace(member,source)
        else:
            raise ValueError("Unexpected water output " + name)
    decor = jsonfile(work/"dressing/level-decor.json")
    if not isinstance(decor,list) or [p["id"] for p in decor] != [p["id"] for p in level["decor"]]:
        raise ValueError("Unexpected change in placement identities or ordering")
    ledger = jsonfile(work/"dressing/decor-moves.json")
    moved = {item["id"]:item for item in ledger["decor"]}
    if len(moved) != len(ledger["decor"]):
        raise ValueError("Duplicate rock placement in dressing ledger")
    for old,new in zip(level["decor"],decor):
        row = moved.get(old["id"])
        if row:
            if (row["old_pos_ue_cm"] != old["pos"] or row["new_pos_ue_cm"] != new["pos"]
                    or dict(old,pos=new["pos"]) != new or row["mesh"] != old["mesh"]):
                raise ValueError("Cooked rock placement differs from ledger: " + row["id"])
        elif old != new:
            raise ValueError("Change outside the shoreline dressing ledger: " + old["id"])
    groups = jsonfile(work/"dressing/foliage.json")
    if any(level["foliage"].get(k) != v for k,v in groups.items()):
        raise ValueError("Packed grass groups differ from the baseline native scene")
    level["decor"] = decor
    level["flux"] = flux
    write_json(level_file,level)
    hashes["map/level.json"] = sha(level_file)
    replace("map/foliage.bin",work/"dressing/foliage.bin")

    modified = sorted(k for k in hashes if hashes[k] != original[k])
    if not all("map/flux_state/upper_river/"+n in modified for n in ("state.json","ground.exr","velocity.exr","height.exr")):
        raise ValueError("Incomplete upper water update")
    seal_release(args,folder,inputs,info,hashes,manifest,{
        "modified_members":modified, "level_sections":["decor","flux"], "world_packages":packages,
        "headwater":{"terrain":terrain,"water":water,"native":native,"dressing":dressing,
                     "shore_material":shore,**surface_reference}})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline",type=Path,default=ROOT/"out/pwr/sweep-polish/round31/saturday.31")
    parser.add_argument("--work",type=Path,default=ROOT/"out/pwr/headwater-lake")
    parser.add_argument("--water",type=Path,help="Verified alternate Fluid Flux bake")
    parser.add_argument("--river-reference",type=Path,help="Map package supplying the northern river surface settings")
    parser.add_argument("--cli",type=Path,default=ROOT/"target/release/mjolnir.exe")
    parser.add_argument("--version",default="0.1.0-playtest.33")
    parser.add_argument("--out",type=Path)
    args = parser.parse_args()
    target = args.out or args.work/("saturday."+args.version.rsplit(".",1)[-1])
    if target.exists():
        parser.error(f"Refusing to replace {target}")
    with tempfile.TemporaryDirectory(dir=target.parent) as temp:
        folder = Path(temp)/"release"
        folder.mkdir()
        stage(args,folder)
        folder.rename(target)
    print(target)
