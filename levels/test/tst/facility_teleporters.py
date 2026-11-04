"""Mirrored balcony lift niches in the facility entrance side walls.

All dimensions are final world metres. A shallow sealed pocket is deliberately
used here: the opposite side of this wall is an existing blind hallway cap.
The green shield is visual only; the placement owns the teleport trigger.
"""

CENTER_Y = 27.9
WALL_X = 44.6
BACK_X = 43.98
SHIELD_X = 44.12
FLOOR_Z = .30
TRIGGER_RADIUS_M = .78


def balcony_links(arrivals):
    links = []
    for channel, arrival in enumerate(arrivals, 2):
        side = -1 if arrival[0] < 0 else 1
        links.append({
            'channel': channel, 'from_m': [side*WALL_X, CENTER_Y, .35],
            'to_m': list(arrival), 'from_yaw_degrees': 0 if side < 0 else 180,
            'to_yaw_degrees': 270, 'scenery': False, 'radius_m': TRIGGER_RADIUS_M,
            'authoring_note': 'Recessed indoor side-wall shield to balcony; no exterior pad',
        })
        links.append({
            'channel': channel+2, 'from_m': [arrival[0], 30.85, 7.25],
            'to_m': [side*47, CENTER_Y, .35], 'from_yaw_degrees': 90,
            'to_yaw_degrees': 180 if side < 0 else 0, 'scenery': False,
            'shield_return': True,
            'authoring_note': 'Balcony shield returns inside the vestibule, facing away from the lift; separate landing avoids bounce-back',
        })
    return links


def build(wall, mesh_object, boolean, portal, lamp, detail):
    import bmesh
    from architecture_surfaces import blender_material
    finishes = {name: blender_material(name, True) for name in
                ('facility_structure', 'facility_recess', 'fitted_pale')}
    structural = blender_material('facility_structure')

    def arch(width, top, shoulder):
        return [(-width, FLOOR_Z), (width, FLOOR_Z),
                (width, top-shoulder), (width-shoulder, top),
                (-width+shoulder, top), (-width, top-shoulder)]

    for side in (-1, 1):
        label = 'red' if side < 0 else 'blue'

        def point(u, depth, z):
            return (side*depth, CENTER_Y+u, z)

        def profile(name, outline, start, end, material):
            count = len(outline)
            vertices = [point(u, depth, z) for depth in (start, end) for u,z in outline]
            faces = [tuple(range(count)), tuple(reversed(range(count, 2*count)))]
            faces += [(i, i+count, (i+1)%count+count, (i+1)%count) for i in range(count)]
            obj = mesh_object('facility_lift_'+label+'_'+name, vertices, faces, [material])
            bm = bmesh.new(); bm.from_mesh(obj.data)
            bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
            bm.to_mesh(obj.data); bm.free()
            return obj

        aperture = arch(1.02, 3.12, .40)
        # Stop 18 cm before the rear of the original .80 m solid cap.
        # The cutter starts on the floor, so there is no raised threshold.
        boolean(wall, profile('pocket_air', aperture, BACK_X, WALL_X+.30, structural))

        def frame(name, outer, inner, start, end, role, bevel=.015):
            # Skip the bottom edge, leaving the walking surface uninterrupted.
            for i in range(1, len(outer)):
                j = (i+1) % len(outer)
                outline = [outer[i], outer[j], inner[j], inner[i]]
                detail(profile(name+'_'+str(i), outline, start, end, finishes[role]), bevel)

        frame('shadow_gasket', arch(1.27, 3.43, .47), aperture,
              WALL_X-.015, WALL_X+.035, 'facility_recess', .012)
        frame('fitted_surround', arch(1.23, 3.38, .46), arch(1.09, 3.20, .42),
              WALL_X+.030, WALL_X+.105, 'facility_structure', .018)
        frame('inner_lip', arch(1.085, 3.195, .42), aperture,
              WALL_X+.025, WALL_X+.065, 'fitted_pale', .008)
        # Sleeved reveal follows the actual pocket walls and ends behind the
        # energy curtain. Every decorative part is backed by collision shell.
        frame('reveal_liner', aperture, arch(1.005, 3.105, .40),
              BACK_X+.015, WALL_X+.025, 'facility_recess', .004)

        shield_outline = arch(.998, 3.096, .40)
        points = [point(u, SHIELD_X, z+.008 if z == FLOOR_Z else z)
                  for u,z in shield_outline]
        # Y/Z face: positive X normal on blue, negative X normal on red.
        winding = tuple(range(len(points))) if side > 0 else tuple(reversed(range(len(points))))
        obj = mesh_object('facility_lift_'+label+'_walkthrough_teleporter', points, [winding], [portal])
        obj['mjolnir_pcg_policy'] = 'NONE'
        obj['noncolliding_portal'] = True
        obj['balcony_lift_channel'] = 2 if side < 0 else 3

        # Two small cyan apertures sit 2 mm proud of their metal backing.
        for edge in (-1, 1):
            u = edge*1.16
            lamp('lift_'+label+'_jamb_lens',
                 [point(u-.035, WALL_X+.107, 1.15), point(u+.035, WALL_X+.107, 1.15),
                  point(u+.035, WALL_X+.107, 2.55), point(u-.035, WALL_X+.107, 2.55)],
                 85, (side, 0, 0), (.07, 1.40), (.70, .92, 1))

    return wall
