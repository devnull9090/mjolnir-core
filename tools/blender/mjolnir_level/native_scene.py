"""Show runtime scenery assemblies with locally extracted meshes in Blender."""
import json
import math
from pathlib import Path
import bpy
from mathutils import Matrix
from .native import import_reference


def bind_material(objects, settings, name):
    if 'slots' in settings:
        # Complete native trees contain separate bark and foliage primitives;
        # keep those slots distinct instead of painting needles onto the bark.
        materials={str(index):bind_material([],binding,name+' slot '+str(index))
                   for index,binding in settings['slots'].items()}
        for obj in objects:
            if obj.type=='MESH' and not obj.hide_render:
                for index,slot in enumerate(obj.material_slots):
                    # glTF omits unused material slots, so names are preferable
                    # to source indices for mixed native tree primitives.
                    original=slot.material.name.rsplit('.',1)[0] if slot.material else ''
                    binding=materials.get(original,materials.get(str(index)))
                    if binding: slot.material=binding
        return materials
    mat = bpy.data.materials.new("LOCAL GAME PREVIEW - "+name)
    mat.use_nodes = True
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    shader = nodes.get("Principled BSDF")
    shader.inputs["Roughness"].default_value = .8
    albedo = nodes.new("ShaderNodeTexImage")
    albedo.image = bpy.data.images.load(settings["albedo"],check_existing=True)
    links.new(albedo.outputs["Color"],shader.inputs["Base Color"])
    if settings.get('box_tile_m'):
        coordinates=nodes.new('ShaderNodeTexCoord')
        mapping=nodes.new('ShaderNodeVectorMath'); mapping.operation='SCALE'
        mapping.inputs[3].default_value=bpy.context.scene.unit_settings.scale_length/settings['box_tile_m']
        links.new(coordinates.outputs['Object'],mapping.inputs[0])
        links.new(mapping.outputs['Vector'],albedo.inputs['Vector'])
        albedo.projection='BOX'; albedo.projection_blend=.15
    if settings.get('estimated_bump'):
        bump=nodes.new('ShaderNodeBump'); bump.inputs['Strength'].default_value=.12
        bump.inputs['Distance'].default_value=.012/bpy.context.scene.unit_settings.scale_length
        links.new(albedo.outputs['Color'],bump.inputs['Height'])
        links.new(bump.outputs['Normal'],shader.inputs['Normal'])
    if settings.get('weathering'):
        # Preview counterpart for the game's layered rock response: darker
        # minerals and restrained moss on upward-facing fracture ledges.
        noise=nodes.new('ShaderNodeTexNoise'); noise.inputs['Scale'].default_value=1.3
        noise.inputs['Detail'].default_value=3
        links.new(mapping.outputs['Vector'],noise.inputs['Vector'])
        minerals=nodes.new('ShaderNodeValToRGB')
        minerals.color_ramp.elements[0].color=(.22,.22,.20,1)
        minerals.color_ramp.elements[1].color=(.85,.76,.62,1)
        links.new(noise.outputs['Fac'],minerals.inputs[0])
        stone=albedo.outputs['Color']
        quiet_path=Path(settings['albedo']).with_name('coastal_granite_albedo.png')
        if 'lichen' in Path(settings['albedo']).name and quiet_path.is_file():
            quiet=nodes.new('ShaderNodeTexImage')
            quiet.image=bpy.data.images.load(str(quiet_path),check_existing=True)
            quiet.projection='BOX'; quiet.projection_blend=.15
            links.new(mapping.outputs['Vector'],quiet.inputs['Vector'])
            quiet_tone=nodes.new('ShaderNodeMixRGB'); quiet_tone.blend_type='MULTIPLY'
            quiet_tone.inputs[0].default_value=1
            quiet_tone.inputs[2].default_value=(.72,.70,.66,1)
            links.new(quiet.outputs['Color'],quiet_tone.inputs[1])
            patch=nodes.new('ShaderNodeMapRange'); patch.clamp=True
            patch.inputs['From Min'].default_value=.53
            patch.inputs['From Max'].default_value=.73
            links.new(noise.outputs['Fac'],patch.inputs['Value'])
            localized=nodes.new('ShaderNodeMixRGB')
            localized.label='Localized lichen over broad quiet granite'
            links.new(patch.outputs[0],localized.inputs[0])
            links.new(quiet_tone.outputs[0],localized.inputs[1])
            links.new(albedo.outputs['Color'],localized.inputs[2])
            stone=localized.outputs[0]
        tint=nodes.new('ShaderNodeMixRGB'); tint.blend_type='MULTIPLY'; tint.inputs[0].default_value=1
        links.new(stone,tint.inputs[1]); links.new(minerals.outputs[0],tint.inputs[2])
        geometry=nodes.new('ShaderNodeNewGeometry'); separate=nodes.new('ShaderNodeSeparateXYZ')
        links.new(geometry.outputs['Normal'],separate.inputs[0])
        slope=nodes.new('ShaderNodeMapRange'); slope.clamp=True
        slope.inputs['From Min'].default_value=.35; slope.inputs['From Max'].default_value=.95
        links.new(separate.outputs['Z'],slope.inputs['Value'])
        patches=nodes.new('ShaderNodeMapRange'); patches.clamp=True
        patches.inputs['From Min'].default_value=.57; patches.inputs['From Max'].default_value=.80
        links.new(noise.outputs['Fac'],patches.inputs['Value'])
        mask=nodes.new('ShaderNodeMath'); mask.operation='MULTIPLY'
        links.new(slope.outputs[0],mask.inputs[0]); links.new(patches.outputs[0],mask.inputs[1])
        moss=nodes.new('ShaderNodeMixRGB'); moss.inputs[2].default_value=(.12,.14,.045,1)
        links.new(mask.outputs[0],moss.inputs[0]); links.new(tint.outputs[0],moss.inputs[1])
        links.new(moss.outputs[0],shader.inputs['Base Color'])
    if settings.get('tint'):
        tint=nodes.new('ShaderNodeMixRGB'); tint.blend_type='MULTIPLY'; tint.inputs[0].default_value=1
        color=settings['tint']; peak=max(color)
        tint.inputs[2].default_value=tuple(v/peak*.85 for v in color)+(1,)
        links.new(albedo.outputs['Color'],tint.inputs[1]); links.new(tint.outputs[0],shader.inputs['Base Color'])
    if settings.get("alpha"):
        links.new(albedo.outputs["Alpha"],shader.inputs["Alpha"])
        if hasattr(mat,"surface_render_method"):
            mat.surface_render_method = "DITHERED"
        shader.inputs["Subsurface Weight"].default_value = .08
    if settings.get('opacity_red'):
        packed=nodes.new('ShaderNodeTexImage'); packed.image=bpy.data.images.load(settings['opacity_red'],check_existing=True)
        packed.image.colorspace_settings.name='Non-Color'
        separate=nodes.new('ShaderNodeSeparateColor'); links.new(packed.outputs['Color'],separate.inputs[0])
        links.new(separate.outputs['Red'],shader.inputs['Alpha'])
        links.new(separate.outputs['Green'],shader.inputs['Roughness'])
    if settings.get("normal_dx"):
        texture = nodes.new("ShaderNodeTexImage")
        texture.image = bpy.data.images.load(settings["normal_dx"],check_existing=True)
        texture.image.colorspace_settings.name = "Non-Color"
        separate = nodes.new("ShaderNodeSeparateXYZ")
        invert = nodes.new("ShaderNodeMath")
        invert.operation = "SUBTRACT"
        invert.inputs[0].default_value = 1
        combine = nodes.new("ShaderNodeCombineXYZ")
        normal = nodes.new("ShaderNodeNormalMap")
        links.new(texture.outputs["Color"],separate.inputs[0])
        links.new(separate.outputs["X"],combine.inputs["X"])
        links.new(separate.outputs["Y"],invert.inputs[1])
        links.new(invert.outputs[0],combine.inputs["Y"])
        if settings.get("normal_xy"):
            # Cooked BC5 carries only X/Y. Its exported blue channel is zero,
            # not a negative-facing Z normal. Reconstruct positive Z in shader.
            squared=[]
            for channel in ("X","Y"):
                unpack=nodes.new("ShaderNodeMath"); unpack.operation="MULTIPLY_ADD"
                unpack.inputs[1].default_value=2; unpack.inputs[2].default_value=-1
                links.new(separate.outputs[channel],unpack.inputs[0])
                square=nodes.new("ShaderNodeMath"); square.operation="MULTIPLY"
                links.new(unpack.outputs[0],square.inputs[0]); links.new(unpack.outputs[0],square.inputs[1])
                squared.append(square)
            add=nodes.new("ShaderNodeMath"); add.operation="ADD"
            links.new(squared[0].outputs[0],add.inputs[0]); links.new(squared[1].outputs[0],add.inputs[1])
            remain=nodes.new("ShaderNodeMath"); remain.operation="SUBTRACT"; remain.inputs[0].default_value=1
            links.new(add.outputs[0],remain.inputs[1])
            clamp=nodes.new("ShaderNodeMath"); clamp.operation="MAXIMUM"; clamp.inputs[1].default_value=0
            links.new(remain.outputs[0],clamp.inputs[0])
            sqrt=nodes.new("ShaderNodeMath"); sqrt.operation="SQRT"; links.new(clamp.outputs[0],sqrt.inputs[0])
            pack=nodes.new("ShaderNodeMath"); pack.operation="MULTIPLY_ADD"
            pack.inputs[1].default_value=.5; pack.inputs[2].default_value=.5
            links.new(sqrt.outputs[0],pack.inputs[0]); links.new(pack.outputs[0],combine.inputs["Z"])
        else:
            links.new(separate.outputs["Z"],combine.inputs["Z"])
        links.new(combine.outputs[0],normal.inputs["Color"])
        links.new(normal.outputs[0],shader.inputs["Normal"])
    if settings.get('occlusion_red'):
        packed=nodes.new('ShaderNodeTexImage')
        packed.image=bpy.data.images.load(settings['occlusion_red'],check_existing=True)
        packed.image.colorspace_settings.name='Non-Color'
        separate=nodes.new('ShaderNodeSeparateColor'); links.new(packed.outputs['Color'],separate.inputs[0])
        shade=nodes.new('ShaderNodeMixRGB'); shade.blend_type='MULTIPLY'; shade.inputs[0].default_value=.65
        links.new(shader.inputs['Base Color'].links[0].from_socket,shade.inputs[1])
        links.new(separate.outputs['Red'],shade.inputs[2]); links.new(shade.outputs[0],shader.inputs['Base Color'])
        links.new(separate.outputs['Green'],shader.inputs['Roughness'])
    if settings.get('weathering'):
        cavity=nodes.new('ShaderNodeAmbientOcclusion')
        cavity.inputs['Distance'].default_value=1.5/bpy.context.scene.unit_settings.scale_length
        cavity.samples=1
        shade=nodes.new('ShaderNodeMixRGB'); shade.blend_type='MULTIPLY'; shade.inputs[0].default_value=.35
        links.new(shader.inputs['Base Color'].links[0].from_socket,shade.inputs[1])
        links.new(cavity.outputs['AO'],shade.inputs[2]); links.new(shade.outputs[0],shader.inputs['Base Color'])
    for obj in objects:
        if obj.type == "MESH" and not obj.hide_render:
            for slot in obj.material_slots:
                slot.material = mat
    return mat


