"""Project forest-road earth and loose stone candidates onto the released PWR terrain."""
from pathlib import Path
import argparse
import json
import re
import subprocess
import sys

import numpy as np
from PIL import Image
from scipy.ndimage import distance_transform_edt, map_coordinates
from scipy.spatial import cKDTree

from bake_approach_roads import GEOMETRY, ROOT, PRIMARY, sha, smooth
from bake_site_finish import noise

sys.path.insert(0,str(ROOT/"tools/level"))
from heightfield import load_heightfield
from foliage_bake import mesh_info, PAKS


OUT=ROOT/"out/pwr/ground-life/earth"
LEVEL=ROOT/"out/pwr/base-approaches/saturday.10/map-input/pwr.level.json"
MASTER=ROOT/"levels/warfare/pwr/terrain/runtime-v5/runtime-master.json"
TREES=ROOT/"out/pwr/visual-v6/scenery/trees/trees.selected.json"
CATALOG=ROOT/"out/pwr/visual-v4/assets/rock-bounds.json"
BIOME=ROOT/"out/pwr/base-approaches/site-finish/terrain/native-biome-color.png"
ROAD=ROOT/"out/pwr/base-approaches/roads/native-road-network.png"
SIZE=1024
MESH_IDS=("wd3nech","wd5nfa1","wfbscavr","wfcpeggr")
SEED=11670


def load(path):
    return json.loads(path.read_text())


def save(name,value,compact=False):
    (OUT/name).write_text(json.dumps(value,indent=None if compact else 2,separators=(",",":") if compact else None)+"\n")


def sample(data,x,y):
    n=len(data); return map_coordinates(data.astype(np.float32,copy=False),
        [(1000-y)*n/2000-.5,(x+1000)*n/2000-.5],order=1,mode="nearest")


