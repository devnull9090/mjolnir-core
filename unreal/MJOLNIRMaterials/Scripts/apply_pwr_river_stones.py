"""Bake or verify the river stones (levels/warfare/pwr/visual_dressing/river_stones.py) into the
PWR authoring map, as the meadow life is baked: static instances, nothing at load.

PWR_RIVER_STONES = the generator's output folder (verges.json, verges.bin, .xfN).
PWR_RIVER_STONES_VERIFY=1 only verifies. A bake first removes an earlier PWR_RiverStones actor.
"""
import os
import sys
from pathlib import Path

import unreal as ue

sys.path.insert(0, str(Path(__file__).resolve().parent))
from apply_pwr_alpine_verges import WORLD, apply  # noqa: E402

OWNER, PREFIX = "PWR_RiverStones", "PWRRiverStone_"

if __name__ == "__main__":
    if not ue.get_editor_subsystem(ue.LevelEditorSubsystem).load_level(WORLD):
        raise RuntimeError("Could not load the PWR level")
    world = ue.get_editor_subsystem(ue.UnrealEditorSubsystem).get_editor_world()
    verify = os.environ.get("PWR_RIVER_STONES_VERIFY") == "1"
    if not verify:
        actors = ue.get_editor_subsystem(ue.EditorActorSubsystem)
        old = [a for a in actors.get_all_level_actors() if a.get_name() == OWNER]
        for a in old:
            actors.destroy_actor(a)
        if old:
            ue.log(f"river stones: removed {len(old)} earlier {OWNER} actor(s)")
    apply(world, Path(os.environ["PWR_RIVER_STONES"]) / "verges.json", verify, expected_owner=OWNER, prefix=PREFIX)
    ue.log("river stones: " + ("verified" if verify else "baked"))
