"""Isolated Blender MCP visual comparison; never an installed-game claim."""
from pathlib import Path
import json,math,struct,sys
import bpy
import numpy as np
from mathutils import Matrix,Vector

ROOT=Path(__file__).resolve().parents[4];BASE=ROOT/'out/pwr/visual-v8/foothills';OUT=Path(globals().get('PWR_PREVIEW_OUTPUT',BASE/'preview'));OUT.mkdir(exist_ok=True)
sys.path.insert(0,str(ROOT/'tools/level'))
from render_only_hism import matrix,digest
SOURCE=ROOT/'out/pwr/visual-v7/apron-cliffs/heroes/apron-cliff-pilot.blend'
SELECTED=Path(globals().get('PWR_PLACEMENTS_DIR',BASE/'selected'))
CLIFFS=SELECTED/'render-only-hism.json';PINES=SELECTED/'render-only-pines.json'
if bpy.data.is_dirty:bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'before-preview.blend'),copy=True)
if Path(bpy.data.filepath).resolve()==SOURCE.resolve():bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'workspace.blend'))
with bpy.data.libraries.load(str(SOURCE),link=False) as (source,target):
    target.scenes=[next(n for n in source.scenes if 'PWR exterior cliff pilot V7' in n)]
scene=target.scenes[0];scene.name='PWR V8 Foothills isolated actual-PCG comparison';bpy.context.window.scene=scene
rows=json.loads(CLIFFS.read_text())['instances'];trees=json.loads(PINES.read_text())['instances']
existing=[o for o in scene.objects if o.name.startswith('pwr_apron_cliff_')]
if len(existing)!=27:raise RuntimeError('Original hero source scene differs')
additions=bpy.data.collections.new('V8 69 fractured foothill additions');scene.collection.children.link(additions)
forest=bpy.data.collections.new('V8 600 exterior native conifers');scene.collection.children.link(forest)
granite=bpy.data.materials.new('V8 rough gray rock - approximate native shader');granite.use_nodes=True
granite.node_tree.nodes['Principled BSDF'].inputs['Base Color'].default_value=(.24,.27,.285,1)
granite.node_tree.nodes['Principled BSDF'].inputs['Roughness'].default_value=.85
leafmat=bpy.data.materials.new('Sapling foliage shape approximation');leafmat.diffuse_color=(.075,.13,.04,1)
barkmat=bpy.data.materials.new('Sapling bark approximation');barkmat.diffuse_color=(.15,.12,.08,1)

def accessor(doc,data,index):
    a=doc['accessors'][index];view=doc['bufferViews'][a['bufferView']];n={'SCALAR':1,'VEC3':3}[a['type']]
    dtype={5126:'<f4',5125:'<u4',5123:'<u2'}[a['componentType']];item=np.dtype(dtype).itemsize
    return np.ndarray((a['count'],n),dtype=dtype,buffer=data,offset=view.get('byteOffset',0)+a.get('byteOffset',0),strides=(view.get('byteStride',n*item),item))

models={};winding_repairs=[]
def native_mesh(path,name,is_tree=False):
    if name in models:return models[name]
    raw=path.read_bytes();size=struct.unpack_from('<I',raw,12)[0];doc=json.loads(raw[20:20+size]);data=raw[28+size:]
    vertices=[];triangles=[];normals=[];materials=[];offset=0
    for primitive in doc['meshes'][0]['primitives']:
        pos=accessor(doc,data,primitive['attributes']['POSITION'])[:,[0,2,1]]*[1,-1,1]
        normal=accessor(doc,data,primitive['attributes']['NORMAL'])[:,[0,2,1]]*[1,-1,1]
        local_tri=accessor(doc,data,primitive['indices']).reshape(-1,3)
        cross=np.cross(pos[local_tri[:,1]]-pos[local_tri[:,0]],pos[local_tri[:,2]]-pos[local_tri[:,0]])
        dots=np.einsum('ij,ij->i',cross,normal[local_tri].mean(axis=1))
        if (dots<0).mean()>.98:
            # The retained older Uluwatu inspection GLB predates the native-CW
            # exporter fix. Repair only preview triangle order; never the asset,
            # points, runtime placement or shipped native geometry.
            local_tri=local_tri[:,[0,2,1]];winding_repairs.append({'asset':str(path),'negative_fraction':float((dots<0).mean()),'preview_only':True})
        tri=local_tri+offset
        vertices.append(pos);normals.append(normal);triangles.append(tri);materials.extend([primitive.get('material',0)]*len(tri));offset+=len(pos)
    mesh=bpy.data.meshes.new(name+' actual native triangles');mesh.from_pydata(np.concatenate(vertices).tolist(),[],np.concatenate(triangles).tolist());mesh.update()
    for polygon in mesh.polygons:polygon.use_smooth=True
    mesh.normals_split_custom_set_from_vertices(np.concatenate(normals).tolist())
    if is_tree:
        mesh.materials.append(barkmat);mesh.materials.append(leafmat);mesh.polygons.foreach_set('material_index',materials)
    else:mesh.materials.append(granite)
    models[name]=mesh;return mesh

