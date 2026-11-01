"""Localised wear on actual generated facility chamfers, never overlay meshes.

The builder reserves a duplicate slot pointing to the original material before
applying the bevel. This identifies only faces created by that modifier. Closed
solids are then split at shared vertices, and selected short bevel runs receive
an existing dark mineral finish. Angular, tapered boundary profiles cross each
bevel rather than forming square-ended bands. Original faces and silhouettes
remain intact.
"""
import hashlib
import math


def prepare(obj, bevel, metres_per_ce):
    if not obj.get('tst_facility') or not obj.get('mjolnir_render_detail'):
        return False
    name=obj.name
    near_rib=name.startswith('facility_branch_rib') and max(abs(v.co.x)*metres_per_ce for v in obj.data.vertices)<17
    near_coffer=name.startswith(('facility_foyer_coffer_border','facility_branch_coffer_cross_border')) and max(abs(v.co.x)*metres_per_ce for v in obj.data.vertices)<17
    door=name.startswith('facility_service_foyer_') and any(part in name for part in ('_structural_surround_','_precision_lip_'))
    if not (near_rib or near_coffer or door): return False
    if not obj.data.materials: return False
    # Duplicating a slot does not create a material or brighten untouched edges.
    original_index=0
    marker=len(obj.data.materials)
    obj.data.materials.append(obj.data.materials[original_index])
    bevel.material=marker
    obj['facility_bevel_marker_slot']=marker
    obj['facility_bevel_original_slot']=original_index
    return True


