import unittest
from temperate_riparian import apply,signature


class TemperateRiparianTests(unittest.TestCase):
    def test_only_materials_change_and_actual_native_recipe_is_preserved(self):
        rows=[{'id':'baseline','mesh':'old','pos':[1,2,3],'materials':[{'parent':'old'}]}]
        for i,letter in enumerate('ABC'):
            rows.append({'id':f'pwr_v6_riparian_{i}','mesh':f'/Game/SM_Rock_Glacial_Med_{letter}.SM_Rock_Glacial_Med_{letter}',
                         'pos':[1,2,3],'rot':[0,20,0],'scale':[.3]*3,'static':True})
        out,changes=apply({'decor':rows},expected=3)
        self.assertEqual(out['decor'][0],rows[0]);self.assertEqual(signature(rows),signature(out['decor']))
        self.assertNotIn('materials',rows[1])
        for row,variant in zip(out['decor'][1:],('Lrg_C','Med_B','Lrg_C')):
            self.assertIn(f'MI_Rock_Glacial_{variant}_NoSnow',row['materials'][0]['parent'])
        self.assertEqual(len(changes),3)

    def test_existing_material_or_unknown_mesh_cannot_be_silently_replaced(self):
        for row in ({'id':'pwr_v6_riparian_1','mesh':'unknown'},
                    {'id':'pwr_v6_riparian_1','mesh':'SM_Rock_Glacial_Med_A','materials':[]}):
            with self.assertRaises(ValueError):apply({'decor':[row]},expected=1)
        with self.assertRaises(ValueError):apply({'decor':[]},expected=1)


if __name__=='__main__':unittest.main()
