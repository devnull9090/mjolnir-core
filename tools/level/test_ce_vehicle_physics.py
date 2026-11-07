#!/usr/bin/env python3
"""python tools/level/test_ce_vehicle_physics.py"""
import unittest

import ce_vehicle_physics as physics

CE = {"vehicle": {"mass": 2500.0, "forward_speed": 0.28, "reverse_speed": 0.12, "steering_left": 20.0,
                  "ground_friction": 0.23, "ground_depth": 0.1},
      "baseline": {"mass": 5000.0, "forward_speed": 0.275, "reverse_speed": 0.12, "steering_left": 30.0,
                   "ground_friction": 0.23, "ground_depth": 0.15}}


def vehicle():
    flat = {f"{physics.JEEP}.steering control.max steering angle at zero": "1.5",
            f"{physics.JEEP}.steering control.max steering angle at full speed": "0.6",
            f"{physics.JEEP}.turning control.maximum left turn": "1.2",
            f"{physics.JEEP}.turning control.maximum right turn (negative)": "-1.2",
            f"{physics.JEEP}.engine.engine moment": "1800",
            f"{physics.JEEP}.engine.engine max angular velocity": "9.3",
            f"{physics.JEEP}.engine.gears[0].gear ratio": "-0.5",
            f"{physics.HAVOK}.ground friction": "3.45",
            f"{physics.HAVOK}.ground depth": "0.125",
            "unit.seats[0].label": "warthog_d",
            "unit.seats[1].label": "warthog_p"}
    for i in range(4):
        flat[f"{physics.HAVOK}.friction points[{i}].radius"] = "0.25"
        flat[f"{physics.HAVOK}.friction points[{i}].damaged radius"] = "0.1"
    return flat


class Fighter(unittest.TestCase):
    FLAT = {f"{physics.FIGHTER}.maximum forward speed": "5", f"{physics.FIGHTER}.speed acceleration": "15",
            f"{physics.FIGHTER}.speed deceleration": "25", f"{physics.FIGHTER}.turning control.turn rate": "9.424778"}
    NUMBERS = {"vehicle": {"forward_speed": 4.0, "acceleration": 0.32, "deceleration": 0.36, "turn_rate": 0.2},
               "baseline": {"forward_speed": 0.22, "acceleration": 0.008, "deceleration": 0.016, "turn_rate": 0.13}}

    def values(self, forward=None):
        sets = physics.fighter_sets(self.FLAT, self.NUMBERS, forward)
        return {s.split("=")[0].rsplit(".", 1)[-1]: float(s.split("=")[1]) for s in sets}

    def test_each_number_is_the_shipped_one_times_ce_over_ce(self):
        got = self.values()
        self.assertAlmostEqual(got["maximum forward speed"], 90.909, 3)
        self.assertAlmostEqual(got["speed acceleration"], 600, 3)
        self.assertAlmostEqual(got["speed deceleration"], 562.5, 3)
        self.assertAlmostEqual(got["turn rate"], 14.4997, 3)

    def test_a_clamp_moves_top_speed_alone(self):
        got = self.values(35)
        self.assertEqual(got["maximum forward speed"], 35)
        self.assertAlmostEqual(got["speed acceleration"], 600, 3)


class Flatten(unittest.TestCase):
    def test_paths_cross_structs_and_blocks(self):
        tree = [{"kind": "field", "name": "mass", "value": "3300"},
                {"kind": "struct", "name": "base", "children": [
                    {"kind": "field", "name": "volume ", "value": "1"}]},
                {"kind": "block", "name": "seats", "children": [
                    {"children": [{"kind": "field", "name": "label", "value": '"warthog_d"'}]}]}]
        self.assertEqual(physics.flatten(tree),
                         {"mass": "3300", "base.volume": "1", "seats[0].label": "warthog_d"})


