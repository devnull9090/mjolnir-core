"""Render Crosswalk from the actual Foundry Blender assets.

blender --background --factory-startup --python build_demo.py
Requires build_blender.py first. Outputs build/crosswalk.blend and
art/foundry-crosswalk.png; does not modify game files or create a native save.
"""

import json
import math
from pathlib import Path
import sys

import bpy
from mathutils import Vector

ROOT = Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT))
from build_blender import material, mesh_object
from generate import box
from generate_demo import build, validate


def main():
    layout=build()
    validate(layout)
    (ROOT/"demo").mkdir(exist_ok=True)
    (ROOT/"demo/crosswalk.layout.json").write_text(json.dumps(layout,indent=2)+"\n")
    library=ROOT/"build/foundry.blend"
    if not library.exists():
        raise RuntimeError("Run build_blender.py first")
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    scene=bpy.context.scene
    scene.unit_settings.system="METRIC"
    scene.unit_settings.scale_length=1
    with bpy.data.libraries.load(str(library),link=False) as (data_in,data_out):
        data_out.objects=[name for name in data_in.objects if name.startswith("foundry_")]
    prototypes={obj.name.removeprefix("foundry_"):obj for obj in data_out.objects}
    assembly=bpy.data.collections.new("Crosswalk / Foundry assembly")
    studio=bpy.data.collections.new("Crosswalk / Studio")
    scene.collection.children.link(assembly)
    scene.collection.children.link(studio)
    for placement in layout["placements"]:
        obj=prototypes[placement["block"]].copy()
        obj.name=placement["id"]+"_"+placement["block"]
        obj.location=placement["position_m"]
        obj.rotation_euler=[math.radians(v) for v in placement["rotation_deg"]]
        obj.scale=(1,1,1)
        obj["demo_role"]=placement["role"]
        assembly.objects.link(obj)
    dark=material("Studio / charcoal",{"base_color":[0.028,0.042,0.052,1],"metallic":0,"roughness":0.9})
    base=mesh_object("Presentation plinth",box(17,17,0.45,z=-0.45),studio)
    base.data.materials.append(dark)
    floor=mesh_object("Studio floor",box(200,200,0.1,z=-0.6),studio)
    floor.data.materials.append(dark)
    camera_data=bpy.data.cameras.new("Crosswalk camera")
    camera=bpy.data.objects.new("Crosswalk camera",camera_data)
    studio.objects.link(camera)
    camera.location=(23,-27,25)
    camera.rotation_euler=(Vector((0,0,1.5))-camera.location).to_track_quat("-Z","Y").to_euler()
    camera_data.type="ORTHO"
    camera_data.ortho_scale=27
    scene.camera=camera
    for name,position,energy,size in [("Key",(-12,-15,24),8000,15),("Fill",(14,5,20),6000,12),("Rim",(0,14,15),5000,10)]:
        data=bpy.data.lights.new(name,"AREA")
        data.energy,data.shape,data.size=energy,"DISK",size
        light=bpy.data.objects.new(name,data)
        studio.objects.link(light)
        light.location=position
        light.rotation_euler=(Vector((0,0,1))-light.location).to_track_quat("-Z","Y").to_euler()
    scene.world.use_nodes=True
    scene.world.node_tree.nodes["Background"].inputs["Color"].default_value=(0.2,0.25,0.3,1)
    scene.world.node_tree.nodes["Background"].inputs["Strength"].default_value=0.3
    scene.render.engine="CYCLES"
    scene.cycles.samples=48
    scene.cycles.use_denoising=True
    scene.render.resolution_x=1800
    scene.render.resolution_y=1400
    scene.render.resolution_percentage=100
    scene.render.image_settings.file_format="PNG"
    scene.view_settings.view_transform="AgX"
    (ROOT/"art").mkdir(exist_ok=True)
    scene.render.filepath=str(ROOT/"art/foundry-crosswalk.png")
    bpy.ops.wm.save_as_mainfile(filepath=str(ROOT/"build/crosswalk.blend"))
    bpy.ops.render.render(write_still=True)
    print(f"CROSSWALK_OK: {len(layout['placements'])} placements from the real Foundry assets")


if __name__=="__main__":
    main()
