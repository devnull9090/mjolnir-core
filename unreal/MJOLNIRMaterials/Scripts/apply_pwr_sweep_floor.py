"""Import and independently verify Southwest Sweep's native ground-cover transforms."""

import os
from pathlib import Path
import json
import struct
import sys

import unreal as ue

sys.path.insert(0, str(Path(__file__).resolve().parent))
from apply_pwr_alpine_verges import WORLD, apply, common


def append_gravel(path):
    receipt = path.parent / "gravel-edit.json"
    if not receipt.is_file():
        return
    edits = json.loads(receipt.read_text())["groups"]
    spec = json.loads(path.read_text())
    components = {
        c.get_name(): c
        for actor, c in common.actor_components()
        if actor.get_name() == spec["actor"]
    }
    if not components:
        # On a fresh level the common importer below builds every group directly.
        return
    for index, row in enumerate(spec["groups"], 1):
        if row["key"] not in edits:
            continue
        change = edits[row["key"]]
        c = components["PWRSweep_" + row["key"]]
        if c.get_instance_count() == row["count"]:
            continue
        if (
            c.get_instance_count() != change["base_count"]
            or change["count"] != row["count"]
        ):
            raise RuntimeError("Unexpected previous stone inventory in " + row["key"])
        raw = (path.parent / (spec["file"] + f".xf{index}")).read_bytes()
        added = raw[change["base_count"] * 40 :]
        transforms = []
        for pose in struct.iter_unpack("<10f", added):
            t = ue.Transform()
            t.translation = ue.Vector(*pose[:3])
            t.rotation = ue.Quat(*pose[3:7])
            t.scale3d = ue.Vector(*pose[7:])
            transforms.append(t)
        c.modify()
        c.add_instances(
            transforms,
            should_return_indices=False,
            world_space=True,
            update_navigation=False,
        )


if __name__ == "__main__":
    level = ue.get_editor_subsystem(ue.LevelEditorSubsystem)
    if not level.load_level(WORLD):
        raise RuntimeError("Could not load the PWR source world")
    spec_path = Path(
        os.environ.get(
            "PWR_SWEEP_VERGES",
            str(common.ROOT / "out/pwr/sweep-polish/verges/verges.json"),
        )
    )
    verify = os.environ.get("PWR_VERGES_VERIFY") == "1"
    if not verify:
        append_gravel(spec_path)
    apply(
        ue.get_editor_subsystem(ue.UnrealEditorSubsystem).get_editor_world(),
        str(spec_path),
        verify,
        expected_owner="PWR_SweepForestFloor",
        prefix="PWRSweep_",
    )
    if (
        not verify
        and (spec_path.parent / "gravel-edit.json").is_file()
        and not level.save_current_level()
    ):
        raise RuntimeError("Could not save the appended native gravel")
