"""Blender-only before/after native rock geometry preview on the frozen terrain."""
from pathlib import Path
import json,math
import bpy
from mathutils import Vector,Matrix
ROOT=Path(__file__).resolve().parents[4]
OUT=ROOT/'out/pwr/visual-v5/outcrops-v2'
if bpy.data.is_dirty:
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'before-outcrop-preview.blend'),copy=True)
previous=ROOT/'out/pwr/visual-v5/apron-v2/apron-v2-preview.blend'
if Path(bpy.data.filepath).resolve()==previous.resolve():
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'before-outcrop-preview.blend'))
with bpy.data.libraries.load(str(previous),link=False) as (source,target):
    target.scenes=[next(name for name in source.scenes if 'Apron V2' in name)]
scene=target.scenes[0];scene.name='PWR Outcrop V2 Geometry Review';bpy.context.window.scene=scene
proposal=json.loads((OUT/'proposal.json').read_text())
before=json.loads((ROOT/'out/pwr/visual-v5/outcrops.authored-decor.json').read_text())['decor']
material=bpy.data.materials.new('Granite shape preview - not native material');material.use_nodes=True
material.node_tree.nodes['Principled BSDF'].inputs['Base Color'].default_value=(.24,.26,.275,1)
material.node_tree.nodes['Principled BSDF'].inputs['Roughness'].default_value=.84
templates={}

def template(leaf):
    if leaf in templates:return templates[leaf]
    path=(OUT/'assets'/f'{leaf}.glb') if leaf=='SM_Rock_CliffFlat_Kit_B' else ROOT/'out/pwr/visual-v4/assets'/f'{leaf}.glb'
    old=set(bpy.data.objects);bpy.ops.import_scene.gltf(filepath=str(path));created=set(bpy.data.objects)-old
    result=[]
    for ob in created:
        if ob.type!='MESH' or any('LOD'+str(n) in ob.name for n in range(1,10)):continue
        bpy.context.view_layer.objects.active=ob;ob.select_set(True)
        if ob.data.has_custom_normals:bpy.ops.mesh.customdata_custom_splitnormals_clear()
        ob.select_set(False)
        ob.data.materials.clear();ob.data.materials.append(material)
        for poly in ob.data.polygons:poly.material_index=0
        result.append((ob.data,ob.matrix_world.copy()))
    for ob in created:bpy.data.objects.remove(ob,do_unlink=True)
    templates[leaf]=result;return result


def place(rows,name):
    collection=bpy.data.collections.new(name);scene.collection.children.link(collection)
    for row in rows:
        p=row['pos'];location=Vector((p[0]/100,-p[1]/100,p[2]/100))
        transform=Matrix.Translation(location)@Matrix.Rotation(math.radians(-row['rot'][1]),4,'Z')@Matrix.Diagonal((*row['scale'],1))
        for mesh,basis in template(row['mesh'].split('.')[-1]):
            ob=bpy.data.objects.new(row['id'],mesh);collection.objects.link(ob);ob.matrix_world=transform@basis
    return collection

old=place(before,'Current 108 outcrops');new=place(proposal['proposed_decor'],'Proposed 58 outcrops')
scene.cycles.samples=24;scene.render.resolution_x=1672;scene.render.resolution_y=941
camera=scene.camera;camera.data.lens=32;camera.location=(1420,90,700)
camera.rotation_euler=(Vector((650,650,260))-camera.location).to_track_quat('-Z','Y').to_euler()
new.hide_render=True;old.hide_render=False
scene.render.filepath=str(OUT/'northeast-before.png');bpy.ops.render.render(write_still=True)
new.hide_render=False;old.hide_render=True
scene.render.filepath=str(OUT/'northeast-after.png');bpy.ops.render.render(write_still=True)
# The palette closeup uses the same actual CliffFlat mesh at its authored scale.
ledge=next(row for row in proposal['proposed_decor'] if 'granite_ledge' in row['id'])
p=ledge['pos'];centre=Vector((p[0]/100,-p[1]/100,p[2]/100+8))
camera.location=centre+Vector((65,-85,60));camera.data.lens=36
camera.rotation_euler=(centre-camera.location).to_track_quat('-Z','Y').to_euler()
scene.render.filepath=str(OUT/'cliffflat-closeup.png');bpy.ops.render.render(write_still=True)
bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'outcrops-v2-preview.blend'))
(OUT/'preview.receipt.json').write_text(json.dumps({'preview':'Actual native mesh geometry and exact proposed transforms; approximate Blender material, not game proof',
 'current_count':len(before),'proposed_count':proposal['proposed_count'],'images':['northeast-before.png','northeast-after.png','cliffflat-closeup.png'],'installed':False},indent=2)+'\n')
print(str(OUT/'northeast-after.png'))
