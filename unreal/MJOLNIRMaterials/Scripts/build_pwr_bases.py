"""Build reviewed PWR base meshes/materials with native UE Nanite assets.

MJ_PWR_BASE_MANIFEST may override the isolated Blender-export manifest path.
No game installation. Native Blam collision is built by the separate pipeline.
"""
from pathlib import Path
import gc,hashlib,json,os,struct,time
import unreal

REPO=Path(__file__).resolve().parents[3]
SOURCE=Path(os.environ.get('MJ_PWR_BASE_MANIFEST',str(REPO/'out/pwr/base-runtime/visuals/manifest.json')))
OUT=SOURCE.parent
manifest=json.loads(SOURCE.read_text())
ROOT=manifest['asset_root']
CHUNK=int(os.environ.get('MJ_PWR_BASE_CHUNK',manifest['chunk']))
if not manifest['complete_export'] or ROOT!='/Game/MJOLNIR/Bases/PWRV1' or CHUNK!=955:
    raise RuntimeError('Unexpected base visual input/ownership contract')
eal=unreal.EditorAssetLibrary
tools=unreal.AssetToolsHelpers.get_asset_tools()
mel=unreal.MaterialEditingLibrary
subsystem=unreal.get_default_object(unreal.StaticMeshEditorSubsystem)

def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()

# Capture provenance before any long-running mesh build. A source edit while
# Unreal is importing must not make the old compiled script claim the new hash.
SOURCE_SHA=digest(SOURCE)
SCRIPT_SHA=digest(__file__)

def props(obj,values):
    # Python's batched setter emits one Pre/PostEditChange for the whole map.
    # Per-field setters on a mesh-owned struct can rebuild Nanite every time.
    obj.set_editor_properties(values)

def texture(key,name,compression):
    spec=manifest['textures'][key]
    if digest(spec['path'])!=spec['sha256']:raise RuntimeError('Changed texture '+key)
    task=unreal.AssetImportTask();props(task,{'filename':spec['path'],'destination_path':ROOT+'/Textures',
         'destination_name':name,'automated':True,'replace_existing':True,'save':False})
    tools.import_asset_tasks([task])
    tex=unreal.load_asset(ROOT+'/Textures/'+name)
    if not isinstance(tex,unreal.Texture2D):raise RuntimeError('Texture import failed '+key)
    props(tex,{'srgb':False,'compression_settings':compression,'never_stream':False,
               'address_x':unreal.TextureAddress.TA_WRAP,'address_y':unreal.TextureAddress.TA_WRAP})
    eal.save_loaded_asset(tex);return tex

normal=texture('normal_rg','T_FR_Diagonal_RG',unreal.TextureCompressionSettings.TC_VECTOR_DISPLACEMENTMAP)
masks=texture('mask_orhg','T_FR_Diagonal_ORHG',unreal.TextureCompressionSettings.TC_MASKS)
master_path=ROOT+'/Materials/M_PWR_BaseFinish'
master=unreal.load_asset(master_path)
if master is None:master=tools.create_asset('M_PWR_BaseFinish',ROOT+'/Materials',unreal.Material,unreal.MaterialFactoryNew())
if not isinstance(master,unreal.Material):raise RuntimeError('Unexpected master material class')
mel.delete_all_material_expressions(master)
props(master,{'used_with_nanite':True,'used_with_instanced_static_meshes':True,'used_with_static_lighting':False,
               'two_sided':False,'tangent_space_normal':True,'blend_mode':unreal.BlendMode.BLEND_OPAQUE})

def node(cls,**kw):
    n=mel.create_material_expression(master,cls);props(n,kw);return n

def link(a,p,b,q):
    if not mel.connect_material_expressions(a,p,b,q):raise RuntimeError('Material link failed: '+q)

def output(a,prop):
    if not mel.connect_material_property(a,'',prop):raise RuntimeError('Material output failed')

def scalar(name,value):return node(unreal.MaterialExpressionScalarParameter,parameter_name=name,default_value=value)

def custom(code,bindings,kind):
    n=node(unreal.MaterialExpressionCustom,code=code,output_type=kind,description='PWR base finish')
    entries=[]
    for name,source,pin in bindings:
        c=unreal.CustomInput();c.set_editor_property('input_name',name);entries.append(c)
    n.set_editor_property('inputs',entries)
    for name,source,pin in bindings:link(source,pin,n,name)
    return n

