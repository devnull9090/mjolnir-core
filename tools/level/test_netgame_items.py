#!/usr/bin/env python3
"""gen_ce_level's netgame equipment: the game types that place a pickup, the
sets they share with the spawn points, respawn times and the starting kits.
Run from tools/level: python -m unittest test_netgame_items."""
import unittest

import add_netgame
import build_weapon_respawn
import gen_ce_level as g

WEAPONS = ["assault_rifle", "battle_rifle", "smg", "magnum", "sniper_rifle", "shotgun", "rocket_launcher",
           "plasma_rifle", "plasma_rifle_red", "plasma_pistol", "needler"]


def resolve(section, asset):
    return {"w/ar": "assault_rifle", "w/pistol": "magnum", "w/smg": "smg", "w/br": "battle_rifle",
            "w/pp": "plasma_pistol", "w/shotgun": "shotgun", "w/needler": "needler"}.get(asset)


def entry(types, weapons, flags=0):
    return {"game_types": list(types), "flags": flags, "no_grenades": bool(flags & 1),
            "plasma_grenades": bool(flags & 2),
            "item_collections": [{"item_collection": w, "items": [{"asset": w, "tag_class": "weap", "weight": 100.0}]}
                                 for w in weapons]}


class Families(unittest.TestCase):
    def test_ce_game_types(self):
        self.assertEqual(g.item_families(["AllGames"], False), {"ctf", "slayer", "oddball", "king", "race"})
        self.assertEqual(g.item_families(["AllGamesExceptCtf"], False), {"slayer", "oddball", "king", "race"})
        self.assertEqual(g.item_families(["AllGamesExceptCtfAndRace"], False), {"slayer", "oddball", "king"})
        self.assertEqual(g.item_families(["Ctf", "Race", "None", "None"], False), {"ctf", "race"})
        # CE's Juggernaut is Oddball's engine, and Terminator was never played.
        self.assertEqual(g.item_families(["Juggernaut", "Terminator"], False), set())

    def test_halo2_game_types(self):
        every = {"ctf", "slayer", "oddball", "king", "race", "juggernaut"}
        self.assertEqual(g.item_families(["AllGames"], True), every)
        # Halo 2 reads 14 as 13, and Assault as CTF.
        self.assertEqual(g.item_families(["AllGamesExceptCtfAndRace"], True), every - {"ctf"})
        self.assertEqual(g.item_families(["Assault"], True), {"ctf"})
        self.assertEqual(g.item_families(["Ctf", "Slayer", "Oddball", "Juggernaut"], True),
                         {"ctf", "slayer", "oddball", "juggernaut"})
        # An entry that lists no game type is in none; so is Territories'.
        self.assertEqual(g.item_families(["None", "None", "None", "None"], True), set())
        self.assertEqual(g.item_families(["Territories", "Headhunter"], True), set())

    def test_pickups_share_the_spawn_sets_labels(self):
        sets = {}
        start = {"pos": [1.0, 0.0, 0.0], "facing": 0.0, "team": 0,
                 "game_types": ["AllGamesExceptCtfAndRace", "None", "None", "None"]}
        ctf = {"pos": [2.0, 0.0, 0.0], "facing": 0.0, "team": 0, "game_types": ["Ctf", "None", "None", "None"]}
        # Race has starts of its own, or it would spawn at Slayer's.
        race = {"pos": [3.0, 0.0, 0.0], "facing": 0.0, "team": 0, "game_types": ["Race", "None", "None", "None"]}
        g.spawn_plan([start, ctf, race], False, sets)
        mine = dict(sets)
        # A pickup the same game types place takes the spawn set's label, one
        # only CTF places a set of its own.
        self.assertEqual(g.set_label(sets, g.item_families(["AllGamesExceptCtfAndRace"], False)),
                         mine[frozenset({"slayer", "oddball", "king"})])
        self.assertEqual(g.set_label(sets, {"ctf"}), "spawn_set_%d" % len(mine))
        self.assertEqual(len(sets), len(mine) + 1)


