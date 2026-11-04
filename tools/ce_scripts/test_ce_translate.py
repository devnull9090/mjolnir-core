"""Tests for ce_translate.py. Run: python tools/ce_scripts/test_ce_translate.py

The synthetic cases run anywhere. With CE_YOY_MAP naming Yoyorast Island V2's
.map, the translation is also held against tools/level/data/yoy.hsc, the script
written by hand and proven in game.
"""
import collections
import json
import os
import re
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "level"))
import ce_translate as ct  # noqa: E402
from ce_hs import Call, Lit  # noqa: E402


def lit(text, vtype="object_name"):
    return Lit(text, vtype)


def real(v):
    return Lit(repr(float(v)), "real")


def flag(text):
    return Lit(text, "boolean", True)


def translator(scripts, globals_=(), objects=None, flags=None, volumes=None):
    """A Translator over a hand-built script, with no map behind it."""
    t = ct.Translator.__new__(ct.Translator)
    t.objects = objects or {}
    t.names = list(t.objects)
    t.flags = flags or {}
    t.volumes = volumes or {}
    t.groups = set()
    console = json.load(open(os.path.join(ct.REPO, "defs", "hce", "console.json")))
    t.console = {f["name"]: f for f in console["functions"]}
    t.tag_paths = {"ce\\effect": "cu4\\effect"}
    t.string_ids = {"known"}
    t.notes = collections.defaultdict(collections.Counter)
    t.dropped, t.rules, t.startup, t.promote = {}, [], [], set()
    t.script_names = {}
    t.globals = [list(g) for g in globals_]
    t.scripts = [ct.Script(n, k, "void", b) for n, k, b in scripts]
    t.animated = lambda name: False
    return t


def obj(kind, at=(0, 0, 0), index=0, not_placed=0):
    return {"kind": kind, "index": index, "position": list(at), "rotation": [0, 0, 0], "not_placed": not_placed}


class Fold(unittest.TestCase):
    def test_a_false_condition_takes_its_branch(self):
        e = ct.fold(Call("if", [ct.FALSE, Call("sleep", [real(1)]), Call("wake", [lit("a", "script")])]))
        self.assertEqual(e.fn, "wake")

    def test_equals_true_is_the_condition(self):
        e = ct.fold(Call("=", [Call(">", [real(1), flag("x")], "boolean"), ct.TRUE]))
        self.assertEqual(e.fn, ">")

    def test_arithmetic(self):
        self.assertEqual(float(ct.fold(Call("*", [real(30), real(20)])).text), 600.0)

    def test_empty_else_goes(self):
        e = ct.fold(Call("if", [flag("x"), Call("sleep", [real(1)]), Lit("", "void")]))
        self.assertEqual(len(e.args), 2)


class Host(unittest.TestCase):
    def test_a_health_probe_flag_is_true_and_client_scripts_go(self):
        probe = Call("if", [Call(">=", [Call("unit_get_health", [lit("hog", "unit")]), real(0)]),
                            Call("set", [flag("up"), ct.TRUE])])
        host_side = Call("if", [Call("=", [flag("up"), ct.TRUE]), Call("device_set_power", [lit("sw", "device"), real(1)])])
        client = Call("if", [Call("=", [flag("up"), ct.FALSE]), Call("device_set_power", [lit("sw", "device"), real(0)])])
        t = translator([("probe", "startup", [probe]), ("a", "continuous", [host_side]), ("b", "continuous", [client])],
                       [["up", "boolean", ct.FALSE]], {"hog": obj("vehicle"), "sw": obj("control")})
        t.run()
        text = t.text()
        self.assertNotIn("(global", text)
        self.assertIn("(device_set_power sw 1.0)", text)
        self.assertNotIn("(device_set_power sw 0.0)", text)
        self.assertEqual(sorted(s.name for s in t.scripts), ["a"])


class HostNames(unittest.TestCase):
    def test_a_ghost_is_not_a_host(self):
        self.assertIsNone(ct.HOST_OBJECT.search("ghostbase_biped"))
        self.assertTrue(ct.HOST_OBJECT.search("is_server_biped"))
        self.assertTrue(ct.HOST_OBJECT.search("host_check_2"))


def door(on, off):
    """YOY's check and sync scripts around one control."""
    pos = Call("device_get_position", [lit("c", "device")])
    check = Call("if", [Call("=", [pos, real(1)]),
                        Call("begin", [Call("object_teleport", [lit("k", "object"), lit("open_flag", "cutscene_flag")]),
                                       Call("sleep", [Lit("15", "short")])]),
                        Call("begin", [Call("object_teleport", [lit("k", "object"), lit("shut_flag", "cutscene_flag")]),
                                       Call("sleep", [Lit("15", "short")])])])

    def branch(biped, to):
        return Call("if", [Call("<", [Call("unit_get_health", [lit(biped, "unit")]), real(0.1)]),
                           Call("begin", [Call("device_set_position", [lit("m", "device"), real(to)]),
                                          Call("object_create_anew", [lit(biped)])])])
    return [("x_check", "continuous", [check]),
            ("x_sync", "continuous", [branch("open_b", on), branch("shut_b", off)])]


