"""Numerical terrain checks, including the actual Gaea/site-plan build.

uv run --with numpy --with scipy==1.17.0 --with pillow python -m unittest discover -s levels/warfare/pwr/terrain -p test_finalize_terrain.py -v
"""
import copy
import json
from pathlib import Path
import tempfile
import unittest

import numpy as np

import finalize_terrain as terrain


class TerrainFinalizerTest(unittest.TestCase):
    def test_rounded_corner_preserves_endpoints_and_minimum_radius(self):
        points = [[0, 0], [100, 0], [100, 100]]
        curve, radius = terrain.rounded_road(points)
        np.testing.assert_array_equal(curve[[0, -1]], np.asarray(points)[[0, -1]])
        self.assertEqual(radius, 35)
        self.assertLessEqual(np.max(np.linalg.norm(np.diff(curve, axis=0), axis=1)), 2.001)
        self.assertLess(np.min(np.linalg.norm(curve - [100, 0], axis=1)), 15)
        self.assertTrue(np.all(curve[:, 0] >= 0) and np.all(curve[:, 1] >= 0))

    def test_water_curve_preserves_parent_junction(self):
        points = [[0, 200], [20, 100], [-10, 0], [50, -100]]
        curve = terrain.water_curve(points)
        for point in points:
            self.assertLess(np.min(np.linalg.norm(curve - point, axis=1)), 1e-10)

    def test_nearest_line_returns_continuous_height_interpolation(self):
        line = np.array([[0, 0, 100], [1, 0, 98], [2, 0, 96]], dtype=float)
        distance, index, fraction = terrain.nearest_line(np.array([[.5, 3], [1.25, 0]]), line)
        np.testing.assert_allclose(distance, [3, 0])
        np.testing.assert_allclose(line[index, 2] * (1 - fraction) + line[index + 1, 2] * fraction, [99, 97.5])

    def test_actual_build_is_reproducible_and_rejects_floating_road(self):
        existing = terrain.load_heightfield(terrain.HERE / "final-v3/final-master.json")
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "final-master.json"
            report = terrain.finalize(terrain.HERE / "gaea-v2/source.json", terrain.HERE / "site-plan-v3.json", output)
            built = terrain.load_heightfield(output)
            self.assertEqual(built.metadata["height"]["sha256"], existing.metadata["height"]["sha256"])
            np.testing.assert_array_equal(built.heights_m, existing.heights_m)
            self.assertTrue(report["water_downhill"])
            self.assertLess(report["validation"]["max_lane_grade"], .1)
            self.assertLess(report["validation"]["max_road_alignment_error_m"], .01)
            self.assertTrue(all(15 < c["freeboard_m"] < 25 for c in report["validation"]["crossings"]))
            geometry = json.loads((Path(folder) / "terrain.geometry.json").read_text())
            bad = copy.deepcopy(geometry)
            road = next(r for r in bad["roads"] if not r.get("structure"))
            road["centreline_m"][5][2] += 2
            with self.assertRaisesRegex(ValueError, "floats"):
                terrain.validate_geometry(built, bad)
            bad = copy.deepcopy(geometry)
            bad["watercourses"][0]["surface_centreline_m"][10][2] += 30
            with self.assertRaisesRegex(ValueError, "uphill"):
                terrain.validate_geometry(built, bad)


if __name__ == "__main__":
    unittest.main()
