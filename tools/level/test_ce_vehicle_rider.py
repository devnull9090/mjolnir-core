#!/usr/bin/env python3
"""Tests for ce_vehicle_rider.py. Run with python -m unittest."""
import math
import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ce_vehicle_nodes as nodes  # noqa: E402
import ce_vehicle_rider as rider  # noqa: E402


def turn_y(degrees):
    h = math.radians(degrees) / 2
    return [0.0, math.sin(h), 0.0, math.cos(h)]


def turn_z(degrees):
    h = math.radians(degrees) / 2
    return [0.0, 0.0, math.sin(h), math.cos(h)]


# A man standing at attention, facing +x, in one flat table. Each row is a node,
# its parent and where it sits in the object. All frames are unturned, so an
# object position is also how a node's child offsets are read.
SPARTAN = [
    ("pedestal", None, (0, 0, 0)), ("root_m", "pedestal", (0, 0, 0.40)),
    ("spine1_m", "root_m", (0, 0, 0.44)), ("spine2_m", "spine1_m", (0, 0, 0.48)),
    ("chest_m", "spine2_m", (0, 0, 0.52)), ("neck_m", "chest_m", (0, 0, 0.60)),
    ("head_m", "neck_m", (0, 0, 0.64)), ("helmet_m", "head_m", (0, 0, 0.66)),
    ("scapula_l", "chest_m", (0, 0.02, 0.58)), ("shoulder_l", "scapula_l", (0, 0.08, 0.58)),
    ("elbow_l", "shoulder_l", (0.01, 0.08, 0.47)), ("wrist_l", "elbow_l", (0.01, 0.08, 0.37)),
    ("indexfinger1_l", "wrist_l", (0.03, 0.08, 0.35)),
    ("scapula_r", "chest_m", (0, -0.02, 0.58)), ("shoulder_r", "scapula_r", (0, -0.08, 0.58)),
    ("elbow_r", "shoulder_r", (0.01, -0.08, 0.47)), ("wrist_r", "elbow_r", (0.01, -0.08, 0.37)),
    ("hip_l", "root_m", (0.01, 0.04, 0.38)), ("knee_l", "hip_l", (0.02, 0.04, 0.20)),
    ("ankle_l", "knee_l", (0, 0.04, 0.03)), ("toes_l", "ankle_l", (0.05, 0.04, 0.01)),
    ("hip_r", "root_m", (0.01, -0.04, 0.38)), ("knee_r", "hip_r", (0.02, -0.04, 0.20)),
    ("ankle_r", "knee_r", (0, -0.04, 0.03)), ("toes_r", "ankle_r", (0.05, -0.04, 0.01)),
]
CE = [
    ("bip01 pelvis", None, (0, 0, 0.39)), ("bip01 l thigh", "bip01 pelvis", (0, 0.04, 0.39)),
    ("bip01 r thigh", "bip01 pelvis", (0, -0.04, 0.39)), ("bip01 spine", "bip01 pelvis", (0, 0, 0.43)),
    ("bip01 l calf", "bip01 l thigh", (0.01, 0.04, 0.21)), ("bip01 r calf", "bip01 r thigh", (0.01, -0.04, 0.21)),
    ("bip01 spine1", "bip01 spine", (0, 0, 0.50)), ("bip01 l clavicle", "bip01 spine1", (0, 0.06, 0.57)),
    ("bip01 l foot", "bip01 l calf", (0, 0.04, 0.05)), ("bip01 neck", "bip01 spine1", (0, 0, 0.59)),
    ("bip01 r clavicle", "bip01 spine1", (0, -0.06, 0.57)), ("bip01 r foot", "bip01 r calf", (0, -0.04, 0.05)),
    ("bip01 head", "bip01 neck", (0, 0, 0.61)), ("bip01 l upperarm", "bip01 l clavicle", (0, 0.09, 0.57)),
    ("bip01 r upperarm", "bip01 r clavicle", (0, -0.09, 0.57)), ("bip01 l forearm", "bip01 l upperarm", (0.02, 0.09, 0.47)),
    ("bip01 r forearm", "bip01 r upperarm", (0.02, -0.09, 0.47)), ("bip01 l hand", "bip01 l forearm", (0.06, 0.09, 0.39)),
    ("bip01 r hand", "bip01 r forearm", (0.06, -0.09, 0.39)),
]


