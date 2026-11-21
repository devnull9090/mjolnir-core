"""Build and verify the two-stage headwater spring in the native playable level."""
from pathlib import Path
import hashlib
import json
import unreal as ue

FOLDER = "/Game/MJOLNIR/GrassPilot/Playable/"
MESH = "SM_PWR_SpringCascade"
MATERIAL = "M_PWR_SpringCascade"
BEDROCK = FOLDER+"MI_PWR_ExteriorCliffs_9c8b739f48f3"
LABEL = "PWR_SpringCascade"
WORLD = "/Game/Levels/Halo1/Solo/LPE/LPE"

# UV.x spans the wet channel. UV.y is travelled metres, so ripples travel
# downstream at the same rate through a narrow throat and the widening apron.
SHADER = """
struct WaterNoise {
    float hash(float2 p) {
        float3 h = frac(float3(p.xyx)*.1031);
        h += dot(h,h.yzx+33.33);
        return frac((h.x+h.y)*h.z);
    }
    float value(float2 p) {
        float2 i = floor(p);
        float2 f = frac(p); f = f*f*(3.-2.*f);
        return lerp(lerp(hash(i),hash(i+float2(1,0)),f.x),
                    lerp(hash(i+float2(0,1)),hash(i+1),f.x),f.y);
    }
};
WaterNoise N;
float u = UV.x, s = UV.y, t = FlowTime;
float fall = Region.r, impact = Region.g, tail = Region.b;
float wetEdge = saturate(2.*min(u,1.-u));
float nearDetail = 1.-smoothstep(2100.,13500.,ViewDepth);
float braid = N.value(float2(u*7.15+.25*sin(.64*s),s*.46-t*.80));
float flank = N.value(float2(u*5.7,s*.59-t*.91+11.));
float filaments = N.value(float2(u*44.+3.9*braid,s*1.29-t*2.62));
float micro = N.value(float2(u*138.+filaments*4.,s*3.41-t*6.7));
float roll = sin(s*6.8-t*8.4+u*5.1+braid*2.8);
float strand = smoothstep(.34,.70,.40*braid+.42*filaments+.18*micro);
float rib = .5+.5*cos(25.*u+2.35*flank+.77*sin(s*.94-t*.81));
float lower = smoothstep(8.4,13.2,s);
float sill = pow(saturate(fall),lerp(.74,.53,lower));
float whiteFall = sill*saturate(.15+.12*lower+(.54+.11*lower)*strand+.25*pow(rib,2.45)*filaments);
float boil = N.value(float2(u*26.+1.87*flank,s*2.75-t*2.17));
float cellular = .69*boil+.31*micro;
float lace = 1.-smoothstep(.021,.12,abs(cellular-.51));
float toe = impact*(.14+.63*lace+.14*strand);
float source = .10*smoothstep(.64,.84,filaments);
float froth = saturate(max(max(whiteFall,toe),source)+.08*strand*wetEdge);
float deposit = 1.-smoothstep(17.8,22.8,s);
float apron = deposit*(.18+.55*lace)*(.54+.46*strand);
froth = lerp(froth,apron,tail);
float3 clear = lerp(float3(.041,.083,.092),float3(.096,.217,.231),.30+.61*braid);
float3 entrained = lerp(float3(.39,.50,.53),float3(.78,.85,.88),.60*strand+.26*lace);
float3 body = lerp(clear,entrained,smoothstep(.055,.86,froth));
float edgeCut = (.021+.060*flank+.028*strand)*lerp(1.,2.02,tail);
float startWet = smoothstep(-1.8,-.15,s);
float volumeCut = .22+.16*flank+.053*micro;
float cover = saturate((wetEdge-edgeCut)*13.)*smoothstep(volumeCut-.078,volumeCut+.078,Volume)*startWet;
float lakeCoverage = saturate(.83*lace+.32*strand+.19*boil-.15);
Coverage = cover*lerp(1.,lakeCoverage*deposit,tail);
Rough = lerp(.29,.54,froth);
// Thin aerated water transmits sky light even on the shaded face of a lip.
// Keep the calm lake contact free of this extra scattering.
Scatter = (float3(.006,.011,.014)+froth*float3(.025,.032,.037))*
          (.38+.62*sill)*(1.-tail);
float tilt = (.30*(filaments-.5)+.18*(micro-.5)*nearDetail)*(1.+.5*fall);
TangentNormal = normalize(float3(tilt,.07*roll+.21*(boil-.5)*impact,1.));
return body;
"""


