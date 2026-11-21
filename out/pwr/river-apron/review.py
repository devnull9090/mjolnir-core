"""Validate the registered captures and make comparison sheets from the two live maps."""
import argparse
from pathlib import Path
import sys

from PIL import Image, ImageDraw, ImageFont
import numpy as np

WORK = Path(__file__).resolve().parent
BENCH = WORK.parent / "alpine-target/bench"
sys.path.insert(0, str(BENCH))
import benchmark as b


def sheet(path, before, after, name, title):
    panel = Image.new("RGB", (1944, 616), (22, 26, 26))
    draw = ImageDraw.Draw(panel)
    large = ImageFont.truetype("C:/Windows/Fonts/seguisb.ttf", 25)
    small = ImageFont.truetype("C:/Windows/Fonts/segoeui.ttf", 18)
    for i, data in enumerate((before, after)):
        version = "." + data["release"]["archive"].removesuffix(".mjolnir").rsplit(".", 1)[-1]
        x = 10 + i * 968
        draw.text((x + 2, 6), title, font=large, fill=(235, 239, 229))
        draw.text((x + 3, 38), "Pelican Warfare  " + version, font=small, fill=(174, 188, 181))
        with Image.open(data["frames"][name]["file"]) as image:
            b.check(image.size == (1600, 900), "Unexpected capture resolution")
            panel.paste(image.convert("RGB").resize((956, 538), Image.Resampling.LANCZOS), (x, 68))
    panel.save(path, quality=94, subsampling=0)


def expansion_readback(candidate_work, before_dir, after_dir):
    """Measure actual surface visibility where the two banks moved outward."""
    def surface_contrast(folder):
        arrays = []
        for mode in ("on", "off"):
            with Image.open(folder / "water" / ("surface-" + mode + ".png")) as image:
                arrays.append(np.asarray(image.convert("RGB"), dtype=np.int16))
        return np.abs(arrays[0] - arrays[1]).mean(axis=2)
    before, after = [surface_contrast(folder) for folder in (before_dir, after_dir)]
    survey = b.read(candidate_work / "terrain/headwater-terrain.receipt.json")
    samples = []
    for row in survey["camera_rows"]:
        y = row["y"]
        for side, (left,right) in enumerate(zip(row["native"], row["previous"])):
            lo,hi = sorted((left,right))
            if hi - lo < 32:
                continue
            xs = slice(lo+10,hi-10)
            ys = slice(y-1,y+2)
            samples.append({"y_px":y, "side":("left","right")[side], "x_span": [xs.start,xs.stop],
                            "before_median":float(np.median(before[ys,xs])),
                            "after_median":float(np.median(after[ys,xs])),
                            "before_frac_gt8":float((before[ys,xs]>8).mean()), "after_frac_gt8":float((after[ys,xs]>8).mean())})
    return {"method":"Matched render with upper native water visible and hidden on each map, measured in newly wetted strips away from the predicted shore. Median absolute 8-bit sRGB difference.",
            "before_release":b.read(before_dir/"water/photos.json")["release"], "samples":samples}