def spartan():
    """A skeleton and a one-frame animation holding its rest."""
    names = [r[0] for r in SPARTAN]
    at = {r[0]: np.array(r[2], float) for r in SPARTAN}
    skeleton, tracks = [], []
    for name, parent, _ in SPARTAN:
        local = at[name] - (at[parent] if parent else 0)
        skeleton.append({"name": name, "parent": names.index(parent) if parent else None,
                         "default": {"rotation": [0, 0, 0, 1], "translation": list(at[name]), "scale": 1}})
        tracks.append({"rotation": {"static": [0, 0, 0, 1]}, "translation": {"static": list(local)},
                       "scale": {"static": 1.0}})
    return skeleton, {"frames": 1, "tracks": tracks}


def ce_rider():
    names = [r[0] for r in CE]
    at = {r[0]: np.array(r[2], float) for r in CE}
    rows = []
    for name, parent, _ in CE:
        local = at[name] - (at[parent] if parent else 0)
        rows.append({"name": name, "parent": names.index(parent) if parent else -1,
                     "translation": list(local), "rotation": [0, 0, 0, 1]})
    return {"nodes": rows, "markers": {"left hand": {"node": "bip01 l hand", "translation": [0, 0, 0],
                                                     "rotation": [0, 0, 0, 1]}}}


def seated(leaning):
    """CE's rider bent at the waist: the frame a seat's idle would hold."""
    r = ce_rider()
    frame = [{"rotation": list(n["rotation"]), "translation": list(n["translation"])} for n in r["nodes"]]
    # CE stores the conjugate, so a stored negative turn leans forward.
    frame[3]["rotation"] = turn_y(-leaning)
    frame[1]["rotation"] = turn_y(90)
    frame[2]["rotation"] = turn_y(90)
    frame[4]["rotation"] = turn_y(-90)
    frame[5]["rotation"] = turn_y(-90)
    return r, frame


def vehicle(seat=(0.5, 0, 1.0)):
    axes = {"forward": [1, 0, 0], "left": [0, 1, 0], "up": [0, 0, 1]}
    return {"markers": {"driver": {"node": "frame hull", "position": list(seat), **axes},
                        "grip": {"node": "frame steering", "position": [0.9, 0.2, 1.3], **axes}}}


def ce_seats(frames, ik_points=()):
    r = ce_rider()
    return {"vehicle": vehicle(), "rider": r,
            "seats": [{"label": "seat", "marker": "driver", "idle": "idle", "ik_points": list(ik_points), "frames": frames}]}


def manifest():
    def row(i, name, at):
        return {"index": i, "name": name,
                "tag_object": {"translation": at, "rotation_xyzw": turn_y(-10) if name == "frame steering" else [0, 0, 0, 1]}}
    return {"bones": [row(0, "pedestal", [0, 0, 0]), row(1, "frame hull", [0.1, 0, 0.3]), row(6, "frame steering", [0.7, 0, 1.1])]}


class Seats(unittest.TestCase):
    def test_one_table_names_the_labels_and_the_modes(self):
        self.assertEqual(rider.seat_sets(), ["unit.seats[0].label=mongoose_d", "unit.seats[1].label=mongoose_p"])
        self.assertEqual(rider.child_modes(), ["--mode", "ghost_d=mongoose_d", "--mode", "warthog_p=mongoose_p"])

    def test_every_seat_mode_has_its_proxies(self):
        self.assertEqual({donor for _, donor in rider.SEATS}, set(rider.MODE_PROXIES))


