# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy>=2,<3", "scipy==1.17.0", "shapely>=2,<3", "pillow>=11,<13", "matplotlib>=3.10"]
# ///
"""Prepare explicit dense stands/open meadows on the immutable runtime field.

This emits candidate inputs and a clearly labeled offline preview selection.
It is not an actual editor PCG run and never replaces the installed selection.
"""
from pathlib import Path
import json,math,sys
import numpy as np
from scipy.ndimage import gaussian_filter,distance_transform_edt
from scipy.spatial import ConvexHull,cKDTree
import shapely
from shapely.geometry import Polygon,shape
from shapely.ops import unary_union
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT=Path(__file__).resolve().parents[4];OUT=ROOT/'out/pwr/visual-v5/outcrops-v4/trees'
sys.path.insert(0,str(ROOT/'tools/level'))
from heightfield import load_heightfield,sha256
import b30_collision
MASTER=ROOT/'levels/warfare/pwr/terrain/runtime-v5/runtime-master.json'
BASE=ROOT/'out/pwr/visual-v5/outcrops-v3/trees.selected.json'
ROCKS=ROOT/'out/pwr/visual-v5/outcrops-v3/rocks-and-outcrops.authored-decor.json'
HULLS=ROOT/'out/pwr/visual-v5/outcrops-v3/hulls'
PAVING=ROOT/'out/pwr/visual-v5/base-paving-v3/footprints.geojson'

def dump(path,value):Path(path).write_text(json.dumps(value,indent=2)+'\n')

STANDS=[
 ('west_range',-790,380,155,360,-12),('northwest_foot',-570,600,165,170,-35),
 ('east_range',800,380,160,350,10),('northeast_foot',560,610,160,160,28),
 ('western_meadow_edge',-410,220,130,150,-25),('eastern_meadow_edge',370,170,140,140,25),
 ('southwest_loop',-600,-470,160,210,20),('southwest_lowland',-660,-770,175,140,-12),
 ('west_river_grove',-220,-200,95,160,-15),('east_river_grove',210,-70,110,180,15),
 ('southeast_lake_rim',825,-500,95,290,-5),('southern_grove',-230,-800,150,95,0),
]

