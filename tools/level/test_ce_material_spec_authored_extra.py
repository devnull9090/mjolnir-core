"""Exercise the native-only authored material path without Unreal or the game."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from authored_surfaces import apply_library, load_library
from ce_material_spec import add_authored_extra_slots

ROOT = Path(__file__).resolve().parents[2]
LIBRARY = ROOT / 'levels/test/tst/surfaces.json'


class NativeAuthoredSlots(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.addCleanup(self.temp.cleanup)
        self.surfaces = load_library(LIBRARY)
        self.materials = [{'name': 'existing', 'parent': 'stock'}]
        self.slots = [{'name': 'existing', 'pattern': 'existing$', 'material': {'parent': 'stock'}}]
        self.gltf = [{'name': 'existing', 'extras': {'halo': {'tag_path': 'levels/b30/stock'}}}]

    def write_extra(self, materials, indices=None):
        if indices is None:
            indices = list(range(len(materials)))
        path = self.root / 'extra.gltf'
        path.write_text(json.dumps({'asset': {'version': '2.0'}, 'materials': materials,
                                    'meshes': [{'primitives': [{'material': i} for i in indices]}]}),
                        encoding='utf-8')
        return path

    def material(self, role):
        return {'name': 'native_' + role,
                'extras': {'halo': {'tag_path': self.surfaces[role]['tag'].replace('/', '\\')}}}

    def test_missing_staged_shaders_bind_all_exact_authored_roles(self):
        # Every authored tag is deliberately absent from staged CE shaders:
        # all slots must still bind through the validated source palette.
        extra = self.write_extra([self.material(role) for role in self.surfaces])
        add_authored_extra_slots(extra, LIBRARY, self.materials, self.slots, self.gltf)
        textures = {}
        surfaces = apply_library(LIBRARY, '/Game/MJOLNIR/Maps/TST',
                                 self.materials, self.slots, self.gltf, textures)
        self.assertEqual(set(surfaces), set(self.surfaces))
        self.assertEqual(self.slots[0]['material'], {'parent': 'stock'})
        for role, slot in zip(self.surfaces, self.slots[1:]):
            self.assertEqual(slot['pattern'], 'native_' + role + '$')
            self.assertEqual(slot['material']['parent'],
                f'/Game/MJOLNIR/Maps/TST/SurfaceMaterials/M_Authored_{role}.M_Authored_{role}')
        self.assertTrue(any(t.get('normal_map') and t.get('flip_green_channel')
                            for t in textures.values()))

    def test_rejects_unknown_tag_or_unsafe_name_without_partial_mutation(self):
        valid = self.material('armor')
        bad_tag = self.material('recess')
        bad_tag['extras']['halo']['tag_path'] += '_fake'
        bad_name = self.material('structure')
        bad_name['name'] = '../structure'
        for bad in (bad_tag, bad_name):
            before = copy.deepcopy((self.materials, self.slots, self.gltf))
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                add_authored_extra_slots(self.write_extra([valid, bad]), LIBRARY,
                                         self.materials, self.slots, self.gltf)
            self.assertEqual((self.materials, self.slots, self.gltf), before)

    def test_rejects_duplicate_and_existing_names_case_insensitively(self):
        for names in (('native_a', 'NATIVE_A'), ('existing', 'native_b'),
                      ('native_a_2', 'native_a_n2')):
            mats = [self.material('armor'), self.material('recess')]
            for mat, name in zip(mats, names): mat['name'] = name
            with self.subTest(names=names), self.assertRaisesRegex(ValueError, 'collides'):
                add_authored_extra_slots(self.write_extra(mats), LIBRARY,
                                         self.materials, self.slots, self.gltf)

    def test_rejects_unreferenced_and_invalid_primitive_materials(self):
        mats = [self.material('armor'), self.material('recess')]
        for indices in ([0], [0, 2], [0, True], []):
            with self.subTest(indices=indices), self.assertRaises(ValueError):
                add_authored_extra_slots(self.write_extra(mats, indices), LIBRARY,
                                         self.materials, self.slots, self.gltf)

    def test_requires_library(self):
        with self.assertRaisesRegex(ValueError, 'requires --surface-library'):
            add_authored_extra_slots(self.write_extra([self.material('armor')]), None,
                                     self.materials, self.slots, self.gltf)

    def test_cli_extra_is_opt_in_and_does_not_need_ce_shader_records(self):
        staging = self.root / 'staging'
        staging.mkdir()
        (staging / 'materials.json').write_text('{}', encoding='utf-8')
        scene = self.root / 'scene.gltf'
        scene.write_text(json.dumps({'materials': [], 'meshes': [], 'accessors': []}), encoding='utf-8')
        extra = self.write_extra([self.material(role) for role in self.surfaces])
        destination = self.root / 'materials.spec.json'
        command = [sys.executable, str(ROOT / 'tools/level/ce_material_spec.py'),
                   str(staging), 'TST', str(destination), str(scene), '--code', 'TST']
        plain = subprocess.run(command, capture_output=True, text=True)
        self.assertEqual(plain.returncode, 0, plain.stderr)
        self.assertEqual(json.loads(destination.read_text())['slots'], [])
        added = subprocess.run(command + ['--surface-library', str(LIBRARY),
                                          '--authored-extra-gltf', str(extra)],
                               capture_output=True, text=True)
        self.assertEqual(added.returncode, 0, added.stderr)
        result = json.loads(destination.read_text())
        self.assertEqual(result['chunk'], 968)
        self.assertEqual(len(result['slots']), len(self.surfaces))
        self.assertEqual(set(result['authored_surfaces']), set(self.surfaces))
        self.assertTrue(all('M_Authored_' in slot['material']['parent'] for slot in result['slots']))
        missing_library = subprocess.run(command + ['--authored-extra-gltf', str(extra)],
                                         capture_output=True, text=True)
        self.assertNotEqual(missing_library.returncode, 0)
        self.assertIn('requires --surface-library', missing_library.stderr)


if __name__ == '__main__':
    unittest.main()
