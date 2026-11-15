"""Calibrate a successful Gaea UI build into a versioned PWR source field."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--variant", default="v5b")
    p.add_argument("--datum", type=float, default=70)
    p.add_argument("--height-range", type=float, default=400)
    a = p.parse_args()
    source = ROOT / ("out/pwr/gaea-world-" + a.variant)
    graph = HERE / ("pwr_world_native_" + a.variant + ".terrain")
    report = json.loads((source / "report.json").read_text())
    if report["Result"] != "Success" or report["Resolution"] != 1024:
        raise ValueError("Requires a successful 1024-square Gaea build")
    raw = np.fromfile(source / "pwr_height.r32", dtype="<f4").reshape(1024, 1024)
    if not np.isfinite(raw).all() or raw.min() < 0 or raw.max() > 1:
        raise ValueError("Invalid normalized Gaea height output")
    heights = (a.datum + np.flipud(raw) * a.height_range).astype("float32")
    if not np.isfinite(heights).all():
        raise ValueError("Invalid height calibration")
    out = HERE / ("gaea-" + a.variant)
    out.mkdir(exist_ok=True)
    np.save(out / "source.heights.npy", heights)
    shutil.copy2(source / "pwr_height.r32", out / "height.r32")
    shutil.copy2(source / "report.json", out / "build-report.json")
    manifest = {
        "schema": "pwr-heightfield-v1", "coordinates": "authoring_metres_z_up",
        "source_tool": "Gaea 2.3.1.0 Community", "source_build_report": "build-report.json",
        "source_graph": "../" + graph.name, "source_graph_sha256": digest(graph),
        "source_r32_sha256": digest(out / "height.r32"),
        "normalization": "North-first R32 flipped to +Y rows; explicit datum plus height range",
        "calibration": {"datum_m": a.datum, "height_range_m": a.height_range},
        "status": "Native Gaea landforms; constrained gameplay earthworks pending",
        "origin_m": [-1000, -1000], "spacing_m": [2000/1023, 2000/1023],
        "dimensions": [1024, 1024], "row_order": "+y",
        "height": {"path": "source.heights.npy", "encoding": "float32_npy",
                   "offset_m": 0, "scale_m": 1, "sha256": digest(out / "source.heights.npy")},
        "masks": {},
    }
    (out / "source.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps({"manifest": str(out / "source.json"),
                      "min_m": float(heights.min()), "max_m": float(heights.max())}))


if __name__ == "__main__":
    main()
