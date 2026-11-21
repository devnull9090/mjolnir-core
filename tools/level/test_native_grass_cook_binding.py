import json
from pathlib import Path
import shutil
import os
import subprocess
import unittest
from unittest.mock import patch

from owned_map_cook import digest, native_grass_pilot_config, native_grass_pilot_cook_inputs
from upgrade_ce_map import cooked_landscape_world, verify_grass_phase, powershell, bake_world_path


class NativeGrassCookBindingTests(unittest.TestCase):
    def fixture(self):
        from test_landscape_grass_pilot import GrassPilotTests
        fixture=GrassPilotTests('test_fresh_saved_native_weights_pass')
        fixture.setUp();self.addCleanup(fixture.doCleanups)
        root=fixture.folder
        filtered=root/'foliage.json';filtered.write_text('{}')
        fixture.config['filtered_foliage']={'spec':str(filtered),
            'files':[{'path':str(filtered),'sha256':digest(filtered)}]}
        path=root/'pilot.json';path.write_text(json.dumps(fixture.config))
        land=root/'land';land.mkdir()
        (land/'landscape.json').write_text(json.dumps({**fixture.config['grid'],'heights':'heights.r16'}))
        shutil.copyfile(root/'heights.r16',land/'heights.r16')
        fixture.readback['config_sha256']=digest(path)
        saved=root/'grass-saved.readback.json';saved.write_text(json.dumps(fixture.readback))
        cfg={'native_grass_pilot':str(path),'bake_foliage':True,'pcg_foliage':str(filtered),'landscape':'LPW'}
        return root,cfg,path,saved,fixture

    def test_default_world_is_unchanged(self):
        self.assertEqual(cooked_landscape_world({'landscape':'LPW'}),'/Game/Levels/Halo1/Solo/LPW/LPW')
        self.assertEqual(native_grass_pilot_cook_inputs({},'unused'),{})

    def test_long_source_codename_fails_before_native_bake(self):
        self.assertEqual(bake_world_path('PWR',{'landscape':'LPG'}),'/Game/Levels/Halo1/Solo/LPG/LPG')
        with self.assertRaisesRegex(ValueError,'equal-length'):
            bake_world_path('PWR',{'landscape':'PWRGrassPilot'})

    def test_binds_saved_native_buffers_and_filtered_records(self):
        root,cfg,path,saved,fixture=self.fixture()
        inputs=native_grass_pilot_cook_inputs(cfg,root)
        self.assertIn(root/'foliage.json',inputs.values())
        self.assertIn(saved,inputs.values())
        self.assertEqual(cooked_landscape_world(cfg),fixture.config['world'])
        cfg['pcg_foliage']=str(root/'unfiltered.json')
        with self.assertRaisesRegex(ValueError,'filtered meadow'):native_grass_pilot_config(cfg)

    def test_current_height_changes_invalidate_saved_pilot(self):
        root,cfg,_,_,_=self.fixture()
        height=root/'land/heights.r16'
        data=bytearray(height.read_bytes());data[0]^=1;height.write_bytes(data)
        with self.assertRaisesRegex(ValueError,'current landscape'):native_grass_pilot_cook_inputs(cfg,root)

    def test_config_mismatch_cannot_reuse_saved_buffers(self):
        root,cfg,_,saved,fixture=self.fixture()
        fixture.readback['config_sha256']='changed'
        saved.write_text(json.dumps(fixture.readback))
        with self.assertRaisesRegex(ValueError,'another config'):native_grass_pilot_cook_inputs(cfg,root)

    def test_build_cannot_reuse_saved_phase_receipt(self):
        root,_,path,saved,fixture=self.fixture()
        build=root/'grass-build.readback.json'
        build.write_text(saved.read_text())
        with self.assertRaisesRegex(ValueError,'another config or phase'):
            verify_grass_phase(path,'build',0)
        fixture.readback['built']=True
        build.write_text(json.dumps(fixture.readback))
        verify_grass_phase(path,'build',0)
        verify_grass_phase(path,'verify',0)

    def test_old_receipt_cannot_pass_new_phase(self):
        root,_,path,saved,_=self.fixture()
        os.utime(saved,(100,100))
        with self.assertRaisesRegex(ValueError,'fresh receipt'):
            verify_grass_phase(path,'verify',101)
        with self.assertRaisesRegex(ValueError,'fresh receipt'):
            verify_grass_phase(path,'build',0)

    def test_powershell_checks_process_failure(self):
        result=subprocess.CompletedProcess([],7,'BUILD SUCCESSFUL\n','Retarget failed')
        with patch('upgrade_ce_map.subprocess.run',return_value=result):
            with self.assertRaisesRegex(SystemExit,'failed \\(7\\)'):
                powershell('cook.ps1',[])


if __name__=='__main__':unittest.main()
