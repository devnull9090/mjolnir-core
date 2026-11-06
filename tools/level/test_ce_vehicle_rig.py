#!/usr/bin/env python3
"""Tests for ce_vehicle_rig.py's edit rules. Run with python -m unittest."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ce_vehicle_rig as rig  # noqa: E402


class EmptyRegions(unittest.TestCase):
    def test_every_filled_list_is_emptied(self):
        rows = {"hull": {"default": [11, 0]}, "turret": {"default": [1, 2], "damaged": [0, 1]}}
        self.assertEqual(rig.empty_regions(rows), [
            "0|RuntimeRegions{hull}.Permutations{default}.StaticMeshes|@len=0",
            "0|RuntimeRegions{turret}.Permutations{default}.StaticMeshes|@len=0",
            "0|RuntimeRegions{turret}.Permutations{default}.SkeletalMeshes|@len=0",
            "0|RuntimeRegions{turret}.Permutations{damaged}.SkeletalMeshes|@len=0",
        ])

    def test_an_empty_region_needs_no_edit(self):
        self.assertEqual(rig.empty_regions({"antenna_marker": {"default": [0, 0]}}), [])


if __name__ == "__main__":
    unittest.main()
