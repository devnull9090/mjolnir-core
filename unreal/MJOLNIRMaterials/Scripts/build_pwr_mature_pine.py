"""Import the frozen native-attribute pine through a full MeshDescription.

Original UV0/1/2 and RGBA survive the explicit attribute builder. Native
material references use never-cooked /Game/Env MIC stand-ins, exactly as the
foliage pipeline does. Only the measured Nanite StaticMesh belongs to959.
"""
import hashlib
import json
import os
import struct
from pathlib import Path
import unreal

ROOT=Path(__file__).resolve().parents[3]
SOURCE=Path(os.environ.get('MJ_PWR_PINE_SOURCE',str(ROOT/'out/pwr/visual-v5/outcrops-v4/trees/mature-pine-a.glb')))
OUT=Path(os.environ.get('MJ_PWR_PINE_OUT',str(ROOT/'out/pwr/visual-v5/outcrops-v4/trees/native')))
EXPECTED=os.environ.get('MJ_PWR_PINE_SHA','68bdcb09e0af2dc2030b50b543f45d28a7284264bd7ce188484759b320cdf405')
FOLDER='/Game/MJOLNIR/Scenery/PWR'
NAME='SM_PWR_MaturePine_A'
BINDINGS={
 'MI_Pine_Tree_Mat':'/Game/Env/Bio/Tree/Pine/Tree_Windswept/Materials/MI_Pine_Tree_Mat_LOD0',
 'MI_Branch_Mat':'/Game/Env/Bio/Tree/Pine/Tree_Windswept_A/Materials/MI_Branch_Mat_LOD0_TwoSided',
}
eal=unreal.EditorAssetLibrary
tools=unreal.AssetToolsHelpers.get_asset_tools()
# PythonScriptCommandlet does not instantiate editor subsystems. These query
# functions are stateless; use the CDO only for reads. Mutating subsystem
# methods dereference AssetEditorSubsystem and are not commandlet-safe.
subsystem=unreal.get_default_object(unreal.StaticMeshEditorSubsystem)


def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def set_props(obj,properties):
    for name,value in properties.items():obj.set_editor_property(name,value)


def native_material(path,masked):
    # The placeholder parent never ships. Its flags let Nanite build the
    # masked, two-sided branch sections correctly during this authoring cook.
    folder,name=path.rsplit('/',1)
    material=unreal.load_asset(path)
    if material is None:
        material=tools.create_asset(name,folder,unreal.MaterialInstanceConstant,unreal.MaterialInstanceConstantFactoryNew())
    if not isinstance(material,unreal.MaterialInstanceConstant):raise RuntimeError('Unexpected native stand-in class: '+path)
    parent_path='/Game/Env/MJOLNIRAuthoring/M_PWR_Pine_'+('Needles' if masked else 'Bark')
    parent=unreal.load_asset(parent_path)
    if parent is None:
        directory,leaf=parent_path.rsplit('/',1)
        parent=tools.create_asset(leaf,directory,unreal.Material,unreal.MaterialFactoryNew())
    set_props(parent,{'two_sided':masked,'blend_mode':unreal.BlendMode.BLEND_MASKED if masked else unreal.BlendMode.BLEND_OPAQUE,
                      'used_with_nanite':True,'used_with_instanced_static_meshes':True,'used_with_static_lighting':False})
    unreal.MaterialEditingLibrary.recompile_material(parent)
    unreal.MaterialEditingLibrary.set_material_instance_parent(material,parent)
    eal.save_loaded_asset(parent);eal.save_loaded_asset(material)
    return material


if digest(SOURCE)!=EXPECTED:raise RuntimeError('Frozen pine GLB changed')
OUT.mkdir(parents=True,exist_ok=True)
materials={name:native_material(path,name=='MI_Branch_Mat') for name,path in BINDINGS.items()}

