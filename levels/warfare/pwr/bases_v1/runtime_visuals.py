"""Export the integrated Blender bases for native UE MeshDescription/Nanite cook.

Run through Blender MCP in the assembled world. Evaluated transforms, including
blue's reflection, are baked into vertices, normals and winding. Runtime actors
have positive unit scale. This writes an isolated native-build input; no install.
"""
from pathlib import Path
import hashlib,json,re,sys,time
import numpy as np

ROOT=Path(__file__).resolve().parents[4]
HERE=Path(__file__).resolve().parent
OUT=ROOT/'out/pwr/base-runtime/visuals'
ASSET_ROOT='/Game/MJOLNIR/Bases/PWRV1'
CHUNK=955

def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
    return h.hexdigest()

def material_recipe(mat):
    sys.path.insert(0,str(HERE))
    from finishing_materials import PROFILES
    key=mat.get('native_finish_profile') if mat else None
    if key in PROFILES:
        p=PROFILES[key]
        return key,{'color':list(p['color']),'metallic':p['metal'],'roughness':list(p['rough']),
                    'normal_strength':p['normal'],'variation':p['variance'],'emission':0.,'court':False}
    name=mat.name if mat else 'missing'
    if 'weathered modular court' in name:
        return 'court',{'color':[.17,.19,.20],'metallic':.28,'roughness':[.68,.84],
                        'normal_strength':0.,'variation':.035,'emission':0.,'court':True}
    b=mat.node_tree.nodes.get('Principled BSDF') if mat and mat.use_nodes else None
    color=list(b.inputs['Base Color'].default_value[:3]) if b else [.12,.14,.16]
    metal=float(b.inputs['Metallic'].default_value) if b else .35
    rough=float(b.inputs['Roughness'].default_value) if b else .65
    emission=float(b.inputs['Emission Strength'].default_value) if b else 0
    if emission and b:color=list(b.inputs['Emission Color'].default_value[:3])
    label='team_red' if name.startswith('TEAM') and 'red' in name else 'team_blue' if name.startswith('TEAM') and 'blue' in name else 'team_green' if name.startswith('TEAM') and 'green' in name else 'interior_light' if emission else 'recess' if 'recessed foundation' in name else 'shadow'
    return label,{'color':color,'metallic':metal,'roughness':[rough,rough],
                  'normal_strength':0.,'variation':.02,'emission':emission,'court':False}

def repair_triangle_uvs(flat):
    """Supply metric tangent frames only where evaluated bevel UVs collapsed.

    Bevel-generated side faces can inherit collinear UVs from an otherwise
    valid source polygon. Project those triangles onto their dominant physical
    plane, with U cross V following the geometric normal. Native normal maps
    then have a stable tangent basis on both reflected and unreflected assets.
    Positions, split normals, triangle order and all unaffected UVs stay exact.
    """
    data=flat.reshape(-1,3,8)
    uv=data[:,:,6:8];a=uv[:,1]-uv[:,0];b=uv[:,2]-uv[:,0]
    det=a[:,0]*b[:,1]-a[:,1]*b[:,0]
    bad=np.flatnonzero(abs(det)<1e-10)
    if not len(bad):return flat,0,0
    # glTF metres (X,Z,-Y) back to the reviewed authoring metre axes.
    p=data[bad,:,:3][:,:,[0,2,1]]*np.array([1,-1,1],dtype=np.float32)
    normal=np.cross(p[:,1]-p[:,0],p[:,2]-p[:,0]);axis=np.argmax(abs(normal),axis=1)
    valid=np.linalg.norm(normal,axis=1)>1e-10
    fixed=np.empty((len(bad),3,2),dtype=np.float32)
    for k in range(3):
        use=axis==k;sign=np.sign(normal[use,k]);sign[sign==0]=1
        if k==0:
            fixed[use,:,0]=p[use,:,1]*sign[:,None];fixed[use,:,1]=p[use,:,2]
        elif k==1:
            fixed[use,:,0]=-p[use,:,0]*sign[:,None];fixed[use,:,1]=p[use,:,2]
        else:
            fixed[use,:,0]=p[use,:,0]*sign[:,None];fixed[use,:,1]=p[use,:,1]
    data[bad[valid],:,6:8]=fixed[valid]/5.
    return data.reshape(-1,8),int(np.count_nonzero(valid)),int(np.count_nonzero(~valid))

