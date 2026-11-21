"""Opt-in exterior pines using original native slots; never Blam scenery.

Only the measured complete mature pine and native sapling are supported.
Root contacts and full transformed bounds are checked before any bake writes.
"""
from pathlib import Path
import itertools
import json
import math
import struct
from render_only_hism import digest, matrix, vector

SCHEMA='pwr-render-only-pines-v1'
MATURE='/Game/MJOLNIR/Scenery/PWR/SM_PWR_MaturePine_A.SM_PWR_MaturePine_A'
SAPLING='/Game/Env/Bio/Tree/Pine/Tree_Pine_Sapling_A/Meshes/SM_Tree_Pine_Sapling_A.SM_Tree_Pine_Sapling_A'
ASSETS={
    MATURE:{'bounds_cm':[[-412.985,-443.844,-195.235],[411.641,371.407,2896.016]],'root_z_cm':0.,
            'slot_names':['MI_Pine_Tree_Mat','MI_Branch_Mat'],'source_triangles':111147},
    SAPLING:{'bounds_cm':[[-60.5,-82.8125,-5.3125],[55.6875,62.625,206]],'root_z_cm':-5.3124998,
             'slot_names':['Bark_Mat','Leaves_Mat'],'source_triangles':22891}}

def transformed_bounds(row):
    rot=matrix(row['rotation_xyzw']);lo,hi=ASSETS[row['mesh']]['bounds_cm'];points=[]
    for p in itertools.product(*zip(lo,hi)):
        q=[p[i]*row['scale'][i] for i in range(3)]
        points.append([sum(rot[i][j]*q[j] for j in range(3))+row['position_cm'][i] for i in range(3)])
    return [[min(p[i] for p in points)-1 for i in range(3)],[max(p[i] for p in points)+1 for i in range(3)]]

def load(path):
    path=Path(path).resolve();doc=json.loads(path.read_text())
    if doc.get('schema')!=SCHEMA or doc.get('coordinates')!='unreal_centimetres':raise ValueError('Wrong exterior pine schema/coordinates')
    for key,value in [('no_native_collision',True),('no_navigation',True),('wpo',False),('cast_shadow',True),('preserve_native_material_slots',True),('exclusion_square_half_extent_m',1050),('grouping_cell_cm',50000)]:
        if doc.get(key)!=value or (isinstance(value,bool) and doc.get(key) is not value):raise ValueError('Wrong exterior pine policy: '+key)
    if any(k in doc for k in ('material','materials','override_materials')):raise ValueError('Exterior pine material overrides forbidden')
    refs=doc.get('sources',[])
    if not refs:raise ValueError('Missing exterior pine source provenance')
    for ref in refs:
        source=(path.parent/ref['path']).resolve()
        if not source.is_file() or digest(source)!=ref.get('sha256'):raise ValueError('Changed exterior pine source: '+str(source))
    cull=vector(doc.get('cull_cm'),2,'cull')
    if not 0<=cull[0]<cull[1]<=350000 or any(int(v)!=v for v in cull):raise ValueError('Unsafe exterior pine cull')
    rows=doc.get('instances');ids=set();total=0;counts={mesh:0 for mesh in ASSETS}
    if not isinstance(rows,list) or not 1<=len(rows)<=600:raise ValueError('Exterior pine count exceeds600')
    for row in rows:
        if set(row)-{'id','mesh','position_cm','rotation_xyzw','scale','ridge','ground_z_cm'}:raise ValueError('Unknown exterior pine field')
        if not isinstance(row.get('id'),str) or not row['id'].startswith('pwr_exterior_pine_') or row['id'] in ids:raise ValueError('Invalid/duplicate exterior pine id')
        ids.add(row['id']);mesh=row.get('mesh')
        if mesh not in ASSETS:raise ValueError('Unreviewed exterior pine mesh')
        pos=vector(row.get('position_cm'),3,'position');q=vector(row.get('rotation_xyzw'),4,'rotation');s=vector(row.get('scale'),3,'scale')
        if abs(sum(v*v for v in q)-1)>1e-6 or abs(q[0])+abs(q[1])>1e-8 or max(s)-min(s)>1e-7 or not .5<=s[0]<=1.25:raise ValueError('Exterior pine must be upright with bounded uniform scale')
        ground=vector([row.get('ground_z_cm')],1,'ground')[0]
        if abs(pos[2]+ASSETS[mesh]['root_z_cm']*s[0]-ground)>.01:raise ValueError('Exterior pine root contact changed')
        lo,hi=transformed_bounds(row)
        if not(lo[0]>105000 or hi[0]<-105000 or lo[1]>105000 or hi[1]<-105000):raise ValueError('Full exterior pine bounds enter1050 square')
        if max(abs(v) for v in lo[:2]+hi[:2])>400000:raise ValueError('Exterior pine outside apron')
        counts[mesh]+=1;total+=ASSETS[mesh]['source_triangles']
    if counts[MATURE]>500 or counts[SAPLING]>100:raise ValueError('Exterior pine family budget exceeded')
    return doc,{'path':str(path),'sha256':digest(path),'instances':len(rows),'family_counts':counts,
                'instanced_source_triangles':total,'grouping_cell_cm':50000,'cull_cm':cull,
                'expected_material_slots':{mesh:data['slot_names'] for mesh,data in ASSETS.items()}}