uv=node(unreal.MaterialExpressionTextureCoordinate,coordinate_index=0)
rg=node(unreal.MaterialExpressionTextureSample,texture=normal,sampler_type=unreal.MaterialSamplerType.SAMPLERTYPE_LINEAR_COLOR)
orm=node(unreal.MaterialExpressionTextureSample,texture=masks,sampler_type=unreal.MaterialSamplerType.SAMPLERTYPE_MASKS)
link(uv,'',rg,'UVs');link(uv,'',orm,'UVs')
tint=node(unreal.MaterialExpressionVectorParameter,parameter_name='Tint',default_value=unreal.LinearColor(.242,.246,.244,1))
variance=scalar('Variation',.06);court=scalar('Court',0)
color=custom('''
float2 p=UV*.43; float2 cell=floor(p), f=frac(p); f=f*f*(3-2*f);
float4 h=frac(sin(float4(dot(cell,float2(127.1,311.7)),dot(cell+float2(1,0),float2(127.1,311.7)),dot(cell+float2(0,1),float2(127.1,311.7)),dot(cell+1,float2(127.1,311.7))))*43758.5453);
float noise=lerp(lerp(h.x,h.y,f.x),lerp(h.z,h.w,f.x),f.y);
float3 c=Tint*(1+(noise*2-1)*Variation);
float2 metre=UV*5; float row=floor(metre.y/6); metre.x+=fmod(abs(row),2)*4;
float2 q=frac(metre/float2(8,6)); float edge=min(min(q.x,1-q.x)*8,min(q.y,1-q.y)*6);
float seam=1-smoothstep(.018,.035,edge);
return c*lerp(1,1-.55*seam,Court);
''',[('UV',uv,''),('Tint',tint,''),('Variation',variance,''),('Court',court,'')],unreal.CustomMaterialOutputType.CMOT_FLOAT3)
output(color,unreal.MaterialProperty.MP_BASE_COLOR)
low=scalar('RoughMin',.32);high=scalar('RoughMax',.50)
rough=custom('return lerp(Low,High,saturate(Mask.g));',[('Mask',orm,'RGB'),('Low',low,''),('High',high,'')],unreal.CustomMaterialOutputType.CMOT_FLOAT1)
output(rough,unreal.MaterialProperty.MP_ROUGHNESS)
output(scalar('Metallic',.66),unreal.MaterialProperty.MP_METALLIC)
strength=scalar('NormalStrength',.17)
normal_node=custom('float2 xy=(RG.xy*2-1)*Strength; return normalize(float3(xy,sqrt(saturate(1-dot(xy,xy)))));',
                   [('RG',rg,'RGB'),('Strength',strength,'')],unreal.CustomMaterialOutputType.CMOT_FLOAT3)
output(normal_node,unreal.MaterialProperty.MP_NORMAL)
emission=scalar('Emission',0)
emit=custom('return Tint*Power;',[('Tint',tint,''),('Power',emission,'')],unreal.CustomMaterialOutputType.CMOT_FLOAT3)
output(emit,unreal.MaterialProperty.MP_EMISSIVE_COLOR)
mel.recompile_material(master);eal.save_loaded_asset(master)
materials={}
for key,recipe in manifest['materials'].items():
    name='MI_PWR_'+key;path=ROOT+'/Materials/'+name
    mat=unreal.load_asset(path)
    if mat is None:mat=tools.create_asset(name,ROOT+'/Materials',unreal.MaterialInstanceConstant,unreal.MaterialInstanceConstantFactoryNew())
    mel.set_material_instance_parent(mat,master)
    mel.set_material_instance_vector_parameter_value(mat,'Tint',unreal.LinearColor(*recipe['color'],1))
    for k,v in {'Metallic':recipe['metallic'],'RoughMin':recipe['roughness'][0],'RoughMax':recipe['roughness'][1],
                'NormalStrength':recipe['normal_strength'],'Variation':recipe['variation'],
                'Emission':recipe['emission'],'Court':float(recipe['court'])}.items():
        mel.set_material_instance_scalar_parameter_value(mat,k,v)
    mel.update_material_instance(mat);eal.save_loaded_asset(mat);materials[key]=mat

