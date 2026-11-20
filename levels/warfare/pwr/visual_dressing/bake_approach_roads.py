"""Bake the playable road splines into a metric, mipmapped material field for LPE."""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
from scipy.ndimage import distance_transform_edt
from scipy.spatial import cKDTree


ROOT = Path(__file__).resolve().parents[4]
GEOMETRY = ROOT/"levels/warfare/pwr/terrain/final-v5/terrain.geometry.json"
MASTER = ROOT/"levels/warfare/pwr/terrain/runtime-v5"
ROADWORKS = ROOT/"forge-packs/roadworks/catalog.json"
SIZE = 2048
PRIMARY = {"red_apron", "red_upper_approach", "west_bank_upper", "upper_w_approach", "bridge_upper",
           "upper_e_approach", "citadel_climb", "citadel_apron", "east_bank_upper", "middle_w_approach",
           "bridge_middle", "middle_e_approach", "east_bank_middle", "blue_upper_approach", "blue_apron",
           "blue_lower_approach", "bridge_lower"}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def smooth(a,b,x):
    t=np.clip((x-a)/(b-a),0,1)
    return t*t*(3-2*t)


def subsection(line,begin,end):
    length=np.r_[0,np.cumsum(np.linalg.norm(np.diff(line,axis=0),axis=1))]
    q=np.r_[begin,length[(length>begin)&(length<end)],end]
    return np.stack([np.interp(q,length,line[:,i]) for i in range(2)],axis=1)


def split_at_y(line,y):
    hits=np.flatnonzero((line[:-1,1]<y)!=(line[1:,1]<y))
    if len(hits)!=1: raise ValueError(f"Expected one road cut at Y={y}")
    i=int(hits[0]); t=(y-line[i,1])/(line[i+1,1]-line[i,1])
    crossing=(1-t)*line[i]+t*line[i+1]
    left=np.vstack((line[:i+1],crossing))
    right=np.vstack((crossing,line[i+1:]))
    return (left,right) if line[0,1]<y else (right,left)


def lines_from_geometry(geometry,approaches):
    routes=[]
    def add(name,path,kind,**options):
        points=np.asarray(path,dtype=float)[:,:2]
        keep=np.r_[True,np.linalg.norm(np.diff(points,axis=0),axis=1)>.01]
        points=points[keep]
        # Source roads are already sampled every 2 m. Subdivide the extra
        # causeway/approach straight segments for fast, local nearest queries.
        seg=np.linalg.norm(np.diff(points,axis=0),axis=1)
        if not len(seg): raise ValueError(f"Road has no extent: {name}")
        t=np.r_[0,np.cumsum(seg)]
        q=np.unique(np.r_[t,np.arange(0,t[-1],1.8)])
        line=np.stack([np.interp(q,t,points[:,k]) for k in range(2)],axis=1)
        routes.append(dict(id=name,kind=kind,xy=line,**options))
    junctions=[n["position_m"][:2] for n in geometry["nodes"]]
    for road in geometry["roads"]:
        name=road["id"]; line=np.asarray(road["centreline_m"])[:,:2]
        kind="primary" if name in PRIMARY else "dirt"
        if name in ("red_apron","blue_apron"):
            exterior,diagonal=split_at_y(line,-205.)
            join=exterior[-1] if np.isclose(exterior[-1,1],-205) else exterior[0]
            junctions.append(join.tolist())
            add(name,exterior,kind)
            # Keep the shared junction, then fade the diagonal service surface
            # at the actual south edge of the native court.
            tail,_=split_at_y(diagonal,-147.)
            add(name+"_vehicle_service",tail,"dirt",end_y=-150.)
        else:
            add(name,line,kind)
        if name in ("lower_e_approach","lower_w_approach"):
            length=np.linalg.norm(np.diff(line,axis=0),axis=1).sum()
            add(name+"_abutment",subsection(line,length-13.,length),"primary")
    for feature in approaches["features"]:
        prop=feature["properties"]
        role,site=prop["role"],prop["site"]
        if role not in ("front","rear"): continue
        points=feature["geometry"]["coordinates"]
        limits=(dict(end_y=620. if site=="green" else -156.) if role=="front" else
                dict(start_y=766. if site=="green" else -4.))
        add(f"{site}_{role}_drive",points,"primary",width_m=prop["width_m"],**limits)
    return routes,np.asarray(junctions)


