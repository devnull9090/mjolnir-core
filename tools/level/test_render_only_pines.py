import copy
import json
from pathlib import Path
import tempfile
import unittest
import render_only_pines as p
from foliage_bake import write_exact

class ExteriorPines(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        self.source=self.root/'source';self.source.write_text('frozen')
        self.doc={'schema':p.SCHEMA,'coordinates':'unreal_centimetres','no_native_collision':True,'no_navigation':True,
            'wpo':False,'cast_shadow':True,'preserve_native_material_slots':True,'exclusion_square_half_extent_m':1050,'grouping_cell_cm':50000,
            'cull_cm':[250000,350000],'sources':[{'path':'source','sha256':p.digest(self.source)}],
            'instances':[{'id':'pwr_exterior_pine_test','mesh':p.MATURE,'position_cm':[150000,50000,20000],
                          'ground_z_cm':20000,'rotation_xyzw':[0,0,0,1],'scale':[.8]*3}]}
        self.path=self.root/'input.json';self.save()
    def save(self):self.path.write_text(json.dumps(self.doc))
    def fake_editor(self):
        groups,receipt=p.groups(self.path);folder=self.root/'foliage_bake';folder.mkdir(exist_ok=True)
        binary=folder/'foliage_bake.bin';spec={'bin':str(binary),'groups':[],'decor':[],'render_only_pines':receipt};rows=[]
        for i,(records,group,ids) in enumerate(groups,1):
            receipt['groups'].append({'group':i,'count':len(records),'ids':ids})
            spec['groups'].append({'mesh':group['mesh'],'bands':1,'cull':self.doc['cull_cm'],'flags':35});write_exact(str(binary)+'.xf'+str(i),records)
            rows.append({'component':f'MJFol_{i}_1_0','mesh':group['mesh'],'instances':len(records),'native_slot_names':p.ASSETS[group['mesh']]['slot_names'],
                         'material_overrides':0,'collision':'NoCollision','navigation':False,'wpo':False,'cast_shadow':True,'cull_cm':self.doc['cull_cm']})
        (folder/'spec.json').write_text(json.dumps(spec))
        rb={'schema':'pwr-render-only-pines-editor-v1','source_sha256':receipt['sha256'],'no_native_collision_input':True,
            'maximum_position_error_cm':0,'maximum_quaternion_dot_error':0,'maximum_scale_error':0,'groups':rows}
        rp=folder/'render-only-pines.verification.json';rp.write_text(json.dumps(rb));return rp,rb
    def test_native_slots_and_exact_root(self):
        before=copy.deepcopy(self.doc);groups,receipt=p.groups(self.path)
        self.assertEqual(self.doc,before);self.assertEqual(receipt['instances'],1);self.assertNotIn('material',groups[0][1])
        self.fake_editor();self.assertIn('render_only_pines_transform_0',p.cook_inputs(self.path,self.root))
    def test_full_bounds_and_root_rejected(self):
        self.doc['instances'][0]['position_cm'][0]=105100;self.save()
        with self.assertRaisesRegex(ValueError,'Full exterior'):p.load(self.path)
        self.doc['instances'][0]['position_cm'][0]=150000;self.doc['instances'][0]['position_cm'][2]+=1;self.save()
        with self.assertRaisesRegex(ValueError,'root contact'):p.load(self.path)
    def test_material_and_collision_changes_rejected(self):
        self.doc['materials']=[];self.save()
        with self.assertRaisesRegex(ValueError,'overrides'):p.load(self.path)
        self.doc.pop('materials');self.doc['no_native_collision']=False;self.save()
        with self.assertRaisesRegex(ValueError,'policy'):p.load(self.path)
    def test_cook_rejects_changed_slots_sidecar_and_source(self):
        rp,rb=self.fake_editor();rb['groups'][0]['native_slot_names']=['Default'];rp.write_text(json.dumps(rb))
        with self.assertRaisesRegex(ValueError,'slots/settings'):p.cook_inputs(self.path,self.root)
        self.fake_editor();sidecar=self.root/'foliage_bake/foliage_bake.bin.xf1';sidecar.write_bytes(sidecar.read_bytes()[:-1]+b'\0')
        with self.assertRaisesRegex(ValueError,'transforms'):p.cook_inputs(self.path,self.root)
        self.fake_editor();self.source.write_text('changed')
        with self.assertRaisesRegex(ValueError,'source'):p.cook_inputs(self.path,self.root)

if __name__=='__main__':unittest.main()
