"""Green citadel rear architecture, authored before elevation and global scale.

Call add_details(api), supplying mesh/prism/mats. Coordinates already include
the green base's world Y=150 offset. All objects begin citadel/. The source
region abs(X)<13, Z=0..9 remains empty, and no additions reach Y<174.
No Blender calls or import side effects.
"""

from math import hypot


class _Batch:
    def __init__(self):
        self.verts, self.faces = [], []

    def ribbon(self, a, b, width, y, depth):
        dx, dz = b[0] - a[0], b[1] - a[1]
        length = hypot(dx, dz)
        if length < 1e-8:
            return
        nx, nz = -dz / length * width / 2, dx / length * width / 2
        polygon = [(a[0] - nx, y, a[1] - nz), (b[0] - nx, y, b[1] - nz),
                   (b[0] + nx, y, b[1] + nz), (a[0] + nx, y, a[1] + nz)]
        start = len(self.verts)
        self.verts.extend(polygon)
        self.verts.extend((x, yy + depth, z) for x, yy, z in polygon)
        self.faces.extend([tuple(start + i for i in (3, 2, 1, 0)),
                           tuple(start + i for i in (4, 5, 6, 7))])
        self.faces.extend((start + i, start + (i + 1) % 4,
                           start + (i + 1) % 4 + 4, start + i + 4) for i in range(4))

    def path(self, points, width, y, depth):
        for a, b in zip(points, points[1:]):
            self.ribbon(a, b, width, y, depth)

    def glyphs(self, points, y):
        for a, b in zip(points, points[1:]):
            dx, dz = b[0] - a[0], b[1] - a[1]
            length = hypot(dx, dz)
            ux, uz = dx / length, dz / length
            count = max(1, int(length / .70))
            pitch = length / count
            for index in range(count):
                centre = pitch * (index + .5)
                flip = 1 if index % 2 else -1
                shape = [(-.25, -.14), (-.25, .14), (-.06, .14),
                         (-.06, -.04), (.13, -.04), (.13, .14), (.25, .14)]
                pts = [(a[0] + (centre + x) * ux - z * flip * uz,
                        a[1] + (centre + x) * uz + z * flip * ux) for x, z in shape]
                self.path(pts, .035, y, .025)


