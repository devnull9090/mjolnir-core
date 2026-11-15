import json
from pathlib import Path
import tempfile
import unittest

import numpy as np

from heightfield import write_heightfield
from pcg_pwr_inputs import project_master_candidates, write_requests


class MasterPCGInputTest(unittest.TestCase):
    def test_candidates_match_final_ground_and_exclusion_masks_deterministically(self):
        with tempfile.TemporaryDirectory() as folder:
            x, y = np.meshgrid(np.linspace(-315, 315, 64), np.linspace(-315, 315, 64))
            masks = {"road": (abs(x) < 30), "water": (y < -230), "shore": (y < -210),
                     "bases": ((x - 150) ** 2 + y ** 2 < 70 ** 2), "forest": np.ones_like(x),
                     "walkable": np.ones_like(x)}
            field = write_heightfield(Path(folder) / "master.json", 80 + .02 * x + .03 * y,
                                      (-315, -315), (10, 10), masks)
            first, stats = project_master_candidates(field, "tree", 25, 100)
            second, _ = project_master_candidates(field, "tree", 25, 100)
            self.assertEqual(first, second)
            self.assertAlmostEqual(stats["expected_selected"], 100, places=3)
            self.assertFalse(first["align_to_normal"])
            self.assertEqual(first["height_sha256"], field.metadata["height"]["sha256"])
            for point in first["points"]:
                x, y, z = point["position"]
                self.assertAlmostEqual(z, float(field.sample(x, y)), places=5)
                self.assertAlmostEqual(float(np.linalg.norm(point["normal"])), 1, places=6)
                if point["biome_mask"]:
                    self.assertLess(float(field.sample_mask("road", x, y)), .011)
                    self.assertLess(float(field.sample_mask("water", x, y)), .011)
                    self.assertLess(float(field.sample_mask("bases", x, y)), .011)
                else:
                    self.assertEqual(point["density"], 0)
            self.assertTrue(any(p["biome_mask"] == 0 for p in first["points"]))
            self.assertGreater(len({p["density"] for p in first["points"] if p["biome_mask"]}), 50)
            runtime = write_heightfield(Path(folder) / "runtime.json", field.heights_m + 2,
                                        field.origin_m, field.spacing_m, masks,
                                        surface_interpolation="triangle_nw_se")
            projected, _ = project_master_candidates(field, "tree", 25, 100, runtime)
            for before, after in zip(first["points"], projected["points"]):
                self.assertEqual(before["id"], after["id"])
                self.assertEqual(before["position"][:2], after["position"][:2])
                self.assertEqual(before["density"], after["density"])
                self.assertEqual(before["biome_mask"], after["biome_mask"])
                self.assertAlmostEqual(after["position"][2], before["position"][2] + 2, places=4)

    def test_requests_keep_native_conifer_palette_and_life_size_scale(self):
        with tempfile.TemporaryDirectory() as folder:
            repo = Path(folder)
            config = repo / "levels/warfare/pwr/upgrade.json"
            config.parent.mkdir(parents=True)
            palette = {"recipes": [{"recipe": "Pine_Optimized", "weight": 88},
                                    {"recipe": "Pine_Sapling_A", "weight": 12}]}
            config.write_text(json.dumps({"PWR": {"pcg_tree_palette": palette}}))
            out = repo / "out"; out.mkdir()
            write_requests(repo, out, out / "trees.json", out / "grass.json", 20568)
            actual = json.loads((out / "palette.json").read_text())
            self.assertEqual(actual["kinds"]["tree"], palette)
            jobs = json.loads((out / "request.json").read_text())["jobs"]
            self.assertEqual(len(jobs), 4)
            self.assertEqual((jobs[0]["scale_min"], jobs[0]["scale_max"]), (.7, 1.3))


if __name__ == "__main__":
    unittest.main()
