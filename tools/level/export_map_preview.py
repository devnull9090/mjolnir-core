#!/usr/bin/env python3
"""Export a converted map's terrain as the hub's small preview model.

    export_map_preview.py <conversion out dir> <CODE> <dest dir> [--manifest m.json]

The hub draws a match's kills and deaths over the map they happened on
(hub/src/app/matches/_components/MatchMap.tsx). The model is the map's
`scene.gltf` (merge_ce_scene.py: the BSP with its scenery merged in; the sky
and the translucent pieces are left out), cut down to what a browser needs:

- one primitive, positions as normalized int16 under a node scale and
  translation, normals as int8 (KHR_mesh_quantization), no UVs;
- a vertex colour standing in for the textures: CE's texture pass with the
  base map shrunk to 16x16 and sampled at the vertex (Blood Gulch's dirt
  paths survive it) and each detail map as its average colour, times the
  lightmap at the vertex (an object's own lighting texel for placed scenery,
  times its incident term).

The axes stay glTF's: metres, Y up, and the Unreal positions a match records
are (x, z, y) * 100 of them (convert_ce_map.sh puts the map at CE
coordinates; the Unreal side negates CE's Y, glTF's Z is -Y).

`<dest>/<CODE>.glb` is written and, with --manifest, its entry (bytes,
triangles, Unreal bounds) merged into that JSON.
"""
import argparse
import json
import os
import struct
import sys

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from merge_ce_scene import load_gltf, primitives  # noqa: E402

BASE_SIZE = 16


def srgb_to_linear(c):
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


class Textures:
    """Bitmaps as RGBA floats in their own gamma space, the space CE's
    fixed-function shading worked in."""

    def __init__(self, folder):
        self.folder = folder
        self.cache = {}

    def get(self, name, size=None):
        """An image shrunk to size x size when given; None when missing."""
        key = (name, size)
        if key not in self.cache:
            path = os.path.join(self.folder, name) if name else None
            if not path or not os.path.exists(path):
                self.cache[key] = None
            else:
                im = Image.open(path).convert("RGBA")
                if size:
                    im = im.resize((size, size), Image.Resampling.BOX)
                self.cache[key] = np.asarray(im, dtype=np.float64) / 255.0
        return self.cache[key]

    def mean(self, name):
        """A detail map's average colour and alpha: at a preview's size a
        tiled detail map is its average."""
        img = self.get(name, 1)
        return None if img is None else img[0, 0]


def sample(img, uv, wrap):
    """Bilinear samples of img at uv (glTF: origin top left)."""
    h, w, _ = img.shape
    u = uv[:, 0] * w - 0.5
    v = uv[:, 1] * h - 0.5
    x0 = np.floor(u).astype(np.int64)
    y0 = np.floor(v).astype(np.int64)
    fx = (u - x0)[:, None]
    fy = (v - y0)[:, None]

    def at(x, y):
        if wrap:
            x, y = x % w, y % h
        else:
            x, y = np.clip(x, 0, w - 1), np.clip(y, 0, h - 1)
        return img[y, x]

    top = at(x0, y0) * (1 - fx) + at(x0 + 1, y0) * fx
    bottom = at(x0, y0 + 1) * (1 - fx) + at(x0 + 1, y0 + 1) * fx
    return top * (1 - fy) + bottom * fy


def detail(base, d, function):
    """CE's detail functions (docs/ce_map_conversion.md, the texture pass)."""
    if function == 1:
        out = base * d
    elif function == 2:
        out = base + 2 * d - 1
    else:
        out = 2 * base * d
    return np.clip(out, 0, 1)


def vertex_colours(p, materials, tex):
    """The texture pass at the vertex, with each detail map as its average,
    times the lightmap pass; linear, as glTF vertex colours are."""
    n = len(p["pos"])
    halo = p["extras"].get("halo", {})
    shader = materials.get(halo.get("material", ""), {}).get("shader", {})
    base = tex.get(shader.get("base_map"), BASE_SIZE)
    texel = sample(base, p["uv0"], wrap=True) if base is not None else np.full((n, 4), 0.5)
    colour = texel[:, :3]
    d = shader.get("detail") or {}
    primary, secondary = tex.mean(d.get("primary")), tex.mean(d.get("secondary"))
    if primary is not None or secondary is not None:
        primary = primary if primary is not None else secondary
        secondary = secondary if secondary is not None else primary
        # Blended shaders blend by the base map's alpha (low shows the
        # secondary map), normal ones by the secondary map's own.
        t = texel[:, 3:4] if shader.get("shader_type") == 1 else np.full((n, 1), secondary[3])
        colour = detail(colour, secondary[:3] * (1 - t) + primary[:3] * t, d.get("function", 0))
    micro = tex.mean(d.get("micro"))
    if micro is not None:
        colour = detail(colour, micro[:3], d.get("micro_function", 0))

    light = np.ones((n, 3))
    lm = tex.get(halo.get("lightmap_texture"))
    if lm is not None and p["uv1"] is not None:
        light = sample(lm, p["uv1"], wrap=False)[:, :3]
        if halo.get("lightmap_index") == "objects" and p["inc"] is not None:
            # A placed object's texel is its brightest lighting; each
            # vertex takes its share by its normal (merge_ce_scene.py).
            share = np.clip(np.sum(p["nrm"] * p["inc"][:, :3], axis=1), 0, 1)
            light = light * (0.35 + 0.65 * share)[:, None]
    return srgb_to_linear(np.clip(colour * light, 0, 1))


def pad4(b):
    return b + b"\0" * (-len(b) % 4)


