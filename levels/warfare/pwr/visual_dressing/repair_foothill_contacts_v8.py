"""Prepare another actual-PCG request for only post-variation tree contacts."""
import copy,json,math
from pathlib import Path
import numpy as np
from finish_foothills_v8 import BASE,ExactPackagedApron,ground_module,ref
from heightfield import load_heightfield
import render_only_hism as h

SOURCE=BASE/'clustered';SELECTED=BASE/'clustered-selected';OUT=BASE/'clustered-contact'
def write(name,value):(OUT/name).write_text(json.dumps(value,indent=2)+'\n')
def main():
    OUT.mkdir(exist_ok=True)
    if (OUT/'contact-repair.json').exists():raise ValueError('Preserve contact repair evidence')
    cliffs=json.loads((SELECTED/'render-only-hism.json').read_text())['instances'];plan=json.loads((SOURCE/'trees.plan.json').read_text())
    points=json.loads((SOURCE/'trees.candidates.json').read_text());ground=ExactPackagedApron();field=load_heightfield(ground_module.SOURCE)
    boxes=[h.transformed_bounds(r) for r in cliffs];repairs=[]
    def clearance(x,y):
        x*=100;y*=-100
        return min(math.hypot(max(lo[0]-x,0,x-hi[0]),max(lo[1]-y,0,y-hi[1]))/100 for lo,hi in boxes)
    for i,entry in enumerate(plan['instances']):
        ox,oy=entry['position_m'][:2]
        if clearance(ox,oy)>=3:continue
        choices=[]
        for radius in (10,18,28,40,60):
            for angle in np.linspace(0,2*math.pi,32,endpoint=False):
                x,y=ox+radius*math.cos(angle),oy+radius*math.sin(angle)
                if max(abs(x),abs(y))<1070 or clearance(x,y)<8:continue
                if any(j!=i and (x-other['position_m'][0])**2+(y-other['position_m'][1])**2<81 for j,other in enumerate(plan['instances'])):continue
                z=float(ground.sample(x,y));gx=float((ground.sample(x+5,y)-ground.sample(x-5,y))/10);gy=float((ground.sample(x,y+5)-ground.sample(x,y-5))/10)
                if not 100<z<460 or math.hypot(gx,gy)>.7 or float(field.sample_mask('flow',x,y))>.65:continue
                choices.append((radius,abs(z-entry['position_m'][2]),x,y,z,gx,gy))
            if choices:break
        if not choices:raise ValueError('No safe exterior root contact alternative')
        _,_,x,y,z,gx,gy=min(choices);old=entry['position_m']
        entry['position_m']=[x,y,z];entry['normal']=[-gx/(1+gx*gx+gy*gy)**.5,-gy/(1+gx*gx+gy*gy)**.5,1/(1+gx*gx+gy*gy)**.5]
        points['points'][i]['position']=[x,y,z];repairs.append({'id':entry['id'],'before_m':old,'after_m':[x,y,z],'final_root_to_rock_aabb_m':clearance(x,y)})
    for file in ['cliffs.plan.json','cliffs.candidates.json']:(OUT/file).write_bytes((SOURCE/file).read_bytes())
    plan['sources'] += [ref(SELECTED/'render-only-hism.json'),ref(Path(__file__))]
    write('trees.plan.json',plan);write('trees.candidates.json',points)
    request=json.loads((SOURCE/'request.json').read_text())
    for job in request['jobs']:
        job['input']=str(OUT/Path(job['input']).name);job['output']=str(OUT/Path(job['output']).name);job['graph']=job['graph'].replace('PCG_clustered_','PCG_clustered_contact_')
    write('request.json',request);write('contact-repair.json',{'repairs':repairs,'reason':'Final engine yaw/scale expanded Macro_B footprint into2 proposed exterior roots; no gameplay roots moved'})
    print(json.dumps({'repaired_exterior_roots':len(repairs),'details':repairs}))

if __name__=='__main__':main()
