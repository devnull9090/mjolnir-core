#!/usr/bin/env python3
"""Give each breakable sheet of glass a mesh slot of its own.

    split_breakable_glass.py <scene_translucent.gltf> <map.sbsp.breakables.json>

`mjolnir level collision` writes the sheets it made breakable (Halo 2's
glass: blam_sbsp::convert::rebuild_breakable) beside the BSP, each a
(instance, set) and its box in staged world units. Each transparent
triangle whose centre lies in a sheet's box (and whose plane is the
sheet's: within a few centimetres of the box's thin axis) moves into a
primitive of its own whose material is a copy of the triangle's, named
`<material>__brk<k>` (before a `__reflection` suffix, which stays last), and
whose extras carry the sheet: `halo.breakable = {sheet, min, max}`, the box in
Unreal centimetres. tools/level/build_terrain_meshes.py lists those slots on
the mesh's level entry (`breakables`), and the level loader hides a sheet's
slots when the game breaks it (its break effect names the point).

The glTF is rewritten in place; the vertices are shared, only index lists
are added. A scene with no sheet in reach is left as it is.
"""
import json
import os
import sys

import numpy as np

WU_M = 3.048          # world unit, metres (the staged glTF is in metres, +Y up)
WU_CM = 304.8         # world unit, Unreal centimetres
PAD = 0.05            # world units around a sheet's box


def load(path):
    doc = json.load(open(path, encoding="utf-8"))
    base = os.path.dirname(path)
    bins = [bytearray(open(os.path.join(base, b["uri"]), "rb").read()) for b in doc["buffers"]]
    return doc, bins


def accessor(doc, bins, i):
    a = doc["accessors"][i]
    bv = doc["bufferViews"][a["bufferView"]]
    n = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4}[a["type"]]
    dt = {5126: np.float32, 5125: np.uint32, 5123: np.uint16, 5121: np.uint8}[a["componentType"]]
    off = bv.get("byteOffset", 0) + a.get("byteOffset", 0)
    stride = bv.get("byteStride")
    raw = bytes(bins[bv["buffer"]])
    item = np.dtype(dt).itemsize * n
    if stride and stride != item:
        arr = np.ndarray((a["count"], n), dt, raw, off, (stride, np.dtype(dt).itemsize))
        return np.array(arr)
    arr = np.frombuffer(raw, dt, a["count"] * n, off)
    return arr.reshape(a["count"], n) if n > 1 else arr


def add_indices(doc, bins, indices):
    """Append a uint32 index list to buffer 0; returns its accessor."""
    buf = bins[0]
    while len(buf) % 4:
        buf.append(0)
    off = len(buf)
    data = np.asarray(indices, dtype=np.uint32).tobytes()
    buf.extend(data)
    doc["bufferViews"].append({"buffer": 0, "byteOffset": off, "byteLength": len(data), "target": 34963})
    doc["accessors"].append({"bufferView": len(doc["bufferViews"]) - 1, "componentType": 5125,
                             "count": len(indices), "type": "SCALAR"})
    return len(doc["accessors"]) - 1


def sheet_name(name, k):
    tail = "__reflection"
    if name.endswith(tail):
        return f"{name[:-len(tail)]}__brk{k}{tail}"
    return f"{name}__brk{k}"


def to_cm(p):
    """Staged world units (x, y, z) to Unreal centimetres (x, -y, z)."""
    return [round(float(p[0]) * WU_CM, 1), round(float(-p[1]) * WU_CM, 1), round(float(p[2]) * WU_CM, 1)]


def main():
    gltf, sheets_path = sys.argv[1:3]
    sheets = json.load(open(sheets_path, encoding="utf-8")).get("sheets") or []
    if not sheets:
        print("breakable glass: no sheets")
        return
    lo = np.array([s["min"] for s in sheets], dtype=np.float64) - PAD
    hi = np.array([s["max"] for s in sheets], dtype=np.float64) + PAD
    doc, bins = load(gltf)
    moved = {}
    for mesh in doc["meshes"]:
        out = []
        for prim in mesh["primitives"]:
            if prim.get("mode", 4) != 4 or "material" not in prim:
                out.append(prim)
                continue
            pos = accessor(doc, bins, prim["attributes"]["POSITION"]).astype(np.float64)
            idx = accessor(doc, bins, prim["indices"]).astype(np.int64).reshape(-1, 3)
            # glTF metres, +Y up -> staged world units (x, -z, y).
            tri = pos[idx]
            c = np.stack([tri[..., 0], -tri[..., 2], tri[..., 1]], -1).mean(1) / WU_M
            inside = np.all((c[:, None, :] >= lo[None]) & (c[:, None, :] <= hi[None]), axis=2)
            which = np.where(inside.any(1), inside.argmax(1), -1)
            if not (which >= 0).any():
                out.append(prim)
                continue
            keep = idx[which < 0]
            if len(keep):
                rest = dict(prim)
                rest["indices"] = add_indices(doc, bins, keep.reshape(-1))
                out.append(rest)
            base = doc["materials"][prim["material"]]
            for k in sorted(set(int(w) for w in which if w >= 0)):
                mat = json.loads(json.dumps(base))
                mat["name"] = sheet_name(base.get("name", "glass"), k)
                halo = mat.setdefault("extras", {}).setdefault("halo", {})
                halo["breakable"] = {"sheet": k, "instance": sheets[k]["instance"], "set": sheets[k]["set"],
                                     "min": to_cm([sheets[k]["min"][0], sheets[k]["max"][1], sheets[k]["min"][2]]),
                                     "max": to_cm([sheets[k]["max"][0], sheets[k]["min"][1], sheets[k]["max"][2]])}
                doc["materials"].append(mat)
                part = dict(prim)
                part["material"] = len(doc["materials"]) - 1
                part["indices"] = add_indices(doc, bins, idx[which == k].reshape(-1))
                out.append(part)
                moved[k] = moved.get(k, 0) + int((which == k).sum())
        mesh["primitives"] = out
    if not moved:
        print("breakable glass: no transparent triangle on a sheet")
        return
    doc["buffers"][0]["byteLength"] = len(bins[0])
    open(os.path.join(os.path.dirname(gltf), doc["buffers"][0]["uri"]), "wb").write(bytes(bins[0]))
    json.dump(doc, open(gltf, "w", encoding="utf-8"))
    print(f"breakable glass: {sum(moved.values())} triangle(s) of {len(moved)} of {len(sheets)} sheet(s) "
          f"in slots of their own")


if __name__ == "__main__":
    main()
