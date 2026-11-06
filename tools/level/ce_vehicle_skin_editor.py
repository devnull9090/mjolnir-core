"""Import a CE vehicle's skinned glTF as a SkeletalMesh, in the Unreal editor.

    set MJ_CE_SKIN=<name>.skin.json
    UnrealEditor-Cmd.exe Meteorite.uproject -run=pythonscript -script=<this file>

The file holds `gltf`, `folder`, `stem` and, when the slots are to be dressed,
`slots`: {section name: material instance object path}. Makes
<folder>/SK_<stem> and <folder>/SKEL_<stem>, with no physics asset of their own.
A label at the folder puts them in chunk `chunk`.

The importer names the skeleton after the mesh, so it is renamed here, and the
mesh is force-saved after the rename: a mesh not saved again keeps the old path
and cooks with no Skeleton at all, silently.

Every bone's name and reference pose is printed, for the read-back.
"""
import json
import os

import unreal

eal = unreal.EditorAssetLibrary
tools = unreal.AssetToolsHelpers.get_asset_tools()

spec = json.load(open(os.environ["MJ_CE_SKIN"], encoding="utf-8"))
folder, stem = spec["folder"], spec["stem"]
sk, skel = f"SK_{stem}", f"SKEL_{stem}"

if eal.does_directory_exist(folder):
    eal.delete_directory(folder)

task = unreal.AssetImportTask()
task.filename = spec["gltf"]
task.destination_path = folder
task.destination_name = sk
task.automated = True
task.save = True
task.replace_existing = True
tools.import_asset_tasks([task])

mesh = eal.load_asset(f"{folder}/{sk}")
if not isinstance(mesh, unreal.SkeletalMesh):
    raise RuntimeError(f"{folder}/{sk} did not import as a SkeletalMesh: {eal.list_assets(folder)}")

mesh.set_editor_property("physics_asset", None)
mesh.set_editor_property("support_ray_tracing", False)
# The vertex colour holds a direction in each vertex's tangent frame, so the
# frames have to stay the file's.
editor = unreal.get_editor_subsystem(unreal.SkeletalMeshEditorSubsystem)
build = editor.get_lod_build_settings(mesh, 0)
build.set_editor_property("recompute_normals", False)
build.set_editor_property("recompute_tangents", False)
editor.set_lod_build_settings(mesh, 0, build)
eal.save_asset(f"{folder}/{sk}")

slots = spec.get("slots", {})
materials = mesh.get_editor_property("materials")
for i, m in enumerate(materials):
    name = str(m.get_editor_property("material_slot_name"))
    print(f"MJOLNIR skin slot {name}")
    if slots:
        # An array hands out copies of its structs, so the edit goes back in.
        m.set_editor_property("material_interface", eal.load_asset(slots[name]))
        materials[i] = m
if slots:
    mesh.set_editor_property("materials", materials)
    empty = [str(m.get_editor_property("material_slot_name")) for m in mesh.get_editor_property("materials")
             if m.get_editor_property("material_interface") is None]
    if empty:
        raise RuntimeError(f"slots left with no material: {empty}")

# What the import made beside the mesh goes: materials, textures, physics.
for path in eal.list_assets(folder, recursive=True):
    leaf = path.split(".")[-1]
    if leaf not in (sk, f"{sk}_Skeleton"):
        eal.delete_asset(path)

eal.rename_asset(f"{folder}/{sk}_Skeleton", f"{folder}/{skel}")
if not eal.save_loaded_asset(mesh, False):
    raise RuntimeError("the mesh would not save after the rename")
eal.save_asset(f"{folder}/{skel}", False)

if spec.get("chunk"):
    label = tools.create_asset(f"PAL_{stem}", folder, unreal.PrimaryAssetLabel, unreal.DataAssetFactory())
    rules = label.get_editor_property("rules")
    rules.set_editor_property("chunk_id", int(spec["chunk"]))
    rules.set_editor_property("priority", 10)
    rules.set_editor_property("apply_recursively", True)
    rules.set_editor_property("cook_rule", unreal.PrimaryAssetCookRule.ALWAYS_COOK)
    label.set_editor_property("rules", rules)
    label.set_editor_property("label_assets_in_my_directory", True)
    eal.save_loaded_asset(label)

skeleton = mesh.skeleton
print("MJOLNIR skin skeleton", skeleton.get_path_name())
pose = unreal.AnimPoseExtensions.get_reference_pose(skeleton)
for name in unreal.AnimPoseExtensions.get_bone_names(pose):
    t = unreal.AnimPoseExtensions.get_bone_pose(pose, name, unreal.AnimPoseSpaces.LOCAL)
    q, v = t.rotation, t.translation
    print(f"MJOLNIR skin bone [{name}] t {v.x:.4f} {v.y:.4f} {v.z:.4f} q {q.x:.5f} {q.y:.5f} {q.z:.5f} {q.w:.5f}")
print("MJOLNIR skin assets", eal.list_assets(folder, recursive=True))