def mesh_arrays(ob,dg,anchor):
    import bpy
    eo=ob.evaluated_get(dg);me=eo.to_mesh()
    try:
        me.calc_loop_triangles()
        verts=np.empty((len(me.vertices),3),dtype=np.float64);me.vertices.foreach_get('co',verts.ravel())
        matrix=np.asarray(eo.matrix_world,dtype=np.float64)
        world=verts@matrix[:3,:3].T+matrix[:3,3]
        loops=np.empty(len(me.loops),dtype=np.int32);me.loops.foreach_get('vertex_index',loops)
        tri_loops=np.empty((len(me.loop_triangles),3),dtype=np.int32);me.loop_triangles.foreach_get('loops',tri_loops.ravel())
        tri_mats=np.empty(len(me.loop_triangles),dtype=np.int32);me.loop_triangles.foreach_get('material_index',tri_mats)
        ns=np.empty((len(me.loops),3),dtype=np.float64);me.corner_normals.foreach_get('vector',ns.ravel())
        ns=ns@np.linalg.inv(matrix[:3,:3]);ns/=np.maximum(np.linalg.norm(ns,axis=1)[:,None],1e-15)
        uv_layer=me.uv_layers.get('FinishUV')
        if uv_layer:
            uv=np.empty((len(me.loops),2),dtype=np.float32);uv_layer.data.foreach_get('uv',uv.ravel())
        else:
            # Courtyard and bridge shaders use world-metric mapping. Nonfinish
            # fixtures are constant colors, so the projection cannot distort them.
            uv=((world[loops,:2]-np.asarray(anchor)[:2])/5).astype(np.float32)
        reflected=np.linalg.det(matrix[:3,:3])<0
        if reflected:tri_loops=tri_loops[:,[0,2,1]]
        local=(world-np.asarray(anchor)).astype(np.float32)
        pos=local[loops][:,[0,2,1]]*np.array([1,1,-1],np.float32)
        norm=ns[:,[0,2,1]]*np.array([1,1,-1],np.float64)
        # OpenGL glTF UV convention: native UE custom loader consumes UVs
        # directly, so keep the reviewed Blender V rather than exporter flips.
        attributes=np.c_[pos,norm.astype(np.float32),uv].astype('<f4')
        parts=[];uv_repaired=uv_zero_area=0
        for mi in sorted(set(tri_mats.tolist())):
            tri=tri_loops[tri_mats==mi]
            flat=attributes[tri.ravel()].copy()
            flat,fixed,zero=repair_triangle_uvs(flat);uv_repaired+=fixed;uv_zero_area+=zero
            unique,inverse=np.unique(flat,axis=0,return_inverse=True)
            mat=ob.material_slots[mi].material if mi<len(ob.material_slots) else None
            key,recipe=material_recipe(mat)
            parts.append((key,recipe,unique,inverse.reshape(-1,3).astype('<u4')))
        return parts,{'object':ob.name,'triangles':len(tri_loops),'reflected_transform_baked':bool(reflected),
                      'repaired_degenerate_uv_triangles':uv_repaired,'unrepairable_zero_area_uv_triangles':uv_zero_area,
                      'world_bounds_m':[world.min(0).tolist(),world.max(0).tolist()]}
    finally:eo.to_mesh_clear()

