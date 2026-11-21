import bpy,json,math,sys
from pathlib import Path
from mathutils import Vector,Matrix
REPO=Path(__file__).resolve().parents[3]
ROOT=REPO/'out/pwr/visual-v4/base-details'
sys.path.insert(0,str(REPO/'levels/warfare/pwr'))
from forerunner_kit import pieces
from forerunner_stock import placements
proposal=json.loads((ROOT/'proposal.json').read_text())
geometry=json.loads((REPO/'levels/warfare/pwr/terrain/final-v3/terrain.geometry.json').read_text())
site=next(s for s in geometry['sites'] if s['id']=='red_home');centre=Vector(site['position_m'])
for ob in list(bpy.data.objects):bpy.data.objects.remove(ob,do_unlink=True)
scene=bpy.context.scene;scene.unit_settings.system='METRIC';scene.unit_settings.scale_length=1.0

def mat(name,color,metal=.4,rough=.5,emission=0):
    m=bpy.data.materials.new(name);m.use_nodes=True;b=m.node_tree.nodes.get('Principled BSDF')
    b.inputs['Base Color'].default_value=(*color,1);b.inputs['Metallic'].default_value=metal;b.inputs['Roughness'].default_value=rough
    if emission:b.inputs['Emission Color'].default_value=(*color,1);b.inputs['Emission Strength'].default_value=emission
    return m
mats={'floor':mat('Native metal preview - floor',(.11,.14,.16)),
      'metal':mat('Native metal preview - structure',(.25,.3,.33)),
      'energy':mat('Cyan channel',(.015,.55,1),.2,.3,5),
      'details':mat('Native detail preview alloy',(.28,.34,.38),.65,.38)}
for part in pieces('red_home',site['position_m']):
    if part['module'].startswith('blade_'):continue
    data=bpy.data.meshes.new(part['name']);data.from_pydata([Vector(p)-centre for p in part['vertices_m']],[],part['faces']);data.update()
    ob=bpy.data.objects.new(part['name'],data);scene.collection.objects.link(ob);data.materials.append(mats[part['material']])

templates={}
def template(path):
    if path in templates:return templates[path]
    before=set(bpy.data.objects);bpy.ops.import_scene.gltf(filepath=str(path))
    created=set(bpy.data.objects)-before
    result=[]
    for ob in created:
        if ob.type!='MESH' or any('LOD'+str(n) in ob.name for n in range(1,9)):continue
        bpy.context.view_layer.objects.active=ob;ob.select_set(True)
        if ob.data.has_custom_normals:bpy.ops.mesh.customdata_custom_splitnormals_clear()
        ob.select_set(False)
        for slot in range(len(ob.data.materials)):ob.data.materials[slot]=mats['details']
        result.append((ob.data,ob.matrix_world.copy()))
    for ob in created:bpy.data.objects.remove(ob,do_unlink=True)
    templates[path]=result;return result

def place(item,path):
    p=item['pos'];origin=Vector((p[0]/100,-p[1]/100,p[2]/100))-centre
    transform=Matrix.Translation(origin)@Matrix.Rotation(math.radians(-item['rot'][1]),4,'Z')@Matrix.Diagonal((*item['scale'],1))
    for i,(mesh,basis) in enumerate(template(path)):
        ob=bpy.data.objects.new(item['id']+f'_{i}',mesh);scene.collection.objects.link(ob);ob.matrix_world=transform@basis

stock=REPO/'out/pwr/architecture-stock/SM_FR_ACR_Ext_Canyon_B_Ziggurat_Pillar_w10_d40_h62_A.glb'
for item in placements(geometry):
    if item['id'].startswith('red_home_'):place(item,stock)
for item in proposal['items']:
    if item['site']=='red_home':place(item['decor'],Path(proposal['palette'][item['role']]['glb']))

bpy.ops.mesh.primitive_plane_add(size=350,location=(0,0,-.08));bpy.context.object.data.materials.append(mat('Terrace backdrop',(.10,.145,.055),0,.95))
world=bpy.data.worlds.new('Preview daylight');world.use_nodes=True;scene.world=world
world.node_tree.nodes['Background'].inputs['Color'].default_value=(.38,.5,.7,1);world.node_tree.nodes['Background'].inputs['Strength'].default_value=.45
sun=bpy.data.lights.new('KeySun','SUN');sun.energy=3;sun.angle=math.radians(1.2);ob=bpy.data.objects.new('KeySun',sun);scene.collection.objects.link(ob);ob.rotation_euler=(math.radians(28),math.radians(-20),math.radians(-25))
data=bpy.data.cameras.new('BaseDetail');cam=bpy.data.objects.new('BaseDetail',data);scene.collection.objects.link(cam);scene.camera=cam;data.clip_end=1000
cam.location=(145,-190,125);cam.rotation_euler=(Vector((0,0,18))-cam.location).to_track_quat('-Z','Y').to_euler();data.type='ORTHO';data.ortho_scale=235
scene.render.engine='CYCLES';scene.cycles.samples=32;scene.cycles.use_denoising=True
scene.render.resolution_x=1600;scene.render.resolution_y=1100;scene.render.resolution_percentage=100;scene.view_settings.view_transform='AgX';scene.view_settings.exposure=0
scene.render.filepath=str(ROOT/'assembly-preview.png');bpy.ops.wm.save_as_mainfile(filepath=str(ROOT/'assembly-preview.blend'));bpy.ops.render.render(write_still=True)
cam.location=(0,0,220);cam.rotation_euler=(0,0,0);data.ortho_scale=230;scene.render.filepath=str(ROOT/'assembly-topdown.png');bpy.ops.render.render(write_still=True)
print('Preview only: original module geometry, stock mesh geometry, approximation of native materials. '+str(ROOT/'assembly-preview.png'))
