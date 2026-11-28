"""A rebuilt pack is refused when it has none of something its last release has."""
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

import pack_remastered
import release_loss

LABEL = "multiplayer data.megalo label"
TEAM = "multiplayer data.owner team"


def placed(group, label=None, team=None):
    made = {"group": group, "tag": "t", "set": {}}
    if label:
        made["set"][LABEL] = label
    if team:
        made["set"][TEAM] = team
    return made


def full():
    """A release with objectives, devices, a script and a custom vehicle."""
    names = ["mjolnir.json", "map/level.json", "map/bots.json", "map/vehicle_sounds.json",
             "map/decals/a.png", "map/decals/b.png",
             "content/pakchunk997-MJOLNIRMAP-AAA_P.utoc", "content/pakchunk997-MJOLNIRMAP-AAA_P.ucas",
             "content/pakchunk986-MJOLNIRMACH-AAA-0C_P.utoc", "content/pakchunk986-MJOLNIRMACH-AAA-1C_P.utoc",
             "content/pakchunk996-MJOLNIRVVEHI-AAA_P.utoc"]
    level = {"modes": ["slayer", "ctf", "koth"], "koth_hills": [[0, 0, 0, 1]], "devices": [{"name": "gate"}],
             "blam": {"script": "aaa.hsc", "trigger_volumes": [{}], "bots": {"count": 15},
                      "objects": [placed("scenery", "koth_hill", "eighth party"),
                                  placed("scenery", "ce_health_pack", "eighth party"),
                                  placed("scenery", "ce_health_pack", "eighth party"),
                                  placed("machines"), placed("machines"), placed("controls")],
                      "vehicles": [{"type": "warthog"}, {"type": "warthog", "tag": "objects\\mjolnir\\aaa\\mongoose"}]}}
    return names, level


class KindsTest(unittest.TestCase):
    def test_a_container_is_its_family(self):
        self.assertEqual(release_loss.family("content/pakchunk986-MJOLNIRMACH-YOY-0C_P.utoc"), "MJOLNIRMACH")
        self.assertEqual(release_loss.family("pakchunk978-MJOLNIRLAND-BGL_P.ucas"), "MJOLNIRLAND")
        self.assertEqual(release_loss.family("content/pakchunk981-MJOLNIRH2-Windows.utoc"), "MJOLNIRH2")
        self.assertIsNone(release_loss.family("map/level.json"))

    def test_a_map_file_is_itself_and_a_folder_is_one_thing(self):
        self.assertEqual(release_loss.map_entry("map/vehicle_sounds.json"), "map/vehicle_sounds.json")
        self.assertEqual(release_loss.map_entry("map/decals/a.png"), "map/decals/")
        self.assertIsNone(release_loss.map_entry("content/pakchunk997-MJOLNIRMAP-AAA_P.utoc"))


