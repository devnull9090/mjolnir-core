"""Import one converted CE level's bitmaps and lightmaps.

    set MJ_CE_SPEC=<spec.json>
    UnrealEditor-Cmd.exe Meteorite.uproject -run=pythonscript -script=Scripts/build_ce_level.py

The spec comes from tools/level/ce_material_spec.py:
  {"root": "/Game/MJOLNIR/Levels/<map>",
   "textures": [{"file": "<png>", "name": "T_...", "lightmap": false}, ...],
   ...}
Textures go to <root>/Textures. The spec's materials are for the level
loader, which makes them at runtime over Scripts/build_ce_materials.py's
masters.
"""
import json
import os

import unreal

assets = unreal.AssetToolsHelpers.get_asset_tools()
mel = unreal.MaterialEditingLibrary
eal = unreal.EditorAssetLibrary

spec = json.load(open(os.environ["MJ_CE_SPEC"], encoding="utf-8"))
root = spec["root"]
tex_dir = f"{root}/Textures"
mat_dir = f"{root}/Materials"

# A map with a code of its own (/Game/MJOLNIR/Maps/<CODE>) cooks into a chunk
# of its own, which its map pack ships (docs/map_distribution.md): a label at
# its root, recursive, outside the folders chunk 988 labels, for everything
# below it (textures here, the ambient sounds build_ce_sounds.py adds).
if spec.get("chunk"):
    label_name = "PAL_" + root.rsplit("/", 1)[-1]
    label_path = f"{root}/{label_name}"
    if eal.does_asset_exist(label_path):
        eal.delete_asset(label_path)
    label = assets.create_asset(label_name, root, unreal.PrimaryAssetLabel, unreal.DataAssetFactory())
    rules = label.get_editor_property("rules")
    rules.set_editor_property("chunk_id", int(spec["chunk"]))
    rules.set_editor_property("priority", 10)
    rules.set_editor_property("apply_recursively", True)
    rules.set_editor_property("cook_rule", unreal.PrimaryAssetCookRule.ALWAYS_COOK)
    label.set_editor_property("rules", rules)
    label.set_editor_property("label_assets_in_my_directory", True)
    eal.save_loaded_asset(label)
    unreal.log(f"MJOLNIR: {label_path} puts {root} in chunk {spec['chunk']}")

tasks = []
for t in spec["textures"]:
    task = unreal.AssetImportTask()
    task.set_editor_property("filename", t["file"])
    task.set_editor_property("destination_path", tex_dir)
    task.set_editor_property("destination_name", t["name"])
    task.set_editor_property("replace_existing", True)
    task.set_editor_property("automated", True)
    task.set_editor_property("save", False)
    tasks.append(task)
assets.import_asset_tasks(tasks)

textures = {}
for t in spec["textures"]:
    tex = unreal.load_asset(f"{tex_dir}/{t['name']}")
    if tex is None:
        unreal.log_error(f"MJOLNIR: {t['file']} did not import")
        continue
    # Gamma-space values the material's CE math uses as they are, kept
    # uncompressed (the source bitmaps were already block compressed once).
    tex.set_editor_property("srgb", False)
    tex.set_editor_property("compression_settings", unreal.TextureCompressionSettings.TC_VECTOR_DISPLACEMENTMAP)
    tex.set_editor_property("never_stream", True)
    if t.get("mips"):
        # The DDS carries the bitmap's own mip chain (CE's detail maps fade
        # to grey in theirs); keep it rather than regenerate one.
        tex.set_editor_property("mip_gen_settings", unreal.TextureMipGenSettings.TMGS_LEAVE_EXISTING_MIPS)
    if t.get("lightmap"):
        tex.set_editor_property("mip_gen_settings", unreal.TextureMipGenSettings.TMGS_NO_MIPMAPS)
        tex.set_editor_property("address_x", unreal.TextureAddress.TA_CLAMP)
        tex.set_editor_property("address_y", unreal.TextureAddress.TA_CLAMP)
    if t.get("bake"):
        # lightmap_bake's corners and sun: our own, up to 2048 a page at 8 or
        # 16 times its lightmap, so block compressed (BC1, linear) with mips
        # rather than kept raw (Blood Gulch's pages are ~20M texels).
        tex.set_editor_property("compression_settings", unreal.TextureCompressionSettings.TC_DEFAULT)
        tex.set_editor_property("address_x", unreal.TextureAddress.TA_CLAMP)
        tex.set_editor_property("address_y", unreal.TextureAddress.TA_CLAMP)
    eal.save_loaded_asset(tex)
    textures[t["name"]] = tex

# Textures the spec no longer names (renamed or dropped) would still cook.
wanted = {f"{tex_dir}/{t['name']}" for t in spec["textures"]}
for path in eal.list_assets(tex_dir, recursive=True, include_folder=False):
    if path.split(".")[0] not in wanted:
        eal.delete_asset(path.split(".")[0])

# Material instances are not cooked (the fork serializes them differently;
# see build_ce_materials.py): the level loader builds each slot's dynamic
# instance from the spec at runtime. Clear any left from older builds so the
# cook does not ship them.
for path in eal.list_assets(mat_dir, recursive=True, include_folder=False) if eal.does_directory_exist(mat_dir) else []:
    eal.delete_asset(path.split(".")[0])

unreal.log(f"MJOLNIR CE level: {len(textures)} texture(s) under {root}")
