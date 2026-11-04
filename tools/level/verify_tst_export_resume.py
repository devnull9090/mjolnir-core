"""Verify an interrupted TST export before resuming its unused HEK build.

Only the narrow failure after a complete partition write and before its atomic
directory publication is accepted. This verifies retained bytes and logs, not
the provenance of arbitrary operator-provided evidence.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from partition_tst_facility import owned_texture_hashes, sha256


def verify(bundle, source, logs):
    bundle, source, logs = (Path(p).resolve(strict=True) for p in (bundle, source, logs))
    for root in (bundle, source, logs):
        if not root.is_dir() or root.is_symlink():
            raise ValueError('Resume roots must be ordinary directories')
    for reserved in ('partition', 'evidence', 'tst.map', 'tst-facility-ce-build-receipt.json',
                     '.tst-facility-ce-build-receipt.pending', 'tst_lights_amber.shader_environment'):
        if (bundle / reserved).exists():
            raise ValueError('Resume requires no later build outputs: ' + reserved)
    candidates = list(bundle.glob('.tst-facility-partition-*/manifest.json'))
    if len(candidates) != 1:
        raise ValueError('Resume needs exactly one complete interrupted partition manifest')
    manifest_path = candidates[0]
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    if manifest.get('format') != 'tst-facility-partition-v1':
        raise ValueError('Unexpected retained partition format')
    expected_files = {'tst-ce-structure.JMS', 'tst-facility-detail.gltf', 'tst-facility-detail.bin'}
    if set(manifest.get('files', {})) != expected_files:
        raise ValueError('Retained partition file set is incomplete')
    for name, expected in manifest['files'].items():
        path = manifest_path.parent / name
        if path.is_symlink() or sha256(path) != expected:
            raise ValueError('Retained partition file changed: ' + name)
    authoring = bundle / 'authoring'
    jms = authoring / 'data/levels/test/tst/models/tst.JMS'
    library = authoring / 'surfaces.json'
    if sha256(jms) != manifest.get('source_sha256'):
        raise ValueError('Completed export JMS changed after partition')
    if sha256(library) != manifest.get('surface_library_sha256') or sha256(source / 'surfaces.json') != sha256(library):
        raise ValueError('Completed export palette changed')
    if owned_texture_hashes(library) != manifest.get('texture_hashes'):
        raise ValueError('Completed export textures changed')
    if owned_texture_hashes(source / 'surfaces.json') != manifest.get('texture_hashes'):
        raise ValueError('Live owned textures differ from completed export')
    if manifest.get('ce_triangles', -1) + manifest.get('native_triangles', -1) != manifest.get('source_triangles'):
        raise ValueError('Retained partition triangle counts do not add up')
    snapshot = bundle / 'authoring-source'
    names = {p.name for p in source.glob('*.py') if not p.name.startswith('test_')}
    names.update(n for n in ('rebuild.ps1', 'surfaces.json', 'amber_light.json', 'facility_runtime_lights.json')
                 if (source / n).is_file())
    if {p.name for p in snapshot.iterdir()} != names:
        raise ValueError('Authoring source module set changed after export')
    sources = {}
    for name in sorted(names):
        old, live = snapshot / name, source / name
        if old.is_symlink() or live.is_symlink() or not old.is_file():
            raise ValueError('Authoring sources must be ordinary files')
        sources[name] = sha256(old)
        if name != 'rebuild.ps1' and sha256(live) != sources[name]:
            raise ValueError('Authoring source changed after export: ' + name)
    records = {}
    for name in ('geometry.log', 'annotate.log', 'facility-partition.log'):
        path = logs / name
        records[name] = {'path': str(path), 'sha256': sha256(path)}
    geometry = (logs / 'geometry.log').read_text(encoding='utf-8', errors='replace')
    annotated = (logs / 'annotate.log').read_text(encoding='utf-8', errors='replace')
    failure = (logs / 'facility-partition.log').read_text(encoding='utf-8', errors='replace')
    def normalized(value):
        return value.replace('\\', '/').lower()
    if ('TST_GEOMETRY_EXPORTED' not in geometry or 'Export completed successfully' not in geometry
            or normalized(str(jms)) not in normalized(geometry)):
        raise ValueError('Prior geometry log does not show this completed export')
    blend = authoring / 'tst.blend'
    if ('TST_ANNOTATED' not in annotated or normalized(str(blend)) not in normalized(annotated)
            or blend.stat().st_size == 0 or blend.stat().st_mtime < jms.stat().st_mtime):
        raise ValueError('Prior annotation does not show this completed blend')
    if not all(token in failure for token in ('PermissionError', 'WinError 5', manifest_path.parent.name)):
        raise ValueError('Prior failure was not the supported partition publication sharing conflict')
    for name in ('placements.json', 'perimeter_dressing.json', 'tst.surfaces.json'):
        json.loads((authoring / name).read_text(encoding='utf-8'))
    files = {str(p.relative_to(authoring)): sha256(p) for p in authoring.rglob('*') if p.is_file()}
    return {'format': 'tst-verified-export-resume-v1', 'bundle': str(bundle),
            'retained_partition_manifest': str(manifest_path), 'retained_partition_sha256': sha256(manifest_path),
            'logs': records, 'authoring_source_hashes': sources, 'authoring_files': files,
            'texture_hashes': manifest['texture_hashes'],
            'original_runner_sha256': sources['rebuild.ps1'], 'resume_runner_sha256': sha256(source / 'rebuild.ps1'),
            'scope': 'Reuse verified completed export only; partition and every HEK stage run fresh. Original failure artifacts retained.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('bundle', 'source', 'logs'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(verify(args.bundle, args.source, args.logs), indent=2))


if __name__ == '__main__':
    main()