class LostTest(unittest.TestCase):
    def test_the_same_release_loses_nothing(self):
        self.assertEqual(release_loss.lost(*full(), *full()), [])

    def test_fewer_of_a_kind_is_no_loss(self):
        names, level = full()
        names.remove("content/pakchunk986-MJOLNIRMACH-AAA-1C_P.utoc")
        names.remove("map/decals/b.png")
        del level["blam"]["objects"][3]   # one of two machines
        del level["blam"]["objects"][2]   # one of two health spots
        self.assertEqual(release_loss.lost(*full(), names, level), [])

    def test_more_is_no_loss(self):
        names, level = full()
        names.append("content/pakchunk970-MJOLNIRROCK-AAA_P.utoc")
        level["modes"].append("race")
        level["blam"]["objects"].append(placed("crates"))
        self.assertEqual(release_loss.lost(*full(), names, level), [])

    def test_a_rebuild_from_an_old_conversion_names_each_thing_it_dropped(self):
        # What the 2026-11-18 rebuild did to Yoyorast, in small.
        names = ["mjolnir.json", "map/level.json", "map/bots.json", "map/decals/a.png",
                 "content/pakchunk997-MJOLNIRMAP-AAA_P.utoc", "content/pakchunk997-MJOLNIRMAP-AAA_P.ucas"]
        level = {"modes": ["slayer", "ctf"],
                 "blam": {"objects": [placed("scenery", "ce_health_pack", "neutral")],
                          "vehicles": [{"type": "warthog"}, {"type": "warthog"}]}}
        self.assertEqual(release_loss.lost(*full(), names, level), sorted([
            "MJOLNIRMACH containers", "MJOLNIRVVEHI containers", "`blam.script`", "`blam.trigger_volumes`",
            "`devices` in the level file", "`koth_hills` in the level file",
            "ce_health_pack objects on the team `eighth party`", "controls in `blam.objects`",
            "machines in `blam.objects`", "map/vehicle_sounds.json", "objects labelled koth_hill",
            "the game type koth", "the vehicle objects\\mjolnir\\aaa\\mongoose"]))

    def test_a_weapon_type_and_game_type_pickups_are_kinds(self):
        old = {"blam": {"weapons": [{"type": "battle_rifle"}, {"type": "smg", "set": {release_loss.LABEL: "spawn_set_0"}}],
                        "equipment": [{"type": "ammo_box"}]},
               "starting_equipment": [{"families": ["slayer"]}]}
        new = {"blam": {"weapons": [{"type": "assault_rifle"}, {"type": "smg"}], "equipment": [{"type": "ammo_box"}]}}
        self.assertEqual(release_loss.lost([], old, [], new),
                         sorted(["`starting_equipment` in the level file", "the weapon battle_rifle",
                                 "weapons placed in some game types only"]))
        self.assertEqual(release_loss.lost([], old, [], old), [])

    def test_a_shipped_level_need_not_name_its_bots(self):
        names, level = full()
        del level["blam"]["bots"]
        self.assertEqual(release_loss.lost(*full(), names, level), [])

    def test_a_label_gone_is_one_loss_not_one_a_team(self):
        names, level = full()
        level["blam"]["objects"] = [o for o in level["blam"]["objects"] if o["set"].get(LABEL) != "ce_health_pack"]
        self.assertEqual(release_loss.lost(*full(), names, level), ["objects labelled ce_health_pack"])


class RefusalTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def archive(self, name, names, level):
        path = self.root / name
        with zipfile.ZipFile(path, "w") as z:
            for n in names:
                z.writestr(n, json.dumps(level) if n == "map/level.json" else "x")
        return str(path)

    def test_a_pack_that_lost_something_is_removed(self):
        names, level = full()
        level["modes"].remove("koth")
        new = self.archive("new.mjolnir", names, level)
        with self.assertRaises(SystemExit) as stop:
            pack_remastered.refuse_losses("AAA", new, full(), [])
        self.assertIn("the game type koth", str(stop.exception))
        self.assertFalse(Path(new).exists())

    def test_a_loss_that_is_meant_goes_through(self):
        names, level = full()
        level["modes"].remove("koth")
        new = self.archive("new.mjolnir", names, level)
        pack_remastered.refuse_losses("AAA", new, full(), ["game type koth"])
        self.assertTrue(Path(new).exists())

    def test_the_release_replaced_is_the_installed_one_or_the_pack_named(self):
        names, level = full()
        cache = self.root / "cache"
        for n in names:
            # The launcher's cache holds containers beside `map/`, not under `content/`.
            at = cache / (n[len("content/"):] if n.startswith("content/") else n)
            at.parent.mkdir(parents=True, exist_ok=True)
            at.write_text(json.dumps(level) if n == "map/level.json" else "x")
        installed = pack_remastered.replaced(str(cache), None)
        self.assertEqual(installed[1], level)
        self.assertEqual(release_loss.lost(*installed, *full()), [])
        self.assertEqual(release_loss.lost(*full(), *installed), [])
        named = pack_remastered.replaced(str(cache), self.archive("old.mjolnir", names, level))
        self.assertEqual(sorted(named[0]), sorted(names))


if __name__ == "__main__":
    unittest.main()
