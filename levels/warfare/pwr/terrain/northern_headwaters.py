"""Build the northern headwater basin on the existing quantized playtest terrain."""
import argparse
import copy
import json
from pathlib import Path
import sys
import tempfile

import numpy as np
from scipy import ndimage

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
sys.path.insert(0, str(ROOT / "tools/level"))
from derive_runtime_heightfield import derive
from heightfield import load_heightfield, sha256, write_heightfield
from finalize_terrain import arclength, inside_polygon, nearest_line, smooth

BASE = HERE / "runtime-v5/runtime-master.json"
PLAN = HERE / "northern-headwaters.json"
OUTPUT = ROOT / "out/pwr/headwater-lake/terrain"


def save(path, result):
    path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")


def round_shore(points):
    # The same three corner-cutting passes as the dimensioned concept.
    poly = np.array(points, dtype=float)
    for _ in range(3):
        nxt = np.roll(poly, -1, axis=0)
        poly = np.stack((.75*poly+.25*nxt, .25*poly+.75*nxt), axis=1).reshape(-1, 2)
    return poly


def densify(line, step=.75):
    line = np.asarray(line)
    arc = arclength(line[:, :2])
    stations = np.unique(np.r_[np.arange(0., arc[-1], step), arc])
    return np.column_stack([np.interp(stations, arc, a) for a in line.T])


def line_fields(xx, yy, line):
    distance, i, t = nearest_line(np.c_[xx.ravel(), yy.ravel()], line)
    stations = arclength(line[:, :2])
    def blend(values):
        return (values[i]*(1-t) + values[i+1]*t).reshape(xx.shape)
    return distance.reshape(xx.shape), blend(stations), blend(line[:, 2])


def shore_distance(xx, yy, polygon):
    loop = densify(np.vstack((polygon, polygon[0])))
    delta, _, _ = nearest_line(np.c_[xx.ravel(), yy.ravel()], loop)
    return np.where(inside_polygon(xx, yy, polygon), 1., -1.)*delta.reshape(xx.shape)


def channel_surface(distance, width, depth, surface, bank_grade):
    half = width*.5
    inner = np.clip(distance/half, 0., 1.)
    return surface - depth*(1.-inner**1.65) + bank_grade*np.maximum(distance-half, 0.)


def geometry(base, plan):
    geo = copy.deepcopy(base)
    polygon = round_shore(plan["shore_controls_m"])
    main = next(c for c in geo["watercourses"] if c["id"] == "central_river")
    old = np.asarray(main["surface_centreline_m"])
    split = np.linalg.norm(old[:, :2]-plan["outlet_anchor_m"],axis=1).argmin()
    spill = old[split].copy()
    lake_z = plan["water_z_m"]
    if abs(spill[2]-lake_z) > .1:
        raise ValueError("The surveyed outlet missed the existing river profile")
    main_points = old[split:].copy()
    main_points[0, 2] = lake_z
    stations = arclength(main_points[:, :2])
    invert_uv = lambda points: ((np.asarray(points)[:, :2]*[1,-1]+1000.)/2000.).tolist()
    downstream_controls = [p for p in main["control_points_m"]
                           if np.linalg.norm(old[:, :2]-p,axis=1).argmin() > split]
    main["control_points_m"] = [spill[:2].tolist(), *downstream_controls]
    main["control_points_uv"] = invert_uv(main["control_points_m"])
    main["source"] = {"lake":"north_headwater_lake","position_m":main_points[0].tolist()}
    main["surface_centreline_m"] = main_points.tolist()
    main["section_station_width_depth_m"] = [s for s in plan["outlet_section_station_width_depth_m"] if s[0]>=0]
    samples = np.unique(np.r_[np.arange(0, len(stations), 12), len(stations)-1])
    main["relative_water_profile"] = np.c_[stations[samples]/stations[-1],
        (main_points[samples,2]-main_points[-1,2])/(lake_z-main_points[-1,2])].tolist()
    spring = densify(plan["spring_surface_m"])
    geo["watercourses"].append(dict(id="headwater_spring",control_points_m=spring[:,:2].tolist(),
        control_points_uv=invert_uv(spring),surface_centreline_m=spring.tolist(),flow_direction="listed_start_to_end",
        channel_width_m=plan["spring_width_m"],target_water_depth_m=plan["spring_depth_m"],bank_blend_m=5.0,
        source={"kind":"rock_spring","position_m":spring[0].tolist()},outlet="north_headwater_lake",cascades=[]))
    geo["lakes"].append(dict(id="north_headwater_lake",polygon_m=polygon.tolist(),polygon_uv=invert_uv(polygon),
        water_z_m=lake_z,shore_blend_m=plan["bank_blend_m"],islands=[],inlet_watercourse="headwater_spring",
        outlet={"watercourse":"central_river","position_m":main_points[0].tolist(),"width_m":10.0}))
    inlake = np.asarray(plan["outlet_approach_m"])
    neck = densify(np.vstack((np.c_[inlake, np.full(len(inlake), lake_z)], main_points[stations <= 98.])))
    neck_zero = arclength(neck[:,:2])[np.linalg.norm(neck[:,:2]-spill[:2],axis=1).argmin()]
    return geo, polygon, old, split, neck, neck_zero, spring


