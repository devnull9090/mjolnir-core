"""Register and reopen the .43 outlet sediment face, exposed wood and gravel mesh."""
import hashlib
import json
from pathlib import Path

import unreal as ue

FOLDER = "/Game/MJOLNIR/GrassPilot/Playable/"
MESH = "SM_PWR_CutbankRoots"
MATERIAL = "M_PWR_CutbankRoots"
LABEL = "PWR_CutbankRootToe"
WORLD = "/Game/Levels/Halo1/Solo/LPE/LPE"
COLOR = """float wood=1.-step(.2,abs(part-.5));
float3 scan=lerp(gravel,bark,wood);
float l=dot(scan,float3(.26,.56,.18));
float3 hues=clamp(scan/max(.014,l),.77,1.23);
float grain=lerp(.62,1.50,smoothstep(.018,.34,l));
float cavity=lerp(.42,1.,smoothstep(.012,.105,part));
return tint*lerp(1.,hues,.44)*grain*cavity;"""
NORMAL = """float wood=1.-step(.2,abs(part-.5));
float2 xy=lerp(mineral.xy,woodgrain.xy,wood)*lerp(.48,.29,step(.8,part));
return normalize(float3(xy,sqrt(saturate(1.-dot(xy,xy)))));"""
BOUNCE = """float wood=1.-step(.2,abs(part-.5));
float wet=step(.8,part);
float openSoil=saturate(5.7*part);
return shaded*lerp(.064+.14*openSoil+.17*wood,.16,wet)+float3(.003,.0033,.0037);"""


OCCLUSION = "return lerp(lerp(.44,.94,saturate(5.7*part)),.93,step(.3,part));"


def material_graph():
    lib = ue.MaterialEditingLibrary
    prop = ue.MaterialProperty
    asset = ue.load_asset(FOLDER + MATERIAL)
    if not asset:
        asset = ue.AssetToolsHelpers.get_asset_tools().create_asset(
            MATERIAL,FOLDER.rstrip("/"),ue.Material,ue.MaterialFactoryNew())
    lib.delete_all_material_expressions(asset)
    asset.set_editor_properties(dict(two_sided=False))

    def node(kind,x,y):
        return lib.create_material_expression(asset,kind,x,y)

    def connect(src,pin,dst,inp):
        if not lib.connect_material_expressions(src,pin,dst,inp):
            raise ValueError("Cutbank graph connection failed: " + inp)

    def output(src,prop_name):
        if not lib.connect_material_property(src,"",prop_name):
            raise ValueError("Cutbank material property connection failed")

    def custom(code,terms,count,x,y):
        expr = node(ue.MaterialExpressionCustom,x,y)
        pins = []
        for name,src,pin in terms:
            inp = ue.CustomInput()
            inp.set_editor_property("input_name",name)
            pins.append(inp)
        typ = getattr(ue.CustomMaterialOutputType,"CMOT_FLOAT"+str(count))
        expr.set_editor_properties(dict(code=code,inputs=pins,output_type=typ))
        for name,src,pin in terms:
            connect(src,pin,expr,name)
        return expr

    vc = node(ue.MaterialExpressionVertexColor,-1080,-320)
    def scan(name,normal,x,y):
        tex = ue.load_asset(FOLDER+name)
        if not tex:
            raise ValueError("Missing photographed cutbank input "+name)
        typ = ue.MaterialSamplerType
        exp = node(ue.MaterialExpressionTextureSample,x,y)
        exp.set_editor_properties(dict(texture=tex,sampler_type=typ.SAMPLERTYPE_NORMAL
                                      if normal else typ.SAMPLERTYPE_COLOR))
        return exp
    gravel = scan("T_PWR_RiverCobble_BC",False,-590,-160)
    granite = scan("T_PWR_RiverCobble_N",True,-575,290)
    bark = scan("T_PWR_SweepLitter_D",False,-575,35)
    woodgrain = scan("T_PWR_SweepLitter_N",True,-575,535)
    clr = custom(COLOR,[("gravel",gravel,"RGB"),("bark",bark,"RGB"),
                       ("tint",vc,""),("part",vc,"A")],3,-235,-175)
    norm = custom(NORMAL,[("mineral",granite,"RGB"),("woodgrain",woodgrain,"RGB"),
                          ("part",vc,"A")],3,-230,260)
    bounce = custom(BOUNCE,[("shaded",clr,""),("part",vc,"A")],3,15,150)
    occlusion = custom(OCCLUSION,[("part",vc,"A")],1,-120,660)
    rough = custom("return lerp(.91,clamp(.43+.38*scanrough,.50,.78),step(.8,part));",
                   [("scanrough",gravel,"A"),("part",vc,"A")],1,-230,-395)
    spec = node(ue.MaterialExpressionConstant,-225,525)
    spec.set_editor_property("r",.17)
    for exp,output_property in ((clr,prop.MP_BASE_COLOR),(norm,prop.MP_NORMAL),
                                (bounce,prop.MP_EMISSIVE_COLOR),(rough,prop.MP_ROUGHNESS),
                                (spec,prop.MP_SPECULAR),(occlusion,prop.MP_AMBIENT_OCCLUSION)):
        output(exp,output_property)
    lib.recompile_material(asset)
    if not ue.EditorAssetLibrary.save_loaded_asset(asset,False):
        raise RuntimeError("Saving cutbank material failed")
    return asset


