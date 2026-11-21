"""Read cooked/cloned/final-world exterior HISM and existing pine ownership.

The native reader reuses ue_asset::level::instance_matrices. Exact editor
sidecar transforms are checked against serialized affine matrices, not merely
component counts. No package, staging input or installed object is modified.
"""
from pathlib import Path
import argparse
import hashlib
import json
import math
import re
import struct
import subprocess
import numpy as np
import render_only_hism as h
from verify_landscape_lod_cook import verify_rows

ROOT=Path(__file__).resolve().parents[2]


def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def number(value,default=0.):
    return float(str(default if value is None else value).split()[0])


def package(row,key):return row.get('references',{}).get(key,{}).get('package')


def matrices(path):
    result=[]
    for record in struct.iter_unpack('<10f',Path(path).read_bytes()):
        q=np.array(record[3:7],dtype=float);q/=np.linalg.norm(q)
        m=np.eye(4);m[:3,:3]=(np.array(h.matrix(q))*np.array(record[7:10])).T;m[3,:3]=record[:3]
        result.append(m)
    return np.array(result)


def identity_ancestors(row,by_export):
    visited=set()
    while row:
        if row['export'] in visited:raise ValueError('Component attachment cycle')
        visited.add(row['export']);props=row.get('properties',{})
        for key,default in [('RelativeLocation',[0,0,0]),('RelativeRotation',[0,0,0]),('RelativeScale3D',[1,1,1])]:
            value=props.get(key)
            decoded = [0,0,0] if value == '0 (zeroed)' else ([float(v) for v in value.split(',')] if value is not None else default)
            if decoded!=default:
                raise ValueError('Nonidentity exterior component/parent transform requires explicit composition: '+key)
        parent=props.get('AttachParent','null')
        if parent=='null':break
        match=re.fullmatch(r'export (\d+)',parent)
        if not match or int(match[1]) not in by_export:raise ValueError('Unresolved component attachment')
        row=by_export[int(match[1])]


def compare_matrices(actual,expected):
    actual=np.asarray(actual,dtype=float)
    if actual.shape!=expected.shape or not np.all(np.isfinite(actual)):raise ValueError('Native HISM affine inventory changed')
    remaining=set(range(len(actual)));position=basis=0.
    for target in expected:
        best=min(remaining,key=lambda i:np.linalg.norm(actual[i,3,:3]-target[3,:3]));remaining.remove(best)
        position=max(position,float(np.max(abs(actual[best,3,:3]-target[3,:3]))))
        basis=max(basis,float(np.max(abs(actual[best,:3,:3]-target[:3,:3]))))
        if not np.allclose(actual[best,:,3],[0,0,0,1],rtol=0,atol=1e-12):raise ValueError('Non-affine native matrix')
    if position>.01 or basis>1e-5:raise ValueError(f'Serialized exterior transform drift: position{position}cm/basis{basis}')
    return position,basis


