"""Apply or verify the additive native PWR meadow actor on the chosen LPE editor copy."""
import hashlib
import json
import os
from pathlib import Path
import struct

import unreal

ACTOR = "PWR_DistanceColonies"
WORLD = "/Game/Levels/Halo1/Solo/LPE/LPE"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def apply(world, spec_path, verify_only=False):
    """Call after loading LPE. The caller owns any save when used as a module."""
    if world.get_path_name().split(".")[0] != WORLD:
        raise ValueError(f"Expected the playable terrain world, got {world.get_path_name()}")
    spec_path = Path(spec_path)
    source = json.loads(spec_path.read_text(encoding="utf-8"))
    groups = source["groups"]
    binary = spec_path.parent/source["file"]
    if sha(binary)!=source["binary_sha256"] or len(groups)!=len(source["exact_sidecars"]):
        raise ValueError("The colony batch differs from the verified PCG bake")
    sidecars=[]
    for i,(row,digest) in enumerate(zip(groups,source["exact_sidecars"]),1):
        sidecar = Path(str(binary)+f".xf{i}")
        if sha(sidecar)!=digest or sidecar.stat().st_size!=40*row["count"]:
            raise ValueError(f"Stale colony transforms for {row['mesh']}")
        if not unreal.load_asset(row["mesh"]):
            raise ValueError(f"The editor copy lacks the existing stand-in for {row['mesh']}")
        sidecars.append(sidecar)
    actors=unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    baseline={a.get_name() for a in actors.get_all_level_actors() if a.get_name()!=ACTOR}
    if "PWR_FieldUnderstory" not in baseline:
        raise ValueError("The source level is missing the verified .7 forest actor")
    existing=[a for a in actors.get_all_level_actors() if a.get_name()==ACTOR]
    if not existing and not verify_only:
        count=unreal.MjolnirUIBuilderLibrary.bake_foliage(world,str(binary),ACTOR,
            [g["mesh"] for g in groups],[1]*len(groups),[unreal.Vector2D(*g["cull"]) for g in groups],
            [34]*len(groups))
        if count!=source["count"]:
            raise RuntimeError(f"BakeFoliage placed {count} instead of {source['count']}")
    all_actors=actors.get_all_level_actors()
    if baseline != {a.get_name() for a in all_actors if a.get_name()!=ACTOR}:
        raise RuntimeError("A pre-existing world actor changed during foliage placement")
    target,=[a for a in all_actors if a.get_name()==ACTOR]
    components=target.get_components_by_class(unreal.HierarchicalInstancedStaticMeshComponent)
    by_mesh={c.get_editor_property("static_mesh").get_path_name():c for c in components}
    if len(by_mesh)!=len(groups) or len(components)!=len(groups):
        raise ValueError("The native mesh groups do not match the PCG bake")
    result={}
    for row,sidecar in zip(groups,sidecars):
        component=by_mesh[row["mesh"]]
        cull=[component.get_editor_property(k) for k in ("instance_start_cull_distance","instance_end_cull_distance")]
        count=component.get_instance_count()
        if cull!=row["cull"] or count!=row["count"] or component.get_collision_enabled()!=unreal.CollisionEnabled.NO_COLLISION:
            raise ValueError(f"Wrong HISM distances, placement count or collision for {row['mesh']}")
        records=sidecar.read_bytes()
        max_error=0.
        # Inspect every saved location, so loading a stale batch with the same counts cannot pass.
        for index in range(count):
            transform=component.get_instance_transform(index,world_space=True)
            v=transform.translation
            point=struct.unpack_from("<3f",records,index*40)
            max_error=max(max_error,abs(v.x-point[0]),abs(v.y-point[1]),abs(v.z-point[2]))
        if max_error>.03:
            raise ValueError(f"Misplaced {row['mesh']}, maximum error {max_error:.3f} cm")
        result[row["mesh"]]=dict(count=count,cull_cm=cull,maximum_position_error_cm=max_error,collision=False)
    return dict(actor=ACTOR,world=world.get_path_name(),existing_actors=len(baseline),
                source_sha256=sha(spec_path),components=result)


if __name__=="__main__":
    spec=Path(os.environ["PWR_DISTANCE_COLONIES_SPEC"])
    mode=os.environ.get("PWR_DISTANCE_COLONIES_MODE","build")
    if mode not in ("build","verify"):
        raise ValueError(mode)
    loader=unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    if not loader.load_level(WORLD):
        raise RuntimeError("Cannot open the working LPE world")
    world=unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
    receipt=apply(world,spec,mode=="verify")
    if mode=="build" and not loader.save_current_level():
        raise RuntimeError("Could not save the revised terrain world")
    (spec.parent/f"editor-{mode}.json").write_text(json.dumps(receipt,indent=2))
