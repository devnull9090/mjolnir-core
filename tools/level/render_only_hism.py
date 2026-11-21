"""Explicit exterior cliff instances, excluded from native scenery/collision.

This adapter is deliberately independent of swap.decor. Only audited shipped
cliff meshes outside the gameplay square are accepted. Default foliage builds
do not read this file or change any groups.
"""
from pathlib import Path
import copy
import hashlib
import itertools
import json
import math

SCHEMA = 'pwr-render-only-hism-v1'
PARENT = '/Game/MJOLNIR/CETrial/M_CE_PWRRock.M_CE_PWRRock'
TEXTURES = {k:f'/Game/Megascans/Surfaces/Rock_Jagged_udemcebew/T_Rock_Jagged_udemcebew_NSVT_{suffix}.T_Rock_Jagged_udemcebew_NSVT_{suffix}'
            for k,suffix in [('RockD','D'),('RockN','N')]}
ASSETS = {}
for variant,lo,hi,tris in [
    ('A',[-1826.625,-1619.9375,-124.5],[1563.375,1948.5,2743.5625],284378),
    ('C',[-1350.5,-1753.75,-142.4375],[1250.6875,1208.25,2693.5],159803),
    ('D',[-2542.4375,-1350.8125,-139.75],[2566.5,1412.625,2779.5],177206)]:
    leaf='SM_Rock_Desert_Cliff_'+variant
    ASSETS[f'/Game/Env/Bio/Rock/Desert/Rock_Desert_Cliff_{variant}/{leaf}.{leaf}']={'bounds_cm':[lo,hi],'source_triangles':tris}
for folder,leaf,lo,hi,tris in [
    ('PNW/PNWGL_Rock_Macro_B','SM_PNWGL_Rock_Macro_B',[-11044.8125,-8551.9375,-12456.25],[10407.375,7900,13218.25],441694),
    ('Uluwatu/Rock_Uluwatu_Cliff_B','SM_Rock_Uluwatu_Cliff_B',[-2695.375,-2149.125,-2850.9375],[3442.1875,3702.75,3194.75],567954)]:
    ASSETS[f'/Game/Env/Bio/Rock/{folder}/{leaf}.{leaf}']={'bounds_cm':[lo,hi],'source_triangles':tris}


def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def vector(value,n,label):
    if (not isinstance(value,list) or len(value)!=n or any(isinstance(x,bool) or not isinstance(x,(int,float)) or not math.isfinite(x) for x in value)):
        raise ValueError(f'Invalid finite {label}')
    return list(map(float,value))


def matrix(q):
    x,y,z,w=q
    return [[1-2*(y*y+z*z),2*(x*y-z*w),2*(x*z+y*w)],
            [2*(x*y+z*w),1-2*(x*x+z*z),2*(y*z-x*w)],
            [2*(x*z-y*w),2*(y*z+x*w),1-2*(x*x+y*y)]]


def transformed_bounds(row):
    rot=matrix(row['rotation_xyzw']);lo,hi=ASSETS[row['mesh']]['bounds_cm'];result=[]
    for point in itertools.product(*zip(lo,hi)):
        scaled=[point[i]*row['scale'][i] for i in range(3)]
        result.append([sum(rot[i][j]*scaled[j] for j in range(3))+row['position_cm'][i] for i in range(3)])
    # One millimetre also covers source-float/native world-transform rounding.
    return [[min(p[i] for p in result)-.1 for i in range(3)], [max(p[i] for p in result)+.1 for i in range(3)]]


def material(value):
    if not isinstance(value,dict) or set(value)-{'parent','textures','vectors','scalars'}:
        raise ValueError('Unsupported exterior material fields')
    if value.get('parent')!=PARENT or value.get('textures')!=TEXTURES or value.get('scalars'):
        raise ValueError('Exterior cliffs require the verified world-space gray/no-snow rock binding')
    vectors=value.get('vectors',{})
    if set(vectors)!={'RockTint','RockParams'}:raise ValueError('Explicit rock parameters required')
    for key,entry in vectors.items():vector(entry,4,key)
    return copy.deepcopy(value)


