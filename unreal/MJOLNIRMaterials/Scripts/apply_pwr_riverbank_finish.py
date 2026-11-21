"""Cook photographed river gravel and rooted native shoreline plants onto the .34 scene."""
from hashlib import sha256
import json
import math
import os
from pathlib import Path
import sys
import traceback

import unreal as ue

ROOT=Path(os.environ["PWR_HEADWATER_ROOT"])
APRON=os.environ.get("PWR_RIVER_APRON")=="1"
BASE=Path(os.environ["PWR_HEADWATER_OUTPUT"]) if APRON else ROOT/"out/pwr/river-erosion"
WORK=BASE/"bank" if APRON else BASE/"shore-finish"
SCANS=ROOT/"out/pwr/river-erosion/shore-finish/scans" if APRON else WORK/"scans"
SCRIPTS=ROOT/"unreal/MJOLNIRMaterials/Scripts"
sys.path.insert(0,str(SCRIPTS))
from apply_headwater_shore import station_rows

VERIFY=os.environ.get("PWR_HEADWATER_VERIFY")=="1"
DIR="/Game/MJOLNIR/GrassPilot/Playable"
PLANTS={
    "rye":("PWR_WindMeadow","PWRBlade_MJFol_1_1_0"),
    "wild_a":("PWR_WindMeadow","PWRBlade_MJFol_2_1_0"),
    "wild_b":("PWR_WindMeadow","PWRBlade_MJFol_3_1_0"),
    "sedge":("MJOLNIR_Foliage","MJFol_2_1_0"),
    "rush":("PWR_FieldUnderstory","MJFol_13_1_0"),
    "willow":("PWR_FieldUnderstory","MJFol_17_1_0"),
}


def read(path):
    return json.loads(path.read_text())


def material():
    asset=ue.EditorAssetLibrary
    lib=ue.MaterialEditingLibrary
    material=ue.load_asset(DIR+"/M_PWRPilot")
    node=lib.get_material_property_input_node(material,ue.MaterialProperty.MP_BASE_COLOR)
    current=node.get_editor_property("code").replace("\r\n","\n").strip()
    scan=read(SCANS/"ganges-river-cobble.json")
    tokens=("RiverCobble","RiverCobbleN")
    spec=(scan["packed_diffuse"],scan["maps"]["nor_dx"])
    def linked():
        names=[str(v.get_editor_property("input_name")) for v in node.get_editor_property("inputs")]
        return dict(zip(names,lib.get_inputs_for_material_expression(material,node)))
    texture_hashes={}
    for pin,record in zip(tokens,spec):
        image=SCANS/record["file"]
        name=image.stem
        texpath=DIR+"/"+name
        normal=(pin=="RiverCobbleN")
        digest=sha256(image.read_bytes()).hexdigest()
        if digest!=record["sha256"]:
            raise ValueError("Scan hash mismatch: "+name)
        texture_hashes[name]=digest
        if not asset.does_asset_exist(texpath):
            if VERIFY:
                raise ValueError("Missing cooked scan: "+texpath)
            task=ue.AssetImportTask()
            task.set_editor_properties(dict(filename=str(image),destination_path=DIR,destination_name=name,
                                            automated=True,replace_existing=False,save=False))
            ue.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])
        tex=ue.load_asset(texpath)
        settings=dict(srgb=not normal,compression_settings=ue.TextureCompressionSettings.TC_NORMALMAP if normal
                      else ue.TextureCompressionSettings.TC_BC7,compression_no_alpha=normal,
                      max_texture_size=2048,filter=ue.TextureFilter.TF_DEFAULT)
        if not VERIFY and not APRON:
            tex.set_editor_properties(settings)
            if not asset.save_loaded_asset(tex,False):
                raise ValueError("Could not save "+texpath)
        if any(tex.get_editor_property(k)!=v for k,v in settings.items()):
            raise ValueError("Unexpected scan space or compression")
        wiring=linked()
        if pin not in wiring:
            if VERIFY:
                raise ValueError("Missing "+pin)
            obj=lib.create_material_expression(material,ue.MaterialExpressionTextureObjectParameter,
                                              760,1460+125*normal)
            obj.set_editor_properties(dict(parameter_name=pin,texture=tex,
                sampler_type=ue.MaterialSamplerType.SAMPLERTYPE_NORMAL if normal else ue.MaterialSamplerType.SAMPLERTYPE_COLOR,
                sampler_source=ue.SamplerSourceMode.SSM_WRAP_WORLD_GROUP_SETTINGS))
            inputs=list(node.get_editor_property("inputs"))
            inp=ue.CustomInput()
            inp.set_editor_property("input_name",pin)
            node.set_editor_property("inputs",inputs+[inp])
            if not lib.connect_material_expressions(obj,"",node,pin):
                raise RuntimeError("Unable to bind "+pin)
        if linked()[pin].get_editor_property("texture").get_path_name()!=tex.get_path_name():
            raise RuntimeError("Wrong linked scan texture")
    start="// Flow-aligned alluvium in the sculpted outlet"
    end="return originalGround;"
    parent=read(BASE/"shore-material.json")["shader_sha256"]
    if VERIFY:
        if sha256(current.encode()).hexdigest()!=read(WORK/"material.json")["shader_sha256"]:
            raise ValueError("Saved scan material changed")
    else:
        if APRON and (WORK/'material.json').is_file() and sha256(current.encode()).hexdigest()==read(WORK/'material.json')['shader_sha256']:
            return
        if sha256(current.encode()).hexdigest()!=parent or current.count(start)!=1:
            raise ValueError("Unexpected .34 terrain material")
        geo=read(BASE/"terrain/terrain.geometry.json")
        river,=[r for r in geo["watercourses"] if r["id"]=="central_river"]
        lo,hi,rows=station_rows(river["erosion_reach"],river["section_station_width_depth_m"])
        raw=(SCRIPTS/"pwr_scanned_riverbank.ush").read_text()
        raw=raw.replace("REACH_ROWS",",\n".join(rows)).replace("REACH_Y_LOW",str(lo)).replace("REACH_Y_HIGH",str(hi))
        if APRON:
            from apply_pwr_outlet_bank import register_shader
            raw=register_shader(raw,read(WORK/"banks.json"))
        updated=current[:current.index(start)]+raw.rstrip()+"\n"+end
        node.set_editor_property("code",updated)
        lib.recompile_material(material)
        if not asset.save_loaded_asset(material,False):
            raise RuntimeError("Could not save scanned riverbank material")
        (WORK/"material.json").write_text(json.dumps(dict(shader_sha256=sha256(updated.encode()).hexdigest(),
            parent_shader_sha256=parent,textures_sha256=texture_hashes,shared_gpu_samplers=0,scan_tile_metres=2.16),indent=2))


