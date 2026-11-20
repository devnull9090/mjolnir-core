"""Export the three reviewed Blender additions and their separate structural cores."""
import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
import sys

import bpy
import numpy as np
from mathutils import Matrix, Vector

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from portal_guides import CENTERS
from runtime_visuals import mesh_arrays, write_gltf, sha
from validate_bases import CONTACT_ALLOWANCE, EvaluatedScene, volume_audit


def raw_core(ob, center):
    mesh = ob.data
    mesh.calc_loop_triangles()
    faces = np.array([t.vertices[:] for t in mesh.loop_triangles])
    edges = Counter(tuple(sorted((int(i), int(j)))) for face in faces
                    for i, j in zip(face, np.roll(face, -1)))
    if set(edges.values()) != {2}:
        raise ValueError(f"Open/nonmanifold collision core: {ob.name}")
    matrix = np.asarray(ob.matrix_world)
    xyz = np.array([v.co[:] for v in mesh.vertices]) @ matrix[:3, :3].T + matrix[:3, 3] - center
    if np.linalg.det(matrix[:3, :3]) < 0:
        faces = faces[:, [0, 2, 1]]
    return {"name": ob.name, "points": xyz.tolist(), "faces": faces.tolist()}


def clearances(objects, center, scale, roof):
    scene = EvaluatedScene(objects, Matrix.Translation(-Vector(center)))
    z = .2 + CONTACT_ALLOWANCE
    y = 35 * scale + 3.5
    x = 28 * scale + 3.5
    court = 15 * scale
    boxes = {
        "through_tunnel": ([-1.75, -y, z], [1.75, y, 4.7]),
        "cross_gallery": ([-x, 9*scale-1.75, z], [x, 9*scale+1.75, 4.7]),
        "cannon_reserve": ([-court, -court, roof + .8*scale],
                           [court, court, max(scene.bounds["max"][2] + 2, roof + 10)]),
    }
    for flank in (-1, 1):
        x = flank * 33 * scale
        boxes[f"side_gallery_{flank}"] = ([x-1.75, -36*scale-3.5, z], [x+1.75, -10*scale+3.5, 4.7])
    result = {k:volume_audit(scene, {"min":lo, "max":hi}) for k, (lo, hi) in boxes.items()}
    if any(not c["passed"] for c in result.values()):
        raise ValueError(f"Addition blocks protected architecture: {result}")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(sys.argv[sys.argv.index("--")+1:])
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    scene = bpy.context.scene
    graph = bpy.context.evaluated_depsgraph_get()
    source = Path(bpy.data.filepath)
    receipt = {"scene":str(source), "scene_sha256":sha(source), "meshes":{}, "clearances":{}, "source_objects":{}}
    cores = {}
    for team, center in CENTERS.items():
        objects = sorted((o for o in scene.objects if o.type == "MESH" and o.get("pwr_polish_site") == team), key=lambda o:o.name)
        if not objects:
            raise ValueError("Missing new base art for " + team)
        parts = defaultdict(list)
        log = []
        for ob in objects:
            streams, record = mesh_arrays(ob, graph, center)
            log.append(record)
            for key, recipe, values, faces in streams:
                parts[key].append((values, faces))
        receipt["source_objects"][team] = log
        receipt["meshes"][team] = write_gltf("SM_PWR_BasePolish_"+team.title(), parts, out)
        receipt["clearances"][team] = clearances(objects, center, scene["base_authoring_scale"], scene["roof_deck_z_m"])
        cores[team] = [raw_core(o, center) for o in objects if o.get("pwr_polish_solid")]
    if not cores["green"]:
        raise ValueError("Citadel has no physical crown")
    collision = out / "solid-cores.json"
    collision.write_text(json.dumps(cores, separators=(",", ":"))+"\n")
    receipt["collision_sha256"] = sha(collision)
    (out/"base-polish.json").write_text(json.dumps(receipt, indent=2)+"\n")
    print({k:v["triangles"] for k,v in receipt["meshes"].items()})


if __name__ == "__main__":
    main()
