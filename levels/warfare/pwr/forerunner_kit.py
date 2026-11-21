"""Original metre-space Forerunner architecture, shared by preview and HEK.

Each structural piece is a closed solid. Accent panels are separate visual
pieces. No operation flattens terrain; the caller supplies a prepared terrace.
"""
from __future__ import annotations
import math


def prism(profile, half_width):
    """Extrude a Y/Z profile across X, returning vertices and closed faces."""
    n = len(profile)
    vertices = [(x, y, z) for x in (-half_width, half_width) for y, z in profile]
    faces = [tuple(reversed(range(n))), tuple(range(n, 2*n))]
    faces += [(i, (i+1)%n, (i+1)%n+n, i+n) for i in range(n)]
    return vertices, faces


def ring(rings, sides=12):
    vertices = [(r*math.cos(i*math.tau/sides), r*math.sin(i*math.tau/sides), z)
                for r,z in rings for i in range(sides)]
    faces = [tuple(reversed(range(sides))), tuple(range((len(rings)-1)*sides,len(rings)*sides))]
    for j in range(len(rings)-1):
        faces += [(j*sides+i,j*sides+(i+1)%sides,(j+1)*sides+(i+1)%sides,(j+1)*sides+i)
                  for i in range(sides)]
    return vertices,faces


def pieces(name, center, citadel=False, heading=0):
    """Build layered three-arm architecture; accent=False pieces form hulls.

    The south approach remains open. The major spires sit behind the plaza,
    leaving a generous foreground apron for spawning and vehicle circulation.
    """
    output=[]
    scale=1.45 if citadel else 1.0
    def add(suffix,geometry,material='metal',angle=0,offset=(0,0,0),accent=False):
        vertices,faces=geometry
        a=math.radians(angle); c,s=math.cos(a),math.sin(a)
        h=math.radians(heading); hc,hs=math.cos(h),math.sin(h)
        placed=[]
        for x,y,z in vertices:
            xx=(x*c-y*s+offset[0])*scale; yy=(x*s+y*c+offset[1])*scale
            placed.append((center[0]+xx*hc-yy*hs,center[1]+xx*hs+yy*hc,center[2]+(z+offset[2])*scale))
        output.append({'name':name+'_'+suffix,'vertices_m':placed,'faces':faces,
                       'material':material,'collision':not accent,'module':suffix})
    # Terrain provides the full terrace; this inset podium is only a 0.35m lip.
    add('plaza',ring([(81,-1.2),(81,0),(78,.35)],12),'floor')
    # The south half is an open turning apron. Three fins focus on a rear hub.
    add('hub',ring([(21,0),(24,8),(17,20),(12,27)],8),offset=(0,20,0))
    for index,angle in enumerate((0,120,240)):
        # Long tapered foundations and tiered sloping roof planes.
        add(f'wing_{index}',prism([(12,0),(75,0),(70,5),(42,10),(12,21)],11),angle=angle,offset=(0,20,0))
        add(f'wing_shoulder_{index}',prism([(18,9),(59,4),(62,6),(40,13),(18,23)],8),angle=angle,offset=(0,20,0))
        # Thin azure roof channel and two raised protective metal rails.
        add(f'energy_channel_{index}',prism([(21,21.8),(59,7.0),(60,7.4),(21,22.2)],.8),'energy',angle,offset=(0,20,0),accent=True)
        for side in (-1,1):
            add(f'roof_rail_{index}_{side}',prism([(22,21),(62,5.6),(62,7.1),(22,22.5)],.9),angle=angle,offset=(side*8.8,20,0),accent=True)
        # Faceted blade profile: tall, swept, tapered; no cylindrical towers.
        blade=[(-11,0),(14,0),(13,32),(5,68),(-2,73),(-6,57),(-7,26)]
        add(f'blade_{index}',prism(blade,5.8),angle=angle,offset=(0,25,9))
        add(f'blade_spine_{index}',prism([(12,8),(14,8),(13,32),(5,67),(3.7,66),(11.4,31)],.78),
            'energy',angle,offset=(0,25,9),accent=True)
        # Layered outer pylons echo the central silhouette.
        add(f'outer_pylon_{index}',prism([(-5,0),(7,0),(5,12),(0,28),(-3,27)],3.2),angle=angle,offset=(-math.sin(math.radians(angle))*68,20+math.cos(math.radians(angle))*68,0))
    # Low perimeter markers preserve clear approaches and open sight lines.
    for i,angle in enumerate((15,45,75,105,135,165,195,345)):
        a=math.radians(angle)
        add(f'perimeter_marker_{i}',prism([(-2,0),(2,0),(2,2.5),(-2,3.8)],4),angle=angle,
            offset=(74*math.cos(a),74*math.sin(a),.35))
    # Approach ramp is wide enough for a tank, without any sealed doorway.
    add('approach_ramp',prism([(-101,-1),(-72,-1),(-72,.35),(-101,-.2)],18),'floor')
    return output


def triangle_count(parts,collision_only=False):
    return sum(len(face)-2 for p in parts if p['collision'] or not collision_only for face in p['faces'])


if __name__=='__main__':
    import json
    p=pieces('headquarters',(0,0,0))
    print(json.dumps({'modules':len(p),'triangles':triangle_count(p),'collision_triangles':triangle_count(p,True)}))
