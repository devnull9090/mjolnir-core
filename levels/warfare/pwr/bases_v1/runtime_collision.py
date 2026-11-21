"""Prepare native base collision without changing the frozen terrain or gameplay.

The Blender export is in authoring metres. Native extra triangles are in CE
world units. Each structural mesh remains separate; no convex hull closes a
whole base. Existing terrain and bridge source triangles are copied exactly.
"""
from __future__ import annotations
import argparse, collections, hashlib, json, math, shutil, struct, sys
from pathlib import Path
import numpy as np

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
OUT=ROOT/'out/pwr/base-runtime'
HANDOFF=ROOT/'out/pwr/base-integration/runtime-handoff.json'
PLAN=ROOT/'out/pwr/base-integration/placement-plan.json'
OLD=Path('C:/haloce/ce_conversions/warfare/PWR/expansion/world-v5-visual8')
WORLD=OLD.parent/'world-bases-v1'
SCHEMA='pwr-base-architecture-contract-v1'
TERRAIN=135836
BRIDGES=1808
REMOVED=6528
MAX_SURFACES=1200000

def require(value,message):
    if not value:raise ValueError(message)

def sha(path):
    with Path(path).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()

def read(path):return json.loads(Path(path).read_text(encoding='utf-8-sig'))
def json_scalar(value):
    if isinstance(value,np.generic):return value.item()
    raise TypeError('Not JSON serializable: '+repr(type(value)))
def write(path,value):Path(path).write_text(json.dumps(value,indent=2,default=json_scalar)+'\n',encoding='utf-8')
def triangle_hash(points):return hashlib.sha256(np.asarray(points,dtype='<f8').tobytes()).hexdigest()
def canonical(value):return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()

def canonical_name(name):
    for prefix in ('02_BLUE/','03_GREEN/'):
        if name.startswith(prefix):return name[len(prefix):]
    return name

def omission_reason(row):
    name=canonical_name(row['name']).lower();role=row.get('module_role','')
    if role=='stock' or row.get('stock_source_file'):return 'Native visual lining; explicit compact proxy supplied separately'
    if role=='detail':return 'Small visual-only panel joints, guides and light fixtures'
    if 'glyph' in name or 'engraving' in name or 'machining' in name:
        return 'Sub-centimetre engraved/embossed decoration; structural backing retained'
    if role=='facade' and ('/trim/' in name or '/energy/' in name or 'stepped joints' in name):
        return 'Facade trim/energy overlay; structural door surrounds retained'
    if role=='ramp' and any(n in name for n in ('segmented traction plate','detailed trim','shoulder recessed armor field')):
        return 'Ramp tread/trim overlay; continuous driveable ramp and curbs retained'
    if role in ('fin','citadel') and any(n in name for n in ('inset','recess','energy','contour borders','shadow reveals','channel housing','team incisions')):
        return 'Fine inset decoration; solid fin/pier/gateway core retained'
    if role=='gallery' and any(n in name for n in ('stepped engraving','light well','bulkhead light')):
        return 'Gallery lighting decoration; complete wall/cover collision retained'
    if role=='mount' and 'team marker' in name:return 'Emissive socket overlay'
    if role=='flank' and 'deep field' in name:return 'Thin recessed exterior panel overlay'
    return None

