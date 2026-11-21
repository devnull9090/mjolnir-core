"""Blender MCP: inspect/bake the exact mature stock pine assembly in isolation."""
from pathlib import Path
import json,sys,math,struct
import bpy
import numpy as np
from mathutils import Matrix,Vector

ROOT=Path(__file__).resolve().parents[4];OUT=ROOT/'out/pwr/visual-v5/outcrops-v4/trees'
sys.path.insert(0,str(ROOT/'tools/level'))
from heightfield import sha256
source=json.loads((OUT/'source.json').read_text());recipe=source['recipe'];scale=28./source['source_height_m']
if not source.get('attributes_required'):raise RuntimeError('Re-extract classic native UV/color attributes before baking this asset')
if bpy.data.is_dirty:bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'before-conifer-review.blend'),copy=True)
scene=bpy.data.scenes.new('PWR Mature Native Conifer Review');bpy.context.window.scene=scene

def material(name,texture):
    result=bpy.data.materials.get(name) or bpy.data.materials.new(name);result.use_nodes=True
    bsdf=result.node_tree.nodes.get('Principled BSDF');bsdf.inputs['Roughness'].default_value=.8
    image=bpy.data.images.load(str(OUT/'assets'/texture),check_existing=True)
    sample=result.node_tree.nodes.new('ShaderNodeTexImage');sample.image=image
    result.node_tree.links.new(sample.outputs['Color'],bsdf.inputs['Base Color'])
    return result

bark=material('MI_Pine_Tree_Mat','bark-albedo.png')
needles=material('MI_Branch_Mat','needle-albedo.png')
models={};source_objects=[]
for index,entry in enumerate(source['assets']):
    selected=[];lod=entry['lods'][entry['selected_lod']];name=lod['name'];attributes=lod['native_attributes']
    if not attributes.get('decodedUvColorComplete'):raise RuntimeError('Unverified native attributes: '+name)
    raw=Path(entry['glb']).read_bytes();length=struct.unpack_from('<I',raw,12)[0]
    document=json.loads(raw[20:20+length]);binary=raw[28+length:]
    def accessor(i):
        a=document['accessors'][i];v=document['bufferViews'][a['bufferView']]
        dtype=np.dtype({5126:'<f4',5125:'<u4',5123:'<u2',5121:'u1'}[a['componentType']])
        columns={'SCALAR':1,'VEC2':2,'VEC3':3,'VEC4':4}[a['type']]
        array=np.ndarray((a['count'],columns),dtype=dtype,buffer=binary,
            offset=v.get('byteOffset',0)+a.get('byteOffset',0),strides=(v.get('byteStride',dtype.itemsize*columns),dtype.itemsize)).copy()
        if a.get('normalized'):array=array.astype(np.float32)/np.iinfo(dtype).max
        return array
    for primitive in document['meshes'][entry['selected_lod']]['primitives']:
        attrs=primitive['attributes'];positions=accessor(attrs['POSITION'])[:,[0,2,1]]*[1,-1,1]
        normals=accessor(attrs['NORMAL'])[:,[0,2,1]]*[1,-1,1];faces=accessor(primitive['indices']).reshape(-1,3)
        data=bpy.data.meshes.new(name);data.from_pydata(positions.tolist(),[],faces.tolist());data.update()
        loops=np.array([loop.vertex_index for loop in data.loops])
        for channel in range(attributes['nativeUvChannelCount']):
            uv=accessor(attrs['TEXCOORD_'+str(channel)]);uv[:,1]=1-uv[:,1]
            layer=data.uv_layers.new(name='UVMap' if channel==0 else 'UVMap.'+str(channel).zfill(3))
            layer.data.foreach_set('uv',uv[loops].ravel())
        if attributes['nativeColorVertexCount']:
            # The generic Blender importer stores BYTE_COLOR through sRGB,
            # corrupting native linear mask bytes. Start directly from the
            # original accessor in FLOAT_COLOR; never up-convert lost bytes.
            color=data.color_attributes.new(name='Color',type='FLOAT_COLOR',domain='POINT')
            color.data.foreach_set('color',accessor(attrs['COLOR_0']).ravel())
            data.color_attributes.active_color=color;data.color_attributes.render_color_index=0
        for poly in data.polygons:poly.use_smooth=True
        data.normals_split_custom_set_from_vertices(normals.tolist())
        data.materials.append(needles if 'Protoype_Branch' in entry['mesh'] else bark)
        selected.append((data,Matrix.Identity(4)))
    if not selected:raise RuntimeError('Native fallback mesh absent: '+name)
    models[entry['mesh']]=selected

collection=bpy.data.collections.new('Exact native Tree_Pine assembly');scene.collection.children.link(collection)
F=np.diag([1.,-1.,1.])
for i,part in enumerate(recipe['parts']):
    transform=Matrix.Translation(Vector(np.array(part['off'])*[.01,-.01,.01]*scale))@Matrix.Scale(scale,4)
    for mesh,basis in models[part['mesh']]:
        obj=bpy.data.objects.new(f'pine_bark_{i:03d}',mesh);collection.objects.link(obj);obj.matrix_world=transform@basis;source_objects.append(obj)
