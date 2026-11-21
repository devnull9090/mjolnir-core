"""flux_wrap_safe: border blends stay under ground, interior water is untouched, a second pass changes nothing."""
import json
from pathlib import Path

import numpy as np
import pytest

OpenEXR = pytest.importorskip("OpenEXR")
import flux_wrap_safe as fw  # noqa: E402


def state_files(root: Path):
    n, cz, capture = 16, 30000.0, 8000.0
    terrain = np.full((n, n), 90.0)           # m: a river valley floor...
    terrain[:3] = 130.0                       # ...under high ground along the far (row 0) edge
    surface = np.full((n, n), 92.0)           # wet interior
    surface[:3] = 107.0                       # dry fill over the high edge, as the bakes leave it
    height = np.zeros((n, n, 4), np.float32); height[..., 3] = 1
    height[..., 0] = height[..., 1] = surface * 100 - capture
    ground = np.zeros((n, n, 4), np.float32); ground[..., 3] = 1
    ground[..., 0] = cz - terrain * 100
    velocity = np.zeros((n, n, 4), np.float32); velocity[..., 3] = 1
    velocity[3:, :, 2] = 200                  # 2 m deep below the high edge
    st = {"centre": [0.0, 0.0, cz], "capture": capture, "res": [n, n], "cell": 100.0}
    (root / "flux_state/main").mkdir(parents=True)
    for key, arr in (("height", height), ("ground", ground), ("velocity", velocity)):
        st[key] = f"flux_state/main/{key}.exr"
        fw.write(root / st[key], arr)
    (root / "flux_state/main/state.json").write_text(json.dumps(st))
    (root / "level.json").write_text(json.dumps({"flux": {"domains": [{"id": "main", "state": st}]}}))
    return st, terrain


def test_borders_tucked_under_and_idempotent(tmp_path):
    st, terrain = state_files(tmp_path)
    before = fw.read(tmp_path / st["height"])
    assert fw.wrap_blend_above_ground(before, terrain, st) > 5      # the curtain the fix removes
    changed, report = fw.make_level_safe(tmp_path / "level.json", tmp_path)
    after = fw.read(tmp_path / st["height"])
    assert report[0]["border_blend_above_ground_m"]["after"] == 0.0
    assert fw.wrap_blend_above_ground(after, terrain, st) <= 0
    np.testing.assert_array_equal(after[2:-2, 2:-2], before[2:-2, 2:-2])  # interior untouched
    v = fw.read(tmp_path / st["velocity"])
    assert not v[:2, :, :3].any() and not v[:, -2:, :3].any()
    level = json.loads((tmp_path / "level.json").read_text())["flux"]["domains"][0]["state"]
    own = json.loads((tmp_path / "flux_state/main/state.json").read_text())
    assert level["height_sha256"] == own["height_sha256"] == fw.sha(tmp_path / st["height"])
    again, _ = fw.make_level_safe(tmp_path / "level.json", tmp_path)
    assert "flux_state/main/height.exr" not in again and "flux_state/main/velocity.exr" not in again
