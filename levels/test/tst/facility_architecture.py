"""Enclosed under-balcony facility, authored in metres.

The two arena-facing portals are its only exterior connections. Two symmetric
branches diverge around roof-connected structural wedges into blind end bays;
concealed lateral concourses join them. No air opening reaches the rear canyon.
"""
import math
from architecture_surfaces import blender_material

FLOOR_Z = .30
INTERIOR_CEILING_Z = 4.01
HALF_X, FRONT_Y, BACK_Y = 53.5, 24.6, 55.5
FRONT_BRANCH = [(7.6,36.2),(16,34),(30,28.5),(43.8,28.5)]
BRANCH_PROFILE = [(-2.25,.30),(2.25,.30),(2.6,.65),(2.6,3.46),
                  (2.05,4.01),(-2.05,4.01),(-2.6,3.46),(-2.6,.65)]
RIB_INNER = [(-2.15,.30),(2.15,.30),(2.40,.65),(2.40,3.30),
             (1.92,3.78),(-1.92,3.78),(-2.40,3.30),(-2.40,.65)]


def branch_path(side=1, rear=False):
    return [(side*x,80-y if rear else y) for x,y in FRONT_BRANCH]


def validation_contract():
    routes={}
    for rear in (False,True):
        branch=branch_path(-1,rear)
        approach=[(-48,24.9),(-48,36),(-40,36)]
        if rear: approach += [(-40,49),(-40,51.5)]
        else: approach += [(-40,28.5)]
        west=approach+list(reversed(branch[:-1]))+[(0,40)]
        routes['rear' if rear else 'front']=west+[(-x,y) for x,y in reversed(west[:-1])]
    sections=[]; ceilings=[]; caps=[]
    for side in (-1,1):
        for rear in (False,True):
            path=branch_path(side,rear)
            for index,(a,b) in enumerate(zip(path,path[1:])):
                dx,dy=b[0]-a[0],b[1]-a[1]; length=math.hypot(dx,dy)
                for fraction in (.25,.65):
                    p=[a[0]+dx*fraction,a[1]+dy*fraction]
                    ceilings.append(p)
                    sections.append({'name':f'branch_{side}_{rear}_{index}_{fraction}',
                        'center':p,'normal':[-dy/length,dx/length],'required_width_m':4.2})
            caps.append({'name':f'blind_end_{side}_{rear}',
                'origin':[side*42.8,51.5 if rear else 28.5,2.0],
                'direction':[side,0,0],'max_distance_m':1.1})
    ceilings += [[x,y] for x in (-5,0,5) for y in (35,40,45)]
    turns=[]
    for side in (-1,1):
        for ya in (35,48):
            turns.append({'name':f'concourse_{side}_{ya}',
                'x_span_m':sorted([side*39,side*41]),'y_span_m':[ya,ya+2]})
    return {'routes':routes,'branch_sections':sections,'ceiling_points':ceilings,
            'closed_caps':caps,'turning_bays':turns,
            'bounds':{'half_x':HALF_X,'front_y':FRONT_Y,'back_y':BACK_Y},
            'ceiling_m':INTERIOR_CEILING_Z}


