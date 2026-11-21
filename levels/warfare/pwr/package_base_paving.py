# /// script
# dependencies = ["numpy", "shapely>=2.1,<3"]
# ///
"""Package reviewed paving using the native mesh-clone writer; never install.

    uv run levels/warfare/pwr/package_base_paving.py

Exports and decodes the produced container, using the exact float32 writer
transform rather than its rounded console display. Rejects >1mm source or
terrain alignment error, incorrect native materials/UVs, or protected overlap.
"""
from __future__ import annotations
import argparse
import json
import re
import shutil
import struct
import subprocess
from pathlib import Path

import numpy as np
from shapely.geometry import Polygon
from shapely.ops import unary_union
import base_paving as paving
from heightfield import load_heightfield,sha256

ROOT=paving.ROOT
STEM="pakchunk961-MJOLNIRPWRPAVING_P"
SITE_LEAF={"red_home":"SM_PWR_BasePaving_Red","blue_home":"SM_PWR_BasePaving_Blue",
           "citadel_plateau":"SM_PWR_BasePaving_Citadel"}


def run(args,log):
    result=subprocess.run([str(x) for x in args],cwd=ROOT,capture_output=True,text=True)
    log.write_text(result.stdout+result.stderr,encoding="utf-8")
    if result.returncode or "MISMATCH" in result.stdout+result.stderr:
        raise RuntimeError(str(log)+": "+(result.stdout+result.stderr)[-2500:])
    return result.stdout+result.stderr


def write_gltf(parts,source,out,leaf,site):
    data=[];views=[];accessors=[];primitives=[];offset=0
    original=[];original_triangles=[];source_uv=[];vertex_offset=0
    def add(array,kind,component):
        nonlocal offset
        index=len(views);views.append({"buffer":0,"byteOffset":offset,"byteLength":array.nbytes})
        offset+=array.nbytes;data.append(array)
        accessors.append({"bufferView":index,"componentType":component,
                          "count":array.size if kind=="SCALAR" else len(array),"type":kind})
        return index
    for part in parts:
        src=np.load(source/part["mesh_file"]);v=src["vertices_m"];t=src["triangles"]
        normals=np.cross(v[t[:,1]]-v[t[:,0]],v[t[:,2]]-v[t[:,0]])
        normals/=np.linalg.norm(normals,axis=1)[:,None]
        # Source uses unshared triangle vertices, so each lies on exactly one
        # terrain plane. A4m UV unit preserves metre-scale detail under actor
        # normalization; UVs are not scaled with the donor mesh afterwards.
        n=np.repeat(normals,3,axis=0)
        position=np.c_[v[:,0],v[:,2],-v[:,1]].astype("<f4")
        normal=np.c_[n[:,0],n[:,2],-n[:,1]].astype("<f4")
        uv=((v[:,:2]-np.asarray(site["position_m"][:2]))/4).astype("<f4")
        a=add(position,"VEC3",5126);b=add(normal,"VEC3",5126);c=add(uv,"VEC2",5126);d=add(t.astype("<u4"),"SCALAR",5125)
        accessors[a].update(min=position.min(0).tolist(),max=position.max(0).tolist())
        primitives.append({"attributes":{"POSITION":a,"NORMAL":b,"TEXCOORD_0":c},"indices":d,"material":part["material_slot"]})
        original.append(v);source_uv.append(uv);original_triangles.append(t+vertex_offset);vertex_offset+=len(v)
    (out/(leaf+".bin")).write_bytes(b"".join(a.tobytes() for a in data))
    doc={"asset":{"version":"2.0","generator":"PWR exact-triangle render-only paving"},
         "buffers":[{"uri":leaf+".bin","byteLength":offset}],"bufferViews":views,"accessors":accessors,
         "materials":[{"name":"PavingPanels"},{"name":"PavingJoints"}],
         "meshes":[{"name":leaf,"primitives":primitives}],"nodes":[{"mesh":0}],"scenes":[{"nodes":[0]}],"scene":0}
    path=out/(leaf+".gltf");path.write_text(json.dumps(doc,indent=2)+"\n")
    v=np.concatenate(original);t=np.concatenate(original_triangles);uv=np.concatenate(source_uv)
    # Mirror mesh_rewrite's float32 arithmetic exactly, including100cm
    # conversion and the reciprocal round-off. The log rounds centre to0.1cm.
    world=(v.astype(np.float32)*np.array([100,-100,100],dtype=np.float32)).astype(np.float32)
    low,high=world.min(0),world.max(0);center=((low+high)*np.float32(.5)).astype(np.float32)
    half=np.float32(np.max((high-low)*np.float32(.5)));fit=np.float32(50)/half
    scale=np.float32(1)/fit
    return path,v,t,uv,center,float(scale)


