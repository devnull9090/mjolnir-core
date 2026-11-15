"""Synthetic accuracy experiment, explicitly not PWR geography or a runtime build."""
import argparse
import json
from pathlib import Path
import numpy as np
from adaptive_heightfield import build
from heightfield import write_heightfield

def fixture(size=1025):
    y,x=np.mgrid[-1000:1000:complex(size),-1000:1000:complex(size)]
    h=70+45*np.sin(x/330)*np.cos(y/310)
    h+=95*np.exp(-((x+610)/260)**2-((y-410)/310)**2)
    h+=55*np.exp(-((x-540)/230)**2-((y+570)/220)**2)
    h+=7*np.sin((x+y)/58)*np.sin((x-y)/105)
    # A smoothly graded, winding road. The mask measures its full clear lane.
    distance=np.abs(x-160*np.sin(y/420))
    road=(distance<16).astype(float)
    blend=np.clip((distance-17)/46,0,1);blend=blend*blend*(3-2*blend)
    h=h*blend+(38+y*.014+3*np.sin(y/450))*(1-blend)
    # Basin and natural shore: intentional curvature, not a rectangle or step.
    radius=np.hypot((x+430)/210,(y+330)/150)
    water=28.
    shore=(np.abs(radius-1)<.13).astype(float)
    basin=water+(radius-1)*24
    rim=np.clip((radius-.95)/.65,0,1);rim=rim*rim*(3-2*rim)
    h=basin*(1-rim)+h*rim
    # One exact planar foundation tests preservation of a gameplay flat.
    r=np.maximum(np.abs(x-680),np.abs(y-630))
    flat=(r<=40).astype(float)
    blend=np.clip((r-45)/65,0,1);blend=blend*blend*(3-2*blend)
    h=45*(1-blend)+h*blend
    return h,{"road":road,"shore":shore,"flat":flat}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--out",type=Path,default=Path("out/pwr/terrain-prototype"))
    p.add_argument("--size",type=int,default=1025)
    p.add_argument("--budgets",default="12000,22000")
    a=p.parse_args();a.out.mkdir(parents=True,exist_ok=True)
    heights,masks=fixture(a.size)
    field=write_heightfield(a.out/"synthetic-master.json",heights,(-1000,-1000),
                           (2000/(a.size-1),2000/(a.size-1)),masks,
                           purpose="synthetic collision approximation proof; not approved PWR geography",water_level_m=28)
    rows=[]
    for budget in map(int,a.budgets.split(",")):
        v,t,report=build(field,terrain_budget=budget)
        target=a.out/str(budget);target.mkdir(exist_ok=True)
        np.savez_compressed(target/"collision-surface.npz",vertices_m=v,triangles=t)
        (target/"collision-report.json").write_text(json.dumps(report,indent=2)+"\n")
        row={"budget":budget,"surfaces":len(t),"edges":report["topology"]["edges"],
             "errors_m":{k:v["max_abs_m"] for k,v in report["measurement"]["regions"].items()},
             "pass":report["accuracy_and_mesh_budget_pass"],"elapsed_seconds":report["elapsed_seconds"]}
        rows.append(row);print(json.dumps(row),flush=True)
    (a.out/"comparison.json").write_text(json.dumps(rows,indent=2)+"\n")

if __name__=="__main__":main()
