import copy
import unittest
from pcg_tree_decor import convert
from authored_decor import (expand_background_trees, PINE_OPTIMIZED, PINE_SAPLING,
                           PWR_MATURE_PINE, PWR_MATURE_PINE_RECIPE)


class TreeDecorTest(unittest.TestCase):
    def setUp(self):
        self.source = {"schema": 1, "generator": "UE PCG", "graph": "/Game/PCG/Test", "seed": 4,
                       "source_sha256": "a"*64, "pcg_output_sha256": "b"*64,
                       "input_count": 2, "selected_count": 1, "instances": [
                           {"id": "pcg_tree_1", "kind": "tree", "mesh": None, "recipe": "Lrg_A",
                            "position": [110, -50, 30], "position_cm": [11000, 5000, 3000],
                            "yaw_degrees": -65, "scale": 1.2, "scale_xyz": [1.2]*3}]}
        self.recipes = {"Lrg_A": {"height": 2000}}

    def test_selected_pose_and_scale_reach_recipe_without_resampling(self):
        doc = convert(self.source, self.recipes)
        self.assertEqual(doc["background_trees"], [{"id": "pcg_tree_1", "position_m": [110, -50, 30],
                          "yaw_degrees": -65, "height_m": 24, "variant": "Lrg_A"}])
        self.assertEqual(doc["pcg_provenance"]["selected_count"], 1)
        self.assertEqual(doc["decor"], [])

    def test_coordinate_mismatch_and_nonuniform_scale_are_rejected(self):
        for field, value in (("position_cm", [11000, -5000, 3000]), ("scale_xyz", [1.2, 1.1, 1.2])):
            source = copy.deepcopy(self.source)
            source["instances"][0][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                convert(source, self.recipes)

    def test_complete_pines_keep_selected_transform_and_correct_root_height(self):
        for recipe, mesh, min_z, height in (("Pine_Optimized", PINE_OPTIMIZED, -166.25, 2150.125),
                                           ("Pine_Sapling_A", PINE_SAPLING, -5.3125, 211.3125)):
            with self.subTest(recipe=recipe):
                source = copy.deepcopy(self.source)
                row = source["instances"][0]
                row.update(recipe=recipe, scale=1.123456789, scale_xyz=[1.123456789]*3,
                           yaw_degrees=65.1234567, position=[110.123456, -50.123456, 30.123456],
                           position_cm=[11012.3456, 5012.3456, 3012.3456])
                doc = convert(source, {})
                self.assertAlmostEqual(doc["background_trees"][0]["height_m"], height*row["scale"]/100)
                decor, leaves = expand_background_trees(doc, {}, {})
                self.assertEqual(leaves, [])
                self.assertEqual(decor[0]["mesh"].split(".")[0], mesh)
                self.assertEqual(decor[0]["rot"], [0, -row["yaw_degrees"], 0])
                for value in decor[0]["scale"]:
                    self.assertAlmostEqual(value, row["scale"], places=12)
                for axis in range(2):
                    self.assertAlmostEqual(decor[0]["pos"][axis], row["position_cm"][axis])
                self.assertAlmostEqual(decor[0]["pos"][2] + min_z*decor[0]["scale"][2], row["position_cm"][2])

    def test_integer_source_ids_get_stable_runtime_names(self):
        self.source["instances"][0]["id"] = 42
        self.assertEqual(convert(self.source, self.recipes)["background_trees"][0]["id"], "pcg_tree_42")
        self.assertEqual(self.source["instances"][0]["id"], 42)

    def test_measured_complete_pine_keeps_one_exact_part_and_provenance(self):
        measured={"complete_mesh":PWR_MATURE_PINE,"min_z":-12.5,"height":2800.25,"root_z":0.,
                  "geometry_sha256":"c"*64,"bark_material_slots":["MI_Pine_Tree_Mat"]}
        self.recipes[PWR_MATURE_PINE_RECIPE]=measured
        self.source['instances'][0]['recipe']=PWR_MATURE_PINE_RECIPE
        doc=convert(self.source,self.recipes)
        decor,leaves=expand_background_trees(doc,self.recipes,{})
        self.assertEqual(len(decor),1)
        self.assertEqual(leaves,[])
        self.assertEqual(decor[0]['mesh'].split('.')[0],PWR_MATURE_PINE)
        self.assertEqual(decor[0]['rot'],[0,65,0])
        for value in decor[0]['scale']:
            self.assertAlmostEqual(value,1.2,places=12)
        self.assertAlmostEqual(decor[0]['pos'][2]+measured['root_z']*1.2,3000)
        self.assertEqual(doc['complete_tree_provenance'][PWR_MATURE_PINE_RECIPE],measured)
        self.assertEqual(decor[0]['source_geometry_sha256'],measured['geometry_sha256'])
        changed=copy.deepcopy(self.recipes)
        changed[PWR_MATURE_PINE_RECIPE]['geometry_sha256']='d'*64
        with self.assertRaisesRegex(ValueError,'changed after PCG'):
            expand_background_trees(doc,changed,{})
        for field,bad in [('complete_mesh','/Game/MJOLNIR/Unverified'),('height',0),
                          ('min_z',float('nan')),('geometry_sha256','missing'),
                          ('root_z',-100),('root_z',float('nan')),
                          ('bark_material_slots',['Needles'])]:
            changed=copy.deepcopy(self.recipes)
            changed[PWR_MATURE_PINE_RECIPE][field]=bad
            with self.subTest(field=field),self.assertRaises(ValueError):
                convert(self.source,changed)
        with self.assertRaisesRegex(ValueError,'Missing measured'):
            convert(self.source,{})

    def test_duplicate_geometry_budget_and_missing_provenance_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "budget"):
            convert(self.source, self.recipes, max_trees=0)
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            convert(self.source, self.recipes, {"decor": [{"id": "pcg_tree_1"}]})
        self.source["instances"][0]["mesh"] = "/Game/DuplicateTree"
        with self.assertRaisesRegex(ValueError, "duplicate mesh"):
            convert(self.source, self.recipes)
        self.source["source_sha256"] = ""
        with self.assertRaisesRegex(ValueError, "provenance"):
            convert(self.source, self.recipes)


if __name__ == "__main__":
    unittest.main()
