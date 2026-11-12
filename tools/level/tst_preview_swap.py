"""Temporarily replace the installed TST hub map with a local test build.

The game must be closed.  Input is an already prepared pack_local_map staging
directory and its conversion materials.spec.json.  This does not publish,
change launcher state, modify shared runtime containers, or touch the hub's
containers: the staged containers go in as local builds above them
(`mjolnir dev install`, dev_paks.py), and restore removes those builds.  The
map's data files are swapped and backed up; the backup manifest is required
for a checked restore.

A local build shadows the hub copy; a package the hub copy has and the build
does not still loads from the hub.
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
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parent))
import dev_paks  # noqa: E402


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
# The local build each staged container goes in as. Names of their own, so
# a swap never replaces (or its restore removes) a build installed otherwise.
BUILD_NAMES = {stem: 'TST-PREVIEW-' + stem.split('-')[1].removeprefix('MJOLNIR') for stem in CONTAINERS}
MANIFEST = 'manifest.json'


def default_cli():
    return os.environ.get('MJOLNIR', str(REPO / 'target/release/mjolnir.exe'))


def run_cli(command):
    """Run a `mjolnir` command; its output, or RuntimeError with it."""
    result = subprocess.run(command, capture_output=True, text=True, errors='replace')
    if result.returncode != 0:
        raise RuntimeError(f'{" ".join(command[1:3])} failed: {result.stdout}{result.stderr}')
    return result.stdout


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
    for index, stem in enumerate(CONTAINERS):
        # The launcher's copy, under its local chunk number and load-order
        # suffix (or the older `-<index>_P` name). Never changed here: the
        # launcher rewrites its library, so it is no longer the cached bytes.
        matches = dev_paks.hub_containers(paks, SLUG, index)
        if len(matches) != 1:
            raise ValueError(f'Expected exactly one installed container for index {index}')
        for ext in ('utoc', 'ucas'):
            if not hashes.get(stem + '.' + ext):
                raise ValueError(f'No hub hash for {stem}.{ext}')
    return identity, hashes


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
    identity, hub_hashes = hub_install(state_path, paks)
    level = read_json(auxiliary(stage, 'tst.level.json'))
    registration = read_json(auxiliary(stage, 'TST.registration.json'))
    if registration.get('code') != CODE or registration.get('world') != '/Game/Levels/Halo1/Solo/TST/TST.TST':
        raise ValueError('Staged registration does not identify the TST world')
    if set(level.get('modes', [])) != {'slayer', 'ctf'}:
        raise ValueError('Staged level is not the supported-mode TST beta configuration')
    builds = []
    for stem in CONTAINERS:
        for ext in ('utoc', 'ucas'):
            source = auxiliary(stage, stem + '.' + ext)
            if source.stat().st_mtime + 2 < threshold:
                raise ValueError(f'Staged container predates the declared build: {stem}.{ext}')
        builds.append({'name': BUILD_NAMES[stem], 'source': str(stage / stem),
                       'sha256': digest(stage / (stem + '.ucas'))})
    # A fresh material cook, mesh and map must all differ from the installed
    # beta; an unchanged native-rock container can be legitimate. The data
    # file is compared: the launcher never changes it.
    for stem in (CONTAINERS[0], CONTAINERS[3], CONTAINERS[4]):
        if digest(stage / (stem + '.ucas')) == hub_hashes[stem + '.ucas']:
            raise ValueError(f'Staged {stem} is identical to the installed beta')
    pairs = []
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
    decals = stage / 'decals'
    # pack_local_map may create an empty directory even when no decals are
    # authored. Do not follow a link (including a Windows junction), accept
    # only a real empty directory, and keep rejecting actual decal content.
    if decals.is_symlink() or getattr(decals, 'is_junction', lambda: False)():
        raise ValueError('Staged decals directory is a link')
    if decals.exists() and (not decals.is_dir() or not within(decals, stage) or
                            next(decals.iterdir(), None) is not None):
        raise ValueError('This TST helper does not install staged decals; review them separately')
    return game, paks, data, identity, pairs, builds


def remove_builds(cli, paks, builds):
    for build in reversed(builds):
        require_game_closed()
        run_cli(dev_paks.remove_command(cli, paks, build['name']))


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
    if manifest.get('format') != 'tst-preview-swap-v2':
        raise ValueError('Unrecognized backup manifest')
    game, paks, data = roots(manifest['game'])
    identity, _ = hub_install(state_path, paks)
    if identity != manifest.get('hub_identity'):
        raise ValueError('The installed TST hub release changed since the backup')
    if {b.get('name') for b in manifest.get('builds', [])} - set(BUILD_NAMES.values()):
        raise ValueError('Unexpected local build in backup manifest')
    fixed = {str(data / name) for name in ('level.json', 'registration.json', 'foliage.bin')}
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
    required = {str(data / 'level.json'), str(data / 'registration.json')}
    if not required.issubset(seen):
        raise ValueError('Backup manifest omits required TST files')
    if Path(manifest['game']).resolve() != game:
        raise ValueError('Backup game path changed')


def install(game, state_path, stage, spec_path, backup, build_start, surfaces_path=SURFACES, cli=None):
    require_game_closed()
    cli = cli or default_cli()
    game, paks, data, identity, pairs, builds = plan(game, state_path, stage, spec_path, surfaces_path, build_start)
    listed = json.loads(run_cli([str(cli), 'dev', 'list', '--json', '--paks', str(paks)]))
    if any(b['name'] in BUILD_NAMES.values() for b in listed.get('builds', [])):
        raise ValueError('A TST preview is already installed; restore it first')
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
    manifest = {'format': 'tst-preview-swap-v2', 'status': 'prepared', 'game': str(game),
                'hub_identity': identity, 'build_start': build_start,
                'conversion_spec_sha256': digest(spec_path), 'files': entries, 'builds': builds}
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
        for build in builds:
            require_game_closed()
            if digest(Path(build['source'] + '.ucas')) != build['sha256']:
                raise RuntimeError(f'Staged container changed during swap: {build["source"]}')
            run_cli(dev_paks.install_command(cli, paks, build['source'], build['name']))
        manifest['status'] = 'installed'
        write_manifest(backup, manifest)
    except Exception:
        try:
            remove_builds(cli, paks, builds)
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


def restore(backup, state_path, game, cli=None):
    require_game_closed()
    cli = cli or default_cli()
    backup = Path(backup).resolve(strict=True)
    manifest = read_json(backup / MANIFEST)
    if manifest.get('status') not in ('installed', 'installing', 'recovery_required'):
        raise ValueError('Backup does not describe an active or interrupted swap')
    if Path(manifest['game']).resolve() != Path(game).resolve(strict=True):
        raise ValueError('Selected game does not match the backup manifest')
    validate_manifest(manifest, backup, state_path)
    restore_entries(manifest, backup, allow_original=manifest['status'] != 'installed')
    remove_builds(cli, roots(manifest['game'])[1], manifest.get('builds', []))
    manifest['status'] = 'restored'
    write_manifest(backup, manifest)
    return backup / MANIFEST


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--game', type=Path, required=True, help='Halo Campaign Evolved installation root')
    parser.add_argument('--hub-state', type=Path, required=True, help='Launcher hub_state.json (read only)')
    parser.add_argument('--cli', default=None, help='mjolnir.exe (default: $MJOLNIR or target/release)')
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
        result = install(args.game, args.hub_state, args.stage, args.spec, args.backup, args.build_start,
                         cli=args.cli)
    else:
        result = restore(args.backup, args.hub_state, args.game, cli=args.cli)
    print(f'{args.command} complete; manifest: {result}')


if __name__ == '__main__':
    main()
