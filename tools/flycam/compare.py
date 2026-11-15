#!/usr/bin/env python3
"""Compare two folders of FlyCam captures (tools/flycam/capture.mjs).

    python tools/flycam/compare.py <before-dir> <after-dir> [--side-by-side <out-dir>]

For every shot image in both folders, prints the mean absolute difference per
channel (0-255) and the share of pixels that differ by more than 16 on any
channel. Two captures of the same build should read close to zero, apart from
moving things (water, foliage, particles, sky). With --side-by-side, writes
before|after images for review.
"""
import argparse
import pathlib
import sys

import numpy as np
from PIL import Image


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("before", type=pathlib.Path)
    parser.add_argument("after", type=pathlib.Path)
    parser.add_argument("--side-by-side", type=pathlib.Path)
    args = parser.parse_args()

    names = sorted(p.name for p in args.before.glob("shot*.png") if (args.after / p.name).exists())
    if not names:
        print("no shot images in common", file=sys.stderr)
        return 1
    if args.side_by_side:
        args.side_by_side.mkdir(parents=True, exist_ok=True)
    print(f"{'shot':40} {'mean diff':>10} {'pixels >16':>11}")
    for name in names:
        a = Image.open(args.before / name).convert("RGB")
        b = Image.open(args.after / name).convert("RGB")
        if a.size != b.size:
            print(f"{name:40} size differs: {a.size} vs {b.size}")
            continue
        da = np.asarray(a, dtype=np.int16)
        db = np.asarray(b, dtype=np.int16)
        diff = np.abs(da - db)
        mean = float(diff.mean())
        changed = float((diff.max(axis=2) > 16).mean()) * 100.0
        print(f"{name:40} {mean:10.2f} {changed:10.2f}%")
        if args.side_by_side:
            pair = Image.new("RGB", (a.width * 2, a.height))
            pair.paste(a, (0, 0))
            pair.paste(b, (a.width, 0))
            pair.save(args.side_by_side / name)
    return 0


if __name__ == "__main__":
    sys.exit(main())
