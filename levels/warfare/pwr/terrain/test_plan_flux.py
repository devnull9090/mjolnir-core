import json
from pathlib import Path
import tempfile
import unittest

import numpy as np

from plan_flux import capture_domain, plan
from heightfield import load_heightfield, sha256


class FluxPlanTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        heights=np.full((11,11),48,dtype=np.float32)
        heights[7:,0:4]=180
        np.save(self.root/"heights.npy",heights)
        self.master=self.root/"master.json"
        self.master.write_text(json.dumps({"schema":"pwr-heightfield-v1","coordinates":"authoring_metres_z_up",
            "origin_m":[-1000,-1000],"spacing_m":[200,200],"dimensions":[11,11],"row_order":"+y",
            "surface_interpolation":"triangle_nw_se","height":{"path":"heights.npy","encoding":"float32_npy",
                "offset_m":0,"scale_m":1,"sha256":sha256(self.root/"heights.npy")}}))

    def test_capture_reference_and_plane_enclose_original_vertices(self):
        domain,report=capture_domain(load_heightfield(self.master),[-732,0,268,1000],1024)
        self.assertGreaterEqual(report["capture_plane_m"]-report["bed_max_m"],5)
        self.assertGreaterEqual(report["bed_min_m"]-report["capture_offset_m"],5)
        self.assertLessEqual(domain["height"],32000)

    def test_shared_head_lake_holds_and_exact_provenance(self):
        geometry=self.root/"water.json"
        geometry.write_text(json.dumps({"watercourses":[{"id":"central_river",
            "surface_centreline_m":[[-100,900,150],[-20,20,92.4],[0,-20,92],[200,-600,55]]}],
            "lakes":[{"id":"lake","water_z_m":55,"polygon_m":[[0,-900],[600,-900],[600,-500],[0,-500]],
                      "islands":[{"polygon_m":[[200,-800],[300,-800],[300,-700],[200,-700]]}]}]}))
        plan(self.master,geometry,self.root/"out",128)
        spec=json.loads((self.root/"out/flux.spec.json").read_text())
        heads=[[s for s in e["sources"] if s["role"]=="shared_seam_head"][0] for e in spec["domains"]]
        self.assertEqual(heads[0],heads[1]);self.assertAlmostEqual(heads[0]["pos"][2],9220)
        holds=[s for s in spec["domains"][1]["sources"] if s["role"]=="lake_level_hold"]
        self.assertGreater(len(holds),0);self.assertTrue(all(s["pos"][2]==5500 and not s["prime"] for s in holds))
        self.assertTrue(all(e["provenance"]["terrain_manifest_sha256"]==sha256(self.master) for e in spec["domains"]))
        release=json.loads((self.root/"out/flux.config.fragment.json").read_text())
        self.assertTrue(all(e["playback"]=="baked" for e in release["domains"]))

    def test_northern_lake_has_its_own_inlet_without_changing_southern_controls(self):
        geometry = self.root / "water.json"
        data = {
            "watercourses": [{"id": "central_river", "surface_centreline_m":
                              [[-30, 310, 100], [-20, 20, 92.4], [0, -20, 92], [200, -600, 55]]}],
            "lakes": [{"id": "southeast_lake", "water_z_m": 55,
                       "polygon_m": [[0,-900],[600,-900],[600,-500],[0,-500]]}],
        }
        geometry.write_text(json.dumps(data))
        plan(self.master, geometry, self.root / "old", 128)
        old = json.loads((self.root / "old/flux.spec.json").read_text())["domains"]
        data["lakes"].append({"id": "north_headwater_lake", "water_z_m": 100,
                              "polygon_m": [[-100,310],[100,310],[100,420],[-100,420]]})
        data["watercourses"].append({"id": "headwater_spring",
                                     "surface_centreline_m": [[0,440,103], [0,418,100]]})
        geometry.write_text(json.dumps(data))
        plan(self.master, geometry, self.root / "new", 128)
        upper, lower = json.loads((self.root / "new/flux.spec.json").read_text())["domains"]
        self.assertEqual(lower["sources"], old[1]["sources"])
        holds = [s for s in upper["sources"] if s["role"] == "headwater_level_hold"]
        self.assertTrue(holds)
        self.assertTrue(all(s["pos"][2] == 10000 and not s["prime"] for s in holds))
        springs = [s for s in upper["sources"] if s["role"] == "spring_inlet"]
        self.assertEqual(len(springs), 1)
        self.assertFalse(springs[0]["prime"])
        self.assertFalse(any(s["role"] == "inlet_flow" for s in upper["sources"]))


if __name__=="__main__":unittest.main()
