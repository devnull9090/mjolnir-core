"""Publish probe coordinates clear of real stock rock hulls for the private Halo trace."""
import argparse
from pathlib import Path
import json
import numpy as np

import headwater_dressing as d
import registered_basin as basin
from survey_outlet_apron import survey as survey_apron


def verify(work):
    f=d.load_heightfield(work/"terrain/runtime-master.json")
    parent=d.load_heightfield(basin.PREVIOUS/"runtime-master.json")
    receipt=d.read(work/"terrain/headwater-terrain.receipt.json")
    rows=d.read(work/"dressing/level-decor.json")
    moves=d.read(work/"dressing/decor-moves.json")
    original=d.read(d.PLAYTEST/"pwr.level.json")["decor"]
    previous=d.read(basin.a.WORK/"dressing/level-decor.json")
    transformed={r["level_index"]:r for r in moves["decor"]}
    if len(original)!=len(rows):raise ValueError("Different native row count")
    for i,(source,row) in enumerate(zip(original,rows)):
        if any(source.get(k)!=row.get(k) for k in ("id","mesh","rot","scale")):
            raise ValueError("Native mesh, rotation, scale or index changed")
        if i in transformed:
            ledger=transformed[i]
            if ledger["new_pos_ue_cm"]!=row["pos"] or ledger["old_pos_ue_cm"]!=source["pos"]:
                raise ValueError("Collision and visible model transforms disagree")
        elif source["pos"]!=row["pos"]:
            raise ValueError("Native actor moved without a corresponding collision")
    rocks=d.read(work/"dressing/flow-rocks.json")["rocks"]
    if rocks!=d.read(basin.a.WORK/"dressing/flow-rocks.json")["rocks"]:
        raise ValueError("Registered outlet obstacles changed")
    trees=np.array([row["position"][:2] for row in d.read(d.TREES)["instances"]])
    drowned=np.sum((d.mask(f,"water",trees)>=.3)&(d.mask(parent,"water",trees)<.3))
    if drowned:raise ValueError("Additional stock trees drowned")
    cache={};positions=[];radii=[]
    for row in rows:
        p=np.array(row["pos"][:2])*d.UE_TO_WORLD
        if not (-540<p[0]<-188 and 730<p[1]<1000):continue
        if "SM_Rock_Glacial_" in row["mesh"]:
            vertices=d.world_foot(row,cache)[:,:2]*d.UE_TO_WORLD
            positions.append(p);radii.append(np.linalg.norm(vertices,axis=1).max())
    centres=np.array(positions);radius=np.array(radii)
    labels={"west_shallow":"west_submerged","west_rim_dry":"west_ridge",
            "east_shallow":"eastern_shelf","east_rim_dry":"eastern_rim","upper_lake_wet":"left_north_bank",
            "north_dry_closure":"right_closure","lower_lake_wet":"lower_basin"}
    probes={};details={}
    for label,name in labels.items():
        source=receipt["native_probes"][name]
        p=np.array(source["xy_m"]);seen=None
        for _,x,y in sorted((x*x+y*y,x,y) for x in range(-3,4) for y in range(-3,4)):
            test=p+[x,y];clear=float(np.min(np.linalg.norm(centres-test,axis=1)-radius))
            if clear<1.8:continue
            z=float(f.sample(*test))
            if (z-basin.LEVEL)*source["bed_above_local_water_m"]<=0 or abs(z-basin.LEVEL)<.12:continue
            seen=(test,z,clear);break
        if seen is None:raise ValueError("Native trace has no clear sample at "+name)
        test,z,clear=seen
        probes[label]=test.tolist()
        details[label]=dict(ground_z_m=round(z,5),water_z_m=basin.LEVEL,
            prior_ground_z_m=round(float(parent.sample(*test)),5),native_rock_radial_clearance_m=round(clear,3))
    result=dict(schema="pwr-basin-native-probes-v1",terrain_sha256=f.manifest_sha256,terrain_probes=probes,
        expected=details,all_native_decor_rows_verified=len(rows),
        newly_drowned_stock_trees=int(drowned),unchanged_three_flow_obstacles=True)
    basin.head.save(work/"terrain/basin-probes.json",result)
    proof=survey_apron(work)
    previous_proof=d.read(basin.a.WORK/"dressing/apron-survey.json")
    if proof["camera_rows"]!=previous_proof["camera_rows"] or proof["rock_hulls"]!=previous_proof["rock_hulls"]:
        raise ValueError("Foreground camera projection changed")
    basin.head.save(work/"dressing/apron-survey.json",proof)
    return result


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work",type=Path,default=basin.OUT)
    print(json.dumps(verify(parser.parse_args().work),indent=2))

