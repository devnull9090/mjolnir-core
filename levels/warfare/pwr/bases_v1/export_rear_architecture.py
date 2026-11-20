"""Preserve the sealed native architecture's existing vertex streams and replace the edited gate modules."""

import argparse
from collections import defaultdict
import json
from pathlib import Path
import re
import sys

import bpy
import numpy as np
from mathutils import Matrix

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
sys.path.insert(0, str(HERE))
from runtime_visuals import mesh_arrays, write_gltf, sha
from portal_guides import export_meshes

VIS = ROOT / "out/pwr/base-runtime/visuals/manifest.json"
PLAN = ROOT / "out/pwr/base-integration/placement-plan.json"
SITES = {s["id"]: s for s in json.loads(PLAN.read_text())["bases"]}
GROUPS = [
    row
    for row in json.loads(VIS.read_text())["assets"]
    if row["id"].endswith("_architecture")
]
GATE = re.compile(
    r"portal/(?:monolithic outer jamb|dark rebated ring|rear inner armored surround)[0-6]$"
)


def write_doc(path, doc):
    path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")


def capture_original(out):
    # The first native exporter concatenated each object's attributed triangles within material slots.
    # First reproduce its object boundaries against the sealed input. Never regenerate untouched triangles.
    original_manifest = json.loads(VIS.read_text())
    assert sha(bpy.data.filepath) == original_manifest["source_blend_sha256"]
    graph = bpy.context.evaluated_depsgraph_get()
    boundaries = {}
    for spec in GROUPS:
        counts = defaultdict(lambda: [0, 0])
        sealed = read_original(spec)
        records = {}
        for old in spec["source_objects"]:
            name = old["object"]
            obj = bpy.data.objects[name]
            streams, _ = mesh_arrays(obj, graph, spec["anchor_m"])
            shape = {}
            for key, _, verts, faces in streams:
                start_v, start_t = counts[key]
                source_faces = sealed[key][1][start_t : start_t + len(faces)]
                if source_faces.min() != start_v:
                    raise ValueError(
                        (
                            name,
                            key,
                            "loss of original contiguous object boundary",
                            start_v,
                            int(source_faces.min()),
                        )
                    )
                vertex_count = int(source_faces.max()) + 1 - start_v
                shape[key] = {
                    "v": start_v,
                    "n": vertex_count,
                    "i": start_t,
                    "t": len(faces),
                }
                counts[key] = [start_v + vertex_count, start_t + len(faces)]
            assert sum(r["t"] for r in shape.values()) == old["triangles"], name
            records[name] = shape
        assert sum(n for n, t in counts.values()) == spec["vertices"], (
            spec["name"],
            counts,
        )
        assert sum(t for n, t in counts.values()) == spec["triangles"]
        boundaries[spec["id"]] = records
        print(
            "SEALED SECTION BOUNDARIES",
            spec["id"],
            sum(t for v, t in counts.values()),
            flush=True,
        )
    write_doc(out / "original-object-boundaries.json", boundaries)


def read_original(spec):
    gltf = Path(spec["gltf"])
    binary = gltf.with_suffix(".bin")
    assert sha(gltf) == spec["gltf_sha256"] and sha(binary) == spec["bin_sha256"]
    gl = json.loads(gltf.read_text())
    data = binary.read_bytes()

    def arr(i):
        a = gl["accessors"][i]
        v = gl["bufferViews"][a["bufferView"]]
        dtype = {5125: "<u4", 5126: "<f4"}[a["componentType"]]
        width = {"VEC3": 3, "VEC2": 2, "SCALAR": 1}[a["type"]]
        return np.frombuffer(
            data,
            dtype=dtype,
            count=a["count"] * width,
            offset=v.get("byteOffset", 0) + a.get("byteOffset", 0),
        ).reshape(-1, width)

    parts = {}
    for prim in gl["meshes"][0]["primitives"]:
        attrs = prim["attributes"]
        vals = np.column_stack(
            [arr(attrs[key]) for key in ("POSITION", "NORMAL", "TEXCOORD_0")]
        )
        faces = arr(prim["indices"]).reshape(-1, 3)
        parts[gl["materials"][prim["material"]]["name"]] = (vals, faces)
    return parts


