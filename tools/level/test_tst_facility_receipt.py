"""Reject mismatched TST map/detail pairs and material specifications."""
import json
import os
from pathlib import Path
import tempfile
import unittest

from authored_surfaces import load_library
from partition_tst_facility import partition, sha256
from test_partition_tst_facility import write_jms, write_library
from make_tst_facility_receipt import create
from verify_tst_facility_receipt import PREDICATE, verify


class FacilityReceiptTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.source = self.root / 'source.JMS'
        write_jms(self.source)
        self.library = write_library(self.root)
        self.part = self.root / 'partition'
        self.manifest = partition(self.source, self.library, self.part)
        self.detail = self.part / 'tst-facility-detail.gltf'
        self.map = self.root / 'tst.map'
        self.map.write_bytes(b'validated map fixture')
        files = self.manifest['files']
        self.receipt_data = {
            'format': 'tst-facility-ce-build-v1',
            'partition_format': self.manifest['format'], 'predicate': PREDICATE,
            'partition_manifest_sha256': sha256(self.part / 'manifest.json'),
            'source_jms_sha256': sha256(self.source),
            'ce_jms_sha256': files['tst-ce-structure.JMS'],
            'native_gltf_sha256': files['tst-facility-detail.gltf'],
            'native_bin_sha256': files['tst-facility-detail.bin'],
            'texture_hashes': self.manifest['texture_hashes'],
            'surface_library_sha256': sha256(self.library), 'ce_map_sha256': sha256(self.map),
            'hek_input_jms_sha256': files['tst-ce-structure.JMS'],
            'build_input_manifest_sha256': 'a' * 64, 'structure_bsp_sha256': 'b' * 64,
            'structure_log_sha256': 'c' * 64, 'scenario_log_sha256': 'd' * 64,
            'scenario_sha256': 'e' * 64, 'lightmap_log_sha256': 'f' * 64,
            'lightmap_bitmap_sha256': '0' * 64, 'cache_log_sha256': '1' * 64,
        }
        self.receipt = self.root / 'build-receipt.json'
        self.write_receipt()

    def tearDown(self):
        self.temp.cleanup()

    def write_receipt(self):
        self.receipt.write_text(json.dumps(self.receipt_data), encoding='utf-8')

    def check(self, spec=None):
        return verify(self.part, self.detail, self.receipt, self.source, self.library, self.map, spec)

    def spec(self):
        library = load_library(self.library)
        detail = json.loads(self.detail.read_text())
        roles_by_tag = {value['tag']: role for role, value in library.items()}
        slots = []
        for material in detail['materials']:
            role = roles_by_tag[material['extras']['halo']['tag_path']]
            leaf = 'M_Authored_' + role
            slots.append({'pattern': material['name'].lower() + '$', 'material': {
                'parent': f'/Game/MJOLNIR/Maps/TST/SurfaceMaterials/{leaf}.{leaf}'}})
        path = self.root / 'materials.spec.json'
        path.write_text(json.dumps({'root': '/Game/MJOLNIR/Maps/TST', 'chunk': 968,
                                    'authored_surfaces': library, 'slots': slots}), encoding='utf-8')
        return path

    def test_valid_pair_and_spec_are_bound(self):
        spec = self.spec()
        result = self.check(spec)
        self.assertEqual(result['format'], 'tst-facility-native-conversion-v1')
        self.assertEqual(result['material_spec_sha256'], sha256(spec))
        self.assertEqual(result['native_material_slots'], 2)

    def test_every_receipt_claim_must_match(self):
        for key in ('partition_manifest_sha256', 'source_jms_sha256', 'ce_jms_sha256',
                    'native_gltf_sha256', 'native_bin_sha256', 'surface_library_sha256', 'ce_map_sha256',
                    'predicate', 'partition_format', 'hek_input_jms_sha256', 'texture_hashes',
                    'build_input_manifest_sha256', 'structure_bsp_sha256',
                    'structure_log_sha256', 'scenario_log_sha256', 'scenario_sha256',
                    'lightmap_log_sha256', 'lightmap_bitmap_sha256', 'cache_log_sha256'):
            with self.subTest(key=key):
                old = self.receipt_data[key]
                self.receipt_data[key] = 'different'
                self.write_receipt()
                with self.assertRaises(ValueError):
                    self.check()
                self.receipt_data[key] = old
        self.write_receipt()

    def test_actual_map_and_external_buffer_changes_are_refused(self):
        self.map.write_bytes(b'other map')
        with self.assertRaisesRegex(ValueError, 'ce_map_sha256'):
            self.check()
        self.map.write_bytes(b'validated map fixture')
        buffer = self.part / 'tst-facility-detail.bin'
        buffer.write_bytes(buffer.read_bytes() + b'changed')
        with self.assertRaisesRegex(ValueError, 'changed'):
            self.check()

    def test_material_and_slot_changes_are_refused(self):
        spec = self.spec()
        value = json.loads(spec.read_text())
        value['slots'][0]['material']['parent'] = '/Game/Wrong.Wrong'
        spec.write_text(json.dumps(value))
        with self.assertRaisesRegex(ValueError, 'authored slot'):
            self.check(spec)
        spec = self.spec()
        value = json.loads(spec.read_text())
        value['authored_surfaces']['structure']['metallic'] = 0.99
        spec.write_text(json.dumps(value))
        with self.assertRaisesRegex(ValueError, 'differs from source role'):
            self.check(spec)

    def test_texture_bytes_and_missing_textures_fail_before_and_after_spec(self):
        spec = self.spec()
        texture = self.root / 'albedo.png'
        texture.write_bytes(b'changed')
        for current_spec in (None, spec):
            with self.assertRaisesRegex(ValueError, 'texture hashes'):
                self.check(current_spec)
        texture.unlink()
        for current_spec in (None, spec):
            with self.assertRaisesRegex(ValueError, 'missing or outside'):
                self.check(current_spec)

    def test_detail_must_be_the_manifest_gltf(self):
        other = self.root / 'other.gltf'
        other.write_bytes(self.detail.read_bytes())
        with self.assertRaisesRegex(ValueError, 'not the glTF'):
            verify(self.part, other, self.receipt, self.source, self.library, self.map)

    def test_receipt_creator_requires_frozen_inputs_and_successful_logs(self):
        bsp = self.root / 'structure.bsp'
        bsp.write_bytes(b'verified BSP fixture')
        hek_input = self.part / 'tst-ce-structure.JMS'
        frozen = self.root / 'frozen.json'
        frozen.write_text(json.dumps({'hashes': {'jms': sha256(hek_input).upper(),
            'bsp': sha256(bsp).upper(), 'surfaces': sha256(self.library).upper()}}))
        structure = self.root / 'structure.log'
        structure.write_text('structure bsp tst\n0 portals, 1 clusters\nwithout debug information')
        scenario = self.root / 'tst.scenario'
        scenario.write_bytes(b'scenario fixture')
        scenario_log = self.root / 'scenario.log'
        scenario_log.write_text(json.dumps({'roundtrip': 'passed', 'scenario': str(scenario),
                                            'sha256': sha256(scenario)}))
        lightmap = self.root / 'lightmap.log'
        lightmap.write_text(r'finished levels\test\tst\tst' + '\ndone')
        bitmap = self.root / 'lightmap.bitmap'
        bitmap.write_bytes(b'lightmap fixture')
        cache = self.root / 'cache.log'
        cache.write_text('successfully built cache file.')
        # A genuinely new map follows the input snapshot.
        self.map.write_bytes(b'new build')
        def build():
            return create(self.part, self.detail, self.source, self.library, self.map,
                          frozen, hek_input, bsp, structure, scenario_log, lightmap, bitmap, cache)
        receipt = build()
        self.assertEqual(receipt['hek_input_jms_sha256'], sha256(hek_input))
        self.assertEqual(receipt['structure_bsp_sha256'], sha256(bsp))
        snapshot = json.loads(frozen.read_text())
        snapshot['texture_hashes'] = dict(self.manifest['texture_hashes'])
        snapshot['texture_hashes']['albedo.png'] = '0' * 64
        frozen.write_text(json.dumps(snapshot))
        with self.assertRaisesRegex(ValueError, 'different owned texture bytes'):
            build()
        snapshot['texture_hashes'] = self.manifest['texture_hashes']
        frozen.write_text(json.dumps(snapshot))
        build()
        cache.write_text('successfully built cache file.\nEXCEPTION_ACCESS_VIOLATION')
        with self.assertRaisesRegex(ValueError, 'Cache log'):
            build()
        cache.write_text('successfully built cache file.')
        structure.write_text('structure bsp tst\n0 portals, 1 clusters\nwithout debug information\nEXCEPTION_ACCESS_VIOLATION')
        with self.assertRaisesRegex(ValueError, 'Structure log'):
            build()
        structure.write_text('structure bsp tst\n0 portals, 1 clusters\nwithout debug information')
        lightmap.write_text('unfinished')
        with self.assertRaisesRegex(ValueError, 'Lightmap log'):
            build()
        lightmap.write_text(r'finished levels\test\tst\tst' + '\ndone')
        bsp.write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError, 'Structure BSP'):
            build()
        bsp.write_bytes(b'verified BSP fixture')
        os.utime(self.map, (1, 1))
        with self.assertRaisesRegex(ValueError, 'predates'):
            build()


if __name__ == '__main__':
    unittest.main()
