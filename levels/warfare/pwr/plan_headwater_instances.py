"""Project only existing native HISM instances touched by the new shore."""

import json
import os
import sys
from pathlib import Path
import numpy as np
from scipy.spatial import ConvexHull

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "terrain"))
import headwater_dressing as d

out = Path(os.environ.get("PWR_HEADWATER_OUTPUT",d.HEADWATER))
basin = os.environ.get("PWR_RIVER_BASIN") == "1"
parent = d.ROOT / "out/pwr/river-apron"
old = d.load_heightfield(parent/"terrain/runtime-master.json" if basin else d.HERE / "runtime-v5/runtime-master.json")
new = d.load_heightfield(out / "terrain/runtime-master.json")
inventory = d.read(out / "native-scene-inventory.json")
bounds = np.array(
    d.read(out / "terrain/headwater-terrain.receipt.json")["changed_bounds_m"]
).reshape(2, 2) + [[-12, -12], [12, 12]]
# Read the final ledger, including deliberately submerged boulders. The native
# instance exclusion must follow the very same transforms as the physical hull.
feet = []
mesh_hulls = {}
ledger = d.read(out / "dressing/decor-moves.json")
previous = {r["id"]:r for r in d.read(parent/"dressing/decor-moves.json")["decor"]} if basin else {}
for row in ledger["decor"]:
    if basin and row["id"] in previous and row["new_pos_ue_cm"] == previous[row["id"]]["new_pos_ue_cm"]:
        continue
    if row["location"] == "original_bank" and not basin:
        continue
    local = d.world_foot(row,mesh_hulls)[:,:2] * d.UE_TO_WORLD
    centre = np.asarray(row["new_pos_ue_cm"][:2]) * d.UE_TO_WORLD
    feet.append((centre,np.linalg.norm(local,axis=1).max(),centre + local[ConvexHull(local).vertices]))

river, = [r for r in d.read(out/"terrain/terrain.geometry.json")["watercourses"] if r["id"]=="central_river"]

def riparian_targets(variant):
    """Small colonies at the back of the point bar, and on the opposite cut lip."""
    line = np.asarray(river["erosion_reach"]["centreline_m"])
    lengths = np.linalg.norm(np.diff(line[:,:2],axis=0),axis=1)
    arc = np.r_[0.,lengths.cumsum()]-river["erosion_reach"]["sill_station_m"]
    sections = np.asarray(river["section_station_width_depth_m"])
    clusters = [(4.4,1),(12.8,-1),(19.,1),(30.7,1),(35.,-1)] if variant==0 else [(7.2,-1),(16.1,1),(29.,-1),(37.2,1)]
    targets=[]
    for station,sign in clusters:
        for ds,offset in ((-.7,.35),(.25,1.23),(1.05,-.31)):
            s=station+ds
            j=np.clip(np.searchsorted(arc,s)-1,0,len(lengths)-1)
            f=(s-arc[j])/lengths[j]
            xyz=line[j]+f*(line[j+1]-line[j])
            delta=line[j+1,:2]-line[j,:2]
            normal=np.array([-delta[1],delta[0]])/lengths[j]
            half=.5*np.interp(s,sections[:,0],sections[:,1])
            offset+= ((1.45*np.cos(.15*s+.4)-.72*np.sin(.31*s)) if sign>0 else
                      (1.2+.9*np.sin(s*.19)+.48*np.sin(s*.53+.7)))
            xy=xyz[:2]+normal*sign*(half+(1.4 if sign>0 else 2.95)+offset)
            level=d.sample(new,xy)
            if not .03 < level-xyz[2] < 2.75:
                continue
            if any(d.inside_polygon(xy[0:1],xy[1:2],polygon)[0] for _,_,polygon in feet):
                continue
            targets.append(xy)
    return targets

result = []
for c in inventory["instances"]:
    rows = np.asarray(c["instances"], dtype=float)
    ix = rows[:, 0].astype(int)
    rec = np.empty(len(ix), dtype=[("xyz", "<f4", (3,))])
    rec["xyz"] = rows[:, 1:]
    removed, moved, z, stats = d.grass_changes(rec, old, new, bounds, feet)
    transplanted=[]
    if (not basin and "erosion_reach" in river and c["label"]=="PWR_FieldUnderstory" and
            c["component"] in ("MJFol_13_1_0","MJFol_14_1_0") and "Rushes" in c["mesh"]):
        targets=riparian_targets(int(c["component"]=="MJFol_14_1_0"))
        count=min(len(removed),len(targets))
        for source,dest in zip(removed[:count],targets):
            xyz=rec["xyz"][source].astype(float)
            root_offset=xyz[2]-100.*d.sample(old,xyz[:2]*d.UE_TO_WORLD)
            new_xyz=[*(dest/d.UE_TO_WORLD),100.*d.sample(new,dest)+root_offset]
            transplanted.append([int(ix[source]),*xyz,*new_xyz])
        removed=removed[count:]
    if not len(removed) + len(moved) + len(transplanted):
        continue
    if "MaturePine" in c["mesh"]:
        print("pine", rows[removed], rows[moved], z, flush=True)
    result.append(
        dict(
            label=c["label"],
            component=c["component"],
            mesh=c["mesh"],
            removed=[[int(ix[i]), *rec["xyz"][i].astype(float)] for i in removed],
            moved=[
                [int(ix[i]), *rec["xyz"][i].astype(float), float(h)]
                for i, h in zip(moved, z)
            ],
            transplanted=transplanted,
        )
    )
(out / "native-foliage-plan.json").write_text(json.dumps(result, separators=(",", ":")))
print(
    "Native components",
    len(result),
    "removed",
    sum(len(v["removed"]) for v in result),
    "moved",
    sum(len(v["moved"]) for v in result),
)
