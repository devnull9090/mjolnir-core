"""Export current authored BSP to the existing scatter sampler without HEK.

Only geometry/UVs and a mapping to the existing CE shader spec are emitted.
The obsolete lightmap is explicitly replaced with neutral white for preview.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys
import bpy

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--blend',type=Path,required=True)
p.add_argument('--spec',type=Path,required=True)
p.add_argument('--out',type=Path,required=True)
a=p.parse_args(sys.argv[sys.argv.index('--')+1:])
a.out.mkdir(parents=True,exist_ok=True)
bpy.ops.wm.open_mainfile(filepath=str(a.blend.resolve()))
scale=bpy.context.scene.unit_settings.scale_length
spec=json.loads(a.spec.read_text())
mapping={}
for name,match in [('beach','levels_b30_shaders_beach'),('tst_cliffs','levels_test_tst_shaders_tst_cliffs')]:
    mapping[name]=next(s['pattern'].rstrip('$') for s in spec['slots'] if s['pattern'].startswith(match))
doc={'asset':{'version':'2.0'},'buffers':[{'uri':'scene.bin','byteLength':0}],
     'bufferViews':[],'accessors':[],'materials':[],'meshes':[{'primitives':[]}],
     'nodes':[{'mesh':0}],'scenes':[{'nodes':[0]}],'scene':0}
binary=bytearray()
def acc(values,width,kind):
    offset=len(binary)
    if kind==5126:
        binary.extend(struct.pack('<'+'f'*len(values),*values))
    else:
        binary.extend(struct.pack('<'+'I'*len(values),*values))
    view=len(doc['bufferViews']); doc['bufferViews'].append({'buffer':0,'byteOffset':offset,'byteLength':len(binary)-offset})
    index=len(doc['accessors'])
    entry={'bufferView':view,'componentType':kind,'count':len(values)//width,'type':{1:'SCALAR',2:'VEC2',3:'VEC3'}[width]}
    if width==3:
        entry['min']=[min(values[i::3]) for i in range(3)]
        entry['max']=[max(values[i::3]) for i in range(3)]
    doc['accessors'].append(entry)
    return index
groups={}
for obj in bpy.context.scene.objects:
    if obj.type!='MESH' or obj.hide_render or obj.name.startswith('SOURCE_') or obj.get('mjolnir_preview_only'):
        continue
    mesh=obj.data; mesh.calc_loop_triangles()
    for tri in mesh.loop_triangles:
        material=mesh.materials[tri.material_index]
        if 'sky' in material.name.lower(): continue
        key=mapping.get(material.name,material.name)
        positions,uv=groups.setdefault(key,([],[]))
        for loop in tri.loops:
            co=(obj.matrix_world @ mesh.vertices[mesh.loops[loop].vertex_index].co)*scale
            positions.extend((co.x,co.z,-co.y))
            v=mesh.uv_layers.active.data[loop].uv if mesh.uv_layers.active else (0,0)
            uv.extend((v[0],v[1]))
for key,(positions,uv) in groups.items():
    material=len(doc['materials']); doc['materials'].append({'name':key})
    pa=acc(positions,3,5126); ua=acc(uv,2,5126)
    ia=acc(list(range(len(positions)//3)),1,5125)
    doc['meshes'][0]['primitives'].append({'attributes':{'POSITION':pa,'TEXCOORD_0':ua,'TEXCOORD_1':ua},'indices':ia,'material':material})
doc['buffers'][0]['byteLength']=len(binary)
(a.out/'scene.bin').write_bytes(binary)
(a.out/'scene.gltf').write_text(json.dumps(doc),encoding='utf-8')
# No new bake exists: the sampler needs a lightmap only for tint, so use white.
image=bpy.data.images.new('UNBAKED neutral light',width=1,height=1)
image.pixels=[1,1,1,1]; image.filepath_raw=str((a.out/'neutral.png').resolve()); image.file_format='PNG'; image.save()
for s in spec['slots']:
    if 'Lightmap' in s['material'].get('textures',{}):
        s['material']['textures']['Lightmap']='/Preview/T_neutral.T_neutral'
spec['textures'].append({'name':'T_neutral','file':str((a.out/'neutral.png').resolve())})
(a.out/'materials.spec.json').write_text(json.dumps(spec),encoding='utf-8')
(a.out/'source.json').write_text(json.dumps({'blend':str(a.blend.resolve()),
    'sha256':hashlib.sha256(a.blend.read_bytes()).hexdigest(),
    'note':'Actual current BSP/UVs and existing CE biome shader inputs; neutral unbaked lightmap.'}),encoding='utf-8')
print('SCATTER_SOURCE',sum(len(v[0])//9 for v in groups.values()),'triangles')
