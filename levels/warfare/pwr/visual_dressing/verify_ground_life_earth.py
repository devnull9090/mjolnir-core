"""Verify authored habitat data, native gameplay-mesh ownership and cooked forest-road material."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import struct
import subprocess
import tempfile

import numpy as np
from PIL import Image

from ground_life_earth import Ground, OUT, ROOT, ROAD, BIOME, sha, sample, load
from verify_distance_colonies import (decode, GAME, native_matrices, world_from_container, identity_ancestors,
                                      matrices, number, package)
from verify_distance_terrain import DEFAULT_OODLE, load_container, read_chunk, load_name_batch, shader_receipt
from verify_site_finish import stage_files


REL=ROOT/"out/pwr/base-approaches/saturday.10/map-input"
PREV_LAND=REL/"pakchunk965-MJOLNIRLAND-PWR_P.utoc"
PREV_WORLD=REL/"pakchunk997-MJOLNIRMAP-PWR_P.utoc"
ACTOR="PWR_LooseGroundStones"


def source():
    spec=load(OUT/"earth.json")
    for f,h in spec["source_sha256"].items():
        if sha(OUT/f)!=h:raise ValueError("Stale earth source "+f)
    for f,h in spec["inputs"].items():
        if sha(ROOT/f)!=h:raise ValueError("The released source changed: "+f)
    for mesh in spec["stock_meshes"]:
        if sha(OUT/"stock"/mesh["source_file"])!=mesh["sha256"]:raise ValueError("Source scan changed")
    world=Ground(); planned=load(OUT/"points.json")["points"]; patches=load(OUT/"patches.json")
    field=np.asarray(Image.open(OUT/"earth-detail.png").convert("RGBA"));fresh=world.bake(patches)
    if not np.array_equal(field,fresh) or np.any(field[world.hard|world.protected]):raise ValueError("Ground painted outside survey")
    pos=np.array([r["position"] for r in planned]);x,y,z=pos.T
    err=np.max(abs(z-(world.field.sample(x,y)-.006)))
    if err>.00002 or not world.safe(x,y).all():raise ValueError("Stone projection/clearance error")
    density=sample(field[:,:,0],x,y)
    if np.mean(density>20)<.86:raise ValueError("Loose meshes do not match their earth deposits")
    return dict(source_sha256=spec["source_sha256"],stock_meshes=spec["stock_meshes"],patches=len(patches),
                candidates=len(planned),max_projection_error_m=round(float(err),8),min_road_centre_m=spec["closest_road_center_m"],
                allow_mask_outside_paving_water_bases=True,protected_texels=int(world.protected.sum()),
                candidates_on_visible_earth_ratio=round(float(np.mean(density>20)),4))


def inspect_world(toc):
    spec=load(OUT/"hism.json");pcg=load(OUT/"pcg-proof.json")
    if not pcg["deterministic"] or not pcg["projection_preserved"]:raise ValueError("Unverified stone PCG")
    with tempfile.TemporaryDirectory(dir=OUT) as temp:
        files=[world_from_container(q,Path(temp)/(str(i)+".umap")) for i,q in enumerate((PREV_WORLD,toc))]
        docs=[decode(p,GAME) for p in files];payloads=[p.read_bytes() for p in files]
    def records(data):
        return {(r["outer"],r["name"]):r for r in data["exports"] if r["class"]=="HierarchicalInstancedStaticMeshComponent"}
    old,current=map(records,docs)
    if any(k[0]==ACTOR for k in old) or not set(old)<=set(current):raise ValueError("Previous PWR instance containers differ")
    retained=0
    for k,v in old.items():
        new=current[k]; n=int(number(v["properties"].get("NumBuiltInstances")))
        if not n:continue
        if n!=int(number(new["properties"].get("NumBuiltInstances"))) or package(v,"StaticMesh")!=package(new,"StaticMesh"):
            raise ValueError("Changed .10 instance count or stock mesh "+str(k))
        if not np.array_equal(native_matrices(payloads[0],v,n),native_matrices(payloads[1],new,n)):
            raise ValueError("Moved existing native .10 instances "+str(k))
        retained+=n
    own={k[1]:r for k,r in current.items() if k[0]==ACTOR}
    if len(own)!=len(spec["groups"]):raise ValueError("Incomplete cooked rock ownership")
    by_id={r["export"]:r for r in docs[1]["exports"]};summary=[]
    def sorted_by_position(m):
        return m[np.lexsort(tuple(m[:,3,j] for j in (2,1,0)))]
    for i,g in enumerate(spec["groups"],1):
        r=own[f"MJFol_{i}_1_0"];p=r["properties"];n=int(number(p.get("NumBuiltInstances")))
        if n!=g["count"] or package(r,"StaticMesh")!=g["mesh"].split(".")[0]:raise ValueError("Stale cooked stone group")
        if [int(number(p.get(key))) for key in ("InstanceStartCullDistance","InstanceEndCullDistance")]!=g["cull"]:
            raise ValueError("Unexpected stone cull")
        if any(k.startswith("OverrideMaterials[") for k in p) or p.get("BodyInstance.CollisionProfileName")!="NoCollision":
            raise ValueError("Cooked mesh material owner or collision changed")
        identity_ancestors(r,by_id)
        xf=OUT/(spec["file"]+f".xf{i}")
        if sha(xf)!=spec["exact_sidecars"][i-1]:raise ValueError("Stale source matrices")
        ref=sorted_by_position(matrices(xf));cur=sorted_by_position(native_matrices(payloads[1],r,n))
        delta=abs(cur-ref);location=delta[:,3,:3].max();basis=delta[:,:3,:3].max()
        if location>.01 or basis>1e-5:raise ValueError("Cooked stone transform differs")
        summary.append(dict(mesh=g["mesh"],count=n,maximum_position_error_cm=float(location),maximum_basis_error=float(basis),
                            cull_cm=g["cull"],stock_materials=True,collision=False))
    return dict(world_container_sha256={s:sha(toc.with_suffix(s)) for s in (".utoc",".ucas")},
                actor=ACTOR,groups=summary,instances=sum(g["count"] for g in summary),pcg=pcg,
                retained_original_HISM_instances=retained,original_HISM_matrices_equal=True)


def inspect_land(toc,global_toc,log):
    report=log.read_text(errors="replace")
    if "BUILD SUCCESSFUL" not in report or "ExitCode=0" not in report:raise ValueError("Cook not complete")
    if re.search(r"Failed to compile Material|Default Material will be used in game|too many Samplers",report,re.I):
        raise ValueError("Shader fallback in UAT log")
    if log.stat().st_mtime<(OUT/"editor-build.json").stat().st_mtime:raise ValueError("Old shader cook")
    expected={"T_PWR_EarthDetail":OUT/"earth-detail.png","T_PWR_BiomeColor":BIOME,
              "T_PWR_RoadNetwork":ROAD,"T_PWR_SiteGround":ROOT/"out/pwr/base-approaches/site-finish/terrain/native-site-ground.png"}
    cli=str(ROOT/"target/release/mjolnir.exe"); textures={}
    with tempfile.TemporaryDirectory(dir=OUT) as temp:
        folder=Path(temp);stage_files(folder,toc,global_toc)
        for name,reference in expected.items():
            source=np.asarray(Image.open(reference).convert("RGBA"));side=len(source);mips={}
            base=["--paks",str(folder),"--asset",name]
            info=subprocess.run([cli,"texture","info",*base],check=True,capture_output=True,text=True).stdout
            if not(re.search(fr"size\s+{side}x{side}",info) and re.search(fr"mips\s+{side.bit_length()}\b",info) and "PF_B8G8R8A8" in info):
                raise ValueError("Changed format "+name)
            for lod in ((0,2,4,7,10) if name=="T_PWR_EarthDetail" else (0,)):
                dest=folder/f"{name}-{lod}.png"
                subprocess.run([cli,"texture","export",*base,"--mip",str(lod),"--out",str(dest)],check=True,capture_output=True)
                cooked=np.asarray(Image.open(dest).convert("RGBA"));w=side>>lod
                projected=np.stack([np.asarray(Image.fromarray(source[:,:,i]).resize((w,w),Image.Resampling.BOX)) for i in range(4)],axis=-1)
                err=int(np.max(np.abs(cooked.astype(int)-projected.astype(int))))
                if err>(3 if lod else 0):raise ValueError(f"Cooked {name}/{lod} differs")
                mips[str(lod)]=dict(max_byte_error=err,sha256=hashlib.sha256(cooked.tobytes()).hexdigest())
            textures[name]=dict(exact_rgba_texels=side*side,mips=mips)
    shader=shader_receipt(toc,DEFAULT_OODLE);before=shader_receipt(PREV_LAND,DEFAULT_OODLE)
    for n in ("master","landscape_world"):
        if set(before[n])==set(shader[n]) or max(p["PS"] for p in shader[n].values())<max(p["PS"] for p in before[n].values()):
            raise ValueError("Missing native .11 "+n+" PS permutations")
    c=load_container(toc);v=next(v for k,v in c.files.items() if k.endswith("GrassPilot/Playable/M_PWRPilot.uasset"))
    b=read_chunk(c,c.chunks[v],oodle_roots=[DEFAULT_OODLE]);names=load_name_batch(b,struct.unpack_from("<i",b,48)[0])[0]
    if any(f"/Game/MJOLNIR/GrassPilot/Playable/{leaf}" not in names for leaf in expected) or b"PWREarthDetail" not in b:
        raise ValueError("Native shader omitted the graded ground input")
    for mesh in load(OUT/"earth.json")["stock_meshes"]:
        if any(k.endswith("/"+mesh["path"].split(".")[-1]+".uasset") for k in c.files):raise ValueError("Editor stand-in overrides campaign rock")
    return dict(terrain_container_sha256={s:sha(toc.with_suffix(s)) for s in (".utoc",".ucas")},
                textures=textures,sm6=shader,cook_log_sha256=sha(log),fallback_diagnostics=0,
                stock_stone_packages_in_terrain_container=0)


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--world",type=Path);p.add_argument("--land",type=Path)
    p.add_argument("--global-toc",type=Path);p.add_argument("--cook-log",type=Path);args=p.parse_args()
    result=source()
    if args.land:
        if not args.global_toc or not args.cook_log:p.error("--land requires --global-toc and --cook-log")
        result.update(inspect_land(args.land,args.global_toc,args.cook_log))
    if args.world:result.update(inspect_world(args.world))
    name="earth-"+("native" if args.land and args.world else "world" if args.world else "terrain" if args.land else "source")+"-readback.json"
    (OUT/name).write_text(json.dumps(result,indent=2)+"\n"); print(name,result.get("instances"),result.get("terrain_container_sha256"))
