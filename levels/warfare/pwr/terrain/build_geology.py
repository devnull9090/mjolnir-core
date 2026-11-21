# /// script
# dependencies = ["numpy", "scipy", "pillow"]
# ///
"""Derive PWR surface masks from actual Gaea erosion channels and runtime relief.

No heights change. RGB encodes exposed rock, retained snow and meadow soil;
the Landscape Base alpha remains the authoritative road mask at integration.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys
import numpy as np
from scipy.ndimage import gaussian_filter, map_coordinates, maximum_filter, minimum_filter
from PIL import Image

ROOT=Path(__file__).resolve().parents[4]
sys.path.insert(0,str(ROOT/'tools/level'))
from heightfield import load_heightfield,sha256


def smooth(a,b,x):
    t=np.clip((x-a)/(b-a),0,1);return t*t*(3-2*t)


def runoff(z,spacing):
    """D8 contributing area, strictly downhill (no artificial water simulation)."""
    h,w=z.shape;best=np.zeros_like(z);down=np.full(z.shape,-1,dtype=np.int64)
    indices=np.arange(z.size).reshape(z.shape)
    for dy,dx in ((-1,-1),(-1,0),(-1,1),(0,-1),(0,1),(1,-1),(1,0),(1,1)):
        js=slice(max(0,-dy),min(h,h-dy));is_=slice(max(0,-dx),min(w,w-dx))
        jt=slice(max(0,dy),min(h,h+dy));it=slice(max(0,dx),min(w,w+dx))
        fall=(z[js,is_]-z[jt,it])/(spacing*np.hypot(dx,dy));hit=fall>best[js,is_]+1e-8
        best[js,is_][hit]=fall[hit];down[js,is_][hit]=indices[jt,it][hit]
    acc=np.ones(z.size,dtype=float);down=down.ravel()
    for i in np.argsort(z.ravel())[::-1]:
        if down[i]>=0:acc[down[i]]+=acc[i]
    return np.log1p(acc.reshape(z.shape)*spacing*spacing)


def build(master,gaea,raw,out):
    out.mkdir(parents=True,exist_ok=True)
    field=load_heightfield(master);source=load_heightfield(gaea)
    z=field.heights_m;dy,dx=field.spacing_m
    xx,yy=np.meshgrid(field.origin_m[0]+np.arange(z.shape[1])*dx,field.origin_m[1]+np.arange(z.shape[0])*dy)
    source_z=source.sample(xx,yy)
    # The raw Gaea exports are north-first1024square, same exact graph/build
    # as source.json. Verify the height channel before trusting erosion masks.
    h=np.fromfile(raw/'pwr_height.r32',dtype='<f4').reshape(source.heights_m.shape)[::-1]
    calibration=source.metadata['calibration'];decoded=h*calibration['height_range_m']+calibration['datum_m']
    if np.max(abs(decoded-source.heights_m))>5e-5:raise ValueError('Gaea masks do not match the calibrated source height')
    coordinates=[(yy-source.origin_m[1])/source.spacing_m[1],(xx-source.origin_m[0])/source.spacing_m[0]]
    channels={}
    for name in ('flow','wear','deposits'):
        data=np.fromfile(raw/('pwr_'+name+'.r32'),dtype='<f4').reshape(source.heights_m.shape)[::-1]
        if not np.isfinite(data).all() or data.min()<0:raise ValueError('Invalid Gaea '+name)
        channels[name]=map_coordinates(data,coordinates,order=1,mode='nearest',prefilter=False)
    z2=gaussian_filter(z,1.2/dx);z12=gaussian_filter(z,12/dx);z35=gaussian_filter(z,35/dx)
    gy,gx=np.gradient(z2,dy,dx);slope=np.hypot(gx,gy);nz=1/np.sqrt(1+slope*slope)
    # Positive residual is an exposed ridge; negative is a sheltered gully.
    ridge=smooth(.15,2.7,z2-z12);gully=smooth(.15,2.8,z12-z2)
    broad_ridge=smooth(.7,8,z12-z35)
    relief=maximum_filter(z,size=35)-minimum_filter(z,size=35)
    trust=1-smooth(.5,6,abs(z-source_z))
    flow_runtime=smooth(3.6,7.4,runoff(z2,dx))
    flow_gaea=smooth(.001,.08,channels['flow'])
    flow=gaussian_filter(flow_gaea*trust+flow_runtime*(1-trust),1.4/dx)
    wear_gaea=smooth(.001,.018,channels['wear'])
    wear_runtime=np.clip(.68*ridge+.42*smooth(.18,.65,slope),0,1)
    wear=wear_gaea*trust+wear_runtime*(1-trust)
    deposits_gaea=smooth(.0001,.0025,channels['deposits'])
    deposits=deposits_gaea*trust+gully*(1-trust)
    protection=np.maximum.reduce([field.masks.get(k,np.zeros_like(z)) for k in ('road','bases','water')])
    clear=1-smooth(.08,.7,protection)
    mountain=smooth(125,190,z)*smooth(5,30,relief)
    # Bedrock covers mountain slopes and exposed ridges, not flat valley
    # turf. Wear follows the actual eroded bands instead of colour noise.
    rock=np.clip(mountain*(.43+.44*smooth(.14,.55,slope)+.42*ridge+.25*wear),0,1)
    rock=np.maximum(rock,smooth(.35,.85,slope)*.82)
    rock*=clear
    # Snow remains in high sheltered gullies/ledges. Convex summits and wind-
    # exposed ridges lose most snow rather than becoming a continuous cap.
    north=np.clip(gy/np.maximum(slope,.01)*.5+.5,0,1)
    retention=np.clip(.12+.50*gully+.30*flow+.24*deposits+.12*north-.62*ridge-.16*broad_ridge,0,1)
    # A connected, wider sheltered snowfield rather than hairline channels.
    # The ridge penalty remains in retention, so upper exposed rock survives.
    snow=smooth(165,260,z)*smooth(.08,.48,retention)*(1-smooth(.8,1.5,slope))
    snow*=clear
    # Damp/gentle deposits and worn colluvium make small soil openings in
    # meadows. Never replace the entire green valley with thresholded blobs.
    soil=np.clip((.22*deposits+.35*wear+.16*flow)*smooth(.03,.25,slope),0,.65)
    soil*=clear*(1-rock)*(1-snow)
    rgb=np.stack([rock,snow,soil],axis=-1).astype(np.float32)
    np.save(out/'geology.rgb.npy',rgb)
    Image.fromarray(np.rint(rgb[::-1]*255).astype(np.uint8),'RGB').save(out/'geology.png')
    # Geometry-led material placement preview; no claim of Unreal shading.
    colors=np.tile([.20,.29,.12],(*z.shape,1))
    colors=colors*(1-soil[...,None])+np.array([.27,.235,.18])*soil[...,None]
    colors=colors*(1-rock[...,None])+np.array([.32,.34,.35])*rock[...,None]
    colors=colors*(1-snow[...,None])+np.array([.82,.85,.88])*snow[...,None]
    light=np.clip((-.45*gx+.35*gy+1.2)/np.sqrt(1+gx*gx+gy*gy),.3,1.5)
    colors=np.clip(colors*light[...,None],0,1)
    road=field.masks.get('road',np.zeros_like(z));colors=colors*(1-road[...,None])+np.array([.26,.225,.17])*road[...,None]
    water=field.masks.get('water',np.zeros_like(z));colors=colors*(1-water[...,None])+np.array([.015,.20,.23])*water[...,None]
    Image.fromarray(np.rint(colors[::-1]**(1/2.2)*255).astype(np.uint8),'RGB').save(out/'surface-placement-preview.png')
    for name,array in [('rock',rock),('snow',snow),('soil',soil),('source-trust',trust),('flow',flow),('wear',wear),('deposits',deposits)]:
        Image.fromarray(np.rint(np.clip(array[::-1],0,1)*255).astype(np.uint8),'L').save(out/(name+'.png'))
    report={'schema':'pwr-alpine-geology-v1','coordinates':'authoring_metres_z_up','row_order':'+y',
            'master_sha256':field.manifest_sha256,'source_gaea_sha256':source.manifest_sha256,
            'source_erosion_exports':{name:sha256(raw/('pwr_'+name+'.r32')) for name in ('height','flow','wear','deposits')},
            'dimensions':list(field.dimensions),'origin_m':list(field.origin_m),'spacing_m':list(field.spacing_m),
            'data':'geology.rgb.npy','data_sha256':sha256(out/'geology.rgb.npy'),
            'channels':['exposed_rock','retained_snow','meadow_soil'],
            'encoding':'Base RGB linear0..1, preserve road alpha exactly; LandAlpine.w=2 only',
            'source_trust':'1 at<=0.5m source/runtime deviation,0 at>=6m; elsewhere runtime curvature/D8 contributing area',
            'weighted_cover':{'rock':float(rock.mean()),'snow':float(snow.mean()),'soil':float(soil.mean())},
            'dominant_cover':{'rock':float(np.mean(rock>.5)),'snow':float(np.mean(snow>.5))},
            'protected_mask_max':float(rgb[protection>=.7].max(initial=0)),
            'height_changes':False,'status':'isolated surface candidate; native material/render review pending'}
    (out/'geology.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report['weighted_cover'],indent=2));return report


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--master',type=Path,default=ROOT/'levels/warfare/pwr/terrain/runtime-v5/runtime-master.json')
    p.add_argument('--gaea',type=Path,default=ROOT/'levels/warfare/pwr/terrain/gaea-v5c/source.json')
    p.add_argument('--raw',type=Path,default=ROOT/'out/pwr/gaea-world-v5c')
    p.add_argument('--out',type=Path,default=ROOT/'out/pwr/visual-v5/geology')
    a=p.parse_args();build(a.master,a.gaea,a.raw,a.out)
