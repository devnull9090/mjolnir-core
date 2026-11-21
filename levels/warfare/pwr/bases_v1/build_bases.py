"""Blender-only Forerunner bastion art source. Metres, front = -Y, up = Z.

One modular team-base master, genuinely reflected blue geometry, green citadel.
Does not touch the game, terrain, cooked files, or physics assets.
Execute through the verified Blender MCP session.
"""
import bpy, bmesh, math, json, sys
from mathutils import Vector
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
HERE = Path(__file__).resolve().parent
OUT = ROOT / 'out/pwr/base-art'
ART_SCALE=.65
OUT.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(HERE))

def reset():
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete(use_global=False)
    for c in list(bpy.data.collections):
        if c.name != 'Collection': bpy.data.collections.remove(c)
    bpy.data.orphans_purge(do_local_ids=True,do_linked_ids=False,do_recursive=True)

def collection(name):
    c=bpy.data.collections.new(name); bpy.context.scene.collection.children.link(c); return c

COL=None
def mesh(name, verts, faces, mat, bevel=.06):
    # Facade cap backs tuck beneath the separate roof plates. Equal coplanar
    # faces produced view-dependent tears on reflected instances.
    if name.startswith('facade/'):
        verts=[(x,y,11.16 if abs(z-11.2)<.001 else z) for x,y,z in verts]
    if name.startswith('fin/'):
        verts=[(x,y,11.2+(z-11.2)*1.25) for x,y,z in verts]
    if name.startswith('mount/'):
        verts=[(x*1.25,y*1.25,z-.83 if 'socket insert' in name else z) for x,y,z in verts]
    # Armor inclines back toward the roof datum. Door recesses remain real voids.
    if name.startswith(('facade/','portal/','shoulder/','gallery/front','gallery/enclosing','gallery/upper','detail/')):
        verts=[(x,y-max(0,11.2-z)*.35 if y<-20 else y,z) for x,y,z in verts]
    me=bpy.data.meshes.new(name); me.from_pydata(verts, [], faces); me.update()
    bm=bmesh.new(); bm.from_mesh(me); bmesh.ops.recalc_face_normals(bm, faces=bm.faces); bm.to_mesh(me); bm.free()
    ob=bpy.data.objects.new(name, me); COL.objects.link(ob)
    if mat: me.materials.append(mat)
    uv=me.uv_layers.new(name='AtlasUV')
    band=mat.get('atlas_band', 'alloy') if mat else 'alloy'
    vmin,vmax={'alloy':(.52,.98),'dark':(.265,.485),'trim':(.015,.235)}.get(band,(.52,.98))
    for poly in me.polygons:
        axis=max(range(3),key=lambda k: abs(poly.normal[k])); axes=[k for k in range(3) if k!=axis]
        co=[me.vertices[me.loops[i].vertex_index].co for i in poly.loop_indices]
        mins=[min(v[k] for v in co) for k in axes]; maxs=[max(v[k] for v in co) for k in axes]
        for li,v in zip(poly.loop_indices,co):
            uu=(v[axes[0]]-mins[0])/max(.001,maxs[0]-mins[0]); vv=(v[axes[1]]-mins[1])/max(.001,maxs[1]-mins[1])
            uv.data[li].uv=(.01+.98*uu,vmin+(vmax-vmin)*vv)
    if bevel:
        mod=ob.modifiers.new('Machined edge radii','BEVEL');mod.width=bevel;mod.segments=3
        mod.limit_method='ANGLE'
        wn=ob.modifiers.new('Face weighted normals','WEIGHTED_NORMAL');wn.keep_sharp=True;wn.weight=50
    ob['module_role']=name.split('/')[0]
    return ob

def box(name,loc,size,mat,bevel=.06):
    x,y,z=loc; a,b,c=[s*.5 for s in size]
    v=[(x+i*a,y+j*b,z+k*c) for k in [-1,1] for j in [-1,1] for i in [-1,1]]
    return mesh(name,v,[(0,1,3,2),(4,6,7,5),(0,4,5,1),(2,3,7,6),(0,2,6,4),(1,5,7,3)],mat,bevel)

def prism(name, pointsXZ,y0,y1,mat,bevel=.06):
    n=len(pointsXZ);v=[(x,y,z) for y in [y0,y1] for x,z in pointsXZ]
    return mesh(name,v,[tuple(range(n-1,-1,-1)),tuple(range(n,n*2))]+[(i,(i+1)%n,(i+1)%n+n,i+n) for i in range(n)],mat,bevel)

def slab(name,poly,z0,z1,mat,bevel=.06):
    n=len(poly);v=[(x,y,z) for z in [z0,z1] for x,y in poly]
    return mesh(name,v,[tuple(range(n-1,-1,-1)),tuple(range(n,n*2))]+[(i,(i+1)%n,(i+1)%n+n,i+n) for i in range(n)],mat,bevel)

def cut_convex_hole(poly,hole):
    """Partition polygon outside a convex CCW hole into closed convex pieces."""
    def clip(points,a,b,inside):
        if not points:return []
        def d(p):return (b[0]-a[0])*(p[1]-a[1])-(b[1]-a[1])*(p[0]-a[0])
        out=[]
        for p,q in zip(points,points[1:]+points[:1]):
            dp,dq=d(p),d(q);ip=dp>=-1e-8 if inside else dp<=1e-8;iq=dq>=-1e-8 if inside else dq<=1e-8
            if ip:out.append(p)
            if ip!=iq:
                t=dp/(dp-dq);out.append((p[0]+t*(q[0]-p[0]),p[1]+t*(q[1]-p[1])))
        return out
    remaining=poly;pieces=[]
    for a,b in zip(hole,hole[1:]+hole[:1]):
        outside=clip(remaining,a,b,False)
        if len(outside)>=3:pieces.append(outside)
        remaining=clip(remaining,a,b,True)
    return pieces

def paving_cells(poly, xs, ys, gap=.035):
    """Clip large apron fields into construction-scale convex slabs."""
    def clip(points, axis, limit, above):
        out=[]
        for a,b in zip(points,points[1:]+points[:1]):
            da=a[axis]-limit;db=b[axis]-limit
            ia=da>=0 if above else da<=0;ib=db>=0 if above else db<=0
            if ia:out.append(a)
            if ia!=ib:
                t=da/(da-db);out.append(tuple(a[k]+t*(b[k]-a[k]) for k in range(2)))
        return out
    for xa,xb in zip(xs,xs[1:]):
        for ya,yb in zip(ys,ys[1:]):
            part=list(poly)
            for axis,limit,above in [(0,xa,True),(0,xb,False),(1,ya,True),(1,yb,False)]:
                if part:part=clip(part,axis,limit,above)
            if len(part)<3:continue
            area=abs(sum(a[0]*b[1]-b[0]*a[1] for a,b in zip(part,part[1:]+part[:1])))*.5
            if area<.3:continue
            center=Vector((sum(p[0] for p in part)/len(part),sum(p[1] for p in part)/len(part)))
            yield [tuple(Vector(p)+(center-Vector(p)).normalized()*gap) for p in part]

