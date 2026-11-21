"""Restore exact map-owned scenery in the offline Blender world assembly.

No import-time Blender effects, game launch, runtime write, or random placement.
``add_world_dressing(scene, sites)`` adds linked mesh instances to two owned
collections and returns a provenance receipt. The caller owns scene saving.
Native rock shaders are approximated in Blender with local source textures;
this is a placement/art review, not evidence of the Unreal material graph.
"""
from pathlib import Path
import hashlib
import json
import math
import re
import struct

ROOT = Path(__file__).resolve().parents[4]
TREES = ROOT / 'out/pwr/visual-v6/scenery/trees/trees.selected.json'
DECOR = ROOT / 'out/pwr/world-v5/visual7/authored-decor.json'
OWNER = 'pwr_base_integration_world_dressing_v1'
SAPLING_ROOT_POLICY = 'native-sapling-min-z-v1'
ASSET_DIRS = [
    ROOT / 'out/pwr/base-integration/assets',
    ROOT / 'out/pwr/visual-v7/apron-cliffs/heroes/assets',
    ROOT / 'out/pwr/visual-v5/outcrops-v3/assets',
    ROOT / 'out/pwr/visual-v5/outcrops-v2/assets',
    ROOT / 'out/pwr/visual-v4/assets',
    ROOT / 'out/pwr-research/nanite',
]
PINE_TEXTURES = ROOT / 'out/pwr/visual-v5/outcrops-v4/trees/assets'


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def source_rows():
    trees = json.loads(TREES.read_text())['instances']
    rows = json.loads(DECOR.read_text())['decor']
    retired = [r for r in rows if r['id'].startswith(('red_home_', 'blue_home_', 'citadel_plateau_'))]
    rocks = [r for r in rows if r not in retired]
    if len(trees) != 4702 or len(retired) != 69 or len(rocks) != 1072:
        raise ValueError('The reviewed V8 map dressing inputs changed')
    for values, key in ((trees, 'id'), (rocks, 'id')):
        if len({r[key] for r in values}) != len(values):
            raise ValueError('Duplicate exact-placement IDs')
    return trees, rocks, retired


def resolve_asset(leaf):
    paths = [p / (leaf + '.glb') for p in ASSET_DIRS]
    return next((p for p in paths if p.is_file()), None)