def outlet_coordinates(xx, yy, neck, neck_zero):
    """Metres along flow from sill and across flow toward the depositional bank."""
    samples = np.column_stack((xx.ravel(), yy.ravel()))
    distance, index, fraction = nearest_line(samples, neck)
    edge = neck[index+1, :2]-neck[index, :2]
    length = np.linalg.norm(edge,axis=1)
    tangent = edge/length[:,None]
    delta = samples-(neck[index,:2]+edge*fraction[:,None])
    side = -tangent[:,1]*delta[:,0]+tangent[:,0]*delta[:,1]
    arc = arclength(neck[:,:2])
    along = arc[index]+fraction*length-neck_zero
    # Extend the station coordinate off the endpoints so feather weights
    # fall to zero behind the head of the neck.
    along += np.where((index==0)|(index==len(neck)-2),np.sum(delta*tangent,axis=1),0.)
    return along.reshape(xx.shape),side.reshape(xx.shape)


def erode_outlet(ground, xx, yy, inside, previous_wet, previous_shore, water, neck, neck_zero, plan):
    z = plan["water_z_m"]
    # Submerged terraces are broad enough for the native 1.98 m terrain grid.
    # Offset their edge along the bank. Each fades into the deep, quiet basin.
    shelf_weight = np.maximum(
        np.exp(-((xx+302)/19.)**2-((yy-859)/34.)**2),
        np.exp(-((xx+351)/36.)**2-((yy-851)/16.)**2))
    shore_fold = .70*np.sin((xx+.56*yy)/5.)+.38*np.sin((yy-.27*xx)/3.2)
    bank_distance = inside+shore_fold
    terrace = np.interp(bank_distance,[-13,-5,-1,0,3.5,7.5,10,14,22],
                        [1.9,.83,.20,0,-.27,-.44,-.73,-1.35,-3.4])
    shelf_weight *= smooth((bank_distance+11.)/7.)*(1.-smooth((bank_distance-11.)/10.))
    ground += shelf_weight*(z+terrace-ground)

    along, side = outlet_coordinates(xx,yy,neck,neck_zero)
    section = np.array(plan["outlet_section_station_width_depth_m"])
    width = np.interp(along,section[:,0],section[:,1])
    depth = np.interp(along,section[:,0],section[:,2])
    reach = smooth((along+22.)/12.)*(1.-smooth((along-44.)/19.))
    # A scalloped outer cut and an elongated point bar occupy opposite banks.
    # Saltation lobes feather into a cobble shelf below the local water plane.
    cut = -.5*width-1.2-.9*np.sin(along*.19)-.48*np.sin(along*.53+.7)
    bar = .5*width+1.45*np.cos(along*.15+.4)-.72*np.sin(along*.31)
    u = np.clip((side-cut)/(bar-cut),0.,1.)
    dry = np.maximum(cut-side,0.)
    cut_height = np.interp(dry,[0,1.1,2.5,4.6,8.,18.],[0,.63,1.65,2.1,2.45,3.1])
    scoured = -depth*(.58+.66*np.exp(-((u-.26)/.21)**2))*np.minimum((side-cut)/2.5,1.)
    shelf_toe = .26+.07*np.sin(along*.14+.4)
    bar_bed = np.interp(u,[0,.36,.5,.61,.78,1.],[0,-.91,-.61,-.39,-.29,0.])
    bar_bed += .08*np.sin(along*.27+u*8.)*np.sin(u*np.pi)
    wetted = scoured + smooth((u-shelf_toe)/.26)*(bar_bed-scoured)
    bar_height = np.interp(side-bar,[0.,4.,9.,15.],[0.,.38,1.,1.6])
    profile = np.where(side<cut,cut_height,np.where(side>bar,bar_height,wetted))
    beyond = np.maximum.reduce([cut-side, side-bar, np.zeros_like(side)])
    reach *= 1.-smooth((beyond-6.)/10.)
    # Preserve the existing sill cross-section while introducing an offset
    # scour pool, the graded bar, and a taller grassy bank on either side.
    sill = smooth((np.abs(along)-2.8)/4.5)
    sill_weight = np.maximum(sill, smooth((beyond-2.)/3.))
    weight = reach*sill_weight
    ground += weight*(water+profile-ground)
    coverage = np.maximum(reach,shelf_weight)
    surface = np.where(reach>.001,water,z)
    wet = np.where(coverage>.005,ground<surface,previous_wet)
    # Drier, elevated edges stop qualifying as riparian vegetation exclusion.
    shore = previous_shore+coverage*(1.-smooth(np.abs(ground-surface)/2.7)-previous_shore)
    return ground,wet,shore,coverage


