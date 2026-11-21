"""Verify UE5.5 saved HISM matrices in the stock cook, game-layout copy and shipped PWR container."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import sys

import numpy as np

ROOT=Path(__file__).resolve().parents[4]
sys.path[:0]=[str(ROOT/"tools/level"),str(ROOT/"tools/iostore")]
from iostore import load_container, read_chunk
from verify_render_only_hism_cook import identity_ancestors, matrices, number, package

OUT=ROOT/"out/pwr/landscape-distance"
ACTOR="PWR_DistanceColonies"
GLOBAL=ROOT/"out/pwr/world-art/foliage-r2/cooked-proof"
BASE=ROOT/"out/pwr/base-polish/saturday.7/map-input/pakchunk997-MJOLNIRMAP-PWR_P.utoc"
READER=ROOT/"target/release/examples/hism_readback.exe"
GAME="Meteorite-2607-CU3.usmap"
STOCK="UE-5.5-stock.usmap"


def sha(data):
    return hashlib.sha256(data).hexdigest()


def world_from_container(toc,dest):
    c=load_container(toc)
    name="Meteorite/Content/Levels/Halo1/Solo/PWR/PWR.umap"
    dest.write_bytes(read_chunk(c,c.chunks[c.files[name]]))
    return dest


def decode(path,schema):
    global_paks=GLOBAL/("stock-paks" if schema==STOCK else "world-paks")
    result=subprocess.run([str(READER),str(global_paks),str(ROOT/"defs/ue"/schema),str(path)],
                          capture_output=True,check=True)
    return json.loads(result.stdout)


def native_matrices(data,row,count):
    # The package decoder supplies the property block boundary so bytes resembling
    # a matrix in tagged properties or unrelated exports cannot be accepted.
    header=struct.unpack_from("<13I",data)
    pos,n=struct.unpack_from("<QQ",data,header[8]+72*row["export"])
    end=header[1]+pos+n
    start=end-row["native_tail_bytes"]
    matches=[]
    marker=struct.pack("<II",128,count)
    for i in range(start,min(end-7,start+249)):
        if data[i:i+8]!=marker or i+8+128*count>end:
            continue
        m=np.frombuffer(data,dtype="<f8",count=16*count,offset=i+8).reshape(count,4,4)
        if np.isfinite(m).all() and np.all(m[:,:,3]==[0.,0.,0.,1.]):
            matches.append(m)
    if len(matches)!=1:
        raise ValueError(f"Unresolved native affine stream in {row['outer']}/{row['name']} ({count})")
    return matches[0]


def inventory(doc,data):
    result={}
    for row in doc["exports"]:
        if row["class"]!="HierarchicalInstancedStaticMeshComponent" or row["outer"]==ACTOR:
            continue
        p=row["properties"]
        key=f"{row['outer']}/{row['name']}"
        if key in result:
            raise ValueError("Duplicate original component "+key)
        count=int(number(p.get("NumBuiltInstances")))
        transform_bytes=native_matrices(data,row,count).tobytes()
        result[key]=dict(mesh=package(row,"StaticMesh"),count=count,
                         matrices_sha256=sha(transform_bytes),
                         cull=[int(number(p.get(k))) for k in ("InstanceStartCullDistance","InstanceEndCullDistance")])
    return result


def inspect(path,schema,spec,original,expected_package):
    doc=decode(path,schema)
    if doc["package"]!=expected_package:
        raise ValueError(f"Expected {expected_package}, got {doc['package']}")
    data=path.read_bytes()
    if inventory(doc,data)!=original:
        raise ValueError("Original HISM assets, transforms, culling, population or ownership changed")
    rows=[r for r in doc["exports"] if r["outer"]==ACTOR and r["class"]=="HierarchicalInstancedStaticMeshComponent"]
    if len(rows)!=len(spec["groups"]):
        raise ValueError("Wrong number of new components")
    lookup={row["name"]:row for row in rows}
    by_id={r["export"]:r for r in doc["exports"]}
    proof={}
    for i,g in enumerate(spec["groups"],1):
        row=lookup[f"MJFol_{i}_1_0"]
        p=row["properties"]
        count=int(number(p.get("NumBuiltInstances")))
        cull=[int(number(p.get(k))) for k in ("InstanceStartCullDistance","InstanceEndCullDistance")]
        if package(row,"StaticMesh")!=g["mesh"].split(".")[0] or count!=g["count"] or cull!=g["cull"]:
            raise ValueError(f"Wrong mesh, instance count or distance for {g['rule']}")
        if any(k.startswith("OverrideMaterials[") for k in p) or p.get("BodyInstance.CollisionProfileName")!="NoCollision":
            raise ValueError(f"Collision or material changed on {g['rule']}")
        identity_ancestors(row,by_id)
        actual=native_matrices(data,row,count)
        sidecar=OUT/"vegetation"/(spec["file"]+f".xf{i}")
        if sha(sidecar.read_bytes())!=spec["exact_sidecars"][i-1]:
            raise ValueError("Stale source transform seal")
        expected=matrices(sidecar)
        def by_position(m):
            return m[np.lexsort(tuple(m[:,3,j] for j in (2,1,0)))]
        delta=abs(by_position(actual)-by_position(expected))
        pos=float(delta[:,3,:3].max()); basis=float(delta[:,:3,:3].max())
        if pos>.01 or basis>1e-5:
            raise ValueError(f"{g['rule']} cook drifted by {pos} cm, {basis} basis")
        proof[g["rule"]]=dict(mesh=g["mesh"],count=count,cull_cm=cull,position_error_cm=pos,basis_error=basis,
                              native_transform_sha256=sha(actual.tobytes()))
    return dict(source=str(path),source_sha256=sha(data),package=doc["package"],components=proof)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage",choices=("baseline","stock","layout","final","all"))
    parser.add_argument("--world-container",type=Path,
                        default=OUT/"native/world-final/pakchunk997-MJOLNIRMAP-PWR_P.utoc")
    args=parser.parse_args()
    out=OUT/"vegetation/cooked-proof";out.mkdir(parents=True,exist_ok=True)
    expected="/Game/Levels/Halo1/Solo/PWR/PWR"
    baseline_path=world_from_container(BASE,out/"baseline.umap")
    baseline=decode(baseline_path,GAME)
    if baseline["package"]!=expected or any(r["outer"]==ACTOR for r in baseline["exports"]):
        raise ValueError("Unexpected release baseline")
    original=inventory(baseline,baseline_path.read_bytes())
    if not any(k.startswith("PWR_FieldUnderstory/") for k in original):
        raise ValueError("Baseline shrub actor missing")
    if args.stage=="baseline":
        print("Baseline HISM ownership verified:",len(original),sum(r["count"] for r in original.values()))
        return
    native=OUT/"native"
    spec=json.loads((OUT/"vegetation/hism.json").read_text())
    stages=("stock","layout","final") if args.stage=="all" else [args.stage]
    for stage in stages:
        if stage=="final":
            utoc=args.world_container
            path=world_from_container(utoc,out/"packaged.umap")
        else:
            path=native/("LPE.stock.umap" if stage=="stock" else "LPE.umap")
        report=inspect(path,STOCK if stage=="stock" else GAME,spec,original,
                       expected if stage=="final" else "/Game/Levels/Halo1/Solo/LPE/LPE")
        report.update(preserved_previous_hisms=len(original),previous_affine_streams_identical=True,
                      preserved_instance_count=sum(r["count"] for r in original.values()))
        if stage=="final":
            report.update(utoc_sha256=sha(utoc.read_bytes()),ucas_sha256=sha(utoc.with_suffix(".ucas").read_bytes()))
        (out/(stage+".json")).write_text(json.dumps(report,indent=2))
        print(stage,"verified",sum(r["count"] for r in report["components"].values()),"matrices")


if __name__=="__main__":
    main()
