"""Exact planar clipping creates clean non-colliding roads on the native triangle shell."""
import layout

def half(poly,axis,bound,positive=True):
    result=[]
    if not poly: return result
    for a,b in zip(poly,poly[1:]+poly[:1]):
        av,bv=a[axis]-bound,b[axis]-bound
        inside=av>=-1e-8 if positive else av<=1e-8
        other=bv>=-1e-8 if positive else bv<=1e-8
        if inside: result.append(a)
        if inside!=other:
            t=av/(av-bv)
            result.append(tuple(a[k]+t*(b[k]-a[k]) for k in range(3)))
    clean=[]
    for p in result:
        if not clean or sum((p[k]-clean[-1][k])**2 for k in range(3))>1e-12: clean.append(p)
    if len(clean)>1 and sum((clean[0][k]-clean[-1][k])**2 for k in range(3))<1e-12: clean.pop()
    return clean if len(clean)>=3 else []

def rectangles():
    r=[]
    for x in (-650,650): r.append((x-12,x+12,-800,800))
    for y in (-650,650):
        r.extend([(-760,-250,y-12,y+12),(250,760,y-12,y+12)])
    for y,span in ((0,850),(-350,650),(350,650),(-800,650),(800,650)):
        r.append((-span,span,y-12,y+12))
    r.append((-512,-488,650,800))
    for x,y,_ in layout.CAPTURES+layout.SATELLITES:
        side=-650 if x<0 else 650
        r.append((min(x,side)-10,max(x,side)+10,y-12,y+12))
    return r

def build(triangles,lift=.12):
    verts,faces=[],[]
    rects=rectangles()
    for tri in triangles:
        remaining=[list(tri)]
        tx=[p[0] for p in tri]; ty=[p[1] for p in tri]
        for x0,x1,y0,y1 in rects:
            if max(tx)<x0 or min(tx)>x1 or max(ty)<y0 or min(ty)>y1: continue
            outside=[]
            for poly in remaining:
                inside=poly
                for axis,bound,positive in ((0,x0,True),(0,x1,False),(1,y0,True),(1,y1,False)):
                    rejected=half(inside,axis,bound,not positive)
                    if rejected: outside.append(rejected)
                    inside=half(inside,axis,bound,positive)
                    if not inside: break
                if inside:
                    cy=sum(p[1] for p in inside)/len(inside)
                    if min(abs(cy-800),abs(cy+800))>13:
                        inside=half(inside,2,layout.WATER_Z+.04)
                    if inside:
                        start=len(verts); verts.extend((p[0],p[1],p[2]+lift) for p in inside)
                        for k in range(1,len(inside)-1):
                            a,b,c=(inside[j] for j in (0,k,k+1))
                            area=abs((b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0]))
                            if area>.0001: faces.append((start,start+k,start+k+1))
            remaining=outside
            if not remaining: break
    return verts,faces
