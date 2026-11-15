"""Bind an unchanged original albedo to the optional PWR paving material.

The 1254-square image is not a height/normal map. UE performs an explicitly
declared 1024-square build resize and generates the mip chain; this module
never edits or resamples image pixels. The same validator runs in the editor,
owned-cook sealing, and final cooked readback.
"""
from __future__ import annotations
import argparse
import copy
import hashlib
import json
from pathlib import Path
import shutil
import struct

ROOT = Path(__file__).resolve().parents[2]
ASSET = ROOT / 'levels/warfare/pwr/materials/forerunner-panels-v7'
PACKAGE = '/Game/MJOLNIR/CETrial/T_PWR_PavingGraphic'
PARENT = '/Game/MJOLNIR/CETrial/M_CE_PWRPaving.M_CE_PWRPaving'
SOURCE_SHA = 'c99688c682c5973f9ce52000d5b7445af1d9d6a4a7edd0a1bce63d851cfda9fa'
BUILD = {'dimensions': [1024, 1024], 'power_of_two_mode': 'ResizeToSpecificResolution',
         'mips': 11, 'compression': 'BC7', 'srgb': True, 'virtual_texture': False,
         'address_x': 'mirror', 'address_y': 'mirror'}


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def dump(path, value):
    Path(path).write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8')


def png_dimensions(path):
    with Path(path).open('rb') as stream:
        header = stream.read(33)
    if len(header) != 33 or header[:8] != b'\x89PNG\r\n\x1a\n' or header[12:16] != b'IHDR':
        raise ValueError('Paving graphic must be an original PNG')
    if header[24:26] != bytes((8, 2)):
        raise ValueError('Paving graphic requires original 8-bit RGB source')
    return list(struct.unpack('>II', header[16:24]))


def load_graphic_manifest(path):
    path = Path(path).resolve()
    spec = read(path)
    if spec.get('schema') != 'pwr-paving-graphic-v1' or spec.get('package') != PACKAGE:
        raise ValueError('Unrecognized PWR paving graphic binding')
    if spec.get('build') != BUILD:
        raise ValueError('Paving graphic build must preserve the explicit 1024 BC7 sRGB mip contract')
    source = spec.get('source', {})
    image = Path(source.get('path', ''))
    if not image.is_absolute() or not image.is_file():
        raise ValueError('Paving graphic source must identify an existing absolute file')
    if digest(image) != source.get('sha256') or source.get('sha256') != SOURCE_SHA:
        raise ValueError('Original generated paving image changed')
    if png_dimensions(image) != source.get('dimensions') or source.get('dimensions') != [1254, 1254]:
        raise ValueError('Paving graphic original dimensions changed')
    prompt = Path(source.get('prompt', ''))
    if not prompt.is_absolute() or not prompt.is_file() or digest(prompt) != source.get('prompt_sha256'):
        raise ValueError('Paving graphic prompt provenance changed')
    if spec.get('encoding') != 'original sRGB albedo; not height, normal, roughness or AO':
        raise ValueError('Paving graphic is an albedo, not physical surface data')
    return image, spec


def graphic_cook_inputs(path):
    image, spec = load_graphic_manifest(path)
    return [Path(path).resolve(), image.resolve(), Path(spec['source']['prompt']).resolve()]


def prepare(source, out):
    source, out = Path(source).resolve(), Path(out).resolve()
    previous = read(source / 'receipt.json')
    # A fresh directory makes stale material recipes or generated files visible.
    out.mkdir(parents=True, exist_ok=False)
    (out / 'textures').mkdir()
    for name, expected in previous['files'].items():
        file = source / name
        if digest(file) != expected:
            raise ValueError('Frozen native paving input changed: ' + str(file))
        target = out / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(file, target)
    image, prompt = ASSET / 'panel-albedo.png', ASSET / 'prompt.txt'
    manifest = {'schema': 'pwr-paving-graphic-v1', 'package': PACKAGE,
                'source': {'path': str(image), 'sha256': digest(image),
                           'dimensions': png_dimensions(image), 'prompt': str(prompt),
                           'prompt_sha256': digest(prompt), 'generator': 'built-in image_gen'},
                'build': BUILD, 'encoding': 'original sRGB albedo; not height, normal, roughness or AO',
                'mapping': '12m world-projected source cells; mirrored addressing gives a 24m repeat',
                'source_seamless': False, 'source_modified': False,
                'validation': 'Candidate only; requires editor import, final cook readback and live visual acceptance'}
    dump(out / 'graphic.json', manifest)
    load_graphic_manifest(out / 'graphic.json')
    recipes = copy.deepcopy(previous['recipes'])
    changes = {'alloy': ([.29, .31, .31, 1], .64),
               'joint': ([.14, .16, .16, 1], .70),
               'floor': ([.26, .29, .29, 1], .66),
               'wall': ([.28, .30, .30, 1], .65)}
    for name, (tint, roughness) in changes.items():
        recipes[name]['PavingTint'] = tint
        recipes[name]['PavingParams'][1] = roughness
        # Scale(cm), enable, contribution, neutral reference(linear). Both slots
        # bind the image deliberately. No inferred relief from albedo brightness.
        recipes[name]['PavingGraphic'] = [1200, 1, 1, .19]
    materials = [{'parent': PARENT, 'vectors': recipes[k],
                  'textures': {'PanelGraphic': PACKAGE + '.T_PWR_PavingGraphic'}}
                 for k in ('alloy', 'joint')]
    overrides = read(source / 'material-overrides.json')
    for rule, name in zip(overrides['overrides'][:2], ('floor', 'wall')):
        rule['vectors'] = recipes[name]
        rule.setdefault('textures', {})['PanelGraphic'] = PACKAGE + '.T_PWR_PavingGraphic'
    dump(out / 'materials.json', materials)
    dump(out / 'material-overrides.json', overrides)
    report = copy.deepcopy(previous)
    report.update({'schema': 'pwr-paving-materials-v4', 'recipes': recipes,
                   'graphic': manifest, 'graphic_manifest': str(out / 'graphic.json'),
                   'roughness_bounds': [.50, .82],
                   'generator_sha256': digest(__file__),
                   'shader_source_sha256': digest(ROOT / 'unreal/MJOLNIRMaterials/Scripts/build_ce_materials.py'),
                   'validation': 'CPU candidate; no cooked or live appearance claim'})
    report['files'] = {str(p.relative_to(out)): digest(p) for p in out.rglob('*') if p.is_file()}
    for entry in report['sources'].values():
        entry['export'] = str(out / 'textures' / Path(entry['export']).name)
    dump(out / 'receipt.json', report)
    dump(out / 'config.fragment.json', {'paving_graphic': str(out / 'graphic.json'),
                                      'paving_materials': str(out / 'receipt.json'),
                                      'material_overrides': str(out / 'material-overrides.json')})
    print(json.dumps({'manifest': str(out / 'graphic.json'), 'receipt': str(out / 'receipt.json')}))
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=ROOT / 'out/pwr/visual-v6/surface/paving')
    parser.add_argument('--out', type=Path, default=ROOT / 'out/pwr/visual-v7/paving')
    args = parser.parse_args()
    prepare(args.source, args.out)