class Geometry(unittest.TestCase):
    def test_swing_takes_one_direction_to_another(self):
        a, b = np.array([1.0, 0, 0]), np.array([1.0, 1.0, 0])
        np.testing.assert_allclose(rider.swing(a, b) @ a, b / np.linalg.norm(b), atol=1e-12)

    def test_swing_handles_the_opposite_direction(self):
        a = np.array([0.0, 0, 1])
        np.testing.assert_allclose(rider.swing(a, -a) @ a, -a, atol=1e-12)

    def test_quaternion_returns_what_made_the_matrix(self):
        for q in (turn_y(30), turn_z(170), nodes.unit([0.3, -0.5, 0.6, -0.2]), nodes.unit([0.7, 0.7, 0.05, 0.01])):
            got = rider.quaternion(nodes.matrix(nodes.unit(q)))
            np.testing.assert_allclose(nodes.matrix(got), nodes.matrix(nodes.unit(q)), atol=1e-9)

    def test_a_limb_ends_on_a_target_it_reaches(self):
        start, target = np.zeros(3), np.array([0.5, 0, 0])
        joint, end = rider.bend(start, np.array([0.2, 0, 1.0]), target, 0.4, 0.3)
        np.testing.assert_allclose(end, target, atol=1e-12)
        self.assertAlmostEqual(float(np.linalg.norm(joint)), 0.4)
        self.assertAlmostEqual(float(np.linalg.norm(end - joint)), 0.3)
        self.assertGreater(joint[2], 0)

    def test_a_limb_stops_short_of_straight(self):
        _, end = rider.bend(np.zeros(3), np.array([0, 0, 1.0]), np.array([5.0, 0, 0]), 0.4, 0.3)
        self.assertAlmostEqual(float(end[0]), 0.98 * 0.7)


class CeSide(unittest.TestCase):
    def test_a_stored_rotation_is_the_conjugate(self):
        m = rider.ce_local({"rotation": turn_z(90), "translation": [0, 0, 0]})
        np.testing.assert_allclose(m[:3, :3] @ [1, 0, 0], [0, -1, 0], atol=1e-12)

    def test_resampling_starts_on_the_first_frame_and_keeps_the_count(self):
        frames = [[{"rotation": [0, 0, 0, 1], "translation": [float(k), 0, 0]}] for k in range(65)]
        out = rider.resampled(frames, 60)
        self.assertEqual(len(out), 60)
        self.assertEqual(out[0][0]["translation"][0], 0)
        self.assertAlmostEqual(out[30][0]["translation"][0], 32.5)

    def test_resampling_closes_the_loop_through_the_first_frame(self):
        frames = [[{"rotation": [0, 0, 0, 1], "translation": [float(k), 0, 0]}] for k in (0, 10)]
        self.assertAlmostEqual(rider.resampled(frames, 4)[3][0]["translation"][0], 5.0)

    def test_ik_brings_the_hand_to_the_marker_over_the_seat(self):
        r, frame = seated(0)
        ce = ce_seats([frame], [{"marker": "left hand", "attached_to": "grip"}])
        ce["rider"] = r
        world = rider.ce_after_ik(ce, ce["seats"][0], frame)
        want = np.array(ce["vehicle"]["markers"]["grip"]["position"]) - ce["vehicle"]["markers"]["driver"]["position"]
        shoulder = world["bip01 l upperarm"][:3, 3]
        if np.linalg.norm(want - shoulder) < 0.98 * 0.22:
            np.testing.assert_allclose(world["bip01 l hand"][:3, 3], want, atol=1e-9)
        else:
            self.assertLess(np.linalg.norm(world["bip01 l hand"][:3, 3] - shoulder), 0.22)

    def test_a_missing_marker_skips_the_point(self):
        r, frame = seated(0)
        ce = ce_seats([frame], [{"marker": "left hand", "attached_to": "nowhere"}])
        ce["rider"] = r
        before = rider.ce_pose(r, frame)["bip01 l hand"]
        after = rider.ce_after_ik(ce, ce["seats"][0], frame)["bip01 l hand"]
        np.testing.assert_allclose(before, after)


