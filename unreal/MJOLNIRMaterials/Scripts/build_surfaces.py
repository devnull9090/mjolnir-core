"""Import PBR surfaces the structure dressing draws walls with.

    $env:MJ_SURFACES = "C:/haloce/ce_conversions/polyhaven"
    $env:MJ_SURFACE_NAMES = "concrete_wall_008;concrete_wall_003"
    powershell -File tools/ue/editor_cmd.ps1 -Script Scripts/build_surfaces.py

A converted map's structure walls (Zanzibar's sea wall) are one small CE or
Halo 2 colour map stretched over tens of metres. MJOLNIRLevelLoader's
Land.structures draws named shaders with the cliffs' master instead
(M_CE_CliffPBR: a surface projected in world space, the map's own base map
kept as its colour and its lightmap as its light), and these are the
surfaces: Poly Haven textures (CC0), three maps a surface as the game's
Megascans rock has them.

For each name, from the folder:
    <name>_diffuse.jpg   -> T_<name>_D   colour, sRGB
    <name>_nor_dx.png    -> T_<name>_N   normal map (DirectX)
    <name>_orh.png       -> T_<name>_O   occlusion, roughness, height in
                                         R, G, B (packed from the pack's arm
                                         and displacement maps), linear
under /Game/MJOLNIR/CETrial/Surfaces, which cooks with the trial masters
(chunk 983). Each is capped at 2048.
"""
import os

import unreal

SRC = os.environ.get("MJ_SURFACES", "")
NAMES = [n for n in os.environ.get("MJ_SURFACE_NAMES", "").split(";") if n]
DEST = "/Game/MJOLNIR/CETrial/Surfaces"
if not SRC or not NAMES:
    raise RuntimeError("set MJ_SURFACES and MJ_SURFACE_NAMES")

tools = unreal.AssetToolsHelpers.get_asset_tools()
eal = unreal.EditorAssetLibrary
TC = unreal.TextureCompressionSettings


def import_texture(file, name, srgb, compression):
    if not os.path.isfile(file):
        raise RuntimeError(f"missing {file}")
    task = unreal.AssetImportTask()
    task.set_editor_property("filename", file)
    task.set_editor_property("destination_path", DEST)
    task.set_editor_property("destination_name", name)
    task.set_editor_property("replace_existing", True)
    task.set_editor_property("automated", True)
    task.set_editor_property("save", False)
    tools.import_asset_tasks([task])
    tex = unreal.load_asset(f"{DEST}/{name}")
    if not tex:
        raise RuntimeError(f"{name} did not import from {file}")
    tex.set_editor_property("srgb", srgb)
    tex.set_editor_property("compression_settings", compression)
    tex.set_editor_property("max_texture_size", 2048)
    tex.set_editor_property("address_x", unreal.TextureAddress.TA_WRAP)
    tex.set_editor_property("address_y", unreal.TextureAddress.TA_WRAP)
    if not eal.save_loaded_asset(tex):
        raise RuntimeError(f"could not save {name}")
    return tex


for name in NAMES:
    import_texture(os.path.join(SRC, f"{name}_diffuse.jpg"), f"T_{name}_D", True, TC.TC_DEFAULT)
    import_texture(os.path.join(SRC, f"{name}_nor_dx.png"), f"T_{name}_N", False, TC.TC_NORMALMAP)
    import_texture(os.path.join(SRC, f"{name}_orh.png"), f"T_{name}_O", False, TC.TC_MASKS)
    unreal.log(f"MJOLNIR surfaces: {name} imported")
unreal.log("MJOLNIR surfaces: built")
