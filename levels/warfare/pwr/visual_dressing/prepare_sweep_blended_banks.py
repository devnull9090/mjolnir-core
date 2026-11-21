# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy>=2,<3","pillow","scipy","shapely"]
# ///
"""Bake UV-registered granite caps and masked forest-floor toes from the surveyed render triangles."""

import numpy as np
from PIL import Image
from scipy.ndimage import gaussian_filter

from build_sweep_banks import ROOT, SWEEP, read, save, sha256
from prepare_sweep_bank_textures import STOCK, FILES, read_source, sample
from sweep_bank_forms import BANKS, tile, smooth
import argparse

OUT = SWEEP / "round17/verges"
SIZE = 2048


def rasterize(uv, faces, fields):
    """Interpolate authored height-to-ground, slope and rim distance on the real triangles."""
    result = np.zeros((SIZE, SIZE, fields.shape[1]), dtype=np.float32)
    result[..., 0] = 1.14
    result[..., 1] = -0.4
    result[..., 2] = 1
    for f in faces:
        tri = uv[f] * SIZE - 0.5
        lo = np.maximum(np.floor(tri.min(axis=0)).astype(int), 0)
        hi = np.minimum(np.ceil(tri.max(axis=0)).astype(int) + 1, SIZE)
        x, y = np.meshgrid(np.arange(lo[0], hi[0]), np.arange(lo[1], hi[1]))
        p = np.stack((x - tri[0, 0], y - tri[0, 1]), axis=-1)
        weight = p @ np.linalg.inv(tri[1:] - tri[0])
        inside = (weight.min(-1) > -1e-5) & (weight.sum(-1) < 1.00001)
        region = result[lo[1] : hi[1], lo[0] : hi[0]]
        region[inside] = fields[f[0]] + weight[inside] @ (fields[f[1:]] - fields[f[0]])
    return result


def tone(scan, color, contrast, chromaticity):
    """Shape scan luminance across each surface while retaining the source's mineral variation."""
    luma = scan @ np.array([0.25, 0.58, 0.17], dtype=np.float32)
    delta = (luma - np.median(luma)) * contrast
    return np.clip(
        color + delta[..., None] + (scan - luma[..., None]) * chromaticity, 0, 255
    )


