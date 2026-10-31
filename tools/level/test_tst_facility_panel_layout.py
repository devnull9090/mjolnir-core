"""Geometry-level regression checks for the facility's illuminated ribs."""
import math
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'levels/test/tst'))
from facility_architecture import branch_path
from facility_panel_layout import branch_panel_bays


class FacilityPanelLayoutTest(unittest.TestCase):
    def test_every_real_branch_bay_clears_ribs_and_concourse(self):
        # Mirrors and turns use the same measured path and active-station
        # logic as the generator; test the full width of the OUTERMOST field.
        layouts = []
        for side in (-1, 1):
            for rear in (False, True):
                path = branch_path(side, rear)
                for segment, (a, b) in enumerate(zip(path, path[1:])):
                    dx, dy = b[0] - a[0], b[1] - a[1]
                    length = math.hypot(dx, dy)
                    tx = dx / length
                    stations = ([2.0, 6.1] if segment == 0 else
                                [3.0, 8.2, 13.2] if segment == 1 else [3.3, 8.7])
                    active = [s for s in stations if s <= length - .8 and
                              abs(a[0] + s * tx) + .30 < 37.4]
                    bays = branch_panel_bays(length, active, a[0], tx)
                    self.assertTrue(bays)
                    for left, right in bays:
                        self.assertGreaterEqual(left, .6 - 1e-8)
                        self.assertLessEqual(right, length - .6 + 1e-8)
                        self.assertGreaterEqual(right-left, 1.2 - 1e-8)
                        self.assertLessEqual(right-left, 3.1 + 1e-8)
                        for station in active:
                            self.assertTrue(right <= station-1.35+1e-8 or
                                            left >= station+1.35-1e-8,
                                            (side, rear, segment, left, right, station))
                        for point in (left, right):
                            self.assertLessEqual(abs(a[0]+point*tx), 37.0 + 1e-8)
                    layouts.append(tuple((round(a, 5), round(b, 5)) for a,b in bays))
        # Mirror symmetry is deliberate; each same-segment layout is equal.
        for segment in range(3):
            self.assertEqual(len({layouts[i] for i in range(segment, len(layouts), 3)}), 1)

    def test_crowded_or_off_wall_bays_are_not_filled(self):
        self.assertEqual(branch_panel_bays(2.0, [1.0], 0, 1), [])
        self.assertEqual(branch_panel_bays(5.0, [], 38, 0), [])

    def test_marked_oblique_view_panel_stops_before_rib(self):
        a, b = branch_path(-1, False)[:2]
        length = math.dist(a, b)
        bays = branch_panel_bays(length, [2.0, 6.1], a[0], (b[0]-a[0])/length)
        self.assertEqual(len(bays), 1)
        self.assertAlmostEqual(bays[0][0], 3.35)
        self.assertAlmostEqual(bays[0][1], 4.75)

    def test_invalid_dimensions_rejected(self):
        with self.assertRaises(ValueError):
            branch_panel_bays(0, [], 0, 1)


if __name__ == '__main__':
    unittest.main()
