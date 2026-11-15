"""A stale exterior transform or editor binding must invalidate the cook."""
import json
from pathlib import Path
import tempfile
import unittest

import foliage_bake
import render_only_hism as h
from owned_map_cook import render_only_hism_cook_inputs, render_only_hism_path


class ExteriorCookBindingTest(unittest.TestCase):
    def fixture(self, root):
        source = root/'pcg.json'
        source.write_text('actual PCG output fixture')
        manifest = root/'exterior.json'
        doc = {'schema':h.SCHEMA,'coordinates':'unreal_centimetres','no_native_collision':True,
               'no_navigation':True,'exclusion_square_half_extent_m':1050,
               'sources':[{'path':'pcg.json','sha256':h.digest(source)}],
               'material':{'parent':h.PARENT,'textures':h.TEXTURES,
                           'vectors':{'RockTint':[.8,.83,.84,1],'RockParams':[650,.85,.75,0]}},
               'cull_cm':[600000,1000000], 'instances':[{'id':'pwr_apron_cliff_test',
               'mesh':next(iter(h.ASSETS)),'position_cm':[150000,40000,30000],
               'rotation_xyzw':[0,0,0,1],'scale':[1,1,1]}]}
        manifest.write_text(json.dumps(doc))
        groups, proof = h.groups(manifest)
        records, group, ids = groups[0]
        proof['groups'] = [{'group':1,'count':1,'ids':ids}]
        folder = root/'foliage_bake'
        folder.mkdir()
        binary = folder/'foliage_bake.bin'
        xf = Path(str(binary)+'.xf1')
        foliage_bake.write_exact(xf,records)
        spec = folder/'spec.json'
        spec.write_text(json.dumps({'bin':str(binary),'groups':[{'mesh':group['mesh'],'flags':35}],
                                    'render_only_hism':proof}))
        material = 'MI_PWR_ExteriorCliffs_'+proof['sha256'][:12]
        readback = folder/'render-only-hism.verification.json'
        readback.write_text(json.dumps({'schema':'pwr-render-only-hism-editor-v1',
            'source_sha256':proof['sha256'],'no_native_collision_input':True,
            'maximum_position_error_cm':0,'maximum_quaternion_dot_error':0,'maximum_scale_error':0,
            'groups':[{'component':'MJFol_1_1_0','mesh':group['mesh'],'instances':1,
                       'material':'/Game/Test/'+material+'.'+material,'collision':'NoCollision',
                       'navigation':False,'wpo':False,'cull_cm':doc['cull_cm']}]}))
        return {'render_only_hism':str(manifest),'bake_foliage':True},source,spec,xf,readback

    def test_unset_is_unchanged(self):
        self.assertEqual(render_only_hism_cook_inputs({},'unused'),{})

    def test_all_sources_transforms_and_editor_proof_bound(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cfg,source,spec,xf,readback = self.fixture(root)
            inputs = render_only_hism_cook_inputs(cfg,root)
            self.assertEqual(set(inputs.values()),{Path(cfg['render_only_hism']),source,spec,xf,readback})
            cfg['bake_foliage'] = False
            with self.assertRaisesRegex(ValueError,'bake_foliage'):
                render_only_hism_path(cfg)

    def test_changed_transform_or_pcg_source_rejected(self):
        for target in ('source','transform'):
            with self.subTest(target=target),tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                cfg,source,_,xf,_ = self.fixture(root)
                path = source if target=='source' else xf
                data = bytearray(path.read_bytes()); data[0] ^= 1; path.write_bytes(data)
                with self.assertRaises(ValueError):render_only_hism_cook_inputs(cfg,root)

    def test_editor_setting_mutations_and_missing_component_rejected(self):
        for key,value in [('collision','QueryAndPhysics'),('navigation',True),('wpo',True),
                          ('instances',2),('material','/Game/Wrong'),('component','MJFol_2_1_0')]:
            with self.subTest(key=key),tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                cfg,_,_,_,readback = self.fixture(root)
                doc = json.loads(readback.read_text());doc['groups'][0][key]=value
                readback.write_text(json.dumps(doc))
                with self.assertRaises(ValueError):render_only_hism_cook_inputs(cfg,root)


if __name__=='__main__':unittest.main()
