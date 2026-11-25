"""Import Pelican Warfare's voice lines as SoundWaves, chunk 950.

    set MJ_VOICE_DIR=<folder of .wav lines>
    UnrealEditor-Cmd.exe Meteorite.uproject -run=pythonscript -script=Scripts/build_warfare_voice.py

Every <name>.wav in the folder becomes /Game/MJOLNIR/Sounds/Warfare/<name>,
a one-shot ADPCM SoundWave (ADPCM decodes in every Unreal build; the default
Bink needs a plugin the game may not ship). Waves under that root that the
folder no longer has are deleted, and nothing outside the root is touched (the
CE event sounds in /Game/MJOLNIR/Sounds/Events have their own builder). A
label puts the folder in chunk 950 (pakchunk950-MJOLNIRVOICE): MJOLNIRHud's
warfare_voice.lua plays the waves by these paths and stays silent when the
container is not installed.

Why 950: an IoStore container's id is CityHash64 of its cooked name
(`mjolnir packageid --name pakchunk<N>-Windows`), whatever the file is renamed
to, and hub maps are cooked under many numbers (Gephyrophobia's container has
972's id). Whether a shared id stops a container loading is unproven: the
first 972 build failed for another reason (a wave named `_1`, below), and
containers sharing an id (981-983, 988) are installed side by side. 950 was
chosen because no installed container had its id on 2026-11-24.
"""
import os

import unreal

ROOT = "/Game/MJOLNIR/Sounds/Warfare"
CHUNK = 950

assets = unreal.AssetToolsHelpers.get_asset_tools()
eal = unreal.EditorAssetLibrary
src = os.environ["MJ_VOICE_DIR"]
names = sorted(os.path.splitext(f)[0] for f in os.listdir(src) if f.lower().endswith(".wav"))
if not names:
    raise RuntimeError(f"MJOLNIR warfare voice: no .wav in {src}")
# A name ending in _<digits> is stored as a name number, and the game never
# loaded such a wave (cortana_low_altitude_1, 2026-11-24): variants are _a, _b.
numbered = [n for n in names if n.rsplit("_", 1)[-1].isdigit()]
if numbered:
    raise RuntimeError(f"MJOLNIR warfare voice: names must not end in _<digits>: {numbered}")

if eal.does_directory_exist(ROOT):
    for path in eal.list_assets(ROOT, recursive=False):
        base = path.rsplit(".", 1)[0].rsplit("/", 1)[-1]
        if base not in names and not base.startswith("PAL_"):
            eal.delete_asset(path)

tasks = []
for name in names:
    task = unreal.AssetImportTask()
    task.set_editor_property("filename", os.path.join(src, name + ".wav"))
    task.set_editor_property("destination_path", ROOT)
    task.set_editor_property("destination_name", name)
    task.set_editor_property("replace_existing", True)
    task.set_editor_property("automated", True)
    task.set_editor_property("save", False)
    tasks.append(task)
assets.import_asset_tasks(tasks)

waves = []
for name in names:
    wave = eal.load_asset(f"{ROOT}/{name}.{name}")
    if not wave:
        raise RuntimeError(f"MJOLNIR warfare voice: {name} did not import")
    wave.set_editor_property("looping", False)
    wave.set_editor_property("sound_asset_compression_type", unreal.SoundAssetCompressionType.ADPCM)
    eal.save_loaded_asset(wave)
    waves.append(wave)

label_path = f"{ROOT}/PAL_WarfareVoice"
label = eal.load_asset(label_path) if eal.does_asset_exist(label_path) else assets.create_asset(
    "PAL_WarfareVoice", ROOT, unreal.PrimaryAssetLabel, unreal.DataAssetFactory())
rules = label.get_editor_property("rules")
rules.set_editor_property("chunk_id", CHUNK)
rules.set_editor_property("apply_recursively", True)
rules.set_editor_property("cook_rule", unreal.PrimaryAssetCookRule.ALWAYS_COOK)
label.set_editor_property("rules", rules)
label.set_editor_property("label_assets_in_my_directory", False)
label.set_editor_property("explicit_assets", waves)
eal.save_loaded_asset(label)
unreal.log(f"MJOLNIR warfare voice: {len(waves)} SoundWave(s) under {ROOT}, chunk {CHUNK}")
