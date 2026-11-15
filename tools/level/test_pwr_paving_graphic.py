import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import pwr_paving_graphic as graphic


class PavingGraphicTests(unittest.TestCase):
    def manifest(self):
        image, prompt = graphic.ASSET / 'panel-albedo.png', graphic.ASSET / 'prompt.txt'
        return {'schema': 'pwr-paving-graphic-v1', 'package': graphic.PACKAGE,
                'source': {'path': str(image), 'sha256': graphic.digest(image),
                           'dimensions': [1254, 1254], 'prompt': str(prompt),
                           'prompt_sha256': graphic.digest(prompt)},
                'build': copy.deepcopy(graphic.BUILD),
                'encoding': 'original sRGB albedo; not height, normal, roughness or AO'}

    def test_original_and_prompt_are_sealed_cook_inputs(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'graphic.json'
            graphic.dump(path, self.manifest())
            image, spec = graphic.load_graphic_manifest(path)
            self.assertEqual(graphic.digest(image), graphic.SOURCE_SHA)
            self.assertEqual(len(graphic.graphic_cook_inputs(path)), 3)
            self.assertEqual(spec['source']['dimensions'], [1254, 1254])

    def test_false_resolution_encoding_and_sampler_claims_fail_closed(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'graphic.json'
            for category, key, value in [('build', 'dimensions', [2048, 2048]),
                                         ('build', 'srgb', False), ('build', 'address_x', 'wrap'),
                                         ('source', 'dimensions', [1024, 1024]),
                                         ('source', 'sha256', '0' * 64),
                                         ('source', 'prompt_sha256', '0' * 64)]:
                document = self.manifest();document[category][key] = value
                graphic.dump(path, document)
                with self.assertRaises(ValueError):graphic.load_graphic_manifest(path)
            document = self.manifest();document['encoding'] = 'height'
            graphic.dump(path, document)
            with self.assertRaises(ValueError):graphic.load_graphic_manifest(path)

    def test_changed_image_and_prompt_are_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder);path = root / 'graphic.json'
            for name in ('image', 'prompt'):
                document = self.manifest();changed = root / name
                source_key = 'path' if name == 'image' else 'prompt'
                original = Path(document['source'][source_key])
                changed.write_bytes(original.read_bytes() + b'changed')
                document['source'][source_key] = str(changed)
                graphic.dump(path, document)
                with self.assertRaises(ValueError):graphic.load_graphic_manifest(path)

    def test_preparation_keeps_native_maps_exact_and_enables_every_owned_slot(self):
        source = graphic.ROOT / 'out/pwr/visual-v6/surface/paving'
        with tempfile.TemporaryDirectory() as folder:
            out = Path(folder) / 'candidate'
            report = graphic.prepare(source, out)
            previous = graphic.read(source / 'receipt.json')
            for name, expected in previous['files'].items():
                self.assertEqual(graphic.digest(out / name), expected)
            materials = graphic.read(out / 'materials.json')
            self.assertEqual(len(materials), 2)
            overrides = graphic.read(out / 'material-overrides.json')['overrides'][:2]
            for row in materials + overrides:
                self.assertEqual(row['vectors']['PavingGraphic'], [1200, 1, 1, .19])
                self.assertEqual(row['textures']['PanelGraphic'], graphic.PACKAGE + '.T_PWR_PavingGraphic')
            self.assertFalse(report['graphic']['source_modified'])
            self.assertFalse(report['graphic']['source_seamless'])
            with self.assertRaises(FileExistsError):graphic.prepare(source, out)


if __name__ == '__main__':unittest.main()
