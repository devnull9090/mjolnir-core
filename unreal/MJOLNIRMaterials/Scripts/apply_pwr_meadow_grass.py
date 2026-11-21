"""Replace GT_PWRPilot's grass varieties with a richer meadow mix and rebuild the saved grass maps.

PWR_MEADOW_GRASS = grass-mix.json (levels/warfare/pwr/visual_dressing, meadow-life round notes).
PWR_MEADOW_GRASS_MODE = build (needs -AllowCommandletRendering -DisablePlugins=MjolnirForkLayouts)
                        or verify (a fresh process; reads the saved grass data without building).
The landscape material, density texture and canyon override material stay as they are; only the
variety list changes. Varieties keep the pilot's grid, jitter, rotation and shadow settings, copied
from the shipped first variety.
"""
import json
import os
import sys
from pathlib import Path

import unreal as ue

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pwr_wind_meadow as common
from apply_pwr_alpine_verges import WORLD

config = json.loads(Path(os.environ["PWR_MEADOW_GRASS"]).read_text(encoding="utf-8"))
mode = os.environ.get("PWR_MEADOW_GRASS_MODE", "build")
eal = ue.EditorAssetLibrary
levels = ue.get_editor_subsystem(ue.LevelEditorSubsystem)
actors = ue.get_editor_subsystem(ue.EditorActorSubsystem)
if not levels.load_level(WORLD):
    raise RuntimeError("Could not load the PWR level")
lands = [a for a in actors.get_all_level_actors() if isinstance(a, ue.Landscape)]
if len(lands) != 1:
    raise RuntimeError(f"Expected one Landscape, got {len(lands)}")
land = lands[0]
grass = ue.load_asset(config["grass_type"])
if not grass:
    raise RuntimeError("GT_PWRPilot missing")


def readback():
    out = []
    for v in grass.get_editor_property("grass_varieties"):
        out.append(dict(mesh=v.get_editor_property("grass_mesh").get_path_name(),
                        density=v.get_editor_property("grass_density").get_editor_property("default"),
                        cull=[v.get_editor_property(k).get_editor_property("default") for k in ("start_cull_distance", "end_cull_distance")],
                        min_lod=v.get_editor_property("min_lod"),
                        overrides=[m.get_path_name() for m in v.get_editor_property("override_materials")]))
    return out


if mode == "build" and config.get("density_png"):
    # Replace the pilot's density texture in place (same asset, same import settings as
    # build_pwr_landscape_grass_pilot.py), so the grass reaches the extended field.
    folder = config["grass_type"].rsplit("/", 1)[0]
    task = ue.AssetImportTask()
    task.set_editor_property("filename", str(Path(os.environ["PWR_MEADOW_GRASS"]).with_name(config["density_png"])))
    task.set_editor_property("destination_path", folder)
    task.set_editor_property("destination_name", "T_PWRPilotDensity")
    task.set_editor_property("automated", True)
    task.set_editor_property("replace_existing", True)
    task.set_editor_property("save", False)
    ue.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])
    texture = ue.load_asset(folder + "/T_PWRPilotDensity")
    if not texture:
        raise RuntimeError("Density texture reimport failed")
    texture.set_editor_property("srgb", False)
    texture.set_editor_property("compression_settings", ue.TextureCompressionSettings.TC_VECTOR_DISPLACEMENTMAP)
    texture.set_editor_property("never_stream", True)
    texture.set_editor_property("mip_gen_settings", ue.TextureMipGenSettings.TMGS_NO_MIPMAPS)
    texture.set_editor_property("filter", ue.TextureFilter.TF_NEAREST)
    texture.set_editor_property("address_x", ue.TextureAddress.TA_CLAMP)
    texture.set_editor_property("address_y", ue.TextureAddress.TA_CLAMP)
    if not eal.save_loaded_asset(texture):
        raise RuntimeError("Could not save the density texture")
    ue.log("meadow grass: density texture replaced from " + config["density_png"])
    # UE hashes a grass map from the landscape material's state, heightmap and weightmaps, not from
    # textures the material samples (LandscapeGrassMapsBuilder.cpp, ComputeGrassMapGenerationHash),
    # so a new density texture alone leaves every grass map "up to date". Recompiling the master gives
    # it a new StateId, which marks the maps outdated and makes BuildGrassMaps render them again.
    master = ue.load_asset(folder + "/M_PWRPilot")
    if not isinstance(master, ue.Material):
        raise RuntimeError("M_PWRPilot missing")
    ue.MaterialEditingLibrary.recompile_material(master)
    if not eal.save_loaded_asset(master):
        raise RuntimeError("Could not save M_PWRPilot")
    ue.log("meadow grass: landscape master recompiled; grass maps now outdated")

if mode == "build":
    old = list(grass.get_editor_property("grass_varieties"))
    template = old[0]
    canyon_override = list(template.get_editor_property("override_materials"))
    varieties = []
    for row in config["varieties"]:
        mesh = ue.load_asset(row["mesh"]) or common.standin(row)
        if not mesh or mesh.get_path_name() != row["mesh"]:
            raise RuntimeError("Missing grass mesh " + row["mesh"])
        v = template.copy()
        v.set_editor_property("grass_mesh", mesh)
        density = v.get_editor_property("grass_density")
        density.set_editor_property("default", float(row["density"]))
        v.set_editor_property("grass_density", density)
        lo, hi = row["scale"]
        for axis in ("scale_x", "scale_y", "scale_z"):
            v.set_editor_property(axis, ue.FloatInterval(lo, hi))
        v.set_editor_property("override_materials", canyon_override if row.get("keep_override") else [])
        # Optional per-variety draw distance: a sparse far layer draws out past the dense near grass,
        # locked to a cheap LOD (min_lod) with its wind sway off beyond wpo_disable_cm.
        if row.get("cull_cm"):
            for key, value in zip(("start_cull_distance", "end_cull_distance"), row["cull_cm"]):
                d = v.get_editor_property(key); d.set_editor_property("default", int(value)); v.set_editor_property(key, d)
        if row.get("min_lod") is not None:
            v.set_editor_property("min_lod", int(row["min_lod"]))
        if row.get("wpo_disable_cm") is not None:
            v.set_editor_property("instance_world_position_offset_disable_distance", int(row["wpo_disable_cm"]))
        varieties.append(v)
    grass.set_editor_property("grass_varieties", varieties)
    if not eal.save_loaded_asset(grass):
        raise RuntimeError("Could not save GT_PWRPilot")
    result = json.loads(ue.MjolnirGrassPilotLibrary.read_grass_data(land, grass, True))
    if not levels.save_current_level():
        raise RuntimeError("Could not save the level's grass data")
else:
    result = json.loads(ue.MjolnirGrassPilotLibrary.read_grass_data(land, grass, False))
result["varieties"] = readback()
expected = [r["mesh"] for r in config["varieties"]]
if [r["mesh"] for r in result["varieties"]] != expected:
    raise RuntimeError("GT_PWRPilot varieties differ from the mix")
Path(os.environ["PWR_MEADOW_GRASS"]).with_name(f"grass-{mode}.readback.json").write_text(json.dumps(result, indent=1))
ue.log(f"meadow grass {mode}: {len(expected)} varieties; " + json.dumps({k: result[k] for k in result if k != 'varieties'})[:400])
