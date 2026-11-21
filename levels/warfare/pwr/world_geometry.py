"""Pure geometry helpers for the finalized heightfield world; no app side effects."""
import math
import numpy as np
from forerunner_kit import pieces

def boundary_loop(triangles):
    directed={}
    for tri in triangles:
        for a,b in zip(tri,(tri[1],tri[2],tri[0])):
            key=tuple(sorted((int(a),int(b))))
            directed.setdefault(key,[]).append((int(a),int(b)))
    edges=[uses[0] for uses in directed.values() if len(uses)==1]
    if any(len(uses)>2 for uses in directed.values()): raise ValueError("Nonmanifold terrain edge")
    successor=dict(edges)
    if len(successor)!=len(edges): raise ValueError("Ambiguous terrain boundary")
    start=min(successor);loop=[start];current=successor[start]
    while current!=start:
        if current in loop or current not in successor: raise ValueError("Broken terrain boundary")
        loop.append(current);current=successor[current]
    if len(loop)!=len(edges): raise ValueError("Terrain must have exactly one boundary loop")
    return loop

def sealed_air(vertices,triangles,sky_z):
    """Inward-facing terrain, walls and ceiling; every boundary vertex retained."""
    points=[tuple(map(float,p)) for p in vertices]
    if sky_z<=max(p[2] for p in points)+30: raise ValueError("Sky must leave at least30m above all terrain")
    faces=[tuple(map(int,t)) for t in triangles]
    ground_count=len(faces);loop=boundary_loop(triangles)
    upper=[]
    for i in loop:
        upper.append(len(points));points.append((points[i][0],points[i][1],float(sky_z)))
    for j,i in enumerate(loop):
        k=(j+1)%len(loop)
        faces.extend([(i,upper[j],upper[k]),(i,upper[k],loop[k])])
    centre=len(points)
    points.append((float(np.mean([points[i][0] for i in loop])),float(np.mean([points[i][1] for i in loop])),float(sky_z)))
    for j in range(len(loop)): faces.append((centre,upper[(j+1)%len(loop)],upper[j]))
    return points,faces,ground_count

def base_parts(geometry,hull_dir=None):
    output=[]
    for site in geometry["sites"]:
        if site["role"] not in ("permanent_base","dominant_northern_citadel"):continue
        output.extend(p for p in pieces(site["id"],site["position_m"],site["role"]=="dominant_northern_citadel",site.get("heading_degrees",0))
                      if not p["module"].startswith("blade_"))
    if hull_dir is not None:
        from forerunner_stock import collision_parts
        output.extend(collision_parts(geometry,hull_dir))
    return output

def bridge_parts(geometry,field):
    """Closed swept decks along the authoritative, graded road cross-sections."""
    output=[]
    for road in geometry["roads"]:
        if road.get("structure") not in ("bridge","culvert"):continue
        sections=road["cross_sections_m"]
        # Width24 is the clear driving deck, shoulder supports stay outside it.
        offsets=road["cross_section_offsets_m"]
        left=offsets.index(-12);right=offsets.index(12)
        # Retain every authoritative cross-section. An arbitrary decimation can
        # change vertical curves and fail native/render deck agreement.
        chosen=list(range(len(sections)))
        vertices=[]
        for i in chosen:
            a,b=sections[i][left],sections[i][right]
            vertices.extend([tuple(a),tuple(b),(a[0],a[1],a[2]-2),(b[0],b[1],b[2]-2)])
        faces=[]
        for j in range(len(chosen)-1):
            a=j*4;b=(j+1)*4
            faces.extend([(a,a+1,b+1,b),(a+2,b+2,b+3,a+3),(a,b,b+2,a+2),(a+1,a+3,b+3,b+1)])
        last=(len(chosen)-1)*4
        faces.extend([(0,2,3,1),(last,last+1,last+3,last+2)])
        output.append({"name":road["id"]+"_deck","vertices_m":vertices,"faces":faces,
                       "material":"floor","collision":True,"module":"graded_bridge"})
    return output

def road_surfaces(geometry,lift=.03):
    output=[]
    for road in geometry["roads"]:
        if road.get("structure"):continue
        rows=road["cross_sections_m"];offsets=road["cross_section_offsets_m"]
        indices=[i for i,v in enumerate(offsets) if -12<=v<=12]
        vertices=[(row[i][0],row[i][1],row[i][2]+lift) for row in rows for i in indices]
        n=len(indices);faces=[]
        for j in range(len(rows)-1):
            for i in range(n-1):
                a=j*n+i;b=(j+1)*n+i
                faces.extend([(a,b,b+1),(a,b+1,a+1)])
        output.append({"name":road["id"]+"_surface","vertices_m":vertices,"faces":faces,
                       "material":"road","collision":False,"module":"contour_road"})
    return output

def orient_closed(vertices,faces):
    """Use signed volume to correct whole closed module orientation."""
    vertices=np.asarray(vertices,dtype=float);volume=0.
    for face in faces:
        a=vertices[face[0]]
        for j in range(1,len(face)-1):volume+=float(np.dot(a,np.cross(vertices[face[j]],vertices[face[j+1]])))
    if abs(volume)<1e-8:raise ValueError("Degenerate closed gameplay hull")
    return [tuple(reversed(face)) for face in faces] if volume<0 else faces