class Translation(unittest.TestCase):
    def setUp(self):
        self.skeleton, self.animation = spartan()
        r, frame = seated(40)
        self.ce = ce_seats([frame])
        self.ce["rider"] = r
        poses, targets = rider.translate_seat(self.ce, self.ce["seats"][0], self.skeleton, self.animation)
        self.pose, self.target = poses[0], targets[0]
        self.donor = rider.Pose(self.skeleton, self.animation["tracks"], 0)

    def test_the_root_takes_the_pelvis_place(self):
        np.testing.assert_allclose(self.pose.at("root_m"), self.target["bip01 pelvis"][:3, 3], atol=1e-9)

    def test_no_bone_changes_length(self):
        for i, name in enumerate(self.pose.names):
            if name != "root_m":
                np.testing.assert_allclose(self.pose.local[i][:3, 3], self.donor.local[i][:3, 3], atol=1e-12)

    def test_unmapped_nodes_keep_their_local_frames(self):
        for name in ("helmet_m", "indexfinger1_l", "toes_l", "toes_r"):
            i = self.pose.index[name]
            np.testing.assert_array_equal(self.pose.local[i], self.donor.local[i])

    def test_the_spine_follows_ce_rather_than_staying_rigid(self):
        want = self.target["bip01 spine1"][:3, 3] - self.target["bip01 spine"][:3, 3]
        got = self.pose.at("chest_m") - self.pose.at("spine2_m")
        self.assertAlmostEqual(float(rider.along(want) @ rider.along(got)), 1.0, places=6)
        for name in ("spine1_m", "spine2_m", "chest_m", "neck_m", "scapula_l", "scapula_r"):
            self.assertIn(name, rider.edited_nodes())

    def test_the_chest_leans_as_far_as_ce(self):
        up = self.pose.at("neck_m") - self.pose.at("chest_m")
        lean = math.degrees(math.atan2(up[0], up[2]))
        self.assertAlmostEqual(lean, 40, places=3)

    def test_the_shoulders_point_at_ce_s(self):
        for side in "lr":
            aim = self.target[f"bip01 {side} upperarm"][:3, 3] - self.pose.at(f"scapula_{side}")
            got = self.pose.at(f"shoulder_{side}") - self.pose.at(f"scapula_{side}")
            self.assertAlmostEqual(float(rider.along(aim) @ rider.along(got)), 1.0, places=6)

    def test_limbs_end_on_ce_s_joints(self):
        for joint, ce_joint in (("wrist_l", "bip01 l hand"), ("wrist_r", "bip01 r hand"),
                                ("ankle_l", "bip01 l foot"), ("ankle_r", "bip01 r foot")):
            np.testing.assert_allclose(self.pose.at(joint), self.target[ce_joint][:3, 3], atol=1e-9)

    def test_a_wrist_keeps_the_donor_s_rotation_in_the_seat(self):
        np.testing.assert_allclose(self.pose.world("wrist_l")[:3, :3], self.donor.world("wrist_l")[:3, :3], atol=1e-9)

    def test_a_head_turns_as_ce_s_did(self):
        np.testing.assert_allclose(self.pose.world("head_m")[:3, :3], self.target["bip01 head"][:3, :3], atol=1e-9)


