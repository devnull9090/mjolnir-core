"""Blind maintenance niches and sealed Forerunner leaves, in world metres.

The apertures stop 45 cm behind the hall wall. Neither the visual leaf nor its
status lamp is an interactive object. The remaining structural wall supplies
collision and guarantees that the suggested deeper facility is inaccessible.
"""
from architecture_surfaces import blender_material

DOOR_PLACEMENTS = (
    ('foyer_front_west',(-3,33),(1,0),(0,1)),
    ('foyer_front_east',(3,33),(1,0),(0,1)),
    ('foyer_rear_west',(-3,47),(1,0),(0,-1)),
    ('foyer_rear_east',(3,47),(1,0),(0,-1)),
    ('concourse_rear_west',(-48,54.5),(1,0),(0,-1)),
    ('concourse_rear_east',(48,54.5),(1,0),(0,-1)),
    ('concourse_side_west',(-52.5,40),(0,1),(1,0)),
    ('concourse_side_east',(52.5,40),(0,1),(-1,0)),
)


def build(wall, mesh_object, box, boolean, amber_light):
    import bmesh
    from math import hypot
    from mathutils import Vector

    finishes = {name: blender_material(name, True) for name in
                ('armor', 'structure', 'recess', 'fitted_pale',
                 'fitted_inset', 'fitted_charcoal', 'edge')}
    structural = blender_material('structure')
    height_scale = .70
    leaf_width_scale = .875
    amber_spill = tuple(amber_light['preview_spill_color'])

    def interior_z(z):
        # Keep the floor fixed while matching the lowered main-hall crown.
        # Apply once at mesh creation, including Boolean pocket cutters.
        return .30+(z-.30)*height_scale

    def chamfer(width, bottom, top, lower=.27, upper=.62):
        """Consistent clockwise correspondence for open-bottom arch strips."""
        return [(-width+lower,bottom),(width-lower,bottom),
                (width,bottom+lower),(width,top-upper),
                (width-upper,top),(-width+upper,top),
                (-width,top-upper),(-width,bottom+lower)]

    def channel_outline(path, width):
        """Miter a narrow open routing path into one closed pocket cutter."""
        widths = [width]*len(path) if isinstance(width,(int,float)) else width
        if len(widths) != len(path):
            raise ValueError('Every routing vertex needs an explicit width')
        normals = []
        for (x0,z0),(x1,z1) in zip(path,path[1:]):
            length = hypot(x1-x0,z1-z0)
            normals.append((-(z1-z0)/length,(x1-x0)/length))
        offsets = []
        for index in range(len(path)):
            if index == 0:
                nx,nz = normals[0]
            elif index == len(path)-1:
                nx,nz = normals[-1]
            else:
                ax,az = normals[index-1]
                bx,bz = normals[index]
                # Adjacent 45/90-degree bends retain constant groove width.
                scale = 1/(1+ax*bx+az*bz)
                nx,nz = (ax+bx)*scale,(az+bz)*scale
            offsets.append((nx*widths[index]*.5,nz*widths[index]*.5))
        left = [(x+dx,z+dz) for (x,z),(dx,dz) in zip(path,offsets)]
        right = [(x-dx,z-dz) for (x,z),(dx,dz) in zip(path,offsets)]
        return left+list(reversed(right))

    for label,origin,tangent,inward in DOOR_PLACEMENTS:
        def point(x,depth,z):
            return (origin[0]+tangent[0]*x+inward[0]*depth,
                    origin[1]+tangent[1]*x+inward[1]*depth,interior_z(z))

        def profile(name, outline, near, far, material):
            # Distances are positive into the room, negative into the niche.
            count = len(outline)
            vertices = [point(x,depth,z) for depth in (near,far) for x,z in outline]
            faces = [tuple(range(count)), tuple(reversed(range(count,2*count)))]
            faces += [(i,i+count,(i+1)%count+count,(i+1)%count)
                      for i in range(count)]
            obj = mesh_object('facility_service_'+label+'_'+name, vertices, faces, [material])
            bm = bmesh.new(); bm.from_mesh(obj.data)
            bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
            bm.to_mesh(obj.data); bm.free()
            return obj

        def finish(obj, bevel=.02):
            obj['mjolnir_render_detail'] = True
            obj['mjolnir_pcg_policy'] = 'NONE'
            obj['tst_facility'] = True
            obj['precision_bevel_m'] = bevel
            obj['facility_status'] = 'SEALED / decorative blind niche, solid collision backing'
            obj['authoring_note'] = 'Fitted door detail; source BSP niche terminates behind the sealed leaf.'
            return obj

        def plate(name, outline, near, far, role, bevel=.02):
            return finish(profile(name,outline,near,far,finishes[role]),bevel)

        def arch(name, outer, inner, near, far, role, bevel=.025):
            # Individually closed fitted plates, not an n-gon spanning a hole.
            for index in range(1,len(outer)):
                nxt = (index+1)%len(outer)
                poly = [outer[index],outer[nxt],inner[nxt],inner[index]]
                xmid = sum(x for x,z in poly)/4
                zmid = sum(z for x,z in poly)/4
                poly = [(xmid+(x-xmid)*.99,zmid+(z-zmid)*.99) for x,z in poly]
                plate(name+'_'+str(index),poly,near,far,role,bevel)

        aperture = chamfer(1.97,.30,4.47,.30,.59)
        # The cut extends through the battered skirting into the room, but
        # never through the 0.35m remaining rear wall or through the floor.
        boolean(wall,profile('blind_niche_cutter',aperture,-.45,1.03,structural))

        outer = chamfer(2.30,.30,4.80,.34,.68)
        reveal = chamfer(2.015,.30,4.515,.30,.60)
        arch('structural_surround',outer,reveal,-.09,.065,'structure',.035)
        # A restrained titanium lip and dark interior return give three
        # distinct depths without turning the entire border brilliant white.
        arch('precision_lip',chamfer(2.08,.30,4.58,.31,.62),
             chamfer(2.015,.30,4.515,.30,.60),.068,.098,'fitted_inset',.012)
        arch('shadow_return',chamfer(1.99,.30,4.49,.30,.59),
             chamfer(1.925,.30,4.425,.30,.58),-.40,.055,'recess',.012)

        # A deeper visible jamb surrounds narrower paired leaves without
        # changing the 4.6 m outer assembly or the 45 cm blind pocket. These
        # canted, closed return panels fill the newly exposed lateral space;
        # their front edge remains behind the existing 65 mm surround.
        return_outer=chamfer(1.925,.30,4.425,.30,.58)
        return_inner=[(x*leaf_width_scale,z) for x,z in return_outer]
        for index in range(1,len(return_outer)):
            nxt=(index+1)%len(return_outer)
            front=[Vector(point(*args)) for args in
                   ((return_outer[index][0],.045,return_outer[index][1]),
                    (return_outer[nxt][0],.045,return_outer[nxt][1]),
                    (return_inner[nxt][0],-.344,return_inner[nxt][1]),
                    (return_inner[index][0],-.344,return_inner[index][1]))]
            normal=(front[1]-front[0]).cross(front[2]-front[0]).normalized()
            toward_opening=Vector(point(0,.5,2.2))-sum(front,Vector())/4
            if normal.dot(toward_opening)<0: normal=-normal
            # Extrude along the face normal so the horizontal head return
            # also has real thickness; a depth-only extrusion would be flat.
            vertices=[tuple(v) for v in front]+[tuple(v-normal*.018) for v in front]
            faces=[(0,1,2,3),(7,6,5,4),(0,4,5,1),(1,5,6,2),(2,6,7,3),(3,7,4,0)]
            obj=mesh_object('facility_service_'+label+'_fitted_leaf_return_'+str(index),
                            vertices,faces,[finishes['fitted_charcoal']])
            bm=bmesh.new(); bm.from_mesh(obj.data)
            bmesh.ops.recalc_face_normals(bm,faces=list(bm.faces))
            bm.to_mesh(obj.data); bm.free()
            finish(obj,.008)

        plate('dark_seam_backing',chamfer(1.925,.315,4.415,.30,.57),
              -.448,-.431,'recess',.008)
        for side in (-1,1):
            # Shield-shaped metal fields are fitted into the larger leaves.
            # The relief is an interconnected assembly seated in the field,
            # rather than disconnected bracket ornaments or center buttons.
            outer_leaf = [(.026,.34),(1.58,.34),(1.91,.69),
                          (1.91,3.84),(1.35,4.40),(.026,4.40)]
            outer_leaf = [(side*x*leaf_width_scale,z) for x,z in outer_leaf]
            plate('leaf_'+str(side),outer_leaf,-.43,-.345,'fitted_inset',.023)
            field = [(.15,.58),(1.39,.58),(1.69,.91),
                     (1.69,3.69),(1.18,4.17),(.15,4.17)]
            field = [(side*x*leaf_width_scale,z) for x,z in field]
            face = profile('recessed_field_'+str(side),field,-.339,-.304,
                           finishes['fitted_charcoal'])
            # Two angular branches merge into a shared vertical trunk in
            # each half. This is a branching hierarchy, not nested C-shaped
            # outlines: the outer fork meets the trunk below the inner fork,
            # and both lead continuously to the unchanged amber housing.
            # Arms taper 30% toward the trunk. After the established height/
            # leaf scaling they are 21–38 mm wide, with the same 20 mm relief.
            # One secondary wing branches from the outer fork into each
            # blank middle quadrant. It adds 41.6% to the routed contour
            # length, with two 45-degree changes and only 6.3% additional
            # leaf-width reach. Its first 12 cm taper toward the joined fork.
            for upper in (True,False):
                routes=(
                    ('stem',[(.11,2.86),(.20,2.99),(.20,3.43)],
                     [.038,.038,.038]),
                    ('inner_arm',[(.20,3.34),(.61,3.72),(.61,4.03)],
                     [.0301,.043,.043]),
                    ('outer_arm',[(.20,3.09),(1.10,3.80),(1.10,4.03)],
                     [.0301,.043,.043]),
                    ('middle_wing',[(.65,3.445),(.757,3.338),(.87,3.225),
                                    (.87,2.84),(1.22,2.49)],
                     [.0301,.043,.043,.043,.043]),
                )
                trim=None
                for part,route,widths in routes:
                    if not upper:
                        route=[(x,4.72-z) for x,z in route]
                    # The continuous dark bed gives the real band a narrow
                    # shadow gutter. Its 10 mm depth retains 25 mm of solid
                    # field; the 15 mm seat reaches 5 mm into that backing.
                    channel=[(side*x*leaf_width_scale,z) for x,z in
                             channel_outline(route,[width+.018 for width in widths])]
                    boolean(face,profile('routed_'+('upper_' if upper else 'lower_')+
                                         str(side)+'_'+part,channel,-.314,-.29,
                                         finishes['recess']))
                    outline=[(side*x*leaf_width_scale,z) for x,z in channel_outline(route,widths)]
                    piece=profile('connected_relief_'+('upper_' if upper else 'lower_')+
                                  str(side)+'_'+part,outline,-.319,-.284,finishes['fitted_inset'])
                    if trim is None: trim=piece
                    else: boolean(trim,piece,'UNION')
                finish(trim,.0045)
                trim['door_relief']='Two angular Y forks and a connected secondary wing; 15 mm seated, 20 mm raised, 21–38 mm width, arms taper 30% toward joins.'
                bm=bmesh.new(); bm.from_mesh(trim.data)
                if any(not edge.is_manifold for edge in bm.edges):
                    bm.free()
                    raise ValueError('Connected door relief is not a closed solid: '+trim.name)
                bm.free()
            # A shallow fitted shoulder transitions into the narrow status
            # insert. It is cut into the field, with no added projection and
            # at least 15mm of original solid backing beneath every pocket.
            # The former broad tabs become compact tapered pockets beside
            # the narrower vertical mount: 45% less width, with 28 mm tips.
            shoulder = [(.16,2.14),(.27,2.14),(.375,2.34),(.375,2.38),
                        (.27,2.58),(.16,2.58)]
            boolean(face,profile('lock_shoulder_recess_'+str(side),
                                 [(side*x*leaf_width_scale,z) for x,z in shoulder],
                                 -.314,-.29,finishes['fitted_inset']))
            finish(face,.0045)
            # A narrow inner edge catches grazing light at the sealed seam.
            plate('seam_edge_'+str(side),
                  [(side*x*leaf_width_scale,z) for x,z in
                   ((.044,.53),(.083,.53),(.083,4.18),(.044,4.18))],
                  -.342,-.312,'structure',.009)

        # The status housing projects only 7cm from the leaf face. It is a
        # small vertical insert, not a control console or usable handle.
        housing = [(-.13,1.84),(.13,1.84),(.17,1.92),(.17,2.79),
                   (.10,2.88),(-.10,2.88),(-.17,2.79),(-.17,1.92)]
        housing=[(x*.78,z) for x,z in housing]
        plate('status_housing',housing,-.304,-.234,'structure',.012)
        plate('status_socket',[(-.047,2.02),(.047,2.02),(.047,2.71),(-.047,2.71)],
              -.232,-.226,'recess',.004)
        points=[point(-.025,-.222,2.04),point(.025,-.222,2.04),
                point(.025,-.222,2.69),point(-.025,-.222,2.69)]
        direction=(*inward,0)
        normal=(Vector(points[1])-Vector(points[0])).cross(Vector(points[2])-Vector(points[0]))
        winding=(0,1,2,3) if normal.dot(Vector(direction))>0 else (3,2,1,0)
        lens = mesh_object('facility_service_'+label+'_status_lens',points,[winding],[amber_light])
        lens['tst_facility_fixture'] = True
        lens['mjolnir_pcg_policy'] = 'NONE'
        lens['authored_light_lens'] = True
        lens['face_direction'] = direction
        lens['light_atlas_pixels'] = tuple(amber_light['light_atlas_pixels'])
        lens['preview_light_power'] = 32*height_scale*.72
        lens['preview_light_direction'] = (*inward,0)
        lens['preview_light_size'] = (.05,.65*height_scale)
        # Desaturated reflected spill is a Blender lighting study; the visible
        # emitter and exported shader retain the authored amber source color.
        lens['preview_light_color'] = amber_spill
        lens['preview_emission_strength'] = 1.8
        lens['facility_status'] = 'SEALED / amber maintenance indicator, no interaction'
        lens['facility_status_light'] = True
        # An outward jamb repeat carries the same sealed-maintenance amber
        # signal. It is wall-attached, outside the existing frame, and has
        # no handle/button geometry or interactive authoring metadata.
        jamb_side=(1 if origin[0]>0 else -1) if tangent==(1,0) else 1
        jamb_x=jamb_side*2.65
        housing=[(jamb_x+jamb_side*x,z) for x,z in
                 ((-.17,1.75),(.17,1.75),(.17,2.83),(.04,3.02),(-.17,3.02))]
        plate('jamb_status_housing',housing,-.02,.15,'structure',.018)
        plate('jamb_status_socket',[(jamb_x-.054,1.90),(jamb_x+.054,1.90),
              (jamb_x+.054,2.91),(jamb_x-.054,2.91)],.151,.17,'recess',.006)
        points=[point(jamb_x-.03,.177,1.942857),point(jamb_x+.03,.177,1.942857),
                point(jamb_x+.03,.177,2.871429),point(jamb_x-.03,.177,2.871429)]
        normal=(Vector(points[1])-Vector(points[0])).cross(Vector(points[2])-Vector(points[0]))
        winding=(0,1,2,3) if normal.dot(Vector(direction))>0 else (3,2,1,0)
        jamb=mesh_object('facility_service_'+label+'_jamb_status_lens',points,[winding],[amber_light])
        jamb['tst_facility_fixture']=True
        jamb['mjolnir_pcg_policy']='NONE'
        jamb['authored_light_lens']=True
        jamb['face_direction']=direction
        jamb['light_atlas_pixels']=tuple(amber_light['light_atlas_pixels'])
        jamb['preview_light_power']=14.0*.72
        jamb['preview_light_direction']=direction
        jamb['preview_light_size']=(.06,.65)
        jamb['preview_light_color']=amber_spill
        jamb['preview_emission_strength']=1.8
        jamb['facility_status']='SEALED / wall-attached amber maintenance indicator, no interaction'
        jamb['facility_status_light']=True
        # A thin threshold ends inside the niche; no trim crosses the route.
        a,b=point(-1.56,-.43,.301),point(1.56,.45,.313)
        lo=tuple(min(x,y) for x,y in zip(a,b))
        hi=tuple(max(x,y) for x,y in zip(a,b))
        finish(box('facility_service_'+label+'_threshold',
                   lo,hi,
                   finishes['structure']),.004)
