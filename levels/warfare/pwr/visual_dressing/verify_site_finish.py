"""Read the actual .10 ground, roads and local atlas from 965 and compare them with .9."""
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

from bake_site_finish import ART, GATES, GEOMETRY, PREVIOUS, ROAD, ROOT, SITES, SPAN, TILE, WORK, Survey, sha
from verify_approach_roads import road_checks
from verify_distance_terrain import DEFAULT_OODLE, load_container, load_name_batch, read_chunk, shader_receipt


PRIOR=WORK/"saturday.9/map-input/pakchunk965-MJOLNIRLAND-PWR_P.utoc"
FOLDER="/Game/MJOLNIR/GrassPilot/Playable/"
NAMES={"biome":"T_PWR_BiomeColor","grade":"T_PWR_SiteGround","road":"T_PWR_RoadNetwork"}


def rgba(path):
    return np.asarray(Image.open(path).convert("RGBA"))


def sample_atlas(field,site,x,y):
    cx,cy,col,row=SITES[site]
    px=int(col*TILE+((x-cx)/SPAN+.5)*TILE)
    py=int(row*TILE+((cy-y)/SPAN+.5)*TILE)
    return field[py,px]


def validate_sources():
    spec=json.loads((ART/"site-ground.json").read_text())
    for k,f in spec["files"].items():
        if sha(ART/f)!=spec["source_sha256"][k]: raise ValueError("Changed "+k+" source")
    for f,h in spec["inputs"].items():
        if sha(ROOT/f)!=h: raise ValueError("Changed input "+f)
    new=rgba(ART/spec["files"]["biome"]); old=rgba(PREVIOUS); grade=rgba(ART/spec["files"]["grade"])
    allowed=np.asarray(Image.open(ART/spec["files"]["support"]))>0
    if not np.array_equal(old[~allowed],new[~allowed]) or not np.array_equal(old[:,:,3],new[:,:,3]):
        raise ValueError("Authoring changed terrain outside graded sites or wetland coverage")
    survey=Survey()
    probes={}
    local=((np.arange(TILE)+.5)/TILE-.5)*SPAN
    coords=(np.arange(1024)+.5)*2000/1024-1000
    support=np.zeros_like(allowed)
    for site,(cx,cy,col,row) in SITES.items():
        px,py=np.meshgrid(cx+local,cy-local)
        reference=survey.field(site,px,py)
        tile=grade[row*TILE:(row+1)*TILE,col*TILE:(col+1)*TILE]
        if not np.array_equal(reference,tile): raise ValueError("Stale grading geometry at "+site)
        xs=np.where(abs(coords-cx)<SPAN*.5)[0]; ys=np.where(abs(-coords-cy)<SPAN*.5)[0]
        x,y=np.meshgrid(coords[xs],-coords[ys])
        support[np.ix_(ys,xs)]=survey.field(site,x,y)[:,:,0]>0
        points={"west_toe":(cx-82,cy),"east_toe":(cx+82,cy-8),"rear_shoulder":(cx-42,cy+78),
                "west_turf":(cx-110,cy),"rear_turf":(cx+50,cy+112),"court_centre":(cx,cy),
                "engineered_rear_drive":(cx,cy+86),"rear_head":(cx,cy+103)}
        if site!="green":
            line=np.asarray(next(r["centreline_m"] for r in survey.geometry["roads"] if r["id"]==site+"_apron"))
            order=np.argsort(line[:,1])
            for label,ly in (("service_flare",-173),("service_before",-203)):
                points[label]=(np.interp(ly,line[order,1],line[order,0]),ly)
        probes[site]={label:{"xy_m":[round(x,2),round(y,2)],"rgba":sample_atlas(grade,site,x,y).tolist()}
                      for label,(x,y) in points.items()}
        def channel(key,idx=0):
            return probes[site][key]["rgba"][idx]
        if min(channel(k) for k in ("west_toe","east_toe","rear_shoulder"))<104:
            raise ValueError(f"{site}: missing mineral-to-grass apron "+str(probes[site]))
        if any(channel(k)>1 for k in ("west_turf","rear_turf","court_centre","engineered_rear_drive","rear_head")):
            raise ValueError(f"{site}: treatment exceeds the natural edge or an occupied route")
        if site!="green" and (channel("service_flare",3)<140 or channel("service_before",3)>4):
            raise ValueError(f"{site}: no graduated gravel handoff "+str(probes[site]))
        if not np.count_nonzero(tile[:,:,0]>155)>1500: raise ValueError("Weak court grounding at "+site)
    if not np.array_equal(allowed,support): raise ValueError("Authorization mask no longer matches the sites")
    if np.any(grade[TILE:,TILE:]): raise ValueError("Nonempty spare tile")
    return dict(source_sha256=spec["source_sha256"],prior_biome_source_sha256=sha(PREVIOUS),
                road_source_sha256=sha(ROAD),sites=spec["sites"],survey_samples=probes,
                changed_biome_texels=int(np.count_nonzero(np.any(old!=new,axis=-1))),
                exterior_identical_rgba=int((~allowed).sum()),unchanged_wet_alpha=1024**2)


