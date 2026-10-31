"""Facility runtime-light export is opt-in and preserves authoring coordinates."""
import json
import math
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import upgrade_ce_map as upgrade


class AuthoredMapLightsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.conv = self.root / 'conversion'
        self.conv.mkdir()
        self.path = self.root / 'lights.json'
        self.doc = {
            'required_surfaces': ['facility_armor', 'facility_floor'],
            'required_slot_fragments': ['tst_metal_facility_armor', 'tst_metal_facility_floor'],
            'lights': [{'name': 'fixture', 'position_m': [-16, 34, 3.5],
                        'colour': [0.82, 0.91, 1], 'intensity': .12,
                        'radius_cm': 650, 'falloff': 4}],
        }
        self.write(self.path, self.doc)
        self.spec = self.conv / 'materials.spec.json'
        self.write(self.spec, {'authored_surfaces': {'facility_armor': {}, 'facility_floor': {}},
                               'slots': [{'name': 'levels_tst_metal_facility_armor__lm0'},
                                         {'name': 'levels_tst_metal_facility_floor__lm5'}]})
        self.repo = patch.object(upgrade, 'REPO', str(self.root))
        self.repo.start()
        self.addCleanup(self.repo.stop)
        self.map = {'authored_lights': 'lights.json'}
        self.paths = {'conv': str(self.conv)}

    @staticmethod
    def write(path, value):
        path.write_text(json.dumps(value), encoding='utf-8')

    def test_converts_metres_and_y_axis_for_loader_without_changing_parameters(self):
        self.assertEqual(upgrade.authored_map_lights(self.map, self.paths), [
            {'name': 'fixture', 'pos': [-1600, -3400, 350], 'colour': [.82, .91, 1],
             'intensity': .12, 'radius': 650, 'falloff': 4}])

    def test_unconfigured_or_older_conversion_has_no_facility_lights(self):
        self.assertEqual(upgrade.authored_map_lights({}, self.paths), [])
        self.write(self.spec, {'authored_surfaces': {'armor': {}}})
        self.assertEqual(upgrade.authored_map_lights(self.map, self.paths), [])
        self.write(self.spec, {'authored_surfaces': {'facility_armor': {}, 'facility_floor': {}},
                               'slots': [{'name': 'levels_tst_metal_armor__lm0'}]})
        self.assertEqual(upgrade.authored_map_lights(self.map, self.paths), [])
        self.spec.unlink()
        self.assertEqual(upgrade.authored_map_lights(self.map, self.paths), [])

    def test_rejects_invalid_or_duplicate_lights(self):
        for key, value in [('intensity', math.nan), ('radius_cm', 0), ('falloff', -1),
                           ('colour', [1, -1, 1]), ('position_m', [1, 2, True])]:
            with self.subTest(key=key):
                doc = json.loads(json.dumps(self.doc))
                doc['lights'][0][key] = value
                self.write(self.path, doc)
                with self.assertRaises(ValueError):
                    upgrade.authored_map_lights(self.map, self.paths)
        self.doc['lights'].append(dict(self.doc['lights'][0]))
        self.write(self.path, self.doc)
        with self.assertRaisesRegex(ValueError, 'unique'):
            upgrade.authored_map_lights(self.map, self.paths)

    def test_requires_an_explicit_surface_guard(self):
        self.doc['required_surfaces'] = []
        self.write(self.path, self.doc)
        with self.assertRaisesRegex(ValueError, 'surface-role guard'):
            upgrade.authored_map_lights(self.map, self.paths)

    def test_assembly_retains_existing_ce_lights_and_appends_authored_fixture(self):
        self.write(self.root / 'landscape.json', {})
        self.write(self.root / 'source.json', {'environment': {}, 'decor': []})
        paths = dict(self.paths, land=str(self.root), work=str(self.root), scene=str(self.root),
                     level=str(self.root / 'source.json'), out_level=str(self.root / 'level.json'))
        existing = {'name': 'base fixture', 'pos': [0, 0, 100], 'intensity': 2.344}
        config = dict(self.map, indoor=True)
        with patch.object(upgrade, 'ce_lights', return_value=[existing]), \
             patch.object(upgrade, 'ce_decals', return_value=([], [])):
            upgrade.stage_assemble('TST', config, paths)
        result = json.loads((self.root / 'level.json').read_text(encoding='utf-8'))
        self.assertEqual(result['lights'][0], existing)
        self.assertEqual(result['lights'][1]['name'], 'fixture')
        self.assertEqual(result['lights'][1]['pos'], [-1600, -3400, 350])


if __name__ == '__main__':
    unittest.main()
