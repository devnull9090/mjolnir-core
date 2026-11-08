#!/usr/bin/env python3
"""gen_ce_level.spawn_plan: which game types spawn players at each start
(#360). Run from tools/level: python -m unittest test_spawn_sets."""
import collections
import unittest

import gen_ce_level as g


def start(x, types, team=0, spawn_types=None):
    s = {"pos": [float(x), 0.0, 0.0], "facing": 0.0, "team": team, "game_types": list(types) + ["None"] * (4 - len(types))}
    if spawn_types is not None:
        s["spawn_types"] = spawn_types
    return s


def summary(spawns):
    return collections.Counter((s["label"], s["hidden"]) for s in spawns)


class CeSpawnSets(unittest.TestCase):
    def test_blood_gulch(self):
        # CTF base starts, Slayer's (All except CTF and Race) and Race's.
        starts = [start(1, ["Ctf"], 0), start(2, ["Ctf"], 1),
                  start(3, ["AllGamesExceptCtfAndRace"]), start(4, ["Race"])]
        spawns, sets = g.spawn_plan(starts, halo2=False)
        self.assertEqual(sets, [{"label": "spawn_set_0", "families": ["king", "oddball", "slayer"]},
                                {"label": "spawn_set_1", "families": ["race"]}])
        self.assertEqual(summary(spawns), collections.Counter({
            ("ctf_spawn_red", True): 1, ("ctf_spawn_blue", True): 1,
            ("spawn_set_0", True): 1, ("spawn_set_1", True): 1}))

    def test_every_game_type_is_shown(self):
        # All games: every game spawns here, CTF with its team.
        spawns, sets = g.spawn_plan([start(1, ["AllGames"], 1), start(2, ["AllGamesExceptCtf"])], halo2=False)
        self.assertEqual(sets, [])
        self.assertEqual(summary(spawns), collections.Counter({
            ("ctf_spawn_blue", False): 1, ("ctf_spawn_none", False): 1}))

    def test_ctf_and_some_others_split(self):
        # Coldsnap's CTF + Oddball starts: one hidden spawn for CTF, one for Oddball.
        spawns, sets = g.spawn_plan([start(1, ["Ctf", "Oddball"], 0), start(2, ["AllGamesExceptCtf"])],
                                    halo2=False)
        self.assertEqual(sets, [{"label": "spawn_set_0", "families": ["oddball"]}])
        self.assertEqual(summary(spawns), collections.Counter({
            ("ctf_spawn_red", True): 1, ("spawn_set_0", True): 1, ("ctf_spawn_none", False): 1}))

    def test_one_position_unites_its_starts(self):
        # Two starts on one spot: one spawn serving both, keeping the CTF team.
        spawns, _ = g.spawn_plan([start(1, ["Ctf"], 1), start(1, ["AllGamesExceptCtf"], 0)], halo2=False)
        self.assertEqual(summary(spawns), collections.Counter({("ctf_spawn_blue", False): 1}))

    def test_ctf_start_without_a_team_is_not_placed(self):
        spawns, _ = g.spawn_plan([start(1, ["Ctf"], 3), start(2, ["AllGamesExceptCtf"])], halo2=False)
        self.assertEqual(summary(spawns), collections.Counter({("ctf_spawn_none", False): 1}))

    def test_a_family_without_starts_spawns_with_slayer(self):
        # No King or Race starts: both take Slayer's.
        spawns, sets = g.spawn_plan([start(1, ["Slayer"]), start(2, ["Oddball"]), start(3, ["Ctf"], 0)],
                                    halo2=False)
        self.assertEqual({tuple(s["families"]) for s in sets},
                         {("king", "race", "slayer"), ("oddball",)})

    def test_only_ctf_starts_are_shown(self):
        spawns, sets = g.spawn_plan([start(1, ["Ctf"], 0), start(2, ["Ctf"], 1)], halo2=False)
        self.assertEqual(sets, [])
        self.assertFalse(any(s["hidden"] for s in spawns))

    def test_no_game_type_named_takes_every_start(self):
        # CE starts that list no game type at all: every game spawns there,
        # as before, with no CTF team.
        spawns, _ = g.spawn_plan([start(1, []), start(2, [])], halo2=False)
        self.assertEqual(summary(spawns), collections.Counter({("ctf_spawn_none", False): 2}))

    def test_ce_has_no_juggernaut_family(self):
        self.assertNotIn("juggernaut", g.start_families(start(1, ["AllGames"]), halo2=False))


class H2SpawnSets(unittest.TestCase):
    def test_no_game_type_is_every_game_type(self):
        # Terminal: untyped starts beside All games ones; both are every game's.
        spawns, sets = g.spawn_plan([start(1, []), start(2, ["AllGames"], 1)], halo2=True)
        self.assertEqual(sets, [])
        self.assertEqual(summary(spawns), collections.Counter({
            ("ctf_spawn_red", False): 1, ("ctf_spawn_blue", False): 1}))

    def test_juggernaut_starts(self):
        spawns, sets = g.spawn_plan([start(1, ["Juggernaut"]), start(2, ["Slayer", "Oddball", "King"])],
                                    halo2=True)
        self.assertEqual({tuple(s["families"]) for s in sets},
                         {("juggernaut",), ("king", "oddball", "race", "slayer")})

    def test_territories_and_headhunter_are_not_placed(self):
        spawns, _ = g.spawn_plan([start(1, ["Territories"]), start(2, ["Headhunter"]), start(3, ["AllGames"])],
                                 halo2=True)
        self.assertEqual(len(spawns), 1)


if __name__ == "__main__":
    unittest.main()
