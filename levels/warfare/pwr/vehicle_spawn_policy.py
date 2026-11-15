"""Sealed PWR correction for stationary vehicle abandonment after spawn settling.

Changes only eight Tank/Banshee origin heights and four QA volume heights.
No runtime hooks, timer changes, native writes, or in-place scenario edits.
"""
from __future__ import annotations
import argparse
import copy
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
POLICY = HERE / 'vehicle-spawn-policy-v1.json'
ACCEPTED_SHA256 = 'dd3d8a4c49c21c49d6242e4b4b9882ae819caa84f77b14205515ea998cfec0cf'
SUPPORT_CLEARANCE_M = .9
ABANDON_DISTANCE_M = .5 * 3.048


def require(condition, message):
    if not condition: raise ValueError(message)


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def read(path): return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def unique(rows, name):
    found = [row for row in rows if row.get('name') == name]
    require(len(found) == 1, 'Missing or duplicate native placement: '+name)
    return found[0]


def generate():
    # These existing validators independently pin the accepted v3 references.
    from check_native_contract import load_frozen_contract
    from world_placements import placements
    frozen, layout, level, field, geometry, _ = load_frozen_contract()
    authored = placements(layout, geometry, field)['vehicles']
    observation_path = ROOT/'out/pwr/world-v5/forest-r2/qa/vehicle-recycle-diagnosis.json'
    observations = {row['name']: row for row in read(observation_path)['vehicles']}
    counts, vehicles, probes = {}, [], []
    for placement in authored:
        kind = 'tank' if 'scorpion' in placement['tag'] else 'banshee' if 'banshee' in placement['tag'] else 'hog'
        team = ('red', 'blue')[placement['team']]
        index = counts.get((team, kind), 0); counts[team, kind] = index+1
        if kind == 'hog': continue
        name = f'pwr_{kind}_{team}_{index}'
        before = unique(level['blam']['vehicles'], name)
        expected_xy = [placement['position_m'][0]*100, -placement['position_m'][1]*100]
        require(before['pos'][:2] == expected_xy, 'Frozen vehicle XY does not match canonical placement')
        # world_placements explicitly lifts Tanks 1 m and Banshees 2 m above
        # support. The converter adds another 0.3 WU, which caused the defect.
        support = placement['position_m'][2]-(2 if kind == 'banshee' else 1)
        after = [*before['pos'][:2], round((support+SUPPORT_CLEARANCE_M)*100, 6)]
        actual = observations[name]
        settling = after[2]/100-actual['rest_median_z_m']
        require(.1 < settling < .75, 'Corrected spawn must clear the observed chassis and stay well below the native displacement threshold')
        require(actual['minimum_observed_health_percent'] == 100 and actual['completed_unavailability_intervals'],
                'Expected healthy repeated abandonment evidence')
        vehicles.append({'name': name, 'type': before['type'], 'old_pos_cm': before['pos'],
            'new_pos_cm': after, 'support_floor_m': support, 'observed_rest_origin_z_m': actual['rest_median_z_m'],
            'expected_initial_settling_m': settling, 'distance_threshold_margin_m': ABANDON_DISTANCE_M-settling,
            'unchanged_spawn_seconds': before['set']['multiplayer data.spawn time'],
            'unchanged_abandonment_seconds': before['set']['multiplayer data.abandonment time']})
        if index == 0:
            probe = unique(level['blam']['trigger_volumes'], f'pwr_probe_{kind}_{team}')
            require(probe['pos'][2] == before['pos'][2]-300, 'Unexpected frozen vehicle probe origin')
            probes.append({'name': probe['name'], 'old_pos_cm': probe['pos'],
                           'new_pos_cm': [*probe['pos'][:2], after[2]-300]})
    require(len(vehicles) == 8 and len(probes) == 4, 'Expected eight corrected vehicle origins and four related probes')
    dll = Path('C:/ghidra_proj/cu4/HaloSimulation_tag_release.dll')
    return {'schema': 'pwr-vehicle-spawn-correction-v1', 'protocol': 20569, 'layout_revision': 3,
        'revision': 1, 'support_clearance_m': SUPPORT_CLEARANCE_M,
        'scope': 'Only Tank/Banshee scenario-origin Z and matching probe-volume Z; physical terrain and settled destinations are unchanged',
        'frozen_references': {key: frozen[key] for key in ('layout', 'geometry', 'level_gameplay')},
        'frozen_runtime_manifest_sha256': field.manifest_sha256,
        'frozen_runtime_height_sha256': field.metadata['height']['sha256'],
        'cause': {'binary': str(dll), 'binary_sha256': sha(dll), 'distance_predicate_rva': '0x3f8130',
            'distance_squared_wu': .25, 'distance_metres': ABANDON_DISTANCE_M,
            'abandonment_update_rva': '0x3f7a60', 'respawn_update_rva': '0x3f72b0',
            'observation_sha256': sha(observation_path)},
        'vehicles': vehicles, 'probes': probes,
        'live_acceptance_required': ['all eight stationary vehicles retained for more than two original recycle cycles',
            'initial chassis/floor clearance and guarded Tank/Banshee driving',
            'driven-away abandonment and destroyed-vehicle respawn with original timers'],
        'native_binary_or_layout_constants_changed': False}