def _glb_lod0(path):
    """Read only native LOD0; retain points, primitive slots, UVs and normals."""
    import numpy as np
    raw = Path(path).read_bytes()
    if raw[:4] != b'glTF':
        raise ValueError('Expected native GLB: ' + str(path))
    chunks = {}
    offset = 12
    while offset < len(raw):
        size, kind = struct.unpack_from('<II', raw, offset)
        chunks[kind] = raw[offset + 8:offset + 8 + size]
        offset += 8 + size
    doc = json.loads(chunks[0x4E4F534A])
    binary = chunks[0x004E4942]
    # These audited exports use identity LOD nodes. Fail if a later exporter
    # introduces a transform instead of silently discarding it.
    nodes = [n for n in doc.get('nodes', []) if n.get('mesh') == 0]
    if len(nodes) != 1 or any(k in nodes[0] for k in ('matrix', 'translation', 'rotation', 'scale')):
        raise ValueError('Unreviewed LOD0 node transform: ' + str(path))

    def accessor(index):
        a = doc['accessors'][index]
        if 'sparse' in a:
            raise ValueError('Sparse native accessor unsupported')
        view = doc['bufferViews'][a['bufferView']]
        n = {'SCALAR': 1, 'VEC2': 2, 'VEC3': 3, 'VEC4': 4}[a['type']]
        dtype = {5126: '<f4', 5125: '<u4', 5123: '<u2', 5121: 'u1'}[a['componentType']]
        item = np.dtype(dtype).itemsize
        return np.ndarray((a['count'], n), dtype=dtype, buffer=binary,
                          offset=view.get('byteOffset', 0) + a.get('byteOffset', 0),
                          strides=(view.get('byteStride', n * item), item))

    points, faces, normals, uv, slots, repairs = [], [], [], [], [], []
    offset = 0
    for p in doc['meshes'][0]['primitives']:
        if p.get('mode', 4) != 4:
            raise ValueError('Native mesh primitive is not triangles')
        pos = accessor(p['attributes']['POSITION'])[:, [0, 2, 1]] * [1, -1, 1]
        normal = accessor(p['attributes']['NORMAL'])[:, [0, 2, 1]] * [1, -1, 1]
        tri = accessor(p['indices']).reshape(-1, 3).astype('int64')
        cross = np.cross(pos[tri[:, 1]] - pos[tri[:, 0]], pos[tri[:, 2]] - pos[tri[:, 0]])
        dots = np.einsum('ij,ij->i', cross, normal[tri].mean(axis=1))
        nondegenerate = np.linalg.norm(cross, axis=1) > 1e-12
        ratio = float((dots[nondegenerate] < 0).mean()) if nondegenerate.any() else 0
        flipped = ratio > .98
        if flipped:
            tri = tri[:, [0, 2, 1]]
        repairs.append({'primitive': len(repairs), 'inverted_fraction': ratio,
                        'preview_triangle_winding_flipped': flipped})
        tex = accessor(p['attributes']['TEXCOORD_0']).copy() if 'TEXCOORD_0' in p['attributes'] else np.zeros((len(pos), 2))
        tex[:, 1] = 1 - tex[:, 1]
        points.append(pos); normals.append(normal); uv.append(tex)
        faces.append(tri + offset); slots.extend([p.get('material', 0)] * len(tri))
        offset += len(pos)
    return {'vertices': np.concatenate(points), 'faces': np.concatenate(faces),
            'normals': np.concatenate(normals), 'uv': np.concatenate(uv),
            'slots': slots, 'normal_review': repairs,
            'native_material_names': [m.get('name', '') for m in doc.get('materials', [])]}


def _inside(point, polygon):
    """XY point-in-polygon with an explicit boundary inclusion."""
    x, y = point[:2]
    inside = False
    for a, b in zip(polygon, polygon[1:] + polygon[:1]):
        ax, ay = a[:2]; bx, by = b[:2]
        cross = (x - ax) * (by - ay) - (y - ay) * (bx - ax)
        if abs(cross) < 1e-7 and min(ax, bx) - 1e-7 <= x <= max(ax, bx) + 1e-7 and min(ay, by) - 1e-7 <= y <= max(ay, by) + 1e-7:
            return True
        if (ay > y) != (by > y) and x < (bx - ax) * (y - ay) / (by - ay) + ax:
            inside = not inside
    return inside


def _site_exclusions(sites):
    result = []
    for site in sites:
        center = site.get('center_world_m', site.get('terrace_center_m', site.get('position_m')))
        if center is None:
            raise ValueError('Site needs center_world_m, terrace_center_m or position_m')
        explicit = site.get('dressing_exclusion_polygon_world_m', site.get('court_outer_polygon_m'))
        if explicit:
            polygon = explicit
        else:
            # Exactly the new architecture envelope, not the old giant pad.
            cx, cy = center[:2]
            polygon = [[cx - 40, cy - 32], [cx + 40, cy - 32],
                       [cx + 40, cy + 32], [cx - 40, cy + 32]]
        result.append((site.get('team', site.get('id', 'site')), polygon))
    return result


