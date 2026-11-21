"""Same full-frame Spartan eye point for every handle review, without HUD or hand occlusion."""
import bpy
import math
from pathlib import Path
from mathutils import Vector

def render(output):
    source=bpy.context.scene
    preview=bpy.data.scenes.new("Pilot handle inspection")
    preview.collection.children.link(bpy.data.collections["rig"])
    preview.world=bpy.data.worlds.new("Inspection sky")
    preview.world.use_nodes=True
    sky=preview.world.node_tree.nodes["Background"]
    sky.inputs[0].default_value=(.205,.24,.28,1)
    sky.inputs[1].default_value=.80
    camera=bpy.data.objects.new("Forward",bpy.data.cameras.new("Player eye"))
    preview.collection.objects.link(camera)
    camera.location=(0,.0006,1.89)
    camera.rotation_euler=Vector((0,-1,0)).to_track_quat("-Z","Y").to_euler()
    camera.data.lens_unit="FOV"
    camera.data.angle=math.radians(85)
    camera.data.clip_start=.003
    preview.camera=camera
    for name,loc,size,power,color in [
        ("Sky",(-.52,.78,3.36),1.30,75,(.86,.91,1.0)),
        ("Sun",(-1.28,-.65,3.70),.32,84,(1.0,.94,.80)),
        ("Return",(1.38,.64,2.35),.90,34,(1.0,.85,.70)),
    ]:
        lamp=bpy.data.objects.new(name,bpy.data.lights.new(name,"AREA"))
        preview.collection.objects.link(lamp)
        lamp.location=loc
        lamp.data.shape="DISK"
        lamp.data.size=size
        lamp.data.energy=power
        lamp.data.color=color
        lamp.rotation_euler=(Vector((0,-.45,1.91))-lamp.location).to_track_quat("-Z","Y").to_euler()
    preview.render.engine="CYCLES"
    preview.cycles.samples=20
    preview.cycles.use_denoising=True
    preview.render.resolution_x,preview.render.resolution_y=1920,1080
    preview.render.resolution_percentage=100
    preview.view_settings.view_transform="AgX"
    preview.render.image_settings.file_format="PNG"
    preview.render.filepath=str(Path(output).resolve())
    try:
        bpy.ops.render.render(write_still=True,scene=preview.name)
    finally:
        # Scene-only lights and camera are not part of the authored delivery.
        for obj in tuple(preview.collection.objects):
            bpy.data.objects.remove(obj,do_unlink=True)
        bpy.data.scenes.remove(preview)
