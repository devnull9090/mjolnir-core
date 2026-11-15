"""Blender MCP authoring preview only, with the preserved scene and original Gaea apron."""
from pathlib import Path
import sys
import json
import math
import bpy
import numpy as np
from mathutils import Vector

ROOT = Path(__file__).resolve().parents[4]
OUT = ROOT/'out/pwr/visual-v5/apron-v3'
OUT.mkdir(parents=True, exist_ok=True)
if bpy.data.is_dirty:
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'before-apron-preview.blend'), copy=True)
sys.path.insert(0, str(Path(__file__).parent))
import build_apron_v3
import importlib
import build_apron_v2
importlib.reload(build_apron_v2)
importlib.reload(build_apron_v3)
build_apron_v3.build(ROOT/'levels/warfare/pwr/terrain/runtime-v5/runtime-master.json',
                    ROOT/'levels/warfare/pwr/terrain/gaea-v5c/source.json', OUT)
previous = ROOT/'out/pwr/world-v5/constrained-preview/pwr_world_preview.blend'
if bpy.data.filepath and Path(bpy.data.filepath).resolve() == previous.resolve():
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'before-apron-preview.blend'))
with bpy.data.libraries.load(str(previous), link=False) as (source, target):
    target.scenes = [source.scenes[0]]
scene = target.scenes[0]
scene.name = 'PWR Apron V3 Isolated Authoring Preview'
bpy.context.window.scene = scene
arrays = np.load(OUT/'apron.source.npz')
v, tri, n = arrays['vertices_m'], arrays['triangles'], arrays['normals']
mesh = bpy.data.meshes.new('Thin-plate joined continuous Gaea relief')
mesh.from_pydata(v.tolist(), [], tri.tolist()); mesh.update()
ob = bpy.data.objects.new('Gaea Apron V3 - Render Only', mesh)
scene.collection.objects.link(ob)
for face in mesh.polygons:
    face.use_smooth = True
mesh.normals_split_custom_set_from_vertices(n.tolist())
colors = mesh.color_attributes.new(name='apron_preview', type='FLOAT_COLOR', domain='POINT')
snow = np.clip((v[:, 2]-470)/240, 0, 1)*(np.clip((n[:, 2]-.38)/.42, 0, 1))
grass = np.clip((230-v[:, 2])/130, 0, 1)*np.clip((n[:, 2]-.6)/.35, 0, 1)
rock = np.tile([.20, .23, .245], (len(v), 1))
rock = rock*(1-grass[:, None]) + np.array([.18, .235, .09])*grass[:, None]
rgba = np.c_[rock*(1-snow[:, None])+np.array([.77, .80, .83])*snow[:, None], np.ones(len(v))]
colors.data.foreach_set('color', rgba.ravel())
material = bpy.data.materials.new('Apron shape inspection only - native materials pending')
material.use_nodes = True
nodes, links = material.node_tree.nodes, material.node_tree.links
attr = nodes.new('ShaderNodeVertexColor'); attr.layer_name = 'apron_preview'
links.new(attr.outputs['Color'], nodes['Principled BSDF'].inputs['Base Color'])
nodes['Principled BSDF'].inputs['Roughness'].default_value = .85
mesh.materials.append(material)
world = bpy.data.worlds.new('Neutral apron inspection daylight')
world.use_nodes = True
world.node_tree.nodes['Background'].inputs['Color'].default_value = (.22, .30, .43, 1)
world.node_tree.nodes['Background'].inputs['Strength'].default_value = .45
scene.world = world
for old in list(scene.objects):
    if old.type == 'LIGHT':
        bpy.data.objects.remove(old, do_unlink=True)
sun = bpy.data.lights.new('Apron inspection sun', 'SUN'); sun.energy = 2.3
sun.angle = math.radians(1.5)
lamp = bpy.data.objects.new('Apron inspection sun', sun); scene.collection.objects.link(lamp)
lamp.rotation_euler = (math.radians(33), math.radians(-25), math.radians(-30))
scene.render.engine = 'CYCLES'; scene.cycles.samples = 24
scene.cycles.use_denoising = True
scene.render.resolution_x = 1672; scene.render.resolution_y = 941
scene.render.resolution_percentage = 100
scene.view_settings.exposure = 0
scene['preview_only'] = True
scene['apron_source'] = 'Accepted native Gaea v5c, continuous scaled field; no synthesized mounds'
camera = scene.camera
camera.data.type = 'PERSP'; camera.data.lens = 25; camera.data.clip_end = 20000
camera.location = (150, -1350, 520)
camera.rotation_euler = (Vector((0, 650, 260))-camera.location).to_track_quat('-Z', 'Y').to_euler()
scene.render.filepath = str(OUT/'valley-preview.png')
bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'apron-v3-preview.blend'))
bpy.ops.render.render(write_still=True)
camera.location = (0, -1450, 2000)
camera.data.angle = math.radians(65)
camera.rotation_euler = (Vector((0, -1450 + 2000 / math.tan(math.radians(58)), 0))-camera.location).to_track_quat('-Z', 'Y').to_euler()
scene.render.filepath = str(OUT/'target-preview.png')
bpy.ops.render.render(write_still=True)
clay = bpy.data.materials.new('Uniform clay - geometry comparison only')
clay.diffuse_color = (.33, .37, .39, 1)
clay.use_nodes = True
clay.node_tree.nodes['Principled BSDF'].inputs['Base Color'].default_value = (.33, .37, .39, 1)
clay.node_tree.nodes['Principled BSDF'].inputs['Roughness'].default_value = .9
scene.view_layers[0].material_override = clay
camera.location = (1650, -1450, 1000)
camera.data.angle = math.radians(65)
camera.rotation_euler = (Vector((450, 250, 170))-camera.location).to_track_quat('-Z', 'Y').to_euler()
scene.render.filepath = str(OUT/'seam-after-clay.png')
bpy.ops.render.render(write_still=True)
old = np.load(ROOT/'out/pwr/visual-v5/apron-v2/apron.source.npz')
old_mesh = bpy.data.meshes.new('Apron V2 comparison only')
old_mesh.from_pydata(old['vertices_m'].tolist(), [], old['triangles'].tolist())
old_mesh.update()
for face in old_mesh.polygons:
    face.use_smooth=True
old_mesh.normals_split_custom_set_from_vertices(old['normals'].tolist())
ob.data=old_mesh
scene.render.filepath = str(OUT/'seam-before-clay.png')
bpy.ops.render.render(write_still=True)
ob.data=mesh
scene.view_layers[0].material_override = None
bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'apron-v3-preview.blend'))
(OUT/'preview.receipt.json').write_text(json.dumps({'status': 'Blender approximation, not game proof',
    'geometry_receipt_sha256': build_apron_v3.sha256(OUT/'receipt.json'),
    'existing_scene': str(previous), 'existing_scene_sha256': build_apron_v3.sha256(previous),
    'images': ['valley-preview.png', 'target-preview.png', 'seam-before-clay.png', 'seam-after-clay.png'],
    'comparison': 'Identical camera, uniform material, lighting and preserved playable scene; only apron geometry differs',
    'native_materials': False, 'installed': False}, indent=2)+'\n')
print(str(OUT/'valley-preview.png'))
