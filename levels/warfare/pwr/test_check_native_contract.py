import copy
from dataclasses import replace
import json
from pathlib import Path
import tempfile
import unittest

import numpy as np
import check_native_contract as check


class FrozenContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.frozen, cls.layout, cls.level, cls.baseline, cls.geometry, cls.required = check.load_frozen_contract()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        metadata = copy.deepcopy(self.baseline.metadata)
        metadata['geometry'] = str((self.baseline.path.parent / metadata['geometry']).resolve())
        metadata['preservation'] = {
            'baseline_manifest_sha256': self.baseline.manifest_sha256,
            'baseline_height_sha256': self.baseline.metadata['height']['sha256'],
            'geometry_sha256': self.frozen['geometry']['sha256'],
            'layout_sha256': self.frozen['layout']['sha256'], 'protected_mask': 'protected'}
        self.candidate = replace(self.baseline, metadata=metadata, path=root/'runtime-master.json',
            manifest_sha256='b'*64, heights_m=self.baseline.heights_m.copy(),
            masks={**self.baseline.masks, 'protected': self.required.astype(float)})
        self.raw = np.fromfile(self.baseline.path.with_suffix('.r16'), dtype='<u2').reshape(self.baseline.heights_m.shape)
        self.candidate_layout = copy.deepcopy(self.layout)
        self.candidate_layout['provenance']['master_manifest_sha256'] = self.candidate.manifest_sha256
        self.publish_raw()

    def publish_raw(self):
        path = self.candidate.path.with_suffix('.r16')
        path.write_bytes(self.raw.tobytes())
        self.candidate.metadata['landscape_encoding']['r16_sha256'] = check.sha256(path)
        encoding = self.candidate.metadata['landscape_encoding']
        self.candidate.heights_m = ((encoding['centre_cm']+(self.raw.astype(float)-32768)*encoding['z_scale']/128)[::-1]/100)

    def run_check(self):
        return check.check_terrain(self.candidate, self.candidate_layout, self.frozen, self.layout,
            self.level, self.baseline, self.geometry, self.required)

    def test_frozen_baseline_and_new_unprotected_landform_pass(self):
        report = check.check_terrain(self.baseline, self.layout, self.frozen, self.layout,
            self.level, self.baseline, self.geometry, self.required)
        self.assertTrue(report['candidate_is_baseline'])
        j, i = np.argwhere(~self.required)[0]
        self.raw[-1-j, i] += 32
        self.publish_raw()
        report = self.run_check()
        self.assertEqual(report['protected_max_abs_error_m'], 0)
        self.assertEqual(report['flight_altitude_m'], 550)

    def test_one_quantization_step_on_protected_floor_rejected(self):
        j, i = np.argwhere(self.required)[0]
        self.raw[-1-j, i] += 1
        self.publish_raw()
        with self.assertRaisesRegex(ValueError, 'Protected runtime floor'):
            self.run_check()

    def test_missing_or_nonbinary_protection_rejected(self):
        j, i = np.argwhere(self.required)[0]
        self.candidate.masks['protected'][j, i] = 0
        with self.assertRaisesRegex(ValueError, 'omits required'):
            self.run_check()
        self.candidate.masks['protected'][j, i] = .5
        with self.assertRaisesRegex(ValueError, 'exact binary'):
            self.run_check()

    def test_changed_spawn_rejected_even_when_ten_guard_markers_unchanged(self):
        self.candidate_layout['spawns_m']['red'][0][0] += .01
        self.assertEqual(check.marker_points(self.layout), check.marker_points(self.candidate_layout))
        with self.assertRaisesRegex(ValueError, 'spawns_m'):
            self.run_check()

    def test_changed_timings_and_lowered_flights_rejected(self):
        self.candidate_layout['forced_exit_seconds'] = 53
        with self.assertRaises(ValueError): self.run_check()
        self.candidate_layout = copy.deepcopy(self.layout)
        self.candidate_layout['flights_m']['red']['start'][2] = 525
        with self.assertRaises(ValueError): self.run_check()

    def test_wrong_runtime_encoding_and_high_peak_rejected(self):
        self.candidate.heights_m[0, 0] += .001
        with self.assertRaisesRegex(ValueError, 'actual encoded Landscape'):
            self.run_check()
        self.publish_raw()
        j, i = np.argwhere(~self.required)[0]
        self.raw[-1-j, i] = 32768 + 23000  # 403.6875 m under the frozen transform.
        self.publish_raw()
        with self.assertRaisesRegex(ValueError, 'obstacle envelope'):
            self.run_check()

    def test_geometry_and_preservation_hash_mismatch_rejected(self):
        self.candidate.metadata['geometry_sha256'] = '0'*64
        with self.assertRaisesRegex(ValueError, 'geometry hash'):
            self.run_check()
        self.candidate.metadata['geometry_sha256'] = self.frozen['geometry']['sha256']
        self.candidate.metadata['preservation']['layout_sha256'] = '0'*64
        with self.assertRaisesRegex(ValueError, 'preservation provenance'):
            self.run_check()

    def test_native_vehicle_change_rejected_but_new_probe_flags_allowed(self):
        prepared = copy.deepcopy(self.level)
        prepared['blam']['cutscene_flags'].append({'name':'terrain_probe_new', 'pos':[1,2,3], 'yaw':0})
        self.assertEqual(check.gameplay_level(prepared), self.level)
        prepared['blam']['vehicles'][0]['pos'][0] += 1
        with self.assertRaisesRegex(ValueError, 'vehicles'):
            check.assert_equal(self.level, check.gameplay_level(prepared), 'gameplay')

    def test_probe_plan_rejects_stale_terrain_and_changed_marker(self):
        root = Path(self.temp.name)
        layout_path = root/'layout.json'; layout_path.write_text(json.dumps(self.candidate_layout))
        ordered = root/'ordered.npz'; ordered.write_bytes(b'test ordered stream')
        terrain_receipt = root/'terrain.json'; terrain_receipt.write_text('{}')
        collision = {'receipt_sha256':'1'*64, 'compiled_collision_sha256':'2'*64}
        plan = {'schema':'pwr-terrain-probe-v1', 'protocol':20569, 'layout_revision':3,
            'master_manifest_sha256':self.candidate.manifest_sha256,
            'height_sha256':self.candidate.metadata['height']['sha256'],
            'provenance':{'compiled_boundaries_verified':True, 'receipt_sha256':'1'*64,
                'compiled_tag_sha256':'2'*64, 'ordered_path':str(ordered), 'ordered_sha256':check.sha256(ordered),
                'terrain_receipt_path':str(terrain_receipt), 'terrain_receipt_sha256':check.sha256(terrain_receipt),
                'layout_sha256':check.sha256(layout_path)},
            'probes':[{'flag':f'terrain_probe_{i}', 'position_m':[1,2,3], 'yaw':90} for i in range(12)]}
        path=root/'plan.json'; path.write_text(json.dumps(plan))
        level={'blam':{'cutscene_flags':[
            {'name':f'terrain_probe_{i}','pos':[100,-200,300],'yaw':90} for i in range(12)] +
            [{'name':'terrain_probe_hash_'+check.sha256(path)[:12],'pos':[100,-200,300],'yaw':0}]}}
        check.check_probe_plan(path,self.candidate,layout_path,collision,level)
        level['blam']['cutscene_flags'][0]['pos'][0]+=1
        with self.assertRaisesRegex(ValueError,'probe coordinates'):
            check.check_probe_plan(path,self.candidate,layout_path,collision,level)
        plan['master_manifest_sha256']=self.baseline.manifest_sha256
        path.write_text(json.dumps(plan))
        with self.assertRaisesRegex(ValueError,'another terrain'):
            check.check_probe_plan(path,self.candidate,layout_path,collision,level)

    def test_collision_hash_and_obstacle_envelope_are_checked(self):
        root=Path(self.temp.name);source=root/'collision.json'; source.write_text('{}')
        source.with_suffix('.bin').write_bytes(b'collision')
        output=root/'map.sbsp';output.write_bytes(b'compiled')
        doc={'schema':'mjolnir-collision-pieces-v1','delta_wu':[0,0,0],
            'source_manifest':str(source),'source_manifest_sha256':check.sha256(source),
            'source_binary_sha256':check.sha256(source.with_suffix('.bin')),
            'output':str(output),'output_sha256':check.sha256(output),
            'pieces':[{'bounds_wu':{'max':[0,0,400/3.048]}}]}
        receipt=root/'receipt.json';receipt.write_text(json.dumps(doc))
        self.assertEqual(check.check_collision(receipt,self.frozen)['static_collision_max_m'],400)
        output.write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError,'hashes are stale'):check.check_collision(receipt,self.frozen)
        doc['output_sha256']=check.sha256(output);doc['pieces'][0]['bounds_wu']['max'][2]=419/3.048
        receipt.write_text(json.dumps(doc))
        with self.assertRaisesRegex(ValueError,'obstacle envelope'):check.check_collision(receipt,self.frozen)


if __name__ == '__main__':
    unittest.main()
