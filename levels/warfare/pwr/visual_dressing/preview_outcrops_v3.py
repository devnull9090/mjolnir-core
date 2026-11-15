"""Lightweight isolated Blender MCP pilot; exact stock meshes/poses, approximate material."""
from pathlib import Path
import sys,json,math
import bpy
import numpy as np
from mathutils import Matrix,Vector

ROOT=Path(__file__).resolve().parents[4]
OUT=ROOT/'out/pwr/visual-v5/outcrops-v3'
FULL=bool(globals().get('PWR_FULL',False))
stem='combined' if FULL else 'lake'
sys.path.insert(0,str(ROOT/'tools/level'))
import b30_collision
from heightfield import load_heightfield,sha256
if bpy.data.is_dirty:bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'before-pilot.blend'),copy=True)
previous=ROOT/'out/pwr/visual-v5/apron-v3/apron-v3-preview.blend'
if bpy.data.filepath and Path(bpy.data.filepath).resolve()==previous.resolve():
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'before-pilot.blend'))
with bpy.data.libraries.load(str(previous),link=False) as (source,target):
    target.scenes=[next(x for x in source.scenes if 'Apron V3' in x)]
scene=target.scenes[0];scene.name='PWR Fractured Banks and Ridges' if FULL else 'PWR Fractured Lake Bank Pilot';bpy.context.window.scene=scene
field=load_heightfield(ROOT/'levels/warfare/pwr/terrain/runtime-v5/runtime-master.json')
proposal_path=OUT/('outcrops.authored-decor.json' if FULL else 'pilot.json')
proposal=json.loads(proposal_path.read_text())
assert proposal.get('runtime_master_sha256',proposal.get('visual_v4_provenance',{}).get('frozen_runtime_master_sha256'))==field.manifest_sha256
material=bpy.data.materials.new('Native granite geometry inspection only')
material.use_nodes=True
material.node_tree.nodes['Principled BSDF'].inputs['Base Color'].default_value=(.30,.32,.33,1)
material.node_tree.nodes['Principled BSDF'].inputs['Roughness'].default_value=.85
templates={}


def template(leaf):
    if leaf in templates:return templates[leaf]
    path=OUT/'assets'/(leaf+'.glb')
    if not path.is_file():path=ROOT/'out/pwr/visual-v4/assets'/(leaf+'.glb')
    old=set(bpy.data.objects);bpy.ops.import_scene.gltf(filepath=str(path));created=set(bpy.data.objects)-old
    meshes=[]
    for obj in created:
        if obj.type!='MESH' or any('LOD'+str(n) in obj.name for n in range(1,10)):continue
        bpy.context.view_layer.objects.active=obj;obj.select_set(True)
        if obj.data.has_custom_normals:bpy.ops.mesh.customdata_custom_splitnormals_clear()
        obj.select_set(False)
        obj.data.materials.clear();obj.data.materials.append(material)
        for poly in obj.data.polygons:poly.material_index=0
        meshes.append((obj.data,obj.matrix_world.copy()))
    for obj in created:bpy.data.objects.remove(obj,do_unlink=True)
    templates[leaf]=meshes;return meshes


collection=bpy.data.collections.new('New bank cliff pilot');scene.collection.children.link(collection)
flip=np.diag([1.,-1.,1.])
for row in proposal['decor']:
    rotation=flip@b30_collision.rotator_matrix(*row['rot']).T@flip
    transform=Matrix.Translation(Vector(np.array(row['pos'])*[.01,-.01,.01]))@Matrix(rotation.tolist()).to_4x4()@Matrix.Diagonal((*row['scale'],1))
    for mesh,basis in template(row['mesh'].split('.')[-1]):
        obj=bpy.data.objects.new(row['id'],mesh);collection.objects.link(obj);obj.matrix_world=transform@basis

# Use exact native/render triangles for the local inspection patch instead of
# the old513x513 overview approximation. This prevents false contact gaps.
for obj in list(scene.objects):
    if obj.name.startswith('Actual master heightfield'):
        original_material=obj.data.materials[0]
        obj.hide_render=True
        break
ix=np.arange(1009) if FULL else np.arange(600,951);iy=np.arange(1009) if FULL else np.arange(110,410)
xx,yy=np.meshgrid(-1000+ix*field.spacing_m[0],-1000+iy*field.spacing_m[1])
zz=field.heights_m[np.ix_(iy,ix)];width=len(ix)
vertices=np.c_[xx.ravel(),yy.ravel(),zz.ravel()]
q=np.arange((len(iy)-1)*width).reshape(len(iy)-1,width)[:,:-1].ravel()
tri=np.vstack([np.c_[q,q+1,q+width],np.c_[q+1,q+width+1,q+width]])
mesh=bpy.data.meshes.new('Exact local runtime field')
mesh.from_pydata(vertices.tolist(),[],tri.tolist());mesh.update()
patch=bpy.data.objects.new('Exact native lake bank surface',mesh);scene.collection.objects.link(patch)
terrain_mat=bpy.data.materials.new('Bank inspection ground');terrain_mat.use_nodes=True
terrain_mat.node_tree.nodes['Principled BSDF'].inputs['Base Color'].default_value=(.24,.29,.15,1)
terrain_mat.node_tree.nodes['Principled BSDF'].inputs['Roughness'].default_value=.9
mesh.materials.append(terrain_mat)
for face in mesh.polygons:face.use_smooth=True
scene.render.engine='CYCLES';scene.cycles.device='CPU';scene.cycles.samples=4;scene.cycles.use_denoising=True
scene.render.resolution_x=1280;scene.render.resolution_y=720;scene.render.resolution_percentage=100
camera=scene.camera;camera.data.lens=26;camera.location=(510,-720,92)
camera.rotation_euler=(Vector((510,-430,91))-camera.location).to_track_quat('-Z','Y').to_euler()
collection.hide_render=True;scene.render.filepath=str(OUT/(stem+'-before.png'));bpy.ops.render.render(write_still=True)
collection.hide_render=False;scene.render.filepath=str(OUT/(stem+'-after.png'));bpy.ops.render.render(write_still=True)
camera.location=(810,-800,280);camera.data.lens=30
camera.rotation_euler=(Vector((500,-450,83))-camera.location).to_track_quat('-Z','Y').to_euler()
scene.render.filepath=str(OUT/(stem+'-overview.png'));bpy.ops.render.render(write_still=True)
if FULL:
    camera.location=(-360,390,350);camera.data.lens=30
    camera.rotation_euler=(Vector((-650,660,250))-camera.location).to_track_quat('-Z','Y').to_euler()
    scene.render.filepath=str(OUT/'combined-ridge.png');bpy.ops.render.render(write_still=True)
bpy.ops.wm.save_as_mainfile(filepath=str(OUT/(stem+'-assembly.blend')))
(OUT/(stem+'-preview.receipt.json')).write_text(json.dumps({'schema':'pwr-scarp-pilot-preview-v1',
    'proposal_sha256':sha256(proposal_path),'runtime_master_sha256':field.manifest_sha256,
    'stock_meshes_and_transforms':True,'terrain_patch_uses_exact_runtime_grid_and_diagonal':True,
    'render':'Blender CPU4samples, approximate material; not game proof','installed':False,
    'images':[stem+'-before.png',stem+'-after.png',stem+'-overview.png']+(['combined-ridge.png'] if FULL else [])},indent=2)+'\n')
print(str(OUT/(stem+'-after.png')))
