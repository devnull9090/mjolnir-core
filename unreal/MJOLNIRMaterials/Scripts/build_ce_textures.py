"""Import a folder of CE textures as cooked textures, for what the CE runtime
pack shares between maps (docs/map_distribution.md): the CTF flag's, which
tools/level/ce_flag_textures.py writes.

    set MJ_CE_TEXTURES=<folder of .png>
    set MJ_CE_TEXTURE_ROOT=/Game/MJOLNIR/CE/CTF
    UnrealEditor-Cmd.exe Meteorite.uproject -run=pythonscript -script=Scripts/build_ce_textures.py

Each `<file>.png` becomes `T_<file>` under the root, set up as
build_ce_level.py sets up a map's bitmaps: gamma-space values the CE masters
use as they are, uncompressed, never streamed. The root is under
/Game/MJOLNIR/CE, so PAL_MJOLNIR_CE cooks it into chunk 988 with the masters.
"""
import os

import unreal

assets = unreal.AssetToolsHelpers.get_asset_tools()
eal = unreal.EditorAssetLibrary

src = os.environ["MJ_CE_TEXTURES"]
root = os.environ["MJ_CE_TEXTURE_ROOT"]

names = sorted(f for f in os.listdir(src) if f.lower().endswith(".png"))
tasks = []
for f in names:
    task = unreal.AssetImportTask()
    task.set_editor_property("filename", os.path.join(src, f))
    task.set_editor_property("destination_path", root)
    task.set_editor_property("destination_name", "T_" + os.path.splitext(f)[0])
    task.set_editor_property("replace_existing", True)
    task.set_editor_property("automated", True)
    task.set_editor_property("save", False)
    tasks.append(task)
assets.import_asset_tasks(tasks)

made = 0
for f in names:
    name = "T_" + os.path.splitext(f)[0]
    tex = eal.load_asset(f"{root}/{name}.{name}")
    if not tex:
        unreal.log_error(f"MJOLNIR CE textures: {f} did not import")
        continue
    tex.set_editor_property("srgb", False)
    tex.set_editor_property("compression_settings", unreal.TextureCompressionSettings.TC_VECTOR_DISPLACEMENTMAP)
    tex.set_editor_property("never_stream", True)
    eal.save_loaded_asset(tex)
    made += 1
unreal.log(f"MJOLNIR CE textures: {made} texture(s) under {root}")