# UE5.5's glTF parser silently drops TEXCOORD_2. Decode the frozen GLB
# explicitly and feed the attribute-preserving MeshDescription builder.
raw=SOURCE.read_bytes()
magic,version,length=struct.unpack_from('<4sII',raw)
if magic!=b'glTF' or version!=2 or length!=len(raw):raise RuntimeError('Invalid GLB')
pos=12;doc=None;binary=None
while pos<len(raw):
    size,kind=struct.unpack_from('<II',raw,pos);pos+=8
    payload=raw[pos:pos+size];pos+=size
    if kind==0x4e4f534a:doc=json.loads(payload)
    elif kind==0x004e4942:binary=payload
if doc is None or binary is None:raise RuntimeError('Missing GLB chunks')

def accessor(index):
    a=doc['accessors'][index];view=doc['bufferViews'][a['bufferView']]
    if 'sparse' in a or view.get('buffer',0)!=0:raise RuntimeError('Unsupported source accessor')
    fmt,denominator={5121:('B',255),5123:('H',65535),5125:('I',4294967295),5126:('f',1)}[a['componentType']]
    width={'SCALAR':1,'VEC2':2,'VEC3':3,'VEC4':4}[a['type']]
    packing=struct.Struct('<'+fmt*width);stride=view.get('byteStride',packing.size)
    start=view.get('byteOffset',0)+a.get('byteOffset',0)
    rows=[packing.unpack_from(binary,start+i*stride) for i in range(a['count'])]
    if a.get('normalized'):rows=[tuple(v/denominator for v in row) for row in rows]
    return rows

