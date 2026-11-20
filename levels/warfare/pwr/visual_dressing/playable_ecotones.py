"""Add connected low brush and dry-bank rush beds to the existing PWR ecology cook."""
import argparse
import json
from pathlib import Path
import shutil
import struct
import sys

import numpy as np
from PIL import Image
from scipy.ndimage import distance_transform_edt, gaussian_filter, map_coordinates

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "tools/level"))
import landscape_grass_pilot as grass
import pcg_foliage as pcg
from foliage_bake import PAKS, mesh_info

ORIGINAL = ROOT / "out/pwr/world-art/foliage"
PALETTE = Path(__file__).with_name("playable-ecotone-palette.json")
SEED = 34841


def smooth(a,b,value):
    t=np.clip((value-a)/(b-a),0,1)
    return t*t*(3-2*t)


def mottling(rng,shape,spacing,m):
    n=gaussian_filter(rng.standard_normal(shape),m/spacing,mode="reflect")
    return np.clip(.5+n/(4*n.std()),0,1)


def prepare(out,original):
    first=pcg.load(original/"pilot.json")
    grass.validate_config(first,original)
    land=next(Path(r["path"]).parent for r in first["sources"] if Path(r["path"]).name=="landscape.json")
    field,spec,scenery,sources,x,y,allowed,guard=grass.ground_support(land,None,include_dry_banks=True)
    step=spec["scale"][0]/100
    sx,sy=x[0,0],y[0,0]
    rng=np.random.default_rng(SEED)
    size=len(x)
    trees=np.array([r["position"][:2] for r in pcg.load(scenery/"trees/trees.selected.json")["instances"]])
    canopy=np.zeros((size,size),float)
    np.add.at(canopy,(np.rint((sy-trees[:,1])/step).astype(int),np.rint((trees[:,0]-sx)/step).astype(int)),1.)
    # Smooth measured crowns into stands before measuring their signed edge distance.
    crown_cover=gaussian_filter(canopy,16/step)*160/step**2
    stand=crown_cover>.17
    fringe=(distance_transform_edt(~stand)-distance_transform_edt(stand))*step
    wet=field.sample_mask("water",x,y)
    shore_gap=distance_transform_edt(wet<=.03)*step
    road_gap=distance_transform_edt(field.sample_mask("road",x,y)==0)*step
    base_gap=distance_transform_edt(field.sample_mask("bases",x,y)==0)*step
    geometry=pcg.load(ROOT/"levels/warfare/pwr/terrain/final-v5/terrain.geometry.json")
    bridge_open=np.ones(x.shape,bool)
    for bridge in geometry["crossings"]:
        # Keep each full deck, the view off the deck and both end approaches clear.
        (ax,ay),(bx,by)=bridge["alignment_m"]
        ux,uy=bx-ax,by-ay
        t=np.clip(((x-ax)*ux+(y-ay)*uy)/(ux*ux+uy*uy),-.12,1.12)
        bridge_open &= (x-ax-t*ux)**2+(y-ay-t*uy)**2 > (bridge["road_width_m"]*.5+10)**2
    allowed &= (road_gap>=7)&(base_gap>=10)&bridge_open
    allowed &= (np.abs(x)<=995)&(np.abs(y)<=995)
    broad=mottling(rng,x.shape,step,51.)
    medium=mottling(rng,x.shape,step,19.)
    detail=mottling(rng,x.shape,step,5.)
    # Colonies grow outward in fingers with scalloped edges and grazed gaps.
    # Only one bank of a bend may carry a thick reed bed.
    reach=16 + 96*broad + 30*(medium-.5)
    front=smooth(-32.,4.,fringe)*(1-smooth(reach*.38,reach,fringe))
    scrub=front*smooth(.32,.71,.60*medium+.40*broad)*(.45+.55*detail)
    pine=scrub*smooth(-10,7,fringe)*(1-smooth(17,42,fringe))*smooth(.42,.72,medium)
    rush=(1-smooth(9.,27.,shore_gap))*smooth(.21,.58,.66*broad+.34*medium)*(.58+.42*detail)
    bank=(1-smooth(28,55,shore_gap))*smooth(9,21,shore_gap)*smooth(.33,.70,medium+.12*detail)
    dry=(1-smooth(60,105,fringe))*smooth(17,41,fringe)*smooth(.51,.78,broad+.08*detail)
    fields={"pine":pine*.31,"scrub":scrub*.61,"dry":dry*.32,
            "willow":bank*.52,"rush":rush*.92}
    # The neutral RGB companion is an artist's mask. The surface cook can tint
    # the matching colonies at distances where individual twigs are subpixel.
    mask=np.dstack((np.maximum(scrub,dry),np.maximum(rush,bank),pine))
    Image.fromarray(np.rint(np.clip(mask*allowed[:,:,None],0,1)*255).astype(np.uint8)).save(out/"ecotone-weights.png")
    np.save(out/"eligible.npy",allowed)

    # One jittered cell yields at most one candidate across all plant families.
    # The editor graph independently draws each instance's acceptance and transform.
    pitch=2.3
    row,col=np.mgrid[0:int(2000/pitch),0:int(2000/pitch)]
    px=sx+(col+.5+rng.uniform(-.46,.46,col.shape))*pitch
    py=sy-(row+.5+rng.uniform(-.46,.46,row.shape))*pitch
    coords=np.array([(sy-py.ravel())/step,(px.ravel()-sx)/step])
    def sample(a): return map_coordinates(a.astype(float),coords,order=1,mode="constant",prefilter=False)
    probs=np.array([sample(v) for v in fields.values()])
    total=probs.sum(axis=0)
    keep=(sample(allowed)>.9999)&(total>.035)
    probs=probs[:,keep]
    total=total[keep]
    px,py=px.ravel()[keep],py.ravel()[keep]
    kind=np.sum(np.cumsum(probs,axis=0)<rng.random(len(px))*total,axis=0)
    kinds=list(fields)
    # At most 13k new lightweight visuals over the full map. Empty areas are
    # intentional. Instance culling follows each family's authored silhouette.
    total=np.clip(total,0,.94)
    total*=min(1.,13000/total.sum())
    z=field.sample(px,py)
    dx=(field.sample(px+1,py)-field.sample(px-1,py))*.5
    dy=(field.sample(px,py+1)-field.sample(px,py-1))*.5
    norm=np.c_[-dx,-dy,np.ones(len(dx))]
    norm/=np.linalg.norm(norm,axis=1)[:,None]
    points=[dict(id=i,position=[round(float(px[i]),6),round(float(py[i]),6),round(float(z[i]),6)],
                 normal=norm[i].round(8).tolist(),density=round(float(total[i]),7),
                 biome_mask=1,kind=kinds[kind[i]],biome="forest margin and dry bank") for i in range(len(px))]
    source=out/"ecotones.candidates.json"
    source.write_text(json.dumps({"schema":1,"align_to_normal":True,"points":points},separators=(",",":")))
    jobs=[dict(input=str(source),output=str(out/f"ecotones{suffix}.pcg.json"),seed=SEED,scale_min=.68,scale_max=1.12,
               graph=f"/Game/MJOLNIR/PCGAuthoring/PWRField/PCG_Ecotones{suffix}") for suffix in ("","_repeat")]
    grass.dump(out/"request.json",{"jobs":jobs})
    for k in ("heights","mask","texture"):
        shutil.copy2(original/first[k]["file"],out/first[k]["file"])
    first.pop("understory")
    first["sources"].extend({"path":str(p.resolve()),"sha256":grass.digest(p)}
                            for p in (PALETTE,Path(__file__),original/"understory-bake.json"))
    grass.dump(out/"pilot.json",first)
    grass.dump(out/"ecotones-plan.json",dict(seed=SEED,candidates=len(px),expected_rows=round(float(total.sum())),
            expected_by_family={name:round(float(total[kind==j].sum())) for j,name in enumerate(kinds)},
            road_clearance_from_mask_m=7,base_clearance_from_mask_m=10,
            clear_decks=len(geometry["crossings"]),native_obstacle_clearance_m=guard,
            mask_channels=["forest margin and dry brush","dry riparian sedge and willow","young conifer fingers"]))
    print((out/"ecotones-plan.json").read_text())


