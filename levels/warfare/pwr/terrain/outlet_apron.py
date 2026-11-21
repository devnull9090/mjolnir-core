"""Register the photographed outlet banks to the existing Pelican Warfare heightfield."""
import argparse
from pathlib import Path
import json
import tempfile

import numpy as np
from scipy.interpolate import PchipInterpolator
from scipy import ndimage

import northern_headwaters as head

HERE = Path(__file__).resolve().parent
WORK = head.ROOT / "out/pwr/river-apron"
PREVIOUS = head.ROOT / "out/pwr/river-erosion/terrain"
TARGET = head.ROOT / ".dream-loop/river-erosion/target.png"
EYE = np.array([-273., 785., 152.])
PITCH, YAW = np.deg2rad([-4.5376, -122.9694])
FORWARD_XY = np.array([np.cos(YAW), -np.sin(YAW)])
RIGHT = np.r_[-np.sin(YAW), -np.cos(YAW), 0.]
FORWARD = np.r_[FORWARD_XY*np.cos(PITCH), np.sin(PITCH)]
UP = np.r_[-FORWARD_XY*np.sin(PITCH), np.cos(PITCH)]
FOCAL = 800./np.tan(np.deg2rad(73./2.))

# Hand-traced water contact and gravel toe on the 1672 x 941 target, reviewed
# at 840 x 473. The two off-frame controls extend the physical bar past the eye.
# Columns are image y, left water contact x, and right water contact x.
TRACE = np.array([
    [720, -95, 943], [560, -51, 890], [472, 27, 796], [449, 31, 812],
    [423, 60, 760], [408, 77, 712], [392, 92, 666], [376, 125, 621],
    [358, 151, 581], [345, 183, 566], [333, 212, 570], [324, 231, 579],
    [315, 239, 593], [306, 231, 612], [296, 224, 632], [286, 205, 653],
    [275, 189, 675], [260, 172, 686], [242, 148, 702], [228, 131, 708],
], dtype=float) * np.array([900./473, 1600./840, 1600./840])


def project(xyz):
    delta = np.asarray(xyz)-EYE
    return np.stack((800.+FOCAL*(delta@RIGHT)/(delta@FORWARD),
                     450.-FOCAL*(delta@UP)/(delta@FORWARD)),axis=-1)


def rays(px, py):
    return FORWARD+np.asarray((px-800.)/FOCAL)[...,None]*RIGHT+np.asarray((450.-py)/FOCAL)[...,None]*UP


def surface(xy, line):
    xy = np.asarray(xy)
    _, i, t = head.nearest_line(xy.reshape(-1,2), line)
    return ((1.-t)*line[i,2]+t*line[i+1,2]).reshape(xy.shape[:-1])


def intersect(px, py, line):
    direction = rays(px, py)
    level = 142.4
    for _ in range(24):
        xyz = EYE+((level-EYE[2])/direction[...,2])[...,None]*direction
        next_level = surface(xyz[...,:2],line)
        if np.max(np.abs(next_level-level))<1e-7:
            break
        level = next_level
    return xyz


def coordinates(xy):
    delta = xy-EYE[:2]
    return delta@FORWARD_XY,delta@RIGHT[:2]


def banks(line):
    return [intersect(TRACE[:,side],TRACE[:,0],line) for side in (1,2)]


def curves(line):
    edges = []
    for bank in banks(line):
        distance,side = coordinates(bank[:,:2])
        # Each bank is ordered by physical distance to the camera.
        if np.any(np.diff(distance)<=0):
            raise ValueError("Folded outlet trace")
        edges.append(PchipInterpolator(distance,side,extrapolate=False))
    return edges


