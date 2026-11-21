"""Isolated Blender MCP geometry review; native material appearance is pending."""
from pathlib import Path
import json
import math
import sys
import bpy
import numpy as np
from mathutils import Vector

ROOT=Path(__file__).resolve().parents[3]
OUT=ROOT/'out/pwr/visual-v5/base-paving'
sys.path.insert(0,str(ROOT/'tools/level'))
from heightfield import load_heightfield,sha256

source=ROOT/'out/pwr/visual-v5/apron-v2/apron-v2-preview.blend'
if bpy.data.is_dirty:
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'before-paving-preview.blend'),copy=True)
if bpy.data.filepath and Path(bpy.data.filepath).resolve()==source.resolve():
    raise RuntimeError('Preserve the source scene under another path before appending it')
with bpy.data.libraries.load(str(source),link=False) as (available,loaded):
    loaded.scenes=[next(name for name in available.scenes if 'Apron V2' in name)]
scene=loaded.scenes[0];scene.name='PWR Base Paving Isolated Review';bpy.context.window.scene=scene
receipt=json.loads((OUT/'receipt.json').read_text())
field=load_heightfield(ROOT/'levels/warfare/pwr/terrain/runtime-v5/runtime-master.json')
if receipt['master_sha256']!=field.manifest_sha256:raise ValueError('Paving source is stale')
geometry=json.loads((ROOT/'levels/warfare/pwr/terrain/final-v5/terrain.geometry.json').read_text())
sites={s['id']:s for s in geometry['sites'] if s['id'] in ('red_home','blue_home','citadel_plateau')}
for ob in scene.objects:
    if ob.type=='MESH' and ('heightfield' in ob.name.lower() or 'apron v2' in ob.name.lower()):ob.hide_render=True


def mat(name,color,metallic=.35,roughness=.65):
    m=bpy.data.materials.new(name);m.use_nodes=True
    bs=m.node_tree.nodes.get('Principled BSDF');bs.inputs['Base Color'].default_value=(*color,1)
    bs.inputs['Metallic'].default_value=metallic;bs.inputs['Roughness'].default_value=roughness
    return m


def mesh(name,v,t,material):
    data=bpy.data.meshes.new(name);data.from_pydata(v.tolist(),[],t.tolist());data.update()
    ob=bpy.data.objects.new(name,data);scene.collection.objects.link(ob);data.materials.append(material)
    return ob


