#!/usr/bin/env python3
import copy
import unittest

import fix_teleporter_teams as ft
from ce_objectives import MARKER_TEAM

TEAM = ft.TEAM


def tele(kind, **extra):
    return {"group": "scenery", "tag": ft.TELEPORTERS + kind,
            "set": {"multiplayer data.teleporter channel": "alpha", **extra}}


def level():
    spawn = {"group": "scenery", "tag": "objects\\multi\\spawning\\player_spawn", "set": {TEAM: "neutral"}}
    stand = {"group": "scenery", "tag": "objects\\multi\\ctf\\flag_stand", "set": {TEAM: "attacker"}}
    machine = {"group": "machines", "tag": "levels\\x\\door"}
    return {"modes": ["ctf"], "blam": {"objects": [
        spawn, tele("teleporter_sender"), stand, tele("teleporter_receiver"), machine,
        tele("teleporter_2way", **{TEAM: "neutral"})], "single_bsp": 0}}


class TeleporterTeams(unittest.TestCase):
    def test_every_end_goes_to_the_eighth_team(self):
        new, moved = ft.park(level())
        self.assertEqual(moved, 3)
        teams = [o.get("set", {}).get(TEAM) for o in new["blam"]["objects"]]
        self.assertEqual(teams, ["neutral", MARKER_TEAM, "attacker", MARKER_TEAM, None, MARKER_TEAM])

    def test_park_leaves_its_input_alone_and_is_idempotent(self):
        old = level()
        before = copy.deepcopy(old)
        new, _ = ft.park(old)
        self.assertEqual(old, before)
        self.assertEqual(ft.park(new), (new, 0))

    def test_only_teleporter_teams_may_change(self):
        old = level()
        self.assertEqual(ft.level_changes(old, ft.park(old)[0]), [])

    def test_another_objects_team_changing_stops_the_pack(self):
        old = level()
        new = ft.park(old)[0]
        new["blam"]["objects"][2]["set"][TEAM] = MARKER_TEAM
        self.assertTrue(ft.level_changes(old, new))

    def test_another_teleporter_field_changing_stops_the_pack(self):
        old = level()
        new = ft.park(old)[0]
        new["blam"]["objects"][1]["set"]["multiplayer data.teleporter channel"] = "bravo"
        self.assertTrue(ft.level_changes(old, new))

    def test_an_end_left_off_the_eighth_team_stops_the_pack(self):
        old = level()
        new = ft.park(old)[0]
        new["blam"]["objects"][3]["set"][TEAM] = "defender"
        self.assertTrue(ft.level_changes(old, new))

    def test_a_lost_object_or_other_key_stops_the_pack(self):
        old = level()
        new = ft.park(old)[0]
        del new["blam"]["objects"][4]
        self.assertTrue(ft.level_changes(old, new))
        new = ft.park(old)[0]
        new["modes"].append("slayer")
        self.assertTrue(ft.level_changes(old, new))

    def test_forge_pieces_named_for_teleporters_are_not_ends(self):
        crate = {"group": "crates", "tag": "objects\\mjolnir\\forge\\foundry-wide\\teleporter_pad_wide",
                 "set": {TEAM: "neutral"}}
        old = {"blam": {"objects": [crate]}}
        self.assertEqual(ft.park(old), (old, 0))


if __name__ == "__main__":
    unittest.main()
