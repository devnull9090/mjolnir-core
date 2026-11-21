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


def landscape_lod_policy_path(config):
    value = config.get('landscape_lod_policy')
    if value is None:
        return None
    if not isinstance(value, str) or not value:
        raise ValueError('Landscape LOD policy must name an explicit file')
    path = Path(value)
    if not path.is_absolute():
        path = Path(__file__).resolve().parents[2] / path
    path = path.resolve()
    if not path.is_file():
        raise FileNotFoundError('Landscape LOD policy is missing: ' + str(path))
    return path


def landscape_lod_cook_inputs(config, work):
    """Bind the optional policy to current sources and editor component settings."""
    policy_path = landscape_lod_policy_path(config)
    if policy_path is None:
        return {}
    policy = json.loads(policy_path.read_text(encoding='utf-8'))
    readback_path = Path(work) / 'land' / 'landscape-lod.readback.json'
    readback = json.loads(readback_path.read_text(encoding='utf-8'))
    if (readback.get('schema') != 'mjolnir-landscape-lod-readback-v1'
            or readback.get('policy_sha256') != digest(policy_path)):
        raise ValueError('Landscape LOD editor readback is stale or missing its policy binding')
    from landscape_lod_policy import validate_policy
    source_dir = Path(work) / 'land'
    spec_path = source_dir / 'landscape.json'
    spec = json.loads(spec_path.read_text(encoding='utf-8'))
    forced = validate_policy(policy, spec, source_dir)
    grid = policy['grid']
    step = grid['sections'] * grid['quads']
    expected = {(x*step, y*step) for x in range(grid['components']) for y in range(grid['components'])}
    actual = {}
    for row in readback.get('components', []):
        key = tuple(row['section_base'])
        if key in actual:
            raise ValueError('Landscape LOD readback has a duplicate component')
        actual[key] = row['forced_lod']
    if (not forced <= expected or set(actual) != expected
            or any(actual[key] != (0 if key in forced else -1) for key in expected)
            or readback.get('forced_components') != len(forced)
            or readback.get('automatic_components') != len(expected-forced)):
        raise ValueError('Landscape LOD editor component settings do not match policy')
    inputs = {'landscape_lod_policy': policy_path, 'landscape_lod_readback': readback_path,
              'landscape_lod_spec': spec_path, 'landscape_lod_heights': source_dir / spec['heights']}
    inputs.update({f'landscape_lod_source_{index}': Path(source['path'])
                   for index, source in enumerate(policy.get('sources', []))})
    return inputs


def apron_geology_cook_inputs(config):
    if not config.get('apron_geology'):
        return {}
    if not config.get('heightfield'):
        raise ValueError('Apron geology requires an explicit runtime heightfield')
    from alpine_surface_v6 import load_apron_texture
    from heightfield import load_heightfield
    repo = Path(__file__).resolve().parents[2]
    manifest = (repo / config['apron_geology']).resolve()
    runtime = load_heightfield(repo / config['heightfield'])
    texture, _ = load_apron_texture(manifest, runtime.manifest_sha256)
    return {'apron_geology': manifest, 'apron_geology_texture': texture}


def render_only_hism_path(config):
    value = config.get('render_only_hism')
    if value is None:
        return None
    if not isinstance(value, str) or not value or not config.get('bake_foliage'):
        raise ValueError('Exterior HISM requires an explicit manifest and bake_foliage')
    path = (Path(__file__).resolve().parents[2] / value).resolve()
    from render_only_hism import load
    load(path)
    return path


def render_only_pines_path(config):
    value = config.get('render_only_pines')
    if value is None:
        return None
    if not isinstance(value, str) or not value or not config.get('bake_foliage'):
        raise ValueError('Exterior pines require an explicit manifest and bake_foliage')
    path = (Path(__file__).resolve().parents[2] / value).resolve()
    from render_only_pines import load
    load(path)
    return path


def render_only_pines_cook_inputs(config, work):
    path = render_only_pines_path(config)
    if path is None:
        return {}
    from render_only_pines import cook_inputs
    return cook_inputs(path, work)