def profile(xy, line):
    distance,side = coordinates(xy)
    left_curve,right_curve = curves(line)
    def at(curve):
        return curve(np.clip(distance, curve.x[0], curve.x[-1]))
    left,right = at(left_curve),at(right_curve)
    # Irregularity remains below a native grid cell; the distinct lobes
    # themselves are set by the camera trace and span many native triangles.
    left += .32*np.sin(distance*.61)+.20*np.sin(distance*1.13)
    right += .28*np.sin(distance*.43+1.)+.17*np.sin(distance*.83)
    left_d, right_d = side-left, right-side
    width = right-left
    u = np.clip(left_d/width,0.,1.)
    # Slightly deeper lee pool, a low graded pebble bar on the east shore,
    # and a continuously submerged thalweg with a visible stony channel bed.
    depth = .48 + .48*np.exp(-((u-.27)/.18)**2)+.10*np.sin(distance*.35+u*3.)
    immersed = -depth * np.minimum(np.clip(left_d/1.65,0.,1.),np.clip(right_d/4.5,0.,1.))
    cut = np.interp(-left_d,[0,.7,2.0,3.4,7.,15.],[0,.31,1.30,1.67,1.87,2.30])
    cut += (.15*np.sin(distance*.67)+.12*np.cos(distance*.32))*head.smooth(-left_d/2.)
    bar = np.interp(-right_d,[0,2.5,5.,9.,14.,20.],[0,.18,.43,.89,1.31,1.62])
    raw = np.where(left_d<0,cut,np.where(right_d<0,bar,immersed))
    reach = head.smooth((distance+4.)/14.)*(1.-head.smooth((distance-57.)/21.))
    reach *= 1.-head.smooth((np.maximum(-left_d,-right_d)-5.)/11.)
    return raw,reach,left_d,right_d


