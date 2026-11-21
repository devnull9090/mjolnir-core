"""Actual UE PCG yaw variation on reviewed irregular geological anchors.

Anchor XY, asset role and scale are authored. UE PCG owns the random yaw draw;
the adapter bounds it to +/-14 degrees of the terrain contour and grounds the
same final transform used for rendering and native hulls. Never installs.
"""
import argparse,copy,json,math,struct,sys
from pathlib import Path
import numpy as np
from scipy.spatial import cKDTree
from scipy.ndimage import distance_transform_edt
ROOT=Path(__file__).resolve().parents[4]
sys.path.insert(0,str(ROOT/'tools/level'))
import pcg_foliage,b30_collision
from heightfield import load_heightfield,sha256
OUT=ROOT/'out/pwr/visual-v5/outcrops-v2'
MASTER=ROOT/'levels/warfare/pwr/terrain/runtime-v5/runtime-master.json'


def dump(path,value):Path(path).write_text(json.dumps(value,indent=2)+'\n')


def prepare():
    field=load_heightfield(MASTER);proposal=pcg_foliage.load(OUT/'proposal.json');points=[]
    assert proposal['runtime_master_sha256']==field.manifest_sha256
    for index,row in enumerate(proposal['proposed_decor']):
        x,y=row['pos'][0]/100,-row['pos'][1]/100
        points.append({'id':index,'position':[x,y,float(field.sample(x,y))],'normal':[0,0,1],
                       'density':1.,'biome_mask':1,'kind':'reviewed_geological_anchor'})
    for pid,density,mask in ((10000,0.,1),(10001,1.,0)):
        points.append({'id':pid,'position':points[0]['position'],'normal':[0,0,1],
                       'density':density,'biome_mask':mask,'kind':'excluded_proof_fixture'})
    source=OUT/'anchors.candidates.json'
    dump(source,{'schema':1,'align_to_normal':False,'master_sha256':field.manifest_sha256,
                 'height_sha256':field.metadata['height']['sha256'],'proposal_sha256':sha256(OUT/'proposal.json'),'points':points})
    dump(OUT/'request.json',{'jobs':[{'input':str(source),'output':str(OUT/f'anchors{suffix}.pcg.json'),
         'graph':'/Game/MJOLNIR/PCGAuthoring/PWRVisualV5/PCG_reviewed_outcrops'+suffix,
         'seed':20590,'scale_min':1.,'scale_max':1.} for suffix in ('','_repeat')]})
    print('Prepared58 authored irregular anchors +2 exclusion fixtures; actualPCG owns bounded yaw variation')


