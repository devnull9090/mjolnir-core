"""Isolated irregular scarp placement proposal; never replaces installed decor/collision.

This is an authored candidate selection for review, not a claim of a new UE PCG run.
Existing 298 boulders and 218 shore rocks are inputs only and remain unchanged.
"""
from pathlib import Path
import argparse
import hashlib
import json
import math
import sys
import numpy as np
from scipy.spatial import cKDTree
from scipy.ndimage import distance_transform_edt

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT/'tools/level'))
from heightfield import load_heightfield

OUT = ROOT/'out/pwr/visual-v5/outcrops-v2'
MASTER = ROOT/'levels/warfare/pwr/terrain/runtime-v5/runtime-master.json'
ROLES = {
    'embedded_macro': ('SM_PNWGL_Rock_Macro_B', 2, (.17, .22), (.55, 2.4), .62),
    'embedded_cliff': ('SM_Rock_Uluwatu_Cliff_B', 12, (.35, .55), (.45, 2.1), .48),
    'horizontal_shelf': ('SM_MassiveTundraRockFormation_01', 24, (.5, 1.0), (.18, 1.25), .28),
    'granite_ledge': ('SM_Rock_CliffFlat_Kit_B', 20, (.9, 1.5), (.15, 1.0), .32),
}


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    field = load_heightfield(MASTER)
    catalogue = json.loads((ROOT/'out/pwr/visual-v4/assets/rock-bounds.json').read_text())
    trees_path = ROOT/'out/pwr/pcg-v5/trees.selected.json'
    trees = np.array([x['position'][:2] for x in json.loads(trees_path.read_text())['instances']])
    tree = cKDTree(trees)
    masks = field.masks
    forbidden = ((masks['road']>.002)|(masks['water']>.002)|(masks['shore']>.02)|(masks['bases']>.002))
    clearance = distance_transform_edt(~forbidden, sampling=field.spacing_m[0])
    random = np.random.default_rng(20589)
    selected, palette, receipts = [], {}, []
    for role, (leaf, limit, scales, slopes, bury) in ROLES.items():
        source = next(x for x in catalogue if x['path'].split('.')[-1] == leaf)
        lo, hi = np.array(source['min'])/100, np.array(source['max'])/100
        max_radius = math.hypot(max(abs(lo[0]), abs(hi[0])), max(abs(lo[1]), abs(hi[1])))
        palette[role] = {'mesh': source['path'], 'bounds_m': [lo.tolist(), hi.tolist()],
                         'maximum_count': limit, 'scale_range': scales, 'bury_height_fraction': bury,
                         'verification': 'native catalogue bounds; CliffFlat shape/material preview still required' if role=='granite_ledge' else 'previously exported native Nanite mesh'}
        xy = random.uniform(-930, 930, (30000, 2))
        scale = random.uniform(*scales, len(xy)); radii = max_radius*scale
        z = field.sample(xy[:, 0], xy[:, 1])
        dx = (field.sample(xy[:, 0]+3, xy[:, 1])-field.sample(xy[:, 0]-3, xy[:, 1]))/6
        dy = (field.sample(xy[:, 0], xy[:, 1]+3)-field.sample(xy[:, 0], xy[:, 1]-3))/6
        slope = np.hypot(dx, dy)
        grid = np.round((xy-np.array(field.origin_m))/np.array(field.spacing_m)).astype(int)
        distance = clearance[grid[:, 1], grid[:, 0]]-math.sqrt(2)*field.spacing_m[0]
        near_tree = tree.query(xy)[0]
        allowed = ((distance>radii+12)&(near_tree>radii+8)&(slope>=slopes[0])&(slope<=slopes[1])
                   &(z>130)&(z<365)&(np.max(abs(xy), axis=1)+radii<950))
        # Continuous random candidates, then footprint-aware inhibition. Neither
        # grid rows nor a target-count density multiplier determines the output.
        priority = random.random(len(xy))*(.6+np.clip(slope, 0, 1.2))
        count = 0
        for i in np.argsort(priority)[::-1]:
            if not allowed[i]:
                continue
            if selected and any(np.linalg.norm(xy[i]-np.array(p['xy'])) < radii[i]+p['radius_m']+10 for p in selected):
                continue
            yaw_author = math.atan2(dy[i], dx[i])+math.pi/2+random.uniform(-.24, .24)
            c, s = math.cos(yaw_author), math.sin(yaw_author)
            rotation = np.array([[c, -s], [s, c]])
            # Sample the complete conservative bounding rectangle to bury rather
            # than perch a pillar. Export/render/native hull must share this pose.
            xx, yy = np.meshgrid(np.linspace(lo[0], hi[0], 7), np.linspace(lo[1], hi[1], 7))
            rectangle = np.c_[xx.ravel(), -yy.ravel()]*scale[i]@rotation.T+xy[i]
            support = field.sample(rectangle[:, 0], rectangle[:, 1])
            height = (hi[2]-lo[2])*scale[i]
            actor_z = float(np.quantile(support, .25)-lo[2]*scale[i]-bury*height)
            ident = f'pwr_proposed_{role}_{count:02d}'
            decor = {'id': ident, 'mesh': source['path'], 'pos': [float(xy[i,0]*100), float(-xy[i,1]*100), actor_z*100],
                     'rot': [0, float(-math.degrees(yaw_author)), 0], 'scale': [float(scale[i])]*3, 'static': True}
            row = {'id': ident, 'role': role, 'xy': xy[i].tolist(), 'radius_m': float(radii[i]), 'decor': decor}
            selected.append(row)
            receipts.append({'id': ident, 'world_xy_m': xy[i].tolist(), 'full_footprint_radius_m': float(radii[i]),
                             'road_water_base_clearance_beyond_footprint_m': float(distance[i]-radii[i]),
                             'tree_root_clearance_beyond_footprint_m': float(near_tree[i]-radii[i]),
                             'terrain_slope': float(slope[i]), 'yaw_basis': 'local contour plus bounded14degree variation',
                             'bury_height_fraction': bury, 'vertical_support_range_m': [float(support.min()), float(support.max())]})
            count += 1
            if count == limit:
                break
    before_path = ROOT/'out/pwr/visual-v5/outcrops.authored-decor.json'
    before = json.loads(before_path.read_text())['decor']
    document = {'schema': 'pwr-outcrop-proposal-v2', 'status': 'review candidate; no actual PCG/cook/native collision/install yet',
                'runtime_master_sha256': field.manifest_sha256, 'original_outcrops_sha256': digest(before_path),
                'selected_trees_sha256': digest(trees_path), 'seed': 20589, 'palette': palette,
                'preserves_existing_boulders': 298, 'preserves_existing_shore_rocks': 218,
                'replace_only': '108 outcrop records, after review and regenerated native scenery collision/probes',
                'before_count': len(before), 'proposed_count': len(selected),
                'proposed_decor': [x['decor'] for x in selected], 'footprint_checks': receipts,
                'required_before_integration': ['Inspect CliffFlat native geometry/material and orientation',
                    'Actual PCG graph and repeat proof for the reviewed candidate set',
                    'Generate matching native hulls and refresh grass exclusions',
                    'Recompile scenery collision and regenerate actual seam/probe hashes',
                    'Actual in-game review and vehicle/native acceptance']}
    (OUT/'proposal.json').write_text(json.dumps(document, indent=2)+'\n')
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.patches import Circle
    fig, axes = plt.subplots(1, 2, figsize=(15, 7), constrained_layout=True)
    extent = [-1000, 1000, -1000, 1000]
    for ax in axes:
        ax.imshow(field.heights_m, extent=extent, origin='lower', cmap='Greys', alpha=.48)
        ax.contour(forbidden.astype(float), [.5], extent=extent, origin='lower', colors='#cc985a', linewidths=.5)
        ax.set(xlim=(-1000,1000), ylim=(-1000,1000), xlabel='Authoring X (m)', ylabel='Authoring Y (m)')
    axes[0].scatter([x['pos'][0]/100 for x in before], [-x['pos'][1]/100 for x in before], s=24, c='#ce493c')
    axes[0].set_title('Installed v5: 108 outcrops; 68 identical column cliffs')
    colors = {'embedded_macro':'#8d5a40','embedded_cliff':'#c87236','horizontal_shelf':'#2d766b','granite_ledge':'#296a9a'}
    for role in ROLES:
        items=[x for x in selected if x['role']==role]
        axes[1].scatter([x['xy'][0] for x in items], [x['xy'][1] for x in items], c=colors[role], s=24, label=f'{role}: {len(items)}')
        for item in items:
            axes[1].add_patch(Circle(item['xy'], item['radius_m'], fill=False, color=colors[role], linewidth=.5, alpha=.6))
    axes[1].legend(fontsize=8, loc='lower left')
    axes[1].set_title(f'Proposal: {len(selected)} irregular embedded scarps/ledges; circles = full footprint')
    fig.suptitle('Authoring placement comparison only — fixed terrain, roads, bases, boulders and shore unchanged')
    fig.savefig(OUT/'before-after-footprints.png', dpi=150)
    print(json.dumps({'proposal': str(OUT/'proposal.json'), 'before': len(before), 'proposed': len(selected),
                      'minimum_route_clearance_m': min(x['road_water_base_clearance_beyond_footprint_m'] for x in receipts),
                      'minimum_tree_clearance_m': min(x['tree_root_clearance_beyond_footprint_m'] for x in receipts)}))


