"""Add distance-readable alpine granite, crisp snow and tundra to the PWR-only surveyed mesh.

Rebuilt from the source material's code every run (idempotent): pwr_ridge_granite.ush goes in
before the rock blend, pwr_ridge_alpine.ush before the snow blend.
"""

from pathlib import Path
import unreal

assets = unreal.EditorAssetLibrary
lib = unreal.MaterialEditingLibrary
source = "/Game/MJOLNIR/World/PWR/Surfaces/M_CE_AlpineApron"
target = "/Game/MJOLNIR/GrassPilot/Playable/M_PWR_AlpineRidges"
mat = (
    unreal.load_asset(target)
    if assets.does_asset_exist(target)
    else assets.duplicate_asset(source, target)
)
if not mat:
    raise ValueError("Could not copy the existing alpine material")
original = lib.get_material_property_input_node(
    unreal.load_asset(source), unreal.MaterialProperty.MP_BASE_COLOR
)
node = lib.get_material_property_input_node(mat, unreal.MaterialProperty.MP_BASE_COLOR)
code = original.get_editor_property("code")
here = Path(__file__).parent
for cut, insert in (("albedo = lerp(albedo, rock, stone);", "pwr_ridge_granite.ush"),
                    ("albedo = lerp(albedo, snowD, snow);", "pwr_ridge_alpine.ush")):
    if code.count(cut) != 1:
        raise ValueError("Missing insertion point in source material: " + cut)
    code = code.replace(cut, (here / insert).read_text() + "\n" + cut)
node.set_editor_property("code", code)
lib.recompile_material(mat)
if not assets.save_loaded_asset(mat, False):
    raise ValueError("Could not persist the surveyed mountain material")
unreal.log("PWR saved surveyed alpine granite, snow and tundra")
