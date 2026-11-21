"""Apply the Southwest-only material to the .14 Unreal editor clone."""
import hashlib
import json
import math
import os
from pathlib import Path
import sys

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))
import apply_pwr_alpine_roadbed as base
from pwr_asphalt_source import shared_corners, wearing_course

ART = Path(os.environ.get("PWR_SWEEP_EARTH", base.ROOT/"out/pwr/sweep-polish/earth"))
DETAIL = "T_PWR_SweepFloorDetail"
START, END = "// Begin PWR Southwest forest floor", "// End PWR Southwest forest floor"
OLD = "[branch] if (alpineField.r>.002)"
PAVED = "[branch] if (alpineFar && alpineField.r>.002)"
SWEEP_GAINS = {
    "SweepDirtGain": "PWRSweepDirtGain",
    "SweepTrackGain": "PWRSweepTrackGain",
    "SweepGravelGain": "PWRSweepGravelGain",
}


def wash_constants(fragment, survey):
    frame=survey["finish_frame"]
    origin, axis = frame["centre"], frame["direction"]
    sites=sorted(survey["wash_frames"],key=lambda site: sum((a-b)*v for a,b,v in zip(site["centre_m"],origin,axis)))
    def literal(number):
        return f"{float(number):.7f}"
    def vector(*values):
        return f"float{len(values)}("+",".join(map(literal,values))+")"
    station=[116.+sum((a-b)*v for a,b,v in zip(site["centre_m"],origin,axis)) for site in sites]
    if any(max(abs(a-b) for a,b in zip(site["direction"],axis)) > .00001 for site in sites):
        raise ValueError("The wet shelves require independent axes on this section of route")
    # Binary threshold tree; select one native local bowl per wet pixel.
    def select(left,right):
        if left==right:
            return str(left)
        j=(left+right)//2
        return f"(localStation<{literal((station[j]+station[j+1])*.5)}?{select(left,j)}:{select(j+1,right)})"
    terms={
        "WASH_FRAME_ORIGIN": vector(*origin), "WASH_FRAME_AXIS": vector(*axis),
        "WASH_COUNT": str(len(sites)), "WASH_HERO": str(sites.index(survey["wash_frames"][0])),
        "WASH_CENTRES": ", ".join(vector(*w["centre_m"],*w["half_axes_m"]) for w in sites),
        "WASH_BANKS": ", ".join(vector(w["shear"],w["shelf"],w["strength"]) for w in sites),
        "WASH_SELECT": select(0,len(sites)-1),
    }
    for name,value in terms.items():
        fragment=fragment.replace(name,value)
    return fragment


def gated_verge(fragment,spec):
    clip=spec["grade_clip"]
    rows=clip["wheel_edges"]
    # Compile the fitted lanes as immutable shader constants. Two table
    # entries interpolate each 2 m crossing, independent of forest/duff color.
    values=", ".join("float2(%.5f,%.5f)"%tuple(row) for row in rows)
    body=(SCRIPTS/"pwr_southwest_verge_clip.ush").read_text()
    body=body.replace("GRADE_EDGE_COUNT",str(len(rows))).replace("GRADE_EDGE_ROWS",values)
    body=body.replace("GRADE_LAST_PAIR",str(len(rows)-2))
    fragment=fragment.replace("    float degree=finishScope*deposit;",body+
        "    float degree=finishScope*gradeClip*deposit*(1-smoothstep(.16,.42,survey.y));")
    old="float vergeBand=finishScope*trackEdge*smoothstep(.22,.57,survey.y)*(1-smoothstep(.78,.96,survey.y));"
    new="""float bankCore=(1-smoothstep(.080,.245,survey.x))*smoothstep(.31,.58,survey.y)*(1-smoothstep(.75,.89,survey.y));
    float vergeBand=finishScope*gradeClip*smoothstep(.66,1.29,outsideWheel)*bankCore;"""
    if fragment.count(old)!=1:
        raise ValueError("The .22 native shoulder mixing point changed")
    return fragment.replace("    float trackEdge=1-smoothstep(.46,.75,survey.x);\n","").replace(old,new)


