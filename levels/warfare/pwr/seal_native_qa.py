"""Offline artifact seal for PWR QA with the explicit vehicle spawn correction.

The installed receipt, compiled refresh and scenery seal must all be supplied.
This tool reads installed files; it never starts or communicates with the game.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

from check_native_contract import assert_equal, gameplay_level, load_frozen_contract
from vehicle_spawn_policy import validate_level, load_policy, sha, read, require

ROOT = Path(__file__).resolve().parents[3]
DLL_SHA = '3d5cab72d5ac7fd25278d29aff254d26faa5b6e54150e154ee56462c34e3e3af'
RULES_SHA = '59e5cbfe1bd19aa5b06c60da63a7f8a5b41358f819f5cc7ee23f19a15c889ec1'


def record(path, expected=None):
    path = Path(path).resolve()
    digest = sha(path)
    require(expected is None or digest == expected, 'Artifact differs from receipt: '+str(path))
    return {'path': str(path), 'sha256': digest, 'bytes': path.stat().st_size}


def write_new(path, doc):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf-8') as stream:
        stream.write(json.dumps(doc, indent=2)+'\n')


def check_prepared_level(level, policy_path, contract, plan_path):
    normalized, policy = validate_level(level, policy_path)
    assert_equal(load_frozen_contract()[2], gameplay_level(normalized), 'installed native gameplay')
    require(contract.get('layout3_permitted') is True and contract.get('terrain_contract_compatible') is True,
            'Full compiled native contract must pass')
    require(contract.get('vehicle_spawn_policy') == policy, 'Contract did not explicitly accept this exact spawn policy')
    digest = sha(plan_path)
    require(contract.get('probe_plan_sha256') == digest, 'Contract does not bind the fresh compiled probe plan')
    plan = read(plan_path)
    require(plan.get('schema') == 'pwr-terrain-probe-v1' and plan.get('protocol') == 20569
            and plan.get('layout_revision') == 3 and len(plan.get('probes', [])) == 12
            and len({row['flag'] for row in plan['probes']}) == 12, 'Expected twelve distinct compiled probes')
    expected = [{'name': row['flag'], 'pos': [100*row['position_m'][0], -100*row['position_m'][1],
                100*row['position_m'][2]], 'yaw': row['yaw']} for row in plan['probes']]
    expected.append({'name': 'terrain_probe_hash_'+digest[:12], 'pos': expected[-1]['pos'], 'yaw': 0})
    actual = [row for row in level['blam']['cutscene_flags'] if row['name'].startswith('terrain_probe_')]
    assert_equal(sorted(expected, key=lambda row: row['name']), sorted(actual, key=lambda row: row['name']),
                 'installed compiled probe geometry')
    return policy


def before(qa, receipt, refresh_path, scenery_path, policy_path, exact_health_cli):
    qa, receipt, refresh_path, scenery_path, policy_path = map(lambda p: Path(p).resolve(),
        (qa, receipt, refresh_path, scenery_path, policy_path))
    require(not (qa/'artifact-seal.before.json').exists(), 'Before seal already exists; preserve earlier evidence')
    load_policy(policy_path)
    installation, refresh, scenery = map(read, (receipt, refresh_path, scenery_path))
    require(len(installation.get('files', [])) >= 20, 'Incomplete installation receipt')
    installed = {str(Path(row['installed']).resolve()): record(row['installed'], row['sha256'])
                 for row in installation['files']}
    levels = [Path(p) for p in installed if Path(p).parts[-3:] == ('MJOLNIRMaps', 'PWR', 'level.json')]
    require(len(levels) == 1, 'Expected exactly one installed PWR metadata file')
    level_path = levels[0]
    require(refresh.get('success') is True and refresh.get('applied') is True, 'Native refresh has not passed and published')
    plan_path, contract_path = Path(refresh['probe_plan']), Path(refresh['contract'])
    require(sha(plan_path) == refresh['probe_plan_sha256'] and sha(contract_path) == refresh['contract_sha256'],
            'Changed compiled probe plan or contract')
    policy = check_prepared_level(read(level_path), policy_path, read(contract_path), plan_path)
    require(str(policy_path) in refresh['inputs'] and refresh['inputs'][str(policy_path)] == sha(policy_path),
            'Fresh refresh inputs must explicitly bind the spawn policy')
    inputs = {str(Path(p).resolve()): record(p, digest) for p, digest in refresh['inputs'].items()}
    staged_path = refresh_path.parent/'pwr.level.verified.json'
    inputs[str(staged_path)] = record(staged_path, refresh['verified_level_sha256'])
    for path in (refresh_path, scenery_path, policy_path, plan_path, contract_path,
                 refresh_path.parent/'flight-envelope.json'):
        inputs[str(path)] = record(path)
    require(scenery.get('trees', 0) > 0 and scenery.get('total_rocks', 0) > 0 and scenery.get('files'),
            'Scenery seal must supply final counts and per-file source/cache hashes')
    for row in scenery['files']:
        inputs[str(Path(row['path']).resolve())] = record(row['path'], row['sha256'])
    ue4ss = level_path.parents[2]
    native = ue4ss/'Mods/MJOLNIRLobby/native'
    dll = record(native/'mjolnir_lobby.dll', DLL_SHA)
    rules_candidates = list((ue4ss/'Mods').rglob('warfare.mglo'))
    require(len(rules_candidates) == 1, 'Expected one installed Warfare rules file')
    rules = record(rules_candidates[0], RULES_SHA)
    for row in (dll, rules, record(native/'warfare_config.txt')):
        installed[row['path']] = row
    for mod in ('MJOLNIRLobby', 'MJOLNIRLevelLoader', 'MJOLNIRUI', 'MJOLNIRHud'):
        for path in sorted((ue4ss/'Mods'/mod/'Scripts').rglob('*.lua')):
            installed[str(path)] = record(path)
    for filename in ('smoke-warfare.mjs', 'smoke-warfare-terrain.mjs', 'smoke-warfare-vehicles.mjs',
                     'observe-warfare-vehicles.mjs', 'smoke-warfare-vehicle-destruction.mjs'):
        path = ROOT/'native/lobby'/filename; inputs[str(path)] = record(path)
    for path in (Path(__file__), ROOT/'levels/warfare/pwr/vehicle_spawn_policy.py',
                 ROOT/'out/pwr/world-v5/native-acceptance-v5.json', ROOT/'out/pwr/world-v5/qa-artifact-seal.json',
                 ROOT/'out/pwr/world-v5/forest-r2/verify-landing.mjs', ROOT/'out/pwr/world-v5/forest-r2/return-home.mjs'):
        inputs[str(path.resolve())] = record(path)
    exact_health_cli = Path(exact_health_cli).resolve()
    critical = [record(level_path), dll, rules, record(policy_path), record(exact_health_cli)]
    doc = {'schema': 'pwr-native-qa-seal-v2', 'at': datetime.now(timezone.utc).isoformat(),
        'installation_receipt': record(receipt), 'installed_level': str(level_path),
        'policy_path': str(policy_path), 'vehicle_spawn_policy': policy,
        'exact_health_cli': str(exact_health_cli),
        'installed': list(installed.values()), 'inputs': list(inputs.values()), 'critical': critical,
        'unchanged_gameplay': [dll, rules], 'probe_plan': str(plan_path), 'probe_plan_sha256': sha(plan_path),
        'compiled_collision_sha256': read(plan_path)['provenance']['compiled_tag_sha256'],
        'tree_count': scenery['trees'], 'rock_count': scenery['total_rocks'],
        'historical_scope': 'Prior manual Space/player respawn/capture only. Current collision and corrected vehicle lifecycle require fresh proof.'}
    write_new(qa/'artifact-seal.before.json', doc)
    return {'before_seal': str(qa/'artifact-seal.before.json'), 'installed_files': len(installed), 'input_files': len(inputs)}


def after(qa):
    qa = Path(qa).resolve()
    source = qa/'artifact-seal.before.json'
    doc = read(source)
    require(doc['schema'] == 'pwr-native-qa-seal-v2', 'Unexpected QA seal')
    rows = [doc['installation_receipt']]+doc['installed']+doc['inputs']+doc['critical']
    for row in rows: record(row['path'], row['sha256'])
    result = {'schema': 'pwr-native-qa-seal-verification-v2', 'at': datetime.now(timezone.utc).isoformat(),
              'before': record(source), 'all_unchanged': True, 'verified_files': len(rows)}
    write_new(qa/'artifact-seal.after.json', result)
    return result


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('command', choices=['before', 'after'])
    p.add_argument('--qa', type=Path, required=True)
    for name in ('installed-receipt', 'refresh', 'scenery-seal', 'vehicle-spawn-policy', 'exact-health-cli'):
        p.add_argument('--'+name, type=Path)
    args = p.parse_args()
    if args.command == 'before':
        if not all((args.installed_receipt, args.refresh, args.scenery_seal, args.vehicle_spawn_policy, args.exact_health_cli)):
            p.error('Before requires explicit installed receipt, fresh refresh, scenery seal, vehicle spawn policy and exact-health QA CLI')
        result = before(args.qa, args.installed_receipt, args.refresh, args.scenery_seal, args.vehicle_spawn_policy, args.exact_health_cli)
    else: result = after(args.qa)
    print(json.dumps(result, indent=2))
