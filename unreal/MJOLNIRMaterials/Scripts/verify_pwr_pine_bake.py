"""Editor-only full pine HISM proof. MJ_PINE_PROOF points to pine-proof folder."""
import json
import os
from pathlib import Path
import struct
import unreal

root = Path(os.environ["MJ_PINE_PROOF"])
spec = json.loads((root / "pine.bake.json").read_text())
package = "/Game/MJOLNIR/PCGAuthoring/PWR/Pine_BakeProof"
level = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
assets = unreal.EditorAssetLibrary
level.new_level("/Game/__MJOLNIR_PineScratch")
unreal.AssetRegistryHelpers.get_asset_registry().scan_paths_synchronous([package.rsplit("/", 1)[0]], True)
if assets.does_asset_exist(package):
    assets.delete_asset(package)
if not level.new_level(package, False):
    raise RuntimeError("Could not create pine proof world")
world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
for entry in spec["standins"]:
    mesh = unreal.MjolnirUIBuilderLibrary.create_stand_in_mesh(entry["path"])
    ox, oy, oz = entry["origin"]; ex, ey, ez = entry["extent"]
    vertices = [unreal.Vector(ox + x * ex, oy + y * ey, oz + z * ez)
                for x in (-1, 1) for y in (-1, 1) for z in (-1, 1)]
    normals = [unreal.Vector(x, y, z) for x in (-1, 1) for y in (-1, 1) for z in (-1, 1)]
    faces = ((0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1), (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3))
    indices = [i for a, b, c, d in faces for i in (a, b, c, a, c, d)]
    uv = [unreal.Vector2D(0, 0)] * len(indices)
    if not unreal.MjolnirUIBuilderLibrary.build_static_mesh(mesh, vertices, normals, indices, uv, uv,
                                                            [0] * 12, [unreal.Name(s) for s in entry["slots"]], [], []):
        raise RuntimeError("Native-bound stand-in build failed")
    assets.save_loaded_asset(mesh)
groups = spec["groups"]
count = unreal.MjolnirUIBuilderLibrary.bake_foliage(world, spec["bin"], "PWR_Pine_Proof",
            [g["mesh"] for g in groups], [1] * len(groups),
            [unreal.Vector2D(*g["cull"]) for g in groups], [g["flags"] for g in groups])
expected_count = sum(g["count"] for g in groups)
if count != expected_count:
    raise RuntimeError("Pine instance count changed")
seen = set(); actual = 0; pos_error = rotation_error = scale_error = 0.0
for actor in unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors():
    if actor.get_name().startswith("MJDecor_"):
        raise RuntimeError("Unexpected duplicate pine decor actor")
    for component in actor.get_components_by_class(unreal.HierarchicalInstancedStaticMeshComponent):
        name = component.get_name(); number = int(name.split("_")[1]); seen.add(number)
        expected = list(struct.iter_unpack("<10f", Path(spec["bin"] + ".xf" + str(number)).read_bytes()))
        if component.get_instance_count() != len(expected):
            raise RuntimeError("Pine group size changed")
        for i, target in enumerate(expected):
            transform = component.get_instance_transform(i, world_space=True)
            pos_error = max(pos_error, *(abs(a - b) for a, b in zip(
                [transform.translation.x, transform.translation.y, transform.translation.z], target[:3])))
            rotation_error = max(rotation_error, abs(1 - abs(sum(a * b for a, b in zip(
                [transform.rotation.x, transform.rotation.y, transform.rotation.z, transform.rotation.w], target[3:7])))))
            scale_error = max(scale_error, *(abs(a - b) for a, b in zip(
                [transform.scale3d.x, transform.scale3d.y, transform.scale3d.z], target[7:10])))
        if not component.get_editor_property("cast_shadow") or component.get_editor_property("evaluate_world_position_offset"):
            raise RuntimeError("Pine shadow/static flags changed")
        if (component.get_editor_property("instance_start_cull_distance") != 90000 or
                component.get_editor_property("instance_end_cull_distance") != 180000):
            raise RuntimeError("Pine culling distances changed")
        actual += len(expected)
if len(seen) != len(groups) or actual != expected_count or pos_error > .01 or rotation_error > 1e-5 or scale_error > 1e-5:
    raise RuntimeError("Pine exact transform/component parity failed")
if not level.save_current_level():
    raise RuntimeError("Pine proof world did not save")
receipt = {"schema": 1, "engine": unreal.SystemLibrary.get_engine_version(), "world": package,
           "instances": actual, "hism_components": len(seen), "maximum_position_error_cm": pos_error,
           "maximum_quaternion_dot_error": rotation_error, "maximum_scale_error": scale_error,
           "cull_cm": [90000, 180000], "shadows": True, "world_position_offset": False,
           "decor_actor_copies": 0, "standins": "native game mesh bounds; visual assets resolve in game"}
(root / "pine_hism.verification.json").write_text(json.dumps(receipt, indent=2), encoding="utf-8")
unreal.log("MJOLNIR full pine HISM proof: " + json.dumps(receipt))
