"""Reject stale or incomplete editor LOD settings before owning a map cook."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from owned_map_cook import (digest, landscape_lod_cook_inputs, landscape_lod_policy_path,
                            snapshot_owned_cook, verified_owned_cook)


class LandscapeLodBindingTests(unittest.TestCase):
    def fixture(self, root):
        land=root/'land'
        land.mkdir()
        spec={'size':316,'components':5,'sections':1,'quads':63,
              'location':[0,0,0],'scale':[100,100,100],'heights':'heights.r16',
              'textures':{'color':'color.png'}}
        (land/'landscape.json').write_text(json.dumps(spec))
        heights=land/spec['heights']
        heights.write_bytes(b'\x00\x80' * spec['size'] ** 2)
        paving=root/'paving.json'
        paving.write_text(json.dumps({'features':[{'geometry':{'type':'Polygon','coordinates':[
            [[130,-130],[140,-130],[140,-140],[130,-140],[130,-130]]]}}]}))
        forced=[[x*63,y*63] for x in range(1,4) for y in range(1,4)]
        policy=root/'policy.json'
        policy.write_text(json.dumps({'schema':'mjolnir-landscape-lod-policy-v1','forced_lod':0,
            'grid':{key:spec[key] for key in ('size','components','sections','quads','location','scale')},
            'heights_sha256':digest(heights),'sources':[{'path':str(paving),'sha256':digest(paving)}],
            'core_section_bases':[[126,126]],'forced_section_bases':forced,
            'minimum_paving_to_morph_boundary_m':67}))
        readback=land/'landscape-lod.readback.json'
        doc={'schema':'mjolnir-landscape-lod-readback-v1','policy_sha256':digest(policy),
             'forced_components':9,'automatic_components':16,
             'components':[{'section_base':[x*63,y*63],'forced_lod':0 if [x*63,y*63] in forced else -1}
                           for x in range(5) for y in range(5)]}
        readback.write_text(json.dumps(doc))
        return {'landscape_lod_policy':str(policy)},policy,readback,doc

    def test_legacy_has_no_lod_dependency(self):
        self.assertEqual(landscape_lod_cook_inputs({},'unused'),{})

    def test_missing_policy_fails_before_editor_launch(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(FileNotFoundError):
                landscape_lod_policy_path({'landscape_lod_policy':str(Path(tmp)/'absent.json')})

    def test_changed_policy_invalidates_editor_readback(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg,policy,readback,doc=self.fixture(Path(tmp))
            self.assertTrue(landscape_lod_cook_inputs(cfg,tmp))
            policy.write_text(policy.read_text()+'\n')
            with self.assertRaisesRegex(ValueError,'stale'):
                landscape_lod_cook_inputs(cfg,tmp)

    def test_current_landscape_grid_must_match_policy(self):
        for key,value in (('size',317),('components',4),('sections',2),('quads',31),
                          ('location',[100,0,0]),('scale',[200,100,100])):
            with self.subTest(key=key),tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp)
                cfg,_,_,_=self.fixture(root)
                spec_path=root/'land/landscape.json'
                spec=json.loads(spec_path.read_text())
                spec[key]=value
                spec_path.write_text(json.dumps(spec))
                with self.assertRaisesRegex(ValueError,'grid differs'):
                    landscape_lod_cook_inputs(cfg,tmp)

    def test_height_and_paving_mutations_invalidate_unchanged_readback(self):
        for relative,error in (('land/heights.r16','height bytes changed'),
                               ('paving.json','source changed')):
            with self.subTest(source=relative),tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp)
                cfg,_,_,_=self.fixture(root)
                source=root/relative
                data=bytearray(source.read_bytes())
                data[0]^=1
                source.write_bytes(data)
                with self.assertRaisesRegex(ValueError,error):
                    landscape_lod_cook_inputs(cfg,tmp)

    def test_missing_current_inputs_fail_closed(self):
        for relative in ('land/landscape.json','land/heights.r16','paving.json'):
            with self.subTest(source=relative),tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp)
                cfg,_,_,_=self.fixture(root)
                (root/relative).unlink()
                with self.assertRaises(FileNotFoundError):
                    landscape_lod_cook_inputs(cfg,tmp)

    def test_owned_receipt_hashes_sources_and_rejects_changed_spec(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            cfg,policy,readback,_=self.fixture(root)
            conversion=root/'conversion'
            staged=root/'staged'
            bake=root/'bake'
            for folder in (conversion,staged,bake):folder.mkdir()
            cfg.update(conversion=str(conversion),chunk=969,tess=False)
            (conversion/'materials.spec.json').write_text(json.dumps({'chunk':968}))
            for ext in ('utoc','ucas'):
                (conversion/f'pakchunk985-MJOLNIRCOOK-TST_P.{ext}').write_bytes(b'conversion')
                (staged/f'pakchunk968-Windows.{ext}').write_bytes(b'owned cook')
                (staged/f'pakchunk969-Windows.{ext}').write_bytes(b'landscape')
                (bake/f'pakchunk969-MJOLNIRLAND-Windows.{ext}').write_bytes(b'landscape')
            with patch('owned_map_cook.check_generated_meshes',return_value={'shadow':'fixture'}):
                target=snapshot_owned_cook('TST',cfg,root,staged,'unused-cli')
            self.assertEqual(verified_owned_cook('TST',cfg,root),target)
            receipt=json.loads((root/'owned-cook.json').read_text())
            dependencies={'landscape_lod_policy':policy,'landscape_lod_readback':readback,
                          'landscape_lod_spec':root/'land/landscape.json',
                          'landscape_lod_heights':root/'land/heights.r16',
                          'landscape_lod_source_0':root/'paving.json'}
            for key,path in dependencies.items():
                self.assertEqual(receipt['inputs'][key],digest(path))
            # Material changes leave the validated LOD grid intact but still require a new cook.
            spec_path=dependencies['landscape_lod_spec']
            spec=json.loads(spec_path.read_text())
            spec['textures']['color']='changed-color.png'
            spec_path.write_text(json.dumps(spec))
            self.assertTrue(landscape_lod_cook_inputs(cfg,root))
            with self.assertRaisesRegex(ValueError,'stale'):
                verified_owned_cook('TST',cfg,root)

    def test_component_omission_duplicate_and_wrong_lod_are_rejected(self):
        for mode in ('omitted','duplicate','wrong_lod'):
            with self.subTest(mode=mode),tempfile.TemporaryDirectory() as tmp:
                cfg,_,readback,doc=self.fixture(Path(tmp))
                if mode=='omitted':doc['components'].pop()
                elif mode=='duplicate':doc['components'].append(doc['components'][0])
                else:doc['components'][0]['forced_lod']=0
                readback.write_text(json.dumps(doc))
                with self.assertRaises(ValueError):landscape_lod_cook_inputs(cfg,tmp)


if __name__=='__main__':unittest.main()
