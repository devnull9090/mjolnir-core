"""Put a redrawn two-colour stencil back on its source's palette.

    python tools/level/redraw_palette.py <source.png> <redraw.png> <out.png>

A stencil drawn as a 2x multiply (Halo 2's crate `overlay`: M_CE_PropOverlay)
must keep its background exactly the source's grey, or the whole face of the
prop darkens or tints. redraw_texture.py's redraws come back crisp but in
their own colours: Zanzibar's crate labels came back on grey 110 drifting
104-112 with a stronger yellow (2026-11-15). Here each pixel is projected
onto the redraw's background-to-paint line and rebuilt from the source's own
background and paint, so the background is flat and exact, the paint the
source's colour, and the edges between keep the redraw's antialiasing.

The background is the median of the near-grey pixels, the paint the median
of the strongly warm ones (red well above blue): yellow or orange paint on
grey, as Halo 2's military stencils are.
"""
import sys

import numpy as np
from PIL import Image


def colours(a):
    """(background, paint) of a stencil image."""
    flat = a.reshape(-1, 3).astype(float)
    grey = flat[(flat.max(1) - flat.min(1)) < 12]
    paint = flat[(flat[:, 0] - flat[:, 2]) > 120]
    if not len(grey) or not len(paint):
        sys.exit("not a stencil of warm paint on grey")
    return np.median(grey, 0), np.median(paint, 0)


def main():
    if len(sys.argv) != 4:
        sys.exit(__doc__.strip().splitlines()[2].strip())
    src, red, out = sys.argv[1:4]
    s = np.asarray(Image.open(src).convert("RGB"))
    r = np.asarray(Image.open(red).convert("RGB")).astype(float)
    s_bg, s_paint = colours(s)
    r_bg, r_paint = colours(r)
    d = r_paint - r_bg
    t = np.clip(((r - r_bg) @ d) / (d @ d), 0.0, 1.0)[..., None]
    o = s_bg + t * (s_paint - s_bg)
    Image.fromarray(np.clip(np.round(o), 0, 255).astype(np.uint8)).convert("RGBA").save(out)
    print(f"{out}: background {r_bg.round()} -> {s_bg.round()}, paint {r_paint.round()} -> {s_paint.round()}")


if __name__ == "__main__":
    main()