def export():
    field=load_heightfield(MASTER);proposal=pcg_foliage.load(OUT/'proposal.json')
    source=pcg_foliage.load(OUT/'anchors.candidates.json')
    first,repeat=[pcg_foliage.load(OUT/f'anchors{s}.pcg.json') for s in ('','_repeat')]
    assert source['master_sha256']==field.manifest_sha256
    assert source['proposal_sha256']==sha256(OUT/'proposal.json')
    assert first['source_sha256']==repeat['source_sha256']==sha256(OUT/'anchors.candidates.json')
    assert first['points']==repeat['points'],'PCG repeat changed'
    pairs=pcg_foliage.validate_output(source,first)
    assert {a['id'] for a,b in pairs}==set(range(58)),'Missing anchor or exclusion failed'
    masks=field.masks
    forbidden=(masks['road']>.002)|(masks['water']>.002)|(masks['shore']>.02)|(masks['bases']>.002)
    clearance=distance_transform_edt(~forbidden,sampling=field.spacing_m[0])
    tree_path=ROOT/'out/pwr/pcg-v5/trees.selected.json'
    trees=cKDTree(np.array([x['position'][:2] for x in pcg_foliage.load(tree_path)['instances']]))
    final,checks=[],[]
    by_mesh={entry['mesh']:entry for entry in proposal['palette'].values()}
    for anchor,point in pairs:
        row=copy.deepcopy(proposal['proposed_decor'][anchor['id']]);entry=by_mesh[row['mesh']]
        assert point['scale_xyz']==[1.,1.,1.]
        x,y,z=anchor['position'];s=row['scale'][0]
        dx=(field.sample(x+3,y)-field.sample(x-3,y))/6;dy=(field.sample(x,y+3)-field.sample(x,y-3))/6
        draw=pcg_foliage.authored_yaw(point['rotation_xyzw'])/360
        heading=math.atan2(dy,dx)+math.pi/2+math.radians(draw*28-14)
        lo,hi=np.array(entry['bounds_m']);radius=math.hypot(max(abs(lo[0]),abs(hi[0])),max(abs(lo[1]),abs(hi[1])))*s
        c,t=math.cos(heading),math.sin(heading);rotation=np.array([[c,-t],[t,c]])
        xx,yy=np.meshgrid(np.linspace(lo[0],hi[0],7),np.linspace(lo[1],hi[1],7))
        rectangle=np.c_[xx.ravel(),-yy.ravel()]*s@rotation.T+[x,y]
        support=field.sample(rectangle[:,0],rectangle[:,1]);height=(hi[2]-lo[2])*s
        row['rot']=[0,-math.degrees(heading),0]
        row['pos'][2]=float(np.quantile(support,.25)-lo[2]*s-entry['bury_height_fraction']*height)*100
        ix,iy=np.round((np.array([x,y])-field.origin_m)/field.spacing_m).astype(int)
        route=float(clearance[iy,ix]-math.sqrt(2)*field.spacing_m[0]-radius)
        near=float(trees.query([x,y])[0]-radius)
        assert route>12 and near>8 and max(abs(x),abs(y))+radius<950
        final.append(row);checks.append({'id':row['id'],'pcg_id':anchor['id'],'pcg_yaw_unit_draw':draw,
             'contour_yaw_perturbation_degrees':draw*28-14,'maximum_yaw_independent_footprint_m':radius,
             'route_water_base_clearance_m':route,'tree_root_clearance_m':near,'transform':row})
    provenance={'frozen_runtime_master_sha256':field.manifest_sha256,'master_height_sha256':field.metadata['height']['sha256'],
         'proposal_sha256':sha256(OUT/'proposal.json'),'pcg_request_receipt_sha256':sha256(OUT/'request.receipt.json'),
         'pcg_output_sha256':sha256(OUT/'anchors.pcg.json'),'pcg_repeat_sha256':sha256(OUT/'anchors_repeat.pcg.json'),
         'trees_sha256':sha256(tree_path),'generation':'Authored irregular anchors + actual UE PCG yaw bounded to terrain contour',
         'xy_role_scale_authored':True,'yaw_draw_from_actual_pcg':True,'excluded_fixtures':2,'identical_repeat':True}
    dump(OUT/'outcrops.authored-decor.json',{'schema_version':1,'coordinates':'unreal_centimetres','decor':final,'visual_v4_provenance':provenance})
    fixed_paths=[ROOT/'out/pwr/visual-v5/temperate-rocks.authored-decor.json',ROOT/'out/pwr/visual-v5/shore/shore.authored-decor.json']
    fixed=[x for path in fixed_paths for x in pcg_foliage.load(path)['decor']]
    assert len(fixed)==516 and len(final)==58
    provenance['unchanged_sources']=[{'path':str(path),'sha256':sha256(path)} for path in fixed_paths]
    dump(OUT/'rocks-and-outcrops.authored-decor.json',{'schema_version':1,'coordinates':'unreal_centimetres','decor':fixed+final,'visual_v4_provenance':provenance})
    assert pcg_foliage.load(OUT/'rocks-and-outcrops.authored-decor.json')['decor'][:516]==fixed
    dump(OUT/'final-footprints.receipt.json',{'runtime_master_sha256':field.manifest_sha256,'count':58,
         'minimum_route_clearance_m':min(x['route_water_base_clearance_m'] for x in checks),
         'minimum_tree_clearance_m':min(x['tree_root_clearance_m'] for x in checks),'checks':checks,
         'existing298_boulders218_shore2291_trees_unchanged':True,'provenance':provenance})
    print('Exported58 final actual-PCG-oriented outcrops +516 unchanged rocks; allfootprints passed')