def sculpt(field, plan, polygon, old, split, neck, neck_zero, spring, erosion=False):
    axis = [np.arange(n)*d+o for n,d,o in zip(field.dimensions,field.spacing_m,field.origin_m)]
    points = np.vstack((polygon, neck[:,:2], spring[:,:2]))
    low, high = points.min(axis=0)-42., points.max(axis=0)+42.
    slices = [slice(np.searchsorted(a,l),np.searchsorted(a,h,side="right")) for a,l,h in zip(axis,low,high)]
    area = tuple(slices[::-1])
    xx, yy = np.meshgrid(axis[0][slices[0]],axis[1][slices[1]])
    previous = field.heights_m[area]
    inside = shore_distance(xx,yy,polygon)
    outside = np.maximum(-inside,0.)
    z = plan["water_z_m"]
    # The eastern beach has a gentle shelf. Across the basin, steeper rock cuts
    # descend into a pool whose deepest part is set back from the outlet.
    sx,sy = plan["shelf_centre_m"]
    shelf = np.exp(-((xx-sx)/34.)**2-((yy-sy)/41.)**2)
    deep = 6.15 + .64*np.exp(-((xx+378.)/34.)**2-((yy-916.)/24.)**2)
    lake_depth = deep*(1.-np.exp(-np.maximum(inside,0.)/(11.+19.*shelf)))
    bank_grade = .25-.115*shelf
    shore_target = z-lake_depth+outside*bank_grade
    lake_weight = 1.-smooth((outside-3.)/(plan["bank_blend_m"]-3.))
    ground = previous + lake_weight*(shore_target-previous)
    is_wet = inside >= 0
    shore = 1.-smooth(np.abs(inside)/15.)

    # The upstream river used to be full width. Fill the old margins to keep
    # the new sill to one opening, then rejoin its exact grade downstream.
    nc, ns, water = line_fields(xx,yy,neck)
    ns -= neck_zero
    section = np.asarray(plan["outlet_section_station_width_depth_m"])
    width = np.interp(ns,section[:,0],section[:,1])
    depth = np.interp(ns,section[:,0],section[:,2])
    river_target = channel_surface(nc,width,depth,water,.23)
    river_target = np.where(is_wet,np.minimum(river_target,ground),river_target)
    wrap = 1.-smooth((nc-width/2.-3.)/17.)
    end = plan["main_join_end_station_m"]
    blend_out = 1.-smooth((ns-38.)/(end-38.))
    river_weight = wrap*blend_out
    ground += river_weight*(river_target-ground)
    is_wet |= nc < width/2.
    shore = np.maximum(shore,1.-smooth(np.abs(nc-width/2.)/12.))

    # A narrow feeder carves back into the north shore, with open banks at
    # its toe so its bed cannot form a dam across the lake.
    sc, ss, spring_surface = line_fields(xx,yy,spring)
    spring_width = plan["spring_width_m"]
    spring_depth = plan["spring_depth_m"]
    spring_target = channel_surface(sc,spring_width,spring_depth,spring_surface,.32)
    spring_target = np.where(inside>0,np.minimum(spring_target,ground),spring_target)
    spring_weight = 1.-smooth((sc-spring_width/2.)/5.)
    ground += spring_weight*(spring_target-ground)
    is_wet |= sc < spring_width/2.
    shore=np.maximum(shore,1.-smooth(np.abs(sc-spring_width/2.)/6.))
    erosion_coverage = 0.
    if erosion:
        ground,is_wet,shore,erosion_coverage=erode_outlet(ground,xx,yy,inside,is_wet,shore,water,neck,neck_zero,plan)

    # Clear fragments of the retired wide river mask within its old upper reach.
    old_line=densify(old[:split+1])
    old_distance,_,_=line_fields(xx,yy,old_line)
    old_mask_update=1.-smooth((old_distance-16.)/10.)
    water_influence=np.maximum.reduce([lake_weight,river_weight,spring_weight,old_mask_update])
    water_influence=np.maximum(water_influence,erosion_coverage)
    # At the downstream join, preserve the original wet/shore masks exactly.
    wet_mask=field.masks["water"][area]*(1.-water_influence)+is_wet*water_influence
    shore_mask=field.masks["shore"][area]*(1.-water_influence)+shore*water_influence
    full=field.heights_m.copy()
    full[area]=ground
    masks={k:v.copy() for k,v in field.masks.items()}
    masks["water"][area]=wet_mask
    masks["shore"][area]=shore_mask
    masks["forest"][area]*=1.-np.clip(np.maximum(wet_mask,.80*shore_mask)*water_influence,0,1)
    slope_y,slope_x=np.gradient(full,*field.spacing_m[::-1])
    local=(water_influence>0)|(np.abs(ground-previous)>1.e-7)
    masks["walkable"][area]=np.where(local,(np.hypot(slope_x[area],slope_y[area])<=.35)&(wet_mask<.5),masks["walkable"][area])
    for name in ("protected","protected_core"):
        masks[name][area]=np.maximum(masks[name][area],(lake_weight>0)|(river_weight>0)|(spring_weight>0))
    return full,masks,area,xx,yy,inside


