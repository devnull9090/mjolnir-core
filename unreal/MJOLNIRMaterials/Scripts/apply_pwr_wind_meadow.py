"""Bake and verify PWR grass in the scratch LPE world, keeping only runtime components."""

import os
from pathlib import Path
import sys
import unreal

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pwr_wind_meadow

loader = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
if not loader.load_level("/Game/Levels/Halo1/Solo/LPE/LPE"):
    raise ValueError("Could not open terrain world")
world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
verify = os.environ.get("PWR_GRASS_VERIFY") == "1"
pwr_wind_meadow.apply(world, os.environ["PWR_WIND_GRASS"], verify=verify)


# UE creates this partition helper automatically when authoring a PCG graph.
# Generated instances already belong to the baked, native foliage actors.
def helpers():
    return [
        a
        for a in actors.get_all_level_actors()
        if a.get_class().get_path_name() == "/Script/PCG.PCGWorldActor"
    ]


if not verify:
    for actor in helpers():
        if not actors.destroy_actor(actor):
            raise RuntimeError("Could not release the PCG authoring actor")
    if not loader.save_current_level():
        raise ValueError("Could not save authored grass")
if helpers():
    raise ValueError("Editor-only PCG helper remained in the playable world")