def beam(name,a,b,width,depth,mat,bevel=.04):
    ob=box(name,(0,0,0),(width,depth,(Vector(b)-Vector(a)).length),mat,bevel)
    ob.location=(Vector(a)+Vector(b))*.5;ob.rotation_euler=(Vector(b)-Vector(a)).to_track_quat('Z','Y').to_euler();return ob

def material(name,color,metal=.55,rough=.44,band=None,emission=0):
    m=bpy.data.materials.new(name);m.diffuse_color=(*color,1);m.use_nodes=True
    n=m.node_tree.nodes;l=m.node_tree.links;p=n.get('Principled BSDF')
    p.inputs['Base Color'].default_value=(*color,1);p.inputs['Metallic'].default_value=metal;p.inputs['Roughness'].default_value=rough
    if emission:
        p.inputs['Emission Color'].default_value=(*color,1);p.inputs['Emission Strength'].default_value=emission
    if band:
        m['atlas_band']=band
        tex=n.new('ShaderNodeTexImage');tex.image=bpy.data.images.load(str(HERE/'textures/forerunner-alloy-atlas.png'),check_existing=True)
        tex.interpolation='Linear'
        tint=n.new('ShaderNodeMixRGB');tint.blend_type='MULTIPLY';tint.inputs[0].default_value=1
        tint.inputs[2].default_value=(.32,.40,.48,1) if band=='dark' else ((.44,.47,.51,1) if 'deck alloy' in name else (.95,.92,.86,1))
        l.new(tex.outputs['Color'],tint.inputs[1])
        broad=n.new('ShaderNodeTexNoise');broad.inputs['Scale'].default_value=.09;broad.inputs['Detail'].default_value=2.2
        broadcoord=n.new('ShaderNodeTexCoord');l.new(broadcoord.outputs['Object'],broad.inputs['Vector'])
        variation=n.new('ShaderNodeValToRGB');variation.color_ramp.elements[0].color=(.84,.87,.90,1);variation.color_ramp.elements[1].color=(1,1,1,1)
        l.new(broad.outputs['Fac'],variation.inputs[0])
        finish=n.new('ShaderNodeMixRGB');finish.blend_type='MULTIPLY';finish.inputs[0].default_value=.65
        l.new(tint.outputs[0],finish.inputs[1]);l.new(variation.outputs[0],finish.inputs[2]);l.new(finish.outputs[0],p.inputs['Base Color'])
        noise=n.new('ShaderNodeTexNoise');noise.inputs['Scale'].default_value=42;noise.inputs['Detail'].default_value=3
        coord=n.new('ShaderNodeTexCoord');l.new(coord.outputs['Object'],noise.inputs['Vector'])
        ramp=n.new('ShaderNodeMapRange');ramp.inputs['From Min'].default_value=0;ramp.inputs['From Max'].default_value=1
        ramp.inputs['To Min'].default_value=rough-.10;ramp.inputs['To Max'].default_value=rough+.12
        l.new(noise.outputs['Fac'],ramp.inputs['Value']);l.new(ramp.outputs['Result'],p.inputs['Roughness'])
        bump=n.new('ShaderNodeBump');bump.inputs['Strength'].default_value=.17;bump.inputs['Distance'].default_value=.018
        l.new(noise.outputs['Fac'],bump.inputs['Height']);l.new(bump.outputs['Normal'],p.inputs['Normal'])
    return m

def make_mats():
    return {'alloy':material('FR • silver satin alloy',(.36,.40,.44),.68,.35,'alloy'),
    'dark':material('FR • inset blue graphite',(.09,.13,.18),.48,.50,'dark'),
    'dark_floor':material('FR • dark traffic paving',(.09,.13,.18),.20,.72,'dark'),
    'trim':material('FR • engraved narrow trim',(.4,.45,.5),.6,.38,'trim'),
    'floor':material('FR • textured deck alloy',(.24,.27,.29),.35,.59,'alloy'),
    'black':material('FR • shadow channels',(.018,.026,.035),.4,.53),
    'team':material('TEAM • red recessed energy',(.65,.015,.009),.32,.36,None,2.5),
    'white':material('FR • cool interior light',(.40,.77,1),.15,.22,None,4.5)}

def frame(name,y,inner,outer,depth,mat):
    # A physically hollow polygonal arch: individual closed frame segments, no blocking cap.
    for i in range(len(inner)-1):
        prism(name+str(i),[inner[i],inner[i+1],outer[i+1],outer[i]],y-depth*.5,y+depth*.5,mat,.09)