def read_mesh(spec):
    path=Path(spec['gltf'])
    if digest(path)!=spec['gltf_sha256']:raise RuntimeError('Changed mesh JSON '+spec['name'])
    doc=json.loads(path.read_text());data=(path.parent/doc['buffers'][0]['uri']).read_bytes()
    if hashlib.sha256(data).hexdigest()!=spec['bin_sha256']:raise RuntimeError('Changed mesh binary '+spec['name'])
    def acc(index):
        a=doc['accessors'][index];v=doc['bufferViews'][a['bufferView']]
        width={'SCALAR':1,'VEC2':2,'VEC3':3}[a['type']];fmt={5126:'f',5125:'I'}[a['componentType']]
        pack=struct.Struct('<'+fmt*width);offset=v.get('byteOffset',0)+a.get('byteOffset',0);stride=v.get('byteStride',pack.size)
        return [pack.unpack_from(data,offset+j*stride) for j in range(a['count'])]
    ps=[];ns=[];indices=[];uvs=[];sections=[];names=[]
    for si,p in enumerate(doc['meshes'][0]['primitives']):
        attr=p['attributes'];pos=acc(attr['POSITION']);norm=acc(attr['NORMAL']);uv=acc(attr['TEXCOORD_0']);local=[x[0] for x in acc(p['indices'])];base=len(ps)
        ps.extend(unreal.Vector(x*100,z*100,y*100) for x,y,z in pos)
        ns.extend(unreal.Vector(x,z,y) for x,y,z in norm)
        indices.extend(base+i for i in local);uvs.extend(unreal.Vector2D(*uv[i]) for i in local)
        sections.extend([si]*(len(local)//3));names.append(doc['materials'][p['material']]['name'])
    if names!=spec['material_keys'] or len(indices)//3!=spec['triangles']:raise RuntimeError('Mesh counts/slots changed')
    return ps,ns,indices,uvs,sections,names

reports=[];asset_objects=[master,normal,masks,*materials.values()]
for spec in manifest['assets']:
    ps,ns,indices,uvs,sections,names=read_mesh(spec)
    mesh=unreal.load_asset(spec['asset'])
    if mesh is None:mesh=tools.create_asset(spec['name'],ROOT+'/Meshes',unreal.StaticMesh,None)
    # Configure a detached struct; get_editor_property returns an owner-linked
    # struct whose individual edits otherwise trigger repeated mesh rebuilds.
    nanite=mesh.get_editor_property('nanite_settings').copy()
    nanite.set_editor_property('enabled',False)
    props(mesh,{'nanite_settings':nanite,'allow_cpu_access':True,'has_navigation_data':False})
    colors=[unreal.Color(r=255,g=255,b=255,a=255)]*len(ps)
    if not unreal.MjolnirUIBuilderLibrary.build_attributed_static_mesh(mesh,ps,ns,indices,uvs,1,sections,names,colors):
        raise RuntimeError('MeshDescription build failed: '+spec['name'])
    slots=[]
    for entry,name in zip(mesh.get_editor_property('static_materials'),names):
        slot=entry.copy();slot.set_editor_property('material_interface',materials[name]);slots.append(slot)
    props(nanite,{'enabled':True,'preserve_area':False,'explicit_tangents':True,'keep_percent_triangles':1.0,
                  'trim_relative_error':0.0,'position_precision':6,
                  'fallback_target':unreal.NaniteFallbackTarget.PERCENT_TRIANGLES,
                  'fallback_percent_triangles':1.0,'fallback_relative_error':0.0})
    # One final expensive build with complete materials, UV metadata and the
    # final Nanite settings. The shared builder resets slot interfaces/LM index.
    props(mesh,{'static_materials':slots,'nanite_settings':nanite,'light_map_coordinate_index':0})
    body=mesh.get_editor_property('body_setup')
    instance=body.get_editor_property('default_instance').copy();instance.set_editor_property('collision_profile_name','NoCollision')
    props(body,{'never_needs_cooked_collision_data':True,'collision_trace_flag':unreal.CollisionTraceFlag.CTF_USE_SIMPLE_AS_COMPLEX,'default_instance':instance})
    if subsystem.get_num_uv_channels(mesh,0)!=1:raise RuntimeError('Lost metric UVs')
    if not eal.save_loaded_asset(mesh):raise RuntimeError('Failed to save base mesh')
    b=mesh.get_bounds();c,e=b.origin,b.box_extent
    reports.append({'asset':mesh.get_path_name(),'source_triangles':spec['triangles'],'render_vertices':subsystem.get_number_verts(mesh,0),
                    'uv_channels':1,'materials':names,'bounds_ue_cm':[[c.x-e.x,c.y-e.y,c.z-e.z],[c.x+e.x,c.y+e.y,c.z+e.z]],
                    'nanite_enabled':mesh.get_editor_property('nanite_settings').get_editor_property('enabled')})
    asset_objects.append(mesh)
    unreal.log('MJOLNIR PWR BASE imported '+spec['name']+' '+str(spec['triangles'])+' triangles')
    del ps,ns,indices,uvs,sections,names,colors;gc.collect()

label=unreal.load_asset(ROOT+'/PAL_PWR_Bases955')
if label is None:label=tools.create_asset('PAL_PWR_Bases955',ROOT,unreal.PrimaryAssetLabel,unreal.DataAssetFactory())
rules=label.get_editor_property('rules')
props(rules,{'chunk_id':CHUNK,'priority':1000,'apply_recursively':True,'cook_rule':unreal.PrimaryAssetCookRule.ALWAYS_COOK})
props(label,{'rules':rules,'label_assets_in_my_directory':False,'explicit_assets':asset_objects})
eal.save_loaded_asset(label)
if digest(SOURCE)!=SOURCE_SHA or digest(__file__)!=SCRIPT_SHA:
    raise RuntimeError('Base import inputs changed during the build; rerun before cooking')
receipt={'schema':'pwr-native-base-editor-import-v1','manifest_sha256':SOURCE_SHA,'script_sha256':SCRIPT_SHA,
         'chunk':CHUNK,'asset_root':ROOT,'meshes':reports,'materials':{k:v.get_path_name() for k,v in materials.items()},
         'textures':[normal.get_path_name(),masks.get_path_name()], 'material_policy':'native PBR finish mapped from reviewed profiles; original RG tangent normals and G roughness, team emission and metric court seams',
         'native_collision':'None in Unreal assets; native Blam collision authored separately',
         'requires_retarget_classes':['Material','MaterialInstanceConstant','StaticMesh'],
         'cooked':False,'installed':False}
(OUT/'editor-import.receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
unreal.log('MJOLNIR PWR BASE BUILD COMPLETE '+json.dumps({'meshes':len(reports),'materials':len(materials),'chunk':CHUNK}))
