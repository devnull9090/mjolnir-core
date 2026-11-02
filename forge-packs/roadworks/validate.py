"""Portable geometry, driving-surface and connector regression checks."""

from __future__ import annotations

from collections import Counter
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def sub(a, b):
    return [x-y for x,y in zip(a,b)]


def dot(a, b):
    return sum(x*y for x,y in zip(a,b))


def cross(a, b):
    return [a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0]]


def close(a, b, tolerance=2e-7):
    assert max(abs(x-y) for x,y in zip(a,b)) <= tolerance, (a,b)


def inside(point, hull, tolerance=1e-7):
    return all(dot(cross(sub(hull['vertices'][b],hull['vertices'][a]),
                         sub(hull['vertices'][c],hull['vertices'][a])),
                   sub(point,hull['vertices'][a])) <= tolerance
               for a,b,c in hull['triangles'])


def verify_hull(hull, label):
    vertices, triangles = hull['vertices'], hull['triangles']
    assert all(len(v)==3 and all(math.isfinite(x) for x in v) for v in vertices), label
    directed, edges, volume = Counter(), Counter(), 0
    for tri in triangles:
        assert len(set(tri)) == 3 and all(0 <= i < len(vertices) for i in tri), label
        a,b,c = [vertices[i] for i in tri]
        normal = cross(sub(b,a),sub(c,a))
        assert dot(normal,normal) > 1e-16, label
        assert all(dot(normal,sub(v,a)) < 1e-6 for v in vertices), f'Nonconvex: {label}'
        volume += dot(a,cross(b,c))/6
        for i,j in zip(tri,tri[1:]+tri[:1]):
            directed[i,j] += 1
            edges[tuple(sorted((i,j)))] += 1
    assert volume > 1e-10 and all(n==2 for n in edges.values()), label
    assert all(directed[j,i]==n for (i,j),n in directed.items()), label


def rotate(point, yaw):
    c,s = math.cos(yaw),math.sin(yaw)
    return [c*point[0]-s*point[1], s*point[0]+c*point[1],point[2]]


def heading(forward):
    return math.atan2(-forward[0],forward[1])


def chain(sequence):
    """Place by authored flow tangents and return endpoint/heading/placements."""
    position, direction, placements = [0,0,.5], [0,1,0], []
    for piece, reverse in sequence:
        entry,exit = piece['road']['connectors']
        if reverse:
            entry,exit = exit,entry
        entry_forward = [-x for x in entry['forward']] if reverse else entry['forward']
        exit_forward = [-x for x in exit['forward']] if reverse else exit['forward']
        yaw = heading(direction)-heading(entry_forward)
        origin = sub(position,rotate(entry['position_m'],yaw))
        next_position = [a+b for a,b in zip(origin,rotate(exit['position_m'],yaw))]
        next_direction = rotate(exit_forward,yaw)
        placements.append((piece['id'],origin,yaw))
        position,direction = next_position,next_direction
    return position,direction,placements