def run(revision=17):
    geo = read(OUT / "landform.json")
    raw = read(OUT / "bank-surface-fields.json")
    fields = np.array(raw["fields"])
    surf = rasterize(
        np.array(geo["uv"]),
        np.array(geo["faces"]),
        np.column_stack((fields[:, 0], fields[:, 1], raw["normal_z"], fields[:, 2])),
    )
    stock = {s: read_source(s) for s in FILES}
    granite = (
        ROOT
        / "out/pwr/base-approaches/site-finish/geometry/T_Rock_Jagged_udemcebew_NSVT_D.png"
    )
    ig = Image.open(granite).convert("RGB")
    ig.thumbnail((1536, 1536), Image.Resampling.LANCZOS)
    stock["granite"] = np.asarray(ig)
    color = np.zeros((SIZE, SIZE, 4), dtype=np.uint8)
    normal = np.zeros((SIZE, SIZE, 3), dtype=np.uint8)
    noise = np.random.default_rng(171817).random((SIZE, SIZE), dtype=np.float32)
    proof = []
    for i, (_, _, radii, _, _) in enumerate(BANKS):
        u0, v0, tw, th = tile(i)
        x0, y0, w, h = [int(v * SIZE) for v in [u0, v0, tw, th]]
        sl = np.s_[y0 : y0 + h, x0 : x0 + w]
        radius, elev, nz, roots = surf[sl].transpose(2, 0, 1)
        iy, ix = np.mgrid[:h, :w].astype(np.float32)
        lx = ((ix + 0.5) / w - 0.5) / 0.416
        ly = ((iy + 0.5) / h - 0.5) / 0.416
        x = lx * radii[0]
        y = ly * radii[1]
        u = x + 0.18 * np.sin(2.64 * y + 0.62 * x)
        v = y + 0.11 * np.sin(1.29 * x - 1.36 * y)
        m = sample(stock["moss"], u, v, 1.41)
        d = sample(stock["dirt"], -0.34 * x + 0.94 * y, -0.94 * x - 0.34 * y, 1.83)
        s = sample(stock["granite"], 1.14 * u + 0.17 * v, 0.98 * v - 0.20 * u, 2.41)
        granite_lum = s @ np.array([0.25, 0.58, 0.17], dtype=np.float32)
        grain = np.clip((granite_lum - np.median(granite_lum)) / 36, -1.0, 1.0)
        macro = (
            0.50 * np.sin(2.76 * x + 1.1 * y)
            + 0.30 * np.cos(3.04 * y - 1.53 * x)
            + 0.20 * np.sin(5.61 * x - 5.53 * y)
        )
        if i >= 4:
            gray = tone(s, [137.0, 138.0, 134.0], 1.1, 0.17)
            moss = tone(m, [74.0, 91.0, 48.0], 0.80, 0.21)
            cover = smooth(0.76, 0.97, nz + 0.09 * macro + 0.05 * grain) * (
                0.50 + 0.44 * smooth(-0.62, 0.81, macro + 0.39 * grain)
            )
            c = gray * (1 - cover[..., None]) + moss * cover[..., None]
            # Hairline fractures and an irregular band of moss follow the cap's actual contour.
            seam = np.exp(
                -np.square(
                    13 * (np.sin(x * 3.86 + 0.76 * np.cos(2 * y)) + 0.58 * y + 0.61)
                )
            )
            c *= 1.0 - (0.24 * seam * (1 - 0.66 * cover))[..., None]
            if revision == 18:
                band = smooth(
                    -0.03,
                    0.23,
                    np.sin(7.1 * (1 - nz) + 2.25 * y + 1.4 * np.cos(1.6 * x)) * 0.42
                    + 0.24 * macro
                    + 0.33 * grain,
                )
                cover = np.maximum(cover, 0.73 * band * smooth(0.42, 0.86, nz))
                c = gray * (1 - cover[..., None]) + moss * cover[..., None]
                c *= 1 - (0.29 * seam * (1 - 0.68 * cover))[..., None]
            a = np.ones_like(lx)
            stone = 1.0 - cover
        else:
            moss = tone(m, [55.0, 80.0, 49.0], 0.88, 0.18)
            litter = tone(d, [72.0, 64.0, 51.0], 1.02, 0.22)
            cover = np.clip(
                0.18 + 0.30 * macro + 0.16 * grain + 0.22 * smooth(0.11, 0.42, elev),
                0.04,
                0.84,
            )
            c = litter * (1 - cover[..., None]) + moss * cover[..., None]
            stone = np.clip(0.13 + 0.20 * macro - 0.18 * cover, 0, 0.38)
            c = (
                c * (1 - stone[..., None])
                + tone(s, [94.0, 94.0, 87.0], 0.82, 0.26) * stone[..., None]
            )
            # Bind visible coverage to actual clearance. The outer 30 cm of the mesh
            # lies underground; just above it, metre-scale scallops fade through centimetre-scale pores.
            toe = smooth(-0.015, 0.245, elev) * (1 - smooth(0.59, 0.95, radius))
            toe *= 0.83 + 0.17 * smooth(-0.5, 0.6, macro)
            toe = smooth(0.065, 0.76, toe + 0.12 * macro + 0.044 * grain)
            grain_mask = (
                0.48 * noise[sl]
                + 0.26
                * (0.5 + 0.5 * np.sin(49.1 * u + 34.9 * v + 1.3 * np.sin(9.4 * v)))
                + 0.26 * (0.5 + 0.5 * np.sin(26 * v - 17 * u + 2.7 * np.sin(7 * u)))
            )
            a = np.clip(0.5 + (toe - grain_mask) / 0.30, 0, 1)
            a = np.where((elev < -0.01) | (radius > 0.966), 0, a)
        mn = sample(stock["moss_n"], u, v, 1.41)[..., :2] / 127.5 - 1
        sn = (
            sample(stock["stone_n"], 1.14 * u + 0.17 * v, 0.98 * v - 0.20 * u, 1.51)[
                ..., :2
            ]
            / 127.5
            - 1
        )
        xy = (mn * (1 - stone[..., None]) + sn * stone[..., None]) * 0.91
        if i >= 4:
            relief = gaussian_filter(granite_lum, 1.15)
            gy, gx = np.gradient(relief)
            xy += np.stack((-gx, gy), axis=-1) * 0.025 * stone[..., None]
        xy = np.clip(xy, -0.89, 0.89)
        n = np.dstack((xy, np.sqrt(np.maximum(1.0 - (xy * xy).sum(-1), 0.012))))
        n /= np.linalg.norm(n, axis=-1, keepdims=True)
        color[sl] = np.dstack((np.clip(c, 0, 255), (255 * a))).astype(np.uint8)
        normal[sl] = np.round(255 * (n * 0.5 + 0.5)).astype(np.uint8)
        proof.append(
            dict(
                island=BANKS[i][0],
                opaque_fraction=float(np.mean(a > 0.5)),
                visible_mean_rgb=c[a > 0.5].mean(axis=0).tolist(),
            )
        )
    manifest = dict(
        revision=revision,
        granite_scan=sha256(granite),
        source={k: sha256(STOCK / f) for k, f in FILES.items()},
        images={},
        alpha_islands=proof,
    )
    for key, im in [("D", color), ("N", normal)]:
        path = OUT / f"bank-{key}.png"
        Image.fromarray(im).save(path, compress_level=3)
        manifest["images"][key] = dict(
            filename=path.name, sha256=sha256(path), size=[SIZE, SIZE]
        )
    save(OUT / "bank-textures.json", manifest)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--revision", type=int, choices=[17, 18], default=17)
    revision = parser.parse_args().revision
    OUT = SWEEP / f"round{revision}/verges"
    run(revision)
