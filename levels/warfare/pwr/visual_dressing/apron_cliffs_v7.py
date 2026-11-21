# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy>=2,<3", "matplotlib>=3.10"]
# ///
"""Prepare three irregular exterior ridge assemblies and actual UE-PCG inputs.

CPU preparation never claims a PCG export. Export requires two matching actual
PCG outputs and revalidates full transformed native bounds. No swap.decor,
terrain height, native hull, tree, water or installed file is written.
"""
from pathlib import Path
import argparse
import json
import math
import functools
import struct
import sys
import numpy as np

ROOT=Path(__file__).resolve().parents[4]
sys.path.insert(0,str(ROOT/'tools/level'))
import render_only_hism as adapter
from heightfield import sha256
import pcg_foliage
import build_apron_v3 as join

OUT=ROOT/'out/pwr/visual-v7/apron-cliffs'
BASE=ROOT/'out/pwr/visual-v5/apron-v4'
MASTER=ROOT/'levels/warfare/pwr/terrain/runtime-v5/runtime-master.json'
SOURCE=ROOT/'levels/warfare/pwr/terrain/gaea-apron-v4/source.json'
MATERIAL=ROOT/'out/pwr/visual-v5/surface-v4/rock-material.json'
SEED=20717


def dump(path,value):
    path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(value,indent=2)+'\n')


def quat(heading,tilt):
    # Author +Y maps to UE -Y; heading is reflected, while local-X tilt
    # stays explicit. Rotation composition is UE Z followed by local X.
    z=-heading/2;x=tilt/2
    return [math.cos(z)*math.sin(x),math.sin(z)*math.sin(x),math.sin(z)*math.cos(x),math.cos(z)*math.cos(x)]


@functools.lru_cache(maxsize=3)
def source_points(mesh):
    leaf=mesh.split('.')[-1];path=OUT/'assets'/f'{leaf}.glb'
    raw=path.read_bytes();n=struct.unpack_from('<I',raw,12)[0];doc=json.loads(raw[20:20+n]);data=raw[28+n:];parts=[]
    for primitive in doc['meshes'][0]['primitives']:
        a=doc['accessors'][primitive['attributes']['POSITION']];v=doc['bufferViews'][a['bufferView']]
        if a['componentType']!=5126 or a['type']!='VEC3':raise ValueError('Unexpected native vertex format')
        points=np.ndarray((a['count'],3),dtype='<f4',buffer=data,
            offset=v.get('byteOffset',0)+a.get('byteOffset',0),strides=(v.get('byteStride',12),4))
        parts.append(points[:,[0,2,1]].astype(float)*100)
    return np.concatenate(parts)


