#!/usr/bin/env python3
"""Record a verified TST CE build's inputs for native-detail conversion.

The operator must supply the actual HEK input manifest, input JMS, the frozen
structure BSP, scenario, lightmap and completed cache/map with their logs. The
input manifest's hashes and successful stages are checked. These hashes document
the supplied evidence; they do not prove which executable produced a log.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re

from partition_tst_facility import sha256
from verify_tst_facility_receipt import partition_claims, read_json

FATAL = re.compile(r'\bexception(?:\b|_)|###\s*error|couldn.t allocate subcluster', re.I)


def create(partition_dir, detail, source_jms, surfaces, ce_map, input_manifest,
           hek_input_jms, frozen_bsp, structure_log, scenario_log,
           lightmap_log, lightmap_bitmap, cache_log):
    _, _, _, claims = partition_claims(partition_dir, detail, source_jms, surfaces, ce_map)
    input_manifest, hek_input_jms, frozen_bsp, structure_log, scenario_log, lightmap_log, lightmap_bitmap, cache_log = (
        Path(path).resolve(strict=True) for path in
        (input_manifest, hek_input_jms, frozen_bsp, structure_log, scenario_log, lightmap_log, lightmap_bitmap, cache_log))
    evidence = {
        'build_input_manifest_sha256': sha256(input_manifest),
        'structure_log_sha256': sha256(structure_log),
        'scenario_log_sha256': sha256(scenario_log),
        'lightmap_log_sha256': sha256(lightmap_log),
        'cache_log_sha256': sha256(cache_log),
    }
    frozen = read_json(input_manifest)
    hashes = frozen.get('hashes', {})
    actual_jms = sha256(hek_input_jms)
    actual_bsp = sha256(frozen_bsp)
    if actual_jms != claims['ce_jms_sha256'] or str(hashes.get('jms', '')).lower() != actual_jms:
        raise ValueError('Frozen HEK input JMS is not the CE partition')
    if str(hashes.get('bsp', '')).lower() != actual_bsp:
        raise ValueError('Structure BSP does not match the frozen HEK input manifest')
    if str(hashes.get('surfaces', '')).lower() != claims['surface_library_sha256']:
        raise ValueError('Frozen HEK inputs used a different surface library')
    if 'texture_hashes' in frozen and frozen['texture_hashes'] != claims['texture_hashes']:
        raise ValueError('Frozen HEK inputs used different owned texture bytes')
    structure = structure_log.read_text(encoding='utf-8', errors='replace')
    cache = cache_log.read_text(encoding='utf-8', errors='replace')
    if (FATAL.search(structure) or 'structure bsp' not in structure.lower() or
            'clusters' not in structure.lower() or 'without debug information' not in structure.lower()):
        raise ValueError('Structure log does not demonstrate a successful build')
    scenario_record = read_json(scenario_log)
    if scenario_record.get('roundtrip') != 'passed' or not scenario_record.get('scenario'):
        raise ValueError('Scenario log does not demonstrate a successful round-trip')
    scenario = Path(scenario_record['scenario']).resolve(strict=True)
    scenario_hash = sha256(scenario)
    if scenario_hash != str(scenario_record.get('sha256', '')).lower():
        raise ValueError('Scenario file differs from the successful round-trip log')
    lightmap = lightmap_log.read_text(encoding='utf-8', errors='replace')
    if (FATAL.search(lightmap) or not re.search(r'finished\s+levels[\\/]+test[\\/]+tst[\\/]+tst\b', lightmap, re.I)
            or not re.search(r'\bdone\b', lightmap, re.I)):
        raise ValueError('Lightmap log does not demonstrate a successful build')
    if lightmap_bitmap.stat().st_size == 0 or lightmap_bitmap.stat().st_mtime + 2 < input_manifest.stat().st_mtime:
        raise ValueError('Lightmap bitmap is empty or predates the frozen HEK inputs')
    if FATAL.search(cache) or 'successfully built cache file' not in cache.lower():
        raise ValueError('Cache log does not demonstrate a successful build')
    map_path = Path(ce_map).resolve(strict=True)
    if map_path.stat().st_size == 0 or map_path.stat().st_mtime + 2 < input_manifest.stat().st_mtime:
        raise ValueError('CE map is empty or predates the frozen HEK inputs')
    result = dict(claims)
    result.update({'hek_input_jms_sha256': actual_jms,
                   'build_input_manifest_sha256': evidence['build_input_manifest_sha256'],
                   'structure_bsp_sha256': actual_bsp,
                   'structure_log_sha256': evidence['structure_log_sha256'],
                   'scenario_log_sha256': evidence['scenario_log_sha256'], 'scenario_sha256': scenario_hash,
                   'lightmap_log_sha256': evidence['lightmap_log_sha256'], 'lightmap_bitmap_sha256': sha256(lightmap_bitmap),
                   'cache_log_sha256': evidence['cache_log_sha256']})
    # Reject a concurrent rebuild before returning the attestation.
    _, _, _, after = partition_claims(partition_dir, detail, source_jms, surfaces, ce_map)
    if (claims != after or sha256(hek_input_jms) != actual_jms or sha256(frozen_bsp) != actual_bsp
            or sha256(scenario) != scenario_hash or sha256(lightmap_bitmap) != result['lightmap_bitmap_sha256']
            or any(sha256(path) != evidence[key] for key, path in (
                ('build_input_manifest_sha256', input_manifest), ('structure_log_sha256', structure_log),
                ('scenario_log_sha256', scenario_log), ('lightmap_log_sha256', lightmap_log),
                ('cache_log_sha256', cache_log)))):
        raise RuntimeError('A build input or output changed while creating the receipt')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('partition-dir', 'detail', 'source-jms', 'surfaces', 'map', 'input-manifest',
                 'hek-input-jms', 'frozen-bsp', 'structure-log', 'scenario-log',
                 'lightmap-log', 'lightmap-bitmap', 'cache-log', 'out'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    result = create(args.partition_dir, args.detail, args.source_jms, args.surfaces, args.map,
                    args.input_manifest, args.hek_input_jms, args.frozen_bsp,
                    args.structure_log, args.scenario_log, args.lightmap_log, args.lightmap_bitmap, args.cache_log)
    with args.out.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(result, stream, indent=2)
        stream.write('\n')
    print(f'CE build receipt written: {args.out}')


if __name__ == '__main__':
    main()
