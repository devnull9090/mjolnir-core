import ast
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
import numpy as np
from PIL import Image
import alpine_geology
import upgrade_ce_map


class AlpineGeologyTests(unittest.TestCase):
    def test_editor_import_and_shader_keep_mask_values_linear(self):
        # Run the actual production importer without loading the editor.
        # Its UNORM sampler must return 128/255, not the sRGB-decoded .216.
        scripts=Path(__file__).resolve().parents[2]/'unreal/MJOLNIRMaterials/Scripts'
        source=scripts/'build_ce_landscape.py'
        node=next(n for n in ast.parse(source.read_text()).body
                  if isinstance(n,ast.FunctionDef) and n.name=='import_texture')
        unreal=Mock();texture=unreal.load_asset.return_value
        namespace={'unreal':unreal,'tools':Mock(),'eal':Mock(),'TEXTURES':'/Game/Test'}
        exec(compile(ast.Module(body=[node],type_ignores=[]),str(source),'exec'),namespace)
        namespace['import_texture']('base.png','T_LandBase')
        settings=dict(call.args for call in texture.set_editor_property.call_args_list)
        self.assertIs(settings['srgb'],False)
        self.assertEqual(settings['compression_settings'],unreal.TextureCompressionSettings.TC_VECTOR_DISPLACEMENTMAP)
        shader=(scripts/'build_ce_materials.py').read_text()
        self.assertIn('tex("Base", white, linear)',shader)
        self.assertIn('unreal.MaterialSamplerType.SAMPLERTYPE_LINEAR_COLOR)',shader)
        values=np.arange(256,dtype=np.uint8).astype(np.float32)/255
        self.assertAlmostEqual(float(values[128]),128/255,places=7)
        srgb_mid=((128/255+.055)/1.055)**2.4
        self.assertGreater(abs(float(values[128])-srgb_mid),.28)

    def fixture(self,root):
        values=np.array([[[0,0,0],[1,0,0]],[[0,1,0],[1,1,0]]],dtype=np.float32)
        np.save(root/'data.npy',values)
        spec={'schema':'pwr-alpine-geology-v1','coordinates':'authoring_metres_z_up','row_order':'+y',
              'master_sha256':'master','dimensions':[2,2],'data':'data.npy',
              'data_sha256':alpine_geology.digest(root/'data.npy'),'channels':['rock','snow','soil']}
        path=root/'geology.json';path.write_text(json.dumps(spec));return path,values

    def test_authoring_y_and_pixel_centres(self):
        with tempfile.TemporaryDirectory() as folder:
            _,data=self.fixture(Path(folder))
            image=alpine_geology.sample_texture(data,2,2)
            # Top PNG row is high authoring+Y, and sample locations are .25/.75.
            np.testing.assert_array_equal(image[:,:,0],[[64,191],[64,191]])
            np.testing.assert_array_equal(image[:,:,1],[[191,191],[64,64]])

    def test_actual_road_bytes_survive_codec(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);path,_=self.fixture(root)
            base=np.arange(7*9*4,dtype=np.uint8).reshape(7,9,4)
            Image.fromarray(base,'RGBA').save(root/'base.png')
            document={'textures':{'Base':'base.png'},'pbr':{'alpine':[19000,27000,1800,1]}}
            result=alpine_geology.apply_to_bake(root,document,path,'master')
            actual=np.asarray(Image.open(root/'base.png'))
            np.testing.assert_array_equal(actual[:,:,3],base[:,:,3])
            self.assertEqual(result['road_alpha_sha256'],hashlib.sha256(base[:,:,3].tobytes()).hexdigest())
            self.assertEqual(document['pbr']['alpine'][3],2)
            self.assertEqual(result['texture_encoding']['rgb'],'linear_unorm8')
            self.assertIs(result['texture_encoding']['srgb'],False)
            self.assertFalse(np.array_equal(actual[:,:,:3],base[:,:,:3]))

    def test_stale_master_and_modified_data_fail_before_write(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);path,_=self.fixture(root)
            with self.assertRaisesRegex(ValueError,'another runtime'):alpine_geology.load(path,'other')
            with (root/'data.npy').open('ab') as stream:stream.write(b'changed')
            with self.assertRaisesRegex(ValueError,'hash mismatch'):alpine_geology.load(path,'master')

    def test_upgrade_forwards_opt_in_manifest(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);path,_=self.fixture(root);(root/'master.json').write_text('{}')
            config={'shaders':['ground'],'landscape':'LPW','heightfield':'master.json','geology':path.name}
            with patch.object(upgrade_ce_map,'REPO',str(root)),patch.object(upgrade_ce_map,'run',return_value='') as run:
                upgrade_ce_map.stage_land('PWR',config,{'scene':'scene','land':'land'})
            argv=run.call_args.args[0];self.assertEqual(Path(argv[argv.index('--geology')+1]),path)
            config['landscape']='LBG'
            with patch.object(upgrade_ce_map,'REPO',str(root)),patch.object(upgrade_ce_map,'run') as run:
                with self.assertRaisesRegex(ValueError,'LPW'):upgrade_ce_map.stage_land('PWR',config,{'scene':'scene','land':'land'})
                run.assert_not_called()


if __name__=='__main__':unittest.main()
