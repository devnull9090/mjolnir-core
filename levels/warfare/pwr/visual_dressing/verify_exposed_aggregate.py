"""Read back the .12 native terrain, checking the mineral shader against .11 and every original loose stone."""
import argparse
import hashlib
import json
from pathlib import Path
import tempfile

from ground_life_earth import ROOT, OUT, load, sha
from verify_distance_terrain import DEFAULT_OODLE, shader_receipt
from verify_ground_life_earth import inspect_land, ACTOR
from verify_distance_colonies import decode, GAME, identity_ancestors, native_matrices, number, package, world_from_container


FINISH=OUT.parent/"earth.12"
PARENT=OUT.parent/"saturday.11/map-input"


def compare_stone_actor(previous,world):
    by_release={}
    with tempfile.TemporaryDirectory(dir=FINISH) as t:
        for release,toc in (("11",PARENT/"pakchunk997-MJOLNIRMAP-PWR_P.utoc"),("12",world)):
            file=world_from_container(toc,Path(t)/(release+".umap"))
            doc=decode(file,GAME);raw=file.read_bytes()
            by_id={r["export"]:r for r in doc["exports"]};rows={}
            for row in doc["exports"]:
                if row["outer"]!=ACTOR or row["class"]!="HierarchicalInstancedStaticMeshComponent":continue
                p=row["properties"];n=int(number(p.get("NumBuiltInstances")));identity_ancestors(row,by_id)
                if any(k.startswith("OverrideMaterials[") for k in p) or p.get("BodyInstance.CollisionProfileName")!="NoCollision":
                    raise ValueError("Stone material owner or collision changed")
                rows[row["name"]]=dict(mesh=package(row,"StaticMesh"),count=n,
                    cull_cm=[int(number(p[k])) for k in ("InstanceStartCullDistance","InstanceEndCullDistance")],
                    native_transforms_sha256=hashlib.sha256(native_matrices(raw,row,n).tobytes()).hexdigest())
            by_release[release]=rows
    groups=by_release["12"]
    if len(groups)!=4 or groups!=by_release["11"]:raise ValueError("The .11 loose-stone actor changed in .12")
    count=sum(g["count"] for g in groups.values())
    if count!=previous["instances"] or sorted(g["mesh"] for g in groups.values())!=sorted(g["mesh"].split(".")[0] for g in previous["groups"]):
        raise ValueError("World records do not match the verified original .11 stone shapes")
    return dict(actor=ACTOR,instances=count,groups=groups,stone_affine_streams_byte_identical=True,
                world_container_sha256={ext:sha(world.with_suffix(ext)) for ext in (".utoc",".ucas")})


def verify(land,global_toc,world,cook_log):
    previous=load(OUT/"earth-native-readback.json");applied=load(FINISH/"editor-applied.json")
    if sha(OUT/"earth-native-readback.json")!=applied["complete_prior_11_release_receipt_sha256"]:
        raise ValueError("The reference .11 terrain receipt has drifted")
    if applied["new_earth_block_sha256"]==applied["prior_11_earth_block_sha256"]:
        raise ValueError("The authoring graph retains the .11 treatment")
    if cook_log.stat().st_mtime<(FINISH/"editor-applied.json").stat().st_mtime:
        raise ValueError("The cook precedes this material update")
    stored={"published_11_receipt":sha(OUT/"earth-native-readback.json"),"material_apply":applied}
    if land:
        terrain=inspect_land(land,global_toc,cook_log)
        before=shader_receipt(PARENT/"pakchunk965-MJOLNIRLAND-PWR_P.utoc",DEFAULT_OODLE)
        if before!=previous["sm6"]:raise ValueError("Published .11 native terrain disagrees with its prior shader receipt")
        for group in ("master","landscape_world"):
            if set(terrain["sm6"][group])==set(before[group]):raise ValueError("The archived .11 shader was reused: "+group)
            if (sorted(v.get("PS",0) for v in terrain["sm6"][group].values())!=sorted(v.get("PS",0) for v in before[group].values())):
                raise ValueError("The .12 pixel shader set diverges from .11 coverage: "+group)
        if terrain["textures"]!=previous["textures"]:raise ValueError("The .12 surface cook changed authored texture data")
        stored.update(terrain)
        stored["all_four_original_ground_fields_unchanged"]=True
        stored["compiled_material_replaced_in_master_and_world"]=True
    if world:
        stored.update(compare_stone_actor(previous,world))
    name="aggregate-native-readback.json" if land and world else "aggregate-terrain-readback.json" if land else "aggregate-world-readback.json"
    (FINISH/name).write_text(json.dumps(stored,indent=2)+"\n")
    print(name,stored.get("terrain_container_sha256"),stored.get("instances"))


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--land",type=Path);parser.add_argument("--world",type=Path)
    parser.add_argument("--global-toc",type=Path);parser.add_argument("--cook-log",type=Path,required=True)
    args=parser.parse_args()
    if not args.world and not args.land:parser.error("Supply the cooked map or terrain container")
    if args.land and not args.global_toc:parser.error("The terrain check requires --global-toc")
    verify(args.land,args.global_toc,args.world,args.cook_log)