paving=[mat('Native B Mid alloy approximation',(.28,.32,.33)),mat('Native C Dark joints approximation',(.08,.105,.12))]
ground=mat('Exact runtime terrain review',(.16,.215,.075),0,.95)
for name,site in sites.items():
    cx,cy=site['position_m'][:2]
    ox,oy=field.origin_m;dx,dy=field.spacing_m
    i0=max(0,int((cx-270-ox)//dx));i1=min(field.dimensions[0]-1,int((cx+270-ox)//dx)+1)
    j0=max(0,int((cy-270-oy)//dy));j1=min(field.dimensions[1]-1,int((cy+270-oy)//dy)+1)
    xx,yy=np.meshgrid(ox+np.arange(i0,i1+1)*dx,oy+np.arange(j0,j1+1)*dy)
    z=field.heights_m[j0:j1+1,i0:i1+1];v=np.c_[xx.ravel(),yy.ravel(),z.ravel()]
    w=xx.shape[1];j,i=np.mgrid[:xx.shape[0]-1,:xx.shape[1]-1];a=(j*w+i).ravel()
    t=np.concatenate([np.c_[a,a+1,a+w],np.c_[a+w+1,a+w,a+1]])
    ob=mesh(name+' exact runtime ground',v,t,ground)
    colors=ob.data.color_attributes.new(name='ground_review',type='FLOAT_COLOR',domain='POINT')
    road=field.sample_mask('road',xx,yy).ravel()
    base=np.array([.16,.215,.075])*(1-road[:,None])+np.array([.31,.265,.20])*road[:,None]
    colors.data.foreach_set('color',np.c_[base,np.ones(len(v))].ravel())
    own=ground.copy();ob.data.materials[0]=own
    attribute=own.node_tree.nodes.new('ShaderNodeVertexColor');attribute.layer_name='ground_review'
    own.node_tree.links.new(attribute.outputs['Color'],own.node_tree.nodes['Principled BSDF'].inputs['Base Color'])
for part in receipt['parts']:
    path=OUT/part['mesh_file']
    if sha256(path)!=receipt['files'][path.name]:raise ValueError('Changed paving mesh')
    data=np.load(path);ob=mesh(part['id'],data['vertices_m'],data['triangles'],paving[part['material_slot']])
    ob['render_only']=True;ob['native_collision']=False;ob['lift_m']=receipt['lift_m']

# Exact PCG positions with explicitly approximate silhouettes, so the three
# review exclusions are visible without pretending to render native foliage.
tree_mat=mat('PCG positions - approximate pine crowns',(.025,.09,.045),0,.9)
trees=json.loads((ROOT/'out/pwr/pcg-v5/trees.selected.json').read_text())['instances']
for tree in trees:
    x,y,z=tree['position']
    if min(math.hypot(x-s['position_m'][0],y-s['position_m'][1]) for s in sites.values())>205:continue
    height=(2.11 if tree.get('recipe')=='Pine_Sapling_A' else 21.5)*tree['scale']
    bpy.ops.mesh.primitive_cone_add(vertices=7,radius1=height*.14,radius2=0,depth=height*.85,location=(x,y,z+height*.57))
    ob=bpy.context.object;ob.name='PCG pine position '+str(tree['id']);ob.data.materials.append(tree_mat)

world=bpy.data.worlds.new('Paving review daylight');world.use_nodes=True;scene.world=world
world.node_tree.nodes['Background'].inputs['Color'].default_value=(.22,.30,.43,1)
world.node_tree.nodes['Background'].inputs['Strength'].default_value=.45
for ob in scene.objects:
    if ob.type=='LIGHT':ob.hide_render=True
sun=bpy.data.lights.new('Paving inspection sun','SUN');sun.energy=2.3;sun.angle=math.radians(1.5)
lamp=bpy.data.objects.new('Paving inspection sun',sun);scene.collection.objects.link(lamp)
lamp.rotation_euler=(math.radians(33),math.radians(-25),math.radians(-30))
scene.render.engine='CYCLES';scene.cycles.samples=24;scene.cycles.use_denoising=True
scene.render.resolution_x=1600;scene.render.resolution_y=1150;scene.render.resolution_percentage=100
scene.view_settings.view_transform='AgX';scene.view_settings.exposure=0
scene.render.image_settings.file_format='PNG';scene['preview_only']=True
camera=scene.camera;camera.data.type='ORTHO';camera.data.clip_end=10000
for name,view in [('red_home','oblique'),('red_home','topdown'),('citadel_plateau','topdown')]:
    center=Vector(sites[name]['position_m'])
    if view=='oblique':
        camera.location=center+Vector((230,-310,280));target=center+Vector((0,0,10));camera.data.ortho_scale=365
    else:
        camera.location=center+Vector((0,0,500));target=center;camera.data.ortho_scale=370 if name=='red_home' else 490
    camera.rotation_euler=(target-camera.location).to_track_quat('-Z','Y').to_euler()
    scene.render.filepath=str(OUT/(name+'-'+view+'.png'))
    bpy.ops.render.render(write_still=True)
bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'base-paving-preview.blend'))
(OUT/'preview.receipt.json').write_text(json.dumps({'status':'Blender geometry review, not native game proof',
    'master_sha256':field.manifest_sha256,'geometry_receipt_sha256':sha256(OUT/'receipt.json'),
    'material_appearance':'Approximate solid metal; native material references verified but not rendered by Blender',
    'vegetation':'Actual PCG positions, approximate pine silhouettes',
    'images':['red_home-oblique.png','red_home-topdown.png','citadel_plateau-topdown.png']},indent=2)+'\n')
print('Paving previews ready: '+str(OUT))
