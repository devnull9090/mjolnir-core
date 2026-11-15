import unittest
from verify_landscape_lod_cook import parse_dump, verify_rows, runtime_script


class CookedLodChecks(unittest.TestCase):
    def policy(self):
        return {'grid':{'components':2,'sections':1,'quads':63},'forced_section_bases':[[0,0]]}

    def rows(self):
        text='''export 1 LandscapeComponent (native tail 12 bytes)
  ForcedLOD = 0
export 2 LandscapeComponent (native tail 12 bytes)
  SectionBaseX = 63
export 3 LandscapeComponent (native tail 12 bytes)
  SectionBaseY = 63
export 4 LandscapeComponent (native tail 12 bytes)
  SectionBaseX = 63
  SectionBaseY = 63
export 5 OtherComponent (native tail 12 bytes)
  ForcedLOD = 7
'''
        return parse_dump(text)

    def test_zero_values_and_default_automatic_inventory(self):
        self.assertEqual(verify_rows(self.rows(),self.policy()),{'components':4,'forced_lod0':1,'automatic':3})

    def test_missing_forced_value_duplicate_and_incomplete_are_rejected(self):
        rows=self.rows();rows[0]['ForcedLOD']=-1
        with self.assertRaisesRegex(ValueError,'ForcedLOD'):verify_rows(rows,self.policy())
        with self.assertRaisesRegex(ValueError,'duplicate'):verify_rows(self.rows()+self.rows()[:1],self.policy())
        with self.assertRaisesRegex(ValueError,'Incomplete'):verify_rows(self.rows()[:-1],self.policy())

    def test_runtime_helper_contains_no_setter_and_requires_correct_map_inventory(self):
        source=runtime_script(self.policy())
        self.assertNotIn('SetForcedLOD',source)
        self.assertIn('total==4 and pinned==1',source)
        self.assertIn('/Game/Levels/Halo1/Solo/PWR/PWR',source)


if __name__=='__main__':unittest.main()
