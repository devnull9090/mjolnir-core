"""Draw MJOLNIR's original game type glyphs, ready for a cyan or white tint.

    python tools/ue/draw_gametype_icons.py [--sheet out/gametype-icons.png]

Writes six 256px transparent PNGs to Art/GameTypeIcons. The UI builder imports
them as T_MJMode_<Name> into /Game/MJOLNIR/UI/ModeIcons. These are original
geometric symbols in the same style as draw_hud_icons.py; no game art is copied.
"""
from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ICON = 256
SCALE = 8
SIZE = ICON * SCALE
OUT = Path(__file__).resolve().parents[2] / "unreal/MJOLNIRMaterials/Art/GameTypeIcons"


def points(coords):
    return [(round(x * SIZE), round(y * SIZE)) for x, y in coords]


def poly(draw, coords, fill=255):
    draw.polygon(points(coords), fill=fill)


def circle(draw, x, y, radius, fill=255):
    draw.ellipse(points(((x - radius, y - radius), (x + radius, y + radius))), fill=fill)


def ring(draw, x, y, radius, width):
    circle(draw, x, y, radius)
    circle(draw, x, y, radius - width, 0)


def line(draw, start, end, width, fill=255):
    draw.line(points((start, end)), fill=fill, width=round(width * SIZE))


def skull(draw, cx=0.5, cy=0.47, scale=1.0):
    """An angular skull, with a single strong silhouette at row-icon size."""
    def shape(coords, fill=255):
        poly(draw, [(cx + x * scale, cy + y * scale) for x, y in coords], fill)

    shape([(-.23, -.30), (.23, -.30), (.34, -.18), (.34, .08), (.23, .18),
           (.19, .35), (-.19, .35), (-.23, .18), (-.34, .08), (-.34, -.18)])
    shape([(-.25, -.08), (-.07, -.03), (-.08, .09), (-.22, .07)], 0)
    shape([(.25, -.08), (.07, -.03), (.08, .09), (.22, .07)], 0)
    shape([(0, .09), (-.055, .19), (.055, .19)], 0)
    for x in (-.105, 0, .105):
        shape([(x-.018, .255), (x+.018, .255), (x+.018, .36), (x-.018, .36)], 0)


def slayer(draw):
    """A combat reticle with a skull inside it."""
    ring(draw, .5, .5, .34, .045)
    # Interrupt the circle along the four targeting marks.
    for a, b in (((.5, .06), (.5, .27)), ((.5, .73), (.5, .94)),
                 ((.06, .5), (.27, .5)), ((.73, .5), (.94, .5))):
        line(draw, a, b, .095, 0)
        line(draw, a, b, .045)
    skull(draw, .5, .49, .56)


def helmet(draw, cx, cy, scale=1.0, fill=255):
    def shape(coords, color=fill):
        poly(draw, [(cx + x * scale, cy + y * scale) for x, y in coords], color)

    shape([(-.16, -.24), (.16, -.24), (.24, -.14), (.26, .08), (.17, .23),
           (.08, .28), (-.08, .28), (-.17, .23), (-.26, .08), (-.24, -.14)])
    shape([(-.20, -.06), (-.12, -.10), (.12, -.10), (.20, -.06),
           (.15, .05), (.07, .08), (-.07, .08), (-.15, .05)], 0)
    shape([(-.065, .17), (.065, .17), (.08, .285), (-.08, .285)], 0)


def team_slayer(draw):
    """Two armored combatants, the rear silhouette set off by a clear gap."""
    helmet(draw, .66, .37, .88)
    # Black backing preserves separation between the two helmets.
    helmet(draw, .37, .57, 1.17, 0)
    helmet(draw, .37, .57, 1.0)
    # Team stripes keep the pair distinct from a single Spartan portrait.
    poly(draw, [(.65, .74), (.86, .62), (.86, .70), (.65, .82)])
    poly(draw, [(.65, .86), (.86, .74), (.86, .82), (.65, .94)])


