#!/usr/bin/env python3
"""Take placed props out of a converted map's merged meshes, in place of
nothing: their triangles collapsed to a point, so every material slot, UV
and lightmap page of the mesh stays where it was.

    python tools/level/remove_placed_props.py <staging> <in.gltf> <out.gltf> --asset <tag path> [--asset ...]

merge_ce_scene.py merges every placed scenery object into the terrain (and
translucent) mesh. A prop that is to become a physics object of its own (a
Halo 2 fusion coil as a crate the simulation moves) has to leave the static
mesh, or its copy stays behind when the live one is knocked away. A slot
cannot simply be hidden: Zanzibar's coil frame shares its material with the
drums, packing crates and pallets. Removing the triangles would renumber the
slots the level file's materials are listed by; collapsing them keeps the
mesh's layout.

A triangle goes when its material is one of the prop model's own and its
centroid lies within the model's reach of one placement's origin (the
farthest model vertex from the origin, plus MARGIN): a sphere, so a prop
knocked over on its side (Zanzibar has several, pitch or roll near 90
degrees) is found without matching merge_ce_scene.py's rotation order.
Check the count: one model's triangles a placement, or something close by
of the same materials was caught too. glTF positions are metres (x, z, -y)
x 3.048 of Halo's world units, as merge_ce_scene.py writes them.
"""
import argparse
import json
import math
import os
import shutil
import struct

WU = 3.048
MARGIN = 0.06  # world units


def load(path):
    g = json.load(open(path, encoding="utf-8"))
    base = os.path.dirname(path)
    bins = [open(os.path.join(base, b["uri"]), "rb").read() for b in g["buffers"]]
    return g, bins


def view(g, bins, acc_index):
    a = g["accessors"][acc_index]
    v = g["bufferViews"][a["bufferView"]]
    comp = {5126: ("f", 4), 5125: ("I", 4), 5123: ("H", 2), 5121: ("B", 1)}[a["componentType"]]
    n = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4}[a["type"]]
    off = v.get("byteOffset", 0) + a.get("byteOffset", 0)
    stride = v.get("byteStride") or comp[1] * n
    return a, v, comp, n, off, stride


def model_box(staging, model):
    g, bins = load(os.path.join(staging, model))
    lo, hi = [1e9] * 3, [-1e9] * 3
    mats = {m.get("name") for m in g.get("materials", [])}
    for mesh in g["meshes"]:
        for p in mesh["primitives"]:
            a = g["accessors"][p["attributes"]["POSITION"]]
            lo = [min(x, y) for x, y in zip(lo, a["min"])]
            hi = [max(x, y) for x, y in zip(hi, a["max"])]
    # glTF (x, y-up, -z) metres -> Halo (x, y, z) world units
    hlo = [lo[0] / WU, -hi[2] / WU, lo[1] / WU]
    hhi = [hi[0] / WU, -lo[2] / WU, hi[1] / WU]
    return hlo, hhi, mats


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("staging")
    ap.add_argument("src")
    ap.add_argument("out")
    ap.add_argument("--asset", action="append", required=True, help="tag path of the placed prop, as placement.json names it")
    a = ap.parse_args()
    placement = json.load(open(os.path.join(a.staging, "placement.json"), encoding="utf-8"))
    boxes, materials = [], set()
    for e in placement["entries"]:
        if e.get("asset") in a.asset and e.get("model"):
            lo, hi, mats = model_box(a.staging, e["model"])
            materials |= mats
            reach = max(math.dist((0, 0, 0), (x, y, z)) for x in (lo[0], hi[0]) for y in (lo[1], hi[1])
                        for z in (lo[2], hi[2]))
            boxes.append((e["pos"], reach + MARGIN, mats))
    if not boxes:
        raise SystemExit("no placement of " + ", ".join(a.asset))
    g, bins = load(a.src)
    bins = [bytearray(b) for b in bins]
    taken = 0
    for mesh in g["meshes"]:
        for p in mesh["primitives"]:
            mat = g["materials"][p["material"]].get("name", "") if "material" in p else ""
            # The merged mesh's materials are `<shader>__lm<N>` (one a lightmap page).
            if not any(mat == m or mat.startswith(m + "__") for m in materials):
                continue
            pa, pv, pc, pn, poff, pstride = view(g, bins, p["attributes"]["POSITION"])
            buf = bins[pv["buffer"]]

            def pos(i):
                x, y, z = struct.unpack_from("<3f", buf, poff + i * pstride)
                return [x / WU, -z / WU, y / WU]

            ia, iv, ic, _n, ioff, istride = view(g, bins, p["indices"])
            ibuf = bins[iv["buffer"]]
            idx = [struct.unpack_from("<" + ic[0], ibuf, ioff + k * ic[1])[0] for k in range(ia["count"])]
            # Every corner of every taken triangle goes to ONE point (the
            # placement's origin). Collapsing each triangle onto its own
            # first corner moved corners shared with triangles collapsed
            # before it, and left thin black slivers floating where the props
            # had been (Zanzibar's coils, 2026-11-15).
            gone = {}
            for t in range(0, len(idx), 3):
                tri = idx[t:t + 3]
                c = [sum(pos(i)[k] for i in tri) / 3 for k in range(3)]
                for bpos, reach, own in boxes:
                    # Only the placement's own model's materials: a giant
                    # crate's reach covers a drum beside it, and they share
                    # the frame's material.
                    if not any(mat == m or mat.startswith(m + "__") for m in own):
                        continue
                    if math.dist(c, bpos) <= reach:
                        point = (bpos[0] * WU, bpos[2] * WU, -bpos[1] * WU)  # Halo wu -> glTF metres
                        for i in tri:
                            gone.setdefault(i, point)
                        taken += 1
                        break
            # One point for the whole section, not one a placement: stacked
            # props share corners where they touch (Zanzibar's giant crates,
            # one on the other), and a triangle whose corners went to two
            # origins stretched between them (2026-11-15).
            if gone:
                point = next(iter(gone.values()))
                for i in gone:
                    struct.pack_into("<3f", buf, poff + i * pstride, *point)
    out_dir = os.path.dirname(os.path.abspath(a.out))
    stem = os.path.splitext(os.path.basename(a.out))[0]
    for n, b in enumerate(g["buffers"]):
        name = f"{stem}.bin" if len(g["buffers"]) == 1 else f"{stem}_{n}.bin"
        open(os.path.join(out_dir, name), "wb").write(bins[n])
        b["uri"] = name
    json.dump(g, open(a.out, "w", encoding="utf-8"))
    print(f"{len(boxes)} placement(s) of {', '.join(a.asset)}: {taken} triangle(s) collapsed in {os.path.basename(a.src)}")


if __name__ == "__main__":
    main()
