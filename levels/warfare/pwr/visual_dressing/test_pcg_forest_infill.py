import unittest
import numpy as np
from pcg_forest_infill import polygon_clearance, spaced_candidates, density_for_target


class ForestClearanceTests(unittest.TestCase):
    def test_irregular_paving_hole_is_not_treated_as_solid(self):
        outer = [[0, 0], [10, 0], [10, 10], [0, 10], [0, 0]]
        hole = [[4, 4], [6, 4], [6, 6], [4, 6], [4, 4]]
        distances = polygon_clearance(np.array([[2, 2], [5, 5], [12, 5], [13, 14]]), [outer, hole])
        np.testing.assert_allclose(distances, [0, 1, 2, 5])

    def test_candidate_gap_uses_all_adjacent_spatial_buckets(self):
        xy = np.array([[6.9, 0], [7.1, 0], [14, 0], [21.1, 0], [-.1, 0]])
        allowed = np.ones(5, bool)
        selected = spaced_candidates(xy, allowed, np.array([.5, .9, .7, .4, .1]), 7)
        self.assertEqual(np.flatnonzero(selected).tolist(), [1, 3, 4])
        selected_xy = xy[selected]
        pair_distance = np.linalg.norm(selected_xy[:, None]-selected_xy[None, :], axis=-1)
        np.fill_diagonal(pair_distance, np.inf)
        self.assertGreaterEqual(pair_distance.min(), 7)

    def test_probability_fit_preserves_exclusions_and_clump_order(self):
        weights = np.array([.01, .1, .3, .5, .9, 1.])
        allowed = np.array([True, True, False, True, True, True])
        density = density_for_target(weights, allowed, 3)
        self.assertEqual(density[2], 0)
        self.assertAlmostEqual(density.sum(), 3)
        self.assertLess(density[0], density[1])
        self.assertLess(density[1], density[3])
        self.assertTrue(np.all(density <= 1))

    def test_infeasible_target_fails_without_relaxing_clearance(self):
        with self.assertRaisesRegex(ValueError, "Cannot fit"):
            density_for_target(np.ones(10), np.ones(10, bool), 10)


if __name__ == "__main__":
    unittest.main()
