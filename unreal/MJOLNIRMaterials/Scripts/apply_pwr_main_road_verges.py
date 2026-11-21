"""Save and verify the editor-PCG asphalt verge instances in the native level."""

import os
import sys
from pathlib import Path

import unreal as ue

sys.path.insert(0, str(Path(__file__).resolve().parent))
from apply_pwr_alpine_verges import WORLD, apply

if __name__ == "__main__":
    levels = ue.get_editor_subsystem(ue.LevelEditorSubsystem)
    if not levels.load_level(WORLD):
        raise RuntimeError("Could not load the road level")
    world = ue.get_editor_subsystem(ue.UnrealEditorSubsystem).get_editor_world()
    if "PWR_MAIN_ROAD_EDGE" in os.environ:
        folder = Path(os.environ["PWR_MAIN_ROAD_EDGE"])
        owner, prefix = "PWR_MainRoadEdgeGravel", "PWRMainRoadEdge_"
    else:
        folder = Path(os.environ["PWR_MAIN_ROAD_VERGES"])
        owner, prefix = "PWR_MainRoadVerges", "PWRMainRoadVerge_"
    apply(
        world,
        folder / "verges.json",
        os.environ.get("PWR_VERGES_VERIFY") == "1",
        expected_owner=owner,
        prefix=prefix,
    )
