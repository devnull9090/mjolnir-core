"""Build the grounded .12 meadow on the isolated, already-authored .11 LPE."""

import json
import math
import os
from pathlib import Path
import random
import sys

import unreal as ue

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pwr_wind_meadow as old

FINE = "PWR_FineMeadow"
NAME = "PWRBlade_"


def make_blades(key, material):
    """Six irregular crowns spread across this low patch. Each blade is solid curved geometry."""
    asset_name = "SM_PWR_FineFescue_" + key
    path = old.FOLDER + "/" + asset_name + "." + asset_name
    mesh = ue.load_asset(path) or ue.MjolnirUIBuilderLibrary.create_stand_in_mesh(path)
    rng = random.Random(1317 if key == "A" else 427)
    verts = []
    indices = []
    coords = []
    for crown in range(7 if key == "A" else 9):
        a = rng.uniform(0, math.tau)
        r = math.sqrt(rng.random()) * (55 if key == "A" else 47)
        x, y = math.cos(a) * r, math.sin(a) * r
        for leaf in range(rng.randint(5, 9)):
            az = rng.uniform(0, math.tau)
            dx, dy = math.cos(az), math.sin(az)
            rx, ry = x + rng.uniform(-4.8, 4.8), y + rng.uniform(-4.8, 4.8)
            h = rng.uniform(6.5, 19.5)
            span = rng.uniform(2.8, 13.3)
            w = rng.uniform(0.42, 0.86)
            ix = len(verts)
            for t, pair in ((0, True), (0.57, True), (1.0, False)):
                for side in (-1, 1) if pair else (0,):
                    half = w * (1.0 - 0.55 * t) * side
                    verts.append(
                        ue.Vector(
                            rx + dx * span * t * t - dy * half,
                            ry + dy * span * t * t + dx * half,
                            -0.35 + h * t,
                        )
                    )
            offset = rng.uniform(0.05, 0.93)
            topo = [0, 1, 2, 1, 3, 2, 2, 3, 4]
            uv = [
                (offset, 0.92),
                (offset + 0.014, 0.92),
                (offset, 0.48),
                (offset + 0.014, 0.48),
                (offset + 0.007, 0.03),
            ]
            indices.extend(ix + i for i in topo)
            coords.extend(ue.Vector2D(*uv[i]) for i in topo)
    if not ue.MjolnirUIBuilderLibrary.build_static_mesh(
        mesh,
        verts,
        [ue.Vector(0, 0, 1)] * len(verts),
        indices,
        coords,
        coords,
        [0] * (len(indices) // 3),
        [ue.Name("Grass")],
        [],
        [],
    ):
        raise RuntimeError("Failed to build " + asset_name)
    mesh.set_material(0, material)
    old.save(mesh)
    return {"mesh": path, "triangles": len(indices) // 3, "vertices": len(verts)}


def apply(world, spec_path, verify=False):
    folder = Path(spec_path).resolve().parent
    spec = old.pcg.load(spec_path)
    if world.get_name() != "LPE":
        raise RuntimeError("LPE is required")
    source = folder.parent / "grass"
    coarse = old.pcg.load(source / "wind.selected.json")
    if not verify:
        materials = old.materials(spec, grounded=True)
        patch = {k: make_blades(k, materials["Fescue"]) for k in ("A", "B")}
        (folder / "meshes.json").write_text(json.dumps(patch, indent=2))
        if not ue.MjolnirPCGLibrary.generate_points(
            world,
            str(folder / "points.json"),
            old.GRAPH + "Fine",
            str(folder / "pcg-output.json"),
            spec["seed"],
            0.67,
            1.20,
        ):
            raise RuntimeError("Native meadow floor PCG failed")
        fine = old.pcg.adapt(
            folder / "points.json",
            folder / "pcg-output.json",
            folder / "palette.json",
            folder,
            "fine",
        )
        groups = old.pcg.load(folder / "fine.json")["groups"]
        if not 0 < fine["selected_count"] <= spec["budget"]:
            raise ValueError("Fine meadow budget exceeded")
        if not any(a.get_name() == FINE for a, c in old.actor_components()):
            count = ue.MjolnirUIBuilderLibrary.bake_foliage(
                world,
                str(folder / "fine.bin"),
                FINE,
                [g["mesh"] for g in groups],
                [1] * len(groups),
                [ue.Vector2D(*g["cull"]) for g in groups],
                [32] * len(groups),
            )
            if count != fine["selected_count"]:
                raise RuntimeError("World omitted fine grass")
        canyon = {}
        for pt in coarse["instances"]:
            if pt["kind"] == "Canyon":
                x, y, z = pt["position_cm"]
                canyon.setdefault((math.floor(x), math.floor(y)), []).append(
                    (x, y, z, pt["scale"])
                )
        for actor, c in old.actor_components():
            mesh = c.get_editor_property("static_mesh")
            family = mesh.get_name() if mesh else ""
            wind = actor.get_name() == old.NAME
            low = actor.get_name() == FINE
            tundra = family == "SM_Grass_GroundcoverClump_A"
            if not (wind or low or tundra):
                continue
            c.modify()
            if not c.get_name().startswith(NAME):
                new = NAME + c.get_name()
                c.rename(new)
                if c.get_name() != new:
                    raise RuntimeError(
                        "Wind component did not acquire independent ownership"
                    )
            key = (
                "Fescue"
                if low
                else "Tundra"
                if tundra
                else "Canyon"
                if "Canyon" in family
                else "B30"
            )
            c.set_material(0, materials[key])
            c.set_evaluate_world_position_offset(True)
            c.set_world_position_offset_disable_distance(
                3100 if low else 2850 if tundra else 4800
            )
            # HISM exposes this scalar to native reflection but excludes it from
            # Python's editable properties. Its Kismet setter uses FBoolProperty.
            ue.get_default_object(ue.SystemLibrary).call_method(
                "SetBoolPropertyByName",
                args=(c, ue.Name("bEnableDensityScaling"), True),
            )
            if key == "Canyon":
                ts = []
                for i in range(c.get_instance_count()):
                    t = c.get_instance_transform(i, world_space=False)
                    p = t.translation
                    xi, yi = math.floor(p.x), math.floor(p.y)
                    nearest = min(
                        (math.dist((p.x, p.y, p.z), v[:3]), v[3])
                        for dx in (-1, 0, 1)
                        for dy in (-1, 0, 1)
                        for v in canyon.get((xi + dx, yi + dy), ())
                    )
                    if nearest[0] > 0.15:
                        raise RuntimeError("Authored Canyon pivot moved")
                    s = nearest[1]
                    v = 0.5 + 0.5 * math.sin(p.x * 0.735 + p.y * 0.971 + p.z * 0.047)
                    t.scale3d = ue.Vector(
                        s * (0.7 + 0.28 * v),
                        s * (0.7 + 0.28 * v),
                        s * (0.53 + 0.37 * v),
                    )
                    ts.append(t)
                if not c.batch_update_instances_transforms(
                    0,
                    ts,
                    world_space=False,
                    mark_render_state_dirty=True,
                    teleport=True,
                ):
                    raise RuntimeError("Could not vary Canyon heights")
        actors = ue.get_editor_subsystem(ue.EditorActorSubsystem)
        for actor in actors.get_all_level_actors():
            if (
                actor.get_class().get_path_name() == "/Script/PCG.PCGWorldActor"
                and not actors.destroy_actor(actor)
            ):
                raise RuntimeError("Could not clear the editor PCG partition helper")
        if not ue.get_editor_subsystem(ue.LevelEditorSubsystem).save_current_level():
            raise RuntimeError("Could not save LPE")
    fine = old.pcg.load(folder / "fine.selected.json")
    rows = []
    for a, c in old.actor_components():
        m = c.get_editor_property("static_mesh")
        if not m:
            continue
        if (
            a.get_name() not in (old.NAME, FINE)
            and m.get_name() != "SM_Grass_GroundcoverClump_A"
        ):
            continue
        assert c.get_name().startswith(NAME) and c.get_editor_property(
            "evaluate_world_position_offset"
        )
        rows.append(
            dict(
                owner=a.get_name(),
                component=c.get_name(),
                mesh=m.get_path_name(),
                count=c.get_instance_count(),
                material=c.get_material(0).get_path_name(),
                cull=[
                    c.get_editor_property("instance_start_cull_distance"),
                    c.get_editor_property("instance_end_cull_distance"),
                ],
                wpo_stop_cm=c.get_editor_property(
                    "world_position_offset_disable_distance"
                ),
            )
        )
    assert (
        len(rows) == 18
        and sum(r["count"] for r in rows if r["owner"] == FINE)
        == fine["selected_count"]
    )
    info = dict(
        fine_count=fine["selected_count"],
        coarse_count=coarse["selected_count"],
        rows=rows,
    )
    (folder / ("editor-saved.json" if verify else "editor-built.json")).write_text(
        json.dumps(info, indent=2)
    )
    return info


if __name__ == "__main__":
    level = ue.get_editor_subsystem(ue.LevelEditorSubsystem)
    if not level.load_level("/Game/Levels/Halo1/Solo/LPE/LPE"):
        raise RuntimeError("Could not load saved LPE")
    apply(
        ue.get_editor_subsystem(ue.UnrealEditorSubsystem).get_editor_world(),
        os.environ.get(
            "PWR_WIND_GRASS",
            str(old.ROOT / "out/pwr/ground-life/grass.12/wind-grass.json"),
        ),
        verify=os.environ.get("PWR_WIND_VERIFY") == "1",
    )
