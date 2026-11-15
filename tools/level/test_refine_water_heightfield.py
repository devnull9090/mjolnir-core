"""Local-elevation water bakes; no Unreal or installed-map writes."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

import numpy as np

from heightfield import load_heightfield
from refine_water_gltf import bake_shore, euclidean_distance_to, read_accessor


class HeightfieldWaterTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def field(self, values, spacing=1):
        values = np.asarray(values, dtype="<f4")
        p = self.root / "master.npy"
        np.save(p, values)
        spec = {"schema": "pwr-heightfield-v1", "coordinates": "authoring_metres_z_up",
                "origin_m": [0, 0], "spacing_m": [spacing, spacing],
                "dimensions": list(values.shape[::-1]), "row_order": "+y",
                "surface_interpolation": "triangle_nw_se",
                "height": {"path": p.name, "encoding": "float32_npy", "offset_m": 0, "scale_m": 1,
                           "sha256": hashlib.sha256(p.read_bytes()).hexdigest()}}
        manifest = self.root / "master.json"
        manifest.write_text(json.dumps(spec), encoding="utf-8")
        return manifest

    def water(self, xy, elevations, triangles, name="water"):
        xy = np.asarray(xy, dtype=float)
        pos = np.column_stack([xy[:, 0], np.broadcast_to(elevations, len(xy)), -xy[:, 1]]).astype("<f4")
        arrays = [pos, np.zeros((len(pos), 2), dtype="<f4"), np.asarray(triangles, dtype="<u4").reshape(-1)]
        views, acc, blob = [], [], b""
        for values, typ in zip(arrays, ["VEC3", "VEC2", "SCALAR"]):
            views.append({"buffer": 0, "byteOffset": len(blob), "byteLength": values.nbytes})
            acc.append({"bufferView": len(views) - 1, "componentType": 5126 if typ != "SCALAR" else 5125,
                        "count": len(values), "type": typ})
            blob += values.tobytes()
        path = self.root / (name + ".gltf")
        doc = {"asset": {"version": "2.0"}, "nodes": [{"mesh": 0}], "scenes": [{"nodes": [0]}], "scene": 0,
               "buffers": [{"uri": name + ".bin", "byteLength": len(blob)}], "bufferViews": views,
               "accessors": acc, "meshes": [{"primitives": [{"attributes": {"POSITION": 0, "TEXCOORD_1": 1}, "indices": 2}]}]}
        path.with_suffix(".bin").write_bytes(blob)
        path.write_text(json.dumps(doc), encoding="utf-8")
        return path, pos

    def output(self, path):
        doc = json.loads(path.read_text(encoding="utf-8"))
        blob = (path.parent / doc["buffers"][0]["uri"]).read_bytes()
        return read_accessor(doc, blob, 1), read_accessor(doc, blob, 0)

    def test_exact_euclidean_grid_distance(self):
        mask = np.zeros((11, 13), dtype=bool)
        mask[1, 2] = mask[9, 10] = True
        y, x = np.indices(mask.shape)
        expected = np.minimum(np.hypot(y - 1, x - 2), np.hypot(y - 9, x - 10)) * 1.7
        np.testing.assert_allclose(euclidean_distance_to(mask, 1.7, 100), expected, atol=1e-12)
        np.testing.assert_array_equal(euclidean_distance_to(np.zeros((3, 4), dtype=bool), 1, 8), 8)

    def test_local_water_levels_triangle_depth_and_unchanged_positions(self):
        manifest = self.field([[0, 0], [0, 8]])
        xy = [[0, 0], [1, 0], [1, 1], [0, 1], [.25, .25]]
        path, before = self.water(xy, [2, 3, 4, 3, 2.5], [[0, 1, 4], [1, 2, 4], [2, 3, 4], [3, 0, 4]])
        sea, _, _, count = bake_shore(path, heightfield=manifest, cell=.1)
        self.assertIsNone(sea)
        self.assertEqual(count, 5)
        uv, pos = self.output(path)
        expected = np.maximum(0, before[:, 1] - load_heightfield(manifest).sample(before[:, 0], -before[:, 2]))
        np.testing.assert_allclose(uv[:, 1], expected, atol=1e-6)
        self.assertEqual(float(uv[4, 1]), 2.5)  # Bilinear terrain would incorrectly subtract 0.5.
        self.assertEqual(float(uv[2, 0]), 0)  # Occluded/dry vertex.
        np.testing.assert_array_equal(pos, before)
        receipt = json.loads(path.with_suffix(".shore.json").read_text())
        self.assertEqual(receipt["surface_interpolation"], "triangle_nw_se")
        self.assertLess(receipt["depth_float32_max_error_m"], 1e-6)

    def test_island_and_footprint_edges_are_shore(self):
        values = np.zeros((21, 21), dtype="<f4")
        values[8:13, 8:13] = 12
        manifest = self.field(values)
        # A lake covers the square; the dry central terrain must form an island.
        path, _ = self.water([[0, 0], [20, 0], [20, 20], [0, 20], [10, 10], [6, 10], [1, 10]],
                             10, [[0, 1, 4], [1, 2, 4], [2, 3, 4], [3, 0, 4]])
        bake_shore(path, heightfield=manifest, cell=.5)
        uv, _ = self.output(path)
        self.assertEqual(float(uv[4, 0]), 0)
        self.assertEqual(float(uv[4, 1]), 0)
        self.assertLess(float(uv[5, 0]), 2.6)  # Shore is the island, not the outer edge 6m away.
        self.assertLessEqual(float(uv[6, 0]), 1.5)  # Authored footprint edge with no terrain intersection.

    def test_mismatched_frame_and_changed_hash_fail_before_writes(self):
        manifest = self.field(np.zeros((3, 3)))
        path, _ = self.water([[0, 0], [2, 0], [0, 2]], 1, [[0, 1, 2]])
        before = path.with_suffix(".bin").read_bytes()
        doc = json.loads(path.read_text())
        doc["nodes"][0]["translation"] = [1, 0, 0]
        path.write_text(json.dumps(doc), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "transforms applied"):
            bake_shore(path, heightfield=manifest)
        self.assertEqual(before, path.with_suffix(".bin").read_bytes())
        doc["nodes"][0].pop("translation")
        path.write_text(json.dumps(doc), encoding="utf-8")
        np.save(self.root / "master.npy", np.ones((3, 3), dtype="<f4"))
        with self.assertRaisesRegex(ValueError, "SHA-256 mismatch"):
            bake_shore(path, heightfield=manifest)
        self.assertEqual(before, path.with_suffix(".bin").read_bytes())

    def test_legacy_bake_keeps_scalar_sea_contract(self):
        path, _ = self.water([[0, 0], [10, 0], [10, 10], [0, 10]], 3, [[0, 1, 2], [0, 2, 3]])
        terrain, _ = self.water([[-10, -10], [20, -10], [20, 20], [-10, 20]], 0, [[0, 1, 2], [0, 2, 3]], name="ground")
        doc = json.loads(terrain.read_text())
        doc["accessors"][0].update(min=[-10, 0, -20], max=[20, 0, 10])
        terrain.write_text(json.dumps(doc), encoding="utf-8")
        sea, _, shallow, count = bake_shore(path, terrain)
        self.assertEqual((sea, shallow, count), (3, 0, 4))
        np.testing.assert_allclose(self.output(path)[0][:, 1], 3)
        self.assertFalse(path.with_suffix(".shore.json").exists())


if __name__ == "__main__":
    unittest.main()
