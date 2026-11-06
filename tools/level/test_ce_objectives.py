#!/usr/bin/env python3
import copy
import math
import unittest

import add_objectives as ao
import ce_objectives as co


def corner(x, y, z=0.0, team=0):
    return {"type": "hill", "team": team, "pos": [x, y, z], "yaw": 0}


def ball(team, x=0.0):
    return {"type": "oddball", "team": team, "pos": [x, 0.0, 0.0], "yaw": 0}


def track(team, x, y=0.0, z=0.0):
    return {"type": "race_track", "team": team, "pos": [x, y, z], "yaw": 0}


def races(objects):
    return [o for o in objects if o["set"][co.LABEL] == co.RACE_LABEL]


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

    def test_hills_rotate_in_team_order(self):
        markers = ([corner(x, y, team=5) for x, y in ((0, 0), (900, 0), (0, 900))]
                   + [corner(x, y, team=2) for x, y in ((5000, 0), (5900, 0), (5000, 900))])
        objects, modes = co.objective_objects(markers)
        self.assertEqual(modes, ["koth"])
        self.assertEqual([o["set"]["multiplayer data.spawn order"] for o in objects], ["0", "1"])
        self.assertGreater(objects[0]["pos"][0], 5000)
        self.assertEqual({o["set"][co.LABEL] for o in objects}, {co.HILL_LABEL})

    def test_a_lone_flag_is_ces_square_beside_real_hills(self):
        ring = [corner(x, y, team=0) for x, y in ((0, 0), (900, 0), (0, 900))]
        objects, _ = co.objective_objects(ring + [corner(9000, 7000, 50, team=6)])
        lone = objects[1]
        self.assertEqual(lone["pos"], [9000.0, 7000.0, 50])
        radius = float(lone["set"]["multiplayer data.boundary width or radius"])
        self.assertAlmostEqual(radius, 2 / math.sqrt(math.pi), places=3)

    def test_two_flags_are_no_hill(self):
        ring = [corner(x, y, team=0) for x, y in ((0, 0), (900, 0), (0, 900))]
        pair = [corner(9000, 0, team=1), corner(9900, 0, team=1)]
        self.assertEqual(len(co.objective_objects(ring + pair)[0]), 1)

    def test_a_map_with_only_a_stray_flag_has_no_hill(self):
        self.assertEqual(co.objective_objects([corner(9000, 9000, team=1)]), ([], []))

    def test_a_hill_uses_its_first_twelve_flags_in_marker_order(self):
        twelve = [corner(x, y) for x, y in ((0, 0), (1000, 0), (1000, 1000), (0, 1000))] * 3
        far = corner(50000, 50000)
        capped, _ = co.objective_objects(twelve + [far])
        self.assertEqual(capped[0]["pos"][:2], [500.0, 500.0])
        whole, _ = co.objective_objects(twelve + [far], None)
        self.assertGreater(whole[0]["pos"][0], 1000)
        self.assertEqual(co.hill_flags_for("halo2"), None)
        self.assertEqual(co.hill_flags_for("halo1"), co.HILL_MAX_FLAGS)
        self.assertEqual(co.hill_flags_for(None), co.HILL_MAX_FLAGS)

    def test_race_flags_take_sorted_ranks_across_gaps(self):
        objects, modes = co.objective_objects([track(11, 9000), track(3, 0), track(4, 3000, 3000)])
        self.assertEqual(modes, ["race"])
        ranked = {o["set"]["multiplayer data.spawn order"]: o["pos"][0] for o in races(objects)}
        self.assertEqual(ranked, {"0": 0, "1": 3000, "2": 9000})
        for o in objects:
            self.assertEqual(o["set"]["multiplayer data.owner team"], co.MARKER_TEAM)
            self.assertEqual(o["set"]["multiplayer data.boundary shape"], "cylinder")

    def test_race_radius_stays_six_metres_on_an_open_track(self):
        self.assertAlmostEqual(co.race_radius([[0, 0, 0], [5000, 0, 0], [5000, 5000, 0]]) * co.CM_PER_WORLD_UNIT,
                               600, places=1)

    def test_race_radius_shrinks_for_the_closest_pair_and_counts_the_closing_leg(self):
        close = [[0, 0, 0], [5000, 0, 0], [5000, 5000, 0], [800, 0, 0]]
        self.assertAlmostEqual(co.race_radius(close) * co.CM_PER_WORLD_UNIT, 400, places=1)

    def test_race_radius_stops_at_its_floor(self):
        tight = [[0, 0, 0], [100, 0, 0], [5000, 0, 0]]
        self.assertAlmostEqual(co.race_radius(tight) * co.CM_PER_WORLD_UNIT, 250, places=1)

    def test_a_long_closing_leg_is_left_as_data(self):
        far = [track(0, 0), track(1, 5000), track(2, 700000)]
        self.assertEqual(len(races(co.objective_objects(far)[0])), 3)

    def test_two_race_flags_on_one_index_stop_the_run(self):
        with self.assertRaises(ValueError):
            co.objective_objects([track(1, 0), track(1, 5000)])

    def test_one_race_flag_is_no_track(self):
        self.assertEqual(co.objective_objects([track(0, 0)]), ([], []))

    def test_modes_come_from_the_map(self):
        self.assertEqual(co.objective_objects([])[1], [])
        self.assertEqual(co.objective_objects([corner(0, 0)])[1], [])
        self.assertEqual(co.objective_objects([track(0, 0), track(1, 5000)])[1], ["race"])
        self.assertEqual(co.objective_objects([ball(8), ball(8, 100.0)])[1], ["oddball"])

    def test_apply_takes_health_spots_out_of_the_spawn_search(self):
        spot = {"tag": "a", "set": {co.LABEL: co.HEALTH_LABEL, "multiplayer data.owner team": "neutral"}}
        level = {"blam": {"objects": [spot]}}
        co.apply(level)
        self.assertEqual(spot["set"]["multiplayer data.owner team"], co.MARKER_TEAM)

    def test_apply_can_leave_the_track_out(self):
        level = {"modes": ["slayer"], "blam": {"objects": []},
                 "markers": [corner(0, 0), corner(900, 0), corner(0, 900), ball(0),
                             track(0, 5000), track(1, 0, 1000)]}
        co.apply(level, race=False)
        self.assertEqual(level["modes"], ["slayer", "koth", "oddball"])
        self.assertEqual(races(level["blam"]["objects"]), [])
        self.assertNotIn("race_flags", level)
        self.assertIn("koth_hills", level)

    def test_apply_keeps_other_objects_and_is_idempotent(self):
        level = {"modes": ["slayer", "ctf"], "blam": {"objects": [{"tag": "a", "set": {co.LABEL: "ctf_flag_return"}}]},
                 "markers": [corner(0, 0), corner(900, 0), corner(0, 900), ball(0),
                             track(4, 5000), track(1, 0, 1000)]}
        co.apply(level)
        self.assertEqual(level["modes"], ["slayer", "ctf", "koth", "oddball", "race"])
        self.assertEqual(len(level["blam"]["objects"]), 5)
        self.assertEqual(len(level["koth_hills"]), 1)
        self.assertEqual(len(level["koth_hills"][0]), 4)
        self.assertEqual([f[:2] for f in level["race_flags"]], [[0, 1000], [5000, 0.0]])
        self.assertEqual(len(level["race_flags"][0]), 4)
        again = copy.deepcopy(level)
        co.apply(again)
        self.assertEqual(again, level)

    def test_apply_drops_what_the_markers_no_longer_give(self):
        level = {"modes": ["slayer", "race"], "race_flags": [[0, 0, 0, 600]],
                 "blam": {"objects": [{"tag": "a", "set": {co.LABEL: co.RACE_LABEL}}]}, "markers": []}
        co.apply(level)
        self.assertEqual(level["modes"], ["slayer"])
        self.assertNotIn("race_flags", level)
        self.assertEqual(level["blam"]["objects"], [])


