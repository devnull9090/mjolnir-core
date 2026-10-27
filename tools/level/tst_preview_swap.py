"""Temporarily replace the installed TST hub map with a local test build.

The game must be closed.  Input is an already prepared pack_local_map staging
directory and its conversion materials.spec.json.  This does not publish,
change launcher state, modify shared runtime containers, or touch pak stubs.
The backup manifest is required for a checked restore.
"""
import argparse
import csv
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile


REPO = Path(__file__).resolve().parents[2]
SURFACES = REPO / 'levels/test/tst/surfaces.json'
SLUG = 'tst-proving-ground'
CODE = 'TST'
CONTAINERS = (
    'pakchunk968-MJOLNIRCOOK-TST_P',
    'pakchunk969-MJOLNIRLAND-TST_P',
    'pakchunk970-MJOLNIRROCK-TST_P',
    'pakchunk986-MJOLNIRMESH-TST_P',
    'pakchunk997-MJOLNIRMAP-TST_P',
)
MANIFEST = 'manifest.json'


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def within(path, root):
    return Path(path).resolve().is_relative_to(Path(root).resolve())


def real_file(path, root):
    path = Path(path)
    if path.is_symlink() or not path.is_file() or not within(path, root):
        raise ValueError(f'Missing, linked, or out-of-bounds file: {path}')
    return path.resolve()


def require_game_closed():
    if os.name != 'nt':
        raise RuntimeError('Game process detection requires Windows')
    result = subprocess.run(['tasklist', '/FO', 'CSV', '/NH'], check=True,
                            capture_output=True, text=True, errors='replace')
    names = [row[0].lower() for row in csv.reader(result.stdout.splitlines()) if row]
    if any(name.startswith('halocampaignevolved') and name.endswith('.exe') for name in names):
        raise RuntimeError('Close Halo Campaign Evolved before changing map files')


def atomic_copy(src, dst):
    """Replace one file only after its copy is complete, on the same volume."""
    dst = Path(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='.tst-preview-', dir=dst.parent)
    os.close(fd)
    try:
        shutil.copyfile(src, temporary)
        os.replace(temporary, dst)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def write_manifest(folder, value):
    path = Path(folder) / MANIFEST
    fd, temporary = tempfile.mkstemp(prefix='.manifest-', dir=folder)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8', newline='\n') as stream:
            json.dump(value, stream, indent=2)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def roots(game):
    game = Path(game).resolve(strict=True)
    paks = (game / 'Meteorite/Content/Paks').resolve(strict=True)
    maps = (game / 'Meteorite/Binaries/Win64/ue4ss/MJOLNIRMaps').resolve(strict=True)
    data = (maps / CODE).resolve(strict=True)
    if not all(p.is_dir() and within(p, game) for p in (paks, maps, data)):
        raise ValueError('Game paths leave the selected game directory')
    return game, paks, data


def hub_install(state_path, paks):
    state = read_json(state_path)
    matches = [entry for entry in state.get('installed', []) if entry.get('slug') == SLUG]
    if len(matches) != 1:
        raise ValueError('Expected exactly one installed TST hub entry')
    entry = matches[0]
    if entry.get('map_code') != CODE or tuple(entry.get('containers', [])) != CONTAINERS:
        raise ValueError('Installed TST container list differs from the expected five containers')
    identity = {key: entry.get(key) for key in ('slug', 'map_code', 'release_id', 'version', 'sha256')}
    if not all(identity.values()):
        raise ValueError('Installed TST release identity is incomplete')
    hashes = entry.get('container_hashes') or {}
    destinations = {}
    for index, stem in enumerate(CONTAINERS):
        matches = list(paks.glob(f'pakchunk*-MJOLNIRHUB-{SLUG}-{index}_P.utoc'))
        if len(matches) != 1:
            raise ValueError(f'Expected exactly one installed container for index {index}')
        base = matches[0].with_suffix('')
        real_file(base.with_suffix('.pak'), paks)  # The existing stub is never changed.
        for ext in ('utoc', 'ucas'):
            path = real_file(base.with_suffix('.' + ext), paks)
            expected = hashes.get(stem + '.' + ext)
            if not expected:
                raise ValueError(f'No hub hash for {stem}.{ext}')
            destinations[stem + '.' + ext] = (path, expected)
    return identity, hashes, destinations


