"""Sculpted, inward-swept Forerunner roof fins for the Blender base study.

``add_fins(api)`` returns created objects. Required entries: mesh, prism, mats.
No bpy calls, scene mutation outside the supplied creation helpers, or imports
from other modules. Local metres: front -Y, up +Z. Both footprints remain in
abs(X)=20..36, Y=15..23, Z=11.2..26.5, clear of the central mount envelope.
"""

from math import hypot


class _StripBatch:
    def __init__(self):
        self.verts, self.faces = [], []

    def solid(self, poly, offset):
        n, start = len(poly), len(self.verts)
        self.verts.extend(poly)
        self.verts.extend(tuple(v[i] + offset[i] for i in range(3)) for v in poly)
        self.faces.extend([tuple(start + i for i in reversed(range(n))),
                           tuple(start + n + i for i in range(n))])
        self.faces.extend((start + i, start + (i + 1) % n,
                           start + n + (i + 1) % n, start + n + i) for i in range(n))

    def line(self, a, b, width, y, depth, sign):
        dx, dz = b[0] - a[0], b[1] - a[1]
        length = hypot(dx, dz)
        nx, nz = -dz / length * width * .5, dx / length * width * .5
        self.solid([(sign * x, y, z) for x, z in
                    [(a[0] - nx, a[1] - nz), (b[0] - nx, b[1] - nz),
                     (b[0] + nx, b[1] + nz), (a[0] + nx, a[1] + nz)]],
                   (0, depth, 0))

    def path(self, points, width, y, depth, sign):
        for a, b in zip(points, points[1:]):
            self.line(a, b, width, y, depth, sign)


def add_fins(api):
    """Create two mirrored fins with structural depth and restrained detail.

    Main volumes use three overlapping shoulder planes, a full rear spine,
    a deeply set blue-gray face and articulated foot blocks. Team accents use
    the caller's material, so master clones can swap it without changing mesh.
    """
    create_mesh, create_prism = api['mesh'], api['prism']
    mats = api['mats']
    prefix = api.get('prefix', 'fin')
    objects = []

    for sign, side in ((-1, 'L'), (1, 'R')):
        stem = prefix.rstrip('/') + '/sculpted_' + side + '/'

        def profile(name, points, y0, y1, material='alloy', bevel=.08):
            obj = create_prism(stem + name, [(sign * x, z) for x, z in points],
                               y0, y1, mats[material], bevel=bevel)
            objects.append(obj)
            return obj

        # Structural volume has a narrow inward crown and a genuinely broad
        # triangular foot. Its lower and upper sloping faces change direction.
        profile('swept structural core',
                [(20.7, 11.2), (33.2, 11.2), (30.2, 18.8),
                 (27.4, 21.2), (26, 26.5), (22, 26.5)], 16.7, 22.6, bevel=.13)

        inset = [(22, 12.3), (29.6, 12.3), (28.15, 17.5),
                 (25.95, 20), (24.6, 25.55), (23.15, 25.55)]
        profile('deep front inset', inset, 16.48, 16.72, 'dark', .035)
        profile('rear inset', [(22.2, 12.6), (30.95, 12.6), (28.9, 18.4),
                               (26.25, 20.9), (25.35, 25.4), (23.15, 25.4)],
                22.60, 22.67, 'dark', .035)

        # Three offset inclined support planes provide shadowed overlaps.
        profile('lower splayed buttress',
                [(27.8, 11.2), (36, 11.2), (35.1, 13.15),
                 (31.4, 17.2), (29.7, 16.45)], 15.10, 22.3, bevel=.13)
        profile('middle interlocking shoulder',
                [(29.65, 16.45), (31.40, 17.20), (28.95, 20.25),
                 (27.05, 21.0), (26.05, 19.45)], 15.55, 22.7, bevel=.10)
        profile('upper inclined blade',
                [(26.05, 19.45), (27.05, 21), (26, 26.5), (24.1, 26.5)],
                15.95, 22.7, bevel=.085)

        profile('inner blade', [(20, 11.2), (21.25, 11.2), (23.02, 26.3),
                                (22, 26.5), (21.2, 18)], 15.30, 23.0, bevel=.10)
        profile('outer rear support',
                [(32.4, 11.2), (36, 11.2), (35.5, 13.5),
                 (31.6, 20), (27, 25.3), (25.7, 25.4), (29.9, 19)],
                20.85, 23.0, bevel=.10)

        # Roots and a forward crown brow make the fin feel assembled into the
        # architecture; they are volumes, not decals drawn on a flat obelisk.
        profile('inner armored foot',
                [(20, 11.2), (24.4, 11.2), (23.45, 12.95), (20.55, 13.20)],
                15.0, 22.8, bevel=.11)
        profile('outer armored foot',
                [(29.5, 11.2), (36, 11.2), (35.25, 12.7), (31.15, 13.05)],
                15.0, 23.0, bevel=.12)
        profile('four metre crown',
                [(22, 25.72), (26, 25.72), (26, 26.5), (22, 26.5)],
                15.0, 23.0, bevel=.08)

        # The stepped support edges carry a narrow dark reveal rather than
        # arbitrary greeble. The front face remains mostly quiet metal.
        reveals, edging = _StripBatch(), _StripBatch()
        reveals.path([(28.8, 12.0), (30.55, 15.85), (30.05, 16.35)],
                     .20, 15.025, .040, sign)
        reveals.path([(27.15, 19.8), (28.4, 19.5), (30.5, 17.15)],
                     .17, 15.475, .035, sign)
        reveals.path([(26.22, 20.35), (26.0, 22.1), (25.45, 25.4)],
                     .18, 15.875, .035, sign)
        edging.path(inset + [inset[0]], .085, 16.385, .045, sign)

        # Two line lengths give readable team identity without painting the fin.
        light_housing, team = _StripBatch(), _StripBatch()
        for a, b, y in [((23.32, 15.05), (24.03, 20.1), 16.29),
                        ((29.75, 17.35), (28.32, 19.05), 15.40)]:
            light_housing.line(a, b, .28, y, .05, sign)
            team.line(a, b, .085, y - .045, .025, sign)

        # A restrained original stepped inset motif, subordinate to structure.
        engraving = _StripBatch()
        engraving.path([(25.05, 13.70), (25.05, 14.7), (26.05, 15.6),
                        (25.65, 17.2), (24.95, 17.9)], .055, 16.36, .025, sign)
        engraving.path([(25.48, 13.70), (25.48, 14.5), (26.50, 15.4),
                        (26.1, 16.8)], .055, 16.36, .025, sign)

        for name, batch, material, bevel in [
                ('stepped shadow reveals', reveals, 'dark', .008),
                ('inset machined outline', edging, 'trim', .012),
                ('energy channel housing', light_housing, 'dark', .018),
                ('team energy channels', team, 'team', .008),
                ('inset geometric engraving', engraving, 'trim', .008)]:
            objects.append(create_mesh(stem + name, batch.verts, batch.faces,
                                       mats[material], bevel=bevel))

    return objects
