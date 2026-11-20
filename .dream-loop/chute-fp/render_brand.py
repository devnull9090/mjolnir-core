"""Presentation views of the real marked panels in the authored Blender file."""
import bpy
import math
from pathlib import Path
from mathutils import Vector

def render(output):
    folder=Path(output)
    scene=bpy.data.scenes.new("PWR maker markings inspection")
    for name in ("wing","rig","pack"):
        scene.collection.children.link(bpy.data.collections[name])
    scene.world=bpy.data.worlds.new("Neutral sky")
    scene.world.use_nodes=True
    scene.world.node_tree.nodes["Background"].inputs["Color"].default_value=(.22,.25,.29,1)
    cam=bpy.data.objects.new("Inspection camera",bpy.data.cameras.new("Lens"))
    scene.collection.objects.link(cam)
    scene.camera=cam
    cam.data.type="ORTHO"
    cam.data.clip_start=.005
    for pos,energy,size in [((-2,3,5.75),230,2.6),((2,1,2.4),65,2.0),((-.6,-1,2.4),115,2.2)]:
        lamp=bpy.data.objects.new("Inspection softbox",bpy.data.lights.new("Softbox","AREA"))
        scene.collection.objects.link(lamp)
        lamp.data.energy, lamp.data.size=energy,size
        lamp.location=pos
        lamp.rotation_euler=(Vector((0,.15,2.8))-lamp.location).to_track_quat("-Z","Y").to_euler()
    scene.render.engine="CYCLES"
    scene.cycles.samples=20
    scene.cycles.use_denoising=True
    scene.render.image_settings.file_format="PNG"
    scene.view_settings.view_transform="AgX"
    try:
        for name,pos,direction,span,size in [
            ("canopy-underside",(0,-.04,4.34),(0,0,1),3.28,(1400,800)),
            ("pack",(0,1.55,1.49),(0,-1,.018),.85,(920,820)),
            ("pack-maker-close",(0,.86,1.38),(0,-1,.075),.158,(1152,648))]:
            cam.location=pos
            cam.rotation_euler=(math.pi,0,0) if name=="canopy-underside" else Vector(direction).to_track_quat("-Z","Y").to_euler()
            cam.data.ortho_scale=span
            scene.render.resolution_x,scene.render.resolution_y=size
            scene.render.resolution_percentage=100
            scene.render.filepath=str(folder/(name+".png"))
            bpy.ops.render.render(write_still=True,scene=scene.name)
    finally:
        for obj in tuple(scene.collection.objects):
            bpy.data.objects.remove(obj,do_unlink=True)
        bpy.data.scenes.remove(scene)
