"""Draw MJOLNIR's UNSC Halo-style UI chrome textures (9-slice glass panels,
twin-pip glowing buttons, fading header rules, concentric medallion rings,
and native-style bottom hotkey bar chrome).

    python tools/ue/draw_ui_chrome.py [--sheet out/ui-chrome.png]

Writes transparent PNGs to unreal/MJOLNIRMaterials/Art/UIChrome/. The UI
builder (Scripts/build_mjolnir_ui.py) imports them as T_MJChrome_<Name> into
/Game/MJOLNIR/UI/Chrome and cooks them in chunk 984 alongside the screens.
All textures are procedurally drawn original art; no game art is copied.
"""
from __future__ import annotations

import argparse
import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

OUT = Path(__file__).resolve().parents[2] / "unreal/MJOLNIRMaterials/Art/UIChrome"

# Palette tuned to match Halo Campaign Evolved's native menu language
CYAN_BRIGHT = (138, 228, 255)
CYAN_MID = (92, 194, 236)
CYAN_DIM = (58, 134, 174)
GOLD_BRIGHT = (255, 224, 132)
GOLD_MID = (242, 188, 72)
NAVY_TOP = (7, 23, 36)
NAVY_BOT = (4, 13, 22)


def draw_vertical_gradient(img: Image.Image, top_rgba: tuple, bot_rgba: tuple, box: tuple | None = None):
    w, h = img.size
    x0, y0, x1, y1 = box if box else (0, 0, w, h)
    span = max(1, y1 - y0 - 1)
    px = img.load()
    for y in range(y0, y1):
        t = (y - y0) / span
        r = int(top_rgba[0] + (bot_rgba[0] - top_rgba[0]) * t)
        g = int(top_rgba[1] + (bot_rgba[1] - top_rgba[1]) * t)
        b = int(top_rgba[2] + (bot_rgba[2] - top_rgba[2]) * t)
        a = int(top_rgba[3] + (bot_rgba[3] - top_rgba[3]) * t)
        for x in range(x0, x1):
            px[x, y] = (r, g, b, a)


def add_glow_layer(base: Image.Image, draw_fn, radius: float) -> Image.Image:
    layer = Image.new("RGBA", base.size, (0, 0, 0, 0))
    draw_fn(ImageDraw.Draw(layer))
    if radius > 0:
        layer = layer.filter(ImageFilter.GaussianBlur(radius))
    return Image.alpha_composite(base, layer)


def draw_l_brackets(draw: ImageDraw.ImageDraw, x0: int, y0: int, x1: int, y1: int,
                    length: int, thickness: int, color: tuple):
    # Top-left
    draw.rectangle((x0, y0, x0 + length, y0 + thickness - 1), fill=color)
    draw.rectangle((x0, y0, x0 + thickness - 1, y0 + length), fill=color)
    # Top-right
    draw.rectangle((x1 - length, y0, x1, y0 + thickness - 1), fill=color)
    draw.rectangle((x1 - thickness + 1, y0, x1, y0 + length), fill=color)
    # Bottom-left
    draw.rectangle((x0, y1 - thickness + 1, x0 + length, y1), fill=color)
    draw.rectangle((x0, y1 - length, x0 + thickness - 1, y1), fill=color)
    # Bottom-right
    draw.rectangle((x1 - length, y1 - thickness + 1, x1, y1), fill=color)
    draw.rectangle((x1 - thickness + 1, y1 - length, x1, y1), fill=color)