def read_texture(folder,key,lods):
    name=NAMES[key];size={"biome":1024,"road":2048,"grade":512}[key]
    cmd=[str(ROOT/"target/release/mjolnir.exe"),"texture"]
    args=["--paks",str(folder),"--asset",name]
    info=subprocess.run(cmd+["info",*args],check=True,capture_output=True,text=True).stdout
    if not (re.search(fr"size\s+{size}x{size}",info) and re.search(fr"mips\s+{size.bit_length()}\b",info)
            and "PF_B8G8R8A8" in info):
        raise ValueError("Unexpected native "+name+" texture "+info)
    values={}
    for lod in lods:
        out=folder/f"{name}-{lod}.png"
        subprocess.run(cmd+["export",*args,"--mip",str(lod),"--out",str(out)],check=True,capture_output=True)
        values[lod]=rgba(out)
    return values


def stage_files(folder,toc,global_toc):
    for item in (global_toc,toc):
        for suffix in (".utoc",".ucas"):
            src=item.with_suffix(suffix); dest=folder/src.name
            try: os.link(src,dest)
            except OSError: shutil.copyfile(src,dest)


def check_shader_cook(log):
    text=log.read_text(encoding="utf-8",errors="replace")
    if "BUILD SUCCESSFUL" not in text or "ExitCode=0" not in text:
        raise ValueError("The requested cook did not finish")
    rejected=("Failed to compile Material","Default Material will be used in game",
              "Shader is using too many Samplers","ShaderCompileWorker crashed")
    for needle in rejected:
        if needle.lower() in text.lower():
            raise ValueError("The cook substituted or failed a shader: "+needle)
    compiled=(ART/"editor-site-ground.json")
    if log.stat().st_mtime<compiled.stat().st_mtime:
        raise ValueError("The cook log predates the last material apply")
    return {"log":str(log),"sha256":sha(log),"shader_fallback_diagnostics":0,
            "editor_shader_sha256":json.loads(compiled.read_text())["shader_sha256"]}


