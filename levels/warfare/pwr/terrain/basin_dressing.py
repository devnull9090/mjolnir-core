"""Reseat the affected stock .36 shore rocks while retaining their original native hulls."""
import copy
import numpy as np
from scipy.spatial import ConvexHull

import headwater_dressing as dressing
import registered_basin as basin


def dry_position(origin,rotated,field,occupied,trees):
    foot=rotated[:,:2]*dressing.UE_TO_WORLD
    radius=np.linalg.norm(foot,axis=1).max()
    dr=np.arange(-64,65,1.)
    u,v=np.meshgrid(dr,dr);xy=origin+np.column_stack((u.ravel(),v.ravel()))
    xy=xy[np.max(np.abs(xy),axis=1)<996.]
    level=basin.LEVEL
    height=dressing.sample(field,xy)
    candidates=(height>level+.16)&(dressing.mask(field,"water",xy)<.08)
    candidates&=(dressing.mask(field,"road",xy)<.01)&(dressing.mask(field,"bases",xy)<.01)
    candidates&=trees.query(xy)[0]>radius+1.
    for pos,r in occupied:
        if np.linalg.norm(pos-origin)<100.:
            candidates &= np.sum((xy-pos)**2,axis=1)>(radius+r+.45)**2
    xy=xy[candidates]
    if not len(xy):raise ValueError("No dry shore near native rock")
    height=height[candidates]
    # Prefer a low, gently sloped bank; let a large boulder recede up the
    # shore enough to keep its entire old rotated collision hull out of water.
    score=np.sum((xy-origin)**2,axis=1)+2.5*(height-level-1.5)**2
    for idx in np.argsort(score,kind="stable"):
        p=xy[idx];hull=p+foot
        if np.max(dressing.mask(field,"water",hull))>.14 or np.min(dressing.sample(field,hull))<level+.05:
            continue
        if np.ptp(dressing.sample(field,hull))>max(1.05,.42*np.ptp(rotated[:,2])*.01):
            continue
        return p
    raise ValueError("No fully seated native shore-rock position near "+str(origin))


def dress(decor,field,trees):
    prior=dressing.load_heightfield(basin.PREVIOUS/"runtime-master.json")
    work=basin.a.WORK/"dressing"
    previous=dressing.read(work/"level-decor.json")
    previous_moves={r["id"]:r for r in dressing.read(work/"decor-moves.json")["decor"]}
    obstacles=dressing.read(work/"flow-rocks.json")["rocks"]
    protected={r["id"] for r in obstacles}
    if len(previous)!=len(decor):raise ValueError("Previous native actor roster changed")
    geometry=copy.deepcopy(previous)
    cached={};pending=[];occupied=[];moves=copy.deepcopy(previous_moves)
    changes=[]
    for i,(row,src) in enumerate(zip(previous,decor)):
        if row["id"]!=src["id"] or row.get("scale")!=src.get("scale") or row.get("rot")!=src.get("rot"):
            raise ValueError("Original native actors differ")
        origin=np.array(row["pos"][:2])*dressing.UE_TO_WORLD
        if not (-540<origin[0]<-188 and 725<origin[1]<1000):continue
        if "SM_Rock_Glacial_" not in row["mesh"]:
            if abs(field.sample(*origin)-prior.sample(*origin))>.002:
                raise ValueError("Unmodeled native actor on regraded terrain "+row["id"])
            continue
        hull=dressing.world_foot(row,cached);foot=hull[:,:2]*dressing.UE_TO_WORLD
        radius=float(np.linalg.norm(foot,axis=1).max());xy=np.vstack((origin,origin+foot))
        wet=dressing.mask(field,"water",xy);prev=dressing.mask(prior,"water",xy)
        delta=dressing.sample(field,xy)-dressing.sample(prior,xy)
        if not np.any(delta!=0.) and not np.any(wet-prev>.15):
            occupied.append((origin,radius))
            continue
        if row["id"] in protected:raise ValueError("Would move an outlet obstacle")
        relocate=bool(wet[0]>.14 or np.max(wet)>.40)
        if not relocate:occupied.append((origin,radius))
        pending.append((relocate,-radius,i,origin,hull))
    for relocate,negative_radius,i,origin,hull in sorted(pending,key=lambda row:(not row[0],row[1],row[2])):
        row=previous[i];src=decor[i];foot=hull[:,:2]*dressing.UE_TO_WORLD
        xy=dry_position(origin,hull,field,occupied,trees) if relocate else origin
        if relocate:occupied.append((xy,-negative_radius))
        z,burial=dressing.seat_rock(row,hull,xy,prior,field)
        pos=[*(xy/dressing.UE_TO_WORLD).tolist(),z] if relocate else [*row["pos"][:2],z]
        geometry[i]["pos"]=pos
        location="basin_dry_shore" if relocate else previous_moves.get(row["id"],{}).get("location","basin_original_bank")
        moves[row["id"]]=dict(level_index=i,id=row["id"],mesh=row["mesh"],old_pos_ue_cm=src["pos"],new_pos_ue_cm=pos,
            delta_ue_cm=(np.array(pos)-np.array(src["pos"])).tolist(),rot=row["rot"],scale=row["scale"],
            location=location,hull_height_vs_ground_m=burial)
        changes.append(dict(id=row["id"],new_xy_m=xy.tolist(),previous_xy_m=origin.tolist(),
            relocated_to_dry_shore=relocate,hull_clearance_range_m=list(burial)))
    footprints=[]
    for row in moves.values():
        if np.array_equal(row["new_pos_ue_cm"][:2],row["old_pos_ue_cm"][:2]):continue
        dest=geometry[row["level_index"]];xy=np.array(dest["pos"][:2])*dressing.UE_TO_WORLD
        foot=dressing.world_foot(dest,cached)[:,:2]*dressing.UE_TO_WORLD
        footprints.append((xy,float(np.linalg.norm(foot,axis=1).max()),xy+foot[ConvexHull(foot).vertices]))
    return geometry,sorted(moves.values(),key=lambda r:r["level_index"]),footprints,obstacles,changes

