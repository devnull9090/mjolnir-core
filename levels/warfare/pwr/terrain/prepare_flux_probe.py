"""Prepare an isolated exact-bed Fluid Flux proof; never installs or calls game.

Explicit source paths keep temporary v3 proof data separate from final v5 water.
"""
import argparse
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys

import numpy as np

REPO=Path(__file__).resolve().parents[4]
sys.path.insert(0,str(REPO/"tools/level"))
from flux_heightfield import build_capture_bed, provenance, sha256
from heightfield import load_heightfield


def prepare(master,geometry,out,package=False):
    out=Path(out);out.mkdir(parents=True,exist_ok=True)
    field=load_heightfield(master)
    x=field.origin_m[0]+np.arange(field.dimensions[0])*field.spacing_m[0]
    y=field.origin_m[1]+np.arange(field.dimensions[1])*field.spacing_m[1]
    tile=field.heights_m[np.ix_((y>=242)&(y<=758),(x>=-478)&(x<=38))]
    plane=float(np.ceil(tile.max()+5)); height=float(np.ceil((plane-tile.min()+5)/.75))
    domain={"centre":[-22000,-50000,plane*100],"res":[256,256],"cell":200,"height":height*100}
    bed=out/"flux_bed.json"
    receipt=build_capture_bed(master,[domain],bed)
    data=json.loads(Path(geometry).read_text(encoding="utf-8"))
    river=next(x for x in data["watercourses"] if x["id"]=="central_river")
    points=np.array(river["surface_centreline_m"])
    points=points[(points[:,0]>-456)&(points[:,0]<16)&(points[:,1]>264)&(points[:,1]<736)]
    if len(points)<3:raise ValueError("Upper-cascade proof tile does not intersect the authored river")
    arc=np.r_[0,np.cumsum(np.linalg.norm(np.diff(points[:,:2],axis=0),axis=1))]
    sources=[]
    for distance in np.arange(0,arc[-1]+1,16):
        p=points[np.argmin(abs(arc-distance))]
        sources.append({"pos":[round(p[0]*100,3),round(-p[1]*100,3),round(p[2]*100,3)],
                        "scale":2.5,"volume":1,"mode":2,"prime":True})
    sources.insert(0,dict(sources[0],prime=False,mode=0,volume=2))
    sources.append(dict(sources[-1],prime=False,mode=1,volume=1))
    spec={"id":"upper_cascade","playback":"simulate","domain":domain,"origin":[0,0,0],
          "sources":sources,"ground":["pwr_flux_bed"],"prime_ms":45000,
          "hide":["pwr_terrain_3"],"provenance":provenance(master,geometry,bed,domain,sources)}
    (out/"flux.spec.json").write_text(json.dumps({"schema":"mjolnir-flux-v2","domains":[spec]},indent=2)+"\n")
    package_bed(out,receipt,package=package)
    print(json.dumps(receipt,indent=2))


def package_bed(out,receipt,package=False):
    """Native-package the exact bed for isolated authoring; no installed writes."""
    out=Path(out);bed=out/"flux_bed.json"
    mesh=json.loads(bed.read_text())
    ue=np.array(mesh["positions"])
    vertices=(ue[:,[0,2,1]]/100).astype("<f4")
    normals=np.tile([0,1,0],(len(vertices),1)).astype("<f4")
    uv=(vertices[:,[0,2]]/10).astype("<f4")
    indices=np.array(mesh["indices"],dtype="<u4")
    parts=[vertices.tobytes(),normals.tobytes(),uv.tobytes(),indices.tobytes()]
    views=[];offset=0
    for part in parts:views.append({"buffer":0,"byteOffset":offset,"byteLength":len(part)});offset+=len(part)
    gltf={"asset":{"version":"2.0","generator":"Exact runtime-grid Flux capture proof"},
        "buffers":[{"uri":"bed.bin","byteLength":offset}],"bufferViews":views,
        "accessors":[{"bufferView":0,"componentType":5126,"count":len(vertices),"type":"VEC3","min":vertices.min(0).tolist(),"max":vertices.max(0).tolist()},
            {"bufferView":1,"componentType":5126,"count":len(vertices),"type":"VEC3"},
            {"bufferView":2,"componentType":5126,"count":len(vertices),"type":"VEC2"},
            {"bufferView":3,"componentType":5125,"count":len(indices),"type":"SCALAR"}],
        "materials":[{"name":"FluxBed"}],"meshes":[{"primitives":[{"attributes":{"POSITION":0,"NORMAL":1,"TEXCOORD_0":2},"indices":3,"material":0}]}],
        "nodes":[{"mesh":0}],"scenes":[{"nodes":[0]}],"scene":0}
    (out/"bed.gltf").write_text(json.dumps(gltf));(out/"bed.bin").write_bytes(b"".join(parts))
    if package:
        paks=Path("C:/Program Files (x86)/Steam/steamapps/common/Halo Campaign Evolved/Meteorite/Content/Paks")
        asset="/Game/MJOLNIR/Maps/PWR/SM_PWR_FluxProofBed"
        def run(name,args):
            result=subprocess.run(list(map(str,args)),cwd=REPO,capture_output=True,text=True)
            log=result.stdout+result.stderr;(out/(name+".log")).write_text(log,encoding="utf-8")
            if result.returncode or "MISMATCH" in log:raise RuntimeError(log[-2500:])
            return log
        log=run("mesh",[REPO/"target/release/examples/mesh_rewrite.exe",paks,"basicshapes/cylinder",
            out/"bed.gltf",out/"bed.uasset","--offset","0,0,0","--rename",asset,
            "--material","FluxBed=/Engine/EngineMaterials/DefaultMaterial=*","--asset-imports","--selftest"])
        match=re.search(r"SPAWN: location \(([-\d.]+), ([-\d.]+), ([-\d.]+)\) cm, uniform scale ([\d.]+)",log)
        if not match:raise RuntimeError("Native mesh transform missing")
        x,y,z,scale=map(float,match.groups())
        stem="pakchunk962-MJOLNIRPWRFLUXPROOF_P"
        run("package",[REPO/"target/release/examples/package_add.exe",paks,out,"--name",stem,"--package",f"{asset}={out/'bed.uasset'}"])
        shutil.copy2(paks/"pakchunk115-Windows.pak",out/(stem+".pak"))
        actor={"id":"pwr_flux_bed","mesh":asset+".SM_PWR_FluxProofBed","pos":[x,y,z],"rot":[0,0,0],"scale":[scale]*3,
               "capture_only":True,"cast_shadow":False,"materials":["/Engine/EngineMaterials/DefaultMaterial.DefaultMaterial"]}
        (out/"bed.actor.json").write_text(json.dumps(actor,indent=2)+"\n")
        receipt["container"]={suffix:sha256(out/(stem+suffix)) for suffix in (".utoc",".ucas",".pak")}
        receipt["actor"]=actor
    (out/"proof.prepare.receipt.json").write_text(json.dumps(receipt,indent=2)+"\n")


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--heightfield",required=True);p.add_argument("--geometry",required=True)
    p.add_argument("--out",required=True);p.add_argument("--package",action="store_true")
    a=p.parse_args();prepare(a.heightfield,a.geometry,a.out,a.package)
