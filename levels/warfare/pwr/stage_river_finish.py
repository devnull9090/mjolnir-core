"""Seal the shoreline material revision and verified Flux contact on the .34 map."""
import argparse
from pathlib import Path
import shutil
import sys
import tempfile
from bases_v1.stage_base_polish import unpack_map,seal_release
from stage_world_playtest import LAND,WORLD,ROOT,jsonfile,sha,stage_name,world_entries,write_json

sys.path.insert(0,str(ROOT/"tools/level"))
from flux_heightfield import verify_state_files

PARENT="1d3230b179d454a738362a3e27886d2c63593030e3706b3a5176eb38b07c2d52"


def stage(args,folder):
    inputs,previous,hashes,manifest=unpack_map(args.baseline,folder)
    if previous["sha256"]!=PARENT:
        raise ValueError("The finish must be applied to the verified .34 river")
    original=dict(hashes)
    art=jsonfile(args.art/"receipt.json")
    cooked=args.art/"map-input"
    package_proof={}
    for stem in (LAND,WORLD):
        if not (cooked/(stem+".utoc")).exists():
            continue
        before=world_entries(inputs/(stem+".utoc"))
        after=world_entries(cooked/(stem+".utoc"))
        if before.keys()-after.keys():
            raise ValueError("Shader cook removed a shipping asset")
        changed=sorted(k for k in after if after[k]!=before.get(k))
        added=set(after)-before.keys()
        if stem==WORLD:
            if added or any(Path(k).name.lower() not in {"pwr.umap","pwr.ubulk"} for k in changed):
                raise ValueError("The shoreline art changed the scenario or Halo collision")
        if stem==LAND:
            known={"shaderarchive-meteorite_chunk965-pcd3d_sm6-pcd3d_sm6.ushaderbytecode",
                   "mjolnir/grasspilot/playable/m_pwrpilot.uasset","levels/halo1/solo/lpe/lpe.umap",
                   "levels/halo1/solo/lpe/lpe.ubulk"}
            if any(k.lower() not in known for k in (set(changed)-added)):
                raise ValueError(f"Unexpected edits to existing terrain assets: {changed}")
            if set(art.get("added_land_entries",[]))!=added:
                raise ValueError(f"Unverified additions to terrain container: {sorted(added)}")
        for ext in (".utoc",".ucas"):
            src=cooked/(stem+ext)
            if sha(src)!=art["native_members"][src.name]:
                raise ValueError("Native package does not match the material receipt")
            shutil.copyfile(src,inputs/src.name)
            hashes["content/"+src.name]=sha(inputs/src.name)
        package_proof[stem]={"changed":changed,"added":sorted(added),"preserved":len(before)-len(set(changed)-added)}
    if LAND not in package_proof:
        raise ValueError("Missing revised terrain material")
    water={}
    if args.water:
        water=jsonfile(args.water/"receipt.json")
        level_path=inputs/"pwr.level.json"
        level=jsonfile(level_path)
        new=jsonfile(args.water/"flux.json")
        old=level["flux"]
        if new["domains"][1]!=old["domains"][1] or new["domains"][0]["id"]!="upper_river" or len(new["domains"])!=2:
            raise ValueError("Unexpected change to the southeast water")
        upper=new["domains"][0]
        old_upper=old["domains"][0]
        if {k for k in upper.keys()|old_upper.keys() if upper.get(k)!=old_upper.get(k)}-{"domain","provenance","state"}:
            raise ValueError("Unexpected upper surface or simulation change")
        expected_domain=dict(old_upper["domain"])
        centre=expected_domain["centre"].copy()
        centre[1]+=8*expected_domain["cell"]
        if upper["domain"]!=dict(expected_domain,centre=centre):
            raise ValueError("Upper water may only extend by eight existing whole rows")
        upper["surface_painter"]={"from_domain":"lower_lake","start_ue_y_cm":-9375.0,"end_ue_y_cm":0.0}
        if not water["same_wet_component"] or water["inputs"]["terrain"]!=previous["headwater"]["terrain"]["runtime_manifest_sha256"]:
            raise ValueError("Water state no longer follows the verified native terrain")
        for d in new["domains"]:
            state=jsonfile(args.water/"flux_state"/d["id"]/"state.json")
            if d["state"]!=state:
                raise ValueError("Released state differs from baked descriptor")
            verify_state_files(args.water,state)
        for name,value in water["files"].items():
            member="map/"+name
            if member not in hashes or sha(args.water/name)!=value:
                raise ValueError("Unverified Flux file " + name)
            if name.startswith("flux_state/lower_lake/"):
                if value!=hashes[member]:
                    raise ValueError("Southeast water changed")
            elif name.startswith("flux_state/upper_river/"):
                shutil.copyfile(args.water/name,inputs/stage_name(member))
                hashes[member]=sha(inputs/stage_name(member))
            else:
                raise ValueError("Unexpected water file")
        level["flux"]=new
        write_json(level_path,level)
        hashes["map/level.json"]=sha(level_path)
    seal_release(args,folder,inputs,previous,hashes,manifest,{"modified_members":sorted(k for k,d in hashes.items() if d!=original[k]),
        "shore_finish":art,"world_packages":package_proof,"water_contact":water})
    if args.water:
        from pair_river_painter import install_painter_runtime
        install_painter_runtime(folder)


if __name__=="__main__":
    pa=argparse.ArgumentParser(description=__doc__)
    pa.add_argument("--baseline",type=Path,default=ROOT/"out/pwr/river-erosion/saturday.34")
    pa.add_argument("--art",type=Path,default=ROOT/"out/pwr/river-erosion/shore-finish")
    pa.add_argument("--water",type=Path)
    pa.add_argument("--cli",type=Path,default=ROOT/"target/release/mjolnir.exe")
    pa.add_argument("--version",default="0.1.0-playtest.35")
    pa.add_argument("--out",type=Path,default=ROOT/"out/pwr/river-erosion/saturday.35")
    args=pa.parse_args()
    if args.out.exists():
        pa.error("Choose a new release folder")
    with tempfile.TemporaryDirectory(dir=args.out.parent) as temp:
        folder=Path(temp)/"release";folder.mkdir()
        stage(args,folder)
        folder.rename(args.out)
    print(args.out)