def groups(path):
    doc,receipt=load(path);buckets={}
    for row in doc['instances']:
        pos=row['position_cm'];rot=matrix(row['rotation_xyzw']);s=row['scale']
        record=[*pos,0,s[0],0,0,*[rot[i][j]*s[j] for j in range(3) for i in range(3)]]
        key=(row['mesh'],math.floor(pos[0]/50000),math.floor(pos[1]/50000))
        buckets.setdefault(key,[]).append((row['id'],record))
    if len(buckets)>48:raise ValueError('Exterior pine component budget exceeds48')
    result=[]
    for key,rows in sorted(buckets.items()):
        rows.sort();result.append(([r for _,r in rows],{'mesh':key[0],'rule':'exterior pine woodland','bands':1,
            'cull':doc['cull_cm'],'shadow':True,'static':True,'exact':True},[ident for ident,_ in rows]))
    receipt.update(components=len(result),groups=[]);return result,receipt

def cook_inputs(path,work):
    """Fail closed on source, exact transform or saved-editor proof drift."""
    from foliage_bake import exact_transform
    path=Path(path).resolve();doc,proof=load(path);expected,grouped=groups(path)
    folder=Path(work)/'foliage_bake';spec_path=folder/'spec.json';readback_path=folder/'render-only-pines.verification.json'
    spec=json.loads(spec_path.read_text());declared=spec.get('render_only_pines',{})
    if (Path(declared.get('path','')).resolve()!=path or any(declared.get(k)!=proof[k] for k in ('sha256','instances','family_counts','expected_material_slots','grouping_cell_cm','cull_cm'))
            or declared.get('components')!=grouped['components'] or len(declared.get('groups',[]))!=len(expected)):
        raise ValueError('Exterior pine foliage spec does not match source')
    rb=json.loads(readback_path.read_text())
    if rb.get('schema')!='pwr-render-only-pines-editor-v1' or rb.get('source_sha256')!=proof['sha256'] or rb.get('no_native_collision_input') is not True:raise ValueError('Stale exterior pine editor proof')
    for key,limit in [('maximum_position_error_cm',.01),('maximum_quaternion_dot_error',1e-5),('maximum_scale_error',1e-5)]:
        value=rb.get(key)
        if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or not 0<=value<=limit:raise ValueError('Exterior pine transform error exceeds tolerance')
    rows=rb.get('groups',[]);actual={r['component']:r for r in rows}
    if len(actual)!=len(rows) or len(actual)!=len(expected):raise ValueError('Exterior pine component inventory changed')
    inputs={'render_only_pines':path,'render_only_pines_spec':spec_path,'render_only_pines_readback':readback_path}
    inputs.update({f'render_only_pines_source_{i}':(path.parent/r['path']).resolve() for i,r in enumerate(doc['sources'])})
    seen=set();ids=set()
    for i,((records,group,identifiers),entry) in enumerate(zip(expected,declared['groups'])):
        number=entry.get('group')
        if isinstance(number,bool) or not isinstance(number,int) or number in seen or not 1<=number<=len(spec['groups']) or entry.get('count')!=len(records) or entry.get('ids')!=identifiers:raise ValueError('Exterior pine group mapping changed')
        seen.add(number);ids.update(identifiers);baked=spec['groups'][number-1]
        if baked!={'mesh':group['mesh'],'bands':1,'cull':doc['cull_cm'],'flags':35}:raise ValueError('Exterior pine baked group policy changed')
        raw=bytearray()
        for record in records:
            q,s=exact_transform([record[7:10],record[10:13],record[13:16]])
            raw.extend(struct.pack('<10f',*record[:3],*q,*s))
        sidecar=Path(f"{spec['bin']}.xf{number}")
        if sidecar.read_bytes()!=raw:raise ValueError('Exterior pine exact transforms changed')
        inputs[f'render_only_pines_transform_{i}']=sidecar
        row=actual.pop(f'MJFol_{number}_1_0',{})
        if any(row.get(k)!=v for k,v in {'mesh':group['mesh'],'instances':len(records),'native_slot_names':ASSETS[group['mesh']]['slot_names'],
               'material_overrides':0,'collision':'NoCollision','navigation':False,'wpo':False,'cast_shadow':True,'cull_cm':doc['cull_cm']}.items()):raise ValueError('Exterior pine editor slots/settings changed')
    if ids.intersection(d['id'] for d in spec.get('decor',[])):raise ValueError('Exterior pine also scheduled as native decor')
    if ids.intersection(i for r in spec.get('pine_hism',{}).get('groups',[]) for i in r['ids']):raise ValueError('Exterior pine duplicated in gameplay population')
    return inputs
