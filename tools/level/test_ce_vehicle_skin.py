#!/usr/bin/env python3
"""Tests for ce_vehicle_skin.py's rules, on a small made-up model."""
import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ce_vehicle_skin as S  # noqa: E402


def model(root_at=(0.5, 1.0, 0.0)):
    """A root with one child, plus a marker node outside the skin."""
    return {"nodes": [{"name": "frame hull", "translation": list(root_at), "children": [1, 2]},
                      {"name": "frame wheel", "translation": [0.0, -0.25, 1.0]},
                      {"name": "#marker", "translation": [1.0, 0.0, 0.0]}],
            "skins": [{"joints": [0, 1]}]}


class Names(unittest.TestCase):
    def test_bone_name(self):
        self.assertEqual(S.bone_name("frame lb_tire"), "frame_lb_tire")
        self.assertEqual(S.bone_name(" a b "), "a_b")


class Bones(unittest.TestCase):
    def test_root_off_the_origin_gets_a_parent(self):
        bones, added = S.bone_list(model())
        self.assertEqual(added, 1)
        self.assertEqual([b["name"] for b in bones], [S.ORIGIN_ROOT, "frame hull", "frame wheel"])
        self.assertEqual([b["parent"] for b in bones], [-1, 0, 1])
        self.assertTrue(S.is_identity(bones[0]["local"]))

    def test_every_node_keeps_its_place(self):
        bones, _ = S.bone_list(model())
        np.testing.assert_allclose(bones[1]["object"][:3, 3], [0.5, 1.0, 0.0])
        np.testing.assert_allclose(bones[2]["object"][:3, 3], [0.5, 0.75, 1.0])
        np.testing.assert_allclose(bones[2]["local"][:3, 3], [0.0, -0.25, 1.0])

    def test_root_at_the_origin_stays_the_root(self):
        bones, added = S.bone_list(model((0.0, 0.0, 0.0)))
        self.assertEqual(added, 0)
        self.assertEqual([b["parent"] for b in bones], [-1, 0])

    def test_two_nodes_of_one_name_stop(self):
        g = model()
        g["nodes"][1]["name"] = "frame hull"
        with self.assertRaises(SystemExit):
            S.bone_list(g)

    def test_names_the_sim_would_merge_stop(self):
        g = model()
        g["nodes"][1]["name"] = "frame_hull"
        with self.assertRaises(SystemExit):
            S.bone_list(g)

    def test_manifest(self):
        bones, added = S.bone_list(model())
        m = S.bones_manifest(bones, added, "x")
        self.assertEqual(m["node_index_shift"], 1)
        self.assertEqual(m["contract"]["node_count"], 3)
        hull = m["bones"][1]
        self.assertEqual((hull["name"], hull["bone"], hull["ce_node"], hull["parent_name"]),
                         ("frame hull", "frame_hull", 0, S.ORIGIN_ROOT))
        # glTF (0.5, 1, 0) metres: Unreal's (x, z, y) in centimetres.
        np.testing.assert_allclose(hull["ue_local"]["translation"], [50.0, 0.0, 100.0])