def build_master(m):
    global COL
    COL=collection('01_RED • master architecture')
    deck=[(-39,-25),(-42,-17),(-42,17),(-34,25),(34,25),(42,17),(42,-17),(39,-25)]
    apron=[(-42,-36),(-49,-22),(-49,22),(-39,32),(39,32),(49,22),(49,-22),(42,-36)]
    slab('foundation/continuous footplate',apron,-.7,0,m['dark'],.15)
    slab('floor/covered hall',deck,-.05,.10,m['dark_floor'],.02)
    for row,ya in enumerate(range(-25,24,6)):
        # Full-thickness flush paving with staggered joints throughout the rooms.
        xs=sorted(set([-42,42]+[x+(3 if row%2 else 0) for x in range(-42,43,6) if -42<x+(3 if row%2 else 0)<42]))
        for part in paving_cells(deck,xs,[ya,min(25,ya+6)],gap=.025):
            slab('floor/inset structural paving slab',part,-.03,.20,m['floor'],.014)
    for y in [-30,29]:
        box('floor/vehicle threshold',(0,y,.1),(28,14,.2),m['floor'],.025)
    for s in [-1,1]:
        for part in paving_cells([(29,-37),(37,-37),(37,-25.04),(29,-25.04)],[29,33,37],[-37,-31,-25.04],gap=.025):
            slab('floor/flush gallery approach',[(s*x,y) for x,y in part],-.08,.20,m['floor'],.014)
    # Segmented paving, not a printed radial disc.
    for s in [-1,1]:
        for j in range(5):
            x0=12+j*6.6
            slab('apron/angular plate',[(s*x0,-35),(s*(x0+6.4),-35),(s*(x0+6.4),-27),(s*x0,-27)],.02,.16,m['floor'],.035)
        approach=[(13,-29),(43,-29),(50,-37),(27,-45),(13,-39)]
        slab('apron/continuous angular substructure',[(s*x,y) for x,y in approach],-.25,.16,m['dark'],.10)
        for part in paving_cells(approach,[13,19,25,31,37,43,50],[-46,-39,-33,-28]):
            slab('apron/individual fitted alloy slab',[(s*x,y) for x,y in part],.15,.20,m['alloy'],.022)
        inset=[(18,-32),(39,-32),(43,-36),(29,-41),(18,-37)]
        slab('apron/inset angular substructure',[(s*x,y) for x,y in inset],.201,.208,m['black'],.01)
        for part in paving_cells(inset,[18,24,30,36,43],[-42,-36.5,-31]):
            slab('apron/inset fitted traffic slab',[(s*x,y) for x,y in part],.209,.224,m['dark_floor'],.012)
    # Roof in panels with actual seams. Central section broad enough for 30m mount envelope.
    hole=[(10*math.cos(i*math.pi/4+math.pi/8),10*math.sin(i*math.pi/4+math.pi/8)) for i in range(8)]
    roof_panels=[]
    for yi in range(4):
        y0=-24+yi*12;y1=y0+11.94
        xs=[-35,-20,-2,17,35] if yi%2==0 else [-35,-25,-8,11,35]
        for x0,x1 in zip(xs,xs[1:]):
            ob=slab('roof/large staggered armor plate',[(x0,y0),(x1-.06,y0),(x1-.06,y1),(x0,y1)],10.2,11.2,m['alloy'],.07)
            if x0<10 and x1>-10 and y0<10 and y1>-10:roof_panels.append(ob)
    # A real Boolean aperture avoids beveling artificial polygon-partition
    # boundaries across otherwise continuous panels.
    cutter=slab('Temporary cannon aperture cutter',hole,9.0,12.5,None,0)
    for ob in roof_panels:
        bpy.context.view_layer.objects.active=ob
        mod=ob.modifiers.new('Recessed cannon aperture','BOOLEAN');mod.operation='DIFFERENCE';mod.solver='EXACT';mod.object=cutter
        while ob.modifiers.find(mod.name)>0:bpy.ops.object.modifier_move_up(modifier=mod.name)
        bpy.ops.object.modifier_apply(modifier=mod.name)
        if not ob.data.polygons:raise RuntimeError('Roof aperture removed entire deck panel')
    cutter_data=cutter.data;bpy.data.objects.remove(cutter,do_unlink=True);bpy.data.meshes.remove(cutter_data)
    for s in [-1,1]:
        slab('roof/chamfered shoulder',[(s*35,-24),(s*41,-16),(s*41,16),(s*34,24)],10.2,11.22,m['alloy'],.1)
    box('roof/rear gallery closure',(0,25,10.7),(78,4,1.08),m['alloy'],.09)
    slab('roof/gateway crown',[(-15,-22),(-13,-27.5),(13,-27.5),(15,-22)],10.15,11.24,m['alloy'],.13)
    for s in [-1,1]:
        slab('roof/integrated ramp shoulder',[(s*40,-21),(s*46.1,-18),(s*46.1,16),(s*40,22)],10.2,11.26,m['alloy'],.15)
        slab('roof/front wing junction armor',[(s*35,-24),(s*40,-24),(s*46.1,-18),(s*41,-16),(s*35,-16)],10.3,11.32,m['alloy'],.10)
        slab('roof/rear wing junction armor',[(s*34,24),(s*40,24),(s*46.1,20),(s*46.1,16),(s*40,16),(s*34,20)],10.3,11.34,m['alloy'],.10)
    inner=[(-13,.2),(-13,3),(-9.1,9),(9.1,9),(13,3),(13,.2)]
    outer=[(-18.2,0),(-18.2,3.5),(-11.7,11.2),(11.7,11.2),(18.2,3.5),(18.2,0)]
    for y in [24]:
        rear_inner=[(-4.5,.2),(-4.5,2.7),(-4.0,6.4),(-2.9,7.5),(2.9,7.5),(4.0,6.4),(4.5,2.7),(4.5,.2)]
        rear_outer=[(-18.2,0),(-18.2,3.5),(-14,9.8),(-11.7,11.2),(11.7,11.2),(14,9.8),(18.2,3.5),(18.2,0)]
        frame('portal/monolithic outer jamb',y,rear_inner,rear_outer,2.6,m['alloy'])
        inner2=[(-13.195,.2),(-13.195,3),(-9.256,9.15),(9.256,9.15),(13.195,3),(13.195,.2)]
        outer2=[(-14.04,.2),(-14.04,3.15),(-9.88,9.75),(9.88,9.75),(14.04,3.15),(14.04,.2)]
        rear_trim=[(-4.62,.2),(-4.62,2.73),(-4.12,6.48),(-3.02,7.65),(3.02,7.65),(4.12,6.48),(4.62,2.73),(4.62,.2)]
        rear_rim=[(-5.15,.2),(-5.15,2.8),(-4.65,6.75),(-3.37,8.1),(3.37,8.1),(4.65,6.75),(5.15,2.8),(5.15,.2)]
        frame('portal/dark rebated ring',25.33,rear_trim,rear_rim,.16,m['dark'])
    # Repeated structural tunnel ribs, lining behind them; crosscuts into the galleries at y=4..14.
    for y in [-16,-6,4,14]:
        frame('tunnel/structural rib',y,inner,[(-14.82,.2),(-14.82,3.3),(-10.4,10),(10.4,10),(14.82,3.3),(14.82,.2)],1.2,m['alloy'])
    frame('tunnel/deep entrance soffit',-21,[(-12,.2),(-12,2.7),(-8.1,7.8),(8.1,7.8),(12,2.7),(12,.2)],
          [(-14,.2),(-14,3.3),(-10.4,9.7),(10.4,9.7),(14,3.3),(14,.2)],2.2,m['dark'])
    for s in [-1,1]:
        for ya,yb in [(-25,-18),(-17,-8),(-7,1),(16,23)]:
            prism('tunnel/lining lower',[(s*14.4,.2),(s*15.2,.2),(s*15.2,3.6),(s*14.4,3.2)],ya,yb,m['dark'],.04)
            prism('tunnel/lining angled',[(s*13.65,3.2),(s*9.49,9.5),(s*11.05,10.1),(s*14.69,3.5)],ya,yb,m['dark'],.04)
    box('tunnel/ceiling',(0,0,9.8),(18.98,51,.45),m['dark'],.08)
    # Flanking angled armor blocks have depth and functional space behind, not solid building fill.
    for s in [-1,1]:
        # Front shoulders between vehicle portal and gallery.
        # Wide portals to real infantry/vehicle refuge galleries.
        cx=s*28
        small=[(cx-4,.2),(cx-4,2.4),(cx-2.8,5.2),(cx+2.8,5.2),(cx+4,2.4),(cx+4,.2)]
        big=[(cx-5.3,0),(cx-5.3,2.7),(cx-3.6,6.5),(cx+3.6,6.5),(cx+5.3,2.7),(cx+5.3,0)]
        # Load-bearing spandrel and jamb infill surround a real portal opening.
        infill=[(cx-6,0),(cx-6,3),(cx-6,10.8),(cx+6,10.8),(cx+6,3),(cx+6,0)]
        # Outermost shoulder closes frontage beyond side portal.
        # Sloping side wall, visibly articulated with large panels and rooted pilasters.
        for y in [-13,-3,7,17]:
            prism('flank/sloping wall',[(s*42,.2),(s*44,.2),(s*39.5,11.1),(s*37.6,11.1)],y-4.9,y+4.9,m['alloy'],.12)
            prism('flank/deep field',[(s*43,.9),(s*43.22,.9),(s*39.64,9.7),(s*39.39,9.7)],y-3.6,y+3.6,m['dark'],.03)
            prism('flank/buttress',[(s*45,.05),(s*41.5,.05),(s*37.6,10.8),(s*39.7,10.8)],y-5.25,y-4.55,m['alloy'],.13)
        # Broad external ramp rises continuously, handrail follows the same slope.
        xa,xb=sorted([s*45,s*55]); yf,yt=-42,6;zt=11.2
        verts=[(xa,yf,.12),(xb,yf,.12),(xb,yt,zt),(xa,yt,zt),(xa,yf,-.25),(xb,yf,-.25),(xb,yt,zt-.9),(xa,yt,zt-.9)]
        mesh('ramp/driveable roof access',verts,[(0,1,2,3),(4,7,6,5),(0,4,5,1),(3,2,6,7),(0,3,7,4),(1,5,6,2)],m['floor'],.07)
        for x in [xa,xb]:
            beam('ramp/edge curb',(x,yf,.75),(x,yt,12.0),1.35,1.0,m['alloy'],.18)
            beam('ramp/detailed trim',(x,yf,1.26),(x,yt,12.51),.42,.25,m['trim'],.04)
            # Solid sloped retaining wings root each ramp in the base silhouette.
            v=[(xx,y,z) for xx in [x-1.1,x+1.1] for y,z in [(yf,0),(yt,0),(yt,12.0),(yf,.75)]]
            mesh('ramp/armored retaining wall',v,[(0,3,2,1),(4,5,6,7),(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7)],m['alloy'],.12)
        # Stepped exterior support feet anchor the long sloped ramp.
        for y in [-31,-17,-3]:
            z=.12+(y-yf)/(yt-yf)*(zt-.12)
            for side_x in [43.0,57.0]:
                profile=[(y-7,0),(y+6,0),(y+6,z+3.0),(y+1,z+3.0),(y-1,z+1.0),(y-7,max(.6,z-.6))]
                x=s*side_x
                verts=[(xx,yy,zz) for xx in [x-1.7,x+1.7] for yy,zz in profile];n=len(profile)
                mesh('ramp/interlocking armored shoulder',verts,[tuple(range(n-1,-1,-1)),tuple(range(n,n*2))]+[(j,(j+1)%n,(j+1)%n+n,j+n) for j in range(n)],m['alloy'],.24)
                inset=[(y-5,.55),(y+4,.55),(y+4,z+1.9),(y+1,z+1.9),(y-2,max(.8,z-.2))]
                outward=s*(side_x+1.72)
                verts=[(xx,yy,zz) for xx in [outward,outward+s*.08] for yy,zz in inset];n=len(inset)
                mesh('ramp/shoulder recessed armor field',verts,[tuple(range(n-1,-1,-1)),tuple(range(n,n*2))]+[(j,(j+1)%n,(j+1)%n+n,j+n) for j in range(n)],m['dark'],.045)
        for j in range(48):
            ya=yf+j+.03;yb=ya+.94
            za=.12+(ya-yf)/(yt-yf)*(zt-.12);zb=.12+(yb-yf)/(yt-yf)*(zt-.12)
            vertices=[(x,y,z+dz) for dz in [-.04,.065] for x,y,z in [(xa+.24,ya,za),(xb-.24,ya,za),(xb-.24,yb,zb),(xa+.24,yb,zb)]]
            mesh('ramp/segmented traction plate',vertices,[(0,3,2,1),(4,5,6,7),(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7)],m['floor'],.024)
        slab('ramp/open upper turning landing',[(s*35,6),(s*55,6),(s*55,20),(s*35,20)],10.3,11.30,m['alloy'],.12)
        for y in [7,19]:
            prism('ramp/landing support',[(s*47,0),(s*51,0),(s*50,10.3),(s*48,10.3)],y-.7,y+.7,m['alloy'],.12)
        box('ramp/landing outer curb',(s*54.7,13,11.8),(.6,14,1.2),m['alloy'],.1)
        box('ramp/landing rear curb',(s*45,19.7,11.8),(20,.6,1.2),m['alloy'],.1)
        # Interior galleries remain open; cover follows outside edge, clear from main vehicle path.
        for y in [-12,0,17]:
            prism('gallery/cover plinth',[(s*22,.2),(s*25,.2),(s*24.5,1.6),(s*22.5,1.6)],y-1.5,y+1.5,m['alloy'],.12)
        # A rear wall with broad connection to the through hall.
        box('rear/gallery wall',(s*26,25.05,5.2),(23,1.5,10.0),m['alloy'],.13)
        prism('rear/gallery angled wall closure',[(s*37.3,.2),(s*43.5,.2),(s*39.5,11.2),(s*37.3,11.2)],24.3,25.8,m['alloy'],.10)
        cx=s*28
        inner=[(cx-3.6,.6),(cx-3.6,3.8),(cx-2.8,4.7),(cx+2.8,4.7),(cx+3.6,3.8),(cx+3.6,.6)]
        outer=[(cx-4.5,.2),(cx-4.5,4.1),(cx-3.2,5.5),(cx+3.2,5.5),(cx+4.5,4.1),(cx+4.5,.2)]
        frame('gallery/rear bulkhead armor',22.85,inner,outer,1.0,m['alloy'])
        prism('gallery/rear bulkhead recessed field',inner,23.12,23.50,m['floor'],.075)
        box('gallery/rear bulkhead sill',(cx,22.85,.45),(9,1,.5),m['alloy'],.06)
        for side in [-1,1]:
            path=[(cx+side*2.9,23.04,1.05),(cx+side*2.9,23.04,3.25),(cx+side*1.9,23.04,4.2),(cx+side*.55,23.04,4.2)]
            for a,b in zip(path,path[1:]):beam('gallery/rear bulkhead stepped engraving',a,b,.065,.055,m['dark'],.012)
        box('gallery/rear bulkhead light well',(cx,22.27,5.04),(2.6,.18,.25),m['dark'],.03)
        box('gallery/rear bulkhead light',(cx,22.16,5.04),(2.2,.06,.09),m['white'],.015)
        # Two separated rear fins; the entire central 30x30 rooftop remains clear.
        # Roof edge cover blocks, absent in the ramp landing and center mount reserved zone.
        for y in [20]:
            prism('roof/low parapet',[(s*38.4,11.2),(s*40.2,11.2),(s*39.9,12.3),(s*38.8,12.3)],y-2.5,y+2.5,m['alloy'],.08)
        for x in [s*13,s*20]:
            box('roof/rear low cover',(x,23,11.75),(5,.8,1.1),m['alloy'],.1)
    # Octagonal removable mount, no gun is fabricated or misidentified here.
    for i in range(8):
        a=2*math.pi*i/8+math.pi/8;b=2*math.pi*(i+1)/8+math.pi/8
        po=[(r*math.cos(t),r*math.sin(t)) for r,t in [(8,a),(8,b),(10,b),(10,a)]]
        slab('mount/octagonal removable curb',po,11.22,11.85,m['alloy'],.09)
        po=[(r*math.cos(t),r*math.sin(t)) for r,t in [(7.95,a+.13),(7.95,b-.13),(8.10,b-.13),(8.10,a+.13)]]
        slab('mount/recessed team marker',po,11.45,11.58,m['team'],.025)
        wall=[(r*math.cos(t),r*math.sin(t)) for r,t in [(7.89,a),(7.89,b),(8.05,b),(8.05,a)]]
        slab('mount/deep socket inner wall',wall,10.39,11.8,m['dark'],.035)
    slab('mount/socket insert',[(7.9*math.cos(i*math.pi/4+math.pi/8),7.9*math.sin(i*math.pi/4+math.pi/8)) for i in range(8)],11.21,11.25,m['dark'],.03)
    # Layered socket rim, removable inset plates and narrow team illuminators.
    for i in range(8):
        a=2*math.pi*i/8+math.pi/8;b=2*math.pi*(i+1)/8+math.pi/8
        poly=[(r*math.cos(t),r*math.sin(t)) for r,t in [(8.18,a+.025),(8.18,b-.025),(9.5,b-.025),(9.5,a+.025)]]
        slab('mount/rim inset plate',poly,11.86,11.91,m['dark'],.035)
        mid=(a+b)/2
        beam('mount/inner light',(8.07*math.cos(mid-.15),8.07*math.sin(mid-.15),11.9),(8.07*math.cos(mid+.15),8.07*math.sin(mid+.15),11.9),.10,.10,m['team'],.015)
    # Roof joints belong to fitted structural plates; no raised decorative
    # linework crosses their seams or the cannon approach.
    for s in [-1,1]:
        for y in [-13,-3,7,17]:
            beam('gallery/recessed light housing',(s*41.27,y,2),(s*39.39,y,6.7),.30,.15,m['dark'],.035)
            beam('gallery/cool wall strip',(s*41.20,y,2.15),(s*39.32,y,6.55),.10,.13,m['white'],.02)
        for y in [-14,-3,8,19]:
            box('gallery/low wall fixture backing',(s*41.7,y,.85),(.25,1.6,.5),m['dark'],.035)
            box('gallery/low wall fixture lens',(s*41.5,y,.88),(.1,1.3,.16),m['white'],.018)
    try:
        import detail_kit,importlib;importlib.reload(detail_kit)
        def tunnel_detail_mesh(name,verts,faces,mat,bevel=.05):
            if 'Tunnel_' not in name:return None
            return mesh(name,[(x*1.3,y,z) for x,y,z in verts],faces,mat,bevel)
        detail_kit.add_details({'prefix':'detail/','box':box,'prism':prism,'mesh':tunnel_detail_mesh,'mats':m,'collection':COL,'portal_front_y':-27.3,'portal_rear_y':25.3})
    except ImportError: pass
    import sculpted_facade,importlib;importlib.reload(sculpted_facade)
    sculpted_facade.add_facade({'prefix':'facade/','box':box,'prism':prism,'mesh':mesh,'mats':m,'collection':COL})
    cutters=next(ob for ob in COL.objects if ob.name.startswith('facade/flanks/secondary deep grooves'))
    # Cut each closed segment separately. Overlapping disconnected operands in
    # a single Boolean can erase a concave field in Blender's exact solver.
    adjacency={v.index:set() for v in cutters.data.vertices}
    for e in cutters.data.edges:
        a,b=e.vertices;adjacency[a].add(b);adjacency[b].add(a)
    remaining=set(adjacency);components=[]
    while remaining:
        seed=remaining.pop();part={seed};todo=[seed]
        while todo:
            for vi in adjacency[todo.pop()]:
                if vi in remaining:remaining.remove(vi);part.add(vi);todo.append(vi)
        components.append(part)
    fields=[o for o in COL.objects if 'continuous recessed field' in o.name]
    for part in components:
        indices=sorted(part);remap={v:i for i,v in enumerate(indices)}
        verts=[tuple(cutters.data.vertices[i].co) for i in indices]
        faces=[tuple(remap[i] for i in p.vertices) for p in cutters.data.polygons if p.vertices[0] in part]
        data=bpy.data.meshes.new('Temporary channel cutter');data.from_pydata(verts,[],faces);data.update()
        temp=bpy.data.objects.new('Temporary channel cutter',data);COL.objects.link(temp)
        for ob in fields:
            if max(v.co.x for v in ob.data.vertices)<min(v[0] for v in verts) or min(v.co.x for v in ob.data.vertices)>max(v[0] for v in verts):continue
            bpy.context.view_layer.objects.active=ob
            mod=ob.modifiers.new('Cut recessed architectural channel','BOOLEAN');mod.operation='DIFFERENCE';mod.solver='EXACT';mod.object=temp;mod.use_self=True
            while ob.modifiers.find(mod.name)>0:bpy.ops.object.modifier_move_up(modifier=mod.name)
            bpy.ops.object.modifier_apply(modifier=mod.name)
            if len(ob.data.polygons)==0:raise RuntimeError('Architectural channel cut removed an entire field')
        bpy.data.objects.remove(temp,do_unlink=True);bpy.data.meshes.remove(data)
    bpy.data.objects.remove(cutters,do_unlink=True)
    import stock_interior;importlib.reload(stock_interior)
    stock_interior.add_stock_panels({'collection':COL,'mats':m,'include_front':False,'tunnel_inner_x':13.7})
    try:
        import sculpted_fins,importlib;importlib.reload(sculpted_fins);sculpted_fins.add_fins({'prefix':'fin/','box':box,'prism':prism,'mesh':mesh,'mats':m,'collection':COL})
    except ImportError: pass
    for s in [-1,1]:
        prism('fin/offset shoulder carapace',[(s*30.2,11.35),(s*35.3,11.35),(s*32.4,16.2),(s*28.8,20.1),(s*26.6,21.0),(s*25.6,19.5),(s*29.4,16.4)],14.1,16.4,m['alloy'],.20)
        prism('fin/seated shoulder return',[(s*29.8,11.1),(s*35.5,11.1),(s*34.8,13.1),(s*31.0,12.8)],13.9,16.5,m['alloy'],.14)
    # Stepped returns make the crown read as assembled armor rather than a fascia strip.
    for s in [-1,1]:
        for index,(x0,x1) in enumerate([(13.5,23.8),(22.3,33.0),(31.5,40)]):
            slab('roof/interlocking crown armor',[(s*x0,-25.0),(s*(x0+.6),-27.6),(s*(x1-.8),-27.6),(s*x1,-24.9),(s*x1,-22.3),(s*x0,-22.3)],10.65,11.58 if index==1 else 11.52,m['alloy'],.14)
        for y in [-16,-6,4,14]:
            beam('tunnel/rib recessed light well',(s*12.7,y-.68,3.7),(s*11.0,y-.68,6.15),.39,.19,m['black'],.035)
            beam('tunnel/rib illuminated face',(s*12.67,y-.80,3.9),(s*11.14,y-.80,6.05),.12,.065,m['white'],.02)
            box('tunnel/low fixture well',(s*12.25,y-.7,.74),(.27,1.8,.42),m['black'],.04)
            box('tunnel/low fixture lens',(s*12.10,y-.7,.76),(.08,1.32,.18),m['white'],.02)
        for side in [-1,1]:
            edge=s*33+side*4
            prism('gallery/entry lining pier',[(edge,.2),(edge+side*.9,.2),(edge+side*.9,5.8),(edge-side*1.2,5.2),(edge,2.4)],-21,-17,m['dark'],.09)
            box('gallery/entry light housing',(edge+side*.32,-21.14,1.35),(.28,.28,1.9),m['black'],.04)
            box('gallery/entry light lens',(edge+side*.32,-21.30,1.35),(.11,.04,1.45),m['white'],.02)
    # Ceiling cassettes stay well above the conservative vehicle envelope.
    for y in [-15,-5,5,15]:
        for x in [-6.1,0,6.1]:
            slab('tunnel/ceiling cassette',[(x-2.9,y-4.55),(x+2.9,y-4.55),(x+2.9,y+3.6),(x+2.0,y+4.45),(x-2.9,y+4.45)],9.06,9.30,m['dark'],.06)
        box('tunnel/ceiling recessed fixture',(0,y-2,9.02),(4.1,.46,.12),m['black'],.04)
        box('tunnel/ceiling luminous lens',(0,y-2,8.95),(3.4,.19,.04),m['white'],.015)
    frame('portal/rear inner armored surround',22.48,
          [(-4.5,.2),(-4.5,2.7),(-4.0,6.4),(-2.9,7.5),(2.9,7.5),(4.0,6.4),(4.5,2.7),(4.5,.2)],
          [(-5.25,.2),(-5.25,2.95),(-4.65,6.9),(-3.6,8.2),(3.6,8.2),(4.65,6.9),(5.25,2.95),(5.25,.2)],.32,m['dark'])
    return COL

