"""Opt-in grass bake on a copy of LPW; never edits the source world's assets.

MJ_NATIVE_GRASS_PILOT: CPU-generated pilot.json.
MJ_NATIVE_GRASS_MODE: build (editor_cmd.ps1 -AllowRendering -StockRenderer) or verify.
Run verify in a NEW editor process: it reads saved GrassData without generating it.
"""
import json
import os
from pathlib import Path
import sys

import unreal

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT/"tools/level"))
from landscape_grass_pilot import (ASSETS as V7_ASSETS, FIELD_WORLD, CANYON_OBJECT, digest, dump,
                                   validate_config, validate_readback, archive_owned_editor_assets)

path = Path(os.environ["MJ_NATIVE_GRASS_PILOT"]).resolve()
config = json.loads(path.read_text(encoding="utf-8"))
mode = os.environ.get("MJ_NATIVE_GRASS_MODE", "build")
if mode not in ("build", "verify"):
    raise RuntimeError("MJ_NATIVE_GRASS_MODE must be build or verify")
validate_config(config,path.parent)
ASSETS = config["asset_folder"]
WORLD = config["world"]
eal = unreal.EditorAssetLibrary
les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
editor = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
assets = unreal.AssetToolsHelpers.get_asset_tools()
helper = unreal.MjolnirGrassPilotLibrary
world_folder = WORLD.rsplit("/",1)[0]


def landscape():
    candidates = [a for a in actors.get_all_level_actors() if isinstance(a,unreal.Landscape)]
    if len(candidates) != 1:
        raise RuntimeError(f"Expected one Landscape, got {len(candidates)}")
    result = candidates[0]
    world = editor.get_editor_world()
    if world.get_path_name().split(".")[0] != WORLD:
        raise RuntimeError("Refusing to edit the source world")
    position, scale = result.get_actor_location(),result.get_actor_scale3d()
    for actual,wanted in (([position.x,position.y,position.z],config["grid"]["location"]),
                          ([scale.x,scale.y,scale.z],config["grid"]["scale"])):
        if max(abs(a-b) for a,b in zip(actual,wanted)) > .001:
            raise RuntimeError("Pilot landscape transform differs from frozen grid")
    rotation=result.get_actor_rotation()
    if max(abs(rotation.pitch),abs(rotation.yaw),abs(rotation.roll)) > 1e-6:
        raise RuntimeError("Rotated landscape is not supported")
    return result