class StretchMaths(unittest.TestCase):
    stretch = physics.Stretch([-1, -2, 0], [1, 2, 4], [0, -1, 1], [1, 1, 3])

    def test_the_box_lands_on_the_box(self):
        self.assertEqual(self.stretch.point([-1, -2, 0]), [0, -1, 1])
        self.assertEqual(self.stretch.point([1, 2, 4]), [1, 1, 3])

    def test_a_point_on_a_plane_stays_on_it(self):
        n, d = [0.6, 0.0, 0.8], -1.0
        point = [1.0, 0.5, 0.5]  # n.p + d = 0
        m, w = physics.Stretch.plane(self.stretch, n, d)
        p = self.stretch.point(point)
        self.assertAlmostEqual(sum(a * b for a, b in zip(m, p)) + w, 0.0)
        self.assertAlmostEqual(sum(a * a for a in m), 1.0)

    def test_a_box_keeps_its_smallest_half_in_w_and_its_radius_in_its_volume(self):
        box = {"boxes[0].half extents": "(2, 1, 4)",
               "boxes[0].box shape.radius": "0.5",
               "boxes[0].convex transform shape.rotation i": "(1, 0, 0)",
               "boxes[0].convex transform shape.translation": "(0, 0, 0)",
               "polyhedra[0].base.volume": "1",
               "polyhedra[0].polyhedron shape.radius": "0",
               "polyhedra[0].aabb center": "(0, 0, 0)",
               "polyhedra[0].aabb half extents": "(1, 1, 1)",
               "lists[0].aabb center": "(0, 0, 0)",
               "lists[0].aabb half extents": "(1, 1, 1)",
               "list shapes[0].shape reference.shape type": "box (2)",
               "list shapes[0].shape reference.shape": "#0",
               "boxes[0].base.volume": "1",
               "mass distributions[0].center of mass": "(0, 0, 0)",
               "mass distributions[0].inertia tensor i": "(1, 0, 0)",
               "mass distributions[0].inertia tensor j": "(0, 1, 0)",
               "mass distributions[0].inertia tensor k": "(0, 0, 1)"}
        same = physics.Stretch([0, 0, 0], [1, 1, 1], [0, 0, 0], [1, 1, 1])
        sets = physics.physics_sets(box, same, 1.0, [0, 0, 0])
        self.assertIn("boxes[0].havok w half extents=1.000000", sets)
        self.assertIn(f"boxes[0].base.volume={8 * 2.5 * 1.5 * 4.5:.6f}", sets)

    def test_a_box_tensor_stretches_as_a_box(self):
        def tensor(h):
            return [[(h[1] ** 2 + h[2] ** 2) / 3, 0, 0], [0, (h[0] ** 2 + h[2] ** 2) / 3, 0],
                    [0, 0, (h[0] ** 2 + h[1] ** 2) / 3]]
        got = self.stretch.inertia(tensor([1, 2, 3]))
        want = tensor(self.stretch.size([1, 2, 3]))
        for row, expected in zip(got, want):
            for a, b in zip(row, expected):
                self.assertAlmostEqual(a, b)


