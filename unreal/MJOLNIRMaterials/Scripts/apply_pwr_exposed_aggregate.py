"""Upgrade only the .11 driving-surface material, keeping its world, textures and instances."""
import hashlib
import json
import os
from pathlib import Path
import unreal


SCRIPTS=Path(__file__).resolve().parent
ROOT=SCRIPTS.parents[2]
OUT=Path(os.environ.get("PWR_EARTH_FINISH",str(ROOT/"out/pwr/ground-life/earth.12"))).resolve()
START="// Begin PWR forest tracks and loose earth"
END="// End PWR forest tracks and loose earth"
TEXTURE="/Game/MJOLNIR/GrassPilot/Playable/T_PWR_EarthDetail"
MATERIAL="/Game/MJOLNIR/GrassPilot/Playable/M_PWRPilot"
VERIFY=os.environ.get("PWR_EARTH_FINISH_MODE","build")=="verify"


def digest(text):
    return hashlib.sha256(text.encode()).hexdigest()


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    source=(SCRIPTS/"pwr_loose_earth.ush").read_text().strip()
    tail=(SCRIPTS/"pwr_exposed_aggregate.ush").read_text().rstrip()
    first=source.index("    float3 floorShade=lerp")
    last=source.index("\n}",first)
    desired=source[:first]+tail+source[last:]
    lib=unreal.MaterialEditingLibrary
    mat=unreal.load_asset(MATERIAL)
    node=lib.get_material_property_input_node(mat,unreal.MaterialProperty.MP_BASE_COLOR)
    code=node.get_editor_property("code").replace("\r\n","\n")
    if code.count(START)!=1 or code.count(END)!=1:raise ValueError("The .11 ground is missing or duplicated")
    a=code.index(START); b=code.index(END,a)+len(END);previous=code[a:b]
    if previous not in (source,desired):raise ValueError("Unknown road material at this point in its graph history")
    originals=list(node.get_editor_property("inputs"))
    linked=dict(zip([str(i.get_editor_property("input_name")) for i in originals],
                    lib.get_inputs_for_material_expression(mat,node)))
    if linked["ForestFloor"].get_editor_property("texture").get_path_name()!=TEXTURE+".T_PWR_EarthDetail":
        raise ValueError("Unexpected forest-road field")
    existing=linked.get("PathGravelNormal")
    if not existing:
        if VERIFY:raise ValueError("No saved native gravel normal")
        parent=next(s for s in linked.values() if isinstance(s,unreal.MaterialExpressionCustom)
                    and s.get_editor_property("description")=="B30 ground")
        normal=next(s for s in lib.get_inputs_for_material_expression(mat,parent)
                    if isinstance(s,unreal.MaterialExpressionTextureObjectParameter) and
                    str(s.get_editor_property("parameter_name"))=="SandBN")
        pin=unreal.CustomInput();pin.set_editor_property("input_name","PathGravelNormal")
        node.set_editor_property("inputs",originals+[pin])
        if not lib.connect_material_expressions(normal,"",node,"PathGravelNormal"):
            raise RuntimeError("Could not connect existing stock gravel normal")
    elif str(existing.get_editor_property("parameter_name"))!="SandBN":raise ValueError("Unexpected stock normal binding")
    fresh=code[:a]+desired+code[b:]
    if VERIFY:
        if code!=fresh:raise RuntimeError("Material reloaded with stale forest floor")
    else:
        node.set_editor_property("code",fresh)
        lib.recompile_material(mat)
        if not unreal.EditorAssetLibrary.save_loaded_asset(mat,False):raise RuntimeError("Could not save material")
    proof=dict(material=mat.get_path_name(),prior_11_earth_block_sha256=digest(source),
               new_earth_block_sha256=digest(desired),shader_sha256=digest(fresh),
               source_scan="/Game/Megascans/Surfaces/Ground_Gravel_uconcitg",
               existing_stock_colour="SandBD",existing_stock_normal="SandBN",physical_scan_repeat_m=[1.58,5.7,18.6],
               texture_imports=0,world_saves=0,additional_sampler_states=0,
               complete_prior_11_release_receipt_sha256=hashlib.sha256((ROOT/"out/pwr/ground-life/earth/earth-native-readback.json").read_bytes()).hexdigest())
    (OUT/("editor-verified.json" if VERIFY else "editor-applied.json")).write_text(json.dumps(proof,indent=2)+"\n")
    unreal.log("PWR exposed road aggregate "+proof["shader_sha256"])


if __name__=="__main__":main()
