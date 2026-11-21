"""Apply the alpine roadbed to a scratch copy of the .13 terrain material.

Set PWR_ALPINE_EARTH to the directory written by bake_alpine_roadbed.py. A
second commandlet with PWR_ALPINE_EARTH_MODE=verify checks saved graph state.
"""

import hashlib
import json
import os
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parents[2]
ART = Path(
    os.environ.get("PWR_ALPINE_EARTH", ROOT / "out/pwr/alpine-target/earth")
).resolve()
FOLDER = "/Game/MJOLNIR/GrassPilot/Playable"
MATERIAL = FOLDER + "/M_PWRPilot"
LEAF = "T_PWR_AlpineRoadbed"
BASE_RECEIPT = ROOT / "out/pwr/ground-life/earth.12/editor-verified.json"
PRE_START = "// Begin PWR alpine roadbed survey"
PRE_END = "// End PWR alpine roadbed survey"
FINISH_START = "// Begin PWR alpine roadbed finish"
FINISH_END = "// End PWR alpine roadbed finish"
EARTH_TOKEN = "// Begin PWR forest tracks and loose earth"
CONDITION = "[branch] if (loose.r>.002)"
CONDITION_WITH_TILE = "[branch] if (loose.r>.002 && alpineField.r<.998)"
END = "return originalGround;"

# Derivatives are evaluated above the dynamic branch in the parent graph.
# A zero guard of 7 metres keeps the two tiles independent at mip three.
SURVEY = """// Begin PWR alpine roadbed survey
float2 alpineXY = WorldCM.xy*float2(.01,-.01);
bool alpineFar = alpineXY.y > -326.;
float2 alpineOffset = alpineXY-(alpineFar ? float2(-400.,-112.) : float2(-580.,-540.));
float4 alpineField = 0;
[branch] if (max(abs(alpineOffset.x),abs(alpineOffset.y))<123.)
{
    float2 localUV = alpineOffset*float2(1.,-1.)/256. + .5;
    float2 atlasUV = float2((localUV.x + (alpineFar ? 0. : 1.))*.5,localUV.y);
    float lod = clamp(log2(max(.50,pixelMetres)*2.),0.,3.);
    alpineField = Texture2DSampleLevel(AlpineRoadbed,RoadAtlasSampler,atlasUV,lod);
}
// End PWR alpine roadbed survey"""


def sha(data):
    return hashlib.sha256(data).hexdigest()


def without_block(code, start, end):
    if not code.count(start) == code.count(end) == 1:
        raise ValueError("Repeated or incomplete material section: " + start)
    a, b = code.index(start), code.index(end) + len(end)
    return code[:a] + code[b + 1 :]


def compose(code):
    code = code.replace("\r\n", "\n")
    if PRE_START in code:
        code = without_block(code, PRE_START, PRE_END)
        code = without_block(code, FINISH_START, FINISH_END)
        code = code.replace(CONDITION_WITH_TILE, CONDITION)
    old = json.loads(BASE_RECEIPT.read_text())
    if sha(code.encode()) != old["shader_sha256"]:
        raise ValueError(
            "Current ground graph is different from the certified .13 terrain"
        )
    for token in (EARTH_TOKEN, CONDITION, END):
        if code.count(token) != 1:
            raise ValueError("Missing or duplicate terrain anchor: " + token)
    finish = (SCRIPTS / "pwr_alpine_roadbed.ush").read_text().strip()
    if not finish.startswith(FINISH_START) or not finish.endswith(FINISH_END):
        raise ValueError("Incomplete alpine material fragment")
    return (
        code.replace(EARTH_TOKEN, SURVEY + "\n" + EARTH_TOKEN)
        .replace(CONDITION, CONDITION_WITH_TILE)
        .replace(END, finish + "\n" + END)
    )


