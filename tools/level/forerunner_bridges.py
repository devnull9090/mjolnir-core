"""Forerunner bridge dressing for every road whose `structure` is bridge or culvert.

Render only: the road's collision deck (world_geometry.bridge_parts, 24 m wide
and 2 m thick) keeps all gameplay. Each deck gets

  * a generated shell that encloses that slab: a flat top 4 cm above it, a
    chamfered fascia carrying a light line, and a keeled underside, with ribs
    and glowing floor inlays on 343's 15 m rhythm. It is drawn with its own
    world-projected Forerunner plate materials (apply_forerunner_bridges.py);
  * 343's own pieces from the Assault on the Control Room vehicle bridges
    (tools/level/data/forerunner_bridge_kit.json): the edge posts in pairs every
    30 m, the hanging bracket at each bank of the gap, and a pair of end
    pylons flanking the road at each end.

343's deck floors are not used: their lane is about 12.5 m between 75 cm
curbs, half this deck's width, so they cannot cover it without drive-through
curbs. Nothing here stands above the deck inside the collision width: the
posts sit outboard of the fascia and the pylons beside the road (343 put one
on the centre line of a wider deck), clear of the road's shoulder. Only paths and transforms of 343's
meshes are stored; the shell is generated from these parameters alone.
"""
from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
import sys

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from heightfield import load_heightfield  # noqa: E402

KIT = HERE / "data/forerunner_bridge_kit.json"
SLAB_HALF_WIDTH = 1200.0   # collision deck: offsets -12..12 m
SLAB_DEPTH = 200.0         # collision deck: 2 m thick
LIFT = 4.0                 # shell top above the slab top
PITCH = 1500.0             # 343's module rhythm along the deck
GAP_DROP = 300.0           # terrain this far below the deck top is the gap
PYLON_CLEAR = 50.0         # pylon face beyond the road's shoulder
PYLON_MAX_SINK = 300.0     # a pylon sinks at most this far to meet lower ground
POST_GAP = 5.0             # post inner face outboard of the fascia

# Shell half-profile, (x, z) cm from the centre line and the slab top, top to keel.
TOP_EDGE = 1215.0
FASCIA = 1275.0
PROFILE = [(0.0, LIFT), (TOP_EDGE, LIFT), (1245.0, -8.0), (FASCIA, -40.0), (FASCIA, -150.0),
           (1240.0, -225.0), (430.0, -320.0), (0.0, -320.0)]
RIB = [(0.0, -150.0), (1290.0, -150.0), (1290.0, -175.0), (1250.0, -255.0), (520.0, -385.0), (0.0, -385.0)]
RIB_HALF = 35.0
LIGHT_Z = (-100.0, -84.0)        # fascia light line
INLAY_X = (265.0, 335.0)         # floor inlays either side of the centre line
INLAY_HALF_LEN = 385.0
KEEL_Z = PROFILE[-1][1]
END_COVER = 5.0

SECTIONS = ["DeckMetal", "TrimMetal", "Light"]


class Mesh:
    """Flat-shaded triangles: positions duplicated per face so each face keeps its normal."""

    def __init__(self):
        self.p, self.n, self.idx, self.sec = [], [], [], []

    def tri(self, a, b, c, section):
        a, b, c = (np.asarray(v, float) for v in (a, b, c))
        nrm = np.cross(b - a, c - a)
        ln = np.linalg.norm(nrm)
        if ln < 1e-9:
            return
        nrm /= ln
        i = len(self.p)
        self.p += [a, b, c]; self.n += [nrm, nrm, nrm]; self.idx += [i, i + 1, i + 2]; self.sec.append(section)

    def quad(self, a, b, c, d, section):
        self.tri(a, b, c, section); self.tri(a, c, d, section)


