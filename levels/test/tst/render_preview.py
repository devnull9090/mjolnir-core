"""Render repeatable Blender design views without exporting or changing TST.

    blender --background --factory-startup --python render_preview.py -- \
        --staging C:/haloce/ce_conversions/community/TST/staging --views exterior side

The optional staging path reads local CE textures and reference glTF models.
It never downloads or bundles game assets. Without staging, explicit wire
bounds indicate scenery locations. Preview materials, lights, sea and imported
assets are saved only into the output preview.blend. Source .blend, JMS,
placement JSON and game files are never changed.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
from pathlib import Path
import sys
import time
import bpy
import bmesh
from mathutils import Matrix, Vector

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from amber_light import load_spec as load_amber_spec
AMBER_SPEC = load_amber_spec()
REPO = ROOT.parents[2]
METRES_PER_CE = 3.048
VIEWS = {
    "exterior": {"position": (0,-142,92), "target": (0,0,1), "lens": 40},
    "topdown": {"position": (0,-5,140), "target": (0,-5,0), "ortho": 165},
    "side": {"position": (-24,-38,17), "target": (-54,-1,2.7), "lens": 45},
    "wall": {"position": (0,-17,12), "target": (0,33,12), "lens": 18},
    "balcony": {"position": (-59,24,9), "target": (-27,28.8,8.7), "lens": 25},
    "tower-passage": {"position": (-10,28.8,8.9), "target": (7,28.8,8.9), "lens": 22},
    "tower-elevation": {"position": (-20,28.8,17.5), "target": (0,28.8,17.5), "ortho": 26},
    "rail-joint": {"position": (-58,15,11), "target": (-53,22,7.9), "lens": 52},
    "blue-roof-access": {"position": (35,-26,25), "target": (57,0,3.8), "lens": 42},
    "red-roof-access": {"position": (-35,26,25), "target": (-57,0,3.8), "lens": 42},
    "blue-ramp-approach": {"position": (63,-24,27), "target": (60,0,4), "lens": 40},
    "portal": {"position": (-48,23.5,9.0), "target": (-48,31.5,9), "lens": 25},
    "red-interior": {"position": (-57.2,5.8,2.15), "target": (-49.8,-3.5,1.9), "lens": 19},
    "blue-interior": {"position": (57.2,-5.8,2.15), "target": (49.8,3.5,1.9), "lens": 19},
    "facility-red": {"position": (-34,-10,2.1), "target": (-53,18,5.5), "lens": 35, "aspect": 854/525},
    "facility-blue": {"position": (34,-10,2.1), "target": (53,18,5.5), "lens": 35, "aspect": 854/525},
    "facility-interior": {"position": (-7.5,40,1.55), "target": (20,40,2.4), "lens": 22, "aspect": 1715/392},
    "facility-door": {"position": (-1,40,1.9), "target": (3,47,2.0), "lens": 30},
    "facility-route": {"position": (-40,51.5,1.9), "target": (-18,46.8,2.0), "lens": 24},
    "facility-entry-red-inside": {"position": (-48,38.8,1.8), "target": (-48,25,2.3), "lens": 20},
    "facility-entry-blue-inside": {"position": (48,38.8,1.8), "target": (48,25,2.3), "lens": 20},
    "facility-panel-bays": {"position": (-30,28.5,1.8), "target": (-19,32.8,1.9), "lens": 25},
    "facility-turn-red": {"position": (-40,35,1.8), "target": (-43.8,29,2), "lens": 24},
    "facility-turn-blue": {"position": (40,35,1.8), "target": (43.8,29,2), "lens": 24},
    "facility-former-riser-red": {"position": (-26,6,2.5), "target": (-33,19,2.5), "lens": 28},
    "facility-former-riser-blue": {"position": (26,6,2.5), "target": (33,19,2.5), "lens": 28},
    "layout": {"position": (0,-8,140), "target": (0,-8,0), "ortho": 230},
    "pcg": {"position": (0,-134,76), "target": (0,3,2), "lens": 34},
}
MATERIAL_TEXTURES = {
    "mp lights small strips!": "levels_test_bloodgulch_bitmaps_mp_lights_small_strips.png",
    AMBER_SPEC["material"]: AMBER_SPEC["atlas_texture"],
    "example_tutorial_teleporter!": "scenery_teleporter_shield_bitmaps_teleporter_shield_dust.png",
    "beach": "levels_b30_bitmaps_beach.png",
    "tst_cliffs": "levels_b30_bitmaps_cliffs.png",
    "metal panels generic ext": "levels_b30_bitmaps_metal_panels_generic_ext.png",
    "metal plate floor ext": "levels_b30_bitmaps_metal_plate_floor_ext.png",
    "dangercanyon_decor_strip_red!": "levels_test_dangercanyon_bitmaps_dangercanyon_decor_strip_red.png",
    "dangercanyon_decor_strip_blue!": "levels_test_dangercanyon_bitmaps_dangercanyon_decor_strip_blue.png",
}
DETAIL_TEXTURES = {
    "beach": "levels_b30_bitmaps_detail_ground.png",
    "tst_cliffs": "levels_b30_bitmaps_detail_cliff_rock.png",
    "metal panels generic ext": "levels_b30_bitmaps_detail_brushed_metal.png",
    "metal plate floor ext": "levels_b30_bitmaps_metal_plate_floor_bump.png",
}

def arguments():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--blend", type=Path, default=ROOT/"tst.blend")
    parser.add_argument("--placements", type=Path, default=ROOT/"placements.json")
    parser.add_argument("--staging", type=Path, help="Local CE conversion staging with models/ and textures/")
    parser.add_argument("--alloy-albedo", type=Path, help="Authored architectural albedo, box projected at 2 m tiles")
    parser.add_argument("--floor-albedo", type=Path, help="Authored FLOOR albedo, box projected at 4 m tiles")
    parser.add_argument("--cliff-albedo", type=Path, help="Authored cliff albedo, box projected at 6 m tiles")
    parser.add_argument("--out", type=Path, default=REPO/".dream-loop/blender-preview")
    parser.add_argument("--views", nargs="+", choices=list(VIEWS), default=[name for name in VIEWS if name!="pcg"])
    parser.add_argument("--engine", choices=["eevee","cycles"], default="cycles")
    parser.add_argument("--device", choices=["auto","cpu"], default="auto",
                        help="Cycles GPU when available, otherwise CPU; manifest records effective device")
    parser.add_argument("--samples", type=int, default=64)
    parser.add_argument("--width", type=int, default=1600)
    parser.add_argument("--height", type=int, default=900)
    parser.add_argument("--no-scenery", action="store_true")
    parser.add_argument("--native-assets", type=Path, help="Local native-preview.json produced by tools/blender/prepare_native_preview.py")
    parser.add_argument("--pcg-assets", type=Path, help="Actual runtime scatter and cached meshes from prepare_pcg_preview.py")
    parser.add_argument("--cyborg", type=Path, help="Locally converted cyborg glTF, imported at its real metre scale")
    argv = sys.argv[sys.argv.index("--")+1:] if "--" in sys.argv else []
    args = parser.parse_args(argv)
    if args.samples < 1 or min(args.width,args.height) < 128:
        parser.error("Samples must be positive; image dimensions must be at least 128")
    if args.staging and not (args.staging/"models").is_dir():
        parser.error("--staging must contain the conversion's models/ directory")
    return args

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def collection(scene,name):
    result = bpy.data.collections.new("PREVIEW ONLY - "+name)
    result["mjolnir_preview_only"] = True
    scene.collection.children.link(result)
    return result

def link_only(obj,target):
    for existing in list(obj.users_collection):
        existing.objects.unlink(obj)
    target.objects.link(obj)
    obj["mjolnir_preview_only"] = True

def point_at(obj,target):
    obj.rotation_euler = (Vector(target)/METRES_PER_CE-obj.location).to_track_quat("-Z","Y").to_euler()

def material(name,color,roughness=.7,metallic=0):
    mat = bpy.data.materials.new("PREVIEW - "+name)
    mat.use_nodes = True
    shader = mat.node_tree.nodes.get("Principled BSDF")
    shader.inputs["Base Color"].default_value = (*color,1)
    shader.inputs["Roughness"].default_value = roughness
    shader.inputs["Metallic"].default_value = metallic
    return mat

def facility_fixture(obj):
    """Authored facility lenses supply the only new interior light sources."""
    return bool(obj.get("tst_facility_fixture") or obj.name.lower().startswith("facility_"))

def snapshot_authored_surfaces(scene):
    """Capture used exported roles and UVs before any preview-only styling.

    Call after the intentional sky-face removal so terrain polygon indices are
    stable. Stock CE/native approximation materials have no authored role and
    are excluded. Hidden construction copies are not preview geometry.
    """
    snapshot={}
    for obj in scene.objects:
        if obj.type!='MESH' or obj.hide_render or obj.name.startswith('SOURCE_'):
            continue
        rows=[]
        uv=obj.data.uv_layers.get('UVMap')
        for face in obj.data.polygons:
            mat=obj.data.materials[face.material_index]
            if not mat or not mat.get('tst_surface_role'):
                continue
            if uv is None:
                raise RuntimeError('Authored surface has no exported UVMap: '+obj.name)
            rows.append((face.index,tuple(face.vertices),mat['tst_surface_role'],
                         mat.get('source_shader_tag'),
                         tuple(tuple(uv.data[index].uv) for index in face.loop_indices)))
        if rows:
            snapshot[obj.name]=(len(obj.data.vertices),len(obj.data.polygons),rows)
    return snapshot

def assert_authored_surfaces(scene,snapshot):
    """Fail if a later fallback changes exported face finishes or UVs."""
    checked=0;changes=[]
    for name,(vertex_count,face_count,rows) in snapshot.items():
        obj=scene.objects.get(name)
        if obj is None or obj.type!='MESH' or len(obj.data.vertices)!=vertex_count or len(obj.data.polygons)!=face_count:
            changes.append({'object':name,'kind':'missing_object_or_changed_topology'})
            continue
        uv=obj.data.uv_layers.get('UVMap')
        for index,vertices,role,tag,coords in rows:
            face=obj.data.polygons[index]
            mat=obj.data.materials[face.material_index]
            checked+=1
            current_coords=tuple(tuple(uv.data[i].uv) for i in face.loop_indices) if uv else None
            if (tuple(face.vertices)!=vertices or mat is None or
                mat.get('tst_surface_role')!=role or mat.get('source_shader_tag')!=tag or current_coords!=coords):
                changes.append({'object':name,'face':index,'kind':'authored_surface_changed'})
    result={'checked_objects':len(snapshot),'checked_faces':checked,
            'changed_faces':len(changes),'passed':not changes,
            'scope':'Used authored face roles, source shader tags, topology and exported UVMap; stock/native approximations excluded.'}
    if changes:
        raise RuntimeError('Preview changed authored surfaces: '+json.dumps({**result,'first_changes':changes[:12]}))
    return result

def prepare_materials(scene,staging,manifest,alloy_albedo=None,floor_albedo=None,cliff_albedo=None):
    replacements = {}
    for obj in scene.objects:
        if obj.type!="MESH" or obj.hide_render:
            continue
        for slot in obj.material_slots:
            original = slot.material
            if not original:
                continue
            if original.get('tst_surface_role'):
                # Shared authored material and UVMap travel through the game build.
                manifest.setdefault('exported_surface_roles', [])
                if original['tst_surface_role'] not in manifest['exported_surface_roles']:
                    manifest['exported_surface_roles'].append(original['tst_surface_role'])
                    surface = json.loads((ROOT/'surfaces.json').read_text())['surfaces'][original['tst_surface_role']]
                    for key in ('albedo', 'roughness_map', 'normal_map'):
                        if key not in surface:
                            continue
                        path = str((ROOT/surface[key]).resolve())
                        if path not in manifest['texture_references']:
                            manifest['texture_references'].append(path)
                continue
            if original.get('tst_detail_material'):
                original=bpy.data.materials[original['tst_detail_material']]
            if original.name not in replacements:
                mat = original.copy()
                mat.name = "PREVIEW - "+original.name
                mat.use_nodes = True
                nodes,links = mat.node_tree.nodes,mat.node_tree.links
                shader = nodes.get("Principled BSDF")
                shader.inputs["Roughness"].default_value = .78 if original.name in {"beach","tst_cliffs"} else .52
                shader.inputs["Metallic"].default_value = .28 if "metal" in original.name else 0
                texture = staging/"textures"/MATERIAL_TEXTURES[original.name] if staging and original.name in MATERIAL_TEXTURES else None
                if texture and texture.is_file():
                    node = nodes.new("ShaderNodeTexImage")
                    node.image = bpy.data.images.load(str(texture),check_existing=True)
                    links.new(node.outputs["Color"],shader.inputs["Base Color"])
                    manifest["texture_references"].append(str(texture.resolve()))
                detail = staging/"textures"/DETAIL_TEXTURES[original.name] if staging and original.name in DETAIL_TEXTURES else None
                if detail and detail.is_file():
                    coordinate = nodes.new("ShaderNodeTexCoord")
                    mapping = nodes.new("ShaderNodeVectorMath")
                    mapping.operation = "SCALE"
                    mapping.inputs[3].default_value = 180 if original.name=="beach" else 6
                    links.new(coordinate.outputs["UV"],mapping.inputs[0])
                    node = nodes.new("ShaderNodeTexImage")
                    node.image = bpy.data.images.load(str(detail),check_existing=True)
                    node.image.colorspace_settings.name = "Non-Color"
                    links.new(mapping.outputs["Vector"],node.inputs["Vector"])
                    bump = nodes.new("ShaderNodeBump")
                    bump.inputs["Strength"].default_value = .28
                    bump.inputs["Distance"].default_value = .015/METRES_PER_CE
                    links.new(node.outputs["Color"],bump.inputs["Height"])
                    links.new(bump.outputs["Normal"],shader.inputs["Normal"])
                    manifest["texture_references"].append(str(detail.resolve()))
                if original.name=="tst_water!":
                    for link in list(shader.inputs['Base Color'].links): links.remove(link)
                    shader.inputs["Base Color"].default_value = (.025,.11,.13,1)
                    shader.inputs["Roughness"].default_value = .10
                    shader.inputs["Metallic"].default_value = 0
                    shader.inputs["Transmission Weight"].default_value = .55
                    shader.inputs['IOR'].default_value=1.333
                    coordinate = nodes.new("ShaderNodeTexCoord")
                    noise = nodes.new("ShaderNodeTexNoise")
                    noise.inputs["Scale"].default_value = 8
                    noise.inputs["Detail"].default_value = 2
                    links.new(coordinate.outputs["Object"],noise.inputs["Vector"])
                    bump = nodes.new("ShaderNodeBump")
                    bump.inputs["Strength"].default_value = .18
                    bump.inputs["Distance"].default_value = .025/METRES_PER_CE
                    links.new(noise.outputs["Fac"],bump.inputs["Height"])
                    links.new(bump.outputs["Normal"],shader.inputs["Normal"])
                if original.name in {"beach","tst_cliffs"}:
                    # The stock beach base bitmap encodes an entire different
                    # island. A clearly labeled preview shader keeps our actual
                    # terrain readable without importing that island's coastline.
                    coordinate = nodes.new("ShaderNodeTexCoord")
                    noise = nodes.new("ShaderNodeTexNoise")
                    noise.inputs["Scale"].default_value = .35 if original.name=="beach" else 1.8
                    noise.inputs["Detail"].default_value = 5
                    links.new(coordinate.outputs["Object"],noise.inputs["Vector"])
                    ramp = nodes.new("ShaderNodeValToRGB")
                    ramp.label = "Preview terrain colour study"
                    colors = ((.10,.14,.04,1),(.36,.32,.16,1)) if original.name=="beach" else ((.13,.14,.12,1),(.42,.39,.31,1))
                    for element,color in zip(ramp.color_ramp.elements,colors):
                        element.color = color
                    links.new(noise.outputs["Fac"],ramp.inputs["Fac"])
                    links.new(ramp.outputs["Color"],shader.inputs["Base Color"])
                if original.name.startswith("dangercanyon_decor_strip_"):
                    shader.inputs["Metallic"].default_value = .15
                    if texture and texture.is_file():
                        # Emblems and narrow bands share the real CE bitmap;
                        # source UVs distinguish the complete panel from a
                        # small coloured patch. Do not flatten both to paint.
                        team='red' if 'red' in original.name else 'blue'
                        glow_path=staging/'textures'/f'levels_test_dangercanyon_bitmaps_dangercanyon_strip_{team}_glow.png'
                        if glow_path.is_file():
                            glow=nodes.new('ShaderNodeTexImage')
                            glow.image=bpy.data.images.load(str(glow_path),check_existing=True)
                            # CE stores this glow mask in the red channel for
                            # BOTH teams; the shader supplies the team hue.
                            mask=nodes.new('ShaderNodeSeparateColor'); mask.mode='RGB'
                            links.new(glow.outputs['Color'],mask.inputs['Color'])
                            tint=nodes.new('ShaderNodeMixRGB'); tint.blend_type='MULTIPLY'
                            tint.inputs[0].default_value=1
                            tint.inputs[2].default_value=(1,.012,.006,1) if team=='red' else (.012,.09,1,1)
                            links.new(mask.outputs['Red'],tint.inputs[1])
                            links.new(tint.outputs['Color'],shader.inputs['Emission Color'])
                            shader.inputs['Emission Strength'].default_value=.7
                            manifest['texture_references'].append(str(glow_path.resolve()))
                        bump_path=staging/'textures/levels_test_dangercanyon_bitmaps_dangercanyon_decor_strip_bump.png'
                        if bump_path.is_file():
                            relief=nodes.new('ShaderNodeTexImage')
                            relief.image=bpy.data.images.load(str(bump_path),check_existing=True)
                            relief.image.colorspace_settings.name='Non-Color'
                            bump=nodes.new('ShaderNodeBump')
                            bump.inputs['Strength'].default_value=.18
                            bump.inputs['Distance'].default_value=.003/METRES_PER_CE
                            links.new(relief.outputs['Color'],bump.inputs['Height'])
                            links.new(bump.outputs['Normal'],shader.inputs['Normal'])
                            manifest['texture_references'].append(str(bump_path.resolve()))
                    else:
                        shader.inputs['Base Color'].default_value=(.45,.012,.006,1) if 'red' in original.name else (.012,.09,.42,1)
                        shader.inputs['Emission Color'].default_value=shader.inputs['Base Color'].default_value
                        shader.inputs['Emission Strength'].default_value=.7
                if original.get('tst_light_atlas') or original.name=="mp lights small strips!":
                    # Keep the atlas visible: a flat emissive preview concealed
                    # incorrect whole-sheet UVs in the first game check.
                    if texture and texture.is_file():
                        cyan=nodes.new('ShaderNodeMixRGB'); cyan.blend_type='MULTIPLY'
                        cyan.name='CE light atlas tint'
                        cyan.inputs[0].default_value=1
                        authored_color=original.get('authored_light_color')
                        cyan.inputs[2].default_value=(*authored_color,1) if authored_color else (.48,.86,1,1)
                        links.new(node.outputs['Color'],cyan.inputs[1])
                        links.new(cyan.outputs['Color'],shader.inputs['Base Color'])
                        if authored_color:
                            # The derived CE shader uses the SAME atlas as its
                            # self-illumination mask: red * primary amber, then
                            # multiplied by the atlas base. Retain that detail.
                            channels=nodes.new('ShaderNodeSeparateColor')
                            channels.mode='RGB'
                            links.new(node.outputs['Color'],channels.inputs['Color'])
                            emission=nodes.new('ShaderNodeMixRGB'); emission.blend_type='MULTIPLY'
                            emission.name='Authored CE primary self-illumination'
                            emission.inputs[0].default_value=1
                            links.new(cyan.outputs['Color'],emission.inputs[1])
                            links.new(channels.outputs['Red'],emission.inputs[2])
                            links.new(emission.outputs['Color'],shader.inputs['Emission Color'])
                            manifest['authored_amber_light']={
                                'source':'amber_light.json', 'tag':original['source_shader_tag'],
                                'material_color':list(authored_color), 'primary_on_off':list(authored_color),
                                'self_illumination_map':'unchanged stock atlas, red channel',
                                'preview_note':'Shared source hue and atlas; physical lighting/exposure remain approximate'}
                        else:
                            links.new(cyan.outputs['Color'],shader.inputs['Emission Color'])
                    shader.inputs["Emission Strength"].default_value = 1.6
                    if original.get('tst_authored_light') and not (texture and texture.is_file()):
                        shader.inputs['Emission Color'].default_value=(*original['authored_light_color'],1)
                    # The stock CE shader is single-sided. Match it in Cycles
                    # as well as the viewport so reversed source faces cannot
                    # look correct here and disappear after game export.
                    mat.use_backface_culling = True
                    geometry = nodes.new('ShaderNodeNewGeometry')
                    transparent = nodes.new('ShaderNodeBsdfTransparent')
                    sided = nodes.new('ShaderNodeMixShader')
                    sided.label = 'Stock CE light: room-facing side only'
                    links.new(geometry.outputs['Backfacing'],sided.inputs[0])
                    links.new(shader.outputs['BSDF'],sided.inputs[1])
                    links.new(transparent.outputs[0],sided.inputs[2])
                    links.new(sided.outputs[0],nodes.get('Material Output').inputs['Surface'])
                    manifest['stock_light_single_sided'] = True
                if original.name=="example_tutorial_teleporter!":
                    if texture and texture.is_file():
                        # Static study of the stock Chicago dust + green mask
                        # layers. The game shader supplies animated scrolling.
                        mask_path=staging/"textures/scenery_teleporter_shield_bitmaps_teleporter_shield_mask.png"
                        mask=nodes.new("ShaderNodeTexImage")
                        mask.image=bpy.data.images.load(str(mask_path),check_existing=True)
                        mix=nodes.new("ShaderNodeMixRGB"); mix.blend_type='MULTIPLY'
                        mix.inputs[0].default_value=1
                        links.new(node.outputs['Color'],mix.inputs[1])
                        links.new(mask.outputs['Color'],mix.inputs[2])
                        emit=nodes.new('ShaderNodeEmission')
                        links.new(mix.outputs['Color'],emit.inputs['Color'])
                        emit.inputs['Strength'].default_value=3
                        transparent=nodes.new('ShaderNodeBsdfTransparent')
                        add=nodes.new('ShaderNodeAddShader')
                        links.new(transparent.outputs[0],add.inputs[0])
                        links.new(emit.outputs[0],add.inputs[1])
                        links.new(add.outputs[0],nodes.get('Material Output').inputs['Surface'])
                        manifest['texture_references'].append(str(mask_path.resolve()))
                custom_albedo = floor_albedo if floor_albedo and original.name=="metal plate floor ext" else alloy_albedo
                if custom_albedo and original.name in {"metal panels generic ext","metal plate floor ext"}:
                    coordinate = nodes.new("ShaderNodeTexCoord")
                    mapping = nodes.new("ShaderNodeVectorMath")
                    mapping.operation = "SCALE"
                    mapping.inputs[3].default_value = METRES_PER_CE/(4 if floor_albedo and original.name=="metal plate floor ext" else 2.4)
                    links.new(coordinate.outputs["Object"],mapping.inputs[0])
                    node = nodes.new("ShaderNodeTexImage")
                    node.image = bpy.data.images.load(str(custom_albedo.resolve(strict=True)),check_existing=True)
                    node.projection = "BOX"
                    node.projection_blend = .15
                    links.new(mapping.outputs["Vector"],node.inputs["Vector"])
                    tint = nodes.new("ShaderNodeMixRGB")
                    tint.blend_type = "MULTIPLY"
                    tint.inputs[0].default_value = 1
                    tint.inputs[2].default_value = ((1.05,1.05,1.0,1) if floor_albedo else (.23,.255,.28,1)) if original.name=="metal plate floor ext" else (1.45,1.38,1.24,1)
                    softened=nodes.new('ShaderNodeMixRGB')
                    softened.label='Restrain patina contrast; retain image microstructure'
                    softened.inputs[0].default_value=.08 if original.name=='metal plate floor ext' else .10
                    softened.inputs[2].default_value=(.32,.32,.32,1)
                    links.new(node.outputs['Color'],softened.inputs[1])
                    links.new(softened.outputs['Color'],tint.inputs[1])
                    links.new(tint.outputs["Color"],shader.inputs["Base Color"])
                    shader.inputs["Roughness"].default_value = .40
                    shader.inputs["Metallic"].default_value = .72 if original.name=='metal plate floor ext' else .96
                    bump = nodes.new("ShaderNodeBump")
                    bump.label = "Estimated micro relief from albedo; not authored normal map"
                    bump.inputs["Strength"].default_value = .04
                    bump.inputs["Distance"].default_value = .0004/METRES_PER_CE
                    links.new(node.outputs["Color"],bump.inputs["Height"])
                    links.new(bump.outputs["Normal"],shader.inputs["Normal"])
                    rough=nodes.new('ShaderNodeMapRange')
                    rough.label='Image-driven alloy roughness variation'
                    rough.inputs['From Min'].default_value=.18
                    rough.inputs['From Max'].default_value=.48
                    rough.inputs['To Min'].default_value=.34 if original.name=='metal plate floor ext' else .23
                    rough.inputs['To Max'].default_value=.48 if original.name=='metal plate floor ext' else .43
                    links.new(node.outputs['Color'],rough.inputs['Value'])
                    links.new(rough.outputs['Result'],shader.inputs['Roughness'])
                    rough_path=ROOT/'art/textures/forerunner_titanium_roughness.png'
                    if rough_path.is_file():
                        scratch=nodes.new('ShaderNodeTexImage')
                        scratch.label='Authored micro abrasion / roughness study'
                        scratch.image=bpy.data.images.load(str(rough_path),check_existing=True)
                        scratch.image.colorspace_settings.name='Non-Color'
                        scratch.projection='BOX'; scratch.projection_blend=.15
                        links.new(mapping.outputs['Vector'],scratch.inputs['Vector'])
                        rough.inputs['From Min'].default_value=.30
                        rough.inputs['From Max'].default_value=.60
                        links.new(scratch.outputs['Color'],rough.inputs['Value'])
                        links.new(scratch.outputs['Color'],bump.inputs['Height'])
                        bump.inputs['Strength'].default_value=.12
                        bump.inputs['Distance'].default_value=.0008/METRES_PER_CE
                        bevel=nodes.new('ShaderNodeBevel'); bevel.samples=4
                        bevel.inputs['Radius'].default_value=.008/METRES_PER_CE
                        links.new(bump.outputs['Normal'],bevel.inputs['Normal'])
                        links.new(bevel.outputs['Normal'],shader.inputs['Normal'])
                        manifest['texture_references'].append(str(rough_path))
                    manifest["texture_references"].append(str(custom_albedo.resolve()))
                if cliff_albedo and original.name=="tst_cliffs":
                    coordinate = nodes.new("ShaderNodeTexCoord")
                    mapping = nodes.new("ShaderNodeVectorMath")
                    mapping.operation = "SCALE"
                    mapping.inputs[3].default_value = METRES_PER_CE/6
                    links.new(coordinate.outputs["Object"],mapping.inputs[0])
                    node = nodes.new("ShaderNodeTexImage")
                    node.image = bpy.data.images.load(str(cliff_albedo.resolve(strict=True)),check_existing=True)
                    node.projection = "BOX"
                    node.projection_blend = .18
                    links.new(mapping.outputs["Vector"],node.inputs["Vector"])
                    links.new(node.outputs["Color"],shader.inputs["Base Color"])
                    shader.inputs["Roughness"].default_value = .88
                    bump = nodes.new("ShaderNodeBump")
                    bump.label = "Estimated cliff micro relief from albedo"
                    bump.inputs["Strength"].default_value = .10
                    bump.inputs["Distance"].default_value = .009/METRES_PER_CE
                    links.new(node.outputs["Color"],bump.inputs["Height"])
                    links.new(bump.outputs["Normal"],shader.inputs["Normal"])
                    manifest["texture_references"].append(str(cliff_albedo.resolve()))
                replacements[original.name] = mat
            slot.material = replacements[original.name]

    # Structural cores use the same stock CE floor shader at export. In the
    # material study, wall-facing polygons use calm alloy rather than tiled
    # floor plates. This is a documented preview graph, not a new game tag.
    if alloy_albedo and "metal panels generic ext" in replacements:
        armor=replacements.get("metal panels generic ext")
        dark=armor.copy(); dark.name="PREVIEW - dark structural titanium"
        for node in dark.node_tree.nodes:
            if node.type=='MIX_RGB' and node.blend_type=='MULTIPLY':
                node.inputs[2].default_value=(.65,.68,.72,1)
        dark.node_tree.nodes.get('Principled BSDF').inputs['Roughness'].default_value=.44
        recess=dark.copy(); recess.name='PREVIEW - recessed charcoal armor'
        for node in recess.node_tree.nodes:
            if node.type=='MIX_RGB' and node.blend_type=='MULTIPLY':
                node.inputs[2].default_value=(.24,.27,.30,1)
        for obj in scene.objects:
            if obj.type!='MESH' or obj.hide_render: continue
            inset=any(word in obj.name for word in ('dark_','recess','inlay','gasket'))
            index=len(obj.data.materials); obj.data.materials.append(recess if inset and obj.get('mjolnir_render_detail') else dark)
            for face in obj.data.polygons:
                source_mat=obj.data.materials[face.material_index]
                if source_mat and source_mat.get('tst_surface_role'):
                    continue
                if source_mat and source_mat.name=="PREVIEW - metal plate floor ext" and (abs(face.normal.z)<.75 or obj.get('mjolnir_render_detail')):
                    face.material_index=index

        # Fitted hero plates receive a once-per-part UV image, rather than
        # repeating cloudy world-space patina. Edge abrasion follows the part.
        # This separate UV set exists only in the preview copy; CE UVs survive.
        plate_path=ROOT/'art/textures/forerunner_fitted_plate_albedo.png'
        if plate_path.is_file():
            plate_image=bpy.data.images.load(str(plate_path),check_existing=True)
            plate_mats={}
            for style,gain in [('pale',2.65),('inset',1.65),('charcoal',.85)]:
                mat=armor.copy(); mat.name='PREVIEW - fitted '+style+' titanium'
                nodes,links=mat.node_tree.nodes,mat.node_tree.links
                uv=nodes.new('ShaderNodeUVMap'); uv.uv_map='PREVIEW fitted plate UV'
                tex=nodes.new('ShaderNodeTexImage'); tex.image=plate_image
                links.new(uv.outputs['UV'],tex.inputs['Vector'])
                tone=nodes.new('ShaderNodeMixRGB'); tone.blend_type='MULTIPLY'
                tone.inputs[0].default_value=1; tone.inputs[2].default_value=(gain,gain*.97,gain*.92,1)
                contrast=nodes.new('ShaderNodeBrightContrast'); contrast.inputs['Contrast'].default_value=0
                links.new(tex.outputs['Color'],contrast.inputs['Color'])
                links.new(contrast.outputs['Color'],tone.inputs[1])
                shader=nodes.get('Principled BSDF')
                info=nodes.new('ShaderNodeObjectInfo')
                variation=nodes.new('ShaderNodeMapRange')
                variation.inputs['To Min'].default_value=.92; variation.inputs['To Max'].default_value=1.08
                links.new(info.outputs['Random'],variation.inputs['Value'])
                tint=nodes.new('ShaderNodeMixRGB'); tint.blend_type='MULTIPLY'; tint.inputs[0].default_value=1
                links.new(tone.outputs['Color'],tint.inputs[1]); links.new(variation.outputs['Result'],tint.inputs[2])
                links.new(tint.outputs['Color'],shader.inputs['Base Color'])
                rough_source=shader.inputs['Roughness'].links[0].from_socket
                offset=nodes.new('ShaderNodeMapRange'); offset.inputs['To Min'].default_value=-.015; offset.inputs['To Max'].default_value=.025
                links.new(info.outputs['Random'],offset.inputs['Value'])
                rough_add=nodes.new('ShaderNodeMath'); rough_add.operation='ADD'
                links.new(rough_source,rough_add.inputs[0]); links.new(offset.outputs['Result'],rough_add.inputs[1])
                links.new(rough_add.outputs[0],shader.inputs['Roughness'])
                plate_mats[style]=mat
            for obj in scene.objects:
                if obj.type!='MESH' or not obj.get('mjolnir_render_detail'): continue
                name=obj.name
                if name.startswith('arrival_fitted_titanium_frame'): style='pale'
                elif name.startswith(('tower_side_fitted_armor_leaf','parapet_fitted_cap_plate')): style='inset'
                elif name.startswith(('parapet_charcoal_insert','arrival_inner_jamb_liner','parapet_clasp_fitted_crown','arrival_jamb_fitted_dark_insert')): style='charcoal'
                else: continue
                # Legacy preview finishes apply only to stock fallback faces.
                # Authored roles already carry their exported finish and UVs;
                # avoid even adding an active preview UV map for those parts.
                if all(obj.data.materials[face.material_index].get('tst_surface_role')
                       for face in obj.data.polygons):
                    continue
                main=max(obj.data.polygons,key=lambda p:p.area)
                normal_axis=max(range(3),key=lambda a:abs(main.normal[a]))
                axes=[a for a in range(3) if a!=normal_axis]
                lo=[min(v.co[a] for v in obj.data.vertices) for a in axes]
                hi=[max(v.co[a] for v in obj.data.vertices) for a in axes]
                uv=obj.data.uv_layers.new(name='PREVIEW fitted plate UV')
                orientation=sum(name.encode())%8
                for face in obj.data.polygons:
                    for loop_index in face.loop_indices:
                        v=obj.data.vertices[obj.data.loops[loop_index].vertex_index].co
                        u,w=[(v[a]-lo[i])/max(hi[i]-lo[i],1e-6) for i,a in enumerate(axes)]
                        for _ in range(orientation%4): u,w=w,1-u
                        uv.data[loop_index].uv=(1-u if orientation>=4 else u,w)
                index=len(obj.data.materials); obj.data.materials.append(plate_mats[style])
                # Side returns use the quiet metal. Collapsing their UVs onto
                # the front plate's edge would stretch chips into long stripes.
                side_index=len(obj.data.materials); obj.data.materials.append(armor if style=='pale' else dark)
                groove_index=len(obj.data.materials); obj.data.materials.append(recess)
                for face in obj.data.polygons:
                    previous=obj.data.materials[face.material_index]
                    if previous.get('tst_surface_role'):
                        continue
                    if obj.get('engraved_armor') and previous in (dark,recess): face.material_index=groove_index
                    else:
                        threshold=.6 if name.startswith('parapet_clasp_fitted_crown_wrap') else .985
                        face.material_index=index if abs(face.normal[normal_axis])>threshold else side_index
                obj['preview_plate_finish']='Imagegen single-plate albedo; dedicated UVs, stock CE UVs retained'
            manifest['texture_references'].append(str(plate_path))

            # Sparse abrasion is restricted to real narrow chamfer faces.
            # Broad face grain and the accepted floor shader stay unchanged.
            wear=armor.copy(); wear.name='PREVIEW - exposed titanium edge abrasion'
            nodes,links=wear.node_tree.nodes,wear.node_tree.links
            shader=nodes.get('Principled BSDF')
            base=shader.inputs['Base Color'].links[0].from_socket
            abrasion=next(n for n in nodes if n.type=='TEX_IMAGE' and 'roughness' in n.image.name)
            mask=nodes.new('ShaderNodeMapRange')
            mask.inputs['From Min'].default_value=.49; mask.inputs['From Max'].default_value=.58
            mask.inputs['To Min'].default_value=0; mask.inputs['To Max'].default_value=.85
            links.new(abrasion.outputs['Color'],mask.inputs['Value'])
            edge_color=nodes.new('ShaderNodeMixRGB'); edge_color.inputs[2].default_value=(.72,.75,.78,1)
            links.new(mask.outputs['Result'],edge_color.inputs[0]); links.new(base,edge_color.inputs[1])
            links.new(edge_color.outputs[0],shader.inputs['Base Color'])
            for obj in scene.objects:
                if obj.type!='MESH' or not obj.get('mjolnir_render_detail'): continue
                if not any(word in obj.name for word in ('frame','border','cap','surround','crown','bright_edge','precision_lip')): continue
                if sum(obj.name.encode())%4==0: continue
                slot=len(obj.data.materials); obj.data.materials.append(wear)
                for face in obj.data.polygons:
                    previous=obj.data.materials[face.material_index]
                    # The initial material-slot guard is insufficient: these
                    # later face assignments must preserve authored roles too.
                    if previous.get('tst_surface_role') or previous==recess: continue
                    verts=[obj.data.vertices[v].co for v in face.vertices]
                    perimeter=sum((b-a).length for a,b in zip(verts,verts[1:]+verts[:1]))
                    width=2*face.area*METRES_PER_CE/max(perimeter,1e-8)
                    if .002<width<.045: face.material_index=slot

def load_model(staging,tag,group,position,yaw,target,manifest):
    filename = tag.replace("\\","_").replace("/","_").replace(" ","_")+"__"+group+".gltf"
    model = staging/"models"/filename
    if not model.is_file():
        manifest["missing_reference_assets"].append(str(model))
        return False
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=str(model))
    imported = set(bpy.data.objects)-before
    from mjolnir_level.native_scene import bind_ce_teleporter_effects
    manifest.setdefault('ce_effect_materials',[]).extend(bind_ce_teleporter_effects(imported,staging))
    anchor = bpy.data.objects.new("CE REFERENCE - "+tag.rsplit("\\",1)[-1],None)
    target.objects.link(anchor)
    anchor.location = Vector(position)/METRES_PER_CE
    anchor.rotation_euler.z = math.radians(yaw)
    # glTF importer already converts metres through scene.unit_settings.scale_length.
    anchor.scale = (1,1,1)
    anchor["mjolnir_preview_only"] = True
    anchor["reference_source"] = str(model.resolve())
    for obj in imported:
        if any(c.hide_render for c in obj.users_collection):
            # glTF armature display-shape meshes live in glTF_not_exported.
            # Preserve their collection's render exclusion when relinking.
            obj.hide_render = True
        link_only(obj,target)
        if obj.parent not in imported:
            obj.parent = anchor
    manifest["model_references"].append(str(model.resolve()))
    return True

def proxy(item,kind,target,manifest):
    dimensions = (7,7,13.57) if kind=="tree" else (3.6,3.6,3) if kind=="rock" else (5,3,2.4)
    position = Vector(item["position_m"])
    position.z += dimensions[2]/2
    bpy.ops.mesh.primitive_cube_add(size=1,location=position/METRES_PER_CE)
    obj = bpy.context.object
    obj.name = "PROXY BOUNDS - "+kind.upper()
    obj.scale = Vector(dimensions)/METRES_PER_CE
    bpy.ops.object.transform_apply(location=False,rotation=False,scale=True)
    obj.rotation_euler.z = math.radians(item.get("yaw_degrees",0))
    obj.data.materials.append(material("proxy outline",(.12,.34,.17)))
    wire = obj.modifiers.new("Explicit proxy bounds","WIREFRAME")
    wire.thickness = .04/METRES_PER_CE
    link_only(obj,target)
    manifest["proxy_bounds"].append({"kind":kind,"position_m":item["position_m"]})

def lighting(scene,placements,target):
    world = bpy.data.worlds.new("PREVIEW - temperate daylight")
    world.use_nodes = True
    sky = world.node_tree.nodes.new("ShaderNodeTexSky")
    sky.sky_type = "MULTIPLE_SCATTERING" if bpy.app.version >= (5,0,0) else "NISHITA"
    sky.sun_disc = False
    sky.sun_elevation = math.radians(37)
    sky.sun_rotation = math.atan2(.3,1.25)
    world.node_tree.links.new(sky.outputs["Color"],world.node_tree.nodes["Background"].inputs["Color"])
    nodes,links=world.node_tree.nodes,world.node_tree.links
    coordinates=nodes.new('ShaderNodeTexCoord')
    cloud=nodes.new('ShaderNodeTexNoise'); cloud.inputs['Scale'].default_value=5
    cloud.inputs['Detail'].default_value=4; cloud.inputs['Roughness'].default_value=.65
    links.new(coordinates.outputs['Normal'],cloud.inputs['Vector'])
    mask=nodes.new('ShaderNodeValToRGB')
    mask.color_ramp.elements[0].position=.53; mask.color_ramp.elements[1].position=.69
    links.new(cloud.outputs['Fac'],mask.inputs[0])
    blend=nodes.new('ShaderNodeMixRGB'); blend.inputs[2].default_value=(12,12,12,1)
    links.new(mask.outputs[0],blend.inputs[0]); links.new(sky.outputs['Color'],blend.inputs[1])
    links.new(blend.outputs[0],nodes['Background'].inputs['Color'])
    world.node_tree.nodes["Background"].inputs["Strength"].default_value = .14
    # Separate the camera backdrop from illumination for this finite enclosed
    # map preview; the distant ground context is outside the authored level.
    camera_color=nodes.new('ShaderNodeMixRGB')
    camera_color.inputs[1].default_value=(.20,.43,.88,1)
    camera_color.inputs[2].default_value=(.95,.98,1,1)
    links.new(mask.outputs[0],camera_color.inputs[0])
    camera_sky=nodes.new('ShaderNodeBackground'); camera_sky.inputs['Strength'].default_value=1.2
    links.new(camera_color.outputs[0],camera_sky.inputs['Color'])
    rays=nodes.new('ShaderNodeLightPath'); mix=nodes.new('ShaderNodeMixShader')
    visible=nodes.new('ShaderNodeMath'); visible.operation='MAXIMUM'
    links.new(rays.outputs['Is Camera Ray'],visible.inputs[0])
    # Reflections use the physical sky; the saturated backdrop is camera-only.
    visible.inputs[1].default_value=0
    links.new(visible.outputs[0],mix.inputs[0])
    links.new(nodes['Background'].outputs[0],mix.inputs[1]); links.new(camera_sky.outputs[0],mix.inputs[2])
    links.new(mix.outputs[0],nodes['World Output'].inputs['Surface'])
    scene.world = world
    data = bpy.data.lights.new("PREVIEW - afternoon sun","SUN")
    data.energy = 4.6
    data.color = (1,.91,.78)
    data.angle = math.radians(3)
    sun = bpy.data.objects.new(data.name,data)
    target.objects.link(sun)
    sun.rotation_euler = Vector((.8,1,-1)).to_track_quat("-Z","Y").to_euler()
    # Broad sky-bounce study keeps the eastern base readable below its cliff.
    # Like the other preview lights, this is not exported as baked game light.
    fill=bpy.data.lights.new("PREVIEW - eastern sky bounce","AREA")
    fill.energy=12000/METRES_PER_CE**2
    fill.shape='DISK'; fill.size=18/METRES_PER_CE
    fill.color=(.82,.91,1)
    bounce=bpy.data.objects.new(fill.name,fill); target.objects.link(bounce)
    bounce.location=Vector((49,-10,25))/METRES_PER_CE
    point_at(bounce,(54,0,2))
    fill=bpy.data.lights.new("PREVIEW - broad wall sky bounce","AREA")
    fill.energy=15000/METRES_PER_CE**2
    fill.shape='DISK'; fill.size=110/METRES_PER_CE
    fill.color=(.9,.94,1)
    bounce=bpy.data.objects.new(fill.name,fill); target.objects.link(bounce)
    bounce.location=Vector((0,-25,50))/METRES_PER_CE
    point_at(bounce,(0,35,15))
    fill=bpy.data.lights.new("PREVIEW - balcony open sky reflection","AREA")
    fill.energy=8000/METRES_PER_CE**2
    fill.shape='DISK'; fill.size=32/METRES_PER_CE
    fill.color=(1,.94,.84)
    bounce=bpy.data.objects.new(fill.name,fill); target.objects.link(bounce)
    bounce.location=Vector((-65,8,24))/METRES_PER_CE
    point_at(bounce,(-35,29,12))
    for index,item in enumerate(placements.get("lights",[])):
        data = bpy.data.lights.new(f"PREVIEW - authored fixture wash {index+1}","POINT")
        data.energy = (180 if item["position_m"][2]>2 else 240)/METRES_PER_CE**2
        data.color = (1.0,.87,.68)
        data.shadow_soft_size = .30/METRES_PER_CE
        obj = bpy.data.objects.new(data.name,data)
        target.objects.link(obj)
        position = Vector(item["position_m"])
        position.z += .18 if position.z>2 else .6
        obj.location = position/METRES_PER_CE
        obj["preview_note"] = "Lighting study at authored fixture; not a game light bake"
    for lens in list(scene.objects):
        if not lens.get("authored_light_lens"):
            continue
        enclosed = facility_fixture(lens)
        data = bpy.data.lights.new("PREVIEW wash - "+lens.name,"AREA")
        data.shape = "RECTANGLE"
        size=lens.get('preview_light_size',(2.8,.45) if enclosed else (.28,1.35))
        data.size = size[0]/METRES_PER_CE
        data.size_y = size[1]/METRES_PER_CE
        # Area-light power scales with area when metres become CE units.
        # Ceiling fixtures illuminate the enclosed route through real bounces;
        # no ambient fill or increased exposure disguises missing apertures.
        data.energy = lens.get('preview_light_power',900 if enclosed else 100)/METRES_PER_CE**2
        data.color = lens.get('preview_light_color',(.80,.90,1.0) if enclosed else (1.0,.78,.50))
        data.spread = math.radians(lens.get('preview_light_spread_degrees',180))
        obj = bpy.data.objects.new(data.name,data)
        target.objects.link(obj)
        obj.location = sum((lens.matrix_world @ v.co for v in lens.data.vertices),Vector())/len(lens.data.vertices)
        direction=Vector(lens.get('preview_light_direction',(0,0,-1))).normalized()
        obj.location += direction*.025/METRES_PER_CE
        tangent=lens.get('preview_light_tangent')
        if tangent is not None:
            x=Vector(tangent)
            if x.length<.99 or abs(x.normalized().dot(direction))>1e-5:
                raise ValueError('Invalid AREA-light long-axis tangent: '+lens.name)
            x.normalize()
            z=-direction
            y=z.cross(x).normalized()
            obj.rotation_euler=Matrix((x,y,z)).transposed().to_euler()
            # Long atlas lenses consist of many repeated quads. Bound them
            # in the authored light frame instead of accumulating float32
            # vertex sums; the physical run remains one rectangular source.
            points=[lens.matrix_world@vertex.co for vertex in lens.data.vertices]
            center=Vector()
            for axis in (x,y,direction):
                values=[point.dot(axis) for point in points]
                center+=axis*((min(values)+max(values))*.5)
            obj.location=center+direction*.025/METRES_PER_CE
        else:
            obj.rotation_euler=direction.to_track_quat('-Z','Y').to_euler()
        obj["preview_note"] = "Localized wash at authored shader light lens; not baked game lighting"
        obj["authored_lens"] = lens.name
        obj["mjolnir_preview_only"] = True

def layout_overlay(scene,placements):
    """Diagram symbols above the actual map, authored only from placement data."""
    target = collection(scene,"gameplay layout overlay")
    z = 30.0
    palette = {"red":(.9,.025,.015), "blue":(.025,.25,1), "neutral":(.95,.95,.88),
               "planned":(1,.66,.04), "teleport":(.6,.12,1), "ink":(.012,.017,.025)}
    mats = {}
    for name,color in palette.items():
        mat = material("diagram "+name,color)
        nodes,links = mat.node_tree.nodes,mat.node_tree.links
        emission = nodes.new("ShaderNodeEmission")
        emission.inputs["Color"].default_value = (*color,1)
        emission.inputs["Strength"].default_value = 1
        links.new(emission.outputs[0],nodes.get("Material Output").inputs["Surface"])
        mats[name] = mat
    def shape(name,points,color,height=z):
        mesh = bpy.data.meshes.new("DIAGRAM "+name)
        mesh.from_pydata([(x/METRES_PER_CE,y/METRES_PER_CE,height/METRES_PER_CE) for x,y in points],[],[tuple(range(len(points)))])
        mesh.update()
        obj = bpy.data.objects.new("DIAGRAM "+name,mesh)
        target.objects.link(obj)
        obj.data.materials.append(mats[color])
        obj["mjolnir_preview_only"] = True
        return obj
    def disc(name,x,y,r,color,height=z):
        return shape(name,[(x+r*math.cos(i*math.tau/32),y+r*math.sin(i*math.tau/32)) for i in range(32)],color,height)
    def line(name,points,color,width=.14,height=z):
        data = bpy.data.curves.new("DIAGRAM "+name,"CURVE")
        data.dimensions = "3D"
        data.bevel_depth = width/METRES_PER_CE
        data.bevel_resolution = 0
        spline = data.splines.new("POLY")
        spline.points.add(len(points)-1)
        for point,(x,y) in zip(spline.points,points):
            point.co = (x/METRES_PER_CE,y/METRES_PER_CE,height/METRES_PER_CE,1)
        obj = bpy.data.objects.new(data.name,data)
        target.objects.link(obj)
        data.materials.append(mats[color])
        return obj
    def label(text,x,y,color="neutral",size=1.5):
        data = bpy.data.curves.new("DIAGRAM label "+text,"FONT")
        data.body = text
        data.size = size/METRES_PER_CE
        data.align_x = "CENTER"
        data.align_y = "CENTER"
        obj = bpy.data.objects.new(data.name,data)
        target.objects.link(obj)
        obj.location = (x/METRES_PER_CE,y/METRES_PER_CE,(z+.4)/METRES_PER_CE)
        data.materials.append(mats[color])
    for index,item in enumerate(placements.get("spawns",[])):
        x,y,_ = item["position_m"]
        team = item.get("team",-1)
        color = "red" if team==0 else "blue" if team==1 else "neutral"
        disc(f"start border {index}",x,y,1.05,"ink")
        yaw = math.radians(item.get("yaw_degrees",0))
        triangle = [(1.0,0),(-.65,.65),(-.65,-.65)]
        shape(f"start {index}",[(x+u*math.cos(yaw)-v*math.sin(yaw),y+u*math.sin(yaw)+v*math.cos(yaw)) for u,v in triangle],color,z+.1)
    for item in placements.get("flags",[]):
        x,y,_ = item["position_m"]
        color = "red" if item["team"]==0 else "blue"
        disc("flag backing",x,y,1.8,"ink",z+.15)
        shape("flag",[(x,y+1.4),(x+1.4,y),(x,y-1.4),(x-1.4,y)],color,z+.2)
        label("FLAG",x,y+3,color,1.65)
    for index,point in enumerate(placements.get("objective_markers",{}).get("king",{}).get("positions_m",[]),1):
        x,y,_ = point
        line(f"planned hill {index}",[(x+4.5*math.cos(i*math.tau/64),y+4.5*math.sin(i*math.tau/64)) for i in range(65)],"planned",.16)
        label(f"H{index}*",x,y+6,"planned",1.7)
    ball = placements.get("objective_markers",{}).get("oddball",{}).get("position_m")
    if ball:
        disc("planned ball",ball[0],ball[1],.9,"planned")
        label("BALL*",ball[0],ball[1]-2.5,"planned",1.7)
    for item in placements.get("teleporters",[]):
        ax,ay,_ = item["from_m"]
        bx,by,_ = item["to_m"]
        line("authored teleport link",[(ax,ay),(bx,by)],"teleport",.16)
        direction = Vector((bx-ax,by-ay)).normalized()
        normal = Vector((-direction.y,direction.x))
        tip = Vector((bx,by))-direction*1.7
        back = tip-direction*2
        shape("one-way arrow",[tuple(tip),tuple(back+normal),tuple(back-normal)],"teleport",z+.1)
        for x,y,kind in ((ax,ay,"IN"),(bx,by,"OUT")):
            disc("teleport border",x,y,1.5,"ink")
            disc("teleport endpoint",x,y,1.1,"teleport",z+.1)
            label(f"T{item['channel']} {kind}",x,y+3,"teleport",1.6)
    # Legend sits outside playable bounds. No speculative route lines.
    shape("legend",[(-89,-54),(89,-54),(89,-65),(-89,-65)],"ink",z+.2)
    label("TST  /  AUTHORED GAMEPLAY LAYOUT  /  150 x 84 m",0,-56.5,size=2.0)
    label("RED / BLUE: team starts + flags    WHITE: neutral starts    PURPLE: one-way teleport links",0,-60,size=1.7)
    label("* AMBER: planned ball / hill markers; only CTF and Slayer currently playable",0,-63,"planned",1.6)
    for obj in target.all_objects:
        obj.visible_shadow = False
        obj.visible_diffuse = False
        obj.visible_glossy = False
    target.hide_render = True
    target.hide_viewport = True
    return target

def main():
    args = arguments()
    source = args.blend.resolve(strict=True)
    placements_path = args.placements.resolve(strict=True)
    source_hash,placements_hash = digest(source),digest(placements_path)
    placements = json.loads(placements_path.read_text(encoding="utf-8"))
    bpy.ops.wm.open_mainfile(filepath=str(source),load_ui=False)
    scene = bpy.context.scene
    args.out.mkdir(parents=True,exist_ok=True)
    preview_file = (args.out/"preview.blend").resolve()
    if preview_file == source:
        raise ValueError("Preview destination cannot overwrite the source Blender file")
    manifest = {"source_blend":str(source),"source_sha256":source_hash,
        "placements_sha256":placements_hash,"engine":args.engine,"samples":args.samples,
        "resolution":[args.width,args.height],"units":"1 Blender unit = 3.048 m",
        "disclaimer":"Blender design preview, not in-game evidence. CE reference scenery differs from the runtime's B30 replacements. Lighting and water are preview approximations.",
        "texture_references":[],"model_references":[],"missing_reference_assets":[],"proxy_bounds":[],"views":{}}
    for obj in scene.objects:
        if obj.type in {"LIGHT","CAMERA"}:
            obj.hide_render = True
    terrain = bpy.data.objects["TST_sealed_terrain_and_sky"]
    terrain.data = terrain.data.copy()
    bm = bmesh.new()
    bm.from_mesh(terrain.data)
    sky_faces = [face for face in bm.faces if terrain.data.materials[face.material_index].name=="+sky"]
    manifest["removed_preview_sky_faces"] = len(sky_faces)
    bmesh.ops.delete(bm,geom=sky_faces,context="FACES")
    bm.to_mesh(terrain.data)
    bm.free()
    authored_surfaces=snapshot_authored_surfaces(scene)
    prepare_materials(scene,args.staging,manifest,args.alloy_albedo,args.floor_albedo,args.cliff_albedo)
    manifest['authored_surface_preservation']=assert_authored_surfaces(scene,authored_surfaces)
    for obj in scene.objects:
        if obj.type=='MESH' and facility_fixture(obj) and obj.get('authored_light_lens') and obj.get('light_atlas_pixels'):
            # Keep the exported atlas UVs and image-driven emission. Only the
            # preview radiance changes, so whole-sheet UV mistakes stay visible.
            for slot in obj.material_slots:
                mat=slot.material.copy(); slot.material=mat
                shader=mat.node_tree.nodes.get('Principled BSDF')
                shader.inputs['Emission Strength'].default_value=obj.get('preview_emission_strength',3.2)
                if obj.get('facility_status_light') and not mat.get('tst_authored_light'):
                    # The gold atlas rectangle must retain its actual hue;
                    # the generic cyan treatment otherwise turns it green.
                    tint=mat.node_tree.nodes.get('CE light atlas tint')
                    if tint:
                        tint.inputs[2].default_value=(1,1,1,1)
                    else:
                        # A source-only preview may have no installed CE atlas.
                        shader.inputs['Emission Color'].default_value=(1,.4,.06,1)
        if obj.type=='MESH' and obj.get('preview_emission_color') and not obj.get('light_atlas_pixels'):
            for slot in obj.material_slots:
                mat=slot.material.copy(); slot.material=mat
                shader=mat.node_tree.nodes.get('Principled BSDF')
                color=tuple(obj['preview_emission_color'])+(1,)
                shader.inputs['Base Color'].default_value=color
                for link in list(shader.inputs['Base Color'].links): mat.node_tree.links.remove(link)
                shader.inputs['Emission Color'].default_value=color
                shader.inputs['Emission Strength'].default_value=obj.get('preview_emission_strength',5)
    refs = collection(scene,"scenery references and bounds")
    sys.path.insert(0,str(REPO/"tools/blender"))
    if args.native_assets:
        from mjolnir_level.native_scene import load_runtime_scenery
        native_doc = json.loads(args.native_assets.read_text(encoding="utf-8"))
        if native_doc["placements_sha256"] != placements_hash:
            raise ValueError("Native scenery preview is stale: rerun prepare_native_preview.py for these placements")
        if native_doc.get('authored_decor'):
            decor=native_doc['authored_decor']
            if digest(Path(decor['path']))!=decor['sha256']:
                raise ValueError('Native authored decor is stale: rerun prepare_native_preview.py')
        manifest["native_scenery"] = load_runtime_scenery(args.native_assets,refs)
    if args.cyborg:
        from mjolnir_level.native import import_reference
        anchor, objects = import_reference(args.cyborg,refs,"CYBORG - ACTUAL SCALE REFERENCE")
        from mjolnir_level.native_scene import bind_ce_cyborg_materials
        manifest.setdefault('ce_cyborg_materials',[]).extend(bind_ce_cyborg_materials(objects,args.cyborg.parent.parent))
        anchor.location = Vector((-51,0,.45))/METRES_PER_CE
        anchor.rotation_euler.z = math.radians(135)
        bpy.context.view_layer.update()
        points = [obj.matrix_world @ Vector(corner) for obj in objects if obj.type=="MESH" and not obj.hide_render for corner in obj.bound_box]
        manifest["cyborg_reference"] = {"source":str(args.cyborg.resolve()),
            "height_m":round((max(p.z for p in points)-min(p.z for p in points))*METRES_PER_CE,3),
            "note":"Unscaled imported rest-pose model; not the movement collision capsule"}
        facility_anchor, facility_objects = import_reference(args.cyborg,refs,"CYBORG - FACILITY SCALE REFERENCE")
        manifest['ce_cyborg_materials'].extend(bind_ce_cyborg_materials(facility_objects,args.cyborg.parent.parent))
        facility_anchor.location = Vector((7.0,46.0,.32))/METRES_PER_CE
        facility_anchor.rotation_euler.z = math.radians(90)
        manifest['facility_cyborg_reference'] = {'position_m':[7.0,46.0,.32],
            'note':'Preview-only actual cyborg model for room scale; no gameplay spawn added.'}
    if args.pcg_assets:
        from mjolnir_level.pcg_scene import load_pcg
        pcg_doc=json.loads(args.pcg_assets.read_text())
        if pcg_doc['source']['sha256']!=source_hash:
            raise ValueError('PCG preview is stale: regenerate scatter from current source')
        manifest['native_pcg']=load_pcg(args.pcg_assets,refs)
    if not args.no_scenery:
        for item in ([] if args.native_assets else placements.get("scenery",[])):
            kind = "tree" if "trees" in item["tag"] else "rock"
            if not args.staging or not load_model(args.staging,item["tag"],"scen",item["position_m"],item.get("yaw_degrees",0),refs,manifest):
                proxy(item,kind,refs,manifest)
        for item in placements.get("vehicles",[]):
            if not args.staging or not load_model(args.staging,item["tag"],"vehi",item["position_m"],item.get("yaw_degrees",0),refs,manifest):
                proxy(item,"vehicle",refs,manifest)
        if args.staging:
            for item in placements.get("lights",[]):
                load_model(args.staging,item["tag"],"lifi",item["position_m"],item.get("yaw_degrees",0),refs,manifest)
            for item in placements.get("teleporters",[]):
                for endpoint in ("from","to"):
                    if not item.get("scenery",True) or not item.get(f"{endpoint}_scenery",True):
                        continue
                    load_model(args.staging,r"scenery\teleporter_base\teleporter_base","scen",item[f"{endpoint}_m"],item.get(f"{endpoint}_yaw_degrees",0),refs,manifest)
    sys.path.insert(0,str(ROOT))
    from preview_surface_detail import enhance
    enhance(scene,manifest)
    environment = collection(scene,"environment and lights")
    lighting(scene,placements,environment)
    bpy.ops.mesh.primitive_plane_add(size=2000/METRES_PER_CE,location=(0,0,-2.5/METRES_PER_CE))
    sea = bpy.context.object
    sea.name = "PREVIEW - distant context below enclosed basin"
    sea.hide_render = True
    sea.data.materials.append(material("ocean",(.025,.09,.13),.25,.08))
    link_only(sea,environment)
    overlay = layout_overlay(scene,placements)
    cameras = {}
    for name,view in VIEWS.items():
        camera_data = bpy.data.cameras.new("PREVIEW CAMERA - "+name)
        camera = bpy.data.objects.new(camera_data.name,camera_data)
        environment.objects.link(camera)
        camera_data.clip_start = .03/METRES_PER_CE
        camera_data.clip_end = 4000/METRES_PER_CE
        camera.location = Vector(view["position"])/METRES_PER_CE
        point_at(camera,view["target"])
        camera_data.type = "ORTHO" if "ortho" in view else "PERSP"
        camera_data.ortho_scale = view.get("ortho",100)/METRES_PER_CE
        camera_data.lens = view.get("lens",35)
        cameras[name] = camera
    if args.engine=="cycles":
        scene.render.engine = "CYCLES"
        scene.cycles.samples = args.samples
        scene.cycles.use_denoising = True
        scene.cycles.device = "CPU"
        manifest["render_device"] = "CPU"
        if args.device=="auto":
            preferences = bpy.context.preferences.addons["cycles"].preferences
            for backend in ("OPTIX","CUDA","HIP","ONEAPI","METAL"):
                try:
                    preferences.compute_device_type = backend
                    preferences.refresh_devices()
                    devices = [device for device in preferences.devices if device.type==backend]
                    if not devices:
                        continue
                    for device in preferences.devices:
                        device.use = device in devices
                    scene.cycles.device = "GPU"
                    manifest["render_device"] = backend+": "+", ".join(device.name for device in devices)
                    break
                except (TypeError,ValueError,RuntimeError):
                    continue
        scene.cycles.max_bounces = 6
        scene.cycles.transparent_max_bounces = 16
    else:
        try:
            scene.render.engine = "BLENDER_EEVEE_NEXT"
        except TypeError:
            scene.render.engine = "BLENDER_EEVEE"
        if hasattr(scene,"eevee") and hasattr(scene.eevee,"taa_render_samples"):
            scene.eevee.taa_render_samples = args.samples
    scene.render.resolution_x,scene.render.resolution_y = args.width,args.height
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.view_settings.view_transform = "AgX"
    scene.view_settings.look = "AgX - Medium High Contrast"
    scene.view_settings.exposure = 0
    scene.render.film_transparent = False
    for name in args.views:
        view = VIEWS[name]
        # Match the approved concept's individual panels with real camera renders.
        scene.render.resolution_y = round(args.width/view["aspect"]) if "aspect" in view else args.height
        scene.camera = cameras[name]
        overlay.hide_render = name!="layout"
        scene.render.filepath = str((args.out/(name+".png")).resolve())
        original_indices = []
        if name == "pcg":
            from mjolnir_level.surface import review_materials
            original_indices = [(obj,[p.material_index for p in obj.data.polygons]) for obj in scene.objects
                                if obj.type=="MESH" and not obj.hide_render and not obj.get("mjolnir_preview_only")]
            manifest["pcg_colors"] = review_materials(scene)
            refs.hide_render = True
        started = time.perf_counter()
        bpy.ops.render.render(write_still=True)
        if name == "pcg":
            refs.hide_render = False
            for obj,indices in original_indices:
                for poly,index in zip(obj.data.polygons,indices):
                    poly.material_index = index
        manifest["views"][name] = {**view,"file":scene.render.filepath,
            "resolution":[scene.render.resolution_x,scene.render.resolution_y],
            "seconds":round(time.perf_counter()-started,2)}
        print(f"TST_PREVIEW {name}: {scene.render.filepath}",flush=True)
    overlay.hide_render = True
    scene.camera = cameras["facility-interior"] if 'facility-interior' in args.views else cameras["exterior"]
    if 'facility-interior' in args.views:
        scene.render.resolution_y=round(args.width/VIEWS['facility-interior']['aspect'])
        scene.cycles.preview_samples=16
        scene.cycles.use_preview_denoising=True
        for screen in bpy.data.screens:
            for area in screen.areas:
                if area.type=='VIEW_3D':
                    area.spaces.active.region_3d.view_perspective='CAMERA'
                    area.spaces.active.overlay.show_overlays=False
                    area.spaces.active.shading.type='RENDERED'
    scene["mjolnir_preview_only"] = True
    scene["preview_source"] = str(source)
    readme = bpy.data.texts.new("README - PREVIEW ONLY")
    readme.write("This is an isolated Blender design preview. DO NOT EXPORT.\n"
        "Open levels/test/tst/tst.blend for the actual authoring source.\n"
        "Sky faces were removed in this copy for cameras. PREVIEW ONLY collections\n"
        "contain local CE/native game references, approximate water/terrain materials,\n"
        "daylight, authored-fixture light studies, cameras and a layout diagram.\n"
        "No geometry design was changed. Imported stock textures remain external.\n"
        "Switch scene camera between PREVIEW CAMERA objects; enable both\n"
        "render/viewport visibility on gameplay layout overlay for the layout view.\n"
        "Preview materials and fixture illumination are not in-game evidence.\n")
    manifest['authored_surface_preservation']=assert_authored_surfaces(scene,authored_surfaces)
    bpy.ops.wm.save_as_mainfile(filepath=str(preview_file),check_existing=False)
    manifest["preview_blend"] = str(preview_file)
    manifest["actual_engine"] = scene.render.engine
    surface_library = ROOT/'surfaces.json'
    manifest['source_surface_library'] = {
        'path':str(surface_library.resolve()),
        'sha256':digest(surface_library),
        'surfaces':json.loads(surface_library.read_text())['surfaces'],
        'scope':'Authored role materials are retained from the source blend; rebuild geometry after editing this library.'}
    manifest["material_study"] = {
        "scope":"Fallback preview graphs for stock CE slots only. Authored tst_surface_role materials retain their source graphs; their definitions are recorded in source_surface_library.",
        "authored_albedo":str(args.alloy_albedo.resolve()) if args.alloy_albedo else None,
        "floor_albedo":str(args.floor_albedo.resolve()) if args.floor_albedo else None,
        "cliff_albedo":str(args.cliff_albedo.resolve()) if args.cliff_albedo else None,
        "cliff_tile_m":6,
        "floor_tile_m":4 if args.floor_albedo else 2,
        "alloy_tile_m":2.4, "panel_multiplier":[1.45,1.38,1.24], "floor_beam_multiplier":[1.05,1.05,1.0] if args.floor_albedo else [.23,.255,.28],
        "structural_core_multiplier":[.65,.68,.72], "recess_multiplier":[.24,.27,.30],
        "roughness":"armor 0.23-0.43; floor 0.34-0.48 from generated Non-Color abrasion image (albedo fallback)","metallic":{"armor":.96,"floor":.72},"normal_map":"none; 0.8 mm estimated abrasion bump plus 8 mm shader bevel",
        "fitted_plates":"Dedicated preview UVs map one generated edge-worn image per part; CE UVs retained. Pale/inset/charcoal reflectance variants.",
        "export_assignments":"Authored architectural roles share source materials and UVs. Stock light lenses use the Blood Gulch atlas with single-sided faces. Fallback preview graphs are not exported.",
        "terrain":"Installed CE grass/soil detail and actual source UV mask; see surface_detail_study. Native rock normals/AO plus approximate layered weathering.",
        "light_study":"Local area lights read each authored lens's power, size, direction and color metadata, scaled to CE units; not a game bake.",
        "environment":"Southwest daylight key and physical sky illumination/reflections; procedural camera clouds. Enclosed coastal map preview. Ocean context hidden."
    }
    manifest["source_unchanged"] = source_hash==digest(source) and placements_hash==digest(placements_path)
    (args.out/"preview-manifest.json").write_text(json.dumps(manifest,indent=2)+"\n",encoding="utf-8")
    if not manifest["source_unchanged"]:
        raise RuntimeError("Source changed during preview rendering; inspect before continuing")

if __name__=="__main__":
    main()