def load_policy(path=POLICY):
    path = Path(path).resolve()
    require(sha(path) == ACCEPTED_SHA256, 'Vehicle spawn policy differs from the explicitly reviewed sealed correction')
    doc = read(path)
    require(doc['schema'] == 'pwr-vehicle-spawn-correction-v1' and doc['protocol'] == 20569
            and doc['layout_revision'] == 3 and len(doc['vehicles']) == 8 and len(doc['probes']) == 4,
            'Unsupported vehicle spawn correction')
    return doc


def transform(level, policy, revert=False):
    result = copy.deepcopy(level)
    states = []
    operations = []
    for collection, key in (('vehicles', 'vehicles'), ('trigger_volumes', 'probes')):
        for change in policy[key]:
            item = unique(result['blam'][collection], change['name'])
            if key == 'vehicles':
                require(item['type'] == change['type'], 'Vehicle type changed')
                require(item['set']['multiplayer data.spawn time'] == change['unchanged_spawn_seconds']
                        and item['set']['multiplayer data.abandonment time'] == change['unchanged_abandonment_seconds'],
                        'Vehicle respawn/abandonment timers must remain unchanged')
            if item['pos'] == change['old_pos_cm']: states.append('old')
            elif item['pos'] == change['new_pos_cm']: states.append('new')
            else: raise ValueError('Placement is neither the frozen nor sealed corrected position: '+change['name'])
            operations.append((item, change))
    require(len(set(states)) == 1, 'Partially applied vehicle policy; refusing to normalize or patch')
    if revert: require(states[0] == 'new', 'Explicit correction policy requires the corrected scenario, not an unchanged old one')
    for item, change in operations: item['pos'] = copy.deepcopy(change['old_pos_cm' if revert else 'new_pos_cm'])
    return result


def validate_level(level, policy_path=POLICY):
    """Return exact frozen-shape gameplay for the existing strict comparator."""
    policy = load_policy(policy_path)
    restored = transform(level, policy, revert=True)
    return restored, {'policy_sha256': sha(policy_path), 'vehicle_origins': 8, 'probe_origins': 4,
        'support_clearance_m': SUPPORT_CLEARANCE_M, 'native_distance_threshold_m': ABANDON_DISTANCE_M,
        'timers_preserved': True, 'live_acceptance_required': True}


def patch_file(source, output, policy_path=POLICY):
    source, output = Path(source).resolve(), Path(output).resolve()
    require(source != output, 'An independent output path is required; no in-place scenario mutation')
    require(not output.exists(), 'Output already exists; preserve earlier proposal evidence')
    source_hash = sha(source)
    policy = load_policy(policy_path)
    original = read(source)
    patched = transform(original, policy)
    # This check prevents an otherwise valid Z policy being applied to a map
    # whose timers, labels, spawns, routes, or any other native field drifted.
    from check_native_contract import load_frozen_contract, gameplay_level, assert_equal
    _, _, frozen_level, *_ = load_frozen_contract()
    assert_equal(frozen_level, gameplay_level(transform(patched, policy, revert=True)), 'corrected gameplay scenario')
    require(sha(source) == source_hash, 'Source changed during preparation')
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(patched, indent=2)+'\n', encoding='utf-8')
    receipt = {'schema': 'pwr-vehicle-spawn-patch-v1', 'source': str(source), 'source_sha256': source_hash,
        'output': str(output), 'output_sha256': sha(output), 'policy': str(Path(policy_path).resolve()),
        'policy_sha256': sha(policy_path), 'changed_vehicle_origins': 8, 'changed_probe_origins': 4,
        'all_other_gameplay_exact': True, 'timers_preserved': True, 'installed': False,
        'live_acceptance_required': True}
    output.with_suffix(output.suffix+'.spawn-policy.receipt.json').write_text(json.dumps(receipt, indent=2)+'\n')
    return receipt


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('command', choices=['generate', 'patch'])
    p.add_argument('--level', type=Path)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--policy', type=Path, default=POLICY)
    args = p.parse_args()
    if args.command == 'generate':
        require(not args.out.exists(), 'Refusing to overwrite an existing correction policy')
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(generate(), indent=2)+'\n')
        print('Generated policy SHA256:', sha(args.out))
    else:
        if not args.level: p.error('--level is required for patch')
        print(json.dumps(patch_file(args.level, args.out, args.policy), indent=2))
