import copy
import json
from pathlib import Path
import tempfile
import unittest

import numpy as np
import final_layout as layout
from heightfield import sha256, write_heightfield


class FinalLayoutTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.geometry={"schema":"pwr-terrain-geometry-v1","coordinates":"authoring_metres_z_up","sites":[]}
        positions={"red_home":[-590,-80,160],"blue_home":[600,-80,160],"warmup":[-568,-130,160],
                   "citadel_plateau":[0,690,160],"capture_a":[-232,-156,160],"capture_b":[0,510,160],"capture_c":[240,-170,160]}
        for name,position in positions.items():
            self.geometry["sites"].append({"id":name,"position_m":position,"radius_m":20})
        path=self.root/"terrain.geometry.json";path.write_text(json.dumps(self.geometry))
        heights=np.full((17,17),160,dtype=np.float32);heights[-1,-1]=400
        self.master=write_heightfield(self.root/"final-master.json",heights,[-1000,-1000],[125,125],
            geometry=path.name,geometry_sha256=sha256(path))
        self.policy=json.loads(layout.POLICY.read_text())

    def test_frozen_flight_survives_lower_hills_and_rejects_higher_obstacles(self):
        result=layout.derive(self.master,self.geometry,self.policy)
        self.assertEqual(result["flights_m"]["red"]["start"],[-850,-180,550])
        self.assertEqual(result["scenario_bounds_m"]["max"],[1000,1000,650])
        self.assertEqual(result["provenance"]["minimum_flight_clearance_m"],150)
        self.assertGreaterEqual(result["descent_timeout_seconds"],(550+20)/6+15)
        self.master.heights_m[-1,-1]=300
        lower=layout.derive(self.master,self.geometry,self.policy)
        self.assertEqual(lower["flights_m"],result["flights_m"])
        self.assertEqual(lower["scenario_bounds_m"],result["scenario_bounds_m"])
        self.master.heights_m[-1,-1]=-10
        low=layout.derive(self.master,self.geometry,self.policy)
        self.assertEqual(low["scenario_bounds_m"],result["scenario_bounds_m"])
        self.master.heights_m[-1,-1]=-18
        with self.assertRaisesRegex(ValueError,"membership floor"):
            layout.derive(self.master,self.geometry,self.policy)
        self.master.heights_m[-1,-1]=450
        with self.assertRaisesRegex(ValueError,"envelope exceeds 400m"):
            layout.derive(self.master,self.geometry,self.policy)

    def test_sites_and_apron_origins_derive_from_finalized_geometry(self):
        result=layout.derive(self.master,self.geometry,self.policy)
        self.assertEqual(result["homes_m"]["red"],[-590,-130,160.35])
        self.assertEqual(result["warmup_m"],[-568,-130,160.35])
        self.assertEqual(result["captures_m"][1],[0,510,160])
        self.assertEqual(result["spawns_m"]["red"][0],[-608,-130,161.15])
        self.assertEqual(len(result["spawns_m"]["red"]),8)
        changed=copy.deepcopy(self.geometry);changed["sites"][0]["position_m"][0]+=15
        moved=layout.derive(self.master,changed,self.policy)
        self.assertEqual(moved["homes_m"]["red"][0],result["homes_m"]["red"][0]+15)
        self.assertEqual(moved["spawns_m"]["red"][0][0],result["spawns_m"]["red"][0][0]+15)

    def test_floating_or_buried_supports_missing_sites_and_unsafe_routes_fail(self):
        for mutate in (lambda g:g["sites"][0]["position_m"].__setitem__(2,150),
                       lambda g:g["sites"][0]["position_m"].__setitem__(2,170),
                       lambda g:g["sites"].pop()):
            bad=copy.deepcopy(self.geometry);mutate(bad)
            with self.assertRaises(ValueError):layout.derive(self.master,bad,self.policy)
        for key,value in (("insertion_seconds",20),("flight_clearance_m",20),("route_end_inset_m",25)):
            bad=dict(self.policy);bad[key]=value
            with self.assertRaises(ValueError):layout.derive(self.master,self.geometry,bad)

    def test_changed_geometry_cannot_be_combined_with_old_master(self):
        accepted=layout.load_and_derive(self.master.path)
        self.assertEqual(accepted["protocol"],20569)
        path=self.root/"terrain.geometry.json"
        path.write_text(path.read_text()+" ")
        with self.assertRaisesRegex(ValueError,"geometry hash"):
            layout.load_and_derive(self.master.path)


if __name__=="__main__":unittest.main()
