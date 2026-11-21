"""Add the .9 road surface to the isolated, already validated .8 landscape graph."""
import hashlib
import json
import os
from pathlib import Path
import unreal


ART=Path(os.environ["PWR_APPROACH_ROADS"]).resolve()
ROOT="/Game/MJOLNIR/GrassPilot/Playable"
LEAF="T_PWR_RoadNetwork"
STOCK="PWR valley reflectance and wet ground"
NEW="PWR valley ground with engineered and service roads"
MARKER="// Begin PWR road field"
FINAL="return lerp(diffuse,earth,smoothstep(.07,.78,wet)*.88);"


def main():
    spec=json.loads((ART/"roads.json").read_text())
    image=ART/spec["file"]
    if hashlib.sha256(image.read_bytes()).hexdigest()!=spec["sha256"]:
        raise RuntimeError("Road field and sealed topology disagree")
    library=unreal.MaterialEditingLibrary
    assets=unreal.EditorAssetLibrary
    mat=unreal.load_asset(ROOT+"/M_PWRPilot")
    node=library.get_material_property_input_node(mat,unreal.MaterialProperty.MP_BASE_COLOR)
    if not isinstance(node,unreal.MaterialExpressionCustom) or node.get_editor_property("description") not in (STOCK,NEW):
        raise ValueError("Expected the .8 PWR valley ground and wetland graph")
    text=node.get_editor_property("code")
    if MARKER in text: original=text.split(MARKER)[0]
    else:
        if text.count(FINAL)!=1: raise ValueError("Unexpected .8 terrain return")
        original=text.replace(FINAL,"float3 originalGround = lerp(diffuse,earth,smoothstep(.07,.78,wet)*.88);\n")
    task=unreal.AssetImportTask()
    task.set_editor_properties(dict(filename=str(image),destination_path=ROOT,destination_name=LEAF,
                                    automated=True,replace_existing=True,save=False))
    unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])
    tex=unreal.load_asset(ROOT+"/"+LEAF)
    if not tex: raise RuntimeError("Missing imported road field")
    tex.set_editor_properties(dict(srgb=False,compression_settings=unreal.TextureCompressionSettings.TC_VECTOR_DISPLACEMENTMAP,
                                   compression_no_alpha=False,mip_gen_settings=unreal.TextureMipGenSettings.TMGS_SIMPLE_AVERAGE,
                                   address_x=unreal.TextureAddress.TA_CLAMP,address_y=unreal.TextureAddress.TA_CLAMP,
                                   virtual_texture_streaming=False))
    if node.get_editor_property("description")==STOCK:
        if library.get_material_property_input_node(mat,unreal.MaterialProperty.MP_METALLIC):
            raise RuntimeError("Existing landscape also authors metallic")
        sample=library.create_material_expression(mat,unreal.MaterialExpressionTextureObjectParameter,600,650)
        sample.set_editor_properties(dict(parameter_name="PWRRoadNetwork",texture=tex,
            sampler_type=unreal.MaterialSamplerType.SAMPLERTYPE_LINEAR_COLOR,
            sampler_source=unreal.SamplerSourceMode.SSM_CLAMP_WORLD_GROUP_SETTINGS))
        pins=list(node.get_editor_property("inputs"))
        field=unreal.CustomInput();field.set_editor_property("input_name","RoadAtlas")
        pins.append(field);node.set_editor_property("inputs",pins)
        if not library.connect_material_expressions(sample,"",node,"RoadAtlas"):
            raise RuntimeError("Could not connect road texture")
        outs=list(node.get_editor_property("additional_outputs"))
        metal=unreal.CustomOutput()
        metal.set_editor_properties(dict(output_name="RoadMetal",output_type=unreal.CustomMaterialOutputType.CMOT_FLOAT1))
        outs.append(metal);node.set_editor_property("additional_outputs",outs)
        if not library.connect_material_property(node,"RoadMetal",unreal.MaterialProperty.MP_METALLIC):
            raise RuntimeError("Could not connect flush metal shoulders")
    hlsl=(Path(__file__).with_name("pwr_approach_roads.ush")).read_text()
    node.set_editor_property("code",original+MARKER+"\n"+hlsl)
    node.set_editor_property("description",NEW)
    library.recompile_material(mat)
    if not assets.save_loaded_asset(tex,False) or not assets.save_loaded_asset(mat,False):
        raise RuntimeError("Could not save road material and texture")
    names={}
    for prop,output in ((unreal.MaterialProperty.MP_ROUGHNESS,"WetRough"),
                        (unreal.MaterialProperty.MP_NORMAL,"WetNormal"),
                        (unreal.MaterialProperty.MP_SPECULAR,"WetSpec"),
                        (unreal.MaterialProperty.MP_METALLIC,"RoadMetal")):
        if (library.get_material_property_input_node(mat,prop)!=node or
            library.get_material_property_input_node_output_name(mat,prop)!=output):
            raise RuntimeError("Unexpected terrain property binding "+str(prop))
        names[str(prop)]=output
    proof=dict(source_sha256=spec["sha256"],world_bounds_cm=spec["bounds_ue_cm"],material=mat.get_path_name(),
               atlas=tex.get_path_name(),revision=NEW,properties=names,shader_sha256=hashlib.sha256(hlsl.encode()).hexdigest())
    (ART/"editor-roads.json").write_text(json.dumps(proof,indent=2)+"\n")
    unreal.log("PWR native road material saved "+spec["sha256"])


main()
