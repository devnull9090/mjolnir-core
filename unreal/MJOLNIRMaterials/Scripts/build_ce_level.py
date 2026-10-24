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
import re
import shutil
import tempfile

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

# Unreal takes a file whose name ends in a four-digit number for a UDIM tile
# and stitches it to its numbered siblings into one virtual texture. A
# protected map's bitmaps are named that way (protected_bitm_1459, _1475,
# _1477, ...): Yoyorast's became virtual textures of mismatched blocks, and
# the cook failed on them (2026-10-10). Such a file goes in from a copy
# named otherwise.
UDIM_NAME = re.compile(r"[._]\d{4}$")
renamed = tempfile.mkdtemp(prefix="mjolnir_ce_import_")


def import_source(path):
    stem, ext = os.path.splitext(os.path.basename(path))
    if not UDIM_NAME.search(stem):
        return path
    copy = os.path.join(renamed, stem + "_tex" + ext)
    shutil.copyfile(path, copy)
    return copy


tasks = []
for t in spec["textures"]:
    task = unreal.AssetImportTask()
    task.set_editor_property("filename", import_source(t["file"]))
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
    # One that came in as a UDIM set before (above) keeps the flag on a
    # re-import.
    tex.set_editor_property("virtual_texture_streaming", False)
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
    if t.get("sunmask"):
        # CE's light seen from above, a metre a texel: raw, one mip, clamped
        # (M_CE_SunLight filters it itself).
        tex.set_editor_property("mip_gen_settings", unreal.TextureMipGenSettings.TMGS_NO_MIPMAPS)
        tex.set_editor_property("address_x", unreal.TextureAddress.TA_CLAMP)
        tex.set_editor_property("address_y", unreal.TextureAddress.TA_CLAMP)
    if t.get("authored_pbr"):
        # Authored albedo is sRGB; roughness is linear data. Stream with mips.
        tex.set_editor_property("srgb", t["srgb"])
        tex.set_editor_property("compression_settings", unreal.TextureCompressionSettings.TC_DEFAULT if t["srgb"] else unreal.TextureCompressionSettings.TC_MASKS)
        tex.set_editor_property("never_stream", False)
        tex.set_editor_property("mip_gen_settings", unreal.TextureMipGenSettings.TMGS_FROM_TEXTURE_GROUP)
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

shutil.rmtree(renamed, ignore_errors=True)


# Map-owned masters; no dependency on an unpublished shared runtime shader.
# UV0 and palette values are identical to Blender's authored surface graph.
def build_authored_surface(role, surface):
    name = "M_Authored_" + role
    path = f"{root}/SurfaceMaterials"
    material = unreal.load_asset(f"{path}/{name}")
    if material is None:
        material = assets.create_asset(name, path, unreal.Material, unreal.MaterialFactoryNew())
    mel.delete_all_material_expressions(material)
    material.set_editor_property("two_sided", False)
    def node(cls, **props):
        result = mel.create_material_expression(material, cls)
        for key,value in props.items(): result.set_editor_property(key, value)
        return result
    def connect(source, output, target, pin):
        if not mel.connect_material_expressions(source, output, target, pin):
            raise RuntimeError(f"Authored surface connection failed: {role} / {pin}")
    def output(source, pin, prop):
        if not mel.connect_material_property(source, pin, prop):
            raise RuntimeError(f"Authored surface output failed: {role}")
    def inputs(names):
        result = []
        for name in names:
            entry = unreal.CustomInput()
            entry.set_editor_property("input_name", name)
            result.append(entry)
        return result
    albedo = node(unreal.MaterialExpressionTextureSample, texture=unreal.load_asset(surface["albedo_asset"]), sampler_type=unreal.MaterialSamplerType.SAMPLERTYPE_COLOR)
    rough = node(unreal.MaterialExpressionTextureSample, texture=unreal.load_asset(surface["roughness_map_asset"]), sampler_type=unreal.MaterialSamplerType.SAMPLERTYPE_MASKS)
    tone = node(unreal.MaterialExpressionCustom, code="return lerp(Base, 0.32.xxx, Soften) * Tint;", output_type=unreal.CustomMaterialOutputType.CMOT_FLOAT3)
    tone.set_editor_property("inputs", inputs(("Base", "Soften", "Tint")))
    connect(albedo, "RGB", tone, "Base")
    connect(node(unreal.MaterialExpressionConstant, r=surface["soften"]), "", tone, "Soften")
    connect(node(unreal.MaterialExpressionConstant3Vector, constant=unreal.LinearColor(*surface["tint"],1)), "", tone, "Tint")
    output(tone, "", unreal.MaterialProperty.MP_BASE_COLOR)
    remap = node(unreal.MaterialExpressionCustom, code="return lerp(Low, High, saturate((Rough - 0.30) / 0.30));", output_type=unreal.CustomMaterialOutputType.CMOT_FLOAT1)
    remap.set_editor_property("inputs", inputs(("Rough", "Low", "High")))
    connect(rough, "R", remap, "Rough")
    connect(node(unreal.MaterialExpressionConstant, r=surface["roughness"][0]), "", remap, "Low")
    connect(node(unreal.MaterialExpressionConstant, r=surface["roughness"][1]), "", remap, "High")
    output(remap, "", unreal.MaterialProperty.MP_ROUGHNESS)
    output(node(unreal.MaterialExpressionConstant, r=surface["metallic"]), "", unreal.MaterialProperty.MP_METALLIC)
    mel.recompile_material(material)
    eal.save_loaded_asset(material)

for role,surface in spec.get("authored_surfaces", {}).items():
    build_authored_surface(role, surface)
unreal.log(f"MJOLNIR authored PBR surfaces: {len(spec.get('authored_surfaces', {}))}")

unreal.log(f"MJOLNIR CE level: {len(textures)} texture(s) under {root}")
