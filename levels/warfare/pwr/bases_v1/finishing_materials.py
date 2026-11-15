"""Native Forerunner surface finish for the Blender art scene.

API: apply_material_finish(mats), then finish_scene_geometry(mats, objects=None)
after final scaling. Both functions are safe to call on the existing art scene.
Importing this module executes no Blender operations. Geometry/links/transforms
are preserved; only materials, material-slot overrides and a metric UV layer
are authored. Team emission and fixture materials are not changed.
"""

from pathlib import Path
import hashlib
import re


HERE = Path(__file__).resolve().parent
TEXTURES = HERE / 'textures'
NORMAL_FILE = TEXTURES / 'native-fr-diagonal-rg.png'
MASK_FILE = TEXTURES / 'native-fr-diagonal-orhg.png'
UV_NAME = 'FinishUV'
TILE_METRES = 5.0
VERSION = 1

# Linear colors preserve the established v9 lighting hierarchy. Variation is
# relative to these colors, not a new overall exposure or color grade.
PROFILES = {
    'alloy': dict(color=(.242, .246, .244), metal=.66, rough=(.32, .50), variance=.060, normal=.17, streak=.030, aniso=.06),
    'dark': dict(color=(.033, .047, .064), metal=.48, rough=(.41, .57), variance=.065, normal=.13, streak=.035, aniso=.03),
    'trim': dict(color=(.255, .270, .282), metal=.72, rough=(.28, .44), variance=.045, normal=.18, streak=.020, aniso=.10),
    'floor': dict(color=(.110, .121, .132), metal=.48, rough=(.32, .52), variance=.055, normal=.12, streak=.025, aniso=.10),
    'dark_floor': dict(color=(.033, .044, .058), metal=.42, rough=(.36, .54), variance=.055, normal=.12, streak=.022, aniso=.10),
    'ramp_finish': dict(color=(.120, .131, .142), metal=.44, rough=(.38, .60), variance=.055, normal=.15, streak=.040, aniso=.25),
    'interior_finish': dict(color=(.105, .117, .129), metal=.55, rough=(.31, .48), variance=.055, normal=.10, streak=.020, aniso=.16),
    'apron_finish': dict(color=(.145, .154, .164), metal=.56, rough=(.34, .52), variance=.060, normal=.14, streak=.028, aniso=.08),
}

# Slab-to-slab response is deliberately separate from the accepted armor shader.
# Adjacent serialized slabs alternate through A/B/C/B, giving a .09 roughness
# step rather than jumping directly between the most polished and matte variants.
SLAB_FAMILIES = ('apron_finish', 'interior_finish')
SLAB_STEPS = ((-.09, .97), (0.0, 1.0), (.09, 1.03))
for _family in SLAB_FAMILIES:
    for _index, (_rough_shift, _color_gain) in enumerate(SLAB_STEPS):
        _base = PROFILES[_family]
        PROFILES[_family + '_v' + str(_index)] = {
            **_base,
            'color': tuple(channel * _color_gain for channel in _base['color']),
            'rough': tuple(value + _rough_shift for value in _base['rough']),
        }


def _slab_variant(mesh_name):
    """Stable selection from shared mesh identity, never the team object name."""
    match = re.search(r'((?:\.\d{3,})+)$', mesh_name)
    if match:
        family = mesh_name[:match.start()]
        serial = sum(int(number) for number in re.findall(r'\d+', match.group(1)))
    else:
        family, serial = mesh_name, 0
    seed = int.from_bytes(hashlib.blake2s(family.encode('utf-8'), digest_size=4).digest(), 'little')
    return (0, 1, 2, 1)[(seed + serial) % 4]


