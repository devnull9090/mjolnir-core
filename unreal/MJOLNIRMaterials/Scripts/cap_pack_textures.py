"""Cap a content pack's textures so a map that uses it stays small.

    $env:MJ_CAP_ROOTS = "/Game/Namaqualand"
    $env:MJ_CAP_SIZE = "1024"
    powershell -File tools/ue/editor_cmd.ps1 -Script Scripts/cap_pack_textures.py

Poly Haven's Namaqualand ships 4K maps for plants a hand across: cooked
as they come, Coagulation's flowers, succulents and stones added 1.1 GB to
its landscape container (2026-11-12). This sets Maximum Texture Size on
every Texture2D under the roots that is larger and saves it; the source
art in the package is kept, so a larger cap can be set again later.
Cube maps (the pack's HDRIs) are left alone: nothing of ours names them.
"""
import os

import unreal

ROOTS = [r for r in os.environ.get("MJ_CAP_ROOTS", "").split(";") if r]
SIZE = int(os.environ.get("MJ_CAP_SIZE", "1024"))
if not ROOTS:
    raise RuntimeError("set MJ_CAP_ROOTS")

registry = unreal.AssetRegistryHelpers.get_asset_registry()
eal = unreal.EditorAssetLibrary
# The commandlet can reach here before the registry has read the pack.
registry.scan_paths_synchronous(ROOTS, True)
changed = kept = 0
for root in ROOTS:
    for data in registry.get_assets_by_path(root, recursive=True):
        if str(data.asset_class_path.asset_name) != "Texture2D":
            continue
        texture = data.get_asset()
        current = texture.get_editor_property("max_texture_size")
        if max(texture.blueprint_get_size_x(), texture.blueprint_get_size_y()) <= SIZE or (0 < current <= SIZE):
            kept += 1
            continue
        texture.set_editor_property("max_texture_size", SIZE)
        if not eal.save_loaded_asset(texture):
            raise RuntimeError(f"could not save {data.package_name}")
        changed += 1
unreal.log(f"MJOLNIR cap textures: {changed} capped at {SIZE}, {kept} already within it")
