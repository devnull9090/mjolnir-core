import hashlib
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import numpy as np
from PIL import Image
import alpine_ecology as ecology
import upgrade_ce_map


class EcologyTests(unittest.TestCase):
    def field(self):
        y,x=np.mgrid[-32:33,-32:33]*2.
        z=30+.002*x*x+.08*y
        road=np.zeros_like(z);road[30:35,:]=1
        return SimpleNamespace(heights_m=z,spacing_m=(2.,2.),origin_m=(-64.,-64.),masks={'road':road})

    def test_exact_tree_roots_create_litter_but_protected_roads_stay_clear(self):
        field=self.field();before=field.heights_m.copy()
        roots=[{'position':[x,y,0],'recipe':'Pine_Optimized'} for x in (-12,0,12) for y in (18,30,42)]
        empty=ecology.derive(field,[]);planted=ecology.derive(field,roots)
        self.assertGreater(planted[...,1].max(),.5)
        np.testing.assert_array_equal(empty[...,1],0)
        np.testing.assert_array_equal(planted[30:35,:,1:3],0)
        np.testing.assert_array_equal(field.heights_m,before)
        np.testing.assert_array_equal(planted,ecology.derive(field,roots))
        self.assertTrue(np.isfinite(planted).all())

    def test_drainage_flows_downhill_without_cycles(self):
        z=np.tile(np.arange(8,0,-1),(8,1)).astype(float)
        area=ecology.drainage(z,2)
        self.assertEqual(area[3,-1],32)
        self.assertEqual(area[3,0],4)

    def test_bake_preserves_base_and_y_axis_and_rejects_wrong_master(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);data=np.zeros((4,4,4),np.float32);data[:,:,0]=np.arange(4)[:,None]/3
            np.save(root/'field.npy',data)
            spec={'schema':'pwr-alpine-ecology-v1','coordinates':'authoring_metres_z_up','row_order':'+y',
                  'master_sha256':'a'*64,'dimensions':[4,4],'data':'field.npy','data_sha256':ecology.digest(root/'field.npy'),
                  'channels':['moisture','canopy_litter','colluvium','road_weathering']}
            (root/'field.json').write_text(json.dumps(spec))
            base=np.arange(64,dtype=np.uint8).reshape(4,4,4);Image.fromarray(base).save(root/'base.png')
            before=(root/'base.png').read_bytes()
            document={'textures':{'Base':'base.png'},'pbr':{'base':'/Game/Test/T_LandBase.T_LandBase'}}
            result=ecology.apply_to_bake(root,document,root/'field.json','a'*64)
            self.assertEqual(before,(root/'base.png').read_bytes())
            self.assertEqual(result['road_alpha_sha256'],hashlib.sha256(base[...,3].tobytes()).hexdigest())
            image=np.asarray(Image.open(root/'ecology.png'))
            self.assertGreater(image[0,0,0],image[-1,0,0])
            self.assertFalse(result['texture_encoding']['srgb'])
            with self.assertRaisesRegex(ValueError,'provenance'):ecology.load(root/'field.json','b'*64)
            (root/'field.npy').write_bytes(b'bad')
            with self.assertRaisesRegex(ValueError,'hash'):ecology.load(root/'field.json','a'*64)

    def test_pipeline_requires_exact_alpine_inputs_and_forwards_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            for name in ('master.json','geology.json','ecology.json'):(root/name).write_text('{}')
            config={'shaders':['ground'],'landscape':'LPW','heightfield':'master.json',
                    'geology':'geology.json','ecology':'ecology.json'}
            with patch.object(upgrade_ce_map,'REPO',str(root)),patch.object(upgrade_ce_map,'run',return_value='') as run:
                upgrade_ce_map.stage_land('PWR',config,{'scene':'scene','land':'land'})
            argv=run.call_args.args[0]
            self.assertEqual(Path(argv[argv.index('--ecology')+1]),root/'ecology.json')
            config.pop('geology')
            with patch.object(upgrade_ce_map,'REPO',str(root)),patch.object(upgrade_ce_map,'run') as run:
                with self.assertRaisesRegex(ValueError,'Alpine2'):upgrade_ce_map.stage_land('PWR',config,{'scene':'scene','land':'land'})
                run.assert_not_called()


if __name__=='__main__':unittest.main()
