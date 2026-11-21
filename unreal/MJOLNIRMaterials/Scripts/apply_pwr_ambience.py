"""Import PWR's ambient loops (visual_dressing/ambience.json `waves`) as looping SoundWaves.

    env PWR_AMBIENCE=<ambience.json>  PWR_AMBIENCE_SOUNDS=<folder of <wave name>.wav>

Each wave lands under the palette's root (the map's own content, cooked into LAND) under its
palette name, marked looping, read back. The game plays them through Unreal's audio engine,
spawned by MJOLNIRLevelLoader from level.json environment.sounds (tools/level/flux_ambience.py).
Only the named waves are touched; nothing else in the folder is deleted.
"""
import json
import os

import unreal

eal = unreal.EditorAssetLibrary
palette = json.loads(open(os.environ["PWR_AMBIENCE"]).read())
src = os.environ["PWR_AMBIENCE_SOUNDS"]
root = palette["root"].rstrip("/")
tasks = []
for name in palette["waves"]:
    path = os.path.join(src, name + ".wav")
    if not os.path.isfile(path):
        raise RuntimeError("Missing ambience source " + path)
    task = unreal.AssetImportTask()
    task.set_editor_property("filename", path)
    task.set_editor_property("destination_path", root)
    task.set_editor_property("destination_name", name)
    task.set_editor_property("replace_existing", True)
    task.set_editor_property("automated", True)
    task.set_editor_property("save", False)
    tasks.append(task)
unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks(tasks)
done = {}
for name in palette["waves"]:
    wave = eal.load_asset(f"{root}/{name}.{name}")
    if not isinstance(wave, unreal.SoundWave):
        raise RuntimeError("Ambience import failed: " + name)
    wave.set_editor_property("looping", True)
    # ADPCM decodes in every Unreal build; the project default (Bink) needs a plugin this
    # project lacks (build_ce_sounds.py does the same for converted maps).
    wave.set_editor_property("sound_asset_compression_type", unreal.SoundAssetCompressionType.ADPCM)
    if not eal.save_loaded_asset(wave, False) or not wave.get_editor_property("looping"):
        raise RuntimeError("Could not save looping " + name)
    done[name] = round(wave.get_editor_property("duration"), 2)
unreal.log("PWR ambience: " + json.dumps(done))