class Lights(unittest.TestCase):
    ROWS = [{"bone": "pedestal", "ce_node": None}, {"bone": "frame_hull", "ce_node": 0}]

    @staticmethod
    def marker(name, y, q=(0.0, 0.0, 0.0, 1.0)):
        return {"name": name, "node": 0, "t": [1.0, y, 0.5], "q": list(q)}

    def test_left_is_positive_y_and_flips_for_unreal(self):
        m = [self.marker("taillight", -0.1, (0.0, 0.0, 1.0, 0.0)), self.marker("taillight", 0.1, (0.0, 0.0, 1.0, 0.0))]
        left, right = S.light_bones(m, self.ROWS)
        self.assertEqual((left["name"], right["name"]), ("VFX_Taillight_L", "VFX_Taillight_R"))
        np.testing.assert_allclose(left["location"], [304.8, -30.48, 152.4])
        self.assertEqual(left["bone"], "frame_hull")

    def test_a_light_joint_lands_on_its_marker_in_unreal(self):
        bones = [{"name": "frame hull", "object": np.eye(4)}]
        row = {"name": "x", "bone": "frame_hull", "location": [100.0, -50.0, 25.0], "rotation": [0.0, 0.0, 1.0, 0.0]}
        joint = S.light_joints([row], bones)[0]
        placed = S.rest(joint["object"])["ue_cm"]
        np.testing.assert_allclose(placed["translation"], row["location"])
        np.testing.assert_allclose(np.abs(placed["rotation_xyzw"]), [0, 0, 1, 0], atol=1e-9)

    def test_a_buried_light_comes_out_along_its_facing(self):
        row = {"name": "x", "bone": "b", "location": [10.0, 0.0, 0.0], "rotation": [0.0, 0.0, 0.0, 1.0]}
        points = np.array([[14.0, 2.0, 0.0], [90.0, 50.0, 0.0], [-5.0, 0.0, 0.0]])
        S.clear_of_body([row], {"b": np.zeros(3)}, points)
        np.testing.assert_allclose(row["location"], [15.0, 0.0, 0.0])

    def test_a_clear_light_stays(self):
        row = {"name": "x", "bone": "b", "location": [-10.0, 0.0, 0.0], "rotation": [0.0, 0.0, 1.0, 0.0]}
        S.clear_of_body([row], {"b": np.zeros(3)}, np.array([[5.0, 0.0, 0.0]]))
        np.testing.assert_allclose(row["location"], [-10.0, 0.0, 0.0])

    def test_two_headlights_take_the_outer_names(self):
        got = S.light_bones([self.marker("headlight", 0.2), self.marker("headlight", -0.2)], self.ROWS)
        self.assertEqual([s["name"] for s in got], ["VFX_Headlight_L", "VFX_Headlight_R"])

    def test_four_headlights_run_left_to_right(self):
        got = S.light_bones([self.marker("headlight", y) for y in (0.1, -0.2, 0.2, -0.1)], self.ROWS)
        self.assertEqual([s["name"] for s in got], list(S.LIGHT_BONES["headlight"]))
        self.assertEqual([s["location"][1] < 0 for s in got], [True, True, False, False])


class Vertices(unittest.TestCase):
    def test_incident_packs_in_the_tangent_frame(self):
        p = {"nrm": np.array([[0.0, 0.0, 1.0]]), "tan": np.array([[1.0, 0.0, 0.0, 1.0]]),
             "inc": np.array([[0.0, 0.5, 0.0]])}
        np.testing.assert_array_equal(S.pack_incident(p), [[128, 255, 128, 128]])

    def test_a_flipped_tangent_flips_the_bitangent(self):
        p = {"nrm": np.array([[0.0, 0.0, 1.0]]), "tan": np.array([[1.0, 0.0, 0.0, -1.0]]),
             "inc": np.array([[0.0, 1.0, 0.0]])}
        np.testing.assert_array_equal(S.pack_incident(p), [[128, 0, 128, 255]])

    def test_no_incident_is_neutral(self):
        p = {"nrm": np.array([[0.0, 0.0, 1.0]]), "tan": np.array([[1.0, 0.0, 0.0, 1.0]]), "inc": np.zeros((1, 3))}
        np.testing.assert_array_equal(S.pack_incident(p), [[128, 128, 128, 0]])

    def test_constant_uv(self):
        self.assertEqual(S.constant_uv([{"uv1": [[0.25, 0.5], [0.25, 0.5]]}]), [0.25, 0.5])
        with self.assertRaises(SystemExit):
            S.constant_uv([{"uv1": [[0.25, 0.5], [0.5, 0.5]]}])

    def test_binding_rejects_a_weight_on_the_added_root(self):
        bones, added = S.bone_list(model())
        s = {"material": "m", "joints": np.array([[0, 0, 0, 0]]), "weights": np.array([[1.0, 0, 0, 0]])}
        with self.assertRaises(SystemExit):
            S.check_binding(bones, [s], added)


if __name__ == "__main__":
    unittest.main()