def normalize_mesh(row):
    """Retain exact raw faces, correcting only inward closed-component winding."""
    vertices=np.asarray(row['vertices_m'],dtype=float);faces=np.asarray(row['triangles'],dtype=np.int64).copy()
    require(vertices.ndim==2 and vertices.shape[1]==3 and np.isfinite(vertices).all(),'Invalid vertices: '+row['name'])
    require(faces.ndim==2 and faces.shape[1]==3 and len(faces)>0 and np.all((faces>=0)&(faces<len(vertices))),'Invalid triangles: '+row['name'])
    original_vertices=len(vertices)
    vertices,inverse=np.unique(vertices,axis=0,return_inverse=True);faces=inverse[faces]
    cross=np.cross(vertices[faces[:,1]]-vertices[faces[:,0]],vertices[faces[:,2]]-vertices[faces[:,0]])
    valid=np.linalg.norm(cross,axis=1)>1e-10
    degenerate=int((~valid).sum());faces=faces[valid]
    require(len(faces)>0,'Empty structural triangle mesh: '+row['name'])
    edges={};adj=[set() for _ in faces]
    for i,f in enumerate(faces):
        for a,b in zip(f,np.roll(f,-1)):edges.setdefault(tuple(sorted((int(a),int(b)))),[]).append((i,int(a),int(b)))
    require(all(len(v)==2 for v in edges.values()),'Structural mesh is not closed: '+row['name'])
    for pair in edges.values():
        (i,a,b),(j,c,d)=pair
        require(a==d and b==c,'Inconsistent structural triangle winding: '+row['name'])
        adj[i].add(j);adj[j].add(i)
    remaining=set(range(len(faces)));repairs=0;components=0
    while remaining:
        start=remaining.pop();component=[start];queue=[start]
        while queue:
            for nxt in adj[queue.pop()]:
                if nxt in remaining:remaining.remove(nxt);component.append(nxt);queue.append(nxt)
        indices=np.asarray(component);points=vertices[faces[indices]]
        origin=points.reshape(-1,3).mean(axis=0);p=points-origin
        volume=np.einsum('ij,ij->i',p[:,0],np.cross(p[:,1],p[:,2])).sum()/6
        require(abs(volume)>1e-9,'Zero-volume structural component: '+row['name'])
        if volume<0:faces[indices]=faces[indices][:,[0,2,1]];repairs+=1
        components+=1
    return vertices[faces],{'closed_components':components,'inward_components_repaired':repairs,
                           'duplicate_vertices_welded':original_vertices-len(vertices),'zero_area_triangles_removed':degenerate}

def box_triangles(lo,hi):
    v=np.array([(x,y,z) for z in (lo[2],hi[2]) for y in (lo[1],hi[1]) for x in (lo[0],hi[0])],dtype=float)
    f=np.array([[0,3,1],[0,2,3],[4,5,7],[4,7,6],[0,1,5],[0,5,4],
                [2,6,7],[2,7,3],[0,4,6],[0,6,2],[1,3,7],[1,7,5]])
    return v,f

def native_proxy(row):
    """One measured bounded solid per decorative panel/pillar, never a base hull."""
    lo=np.array(row['bounds_m']['min']);hi=np.array(row['bounds_m']['max'])
    v,f=box_triangles(lo,hi)
    return {'name':'native-proxy/'+row['name'],'team':row['team'],'module_role':'native_lining_proxy',
            'vertices_m':v.tolist(),'triangles':f.tolist(),'proxy_source':row['stock_source_file'],
            'proxy_policy':'Measured per-module world AABB; audited against vehicle clearances. No whole-base hull.'}

