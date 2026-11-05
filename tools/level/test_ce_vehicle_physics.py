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