def assemble():
    proposal_path=OUT/'proposal.json';proposal=json.loads(proposal_path.read_text())
    field=load_heightfield(MASTER)
    if proposal['runtime_master_sha256']!=field.manifest_sha256:
        raise ValueError('Proposed placements belong to another terrain')
    preview=OUT/'preview.receipt.json'
    if not preview.is_file() or json.loads(preview.read_text())['proposed_count']!=proposal['proposed_count']:
        raise ValueError('Complete the native geometry preview before assembling a candidate')
    paths={'boulders':ROOT/'out/pwr/visual-v5/temperate-rocks.authored-decor.json',
           'shore':ROOT/'out/pwr/visual-v5/shore/shore.authored-decor.json'}
    documents={key:json.loads(path.read_text()) for key,path in paths.items()}
    assert len(documents['boulders']['decor'])==298 and len(documents['shore']['decor'])==218
    fixed=documents['boulders']['decor']+documents['shore']['decor']
    decor=fixed+proposal['proposed_decor']
    assert len({row['id'] for row in decor})==len(decor)==574
    result={'schema_version':1,'coordinates':'unreal_centimetres','decor':decor,
        'status':'candidate only; new outcrops are reviewed authoring proposals, not a completed PCG/native collision/live acceptance',
        'visual_v4_provenance':{'frozen_runtime_master_sha256':field.manifest_sha256,
            'proposal_sha256':digest(proposal_path),'geometry_preview_sha256':digest(preview),
            'unchanged_sources':{key:{'path':str(path),'sha256':digest(path),'count':len(documents[key]['decor'])} for key,path in paths.items()},
            'preserved_record_count':len(fixed),'proposed_outcrop_count':len(proposal['proposed_decor']),
            'requires_new_scenery_collision_and_probes':True}}
    output=OUT/'rocks-and-outcrops.authored-decor.json'
    output.write_text(json.dumps(result,indent=2)+'\n')
    reloaded=json.loads(output.read_text())
    assert reloaded['decor'][:516]==fixed
    print(json.dumps({'output':str(output),'unchanged_boulders':298,'unchanged_shore':218,'proposed_outcrops':58,'total':len(decor),'current_decor_unchanged':True}))


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--assemble',action='store_true')
    args=parser.parse_args()
    assemble() if args.assemble else main()
