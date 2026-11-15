"""Isolated PWR visual-v4 candidate. Never writes frozen inputs or installs assets.

prepare -> actual UE PCG request -> export -> shared native hull generation.
apron creates a render-only stitched outer mesh, never gameplay terrain.
"""
import argparse
import copy
import hashlib
import json
import math
from pathlib import Path
import struct
import sys

import numpy as np

REPO = Path(__file__).resolve().parents[4]
OUT = REPO / "out/pwr/visual-v4"
sys.path.insert(0, str(REPO / "tools/level"))
from heightfield import load_heightfield
from refine_water_gltf import euclidean_distance_to
import b30_collision
import pcg_foliage

MASTER = REPO / "levels/warfare/pwr/terrain/runtime-v3/runtime-master.json"
EXPECTED_MASTER = "814c7a8b3796394f2a8027c10b9577424acff5c23972d65265f9d86f3b7fd3ec"
SOURCE_ROCKS = REPO / "out/pwr/pcg-v3/rocks/authored_decor.json"
SOURCE_TREES = REPO / "out/pwr/pcg-v3/trees.selected.json"
ASSET_DIR = OUT / "assets"
ROCK_HULLS = REPO / "out/pwr/pcg-v3/rocks/hulls"
SOURCE_GRASS = REPO / "out/pwr/pcg-v3/grass/foliage.json"
APRON_RADIAL_STEP = None  # Historical v4 defaults; replacement fields use100m.
APRON_SNOW = False
ASSETS = {
    "macro": {"leaf": "SM_PNWGL_Rock_Macro_B", "spacing": 165, "scale": [.22, .40],
              "target": 22, "slope": [.32, 3.0], "height": [165, 365], "bury": .14},
    "cliff": {"leaf": "SM_Rock_Uluwatu_Cliff_B", "spacing": 43, "scale": [.45, .85],
              "target": 65, "slope": [.35, 2.5], "height": [130, 360], "bury": .16},
    "shelf": {"leaf": "SM_MassiveTundraRockFormation_01", "spacing": 43, "scale": [.35, .65],
              "target": 40, "slope": [.10, .85], "height": [125, 300], "bury": .10},
}


def dump(path, data):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def add_source_arguments(parser):
    parser.add_argument("--master",type=Path,help="Verified runtime master; default remains frozen v3")
    parser.add_argument("--expected-master",help="Optional explicit SHA256 for a new master")
    parser.add_argument("--trees",type=Path,help="Selected actual-PCG tree receipt")
    parser.add_argument("--rocks",type=Path,help="Authored native boulder placements")
    parser.add_argument("--grass",type=Path,help="Actual-PCG grass foliage.json before rock exclusions")
    parser.add_argument("--out",type=Path,help="Independent output root; default remains visual-v4")
    parser.add_argument("--assets",type=Path,help="Reuse verified exported stock asset cache")
    parser.add_argument("--rock-hulls",type=Path,help="Reuse verified native boulder hull cache")
    parser.add_argument("--apron-radial-step",type=float,help="Maximum ring spacing in metres (new masters default100)")
    parser.add_argument("--apron-snow",choices=("on","off"),help="Native height/slope Snowblend material (new masters defaulton)")


def configure(args):
    global MASTER,EXPECTED_MASTER,SOURCE_TREES,SOURCE_ROCKS,OUT,ASSET_DIR,ROCK_HULLS,SOURCE_GRASS,APRON_RADIAL_STEP,APRON_SNOW
    if args.master is not None:
        MASTER=args.master.resolve()
        EXPECTED_MASTER=args.expected_master or load_heightfield(MASTER).manifest_sha256
        APRON_RADIAL_STEP=100.
        APRON_SNOW=True
        if args.out is None:raise ValueError("A replacement master requires an isolated --out directory")
        if getattr(args,"command",None)=="prepare" and args.trees is None:
            raise ValueError("New terrain candidate generation requires explicit --trees")
        if getattr(args,"command",None)=="nonsnow" and args.rocks is None:
            raise ValueError("New terrain rock materials require explicit --rocks")
        if getattr(args,"command",None)=="audit" and args.grass is None:
            raise ValueError("New terrain vegetation audit requires explicit --grass")
    elif args.expected_master is not None:EXPECTED_MASTER=args.expected_master
    if args.apron_snow is not None:APRON_SNOW=args.apron_snow=="on"
    if args.apron_radial_step is not None:
        if not math.isfinite(args.apron_radial_step) or not 25<=args.apron_radial_step<=100:
            raise ValueError("Apron radial step must be finite25..100m")
        APRON_RADIAL_STEP=args.apron_radial_step
    for key,argument in (("SOURCE_TREES","trees"),("SOURCE_ROCKS","rocks"),("OUT","out"),
                         ("ASSET_DIR","assets"),("ROCK_HULLS","rock_hulls"),("SOURCE_GRASS","grass")):
        value=getattr(args,argument,None)
        if value is not None:globals()[key]=value.resolve()
    if MASTER != (REPO/"levels/warfare/pwr/terrain/runtime-v3/runtime-master.json") and OUT==(REPO/"out/pwr/visual-v4"):
        raise ValueError("Replacement terrain must not overwrite visual-v4 outputs")
    field()  # Hash/format validation before any output mutation.


