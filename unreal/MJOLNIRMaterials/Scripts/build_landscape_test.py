"""The landscape spike (2026-10-11): a bare world with one small Landscape, to
see whether a cooked landscape loads in the game.

    UnrealEditor-Cmd.exe Meteorite.uproject -run=pythonscript -script=Scripts/build_landscape_test.py

Writes /Game/Levels/Halo1/Solo/LTS/LTS (a classic level, no World
Partition, at a mission's /<X>/<X> path the same length as the bare world's
so `mjolnir level bake --world` can rename it to a map's codename) holding a
127 m square landscape of gentle hills (2 x 2 components of 63 quads, 1 m a
quad, +-3 m) on Death Island's beach, with the engine's default material,
and labels the folder for chunk 979.
"""
import math

import unreal

PACKAGE = "/Game/Levels/Halo1/Solo/LTS/LTS"
FOLDER = PACKAGE.rsplit("/", 1)[0]
CHUNK = 979
# Death Island's beach, south-west of the test camera; sea level 507.8 cm.
CORNER = unreal.Vector(-6000.0, -21000.0, 600.0)

eal = unreal.EditorAssetLibrary
les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)

if eal.does_asset_exist(PACKAGE):
    eal.delete_asset(PACKAGE)
try:
    ok = les.new_level(PACKAGE, False)
except TypeError:
    ok = les.new_level(PACKAGE)
if not ok:
    raise RuntimeError(f"new_level {PACKAGE} failed")
world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()

quads, comps = 63, 2
size = comps * quads + 1
# z scale 100: 65536 units span 512 m, 32768 is the actor's z.
unit = 51200.0 / 65536.0
heights = []
for y in range(size):
    for x in range(size):
        h = 300.0 * math.sin(x / size * math.pi * 2.0) * math.cos(y / size * math.pi * 1.5)
        heights.append(int(32768 + h / unit))
landscape = unreal.MjolnirUIBuilderLibrary.create_landscape(world, CORNER, unreal.Vector(100.0, 100.0, 100.0),
                                                            comps, comps, 1, quads, heights, None)
if not landscape:
    raise RuntimeError("create_landscape failed")
if not les.save_current_level():
    raise RuntimeError("save_current_level failed")

label_path = f"{FOLDER}/PAL_MJOLNIR_LTS"
if eal.does_asset_exist(label_path):
    eal.delete_asset(label_path)
label = unreal.AssetToolsHelpers.get_asset_tools().create_asset("PAL_MJOLNIR_LTS", FOLDER, unreal.PrimaryAssetLabel,
                                                                unreal.DataAssetFactory())
rules = label.get_editor_property("rules")
rules.set_editor_property("chunk_id", CHUNK)
rules.set_editor_property("apply_recursively", True)
rules.set_editor_property("cook_rule", unreal.PrimaryAssetCookRule.ALWAYS_COOK)
label.set_editor_property("rules", rules)
label.set_editor_property("label_assets_in_my_directory", True)
eal.save_loaded_asset(label)
unreal.log(f"MJOLNIR landscape test built: {landscape.get_name()} in {PACKAGE}")
