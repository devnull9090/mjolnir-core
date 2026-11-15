"""A complete, layered Forerunner front elevation, before the root's warps.

Call add_facade(api) with mesh/prism/box/mats helpers. Every created object's
name begins facade/ so the root's inclined-front and height transforms apply
consistently. There are no Blender imports, operators or execution side effects.
Main clear opening: 26 m floor, 18.2 m ceiling, z .2..9.0.
Side clear openings: centers +/-33 m, 8 m floor, 5.6 m ceiling, z .2..5.2.
"""

from math import hypot


class _Batch:
    def __init__(self):
        self.verts, self.faces = [], []

    def solid(self, poly, offset):
        start, n = len(self.verts), len(poly)
        self.verts.extend(poly)
        self.verts.extend(tuple(v[i] + offset[i] for i in range(3)) for v in poly)
        self.faces.extend([tuple(start + i for i in reversed(range(n))),
                           tuple(start + n + i for i in range(n))])
        self.faces.extend((start + i, start + (i + 1) % n,
                           start + n + (i + 1) % n, start + n + i) for i in range(n))

    def ribbon(self, a, b, width, y, depth):
        dx, dz = b[0] - a[0], b[1] - a[1]
        length = hypot(dx, dz)
        if length < 1e-8:
            return
        nx, nz = -dz / length * width * .5, dx / length * width * .5
        points = [(a[0] - nx, a[1] - nz), (b[0] - nx, b[1] - nz),
                  (b[0] + nx, b[1] + nz), (a[0] + nx, a[1] + nz)]
        self.solid([(x, y, z) for x, z in points], (0, depth, 0))

    def path(self, points, width, y, depth):
        for a, b in zip(points, points[1:]):
            self.ribbon(a, b, width, y, depth)

    def glyphs(self, points, width, pitch, y):
        """One continuous architectural vocabulary: alternating stepped keys."""
        for a, b in zip(points, points[1:]):
            dx, dz = b[0] - a[0], b[1] - a[1]
            length = hypot(dx, dz)
            ux, uz = dx / length, dz / length
            vx, vz = -uz, ux
            count = max(1, int((length - .2) / pitch))
            spacing = (length - .2) / count
            for i in range(count):
                centre = .1 + (i + .5) * spacing
                handed = 1 if i % 2 == 0 else -1
                shape = [(-.34, -.5), (-.34, .5), (-.08, .5),
                         (-.08, -.18), (.16, -.18), (.16, .5), (.34, .5)]
                path = [(a[0] + (centre + gx * spacing) * ux + gz * width * handed * vx,
                         a[1] + (centre + gx * spacing) * uz + gz * width * handed * vz)
                        for gx, gz in shape]
                self.path(path, width * .105, y, .025)


