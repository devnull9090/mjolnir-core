"""Selectively replace the original dry pine-floor sedge in the authored .12 LPE."""

import json
import math
import os
from pathlib import Path
import struct
import sys

import unreal as ue

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pwr_wind_meadow as common

OWNER = "PWR_DryForestFloor"
STOCK = "SM_Grass_Sedges_A_Leaves_C"


def apply(world, spec_path, verify=False):
    if world.get_name() != "LPE":
        raise RuntimeError("Expected preserved .12 LPE")
    spec_path = Path(spec_path).resolve()
    folder = spec_path.parent
    spec = json.loads(spec_path.read_text())

    def collect():
        origins = {}
        replacement = {}
        for a, c in common.actor_components():
            mesh = c.get_editor_property("static_mesh")
            if a.get_name() == "MJOLNIR_Foliage" and mesh and mesh.get_name() == STOCK:
                origins[c.get_name()] = c
            if a.get_name() == OWNER:
                replacement[mesh.get_path_name()] = c
        return origins, replacement

    origins, planted = collect()
    if len(origins) != 2:
        raise RuntimeError("Expected both .12 sedge components")
    if not verify and not planted:
        # Compare each selected pivot before world mutation. A changed source
        # layout cannot remove an otherwise valid instance at the same index.
        chosen = {}
        for row in spec["source"]:
            c = origins[row["component"]]
            if c.get_instance_count() != row["original"]:
                raise RuntimeError("Changed source sedge count")
            records = list(
                struct.iter_unpack(
                    "<i3f", (folder / (row["component"] + ".remove")).read_bytes()
                )
            )
            assert len(records) == row["removed"]

            def xyz(i):
                v = c.get_instance_transform(i, world_space=False).translation
                return v.x, v.y, v.z

            sentinel = records[:: max(1, len(records) // 29)]
            if all(math.dist(xyz(i), x) < 0.18 for i, *x in sentinel):
                for i, *x in records:
                    if math.dist(xyz(i), x) > 0.18:
                        raise RuntimeError("Unexpected source pivot order")
                chosen[c.get_name()] = [v[0] for v in records]
            else:
                # Cooked HISM cluster trees can reorder an affine stream.
                buckets = {}
                for _, x, y, z in records:
                    buckets.setdefault((math.floor(x), math.floor(y)), []).append(
                        (x, y, z)
                    )
                indices = []
                for i in range(c.get_instance_count()):
                    pos = xyz(i)
                    x, y = math.floor(pos[0]), math.floor(pos[1])
                    hits = [
                        point
                        for a in (-1, 0, 1)
                        for b in (-1, 0, 1)
                        for point in buckets.get((x + a, y + b), ())
                        if math.dist(point, pos) < 0.18
                    ]
                    if len(hits) > 1:
                        raise RuntimeError("Ambiguous selected sedge center")
                    if hits:
                        indices.append(i)
                if len(indices) != len(records):
                    raise RuntimeError("Could not match selected sedges in editor")
                chosen[c.get_name()] = indices
        for row in spec["source"]:
            c = origins[row["component"]]
            c.modify()
            if (
                not c.remove_instances(sorted(chosen[c.get_name()], reverse=True))
                or c.get_instance_count() != row["survivors"]
            ):
                raise RuntimeError("Failed to partition the native sedge group")
        groups = spec["groups"]
        n = ue.MjolnirUIBuilderLibrary.bake_foliage(
            world,
            str(folder / "floor.bin"),
            OWNER,
            [g["mesh"] for g in groups],
            [1] * len(groups),
            [ue.Vector2D(*g["cull"]) for g in groups],
            [32] * len(groups),
        )
        if n != spec["totals"]["dry_forest"]:
            raise RuntimeError("Understory PCG positions lost")
        _, planted = collect()
        for g in groups:
            c = planted[g["mesh"]]
            c.rename("PWRFloor_" + g["key"])
            if g["material"]:
                c.set_material(0, ue.load_asset(common.FOLDER + "/" + g["material"]))
            c.set_evaluate_world_position_offset(True)
            c.set_world_position_offset_disable_distance(g["wpo"])
            ue.get_default_object(ue.SystemLibrary).call_method(
                "SetBoolPropertyByName",
                args=(c, ue.Name("bEnableDensityScaling"), True),
            )
        if not ue.get_editor_subsystem(ue.LevelEditorSubsystem).save_current_level():
            raise RuntimeError("Failed to save dry pine floor")
    origins, planted = collect()
    for r in spec["source"]:
        if origins[r["component"]].get_instance_count() != r["survivors"]:
            raise RuntimeError("Native survivor count changed")
    assert len(planted) == 6
    rows = []
    for g in spec["groups"]:
        c = planted[g["mesh"]]
        assert (
            c.get_name() == "PWRFloor_" + g["key"]
            and c.get_instance_count() == g["count"]
            and c.get_collision_enabled() == ue.CollisionEnabled.NO_COLLISION
        )
        assert c.get_editor_property("evaluate_world_position_offset")
        assert [
            c.get_editor_property(k)
            for k in ("instance_start_cull_distance", "instance_end_cull_distance")
        ] == g["cull"]
        if g["material"]:
            assert c.get_material(0).get_name() == g["material"]
        rows.append(
            dict(name=c.get_name(), mesh=g["mesh"], count=c.get_instance_count())
        )
    receipt = dict(components=rows, totals=spec["totals"])
    (folder / ("editor-saved.json" if verify else "editor-built.json")).write_text(
        json.dumps(receipt, indent=2)
    )
    return receipt


if __name__ == "__main__":
    level = ue.get_editor_subsystem(ue.LevelEditorSubsystem)
    if not level.load_level("/Game/Levels/Halo1/Solo/LPE/LPE"):
        raise RuntimeError("LPE missing")
    apply(
        ue.get_editor_subsystem(ue.UnrealEditorSubsystem).get_editor_world(),
        os.environ.get(
            "PWR_FOREST_FLOOR",
            str(common.ROOT / "out/pwr/ground-life/forest.13/floor.json"),
        ),
        os.environ.get("PWR_FOREST_VERIFY") == "1",
    )