def run(args):
    before_dir = BENCH / args.before
    after_dir = BENCH / args.label
    control_dir = BENCH / args.control
    candidate_work = WORK.parent / "river-basin" if args.version in ("38", "39") else WORK
    released = candidate_work / ("saturday." + args.version)
    release = b.read(released / "receipt.json")
    physical_release = b.read(WORK / "saturday.36/receipt.json")
    before, after = (b.read(d / "water/photos.json") for d in (before_dir, after_dir))
    chain = {physical_release["baseline_sha256"], physical_release["sha256"]}
    if args.version in ("38", "39"):
        finished = b.read(WORK / "saturday.37/receipt.json")
        basin = b.read(candidate_work / "saturday.38/receipt.json")
        b.check(finished["baseline_sha256"] == physical_release["sha256"] and basin["baseline_sha256"] == finished["sha256"],
                "Different lake and outlet lineage")
        chain.add(finished["sha256"])
        if args.version == "39":
            chain.add(basin["sha256"])
            b.check(release["baseline_sha256"] == basin["sha256"], "Contact finish parent mismatch")
    b.check(before["release"]["map_sha256"] in chain and release["baseline_sha256"] in chain and
            after["release"]["map_sha256"] == release["sha256"] == b.sha(released / release["archive"]),
            "Registered captures are from different releases")
    b.check(before["settings"] == after["settings"], "Different game settings")
    for name, frame in after["frames"].items():
        b.check(after["views"][name] == before["views"][name], "Camera moved at " + name)
        for original in (frame, before["frames"][name]):
            b.check(b.sha(original["file"]) == original["sha256"], "Modified capture " + name)
    for d in (before_dir, control_dir, after_dir):
        b.check(b.read(d / "steam/restored.json")["restored"] and b.read(d / "visual-profile-restored.json")["byte_verified"],
                "Install or preferences did not restore")
    for key, marker in (("terrain", "HEADWATER_LANDSCAPE_ACCEPTANCE PASS"), ("water", "HEADWATER_TEXEL_ACCEPTANCE PASS"),
                        ("painter", "JOIN_PAINTER_ACCEPTANCE PASS")):
        b.check(marker in (after_dir / "water" / (key + ".log")).read_text(), "Failed " + key)
    if args.version in ("37", "38", "39"):
        b.check("PWR_WAVE_RELEASE PASS" in (after_dir / "water/detail-wave-shipped.log").read_text(),
                "The shipped surface did not read back its approved normal height")
    a, z = (b.read(d / "water/native-performance.json") for d in (control_dir, after_dir))
    for key in ["settings", "camera", "module_sha256"]:
        b.check(a[key] == z[key], "Unmatched timing " + key)
    b.check(b.read(control_dir / "benchmark.json")["release"] == before["release"], "Timing control differs from before image")
    out = candidate_work / args.out
    out.mkdir(exist_ok=True)
    sheet(out / "lake-outlet-before-after.jpg", before, after, "outlet", "Lake outlet")
    sheet(out / "water-level-before-after.jpg", before, after, "riffle", "Water level")
    if args.version in ("38", "39"):
        sheet(out / "headwater-basin-before-after.jpg", before, after, "basin", "Headwater lake")
    survey = b.read(WORK / "dressing/apron-survey.json")
    water_frames = []
    for mode in ("on", "off"):
        with Image.open(after_dir / "water" / ("surface-" + mode + ".png")) as img:
            water_frames.append(np.asarray(img.convert("RGB"), dtype=np.int16))
    difference = np.abs(water_frames[0] - water_frames[1]).mean(axis=2)
    contrast = {}
    # These fixed regions are clear of the three emergent boulder crowns.
    for name, (x1,y1,x2,y2) in {"central_shallow_bed": (540,805,1050,895), "upper_basin": (700,470,880,502),
                                "distant_static_ridge_control": (630,195,900,270)}.items():
        region = difference[y1:y2, x1:x2]
        contrast[name] = {"box_xyxy": [x1,y1,x2,y2], "median_absolute_rgb_difference": float(np.median(region)),
                          "fraction_with_mean_rgb_difference_over_8": float((region > 8).mean())}
    b.check("PWR_EDGE_RESTORED PASS" in (after_dir / "water/surface-control-restored.log").read_text(),
            "Water visibility control did not restore")
    extras = {}
    if args.version in ("38", "39"):
        extras["rendered_basin_shores_vs_37"] = expansion_readback(candidate_work, BENCH / "river-apron-37", after_dir)
    if args.version == "39":
        b.check("PWR_SHORE_FOLIAGE PASS" in (after_dir / "water/shore-planting.log").read_text(),
                "Shoreline foliage was not verified in game")
    b.write(out / "results.json", dict(baseline_map=before["release"]["map_sha256"], candidate_map=release["sha256"],
            poses={k: after["views"][k] for k in after["frames"]}, actual_frames=after["frames"], settings=z["settings"],
            native_performance_before_after=[a["aggregate"],z["aggregate"]], offline_waterline_scanlines=survey["camera_rows"],
            protected_road_and_base_vertices=b.read(candidate_work / "terrain/headwater-terrain.receipt.json")["untouched_road_and_base_vertices"],
            matched_water_on_off_render=contrast, game_water_landscape_painter_verified=True,
            install_and_preferences_restored=True, **extras))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--label", default="river-apron-36")
    parser.add_argument("--control", default="river-apron-perf-35")
    parser.add_argument("--version", default="36")
    parser.add_argument("--before", default="river-shore-35")
    parser.add_argument("--out", default="review")
    run(parser.parse_args())
