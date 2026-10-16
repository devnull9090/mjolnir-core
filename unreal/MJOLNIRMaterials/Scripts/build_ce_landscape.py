"""A converted CE map's ground as a Landscape, in a world of its own.

    set MJ_LANDSCAPE=<dir written by tools/level/build_landscape.py>
    powershell -File tools/ue/editor_cmd.ps1 -Script Scripts/build_ce_landscape.py

Reads <dir>/landscape.json and builds /Game/Levels/Halo1/Solo/<NAME>/<NAME>
(MJ_LANDSCAPE_NAME, default LTS: a classic level, its folder labelled for
chunk MJ_LANDSCAPE_CHUNK, default 979): a Landscape from
heights.r16 with holes.r8 its visibility layer, drawn with the B30 ground
master (MJ_LANDSCAPE_MASTER, default /Game/MJOLNIR/CETrial/M_CE_LandscapePBR;
M_CE_Landscape draws CE's look instead; both from build_ce_materials.py),
and the world-space bakes in /Game/MJOLNIR/Landscape/<NAME> (T_LandBase,
T_LandLightmap, T_LandBake, T_LandSunShare, T_LandMask; both folders
labelled for the chunk). MJOLNIRLevelLoader sets the material's textures and
parameters at runtime (level.landscape.pbr, or the ground slot's own for the
CE look); the landscape has dynamic material instances for that.

Then: tools/ue/cook.ps1 -Map /Game/Levels/Halo1/Solo/<NAME>/<NAME> and
tools/level/bake_editor_world.sh, which retargets the cooked world to the
game's property layout and bakes the map around it.
"""
import json
import os
import sys
from array import array

import unreal

# One landscape a map, each its own world, bake folder and chunk (MJ_LANDSCAPE_NAME,
# MJ_LANDSCAPE_CHUNK; Death Island's are the defaults, LTS and 979): two maps
# sharing them would overwrite each other's bakes.
NAME = os.environ.get("MJ_LANDSCAPE_NAME", "LTS")
PACKAGE = f"/Game/Levels/Halo1/Solo/{NAME}/{NAME}"
FOLDER = PACKAGE.rsplit("/", 1)[0]
# The bakes: nothing in the world refers to them (the loader sets them), so
# they live where the project always cooks (DirectoriesToAlwaysCook).
TEXTURES = f"/Game/MJOLNIR/Landscape/{NAME}"
CHUNK = int(os.environ.get("MJ_LANDSCAPE_CHUNK", "979"))
MASTER = os.environ.get("MJ_LANDSCAPE_MASTER", "/Game/MJOLNIR/CETrial/M_CE_LandscapePBR")

src = os.environ.get("MJ_LANDSCAPE")
if not src:
    raise RuntimeError("set MJ_LANDSCAPE to a build_landscape.py output folder")
spec = json.load(open(os.path.join(src, "landscape.json"), encoding="utf-8"))

eal = unreal.EditorAssetLibrary
les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
tools = unreal.AssetToolsHelpers.get_asset_tools()

# Fresh folders: the world and its label, the bakes and theirs. The asset
# registry gathers in the background at startup: unscanned, the old world
# was not found to delete, and new_level then refused the path ("an asset
# already exists"), for whichever map's folder the gather had not reached
# (Ice Fields, then Yoyorast, 2026-10-16). So scan first, and take what is
# left off the disk.
les.new_level("/Game/__MJOLNIR_Scratch")
unreal.AssetRegistryHelpers.get_asset_registry().scan_paths_synchronous([FOLDER, TEXTURES], True)
for folder in (FOLDER, TEXTURES):
    if eal.does_directory_exist(folder):
        eal.delete_directory(folder)
disk = os.path.join(unreal.Paths.project_content_dir(), FOLDER[len("/Game/"):])
for leaf in (f"{NAME}.umap", f"PAL_MJOLNIR_{NAME}.uasset"):
    path = os.path.join(disk, leaf)
    if os.path.exists(path):
        unreal.log_warning(f"removing {path} the editor left")
        os.remove(path)
