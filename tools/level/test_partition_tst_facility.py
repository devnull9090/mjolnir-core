"""Round-trip the exact CE/native triangle partition without touching game data."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

import numpy as np

from partition_tst_facility import partition, read_jms


def write_jms(path, private=True):
    materials = ['tst_metal_facility_armor!', 'tst_metal_structure!',
                 'tst_lights_amber!', 'tst_metal_facility_armor', 'tst_water!']
    # Two detail triangles inside; everything else must remain byte-for-byte
    # in CE, including metal outside, amber, collision metal, and water.
    definitions = [(0, 0, 800), (1, 0, 900), (0, 0, 400), (2, 0, 850),
                   (3, 0, 850), (4, 0, 850)]
    lines = ['8200', '123', '1', 'frame', '-1', '-1', '0 0 0 1', '0 0 0', str(len(materials))]
    for name in materials:
        lines += [name, '<none>']
    lines += ['0', '1', 'default', str(len(definitions) * 3)]
    for index, (_, x, y) in enumerate(definitions):
        for dx, dy, dz in ((0, 0, 0), (10, 0, 0), (0, 10, 0)):
            lines += ['0', f'{x+dx} {y+dy} {dz}', '0 0 1', '-1', '0',
                      f'{index / 10 + dx / 100} {dy / 100}', '0']
    lines += [str(len(definitions))]
    for i, (material, _, _) in enumerate(definitions):
        indexes = (3*i, 3*i+1, 3*i+2) if private or i else (0, 1, 3)
        lines += ['0', str(material), ' '.join(str(v) for v in indexes)]
    path.write_text('\n'.join(lines) + '\n', encoding='utf-8')


def write_library(folder):
    for name in ('albedo.png', 'roughness.png'):
        (folder / name).write_bytes(b'owned image fixture')
    surfaces = {}
    for role in ('facility_armor', 'structure'):
        surfaces[role] = {'tag': f'levels/test/tst/shaders/tst_metal_{role}',
                          'albedo': 'albedo.png', 'roughness_map': 'roughness.png',
                          'tint': [1, 1, 1], 'roughness': [0.2, 0.8],
                          'metallic': 0.1, 'soften': 0}
    path = folder / 'surfaces.json'
    path.write_text(json.dumps({'version': 1, 'surfaces': surfaces}), encoding='utf-8')
    return path


def get_accessor(doc, data, index):
    access = doc['accessors'][index]
    view = doc['bufferViews'][access['bufferView']]
    width = {'SCALAR': 1, 'VEC2': 2, 'VEC3': 3}[access['type']]
    dtype = '<f4' if access['componentType'] == 5126 else '<u4'
    return np.frombuffer(data, dtype=dtype, count=access['count']*width,
                         offset=view['byteOffset']).reshape(-1, width)


class PartitionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.source = self.root / 'source.JMS'
        write_jms(self.source)
        self.library = write_library(self.root)

    def tearDown(self):
        self.temp.cleanup()

    def test_partition_is_disjoint_and_preserves_ce_records_and_native_attributes(self):
        before = self.source.read_bytes()
        original = read_jms(self.source)
        out = self.root / 'new-output'
        result = partition(self.source, self.library, out)
        self.assertEqual(self.source.read_bytes(), before)
        self.assertEqual((result['source_triangles'], result['ce_triangles'], result['native_triangles']), (6, 4, 2))
        self.assertEqual(result['source_sha256'], hashlib.sha256(before).hexdigest())
        ce = read_jms(out / 'tst-ce-structure.JMS')
        kept = [2, 3, 4, 5]
        self.assertEqual(ce[2], [original[2][i*3+j].replace(b'\r\n', b'\n')
                                 for i in kept for j in range(3)])
        np.testing.assert_array_equal(ce[7], original[7][kept])
        doc = json.loads((out / 'tst-facility-detail.gltf').read_text())
        data = (out / 'tst-facility-detail.bin').read_bytes()
        by_role = {m['extras']['halo']['tag_path'].rsplit('_', 1)[-1]: m for m in doc['materials']}
        self.assertEqual(len(by_role), 2)
        for primitive in doc['meshes'][0]['primitives']:
            mat = doc['materials'][primitive['material']]
            role = mat['name'].removeprefix('tst_native_detail_')
            old = 0 if role == 'facility_armor' else 1
            ids = np.arange(old*3, old*3+3)
            p, n, uv = original[3][ids], original[4][ids], original[5][ids]
            expected_pos = np.column_stack((p[:, 0], p[:, 2], -p[:, 1])) * 0.03048
            expected_normal = np.column_stack((n[:, 0], n[:, 2], -n[:, 1]))
            attrs = primitive['attributes']
            np.testing.assert_allclose(get_accessor(doc, data, attrs['POSITION']), expected_pos, atol=2e-6)
            np.testing.assert_allclose(get_accessor(doc, data, attrs['NORMAL']), expected_normal)
            np.testing.assert_allclose(get_accessor(doc, data, attrs['TEXCOORD_0']), uv, atol=1e-6)
            np.testing.assert_array_equal(get_accessor(doc, data, primitive['indices']).ravel(), [0, 1, 2])
            self.assertTrue(mat['extras']['halo']['tag_path'].endswith('tst_metal_' + role))

    def test_existing_destination_and_non_private_vertices_are_refused(self):
        out = self.root / 'occupied'
        out.mkdir()
        marker = out / 'keep.txt'
        marker.write_text('keep')
        with self.assertRaises(FileExistsError):
            partition(self.source, self.library, out)
        self.assertEqual(marker.read_text(), 'keep')
        write_jms(self.source, private=False)
        with self.assertRaisesRegex(ValueError, 'private ordered'):
            partition(self.source, self.library, self.root / 'bad')
        self.assertFalse((self.root / 'bad').exists())

    def test_unknown_authored_metal_is_refused(self):
        text = self.source.read_text().replace('tst_metal_structure!', 'tst_metal_unknown!')
        self.source.write_text(text)
        with self.assertRaisesRegex(ValueError, 'no exact authored role'):
            partition(self.source, self.library, self.root / 'bad')

    def test_escaping_texture_paths_are_refused(self):
        doc = json.loads(self.library.read_text())
        for raw in ('../outside.png', '/outside.png', 'C:/outside.png', 'art/../outside.png'):
            with self.subTest(raw=raw):
                doc['surfaces']['structure']['albedo'] = raw
                self.library.write_text(json.dumps(doc))
                with self.assertRaisesRegex(ValueError, 'texture path'):
                    partition(self.source, self.library, self.root / 'bad')


if __name__ == '__main__':
    unittest.main()
