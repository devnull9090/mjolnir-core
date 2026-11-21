"""Place or independently re-open the single rooted bend pine in its PWR authoring map."""

import os
import sys
from pathlib import Path

import unreal as ue

sys.path.insert(0, str(Path(__file__).resolve().parent))
import apply_pwr_alpine_verges as verges


def run():
    art = Path(os.environ["PWR_SWEEP_ART"]).resolve()
    expected = (art / "editor/Meteorite").resolve()
    if (
        Path(ue.Paths.convert_relative_path_to_full(ue.Paths.project_dir())).resolve()
        != expected
    ):
        raise ValueError("The active editor project is outside the requested revision")
    level = ue.get_editor_subsystem(ue.LevelEditorSubsystem)
    if not level.load_level(verges.WORLD):
        raise RuntimeError("Could not open the PWR road authoring world")
    world = ue.get_editor_subsystem(ue.UnrealEditorSubsystem).get_editor_world()
    verges.apply(
        world,
        art / "pine/verges.json",
        os.environ.get("PWR_VERGES_VERIFY") == "1",
        expected_owner="PWR_SweepBendPine",
        prefix="PWRSweepBend_",
    )


if __name__ == "__main__":
    run()