def _texture_material(name, path, *, world_scale=None, foliage=False):
    import bpy
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    bsdf = nodes.get('Principled BSDF')
    bsdf.inputs['Roughness'].default_value = .87
    tex = nodes.new('ShaderNodeTexImage')
    tex.image = bpy.data.images.load(str(path), check_existing=True)
    if world_scale is not None:
        geom = nodes.new('ShaderNodeNewGeometry')
        scale = nodes.new('ShaderNodeVectorMath'); scale.operation = 'SCALE'
        scale.inputs['Scale'].default_value = world_scale
        links.new(geom.outputs['Position'], scale.inputs[0])
        links.new(scale.outputs['Vector'], tex.inputs['Vector'])
        tex.projection = 'BOX'; tex.projection_blend = .3
    links.new(tex.outputs['Color'], bsdf.inputs['Base Color'])
    if foliage:
        links.new(tex.outputs['Alpha'], bsdf.inputs['Alpha'])
        if hasattr(mat, 'surface_render_method'):
            mat.surface_render_method = 'DITHERED'
    mat['native_texture_source'] = str(path)
    mat['unreal_shader_approximation'] = True
    return mat


def _sapling_root_offset_m(row):
    """Match authored_decor.expand_background_trees, in Blender metres."""
    import sys
    sys.path.insert(0, str(ROOT / 'tools/level'))
    from authored_decor import PINE_SAPLING_MIN_Z
    if PINE_SAPLING_MIN_Z != -5.3125:
        raise ValueError('Native sapling root datum changed; review before assembly')
    if row['recipe'] != 'Pine_Sapling_A':
        return 0.0
    if any(abs(v - row['scale']) > 1e-5 for v in row['scale_xyz']):
        raise ValueError('Native tree root policy requires uniform PCG scale')
    return -PINE_SAPLING_MIN_Z * row['scale'] / 100.0


def _root_policy_receipt():
    source = ROOT / 'tools/level/authored_decor.py'
    return {'policy': SAPLING_ROOT_POLICY, 'source': str(source), 'source_sha256': digest(source),
            'function': 'expand_background_trees', 'native_min_z_cm': -5.3125,
            'render_origin_z_m': 'pcg_anchor_z_m + 0.053125 * uniform_scale',
            'pcg_anchor_transforms_preserved': True, 'native_sapling_render_origin_corrected': True,
            'mature_pine': 'retained reviewed assembly datum; no additional correction here'}


