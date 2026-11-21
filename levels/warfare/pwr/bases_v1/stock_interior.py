"""Authentic local Halo wall modules for the Blender-only base art study.

Import has no Blender side effects. Call ``add_stock_panels(api)`` while the
master is at the origin and before the build's vertical elevation transform.
``api`` supplies collection and mats; include_front=True enables two removable
facade inserts. No game files are altered and no assets are exported.
"""

from pathlib import Path
import hashlib
import itertools
import json
import math
import statistics
import struct


ROOT = Path(__file__).resolve().parents[4]
ASSET_DIR = ROOT / 'out/pwr/visual-v4/base-details'
ASSET_FILES = {
    'wall': 'SM_FR_ACR_Int_Canyon_A_SmallRoom_Wall_w9_d1_h5_A.glb',
    'pillar': 'SM_FR_ACR_Int_Canyon_A_SmallRoom_Pillar_w2_d0i5_h5i5_A.glb',
}
NATIVE_DIMENSIONS = {
    'wall': (8.005625, 1.274375, 5.2025),
    'pillar': (2.00625, .54875, 5.501875),
}
PROVENANCE = 'user-installed Halo game asset; local authoring reference'


def _glb_manifest(path):
    raw = path.read_bytes()
    if raw[:4] != b'glTF':
        raise ValueError('Expected GLB: ' + str(path))
    size, chunk_type = struct.unpack_from('<II', raw, 12)
    if chunk_type != 0x4E4F534A:
        raise ValueError('GLB first chunk is not JSON: ' + str(path))
    document = json.loads(raw[20:20 + size])
    return {
        'file': str(path), 'sha256': hashlib.sha256(raw).hexdigest(),
        'generator': document.get('asset', {}).get('generator'),
        'nodes': [{key: node[key] for key in ('name', 'matrix', 'rotation', 'translation', 'scale')
                   if key in node} for node in document.get('nodes', [])],
        'original_materials': [mat.get('name', '') for mat in document.get('materials', [])],
        'embedded_images': len(document.get('images', [])),
    }


def _bounds(meshes):
    points = [vertex.co for data in meshes for vertex in data.vertices]
    return ([min(v[k] for v in points) for k in range(3)],
            [max(v[k] for v in points) for k in range(3)])


def _orientation_and_scale(dimensions, expected):
    """Find uniform units/orientation correction without distorting the asset.

    Blender normally converts GLTF +Y up to +Z up on import. Current files have
    identity node transforms and already use metres, so the result is identity.
    This check also catches an imported global unit scale or an axis swap.
    """
    from mathutils import Matrix
    choices = []
    for perm in itertools.permutations(range(3)):
        ratios = [expected[i] / max(dimensions[perm[i]], 1e-9) for i in range(3)]
        uniform_scale = statistics.median(ratios)
        error = max(abs(math.log(r / uniform_scale)) for r in ratios)
        choices.append((error, perm, uniform_scale))
    error, perm, scale = min(choices)
    if error > .025:
        raise ValueError('Stock asset dimensions differ from verified geometry: '
                         + repr((dimensions, expected)))
    orientation = Matrix.Identity(4)
    for row in range(3):
        for col in range(3):
            orientation[row][col] = 1.0 if col == perm[row] else 0.0
    # Keep positive handedness. The usual Y/Z conversion becomes (X,-Z,Y).
    if orientation.determinant() < 0:
        for col in range(3):
            orientation[1][col] *= -1
    return orientation, scale