def parse_build_time(value):
    try:
        when = dt.datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError as exc:
        raise ValueError('Build start must be an ISO 8601 timestamp with timezone') from exc
    if when.tzinfo is None:
        raise ValueError('Build start must include a timezone')
    return when.timestamp()


def inspect_spec(spec_path, surfaces_path):
    spec = read_json(spec_path)
    expected = read_json(surfaces_path)['surfaces']
    actual = spec.get('authored_surfaces') or {}
    if spec.get('chunk') != 968 or spec.get('root') != '/Game/MJOLNIR/Maps/TST':
        raise ValueError('Conversion spec does not identify the TST 968 material chunk')
    if set(actual) != set(expected) or len(actual) != 12:
        raise ValueError('Conversion spec does not contain the twelve authored TST surface roles')
    for role, settings in expected.items():
        scalar_keys = ('shader', 'tag', 'metallic', 'roughness', 'tint', 'tile_m',
                       'normal_strength', 'normal_convention')
        if any(actual[role].get(key) != settings[key] for key in scalar_keys if key in settings):
            raise ValueError(f'Conversion material does not match source role: {role}')


def auxiliary(stage, name):
    path = Path(name)
    if path.is_absolute() or '..' in path.parts or not path.parts:
        raise ValueError(f'Invalid staged auxiliary path: {name}')
    return real_file(stage / path, stage)


def plan(game, state_path, stage, spec_path, surfaces_path, build_start):
    game, paks, data = roots(game)
    stage = Path(stage).resolve(strict=True)
    spec_path = Path(spec_path).resolve(strict=True)
    surfaces_path = Path(surfaces_path).resolve(strict=True)
    if within(stage, game) or within(game, stage) or within(spec_path, game):
        raise ValueError('Staging and conversion spec must be outside the game installation')
    inspect_spec(spec_path, surfaces_path)
    threshold = parse_build_time(build_start)
    if spec_path.stat().st_mtime + 2 < threshold:
        raise ValueError('Conversion materials spec predates the declared build')
    identity, hub_hashes, container_destinations = hub_install(state_path, paks)
    level = read_json(auxiliary(stage, 'tst.level.json'))
    registration = read_json(auxiliary(stage, 'TST.registration.json'))
    if registration.get('code') != CODE or registration.get('world') != '/Game/Levels/Halo1/Solo/TST/TST.TST':
        raise ValueError('Staged registration does not identify the TST world')
    if set(level.get('modes', [])) != {'slayer', 'team_slayer', 'ctf'}:
        raise ValueError('Staged level is not the supported-mode TST beta configuration')
    pairs = []
    for name, (destination, expected) in container_destinations.items():
        source = auxiliary(stage, name)
        if source.stat().st_mtime + 2 < threshold:
            raise ValueError(f'Staged container predates the declared build: {name}')
        if digest(destination) != expected:
            raise ValueError(f'Installed hub container differs from launcher hash: {destination.name}')
        pairs.append((source, destination, expected, name))
    # A fresh material cook, mesh and map must all differ from the installed
    # beta; an unchanged native-rock container can be legitimate.
    for stem in (CONTAINERS[0], CONTAINERS[3], CONTAINERS[4]):
        source, destination, _, _ = next(pair for pair in pairs if pair[3] == stem + '.ucas')
        if digest(source) == digest(destination):
            raise ValueError(f'Staged {stem} is identical to the installed beta')
    for staged_name, installed_name in (('tst.level.json', 'level.json'),
                                        ('TST.registration.json', 'registration.json')):
        source = auxiliary(stage, staged_name)
        if source.stat().st_mtime + 2 < threshold:
            raise ValueError(f'Staged metadata predates the declared build: {staged_name}')
        destination = real_file(data / installed_name, data)
        expected = hub_hashes.get('map/' + installed_name)
        if not expected or digest(destination) != expected:
            raise ValueError(f'Installed map data differs from launcher hash: {installed_name}')
        pairs.append((source, destination, expected, 'map/' + installed_name))
    foliage = (level.get('foliage') or {}).get('file')
    if foliage:
        if foliage != 'foliage.bin':
            raise ValueError('Unexpected foliage file name')
        source = auxiliary(stage, foliage)
        if source.stat().st_mtime + 2 < threshold:
            raise ValueError('Staged foliage predates the declared build')
        destination = data / foliage
        expected = hub_hashes.get('map/' + foliage)
        if not expected or digest(real_file(destination, data)) != expected:
            raise ValueError('Installed foliage differs from launcher hash')
        pairs.append((source, destination.resolve(), expected, 'map/' + foliage))
    if (level.get('flux') or {}).get('state'):
        state_file = auxiliary(stage, 'flux_state/state.json')
        state = read_json(state_file)
        if state != level['flux']['state']:
            raise ValueError('Staged baked-water metadata does not match the level')
        for key in ('height', 'velocity'):
            name = state.get(key)
            if not isinstance(name, str) or not Path(name).parts or Path(name).parts[0] != 'flux_state':
                raise ValueError(f'Invalid baked-water {key} path')
            auxiliary(stage, name)
        directory = stage / 'flux_state'
        files = sorted(p for p in directory.rglob('*') if p.is_file() or p.is_symlink())
        if not files:
            raise ValueError('Staged baked-water state is empty')
        for file in files:
            source = auxiliary(stage, file.relative_to(stage))
            rel = file.relative_to(stage)
            destination = data / rel
            if not within(destination, data) or destination.is_symlink():
                raise ValueError(f'Unsafe water state destination: {destination}')
            old = digest(destination) if destination.is_file() else None
            pairs.append((source, destination.resolve(), old, 'map/' + rel.as_posix()))
    if (stage / 'decals').exists():
        raise ValueError('This TST helper does not install staged decals; review them separately')
    return game, data, identity, pairs


