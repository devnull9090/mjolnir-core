"""The landscape spike (2026-10-11): a bare world with one small Landscape, to
see whether a cooked landscape loads in the game.

    UnrealEditor-Cmd.exe Meteorite.uproject -run=pythonscript -script=Scripts/build_landscape_test.py

Writes /Game/Levels/Halo1/Solo/LTS/LTS (a classic level, no World
Partition, at a mission's /<X>/<X> path the same length as the bare world's
so `mjolnir level bake --world` can rename it to a map's codename) holding a
127 m square landscape of gentle hills (2 x 2 components of 63 quads, 1 m a
quad, +-3 m) on Death Island's beach, and labels the folder for chunk 979.
Its material is our own M_LandTest (a 10 m orange and blue world checker
times a Tint parameter), so the test proves a landscape shader we cook runs
on the game's landscape vertex factory, and that the loader can set a
landscape's parameters (bUseDynamicMaterialInstance).
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

mel = unreal.MaterialEditingLibrary
mat_path = f"{FOLDER}/M_LandTest"
if eal.does_asset_exist(mat_path):
    eal.delete_asset(mat_path)
mat = unreal.AssetToolsHelpers.get_asset_tools().create_asset("M_LandTest", FOLDER, unreal.Material,
                                                              unreal.MaterialFactoryNew())
world_pos = mel.create_material_expression(mat, unreal.MaterialExpressionWorldPosition, -900, 0)
tint = mel.create_material_expression(mat, unreal.MaterialExpressionVectorParameter, -900, 200)
tint.set_editor_property("parameter_name", "Tint")
tint.set_editor_property("default_value", unreal.LinearColor(1, 1, 1, 1))
checker = mel.create_material_expression(mat, unreal.MaterialExpressionCustom, -600, 0)
checker.set_editor_property("code", "float2 c = floor(W.xy / 1000.0); float k = fmod(abs(c.x + c.y), 2.0);"
                            " return lerp(float3(0.9, 0.4, 0.05), float3(0.05, 0.2, 0.8), k) * T.rgb;")
checker.set_editor_property("output_type", unreal.CustomMaterialOutputType.CMOT_FLOAT3)
ins = []
for pin in ("W", "T"):
    ci = unreal.CustomInput()
    ci.set_editor_property("input_name", pin)
    ins.append(ci)
checker.set_editor_property("inputs", ins)
mel.connect_material_expressions(world_pos, "", checker, "W")
mel.connect_material_expressions(tint, "", checker, "T")
mel.connect_material_property(checker, "", unreal.MaterialProperty.MP_BASE_COLOR)
mel.recompile_material(mat)
eal.save_loaded_asset(mat)

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
                                                            comps, comps, 1, quads, heights, mat, [])
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
