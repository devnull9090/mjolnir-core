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
            if portal.get("shield_return"):
                x,y,z = portal["from_m"]
                self.level["blam"]["objects"].append({
                    "tag": r"objects\multi\teleporters\teleporter_sender",
                    "pos": [x*100,-y*100,z*100], "set": {}})

    def test_beta_removes_candidate_markers_and_is_idempotent(self):
        runtime.apply(self.level, self.placements)
        self.assertIn("oddball", self.level["modes"])
        runtime.apply(self.level, self.placements, release_beta=True)
        self.assertEqual(self.level["modes"], ["slayer", "team_slayer", "ctf"])
        self.assertFalse(any(o["set"].get("multiplayer data.megalo label", "").startswith(
            ("oddball_", "koth_")) for o in self.level["blam"]["objects"]))
        snapshot = copy.deepcopy(self.level)
        runtime.apply(self.level, self.placements, release_beta=True)
        self.assertEqual(snapshot, self.level)
        senders = [o for o in self.level["blam"]["objects"] if "teleporter_sender" in o["tag"]]
        self.assertEqual(len(senders), 3*sum(bool(p.get("shield_return")) for p in self.placements["teleporters"]))

if __name__ == "__main__":
    unittest.main()
