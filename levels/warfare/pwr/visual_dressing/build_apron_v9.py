# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy", "scipy", "pillow", "rasterio", "shapely"]
# ///
"""Re-refine the distant range against the surface it actually draws.

The live apron (prepare_alpine_range.py on build_survey_ridges.py) lifts surveyed Teton relief onto
a triangle layout that build_apron_v7.py refined against the gentle Gaea field underneath, so the
peaks ride on edges up to 50 m long and their ridges and gullies fall between vertices. This keeps
every existing vertex (the 4032 seam vertices exactly) and splits, with shared edge midpoints,
wherever the mesh misses the final surface: Gaea field + surveyed ridges + rear range and ribs,
evaluated at any point. Triangles under the grounded cliffs and trees are never split, so their
supporting planes stay exact.

    python build_apron_v9.py --out <dir> [--max-triangles N] [--near-error m] [--far-error m]
"""
import argparse
import json
from pathlib import Path

import numpy as np
from scipy import ndimage as nd

import build_apron_v3 as join
import build_apron_v7 as mesh
import build_survey_ridges as survey
import prepare_alpine_range as rng
from heightfield import sha256

LIVE = rng.OUT                      # out/pwr/alpine-target/range (the shipped apron)
PARENT = rng.BASE                   # its parent, ridges-final


def target_surface():
    gaea, _ = join.sampler(mesh.MASTER, mesh.SOURCE, mesh.BASE)
    contacts = json.loads(survey.GROUND.read_text())
    contacts["cliffs"].extend(json.loads(survey.ORIGINAL_CLIFFS.read_text())["checks"])
    ridges = survey.Ridges(rng.DEM, contacts)
    with np.load(PARENT / "apron.source.npz") as parent:
        x, y, height, weight, ribs, rear_lift, rows = rng.range_field(parent["vertices_m"])
    lift = (ribs + rear_lift) * weight

    def sample(px, py):
        px = np.asarray(px, float); py = np.asarray(py, float)
        out = np.empty(len(px))
        for s in range(0, len(px), 400000):
            a, b = px[s:s + 400000], py[s:s + 400000]
            out[s:s + 400000] = ridges.evaluate(a, b, gaea(a, b)) + rng.sample_grid(lift, a, b)
        return out
    return sample, rows


def protected_triangles(vertices, triangles, rows, margin=100.0):
    """Triangles touching a grounded cliff's or tree's footprint (plus margin): never split."""
    c = vertices[triangles, :2]
    lo_t, hi_t = c.min(1), c.max(1)
    keep = np.zeros(len(triangles), bool)
    for row in rows:
        b = np.asarray(row["bounds_ue_cm"])[:, :2] * [.01, -.01]
        lo, hi = b.min(0) - margin, b.max(0) + margin
        keep |= np.all(hi_t >= lo, 1) & np.all(lo_t <= hi, 1)
    return keep


def build(out, max_triangles, rounds, near_error, far_error, angular=0.0):
    out = Path(out); out.mkdir(parents=True, exist_ok=True)
    sample, rows = target_surface()
    with np.load(LIVE / "apron.source.npz") as live:
        vertices = live["vertices_m"].copy(); triangles = live["triangles"].copy()
        seam_normals = live["normals"][:4032].copy()
    seam = vertices[:4032].copy()
    drift = np.abs(sample(vertices[:, 0], vertices[:, 1]) - vertices[:, 2])
    err = mesh.errors(vertices, triangles, sample)
    before = mesh.summary(err, vertices, triangles)
    iterations = []
    for step in range(rounds):
        radius = np.max(np.abs(vertices[triangles, :2].mean(1)), axis=1)
        tol = np.where(radius < 2500, near_error, far_error)
        if angular:
            # What a player can see: no viewer stands outside the playable square, so an error at
            # radius r is at least r - 1000 m away. Hold a fixed angle, never finer than near_error.
            tol = np.maximum(near_error, angular * (radius - 700.0))
        frozen = protected_triangles(vertices, triangles, rows)
        selected = np.flatnonzero((err > tol) & ~frozen)
        limit = max(0, (max_triangles - len(triangles)) // 4)
        if len(selected) > limit:
            selected = selected[np.argsort((err / tol)[selected])[-limit:]] if limit else selected[:0]
        if not len(selected):
            break
        vertices, triangles = mesh.split(vertices, triangles, selected, sample)
        err = mesh.errors(vertices, triangles, sample)
        iterations.append({"iteration": step + 1, "selected": int(len(selected)), "triangles": int(len(triangles)),
                           **mesh.summary(err, vertices, triangles)})
        print(json.dumps(iterations[-1]), flush=True)
    if not np.array_equal(vertices[:4032], seam):
        raise ValueError("Seam changed")
    outer, edge = mesh.write_mesh(out, vertices, triangles, seam_normals)
    receipt = {"schema": "pwr-apron-v9", "method": "conforming shared-edge split against the drawn surface "
               "(Gaea field + surveyed ridges + rear range/ribs); existing vertices kept; prop supports frozen",
               "live_mesh_sha256": sha256(LIVE / "apron.source.npz"), "survey_sha256": sha256(rng.DEM),
               "runtime_master_sha256": sha256(mesh.MASTER), "vertices": int(len(vertices)),
               "triangles": int(len(triangles)), "maximum_render_triangles": max_triangles,
               "live_vertex_drift_m": {"p99": float(np.percentile(drift, 99)), "max": float(drift.max())},
               "error_target_m": {"near": near_error, "far": far_error, "angular_m_per_m": angular}, "before": before,
               "after": mesh.summary(err, vertices, triangles), "iterations": iterations,
               "exact_inner_seam_vertices": 4032, "outer_boundary_edges": outer, "maximum_horizontal_edge_m": edge,
               "protected_objects": len(rows), "bounds_m": [vertices.min(0).tolist(), vertices.max(0).tolist()],
               **{s + "_sha256": sha256(out / ("apron." + s)) for s in ("gltf", "bin")}}
    (out / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    return receipt


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--max-triangles", type=int, default=4500000)
    p.add_argument("--rounds", type=int, default=6)
    p.add_argument("--near-error", type=float, default=1.0)
    p.add_argument("--far-error", type=float, default=2.0)
    p.add_argument("--angular", type=float, default=0.0, help="error allowed per metre of distance from the play square (overrides near/far bands)")
    a = p.parse_args()
    r = build(a.out, a.max_triangles, a.rounds, a.near_error, a.far_error, a.angular)
    print(json.dumps({k: r[k] for k in ("triangles", "live_vertex_drift_m", "before", "after")}))
