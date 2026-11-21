"""Mutations of the native saved-buffer contract; no editor or renderer required."""
import base64
import copy
import json
from pathlib import Path
import tempfile
import unittest
import struct

from landscape_grass_pilot import (ASSETS, WORLD, FAMILIES, SCHEMA, component_weights,
                                   digest, validate_config, validate_readback, filter_meadow_group, OLD_MEADOW,
                                   ASSETS_V8, CANYON_SOURCE, CANYON_TARGET, CANYON_OBJECT,
                                   CANYON_CONTAINER, MATERIAL_NEVER_COOK, material_cook_inputs,
                                   archive_owned_editor_assets, prepare_material_variant)


class GrassPilotTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder=Path(self.temp.name)
        size=1009
        self.mask=bytearray(size*size)
        self.mask[710*size+600]=255
        self.mask[720*size+660]=127
        (self.folder/"density.r8").write_bytes(self.mask)
        (self.folder/"density.png").write_bytes(b"texture fixture")
        (self.folder/"heights.r16").write_bytes(b"\x34\x80"*(size*size))
        source=self.folder/"input.json"; source.write_text("frozen input")
        self.config={"schema":SCHEMA,"world":WORLD,"source_world":"/Game/Levels/Halo1/Solo/LPW/LPW",
            "asset_folder":ASSETS,"chunk":965,"preserved_groundcover":279132,"serialized_instances":0,
            "grid":{"size":size,"components":16,"sections":1,"quads":63,
                    "location":[-100000.,-100000.,22400.],"scale":[12500/63,12500/63,100.]},
            "section_bases":[[567,693],[630,693]],"cull_cm":[4000,6000],
            "sources":[{"path":str(source),"sha256":digest(source)}],
            "varieties":[{"name":name,"mesh":mesh,"density_per_100m2":density,"scale":scale,
                          "override_materials":[]} for name,mesh,density,scale in FAMILIES]}
        for key,file in (("mask","density.r8"),("texture","density.png"),("heights","heights.r16")):
            self.config[key]={"file":file,"sha256":digest(self.folder/file)}
        grass=ASSETS+"/GT_PWRPilot.GT_PWRPilot"
        self.readback={"schema":"mjolnir-native-grass-readback-v1","world":WORLD,"grass_type":grass,
                       "built":False,"components":[]}
        for y in range(0,1008,63):
            for x in range(0,1008,63):
                weights=component_weights(self.mask,size,63,x,y)
                row={"x":x,"y":y,"quads":63,"material":ASSETS+"/M_PWRPilot.M_PWRPilot",
                     "grass_types":[grass],"num_elements":4096 if any(weights) else 0,
                     "weight_channels":1 if any(weights) else 0}
                if any(weights):
                    row["weights_b64"]=base64.b64encode(weights).decode()
                    row["heights_b64"]=base64.b64encode(b"\x34\x80"*4096).decode()
                self.readback["components"].append(row)

    def check(self):
        return validate_readback(self.config,self.folder,self.readback,require_saved=True)

    def active(self):
        return next(v for v in self.readback["components"] if v["num_elements"] > 0)

    def enable_material(self):
        def pinned(name, contents):
            path=self.folder/name
            path.write_text(contents,encoding="utf-8")
            return {"path":str(path),"sha256":digest(path)}
        self.material_proof={"schema":"pwr-native-grass-material-clone-independent-audit-v1","status":"passed",
            "source":{"identity":CANYON_SOURCE},"clone":{"identity":CANYON_TARGET},
            "added_scalar":{"name":"Max Offset","association":2,"index":-1,"value":10.,
                            "expression_guid":"00000000000000000000000000000000"},
            "source_properties_preserved":True,"native_tail_identical":True,
            "native_parent_and_texture_imports_preserved":True,"existing_guids_preserved":True}
        manifest=[{"source":CANYON_SOURCE,"target":CANYON_TARGET,
                   "scalars":{"Max Offset#-1":{"value":10.,"association":2}},"vectors":{}}]
        self.config["canyon_material"]={"schema":"pwr-canyon-max-offset-v1",
            "source":CANYON_SOURCE,"target":CANYON_TARGET,"container":CANYON_CONTAINER,
            "never_cook":MATERIAL_NEVER_COOK,"manifest":pinned("clone.json",json.dumps(manifest)),
            "proof":pinned("proof.json",json.dumps(self.material_proof)),
            "tool":pinned("tool.exe","fixture tool"),
            "files":[pinned(CANYON_CONTAINER+suffix,"fixture "+suffix) for suffix in (".utoc",".ucas",".pak")]}
        entry=self.config["canyon_material"]
        self.material_proof["input_seals"]=[dict(row) for row in [entry["manifest"],entry["tool"],*entry["files"]]]
        self.rewrite_material_proof()
        self.config["asset_folder"]=ASSETS_V8
        self.config["varieties"][0]["override_materials"]=[CANYON_OBJECT]
        self.readback["grass_type"]=self.readback["grass_type"].replace(ASSETS,ASSETS_V8)
        self.readback["varieties"]=[{"mesh":row["mesh"],"override_materials":row["override_materials"][:]}
                                    for row in self.config["varieties"]]
        for row in self.readback["components"]:
            row["material"]=row["material"].replace(ASSETS,ASSETS_V8)
            row["grass_types"]=[v.replace(ASSETS,ASSETS_V8) for v in row["grass_types"]]

    def rewrite_material_proof(self):
        entry=self.config["canyon_material"]["proof"]
        Path(entry["path"]).write_text(json.dumps(self.material_proof),encoding="utf-8")
        entry["sha256"]=digest(entry["path"])

    def test_fresh_saved_native_weights_pass(self):
        self.assertEqual(self.check(),{"components":256,"nonzero_components":2,
            "nonzero_weight_samples":2,"maximum_weight_byte_error":0,"saved_buffers_verified":True})

    def test_rejects_stale_source(self):
        (self.folder/"input.json").write_text("changed")
        with self.assertRaisesRegex(ValueError,"Stale"): self.check()

    def test_rejects_unbuilt_and_stripped_data(self):
        for value in (-1,0):
            with self.subTest(value=value):
                original=copy.deepcopy(self.active())
                row=self.active(); row["num_elements"]=value
                with self.assertRaises(ValueError): self.check()
                row.update(original)

    def test_rejects_rebuild_disguised_as_saved_verification(self):
        self.readback["built"]=True
        with self.assertRaisesRegex(ValueError,"without generating"): self.check()

    def test_rejects_weights_shifted_by_one_texel(self):
        row=self.active()
        data=base64.b64decode(row["weights_b64"])
        row["weights_b64"]=base64.b64encode(data[-1:]+data[:-1]).decode()
        with self.assertRaisesRegex(ValueError,"weights differ"): self.check()

    def test_rejects_one_byte_leak_into_exclusion(self):
        row=self.active(); data=bytearray(base64.b64decode(row["weights_b64"]))
        data[0]=1
        row["weights_b64"]=base64.b64encode(data).decode()
        with self.assertRaisesRegex(ValueError,"leak"): self.check()

    def test_accepts_one_byte_render_rounding_within_support(self):
        row=self.active(); data=bytearray(base64.b64decode(row["weights_b64"]))
        data[data.index(255)]=254
        row["weights_b64"]=base64.b64encode(data).decode()
        self.assertEqual(self.check()["maximum_weight_byte_error"],1)

    def test_rejects_changed_terrain_height(self):
        row=self.active(); data=bytearray(base64.b64decode(row["heights_b64"]))
        data[0]^=1
        row["heights_b64"]=base64.b64encode(data).decode()
        with self.assertRaisesRegex(ValueError,"height buffer"): self.check()

    def test_rejects_wrong_material_or_grass_type(self):
        for key,value in (("material","/Game/Wrong.Wrong"),("grass_types",[])):
            with self.subTest(key=key):
                row=self.active(); original=row[key]; row[key]=value
                with self.assertRaisesRegex(ValueError,"binding"): self.check()
                row[key]=original

    def test_rejects_missing_or_duplicate_components(self):
        row=self.readback["components"].pop()
        with self.assertRaisesRegex(ValueError,"Missing components"): self.check()
        self.readback["components"].append(self.readback["components"][0])
        with self.assertRaisesRegex(ValueError,"Duplicate"): self.check()

    def test_rejects_mask_escape_even_when_hash_is_updated(self):
        self.mask[0]=255
        path=self.folder/"density.r8"; path.write_bytes(self.mask)
        self.config["mask"]["sha256"]=digest(path)
        with self.assertRaisesRegex(ValueError,"escaped"): self.check()

    def test_rejects_native_material_override(self):
        self.config["varieties"][0]["override_materials"]=["/Game/Fake.Fake"]
        with self.assertRaisesRegex(ValueError,"slots changed"): self.check()

    def test_rejects_source_world_as_destination(self):
        self.config["world"]=self.config["source_world"]
        with self.assertRaisesRegex(ValueError,"isolated"): self.check()

    def test_rejects_wrong_chunk(self):
        self.config["chunk"]=959
        with self.assertRaisesRegex(ValueError,"965"): self.check()

    def test_native_stripped_zero_channel_keeps_exact_height_grid(self):
        row=self.readback["components"][0]
        row.update(num_elements=4096,weight_channels=0,
                   heights_b64=base64.b64encode(b"\x34\x80"*4096).decode())
        self.assertEqual(self.check()["nonzero_components"],2)
        row["heights_b64"]=base64.b64encode(b"\x35\x80"*4096).decode()
        with self.assertRaisesRegex(ValueError,"height buffer"): self.check()

    def test_stripped_channel_cannot_hide_expected_nonzero_weights(self):
        row=self.active(); row["weight_channels"]=0; row.pop("weights_b64")
        with self.assertRaisesRegex(ValueError,"Missing nonzero"): self.check()

    def test_stripped_channel_rejects_unexpected_weight_payload(self):
        row=self.readback["components"][0]
        row.update(num_elements=4096,weight_channels=0,
                   heights_b64=base64.b64encode(b"\x34\x80"*4096).decode(),weights_b64="AQ==")
        with self.assertRaisesRegex(ValueError,"unexpected stripped"): self.check()

    def test_meadow_filter_preserves_all_retained_bytes_and_order(self):
        poses=[(12499.,40000.),(12500.,40000.),(25000.,45000.),(37500.,50000.),(37501.,40000.)]
        xf=b"".join(struct.pack("<10f",x,y,90+i,0,0,0,1,.6,.6,.6) for i,(x,y) in enumerate(poses))
        records=b"".join(bytes([i])*19 for i in range(5))
        custom=b"".join(bytes([20+i])*16 for i in range(5))
        group={"mesh":OLD_MEADOW[0],"rule":"visual6 meadow","pcg":True,"exact":True}
        result=filter_meadow_group(group,struct.pack("<I",5)+records,{"xf":xf,"xc":custom},5)
        self.assertEqual(result[3],2)
        self.assertEqual(result[1],struct.pack("<I",2)+records[:19]+records[-19:])
        self.assertEqual(result[2],{"xf":xf[:40]+xf[-40:],"xc":custom[:16]+custom[-16:]})
        self.assertEqual(result[0],group)

    def test_baseline_group_is_never_filtered_even_inside_pilot(self):
        group={"mesh":"native groundcover","rule":"short grass","pcg":True,"exact":True}
        row=(group,b"original records",{"xf":b"original poses"},279132)
        self.assertEqual(filter_meadow_group(*row),row)

    def test_owned_material_requires_complete_external_inputs_and_saved_binding(self):
        self.enable_material()
        self.assertTrue(self.check()["saved_buffers_verified"])
        inputs=material_cook_inputs(self.config,self.folder)
        self.assertTrue({"native_grass_material_utoc","native_grass_material_ucas",
                         "native_grass_material_pak","native_grass_material_proof",
                         "native_grass_material_manifest","native_grass_material_tool",
                         "native_grass_material_packaging"}.issubset(inputs))

    def test_owned_material_rejects_stale_container(self):
        self.enable_material()
        Path(self.config["canyon_material"]["files"][0]["path"]).write_bytes(b"changed container")
        with self.assertRaisesRegex(ValueError,"Stale native grass material"): self.check()

    def test_owned_material_updated_container_hash_cannot_reuse_old_proof(self):
        self.enable_material()
        entry=self.config["canyon_material"]["files"][0]
        Path(entry["path"]).write_bytes(b"changed container")
        entry["sha256"]=digest(entry["path"])
        with self.assertRaisesRegex(ValueError,"Stale native grass material evidence"): self.check()

    def test_owned_material_rejects_missing_or_duplicate_container_piece(self):
        self.enable_material()
        original=self.config["canyon_material"]["files"][:]
        self.config["canyon_material"]["files"].pop()
        with self.assertRaisesRegex(ValueError,"complete external"): self.check()
        self.config["canyon_material"]["files"]=[original[0],original[0],original[2]]
        with self.assertRaisesRegex(ValueError,"Unexpected native grass material"): self.check()

    def test_owned_material_rejects_other_parameter_or_association(self):
        self.enable_material()
        entry=self.config["canyon_material"]["manifest"]
        original=json.loads(Path(entry["path"]).read_text())
        for scalars in ({"Dynamic Wind Intensity#-1":{"value":.15,"association":2}},
                        {"Max Offset#-1":{"value":10.,"association":0}},
                        {"Max Offset#-1":{"value":10.,"association":2},"Global Wind Amount#-1":0.}):
            with self.subTest(scalars=scalars):
                altered=copy.deepcopy(original); altered[0]["scalars"]=scalars
                Path(entry["path"]).write_text(json.dumps(altered)); entry["sha256"]=digest(entry["path"])
                with self.assertRaisesRegex(ValueError,"only global Max Offset"): self.check()

    def test_owned_material_rejects_any_lost_native_property_proof(self):
        self.enable_material()
        for key in ("source_properties_preserved","native_tail_identical",
                    "native_parent_and_texture_imports_preserved","existing_guids_preserved"):
            with self.subTest(key=key):
                self.material_proof[key]=False; self.rewrite_material_proof()
                with self.assertRaisesRegex(ValueError,"preservation proof"): self.check()
                self.material_proof[key]=True

    def test_owned_material_cannot_override_other_varieties_or_slots(self):
        self.enable_material()
        for index in (0,1,2):
            with self.subTest(index=index):
                row=self.config["varieties"][index]; old=row["override_materials"][:]
                row["override_materials"].append(CANYON_OBJECT)
                with self.assertRaisesRegex(ValueError,"slots changed"): self.check()
                row["override_materials"]=old

    def test_owned_material_requires_actual_saved_native_binding(self):
        self.enable_material()
        original=copy.deepcopy(self.readback["varieties"])
        for value in (None,[],[dict(v,override_materials=[]) for v in original]):
            with self.subTest(value=value):
                self.readback["varieties"]=value
                with self.assertRaisesRegex(ValueError,"Saved native grass variety"): self.check()

    def test_owned_material_rejects_wrong_identity_or_nonzero_new_guid(self):
        self.enable_material()
        original=copy.deepcopy(self.material_proof["added_scalar"])
        for key,value in (("association",0),("index",0),("expression_guid","1"*32),("value",75.)):
            with self.subTest(key=key):
                self.material_proof["added_scalar"]=dict(original,**{key:value})
                self.rewrite_material_proof()
                with self.assertRaisesRegex(ValueError,"preservation proof"): self.check()

    def test_editor_retirement_requires_verified_unchanged_archive(self):
        source=self.folder/"owned_editor"; source.mkdir()
        (source/"GT.uasset").write_bytes(b"frozen editor asset")
        destination=self.folder/"archive"
        receipt=archive_owned_editor_assets(source,destination)
        self.assertEqual((destination/"GT.uasset").read_bytes(),b"frozen editor asset")
        self.assertEqual(receipt["files"][0]["sha256"],digest(source/"GT.uasset"))
        (source/"GT.uasset").write_bytes(b"changed source")
        with self.assertRaisesRegex(ValueError,"earlier editor archive"):
            archive_owned_editor_assets(source,destination)
        self.assertEqual((destination/"GT.uasset").read_bytes(),b"frozen editor asset")

    def test_editor_archive_cannot_be_inside_retired_folder(self):
        source=self.folder/"owned_editor"; source.mkdir()
        with self.assertRaisesRegex(ValueError,"outside"):
            archive_owned_editor_assets(source,source/"backup")

    def test_material_variant_rejects_grid_or_height_change_before_output(self):
        pilot=self.folder/"pilot.json"; pilot.write_text(json.dumps(self.config))
        land=self.folder/"land"; land.mkdir()
        spec=dict(self.config["grid"],heights="heights.r16")
        (land/"heights.r16").write_bytes((self.folder/"heights.r16").read_bytes())
        destination=self.folder/"variant"
        changed=dict(spec,scale=[200,200,100])
        (land/"landscape.json").write_text(json.dumps(changed))
        with self.assertRaisesRegex(ValueError,"terrain grid"):
            prepare_material_variant(pilot,land,self.folder,destination)
        self.assertFalse(destination.exists())
        (land/"landscape.json").write_text(json.dumps(spec))
        (land/"heights.r16").write_bytes(b"changed terrain")
        with self.assertRaisesRegex(ValueError,"terrain heights"):
            prepare_material_variant(pilot,land,self.folder,destination)
        self.assertFalse(destination.exists())


if __name__ == "__main__": unittest.main()
