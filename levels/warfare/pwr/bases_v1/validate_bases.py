"""Offline evaluated-mesh checks for the Blender base art scene.

Run in the existing Blender session after build_bases.py. This reads evaluated
bevelled geometry, never starts the game, and never changes scene objects.
It writes out/pwr/base-art/geometry-validation.json. This is an architectural
clearance audit, not a gameplay, vehicle dynamics, collision-cook or physics test.
"""
from pathlib import Path
from collections import Counter, defaultdict
import json
import math
import time

import bpy
from mathutils import Vector, Matrix
from mathutils.bvhtree import BVHTree

ROOT = Path(__file__).resolve().parents[4]
OUT = ROOT / 'out/pwr/base-art/geometry-validation.json'
CONTACT_ALLOWANCE = .08
EPS = 1e-5


def samples(lo, hi, step=1.):
    n = max(1, math.ceil((hi-lo)/step))
    return [lo+(hi-lo)*i/n for i in range(n+1)]


def bbox(points):
    return {'min': [min(p[k] for p in points) for k in range(3)],
            'max': [max(p[k] for p in points) for k in range(3)]}


def inside(point, bounds, margin=0.):
    return all(bounds['min'][k]+margin < point[k] < bounds['max'][k]-margin for k in range(3))


def overlap_bounds(a, b):
    return all(a['max'][k] >= b['min'][k] and b['max'][k] >= a['min'][k] for k in range(3))


def box_tree(bounds):
    lo, hi = bounds['min'], bounds['max']
    verts = [(x,y,z) for z in (lo[2],hi[2]) for y in (lo[1],hi[1]) for x in (lo[0],hi[0])]
    faces = [(0,1,3,2),(4,6,7,5),(0,4,5,1),(2,3,7,6),(0,2,6,4),(1,5,7,3)]
    return BVHTree.FromPolygons(verts,faces,all_triangles=False)


class EvaluatedScene:
    def __init__(self, objects, normalizer=None):
        self.records = []
        self.vertices = []
        self.triangles = []
        self.owners = []
        dg = bpy.context.evaluated_depsgraph_get()
        normalizer = normalizer or Matrix.Identity(4)
        for ob in objects:
            if ob.type != 'MESH':
                continue
            evaluated = ob.evaluated_get(dg)
            me = evaluated.to_mesh()
            try:
                me.calc_loop_triangles()
                matrix = normalizer @ evaluated.matrix_world
                verts = [matrix @ v.co for v in me.vertices]
                tris = [tuple(p.vertices) for p in me.loop_triangles]
                if not verts or not tris:
                    continue
                record = {'object': ob, 'name': ob.name, 'vertices': verts, 'triangles': tris,
                          'bounds': bbox(verts), 'bvh': BVHTree.FromPolygons(verts,tris,all_triangles=True),
                          'source_mesh': ob.data.name, 'materials': [s.material.name if s.material else None for s in ob.material_slots]}
                self.records.append(record)
                start = len(self.vertices)
                self.vertices.extend(verts)
                self.triangles.extend(tuple(start+i for i in tri) for tri in tris)
                self.owners.extend([ob.name]*len(tris))
            finally:
                evaluated.to_mesh_clear()
        self.bvh = BVHTree.FromPolygons(self.vertices,self.triangles,all_triangles=True)
        self.bounds = bbox(self.vertices)

    def ray(self, origin, direction, distance):
        p, normal, index, dist = self.bvh.ray_cast(Vector(origin),Vector(direction),distance)
        if p is None:
            return None
        return {'point_m': list(p), 'distance_m': dist, 'object': self.owners[index]}

    def stats(self):
        return {'mesh_objects': len(self.records), 'evaluated_vertices': len(self.vertices),
                'evaluated_triangles': len(self.triangles), 'bounds_m': self.bounds,
                'module_roles': dict(Counter(r['object'].get('module_role','unknown') for r in self.records))}


