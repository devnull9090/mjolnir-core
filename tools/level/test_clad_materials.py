import unittest

import clad_materials


def level(cliff, env=None, decor=None, pbr=None):
    return {"landscape": {"cliff": cliff, "pbr": pbr or {"grass_tint": [0.3, 0.6, 0.2, 1]}},
            "environment": env or {}, "decor": decor or [], "canvas": {"origin": [0, 0, 100]}}


GROUPS = [{"name": "grass"},
          {"cliff": True, "base": "/Game/MJOLNIR/Maps/X/Textures/T_wall.T_wall", "light": [1, 0.9, 0.8], "lm": True},
          {"cliff": True, "light": [0.5, 0.5, 0.5]}]


class Entries(unittest.TestCase):
    def test_shipped_cliff_material_bakes_nothing(self):
        # The snow maps' rocks keep their meshes' own materials.
        self.assertEqual(clad_materials.entries(level({"material": "/Game/X.X"}), GROUPS, "LXX"), [])

    def test_a_group_each_with_the_loaders_values(self):
        cliff = {"fill": [1, 0.8, 0.6, 1.0], "drape": [30, 40, 500], "tess": {"cladding": True, "clad_disp": 0.0}}
        env = {"post": {"manual_exposure": True}, "sun": {"lightmap_sun": [0.3, 1.0]}}
        decor = [{"mesh": "/Game/M/SM_X_Water.SM_X_Water", "pos": [0, 0, -50]}]
        out = clad_materials.entries(level(cliff, env, decor), GROUPS, "LXX")
        self.assertEqual([e["group"] for e in out], [2, 3])
        a, b = out
        self.assertTrue(a["parent"].endswith("M_CE_CladTess.M_CE_CladTess"))
        # The fill's alpha exposed by the default light scale, as lightScale().
        self.assertEqual(a["vectors"]["CliffFill"], [1.0, 0.8, 0.6, 256.0])
        self.assertEqual(a["vectors"]["CliffDisp"], [0.0, 400.0, 0.0, 0.0])
        self.assertEqual(a["vectors"]["CliffDrape"], [30.0, 40.0, 500.0, 0.0])
        self.assertEqual(a["vectors"]["LandSea"], [50.0, 0.0, 60.0, 1.0])
        # Lightmapped: its light with alpha 2 and the lightmap's levels.
        self.assertEqual(a["vectors"]["CladLight"], [1.0, 0.9, 0.8, 2.0])
        self.assertEqual(a["vectors"]["LandLMLevels"], [0.3, 1.0, 0.0, 0.0])
        self.assertEqual(a["textures"]["Base"], GROUPS[1]["base"])
        # Not lightmapped: its light as it is, no base of its own.
        self.assertEqual(b["vectors"]["CladLight"], [0.5, 0.5, 0.5, 1.0])
        self.assertNotIn("Base", b["textures"])
        self.assertTrue(a["textures"]["RockAD"].startswith(clad_materials.MEGASCANS))
        self.assertEqual(a["light_scale"], 256.0)
        self.assertEqual(clad_materials.loader_spec(out)["2"]["object"], a["object"])

    def test_name_follows_the_values(self):
        one = clad_materials.entries(level({"fill": [1, 1, 1, 1]}), GROUPS, "LXX")
        two = clad_materials.entries(level({"fill": [1, 1, 1, 0.5]}), GROUPS, "LXX")
        self.assertEqual(one, clad_materials.entries(level({"fill": [1, 1, 1, 1]}), GROUPS, "LXX"))
        self.assertNotEqual(one[0]["package"], two[0]["package"])

    def test_no_sea_for_a_pond(self):
        lv = level({}, decor=[{"mesh": "/Game/M/SM_X_Water.SM_X_Water", "pos": [0, 0, 0]}])
        lv["landscape"]["sea"] = False
        out = clad_materials.entries(lv, GROUPS, "LXX")
        self.assertNotIn("LandSea", out[0]["vectors"])
        self.assertTrue(out[0]["parent"].endswith("M_CE_CliffPBR.M_CE_CliffPBR"))


if __name__ == "__main__":
    unittest.main()
