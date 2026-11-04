"""Verify entrance fixtures and indoor balcony lifts from evaluated Blender meshes.

blender --background --factory-startup --python inspect_entry_fixtures.py -- \
    --blend tst.blend --placements placements.json --out entry-fixtures.json

This reads the generated geometry and placement file, without importing their
construction constants. It does not modify the blend or claim game physics QA.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import sys

import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree

ROOT = Path(__file__).resolve().parent
# Retail Spartan radius: .175 Halo world units * 3.048 metres per unit.
PLAYER_RADIUS = .5334
PLAYER_HEIGHT = 2.40
EPSILON = .0002


def arguments():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--blend', type=Path, default=ROOT/'tst.blend')
    parser.add_argument('--placements', type=Path, default=ROOT/'placements.json')
    parser.add_argument('--out', type=Path, required=True)
    return parser.parse_args(sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else [])


def snapshot(obj, unit, depsgraph):
    evaluated = obj.evaluated_get(depsgraph)
    mesh = evaluated.to_mesh(preserve_all_data_layers=True, depsgraph=depsgraph)
    try:
        vertices = [(evaluated.matrix_world@vertex.co)*unit for vertex in mesh.vertices]
        uv = mesh.uv_layers.get('UVMap')
        faces = []
        for face in mesh.polygons:
            indices = tuple(face.vertices)
            points = [vertices[index] for index in indices]
            normal = (points[1]-points[0]).cross(points[2]-points[0]).normalized()
            material = mesh.materials[face.material_index] if mesh.materials else None
            faces.append({'indices':indices, 'points':points, 'normal':normal,
                          'uv':[tuple(uv.data[index].uv) for index in face.loop_indices] if uv else [],
                          'material':material.name if material else ''})
        return {'name':obj.name, 'vertices':vertices, 'faces':faces}
    finally:
        evaluated.to_mesh_clear()


def tree(meshes, solid_only=False):
    vertices, polygons, owners = [], [], []
    for mesh in meshes:
        offset = len(vertices)
        vertices.extend(mesh['vertices'])
        for face in mesh['faces']:
            if solid_only and any(term in face['material'].lower() for term in ('water', 'teleporter', 'sky')):
                continue
            polygons.append(tuple(offset+index for index in face['indices']))
            owners.append(mesh['name'])
    return BVHTree.FromPolygons(vertices, polygons), owners


def ray(surface, origin, direction, distance):
    position, normal, index, length = surface[0].ray_cast(Vector(origin), Vector(direction), distance)
    if position is None:
        return None
    return {'point':position, 'normal':normal, 'distance':length, 'object':surface[1][index]}


def serialize(value):
    if isinstance(value, Vector):
        return [round(component, 6) for component in value]
    if isinstance(value, dict):
        return {key:serialize(item) for key,item in value.items()}
    if isinstance(value, (tuple, list)):
        return [serialize(item) for item in value]
    if isinstance(value, float):
        return round(value, 7)
    return value


def center(points):
    return sum(points, Vector())/len(points)


def face_samples(face):
    middle = center(face['points'])
    return [middle]+[point.lerp(middle, .12) for point in face['points']]


def main():
    args = arguments()
    source, placement_path = args.blend.resolve(strict=True), args.placements.resolve(strict=True)
    initial_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    placements = json.loads(placement_path.read_text(encoding='utf-8'))
    bpy.ops.wm.open_mainfile(filepath=str(source), load_ui=False)
    scene = bpy.context.scene
    if scene.get('mjolnir_preview_only'):
        raise ValueError('Inspect the authored source, not a preview-only blend')
    depsgraph = bpy.context.evaluated_depsgraph_get()
    authored = [obj for obj in scene.objects if obj.type == 'MESH' and not obj.hide_render
                and not obj.get('mjolnir_preview_only') and not obj.name.startswith('SOURCE_')
                and not any('SOURCE' in collection.name.upper() or collection.get('mjolnir_preview_only')
                            for collection in obj.users_collection)]
    meshes = {obj.name:snapshot(obj, scene.unit_settings.scale_length, depsgraph) for obj in authored}
    bsp = meshes.get('TST_sealed_terrain_and_sky')
    if bsp is None:
        raise ValueError('Missing authored BSP collision boundary')
    structure = tree([bsp], solid_only=True)
    visible = tree(list(meshes.values()), solid_only=True)
    issues = []

    def issue(kind, **values):
        issues.append({'kind':kind, **values})

    frame_meshes = [mesh for name,mesh in meshes.items() if name.startswith(
        ('facility_portal_outer_frame_', 'facility_portal_silver_reveal_', 'facility_portal_inner_frame_'))]
    frames = tree(frame_meshes)
    fixtures = [obj for obj in authored if obj.get('fixture_backing_object')]
    if len(fixtures) != 10:
        issue('fixture_count', expected=10, actual=len(fixtures))
    fixture_results = []
    for obj in fixtures:
        mesh = meshes[obj.name]
        backing = meshes.get(obj['fixture_backing_object'])
        if backing is None:
            issue('fixture_missing_backing', object=obj.name, backing=obj['fixture_backing_object'])
            continue
        backing_tree = tree([backing])
        distances = []
        for face in mesh['faces']:
            if face['normal'].dot(Vector((0,-1,0))) < .999:
                issue('fixture_faces_away_from_arena', object=obj.name, normal=face['normal'])
            for point in face_samples(face):
                hit = ray(backing_tree, point, (0,1,0), .002+EPSILON)
                if hit is None or abs(hit['distance']-.002) > EPSILON:
                    issue('fixture_unbacked_or_floating', object=obj.name, point=point, hit=hit)
                else:
                    distances.append(hit['distance'])
        # Inspect real housing/frame intersections. A housing's front can
        # stand proud, but its rear must penetrate the actual frame surface.
        low_y = min(point.y for point in backing['vertices'])
        high_y = max(point.y for point in backing['vertices'])
        embedded = []
        front_faces = [face for face in backing['faces']
                       if all(abs(point.y-low_y)<EPSILON for point in face['points'])]
        if not front_faces:
            issue('backing_front_face_missing', object=backing['name'])
        for face in front_faces:
            for point in face_samples(face):
                hit = ray(frames, point, (0,1,0), high_y-low_y+EPSILON)
                depth = high_y-hit['point'].y if hit else None
                if depth is None or depth < .010-EPSILON:
                    issue('housing_not_seated_in_frame', object=backing['name'], point=point, hit=hit)
                else:
                    embedded.append(depth)
        uv_result = None
        if obj.get('team_marker_uv_mode'):
            xs = [point.x for point in mesh['vertices']]
            zs = [point.z for point in mesh['vertices']]
            width, height = max(xs)-min(xs), max(zs)-min(zs)
            if abs(width/height-.5) > 1e-4:
                issue('team_emblem_stretched', object=obj.name, width_m=width, height_m=height)
            uv_errors = []
            for face in mesh['faces']:
                if len(face['uv']) != len(face['points']):
                    issue('team_emblem_uv_missing', object=obj.name)
                    continue
                for point,uv in zip(face['points'],face['uv']):
                    expected = ((point.x-min(xs))/width, (point.z-min(zs))/height)
                    uv_errors.append(max(abs(a-b) for a,b in zip(uv,expected)))
            if not uv_errors or max(uv_errors) > 1e-5:
                issue('team_emblem_uv_orientation_or_extent', object=obj.name, max_error=max(uv_errors,default=None))
            uv_result = {'width_m':width,'height_m':height,'image_aspect':.5,
                         'max_mapping_error':max(uv_errors, default=None)}
        fixture_results.append({'object':obj.name,'backing':backing['name'],
            'sample_count':len(distances),'max_face_gap_m':max(distances,default=None),
            'minimum_frame_embedding_m':min(embedded,default=None),'emblem_uv':uv_result})

    portals = [obj for obj in authored if obj.name.startswith('facility_lift_')
               and obj.get('noncolliding_portal')]
    if len(portals) != 2:
        issue('indoor_lift_portal_count', expected=2, actual=len(portals))
    portal_results = []
    portal_by_channel = {}
    for obj in portals:
        mesh = meshes[obj.name]
        middle = center(mesh['vertices'])
        side = 1 if middle.x>0 else -1
        outward = Vector((side,0,0))
        ys, zs = [point.y for point in mesh['vertices']], [point.z for point in mesh['vertices']]
        width, height = max(ys)-min(ys), max(zs)-min(zs)
        errors = []
        for face in mesh['faces']:
            if face['normal'].dot(outward) < .999:
                issue('lift_portal_faces_wall', object=obj.name, normal=face['normal'])
            if len(face['uv']) != len(face['points']):
                issue('lift_portal_uv_missing', object=obj.name)
                continue
            for point,uv in zip(face['points'],face['uv']):
                expected = ((point.y-min(ys))/width, (point.z-min(zs))/height)
                errors.append(max(abs(a-b) for a,b in zip(uv,expected)))
        if not errors or max(errors) > 1e-5:
            issue('lift_portal_yz_uv_extent_or_orientation', object=obj.name, max_error=max(errors,default=None))
        seals = []
        for horizontal in (-.30,0,.30):
            for vertical in (.12,.48,.82):
                origin = Vector((middle.x, (min(ys)+max(ys))/2+horizontal*width, min(zs)+vertical*height))
                near = ray(structure, origin, -outward, .5)
                far = ray(structure, near['point']-outward*EPSILON, -outward, 2) if near else None
                thickness = far['distance']+EPSILON if far else None
                if near is None or near['normal'].dot(outward)<.99:
                    issue('lift_pocket_open_back', object=obj.name, point=origin, hit=near)
                elif thickness is None or thickness < .18-EPSILON:
                    issue('lift_backwall_too_thin_or_missing', object=obj.name, point=origin, thickness_m=thickness)
                seals.append({'origin_m':origin,'near':near,'far':far,'thickness_m':thickness})
        channel = int(obj.get('balcony_lift_channel', -1))
        if channel in portal_by_channel:
            issue('duplicate_lift_channel',channel=channel)
        portal_by_channel[channel] = {'object':obj.name,'center':middle,'side':side,
                                      'y_center':(min(ys)+max(ys))/2,'floor':min(zs)}
        portal_results.append({'object':obj.name,'channel':channel,'center_m':middle,
                               'max_uv_error':max(errors,default=None),'backwall_probes':seals})

    def player_sample(label, xy, expected_floor=None):
        # Floor, headroom, and radial sweeps include decorative finishes so
        # a visually blocked route cannot pass merely because BSP is clear.
        x,y = xy
        cast_z = (expected_floor if expected_floor is not None else .3)+.25
        floor = ray(visible, (x,y,cast_z), (0,0,-1), .5)
        if floor is None or floor['normal'].z < .99:
            issue('player_floor_missing_or_sloped', sample=label, xy_m=xy, hit=floor)
            return None
        foot = floor['point'].z
        if expected_floor is not None and abs(foot-expected_floor)>.025:
            issue('player_floor_step', sample=label, expected_floor_m=expected_floor, hit=floor)
        blockage = None
        for height in (.08,.50,1,1.5,PLAYER_HEIGHT-.01):
            for angle_index in range(24):
                angle = math.tau*angle_index/24
                blockage = ray(visible, (x,y,foot+height), (math.cos(angle),math.sin(angle),0), PLAYER_RADIUS)
                if blockage: break
            if blockage: break
        if blockage:
            issue('player_body_obstruction', sample=label, xy_m=xy, hit=blockage)
        for angle_index in range(9):
            dx,dy = (0,0) if angle_index==8 else (PLAYER_RADIUS*math.cos(math.tau*angle_index/8),
                                                PLAYER_RADIUS*math.sin(math.tau*angle_index/8))
            head = ray(visible, (x+dx,y+dy,foot+.05), (0,0,1), PLAYER_HEIGHT-.05)
            if head:
                issue('player_headroom_obstruction', sample=label, xy_m=xy, hit=head)
                break
            edge_floor = ray(visible, (x+dx,y+dy,foot+.15), (0,0,-1), .3)
            if edge_floor is None or abs(edge_floor['point'].z-foot)>.025:
                issue('player_footprint_threshold_or_gap', sample=label, xy_m=xy, hit=edge_floor)
                break
        return {'sample':label,'xy_m':xy,'floor_m':foot}

    links = placements.get('teleporters', [])
    by_channel = {item['channel']:item for item in links}
    if len(by_channel)!=len(links):
        issue('duplicate_placement_channels')
    link_results, route_samples = [], []
    for channel,portal in portal_by_channel.items():
        forward, returning = by_channel.get(channel), by_channel.get(channel+2)
        if not forward or not returning:
            issue('lift_link_pair_missing', channel=channel)
            continue
        if forward.get('scenery') is not False or returning.get('scenery') is not False:
            issue('lift_still_spawns_ground_pad', channel=channel)
        start, end = Vector(forward['from_m']), Vector(forward['to_m'])
        return_start, landing = Vector(returning['from_m']), Vector(returning['to_m'])
        side = portal['side']
        if not (start.x*side>abs(portal['center'].x) and abs(start.y-portal['y_center'])<.05):
            issue('lift_trigger_not_at_side_door', channel=channel, from_m=start)
        if abs(start.x-portal['center'].x)>forward.get('radius_m',1.15):
            issue('lift_shield_outside_trigger',channel=channel)
        for name,point in (('forward',start),('return_landing',landing)):
            roof = ray(structure, point+Vector((0,0,PLAYER_HEIGHT)), (0,0,1), 5)
            if roof is None:
                issue('lift_ground_endpoint_outdoors',channel=channel,endpoint=name,point=point)
        if end.z < 6 or return_start.z < 6 or abs(end.x-return_start.x)>.1:
            issue('lift_no_longer_connects_upper_walkway',channel=channel)
        spacing = Vector((start.x-landing.x,start.y-landing.y,0)).length
        required = forward.get('radius_m',1.15)+PLAYER_RADIUS+.15
        if spacing < required:
            issue('return_landing_bounce_back',channel=channel,spacing_m=spacing,required_m=required)
        yaw = math.radians(returning.get('to_yaw_degrees',0))
        away = Vector((landing.x-start.x,landing.y-start.y,0)).normalized()
        if Vector((math.cos(yaw),math.sin(yaw),0)).dot(away)<.9:
            issue('return_landing_faces_into_lift',channel=channel)
        # Walk from the entrance centre to the return point, then to the
        # trigger. This tests the authored route independently of its cutter.
        route = [Vector((side*48,25.5)),Vector((landing.x,landing.y)),Vector((start.x,start.y))]
        for segment,(a,b) in enumerate(zip(route,route[1:])):
            count = max(1,math.ceil((b-a).length/.15))
            for index in range(count+1):
                point = a.lerp(b,index/count)
                result = player_sample(f'channel_{channel}_approach_{segment}_{index}',tuple(point),.30)
                if result: route_samples.append(result)
        for label,point in (('upper_arrival',end),('upper_return_trigger',return_start),('indoor_return',landing)):
            result=player_sample(f'channel_{channel}_{label}',(point.x,point.y),point.z-.05)
            if result: route_samples.append(result)
        link_results.append({'channel':channel,'from_m':start,'to_m':end,'return_from_m':return_start,
                             'return_to_m':landing,'return_trigger_separation_m':spacing})
    if set(portal_by_channel)!={2,3}:
        issue('expected_red_blue_lift_channels_missing',actual=sorted(portal_by_channel))
    for scenery in placements.get('scenery',[]):
        point=scenery.get('position_m',[])
        if ('teleport' in scenery.get('tag','').lower() and len(point)==3
                and abs(point[0])>40 and 18<point[1]<35 and point[2]<2):
            issue('exterior_entry_teleporter_scenery_remaining',scenery=scenery)
    source_unchanged = initial_hash == hashlib.sha256(source.read_bytes()).hexdigest()
    if not source_unchanged:
        issue('source_was_modified')
    report={'source_blend':str(source),'source_sha256':initial_hash,
            'placements':str(placement_path),'placements_sha256':hashlib.sha256(placement_path.read_bytes()).hexdigest(),
            'source_unchanged':source_unchanged,
            'scope':'Evaluated authored render/BSP meshes and generated placements; excludes native decor and runtime physics.',
            'player_envelope':{'radius_m':PLAYER_RADIUS,'height_m':PLAYER_HEIGHT},
            'fixtures':fixture_results,'lift_portals':portal_results,'links':link_results,
            'player_samples':route_samples,'issues':issues,'issue_count':len(issues)}
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(serialize(report),indent=2)+'\n',encoding='utf-8')
    print(f'TST entry fixtures: {len(fixtures)} fixtures, {len(portals)} lifts, {len(route_samples)} player samples, {len(issues)} issues -> {args.out}')
    for value in issues[:15]: print(json.dumps(serialize(value)))
    if issues: raise SystemExit(1)


if __name__=='__main__':
    main()
