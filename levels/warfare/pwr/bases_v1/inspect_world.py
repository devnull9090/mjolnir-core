"""Inspect the existing offline world, never invoking a game or editor."""
from pathlib import Path
import bpy, json, collections
ROOT = Path(__file__).resolve().parents[4]
OUT = ROOT / 'out/pwr/base-integration'
SOURCE = ROOT / 'out/pwr/visual-v8/foothills/preview-clustered/foothills-v8.blend'
if bpy.data.is_dirty:
    raise RuntimeError('Save the current scene before switching files')
bpy.ops.wm.open_mainfile(filepath=str(SOURCE))
s = bpy.context.scene
report = {'file': str(SOURCE), 'scene': s.name, 'units': s.unit_settings.scale_length,
          'objects': len(s.objects), 'collections': {c.name: len(c.objects) for c in bpy.data.collections},
          'objects_summary': []}
for o in s.objects:
    # Compact inventory enough to identify old structures and exact ground.
    if o.type != 'MESH' or not any(x in o.name.lower() for x in ('tree','pine','rock','cliff','grass','foliage')):
        report['objects_summary'].append({'name': o.name, 'type':o.type, 'location':list(o.location),
          'dimensions':list(o.dimensions), 'hidden_render':o.hide_render,
          'collections':[c.name for c in o.users_collection], 'properties':dict(o.items())})
OUT.mkdir(parents=True, exist_ok=True)
(OUT/'world-inventory.json').write_text(json.dumps(report, indent=2, default=str))
print(json.dumps({'file': str(SOURCE), 'objects':len(s.objects), 'units': s.unit_settings.scale_length,
                 'inventory':str(OUT/'world-inventory.json')}))
