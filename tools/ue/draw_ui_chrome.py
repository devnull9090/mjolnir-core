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


def draw_panel_glass(top_alpha: int = 214, bot_alpha: int = 226) -> Image.Image:
    """256x256 9-slice translucent UNSC glass panel with luminous cyan top
    hairline, subtle micro-dot grid, clipped soft top bloom, and flush corner
    L-brackets. Designed for SlateBrush BOX margin = 0.14 (~36px)."""
    size = 256
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    inset = 6
    x0, y0, x1, y1 = inset, inset, size - 1 - inset, size - 1 - inset

    # Deep translucent teal-navy gradient body
    draw_vertical_gradient(img, (*NAVY_TOP, top_alpha), (*NAVY_BOT, bot_alpha), (x0, y0, x1 + 1, y1 + 1))

    # Faint UNSC tactical micro-dot grid (matches Campaign Evolved's Last Played box)
    dots = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(dots)
    for y in range(y0 + 14, y1 - 12, 12):
        for x in range(x0 + 14, x1 - 12, 12):
            d.point((x, y), fill=(*CYAN_MID, 16))
    img = Image.alpha_composite(img, dots)

    # Soft cyan edge bloom strictly clipped inside the panel bounds
    def top_bloom(draw):
        draw.rectangle((x0 + 8, y0, x1 - 8, y0 + 5), fill=(*CYAN_BRIGHT, 115))
    bloom_raw = add_glow_layer(Image.new("RGBA", (size, size), (0, 0, 0, 0)), top_bloom, radius=10)
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rectangle((x0, y0, x1, y1), fill=255)
    bloom_clipped = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    bloom_clipped.paste(bloom_raw, (0, 0), mask)
    img = Image.alpha_composite(img, bloom_clipped)

    # Crisp 1px luminous frame border + 2px glowing top edge
    frame = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    fd = ImageDraw.Draw(frame)
    fd.rectangle((x0, y0, x1, y1), outline=(*CYAN_DIM, 130), width=1)
    fd.rectangle((x0, y0, x1, y0 + 1), fill=(*CYAN_BRIGHT, 225))
    # Subtle bottom hairline
    fd.rectangle((x0 + 24, y1, x1 - 24, y1), fill=(*CYAN_MID, 105))
    img = Image.alpha_composite(img, frame)

    # Corner L-brackets flush on the panel corners (no floating gap)
    def brackets_glow(draw):
        draw_l_brackets(draw, x0, y0, x1, y1, 18, 2, (*CYAN_BRIGHT, 145))
    img = add_glow_layer(img, brackets_glow, radius=3)

    crisp = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw_l_brackets(ImageDraw.Draw(crisp), x0, y0, x1, y1, 18, 2, (*CYAN_BRIGHT, 240))
    return Image.alpha_composite(img, crisp)


def draw_panel_subtle() -> Image.Image:
    """256x256 9-slice secondary inner glass card (lobby tiles, map sub-card,
    search bar). Designed for BOX margin = 0.08."""
    size = 256
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    inset = 2
    x0, y0, x1, y1 = inset, inset, size - 1 - inset, size - 1 - inset
    draw_vertical_gradient(img, (13, 36, 54, 172), (7, 21, 34, 192), (x0, y0, x1 + 1, y1 + 1))

    frame = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    fd = ImageDraw.Draw(frame)
    fd.rectangle((x0, y0, x1, y1), outline=(*CYAN_MID, 108), width=1)
    fd.rectangle((x0 + 1, y0, x1 - 1, y0), fill=(*CYAN_BRIGHT, 160))
    return Image.alpha_composite(img, frame)


