"""Render the actual PWR authored geometry; native scenery is not in this preview."""
import argparse
from pathlib import Path
import sys

import bpy
from mathutils import Vector

ROOT=Path(__file__).resolve().parent
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument("--output",type=Path,default=ROOT.parents[2]/"out/pwr/expansion/pwr-overview.png")
args=parser.parse_args(sys.argv[sys.argv.index("--")+1:] if "--" in sys.argv else [])
bpy.ops.wm.open_mainfile(filepath=str(ROOT/"pwr.blend"))
scene=bpy.context.scene
# Remove only sky faces in this unsaved render scene so overview sees inside.
obj=bpy.data.objects["PWR_sealed_air_and_terrain"]
import bmesh
bm=bmesh.new(); bm.from_mesh(obj.data)
sky=[f for f in bm.faces if obj.data.materials[f.material_index].name=="+sky"]
bmesh.ops.delete(bm,geom=sky,context="FACES")
bm.to_mesh(obj.data); bm.free()
camera=bpy.data.objects.new("PWR overview camera",bpy.data.cameras.new("PWR overview camera"))
scene.collection.objects.link(camera)
camera.location=(1850/3.048,-2200/3.048,2400/3.048)
camera.rotation_euler=(Vector((0,0,0))-camera.location).to_track_quat("-Z","Y").to_euler()
camera.data.type="ORTHO"; camera.data.ortho_scale=2900/3.048; camera.data.clip_end=5000
scene.camera=camera
sun=bpy.data.objects.new("PWR preview sun",bpy.data.lights.new("PWR preview sun","SUN"))
scene.collection.objects.link(sun)
sun.rotation_euler=(.45,-.3,-.8)
sun.data.energy=3
scene.world.color=(.35,.45,.55)
scene.render.engine="CYCLES"
scene.cycles.samples=24
scene.cycles.use_denoising=True
scene.render.resolution_x=1500; scene.render.resolution_y=1100; scene.render.resolution_percentage=100
scene.view_settings.view_transform="AgX"
args.output.parent.mkdir(parents=True,exist_ok=True)
scene.render.filepath=str(args.output)
bpy.ops.render.render(write_still=True)
print("PWR_PREVIEW",args.output)
bpy.ops.wm.open_mainfile(filepath=str(ROOT/"pwr.blend"))