def ground_pose(sample,entry,yaw_delta=0,scale_factor=1):
    x,y=entry['anchor_m'][:2];heading=entry['heading_radians']+yaw_delta
    row={'id':entry['id'],'mesh':entry['mesh'],'ridge':entry['ridge'],
        'position_cm':[x*100,-y*100,0.],
        'rotation_xyzw':quat(heading,entry['tilt_radians']),
        'scale':[s*scale_factor for s in entry['scale']]}
    lo,hi=adapter.transformed_bounds(row)
    row['position_cm'][2]=(float(sample(x,y))+entry['crest_exposure_m'])*100-hi[2]
    # Inspect the actual native lower surface, not only its bounding box.
    # Deeply embed the lowest20% of referenced vertices so sloping support
    # cannot leave an exposed floating bottom. Keep modest source proportions;
    # if lowering hides a crest, the preview must reject/reposition that piece.
    local=source_points(row['mesh']);rot=np.array(adapter.matrix(row['rotation_xyzw']))
    transformed=(local*np.array(row['scale']))@rot.T+row['position_cm']
    bottom=transformed[local[:,2]<=np.quantile(local[:,2],.20)]
    floor=sample(bottom[:,0]/100,-bottom[:,1]/100)*100
    lower=max(0.,float(np.max(bottom[:,2]-floor))+150.)
    row['position_cm'][2]-=lower
    lo,hi=adapter.transformed_bounds(row)
    # Conservative entire bounds must remain on the exterior terrain domain.
    if not (lo[0]>105000 or hi[0]<-105000 or lo[1]>105000 or hi[1]<-105000):
        raise ValueError('Pilot full mesh enters protected square')
    if max(abs(v) for v in lo[:2]+hi[:2])>400000:raise ValueError('Pilot outside source domain')
    xs=np.linspace(lo[0]/100,hi[0]/100,9);ys=np.linspace(-hi[1]/100,-lo[1]/100,9)
    xx,yy=np.meshgrid(xs,ys);heights=sample(xx,yy)
    return row,{'id':row['id'],'bounds_ue_cm':[lo,hi],'center_ground_m':float(sample(x,y)),
        'top_above_center_m':entry['crest_exposure_m']-lower/100,
        'bottom20pct_source_vertices':len(bottom),'maximum_lower_surface_gap_m':float(np.max(bottom[:,2]-lower-floor))/100,
        'grounding_lowering_m':lower/100,'conservative_bottom_burial_min_m':float(np.min(heights)-lo[2]/100),
        'footprint_ground_range_m':[float(np.min(heights)),float(np.max(heights))],
        'maximum_source_bound_radius_m':float(np.linalg.norm((np.array(hi[:2])-lo[:2])/200))}