def repair_existing_sapling_roots(scene, receipt=None):
    """Correct existing owned saplings once; validate the entire batch first.

    Matching is by this helper's ownership tag, exact selected ID, native
    recipe and exact mesh family. An untagged object at the already-correct
    position is adopted without applying the shift twice. Any unexplained
    translation, orientation or scale change aborts before any mutation.
    Pass the existing dressing receipt dict to refresh its policy fields;
    the caller retains responsibility for saving the receipt and .blend.
    """
    import numpy as np
    from mathutils import Vector
    import sys
    sys.path.insert(0, str(ROOT / 'tools/level'))
    from render_only_hism import matrix as quaternion_matrix
    trees, _, _ = source_rows()
    selected = {str(r['id']): r for r in trees if r['recipe'] == 'Pine_Sapling_A'}
    flip = np.diag([1., -1., 1.])
    planned, seen = [], set()
    tolerance = .0003  # Blender world matrices use float32 at kilometre scale.
    for obj in scene.objects:
        if obj.get('dressing_owner') != OWNER or obj.type != 'MESH':
            continue
        source_id = str(obj.get('source_placement_id', ''))
        row = selected.get(source_id)
        if row is None or not obj.name.startswith('world/trees/'):
            continue
        if source_id in seen:
            raise ValueError('Duplicate owned sapling ID: ' + source_id)
        seen.add(source_id)
        if not obj.data.name.startswith('SM_Tree_Pine_Sapling_A • exact LOD0 integration'):
            raise ValueError('Unreviewed sapling mesh for ' + source_id)
        if obj.get('source_recipe', 'Pine_Sapling_A') != 'Pine_Sapling_A':
            raise ValueError('Sapling recipe metadata disagrees for ' + source_id)
        linear = flip @ np.asarray(quaternion_matrix(row['rotation_xyzw'])) @ flip @ np.diag(row['scale_xyz'])
        if np.max(np.abs(np.asarray(obj.matrix_world.to_3x3()) - linear)) > 5e-5:
            raise ValueError('Owned sapling orientation/scale changed: ' + source_id)
        anchor = np.asarray(row['position_cm']) * [.01, -.01, .01]
        offset = _sapling_root_offset_m(row)
        expected = anchor + [0, 0, offset]
        current = np.asarray(obj.matrix_world.translation)
        at_anchor = bool(np.max(np.abs(current - anchor)) <= tolerance)
        at_corrected = bool(np.max(np.abs(current - expected)) <= tolerance)
        tag = obj.get('native_root_policy')
        if tag not in (None, SAPLING_ROOT_POLICY):
            raise ValueError('Unknown existing root policy: ' + source_id)
        if tag == SAPLING_ROOT_POLICY and not at_corrected:
            raise ValueError('Previously corrected sapling was moved: ' + source_id)
        if not at_anchor and not at_corrected:
            raise ValueError('Owned sapling has unexplained translation: ' + source_id)
        planned.append((obj, source_id, anchor, expected, offset, not at_corrected, tag))
    if not planned:
        raise ValueError('No owned, source-matched saplings found')
    changed, adopted, already = [], [], []
    for obj, source_id, anchor, expected, offset, needs_shift, tag in planned:
        if needs_shift:
            matrix = obj.matrix_world.copy(); matrix.translation = Vector(expected)
            obj.matrix_world = matrix; changed.append(source_id)
        elif tag is None:
            adopted.append(source_id)
        else:
            already.append(source_id)
        obj['source_recipe'] = 'Pine_Sapling_A'
        obj['source_anchor_m'] = anchor.tolist()
        obj['exact_source_anchor_transform'] = True
        obj['exact_source_transform'] = False
        obj['native_root_offset_m'] = float(offset)
        obj['native_root_policy'] = SAPLING_ROOT_POLICY
    result = {'schema': 'pwr-offline-sapling-root-repair-v1', 'policy': _root_policy_receipt(),
              'matched': len(planned), 'corrected_count': len(changed), 'corrected_ids': changed,
              'adopted_corrected_count': len(adopted), 'already_corrected_count': len(already),
              'missing_selected_ids': sorted(set(selected) - seen),
              'offset_range_m': [min(p[4] for p in planned), max(p[4] for p in planned)],
              'idempotent': True, 'runtime_modified': False}
    if receipt is not None:
        receipt['native_render_origin_policy'] = _root_policy_receipt()
        receipt['sapling_root_correction'] = result
        receipt['coordinate_policy'] = ('Authoritative PCG anchors reflected Y into metres; '
            'sapling render origins additionally use the native -min_z * uniform_scale root correction. '
            'No anchor reprojection or rerandomization.')
    return result


