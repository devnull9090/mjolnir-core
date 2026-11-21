"""Build Pelican Warfare's material parents and their private texture defaults in chunk 956."""
import json
import os
from pathlib import Path
import runpy

import unreal


PROJECT = Path(unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_dir()))
REPO = PROJECT.parents[1]
OUT = REPO / "out/pwr/world-surfaces"
ROOT = "/Game/MJOLNIR/World/PWR/Surfaces"
LAYERS = REPO / "out/pwr/visual-v6/surface/apron"
GRAPHIC = REPO / "out/pwr/visual-v8/paving/graphic.json"
PAVING = REPO / "out/pwr/visual-v5/paving-materials-v3/textures"


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    apron = LAYERS / json.loads((LAYERS / "geology.json").read_text())["texture"]
    for path in (apron, GRAPHIC, PAVING / "diagonal-normal.png", PAVING / "diagonal-orhg.png"):
        if not path.is_file():
            raise FileNotFoundError(path)
    os.environ.update(MJ_CE_LIBRARY="1", MJ_CE_ROOT=ROOT, MJ_CE_CHUNK="956",
                      MJ_PWR_APRON_FIELD=str(apron), MJ_PWR_PAVING_GRAPHIC=str(GRAPHIC),
                      MJ_PWR_PAVING_TEXTURES=str(PAVING))
    material = runpy.run_path(str(PROJECT / "Scripts/build_ce_materials.py"))
    white_png = OUT / "white.png"
    material["write_png"](str(white_png), (255, 255, 255, 255))
    white = material["import_texture"](str(white_png), ROOT, "T_CE_White")
    material["ce_texture_settings"](white)
    library = unreal.EditorAssetLibrary
    library.save_loaded_asset(white)
    defaults = {"T_CE_White": white}
    for build in ("build_alpine_apron", "build_pwr_rock", "build_pwr_paving"):
        material[build](defaults)

    names = ["M_CE_AlpineApron", "M_CE_PWRRock", "M_CE_PWRPaving", "T_CE_White",
             "T_PWR_ApronField", "T_PWR_PavingData", "T_PWR_PavingNormal", "T_PWR_PavingGraphic"]
    objects = [library.load_asset(f"{ROOT}/{name}") for name in names]
    if not all(objects):
        raise RuntimeError("Missing one of the PWR surface assets")
    label = material["fresh"](ROOT, "PAL_PWR_Surfaces956", unreal.PrimaryAssetLabel, unreal.DataAssetFactory())
    rules = label.get_editor_property("rules")
    rules.set_editor_properties({"chunk_id": 956, "priority": 1000, "apply_recursively": False,
                                "cook_rule": unreal.PrimaryAssetCookRule.ALWAYS_COOK})
    label.set_editor_properties({"rules": rules, "explicit_assets": objects, "label_assets_in_my_directory": False})
    library.save_loaded_asset(label)
    (OUT / "editor-assets.json").write_text(json.dumps([f"{ROOT}/{name}" for name in names], indent=2))


main()
