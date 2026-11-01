"""Bind map-owned cook output to the conversion and freshly generated cliffs.

The conversion cook can contain an older package with the same generated asset
path as the later landscape cook. Packaging that first cook makes Unreal load
stale geometry. Keep the map cook produced *after* the cliff editor build.
"""
import hashlib
import json
from pathlib import Path
import re
import os
import shutil
import subprocess
import tempfile
import uuid

from cooked_map_container import cooked_map_container


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def input_files(code, config, work):
    conversion = Path(config['conversion'])
    base = cooked_map_container(conversion, code)
    inputs = {'materials': conversion / 'materials.spec.json',
            'conversion_utoc': Path(str(base) + '.utoc'),
            'conversion_ucas': Path(str(base) + '.ucas')}
    for name in ('cliff_mesh', 'shadow_shell', 'flux_bed', 'flux_ground', 'river_mesh', 'plasma_mesh'):
        path = Path(work) / (name + '.json')
        if path.is_file():
            inputs[name] = path
    if 'cliff_mesh' not in inputs:
        raise ValueError('Missing generated cliff mesh')
    return inputs


def check_generated_meshes(code, config, work, staged, map_chunk, cli):
    """Reject duplicate generated meshes that disagree across the two cooks.

    Use isolated container inventories so mount order cannot hide a duplicate.
    Export both packages through the runtime mesh reader and compare GLBs.
    """
    work, staged = Path(work), Path(staged)
    mesh_files = {'cliff_mesh.json': 'CliffTess', 'shadow_shell.json': 'ShadowShell',
                  'flux_bed.json': 'FluxBed', 'flux_ground.json': 'FluxGround',
                  'river_mesh.json': 'River', 'plasma_mesh.json': 'Plasma'}
    names = [f'SM_{code}_{suffix}' for filename, suffix in mesh_files.items()
             if (work / filename).is_file()]
    if not names:
        raise ValueError('No generated map meshes to verify')
    with tempfile.TemporaryDirectory(prefix='mj-owned-cook-', dir=work) as temp:
        root = Path(temp)
        results = []
        for chunk in (map_chunk, int(config['chunk'])):
            folder = root / str(chunk)
            folder.mkdir(exist_ok=True)
            for stem in ('global', f'pakchunk{chunk}-Windows'):
                for ext in ('utoc', 'ucas'):
                    source, dest = staged / f'{stem}.{ext}', folder / f'{stem}.{ext}'
                    if not dest.exists():
                        try:
                            os.link(source, dest)
                        except OSError:
                            shutil.copyfile(source, dest)
            hashes = {}
            for name in names:
                out = folder / (name + '.glb')
                proc = subprocess.run([str(cli), 'mesh', 'export', '--paks', str(folder),
                                       '--asset', name, '--out', str(out)], capture_output=True, text=True)
                if proc.returncode or not out.is_file():
                    raise ValueError(f'Cannot verify {name} in chunk {chunk}: {proc.stderr.strip()}')
                hashes[name] = digest(out)
            results.append(hashes)
        if results[0] != results[1]:
            raise ValueError('Map and landscape chunks contain different generated meshes')
        return results[0]


def snapshot_owned_cook(code, config, work, staged, cli):
    """Snapshot only after editor rebuilt map meshes and cook succeeded."""
    work, staged = Path(work), Path(staged)
    base = cooked_map_container(config['conversion'], code)
    match = re.fullmatch(r'pakchunk(\d+)-MJOLNIRCOOK-' + re.escape(code) + r'_P', base.name)
    if not match:
        raise ValueError(f'Invalid owned cook name: {base.name}')
    chunk = int(match.group(1))
    inputs = {name: digest(path) for name, path in input_files(code, config, work).items()}
    meshes = check_generated_meshes(code, config, work, staged, chunk, cli)
    landscape = {ext: digest(staged / f"pakchunk{int(config['chunk'])}-Windows.{ext}")
                 for ext in ('utoc', 'ucas')}
    token = uuid.uuid4().hex
    dest = work / f'owned-cook-{token}'
    dest.mkdir(parents=True, exist_ok=False)
    hashes = {}
    for ext in ('utoc', 'ucas'):
        src = staged / f'pakchunk{chunk}-Windows.{ext}'
        dst = dest / f'{base.name}.{ext}'
        shutil.copyfile(src, dst)
        hashes[ext] = digest(dst)
    receipt = {'schema': 1, 'code': code, 'chunk': chunk, 'dir': dest.name,
               'inputs': inputs, 'containers': hashes, 'landscape': landscape,
               'verified_meshes': meshes}
    temp = work / f'owned-cook-{token}.tmp'
    temp.write_text(json.dumps(receipt, indent=2) + '\n', encoding='utf-8')
    temp.replace(work / 'owned-cook.json')
    return dest / base.name


def verified_owned_cook(code, config, work):
    """Reject changed inputs or incomplete/tampered cook before staging."""
    work = Path(work)
    receipt = json.loads((work / 'owned-cook.json').read_text(encoding='utf-8'))
    if receipt.get('schema') != 1 or receipt.get('code') != code:
        raise ValueError('Owned cook receipt does not match map')
    folder = receipt.get('dir', '')
    if not re.fullmatch(r'owned-cook-[0-9a-f]{32}', folder):
        raise ValueError('Invalid owned cook folder')
    base = cooked_map_container(config['conversion'], code)
    chunk = int(base.name.split('-', 1)[0].removeprefix('pakchunk'))
    if receipt.get('chunk') != chunk:
        raise ValueError('Owned cook chunk does not match conversion')
    if not receipt.get('verified_meshes'):
        raise ValueError('Owned cook lacks generated mesh verification')
    landscape = {ext: digest(work / 'bake' / f"pakchunk{int(config['chunk'])}-MJOLNIRLAND-Windows.{ext}")
                 for ext in ('utoc', 'ucas')}
    if receipt.get('landscape') != landscape:
        raise ValueError('Landscape bake does not match the verified owned cook')
    inputs = {name: digest(path) for name, path in input_files(code, config, work).items()}
    if receipt.get('inputs') != inputs:
        raise ValueError('Owned cook is stale: conversion or generated cliff changed')
    target = work / folder / base.name
    for ext in ('utoc', 'ucas'):
        if digest(str(target) + '.' + ext) != receipt.get('containers', {}).get(ext):
            raise ValueError('Owned cook container hash mismatch')
    return target