def field_without_engraved_grooves(row):
    """Reconstruct the nine-vertex concave field before its tiny Boolean cuts.

    The exact authoring contour is retained, including its side-door opening.
    Every reconstructed boundary point must still occur in the exported source.
    This is deliberately limited to the named six facade overlays.
    """
    name=canonical_name(row['name'])
    require(name in ('facade/flanks/L continuous recessed field','facade/flanks/R continuous recessed field'),'Unreviewed facade repair')
    sign=-1 if '/L ' in name else 1
    contour=np.array([(20.75,2.2),(27.4,2.2),(27.8,3.4),(29.5,6.5),(36.5,6.5),
                      (37.5,4.5),(41.,4.5),(40.,10.2),(16.9,10.2)],dtype=float)
    contour[:,0]*=sign
    # Ear clipping in the original X/Z profile, before the affine art shaping.
    area=sum(a[0]*b[1]-a[1]*b[0] for a,b in zip(contour,np.roll(contour,-1,axis=0)))
    indices=list(range(len(contour))) if area>0 else list(reversed(range(len(contour))))
    triangles=[]
    def cross2(a,b):return a[0]*b[1]-a[1]*b[0]
    while len(indices)>3:
        removed=False
        for k,j in enumerate(indices):
            i,h=indices[k-1],indices[(k+1)%len(indices)]
            a,b,c=contour[[i,j,h]]
            if cross2(b-a,c-b)<=1e-10:continue
            inside=False
            for q in indices:
                if q in (i,j,h):continue
                p=contour[q]
                if all(cross2(v-u,p-u)>=-1e-10 for u,v in ((a,b),(b,c),(c,a))):inside=True;break
            if inside:continue
            triangles.append((i,j,h));indices.pop(k);removed=True;break
        require(removed,'Concave field triangulation failed')
    triangles.append(tuple(indices));n=len(contour)
    local=[]
    for y in (-26.24,-25.72):
        for x,z in contour:
            local.append([x,y-max(0,11.2-z)*.35,.2+(z-.2)*1.45,1.])
    world=(np.asarray(row['world_matrix'])@np.asarray(local).T).T[:,:3]
    original=np.asarray(row['vertices_m'])
    error=max(np.linalg.norm(original-point,axis=1).min() for point in world)
    require(error<1e-4,'Facade reconstruction boundary differs from reviewed source')
    faces=[tuple(reversed(t)) for t in triangles]+[tuple(i+n for i in t) for t in triangles]
    boundary=list(range(n)) if area>0 else list(reversed(range(n)))
    for i,j in zip(boundary,boundary[1:]+boundary[:1]):
        faces.extend([(i,j,j+n),(i,j+n,i+n)])
    # Normalize orientation from the prism's geometry rather than applying a
    # second blind reflection to the already mirrored source.
    result={**row,'vertices_m':world.tolist(),'triangles':faces}
    return result,{'policy':'Exact concave facade outline; Boolean engraving omitted from collision',
                   'maximum_source_boundary_error_m':float(error),'door_outline_retained':True}

def triangles_intersect_box(points,lo,hi):
    """Exact separating-axis test for triangle/AABB intersections."""
    p=np.asarray(points,dtype=float);lo=np.asarray(lo);hi=np.asarray(hi)
    selected=np.all(p.max(axis=1)>=lo-1e-8,axis=1)&np.all(p.min(axis=1)<=hi+1e-8,axis=1)
    indices=np.flatnonzero(selected);p=p[selected]
    if not len(p):return indices
    center=(lo+hi)/2;half=(hi-lo)/2;p=p-center
    edge=np.roll(p,-1,axis=1)-p
    axes=[np.broadcast_to(a,(len(p),3)) for a in np.eye(3)]
    axes+=[np.cross(edge[:,0],edge[:,1])]
    axes += [np.cross(edge[:,j],a) for j in range(3) for a in np.eye(3)]
    hit=np.ones(len(p),dtype=bool)
    for axis in axes:
        projection=np.einsum('nij,nj->ni',p,axis)
        radius=np.abs(axis)@half
        hit &= (projection.min(axis=1)<=radius+1e-8)&(projection.max(axis=1)>=-radius-1e-8)
    return indices[hit]

def floor_height(points,x,y,ceiling,depth=2.):
    p=np.asarray(points);x,y=float(x),float(y)
    match=(p[:,:,0].min(axis=1)<=x+1e-6)&(p[:,:,0].max(axis=1)>=x-1e-6)&(p[:,:,1].min(axis=1)<=y+1e-6)&(p[:,:,1].max(axis=1)>=y-1e-6)
    t=p[match]
    if not len(t):return None
    a=t[:,0];u=t[:,1]-a;v=t[:,2]-a;dx=x-a[:,0];dy=y-a[:,1]
    det=u[:,0]*v[:,1]-u[:,1]*v[:,0];ok=np.abs(det)>1e-12
    uu=np.divide(dx*v[:,1]-dy*v[:,0],det,out=np.zeros(len(t)),where=ok)
    vv=np.divide(u[:,0]*dy-u[:,1]*dx,det,out=np.zeros(len(t)),where=ok)
    z=a[:,2]+uu*u[:,2]+vv*v[:,2]
    hit=ok&(uu>=-1e-6)&(vv>=-1e-6)&(uu+vv<=1+1e-6)&(z<=ceiling+1e-6)&(z>=ceiling-depth-1e-6)
    return float(z[hit].max()) if hit.any() else None