def copy_entry(entry, backup, restore=False):
    dst = Path(entry['destination'])
    expected = entry['original_sha256'] if restore else entry['staged_sha256']
    if restore and expected is None:
        dst.unlink()
    else:
        src = Path(backup) / entry['backup'] if restore else Path(entry['source'])
        if digest(src) != expected:
            raise RuntimeError(f'Copy input hash changed: {src}')
        atomic_copy(src, dst)
        if digest(dst) != expected:
            raise RuntimeError(f'Copied file hash does not match: {dst}')


def restore_entries(manifest, backup, *, allow_original=False):
    """Preflight the entire set before touching any destination."""
    for entry in manifest['files']:
        original = entry['original_sha256']
        if original is not None:
            saved = real_file(Path(backup) / entry['backup'], backup)
            if digest(saved) != original:
                raise ValueError(f'Backup hash mismatch: {saved}')
        dst = Path(entry['destination'])
        current = digest(dst) if dst.is_file() and not dst.is_symlink() else None
        allowed = (entry['staged_sha256'], original) if allow_original else (entry['staged_sha256'],)
        if current not in allowed:
            raise ValueError(f'Test file changed since installation: {dst}')
    for entry in reversed(manifest['files']):
        dst = Path(entry['destination'])
        current = digest(dst) if dst.is_file() else None
        if current == entry['original_sha256']:
            continue
        if current != entry['staged_sha256']:
            raise ValueError(f'Test file changed during restoration: {dst}')
        require_game_closed()
        copy_entry(entry, backup, restore=True)


def validate_manifest(manifest, backup, state_path):
    if manifest.get('format') != 'tst-preview-swap-v1':
        raise ValueError('Unrecognized backup manifest')
    game, paks, data = roots(manifest['game'])
    identity, _, destinations = hub_install(state_path, paks)
    if identity != manifest.get('hub_identity'):
        raise ValueError('The installed TST hub release changed since the backup')
    fixed = {str(path) for path, _ in destinations.values()}
    fixed.update(str(data / name) for name in ('level.json', 'registration.json', 'foliage.bin'))
    seen = set()
    for entry in manifest['files']:
        destination = Path(entry['destination'])
        actual = str(destination.resolve())
        if actual in seen or destination.is_symlink():
            raise ValueError('Duplicate or linked destination in backup manifest')
        seen.add(actual)
        in_water = within(destination, data) and within(destination, data / 'flux_state')
        if actual not in fixed and not in_water:
            raise ValueError(f'Unexpected destination in backup manifest: {destination}')
        saved = Path(backup) / entry['backup']
        if not within(saved, backup):
            raise ValueError('Backup path leaves its manifest directory')
    required = {str(path) for path, _ in destinations.values()} | {str(data / 'level.json'), str(data / 'registration.json')}
    if not required.issubset(seen):
        raise ValueError('Backup manifest omits required TST files')
    if Path(manifest['game']).resolve() != game:
        raise ValueError('Backup game path changed')