def _build_shader(material, profile, normal_image, mask_image):
    nodes, links = material.node_tree.nodes, material.node_tree.links
    nodes.clear()

    def node(kind, label):
        obj = nodes.new(kind); obj.label = label
        return obj

    def math_node(operation, *values):
        obj = node('ShaderNodeMath', operation)
        obj.operation = operation
        for index, value in enumerate(values):
            if isinstance(value, (float, int)):
                obj.inputs[index].default_value = value
            else:
                links.new(value, obj.inputs[index])
        return obj.outputs[0]

    def ramp(source, entries, label):
        obj = node('ShaderNodeValToRGB', label)
        obj.color_ramp.interpolation = 'EASE'
        for index, (position, color) in enumerate(entries):
            element = obj.color_ramp.elements[index] if index < 2 else obj.color_ramp.elements.new(position)
            element.position = position
            element.color = (*color, 1)
        links.new(source, obj.inputs[0])
        return obj.outputs['Color']

    output = node('ShaderNodeOutputMaterial', 'Finished Forerunner alloy')
    bsdf = node('ShaderNodeBsdfPrincipled', 'Broad selective metal sheen')
    links.new(bsdf.outputs['BSDF'], output.inputs['Surface'])
    bsdf.inputs['Metallic'].default_value = profile['metal']
    for socket_name in ('Anisotropic IOR Level', 'Anisotropic'):
        if socket_name in bsdf.inputs:
            bsdf.inputs[socket_name].default_value = profile['aniso']; break
    if 'Anisotropic Rotation' in bsdf.inputs:
        bsdf.inputs['Anisotropic Rotation'].default_value = .25

    uv = node('ShaderNodeUVMap', 'Metric mapping: one native tile per 5 metres')
    uv.uv_map = UV_NAME
    coordinates = uv.outputs['UV']
    if 'Tangent' in bsdf.inputs and profile['aniso'] > .1:
        tangent = node('ShaderNodeTangent', 'Subtle travel-direction scuff response')
        tangent.direction_type = 'UV_MAP'; tangent.uv_map = UV_NAME
        links.new(tangent.outputs['Tangent'], bsdf.inputs['Tangent'])

    # One broad 2D field supplies mineral value regions and broad roughness
    # patches. It follows shared geometry UVs: mirrored team bases match.
    broad = node('ShaderNodeTexNoise', 'Mineral changes across 1.5–4 metre regions')
    broad.noise_dimensions = '3D'
    broad.inputs['Scale'].default_value = 1.40
    broad.inputs['Detail'].default_value = 3.5
    broad.inputs['Roughness'].default_value = .68
    links.new(coordinates, broad.inputs['Vector'])
    base, variation = profile['color'], profile['variance']
    color = ramp(broad.outputs['Fac'], [
        (.25, tuple(c * (1 - variation) for c in base)),
        (.75, tuple(c * (1 + variation) for c in base))], 'Broad ±4–7% mineral value variation')

    # Noise is strongly stretched along the surface's second UV axis, but only
    # its rare upper tail contributes. This cannot form uniform vertical stripes.
    stretch = node('ShaderNodeVectorMath', 'Sparse slab-length directional weathering')
    stretch.operation = 'MULTIPLY'; stretch.inputs[1].default_value = (7.0, .72, 1.0)
    links.new(coordinates, stretch.inputs[0])
    streaks = node('ShaderNodeTexNoise', 'Occasional streaks, mostly quiet surface')
    streaks.inputs['Scale'].default_value = 1
    streaks.inputs['Detail'].default_value = 1.2
    streaks.inputs['Roughness'].default_value = .42
    links.new(stretch.outputs['Vector'], streaks.inputs['Vector'])
    sparse = ramp(streaks.outputs['Fac'], [(.69, (0, 0, 0)), (.82, (1, 1, 1))], 'Only sparse weathered patches')
    weather_factor = math_node('SUBTRACT', 1.0, math_node('MULTIPLY', sparse, profile['streak']))
    tint = node('ShaderNodeMixRGB', 'Very restrained construction-related weathering')
    tint.blend_type = 'MULTIPLY'; tint.inputs[0].default_value = 1
    links.new(color, tint.inputs[1]); links.new(weather_factor, tint.inputs[2])
    grain = node('ShaderNodeTexNoise', 'Fine alloy grain over broad mineral finish')
    grain.inputs['Scale'].default_value = 120
    grain.inputs['Detail'].default_value = 2
    links.new(coordinates, grain.inputs['Vector'])
    grain_tone = ramp(grain.outputs['Fac'], [(.2, (.94, .95, .96)), (.8, (1.04, 1.04, 1.04))], 'Subtle micrograin color variation')
    grain_mix = node('ShaderNodeMixRGB', 'Neutral fine alloy texture')
    grain_mix.blend_type = 'MULTIPLY'; grain_mix.inputs[0].default_value = 1
    links.new(tint.outputs['Color'], grain_mix.inputs[1]); links.new(grain_tone, grain_mix.inputs[2])
    links.new(grain_mix.outputs['Color'], bsdf.inputs['Base Color'])

    rough_min, rough_max = profile['rough']
    rough = ramp(broad.outputs['Fac'], [
        (.25, (rough_min,) * 3), (.75, (rough_max,) * 3),
        (.46, (rough_min + .035,) * 3), (.57, (rough_max - .035,) * 3)],
        'Soft reflection islands across entire slabs')
    packed = node('ShaderNodeTexImage', 'Original T_FR_Diagonal_01_ORHG, linear masks')
    packed.image = mask_image; packed.interpolation = 'Linear'; packed.extension = 'REPEAT'
    links.new(coordinates, packed.inputs['Vector'])
    mask_channels = node('ShaderNodeSeparateXYZ', 'Verified native channel: G is roughness')
    links.new(packed.outputs['Color'], mask_channels.inputs[0])
    micro_rough = math_node('MULTIPLY', math_node('SUBTRACT', mask_channels.outputs['Y'], .5), .045)
    combined_rough = math_node('ADD', rough, micro_rough)
    combined_rough = math_node('MINIMUM', math_node('MAXIMUM', combined_rough, rough_min), rough_max)
    links.new(combined_rough, bsdf.inputs['Roughness'])

    # The shipped PNG is BC5 RG, with B=0. Reconstruct positive Z in linear
    # tangent space; invert DirectX Y for Blender's OpenGL normal convention.
    packed_normal = node('ShaderNodeTexImage', 'Original T_FR_Diagonal_01_N, BC5 RG')
    packed_normal.image = normal_image; packed_normal.interpolation = 'Linear'; packed_normal.extension = 'REPEAT'
    links.new(coordinates, packed_normal.inputs['Vector'])
    rg = node('ShaderNodeSeparateXYZ', 'Unpack native two-channel normal')
    links.new(packed_normal.outputs['Color'], rg.inputs[0])
    nx = math_node('MULTIPLY_ADD', rg.outputs['X'], 2.0, -1.0)
    ny = math_node('MULTIPLY_ADD', rg.outputs['Y'], 2.0, -1.0)
    norm_xy = math_node('ADD', math_node('MULTIPLY', nx, nx), math_node('MULTIPLY', ny, ny))
    nz = math_node('SQRT', math_node('MAXIMUM', math_node('SUBTRACT', 1.0, norm_xy), 0.0))
    rgb_normal = node('ShaderNodeCombineXYZ', 'Reconstructed RGB normal, green flipped')
    links.new(rg.outputs['X'], rgb_normal.inputs['X'])
    links.new(math_node('SUBTRACT', 1.0, rg.outputs['Y']), rgb_normal.inputs['Y'])
    links.new(math_node('MULTIPLY_ADD', nz, .5, .5), rgb_normal.inputs['Z'])
    normal = node('ShaderNodeNormalMap', 'Subtle authentic machined planes')
    normal.space = 'TANGENT'; normal.uv_map = UV_NAME
    normal.inputs['Strength'].default_value = profile['normal'] * 1.65
    links.new(rgb_normal.outputs['Vector'], normal.inputs['Color'])
    bump = node('ShaderNodeBump', 'Microscopic non-polished alloy finish')
    bump.inputs['Strength'].default_value = .12; bump.inputs['Distance'].default_value = .003
    links.new(grain.outputs['Fac'], bump.inputs['Height']); links.new(normal.outputs['Normal'], bump.inputs['Normal'])
    links.new(bump.outputs['Normal'], bsdf.inputs['Normal'])

    material.diffuse_color = (*base, 1)
    material['native_finish_version'] = VERSION
    material['finish_roughness_range'] = list(profile['rough'])
    material['finish_value_variation'] = profile['variance']
    material['finish_native_tile_m'] = TILE_METRES
    material['finish_old_atlas_removed'] = True