def prepare():
    OUT.mkdir(parents=True,exist_ok=True);sample,joined=join.sampler(MASTER,SOURCE,BASE);rng=np.random.default_rng(SEED)
    # Three visible-facing ridge shoulders. Selection uses actual 35m convexity,
    # slope and inward face direction; no new artificial height/noise field.
    regions=[('west',(-2100,-1350,300,1300)),('north',(-800,800,1400,2300)),('east',(1350,2100,300,1300))]
    centres=[];anchors=[];palette=[p for p in adapter.ASSETS if '/Desert/' in p]
    for ridge,(x0,x1,y0,y1) in regions:
        xx,yy=np.meshgrid(np.arange(x0,x1+1,20),np.arange(y0,y1+1,20));x,y=xx.ravel(),yy.ravel();z=sample(x,y)
        gx=(sample(x+8,y)-sample(x-8,y))/16;gy=(sample(x,y+8)-sample(x,y-8))/16;slope=np.hypot(gx,gy)
        convex=z-(sample(x+35,y)+sample(x-35,y)+sample(x,y+35)+sample(x,y-35))/4
        inward=(gx*x+gy*y)/(np.maximum(slope,1e-9)*np.hypot(x,y))
        valid=(slope>.35)&(slope<1.6)&(convex>1)&(z>200)&(z<850)&(inward>.3)
        score=np.where(valid,convex*(.5+.5*inward),-1)
        k=int(np.argmax(score))
        if score[k]<=0:raise ValueError(f'No real convex ridge in {ridge}')
        center=np.array([x[k],y[k]]);down=-np.array([gx[k],gy[k]])/slope[k];along=np.array([-down[1],down[0]])
        centres.append({'id':ridge,'position_m':[float(x[k]),float(y[k]),float(z[k])],'slope':float(slope[k]),'convex35m':float(convex[k])})
        for i,offset in enumerate([-76,-53,-29,-5,19,44,68,90]):
            xy=center+along*offset+down*rng.uniform(-10,10)
            dx=(sample(xy[0]+8,xy[1])-sample(xy[0]-8,xy[1]))/16
            dy=(sample(xy[0],xy[1]+8)-sample(xy[0],xy[1]-8))/16
            heading=math.atan2(float(dy),float(dx))+math.pi/2
            scale=float(rng.uniform(1.2,1.9));mesh=palette[(i+len(anchors))%len(palette)]
            entry={'id':f'pwr_apron_cliff_{ridge}_{i:02d}','ridge':ridge,'mesh':mesh,
                'anchor_m':[float(xy[0]),float(xy[1]),float(sample(*xy))],
                'heading_radians':heading,'tilt_radians':float(rng.uniform(-.16,.16)),
                'scale':[scale,float(scale*rng.uniform(.8,1.05)),float(scale*rng.uniform(.8,1.1))],
                'crest_exposure_m':float(rng.uniform(3,10))}
            ground_pose(sample,entry);anchors.append(entry)
    refs=[MASTER,SOURCE,BASE/'harmonic-field.npz',BASE/'join.receipt.json',MATERIAL,Path(__file__),ROOT/'tools/level/render_only_hism.py']
    asset_checks=[]
    for path in palette:
        leaf=path.split('.')[-1];refs.append(OUT/'assets'/f'{leaf}.glb')
        points=source_points(path);lo,hi=np.array(adapter.ASSETS[path]['bounds_cm'])
        excess=float(np.max(np.maximum(lo-points,points-hi)))
        if excess>.1:raise ValueError('Native source vertices exceed verified bound plus1mm guard')
        asset_checks.append({'mesh':path,'source_sha256':sha256(refs[-1]),'vertices':len(points),
            'maximum_catalog_bound_excess_cm':excess,'world_bound_guard_cm':.1,
            'source_triangles':adapter.ASSETS[path]['source_triangles']})
    plan={'schema':'pwr-apron-cliff-pilot-v1','seed':SEED,'ridge_centres':centres,'anchors':anchors,
        'sources':[{'path':str(p),'sha256':sha256(p)} for p in refs],
        'geometry_policy':'24 native irregular masses; source contour heading, top3–10m above local ground; no playable/collision edits',
        'status':'CPU-authored anchors; actual PCG selection/variance and actual view required'}
    dump(OUT/'pilot.plan.json',plan)
    dump(OUT/'assets.receipt.json',{'schema':'pwr-apron-cliff-native-assets-v1','assets':asset_checks,
        'exporter_sha256':sha256(ROOT/'out/pwr/toolchain-mesh-attrs-v2/mjolnir.exe'),
        'native_geometry_not_recooked':True,'shipped_material_overridden_only_for_gray_no_snow_palette':True})
    points=[]
    for i,entry in enumerate(anchors):
        points.append({'id':i,'position':entry['anchor_m'],'normal':[0,0,1],'density':1.,'biome_mask':1,'kind':'exterior_ridge_anchor'})
    for i,density,mask in [(1000,0.,1),(1001,1.,0)]:
        points.append({'id':i,'position':points[0]['position'],'normal':[0,0,1],'density':density,'biome_mask':mask,'kind':'excluded_fixture'})
    candidate=OUT/'pilot.candidates.json'
    dump(candidate,{'schema':1,'align_to_normal':False,'master_sha256':sha256(SOURCE),'plan_sha256':sha256(OUT/'pilot.plan.json'),'points':points})
    dump(OUT/'request.json',{'jobs':[{'input':str(candidate),'output':str(OUT/f'pilot{s}.pcg.json'),
        'graph':'/Game/MJOLNIR/PCGAuthoring/PWRVisualV7/PCG_apron_cliffs'+s,'seed':SEED,'scale_min':.95,'scale_max':1.05}
        for s in ('','_repeat')]})
    posed=[ground_pose(sample,e) for e in anchors]
    preview=[row for row,check in posed]
    dump(OUT/'pilot.preview-transforms.json',{'status':'CPU planned transforms, not actual PCG output','instances':preview})
    dump(OUT/'pilot.preview-grounding.json',{'status':'CPU source-vertex/bounds checks; actualPCG and actualview pending',
        'plan_sha256':sha256(OUT/'pilot.plan.json'),'source_triangles':sum(adapter.ASSETS[e['mesh']]['source_triangles'] for e in anchors),
        'lower_surface_policy':'Lowest20percent of full native LOD0 vertices embedded at least1.5m; no convex-hull substitution',
        'checks':[check for row,check in posed]})
    plot(sample,centres,preview)
    print(json.dumps({'anchors':len(anchors),'ridge_centres':centres,'actual_pcg_pending':True}))


