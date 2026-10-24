"""Draw MJOLNIR's own HUD glyphs: white silhouettes with a soft dark edge,
for the kill feed's modifiers (headshot, melee, splatter ...), its event
lines (joined, left, kicked ...) and its medal lines.

    python tools/ue/draw_hud_icons.py [--sheet preview.png]

Writes unreal/MJOLNIRMaterials/Art/HudIcons/<name>.png (ICON x ICON, RGBA).
Scripts/build_mjolnir_ui.py imports them as T_MJHud_<Name> into
/Game/MJOLNIR/UI/Icons, cooked into chunk 984 with the widgets. MJOLNIRHud
tints them (SetColorAndOpacity), so they are drawn white.

Weapon silhouettes are not drawn here: the HUD shows the game's own
(ui/Hud/WeaponCradle), through the game's own icon material, at runtime.

Each glyph is drawn at SS times the size on a 0..1 square and scaled down,
which antialiases every edge.
"""
import argparse
import math
import os

from PIL import Image, ImageChops, ImageDraw, ImageFilter

ICON = 96
SS = 8
S = ICON * SS
OUT = os.path.join(os.path.dirname(__file__), "..", "..", "unreal", "MJOLNIRMaterials", "Art", "HudIcons")

WHITE = 255


def px(v):
    return v * S


def pts(points):
    return [(px(x), px(y)) for x, y in points]


def canvas():
    return Image.new("L", (S, S), 0)


def circle(d, cx, cy, r, fill=WHITE):
    d.ellipse([px(cx - r), px(cy - r), px(cx + r), px(cy + r)], fill=fill)


def ring(d, cx, cy, r, w, fill=WHITE):
    d.ellipse([px(cx - r), px(cy - r), px(cx + r), px(cy + r)], outline=fill, width=int(px(w)))


def rrect(d, x0, y0, x1, y1, r, fill=WHITE):
    d.rounded_rectangle([px(x0), px(y0), px(x1), px(y1)], radius=px(r), fill=fill)


def line(d, a, b, w, fill=WHITE):
    d.line(pts([a, b]), fill=fill, width=int(px(w)))
    # Round caps.
    for x, y in (a, b):
        circle(d, x, y, w / 2, fill)


def poly(d, points, fill=WHITE):
    d.polygon(pts(points), fill=fill)


# --- glyphs ------------------------------------------------------------------


def headshot(d):
    """A reticle: ring, four ticks, a centre dot."""
    ring(d, 0.5, 0.5, 0.30, 0.085)
    for (ax, ay), (bx, by) in (((0.5, 0.04), (0.5, 0.26)), ((0.5, 0.74), (0.5, 0.96)),
                               ((0.04, 0.5), (0.26, 0.5)), ((0.74, 0.5), (0.96, 0.5))):
        line(d, (ax, ay), (bx, by), 0.085)
    circle(d, 0.5, 0.5, 0.085)


def melee(d):
    """A fist from the front: four curled fingers over the thumb, the wrist
    below."""
    for i, x in enumerate((0.15, 0.335, 0.52, 0.705)):
        top = 0.14 if i in (1, 2) else 0.19
        rrect(d, x, top, x + 0.165, 0.56, 0.08)
    rrect(d, 0.15, 0.36, 0.87, 0.80, 0.12)
    # The thumb folded across, set off by a gap.
    rrect(d, 0.10, 0.47, 0.66, 0.66, 0.095, fill=0)
    rrect(d, 0.13, 0.50, 0.63, 0.63, 0.065)
    rrect(d, 0.30, 0.78, 0.74, 0.96, 0.04)


def assassination(d):
    """A combat knife, point up and to the right."""
    blade = [(0.30, 0.70), (0.80, 0.12), (0.90, 0.10), (0.88, 0.20), (0.40, 0.78)]
    poly(d, blade)
    # Guard and grip.
    line(d, (0.20, 0.58), (0.44, 0.84), 0.09)
    line(d, (0.31, 0.73), (0.12, 0.92), 0.12)


def burst(d, cx=0.5, cy=0.5, outer=0.47, inner=0.22, points=8, twist=0.0):
    star = []
    for i in range(points * 2):
        a = math.pi * i / points + twist
        r = outer if i % 2 == 0 else inner
        star.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    poly(d, star)


