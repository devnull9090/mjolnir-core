"""Tests for h2_machines.py's frame sampling and box fitting (the tag
building needs the game's containers and is checked in game)."""
import math
import unittest

import h2_machines


class FramesOf(unittest.TestCase):
    def test_frame_f_is_the_angle_at_f_over_n_of_the_turn(self):
        # Ascension's antenna: 40 s at a frame every 0.1 s.
        turn = {"period": 40.0, "keys": [[0, 0.0], [2, 1.0], [6, 20.0], [10, 20.0], [40, 0.0]]}
        frames = h2_machines.frames_of(turn)
        self.assertEqual(len(frames), 400)
        self.assertAlmostEqual(frames[20], 1.0)
        self.assertAlmostEqual(frames[80], 20.0)
        # The last frame, held to the end of the turn, is one step short of it.
        self.assertAlmostEqual(frames[-1], 20.0 * 0.1 / 30.0)

    def test_a_full_turn_runs_evenly_to_its_end(self):
        turn = {"period": 30.0, "keys": [[0, 0.0], [7.5, 90.0], [15, 180.0], [22.5, 270.0], [30, 360.0]]}
        frames = h2_machines.frames_of(turn)
        self.assertEqual(len(frames), 300)
        steps = {round(b - a, 6) for a, b in zip(frames, frames[1:])}
        self.assertEqual(steps, {1.2})
        self.assertAlmostEqual(frames[-1], 358.8)


class Boxes(unittest.TestCase):
    def test_a_thin_panel_is_covered_by_few_boxes(self):
        # Two triangles: a 2 x 1 panel in the plane x = 0.
        tris = [0, 0, 0, 0, 2, 0, 0, 2, 1,
                0, 0, 0, 0, 2, 1, 0, 0, 1]
        out = h2_machines.boxes(tris, cell=0.25)
        self.assertLessEqual(len(out), 4)
        lo = [min(b["center"][k] - b["half"][k] for b in out) for k in range(3)]
        hi = [max(b["center"][k] + b["half"][k] for b in out) for k in range(3)]
        self.assertLessEqual(lo[1], 0.0)
        self.assertGreaterEqual(hi[1], 2.0)
        self.assertGreaterEqual(hi[2], 1.0)
        self.assertLessEqual(hi[0] - lo[0], 0.25 + 1e-6)

    def test_the_grid_coarsens_to_the_limit(self):
        tris = []
        for i in range(40):
            a = 2 * math.pi * i / 40
            b = 2 * math.pi * (i + 1) / 40
            tris += [0, 0, 0, 5 * math.cos(a), 5 * math.sin(a), 0, 5 * math.cos(b), 5 * math.sin(b), 3]
        self.assertLessEqual(len(h2_machines.boxes(tris, cell=0.1, limit=30)), 30)


class Turn(unittest.TestCase):
    def test_quaternions_turn_about_the_axis(self):
        q = h2_machines.quat([0.0, 1.0, 0.0], 90.0)
        v = h2_machines.qrot(q, (0.0, 0.0, 1.0))
        self.assertAlmostEqual(v[0], 1.0, places=6)
        self.assertAlmostEqual(v[2], 0.0, places=6)


if __name__ == "__main__":
    unittest.main()
