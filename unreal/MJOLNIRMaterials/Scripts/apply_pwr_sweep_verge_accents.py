"""Bake native verge pockets into the existing Warthog road and check them after reload."""

import os
import sys
from pathlib import Path

import unreal as ue

sys.path.insert(0, str(Path(__file__).resolve().parent))
from apply_pwr_alpine_verges import WORLD, apply

if __name__ == "__main__":
    levels = ue.get_editor_subsystem(ue.LevelEditorSubsystem)
    if not levels.load_level(WORLD):
        raise RuntimeError("Could not load the road world")
    art = Path(os.environ["PWR_VERGE_ACCENTS"])
    verify = os.environ.get("PWR_VERGES_VERIFY") == "1"
    apply(
        ue.get_editor_subsystem(ue.UnrealEditorSubsystem).get_editor_world(),
        str(art / "verges.json"),
        verify,
        expected_owner="PWR_SweepVergeAccents",
        prefix="PWRVergeAccent_",
    )
