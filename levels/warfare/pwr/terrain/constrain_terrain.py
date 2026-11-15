"""Replace macro relief while retaining the tested terrain/geometry contract.

The reference is the exact, quantized Unreal runtime grid. New Gaea relief is
sampled onto that grid once; no sine hills, basin compression or road Z solver
is used. A harmonic displacement joins it to the protected reference samples.
Outputs are candidates until independent native collision and live checks pass.
"""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import sys

import numpy as np
from scipy.ndimage import binary_dilation, binary_propagation, distance_transform_edt
from scipy.sparse.linalg import cg

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
sys.path.insert(0,str(ROOT/"tools/level"))
from heightfield import Heightfield, load_heightfield, write_heightfield, sha256
from build_landscape import encode_master_heights
from derive_runtime_heightfield import preservation_report


class TerrainFitError(ValueError):
    def __init__(self,message,heights,report):
        super().__init__(message)
        self.heights=heights
        self.report=report


def smoother(t):
    t=np.clip(t,0,1)
    return t*t*t*(t*(t*6-15)+10)


def lock_sample_cells(mask, field, points):
    """Lock all four vertices supporting a sample, including diagonal edges."""
    points=np.asarray(points,dtype=float).reshape(-1,3)
    if not len(points):return
    field.sample(points[:,0],points[:,1])  # Finite/bounds validation.
    ij=np.floor((points[:,:2]-field.origin_m)/field.spacing_m).astype(int)
    ij=np.minimum(ij,np.array(field.dimensions)-2)
    for dx,dy in ((0,0),(1,0),(0,1),(1,1)):
        mask[ij[:,1]+dy,ij[:,0]+dx]=True


def protected_mask(baseline, geometry, layout, collar_cells=2):
    """Pin lanes+shoulders, foundations, water beds/near shore and support cells."""
    if type(collar_cells) is not int or collar_cells<2:
        raise ValueError("At least two protected interpolation collar cells are required")
    masks=baseline.masks
    required={"road":.001,"bases":.5,"flat":.5,"water":.01,"shore":.5}
    if not required.keys()<=masks.keys():raise ValueError("Baseline is missing required gameplay masks")
    result=np.zeros(baseline.heights_m.shape,dtype=bool)
    counts={}
    for name,threshold in required.items():
        selected=masks[name]>threshold
        counts[name]=int(selected.sum());result|=selected
    # Some already-tested engineered banks connect a high road to a low lake
    # over a narrow gap. Their accepted slope cannot be recreated by a .75
    # correction-grade cap on a nearly flat new Gaea field. Preserve ONLY the
    # existing steep part of bounded road/water gaps, then keep the normal gate
    # outside its interpolation collar. This does not capture remote mountains.
    water_distance=distance_transform_edt(masks["water"]<=.5,sampling=baseline.spacing_m[::-1])
    road_distance=distance_transform_edt(masks["road"]<=.001,sampling=baseline.spacing_m[::-1])
    dy,dx=np.gradient(baseline.heights_m,*baseline.spacing_m[::-1])
    old_grade=np.hypot(dx,dy)
    bank=((water_distance+road_distance<=80)&(water_distance<=60)&(road_distance<=60)&(old_grade>.35))
    bank_added=int((bank&~result).sum())
    result|=bank
    points=[]
    for road in geometry["roads"]:
        line=np.asarray(road["centreline_m"])
        sections=np.asarray(road["cross_sections_m"])
        # Elevated deck geometry stays immutable. Its supports/abutments retain
        # terrain; locking terrain to deck heights would create an earthen dam.
        points.extend((sections[[0,-1]] if road.get("structure") else sections).reshape(-1,3))
        if not road.get("structure"):points.extend(line)
    for river in geometry["watercourses"]:points.extend(river["surface_centreline_m"])
    points.extend(site["position_m"] for site in geometry["sites"])
    points.extend(layout["homes_m"].values())
    points.extend(layout["captures_m"])
    points.append(layout["warmup_m"])
    for starts in layout["spawns_m"].values():points.extend(starts)
    vehicle_count=0
    if {"red_home","blue_home"}<={site["id"] for site in geometry["sites"]}:
        sys.path.insert(0,str(HERE.parent))
        from world_placements import placements
        authored=placements(layout,geometry,baseline)
        points.extend(p["position_m"] for p in authored["pickups"])
        yy,xx=np.indices(result.shape)
        gx=baseline.origin_m[0]+xx*baseline.spacing_m[0]
        gy=baseline.origin_m[1]+yy*baseline.spacing_m[1]
        for vehicle in authored["vehicles"]:
            px,py,pz=vehicle["position_m"]
            result|=(gx-px)**2+(gy-py)**2<=12**2
            points.append([px,py,pz]);vehicle_count+=1
    lock_sample_cells(result,baseline,points)
    result=binary_dilation(result,structure=np.ones((3,3),bool),iterations=collar_cells)
    return result,{"thresholds":required,"vertices_by_mask":counts,"collar_cells":collar_cells,
                   "support_points":len(points),"vehicle_support_discs":vehicle_count,
                   "vehicle_support_radius_m":12,"protected_vertices":int(result.sum()),
                   "protected_fraction":float(result.mean()),
                   "engineered_bank":{"source":"immutable baseline", "maximum_road_water_gap_m":80,
                       "maximum_distance_to_each_m":60,"minimum_existing_grade":.35,
                       "selected_vertices":int(bank.sum()),"additional_vertices_before_collar":bank_added}}


