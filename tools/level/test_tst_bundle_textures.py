"""Portable TST texture-bundle behavior using temporary files only."""
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'levels/test/tst'))
from bundle_textures import copy_owned_image


class BundleTexturesTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.source = root / 'source'
        self.textures = self.source / 'art/textures'
        self.textures.mkdir(parents=True)
        self.output = root / 'new-bundle'
        self.output.mkdir()
        self.image = self.textures / 'metal.png'
        self.image.write_bytes(b'owned image fixture')

    def test_copy_is_relative_and_repeated_reference_does_not_overwrite(self):
        self.assertEqual(copy_owned_image(self.image, self.source, self.output), '//art/textures/metal.png')
        target = self.output / 'art/textures/metal.png'
        self.assertEqual(target.read_bytes(), self.image.read_bytes())
        self.assertEqual(copy_owned_image(self.image, self.source, self.output), '//art/textures/metal.png')

    def test_different_existing_texture_is_never_overwritten(self):
        target = self.output / 'art/textures/metal.png'
        target.parent.mkdir(parents=True)
        target.write_bytes(b'user file')
        with self.assertRaises(FileExistsError):
            copy_owned_image(self.image, self.source, self.output)
        self.assertEqual(target.read_bytes(), b'user file')

    def test_external_image_is_rejected(self):
        outside = self.source / 'secret.png'
        outside.write_bytes(b'not an owned texture')
        with self.assertRaisesRegex(ValueError, 'not inside'):
            copy_owned_image(outside, self.source, self.output)
        self.assertFalse((self.output / 'secret.png').exists())


if __name__ == '__main__':
    unittest.main()