def contains_point(points,point):
    """Parity supplement catches a whole solid enclosing a protected box."""
    p=np.asarray(points);origin=np.asarray(point);direction=np.array([.371,.529,.763]);direction/=np.linalg.norm(direction)
    e1=p[:,1]-p[:,0];e2=p[:,2]-p[:,0];h=np.cross(direction,e2);a=np.einsum('ij,ij->i',e1,h)
    ok=np.abs(a)>1e-12;f=np.divide(1.,a,out=np.zeros(len(a)),where=ok);s=origin-p[:,0]
    u=f*np.einsum('ij,ij->i',s,h);q=np.cross(s,e1);v=f*(q@direction);t=f*np.einsum('ij,ij->i',e2,q)
    hit=t[ok&(u>=-1e-8)&(v>=-1e-8)&(u+v<=1+1e-8)&(t>1e-7)]
    return len(np.unique(np.round(hit,6)))%2==1

def audit_architecture(records,plan):
    bases={};failures=[];probes=[]
    for site in plan['bases']:
        team=site['id'];origin=np.asarray(site['normalize_then_translate_m'])
        own=[r for r in records if r['team']==team]
        points=np.concatenate([r['points_m'] for r in own])-origin
        ownership=np.concatenate([[r['name']]*len(r['points_m']) for r in own])
        routes={}
        for name,x,y0,y1 in [('main',0,-65,57),('gallery_left',-21.45,-50,-6.5),('gallery_right',21.45,-50,-6.5),('bypass_left',-50,-60,57),('bypass_right',50,-60,57)]:
            lo=np.array([x-1.75,y0-3.5,.28]);hi=np.array([x+1.75,y1+3.5,4.7])
            crossing=triangles_intersect_box(points,lo,hi)
            enclosing=[]
            for r in own:
                local=r['points_m']-origin
                if np.all(local.min(axis=(0,1))<lo) and np.all(local.max(axis=(0,1))>hi) and contains_point(local,(lo+hi)/2):enclosing.append(r['name'])
            bad=[];count=0
            for lane in (x-1.4,x,x+1.4):
                for y in np.arange(y0,y1+.001,.5):
                    z=floor_height(points,lane,y,1.0)
                    count+=1
                    if z is None or abs(z-.2)>.085:bad.append({'xy':[lane,float(y)],'floor':z})
            routes[name]={'passed':not len(crossing) and not bad and not enclosing,'support_samples':count,
                          'obstructing_objects':sorted(set(ownership[crossing])),'enclosing_solids':enclosing,'unsupported_samples':bad[:30]}
            if not routes[name]['passed']:failures.append(team+'/'+name)
        roof=triangles_intersect_box(points,[-9.75,-9.75,11.0875],[9.75,9.75,45])
        if len(roof):failures.append(team+'/roof_reservation')
        # Native spawn supports must also survive every simplification.
        native=[]
        for sample in plan['validation']['native_support_checks']:
            if not sample['id'].startswith(team+'_') and ('_'+team+'_') not in sample['id'] and not(team=='red' and sample['id']=='warmup'):continue
            if 'banshee' in sample['id']:continue  # Ground remains authoritative terrain, below the new courts.
            x,y=np.asarray(sample['xy_m'])-origin[:2]
            z=floor_height(points,x,y,2.)
            expected=sample['expected_z_m']-origin[2]
            ok=z is not None and abs(z-expected)<.01
            native.append({'id':sample['id'],'passed':ok,'error_m':None if z is None else z-expected})
            if not ok:failures.append(team+'/'+sample['id'])
        # Roof y=0 lies exactly on a panel edge beside a 39mm visual joint;
        # select an interior point that survives native float32 quantization.
        for name,x,y,z in [('main_tunnel',0,0,.2),('front_court',0,-50,.2),('rear_court',0,45,.2),('roof',12,2,10.5675),('left_gallery',-21.45,-10,.2),('right_gallery',21.45,-10,.2)]:
            measured=floor_height(points,x,y,z+1.5,3.)
            require(measured is not None,'Missing architecture probe support '+team+'/'+name)
            p=np.array([x,y,measured])+origin
            probes.append({'id':team+'_'+name,'team':team,'floor_m':float(p[2]),'position_m':(p+[0,0,1.2]).tolist(),
                           'max_residual_m':.15,'yaw':0,'kind':'base_structure'})
        bases[team]={'routes':routes,'native_supports':native,'roof_reservation_passed':not len(roof),
                     'roof_obstructing_objects':sorted(set(ownership[roof])),'triangles':len(points)}
    return {'schema':'pwr-native-base-source-audit-v1','passed':not failures,'failures':failures,'bases':bases,
            'support_samples':sum(r['support_samples'] for b in bases.values() for r in b['routes'].values()),
            'probes':probes,'scope':'Prepared collision triangles, before native compilation. 7x3.5x4.5m conservative envelope; .5m tyre support samples. Not game physics.'}

