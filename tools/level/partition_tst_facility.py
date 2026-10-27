#!/usr/bin/env python3
"""Split dense TST render-only facility triangles out of a classic JMS.

The original JMS is never modified.  A new output directory contains a CE
structure JMS, a complementary native render-detail glTF/bin, and a manifest.
Only this map's authored metal render-only triangles inside the verified
facility bounds are moved; collision, light lenses, water and teleporters stay
in the CE structure. Coordinates in JMS are hundredths of a CE world unit.

This preserves source geometry and materials, not proof of game lighting or
runtime performance. The compiled native and CE results require in-game review.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath, PureWindowsPath
import tempfile

import numpy as np


def sha256(path: Path) -> str:
    with path.open('rb') as source:
        return hashlib.file_digest(source, 'sha256').hexdigest()


def owned_texture_hashes(library: Path) -> dict[str, str]:
    """Hash palette textures using portable, palette-relative names only."""
    library = Path(library).resolve(strict=True)
    base = library.parent
    document = json.loads(library.read_text(encoding='utf-8'))
    textures = {}
    for surface in document['surfaces'].values():
        for key in ('albedo', 'roughness_map', 'normal_map'):
            if key not in surface:
                continue
            raw = surface[key]
            if not isinstance(raw, str) or not raw or '\\' in raw:
                raise ValueError(f'Invalid owned texture path: {raw!r}')
            posix, windows = PurePosixPath(raw), PureWindowsPath(raw)
            if (posix.is_absolute() or windows.is_absolute() or windows.drive or
                    raw != posix.as_posix() or any(part in ('.', '..') for part in posix.parts)):
                raise ValueError(f'Owned texture path escapes or is not canonical: {raw}')
            path = base
            for part in posix.parts:
                path = path / part
                if path.is_symlink() or (hasattr(path, 'is_junction') and path.is_junction()):
                    raise ValueError(f'Owned texture path contains a link: {raw}')
            try:
                resolved = path.resolve(strict=True)
                resolved.relative_to(base)
            except (OSError, ValueError) as exc:
                raise ValueError(f'Owned texture is missing or outside the palette: {raw}') from exc
            if not resolved.is_file():
                raise ValueError(f'Owned texture is not a file: {raw}')
            textures[raw] = sha256(resolved)
    if not textures:
        raise ValueError('Palette has no owned textures')
    return dict(sorted(textures.items()))


def roles_from_library(path: Path) -> dict[str, tuple[str, str]]:
    """Map exact CE shader leaf names to validated authored roles and tags."""
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from authored_surfaces import load_library
    roles = {}
    for role, data in load_library(path).items():
        tag = data['tag'].replace('\\', '/').lower()
        leaf = tag.rsplit('/', 1)[-1]
        if leaf in roles:
            raise ValueError(f'Duplicate authored shader leaf: {leaf}')
        roles[leaf] = (role, tag)
    return roles


def read_jms(path: Path):
    """Read this map's 8200 JMS, rejecting unsupported or indexed variants."""
    with path.open('rb') as stream:
        prefix = []

        def line():
            value = stream.readline()
            if not value:
                raise ValueError('Unexpected end of JMS')
            prefix.append(value)
            return value.strip()

        if line() != b'8200':
            raise ValueError('Expected a version 8200 JMS')
        line()  # checksum
        nodes = int(line())
        if not 0 <= nodes <= 256:
            raise ValueError('Unexpected JMS node count')
        for _ in range(nodes * 5):
            line()
        count = int(line())
        if not 0 < count <= 4096:
            raise ValueError('Unexpected JMS material count')
        materials = []
        for _ in range(count):
            materials.append(line().decode('utf-8'))
            line()  # material texture reference
        if int(line()) != 0:
            raise ValueError('JMS markers are unsupported; source left unchanged')
        region_count = int(line())
        if not 0 < region_count <= 1024:
            raise ValueError('Unexpected JMS region count')
        for _ in range(region_count):
            line()
        vertices = int(line())
        if vertices <= 0 or vertices > 3_000_000 or vertices % 3:
            raise ValueError('Unexpected JMS vertex count')
        rows = []
        positions = np.empty((vertices, 3), dtype=np.float64)
        normals = np.empty((vertices, 3), dtype=np.float64)
        uvs = np.empty((vertices, 2), dtype=np.float64)
        for i in range(vertices):
            row = [stream.readline() for _ in range(7)]
            if any(not value for value in row):
                raise ValueError('Unexpected end of JMS vertex data')
            rows.append(b''.join(row))
            positions[i] = [float(value) for value in row[1].split()]
            normals[i] = [float(value) for value in row[2].split()]
            uvs[i] = [float(value) for value in row[5].split()]
        if not all(np.isfinite(values).all() for values in (positions, normals, uvs)):
            raise ValueError('JMS has non-finite geometry or UVs')
        triangles = int(stream.readline().strip())
        if triangles * 3 != vertices:
            raise ValueError('Expected three private vertices per JMS triangle')
        material_ids = np.empty(triangles, dtype=np.int32)
        regions = np.empty(triangles, dtype=np.int32)
        for i in range(triangles):
            regions[i] = int(stream.readline().strip())
            material_ids[i] = int(stream.readline().strip())
            indices = tuple(int(value) for value in stream.readline().split())
            if indices != (3 * i, 3 * i + 1, 3 * i + 2):
                raise ValueError(f'JMS triangle {i} does not have private ordered vertices')
            if not 0 <= material_ids[i] < count:
                raise ValueError(f'Invalid material index on triangle {i}')
            if not 0 <= regions[i] < region_count:
                raise ValueError(f'Invalid region index on triangle {i}')
        trailing = stream.read()
    return prefix, materials, rows, positions, normals, uvs, regions, material_ids, trailing


