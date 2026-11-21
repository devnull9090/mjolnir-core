"""Author the sediment face, exposed willow roots and gravel against the retained outlet shell."""
from pathlib import Path
import hashlib
import json
import sys

import numpy as np
from scipy.spatial import ConvexHull

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "terrain"))
import headwater_dressing as dressing
import outlet_apron as outlet

BASE = dressing.ROOT / "out/pwr/river-apron"
WORK = dressing.ROOT / "out/pwr/river-riparian/cutbank"
SCALE = np.array([100., -100., 100.])
ALONG = np.r_[outlet.FORWARD_XY, 0.]
ACROSS = outlet.RIGHT
UP = np.array([0., 0., 1.])


def unit(vector):
    return vector / np.maximum(np.linalg.norm(vector, axis=-1, keepdims=True), 1e-12)


def save(path, data):
    path.write_text(json.dumps(data, allow_nan=False, separators=(",", ":")))


def build():
    WORK.mkdir(exist_ok=True, parents=True)
    src = BASE / "finish37/surface.json"
    mesh = json.loads(src.read_bytes())
    origin = np.array(mesh["origin_cm"]) / SCALE
    # This 181 x 7 strip is the surveyed .37 crest and contact. The far banks and
    # the foreground channel boulders aren't part of these new render surfaces.
    old = (np.asarray(mesh["positions"][:181 * 7]) / SCALE + origin).reshape(181, 7, 3)
    del mesh
    terrain = dressing.load_heightfield(BASE / "terrain/runtime-master.json")
    rng = np.random.default_rng(400192)
    vertices, colors, uv, faces, kinds = [], [], [], [], []
    tower = {"loam": 0, "root_primaries": 0, "root_branches": 0, "cobbles": 0}
    gravel_heights = []

    def add_vertex(p, color, tc):
        vertices.append(p)
        colors.append(color)
        uv.append(tc)
        return len(vertices) - 1

    def add_face(a, b, c, outward, kind):
        face = (a, b, c)
        p = np.array([vertices[i] for i in face])
        if np.dot(np.cross(p[1] - p[0], p[2] - p[0]), outward) < 0:
            face = (a, c, b)
        faces.append(face)
        kinds.append(kind)

    def profile(s):
        ix = np.clip((s - 13.) * 4., 0., 179.99999)
        i = int(ix)
        return old[i] + (ix - i) * (old[i + 1] - old[i])

    old_support = BASE / "bank/support.npz"
    with np.load(old_support) as native:
        support = native["triangles_m"].copy()
        materials = native["materials"].copy()
    sections = np.linspace(13.,58.,19)
    # Recover the exact existing landward corners to keep the route from the
    # turf continuous. Other recovered slots carry the existing shore rocks.
    native_rows = []
    line = np.array(dressing.read(BASE / "terrain/terrain.geometry.json")["watercourses"][0]["erosion_reach"]["centreline_m"])
    for i,s in enumerate(sections):
        k = min(i,17)*6
        land, crest = (support[k,2],support[k,0]) if i<18 else (support[k,1],support[k+1,1])
        level = float(outlet.surface(crest[:2],line))
        spread = 1.25 + .29*np.sin(s*.62+.8*np.cos(s*.29)) + .17*np.cos(s*.84)
        taper = np.clip(min((s-13.)/3.,(58.-s)/3.),0.,1.)
        bench = crest + ACROSS*(.6 + spread*taper)
        bench_grade = terrain.sample(*bench[:2])
        bench[2] = (1.-taper)*bench_grade + taper*max(bench_grade,level+.19+.055*np.sin(s*1.22))
        foot = bench + ACROSS*(.48+1.25*taper)
        foot[2] = terrain.sample(*foot[:2]) - .155
        native_rows.append(np.array([land,crest,bench,foot]))
    native_rows = np.array(native_rows)
    for i,(near,far) in enumerate(zip(native_rows,native_rows[1:])):
        for j in (1,2):
            # Match the legacy winding and slot order exactly.
            k = i*6+j*2
            support[k] = [near[j+1],far[j],near[j]]
            support[k+1] = [near[j+1],far[j+1],far[j]]
    np.savez_compressed(WORK/"support.npz",triangles_m=support,materials=materials)
    if hashlib.sha256((WORK/"support.npz").read_bytes()).hexdigest() != "f633f129bc9bc1ec17b4554ec3572bbf50bd78efb0aa9239f2363518569d3736":
        raise ValueError("The retained .41 support changed")

    def shelf(s, band, across):
        # Interpolate the actual collision triangle, including its diagonal.
        u=np.clip((s-13.)/2.5,0.,17.999999)
        i=int(u)
        u-=i
        a,b = native_rows[i,band:band+2]
        c,d = native_rows[i+1,band:band+2]
        if u+across<=1.:
            return a+(c-a)*u+(b-a)*across
        return d+(b-d)*(1.-u)+(c-d)*(1.-across)

    def row(s):
        p = profile(s)
        wave = np.sin(s*2.39+.6*np.cos(.7*s))
        ripple = .038*wave + .018*np.sin(6.4*s)
        rim = p[2] - .265*ACROSS - .030*UP
        turf = p[2] + (.225+.055*wave)*ACROSS + (.079+.019*wave)*UP
        lip = p[2] + (.254+.060*wave)*ACROSS - (.042-.020*wave)*UP
        # The projecting sod holds a knobbly root mat above a pocket of damp
        # earth. The forward toe stays aligned with the walkable gravel wedge.
        rind = p[3] + (.038+ripple)*ACROSS - (.052-.027*wave)*UP
        clay = shelf(s,1,.292+.037*wave) - (.098+.035*wave)*UP
        loam = shelf(s,1,.47+.067*wave) + (.026+.027*wave)*UP
        gravel = shelf(s,1,.91+.045*wave) + .024*UP
        toe = shelf(s,2,.26+.058*wave) + (.025+.016*wave)*UP
        foot = shelf(s,2,1.)-.005*UP
        return np.array((rim,turf,lip,rind,clay,loam,gravel,toe,foot))

    # Sample once: the curved face stays the common attachment surface for every fork.
    survey_s = np.linspace(13., 58., 451)
    survey = np.stack([row(s) for s in survey_s])
    ticks = np.array([0.,.105,.178,.275,.385,.515,.710,.910,1.])
    def skin(s, t):
        s = np.clip((s - 13.) * 10., 0., len(survey) - 1.000001)
        i = int(s)
        q = survey[i] + (s - i) * (survey[i + 1] - survey[i])
        j = np.clip(np.searchsorted(ticks, t) - 1, 0, len(ticks) - 2)
        w = (t - ticks[j]) / (ticks[j + 1] - ticks[j])
        return q[j] + w * (q[j + 1] - q[j])

    soil_tints = np.array([[.074,.078,.041],[.085,.083,.038],[.078,.064,.034],
                           [.063,.048,.030],[.109,.082,.053],[.148,.117,.080],
                           [.166,.148,.116],[.117,.125,.112],[.101,.104,.098]])
    openness = [.09,.10,.012,.005,.034,.075,.170,.135,.105]
    stride = len(ticks)
    for i, (s, q) in enumerate(zip(survey_s, survey)):
        for j, p in enumerate(q):
            flake = .90 + .12 * np.sin(s * 4. + .34 * j) + .07 * np.cos(s * 1.12 - j)
            flake *= .98 + .105*np.sin(.77*s + .69*j + .6*np.cos(s*1.36))
            add_vertex(p, [*(soil_tints[j] * flake), openness[j]],
                       [s / 1.75, (np.dot(p - origin, ACROSS) - (p[2] - origin[2])) / 1.28])
            if i and j:
                k = i * stride + j
                # Rows fold under the lip. Signed orientation is fixed in the
                # cross-section, preserving the outward face even under an overhang.
                outward = np.cross(q[j] - q[j - 1], ALONG)
                add_face(k-stride-1,k-stride,k-1,outward,0)
                add_face(k-1,k-stride,k,outward,0)
                tower["loam"] += 2

    def root(st, depth, radius, hue, primary, attach=None):
        # The top sits inside the turf rind, the descending cambium hangs clear
        # of the earth in the middle, and fine ends disappear into damp gravel.
        count = len(st)
        frac = np.linspace(0., 1., count)
        phase = rng.uniform(0., 2 * np.pi)
        bow = (.143 if primary else .076)*np.sin(frac*np.pi)
        # Outer cambium bows beyond the sod, then the washed end curls back
        # through the earth. Vary exposure along the fibre rather than laying it flat.
        outward = bow + .041 + .024*np.sin(frac*8.+phase) - .047*frac**7
        height = .47*bow + .019 - (.042 if primary else .026)*frac**7
        coords = np.array([skin(s,t) for s,t in zip(st,depth)]) + outward[:,None]*ACROSS + height[:,None]*UP
        if attach is not None:
            coords += (attach-coords[0])*(1.-frac[:,None])**2
        ax = unit(np.gradient(coords, axis=0))
        v = unit(np.cross(ax, ACROSS))
        u = unit(np.cross(v, ax))
        sides = 7 if primary else 5
        rings = []
        for n, f in enumerate(frac):
            r = radius * (1. - .96 * f) ** .75
            widths = r * (1. + .09 * np.sin(n * .87 + phase))
            ring = []
            for j in range(sides):
                angle = 2. * np.pi * j / sides + .18 * np.sin(f * 5. + phase)
                radial = (np.cos(angle) * u[n] + .80 * np.sin(angle) * v[n]) * widths
                rib = 1. + .095 * np.sin(3 * angle + phase)
                ring.append(add_vertex(coords[n] + radial * rib,
                                       [*(hue * (.94 + .09 * np.sin(angle + phase))), .5],
                                       [.012 + .476 * j / sides, .512 + .476 * f]))
            if rings:
                for j,k in zip(range(sides), [*range(1,sides),0]):
                    outward = vertices[ring[j]] - coords[n]
                    add_face(rings[-1][j], ring[j], rings[-1][k], outward, 1)
                    add_face(rings[-1][k], ring[j], ring[k], outward, 1)
            rings.append(ring)
        tower["root_primaries" if primary else "root_branches"] += 1
        return coords

    for center in (15.9, 18.7, 21.5, 23.1, 26.0, 28.5, 31.8, 33.1, 36.6, 40.9, 43., 46.5, 50.1, 53., 56.2):
        for n in range(rng.integers(4,8)):
            s0 = center + rng.uniform(-.6,.6)
            sign = rng.choice([-1.,1.])
            span = sign*rng.uniform(.39,1.63)
            f = np.linspace(0.,1.,13)
            phase = rng.uniform(0.,2*np.pi)
            curl = rng.uniform(.11,.26)*sign
            along = (s0+span*(.18*f+.82*f**1.75)
                     + curl*np.sin(f*5.6+phase)*np.sin(f*np.pi)
                     - .32*span*np.exp(-((f-.97)/.15)**2))
            depth = rng.uniform(.055,.122) + rng.uniform(.50,.76)*f**.86
            depth += rng.uniform(.012,.051)*np.sin(7.*f+phase)*np.sin(f*np.pi)
            hue = np.array([.366,.285,.195])*rng.uniform(.77,1.16)
            radius = rng.uniform(.047,.083)*(1.19 if n==0 else 1.)
            primary_coords = root(along,depth,radius,hue,True)
            # Rhizomes fork in both directions. A few fine radicles cross the
            # local grain, others lie almost parallel with the coarse wood.
            for j in rng.choice(np.arange(3,10), size=rng.integers(3,6), replace=False):
                g = np.linspace(0.,1.,7)
                side = rng.choice([-1.,1.])
                b = (along[j]+side*rng.uniform(.14,.54)*g
                     + rng.uniform(.048,.11)*np.sin(g*6.3+phase)*np.sin(g*np.pi))
                t = np.minimum(.969,depth[j]+rng.uniform(.095,.246)*g+.029*np.sin(g*np.pi*2.))
                root(b,t,radius*rng.uniform(.26,.49),hue*rng.uniform(.80,1.15),False,primary_coords[j])

    palette = np.array([[.244,.258,.251],[.198,.221,.229],[.238,.225,.199],
                        [.126,.151,.149],[.311,.309,.279],[.201,.172,.143]])
    # Sorted deposits occupy lenses of varying width and height. A quiet run
    # of wet silt separates fans on the inside of the bends.
    centers = [14.8,17.1,20.2,20.9,24.0,26.5,29.8,32.1,32.9,36.4,39.5,42.1,
               45.7,46.4,49.6,52.8,55.3,56.1]
    for index,center in enumerate(centers):
        station_width = rng.uniform(.29,.82)
        level = rng.uniform(.57,.81)
        width = rng.uniform(.068,.145)
        count = rng.integers(38,78)
        coarse = rng.integers(4,9)
        # Fine satellites fill a second nearby elevation. They grade away from
        # the coarse centre, with little overlap at the empty bank margins.
        for n in range(count):
            offset = rng.normal(0.,station_width)
            fine = n>count*.55
            s = np.clip(center + offset + (.32 if fine else 0.),13.35,57.65)
            t = level + rng.normal(0.,width) + (.105 if fine else 0.) + .06*offset
            if not .34<t<.975:
                continue
            p = skin(s,t)
            across = skin(s,t+.003)-skin(s,t-.003)
            tangent = skin(s+.025,t)-skin(s-.025,t)
            plane = unit(np.cross(across,tangent))
            gradient = -plane[:2]/max(plane[2],.5)
            if n<coarse:
                radius = rng.uniform(.158,.308)
            else:
                radius = .027 + (.123 if fine else .175)*rng.beta(1.65,2.65)
            stretch = rng.uniform(.59,.97)
            height = min(.154,radius*rng.uniform(.47,.76))
            p[2] -= .008
            gravel_heights.append(max(0.,height-.008))
            angle = rng.uniform(0.,np.pi)
            az = rng.uniform(0.,2*np.pi)
            sides = 9 if n<coarse else 8
            theta = np.arange(sides)*2.*np.pi/sides + rng.uniform(-.105,.105,sides)
            rand = rng.uniform(.90,1.07,sides)
            xy = np.column_stack((np.cos(theta)*radius*rand, np.sin(theta)*radius*stretch*rand))
            xy = xy @ np.array([[np.cos(angle),np.sin(angle)],[-np.sin(angle),np.cos(angle)]])
            lean = np.array([.09*radius*np.cos(az),.09*radius*np.sin(az)])
            rings = []
            for radial,raised,scatter in ((.96,-.52,.13),(1.,.08,.11),(.86,.48,.08),
                                          (.62,.78,.055),(.34,.933,.025)):
                q = xy * radial + lean*max(0.,raised)
                rings.append(np.c_[q,height*(raised+rng.uniform(-scatter,scatter,sides))])
            xyz = np.vstack([*rings, [*lean,height]])
            xyz[:,2] += xyz[:,:2] @ gradient
            wet = 1.-.27*np.clip((t-.55)/.39,0.,1.)
            mineral = palette[rng.integers(len(palette))] * rng.uniform(.90,1.28) * wet
            ids = [add_vertex(p+off,[*(mineral * (.86 + .13*(off[2]/height))),1.],
                              (p[:2]+off[:2])/1.36 + off[2]*np.array([.22,.36])) for off in xyz]
            for tri in ConvexHull(xyz).simplices:
                add_face(*[ids[k] for k in tri],xyz[tri].mean(axis=0),2)
            tower["cobbles"] += 1

    vertices = np.asarray(vertices)
    faces = np.asarray(faces)
    normals = np.zeros_like(vertices)
    tri = vertices[faces]
    hard = np.cross(tri[:,1]-tri[:,0], tri[:,2]-tri[:,0])
    if np.any(np.linalg.norm(hard,axis=1)<1e-11):
        raise ValueError("Degenerate bank geometry")
    for j in range(3):
        np.add.at(normals,faces[:,j],hard)
    normals = unit(normals)
    # Lower clast rings can be strictly interior to the convex hull, omit unused vertices.
    used, flat = np.unique(faces, return_inverse=True)
    faces = flat.reshape(-1,3)
    geo = dict(origin_cm=(origin*SCALE).tolist(), positions=np.round((vertices[used]-origin)*SCALE,3).tolist(),
               faces=faces.tolist(), normals=np.round(normals[used]*[1.,-1.,1.],5).tolist(),
               uv=np.round(np.asarray(uv)[used],5).tolist(), colors=np.round(np.asarray(colors)[used],5).tolist())
    if not np.allclose(np.linalg.norm(normals[used],axis=1),1.,atol=1e-6):
        raise ValueError("Unlit vertex normal in bank")
    save(WORK/"surface.json",geo)
    proof = dict(seed=400192, **tower, triangles=len(faces), vertices=len(used),
                 maximum_pebble_crown_above_toe_m=max(gravel_heights),
                 source_sha256=hashlib.sha256(src.read_bytes()).hexdigest(),
                 previous_native_support_sha256=hashlib.sha256(old_support.read_bytes()).hexdigest(),
                 native_support_sha256=hashlib.sha256((WORK/"support.npz").read_bytes()).hexdigest(),
                 native_strip_bounds_m=[native_rows.min(axis=(0,1)).round(3).tolist(),native_rows.max(axis=(0,1)).round(3).tolist()],
                 section_lengths_m=[13.,58.], old_native_bank_slots=108, new_native_bank_slots=108,
                 changed_native_faces=sum(1 for i in range(108) if i%6>=2),
                 triangle_counts={k:int(np.sum(np.asarray(kinds)==i)) for i,k in enumerate(["earth","wood","stone"])})
    save(WORK/"survey.json",proof)
    print(json.dumps(proof,indent=2))


if __name__ == "__main__":
    build()