def plot(sample,centres,rows):
    import matplotlib;matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig,axes=plt.subplots(1,3,figsize=(15,5),constrained_layout=True)
    for ax,center in zip(axes,centres):
        x,y,_=center['position_m'];xx,yy=np.meshgrid(np.linspace(x-180,x+180,150),np.linspace(y-180,y+180,150))
        h=sample(xx,yy);ax.contourf(xx,yy,h,25,cmap='gist_earth');ax.contour(xx,yy,h,15,colors='black',alpha=.25,linewidths=.4)
        for row in rows:
            if row['ridge']!=center['id']:continue
            lo,hi=adapter.transformed_bounds(row);px=[lo[0],hi[0],hi[0],lo[0],lo[0]];py=[lo[1],lo[1],hi[1],hi[1],lo[1]]
            ax.plot(np.array(px)/100,-np.array(py)/100,color='cyan',lw=1)
            ax.scatter(row['position_cm'][0]/100,-row['position_cm'][1]/100,s=9,c='white')
        ax.set_aspect('equal');ax.set_title(center['id']+' — CPU bounds/contours')
    fig.savefig(OUT/'pilot-plan.png',dpi=160);plt.close(fig)


def export():
    plan=json.loads((OUT/'pilot.plan.json').read_text());candidate=json.loads((OUT/'pilot.candidates.json').read_text())
    if candidate['plan_sha256']!=sha256(OUT/'pilot.plan.json'):raise ValueError('Pilot plan changed')
    for ref in plan['sources']:
        if sha256(ref['path'])!=ref['sha256']:raise ValueError('Pilot source changed')
    first,repeat=[json.loads((OUT/f'pilot{s}.pcg.json').read_text()) for s in ('','_repeat')]
    if first['source_sha256']!=repeat['source_sha256'] or first['source_sha256']!=sha256(OUT/'pilot.candidates.json') or first['points']!=repeat['points']:
        raise ValueError('Actual PCG provenance/repeat failed')
    pairs=pcg_foliage.validate_output(candidate,first)
    if {a['id'] for a,b in pairs}!=set(range(24)):raise ValueError('Pilot anchor/exclusion inventory failed')
    sample,_=join.sampler(MASTER,SOURCE,BASE);rows=[];checks=[]
    for anchor,point in pairs:
        draw=pcg_foliage.authored_yaw(point['rotation_xyzw'])/360
        scales=point['scale_xyz']
        if max(scales)-min(scales)>1e-6 or not .95-1e-6<=scales[0]<=1.05+1e-6:raise ValueError('Unexpected PCG scale')
        row,check=ground_pose(sample,plan['anchors'][anchor['id']],math.radians(draw*28-14),scales[0]);rows.append(row);checks.append(check)
    refs=plan['sources']+[{'path':str(OUT/name),'sha256':sha256(OUT/name)} for name in ['pilot.plan.json','pilot.pcg.json','pilot_repeat.pcg.json','request.receipt.json']]
    doc={'schema':adapter.SCHEMA,'coordinates':'unreal_centimetres','no_native_collision':True,'no_navigation':True,
        'exclusion_square_half_extent_m':1050,'sources':refs,'material':json.loads(MATERIAL.read_text()),
        'cull_cm':[600000,1000000],'instances':rows}
    target=OUT/'render-only-hism.json';dump(target,doc);_,receipt=adapter.groups(target)
    receipt.update(schema='pwr-apron-cliff-pilot-receipt-v1',grounding=checks,actual_pcg=True,repeat_identical=True,
        excluded_fixtures=2,status='Actual PCG/offline bounds passed; actual view/editor cook/FPS pending')
    dump(OUT/'pilot.receipt.json',receipt);print(json.dumps({k:receipt[k] for k in ['instances','components','instanced_source_triangles','sha256']}))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('command',choices=['prepare','export']);a=p.parse_args()
    prepare() if a.command=='prepare' else export()
