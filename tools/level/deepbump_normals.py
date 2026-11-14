"""A bump map for a redrawn colour map, from DeepBump's colour-to-normals model.

    python tools/level/deepbump_normals.py <redrawn colour png> <source bump> <out.png>
        [--deepbump <DeepBump folder>] [--overlap LARGE] [--preview lit.png]
        [--seams <conversion folder> --material <shader token> [--seam-width 10]]

DeepBump (github.com/HugoTini/DeepBump, GPL-3.0; run as a tool here, not
shipped) guesses a tangent-space normal map from a colour map's
brightness. It is not in the repository: clone it anywhere and pass its
folder (or set DEEPBUMP); it needs `onnxruntime`.

The source bump map (Halo 2's) is not an input to the model. It is read
to put the result in the game's convention: DeepBump's green may point
the other way, and the sign that makes its y slopes agree with the
source's is kept. The output is the colour map's size, with the source's
alpha magnified. The agreement with the source's slopes is printed: a
guess from colour cannot know depth the colour does not show, so expect
it well under a redraw's.

`--seams`: a texture is often laid on its models in pieces, and a piece
mirrored (a crate face that is one quarter panel used four times) or cut
off from its neighbour on the sheet. Halo 2's bump map is flat or
continuous along those joins; DeepBump invents slopes at them, so the two
sides light differently and a line shows down the model. Every UV island
border and mirror fold of the named shader's triangles (from the
conversion's scene glTFs) is drawn on the sheet, and within `--seam-width`
texels of one the result fades back to the original bump, enlarged. The
islands' insides keep DeepBump's relief. The mask is written beside the
output (`<out>.seams.png`) to check.

`--broad <texels>` (default 12; 0 off): DeepBump also tilts whole panels
(a gradient of brightness reads as a slope), and a mirrored panel tilted
one way lights brighter on one side of the mirror than the other. Its
slopes broader than that many texels are replaced by the original's, as
redraw_bump.py does for an image model's redraw; the finer relief stays.
"""
import argparse
import os
import sys

import json

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import redraw_bump as rb  # noqa: E402


