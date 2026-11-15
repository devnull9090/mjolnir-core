"""A converted map's terrain mesh cut into a grid of meshes Lumen can light.

    python tools/level/structure_chunks.py <level.json> <scene.gltf> <out_dir> [--cell 2000]
        [--cliff cliff_mesh.json] [--swap swap.json] [--code ZAN]

The map's terrain (SM_<CODE>_Terrain) is written by rewriting a shipped
engine mesh (ue-asset mesh_write): it carries no Lumen mesh cards, so
Lumen's surface cache has nothing for any wall and its bounce light and
short-range AO come back black indoors (Zanzibar, 2026-11-14: Lumen's
overview showed the whole level as missing surface cache coverage; the
stock-cooked cladding rocks beside it were covered). Built in the stock
editor instead (Scripts/build_ce_cliffs.py), a mesh gets cards, but only a
few dozen a mesh, set around its outside: one level-sized mesh would still
leave every room uncovered. So the terrain's triangles go into square
cells (by their centre, `--cell` cm in x and y), one mesh a cell, each slot
kept as `slot_<terrain slot>` for the loader to give it the terrain slot's
material.

Left out: the cliff slots (`--cliff`: cliff_mesh.py's output, drawn by the
tessellated cliff mesh), the slots scenery_swap.py hides (`--swap`) and
M_CE_Hidden. Positions are Unreal centimetres placed at the origin, as the
cliff mesh is (glTF (x, y, z) m -> (x, z, y) * 100).

Writes <out_dir>/<name>.json for each cell and prints one
`SM_<CODE>_Lumen_X<i>_Y<j>=<path>` spec a line for build_ce_cliffs.py.
"""
import argparse
import glob
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
OPAQUE = ("M_CE_Environment", "M_CE_EnvironmentMasked")