def apply(obj, metres_per_ce):
    if 'facility_bevel_marker_slot' not in obj: return
    import bmesh
    from mathutils import Vector
    from architecture_surfaces import blender_material
    marker=int(obj['facility_bevel_marker_slot'])
    original=int(obj['facility_bevel_original_slot'])
    bm=bmesh.new(); bm.from_mesh(obj.data)
    phase_layer=bm.faces.layers.int.new('facility_bevel_wear_group')
    strip_layer=bm.faces.layers.int.new('facility_bevel_wear_strip')
    candidates=[]
    for face in bm.faces:
        if face.material_index!=marker: continue
        perimeter=sum(edge.calc_length() for edge in face.edges)
        width=2*face.calc_area()*metres_per_ce/max(perimeter,1e-10)
        edge=max(face.edges,key=lambda edge:edge.calc_length())
        length=edge.calc_length()*metres_per_ce
        if .001<width<.060 and length>.35:
            candidates.append((length,face,edge))
    if not candidates:
        for face in bm.faces:
            if face.material_index==marker: face.material_index=original
        bm.to_mesh(obj.data); bm.free()
        del obj['facility_bevel_marker_slot']; del obj['facility_bevel_original_slot']
        return
    _,_,long_edge=max(candidates,key=lambda item:item[0])
    axis=(long_edge.verts[1].co-long_edge.verts[0].co).normalized()
    if axis[max(range(3),key=lambda index:abs(axis[index]))]<0: axis=-axis
    seed=int.from_bytes(hashlib.sha256(obj.name.encode()).digest()[:4],'little')
    strips=[]
    for _,face,edge in candidates:
        direction=(edge.verts[1].co-edge.verts[0].co).normalized()
        if abs(direction.dot(axis))>.94:
            # Different normal directions use different offsets so the wear
            # never forms tape-like rings around an entire structural piece.
            normal_key=sum((index+3)*int(round((value+1)*7)) for index,value in enumerate(face.normal))
            face[phase_layer]=1+(normal_key+seed)%2
            face[strip_layer]=len(strips)+1
            across=face.normal.cross(axis).normalized()
            transverse=[vert.co.dot(across)*metres_per_ce for vert in face.verts]
            strips.append((face[strip_layer],face[phase_layer],across,min(transverse),max(transverse),normal_key))
    positions=[v.co.dot(axis)*metres_per_ce for v in bm.verts]
    lo,hi=min(positions),max(positions)
    length=hi-lo
    width=.075+.035*((seed%101)/100)
    spacing=width/.17
    intervals={}
    for group in (1,2):
        phase=((seed//(17*group))%97)/97
        first=lo+.06+phase*spacing+(.24*spacing if group==2 else 0)
        bands=[]; start=first
        while start+width<hi-.045:
            bands.append((start,start+width)); start+=spacing
        if not bands and length>.42:
            start=lo+length*(.32 if group==1 else .57)
            bands=[(start,min(start+width,hi-.045))]
        intervals[group]=bands
    def split_faces(faces,point,normal):
        # BMesh splits shared boundary edges in adjacent faces as well. Restrict
        # the cut faces to this bevel lane: broad faces keep their finish, and
        # a boundary does not continue as a uniform ring around the whole part.
        if not faces:return
        edges={edge for face in faces for edge in face.edges}
        verts={vert for edge in edges for vert in edge.verts}
        bm.verts.index_update();bm.edges.index_update()
        bmesh.ops.bisect_plane(bm,geom=sorted(verts,key=lambda vert:vert.index)+sorted(edges,key=lambda edge:edge.index)+faces,
            dist=1e-8,plane_co=point,plane_no=normal,
            clear_inner=False,clear_outer=False)

    def centered_offsets(values,amount):
        # Piecewise-linear integral over t=(0,.34,.69,1). Subtract its mean
        # so tapering changes patch shape, not average worn length/coverage.
        stops=(0,.34,.69,1)
        average=sum((b-a)*(values[i]+values[i+1])*.5
                    for i,(a,b) in enumerate(zip(stops,stops[1:])))
        return [(value-average)*amount for value in values]

    profiles={}
    stagger_ranges=[]
    for strip,group,across,low,high,normal_key in strips:
        stops=[low+(high-low)*fraction for fraction in (0,.34,.69,1)]
        for cut in stops[1:-1]:
            faces=[face for face in bm.faces if face[strip_layer]==strip]
            split_faces(faces,across*(cut/metres_per_ce),across)
        boundaries=[]
        for number,(start,end) in enumerate(intervals[group]):
            code=int.from_bytes(hashlib.sha256(f'{seed}:{normal_key}:{strip}:{number}'.encode()).digest()[:4],'little')
            amount=.012+.016*((code%101)/100)
            sign=1 if code&1 else -1
            leading=centered_offsets([-.45,.55,-.20,.25],amount*sign)
            trailing=centered_offsets([.40,-.55,.15,-.35],amount*(-sign if code&2 else sign))
            starts=[start+offset for offset in leading]
            ends=[end+offset for offset in trailing]
            boundaries.append((starts,ends))
            stagger_ranges.extend((max(leading)-min(leading),max(trailing)-min(trailing)))
            for lane,(t0,t1) in enumerate(zip(stops,stops[1:])):
                for values in (starts,ends):
                    slope=(values[lane+1]-values[lane])/(t1-t0)
                    normal=(axis-across*slope).normalized()
                    point=(axis*values[lane]+across*t0)/metres_per_ce
                    faces=[face for face in bm.faces if face[strip_layer]==strip and
                           t0-1e-8<face.calc_center_median().dot(across)*metres_per_ce<t1+1e-8]
                    split_faces(faces,point,normal)
        profiles[strip]=(across,stops,boundaries)
    dark=blender_material('facility_recess',True)
    dark_index=next((i for i,material in enumerate(obj.data.materials) if material==dark),None)
    if dark_index is None:
        dark_index=len(obj.data.materials); obj.data.materials.append(dark)
    worn_area=0; bevel_area=0; worn_faces=0
    for face in bm.faces:
        if face.material_index!=marker: continue
        group=face[phase_layer]
        face.material_index=original
        if not group: continue
        bevel_area+=face.calc_area()
        center=face.calc_center_median()*metres_per_ce
        distance=center.dot(axis)
        across,stops,boundaries=profiles[face[strip_layer]]
        transverse=center.dot(across)
        lane=next((index for index in range(3) if transverse<=stops[index+1]+1e-7),2)
        weight=max(0,min(1,(transverse-stops[lane])/(stops[lane+1]-stops[lane])))
        def along(values):return values[lane]+(values[lane+1]-values[lane])*weight
        if any(along(starts)-1e-7<=distance<=along(ends)+1e-7 for starts,ends in boundaries):
            face.material_index=dark_index
            worn_area+=face.calc_area(); worn_faces+=1
    if any(not edge.is_manifold for edge in bm.edges):
        bm.free()
        raise RuntimeError('Facility bevel wear opened a closed solid: '+obj.name)
    bmesh.ops.recalc_face_normals(bm,faces=list(bm.faces))
    bm.to_mesh(obj.data); bm.free(); obj.data.update()
    obj['facility_edge_wear']='Actual bevel faces only; angular tapered boundaries, shared vertices, existing dark mineral finish, no silhouette displacement.'
    obj['facility_edge_worn_fraction']=round(worn_area/max(bevel_area,1e-12),4)
    obj['facility_edge_worn_faces']=worn_faces
    obj['facility_edge_wear_run_m']=round(width,4)
    obj['facility_edge_wear_boundary']='Three transverse lanes; independently tapered four-point leading/trailing profiles, zero-mean offsets.'
    obj['facility_edge_wear_stagger_m']=[round(min(stagger_ranges),5),round(max(stagger_ranges),5)] if stagger_ranges else [0,0]
    del obj['facility_bevel_marker_slot']; del obj['facility_bevel_original_slot']