def worn_earth_finish(revision,survey=None):
    # Keep .18's reviewed organic surface and individual wet hollows while
    # giving wheel compaction and mineral deposits an independent cross-section.
    previous = (SCRIPTS / "pwr_southwest_bend_finish.ush").read_text()
    organic = previous[previous.index("    float moss="):previous.index("    float2 gravelN=")]
    wet = previous[previous.index("    float damp=0"):]
    wet = wet.replace("alpineField.r);", "finishWeight);")
    normal = """    float2 gravelN=mul(mineralN,mineralRot);
    float2 litterN=mul(litter.ba*2-1,pineRot);
    float2 groundN=lerp(soilNormal*.62,soilNormal*.24,compact);
    float2 n=lerp(groundN,gravelN*(.87+.38*highFace),max(stoneFraction,.53*bearing))+rutSlope;
    n=lerp(n,litterN*.68,duff);
"""
    road = (SCRIPTS / "pwr_southwest_worn_earth.ush").read_text()
    if revision >= 20:
        packed = (SCRIPTS / "pwr_southwest_bend_tracks.ush").read_text()
        start, end = road.index("    float3 packed="), road.index("    float3 matrix=")
        road = road[:start] + packed + road[end:]
        # The packed track carries fine mineral roughness. Keep the larger
        # protruding faces in the centre, even around the sunlit apex.
        normal = normal.replace("soilNormal*.24,compact", "(soilNormal*.39+gravelN*.12),compact")
        wet = wet.replace("smoothstep(.77,.95,stone.a)",
                          "smoothstep(.61,.90,stone.a)*(.47+.53*scattered)")
    if revision >= 21:
        interstices = (SCRIPTS/"pwr_southwest_wash_interstices.ush").read_text()
        road = road.replace("    float stoneFraction=", interstices+"    float stoneFraction=")
        road = road.replace("    float3 mineralFace","    stoneFraction*=1-.96*bareLens*deposit;\n    float3 mineralFace")
        organic += (SCRIPTS/"pwr_southwest_wash_verges.ush").read_text()
        normal += "    n=lerp(n,lerp(litterN*.55,gravelN*.86,chipTip),vergeStain*.78);\n"
        wet = (SCRIPTS/"pwr_southwest_shallow_wash.ush").read_text()
        if revision>=22:
            detail=(SCRIPTS/"pwr_southwest_drive_detail.ush").read_text()
            road=road.replace("    float stoneFraction=",detail+"    float stoneFraction=")
            road=road.replace("1-.96*bareLens*deposit;", "(1-.96*bareLens*deposit)*(1-.83*washGap);")
            organic+=(SCRIPTS/"pwr_southwest_embedded_verge.ush").read_text()
            normal=normal.replace("(soilNormal*.39+gravelN*.12)","(soilNormal*.64+gravelN*.15)")
            normal+="    n=lerp(n,gravelN*(.72+.3*highFace),max(inset*.69,vergeBand*scan.r*.74));\n"
            # A thin dark mud margin is visible along the silty bank; larger
            # exposed stones protrude at its waterline. The hero core has a
            # native sky response between .20's flat blue and .21's dark mud.
            wet=wet.replace("        float depth=", "        float chosenGlint=bowlIndex==WASH_HERO ? 1. : 0.;\n        float depth=")
            wet=wet.replace("        color=lerp(color,color*float3", """        float mudLip=shelf*damp*smoothstep(.41,.85,basin)*(1-smoothstep(1.,1.65,basin));
        color=lerp(color,exposed*float3(.70,.65,.61),mudLip*(1-.84*scan.r));
        pool=saturate(pool*(1+.25*chosenGlint))*(1-.42*scan.r);
        color=lerp(color,color*float3""")
            wet=wet.replace("        color=lerp(color,lerp(color*.86,reflectedSky,.54),pool);",
                """        reflectedSky=lerp(reflectedSky,float3(.052,.082,.125),chosenGlint*.85);
        color=lerp(color,lerp(color*.84,reflectedSky,.55+.17*chosenGlint),pool);""")
        if revision>=23:
            organic=gated_verge(organic,survey)
        if revision>=24:
            grit=(SCRIPTS/"pwr_southwest_near_puddle_grit.ush").read_text()
            basin=survey["near_puddle_grit"]
            anchor="float2(%.6f,%.6f)"%tuple(basin["centre_m"])
            grit=grit.replace("PUDDLE_ORIGIN",anchor)
            boundary="    n*=rsqrt(max(1.,dot(n,n)*1.025));"
            if wet.count(boundary)!=1:
                raise ValueError("Missing post-water terrain boundary")
            wet=wet.replace(boundary,grit+boundary)
        if revision>=25:
            # Full forest has no compaction, signed mineral/duff pocket or
            # operative wet field. The road-only grit lookup is redundant there.
            road=road.replace("[branch] if (finishScope>.001)","[branch] if (finishScope>.001 && forestMix<.999)")
            lower=organic.index("    float moss=");upper=organic.index("    float3 humus=",lower)
            organic=organic[:lower]+"    float moss=sampleMoss, pine=samplePine;\n"+organic[upper:]
            transition_name="pwr_southwest_forest_duff.ush" if revision>=26 else "pwr_southwest_ground_transition.ush"
            transition=(SCRIPTS/transition_name).read_text()
            if revision>=28:
                transition=shared_corners(transition,"        float4 ids=","        float localMoisture=","cell","corners")
            organic=organic.replace("    float contact=",transition+"    float contact=")
            organic=organic.replace("    color=lerp(color,forest,duff);",
                "    duff=saturate(duff+forestMix*fringe*(.17*(standMoisture-.5)+.08*(litter.r-.44)));\n    color=lerp(color,forest,duff);")
            normal=normal.replace("float2 litterN=mul(litter.ba*2-1,pineRot);","float2 litterN=litterWorld;")
        return wash_constants(road+organic+normal+wet,survey)
    return road+organic+normal+wet


