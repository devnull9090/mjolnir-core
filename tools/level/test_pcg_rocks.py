import json
import math
from pathlib import Path
import tempfile
import unittest

import pcg_foliage
import pcg_rocks


class PCGRockExportTest(unittest.TestCase):
    def fixture(self, root):
        source = {"points": [{"id": 9, "position": [10, -20, 100], "density": 1, "biome_mask": 1}]}
        (root / "source.json").write_text(json.dumps(source))
        generated = {"schema": 1, "generator": "UE5.5 UPCGGraph / fixture", "graph": "/RockGraph", "seed": 3,
                     "input_count": 1, "source_sha256": pcg_foliage.digest(root / "source.json"), "points": [
                         {"id": 9, "position_cm": [1000, 2000, 10000],
                          "rotation_xyzw": [0, 0, math.sin(math.pi / 8), math.cos(math.pi / 8)],
                          "scale_xyz": [.8] * 3, "asset_draw": .1}]}
        (root / "generated.json").write_text(json.dumps(generated))
        (root / "assets.json").write_text(json.dumps({"glacial_rocks": [
            {"mesh": "/Game/Env/Bio/Rock/Glacial/Rock_A", "bounds_cm": {"min": [-100, -100, -50],
                                                                       "max": [100, 100, 350]}}]}))

    def test_actor_and_hull_share_grounding_offset_without_duplicate_foliage(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); self.fixture(root)
            pcg_rocks.export(root / "source.json", root / "generated.json", root / "assets.json", root / "decor.json")
            out = json.loads((root / "decor.json").read_text())
            rock = out["decor"][0]
            self.assertEqual(rock["id"], "pcg_rock_9")
            self.assertEqual(rock["pos"], [1000, 2000, 9976])  # (-minZ -20%height) *scale
            self.assertAlmostEqual(rock["rot"][1] % 360, 45)
            self.assertEqual(rock["scale"], [.8] * 3)
            self.assertTrue(rock["static"])
            self.assertEqual(out["background_trees"], [])
            self.assertEqual(list(root.glob("*.bin")), [])
            self.assertFalse(json.loads((root / "decor.receipt.json").read_text())["cladding_reach_lookup"])

    def test_changed_candidates_are_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); self.fixture(root)
            (root / "source.json").write_text('{"points": []}')
            with self.assertRaisesRegex(ValueError, "changed"):
                pcg_rocks.export(root / "source.json", root / "generated.json", root / "assets.json", root / "decor.json")
            self.assertFalse((root / "decor.json").exists())


if __name__ == "__main__":
    unittest.main()