def compatibility_collar(baseline, new, protected, failed_heights, original,
                         maximum_m=12., target_grade=.75, bank_maximum_m=24.):
    """Grow only *measured* failing first-ring clusters, within original12m cap."""
    distance=distance_transform_edt(~original,sampling=baseline.spacing_m[::-1])
    current_distance=distance_transform_edt(~protected,sampling=baseline.spacing_m[::-1])
    dy,dx=np.gradient(failed_heights-new,*baseline.spacing_m[::-1]);grade=np.hypot(dx,dy)
    first=(current_distance>0)&(current_distance<=2*max(baseline.spacing_m))
    incompatible=first&(grade>target_grade)
    extra=binary_dilation(incompatible,structure=np.ones((3,3),bool))&~protected&(distance<=maximum_m)
    # Root-reviewed exception: measured bank failures may follow their already
    # existing steep face to its gentle toe/rim, first24m then at most40m.
    # This never enlarges the distant NE road or a global collar.
    water=distance_transform_edt(baseline.masks["water"]<=.5,sampling=baseline.spacing_m[::-1])
    road=distance_transform_edt(baseline.masks["road"]<=.001,sampling=baseline.spacing_m[::-1])
    by,bx=np.gradient(baseline.heights_m,*baseline.spacing_m[::-1])
    steep=np.hypot(bx,by)>.35
    bank_near=(water<=100)&(road<=100)
    seeds=incompatible&steep&bank_near
    bank_added=np.zeros_like(protected)
    if seeds.any():
        seed_distance=distance_transform_edt(~seeds,sampling=baseline.spacing_m[::-1])
        permitted=bank_near&(distance<=bank_maximum_m)&(seed_distance<=60)
        connected=binary_propagation(seeds&permitted,structure=np.ones((3,3),bool),mask=steep&permitted)
        bank_added=binary_dilation(connected,structure=np.ones((3,3),bool))&permitted&~protected
        extra|=bank_added
    protected=protected|extra
    added=protected&~original
    from scipy.ndimage import label,find_objects
    labels,_=label(added,structure=np.ones((3,3),bool));regions=[]
    for index,region in enumerate(find_objects(labels),1):
        yy,xx=np.nonzero(labels[region]==index);yy+=region[0].start;xx+=region[1].start
        regions.append({"vertices":len(xx),"bounds_m":[
            [baseline.origin_m[0]+float(xx.min())*baseline.spacing_m[0],baseline.origin_m[1]+float(yy.min())*baseline.spacing_m[1]],
            [baseline.origin_m[0]+float(xx.max())*baseline.spacing_m[0],baseline.origin_m[1]+float(yy.max())*baseline.spacing_m[1]]]})
    return protected,{"maximum_extension_m":maximum_m,"compatibility_target_grade":target_grade,
        "bank_maximum_extension_m":bank_maximum_m,"bank_seed_neighbourhood_m":60,
        "bank_added_this_attempt":int(bank_added.sum()),"bank_existing_grade_threshold":.35,
        "original_vertices":int(original.sum()),"added_vertices":int(added.sum()),
        "actual_max_extension_m":float(distance[added].max()) if added.any() else 0.,
        "original_mask_sha256":hashlib.sha256(original.tobytes()).hexdigest(),
        "final_mask_sha256":hashlib.sha256(protected.tobytes()).hexdigest(),"regions":regions}


