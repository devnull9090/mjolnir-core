#!/usr/bin/env python3
"""Verify that a TST CE map and native detail come from the same export.

The CE build receipt is written only after a successful structure/lightmap/cache
build has been independently verified against its frozen HEK input manifest.
This verifier checks its hash claims, not the truth of the build process itself.
When given a material spec, it also validates every authored slot and writes a
new conversion receipt containing the spec hash. No inputs are overwritten.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re

from authored_surfaces import load_library
from partition_tst_facility import owned_texture_hashes, sha256

PREDICATE = 'tst_metal_*! and abs(x)<1800, 700<y<1900, z<240 in JMS units'
PARTITION_FILES = ('tst-ce-structure.JMS', 'tst-facility-detail.gltf', 'tst-facility-detail.bin')


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def partition_claims(partition_dir, detail, source_jms, surfaces, ce_map):
    folder = Path(partition_dir).resolve(strict=True)
    if not folder.is_dir():
        raise ValueError('Partition path must be a directory')
    manifest_path = folder / 'manifest.json'
    manifest = read_json(manifest_path)
    if manifest.get('format') != 'tst-facility-partition-v1' or manifest.get('predicate') != PREDICATE:
        raise ValueError('Unexpected TST partition format or predicate')
    files = manifest.get('files')
    if not isinstance(files, dict) or set(files) != set(PARTITION_FILES):
        raise ValueError('Partition does not list the required CE JMS, glTF and buffer')
    for name in PARTITION_FILES:
        path = folder / name
        if path.is_symlink() or not path.is_file() or sha256(path) != files[name]:
            raise ValueError(f'Partition file is missing, linked, or changed: {name}')
    if Path(detail).resolve(strict=True) != (folder / PARTITION_FILES[1]).resolve(strict=True):
        raise ValueError('Native detail is not the glTF from this partition')
    gltf = read_json(folder / PARTITION_FILES[1])
    if len(gltf.get('buffers', [])) != 1 or gltf['buffers'][0].get('uri') != PARTITION_FILES[2]:
        raise ValueError('Native detail does not reference the recorded external buffer')
    source_jms, surfaces, ce_map = (Path(path).resolve(strict=True) for path in (source_jms, surfaces, ce_map))
    expected = {
        'format': 'tst-facility-ce-build-v1',
        'partition_format': manifest['format'], 'predicate': PREDICATE,
        'partition_manifest_sha256': sha256(manifest_path),
        'source_jms_sha256': sha256(source_jms),
        'ce_jms_sha256': files[PARTITION_FILES[0]],
        'native_gltf_sha256': files[PARTITION_FILES[1]],
        'native_bin_sha256': files[PARTITION_FILES[2]],
        'surface_library_sha256': sha256(surfaces), 'texture_hashes': owned_texture_hashes(surfaces),
        'ce_map_sha256': sha256(ce_map),
    }
    if expected['source_jms_sha256'] != manifest.get('source_sha256'):
        raise ValueError('Full source JMS differs from the partition')
    if expected['surface_library_sha256'] != manifest.get('surface_library_sha256'):
        raise ValueError('Surface library differs from the partition')
    if expected['texture_hashes'] != manifest.get('texture_hashes'):
        raise ValueError('Owned texture hashes differ from the partition')
    if manifest.get('ce_triangles', -1) + manifest.get('native_triangles', -1) != manifest.get('source_triangles'):
        raise ValueError('Partition triangle counts do not add up')
    return manifest, gltf, surfaces, expected


def verify(partition_dir, detail, receipt, source_jms, surfaces, ce_map, spec=None):
    _, gltf, surfaces, expected = partition_claims(partition_dir, detail, source_jms, surfaces, ce_map)
    evidence = read_json(receipt)
    for key, value in expected.items():
        if evidence.get(key) != value:
            raise ValueError(f'CE build receipt does not match {key}')
    if evidence.get('hek_input_jms_sha256') != expected['ce_jms_sha256']:
        raise ValueError('CE build receipt does not attest the actual HEK input JMS')
    for key in ('build_input_manifest_sha256', 'structure_bsp_sha256',
                'structure_log_sha256', 'scenario_log_sha256', 'scenario_sha256',
                'lightmap_log_sha256', 'lightmap_bitmap_sha256', 'cache_log_sha256'):
        if not re.fullmatch(r'[0-9a-f]{64}', str(evidence.get(key, ''))):
            raise ValueError(f'CE build receipt lacks valid provenance: {key}')
    result = dict(expected)
    result.update({key: evidence[key] for key in ('hek_input_jms_sha256', 'build_input_manifest_sha256',
                   'structure_bsp_sha256', 'structure_log_sha256', 'scenario_log_sha256', 'scenario_sha256',
                   'lightmap_log_sha256', 'lightmap_bitmap_sha256', 'cache_log_sha256')})
    result['ce_build_receipt_sha256'] = sha256(Path(receipt))
    if spec is None:
        return result

    # The spec is produced during conversion and therefore cannot be part of
    # the earlier CE build receipt. Bind it now, before mesh rewrite/cook.
    spec_path = Path(spec).resolve(strict=True)
    doc = read_json(spec_path)
    root = '/Game/MJOLNIR/Maps/TST'
    if doc.get('root') != root or doc.get('chunk') != 968:
        raise ValueError('Material spec does not target TST material chunk 968')
    library = load_library(surfaces)
    authored = doc.get('authored_surfaces', {})
    if set(authored) != set(library):
        raise ValueError('Material spec authored role set does not match the source library')
    for role, values in library.items():
        for key, value in values.items():
            if authored[role].get(key) != value:
                raise ValueError(f'Material spec differs from source role {role}: {key}')
    by_tag = {data['tag']: role for role, data in library.items()}
    slots = doc.get('slots', [])
    names = set()
    for material in gltf.get('materials', []):
        name = material.get('name', '')
        halo = material.get('extras', {}).get('halo', {})
        tag = str(halo.get('tag_path', '')).replace('\\', '/').lower()
        if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]*', name) or name.lower() in names or tag not in by_tag:
            raise ValueError('Native detail contains an invalid, duplicate or non-authored material')
        names.add(name.lower())
        role = by_tag[tag]
        leaf = 'M_Authored_' + role
        expected_parent = f'{root}/SurfaceMaterials/{leaf}.{leaf}'
        found = [slot for slot in slots if slot.get('pattern') == name.lower() + '$']
        if len(found) != 1 or found[0].get('material', {}).get('parent') != expected_parent:
            raise ValueError(f'Native detail material is missing its exact authored slot: {name}')
    if not names:
        raise ValueError('Native detail has no authored materials')
    result['format'] = 'tst-facility-native-conversion-v1'
    result['ce_build_format'] = expected['format']
    result['material_spec_sha256'] = sha256(spec_path)
    result['native_material_slots'] = len(names)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--partition-dir', type=Path, required=True)
    parser.add_argument('--detail', type=Path, required=True)
    parser.add_argument('--receipt', type=Path, required=True)
    parser.add_argument('--source-jms', type=Path, required=True)
    parser.add_argument('--surfaces', type=Path, required=True)
    parser.add_argument('--map', type=Path, required=True)
    parser.add_argument('--spec', type=Path)
    parser.add_argument('--out', type=Path, help='New conversion receipt; requires --spec')
    args = parser.parse_args()
    if args.out and not args.spec:
        parser.error('--out requires --spec')
    result = verify(args.partition_dir, args.detail, args.receipt, args.source_jms, args.surfaces, args.map, args.spec)
    if args.out:
        # Exclusive create avoids replacing an earlier report or user file.
        with args.out.open('x', encoding='utf-8', newline='\n') as stream:
            json.dump(result, stream, indent=2)
            stream.write('\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
