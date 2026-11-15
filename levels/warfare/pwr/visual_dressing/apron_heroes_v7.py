"""Larger exterior ridge comparison, isolated from the original24-piece pilot."""
from pathlib import Path
import argparse
import copy
import json
import math
import numpy as np
import apron_cliffs_v7 as pilot

ROOT=pilot.ROOT
CONTROL=ROOT/'out/pwr/visual-v7/apron-cliffs'
OUT=CONTROL/'heroes'
SEED=20719


def prepare():
    OUT.mkdir(parents=True,exist_ok=True);pilot.OUT=OUT
    old=json.loads((CONTROL/'pilot.plan.json').read_text());anchors=copy.deepcopy(old['anchors'])
    sample,_=pilot.join.sampler(pilot.MASTER,pilot.SOURCE,pilot.BASE)
    rng=np.random.default_rng(SEED)
    for entry in anchors:
        entry['crest_exposure_m']=float(rng.uniform(18,30))
        entry['scale'][2]=min(2.9,max(2.1,entry['scale'][2]*1.4))
    macro=next(p for p in pilot.adapter.ASSETS if 'SM_PNWGL_Rock_Macro_B.' in p)
    for index,center in enumerate(old['ridge_centres']):
        x,y,z=center['position_m']
        gx=float((sample(x+8,y)-sample(x-8,y))/16);gy=float((sample(x,y+8)-sample(x,y-8))/16)
        anchors.append({'id':'pwr_apron_cliff_'+center['id']+'_hero','ridge':center['id'],'mesh':macro,
            'anchor_m':[x,y,z],'heading_radians':math.atan2(gy,gx)+math.pi/2,
            'tilt_radians':[-.06,.08,-.04][index],
            'scale':[[.72,.78,.72],[.82,.9,.8],[.76,.8,.74]][index],
            'crest_exposure_m':[48.,58.,45.][index]})
    refs=[pilot.MASTER,pilot.SOURCE,pilot.BASE/'harmonic-field.npz',pilot.BASE/'join.receipt.json',pilot.MATERIAL,
        CONTROL/'pilot.plan.json',Path(__file__),Path(pilot.__file__),ROOT/'tools/level/render_only_hism.py']
    asset_checks=[]
    for mesh in sorted({r['mesh'] for r in anchors}):
        leaf=mesh.split('.')[-1];path=OUT/'assets'/f'{leaf}.glb';refs.append(path)
        points=pilot.source_points(mesh);lo,hi=np.array(pilot.adapter.ASSETS[mesh]['bounds_cm'])
        excess=float(np.max(np.maximum(lo-points,points-hi)))
        if excess>.1:raise ValueError('Native bounds mismatch')
        asset_checks.append({'mesh':mesh,'source_sha256':pilot.sha256(path),'vertices':len(points),
            'maximum_catalog_bound_excess_cm':excess,'world_bound_guard_cm':.1})
    plan={'schema':'pwr-apron-cliff-hero-pilot-v1','seed':SEED,'ridge_centres':old['ridge_centres'],'anchors':anchors,
        'sources':[{'path':str(p),'sha256':pilot.sha256(p)} for p in refs],
        'control_unchanged':True,'geometry_policy':'3 native MacroB formations plus24 taller fractured faces; fullbounds exterior1050m; no collision',
        'status':'CPU comparison; actualPCG and geometry/material preview pending'}
    pilot.dump(OUT/'pilot.plan.json',plan)
    posed=[pilot.ground_pose(sample,e) for e in anchors];rows=[r for r,c in posed]
    pilot.dump(OUT/'pilot.preview-transforms.json',{'status':'CPU planned transforms; not actualPCG output','instances':rows})
    pilot.dump(OUT/'pilot.preview-grounding.json',{'status':'CPU fullnative lower-surface and bounds checks only',
        'plan_sha256':pilot.sha256(OUT/'pilot.plan.json'),'source_triangles':sum(pilot.adapter.ASSETS[e['mesh']]['source_triangles'] for e in anchors),
        'checks':[c for r,c in posed]})
    pilot.dump(OUT/'assets.receipt.json',{'schema':'pwr-apron-cliff-native-assets-v1','assets':asset_checks,
        'exporter_sha256':pilot.sha256(ROOT/'out/pwr/toolchain-mesh-attrs-v2/mjolnir.exe'),'native_geometry_not_recooked':True})
    points=[{'id':i,'position':a['anchor_m'],'normal':[0,0,1],'density':1.,'biome_mask':1,'kind':'exterior_ridge_hero_anchor'} for i,a in enumerate(anchors)]
    for i,density,mask in [(1000,0.,1),(1001,1.,0)]:points.append({'id':i,'position':points[0]['position'],'normal':[0,0,1],'density':density,'biome_mask':mask,'kind':'excluded_fixture'})
    candidate=OUT/'pilot.candidates.json'
    pilot.dump(candidate,{'schema':1,'align_to_normal':False,'master_sha256':pilot.sha256(pilot.SOURCE),
        'plan_sha256':pilot.sha256(OUT/'pilot.plan.json'),'points':points})
    pilot.dump(OUT/'request.json',{'jobs':[{'input':str(candidate),'output':str(OUT/f'pilot{s}.pcg.json'),
        'graph':'/Game/MJOLNIR/PCGAuthoring/PWRVisualV7/PCG_apron_heroes'+s,'seed':SEED,'scale_min':.95,'scale_max':1.05}
        for s in ('','_repeat')]})
    pilot.plot(sample,old['ridge_centres'],rows)
    print(json.dumps({'anchors':len(anchors),'source_triangles':sum(pilot.adapter.ASSETS[a['mesh']]['source_triangles'] for a in anchors),
        'hero_checks':[c for r,c in posed if r['id'].endswith('_hero')],
        'cliff_exposure_minmax_m':[min(c['top_above_center_m'] for r,c in posed if not r['id'].endswith('_hero')),
                                    max(c['top_above_center_m'] for r,c in posed if not r['id'].endswith('_hero'))]}))


