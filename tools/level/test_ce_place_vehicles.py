"""ce_place_vehicles.py's plan: moves, drops, and refusing the wrong level."""
import math
import unittest

import ce_place_vehicles as tool


def row(name, tag, position):
    return {"name": name, "tag": tag, "position": position}


def vehicle(position):
    return {"type": "warthog", "pos": tool.to_ue(position), "yaw": 0, "set": {"a": "b"}}


PLAN = {"moves": {"m": {"flag": "f", "tag": "new"}}, "drop_tags": ["prop"], "drop_names": ["gone"]}
FLAGS = {"f": {"position": [10.0, -2.0, 5.3], "facing": [-math.pi / 2, 0.0]}}


class Relabel(unittest.TestCase):
    PLAN = {"moves": {"a": {"flag": "f", "tag": "goose", "label": "ce_warthog_1"},
                      "b": {"flag": "f", "tag": "goose", "label": "ce_warthog_1"},
                      "c": {"flag": "f"}},
            "drop_tags": ["prop"], "drop_names": ["pen"]}
    ROWS = [row("a", "t", [0, 0, 0]), row(None, "prop", [0, 0, 0]), row("b", "t", [0, 0, 0]),
            row("pen", "t", [0, 0, 0]), row("c", "t", [0, 0, 0])]

    def level(self, tags=("goose", "goose", None)):
        vehicles = [{"set": {tool.LABEL: f"ce_warthog_{i}"}} for i in range(1, 4)]
        for v, tag in zip(vehicles, tags):
            if tag:
                v["tag"] = tag
        return {"blam": {"vehicles": vehicles}, "vehicle_sets": [{"label": f"ce_warthog_{i}"} for i in range(1, 4)]}

    def test_rows_the_plan_dropped_are_skipped_and_the_label_is_shared(self):
        level = tool.relabel(self.level(), self.ROWS, self.PLAN)
        self.assertEqual([v["set"][tool.LABEL] for v in level["blam"]["vehicles"]],
                         ["ce_warthog_1", "ce_warthog_1", "ce_warthog_3"])
        self.assertEqual([r["label"] for r in level["vehicle_sets"]],
                         ["ce_warthog_1", "ce_warthog_1", "ce_warthog_3"])

    def test_refuses_another_count(self):
        with self.assertRaises(SystemExit):
            tool.relabel(self.level(), self.ROWS[:2], self.PLAN)

    def test_refuses_a_level_in_another_order(self):
        with self.assertRaises(SystemExit):
            tool.relabel(self.level(("goose", None, "goose")), self.ROWS, self.PLAN)


class Plan(unittest.TestCase):
    def apply(self, rows, vehicles=None, surfaces=lambda x, y: [0.0, 5.0, 9.0]):
        vehicles = vehicles or [vehicle(r["position"]) for r in rows]
        return tool.apply_plan(vehicles, [{"label": str(i)} for i in range(len(vehicles))], rows, FLAGS, PLAN, surfaces)

    def test_moves_keep_spawn_data_and_set_row(self):
        kept, sets, _ = self.apply([row("x", "prop", [1, 1, 1]), row("m", "t", [2, 2, 2]), row(None, "t", [3, 3, 3])])
        self.assertEqual(sets, [{"label": "1"}, {"label": "2"}])
        self.assertEqual(kept[0]["pos"], [3048.0, 609.6, 1615.4])
        self.assertEqual(kept[0]["yaw"], 90.0)
        self.assertEqual(kept[0]["tag"], "new")
        self.assertEqual(kept[0]["set"], {"a": "b"})
        self.assertEqual(kept[1]["pos"], tool.to_ue([3, 3, 3]))

    def test_a_label_goes_on_the_vehicle_and_its_set_row(self):
        plan = {"moves": {"m": {"flag": "f", "label": "ce_warthog_1"}}, "drop_tags": [], "drop_names": []}
        rows = [row("m", "t", [2, 2, 2])]
        vehicles = [vehicle(rows[0]["position"])]
        kept, sets, _ = tool.apply_plan(vehicles, [{"label": "old"}], rows, FLAGS, plan, lambda x, y: [0.0, 5.0, 9.0])
        self.assertEqual(kept[0]["set"][tool.LABEL], "ce_warthog_1")
        self.assertEqual(kept[0]["set"]["a"], "b")
        self.assertEqual(sets, [{"label": "ce_warthog_1"}])
        self.assertNotIn(tool.LABEL, vehicles[0]["set"])  # the input stays as it was

    def test_a_flag_on_the_ground_is_lifted(self):
        kept, _, _ = self.apply([row("m", "t", [2, 2, 2])], surfaces=lambda x, y: [5.29])
        self.assertAlmostEqual(kept[0]["pos"][2] / tool.CM, 5.34, places=2)

    def test_refuses_a_level_in_another_order(self):
        with self.assertRaises(SystemExit):
            self.apply([row("m", "t", [2, 2, 2])], vehicles=[vehicle([9, 9, 9])])

    def test_refuses_a_flag_over_nothing(self):
        with self.assertRaises(SystemExit):
            self.apply([row("m", "t", [2, 2, 2])], surfaces=lambda x, y: [0.0])


if __name__ == "__main__":
    unittest.main()
