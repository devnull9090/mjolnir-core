"""Prove every triangle that can support a pre-existing exterior actor retained its height."""

import argparse
import json
from pathlib import Path
import numpy as np
from scipy.spatial import cKDTree

from build_survey_ridges import GROUND, OLD, ORIGINAL_CLIFFS, sha256


def verify(out):
    before = np.load(OLD)["vertices_m"]
    after = np.load(out / "apron.source.npz")["vertices_m"]
    if not np.array_equal(before[:, :2], after[:, :2]):
        raise ValueError("Vertex positions or ordering changed")
    limit = json.loads((out / "receipt.json").read_text())["maximum_horizontal_edge_m"]
    readback = json.loads((out / "roundtrip.verification.json").read_text())
    contacts = json.loads(GROUND.read_text())
    contacts["cliffs"].extend(json.loads(ORIGINAL_CLIFFS.read_text())["checks"])
    tree = cKDTree(after[:, :2])
    output = {}
    total = 0
    for group, rows in contacts.items():
        max_error = 0
        for row in rows:
            a, b = np.asarray(row["bounds_ue_cm"])[:, :2] * [0.01, -0.01]
            # A vertex of a triangle crossing the object's bounds lies within
            # one maximum projected edge length of that bounding rectangle.
            lo, hi = np.minimum(a, b) - limit, np.maximum(a, b) + limit
            ids = np.array(
                tree.query_ball_point((lo + hi) / 2, np.linalg.norm(hi - lo) / 2)
            )
            inside = np.all((after[ids, :2] >= lo) & (after[ids, :2] <= hi), axis=1)
            ids = ids[inside]
            if not len(ids):
                raise ValueError(row["id"] + " has no supporting vertices")
            total += len(ids)
            max_error = max(
                max_error, float(np.abs(before[ids, 2] - after[ids, 2]).max())
            )
        if max_error != 0:
            raise ValueError(f"{group} support changed by {max_error} metres")
        output[group] = {
            "assets": len(rows),
            "maximum_authored_height_delta_m": max_error,
        }
    result = {
        "subjects": output,
        "vertex_comparisons": total,
        "maximum_native_readback_error_m": readback["native_max_position_error_m"],
        "geometry_sha256": sha256(out / "receipt.json"),
        "roundtrip_sha256": sha256(out / "roundtrip.verification.json"),
    }
    (out / "contact.verification.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("out", type=Path)
    verify(p.parse_args().out)