def render_only_hism_cook_inputs(config, work):
    """Bind exterior decoration to its source, exact transforms and editor proof."""
    path = render_only_hism_path(config)
    if path is None:
        return {}
    from render_only_hism import load, groups
    from foliage_bake import write_exact
    doc, proof = load(path)
    expected, grouped = groups(path)
    folder = Path(work) / 'foliage_bake'
    spec_path = folder / 'spec.json'
    spec = json.loads(spec_path.read_text(encoding='utf-8'))
    declared = spec.get('render_only_hism', {})
    if (Path(declared.get('path', '')).resolve() != path
            or any(declared.get(k) != proof[k] for k in ('sha256', 'instances', 'instanced_source_triangles', 'material'))
            or declared.get('components') != grouped['components']
            or len(declared.get('groups', [])) != len(expected)):
        raise ValueError('Exterior HISM foliage spec does not match manifest')
    readback_path = folder / 'render-only-hism.verification.json'
    readback = json.loads(readback_path.read_text(encoding='utf-8'))
    if (readback.get('schema') != 'pwr-render-only-hism-editor-v1'
            or readback.get('source_sha256') != proof['sha256']
            or readback.get('no_native_collision_input') is not True):
        raise ValueError('Exterior HISM editor proof is stale')
    for key, limit in (('maximum_position_error_cm', .01),
                       ('maximum_quaternion_dot_error', 1e-5), ('maximum_scale_error', 1e-5)):
        value = readback.get(key)
        if not isinstance(value, (int, float)) or not 0 <= value <= limit:
            raise ValueError('Exterior HISM editor transform error exceeds tolerance')
    rows = readback.get('groups', [])
    actual = {row['component']: row for row in rows}
    if len(actual) != len(rows) or len(actual) != len(expected):
        raise ValueError('Exterior HISM editor component inventory differs')
    inputs = {'render_only_hism': path, 'render_only_hism_spec': spec_path,
              'render_only_hism_readback': readback_path}
    inputs.update({f'render_only_hism_source_{i}': (path.parent / entry['path']).resolve()
                   for i, entry in enumerate(doc['sources'])})
    seen = set()
    for index, ((records, group, ids), entry) in enumerate(zip(expected, declared['groups'])):
        number = entry.get('group')
        if (not isinstance(number, int) or number in seen or not 1 <= number <= len(spec['groups'])
                or entry.get('count') != len(records) or entry.get('ids') != ids):
            raise ValueError('Exterior HISM group mapping differs')
        seen.add(number)
        baked = spec['groups'][number-1]
        if baked.get('mesh') != group['mesh'] or baked.get('flags') != 35:
            raise ValueError('Exterior HISM mesh or collision-independent flags changed')
        sidecar = Path(f"{spec['bin']}.xf{number}")
        with tempfile.TemporaryDirectory(prefix='exterior-xf-') as temp:
            check = Path(temp) / 'expected.xf'
            write_exact(check, records)
            if sidecar.read_bytes() != check.read_bytes():
                raise ValueError('Exterior HISM exact transforms changed')
        inputs[f'render_only_hism_transform_{index}'] = sidecar
        row = actual.pop(f'MJFol_{number}_1_0', {})
        if (row.get('mesh') != group['mesh'] or row.get('instances') != len(records)
                or row.get('collision') != 'NoCollision' or row.get('navigation') is not False
                or row.get('wpo') is not False or row.get('cull_cm') != doc['cull_cm']
                or not row.get('material', '').endswith('/MI_PWR_ExteriorCliffs_' + proof['sha256'][:12]
                    + '.MI_PWR_ExteriorCliffs_' + proof['sha256'][:12])):
            raise ValueError('Exterior HISM editor mesh/material/settings differ')
    if actual:
        raise ValueError('Unexpected exterior HISM editor components')
    return inputs


def paving_graphic_cook_inputs(config):
    if not config.get('paving_graphic'):
        return {}
    from pwr_paving_graphic import graphic_cook_inputs, load_graphic_manifest
    path = (Path(__file__).resolve().parents[2] / config['paving_graphic']).resolve()
    image, spec = load_graphic_manifest(path)
    readback_path = path.with_name('graphic.editor.json')
    readback = json.loads(readback_path.read_text(encoding='utf-8'))
    if (readback.get('schema') != 'pwr-paving-graphic-editor-v1'
            or readback.get('manifest_sha256') != digest(path)
            or readback.get('source_sha256') != digest(image)
            or readback.get('source_dimensions') != spec['source']['dimensions']
            or readback.get('build') != spec['build']
            or readback.get('package') != spec['package']+'.T_PWR_PavingGraphic'):
        raise ValueError('Paving graphic editor import proof is stale')
    return {**{f'paving_graphic_{i}': p for i, p in enumerate(graphic_cook_inputs(path))},
            'paving_graphic_editor': readback_path}