flip=np.diag([1.,-1.,1.])
def place(row,data,collection):
    ob=bpy.data.objects.new(row['id'],data);collection.objects.link(ob)
    rotation=flip@np.asarray(matrix(row['rotation_xyzw']))@flip
    ob.matrix_world=Matrix.Translation(Vector(np.asarray(row['position_cm'])*[.01,-.01,.01]))@Matrix(rotation.tolist()).to_4x4()@Matrix.Diagonal((*row['scale'],1))

for row in rows[27:]:
    leaf=row['mesh'].split('.')[-1]
    path=(ROOT/'out/pwr/visual-v4/assets' if 'Uluwatu' in leaf else ROOT/'out/pwr/visual-v7/apron-cliffs/heroes/assets')/(leaf+'.glb')
    place(row,native_mesh(path,leaf),additions)
tree_source=ROOT/'out/pwr/visual-v5/outcrops-v4/trees/native-conifer-review.blend'
with bpy.data.libraries.load(str(tree_source),link=False) as (source,target):target.objects=[next(n for n in source.objects if n=='SM_PWR_MaturePine_A')]
mature=target.objects[0].data
sapling=native_mesh(ROOT/'out/pwr-research/nanite/SM_Tree_Pine_Sapling_A.glb','Native sapling',True)
for row in trees:place(row,mature if 'SM_PWR_MaturePine_A' in row['mesh'] else sapling,forest)
scene.render.engine='CYCLES';scene.cycles.device='GPU';scene.cycles.samples=12;scene.cycles.use_denoising=True
prefs=bpy.context.preferences.addons['cycles'].preferences;prefs.compute_device_type='OPTIX';prefs.get_devices()
for device in prefs.devices:device.use=device.type=='OPTIX'
scene.render.resolution_x=1600;scene.render.resolution_y=900;scene.render.resolution_percentage=100
scene.view_layers[0].material_override=None
camera=scene.camera;camera.data.type='PERSP';camera.data.clip_end=20000;camera.data.angle=math.radians(65)
views=[('valley',(150,-1350,520),(0,650,260)),('target',(0,-1450,2000),(0,-1450+2000/math.tan(math.radians(58)),0)),
       ('east',(650,100,450),(1530,650,410)),('north',(0,700,420),(100,1680,360))]
images=[]
for name,origin,target in views:
    camera.location=origin;camera.rotation_euler=(Vector(target)-camera.location).to_track_quat('-Z','Y').to_euler()
    for visible in (False,True):
        additions.hide_render=not visible;forest.hide_render=not visible
        image=name+('-after.png' if visible else '-before.png');scene.render.filepath=str(OUT/image)
        bpy.ops.render.render(write_still=True);images.append(image)
additions.hide_render=False;forest.hide_render=False
bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'foothills-v8.blend'))
(OUT/'receipt.json').write_text(json.dumps({'schema':'pwr-v8-foothill-preview-v1','cliffs_sha256':digest(CLIFFS),'pines_sha256':digest(PINES),
    'source_scene_sha256':digest(SOURCE),'preserved_hero_objects':len(existing),'added_cliffs':69,'added_trees':600,
    'images':images,'preview_winding_repairs':winding_repairs,'actual_game_proof':False,'materials':'Approximate rock/terrain/sapling. Mature pine native UV/albedo, approximate lighting.'},indent=2)+'\n')
print('V8 PREVIEW COMPLETE: '+str(OUT))