def ctf(draw):
    """A planted banner with a cut-out chevron and a sturdy pedestal."""
    line(draw, (.22, .13), (.22, .86), .055)
    circle(draw, .22, .11, .035)
    poly(draw, [(.28, .15), (.54, .15), (.63, .21), (.85, .21),
                (.77, .37), (.85, .53), (.60, .53), (.51, .47), (.28, .47)])
    poly(draw, [(.39, .24), (.48, .31), (.39, .38), (.45, .31)], 0)
    poly(draw, [(.11, .88), (.33, .88), (.38, .94), (.06, .94)])


def oddball(draw):
    """The objective skull, framed by short carrying brackets."""
    skull(draw)
    for left in (True, False):
        x = .08 if left else .92
        inward = .08 if left else -.08
        line(draw, (x, .59), (x, .77), .04)
        line(draw, (x, .77), (x + inward, .77), .04)


def koth(draw):
    """A crown above a stepped hill; the diamond is the control point."""
    poly(draw, [(.18, .23), (.35, .35), (.50, .13), (.65, .35), (.82, .23),
                (.74, .57), (.26, .57)])
    poly(draw, [(.50, .34), (.55, .40), (.50, .46), (.45, .40)], 0)
    poly(draw, [(.28, .62), (.72, .62), (.78, .69), (.22, .69)])
    poly(draw, [(.22, .74), (.78, .74), (.84, .81), (.16, .81)])
    poly(draw, [(.16, .86), (.84, .86), (.90, .93), (.10, .93)])


def forge(draw):
    """A Monitor: segmented circular shell, open eye, and side fins."""
    ring(draw, .5, .5, .32, .055)
    line(draw, (.5, .15), (.5, .27), .07, 0)
    line(draw, (.5, .73), (.5, .85), .07, 0)
    ring(draw, .5, .5, .19, .042)
    circle(draw, .5, .5, .085)
    poly(draw, [(.04, .38), (.12, .42), (.12, .58), (.04, .62)])
    poly(draw, [(.96, .38), (.88, .42), (.88, .58), (.96, .62)])
    poly(draw, [(.43, .08), (.57, .08), (.55, .14), (.45, .14)])
    poly(draw, [(.45, .86), (.55, .86), (.57, .92), (.43, .92)])


GLYPHS = {"Slayer": slayer, "TeamSlayer": team_slayer, "Ctf": ctf,
          "Oddball": oddball, "Koth": koth, "Forge": forge}


def render(fn):
    mask = Image.new("L", (SIZE, SIZE), 0)
    fn(ImageDraw.Draw(mask))
    mask = mask.resize((ICON, ICON), Image.Resampling.LANCZOS)
    result = Image.new("RGBA", (ICON, ICON), (255, 255, 255, 0))
    result.putalpha(mask)
    return result


def preview(images, path):
    sheet = Image.new("RGBA", (6 * 292, 380), (9, 24, 34, 255))
    draw = ImageDraw.Draw(sheet)
    try:
        font = ImageFont.truetype("C:/Windows/Fonts/arial.ttf", 20)
    except OSError:
        font = ImageFont.load_default(size=20)
    for i, (name, icon) in enumerate(images.items()):
        tinted = Image.new("RGBA", icon.size, (163, 217, 236, 255))
        tinted.putalpha(icon.getchannel("A"))
        x = i * 292
        sheet.alpha_composite(tinted, (x + 18, 10))
        sheet.alpha_composite(tinted.resize((56, 56), Image.Resampling.LANCZOS), (x + 118, 275))
        draw.text((x + 146, 348), name.upper(), font=font, fill=(225, 242, 249), anchor="mm")
    path.parent.mkdir(parents=True, exist_ok=True)
    sheet.convert("RGB").save(path)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--sheet", type=Path)
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    images = {name: render(fn) for name, fn in GLYPHS.items()}
    for name, icon in images.items():
        icon.save(OUT / (name + ".png"))
    print(f"{len(images)} game type icons -> {OUT}")
    if args.sheet:
        preview(images, args.sheet)


if __name__ == "__main__":
    main()
