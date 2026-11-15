"""Render the actual master heightfield and authored geometry through Blender MCP.

This is a terrain/architecture authoring preview, not an in-game screenshot.
"""
import argparse,json,math,sys
from pathlib import Path
import bpy
import numpy as np
from mathutils import Vector

ROOT=Path(__file__).resolve().parents[4]
sys.path[:0]=[str(ROOT/'tools/level'),str(ROOT/'levels/warfare/pwr')]
from heightfield import load_heightfield
from forerunner_kit import pieces
from forerunner_stock import placements
p=argparse.ArgumentParser();p.add_argument('--master',type=Path,required=True);p.add_argument('--geometry',type=Path,required=True)
p.add_argument('--out',type=Path,required=True);p.add_argument('--camera',default='overview',choices=['overview','topdown','base'])
a=p.parse_args(sys.argv[sys.argv.index('--')+1:]);a.out.mkdir(parents=True,exist_ok=True)
field=load_heightfield(a.master); geo=json.loads(a.geometry.read_text())
scene=bpy.context.scene
for obj in list(bpy.data.objects):bpy.data.objects.remove(obj,do_unlink=True)
scene.unit_settings.system='METRIC';scene.unit_settings.scale_length=1

def mat(name,color,roughness=.7,metallic=0):
    m=bpy.data.materials.new(name);m.diffuse_color=(*color,1);m.use_nodes=True
    bs=m.node_tree.nodes.get('Principled BSDF');bs.inputs['Base Color'].default_value=(*color,1)
    bs.inputs['Roughness'].default_value=roughness;bs.inputs['Metallic'].default_value=metallic
    return m
metal=mat('Forerunner weathered alloy',(.32,.37,.38),.43,.65)
floor=mat('Forerunner dark inset deck',(.16,.20,.21),.7,.4)
energy=mat('Forerunner azure energy',(.01,.25,.75),.25,.25)
bs=energy.node_tree.nodes.get('Principled BSDF');bs.inputs['Emission Color'].default_value=(.015,.3,1,1);bs.inputs['Emission Strength'].default_value=4
water=mat('Alpine water',(.012,.19,.24),.17,.25)
water.node_tree.nodes.get('Principled BSDF').inputs['IOR'].default_value=1.333
terrainmat=mat('Master terrain surface',(.3,.4,.15))
nodes=terrainmat.node_tree.nodes;links=terrainmat.node_tree.links;bs=nodes.get('Principled BSDF')
attr=nodes.new('ShaderNodeVertexColor');attr.layer_name='surface';links.new(attr.outputs['Color'],bs.inputs['Base Color'])
noise=nodes.new('ShaderNodeTexNoise');noise.inputs['Scale'].default_value=3;noise.inputs['Detail'].default_value=3
coord=nodes.new('ShaderNodeTexCoord');links.new(coord.outputs['Object'],noise.inputs['Vector'])
bump=nodes.new('ShaderNodeBump');bump.inputs['Strength'].default_value=.18;bump.inputs['Distance'].default_value=.22
links.new(noise.outputs['Fac'],bump.inputs['Height']);links.new(bump.outputs['Normal'],bs.inputs['Normal'])

def mesh(name,verts,faces,material,smooth=False):
    m=bpy.data.meshes.new(name);m.from_pydata(verts,[],faces);m.update()
    obj=bpy.data.objects.new(name,m);scene.collection.objects.link(obj);m.materials.append(material)
    for poly in m.polygons:poly.use_smooth=smooth
    return obj

n=513;lo,hi=field.bounds_m;x=np.linspace(lo[0],hi[0],n);y=np.linspace(lo[1],hi[1],n)
xx,yy=np.meshgrid(x,y);zz=field.sample(xx,yy)
verts=np.stack((xx,yy,zz),axis=-1).reshape(-1,3)
faces=[(j*n+i,j*n+i+1,(j+1)*n+i+1,(j+1)*n+i) for j in range(n-1) for i in range(n-1)]
terrain=mesh('Actual master heightfield',verts.tolist(),faces,terrainmat,True)
gy,gx=np.gradient(zz,(hi[1]-lo[1])/(n-1),(hi[0]-lo[0])/(n-1));slope=np.hypot(gx,gy)
rock=np.clip((slope-.35)/.6,0,1);snow=np.clip((zz-295)/65,0,1)*(1-np.clip((slope-1)/1.2,0,1))
grass=np.zeros((*zz.shape,3))+[.23,.31,.095];stone=np.zeros_like(grass)+[.36,.38,.37]
colors=grass*(1-rock[...,None])+stone*rock[...,None];colors=colors*(1-snow[...,None])+np.array([.81,.86,.89])*snow[...,None]
road=field.sample_mask('road',xx,yy);colors=colors*(1-road[...,None])+np.array([.34,.27,.18])*road[...,None]
shore=field.sample_mask('shore',xx,yy)*.45;colors=colors*(1-shore[...,None])+np.array([.34,.33,.27])*shore[...,None]
rgba=np.concatenate((colors,np.ones((*zz.shape,1))),axis=-1).reshape(-1,4).astype(np.float32)
attr=terrain.data.color_attributes.new(name='surface',type='FLOAT_COLOR',domain='POINT');attr.data.foreach_set('color',rgba.ravel())
for lake in geo.get('lakes',[]):
    poly=[(v[0],v[1],lake['water_z_m']+.04) for v in lake['polygon_m']]
    mesh('Water '+lake.get('id','lake'),poly,[tuple(range(len(poly)))],water)
