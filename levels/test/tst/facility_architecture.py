"""Enclosed under-balcony facility, authored in metres.

The two arena-facing vestibules are its only entrances. A covered lateral
route folds around solid bulkheads; amber service doors remain sealed.
All metal uses the same eight exported finishes as the outdoor architecture.
"""
import math
from architecture_surfaces import blender_material

FLOOR_Z = .30
INTERIOR_HEIGHT_SCALE = .70
INTERIOR_CEILING_Z = FLOOR_Z+(5.60-FLOOR_Z)*INTERIOR_HEIGHT_SCALE
HALL_PROFILE = [(28.5,.30),(37.7,.30),(38.2,1.10),(38.2,4.55),
                (37.15,5.60),(29.05,5.60),(28,4.55),(28,1.10)]


def build(wall, mesh_object, box, prism, bevel_rectangle, boolean, light, red, blue):
    import bpy
    import bmesh
    metre = 3.048
    mats = {name: blender_material(name, True) for name in
            ('armor','structure','recess','floor','fitted_pale','fitted_inset','fitted_charcoal','edge')}
    solid = {name: blender_material(name) for name in ('armor','structure','floor')}
    def hall_y(y):
        return 26.2+(y-28)*12/10.2
    def remap(obj, core=False):
        for v in obj.data.vertices:
            y=v.co.y*metre
            v.co.y=(32.2+(y-33.1)*.8 if core else hall_y(y))/metre
            if core: v.co.x*=1.4
        return obj

    def world_space(obj):
        # The junction is dimensioned in the expanded hall's final metres.
        # Do not apply the legacy hall/profile remap a second time.
        obj['facility_world_space']=True
        return obj

    def compress_interior(obj):
        # Keep the shared walking datum and horizontal gameplay dimensions.
        # Apply before each collision Boolean and once to the matching skin.
        if obj.get('facility_height_scaled'):
            raise ValueError('Facility interior was height-scaled twice: '+obj.name)
        z_span=max(v.co.z for v in obj.data.vertices)-min(v.co.z for v in obj.data.vertices)
        for v in obj.data.vertices:
            v.co.z=(FLOOR_Z+(v.co.z*metre-FLOOR_Z)*INTERIOR_HEIGHT_SCALE)/metre
        if obj.get('authored_light_lens'):
            obj['preview_light_power']*=INTERIOR_HEIGHT_SCALE
            if z_span>1e-5:
                width,height=obj['preview_light_size']
                obj['preview_light_size']=(width,height*INTERIOR_HEIGHT_SCALE)
        obj['facility_height_scaled']=INTERIOR_HEIGHT_SCALE
        return obj

    def profile(name, outline, start, end, mat, axis='y'):
        def point(a, d, b):
            return (a,d,b) if axis=='y' else (d,a,b)
        n=len(outline)
        verts=[point(a,d,b) for d in (start,end) for a,b in outline]
        faces=[tuple(range(n)),tuple(reversed(range(n,2*n)))]
        faces += [(i,i+n,(i+1)%n+n,(i+1)%n) for i in range(n)]
        obj=mesh_object('facility_'+name,verts,faces,[mat])
        bm=bmesh.new(); bm.from_mesh(obj.data)
        bmesh.ops.recalc_face_normals(bm,faces=list(bm.faces))
        bm.to_mesh(obj.data); bm.free()
        return obj

    def detail(obj, bevel=.025):
        obj['mjolnir_render_detail']=True
        obj['mjolnir_pcg_policy']='NONE'
        obj['tst_facility']=True
        obj['precision_bevel_m']=bevel
        obj['authoring_note']='Editable facility finish; sealed underlying BSP owns collision.'
        return obj

    def block(name, lo, hi, role='structure', bevel=.025):
        return detail(box('facility_'+name,lo,hi,mats[role]),bevel)

    def plate(name, poly, d0, d1, role='armor', axis='y', bevel=.025):
        return detail(profile(name,poly,d0,d1,mats[role],axis),bevel)

    def lamp(name, points, power=0, direction=(0,0,-1), size=(2.4,.3), color=(.96,.96,1)):
        obj=mesh_object('facility_'+name,points,[(0,1,2,3)],[light])
        obj['tst_facility_fixture']=True
        obj['mjolnir_pcg_policy']='NONE'
        obj['preview_emission_strength']=2.4
        if power:
            obj['authored_light_lens']=True
            obj['preview_light_power']=power*.23
            obj['preview_light_direction']=direction
            obj['preview_light_size']=size
            obj['preview_light_color']=color
        return obj

    def ring(name, outer, inner, d0, d1, axis='y', role='armor'):
        # Separate fitted rib plates have deliberate dark assembly joints.
        # Leave the lower edge open to keep the walking surface flush.
        for i in range(1,len(outer)):
            j=(i+1)%len(outer)
            poly=[outer[i],outer[j],inner[j],inner[i]]
            cx=sum(p[0] for p in poly)/4; cz=sum(p[1] for p in poly)/4
            poly=[(cx+(x-cx)*.985,cz+(z-cz)*.985) for x,z in poly]
            plate(name+'_'+str(i),poly,d0,d1,role,axis,.035)

    # Merge the room envelope into the existing retaining structure BEFORE
    # cutting the air route. This opens the original wall and lower spines too.
    boolean(wall,box('facility_envelope',(-53,24.6,-.6),(53,39,6.35),solid['armor']),'UNION')
    boolean(wall,compress_interior(remap(profile('main_air',HALL_PROFILE,-51.7,51.7,solid['structure'],'x'))))
    for side in (-1,1):
        cx=side*48
        opening=[(cx-3.15,.3),(cx+3.15,.3),(cx+3.9,1.05),
                 (cx+3.9,3.85),(cx+2.95,4.85),(cx-2.95,4.85),
                 (cx-3.9,3.85),(cx-3.9,1.05)]
        opening=[(cx+(x-cx)*4.4/3.9,.3+(z-.3)*4.2/4.55) for x,z in opening]
        boolean(wall,profile('vestibule_air',opening,23.8,37.8,solid['structure']))
        # A broad almost-level apron joins the excavated terrain; no step/jump.
        apron=profile('entry_apron',[(22.1,-.35),(27.9,-.35),(27.9,.30),
                      (24.6,.30),(22.1,-.10)],cx-4.45,cx+4.45,solid['floor'],'x')
        boolean(wall,apron,'UNION')

    # Flush common floor; top of the volume is exactly the walking datum.
    boolean(wall,box('facility_floor',(-52.5,25,-.45),(52.5,38.8,.3),solid['floor']),'UNION')
    for side in (-1,1):
        x=side*39
        poly=bevel_rectangle(x-.65,28,x+.65,33.8,.20)
        boolean(wall,compress_interior(remap(prism('facility_front_baffle',poly,.3,5.8,solid['structure']))),'UNION')
        x=side*26
        poly=bevel_rectangle(x-.65,33,x+.65,38.2,.20)
        boolean(wall,compress_interior(remap(prism('facility_rear_baffle',poly,.3,5.8,solid['structure']))),'UNION')
    core_profile=[(31.0,.3),(33.4,.3),(33.0,1.4),(33.0,5.8),
                  (31.4,5.8),(31.4,1.4)]
    for a,b in ((-6.44,-3.0),(3.0,6.44)):
        boolean(wall,compress_interior(profile('central_pier',core_profile,a,b,solid['structure'],'x')),'UNION')
    # Two sealed wing walls make a substantial central cross-gate. The
    # 3.2 m opening joins both halves indoors, with 2.5 m turning bays on
    # either side between each short pier and the gate's structural face.
    for ya,yb in ((26.0,30.6),(33.8,38.4)):
        boolean(wall,compress_interior(box('facility_central_gate',(-.5,ya,.3),(.5,yb,5.8),solid['structure'])),'UNION')

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
                 (cx+1.8,y+.19,4.50),(cx-1.8,y+.19,4.50)],700,size=(3.6,.20))

    # Main route ribs. Articulate planes rather than tiling one texture over
    # a tube: broad armor, black shadow joints, pale edge plates, inset coffers.
    rib_inner=[(28.60,.30),(37.60,.30),(37.91,1.15),(37.91,4.42),
               (37.04,5.29),(29.16,5.29),(28.29,4.42),(28.29,1.15)]
    # Ribs occupy panel joints and leave all sealed-door leaves unobstructed.
    for x in sorted(side*d for side in (-1,1) for d in (5,11.5,15,21,33,45)):
        ring('hall_structural_rib',HALL_PROFILE,rib_inner,x-.32,x+.32,'x','armor')
        for y,sign in ((28.33,1),(37.87,-1)):
            # Vertical lens strips sit on the rib's broad return face.
            lamp('hall_rib_lens',[(x-.13,y,1.48),(x+.13,y,1.48),
                 (x+.13,y,3.85),(x-.13,y,3.85)],50,(0,sign,.35),(.18,2.3))
        block('ceiling_light_socket',(x-.38,30,5.29),(x+.38,36.2,5.53),'recess',.06)
        for ya,yb in ((30.4,31.8),(34.4,35.8)):
            lamp('hall_ceiling_lens',[(x-.14,ya,5.265),(x+.14,ya,5.265),
                 (x+.14,yb,5.265),(x-.14,yb,5.265)],500,size=(.30,yb-ya))
        for y in (28.7,37.5):
            block('concealed_uplight_tray',(x-.30,y-.12,4.39),(x+.30,y+.12,4.48),'structure',.03)
            lamp('ceiling_bounce_lens',[(x-.22,y-.08,4.49),(x+.22,y-.08,4.49),
                 (x+.22,y+.08,4.49),(x-.22,y+.08,4.49)],65,(0,0,1),(.90,.40),(.96,.90,.78))

    # Wall armor panels each have real chamfered shoulders and thin borders.
    for x in range(-42,43,6):
        for y,front in ((28.06,True),(38.14,False)):
            if front and abs(x)>42: continue
            if any(abs(x-d)<5 for d in (-8.5,8.5)): continue
            if not front and any(abs(x-d)<3.3 for d in (-48,-18,18,48)): continue
            a,b=(y,y+.16) if front else (y-.16,y)
            plate('wall_shadow_panel',bevel_rectangle(x-2.65,1.12,x+2.65,4.40,.34),
                  a,b,'recess',bevel=.03)
            a,b=(y+.16,y+.26) if front else (y-.26,y-.16)
            plate('wall_fitted_armor',bevel_rectangle(x-2.48,1.27,x+2.48,4.24,.31),
                  a,b,'fitted_inset',bevel=.05)
            # Two offset fields leave a clean chevron-shaped dark gasket.
            a,b=(y+.27,y+.31) if front else (y-.31,y-.27)
            for s in (-1,1):
                coords=[(x+s*.09,1.51),(x+s*2.18,1.51),(x+s*2.30,1.70),
                        (x+s*2.30,3.80),(x+s*1.98,4.03),(x+s*.09,4.03)]
                plate('wall_inner_leaf',coords,a,b,'fitted_charcoal',bevel=.025)
                # Nested angular fields leave narrow dark reveal channels.
                # No raised generic symbols compete with the door language.
                poly=[(x+s*.26,1.74),(x+s*1.77,1.74),(x+s*2.01,1.98),
                      (x+s*2.01,3.56),(x+s*1.76,3.82),(x+s*.26,3.82)]
                aa,bb=(b+.012,b+.034) if front else (a-.034,a-.012)
                plate('wall_inner_reveal',poly,aa,bb,'recess',bevel=.012)
                cx=sum(v[0] for v in poly)/len(poly); cz=sum(v[1] for v in poly)/len(poly)
                poly=[(cx+(u-cx)*.94,cz+(v-cz)*.94) for u,v in poly]
                aa,bb=(b+.035,b+.062) if front else (a-.062,a-.035)
                plate('wall_inner_armor_field',poly,aa,bb,'structure',bevel=.018)
            # Upper technical reveal and lower continuous cable trunk.
            block('wall_skirting',(x-2.70,min(y,y+.12),.68),
                  (x+2.70,max(y+.12,y+.30),.90),'structure',.04)

    # Two roof-connected piers retain the broad north/south bypasses, then
    # release into transverse turning bays at the centre of the facility.
    for x,sign in ((-6.44,-1),(-3.0,1),(3.0,-1),(6.44,1)):
        a,b=sorted((x,x+sign*.09))
        poly=[(31.04,.32),(33.36,.32),(32.96,1.45),(32.96,5.60),
              (31.44,5.60),(31.44,1.45)]
        world_space(plate('core_pier_end',poly,a,b,'armor','x',.045))
        for sy in (-1,1):
            poly=[(32.2+sy*.14,.58),(32.2+sy*.96,.58),
                  (32.2+sy*.63,1.56),(32.2+sy*.63,5.38),
                  (32.2+sy*.14,5.38)]
            a,b=sorted((x+sign*.10,x+sign*.15))
            world_space(plate('core_pier_vertical_recess',poly,a,b,'structure','x',.025))
        a,b=sorted((x+sign*.16,x+sign*.18))
        world_space(plate('core_pier_centre_seam',[(32.176,.6),(32.224,.6),
                          (32.224,5.6),(32.176,5.6)],a,b,'recess','x',.008))
    for y,front in ((31.40,True),(33.0,False)):
        a,b=(y-.08,y) if front else (y,y+.08)
        for x in (-4.72,4.72):
            world_space(plate('core_pier_side_bay',bevel_rectangle(x-1.44,1.55,x+1.44,5.35,.30),a,b,'fitted_inset',bevel=.04))
            aa,bb=(a-.035,a) if front else (b,b+.035)
            world_space(plate('core_pier_side_recess',bevel_rectangle(x-1.22,1.76,x+1.22,5.14,.27),aa,bb,'structure',bevel=.025))

    # Substantial closed end faces flank the central opening. All nested
    # plates stay inside the wings' Y footprint, so the real 3.2 m passage
    # survives every finish layer. The outer shoulders fit the hall bevels.
    gate_outline=[(26.90,.34),(30.30,.34),(30.57,.61),(30.57,5.30),
                  (30.30,5.57),(27.49,5.57),(26.36,4.44),(26.36,1.12)]
    for rear in (False,True):
        outline=[(64.4-y,z) if rear else (y,z) for y,z in gate_outline]
        for sx in (-1,1):
            a,b=sorted((sx*.50,sx*.61))
            world_space(plate('central_gate_cap',outline,a,b,'armor','x',.04))
            # Broad quiet armour surrounded by three legible inset reveals.
            for layer,inset,depth,role in ((0,.12,.025,'fitted_pale'),
                                           (1,.20,.045,'recess'),
                                           (2,.30,.070,'fitted_charcoal')):
                poly=bevel_rectangle(26.96+inset,.55+inset,30.36-inset,5.34-inset,.38)
                if rear: poly=[(64.4-y,z) for y,z in poly]
                a,b=sorted((sx*(.62+depth),sx*(.64+depth)))
                world_space(plate('central_gate_inset_'+str(layer),poly,a,b,role,'x',.014))
            # Full-height edge light identifies the gap without suggesting
            # an operable door or an equipment control panel.
            ya,yb=(30.36,30.43) if not rear else (33.97,34.04)
            px=sx*.735
            world_space(lamp('central_gate_edge_lens',[(px,ya,1.22),(px,yb,1.22),
                              (px,yb,4.68),(px,ya,4.68)]))

    # Faceted bulkhead end caps keep alternate bends from looking like boxes.
    for side in (-1,1):
        for x,y,direction in ((side*39,33.8,1),(side*26,33,-1)):
            ya,yb=(28.6,33.5) if direction==1 else (33.3,37.6)
            for sx in (-1,1):
                a,b=sorted((x+sx*.66,x+sx*.77))
                plate('baffle_shadow_field',bevel_rectangle(ya,.75,yb,5.15,.48),a,b,'recess','x',.04)
                a,b=sorted((x+sx*.78,x+sx*.88))
                plate('baffle_fitted_field',bevel_rectangle(ya+.19,.96,yb-.19,4.94,.42),a,b,'fitted_charcoal','x',.045)
                # Diagonal raised shoulders flank a recessed technical spine.
                cy=(ya+yb)*.5
                for sy in (-1,1):
                    poly=[(cy+sy*.18,1.20),(cy+sy*(yb-ya)*.35,1.20),
                          (cy+sy*(yb-ya)*.40,1.62),(cy+sy*(yb-ya)*.40,4.27),
                          (cy+sy*(yb-ya)*.27,4.68),(cy+sy*.18,4.68)]
                    a,b=sorted((x+sx*.89,x+sx*.96))
                    plate('baffle_armor_shoulder',poly,a,b,'armor','x',.04)
                for z in (1.48,2.05,2.62,3.19,3.76):
                    a,b=sorted((x+sx*.97,x+sx*1.035))
                    plate('baffle_spine_vent',bevel_rectangle(cy-.13,z,cy+.13,z+.27,.06),a,b,'structure','x',.015)
            poly=bevel_rectangle(x-.62,.65,x+.62,5.25,.20)
            a,b=sorted((y,y+direction*.17))
            plate('turn_pier_cap',poly,a,b,'fitted_pale',bevel=.05)
            poly=bevel_rectangle(x-.39,1.0,x+.39,4.91,.16)
            a,b=sorted((y+direction*.18,y+direction*.25))
            plate('turn_pier_insert',poly,a,b,'recess')
            yy=y+direction*.26
            lamp('turn_pier_lens',[(x-.06,yy,1.5),(x+.06,yy,1.5),
                 (x+.06,yy,4.3),(x-.06,yy,4.3)],90,(0,direction,0),(.12,2.8))

    # Real blind niches and solid service doors remain in world coordinates.
    from facility_doors import build as build_service_doors
    build_service_doors(wall,mesh_object,box,boolean,light)

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

    # Floor layout is flush and deliberately broad. Narrow gaskets, edge
    # channels and diamond corner cuts read at player scale without a grid.
    for x in range(-48,49,4):
        for ya,yb in ((29.05,32.9),(33.12,37.12)):
            if abs(x)<6 and ya>31: continue
            slab=prism('facility_floor_plate',bevel_rectangle(x-1.94,ya,x+1.94,yb,.20),
                       .3005,.313,mats['floor'])
            detail(slab,.008)
    # Segmented dark ceiling coffers with corner armor and exposed cross rails.
    # Their recess depth gives the room a convincing underside at eye level.
    for x in range(-42,43,6):
        if abs(x)<6: continue
        obj=prism('facility_ceiling_recess',bevel_rectangle(x-2.5,29.25,x+2.5,36.95,.45),
                  5.52,5.59,mats['recess'])
        detail(obj,.025)
        for y in (30.0,36.2):
            block('ceiling_parallel_rail',(x-2.45,y-.12,5.41),(x+2.45,y+.12,5.52),'structure',.03)
        for dy in (-.35,0,.35):
            block('ceiling_vent_blade',(x-1.55,33.1+dy-.07,5.43),(x+1.55,33.1+dy+.07,5.53),'armor',.025)
    for y in (29.03,37.17):
        for a,b in ((-43,-40.0),(-38,-27),(-25,-5.4),(5.4,25),(27,38),(40,43)):
            block('floor_light_channel',(a,y-.10,.31),(b,y+.10,.35),'recess',.01)
            lamp('floor_edge_lens',[(a+.15,y-.025,.355),(b-.15,y-.025,.355),
                 (b-.15,y+.025,.355),(a+.15,y+.025,.355)])
    # Roof coffers and strips at the central junction supply an authored
    # focal lighting rhythm even when no daylight reaches the bend.
    for x in (-9,-5,5,9):
        block('junction_ceiling_coffer',(x-.65,29.2,5.36),(x+.65,37.0,5.58),'recess',.08)
        for ya,yb in ((29.6,31.1),(35.1,36.6)):
            lamp('junction_ceiling_lens',[(x-.12,ya,5.335),(x+.12,ya,5.335),
                 (x+.12,yb,5.335),(x-.12,yb,5.335)],480,size=(.24,yb-ya))
    # Fit this module's interior to the measured under-balcony envelope.
    # Both bypasses gain over 40 percent clear floor width; exterior portals
    # are wider and lower. The source remains metre-parametric and editable.
    for obj in list(bpy.context.scene.objects):
        if obj.type!='MESH' or not obj.name.startswith('facility_'): continue
        name=obj.name[len('facility_'):]
        if name.startswith(('facade_','service_')): continue
        if name.startswith(('portal_','vestibule_','entry_team_')):
            cx=48 if sum(v.co.x for v in obj.data.vertices)>0 else -48
            for v in obj.data.vertices:
                v.co.x=(cx+(v.co.x*metre-cx)*4.4/3.9)/metre
                v.co.z=(.3+(v.co.z*metre-.3)*4.2/4.55)/metre
        else:
            if not obj.get('facility_world_space'):
                remap(obj,name.startswith('core_'))
            compress_interior(obj)
    wall['facility_design']='Indoor-only, two same-wall entrances, mirrored doglegs, sealed service doors'
    wall['facility_floor_m']=FLOOR_Z
    wall['facility_ceiling_m']=INTERIOR_CEILING_Z
    # The intersecting doorway/chamber/apron cutters all meet at one floor
    # datum. Give that coplanar skin one finish before the CE-scale weld;
    # artificial material boundaries must not preserve tiny Boolean slivers.
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
