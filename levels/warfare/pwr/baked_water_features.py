"""Place native cascade spray on the actual saved Flux surface, not design Z.

This is an offline presentation recipe. It never alters water state, geometry,
native collision or gameplay. Outputs remain candidates until visual review.
"""
from pathlib import Path
import argparse
import hashlib
import json
import math
import sys

import numpy as np
from shapely.geometry import Point, Polygon

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'tools/level'))
from audit_flux_state import sample, texture
from flux_heightfield import verify_state_files
from water_features import SPRAY, SPLASH


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def build(geometry_path, states_root, config_path, output):
    geometry_path, states_root, config_path, output = map(Path, (geometry_path, states_root, config_path, output))
    geometry = json.loads(geometry_path.read_text())
    config = json.loads(config_path.read_text())['PWR']
    waves = [domain['ocean_wave'] for domain in config['flux']['domains'] if domain.get('ocean_wave')]
    lakes = [(Polygon(lake['polygon_m']), float(lake['water_z_m'])) for lake in geometry['lakes']]
    states = []
    inputs = {str(path.resolve()): sha(path) for path in (geometry_path, config_path)}
    for state_path in sorted((states_root / 'flux_state').glob('*/state.json')):
        state = json.loads(state_path.read_text())
        verify_state_files(states_root, state)
        h = texture(states_root / state['height'])
        v = texture(states_root / state['velocity'])
        states.append((state, (h[..., 0] + state['capture']) / 100, v[..., 2] / 100))
        for file in (state_path, *(states_root / state[k] for k in ('height', 'velocity', 'ground'))):
            inputs[str(file.resolve())] = sha(file)
    if not states:
        raise ValueError('No verified native Flux states')

    falls, measurements = [], []
    for river in geometry['watercourses']:
        line = np.asarray(river['surface_centreline_m'], dtype=float)
        arc = np.r_[0, np.cumsum(np.linalg.norm(np.diff(line[:, :2], axis=0), axis=1))]
        for number, cascade in enumerate(river.get('cascades', [])):
            middle = int(np.argmin(np.linalg.norm(line[:, :2] - cascade['position_m'], axis=1)))
            # Cascades are specified at the middle of their descent. Place
            # splash downstream of its foot using measured arclength, not an
            # assumed number of samples per metre.
            reach = float(cascade['reach_length_m'])
            foot_arc = min(arc[-2], arc[middle] + reach * .5 + min(12, max(4, reach * .12)))
            foot = int(np.clip(np.searchsorted(arc, foot_arc), 1, len(line) - 2))
            tangent = line[foot + 1, :2] - line[foot - 1, :2]
            tangent /= np.linalg.norm(tangent)
            normal = np.array([-tangent[1], tangent[0]])
            yaw = math.degrees(math.atan2(-tangent[1], tangent[0]))
            effects, samples = [], []
            for side in (-.18, 0, .18):
                xy = line[foot, :2] + normal * float(river['channel_width_m']) * side
                candidates = []
                for state, surface, depth in states:
                    z, valid = sample(surface, state, xy[None, :])
                    d, _ = sample(depth, state, xy[None, :])
                    if valid[0] and d[0] > .2:
                        candidates.append((float(z[0]), float(d[0])))
                if len(candidates) != 1:
                    raise ValueError(f'Expected one wet Flux tile at {river["id"]}/{number}/{side}')
                z, depth = candidates[0]
                visible_z = z
                for polygon, lake_z in lakes:
                    if polygon.covers(Point(*xy)):
                        matching = [wave for wave in waves if abs(wave['water_height_cm'] / 100 - lake_z) < 1e-5]
                        if len(matching) != 1:
                            raise ValueError('Lake spray requires its explicit native coastline wave configuration')
                        wave = matching[0]
                        # Coastline waves can cover a slightly lower saved river
                        # outlet. Keep the spray emitter above the visible crest.
                        visible_z = max(visible_z, lake_z + (wave['offset_cm'] + wave['height_cm']) / 100)
                large = cascade['drop_m'] > 5
                # Loader's waterfall scale is scalar. A vector was silently
                # falling back to1, leaving an almost invisible stock effect.
                scale = (5.0 if side == 0 else 3.2) if large else 2.4
                effects.append({'system': SPLASH if large and side == 0 else SPRAY,
                    'pos': [float(xy[0] * 100), float(-xy[1] * 100), (visible_z + .12) * 100],
                    'rot': [0, yaw, 0], 'scale': scale})
                samples.append({'side': side, 'water_z_m': z, 'visible_water_crest_m': visible_z,
                                'emitter_z_m': visible_z + .12, 'depth_m': depth, 'scale': scale})
            falls.append({'pos': (line[middle] * [100, -100, 100]).tolist(),
                          'yaw': yaw, 'sheet': False, 'effects': effects})
            measurements.append({'river': river['id'], 'cascade': number,
                'centre_arc_m': float(arc[middle]), 'foot_arc_m': float(arc[foot]),
                'authored_drop_m': cascade['drop_m'], 'samples': samples})
    for path, digest in inputs.items():
        if sha(path) != digest:
            raise ValueError('Source changed during recipe generation: ' + path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('x') as stream:
        json.dump({'schema': 'pwr-baked-cascade-effects-v1', 'status': 'candidate_pending_live_review',
            'waterfalls': {'falls': falls},
            'surface_scalars': {'FoamColorAlpha': 1, 'FoamSoftIntensity': 3, 'FoamSoftBase': .05,
                                'FoamSoftMax': .8, 'StateFoamSlope': 3, 'StateFoamDivergence': 2},
            'inputs': inputs, 'measurements': measurements,
            'water_state_changed': False, 'physics_changed': False}, stream, indent=2)
    print(json.dumps({'output': str(output), 'falls': len(falls),
                      'native_effects': sum(len(f['effects']) for f in falls), 'sha256': sha(output)}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--geometry', type=Path, required=True)
    parser.add_argument('--states', type=Path, required=True)
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    build(args.geometry, args.states, args.config, args.out)