for stream in geo.get('watercourses',[]):
    line=np.asarray(stream['surface_centreline_m']);width=stream.get('channel_width_m',20)
    if not np.isscalar(width):width=float(np.mean(width))
    tangent=np.gradient(line[:,:2],axis=0);tangent/=np.maximum(np.linalg.norm(tangent,axis=1)[:,None],1e-6)
    normal=np.stack((-tangent[:,1],tangent[:,0]),axis=1)*width*.5
    left=line.copy();right=line.copy();left[:,:2]+=normal;right[:,:2]-=normal
    v=np.stack((left,right),axis=1).reshape(-1,3);v[:,2]+=.05
    mesh('River '+stream.get('id','main'),v.tolist(),[(2*i,2*i+1,2*i+3,2*i+2) for i in range(len(line)-1)],water,True)
for site in geo.get('sites',[]):
    name=site.get('id','site')
    if name not in ('red_home','blue_home','citadel_plateau'):continue
    for part in pieces(name,site['position_m'],citadel=name=='citadel_plateau'):
        if part['module'].startswith('blade_'):continue
        obj=mesh(part['name'],part['vertices_m'],part['faces'],{'metal':metal,'floor':floor,'energy':energy}[part['material']])
        bevel=obj.modifiers.new('Architectural edge highlights','BEVEL');bevel.width=.22;bevel.segments=2
        obj['collision_hull']=part['collision'];obj['original_module']=part['module']
stock_cache=ROOT/'out/pwr/architecture-stock'
stock_models=json.loads((stock_cache/'models.json').read_text())
for item in placements(geo):
    model=next(m for m in stock_models if m['path']==item['mesh'])
    before=set(bpy.data.objects);bpy.ops.import_scene.gltf(filepath=model['glb'])
    for obj in list(set(bpy.data.objects)-before):
        if obj.type!='MESH' or 'LOD1' in obj.name:
            bpy.data.objects.remove(obj,do_unlink=True);continue
        bpy.context.view_layer.objects.active=obj;obj.select_set(True)
        if obj.data.has_custom_normals:bpy.ops.mesh.customdata_custom_splitnormals_clear()
        obj.select_set(False)
        obj.name=item['id'];obj.location=np.asarray(item['pos'])*np.array([.01,-.01,.01])
        obj.rotation_mode='XYZ';obj.rotation_euler=(0,0,math.radians(-item['rot'][1]));obj.scale=item['scale']
        for index in range(len(obj.data.materials)):obj.data.materials[index]=metal
for bridge in [r for r in geo.get('roads',[]) if 'bridge' in r.get('id','')]:
    line=bridge.get('centreline_m',bridge.get('deck_centreline_m'))
    if not line:continue
    pts=np.asarray(line); tangent=pts[-1,:2]-pts[0,:2];tangent/=np.linalg.norm(tangent);norm=np.array([-tangent[1],tangent[0]])*12
    v=[]
    for dz in (-2,0):
        for end,side in ((pts[0],-1),(pts[0],1),(pts[-1],1),(pts[-1],-1)):
            v.append([*(end[:2]+norm*side),end[2]+dz])
    mesh('Bridge '+bridge.get('id','deck'),v,[(3,2,1,0),(4,5,6,7),(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7)],metal)
world=bpy.data.worlds.new('Clear alpine sky');scene.world=world;world.use_nodes=True
sky=world.node_tree.nodes.new('ShaderNodeTexSky')
sky_types={item.identifier for item in sky.bl_rna.properties['sky_type'].enum_items}
sky.sky_type='MULTIPLE_SCATTERING' if 'MULTIPLE_SCATTERING' in sky_types else 'NISHITA'
sky.sun_elevation=math.radians(38);sky.sun_rotation=math.radians(140)
world.node_tree.links.new(sky.outputs['Color'],world.node_tree.nodes['Background'].inputs['Color']);world.node_tree.nodes['Background'].inputs['Strength'].default_value=.22
sun=bpy.data.lights.new('Mountain sunlight','SUN');sun.energy=3;sun.angle=math.radians(4)
obj=bpy.data.objects.new('Mountain sunlight',sun);scene.collection.objects.link(obj);obj.rotation_euler=(math.radians(28),math.radians(-20),math.radians(-35))
cam=bpy.data.cameras.new('Terrain inspection');co=bpy.data.objects.new('Terrain inspection',cam);scene.collection.objects.link(co);scene.camera=co
cam.clip_start=1;cam.clip_end=20000
if a.camera=='topdown':co.location=(0,0,2500);target=(0,0,0);cam.type='ORTHO';cam.ortho_scale=3700
elif a.camera=='base':co.location=(-690,-480,230);target=(-400,250,145);cam.lens=28
else:co.location=(200,-2400,1850);target=(0,70,110);cam.lens=37
co.rotation_euler=(Vector(target)-co.location).to_track_quat('-Z','Y').to_euler()
scene.render.engine='CYCLES';scene.cycles.samples=32;scene.cycles.use_denoising=True
scene.render.resolution_x=1672;scene.render.resolution_y=941;scene.render.resolution_percentage=100
scene.view_settings.view_transform='AgX';scene.view_settings.exposure=-1.5;scene.render.image_settings.file_format='PNG'
scene['master_heightfield_sha256']=field.manifest_sha256;scene['preview_only']=True
bpy.ops.wm.save_as_mainfile(filepath=str(a.out/'pwr_world_preview.blend'))
scene.render.filepath=str(a.out/(a.camera+'.png'));bpy.ops.render.render(write_still=True)
(a.out/(a.camera+'.json')).write_text(json.dumps({'master_sha256':field.manifest_sha256,'camera':a.camera,'terrain_samples':n,'render':'Blender authoring preview, not in game'},indent=2))
print(scene.render.filepath)
