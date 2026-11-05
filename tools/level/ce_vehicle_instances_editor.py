"""Make a CE vehicle's material instances, in the Unreal editor.

    set MJ_CE_INSTANCES=<name>.instances.json
    powershell -File tools/ue/editor_cmd.ps1 -Script ..\\..\\tools\\level\\ce_vehicle_instances_editor.py

tools/level/ce_vehicle_materials.py writes the file and runs this. Each entry
becomes a MaterialInstanceConstant of one of Scripts/build_ce_materials.py's
masters, with the textures, scalars and vectors a level's loader would have
set on a dynamic instance. A scalar or vector the master does not have is left
out, as a dynamic instance ignores it (ce_material_spec.py gives every object
section ObjectPage; the glass masters have none), and listed in <file>.dropped
for the read-back. A texture the master does not have stops the run. The file's
`overrides` go on whichever masters have them.
"""
import json
import os

import unreal

mel = unreal.MaterialEditingLibrary
eal = unreal.EditorAssetLibrary
assets = unreal.AssetToolsHelpers.get_asset_tools()

spec = json.load(open(os.environ["MJ_CE_INSTANCES"], encoding="utf-8"))

# Instances the file no longer names would still cook.
folder = spec["folder"]
wanted = {e["package"] for e in spec["instances"]}
if eal.does_directory_exist(folder):
    for path in eal.list_assets(folder, recursive=True, include_folder=False):
        if path.split(".")[0] not in wanted:
            eal.delete_asset(path.split(".")[0])

dropped = {}
for entry in spec["instances"]:
    package = entry["package"]
    leaf = package.rsplit("/", 1)[1]
    parent = unreal.load_asset(entry["parent"])
    if parent is None:
        raise RuntimeError(f"no master {entry['parent']}")
    mi = unreal.load_asset(package)
    if mi is None:
        mi = assets.create_asset(leaf, folder, unreal.MaterialInstanceConstant,
                                 unreal.MaterialInstanceConstantFactoryNew())
    if mi is None:
        raise RuntimeError(f"could not create {package}")
    mel.set_material_instance_parent(mi, parent)
    mel.clear_all_material_instance_parameters(mi)
    have = {str(n) for n in mel.get_scalar_parameter_names(parent)}
    have_vector = {str(n) for n in mel.get_vector_parameter_names(parent)}
    have_texture = {str(n) for n in mel.get_texture_parameter_names(parent)}
    dropped[package] = [n for n in list(entry["scalars"]) + list(entry["vectors"]) if n not in have | have_vector]
    for name, value in entry["scalars"].items():
        if name in have:
            mel.set_material_instance_scalar_parameter_value(mi, name, float(value))
    for name, value in spec.get("overrides", {}).items():
        if name in have:
            mel.set_material_instance_scalar_parameter_value(mi, name, float(value))
    for name, value in entry["vectors"].items():
        if name in have_vector:
            mel.set_material_instance_vector_parameter_value(mi, name, unreal.LinearColor(*value))
    for name, path in entry["textures"].items():
        if name not in have_texture:
            raise RuntimeError(f"{leaf}: {entry['parent']} has no texture {name}")
        texture = unreal.load_asset(path)
        if texture is None:
            raise RuntimeError(f"{leaf}: no texture {path}")
        mel.set_material_instance_texture_parameter_value(mi, name, texture)
    mel.update_material_instance(mi)
    if not eal.save_loaded_asset(mi):
        raise RuntimeError(f"could not save {package}")
    unreal.log(f"MJOLNIR instance {leaf}: {len(entry['scalars'])} scalar(s), {len(entry['vectors'])} vector(s), "
               f"{len(entry['textures'])} texture(s), left out {dropped[package]}")

# build_ce_level.py's label is recursive, which for textures alone costs
# nothing. An instance's references reach its master and the master's default
# textures, and the chunk took copies of them, shaders and all, to shadow the
# runtime pack's. The label's folder scan already holds everything here.
root = folder.rsplit("/", 1)[0]
label = unreal.load_asset(f"{root}/PAL_{root.rsplit('/', 1)[1]}")
rules = label.get_editor_property("rules")
rules.set_editor_property("apply_recursively", False)
label.set_editor_property("rules", rules)
eal.save_loaded_asset(label)

json.dump(dropped, open(os.environ["MJ_CE_INSTANCES"] + ".dropped", "w", encoding="utf-8"), indent=1)
unreal.log(f"MJOLNIR vehicle instances: {len(spec['instances'])} under {folder}")