def apply(work,verify=False):
    work = Path(work)/"cutbank"
    source = work/"surface.json"
    geo = json.loads(source.read_bytes())
    mesh = ue.load_asset(FOLDER+MESH)
    if verify:
        mat = ue.load_asset(FOLDER+MATERIAL)
    else:
        mat = material_graph()
        mesh = mesh or ue.MjolnirUIBuilderLibrary.create_stand_in_mesh(FOLDER+MESH+"."+MESH)
        indices = [i for f in geo["faces"] for i in f]
        coords = [ue.Vector2D(*geo["uv"][i]) for i in indices]
        built = ue.MjolnirUIBuilderLibrary.build_static_mesh(
            mesh,[ue.Vector(*p) for p in geo["positions"]],[ue.Vector(*n) for n in geo["normals"]],
            indices,coords,coords,[0]*len(geo["faces"]),[ue.Name("RiparianBank")],
            [ue.LinearColor(*c) for c in geo["colors"]],[])
        if not built:
            raise RuntimeError("Building the eroded bank mesh failed")
        mesh.set_material(0,mat)
        if not ue.EditorAssetLibrary.save_loaded_asset(mesh,False):
            raise RuntimeError("Saving the cutbank mesh failed")
    if not mesh or not mat or mesh.get_material(0)!=mat:
        raise ValueError("Missing native cutbank surface")
    level = ue.get_editor_subsystem(ue.LevelEditorSubsystem)
    editor = ue.get_editor_subsystem(ue.UnrealEditorSubsystem)
    if editor.get_editor_world().get_path_name().split(".")[0] != WORLD:
        if not level.load_level(WORLD):
            raise RuntimeError("Could not open Pelican Warfare authoring map")
    actors = ue.get_editor_subsystem(ue.EditorActorSubsystem)
    matches = [a for a in actors.get_all_level_actors() if a.get_actor_label()==LABEL]
    if not verify:
        actor = matches[0] if matches else actors.spawn_actor_from_class(
            ue.StaticMeshActor,ue.Vector(*geo["origin_cm"]))
        actor.set_actor_label(LABEL)
        actor.set_actor_location(ue.Vector(*geo["origin_cm"]),False,True)
        comp = actor.get_editor_property("static_mesh_component")
        comp.set_mobility(ue.ComponentMobility.STATIC)
        comp.set_static_mesh(mesh)
        comp.set_collision_profile_name("NoCollision")
        comp.set_collision_enabled(ue.CollisionEnabled.NO_COLLISION)
        comp.set_editor_property("generate_overlap_events",False)
        actor.set_actor_enable_collision(False)
        actor.modify()
        comp.set_editor_property("cast_shadow",True)
        if not level.save_current_level():
            raise RuntimeError("Saving the in-world cutbank failed")
        matches = [a for a in actors.get_all_level_actors() if a.get_actor_label()==LABEL]
    if len(matches)!=1:
        raise ValueError("Expected one cutbank in Pelican Warfare")
    actor = matches[0]
    comp = actor.get_editor_property("static_mesh_component")
    loc = actor.get_actor_location()
    if (not comp.get_editor_property("static_mesh") or
        comp.get_editor_property("static_mesh").get_path_name()!=mesh.get_path_name() or
        actor.get_actor_enable_collision() or
        comp.get_collision_enabled()!=ue.CollisionEnabled.NO_COLLISION or
        max(abs(a-b) for a,b in zip([loc.x,loc.y,loc.z],geo["origin_cm"])) > .05):
        raise ValueError("Cutbank state: mesh=%s, expectedMesh=%s, collision=%s, actorCollision=%s, position=%s, expected=%s" % (comp.get_editor_property("static_mesh"),mesh.get_path_name(),comp.get_collision_enabled(),actor.get_actor_enable_collision(),loc,geo["origin_cm"]))
    lib = ue.MaterialEditingLibrary
    for prop,code in ((ue.MaterialProperty.MP_BASE_COLOR,COLOR),
                      (ue.MaterialProperty.MP_NORMAL,NORMAL),(ue.MaterialProperty.MP_EMISSIVE_COLOR,BOUNCE),
                      (ue.MaterialProperty.MP_AMBIENT_OCCLUSION,OCCLUSION)):
        if lib.get_material_property_input_node(mat,prop).get_editor_property("code")!=code:
            raise ValueError("Cutbank graph differs from its authoring source")
    count = mesh.get_num_triangles(0)
    if count != len(geo["faces"]):
        raise ValueError("Cutbank triangle count changed: %d of %d"%(count,len(geo["faces"])))
    receipt = dict(asset=mesh.get_path_name(),material=mat.get_path_name(),actor=LABEL,
                   triangles=count,source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
                   native_support_sha256=hashlib.sha256((work/"support.npz").read_bytes()).hexdigest())
    (work/("editor-verified.json" if verify else "editor-built.json")).write_text(json.dumps(receipt,indent=2))
    return receipt
