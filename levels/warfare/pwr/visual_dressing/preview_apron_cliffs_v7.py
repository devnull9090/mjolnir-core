"""Run ONLY through the authorized Blender MCP lease; isolated visual candidate.

Uses exact prepared geometry and corrected native GLB extraction. Materials
are approximate inspection colors; images are never presented as game proof.
"""
from pathlib import Path
import json
import math
import struct
import sys
import bpy
import numpy as np
from mathutils import Matrix,Vector

ROOT=Path(__file__).resolve().parents[4]
BASE_OUT=ROOT/'out/pwr/visual-v7/apron-cliffs'
OUT=Path(globals().get('PWR_PILOT_DIR',BASE_OUT))
APRON=BASE_OUT/'apron'
sys.path.insert(0,str(ROOT/'tools/level'))
from heightfield import sha256
from render_only_hism import matrix
if bpy.data.is_dirty:bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'before-preview.blend'),copy=True)
previous=ROOT/'out/pwr/visual-v5/apron-v4/apron-v4-preview.blend'
with bpy.data.libraries.load(str(previous),link=False) as (source,target):
    target.scenes=[next(s for s in source.scenes if 'Apron V4' in s)]
scene=target.scenes[0];scene.name='PWR exterior cliff pilot V7';bpy.context.window.scene=scene
for obj in list(scene.objects):
    if 'Gaea Apron' in obj.name:scene.collection.objects.unlink(obj) if obj.name in scene.collection.objects else bpy.data.objects.remove(obj,do_unlink=True)
arrays=np.load(APRON/'apron.source.npz');v,t,n=arrays['vertices_m'],arrays['triangles'],arrays['normals']
mesh=bpy.data.meshes.new('Refined native Gaea/harmonic field')
mesh.from_pydata(v.tolist(),[],t.tolist());mesh.update()
ob=bpy.data.objects.new('Refined exterior apron - no native collision',mesh);scene.collection.objects.link(ob)
for face in mesh.polygons:face.use_smooth=True
mesh.normals_split_custom_set_from_vertices(n.tolist())
color=mesh.color_attributes.new(name='apron_shape',type='FLOAT_COLOR',domain='POINT')
snow=np.clip((v[:,2]-490)/260,0,1)*np.clip((n[:,2]-.38)/.42,0,1)
green=np.clip((250-v[:,2])/150,0,1)*np.clip((n[:,2]-.6)/.35,0,1)
rock=np.tile([.20,.23,.245],(len(v),1))*(1-green[:,None])+np.array([.18,.235,.09])*green[:,None]
rgba=np.c_[rock*(1-snow[:,None])+np.array([.77,.80,.83])*snow[:,None],np.ones(len(v))]
color.data.foreach_set('color',rgba.ravel())
mat=bpy.data.materials.new('Approximate apron geology - shape only');mat.use_nodes=True
node=mat.node_tree.nodes.new('ShaderNodeVertexColor');node.layer_name='apron_shape'
mat.node_tree.links.new(node.outputs['Color'],mat.node_tree.nodes['Principled BSDF'].inputs['Base Color'])
mat.node_tree.nodes['Principled BSDF'].inputs['Roughness'].default_value=.85;mesh.materials.append(mat)
granite=bpy.data.materials.new('Gray fractured native geometry - game material pending');granite.use_nodes=True
granite.node_tree.nodes['Principled BSDF'].inputs['Base Color'].default_value=(.24,.27,.285,1)
granite.node_tree.nodes['Principled BSDF'].inputs['Roughness'].default_value=.85


def accessor(doc,data,index):
    a=doc['accessors'][index];view=doc['bufferViews'][a['bufferView']]
    count={'SCALAR':1,'VEC3':3}[a['type']];dtype={5126:'<f4',5125:'<u4',5123:'<u2'}[a['componentType']]
    item=np.dtype(dtype).itemsize
    return np.ndarray((a['count'],count),dtype=dtype,buffer=data,
        offset=view.get('byteOffset',0)+a.get('byteOffset',0),strides=(view.get('byteStride',count*item),item))


