"""Measure exported native Flux capture, water levels and the PWR tile seam.

Requires OpenEXR and NumPy. Reads only immutable field, geometry and saved EXRs.
"""
import argparse
import json
from pathlib import Path

import numpy as np
import OpenEXR

from heightfield import load_heightfield
from flux_heightfield import state_matches, verify_state_files


def texture(path):
    channels=OpenEXR.File(str(path)).channels()
    if "RGBA" in channels:return channels["RGBA"].pixels.astype(np.float64)
    return np.stack([channels[k].pixels for k in "RGBA"],axis=-1).astype(np.float64)


def quantile(values):
    return np.quantile(values,[0,.5,.95,1]).tolist() if len(values) else []


def sample(array,state,xy):
    xy=np.asarray(xy)
    # Texture row zero is Unreal -Y: authored +Y. Preserve texel-centre offset.
    column=(xy[:,0]*100-state["centre"][0])/state["cell"]+state["res"][0]/2-.5
    row=(-xy[:,1]*100-state["centre"][1])/state["cell"]+state["res"][1]/2-.5
    good=(column>=0)&(column<=state["res"][0]-1)&(row>=0)&(row<=state["res"][1]-1)
    column=np.clip(column,0,state["res"][0]-1);row=np.clip(row,0,state["res"][1]-1)
    x0=np.floor(column).astype(int);y0=np.floor(row).astype(int)
    x1=np.minimum(x0+1,state["res"][0]-1);y1=np.minimum(y0+1,state["res"][1]-1)
    u=column-x0;v=row-y0
    result=(array[y0,x0]*(1-u)*(1-v)+array[y0,x1]*u*(1-v)+array[y1,x0]*(1-u)*v+array[y1,x1]*u*v)
    return result,good


def audit(master,geometry,spec_path,state_root,out):
    field=load_heightfield(master);geometry=json.loads(Path(geometry).read_text())
    spec=json.loads(Path(spec_path).read_text());root=Path(state_root)
    report={"schema":"mjolnir-flux-audit-v1","terrain_manifest_sha256":field.manifest_sha256,"domains":[]}
    domains={}
    for entry in spec["domains"]:
        state=json.loads((root/"flux_state"/entry["id"]/"state.json").read_text())
        if not state_matches(state,entry):raise ValueError("State provenance/domain mismatch: "+entry["id"])
        verify_state_files(root,state)
        h=texture(root/state["height"]);v=texture(root/state["velocity"]);g=texture(root/state["ground"])
        x=(state["centre"][0]+(np.arange(state["res"][0])+.5-state["res"][0]/2)*state["cell"])/100
        y=-(state["centre"][1]+(np.arange(state["res"][1])+.5-state["res"][1]/2)*state["cell"])/100
        xx,yy=np.meshgrid(x,y);expected=field.sample(xx,yy)
        error=np.abs((state["centre"][2]-g[...,0])/100-expected)
        depth=v[...,2]/100;surface=(h[...,0]+state["capture"])/100
        wet=depth>.01
        item={"id":entry["id"],"capture_abs_error_m_min_median_p95_max":quantile(error.ravel()),
              "wet_capture_error_m_min_median_p95_max":quantile(error[wet]),
              "wet_pixels":int(wet.sum()),"max_depth_m":float(depth.max()),
              "moving_pixels":int(((np.linalg.norm(v[...,:2],axis=-1)>.001)&wet).sum()),
              "foam_above_half_pixels":int(((v[...,3]>.5)&wet).sum()),"profiles":[]}
        for course in geometry["watercourses"]:
            points=np.asarray(course["surface_centreline_m"])
            level,valid=sample(surface,state,points[:,:2]);d,_=sample(depth,state,points[:,:2])
            item["profiles"].append({"id":course["id"],"samples":int(valid.sum()),
                "surface_minus_target_m_min_median_p95_max":quantile((level-points[:,2])[valid]),
                "dry_samples":int(((d<=.01)&valid).sum())})
        # Lake target measurement uses the supplied master mask and target
        # footprint, excluding shoreline, islands and river channels.
        for lake in geometry["lakes"]:
            import sys
            sys.path.insert(0,str(Path(__file__).resolve().parents[2]/"levels/warfare/pwr/terrain"))
            from plan_flux import inside
            mask=inside(np.stack((xx,yy),-1),lake["polygon_m"])&(expected<lake["water_z_m"]-1)
            for island in lake.get("islands",[]):mask&=~inside(np.stack((xx,yy),-1),island["polygon_m"])
            if mask.any():item["lake"]={"id":lake["id"],"target_m":lake["water_z_m"],"samples":int(mask.sum()),
                "surface_minus_target_m_min_median_p95_max":quantile(surface[mask]-lake["water_z_m"]),
                "dry_samples":int((mask&~wet).sum())}
            if mask.any():
                calm=mask.copy()
                for course in geometry["watercourses"]:
                    upstream=np.asarray(course["surface_centreline_m"])[::8]
                    for point in upstream[upstream[:,2]>lake["water_z_m"]+.5]:
                        calm &= (xx-point[0])**2+(yy-point[1])**2>=110**2
                item["lake"]["calm_reservoir"]={"inlet_exclusion_m":110,"samples":int(calm.sum()),
                    "surface_minus_target_m_min_median_p95_max":quantile(surface[calm]-lake["water_z_m"])}
        domains[entry["id"]]=(state,surface,depth)
        report["domains"].append(item)
    if "upper_river" in domains and "lower_lake" in domains:
        river=next(c for c in geometry["watercourses"] if c["id"]=="central_river")
        p=np.asarray(river["surface_centreline_m"]);i=np.where(p[:-1,1]*p[1:,1]<=0)[0][0]
        t=-p[i,1]/(p[i+1,1]-p[i,1]);seam=p[i]*(1-t)+p[i+1]*t
        x=np.linspace(seam[0]-10,seam[0]+10,41)
        states=[]
        for name,sign in [("upper_river",1),("lower_lake",-1)]:
            state,surface,depth=domains[name];y=sign*state["cell"]/200
            level,_=sample(surface,state,np.c_[x,np.full_like(x,y)])
            d,_=sample(depth,state,np.c_[x,np.full_like(x,y)])
            states.append(level)
            report.setdefault("seam",{})[name]={"surface_m_min_median_p95_max":quantile(level),"dry_samples":int((d<=.01).sum())}
        report["seam"]["adjacent_edge_difference_m_min_median_p95_max"]=quantile(np.abs(states[0]-states[1]))
        report["seam"]["target_m"]=float(seam[2])
    Path(out).write_text(json.dumps(report,indent=2)+"\n")
    print(json.dumps(report,indent=2))
    return report


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    for name in ("heightfield","geometry","spec","states","out"):p.add_argument("--"+name,required=True)
    a=p.parse_args();audit(a.heightfield,a.geometry,a.spec,a.states,a.out)