def draw_panel_glass() -> Image.Image:
    """256x256 9-slice translucent UNSC glass panel with luminous cyan top
    hairline, subtle micro-dot grid, soft top edge bloom, and L-brackets.
    Designed for SlateBrush BOX margin = 48/256 (0.1875)."""
    size = 256
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    inset = 6
    x0, y0, x1, y1 = inset, inset, size - 1 - inset, size - 1 - inset

    # Deep translucent teal-navy gradient body
    draw_vertical_gradient(img, (*NAVY_TOP, 212), (*NAVY_BOT, 224), (x0, y0, x1 + 1, y1 + 1))

    # Faint UNSC tactical micro-dot grid (matches Campaign Evolved's Last Played box)
    dots = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(dots)
    for y in range(y0 + 10, y1 - 8, 12):
        for x in range(x0 + 10, x1 - 8, 12):
            d.point((x, y), fill=(*CYAN_MID, 16))
    img = Image.alpha_composite(img, dots)

    # Soft cyan edge bloom just below the top rail
    def top_bloom(draw):
        draw.rectangle((x0 + 6, y0, x1 - 6, y0 + 5), fill=(*CYAN_BRIGHT, 115))
    img = add_glow_layer(img, top_bloom, radius=10)

    # Crisp 1px luminous frame border + 2px glowing top edge
    frame = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    fd = ImageDraw.Draw(frame)
    fd.rectangle((x0, y0, x1, y1), outline=(*CYAN_DIM, 115), width=1)
    fd.rectangle((x0, y0, x1, y0 + 1), fill=(*CYAN_BRIGHT, 220))
    # Subtle bottom hairline
    fd.rectangle((x0 + 24, y1, x1 - 24, y1), fill=(*CYAN_MID, 95))
    img = Image.alpha_composite(img, frame)

    # Corner L-brackets with soft glow
    def brackets_glow(draw):
        draw_l_brackets(draw, x0 - 2, y0 - 2, x1 + 2, y1 + 2, 18, 2, (*CYAN_BRIGHT, 140))
    img = add_glow_layer(img, brackets_glow, radius=3)

    crisp = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw_l_brackets(ImageDraw.Draw(crisp), x0 - 2, y0 - 2, x1 + 2, y1 + 2, 18, 2, (*CYAN_BRIGHT, 235))
    return Image.alpha_composite(img, crisp)


def draw_panel_subtle() -> Image.Image:
    """256x256 9-slice secondary inner glass card (lobby tiles, variant cards,
    settings box). Designed for BOX margin = 32/256 (0.125)."""
    size = 256
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    inset = 2
    x0, y0, x1, y1 = inset, inset, size - 1 - inset, size - 1 - inset
    draw_vertical_gradient(img, (11, 31, 46, 165), (6, 18, 29, 185), (x0, y0, x1 + 1, y1 + 1))

    frame = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    fd = ImageDraw.Draw(frame)
    fd.rectangle((x0, y0, x1, y1), outline=(*CYAN_DIM, 88), width=1)
    fd.rectangle((x0 + 1, y0, x1 - 1, y0), fill=(*CYAN_MID, 145))
    return Image.alpha_composite(img, frame)