def explosion(d):
    burst(d, outer=0.48, inner=0.24, points=9, twist=-math.pi / 2)
    circle(d, 0.5, 0.5, 0.15, fill=0)


def splatter(d):
    """A splat: a blob with droplets thrown out."""
    burst(d, outer=0.34, inner=0.24, points=7, twist=0.3)
    circle(d, 0.5, 0.5, 0.25)
    for x, y, r in ((0.14, 0.22, 0.06), (0.86, 0.30, 0.055), (0.83, 0.82, 0.07), (0.20, 0.84, 0.05),
                    (0.50, 0.07, 0.045)):
        circle(d, x, y, r)


def stuck(d):
    """An asterisk with a hot centre: a stuck grenade."""
    for i in range(3):
        a = math.pi * i / 3 + math.pi / 2
        dx, dy = 0.38 * math.cos(a), 0.38 * math.sin(a)
        line(d, (0.5 - dx, 0.5 - dy), (0.5 + dx, 0.5 + dy), 0.12)
    circle(d, 0.5, 0.5, 0.17)


def fall(d):
    """An arrow down onto the ground."""
    line(d, (0.5, 0.08), (0.5, 0.56), 0.13)
    poly(d, [(0.24, 0.48), (0.76, 0.48), (0.5, 0.78)])
    line(d, (0.14, 0.90), (0.86, 0.90), 0.08)


def guardians(d):
    """A lightning bolt."""
    poly(d, [(0.58, 0.04), (0.20, 0.56), (0.47, 0.56), (0.38, 0.96), (0.80, 0.40), (0.53, 0.40), (0.66, 0.04)])


def skull(d):
    """A skull, for deaths and suicides."""
    circle(d, 0.5, 0.42, 0.34)
    rrect(d, 0.30, 0.52, 0.70, 0.86, 0.06)
    # Eyes and nose.
    circle(d, 0.37, 0.47, 0.095, fill=0)
    circle(d, 0.63, 0.47, 0.095, fill=0)
    poly(d, [(0.5, 0.57), (0.45, 0.67), (0.55, 0.67)], fill=0)
    # Teeth.
    for x in (0.40, 0.5, 0.60):
        line(d, (x, 0.76), (x, 0.88), 0.035, fill=0)


def person(d, cx=0.40):
    circle(d, cx, 0.30, 0.17)
    d.chord([px(cx - 0.33), px(0.52), px(cx + 0.33), px(1.18)], 180, 360, fill=WHITE)


def joined(d):
    person(d)
    line(d, (0.80, 0.30), (0.80, 0.62), 0.10)
    line(d, (0.64, 0.46), (0.96, 0.46), 0.10)


def left(d):
    person(d, 0.36)
    poly(d, [(0.66, 0.30), (0.98, 0.50), (0.66, 0.70)])
    line(d, (0.56, 0.50), (0.74, 0.50), 0.12)


def kicked(d):
    person(d)
    line(d, (0.68, 0.32), (0.94, 0.58), 0.10)
    line(d, (0.94, 0.32), (0.68, 0.58), 0.10)


def flag(d):
    line(d, (0.22, 0.08), (0.22, 0.94), 0.08)
    poly(d, [(0.22, 0.10), (0.86, 0.26), (0.22, 0.54)])


def medal(d):
    """Three chevrons: a multi-kill or a spree."""
    for y in (0.14, 0.40, 0.66):
        poly(d, [(0.12, y), (0.5, y + 0.16), (0.88, y), (0.88, y + 0.16), (0.5, y + 0.32), (0.12, y + 0.16)])


def spree(d):
    """A flame."""
    poly(d, [(0.50, 0.04), (0.66, 0.30), (0.62, 0.42), (0.74, 0.34), (0.84, 0.62), (0.72, 0.86),
             (0.50, 0.96), (0.28, 0.86), (0.16, 0.62), (0.26, 0.38), (0.36, 0.48), (0.38, 0.28)])
    poly(d, [(0.50, 0.50), (0.60, 0.70), (0.56, 0.86), (0.44, 0.86), (0.40, 0.70)], fill=0)


def firstblood(d):
    """A drop."""
    poly(d, [(0.5, 0.06), (0.74, 0.50), (0.26, 0.50)])
    circle(d, 0.5, 0.62, 0.26)


