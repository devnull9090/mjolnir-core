"""Cooked-package and release checks for the outlet planting, cutbank and spring."""
import argparse
from pathlib import Path
import shutil
import tempfile
from types import SimpleNamespace

import package_pwr_headwater as p
from bases_v1.stage_base_polish import seal_release, unpack_map
from stage_apron_finish import asset_layout
from stage_world_playtest import jsonfile

WORK = p.ROOT / "out/pwr/river-riparian"
BASIN = WORK.parent / "river-basin"
PARENT = "dc06be35b9549104baaba411eb86395651630b1011db4009918f08d1c76d8f0e"
BASELINE = BASIN / "saturday.39"
PRIOR = BASIN / "shore-contact/native/map-input"
WORLD_MAP = "Meteorite/Content/Levels/Halo1/Solo/PWR/PWR"

def prepare(version):
    checked = jsonfile(WORK/"editor-verified.json")
    stem_names = set(checked["assets"])
    additions = {"MJOLNIR/GrassPilot/Playable/" + stem + ext for stem in stem_names for ext in (".uasset",".ubulk")}
    required = {name for name in additions if name.endswith(".uasset")}
    baseline = jsonfile(BASELINE/"receipt.json")
    old = jsonfile(PRIOR.parent/"receipt.json")
    if p.sha(BASELINE/baseline["archive"]) != PARENT or baseline["sha256"] != PARENT:
        raise ValueError("Wrong lake release")
    for name, expected in old["native_members"].items():
        if p.sha(PRIOR/name) != expected or baseline["members_sha256"]["content/"+name] != expected:
            raise ValueError("Parent native package changed: "+name)
    p.out, p.n, p.maps, p.old = WORK, WORK/"packaging", WORK/"map-input", PRIOR
    p.apron = p.basin = False
    p.n.mkdir(exist_ok=True)
    p.prepare(allowed_additions=additions, require_material_change=False)
    toc = p.LAND + ".utoc"
    changes = jsonfile(p.n/"land-diff.json")
    if not required <= {k for k,v in changes.items() if v[0] is None}:
        raise ValueError("Missing native lake packages")
    if any(k not in additions and not k.endswith(("/LPE/LPE.umap","/LPE/LPE.ubulk",".ushaderbytecode")) for k in changes):
        raise ValueError("Unrelated native art change: "+str(list(changes)))
    mount, container_id, before = asset_layout(p.LAND, PRIOR/toc)
    new_mount, new_id, after = asset_layout(p.LAND, p.maps/toc)
    if (mount, container_id) != (new_mount, new_id) or any(after.get(k) != address for k,address in before.items()):
        raise ValueError("Changed a prior native asset address")
    bsp = BASIN / "native/physics/pwr.sbsp"
    if p.sha(bsp) != old["retained_bsp_sha256"]:
        raise ValueError("Terrain collision mismatch")
    support=None
    if version>=41:
        physics=WORK/"native/physics"
        bsp=physics/"pwr.sbsp"
        support=jsonfile(physics/"collision_scene.json")["riparian_cutbank"]
        verified=jsonfile(physics/"native-readback.json")
        if (p.sha(bsp)!=verified["compiled_bsp_sha256"] or support["support_sha256"]!=p.sha(WORK/"cutbank/support.npz")
                or support["changed_faces"]!=verified["verified_changed_faces"] or not verified["root_and_definition_havok_queries"]):
            raise ValueError("New bank support is unverified")
    folder = p.n/"world-bake"
    p.run([p.cli,"level","bake",BASIN/"native/native-level.json","--paks",p.paks,"--standalone","PWR",
           "--bsp","8="+str(bsp.resolve()),"--out-dir",folder,"--world",p.n/"LPE.umap"],p.n/"world-bake.log")
    world_toc = p.WORLD+".utoc"
    world_changes = p.changes(PRIOR/world_toc,folder/world_toc)
    allowed={WORLD_MAP+".umap",WORLD_MAP+".ubulk"}
    if support:
        allowed.update(k for k in world_changes if k.endswith(("/BSP_01_1_Start-scenario_structure_bsp.uasset","/BSP_01_1_Start-scenario_structure_bsp.ubulk")))
        if not any(k.endswith("-scenario_structure_bsp.ubulk") for k in allowed):
            raise ValueError("World cook did not include the new shore physics")
    if WORLD_MAP+".umap" not in world_changes or world_changes.keys()-allowed:
        raise ValueError("Unexpected gameplay, collision or lighting change: "+str(list(world_changes)))
    for suffix in (".ucas",".utoc"):
        shutil.copyfile(folder/(p.WORLD+suffix),p.maps/(p.WORLD+suffix))
    return dict(native_members={name:p.sha(p.maps/name) for name in old["native_members"]},
                editor=checked,land_packages=changes,world_packages=world_changes,
                base_bsp_sha256=old["retained_bsp_sha256"],compiled_bsp_sha256=p.sha(bsp),shore_support=support)

def stage(art, version):
    output = WORK / ("saturday."+str(version))
    if output.exists():
        raise FileExistsError(output)
    args = SimpleNamespace(baseline=BASELINE,cli=p.ROOT/"target/release/mjolnir.exe",version="0.1.0-playtest."+str(version))
    with tempfile.TemporaryDirectory(dir=WORK) as tmp:
        folder=Path(tmp)/"release"
        folder.mkdir()
        inputs, parent, hashes, manifest=unpack_map(BASELINE,folder)
        original=dict(hashes)
        for name, expected in art["native_members"].items():
            shutil.copyfile(p.maps/name,inputs/name)
            if p.sha(inputs/name)!=expected:
                raise ValueError("Staged native package differs: "+name)
            hashes["content/"+name]=expected
        seal_release(args,folder,inputs,parent,hashes,manifest,dict(
            modified_members=sorted(k for k in hashes if hashes[k]!=original[k]),
            riparian_shore=art,compiled_bsp_sha256=art["compiled_bsp_sha256"]))
        folder.rename(output)
    print(output)

if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--version",type=int,default=43)
    version=parser.parse_args().version
    stage(prepare(version),version)