def export(out,original):
    src,run,repeat=[out/p for p in ("ecotones.candidates.json","ecotones.pcg.json","ecotones_repeat.pcg.json")]
    proof=pcg.compare(src,run,repeat)
    addition=pcg.adapt(src,run,PALETTE,out,"ecotones")
    old=pcg.load(original/"understory-bake.json")
    combined=[(g,raw,extras,n) for g,(_,raw,extras,n) in zip(old["groups"],pcg.read_mjf_groups(original/"understory.json")[1],strict=True)]
    for group,raw,extras,n in pcg.read_mjf_groups(out/"ecotones.json")[1]:
        group.update(mesh_info(str(ROOT/"target/release/mjolnir.exe"),PAKS,group["mesh"]))
        group["standin_slots"]=group.pop("slots")
        group["count"]=n
        combined.append((group,raw,extras,n))
    assert len(combined)==len({g["mesh"] for g,_,_,_ in combined})
    total=sum(n for _,_,_,n in combined)
    if not len(addition["instances"])<=15000 or total!=old["count"]+len(addition["instances"]):
        raise ValueError("Instance budget exceeded or original understory differs")
    binary=out/"understory.bin"
    sides=[]
    with binary.open("wb") as b:
        b.write(b"MJF3"+struct.pack("<II",3,len(combined)))
        for i,(_,raw,extras,n) in enumerate(combined,1):
            # read_mjf_groups preserves each group's count header and payload.
            b.write(raw)
            side=out/(binary.name+f".xf{i}")
            side.write_bytes(extras["xf"])
            sides.append(grass.digest(side))
    bake=out/"understory-bake.json"
    grass.dump(bake,dict(file=binary.name,count=total,groups=[g for g,_,_,_ in combined],
                        binary_sha256=grass.digest(binary),exact_sidecars=sides))
    _,parsed=pcg.read_mjf_groups(bake)
    if [n for _,_,_,n in parsed]!=[n for _,_,_,n in combined]:
        raise ValueError("Combined foliage stream failed its count readback")
    doc=pcg.load(out/"pilot.json")
    doc["understory"]={"file":bake.name,"sha256":grass.digest(bake)}
    grass.dump(out/"pilot.json",doc)
    eligible=np.load(out/"eligible.npy")
    xyz=np.array([r["position"] for r in addition["instances"]])
    coords=np.array([(1000-xyz[:,1])*.504,(xyz[:,0]+1000)*.504])
    support=map_coordinates(eligible.astype(float),coords,order=1,mode="constant",prefilter=False)
    if support.min()<.9998: raise ValueError("PCG margin failed ground and water exclusions")
    families={k:sum(r["kind"]==k for r in addition["instances"]) for k in pcg.load(PALETTE)["kinds"]}
    heights=[(g["origin"][2]+g["extent"][2])*1.12 for g,_,_,_ in combined[len(old["groups"]):]]
    if max(heights)>250:raise ValueError("New drive-through growth exceeds 2.5 m")
    report=dict(proof=proof,added=addition["selected_count"],counts=families,preserved=old["count"],
                total=total,mesh_groups=len(combined),excluded_hits=0,maximum_new_height_cm=round(max(heights),2))
    grass.dump(out/"ecotones.receipt.json",report)
    print(json.dumps(report))


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action",choices=["prepare","export"])
    parser.add_argument("--base",type=Path,default=ORIGINAL)
    parser.add_argument("--out",type=Path,default=ROOT/"out/pwr/world-art/foliage-r2")
    args=parser.parse_args()
    out=args.out.resolve()
    out.mkdir(parents=True,exist_ok=True)
    (prepare if args.action=="prepare" else export)(out,args.base.resolve())
