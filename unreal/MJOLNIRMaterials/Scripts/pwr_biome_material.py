"""Add the map's mipmapped reflectance field to the PWR Landscape's existing PBR albedo."""
import hashlib

import unreal


def attach(material, folder, spec, source_dir):
    png = source_dir / spec["file"]
    if hashlib.sha256(png.read_bytes()).hexdigest() != spec["sha256"]:
        raise ValueError("The PWR biome texture changed after authoring")
    library = unreal.MaterialEditingLibrary
    prop = unreal.MaterialProperty.MP_BASE_COLOR
    old = library.get_material_property_input_node(material, prop)
    if not old:
        raise ValueError("PWR Landscape has no existing base-colour expression")
    old_pin = library.get_material_property_input_node_output_name(material, prop)
    task = unreal.AssetImportTask()
    task.set_editor_properties({"filename":str(png),"destination_path":folder,"destination_name":"T_PWR_BiomeColor",
                                "automated":True,"save":False})
    unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])
    texture = unreal.load_asset(folder+"/T_PWR_BiomeColor")
    texture.set_editor_properties({"srgb":False,"compression_settings":unreal.TextureCompressionSettings.TC_VECTOR_DISPLACEMENTMAP,
        "mip_gen_settings":unreal.TextureMipGenSettings.TMGS_SIMPLE_AVERAGE,"address_x":unreal.TextureAddress.TA_CLAMP,
        "address_y":unreal.TextureAddress.TA_CLAMP,"virtual_texture_streaming":False})
    if not unreal.EditorAssetLibrary.save_loaded_asset(texture):
        raise RuntimeError("Could not save PWR biome texture")

    def node(cls,y,**props):
        n=library.create_material_expression(material,cls,600,y)
        n.set_editor_properties(props)
        return n
    pos=node(unreal.MaterialExpressionWorldPosition,0)
    tex=node(unreal.MaterialExpressionTextureObjectParameter,150,texture=texture,parameter_name="PWRBiomeColor",
             sampler_type=unreal.MaterialSamplerType.SAMPLERTYPE_LINEAR_COLOR)
    strength=node(unreal.MaterialExpressionScalarParameter,290,parameter_name="PWRBiomeStrength",default_value=1.)
    ox,oy,sx,sy=spec["bounds_ue_cm"]
    code=f"float2 uv = saturate((WorldCM.xy - float2({ox:.1f},{oy:.1f})) / float2({sx:.1f},{sy:.1f}));\n"
    code+="float3 factor = Texture2DSample(Biome,BiomeSampler,uv).rgb * (255.0/128.0);\n"
    code+="return Ground * lerp(1.0.xxx,factor,saturate(Strength));"
    mod=node(unreal.MaterialExpressionCustom,455,description="PWR valley reflectance",code=code,
             output_type=unreal.CustomMaterialOutputType.CMOT_FLOAT3)
    inputs=[("Ground",old,old_pin),("WorldCM",pos,""),("Biome",tex,""),("Strength",strength,"")]
    pins=[]
    for name,_,_ in inputs:
        p=unreal.CustomInput()
        p.set_editor_property("input_name",name)
        pins.append(p)
    mod.set_editor_property("inputs",pins)
    for name,n,pin in inputs:
        if not library.connect_material_expressions(n,pin,mod,name):
            raise RuntimeError(f"Could not bind PWR biome input {name}")
    if not library.connect_material_property(mod,"",prop):
        raise RuntimeError("Could not bind PWR biome colour to albedo")