def main():
    OUT.mkdir(parents=True,exist_ok=True);f=load_heightfield(MASTER);rng=np.random.default_rng(20605);s=f.spacing_m[0]
    yy,xx=np.indices(f.heights_m.shape);x=xx*s+f.origin_m[0];y=yy*s+f.origin_m[1]
    strength=np.zeros(x.shape)
    for _,cx,cy,rx,ry,deg in STANDS:
        c,t=math.cos(math.radians(deg)),math.sin(math.radians(deg));dx=x-cx;dy=y-cy
        radius=np.sqrt(((dx*c+dy*t)/rx)**2+((-dx*t+dy*c)/ry)**2)
        strength=np.maximum(strength,np.clip((1.13-radius)/.35,0,1))
    edge=gaussian_filter(rng.normal(size=x.shape),13);edge=edge/max(edge.std(),1e-12)
    strength=np.clip(strength+edge*.08,0,1)
    # Separate stand borders from meadows. Low-probability noise is never
    # spread through every meadow, which made the previous forest uniform.
    strength[strength<.18]=0
    gy,gx=np.gradient(f.heights_m,s);normal_z=1/np.sqrt(1+gx*gx+gy*gy)
    forbidden=(f.masks['road']>=1-1e-7)|(f.masks['water']>.002)|(f.masks['bases']>.99)
    corridor=distance_transform_edt(~forbidden,sampling=s)
    paving=unary_union([shape(z['geometry']) for z in json.loads(PAVING.read_text())['features']]).buffer(3)
    footprints=[]
    for row in json.loads(ROCKS.read_text())['decor']:
        h=json.loads((HULLS/(row['mesh'].split('.')[-1]+'.json')).read_text())
        p=np.array(h['points'])*row['scale']@b30_collision.rotator_matrix(*row['rot'])+row['pos']
        p=p[:,:2]*[.01,-.01];q=ConvexHull(p);footprints.append(Polygon(p[q.vertices]).buffer(2))
    rock_area=unary_union(footprints)
    axis=np.arange(-930,931,7.0);gx0,gy0=np.meshgrid(axis,axis)
    fresh=np.c_[gx0.ravel(),gy0.ravel()]+rng.uniform(-1.7,1.7,(gx0.size,2))
    old=json.loads(BASE.read_text())['instances'];oldxy=np.array([r['position'][:2] for r in old])
    xy=np.vstack([oldxy,fresh]);ids=np.r_[[r['id'] for r in old],np.arange(len(fresh))+1000000]
    ij=np.rint((xy-f.origin_m)/s).astype(int);ix,iy=ij.T;weights=strength[iy,ix]
    allowed=(weights>.18)&(normal_z[iy,ix]>.82)&(corridor[iy,ix]>8.9)&(f.heights_m[iy,ix]<280)
    allowed&=~shapely.intersects_xy(paving,xy[:,0],xy[:,1]);allowed&=~shapely.intersects_xy(rock_area,xy[:,0],xy[:,1])
    # Preserve the native acceptance path/vehicle/landing clearances exactly.
    features=json.loads((ROOT/'out/pwr/visual-v5/forest-v2/inputs.receipt.json').read_text())['clearance_discs']
    for _,point,radius in features:allowed&=np.linalg.norm(xy-point,axis=1)>=radius
    selected=[];buckets={};minimum=6.8;cell=minimum
    # Keep existing accepted roots inside selected stands first; deterministic
    # new blue-noise anchors fill those stands rather than their open meadows.
    priority=np.r_[np.arange(len(old)),len(old)+np.argsort(-weights[len(old):]+rng.random(len(fresh))*.15)]
    for i in priority:
        if not allowed[i]:continue
        if i>=len(old) and rng.random()>weights[i]**.7:continue
        point=xy[i];key=tuple(np.floor(point/cell).astype(int))
        nearby=[j for dx in (-1,0,1) for dy in (-1,0,1) for j in buckets.get((key[0]+dx,key[1]+dy),[])]
        if nearby and np.min(np.linalg.norm(xy[nearby]-point,axis=1))<minimum:continue
        selected.append(i);buckets.setdefault(key,[]).append(i)
    selected=np.array(selected,dtype=int);points=[]
    # This is a geometric candidate, not a PCG export. Root can approve stand
    # shape/count before requesting the actual editor graph and collision bake.
    for i in selected:
        pos=[float(xy[i,0]),float(xy[i,1]),float(f.sample(*xy[i]))]
        points.append({'id':int(ids[i]),'position':pos,'normal':[0,0,1],'density':1.,'biome_mask':1,
            'kind':'tree','prototype':'mature_pine_a','stand_weight':float(weights[i]),'retained_original_xy':bool(i<len(old))})
    pins={str(p):sha256(p) for p in (MASTER,BASE,ROCKS,PAVING)}
    dump(OUT/'stands.candidates.json',{'schema':1,'align_to_normal':False,'master_sha256':f.manifest_sha256,
          'source_status':'authored stand anchors; actual UE PCG pending','pins':pins,'points':points})
    dump(OUT/'stands.preview.json',{'schema':'pwr-forest-stand-preview-v1','status':'offline authored proposal, not new UE PCG output',
        'master_sha256':f.manifest_sha256,'pins':pins,'stand_regions':[dict(zip(('name','x','y','rx','ry','rotation'),v)) for v in STANDS],
        'count':len(points),'retained_original_xy':sum(x['retained_original_xy'] for x in points),'minimum_trunk_gap_m':minimum,
        'prototype_height_m':[22,36],'prototype_mesh_pending_preview':True,'points':points})
    fig,ax=plt.subplots(1,2,figsize=(15,7),constrained_layout=True)
    for a in ax:a.imshow(f.heights_m,origin='lower',extent=(-1000,1000,-1000,1000),cmap='gist_earth',alpha=.35);a.set_aspect('equal');a.set_xlim(-1000,1000);a.set_ylim(-1000,1000)
    ax[0].scatter(oldxy[:,0],oldxy[:,1],s=2,c='#244a2d');ax[0].set_title(f'Installed dispersed woodland: {len(old)} roots')
    ax[1].scatter(xy[selected,0],xy[selected,1],s=1.4,c='#183c23');ax[1].set_title(f'Candidate coherent stands: {len(points)} roots (not PCG output)')
    for a in ax:
        for feature in json.loads(PAVING.read_text())['features']:
            geo=shape(feature['geometry'])
            for p in geo.geoms if geo.geom_type=='MultiPolygon' else [geo]:a.plot(*p.exterior.xy,color='#777777',lw=.4)
    fig.savefig(OUT/'stands-before-after.png',dpi=140);plt.close(fig)
    print(json.dumps({'candidate_count':len(points),'preserved_root_xy':sum(p['retained_original_xy'] for p in points),'path':str(OUT/'stands.preview.json')}))

if __name__=='__main__':main()
