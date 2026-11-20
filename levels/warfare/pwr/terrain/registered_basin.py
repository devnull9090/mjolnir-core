"""Regrade the registered northern lake behind the existing .36 headwater apron."""
import argparse
import copy
import json
from pathlib import Path
import tempfile

import contourpy
import numpy as np
from scipy import ndimage
from scipy.spatial import cKDTree

import outlet_apron as a
import northern_headwaters as head
import headwater_dressing as dressing
from survey_outlet_apron import ray_water, intervals

PREVIOUS = a.WORK/"terrain"
OUT = head.ROOT/"out/pwr/river-basin"
LEVEL = 142.4
# The reeds partly hide the physical contact in the generated reference.
# Trace in the registered 1600x900 viewport; the first and last controls
# close the far spring cove and overlap the already built outlet respectively.
TRACE = np.array([[412,660,895],[414,500,955],[420,292,1060],[428,190,1260],[440,227,1395],[452,255,1387],
    [464,282,1374],[476,315,1360],[492,334,1333],[508,354,1295],[524,365,1280],[540,393,1250],
    [555,426,1228],[567,434,1200]],float)


def flood(ground,xy):
    forward,side=a.coordinates(xy)
    seal=(np.abs(forward-40.)<3.)&(np.abs(side)<25.)
    labels,_=ndimage.label((ground<LEVEL-.025)&~seal,np.ones((3,3)))
    source=np.unravel_index(np.argmin(np.sum((xy-[-360.,900.])**2,axis=-1)),ground.shape)
    fill=labels==labels[source]
    if not labels[source] or np.any(fill[[0,-1],:]) or np.any(fill[:,[0,-1]]):
        raise ValueError("North headwater has an unintended second outlet")
    return fill


def chain(poly,greater):
    # Retain the .36 polygon vertices and analytic seam at the exact plane
    # where its upstream, resculpted part begins.
    fw,_=a.coordinates(poly)
    signed=(fw-61.)*(1 if greater else -1)
    enter=np.flatnonzero((signed<0)&(np.roll(signed,-1)>=0))
    if len(enter)!=1:
        raise ValueError("Unexpected number of shoreline seam crossings")
    i=int(enter[0]); j=(i+1)%len(poly)
    def crossing(i,j):
        t=signed[i]/(signed[i]-signed[j])
        return (1.-t)*poly[i]+t*poly[j]
    points=[crossing(i,j)]
    while signed[j]>=0:
        points.append(poly[j]);i,j=j,(j+1)%len(poly)
    points.append(crossing(i,j))
    return np.array(points)


def perimeter(poly,fill,xx,yy,field):
    fw,_=a.coordinates(np.stack((xx,yy),axis=-1))
    left=head.shore_distance(xx,yy,poly)
    right=(ndimage.distance_transform_edt(fill)-ndimage.distance_transform_edt(~fill))*field.spacing_m[0]
    signed=left+head.smooth((fw-61.)/11.)*(right-left)
    loops=contourpy.contour_generator(x=xx[0],y=yy[:,0],z=signed).lines(0.)
    centre=[p for p in loops if head.inside_polygon(np.array([-360.]),np.array([900.]),p)[0]]
    if len(centre)!=1:raise ValueError("Disconnected basin shoreline geometry")
    old=chain(poly,False);new=chain(centre[0][:-1],True)
    if np.linalg.norm(old[-1]-new[-1])<np.linalg.norm(old[-1]-new[0]):new=new[::-1]
    return np.vstack((old,new[1:-1]))