def add_details(api):
    """Return a compact collection of sculpted rear details and an open frame.

    Rear opening is 34 m wide at ground and 26.4 m wide at z=9.2, intentionally
    clearing the complete requested 26 x 9 m rectangular through-path. The
    supplied team material determines the green accent color.
    """
    create, prism, mats = api['mesh'], api['prism'], api['mats']
    objects, batches = [], {}

    def solid(name, points, y0, y1, material='alloy', bevel=.10):
        ob = prism('citadel/' + name, points, y0, y1, mats[material], bevel=bevel)
        objects.append(ob)
        return ob

    def batch(name, material, bevel=.015):
        key = (name, material, bevel)
        if key not in batches:
            batches[key] = _Batch()
        return batches[key]

    contour = batch('pier machined contour borders', 'alloy', .025)
    seams = batch('stepped inset machining', 'trim', .018)
    wells = batch('recessed energy wells', 'dark', .025)
    energy = batch('green team energy incisions', 'team', .009)
    glyphs = batch('rear continuous Forerunner engraving', 'trim', .005)

    for sign, side in ((-1, 'L'), (1, 'R')):
        def mirror(points):
            return [(sign * x, z) for x, z in points]

        # The old rear pier becomes a rooted, crowned, three-plane structure.
        solid(side + ' observation pier armored foot',
              mirror([(37.5, .2), (44.8, .2), (44.4, 1.9),
                      (42.9, 3.2), (38.2, 2.8)]), 187.4, 191.0, bevel=.15)
        solid(side + ' observation pier sloped crown',
              mirror([(36.7, 15.0), (41.7, 15.0), (41.35, 16.5),
                      (37.2, 16.5)]), 174.8, 190.9, bevel=.15)
        lower = [(39.1, 2.85), (42.65, 2.85), (42.1, 7.4),
                 (41.0, 8.25), (38.65, 8.25)]
        upper = [(38.55, 8.65), (41.75, 8.65), (40.55, 15.10),
                 (38.05, 15.10), (37.9, 13.3)]
        solid(side + ' pier lower angular recess', mirror(lower), 190.02, 190.27, 'dark', .045)
        solid(side + ' pier upper angular recess', mirror(upper), 190.02, 190.27, 'dark', .045)
        solid(side + ' pier outer stepped blade',
              mirror([(42.6, 2.6), (43.4, 3.0), (41.9, 9.3),
                      (40.8, 15.5), (40.0, 15.5), (41.0, 8.6)]),
              189.8, 190.75, bevel=.085)
        solid(side + ' pier inner blade',
              mirror([(37.8, 2.7), (38.65, 2.7), (37.95, 15.4), (37.25, 15.4)]),
              189.9, 190.70, bevel=.075)
        for polygon in (lower, upper):
            contour.path(mirror(polygon + [polygon[0]]), .17, 190.28, .25)
        seams.path(mirror([(39.75, 3.55), (40.95, 3.55), (40.50, 6.35),
                           (39.6, 7.15)]), .065, 190.30, .045)
        seams.path(mirror([(38.8, 9.0), (39.5, 9.8), (39.15, 13.9)]),
                   .065, 190.30, .045)
        for a, b in [((40.70, 4.1), (40.25, 6.4)), ((39.95, 9.7), (39.45, 13.9))]:
            aa, bb = mirror([a, b])
            wells.ribbon(aa, bb, .25, 190.31, .065)
            energy.ribbon(aa, bb, .075, 190.39, .025)

        # A deep stepped bridge shoulder joins the new gate to the observation
        # piers. Its recessed frieze is bounded by angular structural masses.
        solid(side + ' rear bridge armored spandrel',
              mirror([(21.0, 9.30), (36.5, 10.05), (38.0, 11.2),
                      (21.5, 11.2)]), 185.9, 189.20, bevel=.13)
        field = [(23.0, 9.8), (35.8, 10.40), (36.4, 10.87), (23.2, 10.87)]
        solid(side + ' rear bridge recessed frieze', mirror(field), 189.22, 189.28, 'dark', .025)
        seams.path(mirror([(23.65, 10.18), (29.0, 10.4), (30.0, 10.7), (35.3, 10.7)]),
                   .07, 189.30, .035)
        solid(side + ' rear angular roof cover',
              mirror([(22.0, 11.2), (36.0, 11.2), (35.35, 12.4),
                      (32.0, 13.25), (24.5, 13.25), (22.0, 12.15)]),
              187.35, 189.05, bevel=.105)
        wells.path(mirror([(25.2, 12.35), (30.2, 12.35), (31.3, 12.05)]),
                   .23, 189.08, .05)
        energy.path(mirror([(25.35, 12.35), (29.8, 12.35)]), .075, 189.15, .025)

    # A genuinely open rear arcade presents the same gateway vocabulary as the
    # front, with a larger clear area to preserve the rectangular vehicle route.
    inner = [(-17, .2), (-17, 3), (-13.2, 9.2), (13.2, 9.2), (17, 3), (17, .2)]
    trim_outer = [(-17.65, .2), (-17.65, 3.2), (-13.65, 9.8),
                  (13.65, 9.8), (17.65, 3.2), (17.65, .2)]
    outer = [(-21.5, .2), (-21.5, 3.4), (-15.7, 11.2),
             (15.7, 11.2), (21.5, 3.4), (21.5, .2)]
    for layer, inside, outside, front, material in [
            ('rear gateway deep trim', inner, trim_outer, 190.30, 'dark'),
            ('rear gateway structural armor', trim_outer, outer, 190.68, 'alloy')]:
        for i in range(5):
            solid(layer + '-' + str(i), [inside[i], inside[i + 1], outside[i + 1], outside[i]],
                  186.0, front, material, .11 if material == 'alloy' else .055)
    arch_trim = [(-17.33, .7), (-17.33, 3.1), (-13.43, 9.50),
                 (13.43, 9.50), (17.33, 3.1), (17.33, .7)]
    glyphs.glyphs(arch_trim, 190.35)
    for a, b in zip(arch_trim, arch_trim[1:]):
        dx, dz = b[0] - a[0], b[1] - a[1]
        length = hypot(dx, dz)
        for side in (-1, 1):
            nx, nz = -dz / length * side * .24, dx / length * side * .24
            seams.ribbon((a[0] + nx, a[1] + nz), (b[0] + nx, b[1] + nz),
                         .05, 190.40, .035)
    for sign, side in ((-1, 'L'), (1, 'R')):
        solid(side + ' rear gateway toe',
              [(sign * x, z) for x, z in [(17.8, .2), (22.5, .2),
                                          (21.9, 1.8), (19.8, 2.6), (18.2, 2.6)]],
              187.8, 191.10, bevel=.13)
        wells.ribbon((sign * 18.8, .9), (sign * 18.8, 2.1), .27, 191.12, .045)
        energy.ribbon((sign * 18.8, .98), (sign * 18.8, 2.02), .085, 191.18, .025)

    solid('central angular roof battlement',
          [(-12, 11.2), (-12, 12.2), (-9, 13.1), (-5, 13.1),
           (-3, 12.6), (3, 12.6), (5, 13.1), (9, 13.1), (12, 12.2), (12, 11.2)],
          187.4, 189.20, bevel=.11)
    seams.path([(-10.0, 11.9), (-6.0, 12.45), (-3.0, 12.1),
                (3.0, 12.1), (6.0, 12.45), (10.0, 11.9)], .11, 189.22, .04)

    for (name, material, bevel), data in batches.items():
        objects.append(create('citadel/' + name, data.verts, data.faces, mats[material], bevel=bevel))
    return objects