def volume_audit(scene, bounds, ray_grid=True):
    """Continuous boundary intersections + contained vertices + <=1m ray grids.

    Volume boundary BVH catches crossing triangles between sample lines; vertex
    containment catches isolated small pieces wholly inside the protected box.
    A parity probe additionally detects a solid which encloses the whole box.
    """
    shell = box_tree(bounds)
    violations = {}
    center = Vector([(a+b)*.5 for a,b in zip(bounds['min'],bounds['max'])])
    for r in scene.records:
        if not overlap_bounds(r['bounds'],bounds):
            continue
        count = sum(1 for v in r['vertices'] if inside(v,bounds,EPS))
        cross = r['bvh'].overlap(shell)
        if count or cross:
            violations[r['name']] = {'contained_vertices':count,'boundary_triangle_intersections':len(cross)}
        elif inside(center,r['bounds']):
            direction=Vector((.371,.529,.763)).normalized()
            p=center.copy();distance=1000.;hits=0
            for _ in range(256):
                hit,_,_,dist=r['bvh'].ray_cast(p,direction,distance)
                if hit is None:break
                hits+=1;p=hit+direction*.0001;distance-=dist+.0001
            if hits%2:
                violations[r['name']]={'encloses_center_by_parity':True}
    rays=0; ray_hits=Counter();examples=[]
    if ray_grid:
        # Each axis samples the full span of the other axes, including edges.
        for axis in range(3):
            others=[k for k in range(3) if k!=axis]
            for a in samples(bounds['min'][others[0]],bounds['max'][others[0]]):
                for b in samples(bounds['min'][others[1]],bounds['max'][others[1]]):
                    start=list(bounds['min']);start[others[0]]=a;start[others[1]]=b
                    direction=[0,0,0];direction[axis]=1
                    hit=scene.ray(start,direction,bounds['max'][axis]-bounds['min'][axis])
                    rays+=1
                    if hit:
                        ray_hits[hit['object']]+=1
                        if len(examples)<12:examples.append(hit)
    return {'passed':not violations and not ray_hits,'protected_bounds_m':bounds,
            'continuous_volume_intersections':violations,'grid_spacing_max_m':1.,
            'ray_count':rays,'ray_hit_objects':dict(ray_hits),'hit_examples':examples}


def floor_and_cover(scene, authoring_scale):
    missing=[];heights=[];cover=[];bad_floor=[]
    for y in samples(-35*authoring_scale,35*authoring_scale):
        for x in samples(-1.75,1.75):
            hit=scene.ray((x,y,.8),(0,0,-1),2)
            if hit is None:missing.append([x,y])
            else:
                z=hit['point_m'][2];heights.append(z)
                if abs(z-.2)>CONTACT_ALLOWANCE:bad_floor.append({'xy':[x,y],**hit})
            sky=scene.ray((x,y,4.8),(0,0,1),max(40.,scene.bounds['max'][2]-4.8+2))
            if sky and -23*authoring_scale<=y<=23*authoring_scale:cover.append({'xy':[x,y],**sky})
    return {'floor_passed':not missing and not bad_floor,'floor_expected_z_m':.2,
            'floor_contact_tolerance_m':CONTACT_ALLOWANCE,'floor_sample_count':len(heights)+len(missing),
            'center_path_y_range_m':[-35*authoring_scale,35*authoring_scale],
            'floor_height_range_m':[min(heights),max(heights)] if heights else None,
            'unsupported_floor_xy_m':missing,'floor_deviations':bad_floor[:30],
            'measured_covered_soffit_z_range_m':[min(h['point_m'][2] for h in cover),max(h['point_m'][2] for h in cover)] if cover else None,
            'covered_height_above_floor_min_m':min(h['point_m'][2] for h in cover)-.2 if cover else None,
            'note':'Support sampled at vehicle center stations. Full body air envelope extends3.5m beyond endpoint centers. Terrain approaches are excluded.'}


