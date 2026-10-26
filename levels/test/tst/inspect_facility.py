"""Inspect TST's enclosed facility in the authored Blender source, without a bake.

blender --background --factory-startup --python inspect_facility.py -- \
    --out .dream-loop/blender-preview/facility-check.json

The continuous route is sampled every 20 cm with a 2 m high, 0.4 m radius
cylinder. Boundary probes check roof, rear and side enclosure and the two
arena-facing openings. This is authored-mesh evidence, not game physics.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import sys

import bpy
import bmesh
from mathutils import Vector
from mathutils.bvhtree import BVHTree

ROOT = Path(__file__).resolve().parent
POLICIES = ('AUTO', 'NONE', 'GROUND', 'CLIFF', 'BOTH')
FLOOR = .30
HEIGHT = 2.0
RADIUS = .40
STEP = .20
APPROACH_MAX_SLOPE_DEGREES = 15.0
APPROACH_JOIN_STEP = .02
APPROACH_MAX_STEP = .05
ENTRANCE_WIDTH = 8.8
CENTRAL_PASSAGE_WIDTH = 4.0
CENTRAL_GATE_WIDTH = 3.0
MAIN_CEILING = 4.01
WEST_ROUTE = [(-48,24.9),(-48,35.8),(-36,35.8),(-31,30.5),
              (-18,30.5),(-8,29.9),(-2,29.9),(-2,32.2)]
ROUTE = WEST_ROUTE + [(-x,y) for x,y in reversed(WEST_ROUTE)]


def arguments():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--blend', type=Path, default=ROOT/'tst.blend')
    parser.add_argument('--out', type=Path, default=ROOT.parents[2]/'.dream-loop/blender-preview/facility-check.json')
    return parser.parse_args(sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else [])


def policy(obj, mesh, face):
    attr = mesh.attributes.get('mjolnir_pcg_policy')
    value = attr.data[face.index].value if attr else 0
    name = POLICIES[value] if 0 <= value < len(POLICIES) else 'INVALID'
    if name == 'AUTO':
        name = obj.get('mjolnir_pcg_policy', 'AUTO')
    if name == 'AUTO' and mesh.materials:
        name = mesh.materials[face.material_index].get('mjolnir_pcg_policy', 'AUTO')
    return name


def authored_mesh(obj):
    return (obj.type == 'MESH' and not obj.hide_render and
            not obj.get('mjolnir_preview_only') and not obj.name.startswith('SOURCE_') and
            not any('SOURCE' in c.name.upper() or c.get('mjolnir_preview_only') for c in obj.users_collection))


def tree(objects, unit):
    vertices, faces, sources = [], [], []
    depsgraph = bpy.context.evaluated_depsgraph_get()
    for obj in objects:
        evaluated = obj.evaluated_get(depsgraph)
        mesh = evaluated.to_mesh(preserve_all_data_layers=True, depsgraph=depsgraph)
        try:
            offset = len(vertices)
            vertices.extend((obj.matrix_world @ v.co)*unit for v in mesh.vertices)
            for face in mesh.polygons:
                mat = mesh.materials[face.material_index] if mesh.materials else None
                if mat and any(token in mat.name.lower() for token in ('sky','water','teleporter')):
                    continue
                faces.append(tuple(offset+i for i in face.vertices))
                sources.append({'object':obj.name, 'material':mat.name if mat else None,
                                'pcg_policy':policy(obj,mesh,face)})
        finally:
            evaluated.to_mesh_clear()
    return BVHTree.FromPolygons(vertices, faces), sources


def ray(surface, origin, direction, distance):
    hit, normal, index, length = surface[0].ray_cast(Vector(origin),Vector(direction),distance)
    if hit is None:
        return None
    return {'point_m':[round(v,5) for v in hit], 'normal':[round(v,5) for v in normal],
            'distance_m':round(length,5), **surface[1][index]}


def inside_solid(surface, point):
    # The BSP normals face the playable air. A negative signed distance to
    # the closest boundary places a probe inside a wall/baffle, not the room.
    origin=Vector(point)
    nearest,normal,_,distance=surface[0].find_nearest(origin)
    if nearest is None:
        return False
    signed=(origin-nearest).dot(normal)
    if abs(signed)>1e-5:
        return signed<0
    # At a shared edge BVH may return the face tangent to the probe vector
    # instead of the adjoining ceiling/wall. Resolve that ambiguity using
    # equally-near faces only; mixed or positive signs remain air/unchecked.
    # A point on the boundary itself is not silently classified as solid.
    if distance<=1e-5:
        return False
    signs=[]
    for point,face_normal,_,_ in surface[0].find_nearest_range(origin,distance+1e-5):
        value=(origin-point).dot(face_normal)
        if abs(value)>1e-5:
            signs.append(value)
    return bool(signs) and all(value<0 for value in signs)


def sampled_route():
    points = []
    for a,b in zip(ROUTE,ROUTE[1:]):
        count = max(1, math.ceil(math.dist(a,b)/STEP))
        points.extend((a[0]+(b[0]-a[0])*i/count, a[1]+(b[1]-a[1])*i/count) for i in range(count))
    return points+[ROUTE[-1]]


def main():
    args = arguments()
    source = args.blend.resolve(strict=True)
    before = hashlib.sha256(source.read_bytes()).hexdigest()
    bpy.ops.wm.open_mainfile(filepath=str(source),load_ui=False)
    scene = bpy.context.scene
    if scene.get('mjolnir_preview_only'):
        raise ValueError('Use the authored source .blend, not the isolated design preview')
    unit = scene.unit_settings.scale_length
    objects = [obj for obj in scene.objects if authored_mesh(obj)]
    bsp = bpy.data.objects.get('TST_sealed_terrain_and_sky')
    if bsp is None:
        raise ValueError('Authored BSP boundary is missing')
    structure = tree([bsp],unit)
    visible = tree(objects,unit)
    terrain_source=bpy.data.objects.get('SOURCE_TST_sealed_terrain_and_sky')
    if terrain_source is None:
        raise ValueError('Pre-Boolean terrain source is needed to validate the buried apron toe independently')
    terrain_surface=tree([terrain_source],unit)
    issues = []

    def issue(kind, **detail):
        issues.append({'kind':kind, **detail})

    # Check both the physical BSP and finish meshes that could visibly intrude.
    route_checks = []
    for x,y in sampled_route():
        position = [round(x,4),round(y,4)]
        floor = ray(structure,(x,y,FLOOR+.12),(0,0,-1),.25)
        finish = ray(visible,(x,y,FLOOR+.12),(0,0,-1),.25)
        if floor is None or abs(floor['point_m'][2]-FLOOR) > .015 or floor['normal'][2] < .99:
            issue('route_floor',xy_m=position,hit=floor)
        elif floor['pcg_policy'] != 'NONE':
            issue('route_floor_pcg',xy_m=position,hit=floor)
        if finish is None or abs(finish['point_m'][2]-FLOOR) > .025 or finish['normal'][2] < .99:
            issue('finish_floor',xy_m=position,hit=finish)
        foot = max(FLOOR,finish['point_m'][2]) if finish else FLOOR
        obstruction = None
        for z in (.15,.50,1.0,1.5,HEIGHT-.01):
            for i in range(24):
                angle = math.tau*i/24
                hit = ray(visible,(x,y,foot+z),(math.cos(angle),math.sin(angle),0),RADIUS)
                if hit:
                    obstruction = hit
                    break
            if obstruction:
                break
        if obstruction:
            issue('route_radius',xy_m=position,hit=obstruction)
        for dx,dy in [(0,0)]+[(RADIUS*math.cos(math.tau*i/8),RADIUS*math.sin(math.tau*i/8)) for i in range(8)]:
            hit = ray(visible,(x+dx,y+dy,foot+.08),(0,0,1),HEIGHT-.08)
            if hit:
                issue('route_headroom',xy_m=position,hit=hit)
                break
        roof = ray(structure,(x,y,foot+HEIGHT),(0,0,1),6.5-foot-HEIGHT)
        if roof is None:
            issue('route_roof_open',xy_m=position)
        elif roof['pcg_policy'] != 'NONE':
            issue('roof_pcg',xy_m=position,hit=roof)
        rear = ray(structure,(x,y,foot+1.0),(0,1,0),39.05-y)
        if rear is None:
            issue('route_rear_open',xy_m=position)
        route_checks.append({'xy_m':position,'floor_m':floor['point_m'][2] if floor else None,
                             'finish_floor_m':finish['point_m'][2] if finish else None,
                             'roof_m':roof['point_m'][2] if roof else None})

    # Ramp toes intentionally start under the terrain. The visible approach
    # is max(original triangulated terrain, ramp top), then a flat indoor floor.
    # The saved pre-Boolean terrain is independent of the final union boundary.
    def approach_expected(x,y):
        ramp=-.10+.40*min(1,(y-22.1)/2.5)
        original=ray(terrain_surface,(x,y,3),(0,0,-1),5)
        if original is None:
            issue('approach_original_terrain_missing',xy_m=[x,y])
            return ramp,None
        return max(ramp,original['point_m'][2]) if y<24.6 else FLOOR,original['point_m'][2]

    approach_checks=[]
    approach_steps=math.ceil((25.0-22.1)/STEP)
    for x in (-48,48):
        previous=None
        for i in range(approach_steps+1):
            y=22.1+(25.0-22.1)*i/approach_steps
            position=[x,round(y,4)]
            expected,terrain_height=approach_expected(x,y)
            floor=ray(structure,(x,y,.65),(0,0,-1),1.4)
            finish=ray(visible,(x,y,.65),(0,0,-1),1.4)
            face_slope=None
            sampled_slope=None
            if floor is None or finish is None:
                issue('approach_floor_missing',xy_m=position,structure=floor,finish=finish)
                previous=None
                continue
            if abs(floor['point_m'][2]-expected)>.035:
                issue('approach_floor_profile',xy_m=position,expected_floor_m=round(expected,4),hit=floor)
            foot=finish['point_m'][2]
            face_slope=max(math.degrees(math.acos(max(-1,min(1,h['normal'][2])))) for h in (floor,finish))
            if face_slope>APPROACH_MAX_SLOPE_DEGREES:
                issue('approach_face_slope',xy_m=position,slope_degrees=round(face_slope,3))
            if previous:
                sampled_slope=math.degrees(math.atan2(abs(foot-previous[1]),y-previous[0]))
                if sampled_slope>APPROACH_MAX_SLOPE_DEGREES:
                    issue('approach_step_or_slope',xy_m=position,slope_degrees=round(sampled_slope,3))
            previous=(y,foot)
            obstruction=None
            for height in (.15,.50,1.0,1.5,HEIGHT-.01):
                for j in range(24):
                    angle=math.tau*j/24
                    hit=ray(visible,(x,y,foot+height),(math.cos(angle),math.sin(angle),0),RADIUS)
                    if hit:
                        obstruction=hit
                        break
                if obstruction: break
            if obstruction:
                issue('approach_radius',xy_m=position,hit=obstruction)
            for dx,dy in [(0,0)]+[(RADIUS*math.cos(math.tau*j/8),RADIUS*math.sin(math.tau*j/8)) for j in range(8)]:
                hit=ray(visible,(x+dx,y+dy,foot+.08),(0,0,1),HEIGHT-.08)
                if hit:
                    issue('approach_headroom',xy_m=position,hit=hit)
                    break
            approach_checks.append({'xy_m':position,'floor_m':floor['point_m'][2],
                                    'expected_floor_m':round(expected,5),'original_terrain_m':terrain_height,
                                    'finish_floor_m':foot,'face_slope_degrees':round(face_slope,3),
                                    'sampled_slope_degrees':round(sampled_slope,3) if sampled_slope is not None else None})

    # Dense probes straddle the terrain/metal intersection and the ramp/flat
    # junction. Three lanes span the broad approach; a 5 cm vertical lip must
    # fail even when the coarser walk samples land on either side of it.
    joins=[]
    dense_count=math.ceil((25.0-22.1)/APPROACH_JOIN_STEP)
    for center in (-48,48):
        for offset in (-2,0,2):
            x=center+offset
            previous=None
            transitions=[]
            max_height_change=0.0
            max_profile_error=0.0
            hits=0
            for i in range(dense_count+1):
                y=22.1+(25.0-22.1)*i/dense_count
                expected,_=approach_expected(x,y)
                floor=ray(visible,(x,y,.65),(0,0,-1),1.4)
                if floor is None:
                    issue('approach_join_floor_missing',xy_m=[x,round(y,5)])
                    previous=None
                    continue
                hits+=1
                foot=floor['point_m'][2]
                error=abs(foot-expected)
                max_profile_error=max(max_profile_error,error)
                if error>.035:
                    issue('approach_join_profile',xy_m=[x,round(y,5)],
                          expected_floor_m=round(expected,5),hit=floor)
                finish='terrain' if floor['material'] in ('beach','tst_cliffs') else 'metal'
                if previous:
                    delta=abs(foot-previous['floor_m'])
                    max_height_change=max(max_height_change,delta)
                    if delta>APPROACH_MAX_STEP:
                        issue('approach_visible_step',x_m=x,y_interval_m=[previous['y_m'],round(y,5)],
                              height_change_m=round(delta,5),limit_m=APPROACH_MAX_STEP)
                    if finish!=previous['finish']:
                        transitions.append({'from':previous['finish'],'to':finish,
                                            'y_interval_m':[previous['y_m'],round(y,5)],
                                            'height_change_m':round(delta,5)})
                previous={'y_m':round(y,5),'floor_m':foot,'finish':finish}
            if not any(t['from']=='terrain' and t['to']=='metal' for t in transitions):
                issue('approach_terrain_to_metal_transition_missing',x_m=x,transitions=transitions)
            joins.append({'entrance_center_x_m':center,'lane_x_m':x,'sample_count':hits,
                          'max_adjacent_height_change_m':round(max_height_change,5),
                          'max_expected_profile_error_m':round(max_profile_error,5),
                          'transitions':transitions,'no_sampled_vertical_step':max_height_change<=APPROACH_MAX_STEP})

    # The central partition must leave genuinely broad bypasses. Intersect
    # visible clear intervals at ankle, body and head heights, then require a
    # contiguous 4 m band of level structural floor within that interval.
    # This measures physical passage width, not merely a clear centre line.
    central_passages=[]
    gate_passages=[]
    passage_specs=[(side,y,(-6,-5.1,-4.2,-3.3,3.3,4.2,5.1,6),CENTRAL_PASSAGE_WIDTH)
                   for side,y in (('front',29.1),('rear',35.3))]
    passage_specs.append(('gate',32.2,(-.65,-.48,0,.48,.65),CENTRAL_GATE_WIDTH))
    for side,center_y,x_positions,required_width in passage_specs:
        for x in x_positions:
            sections=[]
            for height in (.15,.40,1.0,HEIGHT):
                origin=(x,center_y,FLOOR+height)
                lo=ray(visible,origin,(0,-1,0),14)
                hi=ray(visible,origin,(0,1,0),14)
                if lo is None or hi is None:
                    issue('central_passage_boundary_missing',side=side,x_m=x,height_m=height,low=lo,high=hi)
                    continue
                sections.append({'height_m':height,'low_y_m':lo['point_m'][1],
                                 'high_y_m':hi['point_m'][1],
                                 'width_m':round(hi['point_m'][1]-lo['point_m'][1],5),
                                 'low_object':lo['object'],'high_object':hi['object']})
            if len(sections)!=4:
                continue
            lower=max(section['low_y_m'] for section in sections)+.002
            upper=min(section['high_y_m'] for section in sections)-.002
            floor_spans=[]
            current=[]
            if upper>lower:
                steps=max(1,math.ceil((upper-lower)/.025))
                for i in range(steps+1):
                    y=lower+(upper-lower)*i/steps
                    floor=ray(structure,(x,y,FLOOR+.12),(0,0,-1),.25)
                    level=bool(floor and abs(floor['point_m'][2]-FLOOR)<.015 and floor['normal'][2]>.99)
                    if level:
                        current.append(y)
                    elif current:
                        floor_spans.append([current[0],current[-1]])
                        current=[]
                if current: floor_spans.append([current[0],current[-1]])
            span=max(floor_spans,key=lambda v:v[1]-v[0]) if floor_spans else None
            width=span[1]-span[0] if span else 0
            if width<required_width:
                issue('central_passage_too_narrow',side=side,x_m=x,
                      required_width_m=required_width,clear_width_m=round(width,5),
                      level_floor_span_y_m=span,sections=sections)
            elif span:
                band_center=sum(span)/2
                for i in range(17):
                    y=band_center-required_width/2+required_width*i/16
                    hit=ray(visible,(x,y,FLOOR+.08),(0,0,1),HEIGHT-.08)
                    if hit:
                        issue('central_full_width_headroom',side=side,xy_m=[x,y],hit=hit)
                        break
            target=gate_passages if side=='gate' else central_passages
            target.append({'side':side,'x_m':x,'body_sections':sections,
                           'level_floor_span_y_m':span,'clear_width_m':round(width,5)})

    # Each change of direction has a full 2 x 2 m turning area, checked on
    # a 10 cm grid, in addition to the route's swept 0.4 m radius envelope.
    # This checks the space after all visible end-cap trim, not BSP alone.
    turning_bays=[]
    for sign in (-1,1):
        samples=0
        for ix in range(21):
            x=sign*(.78+ix*.10)
            for iy in range(21):
                y=30.2+iy*.10
                floor=ray(structure,(x,y,FLOOR+.12),(0,0,-1),.25)
                finish=ray(visible,(x,y,FLOOR+.12),(0,0,-1),.25)
                if not floor or abs(floor['point_m'][2]-FLOOR)>.015 or floor['normal'][2]<.99:
                    issue('turning_bay_floor',xy_m=[x,y],hit=floor)
                # Floor plates have intentional millimetre bevels. Their
                # render-only edge normals need not be horizontal; the BSP
                # above is independently required to be level, and every
                # visible floor sample must remain within the 25 mm skin.
                if not finish or abs(finish['point_m'][2]-FLOOR)>.025:
                    issue('turning_bay_finish_floor',xy_m=[x,y],hit=finish)
                hit=ray(visible,(x,y,FLOOR+.08),(0,0,1),HEIGHT-.08)
                if hit:
                    issue('turning_bay_headroom',xy_m=[x,y],hit=hit)
                if inside_solid(structure,(x,y,FLOOR+1)):
                    issue('turning_bay_inside_solid',xy_m=[x,y])
                samples+=1
        turning_bays.append({'side':'west' if sign<0 else 'east',
                             'x_span_m':sorted([sign*.78,sign*2.78]),'y_span_m':[30.2,32.2],
                             'clear_area_m':[2,2],'height_m':HEIGHT,'grid_step_m':.10,'sample_count':samples})

    # Verify the revised main chamber height independently of the taller
    # entrance vaults. These probes avoid piers and the two exterior portals.
    ceiling_checks=[]
    for x in (-35,-30,-20,-12,-8,8,12,20,30,35):
        for y in (30.0,35.5):
            roof=ray(structure,(x,y,FLOOR+HEIGHT),(0,0,1),4)
            if roof is None or abs(roof['point_m'][2]-MAIN_CEILING)>.015:
                issue('main_chamber_ceiling_height',xy_m=[x,y],expected_m=MAIN_CEILING,hit=roof)
            ceiling_checks.append({'xy_m':[x,y],'ceiling_m':roof['point_m'][2] if roof else None})

    # Direct boundary crossings avoid mistaking an internal pier for an outer
    # wall. Sampling resolution is recorded, so the result is not a claim of
    # mathematically exhaustive aperture/collision testing.
    boundary_count = 0
    solid_probe_count = 0
    for z in (.9,1.8,2.7,3.6,4.4):
        for i in range(409):
            x=-51+i*.25
            if inside_solid(structure,(x,37.7,z)):
                solid_probe_count += 1
                continue
            boundary_count += 1
            if ray(structure,(x,37.7,z),(0,1,0),1.6) is None:
                issue('rear_boundary_open',origin_m=[x,37.7,z])
        for side in (-1,1):
            for i in range(51):
                y=25.0+i*.25
                if inside_solid(structure,(side*51.2,y,z)):
                    solid_probe_count += 1
                    continue
                boundary_count += 1
                if ray(structure,(side*51.2,y,z),(side,0,0),2.0) is None:
                    issue('side_boundary_open',origin_m=[side*51.2,y,z])
    roof_count=0
    for x in range(-50,51,2):
        for y in range(27,38):
            origin=(x,y,2.4)
            if inside_solid(structure,origin):
                solid_probe_count += 1
                continue
            roof_count += 1
            if ray(structure,origin,(0,0,1),4.0) is None:
                issue('roof_boundary_open',origin_m=list(origin))
    opening_rows = []
    for z in (1.3,2.3,3.3):
        samples=[]
        for i in range(530):
            x=-52.9+i*.20
            if ray(structure,(x,25.4,z),(0,-1,0),2.0) is None:
                samples.append(round(x,3))
        spans=[]
        for x in samples:
            if not spans or x-spans[-1][1]>.21:
                spans.append([x,x])
            else:
                spans[-1][1]=x
        opening_rows.append({'height_m':z,'open_spans_x_m':spans,'expected_width_m':ENTRANCE_WIDTH})
        if len(spans)!=2 or any(abs(sum(span)/2-center)>.5 for span,center in zip(spans,(-48,48))):
            issue('exterior_connections',height_m=z,open_spans_x_m=spans)
        elif any(not ENTRANCE_WIDTH-.40<=round(span[1]-span[0],5)<=ENTRANCE_WIDTH+.20 for span in spans):
            issue('entrance_width',height_m=z,expected_width_m=ENTRANCE_WIDTH,
                  sampling_tolerance_m=.40,open_spans_x_m=spans)

    # Check the underlying air boundary, including its deliberately sealed sky.
    bm=bmesh.new(); bm.from_mesh(bsp.data)
    nonmanifold=sum(not edge.is_manifold for edge in bm.edges)
    bm.free()
    if nonmanifold:
        issue('source_nonmanifold',edge_count=nonmanifold)

    facility_objects=[obj for obj in objects if obj.name.startswith('facility_') or obj.get('tst_facility')]
    if not facility_objects:
        issue('facility_missing')
    policy_faces=0
    for obj in facility_objects:
        for face in obj.data.polygons:
            policy_faces += 1
            resolved=policy(obj,obj.data,face)
            if resolved!='NONE':
                issue('facility_finish_pcg',object=obj.name,face=face.index,policy=resolved)
                break
    structural_faces=0
    for face in bsp.data.polygons:
        c=(bsp.matrix_world @ face.center)*unit
        if -52<=c.x<=52 and 24.6<=c.y<=39.05 and -.01<=c.z<=5.9:
            structural_faces += 1
            resolved=policy(bsp,bsp.data,face)
            if resolved!='NONE':
                issue('facility_structure_pcg',face=face.index,center_m=list(c),policy=resolved)
    if not structural_faces:
        issue('facility_structural_faces_missing')

    fixtures=[]
    for obj in facility_objects:
        if not obj.get('tst_facility_fixture'):
            continue
        powered=bool(obj.get('authored_light_lens'))
        failures=[]
        pixels=tuple(obj.get('light_atlas_pixels',()))
        rect_valid=(len(pixels)==4 and all(math.isfinite(v) for v in pixels) and
                    0<=pixels[0]<pixels[2]<=1024 and 0<=pixels[1]<pixels[3]<=256)
        if not rect_valid:
            failures.append('Missing or invalid per-object 1024x256 light-atlas rectangle')
        uv=obj.data.uv_layers.get('UVMap')
        if uv is None:
            failures.append('Missing UVMap for the atlas lens')
        elif rect_valid:
            u0,u1,v0,v1=pixels[0]/1024,pixels[2]/1024,1-pixels[3]/256,1-pixels[1]/256
            if any(not (u0-1e-6<=loop.uv.x<=u1+1e-6 and v0-1e-6<=loop.uv.y<=v1+1e-6) for loop in uv.data):
                failures.append('UVs leave the selected per-object atlas capsule')
            for face in obj.data.polygons:
                coords=[uv.data[index].uv for index in face.loop_indices]
                area=abs(sum(a.x*b.y-b.x*a.y for a,b in zip(coords,coords[1:]+coords[:1])))/2
                if abs(area-(u1-u0)*(v1-v0))>1e-6:
                    failures.append('Lens face does not map one complete atlas capsule')
                    break
        if powered:
            power=obj.get('preview_light_power',0)
            size=obj.get('preview_light_size',())
            direction=obj.get('preview_light_direction',())
            color=obj.get('preview_light_color',())
            if not math.isfinite(power) or power<=0: failures.append('Invalid light power')
            if len(size)!=2 or any(not math.isfinite(v) or v<=0 for v in size): failures.append('Invalid area size')
            if len(direction)!=3 or any(not math.isfinite(v) for v in direction) or sum(v*v for v in direction)<.01: failures.append('Invalid light direction')
            if len(color)!=3 or any(not math.isfinite(v) or not 0<=v<=1 for v in color): failures.append('Invalid light color')
        if failures:
            issue('fixture_metadata',object=obj.name,failures=failures)
        fixtures.append({'object':obj.name,'powered':powered,'watts':obj.get('preview_light_power',0),
                         'atlas_pixels':pixels})
    if not any(f['powered'] for f in fixtures):
        issue('powered_fixtures_missing')

    # Keep the existing native-decor inspector usable on this new route.
    # Its own envelope is 2.4 m high / .4 m radius and tests real imported
    # rock render meshes; this report's structural route remains 2 m high.
    native_checks=[]
    for group,samples in (('route',route_checks),('approach',approach_checks)):
        for index,sample in enumerate(samples):
            foot=sample['floor_m']
            check={'name':f'facility_{group}_{index:04d}',
                   'position_m':[*sample['xy_m'],round((foot if foot is not None else FLOOR)+.05,5)]}
            if foot is not None:
                check['floor_m']=foot
            native_checks.append(check)

    unchanged=before==hashlib.sha256(source.read_bytes()).hexdigest()
    report={'source_blend':str(source),'source_sha256':before,'source_unchanged':unchanged,
            'scope':'Authored BSP and visible finish geometry only; no game physics, native decor or runtime lighting evaluation.',
            'player_envelope':{'height_m':HEIGHT,'radius_m':RADIUS,'route_step_m':STEP},
            'route_waypoints_xy_m':ROUTE,'route_sample_count':len(route_checks),'route':route_checks,
            'checks':native_checks,
            'central_passages':{'required_clear_width_m':CENTRAL_PASSAGE_WIDTH,
                                'height_m':HEIGHT,'floor_sampling_step_m':.025,'cross_sections':central_passages},
            'central_gate':{'required_clear_width_m':CENTRAL_GATE_WIDTH,'height_m':HEIGHT,
                            'floor_sampling_step_m':.025,'cross_sections':gate_passages,'turning_bays':turning_bays},
            'main_chamber':{'ceiling_m':MAIN_CEILING,'clear_height_m':MAIN_CEILING-FLOOR,
                            'ceiling_probes':ceiling_checks},
            'approaches':{'max_allowed_slope_degrees':APPROACH_MAX_SLOPE_DEGREES,
                          'profile':'max(pre-Boolean triangulated terrain, ramp top) before y=24.6; flat .30 m inside',
                          'sample_count':len(approach_checks),'samples':approach_checks,
                          'join_step_m':APPROACH_JOIN_STEP,'max_allowed_vertical_step_m':APPROACH_MAX_STEP,
                          'terrain_to_metal_joins':joins},
            'enclosure':{'route_roof_and_rear_checks':len(route_checks),'boundary_probe_count':boundary_count,
                         'roof_grid_probe_count':roof_count,'probes_inside_solid_structure':solid_probe_count,
                         'boundary_grid_m':.25,'front_grid_m':.20,'front_opening_rows':opening_rows},
            'nonmanifold_edges':nonmanifold,'facility_objects':len(facility_objects),
            'pcg_none_faces_checked':{'finishes':policy_faces,'structure':structural_faces},
            'fixtures':fixtures,'issues':issues,'issue_count':len(issues)}
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(f'TST facility: {len(route_checks)} route samples, {len(fixtures)} fixtures, {len(issues)} issues -> {args.out}')
    if not unchanged or issues:
        for item in issues[:15]: print(json.dumps(item))
        raise SystemExit(1)


if __name__=='__main__':
    main()
