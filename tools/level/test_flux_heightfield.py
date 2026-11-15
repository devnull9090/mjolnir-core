import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from flux_heightfield import build_capture_bed, provenance, sha256, state_matches, verify_state_files
from collect_flux_bake import collect
import upgrade_ce_map as upgrade


class FluxHeightfieldTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.samples=np.array([[2,4,9],[3,17,12],[5,6,8]],dtype=np.float32)
        np.save(self.root/"height.npy",self.samples)
        manifest={"schema":"pwr-heightfield-v1","coordinates":"authoring_metres_z_up",
            "origin_m":[-2,-2],"spacing_m":[2,2],"dimensions":[3,3],"row_order":"+y",
            "surface_interpolation":"triangle_nw_se","height":{"path":"height.npy","encoding":"float32_npy",
            "offset_m":0,"scale_m":1,"sha256":sha256(self.root/"height.npy")}}
        self.manifest=self.root/"master.json";self.manifest.write_text(json.dumps(manifest))
        self.water=self.root/"water.json";self.water.write_text('{"lake":20}')
        self.domain={"centre":[0,0,2000],"res":[4,4],"cell":100,"height":4000}
        self.bed=self.root/"flux_bed.json"
        build_capture_bed(self.manifest,[self.domain],self.bed)

    def spec(self):
        return {"domain":self.domain,"origin":[0,0,0],"provenance":provenance(
            self.manifest,self.water,self.bed,self.domain,[])}

    def state(self,spec):
        return {"centre":self.domain["centre"],"res":self.domain["res"],"cell":100,"height_cm":4000,
                "capture":0,"origin":[0,0,0],"provenance":spec["provenance"],
                "height":"flux_state/main/height.exr","velocity":"flux_state/main/velocity.exr","ground":"flux_state/main/ground.exr"}

    def exrs(self,state):
        for key in ("height","velocity","ground"):
            path=self.root/state[key];path.parent.mkdir(parents=True,exist_ok=True)
            path.write_bytes(struct.pack("<II",20000630,2)+b"dataWindow\0box2i\0"+
                             struct.pack("<I4i",16,0,0,3,3)+b"\0payload")

    def test_original_vertices_and_diagonal_are_preserved(self):
        bed=json.loads(self.bed.read_text())
        vertices=np.array(bed["positions"])
        np.testing.assert_array_equal(vertices[:,2]/100,self.samples.ravel())
        np.testing.assert_array_equal(vertices[:3,:2],[[-200,200],[0,200],[200,200]])
        tris=np.array(bed["indices"]).reshape(-1,3)
        np.testing.assert_array_equal(tris[:4],[[0,3,1],[4,1,3],[0,1,3],[4,3,1]])
        self.assertEqual(len(tris),16)

    def test_rejects_uncovered_capture_and_non_runtime_surface(self):
        with self.assertRaisesRegex(ValueError,"exceeds"):
            build_capture_bed(self.manifest,[dict(self.domain,centre=[1000,0,2000])],self.bed)
        data=json.loads(self.manifest.read_text());data["surface_interpolation"]="bilinear"
        self.manifest.write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError,"triangle_nw_se"):
            build_capture_bed(self.manifest,[self.domain],self.bed)

    def test_stale_terrain_water_settings_and_modified_bed(self):
        spec=self.spec();state=self.state(spec);self.assertTrue(state_matches(state,spec))
        self.water.write_text('{"lake":21}')
        self.assertFalse(state_matches(state,self.spec()))
        changed=dict(spec,provenance=provenance(self.manifest,self.water,self.bed,self.domain,[{"volume":2}]))
        self.assertFalse(state_matches(state,changed))
        self.bed.write_text(self.bed.read_text()+" ")
        with self.assertRaisesRegex(ValueError,"stale or modified"):self.spec()

    def test_validates_and_seals_real_exr_header_dimensions(self):
        state=self.state(self.spec());self.exrs(state)
        verify_state_files(self.root,state)
        self.assertEqual(state["height_sha256"],sha256(self.root/state["height"]))
        path=self.root/state["height"];path.write_bytes(path.read_bytes()+b"tampered")
        with self.assertRaisesRegex(ValueError,"changed"):verify_state_files(self.root,state)
        state=self.state(self.spec());self.exrs(state);state["res"]=[8,4]
        with self.assertRaisesRegex(ValueError,"dimensions"):verify_state_files(self.root,state)

    def test_assembly_requires_bake_and_accepts_only_matching_provenance(self):
        m={"flux":{"heightfield":str(self.manifest),"water_geometry":str(self.water),
            "domains":[{"id":"main","domain":self.domain}],"playback":"baked"}}
        level={"canvas":{"origin":[0,0,0]},"decor":[]};paths={"work":str(self.root)}
        with patch.object(upgrade,"UE4SS",str(self.root/"installed")),patch.object(upgrade,"generated_mesh",return_value="/Game/Bed.Bed"):
            with self.assertRaisesRegex(ValueError,"matching Flux bake missing"):
                upgrade.terrain_flux_spec("PWR",m,paths,level)
            m["flux"]["playback"]="simulate"
            result=upgrade.terrain_flux_spec("PWR",m,paths,level)
            state=self.state(result["domains"][0]);self.exrs(state)
            (self.root/"flux_state/main/state.json").write_text(json.dumps(state))
            m["flux"]["playback"]="baked"
            shipped={"decor":[]}
            result=upgrade.terrain_flux_spec("PWR",m,paths,shipped)
            self.assertIn("height_sha256",result["domains"][0]["state"])
            self.assertEqual(shipped["decor"],[],"Baked surfaces must not load the capture bed")
            before=result["domains"][0]["provenance"]
            m["flux"]["ocean_wave"]={"height_cm":18,"length_cm":1800,"choppiness":0,"offset_cm":0,"water_height_cm":5500}
            result=upgrade.terrain_flux_spec("PWR",m,paths,{"decor":[]})
            self.assertEqual(result["domains"][0]["ocean_wave"],m["flux"]["ocean_wave"])
            self.assertEqual(result["domains"][0]["provenance"],before,"Presentation must not invalidate fluid simulation")
            self.water.write_text('{"lake":22}')
            with self.assertRaisesRegex(ValueError,"matching Flux bake missing"):
                upgrade.terrain_flux_spec("PWR",m,paths,{"decor":[]})

    def test_collection_seals_three_textures_without_modifying_export(self):
        spec=dict(self.spec(),id="main",playback="simulate")
        state=self.state(spec);self.exrs(state)
        original=json.dumps(state);(self.root/"flux_state/main/state.json").write_text(original)
        source=self.root/"spec.json";source.write_text(json.dumps({"domains":[spec]}))
        output=self.root/"immutable"
        collect(source,self.root,output)
        saved=json.loads((output/"flux.spec.json").read_text())["domains"][0]
        self.assertEqual(saved["playback"],"baked")
        self.assertIn("ground_sha256",saved["state"])
        self.assertEqual((self.root/"flux_state/main/state.json").read_text(),original)
        with self.assertRaisesRegex(ValueError,"new output folder"):
            collect(source,self.root,output)


if __name__=="__main__":unittest.main()