def write_glb(path, pos, nrm, col, idx, extras):
    lo, hi = pos.min(axis=0), pos.max(axis=0)
    centre = (lo + hi) / 2
    half = np.maximum((hi - lo) / 2, 1e-6)
    qpos = np.round((pos - centre) / half * 32767).astype(np.int16)
    qpos = np.hstack([qpos, np.zeros((len(qpos), 1), np.int16)])  # 8-byte stride
    qnrm = np.round(np.clip(nrm, -1, 1) * 127).astype(np.int8)
    qnrm = np.hstack([qnrm, np.zeros((len(qnrm), 1), np.int8)])
    qcol = np.hstack([np.round(col * 255).astype(np.uint8), np.full((len(col), 1), 255, np.uint8)])
    big = len(pos) > 65535
    qidx = idx.astype(np.uint32 if big else np.uint16)

    chunks = [qpos.tobytes(), qnrm.tobytes(), qcol.tobytes(), qidx.tobytes()]
    views, offset, binary = [], 0, b""
    for i, c in enumerate(chunks):
        view = {"buffer": 0, "byteOffset": offset, "byteLength": len(c)}
        if i < 3:
            view["byteStride"] = (8, 4, 4)[i]
            view["target"] = 34962
        else:
            view["target"] = 34963
        views.append(view)
        binary += pad4(c)
        offset = len(binary)

    qmin = qpos[:, :3].min(axis=0).tolist()
    qmax = qpos[:, :3].max(axis=0).tolist()
    doc = {
        "asset": {"version": "2.0", "generator": "export_map_preview.py", "extras": extras},
        "extensionsUsed": ["KHR_mesh_quantization"],
        "extensionsRequired": ["KHR_mesh_quantization"],
        "scene": 0,
        "scenes": [{"nodes": [0]}],
        "nodes": [{
            "mesh": 0, "name": extras["code"],
            "translation": centre.tolist(),
            # Normalized int16 decodes to -1..1.
            "scale": half.tolist(),
        }],
        "meshes": [{"primitives": [{
            "attributes": {"POSITION": 0, "NORMAL": 1, "COLOR_0": 2},
            "indices": 3, "material": 0,
        }]}],
        "materials": [{"name": "terrain", "pbrMetallicRoughness": {"metallicFactor": 0, "roughnessFactor": 1}}],
        "accessors": [
            # glTF's min/max are of the stored values: int16 as stored.
            {"bufferView": 0, "componentType": 5122, "normalized": True, "count": len(pos), "type": "VEC3",
             "min": qmin, "max": qmax},
            {"bufferView": 1, "componentType": 5120, "normalized": True, "count": len(pos), "type": "VEC3"},
            {"bufferView": 2, "componentType": 5121, "normalized": True, "count": len(pos), "type": "VEC4"},
            {"bufferView": 3, "componentType": 5125 if big else 5123, "count": len(qidx), "type": "SCALAR"},
        ],
        "bufferViews": views,
        "buffers": [{"byteLength": len(binary)}],
    }
    js =json.dumps(doc, separators=(",", ":")).encode()
    js += b" " * (-len(js) % 4)
    total = 12 + 8 + len(js) + 8 + len(binary)
    with open(path, "wb") as f:
        f.write(struct.pack("<III", 0x46546C67, 2, total))
        f.write(struct.pack("<II", len(js), 0x4E4F534A) + js)
        f.write(struct.pack("<II", len(binary), 0x004E4942) + binary)
    return total


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("out", help="convert_ce_map.sh output folder (scene.gltf, staging/)")
    ap.add_argument("code", help="the map's three-character codename")
    ap.add_argument("dest", help="folder for <CODE>.glb")
    ap.add_argument("--manifest", help="JSON of every preview, updated with this one")
    a = ap.parse_args()

    staging = os.path.join(a.out, "staging")
    g, buf = load_gltf(os.path.join(a.out, "scene.gltf"))
    materials = json.load(open(os.path.join(staging, "materials.json"), encoding="utf-8"))
    tex = Textures(os.path.join(staging, "textures"))

    pos, nrm, col, idx, base = [], [], [], [], 0
    for p in primitives(g, buf):
        pos.append(p["pos"])
        nrm.append(p["nrm"])
        col.append(vertex_colours(p, materials, tex))
        idx.append(p["idx"] + base)
        base += len(p["pos"])
    pos, nrm, col, idx = map(np.concatenate, (pos, nrm, col, idx))

    lo, hi = pos.min(axis=0), pos.max(axis=0)
    # glTF metres (x, y up, z) -> Unreal centimetres (x, z, y).
    bounds = {"min": [round(lo[0] * 100, 1), round(lo[2] * 100, 1), round(lo[1] * 100, 1)],
              "max": [round(hi[0] * 100, 1), round(hi[2] * 100, 1), round(hi[1] * 100, 1)]}
    code = a.code.upper()
    os.makedirs(a.dest, exist_ok=True)
    size = write_glb(os.path.join(a.dest, f"{code}.glb"), pos, nrm, col, idx, {"code": code, "unreal_bounds": bounds})
    tris = len(idx) // 3
    print(f"{code}: {tris} triangles, {len(pos)} vertices, {size / 1024:.0f} KiB -> {a.dest}")

    if a.manifest:
        m = json.load(open(a.manifest, encoding="utf-8")) if os.path.exists(a.manifest) else {}
        m[code] = {"bytes": size, "triangles": tris, "bounds": bounds}
        m = dict(sorted(m.items()))
        with open(a.manifest, "w", encoding="utf-8", newline="\n") as f:
            json.dump(m, f, indent=2)
            f.write("\n")


if __name__ == "__main__":
    main()
