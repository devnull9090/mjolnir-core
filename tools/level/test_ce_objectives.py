#!/usr/bin/env python3
import copy
import math
import unittest

import ce_objectives as co


def corner(x, y, z=0.0, team=0):
    return {"type": "hill", "team": team, "pos": [x, y, z], "yaw": 0}


def ball(team, x=0.0):
    return {"type": "oddball", "team": team, "pos": [x, 0.0, 0.0], "yaw": 0}


class Objectives(unittest.TestCase):
    def test_square_hill_is_a_cylinder_of_its_area(self):
        pos, radius, top, bottom = co.fit_hill([[0, 0, 100], [1000, 0, 100], [1000, 1000, 400], [0, 1000, 100]])
        self.assertEqual(pos, [500.0, 500.0, 100])
        self.assertAlmostEqual(radius * co.CM_PER_WORLD_UNIT, 1000 / math.sqrt(math.pi), places=1)
        self.assertAlmostEqual(top, 300 / co.CM_PER_WORLD_UNIT + co.HILL_HEADROOM, places=3)
        self.assertEqual(bottom, co.HILL_FOOTROOM)

    def test_corners_out_of_order_fit_the_same(self):
        ring = [[0, 0, 0], [1000, 1000, 0], [1000, 0, 0], [0, 1000, 0], [500, 500, 0]]
        self.assertEqual(co.fit_hill(ring), co.fit_hill(ring[::-1]))
        self.assertEqual(co.fit_hill(ring)[0][:2], [500.0, 500.0])

    def test_hills_rotate_in_team_order_and_stray_corners_are_no_hill(self):
        markers = ([corner(x, y, team=5) for x, y in ((0, 0), (900, 0), (0, 900))]
                   + [corner(x, y, team=2) for x, y in ((5000, 0), (5900, 0), (5000, 900))]
                   + [corner(9000, 9000, team=7)])
        objects, modes = co.objective_objects(markers)
        self.assertEqual(modes, ["koth"])
        self.assertEqual([o["set"]["multiplayer data.spawn order"] for o in objects], ["0", "1"])
        self.assertGreater(objects[0]["pos"][0], 5000)
        self.assertEqual({o["set"][co.LABEL] for o in objects}, {co.HILL_LABEL})

    def test_modes_come_from_the_map(self):
        self.assertEqual(co.objective_objects([])[1], [])
        self.assertEqual(co.objective_objects([corner(0, 0)])[1], [])
        self.assertEqual(co.objective_objects([ball(8), ball(8, 100.0)])[1], ["oddball"])

    def test_apply_takes_health_spots_out_of_the_spawn_search(self):
        spot = {"tag": "a", "set": {co.LABEL: co.HEALTH_LABEL, "multiplayer data.owner team": "neutral"}}
        level = {"blam": {"objects": [spot]}}
        co.apply(level)
        self.assertEqual(spot["set"]["multiplayer data.owner team"], co.MARKER_TEAM)

    def test_apply_keeps_other_objects_and_is_idempotent(self):
        level = {"modes": ["slayer", "ctf"], "blam": {"objects": [{"tag": "a", "set": {co.LABEL: "ctf_flag_return"}}]},
                 "markers": [corner(0, 0), corner(900, 0), corner(0, 900), ball(0)]}
        co.apply(level)
        self.assertEqual(level["modes"], ["slayer", "ctf", "koth", "oddball"])
        self.assertEqual(len(level["blam"]["objects"]), 3)
        self.assertEqual(len(level["koth_hills"]), 1)
        self.assertEqual(len(level["koth_hills"][0]), 4)
        again = copy.deepcopy(level)
        co.apply(again)
        self.assertEqual(again, level)


if __name__ == "__main__":
    unittest.main()
