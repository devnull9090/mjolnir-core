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


if __name__ == "__main__":
    unittest.main()