class Respawn(unittest.TestCase):
    def test_spawn_time(self):
        self.assertEqual(g.spawn_time({"spawn_time": 45, "collection_spawn_time": 0}, 0), "45")
        self.assertEqual(g.spawn_time({"spawn_time": 0, "collection_spawn_time": 60}, 0), "60")
        self.assertEqual(g.spawn_time({"spawn_time": 0, "collection_spawn_time": 0}, 0), str(g.DEFAULT_RESPAWN))
        self.assertEqual(g.spawn_time({"spawn_time": 30}, 3), str(30 + (3 * 7) % g.RESPAWN_SPREAD))
        # Halo 2: a negative time never comes back, which 0 says here.
        self.assertEqual(g.spawn_time({"spawn_time": -8739, "collection_spawn_time": 60}, 5), "0")


class Kits(unittest.TestCase):
    def test_halo2_one_kit_is_the_profile(self):
        kits = g.starting_kits([entry(["AllGames"], ["w/br", "w/smg"])], True, resolve, WEAPONS)
        self.assertEqual(len(kits), 1)
        self.assertEqual(kits[0]["weapons"], ["battle_rifle", "smg"])
        self.assertEqual((kits[0]["frag_grenades"], kits[0]["plasma_grenades"]), (2, 0))
        self.assertTrue(kits[0]["profile"])
        self.assertEqual(kits[0]["traits"], {"primary_weapon": 254, "secondary_weapon": 254, "grenades": 1})

    def test_flags(self):
        none = g.starting_kits([entry(["AllGames"], ["w/smg"], 1)], True, resolve, WEAPONS)[0]
        self.assertEqual((none["frag_grenades"], none["plasma_grenades"]), (0, 0))
        plasma = g.starting_kits([entry(["AllGames"], ["w/smg"], 2)], True, resolve, WEAPONS)[0]
        self.assertEqual((plasma["frag_grenades"], plasma["plasma_grenades"]), (0, 2))

    def test_second_weapon_is_the_next_different_one(self):
        kit = g.starting_kits([entry(["AllGames"], ["w/smg", "w/smg", "w/pistol", "w/br"])], True, resolve, WEAPONS)[0]
        self.assertEqual(kit["weapons"], ["smg", "magnum"])
        # A weapon the game has nothing for is passed over.
        kit = g.starting_kits([entry(["AllGames"], ["w/c4", "w/pistol"])], True, resolve, WEAPONS)[0]
        self.assertEqual(kit["weapons"], ["magnum"])

    def test_ce_kits_by_game_type(self):
        # Blood Gulch: CTF's kit, and every other game's.
        kits = g.starting_kits([entry(["Ctf"], ["w/ar", "w/pistol"]), entry(["AllGamesExceptCtf"], ["w/pp"], 1)],
                               False, resolve, WEAPONS, (2, 0))
        ctf, rest = kits
        self.assertEqual(ctf["families"], ["ctf"])
        self.assertFalse(ctf["profile"])
        # Named by their place in the game's weapon list; two frags are trait 4.
        self.assertEqual(ctf["traits"], {"primary_weapon": 0, "secondary_weapon": 3, "grenades": 4})
        self.assertEqual(rest["families"], ["king", "oddball", "race", "slayer"])
        self.assertTrue(rest["profile"])
        self.assertEqual((rest["frag_grenades"], rest["plasma_grenades"]), (0, 0))

    def test_the_first_entry_naming_a_game_wins(self):
        kits = g.starting_kits([entry(["Ctf", "Oddball", "King"], ["w/pistol", "w/ar"], 2), entry(["Race"], ["w/pp"], 1),
                                entry(["AllGamesExceptCtfAndRace"], ["w/pistol"], 2)], False, resolve, WEAPONS, (2, 0))
        self.assertEqual([k["families"] for k in kits], [["ctf", "king", "oddball"], ["race"], ["slayer"]])
        self.assertEqual(kits[2]["traits"], {"primary_weapon": 3, "secondary_weapon": 255, "grenades": 8})

    def test_ce_fallback_for_games_no_entry_lists(self):
        fallback = [{"asset": "w/ar", "tag_class": "weap"}, {"asset": "w/pistol", "tag_class": "weap"}]
        kits = g.starting_kits([], False, resolve, WEAPONS, (2, 0), fallback)
        self.assertEqual(len(kits), 1)
        self.assertEqual(kits[0]["weapons"], ["assault_rifle", "magnum"])
        self.assertEqual(kits[0]["families"], ["ctf", "king", "oddball", "race", "slayer"])
        kits = g.starting_kits([entry(["Ctf"], ["w/shotgun"])], False, resolve, WEAPONS, (2, 0), fallback)
        self.assertEqual([k["families"] for k in kits], [["ctf"], ["king", "oddball", "race", "slayer"]])
        # Halo 2 has no such rule.
        self.assertEqual(g.starting_kits([], True, resolve, WEAPONS), [])

    def test_grenade_trait(self):
        self.assertEqual(g.grenade_trait(0, 0), 2)
        self.assertEqual([g.grenade_trait(n, 0) for n in (1, 2, 3, 4)], [3, 4, 5, 6])
        self.assertEqual([g.grenade_trait(0, n) for n in (1, 2, 3, 4)], [7, 8, 9, 10])
        self.assertEqual(g.grenade_trait(2, 2), 12)

    def test_a_kit_weapon_must_be_in_the_weapon_list(self):
        with self.assertRaises(SystemExit):
            g.starting_kits([entry(["Ctf"], ["w/needler"]), entry(["AllGamesExceptCtf"], ["w/pp"])],
                            False, resolve, ["assault_rifle", "plasma_pistol"])