def replace(args):
    limits = json.loads((args.out / "original-object-boundaries.json").read_text())
    manifest = json.loads(VIS.read_text())
    records = []
    assets = []
    graph = bpy.context.evaluated_depsgraph_get()
    for spec in GROUPS:
        team = spec["id"].split("_")[0]
        change = [
            old["object"]
            for old in spec["source_objects"]
            if GATE.search(old["object"])
        ]
        assert len(change) == 21, (team, change)
        old = read_original(spec)
        placement = Matrix(SITES[team]["presentation_world_to_map_matrix"])
        for name in change:
            ob = bpy.data.objects[name]
            ob.matrix_world = placement @ ob.matrix_world
        bpy.context.view_layer.update()
        bins = defaultdict(list)
        for name, slots in limits[spec["id"]].items():
            streams = {}
            if name in change:
                parts, record = mesh_arrays(
                    bpy.data.objects[name], graph, spec["anchor_m"]
                )
                streams = {k: (a, i) for k, _, a, i in parts}
                if not set(streams) == set(slots):
                    raise ValueError(
                        (name, "new material slot", list(streams), list(slots))
                    )
                records.append(record)
            for key, limit in slots.items():
                verts, faces = old[key]
                v, n, i, t = [limit[k] for k in ("v", "n", "i", "t")]
                original_vertices = verts[v : v + n]
                original_faces = faces[i : i + t]
                assert len(original_vertices) == n and len(original_faces) == t
                assert original_faces.min() >= v and original_faces.max() < v + n, (
                    name,
                    key,
                )
                if name in change:
                    bins[key].append(streams[key])
                else:
                    bins[key].append((original_vertices, original_faces - np.uint32(v)))
        dumped = write_gltf(spec["name"], bins, args.out)
        assert set(dumped["material_keys"]) == set(spec["material_keys"])
        assets.append(
            {
                **spec,
                **dumped,
                "source_objects": [
                    {k: v for k, v in r.items() if k != "world_bounds_m"}
                    for r in spec["source_objects"]
                ],
            }
        )
        print("REPLACED", team, len(change), dumped["triangles"], flush=True)
    for key, recipe in manifest["materials"].items():
        if key in ("alloy", "ramp_finish") or key.startswith("apron_finish"):
            recipe["color"] = [
                a * b for a, b in zip(recipe["color"], (0.925, 0.866, 0.815))
            ]
            recipe["roughness"] = [
                recipe["roughness"][0] + 0.025,
                recipe["roughness"][1] - 0.035,
            ]
            recipe["variation"] *= 0.58
    result = {
        **manifest,
        "assets": assets,
        "total_triangles": sum(a["triangles"] for a in assets),
        "changed_object_records": records,
        "source_blend": bpy.data.filepath,
        "source_blend_sha256": sha(bpy.data.filepath),
        "sealed_parent_manifest": str(VIS),
        "sealed_parent_manifest_sha256": sha(VIS),
    }
    write_doc(args.out / "manifest.json", result)
    guides = [
        o
        for o in bpy.context.scene.objects
        if o.get("purpose") == "Visual vehicle route marking"
    ]
    assert len(guides) == 14
    write_doc(
        args.out / "portal-guides.json",
        {
            "meshes": export_meshes(guides, args.out),
            "placements": len(guides),
            "source_blend_sha256": result["source_blend_sha256"],
        },
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--baseline", action="store_true")
    args = parser.parse_args(sys.argv[sys.argv.index("--") + 1 :])
    args.out = args.out.resolve()
    args.out.mkdir(parents=True, exist_ok=True)
    if args.baseline:
        capture_original(args.out)
    else:
        replace(args)
