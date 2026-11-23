"""Draw the Pelican Warfare zone badges: a flat-topped hexagon's outline and
its fill, white on transparent, for the stacked zone bars in the top left.

    python tools/ue/draw_zone_badges.py

Writes unreal/MJOLNIRMaterials/Art/WarfareZones/{HexRim,HexFill}.png (SIZE x
SIZE, RGBA). Scripts/build_pwr_warfare_zones.py imports them as
T_PWR_Zone<Name> beside the widget in chunk 958; MJOLNIRHud tints them per
owner through each Border's brush colour, so they are drawn white.

Drawn at SS times the size and scaled down, which antialiases every edge.
"""
import math
import os

from PIL import Image, ImageDraw

SIZE = 128
SS = 8
RIM = 0.1   # outline width, as a fraction of SIZE
INSET = 0.04  # room at the edge for the antialiased outline
OUT = os.path.join(os.path.dirname(__file__), "..", "..", "unreal", "MJOLNIRMaterials", "Art", "WarfareZones")


def hexagon(scale, inset):
    """A pointy-sided (flat-topped) hexagon filling the square, inset by `inset`."""
    c = scale / 2
    r = c - inset * scale
    return [(c + r * math.cos(math.radians(60 * k)), c + r * math.sin(math.radians(60 * k))) for k in range(6)]


def draw(name, rim):
    big = SIZE * SS
    image = Image.new("L", (big, big), 0)
    pen = ImageDraw.Draw(image)
    pen.polygon(hexagon(big, INSET), fill=255)
    if rim:
        pen.polygon(hexagon(big, INSET + RIM), fill=0)
    alpha = image.resize((SIZE, SIZE), Image.LANCZOS)
    out = Image.new("RGBA", (SIZE, SIZE), (255, 255, 255, 0))
    out.putalpha(alpha)
    path = os.path.join(OUT, name + ".png")
    out.save(path)
    print(path)


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    draw("HexRim", True)
    draw("HexFill", False)
