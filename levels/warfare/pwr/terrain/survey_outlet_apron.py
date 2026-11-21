"""Prove the visible wetted apron, stock-rock crowns and native survey positions."""
import argparse
import json
from pathlib import Path

import numpy as np
from scipy.spatial import ConvexHull
from scipy import ndimage

import outlet_apron as apron
import headwater_dressing as dress
from verify_outlet_erosion import slice_hull
from finalize_terrain import inside_polygon


def ray_water(terrain, px, py, line):
    hit=apron.intersect(px,py,line)
    # Check the complete sight line for a dry foreground bank, including
    # the last interval before the ray meets the water plane.
    ray=hit-apron.EYE
    ts=np.linspace(.005,1.,321)
    pts=apron.EYE+ray[:,None,:]*ts[None,:,None]
    heights=terrain.sample(pts[...,0],pts[...,1])
    clearance=pts[...,2]-heights
    return ((clearance.min(axis=1)>.007)&(terrain.sample_mask("water",hit[:,0],hit[:,1])>.35))


def intervals(pixels,keep):
    indices=np.flatnonzero(np.diff(np.r_[False,keep,False])).reshape(-1,2)
    return [[int(pixels[a]),int(pixels[b-1])] for a,b in indices]


def native_probe(terrain,xy):
    return {"xy_m":np.asarray(xy).round(5).tolist(),"ground_z_m":round(float(terrain.sample(*xy)),5)}


def corridor(terrain,line,reach,shoals):
    arc=apron.head.arclength(line[:,:2])-reach["sill_station_m"]
    offset=np.arange(-35.,35.01,.05)
    stations=np.arange(-13.,28.01,.25)
    width=[]
    for station in stations:
        i=np.clip(np.searchsorted(arc,station)-1,0,len(arc)-2)
        t=(station-arc[i])/(arc[i+1]-arc[i])
        centre=(1.-t)*line[i]+t*line[i+1]
        direction=line[i+1,:2]-line[i,:2]
        normal=np.array([-direction[1],direction[0]])/np.linalg.norm(direction)
        xy=centre[:2]+offset[:,None]*normal
        wet=terrain.sample(*xy.T)<apron.surface(xy,line)-.15
        solid=np.logical_or.reduce([inside_polygon(*xy.T,poly) for poly in shoals])
        cuts=np.flatnonzero(np.diff(np.r_[False,wet&~solid,False])).reshape(-1,2)
        width.append(float(np.max(np.diff(cuts,axis=1))*.05))
    if min(width)<2.5:
        raise ValueError("Native rocks obstruct the river")
    return {"minimum_width_m":round(min(width),2),"narrowest_station_from_sill_m":float(stations[np.argmin(width)]),
            "survey_station_range_m":[float(stations[0]),float(stations[-1])],"station_step_m":.25,"minimum_depth_m":.15}


def closed_sill(terrain,polygon):
    # Test the basin at static lake elevation. Close its actual sill (40 m
    # forward in this camera), upstream of the grading on the falling river.
    axes=[np.arange(n)*d+o for n,d,o in zip(terrain.dimensions,terrain.spacing_m,terrain.origin_m)]
    xs=np.where((axes[0]>=-510)&(axes[0]<=-180))[0]
    ys=np.where((axes[1]>=705)&(axes[1]<=997))[0]
    xx,yy=np.meshgrid(axes[0][xs],axes[1][ys])
    forward,side=apron.coordinates(np.stack((xx,yy),axis=-1))
    seal=(np.abs(forward-40.)<3.)&(np.abs(side)<25.)
    flood=(terrain.heights_m[np.ix_(ys,xs)]<142.375)&~seal
    labels,_=ndimage.label(flood,np.ones((3,3)))
    source=np.unravel_index(np.argmin((xx+360.)**2+(yy-900.)**2),xx.shape)
    fill=labels==labels[source]
    if not labels[source] or np.any(fill[[0,-1]]) or np.any(fill[:,[0,-1]]):
        raise ValueError("Northern lake spills through another outlet")
    return {"lake_test_level_m":142.375,"sealed_forward_m":40.,"sealed_width_m":50.,
            "connected_area_m2":round(float(fill.sum()*np.prod(terrain.spacing_m)),2),"single_outlet":True}


def clear_flank(rock,sign,line,terrain,solids):
    cut=slice_hull(rock,rock["surface_z_m"])[:,:2]
    # Distinguish bare bed from a point covered by the neighbouring crown.
    # Follow the outside of the actual cut polygon to find an open flank.
    centre=cut.mean(0)
    ring=apron.head.densify(np.vstack((cut,cut[0])),step=.15)
    radial=ring-centre
    candidates=ring+radial/np.linalg.norm(radial,axis=1)[:,None]
    lateral=sign*((ring-centre)@apron.RIGHT[:2])
    neighbour=np.logical_or.reduce([inside_polygon(*candidates.T,poly) for poly in solids])
    depths=apron.surface(candidates,line)-terrain.sample(*candidates.T)
    valid=(~neighbour)&(depths>.1)&(lateral>.3*lateral.max())
    if not np.any(valid):
        raise ValueError("No open water on flank of "+rock["id"])
    probe=int(np.nanargmax(np.where(valid,lateral,np.nan)))
    return {"rock":rock["role"],"flank":"screen left" if sign<0 else "screen right",
            "spot_m":candidates[probe].round(4).tolist(),"clear_water_depth_m":round(float(depths[probe]),3),
            "clear_of_all_rock_hulls_at_15cm":True}


