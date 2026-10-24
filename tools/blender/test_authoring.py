"""Headless Blender integration checks for surface permissions and references.

blender --background --factory-startup --python-exit-code 1 --python tools/blender/test_authoring.py
"""
import json
from pathlib import Path
import sys
import bpy
import bmesh

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/"tools/blender"))
sys.path.insert(0,str(ROOT/"tools/level"))
import mjolnir_level
from mjolnir_level.surface import build_surface_policy, ATTRIBUTE
from mjolnir_level.export import build_level
from surface_policy import SurfacePolicy

mjolnir_level.register()
bpy.ops.object.select_all(action="SELECT")
bpy.ops.object.delete(use_global=False)
scene=bpy.context.scene
scene.unit_settings.system="METRIC"
scene.unit_settings.scale_length=3.048
bpy.ops.mesh.primitive_plane_add(size=2,location=(2,3,1))
plane=bpy.context.object
bpy.ops.object.mode_set(mode="EDIT")
bpy.ops.mesh.select_all(action="SELECT")
assert bpy.ops.mjolnir.pcg_faces(policy="CLIFF")=={"FINISHED"}
bpy.ops.object.mode_set(mode="OBJECT")
assert plane.data.attributes[ATTRIBUTE].data[0].value==3
doc=build_surface_policy(scene)
assert len(doc["triangles"])==2
mask=SurfacePolicy(doc)
assert not mask.allows(609.6,-914.4,304.8,"ground")
assert mask.allows(609.6,-914.4,304.8,"cliff")
plane.mjolnir.kind="MARKER"
level,problems=build_level(scene)
assert not problems and level["markers"][0]["pos"]==[609.6,-914.4,304.8]
plane["mjolnir_preview_only"]=True
assert not build_surface_policy(scene)["triangles"]
assert "markers" not in build_level(scene)[0]
mjolnir_level.unregister()
print("PASS: add-on registration, painted face policy, CE scene units/Y conversion, reference export exclusion")
