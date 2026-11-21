"""Apply the sealed valley field to an isolated copy of the playable LPE project's material."""
import hashlib
import json
import os
from pathlib import Path

import unreal


ART = Path(os.environ["PWR_TERRAIN_DISTANCE"]).resolve()
FOLDER = "/Game/MJOLNIR/GrassPilot/Playable"
REVISION = "PWR valley reflectance and wet ground"
INPUTS = (("GroundRough", "WetRough", unreal.MaterialProperty.MP_ROUGHNESS, unreal.CustomMaterialOutputType.CMOT_FLOAT1),
          ("GroundNormal", "WetNormal", unreal.MaterialProperty.MP_NORMAL, unreal.CustomMaterialOutputType.CMOT_FLOAT3),
          ("GroundSpec", "WetSpec", unreal.MaterialProperty.MP_SPECULAR, unreal.CustomMaterialOutputType.CMOT_FLOAT1))


def main():
    spec = json.loads((ART/"terrain-field.json").read_text())
    png = ART / spec["file"]
    if hashlib.sha256(png.read_bytes()).hexdigest() != spec["sha256"]:
        raise RuntimeError("Terrain colour/coverage field does not match its authoring receipt")
    eal, mel = unreal.EditorAssetLibrary, unreal.MaterialEditingLibrary
    master = unreal.load_asset(FOLDER+"/M_PWRPilot")
    tex = unreal.load_asset(FOLDER+"/T_PWR_BiomeColor")
    if not master or not tex:
        raise RuntimeError("The playable .7 LPE material and biome texture are required")
    paint = mel.get_material_property_input_node(master,unreal.MaterialProperty.MP_BASE_COLOR)
    if not isinstance(paint,unreal.MaterialExpressionCustom):
        raise RuntimeError("Unexpected base-colour driver on M_PWRPilot")
    label = paint.get_editor_property("description")
    if label not in ("PWR valley reflectance",REVISION):
        raise RuntimeError(f"Unexpected landscape graph: {label}")

    if label != REVISION:
        # Retain the four wired inputs from the existing RGB wrapper. Connect
        # the original material's surface properties while their wires still exist.
        pins = list(paint.get_editor_property("inputs"))
        if [str(p.get_editor_property("input_name")) for p in pins] != ["Ground","WorldCM","Biome","Strength"]:
            raise RuntimeError("The sealed landscape biome graph inputs changed")
        original = []
        outputs = []
        for name, result, prop, kind in INPUTS:
            src = mel.get_material_property_input_node(master,prop)
            src_pin = mel.get_material_property_input_node_output_name(master,prop)
            if not src or src == paint:
                raise RuntimeError(f"Missing original landscape {prop}")
            original.append((src,src_pin,name))
            pin = unreal.CustomInput()
            pin.set_editor_property("input_name",name)
            pins.append(pin)
            output = unreal.CustomOutput()
            output.set_editor_properties({"output_name":result,"output_type":kind})
            outputs.append(output)
        paint.set_editor_property("inputs",pins)
        paint.set_editor_property("additional_outputs",outputs)
        for src,src_pin,name in original:
            if not mel.connect_material_expressions(src,src_pin,paint,name):
                raise RuntimeError(f"Could not feed original {name} to the wet-ground expression")
        for _,result,prop,_ in INPUTS:
            if not mel.connect_material_property(paint,result,prop):
                raise RuntimeError(f"Could not attach wet-ground output {result}")

    task = unreal.AssetImportTask()
    task.set_editor_properties(dict(filename=str(png),destination_path=FOLDER,destination_name="T_PWR_BiomeColor",
                                    automated=True,replace_existing=True,save=False))
    unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])
    tex = unreal.load_asset(FOLDER+"/T_PWR_BiomeColor")
    tex.set_editor_properties(dict(srgb=False,compression_settings=unreal.TextureCompressionSettings.TC_VECTOR_DISPLACEMENTMAP,
                                   compression_no_alpha=False,mip_gen_settings=unreal.TextureMipGenSettings.TMGS_SIMPLE_AVERAGE,
                                   address_x=unreal.TextureAddress.TA_CLAMP,address_y=unreal.TextureAddress.TA_CLAMP,
                                   virtual_texture_streaming=False))
    ox, oy, sx, sy = spec["bounds_ue_cm"]
    code = f"float2 rect = saturate((WorldCM.xy - float2({ox:.1f},{oy:.1f}))/float2({sx:.1f},{sy:.1f}));\n"
    # Reuse the single mipmapped field lookup. Outside a wet region all three
    # native surface properties survive exactly. Use the original albedo's detail
    # for the warm mud; the Flux lake/river materials still draw the open water.
    code += """
float4 field = Texture2DSample(Biome,BiomeSampler,rect);
float k = saturate(Strength);
float3 diffuse = Ground * lerp(1.0.xxx,field.rgb*(255.0/128.0),k);
float wet = field.a*k;
float pool = smoothstep(.53,.89,wet);
float3 earth = dot(diffuse,float3(.2126,.7152,.0722))*float3(1.09,.89,.66);
WetRough = lerp(GroundRough,min(GroundRough,lerp(.46,.13,pool)),wet);
WetSpec = lerp(GroundSpec,lerp(.24,.30,pool),wet);
WetNormal = lerp(GroundNormal,float3(0,0,1),pool*.90);
return lerp(diffuse,earth,smoothstep(.07,.78,wet)*.88);
"""
    paint.set_editor_property("code",code)
    paint.set_editor_property("description",REVISION)
    mel.recompile_material(master)
    if not eal.save_loaded_asset(tex,False) or not eal.save_loaded_asset(master,False):
        raise RuntimeError("Could not persist the terrain texture and PBR graph")
    def verify(prop, name):
        src = mel.get_material_property_input_node(master,prop)
        if src != paint or mel.get_material_property_input_node_output_name(master,prop) != name:
            raise ValueError(f"Wrong graph binding at {prop}")
    for _,name,prop,_ in INPUTS:
        verify(prop,name)
    if mel.get_material_property_input_node(master,unreal.MaterialProperty.MP_BASE_COLOR) != paint:
        raise RuntimeError("The terrain albedo no longer references its own wrapper")
    record = {"material":master.get_path_name(),"field":tex.get_path_name(),"source_sha256":spec["sha256"],
              "sampler_count_added":0,"world_bounds_cm":spec["bounds_ue_cm"],
              "verified_outputs":[name for _,name,_,_ in INPUTS],
              "colour_space":"linear RGB and wet coverage alpha","mips":"simple average, clamped"}
    (ART/"editor-field.json").write_text(json.dumps(record,indent=2)+"\n")
    unreal.log("PWR terrain field saved "+spec["sha256"])


main()