class Rebake(unittest.TestCase):
    def level(self):
        spot = {"tag": "s", "set": {co.LABEL: co.HEALTH_LABEL, "multiplayer data.owner team": "neutral"}}
        crate = {"tag": "c", "set": {"multiplayer data.owner team": "neutral"}}
        return {"modes": ["slayer"], "landscape": {"a": 1}, "blam": {"objects": [spot, crate], "single_bsp": 0},
                "markers": [track(0, 0), track(1, 5000)]}

    def test_objectives_change_only_what_they_may(self):
        old = self.level()
        self.assertEqual(ao.level_changes(old, co.apply(copy.deepcopy(old))), [])

    def test_a_loader_key_changing_stops_the_pack(self):
        old = self.level()
        new = co.apply(copy.deepcopy(old))
        new["landscape"]["a"] = 2
        self.assertTrue(ao.level_changes(old, new))

    def test_a_scenario_setting_changing_stops_the_pack(self):
        old = self.level()
        new = co.apply(copy.deepcopy(old))
        new["blam"]["single_bsp"] = 1
        self.assertTrue(ao.level_changes(old, new))

    def test_another_objects_team_changing_stops_the_pack(self):
        old = self.level()
        new = co.apply(copy.deepcopy(old))
        new["blam"]["objects"][1]["set"]["multiplayer data.owner team"] = "red"
        self.assertTrue(ao.level_changes(old, new))

    def test_a_lost_object_stops_the_pack(self):
        old = self.level()
        new = co.apply(copy.deepcopy(old))
        del new["blam"]["objects"][1]
        self.assertTrue(ao.level_changes(old, new))

    def test_a_manifest_keeps_all_but_its_release_fields(self):
        old = {"name": "A", "version": "1.0.0", "deps": [], "map": {"code": "AAA", "modes": ["slayer"], "size": "small"}}
        new = copy.deepcopy(old)
        new["version"] = "1.1.0"
        new["map"]["modes"].append("race")
        self.assertEqual(ao.manifest_changes(old, new), [])
        del new["map"]["size"]
        self.assertTrue(ao.manifest_changes(old, new))

    def test_the_runtime_range_is_the_packs_own(self):
        self.assertEqual(ao.runtime_range({"deps": [{"slug": ao.RUNTIME, "range": "^1.16.0"}]}), ("^1.16.0", []))
        other = {"slug": "pack", "range": "*"}
        self.assertEqual(ao.runtime_range({"deps": [other]}), (None, [other]))


if __name__ == "__main__":
    unittest.main()
