# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy>=2,<3","pillow","scipy","shapely"]
# ///
"""Bake four individual bank surfaces into a shared native color and normal atlas."""

import numpy as np
from PIL import Image
from scipy.ndimage import map_coordinates

from build_sweep_banks import BANKS, OUT, SWEEP, save, sha256

STOCK = SWEEP / "earth/stock"
FILES = {
    "moss": "T_Mossy_Ground_xiboab2r_4K_D.png",
    "dirt": "T_Trampled_Forest_Path_ub4jdihkw_NSVT_D.png",
    "stone": "T_Scree_NSVT_A30_D.png",
    "moss_n": "T_Mossy_Ground_xiboab2r_4K_N.png",
    "stone_n": "T_Gravel_Natural_vglndb0g_4K_NSVT_N.png",
}


def read_source(name):
    im = Image.open(STOCK / FILES[name]).convert("RGB")
    im.thumbnail((1536, 1536), Image.Resampling.LANCZOS)
    return np.asarray(im)


def sample(im, u, v, period):
    h, w = im.shape[:2]
    coords = np.stack(((v / period % 1) * h, (u / period % 1) * w))
    return np.stack(
        [
            map_coordinates(c, coords, order=1, mode="grid-wrap")
            for c in im.transpose(2, 0, 1)
        ],
        axis=-1,
    ).astype(np.float32)


def main():
    source = {s: read_source(s) for s in FILES}
    size = 1024
    color, normal = (
        np.zeros((size * 2, size * 2, 3), dtype=np.uint8) for i in range(2)
    )
    ly, lx = np.mgrid[:size, :size].astype(np.float32)
    lx = ((lx + 0.5) / size - 0.5) / 0.445
    ly = ((ly + 0.5) / size - 0.5) / 0.445
    for i, (_, _, radii, angle, _) in enumerate(BANKS):
        x, y = radii[0] * lx + 3 * i, radii[1] * ly - 1.72 * i
        # Tile in metres. Gentle domain distortion breaks the scan repetition on long banks.
        u, v = (
            x + 0.12 * np.sin(y * 1.19 + x * 0.57),
            y + 0.16 * np.sin(x * 0.85 - y * 0.62),
        )
        m = sample(source["moss"], u, v, 1.64)
        s = sample(source["stone"], u + 0.27 * v, v - 0.13 * u, 1.32)
        d = sample(source["dirt"], -0.76 * v + 0.65 * u, 0.76 * u + 0.65 * v, 1.86)
        macro = (
            0.45 * np.sin(x * 1.67 + y * 0.89)
            + 0.30 * np.cos(y * 2.13 - x * 0.64)
            + 0.25 * np.sin(x * 3.27 - y * 2.72)
        )
        stone = np.clip(
            (macro - (0.04 if i == 0 else 0.46)) * (1.9 if i == 0 else 1.3), 0, 0.86
        )
        # Thick velvety moss breaks up into granular bark, leaf litter and clean mineral faces.
        litter = np.clip(
            0.20 + 0.38 * np.hypot(lx, ly) - 0.29 * macro + (0.16 if i > 1 else 0),
            0.08,
            0.79,
        )
        m = m * np.array([0.80, 0.85, 0.64], dtype=np.float32) + [7.0, 7.0, 4.0]
        s = s * np.array([0.61, 0.62, 0.58], dtype=np.float32) + [7.0, 6.0, 4.0]
        d = d * np.array([0.83, 0.70, 0.52], dtype=np.float32) + [10.0, 7.0, 4.0]
        c = (m * (1 - litter[..., None]) + d * litter[..., None]) * (
            1 - stone[..., None]
        ) + s * stone[..., None]
        # Retain scan normals on the visible cap even under grazing afternoon light.
        mn = sample(source["moss_n"], u, v, 1.64)[..., :2] / 127.5 - 1
        sn = (
            sample(source["stone_n"], u + 0.27 * v, v - 0.13 * u, 1.32)[..., :2] / 127.5
            - 1
        )
        w = (0.27 + 0.65 * stone)[..., None]
        xy = np.clip((mn * (1 - w) + sn * w) * 0.83, -0.9, 0.9)
        z = np.sqrt(np.maximum(1.0 - (xy * xy).sum(axis=-1), 0.01))
        n = np.dstack((xy, z))
        n /= np.linalg.norm(n, axis=-1, keepdims=True)
        sl = np.s_[
            i // 2 * size : (i // 2 + 1) * size, i % 2 * size : (i % 2 + 1) * size, :
        ]
        color[sl] = np.clip(c, 0, 255).astype(np.uint8)
        normal[sl] = np.round((n * 0.5 + 0.5) * 255).astype(np.uint8)
    manifest = {
        "source": {k: sha256(STOCK / f) for k, f in FILES.items()},
        "images": {},
    }
    for key, im in (("D", color), ("N", normal)):
        path = OUT / f"bank-{key}.png"
        Image.fromarray(im).save(path, compress_level=3)
        manifest["images"][key] = dict(
            filename=path.name, sha256=sha256(path), size=list(im.shape[:2])
        )
    save(OUT / "bank-textures.json", manifest)


if __name__ == "__main__":
    main()