class Segments:
    def __init__(self,routes):
        starts=[]; ends=[]; stations=[]; owners=[]
        for i,route in enumerate(routes):
            line=route["xy"]
            delta=np.diff(line,axis=0)
            segment=np.linalg.norm(delta,axis=1)
            keep=segment>.001
            starts.extend(line[:-1][keep]); ends.extend(line[1:][keep])
            stations.extend(np.r_[0.,np.cumsum(segment)][:-1][keep])
            owners.extend([i]*int(keep.sum()))
        self.routes=routes
        self.a=np.array(starts); self.v=np.array(ends)-self.a
        self.length=np.linalg.norm(self.v,axis=1)
        self.s=np.array(stations); self.owner=np.array(owners)
        self.tree=cKDTree(self.a+.5*self.v)

    def project(self,xy):
        n=len(xy); d=np.full(n,32.); lateral=np.full(n,16.)
        station=np.zeros(n); owner=np.full(n,-1,int)
        close=self.tree.query(xy,k=1,distance_upper_bound=18.5)[0]<18.5
        p=xy[close]
        if not len(p): return d,lateral,station,owner
        # Nearest midpoint candidates are projected onto their true finite segments.
        _,ix=self.tree.query(p,k=min(12,len(self.a)))
        off=p[:,None,:]-self.a[ix]
        frac=np.clip((off*self.v[ix]).sum(-1)/self.length[ix]**2,0,1)
        side=off-frac[:,:,None]*self.v[ix]
        r=np.arange(len(p)); nearest=(side**2).sum(-1).argmin(1)
        best=ix[r,nearest]; delta=side[r,nearest]
        tangent=self.v[best]/self.length[best,None]
        d[close]=np.linalg.norm(delta,axis=1)
        lateral[close]=tangent[:,0]*delta[:,1]-tangent[:,1]*delta[:,0]
        station[close]=self.s[best]+frac[r,nearest]*self.length[best]
        owner[close]=self.owner[best]
        return d,lateral,station,owner


