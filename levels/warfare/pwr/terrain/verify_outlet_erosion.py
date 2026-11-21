"""Survey the final headwater cut, gravel bar, wet rock silhouettes and free channel."""
import argparse
import json
from pathlib import Path

import numpy as np
from scipy.spatial import ConvexHull

import headwater_dressing as dressing
from finalize_terrain import arclength, inside_polygon


def slice_hull(rock, elevation):
    vertices = np.asarray(rock["vertices_m"])
    faces = np.asarray(rock["faces"])
    edges = np.unique(np.sort(faces[:, [0,1,1,2,2,0]].reshape(-1,2),axis=1),axis=0)
    a,b = vertices[edges[:,0]],vertices[edges[:,1]]
    valid = (a[:,2]<elevation)!=(b[:,2]<elevation)
    a,b = a[valid],b[valid]
    t = (elevation-a[:,2])/(b[:,2]-a[:,2])
    crossings = a+t[:,None]*(b-a)
    if len(crossings)<3:
        raise ValueError("Missing wet hull at "+rock["id"])
    return crossings[ConvexHull(crossings[:,:2]).vertices]


def survey(work):
    terrain = dressing.load_heightfield(work/"terrain/runtime-master.json")
    old = dressing.load_heightfield(dressing.HEADWATER/"terrain/runtime-master.json")
    water = dressing.read(work/"dressing/flow-rocks.json")
    if water["terrain_sha256"] != terrain.manifest_sha256:
        raise ValueError("Rock survey uses a different terrain")
    geometry = dressing.read(work/"terrain"/terrain.metadata["geometry"])
    reach = geometry["watercourses"][0]["erosion_reach"]
    line = np.array(reach["centreline_m"])
    arc = arclength(line[:,:2])-reach["sill_station_m"]
    # Reuse the actual registered .33 camera matrix for direct screen comparison.
    camera = np.array([-273,785,152])
    view = np.array([-321,859,145])-camera
    view = view/np.linalg.norm(view)
    right = np.cross(view,[0,0,1])
    right /= np.linalg.norm(right)
    up = np.cross(right,view)
    focal = 800/np.tan(np.deg2rad(73/2.))
    block = []
    rocks = []
    for rock in water["rocks"]:
        vertices = np.asarray(rock["vertices_m"])
        crossing = slice_hull(rock,rock["surface_z_m"])
        crown = np.vstack((vertices[vertices[:,2]>rock["surface_z_m"]],crossing))-camera
        projected = np.stack((800+focal*(crown@right)/(crown@view),
                              450-focal*(crown@up)/(crown@view)),axis=1)
        rocks.append({"id":rock["id"],"exposed_m":round(float(vertices[:,2].max()-rock["surface_z_m"]),3),
                      "outlet_camera_bbox_px":[*projected.min(0).round(1),*projected.max(0).round(1)]})
        block.append(slice_hull(rock,rock["surface_z_m"]-.15)[:,:2])
    free = []
    normal_dist = np.arange(-23.,23.01,.05)
    for s in np.arange(-13.,25.01,.25):
        i = max(0,np.searchsorted(arc,s)-1)
        t = (s-arc[i])/(arc[i+1]-arc[i])
        centre = (1.-t)*line[i]+t*line[i+1]
        tangent = line[i+1,:2]-line[i,:2]
        n = np.array([-tangent[1],tangent[0]])/np.linalg.norm(tangent)
        xy = centre[:2]+normal_dist[:,None]*n
        wet = terrain.sample(*xy.T)<centre[2]-.15
        solid = np.logical_or.reduce([inside_polygon(*xy.T,poly) for poly in block])
        changes = np.flatnonzero(np.diff(np.r_[False,wet&~solid,False]))
        runs = np.diff(changes.reshape(-1,2),axis=1) if changes.size else [0]
        free.append(.05*int(np.max(runs)))
    if min(free) < 2.5:
        raise ValueError(f"Rocks pinch the outlet to {min(free)} m")
    pts={"cutbank_lip":(-297.55,795.75),"scoured_toe":(-293.53,798.74),"submerged_gravel_bar":(-281.17,798.53),
         "east_bank_camera":(-275.08,812.47)}
    probes={k:{"xy_m":list(xy),"ground_z_m":float(terrain.sample(*xy)),
               "change_vs_33_m":float(terrain.sample(*xy)-old.sample(*xy))} for k,xy in pts.items()}
    if not (probes["cutbank_lip"]["change_vs_33_m"]>.70 and probes["scoured_toe"]["change_vs_33_m"]<-.70
            and probes["submerged_gravel_bar"]["change_vs_33_m"]>1.):
        raise ValueError("Native cutbank or point bar lacks measurable profile")
    return {"terrain_sha256":terrain.manifest_sha256,"rock_hulls":rocks,
            "terrain_probes":probes,"minimum_free_contiguous_width_m":min(free),
            "minimum_width_station_m":float(-13.+np.argmin(free)*.25),
            "survey_depth_m":.15,"station_step_m":.25,"cross_sample_m":.05,
            "surveyed_stations_m":[-13.,25.]}


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work",type=Path,default=dressing.ROOT/"out/pwr/river-erosion")
    work=parser.parse_args().work
    result=survey(work)
    dest=work/"dressing/erosion-survey.json"
    dest.write_text(json.dumps(result,indent=2)+"\n")
    print(json.dumps(result,indent=2))
