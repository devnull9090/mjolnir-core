"""Validate actual UE-PCG and ground the isolated V8 foothills on packaged apron."""
from pathlib import Path
import copy
import argparse
import importlib.util
import json
import math
import sys
import numpy as np

ROOT=Path(__file__).resolve().parents[4]
BASE=ROOT/'out/pwr/visual-v8/foothills'
INPUT=BASE/'full-grounded';OUT=BASE/'selected'
sys.path.insert(0,str(ROOT/'tools/level'))
import render_only_hism as cliffs
import render_only_pines as pines
import pcg_foliage
spec=importlib.util.spec_from_file_location('v8_ground',BASE/'prepare_full_candidate.py')
ground_module=importlib.util.module_from_spec(spec);spec.loader.exec_module(ground_module)

class ExactPackagedApron(ground_module.PackagedApron):
    """Adaptive triangles can be long/thin: nearest-centroid isn't sufficient."""
    def sample(self,x,y):
        x,y=np.broadcast_arrays(x,y);points=np.c_[x.ravel(),y.ravel()];result=np.empty(len(points));pending=np.arange(len(points))
        def resolve(p,ids):
            a=self.xy[ids,0];b=self.xy[ids,1]-a;c=self.xy[ids,2]-a;q=p[:,None]-a
            det=b[:,:,0]*c[:,:,1]-b[:,:,1]*c[:,:,0]
            u=(q[:,:,0]*c[:,:,1]-q[:,:,1]*c[:,:,0])/det;v=(b[:,:,0]*q[:,:,1]-b[:,:,1]*q[:,:,0])/det
            inside=(u>=-1e-8)&(v>=-1e-8)&(u+v<=1+1e-8);has=inside.any(axis=1);first=inside.argmax(axis=1)
            z=self.z[ids,0]+u*(self.z[ids,1]-self.z[ids,0])+v*(self.z[ids,2]-self.z[ids,0])
            return has,z[np.arange(len(p)),first]
        for k in (12,48,192,1024):
            remaining=[]
            for start in range(0,len(pending),2048 if k<192 else 256):
                ids=pending[start:start+(2048 if k<192 else 256)];p=points[ids]
                has,z=resolve(p,self.tree.query(p,k=k,workers=1)[1]);result[ids[has]]=z[has];remaining.extend(ids[~has])
            pending=np.asarray(remaining,dtype=int);self.maximum_search_neighbors=max(self.maximum_search_neighbors,k)
            if not len(pending):break
        if len(pending):
            low=self.xy.min(axis=1);high=self.xy.max(axis=1)
            for i in pending:
                p=points[i];ids=np.flatnonzero(np.all(low<=p+1e-8,axis=1)&np.all(high>=p-1e-8,axis=1))
                if not len(ids):raise ValueError('No packaged triangle bounds contain '+repr(p))
                has,z=resolve(p[None],ids[None])
                if not has[0]:raise ValueError('Packaged apron topology gap at '+repr(p))
                result[i]=z[0]
        self.queries+=len(points);return result.reshape(x.shape)

def write(name,value):(OUT/name).write_text(json.dumps(value,indent=2)+'\n')
def ref(path):return {'path':str(Path(path).resolve()),'sha256':cliffs.digest(path)}