def clone_base(source,name,offset,mirror,mats):
    bpy.context.view_layer.update()
    dest=collection(name)
    for ob in source.objects:
        new=ob.copy();new.data=ob.data;dest.objects.link(new)
        # Object transform reflection maps both procedural geometry and transform-based details.
        from mathutils import Matrix
        new.matrix_world=Matrix.Translation(Vector(offset)) @ Matrix.Diagonal((mirror,1,1,1)) @ ob.matrix_world
        new.name=name.split(' ')[0]+'/'+ob.name
        new['mirror_source_object']=ob.name
        for slot in new.material_slots:
            if slot.material and slot.material.name.startswith('TEAM'):
                slot.link='OBJECT';slot.material=mats['team']
    return dest

def elevate_architecture(objects):
    """Give the occupied facade the monumentality of the concept; preserve floor datum."""
    from mathutils import Matrix
    bpy.context.view_layer.update()
    for ob in objects:
        if ob.type!='MESH':continue
        if ob.get('stock_source_file'):
            e=Matrix.Diagonal((1,1,1.45,1));e.translation.z=-.09
            ob.matrix_world=e@ob.matrix_world
            continue
        ob.data=ob.data.copy()
        for vertex in ob.data.vertices:
            p=ob.matrix_world @ vertex.co
            if .2<p.z<=11.2001:p.z=.2+(p.z-.2)*1.45
            elif p.z>11.2001:p.z=16.15+(p.z-11.2)*.9
            vertex.co=p
        ob.matrix_world=Matrix.Identity(4)
        ob.data.update()
    bpy.context.view_layer.update()

