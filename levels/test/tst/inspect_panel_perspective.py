"""Check the marked hallway panel/support sightline in an assembled preview.

Run under Blender, not the system Python interpreter. The input is the
``preview.blend`` made by ``preview-native.ps1``. This one ray is a regression
check for the specific user-reported view, not a general occlusion or game
collision test. The preview file is read but never saved or changed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

import bpy
from mathutils import Vector


METRES_PER_UNIT = 3.048
CAMERA_NAME = 'PREVIEW CAMERA - facility-panel-bays'
CAMERA_POSITION_M = Vector((-30, 28.5, 1.8))
CAMERA_TARGET_M = Vector((-19, 32.8, 1.9))
EXPECTED_SUPPORT_M = Vector((-14.317, 36.925, 1.846))
WIDTH, HEIGHT = 1715, 965
PIXEL = (713, 489)  # centre of the user's annotated overlapping area
SUPPORT_PREFIX = 'facility_branch_rib'
PANEL_PREFIXES = ('facility_branch_shadow_field', 'facility_branch_fitted_field',
                  'facility_branch_nested_field')
WALL_NAME = 'TST_sealed_terrain_and_sky'


def args_after_dash():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--blend', required=True, type=Path,
                        help='Assembled Blender preview.blend to inspect')
    parser.add_argument('--out', required=True, type=Path,
                        help='Write a JSON report here; never overwrite the blend')
    return parser.parse_args(sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else [])


def sha256(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def is_family(name, prefix):
    return name == prefix or name.startswith(prefix + '.')


def check_camera(camera):
    if not camera or camera.type != 'CAMERA':
        raise ValueError(f'Missing diagnostic camera {CAMERA_NAME!r}')
    data = camera.data
    if (data.type != 'PERSP' or abs(data.lens - 25) > .001 or
            abs(data.sensor_width - 36) > .001 or data.sensor_fit != 'AUTO' or
            abs(data.shift_x) > .0001 or abs(data.shift_y) > .0001):
        raise ValueError('Diagnostic camera lens or sensor changed; review and rebaseline the ray')
    pos = camera.matrix_world.translation * METRES_PER_UNIT
    if (pos - CAMERA_POSITION_M).length > .005:
        raise ValueError('Diagnostic camera moved; review and rebaseline the ray')
    actual = (camera.matrix_world.to_quaternion() @ Vector((0, 0, -1))).normalized()
    expected = (CAMERA_TARGET_M - CAMERA_POSITION_M).normalized()
    if actual.angle(expected) > .0005:
        raise ValueError('Diagnostic camera direction changed; review and rebaseline the ray')


def trace(scene, camera):
    # Force the reference aspect ratio in memory; don't rely on whichever
    # camera happened to render last before preview.blend was saved.
    scene.render.resolution_x, scene.render.resolution_y = WIDTH, HEIGHT
    scene.render.resolution_percentage = 100
    scene.render.pixel_aspect_x = scene.render.pixel_aspect_y = 1
    corners = sorted(camera.data.view_frame(scene=scene), key=lambda v: (v.y, v.x))
    ll, lr = corners[:2]
    ul, ur = corners[2:]
    x, y = (PIXEL[0] + .5) / WIDTH, 1 - (PIXEL[1] + .5) / HEIGHT
    local = ll * (1 - x) * (1 - y) + lr * x * (1 - y) + ul * (1 - x) * y + ur * x * y
    origin = camera.matrix_world.translation.copy()
    direction = (camera.matrix_world.to_3x3() @ local).normalized()
    depsgraph = bpy.context.evaluated_depsgraph_get()
    hits = []
    for _ in range(50):
        hit, point, _, _, obj, _ = scene.ray_cast(depsgraph, origin, direction, distance=100)
        if not hit:
            break
        hits.append({'object': obj.name, 'position_m': [round(v * METRES_PER_UNIT, 4) for v in point]})
        # Step past the face, including both the entry and exit faces of the
        # support. 0.3 mm is small compared with the nearest panel setback.
        origin = point + direction * .0001
        if obj.name == WALL_NAME:
            break
    return hits


def main():
    args = args_after_dash()
    source = args.blend.resolve(strict=True)
    out = args.out.resolve()
    if source == out:
        raise ValueError('Report must not overwrite the preview blend')
    before = sha256(source)
    bpy.ops.wm.open_mainfile(filepath=str(source))
    camera = bpy.data.objects.get(CAMERA_NAME)
    issues = []
    try:
        check_camera(camera)
    except ValueError as exc:
        hits = []
        issues.append(str(exc))
    else:
        hits = trace(bpy.context.scene, camera)
        if not hits or not is_family(hits[0]['object'], SUPPORT_PREFIX):
            issues.append('Reference ray no longer starts on the expected branch support')
        elif (Vector(hits[0]['position_m']) - EXPECTED_SUPPORT_M).length > .10:
            issues.append('Reference support moved; review and rebaseline the ray')
        if not hits or hits[-1]['object'] != WALL_NAME:
            issues.append('Reference ray did not reach the expected structural wall')
        if any(any(is_family(hit['object'], prefix) for prefix in PANEL_PREFIXES) for hit in hits[1:]):
            issues.append('A branch panel lies behind the support at the annotated pixel')
    after = sha256(source)
    if before != after:
        issues.append('The source preview changed during inspection')
    report = {
        'source_blend': str(source), 'source_sha256': before,
        'source_unchanged': before == after,
        'scope': 'One Blender preview sightline only; not an all-view or in-game collision check.',
        'camera': CAMERA_NAME, 'resolution': [WIDTH, HEIGHT], 'pixel': list(PIXEL),
        'hits': hits, 'issues': issues, 'issue_count': len(issues),
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(f'PANEL_PERSPECTIVE {len(issues)} issue(s); report: {out}')
    if issues:
        for issue in issues:
            print('ISSUE:', issue)
        raise SystemExit(1)


if __name__ == '__main__':
    main()
