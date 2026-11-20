"""Add distance-readable alpine granite to the PWR-only surveyed mesh."""

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
cut = "albedo = lerp(albedo, rock, stone);"
if code.count(cut) != 1:
    raise ValueError("Missing surveyed rock blend in source material")
rock = Path(__file__).with_name("pwr_ridge_granite.ush").read_text()
node.set_editor_property("code", code.replace(cut, rock + "\n" + cut))
lib.recompile_material(mat)
if not assets.save_loaded_asset(mat, False):
    raise ValueError("Could not persist the surveyed mountain material")
unreal.log("PWR saved surveyed alpine granite")