def lighting():
    scene=bpy.context.scene
    scene.render.engine='CYCLES';scene.cycles.samples=128;scene.cycles.use_denoising=True
    try:
        pref=bpy.context.preferences.addons['cycles'].preferences;pref.compute_device_type='OPTIX';pref.get_devices()
        for d in pref.devices:d.use=d.type!='CPU'
        scene.cycles.device='GPU'
    except Exception:pass
    scene.world=bpy.data.worlds.new('Alpine daylight');scene.world.use_nodes=True
    n=scene.world.node_tree.nodes;n.get('Background').inputs['Color'].default_value=(.55,.61,.70,1);n.get('Background').inputs['Strength'].default_value=.45
    hdri=HERE/'textures/daylight-presentation.exr'
    if hdri.exists():
        env=n.new('ShaderNodeTexEnvironment');env.image=bpy.data.images.load(str(hdri),check_existing=True)
        mapping=n.new('ShaderNodeMapping');mapping.inputs['Rotation'].default_value[2]=2.2
        coord=n.new('ShaderNodeTexCoord');scene.world.node_tree.links.new(coord.outputs['Generated'],mapping.inputs['Vector'])
        scene.world.node_tree.links.new(mapping.outputs['Vector'],env.inputs['Vector'])
        scene.world.node_tree.links.new(env.outputs['Color'],n.get('Background').inputs['Color']);n.get('Background').inputs['Strength'].default_value=.23
    light=bpy.data.lights.new('Late morning key','SUN');light.energy=4.8;light.angle=math.radians(2);light.color=(1,.83,.66)
    ob=bpy.data.objects.new(light.name,light);bpy.context.scene.collection.objects.link(ob);ob.location=(-80,-110,150);ob.rotation_euler=(-ob.location).to_track_quat('-Z','Y').to_euler()
    area=bpy.data.lights.new('Architectural broad reflection','AREA');area.energy=25000;area.shape='DISK';area.size=65;area.color=(1,.94,.86)
    aob=bpy.data.objects.new(area.name,area);bpy.context.scene.collection.objects.link(aob);aob.location=(-65,-55,95);aob.rotation_euler=(Vector((0,0,5))-aob.location).to_track_quat('-Z','Y').to_euler()
    scene.view_settings.view_transform='AgX';scene.view_settings.look='AgX - Medium High Contrast';scene.view_settings.exposure=.45
    scene.render.resolution_x=1672;scene.render.resolution_y=940;scene.render.resolution_percentage=100
    scene.render.image_settings.file_format='PNG'
    for y in [-14,-4,6,16]:
        li=bpy.data.lights.new('Tunnel practical bounce','AREA');li.energy=65;li.shape='RECTANGLE';li.size=1.5;li.size_y=2;li.color=(.58,.78,1)
        ob=bpy.data.objects.new(li.name,li);bpy.context.scene.collection.objects.link(ob);ob.location=(0,y*ART_SCALE,.2+(12.5-.2)*ART_SCALE)
    for y in [-16,-6,4,14]:
        for s in [-1,1]:
            li=bpy.data.lights.new('Tunnel fixture pool','SPOT');li.energy=210;li.color=(.48,.75,1);li.spot_size=math.radians(68);li.spot_blend=.45;li.shadow_soft_size=.35
            ob=bpy.data.objects.new(li.name,li);bpy.context.scene.collection.objects.link(ob);ob.location=(s*7.7,y*ART_SCALE,3.4)
            ob.rotation_euler=(Vector((s*4.7,y*ART_SCALE,.23))-ob.location).to_track_quat('-Z','Y').to_euler()
    for s in [-1,1]:
        for y in [-13,-3,7,17]:
            li=bpy.data.lights.new('Gallery wall fixture pool','SPOT');li.energy=30;li.color=(.58,.78,1);li.spot_size=math.radians(66);li.spot_blend=.5;li.shadow_soft_size=.25
            ob=bpy.data.objects.new(li.name,li);bpy.context.scene.collection.objects.link(ob);ob.location=(s*26.0,y*ART_SCALE,3.2)
            ob.rotation_euler=(Vector((s*21.5,y*ART_SCALE,.20))-ob.location).to_track_quat('-Z','Y').to_euler()
        for y in [-14,-3,8,19]:
            li=bpy.data.lights.new('Gallery low fixture pool','SPOT');li.energy=145;li.color=(.58,.78,1);li.spot_size=math.radians(70);li.spot_blend=.45;li.shadow_soft_size=.20
            ob=bpy.data.objects.new(li.name,li);bpy.context.scene.collection.objects.link(ob);ob.location=(s*26.8,y*ART_SCALE,1.1)
            ob.rotation_euler=(Vector((s*23.2,y*ART_SCALE,.20))-ob.location).to_track_quat('-Z','Y').to_euler()
        for x in [29.1,36.9]:
            li=bpy.data.lights.new('Side doorway practical pool','AREA');li.energy=85;li.color=(.55,.8,1);li.shape='RECTANGLE';li.size=.2;li.size_y=1.5
            ob=bpy.data.objects.new(li.name,li);bpy.context.scene.collection.objects.link(ob);ob.location=(s*x*ART_SCALE,-20.6*ART_SCALE,1.65)
            ob.rotation_euler=(Vector((s*33*ART_SCALE,-20*ART_SCALE,.25))-ob.location).to_track_quat('-Z','Y').to_euler()
    for y in [-16,-6,4,14]:
        li=bpy.data.lights.new('Tunnel rib grazing bounce','AREA');li.energy=105;li.color=(.59,.78,1);li.shape='RECTANGLE';li.size=2;li.size_y=1
        ob=bpy.data.objects.new(li.name,li);bpy.context.scene.collection.objects.link(ob);ob.location=(1.2,y*ART_SCALE-1.7,5.8)
        ob.rotation_euler=(Vector((7.2,y*ART_SCALE,4.6))-ob.location).to_track_quat('-Z','Y').to_euler()
    li=bpy.data.lights.new('Rear aperture armor graze','AREA');li.energy=200;li.color=(.65,.8,1);li.shape='RECTANGLE';li.size=3;li.size_y=1
    ob=bpy.data.objects.new(li.name,li);bpy.context.scene.collection.objects.link(ob);ob.location=(0,11.0,5.5)
    ob.rotation_euler=(Vector((0,14.6,5.0))-ob.location).to_track_quat('-Z','Y').to_euler()