def boundary_grade_report(heights, baseline, protected, spacing):
    changes=[];previous=[]
    for axis,step in ((0,spacing[1]),(1,spacing[0])):
        for direction in (-1,1):
            boundary=protected&~np.roll(protected,-direction,axis)&np.roll(protected,direction,axis)
            edge=[slice(None),slice(None)];edge[axis]=0;boundary[tuple(edge)]=False
            edge[axis]=-1;boundary[tuple(edge)]=False
            for field,values in ((heights,changes),(baseline,previous)):
                change=(np.roll(field,-direction,axis)-2*field+np.roll(field,direction,axis))/step
                values.append(np.abs(change[boundary]))
    current=np.concatenate(changes);old=np.concatenate(previous)
    return {"sampled_boundary_edges":len(current),"max_normal_grade_change":float(current.max(initial=0)),
            "p95_normal_grade_change":float(np.percentile(current,95)) if len(current) else 0.,
            "baseline_max_normal_grade_change":float(old.max(initial=0)),
            "baseline_p95_normal_grade_change":float(np.percentile(old,95)) if len(old) else 0.,
            "scope":"Adjacent finite-difference normal grades after R16 quantization; not a literal C1 claim for triangle terrain"}


def biharmonic_blend(new_heights, reference, protected, spacing, blend_m=180.0,
                     max_correction_grade=.75):
    """Minimum-curvature displacement with fixed near/far samples.

    B is the full-grid Laplacian restricted to unknown columns. Minimizing
    ||L*displacement||^2 gives B.T*B, including adjacent *fixed* rows. Those
    boundary rows constrain the derivative, unlike a Dirichlet-only harmonic
    solve. Only protected old samples enter the system; unprotected old relief
    cannot be copied into the replacement landscape.
    """
    from scipy import sparse
    import pyamg
    new=np.asarray(new_heights,dtype=float);old=np.asarray(reference,dtype=float)
    protected=np.asarray(protected,dtype=bool)
    if new.shape!=old.shape or new.shape!=protected.shape or not protected.any():
        raise ValueError("Matching nonempty protected terrain grids are required")
    if not np.isfinite(new).all() or not np.isfinite(old).all():raise ValueError("Terrain must be finite")
    if not np.isfinite(blend_m) or blend_m<4*max(spacing):raise ValueError("Blend width must span at least four cells")
    if not np.isfinite(max_correction_grade) or max_correction_grade<=0:raise ValueError("Positive correction grade required")
    distance=distance_transform_edt(~protected,sampling=spacing[::-1]);unknown=(distance>0)&(distance<blend_m)
    displacement=np.where(protected,old-new,0.);count=int(unknown.sum());iterations=0;residual=0.;levels=0
    if count:
        n=new.size;h,w=new.shape
        horizontal=np.ones(n-1)/spacing[0]**2;horizontal[np.arange(1,n)%w==0]=0
        vertical=np.ones(n-w)/spacing[1]**2
        diagonal=np.zeros(n);diagonal[:-1]+=horizontal;diagonal[1:]+=horizontal
        diagonal[:-w]+=vertical;diagonal[w:]+=vertical
        laplace=sparse.diags([-vertical,-horizontal,diagonal,-horizontal,-vertical],[-w,-1,0,1,w],format="csr")
        columns=laplace[:,unknown.ravel()].tocsr();matrix=(columns.T@columns).tocsr()
        rhs=-columns.T@(laplace@displacement.ravel())
        # Fixed initial vectors make AMG's aggregation reproducible. Avoid
        # changing NumPy's global RNG used by unrelated authoring tools.
        state=np.random.get_state()
        try:
            np.random.seed(20569)
            preconditioner=pyamg.smoothed_aggregation_solver(matrix,symmetry="symmetric",max_coarse=500)
        finally:np.random.set_state(state)
        levels=len(preconditioner.levels)
        def step(_):
            nonlocal iterations
            iterations+=1
        solved,info=cg(matrix,rhs,rtol=1e-8,atol=1e-9,maxiter=1800,M=preconditioner.aspreconditioner(),callback=step)
        if info!=0:raise ValueError(f"Terrain curvature solve did not converge ({info})")
        residual=float(np.max(np.abs(matrix@solved-rhs)));displacement[unknown]=solved
    result=new+displacement;result[protected]=old[protected]
    dy,dx=np.gradient(displacement,*spacing[::-1]);grade=np.hypot(dx,dy)
    correction_grade=float(grade[unknown].max()) if unknown.any() else 0.
    far=distance>=blend_m
    if not np.array_equal(result[protected],old[protected]) or not np.array_equal(result[far],new[far]):
        raise AssertionError("Protected terrain or untouched macro relief changed")
    report={"method":"biharmonic minimum-curvature displacement with fixed boundary rows",
        "blend_m":blend_m,"solver_unknowns":count,"solver_iterations":iterations,"solver_max_residual":residual,
        "solver_amg_levels":levels,"max_correction_grade":correction_grade,"correction_grade_limit":max_correction_grade,
        "max_earthwork_m":float(np.abs(displacement).max()),"far_field_vertices":int(far.sum()),
        "far_field_max_error_m":0.,"protected_max_abs_error_m":0.}
    if correction_grade>max_correction_grade+1e-8:
        iy,ix=np.unravel_index(np.where(unknown,grade,-1).argmax(),grade.shape)
        report["worst_grid_xy"]=[int(ix),int(iy)]
        raise TerrainFitError(f"Terrain blend adds grade {correction_grade:.4f}, above {max_correction_grade:.4f} "
                              f"at grid ({ix},{iy}); inspect boundary compatibility",result,report)
    return result,report