def standin(row):
    existing=unreal.load_asset(row["mesh"])
    if existing:
        return existing
    # These game paths are never cooked. Runtime resolves the actual native mesh,
    # with all of its UVs, colours, materials and Nanite data. No override is set.
    mesh=unreal.MjolnirUIBuilderLibrary.create_stand_in_mesh(row["mesh"])
    if not mesh or mesh.get_path_name() != row["mesh"]:
        raise RuntimeError("Wrong stand-in object identity")
    origin=row.get("origin",[0,0,50])
    extent=row.get("extent",[100,100,50])
    positions=[unreal.Vector(origin[0]+x*extent[0],origin[1]+y*extent[1],origin[2]+z*extent[2])
               for x in (-1,1) for y in (-1,1) for z in (-1,1)]
    faces=((0,1,3,2),(4,6,7,5),(0,4,5,1),(2,3,7,6),(0,2,6,4),(1,5,7,3))
    indices=[i for a,b,c,d in faces for i in (a,b,c,a,c,d)]
    normals=[unreal.Vector(0,0,1)]*8
    uvs=[unreal.Vector2D(0,0)]*len(indices)
    if not unreal.MjolnirUIBuilderLibrary.build_static_mesh(mesh,positions,normals,indices,uvs,uvs,
            [0]*(len(indices)//3),[unreal.Name(v) for v in row["standin_slots"]],[],[]):
        raise RuntimeError("Could not build editor-only stand-in")
    if not eal.save_loaded_asset(mesh): raise RuntimeError("Could not save stand-in")
    return mesh


def label(folder,name):
    obj=assets.create_asset(name,folder,unreal.PrimaryAssetLabel,unreal.DataAssetFactory())
    rules=obj.get_editor_property("rules")
    rules.set_editor_property("chunk_id",config["chunk"])
    rules.set_editor_property("apply_recursively",True)
    rules.set_editor_property("cook_rule",unreal.PrimaryAssetCookRule.ALWAYS_COOK)
    obj.set_editor_property("rules",rules)
    obj.set_editor_property("label_assets_in_my_directory",True)
    if not eal.save_loaded_asset(obj): raise RuntimeError("Could not save pilot chunk label")


def bind_native_material(grass):
    if not config.get("canyon_material"):
        return
    # This same-path MIC is excluded by DirectoriesToNeverCook. The installed
    # external container supplies the full native material and its shader data.
    material = unreal.load_asset(CANYON_OBJECT)
    if not material:
        package = CANYON_OBJECT.split(".")[0]
        folder, name = package.rsplit("/", 1)
        material = assets.create_asset(name, folder, unreal.MaterialInstanceConstant,
                                      unreal.MaterialInstanceConstantFactoryNew())
        parent = unreal.load_asset("/Engine/EngineMaterials/DefaultMaterial.DefaultMaterial")
        if not material or not parent:
            raise RuntimeError("Could not create external native MIC stand-in")
        unreal.MaterialEditingLibrary.set_material_instance_parent(material, parent)
        if not eal.save_loaded_asset(material): raise RuntimeError("Could not save external MIC stand-in")
    if not isinstance(material, unreal.MaterialInstanceConstant) or material.get_path_name() != CANYON_OBJECT:
        raise RuntimeError("Wrong external native MIC stand-in identity")
    varieties = grass.get_editor_property("grass_varieties")
    if len(varieties) != len(config["varieties"]): raise RuntimeError("Wrong native variety count")
    for index, row in enumerate(config["varieties"]):
        variety = varieties[index]
        variety.set_editor_property("override_materials", [material] if row["override_materials"] else [])
        # Unreal struct-array access returns a value copy, unlike a Python list
        # of references. Write the modified struct back before assigning the array.
        varieties[index] = variety
    grass.set_editor_property("grass_varieties", varieties)
    actual = variety_readback(grass)
    expected = [{"mesh": row["mesh"], "override_materials": row["override_materials"]}
                for row in config["varieties"]]
    dump(path.parent / "grass-binding.prebuild.json", {
        "config_sha256": digest(path), "actual": actual, "expected": expected})
    if actual != expected:
        raise RuntimeError("Native grass material assignment did not persist; refusing GPU bake")


def variety_readback(grass):
    return [{"mesh": variety.get_editor_property("grass_mesh").get_path_name(),
             "override_materials": [material.get_path_name() if material else "None"
                                    for material in variety.get_editor_property("override_materials")]}
            for variety in grass.get_editor_property("grass_varieties")]


def understory(creating):
    record=config.get("understory")
    if not record: return
    folder=path.parent
    spec_path=folder/record["file"]
    if digest(spec_path)!=record["sha256"]: raise RuntimeError("Understory specification changed")
    spec=json.loads(spec_path.read_text())
    binary=folder/spec["file"]
    groups=spec["groups"]
    if digest(binary)!=spec["binary_sha256"] or any(
            digest(str(binary)+f".xf{i}")!=seal for i,seal in enumerate(spec["exact_sidecars"],1)):
        raise RuntimeError("Understory PCG transforms changed")
    actor_name="PWR_FieldUnderstory"
    if creating:
        for row in groups: standin(row)
        count=unreal.MjolnirUIBuilderLibrary.bake_foliage(
            editor.get_editor_world(),str(binary),actor_name,[r["mesh"] for r in groups],
            [r["bands"] for r in groups],[unreal.Vector2D(*r["cull"]) for r in groups],
            [34+int(r["shadow"]) for r in groups])
        if count!=spec["count"]: raise RuntimeError("Understory bake omitted PCG instances")
    target,=[a for a in actors.get_all_level_actors() if a.get_name()==actor_name]
    components=target.get_components_by_class(unreal.HierarchicalInstancedStaticMeshComponent)
    readback={}
    for comp in components:
        mesh=comp.get_editor_property("static_mesh").get_path_name()
        readback[mesh]={"count":comp.get_instance_count(), "cull":[comp.get_editor_property(k) for k in
                        ("instance_start_cull_distance","instance_end_cull_distance")]}
        if comp.get_collision_enabled()!=unreal.CollisionEnabled.NO_COLLISION:
            raise RuntimeError("Groundcover must not obstruct vehicles")
    if readback!={r["mesh"]:{"count":r["count"],"cull":r["cull"]} for r in groups}:
        raise RuntimeError("World HISM instances or cull ranges differ from the PCG bake")
    dump(folder/("understory-built.json" if creating else "understory-saved.json"),readback)


def cliff_materials(creating):
    """Keep native exterior HISM shading on the same owned parent as the vista."""
    old="/Game/MJOLNIR/CETrial/M_CE_PWRRock.M_CE_PWRRock"
    new="/Game/MJOLNIR/World/PWR/Surfaces/M_CE_PWRRock.M_CE_PWRRock"
    parent=unreal.load_asset(new)
    if not parent: raise RuntimeError("Cook the map-owned rock shader before authoring LPE")
    copied={}
    affected={}
    for actor in actors.get_all_level_actors():
        for component in actor.get_components_by_class(unreal.HierarchicalInstancedStaticMeshComponent):
            for i in range(component.get_num_materials()):
                mic=component.get_material(i)
                if not isinstance(mic,unreal.MaterialInstanceConstant): continue
                master=mic.get_editor_property("parent")
                if not master: continue
                if master.get_path_name()==old:
                    if not creating: raise RuntimeError("Saved HISM cliff retained a developer shader path")
                    source=mic.get_path_name()
                    if source not in copied:
                        clone=eal.duplicate_asset(source,ASSETS+"/"+mic.get_name())
                        if not clone: raise RuntimeError("Could not duplicate exterior rock MIC")
                        unreal.MaterialEditingLibrary.set_material_instance_parent(clone,parent)
                        unreal.MaterialEditingLibrary.update_material_instance(clone)
                        if not eal.save_loaded_asset(clone): raise RuntimeError("Could not save exterior rock MIC")
                        copied[source]=clone
                    mic=copied[source]
                    component.set_material(i,mic)
                if mic.get_editor_property("parent").get_path_name()==new:
                    affected[mic.get_path_name()]=affected.get(mic.get_path_name(),0)+component.get_instance_count()
    dump(path.parent/("cliff-materials-built.json" if creating else "cliff-materials-saved.json"),affected)


if mode == "build":
    # A scratch map releases only our prior pilot before deleting its exact folders.
    scratch="/Game/__MJOLNIR_GrassPilotScratch"
    ok=les.load_level(scratch) if eal.does_asset_exist(scratch) else les.new_level(scratch)
    if not ok: raise RuntimeError("Could not enter grass pilot scratch map")
    unreal.AssetRegistryHelpers.get_asset_registry().scan_paths_synchronous([world_folder,ASSETS],True)
    for folder in (world_folder,ASSETS):
        if eal.does_directory_exist(folder) and not eal.delete_directory(folder):
            raise RuntimeError("Could not clear owned pilot folder: "+folder)
    if not les.new_level_from_template(WORLD,config["source_world"]):
        raise RuntimeError("Could not clone source landscape world")
    land=landscape()
    source_material=land.get_editor_property("landscape_material")
    if not isinstance(source_material,unreal.Material):
        raise RuntimeError("Expected LPW's master material; refusing to flatten an instance")
    source_material_path=source_material.get_path_name()
    material=eal.duplicate_asset(source_material_path,ASSETS+"/M_PWRPilot")
    if not isinstance(material,unreal.Material): raise RuntimeError("Could not clone landscape master")
    if config.get("biome_color"):
        import runpy
        runpy.run_path(str(Path(__file__).with_name("pwr_biome_material.py")))["attach"](material,ASSETS,config["biome_color"],path.parent)
    task=unreal.AssetImportTask()
    task.set_editor_property("filename",str(path.parent/config["texture"]["file"]))
    task.set_editor_property("destination_path",ASSETS)
    task.set_editor_property("destination_name","T_PWRPilotDensity")
    task.set_editor_property("automated",True)
    task.set_editor_property("save",False)
    assets.import_asset_tasks([task])
    texture=unreal.load_asset(ASSETS+"/T_PWRPilotDensity")
    if not texture: raise RuntimeError("Density texture import failed")
    texture.set_editor_property("srgb",False)
    texture.set_editor_property("compression_settings",unreal.TextureCompressionSettings.TC_VECTOR_DISPLACEMENTMAP)
    texture.set_editor_property("never_stream",True)
    texture.set_editor_property("mip_gen_settings",unreal.TextureMipGenSettings.TMGS_NO_MIPMAPS)
    texture.set_editor_property("filter",unreal.TextureFilter.TF_NEAREST)
    texture.set_editor_property("address_x",unreal.TextureAddress.TA_CLAMP)
    texture.set_editor_property("address_y",unreal.TextureAddress.TA_CLAMP)
    rows=config["varieties"]
    grass=helper.create_grass_type(ASSETS+"/GT_PWRPilot",[standin(r) for r in rows],
        [r["density_per_100m2"] for r in rows],[unreal.Vector2D(*r["scale"]) for r in rows],*config["cull_cm"])
    if not grass: raise RuntimeError("Native GrassType construction failed")
    bind_native_material(grass)
    if not helper.attach_grass_output(material,texture,grass,
            unreal.Vector2D(*config["grid"]["location"][:2]),
            unreal.Vector2D(*config["grid"]["scale"][:2]),config["grid"]["size"]):
        raise RuntimeError("LandscapeGrassOutput attachment failed")
    land.set_editor_property("landscape_material",material)
    land.set_editor_property("landscape_hole_material",material)
    for asset in (texture,grass,material):
        if not eal.save_loaded_asset(asset): raise RuntimeError("Pilot asset save failed")
    unreal.SystemLibrary.execute_console_command(editor.get_editor_world(),"Log LogGrass Verbose")
    readback=json.loads(helper.read_grass_data(land,grass,True))
    readback["varieties"] = variety_readback(grass)
    # Preserve native evidence even if strict validation aborts before saving.
    dump(path.parent/"grass-build.raw.json",readback)
    result=validate_readback(config,path.parent,readback)
    if WORLD==FIELD_WORLD:
        understory(True)
        cliff_materials(True)
    if not les.save_current_level(): raise RuntimeError("Pilot world save failed")
    label(world_folder,"PAL_PWRGrassPilotWorld")
    label(ASSETS,"PAL_PWRGrassPilotAssets")
    if WORLD != FIELD_WORLD and config.get("canyon_material") and eal.does_directory_exist(V7_ASSETS):
        # The new LPG world, V8 material and grass buffers are saved and verified
        # above. Archive only our superseded editor assets before removing their
        # AlwaysCook residue; frozen V7 cooked packages and QA remain untouched.
        content = Path(unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_content_dir())).resolve()
        if content != (ROOT / "Unreal/MJOLNIRMaterials/Content").resolve():
            raise RuntimeError("Refusing to retire grass assets from another editor project")
        retired = content / V7_ASSETS.removeprefix("/Game/")
        archive_owned_editor_assets(retired, path.parent / "retired-editor-PWRV7")
        if not eal.delete_directory(V7_ASSETS):
            raise RuntimeError("Could not retire archived V7 editor grass assets")
    readback["source_material"]=source_material_path
else:
    # A distinct invocation is essential: this reads serialized native buffers,
    # and deliberately never calls BuildGrassMaps or saves any level/asset.
    if not les.load_level(WORLD): raise RuntimeError("Saved pilot world missing")
    land=landscape()
    grass=unreal.load_asset(ASSETS+"/GT_PWRPilot")
    if not grass: raise RuntimeError("Saved pilot GrassType missing")
    readback=json.loads(helper.read_grass_data(land,grass,False))
    readback["varieties"] = variety_readback(grass)
    dump(path.parent/"grass-saved.raw.json",readback)
    result=validate_readback(config,path.parent,readback,require_saved=True)
    if WORLD==FIELD_WORLD:
        understory(False)
        cliff_materials(False)

readback["config_sha256"]=digest(path)
readback["validation"]=result
dump(path.parent/("grass-build.readback.json" if mode=="build" else "grass-saved.readback.json"),readback)
unreal.log("MJOLNIR native grass "+mode+" verified: "+json.dumps(result))
