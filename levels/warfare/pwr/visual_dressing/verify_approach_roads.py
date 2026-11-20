"""Check the graded driving corridors, plus the native road texture, mip chain, SM6 material and .8 biome."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import tempfile

import numpy as np
from PIL import Image

from bake_approach_roads import ROOT, GEOMETRY, MASTER, smooth, sha
from verify_distance_terrain import shader_receipt, DEFAULT_OODLE, load_container, read_chunk, load_name_batch


BASE=ROOT/"out/pwr/landscape-distance/saturday.8/map-input/pakchunk965-MJOLNIRLAND-PWR_P.utoc"
BASE_FIELD=ROOT/"out/pwr/landscape-distance/terrain/cooked-valley-rgba.png"
LEAF="T_PWR_RoadNetwork"


def road_checks(rgba,geometry,approaches):
    n=rgba.shape[0]
    def sample(p):
        p=np.asarray(p); x=(p[0]+1000)*n/2000-.5; y=(1000-p[1])*n/2000-.5
        ix,iy=int(np.floor(x)),int(np.floor(y)); f,g=x-ix,y-iy
        data=((1-g)*((1-f)*rgba[iy,ix]+f*rgba[iy,ix+1])+
              g*((1-f)*rgba[iy+1,ix]+f*rgba[iy+1,ix+1]))/255.
        r,green,b,a=data
        kind=green/max(r,.001)
        return dict(coverage=round(float(r),3),engineered=round(float(smooth(.315,.685,kind)),3),
                    lateral_m=round(float((b-.5)*32),2),phase=round(float(a*2-1),3))
    witnesses={}
    for name,expected in (("red_upper_approach",1),("blue_upper_approach",1),("citadel_climb",1),
                          ("middle_w_approach",1),("southwest_sweep",0),("east_high_loop",0),
                          ("east_lake_overlook",0)):
        row=next(r for r in geometry["roads"] if r["id"]==name)
        line=np.asarray(row["centreline_m"])[:,:2]
        mid=len(line)//2; p=line[mid]
        along=line[mid+1]-line[mid-1]; along/=np.linalg.norm(along)
        side=np.array([-along[1],along[0]])
        checks={str(k):sample(p+k*side) for k in (-20,-11,-7,0,7,11,20)}
        for k in (-7,0,7):
            r=checks[str(k)]
            if r["coverage"]<.95 or abs(r["engineered"]-expected)>.08:
                raise ValueError(f"{name} bad {k}m carriageway point: {r}")
            if abs(abs(r["lateral_m"])-abs(k))>.85:
                raise ValueError(f"{name}: wheel and shoulder coordinate drift at {k}m: {r}")
        if max(checks["-20"]["coverage"],checks["20"]["coverage"])>.05:
            raise ValueError(f"{name}: treatment escaped graded bed")
        if expected and max(checks["-11"]["engineered"],checks["11"]["engineered"])>.05:
            raise ValueError(f"{name}: metal extends through gravel shoulder")
        phase=[sample(p+along*k)["phase"] for k in np.arange(-10.,10.,.75)]
        if max(phase)-min(phase)<1.55:
            raise ValueError(f"{name}: missing longitudinal phase variation")
        witnesses[name]={"authored_xy_m":p.round(3).tolist(),"samples_by_cross_road_offset_m":checks}
    for f in approaches["features"]:
        prop=f["properties"]; site,role=prop["site"],prop["role"]; line=np.array(f["geometry"]["coordinates"])
        if role=="court":
            centre=np.mean(line[0,:-1],axis=0); sample_at=sample(centre)
            if sample_at["coverage"]>.01: raise ValueError(f"{site}: terrain tangled with court mesh")
            witnesses[site+"_court"]={"authored_xy_m":centre.round(3).tolist(),"sample":sample_at}
        if role=="front":
            y=590. if site=="green" else -174.
            sort=np.argsort(line[:,1]); x=np.interp(y,line[sort,1],line[sort,0])
            sample_at=sample([x,y])
            if sample_at["coverage"]<.97 or sample_at["engineered"]<.95:
                raise ValueError(f"{site}: unpainted approach at {x}/{y}: {sample_at}")
            witnesses[site+"_court_handoff"]={"authored_xy_m":[round(x,2),y],"sample":sample_at}
        if role=="rear_pad":
            centre=np.mean(line[0,:-1],axis=0)
            if sample(centre)["coverage"]>.01: raise ValueError(f"{site}: soil overlaps rear pad")
            # Sample normal to the long square end of the unloading head.
            tip=line[0,:,1].max()
            outside=sample([centre[0],tip+1.4]); beyond=sample([centre[0],tip+5.])
            if outside["coverage"]<.10 or beyond["coverage"]>.01:
                raise ValueError(f"{site}: rear verge width at {tip}: {outside}, {beyond}")
            witnesses[site+"_rear_head"]={"authored_xy_m":[round(float(centre[0]),2),float(tip)],
                                         "outside_1_4m":outside,"outside_5m":beyond}
    water=np.asarray(Image.fromarray(np.load(MASTER/"runtime-master.water.npy")[::-1].copy())
                     .resize((n,n),Image.Resampling.BILINEAR))
    if np.any(rgba[:,:,0][water>=.47]):
        raise ValueError("Native road surface spilled into open water")
    return {"actual_corridors":witnesses,"road_free_water_texels":int((water>=.47).sum()),
            "original_ground_texels":int((rgba[:,:,0]==0).sum())}


def export_levels(toc,global_toc,folder):
    for pair in (toc,global_toc):
        for ext in (".utoc",".ucas"):
            src=pair.with_suffix(ext); dest=folder/src.name
            try: os.link(src,dest)
            except OSError: shutil.copyfile(src,dest)
    cli=ROOT/"target/release/mjolnir.exe"
    def image(name,lod):
        dest=folder/f"{name}-{lod}.png"
        subprocess.run([str(cli),"texture","export","--paks",str(folder),"--asset",name,"--mip",str(lod),"--out",str(dest)],
                       check=True,capture_output=True)
        return np.asarray(Image.open(dest).convert("RGBA"))
    info=subprocess.run([str(cli),"texture","info","--paks",str(folder),"--asset",LEAF],
                        check=True,capture_output=True,text=True).stdout
    if not (re.search(r"size\s+2048x2048",info) and re.search(r"mips\s+12\b",info) and "PF_B8G8R8A8" in info):
        raise ValueError(info)
    return {lod:image(LEAF,lod) for lod in (0,2,4,6,11)},image("T_PWR_BiomeColor",0)


def verify(art,approach_path,toc=None,global_toc=None,oodle=DEFAULT_OODLE):
    expected=np.asarray(Image.open(art/"road-network.png").convert("RGBA"))
    spec=json.loads((art/"roads.json").read_text())
    if sha(art/"road-network.png")!=spec["sha256"] or sha(approach_path)!=spec["approach_sha256"]:
        raise ValueError("Road data source has drifted")
    proof={"road_source_sha256":spec["sha256"],"approach_sha256":spec["approach_sha256"]}
    if toc:
        with tempfile.TemporaryDirectory(dir=art) as temp:
            levels,biome=export_levels(toc,global_toc,Path(temp))
        if not np.array_equal(expected,levels[0]): raise ValueError("Cooked road mask differs from source")
        if not np.array_equal(biome,np.asarray(Image.open(BASE_FIELD).convert("RGBA"))):
            raise ValueError("The frozen .8 ground RGB or wet coverage changed")
        proof["mip_check"]={}
        for lod,arr in levels.items():
            size=2048>>lod
            ref=np.stack([np.asarray(Image.fromarray(expected[:,:,i]).resize((size,size),Image.Resampling.BOX))
                          for i in range(4)],axis=-1)
            error=int(np.max(np.abs(arr.astype(int)-ref.astype(int))))
            if error>3: raise ValueError(f"Invalid native road mip {lod}, error={error}")
            proof["mip_check"][lod]={"metres_per_texel":round(2000/size,5),"byte_error":error,
                                    "native_sha256":hashlib.sha256(arr.tobytes()).hexdigest()}
        maps=shader_receipt(toc,oodle); old=shader_receipt(BASE,oodle)
        for kind in ("master","landscape_world"):
            if set(maps[kind])==set(old[kind]): raise ValueError(f"Stale .8 shader retained: {kind}")
        container=load_container(toc)
        item=next(v for k,v in container.files.items() if k.endswith("GrassPilot/Playable/M_PWRPilot.uasset"))
        material=read_chunk(container,container.chunks[item],oodle_roots=[oodle])
        names=load_name_batch(material,struct.unpack_from("<i",material,48)[0])[0]
        if "/Game/MJOLNIR/GrassPilot/Playable/"+LEAF not in names or b"PWRRoadNetwork" not in material:
            raise ValueError("Compiled shader lacks the exported track parameter or texture")
        expected=levels[0]
        proof.update(container_sha256={e:sha(toc.with_suffix(e)) for e in (".utoc",".ucas")},
                     prior_08_container_sha256={e:sha(BASE.with_suffix(e)) for e in (".utoc",".ucas")},
                     mip_count=12,exact_road_rgba=2048**2,unchanged_biome_rgba=1024**2,sm6=maps)
        Image.fromarray(expected).save(art/"native-road-network.png")
    proof.update(road_checks(expected,json.loads(GEOMETRY.read_text()),json.loads(approach_path.read_text())))
    name="cooked-roads-readback.json" if toc else "road-corridors.json"
    (art/name).write_text(json.dumps(proof,indent=2)+"\n")
    print(name,spec["sha256"],len(proof["actual_corridors"]),proof.get("container_sha256"))


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("art",type=Path)
    p.add_argument("approaches",type=Path)
    p.add_argument("--toc",type=Path)
    p.add_argument("--global-toc",type=Path)
    a=p.parse_args()
    verify(a.art.resolve(),a.approaches.resolve(),a.toc.resolve() if a.toc else None,
           a.global_toc.resolve() if a.global_toc else None)