class Generic(unittest.TestCase):
    def test_generic_kit_names_its_weapons_and_grenades(self):
        carried = [{"asset": "w/ar", "tag_class": "weap"}, {"asset": "w/pistol", "tag_class": "weap"}]
        kit = g.generic_kit(carried, resolve, WEAPONS, (2, 0))
        self.assertEqual(kit, {"weapons": ["assault_rifle", "magnum"], "frag_grenades": 2, "plasma_grenades": 0,
                               "traits": {"primary_weapon": 0, "secondary_weapon": 3, "grenades": 4}})

    def test_no_generic_kit_without_weapons(self):
        # Halo 2's staging names none; a weapon the game has nothing for is none either.
        self.assertIsNone(g.generic_kit(None, resolve, WEAPONS, (2, 0)))
        self.assertIsNone(g.generic_kit([{"asset": "w/c4", "tag_class": "weap"}], resolve, WEAPONS, (2, 0)))


class WeaponRespawn(unittest.TestCase):
    AS_WEAPON = {"type": "weapon", "spawn timer type": "starts on disturbance", "default spawn time": "30",
                 "default abandonment time": "60"}
    ORDINARY = {"type": "ordinary", "spawn timer type": "starts on death", "default spawn time": "",
                "default abandonment time": ""}

    def test_a_weapon_not_set_up_as_one_takes_the_reference(self):
        tags = {"t/ar": self.AS_WEAPON, "t/br": self.ORDINARY, "t/smg": self.AS_WEAPON, "t/none": None}
        reference, values, change = build_weapon_respawn.plan(
            {"assault_rifle": "t/ar", "battle_rifle": "t/br", "smg": "t/smg", "beam": "t/none"}, tags.get)
        self.assertEqual(reference, "assault_rifle")
        self.assertEqual(list(change), ["battle_rifle"])
        self.assertEqual(values[reference], self.AS_WEAPON)

    def test_nothing_changes_when_every_weapon_is_one(self):
        _, _, change = build_weapon_respawn.plan({"a": "t/a", "b": "t/b"}, lambda path: self.AS_WEAPON)
        self.assertEqual(change, {})

    def test_enum_text_loses_its_number(self):
        self.assertEqual(build_weapon_respawn.plain("weapon (1)"), "weapon")
        self.assertEqual(build_weapon_respawn.plain("starts on disturbance (1)"), "starts on disturbance")
        self.assertEqual(build_weapon_respawn.plain("30"), "30")


