"""Image-based ground and pond studies for the isolated Blender preview.

Called after prepare_materials and native PCG imports. Only PREVIEW materials are changed; there are
no geometry edits, exports or source-file writes. Installed CE image details
stay external. This approximates surface appearance, not Unreal shader graphs,
Fluid Flux simulation, runtime lighting or calibrated PBR material response.
"""
from pathlib import Path
import bpy


def enhance(scene, manifest):
    unit=scene.unit_settings.scale_length
    report={"fidelity":"Blender-only image-detail and shallow-water study; not UE material/Flux parity",
            "textures":[],"materials":[],"missing":[],
            "ground":"Authored meadow underlay and installed soil detail; scatter's beach-alpha blend with explicit image-V conversion",
            "water":"Two installed ripple images; Fresnel and shallow-edge color/alpha aligned to terrain's irregular shore; no depth simulation"}
    folders=[]
    for path in manifest.get("texture_references",[]):
        folders.append(Path(path).parent)
    for image in bpy.data.images:
        if image.filepath:
            folders.append(Path(bpy.path.abspath(image.filepath)).parent)
    folders=list(dict.fromkeys(folders))

    def locate(name):
        for folder in folders:
            file=folder/name
            if file.is_file():
                report["textures"].append(str(file.resolve()))
                return file
        report["missing"].append(name)
        return None

    def initialize(mat):
        mat.use_nodes=True
        nodes,links=mat.node_tree.nodes,mat.node_tree.links
        nodes.clear()
        output=nodes.new("ShaderNodeOutputMaterial")
        shader=nodes.new("ShaderNodeBsdfPrincipled")
        links.new(shader.outputs["BSDF"],output.inputs["Surface"])
        return nodes,links,shader,output

    def math_node(nodes,links,operation,a,b=None):
        node=nodes.new("ShaderNodeMath"); node.operation=operation
        for i,value in enumerate((a,b)):
            if value is None: continue
            if isinstance(value,(int,float)): node.inputs[i].default_value=value
            else: links.new(value,node.inputs[i])
        return node.outputs[0]

    def vector_scale(nodes,links,source,scale):
        node=nodes.new("ShaderNodeVectorMath"); node.operation="SCALE"
        node.inputs[3].default_value=scale
        links.new(source,node.inputs[0])
        return node.outputs[0]

    def texture(nodes,links,path,vector,noncolor=False):
        node=nodes.new("ShaderNodeTexImage")
        node.image=bpy.data.images.load(str(path),check_existing=True)
        if noncolor and node.image.colorspace_settings.name!="Non-Color":
            # Keep other consumers' color interpretation intact.
            node.image=node.image.copy()
            node.image.colorspace_settings.name="Non-Color"
        node.extension="REPEAT"
        links.new(vector,node.inputs["Vector"])
        return node

    def ramp(nodes,links,socket,stops):
        node=nodes.new("ShaderNodeValToRGB")
        node.color_ramp.interpolation="EASE"
        node.color_ramp.elements.remove(node.color_ramp.elements[1])
        for index,(position,color) in enumerate(stops):
            element=node.color_ramp.elements[0] if index==0 else node.color_ramp.elements.new(position)
            element.position=position; element.color=color
        links.new(socket,node.inputs["Fac"])
        return node.outputs["Color"]

    def ellipse(nodes,links,position):
        # Match terrain_form's actual irregular shoreline, not the oversized
        # water plane extending invisibly beneath dry terrain. Using plane
        # bounds put the entire shallow-water transition underground.
        center=[36/unit,-23/unit,-.18/unit]; radii=[8.5/unit,6.2/unit]
        subtract=nodes.new("ShaderNodeVectorMath"); subtract.operation="SUBTRACT"
        subtract.inputs[1].default_value=center
        links.new(position,subtract.inputs[0])
        separate=nodes.new("ShaderNodeSeparateXYZ")
        links.new(subtract.outputs[0],separate.inputs[0])
        x=math_node(nodes,links,"DIVIDE",separate.outputs["X"],radii[0])
        y=math_node(nodes,links,"DIVIDE",separate.outputs["Y"],radii[1])
        squared=math_node(nodes,links,"ADD",math_node(nodes,links,"MULTIPLY",x,x),
                          math_node(nodes,links,"MULTIPLY",y,y))
        angle=math_node(nodes,links,"ARCTAN2",y,x)
        def wave(operation,frequency,phase,amplitude):
            a=math_node(nodes,links,"ADD",math_node(nodes,links,"MULTIPLY",angle,frequency),phase)
            return math_node(nodes,links,"MULTIPLY",math_node(nodes,links,operation,a),amplitude)
        shape=math_node(nodes,links,"ADD",1,wave('SINE',3,.4,.08))
        shape=math_node(nodes,links,"ADD",shape,wave('COSINE',5,-.3,.055))
        shore=math_node(nodes,links,"ADD",1.485,wave('SINE',7,.8,.038))
        shore=math_node(nodes,links,"ADD",shore,wave('COSINE',11,0,.025))
        radius=math_node(nodes,links,"DIVIDE",math_node(nodes,links,"SQRT",squared),shape)
        return math_node(nodes,links,"DIVIDE",radius,shore)

    def meadow_color(nodes,links,source,position):
        """Shared world-space dry patches across the ground and native blades."""
        noise=nodes.new("ShaderNodeTexNoise")
        noise.inputs["Scale"].default_value=unit/14
        noise.inputs["Detail"].default_value=2
        links.new(position,noise.inputs["Vector"])
        patch=ramp(nodes,links,noise.outputs["Fac"],
                   [(.37,(0,0,0,1)),(.59,(1,1,1,1))])
        dry=nodes.new("ShaderNodeMixRGB"); dry.blend_type="MULTIPLY"
        dry.inputs[0].default_value=1
        dry.inputs[2].default_value=(1.18,1.01,.72,1)
        links.new(source,dry.inputs[1])
        mix=nodes.new("ShaderNodeMixRGB")
        links.new(patch,mix.inputs[0]); links.new(source,mix.inputs[1])
        links.new(dry.outputs[0],mix.inputs[2])
        return mix.outputs[0]

    ground=next((m for m in bpy.data.materials if m.name=="PREVIEW - beach"),None)
    if ground and not ground.get("tst_surface_detail"):
        grass=locate("levels_a30_bitmaps_detail_grass.png")
        meadow=Path(__file__).resolve().parent/'art/textures/coastal_meadow_albedo.png'
        if meadow.is_file():
            grass=meadow
            report['textures'].append(str(meadow))
            report['ground']='Authored meadow albedo underlay at 8m with installed CE soil detail and beach-alpha blend; preview only'
        soil=locate("levels_b30_bitmaps_detail_ground.png")
        mask=locate("levels_b30_bitmaps_beach.png")
        if all((grass,soil,mask)):
            nodes,links,shader,output=initialize(ground)
            coord=nodes.new("ShaderNodeTexCoord")
            geom=nodes.new("ShaderNodeNewGeometry")
            # Runtime's sampler indexes PNG rows top-to-bottom at stored V;
            # Blender's image texture samples bottom-to-top, requiring 1-V.
            split=nodes.new("ShaderNodeSeparateXYZ"); links.new(coord.outputs["UV"],split.inputs[0])
            combine=nodes.new("ShaderNodeCombineXYZ")
            links.new(split.outputs["X"],combine.inputs["X"])
            links.new(math_node(nodes,links,"SUBTRACT",1,split.outputs["Y"]),combine.inputs["Y"])
            base=texture(nodes,links,mask,combine.outputs[0])
            grass_share=math_node(nodes,links,"SUBTRACT",1,base.outputs["Alpha"])
            # Sparse blade regions still have short meadow growth below them;
            # the stock island mask otherwise exposes a bright sandy carpet.
            transition=nodes.new("ShaderNodeMapRange"); transition.clamp=True
            transition.interpolation_type='SMOOTHERSTEP'
            transition.inputs['From Min'].default_value=.04
            transition.inputs['From Max'].default_value=.50
            links.new(grass_share,transition.inputs['Value'])
            grass_share=transition.outputs[0]
            grass_tex=texture(nodes,links,grass,vector_scale(nodes,links,geom.outputs["Position"],unit/8))
            soil_tex=texture(nodes,links,soil,vector_scale(nodes,links,geom.outputs["Position"],unit/1.6),True)
            grass_color=nodes.new("ShaderNodeHueSaturation")
            grass_color.inputs["Saturation"].default_value=.85
            grass_color.inputs["Value"].default_value=1.05
            links.new(grass_tex.outputs["Color"],grass_color.inputs["Color"])
            grass_warm=nodes.new("ShaderNodeMixRGB"); grass_warm.blend_type="MULTIPLY"
            grass_warm.inputs[0].default_value=1
            grass_warm.inputs[2].default_value=(.62,.82,.44,1)
            links.new(grass_color.outputs[0],grass_warm.inputs[1])
            soil_color=ramp(nodes,links,soil_tex.outputs["Color"],
                [(0,(.065,.052,.025,1)),(.40,(.18,.14,.065,1)),
                 (.65,(.37,.30,.16,1)),(1,(.48,.41,.24,1))])
            mix=nodes.new("ShaderNodeMixRGB")
            links.new(grass_share,mix.inputs[0]); links.new(soil_color,mix.inputs[1])
            links.new(meadow_color(nodes,links,grass_warm.outputs[0],geom.outputs["Position"]),mix.inputs[2])
            radius=ellipse(nodes,links,geom.outputs["Position"])
            wet=ramp(nodes,links,radius,[(0,(1,1,1,1)),(.93,(1,1,1,1)),(1.12,(0,0,0,1))])
            wet_color=nodes.new("ShaderNodeMixRGB"); wet_color.blend_type="MULTIPLY"
            wet_color.inputs[0].default_value=1
            links.new(mix.outputs[0],wet_color.inputs[1])
            wet_color.inputs[2].default_value=(.42,.50,.35,1)
            wet_mix=nodes.new("ShaderNodeMixRGB")
            links.new(wet,wet_mix.inputs[0]); links.new(mix.outputs[0],wet_mix.inputs[1])
            links.new(wet_color.outputs[0],wet_mix.inputs[2])
            links.new(wet_mix.outputs[0],shader.inputs["Base Color"])
            relief=nodes.new("ShaderNodeMixRGB")
            links.new(grass_share,relief.inputs[0]); links.new(soil_tex.outputs["Color"],relief.inputs[1])
            links.new(grass_tex.outputs["Color"],relief.inputs[2])
            bump=nodes.new("ShaderNodeBump")
            bump.inputs["Strength"].default_value=.42
            bump.inputs["Distance"].default_value=.025/unit
            links.new(relief.outputs[0],bump.inputs["Height"])
            links.new(bump.outputs["Normal"],shader.inputs["Normal"])
            shader.inputs["Roughness"].default_value=.9
            ground["tst_surface_detail"]=True
            report["materials"].append(ground.name)

    water=next((m for m in bpy.data.materials if m.name=="PREVIEW - tst_water!"),None)
    if water and not water.get("tst_surface_detail"):
        ripple0=locate("sky_bitmaps_crap_water0.png")
        ripple1=locate("sky_bitmaps_crap_water1.png")
        if ripple0 and ripple1:
            nodes,links,shader,output=initialize(water)
            geom=nodes.new("ShaderNodeNewGeometry")
            position=geom.outputs["Position"]
            radius=ellipse(nodes,links,position)
            color=ramp(nodes,links,radius,
                [(0,(.035,.12,.17,1)),(.72,(.08,.24,.28,1)),
                 (.94,(.18,.34,.25,1)),(1,(.25,.34,.22,1))])
            links.new(color,shader.inputs["Base Color"])
            shader.inputs["Roughness"].default_value=.12
            shader.inputs["IOR"].default_value=1.333
            shader.inputs["Transmission Weight"].default_value=.7
            shader.inputs["Coat Weight"].default_value=.3
            shader.inputs["Coat Roughness"].default_value=.1
            # Two distinct, installed image patterns at metre-scale wavelengths
            # break up the reflection without displacement or noisy geometry.
            coarse=texture(nodes,links,ripple0,vector_scale(nodes,links,position,unit/8.0),True)
            rotation=nodes.new("ShaderNodeVectorRotate"); rotation.rotation_type="AXIS_ANGLE"
            rotation.inputs["Axis"].default_value=(0,0,1)
            rotation.inputs["Angle"].default_value=.83
            links.new(position,rotation.inputs["Vector"])
            fine=texture(nodes,links,ripple1,vector_scale(nodes,links,rotation.outputs["Vector"],unit/3.0),True)
            # Light water color modulation preserves the installed ripple
            # pattern in a distant overview where uniform sky reflections can
            # hide bump detail. This is explicitly an art-directed preview.
            ripple_color=ramp(nodes,links,coarse.outputs["Color"],
                [(0,(.55,.65,.72,1)),(.38,(.85,.94,1,1)),
                 (.72,(1.6,1.8,1.9,1)),(1,(2.3,2.5,2.5,1))])
            water_color=nodes.new("ShaderNodeMixRGB"); water_color.blend_type="MULTIPLY"
            water_color.inputs[0].default_value=.20
            links.new(color,water_color.inputs[1]); links.new(ripple_color,water_color.inputs[2])
            water_tone=nodes.new("ShaderNodeHueSaturation")
            water_tone.inputs["Saturation"].default_value=.55
            water_tone.inputs["Value"].default_value=1.1
            links.new(water_color.outputs[0],water_tone.inputs["Color"])
            links.new(water_tone.outputs[0],shader.inputs["Base Color"])
            bump0=nodes.new("ShaderNodeBump")
            bump0.inputs["Strength"].default_value=.6
            bump0.inputs["Distance"].default_value=.14/unit
            links.new(coarse.outputs["Color"],bump0.inputs["Height"])
            bump1=nodes.new("ShaderNodeBump")
            bump1.inputs["Strength"].default_value=.32
            bump1.inputs["Distance"].default_value=.025/unit
            links.new(fine.outputs["Color"],bump1.inputs["Height"])
            links.new(bump0.outputs["Normal"],bump1.inputs["Normal"])
            links.new(bump1.outputs["Normal"],shader.inputs["Normal"])
            links.new(bump1.outputs["Normal"],shader.inputs["Coat Normal"])
            fade=ramp(nodes,links,radius,[(0,(1,1,1,1)),(.96,(1,1,1,1)),(1,(0,0,0,1))])
            transparent=nodes.new("ShaderNodeBsdfTransparent")
            mix=nodes.new("ShaderNodeMixShader")
            links.new(fade,mix.inputs[0]); links.new(transparent.outputs[0],mix.inputs[1])
            links.new(shader.outputs[0],mix.inputs[2]); links.new(mix.outputs[0],output.inputs["Surface"])
            if hasattr(water,"surface_render_method"): water.surface_render_method="DITHERED"
            water["tst_surface_detail"]=True
            report["materials"].append(water.name)
    # Runtime tint values are authored for Unreal's layered foliage master.
    # A gentler saturation approximates that response in the simple Blender
    # shader. This changes neither the native images nor the scatter output.
    for mat in bpy.data.materials:
        if not mat.name.startswith("LOCAL GAME PREVIEW - ") or "Wild_Grass" not in mat.name:
            continue
        if mat.get("tst_grass_color_study") or not mat.use_nodes:
            continue
        nodes,links=mat.node_tree.nodes,mat.node_tree.links
        shader=nodes.get("Principled BSDF")
        if shader is None or not shader.inputs["Base Color"].links:
            continue
        source=shader.inputs["Base Color"].links[0].from_socket
        color=nodes.new("ShaderNodeHueSaturation")
        color.label="Preview response for Unreal layered foliage tint"
        color.inputs["Saturation"].default_value=.52
        color.inputs["Value"].default_value=.72
        links.new(source,color.inputs["Color"])
        warm=nodes.new("ShaderNodeMixRGB"); warm.blend_type="MULTIPLY"
        warm.label="Warm olive mids for preview lighting"
        warm.inputs[0].default_value=1
        warm.inputs[2].default_value=(1.10,1.02,.74,1)
        links.new(color.outputs[0],warm.inputs[1])
        geom=nodes.new("ShaderNodeNewGeometry")
        links.new(meadow_color(nodes,links,warm.outputs[0],geom.outputs["Position"]),shader.inputs["Base Color"])
        shader.inputs["Subsurface Weight"].default_value=.02
        shader.inputs["Specular IOR Level"].default_value=.2
        rough=nodes.new("ShaderNodeMath"); rough.operation="MAXIMUM"
        rough.inputs[1].default_value=.75
        if shader.inputs["Roughness"].links:
            links.new(shader.inputs["Roughness"].links[0].from_socket,rough.inputs[0])
        else:
            rough.inputs[0].default_value=shader.inputs["Roughness"].default_value
        links.new(rough.outputs[0],shader.inputs["Roughness"])
        mat["tst_grass_color_study"]=True
        report["materials"].append(mat.name)
    report["grass_color_study"]="Native foliage images and runtime tint retained; Blender-only 0.52 saturation, 0.72 value, shared 14m dry meadow patches, restrained specular and minimum 0.75 roughness"
    report["water_ripple_study"]="Installed ripple image bump and art-directed color modulation for distant reflection readability; not simulated water"
    report["textures"]=list(dict.fromkeys(report["textures"]))
    manifest.setdefault("texture_references",[]).extend(
        path for path in report["textures"] if path not in manifest["texture_references"])
    manifest["surface_detail_study"]=report
    return report