def main():
    source = json.loads((ROOT/'source'/'geometry.json').read_text())
    catalog = json.loads((ROOT/'catalog.json').read_text())
    assert catalog['version'] == '0.2.0'
    blocks = catalog['forge_pack']['blocks']
    assert source['units']=='meters' and source['axes']=='right_handed_z_up'
    assert len(source['pieces']) == len(blocks) == 10
    assert [p['id'] for p in source['pieces']] == [
        ident+suffix for suffix in ('','_guarded')
        for ident in ('straight_24','straight_48','curve_45','curve_90','ramp_48')]
    by_id, hull_count, tri_count, surface_checks = {},0,0,0
    for piece,block in zip(source['pieces'],blocks):
        ident = piece['id']
        by_id[ident] = piece
        assert block['id'] == ident and block['road']==piece['road']
        assert block['tag'] == 'objects\\mjolnir\\forge\\roadworks\\'+ident
        render_distance = piece['render_distance_m']
        assert isinstance(render_distance, (int,float)) and not isinstance(render_distance,bool)
        assert math.isfinite(render_distance) and 0 < render_distance <= 1000, ident
        assert render_distance == 300, f'Roadworks draw distance changed: {ident}'
        assert 'render_distance_m' not in block, 'Draw distance belongs to source authoring, not the Hub catalog'
        hulls = piece['collision']['hulls']
        vertices = piece['collision']['vertices']
        assert len(hulls) <= 256 and len(piece['collision']['triangles']) <= 4096
        assert len(vertices) <= 8192
        lo = [min(v[i] for v in vertices) for i in range(3)]
        hi = [max(v[i] for v in vertices) for i in range(3)]
        close(sub(hi,lo),piece['dimensions_m'])
        assert lo[2] == 0 and piece['origin']=='entry_floor'
        for i,hull in enumerate(hulls):
            verify_hull(hull,f'{ident}/{i}')
        for i,visual in enumerate(piece['visual']):
            verify_hull(visual,f'{ident}/visual/{i}')
            assert all(lo[i]-1e-7 <= v[i] <= hi[i]+1e-7 for v in visual['vertices'] for i in range(3))
        # A concatenated collider must exactly retain all independent hulls.
        flattened_vertices, flattened_triangles = [],[]
        for hull in hulls:
            offset = len(flattened_vertices)
            flattened_vertices.extend(hull['vertices'])
            flattened_triangles.extend([[i+offset for i in tri] for tri in hull['triangles']])
        assert flattened_vertices == vertices and flattened_triangles == piece['collision']['triangles']
        road = piece['road']
        assert road['clear_width_m']==16 and road['deck_width_m']==17.6
        assert road['deck_thickness_m']==.5
        assert road['guardrail_height_m']==(1.5 if ident.endswith('_guarded') else 0)
        entry,exit = road['connectors']
        close(entry['position_m'],[0,0,.5]); close(entry['forward'],[0,1,0])
        for endpoint in (entry,exit):
            assert endpoint['clear_width_m']==16
            close([dot(endpoint['forward'],endpoint['forward'])],[1])
            close([dot(endpoint['forward'],endpoint['up'])],[0])
            close([math.sqrt(dot(sub(*endpoint['edge_points_m']),sub(*endpoint['edge_points_m'])))],[17.6])
        stride = 3 if road['guardrail_height_m'] else 1
        sections = road['sections']
        for index,(a,b) in enumerate(zip(sections,sections[1:])):
            deck = hulls[index*stride]
            # Every sample on each actual faceted travel surface has solid deck
            # below and free space above, including near both guarded edges.
            for t in (0,.125,.5,.875,1):
                for lateral in (-7.999,-6.5,-3.25,0,3.25,6.5,7.999):
                    points = [[s['center_m'][i]+lateral*s['right'][i] for i in range(3)] for s in (a,b)]
                    p = [points[0][i]*(1-t)+points[1][i]*t for i in range(3)]
                    assert inside([p[0],p[1],p[2]-.001],deck), (ident,index,p)
                    assert not any(inside([p[0],p[1],p[2]+.01],h) for h in hulls), (ident,index,p)
                    surface_checks += 1
            if index:
                previous = hulls[(index-1)*stride]
                # End and next-start faces are exactly shared, without a lip.
                assert previous['vertices'][2]==deck['vertices'][1]
                assert previous['vertices'][3]==deck['vertices'][0]
                assert previous['vertices'][6]==deck['vertices'][5]
                assert previous['vertices'][7]==deck['vertices'][4]
            if stride==3:
                for rail in hulls[index*stride+1:index*stride+3]:
                    assert not inside([(a['center_m'][i]+b['center_m'][i])/2
                                       + (0.5 if i==2 else 0) for i in range(3)],rail)
                    close([v[2] for v in rail['vertices'][4:]],
                          [s['center_m'][2]+1.5 for s in (a,a,b,b)])
        if 'centerline_radius_m' in road:
            assert road['centerline_radius_m']==40
            expected_exit = [-40,40,.5] if road['turn_degrees']==90 else [-11.715728753,28.284271247,.5]
            close(exit['position_m'],expected_exit)
            assert not any(inside([-40,0,.25],h) for h in hulls), 'Curve filled its inside'
            # Polygon strips have 16m radial clear width and >=15.99m normal width.
            assert 16*math.cos(math.radians(road['turn_degrees']/road['segment_count']/2)) > 15.99
        if 'rise_m' in road:
            assert road['run_m']==48 and road['rise_m']==4 and road['flat_end_m']==4
            assert road['easing_run_m']==8 and road['max_grade']==.125
            slopes = [(b['center_m'][2]-a['center_m'][2])/(b['center_m'][1]-a['center_m'][1])
                      for a,b in zip(sections,sections[1:])]
            assert slopes[0]==slopes[-1]==0 and max(slopes)<=.125+1e-9
            assert all(abs(a-b)<.0475 for a,b in zip(slopes,slopes[1:])), slopes
            close(exit['position_m'],[0,48,4.5])
            close(sections[1]['center_m'],[0,4,.5])
            close(sections[-2]['center_m'],[0,44,4.5])
        elif 'run_m' in road:
            expected_run = 24 if ident.startswith('straight_24') else 48
            assert road['run_m']==expected_run
            close(exit['position_m'],[0,expected_run,.5])
        hull_count += len(hulls)
        tri_count += len(piece['collision']['triangles'])
    assert len(by_id)==10
    # Actual assembler cases: a loop closes, two45s equal one90, and a ramp
    # reverse-connected from the elevated deck returns to the original height.
    for guarded in ('','_guarded'):
        straight = by_id['straight_48'+guarded]
        curve = by_id['curve_90'+guarded]
        pos,direction,_ = chain([(p,False) for p in (straight,curve)*4])
        close(pos,[0,0,.5]); close(direction,[0,1,0])
        pos,direction,_ = chain([(by_id['curve_45'+guarded],False)]*2)
        close(pos,curve['road']['connectors'][1]['position_m'])
        close(direction,curve['road']['connectors'][1]['forward'])
        ramp = by_id['ramp_48'+guarded]
        pos,direction,_ = chain([(ramp,False),(straight,False),(ramp,True)])
        close(pos,[0,144,.5]); close(direction,[0,1,0])
    print(f'PASS: 10 pieces; {hull_count} closed convex hulls; {tri_count} triangles; '
          f'{surface_checks} surface probes; exact inter-slice seams, closed loops and reverse ramp connectors')


if __name__ == '__main__':
    main()
