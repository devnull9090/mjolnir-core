#!/usr/bin/env python3
"""python tools/level/test_ce_vehicle_lights.py"""
import unittest

import ce_vehicle_lights as lights

CM = lights.CM


def manifest():
    """A body at 10 cm on x, with a light of every name, in Unreal's axes."""
    names = {"VFX_Headlight_L": (120, -45, 120), "VFX_Headlight_LMid": (118, -36, 120),
             "VFX_Headlight_RMid": (118, 36, 120), "VFX_Headlight_R": (120, 45, 120),
             "VFX_Taillight_L": (-150, -26, 115), "VFX_Taillight_R": (-150, 26, 115)}
    return {"bones": [{"bone": "frame_hull", "ue_object": {"translation": [10.0, 0.0, 0.0]}}],
            "light_bones": [{"name": n, "bone": "frame_hull", "location": list(p)} for n, p in names.items()]}


class Cleared(unittest.TestCase):
    def test_a_light_counts_its_bone_and_goes_to_wu_in_ce_axes(self):
        markers = lights.cleared(manifest())
        self.assertEqual(len(markers["headlight"]), 4)
        self.assertEqual(len(markers["taillight"]), 2)
        x, y, z = markers["taillight"][0]
        self.assertAlmostEqual(x * CM, -140.0)
        self.assertAlmostEqual(y * CM, 26.0)  # Unreal's left, CE's right
        self.assertAlmostEqual(z * CM, 115.0)

    def test_each_component_lands_on_its_side(self):
        table = lights.lights(lights.cleared(manifest()), 0.5887, 20.5, -10.8)
        socket = lights.SOCKETS["VFX_Taillight_L"]
        offset = table["move"]["Brakelight_L"]
        # The taillight sockets are turned half way round: x and y flip.
        at = [socket[0][0] - offset[0] * 0.5887, socket[0][1] - offset[1] * 0.5887]
        self.assertAlmostEqual(at[0], -140.0 + 20.5, delta=1.0)
        self.assertAlmostEqual(at[1], -26.0, delta=1.0)
        self.assertEqual(table["move"]["Brakelight_L"], table["move"]["NS_Breaklights_L"])

    def test_moving_a_light_out_of_the_body_moves_it_back_by_as_much(self):
        near, far = manifest(), manifest()
        for row in far["light_bones"]:
            if "Taillight" in row["name"]:
                row["location"][0] -= 4.4
        a = lights.lights(lights.cleared(near), 0.5887, 20.5, -10.8)["move"]["Brakelight_R"]
        b = lights.lights(lights.cleared(far), 0.5887, 20.5, -10.8)["move"]["Brakelight_R"]
        self.assertAlmostEqual((b[0] - a[0]) * 0.5887, 4.4, delta=0.02)


if __name__ == "__main__":
    unittest.main()
