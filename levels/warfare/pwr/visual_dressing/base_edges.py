# /// script
# dependencies = ["numpy", "shapely>=2.1,<3"]
# ///
"""Grow the meadow over the bases' hard edges: planting along bed rims and the terrace outline.

The base ground is decor (level.json): court meshes (slots `court`/`recess`), site finishes
(`Aggregate` beds, `ServiceSoil` pads, paving) and gate approaches (`Drive` lanes, shoulders).
Their cooked meshes (mjolnir mesh export) give the exact outlines. Planting, low kinds only
(nothing that blocks sight or needs collision):

  * bed rims: a dense band of tufts, sedge and flowers inside each bed's edge, a few spilling over
    the paving lip like weeds in joints; sparser low cover in the bed interior;
  * the terrace outline: a meadow band on the landscape side, densest at the line and fading out
    over BAND_OUT metres, mossy stones near the line, a few tufts creeping onto the paving.

Drive lanes and vehicle spawns stay clear. Writes <out>/edges.json in meadow_life's home.json
format (site metres); meadow_life finalize plants it with the rest of the meadow.

    uv run --with shapely --with numpy python base_edges.py <meadow out folder> --level <level.json> --paks <Paks>
"""
from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
import struct
import subprocess
import sys

import numpy as np
from shapely import STRtree
from shapely.geometry import Point, Polygon
from shapely.ops import unary_union

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
sys.path.insert(0, str(ROOT / "tools/level"))
sys.path.insert(0, str(HERE))
from heightfield import load_heightfield  # noqa: E402

SEED = 26112011
BAND_OUT = 3.6      # m of meadow band outside the terrace
RIM_IN = 1.3        # m of dense rim inside a bed
SPILL = 0.35        # m a rim tuft may lean over the paving
VEHICLE_ROOM = 4.0
DRIVE_ROOM = 0.6
BED_SECTIONS = {"Aggregate"}
PAD_SECTIONS = {"ServiceSoil"}
DRIVE_SECTIONS = {"Drive"}
RIM = [("greentuft", 5, (0.7, 1.15)), ("drygrass", 3, (0.5, 0.8)), ("straw", 2, (0.6, 0.95)),
       ("periwinkle", 2, (0.7, 1.0)), ("windflower", 1, (0.8, 1.2))]
INTERIOR = [("greentuft", 3, (0.8, 1.2)), ("periwinkle", 2, (0.8, 1.1)), ("drygrass", 2, (0.6, 0.9)),
            ("windflower", 2, (0.9, 1.3)), ("fern", 1, (0.8, 1.1))]
OUTSIDE = [("drygrass", 5, (0.6, 0.95)), ("straw", 3, (0.8, 1.2)), ("greentuft", 3, (0.8, 1.25)),
           ("seedweed", 1, (0.8, 1.1)), ("lettuce", 1, (0.55, 0.8))]
SPILLKINDS = [("greentuft", 3, (0.45, 0.7)), ("drygrass", 1, (0.35, 0.55))]


def glb_sections(path):
    """{material name: [(a, b, c) UE-cm local triangles]} of a mjolnir mesh export's LOD0."""
    b = Path(path).read_bytes()
    jl = struct.unpack_from("<I", b, 12)[0]
    doc = json.loads(b[20:20 + jl])
    data = b[20 + jl + 8:]

    def acc(i, comps, fmt):
        a = doc["accessors"][i]; v = doc["bufferViews"][a["bufferView"]]
        off = v.get("byteOffset", 0) + a.get("byteOffset", 0)
        n = a["count"]
        return np.frombuffer(data, dtype=fmt, count=n * comps, offset=off).reshape(n, comps) if comps > 1 else \
            np.frombuffer(data, dtype=fmt, count=n, offset=off)
    out = {}
    for p in doc["meshes"][0]["primitives"]:
        pos = acc(p["attributes"]["POSITION"], 3, "<f4")[:, [0, 2, 1]] * 100.0   # glTF m, y up -> UE cm
        ia = doc["accessors"][p["indices"]]
        idx = acc(p["indices"], 1, {5123: "<u2", 5125: "<u4"}[ia["componentType"]]).reshape(-1, 3)
        name = doc["materials"][p["material"]]["name"]
        out.setdefault(name, []).append(pos[idx])
    return {k: np.concatenate(v) for k, v in out.items()}


