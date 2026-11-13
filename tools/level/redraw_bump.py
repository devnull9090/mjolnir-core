"""Finish a redrawn bump map so it is a normal map a game can light with.

    python tools/level/redraw_texture.py <source bump> <model.png> --normal-map --what "..."
    python tools/level/redraw_bump.py <source bump> <model.png> <out.png>
        [--colour <redrawn colour png>] [--detail 0.3] [--preview lit.png]

A redrawn colour map at four times the size sits on the original's bump
map, a quarter as sharp. Two things were tried first and dropped:
guessing the relief from the colour alone throws away what the artists
built (the rim, the bolts, the tread's real depth), and enlarging the
original's own height with a filter gives soft, lumpy bevels. What works
is asking the image model to redraw the normal map itself
(`redraw_texture.py --normal-map`): it keeps the layout and the way every
slope faces, and draws the bevels clean.

Its picture is still a picture. This makes it a normal map again:

1. Decoded and brought to unit length; the source's alpha is kept.
2. Its broad slopes are set to the source's (the difference, blurred over
   a few source texels, is taken out), so a face the model tinted or
   tilted reads as Halo 2 had it, and only the fine shapes are the
   model's. The whole is scaled to the source's mean slope.
3. With `--colour`, the redrawn colour map's fine grain is added as
   relief (`--detail`, in texels of height): scuffs, cast texture, mud.
   Which way green points is read from the source: the right sign gives
   a gradient field with less curl.

`--preview` writes the colour map (or grey) lit from the upper left with
the source bump (left) and the finished one (right). The output reports
how far the model's slopes agreed with the source's; under about 0.6 it
has redrawn something else, and the result should not be used.
"""
import argparse

import numpy as np
from PIL import Image


def blur(a, sigma):
    """Gaussian, wrapping: the textures tile."""
    h, w = a.shape
    fy, fx = np.fft.fftfreq(h)[:, None], np.fft.fftfreq(w)[None, :]
    return np.real(np.fft.ifft2(np.fft.fft2(a) * np.exp(-2 * (np.pi * sigma) ** 2 * (fx ** 2 + fy ** 2))))


def decode(img):
    n = np.asarray(img.convert("RGB")).astype(np.float64) / 127.5 - 1.0
    n[..., 2] = np.maximum(n[..., 2], 0.05)
    return n / np.linalg.norm(n, axis=2, keepdims=True)


def slopes(n):
    """A normal as the surface's slopes (x, and y as the map stores it)."""
    return -n[..., 0] / n[..., 2], -n[..., 1] / n[..., 2]


def normal(p, q):
    n = np.dstack([-p, -q, np.ones_like(p)])
    return n / np.linalg.norm(n, axis=2, keepdims=True)


def curl(p, q, green):
    return float(np.abs((np.roll(p, -1, 0) - p) - green * (np.roll(q, -1, 1) - q)).mean())


def lit(colour, n, green):
    light = np.array([-0.45, -0.45 * green, 0.77])
    shade = np.clip((n * light).sum(axis=2), 0.0, 1.4) / light[2]
    return np.clip(colour * shade[..., None], 0, 255).astype(np.uint8)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("bump", help="the original bump map")
    ap.add_argument("model", help="the image model's redraw of it")
    ap.add_argument("out")
    ap.add_argument("--colour", help="the redrawn colour map, for its grain and the preview")
    ap.add_argument("--detail", type=float, default=0.3, help="the colour map's grain, in texels of height")
    ap.add_argument("--preview")
    a = ap.parse_args()

    src = Image.open(a.bump).convert("RGBA")
    model = Image.open(a.model).convert("RGB")
    w, h = model.size
    scale = w / src.size[0]
    n0 = decode(src.resize((w, h), Image.BICUBIC))
    p0, q0 = slopes(n0)
    pm, qm = slopes(decode(model))
    agree = [float(np.corrcoef(x.ravel(), y.ravel())[0, 1]) for x, y in ((p0, pm), (q0, qm))]
    sigma = scale * 3.0
    p = pm + blur(p0 - pm, sigma)
    q = qm + blur(q0 - qm, sigma)
    k = float(np.clip((np.abs(p0).mean() + np.abs(q0).mean()) / max(np.abs(p).mean() + np.abs(q).mean(), 1e-6),
                      0.6, 1.6))
    p, q = p * k, q * k
    low = decode(src)
    green = min((1.0, -1.0), key=lambda g: curl(*slopes(low), g))
    colour = None
    if a.colour:
        col = Image.open(a.colour).convert("RGB").resize((w, h), Image.LANCZOS)
        colour = np.asarray(col).astype(np.float64)
        lum = np.asarray(col.convert("L")).astype(np.float64) / 255.0
        grain = (lum - blur(lum, 2.0)) * a.detail * 4.0
        p = p + (np.roll(grain, -1, 1) - np.roll(grain, 1, 1)) / 2.0
        q = q + green * (np.roll(grain, -1, 0) - np.roll(grain, 1, 0)) / 2.0
    out = normal(p, q)
    rgba = np.dstack([np.clip((out + 1.0) * 127.5 + 0.5, 0, 255).astype(np.uint8),
                      np.asarray(src.getchannel("A").resize((w, h), Image.BICUBIC))])
    Image.fromarray(rgba, "RGBA").save(a.out)
    if a.preview:
        c = colour if colour is not None else np.full((h, w, 3), 150.0)
        Image.fromarray(np.hstack([lit(c, n0, green), lit(c, out, green)])).save(a.preview)
    print(f"{src.size[0]}x{src.size[1]} -> {w}x{h}; the model's slopes agree with the source's "
          f"{agree[0]:.2f} (x) and {agree[1]:.2f} (y); scaled {k:.2f}; green {'up' if green > 0 else 'down'}"
          + ("" if min(agree) >= 0.6 else "  ** too far from the source: do not use **"))


if __name__ == "__main__":
    main()