def _map_materials_and_uv(data, mats):
    """Retain stock slots and legacy atlas UVs; final finish adds metric UVs."""
    original_names = [material.name if material else '' for material in data.materials]
    light_slots = []
    for index, name in enumerate(original_names):
        is_light = 'light' in name.lower()
        light_slots.append(is_light)
        data.materials[index] = mats['alloy'] if is_light else mats['dark']
    if not data.materials:
        data.materials.append(mats['alloy'])
        light_slots.append(True)
    lo, hi = _bounds([data])
    uv = data.uv_layers.get('StockAtlasUV') or data.uv_layers.new(name='StockAtlasUV')
    data.uv_layers.active = uv
    uv.active_render = True
    data.update()
    for polygon in data.polygons:
        normal_axis = max(range(3), key=lambda k: abs(polygon.normal[k]))
        axes = [k for k in range(3) if k != normal_axis]
        is_light = light_slots[min(polygon.material_index, len(light_slots) - 1)]
        v0, v1 = (.52, .98) if is_light else (.265, .485)
        for loop_index in polygon.loop_indices:
            coordinate = data.vertices[data.loops[loop_index].vertex_index].co
            u = (coordinate[axes[0]] - lo[axes[0]]) / max(hi[axes[0]] - lo[axes[0]], 1e-6)
            v = (coordinate[axes[1]] - lo[axes[1]]) / max(hi[axes[1]] - lo[axes[1]], 1e-6)
            # Global face-plane projection stays continuous across the many
            # original triangles instead of stretching one full atlas per face.
            uv.data[loop_index].uv = (.01 + .98 * u, v0 + (v1 - v0) * v)
    return original_names


def _repair_custom_normals(data):
    """Correct a globally inverted imported corner-normal field, once per mesh.

    Compare authored split normals with the face normals after all importer,
    unit and orientation transforms have been baked. A majority facing inward
    with a clearly negative median identifies the global sign error observed
    in the cached wall GLB. Negating the entire corner field preserves its
    authored smooth/hard-edge relationships; vertex order and face winding are
    never changed. Mixed or weak evidence is recorded without a blind flip.
    """
    data.update()
    has_custom=bool(data.has_custom_normals)
    original=[tuple(value.vector) for value in data.corner_normals]
    if len(original)!=len(data.loops):
        if has_custom:
            raise ValueError('Incomplete custom corner normals for '+data.name)
        return {'mesh':data.name,'has_custom_normals':False,
                'correction':'none: no complete custom normal field',
                'before':None,'after':None,'face_winding_changed':False}

    def summarize(normals):
        dots=[]
        skipped=0
        for polygon in data.polygons:
            face=tuple(polygon.normal)
            face_length=math.sqrt(math.fsum(component*component for component in face))
            for corner in polygon.loop_indices:
                normal=normals[corner]
                normal_length=math.sqrt(math.fsum(component*component for component in normal))
                if face_length<1e-12 or normal_length<1e-12:
                    skipped+=1
                    continue
                dot=math.fsum(a*b for a,b in zip(face,normal))/(face_length*normal_length)
                if not math.isfinite(dot):
                    skipped+=1
                    continue
                dots.append(max(-1.,min(1.,dot)))
        return {'compared_corners':len(dots),'skipped_degenerate_corners':skipped,
                'dot_mean':math.fsum(dots)/len(dots) if dots else None,
                'dot_median':statistics.median(dots) if dots else None,
                'dot_min':min(dots) if dots else None,'dot_max':max(dots) if dots else None,
                'inverted_corners':sum(dot < -1e-5 for dot in dots),
                'inverted_fraction':sum(dot < -1e-5 for dot in dots)/len(dots) if dots else None,
                'strongly_inverted_fraction':sum(dot < -.5 for dot in dots)/len(dots) if dots else None}

    before=summarize(original)
    should_flip=(has_custom and before['compared_corners']>0
                 and before['strongly_inverted_fraction']>.5)
    correction='none: existing corner orientation retained'
    if should_flip:
        data.normals_split_custom_set([tuple(-component for component in normal) for normal in original])
        data.update()
        correction='negated all custom split corner normals; authored smoothing retained'
    current=[tuple(value.vector) for value in data.corner_normals]
    # A minority of exporter corners already had the opposite sign. Align
    # those remaining outliers to their own face after the global correction.
    hemisphere_repairs=0
    if should_flip:
        for polygon in data.polygons:
            face=tuple(polygon.normal)
            for corner in polygon.loop_indices:
                if sum(a*b for a,b in zip(face,current[corner])) < -1e-4:
                    current[corner]=tuple(-component for component in current[corner]);hemisphere_repairs+=1
        if hemisphere_repairs:
            data.normals_split_custom_set(current);data.update()
            current=[tuple(value.vector) for value in data.corner_normals]
    after=summarize(current)
    report={'mesh':data.name,'has_custom_normals':has_custom,'corner_count':len(original),
            'criterion':'custom normals; more than50% of valid corner-vs-face dot products below-.5',
            'before':before,'correction':correction,'hemisphere_outliers_repaired':hemisphere_repairs,'after':after,
            'face_winding_changed':False,'vertex_geometry_changed':False,
            'shared_data_policy':'Repair once before placement; all linked instances reuse this mesh'}
    data['stock_custom_normal_diagnostics']=json.dumps(report)
    if should_flip and (after['dot_mean'] is None or after['dot_mean']<=0
                        or after['inverted_fraction']>=before['inverted_fraction']):
        raise ValueError('Custom normal sign correction failed verification for '+data.name+': '+json.dumps(report))
    return report


