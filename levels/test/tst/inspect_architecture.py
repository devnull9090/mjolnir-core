"""Offline reflection and native-canopy checks for the northern structure.

Run against a generated preview.blend. No export, bake, or game operation.
"""
import argparse
import json
from pathlib import Path
import sys
import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--blend',type=Path,required=True)
parser.add_argument('--out',type=Path,required=True)
args=parser.parse_args(sys.argv[sys.argv.index('--')+1:])
bpy.ops.wm.open_mainfile(filepath=str(args.blend.resolve()),load_ui=False)
unit=3.048
vertices=[]; faces=[]
for obj in bpy.context.scene.objects:
    if obj.type!='MESH' or not obj.name.startswith(('tower_side_','tower_beacon_')):
        continue
    offset=len(vertices)
    vertices.extend(obj.matrix_world@v.co*unit for v in obj.data.vertices)
    faces.extend(tuple(offset+i for i in p.vertices) for p in obj.data.polygons)
assert vertices, 'No tower panel geometry found'
bvh=BVHTree.FromPolygons(vertices,faces)
errors=[]
for p in vertices:
    q=Vector((p.x,57.6-p.y,p.z))
    distance=bvh.find_nearest(q)[3]
    errors.append(distance)

# Separate railing caps/panel modules must stop before the three support bays.
# Test finished geometry bounds, not just the input recipe's intervals.
clasp_overlap=[]; rail_parts=0
for obj in bpy.context.scene.objects:
    if obj.type!='MESH' or not obj.name.startswith((
        'parapet_fitted_cap_plate','parapet_cap_pale_inner_edge',
        'parapet_recessed_dark_panel','parapet_inset_border',
        'parapet_segmented_pale_surround','parapet_charcoal_insert')): continue
    rail_parts+=1
    xs=[(obj.matrix_world@v.co).x*unit for v in obj.data.vertices]
    for center in (-53,0,53):
        if max(xs)>center-.65 and min(xs)<center+.65:
            clasp_overlap.append(obj.name)

# Conservative complete bounds include bark, branches and foliage cards. A
# positive gap separates every tree part from the entire balcony's front edge.
canopy_max_y=-float('inf'); tree_parts=0; canopy_bounds=[]
depsgraph=bpy.context.evaluated_depsgraph_get()
for instance in depsgraph.object_instances:
    if not instance.is_instance or instance.object.type!='MESH': continue
    parent=instance.parent
    asset=parent.get('ue_asset','') if parent else ''
    # Authored field-tree assemblies and their foliage. Ridge saplings behind
    # the north wall are a separate scenery group, outside this corridor check.
    if '/Tree/' not in asset or not parent.name.startswith(('NATIVE - swap_','NATIVE - leaves ')): continue
    tree_parts+=1
    corners=[instance.matrix_world@Vector(p)*unit for p in instance.object.bound_box]
    if max(p.z for p in corners)>=6.3:
        canopy_max_y=max(canopy_max_y,max(p.y for p in corners))
        canopy_bounds.append({'instance':parent.name,'object':instance.object.name,
                              'low':[min(p[k] for p in corners) for k in range(3)],
                              'high':[max(p[k] for p in corners) for k in range(3)]})
assert tree_parts, 'Native tree instances were not found'
report={
    'scope':'Blender geometry only; reflection of all tower armor surfaces and conservative full native field-tree bounds (excludes distant ridge saplings)',
    'panel_reflection_axis_y_m':28.8,
    'panel_vertices_checked':len(vertices),
    'panel_max_reflection_error_m':round(max(errors),7),
    'native_tree_parts_checked':tree_parts,
    'canopy_max_y_m':round(canopy_max_y,4),
    'metalwork_front_y_m':21.58,
    'canopy_to_metalwork_gap_m':round(21.58-canopy_max_y,4),
    'rail_modules_checked':rail_parts,
    'rail_clasp_overlaps':clasp_overlap,
    'northernmost_parts':sorted(canopy_bounds,key=lambda p:p['high'][1],reverse=True)[:5],
}
args.out.write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
assert max(errors)<.002, 'Tower side geometry is not symmetric within 2 mm'
assert not clasp_overlap, 'Railing cap or panel overlaps its central support bay'
assert canopy_max_y<21.35, 'Native canopy needs at least 25 cm clearance from balcony metalwork'
