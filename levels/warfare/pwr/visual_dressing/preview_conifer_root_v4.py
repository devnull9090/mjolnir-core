"""CPU-only contact preview at the exact proposed lowest-point root placement."""
from pathlib import Path
import json
import bpy
from mathutils import Vector

ROOT=Path(__file__).resolve().parents[4]
OUT=ROOT/'out/pwr/visual-v5/outcrops-v4/trees'
scene=bpy.context.scene
if not scene.name.startswith('PWR Mature Native Conifer Review'):
    raise ValueError('Select the reviewed isolated conifer scene first')
receipt=json.loads((OUT/'preview.receipt.json').read_text())
minimum=receipt['bounds_m'][0][2]
trees=[obj for obj in scene.objects if obj.type=='MESH' and
       any(m and m.name=='MI_Pine_Tree_Mat' for m in obj.data.materials)]
if len(trees)!=5:raise ValueError('Expected exactly the five reviewed tree instances')
for obj in trees:obj.location.z=-minimum*obj.scale.z
scene.cycles.device='CPU';scene.cycles.samples=16
camera=scene.camera
scene.render.filepath=str(OUT/'native-conifer-root-placement.png')
bpy.ops.render.render(write_still=True)
camera.location=(9,-12,5);camera.rotation_euler=(Vector((0,0,2.0))-camera.location).to_track_quat('-Z','Y').to_euler()
camera.data.lens=60
scene.render.filepath=str(OUT/'native-conifer-root-contact.png')
bpy.ops.render.render(write_still=True)
(OUT/'root-contact.receipt.json').write_text(json.dumps({'schema':'pwr-conifer-root-contact-v1',
    'source_geometry_sha256':receipt['model_sha256'],'native_origin_lift_m':-minimum,
    'placement':'Exact same minimum-bound root correction as authored_decor.expand_background_trees',
    'instance_locations':[{'name':obj.name,'location':list(obj.location),'scale':list(obj.scale)} for obj in trees],
    'geometry_unchanged':True,'material_lighting':'Blender approximation; native UE render pending'},indent=2)+'\n')
print(str(OUT/'native-conifer-root-contact.png'))
