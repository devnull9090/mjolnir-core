# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy>=2,<3","pillow","scipy","shapely"]
# ///
"""Bake shared colour and tangent relief for the near-driver ground debris and the decayed pine."""

import numpy as np
import subprocess
from PIL import Image
from scipy.ndimage import gaussian_filter
from sweep_litter import OUT, REGIONS
from build_sweep_banks import CLI, PAKS, SWEEP, sha256, save


def run():
    rng = np.random.default_rng(18930)
    stock = OUT / "stock"
    stock.mkdir(parents=True, exist_ok=True)
    for kind, leaf in [("D", "bark.png"), ("N", "bark-N.png")]:
        if not (stock / leaf).is_file():
            subprocess.run(
                [
                    CLI,
                    "texture",
                    "export",
                    "--paks",
                    PAKS,
                    "--asset",
                    "T_Broken_Tree_Bark_wjhiecy_4K_" + kind,
                    "--out",
                    stock / leaf,
                ],
                check=True,
            )
    bark = np.array(Image.open(OUT / "stock/bark.png").convert("RGB"))
    # Crop a fully covered bark slab inside the original Megascans atlas (dark empty padding excluded).
    s = 256
    weight = np.array(Image.fromarray(bark).convert("L").resize((s, s)))
    best = (-1, None)
    for y in range(0, 128, 6):
        for x in range(0, 177, 6):
            box = weight[y : y + 128, x : x + 80]
            score = np.mean(box > 30) * 100 + box.std() * 0.04
            if score > best[0]:
                best = (score, (x, y))
    x, y = best[1]
    h, w = bark.shape[:2]
    region = (x * w // s, y * h // s, (x + 80) * w // s, (y + 128) * h // s)
    rawb = Image.fromarray(bark).crop(region)
    rn = Image.open(OUT / "stock/bark-N.png").convert("RGB").crop(region)
    gravel = Image.open(SWEEP / "earth/stock/T_Scree_NSVT_A30_D.png").convert("RGB")
    pixels = np.zeros((1024, 1024, 3), dtype=np.uint8)
    normal = np.full((1024, 1024, 3), [128, 128, 255], dtype=np.uint8)
    palette = {
        "needle": [139, 81, 40],
        "gold": [169, 129, 64],
        "grass": [77, 101, 40],
        "stone": [132, 128, 116],
        "cone": [114, 68, 37],
        "twig": [94, 74, 52],
        "moss": [84, 98, 54],
        "shade": [73, 62, 47],
        "bark": [100, 79, 60],
        "end": [143, 110, 77],
    }
    for key, (u, v, sw, sh) in REGIONS.items():
        x, y, w, h = (int(q * 1024) for q in [u, v, sw, sh])
        sl = np.s_[y : y + h, x : x + w]
        yy, xx = np.mgrid[:h, :w].astype(float)
        xx /= w - 1
        yy /= h - 1
        im = gravel if key == "stone" else rawb
        scan = np.array(im.resize((w, h), Image.Resampling.LANCZOS), dtype=float)
        lum = scan @ np.array([0.27, 0.55, 0.18])
        lum -= np.median(lum)
        val = 0.77 * lum if key in ("stone", "bark", "twig") else lum * 0.21
        val += rng.normal(0, 3.2, (h, w))
        if key == "bark":
            val += 8 * np.sin(22 * xx + np.sin(5 * yy)) + 4 * np.sin(
                91 * xx + 2 * np.sin(7 * yy)
            )
            normal[sl] = np.asarray(rn.resize((w, h), Image.Resampling.LANCZOS))
        if key in ("needle", "grass", "gold"):
            val += (
                21 * (1 - yy)
                - 18 * yy
                + 9 * np.cos(11 * xx)
                + 3.5 * np.sin(65 * xx + yy)
            )
        if key == "cone":
            val += 24 * (1 - yy) - 31 * yy + 12 * np.cos((xx - 0.5) * 3)
        if key == "end":
            r = np.hypot((xx - 0.47) * 1.1, yy - 0.52)
            theta = np.arctan2(yy - 0.52, xx - 0.47)
            rings = np.sin(
                149 * r
                + 1.8 * np.sin(theta * 3)
                + 1.3 * np.sin(9 * yy) * np.cos(10 * xx)
            )
            val = (
                val * 0.6
                - 16 * np.maximum(0, rings - 0.27)
                + 9 * np.cos(12 * r + theta)
            )
            for angle, extent in [(0.6, 0.26), (-2.2, 0.13), (2.5, 0.32), (-0.8, 0.25)]:
                dist = abs(np.sin(theta - angle)) * r
                val -= (
                    42
                    * np.exp(-np.square(dist / 0.006))
                    * (r > extent)
                    * (np.cos(theta - angle) > 0)
                )
            val -= 26 * np.clip((r - 0.40) / 0.06, 0, 1)
        c = (
            np.array(palette[key])
            + val[..., None]
            + 0.15 * (scan - (scan @ np.array([0.27, 0.55, 0.18]))[..., None])
        )
        pixels[sl] = np.clip(c, 0, 255).astype(np.uint8)
        if key not in ("bark", "grass", "gold", "needle"):
            gy, gx = np.gradient(gaussian_filter(val, 0.9))
            xy = np.dstack((-gx, gy)) * 0.035
            n = np.dstack((xy, np.ones_like(gy)))
            n /= np.linalg.norm(n, axis=-1, keepdims=True)
            normal[sl] = (255 * (n * 0.5 + 0.5)).astype(np.uint8)
    images = {}
    for key, im in [("D", pixels), ("N", normal)]:
        path = OUT / f"litter-{key}.png"
        Image.fromarray(im).save(path)
        images[key] = dict(
            file=path.name,
            sha256=sha256(path),
            size=[1024, 1024],
            package="/Game/MJOLNIR/GrassPilot/Playable/T_PWR_SweepLitter_" + key,
        )
    save(
        OUT / "litter-textures.json",
        dict(
            images=images,
            bark_source_sha256=sha256(OUT / "stock/bark.png"),
            native_bark_normals_sha256=sha256(OUT / "stock/bark-N.png"),
        ),
    )


if __name__ == "__main__":
    run()