def mirror_audit(red,blue):
    by_name=defaultdict(list)
    by_source_name=defaultdict(list)
    for r in blue.records:
        by_name[r['name']].append(r)
        # Explicit provenance is a strict fallback for Blender's name-length
        # limit. Never choose an arbitrary instance by shared mesh data.
        source_names={r['object'].get(key) for key in ('mirror_source_object','source_object_name')}
        for source_name in source_names:
            if isinstance(source_name,str):by_source_name[source_name].append(r)
    mismatches=[];max_error=0.;pairs=0;team_slots=0
    matched_blue=set()
    for r in red.records:
        expected_name='02_BLUE/'+r['name']
        candidates=by_name.get(expected_name,[])
        match_method='exact clone name'
        if not candidates:
            candidates=by_source_name.get(r['name'],[])
            match_method='explicit source object metadata'
        if len(candidates)!=1:
            mismatches.append({'red':r['name'],'reason':'unambiguous named clone not found',
                               'expected_blue':expected_name,'candidate_count':len(candidates),
                               'match_method':match_method});continue
        b=candidates[0]
        if b['name'] in matched_blue:
            mismatches.append({'red':r['name'],'blue':b['name'],'reason':'blue instance already paired'});continue
        matched_blue.add(b['name']);pairs+=1
        if r['source_mesh']!=b['source_mesh']:
            mismatches.append({'red':r['name'],'blue':b['name'],'reason':'source mesh data differs',
                               'source_meshes':[r['source_mesh'],b['source_mesh']]})
        if len(r['vertices'])!=len(b['vertices']) or r['triangles']!=b['triangles']:
            mismatches.append({'red':r['name'],'blue':b['name'],'reason':'evaluated topology mismatch'});continue
        error=max((a-c).length for a,c in zip(r['vertices'],b['vertices']))
        max_error=max(max_error,error)
        if error>1e-4:mismatches.append({'red':r['name'],'reason':'reflected geometry differs','max_error_m':error})
        if len(r['materials'])!=len(b['materials']):
            mismatches.append({'red':r['name'],'reason':'material slot count differs'});continue
        for rm,bm in zip(r['materials'],b['materials']):
            if rm and bm and rm.startswith('TEAM') and bm.startswith('TEAM'):
                team_slots+=1
                if 'red' not in rm.lower() or 'blue' not in bm.lower():
                    mismatches.append({'red':r['name'],'reason':'incorrect team material pair','materials':[rm,bm]})
            elif rm!=bm:mismatches.append({'red':r['name'],'reason':'non-team material differs','materials':[rm,bm]})
    if len(red.records)!=len(blue.records):mismatches.append({'reason':'object counts differ'})
    unpaired=[r['name'] for r in blue.records if r['name'] not in matched_blue]
    if unpaired:mismatches.append({'reason':'unpaired blue instances','objects':unpaired})
    return {'passed':not mismatches,'paired_objects':pairs,'team_material_slots':team_slots,
            'pairing':'exact 02_BLUE/<red object name>, or explicit mirror_source_object/source_object_name metadata; shared mesh identity also required',
            'canonical_transform':'blue local = reflectX * translate(-135,0,0) * world',
            'maximum_coordinate_error_m':max_error,'mismatches':mismatches,
            'note':'Negative-scale presentation reflection verified geometrically. Export must apply transforms and repair winding/tangents as required.'}


