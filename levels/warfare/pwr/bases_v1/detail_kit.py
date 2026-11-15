"""Restrained CE-inspired detailing for the Blender-only base study.

Call ``add_details(api)`` after the structural shell.  ``api['mesh']`` has
signature (name, vertices, faces, material, bevel=.05).  All coordinates are
metres, local to the base.  The return value is the created object list.
Geometry is batched by material and bevel width, not one object per glyph.
No bpy imports, operators, file writes, scene changes or external dependencies.
"""

from math import hypot, sqrt


class _Batch:
    def __init__(self):
        self.vertices = []
        self.faces = []

    def solid(self, polygon, offset):
        """Extrude an ordered planar polygon; all surfaces remain manifold."""
        polygon = list(polygon)
        edge_a = [polygon[1][i] - polygon[0][i] for i in range(3)]
        edge_b = [polygon[2][i] - polygon[0][i] for i in range(3)]
        normal = (edge_a[1] * edge_b[2] - edge_a[2] * edge_b[1],
                  edge_a[2] * edge_b[0] - edge_a[0] * edge_b[2],
                  edge_a[0] * edge_b[1] - edge_a[1] * edge_b[0])
        if sum(normal[i] * offset[i] for i in range(3)) < 0:
            polygon.reverse()
        start, count = len(self.vertices), len(polygon)
        self.vertices.extend(tuple(p) for p in polygon)
        self.vertices.extend(tuple(p[i] + offset[i] for i in range(3)) for p in polygon)
        self.faces.append(tuple(start + i for i in reversed(range(count))))
        self.faces.append(tuple(start + count + i for i in range(count)))
        for i in range(count):
            j = (i + 1) % count
            self.faces.append((start + i, start + j, start + count + j, start + count + i))

    def xz(self, points, y, depth):
        self.solid([(x, y, z) for x, z in points], (0, depth, 0))

    def plate(self, center, u, v, half_u, half_v, normal, depth):
        corners = []
        for a, b in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
            corners.append(tuple(center[i] + a * half_u * u[i] + b * half_v * v[i] for i in range(3)))
        self.solid(corners, tuple(depth * n for n in normal))


def _ribbon(batch, a, b, width, y, depth):
    dx, dz = b[0] - a[0], b[1] - a[1]
    length = hypot(dx, dz)
    if length < 1e-8:
        return
    nx, nz = -dz / length * width * .5, dx / length * width * .5
    batch.xz([(a[0] - nx, a[1] - nz), (b[0] - nx, b[1] - nz),
              (b[0] + nx, b[1] + nz), (a[0] + nx, a[1] + nz)], y, depth)


def _path(batch, points, width, y, depth):
    for a, b in zip(points, points[1:]):
        _ribbon(batch, a, b, width, y, depth)


def _glyph_run(batch, a, b, y, depth, pitch=.72, glyph_height=.29):
    """Original repeating stepped glyph, aligned to the frame, not random noise."""
    dx, dz = b[0] - a[0], b[1] - a[1]
    length = hypot(dx, dz)
    ux, uz = dx / length, dz / length
    vx, vz = -uz, ux
    repeats = max(1, int((length - .5) / pitch))
    actual_pitch = (length - .5) / repeats
    # Open alternating stepped keys create a coherent continuous trim motif.
    for index in range(repeats):
        t = .25 + (index + .5) * actual_pitch
        handed = 1 if index % 2 == 0 else -1
        glyph = [(-.26, -.5), (-.26, .5), (-.04, .5), (-.04, -.13),
                 (.15, -.13), (.15, .5), (.27, .5)]
        pts = [(a[0] + (t + gx) * ux + gz * glyph_height * handed * vx,
                a[1] + (t + gx) * uz + gz * glyph_height * handed * vz) for gx, gz in glyph]
        _path(batch, pts, .035, y, depth)