master = unreal.load_asset(MASTER)
if not master:
    raise RuntimeError(f"no landscape master at {MASTER} (build_ce_materials.py with MJ_CE_ROOT)")


def import_texture(file, name):
    task = unreal.AssetImportTask()
    task.set_editor_property("filename", file)
    task.set_editor_property("destination_path", TEXTURES)
    task.set_editor_property("destination_name", name)
    task.set_editor_property("replace_existing", True)
    task.set_editor_property("automated", True)
    task.set_editor_property("save", False)
    tools.import_asset_tasks([task])
    tex = unreal.load_asset(f"{TEXTURES}/{name}")
    # As the CE masters read every CE bitmap (build_ce_materials.py
    # ce_texture_settings): gamma values used as they are, BGRA8. The bakes
    # cover the landscape exactly, so they clamp.
    tex.set_editor_property("srgb", False)
    tex.set_editor_property("compression_settings", unreal.TextureCompressionSettings.TC_VECTOR_DISPLACEMENTMAP)
    tex.set_editor_property("never_stream", True)
    tex.set_editor_property("address_x", unreal.TextureAddress.TA_CLAMP)
    tex.set_editor_property("address_y", unreal.TextureAddress.TA_CLAMP)
    eal.save_loaded_asset(tex)
    return tex


# The bakes, as build_landscape.py names them in the loader's material. The
# landscape draws with the master itself: a cooked material instance is a
# package of its own, in stock UE's property layout, which the game misreads
# (only the world is retargeted, tools/level/bake_editor_world.sh).
for param, file in spec["textures"].items():
    import_texture(os.path.join(src, file), f"T_Land{param}")
# The hole mask for the terrain mesh's ground slots: a texel a vertex, read
# bilinear at the top mip only.
for name, file in (spec.get("masks") or {}).items():
    tex = import_texture(os.path.join(src, file), f"T_{name}")
    tex.set_editor_property("mip_gen_settings", unreal.TextureMipGenSettings.TMGS_NO_MIPMAPS)
    eal.save_loaded_asset(tex)

try:
    ok = les.new_level(PACKAGE, False)
except TypeError:
    ok = les.new_level(PACKAGE)
if not ok:
    raise RuntimeError(f"new_level {PACKAGE} failed")
world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
size = spec["size"]
heights = array("H")
with open(os.path.join(src, spec["heights"]), "rb") as f:
    heights.frombytes(f.read())
if sys.byteorder != "little":
    heights.byteswap()
if len(heights) != size * size:
    raise RuntimeError(f"{spec['heights']}: {len(heights)} samples, want {size} x {size}")
holes = []
if spec.get("holes"):
    with open(os.path.join(src, spec["holes"]), "rb") as f:
        holes = list(f.read())
landscape = unreal.MjolnirUIBuilderLibrary.create_landscape(
    world, unreal.Vector(*spec["location"]), unreal.Vector(*spec["scale"]), spec["components"], spec["components"],
    spec["sections"], spec["quads"], heights.tolist(), master, holes)
if not landscape:
    raise RuntimeError("create_landscape failed")
if not les.save_current_level():
    raise RuntimeError("save_current_level failed")

# Labels are primary assets, named apart: one name in two folders is one id,
# and the second label would be the only one.
for folder, name in ((FOLDER, f"PAL_MJOLNIR_{NAME}"), (TEXTURES, f"PAL_MJOLNIR_{NAME}Bakes")):
    label = tools.create_asset(name, folder, unreal.PrimaryAssetLabel, unreal.DataAssetFactory())
    rules = label.get_editor_property("rules")
    rules.set_editor_property("chunk_id", CHUNK)
    rules.set_editor_property("apply_recursively", True)
    rules.set_editor_property("cook_rule", unreal.PrimaryAssetCookRule.ALWAYS_COOK)
    label.set_editor_property("rules", rules)
    label.set_editor_property("label_assets_in_my_directory", True)
    eal.save_loaded_asset(label)
unreal.log(f"MJOLNIR CE landscape built: {spec['components']}^2 components from {src} in {PACKAGE}")