def base_decor(level):
    """Decor that lays Forerunner base ground: court slots, or bindings onto the floor/paving/rock ground masters."""
    keys = ("M_PWR_FRFloor", "M_CE_PWRPaving")   # rock-only decor (cliffs, scarps) is not base ground
    for d in level.get("decor", []):
        mats = d.get("materials") or []
        # Every slot must be ground: buildings carry a few floor slots among walls and roofs ("" entries).
        if mats and all(isinstance(m, dict) for m in mats) and any(any(k in m.get("parent", "") for k in keys) for m in mats):
            if "_deck" in d["id"]:      # bridge slabs are dressed by forerunner_bridges.py
                continue
            yield d


def to_site(tris_cm, d):
    """Mesh-local UE cm through the decor's scale, yaw and position -> site metres (x, y, z), y = -UE y."""
    s = np.asarray(d.get("scale") or [1, 1, 1], float)
    yaw = math.radians((d.get("rot") or [0, 0, 0])[1] if len(d.get("rot") or []) > 1 else 0)
    if any(abs(r) > 1e-6 for i, r in enumerate(d.get("rot") or [0, 0, 0]) if i != 1):
        raise ValueError(f"{d['id']}: only yaw is supported")
    t = tris_cm * s[None, None, :]
    c, sn = math.cos(yaw), math.sin(yaw)
    t = np.stack([t[..., 0] * c - t[..., 1] * sn, t[..., 0] * sn + t[..., 1] * c, t[..., 2]], -1)
    w = t + np.asarray(d["pos"])[None, None, :]
    return np.stack([w[..., 0] / 100, -w[..., 1] / 100, w[..., 2] / 100], -1)


def polys(tris):
    return [Polygon(t[:, :2]) for t in tris if Polygon(t[:, :2]).area > 1e-4]


class Surface:
    """z of the topmost base triangle under a point (site metres), else None."""

    def __init__(self, tris):
        self.tris = tris
        self.polys = polys(tris)
        self.keep = [t for t in tris if Polygon(t[:, :2]).area > 1e-4]
        self.tree = STRtree(self.polys)

    def z(self, x, y):
        best = None
        for i in self.tree.query(Point(x, y)):
            a, b, c = self.keep[i]
            v0, v1, v2 = b[:2] - a[:2], c[:2] - a[:2], np.array([x, y]) - a[:2]
            d = v0[0] * v1[1] - v1[0] * v0[1]
            if abs(d) < 1e-9:
                continue
            u = (v2[0] * v1[1] - v1[0] * v2[1]) / d
            w = (v0[0] * v2[1] - v2[0] * v0[1]) / d
            if u >= -1e-6 and w >= -1e-6 and u + w <= 1 + 1e-6:
                z = a[2] + u * (b[2] - a[2]) + w * (c[2] - a[2])
                best = z if best is None else max(best, z)
        return best


def pick(rng, palette):
    w = np.array([p[1] for p in palette], float)
    k = palette[rng.choice(len(palette), p=w / w.sum())]
    return k[0], float(rng.uniform(*k[2]))


