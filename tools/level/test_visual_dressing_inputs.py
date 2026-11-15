"""Replacement terrain must not silently reuse or overwrite the v4 pass."""
import argparse
import importlib
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/"levels/warfare/pwr/visual_dressing"))
import build_candidate


class DressingInputTests(unittest.TestCase):
    def setUp(self):self.module=importlib.reload(build_candidate)

    def args(self,*argv):
        p=argparse.ArgumentParser();p.add_argument("command")
        self.module.add_source_arguments(p)
        return p.parse_args(argv)

    def test_new_master_requires_independent_output_and_inputs(self):
        for command,extra,message in (("apron",[],"isolated"),("prepare",["--out","out/new"],"trees"),
                                       ("nonsnow",["--out","out/new"],"rocks"),("audit",["--out","out/new"],"grass")):
            with self.subTest(command=command),patch.object(self.module,"field"):
                with self.assertRaisesRegex(ValueError,message):
                    self.module.configure(self.args(command,"--master","new-master.json","--expected-master","a"*64,*extra))

    def test_explicit_paths_reuse_verified_asset_cache_without_changing_default_output(self):
        old_assets=self.module.ASSET_DIR
        with patch.object(self.module,"field"):
            self.module.configure(self.args("prepare","--master","new-master.json","--expected-master","b"*64,
                "--out","out/new","--trees","out/new-pcg/trees.selected.json","--rocks","out/new-pcg/rocks/authored_decor.json",
                "--grass","out/new-pcg/grass/foliage.json"))
        self.assertEqual(self.module.EXPECTED_MASTER,"b"*64)
        self.assertEqual(self.module.ASSET_DIR,old_assets)
        self.assertEqual(self.module.OUT,Path("out/new").resolve())
        self.assertEqual(self.module.SOURCE_TREES,Path("out/new-pcg/trees.selected.json").resolve())
        self.assertEqual(self.module.SOURCE_GRASS,Path("out/new-pcg/grass/foliage.json").resolve())

    def test_new_master_cannot_overwrite_original_dressing_outputs(self):
        with patch.object(self.module,"field"):
            with self.assertRaisesRegex(ValueError,"overwrite visual-v4"):
                self.module.configure(self.args("apron","--master","new-master.json","--expected-master","a"*64,
                    "--out",str(self.module.REPO/"out/pwr/visual-v4")))

    def test_new_apron_rings_limit_radial_facets_and_preserve_stitch_ratios(self):
        rings=self.module.apron_rings(100)
        self.assertEqual(rings[0],(1000,1));self.assertEqual(rings[-1],(4000,16))
        self.assertTrue(all(b[0]-a[0]<=100 for a,b in zip(rings[:-1],rings[1:])))
        self.assertTrue(all(b[1]%a[1]==0 for a,b in zip(rings[:-1],rings[1:])))
        self.assertEqual(len(self.module.apron_rings()),12)


if __name__=="__main__":unittest.main()