class Splice(unittest.TestCase):
    def level(self, **blam):
        return {"name": "x", "decor": [1], "blam": {"objects": [{"tag": "spawn"}], "weapons": [], "equipment": [],
                                                    "vehicles": [], **blam}}

    def test_only_the_netgame_lanes_move(self):
        shipped = self.level(weapons=[{"type": "assault_rifle", "pos": [1, 2, 3]}],
                             vehicles=[{"type": "ghost", "pos": [0, 0, 0],
                                        "set": {add_netgame.SPAWN: "30", "label": "kept"}}])
        shipped["lifts"] = ["kept"]
        fresh = self.level(weapons=[{"type": "battle_rifle", "pos": [1, 2, 3]}],
                           vehicles=[{"type": "ghost", "pos": [0, 0, 0],
                                      "set": {add_netgame.SPAWN: "50", add_netgame.ABANDON: "90", "label": "fresh"}}])
        fresh["decor"] = ["fresh"]
        fresh["starting_equipment"] = [{"families": ["slayer"], "weapons": ["smg"]}]
        fresh["generic_equipment"] = {"weapons": ["assault_rifle", "magnum"]}
        fresh["spawn_sets"] = [{"label": "spawn_set_0", "families": ["ctf"]}]
        level, why = add_netgame.splice(shipped, fresh)
        self.assertIsNone(why)
        self.assertEqual(level["generic_equipment"], fresh["generic_equipment"])
        self.assertEqual(level["blam"]["weapons"], fresh["blam"]["weapons"])
        self.assertEqual(level["blam"]["vehicles"][0]["set"],
                         {add_netgame.SPAWN: "50", add_netgame.ABANDON: "90", "label": "kept"})
        self.assertEqual((level["decor"], level["lifts"]), ([1], ["kept"]))
        self.assertEqual(level["starting_equipment"], fresh["starting_equipment"])
        self.assertEqual(add_netgame.rest(level), add_netgame.rest(shipped))

    def test_a_moved_vehicle_still_takes_its_times_and_other_vehicles_do_not(self):
        shipped = self.level(vehicles=[{"type": "shade", "pos": [9, 9, 9], "set": {add_netgame.SPAWN: "30"}}])
        fresh = self.level(vehicles=[{"type": "shade", "pos": [0, 0, 0], "set": {add_netgame.SPAWN: "250"}}])
        level, _ = add_netgame.splice(shipped, fresh)
        self.assertEqual(level["blam"]["vehicles"], [{"type": "shade", "pos": [9, 9, 9], "set": {add_netgame.SPAWN: "250"}}])
        fresh = self.level(vehicles=[{"type": "ghost", "pos": [9, 9, 9], "set": {add_netgame.SPAWN: "250"}}])
        level, _ = add_netgame.splice(shipped, fresh)
        self.assertEqual(level["blam"]["vehicles"], shipped["blam"]["vehicles"])

    def test_a_level_from_another_conversion_is_refused(self):
        shipped = self.level(weapons=[{"type": "smg", "pos": [100.0, 200.0, 300.0]}])
        fresh = self.level(weapons=[{"type": "smg", "pos": [150.0, 200.0, 300.0]}])
        level, why = add_netgame.splice(shipped, fresh)
        self.assertIsNone(level)
        self.assertIn("not this pack's conversion", why)

    def test_shipped_spawn_sets_must_lead(self):
        shipped = self.level()
        shipped["spawn_sets"] = [{"label": "spawn_set_0", "families": ["slayer"]}]
        fresh = self.level()
        fresh["spawn_sets"] = [{"label": "spawn_set_0", "families": ["ctf"]}]
        level, why = add_netgame.splice(shipped, fresh)
        self.assertIsNone(level)
        self.assertIn("spawn sets", why)


if __name__ == "__main__":
    unittest.main()