def apply_material_finish(mats):
    """Rebuild non-emissive shading; add functional paving variants to mats.

    This function can run immediately after make_mats, or on the already-built
    live art scene. It neither changes lights nor changes geometry.
    """
    import bpy
    for path in (NORMAL_FILE, MASK_FILE):
        if not path.is_file():
            raise FileNotFoundError('Required local native finish map: ' + str(path))
    normal = bpy.data.images.load(str(NORMAL_FILE), check_existing=True)
    masks = bpy.data.images.load(str(MASK_FILE), check_existing=True)
    for image in (normal, masks):
        image.colorspace_settings.name = 'Non-Color'
        image.pack()
    names = {'ramp_finish': 'FR • finish ramp tread',
             'interior_finish': 'FR • finish interior reflective paving',
             'apron_finish': 'FR • finish exterior apron'}
    for family in SLAB_FAMILIES:
        for index in range(3):
            names[family + '_v' + str(index)] = names[family] + ' • slab ' + 'ABC'[index]
    for key, name in names.items():
        if key not in mats:
            mats[key] = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    completed = []
    for key, profile in PROFILES.items():
        if key not in mats:
            continue
        material = mats[key]; material.use_nodes = True
        _build_shader(material, profile, normal, masks)
        material['native_finish_profile'] = key
        if key[-3:-1] == '_v' and key[:-3] in SLAB_FAMILIES:
            index = int(key[-1])
            material['finish_slab_family'] = key[:-3]
            material['finish_slab_variant'] = index
            material['finish_slab_roughness_shift'] = SLAB_STEPS[index][0]
            material['finish_slab_color_gain'] = SLAB_STEPS[index][1]
        completed.append(material.name)
    return {'materials': completed, 'native_maps': [str(NORMAL_FILE), str(MASK_FILE)],
            'tile_metres': TILE_METRES,
            'slab_variants': {family: [family + '_v' + str(index) for index in range(3)]
                              for family in SLAB_FAMILIES},
            'slab_roughness_step': .09,
            'next': 'finish_scene_geometry after final object scale'}


