import copy
import json
import math
from pathlib import Path
import struct
import tempfile
import unittest
import render_only_hism as h
import foliage_bake


class ExteriorHISMTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        self.source=self.root/'proof';self.source.write_text('frozen source')
        self.doc={'schema':h.SCHEMA,'coordinates':'unreal_centimetres','no_native_collision':True,'no_navigation':True,
            'exclusion_square_half_extent_m':1050,'sources':[{'path':'proof','sha256':h.digest(self.source)}],
            'material':{'parent':h.PARENT,'textures':h.TEXTURES,'vectors':{'RockTint':[.8,.83,.84,1],'RockParams':[650,.85,.75,0]}},
            'cull_cm':[600000,1000000],'instances':[{'id':'pwr_apron_cliff_test','mesh':next(iter(h.ASSETS)),
            'position_cm':[150000,40000,30000],'rotation_xyzw':[0,0,math.sin(.3),math.cos(.3)],'scale':[1.3,.8,1.1]}]}
        self.path=self.root/'input.json'

    def save(self):self.path.write_text(json.dumps(self.doc))

    def test_exact_transform_and_no_source_mutation(self):
        before=copy.deepcopy(self.doc);self.save();groups,receipt=h.groups(self.path)
        self.assertEqual(self.doc,before);self.assertEqual(receipt['instances'],1)
        records,group,ids=groups[0];self.assertTrue(group['static'] and group['exact']);self.assertNotIn('cliff',group)
        target=self.root/'xf';foliage_bake.write_exact(target,records);row=struct.unpack('<10f',target.read_bytes())
        self.assertEqual(list(row[:3]),before['instances'][0]['position_cm'])
        self.assertAlmostEqual(abs(sum(a*b for a,b in zip(row[3:7],before['instances'][0]['rotation_xyzw']))),1,places=6)
        for a,b in zip(row[7:],before['instances'][0]['scale']):self.assertAlmostEqual(a,b,places=6)

    def test_full_mesh_exclusion_not_only_origin(self):
        self.doc['instances'][0]['position_cm'][0]=106000;self.save()
        with self.assertRaisesRegex(ValueError,'Full exterior'):h.groups(self.path)

    def test_v8_grouping_explicit_and_legacy_unchanged(self):
        self.save();_,legacy=h.groups(self.path);self.assertNotIn('grouping_cell_cm',legacy)
        self.doc['grouping_cell_cm']=125000;self.save();_,current=h.groups(self.path)
        self.assertEqual(current['grouping_cell_cm'],125000)
        self.doc['grouping_cell_cm']=100000;self.save()
        with self.assertRaisesRegex(ValueError,'grouping'):h.groups(self.path)

    def test_changed_source_collision_and_unreviewed_mesh_rejected(self):
        self.save();self.source.write_text('changed')
        with self.assertRaisesRegex(ValueError,'Changed exterior'):h.groups(self.path)
        self.source.write_text('frozen source');self.doc['no_native_collision']=False;self.save()
        with self.assertRaisesRegex(ValueError,'disable collision'):h.groups(self.path)
        self.doc['no_native_collision']=True;self.doc['instances'][0]['mesh']='/Game/Other.Other';self.save()
        with self.assertRaisesRegex(ValueError,'Unreviewed'):h.groups(self.path)

    def test_unsafe_rotation_and_duplicate_ids_rejected(self):
        self.doc['instances'][0]['rotation_xyzw']=[0,0,0,2];self.save()
        with self.assertRaisesRegex(ValueError,'rotation'):h.groups(self.path)
        self.doc['instances'][0]['rotation_xyzw']=[0,0,0,1];self.doc['instances']*=2;self.save()
        with self.assertRaisesRegex(ValueError,'duplicate'):h.groups(self.path)


if __name__=='__main__':unittest.main()
