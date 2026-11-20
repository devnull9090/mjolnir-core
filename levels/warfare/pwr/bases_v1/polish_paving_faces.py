"""Fit visual-only paving, gallery shoe cladding and segmented sill plates to the PWR bases."""
from pathlib import Path
import sys
import bpy,bmesh
from mathutils import Matrix,Vector
from mathutils.geometry import normal

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
from finishing_materials import finish_scene_geometry

def ccw(p):
    return p if sum(a.x*b.y-b.x*a.y for a,b in zip(p,p[1:]+p[:1]))>=0 else list(reversed(p))

def cross(a,b):return a.x*b.y-a.y*b.x

def clip(poly,a,b,inside=True):
    if not poly:return []
    out=[]
    for u,v in zip(poly,poly[1:]+poly[:1]):
        x=cross(b-a,u-a); y=cross(b-a,v-a)
        if not inside:x,y=-x,-y
        if x>=-1e-8:out.append(u)
        if (x>=-1e-8)!=(y>=-1e-8):
            out.append(u.lerp(v,max(0,min(1,x/(x-y)))))
    return compact(out)

def compact(poly):
    return [p for i,p in enumerate(poly) if (p-poly[i-1]).length>.0003]

def subtract(poly,mask):
    if any(max(p[i] for p in poly)<min(p[i] for p in mask) or min(p[i] for p in poly)>max(p[i] for p in mask) for i in (0,1)):
        return [poly]
    live=poly
    pieces=[]
    for a,b in zip(mask,mask[1:]+mask[:1]):
        off=clip(live,a,b,False)
        if len(off)>2:pieces.append(off)
        live=clip(live,a,b)
        if len(live)<3:return [poly]
    return pieces

def inset(poly,distance):
    # Intersect the parallel offsets of adjacent edges rather than moving
    # radially toward the centroid. The pale cut is 65 mm everywhere.
    res=[]
    for i,p in enumerate(poly):
        u=(p-poly[i-1]).to_2d().normalized()
        v=(poly[(i+1)%len(poly)]-p).to_2d().normalized()
        nu=Vector((-u.y,u.x)); nv=Vector((-v.y,v.x))
        denom=1+nu.dot(nv)
        shift=(nu+nv)*(distance/max(.035,denom))
        res.append(Vector((p.x+shift.x,p.y+shift.y,p.z)))
    return res

class Skin:
    def __init__(self,label):
        self.label=label;self.v=[];self.f=[];self.mat=[];self.count=0
    def component(self,rings,face_mat,edge_mat):
        n=len(rings[0]);start=len(self.v)
        for row in rings:self.v.extend(row)
        def face(indices,mat):
            self.f.append(tuple(start+i for i in indices));self.mat.append(mat)
        face(list(reversed(range(n))),face_mat)
        for i in range(len(rings)-1):
            for j in range(n):
                k=(j+1)%n
                face((i*n+j,i*n+k,(i+1)*n+k,(i+1)*n+j), edge_mat[i][j] if isinstance(edge_mat[i],list) else edge_mat[i])
        face(list(range((len(rings)-1)*n,len(rings)*n)),face_mat)
        self.count+=1
    def publish(self):
        cols=[next(c for c in bpy.data.collections if c.name.startswith(s)) for s in ('01_RED','02_BLUE','03_GREEN')]
        mesh=bpy.data.meshes.new('Lookdev / '+self.label);mesh.from_pydata(self.v,[],self.f);mesh.update()
        slots=list(dict.fromkeys(self.mat))
        for key in slots:mesh.materials.append(next(m for m in bpy.data.materials if m.get('native_finish_profile')==key))
        for p,k in zip(mesh.polygons,self.mat):p.material_index=slots.index(k)
        bm=bmesh.new();bm.from_mesh(mesh);bmesh.ops.recalc_face_normals(bm,faces=bm.faces[:]);bm.to_mesh(mesh);bm.free();mesh.update()
        obs=[]
        for team,c,center,s in zip(('red','blue','green'),cols,((0,0,0),(135,0,0),(0,150,0)),(1,-1,1)):
            ob=bpy.data.objects.new(('' if team=='red' else c.name.split()[0]+'/')+mesh.name,mesh)
            c.objects.link(ob);ob.matrix_world=Matrix.Translation(center)@Matrix.Diagonal((s,1,1,1));ob['pwr_polish_site']=team;ob['collision']='none';ob['lookdev_host_fit']=True
            if obs:ob['mirror_source_object']=obs[0].name
            obs.append(ob)
        bpy.context.view_layer.update();finish_scene_geometry({},objects=obs)
        return obs

def fit_z(pts,host):
    n=normal(host)
    return [Vector((p.x,p.y,p.z-(n.x*(p.x-q.x)+n.y*(p.y-q.y))/n.z)) for p,q in zip(pts,host)]


