"""Prepare local game scenery for Blender using the runtime's swap recipes.

No HEK, Unreal or game launch. All extracted content stays in the supplied cache.
"""
import argparse
from collections import defaultdict, deque
import hashlib
import json
import math
from pathlib import Path
from types import SimpleNamespace
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/"tools/level"))
sys.path.insert(0, str(Path(__file__).resolve().parent/"mjolnir_level"))
from asset_cache import cache_asset
from scenery_swap import swap


def prepare(args):
    args.out.mkdir(parents=True, exist_ok=True)
    placement_path = args.staging/"placement.json"
    placement = json.loads(placement_path.read_text(encoding="utf-8"))
    source = json.loads(args.placements.read_text(encoding="utf-8"))
    choices = defaultdict(deque)
    for item in source["scenery"]:
        choices[item["tag"].lower()].append(item)
    entries = []
    for entry in placement["entries"]:
        if entry.get("kind") != "scenery" or not choices[entry["asset"].lower()]:
            continue
        item = choices[entry["asset"].lower()].popleft()
        entry["model"] = str((args.staging/entry["model"]).resolve())
        entry["pos"] = [v/placement.get("world_unit_meters",3.048) for v in item["position_m"]]
        entry["rot"] = [math.radians(item.get("yaw_degrees",0)),0,0]
        entries.append(entry)
    if any(choices.values()):
        raise ValueError("The staging conversion is missing source scenery models; convert those models before previewing")
    placement["entries"] = entries
    staging = args.out/"placement-input"
    staging.mkdir(exist_ok=True)
    (staging/"placement.json").write_text(json.dumps(placement),encoding="utf-8")
    swap_path = args.out/"swap.json"
    swap(SimpleNamespace(staging=str(staging), scene=str(args.scene),
        recipes=str(ROOT/"tools/level/data/b30_tree_recipes.json"),
        bounds=str(ROOT/"tools/level/data/b30_scenery_bounds.json"),
        spec=str(args.scene/"materials.spec.json"), tree_variant="Lrg_A",
        rocks="beach", biome="b30", foliage=None, sea=-250.0, out=str(swap_path),authored_decor=args.authored_decor))
    document = json.loads(swap_path.read_text())
    models = sorted({d["mesh"] for d in document["decor"]} | {document["leaves"]["mesh"]})
    manifest = {"schema_version":1,"swap":str(swap_path.resolve()),"models":{},"materials":{},
        "placements_sha256":hashlib.sha256(args.placements.read_bytes()).hexdigest(),
        "material_fidelity":"Native base-color, normal, opacity and selected AO/roughness bindings; authored macro-rock albedo/weathering. No UE material layers, wind or runtime lighting",
        "source":"Local installed game assets; never include this cache in a community source archive"}
    if args.authored_decor:
        decor_path=Path(args.authored_decor)
        manifest['authored_decor']={'path':str(decor_path.resolve()),
            'sha256':hashlib.sha256(decor_path.read_bytes()).hexdigest()}
    textures = {}
    for index, mesh in enumerate(models):
        print(f"Cache mesh {index+1}/{len(models)}: {mesh.rsplit('/',1)[-1]}",flush=True)
        manifest["models"][mesh] = str(cache_asset(args.cli,args.paks,args.cache,mesh).resolve())
        if 'SM_Tree_Pine_Sapling_A.' in mesh or 'SM_Tree_Sapling_Optimized.' in mesh:
            # Verified against the shipped material instances' TextureStreamingData.
            bark='/Game/Env/Bio/Materials/Bark/Bark_Forerunner_01/T_Bark_Forerunner_01'
            needles='/Game/Env/Bio/Tree/Pine/Tree_Windswept_A/Textures/T_Tree_Windswept_Branch_A'
            slots={}
            pairs=(('Bark_Mat',bark,False),('Leaves_Mat',needles,True)) if 'SM_Tree_Pine_Sapling_A.' in mesh else (
                ('MI_SaplingTrunk',bark,False),('MI_SaplingBranch',needles,True),('MI_Branch_Mat_LOD0_TwoSided',needles,True))
            for slot,prefix,alpha in pairs:
                slots[slot]={'albedo':str(cache_asset(args.cli,args.paks,args.cache,prefix+'_D','texture').resolve()),
                    'normal_dx':str(cache_asset(args.cli,args.paks,args.cache,prefix+'_N','texture').resolve()),
                    'normal_xy':True,'alpha':alpha}
            manifest['materials'][mesh]={'slots':slots,
                'fidelity':'Complete shipped pine sapling; native bark/needle texture slots; Blender shader approximation'}
            continue
        elif "Maned_Kuenovo_branch_01" in mesh:
            albedo, normal = "T_Tree_Maned_Kuenovo_Canopy_D", "T_Tree_Maned_Kuenovo_Canopy_N"
            alpha = True
        elif "Maned_Kuenovo" in mesh:
            albedo, normal = "T_T_Banyan_Bark_8K_D", "T_T_Banyan_Bark_8K_N"
            alpha = False
        elif "Uluwatu_Med_" in mesh:
            letter = mesh.split("Uluwatu_Med_",1)[1][0]
            albedo, normal = f"T_Rock_Uluwatu_Med_{letter}_D", f"T_Rock_Uluwatu_Med_{letter}_N"
            alpha = False
        elif 'Uluwatu_Cliff_B' in mesh:
            albedo,normal='T_Rock_Uluwatu_Cliff_B_D','T_Rock_Uluwatu_Cliff_B_N'
            alpha=False
        elif 'Rock_Desert_Cliff_' in mesh or 'Rock_CliffFlat_Kit_' in mesh:
            manifest['materials'][mesh]={'albedo':str(ROOT/'levels/test/tst/art/textures/coastal_granite_lichen_albedo.png'),
                'box_tile_m':8,'estimated_bump':True,'weathering':True,
                'fidelity':'Native geometry; authored coastal granite replaces Unreal layered rock shader for preview'}
            if 'Rock_Desert_Cliff_' in mesh:
                variant=mesh.split('Rock_Desert_Cliff_',1)[1][0]
                prefix=f'/Game/Env/Bio/Rock/Desert/Rock_Desert_Cliff_{variant}/Materials/T_Rock_Desert_Cliff_{variant}'
                manifest['materials'][mesh].update({
                    'normal_dx':str(cache_asset(args.cli,args.paks,args.cache,prefix+'_N','texture').resolve()),
                    'normal_xy':True,
                    'occlusion_red':str(cache_asset(args.cli,args.paks,args.cache,prefix+'_ORHG','texture').resolve())})
            continue
        else:
            continue
        if "Maned_Kuenovo" in mesh:
            prefix = "/Game/Env/Bio/Tree/ManedKuenovo/SharedAssets/"
            albedo, normal = prefix+albedo, prefix+normal
        for texture in (albedo,normal):
            if texture not in textures:
                textures[texture] = str(cache_asset(args.cli,args.paks,args.cache,texture,"texture").resolve())
        manifest["materials"][mesh] = {"albedo":textures[albedo],"normal_dx":textures[normal],
                                      "normal_xy":not alpha,"alpha":alpha}
    output = args.out/"native-preview.json"
    output.write_text(json.dumps(manifest,indent=2)+"\n",encoding="utf-8")
    print(f"Native Blender preview: {output}")


if __name__ == "__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--placements",type=Path,required=True)
    parser.add_argument("--scene",type=Path,required=True)
    parser.add_argument("--staging",type=Path,required=True)
    parser.add_argument("--cli",type=Path,required=True)
    parser.add_argument("--paks",type=Path,required=True)
    parser.add_argument("--cache",type=Path,required=True)
    parser.add_argument("--out",type=Path,required=True)
    parser.add_argument("--authored-decor",type=Path,help="Same native source placements used by the runtime upgrade")
    prepare(parser.parse_args())
