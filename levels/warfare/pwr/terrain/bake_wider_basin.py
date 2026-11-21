"""Publish a contained headwater basin, including registered viewpoints and native probes."""
from pathlib import Path
import tempfile

import numpy as np
from scipy import ndimage

import outlet_apron as apron
from audit_flux_state import sample
from bake_eroded_river import (REPO, attach_native_probe, bake, load_heightfield, read, sha256,
                               state_matches, texture, verify_state_files, write)
from bake_outlet_apron import survey as survey_apron
from extend_river_contact import build
from survey_outlet_apron import intervals, ray_water


def survey_basin(folder, work, previous):
    survey_apron(folder,work,previous,37)
    terrain=load_heightfield(work/"terrain/runtime-master.json")
    old_terrain=load_heightfield(apron.WORK/"terrain/runtime-master.json")
    measurements=read(work/"terrain/headwater-terrain.receipt.json")
    if measurements["runtime_manifest_sha256"]!=terrain.manifest_sha256:
        raise ValueError("Stale surveyed lake terrain")
    geometry=read(work/"terrain/terrain.geometry.json")
    reach=np.asarray(geometry["watercourses"][0]["erosion_reach"]["centreline_m"])
    desc=read(folder/"flux.json")
    state=desc["domains"][0]["state"]
    old=read(previous/"pwr.level.json")["flux"]["domains"][0]["state"]
    arrays={k:texture(folder/state[k]) for k in ("velocity","height","ground")}
    velocity=arrays["velocity"]
    prev_velocity=texture(previous/old["velocity"])
    if state["centre"]!=old["centre"] or state["res"]!=old["res"]:
        raise ValueError("Registered Fluid Flux grid changed")
    cell=state["cell"]/100
    cols=state["centre"][0]/100+(np.arange(state["res"][0])+.5-state["res"][0]/2)*cell
    rows=-state["centre"][1]/100-(np.arange(state["res"][1])+.5-state["res"][1]/2)*cell
    c=np.flatnonzero((cols>=-540)&(cols<=-185)); r=np.flatnonzero((rows>=718)&(rows<=1000))
    x,y=np.meshgrid(cols[c],rows[r])
    along,side=apron.coordinates(np.stack((x,y),axis=-1))
    seal=(abs(along-40)<3)&(abs(side)<25)
    seed=np.unravel_index(np.argmin((x+360)**2+(y-900)**2),x.shape)
    def closed_component(wet):
        labels,_=ndimage.label(wet&~seal,np.ones((3,3)))
        if not labels[seed]:
            raise ValueError("The main lake seed is dry")
        fill=labels==labels[seed]
        if fill[[0,-1]].any() or fill[:,[0,-1]].any():
            raise ValueError("Flooded lake reaches the catchment boundary")
        return fill
    wet=closed_component(velocity[r[:,None],c,2]>1.8)
    old_wet=closed_component(prev_velocity[r[:,None],c,2]>1.8)
    physical=closed_component(terrain.sample(x,y)<measurements["water_level_m"]-.018)
    basin_area=float(wet.sum()*cell**2); prior_area=float(old_wet.sum()*cell**2)
    physical_area=float(physical.sum()*cell**2)
    if basin_area-prior_area<5000 or abs(basin_area-physical_area)>.05*physical_area:
        raise ValueError(f"Insufficient hydraulically connected lake: {basin_area}, {prior_area}, {physical_area}")
    # Check the real foreground terrain at each camera ray as well as depth
    # decoded from the two native saved states, at the same pixel locations.
    scanlines=[]
    for row in measurements["camera_rows"]:
        px=np.arange(0,1600,2)
        hit=apron.intersect(px,float(row["y"]),reach)
        limit=np.max(abs(hit[:,:2]),axis=1)<999.99
        px,xy=px[limit],hit[limit,:2]
        def visible(field,depth,spec):
            encoded,valid=sample(depth,spec,xy)
            exposed=ray_water(field,px,float(row["y"]),reach)
            spans=intervals(px,valid&exposed&(encoded>1.8))
            return max(spans,key=lambda p:p[1]-p[0])
        new_span=visible(terrain,velocity[...,2],state)
        old_span=visible(old_terrain,prev_velocity[...,2],old)
        if max(abs(np.asarray(new_span)-row["native"]))>20:
            raise ValueError(f"Native water misses graded contact at {row['y']}: {new_span} / {row['native']}")
        scanlines.append(dict(y_px=row["y"],art_target_px=row["target"],physical_contact_px=row["native"],
                              flux_contact_px=new_span,previous_flux_contact_px=old_span))
    proof=read(folder/"receipt.json")
    probes=proof["readback_texels"]
    native={}
    for name,point in measurements["native_probes"].items():
        px,py=point["xy_m"]
        i,j=int(np.argmin(abs(cols-px))),int(np.argmin(abs(rows-py)))
        ground=float(terrain.sample(cols[i],rows[j]))
        d=float(velocity[j,i,2])
        above=ground-measurements["water_level_m"]
        submerged=point["bed_above_local_water_m"]<0
        if (submerged and not (above<-.12 and d>12)) or (not submerged and not (above>.1 and d==0)):
            raise ValueError(f"Incorrect native shelf/rim depth at {name}: {d} cm, terrain {above:+.2f} m")
        if submerged and abs(d/100+above)>.06:
            raise ValueError(f"Bad terrain-registered water depth at {name}: {d} cm / {above:+.2f} m")
        native[name]=dict(texel=[i,j],xy_m=[float(cols[i]),float(rows[j])],physical_bed_above_pool_m=above,
                          depth_cm=d,prior_depth_cm=float(prev_velocity[j,i,2]))
        probes.append(("basin_"+name,i,j))
    # The old fixed sill probe now sits on the companion's crown. Retain the
    # dedicated crest probe, and place the sill readback in the open passage.
    centre=geometry["lakes"][-1]["outlet"]["position_m"]
    near=(x-centre[0])**2+(y-centre[1])**2
    good=(velocity[r[:,None],c,2]>30)&(near<36)
    j,i=np.unravel_index(np.argmin(np.where(good,near,np.inf)),near.shape)
    if not good[j,i]:
        raise ValueError("No optical sill channel to probe")
    probes=[("sill",int(c[i]),int(r[j])) if p[0]=="sill" else p for p in probes]
    attach_native_probe(folder,state,arrays,[],proof,samples=probes)
    proof.update(schema="pwr-registered-basin-flux-v1",registered_basin_scanlines=scanlines,
                 registered_basin_probes=native,approved_surface_scalars=desc["domains"][0]["surface_scalars"],
                 basin_closure=dict(original_encoded_m2=prior_area,encoded_m2=basin_area,
                     encoded_net_gain_m2=basin_area-prior_area,quantized_terrain_at_flux_centres_m2=physical_area,
                     new_wet_ground_m2=float((wet&~old_wet).sum()*cell**2),
                     previous_wet_ground_now_dry_m2=float((old_wet&~wet).sum()*cell**2),
                     connected_to_open_boundary=False,seal_purpose="Only used to isolate the lake for measurement"),
                 gpu_probe_sha256=sha256(folder/"river_flux_readback.lua"))
    proof["inputs"].update(basin_verification=sha256(Path(__file__)),
                           terrain_measurements=sha256(work/"terrain/headwater-terrain.receipt.json"))
    for group in desc["domains"]:
        verify_state_files(folder,group["state"])
        if not state_matches(group["state"],group):
            raise ValueError("Published state metadata does not match its tile")
    write(folder/"receipt.json",proof)


def main():
    work=REPO/"out/pwr/river-basin"
    parent=apron.WORK/"saturday.37/map-input"
    target=work/"water-fix"
    if target.exists():
        raise FileExistsError(target)
    with tempfile.TemporaryDirectory(dir=work,prefix=".flux-basin-") as scratch:
        first,final=Path(scratch)/"unshifted",Path(scratch)/"ready"
        first.mkdir();final.mkdir()
        bake(first,work/"dressing/flow-rocks.json",work,parent)
        build(final,work,first)
        survey_basin(final,work,parent)
        final.rename(target)
    print(target)


if __name__=="__main__":
    main()