def add_world_dressing(scene, sites):
    import bpy
    import numpy as np
    from mathutils import Matrix, Vector
    import sys
    sys.path.insert(0, str(ROOT / 'tools/level'))
    from scenery_swap import rotation_rows
    from render_only_hism import matrix as quaternion_matrix

    trees, rocks, retired = source_rows()
    exclusions = _site_exclusions(sites)
    if any(o.get('dressing_owner') == OWNER for o in scene.objects):
        raise ValueError('Map dressing already exists; rebuild in a fresh assembly scene')
    assets = {r['mesh'].split('.')[-1]: resolve_asset(r['mesh'].split('.')[-1]) for r in rocks}
    missing = [leaf for leaf, path in assets.items() if path is None]
    if missing:
        raise FileNotFoundError('Missing exact native meshes: ' + ', '.join(missing))
    # The native-conifer-review.blend assembly retains its original first-part
    # mesh datablock name after merging; it is not named after the final native
    # exported asset. Root verified this exact V8 scene mesh through MCP:
    # 246,497 vertices and the native bark/branch slots. Match that documented
    # source profile rather than accepting an arbitrary object called "pine".
    mature_candidates = {}
    for obj in scene.objects:
        if obj.type != 'MESH' or not re.fullmatch(r'pwr_exterior_pine_\d+(?:\.\d+)?', obj.name):
            continue
        data = obj.data
        if not re.fullmatch(r'SM_Tree_Pine_A_Big_10_LOD1(?:\.\d+)?', data.name):
            continue
        slots = [re.sub(r'\.\d+$', '', mat.name) if mat else '' for mat in data.materials]
        if len(data.vertices) == 246497 and slots == ['MI_Pine_Tree_Mat', 'MI_Branch_Mat']:
            mature_candidates[data.as_pointer()] = data
    if len(mature_candidates) != 1:
        raise ValueError('Expected exactly one reviewed V8 mature-pine assembly '
                         '(246497 vertices, native bark/branch slots); found '
                         + str(len(mature_candidates)))
    mature = next(iter(mature_candidates.values()))

    collections = {}
    for key, label in [('trees', '30_WORLD • exact selected forest'), ('rocks', '31_WORLD • exact selected rocks')]:
        col = bpy.data.collections.new(label); scene.collection.children.link(col)
        col['dressing_owner'] = OWNER; collections[key] = col
    rockmat = _texture_material('World rock • native albedo / Blender approximation',
                               ROOT / 'out/pwr/visual-v5/surface-v4/textures/rock.png', world_scale=.25)
    pnw = _texture_material('PNW rock • native UV albedo / Blender approximation',
                            ROOT / 'out/pwr/visual-v4/assets/T_PNWGL_Rock_Macro_B_D.png')
    tundra = _texture_material('Tundra rock • native UV albedo / Blender approximation',
                               ROOT / 'out/pwr/visual-v4/assets/T_MassiveTundraRockFormation_01_BC.png')
    bark = _texture_material('Sapling bark • native albedo approximation', PINE_TEXTURES / 'bark-albedo.png')
    needles = _texture_material('Sapling needles • native alpha / Blender approximation', PINE_TEXTURES / 'needle-albedo.png', foliage=True)
    models, model_receipts = {}, []

    def native_mesh(leaf, path, materials):
        if leaf in models:
            return models[leaf]
        arrays = _glb_lod0(path)
        data = bpy.data.meshes.new(leaf + ' • exact LOD0 integration')
        data.from_pydata(arrays['vertices'].tolist(), [], arrays['faces'].tolist()); data.update()
        for p in data.polygons:
            p.use_smooth = True
        data.normals_split_custom_set_from_vertices(arrays['normals'].tolist())
        uv = data.uv_layers.new(name='NativeUV0')
        loops = np.empty(len(data.loops), dtype=np.int32); data.loops.foreach_get('vertex_index', loops)
        uv.data.foreach_set('uv', arrays['uv'][loops].ravel())
        for mat in materials:
            data.materials.append(mat)
        data.polygons.foreach_set('material_index', [min(s, len(materials) - 1) for s in arrays['slots']])
        models[leaf] = data
        model_receipts.append({'leaf': leaf, 'source': str(path), 'sha256': digest(path),
                               'lod': 0, 'vertices': len(data.vertices), 'triangles': len(data.polygons),
                               'normal_review': arrays['normal_review'], 'source_vertices_unchanged': True,
                               'native_material_names': arrays['native_material_names'],
                               'material_policy': 'local native textures; approximate Blender shader'})
        return data

    sapling_path = ROOT / 'out/pwr-research/nanite/SM_Tree_Pine_Sapling_A.glb'
    sapling = native_mesh('SM_Tree_Pine_Sapling_A', sapling_path, [bark, needles])
    flip = np.diag([1., -1., 1.])
    excluded = []
    bounds_audit = []
    counts = {'trees': 0, 'rocks': 0}

    def place(kind, source_id, data, position, rotation, scale, tree_row=None):
        hits = [label for label, poly in exclusions if _inside(position, poly)]
        if hits:
            excluded.append({'kind': kind, 'source_id': source_id, 'position_m': list(position),
                             'sites': hits, 'reason': 'source pivot inside new architecture/court exclusion'})
            return
        obj = bpy.data.objects.new('world/' + kind + '/' + str(source_id), data)
        collections[kind].objects.link(obj)
        obj.matrix_world = Matrix.Translation(Vector(position)) @ Matrix(rotation.tolist()).to_4x4() @ Matrix.Diagonal((*scale, 1))
        obj['dressing_owner'] = OWNER; obj['source_placement_id'] = str(source_id)
        root_offset = _sapling_root_offset_m(tree_row) if tree_row is not None else 0.0
        obj['exact_source_transform'] = not bool(root_offset)
        if tree_row is not None:
            obj['source_recipe'] = tree_row['recipe']
            obj['source_anchor_m'] = (np.asarray(tree_row['position_cm']) * [.01, -.01, .01]).tolist()
            obj['exact_source_anchor_transform'] = True
            obj['native_root_offset_m'] = root_offset
            if tree_row['recipe'] == 'Pine_Sapling_A':
                obj['native_root_policy'] = SAPLING_ROOT_POLICY
        counts[kind] += 1
        # Report possible canopy/rock overlap, never silently delete a nearby
        # instance by an overbroad center distance. Root can inspect the IDs.
        corners = [obj.matrix_world @ Vector(v) for v in obj.bound_box]
        lo = [min(v[k] for v in corners) for k in range(2)]
        hi = [max(v[k] for v in corners) for k in range(2)]
        for label, poly in exclusions:
            pmin = [min(v[k] for v in poly) for k in range(2)]
            pmax = [max(v[k] for v in poly) for k in range(2)]
            if all(lo[k] <= pmax[k] and hi[k] >= pmin[k] for k in range(2)):
                bounds_audit.append({'kind': kind, 'source_id': source_id, 'site': label,
                                     'world_aabb_xy': [lo, hi], 'exact_intersection_test': False})

    for row in trees:
        pos = (np.asarray(row['position_cm']) * [.01, -.01, .01]).tolist()
        pos[2] += _sapling_root_offset_m(row)
        rotation = flip @ np.asarray(quaternion_matrix(row['rotation_xyzw'])) @ flip
        place('trees', row['id'], mature if row['recipe'] == 'PWR_MaturePine_A' else sapling,
              pos, rotation, row['scale_xyz'], tree_row=row)
    for row in rocks:
        leaf = row['mesh'].split('.')[-1]
        material = pnw if 'PNWGL' in leaf else tundra if 'Tundra' in leaf else rockmat
        data = native_mesh(leaf, assets[leaf], [material])
        pos = (np.asarray(row['pos']) * [.01, -.01, .01]).tolist()
        rotation = flip @ np.asarray(rotation_rows(*row['rot'])).T @ flip
        place('rocks', row['id'], data, pos, rotation, row['scale'])
    bpy.context.view_layer.update()
    return {'schema': 'pwr-offline-world-dressing-v1',
            'sources': [{'path': str(p), 'sha256': digest(p)} for p in (TREES, DECOR)],
            'source_counts': {'trees': len(trees), 'rocks': len(rocks)}, 'added_counts': counts,
            'excluded': excluded, 'possible_bounds_overlaps': bounds_audit,
            'retired_base_visual_ids': [r['id'] for r in retired],
            'native_models': model_receipts, 'mature_pine_shared_mesh': mature.name,
            'collection_names': [c.name for c in collections.values()],
            'coordinate_policy': 'Authoritative PCG anchors reflected Y into metres; sapling render origins additionally use the native -min_z * uniform_scale root correction. No anchor reprojection or rerandomization.',
            'native_render_origin_policy': _root_policy_receipt(),
            'materials': 'Mature pine retains reviewed native UV/albedo. Sapling native UV and pine texture approximation. Rocks use local native albedos with approximate Blender surface shader.',
            'runtime_modified': False, 'actual_game_proof': False}