def limit_boundary_grade(heights, sampled, protected, spacing, blend_m, gate=.75):
    """Project only offending free stencils; exact protected/far samples stay fixed."""
    original=np.asarray(heights,dtype=float);delta=original-sampled
    distance=distance_transform_edt(~protected,sampling=spacing[::-1]);free=(distance>0)&(distance<blend_m)
    dy,dx=np.gradient(delta,*spacing[::-1]);bad=free&(np.hypot(dx,dy)>gate)
    if not bad.any():return original,{"iterations":0,"changed_vertices":0,"max_height_adjustment_m":0.}
    locality=distance_transform_edt(~bad,sampling=spacing[::-1])<=12
    editable=free&locality;affected=binary_dilation(editable,structure=np.ones((3,3),bool))&free
    target=gate-.01;h,w=delta.shape
    for iteration in range(2000):
        gy,gx=np.gradient(delta,*spacing[::-1]);grade=np.hypot(gx,gy);active=affected&(grade>target+1e-7)
        if not active.any():break
        yy,xx=np.nonzero(active)
        if ((xx==0)|(yy==0)|(xx==w-1)|(yy==h-1)).any():raise ValueError("Boundary projection cannot alter world-edge stencils")
        xp=editable[yy,xx+1];xm=editable[yy,xx-1];yp=editable[yy+1,xx];ym=editable[yy-1,xx]
        nx=xp.astype(int)+xm;ny=yp.astype(int)+ym
        fixed=np.where(nx==0,gx[yy,xx]**2,0)+np.where(ny==0,gy[yy,xx]**2,0)
        if np.any(fixed>=target**2):raise ValueError("Protected gradient is incompatible with local projection")
        magnitude=np.sqrt(np.where(nx>0,gx[yy,xx]**2,0)+np.where(ny>0,gy[yy,xx]**2,0))
        factor=np.sqrt(target**2-fixed)/np.maximum(magnitude,1e-20)
        dgx=gx[yy,xx]*(factor-1);dgy=gy[yy,xx]*(factor-1)
        updates=np.zeros_like(delta);counts=np.zeros_like(delta)
        for y,x,ok,change in ((yy,xx+1,xp,2*spacing[0]*dgx/np.maximum(nx,1)),
                             (yy,xx-1,xm,-2*spacing[0]*dgx/np.maximum(nx,1)),
                             (yy+1,xx,yp,2*spacing[1]*dgy/np.maximum(ny,1)),
                             (yy-1,xx,ym,-2*spacing[1]*dgy/np.maximum(ny,1))):
            np.add.at(updates,(y[ok],x[ok]),change[ok]);np.add.at(counts,(y[ok],x[ok]),1)
        delta+=.8*updates/np.maximum(counts,1)
    else:raise ValueError("Local boundary projection did not converge")
    result=sampled+delta;result[~editable]=original[~editable]
    change=result-original;maximum=float(np.abs(change).max());changed=int((np.abs(change)>1e-5).sum())
    gy,gx=np.gradient(result-sampled,*spacing[::-1]);actual=float(np.hypot(gx,gy)[free].max())
    if actual>gate+1e-8 or maximum>1 or changed>5000:
        raise ValueError(f"Local boundary correction exceeds its budget: grade={actual}, delta={maximum}, vertices={changed}")
    return result,{"iterations":iteration,"changed_vertices":changed,"max_height_adjustment_m":maximum,
                   "maximum_locality_m":12,"internal_grade_target":target,"max_correction_grade":actual,
                   "protected_and_far_samples_unchanged":True}