def draw_halo_button(
    fill_top: tuple,
    fill_bot: tuple,
    border_rgba: tuple,
    top_edge_rgba: tuple,
    pip_rgba: tuple | None = None,
    glow_rgba: tuple | None = None,
    left_bar_rgba: tuple | None = None,
    mx: int = 7,
    my: int = 4,
    left_bar_w: int = 4,
) -> Image.Image:
    """256x76 9-slice Campaign Evolved button matching MJOLNIR's natural button
    height (~68-80px) so twin edge pips stay crisp at 1:1.
    Action buttons use mx=7 (margin 0.09); flush rows/tiles use mx=2 (margin 0.06)."""
    w, h = 256, 76
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    x0, y0, x1, y1 = mx, my, w - 1 - mx, h - 1 - my

    # Optional outer glow halo
    if glow_rgba:
        def outer_glow(draw):
            draw.rectangle((x0, y0, x1, y1), outline=glow_rgba, width=3)
        img = add_glow_layer(img, outer_glow, radius=5 if mx >= 6 else 2)

    # Interior vertical gradient
    body = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw_vertical_gradient(body, fill_top, fill_bot, (x0, y0, x1 + 1, y1 + 1))
    img = Image.alpha_composite(img, body)

    # Subtle radial interior highlight near top-center when lit
    if glow_rgba:
        def inner_bloom(draw):
            draw.ellipse((x0 + 28, y0 - 14, x1 - 28, y0 + 28), fill=(glow_rgba[0], glow_rgba[1], glow_rgba[2], 65))
        bloom = add_glow_layer(Image.new("RGBA", (w, h), (0, 0, 0, 0)), inner_bloom, radius=14)
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
        ld.rectangle((x0, y0, x0 + left_bar_w - 1, y1), fill=left_bar_rgba)
    img = Image.alpha_composite(img, lines)

    # Signature Campaign Evolved twin horizontal focus pips (left & right edges),
    # kept compact (x0-4 .. x0+5) so button labels never overlap them.
    if pip_rgba:
        cy = (y0 + y1) // 2

        def draw_pips(draw, color, pad=0):
            draw.polygon([
                (x0 - 4 - pad, cy),
                (x0, cy - 3 - pad),
                (x0 + 5 + pad, cy),
                (x0, cy + 3 + pad),
            ], fill=color)
            draw.polygon([
                (x1 - 5 - pad, cy),
                (x1, cy - 3 - pad),
                (x1 + 4 + pad, cy),
                (x1, cy + 3 + pad),
            ], fill=color)

        img = add_glow_layer(img, lambda dr: draw_pips(dr, (*pip_rgba[:3], 175), pad=2), radius=4)
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
    "PanelModal": lambda: draw_panel_glass(top_alpha=246, bot_alpha=252),
    "PanelSubtle": draw_panel_subtle,
    "BtnDiscordIdle": lambda: draw_halo_button(
        (30, 36, 82, 188), (18, 22, 54, 206),
        (112, 128, 248, 170), (156, 170, 255, 220),
        left_bar_rgba=(126, 142, 255, 215),
        mx=2, my=2, left_bar_w=3,
    ),
    "BtnDiscordHover": lambda: draw_halo_button(
        (52, 62, 134, 226), (34, 42, 96, 236),
        (162, 176, 255, 245), (212, 220, 255, 252),
        glow_rgba=(126, 142, 255, 155),
        left_bar_rgba=(192, 202, 255, 248),
        mx=2, my=2, left_bar_w=3,
    ),
    "BtnDiscordPress": lambda: draw_halo_button(
        (76, 88, 184, 242), (52, 62, 138, 248),
        (210, 218, 255, 255), (236, 240, 255, 255),
        glow_rgba=(150, 166, 255, 205),
        left_bar_rgba=(226, 232, 255, 255),
        mx=2, my=2, left_bar_w=4,
    ),
    "BtnCyanIdle": lambda: draw_halo_button(
        (16, 44, 66, 165), (9, 26, 41, 182),
        (*CYAN_MID, 145), (*CYAN_BRIGHT, 175),
        left_bar_rgba=(*CYAN_MID, 165),
        left_bar_w=2,
    ),
    "BtnCyanHover": lambda: draw_halo_button(
        (26, 84, 118, 215), (15, 56, 80, 228),
        (*CYAN_BRIGHT, 240), (215, 248, 255, 248),
        pip_rgba=(225, 250, 255, 255),
        glow_rgba=(*CYAN_BRIGHT, 145),
        left_bar_rgba=(*CYAN_BRIGHT, 240),
    ),
    "BtnCyanPress": lambda: draw_halo_button(
        (40, 116, 152, 238), (24, 78, 108, 244),
        (220, 248, 255, 255), (242, 252, 255, 255),
        pip_rgba=(255, 255, 255, 255),
        glow_rgba=(*CYAN_BRIGHT, 200),
        left_bar_rgba=(238, 252, 255, 255),
    ),
    "BtnGoldIdle": lambda: draw_halo_button(
        (96, 72, 23, 185), (60, 44, 14, 205),
        (*GOLD_MID, 205), (*GOLD_BRIGHT, 235),
        pip_rgba=(*GOLD_BRIGHT, 225),
        glow_rgba=(*GOLD_MID, 95),
        left_bar_rgba=(*GOLD_BRIGHT, 230),
    ),
    "BtnGoldHover": lambda: draw_halo_button(
        (146, 110, 34, 228), (98, 72, 22, 238),
        (*GOLD_BRIGHT, 252), (255, 244, 196, 255),
        pip_rgba=(255, 248, 218, 255),
        glow_rgba=(*GOLD_BRIGHT, 185),
        left_bar_rgba=(255, 244, 196, 255),
    ),
    "BtnGoldPress": lambda: draw_halo_button(
        (180, 136, 44, 244), (126, 94, 30, 248),
        (255, 248, 210, 255), (255, 252, 235, 255),
        pip_rgba=(255, 255, 245, 255),
        glow_rgba=(*GOLD_BRIGHT, 220),
        left_bar_rgba=(255, 252, 235, 255),
    ),
    "BtnDisabled": lambda: draw_halo_button(
        (10, 18, 25, 105), (7, 13, 19, 118),
        (52, 74, 92, 72), (62, 88, 108, 82),
    ),
    # Flush 9-slice row/tile/chip chrome (mx=2, my=2, no protruding pips) tuned
    # so Lua's SetBackgroundColor(CHOSEN) lights up unmistakably as UNSC cyan glass.
    "RowCyanIdle": lambda: draw_halo_button(
        (20, 52, 74, 138), (13, 35, 51, 156),
        (*CYAN_MID, 112), (*CYAN_BRIGHT, 138),
        left_bar_rgba=(*CYAN_MID, 145),
        mx=2, my=2, left_bar_w=2,
    ),
    "RowCyanHover": lambda: draw_halo_button(
        (30, 92, 126, 212), (18, 62, 88, 226),
        (*CYAN_BRIGHT, 235), (212, 246, 255, 245),
        glow_rgba=(*CYAN_BRIGHT, 120),
        left_bar_rgba=(*CYAN_BRIGHT, 245),
        mx=2, my=2, left_bar_w=3,
    ),
    "RowCyanPress": lambda: draw_halo_button(
        (46, 128, 166, 238), (28, 86, 118, 244),
        (220, 248, 255, 255), (242, 252, 255, 255),
        glow_rgba=(*CYAN_BRIGHT, 180),
        left_bar_rgba=(240, 252, 255, 255),
        mx=2, my=2, left_bar_w=4,
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
