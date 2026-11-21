"""Export raw placed structural meshes for a separately validated native build.

Decorative modifiers are deliberately excluded. Dense native trim is inventoried
separately; the collision compiler selects explicit structural modules and must
prove floor/air clearances rather than convex-filling the buildings.
"""
from pathlib import Path
import bpy,json,hashlib
from mathutils import Vector
ROOT=Path(__file__).resolve().parents[4]
OUT=ROOT/'out/pwr/base-runtime'

def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    return h.hexdigest()

def main():
    source=ROOT/'out/pwr/base-integration/pwr-world-bases-v1.blend'
    if Path(bpy.data.filepath).resolve()!=source.resolve() or bpy.data.is_dirty:
        raise RuntimeError('Export from the clean, sealed integrated world')
    bpy.context.view_layer.update();rows=[];omitted=[]
    for ob in bpy.context.scene.objects:
        if ob.type!='MESH' or not(ob.get('world_base_team') or ob.get('offline_collision_candidate')):continue
        corners=[ob.matrix_world@Vector(q) for q in ob.bound_box]
        row={'name':ob.name,'team':ob.get('world_base_team',ob.get('team')),
             'module_role':ob.get('module_role',ob.get('part_role','')),
             'source_mesh':ob.data.name,'stock_source_file':ob.get('stock_source_file'),
             'bounds_m':{'min':[min(q[k] for q in corners) for k in range(3)],'max':[max(q[k] for q in corners) for k in range(3)]},
             'modifiers_omitted':[m.type for m in ob.modifiers],
             'world_matrix':[list(r) for r in ob.matrix_world]}
        if ob.get('stock_source_file'):
            row['reason']='Dense native decorative panel/pillar; replacement structural collision requires explicit review'
            omitted.append(row);continue
        me=ob.data;me.calc_loop_triangles()
        row['vertices_m']=[list(ob.matrix_world@v.co) for v in me.vertices]
        reverse=ob.matrix_world.determinant()<0
        row['triangles']=[list(reversed(t.vertices)) if reverse else list(t.vertices) for t in me.loop_triangles]
        row['negative_determinant_winding_repaired']=reverse
        row['material']='hard_metal_thick'
        rows.append(row)
    doc={'schema':'pwr-base-collision-source-v1','coordinates':'authoring_metres_z_up',
         'source_blend':str(source),'source_blend_sha256':sha(source),
         'placement_plan_sha256':sha(ROOT/'out/pwr/base-integration/placement-plan.json'),
         'objects':rows,'omitted_native_decor':omitted,'runtime_installed':False}
    path=OUT/'collision-authored.json';path.write_text(json.dumps(doc,separators=(',',':'))+'\n')
    print(json.dumps({'output':str(path),'objects':len(rows),'triangles':sum(len(o['triangles']) for o in rows),
                      'omitted_stock_objects':len(omitted),'sha256':sha(path)}))

if __name__=='__main__':main()
