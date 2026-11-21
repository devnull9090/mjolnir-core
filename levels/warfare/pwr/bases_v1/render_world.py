"""Render actual assembled Blender geometry, without game or image synthesis."""
import bpy, json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[4]
OUT=ROOT/'out/pwr/base-integration'

def main(views=('world-overview','world-topdown','red-integrated','blue-integrated','green-integrated','red-connections')):
    scene=bpy.context.scene
    receipt=json.loads((OUT/'assembly-receipt.json').read_text())
    paths=[]
    for view in views:
        scene.render.resolution_x=1600 if view=='world-topdown' else 1920
        scene.render.resolution_y=1600 if view=='world-topdown' else 1080
        scene.camera=bpy.data.objects[receipt['cameras'][view]]
        scene.render.filepath=str(OUT/(view+'.png'))
        bpy.ops.render.render(write_still=True)
        paths.append(scene.render.filepath)
    scene.camera=bpy.data.objects[receipt['cameras']['red-integrated']]
    scene.render.resolution_x=1920;scene.render.resolution_y=1080
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'pwr-world-bases-v1.blend'))
    (OUT/'render-receipt.json').write_text(json.dumps({'renders':paths,'actual_blender_geometry':True,
        'game_launched':False,'unreal_shader_parity':False},indent=2)+'\n')
    print(json.dumps({'renders':paths}))

if __name__=='__main__':main()