def full_profile(half):
    """Closed loop, counter-clockwise seen from +y: right side top->keel, then the left side back up."""
    right = [(x, z) for x, z in half]
    left = [(-x, z) for x, z in reversed(half)]
    loop = right + left
    out = []
    for q in loop:
        if not out or np.hypot(q[0] - out[-1][0], q[1] - out[-1][1]) > 1e-6:
            out.append(q)
    if np.hypot(out[0][0] - out[-1][0], out[0][1] - out[-1][1]) < 1e-6:
        out.pop()
    return out


def extrude(mesh, loop, y0, y1, section_of, caps=True):
    """Sweep a closed (x, z) loop from y0 to y1; outward normals; optional end caps."""
    n = len(loop)
    for i in range(n):
        (xa, za), (xb, zb) = loop[i], loop[(i + 1) % n]
        sec = section_of(xa, za, xb, zb)
        # loop runs clockwise seen from +y (top centre -> right -> keel -> left): this winding faces outward.
        mesh.quad((xa, y0, za), (xb, y0, zb), (xb, y1, zb), (xa, y1, za), sec)
    if caps:
        cx = sum(x for x, _ in loop) / n; cz = sum(z for _, z in loop) / n
        for i in range(n):
            (xa, za), (xb, zb) = loop[i], loop[(i + 1) % n]
            mesh.tri((cx, y0, cz), (xb, y0, zb), (xa, y0, za), 1)
            mesh.tri((cx, y1, cz), (xa, y1, za), (xb, y1, zb), 1)


def shell(length, modules):
    m = Mesh()
    deck = full_profile(PROFILE)

    def deck_section(xa, za, xb, zb):
        return 0 if za >= LIFT - 0.01 and zb >= LIFT - 0.01 else 1

    # 5 cm past each end of the slab, so its end faces never coincide with the shell's caps.
    extrude(m, deck, -END_COVER, length + END_COVER, deck_section)
    pitch = length / modules
    rib = full_profile(RIB)
    for k in range(1, modules):
        y = k * pitch
        extrude(m, rib, y - RIB_HALF, y + RIB_HALF, lambda *a: 1)
    # Fascia light line, 1 cm proud, both sides, inset from the ends.
    for s in (-1, 1):
        x = s * (FASCIA + 1.0)
        a, b = (x, 30.0, LIGHT_Z[0]), (x, length - 30.0, LIGHT_Z[0])
        c, d = (x, length - 30.0, LIGHT_Z[1]), (x, 30.0, LIGHT_Z[1])
        if s > 0:
            m.quad(a, b, c, d, 2)
        else:
            m.quad(a, d, c, b, 2)
    # Floor inlays: a pair of glowing strips at each module's centre, flush with the top (0.5 cm proud).
    for k in range(modules):
        yc = (k + 0.5) * pitch
        for s in (-1, 1):
            x0, x1 = sorted((s * INLAY_X[0], s * INLAY_X[1]))
            z = LIFT + 0.5
            m.quad((x0, yc - INLAY_HALF_LEN, z), (x1, yc - INLAY_HALF_LEN, z),
                   (x1, yc + INLAY_HALF_LEN, z), (x0, yc + INLAY_HALF_LEN, z), 2)   # facing up
    return m


def straight_level_deck(road):
    o = road["cross_section_offsets_m"]
    if 0 not in o or -12 not in o or 12 not in o:
        raise ValueError(f"{road['id']}: cross-sections lack the -12/0/12 m offsets")
    c = np.array([s[o.index(0)] for s in road["cross_sections_m"]], float)
    left = np.array([s[o.index(-12)] for s in road["cross_sections_m"]], float)
    right = np.array([s[o.index(12)] for s in road["cross_sections_m"]], float)
    a, b = c[0, :2], c[-1, :2]
    d = (b - a) / np.linalg.norm(b - a)
    n = np.array([-d[1], d[0]])
    off = np.abs((c[:, :2] - a) @ n).max()
    rise = np.ptp(np.concatenate([c[:, 2], left[:, 2], right[:, 2]]))
    if off > 0.5 or rise > 0.3:
        # A curved or graded deck needs a swept shell along its stations; not authored yet.
        raise ValueError(f"{road['id']}: deck is not straight and level (off {off:.2f} m, rise {rise:.2f} m)")
    # +x of the bridge frame is the -12 -> +12 cross-section direction projected on the road normal.
    side = np.sign(((right[0, :2] - left[0, :2]) @ n)) or 1.0
    return a, d, side, float(np.linalg.norm(b - a)), float(c[:, 2].mean())