class Output(unittest.TestCase):
    def setUp(self):
        self.skeleton, animation = spartan()
        r, frame = seated(30)
        self.ce = ce_seats([frame, frame])
        self.ce["rider"] = r
        grip = {"frames": 1, "tracks": [dict(t) for t in animation["tracks"]]}
        names = [n["name"] for n in self.skeleton]
        grip["tracks"][names.index("head_m")] = {"rotation": {"each": [[0, 0, 0, 1]]}, "translation": {"static": [0, 0, 0]},
                                                 "scale": {"static": 1.0}}
        grip["tracks"][names.index("neck_m")] = {"rotation": None, "translation": None, "scale": None}
        idle = {"frames": 3, "tracks": animation["tracks"]}
        self.donor = {"nodes": self.skeleton, "animations": {"ghost_d:idle": idle, "ghost_d:grip": grip}}
        self.spec, self.limbs, self.posed = rider.build(self.ce, self.donor, {"seat": "ghost_d:idle"},
                                                        {"ghost_d:idle": ["ghost_d:grip"]}, manifest())

    def test_the_frame_count_stays_the_donor_s(self):
        row = self.spec["animations"][0]
        self.assertEqual(row["frames"], 3)
        for values in row["nodes"].values():
            self.assertEqual(len(values["rotation"]), 3)
        self.assertEqual(len(row["nodes"]["root_m"]["translation"]), 3)
        self.assertNotIn("translation", row["nodes"]["chest_m"])

    def test_nothing_outside_the_table_is_written(self):
        self.assertNotIn("helmet_m", self.spec["animations"][0]["nodes"])
        self.assertNotIn("toes_l", self.spec["animations"][0]["nodes"])

    def test_the_copy_repeats_the_first_frame_in_its_own_channels(self):
        idle, grip = self.spec["animations"]
        self.assertEqual(grip["name"], "ghost_d:grip")
        self.assertEqual(grip["frames"], 1)
        self.assertEqual(grip["nodes"]["chest_m"]["rotation"], idle["nodes"]["chest_m"]["rotation"][0])
        self.assertEqual(grip["nodes"]["head_m"]["rotation"], [idle["nodes"]["head_m"]["rotation"][0]])
        self.assertEqual(grip["nodes"]["root_m"]["translation"], idle["nodes"]["root_m"]["translation"][0])
        self.assertEqual(grip["nodes"]["neck_m"], {})

    def test_a_copy_must_be_one_frame(self):
        self.donor["animations"]["ghost_d:grip"]["frames"] = 2
        with self.assertRaises(ValueError):
            rider.build(self.ce, self.donor, {"seat": "ghost_d:idle"}, {"ghost_d:idle": ["ghost_d:grip"]}, manifest())

    def test_rotations_keep_one_sign_through_the_frames(self):
        q = np.array([0.0, 0, 0, 1.0])
        self.assertTrue(np.array_equal(rider.continuous([q, -q])[1], q))

    def test_a_proxy_is_the_joint_on_the_node_it_rides(self):
        row = self.limbs["spartan_hand_left"]
        self.assertEqual(row["node_name"], "frame hull")
        self.assertEqual(row["node"], 1)
        poses, targets = self.posed["ghost_d:idle"]
        seat = rider.seat_frame(self.ce, self.ce["seats"][0])
        hull = rider.frame(None, [0.1, 0, 0.3])
        marker = hull @ rider.frame(nodes.matrix(nodes.unit(row["rotation"])), row["translation"])
        want = seat @ poses[0].world("wrist_l")
        np.testing.assert_allclose(marker, want, atol=1e-9)
        self.assertAlmostEqual(row["fk_distance_cm"], 0, places=6)

    def test_a_proxy_with_an_ik_point_rides_the_point_s_node(self):
        self.ce["seats"][0]["ik_points"] = [{"marker": "left hand", "attached_to": "grip"}]
        _, limbs, posed = rider.build(self.ce, self.donor, {"seat": "ghost_d:idle"}, {}, manifest())
        row = limbs["spartan_hand_left"]
        self.assertEqual((row["node_name"], row["node"]), ("frame steering", 6))
        steering = rider.frame(nodes.matrix(nodes.unit(turn_y(-10))), [0.7, 0, 1.1])
        marker = steering @ rider.frame(nodes.matrix(nodes.unit(row["rotation"])), row["translation"])
        poses, targets = posed["ghost_d:idle"]
        seat = rider.seat_frame(self.ce, self.ce["seats"][0])
        np.testing.assert_allclose(marker[:3, 3], (seat @ targets[0]["bip01 l hand"])[:3, 3], atol=1e-9)
        np.testing.assert_allclose(marker[:3, :3], (seat @ poses[0].world("wrist_l"))[:3, :3], atol=1e-9)

    def test_a_scaling_donor_is_refused(self):
        _, animation = spartan()
        animation["tracks"][1]["scale"] = {"static": 2.0}
        with self.assertRaises(ValueError):
            rider.Pose(self.skeleton, animation["tracks"], 0)


if __name__ == "__main__":
    unittest.main()