def connect(art):
    lib=ue.MaterialEditingLibrary
    art.set_editor_properties(dict(two_sided=True,blend_mode=ue.BlendMode.BLEND_MASKED,opacity_mask_clip_value=.38))
    lib.delete_all_material_expressions(art)
    node=lib.create_material_expression(art,ue.MaterialExpressionCustom,-245,15)
    ty=ue.CustomMaterialOutputType
    node.set_editor_properties(dict(code=SHADER,output_type=ty.CMOT_FLOAT3))
    inputs=[]
    for name in ("UV","FlowTime","Region","ViewDepth","Volume"):
        pin=ue.CustomInput()
        pin.set_editor_property("input_name",name)
        inputs.append(pin)
    node.set_editor_property("inputs",inputs)
    outputs=[]
    for name,out in (("Coverage",ty.CMOT_FLOAT1),("Rough",ty.CMOT_FLOAT1),("TangentNormal",ty.CMOT_FLOAT3),
                      ("Scatter",ty.CMOT_FLOAT3)):
        pin=ue.CustomOutput()
        pin.set_editor_properties(dict(output_name=name,output_type=out))
        outputs.append(pin)
    node.set_editor_property("additional_outputs",outputs)
    for i,(name,cls) in enumerate((("UV",ue.MaterialExpressionTextureCoordinate),
            ("FlowTime",ue.MaterialExpressionTime),("Region",ue.MaterialExpressionVertexColor),
            ("ViewDepth",ue.MaterialExpressionPixelDepth))):
        expr=lib.create_material_expression(art,cls,-725,-165+i*155)
        assert lib.connect_material_expressions(expr,"",node,name)
        if name=="Region":
            assert lib.connect_material_expressions(expr,"A",node,"Volume")
    prop=ue.MaterialProperty
    for name,dest in (("",prop.MP_BASE_COLOR),("Coverage",prop.MP_OPACITY_MASK),
            ("Rough",prop.MP_ROUGHNESS),("TangentNormal",prop.MP_NORMAL),("Scatter",prop.MP_EMISSIVE_COLOR)):
        assert lib.connect_material_property(node,name,dest)
    spec=lib.create_material_expression(art,ue.MaterialExpressionConstant,-245,430)
    spec.set_editor_property("r",.27)
    assert lib.connect_material_property(spec,"",prop.MP_SPECULAR)
    lib.recompile_material(art)


