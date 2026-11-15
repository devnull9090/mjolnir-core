import unittest
import json
import tempfile
from unittest.mock import patch
from types import SimpleNamespace
from pathlib import Path
import numpy as np
from alpine_surface_v6 import (compose_apron_height,derive_apron,derive_meadow,
                               invert_smooth,smooth,RECIPES,load_apron_texture,digest,verify_tree_binding)
from alpine_geology import sample_texture
from PIL import Image


class Visual6Tests(unittest.TestCase):
    def test_final_ecology_cannot_reuse_old_selection(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'trees.json'
            path.write_text(json.dumps({'schema':1,'selected_count':1,'instances':[{'id':'original'}]}))
            ecology={'tree_count':1,'trees_sha256':digest(path)}
            self.assertEqual(verify_tree_binding(path,ecology)['count'],1)
            path.write_text(json.dumps({'schema':1,'selected_count':1,'instances':[{'id':'different'}]}))
            with self.assertRaisesRegex(ValueError,'exact final tree'):verify_tree_binding(path,ecology)

    def test_master_texture_environment_is_explicitly_map_scoped(self):
        import upgrade_ce_map
        self.assertEqual(upgrade_ce_map.master_material_env({'OTHER':{}}),
                         {'MJ_PWR_APRON_FIELD':'', 'MJ_PWR_PAVING_GRAPHIC':'', 'MJ_PWR_PAVING_GRAPHIC_READBACK':''})
        with self.assertRaisesRegex(ValueError,'requires PWR'):
            upgrade_ce_map.master_material_env({'OTHER':{'apron_geology':'mask.json','heightfield':'master.json'}})
        with (patch('heightfield.load_heightfield',return_value=SimpleNamespace(manifest_sha256='actual')),
              patch('alpine_surface_v6.load_apron_texture',return_value=(Path('checked.png'),{}))):
            env=upgrade_ce_map.master_material_env({'PWR':{'apron_geology':'mask.json','heightfield':'master.json'}})
            self.assertEqual(env['MJ_PWR_APRON_FIELD'],'checked.png')

    def test_apron_manifest_rejects_projection_gamma_and_changed_source(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);source=root/'source.json';collar=root/'collar.npz'
            source.write_text('{}');collar.write_bytes(b'geometry source')
            rgba=np.full((3,3,4),.5,np.float32);np.save(root/'data.npy',rgba)
            Image.fromarray(sample_texture(rgba,1024,1024)).save(root/'data.png')
            spec={'schema':'pwr-apron-geology-v1','coordinates':'authoring_metres_z_up','row_order':'+y',
                  'runtime_master_sha256':'runtime','source_master':str(source),'source_master_sha256':digest(source),
                  'collar':str(collar),'collar_sha256':digest(collar),'dimensions':[3,3],
                  'origin_m':[-4000.,-4000.],'spacing_m':[4000.,4000.],
                  'world_rect_cm':[-400000.,-400000.,800000.,800000.],
                  'exact_edge_blend_m':[0,150],'channels':['rock','snow','colluvium','moisture'],
                  'encoding':{'srgb':False,'compression':'vector_displacement'},
                  'data':'data.npy','data_sha256':digest(root/'data.npy'),
                  'texture':'data.png','texture_sha256':digest(root/'data.png')}
            manifest=root/'geology.json'
            field=SimpleNamespace(dimensions=(3,3),origin_m=(-4000.,-4000.),spacing_m=(4000.,4000.),
                                  bounds_m=((-4000.,-4000.),(4000.,4000.)))
            with patch('alpine_surface_v6.load_heightfield',return_value=field):
                manifest.write_text(json.dumps(spec));load_apron_texture(manifest,'runtime')
                for key,value,message in [('world_rect_cm',[-400000,400000,800000,800000],'projection'),
                                          ('encoding',{'srgb':True,'compression':'vector_displacement'},'linear'),
                                          ('dimensions',[4,4],'grid')]:
                    changed=dict(spec);changed[key]=value;manifest.write_text(json.dumps(changed))
                    with self.assertRaisesRegex(ValueError,message):load_apron_texture(manifest,'runtime')
                manifest.write_text(json.dumps(spec));source.write_text('{"changed":true}')
                with self.assertRaisesRegex(ValueError,'source changed'):load_apron_texture(manifest,'runtime')

    def test_inverse_soil_codec_is_precise_and_bounded(self):
        target=np.linspace(0,.85,1001)
        encoded=.13+.30*invert_smooth(target/.85)
        np.testing.assert_allclose(smooth(.13,.43,encoded)*.85,target,atol=2e-8)

    def test_world_projection_preserves_authoring_y_and_linear_bytes(self):
        y,x=np.mgrid[0:9,0:9];field=np.stack([x/8,y/8,np.full_like(x,.5,dtype=float),np.ones_like(x)],-1)
        image=sample_texture(field,8,8)
        # W=(x,-y,z), rect[-400000,-400000,800000,800000]. Positive
        # authored Y maps to small texture V, without a second shader flip.
        self.assertGreater(image[0,3,1],image[-1,3,1])
        self.assertGreater(image[3,-1,0],image[3,0,0])
        np.testing.assert_array_equal(image[...,2],128)

    def test_join_sampling_changes_only_join_coverage_and_never_source(self):
        z=np.ones((9,9))*100
        f=SimpleNamespace(heights_m=z,origin_m=(-4.,-4.),spacing_m=(1.,1.))
        join={'heights_m':np.full((3,3),60.),'origin_m':np.array([-1.,-1.]),'spacing_m':np.array(1.)}
        composed,_,_=compose_apron_height(f,join)
        np.testing.assert_array_equal(composed[3:6,3:6],60)
        self.assertEqual(composed[0,0],100)
        np.testing.assert_array_equal(z,100)

    def test_meadow_fit_reaches_target_protects_routes_and_keeps_height(self):
        y,x=np.mgrid[-64:65,-64:65]*2.;z=70+.0005*x*x+.0003*y*y
        protected=np.zeros_like(z);protected[62:67]=1
        f=SimpleNamespace(heights_m=z,spacing_m=(2.,2.),masks={'road':protected})
        previous=np.zeros((*z.shape,4),np.float32)
        previous[...,0]=.16+smooth(-100,100,x)*.25
        previous[...,2]=.02+smooth(-100,100,y)*.04
        before=z.copy();result,report=derive_meadow(f,previous)
        self.assertAlmostEqual(report['soil_mix_after'],.08,places=7)
        self.assertEqual(report['protected_soil_max'],0)
        np.testing.assert_array_equal(z,before)
        self.assertTrue(np.isfinite(result).all())
        self.assertGreaterEqual(result.min(),0);self.assertLessEqual(result.max(),1)

    def test_panel_scale_and_joint_slot_cannot_restore_patio_pattern(self):
        for recipe in RECIPES.values():
            self.assertGreaterEqual(min(recipe['PavingLayout'][:2]),2000)
            self.assertLessEqual(recipe['PavingLayout'][2],4)
            self.assertLessEqual(recipe['PavingPattern'][0],35)
            self.assertLessEqual(recipe['PavingPattern'][1],.03)
        self.assertEqual(RECIPES['joint']['PavingLayout'][3],0)

    def test_real_drainage_retains_more_snow_than_identical_dry_height(self):
        z=np.full((9,9),430.);flow=np.zeros_like(z);flow[:,:4]=.10
        f=SimpleNamespace(heights_m=z,origin_m=(-4000.,-4000.),spacing_m=(1000.,1000.),
                          masks={'flow':flow,'wear':np.zeros_like(z),'deposits':np.zeros_like(z)})
        join={'heights_m':np.full((3,3),430.),'origin_m':np.array([-1.,-1.]),'spacing_m':np.array(1.)}
        result,_=derive_apron(f,join)
        self.assertGreater(result[:,:3,1].mean(),result[:,6:,1].mean()+.05)
        np.testing.assert_array_equal(result,derive_apron(f,join)[0])
        np.testing.assert_array_equal(z,430)

    def test_apron_opt_in_and_edge_override_order(self):
        source=(Path(__file__).resolve().parents[2]/'unreal/MJOLNIRMaterials/Scripts/build_ce_materials.py').read_text()
        apron=source[source.index('ALPINE_APRON_CODE ='):source.index('PWR_ROCK_CODE =')]
        self.assertLess(apron.index('stone=saturate(fieldGeology.r)'),apron.index('stone = lerp(stone, saturate(edgeGeology.r)'))
        self.assertLess(apron.index('snow=saturate(fieldGeology.g)'),apron.index('snow = lerp(snow, saturate(edgeGeology.g)'))
        self.assertIn('("ApronFieldInfo",(0,0,0,0))',source)
        self.assertIn('field_texture.set_editor_property("srgb",False)',source)
        self.assertIn('field_texture.set_editor_property("compression_settings",unreal.TextureCompressionSettings.TC_VECTOR_DISPLACEMENTMAP)',source)


if __name__=='__main__':unittest.main()
