"""Bake the three surveyed court verges and loading approaches against the released .9 ground."""
import json
from pathlib import Path

import numpy as np
from PIL import Image
from scipy.ndimage import map_coordinates

from bake_approach_roads import GEOMETRY, MASTER, ROOT, sha, smooth


WORK = ROOT / "out/pwr/base-approaches"
ART = WORK / "site-finish/terrain"
TOPOLOGY = WORK / "site-finish/geometry/site-footprints.geojson"
GATES = WORK / "geometry/gate-routes.geojson"
PREVIOUS = ROOT / "out/pwr/landscape-distance/terrain/cooked-valley-rgba.png"
ROAD = WORK / "roads/native-road-network.png"
SITES = {"red": (-590., -80., 0, 0), "blue": (600., -80., 1, 0), "green": (0., 690., 0, 1)}
TILE = 256
SPAN = 304.


def polygon_distance(x, y, ring):
    """Signed euclidean distance to polygon, including concave mesh verge cutouts."""
    closest = np.full(x.shape, np.inf)
    inside = np.zeros(x.shape, bool)
    for a, b in zip(ring,ring[1:]):
        dx,dy=b[0]-a[0],b[1]-a[1]
        t=np.clip(((x-a[0])*dx+(y-a[1])*dy)/max(dx*dx+dy*dy,1e-14),0,1)
        closest=np.minimum(closest,np.hypot(x-a[0]-t*dx,y-a[1]-t*dy))
        if dy!=0:
            inside ^= ((a[1]>y)!=(b[1]>y)) & (x<a[0]+dx*(y-a[1])/dy)
    return np.where(inside,-closest,closest)


def sample_raster(field,x,y,vertex=False):
    n=len(field)
    scale=(n-1 if vertex else n)/2000
    u=(x+1000)*scale-(0 if vertex else .5)
    v=(y+1000)*scale if vertex else (1000-y)*scale-.5
    return map_coordinates(field.astype(np.float32,copy=False),[v,u],order=1,mode="nearest")


def noise(x,y,scale,seed):
    """Smooth deterministic value noise in world metres, with independent octaves."""
    x=x/scale; y=y/scale
    ix,iy=np.floor(x),np.floor(y)
    u,v=smooth(0,1,x-ix),smooth(0,1,y-iy)
    def corner(i,j):
        return 2*np.mod(np.sin(i*127.1+j*311.7+seed)*43758.5453,1)-1
    return ((1-v)*((1-u)*corner(ix,iy)+u*corner(ix+1,iy))+
            v*((1-u)*corner(ix,iy+1)+u*corner(ix+1,iy+1)))


class Survey:
    def __init__(self):
        self.topology=json.loads(TOPOLOGY.read_text())["features"]
        self.gates=json.loads(GATES.read_text())["features"]
        self.height=np.load(MASTER/"runtime-master.heights.npy")
        self.water=np.load(MASTER/"runtime-master.water.npy")
        self.roads=np.asarray(Image.open(ROAD).convert("RGBA"))
        self.geometry=json.loads(GEOMETRY.read_text())

    def outlines(self,site,role):
        source=self.gates if role=="rear_pad" else self.topology
        features=[f["geometry"] for f in source if f["properties"]["site"]==site and f["properties"]["role"]==role]
        return [ring[0] for geom in features for ring in
                ([geom["coordinates"]] if geom["type"]=="Polygon" else geom["coordinates"])]

    def field(self,site,x,y):
        cx,cy,*_=SITES[site]
        d=polygon_distance(x,y,self.outlines(site,"toe")[0])
        pad=polygon_distance(x,y,self.outlines(site,"rear_pad")[0])
        verge=np.minimum.reduce([polygon_distance(x,y,p) for p in self.outlines(site,"verge")])
        length=np.maximum(1,np.hypot(x-cx,y-cy))
        # The native landscape deliberately has broad level terraces. Sample
        # the real terrain beyond the grading, not invented slope at the toe.
        floor=sample_raster(self.height,np.array([cx]),np.array([cy]),True)[0]
        regional=sample_raster(self.height,cx+178*(x-cx)/length,cy+178*(y-cy)/length,True)-floor
        cut=smooth(.4,11.,regional)
        fill=smooth(.4,9.,-regional)
        patch=noise(x,y,16,1.92); arm=noise(x,y,31,8.1); fine=noise(x,y,5.3,2.8)
        native_verge=1-smooth(1,10,verge)
        width=9+3.6*patch+4.1*arm+3.5*cut+4.8*fill+native_verge*5.1+fine*1.35
        toe=(1-smooth(1.15,width,d))*(.95+.05*patch)
        fringe=(1-smooth(1.8,width+5.2+3.1*arm,d))*(.24+.11*patch)
        skirt=(1-smooth(1.7,6.5+patch*2.+fill*1.3,pad))*.82
        strength=np.maximum.reduce([toe,fringe,skirt])
        mineral=np.clip(.21+.46*(1-smooth(1.,6.4+cut*2.4,d))+.28*cut+
                        .14*fill+.16*patch+.15*fine+.08*native_verge,.11,.95)
        exposed=np.clip(.44+.19*arm+.16*fine+.16*fill+.1*cut,.12,.94)
        service=np.zeros(x.shape)
        if site!="green":
            line=np.asarray(next(r["centreline_m"] for r in self.geometry["roads"] if r["id"]==site+"_apron"))
            i=np.argsort(line[:,1]); centre=np.interp(y,line[i,1],line[i,0])
            # The new mesh flare projects past its terrace. Carry the drive's
            # gravel to its exact outline and widen gradually for the turning bay.
            bay=polygon_distance(x,y,self.outlines(site,"spur_and_bay")[0])
            dist=np.abs(x-centre)*.72
            approach=smooth(-199.,-170.,y)*(1-smooth(-156.,-149.,y))
            flare=approach*(1-smooth(4.7,9.5+approach*4.8+fine,dist))
            service=np.maximum(flare,(1-smooth(-.25,5.5+patch*2.,bay))*.94)
            strength=np.maximum(strength,.98*service)
            mineral=np.where(service>0,mineral*(1-service)+(.49+.19*fine)*service,mineral)
        coverage=sample_raster(self.roads[:,:,0],x,y)/255
        category=sample_raster(self.roads[:,:,1],x,y)/255
        paved=smooth(.32,.62,category/np.maximum(.001,coverage))*smooth(.08,.8,coverage)
        strength*=1-paved
        strength*=((d>=0)&(pad>=0)&(sample_raster(self.water,x,y,True)<.025))
        strength=np.clip(strength,0,1)
        # Premultiplied channels retain mixture proportions as the field mips.
        return np.rint(255*np.stack([strength,strength*mineral,strength*exposed,strength*service],-1)).astype(np.uint8)