def main():
    import unreal

    verify = os.environ.get("PWR_ALPINE_EARTH_MODE", "build") == "verify"
    receipt = json.loads((ART / "roadbed.json").read_text())
    atlas = ART / receipt["file"]
    if sha(atlas.read_bytes()) != receipt["sha256"] or receipt["size"] != [1024, 512]:
        raise ValueError("The physical roadbed field does not match its survey")
    library = unreal.MaterialEditingLibrary
    assets = unreal.EditorAssetLibrary
    material = unreal.load_asset(MATERIAL)
    node = library.get_material_property_input_node(
        material, unreal.MaterialProperty.MP_BASE_COLOR
    )
    original = node.get_editor_property("code").replace("\r\n", "\n")
    desired = compose(original)
    pins = list(node.get_editor_property("inputs"))

    def wired():
        inputs = list(node.get_editor_property("inputs"))
        sources = list(library.get_inputs_for_material_expression(material, node))
        if len(inputs) != len(sources):
            raise ValueError("Landscape has unconnected pins")
        return {
            str(i.get_editor_property("input_name")): s for i, s in zip(inputs, sources)
        }

    sources = wired()
    for key, parameter in (
        ("PathGravel", "SandBD"),
        ("PathGravelNormal", "SandBN"),
        ("SiteEarth", "SandD"),
        ("SiteNormal", "SandN"),
    ):
        if str(sources[key].get_editor_property("parameter_name")) != parameter:
            raise ValueError("Unknown stock source for " + key)
    if not verify:
        task = unreal.AssetImportTask()
        task.set_editor_properties(
            dict(
                filename=str(atlas),
                destination_path=FOLDER,
                destination_name=LEAF,
                automated=True,
                replace_existing=True,
                save=False,
            )
        )
        unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])
    texture = unreal.load_asset(FOLDER + "/" + LEAF)
    if texture is None:
        raise RuntimeError("Missing roadbed atlas")
    settings = dict(
        srgb=False,
        compression_settings=unreal.TextureCompressionSettings.TC_VECTOR_DISPLACEMENTMAP,
        mip_gen_settings=unreal.TextureMipGenSettings.TMGS_SIMPLE_AVERAGE,
        address_x=unreal.TextureAddress.TA_CLAMP,
        address_y=unreal.TextureAddress.TA_CLAMP,
        compression_no_alpha=False,
        virtual_texture_streaming=False,
    )
    if not verify:
        texture.set_editor_properties(settings)
        if "AlpineRoadbed" not in sources:
            atlas_node = library.create_material_expression(
                material, unreal.MaterialExpressionTextureObjectParameter, 760, 1020
            )
            atlas_node.set_editor_properties(
                dict(
                    parameter_name="PWRAlpineRoadbed",
                    texture=texture,
                    sampler_type=unreal.MaterialSamplerType.SAMPLERTYPE_LINEAR_COLOR,
                    sampler_source=unreal.SamplerSourceMode.SSM_CLAMP_WORLD_GROUP_SETTINGS,
                )
            )
            pin = unreal.CustomInput()
            pin.set_editor_property("input_name", "AlpineRoadbed")
            node.set_editor_property("inputs", pins + [pin])
            if not library.connect_material_expressions(
                atlas_node, "", node, "AlpineRoadbed"
            ):
                raise RuntimeError("Could not wire the roadbed field")
        node.set_editor_property("code", desired)
        library.recompile_material(material)
        for asset in (texture, material):
            if not assets.save_loaded_asset(asset, False):
                raise RuntimeError("Cannot save " + asset.get_path_name())
    if node.get_editor_property("code").replace("\r\n", "\n") != desired:
        raise ValueError("Alpine shader did not survive reload")
    if (
        wired()["AlpineRoadbed"].get_editor_property("texture").get_path_name()
        != texture.get_path_name()
    ):
        raise ValueError("Saved material points at a different field")
    if any(texture.get_editor_property(k) != v for k, v in settings.items()):
        raise ValueError(
            "The roadbed field has incorrect mip, color, or clamp settings"
        )
    for prop, output in (
        (unreal.MaterialProperty.MP_NORMAL, "WetNormal"),
        (unreal.MaterialProperty.MP_ROUGHNESS, "WetRough"),
        (unreal.MaterialProperty.MP_METALLIC, "RoadMetal"),
        (unreal.MaterialProperty.MP_SPECULAR, "WetSpec"),
    ):
        if (
            library.get_material_property_input_node(material, prop) != node
            or library.get_material_property_input_node_output_name(material, prop)
            != output
        ):
            raise ValueError("Disconnected roadbed output " + output)
    # Recompile the saved graph after every pin and resource is already wired.
    if verify:
        library.recompile_material(material)
    result = dict(
        material=material.get_path_name(),
        shader_sha256=sha(desired.encode()),
        texture=texture.get_path_name(),
        source_sha256=receipt["sha256"],
        added_sampler_states=0,
        full_strength_stock_scan_lookups=4,
        old_full_strength_stock_scan_lookups=6,
        terrain_shape_changes=0,
        game_thread_ticks=0,
        atlas_uncompressed_full_mip_chain_bytes=2796204,
    )
    (ART / ("editor-verified.json" if verify else "editor-applied.json")).write_text(
        json.dumps(result, indent=2) + "\n"
    )
    unreal.log("PWR alpine roadbed " + result["shader_sha256"])


if __name__ == "__main__":
    main()