def apply(work,verify=False):
    work=Path(work)
    art=json.loads((work/"surface.json").read_text())
    assets=ue.EditorAssetLibrary
    levels=ue.get_editor_subsystem(ue.LevelEditorSubsystem)
    actors=ue.get_editor_subsystem(ue.EditorActorSubsystem)
    editor=ue.get_editor_subsystem(ue.UnrealEditorSubsystem)
    if editor.get_editor_world().get_path_name().split(".")[0]!=WORLD:
        assert levels.load_level(WORLD)
    mesh=ue.load_asset(FOLDER+MESH)
    mat=ue.load_asset(FOLDER+MATERIAL)
    rock=ue.load_asset(BEDROCK)
    if not rock:
        raise RuntimeError("The registered PWR cliff material is missing")
    if not verify:
        mat=mat or ue.AssetToolsHelpers.get_asset_tools().create_asset(
            MATERIAL,FOLDER.rstrip("/"),ue.Material,ue.MaterialFactoryNew())
        connect(mat)
        assert assets.save_loaded_asset(mat,False)
        mesh=mesh or ue.MjolnirUIBuilderLibrary.create_stand_in_mesh(FOLDER+MESH+"."+MESH)
        indices=[i for f in art["faces"] for i in f]
        uvs=[ue.Vector2D(*art["uv"][i]) for i in indices]
        assert ue.MjolnirUIBuilderLibrary.build_static_mesh(mesh,
            [ue.Vector(*p) for p in art["positions"]],[ue.Vector(*n) for n in art["normals"]],
            indices,uvs,uvs,art["sections"],[ue.Name("Flow"),ue.Name("WetBedrock")],
            [ue.LinearColor(*c) for c in art["colors"]],[])
        mesh.set_material(0,mat)
        mesh.set_material(1,rock)
        assert assets.save_loaded_asset(mesh,False)
    if not mesh or not mat or mesh.get_material(0)!=mat or mesh.get_material(1)!=rock:
        raise RuntimeError("Missing cascade asset or material")
    placed=[a for a in actors.get_all_level_actors() if a.get_actor_label()==LABEL]
    if len(placed)>1:
        raise RuntimeError("Duplicate spring actor")
    if not verify:
        actor=placed[0] if placed else actors.spawn_actor_from_class(ue.StaticMeshActor,ue.Vector(*art["origin_cm"]))
        actor.set_actor_label(LABEL)
        actor.set_actor_location(ue.Vector(*art["origin_cm"]),False,True)
        comp=actor.get_editor_property("static_mesh_component")
        comp.set_mobility(ue.ComponentMobility.STATIC)
        comp.set_static_mesh(mesh)
        actor.set_actor_enable_collision(False)
        comp.set_collision_profile_name("NoCollision")
        comp.set_editor_property("generate_overlap_events",False)
        comp.set_collision_enabled(ue.CollisionEnabled.NO_COLLISION)
        comp.set_editor_property("cast_shadow",False)
        assert levels.save_current_level()
        placed=[a for a in actors.get_all_level_actors() if a.get_actor_label()==LABEL]
    if len(placed)!=1:
        raise RuntimeError("Spring actor missing from playable lake")
    comp=placed[0].get_editor_property("static_mesh_component")
    attached=comp.get_editor_property("static_mesh")
    values=dict(mesh=attached.get_path_name() if attached else None, expected=mesh.get_path_name(), bedrock_material=mesh.get_material(1).get_path_name(),
                collision=str(comp.get_collision_enabled()),profile=str(comp.get_collision_profile_name()),
                actor_collision=placed[0].get_actor_enable_collision(),triangles=mesh.get_num_triangles(0))
    ue.log("PWR spring native readback: "+json.dumps(values))
    if (values["mesh"]!=values["expected"] or values["actor_collision"] or
            comp.get_collision_enabled()!=ue.CollisionEnabled.NO_COLLISION or values["triangles"]!=len(art["faces"])):
        raise RuntimeError("Wrong spring state: "+str(values))
    expected=art["origin_cm"]
    pos=placed[0].get_actor_location()
    if max(abs(a-b) for a,b in zip(expected,[pos.x,pos.y,pos.z]))>.01:
        raise RuntimeError("Spring surface moved relative to the surveyed rocks")
    graph=ue.MaterialEditingLibrary.get_material_property_input_node(mat,ue.MaterialProperty.MP_BASE_COLOR)
    if not graph or graph.get_editor_property("code")!=SHADER:
        raise RuntimeError("Saved spring material differs from its native flow shader")
    proof=dict(actor=placed[0].get_path_name(),mesh=mesh.get_path_name(),material=mat.get_path_name(),
               triangles=len(art["faces"]),surface_sha256=hashlib.sha256((work/"surface.json").read_bytes()).hexdigest(),
               shader_sha256=hashlib.sha256(SHADER.encode()).hexdigest(),collision=False,state=values)
    (work/("surface-verified.json" if verify else "surface-built.json")).write_text(json.dumps(proof,indent=2))
    return proof

