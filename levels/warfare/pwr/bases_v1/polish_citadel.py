"""The plateau Citadel's forked crown, flying buttresses and outer arcade.

Run build() in the finished PWR base study. The rear arch stands at local
Y=25 m. Its solid shoulders and observation piers carry the new structure.
All crown mass begins above the gallery deck and behind the cannon court.
"""
from bisect import bisect_right

import bmesh
import bpy


CENTER = (0.0, 150.0, 0.0)
FAMILY = "Citadel / Crown"
SLOT_NAMES = (
    "FR • silver satin alloy", "FR • inset blue graphite",
    "FR • engraved narrow trim", "FR • shadow channels",
    "TEAM • green recessed energy", "FR • cool interior light",
)
ALLOY, GRAPHITE, TRIM, SHADOW, GREEN, COOL = range(len(SLOT_NAMES))


class Part:
    """Closed, stepped solids sharing one finish palette and local frame."""

    def __init__(self):
        self.verts = []
        self.faces = []
        self.slots = []

    def rings(self, rings, sides, caps=ALLOY, mirror=1):
        count = len(rings[0])
        offset = len(self.verts)
        for ring in rings:
            self.verts.extend((mirror * x, y, z) for x, y, z in ring)
        self.faces.append(tuple(offset + j for j in reversed(range(count))))
        self.slots.append(caps)
        for n in range(len(rings) - 1):
            a = offset + n * count
            for j in range(count):
                k = (j + 1) % count
                self.faces.append((a + j, a + k, a + count + k, a + count + j))
                self.slots.append(sides[j])
        self.faces.append(tuple(offset + (len(rings) - 1) * count + j for j in range(count)))
        self.slots.append(caps)

    def prism_y(self, points, y0, y1, mat, mirror=1):
        rings = [[(x,y,z) for x,z in points] for y in (y0,y1)]
        self.rings(rings,[mat]*len(points),mat,mirror)

    def finish(self, title, width, collection, palette, solid):
        mesh = bpy.data.meshes.new(FAMILY + " / " + title)
        mesh.from_pydata(self.verts, [], self.faces)
        for mat in palette:
            mesh.materials.append(mat)
        for poly, slot in zip(mesh.polygons,self.slots):
            poly.material_index = slot
        bm = bmesh.new()
        bm.from_mesh(mesh)
        # Restore winding on both reflected structures before chamfering.
        bmesh.ops.recalc_face_normals(bm,faces=list(bm.faces))
        bm.normal_update()
        edges = [e for e in bm.edges if e.is_manifold and e.calc_face_angle(0) > .19]
        if not solid and width > 0 and edges:
            bmesh.ops.bevel(bm,geom=edges,offset=width,segments=2,affect='EDGES',
                            clamp_overlap=True,material=-1)
        bmesh.ops.dissolve_degenerate(bm,dist=.0001,edges=list(bm.edges))
        if not solid:
            bmesh.ops.triangulate(bm,faces=list(bm.faces))
        bmesh.ops.dissolve_degenerate(bm,dist=.0001,edges=list(bm.edges))
        bm.to_mesh(mesh)
        bm.free()
        mesh.update()
        uv = mesh.uv_layers.new(name="FinishUV")
        for face in mesh.polygons:
            axis = max(range(3),key=lambda a:abs(face.normal[a]))
            u,v = ((1,2),(0,2),(0,1))[axis]
            direction = 1 if face.normal[axis] > 0 else -1
            for j in face.loop_indices:
                point = mesh.vertices[mesh.loops[j].vertex_index].co
                uv.data[j].uv = (direction*point[u]/5,point[v]/5)
        ob = bpy.data.objects.new(mesh.name,mesh)
        collection.objects.link(ob)
        ob.location = CENTER
        ob["pwr_polish_site"] = "green"
        ob["pwr_polish_family"] = FAMILY
        if solid:
            ob["pwr_polish_solid"] = True
            bevel=ob.modifiers.new("Crown edge break","BEVEL")
            bevel.width=width
            bevel.segments=2
            bevel.limit_method='ANGLE'
            bevel.angle_limit=.19
        else:
            ob["collision"] = "none"
        return ob


def section(z, left, right, fore, aft, bevel_x=.18, bevel_y=.20):
    """An eight-sided plan with broad architectural faces and deep arrises."""
    dx = (right-left)*bevel_x
    dy = (aft-fore)*bevel_y
    return [(left+dx,fore,z),(right-dx,fore,z),(right,fore+dy,z),(right,aft-dy,z),
            (right-dx,aft,z),(left+dx,aft,z),(left,aft-dy,z),(left,fore+dy,z)]