def ramps_audit(scene, roof_datum, authoring_scale):
    output=[]
    for r in scene.records:
        if 'ramp/driveable roof access' not in r['name']:continue
        b=r['bounds'];x=(b['min'][0]+b['max'][0])*.5
        yf,yt=b['min'][1],b['max'][1]
        points=[];blocked=[]
        for y in samples(yf+.15,yt-.15):
            cast_top=max(roof_datum+5,b['max'][2]+5)
            hit,_,_,_=r['bvh'].ray_cast(Vector((x,y,cast_top)),Vector((0,0,-1)),cast_top-b['min'][2]+5)
            if hit is None:continue
            points.append(list(hit))
            # Measured surface profile and vertical clearance on all width lanes.
            for xx in samples(x-1.75,x+1.75):
                obstruction=scene.ray((xx,y,hit.z+CONTACT_ALLOWANCE),(0,0,1),4.5-CONTACT_ALLOWANCE)
                if obstruction and len(blocked)<50:blocked.append({'station_xy':[xx,y],**obstruction})
        low=points[0][2] if points else None;high=points[-1][2] if points else None
        # At y just before endpoint we measure the bevelled ramp; immediately
        # after endpoint test the real landing with a downward ray.
        landing=scene.ray((x,yt+.25,roof_datum+.8),(0,0,-1),3)
        bottom=scene.ray((x,yf+.02,2),(0,0,-1),4)
        top_gap=abs(landing['point_m'][2]-roof_datum) if landing else None
        bottom_gap=abs(bottom['point_m'][2]-.2) if bottom else None
        # Test traversable level connection from outboard landing to roof.
        landing_y=yt+4*authoring_scale
        inward=1 if x<0 else -1
        roof_connection_x=inward*-34*authoring_scale
        bridge=[];uncovered=[]
        for xx in samples(min(x,roof_connection_x),max(x,roof_connection_x)):
            hit=scene.ray((xx,landing_y,roof_datum+.5),(0,0,-1),2)
            if hit is None or abs(hit['point_m'][2]-roof_datum)>.12:uncovered.append({'xy':[xx,landing_y],'hit':hit})
            else:bridge.append(hit)
        output.append({'object':r['name'],'bounds_m':b,'measured_center_surface_profile_m':points,
                       'measured_approx_grade':(high-low)/(points[-1][1]-points[0][1]) if len(points)>1 else None,
                       'bottom_surface':bottom,'bottom_gap_to_floor_datum_m':bottom_gap,
                       'top_landing_surface':landing,'roof_datum_z_m':roof_datum,'top_gap_to_roof_datum_m':top_gap,
                       'landing_to_roof_center_path_m':[[x,landing_y,roof_datum],[roof_connection_x,landing_y,roof_datum]],
                       'landing_to_roof_unsupported_samples':uncovered,'vertical_proxy_clearance_obstructions':blocked,
                       'endpoint_datum_passed':bottom_gap is not None and bottom_gap<=.12 and top_gap is not None and top_gap<=.12,
                       'landing_to_roof_passed':not uncovered,
                       'note':f'Endpoint heights checked against floor.2 and scene roof datum{roof_datum:g}. Outboard bottom requires future terrain approach; excluded terrain support not asserted. Vertical proxy sampling is not an articulated uphill vehicle sweep.'})
    return output