def verify_components(data,spec,doc,policy=None,pine_doc=None):
    rows=data['exports'];by_export={r['export']:r for r in rows}
    wanted={f"MJFol_{r['group']}_1_0":r for r in spec['render_only_hism']['groups']}
    exterior_meshes={r['mesh'].split('.')[0] for r in doc['instances']}
    material_package='/Game/MJOLNIR/Landscape/LPW/MI_PWR_ExteriorCliffs_'+spec['render_only_hism']['sha256'][:12]
    seen=set();instances=0;position=basis=0.;reported=[]
    # A stock asset can also be used by pre-existing scenery. Accept only the
    # separately authored static actor with the exact ID and direct transform;
    # shared mesh identity alone does not make it a duplicate exterior owner.
    scenery={"MJDecor_"+r['id']:r for r in spec.get('decor',[])
             if r['mesh'].split('.')[0] in exterior_meshes}
    scenery_seen=set()
    # Only the explicitly selected exterior group names qualify. A second
    # component using that MIC is rejected rather than ignored.
    for row in rows:
        if row['class'] not in ('HierarchicalInstancedStaticMeshComponent','InstancedStaticMeshComponent','StaticMeshComponent'):continue
        name=row['name'];mesh=package(row,'StaticMesh');mat=package(row,'OverrideMaterials[0]')
        if name not in wanted:
            if mat==material_package:raise ValueError('Duplicate exterior material owner/component')
            if mesh in exterior_meshes:
                outer=row.get('outer');entry=scenery.get(outer);props=row['properties']
                if not entry or outer in scenery_seen or row['class']!='StaticMeshComponent' or mesh!=entry['mesh'].split('.')[0]:
                    raise ValueError('Duplicate/unregistered exterior mesh owner/component')
                if props.get('AttachParent','null')!='null':raise ValueError('Pre-existing scenery has an unexpected parent')
                for key,source,default in [('RelativeLocation','loc',[0,0,0]),('RelativeRotation','rot',[0,0,0]),('RelativeScale3D','scale',[1,1,1])]:
                    raw=props.get(key);actual=np.array([0,0,0] if raw=='0 (zeroed)' else ([float(v) for v in raw.split(',')] if raw is not None else default))
                    delta=actual-np.asarray(entry[source])
                    if key=='RelativeRotation':delta=(delta+180)%360-180
                    if not np.all(np.isfinite(delta)) or np.max(abs(delta))>1e-6:raise ValueError('Pre-existing shared-mesh scenery transform changed: '+outer)
                scenery_seen.add(outer)
            continue
        if name in seen:raise ValueError('Duplicate exterior HISM name')
        seen.add(name);entry=wanted[name];group=spec['groups'][entry['group']-1];props=row['properties']
        if row['class']!='HierarchicalInstancedStaticMeshComponent' or mesh!=group['mesh'].split('.')[0]:raise ValueError('Cooked exterior class/native mesh changed')
        if mat!=material_package:raise ValueError('Cooked exterior material binding changed')
        for key in ('bEvaluateWorldPositionOffset','bCanEverAffectNavigation'):
            if props.get(key,'true').split()[0]!='false':raise ValueError('Cooked exterior WPO/navigation enabled or missing: '+key)
        if number(props.get('BodyInstance.CollisionEnabled'),3)!=0 or props.get('BodyInstance.CollisionProfileName')!='NoCollision':
            raise ValueError('Cooked exterior collision is not explicitly disabled')
        if [int(number(props.get(k))) for k in ('InstanceStartCullDistance','InstanceEndCullDistance')]!=doc['cull_cm']:
            raise ValueError('Cooked exterior cull changed')
        expected=matrices(f"{spec['bin']}.xf{entry['group']}")
        if len(expected)!=entry['count'] or int(number(props.get('NumBuiltInstances')))!=len(expected):raise ValueError('Cooked exterior instance count changed')
        identity_ancestors(row,by_export)
        p,b=compare_matrices(row.get('matrices'),expected);position=max(position,p);basis=max(basis,b);instances+=len(expected)
        reported.append({'name':name,'mesh':mesh,'material':mat,'instances':len(expected),'collision':False,'navigation':False,'wpo':False})
    if seen!=set(wanted) or instances!=spec['render_only_hism']['instances']:raise ValueError('Missing cooked exterior components')
    if scenery_seen!=set(scenery):raise ValueError('Missing pre-existing shared-mesh scenery')
    exterior_pine=spec.get('render_only_pines',{});extra_seen=set();extra_count=0;extra_position=extra_basis=0.
    extra_wanted={f"MJFol_{r['group']}_1_0":r for r in exterior_pine.get('groups',[])}
    if bool(exterior_pine)!=bool(pine_doc):raise ValueError('Exterior pine manifest must accompany its cooked population')
    for row in rows:
        if row['name'] not in extra_wanted:continue
        name=row['name'];entry=extra_wanted[name];group=spec['groups'][entry['group']-1];props=row['properties']
        if name in extra_seen or row['class']!='HierarchicalInstancedStaticMeshComponent' or package(row,'StaticMesh')!=group['mesh'].split('.')[0]:raise ValueError('Duplicate/changed exterior pine owner')
        if any(k.startswith('OverrideMaterials[') for k in props):raise ValueError('Exterior pine native material overridden')
        for key in ('bEvaluateWorldPositionOffset','bCanEverAffectNavigation'):
            if props.get(key,'true').split()[0]!='false':raise ValueError('Exterior pine WPO/navigation enabled')
        if number(props.get('BodyInstance.CollisionEnabled'),3)!=0 or props.get('BodyInstance.CollisionProfileName')!='NoCollision':raise ValueError('Exterior pine collision enabled')
        if [int(number(props.get(k))) for k in ('InstanceStartCullDistance','InstanceEndCullDistance')]!=pine_doc['cull_cm']:raise ValueError('Exterior pine cull changed')
        expected=matrices(f"{spec['bin']}.xf{entry['group']}")
        if len(expected)!=entry['count'] or int(number(props.get('NumBuiltInstances')))!=len(expected):raise ValueError('Exterior pine count changed')
        identity_ancestors(row,by_export);p,b=compare_matrices(row.get('matrices'),expected)
        extra_position=max(extra_position,p);extra_basis=max(extra_basis,b);extra_seen.add(name);extra_count+=len(expected)
    if extra_seen!=set(extra_wanted) or extra_count!=exterior_pine.get('instances',0):raise ValueError('Missing exterior pine population')
    pine=spec.get('pine_hism',{});pine_wanted={f"MJFol_{r['group']}_1_0":r for r in pine.get('groups',[])}
    pine_meshes={spec['groups'][r['group']-1]['mesh'].split('.')[0] for r in pine.get('groups',[])}
    pine_seen=set();pine_count=0
    for row in rows:
        if package(row,'StaticMesh') not in pine_meshes:continue
        if row['name'] in extra_seen:continue
        name=row['name']
        if row['class']!='HierarchicalInstancedStaticMeshComponent' or name not in pine_wanted or name in pine_seen:
            raise ValueError('Duplicate/non-HISM pine owner in cooked world')
        pine_seen.add(name);entry=pine_wanted[name]
        if package(row,'StaticMesh')!=spec['groups'][entry['group']-1]['mesh'].split('.')[0] or int(number(row['properties'].get('NumBuiltInstances')))!=entry['count']:
            raise ValueError('Cooked pine mesh/count changed')
        pine_count+=entry['count']
    if pine_seen!=set(pine_wanted) or pine_count!=pine.get('instances',0):raise ValueError('Incomplete cooked pine ownership')
    result={'exterior_components':len(seen),'exterior_instances':instances,'maximum_position_error_cm':position,
        'maximum_basis_error':basis,'components':reported,'pine_components':len(pine_seen),'pine_instances':pine_count,
        'duplicate_pine_actor_owners':0,'preserved_shared_mesh_scenery':len(scenery_seen),'material_package':material_package}
    if exterior_pine:
        result.update(exterior_pine_components=len(extra_seen),exterior_pine_instances=extra_count,
            duplicate_exterior_pine_owners=0,exterior_pine_material_overrides=0,exterior_pine_collision_free=True,
            exterior_pine_full_bounds_outside_1050m=True,exterior_pine_maximum_position_error_cm=extra_position,
            exterior_pine_maximum_basis_error=extra_basis,exterior_pine_expected_native_slots=exterior_pine['expected_material_slots'])
    if policy:
        lod=[{k:int(number(r['properties'].get(k),-1 if k=='ForcedLOD' else 0)) for k in ('SectionBaseX','SectionBaseY','ForcedLOD')}
             for r in rows if r['class']=='LandscapeComponent']
        result['landscape_lod']=verify_rows(lod,policy)
    return result