def field():
    f = load_heightfield(MASTER)
    if f.manifest_sha256 != EXPECTED_MASTER:
        raise ValueError("Frozen runtime terrain changed; review and re-author candidate")
    return f


def load_assets():
    catalogue = pcg_foliage.load(ASSET_DIR / "rock-bounds.json")
    result = copy.deepcopy(ASSETS)
    for name, spec in result.items():
        mesh = next(x for x in catalogue if x["path"].split(".")[-1] == spec["leaf"])
        spec.update(mesh=mesh["path"], bounds_cm={"min": mesh["min"], "max": mesh["max"]})
        # Conservative yaw-independent envelope, measured from actual pivot.
        radius = math.hypot(max(abs(mesh["min"][0]), abs(mesh["max"][0])),
                            max(abs(mesh["min"][1]), abs(mesh["max"][1]))) / 100
        spec["max_radius_m"] = radius * spec["scale"][1]
        log = (ASSET_DIR / (spec["leaf"] + ".export.log")).read_text(encoding="utf-8-sig")
        if "nanite:" not in log or "not decoded" in log:
            raise ValueError("No successful native Nanite proof for " + spec["leaf"])
        spec["nanite_export_receipt"] = log.strip().splitlines()[0].strip()
    return result


def sample_array(f, data, x, y):
    u = (np.asarray(x) - f.origin_m[0]) / f.spacing_m[0]
    v = (np.asarray(y) - f.origin_m[1]) / f.spacing_m[1]
    xi = np.clip(np.floor(u).astype(int), 0, data.shape[1] - 2)
    yi = np.clip(np.floor(v).astype(int), 0, data.shape[0] - 2)
    a, b = u - xi, v - yi
    return ((1-a)*(1-b)*data[yi,xi] + a*(1-b)*data[yi,xi+1]
            + (1-a)*b*data[yi+1,xi] + a*b*data[yi+1,xi+1])


