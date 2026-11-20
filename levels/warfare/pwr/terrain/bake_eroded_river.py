"""Bake a clear, terrain- and boulder-bound upper river from the verified .33 state."""
import json
from pathlib import Path
import shutil
import tempfile
import zipfile

import numpy as np
from scipy import ndimage

from bake_headwater_flux import (inside, project_line, read, section_discharge, smooth,
                                 solve_flow, texture, write, write_exr)
from plan_flux import REPO, headwater_controls
from flux_heightfield import build_capture_bed, provenance, sha256, state_matches, verify_state_files
from heightfield import load_heightfield

WORK = REPO/"out/pwr/river-erosion"
PARENT = REPO/"out/pwr/headwater-lake"
TIMBERLAND = Path("C:/haloce/ce_conversions/release_20261118/packs/ce-timberland-2.5.0.mjolnir")
OPTICS = ("color_preset", "surface_vectors", "surface_scalars")


def rock_surface(x, y, vertices, faces):
    """Return the highest actual collision triangle hit by a vertical ray at each cell centre."""
    top = np.full(x.shape, -np.inf)
    for a,b,c in vertices[np.asarray(faces,dtype=int)]:
        u,v=b-a,c-a
        area=u[0]*v[1]-u[1]*v[0]
        if abs(area)<1.e-10:
            continue
        dx,dy=x-a[0],y-a[1]
        s=(dx*v[1]-dy*v[0])/area
        t=(dy*u[0]-dx*u[1])/area
        within=(s>=-1.e-8)&(t>=-1.e-8)&(s+t<=1.+1.e-8)
        height=a[2]+u[2]*s+v[2]*t
        np.maximum(top,np.where(within,height,-np.inf),out=top)
    return top