def native_grass_pilot_config(config):
    value = config.get('native_grass_pilot')
    if value is None:
        return None
    if not isinstance(value, str) or not value or not config.get('bake_foliage'):
        raise ValueError('Native grass pilot requires an explicit config and baked foliage')
    path = (Path(__file__).resolve().parents[2] / value).resolve()
    doc = json.loads(path.read_text(encoding='utf-8'))
    from landscape_grass_pilot import validate_config
    validate_config(doc, path.parent)
    filtered = doc.get('filtered_foliage', {}).get('spec')
    if (not filtered or not config.get('pcg_foliage')
            or (Path(__file__).resolve().parents[2] / config['pcg_foliage']).resolve() != Path(filtered).resolve()):
        raise ValueError('Native grass pilot requires its exact filtered meadow input')
    return path, doc


def native_grass_pilot_cook_inputs(config, work):
    pilot = native_grass_pilot_config(config)
    if pilot is None:
        return {}
    path, doc = pilot
    from landscape_grass_pilot import validate_readback, material_cook_inputs
    land_path = Path(work) / 'land' / 'landscape.json'
    land = json.loads(land_path.read_text(encoding='utf-8'))
    heights = land_path.parent / land['heights']
    if (doc['grid'] != {k: land[k] for k in doc['grid']}
            or digest(heights) != doc['heights']['sha256']):
        raise ValueError('Native grass pilot differs from the current landscape')
    readback_path = path.parent / 'grass-saved.readback.json'
    readback = json.loads(readback_path.read_text(encoding='utf-8'))
    if readback.get('config_sha256') != digest(path):
        raise ValueError('Native grass saved readback belongs to another config')
    validate_readback(doc, path.parent, readback, require_saved=True)
    inputs = {'native_grass_config': path, 'native_grass_saved': readback_path,
              'native_grass_land': land_path, 'native_grass_current_heights': heights}
    inputs.update({f'native_grass_{key}': path.parent / doc[key]['file']
                   for key in ('mask', 'texture', 'heights')})
    inputs.update({f'native_grass_source_{i}': Path(entry['path'])
                   for i, entry in enumerate(doc['sources'])})
    inputs.update({f'native_grass_filtered_{i}': Path(entry['path'])
                   for i, entry in enumerate(doc.get('filtered_foliage', {}).get('files', []))})
    inputs.update(material_cook_inputs(doc, path.parent))
    return inputs


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
    if 'cliff_mesh' not in inputs and (config.get('tess') is not False or config.get('cliff_uv')):
        raise ValueError('Missing generated cliff mesh')
    inputs.update(landscape_lod_cook_inputs(config, work))
    inputs.update(apron_geology_cook_inputs(config))
    inputs.update(render_only_hism_cook_inputs(config, work))
    inputs.update(render_only_pines_cook_inputs(config, work))
    inputs.update(paving_graphic_cook_inputs(config))
    inputs.update(native_grass_pilot_cook_inputs(config, work))
    if config.get('retarget_cli'):
        inputs['retarget_cli'] = (Path(__file__).resolve().parents[2] / config['retarget_cli']).resolve()
    return inputs


def flux_bed_requires_mesh(config):
    """Saved terrain-backed states contain Ground; other Flux paths need capture geometry."""
    flux = config.get('flux') or {}
    domains = flux.get('domains') or [{}]
    return not (flux.get('heightfield') and all(
        entry.get('playback', flux.get('playback', 'baked')) == 'baked'
        for entry in domains))


def external_asset_inputs(config):
    """Opt-in map dependencies whose packages belong to standalone chunks."""
    result = []
    extras = {str(Path(stem).resolve()) for stem in config.get('extra_containers', [])}
    seen = set()
    for entry in config.get('required_external_assets', []):
        asset, stem = entry['asset'], Path(entry['container']).resolve()
        if not isinstance(asset, str) or not asset.startswith('/Game/') or '.' in asset:
            raise ValueError('External asset must be an exact /Game package path')
        if asset in seen or str(stem) not in extras:
            raise ValueError('External asset is duplicated or its container is not installed by extra_containers')
        seen.add(asset)
        hashes = {suffix: digest(str(stem) + suffix) for suffix in ('.utoc', '.ucas')}
        result.append({'asset': asset, 'container': str(stem), 'hashes': hashes})
    return result


