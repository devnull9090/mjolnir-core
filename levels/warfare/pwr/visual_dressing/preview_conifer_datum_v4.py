"""CPU preview of approved soil datum; retain the rejected min-bound evidence."""
from pathlib import Path
import hashlib,json
import bpy
from mathutils import Vector
ROOT=Path(__file__).resolve().parents[4]
OUT=ROOT/'out/pwr/visual-v5/outcrops-v4/trees'
scene=bpy.context.scene
if not scene.name.startswith('PWR Mature Native Conifer Review'):raise ValueError('Wrong isolated scene')
recipe=json.loads((OUT/'recipes.json').read_text())['PWR_MaturePine_A']
trees=[obj for obj in scene.objects if obj.type=='MESH' and any(m and m.name=='MI_Pine_Tree_Mat' for m in obj.data.materials)]
if len(trees)!=5 or recipe['root_z']!=0:raise ValueError('Expected reviewed native rootdatum')
for obj in trees:obj.location.z=-recipe['root_z']/100*obj.scale.z
scene.cycles.device='CPU';scene.cycles.samples=16
scene.camera.location=(9,-12,5);scene.camera.rotation_euler=(Vector((0,0,2))-scene.camera.location).to_track_quat('-Z','Y').to_euler();scene.camera.data.lens=60
scene.render.filepath=str(OUT/'native-conifer-root-datum-contact.png');bpy.ops.render.render(write_still=True)
scene.camera.location=(45,-65,32);scene.camera.rotation_euler=(Vector((0,6,14))-scene.camera.location).to_track_quat('-Z','Y').to_euler();scene.camera.data.lens=48
scene.render.filepath=str(OUT/'native-conifer-root-datum-placement.png');bpy.ops.render.render(write_still=True)
(OUT/'root-datum.receipt.json').write_text(json.dumps({'schema':'pwr-conifer-soil-datum-v1',
    'source_geometry_sha256':recipe['geometry_sha256'],'recipes_sha256':hashlib.sha256((OUT/'recipes.json').read_bytes()).hexdigest(),
    'root_z_cm':0,'measured_min_z_cm':recipe['min_z'],'below_origin_roots_buried':True,
    'geometry_unchanged':True,'cpu_blender_approximation_not_native_material_proof':True},indent=2)+'\n')
