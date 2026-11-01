"""Make the MJOLNIR CORE emblem for the game's menu screens from the hub's own
logo: cropped to what it draws, centred on a transparent square and scaled
down, so the cooked texture is no bigger than the screens need.

    python tools/ue/brand_logo.py

Writes unreal/MJOLNIRMaterials/Art/Brand/Logo.png (SIZE x SIZE, RGBA).
Scripts/build_mjolnir_ui.py imports it as T_MJBrand_Logo into
/Game/MJOLNIR/UI/Brand and draws it at the top right of every menu screen
(chunk 984).
"""
import os

from PIL import Image

SIZE = 256   # the emblem is drawn 190 UI units square: 285 pixels at 4K
ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
SOURCE = os.path.join(ROOT, "hub", "public", "logo-transparent.png")
OUT = os.path.join(ROOT, "unreal", "MJOLNIRMaterials", "Art", "Brand", "Logo.png")


def main():
    logo = Image.open(SOURCE).convert("RGBA")
    logo = logo.crop(logo.getchannel("A").getbbox())
    side = max(logo.size)
    square = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    square.paste(logo, ((side - logo.width) // 2, (side - logo.height) // 2))
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    square.resize((SIZE, SIZE), Image.LANCZOS).save(OUT)
    print(f"wrote {os.path.normpath(OUT)} ({SIZE} x {SIZE}) from {os.path.normpath(SOURCE)}")


if __name__ == "__main__":
    main()