def native(proof,toc,global_toc,cook_log):
    proof["cook"]=check_shader_cook(cook_log)
    with tempfile.TemporaryDirectory(dir=ART) as temp:
        root=Path(temp); current=root/"new"; current.mkdir(); prior=root/"prior"; prior.mkdir()
        stage_files(current,toc,global_toc);stage_files(prior,PRIOR,global_toc)
        old={k:read_texture(prior,k,[0])[0] for k in ("road","biome")}
        fresh={k:read_texture(current,k,[0,2,4,9 if k=="grade" else 10]) for k in NAMES}
    expected={"road":rgba(ROAD),"biome":rgba(ART/"biome-color.png"),"grade":rgba(ART/"site-ground.png")}
    if not np.array_equal(old["biome"],rgba(PREVIOUS)) or not np.array_equal(old["road"],fresh["road"][0]):
        raise ValueError("The sealed .9 biome differs from .8 or the .10 cook changed .9 driving data")
    allowed=np.asarray(Image.open(ART/"authorized-area.png"))>0
    if not np.array_equal(old["biome"][~allowed],fresh["biome"][0][~allowed]):
        raise ValueError("The cooked landscape changed the .9 surface outside the exact surveyed grading footprint")
    if not np.array_equal(old["biome"][:,:,3],fresh["biome"][0][:,:,3]): raise ValueError("Wet coverage drift")
    proof["cooked_mips"]={}
    for k,levels in fresh.items():
        proof["cooked_mips"][k]={}
        for lod,field in levels.items():
            n=len(expected[k])>>lod
            match=np.stack([np.asarray(Image.fromarray(expected[k][:,:,i]).resize((n,n),Image.Resampling.BOX))
                            for i in range(4)],axis=-1)
            error=int(np.max(np.abs(field.astype(int)-match.astype(int))))
            if error>(0 if lod==0 else 3): raise ValueError(f"{k} mip {lod} byte error {error}")
            proof["cooked_mips"][k][lod]=dict(max_byte_error=error,sha256=hashlib.sha256(field.tobytes()).hexdigest())
    shader=shader_receipt(toc,DEFAULT_OODLE); before=shader_receipt(PRIOR,DEFAULT_OODLE)
    for k in ("master","landscape_world"):
        if set(before[k])==set(shader[k]): raise ValueError("Stale .9 shader in "+k)
        if len(shader[k])<len(before[k]) or max(v.get("PS",0) for v in shader[k].values())<max(v.get("PS",0) for v in before[k].values()):
            raise ValueError("The .10 native cook lost a landscape pixel-shader permutation: "+k)
    container=load_container(toc)
    item=next(v for k,v in container.files.items() if k.endswith("GrassPilot/Playable/M_PWRPilot.uasset"))
    mat=read_chunk(container,container.chunks[item],oodle_roots=[DEFAULT_OODLE])
    names=load_name_batch(mat,struct.unpack_from("<i",mat,48)[0])[0]
    for name in NAMES.values():
        if FOLDER+name not in names: raise ValueError("Native landscape missing "+name)
    for param in (b"PWRSiteGround",b"PWRRoadNetwork",b"SandD",b"SandN",b"RockD"):
        if param not in mat: raise ValueError("Missing runtime material input "+str(param))
    proof.update(sm6=shader,container_sha256={s:sha(toc.with_suffix(s)) for s in (".utoc",".ucas")},
                 prior_09_container_sha256={s:sha(PRIOR.with_suffix(s)) for s in (".utoc",".ucas")},
                 exact_road_rgba=2048**2,exact_biome_rgba=1024**2,exact_grade_rgba=512**2,
                 compiled_textures=list(NAMES.values()))
    checks=road_checks(fresh["road"][0],json.loads(GEOMETRY.read_text()),json.loads(GATES.read_text()))
    proof["road_checks"]=checks
    Image.fromarray(fresh["grade"][0]).save(ART/"native-site-ground.png")
    Image.fromarray(fresh["biome"][0]).save(ART/"native-biome-color.png")


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--toc",type=Path)
    parser.add_argument("--global-toc",type=Path)
    parser.add_argument("--cook-log",type=Path)
    args=parser.parse_args()
    result=validate_sources()
    if args.toc:
        if not args.cook_log: parser.error("--cook-log is required for native readback")
        native(result,args.toc.resolve(),args.global_toc.resolve(),args.cook_log.resolve())
    path=ART/("cooked-site-ground-readback.json" if args.toc else "site-ground-source-check.json")
    path.write_text(json.dumps(result,indent=2)+"\n")
    print(path,result["exterior_identical_rgba"],result.get("container_sha256"))