def _load_asset(key, api):
    import bpy
    from mathutils import Matrix, Vector
    path = Path(api.get('asset_dir', ASSET_DIR)) / ASSET_FILES[key]
    manifest = _glb_manifest(path)
    before = set(bpy.data.objects)
    imported, data_blocks = [], []
    try:
        bpy.ops.import_scene.gltf(filepath=str(path))
        imported = list(set(bpy.data.objects) - before)
        # All temporary helpers are isolated to the requested master collection.
        for obj in imported:
            for collection in list(obj.users_collection):
                collection.objects.unlink(obj)
            api['collection'].objects.link(obj)
        bpy.context.view_layer.update()
        depsgraph = bpy.context.evaluated_depsgraph_get()
        mesh_objects = [obj for obj in imported if obj.type == 'MESH']
        chosen = [obj for obj in mesh_objects if '_LOD0' in obj.name]
        if not chosen:
            chosen = [obj for obj in mesh_objects
                      if not any('_LOD' + str(n) in obj.name for n in range(1, 10))]
        if not chosen:
            raise ValueError('No LOD0 mesh imported from ' + str(path))
        for index, obj in enumerate(chosen):
            evaluated = obj.evaluated_get(depsgraph)
            data = bpy.data.meshes.new_from_object(evaluated, preserve_all_data_layers=True,
                                                  depsgraph=depsgraph)
            data.name = 'Stock_' + key + '_shared_LOD0_' + str(index)
            # Bake every importer/root/node transform before anchoring by bounds.
            data.transform(evaluated.matrix_world)
            data.update()
            data_blocks.append(data)
    finally:
        # Only this import's objects are removed, including empties/armatures,
        # cameras or unused LODs. Existing scene objects are never selected/deleted.
        for obj in imported or list(set(bpy.data.objects) - before):
            bpy.data.objects.remove(obj, do_unlink=True)

    raw_lo, raw_hi = _bounds(data_blocks)
    dimensions = [raw_hi[i] - raw_lo[i] for i in range(3)]
    orientation, scale = _orientation_and_scale(dimensions, NATIVE_DIMENSIONS[key])
    transform = Matrix.Scale(scale, 4) @ orientation
    for data in data_blocks:
        data.transform(transform)
    lo, hi = _bounds(data_blocks)
    # Canonical origin: horizontal centre, frontmost face, lowest point.
    anchor = Vector(((lo[0] + hi[0]) * .5, lo[1], lo[2]))
    normal_diagnostics=[]
    for data in data_blocks:
        data.transform(Matrix.Translation(-anchor))
        normal_diagnostics.append(_repair_custom_normals(data))
        names = _map_materials_and_uv(data, api['mats'])
        data['stock_original_materials'] = json.dumps(names)
        data['stock_source_file'] = str(path)
        data['stock_source_sha256'] = manifest['sha256']
        data['stock_provenance'] = PROVENANCE
        data['stock_lod'] = 0
        data['stock_shared_geometry'] = True
    lo, hi = _bounds(data_blocks)
    manifest.update(imported_dimensions_m=dimensions, normalization_uniform_scale=scale,
                    orientation_matrix=[list(row) for row in orientation],
                    canonical_min_m=lo, canonical_max_m=hi,
                    vertices=sum(len(data.vertices) for data in data_blocks),
                    triangles=sum(sum(len(poly.vertices) - 2 for poly in data.polygons) for data in data_blocks),
                    mesh_parts=len(data_blocks), lod=0,
                    custom_normal_diagnostics=normal_diagnostics,
                    material_policy='Light -> alloy; Mid/Dark -> dark; atlas UV projection')
    return data_blocks, manifest