def camera(name,location,target,lens=48):
    ca=bpy.data.cameras.new(name);ob=bpy.data.objects.new(name,ca);bpy.context.scene.collection.objects.link(ob)
    ob.location=location;ob.rotation_euler=(Vector(target)-ob.location).to_track_quat('-Z','Y').to_euler();ca.lens=lens;ca.clip_end=5000
    return ob

def main():
    global COL
    reset();bpy.context.scene.unit_settings.system='METRIC';bpy.context.scene.unit_settings.scale_length=1
    import finishing_materials,importlib;importlib.reload(finishing_materials)
    m=make_mats();finish_material_report=finishing_materials.apply_material_finish(m)
    red=build_master(m);elevate_architecture(list(red.objects))
    blue_m={**m,'team':material('TEAM • blue recessed energy',(.015,.16,.95),.32,.36,None,2.5)}
    green_m={**m,'team':material('TEAM • green recessed energy',(.035,.65,.16),.32,.36,None,2.5)}
    blue=clone_base(red,'02_BLUE • reflected master',(135,0,0),-1,blue_m)
    green=clone_base(red,'03_GREEN • citadel',(0,150,0),1,green_m)
    # Expanded rear gallery establishes a third-base silhouette using the same kit.
    COL=green
    for s in [-1,1]:
        prism('citadel/rear observation pier',[(s*38,0),(s*44,0),(s*41,16),(s*37,16)],175,190,m['alloy'],.2)
        prism('citadel/upper fin inset',[(s*38.1,11.2),(s*40.7,11.2),(s*40,14.8),(s*38,14.8)],174.8,175,m['dark'],.04)
    slab('citadel/rear gallery',[(-38,174),(-38,188),(38,188),(38,174)],10.2,11.2,m['alloy'],.12)
    box('citadel/rear parapet',(0,188,12),(75,1,1.6),m['alloy'],.12)
    import citadel_details,importlib;importlib.reload(citadel_details)
    citadel_details.add_details({'collection':COL,'mats':green_m,'mesh':mesh,'prism':prism,'box':box})
    elevate_architecture([ob for ob in green.objects if ob.name.startswith('citadel/')])
    from mathutils import Matrix
    size_matrix=Matrix.Diagonal((ART_SCALE,ART_SCALE,ART_SCALE,1));size_matrix.translation.z=.2*(1-ART_SCALE)
    for c,center in [(red,(0,0,0)),(blue,(135,0,0)),(green,(0,150,0))]:
        t=Matrix.Translation(center);inv=t.inverted()
        for ob in c.objects:ob.matrix_world=t@size_matrix@inv@ob.matrix_world
    bpy.context.view_layer.update()
    finish_uv_report=finishing_materials.finish_scene_geometry(m,[o for c in [red,blue,green] for o in c.objects])
    (OUT/'material-finish.json').write_text(json.dumps({'materials':finish_material_report,'geometry':finish_uv_report},indent=2))
    # Reserve exact placement metadata, keeping the presentation copies off the live map.
    red['target_world_center_m']=(-590,-80,107.5998);blue['target_world_center_m']=(600,-80,111.5954);green['target_world_center_m']=(0,690,129.2274)
    for c in [red,blue,green]:c['authoring_only']=True
    COL=collection('90_PRESENTATION • environment')
    try:
        import staging,importlib;importlib.reload(staging);staging.stage_scene({'collection':COL,'mesh':mesh,'box':box,'prism':prism,'mats':m},include_vehicle=False)
        staging.import_warthog(position=(0,-28,-.13))
        for ob in list(bpy.data.objects):
            if ob.type in {'LIGHT','CAMERA'} and ob.get('stage_owner'):
                bpy.data.objects.remove(ob,do_unlink=True)
    except ImportError:
        box('Presentation ground',(0,0,-1.2),(1200,1200,1),material('Ground',(.105,.14,.065),0,.9),0)
    lighting()
    for s in [-1,1]:
        for y in [-10,13]:
            li=bpy.data.lights.new('Gallery practical bounce','AREA');li.energy=110;li.shape='RECTANGLE';li.size=4;li.size_y=5;li.color=(.6,.78,1)
            ob=bpy.data.objects.new(li.name,li);bpy.context.scene.collection.objects.link(ob);ob.location=(s*30*ART_SCALE,y*ART_SCALE,8.9)
        li=bpy.data.lights.new('Gallery warm wall wash','AREA');li.energy=350;li.shape='RECTANGLE';li.size=2.5;li.size_y=2.0;li.color=(1,.74,.46)
        ob=bpy.data.objects.new(li.name,li);bpy.context.scene.collection.objects.link(ob);ob.location=(s*28*ART_SCALE,18*ART_SCALE,4.8)
        ob.rotation_euler=(Vector((s*28*ART_SCALE,24*ART_SCALE,3.4))-ob.location).to_track_quat('-Z','Y').to_euler()
    hero=camera('Camera • RED hero',(18*ART_SCALE,-170*ART_SCALE,35*ART_SCALE),(0,0,9*ART_SCALE),45)
    camera('Camera • portal interior',(3.25,-15.6,2.86),(-1.3,12.35,3.38),22)
    camera('Camera • BLUE hero',(146.7,-110.5,22.75),(135,0,5.85),45)
    camera('Camera • GREEN citadel',(67.6,59,60.45),(0,153.9,7.15),46)
    cam=camera('Camera • roof and paths',(0,-.01,113.75),(0,0,0),48);cam.data.type='ORTHO';cam.data.ortho_scale=81.25
    scene=bpy.context.scene;scene.camera=hero
    blue.hide_render=True;green.hide_render=True
    scene['design_stage']='Blender art v1; no game integration';scene['main_tunnel_clear_m']='Main hall16.9m floorwidth; entry soffit7.16m clear; rear opening5.85m wide /6.88m clear; covered length32.5m'
    scene['roof_deck_z_m']=.2+(16.15-.2)*ART_SCALE
    scene['base_authoring_scale']=ART_SCALE
    scene['cannon_reserved_envelope_m']='19.5 x 19.5 rooftop region; removable13m socket, exact emitter unconfirmed'
    for image in bpy.data.images:
        if image.source=='FILE':
            try:image.pack()
            except Exception:pass
    scene.render.filepath=str(OUT/'renders/red-hero-v16.png')
    scene['art_revision']='v16: authored recessed gallery bulkheads and continuous vehicle approaches'
    bpy.ops.object.select_all(action='DESELECT')
    for screen in bpy.data.screens:
        for area in screen.areas:
            if area.type=='VIEW_3D':
                area.spaces.active.region_3d.view_perspective='CAMERA'
                area.spaces.active.shading.type='MATERIAL'
    bpy.data.orphans_purge(do_local_ids=True,do_linked_ids=False,do_recursive=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(HERE/'forerunner_bases.blend'))
    print(json.dumps({'saved':str(HERE/'forerunner_bases.blend'),'objects':len(bpy.data.objects),'meshes':len(bpy.data.meshes),'red_objects':len(red.objects),'render':scene.render.filepath}))

if __name__=='__main__':main()
