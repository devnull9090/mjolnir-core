"""Place rooted patches on the surveyed wetland margins of the finished .34 terrain."""
import json
import math
from pathlib import Path
import sys

import numpy as np

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/"tools/level"))
from heightfield import load_heightfield


def plan(parent):
    work=parent/"shore-finish"
    field=load_heightfield(parent/"terrain/runtime-master.json")
    geo=json.loads((parent/"terrain/terrain.geometry.json").read_text())
    river,=[r for r in geo["watercourses"] if r["id"]=="central_river"]
    reach=river["erosion_reach"]
    centre=np.asarray(reach["centreline_m"])
    length=np.linalg.norm(np.diff(centre[:,:2],axis=0),axis=1)
    arc=np.r_[0.,length.cumsum()]-reach["sill_station_m"]
    sections=np.asarray(river["section_station_width_depth_m"])
    ledger=json.loads((parent/"dressing/decor-moves.json").read_text())
    sys.path.insert(0,str(Path(__file__).parent/"terrain"))
    import headwater_dressing as d
    from scipy.spatial import ConvexHull
    mesh_cache={}
    rocks=[]
    for row in ledger["decor"]:
        offset=d.world_foot(row,mesh_cache)[:,:2]*d.UE_TO_WORLD
        p=np.asarray(row["new_pos_ue_cm"][:2])*d.UE_TO_WORLD
        rocks.append((p,offset[ConvexHull(offset).vertices]+p,np.linalg.norm(offset,axis=1).max()))
    rng=np.random.default_rng(351710)
    plants=[]
    def add(s,beyond,sign,kind):
        j=int(np.clip(np.searchsorted(arc,s)-1,0,len(length)-1))
        f=(s-arc[j])/length[j]
        xyz=centre[j]+f*(centre[j+1]-centre[j])
        t=(centre[j+1,:2]-centre[j,:2])/length[j]
        half=.5*np.interp(s,sections[:,0],sections[:,1])
        bank=(half+1.45*math.cos(.15*s+.4)-.72*math.sin(.31*s)) if sign==1 else -(half+1.2+.9*math.sin(.19*s)+.48*math.sin(.53*s+.7))
        xy=xyz[:2]+(bank+sign*beyond)*np.array([-t[1],t[0]])
        z=float(field.sample(*xy))
        if not .06<z-xyz[2]<3.85 or any(field.sample_mask(k,*xy)>.01 for k in ("road","bases")):
            return
        if any(np.linalg.norm(xy-p)<r+.12 and d.inside_polygon(xy[:1],xy[1:],poly)[0] for p,poly,r in rocks):
            return
        height={"wild_a":(.39,.73),"wild_b":(.35,.66),"rye":(.51,.91),"rush":(.46,.74),
                "willow":(.81,1.26),"sedge":(.34,.58)}[kind]
        plants.append(dict(kind=kind,position=[round(100*xy[0],3),round(-100*xy[1],3),round(100*z-1.2,3)],
                           height_cm=round(100*rng.uniform(*height),3),yaw=round(rng.uniform(-180,180),4),
                           breadth=round(rng.uniform(.96,1.42),4)))
    for sign in (-1,1):
        s=-14.
        while s<61:
            patch_len=rng.uniform(2.3,6.3)
            width=rng.uniform(1.45,3.65)
            start=rng.uniform(.7,3.4) if sign<0 else rng.uniform(1.3,4.2)
            for _ in range(int(patch_len*width*3.0)):
                station=s+rng.uniform(0,patch_len)
                shore=start+rng.uniform(-width*.34,width)+.50*math.sin(station*.58)
                kind=rng.choice(["wild_a","wild_b","rye","rush","sedge"],p=[.29,.23,.16,.12,.20])
                add(station,shore,sign,kind)
            if rng.uniform()<.46:
                add(s+.45*patch_len,start+width,sign,"willow")
            s+=patch_len+rng.uniform(-.9,1.45)
    if not 650<=len(plants)<=2100:
        raise ValueError(f"Unexpected shoreline coverage: {len(plants)}")
    (work/"planting.json").write_text(json.dumps(plants,separators=(",",":")))
    print(f"{len(plants)} surveyed placements")


if __name__=="__main__":
    plan(ROOT/"out/pwr/river-erosion")
