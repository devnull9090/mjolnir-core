# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy>=2,<3", "scipy==1.17.0"]
# ///
"""Run the approved stand anchors through actual UE PCG, retaining its poses.

Preparation emits probabilities only; export requires a deterministic pair of
real editor outputs and a measured complete-pine recipe. Existing installed
selections and geometry are never rewritten by this isolated candidate tool.
"""
import argparse
import json
from pathlib import Path
import sys
import numpy as np

ROOT=Path(__file__).resolve().parents[4]
sys.path.insert(0,str(ROOT/'tools/level'))
from heightfield import load_heightfield,sha256
from authored_decor import PWR_MATURE_PINE_RECIPE,complete_tree_recipe
import pcg_foliage
import pcg_tree_decor

OUT=ROOT/'out/pwr/visual-v5/outcrops-v4/trees'
MASTER=ROOT/'levels/warfare/pwr/terrain/runtime-v5/runtime-master.json'


def dump(path,value):
    Path(path).write_text(json.dumps(value,indent=2)+'\n')


def prepare(target=4500):
    if not 4000<=target<=5000:raise ValueError('Reviewed initial woodland budget is4000–5000 trees')
    anchors=OUT/'stands.candidates.json'
    source=pcg_foliage.load(anchors)
    if source['master_sha256']!=sha256(MASTER):raise ValueError('Candidate terrain provenance changed')
    for path,expected in source['pins'].items():
        if sha256(path)!=expected:raise ValueError('Candidate source changed: '+path)
    rows=source['points']
    weights=np.array([.65+.35*p['stand_weight'] for p in rows])
    low,high=0.,10.
    for _ in range(60):
        mid=(low+high)/2
        if np.minimum(1,weights*mid).sum()<target:low=mid
        else:high=mid
    density=np.minimum(1,weights*(low+high)/2)
    points=[dict(row,density=float(density[i]),biome='conifer_stand') for i,row in enumerate(rows)]
    path=OUT/'pcg.candidates.json'
    dump(path,dict(source,points=points,source_status='stand anchors with density probabilities; actual UE PCG pending'))
    dump(OUT/'palette.json',{'kinds':{'tree':{'recipes':[
        {'recipe':PWR_MATURE_PINE_RECIPE,'weight':.90},{'recipe':'Pine_Sapling_A','weight':.10}]}}})
    dump(OUT/'request.json',{'jobs':[{'input':str(path),'output':str(OUT/f'stands{suffix}.pcg.json'),
        'graph':'/Game/MJOLNIR/PCGAuthoring/PWRForestV4/PCG_stands'+suffix,
        'seed':20605,'scale_min':.8,'scale_max':1.25} for suffix in ('','_repeat')]})
    report={'schema':'pwr-forest-stands-pcg-input-v1','candidate_count':len(rows),
        'expected_selected':float(density.sum()),'hard_maximum_selected':5000,
        'candidate_source_sha256':sha256(anchors),'source_sha256':sha256(path),
        'palette_sha256':sha256(OUT/'palette.json'),'master_sha256':sha256(MASTER),'pins':source['pins'],
        'selection_pending_actual_ue_pcg':True,'old_root_anchors_in_pool':sum(p['retained_original_xy'] for p in rows)}
    dump(OUT/'pcg-input.receipt.json',report)
    print(json.dumps(report))


def export(recipes):
    recipes=Path(recipes)
    recipe_doc=pcg_foliage.load(recipes)
    measured=complete_tree_recipe(PWR_MATURE_PINE_RECIPE,recipe_doc)
    receipt=pcg_foliage.load(OUT/'pcg-input.receipt.json')
    for path,expected in receipt['pins'].items():
        if sha256(path)!=expected:raise ValueError('Source changed after actual PCG request: '+path)
    source,generated,repeat=OUT/'pcg.candidates.json',OUT/'stands.pcg.json',OUT/'stands_repeat.pcg.json'
    if sha256(source)!=receipt['source_sha256'] or sha256(OUT/'palette.json')!=receipt['palette_sha256']:
        raise ValueError('PCG input changed')
    comparison=pcg_foliage.compare(source,generated,repeat)
    result=pcg_foliage.adapt(source,generated,OUT/'palette.json',OUT,'trees')
    if not 4000<=result['selected_count']<=5000:raise ValueError('Actual selection outside reviewed initial tree budget')
    authored=pcg_tree_decor.convert(result,recipe_doc,max_trees=5000)
    dump(OUT/'trees.authored-decor.json',authored)
    field=load_heightfield(MASTER)
    rows=result['instances'];xy=np.array([r['position'][:2] for r in rows])
    z=np.array([r['position'][2] for r in rows]);error=np.abs(z-field.sample(xy[:,0],xy[:,1]))
    if error.max()>1e-5:raise ValueError('Generated roots no longer match frozen native field')
    from scipy.spatial import cKDTree
    spacing=float(cKDTree(xy).query(xy,k=2)[0][:,1].min())
    if spacing<6.8-1e-6:raise ValueError('PCG changed the minimum trunk spacing')
    heights={**pcg_tree_decor.NATIVE_PINE_HEIGHTS,
             PWR_MATURE_PINE_RECIPE:measured['min_z']+measured['height']-measured['root_z']}
    crown_tops=[r['position'][2]+heights[r['recipe']]*r['scale']/100 for r in rows]
    if max(crown_tops)>=500:raise ValueError('Tree crowns invade reserved insertion airspace')
    report={'schema':'pwr-forest-stands-pcg-output-v1','master_sha256':field.manifest_sha256,
        'source_sha256':sha256(source),'selection_sha256':sha256(OUT/'trees.selected.json'),
        'recipe_file_sha256':sha256(recipes),'geometry_sha256':measured['geometry_sha256'],
        'request_receipt_sha256':sha256(OUT/'request.receipt.json'),'repeat':comparison,
        'selected_count':len(rows),'by_recipe':{r:sum(p['recipe']==r for p in rows) for r in heights},
        'root_height_max_error_m':float(error.max()),'minimum_trunk_gap_m':spacing,
        'maximum_crown_top_m':max(crown_tops),'flight_clearance_m':550-max(crown_tops),
        'scope':'Candidate actual UE PCG poses only; measured hull/vegetation footprint audit and installed appearance/FPS still required'}
    dump(OUT/'pcg-output.receipt.json',report)
    print(json.dumps(report))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('command',choices=['prepare','export'])
    p.add_argument('--target',type=int,default=4500)
    p.add_argument('--recipes',type=Path,default=OUT/'recipes.json')
    a=p.parse_args()
    prepare(a.target) if a.command=='prepare' else export(a.recipes)
