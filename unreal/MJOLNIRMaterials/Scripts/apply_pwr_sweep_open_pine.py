"""Import a native canopy variation and replace only the registered Southwest pine's mesh."""

import json
import os
import runpy
import sys
from pathlib import Path

import unreal as ue

sys.path.insert(0, str(Path(__file__).resolve().parent))
import apply_pwr_alpine_verges as verges


def run():
    art = Path(os.environ["PWR_SWEEP_ART"]).resolve()
    folder = art / "pine"
    if (
        Path(ue.Paths.convert_relative_path_to_full(ue.Paths.project_dir())).resolve()
        != (art / "editor/Meteorite").resolve()
    ):
        raise ValueError("Wrong PWR editor project")
    spec = json.loads((folder / "canopy.json").read_text())
    verify = os.environ.get("PWR_VERGES_VERIFY") == "1"
    if not verify:
        os.environ.update(
            MJ_PWR_PINE_SOURCE=str(folder / "open-canopy.glb"),
            MJ_PWR_PINE_SHA=spec["glb_sha256"],
            MJ_PWR_PINE_OUT=str(folder),
            MJ_PWR_PINE_OPEN_BEND="1",
        )
        runpy.run_path(
            str(Path(__file__).with_name("build_pwr_mature_pine.py")),
            run_name="__main__",
        )
    levels = ue.get_editor_subsystem(ue.LevelEditorSubsystem)
    if not levels.load_level(verges.WORLD):
        raise RuntimeError("Could not open PWR road world")
    owners = [
        (a, c)
        for a, c in verges.common.actor_components()
        if a.get_name() == "PWR_SweepBendPine" and c.get_name() == "PWRSweepBend_Pine"
    ]
    if len(owners) != 1:
        raise RuntimeError("Expected one existing rooted bend pine")
    a, c = owners[0]
    leaf = spec["target_mesh"]
    wanted = ue.load_asset(leaf)
    old = c.get_editor_property("static_mesh").get_path_name().split(".")[0]
    if not wanted:
        raise RuntimeError("Open crown mesh absent")
    if verify:
        if old != leaf:
            raise RuntimeError("Different pine on editor reopen")
    elif old == spec["original_mesh"]:
        a.modify()
        c.modify()
        if not c.set_static_mesh(wanted):
            raise RuntimeError("Could not replace the one pine mesh")
        if not levels.save_current_level():
            raise RuntimeError("Native canopy instance save failed")
    elif old != leaf:
        raise RuntimeError("Different parent pine in isolated map")
    world = ue.get_editor_subsystem(ue.UnrealEditorSubsystem).get_editor_world()
    verges.apply(
        world, folder / "verges.json", verify, "PWR_SweepBendPine", "PWRSweepBend_"
    )


if __name__ == "__main__":
    run()
