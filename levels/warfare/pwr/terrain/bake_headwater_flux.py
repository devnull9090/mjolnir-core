"""Bake a terrain-bound headwater into a copy of the native two-tile Fluid Flux playback.

The local steady-flow solve uses cell-face fluxes and depth-dependent conductance.
The inherited GPU bake supplies the downstream discharge and boundary condition.
"""
import argparse
import contextlib
import hashlib
import json
from pathlib import Path
import shutil
import sys

import numpy as np
import OpenEXR
from scipy import ndimage, sparse
from scipy.sparse.linalg import spsolve

from plan_flux import inside, plan
from audit_flux_state import sample, texture
from flux_heightfield import state_matches, verify_state_files, sha256
from heightfield import load_heightfield


def read(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write(path, value):
    path.write_text(json.dumps(value, indent=2, allow_nan=False)+"\n", encoding="utf-8")


def smooth(lo, hi, x):
    s=np.clip((x-lo)/(hi-lo),0.,1.)
    return s*s*(3.-2.*s)


def project_line(xx, yy, profile):
    """Closest segment, arc station and interpolated water surface in metres."""
    best=np.full(xx.shape,np.inf)
    along=np.zeros_like(xx)
    head=np.zeros_like(xx)
    chain=0.
    for a,b in zip(profile[:-1],profile[1:]):
        dx,dy=b[:2]-a[:2]
        length=np.hypot(dx,dy)
        if length<1.e-6:
            continue
        t=np.clip(((xx-a[0])*dx+(yy-a[1])*dy)/length**2,0.,1.)
        distance=(xx-a[0]-dx*t)**2+(yy-a[1]-dy*t)**2
        closer=distance<best
        np.minimum(best,distance,out=best)
        along[closer]=chain+t[closer]*length
        head[closer]=a[2]+t[closer]*(b[2]-a[2])
        chain+=length
    return np.sqrt(best),along,head


def section_discharge(line, chain, state, velocity):
    """Use the signed stored UE velocity on untouched native cross-sections."""
    values=[]
    for station in (85.,95.,105.):
        at=np.searchsorted(chain,station)
        a,b=line[at-1],line[at]
        axis=(b[:2]-a[:2])/(chain[at]-chain[at-1])
        centre=a[:2]+axis*(station-chain[at-1])
        cross=np.array([-axis[1],axis[0]])
        pts=centre+np.arange(-22.,22.01,.5)[:,None]*cross
        u=sample(velocity[...,0],state,pts)[0]
        v=sample(velocity[...,1],state,pts)[0]
        depth=sample(velocity[...,2],state,pts)[0]/100.
        longitudinal=axis[0]*u-axis[1]*v
        values.append(float(np.trapezoid(longitudinal*depth,dx=.5)))
    if min(values)<=0:
        raise ValueError("Inherited flow does not point down the surveyed river in UE coordinates")
    return float(np.median(values)),values


def solve_flow(depth, source, sink, discharge, cell):
    """Conservative depth-averaged flow. Dry banks have zero normal flux."""
    wet=depth>.018
    labels,n=ndimage.label(wet)
    at=np.unravel_index(sink.argmax(),sink.shape)
    if not labels[at]:
        raise ValueError("Outlet has no connected wet depth")
    wet=labels==labels[at]
    depth=np.where(wet,depth,0.)
    source=np.where(wet,source,0.)
    sink=np.where(wet,sink,0.)
    if min(source.sum(),sink.sum())<=0:
        raise ValueError("Source and outlet must share the same waterbody")
    rhs=discharge*(source[wet]/source.sum()-sink[wet]/sink.sum())
    ids=np.full(wet.shape,-1,np.int32)
    ids[wet]=np.arange(wet.sum(),dtype=np.int32)
    edge_data=[]
    for m,other in [((slice(None),slice(None,-1)),(slice(None),slice(1,None))),
                    ((slice(None,-1),slice(None)),(slice(1,None),slice(None)))]:
        valid=wet[m]&wet[other]
        a=ids[m][valid]; b=ids[other][valid]
        ka=depth[m][valid]**(5./3.)
        kb=depth[other][valid]**(5./3.)
        k=2.*ka*kb/(ka+kb)
        edge_data.append((m,other,valid,a,b,k))
    a=np.concatenate([e[3] for e in edge_data])
    b=np.concatenate([e[4] for e in edge_data])
    k=np.concatenate([e[5] for e in edge_data])
    lap=sparse.coo_matrix((np.r_[k,k,-k,-k],(np.r_[a,b,a,b],np.r_[a,b,b,a])),shape=(len(rhs),len(rhs))).tocsr()
    # Pin one potential, leaving the entire zero-net-discharge problem intact.
    phi=np.r_[0.,spsolve(lap[1:,1:],rhs[1:])]
    residual=float(np.max(np.abs(lap@phi-rhs)))
    if not np.isfinite(residual) or residual>max(1.e-5,1.e-7*discharge):
        raise ValueError(f"Flux balance residual {residual}")
    speeds=[]
    for m,other,valid,a,b,k in edge_data:
        face=np.zeros_like(depth[m])
        face[valid]=k*(phi[a]-phi[b])
        flux=np.zeros_like(depth)
        flux[m]+=face; flux[other]+=face
        speeds.append(np.divide(flux,2*cell*depth,out=np.zeros_like(flux),where=wet))
    return np.dstack(speeds),wet,residual


def write_exr(path, rgba):
    path.parent.mkdir(parents=True,exist_ok=True)
    half=np.ascontiguousarray(rgba,dtype=np.float16)
    if not np.isfinite(half).all():
        raise ValueError(f"Nonfinite state in {path}")
    OpenEXR.File({"compression":OpenEXR.ZIP_COMPRESSION,"type":OpenEXR.scanlineimage},
                 {"RGBA":half}).write(str(path))
    if not np.array_equal(texture(path),half):
        raise ValueError(f"Native EXR round trip failed at {path}")


def bake(master,geometry,parent,old_master,old_geometry,out):
    field,old_field=load_heightfield(master),load_heightfield(old_master)
    geom,old_geom=read(geometry),read(old_geometry)
    baseline=read(parent/"pwr.level.json")["flux"]
    entries={d["id"]:d for d in baseline["domains"]}
    up=entries["upper_river"]
    state=up["state"]
    old_state=dict(state)
    for e in entries.values():
        verify_state_files(parent,e["state"])
        if not state_matches(e["state"],e):raise ValueError("Parent state/domain mismatch")
    lake=next(l for l in geom["lakes"] if l["id"]=="north_headwater_lake")
    old_lake=next(l for l in geom["lakes"] if l["id"]=="southeast_lake")
    if old_lake!=old_geom["lakes"][0]:raise ValueError("Unexpected southern lake edit")
    if field.dimensions!=old_field.dimensions or field.origin_m!=old_field.origin_m or field.spacing_m!=old_field.spacing_m:
        raise ValueError("Terrain grid changed")
    southern_rows=field.origin_m[1]+np.arange(field.dimensions[1])*field.spacing_m[1]<=0.
    if not np.array_equal(field.heights_m[southern_rows],old_field.heights_m[southern_rows]):
        raise ValueError("The inherited lower tile does not cover the same terrain")
    out.mkdir(parents=True,exist_ok=True)
    author=out/"authoring"
    with (out/"authoring-plan.log").open("w") as stream,contextlib.redirect_stdout(stream):
        plan(master,geometry,author,resolution=1024)
    native_plan=read(author/"flux.spec.json")
    next_upper=next(e for e in native_plan["domains"] if e["id"]=="upper_river")
    if next_upper["domain"]!=up["domain"]:
        raise ValueError("Capture extent changed; a new complete upper bake is needed")
    up["sources"]=next_upper["sources"]
    up["provenance"]=dict(next_upper["provenance"])
    up["provenance"]["headwater_bake_source_sha256"]=sha256(Path(__file__))
    state["provenance"]=dict(up["provenance"])
    raw={k:texture(parent/state[k]).astype(np.float32) for k in ("height","velocity","ground")}
    if np.any(raw["height"][...,3]!=1.) or np.any(raw["ground"][...,1:3]!=0.):
        raise ValueError("Unknown parent Flux packing")
    original={k:v.copy() for k,v in raw.items()}
    main=np.asarray(next(r for r in geom["watercourses"] if r["id"]=="central_river")["surface_centreline_m"])
    spring=next(r for r in geom["watercourses"] if r["id"]=="headwater_spring")
    feeder=np.asarray(spring["surface_centreline_m"])
    chain=np.r_[0.,np.cumsum(np.linalg.norm(np.diff(main[:,:2],axis=0),axis=1))]
    main=main[:np.searchsorted(chain,132.)+1]
    chain=chain[:len(main)]
    poly=np.asarray(lake["polygon_m"])
    level=lake["water_z_m"]
    old_line=np.asarray(next(r for r in old_geom["watercourses"] if r["id"]=="central_river")["surface_centreline_m"])
    old_line=old_line[:np.argmin(np.linalg.norm(old_line[:,:2]-main[-1,:2],axis=1))+1]
    xy=np.vstack((poly,main[:,:2],feeder[:,:2],old_line[:,:2]))
    changed=np.column_stack(np.where(field.heights_m!=old_field.heights_m))[:,::-1]
    if not len(changed):raise ValueError("Headwater bed has not been built")
    xy=np.vstack((xy,field.origin_m+changed*field.spacing_m))
    lo,hi=xy.min(axis=0)-35,xy.max(axis=0)+35
    width,height=state["res"]
    cell=state["cell"]/100.
    xs=state["centre"][0]/100.+(np.arange(width)+.5-width/2)*cell
    ys=-state["centre"][1]/100.-(np.arange(height)+.5-height/2)*cell
    columns=np.flatnonzero((xs>=lo[0])&(xs<=hi[0]))
    rows=np.flatnonzero((ys>=lo[1])&(ys<=hi[1]))
    window=np.s_[rows[0]:rows[-1]+1,columns[0]:columns[-1]+1]
    xx,yy=np.meshgrid(xs[columns],ys[rows])
    bed=field.sample(xx,yy)
    terrain_change=np.abs(bed-old_field.sample(xx,yy))>.000001
    ground=raw["ground"][window]
    ground[...,0][terrain_change]=(state["centre"][2]-100.*bed[terrain_change]).astype(np.float16)
    v0=original["velocity"][window];h0=original["height"][window]
    dh0=v0[...,2]/100.
    old_head=(h0[...,0]+state["capture"])/100.
    dist,arc,river_head=project_line(xx,yy,main)
    sd,sa,spring_head=project_line(xx,yy,feeder)
    old_dist,_,_=project_line(xx,yy,old_line)
    lake_mask=inside(np.stack([xx,yy],axis=-1),poly)
    lake_possible=ndimage.distance_transform_edt(~lake_mask)*cell<4.
    for island in lake.get("islands",[]):
        lake_possible &= ~inside(np.stack([xx,yy],axis=-1),island["polygon_m"])
    main_width=np.interp(arc,[0,15,55],[lake["outlet"]["width_m"],15,30])
    river_possible=(dist<main_width*.5+3.)&(arc<112.)
    spring_possible=sd<spring["channel_width_m"]*.5+1.5
    # Native running water is below its initial authoring target. Match the
    # actual downstream surface progressively on the existing centreline.
    centre_head=sample((original["height"][...,0]+state["capture"])/100.,state,main[:,:2])[0]
    river_head+=smooth(17.,92.,arc)*np.interp(arc,chain,centre_head-main[:,2])
    # Only the basin, feeder and outlet can introduce water. Adjacent low land
    # outside those banks is dry; disconnected wet components are rejected.
    unrouted=np.full(bed.shape,-1.e6)
    surface=np.maximum.reduce([np.where(lake_possible,level,unrouted),
                               np.where(spring_possible,spring_head,unrouted),
                               np.where(river_possible,river_head,unrouted)])
    depth=np.maximum(0.,surface-bed)
    source=np.exp(-((xx-feeder[0,0])**2+(yy-feeder[0,1])**2)/5.)*(depth>.018)
    recharge=lake_mask*np.maximum(depth-.50,0.)**2
    if source.sum()==0 or recharge.sum()==0:raise ValueError("Feeder or pool recharge area is dry")
    source=.018*source/source.sum()+.982*recharge/recharge.sum()
    sink=np.exp(-((arc-103.)/3.2)**2)*(dist<14.)*depth**1.65
    discharge,samples=section_discharge(main,chain,state,original["velocity"])
    velocity,wet,residual=solve_flow(depth,source,sink,discharge,cell)
    speed=np.linalg.norm(velocity,axis=-1)
    depth=np.where(wet,depth,0.)
    # Positive native V is +Unreal Y (our raster rows increase to the south).
    # The solve returns velocities in the empirical units of the inherited bake.
    shore=ndimage.distance_transform_edt(~wet)*cell
    region=lake_possible|spring_possible|river_possible|terrain_change|((old_dist<36.)&(dh0>.0001))
    old_channel_after=(arc>=108.)&(old_dist<36.)&~terrain_change
    region &= ~old_channel_after
    blend=np.where((arc>20)&(dist<30),1.-smooth(69.,108.,arc),1.)*region
    blend=np.where((arc>=108.)&~terrain_change&~lake_possible&~spring_possible,0.,blend)
    depth_new=depth*blend+dh0*(1.-blend)
    v=raw["velocity"][window]
    foam=(.004+.048*smooth(.55,1.8,speed))*smooth(.15,.95,speed)*smooth(.015,.15,depth)
    v[...,:2]=v0[...,:2]*(1.-blend[...,None])+velocity*blend[...,None]
    v[...,2]=depth_new*100.
    v[...,3]=v0[...,3]*(1.-blend)+foam*blend
    # Both native height channels coincide under wet water. Dry texels recede
    # below the ground, retaining a narrow wet margin immediately on the bank.
    h=raw["height"][window]
    dry_head=bed-.10-np.minimum(shore*.36,5.5)
    desired=np.where(wet,surface,dry_head)
    desired_wet=np.where(wet,surface,bed-.08-np.minimum(shore*.15,2.6))
    h[...,0]=h0[...,0]*(1.-blend)+(desired*100.-state["capture"])*blend
    h[...,1]=h0[...,1]*(1.-blend)+(desired_wet*100.-state["capture"])*blend
    out_state=out/"flux_state"
    shutil.copytree(parent/"flux_state/lower_lake",out_state/"lower_lake",dirs_exist_ok=True)
    for k in raw:
        write_exr(out/state[k],raw[k])
        state[k+"_sha256"]=sha256(out/state[k])
    write(out_state/"upper_river/state.json",state)
    write(out/"flux.json",baseline)
    for e in entries.values():
        if not state_matches(e["state"],e):raise ValueError("Published domain mismatch")
        verify_state_files(out,e["state"])
    stripe=np.zeros((height,width),dtype=bool)
    stripe[window]=(blend>0)|terrain_change
    output={k:texture(out/state[k]) for k in raw}
    if any(not np.array_equal(output[k][~stripe],original[k][~stripe]) for k in raw):
        raise ValueError("An unaffected Flux texel changed")
    if any(not np.array_equal(output[k][-40:],original[k][-40:]) for k in raw):
        raise ValueError("The inherited Flux seam changed")
    labels,_=ndimage.label(output["velocity"][...,2]>.7)
    probes=np.vstack((feeder,main,[[*poly.mean(axis=0),level]]))
    probe_depth=sample(output["velocity"][...,2]/100.,state,probes[:,:2])[0]
    connected=sample(labels.astype(float),state,probes[:,:2])[0]
    if probe_depth.min()<=.01 or not np.allclose(connected,connected[-1],atol=.001):
        raise ValueError(f"Unconnected pool, feeder or outlet: minimum probe depth {probe_depth.min()}, label range {connected.min(),connected.max()}")
    lake_core=lake_mask&(bed<level-.5)&(sd>5.)&(dist>12.)
    surface_error=(output["height"][window][...,0]+state["capture"])/100.-level
    if not lake_core.any() or np.max(np.abs(surface_error[lake_core]))>.055:
        raise ValueError("Pool misses its design waterline or has dry interior")
    lower_files={p.name:sha256(p) for p in (out_state/"lower_lake").iterdir()}
    if not all(sha256(parent/"flux_state/lower_lake"/p)==v for p,v in lower_files.items()):
        raise ValueError("Lower lake changed")
    q=lambda values: np.quantile(values,[0,.5,.95,1]).round(5).tolist()
    report={"schema":"pwr-headwater-flux-bake-v1","method":"Steady finite-volume native-format Fluid Flux saved state with retained GPU-simulated downstream boundary",
            "runtime_simulation":False,"tile_resolution":state["res"],"grid_cell_m":cell,
            "changed_upper_window":{"columns":[int(columns[0]),int(columns[-1])],"rows":[int(rows[0]),int(rows[-1])]},
            "unchanged_upper_texels_compared":int((~stripe).sum()),"upper_ground_changed_texels":int(np.count_nonzero(output["ground"][...,0]!=original["ground"][...,0])),
            "inherited_lower_files":lower_files,"unchanged_seam_rows":40,"old_upper_state":{k:old_state[k] for k in ["height_sha256","ground_sha256","velocity_sha256"]},
            "lake_target_m":level,"lake_core_pixels":int(lake_core.sum()),"lake_core_surface_error_m":q(surface_error[lake_core]),
            "lake_wet_area_m2":round(float((lake_mask&(output["velocity"][window][...,2]>1)).sum()*cell**2),2),
            "lake_speed_native_units":q(speed[lake_core]),"spring_centre_depth_m":q(probe_depth[:len(feeder)]),
            "outlet_centre_depth_m":q(probe_depth[len(feeder):-1]),"sill_surface_m":float(sample((output["height"][...,0]+state["capture"])/100.,state,main[:1,:2])[0][0]),
            "same_wet_component":True,"discharge_native_velocity_times_square_metres":discharge,
            "downstream_cross_section_discharge":samples,"max_discrete_flux_balance_error":residual,
            "trace_probes":[{"id":name,"xy_m":xy.tolist(),"surface_m":float(sample((output["height"][...,0]+state["capture"])/100.,state,xy[None,:])[0][0]),
                          "depth_m":float(sample(output["velocity"][...,2]/100.,state,xy[None,:])[0][0])}
                          for name,xy in [("pool",poly.mean(axis=0)),("spring",feeder[len(feeder)//2,:2]),("sill",main[0,:2]),("outflow",main[np.searchsorted(chain,26),:2])]],
            "inputs":{"terrain":sha256(master),"geometry":sha256(geometry),"source":sha256(Path(__file__))},
            "files":{p.relative_to(out).as_posix():sha256(p) for p in sorted(out_state.rglob("*")) if p.is_file()}}
    write(out/"receipt.json",report)
    print(json.dumps({k:report[k] for k in ("lake_wet_area_m2","sill_surface_m","same_wet_component","trace_probes")},indent=2))


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    for key in ("master","geometry","parent","old-master","old-geometry","out"):
        parser.add_argument("--"+key,type=Path,required=True)
    bake(**{k:v.resolve() for k,v in vars(parser.parse_args()).items()})