def stage(out):
    base = head.load_heightfield(head.BASE)
    old = head.load_heightfield(PREVIOUS/"runtime-master.json")
    geo = json.loads((PREVIOUS/"terrain.geometry.json").read_text())
    main = geo["watercourses"][0]
    line = np.array(main["erosion_reach"]["centreline_m"])
    # Bound the sculpt; the blend fully expires inside these limits.
    coords = [np.arange(n)*d+o for n,d,o in zip(old.dimensions,old.spacing_m,old.origin_m)]
    slices = [slice(np.searchsorted(axis,lo),np.searchsorted(axis,hi)) for axis,lo,hi in zip(coords,[-378,746],[-237,903])]
    area = tuple(slices[::-1])
    xx,yy = np.meshgrid(coords[0][slices[0]],coords[1][slices[1]])
    xy = np.stack((xx,yy),axis=-1)
    raw,weight,left_d,right_d = profile(xy,line)
    if np.any(weight[[0,-1]]) or np.any(weight[:,[0,-1]]):
        raise ValueError("Cut extends beyond sculpt window")
    water = surface(xy,line)
    heights = old.heights_m.copy()
    prior = heights[area].copy()
    heights[area] = prior + weight*(water+raw-prior)
    if np.any((weight>0)&((base.masks["road"][area]>.01)|(base.masks["bases"][area]>.01))):
        raise ValueError("Apron entered protected roadway or base")
    masks = {k:v.copy() for k,v in old.masks.items()}
    active = weight>0
    wet = heights[area]<water
    # At the taper the flood mask follows the final blended bed. Do not
    # convert unrelated depressions outside the blended bank into open water.
    for name,target in (("water",wet),("shore",1.-head.smooth(abs(heights[area]-water)/2.2))):
        masks[name][area] += head.smooth(weight/.25)*(target-masks[name][area])
    masks["forest"][area] *= 1.-weight*np.maximum(masks["water"][area],.8*masks["shore"][area])
    dy,dx = np.gradient(heights,*base.spacing_m[::-1])
    masks["walkable"][area] = np.where(active,(np.hypot(dx[area],dy[area])<=.35)&(masks["water"][area]<.5),masks["walkable"][area])
    for name in ("protected","protected_core"):
        masks[name][area] = np.maximum(masks[name][area],active)
    edges = banks(line)
    main["apron"] = dict(coordinates="metres east north up", target_sha256=head.sha256(TARGET),
        camera=dict(position_m=EYE.tolist(), pitch_deg=-4.5376,yaw_deg=-122.9694,horizontal_fov_deg=73,viewport_px=[1600,900]),
        target_bank_pixels_y_left_right=TRACE.tolist(),
        left_bank_m=edges[0].tolist(),right_bank_m=edges[1].tolist(),forward_xy=FORWARD_XY.tolist(),
        fade_in_forward_m=[-4,10],fade_out_forward_m=[57,78],
        surface="nearest interpolated erosion_reach centreline elevation",
        left_bank="cut sod lip",right_bank="depositional crescent and submerged gravel toe")
    # Remove the obsolete sill width from the lake and river specifications.
    # Measure each surveyed cross section directly on the revised field below.
    def section_at(station):
        arc = head.arclength(line[:,:2])-main["erosion_reach"]["sill_station_m"]
        i = np.clip(np.searchsorted(arc,station)-1,0,len(arc)-2)
        t = (station-arc[i])/(arc[i+1]-arc[i])
        point = (1.-t)*line[i]+t*line[i+1]
        vec = line[i+1,:2]-line[i,:2]
        normal = np.array([-vec[1],vec[0]])/np.linalg.norm(vec)
        side = np.arange(-55.,55.01,.1)
        cross = point[:2]+side[:,None]*normal
        bed = ndimage.map_coordinates(heights,((cross[:,1]-base.origin_m[1])/base.spacing_m[1],(cross[:,0]-base.origin_m[0])/base.spacing_m[0]),order=1)
        wet = bed<surface(cross,line)-.02
        ids,n = ndimage.label(wet)
        label = ids[np.argmin(abs(side))]
        if not label:
            raise ValueError("Blocked river centre at station "+str(station))
        return [station,round(float((ids==label).sum()*.1),2),round(float(point[2]-bed[np.argmin(abs(side))]),3)]
    main["section_station_width_depth_m"] = [section_at(s) for s in [0,5,10,15,20,25,31,40,50,60]]
    geo["lakes"][-1]["outlet"]["width_m"] = main["section_station_width_depth_m"][0][1]
    out.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(dir=out.parent,prefix=".registered-apron-") as tmp:
        staged=Path(tmp)/"terrain"
        staged.mkdir()
        gp=staged/"terrain.geometry.json"
        head.save(gp,geo)
        source=staged/"authoring-master.json"
        head.write_heightfield(source,heights,base.origin_m,base.spacing_m,masks,
            generator="outlet_apron.py",geometry=gp.name,geometry_sha256=head.sha256(gp),water_level_m=base.metadata["water_level_m"],
            surface_interpolation="triangle_nw_se",parent_runtime_manifest_sha256=base.manifest_sha256,
            previous_erosion_sha256=old.manifest_sha256,landscape_encoding_policy=base.metadata["landscape_encoding_policy"])
        master=staged/"runtime-master.json"
        head.derive(source,master,components=base.metadata["landscape_encoding"]["components"])
        field=head.load_heightfield(master)
        changed=field.heights_m!=base.heights_m
        if np.any(changed&((base.masks["road"]>.01)|(base.masks["bases"]>.01))):
            raise ValueError("Changed an existing base or road")
        previous_geometry=json.loads((PREVIOUS/"terrain.geometry.json").read_text())
        if any(geo[k]!=previous_geometry[k] for k in ("sites","nodes","crossings","roads")):
            raise ValueError("Existing gameplay geometry changed")
        if np.any((field.heights_m!=old.heights_m)[~np.pad(active,[(area[0].start,field.heights_m.shape[0]-area[0].stop),(area[1].start,field.heights_m.shape[1]-area[1].stop)])]):
            raise ValueError("Unrelated terrain height changed")
        iy,ix=np.where(changed)
        probes=line[::4]
        depths=probes[:,2]-field.sample(*probes[:,:2].T)
        if np.min(depths)<.15:
            raise ValueError("A native triangle obstructs the watercourse")
        receipt=dict(schema="pwr-headwater-terrain-v1",parent_terrain_sha256=base.manifest_sha256,
                     previous_erosion_sha256=old.manifest_sha256,runtime_manifest_sha256=field.manifest_sha256,
                     geometry_sha256=head.sha256(gp),r16_sha256=head.sha256(master.with_suffix(".r16")),
                     water_level_m=geo["lakes"][-1]["water_z_m"],changed_bounds_m=[coords[0][ix.min()],coords[1][iy.min()],coords[0][ix.max()],coords[1][iy.max()]],
                     changed_vertices=int(changed.sum()),apron_changed_vertices_vs_previous=int((field.heights_m!=old.heights_m).sum()),
                     rock_sill_wet_width_m=main["section_station_width_depth_m"][0][1],minimum_native_centre_depth_m=float(depths.min()),
                     untouched_road_and_base_vertices=int(np.count_nonzero((base.masks["road"]>.01)|(base.masks["bases"]>.01))))
        head.save(staged/"headwater-terrain.receipt.json",receipt)
        if out.exists():
            if any(not (out/p.name).is_file() or head.sha256(p)!=head.sha256(out/p.name) for p in staged.iterdir()):
                raise ValueError(f"Different products at {out}")
        else:
            staged.rename(out)
    return receipt


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out",type=Path,default=WORK/"terrain")
    print(json.dumps(stage(parser.parse_args().out.resolve()),indent=2))