def export():
    pilot.OUT=OUT;plan=json.loads((OUT/'pilot.plan.json').read_text());candidate=json.loads((OUT/'pilot.candidates.json').read_text())
    if candidate['plan_sha256']!=pilot.sha256(OUT/'pilot.plan.json'):raise ValueError('Hero plan changed')
    for ref in plan['sources']:
        if pilot.sha256(ref['path'])!=ref['sha256']:raise ValueError('Hero source changed')
    first,repeat=[json.loads((OUT/f'pilot{s}.pcg.json').read_text()) for s in ('','_repeat')]
    if first['source_sha256']!=repeat['source_sha256'] or first['source_sha256']!=pilot.sha256(OUT/'pilot.candidates.json') or first['points']!=repeat['points']:
        raise ValueError('ActualPCG source/repeat failed')
    pairs=pilot.pcg_foliage.validate_output(candidate,first)
    if {a['id'] for a,b in pairs}!=set(range(27)):raise ValueError('Hero selection/exclusion inventory failed')
    sample,_=pilot.join.sampler(pilot.MASTER,pilot.SOURCE,pilot.BASE);rows=[];checks=[]
    for anchor,point in pairs:
        draw=pilot.pcg_foliage.authored_yaw(point['rotation_xyzw'])/360;scales=point['scale_xyz']
        if max(scales)-min(scales)>1e-6 or not .95-1e-6<=scales[0]<=1.05+1e-6:raise ValueError('PCG scale changed')
        row,check=pilot.ground_pose(sample,plan['anchors'][anchor['id']],math.radians(draw*28-14),scales[0]);rows.append(row);checks.append(check)
    refs=plan['sources']+[{'path':str(OUT/name),'sha256':pilot.sha256(OUT/name)} for name in ['pilot.plan.json','pilot.pcg.json','pilot_repeat.pcg.json','request.receipt.json']]
    doc={'schema':pilot.adapter.SCHEMA,'coordinates':'unreal_centimetres','no_native_collision':True,'no_navigation':True,
        'exclusion_square_half_extent_m':1050,'sources':refs,'material':json.loads(pilot.MATERIAL.read_text()),
        'cull_cm':[600000,1000000],'instances':rows}
    target=OUT/'render-only-hism.json';pilot.dump(target,doc);_,receipt=pilot.adapter.groups(target)
    receipt.update(schema='pwr-apron-cliff-hero-receipt-v1',grounding=checks,actual_pcg=True,repeat_identical=True,
        excluded_fixtures=2,status='ActualPCG/offline bounds passed; actualview/editorcook/FPS pending')
    pilot.dump(OUT/'pilot.receipt.json',receipt);print(json.dumps({k:receipt[k] for k in ['instances','components','instanced_source_triangles','sha256']}))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('command',choices=['prepare','export']);a=p.parse_args()
    prepare() if a.command=='prepare' else export()