def prepare(source_path,out_dir,contract_path=None):
    source_path=Path(source_path).resolve();out_dir=Path(out_dir).resolve()
    require(out_dir.is_relative_to(OLD.parent.resolve()) and out_dir!=OLD/'source-build','Output must be an isolated PWR expansion source directory')
    source=read(source_path);plan=read(PLAN);handoff=read(HANDOFF)
    require(source.get('schema')=='pwr-base-collision-source-v1' and source.get('coordinates')=='authoring_metres_z_up','Unsupported authored collision export')
    require(source['placement_plan_sha256']==sha(PLAN) and sha(source['source_blend'])==source['source_blend_sha256'],'Stale Blender collision export')
    require(plan['validation']['passed'],'Placement source is not validated')
    for item in handoff['authoritative_inputs']:require(sha(item['path'])==item['sha256'],'Frozen input changed: '+item['path'])
    old_extra_path=OLD/'source-build/terrain-collision-extra.json';old=read(old_extra_path);old_receipt=read(old_extra_path.with_suffix('.receipt.json'))
    old_tri=np.asarray(old['triangles'],dtype=float);inventory=handoff['collision_inventory']
    require(len(old_tri)==144172 and triangle_hash(old_tri[:TERRAIN])==inventory['preserved_terrain_triangle_f64_le_sha256'],'Frozen terrain source mismatch')
    require(canonical(old['materials'][:TERRAIN])==inventory['preserved_terrain_materials_sha256'],'Frozen terrain materials changed')
    keep_indices=list(range(TERRAIN));preserved=[]
    for row in inventory['architecture']:
        first=row['terrain_extra_first_surface'];count=row['surface_count'];p=old_tri[first:first+count]
        require(triangle_hash(p)==row['triangle_f64_le_sha256'],'Legacy architecture inventory changed: '+row['id'])
        if row['action']=='preserve_exactly':
            keep_indices.extend(range(first,first+count));preserved.append({**row,'new_first_extra_surface':len(keep_indices)-count})
    require(len(keep_indices)==TERRAIN+BRIDGES,'Wrong preserved terrain/bridge count')
    omitted=[];records=[]
    for row in source['objects']:
        reason=omission_reason(row)
        if reason:omitted.append({'name':row['name'],'triangles':len(row['triangles']),'reason':reason});continue
        repair=None
        if 'continuous recessed field' in row['name']:
            row,repair=field_without_engraved_grooves(row)
        points,topology=normalize_mesh(row)
        if repair:topology['facade_groove_simplification']=repair
        records.append({'name':row['name'],'team':row['team'],'module_role':row['module_role'],'points_m':points,'topology':topology})
    for row in source['omitted_native_decor']:
        proxy=native_proxy(row);points,topology=normalize_mesh(proxy)
        records.append({'name':proxy['name'],'team':proxy['team'],'module_role':'native_lining_proxy','points_m':points,'topology':topology})
    audit=audit_architecture(records,plan)
    OUT.mkdir(parents=True,exist_ok=True);write(OUT/'collision-source-audit.json',audit)
    require(audit['passed'],'Prepared architecture clearance failed; inspect collision-source-audit.json')
    n=sum(len(r['points_m']) for r in records)
    baseline=read(OLD/'upgrade/PWR/native-collision-receipt.json')
    candidate_global=baseline['source_surfaces']-REMOVED+n
    require(candidate_global<=MAX_SURFACES,f'New collision exceeds accepted1.2M budget: {candidate_global}')
    out_dir.mkdir(parents=True,exist_ok=True)
    dest=out_dir/'terrain-collision-extra.json'
    document={**old,'triangles':[old['triangles'][i] for i in keep_indices],
              'materials':[old['materials'][i] for i in keep_indices],
              'objects':old['objects']-96-60+len(records),'native_runtime_validated':False}
    document.pop('architecture_sha256',None)
    source_rows=[]
    for r in records:
        first=len(document['triangles']);p=r['points_m']/3.048
        document['triangles'].extend(p.tolist());document['materials'].extend(['hard_metal_thick']*len(p))
        source_rows.append({'name':r['name'],'team':r['team'],'module_role':r['module_role'],
                            'first_extra_surface':first,'surfaces':len(p),'triangle_f64_le_sha256':triangle_hash(p),**r['topology']})
    document['architecture_sources']=[{'path':str(source_path),'sha256':sha(source_path),'role':'reviewed_base_replacement',
        'first_extra_surface':TERRAIN+BRIDGES,'triangles':n}]
    document['architecture_contract_schema']=SCHEMA
    dest.write_text(json.dumps(document,separators=(',',':')),encoding='utf-8')
    for suffix in ('.ordered.npz','.seams.json'):
        shutil.copyfile(old_extra_path.with_suffix(suffix),dest.with_suffix(suffix))
    contract_path=Path(contract_path).resolve() if contract_path else out_dir/'base-architecture-contract.json'
    contract={'schema':SCHEMA,'source':{'path':str(source_path),'sha256':sha(source_path)},
       'source_blend':{'path':source['source_blend'],'sha256':source['source_blend_sha256']},
       'placement_plan':{'path':str(PLAN),'sha256':sha(PLAN)},'handoff':{'path':str(HANDOFF),'sha256':sha(HANDOFF)},
       'baseline_extra':{'path':str(old_extra_path),'sha256':sha(old_extra_path)},
       'output_extra':{'path':str(dest),'sha256':sha(dest)},
       'ordered':{'path':str(dest.with_suffix('.ordered.npz')),'sha256':sha(dest.with_suffix('.ordered.npz'))},
       'preserved_terrain':{'surfaces':TERRAIN,'triangle_f64_le_sha256':triangle_hash(old_tri[:TERRAIN]),'materials_sha256':canonical(old['materials'][:TERRAIN])},
       'preserved_bridges':preserved,'replacement_objects':source_rows,'omitted_visual_details':omitted,
       'counts':{'terrain':TERRAIN,'bridges':BRIDGES,'removed_legacy_base':REMOVED,'new_base':n,
                 'trailing_architecture':BRIDGES+n,'total_extra':TERRAIN+BRIDGES+n,
                 'baseline_global':baseline['source_surfaces'],'expected_global':candidate_global,'global_budget':MAX_SURFACES},
       'audit':{'path':str(OUT/'collision-source-audit.json'),'sha256':sha(OUT/'collision-source-audit.json'),'passed':True},
       'native_compiled':False,'live_validated':False,'scope':'Explicit replacement source contract. Native compilation/readback and in-game tests remain required.'}
    write(contract_path,contract)
    receipt={**old_receipt,'file':str(dest),'sha256':sha(dest),'bytes':dest.stat().st_size,
             'trailing_architecture_surfaces':BRIDGES+n,'total_extra_surfaces':TERRAIN+BRIDGES+n,
             'architecture_sources':document['architecture_sources'],'candidate_seams_path':str(dest.with_suffix('.seams.json')),
             'architecture_contract_path':str(contract_path),'architecture_contract_sha256':sha(contract_path)}
    write(dest.with_suffix('.receipt.json'),receipt)
    verify_contract(contract_path,receipt)
    return contract