def read_glb(path):
    raw=path.read_bytes();length=struct.unpack_from("<I",raw,12)[0]
    doc=json.loads(raw[20:20+length]);data=raw[28+length:]
    def read(index):
        a=doc["accessors"][index];v=doc["bufferViews"][a["bufferView"]]
        dtype=np.dtype({5126:"<f4",5125:"<u4",5123:"<u2",5121:"u1"}[a["componentType"]])
        columns={"SCALAR":1,"VEC2":2,"VEC3":3,"VEC4":4}[a["type"]]
        return np.ndarray((a["count"],columns),dtype=dtype,buffer=data,
                          offset=v.get("byteOffset",0)+a.get("byteOffset",0),
                          strides=(v.get("byteStride",columns*dtype.itemsize),dtype.itemsize)).copy()
    mesh=doc["meshes"][0];first=mesh["primitives"][0]
    positions=read(first["attributes"]["POSITION"]).astype(float)
    uv=read(first["attributes"]["TEXCOORD_0"]).astype(float)
    triangles=np.concatenate([read(p["indices"]).reshape(-1,3) for p in mesh["primitives"]])
    # Exporter uses one shared vertex accessor and per-section index arrays.
    if any(p["attributes"]["POSITION"]!=first["attributes"]["POSITION"] for p in mesh["primitives"]):
        raise ValueError("Unexpected native mesh-export vertex layout")
    return positions[:,[0,2,1]]*100,uv,triangles,doc


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source",type=Path,default=ROOT/"out/pwr/visual-v5/base-paving")
    p.add_argument("--paks",type=Path,default=Path("C:/Program Files (x86)/Steam/steamapps/common/Halo Campaign Evolved/Meteorite/Content/Paks"))
    p.add_argument("--master",type=Path,default=ROOT/"levels/warfare/pwr/terrain/runtime-v5/runtime-master.json")
    p.add_argument("--geometry",type=Path,default=ROOT/"levels/warfare/pwr/terrain/final-v5/terrain.geometry.json")
    args=p.parse_args();source=args.source.resolve();out=source/"native";out.mkdir(parents=True,exist_ok=True)
    receipt=json.loads((source/"receipt.json").read_text());field=load_heightfield(args.master)
    geometry=json.loads(args.geometry.read_text());sites=[s for s in geometry["sites"] if s["id"] in SITE_LEAF]
    if receipt["master_sha256"]!=field.manifest_sha256 or receipt["geometry_sha256"]!=sha256(args.geometry):
        raise ValueError("Paving source refers to a different terrain/geometry")
    for file,digest in receipt["files"].items():
        if sha256(source/file)!=digest:raise ValueError("Reviewed paving geometry changed: "+file)
    cli=ROOT/"target/release/mjolnir.exe";rewriter=ROOT/"target/release/examples/mesh_rewrite.exe"
    package_add=ROOT/"target/release/examples/package_add.exe"
    for slot,material in enumerate(receipt["materials"]):
        run([cli,"ue","get","--paks",args.paks,"--package",material.split(".")[0]],out/f"material-{slot}.log")
    packages=[];actors=[];sources=[]
    for site in sites:
        name=site["id"];leaf=SITE_LEAF[name];package="/Game/MJOLNIR/Maps/PWR/"+leaf
        parts=[x for x in receipt["parts"] if x["site"]==name]
        gltf,v,t,uv,center,scale=write_gltf(parts,source,out,leaf,site)
        uasset=out/(leaf+".uasset")
        command=[rewriter,args.paks,"basicshapes/cylinder",gltf,uasset,"--offset","0,0,0","--rename",package,
                 "--material","Panels="+receipt["materials"][0].split(".")[0]+"=PavingPanels|*",
                 "--material","Joints="+receipt["materials"][1].split(".")[0]+"=PavingJoints","--asset-imports","--selftest"]
        log=run(command,out/(leaf+".rewrite.log"))
        material_check="materials read back: [Panels->"+receipt["materials"][0].rsplit(".",1)[-1]+", Joints->"+receipt["materials"][1].rsplit(".",1)[-1]+"] -- MATCHES"
        if material_check not in log:raise ValueError("Native material imports/slot order were not verified")
        match=re.search(r"SPAWN: location \(([-\d.]+), ([-\d.]+), ([-\d.]+)\) cm, uniform scale ([\d.]+)",log)
        if not match:raise ValueError("Missing native writer transform")
        shown=np.array([float(x) for x in match.groups()])
        if np.max(abs(shown[:3]-center))>.051 or abs(shown[3]-scale)>.000051:raise ValueError("Normalization transform mismatch")
        sphere=re.search(r"normalised bounding sphere ([\d.]+)",log)
        if not sphere or float(sphere[1])>70.7:raise ValueError("Paving exceeds donor bounding sphere")
        actors.append({"id":"pwr_paving_"+name,"mesh":package+"."+leaf,"pos":center.astype(float).tolist(),
                       "rot":[0,0,0],"scale":[scale]*3,"static":True,"cast_shadow":False,
                       "materials":[{"parent":m} for m in receipt["materials"]]})
        packages.extend(["--package",package+"="+str(uasset)])
        sources.append((site,leaf,v,t,uv,center.astype(float),scale))
    run([package_add,args.paks,out,"--name",STEM,*packages],out/"package.log")
    shutil.copy2(args.paks/"pakchunk115-Windows.pak",out/(STEM+".pak"))
    audit=out/"audit-paks";audit.mkdir(exist_ok=True)
    for suffix in (".utoc",".ucas"):
        shutil.copy2(args.paks/("global"+suffix),audit/("global"+suffix))
        shutil.copy2(out/(STEM+suffix),audit/(STEM+suffix))
    roads,buildings=paving.obstacles(geometry,sites,road_margin=0,building_margin=0)
    checks=[]
    for site,leaf,original,tri,source_uv,center,scale in sources:
        glb=out/(leaf+".readback.glb")
        run([cli,"mesh","export","--paks",audit,"--asset",leaf,"--out",glb],out/(leaf+".readback.log"))
        local,uv,t,doc=read_glb(glb);world=local*scale+center;authored=world*np.array([.01,-.01,.01])
        if authored.shape!=original.shape or t.shape!=tri.shape:raise ValueError("Native geometry counts changed")
        vertex_error=float(np.max(np.linalg.norm(authored-original,axis=1)))
        uv_error=float(np.max(abs(uv-source_uv)))
        centerpoints=authored[t].mean(1)
        terrain_error=float(np.max(abs(centerpoints[:,2]-field.sample(centerpoints[:,0],centerpoints[:,1])-receipt["lift_m"])))
        if vertex_error>.001 or terrain_error>.001 or uv_error>1e-6:raise ValueError("Native readback exceeded1mm/UV gate")
        footprints=[Polygon(authored[face,:2]) for face in t]
        actual=unary_union([q for q in footprints if q.area>1e-12])
        road_overlap=actual.intersection(roads).area;structure_overlap=actual.intersection(buildings).area
        if road_overlap>1e-6 or structure_overlap>1e-6:
            raise ValueError(f"Native float mesh entered a protected footprint at {site['id']}: road={road_overlap}m2, structure={structure_overlap}m2")
        native_names=[m["name"] for m in doc.get("materials",[])]
        if native_names!=["Panels","Joints"]:raise ValueError("Native material slots changed")
        checks.append({"site":site["id"],"vertices":len(authored),"triangles":len(t),
                       "max_vertex_error_m":vertex_error,"max_face_terrain_alignment_error_m":terrain_error,
                       "uv_max_abs_error":uv_error,"road_overlap_m2":road_overlap,"structure_overlap_m2":structure_overlap,
                       "native_material_slots":native_names,"native_materials":receipt["materials"],"readback_sha256":sha256(glb)})
    fragment={"schema":"mjolnir-runtime-decor-v1","render_only":True,"decor":actors}
    (out/"runtime_decor.json").write_text(json.dumps(fragment,indent=2)+"\n")
    result={"schema":"pwr-native-base-paving-v1","container_stem":str(out/STEM),"runtime_decor":str(out/"runtime_decor.json"),
            "source_geometry_receipt_sha256":sha256(source/"receipt.json"),"master_sha256":field.manifest_sha256,
            "generator_sha256":sha256(Path(__file__)),"uv_scale":"One UV unit per 4 authoring metres; full-precision native UV0. Native material micro-detail tiling is unchanged.",
            "collision":"No Blam hulls. Native donor BodySetup is inert: existing decor loader explicitly calls SetCollisionEnabled(0).",
            "render_only":True,"installed":False,"readback_checks":checks,
            "files":{suffix:{"path":str(out/(STEM+suffix)),"sha256":sha256(out/(STEM+suffix))} for suffix in (".utoc",".ucas",".pak")}}
    (out/"package.receipt.json").write_text(json.dumps(result,indent=2)+"\n")
    print(json.dumps({"container":str(out/STEM),"actors":len(actors),"checks":checks},indent=2))


if __name__=="__main__":main()