def survey(work):
    terrain=dress.load_heightfield(work/"terrain/runtime-master.json")
    old=dress.load_heightfield(apron.PREVIOUS/"runtime-master.json")
    geometry=dress.read(work/"terrain/terrain.geometry.json")
    line=np.array(geometry["watercourses"][0]["erosion_reach"]["centreline_m"])
    rocks=dress.read(work/"dressing/flow-rocks.json")
    if rocks["terrain_sha256"]!=terrain.manifest_sha256:
        raise ValueError("Rock transforms are on a different terrain")
    crowns=[]
    hulls=[]
    flank_records=[]
    solids=[slice_hull(rock,rock["surface_z_m"]-.15)[:,:2] for rock in rocks["rocks"]]
    for rock in rocks["rocks"]:
        level=rock["surface_z_m"]
        v=np.array(rock["vertices_m"])
        world=np.vstack((v[v[:,2]>level],slice_hull(rock,level)))
        pixels=apron.project(world)
        crown=pixels[ConvexHull(pixels).vertices]
        bbox=np.r_[crown.min(0),crown.max(0)]
        bed=terrain.sample(*v[:,:2].T)
        hulls.append(crown)
        crowns.append({"id":rock["id"],"role":rock["role"],"bbox_px":bbox.round(1).tolist(),
                       "exposed_m":round(float(v[:,2].max()-level),3),"toe_below_bed_m":round(float((bed-v[:,2]).max()),3),
                       "highest_hull_vertex_m":v[v[:,2].argmax()].round(5).tolist(),"crown_width_px":round(float(np.ptp(crown[:,0])),1)})
        for sign in (-1,1):
            flank_records.append(clear_flank(rock,sign,line,terrain,solids))
    px=np.arange(0,1600,2)
    rows=[]
    trace=apron.TRACE[::-1]
    cliprows=(565,600,640,680,720,760,800,850,884,898)
    for y in cliprows:
        wet=ray_water(terrain,px,float(y),line)
        prev=ray_water(old,px,float(y),line)
        rock_mask=np.logical_or.reduce([inside_polygon(px,np.full_like(px,y),h) for h in hulls])
        left,right=[float(np.interp(y,trace[:,0],trace[:,i])) for i in (1,2)]
        rows.append({"y_px":y,"target_bank_span_px":np.round([left,right],1).tolist(),
            "traced_target_fraction":round((right-left)/1600,4),"previous_wet_fraction":round(float(prev.mean()),4),
            "terrain_wet_fraction":round(float(wet.mean()),4),"exposed_water_excluding_roofs_of_boulders_fraction":round(float((wet&~rock_mask).mean()),4),
            "native_wet_spans_px":intervals(px,wet),"exposed_water_spans_px":intervals(px,wet&~rock_mask)})
    if rows[-1]["terrain_wet_fraction"]<.845:
        raise ValueError("Native camera proof missed the bottom-coverage target: "+str(rows[-1]))
    left,right=apron.banks(line)
    l=left[11,:2];r=right[9,:2]
    probes={name:native_probe(terrain,xy) for name,xy in {
        "left_sod_lip":l-3.3*apron.RIGHT[:2],"scoured_left_toe":l+3.8*apron.RIGHT[:2],
        "right_submerged_gravel_shelf":r-2.5*apron.RIGHT[:2],"right_exposed_crescent":r+4.*apron.RIGHT[:2],
        "apron_centre_foreground":apron.intersect(790.,845.,line)[:2]}.items()}
    for entry in probes.values():
        xy=np.array(entry["xy_m"]);water=apron.surface(xy,line)
        entry["hydraulic_z_m"]=round(float(water),5)
        entry["bed_above_local_water_m"]=round(entry["ground_z_m"]-float(water),4)
    return {"camera":geometry["watercourses"][0]["apron"]["camera"],"terrain_sha256":terrain.manifest_sha256,
            "target_sha256":apron.head.sha256(apron.TARGET),"native_rock_ledger_sha256":apron.head.sha256(work/"dressing/flow-rocks.json"),
            "pixels_convention":"1600x900; even x pixels sampled; ray tested against actual quantized triangles to the local hydraulic surface",
            "method":"water intersects native triangle field mask, clipped by foreground native terrain, with separate native rock crown occlusion",
            "target_reference":"hand-traced approved river-erosion concept normalized from 1672x941",
            "camera_rows":rows,"rock_hulls":crowns,"flanks":flank_records,"native_probes":probes,
            "continuous_channel":corridor(terrain,line,geometry["watercourses"][0]["erosion_reach"],solids),
            "basin_containment":closed_sill(terrain,np.array(geometry["lakes"][-1]["polygon_m"]))}


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work",type=Path,default=apron.WORK)
    work=parser.parse_args().work
    result=survey(work)
    apron.head.save(work/"dressing/apron-survey.json",result)
    print(json.dumps(result,indent=2))

