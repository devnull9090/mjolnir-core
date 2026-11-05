"""Release modes must not require unpublished variant files."""
import copy
import importlib.util
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("tst_runtime", ROOT / "levels/test/tst/prepare_runtime.py")
runtime = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runtime)

class TstReleaseTests(unittest.TestCase):
    def setUp(self):
        self.placements = json.loads((ROOT / "levels/test/tst/placements.json").read_text())
        self.level = {"blam": {"objects": []}}
        for portal in self.placements["teleporters"]:
            x,y,z = portal["from_m"]
            self.level["blam"]["objects"].append({
                "tag": r"objects\multi\teleporters\teleporter_sender",
                "pos": [x*100,-y*100,z*100], "set": {}})

    def test_beta_removes_candidate_markers_and_is_idempotent(self):
        runtime.apply(self.level, self.placements)
        self.assertIn("oddball", self.level["modes"])
        runtime.apply(self.level, self.placements, release_beta=True)
        self.assertEqual(self.level["modes"], ["slayer", "ctf"])
        self.assertFalse(any(o["set"].get("multiplayer data.megalo label", "").startswith(
            ("oddball_", "koth_")) for o in self.level["blam"]["objects"]))
        snapshot = copy.deepcopy(self.level)
        runtime.apply(self.level, self.placements, release_beta=True)
        self.assertEqual(snapshot, self.level)
        senders = [o for o in self.level["blam"]["objects"] if "teleporter_sender" in o["tag"]]
        self.assertEqual(len(senders), len(self.placements["teleporters"])+2*sum(
            bool(p.get("shield_return")) for p in self.placements["teleporters"]))

    def test_alcove_radius_uses_metres_and_preserves_other_sender_bounds(self):
        for portal in self.placements["teleporters"]:
            if portal["channel"] in (2,3):
                portal["radius_m"] = .78
        runtime.apply(self.level, self.placements, release_beta=True)
        for portal in self.placements["teleporters"]:
            x,y,z = portal["from_m"]
            center = next(o for o in self.level["blam"]["objects"]
                          if o["pos"] == [x*100,-y*100,z*100])
            if portal["channel"] in (2,3):
                radius = float(center["set"]["multiplayer data.boundary width or radius"])
                self.assertAlmostEqual(radius*3.048,.78,places=7)
                # Only the upper wide return shields receive side senders.
                self.assertNotIn("multiplayer data.boundary positive height",center["set"])
            else:
                self.assertNotIn("multiplayer data.boundary width or radius",center["set"])
        snapshot = copy.deepcopy(self.level)
        runtime.apply(self.level, self.placements, release_beta=True)
        self.assertEqual(snapshot,self.level)

    def test_invalid_alcove_radius_is_rejected(self):
        for radius in (0,-1,float("nan"),float("inf")):
            with self.subTest(radius=radius):
                placements = copy.deepcopy(self.placements)
                next(p for p in placements["teleporters"] if p["channel"]==2)["radius_m"] = radius
                with self.assertRaisesRegex(ValueError,"radius_m must be finite and positive"):
                    runtime.apply(copy.deepcopy(self.level),placements,release_beta=True)

if __name__ == "__main__":
    unittest.main()