def compose(code,revision=15,survey=None):
    code = code.replace("\r\n","\n")
    road_start,road_end="// Begin PWR weathered asphalt","// End PWR weathered asphalt"
    if road_start in code:
        code=base.without_block(code,road_start,road_end)
    if START in code:
        code = base.without_block(code, START, END).replace(PAVED,OLD)
    source = json.loads((base.ROOT/"out/pwr/alpine-target/earth/editor-verified.json").read_text())
    if base.sha(code.encode()) != source["shader_sha256"] or code.count(OLD)!=1:
        raise ValueError("The material is not derived from the .14 terrain master")
    fragment = (SCRIPTS/"pwr_southwest_floor.ush").read_text().strip()
    if revision >= 16:
        # Both surfaces use the same four stock/packed samples and UV derivatives.
        # Keep the pixel inputs identical when presenting the refined distribution.
        boundary = "    float lum = dot(soil,float3(.2126,.7152,.0722));"
        if fragment.count(boundary)!=1:
            raise ValueError("Missing boundary after source textures")
        if revision >= 19:
            finish = worn_earth_finish(revision,survey)
        else:
            name = {16:"pwr_southwest_mineral_finish.ush",17:"pwr_southwest_track_finish.ush",
                    18:"pwr_southwest_bend_finish.ush"}[revision]
            finish = (SCRIPTS/name).read_text()
        if revision>=22:
            # The first full-size scan stays byte-identical. The organic
            # material occupies 768x1008 pixels within its own wrapped border.
            a=fragment.index("    float4 litter ="); b=fragment.index("    float3 soil =",a)
            organicUV=fragment[a:b].replace("mul(pad,", "mul(organicPad,")
            fragment=fragment[:a]+"    float2x2 organicPad=float2x2(768./2048.,0,0,1008./1024.);\n"+organicUV+fragment[b:]
        if revision>=25:
            lower=fragment.index("    float2x2 organicPad=");upper=fragment.index("    float3 soil =",lower)
            mosaic=(SCRIPTS/"pwr_southwest_forest_mosaic.ush").read_text()
            if revision>=26:
                # Keep one physical needle scale and favour a single scan where triangles overlap.
                if revision == 26:
                    mosaic=mosaic.replace("1./(2.40*(.77+.57*h.y))", "1./2.40")
                else:
                    # Keep a full scan from repeating within one moss or litter patch.
                    mosaic=mosaic.replace("1./(2.40*(.77+.57*h.y))", "1./(2.40*(.875+.25*h.y))")
                    mosaic=mosaic.replace("1.1547005*m.y)/2.67", "1.1547005*m.y)/1.76")
                mosaic=mosaic.replace("weights/=max", "weights*=weights;\n        weights/=max")
                # Preserve the measured mean of the organic atlas as its features filter out.
                mosaic=mosaic.replace("float4(.44,.26,.5,.5)", "float4(.588,.345,.5,.5)")
                mosaic=mosaic.replace("float2(.34,.23)", "float2(.181,.227)")
                if revision>=28:
                    mosaic=shared_corners(mosaic,"        float4 ids=","        standMoisture=","k","t")
            fragment=fragment[:lower]+mosaic+fragment[upper:]
        fragment = fragment.split(boundary)[0] + finish.strip("\r\n")
    if revision>=25:
        asphalt=wearing_course(revision)
        if not asphalt.startswith(road_start) or not asphalt.endswith(road_end):
            raise ValueError("Incomplete final road branch")
        fragment+="\n"+asphalt
    return code.replace(OLD,PAVED).replace(base.END,fragment+"\n"+base.END)