def write_gltf(name,by_material,out):
    views=[];accessors=[];binary=bytearray();primitives=[];materials=[]
    def add(array,kind):
        a=np.ascontiguousarray(array)
        while len(binary)%4:binary.append(0)
        views.append({'buffer':0,'byteOffset':len(binary),'byteLength':a.nbytes})
        binary.extend(a.tobytes())
        result={'bufferView':len(views)-1,'componentType':5125 if a.dtype.kind=='u' else 5126,
                'count':a.size if kind=='SCALAR' else len(a),'type':kind}
        if kind=='VEC3':result.update(min=a.min(0).tolist(),max=a.max(0).tolist())
        accessors.append(result);return len(accessors)-1
    total_v=total_t=0;bounds=[]
    for key,parts in sorted(by_material.items()):
        arrays=[];tris=[];offset=0
        for values,tri in parts:
            arrays.append(values);tris.append(tri+offset);offset+=len(values)
        values=np.concatenate(arrays);tri=np.concatenate(tris).astype('<u4')
        attributes={label:add(values[:,sl].copy(),kind) for label,sl,kind in
                    [('POSITION',slice(0,3),'VEC3'),('NORMAL',slice(3,6),'VEC3'),('TEXCOORD_0',slice(6,8),'VEC2')]}
        primitives.append({'attributes':attributes,'indices':add(tri,'SCALAR'),'material':len(materials)})
        materials.append({'name':key});total_v+=len(values);total_t+=len(tri);bounds.append(values[:,:3])
    binfile=out/(name+'.bin');binfile.write_bytes(binary)
    document={'asset':{'version':'2.0','generator':'PWR evaluated world native base exporter'},
              'buffers':[{'uri':binfile.name,'byteLength':len(binary)}],'bufferViews':views,'accessors':accessors,
              'materials':materials,'meshes':[{'name':name,'primitives':primitives}],
              'nodes':[{'mesh':0}],'scenes':[{'nodes':[0]}],'scene':0}
    path=out/(name+'.gltf');path.write_text(json.dumps(document,separators=(',',':'))+'\n')
    p=np.concatenate(bounds)
    return {'gltf':str(path),'gltf_sha256':sha(path),'bin_sha256':sha(binfile),'vertices':total_v,'triangles':total_t,
            'material_keys':[m['name'] for m in materials],'gltf_bounds_m':[p.min(0).tolist(),p.max(0).tolist()]}

