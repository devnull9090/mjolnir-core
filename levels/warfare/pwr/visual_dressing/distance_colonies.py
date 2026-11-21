"""Build map-owned grass drifts, dry bank beds and woodland margins on PWR's actual field."""
from pathlib import Path
import argparse
import json
import math
import sys

import numpy as np
from PIL import Image
from scipy.ndimage import distance_transform_edt, map_coordinates
from scipy.spatial import cKDTree

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "tools/level"))
import landscape_grass_pilot as grass
import pcg_foliage as pcg
from heightfield import load_heightfield
from foliage_bake import PAKS, mesh_info

OUT = ROOT / "out/pwr/landscape-distance/vegetation"
BASE = ROOT / "out/pwr/world-art/foliage-r2"
MASTER = ROOT / "levels/warfare/pwr/terrain/runtime-v5/runtime-master.json"
LEVEL = ROOT / "out/pwr/base-polish/saturday.7/map-input/pwr.level.json"
TREES = ROOT / "out/pwr/visual-v6/scenery/trees/trees.selected.json"
PREVIOUS_SUPPORT_SHA = "97211673baadb9487d5d147390d8db9588aefdd884a2b0124d69a0874ed4657a"
SEED = 74719
FAMILIES = {
    "rye": ("/Game/Megascans/3D_Plants/Tall_Grass_rbeki/SM_Tall_Grass_rbeki_01", 155, 305),
    "sedge": ("/Game/Env/Bio/Grass/Sedges/Grass_Sedges_A/SM_Grass_Sedges_A_Leaves_A", 165, 340),
    "rush": ("/Game/Env/Bio/Grass/Rushes/Grass_Rushes_A/SM_Grass_Rushes_A", 160, 355),
    "brush": ("/Game/Megascans/3D_Plants/Yellow_Rabbitbrush_vdtlcbjia/S_Yellow_Rabbitbrush_vdtlcbjia_0_Var1_lod0", 245, 495),
    "sapling": ("/Game/Env/Bio/Tree/Pine/Tree_Pine_Sapling_A/Meshes/SM_Tree_Pine_Sapling_A", 330, 685),
}


def dump(path, data, *, compact=False):
    path.write_text(json.dumps(data, indent=None if compact else 2,
                               separators=(",", ":") if compact else None) + "\n", encoding="utf-8")


def to_raster(x, y, field):
    return np.asarray([field.dimensions[1]-1-(y-field.origin_m[1])/field.spacing_m[1],
                       (x-field.origin_m[0])/field.spacing_m[0]])


