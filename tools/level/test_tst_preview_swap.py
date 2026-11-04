"""Synthetic round-trip and failure tests; never touches an installed game."""
import datetime as dt
from contextlib import nullcontext
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import tst_preview_swap as swap


class PreviewSwapTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.game = self.root / 'game'
        self.paks = self.game / 'Meteorite/Content/Paks'
        self.data = self.game / 'Meteorite/Binaries/Win64/ue4ss/MJOLNIRMaps/TST'
        self.paks.mkdir(parents=True)
        self.data.mkdir(parents=True)
        self.stage = self.root / 'stage'
        self.stage.mkdir()
        self.backup = self.root / 'backup'
        self.spec = self.root / 'conversion/materials.spec.json'
        self.spec.parent.mkdir()
        self.state = self.root / 'launcher/hub_state.json'
        self.state.parent.mkdir()
        self.surfaces = self.root / 'surfaces.json'
        roles = {f'role{i}': {'shader': f'shader{i}', 'tag': f'levels/test/tst/shaders/shader{i}'} for i in range(12)}
        self.write_json(self.surfaces, {'surfaces': roles})
        self.write_json(self.spec, {'chunk': 968, 'root': '/Game/MJOLNIR/Maps/TST', 'authored_surfaces': roles})
        self.start = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=1)).isoformat()
        self.originals = {}
        hashes = {}
        for index, stem in enumerate(swap.CONTAINERS):
            base = self.paks / f'pakchunk{968 + index}-MJOLNIRHUB-{swap.SLUG}-{index}_P'
            self.write(base.with_suffix('.pak'), f'unchanged pak stub {index}'.encode())
            for ext in ('utoc', 'ucas'):
                dst = base.with_suffix('.' + ext)
                self.write(dst, f'old hub {stem} {ext}'.encode())
                self.write(self.stage / (stem + '.' + ext), f'new local {stem} {ext}'.encode())
                hashes[stem + '.' + ext] = swap.digest(dst)
                self.originals[dst.resolve()] = dst.read_bytes()
        for filename, value in [('level.json', b'old level'), ('registration.json', b'old registration'),
                                ('foliage.bin', b'old foliage')]:
            dst = self.data / filename
            self.write(dst, value)
            self.originals[dst.resolve()] = value
            hashes['map/' + filename] = swap.digest(dst)
        self.write_json(self.state, {'installed': [{'slug': swap.SLUG, 'map_code': 'TST',
            'release_id': 'release-1', 'version': 'beta.3', 'sha256': 'archive-hash',
            'containers': list(swap.CONTAINERS), 'container_hashes': hashes}]})
        self.state_bytes = self.state.read_bytes()
        water = {'height': 'flux_state/height.exr', 'velocity': 'flux_state/velocity.exr',
                 'centre': [1, 2, 3], 'res': [8, 8], 'cell': 20, 'height_cm': 2000}
        self.write_json(self.stage / 'tst.level.json', {'modes': ['slayer', 'team_slayer', 'ctf'],
                        'foliage': {'file': 'foliage.bin'}, 'flux': {'state': water}})
        self.write_json(self.stage / 'TST.registration.json', {'code': 'TST',
                        'world': '/Game/Levels/Halo1/Solo/TST/TST.TST'})
        self.write(self.stage / 'foliage.bin', b'new foliage')
        self.write_json(self.stage / 'flux_state/state.json', water)
        self.write(self.stage / 'flux_state/height.exr', b'height')
        self.write(self.stage / 'flux_state/velocity.exr', b'velocity')
        self.closed = mock.patch.object(swap, 'require_game_closed')
        self.closed.start()
        self.addCleanup(self.closed.stop)

    @staticmethod
    def write(path, contents):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(contents)

    def write_json(self, path, value):
        self.write(path, json.dumps(value).encode())

    def install(self):
        return swap.install(self.game, self.state, self.stage, self.spec,
                            self.backup, self.start, self.surfaces)

    def assert_originals(self):
        for path, value in self.originals.items():
            self.assertEqual(path.read_bytes(), value, str(path))
        self.assertEqual(self.state.read_bytes(), self.state_bytes)

    def test_round_trip_restores_exact_hub_files_and_removes_only_created_water_files(self):
        original_stubs = {p: p.read_bytes() for p in self.paks.glob('*.pak')}
        manifest_path = self.install()
        manifest = swap.read_json(manifest_path)
        self.assertEqual(manifest['status'], 'installed')
        self.assertEqual(len(manifest['files']), 16)
        self.assertEqual((self.data / 'foliage.bin').read_bytes(), b'new foliage')
        self.assertEqual((self.data / 'flux_state/height.exr').read_bytes(), b'height')
        for entry in manifest['files']:
            self.assertEqual(swap.digest(entry['destination']), entry['staged_sha256'])
        swap.restore(self.backup, self.state, self.game)
        self.assert_originals()
        self.assertFalse((self.data / 'flux_state/height.exr').exists())
        self.assertEqual(swap.read_json(manifest_path)['status'], 'restored')
        self.assertEqual({p: p.read_bytes() for p in self.paks.glob('*.pak')}, original_stubs)

    def test_corrupt_backup_refuses_restore_before_changing_any_test_file(self):
        manifest = swap.read_json(self.install())
        (self.backup / manifest['files'][0]['backup']).write_bytes(b'corrupt backup')
        before = {entry['destination']: Path(entry['destination']).read_bytes() for entry in manifest['files']}
        with self.assertRaisesRegex(ValueError, 'Backup hash mismatch'):
            swap.restore(self.backup, self.state, self.game)
        self.assertEqual(before, {path: Path(path).read_bytes() for path in before})
        self.assertEqual(swap.read_json(self.backup / swap.MANIFEST)['status'], 'installed')

    def test_modified_test_file_refuses_restore_before_changing_any_file(self):
        manifest = swap.read_json(self.install())
        modified = Path(manifest['files'][2]['destination'])
        modified.write_bytes(b'user changed the file')
        before = {entry['destination']: Path(entry['destination']).read_bytes() for entry in manifest['files']}
        with self.assertRaisesRegex(ValueError, 'Test file changed'):
            swap.restore(self.backup, self.state, self.game)
        self.assertEqual(before, {path: Path(path).read_bytes() for path in before})

    def test_partial_install_failure_rolls_back_all_changed_files(self):
        original_copy = swap.atomic_copy
        calls = 0
        def fail_once(src, dst):
            nonlocal calls
            calls += 1
            if calls == 3:
                raise OSError('synthetic copy failure')
            return original_copy(src, dst)
        with mock.patch.object(swap, 'atomic_copy', side_effect=fail_once):
            with self.assertRaisesRegex(OSError, 'synthetic copy failure'):
                self.install()
        self.assert_originals()
        self.assertEqual(swap.read_json(self.backup / swap.MANIFEST)['status'], 'rolled_back')
        self.assertFalse((self.data / 'flux_state/height.exr').exists())

    def test_mismatched_installed_hub_file_is_refused_without_backup_or_changes(self):
        target = next(iter(self.originals))
        target.write_bytes(b'not the launcher version')
        before = {p: p.read_bytes() for p in self.originals}
        with self.assertRaisesRegex(ValueError, 'differs from launcher hash'):
            self.install()
        self.assertFalse(self.backup.exists())
        self.assertEqual(before, {p: p.read_bytes() for p in before})

    def test_running_game_refuses_install_without_creating_backup(self):
        with mock.patch.object(swap, 'require_game_closed', side_effect=RuntimeError('game running')):
            with self.assertRaisesRegex(RuntimeError, 'game running'):
                self.install()
        self.assertFalse(self.backup.exists())
        self.assert_originals()

    def test_stale_conversion_spec_is_refused(self):
        future = (dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=1)).isoformat()
        with self.assertRaisesRegex(ValueError, 'predates'):
            swap.install(self.game, self.state, self.stage, self.spec, self.backup, future, self.surfaces)
        self.assertFalse(self.backup.exists())
        self.assert_originals()

    def test_same_as_hub_map_is_refused_as_stale(self):
        base = self.paks / f'pakchunk972-MJOLNIRHUB-{swap.SLUG}-4_P.ucas'
        self.write(self.stage / (swap.CONTAINERS[4] + '.ucas'), base.read_bytes())
        with self.assertRaisesRegex(ValueError, 'identical to the installed beta'):
            self.install()
        self.assertFalse(self.backup.exists())
        self.assert_originals()

    def test_empty_real_decals_directory_is_accepted_without_installing_decals(self):
        (self.stage / 'decals').mkdir()
        manifest = swap.read_json(self.install())
        self.assertFalse(any('decals' in entry['name'] for entry in manifest['files']))
        self.assertFalse((self.data / 'decals').exists())
        swap.restore(self.backup, self.state, self.game)
        self.assert_originals()

    def test_nonempty_decals_directory_is_refused_without_writes(self):
        self.write(self.stage / 'decals' / 'detail.bin', b'decal')
        with self.assertRaisesRegex(ValueError, 'does not install staged decals'):
            self.install()
        self.assertFalse(self.backup.exists())
        self.assert_originals()

    def test_decals_subdirectory_is_refused_even_when_empty(self):
        (self.stage / 'decals' / 'nested').mkdir(parents=True)
        with self.assertRaisesRegex(ValueError, 'does not install staged decals'):
            self.install()
        self.assertFalse(self.backup.exists())
        self.assert_originals()

    def test_decals_path_as_a_file_is_refused(self):
        self.write(self.stage / 'decals', b'not a directory')
        with self.assertRaisesRegex(ValueError, 'does not install staged decals'):
            self.install()
        self.assertFalse(self.backup.exists())
        self.assert_originals()

    def test_decals_junction_is_refused_even_when_empty(self):
        decals = self.stage / 'decals'
        decals.mkdir()
        with mock.patch.object(Path, 'is_junction', lambda path: path == decals):
            with self.assertRaisesRegex(ValueError, 'decals directory is a link'):
                self.install()
        self.assertFalse(self.backup.exists())
        self.assert_originals()

    def test_decals_symlink_is_refused_even_when_empty(self):
        target = self.stage / 'empty-target'
        target.mkdir()
        decals = self.stage / 'decals'
        patch = nullcontext()
        try:
            decals.symlink_to(target, target_is_directory=True)
        except (OSError, NotImplementedError):
            # Windows without Developer Mode cannot create a symlink. Still
            # exercise the symlink-specific branch without elevated rights.
            decals.mkdir()
            original = Path.is_symlink
            patch = mock.patch.object(Path, 'is_symlink', lambda path: path == decals or original(path))
        with patch:
            with self.assertRaisesRegex(ValueError, 'decals directory is a link'):
                self.install()
        self.assertFalse(self.backup.exists())
        self.assert_originals()

    def test_dangling_link_inside_decals_is_refused(self):
        decals = self.stage / 'decals'
        decals.mkdir()
        patch = nullcontext()
        try:
            (decals / 'dangling').symlink_to(self.root / 'missing-target')
        except (OSError, NotImplementedError):
            # Simulate the directory entry returned for a dangling link.
            original = Path.iterdir
            patch = mock.patch.object(Path, 'iterdir', lambda path:
                iter([decals / 'dangling']) if path == decals else original(path))
        with patch:
            with self.assertRaisesRegex(ValueError, 'does not install staged decals'):
                self.install()
        self.assertFalse(self.backup.exists())
        self.assert_originals()

    def test_changed_hub_release_refuses_restore(self):
        manifest = swap.read_json(self.install())
        state = swap.read_json(self.state)
        state['installed'][0]['release_id'] = 'new-release'
        self.write_json(self.state, state)
        before = {entry['destination']: Path(entry['destination']).read_bytes() for entry in manifest['files']}
        with self.assertRaisesRegex(ValueError, 'hub release changed'):
            swap.restore(self.backup, self.state, self.game)
        self.assertEqual(before, {path: Path(path).read_bytes() for path in before})

    def test_interrupted_install_can_restore_files_already_back_at_original(self):
        path = self.install()
        manifest = swap.read_json(path)
        manifest['status'] = 'installing'
        swap.write_manifest(self.backup, manifest)
        entry = manifest['files'][0]
        Path(entry['destination']).write_bytes((self.backup / entry['backup']).read_bytes())
        swap.restore(self.backup, self.state, self.game)
        self.assert_originals()
        self.assertFalse((self.data / 'flux_state/height.exr').exists())

    def test_manifest_cannot_restore_outside_approved_paths(self):
        path = self.install()
        manifest = swap.read_json(path)
        outside = self.root / 'outside.txt'
        outside.write_bytes(b'untouched')
        manifest['files'][0]['destination'] = str(outside)
        swap.write_manifest(self.backup, manifest)
        with self.assertRaisesRegex(ValueError, 'Unexpected destination'):
            swap.restore(self.backup, self.state, self.game)
        self.assertEqual(outside.read_bytes(), b'untouched')

    @unittest.skipUnless(os.name == 'nt', 'Windows tasklist process detection')
    def test_tasklist_detects_game_process(self):
        self.closed.stop()
        result = mock.Mock(stdout='"HaloCampaignEvolved.exe","1234","Console","1","42,000 K"\n')
        with mock.patch.object(swap.subprocess, 'run', return_value=result):
            with self.assertRaisesRegex(RuntimeError, 'Close Halo'):
                swap.require_game_closed()
        self.closed.start()


if __name__ == '__main__':
    unittest.main()