def build(out):
    old=head.load_heightfield(PREVIOUS/"runtime-master.json")
    base=head.load_heightfield(head.BASE)
    geo=json.loads((PREVIOUS/"terrain.geometry.json").read_text())
    original=copy.deepcopy(geo)
    lake=geo["lakes"][-1]
    line=np.array(geo["watercourses"][0]["erosion_reach"]["centreline_m"])
    spring=np.array(geo["watercourses"][-1]["surface_centreline_m"])
    traced=[a.intersect(TRACE[:,i],TRACE[:,0],line)[:,:2] for i in (1,2)]
    poly=np.vstack((traced[0],traced[1][::-1]))
    axes=[np.arange(n)*step+orig for n,step,orig in zip(old.dimensions,old.spacing_m,old.origin_m)]
    ix=np.flatnonzero((axes[0]>=-540)&(axes[0]<=-185));iy=np.flatnonzero((axes[1]>=718)&(axes[1]<=1000))
    xx,yy=np.meshgrid(axes[0][ix],axes[1][iy]);xy=np.stack((xx,yy),axis=-1);area=np.ix_(iy,ix)
    inner=head.shore_distance(xx,yy,poly)
    fw,_=a.coordinates(xy)
    spring_dist,_,_=head.line_fields(xx,yy,spring)
    prior=old.heights_m[area]
    guards=head.smooth((fw-61.)/11.)*head.smooth((spring_dist-9.)/7.)*(1.-head.smooth((yy-984.)/12.))
    strength=head.smooth((inner+24.)/22.)*guards
    floor=LEVEL-np.interp(inner,[0,4,10,22],[0,.55,1.4,3.])
    outside=LEVEL+np.interp(-inner,[0,2,8,17,25],[0,.22,.89,2.6,4.8])
    # Carve lakeward, preserve the original deeper water, grade the dry
    # shoulder, then raise the previously low eastern saddle into a point bar.
    cut=np.minimum(prior,np.where(inner>=0,floor,outside))
    rim=np.where((inner<0)&(old.masks["water"][area]<.25),np.maximum(cut,np.minimum(outside,LEVEL+.80)),cut)
    heights=old.heights_m.copy();heights[area]=prior+strength*(rim-prior)
    previous_wet=flood(prior,xy);wet=flood(heights[area],xy)
    masks={k:v.copy() for k,v in old.masks.items()}
    active=strength>0
    apply=active & ((wet!=previous_wet)|(np.abs(prior-heights[area])>.002))
    tide=np.where(wet,1.,0.)
    wet_update=apply|(active&wet&(old.masks["water"][area]<.5))
    masks["water"][area]=np.where(wet_update,tide,masks["water"][area])
    distance=(ndimage.distance_transform_edt(wet)-ndimage.distance_transform_edt(~wet))*old.spacing_m[0]
    shore=1.-head.smooth(np.abs(distance)/12.)
    masks["shore"][area]+=strength*(shore-masks["shore"][area])
    masks["forest"][area]*=1.-strength*np.maximum(masks["water"][area],.8*masks["shore"][area])
    dy,dx=np.gradient(heights,*old.spacing_m[::-1])
    masks["walkable"][area]=np.where(apply,(np.hypot(dy[area],dx[area])<=.35)&(masks["water"][area]<.5),masks["walkable"][area])
    for k in ["protected","protected_core"]:
        masks[k][area]=np.maximum(masks[k][area],apply)
    # Leave an exact source polygon on the rendered outlet side of the seam.
    parent_poly=np.array(lake["polygon_m"])
    boundary=perimeter(parent_poly,wet,xx,yy,old)
    lake["polygon_m"]=boundary.tolist()
    lake["polygon_uv"]=((boundary*[1,-1]+1000.)/2000.).tolist()
    lake["registered_basin"]=dict(target_sha256=head.sha256(a.TARGET),source_terrain_sha256=old.manifest_sha256,
        target_row_left_right_px=TRACE.tolist(),left_bank_trace_m=traced[0].tolist(),right_bank_trace_m=traced[1].tolist(),
        shoreline_hand_trace_tolerance_px=[15,35],spring_grade_reserve_m=9,protected_apron_forward_m=61,
        lake_surface_m=LEVEL,east_rim_emergence_m=.8)
    lake["floor_z_m"]=round(float(heights[area][wet].min()),3)
    lake["target_depth_m"]=[0.,round(LEVEL-lake["floor_z_m"],3)]
    out.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(dir=out.parent,prefix=".basin-") as tmp:
        staged=Path(tmp)/"terrain";staged.mkdir()
        gps=staged/"terrain.geometry.json";head.save(gps,geo)
        source=staged/"authoring-master.json"
        head.write_heightfield(source,heights,base.origin_m,base.spacing_m,masks,generator="registered_basin.py",
            geometry=gps.name,geometry_sha256=head.sha256(gps),water_level_m=base.metadata["water_level_m"],
            surface_interpolation="triangle_nw_se",parent_runtime_manifest_sha256=base.manifest_sha256,
            previous_erosion_sha256=old.manifest_sha256,landscape_encoding_policy=base.metadata["landscape_encoding_policy"])
        master=staged/"runtime-master.json";head.derive(source,master,components=base.metadata["landscape_encoding"]["components"])
        field=head.load_heightfield(master);changed=field.heights_m!=base.heights_m
        new=field.heights_m[area];fill=flood(new,xy);delta=field.heights_m-old.heights_m
        if np.any(delta[(base.masks["road"]>.01)|(base.masks["bases"]>.01)]) or np.any(changed&((base.masks["road"]>.01)|(base.masks["bases"]>.01))):
            raise ValueError("A protected road or base moved")
        if any(geo[k]!=original[k] for k in ["sites","nodes","crossings","roads","watercourses"]):
            raise ValueError("Basin revised a gameplay grade")
        if any(np.any(field.masks[k][area][fw<=61.]!=old.masks[k][area][fw<=61.]) for k in masks) or np.any(delta[area][fw<=61.]):
            raise ValueError("Registered .36 foreground was disturbed")
        support=np.load(a.WORK/"bank/support.npz")["triangles_m"].reshape(-1,3)
        hero=np.vstack([np.array(r["vertices_m"]) for r in dressing.read(a.WORK/"dressing/flow-rocks.json")["rocks"]])
        for held in (hero,support,spring):
            if np.any(field.sample(*held[:,:2].T)!=old.sample(*held[:,:2].T)):
                raise ValueError("Geometry below a reserved hydraulic or bank support point moved")
        def bounds(binary):
            jj,ii=np.where(binary)
            return [axes[0][ii.min()],axes[1][jj.min()],axes[0][ii.max()],axes[1][jj.max()]]
        rows=[];px=np.arange(0,1600,2)
        for y,left,right in TRACE[2:12]:
            hit=a.intersect(px,y,line)[:,:2];valid=np.max(np.abs(hit),axis=1)<999.999
            native=intervals(px[valid],ray_water(field,px[valid],y,line))
            old_w=intervals(px[valid],ray_water(old,px[valid],y,line))
            rows.append(dict(y=int(y),target=[int(left),int(right)],native=max(native,key=lambda r:r[1]-r[0]),previous=max(old_w,key=lambda r:r[1]-r[0])))
        probes={}
        for tag,px0,y in [("west_submerged",281,440),("west_ridge",185,440),("eastern_shelf",1351,452),("eastern_rim",1440,452),
                          ("left_north_bank",360,420),("right_closure",1330,428),("lower_basin",430,508)]:
            point=a.intersect(float(px0),float(y),line)[:2]
            bed=field.sample(*point);old_bed=old.sample(*point)
            probes[tag]=dict(xy_m=point.round(5).tolist(),ground_z_m=round(float(bed),5),previous_bed_z_m=round(float(old_bed),5),
                             bed_above_local_water_m=round(float(bed-LEVEL),4))
        displaced=xy[np.abs(delta[area])>.05];global_xy=np.stack(np.meshgrid(*axes),axis=-1)
        margins={name:round(float(cKDTree(global_xy[base.masks[name]>.01]).query(displaced)[0].min()),2) for name in ("road","bases")}
        trees=np.array([r["position"][:2] for r in dressing.read(dressing.TREES)["instances"]])
        changed_trees=int(np.count_nonzero(np.abs(field.sample(*trees.T)-old.sample(*trees.T))>.01))
        if changed_trees:raise ValueError("A stock tree would need a native collision change")
        receipt=dict(schema="pwr-headwater-terrain-v1",parent_terrain_sha256=base.manifest_sha256,
            previous_erosion_sha256=old.manifest_sha256,runtime_manifest_sha256=field.manifest_sha256,
            geometry_sha256=head.sha256(gps),r16_sha256=head.sha256(master.with_suffix(".r16")),water_level_m=LEVEL,
            changed_bounds_m=bounds(changed),changed_vertices=int(changed.sum()),basin_changed_vertices_vs_previous=int(np.count_nonzero(delta)),
            basin_changed_bounds_vs_previous_m=bounds(delta!=0.),untouched_road_and_base_vertices=int(np.count_nonzero((base.masks["road"]>.01)|(base.masks["bases"]>.01))),
            closed_sill_containment_verified=True,rock_sill_wet_width_m=dressing.read(PREVIOUS/"headwater-terrain.receipt.json")["rock_sill_wet_width_m"],
            previous_connected_lake_area_m2=round(float(previous_wet.sum()*np.prod(field.spacing_m)),2),
            connected_lake_area_m2=round(float(fill.sum()*np.prod(field.spacing_m)),2),
            berm_max_fill_m=round(float(delta.max()),4),max_excavation_m=round(float(-delta.min()),4),
            unchanged_stock_tree_roots=len(trees),changed_stock_tree_roots=changed_trees,protected_terrain_margins_m=margins,
            apron_support_points_checked=len(support),obstacle_hull_vertices_checked=len(hero),
            spring_grade_reserved_points=len(spring),camera_rows=rows,native_probes=probes)
        head.save(staged/"headwater-terrain.receipt.json",receipt)
        if out.exists():
            if any(not (out/p.name).is_file() or head.sha256(out/p.name)!=head.sha256(p) for p in staged.iterdir()):
                raise ValueError("Different products at "+str(out))
        else:staged.rename(out)
    return receipt


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out",type=Path,default=OUT/"terrain")
    print(json.dumps(build(parser.parse_args().out.resolve()),indent=2))