class Ground:
    def __init__(self):
        self.field=load_heightfield(MASTER)
        self.geometry=load(GEOMETRY)
        self.level=load(LEVEL)
        self.roads={r["id"]:np.asarray(r["centreline_m"])[:,:2] for r in self.geometry["roads"]}
        self.all=cKDTree(np.concatenate(list(self.roads.values())))
        # Trunk proximity, measured in the released forest, also works where the
        # forest placement mask was deliberately cut away alongside a graded bed.
        self.trees=cKDTree(np.array([t["position"][:2] for t in load(TREES)["instances"]]))
        c=(np.arange(SIZE)+.5)*2000/SIZE-1000
        self.x,self.y=np.meshgrid(c,-c)
        x,y=self.x,self.y
        xy=np.c_[x.ravel(),y.ravel()]
        def dist(tree):
            return tree.query(xy)[0].reshape(x.shape)
        self.tree_gap=dist(self.trees)
        self.road_gap=dist(self.all)
        secondary=[v for k,v in self.roads.items() if k not in PRIMARY and not k.startswith("capture_")]
        self.dirt_gap=dist(cKDTree(np.concatenate(secondary)))
        flow=self.field.sample_mask("water",x,y)
        self.water_gap=distance_transform_edt(flow<.025)*(2000/SIZE)
        self.wood=np.maximum(1-smooth(18,57,self.tree_gap),self.field.sample_mask("forest",x,y)*.80)
        self.slope=np.hypot(*np.gradient(self.field.sample(x,y),2000/SIZE))
        blocked=self.field.sample_mask("bases",x,y)>.002
        for p in self.level["blam"]["player_starts"]+self.level["blam"]["vehicles"]+self.level["markers"]:
            px,py=p["pos"][:2]
            blocked|=(x-.01*px)**2+(y+.01*py)**2<13**2
        for p in self.level["koth_hills"]:
            blocked|=(x-.01*p[0])**2+(y+.01*p[1])**2<(.01*p[3]+9)**2
        # The rear pads, gate approaches and earth feather are .10-owned. Keep
        # outside a measured envelope including the summit's extended loading head.
        for cx,cy in ((-590,-80),(600,-80),(0,690)):
            blocked|=(abs(x-cx)<112)&(y>cy-125)&(y<cy+142)
        self.protected=blocked | (flow>.01) | (self.water_gap<4.5) | (self.slope>.60)
        # The real old road atlas distinguishes bridge decks/causeways from dirt,
        # even where an engineering route crosses a secondary one.
        net=np.asarray(Image.open(ROAD).convert("RGBA")).astype(np.float32)
        rc=sample(net[:,:,0],x,y)/255; hg=sample(net[:,:,1],x,y)/255
        self.hard=(hg/np.maximum(.001,rc)>.34)&(rc>.15)
        self.hard_gap=distance_transform_edt(~self.hard)*2000/SIZE
        # Conservatively rasterize existing placed rock bounds. Bounding the
        # scaled three-dimensional support radius also covers rotated cliff kits.
        catalog={r["path"]:r for r in load(CATALOG)}
        self.rocks=np.zeros(x.shape,bool)
        for obj in self.level["decor"]:
            ref=catalog.get(obj["mesh"])
            if not ref: continue
            scale=np.asarray(obj.get("scale",[1,1,1])); extent=np.maximum(abs(np.array(ref["min"])),abs(np.array(ref["max"])))
            radius=np.linalg.norm(extent*scale)*.01+.4
            px,py=np.array(obj["pos"][:2])*[.01,-.01]
            ix=np.where(abs(c-px)<radius+2)[0]; iy=np.where(abs(-c-py)<radius+2)[0]
            sel=np.ix_(iy,ix)
            self.rocks[sel]|=(x[sel]-px)**2+(y[sel]-py)**2<radius**2
        self.stone_ok=(~self.protected)&(~self.rocks)&(self.tree_gap>2.3)&(self.hard_gap>5)&(self.road_gap>9.6)

    def safe(self,x,y):
        return sample(self.stone_ok,x,y)>.998

    def centres(self,rng):
        centres=[]
        def propose(xy,tangent,role,road,mandatory=False):
            x,y=xy
            if not self.safe(np.array([x]),np.array([y]))[0]:
                if mandatory: raise ValueError(f"Protected review target at {x} {y}")
                return
            if centres and np.min([np.hypot(x-p["x"],y-p["y"]) for p in centres])<5: return
            centres.append(dict(x=round(x,4),y=round(y,4),heading=float(np.arctan2(tangent[1],tangent[0])),
                                length_m=float(rng.uniform(4.1,9.5) if role=="verge" else rng.uniform(2.0,5.5)),
                                width_m=float(rng.uniform(1.3,3.1)),role=role,road=road))
        # Reserve an actual exposed earth/grass break in the southwest forest.
        propose((-568.62,-587.33),(.14,-.99),"verge","southwest_sweep",True)
        for name,line in self.roads.items():
            if name in PRIMARY or name.startswith("capture_"): continue
            ds=np.r_[0,np.cumsum(np.linalg.norm(np.diff(line,axis=0),axis=1))]
            along=rng.uniform(15,32)
            while along<ds[-1]-14:
                i=np.clip(np.searchsorted(ds,along),1,len(line)-2)
                t=line[i+1]-line[i-1]; t/=np.linalg.norm(t)
                side=np.array([-t[1],t[0]])*rng.choice([-1,1])
                xy=line[i]+side*rng.uniform(11.8,21.5)
                propose(xy,t,"verge",name)
                along+=rng.uniform(14,34)
        for index in rng.permutation(len(self.trees.data))[:1800]:
            if sum(1 for p in centres if p["role"]=="woodland")>=115: break
            angle=rng.uniform(-np.pi,np.pi); direction=np.array([np.cos(angle),np.sin(angle)])
            xy=self.trees.data[index]+direction*rng.uniform(4.1,12.)
            if max(abs(xy))>955: continue
            if sample(self.wood,*xy[:,None])[0]>.62:
                propose(xy,direction,"woodland",None)
        return centres

    def bake(self,centres):
        x,y=self.x,self.y; fine=noise(x,y,5.3,9.6); slow=noise(x,y,23.1,5.2)
        bare=(1-smooth(8.2,14.8+fine*1.7,self.dirt_gap))*(.45+.34*self.wood+.10*slow)
        grit=(1-smooth(1,5.3+fine*1.3,abs(self.dirt_gap-9.4)))*(.35+.36*self.wood+.12*slow)
        tracks=(1-smooth(6.8,9.8,self.dirt_gap))*(.57+.31*self.wood)
        deposit=np.zeros(x.shape); floor=np.zeros(x.shape)
        for p in centres:
            lim=p["length_m"]+p["width_m"]+7
            ix=np.where(abs(x[0]-p["x"])<lim)[0]; iy=np.where(abs(y[:,0]-p["y"])<lim)[0];sel=np.ix_(iy,ix)
            dx=x[sel]-p["x"];dy=y[sel]-p["y"];co=np.cos(p["heading"]);si=np.sin(p["heading"])
            u=(dx*co+dy*si)/p["length_m"]; v=(-dx*si+dy*co)/p["width_m"]
            footprint=1-smooth(.30,1.52,np.hypot(u,v+.22*np.sin(3.3*u))+.15*fine[sel])
            deposit[sel]=np.maximum(deposit[sel],footprint*(.78+.12*fine[sel]))
            floor[sel]=np.maximum(floor[sel],(1-smooth(.5,2.6,np.hypot(u,v)))*(.56+.13*slow[sel]))
        oldwet=np.asarray(Image.open(BIOME))[:,:,3]/255
        keep=(~self.protected)*(smooth(1.7,4.6,self.hard_gap))*(1-smooth(.17,.49,oldwet))
        total=np.maximum.reduce([bare,grit,deposit,floor])*keep
        mineral=np.maximum(grit,deposit)
        damp=(.20+.55*self.wood+.25*(1-smooth(8,60,self.water_gap)))*(.70+.29*slow)
        packed=np.stack([total,total*np.clip(mineral,0,1),total*np.clip(damp,0,1),total*tracks],axis=-1)
        out=np.rint(255*np.clip(packed,0,1)).astype(np.uint8)
        if np.any(out[self.protected|self.hard]):raise ValueError("Material overlaps protected area")
        return out