def prepare():
    f, assets = field(), load_assets()
    masks = f.masks
    forbidden = ((masks["road"] > .002) | (masks["water"] > .002)
                 | (masks["shore"] > .02) | (masks["bases"] > .002))
    # Full-grid EDT protects every cell within the yaw-independent footprint;
    # it cannot miss a narrow road between sparse ring probes.
    clearance = euclidean_distance_to(forbidden, f.spacing_m[0], 4000)
    trees = np.array([p["position"][:2] for p in pcg_foliage.load(SOURCE_TREES)["instances"]])
    jobs, receipt = [], {}
    # The three source lattices are disjoint. Graph performs all stochastic
    # point selection, mesh draw, rotation and scale. Python is masks/projection.
    for number, (kind, spec) in enumerate(assets.items()):
        step, radius = spec["spacing"], spec["max_radius_m"]
        axis = np.arange(-950 + radius, 950 - radius, step)
        xx, yy = np.meshgrid(axis, axis)
        ci, ri = np.meshgrid(np.arange(len(axis)), np.arange(len(axis)))
        xx = xx + .20*step*np.sin(ci*2.399 + ri*1.113 + number)
        yy = yy + .20*step*np.sin(ri*2.173 + ci*1.719 + number)
        x, y = xx.ravel(), yy.ravel()
        z = f.sample(x, y)
        dx = (f.sample(x+3,y)-f.sample(x-3,y))/6
        dy = (f.sample(x,y+3)-f.sample(x,y-3))/6
        slope = np.hypot(dx,dy)
        distance = sample_array(f,clearance,x,y)
        # 2 grid cells cover raster/interpolation uncertainty;8m remains extra
        # beyond the largest possible rendered/collision footprint.
        allowed = ((distance > radius+12) & (slope >= spec["slope"][0])
                   & (slope <= spec["slope"][1]) & (z >= spec["height"][0])
                   & (z <= spec["height"][1]))
        nearest = np.min(np.sum((np.c_[x,y][:,None] - trees[None])**2,axis=2),axis=1)**.5
        allowed &= nearest > radius+8
        # Mineral bands broken into irregular clusters, never even wall rows.
        patch = np.clip(.55 + .28*np.sin(x/163+.8*np.sin(y/101)) + .25*np.cos(y/131),.04,1)
        density = np.where(allowed,patch,0)
        low, high = 0.,10000.
        target = min(spec["target"],.99*allowed.sum())
        for _ in range(60):
            scale=(low+high)/2
            if np.minimum(density*scale,1).sum()<target: low=scale
            else: high=scale
        density=np.minimum(density*((low+high)/2),1)
        points=[{"id": i,"position":[float(x[i]),float(y[i]),float(z[i])],
                 "normal":[0,0,1],"density":float(density[i]),"biome_mask":int(allowed[i]),
                 "kind":kind,"biome":"rock_outcrop","clearance_m":float(distance[i]),
                 "tree_clearance_m":float(nearest[i])} for i in range(len(x))]
        path=OUT/(kind+".candidates.json")
        dump(path,{"schema":1,"align_to_normal":False,"master_sha256":f.manifest_sha256,
                   "height_sha256":f.metadata["height"]["sha256"],"points":points})
        for suffix in ("","_repeat"):
            jobs.append({"input":str(path),"output":str(OUT/(kind+suffix+".pcg.json")),
                         "graph":"/Game/MJOLNIR/PCGAuthoring/PWRVisualV4/PCG_"+kind+suffix,
                         "seed":20580+number,"scale_min":spec["scale"][0],"scale_max":spec["scale"][1]})
        receipt[kind]={"candidates":len(x),"allowed":int(allowed.sum()),"expected":float(density.sum()),
                       "radius_m":radius,"extra_clearance_m":12,"tree_extra_clearance_m":8,
                       "source_sha256":digest(path)}
    dump(OUT/"assets/selected-assets.json",assets)
    dump(OUT/"request.json",{"jobs":jobs})
    dump(OUT/"prepare.receipt.json",{"runtime_master_sha256":f.manifest_sha256,"kinds":receipt,
         "selected_trees_sha256":digest(SOURCE_TREES),"asset_catalogue_sha256":digest(ASSET_DIR/"rock-bounds.json")})
    print(json.dumps(receipt,indent=2))


def nonsnow():
    document=pcg_foliage.load(SOURCE_ROCKS)
    original=copy.deepcopy(document["decor"])
    overrides={
        "Lrg_A":"/Game/Env/Bio/Rock/PNW/Rock_PNW_Lrg_A/Materials/MI_Rock_PNW_Lrg_A",
        "Lrg_B":"/Game/Env/Bio/Rock/Glacial/Rock_Glacial_Lrg_B/Materials/MI_Rock_Glacial_Lrg_B_NoSnow",
        "Lrg_C":"/Game/Env/Bio/Rock/Glacial/Rock_Glacial_Lrg_C/Materials/MI_Rock_Glacial_Lrg_C_NoSnow",
        "Med_A":"/Game/Env/Bio/Rock/Glacial/Rock_Glacial_Med_A/Materials/MI_Rock_Glacial_Med_A_NoSnow",
        "Med_B":"/Game/Env/Bio/Rock/Glacial/Rock_Glacial_Med_B/Materials/MI_Rock_Glacial_Med_B_NoSnow",
        # Native Med_C itself uses Lrg_C's material: preserve that matching UV recipe.
        "Med_C":"/Game/Env/Bio/Rock/Glacial/Rock_Glacial_Lrg_C/Materials/MI_Rock_Glacial_Lrg_C_NoSnow",
    }
    for item in document["decor"]:
        key=item["mesh"].split(".")[-1].replace("SM_Rock_Glacial_","")
        parent=overrides[key]
        item["materials"]=[{"parent":parent+"."+parent.rsplit("/",1)[-1]}]
    for before,after in zip(original,document["decor"]):
        assert all(before[k]==after[k] for k in ("id","mesh","pos","rot","scale"))
    document["visual_v4_provenance"]={"source_sha256":digest(SOURCE_ROCKS),"change":"material_only",
        "collision_unchanged":True,"original_native_hulls_sha256":digest(SOURCE_ROCKS.parent/"native-hulls.json")}
    dump(OUT/"temperate-rocks.authored-decor.json",document)
    print("Preserved",len(original),"native rock transforms/meshes; replaced snow materials only")


