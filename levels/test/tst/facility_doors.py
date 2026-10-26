"""Blind maintenance niches and sealed Forerunner leaves, in world metres.

The apertures stop 45 cm behind the hall wall. Neither the visual leaf nor its
status lamp is an interactive object. The remaining structural wall supplies
collision and guarantees that the suggested deeper facility is inaccessible.
"""
from architecture_surfaces import blender_material


def build(wall, mesh_object, box, boolean, light):
    import bmesh
    from math import hypot

    finishes = {name: blender_material(name, True) for name in
                ('armor', 'structure', 'recess', 'fitted_pale',
                 'fitted_inset', 'fitted_charcoal', 'edge')}
    structural = blender_material('structure')
    height_scale = .70

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
            offsets.append((nx*width*.5,nz*width*.5))
        left = [(x+dx,z+dz) for (x,z),(dx,dz) in zip(path,offsets)]
        right = [(x-dx,z-dz) for (x,z),(dx,dz) in zip(path,offsets)]
        return left+list(reversed(right))

    for cx, front in [(x,False) for x in (-48,-18,-8.5,8.5,18,48)]+[(x,True) for x in (-8.5,8.5)]:
        wall_y = 26.2 if front else 38.2
        toward_room = 1 if front else -1
        label = ('front_' if front else 'rear_') + str(cx).replace('-', 'm').replace('.', '_')

        def profile(name, outline, near, far, material):
            # Distances are positive into the room, negative into the niche.
            y0, y1 = sorted((wall_y+toward_room*near,
                             wall_y+toward_room*far))
            count = len(outline)
            vertices = [(cx+x,y,interior_z(z)) for y in (y0,y1) for x,z in outline]
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
             chamfer(1.925,.30,4.425,.30,.58),-.40,-.035,'recess',.012)

        plate('dark_seam_backing',chamfer(1.925,.315,4.415,.30,.57),
              -.448,-.431,'recess',.008)
        for side in (-1,1):
            # The nested shield-shaped fields are fitted into the larger
            # leaves. Recessed routed channels remain narrow and angular;
            # there are no applied Y ornaments or protruding center buttons.
            outer_leaf = [(.026,.34),(1.58,.34),(1.91,.69),
                          (1.91,3.84),(1.35,4.40),(.026,4.40)]
            outer_leaf = [(side*x,z) for x,z in outer_leaf]
            plate('leaf_'+str(side),outer_leaf,-.43,-.345,'fitted_inset',.023)
            field = [(.15,.58),(1.39,.58),(1.69,.91),
                     (1.69,3.69),(1.18,4.17),(.15,4.17)]
            field = [(side*x,z) for x,z in field]
            face = profile('recessed_field_'+str(side),field,-.339,-.304,
                           finishes['fitted_charcoal'])
            # These Boolean pockets stop halfway through the 35mm field.
            # Their dark material is transferred to actual recessed faces.
            for index, channel in enumerate((
                [(.29,.83),(1.17,.83),(1.45,1.14),(1.45,1.20),
                 (1.13,.89),(.29,.89)],
                [(.29,3.92),(1.01,3.92),(1.43,3.49),(1.43,3.42),
                 (.98,3.86),(.29,3.86)],
                [(1.44,1.55),(1.50,1.55),(1.50,3.06),(1.44,3.06)],
            )):
                channel = [(side*x,z) for x,z in channel]
                boolean(face,profile('routed_channel_'+str(side)+'_'+str(index),
                                     channel,-.324,-.29,finishes['recess']))
            # Two further engraved layers step inward and become shallower.
            # Interrupted upper/lower brackets preserve generous quiet areas
            # and terminate beside the lock, instead of forming raised Y trim.
            nested_routes = (
                ('middle_upper', .045, .014,
                 [(.36,3.64),(.92,3.64),(1.29,3.25),(1.29,2.72)]),
                ('middle_lower', .045, .014,
                 [(.36,1.06),(1.03,1.06),(1.29,1.34),(1.29,2.00)]),
                ('inner_upper', .035, .010,
                 [(.34,3.36),(.76,3.36),(1.04,3.08),(1.04,2.85),
                  (.72,2.53),(.36,2.53)]),
                ('inner_lower', .035, .010,
                 [(.34,1.35),(.76,1.35),(1.04,1.63),(1.04,1.86),
                  (.72,2.18),(.36,2.18)]),
            )
            for route_name,width,depth,path in nested_routes:
                channel = [(side*x,z) for x,z in channel_outline(path,width)]
                boolean(face,profile('routed_'+route_name+'_'+str(side),
                                     channel,-.304-depth,-.29,finishes['recess']))
            # A shallow fitted shoulder transitions into the narrow status
            # insert. It is cut into the field, with no added projection and
            # at least 15mm of original solid backing beneath every pocket.
            shoulder = [(.20,2.04),(.38,2.04),(.59,2.25),(.59,2.47),
                        (.38,2.68),(.20,2.68)]
            boolean(face,profile('lock_shoulder_recess_'+str(side),
                                 [(side*x,z) for x,z in shoulder],
                                 -.310,-.29,finishes['fitted_inset']))
            finish(face,.0045)
            # A narrow inner edge catches grazing light at the sealed seam.
            plate('seam_edge_'+str(side),
                  [(side*.044,.53),(side*.083,.53),(side*.083,4.18),(side*.044,4.18)],
                  -.342,-.312,'structure',.009)

        # The status housing projects only 7cm from the leaf face. It is a
        # small vertical insert, not a control console or usable handle.
        housing = [(-.13,1.84),(.13,1.84),(.17,1.92),(.17,2.79),
                   (.10,2.88),(-.10,2.88),(-.17,2.79),(-.17,1.92)]
        plate('status_housing',housing,-.304,-.234,'structure',.018)
        plate('status_socket',[(-.047,2.02),(.047,2.02),(.047,2.71),(-.047,2.71)],
              -.232,-.226,'recess',.004)
        lens_y = wall_y+toward_room*(-.222)
        lens = mesh_object('facility_service_'+label+'_status_lens',
            [(cx-.025,lens_y,interior_z(2.04)),(cx+.025,lens_y,interior_z(2.04)),
             (cx+.025,lens_y,interior_z(2.69)),(cx-.025,lens_y,interior_z(2.69))],
            [(0,1,2,3)],[light])
        lens['tst_facility_fixture'] = True
        lens['mjolnir_pcg_policy'] = 'NONE'
        lens['authored_light_lens'] = True
        lens['light_atlas_pixels'] = (755,186,786,201)
        lens['preview_light_power'] = 32*height_scale
        lens['preview_light_direction'] = (0,toward_room,0)
        lens['preview_light_size'] = (.05,.65*height_scale)
        lens['preview_light_color'] = (1,.40,.06)
        lens['preview_emission_strength'] = 1.8
        lens['facility_status'] = 'SEALED / amber maintenance indicator, no interaction'
        lens['facility_status_light'] = True
        # A thin threshold ends inside the niche; no trim crosses the route.
        y0,y1 = sorted((wall_y+toward_room*(-.43),wall_y+toward_room*.45))
        finish(box('facility_service_'+label+'_threshold',
                   (cx-1.56,y0,interior_z(.301)),(cx+1.56,y1,interior_z(.313)),
                   finishes['structure']),.004)
