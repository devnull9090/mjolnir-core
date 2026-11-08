#!/usr/bin/env python3
import copy
import json
import os
import tempfile
import unittest

import add_flux_state as fs

DOMAIN = {"centre": [864, -2546, -3232], "res": [352, 1216], "cell": 25.0, "height": 5000.0}
STATE = {"height": "flux_state/height.exr", "velocity": "flux_state/velocity.exr",
         "centre": [864, -2546, -3232], "res": [352, 1216], "cell": 25.0, "height_cm": 5000.0, "capture": -6982.0}


def level():
    return {"blam": {"objects": [], "single_bsp": 0},
            "flux": {"domain": copy.deepcopy(DOMAIN), "hide": ["__ce_water"],
                     "sources": [{"pos": [0, 0, 0], "mode": 1, "prime": True},
                                 {"pos": [1, 1, 1], "mode": 0, "volume": 2}]}}


class Fits(unittest.TestCase):
    def test_the_bake_for_this_domain_fits(self):
        self.assertTrue(fs.fits(STATE, DOMAIN))
        near = dict(STATE, centre=[864.4, -2546.6, -3231.2])
        self.assertTrue(fs.fits(near, DOMAIN))

    def test_a_bake_for_another_domain_does_not(self):
        for change in ({"centre": [900, -2546, -3232]}, {"res": [352, 1200]}, {"cell": 20},
                       {"height_cm": 2000}):
            self.assertFalse(fs.fits(dict(STATE, **change), DOMAIN), change)

    def test_a_malformed_state_does_not_fit(self):
        self.assertFalse(fs.fits({}, DOMAIN))
        self.assertFalse(fs.fits(dict(STATE, centre=[1, 2]), DOMAIN))


class WithState(unittest.TestCase):
    def test_only_flux_state_is_added(self):
        old = level()
        before = copy.deepcopy(old)
        new = fs.with_state(old, STATE)
        self.assertEqual(old, before)
        self.assertEqual(new["flux"]["state"], STATE)
        self.assertEqual(fs.level_changes(old, new), [])

    def test_other_changes_are_caught(self):
        old = level()
        new = fs.with_state(old, STATE)
        new["flux"]["sources"].pop()
        self.assertTrue(fs.level_changes(old, new))

    def test_a_level_without_a_river_or_a_mismatched_bake_is_refused(self):
        with self.assertRaises(ValueError):
            fs.with_state({"flux": {"coast": {}}}, STATE)
        with self.assertRaises(ValueError):
            fs.with_state(level(), dict(STATE, res=[96, 288]))


class ReadState(unittest.TestCase):
    def write(self, folder, files):
        for name, data in files.items():
            with open(os.path.join(folder, name), "wb") as stream:
                stream.write(data)

    def good(self):
        return {"state.json": json.dumps(STATE).encode(), "height.exr": fs.EXR_MAGIC + b"h",
                "velocity.exr": fs.EXR_MAGIC + b"v"}

    def test_a_complete_bake_reads_and_strays_are_ignored(self):
        with tempfile.TemporaryDirectory() as d:
            self.write(d, dict(self.good(), **{"height_wet": b"x", "velocity_depth_foam.exr": b"y"}))
            self.assertEqual(fs.read_state(d), STATE)

    def test_missing_empty_or_wrong_files_are_refused(self):
        bad = [{"velocity.exr": None}, {"height.exr": b""}, {"height.exr": b"\x89PNG"},
               {"state.json": json.dumps(dict(STATE, height="height.exr")).encode()},
               {"state.json": json.dumps(dict(STATE, extra=1)).encode()}]
        for change in bad:
            with tempfile.TemporaryDirectory() as d:
                files = {k: v for k, v in dict(self.good(), **change).items() if v is not None}
                self.write(d, files)
                with self.assertRaises(ValueError, msg=change):
                    fs.read_state(d)


if __name__ == "__main__":
    unittest.main()