def install(game, state_path, stage, spec_path, backup, build_start, surfaces_path=SURFACES):
    require_game_closed()
    game, data, identity, pairs = plan(game, state_path, stage, spec_path, surfaces_path, build_start)
    backup = Path(backup).resolve()
    if backup.exists() or within(backup, game) or within(game, backup) or within(backup, stage) or within(stage, backup):
        raise ValueError('Backup must be a new directory outside both the game and staging trees')
    backup.mkdir(parents=False, exist_ok=False)
    entries = []
    for index, (source, destination, original, name) in enumerate(pairs):
        if original is not None and digest(destination) != original:
            raise ValueError(f'Installed file changed while preparing backup: {destination}')
        saved_name = f'{index:03}.backup'
        if original is not None:
            shutil.copy2(destination, backup / saved_name)
            if digest(backup / saved_name) != original:
                raise RuntimeError(f'Backup verification failed: {destination}')
        entries.append({'name': name, 'source': str(source), 'destination': str(destination),
                        'original_sha256': original, 'staged_sha256': digest(source), 'backup': saved_name})
    manifest = {'format': 'tst-preview-swap-v1', 'status': 'prepared', 'game': str(game),
                'hub_identity': identity, 'build_start': build_start,
                'conversion_spec_sha256': digest(spec_path), 'files': entries}
    write_manifest(backup, manifest)
    try:
        manifest['status'] = 'installing'
        write_manifest(backup, manifest)
        for entry in entries:
            require_game_closed()
            current = digest(entry['destination']) if Path(entry['destination']).is_file() else None
            if current != entry['original_sha256']:
                raise RuntimeError(f'Installed file changed during swap: {entry["destination"]}')
            copy_entry(entry, backup)
        manifest['status'] = 'installed'
        write_manifest(backup, manifest)
    except Exception:
        try:
            restore_entries(manifest, backup, allow_original=True)
            manifest['status'] = 'rolled_back'
            write_manifest(backup, manifest)
        except Exception as rollback:
            manifest['status'] = 'recovery_required'
            manifest['rollback_error'] = str(rollback)
            write_manifest(backup, manifest)
            raise RuntimeError(f'Swap failed and rollback requires attention; see {backup / MANIFEST}') from rollback
        raise
    return backup / MANIFEST


def restore(backup, state_path, game):
    require_game_closed()
    backup = Path(backup).resolve(strict=True)
    manifest = read_json(backup / MANIFEST)
    if manifest.get('status') not in ('installed', 'installing', 'recovery_required'):
        raise ValueError('Backup does not describe an active or interrupted swap')
    if Path(manifest['game']).resolve() != Path(game).resolve(strict=True):
        raise ValueError('Selected game does not match the backup manifest')
    validate_manifest(manifest, backup, state_path)
    restore_entries(manifest, backup, allow_original=manifest['status'] != 'installed')
    manifest['status'] = 'restored'
    write_manifest(backup, manifest)
    return backup / MANIFEST


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--game', type=Path, required=True, help='Halo Campaign Evolved installation root')
    parser.add_argument('--hub-state', type=Path, required=True, help='Launcher hub_state.json (read only)')
    sub = parser.add_subparsers(dest='command', required=True)
    add = sub.add_parser('install')
    add.add_argument('--stage', type=Path, required=True, help='Fresh pack_local_map.prepare output')
    add.add_argument('--spec', type=Path, required=True, help='Matching conversion materials.spec.json')
    add.add_argument('--backup', type=Path, required=True, help='New backup directory outside the game')
    add.add_argument('--build-start', required=True, help='Build start, ISO 8601 with timezone')
    back = sub.add_parser('restore')
    back.add_argument('--backup', type=Path, required=True)
    args = parser.parse_args()
    if args.command == 'install':
        result = install(args.game, args.hub_state, args.stage, args.spec, args.backup, args.build_start)
    else:
        result = restore(args.backup, args.hub_state, args.game)
    print(f'{args.command} complete; manifest: {result}')


if __name__ == '__main__':
    main()
