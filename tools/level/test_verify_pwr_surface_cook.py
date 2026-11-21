import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch
import numpy as np
from PIL import Image
import verify_pwr_surface_cook as verify


class CookVerifierTests(unittest.TestCase):
    def test_graphic_cook_rejects_stripped_mips_wrong_gamma_and_wrapped_edges(self):
        info='  size      1024x1024\n  mips      11\n  format    PF_BC7\n  payload   classic mip chain\n'
        props='export 0 Texture2D (native tail 100 bytes)\n  CompressionSettings = 11\n  AddressX = 2\n  AddressY = 2\n'
        self.assertEqual(verify.verify_graphic_properties(info,props),'omitted_UE5.5_UTexture2D_default_true')
        self.assertEqual(verify.verify_graphic_properties(info,props+'  SRGB = true\n'),'explicit_true')
        for changed in (info.replace('1024x1024','128x128'),info.replace('mips      11','mips      8'),
                        info.replace('PF_BC7','PF_DXT1'),info.replace('classic mip chain','virtual')):
            with self.assertRaises(ValueError):verify.verify_graphic_properties(changed,props)
        for changed in (props+'  SRGB = false\n',props.replace('AddressX = 2','AddressX = 0'),
                        props.replace('AddressY = 2','AddressY = 1'),props.replace('Texture2D','Material')):
            with self.assertRaises(ValueError):verify.verify_graphic_properties(info,changed)

    def test_graphic_colour_grid_detects_changed_design_without_pixel_resampling(self):
        source=np.full((1254,1254,4),128,dtype=np.uint8)
        cooked=np.full((1024,1024,4),128,dtype=np.uint8)
        with patch.object(verify,'pixels',side_effect=[source,cooked]),patch.object(verify,'digest',return_value='test'):
            self.assertEqual(verify.compare_graphic_build('source','cooked')['max_block_mean_rgb_error'],0)
        cooked[:128,:128,:3]=20
        with patch.object(verify,'pixels',side_effect=[source,cooked]),patch.object(verify,'digest',return_value='test'):
            with self.assertRaisesRegex(ValueError,'spatial colour'):verify.compare_graphic_build('source','cooked')

    def test_omitted_material_normal_uses_verified_true_class_default_only(self):
        header='  export 0: M_CE_AlpineApron : Material, 9523 bytes  <- shown\n'
        self.assertEqual(verify.require_tangent_normal_default(header),'omitted_UE5.5_UMaterial_default_true')
        self.assertEqual(verify.require_tangent_normal_default(header+'  bTangentSpaceNormal = true   (Bool)\n'),'explicit_true')
        for value in ('false','0 (zeroed)','nottrue','trueish'):
            with self.assertRaises(ValueError):
                verify.require_tangent_normal_default(header+'  bTangentSpaceNormal = '+value+'\n')
        for text in ('','export 0: T_Texture : Texture2D, 100 bytes',header+'bTangentSpaceNormal : true\n'):
            with self.assertRaises(ValueError):verify.require_tangent_normal_default(text)

    def test_apron_readback_requires_actual_runtime_provenance(self):
        self.assertIsNone(verify.apron_texture_input(None,{}))
        with self.assertRaisesRegex(ValueError,'runtime manifest'):
            verify.apron_texture_input(Path('geology.json'),{})
        with patch('alpine_surface_v6.load_apron_texture',return_value=('texture.png',{})) as load:
            verify.apron_texture_input(Path('geology.json'),{'heightfield':{'manifest_sha256':'actual'}})
            load.assert_called_once_with(Path('geology.json'),'actual')

    def test_final_ecology_cannot_be_silently_omitted_or_misbound(self):
        with self.assertRaisesRegex(ValueError,'requires'):verify.data_texture_inputs({},True)
        document={'pbr':{'ecology':{'texture':'/Game/MJOLNIR/Landscape/LPW/T_LandEcology.T_LandEcology'}},
                  'textures':{'Ecology':'ecology.png'}}
        self.assertIn(('T_LandEcology','ecology.png'),verify.data_texture_inputs(document,True))
        document['pbr']['ecology']['texture']='/Game/Old/T_LandEcology'
        with self.assertRaisesRegex(ValueError,'owned LPW'):verify.data_texture_inputs(document,True)
        self.assertEqual(len(verify.data_texture_inputs({})),2)

    def test_exact_pixels_accept_reencoding_and_reject_alpha_mutation(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);source=root/'source.png';cooked=root/'cooked.png'
            data=np.random.default_rng(1).integers(0,256,(8,8,4),dtype=np.uint8)
            Image.fromarray(data).save(source,compress_level=0)
            Image.fromarray(data).save(cooked,compress_level=9)
            result=verify.compare_pixels(source,cooked)
            self.assertEqual(result['max_rgba_byte_error'],[0,0,0,0])
            self.assertNotEqual(result['source_sha256'],result['export_sha256'])
            data[3,4,3]^=1;Image.fromarray(data).save(cooked)
            with self.assertRaisesRegex(ValueError,'bytes differ'):verify.compare_pixels(source,cooked)

    def test_colour_space_and_compression_fail_closed(self):
        verify.require_false('  SRGB = false\n','SRGB')
        verify.require_false('  bTangentSpaceNormal = 0 (zeroed)   (Bool)\n','bTangentSpaceNormal')
        verify.require_compression('  CompressionSettings = 5\n',5)
        for text in ('  SRGB = true\n',''):
            with self.assertRaises(ValueError):verify.require_false(text,'SRGB')
        with self.assertRaises(ValueError):verify.require_compression('CompressionSettings = 1\n',5)

    def test_source_seal_detects_postcopy_change(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'pakchunk983-Windows.ucas';path.write_bytes(b'original')
            seal={str(path.resolve()):verify.digest(path)}
            verify.verify_seals([path],seal)
            path.write_bytes(b'other')
            with self.assertRaisesRegex(ValueError,'changed during audit'):verify.verify_seals([path],seal)

    def test_import_table_uses_zen_header_not_byte_substring(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'material.uasset';name='/Game/MJOLNIR/CETrial/T_PWR_PavingNormal'
            encoded=name.encode();header=struct.pack('<IIIIIIiiiiiii',*[0]*12,52)
            batch=struct.pack('<iiQ',1,len(encoded),0)+bytes(8)+bytes([len(encoded)>>8,len(encoded)&255])+encoded
            path.write_bytes(header+batch)
            self.assertEqual(verify.imported_packages(path),[name])
            path.write_bytes(b'T_PWR_PavingNormal')
            with self.assertRaisesRegex(ValueError,'Truncated'):verify.imported_packages(path)

    def test_landscape_must_match_requested_owned_snapshot(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);cook=root/'owned-cook-test';cook.mkdir()
            land=root/'pakchunk965-Windows';owned=cook/'pakchunk985-PWR'
            for file in verify.container_files(land)+verify.container_files(owned):file.write_bytes(file.name.encode())
            receipt={'dir':cook.name,'code':'PWR',
                     'landscape':{x.suffix[1:]:verify.digest(x) for x in verify.container_files(land)},
                     'containers':{x.suffix[1:]:verify.digest(x) for x in verify.container_files(owned)}}
            (root/'owned-cook.json').write_text(json.dumps(receipt))
            verify.verify_owned_snapshot(cook,land)
            Path(str(land)+'.ucas').write_bytes(b'stale')
            with self.assertRaisesRegex(ValueError,'owned-cook seal'):verify.verify_owned_snapshot(cook,land)


if __name__=='__main__':unittest.main()