def gaps(field, a, d, length_m, deck_z):
    us = np.arange(0, length_m + 0.01, 0.5)
    z = np.array([field.sample(*(a + d * u), bounds_error=False) for u in us])
    low = z < deck_z - GAP_DROP / 100
    out, start = [], None
    for u, l in zip(us, low):
        if l and start is None:
            start = u
        if not l and start is not None:
            out.append((start, u)); start = None
    if start is not None:
        out.append((start, us[-1]))
    return [g for g in out if g[1] - g[0] >= 4]


def corners(lo, hi):
    return np.array([[x, y, z] for x in (lo[0], hi[0]) for y in (lo[1], hi[1]) for z in (lo[2], hi[2])])


def build_bridge(road, field, kit):
    a, d, side, length_m, deck_z = straight_level_deck(road)
    L = length_m * 100
    modules = max(1, round(L / PITCH))
    pitch = L / modules
    bounds = {k: (np.asarray(v[0]), np.asarray(v[1])) for k, v in kit["mesh_bounds_cm"].items()}
    flipz = np.diag([-1.0, -1.0, 1.0])

    # Bridge frame -> site metres, for terrain queries.
    nrm = np.array([-d[1], d[0]]) * side

    def site(x, y):
        return a + d * (y / 100) + nrm * (x / 100)

    pieces = []   # (mesh, R local, t local)
    # Edge posts: 343's pairs, every other module boundary (every ~30 m), just outboard of the fascia.
    posts = [i for i in kit["modules"]["tile_a"] if "Pillar_w4_d2" in i["mesh"]]
    lo, hi = bounds[posts[0]["mesh"]]
    for k in range(1, modules, 2):
        yb = k * pitch
        for p in posts:
            R = np.asarray(p["r"], float)
            box = corners(lo, hi) @ R.T
            inner = np.abs(box[:, 0] + p["t"][0]).min()
            x = p["t"][0] + math.copysign(FASCIA + POST_GAP - inner, p["t"][0])
            # 343's pair straddles the narrow tile's centre at +-175 cm; keep that spacing.
            dy = math.copysign(175.0, p["t"][1]) * pitch / PITCH
            pieces.append((p["mesh"], R, np.array([x, yb + dy, LIFT + p["t"][2]])))
    # End pylons flanking the road at each deck end, outboard of its shoulder, standing on the ground.
    # They have no collision, so they stay off everything the road's own width and shoulder promise.
    py = kit["modules"]["pylon"][0]
    plo, phi = bounds[py["mesh"]]
    half = max(abs(plo[0]), abs(phi[0]))
    offset = SLAB_HALF_WIDTH + float(road.get("shoulder_m", 0)) * 100 + half + PYLON_CLEAR
    skipped = []

    def seat(R, t):
        box = corners(plo, phi) @ R.T + t
        ground = np.array([field.sample(*site(x, y), bounds_error=False)
                           for x in np.linspace(box[:, 0].min(), box[:, 0].max(), 5)
                           for y in np.linspace(box[:, 1].min(), box[:, 1].max(), 7)]) * 100
        base = deck_z * 100 + box[:, 2].min()
        if not np.all(np.isfinite(ground)) or np.median(ground) < base - PYLON_MAX_SINK or ground.min() < base - 2 * PYLON_MAX_SINK:
            return None
        return t + np.array([0.0, 0.0, min(np.median(ground) - base, 0.0) - 30.0])

    for flip, y0 in ((False, 0.0), (True, L)):
        R = flipz @ np.asarray(py["r"], float) if flip else np.asarray(py["r"], float)
        f = -1 if flip else 1
        # A gateway is a pair: slide it landward until both stand on ground, else leave that end bare.
        for back in (0.0, 500.0, 1000.0, 1500.0):
            pair = [seat(R, np.array([s * offset, y0 + (py["t"][1] - back) * f, LIFT + py["t"][2]])) for s in (-1, 1)]
            if all(q is not None for q in pair):
                pieces.extend((py["mesh"], R, q) for q in pair)
                break
        else:
            skipped.append("end" if flip else "start")
    # Hanging brackets at the banks of each gap, top against the keel, deep end into the bank.
    br = next(i for i in kit["modules"]["end"] if "Bridge_E_Pillar" in i["mesh"])
    blo, bhi = bounds[br["mesh"]]
    gap_list = gaps(field, a, d, length_m, deck_z)
    for g0, g1 in gap_list:
        for flip, edge in ((False, g0 * 100 - 600), (True, g1 * 100 + 600)):
            R = flipz @ np.asarray(br["r"], float) if flip else np.asarray(br["r"], float)
            box = corners(blo, bhi) @ R.T
            f = -1 if flip else 1
            pieces.append((br["mesh"], R, np.array([0.0, edge + br["t"][1] * f, KEEL_Z + 5 - box[:, 2].max()])))

    # Bridge frame -> UE: +y along the road, +x toward the +12 m offset, z from the slab top.
    du = np.array([d[0], -d[1], 0.0]); nu = np.array([nrm[0], -nrm[1], 0.0])
    F = np.column_stack([nu, du, [0, 0, 1.0]])
    if np.linalg.det(F) < 0:   # keep a proper rotation; mirror the frame's x instead
        raise ValueError(f"{road['id']}: bridge frame is mirrored")
    origin = np.array([a[0] * 100, -a[1] * 100, deck_z * 100])
    m = shell(L, modules)
    # Unreal's front face has normal (c - a) x (b - a), the opposite of the right-handed winding built
    # above, so each triangle is emitted as (a, c, b); the supplied normals stay outward.
    ue_idx = [i for k in range(0, len(m.idx), 3) for i in (m.idx[k], m.idx[k + 2], m.idx[k + 1])]
    mesh = dict(positions=[[round(v, 3) for v in F @ p] for p in m.p], normals=[[round(v, 5) for v in F @ n] for n in m.n],
                indices=ue_idx, sections=m.sec, slots=SECTIONS,
                # The plate shader lays its plates along the deck: the deck's UE direction, for the vertex colour.
                axis=[round(float(du[0]), 6), round(float(du[1]), 6)])
    placed = [dict(mesh=name, path=kit["path_of"][name], t=[round(v, 2) for v in origin + F @ t],
                   r=(F @ R).round(6).tolist(), s=[1.0, 1.0, 1.0]) for name, R, t in pieces]
    info = dict(id=road["id"], structure=road["structure"], length_m=round(length_m, 2), deck_z_m=round(deck_z, 3),
                modules=modules, pitch_m=round(pitch / 100, 3), gaps_m=[[round(g0, 1), round(g1, 1)] for g0, g1 in gap_list],
                shell_triangles=len(m.sec), pieces=len(placed), pylons_skipped=skipped)
    return info, dict(id=road["id"], origin_cm=[round(v, 2) for v in origin], mesh=mesh, placements=placed), (F, origin, pieces, bounds)