def pave(batch,points,finish,width=.064):
    p=ccw(compact(points))
    if len(p)<3:return
    area=sum(cross(a,b) for a,b in zip(p,p[1:]+p[:1]))*.5
    if area<.16:return
    perimeter=sum((b-a).length for a,b in zip(p,p[1:]+p[:1]))
    width=min(width,area/perimeter*.31)
    q=fit_z(inset(p,.003),p);u=fit_z(inset(p,width),p)
    n=len(q)
    # Shallow bright worn arris narrowing into the actual traffic surface.
    def lift(vert,h):return Vector((vert.x,vert.y,vert.z+h))
    # A .5 mm bedding gap clears coplanars. All 2–3 cm relief is visual.
    lower=[lift(v,.001) for v in q]
    shoulder=[lift(v,.005) for v in q]
    top=[lift(v,.032) for v in u]
    gleam=['trim' if abs(q[(i+1)%n].y-q[i].y)>abs(q[(i+1)%n].x-q[i].x) else 'alloy' for i in range(n)]
    batch.component([lower,shoulder,top],finish,['dark_floor',gleam])


def faces(ob):
    for p in ob.data.polygons:
        coords=[ob.matrix_world@ob.data.vertices[i].co for i in p.vertices]
        yield coords,normal(coords).normalized()


def build():
    cols=next(c for c in bpy.data.collections if c.name.startswith('01_RED'))
    paving=Skin("Faceted entrance paving")
    dress=Skin("Cast gallery shoe cladding")
    rails=Skin("Ramp sill cover plates")
    tongues=[]
    for pts,n in faces(bpy.data.objects['polish/fitted approach tongue slabs']):
        if n.z<.90:continue
        tongues.append(ccw(pts))
    for i,pts in enumerate(tongues):
        # Use cool wheel-worn faces in coherent bands, with intermittently
        # warmer stone-metal at each wing. Left/right use the same course.
        row,col=divmod(i%15,3)
        finishes=(('floor','interior_finish_v0','apron_finish_v0'),
                  ('floor','interior_finish_v0','apron_finish_v1'),
                  ('apron_finish_v0','floor','apron_finish_v1'),
                  ('apron_finish_v0','interior_finish_v0','floor'),
                  ('floor','floor','apron_finish_v0'))
        pave(paving,pts,finishes[row][col],.077)
    inner=[];outer=[]
    for ob in cols.objects:
        cat=inner if ob.name.startswith('apron/inset fitted traffic slab') else outer if ob.name.startswith('apron/individual fitted alloy slab') else None
        if cat is not None:
            for pts,n in faces(ob):
                if n.z>.98:cat.append(ccw(pts))
    # The ornamental inset traffic field rides 23 mm higher than the original
    # field. Split the lower layer around it and the protruding tongues.
    masks=[]
    for sign in (-1,1):
        masks.append(ccw([Vector((sign*x,y,0)) for x,y in ((11.68,-20.78),(25.38,-20.78),(27.99,-23.4),(18.85,-26.69),(11.68,-24.06))]))
    for kind,polys,blockers in (('inset',inner,tongues),('field',outer,tongues+masks)):
        for p in polys:
            polys_visible=[clip(p,Vector((60,-21.19,0)),Vector((-60,-21.19,0)))]
            for mask in blockers:
                polys_visible=[q for r in polys_visible if len(r)>2 for q in subtract(r,mask)]
            for q in polys_visible:
                if len(q)<3:continue
                x=sum(abs(v.x) for v in q)/len(q);y=sum(v.y for v in q)/len(q)
                finish='interior_finish_v0' if kind=='inset' and int(x/5)%2==0 else 'floor' if kind=='inset' else 'apron_finish_v0'
                pave(paving,q,finish,.060)
    # These folded shoes hug the front of the existing outer and inner piers.
    # Their lower band is a satin graphite footing. Leave the route edge open.
    for p,n in faces(bpy.data.objects['polish/gallery surround shoes']):
        if n.y>-.48:continue
        c=sum(p,Vector((0,0,0)))/len(p)
        base=[v.lerp(c,.012)+n*.001 for v in p]
        face=[v.lerp(c,.04)+n*.032 for v in p]
        dress.component([base,face],'floor' if c.z<.74 else 'alloy',['alloy'])
    # Follow the native channel in panels rather than adding a new rail. Both
    # sides of the curb stay within its existing width and end before the turn.
    for ob in cols.objects:
        if not ob.name.startswith('ramp/detailed trim'):continue
        for p,n in faces(ob):
            if n.z<.85:continue
            lo=sorted(p,key=lambda v:v.y)[:2];hi=sorted(p,key=lambda v:v.y)[2:]
            lo.sort(key=lambda v:v.x);hi.sort(key=lambda v:v.x)
            for j in range(7):
                near=[a.lerp(b,(j+.009)/7) for a,b in zip(lo,hi)]
                far=[a.lerp(b,(j+1-.009)/7) for a,b in zip(lo,hi)]
                coords=[near[0],near[1],far[1],far[0]]
                # A single graphite/cool-face in the fine pale side borders.
                pave(rails,coords,'floor',.026)
    all_obs=[]
    for batch in (paving,dress,rails):all_obs.extend(batch.publish())
    return all_obs,{b.label:b.count for b in (paving,dress,rails)}
