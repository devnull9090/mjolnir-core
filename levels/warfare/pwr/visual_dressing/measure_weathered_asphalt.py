"""Measure the same near-field pavement, shoulder and outside soil in two native release captures."""

import argparse
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "tools/level"))
from heightfield import load_heightfield
from verify_weathered_asphalt import GEOMETRY, section

LUMA = np.array([0.2126, 0.7152, 0.0722])


def project(points, pose):
    eye = np.array(pose[:3]) * [0.01, -0.01, 0.01]
    pitch, yaw, fov = np.radians(pose[3:])
    h = np.array([np.cos(yaw), -np.sin(yaw)])
    fw = np.r_[np.cos(pitch) * h, np.sin(pitch)]
    right = np.array([-np.sin(yaw), -np.cos(yaw), 0])
    up = np.r_[-h * np.sin(pitch), np.cos(pitch)]
    rel = points - eye
    d = rel @ fw
    lens = 800 / np.tan(fov / 2)
    return np.stack(
        [800 + lens * (rel @ right) / d, 450 - lens * (rel @ up) / d], axis=1
    ), d


def masks(site, road, field):
    start = site["station_m"]
    stations = start + np.linspace(3.6, 24.0, 60)
    side = np.sign(site["offset_m"])
    output = {}
    for name, low, high in (
        ("asphalt", 0.9, 7.3),
        ("edge", 7.7, 9.2),
        ("gravel", 9.45, 11.75),
        ("outside", 14.25, 16.5),
    ):
        xy = section(road, stations, side * np.array([low, high]))
        z = field.sample(xy[:, :, 0], xy[:, :, 1])
        flat = np.dstack([xy, z]).reshape(-1, 3)
        pix, depth = project(flat, site["pose"])
        edge = pix.reshape(-1, 2, 2)
        im = Image.new("L", (1600, 900))
        drawer = ImageDraw.Draw(im)
        for i in range(len(stations) - 1):
            if depth[i * 2 : i * 2 + 4].min() < 1:
                continue
            q = np.array([edge[i, 0], edge[i + 1, 0], edge[i + 1, 1], edge[i, 1]])
            drawer.polygon([tuple(v) for v in q], fill=255)
        mask = np.asarray(im) > 0
        mask[:410] = False
        output[name] = mask
    return output


def run(art, reference, candidate=None):
    roads = {r["id"]: r for r in json.loads(GEOMETRY.read_text())["roads"]}
    field = load_heightfield(
        ROOT / "levels/warfare/pwr/terrain/runtime-v5/runtime-master.json"
    )
    poses = json.loads((art / "paved/survey.json").read_text())["sites"]
    images = {}
    summary = {}
    for route in ("primary", "secondary"):
        zones = masks(poses[route], roads[poses[route]["route"]], field)
        summary[route] = {}
        final_name = route + ".png"
        warmed = (reference / final_name).exists() and (
            candidate is None or (candidate / final_name).exists()
        )
        shot = final_name if warmed else route + "-early.png"
        sources = {"before": reference / shot}
        if candidate is not None:
            sources["after"] = candidate / shot
        if route == "primary":
            sources["reference_image"] = (
                ROOT / ".dream-loop/alpine-valley-pwr13/asphalt/target.png"
            )
        for series, path in sources.items():
            rgb = (
                Image.open(path)
                .convert("RGB")
                .resize((1600, 900), Image.Resampling.LANCZOS)
            )
            values = np.asarray(rgb, dtype=float)
            lum = values @ LUMA
            soft = (
                np.asarray(rgb.filter(ImageFilter.GaussianBlur(2.0)), dtype=float)
                @ LUMA
            )
            rows = {}
            for name, mask in zones.items():
                v = values[mask]
                avg = lum[mask]
                rows[name] = {
                    "pixels": int(mask.sum()),
                    "median_rgb": np.median(v, axis=0).astype(int).tolist(),
                    "median_luma": round(float(np.median(avg)), 2),
                    "luma_p10_p90": np.percentile(avg, [10, 90]).round(2).tolist(),
                    "fine_contrast_q80": round(
                        float(np.percentile(abs(lum - soft)[mask], 80)), 2
                    ),
                }
            if route == "primary":
                for label, bounds in (
                    ("near_charcoal", (632, 608, 1344, 856)),
                    ("approach_charcoal", (792, 472, 1192, 556)),
                    ("outside_soil", (184, 568, 336, 648)),
                ):
                    left, top, right, bottom = bounds
                    cell = values[top:bottom, left:right]
                    rows[label] = {
                        "box": list(bounds),
                        "median_rgb": np.median(cell, axis=(0, 1)).astype(int).tolist(),
                        "median_luma": round(float(np.median(cell @ LUMA)), 2),
                    }
            summary[route][series] = {
                "image_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "regions": rows,
            }
            images[series, route] = rgb
    output = (
        art
        / "paved"
        / ("native-comparison.json" if candidate else "native-baseline.json")
    )
    output.write_text(json.dumps(summary, indent=2) + "\n")
    if candidate:
        sheet = Image.new("RGB", (1000, 614), "#1b2224")
        draw = ImageDraw.Draw(sheet)
        for i, series in enumerate(("before", "after")):
            for j, key in enumerate(("primary", "secondary")):
                tile = images[series, key].resize((500, 281), Image.Resampling.LANCZOS)
                x, y = j * 500, i * 307
                sheet.paste(tile, (x, y + 22))
                draw.text((x + 6, y + 5), key + " - " + series, fill="white")
        sheet.save(art / "paved/native-before-after.jpg", quality=94)
    print(output)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("art", type=Path)
    parser.add_argument("reference", type=Path)
    parser.add_argument("candidate", type=Path, nargs="?")
    args = parser.parse_args()
    run(args.art, args.reference, args.candidate)
