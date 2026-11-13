"""A bump map for a redrawn colour map, from DeepBump's colour-to-normals model.

    python tools/level/deepbump_normals.py <redrawn colour png> <source bump> <out.png>
        [--deepbump <DeepBump folder>] [--overlap LARGE] [--preview lit.png]

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
"""
import argparse
import os
import sys

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import redraw_bump as rb  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("colour")
    ap.add_argument("bump", help="the original bump map, for its convention and alpha")
    ap.add_argument("out")
    ap.add_argument("--deepbump", default=os.environ.get("DEEPBUMP"), help="the cloned DeepBump folder")
    ap.add_argument("--overlap", choices=("SMALL", "MEDIUM", "LARGE"), default="LARGE")
    ap.add_argument("--preview")
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
    alpha = np.asarray(src.getchannel("A").resize((w, h), Image.BICUBIC))
    Image.fromarray(np.dstack([rgb, alpha]), "RGBA").save(a.out)
    if a.preview:
        green = min((1.0, -1.0), key=lambda g: rb.curl(*rb.slopes(rb.decode(src)), g))
        c = np.asarray(col).astype(np.float64)
        n0, n1 = rb.decode(src.resize((w, h), Image.BICUBIC)), rb.decode(Image.fromarray(rgb))
        Image.fromarray(np.hstack([rb.lit(c, n0, green), rb.lit(c, n1, green)])).save(a.preview)
    print(f"{w}x{h}; green {'flipped to' if flipped else 'already in'} the source's convention; "
          f"agrees with the source's slopes {ax:.2f} (x) and {ay:.2f} (y); "
          f"mean slope {np.abs(rb.decode(src)[..., :2]).mean():.3f} -> {np.abs(rb.decode(Image.fromarray(rgb))[..., :2]).mean():.3f}")


if __name__ == "__main__":
    main()