def build(wall, mesh_object, box, prism, bevel_rectangle, boolean, light, red, blue, amber_light):
    import bpy
    import bmesh
    from mathutils import Vector
    metre=3.048
    roles=('armor','structure','recess','floor','fitted_pale','fitted_inset','fitted_charcoal','edge')
    # Facility-only finishes preserve the established exterior palette while
    # sharing authored albedo, normal and roughness data with the next export.
    def finish_role(name):
        return 'facility_'+name if name in ('armor','structure','recess','floor') else name
    mats={name:blender_material(finish_role(name),True) for name in roles}
    solid={name:blender_material(finish_role(name)) for name in ('armor','structure','floor')}

    def close_mesh(name,vertices,faces,mat):
        obj=mesh_object('facility_'+name,vertices,faces,[mat])
        bm=bmesh.new(); bm.from_mesh(obj.data)
        bmesh.ops.recalc_face_normals(bm,faces=list(bm.faces))
        bm.to_mesh(obj.data); bm.free()
        return obj

    def profile(name,outline,start,end,mat,axis='y'):
        def point(a,d,z): return (a,d,z) if axis=='y' else (d,a,z)
        n=len(outline)
        vertices=[point(a,d,z) for d in (start,end) for a,z in outline]
        faces=[tuple(range(n)),tuple(reversed(range(n,2*n)))]
        faces += [(i,i+n,(i+1)%n+n,(i+1)%n) for i in range(n)]
        return close_mesh(name,vertices,faces,mat)

    def detail(obj,bevel=.025):
        obj['mjolnir_render_detail']=True
        obj['mjolnir_pcg_policy']='NONE'
        obj['tst_facility']=True
        obj['precision_bevel_m']=bevel
        obj['authoring_note']='Editable fitted finish; sealed underlying BSP owns collision.'
        return obj

    def block(name,lo,hi,role='structure',bevel=.025):
        return detail(box('facility_'+name,lo,hi,mats[role]),bevel)

    def plate(name,poly,d0,d1,role='armor',axis='y',bevel=.025):
        return detail(profile(name,poly,d0,d1,mats[role],axis),bevel)

    def lamp(name,points,power=0,direction=(0,0,-1),size=(2.4,.3),color=(.96,.96,1),spread=180):
        # The exported CE shader is single-sided. Cycles' default two-sided
        # shading must not conceal a lens whose front faces the solid roof.
        normal=(Vector(points[1])-Vector(points[0])).cross(Vector(points[2])-Vector(points[0]))
        facing=normal.dot(Vector(direction))
        if abs(facing)<1e-8:
            raise ValueError('Facility light direction is tangent to its face: '+name)
        winding=(0,1,2,3) if facing>0 else (3,2,1,0)
        obj=mesh_object('facility_'+name,points,[winding],[light])
        obj['tst_facility_fixture']=True
        obj['mjolnir_pcg_policy']='NONE'
        obj['face_direction']=direction
        obj['preview_emission_strength']=2.0
        if power:
            obj['authored_light_lens']=True
            obj['preview_light_power']=power*.23
            obj['preview_light_direction']=direction
            obj['preview_light_size']=size
            obj['preview_light_color']=color
            obj['preview_light_spread_degrees']=spread
        return obj

    def floor_strip_lamp(name,points,foyer=False):
        # The existing upward-facing strip supplies the physical aperture.
        # Long-axis metadata keeps angled branches aligned with their AREA
        # lights; watts are authored per metre, before CE-unit conversion.
        vectors=[Vector(point) for point in points]
        edges=[b-a for a,b in zip(vectors,vectors[1:]+vectors[:1])]
        long_edge=max(edges,key=lambda edge:edge.length)
        length,width=long_edge.length,min(edge.length for edge in edges)
        color=(1,.88,.74) if foyer else (.65,.88,1)
        obj=lamp(name,points,length*6/.23,(0,0,1),(length,width),color,150)
        obj['preview_light_tangent']=tuple(long_edge.normalized())
        obj['preview_floor_linear_watts']=6.0
        obj['preview_floor_run']='foyer' if foyer else 'branch'
        # These previously unpowered lenses used the stock preview's1.6
        # radiance. Adding a physical wash must not brighten the visible core.
        obj['preview_emission_strength']=1.6
        return obj

    def ring(name,outer,inner,d0,d1,axis='y',role='armor'):
        for i in range(1,len(outer)):
            j=(i+1)%len(outer)
            poly=[outer[i],outer[j],inner[j],inner[i]]
            cx=sum(p[0] for p in poly)/4; cz=sum(p[1] for p in poly)/4
            poly=[(cx+(x-cx)*.985,cz+(z-cz)*.985) for x,z in poly]
            plate(name+'_'+str(i),poly,d0,d1,role,axis,.025)

    def basis(a,b):
        dx,dy=b[0]-a[0],b[1]-a[1]; length=math.hypot(dx,dy)
        return (dx/length,dy/length),(-dy/length,dx/length),length

    def local_point(a,t,n,s,w,z):
        return (a[0]+t[0]*s+n[0]*w,a[1]+t[1]*s+n[1]*w,z)

    def local_profile(name,outline,s0,s1,a,t,n,mat):
        count=len(outline)
        vertices=[local_point(a,t,n,s,w,z) for s in (s0,s1) for w,z in outline]
        faces=[tuple(range(count)),tuple(reversed(range(count,2*count)))]
        faces += [(i,i+count,(i+1)%count+count,(i+1)%count) for i in range(count)]
        return close_mesh(name,vertices,faces,mat)

    def local_wall_plate(name,outline,w0,w1,a,t,n,role,bevel=.02):
        count=len(outline)
        vertices=[local_point(a,t,n,s,w,z) for w in (w0,w1) for s,z in outline]
        faces=[tuple(range(count)),tuple(reversed(range(count,2*count)))]
        faces += [(i,i+count,(i+1)%count+count,(i+1)%count) for i in range(count)]
        return detail(close_mesh(name,vertices,faces,mats[role]),bevel)

    def floor_ribbon(name,path,widths):
        # Shared miter vertices give adjacent strips one exact butt joint,
        # without overlapping coplanar faces or gaps around the battered toe.
        normals=[]
        for a,b in zip(path,path[1:]):
            dx,dy=b[0]-a[0],b[1]-a[1]; length=math.hypot(dx,dy)
            normals.append((-dy/length,dx/length))
        offsets=[]
        for i,width in enumerate(widths):
            if i==0: nx,ny=normals[0]
            elif i==len(path)-1: nx,ny=normals[-1]
            else:
                ax,ay=normals[i-1]; bx,by=normals[i]
                scale=1/(1+ax*bx+ay*by)
                nx,ny=(ax+bx)*scale,(ay+by)*scale
            offsets.append((nx*width*.5,ny*width*.5))
        for i,(a,b) in enumerate(zip(path,path[1:])):
            ax,ay=offsets[i]; bx,by=offsets[i+1]
            points=[(a[0]+ax,a[1]+ay,.312),(b[0]+bx,b[1]+by,.312),
                    (b[0]-bx,b[1]-by,.312),(a[0]-ax,a[1]-ay,.312)]
            lamp(name,points,direction=(0,0,1))

    def coffer_border(name,x0,y0,x1,y1):
        # Four closed bars terminate at shared corners; the 115 mm deep
        # assembly is fixed to the ceiling, not hovering below its skin.
        depth=.11
        block(name+'_front',(x0,y0,3.89),(x1,y0+depth,4.005),'structure',.012)
        block(name+'_rear',(x0,y1-depth,3.89),(x1,y1,4.005),'structure',.012)
        block(name+'_left',(x0,y0+depth,3.89),(x0+depth,y1-depth,4.005),'structure',.012)
        block(name+'_right',(x1-depth,y0+depth,3.89),(x1,y1-depth,4.005),'structure',.012)

    def ceiling_washer(name,area_center,target,power_w,size,spread):
        """A roof-attached lens matching the accepted Blender light study.

        The stock CE atlas supplies the exported luminous face. Watts, area
        size and spread remain explicit Blender photometry; they are not a
        claim that the CE shader/bake will reproduce this calibrated wash.
        """
        center=Vector(area_center)
        direction=(Vector(target)-center).normalized()
        rotation=direction.to_track_quat('-Z','Y')
        u=rotation @ Vector((1,0,0))
        v=rotation @ Vector((0,1,0))
        # render_preview moves its AREA source 25 mm in front of the lens.
        # Offset the authored face back so the resulting source is exactly
        # at the position used by the accepted D photometry study.
        lens_center=center-direction*.025
        def corners(origin,width,height):
            return [origin+u*x*width*.5+v*y*height*.5
                    for x,y in ((-1,-1),(1,-1),(1,1),(-1,1))]
        base=corners(lens_center-direction*.012,size[0]+.12,size[1]+.08)
        if min(point.z for point in base)<=3.55:
            raise ValueError('Ceiling washer housing enters the protected height: '+name)
        # The rear of this sloping cassette continues vertically into the
        # solid ceiling. Its lower face stays behind the luminous aperture,
        # and no freestanding support occupies a walking route.
        vertices=[tuple(point) for point in base]
        vertices += [(point.x,point.y,4.015) for point in base]
        faces=[(3,2,1,0),(4,5,6,7),(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7)]
        detail(close_mesh(name+'_housing',vertices,faces,mats['structure']),.012)
        obj=lamp(name+'_lens',[tuple(point) for point in corners(lens_center,*size)],
                 power_w/.23,tuple(direction),size,(1,.85,.70),spread)
        obj['preview_light_reference_center_m']=tuple(center)
        obj['preview_light_reference_target_m']=tuple(target)
        obj['photometry_note']='Blender AREA calibration only; stock CE atlas face exports, game light bake remains unvalidated.'

    # Extend only the sealed solid envelope. build_geometry adds the matching
    # contained positive-air volume behind the original terrain boundary.
    boolean(wall,box('facility_envelope',(-HALF_X,FRONT_Y,-.6),(HALF_X,BACK_Y,6.35),solid['armor']),'UNION')
    boolean(wall,box('facility_foyer_air',(-8,33,FLOOR_Z),(8,47,INTERIOR_CEILING_Z),solid['structure']))
    for side in (-1,1):
        xa,xb=sorted((side*37.4,side*52.5))
        boolean(wall,box('facility_concourse_air',(xa,26,FLOOR_Z),(xb,54.5,INTERIOR_CEILING_Z),solid['structure']))
        for rear in (False,True):
            for a,b in zip(branch_path(side,rear),branch_path(side,rear)[1:]):
                t,n,length=basis(a,b)
                # Overlapping closed sections resolve the angled joins with
                # real volume rather than clipped planes or false doorways.
                boolean(wall,local_profile('branch_air',BRANCH_PROFILE,-.22,length+.22,a,t,n,solid['structure']))
        cx=side*48
        opening=[(cx-3.15,.3),(cx+3.15,.3),(cx+3.9,1.05),(cx+3.9,3.85),
                 (cx+2.95,4.85),(cx-2.95,4.85),(cx-3.9,3.85),(cx-3.9,1.05)]
        opening=[(cx+(x-cx)*4.4/3.9,.3+(z-.3)*4.2/4.55) for x,z in opening]
        boolean(wall,profile('vestibule_air',opening,23.8,37.8,solid['structure']))
        apron=profile('entry_apron',[(22.1,-.35),(27.9,-.35),(27.9,.30),
                      (24.6,.30),(22.1,-.10)],cx-4.45,cx+4.45,solid['floor'],'x')
        boolean(wall,apron,'UNION')
        # Solid caps terminate the visual axis. The broad cross-concourse
        # turns sideways immediately before them and remains fully indoors.
        for ya,yb in ((25.8,31.2),(48.8,54.2)):
            xa,xb=sorted((side*43.8,side*44.6))
            boolean(wall,box('facility_blind_end_cap',(xa,ya,.30),(xb,yb,4.2),solid['structure']),'UNION')
    boolean(wall,box('facility_floor',(-53,25,-.45),(53,55,.30),solid['floor']),'UNION')

    # Arena portals: three nested chamfered frames, structural returns and
    # team accents. Their clear opening is shared with the actual BSP void.
    for side,team in ((-1,red),(1,blue)):
        cx=side*48
        def arch(w,top,cut,bottom=.3):
            return [(cx-w+cut,bottom),(cx+w-cut,bottom),(cx+w,bottom+cut),
                    (cx+w,top-cut),(cx+w-cut,top),(cx-w+cut,top),
                    (cx-w,top-cut),(cx-w,bottom+cut)]
        ring('portal_outer_frame',arch(4.50,5.65,1.05),arch(4.13,5.25,.95),24.18,25.1,role='structure')
        ring('portal_silver_reveal',arch(4.13,5.25,.95),arch(3.97,5.03,.93),24.05,24.55,role='fitted_pale')
        ring('portal_inner_frame',arch(3.97,5.03,.93),arch(3.9,4.85,.95),24.30,25.35,role='armor')
        for edge in (-1,1):
            x=cx+edge*4.22
            p=[(x-.08,24.0,.8),(x+.08,24.0,.8),
               (x+.08+edge*.11,24.0,2.65),(x-.08+edge*.11,24.0,2.65)]
            obj=mesh_object('facility_entry_team_chevron',p,[(0,1,2,3)],[team])
            obj['team_color_band']=True
            lamp('portal_jamb_lens',[(cx+edge*3.97,24.005,2.75),(cx+edge*4.07,24.005,2.75),
                  (cx+edge*4.07,24.005,3.77),(cx+edge*3.97,24.005,3.77)],70,
                  direction=(0,-1,0),size=(.12,1.02))
        lamp('portal_lintel_lens',[(cx-2.45,24.0,5.08),(cx+2.45,24.0,5.08),
             (cx+2.45,24.0,5.19),(cx-2.45,24.0,5.19)],230,(0,-.7,-.7),(4.9,.12))
        # A short rhythm of vaults makes the 90-degree interior turn visible.
        for y in (27.1,30.2,33.3):
            ring('vestibule_rib',arch(3.90,4.85,.95),arch(3.60,4.55,.90),y,y+.26,role='fitted_inset')
            lamp('vestibule_ceiling_lens',[(cx-1.8,y+.02,4.50),(cx+1.8,y+.02,4.50),
                 (cx+1.8,y+.19,4.50),(cx-1.8,y+.19,4.50)],700*.70,size=(3.6,.20),
                 color=(1,.88,.73),spread=180)


    # The visible branch rhythm is built in each passage's own coordinate
    # frame. Every rib is a real chamfered arch with a 4.30 m floor opening.
    for side in (-1,1):
        for rear in (False,True):
            path=branch_path(side,rear)
            for segment,(a,b) in enumerate(zip(path,path[1:])):
                t,n,length=basis(a,b)
                stations=([2.0,6.1] if segment==0 else [3.0,8.2,13.2] if segment==1 else [3.3,8.7])
                active_stations=[]
                for station in stations:
                    if station>length-.8: continue
                    # The lateral concourse removes the branch side walls
                    # from |x|=37.4 onward. End the rib rhythm before that
                    # opening; a freestanding decorative jamb would cross
                    # the turn without having matching BSP collision.
                    center=local_point(a,t,n,station,0,0)
                    if abs(center[0])+.30>=37.4: continue
                    active_stations.append(station)
                    for i in range(1,len(BRANCH_PROFILE)):
                        j=(i+1)%len(BRANCH_PROFILE)
                        poly=[BRANCH_PROFILE[i],BRANCH_PROFILE[j],RIB_INNER[j],RIB_INNER[i]]
                        midw=sum(w for w,z in poly)/4; midz=sum(z for w,z in poly)/4
                        poly=[(midw+(w-midw)*.985,midz+(z-midz)*.985) for w,z in poly]
                        detail(local_profile('branch_rib',poly,station-.24,station+.24,a,t,n,mats['armor']),.028)
                    for edge in (-1,1):
                        w=edge*2.385
                        points=[local_point(a,t,n,s,w,z) for s,z in
                                ((station-.095,1.10),(station+.095,1.10),(station+.095,2.95),(station-.095,2.95))]
                        lamp('branch_rib_lens',points,125*1.20,(-edge*n[0],-edge*n[1],.15),
                             (.19,1.85),(.62,.86,1))
                    points=[local_point(a,t,n,s,w,3.765) for s,w in
                            ((station-.09,-.80),(station+.09,-.80),(station+.09,.80),(station-.09,.80))]
                    lamp('branch_ceiling_lens',points,260*.56,size=(.18,1.6),color=(1,.84,.68),spread=90)
                # Quiet fitted wall fields between the strong transverse
                # ribs have cut-corner relief and narrow double reveals.
                for center in (length*.30,length*.72):
                    half=min(1.55,length*.17)
                    # These fitted skins belong to structural walls. The
                    # final bay opens sideways into the concourse, so stop
                    # the panel field cleanly before its wall disappears.
                    ends=[local_point(a,t,n,s,0,0)[0] for s in (center-half,center+half)]
                    if max(abs(x) for x in ends)>=37.1: continue
                    for edge in (-1,1):
                        wa,wb=sorted((edge*2.53,edge*2.60))
                        poly=bevel_rectangle(center-half,.88,center+half,3.25,.24)
                        local_wall_plate('branch_shadow_field',poly,wa,wb,a,t,n,'recess',.015)
                        wa,wb=sorted((edge*2.47,edge*2.54))
                        poly=bevel_rectangle(center-half+.10,1.00,center+half-.10,3.13,.21)
                        local_wall_plate('branch_fitted_field',poly,wa,wb,a,t,n,'fitted_inset',.024)
                        wa,wb=sorted((edge*2.44,edge*2.47))
                        poly=bevel_rectangle(center-half+.27,1.19,center+half-.27,2.94,.19)
                        local_wall_plate('branch_nested_field',poly,wa,wb,a,t,n,'fitted_charcoal',.012)
                # Flush floor traces run within the flat floor footprint;
                # they stop before each joint so angled pieces never overlap.
                for edge in (-1,1):
                    w=edge*2.10
                    inner_edge=side*(-1 if rear else 1)
                    start=1.5 if segment==0 and edge==inner_edge else .45
                    points=[local_point(a,t,n,s,ww,.312) for s,ww in
                            ((start,w-.022),(length-.45,w-.022),(length-.45,w+.022),(start,w+.022))]
                    floor_strip_lamp('branch_floor_edge_lens',points)
                # A dark coffer under the actual ceiling, bounded by low
                # rails. Each bay terminates before its structural rib, so
                # fitted borders never run through a transverse arch beam.
                bay_starts=[.4]+[s+.30 for s in active_stations]
                bay_ends=[s-.30 for s in active_stations]+[length-.4]
                for start,end in zip(bay_starts,bay_ends):
                    if end-start<1.2: continue
                    obj=local_profile('branch_ceiling_coffer',[(-1.65,3.97),(1.65,3.97),
                         (1.65,4.005),(-1.65,4.005)],start,end,a,t,n,mats['recess'])
                    detail(obj,.012)
                    for edge in (-1,1):
                        local_wall_plate('branch_ceiling_rail',[(start+.09,3.89),(end-.09,3.89),
                            (end-.09,4.005),(start+.09,4.005)],edge*1.69-.045,edge*1.69+.045,a,t,n,'structure',.012)
                    for s0,s1 in ((start,start+.09),(end-.09,end)):
                        obj=local_profile('branch_coffer_cross_border',[(-1.735,3.89),(1.735,3.89),
                            (1.735,4.005),(-1.735,4.005)],s0,s1,a,t,n,mats['structure'])
                        detail(obj,.012)

    # A broad, battered front to each structural wedge visually divides the
    # two branches. Their sides continue into the full solid between routes.
    for side in (-1,1):
        outline=[(38.56,.32),(41.44,.32),(41.09,1.04),(41.09,3.74),
                 (41.33,4.00),(38.67,4.00),(38.91,3.74),(38.91,1.04)]
        a,b=sorted((side*7.85,side*8.04))
        plate('wedge_pier_cap',outline,a,b,'armor','x',.04)
        for sy in (-1,1):
            outline=[(40+sy*.12,.55),(40+sy*1.08,.55),(40+sy*.76,1.14),
                     (40+sy*.76,3.76),(40+sy*.12,3.76)]
            a,b=sorted((side*7.80,side*7.85))
            plate('wedge_nested_face',outline,a,b,'structure','x',.018)
        # Roof-connected canted shoulders have a real 23 cm return. They
        # stay within the pier silhouette and above 3.56 m clear height.
        for rear in (False,True):
            outline=[(38.92,3.56),(39.36,3.56),(39.36,4.015),(38.70,4.015)]
            if rear: outline=[(80-y,z) for y,z in outline]
            a,b=sorted((side*7.66,side*7.89))
            plate('wedge_roof_shoulder',outline,a,b,'fitted_inset','x',.025)
        # A 25 mm cyan inset follows the foot, then flares gently to meet
        # the existing 44 mm passage strips at one shared endpoint. The
        # 12 mm skin is flush enough for the independently checked floor.
        path=branch_path(1,False)
        t,n,_=basis(path[0],path[1])
        join=local_point(path[0],t,n,1.5,2.10,.312)
        toe=[(join[0],join[1]),(8.10,38.24),(7.74,38.54),
             (7.74,41.46),(8.10,41.76),(join[0],80-join[1])]
        toe=[(side*x,y) for x,y in toe]
        floor_ribbon('wedge_toe_channel',toe,[.044,.025,.025,.025,.025,.044])
        for rear in (False,True):
            cy=51.5 if rear else 28.5
            # One continuous unwrapped contour follows the actual closed
            # sidewall, diagonal corner and cap. No vertical frame divides
            # the corner into dark slots; all backing and turns stay put.
            wall_y,inward=(54.5,-1) if rear else (26.0,1)
            path=[(side*39.10,wall_y),(side*43.30,wall_y),
                  (side*43.80,wall_y+inward*.50),
                  (side*43.80,cy+inward*2.52)]
            distances=[0.0]; normals=[]
            for start,end in zip(path,path[1:]):
                dx,dy=end[0]-start[0],end[1]-start[1]
                length=math.hypot(dx,dy)
                distances.append(distances[-1]+length)
                normals.append((-dy/length*side*inward,dx/length*side*inward))
            offsets=[normals[0]]
            for n0,n1 in zip(normals,normals[1:]):
                scale=1/(1+n0[0]*n1[0]+n0[1]*n1[1])
                offsets.append(((n0[0]+n1[0])*scale,(n0[1]+n1[1])*scale))
            offsets.append(normals[-1])

            def clip_u(poly,bound,keep_greater):
                result=[]
                for p0,p1 in zip(poly,poly[1:]+poly[:1]):
                    inside0=(p0[0]>=bound) if keep_greater else (p0[0]<=bound)
                    inside1=(p1[0]>=bound) if keep_greater else (p1[0]<=bound)
                    if inside0: result.append(p0)
                    if inside0!=inside1:
                        f=(bound-p0[0])/(p1[0]-p0[0])
                        result.append((bound,p0[1]+f*(p1[1]-p0[1])))
                return result

            span=distances[-1]
            # 80 mm outer border and 80 mm recessed contour remain the
            # same width around the corner. The warm mineral infill covers
            # about 67% of the assembly; the old black central fields go.
            for label,inset,near,far,role in (
                    ('backing',0,.012,.035,'armor'),
                    ('frame',.08,.036,.060,'structure'),
                    ('reveal',.38,.061,.078,'recess'),
                    ('infill',.46,.079,.095,'structure')):
                outline=bevel_rectangle(inset,.34+inset,span-inset,3.97-inset,.26)
                for segment,(start,end) in enumerate(zip(path,path[1:])):
                    poly=clip_u(clip_u(outline,distances[segment],True),distances[segment+1],False)
                    if len(poly)<3: continue
                    def wrapped(u,z,depth):
                        f=(u-distances[segment])/(distances[segment+1]-distances[segment])
                        offset=tuple(offsets[segment][i]*(1-f)+offsets[segment+1][i]*f for i in (0,1))
                        return (start[0]+(end[0]-start[0])*f+offset[0]*depth,
                                start[1]+(end[1]-start[1])*f+offset[1]*depth,z)
                    count=len(poly)
                    vertices=[wrapped(u,z,depth) for depth in (near,far) for u,z in poly]
                    faces=[tuple(range(count)),tuple(reversed(range(count,2*count)))]
                    faces += [(i,i+count,(i+1)%count+count,(i+1)%count) for i in range(count)]
                    obj=detail(close_mesh('blind_end_wrapping_'+label,vertices,faces,mats[role]),.008)
                    obj['terminal_contour']='Continuous 80 mm border around existing closed corner; route unchanged.'
            # A restrained 0.5 m faceted corner return joins the sidewall to
            # the cap. It is attached to both solids and floor/ceiling, well
            # beyond the existing 2 x 2 m turning squares at |x|39..41.
            plan=[(side*43.30,wall_y),(side*43.80,wall_y),
                  (side*43.80,wall_y+inward*.50)]
            corner=prism('facility_blind_end_corner_return',plan,.30,4.015,mats['structure'])
            bm=bmesh.new(); bm.from_mesh(corner.data)
            bmesh.ops.recalc_face_normals(bm,faces=list(bm.faces))
            bm.to_mesh(corner.data); bm.free()
            detail(corner,.022)
            # A small roof-mounted wall washer reveals the actual blind end
            # after the side passage opens into the concourse. Its inclined
            # front aims at the cap rather than bleaching the ceiling. The
            # lowest housing point is 3.61 m, well above the walking envelope.
            xc=side*40.8
            housing=[(xc-side*.34,3.61),(xc-side*.04,3.61),
                     (xc+side*.17,4.005),(xc-side*.34,4.005)]
            plate('blind_end_wash_housing',housing,cy-.98,cy+.98,'structure',bevel=.025)
            # Match the sloping support face, then offset the luminous lens
            # 14 mm out and 7 mm down so neither face is coplanar or buried.
            def wash_point(y,z):
                return (xc+side*(-.04+(z-3.61)*.21/.395+.014),y,z-.007)
            points=[wash_point(cy-.78,3.68),wash_point(cy+.78,3.68),
                    wash_point(cy+.78,3.88),wash_point(cy-.78,3.88)]
            lamp('blind_end_wall_wash_lens',points,650*.90,(side*.882,0,-.469),
                 (1.56,.226),(.78,.90,1))

    # Foyer: deep ceiling coffers and wall-backed sealed doors frame the two
    # branch mouths without closing the transverse route through the centre.
    for x in (-5,0,5):
        block('foyer_ceiling_coffer',(x-1.75,34.0,3.94),(x+1.75,46.0,4.005),'recess',.02)
        coffer_border('foyer_coffer_border',x-1.75,34.0,x+1.75,46.0)
        for ya,yb in ((34.3,36.5),(43.5,45.7)):
            block('foyer_lens_socket',(x-.24,ya-.15,3.83),(x+.24,yb+.15,3.95),'structure',.025)
            lamp('foyer_ceiling_lens',[(x-.09,ya,3.815),(x+.09,ya,3.815),
                 (x+.09,yb,3.815),(x-.09,yb,3.815)],330*.56,size=(.18,yb-ya),
                 color=(1,.84,.68),spread=130)
    for y in (33.20,46.80):
        floor_strip_lamp('foyer_floor_edge_lens',[(-7.7,y-.022,.312),(7.7,y-.022,.312),
             (7.7,y+.022,.312),(-7.7,y+.022,.312)],foyer=True)
    # These four quiet fields occupy only the measured spare wall strips.
    # The nearest jamb housing ends at |x|5.82 and the fitted field starts
    # at |x|6.0; the opposite edge stops before the branch mouth at |x|8.
    for side in (-1,1):
        cx=side*6.9
        for y,inward in ((33,1),(47,-1)):
            lo,hi=sorted((y+inward*.012,y+inward*.035))
            plate('foyer_wall_field_reveal',bevel_rectangle(cx-.90,.70,cx+.90,3.60,.24),
                  lo,hi,'recess',bevel=.012)
            lo,hi=sorted((y+inward*.036,y+inward*.065))
            plate('foyer_fitted_wall_field',bevel_rectangle(cx-.84,.76,cx+.84,3.54,.21),
                  lo,hi,'fitted_inset',bevel=.018)
    # Ten small, source-authored washers reproduce the accepted D study.
    # They lift mineral/metal relief locally without adding room-wide fill.
    for side in (-1,1):
        ceiling_washer('foyer_pier_wash',(side*5.4,40,3.78),(side*7.8,40,2.45),
                       1.8,(2.0,.18),85)
        for y,target_y in ((35.2,33.08),(44.8,46.92)):
            ceiling_washer('foyer_wall_wash',(side*3,y,3.78),(side*3,target_y,2.4),
                           12.0,(3.0,.18),85)
        for y in (35.4,44.6):
            ceiling_washer('foyer_upper_beam_wash',(side*6.4,y,3.72),(side*9.1,y,3.4),
                           2.0,(2.8,.16),75)
    # Concourse ceiling bays continue behind the blind caps. The visible
    # route is broad and the only brighter opening is the original front door.
    for side in (-1,1):
        for y in (37,43,49):
            x=side*47.7
            block('concourse_ceiling_coffer',(x-3.5,y-1.8,3.94),(x+3.5,y+1.8,4.005),'recess',.025)
            # The first bay meets the taller entrance vault. Keep that
            # transition as authored; add borders only under the low roof.
            if y>37:
                coffer_border('concourse_coffer_border',x-3.5,y-1.8,x+3.5,y+1.8)
            lamp('concourse_ceiling_lens',[(x-2,y-.10,3.82),(x+2,y-.10,3.82),
                 (x+2,y+.10,3.82),(x-2,y+.10,3.82)],420*.56,size=(4,.20),
                 color=(1,.84,.68),spread=110)
    from facility_doors import build as build_service_doors
    build_service_doors(wall,mesh_object,box,boolean,amber_light)

    # Lower facade follows the main wall's structural rhythm. Broad quiet
    # fields, inset keyways and canted buttress feet integrate both entrances
    # into a facility instead of leaving a blank rectangular room frontage.
    for cx in (-36,0,36):
        poly=[(cx-2.25,.35),(cx+2.25,.35),(cx+1.85,6.22),(cx-1.85,6.22)]
        plate('facade_spine_foot',poly,24.25,24.59,'structure',bevel=.12)
        poly=[(cx-1.72,.65),(cx+1.72,.65),(cx+1.38,5.92),(cx-1.38,5.92)]
        plate('facade_spine_armor',poly,24.12,24.29,'armor',bevel=.08)
        plate('facade_spine_keyway',bevel_rectangle(cx-.22,1.40,cx+.22,5.0,.12),24.08,24.13,'recess',bevel=.025)
    for cx in (-28,-18,-8,8,18,28):
        plate('facade_recessed_bay',bevel_rectangle(cx-4.6,.58,cx+4.6,5.89,.58),24.50,24.59,'structure',bevel=.06)
        plate('facade_fitted_bay',bevel_rectangle(cx-4.36,.82,cx+4.36,5.65,.50),24.42,24.51,'fitted_inset',bevel=.07)
        # Inset vertical joints and a small vent give human scale without
        # competing with the large portal and tower silhouettes.
        for offset in (-2.3,2.3):
            poly=[(cx+offset-.035,1.08),(cx+offset+.035,1.08),
                  (cx+offset+.035,5.39),(cx+offset-.035,5.39)]
            plate('facade_panel_joint',poly,24.398,24.415,'recess',bevel=.006)
        plate('facade_vent_reveal',bevel_rectangle(cx-1.4,1.10,cx+1.4,1.48,.08),24.38,24.41,'recess',bevel=.02)
        for i in range(7):
            xx=cx-1.2+i*.4
            plate('facade_vent_fin',[(xx-.06,1.14),(xx+.06,1.14),(xx+.06,1.44),(xx-.06,1.44)],
                  24.34,24.38,'structure',bevel=.012)


    # The exterior arches retain their already-approved exact dimensions.
    # All interior geometry above is authored directly in final world metres.
    for obj in list(bpy.context.scene.objects):
        if obj.type!='MESH' or not obj.name.startswith('facility_'): continue
        if obj.name[len('facility_'):].startswith(('portal_','vestibule_','entry_team_')):
            cx=48 if sum(v.co.x for v in obj.data.vertices)>0 else -48
            for v in obj.data.vertices:
                v.co.x=(cx+(v.co.x*metre-cx)*4.4/3.9)/metre
                v.co.z=(.3+(v.co.z*metre-.3)*4.2/4.55)/metre
    wall['facility_design']='Indoor-only diverging passages; two same-wall entrances; blind caps and sealed service doors'
    wall['facility_floor_m']=FLOOR_Z
    wall['facility_ceiling_m']=INTERIOR_CEILING_Z
    floor_index=next((i for i,m in enumerate(wall.data.materials) if m==solid['floor']),None)
    if floor_index is None:
        floor_index=len(wall.data.materials); wall.data.materials.append(solid['floor'])
    for face in wall.data.polygons:
        if abs(face.normal.z)>.999 and all(abs(wall.data.vertices[i].co.z*metre-FLOOR_Z)<.0001 for i in face.vertices):
            face.material_index=floor_index
    bm=bmesh.new(); bm.from_mesh(wall.data)
    bmesh.ops.dissolve_limit(bm,angle_limit=.0001,verts=list(bm.verts),edges=list(bm.edges),delimit={'MATERIAL'})
    bm.to_mesh(wall.data); bm.free()
    return wall
