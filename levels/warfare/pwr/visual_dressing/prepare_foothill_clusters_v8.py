"""Regroup the same native cliff palette into9 overlapping eroded shoulders."""
from pathlib import Path
import copy,json,math,sys
import numpy as np
from finish_foothills_v8 import ROOT,BASE,ExactPackagedApron,ground_module,ref
sys.path.insert(0,str(ROOT/'tools/level'))
from heightfield import load_heightfield
import render_only_hism as h

OUT=BASE/'clustered';OLD=BASE/'full-grounded';SEED=20821
def write(name,data):(OUT/name).write_text(json.dumps(data,indent=2)+'\n')

def main():
    OUT.mkdir(exist_ok=True)
    if (OUT/'preparation.receipt.json').exists():raise ValueError('Preserve clustered proposal')
    plan=json.loads((OLD/'cliffs.plan.json').read_text());treeplan=json.loads((OLD/'trees.plan.json').read_text())
    ground=ExactPackagedApron();field=load_heightfield(ground_module.SOURCE);rng=np.random.default_rng(SEED)
    anchors=[];checks=[];poses=copy.deepcopy(plan['preserved_instances'])
    for ridge in ('west','east','north'):
        entries=[copy.deepcopy(a) for a in plan['anchors'] if a['ridge']==ridge]
        macros=[a for a in entries if 'Macro_B.' in a['mesh']];panels=[a for a in entries if '/Desert/' in a['mesh']];toes=[a for a in entries if 'Uluwatu' in a['mesh']]
        for j,main in enumerate(macros):
            x,y=main['anchor_m'][:2];gx=float((ground.sample(x+8,y)-ground.sample(x-8,y))/16);gy=float((ground.sample(x,y+8)-ground.sample(x,y-8))/16)
            uphill=np.array([gx,gy]);uphill/=np.linalg.norm(uphill);tangent=np.array([-uphill[1],uphill[0]])
            main['heading_radians']=float(math.atan2(tangent[1],tangent[0]));main['exposure_m']=min(65,main['exposure_m'])
            group=[main]
            # Wide structural face +2 flanking panels each side. Unequal depth
            # and height avoid an even fence; outer panels tuck into uphill soil.
            for k,entry in enumerate(panels[j*4:(j+1)*4]):
                side=(-1 if k<2 else 1);distance=(62 if k%2==0 else 103)*main['scale'][0]/.9
                xy=np.array([x,y])+tangent*(side*distance)+uphill*(15 if k%2==0 else 30)
                entry['anchor_m']=[*map(float,xy),float(ground.sample(*xy))]
                entry['heading_radians']=main['heading_radians']+side*(.14 if k%2==0 else .26)
                entry['exposure_m']=float((28 if k%2==0 else 17)+rng.uniform(-3,3));entry['tilt_radians']=float(rng.uniform(-.16,.08))
                group.append(entry)
            for k,entry in enumerate(toes[j*3:min((j+1)*3,len(toes))]):
                along=([-48,20,75] if j<2 else [-38,48])[k]
                xy=np.array([x,y])+tangent*along-uphill*(38+rng.uniform(-8,8))
                entry['anchor_m']=[*map(float,xy),float(ground.sample(*xy))];entry['heading_radians']=main['heading_radians']+float(rng.uniform(-.3,.3))
                entry['exposure_m']=float(rng.uniform(8,16));entry['scale'][2]*=.8;entry['tilt_radians']=float(rng.uniform(-.18,.05));group.append(entry)
            for entry in group:
                row,check=ground_module.pose(ground,entry);anchors.append(entry);poses.append(row);checks.append(check)
    if len(anchors)!=69 or len({r['id'] for r in anchors})!=69:raise ValueError('Palette count changed')
    # Retain exterior tree roots where clear, relocate only contacts now covered
    # by clustered rock. All final positions still require actual UE-PCG output.
    boxes=[]
    for row in poses:
        lo,hi=h.transformed_bounds(row);boxes.append([lo[0]/100,-hi[1]/100,hi[0]/100,-lo[1]/100])
    trees=[];moved=[];curves=plan['curves_m']
    def clear(x,y):return not any(b[0]-12<x<b[2]+12 and b[1]-12<y<b[3]+12 for b in boxes)
    for old in treeplan['instances']:
        entry=copy.deepcopy(old);x,y=entry['position_m'][:2]
        if not clear(x,y):
            found=False
            for attempt in range(20000):
                curve=np.array(curves[entry['ridge']]);segment=int(rng.integers(0,3));t=rng.random();center=curve[segment]*(1-t)+curve[segment+1]*t
                inward=-center/np.linalg.norm(center);along=np.array([-inward[1],inward[0]])
                x,y=center+inward*rng.uniform(60,260)+along*rng.normal(0,90)
                if max(abs(x),abs(y))<1070 or not clear(x,y):continue
                z=float(ground.sample(x,y));gx=float((ground.sample(x+5,y)-ground.sample(x-5,y))/10);gy=float((ground.sample(x,y+5)-ground.sample(x,y-5))/10)
                if not 100<z<460 or math.hypot(gx,gy)>.7 or float(field.sample_mask('flow',x,y))>.65:continue
                if any((x-r['position_m'][0])**2+(y-r['position_m'][1])**2<81 for r in trees):continue
                entry['position_m']=[float(x),float(y),z];entry['normal']=[-gx/(1+gx*gx+gy*gy)**.5,-gy/(1+gx*gx+gy*gy)**.5,1/(1+gx*gx+gy*gy)**.5]
                found=True;break
            if not found:raise ValueError('No clear exterior tree relocation')
            moved.append(entry['id'])
        trees.append(entry)
    refs=plan['sources']+[ref(OLD/'cliffs.plan.json'),ref(OLD/'trees.plan.json'),ref(Path(__file__))]
    write('cliffs.plan.json',dict(plan,seed=SEED,anchors=anchors,sources=refs,status='Clustered CPU proposal; actualPCG/visual review pending'))
    write('trees.plan.json',dict(treeplan,seed=SEED+1,instances=trees,sources=refs,status='Retained/relocated exterior anchors; actualPCG pending'))
    jobs=[]
    for label,entries in [('cliffs',anchors),('trees',trees)]:
        points=[{'id':i,'position':e.get('anchor_m',e.get('position_m')),'normal':[0,0,1],'density':1.,'biome_mask':1,'kind':'exterior_'+label} for i,e in enumerate(entries)]
        points += [{'id':10000+i,'position':points[0]['position'],'normal':[0,0,1],'density':d,'biome_mask':m,'kind':'excluded_fixture'} for i,(d,m) in enumerate(((0.,1),(1.,0)))]
        candidate=OUT/(label+'.candidates.json');write(candidate.name,{'schema':1,'align_to_normal':False,'points':points})
        for suffix in ('','_repeat'):jobs.append({'input':str(candidate),'output':str(OUT/(label+suffix+'.pcg.json')),
            'graph':'/Game/MJOLNIR/PCGAuthoring/PWRVisualV8/PCG_clustered_'+label+suffix,'seed':SEED+(label=='trees'),'scale_min':.95,'scale_max':1.05})
    write('request.json',{'jobs':jobs});write('preview.json',{'instances':poses,'grounding':checks})
    write('preparation.receipt.json',{'schema':'pwr-v8-clustered-foothill-preparation-v1','cliffs':96,'preserved_heroes_exact':True,
        'source_triangles':sum(h.ASSETS[r['mesh']]['source_triangles'] for r in poses),'new_cluster_count':9,'trees':600,
        'relocated_exterior_tree_ids':moved,'preserved_gameplay_population':True,'native_collision_additions':0})
    print(json.dumps({'cliffs':96,'trees':600,'moved_exterior_roots':len(moved),'source_triangles':sum(h.ASSETS[r['mesh']]['source_triangles'] for r in poses)}))

if __name__=='__main__':main()