def draw_halo_button(
    fill_top: tuple,
    fill_bot: tuple,
    border_rgba: tuple,
    top_edge_rgba: tuple,
    pip_rgba: tuple | None = None,
    glow_rgba: tuple | None = None,
    left_bar_rgba: tuple | None = None,
) -> Image.Image:
    """256x76 9-slice Campaign Evolved button matching MJOLNIR's natural button
    height (~68-80px) so twin edge pips stay crisp at 1:1. Margin = (36/256, 18/76)."""
    w, h = 256, 76
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    mx, my = 10, 4
    x0, y0, x1, y1 = mx, my, w - 1 - mx, h - 1 - my

    # Optional outer glow halo
    if glow_rgba:
        def outer_glow(draw):
            draw.rectangle((x0, y0, x1, y1), outline=glow_rgba, width=4)
        img = add_glow_layer(img, outer_glow, radius=6)

    # Interior vertical gradient
    body = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw_vertical_gradient(body, fill_top, fill_bot, (x0, y0, x1 + 1, y1 + 1))
    img = Image.alpha_composite(img, body)

    # Subtle radial interior highlight near top-center when lit
    if glow_rgba:
        def inner_bloom(draw):
            draw.ellipse((x0 + 28, y0 - 14, x1 - 28, y0 + 28), fill=(glow_rgba[0], glow_rgba[1], glow_rgba[2], 65))
        bloom = add_glow_layer(Image.new("RGBA", (w, h), (0, 0, 0, 0)), inner_bloom, radius=14)
        # Clip bloom strictly inside button bounds
        mask = Image.new("L", (w, h), 0)
        ImageDraw.Draw(mask).rectangle((x0, y0, x1, y1), fill=255)
        clipped = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        clipped.paste(bloom, (0, 0), mask)
        img = Image.alpha_composite(img, clipped)

    # Crisp borders + optional left energy accent bar
    lines = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ld = ImageDraw.Draw(lines)
    ld.rectangle((x0, y0, x1, y1), outline=border_rgba, width=1)
    ld.rectangle((x0 + 1, y0, x1 - 1, y0 + 1), fill=top_edge_rgba)
    if left_bar_rgba:
        ld.rectangle((x0, y0, x0 + 4, y1), fill=left_bar_rgba)
    img = Image.alpha_composite(img, lines)

    # Signature Campaign Evolved twin horizontal focus pips (left & right edges)
    if pip_rgba:
        cy = (y0 + y1) // 2

        def draw_pips(draw, color, pad=0):
            # Left diamond-pill pip straddling x0
            draw.polygon([
                (x0 - 5 - pad, cy),
                (x0, cy - 4 - pad),
                (x0 + 6 + pad, cy),
                (x0, cy + 4 + pad),
            ], fill=color)
            # Right diamond-pill pip straddling x1
            draw.polygon([
                (x1 - 6 - pad, cy),
                (x1, cy - 4 - pad),
                (x1 + 5 + pad, cy),
                (x1, cy + 4 + pad),
            ], fill=color)

        img = add_glow_layer(img, lambda dr: draw_pips(dr, (*pip_rgba[:3], 180), pad=2), radius=5)
        crisp = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        draw_pips(ImageDraw.Draw(crisp), pip_rgba, pad=0)
        img = Image.alpha_composite(img, crisp)

    return img


def draw_header_rule_fade() -> Image.Image:
    """512x16 luminous cyan accent rule that fades softly to transparent on the right."""
    w, h = 512, 16
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    px = img.load()
    cy = h // 2
    for x in range(w):
        t = x / (w - 1)
        fade = 1.0 if t < 0.55 else max(0.0, 1.0 - (t - 0.55) / 0.45) ** 1.6
        for y in range(h):
            dy = abs(y - cy)
            if dy <= 1:
                a = int(245 * fade)
                px[x, y] = (*CYAN_BRIGHT, a)
            elif dy <= 5:
                a = int(75 * fade * (1.0 - dy / 6.0))
                px[x, y] = (*CYAN_MID, a)
    return img


def draw_left_rail() -> Image.Image:
    """16x512 delicate vertical cyan guide rail matching Campaign Evolved's main menu."""
    w, h = 16, 512
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    px = img.load()
    cx = w // 2
    for y in range(h):
        t = y / (h - 1)
        edge = min(1.0, t / 0.08, (1.0 - t) / 0.08)
        for x in range(w):
            dx = abs(x - cx)
            if dx == 0:
                px[x, y] = (*CYAN_MID, int(155 * edge))
            elif dx <= 3:
                px[x, y] = (*CYAN_DIM, int(45 * edge * (1.0 - dx / 4.0)))
    return img