def add_details(api):
    """Add portal trim, inset flank motifs and unobstructed tunnel light strips.

    Optional ``portal_front_y`` and ``portal_rear_y`` allow the caller to align
    these shallow surface layers to its actual structural portal face planes.
    Required material keys: alloy, dark, trim, team, white, floor.
    The central rooftop mount and the vehicle-clearance volume are untouched.
    """
    mats, create = api['mats'], api['mesh']
    prefix = api.get('prefix', 'Base')
    front_y = api.get('portal_front_y', -26.0)
    rear_y = api.get('portal_rear_y', 24.0)
    batches = {}

    def layer(name, material, bevel=.018):
        key = (name, material, bevel)
        if key not in batches:
            batches[key] = _Batch()
        return batches[key]

    trim = layer('Portal_Trim_Rails', 'trim', .018)
    recess = layer('Portal_Trim_Recess', 'dark', .012)
    glyphs = layer('Portal_Stepped_Glyphs', 'alloy', .005)
    team = layer('Portal_Team_Identifiers', 'team', .012)

    # The dark trim lies on a silver structural jamb, never inside the hole.
    # The long sloping strip follows the portal's 1:2 rise, echoing CE edging.
    for face_y, outward in ((front_y, -1), (rear_y, 1)):
        recess_y = face_y + outward * .025
        trim_y = face_y + outward * .055
        glyph_y = face_y + outward * .090
        extrusion = outward * .025
        segments = [((-10.78, .65), (-10.78, 3.18)),
                    ((-10.78, 3.18), (-7.56, 9.62)),
                    ((-7.56, 9.62), (7.56, 9.62)),
                    ((7.56, 9.62), (10.78, 3.18)),
                    ((10.78, 3.18), (10.78, .65))]
        for a, b in segments:
            _ribbon(recess, a, b, .58, recess_y, extrusion)
            dx, dz = b[0] - a[0], b[1] - a[1]
            length = hypot(dx, dz)
            nx, nz = -dz / length, dx / length
            for side in (-1, 1):
                shift = .27 * side
                _ribbon(trim, (a[0] + nx * shift, a[1] + nz * shift),
                        (b[0] + nx * shift, b[1] + nz * shift), .055, trim_y, extrusion)
            _glyph_run(glyphs, a, b, glyph_y, outward * .015)

        for sign in (-1, 1):
            # Two narrow colored slots, not a broad team-painted facade.
            for a, b in (((11.55, .65), (11.55, 1.8)), ((9.50, 5.10), (8.92, 6.26))):
                pa, pb = (sign * a[0], a[1]), (sign * b[0], b[1])
                _ribbon(recess, pa, pb, .30, recess_y, extrusion)
                _ribbon(team, pa, pb, .10, glyph_y, outward * .018)

    # Front flank inset panels echo the image target's long diagonal recesses.
    # Root's shoulder recess is a skew quadrilateral, y=-25.15, with top
    # corners at x12.5/19.7,z9 and lower corners at x15.6/21.4,z4.
    # These shallow layers sit immediately ahead of that actual surface.
    panels = layer('Flank_Inset_Fields', 'dark', .04)
    borders = layer('Flank_Contour_Trim', 'trim', .012)
    panel_glyphs = layer('Flank_Stepped_Motifs', 'alloy', .008)
    for sign in (-1, 1):
        contour = [(15.78, 4.25), (21.05, 4.25), (19.52, 8.75),
                   (12.98, 8.75)]
        contour = [(sign * x, z) for x, z in contour]
        panels.xz(contour, -25.18, .02)
        for a, b in zip(contour, contour[1:] + contour[:1]):
            _ribbon(borders, a, b, .08, -25.22, .025)
        for offset in (0, .40):
            points = [(15.68, 5.05 + offset), (18.50, 5.05 + offset),
                      (17.70, 6.50 + offset), (14.90, 6.50 + offset),
                      (14.15, 7.95 + offset), (17.70, 7.95 + offset)]
            _path(panel_glyphs, [(sign * x, z) for x, z in points], .065, -25.26, .02)
        _ribbon(team, (sign * 20.28, 5.12), (sign * 19.54, 7.15), .10, -25.30, .02)

    # Housings run in bays between the structural tunnel ribs.  None projects
    # into the protected x[-6.5,6.5], z[.2,8.7] drive-through volume.
    wall_panels = layer('Tunnel_Recessed_Wall_Panels', 'dark', .025)
    housings = layer('Tunnel_Light_Housings', 'trim', .025)
    lamps = layer('Tunnel_White_Light_Slits', 'white', .008)
    joint_trim = layer('Tunnel_Panel_Joints', 'alloy', .01)
    floor_guides = layer('Tunnel_Edge_Guides', 'trim', .01)

    for sign in (-1, 1):
        inward = (-sign, 0, 0)
        # Local Y/Z surfaces are completely outside the vehicle envelope.
        # Omit the y=9 bay: the master intentionally opens its wall at y=1..16
        # for lateral circulation into the refuge galleries.
        for bay_y in (-21, -11, -1, 19):
            wall_panels.plate((sign * 10.48, bay_y, 1.6), (0, 1, 0), (0, 0, sign),
                              2.0, 1.0, inward, .035)
            housings.plate((sign * 10.40, bay_y, 1.60), (0, 1, 0), (0, 0, sign),
                           .22, .91, inward, .10)
            lamps.plate((sign * 10.28, bay_y, 1.63), (0, 1, 0), (0, 0, sign),
                        .055, .69, inward, .035)
            # A short lit sill helps reveal the depth of the covered tunnel.
            housings.plate((sign * 10.40, bay_y + 1.25, .55), (0, 1, 0), (0, 0, sign),
                           .55, .16, inward, .08)
            lamps.plate((sign * 10.30, bay_y + 1.25, .55), (0, 1, 0), (0, 0, sign),
                        .41, .045, inward, .025)
            for side_y in (-1.8, 1.8):
                joint_trim.plate((sign * 10.42, bay_y + side_y, 1.55), (0, 1, 0), (0, 0, sign),
                                 .027, .79, inward, .025)

            # Master lining runs from x10.5,z3.2 to x7.3,z9.5.
            slope_length = sqrt(3.2 ** 2 + 6.3 ** 2)
            tangent = (-sign * 3.2 / slope_length, 0, 6.3 / slope_length)
            normal = (-sign * 6.3 / slope_length, 0, -3.2 / slope_length)
            center = (sign * (10.5 - 4.0 * 3.2 / 6.3), bay_y, 7.2)
            housings.plate(center, (0, sign, 0), tangent, .21, .80, normal, .055)
            light_center = tuple(center[i] + .07 * normal[i] for i in range(3))
            lamps.plate(light_center, (0, sign, 0), tangent, .065, .64, normal, .018)

            floor_guides.plate((sign * 9.12, bay_y, .23), (1, 0, 0), (0, 1, 0),
                               .045, 3.65, (0, 0, 1), .025)

    objects = []
    for (name, material, bevel), batch in batches.items():
        if batch.vertices:
            obj = create(prefix + '_' + name, batch.vertices, batch.faces, mats[material], bevel=bevel)
            objects.append(obj)
    return objects