def stock_scans():
    cli=str(ROOT/"target/release/mjolnir.exe")
    stock=OUT/"stock";stock.mkdir(parents=True,exist_ok=True)
    catalogue=load(CATALOG)
    chosen=[next(r for r in catalogue if f"Small_Beach_Rock_{suffix}/" in r["path"] and "_Snow" not in r["path"]) for suffix in MESH_IDS]
    reports=[];assets=[]
    for item in chosen:
        path=item["path"];leaf=path.split(".")[-1];file=stock/(leaf+".glb")
        rendered=subprocess.run([cli,"mesh","export","--paks",PAKS,"--asset",leaf,"--out",str(file)],
                                capture_output=True,text=True,check=True)
        match=re.search(r"nanite: (\d+) page\(s\), (\d+) cluster\(s\), (\d+) at full detail, (\d+) triangles",
                        rendered.stdout+rendered.stderr)
        if not match: raise ValueError("The selected stock asset has no native Nanite geometry: "+leaf)
        info=mesh_info(cli,PAKS,path)
        if not file.exists() or not info["slots"]:raise ValueError("Missing actual scan or material")
        mesh=dict(path=path,min_cm=item["min"],max_cm=item["max"],source_file=file.name,sha256=sha(file),native=info)
        assets.append(mesh)
        refs=subprocess.run([cli,"ue","get","--paks",PAKS,"--package",path.split(".")[0],"--export",leaf],
                            capture_output=True,text=True)
        if refs.returncode: # Some CLI versions require the numeric export object index.
            listing=subprocess.run([cli,"ue","get","--paks",PAKS,"--package",path.split(".")[0]],capture_output=True,text=True,check=True)
            index=re.search(r"export (\d+): \S+ : StaticMesh\b",listing.stdout).group(1)
            refs=subprocess.run([cli,"ue","get","--paks",PAKS,"--package",path.split(".")[0],"--export",index],
                                capture_output=True,text=True,check=True)
        materials=re.findall(r"StaticMaterials\[(\d+)\]\.MaterialInterface = import (\d+)",refs.stdout)
        if len(materials)!=len(info["slots"]):raise ValueError("Stock rock has an empty material reference")
        reports.append(dict(mesh,material_imports=materials,nanite=dict(zip(("pages","clusters","detail_clusters","triangles"),map(int,match.groups())))))
    save("stock-native.json",reports)
    return assets


