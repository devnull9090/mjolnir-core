"""Offline v4 geometry/placement checks and deterministic under-rock clearing."""
import argparse
import json
from pathlib import Path
import struct
import numpy as np
from PIL import Image, ImageDraw
import build_candidate as v4

def audit():
    OUT=v4.OUT
    f=v4.field()
    runtime=v4.pcg_foliage.load(OUT/"apron/runtime_decor.json")["decor"][0]
    source=np.load(OUT/"apron/apron.source.npz")
    receipt=v4.pcg_foliage.load(OUT/"apron/receipt.json")
    if receipt["runtime_master_sha256"]!=f.manifest_sha256:raise ValueError("Apron belongs to another runtime master")
    seam=source["vertices_m"][:4032]
    if not np.array_equal(seam[:,2],f.sample(seam[:,0],seam[:,1])):raise ValueError("Apron seam does not match current terrain")
    expected=source["vertices_m"]*np.array([100,-100,100])
    readback=v4.b30_collision.glb_positions(OUT/"apron/roundtrip.glb")
    actual=readback*np.asarray(runtime["scale"])+runtime["pos"]
    if len(actual)!=len(expected): raise ValueError("Apron roundtrip vertex count changed")
    error=np.linalg.norm(actual-expected,axis=1)/100
    assert error.max()<.005, error.max()
    assert error[:4032].max()<.005,error[:4032].max()
    triangles=source["triangles"]
    edges=np.sort(np.concatenate([triangles[:,[0,1]],triangles[:,[1,2]],triangles[:,[2,0]]]),axis=1)
    unique,counts=np.unique(edges,axis=0,return_counts=True)
    assert counts.max()==2
    boundary=unique[counts==1]
    # Exactly two boundary loops:4032inner and252outer edges, no radial gaps.
    assert len(boundary)==4032+252
    assert not np.any((boundary[:,0]<4032)!=(boundary[:,1]<4032))
    apron_receipt={"native_roundtrip_vertices":len(actual),"native_max_position_error_m":float(error.max()),
                   "native_max_seam_error_m":float(error[:4032].max()),"manifold_edge_max_incidence":int(counts.max()),
                   "open_edges":len(boundary),"expected_inner_plus_outer_edges":4032+252,
                   "source_hash_unchanged":f.manifest_sha256==v4.EXPECTED_MASTER}
    v4.dump(OUT/"apron/roundtrip.verification.json",apron_receipt)

    documents=[v4.pcg_foliage.load(OUT/p) for p in ("temperate-rocks.authored-decor.json",
                "outcrops.authored-decor.json","shore/shore.authored-decor.json")]
    decor=[d for doc in documents for d in doc["decor"]]
    assert len({d["id"] for d in decor})==len(decor), "Duplicate dressing IDs"
    assert 1<=len(decor)<=1000, "Review total dressing budget"
    v4.dump(OUT/"rocks-and-outcrops.authored-decor.json",{"schema_version":1,"coordinates":"unreal_centimetres",
             "decor":decor,"background_trees":[],"visual_v4_provenance":{"frozen_runtime_master_sha256":f.manifest_sha256,
             "sources":[{"path":str(OUT/p),"sha256":v4.digest(OUT/p)} for p in
                       ("temperate-rocks.authored-decor.json","outcrops.authored-decor.json","shore/shore.authored-decor.json")]}})

    # Preserve original actual-PCG transforms byte-for-byte for every retained
    # grass instance. This is a deterministic geometry exclusion, not re-scatter.
    grass_source=v4.SOURCE_GRASS
    spec,groups=v4.pcg_foliage.read_mjf_groups(grass_source)
    grass_out=OUT/"grass";grass_out.mkdir(parents=True,exist_ok=True)
    kept_groups=[];group_reports=[];total_removed=0
    for index,(group,payload,sidecars,n) in enumerate(groups,1):
        if "xf" not in sidecars: raise ValueError("Expected exact PCG grass transforms")
        transforms=np.frombuffer(sidecars["xf"],dtype="<f4").reshape(n,10)
        xyz=transforms[:,:3].astype(float)
        keep=np.ones(n,dtype=bool)
        for item in decor:
            leaf=item["mesh"].split(".")[-1]
            cache=next((root/(leaf+".json") for root in (OUT/"hulls",v4.ROCK_HULLS) if (root/(leaf+".json")).is_file()),None)
            if cache is None:raise FileNotFoundError("Missing verified hull: "+leaf)
            hull=v4.pcg_foliage.load(cache)
            local=np.asarray(hull["points"])
            rot=v4.b30_collision.rotator_matrix(*item.get("rot",[0,0,0]))
            world=local*np.asarray(item["scale"])@rot+item["pos"]
            lo,hi=world.min(0)-65,world.max(0)+65
            ids=np.flatnonzero(keep & np.all(xyz>=lo,axis=1)&np.all(xyz<=hi,axis=1))
            if not len(ids):continue
            faces=np.asarray(hull["faces"])
            a,b,c=world[faces[:,0]],world[faces[:,1]],world[faces[:,2]]
            normals=np.cross(b-a,c-a);length=np.linalg.norm(normals,axis=1)
            valid=length>1e-8;normals=normals[valid]/length[valid,None];a=a[valid]
            # Hull winding is outward in UE frame. A65cm margin protects blades
            # beyond their root;0.15m height tests the actual short-grass canopy.
            points=xyz[ids]+[0,0,15]
            inside=np.all(points@normals.T-np.sum(a*normals,axis=1)<=65,axis=1)
            keep[ids[inside]]=False
        count=int(keep.sum());total_removed+=n-count
        records=np.frombuffer(payload[4:],dtype=np.dtype((np.void,19)))
        newpayload=struct.pack("<I",count)+records[keep].tobytes()
        newside={}
        for suffix,data in sidecars.items():
            stride=40 if suffix=="xf" else 16
            newside[suffix]=np.frombuffer(data,dtype=np.dtype((np.void,stride)))[keep].tobytes()
            assert len(newside[suffix])==count*stride
        kept_groups.append((group,newpayload,newside,count))
        group_reports.append({"group":index,"input":n,"retained":count,"removed":n-count})
    binary=grass_out/"foliage.bin"
    binary.write_bytes(b"MJF3"+struct.pack("<II",3,len(kept_groups))+b"".join(r[1] for r in kept_groups))
    for i,(_,_,sidecars,_) in enumerate(kept_groups,1):
        for suffix,data in sidecars.items():Path(str(binary)+"."+suffix+str(i)).write_bytes(data)
    v4.dump(grass_out/"foliage.json",{"file":"foliage.bin","groups":[r[0] for r in kept_groups]})
    v4.pcg_foliage.read_mjf_groups(grass_out/"foliage.json")
    v4.dump(grass_out/"exclusion.receipt.json",{"source":"actual PCG unchanged transform sequence",
        "source_spec_sha256":v4.digest(grass_source),"source_decor_sha256":v4.digest(OUT/"rocks-and-outcrops.authored-decor.json"),
        "deterministic_exclusion":"native hulls expanded65cm,grasssample15cm above root",
        "retained_transforms_byte_exact":True,"removed":total_removed,"groups":group_reports,
        "retained":sum(r[3] for r in kept_groups)})

    # A compact placement proof, not a claim of an engine-rendered beauty image.
    z=f.heights_m;dy,dx=np.gradient(z,*f.spacing_m[::-1])
    light=np.clip((-.55*dx+.45*dy+1.2)/np.sqrt(1+dx*dx+dy*dy),.08,1.5)
    base=np.stack([.24+.10*np.clip((z-70)/250,0,1),.30+.04*np.clip((z-70)/250,0,1),.18+.10*np.clip((z-70)/250,0,1)],axis=2)
    water=f.masks["water"]>.5;base[water]=[.03,.23,.30]
    road=f.masks["road"]>.5;base[road]=[.42,.32,.22]
    rgb=(np.clip(base*(.55+.6*light[:,:,None]),0,1)*255).astype(np.uint8)
    im=Image.fromarray(np.flipud(rgb));draw=ImageDraw.Draw(im)
    colors={"macro":"#ff7557","cliff":"#ffbe58","shelf":"#f1e4a0","shore":"#6fe5ed"}
    for item in decor:
        if not item["id"].startswith("pcg_v4_"):continue
        x,y=item["pos"][0]/100,-item["pos"][1]/100
        px=(x+1000)/2000*1008;py=(1000-y)/2000*1008
        kind=item["id"].split("_")[2];radius=3 if kind=="shore" else 5
        draw.ellipse((px-radius,py-radius,px+radius,py+radius),fill=colors[kind],outline="black")
    draw.rectangle((8,8,570,40),fill="black")
    draw.text((16,18),"PLACEMENT PROOF: red macro / gold cliffs / pale shelves / cyan shore",fill="white")
    im.save(OUT/"placement-proof.png")
    print(json.dumps({"apron":apron_receipt,"decor":len(decor),"grass_removed":total_removed,
                      "grass_retained":sum(r[3] for r in kept_groups)},indent=2))


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    v4.add_source_arguments(parser);args=parser.parse_args();args.command="audit";v4.configure(args);audit()