def telefrag(d):
    """Two rings overlapping: a teleporter landing on someone."""
    ring(d, 0.38, 0.5, 0.25, 0.09)
    ring(d, 0.62, 0.5, 0.25, 0.09)


def forge_reticle(d):
    """Forge's cursor: a thin ring, four ticks outside it and a centre dot.
    MJOLNIRForge tints it per state (idle, on an object, holding one)."""
    ring(d, 0.5, 0.5, 0.27, 0.035)
    for a, b in (((0.5, 0.06), (0.5, 0.17)), ((0.5, 0.83), (0.5, 0.94)),
                 ((0.06, 0.5), (0.17, 0.5)), ((0.83, 0.5), (0.94, 0.5))):
        line(d, a, b, 0.045)
    circle(d, 0.5, 0.5, 0.035)


def forge_mark(d):
    """The Forge badge: the Monitor, an eye in a ring with a fin either side."""
    ring(d, 0.5, 0.5, 0.27, 0.07)
    circle(d, 0.5, 0.5, 0.11)
    poly(d, [(0.05, 0.40), (0.19, 0.44), (0.19, 0.56), (0.05, 0.60)])
    poly(d, [(0.95, 0.40), (0.81, 0.44), (0.81, 0.56), (0.95, 0.60)])


# Forge's own glyphs: written to Art/ForgeIcons and imported as T_MJForge_<Name>
# into /Game/MJOLNIR/ForgeUI/Icons, cooked with WBP_MJOLNIRForge (chunk 980).
FORGE_GLYPHS = {"Reticle": forge_reticle, "Mark": forge_mark}
FORGE_OUT = os.path.join(os.path.dirname(OUT), "ForgeIcons")

GLYPHS = {
    "Headshot": headshot, "Melee": melee, "Assassination": assassination, "Explosion": explosion,
    "Splatter": splatter, "Stuck": stuck, "Fall": fall, "Guardians": guardians, "Skull": skull,
    "Joined": joined, "Left": left, "Kicked": kicked, "Flag": flag, "Medal": medal, "Spree": spree,
    "FirstBlood": firstblood, "Telefrag": telefrag,
}


def render(fn):
    mask = canvas()
    fn(ImageDraw.Draw(mask))
    mask = mask.resize((ICON, ICON), Image.LANCZOS)
    # A soft dark edge keeps the glyph legible over snow and sky alike.
    edge = mask.filter(ImageFilter.MaxFilter(5)).filter(ImageFilter.GaussianBlur(1.2))
    edge = edge.point(lambda v: int(v * 0.85))
    rgb = Image.merge("RGB", [mask, mask, mask])
    alpha = ImageChops.lighter(mask, edge)
    out = Image.merge("RGBA", (*rgb.split(), alpha))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sheet", help="also write a preview sheet over grey and sky blue")
    args = ap.parse_args()
    os.makedirs(OUT, exist_ok=True)
    images = {}
    for name, fn in GLYPHS.items():
        images[name] = render(fn)
        images[name].save(os.path.join(OUT, name + ".png"))
    print(f"{len(images)} icons -> {os.path.normpath(OUT)}")
    os.makedirs(FORGE_OUT, exist_ok=True)
    for name, fn in FORGE_GLYPHS.items():
        images["Forge" + name] = render(fn)
        images["Forge" + name].save(os.path.join(FORGE_OUT, name + ".png"))
    print(f"{len(FORGE_GLYPHS)} Forge icons -> {os.path.normpath(FORGE_OUT)}")
    if args.sheet:
        cols = 9
        rows = math.ceil(len(images) / cols)
        cell = ICON + 16
        sheet = Image.new("RGBA", (cols * cell, rows * cell * 2), (0, 0, 0, 255))
        for band, bg in enumerate(((40, 52, 64, 255), (150, 190, 220, 255))):
            sheet.paste(Image.new("RGBA", (cols * cell, rows * cell), bg), (0, band * rows * cell))
            for i, img in enumerate(images.values()):
                x, y = (i % cols) * cell + 8, (i // cols) * cell + 8 + band * rows * cell
                sheet.alpha_composite(img, (x, y))
        sheet.save(args.sheet)


if __name__ == "__main__":
    main()
