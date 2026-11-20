"""Prepare the canopy insignia and pack label for the insertion textile atlas."""
import argparse
import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps


HERE = Path(__file__).resolve().parent
LOGO = HERE.parents[4] / "unreal/MJOLNIRMaterials/Art/Brand/Logo.png"
HANDLE_URL = "https://x.com/forkutodevnull"
SIZE = (512, 256)


def cloth(rgb):
    image = Image.new("RGB", SIZE)
    pixels = image.load()
    for y in range(SIZE[1]):
        for x in range(SIZE[0]):
            warp = math.cos(math.tau * x / 3)
            weft = math.cos(math.tau * (y + (x // 3) % 2) / 4)
            delta = round(1.3 * warp + 1.5 * weft)
            pixels[x, y] = tuple(v + delta for v in rgb)
    return image


def insignia():
    # Use the established in-game shield and its lettering. Ink density
    # follows the original art, including its dark cutouts and fine strokes.
    mark = Image.open(LOGO).convert("RGBA")
    mark = mark.crop(mark.getchannel("A").getbbox())
    mark.thumbnail((225, 225), Image.Resampling.LANCZOS)
    stencil = ImageOps.colorize(ImageOps.grayscale(mark), (43, 48, 31), (212, 207, 156))
    base = cloth((73, 80, 51))
    origin = ((512 - mark.width)//2, (256 - mark.height)//2)
    alpha = mark.getchannel("A")
    base.paste(stencil, origin, alpha)
    mask = Image.new("L", SIZE)
    mask.paste(alpha, origin)
    return base, mask


def maker_label(font_file):
    image = cloth((41, 44, 38))
    draw = ImageDraw.Draw(image)
    for x in range(15, 498, 9):
        for y in (12, 242):
            draw.line((x, y, x+4, y), fill=(101, 99, 76), width=2)
    for y in range(21, 240, 9):
        for x in (12, 498):
            draw.line((x, y, x, y+4), fill=(101, 99, 76), width=2)
    font = ImageFont.truetype(str(font_file), 30)
    assert draw.textlength(HANDLE_URL, font=font) <= 476
    draw.text((256,128), HANDLE_URL, font=font, anchor="mm", fill=(207, 205, 170))
    return image


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--font", type=Path, default=Path("C:/Windows/Fonts/bahnschrift.ttf"))
    parser.add_argument("--out", type=Path, default=HERE / "print")
    parser.add_argument("--previews", type=Path)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    if args.previews:
        args.previews.mkdir(parents=True, exist_ok=True)
    mark, mask = insignia()
    for name, image in (("canopy-mark", mark), ("canopy-ink-mask", mask), ("pack-label", maker_label(args.font))):
        image.save(args.out / (name + ".tga"), compression=None)
        if args.previews:
            image.save(args.previews / (name + ".png"))
            image.save(args.previews / (name + ".tga"), compression=None)
