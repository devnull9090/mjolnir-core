"""Encode unchanged gameplay captures for the Forge post and mirror guide assets.

Run from the repository root after rendering tools/forge/render_showcase.py.
Pass --overview <PNG> for a new in-game aerial screenshot, and --featured <PNG>
for the 1200x630 render of blog/featured/forge-building.html. No retouching.
Requires Pillow. Originals remain in docs/images/forge and ignored local captures.
"""
import argparse
from pathlib import Path
import shutil
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
WEB = ROOT / "hub/public/blog-images/forge-building"
DOC = ROOT / "docs/images/forge-showcase"

def encode(source, target, size=None):
    with Image.open(source) as image:
        if size:
            image.thumbnail(size, Image.Resampling.LANCZOS)
        image.convert("RGB").save(target, "WEBP", quality=90, method=6)

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--overview", type=Path)
    parser.add_argument("--featured", type=Path)
    args = parser.parse_args()
    WEB.mkdir(parents=True, exist_ok=True)
    DOC.mkdir(parents=True, exist_ok=True)
    for name in ("door", "glass", "lift", "portal"):
        source = ROOT / "docs/images/forge" / ("crossline-03-" + ("door-open" if name == "door" else name) + ".png")
        encode(source, WEB / (name + ".webp"))
    if args.overview:
        encode(args.overview, WEB / "crossline-overview.webp", (1920, 1080))
    if args.featured:
        with Image.open(args.featured) as image:
            if image.size != (1200, 630):
                raise ValueError("Featured render must be exactly 1200x630")
        encode(args.featured, WEB / "featured.webp")
    for source in WEB.glob("*.webp"):
        if source.name != "featured.webp":
            shutil.copyfile(source, DOC / source.name)
    for source in sorted(WEB.glob("*.webp")):
        print(source.relative_to(ROOT), source.stat().st_size)

if __name__ == "__main__":
    main()