def verify(result, base, geo, polygon, old, split, spring, area, xx, yy, inside, level):
    new_lake=geo["lakes"][-1]
    old_geo=json.loads((base.path.parent/base.metadata["geometry"]).read_text())
    if geo["lakes"][:-1]!=old_geo["lakes"] or any(geo[key]!=old_geo[key] for key in ("roads","sites","crossings","nodes")):
        raise ValueError("Existing gameplay or lake geometry changed")
    if not np.array_equal(np.asarray(geo["watercourses"][0]["surface_centreline_m"])[1:],old[split+1:]):
        raise ValueError("Existing river profile changed below the outlet")
    if geo["watercourses"][1]!=old_geo["watercourses"][1]:
        raise ValueError("Western braid changed")
    delta=result.heights_m-base.heights_m
    changed=delta!=0
    nominal=delta[area]
    if np.count_nonzero(changed)!=np.count_nonzero(nominal) or not np.any(changed):
        raise ValueError("Terrain edit exceeds the headwater bounds or is empty")
    if any(np.any(changed & (base.masks[k]>.01)) for k in ("road","bases")):
        raise ValueError("Headwater modified a base pad or road")
    # Seal the intended outlet with a short cross-section for this test only.
    # Flood the actual quantized mesh raster and require all edges to remain dry.
    cap0=np.array([-299.82,816.27])
    downstream=(old[split+1,:2]-old[split-1,:2])
    downstream/=np.linalg.norm(downstream)
    dist_along=(xx-cap0[0])*downstream[0]+(yy-cap0[1])*downstream[1]
    dist_side=(xx-cap0[0])*(-downstream[1])+(yy-cap0[1])*downstream[0]
    flooded=(result.heights_m[area]<level-.025) & ~((np.abs(dist_along)<2.5)&(np.abs(dist_side)<16.))
    cc,_=ndimage.label(flooded,np.ones((3,3)))
    core=np.unravel_index(np.argmin((xx+360.)**2+(yy-900.)**2),xx.shape)
    fill=cc==cc[core]
    if not cc[core] or np.any(fill[[0,-1],:]) or np.any(fill[:,[0,-1]]) or np.any(fill&(inside < -18.)):
        raise ValueError(f"Lake can spill outside the outlet; most distant connected water {-inside[fill].min():.2f} m")
    # Test the open cross section on native triangle elevations every quarter metre.
    side=np.arange(-24.,24.01,.25)
    normal=np.array([-downstream[1],downstream[0]])
    xy=cap0+side[:,None]*normal
    sill=level-result.sample(xy[:,0],xy[:,1])
    runs,count=ndimage.label(sill>.05)
    wi=runs[np.argmin(np.abs(side))]
    if not wi or count!=1 or not 7<=np.count_nonzero(runs==wi)*.25<=13:
        raise ValueError(f"Unexpected sill width: components={count}, wet width={np.count_nonzero(runs==wi)*.25}")
    spring_depth=spring[:,2]-result.sample(*spring[:,:2].T)
    central=np.asarray(geo["watercourses"][0]["surface_centreline_m"])[:70]
    first_depth=central[:,2]-result.sample(*central[:,:2].T)
    if min(spring_depth.min(),first_depth.min())<.08:
        raise ValueError(f"A watercourse is obstructed: {spring_depth.min()=}, {first_depth.min()=}")
    iy,ix=np.where(changed); x0,y0=base.origin_m; dx,dy=base.spacing_m
    return dict(changed_vertices=int(changed.sum()),changed_bounds_m=[x0+ix.min()*dx,y0+iy.min()*dy,x0+ix.max()*dx,y0+iy.max()*dy],
                height_change_m=[float(delta.min()),float(delta.max())],shoreline_area_m2=abs(float(np.sum(polygon[:,0]*np.roll(polygon[:,1],-1)-polygon[:,1]*np.roll(polygon[:,0],-1))*.5)),
                contained_lake_component_m2=float(fill.sum()*dx*dy),rock_sill_wet_width_m=float((runs==wi).sum()*.25),
                minimum_lake_bed_m=new_lake["floor_z_m"],sill_depth_at_centre_m=float(sill[np.argmin(np.abs(side))]),
                minimum_spring_centre_depth_m=float(spring_depth.min()),minimum_upper_channel_centre_depth_m=float(first_depth.min()),
                untouched_road_and_base_vertices=int(np.count_nonzero((base.masks["road"]>.01)|(base.masks["bases"]>.01))),
                closed_sill_containment_verified=True,original_downstream_surface_samples_retained=int(len(old)-split-1))