def convex2(points):
    p=sorted(set(tuple(v) for v in points))
    def cross(a,b,c): return (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])
    hull=[]
    for v in p:
        while len(hull)>=2 and cross(hull[-2],hull[-1],v)<=0: hull.pop()
        hull.append(v)
    lower=len(hull)
    for v in p[-2::-1]:
        while len(hull)>lower and cross(hull[-2],hull[-1],v)<=0: hull.pop()
        hull.append(v)
    return hull[:-1]


def export():
    f,assets=field(),load_assets()
    decor,exclusions,receipts=[],[],[]
    for kind,spec in assets.items():
        source=pcg_foliage.load(OUT/(kind+".candidates.json"))
        if source.get("master_sha256")!=f.manifest_sha256:raise ValueError("Outcrop candidates refer to a different runtime master")
        generated=pcg_foliage.load(OUT/(kind+".pcg.json"))
        repeat=pcg_foliage.load(OUT/(kind+"_repeat.pcg.json"))
        if generated["source_sha256"]!=digest(OUT/(kind+".candidates.json")):
            raise ValueError("PCG source changed")
        # Graph name differs for independent repeat. Compare actual points exactly.
        assert generated["points"]==repeat["points"], "PCG repeat nondeterministic"
        pairs=pcg_foliage.validate_output(source,generated)
        local=b30_collision.glb_positions(ASSET_DIR/(spec["leaf"]+".glb"))
        sample=local[np.linspace(0,len(local)-1,min(8000,len(local))).astype(int)]
        for original,p in pairs:
            scale=p["scale_xyz"][0]
            yaw=-pcg_foliage.authored_yaw(p["rotation_xyzw"])
            rotation=b30_collision.rotator_matrix(0,yaw,0)
            rotated=sample*scale@rotation
            pos=np.array(p["position_cm"])
            tx=(rotated[:,0]+pos[0])/100
            ty=-(rotated[:,1]+pos[1])/100
            support=f.sample(tx,ty)
            height=(spec["bounds_cm"]["max"][2]-spec["bounds_cm"]["min"][2])*scale
            # Embed the foot into the hillside. This placement is applied once
            # to the actor and its native hull, not a visual-only WPO adjustment.
            base=np.quantile(support,.15)*100
            pos[2]=base-spec["bounds_cm"]["min"][2]*scale-spec["bury"]*height
            above=rotated[:,2]+pos[2]-support*100
            # A low shelf across a slope can otherwise vanish. A bounded lift
            # ensures the upper quarter is visible without floating its foot.
            lift=max(0.,.20*height-float(np.quantile(above,.80)))
            pos[2]+=min(lift,.35*height)
            item={"id":f"pcg_v4_{kind}_{original['id']}","mesh":spec["mesh"],
                  "pos":pos.tolist(),"rot":[0,yaw,0],"scale":p["scale_xyz"],"static":True}
            decor.append(item)
            world=rotated+pos
            footprint=convex2(np.c_[world[:,0]/100,-world[:,1]/100].round(4))
            exclusions.append({"id":item["id"],"polygon_m":footprint,
                               "z_min_m":float(world[:,2].min()/100),"z_max_m":float(world[:,2].max()/100)})
            receipts.append({"id":item["id"],"kind":kind,"support_position_m":original["position"],
                             "actor_position_cm":pos.tolist(),"source_clearance_m":original["clearance_m"],
                             "required_clearance_m":spec["max_radius_m"]+12,
                             "visible_source_vertex_fraction":float(np.mean(world[:,2]>support*100))})
    assert 1<=len(decor)<=145, f"Review outcrop count {len(decor)}"
    result={"schema_version":1,"coordinates":"unreal_centimetres","decor":decor,"background_trees":[],
            "visual_v4_provenance":{"runtime_master_sha256":f.manifest_sha256,
                 "generator":"UE5.5 UPCGGraph", "source_request_sha256":digest(OUT/"request.json")}}
    dump(OUT/"outcrops.authored-decor.json",result)
    dump(OUT/"vegetation-exclusions.json",{"schema":"pwr-vegetation-exclusions-v1",
         "coordinates":"authoring_metres_z_up","footprints":exclusions})
    dump(OUT/"outcrops.receipt.json",{"count":len(decor),"instances":receipts,
         "collision":"Generate from this exact authored_decor using b30_collision --only swap"})
    print("Exported",len(decor),"outcrops with deterministic repeated graph output")