class WheelBoxes(unittest.TestCase):
    """Four boxes turned 45 degrees by the wheels and a square one for the
    proxy body, on a donor twice the clone's size."""
    DONOR = {"fl": (2.0, 1.0, 0.5), "fr": (2.0, -1.0, 0.5), "bl": (-2.0, 1.0, 0.5), "br": (-2.0, -1.0, 0.5)}
    # The clone's rear wheels sit further back than a uniform shrink would put them.
    CLONE = {"fl": (1.0, 0.5, 0.25), "fr": (1.0, -0.5, 0.25), "bl": (-1.5, 0.5, 0.25), "br": (-1.5, -0.5, 0.25)}
    TURNED = ("(0.707107, 0, 0.707107)", "(0, 1, 0)", "(-0.707107, 0, 0.707107)")

    def flat(self):
        flat = {}
        spots = [(2.0, -0.8, 0.7), (2.0, 0.8, 0.7), (-2.0, -0.8, 0.7), (-2.0, 0.8, 0.7)]
        for i, at in enumerate(spots):
            p = f"boxes[{i}]"
            flat[p + ".half extents"] = "(0.2, 0.2, 0.2)"
            flat[p + ".box shape.radius"] = "0.01"
            flat[p + ".convex transform shape.translation"] = str(at)
            for axis, row in zip("ijk", self.TURNED):
                flat[f"{p}.convex transform shape.rotation {axis}"] = row
        p = "boxes[4]"
        flat[p + ".half extents"] = "(2, 1, 0.5)"
        flat[p + ".box shape.radius"] = "0.05"
        flat[p + ".convex transform shape.translation"] = "(0, 0, 0.6)"
        for axis, row in zip("ijk", ("(1, 0, 0)", "(0, 1, 0)", "(0, 0, 1)")):
            flat[f"{p}.convex transform shape.rotation {axis}"] = row
        return flat

    def centres(self):
        return physics.wheel_boxes(self.flat(), 0.5, self.DONOR, self.CLONE, 0.5)

    def test_only_the_turned_boxes_move(self):
        self.assertEqual(sorted(self.centres()), [0, 1, 2, 3])

    def test_a_turned_box_reaches_further_than_its_half(self):
        self.assertAlmostEqual(physics.box_reach(self.flat(), 0)[2], 0.2 * 2 ** 0.5 + 0.01, places=5)

    def test_each_foot_stays_under_its_marker_so_a_wheel_cannot_pass_the_ground(self):
        flat = self.flat()
        donor_gap = 0.5 - (0.7 - physics.box_reach(flat, 0)[2])
        self.assertGreater(donor_gap, 0)
        for i, centre in self.centres().items():
            foot = centre[2] - physics.box_reach(flat, i, 0.5)[2]
            self.assertAlmostEqual(0.25 - foot, donor_gap * 0.5, places=5)

    def test_a_box_follows_its_wheel_not_the_hull(self):
        centres = self.centres()
        self.assertAlmostEqual(centres[2][0], -1.5)  # the back wheel, not half the donor's
        self.assertAlmostEqual(centres[2][1], -0.4)
        self.assertAlmostEqual(centres[1][1], 0.4)

    def test_the_lists_box_grows_round_them(self):
        flat, centres = self.flat(), self.centres()
        sets = dict(s.split("=", 1) for s in physics.wheel_box_sets(flat, 0.5, centres, [0, 0, 1], [2, 1, 0.5]))
        centre, half = physics.vec(sets["lists[0].aabb center"]), physics.vec(sets["lists[0].aabb half extents"])
        foot = min(c[2] - physics.box_reach(flat, i, 0.5)[2] for i, c in centres.items())
        self.assertAlmostEqual(centre[2] - half[2], foot, places=5)
        self.assertAlmostEqual(centre[2] + half[2], 1.5, places=5)  # the top stays
        self.assertEqual(physics.vec(sets["boxes[2].convex transform shape.translation"])[0], -1.5)


class Handling(unittest.TestCase):
    def sets(self):
        lines = physics.vehicle_sets(vehicle(), CE, 0.17)
        return dict(line.split("=", 1) for line in lines)

    def test_a_value_moves_by_the_ce_ratio(self):
        s = self.sets()
        self.assertAlmostEqual(float(s[f"{physics.JEEP}.engine.engine moment"]), 900)
        self.assertAlmostEqual(float(s[f"{physics.JEEP}.turning control.maximum left turn"]), 0.8)
        self.assertAlmostEqual(float(s[f"{physics.JEEP}.turning control.maximum right turn (negative)"]), -0.8)
        self.assertAlmostEqual(float(s[f"{physics.HAVOK}.ground depth"]), 0.083333, 5)

    def test_reverse_keeps_ce_speed_when_the_engine_speeds_up(self):
        s = self.sets()
        top = float(s[f"{physics.JEEP}.engine.engine max angular velocity"]) / 9.3
        gear = float(s[f"{physics.JEEP}.engine.gears[0].gear ratio"]) / -0.5
        self.assertAlmostEqual(top * gear, 1.0, 5)

    def test_tyres_take_the_drawn_radius_and_seats_keep_their_prompts(self):
        s = self.sets()
        self.assertEqual(s[f"{physics.HAVOK}.friction points[3].radius"], "0.170000")
        self.assertAlmostEqual(float(s[f"{physics.HAVOK}.friction points[3].damaged radius"]), 0.068)
        self.assertNotIn("unit.seats[0].enter seat string", s)
        self.assertNotIn("flip message", s)

    def test_the_ground_is_the_donors(self):
        ground = physics.contact_height(vehicle(), 0.222678)
        self.assertAlmostEqual(ground, -0.027322)


if __name__ == "__main__":
    unittest.main()