def check_external_assets(config, staged, owned_chunks, cli):
    """Require exactly one owner; never strip Native/Nanite bulk after cooking."""
    inputs = external_asset_inputs(config)
    if not inputs:
        return []
    staged = Path(staged)

    def inventory(path):
        proc = subprocess.run([str(cli), 'container', '--paks', str(staged), str(path)],
                              capture_output=True, text=True)
        if proc.returncode:
            raise ValueError('Cannot inventory external ownership: ' + proc.stderr.strip())
        return proc.stdout

    owned = {chunk: inventory(staged / f'pakchunk{chunk}-Windows.utoc') for chunk in set(owned_chunks)}
    for entry in inputs:
        suffix = 'Meteorite/Content/' + entry['asset'].removeprefix('/Game/') + '.uasset'
        external = inventory(Path(entry['container'] + '.utoc'))
        if external.count(suffix) != 1:
            raise ValueError('Required external package is missing or duplicated: ' + entry['asset'])
        if any(suffix in text for text in owned.values()):
            raise ValueError('External package is duplicated in a map/landscape chunk: ' + entry['asset'])
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
             if (work / filename).is_file()
             and (filename != 'flux_bed.json' or flux_bed_requires_mesh(config))]
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
    # Texture-only conversions are distributed under legacy chunk 985, but
    # the editor still cooks their packages into the per-map spec chunk.
    # Generated meshes must be checked/copied from that actual staged chunk.
    spec = json.loads((Path(config['conversion']) / 'materials.spec.json').read_text(encoding='utf-8'))
    source_chunk = int(spec.get('chunk') or chunk)
    if source_chunk <= 0:
        raise ValueError('Map cook source chunk must be positive')
    inputs = {name: digest(path) for name, path in input_files(code, config, work).items()}
    meshes = check_generated_meshes(code, config, work, staged, source_chunk, cli)
    external_assets = check_external_assets(config, staged, (source_chunk, int(config['chunk'])), cli)
    landscape = {ext: digest(staged / f"pakchunk{int(config['chunk'])}-Windows.{ext}")
                 for ext in ('utoc', 'ucas')}
    token = uuid.uuid4().hex
    dest = work / f'owned-cook-{token}'
    dest.mkdir(parents=True, exist_ok=False)
    hashes = {}
    for ext in ('utoc', 'ucas'):
        src = staged / f'pakchunk{source_chunk}-Windows.{ext}'
        dst = dest / f'{base.name}.{ext}'
        shutil.copyfile(src, dst)
        hashes[ext] = digest(dst)
    receipt = {'schema': 1, 'code': code, 'chunk': chunk, 'source_chunk': source_chunk, 'dir': dest.name,
               'inputs': inputs, 'containers': hashes, 'landscape': landscape,
               'verified_meshes': meshes, 'external_assets': external_assets}
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
    if (flux_bed_requires_mesh(config) and (work / 'flux_bed.json').is_file()
            and f'SM_{code}_FluxBed' not in receipt['verified_meshes']):
        raise ValueError('Owned cook lacks required Flux capture mesh verification; recook after playback changes')
    landscape = {ext: digest(work / 'bake' / f"pakchunk{int(config['chunk'])}-MJOLNIRLAND-Windows.{ext}")
                 for ext in ('utoc', 'ucas')}
    if receipt.get('landscape') != landscape:
        raise ValueError('Landscape bake does not match the verified owned cook')
    inputs = {name: digest(path) for name, path in input_files(code, config, work).items()}
    if receipt.get('inputs') != inputs:
        raise ValueError('Owned cook is stale: conversion or generated cliff changed')
    if receipt.get('external_assets', []) != external_asset_inputs(config):
        raise ValueError('Owned cook external dependencies changed or were not verified')
    target = work / folder / base.name
    for ext in ('utoc', 'ucas'):
        if digest(str(target) + '.' + ext) != receipt.get('containers', {}).get(ext):
            raise ValueError('Owned cook container hash mismatch')
    return target
