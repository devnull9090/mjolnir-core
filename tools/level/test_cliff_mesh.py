import unittest

from cliff_mesh import texture_page


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