def seam_mask(conv, token, size, width):
    """A weight in [0, 1]: 1 on the UV island borders and mirror folds of
    the shader's triangles, fading out over `width` texels."""
    from refine_water_gltf import read_accessor
    w, h = size
    img = Image.new("L", (w, h), 0)
    draw = ImageDraw.Draw(img)
    tris = drawn = 0
    for scene in sorted(f for f in os.listdir(conv) if f.startswith("scene") and f.endswith(".gltf")):
        doc = json.load(open(os.path.join(conv, scene), encoding="utf-8"))
        if not doc.get("buffers"):
            continue
        data = open(os.path.join(conv, doc["buffers"][0]["uri"]), "rb").read()
        for mesh in doc.get("meshes") or []:
            for prim in mesh["primitives"]:
                name = doc["materials"][prim["material"]]["name"] if "material" in prim else ""
                if token not in name or "TEXCOORD_0" not in prim["attributes"] or "indices" not in prim:
                    continue
                pos = read_accessor(doc, data, prim["attributes"]["POSITION"]).astype(np.float64)
                uv = read_accessor(doc, data, prim["attributes"]["TEXCOORD_0"]).astype(np.float64)
                idx = read_accessor(doc, data, prim["indices"]).reshape(-1, 3)
                tris += len(idx)
                q = np.round(pos / max(float(np.ptp(pos, axis=0).max()), 1e-6) * 2e4).astype(np.int64)
                key = {i: tuple(q[i]) for i in np.unique(idx)}
                edges = {}
                for t in idx:
                    for k in range(3):
                        a, b, c = int(t[k]), int(t[(k + 1) % 3]), int(t[(k + 2) % 3])
                        ka, kb = key[a], key[b]
                        if ka > kb:
                            a, b, ka, kb = b, a, kb, ka
                        edges.setdefault((ka, kb), []).append((a, b, c))
                for group in edges.values():
                    inner = False
                    if len(group) == 2:
                        (a1, b1, c1), (a2, b2, c2) = group
                        same = np.allclose(uv[a1], uv[a2], atol=1e-4) and np.allclose(uv[b1], uv[b2], atol=1e-4)
                        if same:
                            d = uv[b1] - uv[a1]
                            side = lambda c: d[0] * (uv[c][1] - uv[a1][1]) - d[1] * (uv[c][0] - uv[a1][0])
                            inner = side(c1) * side(c2) < 0
                    if inner:
                        continue
                    for a, b, _ in group:
                        off = np.floor(np.minimum(uv[a], uv[b]))
                        pa, pb = (uv[a] - off) * (w, h), (uv[b] - off) * (w, h)
                        draw.line([tuple(pa), tuple(pb)], fill=255, width=max(2, width // 3))
                        drawn += 1
    soft = img.filter(ImageFilter.GaussianBlur(width / 2.0))
    m = np.asarray(soft).astype(np.float64) / 255.0
    return np.clip(m / max(float(m.max()), 1e-6) * 1.6, 0.0, 1.0), img, tris, drawn


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("colour")
    ap.add_argument("bump", help="the original bump map, for its convention and alpha")
    ap.add_argument("out")
    ap.add_argument("--deepbump", default=os.environ.get("DEEPBUMP"), help="the cloned DeepBump folder")
    ap.add_argument("--overlap", choices=("SMALL", "MEDIUM", "LARGE"), default="LARGE")
    ap.add_argument("--preview")
    ap.add_argument("--seams", help="the conversion folder whose scene glTFs hold the models using this texture")
    ap.add_argument("--material", help="with --seams: a token of the shader's name")
    ap.add_argument("--seam-width", type=int, default=10, help="texels over which a seam fades to the original")
    ap.add_argument("--broad", type=float, default=12.0,
                    help="DeepBump's slopes broader than this (texels) are replaced by the original's; 0 keeps them")
    a = ap.parse_args()
    if not a.deepbump or not os.path.isfile(os.path.join(a.deepbump, "deepbump256.onnx")):
        sys.exit("pass --deepbump <folder> (or set DEEPBUMP) to a clone of github.com/HugoTini/DeepBump")
    sys.path.insert(0, a.deepbump)
    import module_color_to_normals  # noqa: E402

    col = Image.open(a.colour).convert("RGB")
    w, h = col.size
    img = np.transpose(np.asarray(col).astype(np.float64) / 255.0, (2, 0, 1))
    out = np.transpose(module_color_to_normals.apply(img, a.overlap, None), (1, 2, 0))
    rgb = np.clip(out * 255.0 + 0.5, 0, 255).astype(np.uint8)
    src = Image.open(a.bump).convert("RGBA")
    p0, q0 = rb.slopes(rb.decode(src.resize((w, h), Image.BICUBIC)))
    p, q = rb.slopes(rb.decode(Image.fromarray(rgb)))
    ay = float(np.corrcoef(q0.ravel(), q.ravel())[0, 1])
    flipped = ay < 0
    if flipped:
        rgb[..., 1] = 255 - rgb[..., 1]
        q, ay = -q, -ay
    ax = float(np.corrcoef(p0.ravel(), p.ravel())[0, 1])
    broad = ""
    if a.broad > 0:
        p0, q0 = rb.slopes(rb.decode(src.resize((w, h), Image.BICUBIC)))
        pm, qm = rb.slopes(rb.decode(Image.fromarray(rgb)))
        n = rb.normal(pm + rb.blur(p0 - pm, a.broad), qm + rb.blur(q0 - qm, a.broad))
        rgb = np.clip((n + 1.0) * 127.5 + 0.5, 0, 255).astype(np.uint8)
        broad = f"; slopes broader than {a.broad:g} texels from the original"
    seams = ""
    if a.seams:
        if not a.material:
            sys.exit("--seams needs --material")
        wt, lines, tris, drawn = seam_mask(a.seams, a.material, (w, h), a.seam_width)
        n0 = rb.decode(src.resize((w, h), Image.BICUBIC))
        n1 = rb.decode(Image.fromarray(rgb))
        n = n1 * (1.0 - wt[..., None]) + n0 * wt[..., None]
        n /= np.linalg.norm(n, axis=2, keepdims=True)
        rgb = np.clip((n + 1.0) * 127.5 + 0.5, 0, 255).astype(np.uint8)
        Image.fromarray((wt * 255).astype(np.uint8)).save(os.path.splitext(a.out)[0] + ".seams.png")
        seams = f"; {drawn} seam edge(s) of {tris} triangle(s), {float((wt > 0.5).mean()) * 100:.1f}% of the sheet faded"
    alpha = np.asarray(src.getchannel("A").resize((w, h), Image.BICUBIC))
    Image.fromarray(np.dstack([rgb, alpha]), "RGBA").save(a.out)
    if a.preview:
        green = min((1.0, -1.0), key=lambda g: rb.curl(*rb.slopes(rb.decode(src)), g))
        c = np.asarray(col).astype(np.float64)
        n0, n1 = rb.decode(src.resize((w, h), Image.BICUBIC)), rb.decode(Image.fromarray(rgb))
        Image.fromarray(np.hstack([rb.lit(c, n0, green), rb.lit(c, n1, green)])).save(a.preview)
    print(f"{w}x{h}; green {'flipped to' if flipped else 'already in'} the source's convention; "
          f"agrees with the source's slopes {ax:.2f} (x) and {ay:.2f} (y); "
          f"mean slope {np.abs(rb.decode(src)[..., :2]).mean():.3f} -> {np.abs(rb.decode(Image.fromarray(rgb))[..., :2]).mean():.3f}"
          + broad + seams)


if __name__ == "__main__":
    main()
