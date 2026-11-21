import copy
import json
import math
from pathlib import Path
import struct
import tempfile
import unittest

import pcg_foliage as pcg


class PCGFoliageTests(unittest.TestCase):
    def fixture(self):
        source = {"points":[{"id":7,"position":[12,-4,3],"normal":[0,0,1],
                             "density":1,"biome_mask":1,"kind":"tree","biome":"forest"}]}
        q = [0,0,-math.sin(math.pi/8),math.cos(math.pi/8)]
        generated = {"schema":1,"generator":"UE5.5 UPCGGraph / test fixture","graph":"/Graph", "seed":42,
                     "input_count":1,"points":[{"id":7,"position_cm":[1200,400,300],
                       "rotation_xyzw":q,"scale_xyz":[1.123]*3,"asset_draw":.8}]}
        return source, generated

    def test_exclusion_cannot_be_reintroduced_by_output(self):
        source, output = self.fixture()
        for field, value in (("biome_mask",0),("density",0),("allowed",False)):
            changed = copy.deepcopy(source); changed["points"][0][field] = value
            with self.assertRaisesRegex(ValueError,"exclusion"): pcg.validate_output(changed, output)

    def test_moved_or_duplicate_collision_positions_rejected(self):
        source, output = self.fixture()
        moved = copy.deepcopy(output); moved["points"][0]["position_cm"][1] *= -1
        with self.assertRaisesRegex(ValueError,"moved"): pcg.validate_output(source,moved)
        duplicate = copy.deepcopy(output); duplicate["points"] *= 2
        with self.assertRaisesRegex(ValueError,"duplicate"): pcg.validate_output(source,duplicate)

    def test_exact_sidecar_and_collision_share_transform(self):
        source, generated = self.fixture()
        with tempfile.TemporaryDirectory() as folder:
            d = Path(folder)
            for name, obj in (("source",source),("generated",generated),
                              ("palette",{"kinds":{"tree":{"meshes":["/TreeA","/TreeB"]}}})):
                (d/f"{name}.json").write_text(json.dumps(obj))
            result = pcg.adapt(d/"source.json",d/"generated.json",d/"palette.json",d/"out")
            placement = result["instances"][0]
            self.assertEqual(placement["mesh"],"/TreeB")
            self.assertAlmostEqual(placement["yaw_degrees"],45)
            self.assertEqual(placement["position"],[12,-4,3])
            exact = struct.unpack("<10f",(d/"out/foliage.bin.xf1").read_bytes())
            expected = placement["position_cm"]+placement["rotation_xyzw"]+placement["scale_xyz"]
            for actual, wanted in zip(exact,expected): self.assertAlmostEqual(actual,wanted,places=5)
            raw = (d/"out/foliage.bin").read_bytes()
            self.assertEqual(struct.unpack("<4sIII",raw[:16]),(b"MJF3",3,1,1))
            self.assertEqual(len(raw),35)

    def test_tree_recipe_does_not_duplicate_render_instances(self):
        source, generated = self.fixture()
        with tempfile.TemporaryDirectory() as folder:
            d = Path(folder)
            for name,obj in (("source",source),("generated",generated),("palette",{"kinds":{"tree":{"recipe":"Lrg_A"}}})):
                (d/f"{name}.json").write_text(json.dumps(obj))
            result = pcg.adapt(d/"source.json",d/"generated.json",d/"palette.json",d/"out","trees")
            self.assertIsNone(result["instances"][0]["mesh"])
            self.assertEqual(result["instances"][0]["recipe"],"Lrg_A")
            self.assertEqual(len((d/"out/trees.bin").read_bytes()),12)

    def test_invalid_rotation_and_scale_are_rejected(self):
        source, generated = self.fixture()
        for field,value in (("rotation_xyzw",[0,0,0,0]),("scale_xyz",[1,2,1]),("asset_draw",float("nan"))):
            bad=copy.deepcopy(generated); bad["points"][0][field]=value
            with self.assertRaises(ValueError): pcg.validate_output(source,bad)

    def test_weighted_pines_use_existing_draw_without_changing_pose(self):
        source, generated = self.fixture()
        rule = {"recipes": [{"recipe": "Pine_Optimized", "weight": .88},
                            {"recipe": "Pine_Sapling_A", "weight": .12}]}
        for draw, expected in ((0, "Pine_Optimized"), (.879, "Pine_Optimized"),
                               (.88, "Pine_Sapling_A"), (1, "Pine_Sapling_A")):
            with self.subTest(draw=draw), tempfile.TemporaryDirectory() as folder:
                generated["points"][0]["asset_draw"] = draw
                d = Path(folder)
                for name, obj in (("source", source), ("generated", generated), ("palette", {"kinds": {"tree": rule}})):
                    (d/f"{name}.json").write_text(json.dumps(obj))
                result = pcg.adapt(d/"source.json", d/"generated.json", d/"palette.json", d/"out", "trees")
                actual = result["instances"][0]
                self.assertEqual(actual["recipe"], expected)
                self.assertIsNone(actual["mesh"])
                self.assertEqual(actual["position"], source["points"][0]["position"])
                for key in ("position_cm", "rotation_xyzw", "scale_xyz"):
                    self.assertEqual(actual[key], generated["points"][0][key])
                self.assertEqual(len((d/"out/trees.bin").read_bytes()), 12)

    def test_invalid_weighted_recipe_palette_fails_closed(self):
        for entries in ([], [{"recipe": "Pine_Optimized", "weight": 0}],
                        [{"recipe": "Pine_Optimized", "weight": float("nan")}],
                        [{"recipe": "Pine_Optimized", "weight": True}]):
            with self.subTest(entries=entries), self.assertRaises(ValueError):
                pcg.choose_recipe({"recipes": entries}, .5)
        with self.assertRaises(ValueError):
            pcg.choose_recipe({"recipes": [{"recipe": "Pine_Optimized", "weight": 1}], "meshes": ["/Tree"]}, .5)

    def test_merge_keeps_rocks_replaces_grass_and_renumbers_exact(self):
        source, generated = self.fixture()
        with tempfile.TemporaryDirectory() as folder:
            d=Path(folder)
            for name,obj in (("source",source),("generated",generated),("palette",{"kinds":{"tree":{"meshes":["/Grass"],"rule":"short grass"}}})):
                (d/f"{name}.json").write_text(json.dumps(obj))
            pcg.adapt(d/"source.json",d/"generated.json",d/"palette.json",d/"extra")
            base=d/"base"; base.mkdir()
            record=struct.pack("<fffBBbbBBB",10,20,30,0,100,0,0,255,255,255)
            (base/"foliage.bin").write_bytes(b"MJF3"+struct.pack("<II",3,2)+struct.pack("<I",1)+record+struct.pack("<I",1)+record)
            (base/"foliage.json").write_text(json.dumps({"file":"foliage.bin","groups":[{"mesh":"/Rock","rule":"cladding"},{"mesh":"/OldGrass","rule":"grass"}]}))
            result=pcg.merge_foliage(base/"foliage.json",d/"extra/foliage.json")
            self.assertEqual(result,{"kept_groups":1,"pcg_groups":1,"pcg_instances":1})
            self.assertEqual((base/"foliage.bin.xf2").read_bytes(),(d/"extra/foliage.bin.xf1").read_bytes())
            self.assertEqual(pcg.read_mjf_groups(base/"foliage.json")[1][0][1],struct.pack("<I",1)+record)
            before=(base/"foliage.bin").read_bytes()
            pcg.merge_foliage(base/"foliage.json",d/"extra/foliage.json")
            self.assertEqual((base/"foliage.bin").read_bytes(),before)

    def test_invalid_sidecar_merge_does_not_modify_existing_foliage(self):
        source, generated = self.fixture()
        with tempfile.TemporaryDirectory() as folder:
            d=Path(folder)
            for name,obj in (("source",source),("generated",generated),("palette",{"kinds":{"tree":{"meshes":["/Tree"]}}})):
                (d/f"{name}.json").write_text(json.dumps(obj))
            for name in ("base","extra"):
                pcg.adapt(d/"source.json",d/"generated.json",d/"palette.json",d/name)
            before=(d/"base/foliage.bin").read_bytes()
            (d/"extra/foliage.bin.xf1").write_bytes(b"broken")
            with self.assertRaisesRegex(ValueError,"sidecar"):
                pcg.merge_foliage(d/"base/foliage.json",d/"extra/foliage.json")
            self.assertEqual((d/"base/foliage.bin").read_bytes(),before)


if __name__ == "__main__": unittest.main()