OBJECTS = {"c": obj("control"), "m": obj("machine"), "k": obj("vehicle", (50, 0, 0)), "open_b": obj("biped", (0, 0, 0)),
           "shut_b": obj("biped", (20, 0, 0))}
FLAGS = {"open_flag": {"position": [0, 0, 1]}, "shut_flag": {"position": [20, 0, 1]}}


class Sync(unittest.TestCase):
    def test_a_check_and_sync_pair_is_one_rule(self):
        t = translator(door(1, 0), objects=OBJECTS, flags=FLAGS)
        t.run()
        self.assertEqual([s.name for s in t.scripts], ["m_rule"])
        text = t.text()
        self.assertIn("(device_set_position m 1.0)", text)
        self.assertLess(text.index("m 1.0"), text.index("m 0.0"))

    def test_an_inverted_door_starts_up_and_keeps_its_direction(self):
        t = translator(door(0, 1), objects=OBJECTS, flags=FLAGS)
        t.run()
        text = t.text()
        self.assertLess(text.index("(device_set_position m 0.0"), text.index("(device_set_position m 1.0"))
        self.assertIn("(device_set_position_immediate m 1.0)", text)

    def test_a_wait_on_a_signal_just_sent_is_over(self):
        body = [Call("object_create_anew", [lit("k")]),
                Call("sleep_until", [Call("<=", [Call("unit_get_health", [lit("open_b", "unit")]), real(0)])]),
                Call("device_set_power", [lit("c", "device"), real(0)])]
        objects = dict(OBJECTS, k=obj("vehicle", (0, 0, 1)))
        t = translator([("s", "continuous", body)], objects=objects, flags=FLAGS)
        t.run()
        self.assertNotIn("sleep_until", t.text())
        self.assertNotIn("sig_", t.text())
        self.assertIn("device_set_power", t.text())

    def test_a_signal_another_script_reads_stays(self):
        send = Call("object_teleport", [lit("k", "object"), lit("open_flag", "cutscene_flag")])
        hear = Call("if", [Call("<", [Call("unit_get_health", [lit("open_b", "unit")]), real(0.1)]),
                           Call("device_set_power", [lit("c", "device"), real(0)])])
        t = translator([("a", "startup", [Call("sleep", [Lit("5", "short")]), send]), ("b", "continuous", [hear])],
                       objects=OBJECTS, flags=FLAGS)
        t.run()
        self.assertIn("(global boolean sig_open_b false)", t.text())
        self.assertIn("(set sig_open_b true)", t.text())


class Names(unittest.TestCase):
    def test_a_name_with_no_carried_placement_costs_the_statement_only(self):
        body = [Call("unit_set_enterable_by_player", [lit("hog", "unit"), ct.FALSE]),
                Call("device_set_power", [lit("c", "device"), real(0)])]
        t = translator([("s", "continuous", body)], objects={"hog": obj("vehicle"), "c": obj("control")})
        t.run()
        self.assertNotIn("hog", t.text())
        self.assertIn("device_set_power", t.text())
        self.assertEqual(t.notes["not carried: vehicle"]["hog"], 1)

    def test_scenery_a_script_destroys_is_promoted_and_parked(self):
        body = [Call("object_destroy", [lit("floor")]), Call("sleep", [Lit("5", "short")]),
                Call("object_create_anew", [lit("floor")])]
        t = translator([("s", "continuous", body)], objects={"floor": obj("scenery")})
        t.run()
        self.assertEqual(t.promote, {"floor"})
        self.assertIn("(device_set_position_immediate floor 0.0)", t.text())
        self.assertEqual(t.scripts[0].name, "devices_start")

    def test_containing_expands_over_names(self):
        body = [Call("object_create_containing", [lit("gate", "string")])]
        t = translator([("s", "continuous", body)], objects={"gate_a": obj("machine"), "gate_b": obj("machine"), "x": obj("machine")})
        t.containing()
        self.assertEqual([x.args[0].text for x in t.scripts[0].body], ["gate_a", "gate_b"])

    def test_a_dropped_script_takes_its_wake(self):
        gone = ("d", "dormant", [Call("unit_kill", [lit("hog", "unit")])])
        wake = ("s", "continuous", [Call("wake", [lit("d", "script")]), Call("device_set_power", [lit("c", "device"), real(0)])])
        t = translator([gone, wake], objects={"hog": obj("vehicle"), "c": obj("control")})
        t.run()
        self.assertEqual([s.name for s in t.scripts], ["s"])
        self.assertNotIn("wake", t.text())


