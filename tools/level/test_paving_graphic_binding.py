import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from owned_map_cook import digest, paving_graphic_cook_inputs
from upgrade_ce_map import master_material_env


class PavingGraphicBindingTests(unittest.TestCase):
    def test_unset_clears_inherited_editor_environment(self):
        self.assertEqual(paving_graphic_cook_inputs({}),{})
        env=master_material_env({'PWR':{}})
        self.assertEqual(env['MJ_PWR_PAVING_GRAPHIC'],'')
        self.assertEqual(env['MJ_PWR_PAVING_GRAPHIC_READBACK'],'')

    def test_editor_readback_rejects_stale_source_or_build(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); manifest=root/'graphic.json';image=root/'source.png';prompt=root/'prompt.txt'
            for p in (manifest,image,prompt):p.write_text('fixture')
            spec={'source':{'dimensions':[1254,1254]},'build':{'dimensions':[1024,1024]},
                  'package':'/Game/MJOLNIR/CETrial/T_PWR_PavingGraphic'}
            readback=root/'graphic.editor.json'
            proof={'schema':'pwr-paving-graphic-editor-v1','manifest_sha256':digest(manifest),
                   'source_sha256':digest(image),'source_dimensions':[1254,1254],
                   'build':spec['build'],'package':spec['package']+'.T_PWR_PavingGraphic'}
            cfg={'paving_graphic':str(manifest)}
            with patch('pwr_paving_graphic.load_graphic_manifest',return_value=(image,spec)), \
                 patch('pwr_paving_graphic.graphic_cook_inputs',return_value=[manifest,image,prompt]):
                readback.write_text(json.dumps(proof))
                self.assertEqual(set(paving_graphic_cook_inputs(cfg).values()),{manifest,image,prompt,readback})
                env=master_material_env({'PWR':cfg})
                self.assertEqual(Path(env['MJ_PWR_PAVING_GRAPHIC_READBACK']),readback)
                for key,value in [('manifest_sha256','changed'),('source_sha256','changed'),
                                  ('build',{'dimensions':[2048,2048]}),('package','/Game/Wrong')]:
                    with self.subTest(key=key):
                        readback.write_text(json.dumps({**proof,key:value}))
                        with self.assertRaisesRegex(ValueError,'stale'):paving_graphic_cook_inputs(cfg)


if __name__=='__main__':unittest.main()
