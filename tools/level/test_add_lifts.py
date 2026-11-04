"""Adding lifts to a published level file must leave the rest of it as shipped."""
import json
import unittest

import add_lifts

LIFT = {"asset": "objects\\lift", "pos": [1.0, 2.0, 3.0], "rot": [0.0, 0.0, 0.0], "scale": 1.0, "phantoms": [{
    "shape": {"planes": [[0.0, 0.0, 1.0, -1.0]], "bounds": [[0.0, 0.0, 0.0], 1.0]},
    "origin": [0.0, 0.0, 0.0], "forward": [0.0, 0.0, 1.0], "center": [0.0, 0.0], "axis": [10.0, 10.0],
    "direction": [10.0, 4.0], "negates_gravity": True}]}
TRANSFORM = {"delta": [0.0, 0.0, 1.0]}


class WithLiftsTests(unittest.TestCase):
    def test_every_shipped_byte_stays_whatever_the_file_layout(self):
        for shipped in (b'{\r\n  "name": "x",\r\n  "n": 1.50\r\n}\r\n', b'{\n "name": "x",\n "n": 1.50\n}'):
            new, lifts = add_lifts.with_lifts(shipped, {"lifts": [LIFT]}, TRANSFORM)
            self.assertTrue(new.startswith(shipped.rstrip()[:-1].rstrip()))
            self.assertEqual(json.loads(new)["lifts"], lifts)
            add_lifts.check_only_lifts(shipped, new)

    def test_the_conversion_delta_places_the_lift(self):
        new, _ = add_lifts.with_lifts(b'{"name": "x"}', {"lifts": [LIFT]}, TRANSFORM)
        self.assertEqual(json.loads(new)["lifts"][0]["origin"], [304.8, -609.6, 1219.2])

    def test_a_map_without_lifts_gets_no_file(self):
        self.assertEqual(add_lifts.with_lifts(b'{"name": "x"}', {}, TRANSFORM), (None, []))

    def test_refuses_a_level_that_has_lifts_or_a_canvas_origin(self):
        with self.assertRaisesRegex(ValueError, "already"):
            add_lifts.with_lifts(b'{"lifts": []}', {"lifts": [LIFT]}, TRANSFORM)
        with self.assertRaisesRegex(ValueError, "origin"):
            add_lifts.with_lifts(b'{"canvas": {"origin": [1, 0, 0]}}', {"lifts": [LIFT]}, TRANSFORM)

    def test_any_other_change_is_caught(self):
        with self.assertRaisesRegex(ValueError, "beyond"):
            add_lifts.check_only_lifts(b'{"n": 1}', b'{"n": 2, "lifts": []}')


if __name__ == "__main__":
    unittest.main()