def smooth01(t):
    t=np.clip(t,0,1); return t*t*(3-2*t)


def apron_rings(maximum_step=None):
    original=[(1000,1),(1004,1),(1016,2),(1050,2),(1125,4),(1250,4),
              (1450,8),(1750,8),(2150,16),(2650,16),(3250,16),(4000,16)]
    if maximum_step is None:return original
    result=[original[0]]
    for (a,first_skip),(b,last_skip) in zip(original[:-1],original[1:]):
        count=math.ceil((b-a)/maximum_step)
        result.extend((a+(b-a)*i/count,last_skip if i==count else first_skip) for i in range(1,count+1))
    return result


def apron():
    f=field(); count=f.dimensions[0]-1
    assert f.dimensions==(1009,1009)
    # Counter-clockwise boundary, every runtime Landscape vertex exactly once.
    axis=np.linspace(-1000,1000,count+1)
    boundary=np.vstack([np.c_[axis[:-1],np.full(count,-1000)],
                        np.c_[np.full(count,1000),axis[:-1]],
                        np.c_[axis[:0:-1],np.full(count,1000)],
                        np.c_[np.full(count,-1000),axis[:0:-1]]])
    ring_specs=apron_rings(APRON_RADIAL_STEP)
    vertices=[]; rings=[]
    # Broad asymmetric massifs, with eroded variation taken from the real Gaea
    # field. No new terrain can overlap the frozen playable square.
    massifs=[(-1850,250,620,620,1250),(1750,650,790,600,1050),(-800,2300,660,1050,650),
             (1250,2700,800,750,900),(-2350,-2050,650,850,650),(2200,-1850,520,700,1050),
             (-300,-2950,430,1400,650)]
    for radius,skip in ring_specs:
        edge=boundary[::skip]
        xy=edge*(radius/1000)
        radial=xy-edge; distance=np.linalg.norm(radial,axis=1)
        direction=radial/np.maximum(distance[:,None],1e-9)
        edgeheight=f.sample(edge[:,0],edge[:,1])
        inner=edge-direction*20
        gradient=np.clip((edgeheight-f.sample(inner[:,0],inner[:,1]))/20,-.6,.6)
        # Smooth near-edge extrapolation matches all boundary elevations and
        # preserves the mountain's direction before broad distant massifs take over.
        tangent=edgeheight+gradient*180*(1-np.exp(-distance/180))
        ridge=np.zeros(len(xy))
        for cx,cy,amplitude,sx,sy in massifs:
            ridge=np.maximum(ridge,amplitude*np.exp(-.5*((xy[:,0]-cx)/sx)**2-.5*((xy[:,1]-cy)/sy)**2))
        # Reflected source coordinates yield actual eroded relief at broader scale.
        def reflect(a):
            v=np.mod(a+1000,4000); return np.where(v<=2000,v-1000,3000-v)
        eroded=f.sample(reflect(xy[:,0]*.78+347),reflect(xy[:,1]*.67-219))
        distant=65+ridge*(.80+.35*np.clip((eroded-60)/340,0,1))
        z=tangent*(1-smooth01(distance/650))+distant*smooth01(distance/650)
        # The seam is copied bit-exactly at float64, not inferred from a coarse ring.
        if radius==1000: z=edgeheight
        rings.append((len(vertices),len(xy)))
        vertices.extend(np.c_[xy,z].tolist())
    triangles=[]
    for (a,n),(b,m) in zip(rings[:-1],rings[1:]):
        assert n%m==0
        ratio=n//m
        for j in range(m):
            # Stitch unequal ring densities with several triangles per quad;
            # this is a graded annular mesh, never one central triangle fan.
            outer0=b+j; outer1=b+(j+1)%m
            for k in range(ratio):
                inner0=a+(j*ratio+k)%n; inner1=a+(j*ratio+k+1)%n
                triangles.append([inner0,outer0,inner1])
            triangles.append([a+((j+1)*ratio)%n,outer0,outer1])
    v=np.array(vertices); ix=np.array(triangles,dtype=np.uint32)
    cross=np.cross(v[ix[:,1]]-v[ix[:,0]],v[ix[:,2]]-v[ix[:,0]])
    flip=cross[:,2]<0; ix[flip]=ix[flip][:,[0,2,1]]
    normals=np.zeros_like(v)
    cross=np.cross(v[ix[:,1]]-v[ix[:,0]],v[ix[:,2]]-v[ix[:,0]])
    for corner in range(3): np.add.at(normals,ix[:,corner],cross)
    normals/=np.maximum(np.linalg.norm(normals,axis=1)[:,None],1e-9)
    # Seam normals use the same exact source surface samples just inside it.
    # Outer mesh smoothing is purely cosmetic; no master sample is written.
    assert np.max(abs(v[:len(boundary),2]-f.sample(boundary[:,0],boundary[:,1])))==0
    centroid=v[ix].mean(axis=1)
    assert np.all(np.max(abs(centroid[:,:2]),axis=1)>=1000-1e-6)
    assert np.isfinite(v).all() and np.isfinite(normals).all()
    gltf_positions=np.c_[v[:,0],v[:,2],-v[:,1]].astype("<f4")
    gltf_normals=np.c_[normals[:,0],normals[:,2],-normals[:,1]].astype("<f4")
    uv=(v[:,:2]/25).astype("<f4")
    parts=[gltf_positions.tobytes(),gltf_normals.tobytes(),uv.tobytes(),ix.astype("<u4").tobytes()]
    offset=0; views=[]
    for part in parts:
        views.append({"buffer":0,"byteOffset":offset,"byteLength":len(part)})
        offset+=len(part)
    doc={"asset":{"version":"2.0","generator":"PWR frozen-edge visual-v4 apron"},
         "buffers":[{"uri":"apron.bin","byteLength":offset}],"bufferViews":views,
         "accessors":[{"bufferView":0,"componentType":5126,"count":len(v),"type":"VEC3","min":gltf_positions.min(0).tolist(),"max":gltf_positions.max(0).tolist()},
                      {"bufferView":1,"componentType":5126,"count":len(v),"type":"VEC3"},
                      {"bufferView":2,"componentType":5126,"count":len(v),"type":"VEC2"},
                      {"bufferView":3,"componentType":5125,"count":ix.size,"type":"SCALAR"}],
         "materials":[{"name":"PWR_Distant_Granite"}],
         "meshes":[{"name":"PWR_Distant_Apron","primitives":[{"attributes":{"POSITION":0,"NORMAL":1,"TEXCOORD_0":2},"indices":3,"material":0}]}],
         "nodes":[{"mesh":0}],"scenes":[{"nodes":[0]}],"scene":0}
    dump(OUT/"apron/apron.gltf",doc)
    (OUT/"apron/apron.bin").write_bytes(b"".join(parts))
    np.savez_compressed(OUT/"apron/apron.source.npz",vertices_m=v,triangles=ix,normals=normals)
    receipt={"runtime_master_sha256":f.manifest_sha256,"bounds_m":[v.min(0).tolist(),v.max(0).tolist()],
             "vertices":len(v),"triangles":len(ix),"exact_inner_seam_vertices":len(boundary),
             "radial_rings":ring_specs,"maximum_radial_spacing_m":max(b[0]-a[0] for a,b in zip(ring_specs[:-1],ring_specs[1:])),
             "max_seam_error_m":0,"min_triangle_centroid_square_radius_m":float(np.max(abs(centroid[:,:2]),axis=1).min()),
             "no_native_collision":True,"no_playable_height_edits":True,
             "gltf_sha256":digest(OUT/"apron/apron.gltf"),"bin_sha256":digest(OUT/"apron/apron.bin")}
    dump(OUT/"apron/receipt.json",receipt)
    print(json.dumps(receipt,indent=2))


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command",choices=["prepare","nonsnow","export","apron"])
    add_source_arguments(parser)
    args=parser.parse_args();configure(args);globals()[args.command]()