def add_facade(api):
    """Build the full front as closed frame segments with three real openings.

    Return all created objects. No material or geometry is placed across the
    openings. The main gate's outer profile is 40 m wide; broad angular flank
    fields wrap around the side portals rather than becoming separate plaques.
    """
    create, prism, mats = api['mesh'], api['prism'], api['mats']
    objects, batches = [], {}

    def solid(name, points, y_front, y_back, mat='alloy', bevel=.09):
        obj = prism('facade/' + name, points, y_front, y_back, mats[mat], bevel=bevel)
        objects.append(obj)
        return obj

    def band(name, inner, outer, y_inner, y_outer, back, mat, bevel=.09):
        # Each segment is its own closed, deep sculptural volume. The two front
        # planes form real chamfers; there is never a polygon spanning the hole.
        for i in range(len(inner) - 1):
            x0, z0 = inner[i]; x1, z1 = inner[i + 1]
            x2, z2 = outer[i + 1]; x3, z3 = outer[i]
            verts = [(x0, y_inner, z0), (x1, y_inner, z1),
                     (x2, y_outer, z2), (x3, y_outer, z3),
                     (x0, back, z0), (x1, back, z1),
                     (x2, back, z2), (x3, back, z3)]
            faces = [(0, 3, 2), (0, 2, 1), (4, 5, 6, 7),
                     (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]
            objects.append(create('facade/' + name + '-' + str(i), verts, faces,
                                  mats[mat], bevel=bevel))

    def batch(name, material, bevel=.012):
        key = (name, material, bevel)
        if key not in batches:
            batches[key] = _Batch()
        return batches[key]

    main_inner = [(-13, .2), (-13, 3), (-9.1, 9), (9.1, 9), (13, 3), (13, .2)]
    rebate_inner = [(-13.35, .2), (-13.35, 3.1), (-9.30, 9.35),
                    (9.30, 9.35), (13.35, 3.1), (13.35, .2)]
    rebate_outer = [(-14.15, .2), (-14.15, 3.35), (-9.82, 10.05),
                    (9.82, 10.05), (14.15, 3.35), (14.15, .2)]
    main_outer = [(-20, .2), (-20, 3.2), (-13, 11.2),
                  (13, 11.2), (20, 3.2), (20, .2)]
    band('gateway/deep inner splay', main_inner, rebate_inner,
         -25.85, -26.95, -20, 'dark', .075)
    band('gateway/engraving recess', rebate_inner, rebate_outer,
         -27.04, -27.04, -20, 'dark', .045)
    band('gateway/monolithic armor', rebate_outer, main_outer,
         -27.30, -27.45, -20, 'alloy', .14)

    # Continuous inset trim, with a complete border visible at distant scale and
    # modeled angular glyphs that resolve on close approach.
    main_trim_path = [(-13.75, .62), (-13.75, 3.23), (-9.56, 9.70),
                      (9.56, 9.70), (13.75, 3.23), (13.75, .62)]
    border = batch('trim/main machined rails', 'trim', .018)
    glyphs = batch('trim/main continuous stepped glyphs', 'alloy', .006)
    for a, b in zip(main_trim_path, main_trim_path[1:]):
        dx, dz = b[0] - a[0], b[1] - a[1]
        length = hypot(dx, dz)
        for sign in (-1, 1):
            off = .29 * sign
            shift = (-dz / length * off, dx / length * off)
            border.ribbon((a[0] + shift[0], a[1] + shift[1]),
                          (b[0] + shift[0], b[1] + shift[1]), .065, -27.16, .045)
    glyphs.glyphs(main_trim_path, .36, .73, -27.115)

    team = batch('energy/team incisions', 'team', .012)
    team_wells = batch('energy/deep channel wells', 'dark', .025)
    flange_seams = batch('armor/purposeful stepped joints', 'dark', .012)
    field_outlines = batch('flanks/raised contour armor', 'alloy', .06)
    field_grooves = batch('flanks/secondary deep grooves', 'dark', .025)
    field_machining = batch('flanks/secondary inset ribs', 'black', .012)
    side_rails = batch('trim/gallery edge rails', 'trim', .012)
    side_glyphs = batch('trim/gallery continuous glyphs', 'alloy', .004)

    for sign, label in ((-1, 'L'), (1, 'R')):
        def mirrored(points):
            return [(sign * x, z) for x, z in points]

        # Broad gateway faces have articulated armor feet and a stepped diagonal
        # inner shoulder. They read as a continuous load-bearing mass.
        solid('gateway/' + label + ' rooted foot',
              mirrored([(14.3, .2), (20, .2), (20, 2.0), (17.9, 3.25), (14.9, 3.25)]),
              -27.85, -22.0, bevel=.13)
        solid('gateway/' + label + ' upper diagonal plate',
              mirrored([(16.2, 4.05), (18.70, 4.05), (13, 11.2),
                        (11.5, 10.95), (15.4, 5.30)]), -27.65, -26.8, bevel=.10)
        flange_seams.path(mirrored([(15.55, 3.75), (17.65, 3.75), (18.95, 2.85)]),
                          .09, -27.92, .035)
        for a, b in [((15.13, .85), (15.13, 2.35)),
                     ((16.10, 5.10), (14.85, 6.95))]:
            pa, pb = mirrored([a, b])
            team_wells.ribbon(pa, pb, .31, -27.79, .075)
            team.ribbon(pa, pb, .105, -27.86, .035)

        # The flank shell is divided around the side portal, not filled by a
        # block with a dark doorway painted on it. Front and rear remain open.
        solid('flanks/' + label + ' inner structural pier',
              mirrored([(20, .2), (29, .2), (29, 2.4), (30.2, 5.2),
                        (30.2, 11.2), (13, 11.2), (20, 3.2)]), -25.80, -20, bevel=.12)
        solid('flanks/' + label + ' outer structural pier',
              mirrored([(37, .2), (43, .2), (43, 11.2),
                        (35.8, 11.2), (35.8, 5.2), (37, 2.4)]), -25.80, -20, bevel=.12)
        solid('flanks/' + label + ' structural portal header',
              mirrored([(30.2, 5.2), (35.8, 5.2), (35.8, 11.2), (30.2, 11.2)]),
              -25.80, -20, bevel=.10)

        # One integrated angular recess spans from central buttress to outer
        # wing, then wraps over the small portal. It is intentionally not a plaque.
        contour = [(20.75, 2.2), (27.4, 2.2), (27.8, 3.4),
                   (29.5, 6.5), (36.5, 6.5), (37.5, 4.5),
                   (41.0, 4.5), (40.0, 10.2), (16.9, 10.2)]
        solid('flanks/' + label + ' continuous recessed field', mirrored(contour),
              -26.24, -25.72, 'dark', .065)
        field_outlines.path(mirrored(contour + [contour[0]]), .43, -26.88, .66)

        # Chunkier nested contours are sunk behind the framing armor. Their
        # changes of direction track the side portal instead of floating alone.
        for dz in (0,):
            path = [(21.3, 4.15 + dz), (25.4, 4.15 + dz),
                    (28.7, 7.55 + dz), (35.6, 7.55 + dz), (37.3, 9.0 + dz)]
            field_grooves.path(mirrored(path), .46, -26.45, .35)
            field_machining.path(mirrored(path), .16, -26.12, .035)
        # A long secondary edge catches light and makes the inset broad at range.
        upper_run=mirrored([(19.5, 8.94), (25.4, 8.94), (26.2, 9.6), (35.7, 9.6)])
        field_grooves.path(upper_run,.27,-26.45,.35)
        field_machining.path(upper_run,.08,-26.12,.035)

        # Heavy outer diagonal ties the entire face into the roof/ramp wing.
        solid('flanks/' + label + ' full height diagonal buttress',
              mirrored([(38.6, .2), (43, .2), (43, 2.2),
                        (40.2, 11.2), (37.2, 11.2), (39.9, 3.4)]),
              -27.45, -20.0, bevel=.16)
        solid('flanks/' + label + ' buttress armored toe',
              mirrored([(39.0, .2), (43, .2), (43, 1.9), (41.0, 3.0), (39.1, 2.6)]),
              -27.85, -24.0, bevel=.14)
        flange_seams.path(mirrored([(39.5, 3.15), (41.2, 3.15), (42.1, 2.5)]),
                          .10, -27.94, .04)

        # Segmented caps replace a continuous straight roof lip with shoulders
        # that align to the gateway and outer structural diagonals.
        for suffix, polygon, depth in [
                ('inner', [(13.1, 10.65), (22.25, 10.65), (23.1, 11.2), (13.0, 11.2)], -27.02),
                ('middle', [(22.6, 10.2), (35.6, 10.2), (36.4, 11.2), (23.4, 11.2)], -26.72),
                ('outer', [(35.9, 10.2), (39.2, 8.75), (42.2, 9.0), (40.2, 11.2), (36.5, 11.2)], -27.0)]:
            solid('roof junction/' + label + ' ' + suffix + ' armor cap', mirrored(polygon),
                  depth, -20.0, bevel=.10)

        side_inner = [(29, .2), (29, 2.4), (30.2, 5.2),
                      (35.8, 5.2), (37, 2.4), (37, .2)]
        side_rebate = [(28.65, .2), (28.65, 2.5), (29.95, 5.55),
                       (36.05, 5.55), (37.35, 2.5), (37.35, .2)]
        side_outer = [(27.4, .2), (27.4, 2.7), (29.3, 6.4),
                      (36.7, 6.4), (38.6, 2.7), (38.6, .2)]
        band('gallery/' + label + ' deep chamfer', mirrored(side_inner), mirrored(side_rebate),
             -25.7, -26.95, -20, 'dark', .065)
        band('gallery/' + label + ' integrated armor', mirrored(side_rebate), mirrored(side_outer),
             -27.12, -27.32, -20, 'alloy', .105)

        small_trim = [(28.79, .65), (28.79, 2.47), (30.03, 5.42),
                      (35.97, 5.42), (37.21, 2.47), (37.21, .65)]
        small_trim = mirrored(small_trim)
        side_rails.path(small_trim, .055, -27.025, .03)
        side_glyphs.glyphs(small_trim, .115, .43, -27.07)
        for suffix, foot in [('inner', [(27.0, .2), (28.9, .2), (28.9, 1.35), (27.65, 1.85)]),
                             ('outer', [(37.1, .2), (39.0, .2), (38.35, 1.85), (37.1, 1.35)])]:
            solid('gallery/' + label + ' ' + suffix + ' foot', mirrored(foot),
                  -27.65, -23.2, bevel=.095)

    for (name, mat, bevel), data in batches.items():
        if data.verts:
            objects.append(create('facade/' + name, data.verts, data.faces, mats[mat], bevel=bevel))
    return objects
