"""Actual-PCG temperate shore boulders; separate from dry mountain outcrops."""
import argparse
import copy
import json
import math
from pathlib import Path
import numpy as np
import build_candidate as v4

OUT=v4.OUT/"shore"


def prepare():
    f=v4.field(); OUT.mkdir(parents=True,exist_ok=True)
    c,r=np.meshgrid(np.arange(196),np.arange(196))
    x=(-980+(c+.5)*10+2.3*np.sin(c*2.399+r*1.113)).ravel()
    y=(-980+(r+.5)*10+2.3*np.sin(r*2.173+c*1.719)).ravel()
    z=f.sample(x,y)
    road=v4.euclidean_distance_to((f.masks["road"]>.002)|(f.masks["bases"]>.002),f.spacing_m[0],4000)
    clearance=v4.sample_array(f,road,x,y)
    shore=f.sample_mask("shore",x,y); wet=f.sample_mask("water",x,y)
    slope=np.hypot((f.sample(x+2,y)-f.sample(x-2,y))/4,(f.sample(x,y+2)-f.sample(x,y-2))/4)
    trees=np.array([p["position"][:2] for p in v4.pcg_foliage.load(v4.SOURCE_TREES)["instances"]])
    nearest=np.empty(len(x))
    for start in range(0,len(x),256):
        pts=np.c_[x[start:start+256],y[start:start+256]]
        nearest[start:start+256]=np.min(np.sum((pts[:,None]-trees[None])**2,axis=2),axis=1)**.5
    allowed=(shore>.15)&(wet<.60)&(slope<.55)&(clearance>12)&(nearest>7)&(z<180)
    # The road mask includes bridge corridors, but preserve explicit additional
    # clearance around the deck endpoints and the entire bridge footprint too.
    geometry=v4.pcg_foliage.load(f.path.parent/f.metadata["geometry"])
    for bridge in geometry["roads"]:
        if bridge.get("structure") not in ("bridge", "culvert"):
            continue
        line=np.array(bridge.get("deck_centreline_m",bridge.get("centreline_m")))
        for a,b in zip(line[:-1,:2],line[1:,:2]):
            edge=b-a; q=np.c_[x,y]-a; t=np.clip(q@edge/(edge@edge),0,1)
            distance=np.linalg.norm(q-t[:,None]*edge,axis=1)
            allowed &= distance>20
    patch=.65+.35*np.sin(x/37+np.cos(y/61))**2
    density=np.where(allowed,shore**2*patch,0)
    low,high=0.,1000.
    for _ in range(55):
        factor=(low+high)/2
        if np.minimum(density*factor,1).sum()<220: low=factor
        else: high=factor
    density=np.minimum(density*(low+high)/2,1)
    points=[{"id":i,"position":[float(x[i]),float(y[i]),float(z[i])],"normal":[0,0,1],
             "density":float(density[i]),"biome_mask":int(allowed[i]),"kind":"shore_rock",
             "biome":"temperate_shore","clearance_m":float(clearance[i]),"shore_weight":float(shore[i])}
            for i in range(len(x))]
    source=OUT/"shore.candidates.json"
    v4.dump(source,{"schema":1,"align_to_normal":False,"master_sha256":f.manifest_sha256,
                   "height_sha256":f.metadata["height"]["sha256"],"points":points})
    jobs=[{"input":str(source),"output":str(OUT/("shore"+suffix+".pcg.json")),
           "graph":"/Game/MJOLNIR/PCGAuthoring/PWRVisualV4/PCG_shore"+suffix,
           "seed":20583,"scale_min":.35,"scale_max":.9} for suffix in ("","_repeat")]
    v4.dump(OUT/"request.json",{"jobs":jobs})
    v4.dump(OUT/"prepare.receipt.json",{"candidates":len(x),"allowed":int(allowed.sum()),
            "expected":float(density.sum()),"source_sha256":v4.digest(source),"radius_limit_m":5.3,
            "road_base_clearance_m":12,"bridge_axis_clearance_m":20,"tree_clearance_m":7})
    print("shore candidates",len(x),"allowed",int(allowed.sum()),"expected",float(density.sum()))


def export():
    source=v4.pcg_foliage.load(OUT/"shore.candidates.json")
    if source.get("master_sha256")!=v4.field().manifest_sha256:raise ValueError("Shore candidates refer to a different runtime master")
    generated=v4.pcg_foliage.load(OUT/"shore.pcg.json")
    repeat=v4.pcg_foliage.load(OUT/"shore_repeat.pcg.json")
    assert generated["source_sha256"]==v4.digest(OUT/"shore.candidates.json")
    assert generated["points"]==repeat["points"]
    pairs=v4.pcg_foliage.validate_output(source,generated)
    assert 1<=len(pairs)<=250
    catalogue=v4.pcg_foliage.load(v4.ASSET_DIR/"rock-bounds.json")
    assets=[next(a for a in catalogue if a["path"].split(".")[-1]=="SM_Rock_Glacial_Med_"+v) for v in "ABC"]
    material_prefix="/Game/Env/Bio/Rock/Glacial/"
    decor=[]
    for original,p in pairs:
        asset=assets[min(2,int(p["asset_draw"]*3))]
        letter=asset["path"][-1]; variant="Lrg_C" if letter=="C" else "Med_"+letter
        parent=material_prefix+f"Rock_Glacial_{variant}/Materials/MI_Rock_Glacial_{variant}_NoSnow"
        s=p["scale_xyz"][0]; height=asset["max"][2]-asset["min"][2]
        pos=list(p["position_cm"]); pos[2]+=(-asset["min"][2]-.26*height)*s
        decor.append({"id":f"pcg_v4_shore_{original['id']}","mesh":asset["path"],"pos":pos,
                      "rot":[0,-v4.pcg_foliage.authored_yaw(p["rotation_xyzw"]),0],"scale":p["scale_xyz"],
                      "static":True,"materials":[{"parent":parent+"."+parent.rsplit("/",1)[-1]}]})
    v4.dump(OUT/"shore.authored-decor.json",{"schema_version":1,"coordinates":"unreal_centimetres",
          "decor":decor,"background_trees":[],"pcg_provenance":{"generator":generated["generator"],
          "graph":generated["graph"],"seed":generated["seed"],"source_sha256":generated["source_sha256"]}})
    v4.dump(OUT/"verification.json",v4.pcg_foliage.compare(OUT/"shore.candidates.json",OUT/"shore.pcg.json",OUT/"shore_repeat.pcg.json"))
    print("selected",len(decor),"shore boulders")


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument("command",choices=["prepare","export"])
    v4.add_source_arguments(parser);args=parser.parse_args();v4.configure(args)
    OUT=v4.OUT/"shore"
    globals()[args.command]()