def scatter_band(rng, line_geom, area, inside, outside, spacing, jitter):
    """Jittered grid points in `area` whose distance to the line lies in [inside, outside] (vectorized)."""
    import shapely
    band = line_geom.buffer(outside).intersection(area)
    if band.is_empty:
        return []
    x0, y0, x1, y1 = band.bounds
    gx, gy = np.meshgrid(np.arange(x0, x1, spacing), np.arange(y0, y1, spacing))
    x = gx.ravel() + rng.uniform(-jitter, jitter, gx.size)
    y = gy.ravel() + rng.uniform(-jitter, jitter, gy.size)
    shapely.prepare(band)
    ok = shapely.contains_xy(band, x, y)
    x, y = x[ok], y[ok]
    dist = shapely.distance(shapely.points(x, y), line_geom)
    sel = dist >= inside
    return [((float(a), float(b)), float(d)) for a, b, d in zip(x[sel], y[sel], dist[sel])]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("out", type=Path)
    ap.add_argument("--level", type=Path, required=True)
    ap.add_argument("--paks", required=True)
    ap.add_argument("--heightfield", type=Path, default=ROOT / "levels/warfare/pwr/terrain/runtime-v5/runtime-master.json")
    ap.add_argument("--meshes", type=Path, default=ROOT / "out/pwr/base-edges/meshes")
    a = ap.parse_args()
    level = json.loads(a.level.read_text())
    field = load_heightfield(a.heightfield)
    cli = str(ROOT / "target/release/mjolnir.exe")
    a.meshes.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(SEED)
    # Vehicle spawns: the map's clearance discs (prepare_alpine_verges inputs), already in site metres.
    discs = json.loads((ROOT / "out/pwr/visual-v5/forest-v2/inputs.receipt.json").read_text())["clearance_discs"]
    spawns = [np.array(c[:2], float) for n, c, r in discs if n.startswith("vehicle")]
    sections = {}
    for d in base_decor(level):
        name = d["mesh"].split(".")[0].rsplit("/", 1)[-1]
        glb = a.meshes / f"{name}.glb"
        if not glb.is_file():
            subprocess.run([cli, "mesh", "export", "--paks", a.paks, "--asset", name, "--out", str(glb)], check=True,
                           env=dict(os.environ, MSYS2_ARG_CONV_EXCL="*"))
        for sec, tris in glb_sections(glb).items():
            sections.setdefault(sec, []).append(to_site(tris, d))
    sections = {k: np.concatenate(v) for k, v in sections.items()}
    import time; T0 = time.time()
    def tick(msg): print(f"[{time.time()-T0:6.1f}s] {msg}", file=sys.stderr, flush=True)
    tick("meshes " + str({k: len(v) for k, v in sections.items()}))
    every = np.concatenate(list(sections.values()))
    surface = Surface(every); tick("surface")
    terrace = unary_union(polys(every)).buffer(0.02).buffer(-0.02)
    beds = unary_union([p for s in BED_SECTIONS if s in sections for p in polys(sections[s])]).buffer(0.01).buffer(-0.01)
    pads = unary_union([p for s in PAD_SECTIONS if s in sections for p in polys(sections[s])])
    drive = unary_union([p for s in DRIVE_SECTIONS if s in sections for p in polys(sections[s])]).buffer(DRIVE_ROOM)
    paving = terrace.difference(beds).difference(pads); tick("polygons")
    tick(f"terrace {terrace.area:.0f} m2 beds {beds.area:.0f} m2 ({beds.geom_type}) pads {pads.area:.0f} paving {paving.area:.0f} keep {keep_clear.area if 'keep_clear' in dir() else 0}")
    keep_clear = drive.union(unary_union([Point(*s).buffer(VEHICLE_ROOM) for s in spawns])) if spawns else drive
    plants = []

    import shapely
    shapely.prepare(keep_clear)

    def plant(q, palette, on_base, yaw=None):
        if shapely.contains_xy(keep_clear, q[0], q[1]):
            return
        z = surface.z(*q) if on_base else None
        if z is None:
            z = float(field.sample(q[0], q[1], bounds_error=False))
        kind, s = pick(rng, palette)
        plants.append(dict(kind=kind, position=[round(q[0], 3), round(q[1], 3), round(z, 3)],
                           yaw=float(rng.uniform(0, 360) if yaw is None else yaw), scale=round(s, 3), variant=float(rng.random())))

    # Bed rims and interiors.
    for bed in getattr(beds, "geoms", [beds]):
        if bed.is_empty:
            continue
        rim = bed.exterior
        for q, dist in scatter_band(rng, rim, bed, 0.0, RIM_IN, 0.55, 0.25):
            if rng.random() < 1.0 - 0.45 * dist / RIM_IN:
                plant(q, RIM, True)
        for q, dist in scatter_band(rng, rim, bed, RIM_IN, 1e3, 1.6, 0.7):
            if rng.random() < 0.55:
                plant(q, INTERIOR, True)
        for q, _ in scatter_band(rng, rim, paving, 0.0, SPILL, 0.9, 0.3):
            if rng.random() < 0.35:
                plant(q, SPILLKINDS, True)
    tick(f"beds done {len(plants)}")
    # The terrace outline: meadow band outside, a few tufts creeping in.
    for ring in [g.exterior for g in getattr(terrace, "geoms", [terrace])]:
        world = ring.buffer(BAND_OUT + 1).difference(terrace)
        for q, dist in scatter_band(rng, ring, world, 0.0, BAND_OUT, 0.6, 0.27):
            if rng.random() < max(0.0, 1.0 - dist / BAND_OUT) ** 1.3:
                plant(q, OUTSIDE, False)
        for q, dist in scatter_band(rng, ring, world, 0.2, 1.4, 4.5, 1.8):
            if rng.random() < 0.5:
                plant(q, [("stone", 1, (0.45, 0.85))], False)
        for q, _ in scatter_band(rng, ring, paving, 0.0, SPILL + 0.15, 1.1, 0.35):
            if rng.random() < 0.3:
                plant(q, SPILLKINDS, True)
    a.out.mkdir(parents=True, exist_ok=True)
    out = a.out / "edges.json"
    from collections import Counter
    summary = dict(plants=len(plants), kinds=Counter(p["kind"] for p in plants), beds=len(getattr(beds, "geoms", [beds])),
                   terrace_rings=len(getattr(terrace, "geoms", [terrace])), terrace_area_m2=round(terrace.area))
    out.write_text(json.dumps(dict(shrubs=plants, summary=summary)))
    print(json.dumps(summary))


if __name__ == "__main__":
    main()
