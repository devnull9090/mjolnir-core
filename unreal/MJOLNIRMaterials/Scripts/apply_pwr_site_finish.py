"""Install the .10 ground in an isolated copy of the .9 project."""
import hashlib
import json
import os
from pathlib import Path

import unreal


ART=Path(os.environ["PWR_SITE_FINISH"]).resolve()
ROOT="/Game/MJOLNIR/GrassPilot/Playable"
PREVIOUS="PWR valley ground with engineered and service roads"
REVISION="PWR valley ground with graded court approaches"
SCRIPT=Path(__file__).resolve().parent
MARKER="// Begin PWR road field"
CUT="return originalGround;"


def import_field(image,name):
    task=unreal.AssetImportTask()
    task.set_editor_properties(dict(filename=str(image),destination_path=ROOT,destination_name=name,
                                   automated=True,replace_existing=True,save=False))
    unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])
    tex=unreal.load_asset(ROOT+"/"+name)
    tex.set_editor_properties(dict(srgb=False,compression_settings=unreal.TextureCompressionSettings.TC_VECTOR_DISPLACEMENTMAP,
                                   compression_no_alpha=False,mip_gen_settings=unreal.TextureMipGenSettings.TMGS_SIMPLE_AVERAGE,
                                   address_x=unreal.TextureAddress.TA_CLAMP,address_y=unreal.TextureAddress.TA_CLAMP,
                                   virtual_texture_streaming=False))
    if not unreal.EditorAssetLibrary.save_loaded_asset(tex,False):
        raise RuntimeError("Could not save "+name)
    return tex


def main():
    spec=json.loads((ART/"site-ground.json").read_text())
    for key,file in spec["files"].items():
        if hashlib.sha256((ART/file).read_bytes()).hexdigest()!=spec["source_sha256"][key]:
            raise RuntimeError("Stale authored "+key)
    library=unreal.MaterialEditingLibrary
    mat=unreal.load_asset(ROOT+"/M_PWRPilot")
    node=library.get_material_property_input_node(mat,unreal.MaterialProperty.MP_BASE_COLOR)
    if node.get_editor_property("description") not in (PREVIOUS,REVISION):
        raise RuntimeError("Expected the sealed .9 landscape material")
    current=node.get_editor_property("code")
    if current.count(MARKER)!=1: raise RuntimeError("Missing .9 road field")
    prefix=current.split(MARKER)[0]
    oldroads=(SCRIPT/"pwr_approach_roads.ush").read_text()
    if node.get_editor_property("description")==PREVIOUS and current.replace("\r\n","\n").strip()!=(prefix+MARKER+"\n"+oldroads).strip():
        raise RuntimeError("The installed .9 graph differs from the .9 road source")
    biome=import_field(ART/spec["files"]["biome"],"T_PWR_BiomeColor")
    grade=import_field(ART/spec["files"]["grade"],"T_PWR_SiteGround")
    if node.get_editor_property("description")==PREVIOUS:
        original=next(n for n in library.get_inputs_for_material_expression(mat,node) if
                      isinstance(n,unreal.MaterialExpressionCustom) and n.get_editor_property("description")=="B30 ground")
        params={str(n.get_editor_property("parameter_name")):n for n in library.get_inputs_for_material_expression(mat,original)
                if isinstance(n,unreal.MaterialExpressionTextureObjectParameter)}
        field=library.create_material_expression(mat,unreal.MaterialExpressionTextureObjectParameter,650,820)
        field.set_editor_properties(dict(parameter_name="PWRSiteGround",texture=grade,
            sampler_type=unreal.MaterialSamplerType.SAMPLERTYPE_LINEAR_COLOR,
            sampler_source=unreal.SamplerSourceMode.SSM_CLAMP_WORLD_GROUP_SETTINGS))
        sources={"SiteGrade":field,"SiteEarth":params["SandD"],"SiteNormal":params["SandN"],"SiteRock":params["RockD"]}
        pins=list(node.get_editor_property("inputs"))
        for name in sources:
            pin=unreal.CustomInput();pin.set_editor_property("input_name",name);pins.append(pin)
        node.set_editor_property("inputs",pins)
        for name,source in sources.items():
            if not library.connect_material_expressions(source,"",node,name):
                raise RuntimeError("Could not reuse material source "+name)
    # A one-metre classification texture causes visibly stepped outer metal.
    # Use its mipped hierarchy only to identify a primary lane, then draw the
    # engineered outside edge in the bilinearly interpolated cross-track metres.
    before="float metal = smoothstep"
    edge="""
    float mainEdge=0;
    [branch] if (side>7.0 && side<12.1 && junction>.70)
    {
        float2 broad=Texture2DSampleLevel(RoadAtlas,RoadAtlasSampler,rect,2.2).rg;
        mainEdge=smoothstep(.08,.24,broad.g/max(broad.r,.001))*smoothstep(.70,.96,junction);
        paving=lerp(paving,1-smoothstep(8.62-aa,8.88+aa,side),mainEdge);
    }
    float metal = smoothstep"""
    margin="float rutsGloss ="
    gravel="""float vergeAggregate=mainEdge*(1-smoothstep(9.70,11.8,side));
    float3 shoulderStone=float3(.168,.151,.121)*clamp(.88+.22*sqrt(lum)+.035*stratum,.79,1.26);
    soil=lerp(soil,shoulderStone,vergeAggregate);
    float rutsGloss ="""
    if any(oldroads.count(term)!=1 for term in (before,margin,CUT)): raise ValueError("Unexpected road shader")
    finish=(SCRIPT/"pwr_site_finish.ush").read_text()
    code=prefix+MARKER+"\n"+oldroads.replace(before,edge).replace(margin,gravel).replace(CUT,finish)
    node.set_editor_properties(dict(code=code,description=REVISION))
    library.recompile_material(mat)
    if not unreal.EditorAssetLibrary.save_loaded_asset(mat,False): raise RuntimeError("Could not save .10 shader")
    bindings={}
    for prop,output in ((unreal.MaterialProperty.MP_ROUGHNESS,"WetRough"),(unreal.MaterialProperty.MP_NORMAL,"WetNormal"),
                        (unreal.MaterialProperty.MP_SPECULAR,"WetSpec"),(unreal.MaterialProperty.MP_METALLIC,"RoadMetal")):
        if library.get_material_property_input_node(mat,prop)!=node or library.get_material_property_input_node_output_name(mat,prop)!=output:
            raise RuntimeError("Unexpected landscape output "+str(prop))
        bindings[str(prop)]=output
    doc=dict(material=mat.get_path_name(),biome=biome.get_path_name(),grade=grade.get_path_name(),
             source_sha256=spec["source_sha256"],shader_sha256=hashlib.sha256(code.encode()).hexdigest(),
             stock_inputs=["SandD","SandN","RockD"],bound_outputs=bindings)
    (ART/"editor-site-ground.json").write_text(json.dumps(doc,indent=2)+"\n")
    unreal.log("PWR .10 graded ground saved "+doc["shader_sha256"])


main()
