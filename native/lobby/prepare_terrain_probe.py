"""Offline plan/flags for a private native floor and compiled-piece seam probe.

The ordered terrain triangles must be the exact contiguous range recorded by
the exporter before its trailing architecture. Every triangle is checked
before source ranges can become seams.
No game calls. Never modifies the frozen or runtime master heightfield.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools/level"))
from heightfield import load_heightfield, sha256

DEFAULT_MASTER = ROOT / "levels/warfare/pwr/terrain/runtime-v3/runtime-master.json"
DEFAULT_LAYOUT = ROOT / "levels/warfare/pwr/layout.json"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def verify_master_vertices(vertices, field, proof=None):
    error=np.abs(field.sample(vertices[:,0],vertices[:,1])-vertices[:,2])
    bad=error>=.001
    if not bad.any():return {"approximated_boundary_vertices":0,"maximum_vertex_error_m":float(error.max(initial=0))}
    lo,hi=field.bounds_m
    boundary=np.any(np.isclose(vertices[:,:2],lo,atol=1e-7,rtol=0)|np.isclose(vertices[:,:2],hi,atol=1e-7,rtol=0),axis=1)
    require(np.all(boundary[bad]),"Interior terrain collision vertices do not match runtime master")
    require(proof is not None and proof.get("accuracy_and_mesh_budget_pass") is True
            and proof["master_manifest_sha256"]==field.manifest_sha256,
            "Clipped boundary approximation requires its matching successful adaptive proof")
    expected={"ground":.5,"road":.15,"shore":.25,"flat":.1,"outside_walkable_mask":2.0}
    require(proof.get("requested_errors_m")==expected,"Unsupported boundary collision tolerances")
    from adaptive_heightfield import tolerance_grid
    tolerance=tolerance_grid(field,.5,.15,.25,.1,2.)
    uv=(vertices[bad,:2]-field.origin_m)/field.spacing_m
    # Clipping axis/45-degree RTIN edges to this integer grid gives grid
    # vertices. Require that fact instead of inventing off-grid tolerances.
    require(np.all(np.abs(uv-np.rint(uv))<1e-6),"Unsupported off-grid boundary vertex")
    ij=np.rint(uv).astype(int)
    require(np.all(error[bad]<=np.minimum(.5,tolerance[ij[:,1],ij[:,0]])+1e-8),"Clipped boundary exceeds its accepted region tolerance")
    return {"approximated_boundary_vertices":int(bad.sum()),"maximum_vertex_error_m":float(error.max()),
            "positions_m":vertices[bad].tolist(),"errors_m":error[bad].tolist()}


def compiled_seams(receipt_path, ordered_path, field, terrain_receipt_path, proof_path=None):
    receipt_path, ordered_path = Path(receipt_path), Path(ordered_path)
    doc = json.loads(receipt_path.read_text(encoding="utf-8-sig"))
    require(doc["schema"] == "mjolnir-collision-pieces-v1" and not doc["tail_linked_in_host"],
            "An actual separate-instance collision receipt is required")
    require(doc["delta_wu"] == [0, 0, 0], "Probe currently requires zero collision translation")
    source = Path(doc["source_manifest"])
    require(source.is_absolute(), "Receipt source_manifest must be an absolute path")
    require(sha256(source) == doc["source_manifest_sha256"] and
            sha256(source.with_suffix(".bin")) == doc["source_binary_sha256"], "Staged collision changed after compilation")
    require(sha256(Path(doc["output"])) == doc["output_sha256"], "Compiled collision changed after receipt")
    with np.load(ordered_path, allow_pickle=False) as data:
        vertices, triangles = data["vertices_m"].copy(), data["triangles"].copy()
    terrain_receipt_path = Path(terrain_receipt_path)
    terrain_receipt = json.loads(terrain_receipt_path.read_text(encoding="utf-8-sig"))
    trailing = terrain_receipt["trailing_architecture_surfaces"]
    require(type(trailing) is int and trailing >= 0 and terrain_receipt["triangles"] == len(triangles),
            "Terrain exporter count/trailing architecture mismatch")
    require(vertices.ndim == 2 and vertices.shape[1] == 3 and triangles.ndim == 2 and triangles.shape[1] == 3,
            "Expected indexed terrain triangles")
    proof=None;proof_provenance={}
    if proof_path is not None:
        proof_path=Path(proof_path);proof=json.loads(proof_path.read_text())
        extra_path=Path(terrain_receipt["file"])
        require(sha256(extra_path)==terrain_receipt["sha256"],"Terrain extra changed after export")
        extra=json.loads(extra_path.read_text())
        require(extra["proof_sha256"]==sha256(proof_path) and extra["master_manifest_sha256"]==field.manifest_sha256
                and proof["topology"]["surfaces"]==len(triangles),"Adaptive proof does not match exact exported terrain")
        proof_provenance={"adaptive_proof_path":str(proof_path.resolve()),"adaptive_proof_sha256":sha256(proof_path)}
    vertex_check=verify_master_vertices(vertices,field,proof)
    # CE element layouts are fixed and shared by blam_sbsp::ce. Only the
    # appended triangular rings are used; no BSP-tree interpretation is needed.
    sizes = [12, 16, 8, 8, 20, 12, 24, 16]
    binary = source.with_suffix(".bin").read_bytes()
    arrays, cursor = [], 0
    for size in sizes:
        count, = struct.unpack_from("<I", binary, cursor)
        cursor += 4
        arrays.append(memoryview(binary)[cursor:cursor + count * size])
        cursor += count * size
    require(cursor == len(binary), "Unsupported staged collision array layout")
    surfaces = np.frombuffer(arrays[5], dtype=np.dtype([("plane", "<i4"), ("edge", "<i4"), ("rest", "<i4")]))
    edges = np.frombuffer(arrays[6], dtype="<i4").reshape(-1, 6)
    points = np.frombuffer(arrays[7], dtype=np.dtype([("xyz", "<f4", 3), ("edge", "<i4")]))["xyz"]
    end = len(surfaces) - trailing
    first = end - len(triangles)
    require(first >= doc["source_tail_range"][0] and len(surfaces) == doc["source_surfaces"],
            "Terrain does not fit compiled source tail")
    first_edges = surfaces["edge"][first:end]
    edge_ids = np.stack([first_edges, edges[first_edges, 2], edges[edges[first_edges, 2], 2]], axis=1)
    require(np.array_equal(edges[edge_ids[:, 2], 2], first_edges), "Terrain tail contains non-triangular rings")
    actual = points[edges[edge_ids, 0]]
    expected = (vertices[triangles] / 3.048).astype(np.float32)
    require(np.array_equal(actual, expected), "Ordered terrain triangles are not the exact staged collision tail")
    owners = np.full(len(triangles), -1, dtype=np.int64)
    for piece in doc["pieces"]:
        span = piece["source_surface_range"]
        if span is None:
            continue
        lo, hi = max(span[0], first) - first, min(span[1], end) - first
        if hi > lo:
            require(np.all(owners[lo:hi] == -1), "Overlapping compiled source ranges")
            owners[lo:hi] = piece["instance"]
    require(np.all(owners >= 0), "Compiled source ranges do not cover terrain")
    seams = seams_for_owners(vertices, triangles, owners)
    return seams, {"receipt_path": str(receipt_path.resolve()), "receipt_sha256": sha256(receipt_path),
        "ordered_path": str(ordered_path.resolve()), "ordered_sha256": sha256(ordered_path),
        "compiled_tag_sha256": doc["output_sha256"], "terrain_source_first": first,
        "terrain_surfaces": len(triangles), "trailing_architecture_surfaces": trailing,
        "terrain_receipt_path": str(terrain_receipt_path.resolve()), "terrain_receipt_sha256": sha256(terrain_receipt_path),
        "vertex_check":vertex_check,**proof_provenance,
        "compiled_boundaries_verified": True,
        "seam_count": len(seams)}


def seams_for_owners(vertices, triangles, owners):
    edges = np.sort(triangles[:, [[0, 1], [1, 2], [2, 0]]].reshape(-1, 2), axis=1)
    owner = np.repeat(owners, 3)
    order = np.lexsort((edges[:, 1], edges[:, 0]))
    edges, owner = edges[order], owner[order]
    equal = np.all(edges[1:] == edges[:-1], axis=1)
    require(not np.any(equal[:-1] & equal[1:]), "Nonmanifold terrain edge")
    indexes = np.flatnonzero(equal & (owner[1:] != owner[:-1]))
    return [{"a_m": vertices[edges[i, 0]].tolist(), "b_m": vertices[edges[i, 1]].tolist(),
             "instances": [int(owner[i]), int(owner[i + 1])]} for i in indexes]


def gentle_dry(field, xy, radius=4, road=False):
    xy = np.asarray(xy)
    probes = xy + np.array([[0, 0], [radius, 0], [-radius, 0], [0, radius], [0, -radius]])
    if np.max(np.abs(probes)) > 920:
        return False
    z = field.sample(probes[:, 0], probes[:, 1])
    return bool(np.max(np.abs(z[1:] - z[0])) / radius < .12 and
        np.max(field.sample_mask("water", probes[:, 0], probes[:, 1])) < .01 and
        np.max(field.sample_mask("bases", probes[:, 0], probes[:, 1])) < .02 and
        (not road or np.min(field.sample_mask("road", probes[:, 0], probes[:, 1])) > .8))


def make_plan(field, layout, seams, provenance):
    require(layout["protocol"] == 20569 and layout["layout_revision"] == 3, "Requires native layout3")
    require(field.metadata.get("surface_interpolation") == "triangle_nw_se", "Requires actual UE triangulated runtime grid")
    probes = []

    def add(name, kind, xy, support=None, **extra):
        z = float(field.sample(*xy)) if support is None else float(support)
        probes.append({"id": name, "flag": "terrain_probe_" + name, "kind": kind,
            "position_m": [float(xy[0]), float(xy[1]), z + .8], "floor_m": z,
            "surface": "runtime_master" if support is None else "base_plaza",
            "yaw": float(extra.pop("yaw", 0)), "max_residual_m": .35 if kind != "shore" else .75,
            **extra})

    for team in ("red", "blue"):
        home = layout["homes_m"][team]
        add(team + "_apron", "calibration" if team == "red" else "base", home[:2], home[2])
    # Deterministic broad coverage, avoiding platforms, water and steep banks.
    lo, hi = field.bounds_m
    x, y = np.meshgrid(np.arange(lo[0] + 60, hi[0] - 60, 10), np.arange(lo[1] + 60, hi[1] - 60, 10))
    for kind, count in (("road", 4), ("shore", 2)):
        mask = field.sample_mask(kind, x, y) > (.9 if kind == "road" else .4)
        candidates = np.column_stack((x[mask], y[mask]))
        chosen = []
        while len(chosen) < count:
            distances = [min(np.linalg.norm(p - np.array(q["position_m"][:2])) for q in probes) for p in candidates]
            require(len(distances) > 0, "Insufficient dry gentle " + kind + " candidates")
            index = int(np.argmax(distances)); point = candidates[index]
            candidates = np.delete(candidates, index, axis=0)
            if gentle_dry(field, point, road=kind == "road"):
                chosen.append(point)
                add(kind + str(len(chosen)), kind, point)
    # Mid-edge crossing on real compiled instances, with a three-metre
    # approach. Keep a generous finite-edge margin to detect going around it.
    eligible = []
    for seam in seams:
        a, b = np.array(seam["a_m"][:2]), np.array(seam["b_m"][:2])
        edge = b - a; length = np.linalg.norm(edge)
        if length < 6:
            continue
        center = (a + b) / 2; normal = np.array([-edge[1], edge[0]]) / length
        if gentle_dry(field, center, radius=6, road=True):
            eligible.append((seam, center, normal))
    for n in range(4):
        require(eligible, "Insufficient actual compiled dry road seams")
        distances = [min(np.linalg.norm(center - np.array(q["position_m"][:2])) for q in probes) for _, center, _ in eligible]
        index = int(np.argmax(distances)); seam, center, normal = eligible.pop(index)
        start = center - normal * 3
        add("seam" + str(n + 1), "seam", start,
            # level.json yaw is Unreal; level.rs ue_yaw_to_blam negates it.
            # The crossing normal remains authored metres/Blam XY.
            yaw=-np.degrees(np.arctan2(normal[1], normal[0])), seam=seam,
            crossing_normal=normal.tolist(), crossing_center_m=center.tolist(),
            max_walk_metres=14, walk_duration_ms=1500)
    return {"schema": "pwr-terrain-probe-v1", "protocol": 20569, "layout_revision": 3,
        "master_path": str(field.path), "master_manifest_sha256": field.manifest_sha256,
        "height_sha256": field.metadata["height"]["sha256"], "provenance": provenance,
        "contact_method": "inferred from stable consecutive native positions; not a raw contact flag or ray hit",
        "probes": probes}


def patch_level(plan_path, level_path):
    plan_path, level_path = Path(plan_path), Path(level_path)
    plan = json.loads(plan_path.read_text(encoding="utf-8-sig"))
    level = json.loads(level_path.read_text(encoding="utf-8-sig"))
    require(level.get("warfare") == {"protocol": 20569, "layout_revision": 3}, "Installed/bake level must be layout3")
    flags = level["blam"].setdefault("cutscene_flags", [])
    flags[:] = [f for f in flags if not f["name"].startswith("terrain_probe_")]
    additions = []
    for p in plan["probes"]:
        x, y, z = p["position_m"]
        additions.append({"name": p["flag"], "pos": [100*x, -100*y, 100*z], "yaw": p["yaw"]})
    stamp = "terrain_probe_hash_" + sha256(plan_path)[:12]
    additions.append({"name": stamp, "pos": additions[-1]["pos"], "yaw": 0})
    # prepare_runtime owns/re-appends its pwr_* markers. Keep those at the
    # end so running its idempotence validator does not reorder our flags.
    flags[:] = ([f for f in flags if not f["name"].startswith("pwr_")] + additions +
                [f for f in flags if f["name"].startswith("pwr_")])
    level_path.write_text(json.dumps(level, indent=2) + "\n", encoding="utf-8")
    return stamp


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    build = sub.add_parser("build")
    build.add_argument("--master", type=Path, default=DEFAULT_MASTER)
    build.add_argument("--layout", type=Path, default=DEFAULT_LAYOUT)
    build.add_argument("--receipt", type=Path, required=True)
    build.add_argument("--ordered", type=Path, required=True)
    build.add_argument("--terrain-receipt", type=Path, required=True)
    build.add_argument("--collision-proof", type=Path, help="Required for clipped boundary vertices that use the audited approximation")
    build.add_argument("--out", type=Path, required=True)
    patch = sub.add_parser("patch")
    patch.add_argument("plan", type=Path); patch.add_argument("level", type=Path)
    sample = sub.add_parser("sample")
    sample.add_argument("plan", type=Path)
    sample.add_argument("x", type=float); sample.add_argument("y", type=float)
    args = parser.parse_args()
    if args.command == "patch":
        print(patch_level(args.plan, args.level))
    elif args.command == "sample":
        plan = json.loads(args.plan.read_text(encoding="utf-8-sig"))
        field = load_heightfield(plan["master_path"])
        require(field.manifest_sha256 == plan["master_manifest_sha256"], "Runtime master changed")
        print(json.dumps({"floor_m": float(field.sample(args.x, args.y))}))
    else:
        field = load_heightfield(args.master)
        seams, provenance = compiled_seams(args.receipt, args.ordered, field, args.terrain_receipt,args.collision_proof)
        provenance["layout_sha256"] = sha256(args.layout)
        plan = make_plan(field, json.loads(args.layout.read_text(encoding="utf-8-sig")), seams, provenance)
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"plan": str(args.out.resolve()), "probes": len(plan["probes"]), "actual_seams": len(seams)}))


if __name__ == "__main__":
    main()