def rotation_rows(pitch,yaw,roll):
    p,y,r = map(math.radians,(pitch,yaw,roll))
    sp,cp,sy,cy,sr,cr = math.sin(p),math.cos(p),math.sin(y),math.cos(y),math.sin(r),math.cos(r)
    return [[cp*cy,cp*sy,sp],[sr*sp*cy-cr*sy,sr*sp*sy+cr*cy,-sr*cp],
            [-(cr*sp*cy+sr*sy),cy*sr-cr*sp*sy,cr*cp]]


def ue_matrix(rows, position, unit):
    mirror = Matrix.Diagonal((1,-1,1))
    result = (mirror @ Matrix(rows).transposed() @ mirror).to_4x4()
    result.translation = (position[0]/100/unit,-position[1]/100/unit,position[2]/100/unit)
    return result


def load_runtime_scenery(path, target):
    document = json.loads(Path(path).read_text(encoding="utf-8"))
    swap = json.loads(Path(document["swap"]).read_text(encoding="utf-8"))
    templates = {}
    for mesh, file in document["models"].items():
        template = bpy.data.collections.new("LOCAL ASSET - "+mesh.rsplit("/",1)[-1])
        template["mjolnir_preview_only"] = True
        _, objects = import_reference(file,template)
        for obj in list(objects):
            if obj.hide_render:
                objects.remove(obj)
                bpy.data.objects.remove(obj,do_unlink=True)
        if mesh in document["materials"]:
            bind_material(objects,document["materials"][mesh],mesh.rsplit("/",1)[-1])
        templates[mesh] = template
    unit = bpy.context.scene.unit_settings.scale_length
    count = 0
    def instance(mesh,name,matrix):
        nonlocal count
        obj = bpy.data.objects.new(name,None)
        obj.instance_type = "COLLECTION"
        obj.instance_collection = templates[mesh]
        target.objects.link(obj)
        obj.matrix_world = matrix
        obj["mjolnir_preview_only"] = True
        obj["ue_asset"] = mesh
        count += 1
    for item in swap["decor"]:
        rows = rotation_rows(*item.get("rot",[0,0,0]))
        for axis,scale in zip(rows,item.get("scale",[1,1,1])):
            for i in range(3):
                axis[i] *= scale
        instance(item["mesh"],"NATIVE - "+item["id"],ue_matrix(rows,item["pos"],unit))
    leaves = swap["leaves"]
    for index,record in enumerate(leaves["records"]):
        rows = [record[7:10],record[10:13],record[13:16]]
        instance(leaves["mesh"],f"NATIVE - leaves {index}",ue_matrix(rows,record[:3],unit))
    return {"manifest":str(Path(path).resolve()),"instances":count,"unique_meshes":len(templates),
            "material_fidelity":document["material_fidelity"],"placements_sha256":document["placements_sha256"]}
