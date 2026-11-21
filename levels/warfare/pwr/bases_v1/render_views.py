"""Review views of actual Blender geometry; restores authoring layout afterward."""
import bpy, json
from pathlib import Path
from mathutils import Matrix, Vector

ROOT=Path(__file__).resolve().parents[4]
OUT=ROOT/'out/pwr/base-art/renders'

def aim(ob,loc,target,lens):
    ob.location=loc;ob.rotation_euler=(Vector(target)-ob.location).to_track_quat('-Z','Y').to_euler();ob.data.lens=lens

def render_views(version='v4',views=('red','blue','green','interior','roof')):
    scene=bpy.context.scene
    art_scale=float(scene.get('base_authoring_scale',1))
    def pose(loc,target,lens):
        aim(cam,tuple(v*art_scale for v in loc),tuple(v*art_scale for v in target),lens)
    cols=[next(c for c in bpy.data.collections if c.name.startswith(p)) for p in ('01_RED','02_BLUE','03_GREEN')]
    matrices={ob:ob.matrix_world.copy() for c in cols for ob in c.objects}
    flags={c:c.hide_render for c in cols}
    original_camera=scene.camera
    cam=bpy.data.objects.get('Camera • RED hero')
    oldcam=(cam.matrix_world.copy(),cam.data.lens,cam.data.type,cam.data.ortho_scale)
    original_path=scene.render.filepath
    paths=[]
    try:
        for view in views:
            for c in cols:c.hide_render=True
            for ob,mat in matrices.items():ob.matrix_world=mat
            scene.camera=cam;cam.data.type='PERSP'
            if view in ('red','blue','green','blue-oblique'):
                index={'red':0,'blue':1,'green':2,'blue-oblique':1}[view];c=cols[index];c.hide_render=False
                offset=[(0,0,0),(-135,0,0),(0,-150,0)][index]
                for ob in c.objects:ob.matrix_world=Matrix.Translation(offset)@matrices[ob]
                pose((18,-170,35),(0,0,9),45)
                if view in ('green','blue-oblique'):pose((104,-140,93),(0,6,11),46)
            elif view=='interior':
                cols[0].hide_render=False;pose((5,-24,4.4),(-2,19,5.2),22)
            elif view=='roof':
                cols[0].hide_render=False;pose((0,-.01,175),(0,0,0),48);cam.data.type='ORTHO';cam.data.ortho_scale=125*art_scale
            elif view=='gallery':
                cols[0].hide_render=False;pose((33,-23,3.5),(19,18,4),22)
            elif view in ('passage-left','passage-right'):
                cols[0].hide_render=False;side=-1 if view=='passage-left' else 1
                pose((side*33,-34,2.7),(side*33,23,3.0),22)
            elif view=='green-rear':
                c=cols[2];c.hide_render=False
                for ob in c.objects:ob.matrix_world=Matrix.Translation((0,-150,0))@matrices[ob]
                pose((95,140,80),(0,5,10),45)
            elif view=='gateway':
                cols[0].hide_render=False;pose((26,-130,31),(0,0,12),43)
            else:raise ValueError(view)
            bpy.context.view_layer.update()
            path=OUT/f'{view}-{version}.png';scene.render.filepath=str(path)
            bpy.ops.render.render(write_still=True);paths.append(str(path))
    finally:
        for ob,mat in matrices.items():ob.matrix_world=mat
        for c,flag in flags.items():c.hide_render=flag
        cam.matrix_world=oldcam[0];cam.data.lens=oldcam[1];cam.data.type=oldcam[2];cam.data.ortho_scale=oldcam[3]
        scene.camera=original_camera;scene.render.filepath=original_path;bpy.context.view_layer.update()
    print(json.dumps({'renders':paths}))
    return paths

if __name__=='__main__':render_views()
