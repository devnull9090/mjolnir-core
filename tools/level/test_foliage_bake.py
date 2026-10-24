"""Offline checks for cooked rock overrides and their runtime exclusion."""
import copy
import math
import unittest

import foliage_bake as bake


class RockMaterialTest(unittest.TestCase):
    def setUp(self):
        self.rocks = [{"id": f"swap_{i}", "mesh": mesh, "pos": [10, 20, 30],
                       "rot": [0, 45, 0], "scale": [1, 2, 3]}
                      for i, mesh in enumerate(bake.ROCK_MATERIALS)]
        self.tree = {"id": "swap_tree", "mesh": "/Game/Env/Tree.Trunk", "pos": [0, 0, 0],
                     "scalars": {"Wind Sway Max Angle": 0}}

    def test_default_keeps_the_existing_bake_and_runtime_records(self):
        source = self.rocks + [self.tree]
        before = copy.deepcopy(source)
        self.assertEqual(bake.runtime_decor(source), source)
        for d in self.rocks:
            self.assertEqual(bake.decor_spec(d, [100, 200, 300]),
                             {"id": d["id"], "mesh": d["mesh"], "loc": [110, 220, 330],
                              "rot": [0, 45, 0], "scale": [1, 2, 3], "flags": 0})
        self.assertEqual(source, before)

    def test_only_supported_baked_rocks_get_mics_and_leave_runtime_decor(self):
        explicit = dict(self.rocks[0], id="explicit", materials=["/Game/Other.Material"])
        source = self.rocks + [self.tree, explicit]
        before = copy.deepcopy(source)
        self.assertEqual(bake.runtime_decor(source, 0.65), [self.tree, explicit])
        for d in self.rocks:
            self.assertTrue(bake.bakeable(d))
            original = bake.decor_spec(d, [0, 0, 0])
            cooked = bake.decor_spec(d, [0, 0, 0], 0.65)
            material = cooked.pop("material")
            self.assertEqual(cooked, original)
            self.assertEqual(material["parent"], bake.ROCK_MATERIALS[d["mesh"]])
            self.assertEqual(material["scalars"], {"Roughness Remap Low#0": 0.65,
                    "Roughness Remap High#0": 1.0, "Roughness Remap Low#1": 0.65,
                    "Roughness Remap High#1": 1.0})
        self.assertNotIn("material", bake.decor_spec(self.tree, [0, 0, 0], 0.65))
        self.assertEqual(source, before)

    def test_coastal_palette_is_cooked_and_never_overwritten_at_runtime(self):
        desert = [{"id": f"cliff_{v}", "mesh": f"/Game/Env/Bio/Rock/Desert/Rock_Desert_Cliff_{v}/SM_Rock_Desert_Cliff_{v}.SM_Rock_Desert_Cliff_{v}", "pos": [0, 0, 0]}
                  for v in ("A", "C")]
        source = self.rocks + desert + [self.tree]
        self.assertEqual(bake.runtime_decor(source, .65, "coastal"), [self.tree])
        self.assertEqual(bake.runtime_decor(desert, .65), desert)
        for item in source[:-1]:
            spec = bake.decor_spec(item, [0, 0, 0], .65, "coastal")
            if item in desert:
                self.assertIn("vectors", spec["material"])
                self.assertNotIn("Color Tint#0", spec["material"]["vectors"])
            else:
                self.assertNotIn("vectors", spec["material"])
            self.assertTrue(spec["material"]["parent"].startswith("/Game/Env/Bio/Rock/"))

    def test_zero_is_valid_and_invalid_values_fail(self):
        material = bake.rock_material(self.rocks[0]["mesh"], 0)
        self.assertEqual(material["scalars"]["Roughness Remap Low#0"], 0)
        for bad in (-0.1, 1.1, math.nan, math.inf, "0.65", True):
            with self.subTest(bad=bad), self.assertRaisesRegex(SystemExit, "between 0 and 1"):
                bake.rock_material(None, bad)


if __name__ == "__main__":
    unittest.main()