def prepare():
    OUT.mkdir(parents=True,exist_ok=True)
    world=Ground();rng=np.random.default_rng(SEED)
    centres=world.centres(rng); atlas=world.bake(centres);Image.fromarray(atlas).save(OUT/"earth-detail.png")
    points=[]
    for ci,p in enumerate(centres):
        count=int(rng.integers(15,38) if p["role"]=="verge" else rng.integers(6,19))
        if ci==0: count=64
        co,si=np.cos(p["heading"]),np.sin(p["heading"])
        # Broken fans concentrate pebbles in pockets rather than evenly peppering grass.
        u=rng.uniform(-1,1,count);v=rng.normal(0,.34,count)+.22*np.sin(3.3*u)
        dx=u*p["length_m"];dy=v*p["width_m"]; x=p["x"]+dx*co-dy*si;y=p["y"]+dx*si+dy*co
        ok=world.safe(x,y); x=x[ok];y=y[ok];z=world.field.sample(x,y)-.006
        normals=np.stack([(world.field.sample(x-.4,y)-world.field.sample(x+.4,y))/.8,
                          (world.field.sample(x,y-.4)-world.field.sample(x,y+.4))/.8,np.ones(len(x))],axis=-1)
        normals/=np.linalg.norm(normals,axis=1,keepdims=True)
        for i in range(len(x)):
            if any(np.hypot(x[i]-x[j],y[i]-y[j])<.16 for j in range(i)):continue
            points.append(dict(id=len(points),position=[round(x[i],6),round(y[i],6),round(z[i],6)],
                               normal=normals[i].round(8).tolist(),kind="loose_stone",density=.90 if ci==0 else .82,
                               biome_mask=1,patch=ci))
    source={"schema":1,"align_to_normal":True,"points":points}
    save("points.json",source,True);save("patches.json",centres,True)
    assets=stock_scans()
    save("palette.json",{"kinds":{"loose_stone":dict(meshes=[v["path"] for v in assets],rule="native loose stone",
                                       cull=[4300,9900],bands=1,static=True,shadow=False)}})
    p=OUT/"points.json";xy=np.array([v["position"][:2] for v in points]);dist=world.all.query(xy)[0]
    if min(dist)<9.5 or not world.safe(*xy.T).all() or len(points)<1000 or len(points)>11000:raise ValueError("Stone candidates outside support")
    manifest=dict(seed=SEED,actor="PWR_LooseGroundStones",stock_meshes=assets,source_paths={"catalog":str(CATALOG),"level":str(LEVEL)},
                  inputs={p.relative_to(ROOT).as_posix():sha(p) for p in (MASTER,GEOMETRY,TREES,LEVEL,ROAD,BIOME,CATALOG)},
                  source_sha256={f:sha(OUT/f) for f in ("points.json","patches.json","earth-detail.png","palette.json")},
                  sites=len(centres),woodland_patches=sum(p["role"]=="woodland" for p in centres),road_patches=sum(p["role"]=="verge" for p in centres),
                  route_ids=sorted({p["road"] for p in centres if p["road"]}),closest_road_center_m=float(min(dist)),
                  stone_candidates=len(points),graded_ground_m2=round(float(atlas[:,:,0].sum()/255*(2000/SIZE)**2)),
                  native_roads_excluded=True,native_wet_alpha_untouched=True,source_burial_m=.006)
    save("earth.json",manifest)
    save("pcg-request.json",{"jobs":[dict(input=str(p),output=str(OUT/f"{tag}.json"),
         graph="/Game/MJOLNIR/PCGAuthoring/PWRGroundLife/"+tag,seed=SEED,scale_min=.65,scale_max=1.72)
         for tag in ("LooseGround","LooseGroundRepeat")]})
    print(len(centres),len(points),manifest["closest_road_center_m"],manifest["graded_ground_m2"])


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stock-only",action="store_true")
    if parser.parse_args().stock_only:stock_scans()
    else:prepare()
