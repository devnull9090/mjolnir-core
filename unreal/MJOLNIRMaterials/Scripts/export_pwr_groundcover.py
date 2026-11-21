"""Editor commandlet: export MJOLNIR_Foliage's instanced components (mesh, cull, transforms) from LPE.

PWR_GROUNDCOVER_OUT = folder. Writes components.json and one <n>.xf per component (10 little-endian
floats an instance: location cm, rotation quaternion xyzw, scale xyz), in the meadow-life format.
"""
import json, os, struct
from pathlib import Path
import unreal as ue
out = Path(os.environ["PWR_GROUNDCOVER_OUT"]); out.mkdir(parents=True, exist_ok=True)
ue.get_editor_subsystem(ue.LevelEditorSubsystem).load_level("/Game/Levels/Halo1/Solo/LPE/LPE")
rows = []
for a in ue.get_editor_subsystem(ue.EditorActorSubsystem).get_all_level_actors():
    if a.get_name() != os.environ.get("PWR_GROUNDCOVER_ACTOR", "MJOLNIR_Foliage"):
        continue
    for i, c in enumerate(a.get_components_by_class(ue.InstancedStaticMeshComponent)):
        m = c.get_editor_property("static_mesh")
        n = c.get_instance_count()
        buf = bytearray()
        for k in range(n):
            t = c.get_instance_transform(k, True)
            v, q, s = t.translation, t.rotation, t.scale3d
            buf += struct.pack("<10f", v.x, v.y, v.z, q.x, q.y, q.z, q.w, s.x, s.y, s.z)
        (out / f"{i}.xf").write_bytes(bytes(buf))
        rows.append(dict(index=i, component=c.get_name(), mesh=m.get_path_name() if m else None, count=n,
                         cull=[c.get_editor_property("instance_start_cull_distance"), c.get_editor_property("instance_end_cull_distance")]))
(out / "components.json").write_text(json.dumps(rows, indent=1))
ue.log(f"exported {len(rows)} components, {sum(r['count'] for r in rows)} instances")
