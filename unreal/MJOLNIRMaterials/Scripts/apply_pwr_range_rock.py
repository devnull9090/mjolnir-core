"""Tint the render-only exterior cliffs (build_render_only_hism.py) into the distant range's palette.

The cliffs on the range's foothills keep the neutral M_CE_PWRRock tint they were baked with, which
beside the range's cool granite reads as tan sandstone. vista.json `range_rock.RockTint` sets it on
every MI_PWR_ExteriorCliffs_* material instance, read back after the save.

    env PWR_VISTA_CONFIG=<vista.json>
"""
import json
import os

import unreal

eal = unreal.EditorAssetLibrary
mel = unreal.MaterialEditingLibrary
spec = json.loads(open(os.environ["PWR_VISTA_CONFIG"]).read())["range_rock"]
done = []
for folder in ("/Game/MJOLNIR/GrassPilot/Playable", "/Game/MJOLNIR/Landscape/LPW"):
    for path in eal.list_assets(folder, recursive=False):
        if "/MI_PWR_ExteriorCliffs_" not in path:
            continue
        mi = unreal.load_asset(path.split(".")[0])
        for key, value in spec.items():
            mel.set_material_instance_vector_parameter_value(mi, key, unreal.LinearColor(*value))
        if not eal.save_loaded_asset(mi, False):
            raise RuntimeError("Could not save " + path)
        for key, value in spec.items():
            got = mel.get_material_instance_vector_parameter_value(mi, key)
            if max(abs(a - b) for a, b in zip((got.r, got.g, got.b, got.a), value)) > 1e-4:
                raise RuntimeError("Exterior cliff tint did not persist: " + path)
        done.append(path.split(".")[0])
if not done:
    raise RuntimeError("No exterior cliff material instances found")
unreal.log("PWR range rock: " + json.dumps(done))