def verify_material(data,binding):
    rows=[r for r in data['exports'] if r['class']=='MaterialInstanceConstant']
    if len(rows)!=1:raise ValueError('Expected exactly one exterior MIC')
    row=rows[0];props=row['properties']
    if package(row,'Parent')!=binding['parent'].split('.')[0]:raise ValueError('Exterior MIC parent changed')
    textures={};vectors={}
    for key,value in props.items():
        match=re.fullmatch(r'(Texture|Vector)ParameterValues\[(\d+)\]\.ParameterInfo.Name',key)
        if not match:continue
        prefix=key.rsplit('.ParameterInfo.Name',1)[0]
        # UE EMaterialParameterAssociation: Layer=0, Blend=1, Global=2.
        if number(props.get(prefix+'.ParameterInfo.Association'),2)!=2:raise ValueError('Unexpected exterior layered parameter')
        if match[1]=='Texture':textures[value]=package(row,prefix+'.ParameterValue')
        else:vectors[value]=[float(x) for x in props[prefix+'.ParameterValue'].split(',')]
    if textures!={k:v.split('.')[0] for k,v in binding['textures'].items()}:raise ValueError('Exterior MIC native textures changed')
    if set(vectors)!=set(binding['vectors']):raise ValueError('Exterior MIC vector inventory changed')
    for key,wanted in binding['vectors'].items():
        if not np.allclose(vectors[key],wanted,rtol=0,atol=1e-5):raise ValueError('Exterior MIC vector changed: '+key)
    return {'parent':package(row,'Parent'),'textures':textures,'vectors':vectors}


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--manifest',type=Path,required=True)
    p.add_argument('--foliage-spec',type=Path,required=True);p.add_argument('--world',type=Path,required=True)
    p.add_argument('--expected-world-package',required=True,help='Exact serialized package identity; e.g. /Game/Levels/Halo1/Solo/PWR/PWR')
    p.add_argument('--material-package',type=Path,required=True);p.add_argument('--schema',choices=['stock','game'],required=True)
    p.add_argument('--pines-manifest',type=Path,help='Required for a source world with the separate exterior pine population')
    p.add_argument('--global-paks',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    p.add_argument('--policy',type=Path);p.add_argument('--reader',type=Path,default=ROOT/'target/release/examples/hism_readback.exe')
    a=p.parse_args();doc,proof=h.load(a.manifest);spec=json.loads(a.foliage_spec.read_text())
    if spec.get('render_only_hism',{}).get('sha256')!=proof['sha256']:raise ValueError('Bake spec/manifest changed')
    pine_doc=None;pine_inputs={}
    if a.pines_manifest:
        from render_only_pines import load as load_pines,cook_inputs as pine_cook_inputs
        pine_doc,_=load_pines(a.pines_manifest)
        pine_inputs=pine_cook_inputs(a.pines_manifest,a.foliage_spec.parent.parent)
    elif spec.get('render_only_pines'):raise ValueError('--pines-manifest is required for this world')
    names=','.join(f"MJFol_{r['group']}_1_0" for r in spec['render_only_hism']['groups']+spec.get('render_only_pines',{}).get('groups',[]))
    schema=ROOT/'defs/ue'/('UE-5.5-stock.usmap' if a.schema=='stock' else 'Meteorite-2607-CU3.usmap')
    a.out.mkdir(parents=True,exist_ok=True);decoded=[]
    for kind,path,selected in [('world',a.world,names),('material',a.material_package,'')]:
        proc=subprocess.run([str(a.reader),str(a.global_paks),str(schema),str(path),selected],capture_output=True,text=True,check=True)
        data=json.loads(proc.stdout);(a.out/(kind+'.json')).write_text(json.dumps(data,separators=(',',':'))+'\n');decoded.append(data)
    policy=json.loads(a.policy.read_text()) if a.policy else None
    if decoded[0]['package']!=a.expected_world_package:raise ValueError('Wrong serialized world package')
    report=verify_components(decoded[0],spec,doc,policy,pine_doc);report['material']=verify_material(decoded[1],doc['material'])
    if decoded[1]['package']!=report['material_package']:raise ValueError('Wrong serialized exterior MIC package')
    inputs=[a.manifest,a.foliage_spec,a.world,a.material_package,schema,a.reader,Path(__file__)]
    inputs.extend(Path(f"{spec['bin']}.xf{r['group']}") for r in spec['render_only_hism']['groups'])
    inputs.extend(pine_inputs.values())
    if a.policy:inputs.append(a.policy)
    report.update(schema='pwr-cooked-exterior-hism-v1',encoding=a.schema,world_package=decoded[0]['package'],
        inputs={str(path.resolve()):digest(path) for path in inputs},
        runtime_acceptance='Cooked/retargeted readback only; live visibility/FPS requires game review')
    (a.out/'receipt.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:report[k] for k in ('exterior_components','exterior_instances','pine_components','pine_instances','maximum_position_error_cm','maximum_basis_error')}))


if __name__=='__main__':main()