def main():
    import bpy
    start=time.time();scene=bpy.context.scene
    if Path(bpy.data.filepath).name!='pwr-world-bases-v1.blend':raise RuntimeError('Open the verified integrated world')
    proof=json.loads((ROOT/'out/pwr/base-integration/world-clearance.json').read_text())
    if not proof['passed']:raise RuntimeError('World clearance failed')
    plan=json.loads((ROOT/'out/pwr/base-integration/placement-plan.json').read_text())
    OUT.mkdir(parents=True,exist_ok=True);bpy.context.view_layer.update();dg=bpy.context.evaluated_depsgraph_get()
    groups={};anchors={};expected_counts={}
    for site in plan['bases']:
        team=site['id'];col=next(c for c in scene.collection.children if c.name.startswith(site['collection_prefix']))
        for ob in col.all_objects:
            if ob.type!='MESH':continue
            clean=re.sub(r'^0[23]_(?:BLUE|GREEN)/','',ob.name)
            category='native_panels' if clean.startswith('stock/') else 'emission' if any(s.material and (s.material.name.startswith('TEAM') or 'interior light' in s.material.name) for s in ob.material_slots) else 'detail' if clean.startswith(('detail/','inlay/','lamp/','engraving/')) else 'architecture'
            label=team+'_'+category;groups.setdefault(label,[]).append(ob);anchors[label]=site['normalize_then_translate_m']
        label=team+'_court';groups[label]=[o for o in scene.objects if o.get('team')==team and o.get('offline_collision_candidate')];anchors[label]=site['normalize_then_translate_m']
    for ob in scene.objects:
        if ob.type=='MESH' and ob.name.startswith('World bridge '):
            label=ob.name.removeprefix('World bridge ');groups[label]=[ob]
            corners=np.asarray([list(ob.matrix_world@__import__('mathutils').Vector(x)) for x in ob.bound_box])
            anchors[label]=((corners.min(0)+corners.max(0))*.5).tolist()
    recipes={};assets=[];decor=[]
    for label,objects in groups.items():
        name='SM_PWR_'+label;by_material={};records=[]
        for ob in objects:
            parts,record=mesh_arrays(ob,dg,anchors[label]);records.append(record)
            for key,recipe,values,tri in parts:
                if key in recipes and recipes[key]!=recipe:raise RuntimeError('Conflicting material recipe '+key)
                recipes[key]=recipe;by_material.setdefault(key,[]).append((values,tri))
        exported=write_gltf(name,by_material,OUT)
        package=ASSET_ROOT+'/Meshes/'+name
        row={'id':label,'name':name,'asset':package,'anchor_m':anchors[label],**exported,'source_objects':records,
             'repaired_degenerate_uv_triangles':sum(r['repaired_degenerate_uv_triangles'] for r in records),
             'unrepairable_zero_area_uv_triangles':sum(r['unrepairable_zero_area_uv_triangles'] for r in records)}
        assets.append(row)
        x,y,z=anchors[label]
        decor.append({'id':'pwr_newbase_'+label,'mesh':package+'.'+name,'pos':[x*100,-y*100,z*100],
                      'rot':[0,0,0],'scale':[1,1,1],'static':True,'cast_shadow':True})
        print('PWR_VISUAL_EXPORT',label,exported['triangles'],flush=True)
    base_triangles=sum(a['triangles'] for a in assets if any(a['id'].startswith(t+'_') for t in ('red','blue','green')) and not a['id'].endswith('_court'))
    expected=sum(b['checks']['reviewed_base_shape_preserved']['actual']['evaluated_triangles'] for b in proof['bases'].values())
    if base_triangles!=expected:raise RuntimeError(f'Lost base triangles: {base_triangles} != {expected}')
    manifest={'schema':'pwr-native-base-visual-input-v1','asset_root':ASSET_ROOT,'chunk':CHUNK,
              'source_blend':bpy.data.filepath,'source_blend_sha256':sha(bpy.data.filepath),
              'placement_plan_sha256':sha(ROOT/'out/pwr/base-integration/placement-plan.json'),
              'geometry_validation_sha256':sha(ROOT/'out/pwr/base-integration/world-clearance.json'),
              'assets':assets,'materials':recipes,'textures':{
                  'normal_rg':{'path':str(HERE/'textures/native-fr-diagonal-rg.png'),'sha256':sha(HERE/'textures/native-fr-diagonal-rg.png')},
                  'mask_orhg':{'path':str(HERE/'textures/native-fr-diagonal-orhg.png'),'sha256':sha(HERE/'textures/native-fr-diagonal-orhg.png')}},
              'total_triangles':sum(a['triangles'] for a in assets),'base_triangles':base_triangles,
              'coordinates':'glTF metres Y-up; vertex transforms and negative-determinant winding baked; actor positions Unreal cm, positive unit scale',
              'runtime_collision':'Separate native Blam replacement; Unreal mesh collision disabled',
              'uv_policy':'Reviewed FinishUV unchanged except collapsed evaluated bevel/side triangle UVs; those receive metre-scale dominant-plane projection with U cross V following the geometric normal. Native DirectX normal texture green remains unflipped.',
              'complete_export':True,'cooked':False,'duration_seconds':time.time()-start}
    (OUT/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    (OUT/'runtime_decor.json').write_text(json.dumps({'schema':'mjolnir-runtime-decor-v1','render_only':True,'decor':decor},indent=2)+'\n')
    print(json.dumps({'manifest':str(OUT/'manifest.json'),'assets':len(assets),'triangles':manifest['total_triangles'],'seconds':time.time()-start}))

if __name__=='__main__':main()