positions=[];normals=[];indices=[];uvs=[];sections=[];colors=[]
source_triangles=0
for section,primitive in enumerate(doc['meshes'][0]['primitives']):
    attrs=primitive['attributes'];base=len(positions)
    vertices=accessor(attrs['POSITION']);ns=accessor(attrs['NORMAL']);cs=accessor(attrs['COLOR_0'])
    channels=[accessor(attrs['TEXCOORD_'+str(i)]) for i in range(3)]
    local=[row[0] for row in accessor(primitive['indices'])]
    # Swapping glTF Y/Z also changes handedness; Unreal clockwise indices
    # therefore use the original glTF counterclockwise order (no reversal).
    positions.extend(unreal.Vector(x*100,z*100,y*100) for x,y,z in vertices)
    normals.extend(unreal.Vector(x,z,y) for x,y,z in ns)
    # FColor's reflected positional constructor is BGRA. Name every channel
    # explicitly: native masks must retain the source RGBA byte order.
    for row in cs:
        r,g,b,a=(round(max(0,min(1,c))*255) for c in row)
        colors.append(unreal.Color(r=r,g=g,b=b,a=a))
    indices.extend(base+i for i in local)
    uvs.extend(unreal.Vector2D(*channel[i]) for i in local for channel in channels)
    sections.extend([section]*(len(local)//3));source_triangles+=len(local)//3
names=[doc['materials'][p['material']]['name'] for p in doc['meshes'][0]['primitives']]
if names!=list(BINDINGS):raise RuntimeError('Source material slots/order changed: '+str(names))
mesh=unreal.load_asset(FOLDER+'/'+NAME)
if mesh is None:mesh=tools.create_asset(NAME,FOLDER,unreal.StaticMesh,None)
if not unreal.MjolnirUIBuilderLibrary.build_attributed_static_mesh(mesh,positions,normals,indices,uvs,3,sections,names,colors):
    raise RuntimeError('Full attribute mesh build failed')
for index,name in enumerate(names):mesh.set_material(index,materials[name])
build=subsystem.get_lod_build_settings(mesh,0)
expected_build={'generate_lightmap_u_vs':False,'recompute_normals':False,'recompute_tangents':True,
                'use_full_precision_u_vs':True,'use_high_precision_tangent_basis':True,'remove_degenerates':False}
for key,value in expected_build.items():
    if build.get_editor_property(key)!=value:raise RuntimeError('Import build option was not preserved: '+key)
nanite=mesh.get_editor_property('nanite_settings')
set_props(nanite,{'enabled':True,'preserve_area':True,'explicit_tangents':True,'keep_percent_triangles':1.0,
                  'trim_relative_error':0.0,'position_precision':6,
                  'fallback_target':unreal.NaniteFallbackTarget.PERCENT_TRIANGLES,
                  'fallback_percent_triangles':1.0,'fallback_relative_error':0.0})
mesh.set_editor_property('nanite_settings',nanite)
mesh.set_editor_property('allow_cpu_access',True)
mesh.set_editor_property('has_navigation_data',False)
body=mesh.get_editor_property('body_setup')
body.set_editor_property('never_needs_cooked_collision_data',True)
body.set_editor_property('collision_trace_flag',unreal.CollisionTraceFlag.CTF_USE_SIMPLE_AS_COMPLEX)
instance=body.get_editor_property('default_instance')
instance.set_editor_property('collision_profile_name','NoCollision')
body.set_editor_property('default_instance',instance)
if subsystem.get_num_uv_channels(mesh,0)!=3:raise RuntimeError('Import lost native UV channels')
if not eal.save_loaded_asset(mesh):raise RuntimeError('Failed to save pine mesh')

label_name='PAL_MJOLNIR_PWR_MaturePine959'
label=unreal.load_asset(FOLDER+'/'+label_name)
if label is None:label=tools.create_asset(label_name,FOLDER,unreal.PrimaryAssetLabel,unreal.DataAssetFactory())
rules=label.get_editor_property('rules')
# Recursive labels participate in priority arbitration. UE5.5 processes
# nonrecursive labels last, which would also leave the HISM world owning this
# mesh. Native /Game/Env dependencies remain explicitly NeverCook.
set_props(rules,{'chunk_id':959,'priority':1000,'apply_recursively':True,'cook_rule':unreal.PrimaryAssetCookRule.ALWAYS_COOK})
set_props(label,{'rules':rules,'label_assets_in_my_directory':False,'explicit_assets':[mesh]})
eal.save_loaded_asset(label)
bounds=mesh.get_bounds();origin=bounds.origin;extent=bounds.box_extent
report={'schema':'pwr-native-pine-import-v1','source':str(SOURCE),'source_sha256':EXPECTED,'mesh':mesh.get_path_name(),
        'uv_channels':subsystem.get_num_uv_channels(mesh,0),'lod_count':subsystem.get_lod_count(mesh),
        'vertices':subsystem.get_number_verts(mesh,0),'source_triangles':source_triangles,
        'bounds_cm':[[origin.x-extent.x,origin.y-extent.y,origin.z-extent.z],
                     [origin.x+extent.x,origin.y+extent.y,origin.z+extent.z]],
        'materials':{name:materials[name].get_path_name() for name in names},
        'nanite':{key:nanite.get_editor_property(key) for key in ('enabled','preserve_area','explicit_tangents','keep_percent_triangles','trim_relative_error','position_precision','fallback_percent_triangles','fallback_relative_error')},
        'build':{key:build.get_editor_property(key) for key in ('generate_lightmap_u_vs','recompute_normals','recompute_tangents','use_full_precision_u_vs','use_high_precision_tangent_basis','remove_degenerates')},
        'chunk':959,'label_priority':1000,'placeholder_materials_ship':False,
        'color_policy':'glTF RGBA quantized to original FColor data bytes, FromSRGBColor counterconversion then native FColor; cooked byte audit required',
        'runtime_collision':'none; Blam trunk hulls authored separately','runtime_wpo':'HISM disabled by existing foliage bake',
        'script_sha256':digest(__file__),'status':'editor_imported_cook_and_native_readback_pending'}
if digest(SOURCE)!=EXPECTED:raise RuntimeError('Pine input changed during import')
(OUT/'editor-import.receipt.json').write_text(json.dumps(report,indent=2)+'\n')
unreal.log('MJOLNIR PWR mature pine: '+json.dumps(report))
