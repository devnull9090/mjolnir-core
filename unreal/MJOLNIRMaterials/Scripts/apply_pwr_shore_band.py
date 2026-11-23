"""PWR landscape: the shore band (wet line, gravel and damp earth) along every lake and river,
from the map's shore mask (tools/level/shore_mask.py), in place of the northern lake's
surveyed outline.

The valley node of M_PWRPilot gains two inputs: ShoreData (texture parameter PWRShoreData, the
mask) and ShoreRect (vector parameter LandRect, which the level loader already binds from
landscape.pbr.rect). The northern lake's block, whose shoreline spans were compiled into the
shader, becomes the same beach drawn wherever the mask says water is near; its look (gravel over
damp earth, darker and glossier at the water) is unchanged. A mask with B = 0 draws no band, so
the parameter's default texture leaves the parent look.

Run with UnrealEditor-Cmd -run=pythonscript on the river-riparian editor project, after the
round has restored M_PWRPilot:
  PWR_SHORE_MASK   the mask PNG (2048 RGBA8)
  PWR_SHORE_VERIFY 1 = check only (a fresh editor), 0 = apply
Writes PWR_SHORE_RECEIPT (json) when set.
"""
from hashlib import sha256
import json
import os
from pathlib import Path

import unreal as ue

DIR = "/Game/MJOLNIR/GrassPilot/Playable"
TEXTURE = "T_PWRShoreData"
START = "// Northern lake. Dry uplands, roads and the downstream river use the parent shader."
END = "// Surveyed river alluvium."
FRAGMENT = r"""// Shore band from the map's own water (tools/level/shore_mask.py): R signed metres from the
// water's edge (-8..24), G metres above that water (-4..12), B 1 where the mask has water data.
float2 hwXY = WorldCM.xy * float2(.01,-.01);
float2 hwDx = ddx(hwXY), hwDy = ddy(hwXY);
{
    float2 suv = (WorldCM.xy - ShoreRect.xy) / max(ShoreRect.zw, 1.);
    float4 sm = ShoreData.SampleLevel(SiteEarthSampler, suv, 0);
    float bank = sm.r * 32. - 8.;
    float level = sm.g * 16. - 4.;
    float fringe = .55*sin(dot(hwXY,float2(.53,.34)))+.42*sin(dot(hwXY,float2(.21,-.71)));
    float cover = step(.5, sm.b)*(1.-smoothstep(2.0,7.0,bank+fringe))*(1.-smoothstep(1.8,4.4,level));
    [branch] if (cover>.001)
    {
        float2 uv = hwXY/2.85 + float2(.343,.718);
        float3 stone = Texture2DSampleGrad(PathGravel,SiteEarthSampler,uv,hwDx/2.85,hwDy/2.85).rgb;
        float2 grain = Texture2DSampleGrad(PathGravelNormal,SiteEarthSampler,uv,hwDx/2.85,hwDy/2.85).rg*2.-1.;
        float3 earth = Texture2DSampleGrad(SiteEarth,SiteEarthSampler,hwXY/5.7,hwDx/5.7,hwDy/5.7).rgb;
        float wet = 1.-smoothstep(-.35,.95,level+.13*fringe);
        // More gravel toward the water, where the current sorts it; damp earth, not ochre, above.
        float gravel = saturate(.42+.19*sin(dot(hwXY,float2(.15,.09)))+.24*dot(stone,float3(.25,.55,.20))+.30*(1.-smoothstep(.5,3.5,bank)));
        float3 beach = lerp(earth*float3(.70,.64,.55),stone*float3(.81,.77,.70),gravel)*lerp(1.,.49,wet);
        originalGround = lerp(originalGround,beach,cover);
        WetNormal = normalize(lerp(WetNormal,normalize(float3(grain*.52,1.)),cover));
        WetRough = lerp(WetRough,lerp(.89,.53,wet),cover);
        WetSpec = lerp(WetSpec,lerp(.23,.34,wet),cover);
        RoadMetal = lerp(RoadMetal,0.,cover);
    }
}

"""


