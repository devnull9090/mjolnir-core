"""Every frame of CE's seat idles, for ce_vehicle_rider.py. Reads the CE map through nx/rider/ce_rider.py."""
import os
import json
SP = os.environ["MJ_NATIVE_WORK"]
exec(open(SP + '/nx/rider/ce_rider.py').read().split("V=vehicle()")[0])
J = json.load(open(SP + '/nx/rider/ce_rider.json'))
e = tag('bipd', 'characters/cyborg_mp/cyborg_mp')
o = off(e['data'])
mod = dep(b, o + 0x28, tags)[2]
antr = dep(b, o + 0x38, tags)[2]
N, mks = model_markers(mod)
an, md = modes(off(antr['data']))
R = J['riders'][0]
out = dict(
    source="%s, %s" % (J['meta']['map_name'], R['antr']),
    vehicle=dict(markers={m['name']: dict(node=m['node_name'], position=m['vehicle_wu'], forward=m['forward'], left=m['left'], up=m['up']) for m in J['vehicle']['markers']}),
    rider=dict(nodes=[dict(name=n['name'], parent=n['parent'], translation=n['default_t'], rotation=n['default_q']) for n in R['nodes']],
               markers={m['name']: dict(node=m['node_name'], translation=m['t'], rotation=m['q']) for m in R['markers']}),
    seats=[])
for s in R['seats']:
    idle = [x for x in an if x['name'] == s['idle']['name']][0]
    frames = []
    for k in range(idle['frames']):
        frames.append([dict(rotation=[float(c) for c in x[0]], translation=[float(c) for c in x[1]]) for x in A.decode(idle, k)])
    out['seats'].append(dict(label=s['seat_label'], marker=s['seat_marker'], idle=s['idle']['name'],
                             ik_points=[dict(marker=p['marker'], attached_to=p['attached_to']) for p in s['ik_points']],
                             frames=frames))
json.dump(out, open(SP + '/nx/rider2/ce_seats.json', 'w'))
print({s['label']: len(s['frames']) for s in out['seats']})
