import json
import os
import tempfile
import unittest

import machine_containers


def touch(path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    for ext in ("utoc", "ucas"):
        open(f"{path}.{ext}", "wb").close()


class MapTagContainers(unittest.TestCase):
    def test_fresh_conversion_door_actors_are_listed(self):
        # A freshly converted map's doors: tags and actors in the
        # conversion's machines folder, no upgrade `doors` file.
        with tempfile.TemporaryDirectory() as conv:
            machines = os.path.join(conv, "machines")
            touch(os.path.join(machines, "pakchunk986-MJOLNIRMACH-CNT-G0C_P"))
            touch(os.path.join(machines, "pakchunk987-MJOLNIRACT-CNT_P"))
            touch(os.path.join(machines, "pakchunk987-MJOLNIRGEAR-CNT_P"))
            names = [n for _, n in machine_containers.map_tag_containers("CNT", {}, conv)]
            self.assertEqual(sorted(names), ["MJOLNIRACT-CNT", "MJOLNIRGEAR-CNT", "MJOLNIRMACH-CNT-G0C"])

    def test_upgrade_doors_win_over_the_conversions(self):
        # An upgrade's own doors (Zanzibar's) and the conversion's actors
        # share a build name: one entry, the upgrade's.
        with tempfile.TemporaryDirectory() as conv, tempfile.TemporaryDirectory() as scene:
            touch(os.path.join(conv, "machines", "pakchunk987-MJOLNIRACT-ZAN_P"))
            doors = os.path.join(scene, "doors.json")
            json.dump([{"machines": [{"containers": ["pakchunk987-MJOLNIRACT-ZAN"]}]}], open(doors, "w"))
            out = machine_containers.map_tag_containers("ZAN", {"doors": doors}, conv)
            self.assertEqual(out, [(os.path.join(scene, "pakchunk987-MJOLNIRACT-ZAN_P"), "MJOLNIRACT-ZAN")])


class ExtraContainers(unittest.TestCase):
    """What neither the conversion nor the bake makes: a CE map's scripted
    devices and a custom vehicle, listed in the map's config."""

    def test_a_pattern_lists_every_container_it_matches(self):
        with tempfile.TemporaryDirectory() as folder:
            for leaf in ("machines/pakchunk986-MJOLNIRMACH-YOY-0C_P", "machines/pakchunk986-MJOLNIRMACH-YOY-0H_P",
                         "pakchunk985-MJOLNIRVCOOK-YOY_P", "pakchunk996-MJOLNIRVVEHI-YOY_P",
                         "pakchunk986-MJOLNIRMESH-YOY_P"):
                touch(os.path.join(folder, leaf))
            m = {"extra_containers": [os.path.join(folder, "machines", "pakchunk986-MJOLNIRMACH-YOY-*_P"),
                                      os.path.join(folder, "pakchunk*-MJOLNIRV*-YOY_P")]}
            out = machine_containers.extra_containers(m, "YOY", folder)
            self.assertEqual([n for _, n in out], ["MJOLNIRMACH-YOY-0C", "MJOLNIRMACH-YOY-0H",
                                                   "MJOLNIRVCOOK-YOY", "MJOLNIRVVEHI-YOY"])
            self.assertTrue(all(os.path.isfile(stem + ".utoc") for stem, _ in out))

    def test_a_stem_under_the_repository_is_taken_as_it_is(self):
        with tempfile.TemporaryDirectory() as repo:
            out = machine_containers.extra_containers(
                {"extra_containers": ["art/pakchunk963-MJOLNIRAPRON-TST_P"]}, "TST", repo)
            self.assertEqual(out, [(os.path.abspath(os.path.join(repo, "art", "pakchunk963-MJOLNIRAPRON-TST_P")),
                                    "MJOLNIRAPRON-TST")])

    def test_a_pattern_that_matches_nothing_stops_the_build(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaisesRegex(ValueError, "matches nothing"):
                machine_containers.extra_containers(
                    {"extra_containers": [os.path.join(folder, "pakchunk*-MJOLNIRV*-YOY_P")]}, "YOY", folder)

    def test_a_name_must_be_the_maps_own_and_the_only_one(self):
        with tempfile.TemporaryDirectory() as repo:
            for entries, used in (([5], ()), (["pakchunk985-MJOLNIRVCOOK-BGL_P"], ()),
                                  (["pakchunk985-MJOLNIRCOOK-YOY_P"], {"MJOLNIRCOOK-YOY"}),
                                  (["a/pakchunk985-MJOLNIRVCOOK-YOY_P", "b/pakchunk986-MJOLNIRVCOOK-YOY_P"], ())):
                with self.assertRaises(ValueError):
                    machine_containers.extra_containers({"extra_containers": entries}, "YOY", repo, used)
            with self.assertRaises(ValueError):
                machine_containers.extra_containers({"extra_containers": "pakchunk985-MJOLNIRVCOOK-YOY_P"}, "YOY", repo)
            self.assertEqual(machine_containers.extra_containers({}, "YOY", repo), [])

    def test_a_pack_keeps_each_name_and_number_with_tags_in_machines(self):
        path = machine_containers.extra_pack_path
        self.assertEqual(path("x/pakchunk986-MJOLNIRMACH-YOY-0C_P", "YOY"),
                         os.path.join("machines", "pakchunk986-MJOLNIRMACH-YOY-0C_P"))
        self.assertEqual(path("x/pakchunk985-MJOLNIRVCOOK-YOY_P", "YOY"), "pakchunk985-MJOLNIRVCOOK-YOY_P")
        # `map pack` takes a map's containers by their -<CODE>_P.
        self.assertEqual(path("x/pakchunk987-MJOLNIRYOY-actor_P", "YOY"), "pakchunk987-MJOLNIRYOY-actor-YOY_P")


if __name__ == "__main__":
    unittest.main()