def main():
    global INPUT,OUT
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--input',type=Path,default=INPUT);parser.add_argument('--out',type=Path,default=OUT)
    args=parser.parse_args();INPUT=args.input.resolve();OUT=args.out.resolve()
    OUT.mkdir(parents=True,exist_ok=True)
    if (OUT/'receipt.json').exists():raise ValueError('Preserve selected proof; use a new revision')
    plans={label:json.loads((INPUT/f'{label}.plan.json').read_text()) for label in ('cliffs','trees')}
    # Keep original source code evidence frozen even as the opt-in adapter grows.
    refs={}
    for plan in plans.values():
        for entry in plan['sources']:
            path=Path(entry['path'])
            if path.resolve()==(ROOT/'tools/level/render_only_hism.py').resolve():path=BASE/'source-snapshots/render_only_hism.py'
            if cliffs.digest(path)!=entry['sha256']:raise ValueError('Changed prepared source: '+str(path))
            refs[str(path.resolve())]=ref(path)
    selected={};proofs={}
    for label in ('cliffs','trees'):
        paths=[INPUT/f'{label}{suffix}' for suffix in ('.candidates.json','.pcg.json','_repeat.pcg.json')]
        proofs[label]=pcg_foliage.compare(*paths)
        source,generated=[json.loads(p.read_text()) for p in paths[:2]]
        pairs=pcg_foliage.validate_output(source,generated)
        expected=69 if label=='cliffs' else 600
        if [a['id'] for a,b in pairs]!=list(range(expected)):raise ValueError('PCG selection/exclusion inventory changed')
        selected[label]=pairs
        for path in paths:refs[str(path.resolve())]=ref(path)
    for path in [INPUT/'request.json',INPUT/'request.receipt.json',INPUT/'cliffs.plan.json',INPUT/'trees.plan.json',Path(__file__),ROOT/'tools/level/render_only_hism.py',ROOT/'tools/level/render_only_pines.py',ROOT/'tools/level/pcg_foliage.py']:
        refs[str(path.resolve())]=ref(path)
    ground=ExactPackagedApron();rows=copy.deepcopy(plans['cliffs']['preserved_instances']);checks=[]
    for original,point in selected['cliffs']:
        entry=copy.deepcopy(plans['cliffs']['anchors'][original['id']]);scale=point['scale_xyz'][0]
        if not .95-1e-6<=scale<=1.05+1e-6:raise ValueError('Unexpected PCG scale')
        entry['heading_radians']+=math.radians(pcg_foliage.authored_yaw(point['rotation_xyzw'])/360*28-14)
        entry['scale']=[s*scale for s in entry['scale']]
        row,check=ground_module.pose(ground,entry);rows.append(row);checks.append(check)
    if rows[:27]!=plans['cliffs']['preserved_instances']:raise ValueError('Original27 transformed')
    tree_rows=[];treechecks=[]
    for original,point in selected['trees']:
        entry=plans['trees']['instances'][original['id']];mesh=pines.MATURE if entry['family']=='mature' else pines.SAPLING
        scale=entry['uniform_scale']*point['scale_xyz'][0];x,y=entry['position_m'][:2]
        z=float(ground.sample(x,y))*100
        row={'id':entry['id'],'mesh':mesh,'ridge':entry['ridge'],'position_cm':[x*100,-y*100,z-pines.ASSETS[mesh]['root_z_cm']*scale],
             'ground_z_cm':z,'rotation_xyzw':point['rotation_xyzw'],'scale':[scale]*3}
        tree_rows.append(row);treechecks.append({'id':row['id'],'bounds_ue_cm':pines.transformed_bounds(row),'ground_z_cm':z,'root_error_cm':0.})
    material=json.loads((ROOT/'out/pwr/visual-v7/apron-cliffs/heroes/render-only-hism.json').read_text())['material']
    shared={'coordinates':'unreal_centimetres','no_native_collision':True,'no_navigation':True,
            'exclusion_square_half_extent_m':1050,'sources':list(refs.values())}
    write('render-only-hism.json',dict(shared,schema=cliffs.SCHEMA,grouping_cell_cm=125000,material=material,cull_cm=[600000,1000000],instances=rows))
    write('render-only-pines.json',dict(shared,schema=pines.SCHEMA,grouping_cell_cm=50000,wpo=False,cast_shadow=True,
          preserve_native_material_slots=True,cull_cm=[250000,350000],instances=tree_rows))
    _,cliffproof=cliffs.groups(OUT/'render-only-hism.json');_,pineproof=pines.groups(OUT/'render-only-pines.json')
    if cliffproof['instanced_source_triangles']>31_400_000:raise ValueError('31.4M cliff cap exceeded')
    write('grounding.json',{'cliffs':checks,'trees':treechecks})
    report={'schema':'pwr-foothills-actual-pcg-v1','actual_pcg':proofs,'cliffs':cliffproof,'pines':pineproof,
        'preserved_heroes_exact':True,'native_collision_additions':0,'existing_native_population_changed':False,
        'full_bounds_exterior_1050m':True,'ground_source':'Exact accepted native packaged apron triangles',
        'maximum_apron_roundtrip_error_m':ground.maximum_roundtrip_error_m,'ground_queries':ground.queries,
        'low_exposure_faces':[c for c in checks if c['top_above_center_m']<15],
        'sources':list(refs.values()),'status':'Actual PCG and source checks passed; Blender/live/final cook pending'}
    write('receipt.json',report)
    print(json.dumps({'cliffs':cliffproof['instances'],'cliff_components':cliffproof['components'],'source_triangles':cliffproof['instanced_source_triangles'],
        'pines':pineproof['instances'],'pine_components':pineproof['components'],'low_exposure_faces':len(report['low_exposure_faces'])}))

if __name__=='__main__':main()
