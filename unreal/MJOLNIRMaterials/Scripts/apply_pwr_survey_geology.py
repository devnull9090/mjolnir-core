"""Reimport the ridge and playable slope fields, preserving their native linear data settings."""

import os
from pathlib import Path
import unreal

art = Path(os.environ["PWR_SURVEY_RIDGES"])
for folder, name in (
    ("/Game/MJOLNIR/Landscape/LPW", "T_LandBase"),
    ("/Game/MJOLNIR/World/PWR/Surfaces", "T_PWR_ApronField"),
):
    if os.environ.get("PWR_SURVEY_EXTERIOR_ONLY") == "1" and name == "T_LandBase":
        continue
    path = folder + "/" + name
    old = unreal.load_asset(path)
    keys = (
        "srgb",
        "compression_settings",
        "compression_no_alpha",
        "mip_gen_settings",
        "address_x",
        "address_y",
        "virtual_texture_streaming",
        "never_stream",
        "lod_group",
    )
    settings = {key: old.get_editor_property(key) for key in keys}
    if settings["srgb"] or settings["virtual_texture_streaming"]:
        raise ValueError("Expected a native linear geology field at " + path)
    task = unreal.AssetImportTask()
    task.set_editor_properties(
        dict(
            filename=str(art / (name + ".png")),
            destination_path=folder,
            destination_name=name,
            automated=True,
            replace_existing=True,
            replace_existing_settings=False,
            save=False,
        )
    )
    unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])
    tex = unreal.load_asset(path)
    if (
        not task.get_objects()
        or tex.blueprint_get_size_x() != 1024
        or tex.blueprint_get_size_y() != 1024
    ):
        raise ValueError("Bad texture import for " + path)
    tex.set_editor_properties(settings)
    if not unreal.EditorAssetLibrary.save_loaded_asset(tex, False):
        raise RuntimeError("Could not save " + path)
    unreal.log("PWR ridge field saved " + path)