def main():
    verify = os.environ.get("PWR_SHORE_VERIFY") == "1"
    image = Path(os.environ["PWR_SHORE_MASK"])
    assets = ue.EditorAssetLibrary
    lib = ue.MaterialEditingLibrary
    texpath = f"{DIR}/{TEXTURE}"
    if verify and not assets.does_asset_exist(texpath):
        raise RuntimeError("Missing shore mask texture " + texpath)
    if not verify:   # always from this mask: a rebaked mask replaces the last one
        task = ue.AssetImportTask()
        task.set_editor_properties(dict(filename=str(image), destination_path=DIR, destination_name=TEXTURE,
                                        automated=True, replace_existing=True, save=False))
        ue.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])
    tex = ue.load_asset(texpath)
    settings = dict(srgb=False, compression_settings=ue.TextureCompressionSettings.TC_VECTOR_DISPLACEMENTMAP,
                    virtual_texture_streaming=False, filter=ue.TextureFilter.TF_BILINEAR,
                    address_x=ue.TextureAddress.TA_CLAMP, address_y=ue.TextureAddress.TA_CLAMP)
    if not verify:
        tex.set_editor_properties(settings)
        if not assets.save_loaded_asset(tex, False):
            raise RuntimeError("Could not save " + texpath)
    for k, v in settings.items():
        if tex.get_editor_property(k) != v:
            raise RuntimeError(f"Shore mask {k} is {tex.get_editor_property(k)}, wanted {v}")

    mat = ue.load_asset(DIR + "/M_PWRPilot")
    node = lib.get_material_property_input_node(mat, ue.MaterialProperty.MP_BASE_COLOR)
    code = node.get_editor_property("code").replace("\r\n", "\n")

    def linked():
        names = [str(v.get_editor_property("input_name")) for v in node.get_editor_property("inputs")]
        return dict(zip(names, lib.get_inputs_for_material_expression(mat, node)))

    if verify:
        wiring = linked()
        if FRAGMENT.strip() not in code or START in code:
            raise RuntimeError("Shore band missing from the saved valley shader")
        if wiring.get("ShoreData") is None or wiring["ShoreData"].get_editor_property("texture").get_path_name() != tex.get_path_name():
            raise RuntimeError("ShoreData not bound to the shore mask")
        both = wiring.get("ShoreRect")
        feeds = lib.get_inputs_for_material_expression(mat, both) if both else []
        if not feeds or not all(f and f.get_class().get_name() == "MaterialExpressionVectorParameter"
                                and str(f.get_editor_property("parameter_name")) == "LandRect" for f in feeds[:2]):
            raise RuntimeError("ShoreRect not bound to LandRect")
    else:
        if code.count(START) != 1 or code.count(END) != 1 or code.index(START) > code.index(END):
            raise RuntimeError("Unrecognised valley shader: the northern lake block is not where expected")
        code = code[:code.index(START)] + FRAGMENT + code[code.index(END):]
        wiring = linked()
        inputs = list(node.get_editor_property("inputs"))
        if "ShoreData" not in wiring:
            obj = lib.create_material_expression(mat, ue.MaterialExpressionTextureObjectParameter, 760, 1760)
            obj.set_editor_properties(dict(parameter_name="PWRShoreData", texture=tex,
                                           sampler_type=ue.MaterialSamplerType.SAMPLERTYPE_LINEAR_COLOR,
                                           sampler_source=ue.SamplerSourceMode.SSM_WRAP_WORLD_GROUP_SETTINGS))
            pin = ue.CustomInput()
            pin.set_editor_property("input_name", "ShoreData")
            inputs.append(pin)
            node.set_editor_property("inputs", inputs)
            if not lib.connect_material_expressions(obj, "", node, "ShoreData"):
                raise RuntimeError("Unable to bind ShoreData")
        if "ShoreRect" not in linked():
            rect = lib.create_material_expression(mat, ue.MaterialExpressionVectorParameter, 760, 1900)
            rect.set_editor_properties(dict(parameter_name="LandRect",
                                            default_value=ue.LinearColor(-100000., -100000., 200000., 200000.)))
            inputs = list(node.get_editor_property("inputs"))
            pin = ue.CustomInput()
            pin.set_editor_property("input_name", "ShoreRect")
            node.set_editor_property("inputs", inputs + [pin])
            # All four components (x, y, width, height): RGB appended with A (the default
            # output is RGB only, and UE 5.5's vector parameter has no RGBA pin).
            both = lib.create_material_expression(mat, ue.MaterialExpressionAppendVector, 900, 1900)
            if not (lib.connect_material_expressions(rect, "", both, "A")
                    and lib.connect_material_expressions(rect, "A", both, "B")
                    and lib.connect_material_expressions(both, "", node, "ShoreRect")):
                raise RuntimeError("Unable to bind ShoreRect")
        node.set_editor_property("code", code)
        lib.recompile_material(mat)
        if not assets.save_loaded_asset(mat, False):
            raise RuntimeError("Could not save M_PWRPilot")
    saved = node.get_editor_property("code").replace("\r\n", "\n")
    receipt = {"material": mat.get_path_name(), "texture": texpath, "verify": verify,
               "mask_sha256": sha256(image.read_bytes()).hexdigest(),
               "shader_sha256": sha256(saved.encode()).hexdigest(),
               "inputs": [str(v.get_editor_property("input_name")) for v in node.get_editor_property("inputs")]}
    if os.environ.get("PWR_SHORE_RECEIPT"):
        Path(os.environ["PWR_SHORE_RECEIPT"]).write_text(json.dumps(receipt, indent=1))
    ue.log("PWR shore band: " + json.dumps(receipt))


main()