templates={}
def native_mesh(leaf):
    if leaf in templates:return templates[leaf]
    raw=(OUT/'assets'/f'{leaf}.glb').read_bytes();size=struct.unpack_from('<I',raw,12)[0]
    doc=json.loads(raw[20:20+size]);data=raw[28+size:];vertices=[];triangles=[];normals=[];offset=0
    for p in doc['meshes'][0]['primitives']:
        pos=accessor(doc,data,p['attributes']['POSITION'])[:,[0,2,1]]*[1,-1,1]
        normal=accessor(doc,data,p['attributes']['NORMAL'])[:,[0,2,1]]*[1,-1,1]
        tri=accessor(doc,data,p['indices']).reshape(-1,3)+offset
        vertices.append(pos);normals.append(normal);triangles.append(tri);offset+=len(pos)
    result=bpy.data.meshes.new(leaf+' native LOD0')
    result.from_pydata(np.concatenate(vertices).tolist(),[],np.concatenate(triangles).tolist());result.update()
    for face in result.polygons:face.use_smooth=True
    result.normals_split_custom_set_from_vertices(np.concatenate(normals).tolist());result.materials.append(granite)
    templates[leaf]=result;return result


proposal_path=OUT/'render-only-hism.json'
if not proposal_path.is_file():proposal_path=OUT/'pilot.preview-transforms.json'
rows=json.loads(proposal_path.read_text())['instances']
collection=bpy.data.collections.new('24 exterior cliff pilot pieces');scene.collection.children.link(collection)
flip=np.diag([1.,-1.,1.])
for row in rows:
    obj=bpy.data.objects.new(row['id'],native_mesh(row['mesh'].split('.')[-1]));collection.objects.link(obj)
    rotation=flip@np.array(matrix(row['rotation_xyzw']))@flip
    obj.matrix_world=Matrix.Translation(Vector(np.array(row['position_cm'])*[.01,-.01,.01]))@Matrix(rotation.tolist()).to_4x4()@Matrix.Diagonal((*row['scale'],1))
scene.render.engine='CYCLES';scene.cycles.device='CPU';scene.cycles.samples=8;scene.cycles.use_denoising=True
scene.render.resolution_x=1440;scene.render.resolution_y=810;scene.render.resolution_percentage=100
scene.view_layers[0].material_override=None
camera=scene.camera;camera.data.type='PERSP';camera.data.clip_end=20000;camera.data.angle=math.radians(65)
plan=json.loads((OUT/'pilot.plan.json').read_text());images=[]
for ridge in plan['ridge_centres']:
    center=Vector(ridge['position_m']);inward=Vector((-center.x,-center.y,0)).normalized()
    camera.location=center+inward*300+Vector((0,0,85))
    camera.rotation_euler=(center-camera.location).to_track_quat('-Z','Y').to_euler()
    for shown in (False,True):
        collection.hide_render=not shown;name=ridge['id']+('-after.png' if shown else '-before.png')
        scene.render.filepath=str(OUT/name);bpy.ops.render.render(write_still=True);images.append(name)
collection.hide_render=False
camera.location=(150,-1350,520);camera.rotation_euler=(Vector((0,650,260))-camera.location).to_track_quat('-Z','Y').to_euler()
scene.render.filepath=str(OUT/'valley-pilot.png');bpy.ops.render.render(write_still=True);images.append('valley-pilot.png')
camera.location=(0,-1450,2000);camera.rotation_euler=(Vector((0,-1450+2000/math.tan(math.radians(58)),0))-camera.location).to_track_quat('-Z','Y').to_euler()
scene.render.filepath=str(OUT/'target-pilot.png');bpy.ops.render.render(write_still=True);images.append('target-pilot.png')
bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'apron-cliff-pilot.blend'))
(OUT/'preview.receipt.json').write_text(json.dumps({'schema':'pwr-apron-cliff-preview-v1',
    'geometry_receipt_sha256':sha256(APRON/'receipt.json'),'placements_sha256':sha256(proposal_path),
    'source_scene_sha256':sha256(previous),'images':images,'actual_game_proof':False,
    'materials':'Blender approximate inspection colors','installed':False},indent=2)+'\n')