def main():
    import unreal as ue
    verify = os.environ.get("PWR_SWEEP_EARTH_MODE") == "verify"
    spec = json.loads((ART/"roadbed.json").read_text())
    lib = ue.MaterialEditingLibrary
    assets = ue.EditorAssetLibrary
    mat = ue.load_asset(base.MATERIAL)
    node = lib.get_material_property_input_node(mat,ue.MaterialProperty.MP_BASE_COLOR)
    revision = int(spec.get("revision",15))
    if revision < 15:
        raise ValueError("Unknown physical road surface")
    expected_gains = {name: 1.0 for name in SWEEP_GAINS.values()}
    if "material_gains" in spec:
        selected = spec["material_gains"]
        if (set(selected) != set(expected_gains) or
                any(not isinstance(v,(float,int)) or not math.isfinite(v) or v <= 0 for v in selected.values())):
            raise ValueError("Supply a complete, positive, finite set of native terrain gains")
        if revision < 20 and selected != expected_gains:
            raise ValueError("The archived road revisions have fixed material gains")
        expected_gains.update(selected)
    code = compose(node.get_editor_property("code"),revision,spec)
    lossless = ue.TextureCompressionSettings.TC_VECTOR_DISPLACEMENTMAP
    texture_specs = [(base.LEAF, "file", "sha256", [1024,512], lossless),
                     (DETAIL, "detail_file", "detail_sha256", [2048,1024],
                      lossless if revision>=17 else ue.TextureCompressionSettings.TC_BC7)]
    textures = {}
    for name,key,digest,size,compression in texture_specs:
        path = ART/spec[key]
        if hashlib.sha256(path.read_bytes()).hexdigest()!=spec[digest]:
            raise ValueError("Source art checksum differs: "+name)
        if not verify and revision < 23:
            task=ue.AssetImportTask()
            task.set_editor_properties(dict(filename=str(path),destination_path=base.FOLDER,destination_name=name,
                                            automated=True,replace_existing=True,replace_existing_settings=False,save=False))
            ue.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])
        tex=ue.load_asset(base.FOLDER+"/"+name)
        if not tex:
            raise ValueError("Missing physical texture: "+name)
        gpu_size = [tex.blueprint_get_size_x(),tex.blueprint_get_size_y()]
        dimensions = assets.find_asset_data(tex.get_path_name()).get_tag_value("Dimensions")
        if gpu_size != size and str(dimensions).lower().replace(" ","") != f"{size[0]}x{size[1]}":
            raise ValueError(f"{name} requires {size}, resource reports {gpu_size}, registry {dimensions}")
        settings=dict(srgb=False,compression_settings=compression,compression_no_alpha=False,
                      mip_gen_settings=ue.TextureMipGenSettings.TMGS_SIMPLE_AVERAGE,address_x=ue.TextureAddress.TA_CLAMP,
                      address_y=ue.TextureAddress.TA_CLAMP,virtual_texture_streaming=False)
        if not verify and revision < 23:
            tex.set_editor_properties(settings)
            if not assets.save_loaded_asset(tex,False):
                raise RuntimeError("Could not persist "+name)
        if any(tex.get_editor_property(k)!=v for k,v in settings.items()):
            raise ValueError("Changed physical texture settings: "+name)
        textures[name]=tex
    def wired():
        names=[str(i.get_editor_property("input_name")) for i in node.get_editor_property("inputs")]
        sources=list(lib.get_inputs_for_material_expression(mat,node))
        if len(names)!=len(sources):
            raise ValueError("Unwired terrain material")
        return dict(zip(names,sources))
    if not verify:
        if "SweepFloorDetail" not in wired():
            obj=lib.create_material_expression(mat,ue.MaterialExpressionTextureObjectParameter,750,1170)
            obj.set_editor_properties(dict(parameter_name="PWRSweepFloorDetail",texture=textures[DETAIL],
                sampler_type=ue.MaterialSamplerType.SAMPLERTYPE_LINEAR_COLOR,
                sampler_source=ue.SamplerSourceMode.SSM_WRAP_WORLD_GROUP_SETTINGS))
            pins = list(node.get_editor_property("inputs"))
            pin = ue.CustomInput()
            pin.set_editor_property("input_name","SweepFloorDetail")
            node.set_editor_property("inputs",pins+[pin])
            if not lib.connect_material_expressions(obj,"",node,"SweepFloorDetail"):
                raise RuntimeError("Could not wire the physical material tile")
        if revision >= 19:
            for index, (pin_name, parameter) in enumerate(SWEEP_GAINS.items()):
                inputs = wired()
                if pin_name in inputs:
                    gain = inputs[pin_name]
                    if str(gain.get_editor_property("parameter_name")) != parameter:
                        raise ValueError("Wrong native parameter wired to "+pin_name)
                    gain.set_editor_property("default_value",expected_gains[parameter])
                    continue
                gain = lib.create_material_expression(mat,ue.MaterialExpressionScalarParameter,750,1290+index*95)
                gain.set_editor_properties(dict(parameter_name=parameter,default_value=expected_gains[parameter]))
                pins = list(node.get_editor_property("inputs"))
                pin = ue.CustomInput()
                pin.set_editor_property("input_name",pin_name)
                node.set_editor_property("inputs",pins+[pin])
                if not lib.connect_material_expressions(gain,"",node,pin_name):
                    raise RuntimeError("Could not bind surface gain "+parameter)
        node.set_editor_property("code",code)
        lib.recompile_material(mat)
        if not assets.save_loaded_asset(mat,False):
            raise RuntimeError("Could not save the Southwest terrain shader")
    for pin,name in (("AlpineRoadbed",base.LEAF),("SweepFloorDetail",DETAIL)):
        if wired()[pin].get_editor_property("texture").get_path_name()!=textures[name].get_path_name():
            raise ValueError("Wrong texture bound to native material")
    gains = {}
    if revision >= 19:
        for pin, parameter in SWEEP_GAINS.items():
            gain = wired()[pin]
            value = gain.get_editor_property("default_value")
            if str(gain.get_editor_property("parameter_name")) != parameter or abs(value-expected_gains[parameter]) > 1e-6:
                raise ValueError("Wrong native terrain gain on "+pin)
            gains[parameter] = float(value)
    if node.get_editor_property("code").replace("\r\n","\n") != code:
        raise ValueError("The Southwest terrain shader failed readback")
    if verify:
        lib.recompile_material(mat)
        (ART/"actual-graph.hlsl").write_text(node.get_editor_property("code").replace("\r\n","\n"), encoding="cp1252")
    result=dict(revision=revision,shader_sha256=base.sha(code.encode()),texture=textures[DETAIL].get_path_name(),
                source_sha256=spec["sha256"],detail_sha256=spec["detail_sha256"],material=mat.get_path_name(),
                detail_format="RGBA8 linear" if revision>=17 else "BC7 linear RGBA",tdim=[2048,1024],
                detail_full_mip_chain_bytes=11184812 if revision>=17 else 2796240,additional_sampler_states=0,
                full_coverage_local_detail_lookups=7 if revision>=22 else (6 if revision>=18 else 4),collision_changes=0)
    if revision >= 19:
        result.update(material_gains=gains, local_rut_field_lookups=2)
    if revision>=25:
        result.update(local_forest_duff_reads=dict(original=1,full_forest=3,transition=4),
                      scoped_asphalt_detail_reads=6 if revision>=27 else 4,
                      distant_asphalt_detail_reads=3 if revision>=27 else 4,
                      road_scan_skipped_in_full_forest=True,per_frame_cpu_scatter=False)
    if revision>=30:
        result["near_shoulder_detail_reads"]=10 if revision>=31 else 9
    (ART/("editor-verified.json" if verify else "editor-applied.json")).write_text(json.dumps(result,indent=2)+"\n")
    ue.log("PWR Southwest physical road floor "+result["shader_sha256"])


if __name__=="__main__":
    main()
