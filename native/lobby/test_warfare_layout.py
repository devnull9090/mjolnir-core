import copy
import json
import unittest

import generate_warfare_layout as generator


class LayoutTests(unittest.TestCase):
    def setUp(self):
        self.data = json.loads(generator.MANIFEST.read_text())

    def test_generated_routes_and_bounds_follow_changed_manifest(self):
        a = generator.generate(self.data)
        b = copy.deepcopy(self.data)
        b["flights_m"]["red"]["start"][1] -= 20
        b["play_area_m"]["min"][0] -= 1
        self.assertNotEqual(a, generator.generate(b))
        self.assertIn("-951.0f", generator.generate(b))

    def test_unsafe_or_invalid_contracts_are_rejected(self):
        for mutate in (
            lambda d: d.__setitem__("schema", "pwr-layout-v2"),
            lambda d: d.__setitem__("protocol", 20568),
            lambda d: d.__setitem__("layout_revision", 2),
            lambda d: d["flights_m"]["red"]["start"].__setitem__(0, -1100),
            lambda d: d.__setitem__("insertion_seconds", 20),
            lambda d: d.__setitem__("forced_exit_seconds", 60),
            lambda d: d.__setitem__("descent_timeout_seconds", 20),
            lambda d: d["play_area_m"]["max"].__setitem__(2, float("nan")),
            lambda d: d["coordinates"]["origin_m"].__setitem__(0, 1),
        ):
            d = copy.deepcopy(self.data)
            mutate(d)
            with self.assertRaises(ValueError):
                generator.generate(d)

    def test_baked_map_guard_includes_homes_warmup_and_captures(self):
        data=copy.deepcopy(self.data)
        before=generator.generate(data)
        data["homes_m"]["red"][0]+=1
        self.assertNotEqual(generator.generate(data),before)
        markers=dict(generator.marker_points(data))
        self.assertEqual(len(markers),10)
        self.assertAlmostEqual(markers["red_home"][2],data["homes_m"]["red"][2]+1.2)
        self.assertAlmostEqual(markers["warmup"][2],data["warmup_m"][2]+.8)
        self.assertAlmostEqual(markers["capture_b"][2],data["captures_m"][1][2]+1.2)
        data["captures_m"][0]=data["homes_m"]["red"][:]
        with self.assertRaisesRegex(ValueError,"distinct"):
            generator.generate(data)


if __name__ == "__main__":
    unittest.main()