def draw_medallion_ring() -> Image.Image:
    """256x256 concentric luminous cyan UNSC tech ring for mode emblems & vote clock."""
    scale = 4
    s = 256 * scale
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    cx = cy = s // 2

    # Soft radial dark-teal circular backing
    d = ImageDraw.Draw(img)
    r_outer = int(s * 0.44)
    d.ellipse((cx - r_outer, cy - r_outer, cx + r_outer, cy + r_outer), fill=(9, 32, 46, 175))

    # Glow halo for the outer ring
    def ring_glow(dr):
        dr.ellipse((cx - r_outer, cy - r_outer, cx + r_outer, cy + r_outer),
                   outline=(*CYAN_BRIGHT, 165), width=int(s * 0.022))
    img = add_glow_layer(img, ring_glow, radius=s * 0.028)

    # Crisp outer ring + inner orbital hairline + 4 cardinal ticks
    crisp = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    cd = ImageDraw.Draw(crisp)
    cd.ellipse((cx - r_outer, cy - r_outer, cx + r_outer, cy + r_outer),
               outline=(*CYAN_BRIGHT, 235), width=int(s * 0.011))
    r_inner = int(s * 0.39)
    cd.ellipse((cx - r_inner, cy - r_inner, cx + r_inner, cy + r_inner),
               outline=(*CYAN_MID, 110), width=int(s * 0.004))

    # 4 subtle cardinal tech tabs on the ring
    tab_w = int(s * 0.014)
    tab_l = int(s * 0.030)
    for angle_deg in (0, 90, 180, 270):
        rad = math.radians(angle_deg)
        nx, ny = math.cos(rad), math.sin(rad)
        px0 = cx + int(nx * (r_outer - tab_l // 2))
        py0 = cy + int(ny * (r_outer - tab_l // 2))
        cd.ellipse((px0 - tab_w, py0 - tab_w, px0 + tab_w, py0 + tab_w), fill=(*CYAN_BRIGHT, 245))

    img = Image.alpha_composite(img, crisp)
    return img.resize((256, 256), Image.Resampling.LANCZOS)


def draw_vote_bar_spark() -> Image.Image:
    """96x48 radial cyan-white leading-edge spark for the draining vote bar."""
    w, h = 96, 48
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    px = img.load()
    cx, cy = w / 2.0, h / 2.0
    for y in range(h):
        for x in range(w):
            dx = (x - cx) / (w * 0.42)
            dy = (y - cy) / (h * 0.36)
            r = math.sqrt(dx * dx + dy * dy)
            if r >= 1.0:
                continue
            core = max(0.0, 1.0 - r * 2.4) ** 2.0
            halo = max(0.0, 1.0 - r) ** 2.6
            # Subtle horizontal flare streak
            streak = max(0.0, 1.0 - abs(x - cx) / (w * 0.48)) * max(0.0, 1.0 - abs(y - cy) / 4.5) ** 2.0
            intensity = min(1.0, core * 1.0 + halo * 0.65 + streak * 0.85)
            mix = min(1.0, core * 1.2 + streak * 0.4)
            rr = int(CYAN_BRIGHT[0] + (255 - CYAN_BRIGHT[0]) * mix)
            gg = int(CYAN_BRIGHT[1] + (255 - CYAN_BRIGHT[1]) * mix)
            bb = int(CYAN_BRIGHT[2] + (255 - CYAN_BRIGHT[2]) * mix)
            px[x, y] = (rr, gg, bb, int(255 * intensity))
    return img


def draw_footer_bar() -> Image.Image:
    """256x64 9-slice translucent dark-teal bottom hotkey bar matching main-menu.jpg."""
    w, h = 256, 64
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw_vertical_gradient(img, (6, 22, 34, 212), (3, 12, 20, 232))
    d = ImageDraw.Draw(img)
    d.rectangle((0, 0, w - 1, 0), fill=(*CYAN_MID, 145))
    d.rectangle((0, 1, w - 1, 1), fill=(*CYAN_DIM, 65))
    return img


def draw_keycap() -> Image.Image:
    """96x64 9-slice sleek UNSC keycap badge ([ENTER], [ESC], [F])."""
    w, h = 96, 64
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((2, 2, w - 3, h - 3), radius=8,
                        fill=(10, 29, 44, 185), outline=(*CYAN_MID, 175), width=2)
    return img


def draw_current_pill() -> Image.Image:
    """160x64 9-slice translucent Spartan-gold badge backing for CURRENT / PLAY AGAIN."""
    w, h = 160, 64
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((3, 3, w - 4, h - 4), radius=24,
                        fill=(110, 82, 24, 150), outline=(*GOLD_MID, 220), width=2)
    return img


ASSETS = {
    "PanelGlass": draw_panel_glass,
    "PanelSubtle": draw_panel_subtle,
    "BtnCyanIdle": lambda: draw_halo_button(
        (12, 33, 49, 130), (7, 21, 33, 148),
        (*CYAN_DIM, 82), (*CYAN_MID, 125),
    ),
    "BtnCyanHover": lambda: draw_halo_button(
        (24, 78, 108, 210), (14, 52, 74, 222),
        (*CYAN_BRIGHT, 235), (210, 246, 255, 245),
        pip_rgba=(220, 248, 255, 255),
        glow_rgba=(*CYAN_BRIGHT, 145),
        left_bar_rgba=(*CYAN_BRIGHT, 240),
    ),
    "BtnCyanPress": lambda: draw_halo_button(
        (38, 110, 145, 235), (22, 74, 104, 242),
        (215, 248, 255, 255), (240, 252, 255, 255),
        pip_rgba=(255, 255, 255, 255),
        glow_rgba=(*CYAN_BRIGHT, 200),
        left_bar_rgba=(235, 252, 255, 255),
    ),
    "BtnGoldIdle": lambda: draw_halo_button(
        (92, 69, 22, 178), (58, 42, 13, 198),
        (*GOLD_MID, 195), (*GOLD_BRIGHT, 225),
        pip_rgba=(*GOLD_BRIGHT, 215),
        glow_rgba=(*GOLD_MID, 90),
        left_bar_rgba=(*GOLD_BRIGHT, 225),
    ),
    "BtnGoldHover": lambda: draw_halo_button(
        (142, 106, 32, 225), (96, 70, 20, 235),
        (*GOLD_BRIGHT, 250), (255, 242, 190, 255),
        pip_rgba=(255, 248, 215, 255),
        glow_rgba=(*GOLD_BRIGHT, 185),
        left_bar_rgba=(255, 242, 190, 255),
    ),
    "BtnGoldPress": lambda: draw_halo_button(
        (178, 134, 42, 242), (125, 92, 28, 246),
        (255, 246, 205, 255), (255, 252, 230, 255),
        pip_rgba=(255, 255, 245, 255),
        glow_rgba=(*GOLD_BRIGHT, 220),
        left_bar_rgba=(255, 252, 230, 255),
    ),
    "BtnDisabled": lambda: draw_halo_button(
        (10, 16, 22, 95), (7, 12, 17, 105),
        (45, 65, 80, 60), (55, 80, 98, 70),
    ),
    "HeaderRuleFade": draw_header_rule_fade,
    "LeftRail": draw_left_rail,
    "MedallionRing": draw_medallion_ring,
    "VoteBarSpark": draw_vote_bar_spark,
    "FooterBar": draw_footer_bar,
    "Keycap": draw_keycap,
    "CurrentPill": draw_current_pill,
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=OUT)
    parser.add_argument("--sheet", type=Path, help="Optional contact sheet PNG for inspection")
    args = parser.parse_args()

    args.out.mkdir(parents=True, exist_ok=True)
    rendered = {}
    for name, fn in ASSETS.items():
        img = fn()
        dest = args.out / f"{name}.png"
        img.save(dest, "PNG")
        rendered[name] = img
        print(f"wrote {dest.relative_to(OUT.parents[3])} ({img.width}x{img.height})")

    if args.sheet:
        cols = 4
        cell_w, cell_h = 280, 180
        rows = (len(rendered) + cols - 1) // cols
        sheet = Image.new("RGBA", (cols * cell_w, rows * cell_h), (6, 12, 20, 255))
        draw = ImageDraw.Draw(sheet)
        for idx, (name, img) in enumerate(rendered.items()):
            r, c = divmod(idx, cols)
            ox, oy = c * cell_w, r * cell_h
            thumb = img.copy()
            thumb.thumbnail((cell_w - 24, cell_h - 40), Image.Resampling.LANCZOS)
            px = ox + (cell_w - thumb.width) // 2
            py = oy + 10 + (cell_h - 40 - thumb.height) // 2
            sheet.alpha_composite(thumb, (px, py))
            draw.text((ox + 12, oy + cell_h - 24), name, fill=(140, 220, 255, 255))
        args.sheet.parent.mkdir(parents=True, exist_ok=True)
        sheet.save(args.sheet, "PNG")
        print(f"wrote sheet {args.sheet}")


if __name__ == "__main__":
    main()