def prepare(out):
    # This reviewed mask already excludes native rock and tree hulls, paving,
    # bridges, protected surface probes, steep slopes, water, roads and bases.
    if grass.digest(BASE / "eligible.npy") != PREVIOUS_SUPPORT_SHA:
        raise ValueError("Regenerate the exclusion audit for the new site layout")
    field = load_heightfield(MASTER)
    if field.dimensions != (1009, 1009):
        raise ValueError("Expected the 2 km playtest terrain")
    step = field.spacing_m[0]
    yy, xx = np.indices(field.heights_m.shape)
    gx = field.origin_m[0] + xx*step
    gy = field.origin_m[1] + (field.dimensions[1]-1-yy)*step
    eligible = np.load(BASE/"eligible.npy")
    # Keep the widest native crown, as well as the root, outside the old exclusion.
    eligible = distance_transform_edt(eligible)*step > 2.8
    level = pcg.load(LEVEL)
    for entry in level["blam"]["vehicles"] + level["blam"]["player_starts"]:
        x, y = entry["pos"][:2]
        eligible &= (gx-.01*x)**2+(gy+.01*y)**2 > 11**2
    for x, y, _, radius in level["koth_hills"]:
        eligible &= (gx-.01*x)**2 + (gy+.01*y)**2 > (.01*radius+5)**2
    road = np.flipud(field.masks["road"]) > 0
    water = np.flipud(field.masks["water"]) > 0
    base = np.flipud(field.masks["bases"]) > 0
    road_gap = distance_transform_edt(~road)*step
    wet_gap = distance_transform_edt(~water)*step
    base_gap = distance_transform_edt(~base)*step
    eligible &= (road_gap >= 9) & (base_gap >= 13) & (wet_gap >= 4)
    np.save(out/"eligible.npy", eligible)
    centers = []
    candidates = []
    masks = np.zeros((*eligible.shape, 3), dtype=np.float32)
    crowns = cKDTree([p["position"][:2] for p in pcg.load(TREES)["instances"]])
    rng = np.random.default_rng(SEED)
    for row in np.arange(-964., 965., 34.):
        for col in np.arange(-964., 965., 34.):
            x, y = np.array([col,row])+rng.uniform(-12,12,2)
            iy, ix = np.rint(to_raster(x,y,field)).astype(int)
            if not eligible[iy,ix]:
                continue
            tree_gap = crowns.query([x,y])[0]
            wet = wet_gap[iy,ix] < 43
            woods = 5 < tree_gap < 35
            if rng.random() > (.93 if wet else .74 if woods else .54):
                continue
            # Meandering drifts follow the contour. Cross-slope jitter and
            # alternating crown widths keep roadside views from showing rows.
            dx = float(field.sample(x+2,y)-field.sample(x-2,y))*.25
            dy = float(field.sample(x,y+2)-field.sample(x,y-2))*.25
            angle = math.atan2(dx,-dy)+rng.normal(0,.39)
            if dx*dx+dy*dy < .00045:
                angle = .37+.57*math.sin(x/125.)+rng.normal(0,.45)
            co, si = math.cos(angle), math.sin(angle)
            radius, width = rng.uniform(9,20), rng.uniform(4.0,8.3)
            rowslice = slice(max(0,iy-13), min(len(eligible),iy+14))
            colslice = slice(max(0,ix-13), min(len(eligible),ix+14))
            ex, ey = gx[rowslice,colslice]-x, gy[rowslice,colslice]-y
            long = (ex*co+ey*si)/radius
            short = (-ex*si+ey*co)/width - .29*np.sin(long*2.4)
            weight = np.maximum(0,1-long**2-short**2)
            channel = 1 if wet else 2 if woods else 0
            region = masks[rowslice,colslice,channel]
            np.maximum(region,np.sqrt(weight)*eligible[rowslice,colslice],out=region)
            centers.append([round(x,3),round(y,3),channel,round(radius,2),round(width,2)])
            for _ in range(int(rng.integers(19,38))):
                u,v=rng.uniform(-1,1,2)
                if u*u+v*v >= 1:
                    continue
                a = u*radius
                b = (v+.29*math.sin(u*2.4))*width
                px, py = x+a*co-b*si, y+a*si+b*co
                pyx = to_raster(px,py,field)
                iy0,ix0=np.floor(pyx).astype(int)
                if not eligible[iy0:iy0+2,ix0:ix0+2].all():
                    continue
                pick = rng.random()
                if wet:
                    kind = "rush" if pick < .64 else "sedge"
                elif woods:
                    kind = "sapling" if pick < .16 else "brush" if pick < .48 else "sedge" if pick < .78 else "rye"
                else:
                    kind = "rye" if pick < .66 else "sedge" if pick < .92 else "brush"
                # Woody volunteers cluster less tightly than grass on the same bed.
                density = (.59 if kind in ("sapling","brush") else .86)*(.76+.24*(1-u*u-v*v))
                candidates.append((px,py,kind,density))
    Image.fromarray(np.rint(255*masks).astype(np.uint8)).save(out/"plant-footprints.png")
    if not candidates:
        raise ValueError("No eligible colony points")
    px,py=np.array([p[:2] for p in candidates]).T
    z=field.sample(px,py)
    norm=np.c_[(field.sample(px-1,py)-field.sample(px+1,py))*.5,
               (field.sample(px,py-1)-field.sample(px,py+1))*.5,np.ones(len(px))]
    norm/=np.linalg.norm(norm,axis=1)[:,None]
    points=[dict(id=i,position=[round(px[i],6),round(py[i],6),round(z[i],6)],
                 normal=norm[i].round(8).tolist(),kind=p[2],density=round(p[3],7),biome_mask=1)
            for i,p in enumerate(candidates)]
    source=out/"points.json"
    dump(source,dict(schema=1,align_to_normal=True,points=points),compact=True)
    dump(out/"centers.json",centers,compact=True)
    dump(out/"request.json",{"jobs":[dict(input=str(source),output=str(out/(label+".json")),seed=SEED,
        scale_min=.85,scale_max=1.15,graph="/Game/MJOLNIR/PCGAuthoring/PWRDistance/"+label)
        for label in ("PCG_Colonies","PCG_Repeat")]})
    dump(out/"palette.json",{"kinds":{k:dict(meshes=[p+"."+p.rsplit("/",1)[1]],cull=[100*a,100*b],
             bands=1,shadow=False,static=True,rule=k) for k,(p,a,b) in FAMILIES.items()}})
    print(f"{len(centers)} colonies, {len(points)} candidates, {int((masks.max(axis=2)>0).sum())} habitat pixels")


