"""Regression checks for the conversion-to-Warfare map contract."""
import unittest

import prepare_runtime as runtime
layout=runtime.layout


def converted_fixture():
    """CE's real conversion shape: hidden neutral CTF + Slayer duplicates."""
    objects = []
    for side, x in (("red", -76000), ("blue", 76000)):
        for i in range(8):
            for label in ("ctf_spawn_"+side, "spawn_set_0"):
                objects.append({"tag": r"objects\multi\spawning\player_spawn", "group": "scenery",
                                "pos": [x, i*100, 3680], "rot": [0,0,0],
                                "set": {"multiplayer data.owner team": "neutral",
                                        "multiplayer data.megalo label": label,
                                        "multiplayer data.spawn flags": "0x4"}})
    objects.append({"tag": r"objects\multi\spawning\player_spawn", "pos": [0,0,0],
                    "set": {"multiplayer data.megalo label": "ctf_spawn_none"}})
    objects.append({"tag": r"objects\multi\ctf\flag_stand", "pos": [0,0,0],
                    "set": {"multiplayer data.megalo label": "ctf_flag_return"}})
    return {"canvas": {"origin": [0,0,0]}, "blam": {"objects": objects},
            "spawn_sets": [{"label": "spawn_set_0", "families": ["slayer"]}],
            "vehicle_sets": [{"type": kind, "team": side, "default": 3, "allowed": 3,
                              "label": "ce_"+kind+"_1"}
                             for side in ("red", "blue") for kind in ("warthog", "scorpion", "banshee")]}


class RuntimeContract(unittest.TestCase):
    def test_ce_conversion_produces_visible_team_home_spawns_and_king_vehicles(self):
        source = converted_fixture()
        prepared = runtime.apply(source)
        runtime.validate(prepared)
        self.assertEqual(len(source["blam"]["objects"]), 34, "Do not mutate converter output in memory")
        self.assertEqual(len(prepared["blam"]["objects"]), 19, "16 home spawns and 3 capture markers")
        self.assertTrue(all(v["default"] == v["allowed"] == 7 for v in prepared["vehicle_sets"]))

    def test_hud_and_simulation_capture_positions_share_units_and_order(self):
        prepared = runtime.apply(converted_fixture())
        self.assertEqual(prepared["koth_hills"], [layout.ue(p)+[2000] for p in layout.CAPTURES])
        markers = prepared["blam"]["objects"][-3:]
        for hill, marker in zip(prepared["koth_hills"], markers):
            self.assertEqual(hill[:3], marker["pos"])
            self.assertAlmostEqual(float(marker["set"]["multiplayer data.boundary width or radius"])*304.8, hill[3])

    def test_mode_patch_is_idempotent_and_rejects_unknown_origin(self):
        source = converted_fixture()
        prepared = runtime.apply(source)
        self.assertEqual(runtime.apply(prepared), prepared)
        source["canvas"]["origin"] = [100,0,0]
        with self.assertRaises(ValueError):
            runtime.apply(source)

    def test_named_transports_do_not_carry_multiplayer_creation_gates(self):
        prepared = runtime.apply(converted_fixture())
        carriers = [v for v in prepared["blam"]["vehicles"] if v.get("tag")==runtime.PELICAN_TAG]
        self.assertEqual({v["name"] for v in carriers}, {"pwr_pelican_red", "pwr_pelican_blue"})
        for carrier in carriers:
            self.assertFalse(carrier["placed"])
            self.assertFalse(carrier.get("set"), "MP hide flags also prevent named HS creation")
        self.assertEqual(runtime.apply(prepared), prepared)

    def test_ground_vehicle_names_preserve_placement_and_respawn_fields(self):
        source=converted_fixture()
        source["blam"]["vehicles"]=[{"type":"warthog","pos":[-70000,0,3680],"yaw":0,
            "set":{"multiplayer data.owner team":"defender","multiplayer data.spawn flags":"0x4"}}]
        prepared=runtime.apply(source)
        hog=prepared["blam"]["vehicles"][0]
        self.assertEqual(hog["name"],"pwr_hog_red_0")
        self.assertEqual(hog["set"],source["blam"]["vehicles"][0]["set"])
        self.assertNotIn("placed",hog)
        self.assertIn(hog["name"],prepared["blam"]["object_names"])
        self.assertEqual(runtime.apply(prepared),prepared)


if __name__ == "__main__":
    unittest.main()