def grass():
    merged=OUT/'rocks-and-outcrops.authored-decor.json';decor=pcg_foliage.load(merged)['decor']
    source=ROOT/'out/pwr/pcg-v5/grass/foliage.json';spec,groups=pcg_foliage.read_mjf_groups(source)
    out=OUT/'grass';out.mkdir(exist_ok=True);kept=[];reports=[];hull_hashes={}
    for index,(group,payload,sidecars,n) in enumerate(groups,1):
        assert 'xf' in sidecars
        transforms=np.frombuffer(sidecars['xf'],dtype='<f4').reshape(n,10);xyz=transforms[:,:3].astype(float);keep=np.ones(n,dtype=bool)
        for item in decor:
            leaf=item['mesh'].split('.')[-1]
            path=next((folder/(leaf+'.json') for folder in (OUT/'hulls',ROOT/'out/pwr/pcg-v3/rocks/hulls') if (folder/(leaf+'.json')).is_file()),None)
            if path is None:raise FileNotFoundError(leaf)
            hull_hashes[str(path)]=sha256(path);hull=pcg_foliage.load(path)
            world=np.array(hull['points'])*np.array(item['scale'])@b30_collision.rotator_matrix(*item.get('rot',[0,0,0]))+item['pos']
            ids=np.flatnonzero(keep&np.all(xyz>=world.min(0)-65,axis=1)&np.all(xyz<=world.max(0)+65,axis=1))
            if not len(ids):continue
            face=np.asarray(hull['faces']);a,b,c=(world[face[:,i]] for i in range(3));normal=np.cross(b-a,c-a);length=np.linalg.norm(normal,axis=1)
            valid=length>1e-8;normal=normal[valid]/length[valid,None];a=a[valid]
            inside=np.all((xyz[ids]+[0,0,15])@normal.T-np.sum(a*normal,axis=1)<=65,axis=1)
            keep[ids[inside]]=False
        count=int(keep.sum());records=np.frombuffer(payload[4:],dtype=np.dtype((np.void,19)))
        data=struct.pack('<I',count)+records[keep].tobytes()
        filtered={suffix:np.frombuffer(value,dtype=np.dtype((np.void,40 if suffix=='xf' else 16)))[keep].tobytes() for suffix,value in sidecars.items()}
        kept.append((group,data,filtered,count));reports.append({'group':index,'input':n,'retained':count,'removed':n-count})
    binary=out/'foliage.bin';binary.write_bytes(b'MJF3'+struct.pack('<II',3,len(kept))+b''.join(row[1] for row in kept))
    for i,(_,_,sidecars,_) in enumerate(kept,1):
        for suffix,data in sidecars.items():Path(str(binary)+'.'+suffix+str(i)).write_bytes(data)
    dump(out/'foliage.json',{'file':'foliage.bin','groups':[row[0] for row in kept]});pcg_foliage.read_mjf_groups(out/'foliage.json')
    receipt={'runtime_master_sha256':load_heightfield(MASTER).manifest_sha256,'source_spec_sha256':sha256(source),
         'source_binary_sha256':sha256(source.parent/spec['file']),'source_decor_sha256':sha256(merged),'hull_hashes':hull_hashes,
         'deterministic_exclusion':'native hulls expanded65cm,grasssample15cm above root','retained_transforms_byte_exact':True,
         'groups':reports,'input':sum(row['input'] for row in reports),'retained':sum(row['retained'] for row in reports),
         'removed':sum(row['removed'] for row in reports),'existing_tree_source_unchanged':True}
    dump(out/'exclusion.receipt.json',receipt);print(json.dumps({k:receipt[k] for k in ('input','retained','removed')}))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('command',choices=['prepare','export','grass']);a=p.parse_args();globals()[a.command]()