def load(path):
    path=Path(path).resolve();doc=json.loads(path.read_text())
    if doc.get('schema')!=SCHEMA or doc.get('coordinates')!='unreal_centimetres':raise ValueError('Wrong render-only HISM schema/coordinates')
    if doc.get('no_native_collision') is not True or doc.get('no_navigation') is not True:
        raise ValueError('Exterior-only geometry must explicitly disable collision/navigation')
    if doc.get('exclusion_square_half_extent_m')!=1050:raise ValueError('Exact exterior safety square1050m required')
    proof=doc.get('sources',[])
    if not proof:raise ValueError('Hash-bound source provenance required')
    for entry in proof:
        source=(path.parent/entry['path']).resolve()
        if not source.is_file() or digest(source)!=entry.get('sha256'):raise ValueError(f'Changed exterior source: {source}')
    binding=material(doc.get('material'))
    cull=vector(doc.get('cull_cm'),2,'cull')
    if not 0<=cull[0]<cull[1]<=1200000 or any(int(x)!=x for x in cull):raise ValueError('Invalid exterior cull range')
    rows=doc.get('instances');ids=set();total=0
    if not isinstance(rows,list) or not 1<=len(rows)<=120:raise ValueError('Exterior cliff count must be1..120')
    for row in rows:
        if set(row)-{'id','mesh','position_cm','rotation_xyzw','scale','ridge'}:raise ValueError('Unknown exterior instance field')
        if not isinstance(row.get('id'),str) or not row['id'].startswith('pwr_apron_cliff_') or row['id'] in ids:raise ValueError('Invalid/duplicate exterior id')
        ids.add(row['id'])
        if row.get('mesh') not in ASSETS:raise ValueError('Unreviewed exterior mesh')
        vector(row.get('position_cm'),3,'position');q=vector(row.get('rotation_xyzw'),4,'quaternion');s=vector(row.get('scale'),3,'scale')
        if abs(sum(x*x for x in q)-1)>1e-6 or not all(.1<=x<=3 for x in s):raise ValueError('Invalid exterior rotation/scale')
        lo,hi=transformed_bounds(row)
        if not (lo[0]>105000 or hi[0]<-105000 or lo[1]>105000 or hi[1]<-105000):
            raise ValueError('Full exterior mesh bounds enter the protected1050m square')
        if max(abs(x) for x in lo[:2]+hi[:2])>400000:raise ValueError('Exterior cliff extends beyond the source domain')
        total+=ASSETS[row['mesh']]['source_triangles']
    if total>40000000:raise ValueError('Exterior source triangle budget exceeds40million')
    return doc, {'path':str(path),'sha256':digest(path),'instances':len(rows),'instanced_source_triangles':total,'material':binding}


def groups(path, cell_cm=None):
    doc,receipt=load(path);buckets={}
    # Legacy manifests retain their exact500m grouping. Only explicit new
    # manifests may request the reviewed V8 1.25km grouping.
    declared=doc.get('grouping_cell_cm',50000)
    if declared not in (50000,125000) or isinstance(declared,bool):raise ValueError('Unreviewed exterior grouping cell')
    if cell_cm is not None and cell_cm!=declared:raise ValueError('Grouping override differs from manifest')
    cell_cm=declared
    for row in doc['instances']:
        pos=row['position_cm'];q=row['rotation_xyzw'];s=row['scale'];rot=matrix(q)
        # Foliage exact records contain the scaled local basis as rows.
        basis=[rot[i][j]*s[j] for j in range(3) for i in range(3)]
        record=[*pos,0,s[0],0,0,*basis]
        key=(row['mesh'],math.floor(pos[0]/cell_cm),math.floor(pos[1]/cell_cm))
        buckets.setdefault(key,[]).append((row['id'],record))
    if len(buckets)>48:raise ValueError('Exterior HISM component budget exceeds48')
    result=[]
    for key,rows in sorted(buckets.items()):
        rows.sort()
        result.append(([r for _,r in rows],{'mesh':key[0],'rule':'exterior cliffs','bands':1,
            'cull':doc['cull_cm'],'shadow':True,'static':True,'exact':True},[ident for ident,_ in rows]))
    receipt.update(components=len(result),groups=[])
    if 'grouping_cell_cm' in doc:receipt['grouping_cell_cm']=cell_cm
    return result,receipt
