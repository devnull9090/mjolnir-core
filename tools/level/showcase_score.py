"""Score before/after screenshots of the B30 pipeline, view by view.

    python tools/level/showcase_score.py <showcase dir> [--after after]

For each <map>/before_<view>.png with an <map>/<after>_<view>.png beside it,
measured over the frame below the horizon band (the top quarter, mostly
sky, is left out):

  detail    mean local contrast (luma's absolute Laplacian): texture and
            relief on the ground and rock; up is better
  palette   the mean colour's distance (Lab ΔE) from the original's: the
            map should still read as itself; under 12 is close
  crushed   share of near-black pixels (luma < 0.04); a rise means shade
            went black
  blue      mean b* below 0 in the shade (luma < 0.25): a blue cast; more
            negative is bluer

and a verdict per view. Writes <showcase dir>/scores.json too.
"""
import argparse
import glob
import json
import os

import numpy as np
from PIL import Image


def load(path):
    img = np.asarray(Image.open(path).convert("RGB"), dtype=np.float32) / 255.0
    h = img.shape[0]
    return img[h // 4:]


def lab(rgb):
    lin = np.where(rgb <= 0.04045, rgb / 12.92, ((rgb + 0.055) / 1.055) ** 2.4)
    m = np.array([[0.4124, 0.3576, 0.1805], [0.2126, 0.7152, 0.0722], [0.0193, 0.1192, 0.9505]])
    xyz = lin @ m.T / np.array([0.9505, 1.0, 1.089])
    f = np.where(xyz > 0.008856, np.cbrt(xyz), 7.787 * xyz + 16 / 116)
    return np.stack([116 * f[..., 1] - 16, 500 * (f[..., 0] - f[..., 1]), 200 * (f[..., 1] - f[..., 2])], -1)


def metrics(img):
    y = img @ np.array([0.2126, 0.7152, 0.0722])
    lap = np.abs(4 * y[1:-1, 1:-1] - y[:-2, 1:-1] - y[2:, 1:-1] - y[1:-1, :-2] - y[1:-1, 2:])
    L = lab(img)
    shade = y < 0.25
    return {"detail": float(lap.mean()), "mean_lab": L.reshape(-1, 3).mean(0).tolist(),
            "crushed": float((y < 0.04).mean()),
            "blue": float(L[..., 2][shade].mean()) if shade.any() else 0.0}


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("dir")
    ap.add_argument("--after", default="after")
    a = ap.parse_args()
    out = {}
    for before in sorted(glob.glob(os.path.join(a.dir, "*", "before_*.png"))):
        code = os.path.basename(os.path.dirname(before))
        view = os.path.basename(before)[len("before_"):-4]
        after = os.path.join(os.path.dirname(before), f"{a.after}_{view}.png")
        if not os.path.exists(after):
            continue
        b, f = metrics(load(before)), metrics(load(after))
        de = float(np.linalg.norm(np.array(b["mean_lab"]) - np.array(f["mean_lab"])))
        gain = f["detail"] / max(b["detail"], 1e-6)
        notes = []
        if gain < 1.05:
            notes.append("little new detail")
        if de > 12:
            notes.append("palette drifted")
        if f["crushed"] > b["crushed"] + 0.03:
            notes.append("shade crushed")
        if f["blue"] < b["blue"] - 4:
            notes.append("bluer shade")
        out[f"{code}/{view}"] = {"detail_gain": round(gain, 2), "palette_dE": round(de, 1),
                                 "crushed": [round(b["crushed"], 3), round(f["crushed"], 3)],
                                 "blue": [round(b["blue"], 1), round(f["blue"], 1)], "notes": notes}
        print(f"{code:4s} {view:10s} detail x{gain:4.2f}  palette dE {de:5.1f}  "
              f"crushed {b['crushed']:.3f}->{f['crushed']:.3f}  blue {b['blue']:5.1f}->{f['blue']:5.1f}  "
              f"{'; '.join(notes) or 'ok'}")
    json.dump(out, open(os.path.join(a.dir, "scores.json"), "w", encoding="utf-8"), indent=1)


if __name__ == "__main__":
    main()