def build(out, erosion=False):
    out=Path(out).resolve()
    out.parent.mkdir(parents=True,exist_ok=True)
    field=load_heightfield(BASE)
    plan=json.loads(PLAN.read_text())
    parent_geometry=field.path.parent/field.metadata["geometry"]
    if sha256(parent_geometry)!=field.metadata["geometry_sha256"]:
        raise ValueError("Runtime master references different geometry")
    geo,poly,prior,split,neck,zero,spring=geometry(json.loads(parent_geometry.read_text()),plan)
    heights,masks,area,xx,yy,inside=sculpt(field,plan,poly,prior,split,neck,zero,spring,erosion)
    if erosion:
        geo["watercourses"][0]["erosion_reach"] = dict(
            station_origin_m=neck[np.argmin(np.abs(arclength(neck[:,:2])-zero)),:2].tolist(),
            centreline_m=neck.tolist(),sill_station_m=float(zero),extent_from_sill_m=[-22.,63.],
            positive_side="depositional gravel bar",negative_side="scoured cut bank")
    lake=geo["lakes"][-1]
    lake["floor_z_m"]=round(float(np.min(heights[area][inside>0])),3)
    lake["target_depth_m"]=[0,round(lake["water_z_m"]-lake["floor_z_m"],3)]
    with tempfile.TemporaryDirectory(dir=out.parent,prefix=".headwater-") as temp:
        staged=Path(temp)/"terrain"
        staged.mkdir()
        gp=staged/"terrain.geometry.json"
        save(gp,geo)
        source=staged/"authoring-master.json"
        write_heightfield(source,heights,field.origin_m,field.spacing_m,masks,
            generator="northern_headwaters.py", geometry=gp.name,geometry_sha256=sha256(gp),
            water_level_m=field.metadata["water_level_m"],surface_interpolation="triangle_nw_se",
            parent_runtime_manifest_sha256=sha256(BASE),headwater_plan_sha256=sha256(PLAN),
            landscape_encoding_policy=field.metadata["landscape_encoding_policy"])
        master=staged/"runtime-master.json"
        derive(source,master,components=field.metadata["landscape_encoding"]["components"])
        result=load_heightfield(master)
        proof=verify(result,field,geo,poly,prior,split,spring,area,xx,yy,inside,plan["water_z_m"])
        receipt=dict(schema="pwr-headwater-terrain-v1",parent_terrain_sha256=field.manifest_sha256,
                     runtime_manifest_sha256=sha256(master),geometry_sha256=sha256(gp),
                     r16_sha256=sha256(master.with_suffix(".r16")),water_level_m=plan["water_z_m"],**proof)
        save(staged/"headwater-terrain.receipt.json",receipt)
        if out.exists():
            # A rerun may overlap another consumer reading the published set.
            # Keep identical products stable and never replace a changed build in place.
            if any(not (out/p.name).exists() or sha256(p)!=sha256(out/p.name) for p in staged.iterdir()):
                raise ValueError(f"{out} contains different results; specify a new --out directory")
        else:
            staged.rename(out)
    return receipt


if __name__=="__main__":
    cli=argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--out",type=Path,default=OUTPUT)
    cli.add_argument("--erosion",action="store_true",help="Sculpt asymmetric outlet banks and underwater shelves")
    args=cli.parse_args()
    print(json.dumps(build(args.out,args.erosion),indent=2))
