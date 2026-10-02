#!/usr/bin/env python3
"""Write the CE flag's textures for MJOLNIRLevelLoader, team-coloured.

    ce_flag_textures.py <halo2ue staging dir> <out dir>

CE draws the flag's cloth in its team's colour (the model shader's change
colour) over a gold atlas; the converted flag's cloth uses `flag_red.png` or
`flag_blue.png`, the atlas's luminance times the team colour, and its pole the
atlas as it is (`flag.png`). The flag base (the stand's scenery) keeps its
three textures. Writes `<out>/*.png`, which the loader imports at runtime.
"""
import os
import shutil
import sys

from PIL import Image

TEAMS = {"red": (1.0, 0.12, 0.08), "blue": (0.1, 0.25, 1.0)}
# The atlas is dark gold; scaled so the cloth reads as a saturated colour.
GAIN = 2.2

COPIES = {
    "weapons_flag_bitmaps_flag.png": "flag.png",
    "scenery_flag_base_bitmaps_flag_base.png": "flag_base.png",
    "levels_b30_bitmaps_metal_strips_decorative_wide.png": "flag_base_strips.png",
    "levels_b30_bitmaps_metal_flat_generic.png": "flag_base_metal.png",
    # Not the flag's, but cooked beside it: CE's health pack
    # (blam_megalo::powerups, build_ctf_flag.sh).
    "powerups_healthpack_bitmaps_healthpack.png": "healthpack.png",
}


def main():
    staging, out = sys.argv[1:3]
    textures = os.path.join(staging, "textures")
    os.makedirs(out, exist_ok=True)
    for src, dst in COPIES.items():
        shutil.copyfile(os.path.join(textures, src), os.path.join(out, dst))
    atlas = Image.open(os.path.join(textures, "weapons_flag_bitmaps_flag.png")).convert("RGBA")
    lum = atlas.convert("L")
    for team, (r, g, b) in TEAMS.items():
        bands = [lum.point(lambda v, c=c: min(255, int(v * c * GAIN))) for c in (r, g, b)]
        Image.merge("RGBA", bands + [atlas.getchannel("A")]).save(os.path.join(out, f"flag_{team}.png"))
    print(f"{len(COPIES) + len(TEAMS)} texture(s) -> {out}")


if __name__ == "__main__":
    main()
