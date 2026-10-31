"""Concept-matched northern Forerunner retaining structure, in metres.

Load-bearing construction is merged into the sealed BSP. Five spines lean in
the front elevation; trapezoidal bays follow them. Trims have physical bevels
and use existing CE slots. Light preview colors remain Blender-only studies.
"""
import math
from terrain_form import height as terrain_height

BALCONY_Z = 7.2
ARRIVALS = ((-48, 28.0, BALCONY_Z+.05), (48, 28.0, BALCONY_Z+.05))


def build(mesh_object, box, prism, bevel_rectangle, boolean, panels, floor, light, portal):
    def profile(name, xz, y0, y1, material):
        n = len(xz)
        return mesh_object(name,[(x,y0,z) for x,z in xz]+[(x,y1,z) for x,z in xz],
            [tuple(range(n)),tuple(reversed(range(n,2*n)))]+
            [(i,i+n,(i+1)%n+n,(i+1)%n) for i in range(n)],[material])

    def inset(poly, width):
        # Intersect inward-offset edges: bevel widths remain physically equal.
        lines=[]
        for a,b in zip(poly,poly[1:]+poly[:1]):
            dx,dz=b[0]-a[0],b[1]-a[1]
            length=math.hypot(dx,dz)
            lines.append(((a[0]-dz/length*width,a[1]+dx/length*width),(dx,dz)))
        result=[]
        for i,(point,direction) in enumerate(lines):
            prev,other=lines[i-1]
            cross=direction[0]*other[1]-direction[1]*other[0]
            if abs(cross)<1e-8:
                result.append(point)
                continue
            delta=(prev[0]-point[0],prev[1]-point[1])
            t=(delta[0]*other[1]-delta[1]*other[0])/cross
            result.append((point[0]+t*direction[0],point[1]+t*direction[1]))
        return result

    def armored(name, outline, y0, y1, material=panels, bevel=.18):
        n=len(outline)
        inside=inset(outline,bevel)
        vertices=[(x,y0,z) for x,z in inside]
        vertices += [(x,y0+bevel,z) for x,z in outline]
        vertices += [(x,y1,z) for x,z in outline]
        faces=[tuple(range(n)),tuple(reversed(range(2*n,3*n)))]
        for start in (0,n):
            faces += [(start+i,start+i+n,start+(i+1)%n+n,start+(i+1)%n) for i in range(n)]
        return mesh_object(name,vertices,faces,[material])

    wall=box("north_infrastructure_gameplay_solid",(-76,34,-1),(76,41,22.4),panels)
    wall["design_role"]="Layered diagonal retaining spines, sheltered balcony and teleport alcoves"
    wall["mjolnir_pcg_policy"]="NONE"
    def add(obj):
        boolean(wall,obj,"UNION")
    def cut(obj):
        boolean(wall,obj)

    # Fine armor is a separately editable render-only layer. Keeping small
    # trim islands out of the sealed BSP avoids CE's 4 cm collision weld
    # collapsing precision bevels. The existing passage collision stays clear.
    detail_materials={}
    def detail(obj):
        import bmesh
        bm=bmesh.new(); bm.from_mesh(obj.data)
        bmesh.ops.recalc_face_normals(bm,faces=list(bm.faces))
        bm.to_mesh(obj.data); bm.free()
        for slot in obj.material_slots:
            original=slot.material
            if original.name not in detail_materials:
                mat=original.copy(); mat.name=original.name.rstrip('!')+'!'
                mat['tst_detail_material']=original.name
                mat['mjolnir_pcg_policy']='NONE'
                detail_materials[original.name]=mat
            slot.material=detail_materials[original.name]
        obj['mjolnir_render_detail']=True
        obj['mjolnir_pcg_policy']='NONE'
        obj['authoring_note']='Render-only precision armor; collision is the sealed underlying shell.'
        return obj

    transverse_warp=None
    def transverse(name, yz, x0, x1, material):
        """Model a Y/Z profile facing down the balcony, not just the arena."""
        obj=profile(name,yz,x0,x1,material)
        for vertex in obj.data.vertices:
            vertex.co.x,vertex.co.y=vertex.co.y,vertex.co.x
            if transverse_warp:
                vertex.co.x=transverse_warp(vertex.co.x*3.048,vertex.co.z*3.048)/3.048
        # Swapping axes reverses handedness.
        import bmesh
        bm=bmesh.new(); bm.from_mesh(obj.data)
        bmesh.ops.reverse_faces(bm,faces=list(bm.faces))
        bm.to_mesh(obj.data); bm.free()
        return obj

    def transverse_ring(name, outer, inner, x0, x1, material):
        # An arch is open at foot level, not a closed ring across the floor.
        if name.startswith('passage_'):
            outer=[(y,6.9 if z==min(p[1] for p in outer) else z) for y,z in outer]
            inner=[(y,6.7 if z==min(p[1] for p in inner) else z) for y,z in inner]
        obj=ring_mesh(name,outer,inner,x0,x1,material,name.startswith('passage_'))
        for v in obj.data.vertices:
            v.co.x,v.co.y=v.co.y,v.co.x
            if transverse_warp:
                v.co.x=transverse_warp(v.co.x*3.048,v.co.z*3.048)/3.048
        detail(obj)

    def ring_mesh(name,outer,inner,d0,d1,material,open_bottom=False):
        # Explicit quad strips avoid Boolean n-gon holes and ensure that
        # beveling cannot fill a doorway with a triangulation fan.
        n=len(outer)
        vertices=[(x,d,z) for d in (d0,d1) for poly in (outer,inner) for x,z in poly]
        faces=[]
        for i in range(n):
            j=(i+1)%n
            if open_bottom and i==0: continue
            faces.extend([(i,j,n+j,n+i),(2*n+i,3*n+i,3*n+j,2*n+j),
                          (i,2*n+i,2*n+j,j),(n+i,n+j,3*n+j,3*n+i)])
        if open_bottom:
            for i in (0,1): faces.append((i,n+i,3*n+i,2*n+i))
        return mesh_object(name,vertices,faces,[material])

    def front_ring(name, outer, inner, y0,y1,material):
        if name.startswith('arrival_'):
            outer=[(x,6.9 if z==min(p[1] for p in outer) else z) for x,z in outer]
            inner=[(x,6.7 if z==min(p[1] for p in inner) else z) for x,z in inner]
        obj=ring_mesh(name,outer,inner,y0,y1,material,name.startswith('arrival_'))
        detail(obj)

    def fitted_arch(name,outer,inner,y0,y1,material):
        # Separate closed plates with real assembly gaps and chamferable edges.
        # Underlying sealed vault provides collision and the dark joint backing.
        outer=[(x,6.9 if z==min(p[1] for p in outer) else z) for x,z in outer]
        inner=[(x,6.7 if z==min(p[1] for p in inner) else z) for x,z in inner]
        for i in range(1,len(outer)):
            j=(i+1)%len(outer)
            plate=[outer[i],outer[j],inner[j],inner[i]]
            if sum(plate[k][0]*plate[(k+1)%4][1]-plate[(k+1)%4][0]*plate[k][1] for k in range(4))<0:
                plate.reverse()
            obj=armored(name+'_plate_'+str(i),inset(plate,.025),y0,y1,material,.025)
            if i in (1,5):
                cx=(min(p[0] for p in outer)+max(p[0] for p in outer))/2
                side=1 if i==1 else -1
                line=[(3.47,9.42),(3.49,9.42),(3.49,7.84),(3.02,7.38),(3.0,7.40),(3.47,7.85)]
                line=[(cx+side*u,v) for u,v in (line if side==1 else reversed(line))]
                line.reverse()  # Profile solids require counterclockwise outlines.
                boolean(obj,profile('jamb_angular_engraving_cut',line,y0-.02,y0+.025,floor))
                obj['precision_bevel_m']=.006
                obj['engraved_armor']=True
            if i in (2,4):
                cx=(min(p[0] for p in outer)+max(p[0] for p in outer))/2
                side=1 if i==2 else -1
                p=(cx+side*3.25,10.15); q=(cx+side*2.48,11.12)
                dx,dz=q[0]-p[0],q[1]-p[1]; length=math.hypot(dx,dz)
                ox,oz=-dz/length*.13,dx/length*.13
                slot=[(p[0]-ox,p[1]-oz),(q[0]-ox,q[1]-oz),(q[0]+ox,q[1]+oz),(p[0]+ox,p[1]+oz)]
                if sum(slot[k][0]*slot[(k+1)%4][1]-slot[(k+1)%4][0]*slot[k][1] for k in range(4))<0: slot.reverse()
                boolean(obj,profile('shoulder_lens_recess_cut',slot,y0-.02,y0+.04,floor))
                obj['precision_bevel_m']=.004; obj['engraved_armor']=True
            detail(obj)

    # Base center, crown center, top, bottom half-width, top half-width.
    spines=[(-72,-68,26.4,3.7,2.8),(-36,-27,26.3,4.4,3.5),
            (0,0,27.3,4.0,3.3),(36,27,26.3,4.4,3.5),(72,68,26.4,3.7,2.8)]
    def side_at(spine,z,right):
        low,high,top,w0,w1=spine
        t=(z+.6)/(top+.6)
        center=low+(high-low)*t
        width=w0+(w1-w0)*t
        return center+(width if right else -width)

    # Each structural bay has two armor leaves inside a deep dark surround.
    for index,(left,right) in enumerate(zip(spines,spines[1:])):
        z0,z1=9.0,22.0
        left0,left1=side_at(left,z0,True)+.35,side_at(left,z1,True)+.35
        right0,right1=side_at(right,z0,False)-.35,side_at(right,z1,False)-.35
        outer=[(left0,z0),(right0,z0),(right1,z1),(left1,z1)]
        cut(profile("deep_structural_bay",outer,32.7,36.0,floor))
        add(armored("bay_outer_frame",outer,33.15,36.2,floor,.25))
        cut(profile("bay_frame_void",inset(outer,.60),32.9,35.65,floor))
        split0=(left0+right0)/2 + (-.45 if index%2 else .45)
        split1=(left1+right1)/2
        leaves=[[(left0+.95,9.85),(split0-.16,9.85),(split1-.16,21.15),(left1+.95,21.15)],
                [(split0+.16,9.85),(right0-.95,9.85),(right1-.95,21.15),(split1+.16,21.15)]]
        for leaf_index,outline in enumerate(leaves):
            front=34.73+leaf_index*.10
            add(armored("recessed_armor_leaf",outline,front,36.3,panels,.20))
            # Each leaf has its own deep gasket, chamfer and set-back face,
            # rather than the previous single flat panel inside one bay frame.
            cut(profile("leaf_inner_gasket",inset(outline,.43),front-.08,front+.42,floor))
            add(armored("leaf_recessed_inner_face",inset(outline,.66),front+.23,
                        front+.60,panels,.16))
            p0,p1,p2,p3=outline
            center0,center1=(p0[0]+p1[0])/2,(p2[0]+p3[0])/2
            joint=[(center0-1.1,11.0),(center0-.96,11.0),
                   (center1+1.1,20.8),(center1+.96,20.8)]
            # Cut through the inset plate's complete bevel/back thickness.
            # Stopping at +.38 left 1 cm slivers on the +.39 bevel return;
            # HEK discards those triangles and opens the collision boundary.
            cut(profile("diagonal_armor_seam",joint,front-.05,front+.65,floor))
            # A second short assembly line meets the major oblique seam, giving
            # broad armor plates a designed hierarchy instead of fine noise.
            midx=(center0+center1)/2
            join_z=14.7 if leaf_index==0 else 17.0
            cut(profile("leaf_horizontal_return_joint",
                [(midx-.1,join_z),(p1[0]-.9,join_z),
                 (p1[0]-.9,join_z+.10),(midx-.1,join_z+.10)],
                front+.12,front+.65,floor))
            # Discrete concealed wall washers: a physical supporting shelf and
            # an upward-facing luminous aperture below the recessed panel.
            add(prism("panel_uplight_shelf",bevel_rectangle(center0-1.5,33.85,
                        center0+1.5,36.3,.18),9.13,9.62,floor))
            lens=mesh_object("panel_foot_uplight_lens",
                [(center0-.9,34.03,9.635),(center0+.9,34.03,9.635),
                 (center0+.9,34.21,9.635),(center0-.9,34.21,9.635)],[(0,1,2,3)],[light])
            lens["authored_light_lens"]=True
            lens["preview_emission_color"]=(1.0,.66,.28)
            lens["preview_emission_strength"]=8.0
            lens["preview_light_power"]=320.0
            lens["preview_light_color"]=(1.0,.66,.28)
            lens["preview_light_direction"]=(0,.2,1)
            lens["preview_light_size"]=(1.8,.18)
            lens["mjolnir_pcg_policy"]="NONE"
        # Stepped lintels merge into raised piers rather than one flat roof bar.
        cap=[(left1-.3,22.05),(right1+.3,22.05),(right1+.3,23.55),
             (right1-1.9,23.55),(right1-2.9,22.85),
             (left1+2.9,22.85),(left1+1.9,23.55),(left1-.3,23.55)]
        add(profile("stepped_bay_entablature",cap,32.75,40.7,panels))
        add(armored("lintel_shadow_rail",
            [(left1,21.9),(right1,21.9),(right1,22.25),(left1,22.25)],32.5,34.1,floor,.08))

    add(prism("continuous_balcony",bevel_rectangle(-70,21.8,70,34.7,1.0),6.45,BALCONY_Z,floor))
    add(box("lower_retaining_plinth",(-76,32.3,-.8),(76,35.4,1.6),floor))
    for x in (-60,-45,-19,19,45,60):
        # Keep recesses above the continuous talus. Cutting a service pocket
        # through that intersection produced almost coincident BSP split edges
        # even though Blender's Boolean result was topologically closed.
        bottom=max(1.9,max(terrain_height(x+dx,y) for dx in (-5.3,-4,-2,0,2,4,5.3)
                           for y in (33.8,34,35.1))+.15)
        if bottom > 4.7:
            continue
        cut(profile("lower_service_recess",bevel_rectangle(x-5.3,bottom,x+5.3,5.7,
                    min(.75,(5.7-bottom)/4)),33.8,35.1,floor))
        for offset in (-3.5,0,3.5):
            add(armored("service_bay_fin",bevel_rectangle(x+offset-.18,bottom+.3,x+offset+.18,5.4,.1),34.65,35.3,floor,.06))

    # Faceted diagonal armor around dark structural cores. Fronts stop behind
    # y=25.1; the outer walk and the passages through the cores are both usable.
    for index,spine in enumerate(spines):
        low,high,top,w0,w1=spine
        core=[(low-w0,-.6),(low+w0,-.6),(high+w1,top-1),
              (high+w1-.8,top),(high-w1+.8,top),(high-w1,top-1)]
        add(profile("diagonal_spine_core",core,25.9,40,floor))
        add(armored("diagonal_spine_armor",inset(core,.28),25.15,34.5,panels,.38))
        def center(z):
            return low+(high-low)*(z+.6)/(top+.6)
        z0,z1=9.1,top-1.4
        channel=[(center(z0)-.78,z0),(center(z0)+.78,z0),
                 (center(z1)+.78,z1),(center(z1)-.78,z1)]
        cut(profile("spine_recessed_raceway",channel,24.95,25.78,floor))
        upper=[(center(18)-1.7,18),(center(18)+1.7,18),
               (center(top-1.7)+1.7,top-1.7),(center(top-1.7)-1.7,top-1.7)]
        cut(profile("spine_upper_coffer",upper,24.96,25.56,floor))
        # Floating-looking black holes become nested armored coffers, with a
        # real 22 cm reveal and a smaller chamfered plate over the dark raceway.
        inner_upper=[(center(18.4)-1.13,18.4),(center(18.4)+1.13,18.4),
                     (center(top-2.2)+1.13,top-2.2),(center(top-2.2)-1.13,top-2.2)]
        add(armored("spine_coffer_inner_armor",inner_upper,25.62,26.1,panels,.17))
        cut(box("spine_crown_key",(high-.8,24.7,top-.45),(high+.8,34.7,top+.2),floor))
        for zz in (3.2,8.7,17.6):
            x=center(zz)
            cut(profile("spine_assembly_joint",[(x-4,zz),(x+4,zz),
                        (x+4,zz+.11),(x-4,zz+.11)],24.96,25.35,floor))
        if index==2:
            # The reference's central spine has paired shoulders around its
            # narrow vertical heart, not the same face as every angled support.
            cheek=[(-3.35,9.0),(-1.04,9.0),(-1.04,23.45),
                   (-2.15,25.55),(-2.95,25.55),(-3.35,24.9)]
            for side in (-1,1):
                outline=cheek if side==-1 else [(-x,z) for x,z in reversed(cheek)]
                add(armored("central_spine_shoulder",outline,24.95,25.52,panels,.19))
            for zz in (12.6,21.4):
                for side in (-1,1):
                    lo,hi=sorted((side*1.2,side*3.25))
                    cut(profile("central_shoulder_joint",
                        [(lo,zz),(hi,zz),(hi,zz+.10),(lo,zz+.10)],24.8,25.14,floor))
            crown_lamp=mesh_object("central_spine_crown_beacon",
                [(-.34,25.595,25.08),(.34,25.595,25.08),
                 (.34,25.595,25.24),(-.34,25.595,25.24)],[(0,1,2,3)],[light])
            crown_lamp["preview_emission_color"]=(.045,.62,1.0)
            crown_lamp["preview_emission_strength"]=5.0
            crown_lamp["mjolnir_pcg_policy"]="NONE"
        a,b=(11.3,17.1) if index==2 else (12.2,13.8)
        lamp=mesh_object("infrastructure_cyan_raceway",
            [(center(a)-.095,25.755,a),(center(a)+.095,25.755,a),
             (center(b)+.095,25.755,b),(center(b)-.095,25.755,b)],[(0,1,2,3)],[light])
        lamp["preview_emission_color"]=(.045,.62,1.0)
        lamp["preview_emission_strength"]=5.0
        lamp["mjolnir_pcg_policy"]="NONE"

        if index in (1,2,3):
            # Transverse, sheltered passage: 5.2 m wide and 3.7 m high.
            # Cut through all tower layers, then restore a single level sill.
            cx=center(8.8)
            cut(box("tower_walkthrough",(cx-8,26.2,7.0),(cx+8,31.4,10.9),floor))
            add(box("tower_passage_sill",(cx-8.2,26.0,6.8),(cx+8.2,31.6,BALCONY_Z),floor))
            lens=mesh_object("tower_passage_ceiling_lamp",
                [(cx-2,28.6,10.68),(cx+2,28.6,10.68),
                 (cx+2,28.85,10.68),(cx-2,28.85,10.68)],[(3,2,1,0)],[light])
            lens["authored_light_lens"]=True
            lens["mjolnir_pcg_policy"]="NONE"
            lens["preview_light_power"]=450
            lens["preview_light_color"]=(1.0,.84,.66)
            lens["preview_light_size"]=(3.4,1.6)

            # Nested six-sided passage ribs. The corners stay above the
            # 2.4 m player envelope; all three 5.2 m route samples stay clear.
            # Cover the core's front return, and follow its real taper. The
            # former fixed-X rib left a strip of leaning wall poking past it.
            outer=[(25.05,7.0),(31.88,7.0),(31.88,10.25),
                   (30.85,11.45),(26.08,11.45),(25.05,10.25)]
            opening=[(26.32,7.0),(31.28,7.0),(31.28,9.88),
                     (30.50,10.73),(27.10,10.73),(26.32,9.88)]
            transverse_warp=lambda x,z: center(z)+(x-cx)*(w0+(w1-w0)*(z+.6)/(top+.6)+.12)/3.9
            for offset in (-3.9,0,3.9):
                xx=cx+offset
                transverse_ring("passage_nested_dark_frame",outer,opening,xx-.32,xx+.32,floor)
                pale_outer=inset(outer,.14)
                pale_inner=inset(outer,.36)
                transverse_ring("passage_titanium_frame",pale_outer,pale_inner,xx-.39,xx+.39,panels)
            # Large side armor panel above the route: sparse geometric
            # silhouette and recessed field instead of a tiled flat slab.
            # Every panel, branching joint and beacon shares y=28.8. Define
            # one side and reflect it rather than hand-drawing unequal halves.
            panel_axis=28.8
            def mirrored(poly):
                return [(2*panel_axis-u,v) for u,v in reversed(poly)]
            side_outer=bevel_rectangle(25.6,11.2,32.0,23.8,.65)
            for direction in (-1,1):
                xx=cx+direction*4.15
                transverse_warp=lambda x,z: x+center(z)-cx+direction*(w0+(w1-w0)*(z+.6)/(top+.6)-4.15)
                a,b=sorted((xx,xx+direction*.30))
                transverse_ring("tower_side_dark_gasket",side_outer,inset(side_outer,.28),a,b,floor)
                a,b=sorted((xx+direction*.12,xx+direction*.38))
                transverse_ring("tower_side_titanium_panel_border",inset(side_outer,.34),inset(side_outer,.53),a,b,panels)
                # Separate fitted plates make the branching grooves. This
                # construction has explicit closed topology, avoiding thin
                # coplanar intersections from a chain of Boolean cutters.
                a,b=sorted((xx+direction*.08,xx+direction*.22))
                a,b=sorted((xx+direction*.08,xx+direction*.13))
                detail(transverse('tower_side_recess_backing',inset(side_outer,.58),a,b,floor))
                flank=[(26.25,12.0),(28.74,12.0),(28.74,13.40),
                       (27.10,14.98),(27.10,20.83),(26.25,20.83)]
                center_leaf=[(27.20,20.83),(27.20,15.02),(28.8,13.53),
                             (30.40,15.02),(30.40,20.83)]
                leaves=[flank,center_leaf,mirrored(flank),
                        [(26.25,20.93),(31.35,20.93),(31.35,23.15),(26.25,23.15)]]
                # This checks the intended profiles before Boolean/bevel work;
                # the final source mesh is also audited by reflection.
                for poly in (side_outer,center_leaf,leaves[3]):
                    assert all(any(abs(2*panel_axis-u-a)<1e-7 and abs(v-b)<1e-7
                               for a,b in poly) for u,v in poly)
                for leaf_index,poly in enumerate(leaves):
                    a,b=sorted((xx+direction*.14,xx+direction*.22))
                    leaf=transverse('tower_side_fitted_armor_leaf',poly,a,b,panels)
                    if leaf_index==1:
                        for mirror in (False,True):
                            for parallel in (0,.065):
                                path=[(27.59,20.1),(27.61,20.1),(27.61,19.68),(27.73,19.53),
                                      (27.73,16.02),(28.40,15.20),(28.38,15.18),(27.71,16.0),
                                      (27.71,19.52),(27.59,19.67)]
                                path=[(u+parallel,v) for u,v in path]
                                if mirror: path=mirrored(path)
                                path.reverse()
                                c,d=sorted((xx+direction*.195,xx+direction*.25))
                                boolean(leaf,transverse('tower_fine_engraving_cut',path,c,d,floor))
                        leaf['precision_bevel_m']=.004
                        leaf['engraved_armor']=True
                    detail(leaf)
                a,b=sorted((xx+direction*.22,xx+direction*.25))
                light_case=[(28.42,16.3),(28.8,15.9),(29.18,16.3),(29.18,20.35),(28.42,20.35)]
                detail(transverse("tower_beacon_dark_housing",light_case,a,b,floor))
                # Atlas light is short enough to remain a fixture, not a
                # texture stretched over the entire height of the tower.
                xp=xx+direction*.26
                lamp=mesh_object("tower_side_beacon",[(xp,28.71,16.6),(xp,28.89,16.6),
                    (xp,28.89,19.9),(xp,28.71,19.9)],[(0,1,2,3)],[light])
                lamp["mjolnir_pcg_policy"]="NONE"
                for v in lamp.data.vertices:
                    v.co.x=transverse_warp(v.co.x*3.048,v.co.z*3.048)/3.048
            transverse_warp=None

    # Close the two former stepped-exit gaps after removing their blocky
    # exterior terraces. The paired teleporter returns still reach the ground.
    # The short new sections overlap the adjacent BSP body by 12 cm for a
    # reliable union, while the visible armor remains inside its own bay.
    for a,b in ((-69,-37),(-37,-29),(-29,29),(29,37),(37,69)):
        join = .12 if (a,b) in ((-37,-29),(29,37)) else 0
        add(prism("balcony_parapet",bevel_rectangle(a-join,21.85,b+join,22.55,.22),7.08,8.25,panels))
        # Armor caps, large dark recesses and narrow inner borders are true
        # geometry. The broad deck and sheltered teleporters stay intact.
        # Reserve a real assembly bay for the central support. No long cap or
        # decorative insert may pass through it, even on the arena-facing side.
        clasp_x=(a+b)/2
        bays=[]
        for start,end in ((a,clasp_x-.75),(clasp_x+.75,b)):
            count=max(1,round((end-start)/4.5))
            bays.extend((start+.30+i*(end-start)/count,
                         start+(i+1)*(end-start)/count-.30) for i in range(count))
        for left,right in bays:
            assert right+.27<clasp_x-.65 or left-.27>clasp_x+.65
            detail(prism('parapet_fitted_cap_plate',bevel_rectangle(left-.27,21.78,right+.27,22.66,.12),8.12,8.37,floor))
            detail(prism('parapet_cap_pale_inner_edge',bevel_rectangle(left-.24,22.61,right+.24,22.72,.035),8.29,8.38,panels))
            outline=bevel_rectangle(left,7.38,right,8.05,.16)
            # Both sides receive the same construction hierarchy.
            for y0,y1 in ((21.73,21.94),(22.49,22.67)):
                detail(armored("parapet_recessed_dark_panel",outline,y0,y1,floor,.06))
                front_ring("parapet_inset_border",inset(outline,.08),inset(outline,.13),y0-.025,y1,panels)
            surround=bevel_rectangle(left-.20,7.24,right+.20,8.18,.20)
            front_ring("parapet_segmented_pale_surround",surround,outline,22.60,22.72,panels)
            detail(profile("parapet_charcoal_insert",inset(outline,.03),22.65,22.69,floor))
            xmid=(left+right)/2
            lamp=mesh_object("parapet_spaced_marker",[(xmid-.12,22.675,8.15),(xmid+.12,22.675,8.15),
                (xmid+.12,22.675,8.25),(xmid-.12,22.675,8.25)],[(0,1,2,3)],[light])
            lamp["mjolnir_pcg_policy"]="NONE"
        if b-a>7:
            x=(a+b)/2
            add(armored("parapet_vertical_clasp",bevel_rectangle(x-.65,6.3,x+.65,8.30,.16),21.6,22.74,floor,.12))
            # A single fitted saddle replaces the interpenetrating wrap plates.
            # Its shoulder meets the body below; neighboring caps terminate in
            # their own bays with a recessed gap on either side of the support.
            crown=[(x-.65,8.29),(x+.65,8.29),(x+.65,8.39),
                   (x+.44,8.57),(x-.44,8.57),(x-.65,8.39)]
            cap=detail(profile('parapet_clasp_single_saddle',crown,21.58,22.78,panels))
            cap['precision_bevel_m']=.018
            for y in (21.565,22.795):
                lamp=mesh_object('parapet_clasp_horizontal_lamp',[(x-.31,y,8.32),(x+.31,y,8.32),
                    (x+.31,y,8.40),(x-.31,y,8.40)],[(0,1,2,3)],[light])
                lamp['mjolnir_pcg_policy']='NONE'
    for x in (-22,22):
        add(prism("balcony_sightline_screen",bevel_rectangle(x-.55,29.8,x+.55,34.3,.2),7.08,10.3,floor))

    # Nearly flush, modeled alloy inlays give the broad floor a designed
    # border. Small mitres echo the angular joints on the tower panels.
    for edge in (23.05,28.95,31.85):
        path=[(-69,edge),(-37,edge),(-36.3,edge+.42),(-29.7,edge+.42),
              (-29,edge),(-4,edge),(-3.3,edge+.42),(3.3,edge+.42),
              (4,edge),(29,edge),(29.7,edge+.42),(36.3,edge+.42),(37,edge),(69,edge)]
        if edge==28.95:
            for center in (-48,48):
                path += [(center-5.5,edge),(center-4.5,edge-.6),(center+4.5,edge-.6),(center+5.5,edge)]
        elif edge==23.05:
            for center in (-53,53):
                path += [(center-2.6,edge),(center-1.9,edge+.42),(center+1.9,edge+.42),(center+2.6,edge)]
        path.sort()
        for i,(a,b) in enumerate(zip(path,path[1:])):
            dx,dy=b[0]-a[0],b[1]-a[1]; length=math.hypot(dx,dy)
            nx,ny=-dy/length,dx/length
            for band in (-.055,.055):
                outline=[(a[0]+nx*(band+.008),a[1]+ny*(band+.008)),
                         (a[0]+nx*(band-.008),a[1]+ny*(band-.008)),
                         (b[0]+nx*(band-.008),b[1]+ny*(band-.008)),
                         (b[0]+nx*(band+.008),b[1]+ny*(band+.008))]
                line=detail(prism("balcony_flush_border_inlay",outline,7.197,7.203,floor))
                line['precision_bevel_m']=.001

    # Six-sided arrival vaults have pale chamfered armor around a dark surround.
    for x,y,z in ARRIVALS:
        outer=[(x-4.6,7.04),(x+4.6,7.04),(x+4.6,10.15),
               (x+2.9,12.3),(x-2.9,12.3),(x-4.6,10.15)]
        add(armored("arrival_outer_vault",outer,29.65,32.4,floor,.25))
        add(armored("arrival_inner_armor",inset(outer,.32),29.4,32.3,panels,.18))
        # Cut below the walking plane, then restore one flat sill. Ending the
        # aperture exactly at z=7.2 intersects the outer bevel at a knife edge
        # which can survive Exact Boolean but collapse during CE's final weld.
        aperture=[(x-2.65,7.0),(x+2.65,7.0),(x+2.65,9.7),
                  (x+1.75,10.85),(x-1.75,10.85),(x-2.65,9.7)]
        cut(profile("arrival_vault_opening",aperture,29.1,32.15,floor))
        # Layered armor is modeled around the opening rather than painted
        # across the entire vault. Every layer shares the walk-through void.
        front_ring("arrival_outer_shadow_gasket",inset(outer,.10),inset(outer,.27),29.40,29.72,floor)
        front_ring("arrival_outer_bright_edge",inset(outer,.31),inset(outer,.43),29.17,29.65,panels)
        fitted_arch('arrival_fitted_titanium_frame',inset(outer,.64),aperture,29.16,29.67,panels)
        front_ring("arrival_inner_precision_lip",inset(outer,.78),inset(outer,.91),29.09,29.61,panels)
        for side in (-1,1):
            # Fitted liner plates meet the threshold, sloping shoulder and
            # back of the vault, sharing one narrow angular assembly joint.
            liner_plates=[[(29.42,7.21),(31.29,7.21),(31.29,8.25),(30.70,8.25),(30.53,8.40),(29.42,8.40)],
                          [(29.42,8.42),(30.54,8.42),(30.72,8.27),(31.29,8.27),(31.29,9.67),(29.42,9.67)]]
            for outline in liner_plates:
                a,b=sorted((x+side*2.63,x+side*2.68))
                liner=transverse('arrival_inner_jamb_liner',outline,a,b,floor)
                detail(liner)
                # The plate edges form the joints; no bright applied rim.
            lining=[(x+side*2.63,29.42,9.69),(x+side*2.63,31.29,9.69),
                    (x+side*1.74,31.29,10.82),(x+side*1.74,29.42,10.82)]
            vertices=lining+[(u+side*.03,v,w) for u,v,w in lining]
            detail(mesh_object('arrival_inner_jamb_liner_shoulder',vertices,
                [(0,1,2,3),(7,6,5,4),(0,4,5,1),(1,5,6,2),(2,6,7,3),(3,7,4,0)],[floor]))
            xx=x+side*4.05
            housing=bevel_rectangle(xx-.17,7.85,xx+.17,9.7,.035)
            detail(armored("arrival_marker_recess",housing,29.20,29.34,floor,.025))
            lamp=mesh_object("arrival_outer_jamb_marker",[(xx-.055,29.19,8.08),(xx+.055,29.19,8.08),
                (xx+.055,29.19,9.44),(xx-.055,29.19,9.44)],[(0,1,2,3)],[light])
            lamp['mjolnir_pcg_policy']='NONE'
            # Two upper corner plates and two jamb plates split the broad
            # titanium surround without filling it with repeated greebles.
            # The diagonal lens sits inside a real pocket in the fitted arch
            # plate. No separate external bracket or support cheek is needed.
            p=(x+side*3.25,10.15); q=(x+side*2.48,11.12)
            dx,dz=q[0]-p[0],q[1]-p[1]; length=math.hypot(dx,dz)
            ox,oz=-dz/length*.055,dx/length*.055
            lamp=mesh_object('arrival_diagonal_shoulder_marker',[(p[0]-ox,29.175,p[1]-oz),
                (q[0]-ox,29.175,q[1]-oz),(q[0]+ox,29.175,q[1]+oz),(p[0]+ox,29.175,p[1]+oz)],[(0,1,2,3)],[light])
            lamp['mjolnir_pcg_policy']='NONE'
        back=[(xx,max(zz,7.2)) for xx,zz in inset(aperture,.22)]
        add(profile("portal_rear_reveal",aperture,31.3,32.4,panels))
        cut(profile("portal_rear_opening",back,31.1,32.18,floor))
        add(box("arrival_continuous_sill",(x-4.7,29.0,6.8),(x+4.7,35.9,7.2),floor))
        lens=mesh_object("wall_arrival_light_lens",
            [(x-1.65,30,10.82),(x+1.65,30,10.82),(x+1.65,31,10.82),(x-1.65,31,10.82)],
            [(3,2,1,0)],[light])
        lens["authored_light_lens"]=True
        lens["mjolnir_pcg_policy"]="NONE"
        for dx in (-2.3,2.3):
            lamp=mesh_object("portal_warm_jamb_light",
                [(x+dx-.055,32.11,7.7),(x+dx+.055,32.11,7.7),
                 (x+dx+.055,32.11,9.5),(x+dx-.055,32.11,9.5)],[(0,1,2,3)],[light])
            lamp["mjolnir_pcg_policy"]="NONE"
        shield=mesh_object("balcony_walkthrough_teleporter",
            [(x-2.35,31.55,7.22),(x+2.35,31.55,7.22),(x+2.35,31.55,9.5),
             (x+1.6,31.55,10.55),(x-1.6,31.55,10.55),(x-2.35,31.55,9.5)],
            [(0,1,2,3,4,5)],[portal])
        shield["mjolnir_pcg_policy"]="NONE"
        shield["noncolliding_portal"]=True

    return wall