def bake(approach_path,out):
    out.mkdir(parents=True,exist_ok=True)
    geo=json.loads(GEOMETRY.read_text())
    approaches=json.loads(approach_path.read_text())
    if approaches["coordinates"]!="authored_xy_m_y_north":
        raise ValueError("External approach coordinates must use authoring metres and north-positive Y")
    routes,joins=lines_from_geometry(geo,approaches)
    primary=Segments([r for r in routes if r["kind"]=="primary"])
    dirt=Segments([r for r in routes if r["kind"]=="dirt"])
    join_tree=cKDTree(joins)
    water_source=MASTER/"runtime-master.water.npy"
    water=np.asarray(Image.fromarray(np.load(water_source)[::-1].copy()).resize((SIZE,SIZE),Image.Resampling.BILINEAR))
    field=np.zeros((SIZE,SIZE,4),np.uint8)
    # Do not filter arbitrary lateral and phase values into an empty apron.
    field[:]=[0,0,128,128]
    def polygons(role):
        im=Image.new("1",(SIZE,SIZE)); draw=ImageDraw.Draw(im)
        for f in approaches["features"]:
            if f["properties"]["role"]==role:
                pts=[((x+1000)*SIZE/2000-.5,(1000-y)*SIZE/2000-.5)
                     for x,y in f["geometry"]["coordinates"][0]]
                draw.polygon(pts,fill=1)
        return np.asarray(im).astype(bool)
    courts=polygons("court"); pads=polygons("rear_pad")
    pad_dist=distance_transform_edt(~pads)*2000/SIZE
    x=(np.arange(SIZE)+.5)*2000/SIZE-1000
    for start in range(0,SIZE,40):
        rows=np.arange(start,min(start+40,SIZE))
        xx,yy=np.meshgrid(x,-x[rows])
        xy=np.stack((xx.ravel(),yy.ravel()),axis=1)
        dp,lp,sp,op=primary.project(xy); dd,ld,sd,od=dirt.project(xy)
        for model,distance,ids in ((primary,dp,op),(dirt,dd,od)):
            for i,route in enumerate(model.routes):
                which=ids==i
                if "width_m" in route:
                    scale=16/route["width_m"]
                    distance[which]*=scale
                    if model is primary: lp[which]*=scale
                    else: ld[which]*=scale
                if "end_y" in route:
                    distance[which & (xy[:,1]>route["end_y"]+.4)]=32.
                if "start_y" in route:
                    distance[which & (xy[:,1]<route["start_y"]-.4)]=32.
        closest=np.minimum(dp,dd)
        eligible=closest<16.
        if not np.any(eligible): continue
        idx=np.nonzero(eligible)[0]; p=xy[idx]
        # The edge extends three metres outside the 17.6m road kit and runs
        # into the original 24m graded bed. Dirt remains across the physical width.
        rough_edge=(.52*np.sin(p[:,0]*.23+p[:,1]*.053)+.38*np.sin(p[:,1]*.37-p[:,0]*.089))
        verge=1-smooth(9.75,13.1+rough_edge,np.minimum(dp[idx],dd[idx]))
        # Dry underpasses and bridges have separate deck meshes. Only lawful
        # landscape ground receives this surface finish.
        verge*=1-smooth(.03,.47,water[rows].ravel()[idx])
        hard=1-smooth(8.68,9.02,dp[idx])
        use_primary=(dp[idx]<9.3)|(dp[idx]<dd[idx])
        lat=np.where(use_primary,lp[idx],ld[idx]); sta=np.where(use_primary,sp[idx],sd[idx])
        confidence=smooth(7.,19.,join_tree.query(p)[0])
        # Suppress longitudinal markings where lateral distances of two
        # crossing road arms are ambiguous. The merged carriageway stays solid.
        lateral=np.clip(lat/32+.5,0,1)
        phase=.5+.5*np.sin(sta*(2*np.pi/24))
        grade=(.31*(1-confidence))*(1-hard)+(.69+.31*confidence)*hard
        # Premultiply classification so a mip spanning the bare hillside and an
        # engineered lane retains its road material, weighted by its actual area.
        packed=np.stack((verge,grade*verge,lateral,phase),axis=1)
        block=field[start:start+len(rows)].reshape(-1,4)
        block[idx]=np.rint(packed.clip(0,1)*255).astype(np.uint8)
    # The meshes carry their own flush paving. Add a three-metre aggregate
    # skirt on exposed ground around each unloading head, keeping the outline clear.
    pad_verge=np.rint(230*(1-smooth(.45,3.45,pad_dist))).astype(np.uint8)
    outside=(pad_verge>field[:,:,0]) & ~pads & ~courts
    field[outside,0]=pad_verge[outside]
    field[outside,1]=np.rint(.31*pad_verge[outside]).astype(np.uint8)
    field[outside,2]=218
    field[outside,3]=128
    field[courts|pads]=[0,0,128,128]
    file=out/"road-network.png"
    Image.fromarray(field).save(file)
    rows=[{k:v for k,v in r.items() if k!="xy"}|{"length_m":round(float(np.linalg.norm(np.diff(r["xy"],axis=0),axis=1).sum()),2)}
          for r in routes]
    receipt={"file":file.name,"sha256":sha(file),"size":SIZE,"bounds_ue_cm":[-100000,-100000,200000,200000],
             "geometry_sha256":sha(GEOMETRY),"approach_sha256":sha(approach_path),"water_sha256":sha(water_source),
             "reference_kit_sha256":sha(ROADWORKS),"clear_deck_m":16,"gunmetal_margin_each_m":.8,"aggregate_verge_m":3.,
             "routes":rows,"primary_centreline_m":round(sum(r["length_m"] for r in rows if r["kind"]=="primary"),1),
             "secondary_centreline_m":round(sum(r["length_m"] for r in rows if r["kind"]=="dirt"),1),
             "joined_station_m":24.,"new_ground_collision":False}
    if np.any(field[:,:,0][water>=.47]) or not (field[:,:,1][field[:,:,0]>230].min()<5
                                            and field[:,:,1][field[:,:,0]>230].max()>250):
        raise ValueError("Road classification or bridge-bed clearance failed")
    (out/"roads.json").write_text(json.dumps(receipt,indent=2)+"\n")
    return receipt


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("approaches",type=Path)
    p.add_argument("out",type=Path)
    a=p.parse_args()
    result=bake(a.approaches.resolve(),a.out.resolve())
    print(result["sha256"],result["primary_centreline_m"],result["secondary_centreline_m"])
