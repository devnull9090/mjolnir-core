import tempfile
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from owned_map_cook import check_external_assets, external_asset_inputs


class ExternalOwnershipTests(unittest.TestCase):
    def fixture(self, folder):
        stem=Path(folder)/'pakchunk959-MJOLNIRPWRPINE_P'
        for ext in ('.utoc','.ucas'):Path(str(stem)+ext).write_bytes(b'sealed')
        asset='/Game/MJOLNIR/Scenery/PWR/SM_PWR_MaturePine_A'
        return {'extra_containers':[str(stem)],'required_external_assets':[{'asset':asset,'container':str(stem)}]}

    def test_absent_optional_contract_preserves_legacy(self):
        self.assertEqual(check_external_assets({},'none',(1,2),'none'),[])

    def test_required_dependency_must_be_installed_and_exist(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg=self.fixture(tmp);cfg['extra_containers']=[]
            with self.assertRaises(ValueError):external_asset_inputs(cfg)
            cfg=self.fixture(tmp);Path(cfg['extra_containers'][0]+'.ucas').unlink()
            with self.assertRaises(FileNotFoundError):external_asset_inputs(cfg)

    def test_duplicate_map_package_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg=self.fixture(tmp)
            text='Meteorite/Content/MJOLNIR/Scenery/PWR/SM_PWR_MaturePine_A.uasset'
            with patch('owned_map_cook.subprocess.run',return_value=SimpleNamespace(returncode=0,stdout=text,stderr='')):
                with self.assertRaisesRegex(ValueError,'duplicated in'):check_external_assets(cfg,tmp,(43579,965),'cli')

    def test_missing_external_package_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg=self.fixture(tmp)
            with patch('owned_map_cook.subprocess.run',return_value=SimpleNamespace(returncode=0,stdout='',stderr='')):
                with self.assertRaisesRegex(ValueError,'missing'):check_external_assets(cfg,tmp,(43579,965),'cli')

    def test_single_owner_records_hashes(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg=self.fixture(tmp)
            def run(args,**kwargs):
                text='Meteorite/Content/MJOLNIR/Scenery/PWR/SM_PWR_MaturePine_A.uasset' if '959-' in args[-1] else ''
                return SimpleNamespace(returncode=0,stdout=text,stderr='')
            with patch('owned_map_cook.subprocess.run',side_effect=run):
                result=check_external_assets(cfg,tmp,(43579,965),'cli')
            self.assertEqual(len(result),1)
            self.assertEqual(len(result[0]['hashes']['.ucas']),64)


if __name__=='__main__':unittest.main()
