"""Apply or verify the road-verge HISM pass inside the isolated PWR authoring map."""

import hashlib
import json
import math
import os
from pathlib import Path
import struct
import sys

import unreal as ue

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pwr_wind_meadow as common

WORLD = "/Game/Levels/Halo1/Solo/LPE/LPE"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_input(path, expected_owner="PWR_AlpineVerges"):
    spec = json.loads(path.read_text(encoding="utf-8-sig"))
    binary = path.parent / spec["file"]
    if spec["actor"] != expected_owner or digest(binary) != spec["binary_sha256"]:
        raise ValueError("Unexpected alpine native instance input")
    groups = spec["groups"]
    if len({r["mesh"] for r in groups}) != len(groups):
        raise ValueError("Duplicate alpine source meshes")
    exact = []
    for i, row in enumerate(groups, 1):
        xf = path.parent / (binary.name + f".xf{i}")
        if digest(xf) != row["transform_sha256"]:
            raise ValueError(
                "Alpine transforms changed since mesh contact verification"
            )
        records = sorted(struct.iter_unpack("<10f", xf.read_bytes()))
        if not (0 < len(records) == row["count"]):
            raise ValueError("Alpine group count mismatch")
        exact.append(records)
    return spec, binary, exact


def pose(t):
    v, q, s = t.translation, t.rotation, t.scale3d
    return v.x, v.y, v.z, q.x, q.y, q.z, q.w, s.x, s.y, s.z


def apply(world, spec_path, verify_only, expected_owner="PWR_AlpineVerges", prefix="PWRVerge_"):
    spec_path = Path(spec_path)
    spec, binary, exact = load_input(spec_path, expected_owner)
    owner = spec["actor"]

    def find():
        return {
            c.get_editor_property("static_mesh").get_path_name(): c
            for a, c in common.actor_components()
            if a.get_name() == owner and c.get_editor_property("static_mesh")
        }

    planted = find()
    if not verify_only and not planted:
        for r in spec["groups"]:
            mesh = ue.load_asset(r["mesh"])
            if not mesh and r.get("standin_slots"):
                mesh = common.standin(r)
            if not mesh or mesh.get_path_name() != r["mesh"]:
                raise RuntimeError("Missing source mesh: " + r["mesh"])
            binding = r.get("material_package") or (common.FOLDER + "/" + r["material"] if r["material"] else None)
            if binding and not ue.load_asset(binding):
                raise RuntimeError("Missing source material: " + binding)
        for row in spec["groups"]:
            if not 0 <= row["cull"][0] < row["cull"][1]:
                raise ValueError("Invalid foliage cull distances")
        groups = spec["groups"]
        count = ue.MjolnirUIBuilderLibrary.bake_foliage(
            world,
            str(binary),
            owner,
            [g["mesh"] for g in groups],
            [1] * len(groups),
            [ue.Vector2D(*g["cull"]) for g in groups],
            [g["flags"] for g in groups],
        )
        if count != spec["count"]:
            raise RuntimeError(
                f"Alpine bakes lost instances: {count} of {spec['count']}"
            )
        planted = find()
        for row in groups:
            c = planted[row["mesh"]]
            c.rename(prefix + row["key"])
            binding = row.get("material_package") or (common.FOLDER + "/" + row["material"] if row["material"] else None)
            if binding:
                c.set_material(0, ue.load_asset(binding))
            c.set_evaluate_world_position_offset(bool(row["wpo"]))
            if row["wpo"]:
                c.set_world_position_offset_disable_distance(row["wpo"])
        if not ue.get_editor_subsystem(ue.LevelEditorSubsystem).save_current_level():
            raise RuntimeError("Unable to save the alpine placement pass")

    if len(planted) != len(spec["groups"]):
        raise RuntimeError("Alpine instance groups do not match the native manifest")
    results = []
    for row, expected in zip(spec["groups"], exact):
        c = planted[row["mesh"]]
        if c.get_name() != prefix + row["key"] or c.get_instance_count() != len(
            expected
        ):
            raise RuntimeError("Unexpected component identity/count: " + row["key"])
        if (
            c.get_editor_property("instance_start_cull_distance") != row["cull"][0]
            or c.get_editor_property("instance_end_cull_distance") != row["cull"][1]
            or bool(c.get_editor_property("evaluate_world_position_offset"))
            != bool(row["wpo"])
            or bool(c.get_editor_property("cast_shadow")) != bool(row["flags"] & 1)
        ):
            raise RuntimeError(
                "Unexpected alpine component render settings: " + row["key"]
            )
        if row["material"] and c.get_material(0).get_name() != row["material"]:
            raise RuntimeError("Unexpected wind material: " + row["key"])
        if row.get("material_package") and c.get_material(0).get_path_name().split(".")[0] != row["material_package"]:
            raise RuntimeError("Unexpected native surface material: " + row["key"])
        actual = sorted(
            pose(c.get_instance_transform(i, world_space=True))
            for i in range(len(expected))
        )
        error = max(math.dist(a[:3], b[:3]) for a, b in zip(actual, expected))
        # A unit quaternion and its negation are the same rotation.
        angle = max(
            1.0 - abs(sum(x * y for x, y in zip(a[3:7], b[3:7])))
            for a, b in zip(actual, expected)
        )
        scale = max(math.dist(a[7:], b[7:]) for a, b in zip(actual, expected))
        if error > 0.08 or angle > 1.0e-5 or scale > 1.0e-4:
            raise RuntimeError(
                f"Unexpected transform drift in {row['key']}: {error}, {angle}, {scale}"
            )
        results.append(
            dict(
                component=c.get_name(),
                count=len(expected),
                mesh=row["mesh"],
                max_position_error_cm=error,
            )
        )
    target = spec_path.parent / (
        "editor-saved.json" if verify_only else "editor-built.json"
    )
    target.write_text(
        json.dumps(
            dict(actor=owner, source_sha256=digest(spec_path), groups=results), indent=2
        )
        + "\n"
    )


if __name__ == "__main__":
    levels = ue.get_editor_subsystem(ue.LevelEditorSubsystem)
    if not levels.load_level(WORLD):
        raise RuntimeError("PWR LPE authoring map did not load")
    apply(
        ue.get_editor_subsystem(ue.UnrealEditorSubsystem).get_editor_world(),
        os.environ.get(
            "PWR_ALPINE_VERGES",
            str(common.ROOT / "out/pwr/alpine-target/verges/verges.json"),
        ),
        os.environ.get("PWR_VERGES_VERIFY") == "1",
    )
