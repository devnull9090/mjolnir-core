import math
import unittest

import numpy as np

from cliff_mesh import smooth_normals, texture_page


def hinge(fold_deg):
    """Two triangles sharing the edge x=0, folded by fold_deg along it."""
    t = math.radians(fold_deg)
    a = [[0, 0, 0], [0, 100, 0], [-100, 0, 0]]
    b = [[0, 0, 0], [100 * math.cos(t), 0, -100 * math.sin(t)], [0, 100, 0]]
    return np.array(a + b, dtype=float)


class SmoothNormalsTest(unittest.TestCase):
    def test_gentle_fold_blends_at_the_shared_edge(self):
        n = smooth_normals(hinge(20), 45, np.tile([0, 0, 1.0], (6, 1)))
        # The shared corner takes both faces: the same normal on each side.
        np.testing.assert_allclose(n[0], n[3], atol=1e-6)
        self.assertGreater(n[0][2], 0.9)

    def test_sharp_crease_stays_hard(self):
        n = smooth_normals(hinge(80), 45, np.tile([0, 0, 1.0], (6, 1)))
        self.assertLess(float(n[0] @ n[3]), 0.5)

    def test_faces_turned_to_the_given_normals(self):
        n = smooth_normals(hinge(0), 45, np.tile([0, 0, -1.0], (6, 1)))
        self.assertTrue((n[:, 2] < 0).all())


def path(leaf):
    return f"/Game/MJOLNIR/Maps/X/Textures/{leaf}.{leaf}"


class TexturePageTest(unittest.TestCase):
    def test_pages_by_suffix(self):
        self.assertEqual(texture_page(path("T_levels_test_bloodgulch_bloodgulch_lightmap")), 0)
        self.assertEqual(texture_page(path("T_levels_test_bloodgulch_bloodgulch_lightmap_n7")), 7)

    def test_halo2_maps_run_past_a_hundred_pages(self):
        self.assertEqual(texture_page(path("T_scenarios_multi_containment_lightmap_bitmaps_n100")), 100)

    def test_protected_page_zero_carries_its_bitmap_number(self):
        self.assertEqual(texture_page(path("T_protected_bitm_n2943")), 0)
        self.assertEqual(texture_page(path("T_protected_bitm_2943_n2")), 2)


if __name__ == "__main__":
    unittest.main()
