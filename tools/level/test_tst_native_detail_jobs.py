"""The optional TST detail mesh must not renumber existing water decor."""
import unittest

from build_terrain_meshes import append_native_detail_jobs, cast_shadow_for_job


class NativeDetailJobs(unittest.TestCase):
    def test_default_order_is_unchanged(self):
        jobs = [['terrain', 'donor', '/Game/Terrain'], ['sky', 'donor', '/Game/Sky']]
        water = [['water', 'donor', '/Game/Water']]
        self.assertEqual(append_native_detail_jobs(jobs, water, []), jobs + water)

    def test_detail_is_appended_after_existing_water_and_machines(self):
        jobs = [[name, 'donor', '/Game/' + name] for name in ('Terrain', 'Translucent', 'Sky')]
        water = [['water.gltf', 'cube', '/Game/Water']]
        details = ['detail.gltf=cylinder=/Game/FacilityDetail']
        result = append_native_detail_jobs(jobs, water, details)
        self.assertEqual(result[3], water[0])  # TST's existing _terrain_3
        self.assertEqual(result[4], ['detail.gltf', 'cylinder', '/Game/FacilityDetail'])
        self.assertTrue(cast_shadow_for_job('/Game/FacilityDetail', details))
        for existing in jobs + water:
            self.assertFalse(cast_shadow_for_job(existing[2], details))
        self.assertFalse(cast_shadow_for_job('/Game/Terrain', []))

    def test_invalid_job_is_rejected(self):
        for value in ('', 'mesh=donor', 'mesh=donor=/Outside/Map', 'mesh==/Game/Map'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                append_native_detail_jobs([], [], [value])
        with self.assertRaisesRegex(ValueError, 'duplicates'):
            append_native_detail_jobs([['base', 'donor', '/Game/Map']], [], ['mesh=donor=/Game/Map'])


if __name__ == '__main__':
    unittest.main()
