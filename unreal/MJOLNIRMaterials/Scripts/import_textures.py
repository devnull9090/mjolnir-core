"""Import listed bitmaps as CE textures (gamma values as they are: no sRGB
decode, BC7), for converted content the level build did not import itself:
a moving prop's Halo 2 stencil drawn as a 2x multiply (M_CE_PropOverlay)
needs the stencil as it is, where the level imported only its darkening
`__overlay` copy (tools/level/h2_physics_props.py).

    MJ_IMPORT=<list.json> UnrealEditor-Cmd ... -script=Scripts/import_textures.py

list.json: [{"file": "<png>", "dest": "/Game/MJOLNIR/Maps/ZAN/Textures", "name": "T_..."}].
"""
import json
import os

import unreal

assets = unreal.AssetToolsHelpers.get_asset_tools()
eal = unreal.EditorAssetLibrary
items = json.load(open(os.environ["MJ_IMPORT"], encoding="utf-8"))
done = 0
for it in items:
    task = unreal.AssetImportTask()
    task.set_editor_property("filename", it["file"])
    task.set_editor_property("destination_path", it["dest"])
    task.set_editor_property("destination_name", it["name"])
    task.set_editor_property("replace_existing", True)
    task.set_editor_property("automated", True)
    task.set_editor_property("save", False)
    assets.import_asset_tasks([task])
    tex = unreal.load_asset(f"{it['dest']}/{it['name']}")
    if not tex:
        unreal.log_error(f"MJOLNIR import: {it['file']} did not import")
        continue
    tex.set_editor_property("srgb", False)
    tex.set_editor_property("compression_settings", unreal.TextureCompressionSettings.TC_BC7)
    eal.save_loaded_asset(tex)
    done += 1
unreal.log(f"MJOLNIR import: {done} of {len(items)} texture(s)")
