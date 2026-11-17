"""A Halo 2 machine placement's flags reach the simulation's placement."""
import unittest

from h2_door_machines import placement_flags


class PlacementFlagTests(unittest.TestCase):
    def test_a_switch_only_door_keeps_its_flag(self):
        # Containment's base gates: doors that do not operate automatically.
        entry = {"h2_device": {"position_group": 0, "device_flags": 0, "machine_flags": 1}}
        self.assertEqual(placement_flags(entry), {"device data.flags": "0x0", "machine data.flags": "0x1"})

    def test_a_staging_without_flags_sets_none(self):
        self.assertEqual(placement_flags({"h2_device": {"position_group": 0}}), {})
        self.assertEqual(placement_flags({}), {})


if __name__ == "__main__":
    unittest.main()