def lerp_section(rows,z):
    index = max(0,min(len(rows)-2,bisect_right([row[0] for row in rows],z)-1))
    a,b = rows[index:index+2]
    t = (z-a[0])/(b[0]-a[0])
    return [p+(q-p)*t for p,q in zip(a[1:],b[1:])]


def skinned_face(part,rows,stops,end,material,sign):
    """Project a closed armor band over the varying width and batter of a blade.

    A band can retreat under the next plate at an articulation. Include every
    crossed host station so the rebate has real and consistent depth.
    Stops are (height, left_fraction, right_fraction, relief_m).
    """
    heights = sorted({s[0] for s in stops}|{r[0] for r in rows if stops[0][0]<r[0]<stops[-1][0]})
    rings=[]
    for z in heights:
        lo,hi,fore,aft = lerp_section(rows,z)
        u0,u1,depth = lerp_section(stops,z)
        x0=lo+(hi-lo)*u0
        x1=lo+(hi-lo)*u1
        surface = fore if end<0 else aft
        y0,y1 = sorted((surface-end*.06,surface+end*depth))
        rings.append(section(z,x0,x1,y0,y1,.065,.35))
    part.rings(rings,[material]*8,material,sign)


def build():
    collection=next(c for c in bpy.data.collections if c.name.startswith("03_GREEN"))
    # Idempotent on the current study, preserving the existing Citadel and guides.
    for ob in list(collection.objects):
        if ob.get("pwr_polish_family") == FAMILY:
            mesh=ob.data
            bpy.data.objects.remove(ob,do_unlink=True)
            if not mesh.users: bpy.data.meshes.remove(mesh)
    materials=[bpy.data.materials[n] for n in SLOT_NAMES]
    built=[]
    def publish(part,title,bevel,solid=False):
        built.append(part.finish(title,bevel,collection,materials,solid))

    for sign,side,top,stagger in ((-1,"west",41.2,-.30),(1,"east",36.6,.55)):
        # A dark structural body is clad with beveled silver armor. The crowns
        # taper, break at the shoulder, and keep daylight between their tips.
        primary=[(10.68,1.8,13.55,21.65,26.0),(12.65,1.8,13.15,20.55,26.4),
                 (17.0,1.75,8.9,21.1,26.35),(21.35,1.45,6.5,21.90,26.05),
                 (25.1,1.04,4.93,22.4,25.95),(top-2.1,.88,3.53,22.95,25.65),
                 (top,1.05,3.32,23.15,25.35)]
        primary=[(z,l,r,f+stagger,b+stagger) for z,l,r,f,b in primary]
        core=Part()
        core.rings([section(*row) for row in primary],
                   [GRAPHITE,ALLOY,ALLOY,TRIM,GRAPHITE,ALLOY,GRAPHITE,TRIM],TRIM,sign)
        publish(core,side+" split monolith",.105,solid=True)

        armor=Part()
        for end in (-1,1):
            # Outer mantle crosses the huge root and resolves into one long
            # quiet face. A break under the crown catches light from the side.
            skinned_face(armor,primary,[(10.88,.49,.85,.24),(12.58,.45,.9,.82),
                    (17.10,.49,.9,.65),(21.30,.55,.88,.55),(25.0,.60,.86,.43),
                    (top-2.0,.61,.86,.34),(top-.31,.64,.84,.20)],end,ALLOY,sign)
            skinned_face(armor,primary,[(12.23,.16,.29,.17),(14.5,.11,.35,.48),
                    (20.6,.13,.35,.41),(24.32,.14,.35,.27)],end,TRIM,sign)
            skinned_face(armor,primary,[(24.57,.15,.34,.27),(25.65,.14,.37,.34),
                    (top-1.75,.14,.35,.22),(top-.28,.16,.30,.14)],end,ALLOY,sign)
            # Narrow inset energy windows disappear under metal at both ends.
            # Keep most of the near-black longitudinal channel unlit.
            for z0,z1 in [(16.2,20.0),(25.8,top-3.4)]:
                skinned_face(armor,primary,[(z0,.405,.445,.035),
                        (z1,.425,.475,.035)],end,GREEN,sign)
        publish(armor,side+" split sheath and energy channels",.05)

        # Flying blade with its own convex crown and dark chamfer beneath the
        # shoulder. Gap to the monolith casts a visible wedge of shadow.
        ribs=[(10.56,15.15,22.1,19.7,25.62),(12.3,14.10,21.98,19.32,25.42),
              (14.32,11.65,17.65,20.0,25.20),(17.2,8.62,13.48,20.71,25.05),
              (20.62,7.40,11.12,21.40,24.93),(25.12,5.52,8.52,22.01,24.89),
              (29.0,4.55,6.10,22.48,24.76)]
        rib=Part()
        rib.rings([section(*row,.135,.22) for row in ribs],
                  [ALLOY,TRIM,ALLOY,ALLOY,ALLOY,GRAPHITE,GRAPHITE,GRAPHITE],TRIM,sign)
        publish(rib,side+" sweeping support",.095,solid=True)
        rib=Part()
        for e in (-1,1):
            skinned_face(rib,ribs,[(11.56,.18,.72,.2),(12.26,.14,.78,.20),
                (16.85,.24,.8,.24),(20.3,.35,.8,.17)],e,GRAPHITE,sign)
            skinned_face(rib,ribs,[(12.45,.27,.33,.244),(16.70,.37,.45,.26)],e,TRIM,sign)
        publish(rib,side+" buttress graphite rebate",.05)

        # Observation turrets root in the two existing piers. Their much
        # smaller caps repeat the crown profile and frame the rear arcade.
        outer=[(13.10,23.95,27.2,17.80,25.9),(14.35,23.72,27.05,18.2,26.12),
               (17.30,23.48,26.55,19.26,25.48),(21.60,23.10,25.62,20.12,25.04),
               (25.15,23.06,24.99,20.68,24.22),(25.9,23.2,24.83,20.95,23.98)]
        mast=Part()
        mast.rings([section(*row,.21,.19) for row in outer],
                   [GRAPHITE,ALLOY,ALLOY,TRIM,GRAPHITE,ALLOY,GRAPHITE,TRIM],TRIM,sign)
        publish(mast,side+" observation pinnacle",.075,solid=True)
        mast=Part()
        for e in (-1,1):
            skinned_face(mast,outer,[(13.65,.28,.55,.10),(15.85,.22,.58,.16),
                        (21.12,.25,.56,.17),(24.85,.28,.50,.10)],e,ALLOY,sign)
            skinned_face(mast,outer,[(17.18,.65,.72,.035),(21.62,.61,.69,.035)],e,GREEN,sign)
        publish(mast,side+" pinnacle inlaid plates",.045)

        # Chamfered rear arc follows the native lintel and inner shoulders.
        # Its outer edge tracks the portal armor, leaving the through volume
        # and jamb guide panels available right down to the floor.
        jamb=Part()
        jamb.prism_y([(12.0,2.4),(13.03,2.4),(13.03,3.22),(9.75,9.77),(8.98,9.68),
                      (9.22,9.04),(12.0,3.04)],26.29,26.57,TRIM,sign)
        jamb.prism_y([(9.18,9.44),(9.68,9.68),(8.83,10.94),(2.44,10.94),
                      (1.90,10.58),(7.68,10.58),(8.20,10.14)],25.90,26.54,ALLOY,sign)
        jamb.prism_y([(2.70,10.65),(6.92,10.65),(7.04,10.77),(2.86,10.77)],
                      26.545,26.57,GREEN,sign)
        publish(jamb,side+" rear vault archivolt",.042)

    # Body behind the deep aperture at the foot of the split. The empty
    # vertical cut above the coupler lets the ridgeline show through.
    coupler=[(11.05,-2.94,2.94,22.62,26.23),(13.55,-3.43,3.43,22.84,26.45),
             (16.02,-2.62,2.62,23.0,26.22),(22.58,-1.74,1.74,23.47,25.80),
             (26.85,-1.38,1.38,23.65,25.48),(28.8,-1.15,1.15,23.86,25.25)]
    connector=Part()
    connector.rings([section(*row,.17,.18) for row in coupler],
                    [GRAPHITE,TRIM,SHADOW,ALLOY,GRAPHITE,TRIM,SHADOW,ALLOY],TRIM)
    publish(connector,"recessed aperture spine",.075,solid=True)

    signal=Part()
    for end in (-1,1):
        for z0,z1,width in ((14.1,16.8,.14),(17.25,23.8,.11),(24.25,27.6,.085)):
            skinned_face(signal,coupler,[(z0,.5-width,.5+width,.12),
                                         (z1,.5-width,.5+width,.12)],end,SHADOW,1)
            width*=.50
            skinned_face(signal,coupler,[(z0+.13,.5-width,.5+width,.15),
                                         (z1-.16,.5-width,.5+width,.15)],end,GREEN,1)
    publish(signal,"three recessed green spine windows",.025)
    bpy.context.view_layer.update()
    return built