def partition(source: Path, library: Path, destination: Path) -> dict:
    source = Path(source).resolve(strict=True)
    library = Path(library).resolve(strict=True)
    destination = Path(destination).absolute()
    if destination.exists():
        raise FileExistsError(f'Output directory already exists: {destination}')
    if not destination.parent.is_dir():
        raise ValueError('Output parent directory must already exist')
    # The originals are not outputs even when the caller chooses a directory
    # adjacent to them. New-directory semantics avoid any overwrite.
    if source == destination or library == destination:
        raise ValueError('Output directory cannot be an input')
    source_digest, library_digest = sha256(source), sha256(library)
    texture_hashes = owned_texture_hashes(library)
    roles = roles_from_library(library)
    prefix, materials, rows, positions, normals, uvs, regions, material_ids, trailing = read_jms(source)
    tri_pos = positions.reshape(-1, 3, 3)
    centre = tri_pos.mean(axis=1)
    inside = ((np.abs(centre[:, 0]) < 1800) & (centre[:, 1] > 700)
              & (centre[:, 1] < 1900) & (centre[:, 2] < 240))
    metal_ids = {i: name[:-1].lower() for i, name in enumerate(materials)
                 if name.lower().startswith('tst_metal_') and name.endswith('!')}
    selected = inside & np.isin(material_ids, list(metal_ids))
    selected_ids = np.flatnonzero(selected)
    kept_ids = np.flatnonzero(~selected)
    if not len(selected_ids) or not len(kept_ids):
        raise ValueError('Partition is empty; source may not be the expected TST export')
    unknown = sorted({metal_ids[int(material_ids[i])] for i in selected_ids
                      if metal_ids[int(material_ids[i])] not in roles})
    if unknown:
        raise ValueError(f'Facility render shaders have no exact authored role: {unknown}')

    # Build in a new sibling directory; the final rename publishes all three
    # files together. On failure the uniquely named temporary directory stays
    # available for diagnosis, rather than deleting user data.
    temp = Path(tempfile.mkdtemp(prefix='.tst-facility-partition-', dir=destination.parent))
    ce_path = temp / 'tst-ce-structure.JMS'
    with ce_path.open('wb') as out:
        # Deterministic LF output matches the verified HEK diagnostic export;
        # all retained vertex fields are unchanged apart from line endings.
        out.writelines(line.replace(b'\r\n', b'\n') for line in prefix[:-1])
        out.write(f'{len(kept_ids) * 3}\n'.encode())
        for i in kept_ids:
            for vertex in range(int(i) * 3, int(i) * 3 + 3):
                out.write(rows[vertex].replace(b'\r\n', b'\n'))
        out.write(f'{len(kept_ids)}\n'.encode())
        for new_index, old_index in enumerate(kept_ids):
            out.write(f'{regions[old_index]}\n{material_ids[old_index]}\n'
                      f'{3*new_index}\t{3*new_index+1}\t{3*new_index+2}\n'.encode())
        out.write(trailing.replace(b'\r\n', b'\n'))

    doc = {'asset': {'version': '2.0', 'generator': 'MJOLNIR TST facility partition'},
           'buffers': [{'uri': 'tst-facility-detail.bin', 'byteLength': 0}],
           'bufferViews': [], 'accessors': [], 'materials': [],
           'meshes': [{'primitives': []}], 'nodes': [{'mesh': 0}],
           'scenes': [{'nodes': [0]}], 'scene': 0}
    binary = bytearray()

    def accessor(data, component, shape):
        arr = np.asarray(data, dtype='<f4' if component == 5126 else '<u4')
        offset = len(binary)
        binary.extend(arr.tobytes(order='C'))
        view = len(doc['bufferViews'])
        doc['bufferViews'].append({'buffer': 0, 'byteOffset': offset, 'byteLength': len(binary) - offset})
        entry = {'bufferView': view, 'componentType': component, 'count': len(arr), 'type': shape}
        if shape == 'VEC3' and component == 5126:
            entry['min'] = [float(x) for x in arr.min(axis=0)]
            entry['max'] = [float(x) for x in arr.max(axis=0)]
        index = len(doc['accessors'])
        doc['accessors'].append(entry)
        return index

    summary = {}
    for material_id, leaf in sorted(metal_ids.items(), key=lambda item: roles.get(item[1], ('~', ''))[0]):
        ids = selected_ids[material_ids[selected_ids] == material_id]
        if not len(ids):
            continue
        role, tag = roles[leaf]
        vertex_ids = (ids[:, None] * 3 + np.arange(3)).reshape(-1)
        # JMS uses hundredths of CE world units. Its Halo-to-glTF axis map
        # matches halo2ue: (x, z, -y); 1 CE unit is 3.048 metres.
        src = positions[vertex_ids]
        p = np.column_stack((src[:, 0], src[:, 2], -src[:, 1])) * 0.03048
        nsrc = normals[vertex_ids]
        n = np.column_stack((nsrc[:, 0], nsrc[:, 2], -nsrc[:, 1]))
        uv = uvs[vertex_ids]
        name = f'tst_native_detail_{role}'
        material_index = len(doc['materials'])
        doc['materials'].append({'name': name, 'extras': {'halo': {
            'material': tag.replace('/', '_'), 'shader_class': 'senv',
            'tag_path': tag, 'native_authored_detail': True}}})
        prim = {'attributes': {'POSITION': accessor(p, 5126, 'VEC3'),
                               'NORMAL': accessor(n, 5126, 'VEC3'),
                               'TEXCOORD_0': accessor(uv, 5126, 'VEC2')},
                'indices': accessor(np.arange(len(vertex_ids)), 5125, 'SCALAR'),
                'material': material_index}
        doc['meshes'][0]['primitives'].append(prim)
        summary[role] = {'triangles': int(len(ids)), 'shader_tag': tag,
                         'source_material': materials[material_id], 'gltf_material': name}
    doc['buffers'][0]['byteLength'] = len(binary)
    gltf = temp / 'tst-facility-detail.gltf'
    gltf_bin = temp / 'tst-facility-detail.bin'
    gltf_bin.write_bytes(binary)
    gltf.write_text(json.dumps(doc, separators=(',', ':')) + '\n', encoding='utf-8')
    if (sha256(source) != source_digest or sha256(library) != library_digest or
            owned_texture_hashes(library) != texture_hashes):
        raise RuntimeError('Source, material library or textures changed during partition; outputs not published')
    manifest = {'format': 'tst-facility-partition-v1', 'source_sha256': source_digest,
                'surface_library_sha256': library_digest, 'texture_hashes': texture_hashes,
                'source_triangles': len(selected),
                'ce_triangles': len(kept_ids), 'native_triangles': len(selected_ids),
                'predicate': 'tst_metal_*! and abs(x)<1800, 700<y<1900, z<240 in JMS units',
                'roles': summary, 'files': {p.name: sha256(p) for p in (ce_path, gltf, gltf_bin)},
                'scope': 'Render detail only; all non-selected JMS triangles and their records stay in CE. Game lighting and runtime unverified.'}
    (temp / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    os.rename(temp, destination)
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', required=True, type=Path, help='Full Blender-exported TST JMS')
    parser.add_argument('--surfaces', required=True, type=Path, help='TST surfaces.json')
    parser.add_argument('--out-dir', required=True, type=Path, help='New output directory; must not exist')
    args = parser.parse_args()
    result = partition(args.source, args.surfaces, args.out_dir)
    print(json.dumps({'source_triangles': result['source_triangles'], 'ce_triangles': result['ce_triangles'],
                      'native_triangles': result['native_triangles'], 'roles': list(result['roles']),
                      'out_dir': str(args.out_dir)}, indent=2))


if __name__ == '__main__':
    main()