def floating_details(scene):
    structural=[r for r in scene.records if not r['object'].get('module_role','').startswith('detail')]
    v=[];t=[]
    for r in structural:
        start=len(v);v.extend(r['vertices']);t.extend(tuple(start+i for i in p) for p in r['triangles'])
    tree=BVHTree.FromPolygons(v,t,all_triangles=True)
    output=[]
    for r in scene.records:
        if not r['object'].get('module_role','').startswith('detail'):continue
        # Vertex sample avoids treating a batch's empty-center AABB as geometry.
        stride=max(1,len(r['vertices'])//200);distances=[]
        for point in r['vertices'][::stride]:
            hit=tree.find_nearest(point)
            if hit[0] is not None:distances.append(hit[3])
        if distances and max(distances)>1.:
            output.append({'object':r['name'],'sample_count':len(distances),
                           'nearest_structural_distance_max_m':max(distances),
                           'sample_fraction_over1m':sum(x>1 for x in distances)/len(distances)})
    return {'warning_objects':output,'note':'Heuristic flags detail farther than1m from structure; not an automatic failure. Intentional suspended lights may be valid.'}


def main():
    start=time.time()
    authoring_scale=float(bpy.context.scene.get('base_authoring_scale',1.))
    if not math.isfinite(authoring_scale) or authoring_scale<=0:
        raise ValueError('base_authoring_scale must be a positive finite scale')
    roof_datum=float(bpy.context.scene.get('roof_deck_z_m',11.2))
    roof_reserve_half_width=15*authoring_scale
    roof_reserve_bottom=roof_datum+.8*authoring_scale
    collections={prefix:next((c for c in bpy.data.collections if c.name.startswith(prefix)),None) for prefix in ('01_RED','02_BLUE','03_GREEN')}
    missing=[k for k,v in collections.items() if v is None]
    if missing:raise RuntimeError('Missing base collections: '+', '.join(missing))
    red=EvaluatedScene(collections['01_RED'].all_objects)
    inverse_blue=Matrix.Diagonal((-1,1,1,1)) @ Matrix.Translation(Vector((-135,0,0)))
    blue=EvaluatedScene(collections['02_BLUE'].all_objects,inverse_blue)
    green=EvaluatedScene(collections['03_GREEN'].all_objects,Matrix.Translation(Vector((0,-150,0))))
    # Scale architectural route positions, never the real vehicle envelope.
    main_path_half_length=35*authoring_scale
    vehicle={'min':[-1.75,-main_path_half_length-3.5,.2+CONTACT_ALLOWANCE],
             'max':[1.75,main_path_half_length+3.5,.2+4.5]}
    # Same complete vehicle proxy travelling sideways through the intentional
    # y4..14 crosscut. Length runs along X and width along Y for this route.
    cross_path_half_length=28*authoring_scale
    cross_y=9*authoring_scale
    cross_vehicle={'min':[-cross_path_half_length-3.5,cross_y-1.75,.2+CONTACT_ALLOWANCE],
                   'max':[cross_path_half_length+3.5,cross_y+1.75,.2+4.5]}
    route=volume_audit(red,vehicle)
    cross_route=volume_audit(red,cross_vehicle)
    cross_route['center_path']=f'x[{-cross_path_half_length:g},{cross_path_half_length:g}], y{cross_y:g}, floor.2; vehicle length alongX'
    side_front_routes={}
    for side,sign in (('left',-1),('right',1)):
        center_x=sign*33*authoring_scale
        center_y_min,center_y_max=-36*authoring_scale,-10*authoring_scale
        # Door and route positions follow art scale; the entire actual vehicle
        # remains7m long,3.5m wide,4.5m high on both sides of the entrance.
        protected={'min':[center_x-1.75,center_y_min-3.5,.2+CONTACT_ALLOWANCE],
                   'max':[center_x+1.75,center_y_max+3.5,.2+4.5]}
        result=volume_audit(red,protected)
        result['center_path']=f'x{center_x:g}, y[{center_y_min:g},{center_y_max:g}], floor.2; vehicle length alongY'
        result['scope']='Side-front gallery air clearance only. Geometry intersections fail this check; side-route floor support and vehicle dynamics are not asserted.'
        side_front_routes[side]=result
    floor=floor_and_cover(red,authoring_scale)
    roof=volume_audit(red,{'min':[-roof_reserve_half_width,-roof_reserve_half_width,roof_reserve_bottom],
                          'max':[roof_reserve_half_width,roof_reserve_half_width,max(roof_reserve_bottom+10.,red.bounds['max'][2]+2)]})
    green_route=volume_audit(green,vehicle)
    green_cross_route=volume_audit(green,cross_vehicle)
    green_cross_route['center_path']=cross_route['center_path']
    green_floor=floor_and_cover(green,authoring_scale)
    green_roof=volume_audit(green,{'min':[-roof_reserve_half_width,-roof_reserve_half_width,roof_reserve_bottom],
                                 'max':[roof_reserve_half_width,roof_reserve_half_width,max(roof_reserve_bottom+10.,green.bounds['max'][2]+2)]})
    mirror=mirror_audit(red,blue)
    ramps=ramps_audit(red,roof_datum,authoring_scale)
    detail=floating_details(red)
    checks={'main_through_tunnel_air':route,'main_route_floor_and_cover':floor,
            'cross_gallery_vehicle_air':cross_route,
            'side_front_gallery_vehicle_air':side_front_routes,
            'red_blue_mirror':mirror,'rooftop_reserved_sky':roof,'roof_ramps':ramps,
            'green_main_through_tunnel_air':green_route,'green_main_route_floor_and_cover':green_floor,
            'green_cross_gallery_vehicle_air':green_cross_route,
            'green_rooftop_reserved_sky':green_roof,
            'floating_detail_heuristic':detail}
    failures=[]
    for name,passed in [('main tunnel',route['passed']),('main floor',floor['floor_passed']),('red/blue mirror',mirror['passed']),('roof reservation',roof['passed'])]:
        if not passed:failures.append(name)
    for name,passed in [('green main tunnel',green_route['passed']),('green main floor',green_floor['floor_passed']),('green roof reservation',green_roof['passed'])]:
        if not passed:failures.append(name)
    for name,passed in [('cross gallery',cross_route['passed']),('green cross gallery',green_cross_route['passed'])]:
        if not passed:failures.append(name)
    for side,result in side_front_routes.items():
        if not result['passed']:failures.append(side+' side-front gallery vehicle air')
    for ramp in ramps:
        if not ramp['endpoint_datum_passed']:failures.append(ramp['object']+' endpoint')
        if not ramp['landing_to_roof_passed']:failures.append(ramp['object']+' landing')
        if ramp['vertical_proxy_clearance_obstructions']:failures.append(ramp['object']+' overhead clearance')
    document={'schema':'pwr-blender-evaluated-geometry-validation-v1','blend':bpy.data.filepath,
              'passed':not failures,'failed_checks':failures,'duration_seconds':time.time()-start,
              'units':'metres; presentation copies normalized to local base coordinates',
              'base_authoring_scale':authoring_scale,
              'datums_m':{'floor_z':.2,'roof_deck_z':roof_datum,'roof_reserved_sky_bottom_z':roof_reserve_bottom},
              'roof_reservation_width_depth_m':[30*authoring_scale,30*authoring_scale],
              'scene_geometry':{'red':red.stats(),'blue':blue.stats(),'green':green.stats()},
              'scope':'Base collection evaluated meshes only. Presentation terrain, rocks, vegetation, vehicles and lighting excluded.',
              'vehicle_proxy_m':{'length':7,'width':3.5,'height':4.5,
                                 'center_path':f'x0, y[{-main_path_half_length:g},{main_path_half_length:g}], floor.2',
                                 'scale_policy':'Real vehicle envelope remains unscaled; only architectural route positions scale.'},
              'limitations':['This is not a physics or gameplay test. No game or Unreal was used.',
                             'Static conservative box clearance does not model suspension, turret rotation, riders, braking, network motion or handling.',
                             'One-metre ray grids supplement BVH boundary and containment checks; they do not replace future collision cooking and gameplay validation.',
                             'Main scene art includes isolated trim and floor seams. Floor contact up to.08m above the nominal floor is allowed.',
                             f'Roof reservation checks{30*authoring_scale:g}x{30*authoring_scale:g}m sky volume abovez{roof_reserve_bottom:g} (scene roof datum +{.8*authoring_scale:g}m). The low mount curb below this volume is deliberately allowed. Exact emitter remains unconfirmed; reservation is adjustable.'],
              'checks':checks}
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(document,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'validation':str(OUT),'passed':document['passed'],'failed_checks':failures,
                      'counts':document['scene_geometry'],'seconds':document['duration_seconds']}))
    return document


if __name__=='__main__':main()
