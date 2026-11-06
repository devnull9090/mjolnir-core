#!/usr/bin/env python3
"""Tests for ce_vehicle_nodes.py. Run with python -m unittest."""
import math
import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ce_vehicle_nodes as nodes  # noqa: E402

HALF_TURN_Z = [0.0, 0.0, 1.0, 0.0]


def bone(index, name, parent, ce_node, translation=(0, 0, 0), rotation=(0, 0, 0, 1)):
    return {"index": index, "name": name, "parent": parent, "ce_node": ce_node,
            "tag_local": {"translation": list(translation), "rotation_xyzw": list(rotation)}}


def manifest():
    """A pedestal over a root with two children, one of them with a child."""
    rows = [bone(0, "pedestal", -1, None), bone(1, "frame hull", 0, 0, (1, 0, 2)),
            bone(2, "frame lf_engine", 1, 1, (0, 1, 0), HALF_TURN_Z), bone(3, "frame lf_tire", 2, 2, (1, 0, 0)),
            bone(4, "frame steering", 1, 3, (0, 0, 1))]
    return {"bones": rows, "contract": {"node_count": len(rows)}}


def turn_y(degrees):
    h = math.radians(degrees) / 2
    return [0.0, math.sin(h), 0.0, math.cos(h)]


def still(count):
    return [{"r": [0, 0, 0, 1], "t": [0, 0, 0]} for _ in range(count)]


def frame(turned, rotation):
    rows = still(4)
    for i in turned:
        rows[i] = {"r": rotation, "t": [0, 0, 0]}
    return rows


def ce_data():
    """CE's rotations are the conjugate of the tag's, its idle the rest pose."""
    idle = [{"r": [0, 0, 0, 1], "t": [1, 0, 2]},
            {"r": [0, 0, -1, 0], "t": [0, 1, 0]},
            {"r": [0, 0, 0, 1], "t": [1, 0, 0]},
            {"r": [0, 0, 0, 1], "t": [0, 0, 1]}]
    suspension = [{"i": 1 + k, "name": name, "frames": 2, "rot_flags": 2,
                   "data": [frame([1], turn_y(25)), frame([1], turn_y(-15))]}
                  for k, name in enumerate(nodes.SUSPENSION)]
    return {
        "animations": [{"i": 0, "name": "stand fixed idle", "frames": 2, "rot_flags": 0, "data": [idle, idle]},
                       *suspension,
                       {"i": 5, "name": "vehicle ground-speed", "frames": 4, "rot_flags": 2,
                        "data": [frame([1], turn_y(a)) for a in (90, 180, 270, 0)]},
                       {"i": 6, "name": "vehicle steering", "frames": 3, "rot_flags": 0b1010,
                        "data": [frame([1, 3], turn_y(30)), still(4), frame([1, 3], turn_y(-30))]}],
        "vehicle_anims": [{"left_yaw": math.radians(30), "suspension": [
            {"animation": 2, "extension": -0.36, "compression": -0.02},
            {"animation": 1, "extension": -0.38, "compression": -0.02}]}],
    }


class Table(unittest.TestCase):
    def setUp(self):
        self.table = nodes.NodeTable.from_bones(manifest())

    def test_links_follow_the_parents(self):
        t = self.table
        self.assertEqual(t.links(0), (-1, None, 1))
        self.assertEqual(t.links(1), (0, None, 2))
        self.assertEqual(t.links(2), (1, 4, 3))
        self.assertEqual(t.links(4), (1, None, None))

    def test_object_frames_compose_rotation_and_translation(self):
        t = self.table
        self.assertTrue(np.allclose(t.wt[3], [0, 1, 2]))  # (1,0,2)+(0,1,0), then x turned to -x

    def test_a_ce_node_finds_its_shifted_index(self):
        self.assertEqual(self.table.of_ce(0), 1)
        self.assertEqual(self.table.of_ce(3), 4)

    def test_a_child_before_its_parent_is_refused(self):
        with self.assertRaises(ValueError):
            nodes.NodeTable(["a", "b"], [1, -1], [[0, 0, 0, 1]] * 2, [[0, 0, 0]] * 2, [0, 1])

    def test_a_manifest_that_miscounts_is_refused(self):
        m = manifest()
        m["contract"]["node_count"] = 4
        with self.assertRaises(ValueError):
            nodes.NodeTable.from_bones(m)

    def test_link_sets_write_minus_one_for_no_link(self):
        sets = self.table.link_sets("nodes", "parent", "sibling", "child")
        self.assertIn("nodes[0].parent=-1", sets)
        self.assertIn("nodes[1].child=2", sets)
        self.assertIn("nodes[4].sibling=-1", sets)

    def test_inverse_frame_is_the_identity_quarter_turn_at_rest(self):
        f, left, up, position = nodes.inverse_frame(nodes.IDENTITY, np.array([1.0, 2.0, 3.0]))
        self.assertTrue(np.allclose(f, [0, 1, 0]))
        self.assertTrue(np.allclose(left, [-1, 0, 0]))
        self.assertTrue(np.allclose(up, [0, 0, 1]))
        self.assertTrue(np.allclose(position, [-1, -2, -3]))

    def test_skeleton_sets_give_every_node_a_runtime_row(self):
        sets = self.table.skeleton_sets()
        self.assertIn("runtime node orientations[4].scale=1", sets)
        self.assertIn("nodes[1].default translation=1.000000,0.000000,2.000000", sets)