def finish(out):
    proof=pcg.compare(out/"points.json",out/"PCG_Colonies.json",out/"PCG_Repeat.json")
    selected=pcg.adapt(out/"points.json",out/"PCG_Colonies.json",out/"palette.json",out,"colonies")
    rows=selected["instances"]
    if len(rows)>15000 or len(rows)<400:
        raise ValueError(f"Unexpected colony size {len(rows)}")
    groups=[]
    for group,_,_,count in pcg.read_mjf_groups(out/"colonies.json")[1]:
        bounds=mesh_info(str(ROOT/"target/release/mjolnir.exe"),PAKS,group["mesh"])
        groups.append(dict(group,count=count,origin=bounds["origin"],extent=bounds["extent"],standin_slots=bounds["slots"]))
    field=load_heightfield(MASTER)
    xy=np.array([p["position"] for p in rows])
    px,py,pz=xy.T
    coords=to_raster(px,py,field)
    support=map_coordinates(np.load(out/"eligible.npy").astype(float),coords,order=1,mode="constant",prefilter=False)
    route_hits={mask:int(np.count_nonzero(field.sample_mask(mask,px,py)>0)) for mask in ("road","water","bases")}
    height_error=float(np.max(np.abs(field.sample(px,py)-pz)))
    if support.min()<.99999 or any(route_hits.values()) or height_error>.001:
        raise ValueError("Output violates frozen terrain or exclusions")
    binary=out/"colonies.bin"
    doc=dict(file=binary.name, groups=groups, count=len(rows),binary_sha256=grass.digest(binary),
             exact_sidecars=[grass.digest(str(binary)+".xf"+str(i)) for i in range(1,len(groups)+1)])
    dump(out/"hism.json",doc)
    report=dict(schema="pwr-distance-colonies-v1",pcg=proof,colonies=len(pcg.load(out/"centers.json")),
        draws_by_kind={g["rule"]:g["count"] for g in groups},centers_on_excluded_masks=route_hits,
        min_interpolated_eligible=float(support.min()),maximum_projection_error_m=height_error,
        source_layer_sha256=PREVIOUS_SUPPORT_SHA, footprint_sha256=grass.digest(out/"plant-footprints.png"),
        level_sha256=grass.digest(LEVEL), mesh_groups=len(groups), instance_budget=15000,instances=len(rows),
        actor="PWR_DistanceColonies",baked_native_hism=True,runtime_pcg=False)
    dump(out/"receipts.json",report)
    print(json.dumps(report))


if __name__=="__main__":
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("phase",choices=("prepare","finish"))
    ap.add_argument("--out",type=Path,default=OUT)
    args=ap.parse_args()
    folder=args.out.resolve()
    folder.mkdir(parents=True,exist_ok=True)
    (prepare if args.phase=="prepare" else finish)(folder)