def plant():
    levels=ue.get_editor_subsystem(ue.LevelEditorSubsystem)
    if not levels.load_level("/Game/Levels/Halo1/Solo/LPE/LPE"):
        raise RuntimeError("Could not open the .34 native scene")
    actors=ue.get_editor_subsystem(ue.EditorActorSubsystem).get_all_level_actors()
    components={(a.get_actor_label(),c.get_name()):(a,c) for a in actors
                for c in a.get_components_by_class(ue.InstancedStaticMeshComponent)}
    plan=read(WORK/"planting.json")
    recorded=read(WORK/"placements.json") if VERIFY else {}
    for kind,key in PLANTS.items():
        actor,c=components[key]
        rows=[p for p in plan if p["kind"]==kind]
        mesh=c.get_editor_property("static_mesh")
        box=mesh.get_bounding_box()
        height=box.max.z-box.min.z
        if not 2.0<height<1000.0:
            raise ValueError((kind,height))
        if VERIFY:
            base=recorded[kind]["before"]
        else:
            base=c.get_instance_count()
            actor.modify()
            c.modify()
            transforms=[]
            for row in rows:
                t=ue.Transform()
                t.translation=ue.Vector(*row["position"])
                z=row["height_cm"]/height
                t.scale3d=ue.Vector(z*row["breadth"],z*row["breadth"],z)
                yaw=math.radians(row["yaw"])/2
                t.rotation=ue.Quat(0,0,math.sin(yaw),math.cos(yaw))
                transforms.append(t)
            c.add_instances(transforms,should_return_indices=False,world_space=True,update_navigation=False)
            recorded[kind]=dict(before=base,added=len(rows),mesh=mesh.get_path_name(),height_cm=height)
        if c.get_instance_count()!=base+len(rows):
            raise ValueError("Changed instances: "+kind)
        for i,row in enumerate(rows):
            t=c.get_instance_transform(base+i,True)
            if math.dist(row["position"],t.translation.to_tuple())>.35 or abs(t.scale3d.z*height-row["height_cm"])>.03:
                raise ValueError("Reopened plant transform differs: "+kind)
    if not VERIFY:
        if not levels.save_current_level():
            raise RuntimeError("Could not save rooted shoreline plants")
        (WORK/"placements.json").write_text(json.dumps(recorded,indent=2))
    else:
        (WORK/"editor-verified.json").write_text(json.dumps(dict(transforms_read_back=len(plan),
                   source_plan_sha256=sha256((WORK/"planting.json").read_bytes()).hexdigest())))


try:
    material()
    if APRON:
        from apply_pwr_outlet_bank import place_surface
        place_surface(WORK, VERIFY)
    plant()
except:
    (WORK/("verify-error.txt" if VERIFY else "editor-error.txt")).write_text(traceback.format_exc())
    raise