def capture_rock_geometry(folder, master, geometry, upper, rocks):
    bed_file = folder/"authoring/flux_bed.json"
    mesh_proof = build_capture_bed(master,[upper["domain"]],bed_file)
    mesh = read(bed_file)
    for rock in rocks:
        vertices = np.asarray(rock["vertices_m"])
        faces = np.asarray(rock["faces"],dtype=int)
        indices = np.vstack([faces, faces[:,::-1]])+len(mesh["positions"])
        mesh["positions"].extend((vertices*[100.,-100.,100.]).tolist())
        mesh["normals"].extend([[0,0,1]]*len(vertices))
        mesh["weight"].extend([1.]*len(vertices))
        mesh["indices"].extend(indices.ravel().tolist())
        mesh["sections"].extend([0]*len(indices))
    bed_file.write_text(json.dumps(mesh,separators=(",",":")),encoding="utf8")
    mesh_proof.update(capture_bed_sha256=sha256(bed_file),rock_ids=[r["id"] for r in rocks],
                      vertices=len(mesh["positions"]),triangles_double_sided=len(mesh["indices"])//3)
    write(bed_file.with_suffix(".receipt.json"),mesh_proof)
    return provenance(master,geometry,bed_file,upper["domain"],upper["sources"],upper["simulation"])


def attach_native_probe(output, state, arrays, rock_probes, proof, samples=None):
    template = (REPO/"tools/level/headwater_flux_readback.lua").read_text(encoding="utf8")
    if samples is None:
        samples = [("pool",389,109),("feeder",346,30),("sill",442,188),("outflow",460,210),
                   ("dry_bank",309,106),("spring_hill",323,3),*rock_probes]
    rows = []
    for name,col,row in samples:
        h = arrays["height"][row,col,0]
        u,v,depth,foam = arrays["velocity"][row,col]
        bed = arrays["ground"][row,col,0]
        rows.append(f'    {{"{name}",{col},{row},{h},{u},{v},{depth},{bed},{foam}}},')
    start = template.index("local probes = {")
    end = template.index("local maps =",start)
    template = template[:start]+"local probes = {\n"+"\n".join(rows)+"\n}\n"+template[end:]
    template = template.replace('{"B", 7, 1}', '{"B", 7, 1}, {"A", 9, .002}')
    proof["readback_texels"] = samples
    (output/"river_flux_readback.lua").write_text(template,encoding="utf8")


def bake(folder, rocks_file, work=WORK, basin_parent=None):
    master = work/"terrain/runtime-master.json"
    geometry = work/"terrain/terrain.geometry.json"
    old_master = PARENT/"terrain/runtime-master.json"
    parent = PARENT/"saturday.33/map-input"
    field, old_field = load_heightfield(master), load_heightfield(old_master)
    geom = read(geometry)
    flux = read(parent/"pwr.level.json")["flux"]
    upper,lower = flux["domains"]
    assert [upper["id"],lower["id"]] == ["upper_river","lower_lake"]
    state = upper["state"]
    for domain in flux["domains"]:
        assert state_matches(domain["state"],domain)
        verify_state_files(parent,domain["state"])
    with zipfile.ZipFile(TIMBERLAND) as archive:
        timber = json.loads(archive.read("map/level.json"))["flux"]
    if any(k in timber for k in (*OPTICS,"surface")) or "surface" in upper:
        raise ValueError("Unexpected explicit Timberland optics or river class")
    for key in OPTICS:
        upper.pop(key)
    lake, = [l for l in geom["lakes"] if l["id"]=="north_headwater_lake"]
    main,spring = [np.asarray(next(c for c in geom["watercourses"] if c["id"]==name)["surface_centreline_m"])
                   for name in ("central_river","headwater_spring")]
    chain=np.r_[0.,np.cumsum(np.linalg.norm(np.diff(main[:,:2],axis=0),axis=1))]
    main=main[:np.searchsorted(chain,145.)+1];chain=chain[:len(main)]
    rock_data=read(rocks_file)
    if rock_data["terrain_sha256"]!=sha256(master):
        raise ValueError("Rock hulls use a different terrain")
    rocks=rock_data["rocks"]
    if not rocks: raise ValueError("Missing physical rock hulls")
    poly=np.asarray(lake["polygon_m"]);level=lake["water_z_m"]
    cell=state["cell"]/100
    xs=state["centre"][0]/100+(np.arange(state["res"][0])+.5-state["res"][0]/2)*cell
    ys=-state["centre"][1]/100-(np.arange(state["res"][1])+.5-state["res"][1]/2)*cell
    rows,cols=np.where(field.heights_m!=old_field.heights_m)
    changed=field.origin_m+np.column_stack([cols,rows])*field.spacing_m
    points=np.vstack([changed,poly,main[:,:2],spring[:,:2],*[np.asarray(r["vertices_m"])[:,:2] for r in rocks]])
    lo,hi=points.min(axis=0)-12,points.max(axis=0)+12
    cols=np.flatnonzero((xs>=lo[0])&(xs<=hi[0]))
    rows=np.flatnonzero((ys>=lo[1])&(ys<=hi[1]))
    if hi[1]>1015 or lo[1]<45 or not len(rows) or not len(cols):
        raise ValueError("Edit exceeds the northern reach")
    window=np.s_[rows[0]:rows[-1]+1,cols[0]:cols[-1]+1]
    xx,yy=np.meshgrid(xs[cols],ys[rows])
    terrain=field.sample(xx,yy)
    ground=terrain.copy()
    changed_terrain=np.abs(terrain-old_field.sample(xx,yy))>1.e-7
    owner=np.zeros(xx.shape,dtype=np.int32)
    for i,rock in enumerate(rocks,1):
        vertices=np.asarray(rock["vertices_m"])
        close=((xx>=vertices[:,0].min())&(xx<=vertices[:,0].max())&
               (yy>=vertices[:,1].min())&(yy<=vertices[:,1].max()))
        roof=rock_surface(xx[close],yy[close],vertices,rock["faces"])
        indices=np.flatnonzero(close)[roof>ground[close]]
        ground.flat[indices]=roof[roof>ground[close]]
        owner.flat[indices]=i
    upper["sources"]=[s for s in upper["sources"] if s["role"]!="headwater_level_hold"]
    upper["sources"]+=headwater_controls(field,lake,[-732,0,268,1000])
    upper["provenance"]=capture_rock_geometry(folder,master,geometry,upper,rocks)
    upper["provenance"].update(rock_geometry_sha256=sha256(rocks_file),erosion_solve_sha256=sha256(Path(__file__)))
    state["provenance"]=dict(upper["provenance"])
    original={k:texture(parent/state[k]) for k in ("height","velocity","ground")}
    result={k:v.copy() for k,v in original.items()}
    dist,station,_=project_line(xx,yy,main)
    oldv=original["velocity"][window]
    oldwet=oldv[...,2]>.7
    oldh=(original["height"][window][...,0]+state["capture"])/100
    distance,nearest=ndimage.distance_transform_edt(~oldwet,return_indices=True)
    surface=oldh[tuple(nearest)]
    lake_mask=inside(np.stack([xx,yy],axis=-1),poly)
    # Extend the calm waterline onto newly cut marginal shelves. Running
    # river and spring heights retain the native longitudinal head profile.
    in_lake=ndimage.distance_transform_edt(~lake_mask)*cell<10
    near_spring,_,_=project_line(xx,yy,spring)
    surface=np.where(in_lake & (near_spring>5) & (dist>10),level,surface)
    updated_ground=changed_terrain|(owner>0)
    active_channel=(dist<30)&(station<119)
    domain=(oldwet & (in_lake | (near_spring<8) | active_channel))|(
        (distance*cell<11) & updated_ground & (in_lake|active_channel))
    basin=None
    if "registered_basin" in lake:
        import outlet_apron
        xy=np.stack((xx,yy),axis=-1)
        along,across=outlet_apron.coordinates(xy)
        # Close ONLY the real outlet for this static connectivity test. A
        # low spot outside the lake may be below the waterline yet belongs
        # to a different catchment. The spring retains its own graded head.
        closed=(abs(along-40.)<3.)&(abs(across)<25.)
        regions,_=ndimage.label((terrain<level-.018)&~closed,np.ones((3,3)))
        r,c=np.unravel_index(np.argmin((xx+360.)**2+(yy-900.)**2),xx.shape)
        basin=regions==regions[r,c]
        if not regions[r,c] or np.any(basin[[0,-1],:]) or np.any(basin[:,[0,-1]]):
            raise ValueError("Lake leaks past its terrain catchment on the Fluid Flux grid")
        broad=(along>57)&(near_spring>5)
        domain=np.where(broad,basin,domain)
        surface=np.where(broad&basin,level,surface)
        updated_ground|=broad&basin
    river=next(c for c in geom["watercourses"] if c["id"]=="central_river")
    apron=None
    if "apron" in river:
        import outlet_apron
        xy=np.stack((xx,yy),axis=-1)
        reach=np.asarray(river["erosion_reach"]["centreline_m"])
        _,strength,left_distance,right_distance=outlet_apron.profile(xy,reach)
        # Native ground height clips the physical land/water contact. The
        # shared traced banks delimit only the local solve, with two cells of
        # interpolation margin past the cut and the depositional toe.
        apron=(strength>0)&(left_distance>-2*cell)&(right_distance>-2*cell)
        _,_,head=project_line(xx,yy,reach)
        surface=np.where(apron,surface+(head-surface)*strength,surface)
        domain|=apron
        updated_ground|=apron
    depth=np.where(domain,np.maximum(surface-ground,0.),0.)
    source=np.exp(-((xx-spring[0,0])**2+(yy-spring[0,1])**2)/5.)*(depth>.018)
    recharge=lake_mask*np.maximum(depth-.5,0.)**2
    source=.018*source/source.sum()+.982*recharge/recharge.sum()
    sink=np.exp(-((station-108)/3.)**2)*(dist<15)*depth**1.65
    discharge,cross=section_discharge(main,chain,state,original["velocity"])
    velocity,wet,residual=solve_flow(depth,source,sink,discharge,cell)
    depth=np.where(wet,depth,0.)
    if basin is not None:
        if basin_parent is None:
            raise ValueError("The registered basin requires its approved apron playback")
        previous=read(basin_parent/"pwr.level.json")["flux"]["domains"][0]["state"]
        shift=(previous["centre"][1]-state["centre"][1])/state["cell"]
        if not shift.is_integer() or previous["centre"][0]!=state["centre"][0] or previous["res"]!=state["res"]:
            raise ValueError("Approved apron does not share the original native cell grid")
        old_apron=texture(basin_parent/previous["velocity"])[np.ix_(np.maximum(rows-int(shift),0),cols)]
        # The unchanged apron is a measured downstream velocity boundary.
        # The widened catchment joins that boundary over its graded mouth.
        inherit=apron*wet*(abs(old_apron[...,2]-100*depth)<1.)*(1-smooth(57.,72.,along))
        velocity=velocity*(1-inherit[...,None])+old_apron[...,:2]*inherit[...,None]
    speed=np.linalg.norm(velocity,axis=-1)
    # Fade into the inherited cross-section well beyond the last eroded bar.
    blend=np.where((station>72)&(dist<28),1-smooth(76,104,station),1.)*(
        domain|updated_ground)
    wet_input=oldwet|wet
    blend=np.where(updated_ground|wet_input,blend,0.)
    if np.any(updated_ground&(blend<.999)):
        raise ValueError("A physical terrain or rock edit enters the downstream boundary blend")
    for idx in range(2):
        result["velocity"][window][...,idx]=oldv[...,idx]*(1-blend)+velocity[...,idx]*blend
    result["velocity"][window][...,2]=oldv[...,2]*(1-blend)+depth*100*blend
    # Glancing foam is generated at obstructions and riffles. The backwater
    # and sheltered shoreline retain a quiet surface.
    foam=.025*smooth(.45,2.2,speed)*smooth(.08,.4,depth)
    rock_info=[];rock_probes=[]
    for i,rock in enumerate(rocks,1):
        footprint=owner==i
        if not footprint.any(): continue
        interacting=(footprint & domain & (surface>terrain+.018)) if apron is not None else (
            footprint & (oldwet | wet) & (distance*cell<2))
        if not interacting.any(): continue
        blocked=interacting & (ground>surface+.02)
        if not blocked.any(): continue
        y,x=np.unravel_index(np.argmax(np.where(blocked,ground-surface,-np.inf)),xx.shape)
        contact=ndimage.binary_dilation(interacting,iterations=3) & wet & ~footprint
        if not contact.any():continue
        direction=np.average(velocity[contact],axis=0,weights=np.maximum(depth[contact],.02))
        direction/=max(np.linalg.norm(direction),1.e-6)
        centre=np.array([xx[interacting].mean(),yy[interacting].mean()])
        radius=max(.75,np.sqrt(interacting.sum()/np.pi)*cell)
        dx=xx-centre[0];dy=centre[1]-yy
        s=dx*direction[0]+dy*direction[1]
        signed_lateral=dy*direction[0]-dx*direction[1]
        lateral=np.abs(signed_lateral)
        wake=np.exp(-((lateral-.72*radius-.10*np.maximum(s,0))/(.48*radius+.3))**2)
        wake*=smooth(-radius,-.25*radius,s)*(1-smooth(radius,5.*radius,s))
        if basin is None:
            foam=np.maximum(foam,.34*wake*smooth(.12,1.3,speed)*wet)
        forward=np.einsum("ijk,k->ij",velocity,direction)
        active_flank=contact & (forward>.04)
        rock_info.append({"id":rock["id"],"role":rock["role"],"emergent_cells":int(blocked.sum()),
                          "flowing_left_right_cells":[int(np.count_nonzero(active_flank&(signed_lateral<0))),
                                                      int(np.count_nonzero(active_flank&(signed_lateral>=0)))],
                          "positive_flow_around_hull_cells":int((contact&(speed>.02)).sum()),
                          "crest_texel":[int(cols[x]),int(rows[y])],"radius_m":float(radius)})
        rock_probes.append((f"crest_{i}",int(cols[x]),int(rows[y])))
        if apron is not None:
            # Resolve even a slow-moving bank-side boulder's own two wake
            # lanes. Relative local acceleration modulates its aeration,
            # while the actual speed floor keeps slack water optically quiet.
            flank_reference=max(.12,float(np.quantile(speed[contact],.80)))
            local_foam=.36*wake*smooth(.015,.30,speed)*smooth(.12,.92,speed/flank_reference)*wet
            if basin is not None:
                # Distance and facing come from the actual waterline silhouette
                # of each collision hull. A near-cell-wide windward collar and
                # two short streaks leave clear water in the sheltered lee.
                edge,nearest_crest=ndimage.distance_transform_edt(~blocked,return_indices=True)
                ny,nx=nearest_crest
                norm=np.maximum(edge*cell,cell)
                facing=-((xx-xx[ny,nx])*direction[0]+(yy[ny,nx]-yy)*direction[1])/norm
                energy=smooth(.015,.32,speed)*wet
                collar=.74*np.exp(-((edge-1.)/.78)**2)*smooth(.03,.66,facing)*energy
                march=np.clip(s/radius,0.,4.)
                rails=np.quantile(signed_lateral[blocked],[.045,.955])
                lanes=np.min(np.stack([abs(signed_lateral-rail*(1.-.07*march)) for rail in rails]),axis=0)
                trough=np.exp(-(lanes/max(.90*cell,.19*radius))**2)
                lee=.53*trough*smooth(-.75*radius,.22*radius,s)*(1-smooth(.8*radius,3.4*radius,s))*energy
                local_foam=np.maximum(collar,lee)
                rock_info[-1].update(collar_peak=float(collar.max()),collar_cells_above_025=int((collar>.25).sum()),
                    trail_peak=float(lee.max()),trail_cells_above_015=int((lee>.15).sum()),
                    wake_max_extent_from_centre_m=round(3.4*radius,2),
                    inherited_wet_flank_cells=int(np.count_nonzero(contact&(inherit==1.))))
                peak=np.unravel_index(collar.argmax(),collar.shape)
                rock_probes.append((f"collar_{i}",int(cols[peak[1]]),int(rows[peak[0]])))
                if (collar>.25).sum()<2 or not np.any((lee>.15)&(s>radius)&(signed_lateral<0)) or not np.any(
                    (lee>.15)&(s>radius)&(signed_lateral>0)):
                    raise ValueError("Missing resolved upstream collar or one of the two trailing wakes: "+rock["id"])
            foam=np.maximum(foam,local_foam)
            peak_field=lee if basin is not None else local_foam
            iy,ix=np.unravel_index(peak_field.argmax(),peak_field.shape)
            rock_info[-1].update(wake_peak=float(local_foam[iy,ix]),
                                  wake_cells=int(np.count_nonzero(local_foam>.06)),
                                  wake_texel=[int(cols[ix]),int(rows[iy])])
            rock_probes.append((f"wake_{i}",int(cols[ix]),int(rows[iy])))
    if apron is not None and (len(rock_info)!=len(rocks) or any(
        min(r["flowing_left_right_cells"])<2 or r["wake_cells"]<2 for r in rock_info)):
        raise ValueError(f"Unresolved flow or wake beside an apron boulder: {rock_info}")
    if len(rock_info)<2: raise ValueError(f"Too few resolved boulders in the active channel: {rock_info}")
    if not any(min(r["flowing_left_right_cells"])>1 for r in rock_info):
        raise ValueError("The stream has no open flowing split around an emergent boulder")
    foam*=wet
    result["velocity"][window][...,3]=oldv[...,3]*(1-blend)+foam*blend
    ground_map=result["ground"][window][...,0]
    ground_map[updated_ground]=state["centre"][2]-ground[updated_ground]*100.
    # At exposed boulder cells the earlier water plane already lies below
    # the crest. Avoid a spurious water spike by never raising that plane.
    dryheight=np.minimum(oldh,ground-.24)
    if apron is not None:
        # Newly inundated banks may have had mountain-height dry samples in
        # the old state. Keeping the water plane below the local head here
        # prevents an interpolated vertical curtain at an emergent rock.
        dryheight=np.where(apron|((owner>0)&domain),np.minimum(dryheight,surface),dryheight)
    for c,margin in ((0,0),(1,.09)):
        old=original["height"][window][...,c]
        new=np.where(wet,surface,dryheight+margin)*100-state["capture"]
        result["height"][window][...,c]=old*(1-blend)+new*blend
    out_state=folder/"flux_state"
    shutil.copytree(parent/"flux_state/lower_lake",out_state/"lower_lake")
    for key,arr in result.items():
        write_exr(folder/state[key],arr)
        state[key+"_sha256"]=sha256(folder/state[key])
    write(out_state/"upper_river/state.json",state)
    write(folder/"flux.json",flux)
    checked={k:texture(folder/state[k]) for k in result}
    changed_total=np.zeros_like(checked["ground"][...,0],dtype=bool)
    changed_total[window]=(blend>0)|updated_ground
    for k,arr in checked.items():
        if not np.array_equal(arr[~changed_total],original[k][~changed_total]):
            raise ValueError("Texture changed outside the revised reach: "+k)
        assert np.array_equal(arr[-40:],original[k][-40:])
    for name,c,r in rock_probes:
        if name.startswith("crest_"):
            assert checked["velocity"][r,c,2]==0
        elif checked["velocity"][r,c,2]<=0 or checked["velocity"][r,c,3]<=.06:
            raise ValueError("Missing stored wet, aerated wake at "+name)
    hill=(3,323)
    if any(not np.array_equal(checked[k][hill],original[k][hill]) for k in checked):
        raise ValueError("Dry crest behind spring was modified")
    label,_=ndimage.label(checked["velocity"][...,2]>.7,np.ones((3,3)))
    component=label[109,389]
    stations=[("pool",109,389),("spring",30,346),("outflow",210,460)]
    reference={k:(int(label[r,c]),float(checked["velocity"][r,c,2])) for k,r,c in stations}
    if not component or any(label[r,c]!=component for _,r,c in stations):
        raise ValueError(f"Feeder, lake and river are disconnected at reference texels: {reference}")
    for i in np.arange(0,102,2.):
        section=(np.abs(station-i)<1.1)&(dist<17)
        if not np.any(section&(label[window]==component)):
            raise ValueError(f"River interrupted at station {i}")
    q=lambda a:np.quantile(a,[0,.5,.95,1.]).tolist()
    core=lake_mask&(depth>1)&(dist>15)&(near_spring>8)
    quiet=q(foam[core])
    if quiet[2]>.015: raise ValueError("Foam pooling in calm water")
    wake_cells=(foam>.095)&wet
    if not np.any(wake_cells):raise ValueError("Undetectable localized flow disturbance")
    r,c=np.unravel_index(np.argmax(foam),foam.shape)
    rock_probes.append(("wake",int(cols[c]),int(rows[r])))
    lower_files={f.name:sha256(f) for f in (out_state/"lower_lake").iterdir()}
    assert all(sha256(parent/"flux_state/lower_lake"/n)==d for n,d in lower_files.items())
    for domain in flux["domains"]:
        assert state_matches(domain["state"],domain)
        verify_state_files(folder,domain["state"])
    proof={"schema":"pwr-eroded-river-flux-v1","runtime_simulation":False,
           "method":"Terrain- and convex-hull-bound depth-averaged finite-volume solve with native downstream discharge",
           "inputs":{"terrain":sha256(master),"geometry":sha256(geometry),"rocks":sha256(rocks_file),
                     "parent_level":sha256(parent/"pwr.level.json"),"source":sha256(Path(__file__))},
           "timberland_archive":str(TIMBERLAND),"timberland_parent_sha256":sha256(TIMBERLAND),
           "river_class":"BP_FluxSurface_River","removed_upper_overrides":list(OPTICS),
           "rocks":rock_info,"internal_flow_residual":residual,"discharge_native_units":discharge,
           "downstream_cross_section_discharge":cross,"lake_core_foam_quantiles":quiet,
           "local_wake_cells":int(wake_cells.sum()),"max_encoded_foam":float(foam.max()),
           "same_wet_component":True,"lake_target_m":level,
           "lake_wet_area_m2":float((lake_mask&(checked['velocity'][window][...,2]>1)).sum()*cell**2),
           "inherited_lower_files":lower_files,"unchanged_seam_rows":40,
           "unchanged_upper_texels_compared":int((~changed_total).sum()),
           "files":{f.relative_to(folder).as_posix():sha256(f) for f in sorted(out_state.rglob("*")) if f.is_file()}}
    attach_native_probe(folder,state,checked,rock_probes,proof)
    write(folder/"receipt.json",proof)


if __name__=="__main__":
    target=WORK/"water-fix"
    if target.exists(): raise FileExistsError(target)
    with tempfile.TemporaryDirectory(dir=WORK) as scratch:
        staged=Path(scratch)/"water"
        staged.mkdir()
        bake(staged,WORK/"dressing/flow-rocks.json")
        staged.rename(target)
    print(target)