def incident_colour(doc, data, att, N, read_accessor):
    """CE's incident light direction (the glTF's _INCIDENT) as the vertex
    colour M_CE_Environment's bump term reads (`Incident`), packed as the
    terrain mesh packs it (ue-asset examples/mesh_rewrite.rs): the unit
    direction in the vertex's tangent frame in rgb, its length in alpha, a
    byte each. The editor's build stores a colour sRGB-encoded and the shader
    reads the byte as it is, so the bytes go in sRGB-decoded. Unreal
    recomputes the tangents; the glTF's stand in for them here. Without it
    (black) the bump term turned every slot on the master dark."""
    n = len(N)
    if "_INCIDENT" not in att or "TANGENT" not in att:
        return np.tile([0.5, 0.5, 1.0, 0.0], (n, 1))
    inc = read_accessor(doc, data, att["_INCIDENT"]).astype(np.float64)[:, [0, 2, 1]]
    tan = read_accessor(doc, data, att["TANGENT"]).astype(np.float64)
    t, sign = tan[:, [0, 2, 1]], -tan[:, 3:4]
    length = np.linalg.norm(inc, axis=1, keepdims=True)
    d = inc / np.maximum(length, 1e-6)
    b = np.cross(N, t) * sign
    packed = np.concatenate([(d * t).sum(1, keepdims=True), (d * b).sum(1, keepdims=True),
                             (d * N).sum(1, keepdims=True)], 1)
    rgb = np.round((np.clip(packed, -1, 1) * 0.5 + 0.5) * 255.0) / 255.0
    a = np.round(np.clip(length, 0, 1) * 255.0) / 255.0
    srgb = np.concatenate([rgb, a], 1)
    # sRGB-decode rgb (the build encodes it back); alpha is stored linear.
    lin = np.where(srgb <= 0.04045, srgb / 12.92, ((srgb + 0.055) / 1.055) ** 2.4)
    lin[:, 3] = srgb[:, 3]
    return lin


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("level")
    ap.add_argument("scene")
    ap.add_argument("out_dir")
    ap.add_argument("--cell", type=float, default=2000.0, help="cell size, cm")
    ap.add_argument("--cliff", help="cliff_mesh.py's output: its slots are left out")
    ap.add_argument("--swap", help="scenery_swap.py's swap.json: its hidden slots are left out")
    ap.add_argument("--code", default="MAP")
    ap.add_argument("--cards", type=int, default=32, help="Lumen mesh cards a mesh (build setting)")
    ap.add_argument("--slot-offset", type=int, default=1)
    a = ap.parse_args()
    sys.path.insert(0, HERE)
    from refine_water_gltf import read_accessor

    level = json.load(open(a.level, encoding="utf-8"))
    terrain = next(i for i in level["decor"] if str(i.get("id", "")).endswith("_terrain"))
    cliff = set(json.load(open(a.cliff, encoding="utf-8"))["slots"]) if a.cliff and os.path.exists(a.cliff) else set()
    hide = json.load(open(a.swap, encoding="utf-8")).get("hide", []) if a.swap and os.path.exists(a.swap) else []
    doc = json.load(open(a.scene, encoding="utf-8"))
    data = open(os.path.join(os.path.dirname(a.scene), doc["buffers"][0]["uri"]), "rb").read()

    keep = {}  # glTF material -> terrain slot
    for i, m in enumerate(terrain.get("materials") or []):
        parent = (m.get("parent") if isinstance(m, dict) else str(m)).split(".")[-1]
        if i in cliff or m in hide or parent not in OPAQUE:
            continue
        keep[i - a.slot_offset] = i

    pos, nrm, uv0, uv1, slot, col = [], [], [], [], [], []
    for p in [q for mesh in doc["meshes"] for q in mesh["primitives"]]:
        s = keep.get(p["material"])
        if s is None:
            continue
        att = p["attributes"]
        P = read_accessor(doc, data, att["POSITION"]).astype(np.float64)[:, [0, 2, 1]] * 100.0
        N = read_accessor(doc, data, att["NORMAL"]).astype(np.float64)[:, [0, 2, 1]]
        T0 = read_accessor(doc, data, att["TEXCOORD_0"]).astype(np.float64)
        T1 = read_accessor(doc, data, att["TEXCOORD_1"]).astype(np.float64)
        C = incident_colour(doc, data, att, N, read_accessor)
        idx = read_accessor(doc, data, p["indices"]).reshape(-1, 3).astype(np.int64)
        # The axis swap mirrors the mesh: keep the winding that agrees with
        # the exported normals (as cliff_mesh.py does).
        a_, b_, c_ = P[idx[:, 0]], P[idx[:, 1]], P[idx[:, 2]]
        face = np.cross(c_ - a_, b_ - a_)
        flip = (face * (N[idx[:, 0]] + N[idx[:, 1]] + N[idx[:, 2]])).sum(1) < 0
        idx[flip] = idx[flip][:, [0, 2, 1]]
        pos.append(P[idx])
        nrm.append(N[idx])
        uv0.append(T0[idx])
        uv1.append(T1[idx])
        col.append(C[idx])
        slot += [s] * len(idx)
    pos, nrm = np.concatenate(pos), np.concatenate(nrm)
    uv0, uv1, slot = np.concatenate(uv0), np.concatenate(uv1), np.asarray(slot)
    col = np.concatenate(col)

    centre = pos.mean(1)
    cell = np.floor(centre[:, :2] / a.cell).astype(np.int64)
    os.makedirs(a.out_dir, exist_ok=True)
    # A cell left from another run (another cell size) would be listed too.
    for old in glob.glob(os.path.join(a.out_dir, f"SM_{a.code}_Lumen_*.json")):
        os.remove(old)
    specs = []
    for key in sorted(set(map(tuple, cell))):
        sel = np.where((cell[:, 0] == key[0]) & (cell[:, 1] == key[1]))[0]
        slots = sorted(set(slot[sel].tolist()))
        section = np.array([slots.index(s) for s in slot[sel]])
        # Sections in slot order, so each slot's triangles run together.
        order = np.argsort(section, kind="stable")
        sel, section = sel[order], section[order]
        corners = pos[sel].reshape(-1, 3)
        c_uv0, c_uv1 = uv0[sel].reshape(-1, 2), uv1[sel].reshape(-1, 2)
        shade = nrm[sel].reshape(-1, 3)
        colour = col[sel].reshape(-1, 4)
        # Corners that agree in everything share a vertex (cliff_mesh.py --flat).
        attrs = np.concatenate([corners.round(2), c_uv0.round(5), c_uv1.round(5), shade.round(4), colour.round(4)], 1)
        index_of = {}
        index = np.array([index_of.setdefault(tuple(r), len(index_of)) for r in attrs])
        first = np.zeros(len(index_of), dtype=np.int64)
        first[index[::-1]] = np.arange(len(index))[::-1]
        # No name may end in `_<digits>`: Unreal reads that as an FName
        # number, and such a package would not load by its path (47 of
        # Zanzibar's 161 cells, 2026-11-14).
        name = f"SM_{a.code}_Lumen_X{key[0]}_Y{key[1]}".replace("-", "m")
        out = {
            "item": terrain["id"], "slots": slots,
            "positions": corners[first].round(3).tolist(), "normals": shade[first].round(5).tolist(),
            "indices": index.tolist(), "uv0": c_uv0.round(6).tolist(), "uv1": c_uv1.round(6).tolist(),
            "shade": shade.round(5).tolist(), "sections": section.tolist(), "weight": [0.0] * len(first),
            "colors": colour[first].round(5).tolist(),
            "nanite": False, "material": "M_CE_CliffTess", "lumen_cards": a.cards,
        }
        path = os.path.join(a.out_dir, name + ".json")
        json.dump(out, open(path, "w", encoding="utf-8"))
        specs.append(f"{name}={path}")
    for s in specs:
        print(s)
    print(f"{len(slot)} triangle(s) from {len(keep)} slot(s) in {len(specs)} cell mesh(es) of {a.cell:g} cm",
          file=sys.stderr)


if __name__ == "__main__":
    main()
