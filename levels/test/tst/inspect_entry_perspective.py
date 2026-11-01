"""Inspect the entrance end-panel sightlines in an assembled Blender preview.

The check samples each front side panel from its corresponding saved entrance
camera. It catches a panel whose near end is hidden by the entrance jamb. It is
not an exhaustive visibility, collision, or in-game test. It never saves the
preview file. Run with Blender's ``--python-exit-code 1``.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

import bpy
from bpy_extras.object_utils import world_to_camera_view
from mathutils import Vector


METRES_PER_UNIT = 3.048
PANEL_PREFIX = 'facility_blind_end_side_'
BACKING_PREFIX = PANEL_PREFIX + 'backing'
RESOLUTION = (1715, 965)
VIEWS = {
    'red': (-1, Vector((-48, 38.8, 1.8)), Vector((-48, 25, 2.3))),
    'blue': (1, Vector((48, 38.8, 1.8)), Vector((48, 25, 2.3))),
}


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def family(name, prefix):
    return name == prefix or name.startswith(prefix + '.')


def bounds_metres(obj):
    points = [obj.matrix_world @ Vector(corner) * METRES_PER_UNIT for corner in obj.bound_box]
    return [(min(p[i] for p in points), max(p[i] for p in points)) for i in range(3)]


def validate_camera(camera, name, position, target):
    if not camera or camera.type != 'CAMERA':
        return f'Missing diagnostic camera {name!r}'
    data = camera.data
    if (data.type != 'PERSP' or abs(data.lens - 20) > .001 or
            abs(data.sensor_width - 36) > .001 or data.sensor_fit != 'AUTO' or
            abs(data.shift_x) > .0001 or abs(data.shift_y) > .0001):
        return f'{name}: lens or sensor changed; review and rebaseline the check'
    if (camera.matrix_world.translation * METRES_PER_UNIT - position).length > .005:
        return f'{name}: camera moved; review and rebaseline the check'
    actual = (camera.matrix_world.to_quaternion() @ Vector((0, 0, -1))).normalized()
    if actual.angle((target - position).normalized()) > .0005:
        return f'{name}: direction changed; review and rebaseline the check'
    return None


def inspect(scene, color, side, camera):
    matches = []
    for obj in bpy.data.objects:
        if obj.type != 'MESH' or not family(obj.name, BACKING_PREFIX):
            continue
        bounds = bounds_metres(obj)
        cx = (bounds[0][0] + bounds[0][1]) / 2
        cy = (bounds[1][0] + bounds[1][1]) / 2
        if cx * side > 0 and 20 < cy < 30:
            matches.append((obj, bounds))
    if len(matches) != 1:
        return [], [f'{color}: expected one front side-panel backing, found {len(matches)}']
    obj, bounds = matches[0]
    (x0, x1), (_, y1), (z0, z1) = bounds
    if x1 - x0 <= .15 or z1 - z0 <= .3:
        return [], [f'{color}: backing {obj.name} is too small to inspect']
    # Sample 6 cm inside each vertical edge and at the centre. Multiple
    # heights catch the jamb masking only part of the panel. A visible infill
    # or frame belonging to the same field is an acceptable first hit.
    xs = (x0 + .06, (x0 + x1) / 2, x1 - .06)
    zs = (z0 + .6, (z0 + z1) / 2, z1 - .6)
    depsgraph = bpy.context.evaluated_depsgraph_get()
    origin = camera.matrix_world.translation.copy()
    samples, issues = [], []
    for x in xs:
        for z in zs:
            target = Vector((x, y1, z)) / METRES_PER_UNIT
            projected = world_to_camera_view(scene, camera, target)
            direction = target - origin
            hit, point, _, _, hit_obj, _ = scene.ray_cast(
                depsgraph, origin, direction.normalized(), distance=direction.length + .01)
            name = hit_obj.name if hit else None
            in_frame = 0 <= projected.x <= 1 and 0 <= projected.y <= 1 and projected.z > 0
            # The visible field layers sit at most a few centimetres in front
            # of the backing; reject an unrelated field farther down the ray.
            same_field = bool(hit and name.startswith(PANEL_PREFIX) and
                              (point - target).length * METRES_PER_UNIT < .2)
            sample = {'target_m': [round(x, 4), round(y1, 4), round(z, 4)],
                      'in_camera_frame': in_frame, 'first_hit': name,
                      'visible': in_frame and same_field}
            samples.append(sample)
            if not sample['visible']:
                issues.append(f"{color}: panel sample {sample['target_m']} not visible (first hit: {name})")
    return samples, issues


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--blend', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--views', nargs='+', choices=tuple(VIEWS), default=list(VIEWS),
                        help='Entrances whose saved cameras exist in this preview (default: both)')
    args = parser.parse_args(sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else [])
    source = args.blend.resolve(strict=True)
    output = args.out.resolve()
    if source == output:
        raise ValueError('Report must not overwrite the preview blend')
    before = digest(source)
    bpy.ops.wm.open_mainfile(filepath=str(source))
    scene = bpy.context.scene
    scene.render.resolution_x, scene.render.resolution_y = RESOLUTION
    scene.render.resolution_percentage = 100
    scene.render.pixel_aspect_x = scene.render.pixel_aspect_y = 1
    checks, issues = {}, []
    for color in dict.fromkeys(args.views):
        side, position, target = VIEWS[color]
        name = f'PREVIEW CAMERA - facility-entry-{color}-inside'
        camera = bpy.data.objects.get(name)
        error = validate_camera(camera, name, position, target)
        if error:
            issues.append(error)
            checks[color] = []
            continue
        checks[color], found = inspect(scene, color, side, camera)
        issues.extend(found)
    unchanged = before == digest(source)
    if not unchanged:
        issues.append('The source preview changed during inspection')
    report = {'source_blend': str(source), 'source_sha256': before,
              'source_unchanged': unchanged, 'resolution': list(RESOLUTION),
              'scope': 'Nine sampled rays per selected Blender entrance camera; not all angles or an in-game check.',
              'checks': checks, 'issues': issues, 'issue_count': len(issues)}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(f'ENTRY_PERSPECTIVE {len(issues)} issue(s); report: {output}')
    for issue in issues:
        print('ISSUE:', issue)
    if issues:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
