"""Apply the saved headwater grid, foliage and shore shader in the isolated .31 editor project."""

import os
import json
import runpy
import traceback
import math
import hashlib
from pathlib import Path
import unreal as u

w = Path(os.environ["PWR_HEADWATER_ROOT"])
out = Path(os.environ.get("PWR_HEADWATER_OUTPUT",w / "out/pwr/headwater-lake"))
verify = os.environ.get("PWR_HEADWATER_VERIFY") == "1"
basin = os.environ.get("PWR_RIVER_BASIN") == "1"
parent_outlet = w/"out/pwr/river-apron"


def run():
    sys = u.get_editor_subsystem(u.LevelEditorSubsystem)
    assert sys.load_level("/Game/Levels/Halo1/Solo/LPE/LPE")
    actors = u.get_editor_subsystem(u.EditorActorSubsystem).get_all_level_actors()
    keys = {
        (a.get_actor_label(), c.get_name()): (a, c)
        for a in actors
        for c in a.get_components_by_class(u.InstancedStaticMeshComponent)
    }
    box = u.Box(min=u.Vector(-51200 if basin else -47000, -103000 if basin else -100000, -100000),
                max=u.Vector(-20500 if basin else -22500,-72000 if basin else -73500,100000))
    if os.environ.get("PWR_HEADWATER_INVENTORY") == "1":
        groups = []
        for (label, component), (actor, c) in keys.items():
            mesh = c.get_editor_property("static_mesh")
            if not mesh:
                continue
            indices = c.get_instances_overlapping_box(box, True)
            if indices:
                groups.append(
                    dict(
                        label=label,
                        component=component,
                        mesh=mesh.get_path_name(),
                        source_count=c.get_instance_count(),
                        instances=[
                            [
                                i,
                                *c.get_instance_transform(
                                    i, True
                                ).translation.to_tuple(),
                            ]
                            for i in indices
                        ],
                    )
                )
        (out / "native-scene-inventory.json").write_text(
            json.dumps(dict(instances=groups))
        )
        return
    (land,) = [a for a in actors if isinstance(a, u.Landscape)]
    baseline = parent_outlet/"terrain/runtime-master.r16" if basin else w / "levels/warfare/pwr/terrain/runtime-v5/runtime-master.r16"
    target = out / "terrain/runtime-master.r16"
    if not u.MjolnirUIBuilderLibrary.patch_landscape_heights(
        land, str(baseline), str(target), True
    ):
        if verify or not u.MjolnirUIBuilderLibrary.patch_landscape_heights(
            land, str(baseline), str(target), False
        ):
            raise RuntimeError(
                "Native landscape is not at the sealed starting or target heightfield"
            )
    assert u.MjolnirUIBuilderLibrary.patch_landscape_heights(
        land, str(baseline), str(target), True
    )
    plans = json.loads((out / "native-foliage-plan.json").read_text())
    source_inventory = json.loads((out / "native-scene-inventory.json").read_text())[
        "instances"
    ]
    counts = {
        r["label"] + "." + r["component"]: r["source_count"] for r in source_inventory
    }
    for plan in plans:
        a, c = keys[plan["label"], plan["component"]]
        name = plan["label"] + "." + plan["component"]
        counts[name] -= len(plan["removed"])
        if not verify:
            if c.get_instance_count() != counts[name] + len(plan["removed"]):
                raise ValueError(name + " source count")
            a.modify()
            c.modify()
            for i, x, y, z in plan["removed"]:
                p = c.get_instance_transform(i, True).translation
                assert math.dist(p.to_tuple(), (x, y, z)) < 0.25
            for i, x, y, z, nz in plan["moved"]:
                t = c.get_instance_transform(i, True)
                p = t.translation
                assert math.dist(p.to_tuple(), (x, y, z)) < 0.25
                t.translation = u.Vector(p.x, p.y, nz)
                assert c.update_instance_transform(i, t, True, False, True)
            for i,x,y,z,nx,ny,nz in plan.get("transplanted",[]):
                t = c.get_instance_transform(i, True)
                assert math.dist(t.translation.to_tuple(),(x,y,z))<.25
                t.translation = u.Vector(nx,ny,nz)
                assert c.update_instance_transform(i,t,True,False,True)
            for i, *_ in sorted(plan["removed"], reverse=True):
                assert c.remove_instance(i)
        if c.get_instance_count() != counts[name]:
            raise ValueError(name + " count")
        # Query all expected new transforms in this component. Index order may change on removals.
        if verify:
            xyz = set()
            for i in c.get_instances_overlapping_box(box, True):
                xyz.add(
                    tuple(
                        round(v, 1)
                        for v in c.get_instance_transform(
                            i, True
                        ).translation.to_tuple()
                    )
                )
            for _, x, y, z, nz in plan["moved"]:
                if tuple(round(v, 1) for v in (x, y, nz)) not in xyz:
                    raise ValueError((name, "missing", x, y, nz))
            for _,x,y,z,nx,ny,nz in plan.get("transplanted",[]):
                destination=tuple(round(v,1) for v in (nx,ny,nz))
                source=tuple(round(v,1) for v in (x,y,z))
                if destination not in xyz or source in xyz:
                    raise ValueError((name,"rush transplant",source,destination))
            for _, x, y, z in plan["removed"]:
                if tuple(round(v, 1) for v in (x, y, z)) in xyz:
                    raise ValueError((name, "retained", x, y, z))
    if not verify:
        if not sys.save_current_level():
            raise ValueError("Scene save failed")
    if not basin:
        runpy.run_path(
            str(w / "unreal/MJOLNIRMaterials/Scripts/apply_headwater_shore.py"),
            run_name="__main__",
        )
    report = dict(
        counts=counts,
        components=len(plans),
        removed=sum(len(p["removed"]) for p in plans),
        moved=sum(len(p["moved"]) for p in plans),
        transplanted_rushes=sum(len(p.get("transplanted",[])) for p in plans),
        height_samples=1009**2,
        dressing_ledger_sha256=hashlib.sha256((out/"dressing/decor-moves.json").read_bytes()).hexdigest(),
        terrain_r16_sha256=hashlib.sha256(target.read_bytes()).hexdigest(),
    )
    (out / ("editor-verified.json" if verify else "editor-dressing.json")).write_text(
        json.dumps(report)
    )


try:
    run()
except:
    (out / ("error-verify.txt" if verify else "error-dress.txt")).write_text(
        traceback.format_exc()
    )
    raise