class Animations(unittest.TestCase):
    def setUp(self):
        self.table = nodes.NodeTable.from_bones(manifest())
        self.spec = nodes.jmad_spec(ce_data(), self.table)
        self.by_name = {a["name"]: a for a in self.spec["animations"]}

    def test_every_node_is_listed_in_order_with_its_parent(self):
        self.assertEqual([n["name"] for n in self.spec["nodes"]], self.table.names)
        self.assertNotIn("parent", self.spec["nodes"][0])
        self.assertEqual(self.spec["nodes"][3]["parent"], "frame lf_engine")

    def test_idle_holds_the_added_root_too(self):
        self.assertEqual(sorted(self.by_name["any:idle"]["nodes"]), sorted(self.table.names))

    def test_a_flag_bit_is_a_ce_node_not_a_table_index(self):
        moved = self.by_name["suspension:left:back"]["nodes"]
        self.assertEqual(list(moved), ["frame lf_engine"])

    def test_suspension_runs_through_the_conjugate(self):
        frames = self.by_name["suspension:left:back"]["nodes"]["frame lf_engine"]["rotation"]
        self.assertEqual(len(frames), nodes.SUSPENSION_FRAMES)
        self.assertAlmostEqual(frames[0][1], -math.sin(math.radians(12.5)), places=6)
        self.assertAlmostEqual(frames[-1][1], math.sin(math.radians(7.5)), places=6)

    def test_ground_speed_ends_back_at_rest_and_splits_front_from_rear(self):
        self.assertEqual(list(self.by_name["vehicle:ground_speed"]["nodes"]), ["frame lf_engine"])
        self.assertEqual(self.by_name["vehicle:ground_speed_rear"]["nodes"], {})
        last = self.by_name["vehicle:ground_speed"]["nodes"]["frame lf_engine"]["rotation"][-1]
        self.assertAlmostEqual(abs(last[3]), 1.0, places=6)

    def test_front_and_rear_come_from_position_not_names(self):
        m = manifest()
        m["bones"][2]["name"] = "axle a"
        m["bones"][4]["name"] = "axle b"
        m["bones"][4]["tag_local"]["translation"] = [-3, 0, 1]
        ce = ce_data()
        ce["animations"][0]["data"][0][3]["t"] = [-3, 0, 1]
        ground = next(a for a in ce["animations"] if a["name"] == "vehicle ground-speed")
        ground["rot_flags"] = 0b1010
        ground["data"] = [frame([1, 3], turn_y(a)) for a in (90, 180, 270, 0)]
        spec = nodes.jmad_spec(ce, nodes.NodeTable.from_bones(m))
        by_name = {a["name"]: a for a in spec["animations"]}
        self.assertEqual(list(by_name["vehicle:ground_speed"]["nodes"]), ["axle a"])
        self.assertEqual(list(by_name["vehicle:ground_speed_rear"]["nodes"]), ["axle b"])

    def test_steering_stops_at_ce_limit(self):
        frames = self.by_name["vehicle:steering"]["nodes"]["frame steering"]["rotation"]
        self.assertAlmostEqual(frames[0][1], math.sin(math.radians(15)), places=6)  # 45 degrees stops at 30
        self.assertAlmostEqual(frames[1][1], math.sin(math.radians(11.25)), places=6)  # 22.5 is under the limit
        self.assertAlmostEqual(frames[2][3], 1.0)
        self.assertAlmostEqual(frames[4][1], -frames[0][1], places=6)

    def test_a_rest_pose_that_moved_is_refused(self):
        ce = ce_data()
        ce["animations"][0]["data"][0][2]["t"] = [5, 0, 0]
        with self.assertRaises(ValueError):
            nodes.jmad_spec(ce, self.table)

    def test_graph_defaults_are_object_frames(self):
        rows = nodes.default_sets(nodes.NodeTable.from_bones(manifest()))
        self.assertEqual(len(rows), 10)
        self.assertIn("additional node data[3].default translation=0.000000,1.000000,2.000000", rows)
        self.assertIn("additional node data[3].default rotation=0.0000000,0.0000000,1.0000000,0.0000000", rows)

    def test_depths_change_sign_and_go_by_animation(self):
        sets = nodes.suspension_sets(ce_data())
        self.assertIn("content.vehicle suspension[1].full extension ground_depth=0.360000", sets)
        self.assertIn("content.vehicle suspension[0].full compression ground_depth=0.020000", sets)


class Agreement(unittest.TestCase):
    def setUp(self):
        self.table = nodes.NodeTable.from_bones(manifest())
        self.rows = [(self.table.names[i], *(-1 if v is None else v for v in self.table.links(i)))
                     for i in range(self.table.count)]

    def test_equal_lists_pass(self):
        self.assertEqual(nodes.disagreements(self.table, {"skel": self.rows}), [])

    def test_a_short_list_is_named(self):
        self.assertIn("jmad: 4 nodes, wanted 5", nodes.disagreements(self.table, {"jmad": self.rows[:4]}))

    def test_a_wrong_name_and_a_wrong_link_are_each_named(self):
        bad = list(self.rows)
        bad[3] = ("frame_lf_tire", 2, -1, -1)
        bad[4] = ("frame steering", 2, -1, -1)
        found = nodes.disagreements(self.table, {"coll": bad})
        self.assertEqual(len(found), 2)
        self.assertIn("named frame_lf_tire", found[0])
        self.assertIn("links", found[1])

    def test_a_list_without_names_checks_links_only(self):
        nameless = [(None, *r[1:]) for r in self.rows]
        self.assertEqual(nodes.disagreements(self.table, {"phmo": nameless}), [])


if __name__ == "__main__":
    unittest.main()
