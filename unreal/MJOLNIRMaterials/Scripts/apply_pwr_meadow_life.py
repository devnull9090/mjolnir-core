"""Bake or verify the meadow-life HISM groups (levels/warfare/pwr/visual_dressing/meadow_life.py).

PWR_MEADOW_LIFE = the generator's output folder (verges.json, verges.bin, .xfN).
PWR_MEADOW_VERIFY=1 only verifies. A bake first removes an earlier PWR_MeadowLife
actor, so a new round replaces the last one instead of adding to it.
"""
import json
import os
import sys
from pathlib import Path

import unreal as ue

sys.path.insert(0, str(Path(__file__).resolve().parent))
from apply_pwr_alpine_verges import WORLD, apply

OWNER, PREFIX = "PWR_MeadowLife", "PWRMeadow_"

if __name__ == "__main__":
    levels = ue.get_editor_subsystem(ue.LevelEditorSubsystem)
    if not levels.load_level(WORLD):
        raise RuntimeError("Could not load the PWR level")
    world = ue.get_editor_subsystem(ue.UnrealEditorSubsystem).get_editor_world()
    folder = Path(os.environ["PWR_MEADOW_LIFE"])
    verify = os.environ.get("PWR_MEADOW_VERIFY") == "1"
    if not verify:
        actors = ue.get_editor_subsystem(ue.EditorActorSubsystem)
        old = [a for a in actors.get_all_level_actors() if a.get_name() == OWNER]
        for a in old:
            actors.destroy_actor(a)
        if old:
            ue.log(f"meadow life: removed {len(old)} earlier {OWNER} actor(s)")
    apply(world, folder / "verges.json", verify, expected_owner=OWNER, prefix=PREFIX)
    for remix in [r for r in os.environ.get("PWR_MEADOW_REMIX", "").split(";") if r]:
        # The converted CE groundcover is re-speciesed in place (levels/warfare/pwr/visual_dressing/
        # meadow_remix.py): empty its listed components, then bake the remix at the same positions.
        remix = Path(remix)
        spec = json.loads((remix / "clear.json").read_text())
        names = set(spec["components"])
        found = {}
        for a in ue.get_editor_subsystem(ue.EditorActorSubsystem).get_all_level_actors():
            if a.get_name() == spec["actor"]:
                for c in a.get_components_by_class(ue.InstancedStaticMeshComponent):
                    if c.get_name() in names:
                        found[c.get_name()] = c
        if set(found) != names:
            raise RuntimeError("Groundcover components missing: " + str(sorted(names - set(found)))[:300])
        keep = json.loads((remix / "keep.json").read_text())
        if verify:
            wrong = {n: c.get_instance_count() for n, c in found.items()
                     if c.get_instance_count() != keep.get(n, {}).get("count", 0)}
            if wrong:
                raise RuntimeError("Remixed groundcover counts differ from keep.json: " + str(wrong)[:300])
        else:
            import struct
            kept = 0
            for n, c in found.items():
                c.clear_instances()
                row = keep.get(n)
                if not row:
                    continue
                transforms = [ue.Transform(ue.Vector(*r[0:3]), ue.Quat(*r[3:7]).rotator(), ue.Vector(*r[7:10]))
                              for r in struct.iter_unpack("<10f", (remix / row["file"]).read_bytes())]
                c.add_instances(transforms, False, True)
                if c.get_instance_count() != row["count"]:
                    raise RuntimeError("Kept groundcover re-add lost instances in " + n)
                kept += row["count"]
            ue.log(f"meadow remix: emptied {len(found)} components ({spec['instances']} instances), kept {kept} in place")
        owner = json.loads((remix / "verges.json").read_text(encoding="utf-8-sig"))["actor"]
        apply(world, remix / "verges.json", verify, expected_owner=owner, prefix="PWRRemix_")
        ue.log("meadow remix: " + ("verified" if verify else "baked") + " " + str(remix))
    ue.log("meadow life: " + ("verified" if verify else "baked") + " " + str(folder))
