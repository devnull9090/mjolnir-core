"""Import one converted CE map's ambient sounds.

    set MJ_CE_SOUNDS=<out dir of tools/level/ce_sounds.py>
    set MJ_CE_SOUND_ROOT=/Game/MJOLNIR/Levels/<map>/Sounds
    UnrealEditor-Cmd.exe Meteorite.uproject -run=pythonscript -script=Scripts/build_ce_sounds.py

Every file under <out dir>/sounds becomes a SoundWave under the root (and so
in chunk 988 under /Game/MJOLNIR/Sounds, or in the map's own chunk under its root). A loop
(`*_loop`) is marked looping; the rest are one-shots. The game plays them
through Unreal's own audio engine, which it runs beside its own (a shipped
FluidFlux SoundWave plays in game), spawned by MJOLNIRLevelLoader.
"""
import json
import os

import unreal

assets = unreal.AssetToolsHelpers.get_asset_tools()
eal = unreal.EditorAssetLibrary

src = os.environ["MJ_CE_SOUNDS"]
root = os.environ["MJ_CE_SOUND_ROOT"]
manifest = json.load(open(os.path.join(src, "sounds.json"), encoding="utf-8"))

# Waves from an earlier import that the map no longer names would linger.
wanted = set()
for info in manifest["sounds"].values():
    wanted.update(os.path.splitext(f)[0] for f in info["files"])
    if info.get("loop"):
        wanted.add(os.path.splitext(info["loop"])[0])
if eal.does_directory_exist(root):
    for path in eal.list_assets(root, recursive=False):
        if path.rsplit(".", 1)[0].rsplit("/", 1)[-1] not in wanted:
            eal.delete_asset(path)

tasks = []
for name in sorted(wanted):
    for ext in (".wav", ".ogg"):
        f = os.path.join(src, "sounds", name + ext)
        if os.path.exists(f):
            break
    else:
        unreal.log_warning(f"MJOLNIR CE sounds: {name} has no file")
        continue
    task = unreal.AssetImportTask()
    task.set_editor_property("filename", f)
    task.set_editor_property("destination_path", root)
    task.set_editor_property("destination_name", name)
    task.set_editor_property("replace_existing", True)
    task.set_editor_property("automated", True)
    task.set_editor_property("save", False)
    tasks.append(task)
assets.import_asset_tasks(tasks)

made = 0
for name in sorted(wanted):
    wave = eal.load_asset(f"{root}/{name}.{name}")
    if not wave:
        unreal.log_error(f"MJOLNIR CE sounds: {name} did not import")
        continue
    wave.set_editor_property("looping", name.endswith("_loop"))
    # ADPCM decodes in every Unreal build; the default (Bink) needs a plugin
    # this project lacks and the game may not ship.
    wave.set_editor_property("sound_asset_compression_type", unreal.SoundAssetCompressionType.ADPCM)
    eal.save_loaded_asset(wave)
    made += 1
unreal.log(f"MJOLNIR CE sounds: {made} SoundWave(s) under {root}")
