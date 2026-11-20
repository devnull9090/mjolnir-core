"""Apply the measured, transform-level Southwest road clearing to the existing PWR actors."""

from bisect import bisect_left, bisect_right
from hashlib import sha256
import json
import math
import os
from pathlib import Path
import struct
import sys

import unreal as ue

sys.path.insert(0, str(Path(__file__).resolve().parent))
import apply_pwr_alpine_verges as verges


ROOT = Path(__file__).resolve().parents[3]
MODES = {
    "PWR_SweepForestFloor": ("floor", "PWRSweep_"),
    "PWR_SweepBanks": ("verges", "PWRSweepBank_"),
    "PWR_AlpineVerges": ("alpine-edits", "PWRVerge_"),
}


def find_removed(c, old, rows):
    actual = []
    for i in range(c.get_instance_count()):
        t = c.get_instance_transform(i, True)
        actual.append((t.translation.x, i, verges.pose(t)))
    actual.sort(key=lambda e: e[0])
    xs = [e[0] for e in actual]
    result = []
    for row in rows:
        p = old[row]
        nearby = actual[bisect_left(xs, p[0] - 0.08) : bisect_right(xs, p[0] + 0.08)]
        matches = [
            i
            for _, i, other in nearby
            if math.dist(other[:3], p[:3]) <= 0.08
            and math.dist(other[7:], p[7:]) <= 1.0e-4
            and abs(sum(x * y for x, y in zip(other[3:7], p[3:7]))) > 1.0 - 1.0e-5
        ]
        if len(matches) != 1:
            raise RuntimeError(
                f"Unable to uniquely locate source {row} in {c.get_name()}"
            )
        result.append(matches[0])
    if len(result) != len(set(result)):
        raise RuntimeError("Two source transforms refer to the same plant")
    return sorted(result, reverse=True)


def read_delta(change):
    base = (ROOT / change["source_transforms"]).read_bytes()
    revised = (ROOT / change["target_transforms"]).read_bytes()
    if (
        sha256(base).hexdigest() != change["base_sha256"]
        or sha256(revised).hexdigest() != change["sha256"]
    ):
        raise ValueError("Stale native input for " + change["component"])
    deleted = set(change["removed_indices"])
    retained = b"".join(
        base[i * 40 : (i + 1) * 40] for i in range(len(base) // 40) if i not in deleted
    )
    suffix = revised[len(retained) :]
    if (
        not revised.startswith(retained)
        or len(suffix) != 40 * change["added_count"]
        or sha256(suffix).hexdigest() != change["append_sha256"]
    ):
        raise ValueError("Road cleaning modified a retained transform")
    return list(struct.iter_unpack("<10f", base)), list(
        struct.iter_unpack("<10f", suffix)
    )


def run():
    art = Path(os.environ["PWR_ROAD_DRESSING"])
    verify = os.environ.get("PWR_VERGES_VERIFY") == "1"
    spec = json.loads((art / "road-dressing.json").read_text())
    level = ue.get_editor_subsystem(ue.LevelEditorSubsystem)
    if not level.load_level(verges.WORLD):
        raise RuntimeError("Could not open the Southwest world")
    world = ue.get_editor_subsystem(ue.UnrealEditorSubsystem).get_editor_world()
    components = {
        (a.get_name(), c.get_name()): c for a, c in verges.common.actor_components()
    }
    for change in spec["groups"]:
        c = components[change["actor"], change["component"]]
        old, new = read_delta(change)
        if verify or c.get_instance_count() == change["count"]:
            continue
        if c.get_instance_count() != change["base_count"]:
            raise RuntimeError("Unexpected source instance count for " + c.get_name())
        indices = find_removed(c, old, change["removed_indices"])
        c.modify()
        if indices and not c.remove_instances(indices):
            raise RuntimeError("Cannot clear local shoulder growth in " + c.get_name())
        added = []
        for pose in new:
            xf = ue.Transform()
            xf.translation = ue.Vector(*pose[:3])
            xf.rotation = ue.Quat(*pose[3:7])
            xf.scale3d = ue.Vector(*pose[7:])
            added.append(xf)
        if added:
            c.add_instances(
                added,
                should_return_indices=False,
                world_space=True,
                update_navigation=False,
            )
        if c.get_instance_count() != change["count"]:
            raise RuntimeError("Incorrect output inventory for " + c.get_name())
    # Cross-check every surviving position, basis, material and distance setting,
    # including components outside the edited group list and the existing outcrop split.
    for owner, (folder, prefix) in MODES.items():
        verges.apply(world, art / folder / "verges.json", True, owner, prefix)
    if not verify and not level.save_current_level():
        raise RuntimeError("Failed to save the verified road clear")
    receipt = {
        "groups": len(spec["groups"]),
        "source_sha256": sha256((art / "road-dressing.json").read_bytes()).hexdigest(),
        "actors": list(MODES),
        "verified_after_reopen": verify,
    }
    name = (
        "editor-road-dressing-verified.json"
        if verify
        else "editor-road-dressing-applied.json"
    )
    (art / name).write_text(json.dumps(receipt, indent=2) + "\n")


if __name__ == "__main__":
    run()