def bake():
    ART.mkdir(parents=True,exist_ok=True)
    survey=Survey()
    old=np.asarray(Image.open(PREVIOUS).convert("RGBA"))
    fresh=old.copy()
    authorized=np.zeros(old.shape[:2],bool)
    atlas=np.zeros((TILE*2,TILE*2,4),np.uint8)
    sites={}
    wxy=(np.arange(len(old))+.5)*2000/len(old)-1000
    local=((np.arange(TILE)+.5)/TILE-.5)*SPAN
    for site,(cx,cy,col,row) in SITES.items():
        xx,yy=np.meshgrid(cx+local,cy-local)
        grade=survey.field(site,xx,yy)
        if np.any(grade[[0,-1]]) or np.any(grade[:,[0,-1]]):
            raise ValueError(f"{site}: atlas tile lacks a guard band")
        atlas[row*TILE:(row+1)*TILE,col*TILE:(col+1)*TILE]=grade
        cols=np.where(abs(wxy-cx)<SPAN*.5)[0]; rows=np.where(abs(-wxy-cy)<SPAN*.5)[0]
        x,y=np.meshgrid(wxy[cols],-wxy[rows]); mask=survey.field(site,x,y)
        weight=mask[:,:,0:1].astype(float)/255
        # Keep continuous mid/far ground colour through the transition. Close
        # replacement of grass by real stock aggregate is handled in the material.
        stone=mask[:,:,1:2]/np.maximum(mask[:,:,0:1],1)
        dest=np.array([163.,123.,96.])+stone*np.array([-18.,17.,41.])
        prior=old[np.ix_(rows,cols)][:,:,:3]
        colour=np.rint(prior+(dest-prior)*weight*.76).astype('uint8')
        sub=fresh[np.ix_(rows,cols)].copy(); sub[:,:,:3]=colour; fresh[np.ix_(rows,cols)]=sub
        authorized[np.ix_(rows,cols)]=mask[:,:,0]>0
        sites[site]=dict(graded_m2=round(float(grade[:,:,0].sum()/255*(SPAN/TILE)**2)),
                         service_m2=round(float(grade[:,:,3].sum()/255*(SPAN/TILE)**2)),
                         full_rock_or_gravel_m2=round(float(grade[:,:,1].sum()/255*(SPAN/TILE)**2)))
    if not np.array_equal(old[:,:,3],fresh[:,:,3]) or np.any((fresh!=old)[~authorized]):
        raise ValueError("Source modified outside terrain grading envelope")
    files={"biome":"biome-color.png","grade":"site-ground.png","support":"authorized-area.png"}
    for key,data in (("biome",fresh),("grade",atlas),("support",authorized.astype('uint8')*255)):
        Image.fromarray(data).save(ART/files[key])
    inputs=[TOPOLOGY,GATES,GEOMETRY,PREVIOUS,ROAD,MASTER/"runtime-master.heights.npy", MASTER/"runtime-master.water.npy"]
    doc=dict(files=files,source_sha256={k:sha(ART/v) for k,v in files.items()},
             inputs={v.relative_to(ROOT).as_posix():sha(v) for v in inputs},sites=sites,
             exterior_identical_rgba=int((~authorized).sum()),wet_alpha_identical=int(old.shape[0]*old.shape[1]),
             changed_biome_texels=int(np.any(fresh!=old,-1).sum()),atlas_size=2*TILE,world_tile_span_m=SPAN)
    (ART/"site-ground.json").write_text(json.dumps(doc,indent=2)+"\n")
    print(json.dumps(doc,indent=2))


if __name__=="__main__":
    bake()
