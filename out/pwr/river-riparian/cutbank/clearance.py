from pathlib import Path
import sys
import json
import numpy as np
from scipy.spatial import cKDTree
sys.path.insert(0,'levels/warfare/pwr/terrain')
import headwater_dressing as d

def closest(points,triangles,neighbours):
    # Shortest Euclidean distance to faces or edges near these points.
    _,idx=cKDTree(triangles.mean(axis=1)).query(points,k=neighbours)
    t=triangles[idx]
    off=points[:,None,:]-t[:,:,0,:]
    e1=t[:,:,1,:]-t[:,:,0,:]
    e2=t[:,:,2,:]-t[:,:,0,:]
    dot=lambda a,b:(a*b).sum(axis=-1)
    a=dot(e1,e1); b=dot(e1,e2); c=dot(e2,e2); x=dot(off,e1); y=dot(off,e2)
    u=(c*x-b*y)/(a*c-b*b); v=(a*y-b*x)/(a*c-b*b)
    toplane=off-u[:,:,None]*e1-v[:,:,None]*e2
    sq=np.where((u>=0)&(v>=0)&(u+v<=1),dot(toplane,toplane),np.inf)
    for q in range(3):
        p=t[:,:,q,:]
        edge=t[:,:,(q+1)%3,:]-p
        cross=points[:,None,:]-p
        frac=np.clip(dot(edge,cross)/dot(edge,edge),0.,1.)
        out=cross-frac[:,:,None]*edge
        sq=np.minimum(sq,dot(out,out))
    return np.sqrt(sq.min(axis=1))
base=Path('out/pwr/river-apron')
work=Path('out/pwr/river-riparian/cutbank')
old=json.loads((base/'finish37/surface.json').read_bytes())
v=(np.array(old['positions'][:181*7])+old['origin_cm'])/[100,-100,100]
f=np.array(old['faces'][:180*12])
oldskin=v[f]
h=d.load_heightfield(base/'terrain/runtime-master.json')
geo=json.loads((work/'surface.json').read_bytes())
v=(np.array(geo['positions'])+geo['origin_cm'])/[100,-100,100]
alpha=np.array(geo['colors'])[:,3]
support=np.load(base/'bank/support.npz')['triangles_m'][:108]
z=np.array([h.sample(*p) for p in v[:,:2]])
clear=np.maximum(0,v[:,2]-z)
proof={}
outs=[]
for triangles,k in ((oldskin,20),(support,12)):
    ds=np.concatenate([closest(v[id:id+2000],triangles,k) for id in range(0,len(v),2000)])
    outs.append(np.minimum(clear,ds))
for a,label in [(0.,'loam'),(.5,'roots'),(1.,'stone')]:
    sel=alpha==a
    proof[label]={'n':int(sel.sum())}
    for arr,key in zip(outs,['from_previous_surface_or_grade_m','from_coarse_support_or_grade_m']):
        proof[label][key]=np.round(np.percentile(arr[sel],[50,95,99,100]),3).tolist()
print(proof)
(work/'clearance.json').write_text(json.dumps(proof,indent=2))