def verify_contract(contract_path,receipt):
    c=read(contract_path);require(c.get('schema')==SCHEMA,'Unsupported base architecture contract')
    require(receipt.get('architecture_contract_sha256')==sha(contract_path),'Receipt has a different architecture contract')
    for key in ('source','source_blend','placement_plan','handoff','baseline_extra','output_extra','ordered','audit'):
        r=c[key];require(sha(r['path'])==r['sha256'],'Architecture contract source changed: '+key)
    counts=c['counts']
    require(counts['terrain']==TERRAIN and counts['bridges']==BRIDGES and counts['removed_legacy_base']==REMOVED,'Wrong preserved architecture ranges')
    require(counts['trailing_architecture']==counts['bridges']+counts['new_base'] and counts['total_extra']==TERRAIN+counts['trailing_architecture'],'Architecture count arithmetic mismatch')
    require(counts['expected_global']==counts['baseline_global']-REMOVED+counts['new_base'] and counts['expected_global']<=MAX_SURFACES,'Architecture collision budget failed')
    require(receipt['triangles']==TERRAIN and receipt['trailing_architecture_surfaces']==counts['trailing_architecture'] and receipt['total_extra_surfaces']==counts['total_extra'],'Terrain receipt disagrees with replacement contract')
    extra=read(receipt['file']);points=np.asarray(extra['triangles'],dtype=float)
    require(sha(receipt['file'])==receipt['sha256']==c['output_extra']['sha256'],'Replacement extra hash changed')
    require(len(points)==counts['total_extra'] and len(extra['materials'])==len(points),'Replacement triangle/material count mismatch')
    require(triangle_hash(points[:TERRAIN])==c['preserved_terrain']['triangle_f64_le_sha256'] and canonical(extra['materials'][:TERRAIN])==c['preserved_terrain']['materials_sha256'],'Protected terrain changed')
    for r in c['preserved_bridges']:
        start=r['new_first_extra_surface'];p=points[start:start+r['surface_count']]
        require(triangle_hash(p)==r['triangle_f64_le_sha256'],'Protected bridge changed: '+r['id'])
    first=TERRAIN+BRIDGES
    for r in c['replacement_objects']:
        require(r['first_extra_surface']==first,'Replacement collision ranges have overlap/gap')
        require(triangle_hash(points[first:first+r['surfaces']])==r['triangle_f64_le_sha256'],'Replacement object changed: '+r['name'])
        first+=r['surfaces']
    require(first==len(points),'Replacement collision has unaccounted tail')
    require(read(c['audit']['path'])['passed'],'Replacement clearance audit failed')
    return c

