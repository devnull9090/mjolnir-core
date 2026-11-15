"""Transactional publication guards; no game, editor or compiler calls."""
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

from refresh_native_probes import replace_verified, sha, verify_terrain_tail


class RefreshTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.target, self.staged, self.source = (root / name for name in ("level.json", "staged.json", "source.bin"))
        self.target.write_text("original")
        self.staged.write_text("verified")
        self.source.write_bytes(b"collision")
        self.original = sha(self.target)
        self.inputs = {str(self.source): sha(self.source)}
        self.gate = {"layout3_permitted": True, "terrain_contract_compatible": True,
                     "protocol": 20569, "layout_revision": 3}

    def publish(self):
        replace_verified(self.target, self.staged, self.original, self.gate, self.inputs)

    def test_failed_gate_never_replaces_scenario(self):
        self.gate["layout3_permitted"] = False
        with self.assertRaisesRegex(ValueError, "did not authorize"):
            self.publish()
        self.assertEqual(self.target.read_text(), "original")

    def test_changed_collision_input_never_replaces_scenario(self):
        self.source.write_bytes(b"new collision")
        with self.assertRaisesRegex(ValueError, "input changed"):
            self.publish()
        self.assertEqual(self.target.read_text(), "original")

    def test_concurrent_scenario_edit_is_retained(self):
        self.target.write_text("someone else's change")
        with self.assertRaisesRegex(ValueError, "scenario changed"):
            self.publish()
        self.assertEqual(self.target.read_text(), "someone else's change")

    def test_verified_publish_is_exact_and_leaves_no_temporary(self):
        self.publish()
        self.assertEqual(self.target.read_bytes(), self.staged.read_bytes())
        self.assertFalse(self.target.with_name(self.target.name + ".native-refresh.tmp").exists())

    def test_changed_terrain_count_or_duplicate_architecture_tail_rejects(self):
        receipt = {"triangles": 135836, "trailing_architecture_surfaces": 8336,
                   "total_extra_surfaces": 144172, "file": str(self.source), "sha256": sha(self.source)}
        verify_terrain_tail(receipt)
        for key in ("triangles", "trailing_architecture_surfaces", "total_extra_surfaces"):
            with self.assertRaisesRegex(ValueError, "unchanged"):
                verify_terrain_tail({**receipt, key: receipt[key] + 1})

    def test_replacement_architecture_requires_explicit_contract(self):
        receipt = {"triangles": 135836, "trailing_architecture_surfaces": 27632,
                   "total_extra_surfaces": 163468}
        with self.assertRaisesRegex(ValueError, "unchanged"):
            verify_terrain_tail(receipt)
        contract = self.source.with_suffix(".contract.json")
        with patch("bases_v1.runtime_collision.verify_contract", return_value={"verified": True}) as verify:
            self.assertEqual(verify_terrain_tail(receipt, contract), {"verified": True})
            verify.assert_called_once_with(contract, receipt)


if __name__ == "__main__":
    unittest.main()