def check(info, frame):
    """Nothing solid above the deck inside the collision width (the shell is checked by ray in the preview)."""
    F, origin, pieces, bounds = frame
    issues = []
    for name, R, t in pieces:
        lo, hi = bounds[name]
        box = corners(lo, hi) @ R.T + t
        if box[:, 2].max() > LIFT + 1 and box[:, 0].min() < SLAB_HALF_WIDTH and box[:, 0].max() > -SLAB_HALF_WIDTH:
            issues.append(f"{name} stands above the deck inside the collision width")
    if TOP_EDGE < SLAB_HALF_WIDTH or KEEL_Z > -SLAB_DEPTH:
        issues.append("shell does not enclose the collision slab")
    info["issues"] = issues
    return issues


def write_obj(path, verts, faces):
    with open(path, "w") as f:
        for v in verts:
            f.write("v %.3f %.3f %.3f\n" % tuple(v))
        for t in faces:
            f.write("f " + " ".join(str(i + 1) for i in t) + "\n")


def previews(out_dir, road, field, geometry, bridge):
    """Terrain patch, the collision slab and the shell, in Blender metres (= site metres)."""
    sys.path.insert(0, str(HERE.parents[1] / "levels/warfare/pwr"))
    from world_geometry import bridge_parts
    c = np.array([s[road["cross_section_offsets_m"].index(0)] for s in road["cross_sections_m"]])
    lo = c[:, :2].min(0) - 60; hi = c[:, :2].max(0) + 60
    xs = np.arange(lo[0], hi[0], 2.0); ys = np.arange(lo[1], hi[1], 2.0)
    verts = [(x, y, field.sample(x, y, bounds_error=False)) for y in ys for x in xs]
    nx = len(xs); faces = []
    for j in range(len(ys) - 1):
        for i in range(nx - 1):
            q = j * nx + i
            faces += [(q, q + 1, q + nx + 1), (q, q + nx + 1, q + nx)]
    write_obj(out_dir / f"{road['id']}_terrain.obj", verts, faces)
    for part in bridge_parts(geometry, field):
        if part["name"] == road["id"] + "_deck":
            write_obj(out_dir / f"{road['id']}_slab.obj", part["vertices_m"], part["faces"])
    o = np.asarray(bridge["origin_cm"])
    for sec, name in enumerate(SECTIONS):
        pts, tris = [], []
        P = bridge["mesh"]["positions"]
        for t, s in enumerate(bridge["mesh"]["sections"]):
            if s != sec:
                continue
            for k in (0, 2, 1):
                q = (np.asarray(P[bridge["mesh"]["indices"][3 * t + k]]) + o) / 100
                pts.append((q[0], -q[1], q[2]))
            tris.append((len(pts) - 3, len(pts) - 2, len(pts) - 1))
        write_obj(out_dir / f"{road['id']}_shell_{name}.obj", pts, tris)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--geometry", type=Path, required=True)
    ap.add_argument("--heightfield", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--kit", type=Path, default=KIT)
    ap.add_argument("--previews", action="store_true")
    ap.add_argument("--mjolnir", default=str(HERE.parents[1] / "target/release/mjolnir.exe"))
    ap.add_argument("--paks", default=os.environ.get("HCE_PAKS", "C:/Program Files (x86)/Steam/steamapps/common/Halo Campaign Evolved/Meteorite/Content/Paks"))
    a = ap.parse_args()
    kit = json.loads(a.kit.read_text())
    geometry = json.loads(a.geometry.read_text())
    field = load_heightfield(a.heightfield)
    a.out.mkdir(parents=True, exist_ok=True)
    report, bridges = [], []
    for road in geometry["roads"]:
        if road.get("structure") not in ("bridge", "culvert"):
            continue
        info, bridge, frame = build_bridge(road, field, kit)
        check(info, frame)
        report.append(info); bridges.append(bridge)
        if a.previews:
            previews(a.out, road, field, geometry, bridge)
    # Editor stand-ins for 343's meshes: a box of each mesh's cooked bounds with its slots (foliage_bake).
    from foliage_bake import mesh_info
    standins = {p: mesh_info(a.mjolnir, a.paks, p) for p in sorted({q["path"] for b in bridges for q in b["placements"]})}
    doc = dict(schema="mjolnir-forerunner-bridges-v2", coordinates="unreal_centimetres", kit=kit["schema"],
               slots=SECTIONS, bridges=bridges, standins=standins, report=report)
    (a.out / "bridges.json").write_text(json.dumps(doc))
    for r in report:
        print(json.dumps(r))
    if any(r["issues"] for r in report):
        raise SystemExit("Bridge dressing has clearance issues")


if __name__ == "__main__":
    main()
