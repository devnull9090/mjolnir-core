"""Editor integration proof: PCG exact sidecars become ordinary HISM transforms.

Set MJ_PCG_PROOF to the small proof directory containing baked/foliage.*.
The saved proof world is editor-only and never installed or cooked.
"""
import json
import os
from pathlib import Path

import unreal

root = Path(os.environ["MJ_PCG_PROOF"])
spec = json.loads((root/"baked/foliage.json").read_text(encoding="utf-8"))
expected = json.loads((root/"a.json").read_text(encoding="utf-8"))["points"]
level = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
package = "/Game/MJOLNIR/PCGAuthoring/PWR/PCG_BakeProof"
if unreal.EditorAssetLibrary.does_asset_exist(package):
    unreal.EditorAssetLibrary.delete_asset(package)
if not level.new_level(package):
    raise RuntimeError("cannot create PCG bake proof world")
world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
groups = spec["groups"]
count = unreal.MjolnirUIBuilderLibrary.bake_foliage(
    world, str(root/"baked/foliage.bin"), "MJOLNIR_PCG_BakeProof",
    [g["mesh"] for g in groups], [g["bands"] for g in groups],
    [unreal.Vector2D(*g["cull"]) for g in groups], [38 for _ in groups])
actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors()
instances = []
components = 0
for actor in actors:
    if "PCG" in actor.get_class().get_name():
        raise RuntimeError("PCG runtime actor leaked into bake proof")
    for component in actor.get_components_by_class(unreal.ActorComponent):
        if "PCG" in component.get_class().get_name():
            raise RuntimeError("PCG runtime component leaked into bake proof")
    for component in actor.get_components_by_class(unreal.HierarchicalInstancedStaticMeshComponent):
        components += 1
        for index in range(component.get_instance_count()):
            t = component.get_instance_transform(index, world_space=True)
            instances.append(([t.translation.x,t.translation.y,t.translation.z],
                              [t.rotation.x,t.rotation.y,t.rotation.z,t.rotation.w],
                              [t.scale3d.x,t.scale3d.y,t.scale3d.z]))
if count != len(expected) or len(instances) != len(expected):
    raise RuntimeError("HISM instance count differs from PCG selection")
instances.sort(key=lambda row:tuple(row[0]))
expected.sort(key=lambda row:tuple(row["position_cm"]))
worst_position = worst_rotation = worst_scale = 0.0
for actual, wanted in zip(instances,expected):
    worst_position=max(worst_position,max(abs(a-b) for a,b in zip(actual[0],wanted["position_cm"])))
    dot=abs(sum(a*b for a,b in zip(actual[1],wanted["rotation_xyzw"])))
    worst_rotation=max(worst_rotation,abs(1-dot))
    worst_scale=max(worst_scale,max(abs(a-b) for a,b in zip(actual[2],wanted["scale_xyz"])))
if worst_position>.01 or worst_rotation>.00001 or worst_scale>.00001:
    raise RuntimeError("PCG to HISM exact transform drift")
if not level.save_current_level(): raise RuntimeError("failed to save bake proof world")
receipt={"schema":1,"pcg_selected":len(expected),"hism_instances":len(instances),
         "hism_components":components,"maximum_position_error_cm":worst_position,
         "maximum_quaternion_dot_error":worst_rotation,"maximum_scale_error":worst_scale,
         "pcg_runtime_objects":0,"world":package,"engine":unreal.SystemLibrary.get_engine_version()}
(root/"bake.verification.json").write_text(json.dumps(receipt,indent=2),encoding="utf-8")
unreal.log("MJOLNIR PCG HISM bake proof: "+json.dumps(receipt))