def finish_scene_geometry(mats, objects=None):
    """Assign functional surfaces and continuous metric UVs without un-linking.

    Each shared mesh is processed once. Uniform mirrored/scaled instances use
    the same UVs, preserving red/blue identity. No transform is applied or baked.
    Vectorized UV generation also handles the dense native stock wall meshes.
    """
    import bpy
    import numpy as np
    bpy.context.view_layer.update()
    candidates = list(objects) if objects is not None else list(bpy.context.scene.objects)
    candidates = [obj for obj in candidates if obj.type == 'MESH' and any(
        slot.material and slot.material.get('native_finish_version') == VERSION for slot in obj.material_slots)]
    assignments, variant_assignments = 0, {}
    for obj in candidates:
        name = obj.name.lower()
        target = None
        family = None
        if 'ramp/' in name and 'driveable roof access' in name:
            # Dark structural bed remains visible between the actual raised
            # traction plates. It no longer shares their tread material.
            target = mats.get('dark_floor')
        elif 'ramp/' in name and any(token in name for token in (
                'open upper turning landing', 'integrated wing deck',
                'segmented traction plate')):
            target = mats.get('ramp_finish')
        elif 'floor/' in name and 'seam' not in name and 'strip' not in name:
            if 'covered hall' in name:
                target = mats.get('interior_finish')
            else:
                family = 'interior_finish'
        elif 'apron/' in name and 'inset' not in name:
            family = 'apron_finish'
        if family:
            index = _slab_variant(obj.data.name)
            key = family + '_v' + str(index)
            target = mats.get(key, mats.get(family))
            obj.data['finish_slab_variant'] = index
            obj.data['finish_slab_variant_key'] = key
            obj.data['finish_slab_seed_mesh'] = obj.data.name
            variant_assignments[key] = variant_assignments.get(key, 0) + 1
        if target:
            for slot in obj.material_slots:
                if slot.material and slot.material.get('native_finish_version') == VERSION:
                    slot.link = 'OBJECT'; slot.material = target; assignments += 1

    groups = {}
    for obj in candidates:
        groups.setdefault(obj.data.as_pointer(), []).append(obj)
    total_loops, conflicts, updated = 0, [], []
    for group in groups.values():
        representative = group[0]; data = representative.data
        if not data.vertices or not data.polygons:
            continue
        scale = np.array([representative.matrix_world.to_3x3().col[i].length for i in range(3)], dtype=np.float32)
        for other in group[1:]:
            other_scale = np.array([other.matrix_world.to_3x3().col[i].length for i in range(3)])
            if not np.allclose(scale, other_scale, rtol=1e-5, atol=1e-6):
                conflicts.append(other.name)
        data.update()
        co = np.empty(len(data.vertices) * 3, dtype=np.float32)
        data.vertices.foreach_get('co', co); co = co.reshape((-1, 3)) * scale
        normals = np.empty(len(data.polygons) * 3, dtype=np.float32)
        data.polygons.foreach_get('normal', normals); normals = normals.reshape((-1, 3))
        lengths = np.empty(len(data.polygons), dtype=np.int32)
        data.polygons.foreach_get('loop_total', lengths)
        faces = np.repeat(np.arange(len(data.polygons)), lengths)
        dominant = np.argmax(np.abs(normals), axis=1)[faces]
        indices = np.empty(len(data.loops), dtype=np.int32)
        data.loops.foreach_get('vertex_index', indices)
        points = co[indices]
        uv = np.empty((len(data.loops), 2), dtype=np.float32)
        for axis in range(3):
            mask = dominant == axis
            sign = np.sign(normals[faces[mask], axis]); sign[sign == 0] = 1
            if axis == 0:  # U x V follows the face normal for correct tangent space.
                uv[mask, 0] = points[mask, 1] * sign
                uv[mask, 1] = points[mask, 2]
            elif axis == 1:
                uv[mask, 0] = -points[mask, 0] * sign
                uv[mask, 1] = points[mask, 2]
            else:
                uv[mask, 0] = points[mask, 0] * sign
                uv[mask, 1] = points[mask, 1]
        uv /= TILE_METRES
        layer = data.uv_layers.get(UV_NAME) or data.uv_layers.new(name=UV_NAME)
        layer.data.foreach_set('uv', uv.ravel())
        data['finish_uv_metres_per_tile'] = TILE_METRES
        data['finish_uv_link_preserved'] = True
        data.update()
        total_loops += len(data.loops); updated.append(data.name)
    return {'updated_meshes': len(updated), 'uv_loops': total_loops,
            'functional_material_assignments': assignments,
            'slab_variant_assignments': variant_assignments,
            'shared_geometry_preserved': True, 'transforms_unchanged': True,
            'different_scale_shared_instances': conflicts, 'tile_metres': TILE_METRES}
