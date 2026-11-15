"""Pack and seal the reviewed Blender authoring scene; never exports to game."""
import bpy, json, re
from pathlib import Path

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
OUT=ROOT/'out/pwr/base-art'
review=ROOT/'.dream-loop/bases-v1/judge-r9.txt'
score=float(re.search(r'\d+(?:\.\d+)?',review.read_text(encoding='utf-8')).group())
validation=json.loads((OUT/'geometry-validation.json').read_text())
if score<8 or not validation['passed']:
    raise RuntimeError('The recorded art review or geometry validation has not passed')
expected=HERE/'forerunner_bases.blend'
if Path(bpy.data.filepath).resolve()!=expected.resolve():
    raise RuntimeError('Wrong authoring scene is active')

packed=[]
for im in bpy.data.images:
    if im.source=='FILE':
        im.pack()
        if not im.packed_file and not len(im.packed_files):
            raise RuntimeError('Unpacked image: '+im.name)
        packed.append({'name':im.name,'original_path':im.filepath,'packed':True})
scene=bpy.context.scene
scene['design_stage']='Blender art review passed; game integration deferred by user'
scene['art_review_score']=score
scene['art_review_file']=str(review)
scene['runtime_validation']='Deferred; static geometry checks only'
scene['blender_mcp_package']='mcp-for-blender 2.2.7 / protocol15'
scene.camera=bpy.data.objects['Camera • RED hero']
scene.render.filepath=str(OUT/'renders/red-hero-v16.png')
bpy.ops.object.select_all(action='DESELECT')
for screen in bpy.data.screens:
    for area in screen.areas:
        if area.type=='VIEW_3D':
            area.spaces.active.region_3d.view_perspective='CAMERA'
            area.spaces.active.shading.type='MATERIAL'
bpy.data.orphans_purge(do_local_ids=True,do_linked_ids=False,do_recursive=True)
bpy.ops.wm.save_as_mainfile(filepath=str(expected))
receipt={'blend':str(expected),'blender_version':bpy.app.version_string,
         'mcp_package':'mcp-for-blender2.2.7','art_review_score':score,
         'geometry_passed':validation['passed'],'packed_images':packed,
         'active_camera':scene.camera.name,'art_revision':scene['art_revision'],
         'runtime_tested':False,'game_exported':False,
         'renders':[str(p) for p in sorted((OUT/'renders').glob('*-v16.png'))]}
(OUT/'final-scene-receipt.json').write_text(json.dumps(receipt,indent=2))
print(json.dumps(receipt))