class Functions(unittest.TestCase):
    def test_a_rename_and_a_seat(self):
        e = Call("vehicle_test_seat_list", [lit("c", "vehicle"), lit("w-driver", "string"), Call("players", [])])
        t = translator([("s", "continuous", [Call("sleep_until", [e]), Call("sleep", [Lit("1", "short")]),
                                             Call("show_hud", [ct.FALSE])])], objects={"c": obj("control")})
        t.run()
        self.assertIn('(vehicle_test_seat_unit_list c "" (players))', t.text())
        self.assertIn("(chud_show false)", t.text())

    def test_a_tag_literal_is_mapped_or_its_statement_goes(self):
        hit = Call("effect_new", [lit("ce\\effect", "effect"), lit("f", "cutscene_flag")])
        miss = Call("effect_new", [lit("ce\\custom", "effect"), lit("f", "cutscene_flag")])
        t = translator([("s", "continuous", [hit, miss])], flags={"f": {"position": [0, 0, 0]}})
        t.run()
        self.assertIn('"cu4\\effect"', t.text())
        self.assertNotIn("custom", t.text())
        self.assertEqual(t.notes["no CU4 tag: effect"]["ce\\custom"], 1)

    def test_a_string_id_the_game_has_not_registered_gets_a_registrar(self):
        e = Call("object_set_permutation", [lit("c", "object"), lit("known", "string_id"), lit("novel", "string_id")])
        t = translator([("s", "continuous", [e])], objects={"c": obj("control")})
        t.run()
        self.assertIn("(script static void novel", t.text())
        self.assertNotIn("(script static void known", t.text())


class Machines(unittest.TestCase):
    def test_a_turn_is_read_about_its_axis(self):
        import math
        import ce_machines

        def frame(deg):
            h = math.radians(deg) / 2
            return [{"t": [0, 0, 0], "q": [0, 0, math.sin(h), math.cos(h)]}]
        frames = [frame(d) for d in (0, 90, 180, 270)]
        kind, axis, angles = ce_machines.part_motion(frames, 0)
        self.assertEqual(kind, "turn")
        self.assertAlmostEqual(abs(axis[2]), 1.0)
        self.assertEqual([round(a) for a in angles], [0, 90, 180, 270])

    def test_a_slide_keeps_its_offsets(self):
        import ce_machines
        frames = [[{"t": [0, 0, 0], "q": [0, 0, 0, 1]}], [{"t": [0, 0.4, 0], "q": [0, 0, 0, 1]}]]
        self.assertEqual(ce_machines.part_motion(frames, 0), ("slide", [[0, 0, 0], [0, 0.4, 0]]))


def rules(text):
    """Each rule of a script text: control -> (position on, position off)."""
    out = {}
    for m in re.finditer(r"\(if\s+\(= \(device_get_position (\w+)\) 1\.0\)\s+"
                         r"\(device_set_position (\w+) ([\d.]+)\)\s+\(device_set_position \w+ ([\d.]+)\)", text):
        out[m.group(1)] = (m.group(2), float(m.group(3)), float(m.group(4)))
    return out


def resets(text):
    return {m.group(1): m.group(2) for m in re.finditer(
        r"\(sleep_until \(= \(device_get_position (\w+)\) 1\.0\)\)\s+\(sleep (\d+)\)\s+\(device_set_position \1 0\.0\)", text)}


@unittest.skipUnless(os.environ.get("CE_YOY_MAP"), "set CE_YOY_MAP to Yoyorast Island V2's .map")
class Yoyorast(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        t = ct.Translator(os.environ["CE_YOY_MAP"])
        t.run()
        cls.made, cls.t = t.text(), t
        cls.hand = open(os.path.join(ct.REPO, "tools", "level", "data", "yoy.hsc"), encoding="utf-8").read()

    def test_the_same_rules_as_the_script_written_by_hand(self):
        self.assertEqual(len(rules(self.hand)), 10)
        self.assertEqual(rules(self.made), rules(self.hand))

    def test_the_same_resets(self):
        self.assertEqual(resets(self.made), resets(self.hand))

    def test_gatepath_starts_closed(self):
        self.assertIn("(device_set_position_immediate gatepath_machine 1.0)", self.made)

    def test_the_sync_layer_is_gone(self):
        for word in ("crusher", "_biped", "is_server", "check_1", "optimize_"):
            self.assertNotIn(word, self.made)

    def test_the_teleporter_and_kill_volume_stay(self):
        self.assertIn("begin_random", self.made)
        self.assertIn("(object_teleport (unit (list_get (players) plyrnum)) thecrater)", self.made)
        self.assertIn("volume_test_object deathbox", self.made)


if __name__ == "__main__":
    unittest.main()