def add_stock_panels(api):
    """Install 12 linked stock pieces, or 14 with include_front=True.

    The JSON-serializable report includes file provenance, vertex counts,
    instance bounds and placements. Required API entries: collection and mats.
    It adds no bevel/subdivision modifiers to the original detailed geometry.
    """
    import bpy
    from mathutils import Matrix, Vector
    wall, wall_info = _load_asset('wall', api)
    pillar, pillar_info = _load_asset('pillar', api)
    report = {'schema_version': 1, 'authoring_only': True,
              'pre_elevation_coordinates_m': True,
              'assets': [wall_info, pillar_info], 'instances': []}

    def place(name, data_blocks, info, matrix):
        lo, hi = info['canonical_min_m'], info['canonical_max_m']
        corners = [matrix @ Vector((x, y, z)) for x in (lo[0], hi[0])
                   for y in (lo[1], hi[1]) for z in (lo[2], hi[2])]
        lower = [min(p[i] for p in corners) for i in range(3)]
        upper = [max(p[i] for p in corners) for i in range(3)]
        names = []
        for index, data in enumerate(data_blocks):
            obj = bpy.data.objects.new(name + ('/part' + str(index) if len(data_blocks) > 1 else ''), data)
            api['collection'].objects.link(obj)
            obj.matrix_world = matrix
            obj['module_role'] = 'stock'
            obj['stock_provenance'] = PROVENANCE
            obj['stock_source_file'] = info['file']
            obj['stock_source_sha256'] = info['sha256']
            obj['stock_lod'] = 0
            obj['stock_removable_module'] = True
            obj['stock_pre_elevation_bounds_m'] = json.dumps([lower, upper])
            names.append(obj.name)
        report['instances'].append({'name': name, 'objects': names, 'source': info['file'],
                                    'matrix': [list(row) for row in matrix],
                                    'min_m': lower, 'max_m': upper})

    for sign, side in ((-1, 'L'), (1, 'R')):
        # The rear bulkhead is authored in the shared kit. This export's large
        # wall sheet still showed view-dependent artifacts after normal repair.
        for x in (23, 33):
            place('stock/rear-gallery-trim-' + side + '-' + str(x), pillar, pillar_info,
                  Matrix.Translation((sign * x, 22.20, .2)) @ Matrix.Rotation(math.pi, 4, 'Z'))
        for bay in (-21, -11, -1, 19):
            # Detailed native face is +Y. Face it into the hall, preserving
            # exactly the former occupied envelope outside the vehicle route.
            transform = (Matrix.Translation((sign * (api.get('tunnel_inner_x',10.55)+NATIVE_DIMENSIONS['wall'][1]*.45), bay, .30))
                         @ Matrix.Rotation(sign * math.pi / 2, 4, 'Z')
                         @ Matrix.Scale(.45, 4))
            place('stock/tunnel-panel-' + side + '-' + str(bay), wall, wall_info, transform)
        if api.get('include_front', False):
            # Original thickness tucks behind the inclined facade. For the
            # whole insert z<11.2, so the requested facade equation is affine.
            # The same native wall pattern is retained on both sides.
            transform = Matrix(((1, 0, 0, sign * 18),
                                (0, 1, .35, -25.5 - (11.2 - 4.0) * .35),
                                (0, 0, 1, 4.0),
                                (0, 0, 0, 1)))
            place('stock/front-hero-' + side, wall, wall_info, transform)

    report['logical_instances'] = len(report['instances'])
    report['objects'] = sum(len(item['objects']) for item in report['instances'])
    report['unique_mesh_vertices'] = wall_info['vertices'] + pillar_info['vertices']
    report['linked_instances_before_elevation'] = True
    api['collection']['stock_interior_manifest'] = json.dumps(report)
    return report