def constrain(source_path, baseline_path, layout_path, output, blend_m=180.0,
              max_correction_grade=.75, maximum_terrain_m=400.0, resume_fit=None):
    from finalize_terrain import validate_geometry
    source=load_heightfield(source_path);baseline=load_heightfield(baseline_path)
    output=Path(output).resolve();layout_path=Path(layout_path).resolve()
    if output.parent in (source.path.parent,baseline.path.parent) or output==source.path or output==baseline.path:
        raise ValueError("Constrained outputs must use a new isolated directory")
    if not np.allclose(source.bounds_m,baseline.bounds_m,rtol=0,atol=1e-8):
        raise ValueError("Replacement Gaea bounds must match the protected world exactly")
    if baseline.metadata.get("surface_interpolation")!="triangle_nw_se":
        raise ValueError("Preservation baseline must be an exact runtime triangle surface")
    encoding=baseline.metadata["landscape_encoding"]
    fixed={"mode":"fixed",**{k:encoding[k] for k in ("centre_cm","z_scale","components","size","origin_cm","quad_cm")}}
    geometry_path=(baseline.path.parent/baseline.metadata["geometry"]).resolve()
    if output.parent==geometry_path.parent:
        raise ValueError("Constrained outputs must not overwrite the frozen geometry directory")
    geometry_bytes=geometry_path.read_bytes();geometry_hash=hashlib.sha256(geometry_bytes).hexdigest()
    if geometry_hash!=baseline.metadata["geometry_sha256"]:raise ValueError("Baseline geometry hash mismatch")
    layout_hash=sha256(layout_path)
    geometry=json.loads(geometry_bytes);layout=json.loads(layout_path.read_text(encoding="utf-8-sig"))
    mask,protection=protected_mask(baseline,geometry,layout)
    sampled=source.resample_grid(baseline.dimensions)
    core_mask=mask.copy();collar=None;fit_attempts=[]
    try:
        if resume_fit is not None:
            resume_fit=Path(resume_fit).resolve();previous=json.loads(resume_fit.with_suffix(".json").read_text())
            data=np.load(resume_fit,allow_pickle=False)
            if (previous["source_manifest_sha256"]!=source.manifest_sha256 or previous["baseline_manifest_sha256"]!=baseline.manifest_sha256
                    or previous["geometry_sha256"]!=geometry_hash or not np.array_equal(data["protected_core"],core_mask)):
                raise ValueError("Rejected fit cache does not match immutable inputs/core mask")
            mask=data["protected"].astype(bool)
            distance=distance_transform_edt(~core_mask,sampling=baseline.spacing_m[::-1])
            if np.any(core_mask&~mask) or np.any(mask&~core_mask&(distance>40)):
                raise ValueError("Rejected fit cache exceeds approved protection scope")
            heights=data["heights"].astype(float)
            if not np.array_equal(heights[mask],baseline.heights_m[mask]):raise ValueError("Cached protected heights changed")
            heights,local=limit_boundary_grade(heights,sampled,mask,baseline.spacing_m,blend_m,max_correction_grade)
            blend={**previous["blend"],"local_derivative_projection":local,"resumed_fit_sha256":sha256(resume_fit),
                   "resumed_receipt_sha256":sha256(resume_fit.with_suffix(".json")),"max_correction_grade":local.get("max_correction_grade",previous["blend"]["max_correction_grade"])}
            protection=previous["protection"];collar=protection.get("compatibility_collar");fit_attempts=protection.get("fit_attempts",[])
        for attempt in range(0 if resume_fit is not None else 8):
            try:
                print(json.dumps({"terrain_fit_attempt":attempt+1,"protected_vertices":int(mask.sum())}),flush=True)
                heights,blend=biharmonic_blend(sampled,baseline.heights_m,mask,baseline.spacing_m,blend_m,max_correction_grade)
                break
            except TerrainFitError as failure:
                if attempt==7:
                    heights,local=limit_boundary_grade(failure.heights,sampled,mask,baseline.spacing_m,blend_m,max_correction_grade)
                    blend={**failure.report,"local_derivative_projection":local,"max_correction_grade":local["max_correction_grade"]};break
                extended,collar=compatibility_collar(baseline,sampled,mask,failure.heights,core_mask,
                    target_grade=max_correction_grade,bank_maximum_m=24. if attempt==0 else 40.)
                fit_attempts.append({"attempt":attempt+1,"max_correction_grade":failure.report["max_correction_grade"],
                                     "additional_vertices":int((extended&~mask).sum()),"worst_grid_xy":failure.report["worst_grid_xy"]})
                if np.array_equal(extended,mask):
                    heights,local=limit_boundary_grade(failure.heights,sampled,mask,baseline.spacing_m,blend_m,max_correction_grade)
                    blend={**failure.report,"local_derivative_projection":local,"max_correction_grade":local["max_correction_grade"]};break
                mask=extended
    except TerrainFitError as error:
        protection.update(compatibility_collar=collar,fit_attempts=fit_attempts,
                          protected_vertices=int(mask.sum()),protected_fraction=float(mask.mean()))
        mask_id=hashlib.sha256(mask.tobytes()).hexdigest()[:8]
        rejected=output.parent/"rejected"/(source.manifest_sha256[:12]+f"-b{blend_m:g}-m{mask_id}")
        rejected.mkdir(parents=True,exist_ok=True)
        ix,iy=error.report["worst_grid_xy"]
        error.report["worst_position_m"]=[baseline.origin_m[0]+ix*baseline.spacing_m[0],baseline.origin_m[1]+iy*baseline.spacing_m[1]]
        report={"schema":"pwr-constrained-terrain-rejection-v1","status":"REJECTED; no master published",
                "source_manifest_sha256":source.manifest_sha256,"baseline_manifest_sha256":baseline.manifest_sha256,
                "geometry_sha256":geometry_hash,"protection":protection,"blend":error.report}
        (rejected/"rejected-fit.json").write_text(json.dumps(report,indent=2)+"\n")
        np.savez_compressed(rejected/"rejected-fit.npz",heights=error.heights.astype(np.float32),
                            source=sampled.astype(np.float32),protected=mask,protected_core=core_mask)
        raise
    protection.update(compatibility_collar=collar,fit_attempts=fit_attempts,protected_vertices=int(mask.sum()),protected_fraction=float(mask.mean()))
    routes=layout.get("flights_m",{})
    if routes:
        flight_limit=min(float(route[key][2]) for route in routes.values() for key in ("start","end"))-150
        maximum_terrain_m=min(maximum_terrain_m,flight_limit)
    if not np.isfinite(maximum_terrain_m) or heights.max()>maximum_terrain_m:
        raise ValueError(f"Terrain maximum {heights.max():.3f} m exceeds preserved flight envelope {maximum_terrain_m:g} m")
    minimum=layout.get("scenario_bounds_m",{}).get("min",[0,0,-20])[2]
    if heights.min()<minimum:raise ValueError("Replacement terrain leaves the preserved lower scenario bounds")
    # Publish the exact quantized samples from the beginning, retaining baseline
    # encoding. The later derivation proves the render roundtrip again.
    raw,centre,scale,quantization=encode_master_heights(heights[::-1]*100,fixed)
    heights=((centre+(raw.astype(float)-32768)*scale/128)/100)[::-1].astype(np.float32)
    distance=distance_transform_edt(~mask,sampling=baseline.spacing_m[::-1])
    dy,dx=np.gradient(heights.astype(float)-sampled,*baseline.spacing_m[::-1])
    grade=np.hypot(dx,dy);unknown=(distance>0)&(distance<blend_m)
    quantized_grade=float(grade[unknown].max()) if unknown.any() else 0.
    if quantized_grade>max_correction_grade+1e-8:
        raise ValueError(f"R16 quantization exceeds correction-grade gate: {quantized_grade:.9f}")
    blend["quantized_max_correction_grade"]=quantized_grade
    far=distance>=blend_m
    blend["quantized_far_field_max_error_m"]=float(np.max(np.abs(heights[far]-sampled[far]))) if far.any() else 0.0
    if not np.array_equal(heights[mask].astype(float),baseline.heights_m[mask]):
        raise ValueError("Fixed encoding changed protected runtime samples")
    masks={k:v.copy() for k,v in baseline.masks.items() if k not in ("protected","forest","walkable")}
    masks["protected"]=mask
    masks["protected_core"]=core_mask
    dy,dx=np.gradient(heights.astype(float),*baseline.spacing_m[::-1]);slope=np.hypot(dx,dy)
    masks["walkable"]=(slope<=.35)&(masks["water"]<.5)
    water_distance=distance_transform_edt(masks["water"]<.5,sampling=baseline.spacing_m[::-1])
    road_distance=distance_transform_edt(masks["road"]<.1,sampling=baseline.spacing_m[::-1])
    base_distance=distance_transform_edt(masks["bases"]<.5,sampling=baseline.spacing_m[::-1])
    masks["forest"]=np.clip((.65-slope)/.45,0,1)*smoother((water_distance-18)/35)*smoother((road_distance-12)/20)*smoother(base_distance/24)
    candidate=Heightfield(heights.astype(float),baseline.origin_m,baseline.spacing_m,masks,
                         {"surface_interpolation":"triangle_nw_se"},"",output)
    validation=validate_geometry(candidate,geometry)
    # All full-width road sections and all river profiles must have identical
    # ground support, rather than only checking a few centreline markers.
    support=[]
    for road in geometry["roads"]:
        if not road.get("structure"):support.extend(np.asarray(road["cross_sections_m"]).reshape(-1,3))
    for river in geometry["watercourses"]:support.extend(river["surface_centreline_m"])
    points=np.asarray(support)
    error=np.abs(candidate.sample(points[:,0],points[:,1])-baseline.sample(points[:,0],points[:,1]))
    if error.max(initial=0)>1e-10:raise ValueError("Fixed full road/water support changed")
    preservation={"baseline_manifest":os.path.relpath(baseline.path,output.parent).replace("\\","/"),
        "baseline_manifest_sha256":baseline.manifest_sha256,"baseline_height_sha256":baseline.metadata["height"]["sha256"],
        "geometry_sha256":geometry_hash,"layout":os.path.relpath(layout_path,output.parent).replace("\\","/"),
        "layout_sha256":layout_hash,"protected_mask":"protected"}
    if (load_heightfield(source.path).manifest_sha256!=source.manifest_sha256
            or load_heightfield(baseline.path).manifest_sha256!=baseline.manifest_sha256
            or sha256(geometry_path)!=geometry_hash or sha256(layout_path)!=layout_hash):
        raise ValueError("An immutable terrain input changed during constrained generation")
    output.parent.mkdir(parents=True,exist_ok=True)
    (output.parent/"terrain.geometry.json").write_bytes(geometry_bytes)
    final=write_heightfield(output,heights,baseline.origin_m,baseline.spacing_m,masks,
        generator="constrain_terrain.py v1",source_manifest_sha256=source.manifest_sha256,
        source_height_sha256=source.metadata["height"]["sha256"],geometry="terrain.geometry.json",
        geometry_sha256=geometry_hash,water_level_m=baseline.metadata.get("water_level_m",55.0),
        surface_interpolation="triangle_nw_se",landscape_encoding_policy=fixed,preservation=preservation)
    preservation_check=preservation_report(final,final.heights_m)
    report={"schema":"pwr-constrained-terrain-v1","master_manifest_sha256":final.manifest_sha256,
        "source_manifest_sha256":source.manifest_sha256,"baseline_manifest_sha256":baseline.manifest_sha256,
        "geometry_sha256":geometry_hash,"layout_sha256":preservation["layout_sha256"],
        "protected_max_abs_error_m":0.0,"full_road_water_support_max_error_m":float(error.max(initial=0)),
        "protection":protection,"preservation":preservation_check,"blend":blend,"encoding":quantization,
        "boundary_derivatives":boundary_grade_report(heights.astype(float),baseline.heights_m,mask,baseline.spacing_m),
        "validation":validation,"terrain_range_m":[float(heights.min()),float(heights.max())],
        "maximum_adjacent_height_jump_m":float(max(np.abs(np.diff(heights,axis=0)).max(),np.abs(np.diff(heights,axis=1)).max())),
        "slope_percentiles":dict(zip(("p50","p95","p99","max"),map(float,np.percentile(slope,[50,95,99,100])))),
        "status":"candidate; native collision, PCG reprojection and live acceptance required"}
    (output.parent/"constrained-terrain.receipt.json").write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
    np.savez_compressed(output.parent/"constrained-terrain.diagnostics.npz",source_sampled_m=sampled.astype(np.float32),
                        earthworks_m=(heights-sampled).astype(np.float32),slope=slope.astype(np.float32),protected=mask,protected_core=core_mask)
    return report
