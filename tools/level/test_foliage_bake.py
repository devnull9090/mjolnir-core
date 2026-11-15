"""Offline checks for cooked rock overrides and their runtime exclusion."""
import copy
import argparse
import math
from pathlib import Path
import struct
import tempfile
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


class PineHISMTest(unittest.TestCase):
    def pine(self, ident, x, yaw=37, scale=.83):
        from authored_decor import PINE_OPTIMIZED
        return {"id": ident, "mesh": PINE_OPTIMIZED + "." + PINE_OPTIMIZED.rsplit("/", 1)[-1],
                "pos": [x, -8000, 1800 + 166.25 * scale], "rot": [0, yaw, 0],
                "scale": [scale] * 3, "static": True}

    def test_spatial_groups_keep_exact_root_transform_and_native_collision_source(self):
        source = [self.pine("a", -30000), self.pine("b", -29000), self.pine("c", 30000)]
        before = copy.deepcopy(source)
        groups = bake.pine_groups(source, [100, 200, 300])
        self.assertEqual(len(groups), 2)
        self.assertEqual(sum(len(records) for records, _, _ in groups), 3)
        by_id = {d["id"]: d for d in source}
        with tempfile.TemporaryDirectory() as folder:
            for index, (records, group, ids) in enumerate(groups):
                self.assertEqual(group["cull"], [90000, 180000])
                self.assertTrue(group["shadow"] and group["static"] and group["exact"])
                self.assertEqual(group["bands"], 1)
                path = Path(folder) / str(index)
                bake.write_exact(path, records)
                for ident, transform in zip(ids, struct.iter_unpack("<10f", path.read_bytes())):
                    original = by_id[ident]
                    for got, want, offset in zip(transform[:3], original["pos"], [100, 200, 300]):
                        self.assertAlmostEqual(got, want + offset, delta=.005)
                    q = [0, 0, math.sin(math.radians(37) / 2), math.cos(math.radians(37) / 2)]
                    self.assertAlmostEqual(abs(sum(a * b for a, b in zip(transform[3:7], q))), 1, places=6)
                    for scale in transform[7:]:
                        self.assertAlmostEqual(scale, .83, places=6)
        self.assertEqual(bake.runtime_decor(source), [])
        self.assertEqual(source, before, "Native trunk collision must retain the original swap records")

    def test_custom_material_or_nonstatic_pine_keeps_actor_path(self):
        source = [dict(self.pine("a", 0), scalars={"Tint": .5}),
                  dict(self.pine("b", 0), static=False),
                  dict(self.pine("c", 0), rot=[10, 20, 0])]
        self.assertEqual(bake.pine_groups(source), [])
        self.assertEqual(bake.runtime_decor(source), source)

    def test_only_exact_authored_mature_pine_uses_hism(self):
        from authored_decor import PWR_MATURE_PINE
        accepted=dict(self.pine('mature',0),mesh=PWR_MATURE_PINE+'.'+PWR_MATURE_PINE.rsplit('/',1)[-1])
        other=dict(accepted,id='other',mesh='/Game/MJOLNIR/Scenery/PWR/Unverified.Unverified')
        customized=dict(accepted,id='custom',materials=['/Game/Unverified'])
        self.assertTrue(bake.pine_hism(accepted))
        self.assertFalse(bake.bakeable(other))
        self.assertFalse(bake.pine_hism(customized))
        self.assertEqual(bake.runtime_decor([accepted,other,customized]),[other,customized])
        groups=bake.pine_groups([accepted,other,customized])
        self.assertEqual(len(groups),1)
        self.assertEqual(groups[0][2],['mature'])
        self.assertTrue(groups[0][1]['static'])
        self.assertFalse(bake.needs_standin(accepted['mesh']))
        self.assertTrue(bake.needs_standin(self.pine('stock',0)['mesh']))
        with self.assertRaisesRegex(ValueError,'stand-in folder'):
            bake.needs_standin(other['mesh'])

    def test_map_specific_cull_preserves_transforms_and_other_map_defaults(self):
        source = [self.pine("a", 0), self.pine("b", 40000)]
        default = bake.pine_groups(source)
        aerial = bake.pine_groups(source, cull_cm=bake.pine_cull_range("160000,300000"))
        for (records, group, ids), (old_records, old_group, old_ids) in zip(aerial, default):
            self.assertEqual(group["cull"], [160000, 300000])
            self.assertEqual(old_group["cull"], [90000, 180000])
            self.assertEqual((records, ids), (old_records, old_ids))
        for bad in ("nan,300000", "100,100", "-1,300000", "300000,100", [True, 20], [10]):
            with self.subTest(bad=bad), self.assertRaises(argparse.ArgumentTypeError):
                bake.pine_cull_range(bad)


if __name__ == "__main__":
    unittest.main()
