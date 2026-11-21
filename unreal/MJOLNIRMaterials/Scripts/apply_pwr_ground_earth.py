"""Run the loose stone PCG, bake a native HISM actor and apply the local forest floor on a .10 working copy."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import runpy
import sys

import unreal


SCRIPT=Path(__file__).resolve().parent
ROOT=SCRIPT.parents[2]
ART=Path(os.environ["PWR_EARTH"]).resolve()
FOLDER="/Game/MJOLNIR/GrassPilot/Playable"
WORLD="/Game/Levels/Halo1/Solo/LPE/LPE"
ACTOR="PWR_LooseGroundStones"
MARKER="// Begin PWR forest tracks and loose earth"
END="// End PWR forest tracks and loose earth"


def sha(file):
    return hashlib.sha256(file.read_bytes()).hexdigest()


def put(name,data):
    (ART/name).write_text(json.dumps(data,indent=2)+"\n")


def stone_actor(world,manifest,verify=False):
    sys.path.insert(0,str(ROOT/"tools/level"))
    import pcg_foliage as pcg
    if not verify:
        os.environ["MJ_PCG_REQUEST"]=str(ART/"pcg-request.json")
        runpy.run_path(str(SCRIPT/"build_pwr_pcg.py"),run_name="__main__")
        first=ART/"LooseGround.json"; repeat=ART/"LooseGroundRepeat.json"
        proof=pcg.compare(ART/"points.json",first,repeat)
        selected=pcg.adapt(ART/"points.json",first,ART/"palette.json",ART,"stones")
        rows=selected["instances"]
        groups=[]
        for g,_,_,count in pcg.read_mjf_groups(ART/"stones.json")[1]:
            groups.append(dict(g,count=count))
        if len(groups)!=4 or not 1900<=len(rows)<=6500:raise ValueError("Unexpected rock selection or counts")
        binary=ART/"stones.bin"
        spec=dict(file=binary.name,actor=ACTOR,count=len(rows),groups=groups,binary_sha256=sha(binary),
                  exact_sidecars=[sha(Path(str(binary)+f".xf{i}")) for i in range(1,len(groups)+1)])
        put("hism.json",spec)
        put("pcg-proof.json",dict(proof,instances=len(rows),source_sha256=sha(ART/"points.json"),
                                 mesh_groups=len(groups),graph=selected["graph"],runtime_pcg=False))
    # The verified .8 baker accepts arbitrary mesh groups, its actor name is the
    # sole different input. Load it privately to keep other editor scripts isolated.
    module_spec=importlib.util.spec_from_file_location("pwr_ground_stone_hism",SCRIPT/"pwr_distance_colonies.py")
    module=importlib.util.module_from_spec(module_spec);module_spec.loader.exec_module(module)
    module.ACTOR=ACTOR
    return module.apply(world,ART/"hism.json",verify)


def terrain(verify=False):
    library=unreal.MaterialEditingLibrary
    mat=unreal.load_asset(FOLDER+"/M_PWRPilot")
    base=library.get_material_property_input_node(mat,unreal.MaterialProperty.MP_BASE_COLOR)
    code=base.get_editor_property("code").replace("\r\n","\n")
    if "Begin PWR road field" not in code or "SiteEarthSampler" not in code or "RoadAtlasSampler" not in code:
        raise ValueError("Missing shipped .10 terrain shader / sampler bindings")
    has=MARKER in code
    if has:
        start=code.index(MARKER);end=code.index(END,start)+len(END);code=code[:start]+code[end:].lstrip("\r\n")
    hlsl=(SCRIPT/"pwr_loose_earth.ush").read_text().strip()
    if code.count("return originalGround;")!=1:raise ValueError("Unexpected final ground colour")
    fresh=code.replace("return originalGround;",hlsl+"\nreturn originalGround;")
    if verify:
        if not has or fresh!=base.get_editor_property("code").replace("\r\n","\n"):
            raise ValueError("Saved .11 landscape graph is stale")
    else:
        tasks=unreal.AssetImportTask()
        tasks.set_editor_properties(dict(filename=str(ART/"earth-detail.png"),destination_path=FOLDER,
                                        destination_name="T_PWR_EarthDetail",automated=True,replace_existing=True,save=False))
        unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([tasks])
        tex=unreal.load_asset(FOLDER+"/T_PWR_EarthDetail")
        tex.set_editor_properties(dict(srgb=False,compression_settings=unreal.TextureCompressionSettings.TC_VECTOR_DISPLACEMENTMAP,
            compression_no_alpha=False,mip_gen_settings=unreal.TextureMipGenSettings.TMGS_SIMPLE_AVERAGE,
            address_x=unreal.TextureAddress.TA_CLAMP,address_y=unreal.TextureAddress.TA_CLAMP,virtual_texture_streaming=False))
        if not has:
            master=next(n for n in library.get_inputs_for_material_expression(mat,base) if isinstance(n,unreal.MaterialExpressionCustom)
                        and n.get_editor_property("description")=="B30 ground")
            mineral=next(n for n in library.get_inputs_for_material_expression(mat,master) if
                isinstance(n,unreal.MaterialExpressionTextureObjectParameter) and str(n.get_editor_property("parameter_name"))=="SandBD")
            atlas=library.create_material_expression(mat,unreal.MaterialExpressionTextureObjectParameter,660,930)
            atlas.set_editor_properties(dict(parameter_name="PWREarthDetail",texture=tex,
                sampler_type=unreal.MaterialSamplerType.SAMPLERTYPE_LINEAR_COLOR,
                sampler_source=unreal.SamplerSourceMode.SSM_CLAMP_WORLD_GROUP_SETTINGS))
            pins=list(base.get_editor_property("inputs"));sources={"ForestFloor":atlas,"PathGravel":mineral}
            for name in sources:
                pin=unreal.CustomInput();pin.set_editor_property("input_name",name);pins.append(pin)
            base.set_editor_property("inputs",pins)
            for name,src in sources.items():
                if not library.connect_material_expressions(src,"",base,name):raise ValueError("Cannot connect "+name)
        base.set_editor_property("code",fresh)
        library.recompile_material(mat)
        for obj in (tex,mat):
            if not unreal.EditorAssetLibrary.save_loaded_asset(obj,False):raise ValueError("Cannot save "+obj.get_name())
    inputs=list(base.get_editor_property("inputs"))
    sources=list(library.get_inputs_for_material_expression(mat,base))
    if len(inputs)!=len(sources):raise ValueError("Landscape graph inputs disagree")
    wired={str(pin.get_editor_property("input_name")):src for pin,src in zip(inputs,sources)}
    for key,parameter in (("ForestFloor","PWREarthDetail"),("PathGravel","SandBD"),("SiteEarth","SandD"),("SiteNormal","SandN")):
        src=wired.get(key)
        if not isinstance(src,unreal.MaterialExpressionTextureObjectParameter) or str(src.get_editor_property("parameter_name"))!=parameter:
            raise ValueError("Missing saved terrain material input "+key)
    if wired["ForestFloor"].get_editor_property("texture").get_path_name()!=FOLDER+"/T_PWR_EarthDetail.T_PWR_EarthDetail":
        raise ValueError("The native graph references a different forest field")
    return {"material":mat.get_path_name(),"field":FOLDER+"/T_PWR_EarthDetail","source_sha256":sha(ART/"earth-detail.png"),
            "shader_sha256":hashlib.sha256(fresh.encode()).hexdigest(),"extra_sampler_states":0,
            "reused_inputs":["RoadAtlasSampler","SiteEarthSampler","SandD","SandN","SandBD"],"forest_floor_and_gravel_pins_connected":True}


def main():
    manifest=json.loads((ART/"earth.json").read_text())
    for f,h in manifest["source_sha256"].items():
        if sha(ART/f)!=h:raise ValueError("Source changed after survey: "+f)
    verify=os.environ.get("PWR_EARTH_MODE","build")=="verify"
    loader=unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    if not loader.load_level(WORLD):raise RuntimeError("Cannot open LPE")
    world=unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
    actors=stone_actor(world,manifest,verify);material=terrain(verify)
    if not verify and not loader.save_current_level():raise RuntimeError("Could not save world")
    put("editor-verify.json" if verify else "editor-build.json",dict(world=actors,material=material))
    unreal.log("PWR ground life saved "+str(actors["actor"]))


if __name__=="__main__":
    main()
