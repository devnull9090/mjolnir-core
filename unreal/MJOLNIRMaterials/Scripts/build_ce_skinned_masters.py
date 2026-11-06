"""Copy CE masters into a folder of their own with skeletal mesh usage set.

    set MJ_CE_INSTANCES=<name>.instances.json
    UnrealEditor-Cmd.exe Meteorite.uproject -run=pythonscript -script=Scripts/build_ce_skinned_masters.py

The file is tools/level/ce_vehicle_materials.py's, planned with --masters: each
entry's parent names a copy to make, of the master of the same name under
/Game/MJOLNIR/CE (MJ_CE_MASTERS overrides that folder).

A cooked game cannot add a usage to a material, and a material without skeletal
usage has no shaders for the GPU skin vertex factories: a skinned mesh falls
back to the default material. These copies carry the usage, cook with their own
shaders, and leave the runtime pack's masters and every level that uses them
untouched. They sit in their own chunk (MJ_CE_SKINNED_CHUNK, default 989), whose
number has to stay in the container's file name for its shader library to open.
The default textures stay the runtime pack's.
"""
import json
import os

import unreal

mel = unreal.MaterialEditingLibrary
eal = unreal.EditorAssetLibrary
tools = unreal.AssetToolsHelpers.get_asset_tools()

source = os.environ.get("MJ_CE_MASTERS", "/Game/MJOLNIR/CE").rstrip("/")
chunk = int(os.environ.get("MJ_CE_SKINNED_CHUNK", "989"))
plan = json.load(open(os.environ["MJ_CE_INSTANCES"], encoding="utf-8"))

parents = sorted({e["parent"].split(".")[0] for e in plan["instances"]})
folder = parents[0].rsplit("/", 1)[0]
if any(p.rsplit("/", 1)[0] != folder for p in parents) or folder == source:
    raise RuntimeError(f"plan the instances with --masters: {parents}")

for parent in parents:
    leaf = parent.rsplit("/", 1)[1]
    if eal.does_asset_exist(parent):
        eal.delete_asset(parent)
    material = eal.duplicate_asset(f"{source}/{leaf}", parent)
    if material is None:
        raise RuntimeError(f"no master {source}/{leaf}")
    material.set_editor_property("used_with_skeletal_mesh", True)
    mel.recompile_material(material)
    if not eal.save_loaded_asset(material, False):
        raise RuntimeError(f"could not save {parent}")
    unreal.log(f"MJOLNIR skinned master {parent}: skeletal {material.get_editor_property('used_with_skeletal_mesh')}")

label_path = f"{folder}/PAL_{folder.rsplit('/', 1)[1]}"
if eal.does_asset_exist(label_path):
    eal.delete_asset(label_path)
label = tools.create_asset(label_path.rsplit("/", 1)[1], folder, unreal.PrimaryAssetLabel, unreal.DataAssetFactory())
rules = label.get_editor_property("rules")
rules.set_editor_property("chunk_id", chunk)
rules.set_editor_property("priority", 10)
rules.set_editor_property("apply_recursively", False)
rules.set_editor_property("cook_rule", unreal.PrimaryAssetCookRule.ALWAYS_COOK)
label.set_editor_property("rules", rules)
label.set_editor_property("label_assets_in_my_directory", True)
eal.save_loaded_asset(label)
unreal.log(f"MJOLNIR skinned masters: {len(parents)} in {folder}, chunk {chunk}")