def verify_compiled(contract_path,compiled_path,out):
    """Read back every appended triangle from the actual native source binary."""
    c=read(contract_path);extra_path=Path(c['output_extra']['path'])
    verify_contract(contract_path,read(extra_path.with_suffix('.receipt.json')))
    compiled=read(compiled_path)
    require(compiled.get('schema')=='mjolnir-collision-pieces-v1' and not compiled['tail_linked_in_host'],'Expected separately instanced native collision')
    require(compiled['source_surfaces']==c['counts']['expected_global'],'Unexpected compiled surface count')
    manifest=Path(compiled['source_manifest']);binary_path=manifest.with_suffix('.bin')
    for p,k in ((manifest,'source_manifest_sha256'),(binary_path,'source_binary_sha256'),(Path(compiled['output']),'output_sha256')):
        require(sha(p)==compiled[k],'Stale compiled collision: '+str(p))
    binary=binary_path.read_bytes();sizes=[12,16,8,8,20,12,24,16];arrays=[];cursor=0
    for size in sizes:
        count,=struct.unpack_from('<I',binary,cursor);cursor+=4;arrays.append(memoryview(binary)[cursor:cursor+count*size]);cursor+=count*size
    require(cursor==len(binary),'Unexpected native source array layout')
    surfaces=np.frombuffer(arrays[5],dtype=np.dtype([('plane','<i4'),('edge','<i4'),('rest','<i4')]))
    edges=np.frombuffer(arrays[6],dtype='<i4').reshape(-1,6)
    points=np.frombuffer(arrays[7],dtype=np.dtype([('xyz','<f4',3),('edge','<i4')]))['xyz']
    first=len(surfaces)-c['counts']['total_extra'];first_edges=surfaces['edge'][first:]
    require(len(surfaces)==compiled['source_surfaces'] and first>=compiled['source_tail_range'][0],
            'Replacement extra does not fit compiled source tail')
    edge_ids=np.stack([first_edges,edges[first_edges,2],edges[edges[first_edges,2],2]],axis=1)
    require(np.array_equal(edges[edge_ids[:,2],2],first_edges),'Non-triangular native extra ring')
    actual=points[edges[edge_ids,0]];expected=np.asarray(read(extra_path)['triangles'],dtype=np.float32)
    require(np.array_equal(actual,expected),'Compiled source does not preserve every prepared collision triangle')
    owners=np.full(len(actual),-1,dtype=np.int64)
    for piece in compiled['pieces']:
        span=piece['source_surface_range']
        if span is None:continue
        lo,hi=max(span[0],first)-first,min(span[1],len(surfaces))-first
        if hi>lo:
            require(np.all(owners[lo:hi]==-1),'Compiled pieces overlap the replacement source tail')
            owners[lo:hi]=piece['instance']
    require(np.all(owners>=0),'Compiled pieces do not cover the replacement source tail')
    records=[]
    for r in c['replacement_objects']:
        start=r['first_extra_surface'];records.append({**r,'points_m':actual[start:start+r['surfaces']].astype(float)*3.048})
    audit=audit_architecture(records,read(c['placement_plan']['path']))
    require(audit['passed'],'Native float32 readback changed architectural support/clearance')
    audit['scope']='Compiled native source float32 triangles and piece ranges. Vehicle clearance/support audit; live game physics remain unvalidated.'
    report={'schema':'pwr-compiled-base-collision-proof-v1','passed':True,'contract_sha256':sha(contract_path),
       'compiled_receipt':str(Path(compiled_path).resolve()),'compiled_receipt_sha256':sha(compiled_path),
       'compiled_collision_sha256':compiled['output_sha256'],'verified_extra_triangles':len(actual),
       'verified_base_triangles':c['counts']['new_base'],'all_source_triangles_exact_float32':True,
       'compiled_boundaries_verified':True,'extra_source_surface_range':[first,len(surfaces)],
       'extra_collision_instances':sorted(map(int,np.unique(owners))),
       'architecture_audit':audit,'live_validated':False}
    write(out,report);return report

def main():
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='command',required=True)
    prep=sub.add_parser('prepare');prep.add_argument('--source',type=Path,default=OUT/'collision-authored.json');prep.add_argument('--out-dir',type=Path,default=WORLD/'source-build')
    verify=sub.add_parser('verify');verify.add_argument('contract',type=Path);verify.add_argument('receipt',type=Path)
    compiled=sub.add_parser('compiled');compiled.add_argument('contract',type=Path);compiled.add_argument('receipt',type=Path);compiled.add_argument('--out',type=Path,default=OUT/'compiled-base-collision-proof.json')
    args=p.parse_args()
    if args.command=='compiled':
        result=verify_compiled(args.contract,args.receipt,args.out);print(json.dumps({'passed':result['passed'],'out':str(args.out),'verified_triangles':result['verified_extra_triangles']}));return
    c=prepare(args.source,args.out_dir) if args.command=='prepare' else verify_contract(args.contract,read(args.receipt))
    print(json.dumps({'counts':c['counts'],'output':c['output_extra'],'audit_passed':c['audit']['passed']},indent=2))

if __name__=='__main__':main()