for i,leaf in enumerate(recipe['leaves']):
    transform=Matrix.Translation(Vector(np.array(leaf['off'])*[.01,-.01,.01]*scale))@Matrix((F@np.array(leaf['m']).T@F).tolist()).to_4x4()@Matrix.Scale(scale,4)
    for mesh,basis in models[recipe['leaf_mesh']]:
        obj=bpy.data.objects.new(f'pine_needles_{i:03d}',mesh);collection.objects.link(obj);obj.matrix_world=transform@basis;source_objects.append(obj)

# Bake this reviewed native assembly into one reusable two-slot tree. Original
# UVs, material assignments, geometry and per-part transforms are retained.
bpy.ops.object.select_all(action='DESELECT')
for obj in source_objects:obj.select_set(True)
bpy.context.view_layer.objects.active=source_objects[0]
bpy.ops.object.join();tree=bpy.context.view_layer.objects.active;tree.name='SM_PWR_MaturePine_A';tree.data.name='SM_PWR_MaturePine_A'
bpy.ops.object.transform_apply(location=False,rotation=True,scale=True)
# First bark piece's origin may have an offset; move origin to world root while
# preserving every world vertex. Root placement is authoring Z=0.
scene.cursor.location=(0,0,0);bpy.ops.object.origin_set(type='ORIGIN_CURSOR')
tree.data.validate();tree.data.update()
bpy.ops.export_scene.gltf(filepath=str(OUT/'mature-pine-a.glb'),export_format='GLB',use_selection=True,use_active_scene=True,export_apply=True,
    export_texcoords=True,export_vertex_color='ACTIVE',export_all_vertex_colors=True,export_attributes=True)
raw=(OUT/'mature-pine-a.glb').read_bytes();gltf=json.loads(raw[20:20+struct.unpack_from('<I',raw,12)[0]])
if len(gltf['meshes'])!=1 or {m['name'] for m in gltf['materials']}!={'MI_Pine_Tree_Mat','MI_Branch_Mat'}:
    raise RuntimeError('Isolated tree export contains unrelated geometry or materials')
expected_uv=max(e['lods'][e['selected_lod']]['native_attributes']['nativeUvChannelCount'] for e in source['assets'])
expected_attributes={'TEXCOORD_'+str(i) for i in range(expected_uv)}
if any(e['lods'][e['selected_lod']]['native_attributes']['nativeColorVertexCount'] for e in source['assets']):expected_attributes.add('COLOR_0')
for mesh in gltf['meshes']:
    for primitive in mesh['primitives']:
        if not expected_attributes.issubset(primitive['attributes']):raise RuntimeError('Assembled GLB lost native attributes')

floor_mesh=bpy.data.meshes.new('Review ground');floor_mesh.from_pydata([(-80,-60,-.02),(80,-60,-.02),(80,60,-.02),(-80,60,-.02)],[],[(0,1,2,3)])
floor=bpy.data.objects.new('Review ground',floor_mesh);scene.collection.objects.link(floor)
floor_mat=bpy.data.materials.new('Neutral soil');floor_mat.diffuse_color=(.22,.25,.18,1);floor.data.materials.append(floor_mat)
for i,(x,y,s) in enumerate(((-17,7,.85),(16,5,1.15),(-11,22,1.07),(10,25,.94))):
    clone=bpy.data.objects.new(f'Pine stand inspection {i}',tree.data);scene.collection.objects.link(clone)
    clone.location=(x,y,0);clone.scale=(s,s,s);clone.rotation_euler.z=i*1.47
world=bpy.data.worlds.new('Conifer daylight');world.use_nodes=True;world.node_tree.nodes['Background'].inputs['Color'].default_value=(.63,.75,.9,1);world.node_tree.nodes['Background'].inputs['Strength'].default_value=.5;scene.world=world
light_data=bpy.data.lights.new('Conifer sun','SUN');light_data.energy=3.;light_data.angle=.1
light=bpy.data.objects.new('Conifer sun',light_data);scene.collection.objects.link(light);light.rotation_euler=(.45,-.35,-.6)
camera_data=bpy.data.cameras.new('Conifer camera');camera=bpy.data.objects.new('Conifer camera',camera_data);scene.collection.objects.link(camera);scene.camera=camera
camera.location=(45,-65,32);camera.rotation_euler=(Vector((0,6,14))-camera.location).to_track_quat('-Z','Y').to_euler();camera_data.lens=48
scene.render.engine='CYCLES';scene.cycles.device='CPU';scene.cycles.samples=16;scene.cycles.use_denoising=True
scene.render.resolution_x=1400;scene.render.resolution_y=1000;scene.render.resolution_percentage=100
scene.render.filepath=str(OUT/'native-conifer-textured.png');bpy.ops.render.render(write_still=True)
bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'native-conifer-review.blend'))
positions=np.array([tree.matrix_world@v.co for v in tree.data.vertices]);triangles=sum(len(p.vertices)-2 for p in tree.data.polygons)
(OUT/'preview.receipt.json').write_text(json.dumps({'schema':'pwr-native-conifer-preview-v1','source_sha256':sha256(OUT/'source.json'),
    'model_sha256':sha256(OUT/'mature-pine-a.glb'),'triangles':triangles,'vertices':len(positions),
    'bounds_m':[positions.min(0).tolist(),positions.max(0).tolist()],
    'preserved_attribute_semantics':sorted(expected_attributes),
    'fidelity':'Actual native fallback geometry/UVs/recipe transforms and albedo; approximate Blender lighting/materials, no UE wind/layer simulation',
    'installed':False,'native_collision_pending':True},indent=2)+'\n')
print(str(OUT/'native-conifer-textured.png'))
